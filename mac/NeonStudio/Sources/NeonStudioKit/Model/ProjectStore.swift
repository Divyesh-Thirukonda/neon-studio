import Foundation

public enum ProjectStoreError: LocalizedError {
    case unreadableProjectFile(URL)
    case notANeonProject(URL)

    public var errorDescription: String? {
        switch self {
        case .unreadableProjectFile(let url):
            return "Couldn't read \(url.lastPathComponent)."
        case .notANeonProject(let url):
            return "\(url.lastPathComponent) isn't a Neon Studio project."
        }
    }

    public var recoverySuggestion: String? {
        switch self {
        case .unreadableProjectFile:
            return "The file may have been moved, renamed, or damaged. Try opening it again from its current location."
        case .notANeonProject:
            return "Neon Studio opens .neon.json project files. Choose a different file, or use File ▸ Import Audio to bring in a sound."
        }
    }
}

/// The on-disk project library: bundled factory songs plus the user's own
/// projects, both living under the app's support directory.
///
/// Individual documents are read and written by `NeonDocument`; this type owns
/// the *library* concerns — enumerating projects, hiding deleted factory songs,
/// and resolving audio paths relative to the support root.
public final class ProjectStore {
    public let rootURL: URL
    private let decoder = JSONDecoder()
    private let encoder = JSONEncoder()

    /// Factory ids are needed on every delete. Reading and decoding every
    /// factory file each time was measurably slow, so the id set is cached and
    /// invalidated whenever the library is reloaded.
    private var cachedFactoryIds: Set<String>?

    public init(rootURL: URL) {
        self.rootURL = rootURL
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    }

    // MARK: Library

    public func loadProjects() -> [LocalProject] {
        cachedFactoryIds = nil
        let deletedIds = Set(readDeletedIds())
        let factoryProjects = loadFactoryProjects().filter { !deletedIds.contains($0.id) }
        let storedProjects = projectFiles(in: dataDirectory()).compactMap { loadProjectFile($0) }
        let storedById = Dictionary(storedProjects.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })

        var merged: [LocalProject] = []
        var factoryIds = Set<String>()

        for factory in factoryProjects {
            factoryIds.insert(factory.id)
            if var stored = storedById[factory.id] {
                stored.projectFile = stored.projectFile ?? factory.projectFile
                stored.assets = stored.assets ?? factory.assets
                stored.description = stored.description ?? factory.description
                stored.keyCenter = stored.keyCenter ?? factory.keyCenter
                merged.append(ProjectNormalizer.normalize(stored))
            } else {
                merged.append(ProjectNormalizer.normalize(factory))
            }
        }

