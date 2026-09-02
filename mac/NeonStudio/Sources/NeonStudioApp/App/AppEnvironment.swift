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
        public static let aiEnabled = "NeonStudioAIEnabled"
        public static let aiModel = "NeonStudioAIModel"
    }

    /// Posted after any AI setting changes (on/off, key, model), so status
    /// surfaces can refresh without polling the Keychain.
    public static let aiSettingsChanged = Notification.Name("NeonStudioAISettingsChanged")

    public static func registerDefaults() {
        UserDefaults.standard.register(defaults: [
            Keys.showWelcomeOnLaunch: true,
            // On until the user turns it off. Somebody who already knows what a
            // send is can switch the explanations off in Settings; somebody who
            // doesn't should never be left guessing.
            Keys.explainMusicTerms: true,
            Keys.confirmDestructiveEdits: true,
            // One bar is enough to catch a downbeat without being a wait.
            Keys.countInBars: 1,
            // On by default: with no key the tools fall back to their rules
            // and say so, so "on" costs nothing until a key is added.
            Keys.aiEnabled: true
        ])
    }

    // MARK: AI assistance (docs/ai.md)

    private static let aiKeychain = KeychainStore(service: "studio.neon.ai", account: "gemini")
    /// Only a key found in the Keychain is remembered. The config file is
    /// re-read on every call (one small read), so a key dropped into it,
    /// edited, or removed while the app is running is seen by the very next
    /// `toolEnvironment()` call, and "no key" is never cached.
    private var cachedKeychainKey: String?

    /// Whether the tools may ask a language model. Has no effect without a
    /// key; every feature works from built-in rules either way.
    public var aiEnabled: Bool {
        get { UserDefaults.standard.bool(forKey: Keys.aiEnabled) }
        set {
            UserDefaults.standard.set(newValue, forKey: Keys.aiEnabled)
            NotificationCenter.default.post(name: AppEnvironment.aiSettingsChanged, object: self)
        }
    }

    /// Optional model override handed to the tools as `NEON_AI_MODEL`.
    public var aiModel: String? {
        get {
            let value = UserDefaults.standard.string(forKey: Keys.aiModel)?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            return value.isEmpty ? nil : value
        }
        set {
            let value = newValue?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            if value.isEmpty {
                UserDefaults.standard.removeObject(forKey: Keys.aiModel)
            } else {
                UserDefaults.standard.set(value, forKey: Keys.aiModel)
            }
            NotificationCenter.default.post(name: AppEnvironment.aiSettingsChanged, object: self)
        }
    }

    /// The Gemini key: the Keychain first, then the CLI's config file so a key
    /// placed there by hand works without the UI. Never logged, never written
    /// anywhere but the Keychain.
    public var geminiAPIKey: String? { resolveAIKey().value }

    public var aiKeySource: AIKeySource { resolveAIKey().source }

    public var hasAIKey: Bool { geminiAPIKey != nil }

    /// On, and there is a key to use.
    public var isAIAvailable: Bool { aiEnabled && hasAIKey }

    /// Saves to the Keychain; an empty string removes the stored key (a key in
    /// the config file, if any, then takes over again).
    @discardableResult
    public func setGeminiAPIKey(_ key: String) -> Bool {
        let ok = AppEnvironment.aiKeychain.write(key)
        cachedKeychainKey = nil
        NotificationCenter.default.post(name: AppEnvironment.aiSettingsChanged, object: self)
        return ok
    }

    /// Forces the next key read to hit the Keychain again. The file is read
    /// fresh every time anyway; the app delegate calls this on activation so a
    /// key added or removed in Keychain Access while the app was in the
    /// background is picked up too.
    public func invalidateAIKeyCache() {
        cachedKeychainKey = nil
    }

    private func resolveAIKey() -> (value: String?, source: AIKeySource) {
        if let cached = cachedKeychainKey { return (cached, .keychain) }
        if let stored = AppEnvironment.aiKeychain.read() {
            cachedKeychainKey = stored
            return (stored, .keychain)
        }
        // Not cached, deliberately: the file is the CLI's, and people edit it
        // by hand while the app is open.
        if let fromFile = ToolEnvironment.readFallbackKey() {
            return (fromFile, .file(ToolEnvironment.fallbackKeyFile))
        }
        return (nil, .none)
    }

    /// The environment every helper tool is launched with. `GEMINI_API_KEY`
    /// only while AI is on; `NEON_AI=off` when it is off; `NEON_AI_MODEL` when
    /// a model is chosen. Merged over the process environment by `ToolRunner`.
    public func toolEnvironment() -> [String: String] {
        ToolEnvironment.make(enabled: aiEnabled, apiKey: aiEnabled ? geminiAPIKey : nil, model: aiModel)
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
