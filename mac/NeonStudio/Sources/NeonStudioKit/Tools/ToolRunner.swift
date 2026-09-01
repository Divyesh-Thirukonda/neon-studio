import Foundation

public struct ToolResult: Sendable {
    public let standardOutput: String
    public let standardError: String
    public let exitCode: Int32

    public init(standardOutput: String, standardError: String, exitCode: Int32) {
        self.standardOutput = standardOutput
        self.standardError = standardError
        self.exitCode = exitCode
    }

    public var succeeded: Bool { exitCode == 0 }

    /// The tools in `tools/` print progress to stdout and finish with a single
    /// JSON object on the last non-empty line.
    public var lastJSONObject: [String: Any] {
        for line in standardOutput.split(separator: "\n").reversed() {
            let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
            guard trimmed.hasPrefix("{"), let data = trimmed.data(using: .utf8) else { continue }
            if let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                return object
            }
        }
        return [:]
    }
}

public enum ToolError: LocalizedError {
    case missingExecutable(String)
    case missingScript(URL)
    case failed(name: String, exitCode: Int32, standardError: String)
    case cancelled(name: String)
    case noJSON(name: String)

    public var errorDescription: String? {
        switch self {
        case .missingExecutable(let path):
            return "Python isn't available at \(path)."
        case .missingScript(let url):
            return "The helper script \(url.lastPathComponent) is missing."
        case .failed(let name, let code, _):
            return "\(name) didn't finish (exit code \(code))."
        case .cancelled(let name):
            return "\(name) was cancelled."
        case .noJSON(let name):
            return "\(name) finished but didn't return a result."
        }
    }

    public var recoverySuggestion: String? {
        switch self {
        case .missingExecutable:
            return "Neon Studio uses Python for rendering and analysis. Install Apple's Command Line Tools by running \"xcode-select --install\" in Terminal, then set the interpreter under Neon Studio ▸ Settings."
        case .missingScript:
            return "Reinstall or rebuild Neon Studio so the bundled tools are copied into place."
        case .failed(_, _, let stderr):
            let detail = stderr.trimmingCharacters(in: .whitespacesAndNewlines)
            return detail.isEmpty ? "Check the Activity log for details." : String(detail.suffix(600))
        case .cancelled:
            return nil
        case .noJSON:
            return "Check the Activity log for the tool's raw output."
        }
    }
}

/// Runs the bundled Python tools off the main thread.
///
/// The previous implementation called `waitUntilExit()` on the main thread and
/// only then drained the pipes, which froze the whole UI for the duration and
/// could deadlock outright once a tool wrote more than one pipe buffer of
/// output. Here both pipes are drained concurrently while the process runs, and
/// the caller gets progress lines plus a cancel handle.
public final class ToolRunner {
    public struct Handle {
        fileprivate let process: Process
        public func cancel() {
            if process.isRunning { process.terminate() }
        }
    }

    private let queue = DispatchQueue(label: "studio.neon.toolrunner", qos: .userInitiated)

    public init() {}

    /// - Parameters:
    ///   - onOutputLine: called on the main queue for each line the tool prints,
    ///     so long-running work can show real progress instead of a frozen window.
    ///   - completion: called on the main queue exactly once.
    /// - Returns: a handle the caller can use to cancel.
    @discardableResult
    public func run(
        name: String,
        executable: URL,
        arguments: [String],
        currentDirectory: URL,
        environment: [String: String]? = nil,
        onOutputLine: ((String) -> Void)? = nil,
        completion: @escaping (Result<ToolResult, Error>) -> Void
    ) -> Handle? {
        guard FileManager.default.isExecutableFile(atPath: executable.path) else {
            DispatchQueue.main.async { completion(.failure(ToolError.missingExecutable(executable.path))) }
            return nil
        }
        if let script = arguments.first, script.hasSuffix(".py"),
           !FileManager.default.fileExists(atPath: script) {
            DispatchQueue.main.async { completion(.failure(ToolError.missingScript(URL(fileURLWithPath: script)))) }
            return nil
        }

        let process = Process()
        process.executableURL = executable
        process.arguments = arguments
        process.currentDirectoryURL = currentDirectory
        if let environment {
            process.environment = ProcessInfo.processInfo.environment.merging(environment) { _, new in new }
        }

        let outPipe = Pipe()
        let errPipe = Pipe()
        process.standardOutput = outPipe
        process.standardError = errPipe

        queue.async {
            let group = DispatchGroup()
            let lock = NSLock()
            var stdoutText = ""
            var stderrText = ""

            // Drain both pipes concurrently with execution. Reading only after
            // waitUntilExit() deadlocks as soon as a child fills the 64 KB pipe.
            func drain(_ handle: FileHandle, into sink: @escaping (String) -> Void) {
                group.enter()
                DispatchQueue.global(qos: .utility).async {
                    var pending = ""
                    while true {
                        let chunk = handle.availableData
                        if chunk.isEmpty { break }
                        guard let text = String(data: chunk, encoding: .utf8) else { continue }
                        sink(text)
                        pending += text
                        while let newline = pending.firstIndex(of: "\n") {
                            let line = String(pending[pending.startIndex..<newline])
                            pending = String(pending[pending.index(after: newline)...])
                            let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
                            if !trimmed.isEmpty, let onOutputLine {
                                DispatchQueue.main.async { onOutputLine(trimmed) }
                            }
                        }
                    }
                    group.leave()
                }
            }

            drain(outPipe.fileHandleForReading) { text in
                lock.lock(); stdoutText += text; lock.unlock()
            }
            drain(errPipe.fileHandleForReading) { text in
                lock.lock(); stderrText += text; lock.unlock()
            }

            do {
                try process.run()
            } catch {
                DispatchQueue.main.async { completion(.failure(error)) }
                return
            }

            process.waitUntilExit()
            group.wait()

            lock.lock()
            let result = ToolResult(
                standardOutput: stdoutText,
                standardError: stderrText,
                exitCode: process.terminationStatus
            )
            lock.unlock()

            DispatchQueue.main.async {
                if process.terminationReason == .uncaughtSignal {
                    completion(.failure(ToolError.cancelled(name: name)))
                } else if result.succeeded {
                    completion(.success(result))
                } else {
                    completion(.failure(ToolError.failed(
                        name: name,
                        exitCode: result.exitCode,
                        standardError: result.standardError
                    )))
                }
            }
        }

        return Handle(process: process)
    }
}
