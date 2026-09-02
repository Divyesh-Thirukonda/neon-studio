import Foundation
import Security

// The app's side of `docs/ai.md`. Everything here is plumbing: where the key
// lives, which environment variables the tools read, and how to describe the
// `ai` block a tool prints. The judgement itself stays in the Python tools.

// MARK: - Keychain

/// A generic-password item in the login keychain. The Gemini key is the only
/// secret the app holds, and it must never land in UserDefaults, a project
/// file, a spec, or a log.
public struct KeychainStore {
    public let service: String
    public let account: String

    public init(service: String, account: String) {
        self.service = service
        self.account = account
    }

    private var query: [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ]
    }

    public func read() -> String? {
        var request = query
        request[kSecReturnData as String] = true
        request[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        let status = SecItemCopyMatching(request as CFDictionary, &item)
        guard status == errSecSuccess, let data = item as? Data else { return nil }
        let value = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return value.isEmpty ? nil : value
    }

    /// Stores `value`, replacing any existing item. An empty value deletes.
    @discardableResult
    public func write(_ value: String) -> Bool {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return delete() }
        let data = Data(trimmed.utf8)
        let update = SecItemUpdate(query as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        if update == errSecSuccess { return true }
        if update != errSecItemNotFound {
            // A stale or unreadable item: start over rather than fail silently.
            SecItemDelete(query as CFDictionary)
        }
        var insert = query
        insert[kSecValueData as String] = data
        insert[kSecAttrLabel as String] = "Neon Studio AI key"
        return SecItemAdd(insert as CFDictionary, nil) == errSecSuccess
    }

    @discardableResult
    public func delete() -> Bool {
        let status = SecItemDelete(query as CFDictionary)
        return status == errSecSuccess || status == errSecItemNotFound
    }
}

// MARK: - Environment for the tools

/// Where the key the tools will use came from, for the Settings status line.
public enum AIKeySource: Equatable {
    case keychain
    /// `~/.config/neon-studio/gemini_api_key`, the same file the CLI reads, so
    /// a key placed there by hand works without touching the UI.
    case file(URL)
    case none

    public var description: String {
        switch self {
        case .keychain: return "stored in your Keychain"
        case .file(let url): return "read from \(url.path)"
        case .none: return "not set"
        }
    }
}

public enum ToolEnvironment {
    /// The variables `tools/llm.py` reads, and nothing else.
    ///
    /// - Off: `NEON_AI=off` and no key, so a key already in the process
    ///   environment or in the config file cannot switch the model back on.
    /// - On: the key (when there is one) and the model override (when set).
    ///   With no key the tools fall back to their rules and say so; the app
    ///   never fails a feature for want of a model.
    public static func make(enabled: Bool, apiKey: String?, model: String?) -> [String: String] {
        guard enabled else { return ["NEON_AI": "off"] }
        var environment: [String: String] = [:]
        if let apiKey, !apiKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            environment["GEMINI_API_KEY"] = apiKey.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        if let model, !model.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            environment["NEON_AI_MODEL"] = model.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        return environment
    }

    /// The CLI's config file, honoured as a fallback so a key placed there by
    /// hand (or by another tool) counts without the UI.
    public static var fallbackKeyFile: URL {
        let base: URL
        if let override = ProcessInfo.processInfo.environment["NEON_CONFIG_DIR"], !override.isEmpty {
            base = URL(fileURLWithPath: override, isDirectory: true)
        } else {
            base = FileManager.default.homeDirectoryForCurrentUser
                .appendingPathComponent(".config", isDirectory: true)
                .appendingPathComponent("neon-studio", isDirectory: true)
        }
        return base.appendingPathComponent("gemini_api_key")
    }

    public static func readFallbackKey() -> String? {
        guard let text = try? String(contentsOf: fallbackKeyFile, encoding: .utf8) else { return nil }
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }
}

// MARK: - The `ai` block a tool prints

/// `{"used": bool, "provider": ..., "model": ..., "note": ...}` — what every
/// model-capable tool puts in its JSON, per `docs/ai.md`. Read defensively: a
/// tool that has not been wired yet prints no block at all, and that is not an
/// error, it just means there is nothing to say.
public struct AIProvenance: Equatable {
    public let used: Bool
    public let provider: String?
    public let model: String?
    public let note: String

    public init(used: Bool, provider: String?, model: String?, note: String) {
        self.used = used
        self.provider = provider
        self.model = model
        self.note = note
    }

    /// The block under `json["ai"]`, or nil when there is none.
    public static func read(from json: [String: Any]) -> AIProvenance? {
        guard let block = json["ai"] as? [String: Any] else { return nil }
        let used: Bool
        if let flag = block["used"] as? Bool {
            used = flag
        } else if let number = block["used"] as? NSNumber {
            used = number.boolValue
        } else {
            used = false
        }
        func string(_ value: Any?) -> String? {
            guard let text = value as? String else { return nil }
            let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
            return trimmed.isEmpty ? nil : trimmed
        }
        return AIProvenance(
            used: used,
            provider: string(block["provider"]),
            model: string(block["model"]),
            note: string(block["note"]) ?? ""
        )
    }

    /// "via gemini-flash-latest" or "offline rules — no API key…". Short enough
    /// for a status bar; the full note is in the tool's JSON for the log.
    public var statusSuffix: String {
        if used {
            return "via \(model ?? provider ?? "the model")"
        }
        let reason = AIProvenance.shorten(note, limit: 90)
        return reason.isEmpty ? "offline rules" : "offline rules — \(reason)"
    }

    /// The line a report window shows under its findings.
    public var footerLine: String {
        if used {
            let who = model ?? provider ?? "a language model"
            return "Written with \(who). Every measurement is from the built-in checks; the model wrote the words."
        }
        let reason = AIProvenance.shorten(note, limit: 140)
        return reason.isEmpty
            ? "Built-in rules only; no language model was used."
            : "Built-in rules only — \(reason)."
    }

    /// `message` with the provenance appended, or unchanged when the tool
    /// printed no `ai` block.
    public static func annotate(_ message: String, from json: [String: Any]) -> String {
        guard let provenance = read(from: json) else { return message }
        return "\(message) (\(provenance.statusSuffix))"
    }

    private static func shorten(_ text: String, limit: Int) -> String {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.count > limit else { return trimmed }
        return String(trimmed.prefix(limit - 1)).trimmingCharacters(in: .whitespaces) + "…"
    }
}
