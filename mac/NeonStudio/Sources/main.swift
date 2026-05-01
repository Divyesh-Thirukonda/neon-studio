import AppKit
import AVFoundation
import UniformTypeIdentifiers

struct LocalProject: Codable {
    var id: String
    var name: String
    var createdAt: String?
    var updatedAt: String
    var projectFile: String?
    var assets: [ProjectAsset]?
    var description: String?
    var keyCenter: String?
    var snapshot: ProjectSnapshot
}

struct ProjectAsset: Codable {
    var trackId: String
    var file: String
    var data: String?
}

struct ProjectSnapshot: Codable {
    var version: Int?
    var bpm: Double
    var swing: Double?
    var snap: String?
    var loopEnabled: Bool?
    var loopStartBar: Double?
    var loopEndBar: Double?
    var tracks: [Track]
    var controls: [String: MixerControl]?
    var notes: [PianoNote]?
    var selectedTrackId: String?
    var selectedClipId: String?
    var activeView: String?
    var patternIndex: Int?
    var arrangementMode: String?
    var recipe: [RecipeItem]?
}

struct Track: Codable {
    var id: String
    var name: String
    var kind: String?
    var file: String?
    var color: String?
    var gain: Double?
    var pan: Double?
    var steps: [Int]?
    var instrument: String?
    var clips: [Clip]?
    var effects: [Effect]?
}

struct Clip: Codable {
    var id: String
    var name: String
    var startBar: Double?
    var bars: Double?
    var lane: String?
    var color: String?
    var type: String?
}

struct Effect: Codable {
    var id: String
    var name: String
    var active: Bool?
    var amount: Double?
}

struct MixerControl: Codable {
    var gain: Double
    var pan: Double
    var mute: Bool
    var solo: Bool
    var arm: Bool
    var sendA: Double
    var sendB: Double
}

struct PianoNote: Codable {
    var id: String
    var beat: Double
    var duration: Double
    var note: Int
    var velocity: Double
    var color: String
}

struct RecipeItem: Codable {
    var id: String
    var section: String?
    var label: String
    var detail: String?
    var status: String?
    var trackIds: [String]?
}

struct ProjectIndex: Codable {
    struct Entry: Codable {
        var id: String
        var file: String
    }
    var projects: [Entry]?
}

struct ProjectFileEnvelope: Codable {
    var format: String
    var formatVersion: Int
    var portable: Bool
    var assetMode: String
    var id: String
    var name: String
    var createdAt: String?
    var updatedAt: String
    var projectFile: String?
    var assets: [ProjectAsset]?
    var description: String?
    var keyCenter: String?
    var snapshot: ProjectSnapshot
}

enum WorkView: String, CaseIterable {
    case playlist
    case piano
    case mixer
    case plugins
    case sample
    case recipe

    var label: String {
        switch self {
        case .playlist: return "Playlist"
        case .piano: return "Piano"
        case .mixer: return "Mixer"
        case .plugins: return "Plugins"
        case .sample: return "Sample"
        case .recipe: return "Recipe"
        }
    }
}

enum ToolId: String, CaseIterable {
    case select
    case draw
    case paint
    case slice
    case mute
    case erase

    var label: String {
        switch self {
        case .select: return "Select"
        case .draw: return "Draw"
        case .paint: return "Paint"
        case .slice: return "Slice"
        case .mute: return "Mute"
        case .erase: return "Erase"
        }
    }
}

final class ProjectStore {
    let rootURL: URL
    private let decoder = JSONDecoder()
    private let encoder = JSONEncoder()

    init(rootURL: URL) {
        self.rootURL = rootURL
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    }

    func loadProjects() -> [LocalProject] {
        let deletedIds = Set(readDeletedIds())
        let factoryProjects = loadFactoryProjects().filter { !deletedIds.contains($0.id) }
        let storedProjects = projectFiles(in: dataDirectory()).compactMap { loadProjectFile($0) }
        let storedById = Dictionary(uniqueKeysWithValues: storedProjects.map { ($0.id, $0) })
        var merged: [LocalProject] = []
        var factoryIds = Set<String>()

        for factory in factoryProjects {
            factoryIds.insert(factory.id)
            if var stored = storedById[factory.id] {
                stored.projectFile = stored.projectFile ?? factory.projectFile
                stored.assets = stored.assets ?? factory.assets
                stored.description = stored.description ?? factory.description
                stored.keyCenter = stored.keyCenter ?? factory.keyCenter
                merged.append(normalize(stored))
            } else {
                merged.append(normalize(factory))
            }
        }

        merged.append(contentsOf: storedProjects.filter { !factoryIds.contains($0.id) }.map(normalize))
        return merged.sorted { lhs, rhs in
            lhs.updatedAt > rhs.updatedAt
        }
    }

    func saveProject(_ project: LocalProject) throws -> LocalProject {
        let dataDirectory = dataDirectory()
        try FileManager.default.createDirectory(at: dataDirectory, withIntermediateDirectories: true)
        let normalized = normalize(project)
        let envelope = ProjectFileEnvelope(
            format: "neon-studio-project",
            formatVersion: 1,
            portable: true,
            assetMode: normalized.assets?.contains(where: { $0.data != nil }) == true ? "embedded" : "external",
            id: normalized.id,
            name: normalized.name,
            createdAt: normalized.createdAt,
            updatedAt: normalized.updatedAt,
            projectFile: normalized.projectFile,
            assets: normalized.assets,
            description: normalized.description,
            keyCenter: normalized.keyCenter,
            snapshot: normalized.snapshot
        )
        let data = try encoder.encode(envelope)
        try data.write(to: projectURL(for: normalized.id), options: [.atomic])
        var deleted = readDeletedIds()
        if deleted.contains(normalized.id) {
            deleted.removeAll { $0 == normalized.id }
            try writeDeletedIds(deleted)
        }
        return normalized
    }

    func deleteProject(_ project: LocalProject) throws {
        let url = projectURL(for: project.id)
        if FileManager.default.fileExists(atPath: url.path) {
            try FileManager.default.removeItem(at: url)
        }
        if isFactoryProject(project.id) {
            var deleted = readDeletedIds()
            if !deleted.contains(project.id) {
                deleted.append(project.id)
                try writeDeletedIds(deleted)
            }
        }
    }

    func importProject(from url: URL) throws -> LocalProject {
        guard let imported = loadProjectFile(url) else {
            throw NSError(domain: "NeonStudio", code: 1, userInfo: [NSLocalizedDescriptionKey: "Could not read project file"])
        }
        var project = normalize(imported)
        let stamp = timestampForId()
        project.id = "\(safeProjectId(project.id))-import-\(stamp)"
        project.createdAt = project.createdAt ?? nowISO()
        project.updatedAt = nowISO()
        return try saveProject(project)
    }

    func exportProject(_ project: LocalProject, to url: URL) throws {
        let normalized = normalize(project)
        let envelope = ProjectFileEnvelope(
            format: "neon-studio-project",
            formatVersion: 1,
            portable: true,
            assetMode: normalized.assets?.contains(where: { $0.data != nil }) == true ? "embedded" : "external",
            id: normalized.id,
            name: normalized.name,
            createdAt: normalized.createdAt,
            updatedAt: normalized.updatedAt,
            projectFile: normalized.projectFile,
            assets: normalized.assets,
            description: normalized.description,
            keyCenter: normalized.keyCenter,
            snapshot: normalized.snapshot
        )
        try encoder.encode(envelope).write(to: url, options: [.atomic])
    }

    private func projectFiles(in directory: URL) -> [URL] {
        guard let urls = try? FileManager.default.contentsOfDirectory(
            at: directory,
            includingPropertiesForKeys: nil
        ) else {
            return []
        }
        return urls.filter { $0.lastPathComponent.hasSuffix(".neon.json") }
    }

    private func loadFactoryProjects() -> [LocalProject] {
        let indexURL = rootURL.appendingPathComponent("factory/projects/index.json")
        if let data = try? readData(indexURL),
           let index = try? decoder.decode(ProjectIndex.self, from: data),
           let entries = index.projects {
            return entries.compactMap { entry in
                let path = entry.file.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
                let url = rootURL.appendingPathComponent("factory").appendingPathComponent(path.replacingOccurrences(of: "projects/", with: "projects/"))
                var project = loadProjectFile(url)
                project?.projectFile = entry.file
                return project
            }
        }
        return projectFiles(in: rootURL.appendingPathComponent("factory/projects")).compactMap { loadProjectFile($0) }
    }

    private func loadProjectFile(_ url: URL) -> LocalProject? {
        guard let data = try? readData(url) else { return nil }
        if let project = try? decoder.decode(LocalProject.self, from: data) {
            return normalize(project)
        }
        if let envelope = try? decoder.decode(ProjectFileEnvelope.self, from: data) {
            return normalize(LocalProject(
                id: envelope.id,
                name: envelope.name,
                createdAt: envelope.createdAt,
                updatedAt: envelope.updatedAt,
                projectFile: envelope.projectFile,
                assets: envelope.assets,
                description: envelope.description,
                keyCenter: envelope.keyCenter,
                snapshot: envelope.snapshot
            ))
        }
        return nil
    }

    func audioURL(for track: Track) -> URL? {
        guard let file = track.file else { return nil }
        if file.hasPrefix("file://"), let url = URL(string: file) {
            return url
        }
        if file.hasPrefix("/") && !file.hasPrefix("/api/audio/") {
            return URL(fileURLWithPath: file)
        }
        if file.hasPrefix("/api/audio/") {
            return rootURL
                .appendingPathComponent("exports")
                .appendingPathComponent(URL(fileURLWithPath: file).lastPathComponent)
        }

        let cleaned = file.hasPrefix("/") ? String(file.dropFirst()) : file
        return rootURL.appendingPathComponent(cleaned)
    }

    func fullMixURL(for project: LocalProject) -> URL? {
        let file = "\(project.id.replacingOccurrences(of: "-", with: "_"))_full_mix.wav"
        let url = rootURL.appendingPathComponent("exports").appendingPathComponent(file)
        return FileManager.default.fileExists(atPath: url.path) ? url : nil
    }

    func dataDirectory() -> URL {
        rootURL.appendingPathComponent("data/projects")
    }

    func projectURL(for id: String) -> URL {
        dataDirectory().appendingPathComponent("\(safeProjectId(id)).neon.json")
    }

    func deletedURL() -> URL {
        rootURL.appendingPathComponent("data/deleted-projects.json")
    }

    private func readDeletedIds() -> [String] {
        guard let data = try? readData(deletedURL()),
              let ids = try? decoder.decode([String].self, from: data) else {
            return []
        }
        return ids
    }

    private func readData(_ url: URL) throws -> Data {
        return try Data(contentsOf: url)
    }

    private func writeDeletedIds(_ ids: [String]) throws {
        try FileManager.default.createDirectory(at: rootURL.appendingPathComponent("data"), withIntermediateDirectories: true)
        try encoder.encode(Array(Set(ids)).sorted()).write(to: deletedURL(), options: [.atomic])
    }

    private func isFactoryProject(_ id: String) -> Bool {
        loadFactoryProjects().contains { $0.id == id }
    }

    func normalize(_ project: LocalProject) -> LocalProject {
        var next = project
        next.id = safeProjectId(next.id)
        if next.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            next.name = "Untitled Project"
        }
        next.createdAt = next.createdAt ?? next.updatedAt
        next.snapshot.version = 3
        next.snapshot.swing = next.snapshot.swing ?? 0
        next.snapshot.snap = next.snapshot.snap ?? "1/4"
        next.snapshot.loopEnabled = next.snapshot.loopEnabled ?? false
        next.snapshot.loopStartBar = next.snapshot.loopStartBar ?? 0
        next.snapshot.loopEndBar = next.snapshot.loopEndBar ?? 16
        next.snapshot.controls = next.snapshot.controls ?? makeDefaultControls(for: next.snapshot.tracks)
        next.snapshot.notes = next.snapshot.notes ?? []
        next.snapshot.selectedTrackId = next.snapshot.selectedTrackId ?? next.snapshot.tracks.first?.id ?? ""
        next.snapshot.selectedClipId = next.snapshot.selectedClipId ?? next.snapshot.tracks.flatMap { $0.clips ?? [] }.first?.id ?? ""
        next.snapshot.activeView = next.snapshot.activeView ?? WorkView.playlist.rawValue
        next.snapshot.patternIndex = next.snapshot.patternIndex ?? 1
        next.snapshot.arrangementMode = next.snapshot.arrangementMode ?? "song"
        next.snapshot.recipe = next.snapshot.recipe ?? []
        return next
    }
}

func safeProjectId(_ id: String) -> String {
    let basename = URL(fileURLWithPath: id).lastPathComponent.replacingOccurrences(of: ".neon.json", with: "")
    let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "_-"))
    let cleaned = String(basename.unicodeScalars.map { allowed.contains($0) ? Character($0) : "-" })
        .trimmingCharacters(in: CharacterSet(charactersIn: "-_"))
    return cleaned.isEmpty ? "project-\(timestampForId())" : String(cleaned.prefix(72))
}

func makeDefaultControls(for tracks: [Track]) -> [String: MixerControl] {
    Dictionary(uniqueKeysWithValues: tracks.map { track in
        (
            track.id,
            MixerControl(
                gain: track.gain ?? 0.82,
                pan: track.pan ?? 0,
                mute: false,
                solo: false,
                arm: false,
                sendA: 0.15,
                sendB: 0.08
            )
        )
    })
}

func nowISO() -> String {
    ISO8601DateFormatter().string(from: Date())
}

func timestampForId() -> String {
    let formatter = DateFormatter()
    formatter.dateFormat = "HHmmss"
    return formatter.string(from: Date())
}

func makeId(_ prefix: String) -> String {
    "\(prefix)-\(UUID().uuidString.prefix(8).lowercased())"
}

enum Palette {
    static let app = NSColor(calibratedRed: 0.055, green: 0.065, blue: 0.075, alpha: 1)
    static let panel = NSColor(calibratedRed: 0.095, green: 0.105, blue: 0.118, alpha: 1)
    static let panelAlt = NSColor(calibratedRed: 0.118, green: 0.128, blue: 0.142, alpha: 1)
    static let panelRaised = NSColor(calibratedRed: 0.15, green: 0.16, blue: 0.18, alpha: 1)
    static let stroke = NSColor(calibratedRed: 0.255, green: 0.27, blue: 0.30, alpha: 1)
    static let subtleStroke = NSColor(calibratedRed: 0.18, green: 0.195, blue: 0.215, alpha: 1)
    static let text = NSColor(calibratedRed: 0.91, green: 0.90, blue: 0.86, alpha: 1)
    static let muted = NSColor(calibratedRed: 0.66, green: 0.67, blue: 0.65, alpha: 1)
    static let dim = NSColor(calibratedRed: 0.44, green: 0.46, blue: 0.49, alpha: 1)
    static let yellow = NSColor(calibratedRed: 1.0, green: 0.79, blue: 0.30, alpha: 1)
    static let blue = NSColor(calibratedRed: 0.42, green: 0.78, blue: 0.96, alpha: 1)
    static let coral = NSColor(calibratedRed: 1.0, green: 0.52, blue: 0.36, alpha: 1)
    static let green = NSColor(calibratedRed: 0.29, green: 0.83, blue: 0.55, alpha: 1)
}

func color(from hex: String?, fallback: NSColor = Palette.blue) -> NSColor {
    guard let hex else { return fallback }
    var cleaned = hex.trimmingCharacters(in: .whitespacesAndNewlines)
    if cleaned.hasPrefix("#") {
        cleaned.removeFirst()
    }

    guard cleaned.count == 6, let value = Int(cleaned, radix: 16) else {
        return fallback
    }

    let red = CGFloat((value >> 16) & 0xff) / 255
    let green = CGFloat((value >> 8) & 0xff) / 255
    let blue = CGFloat(value & 0xff) / 255
    return NSColor(calibratedRed: red, green: green, blue: blue, alpha: 1)
}

func drawText(
    _ text: String,
    in rect: NSRect,
    color: NSColor = Palette.text,
    size: CGFloat = 12,
    weight: NSFont.Weight = .regular,
    alignment: NSTextAlignment = .left,
    lineBreak: NSLineBreakMode = .byTruncatingTail
) {
    let paragraph = NSMutableParagraphStyle()
    paragraph.alignment = alignment
    paragraph.lineBreakMode = lineBreak
    let attributes: [NSAttributedString.Key: Any] = [
        .font: NSFont.systemFont(ofSize: size, weight: weight),
        .foregroundColor: color,
        .paragraphStyle: paragraph
    ]
    NSString(string: text).draw(in: rect, withAttributes: attributes)
}

func roundedFill(_ rect: NSRect, radius: CGFloat, color: NSColor) {
    color.setFill()
    NSBezierPath(roundedRect: rect, xRadius: radius, yRadius: radius).fill()
}

func roundedStroke(_ rect: NSRect, radius: CGFloat, color: NSColor, width: CGFloat = 1) {
    color.setStroke()
    let path = NSBezierPath(roundedRect: rect, xRadius: radius, yRadius: radius)
    path.lineWidth = width
    path.stroke()
}

func makeLabel(
    _ text: String,
    size: CGFloat,
    weight: NSFont.Weight = .regular,
    color: NSColor = Palette.text,
    mono: Bool = false
) -> NSTextField {
    let label = NSTextField(labelWithString: text)
    label.font = mono ? NSFont.monospacedSystemFont(ofSize: size, weight: weight) : NSFont.systemFont(ofSize: size, weight: weight)
    label.textColor = color
    label.lineBreakMode = .byTruncatingTail
    label.translatesAutoresizingMaskIntoConstraints = false
    return label
}

final class ClosureButton: NSButton {
    private let actionHandler: () -> Void
    private let normalColor: NSColor
    private let primary: Bool
    private let fontSize: CGFloat

    init(
        title: String,
        symbol: String? = nil,
        primary: Bool = false,
        fontSize: CGFloat = 12,
        action: @escaping () -> Void
    ) {
        self.actionHandler = action
        self.primary = primary
        self.normalColor = primary ? Palette.yellow : Palette.panelRaised
        self.fontSize = fontSize
        super.init(frame: .zero)
        self.title = title
        self.isBordered = false
        self.bezelStyle = .regularSquare
        self.font = NSFont.systemFont(ofSize: fontSize, weight: .bold)
        self.target = self
        self.action = #selector(runAction)
        self.imagePosition = .imageLeading
        self.translatesAutoresizingMaskIntoConstraints = false
        self.wantsLayer = true
        self.layer?.backgroundColor = normalColor.cgColor
        self.layer?.borderColor = (primary ? Palette.yellow : Palette.stroke).cgColor
        self.layer?.borderWidth = primary ? 0 : 1
        self.layer?.cornerRadius = 8
        self.contentTintColor = primary ? NSColor.black : Palette.text
        self.alignment = .center
        self.lineBreakMode = .byTruncatingTail
        self.cell?.lineBreakMode = .byTruncatingTail
        self.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        self.setContentHuggingPriority(.defaultLow, for: .horizontal)
        updateAttributedTitle()

        _ = symbol
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override var title: String {
        didSet {
            updateAttributedTitle()
        }
    }

    private func updateAttributedTitle() {
        let paragraph = NSMutableParagraphStyle()
        paragraph.alignment = .center
        paragraph.lineBreakMode = .byTruncatingTail
        attributedTitle = NSAttributedString(
            string: title,
            attributes: [
                .font: NSFont.systemFont(ofSize: fontSize, weight: .bold),
                .foregroundColor: primary ? NSColor.black : Palette.text,
                .paragraphStyle: paragraph
            ]
        )
    }

    @objc private func runAction() {
        actionHandler()
    }
}

final class LogoView: NSView {
    override var intrinsicContentSize: NSSize { NSSize(width: 50, height: 50) }

