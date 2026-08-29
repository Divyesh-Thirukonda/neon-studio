import Foundation

/// Finds a usable Python interpreter.
///
/// The old build hardcoded `/usr/bin/python3`. On a Mac without Apple's Command
/// Line Tools that path exists but is a stub that pops a system installer, so
/// every render, sound check, and transcript import failed with an opaque error.
/// Now the app prefers an explicitly configured interpreter, then probes the
/// usual locations, and tells the user exactly what to do when none work.
public enum ToolPaths {
    public static let interpreterDefaultsKey = "NeonStudioPythonInterpreter"

    /// Candidate interpreters in preference order.
    public static let candidates: [String] = [
        "/usr/bin/python3",
        "/opt/homebrew/bin/python3",
        "/usr/local/bin/python3",
        "/opt/homebrew/opt/python@3.12/bin/python3",
        "/Library/Frameworks/Python.framework/Versions/Current/bin/python3"
    ]

    /// A configured interpreter wins if it still runs. Otherwise the first
    /// candidate that actually reports a version is used.
    public static func pythonExecutable(configured: String? = nil) -> URL? {
        if let configured, !configured.trimmingCharacters(in: .whitespaces).isEmpty {
            let url = URL(fileURLWithPath: configured)
            if isWorkingInterpreter(url) { return url }
        }
        for path in candidates {
            let url = URL(fileURLWithPath: path)
            if isWorkingInterpreter(url) { return url }
        }
        return nil
    }

    /// `/usr/bin/python3` exists on stock macOS but only as a shim that triggers
    /// the Command Line Tools installer, so existence alone is not enough —
    /// the interpreter has to actually answer `--version`.
    public static func isWorkingInterpreter(_ url: URL) -> Bool {
        guard FileManager.default.isExecutableFile(atPath: url.path) else { return false }
        let process = Process()
        process.executableURL = url
        process.arguments = ["--version"]
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe
        do {
            try process.run()
        } catch {
            return false
        }
        // Never let a hung shim block launch.
        let deadline = Date().addingTimeInterval(4)
        while process.isRunning && Date() < deadline {
            usleep(20_000)
        }
        if process.isRunning {
            process.terminate()
            return false
        }
        _ = pipe.fileHandleForReading.readDataToEndOfFile()
        return process.terminationStatus == 0
    }

    public static let afconvertURL = URL(fileURLWithPath: "/usr/bin/afconvert")

    public static var afconvertAvailable: Bool {
        FileManager.default.isExecutableFile(atPath: afconvertURL.path)
    }
}