        merged.append(contentsOf: storedProjects.filter { !factoryIds.contains($0.id) }.map(ProjectNormalizer.normalize))
        // Sort on parsed dates. Comparing the raw strings put "2025-06-12T04:41Z"
        // after "2025-06-12T04:41:07.221Z" and generally mis-ordered whenever two
        // files had been written by different tools with different ISO-8601
        // precision, so the wrong project appeared at the top of the list.
        return merged.sorted { lhs, rhs in
            let left = ProjectStore.parseDate(lhs.updatedAt)
            let right = ProjectStore.parseDate(rhs.updatedAt)
            if left != right { return left > right }
            return lhs.name.localizedStandardCompare(rhs.name) == .orderedAscending
        }
    }

    /// Accepts ISO-8601 with or without fractional seconds; unparseable values
    /// sort last rather than throwing off the whole list.
    public static func parseDate(_ raw: String?) -> Date {
        guard let raw, !raw.isEmpty else { return .distantPast }
        let withFraction = ISO8601DateFormatter()
        withFraction.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = withFraction.date(from: raw) { return date }
        let plain = ISO8601DateFormatter()
        plain.formatOptions = [.withInternetDateTime]
        if let date = plain.date(from: raw) { return date }
        return .distantPast
    }

    @discardableResult
    public func saveProject(_ project: LocalProject) throws -> LocalProject {
        try FileManager.default.createDirectory(at: dataDirectory(), withIntermediateDirectories: true)
        let normalized = ProjectNormalizer.normalize(project)
        try encode(normalized).write(to: projectURL(for: normalized.id), options: [.atomic])
        var deleted = readDeletedIds()
        if deleted.contains(normalized.id) {
            deleted.removeAll { $0 == normalized.id }
            try writeDeletedIds(deleted)
        }
        return normalized
    }

    public func deleteProject(_ project: LocalProject) throws {
        let url = projectURL(for: project.id)
        if FileManager.default.fileExists(atPath: url.path) {
            // Move to the Trash rather than unlink, so a mis-click is recoverable
            // from the Finder instead of being permanent.
            var trashed: NSURL?
            try FileManager.default.trashItem(at: url, resultingItemURL: &trashed)
        }
        if isFactoryProject(project.id) {
            var deleted = readDeletedIds()
            if !deleted.contains(project.id) {
                deleted.append(project.id)
                try writeDeletedIds(deleted)
            }
        }
    }

    public func restoreDeletedFactoryProjects() throws {
        try writeDeletedIds([])
    }

    public var hiddenFactoryProjectCount: Int {
        readDeletedIds().count
    }

    // MARK: Files

    public func encode(_ project: LocalProject) throws -> Data {
        try encoder.encode(ProjectFileEnvelope(project: ProjectNormalizer.normalize(project)))
    }

    public func decode(_ data: Data, fallbackName: String) throws -> LocalProject {
        if let project = try? decoder.decode(LocalProject.self, from: data) {
            return ProjectNormalizer.normalize(project)
        }
        if let envelope = try? decoder.decode(ProjectFileEnvelope.self, from: data) {
            return ProjectNormalizer.normalize(envelope.project)
        }
        throw ProjectStoreError.notANeonProject(URL(fileURLWithPath: fallbackName))
    }

    public func loadProject(from url: URL) -> LocalProject? {
        loadProjectFile(url)
    }

    public func exportProject(_ project: LocalProject, to url: URL) throws {
        try encode(project).write(to: url, options: [.atomic])
    }

    public func importProject(from url: URL) throws -> LocalProject {
        guard let imported = loadProjectFile(url) else {
            throw ProjectStoreError.unreadableProjectFile(url)
        }
        var project = ProjectNormalizer.normalize(imported)
        project.id = uniqueProjectId(basedOn: project.id)
        project.createdAt = project.createdAt ?? nowISO()
        project.updatedAt = nowISO()
        return try saveProject(project)
    }

    /// The file URL to open a library project from, so it becomes a real
    /// file-backed document rather than an untitled copy.
    ///
    /// A bundled example lives read-only in `factory/`, so opening one makes the
    /// user's own copy in `data/projects/` first. That way ⌘S saves where they
    /// expect, and the pristine example stays intact for next time.
    public func fileURLForEditing(_ project: LocalProject) throws -> URL {
        let url = projectURL(for: project.id)
        if FileManager.default.fileExists(atPath: url.path) {
            return url
        }
        _ = try saveProject(project)
        return url
    }

    /// Returns `candidate` if no project file claims it, otherwise appends the
    /// smallest numeric suffix that is free. Prevents the silent overwrite the
    /// previous timestamp-suffix scheme allowed.
    public func uniqueProjectId(basedOn candidate: String) -> String {
        let base = safeProjectId(candidate)
        guard FileManager.default.fileExists(atPath: projectURL(for: base).path) else { return base }
        for suffix in 2...9999 {
            let next = safeProjectId("\(base)-\(suffix)")
            if !FileManager.default.fileExists(atPath: projectURL(for: next).path) {
                return next
            }
        }
        return safeProjectId("\(base)-\(UUID().uuidString.prefix(8))")
    }

    private func projectFiles(in directory: URL) -> [URL] {
        guard let urls = try? FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil) else {
            return []
        }
        return urls.filter { $0.lastPathComponent.hasSuffix(".neon.json") }.sorted { $0.path < $1.path }
    }

    private func loadFactoryProjects() -> [LocalProject] {
        let factoryRoot = rootURL.appendingPathComponent("factory", isDirectory: true)
        let indexURL = factoryRoot.appendingPathComponent("projects/index.json")

        if let data = try? Data(contentsOf: indexURL),
           let index = try? decoder.decode(ProjectIndex.self, from: data),
           let entries = index.projects, !entries.isEmpty {
            return entries.compactMap { entry in
                // Index entries are stored relative to `factory/` (e.g.
                // "projects/neon-alone.neon.json"). Absolute-looking entries are
                // trimmed so they can never escape the factory directory.
                let relative = entry.file.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
                var project = loadProjectFile(factoryRoot.appendingPathComponent(relative))
                project?.projectFile = entry.file
                return project
            }
        }
        return projectFiles(in: factoryRoot.appendingPathComponent("projects")).compactMap { loadProjectFile($0) }
    }

    private func loadProjectFile(_ url: URL) -> LocalProject? {
        guard let data = try? Data(contentsOf: url) else { return nil }
        return try? decode(data, fallbackName: url.lastPathComponent)
    }

    /// True for one of the bundled example songs, as opposed to the user's own.
    /// The UI marks these so a beginner can tell demo content from their work.
    public func isFactoryProject(_ id: String) -> Bool {
        if cachedFactoryIds == nil {
            cachedFactoryIds = Set(loadFactoryProjects().map(\.id))
        }
        return cachedFactoryIds?.contains(id) ?? false
    }

    // MARK: Locations

    public func dataDirectory() -> URL {
        rootURL.appendingPathComponent("data/projects", isDirectory: true)
    }

    public func exportsDirectory() -> URL {
        rootURL.appendingPathComponent("exports", isDirectory: true)
    }

    public func vocalInboxDirectory() -> URL {
        rootURL.appendingPathComponent("vocal_inbox", isDirectory: true)
    }

    public func projectURL(for id: String) -> URL {
        dataDirectory().appendingPathComponent("\(safeProjectId(id)).neon.json")
    }

    public func deletedURL() -> URL {
        rootURL.appendingPathComponent("data/deleted-projects.json")
    }

    public func toolURL(_ name: String) -> URL {
        rootURL.appendingPathComponent("tools").appendingPathComponent(name)
    }

    /// Resolves a track's `file` field, which historically held absolute paths,
    /// `file://` URLs, legacy `/api/audio/...` web paths, or paths relative to
    /// the support root.
    public func audioURL(for track: Track) -> URL? {
        guard let file = track.file, !file.isEmpty else { return nil }
        if file.hasPrefix("file://"), let url = URL(string: file) {
            return url
        }
        if file.hasPrefix("/api/audio/") {
            return exportsDirectory().appendingPathComponent(URL(fileURLWithPath: file).lastPathComponent)
        }
        if file.hasPrefix("/") {
            return URL(fileURLWithPath: file)
        }
        return rootURL.appendingPathComponent(file)
    }

    public func existingAudioURL(for track: Track) -> URL? {
        guard let url = audioURL(for: track), FileManager.default.fileExists(atPath: url.path) else { return nil }
        return url
    }

    public func fullMixURL(for project: LocalProject) -> URL? {
        let file = "\(project.id.replacingOccurrences(of: "-", with: "_"))_full_mix.wav"
        let url = exportsDirectory().appendingPathComponent(file)
        return FileManager.default.fileExists(atPath: url.path) ? url : nil
    }

    /// How many of a project's tracks actually have audio on disk. Drives the
    /// "3 of 12 tracks have audio" hint instead of silently playing nothing.
    public func audioTrackCounts(for project: LocalProject) -> (withAudio: Int, total: Int) {
        let total = project.snapshot.tracks.count
        let withAudio = project.snapshot.tracks.filter { existingAudioURL(for: $0) != nil }.count
        return (withAudio, total)
    }

    // MARK: Deleted markers

    private func readDeletedIds() -> [String] {
        guard let data = try? Data(contentsOf: deletedURL()),
              let ids = try? decoder.decode([String].self, from: data) else {
            return []
        }
        return ids
    }

    private func writeDeletedIds(_ ids: [String]) throws {
        try FileManager.default.createDirectory(
            at: rootURL.appendingPathComponent("data", isDirectory: true),
            withIntermediateDirectories: true
        )
        try encoder.encode(Array(Set(ids)).sorted()).write(to: deletedURL(), options: [.atomic])
    }
}