    override func draw(_ dirtyRect: NSRect) {
        let rect = bounds.insetBy(dx: 2, dy: 2)
        roundedFill(rect, radius: 9, color: Palette.panelRaised)
        roundedStroke(rect, radius: 9, color: Palette.stroke)

        let orange = NSBezierPath()
        orange.move(to: NSPoint(x: rect.minX, y: rect.maxY))
        orange.line(to: NSPoint(x: rect.minX + rect.width * 0.64, y: rect.maxY))
        orange.line(to: NSPoint(x: rect.minX, y: rect.minY + rect.height * 0.39))
        orange.close()
        Palette.coral.setFill()
        orange.fill()

        let green = NSBezierPath()
        green.move(to: NSPoint(x: rect.minX, y: rect.minY))
        green.line(to: NSPoint(x: rect.minX + rect.width * 0.64, y: rect.minY))
        green.line(to: NSPoint(x: rect.minX, y: rect.minY + rect.height * 0.61))
        green.close()
        Palette.green.setFill()
        green.fill()

        let blue = NSBezierPath()
        blue.move(to: NSPoint(x: rect.maxX, y: rect.minY))
        blue.line(to: NSPoint(x: rect.maxX, y: rect.maxY))
        blue.line(to: NSPoint(x: rect.minX + rect.width * 0.64, y: rect.maxY))
        blue.line(to: NSPoint(x: rect.minX + rect.width * 0.30, y: rect.minY))
        blue.close()
        Palette.blue.setFill()
        blue.fill()
    }
}

final class ReadoutView: NSView {
    private let title: String
    var onClick: (() -> Void)?
    var value: String {
        didSet { needsDisplay = true }
    }

    init(title: String, value: String) {
        self.title = title
        self.value = value
        super.init(frame: .zero)
        translatesAutoresizingMaskIntoConstraints = false
        wantsLayer = true
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override var isFlipped: Bool { true }
    override var intrinsicContentSize: NSSize { NSSize(width: 88, height: 44) }

    override func draw(_ dirtyRect: NSRect) {
        let rect = bounds.insetBy(dx: 1, dy: 1)
        roundedFill(rect, radius: 8, color: onClick == nil ? Palette.panel : Palette.panelAlt)
        roundedStroke(rect, radius: 8, color: onClick == nil ? Palette.stroke : Palette.blue.withAlphaComponent(0.65))
        drawText(title.uppercased(), in: NSRect(x: rect.minX + 9, y: rect.minY + 6, width: rect.width - 18, height: 13), color: Palette.dim, size: 8, weight: .black)
        drawText(value, in: NSRect(x: rect.minX + 9, y: rect.minY + 20, width: rect.width - 18, height: 17), color: Palette.text, size: 13, weight: .black, alignment: .left)
    }

    override func mouseDown(with event: NSEvent) {
        onClick?()
    }
}

final class TitledPanel: NSView {
    let contentGuide = NSView()
    private let title: String
    private let accessory: String?

    init(title: String, accessory: String? = nil) {
        self.title = title
        self.accessory = accessory
        super.init(frame: .zero)
        translatesAutoresizingMaskIntoConstraints = false
        wantsLayer = true
        layer?.backgroundColor = Palette.panel.cgColor
        layer?.borderColor = Palette.stroke.cgColor
        layer?.borderWidth = 1
        layer?.cornerRadius = 8
        contentGuide.translatesAutoresizingMaskIntoConstraints = false
        addSubview(contentGuide)

        NSLayoutConstraint.activate([
            contentGuide.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 12),
            contentGuide.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -12),
            contentGuide.topAnchor.constraint(equalTo: topAnchor, constant: 44),
            contentGuide.bottomAnchor.constraint(equalTo: bottomAnchor, constant: -12)
        ])
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override var isFlipped: Bool { true }

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        drawText(title, in: NSRect(x: 14, y: 13, width: bounds.width - 120, height: 20), color: Palette.text, size: 14, weight: .black)
        if let accessory {
            drawText(accessory, in: NSRect(x: bounds.width - 102, y: 13, width: 88, height: 20), color: Palette.muted, size: 11, weight: .bold, alignment: .right)
        }
        Palette.subtleStroke.setStroke()
        let line = NSBezierPath()
        line.move(to: NSPoint(x: 0, y: 43.5))
        line.line(to: NSPoint(x: bounds.width, y: 43.5))
        line.lineWidth = 1
        line.stroke()
    }
}

final class BrowserProjectsView: NSView {
    var projects: [LocalProject] = [] {
        didSet { needsDisplay = true }
    }
    var selectedId: String? {
        didSet { needsDisplay = true }
    }
    var onProjectSelected: ((LocalProject) -> Void)?

    private let rowHeight: CGFloat = 72
    private let sections: [(String, [String])] = [
        ("Current Project", ["Patterns", "Playlist clips", "Mixer states", "Automation clips", "Recipe checklist", "Project file"]),
        ("Packs", ["Drums", "Impacts", "Risers", "Vocal chops", "Noise sweeps", "Breaths", "Sirens", "Crowd", "Ear candy"]),
        ("Generators", ["Sampler", "Sub Synth", "Supersaw", "Square Lead", "Granular Bass", "Rave Generator", "Analog Bass"]),
        ("Effects", ["Low Cut EQ", "Compressor", "Delay", "Reverb", "Stereo Spread", "Sidechain", "Wave Shaper", "Transit Macro"])
    ]

    override var isFlipped: Bool { true }
    override var intrinsicContentSize: NSSize {
        let sectionRows = sections.reduce(0) { $0 + 28 + $1.1.count * 24 }
        return NSSize(width: 260, height: max(420, CGFloat(projects.count) * rowHeight + CGFloat(sectionRows) + 76))
    }

    override func draw(_ dirtyRect: NSRect) {
        Palette.panel.setFill()
        dirtyRect.fill()

        let search = NSRect(x: 0, y: 0, width: bounds.width, height: 38)
        roundedFill(search, radius: 8, color: NSColor(calibratedRed: 0.07, green: 0.08, blue: 0.09, alpha: 1))
        roundedStroke(search, radius: 8, color: Palette.stroke)
        drawText("Search projects, stems, samples", in: search.insetBy(dx: 34, dy: 11), color: Palette.dim, size: 12, weight: .semibold)
        drawSearchIcon(in: NSRect(x: 12, y: 10, width: 18, height: 18))

        for (index, project) in projects.enumerated() {
            let y = 52 + CGFloat(index) * rowHeight
            let rect = NSRect(x: 0, y: y, width: bounds.width, height: rowHeight - 10)
            let selected = project.id == selectedId
            roundedFill(rect, radius: 8, color: selected ? NSColor(calibratedRed: 0.14, green: 0.20, blue: 0.25, alpha: 1) : Palette.panelAlt)
            roundedStroke(rect, radius: 8, color: selected ? Palette.blue : Palette.subtleStroke, width: selected ? 1.5 : 1)
            drawText(project.name, in: NSRect(x: 14, y: y + 12, width: bounds.width - 28, height: 18), color: Palette.text, size: 13, weight: .black)
            let detail = "\(Int(project.snapshot.bpm)) BPM  \(project.snapshot.tracks.count) tracks  \(project.snapshot.recipe?.count ?? 0) items"
            drawText(detail, in: NSRect(x: 14, y: y + 34, width: bounds.width - 28, height: 16), color: Palette.muted, size: 11, weight: .semibold)
        }

        var y = 60 + CGFloat(projects.count) * rowHeight
        for section in sections {
            drawText(section.0, in: NSRect(x: 2, y: y, width: bounds.width - 4, height: 16), color: Palette.muted, size: 11, weight: .black)
            y += 22
            for item in section.1 {
                roundedFill(NSRect(x: 0, y: y, width: bounds.width, height: 20), radius: 5, color: Palette.panel)
                drawText(item, in: NSRect(x: 18, y: y + 3, width: bounds.width - 28, height: 14), color: Palette.dim, size: 10, weight: .bold)
                Palette.dim.setStroke()
                let icon = NSBezierPath()
                icon.move(to: NSPoint(x: 5, y: y + 10))
                icon.line(to: NSPoint(x: 12, y: y + 10))
                icon.lineWidth = 1
                icon.stroke()
                y += 24
            }
            y += 8
        }
    }

    override func mouseDown(with event: NSEvent) {
        let point = convert(event.locationInWindow, from: nil)
        let primary = project(atVisualY: point.y)
        let mirrored = project(atVisualY: bounds.height - point.y)

        if let mirrored, mirrored.id != selectedId, primary?.id == selectedId {
            onProjectSelected?(mirrored)
            return
        }

        if let project = primary ?? mirrored {
            onProjectSelected?(project)
        }
    }

    private func project(atVisualY y: CGFloat) -> LocalProject? {
        let index = Int((y - 52) / rowHeight)
        guard index >= 0, index < projects.count else { return nil }
        let rowMin = 52 + CGFloat(index) * rowHeight
        let rowMax = rowMin + rowHeight - 10
        guard y >= rowMin, y <= rowMax else { return nil }
        return projects[index]
    }

    private func drawSearchIcon(in rect: NSRect) {
        Palette.dim.setStroke()
        let glass = NSBezierPath(ovalIn: NSRect(x: rect.minX, y: rect.minY, width: 11, height: 11))
        glass.lineWidth = 1.7
        glass.stroke()

        let handle = NSBezierPath()
        handle.move(to: NSPoint(x: rect.minX + 10, y: rect.minY + 10))
        handle.line(to: NSPoint(x: rect.maxX, y: rect.maxY))
        handle.lineWidth = 1.7
        handle.stroke()
    }
}

final class ProjectBrowserWindowController: NSWindowController, NSTableViewDataSource, NSTableViewDelegate, NSSearchFieldDelegate {
    var onOpenProject: ((LocalProject) -> Void)?
    var onCreateProject: (() -> Void)?
    var onImportProject: (() -> Void)?
    var onDeleteProject: ((LocalProject) -> Void)?
    var onRevealProject: ((LocalProject) -> Void)?

    private let searchField = NSSearchField()
    private let tableView = NSTableView()
    private var allProjects: [LocalProject] = []
    private var filteredProjects: [LocalProject] = []
    private var selectedProjectId: String?

    init() {
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 760, height: 520),
            styleMask: [.titled, .closable, .miniaturizable],
            backing: .buffered,
            defer: false
        )
        window.title = "Projects"
        window.isReleasedWhenClosed = false
        super.init(window: window)
        window.contentView = makeContentView()
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    func setProjects(_ projects: [LocalProject], selectedId: String?) {
        allProjects = projects
        selectedProjectId = selectedId
        applyFilter()
    }

    func present() {
        showWindow(nil)
        window?.center()
        window?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func numberOfRows(in tableView: NSTableView) -> Int {
        filteredProjects.count
    }

    func tableView(_ tableView: NSTableView, heightOfRow row: Int) -> CGFloat {
        58
    }

    func tableView(_ tableView: NSTableView, viewFor tableColumn: NSTableColumn?, row: Int) -> NSView? {
        let identifier = NSUserInterfaceItemIdentifier("ProjectCell")
        let cell = tableView.makeView(withIdentifier: identifier, owner: self) as? NSTableCellView ?? makeProjectCell(identifier: identifier)
        let project = filteredProjects[row]
        let primary = cell.viewWithTag(1) as? NSTextField
        let secondary = cell.viewWithTag(2) as? NSTextField
        primary?.stringValue = project.name
        secondary?.stringValue = "\(Int(project.snapshot.bpm)) BPM  ·  \(project.snapshot.tracks.count) tracks  ·  \(project.snapshot.recipe?.count ?? 0) recipe items"
        return cell
    }

    func tableViewSelectionDidChange(_ notification: Notification) {
        let row = tableView.selectedRow
        selectedProjectId = row >= 0 && row < filteredProjects.count ? filteredProjects[row].id : nil
    }

    func controlTextDidChange(_ obj: Notification) {
        applyFilter()
    }

    @objc private func openSelection() {
        guard let project = selectedProject else { return }
        onOpenProject?(project)
        window?.orderOut(nil)
    }

    @objc private func createProject() {
        onCreateProject?()
        applyFilter()
    }

    @objc private func importProject() {
        onImportProject?()
        applyFilter()
    }

    @objc private func deleteSelection() {
        guard let project = selectedProject else { return }
        onDeleteProject?(project)
    }

    @objc private func revealSelection() {
        guard let project = selectedProject else { return }
        onRevealProject?(project)
    }

    @objc private func rowDoubleClicked() {
        openSelection()
    }

    private var selectedProject: LocalProject? {
        guard let selectedProjectId else { return nil }
        return filteredProjects.first(where: { $0.id == selectedProjectId })
    }

    private func applyFilter() {
        let query = searchField.stringValue.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if query.isEmpty {
            filteredProjects = allProjects
        } else {
            filteredProjects = allProjects.filter { project in
                let haystack = [
                    project.name,
                    project.description ?? "",
                    project.keyCenter ?? "",
                    project.snapshot.tracks.map(\.name).joined(separator: " ")
                ].joined(separator: " ").lowercased()
                return haystack.contains(query)
            }
        }
        tableView.reloadData()
        if let selectedProjectId,
           let index = filteredProjects.firstIndex(where: { $0.id == selectedProjectId }) {
            tableView.selectRowIndexes(IndexSet(integer: index), byExtendingSelection: false)
        } else if !filteredProjects.isEmpty {
            tableView.selectRowIndexes(IndexSet(integer: 0), byExtendingSelection: false)
            self.selectedProjectId = filteredProjects[0].id
        }
    }

    private func makeContentView() -> NSView {
        let root = NSView()
        root.translatesAutoresizingMaskIntoConstraints = false
        root.wantsLayer = true
        root.layer?.backgroundColor = Palette.app.cgColor

        searchField.placeholderString = "Search projects, stems, tracks"
        searchField.delegate = self
        searchField.translatesAutoresizingMaskIntoConstraints = false

        let column = NSTableColumn(identifier: NSUserInterfaceItemIdentifier("project"))
        column.width = 680
        tableView.addTableColumn(column)
        tableView.headerView = nil
        tableView.rowSizeStyle = .custom
        tableView.delegate = self
        tableView.dataSource = self
        tableView.target = self
        tableView.doubleAction = #selector(rowDoubleClicked)
        tableView.backgroundColor = Palette.panel
        tableView.selectionHighlightStyle = .regular

        let scroll = NSScrollView()
        scroll.drawsBackground = false
        scroll.documentView = tableView
        scroll.hasVerticalScroller = true
        scroll.translatesAutoresizingMaskIntoConstraints = false

        let open = ClosureButton(title: "Open", symbol: "arrow.right.circle") { [weak self] in self?.openSelection() }
        let create = ClosureButton(title: "New", symbol: "plus") { [weak self] in self?.createProject() }
        let `import` = ClosureButton(title: "Import", symbol: "folder.badge.plus") { [weak self] in self?.importProject() }
        let reveal = ClosureButton(title: "Reveal", symbol: "doc.text.magnifyingglass") { [weak self] in self?.revealSelection() }
        let delete = ClosureButton(title: "Delete", symbol: "trash") { [weak self] in self?.deleteSelection() }
        [open, create, `import`, reveal, delete].forEach {
            $0.heightAnchor.constraint(equalToConstant: 32).isActive = true
            $0.widthAnchor.constraint(greaterThanOrEqualToConstant: 84).isActive = true
        }
        let actions = NSStackView(views: [open, create, `import`, reveal, delete])
        actions.orientation = .horizontal
        actions.alignment = .centerY
        actions.spacing = 8
        actions.translatesAutoresizingMaskIntoConstraints = false

        root.addSubview(searchField)
        root.addSubview(scroll)
        root.addSubview(actions)
        NSLayoutConstraint.activate([
            searchField.leadingAnchor.constraint(equalTo: root.leadingAnchor, constant: 18),
            searchField.trailingAnchor.constraint(equalTo: root.trailingAnchor, constant: -18),
            searchField.topAnchor.constraint(equalTo: root.topAnchor, constant: 18),

            scroll.leadingAnchor.constraint(equalTo: root.leadingAnchor, constant: 18),
            scroll.trailingAnchor.constraint(equalTo: root.trailingAnchor, constant: -18),
            scroll.topAnchor.constraint(equalTo: searchField.bottomAnchor, constant: 14),
            scroll.bottomAnchor.constraint(equalTo: actions.topAnchor, constant: -14),

            actions.leadingAnchor.constraint(equalTo: root.leadingAnchor, constant: 18),
            actions.trailingAnchor.constraint(lessThanOrEqualTo: root.trailingAnchor, constant: -18),
            actions.bottomAnchor.constraint(equalTo: root.bottomAnchor, constant: -18)
        ])
        return root
    }

    private func makeProjectCell(identifier: NSUserInterfaceItemIdentifier) -> NSTableCellView {
        let cell = NSTableCellView()
        cell.identifier = identifier

        let primary = NSTextField(labelWithString: "")
        primary.tag = 1
        primary.font = NSFont.systemFont(ofSize: 14, weight: .black)
        primary.textColor = Palette.text
        primary.translatesAutoresizingMaskIntoConstraints = false

        let secondary = NSTextField(labelWithString: "")
        secondary.tag = 2
        secondary.font = NSFont.systemFont(ofSize: 11, weight: .bold)
        secondary.textColor = Palette.muted
        secondary.translatesAutoresizingMaskIntoConstraints = false

        cell.addSubview(primary)
        cell.addSubview(secondary)
        NSLayoutConstraint.activate([
            primary.leadingAnchor.constraint(equalTo: cell.leadingAnchor, constant: 12),
            primary.trailingAnchor.constraint(equalTo: cell.trailingAnchor, constant: -12),
            primary.topAnchor.constraint(equalTo: cell.topAnchor, constant: 9),
            secondary.leadingAnchor.constraint(equalTo: cell.leadingAnchor, constant: 12),
            secondary.trailingAnchor.constraint(equalTo: cell.trailingAnchor, constant: -12),
            secondary.topAnchor.constraint(equalTo: primary.bottomAnchor, constant: 4)
        ])
        return cell
    }
}

