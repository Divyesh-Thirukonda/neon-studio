import AppKit
import NeonStudioKit

/// Process-wide services: where projects live, how helper tools are run, and
/// the user's settings.
public final class AppEnvironment {
    public static let shared = AppEnvironment()

    public let supportRoot: URL
    public let store: ProjectStore
    public let toolRunner = ToolRunner()

    /// Problems hit while seeding, collected because this runs before any window
    /// exists to report into. The app delegate posts them once the UI is up —
    /// previously a failed seed copy was swallowed entirely and the user just
    /// found features mysteriously missing.
    public private(set) var setupWarnings: [String] = []

    private init() {
        var warnings: [String] = []
        supportRoot = AppEnvironment.prepareSupportRoot(warnings: &warnings)
        store = ProjectStore(rootURL: supportRoot)
        setupWarnings = warnings
    }

    // MARK: Settings

    public enum Keys {
        public static let hasCompletedFirstRun = "NeonStudioHasCompletedFirstRun"
        public static let showWelcomeOnLaunch = "NeonStudioShowWelcomeOnLaunch"
        public static let explainMusicTerms = "NeonStudioExplainMusicTerms"
        public static let hasSeenTour = "NeonStudioHasSeenTour"
        public static let pythonInterpreter = ToolPaths.interpreterDefaultsKey
        public static let confirmDestructiveEdits = "NeonStudioConfirmDestructiveEdits"
        public static let countInBars = "NeonStudioCountInBars"
    }

    public static func registerDefaults() {
        UserDefaults.standard.register(defaults: [
            Keys.showWelcomeOnLaunch: true,
            // On until the user turns it off. Somebody who already knows what a
            // send is can switch the explanations off in Settings; somebody who
            // doesn't should never be left guessing.
            Keys.explainMusicTerms: true,
            Keys.confirmDestructiveEdits: true,
            // One bar is enough to catch a downbeat without being a wait.
            Keys.countInBars: 1
        ])
    }

    public var isFirstRun: Bool {
        !UserDefaults.standard.bool(forKey: Keys.hasCompletedFirstRun)
    }

    public func markFirstRunComplete() {
        UserDefaults.standard.set(true, forKey: Keys.hasCompletedFirstRun)
    }

    public var explainsMusicTerms: Bool {
        get { UserDefaults.standard.bool(forKey: Keys.explainMusicTerms) }
        set { UserDefaults.standard.set(newValue, forKey: Keys.explainMusicTerms) }
    }

    public var showsWelcomeOnLaunch: Bool {
        get { UserDefaults.standard.bool(forKey: Keys.showWelcomeOnLaunch) }
        set { UserDefaults.standard.set(newValue, forKey: Keys.showWelcomeOnLaunch) }
    }

    public var hasSeenTour: Bool {
        get { UserDefaults.standard.bool(forKey: Keys.hasSeenTour) }
        set { UserDefaults.standard.set(newValue, forKey: Keys.hasSeenTour) }
    }

    /// Bars of clicks before a take starts. 0 records immediately.
    public var countInBars: Int {
        get { max(0, min(8, UserDefaults.standard.integer(forKey: Keys.countInBars))) }
        set { UserDefaults.standard.set(max(0, min(8, newValue)), forKey: Keys.countInBars) }
    }

    public var confirmsDestructiveEdits: Bool {
        get { UserDefaults.standard.bool(forKey: Keys.confirmDestructiveEdits) }
        set { UserDefaults.standard.set(newValue, forKey: Keys.confirmDestructiveEdits) }
    }

    public var configuredPythonPath: String? {
        get { UserDefaults.standard.string(forKey: Keys.pythonInterpreter) }
        set { UserDefaults.standard.set(newValue, forKey: Keys.pythonInterpreter) }
    }

    private var cachedInterpreter: (configured: String?, url: URL?)?

    /// The interpreter to run helper tools with.
    ///
    /// Probing actually executes each candidate, and on a Mac without Apple's
    /// Command Line Tools `/usr/bin/python3` is a stub that can stall for
    /// seconds. The answer is therefore cached and only recomputed when the
    /// configured path changes, so a Settings edit takes effect immediately but
    /// pressing Export Mix does not re-probe every time.
    public var pythonExecutable: URL? {
        let configured = configuredPythonPath
        if let cached = cachedInterpreter, cached.configured == configured {
            return cached.url
        }
        let resolved = ToolPaths.pythonExecutable(configured: configured)
        cachedInterpreter = (configured, resolved)
        return resolved
    }