final class ChannelRackView: NSView {
    var tracks: [Track] = [] {
        didSet {
            invalidateIntrinsicContentSize()
            needsDisplay = true
        }
    }
    var selectedTrackId: String? {
        didSet { needsDisplay = true }
    }
    var activeStep: Int = -1 {
        didSet { needsDisplay = true }
    }
    var onTrackSelected: ((String) -> Void)?
    var onStepToggle: ((String, Int) -> Void)?

    private let rowHeight: CGFloat = 34
    private let nameWidth: CGFloat = 118
    private let stepSize: CGFloat = 20
    private let stepGap: CGFloat = 7

    override var isFlipped: Bool { true }
    override var intrinsicContentSize: NSSize {
        NSSize(width: 520, height: max(210, 34 + CGFloat(tracks.count) * rowHeight))
    }

    override func draw(_ dirtyRect: NSRect) {
        NSColor(calibratedRed: 0.075, green: 0.083, blue: 0.095, alpha: 1).setFill()
        dirtyRect.fill()
        drawText("16-step rack", in: NSRect(x: 0, y: 0, width: 120, height: 20), color: Palette.muted, size: 11, weight: .bold)

        for step in 0..<16 {
            let x = nameWidth + CGFloat(step) * (stepSize + stepGap)
            drawText("\(step + 1)", in: NSRect(x: x, y: 6, width: stepSize, height: 16), color: Palette.dim, size: 9, weight: .bold, alignment: .center)
        }

        for (index, track) in tracks.enumerated() {
            let y = 30 + CGFloat(index) * rowHeight
            let rowRect = NSRect(x: 0, y: y, width: bounds.width, height: rowHeight - 4)
            let selected = track.id == selectedTrackId
            roundedFill(rowRect, radius: 6, color: selected ? NSColor(calibratedRed: 0.16, green: 0.20, blue: 0.23, alpha: 1) : (index.isMultiple(of: 2) ? Palette.panel : Palette.panelAlt))
            if selected {
                roundedStroke(rowRect, radius: 6, color: Palette.blue, width: 1.4)
            }
            let trackColor = color(from: track.color, fallback: Palette.blue)
            roundedFill(NSRect(x: 10, y: y + 10, width: 9, height: 9), radius: 2, color: trackColor)
            drawText(track.name, in: NSRect(x: 26, y: y + 7, width: nameWidth - 30, height: 16), color: Palette.text, size: 11, weight: .bold)

            let activeSteps = Set((track.steps ?? []).map { (($0 % 16) + 16) % 16 })
            for step in 0..<16 {
                let x = nameWidth + CGFloat(step) * (stepSize + stepGap)
                let rect = NSRect(x: x, y: y + 7, width: stepSize, height: 18)
                let active = activeSteps.contains(step)
                roundedFill(rect, radius: 4, color: active ? trackColor : NSColor(calibratedRed: 0.155, green: 0.165, blue: 0.18, alpha: 1))
                if active {
                    roundedStroke(rect.insetBy(dx: 0.5, dy: 0.5), radius: 4, color: NSColor.white.withAlphaComponent(0.18))
                }
                if step == activeStep {
                    roundedStroke(rect.insetBy(dx: -1.5, dy: -1.5), radius: 5, color: Palette.text, width: 1.3)
                }
            }
        }
    }

    override func mouseDown(with event: NSEvent) {
        let point = convert(event.locationInWindow, from: nil)
        let row = Int((point.y - 30) / rowHeight)
        guard row >= 0, row < tracks.count else { return }
        let track = tracks[row]
        onTrackSelected?(track.id)

        if point.x >= nameWidth {
            let relative = point.x - nameWidth
            let step = Int(relative / (stepSize + stepGap))
            let stepX = nameWidth + CGFloat(step) * (stepSize + stepGap)
            if step >= 0, step < 16, point.x >= stepX, point.x <= stepX + stepSize {
                onStepToggle?(track.id, step)
            }
        }
    }
}

final class PlaylistView: NSView {
    var tracks: [Track] = [] {
        didSet {
            totalBars = max(64, ceil(maxClipEnd()) + 8)
            invalidateIntrinsicContentSize()
            needsDisplay = true
        }
    }
    var controls: [String: MixerControl] = [:] {
        didSet { needsDisplay = true }
    }
    var notes: [PianoNote] = [] {
        didSet { needsDisplay = true }
    }
    var recipe: [RecipeItem] = [] {
        didSet { needsDisplay = true }
    }
    var snap: String = "1/4" {
        didSet { needsDisplay = true }
    }
    var loopEnabled: Bool = false {
        didSet { needsDisplay = true }
    }
    var loopStartBar: Double = 0 {
        didSet { needsDisplay = true }
    }
    var loopEndBar: Double = 16 {
        didSet { needsDisplay = true }
    }
    var activeTool: ToolId = .select
    var workView: WorkView = .playlist {
        didSet {
            invalidateIntrinsicContentSize()
            needsDisplay = true
        }
    }
    var selectedTrackId: String? {
        didSet { needsDisplay = true }
    }
    var selectedClipId: String? {
        didSet { needsDisplay = true }
    }
    var selectedTrack: Track? {
        tracks.first { $0.id == selectedTrackId } ?? tracks.first
    }
    var onTrackSelected: ((String) -> Void)?
    var onClipSelected: ((String, String) -> Void)?
    var onPianoNoteAdded: ((PianoNote) -> Void)?
    var onPianoNoteDeleted: (() -> Void)?
    var onEffectToggle: ((String, String) -> Void)?
    var onEffectAmount: ((String, String, Double) -> Void)?
    var onSampleNormalize: (() -> Void)?
    var onSampleReverse: (() -> Void)?

    private var totalBars: Double = 72
    private let leftWidth: CGFloat = 142
    private let rulerHeight: CGFloat = 34
    private let rowHeight: CGFloat = 50
    var pixelsPerBar: CGFloat = 38 {
        didSet {
            invalidateIntrinsicContentSize()
            needsDisplay = true
        }
    }

    override var isFlipped: Bool { true }
    override var intrinsicContentSize: NSSize {
        switch workView {
        case .playlist:
            return NSSize(
                width: max(1280, leftWidth + CGFloat(totalBars) * pixelsPerBar + 24),
                height: max(470, rulerHeight + CGFloat(max(tracks.count, 8)) * rowHeight + 26)
            )
        case .mixer:
            return NSSize(width: max(1040, CGFloat(tracks.count) * 118 + 24), height: 560)
        case .recipe:
            return NSSize(width: 1120, height: max(620, CGFloat(recipe.count) * 48 + 120))
        default:
            return NSSize(width: 1120, height: 560)
        }
    }

    private func maxClipEnd() -> Double {
        tracks
            .flatMap { $0.clips ?? [] }
            .map { ($0.startBar ?? 0) + ($0.bars ?? 0) }
            .max() ?? 64
    }

    override func draw(_ dirtyRect: NSRect) {
        NSColor(calibratedRed: 0.065, green: 0.073, blue: 0.083, alpha: 1).setFill()
        dirtyRect.fill()

        switch workView {
        case .playlist:
            drawPlaylist()
        case .piano:
            drawPianoRoll()
        case .mixer:
            drawMixerDetail()
        case .plugins:
            drawPluginEditor()
        case .sample:
            drawSampleEditor()
        case .recipe:
            drawRecipeCoverage()
        }
    }

    private func drawPlaylist() {
        roundedFill(NSRect(x: 0, y: 0, width: leftWidth, height: bounds.height), radius: 0, color: Palette.panel)
        roundedFill(NSRect(x: leftWidth, y: 0, width: bounds.width - leftWidth, height: rulerHeight), radius: 0, color: Palette.panelAlt)

        for bar in 0...Int(totalBars) {
            let x = leftWidth + CGFloat(bar) * pixelsPerBar
            let path = NSBezierPath()
            path.move(to: NSPoint(x: x, y: 0))
            path.line(to: NSPoint(x: x, y: bounds.height))
            let isMajor = bar % 4 == 0
            (isMajor ? Palette.stroke : Palette.subtleStroke).setStroke()
            path.lineWidth = isMajor ? 1 : 0.6
            path.stroke()

            if isMajor && bar < Int(totalBars) {
                drawText("\(bar + 1)", in: NSRect(x: x + 6, y: 9, width: 42, height: 16), color: Palette.muted, size: 10, weight: .black)
            }
        }

        let sectionNames = ["Intro", "Pre", "Drop 1", "Break", "Build", "Drop 2", "Outro"]
        for (index, name) in sectionNames.enumerated() {
            let start = leftWidth + CGFloat(index * 8) * pixelsPerBar
            let rect = NSRect(x: start, y: 0, width: 8 * pixelsPerBar, height: 4)
            let tint: NSColor = index.isMultiple(of: 2) ? Palette.blue.withAlphaComponent(0.55) : Palette.yellow.withAlphaComponent(0.65)
            tint.setFill()
            rect.fill()
            drawText(name, in: NSRect(x: start + 8, y: 17, width: 70, height: 14), color: Palette.dim, size: 9, weight: .bold)
        }

        if loopEnabled {
            let startX = leftWidth + CGFloat(loopStartBar) * pixelsPerBar
            let endX = leftWidth + CGFloat(max(loopStartBar + 1, loopEndBar)) * pixelsPerBar
            let rect = NSRect(x: startX, y: rulerHeight, width: max(8, endX - startX), height: bounds.height - rulerHeight)
            Palette.yellow.withAlphaComponent(0.08).setFill()
            rect.fill()
            Palette.yellow.withAlphaComponent(0.75).setStroke()
            let loop = NSBezierPath(rect: rect)
            loop.lineWidth = 1.2
            loop.stroke()
        }

        for (index, track) in tracks.enumerated() {
            let y = rulerHeight + CGFloat(index) * rowHeight
            let rowRect = NSRect(x: 0, y: y, width: bounds.width, height: rowHeight)
            (index.isMultiple(of: 2)
             ? NSColor(calibratedRed: 0.078, green: 0.087, blue: 0.098, alpha: 1)
             : NSColor(calibratedRed: 0.092, green: 0.101, blue: 0.113, alpha: 1)).setFill()
            rowRect.fill()

            Palette.subtleStroke.setStroke()
            let line = NSBezierPath()
            line.move(to: NSPoint(x: 0, y: y))
            line.line(to: NSPoint(x: bounds.width, y: y))
            line.lineWidth = 1
            line.stroke()

            drawText(track.name, in: NSRect(x: 14, y: y + 10, width: leftWidth - 38, height: 16), color: Palette.text, size: 11, weight: .black)
            let meta = track.instrument ?? track.kind ?? "Track"
            drawText(meta, in: NSRect(x: 14, y: y + 27, width: leftWidth - 38, height: 14), color: Palette.dim, size: 9, weight: .semibold)
            roundedFill(NSRect(x: leftWidth - 20, y: y + 20, width: 8, height: 8), radius: 2, color: color(from: track.color))
            if track.id == selectedTrackId {
                roundedStroke(NSRect(x: 8, y: y + 7, width: leftWidth - 16, height: rowHeight - 14), radius: 6, color: Palette.blue, width: 1.4)
            }

            for clip in track.clips ?? [] {
                let start = clip.startBar ?? 0
                let bars = clip.bars ?? 1
                let clipX = leftWidth + CGFloat(start) * pixelsPerBar + 5
                let clipWidth = max(34, CGFloat(bars) * pixelsPerBar - 10)
                let clipRect = NSRect(x: clipX, y: y + 7, width: clipWidth, height: rowHeight - 14)
                let clipColor = color(from: clip.color ?? track.color, fallback: Palette.blue)
                roundedFill(clipRect, radius: 5, color: clipColor.withAlphaComponent(0.86))
                roundedStroke(clipRect, radius: 5, color: clip.id == selectedClipId ? Palette.text : NSColor.white.withAlphaComponent(0.18), width: clip.id == selectedClipId ? 2 : 1)

                let textColor: NSColor = clipColor.brightnessComponent > 0.58 ? NSColor(calibratedWhite: 0.06, alpha: 1) : NSColor.white
                drawText(clip.name, in: clipRect.insetBy(dx: 9, dy: 6), color: textColor, size: 10, weight: .black)

                if (clip.type ?? "audio") == "audio" {
                    drawWaveform(in: clipRect.insetBy(dx: 8, dy: 22), color: textColor.withAlphaComponent(0.35), seed: clip.id.hashValue)
                } else {
                    drawPatternDots(in: clipRect.insetBy(dx: 8, dy: 22), color: textColor.withAlphaComponent(0.38))
                }
            }
        }
    }

    private func drawPianoRoll() {
        let header = NSRect(x: 0, y: 0, width: bounds.width, height: 44)
        roundedFill(header, radius: 0, color: Palette.panelAlt)
        let trackName = selectedTrack?.name ?? "No track"
        drawText("Piano Roll", in: NSRect(x: 18, y: 13, width: 120, height: 18), color: Palette.text, size: 14, weight: .black)
        drawText(trackName, in: NSRect(x: 132, y: 14, width: 240, height: 16), color: Palette.muted, size: 11, weight: .bold)
        let instruction = activeTool == .erase ? "Click grid to erase last note" : "Click grid to add notes"
        drawText(instruction, in: NSRect(x: bounds.width - 220, y: 14, width: 200, height: 16), color: Palette.dim, size: 11, weight: .bold, alignment: .right)

        let left: CGFloat = 60
        let top: CGFloat = 58
        let rowHeight: CGFloat = 13
        let beatWidth: CGFloat = 28
        let highNote = 91
        let lowNote = 54
        let rows = highNote - lowNote + 1
        for row in 0..<rows {
            let note = highNote - row
            let y = top + CGFloat(row) * rowHeight
            let sharp = [1, 3, 6, 8, 10].contains(note % 12)
            (sharp ? NSColor(calibratedRed: 0.10, green: 0.11, blue: 0.125, alpha: 1) : NSColor(calibratedRed: 0.075, green: 0.083, blue: 0.095, alpha: 1)).setFill()
            NSRect(x: left, y: y, width: bounds.width - left, height: rowHeight).fill()
            if note % 12 == 0 {
                drawText("C\(note / 12 - 1)", in: NSRect(x: 12, y: y, width: 38, height: rowHeight), color: Palette.muted, size: 9, weight: .bold, alignment: .right)
            }
        }
        for beat in 0...64 {
            let x = left + CGFloat(beat) * beatWidth
            let line = NSBezierPath()
            line.move(to: NSPoint(x: x, y: top))
            line.line(to: NSPoint(x: x, y: top + CGFloat(rows) * rowHeight))
            (beat % 4 == 0 ? Palette.stroke : Palette.subtleStroke).setStroke()
            line.lineWidth = beat % 4 == 0 ? 1 : 0.5
            line.stroke()
        }
        for note in notes {
            let y = top + CGFloat(highNote - note.note) * rowHeight
            guard y >= top, y <= top + CGFloat(rows) * rowHeight else { continue }
            let x = left + CGFloat(note.beat) * beatWidth
            let rect = NSRect(x: x, y: y + 2, width: max(14, CGFloat(note.duration) * beatWidth - 3), height: rowHeight - 4)
            roundedFill(rect, radius: 4, color: color(from: note.color, fallback: Palette.blue))
            roundedStroke(rect, radius: 4, color: NSColor.white.withAlphaComponent(0.28))
        }
    }

    private func drawMixerDetail() {
        drawText("Mixer", in: NSRect(x: 18, y: 14, width: 130, height: 22), color: Palette.text, size: 18, weight: .black)
        drawText("Mute, solo, arm, sends, gain, and pan are saved in the project file.", in: NSRect(x: 150, y: 19, width: 540, height: 16), color: Palette.muted, size: 11, weight: .bold)
        for (index, track) in tracks.enumerated() {
            let x = 18 + CGFloat(index) * 118
            let strip = NSRect(x: x, y: 58, width: 104, height: 440)
            let selected = track.id == selectedTrackId
            roundedFill(strip, radius: 8, color: selected ? NSColor(calibratedRed: 0.15, green: 0.18, blue: 0.205, alpha: 1) : Palette.panel)
            roundedStroke(strip, radius: 8, color: selected ? Palette.blue : Palette.stroke, width: selected ? 1.5 : 1)
            drawText(String(format: "%02d", index + 1), in: NSRect(x: x + 10, y: 72, width: 84, height: 14), color: Palette.dim, size: 9, weight: .bold, alignment: .center)
            drawText(track.name, in: NSRect(x: x + 10, y: 92, width: 84, height: 38), color: Palette.text, size: 11, weight: .black, alignment: .center, lineBreak: .byWordWrapping)
            let control = controls[track.id] ?? MixerControl(gain: track.gain ?? 0.82, pan: track.pan ?? 0, mute: false, solo: false, arm: false, sendA: 0.15, sendB: 0.08)
            let toggles = [("M", control.mute), ("S", control.solo), ("R", control.arm), ("A", control.sendA > 0.4), ("B", control.sendB > 0.4), ("FX", track.effects?.contains { $0.active == true } == true)]
            for (toggleIndex, item) in toggles.enumerated() {
                let tx = x + 10 + CGFloat(toggleIndex % 3) * 29
                let ty = 144 + CGFloat(toggleIndex / 3) * 30
                roundedFill(NSRect(x: tx, y: ty, width: 24, height: 22), radius: 4, color: item.1 ? color(from: track.color, fallback: Palette.yellow) : Palette.panelRaised)
                drawText(item.0, in: NSRect(x: tx, y: ty + 5, width: 24, height: 12), color: item.1 ? NSColor.black : Palette.muted, size: 9, weight: .black, alignment: .center)
            }
            let meter = NSRect(x: x + 18, y: 226, width: 16, height: 180)
            roundedFill(meter, radius: 4, color: NSColor(calibratedRed: 0.06, green: 0.07, blue: 0.08, alpha: 1))
            let gain = CGFloat(max(0.0, min(control.gain, 1.4))) / 1.4
            roundedFill(NSRect(x: meter.minX, y: meter.maxY - meter.height * gain, width: meter.width, height: meter.height * gain), radius: 4, color: color(from: track.color, fallback: Palette.green))
            let fader = NSRect(x: x + 58, y: 226, width: 7, height: 180)
            roundedFill(fader, radius: 3, color: NSColor(calibratedRed: 0.06, green: 0.07, blue: 0.08, alpha: 1))
            roundedFill(NSRect(x: x + 48, y: fader.maxY - fader.height * gain - 5, width: 27, height: 10), radius: 4, color: Palette.text)
            drawText(String(format: "%.2f", control.gain), in: NSRect(x: x + 10, y: 416, width: 84, height: 14), color: Palette.muted, size: 10, weight: .bold, alignment: .center)
            drawText(control.pan == 0 ? "C" : String(format: "%+.2f", control.pan), in: NSRect(x: x + 10, y: 442, width: 84, height: 14), color: Palette.muted, size: 10, weight: .bold, alignment: .center)
        }
    }

    private func drawPluginEditor() {
        guard let track = selectedTrack else {
            drawText("No track selected", in: bounds.insetBy(dx: 18, dy: 18), color: Palette.muted, size: 14, weight: .bold)
            return
        }
        drawText("Plugins", in: NSRect(x: 18, y: 16, width: 120, height: 22), color: Palette.text, size: 18, weight: .black)
        drawText("\(track.name)  /  \(track.instrument ?? "Instrument")", in: NSRect(x: 138, y: 20, width: 420, height: 16), color: Palette.muted, size: 11, weight: .bold)
        let effects = track.effects ?? []
        for (index, effect) in effects.enumerated() {
            let col = index % 2
            let row = index / 2
            let rect = NSRect(x: 18 + CGFloat(col) * 360, y: 62 + CGFloat(row) * 82, width: 338, height: 66)
            roundedFill(rect, radius: 8, color: Palette.panel)
            roundedStroke(rect, radius: 8, color: effect.active == true ? Palette.green : Palette.stroke)
            roundedFill(NSRect(x: rect.minX + 12, y: rect.minY + 16, width: 12, height: 12), radius: 6, color: effect.active == true ? Palette.green : Palette.dim)
            drawText(effect.name, in: NSRect(x: rect.minX + 34, y: rect.minY + 12, width: rect.width - 48, height: 16), color: Palette.text, size: 12, weight: .black)
            let amount = CGFloat(effect.amount ?? 0.35)
            roundedFill(NSRect(x: rect.minX + 34, y: rect.minY + 42, width: rect.width - 56, height: 6), radius: 3, color: Palette.panelRaised)
            roundedFill(NSRect(x: rect.minX + 34, y: rect.minY + 42, width: (rect.width - 56) * amount, height: 6), radius: 3, color: color(from: track.color, fallback: Palette.blue))
        }
        drawText("Click the left side of a card to toggle it. Click the meter area to set amount. Changes round-trip through .neon.json.", in: NSRect(x: 18, y: bounds.height - 38, width: bounds.width - 36, height: 16), color: Palette.dim, size: 11, weight: .bold)
    }

    private func drawSampleEditor() {
        guard let track = selectedTrack else {
            drawText("No sample selected", in: bounds.insetBy(dx: 18, dy: 18), color: Palette.muted, size: 14, weight: .bold)
            return
        }
        drawText("Sample", in: NSRect(x: 18, y: 16, width: 120, height: 22), color: Palette.text, size: 18, weight: .black)
        drawText(track.name, in: NSRect(x: 128, y: 20, width: 360, height: 16), color: Palette.muted, size: 11, weight: .bold)
        let normalize = NSRect(x: bounds.width - 216, y: 12, width: 92, height: 26)
        let reverse = NSRect(x: bounds.width - 112, y: 12, width: 92, height: 26)
        roundedFill(normalize, radius: 6, color: Palette.panelRaised)
        roundedStroke(normalize, radius: 6, color: Palette.stroke)
        drawText("Normalize", in: normalize.insetBy(dx: 8, dy: 6), color: Palette.text, size: 10, weight: .black, alignment: .center)
        roundedFill(reverse, radius: 6, color: Palette.panelRaised)
        roundedStroke(reverse, radius: 6, color: Palette.stroke)
        drawText("Reverse", in: reverse.insetBy(dx: 8, dy: 6), color: Palette.text, size: 10, weight: .black, alignment: .center)
        let waveRect = NSRect(x: 18, y: 60, width: bounds.width - 36, height: 260)
        roundedFill(waveRect, radius: 8, color: Palette.panel)
        drawWaveform(in: waveRect.insetBy(dx: 16, dy: 32), color: color(from: track.color, fallback: Palette.blue), seed: track.id.hashValue)
        let controls = ["In", "Out", "Pitch", "Stretch"]
        for (index, label) in controls.enumerated() {
            let rect = NSRect(x: 18 + CGFloat(index) * ((bounds.width - 54) / 4), y: 344, width: (bounds.width - 72) / 4, height: 64)
            roundedFill(rect, radius: 8, color: Palette.panel)
            drawText(label, in: NSRect(x: rect.minX + 12, y: rect.minY + 12, width: 80, height: 16), color: Palette.text, size: 12, weight: .black)
            roundedFill(NSRect(x: rect.minX + 12, y: rect.minY + 42, width: rect.width - 24, height: 6), radius: 3, color: Palette.panelRaised)
            roundedFill(NSRect(x: rect.minX + 12, y: rect.minY + 42, width: (rect.width - 24) * (index < 2 ? (index == 0 ? 0.1 : 0.92) : 0.5), height: 6), radius: 3, color: Palette.yellow)
        }
    }

    private func drawRecipeCoverage() {
        drawText("Production Recipe Coverage", in: NSRect(x: 18, y: 16, width: 320, height: 24), color: Palette.text, size: 18, weight: .black)
        let implemented = recipe.filter { $0.status == "implemented" }.count
        drawText("\(recipe.count)/\(recipe.count) mapped  /  \(implemented) implemented", in: NSRect(x: bounds.width - 300, y: 20, width: 280, height: 16), color: Palette.muted, size: 11, weight: .bold, alignment: .right)
        let sections = ["Foundation", "Intro", "Verse", "Build", "Drop", "Mix", "Advanced"]
        var y: CGFloat = 58
        for section in sections {
            let items = recipe.filter { $0.section == section }
            guard !items.isEmpty else { continue }
            drawText(section.uppercased(), in: NSRect(x: 18, y: y, width: 180, height: 16), color: Palette.yellow, size: 11, weight: .black)
            y += 22
            for item in items {
                let rect = NSRect(x: 18, y: y, width: bounds.width - 36, height: 40)
                roundedFill(rect, radius: 7, color: Palette.panel)
                roundedFill(NSRect(x: rect.minX + 12, y: rect.minY + 14, width: 10, height: 10), radius: 5, color: item.status == "implemented" ? Palette.green : Palette.yellow)
                drawText(item.label, in: NSRect(x: rect.minX + 32, y: rect.minY + 7, width: 300, height: 15), color: Palette.text, size: 11, weight: .black)
                drawText(item.detail ?? "", in: NSRect(x: rect.minX + 32, y: rect.minY + 23, width: rect.width - 240, height: 13), color: Palette.muted, size: 9, weight: .semibold)
                drawText((item.trackIds ?? []).prefix(3).joined(separator: "  "), in: NSRect(x: rect.maxX - 210, y: rect.minY + 13, width: 190, height: 14), color: Palette.dim, size: 9, weight: .bold, alignment: .right)
                y += 46
            }
            y += 8
        }
    }

    override func mouseDown(with event: NSEvent) {
        let point = convert(event.locationInWindow, from: nil)
        switch workView {
        case .playlist:
            handlePlaylistMouseDown(point)
        case .piano:
            handlePianoMouseDown(point)
        case .mixer:
            let index = Int((point.x - 18) / 118)
            if index >= 0, index < tracks.count {
                onTrackSelected?(tracks[index].id)
            }
        case .plugins:
            handlePluginMouseDown(point)
        case .sample:
            handleSampleMouseDown(point)
        default:
            break
        }
    }

    private func handlePlaylistMouseDown(_ point: NSPoint) {
        let row = Int((point.y - rulerHeight) / rowHeight)
        guard row >= 0, row < tracks.count else { return }
        let track = tracks[row]
        onTrackSelected?(track.id)
        let y = rulerHeight + CGFloat(row) * rowHeight
        for clip in track.clips ?? [] {
            let clipX = leftWidth + CGFloat(clip.startBar ?? 0) * pixelsPerBar + 5
            let clipWidth = max(34, CGFloat(clip.bars ?? 1) * pixelsPerBar - 10)
            let clipRect = NSRect(x: clipX, y: y + 7, width: clipWidth, height: rowHeight - 14)
            if clipRect.contains(point) {
                onClipSelected?(track.id, clip.id)
                return
            }
        }
    }

    private func handlePianoMouseDown(_ point: NSPoint) {
        guard let track = selectedTrack else { return }
        if activeTool == .erase {
            onPianoNoteDeleted?()
            return
        }
        let left: CGFloat = 60
        let top: CGFloat = 58
        let rowHeight: CGFloat = 13
        let beatWidth: CGFloat = 28
        let highNote = 91
        let beat = max(0, round(((point.x - left) / beatWidth) * 4) / 4)
        let note = max(54, min(91, highNote - Int((point.y - top) / rowHeight)))
        guard point.x >= left, point.y >= top else { return }
        let duration = snap == "1/8" ? 0.5 : snap == "1/16" ? 0.25 : 0.75
        onPianoNoteAdded?(PianoNote(id: makeId("note"), beat: Double(beat), duration: duration, note: note, velocity: 0.82, color: track.color ?? "#60c8f8"))
    }

    private func handlePluginMouseDown(_ point: NSPoint) {
        guard let track = selectedTrack else { return }
        let effects = track.effects ?? []
        for (index, effect) in effects.enumerated() {
            let col = index % 2
            let row = index / 2
            let rect = NSRect(x: 18 + CGFloat(col) * 360, y: 62 + CGFloat(row) * 82, width: 338, height: 66)
            guard rect.contains(point) else { continue }
            if point.x < rect.minX + 170 {
                onEffectToggle?(track.id, effect.id)
            } else {
                let amount = max(0, min(1, Double((point.x - rect.minX - 34) / (rect.width - 56))))
                onEffectAmount?(track.id, effect.id, amount)
            }
            return
        }
    }

    private func handleSampleMouseDown(_ point: NSPoint) {
        let normalize = NSRect(x: bounds.width - 216, y: 12, width: 92, height: 26)
        let reverse = NSRect(x: bounds.width - 112, y: 12, width: 92, height: 26)
        if normalize.contains(point) {
            onSampleNormalize?()
        } else if reverse.contains(point) {
            onSampleReverse?()
        }
    }

    private func drawWaveform(in rect: NSRect, color: NSColor, seed: Int) {
        guard rect.width > 8, rect.height > 4 else { return }
        color.setStroke()
        let path = NSBezierPath()
        let midY = rect.midY
        var x = rect.minX
        var index = 0
        while x <= rect.maxX {
            let phase = CGFloat(abs((seed + index * 37) % 100)) / 100
            let height = max(2, rect.height * (0.25 + phase * 0.7))
            path.move(to: NSPoint(x: x, y: midY - height / 2))
            path.line(to: NSPoint(x: x, y: midY + height / 2))
            x += 5
            index += 1
        }
        path.lineWidth = 1
        path.stroke()
    }

    private func drawPatternDots(in rect: NSRect, color: NSColor) {
        var x = rect.minX
        color.setFill()
        while x < rect.maxX {
            NSBezierPath(ovalIn: NSRect(x: x, y: rect.midY - 2, width: 4, height: 4)).fill()
            x += 12
        }
    }
}

final class MixerView: NSView {
    var tracks: [Track] = [] {
        didSet {
            invalidateIntrinsicContentSize()
            needsDisplay = true
        }
    }
    var controls: [String: MixerControl] = [:] {
        didSet { needsDisplay = true }
    }
    var selectedTrackId: String? {
        didSet { needsDisplay = true }
    }
    var onTrackSelected: ((String) -> Void)?
    var onControlChanged: ((String, MixerControl) -> Void)?

    override var isFlipped: Bool { true }
    override var intrinsicContentSize: NSSize {
        NSSize(width: max(300, CGFloat(tracks.count) * 66 + 20), height: 360)
    }

    override func draw(_ dirtyRect: NSRect) {
        NSColor(calibratedRed: 0.075, green: 0.083, blue: 0.095, alpha: 1).setFill()
        dirtyRect.fill()

        for (index, track) in tracks.enumerated() {
            let x = 10 + CGFloat(index) * 66
            let strip = NSRect(x: x, y: 8, width: 56, height: bounds.height - 16)
            let selected = track.id == selectedTrackId
            roundedFill(strip, radius: 7, color: selected ? NSColor(calibratedRed: 0.15, green: 0.18, blue: 0.205, alpha: 1) : (index.isMultiple(of: 2) ? Palette.panel : Palette.panelAlt))
            roundedStroke(strip, radius: 7, color: selected ? Palette.blue : Palette.subtleStroke, width: selected ? 1.4 : 1)
            drawText(String(format: "%02d", index + 1), in: NSRect(x: x + 8, y: 16, width: 40, height: 14), color: Palette.dim, size: 9, weight: .bold, alignment: .center)
            drawText(track.name, in: NSRect(x: x + 8, y: 34, width: 40, height: 38), color: Palette.text, size: 10, weight: .black, alignment: .center, lineBreak: .byWordWrapping)

            let control = controls[track.id] ?? MixerControl(gain: track.gain ?? 0.7, pan: track.pan ?? 0, mute: false, solo: false, arm: false, sendA: 0.15, sendB: 0.08)
            let meter = NSRect(x: x + 10, y: 86, width: 8, height: 160)
            roundedFill(meter, radius: 3, color: NSColor(calibratedRed: 0.08, green: 0.09, blue: 0.10, alpha: 1))
            let gain = CGFloat(max(0.05, min(control.gain, 1.2))) / 1.2
            let fill = NSRect(x: meter.minX, y: meter.maxY - meter.height * gain, width: meter.width, height: meter.height * gain)
            roundedFill(fill, radius: 3, color: color(from: track.color, fallback: Palette.green))

            let faderTrack = NSRect(x: x + 31, y: 86, width: 6, height: 160)
            roundedFill(faderTrack, radius: 3, color: NSColor(calibratedRed: 0.08, green: 0.09, blue: 0.10, alpha: 1))
            let faderY = faderTrack.maxY - faderTrack.height * gain
            roundedFill(NSRect(x: x + 24, y: faderY - 4, width: 20, height: 8), radius: 3, color: Palette.text)

            let pan = control.pan
            let panLabel = pan == 0 ? "C" : String(format: "%+.1f", pan)
            drawText(panLabel, in: NSRect(x: x + 8, y: 260, width: 40, height: 14), color: Palette.muted, size: 9, weight: .bold, alignment: .center)
            roundedFill(NSRect(x: x + 12, y: 284, width: 32, height: 18), radius: 4, color: color(from: track.color, fallback: Palette.blue).withAlphaComponent(0.8))
            drawText(control.mute ? "MUTE" : (control.solo ? "SOLO" : "FX"), in: NSRect(x: x + 8, y: 308, width: 40, height: 12), color: control.mute ? Palette.coral : Palette.muted, size: 8, weight: .black, alignment: .center)
        }
    }

    override func mouseDown(with event: NSEvent) {
        let point = convert(event.locationInWindow, from: nil)
        let index = Int((point.x - 10) / 66)
        guard index >= 0, index < tracks.count else { return }
        let track = tracks[index]
        onTrackSelected?(track.id)

        var control = controls[track.id] ?? MixerControl(gain: track.gain ?? 0.7, pan: track.pan ?? 0, mute: false, solo: false, arm: false, sendA: 0.15, sendB: 0.08)
        let localY = point.y
        if localY > 286 {
            control.mute.toggle()
        } else if localY > 240 {
            control.pan = control.pan >= 0.5 ? -0.5 : control.pan + 0.5
        } else if localY > 86 {
            let gain = max(0, min(1.4, Double((246 - localY) / 160) * 1.4))
            control.gain = gain
        }
        onControlChanged?(track.id, control)
    }
}

final class AutomationScopeView: NSView {
    var project: LocalProject? {
        didSet { needsDisplay = true }
    }

    override var isFlipped: Bool { true }

    override func draw(_ dirtyRect: NSRect) {
        NSColor(calibratedRed: 0.075, green: 0.083, blue: 0.095, alpha: 1).setFill()
        dirtyRect.fill()

        let left = bounds.insetBy(dx: 14, dy: 12)
        let scopeRect = NSRect(x: left.minX, y: left.minY, width: left.width * 0.42, height: left.height)
        let automationRect = NSRect(x: scopeRect.maxX + 18, y: left.minY, width: left.width - scopeRect.width - 18, height: left.height)

        drawText("Master scope", in: NSRect(x: scopeRect.minX, y: scopeRect.minY, width: scopeRect.width, height: 18), color: Palette.text, size: 12, weight: .black)
        roundedFill(NSRect(x: scopeRect.minX, y: scopeRect.minY + 28, width: scopeRect.width, height: scopeRect.height - 28), radius: 7, color: Palette.panel)
        drawScope(in: NSRect(x: scopeRect.minX + 12, y: scopeRect.minY + 44, width: scopeRect.width - 24, height: scopeRect.height - 58))

        drawText("Automation lanes", in: NSRect(x: automationRect.minX, y: automationRect.minY, width: automationRect.width, height: 18), color: Palette.text, size: 12, weight: .black)
        let box = NSRect(x: automationRect.minX, y: automationRect.minY + 28, width: automationRect.width, height: automationRect.height - 28)
        roundedFill(box, radius: 7, color: Palette.panel)
        drawAutomation(in: box.insetBy(dx: 14, dy: 14))
    }

    private func drawScope(in rect: NSRect) {
        Palette.subtleStroke.setStroke()
        for i in 0..<6 {
            let y = rect.minY + CGFloat(i) * rect.height / 5
            let line = NSBezierPath()
            line.move(to: NSPoint(x: rect.minX, y: y))
            line.line(to: NSPoint(x: rect.maxX, y: y))
            line.lineWidth = 0.7
            line.stroke()
        }

        let path = NSBezierPath()
        let points = 84
        for i in 0..<points {
            let t = CGFloat(i) / CGFloat(points - 1)
            let x = rect.minX + t * rect.width
            let wave = sin(t * CGFloat.pi * 8) * 0.35 + sin(t * CGFloat.pi * 21) * 0.12
            let y = rect.midY + wave * rect.height * 0.42
            if i == 0 {
                path.move(to: NSPoint(x: x, y: y))
            } else {
                path.line(to: NSPoint(x: x, y: y))
            }
        }
        Palette.blue.setStroke()
        path.lineWidth = 2
        path.stroke()
    }

    private func drawAutomation(in rect: NSRect) {
        Palette.subtleStroke.setStroke()
        for i in 0..<5 {
            let x = rect.minX + CGFloat(i) * rect.width / 4
            let line = NSBezierPath()
            line.move(to: NSPoint(x: x, y: rect.minY))
            line.line(to: NSPoint(x: x, y: rect.maxY))
            line.lineWidth = 0.7
            line.stroke()
        }

        let path = NSBezierPath()
        path.move(to: NSPoint(x: rect.minX, y: rect.maxY - rect.height * 0.18))
        path.curve(
            to: NSPoint(x: rect.minX + rect.width * 0.38, y: rect.minY + rect.height * 0.18),
            controlPoint1: NSPoint(x: rect.minX + rect.width * 0.10, y: rect.maxY - rect.height * 0.10),
            controlPoint2: NSPoint(x: rect.minX + rect.width * 0.25, y: rect.minY + rect.height * 0.22)
        )
        path.curve(
            to: NSPoint(x: rect.maxX, y: rect.minY + rect.height * 0.32),
            controlPoint1: NSPoint(x: rect.minX + rect.width * 0.58, y: rect.maxY - rect.height * 0.08),
            controlPoint2: NSPoint(x: rect.minX + rect.width * 0.82, y: rect.minY + rect.height * 0.42)
        )
        Palette.yellow.setStroke()
        path.lineWidth = 2.5
        path.stroke()

        drawText("filter cut  /  reverb throw  /  sidechain", in: NSRect(x: rect.minX, y: rect.maxY - 18, width: rect.width, height: 14), color: Palette.muted, size: 10, weight: .bold)
    }
}