    /// Forces the next `pythonExecutable` read to probe again. Call after the
    /// user changes the interpreter or installs the tools.
    public func invalidateInterpreterCache() {
        cachedInterpreter = nil
    }

    /// Appends a jargon gloss when explanations are switched on.
    public func help(_ base: String, term: String? = nil) -> String {
        guard let term, explainsMusicTerms, let entry = Glossary.term(term) else { return base }
        return "\(base)\n\n\(entry.name): \(entry.short)"
    }

    // MARK: Support directory

    /// Copies the bundled factory projects, stems, tools and skills into
    /// ~/Library/Application Support/Neon Studio on first launch, and refreshes
    /// the executable tooling on every launch so an app update can't leave stale
    /// Python behind while still never touching the user's own projects.
    private static func prepareSupportRoot(warnings: inout [String]) -> URL {
        let support = FileManager.default
            .urls(for: .applicationSupportDirectory, in: .userDomainMask)
            .first!
            .appendingPathComponent("Neon Studio", isDirectory: true)
        do {
            try FileManager.default.createDirectory(at: support, withIntermediateDirectories: true)
        } catch {
            warnings.append("Couldn't create the Neon Studio folder in Application Support: \(error.localizedDescription)")
            return support
        }

        guard let seed = Bundle.main.resourceURL?.appendingPathComponent("seed", isDirectory: true),
              FileManager.default.fileExists(atPath: seed.path) else {
            warnings.append("This build has no bundled example songs or helper tools, so rendering and analysis won't work.")
            return support
        }
        // User content: only fill gaps.
        copySeed("factory", from: seed, to: support, replaceExistingFiles: false, warnings: &warnings)
        copySeed("data", from: seed, to: support, replaceExistingFiles: false, warnings: &warnings)
        copySeed("exports", from: seed, to: support, replaceExistingFiles: false, warnings: &warnings)
        // The transcript a factory song was built from, so Check My Mix can
        // also ask whether the song matches its description.
        copySeed("songlab", from: seed, to: support, replaceExistingFiles: false, warnings: &warnings)
        // Code: always refresh, so an app update can't leave stale Python behind.
        copySeed("tools", from: seed, to: support, replaceExistingFiles: true, warnings: &warnings)
        copySeed("skills", from: seed, to: support, replaceExistingFiles: true, warnings: &warnings)
        return support
    }

    private static func copySeed(
        _ name: String,
        from seed: URL,
        to support: URL,
        replaceExistingFiles: Bool,
        warnings: inout [String]
    ) {
        let source = seed.appendingPathComponent(name, isDirectory: true)
        let destination = support.appendingPathComponent(name, isDirectory: true)
        guard FileManager.default.fileExists(atPath: source.path) else { return }
        if !FileManager.default.fileExists(atPath: destination.path) {
            do {
                try FileManager.default.copyItem(at: source, to: destination)
            } catch {
                warnings.append("Couldn't set up “\(name)”: \(error.localizedDescription)")
            }
            return
        }
        merge(from: source, to: destination, replaceExistingFiles: replaceExistingFiles, warnings: &warnings)
    }

    private static func merge(
        from source: URL,
        to destination: URL,
        replaceExistingFiles: Bool,
        warnings: inout [String]
    ) {
        guard let urls = try? FileManager.default.contentsOfDirectory(
            at: source,
            includingPropertiesForKeys: [.isDirectoryKey]
        ) else {
            warnings.append("Couldn't read the bundled \(source.lastPathComponent) folder.")
            return
        }
        for item in urls {
            // Never seed Python bytecode caches into the support root.
            if item.lastPathComponent == "__pycache__" { continue }
            let target = destination.appendingPathComponent(item.lastPathComponent)
            let isDirectory = (try? item.resourceValues(forKeys: [.isDirectoryKey]))?.isDirectory == true
            if FileManager.default.fileExists(atPath: target.path) {
                if isDirectory {
                    merge(from: item, to: target, replaceExistingFiles: replaceExistingFiles, warnings: &warnings)
                } else if replaceExistingFiles {
                    do {
                        try FileManager.default.removeItem(at: target)
                        try FileManager.default.copyItem(at: item, to: target)
                    } catch {
                        warnings.append("Couldn't update \(item.lastPathComponent): \(error.localizedDescription)")
                    }
                }
                continue
            }
            do {
                try FileManager.default.copyItem(at: item, to: target)
            } catch {
                warnings.append("Couldn't install \(item.lastPathComponent): \(error.localizedDescription)")
            }
        }
    }
}