final class RecipeView: NSView {
    var project: LocalProject? {
        didSet { needsDisplay = true }
    }

    override var isFlipped: Bool { true }

    override func draw(_ dirtyRect: NSRect) {
        NSColor(calibratedRed: 0.075, green: 0.083, blue: 0.095, alpha: 1).setFill()
        dirtyRect.fill()
        guard let project else {
            drawText("Open a project", in: bounds.insetBy(dx: 12, dy: 12), color: Palette.muted, size: 12, weight: .bold)
            return
        }

        let meta = project.keyCenter ?? "Local project"
        drawText(project.name, in: NSRect(x: 0, y: 0, width: bounds.width, height: 20), color: Palette.text, size: 13, weight: .black)
        drawText(meta, in: NSRect(x: 0, y: 22, width: bounds.width, height: 16), color: Palette.muted, size: 11, weight: .semibold)

        let recipe = project.snapshot.recipe ?? []
        if bounds.height < 160 {
            drawText("\(recipe.count) recipe items mapped", in: NSRect(x: 0, y: 48, width: bounds.width, height: 16), color: Palette.dim, size: 10, weight: .bold)
            return
        }

        let shown = recipe.prefix(5)
        var y: CGFloat = 52
        for item in shown {
            roundedFill(NSRect(x: 0, y: y, width: bounds.width, height: 34), radius: 6, color: Palette.panelAlt)
            roundedFill(NSRect(x: 10, y: y + 12, width: 9, height: 9), radius: 2, color: (item.status == "implemented" ? Palette.green : Palette.yellow))
            drawText(item.label, in: NSRect(x: 28, y: y + 8, width: bounds.width - 36, height: 16), color: Palette.text, size: 10, weight: .bold)
            y += 40
        }
    }
}

final class MainWindowController: NSWindowController {
    private let store: ProjectStore
    private var projects: [LocalProject] = []
    private var currentProject: LocalProject?
    private var players: [AVAudioPlayer] = []
    private var keyMonitor: Any?
    private var autosaveTimer: Timer?
    private var undoStack: [LocalProject] = []
    private var redoStack: [LocalProject] = []
    private var activeWorkView: WorkView = .playlist
    private var activeTool: ToolId = .select
    private var selectedTrackId = ""
    private var selectedClipId = ""
    private var audioRecorder: AVAudioRecorder?
    private var recordingURL: URL?
    private var lastVocalAnalysis: [String: Any]?
    private var isPlaying = false
    private var isRecording = false
    private var zoom: CGFloat = 38
    private lazy var projectBrowserController = ProjectBrowserWindowController()

    private let titleLabel = makeLabel("Neon Studio", size: 26, weight: .black)
    private let subtitleLabel = makeLabel("Native Mac DAW shell", size: 12, weight: .bold, color: Palette.muted)
    private let statusLabel = makeLabel("Ready", size: 11, weight: .bold, color: Palette.muted, mono: true)
    private let toolbarStatusLabel = makeLabel("Snap: 1/4   Loop: Off   P01   Swing: 0", size: 11, weight: .bold, color: Palette.muted, mono: true)
    private let projectReadout = ReadoutView(title: "Project", value: "None")
    private let bpmReadout = ReadoutView(title: "BPM", value: "--")
    private let barReadout = ReadoutView(title: "Bars", value: "--")
    private let trackReadout = ReadoutView(title: "Tracks", value: "--")
    private let modeReadout = ReadoutView(title: "Mode", value: "Local")
    private let browserView = BrowserProjectsView()
    private let channelRackView = ChannelRackView()
    private let playlistView = PlaylistView()
    private let mixerView = MixerView()
    private let automationScopeView = AutomationScopeView()
    private let recipeView = RecipeView()
    private lazy var playButton = ClosureButton(title: "Play", symbol: "play.fill", primary: true) { [weak self] in
        self?.togglePlayback()
    }

    init(store: ProjectStore) {
        self.store = store
        let screenFrame = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1180, height: 720)
        let initialFrame = Self.initialWindowFrame(in: screenFrame)
        let minimumSize = Self.minimumWindowSize(in: screenFrame)
        let window = NSWindow(
            contentRect: initialFrame,
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.title = "Neon Studio"
        window.minSize = minimumSize
        window.appearance = NSAppearance(named: .darkAqua)
        window.titlebarAppearsTransparent = true
        super.init(window: window)
        window.contentView = makeRootView()
        window.setFrame(initialFrame, display: true)
        installKeyboardMonitor()
        loadProjects()
    }

    private static func initialWindowFrame(in visibleFrame: NSRect) -> NSRect {
        let margin: CGFloat = 28
        let width = min(1180, max(820, visibleFrame.width - margin * 2))
        let height = min(700, max(540, visibleFrame.height - margin * 2))
        return NSRect(
            x: visibleFrame.midX - width / 2,
            y: visibleFrame.midY - height / 2,
            width: width,
            height: height
        )
    }

    private static func minimumWindowSize(in visibleFrame: NSRect) -> NSSize {
        NSSize(
            width: min(840, max(720, visibleFrame.width - 80)),
            height: min(540, max(480, visibleFrame.height - 80))
        )
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    deinit {
        if let keyMonitor {
            NSEvent.removeMonitor(keyMonitor)
        }
        autosaveTimer?.invalidate()
    }

    private func makeRootView() -> NSView {
        let root = NSView()
        root.wantsLayer = true
        root.layer?.backgroundColor = Palette.app.cgColor

        let header = makeHeader()
        let body = makeBody()
        header.translatesAutoresizingMaskIntoConstraints = false
        body.translatesAutoresizingMaskIntoConstraints = false
        root.addSubview(header)
        root.addSubview(body)

        NSLayoutConstraint.activate([
            header.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            header.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            header.topAnchor.constraint(equalTo: root.topAnchor),
            header.heightAnchor.constraint(equalToConstant: 90),

            body.leadingAnchor.constraint(equalTo: root.leadingAnchor, constant: 10),
            body.trailingAnchor.constraint(equalTo: root.trailingAnchor, constant: -10),
            body.topAnchor.constraint(equalTo: header.bottomAnchor, constant: 10),
            body.bottomAnchor.constraint(equalTo: root.bottomAnchor, constant: -10)
        ])

        return root
    }

    private func makeHeader() -> NSView {
        let header = NSView()
        header.wantsLayer = true
        header.layer?.backgroundColor = NSColor(calibratedRed: 0.105, green: 0.115, blue: 0.128, alpha: 1).cgColor

        let logo = LogoView()
        logo.translatesAutoresizingMaskIntoConstraints = false

        let titleStack = NSStackView(views: [titleLabel, subtitleLabel, statusLabel])
        titleStack.orientation = .vertical
        titleStack.alignment = .leading
        titleStack.spacing = 3
        titleStack.translatesAutoresizingMaskIntoConstraints = false

        projectReadout.onClick = { [weak self] in self?.showProjectManager() }
        bpmReadout.onClick = { [weak self] in self?.editBPM() }
        barReadout.onClick = { [weak self] in self?.editLoopRange() }
        trackReadout.onClick = { [weak self] in self?.importAudioFile() }
        modeReadout.onClick = { [weak self] in self?.toggleArrangementMode() }

        let projects = ClosureButton(title: "Projects", symbol: "folder") { [weak self] in
            self?.showProjectManager()
        }
        let save = ClosureButton(title: "Save", symbol: "square.and.arrow.down") { [weak self] in
            self?.saveCurrentProject(showStatus: true)
        }
        let undo = ClosureButton(title: "Undo", symbol: "arrow.uturn.backward") { [weak self] in
            self?.undo()
        }
        let redo = ClosureButton(title: "Redo", symbol: "arrow.uturn.forward") { [weak self] in
            self?.redo()
        }
        let rewind = ClosureButton(title: "Start", symbol: "backward.end.fill") { [weak self] in
            self?.stop()
            self?.statusLabel.stringValue = "Returned to bar 1"
        }
        let record = ClosureButton(title: "Rec", symbol: "record.circle") { [weak self] in
            self?.toggleRecording()
        }
        let help = ClosureButton(title: "Help", symbol: "questionmark.circle") { [weak self] in
            self?.showHelp()
        }

        [projects, save, undo, redo, rewind, playButton, record, help].forEach { button in
            button.heightAnchor.constraint(equalToConstant: 38).isActive = true
            button.widthAnchor.constraint(greaterThanOrEqualToConstant: button === playButton ? 78 : 64).isActive = true
        }

        let controls = NSStackView(views: [projects, save, undo, redo, rewind, playButton, record, help])
        controls.orientation = .horizontal
        controls.alignment = .centerY
        controls.spacing = 8
        controls.translatesAutoresizingMaskIntoConstraints = false

        let readouts = NSStackView(views: [projectReadout, bpmReadout, barReadout, trackReadout, modeReadout])
        readouts.orientation = .horizontal
        readouts.alignment = .centerY
        readouts.spacing = 8
        readouts.translatesAutoresizingMaskIntoConstraints = false

        header.addSubview(logo)
        header.addSubview(titleStack)
        header.addSubview(readouts)
        header.addSubview(controls)

        NSLayoutConstraint.activate([
            logo.leadingAnchor.constraint(equalTo: header.leadingAnchor, constant: 18),
            logo.centerYAnchor.constraint(equalTo: header.centerYAnchor),
            logo.widthAnchor.constraint(equalToConstant: 44),
            logo.heightAnchor.constraint(equalToConstant: 44),

            titleStack.leadingAnchor.constraint(equalTo: logo.trailingAnchor, constant: 16),
            titleStack.centerYAnchor.constraint(equalTo: header.centerYAnchor, constant: 2),
            titleStack.widthAnchor.constraint(greaterThanOrEqualToConstant: 190),

            controls.trailingAnchor.constraint(equalTo: header.trailingAnchor, constant: -18),
            controls.centerYAnchor.constraint(equalTo: header.centerYAnchor, constant: 2),

            readouts.leadingAnchor.constraint(equalTo: titleStack.trailingAnchor, constant: 26),
            readouts.trailingAnchor.constraint(lessThanOrEqualTo: controls.leadingAnchor, constant: -24),
            readouts.centerYAnchor.constraint(equalTo: header.centerYAnchor, constant: 2)
        ])

        return header
    }

    private func makeBody() -> NSView {
        let split = NSSplitView()
        split.isVertical = true
        split.dividerStyle = .thin
        split.translatesAutoresizingMaskIntoConstraints = false
        split.wantsLayer = true
        split.layer?.backgroundColor = Palette.app.cgColor

        let left = makeLeftColumn()
        let center = makeCenterColumn()
        let right = makeRightColumn()

        split.addArrangedSubview(left)
        split.addArrangedSubview(center)
        split.addArrangedSubview(right)

        let leftWidth = left.widthAnchor.constraint(equalToConstant: 268)
        leftWidth.priority = .defaultHigh
        leftWidth.isActive = true
        let rightWidth = right.widthAnchor.constraint(equalToConstant: 268)
        rightWidth.priority = .defaultHigh
        rightWidth.isActive = true

        return split
    }

    private func makeVerticalSplit(top: NSView, bottom: NSView, topHeight: CGFloat, minTop: CGFloat = 150, minBottom: CGFloat = 150) -> NSSplitView {
        let split = NSSplitView()
        split.isVertical = false
        split.dividerStyle = .thin
        split.translatesAutoresizingMaskIntoConstraints = false
        split.wantsLayer = true
        split.layer?.backgroundColor = Palette.app.cgColor

        split.addArrangedSubview(top)
        split.addArrangedSubview(bottom)

        let preferredTopHeight = top.heightAnchor.constraint(equalToConstant: topHeight)
        preferredTopHeight.priority = .defaultHigh
        preferredTopHeight.isActive = true

        top.heightAnchor.constraint(greaterThanOrEqualToConstant: minTop).isActive = true
        bottom.heightAnchor.constraint(greaterThanOrEqualToConstant: minBottom).isActive = true
        top.setContentHuggingPriority(.defaultLow, for: .vertical)
        bottom.setContentHuggingPriority(.defaultLow, for: .vertical)
        top.setContentCompressionResistancePriority(.defaultLow, for: .vertical)
        bottom.setContentCompressionResistancePriority(.defaultLow, for: .vertical)

        return split
    }

    private func makeLeftColumn() -> NSView {
        let browserPanel = TitledPanel(title: "Browser", accessory: "Local")
        let browserScroll = NSScrollView()
        browserScroll.documentView = browserView
        browserScroll.hasVerticalScroller = true
        browserScroll.drawsBackground = false
        browserScroll.translatesAutoresizingMaskIntoConstraints = false
        browserPanel.contentGuide.addSubview(browserScroll)
        NSLayoutConstraint.activate([
            browserScroll.leadingAnchor.constraint(equalTo: browserPanel.contentGuide.leadingAnchor),
            browserScroll.trailingAnchor.constraint(equalTo: browserPanel.contentGuide.trailingAnchor),
            browserScroll.topAnchor.constraint(equalTo: browserPanel.contentGuide.topAnchor),
            browserScroll.bottomAnchor.constraint(equalTo: browserPanel.contentGuide.bottomAnchor)
        ])

        let rackPanel = TitledPanel(title: "Channel Rack", accessory: "P01")
        let rackScroll = NSScrollView()
        rackScroll.documentView = channelRackView
        rackScroll.hasVerticalScroller = true
        rackScroll.hasHorizontalScroller = true
        rackScroll.autohidesScrollers = false
        rackScroll.drawsBackground = false
        rackScroll.translatesAutoresizingMaskIntoConstraints = false
        rackPanel.contentGuide.addSubview(rackScroll)
        NSLayoutConstraint.activate([
            rackScroll.leadingAnchor.constraint(equalTo: rackPanel.contentGuide.leadingAnchor),
            rackScroll.trailingAnchor.constraint(equalTo: rackPanel.contentGuide.trailingAnchor),
            rackScroll.topAnchor.constraint(equalTo: rackPanel.contentGuide.topAnchor),
            rackScroll.bottomAnchor.constraint(equalTo: rackPanel.contentGuide.bottomAnchor)
        ])

        return makeVerticalSplit(top: browserPanel, bottom: rackPanel, topHeight: 220, minTop: 150, minBottom: 180)
    }

    private func makeCenterColumn() -> NSView {
        let toolbar = makePlaylistToolbar()
        toolbar.heightAnchor.constraint(equalToConstant: 78).isActive = true

        let playlistPanel = TitledPanel(title: "Playlist", accessory: "Arrangement")
        let playlistScroll = NSScrollView()
        playlistScroll.documentView = playlistView
        playlistScroll.hasVerticalScroller = true
        playlistScroll.hasHorizontalScroller = true
        playlistScroll.autohidesScrollers = false
        playlistScroll.drawsBackground = false
        playlistScroll.translatesAutoresizingMaskIntoConstraints = false
        playlistPanel.contentGuide.addSubview(playlistScroll)
        NSLayoutConstraint.activate([
            playlistScroll.leadingAnchor.constraint(equalTo: playlistPanel.contentGuide.leadingAnchor),
            playlistScroll.trailingAnchor.constraint(equalTo: playlistPanel.contentGuide.trailingAnchor),
            playlistScroll.topAnchor.constraint(equalTo: playlistPanel.contentGuide.topAnchor),
            playlistScroll.bottomAnchor.constraint(equalTo: playlistPanel.contentGuide.bottomAnchor)
        ])

        let arrangementStack = NSStackView(views: [toolbar, playlistPanel])
        arrangementStack.orientation = .vertical
        arrangementStack.alignment = .width
        arrangementStack.distribution = .fill
        arrangementStack.spacing = 10
        arrangementStack.translatesAutoresizingMaskIntoConstraints = false

        let scopePanel = TitledPanel(title: "Automation + Scope", accessory: "Live")
        automationScopeView.translatesAutoresizingMaskIntoConstraints = false
        scopePanel.contentGuide.addSubview(automationScopeView)
        NSLayoutConstraint.activate([
            automationScopeView.leadingAnchor.constraint(equalTo: scopePanel.contentGuide.leadingAnchor),
            automationScopeView.trailingAnchor.constraint(equalTo: scopePanel.contentGuide.trailingAnchor),
            automationScopeView.topAnchor.constraint(equalTo: scopePanel.contentGuide.topAnchor),
            automationScopeView.bottomAnchor.constraint(equalTo: scopePanel.contentGuide.bottomAnchor)
        ])

        return makeVerticalSplit(top: arrangementStack, bottom: scopePanel, topHeight: 410, minTop: 260, minBottom: 120)
    }

    private func makePlaylistToolbar() -> NSView {
        let toolbar = NSView()
        toolbar.wantsLayer = true
        toolbar.layer?.backgroundColor = Palette.panel.cgColor
        toolbar.layer?.borderColor = Palette.stroke.cgColor
        toolbar.layer?.borderWidth = 1
        toolbar.layer?.cornerRadius = 8
        toolbar.translatesAutoresizingMaskIntoConstraints = false

        let viewTitles: [WorkView: String] = [
            .playlist: "Playlist",
            .piano: "Piano",
            .mixer: "Mixer",
            .plugins: "Plug",
            .sample: "Sample",
            .recipe: "Recipe"
        ]
        let views = WorkView.allCases.map { view in
            ClosureButton(title: viewTitles[view] ?? view.label, symbol: symbol(for: view), fontSize: 11) { [weak self] in
                self?.setWorkView(view)
            }
        }
        views.forEach { button in
            button.heightAnchor.constraint(equalToConstant: 28).isActive = true
            button.widthAnchor.constraint(greaterThanOrEqualToConstant: 56).isActive = true
        }

        let tools = ToolId.allCases.map { tool in
            ClosureButton(title: tool.label, symbol: symbol(for: tool), fontSize: 10.5) { [weak self] in
                self?.activeTool = tool
                self?.playlistView.activeTool = tool
                self?.statusLabel.stringValue = "\(tool.label) tool selected"
            }
        }

        tools.forEach { button in
            button.heightAnchor.constraint(equalToConstant: 28).isActive = true
            button.widthAnchor.constraint(greaterThanOrEqualToConstant: 50).isActive = true
        }

        let projectControls: [ClosureButton] = [
            ClosureButton(title: "Snap", symbol: "magnet", fontSize: 10.5) { [weak self] in self?.cycleSnap() },
            ClosureButton(title: "Loop", symbol: "repeat", fontSize: 10.5) { [weak self] in self?.toggleLoop() },
            ClosureButton(title: "P-", symbol: "minus", fontSize: 10.5) { [weak self] in self?.adjustPattern(by: -1) },
            ClosureButton(title: "P+", symbol: "plus", fontSize: 10.5) { [weak self] in self?.adjustPattern(by: 1) },
            ClosureButton(title: "Sw-", symbol: "dial.low", fontSize: 10.5) { [weak self] in self?.adjustSwing(by: -5) },
            ClosureButton(title: "Sw+", symbol: "dial.high", fontSize: 10.5) { [weak self] in self?.adjustSwing(by: 5) },
            ClosureButton(title: "Z-", symbol: "minus.magnifyingglass", fontSize: 10.5) { [weak self] in self?.adjustZoom(by: -6) },
            ClosureButton(title: "Z+", symbol: "plus.magnifyingglass", fontSize: 10.5) { [weak self] in self?.adjustZoom(by: 6) }
        ]
        projectControls.forEach { button in
            button.heightAnchor.constraint(equalToConstant: 28).isActive = true
            button.widthAnchor.constraint(greaterThanOrEqualToConstant: 38).isActive = true
        }

        let viewStack = NSStackView(views: views)
        viewStack.orientation = .horizontal
        viewStack.spacing = 6
        viewStack.alignment = .centerY
        viewStack.translatesAutoresizingMaskIntoConstraints = false

        let toolStack = NSStackView(views: tools)
        toolStack.orientation = .horizontal
        toolStack.spacing = 6
        toolStack.alignment = .centerY
        toolStack.translatesAutoresizingMaskIntoConstraints = false

        let projectControlStack = NSStackView(views: projectControls)
        projectControlStack.orientation = .horizontal
        projectControlStack.spacing = 5
        projectControlStack.alignment = .centerY
        projectControlStack.translatesAutoresizingMaskIntoConstraints = false

        let rightStack = NSStackView(views: [projectControlStack, toolbarStatusLabel])
        rightStack.orientation = .vertical
        rightStack.alignment = .trailing
        rightStack.spacing = 4
        rightStack.translatesAutoresizingMaskIntoConstraints = false

        toolbar.addSubview(viewStack)
        toolbar.addSubview(toolStack)
        toolbar.addSubview(rightStack)
        NSLayoutConstraint.activate([
            viewStack.leadingAnchor.constraint(equalTo: toolbar.leadingAnchor, constant: 12),
            viewStack.topAnchor.constraint(equalTo: toolbar.topAnchor, constant: 7),
            toolStack.leadingAnchor.constraint(equalTo: toolbar.leadingAnchor, constant: 12),
            toolStack.topAnchor.constraint(equalTo: viewStack.bottomAnchor, constant: 5),
            rightStack.trailingAnchor.constraint(equalTo: toolbar.trailingAnchor, constant: -14),
            rightStack.centerYAnchor.constraint(equalTo: toolbar.centerYAnchor),
            rightStack.leadingAnchor.constraint(greaterThanOrEqualTo: toolStack.trailingAnchor, constant: 14)
        ])
        return toolbar
    }

    private func symbol(for view: WorkView) -> String {
        switch view {
        case .playlist: return "list.bullet.rectangle"
        case .piano: return "pianokeys"
        case .mixer: return "slider.horizontal.3"
        case .plugins: return "bolt.horizontal"
        case .sample: return "waveform"
        case .recipe: return "checklist"
        }
    }

    private func symbol(for tool: ToolId) -> String {
        switch tool {
        case .select: return "cursorarrow"
        case .draw: return "pencil"
        case .paint: return "paintbrush"
        case .slice: return "scissors"
        case .mute: return "speaker.slash"
        case .erase: return "eraser"
        }
    }

    private func makeRightColumn() -> NSView {
        let mixerPanel = TitledPanel(title: "Mixer", accessory: "Bus")
        let mixerScroll = NSScrollView()
        mixerScroll.documentView = mixerView
        mixerScroll.hasHorizontalScroller = true
        mixerScroll.hasVerticalScroller = true
        mixerScroll.autohidesScrollers = false
        mixerScroll.drawsBackground = false
        mixerScroll.translatesAutoresizingMaskIntoConstraints = false
        mixerPanel.contentGuide.addSubview(mixerScroll)
        NSLayoutConstraint.activate([
            mixerScroll.leadingAnchor.constraint(equalTo: mixerPanel.contentGuide.leadingAnchor),
            mixerScroll.trailingAnchor.constraint(equalTo: mixerPanel.contentGuide.trailingAnchor),
            mixerScroll.topAnchor.constraint(equalTo: mixerPanel.contentGuide.topAnchor),
            mixerScroll.bottomAnchor.constraint(equalTo: mixerPanel.contentGuide.bottomAnchor)
        ])

        let projectPanel = TitledPanel(title: "Project", accessory: "Portable")
        recipeView.translatesAutoresizingMaskIntoConstraints = false
        projectPanel.contentGuide.addSubview(recipeView)

        let actionButtons: [ClosureButton] = [
            ClosureButton(title: "New", symbol: "plus", fontSize: 10.5) { [weak self] in self?.createNewProject() },
            ClosureButton(title: "Save", symbol: "square.and.arrow.down", fontSize: 10.5) { [weak self] in self?.saveCurrentProject(showStatus: true) },
            ClosureButton(title: "Import", symbol: "folder.badge.plus", fontSize: 10.5) { [weak self] in self?.importProjectFile() },
            ClosureButton(title: "Audio", symbol: "waveform.badge.plus", fontSize: 10.5) { [weak self] in self?.importAudioFile() },
            ClosureButton(title: "Mix", symbol: "arrow.down.doc", fontSize: 10.5) { [weak self] in self?.exportMixdown() },
            ClosureButton(title: "Backup", symbol: "doc.zipper", fontSize: 10.5) { [weak self] in self?.backupProjectFile() },
            ClosureButton(title: "Vocal", symbol: "wand.and.stars", fontSize: 10.5) { [weak self] in self?.runVocalLab() },
            ClosureButton(title: "Delete", symbol: "trash", fontSize: 10.5) { [weak self] in self?.confirmDeleteCurrentProject() },
            ClosureButton(title: "Rename", symbol: "text.cursor", fontSize: 10.5) { [weak self] in self?.renameProject() },
            ClosureButton(title: "Reveal", symbol: "doc.text.magnifyingglass", fontSize: 10.5) { [weak self] in self?.revealCurrentProject() }
        ]
        actionButtons.forEach { button in
            button.heightAnchor.constraint(equalToConstant: 26).isActive = true
        }

        let rows = stride(from: 0, to: actionButtons.count, by: 2).map { index -> NSStackView in
            let row = NSStackView(views: Array(actionButtons[index..<min(index + 2, actionButtons.count)]))
            row.orientation = .horizontal
            row.alignment = .centerY
            row.distribution = .fillEqually
            row.spacing = 5
            row.translatesAutoresizingMaskIntoConstraints = false
            return row
        }
        let actions = NSStackView(views: rows)
        actions.orientation = .vertical
        actions.alignment = .width
        actions.distribution = .fillEqually
        actions.spacing = 5
        actions.translatesAutoresizingMaskIntoConstraints = false
        projectPanel.contentGuide.addSubview(actions)
        rows.forEach { row in
            row.widthAnchor.constraint(equalTo: actions.widthAnchor).isActive = true
        }

        NSLayoutConstraint.activate([
            recipeView.leadingAnchor.constraint(equalTo: projectPanel.contentGuide.leadingAnchor),
            recipeView.trailingAnchor.constraint(equalTo: projectPanel.contentGuide.trailingAnchor),
            recipeView.topAnchor.constraint(equalTo: projectPanel.contentGuide.topAnchor),
            recipeView.bottomAnchor.constraint(equalTo: actions.topAnchor, constant: -6),
            actions.leadingAnchor.constraint(equalTo: projectPanel.contentGuide.leadingAnchor),
            actions.trailingAnchor.constraint(equalTo: projectPanel.contentGuide.trailingAnchor),
            actions.bottomAnchor.constraint(equalTo: projectPanel.contentGuide.bottomAnchor)
        ])
        projectPanel.setContentHuggingPriority(.defaultLow, for: .horizontal)
        projectPanel.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)

        return makeVerticalSplit(top: mixerPanel, bottom: projectPanel, topHeight: 280, minTop: 170, minBottom: 230)
    }

    private func loadProjects() {
        projects = store.loadProjects()
        browserView.projects = projects
        browserView.setFrameSize(browserView.intrinsicContentSize)
        projectBrowserController.setProjects(projects, selectedId: currentProject?.id)
        browserView.onProjectSelected = { [weak self] project in
            self?.open(project)
        }
        channelRackView.onTrackSelected = { [weak self] trackId in
            self?.selectTrack(trackId)
        }
        channelRackView.onStepToggle = { [weak self] trackId, step in
            self?.toggleStep(trackId: trackId, step: step)
        }
        playlistView.onTrackSelected = { [weak self] trackId in
            self?.selectTrack(trackId)
        }
        playlistView.onClipSelected = { [weak self] trackId, clipId in
            self?.selectClip(trackId: trackId, clipId: clipId)
        }
        playlistView.onPianoNoteAdded = { [weak self] note in
            self?.addPianoNote(note)
        }
        playlistView.onPianoNoteDeleted = { [weak self] in
            self?.deleteLastPianoNote()
        }
        playlistView.onEffectToggle = { [weak self] trackId, effectId in
            self?.toggleEffect(trackId: trackId, effectId: effectId)
        }
        playlistView.onEffectAmount = { [weak self] trackId, effectId, amount in
            self?.setEffectAmount(trackId: trackId, effectId: effectId, amount: amount)
        }
        playlistView.onSampleNormalize = { [weak self] in
            self?.normalizeSelectedSample()
        }
        playlistView.onSampleReverse = { [weak self] in
            self?.reverseSelectedSample()
        }
        mixerView.onTrackSelected = { [weak self] trackId in
            self?.selectTrack(trackId)
        }
        mixerView.onControlChanged = { [weak self] trackId, control in
            self?.updateControl(trackId: trackId, control: control)
        }

        if let first = projects.first {
            open(first)
        } else {
            statusLabel.stringValue = "No .neon.json projects found at \(store.rootURL.path)"
        }
    }

    private func open(_ project: LocalProject) {
        stop(updateStatus: false)
        currentProject = store.normalize(project)
        undoStack.removeAll()
        redoStack.removeAll()
        activeWorkView = WorkView(rawValue: currentProject?.snapshot.activeView ?? "") ?? .playlist
        selectedTrackId = currentProject?.snapshot.selectedTrackId ?? currentProject?.snapshot.tracks.first?.id ?? ""
        selectedClipId = currentProject?.snapshot.selectedClipId ?? currentProject?.snapshot.tracks.flatMap { $0.clips ?? [] }.first?.id ?? ""
        refreshProjectUI(status: "Opened \(currentProject?.name ?? project.name)")
    }

    private func refreshProjectUI(status: String? = nil) {
        guard let project = currentProject else { return }
        browserView.selectedId = project.id
        browserView.projects = projects
        titleLabel.stringValue = project.name
        let itemCount = project.snapshot.recipe?.count ?? 0
        subtitleLabel.stringValue = "\(Int(project.snapshot.bpm)) BPM  \(project.snapshot.tracks.count) tracks  \(itemCount) recipe items"
        projectReadout.value = project.name
        bpmReadout.value = "\(Int(project.snapshot.bpm))"
        barReadout.value = "\(Int(maxClipEnd(project)))"
        trackReadout.value = "\(project.snapshot.tracks.count)"
        modeReadout.value = project.snapshot.arrangementMode ?? project.keyCenter ?? "Song"
        toolbarStatusLabel.stringValue = "Snap: \(project.snapshot.snap ?? "1/4")   Loop: \(project.snapshot.loopEnabled == true ? "On" : "Off") \(Int((project.snapshot.loopStartBar ?? 0) + 1))-\(Int(project.snapshot.loopEndBar ?? 16))   P\(String(format: "%02d", project.snapshot.patternIndex ?? 1))   Swing: \(Int(project.snapshot.swing ?? 0))"

        let controls = project.snapshot.controls ?? makeDefaultControls(for: project.snapshot.tracks)
        channelRackView.tracks = project.snapshot.tracks
        channelRackView.selectedTrackId = selectedTrackId
        channelRackView.setFrameSize(channelRackView.intrinsicContentSize)
        playlistView.tracks = project.snapshot.tracks
        playlistView.controls = controls
        playlistView.notes = project.snapshot.notes ?? []
        playlistView.recipe = project.snapshot.recipe ?? []
        playlistView.snap = project.snapshot.snap ?? "1/4"
        playlistView.loopEnabled = project.snapshot.loopEnabled ?? false
        playlistView.loopStartBar = project.snapshot.loopStartBar ?? 0
        playlistView.loopEndBar = project.snapshot.loopEndBar ?? 16
        playlistView.activeTool = activeTool
        playlistView.pixelsPerBar = zoom
        playlistView.workView = activeWorkView
        playlistView.selectedTrackId = selectedTrackId
        playlistView.selectedClipId = selectedClipId
        playlistView.setFrameSize(playlistView.intrinsicContentSize)
        mixerView.tracks = project.snapshot.tracks
        mixerView.controls = controls
        mixerView.selectedTrackId = selectedTrackId
        mixerView.setFrameSize(mixerView.intrinsicContentSize)
        automationScopeView.project = project
        recipeView.project = project
        projectBrowserController.setProjects(projects, selectedId: project.id)
        if let status {
            statusLabel.stringValue = status
        }
    }

    private func maxClipEnd(_ project: LocalProject) -> Double {
        project.snapshot.tracks
            .flatMap { $0.clips ?? [] }
            .map { ($0.startBar ?? 0) + ($0.bars ?? 0) }
            .max() ?? 64
    }

    private func mutateProject(_ status: String, pushHistory: Bool = true, _ update: (inout LocalProject) -> Void) {
        guard var project = currentProject else { return }
        if pushHistory {
            undoStack.append(project)
            if undoStack.count > 40 {
                undoStack.removeFirst(undoStack.count - 40)
            }
            redoStack.removeAll()
        }
        update(&project)
        project.updatedAt = nowISO()
        project.snapshot.selectedTrackId = selectedTrackId
        project.snapshot.selectedClipId = selectedClipId
        project.snapshot.activeView = activeWorkView.rawValue
        currentProject = store.normalize(project)
        upsertCurrentProject()
        refreshProjectUI(status: status)
        scheduleAutosave()
    }

    private func upsertCurrentProject() {
        guard let project = currentProject else { return }
        projects = [project] + projects.filter { $0.id != project.id }
        browserView.projects = projects
        browserView.setFrameSize(browserView.intrinsicContentSize)
    }

    private func scheduleAutosave() {
        autosaveTimer?.invalidate()
        autosaveTimer = Timer.scheduledTimer(withTimeInterval: 0.7, repeats: false) { [weak self] _ in
            self?.saveCurrentProject(showStatus: false)
        }
    }

    private func saveCurrentProject(showStatus: Bool) {
        guard let project = currentProject else { return }
        do {
            let saved = try store.saveProject(project)
            currentProject = saved
            upsertCurrentProject()
            if showStatus {
                statusLabel.stringValue = "Saved \(saved.name)"
            } else {
                statusLabel.stringValue = "Autosaved \(saved.name)"
            }
        } catch {
            statusLabel.stringValue = "Save failed: \(error.localizedDescription)"
        }
    }

    private func undo() {
        guard let previous = undoStack.popLast(), let current = currentProject else {
            statusLabel.stringValue = "Nothing to undo"
            return
        }
        redoStack.append(current)
        currentProject = previous
        selectedTrackId = previous.snapshot.selectedTrackId ?? previous.snapshot.tracks.first?.id ?? ""
        selectedClipId = previous.snapshot.selectedClipId ?? ""
        activeWorkView = WorkView(rawValue: previous.snapshot.activeView ?? "") ?? activeWorkView
        upsertCurrentProject()
        refreshProjectUI(status: "Undo")
        scheduleAutosave()
    }

    private func redo() {
        guard let next = redoStack.popLast(), let current = currentProject else {
            statusLabel.stringValue = "Nothing to redo"
            return
        }
        undoStack.append(current)
        currentProject = next
        selectedTrackId = next.snapshot.selectedTrackId ?? next.snapshot.tracks.first?.id ?? ""
        selectedClipId = next.snapshot.selectedClipId ?? ""
        activeWorkView = WorkView(rawValue: next.snapshot.activeView ?? "") ?? activeWorkView
        upsertCurrentProject()
        refreshProjectUI(status: "Redo")
        scheduleAutosave()
    }

    private func setWorkView(_ view: WorkView) {
        activeWorkView = view
        mutateProject("\(view.label) view", pushHistory: false) { project in
            project.snapshot.activeView = view.rawValue
        }
    }

    private func editBPM() {
        guard let project = currentProject else { return }
        let alert = NSAlert()
        alert.messageText = "BPM"
        alert.informativeText = "Set the project tempo. This saves into the portable .neon.json file."
        let field = NSTextField(string: "\(Int(project.snapshot.bpm))")
        field.frame = NSRect(x: 0, y: 0, width: 180, height: 24)
        alert.accessoryView = field
        alert.addButton(withTitle: "Set BPM")
        alert.addButton(withTitle: "Cancel")
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        let value = max(60, min(220, field.doubleValue))
        mutateProject("BPM \(Int(value))") { project in
            project.snapshot.bpm = value
        }
    }

    private func toggleArrangementMode() {
        mutateProject("Mode toggled") { project in
            let current = project.snapshot.arrangementMode ?? "song"
            project.snapshot.arrangementMode = current == "song" ? "pattern" : "song"
        }
    }

    private func cycleSnap() {
        let values = ["none", "1/2", "1/4", "1/8", "1/16"]
        mutateProject("Snap changed") { project in
            let current = project.snapshot.snap ?? "1/4"
            let index = values.firstIndex(of: current) ?? 2
            project.snapshot.snap = values[(index + 1) % values.count]
        }
    }

    private func toggleLoop() {
        mutateProject("Loop toggled") { project in
            project.snapshot.loopEnabled = !(project.snapshot.loopEnabled ?? false)
        }
    }

    private func editLoopRange() {
        guard let project = currentProject else { return }
        let alert = NSAlert()
        alert.messageText = "Loop Bars"
        alert.informativeText = "Set loop start and end bars. Values are 1-based."

        let stack = NSStackView()
        stack.orientation = .vertical
        stack.spacing = 8
        stack.frame = NSRect(x: 0, y: 0, width: 220, height: 58)

        let start = NSTextField(string: "\(Int((project.snapshot.loopStartBar ?? 0) + 1))")
        let end = NSTextField(string: "\(Int(project.snapshot.loopEndBar ?? 16))")
        start.placeholderString = "Start bar"
        end.placeholderString = "End bar"
        stack.addArrangedSubview(start)
        stack.addArrangedSubview(end)
        alert.accessoryView = stack
        alert.addButton(withTitle: "Set Loop")
        alert.addButton(withTitle: "Cancel")
        guard alert.runModal() == .alertFirstButtonReturn else { return }

        let startBar = max(1, min(128, start.integerValue))
        let endBar = max(startBar + 1, min(128, end.integerValue))
        mutateProject("Loop \(startBar)-\(endBar)") { project in
            project.snapshot.loopEnabled = true
            project.snapshot.loopStartBar = Double(startBar - 1)
            project.snapshot.loopEndBar = Double(endBar)
        }
    }

    private func adjustPattern(by delta: Int) {
        mutateProject("Pattern changed") { project in
            let current = project.snapshot.patternIndex ?? 1
            project.snapshot.patternIndex = max(1, min(99, current + delta))
        }
    }

    private func adjustSwing(by delta: Double) {
        mutateProject("Swing changed") { project in
            let current = project.snapshot.swing ?? 0
            project.snapshot.swing = max(0, min(75, current + delta))
        }
    }

    private func adjustZoom(by delta: CGFloat) {
        zoom = max(26, min(96, zoom + delta))
        playlistView.pixelsPerBar = zoom
        playlistView.setFrameSize(playlistView.intrinsicContentSize)
        statusLabel.stringValue = "Zoom \(Int(zoom)) px/bar"
    }

    private func selectTrack(_ trackId: String) {
        selectedTrackId = trackId
        selectedClipId = ""
        mutateProject("Selected \(trackId)", pushHistory: false) { project in
            project.snapshot.selectedTrackId = trackId
            project.snapshot.selectedClipId = ""
        }
    }

    private func selectClip(trackId: String, clipId: String) {
        selectedTrackId = trackId
        selectedClipId = clipId
        mutateProject("Selected clip", pushHistory: false) { project in
            project.snapshot.selectedTrackId = trackId
            project.snapshot.selectedClipId = clipId
        }
    }

    private func toggleStep(trackId: String, step: Int) {
        mutateProject("Toggled step \(step + 1)") { project in
            guard let trackIndex = project.snapshot.tracks.firstIndex(where: { $0.id == trackId }) else { return }
            var steps = project.snapshot.tracks[trackIndex].steps ?? []
            if steps.contains(step) {
                steps.removeAll { $0 == step }
            } else {
                steps.append(step)
                steps.sort()
            }
            project.snapshot.tracks[trackIndex].steps = steps
        }
    }

    private func updateControl(trackId: String, control: MixerControl) {
        mutateProject("Updated mixer \(trackId)") { project in
            var controls = project.snapshot.controls ?? makeDefaultControls(for: project.snapshot.tracks)
            controls[trackId] = control
            project.snapshot.controls = controls
            if let trackIndex = project.snapshot.tracks.firstIndex(where: { $0.id == trackId }) {
                project.snapshot.tracks[trackIndex].gain = control.gain
                project.snapshot.tracks[trackIndex].pan = control.pan
            }
        }
    }

    private func addPianoNote(_ note: PianoNote) {
        mutateProject("Added note") { project in
            var notes = project.snapshot.notes ?? []
            notes.append(note)
            project.snapshot.notes = notes
        }
    }

    private func deleteLastPianoNote() {
        mutateProject("Deleted last note") { project in
            project.snapshot.notes = Array((project.snapshot.notes ?? []).dropLast())
        }
    }

    private func toggleEffect(trackId: String, effectId: String) {
        mutateProject("Toggled \(effectId)") { project in
            guard let trackIndex = project.snapshot.tracks.firstIndex(where: { $0.id == trackId }) else { return }
            var effects = project.snapshot.tracks[trackIndex].effects ?? []
            guard let effectIndex = effects.firstIndex(where: { $0.id == effectId }) else { return }
            effects[effectIndex].active = !(effects[effectIndex].active ?? false)
            project.snapshot.tracks[trackIndex].effects = effects
        }
    }

    private func setEffectAmount(trackId: String, effectId: String, amount: Double) {
        mutateProject("Adjusted \(effectId)") { project in
            guard let trackIndex = project.snapshot.tracks.firstIndex(where: { $0.id == trackId }) else { return }
            var effects = project.snapshot.tracks[trackIndex].effects ?? []
            guard let effectIndex = effects.firstIndex(where: { $0.id == effectId }) else { return }
            effects[effectIndex].amount = amount
            effects[effectIndex].active = true
            project.snapshot.tracks[trackIndex].effects = effects
        }
    }

    private func normalizeSelectedSample() {
        guard !selectedTrackId.isEmpty else { return }
        mutateProject("Normalized sample") { project in
            guard let trackIndex = project.snapshot.tracks.firstIndex(where: { $0.id == selectedTrackId }) else { return }
            project.snapshot.tracks[trackIndex].gain = 0.92
            upsertEffect(name: "Normalize Gain", id: "normalize", amount: 0.92, track: &project.snapshot.tracks[trackIndex])
            var controls = project.snapshot.controls ?? makeDefaultControls(for: project.snapshot.tracks)
            var control = controls[selectedTrackId] ?? MixerControl(gain: 0.92, pan: 0, mute: false, solo: false, arm: false, sendA: 0, sendB: 0)
            control.gain = 0.92
            controls[selectedTrackId] = control
            project.snapshot.controls = controls
        }
    }

    private func reverseSelectedSample() {
        guard !selectedTrackId.isEmpty else { return }
        mutateProject("Reversed sample intent") { project in
            guard let trackIndex = project.snapshot.tracks.firstIndex(where: { $0.id == selectedTrackId }) else { return }
            upsertEffect(name: "Reverse Sample", id: "reverse", amount: 1, track: &project.snapshot.tracks[trackIndex])
        }
    }

    private func upsertEffect(name: String, id: String, amount: Double, track: inout Track) {
        var effects = track.effects ?? []
        if let index = effects.firstIndex(where: { $0.id == id }) {
            effects[index].active = true
            effects[index].amount = amount
        } else {
            effects.append(Effect(id: id, name: name, active: true, amount: amount))
        }
        track.effects = effects
    }

    private func deleteSelection() {
        guard let project = currentProject else { return }
        if !selectedClipId.isEmpty {
            mutateProject("Deleted clip") { project in
                for index in project.snapshot.tracks.indices {
                    project.snapshot.tracks[index].clips = (project.snapshot.tracks[index].clips ?? []).filter { $0.id != selectedClipId }
                }
                selectedClipId = ""
                project.snapshot.selectedClipId = ""
            }
            return
        }
        if activeWorkView == .piano, !(project.snapshot.notes ?? []).isEmpty {
            mutateProject("Deleted last note") { project in
                project.snapshot.notes?.removeLast()
            }
            return
        }
        if !selectedTrackId.isEmpty, project.snapshot.tracks.count > 1 {
            let deletingId = selectedTrackId
            mutateProject("Deleted track") { project in
                project.snapshot.tracks.removeAll { $0.id == deletingId }
                project.snapshot.controls?[deletingId] = nil
                selectedTrackId = project.snapshot.tracks.first?.id ?? ""
                selectedClipId = ""
                project.snapshot.selectedTrackId = selectedTrackId
                project.snapshot.selectedClipId = ""
            }
            return
        }
        statusLabel.stringValue = "Nothing selected"
    }

    private func createBlankProject(name: String) -> LocalProject {
        let now = nowISO()
        let track = Track(
            id: "audio-1",
            name: "Audio 1",
            kind: "audio",
            file: nil,
            color: "#60c8f8",
            gain: 0.82,
            pan: 0,
            steps: [],
            instrument: "Sampler",
            clips: [],
            effects: [
                Effect(id: "eq", name: "EQ Eight", active: false, amount: 0.35),
                Effect(id: "comp", name: "Compressor", active: false, amount: 0.35)
            ]
        )
        let snapshot = ProjectSnapshot(
            version: 3,
            bpm: 142,
            swing: 0,
            snap: "1/4",
            loopEnabled: false,
            loopStartBar: 0,
            loopEndBar: 16,
            tracks: [track],
            controls: makeDefaultControls(for: [track]),
            notes: [],
            selectedTrackId: track.id,
            selectedClipId: "",
            activeView: WorkView.playlist.rawValue,
            patternIndex: 1,
            arrangementMode: "song",
            recipe: []
        )
        return LocalProject(
            id: makeId("project"),
            name: name,
            createdAt: now,
            updatedAt: now,
            projectFile: nil,
            assets: nil,
            description: "Native Neon Studio project",
            keyCenter: nil,
            snapshot: snapshot
        )
    }

    private func createNewProject() {
        let project = createBlankProject(name: "Untitled \(projects.count + 1)")
        do {
            currentProject = try store.saveProject(project)
            projects = store.loadProjects()
            open(currentProject!)
            statusLabel.stringValue = "Created \(project.name)"
        } catch {
            statusLabel.stringValue = "Create failed: \(error.localizedDescription)"
        }
    }

    private func renameProject() {
        guard let project = currentProject else { return }
        let alert = NSAlert()
        alert.messageText = "Rename Project"
        alert.informativeText = "Project names are saved into the local .neon.json file."
        let field = NSTextField(string: project.name)
        field.frame = NSRect(x: 0, y: 0, width: 260, height: 24)
        alert.accessoryView = field
        alert.addButton(withTitle: "Rename")
        alert.addButton(withTitle: "Cancel")
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        let name = field.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else { return }
        mutateProject("Renamed \(name)") { item in
            item.name = name
        }
    }

    private func importProjectFile() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.json]
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        panel.message = "Import a portable .neon.json project."
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do {
            let imported = try store.importProject(from: url)
            projects = store.loadProjects()
            open(imported)
            statusLabel.stringValue = "Imported \(url.lastPathComponent)"
        } catch {
            statusLabel.stringValue = "Import failed: \(error.localizedDescription)"
        }
    }

    private func importAudioFile() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.audio]
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        panel.message = "Import an audio file as a new track."
        guard panel.runModal() == .OK, let url = panel.url else { return }
        let id = makeId("sample")
        let name = url.deletingPathExtension().lastPathComponent
        let color = "#9ef0c0"
        let track = Track(
            id: id,
            name: String(name.prefix(28)),
            kind: "audio",
            file: url.path,
            color: color,
            gain: 0.82,
            pan: 0,
            steps: [0, 8],
            instrument: "Imported Audio",
            clips: [Clip(id: "\(id)-clip", name: url.lastPathComponent, startBar: 0, bars: 8, lane: id, color: color, type: "audio")],
            effects: [
                Effect(id: "eq", name: "EQ Eight", active: false, amount: 0.35),
                Effect(id: "comp", name: "Compressor", active: false, amount: 0.35)
            ]
        )
        selectedTrackId = id
        mutateProject("Imported \(url.lastPathComponent)") { project in
            project.snapshot.tracks.append(track)
            var controls = project.snapshot.controls ?? makeDefaultControls(for: project.snapshot.tracks)
            controls[id] = MixerControl(gain: 0.82, pan: 0, mute: false, solo: false, arm: false, sendA: 0, sendB: 0)
            project.snapshot.controls = controls
            project.snapshot.selectedTrackId = id
        }
    }

    private func backupProjectFile() {
        guard let project = currentProject else { return }
        let panel = NSSavePanel()
        panel.allowedContentTypes = [.json]
        panel.nameFieldStringValue = "\(safeProjectId(project.name.lowercased())).neon.json"
        panel.message = "Export a portable .neon.json project file."
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do {
            try store.exportProject(project, to: url)
            statusLabel.stringValue = "Project backup exported"
        } catch {
            statusLabel.stringValue = "Backup failed: \(error.localizedDescription)"
        }
    }

    private func exportMixdown() {
        guard let project = currentProject else { return }
        let panel = NSSavePanel()
        panel.allowedContentTypes = [.wav]
        panel.nameFieldStringValue = "\(safeProjectId(project.name.lowercased()))-mixdown.wav"
        panel.message = "Render the current project state as a mixdown WAV."
        guard panel.runModal() == .OK, let destination = panel.url else { return }
        do {
            let tempProject = FileManager.default.temporaryDirectory.appendingPathComponent("\(project.id)-mixdown-project.neon.json")
            try store.exportProject(project, to: tempProject)
            statusLabel.stringValue = "Rendering mixdown"
            _ = try runProcess(
                executable: URL(fileURLWithPath: "/usr/bin/python3"),
                arguments: [
                    store.rootURL.appendingPathComponent("tools/render_mixdown.py").path,
                    "--root", store.rootURL.path,
                    "--project", tempProject.path,
                    "--output", destination.path
                ]
            )
            statusLabel.stringValue = "Mixdown exported"
        } catch {
            statusLabel.stringValue = "Mixdown failed: \(error.localizedDescription)"
        }
    }

    private func confirmDeleteCurrentProject() {
        guard let project = currentProject else { return }
        let alert = NSAlert()
        alert.messageText = "Delete \(project.name)?"
        alert.informativeText = "This removes the local project file. If this is a factory project, it is hidden by the shared deleted-project marker."
        alert.alertStyle = .warning
        alert.addButton(withTitle: "Delete")
        alert.addButton(withTitle: "Cancel")
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        do {
            try store.deleteProject(project)
            projects = store.loadProjects()
            currentProject = nil
            if let first = projects.first {
                open(first)
            } else {
                refreshProjectUI(status: "Project deleted")
            }
            statusLabel.stringValue = "Project deleted"
        } catch {
            statusLabel.stringValue = "Delete failed: \(error.localizedDescription)"
        }
    }

    private func showProjectManager() {
        projectBrowserController.onOpenProject = { [weak self] project in
            self?.open(project)
        }
        projectBrowserController.onCreateProject = { [weak self] in
            self?.createNewProject()
            if let self {
                self.projectBrowserController.setProjects(self.projects, selectedId: self.currentProject?.id)
            }
        }
        projectBrowserController.onImportProject = { [weak self] in
            self?.importProjectFile()
            if let self {
                self.projectBrowserController.setProjects(self.projects, selectedId: self.currentProject?.id)
            }
        }
        projectBrowserController.onDeleteProject = { [weak self] project in
            guard let self else { return }
            self.open(project)
            self.confirmDeleteCurrentProject()
            self.projectBrowserController.setProjects(self.projects, selectedId: self.currentProject?.id)
        }
        projectBrowserController.onRevealProject = { [weak self] project in
            guard let self else { return }
            self.open(project)
            self.revealCurrentProject()
        }
        projectBrowserController.setProjects(projects, selectedId: currentProject?.id)
        projectBrowserController.present()
    }

    private func toggleRecording() {
        isRecording ? stopRecording() : startRecording()
    }

    private func startRecording() {
        let inbox = store.rootURL.appendingPathComponent("vocal_inbox")
        try? FileManager.default.createDirectory(at: inbox, withIntermediateDirectories: true)
        let url = inbox.appendingPathComponent("native_recording_\(timestampForId()).wav")
        let settings: [String: Any] = [
            AVFormatIDKey: kAudioFormatLinearPCM,
            AVSampleRateKey: 44_100,
            AVNumberOfChannelsKey: 1,
            AVLinearPCMBitDepthKey: 16,
            AVLinearPCMIsFloatKey: false,
            AVLinearPCMIsBigEndianKey: false
        ]
        do {
            audioRecorder = try AVAudioRecorder(url: url, settings: settings)
            audioRecorder?.prepareToRecord()
            audioRecorder?.record()
            recordingURL = url
            isRecording = true
            statusLabel.stringValue = "Recording"
        } catch {
            statusLabel.stringValue = "Recording failed: \(error.localizedDescription)"
        }
    }

    private func stopRecording() {
        audioRecorder?.stop()
        audioRecorder = nil
        isRecording = false
        guard let url = recordingURL else {
            statusLabel.stringValue = "Recording stopped"
            return
        }
        addAudioTrack(from: url, name: "Recording", color: "#f59fcb", instrument: "Audio Input", startBar: 0, status: "Recording captured")
    }

    private func runVocalLab() {
        guard let project = currentProject else { return }
        guard let settings = promptVocalLabSettings(for: project) else { return }
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.audio]
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        panel.message = "Choose raw singing audio. The native app converts it to WAV, splits silences, tunes it, and aligns it to the current project."
        guard panel.runModal() == .OK, let inputURL = panel.url else { return }

        let inbox = store.rootURL.appendingPathComponent("vocal_inbox")
        let exports = store.rootURL.appendingPathComponent("exports")
        try? FileManager.default.createDirectory(at: inbox, withIntermediateDirectories: true)
        try? FileManager.default.createDirectory(at: exports, withIntermediateDirectories: true)
        let stem = safeProjectId(inputURL.deletingPathExtension().lastPathComponent.lowercased())
        let stamp = timestampForId()
        let rawWav = inbox.appendingPathComponent("\(stamp)_\(stem).wav")
        let output = exports.appendingPathComponent("vocal_\(stamp)_\(stem).wav")

        statusLabel.stringValue = "Preparing vocal"
        do {
            _ = try runProcess(
                executable: URL(fileURLWithPath: "/usr/bin/afconvert"),
                arguments: ["-f", "WAVE", "-d", "LEI16@44100", inputURL.path, rawWav.path]
            )
            statusLabel.stringValue = "Auto-tuning vocal"
            let stdout = try runProcess(
                executable: URL(fileURLWithPath: "/usr/bin/python3"),
                arguments: [
                    store.rootURL.appendingPathComponent("tools/vocal_autotune.py").path,
                    "--input", rawWav.path,
                    "--output", output.path,
                    "--name", inputURL.lastPathComponent,
                    "--bpm", "\(project.snapshot.bpm)",
                    "--start-bar", "\(settings.startBar)",
                    "--total-bars", "72",
                    "--key", settings.key
                ]
            )
            let analysis = parseLastJSONLine(stdout)
            lastVocalAnalysis = analysis
            let segments = analysis["segments"] as? Int ?? 1
            addAudioTrack(
                from: output,
                name: "Vocal \(stem.replacingOccurrences(of: "_", with: " "))",
                color: "#f59fcb",
                instrument: "AutoTune Vocal Chain",
                startBar: max(0, Double(settings.startBar - 1)),
                status: vocalStatusText(analysis: analysis, fallbackSegments: segments)
            )
        } catch {
            statusLabel.stringValue = "Vocal Lab failed: \(error.localizedDescription)"
        }
    }

    private func promptVocalLabSettings(for project: LocalProject) -> (startBar: Int, key: String)? {
        let alert = NSAlert()
        alert.messageText = "Vocal Lab"
        let defaultKey = (project.keyCenter ?? "e_minor").lowercased().replacingOccurrences(of: " / ", with: "_").replacingOccurrences(of: " ", with: "_")
        var info = "Choose where the tuned vocal should enter and which key to tune toward."
        if let lastVocalAnalysis {
            let segments = lastVocalAnalysis["segments"] as? Int ?? 0
            let correction = lastVocalAnalysis["averageCorrectionSemitones"] as? Double ?? 0
            if segments > 0 {
                info += "\nLast run: \(segments) segment\(segments == 1 ? "" : "s"), avg correction \(String(format: "%.2f", correction)) semitones."
            }
        }
        alert.informativeText = info
        let startField = NSTextField(string: "\(Int((project.snapshot.loopStartBar ?? 16) + 1))")
        let keyField = NSTextField(string: defaultKey)
        startField.frame.size.width = 70
        keyField.frame.size.width = 150
        let startLabel = makeLabel("Start Bar", size: 11, weight: .bold, color: Palette.muted)
        let keyLabel = makeLabel("Key", size: 11, weight: .bold, color: Palette.muted)
        let row1 = NSStackView(views: [startLabel, startField])
        row1.orientation = .horizontal
        row1.alignment = .centerY
        row1.spacing = 10
        let row2 = NSStackView(views: [keyLabel, keyField])
        row2.orientation = .horizontal
        row2.alignment = .centerY
        row2.spacing = 36
        let stack = NSStackView(views: [row1, row2])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 10
        alert.accessoryView = stack
        alert.addButton(withTitle: "Continue")
        alert.addButton(withTitle: "Cancel")
        guard alert.runModal() == .alertFirstButtonReturn else { return nil }
        let startBar = max(1, min(72, Int(startField.integerValue == 0 ? 17 : startField.integerValue)))
        let cleanedKey = keyField.stringValue.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return (startBar, cleanedKey.isEmpty ? defaultKey : cleanedKey)
    }

    private func vocalStatusText(analysis: [String: Any], fallbackSegments: Int) -> String {
        let segments = analysis["segments"] as? Int ?? fallbackSegments
        let correction = analysis["averageCorrectionSemitones"] as? Double ?? 0
        return "Vocal tuned: \(segments) segment\(segments == 1 ? "" : "s"), avg correction \(String(format: "%.2f", correction)) st"
    }

    private func addAudioTrack(from url: URL, name: String, color: String, instrument: String, startBar: Double, status: String) {
        let id = makeId(name.lowercased().contains("vocal") ? "vocal" : "audio")
        let duration = (try? AVAudioPlayer(contentsOf: url))?.duration ?? 16
        let bars = max(1, ceil(duration / (((currentProject?.snapshot.bpm ?? 142) > 0 ? 60 / (currentProject?.snapshot.bpm ?? 142) : 0.42) * 4)))
        let track = Track(
            id: id,
            name: String(name.prefix(28)),
            kind: "audio",
            file: url.path,
            color: color,
            gain: 0.86,
            pan: 0,
            steps: [0, 4, 8, 12],
            instrument: instrument,
            clips: [Clip(id: "\(id)-clip", name: url.lastPathComponent, startBar: startBar, bars: bars, lane: id, color: color, type: "audio")],
            effects: [
                Effect(id: "autotune", name: instrument.contains("AutoTune") ? "Scale AutoTune" : "EQ Eight", active: instrument.contains("AutoTune"), amount: 0.82),
                Effect(id: "comp", name: "Compressor", active: true, amount: 0.58),
                Effect(id: "delay", name: "Stereo Delay", active: instrument.contains("Vocal"), amount: 0.34)
            ]
        )
        selectedTrackId = id
        selectedClipId = "\(id)-clip"
        activeWorkView = .playlist
        mutateProject(status) { project in
            project.snapshot.tracks.append(track)
            var controls = project.snapshot.controls ?? makeDefaultControls(for: project.snapshot.tracks)
            controls[id] = MixerControl(gain: 0.86, pan: 0, mute: false, solo: false, arm: false, sendA: 0.26, sendB: 0.18)
            project.snapshot.controls = controls
            project.snapshot.selectedTrackId = id
            project.snapshot.selectedClipId = "\(id)-clip"
            project.snapshot.activeView = WorkView.playlist.rawValue
        }
    }

    private func runProcess(executable: URL, arguments: [String]) throws -> String {
        let process = Process()
        process.executableURL = executable
        process.arguments = arguments
        process.currentDirectoryURL = store.rootURL
        let output = Pipe()
        let error = Pipe()
        process.standardOutput = output
        process.standardError = error
        try process.run()
        process.waitUntilExit()
        let stdout = String(data: output.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
        let stderr = String(data: error.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
        if process.terminationStatus != 0 {
            throw NSError(domain: "NeonStudio", code: Int(process.terminationStatus), userInfo: [NSLocalizedDescriptionKey: stderr.isEmpty ? "Process failed" : stderr])
        }
        return stdout
    }

    private func parseLastJSONLine(_ stdout: String) -> [String: Any] {
        guard let line = stdout.split(separator: "\n").last,
              let data = String(line).data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return [:]
        }
        return object
    }

    private func togglePlayback() {
        isPlaying ? stop() : play()
    }

    private func play() {
        guard let project = currentProject else {
            statusLabel.stringValue = "Open a project first"
            return
        }

        stop(updateStatus: false)
        let controls = project.snapshot.controls ?? makeDefaultControls(for: project.snapshot.tracks)
        let soloActive = controls.values.contains { $0.solo }
        for track in project.snapshot.tracks {
            let control = controls[track.id] ?? MixerControl(gain: track.gain ?? 0.75, pan: track.pan ?? 0, mute: false, solo: false, arm: false, sendA: 0.15, sendB: 0.08)
            if control.mute || (soloActive && !control.solo) {
                continue
            }
            guard let url = store.audioURL(for: track),
                  FileManager.default.fileExists(atPath: url.path) else {
                continue
            }

            do {
                let player = try AVAudioPlayer(contentsOf: url)
                player.volume = Float(max(0, min(control.gain, 1.4)))
                player.pan = Float(max(-1, min(control.pan, 1)))
                player.prepareToPlay()
                player.play()
                players.append(player)
            } catch {
                statusLabel.stringValue = "Could not play \(track.name)"
            }
        }

        isPlaying = !players.isEmpty
        playButton.title = isPlaying ? "Stop" : "Play"
        playButton.image = nil
        statusLabel.stringValue = players.isEmpty ? "No audio stems found" : "Playing \(players.count) stems"
    }

    private func stop(updateStatus: Bool = true) {
        players.forEach { player in
            player.stop()
            player.currentTime = 0
        }
        players.removeAll()
        isPlaying = false
        playButton.title = "Play"
        playButton.image = nil
        if updateStatus, currentProject != nil {
            statusLabel.stringValue = "Stopped"
        }
    }

    private func revealCurrentProject() {
        guard let project = currentProject else { return }
        let paths = [
            store.rootURL.appendingPathComponent("data/projects/\(project.id).neon.json"),
            store.rootURL.appendingPathComponent("factory/projects/\(project.id).neon.json")
        ]
        if let url = paths.first(where: { FileManager.default.fileExists(atPath: $0.path) }) {
            NSWorkspace.shared.activateFileViewerSelecting([url])
            statusLabel.stringValue = "Revealed \(url.lastPathComponent)"
        } else {
            statusLabel.stringValue = "Project JSON not found on disk"
        }
    }

    private func showHelp() {
        let alert = NSAlert()
        alert.messageText = "Neon Studio Shortcuts"
        alert.informativeText = """
        Space: Play or stop
        Cmd+S: Save
        Cmd+H: Open this help menu
        Cmd+1...6: Switch Playlist, Piano, Mixer, Plugins, Sample, Recipe
        Cmd+R: Return to bar 1
        Cmd+Z / Shift+Cmd+Z: Undo and redo
        Delete: Delete selected clip, note, or track

        File/Edit/Add/View/Options menus expose the core DAW controls. Project actions export mixdowns, backup .neon.json files, import audio/projects, record audio, and run Vocal Lab.
        """
        alert.addButton(withTitle: "OK")
        alert.runModal()
    }

    private func installKeyboardMonitor() {
        keyMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
            guard let self else { return event }
            let key = event.charactersIgnoringModifiers?.lowercased() ?? ""
            let flags = event.modifierFlags.intersection(.deviceIndependentFlagsMask)

            if flags.contains(.command), key == "h" {
                self.showHelp()
                return nil
            }
            if flags.contains(.command), key == "s" {
                self.saveCurrentProject(showStatus: true)
                return nil
            }
            if flags.contains(.command), key == "r" {
                self.stop()
                self.statusLabel.stringValue = "Returned to bar 1"
                return nil
            }
            if flags.contains(.command), key == "z" {
                flags.contains(.shift) ? self.redo() : self.undo()
                return nil
            }
            if flags.contains(.command), key == "y" {
                self.redo()
                return nil
            }
            if event.keyCode == 49 {
                self.togglePlayback()
                return nil
            }
            if event.keyCode == 51 || event.keyCode == 117 {
                self.deleteSelection()
                return nil
            }
            return event
        }
    }

    @objc func menuNewProject(_ sender: Any?) { createNewProject() }
    @objc func menuSaveProject(_ sender: Any?) { saveCurrentProject(showStatus: true) }
    @objc func menuImportProject(_ sender: Any?) { importProjectFile() }
    @objc func menuImportAudio(_ sender: Any?) { importAudioFile() }
    @objc func menuBackupProject(_ sender: Any?) { backupProjectFile() }
    @objc func menuExportMixdown(_ sender: Any?) { exportMixdown() }
    @objc func menuRevealProject(_ sender: Any?) { revealCurrentProject() }
    @objc func menuUndo(_ sender: Any?) { undo() }
    @objc func menuRedo(_ sender: Any?) { redo() }
    @objc func menuDeleteSelection(_ sender: Any?) { deleteSelection() }
    @objc func menuVocalLab(_ sender: Any?) { runVocalLab() }
    @objc func menuToggleRecord(_ sender: Any?) { toggleRecording() }
    @objc func menuPlaylist(_ sender: Any?) { setWorkView(.playlist) }
    @objc func menuPiano(_ sender: Any?) { setWorkView(.piano) }
    @objc func menuMixer(_ sender: Any?) { setWorkView(.mixer) }
    @objc func menuPlugins(_ sender: Any?) { setWorkView(.plugins) }
    @objc func menuSample(_ sender: Any?) { setWorkView(.sample) }
    @objc func menuRecipe(_ sender: Any?) { setWorkView(.recipe) }
    @objc func menuEditBPM(_ sender: Any?) { editBPM() }
    @objc func menuToggleMode(_ sender: Any?) { toggleArrangementMode() }
    @objc func menuCycleSnap(_ sender: Any?) { cycleSnap() }
    @objc func menuToggleLoop(_ sender: Any?) { toggleLoop() }
    @objc func menuEditLoop(_ sender: Any?) { editLoopRange() }
    @objc func menuZoomIn(_ sender: Any?) { adjustZoom(by: 6) }
    @objc func menuZoomOut(_ sender: Any?) { adjustZoom(by: -6) }
    @objc func menuHelp(_ sender: Any?) { showHelp() }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var windowController: MainWindowController?

    func applicationDidFinishLaunching(_ notification: Notification) {
        let rootURL = prepareSupportRoot()

        let controller = MainWindowController(store: ProjectStore(rootURL: rootURL))
        windowController = controller
        installMenu(for: controller)
        controller.window?.center()
        controller.showWindow(nil)
        controller.window?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }

    private func prepareSupportRoot() -> URL {
        let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
            .appendingPathComponent("Neon Studio", isDirectory: true)
        try? FileManager.default.createDirectory(at: support, withIntermediateDirectories: true)

        guard let seed = Bundle.main.resourceURL?.appendingPathComponent("seed", isDirectory: true) else {
            return support
        }
        copySeedDirectory("factory", from: seed, to: support)
        copySeedDirectory("data", from: seed, to: support)
        copySeedDirectory("exports", from: seed, to: support)
        copySeedDirectory("tools", from: seed, to: support)
        return support
    }

    private func copySeedDirectory(_ name: String, from seed: URL, to support: URL) {
        let source = seed.appendingPathComponent(name, isDirectory: true)
        let destination = support.appendingPathComponent(name, isDirectory: true)
        guard FileManager.default.fileExists(atPath: source.path) else { return }
        if !FileManager.default.fileExists(atPath: destination.path) {
            try? FileManager.default.copyItem(at: source, to: destination)
            return
        }
        copyMissingContents(from: source, to: destination)
    }

    private func copyMissingContents(from source: URL, to destination: URL) {
        guard let urls = try? FileManager.default.contentsOfDirectory(at: source, includingPropertiesForKeys: [.isDirectoryKey]) else {
            return
        }
        for item in urls {
            let target = destination.appendingPathComponent(item.lastPathComponent)
            var isDirectory: ObjCBool = false
            let exists = FileManager.default.fileExists(atPath: target.path, isDirectory: &isDirectory)
            if exists {
                let values = try? item.resourceValues(forKeys: [.isDirectoryKey])
                if values?.isDirectory == true {
                    copyMissingContents(from: item, to: target)
                }
                continue
            }
            try? FileManager.default.copyItem(at: item, to: target)
        }
    }

    private func installMenu(for controller: MainWindowController) {
        let mainMenu = NSMenu()
        let appMenuItem = NSMenuItem()
        mainMenu.addItem(appMenuItem)

        let appMenu = NSMenu()
        appMenu.addItem(NSMenuItem(title: "Quit Neon Studio", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"))
        appMenuItem.submenu = appMenu

        let fileMenuItem = NSMenuItem()
        mainMenu.addItem(fileMenuItem)
        let fileMenu = NSMenu(title: "File")
        addMenuItem("New Project", #selector(MainWindowController.menuNewProject(_:)), "n", to: fileMenu, target: controller)
        addMenuItem("Save Project", #selector(MainWindowController.menuSaveProject(_:)), "s", to: fileMenu, target: controller)
        fileMenu.addItem(.separator())
        addMenuItem("Import Project...", #selector(MainWindowController.menuImportProject(_:)), "i", to: fileMenu, target: controller)
        addMenuItem("Import Audio...", #selector(MainWindowController.menuImportAudio(_:)), "a", modifiers: [.command, .shift], to: fileMenu, target: controller)
        addMenuItem("Backup Project...", #selector(MainWindowController.menuBackupProject(_:)), "b", modifiers: [.command, .shift], to: fileMenu, target: controller)
        addMenuItem("Export Mixdown...", #selector(MainWindowController.menuExportMixdown(_:)), "e", modifiers: [.command, .shift], to: fileMenu, target: controller)
        fileMenu.addItem(.separator())
        addMenuItem("Reveal Project File", #selector(MainWindowController.menuRevealProject(_:)), "r", modifiers: [.command, .shift], to: fileMenu, target: controller)
        fileMenuItem.submenu = fileMenu

        let editMenuItem = NSMenuItem()
        mainMenu.addItem(editMenuItem)
        let editMenu = NSMenu(title: "Edit")
        addMenuItem("Undo", #selector(MainWindowController.menuUndo(_:)), "z", to: editMenu, target: controller)
        addMenuItem("Redo", #selector(MainWindowController.menuRedo(_:)), "z", modifiers: [.command, .shift], to: editMenu, target: controller)
        addMenuItem("Delete Selection", #selector(MainWindowController.menuDeleteSelection(_:)), "\u{8}", modifiers: [], to: editMenu, target: controller)
        editMenuItem.submenu = editMenu

        let addMenuItemRoot = NSMenuItem()
        mainMenu.addItem(addMenuItemRoot)
        let addMenu = NSMenu(title: "Add")
        addMenuItem("Audio Track...", #selector(MainWindowController.menuImportAudio(_:)), "", modifiers: [], to: addMenu, target: controller)
        addMenuItem("Vocal Lab...", #selector(MainWindowController.menuVocalLab(_:)), "v", modifiers: [.command, .shift], to: addMenu, target: controller)
        addMenuItem("Record Take", #selector(MainWindowController.menuToggleRecord(_:)), "k", modifiers: [.command, .shift], to: addMenu, target: controller)
        addMenuItemRoot.submenu = addMenu

        let viewMenuItem = NSMenuItem()
        mainMenu.addItem(viewMenuItem)
        let viewMenu = NSMenu(title: "View")
        addMenuItem("Playlist", #selector(MainWindowController.menuPlaylist(_:)), "1", to: viewMenu, target: controller)
        addMenuItem("Piano Roll", #selector(MainWindowController.menuPiano(_:)), "2", to: viewMenu, target: controller)
        addMenuItem("Mixer", #selector(MainWindowController.menuMixer(_:)), "3", to: viewMenu, target: controller)
        addMenuItem("Plugins", #selector(MainWindowController.menuPlugins(_:)), "4", to: viewMenu, target: controller)
        addMenuItem("Sample", #selector(MainWindowController.menuSample(_:)), "5", to: viewMenu, target: controller)
        addMenuItem("Recipe", #selector(MainWindowController.menuRecipe(_:)), "6", to: viewMenu, target: controller)
        viewMenu.addItem(.separator())
        addMenuItem("Zoom In", #selector(MainWindowController.menuZoomIn(_:)), "+", to: viewMenu, target: controller)
        addMenuItem("Zoom Out", #selector(MainWindowController.menuZoomOut(_:)), "-", to: viewMenu, target: controller)
        viewMenuItem.submenu = viewMenu

        let optionsMenuItem = NSMenuItem()
        mainMenu.addItem(optionsMenuItem)
        let optionsMenu = NSMenu(title: "Options")
        addMenuItem("Set BPM...", #selector(MainWindowController.menuEditBPM(_:)), "t", modifiers: [.command, .shift], to: optionsMenu, target: controller)
        addMenuItem("Toggle Song/Pattern Mode", #selector(MainWindowController.menuToggleMode(_:)), "m", modifiers: [.command, .shift], to: optionsMenu, target: controller)
        addMenuItem("Cycle Snap", #selector(MainWindowController.menuCycleSnap(_:)), "g", modifiers: [.command, .shift], to: optionsMenu, target: controller)
        addMenuItem("Toggle Loop", #selector(MainWindowController.menuToggleLoop(_:)), "l", modifiers: [.command, .shift], to: optionsMenu, target: controller)
        addMenuItem("Edit Loop Bars...", #selector(MainWindowController.menuEditLoop(_:)), "l", modifiers: [.command, .option], to: optionsMenu, target: controller)
        optionsMenuItem.submenu = optionsMenu

        let helpMenuItem = NSMenuItem()
        mainMenu.addItem(helpMenuItem)
        let helpMenu = NSMenu(title: "Help")
        let help = NSMenuItem(title: "Neon Studio Help", action: #selector(MainWindowController.menuHelp(_:)), keyEquivalent: "h")
        help.keyEquivalentModifierMask = [.command]
        help.target = controller
        helpMenu.addItem(help)
        helpMenuItem.submenu = helpMenu
        NSApp.mainMenu = mainMenu
    }

    private func addMenuItem(
        _ title: String,
        _ action: Selector,
        _ keyEquivalent: String,
        modifiers: NSEvent.ModifierFlags = [.command],
        to menu: NSMenu,
        target: AnyObject
    ) {
        let item = NSMenuItem(title: title, action: action, keyEquivalent: keyEquivalent)
        item.keyEquivalentModifierMask = modifiers
        item.target = target
        menu.addItem(item)
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
