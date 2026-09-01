import Foundation

/// A minimal assertion harness.
///
/// XCTest and swift-testing both require Xcode, and Neon Studio builds with
/// Apple's Command Line Tools alone, so `swift test` cannot run here. This gives
/// the same thing that matters — named cases, real assertions, a readable
/// report, and a non-zero exit code on failure — with no dependency beyond the
/// Swift standard library.
public final class TestRunner {
    public struct Failure {
        let test: String
        let message: String
        let file: String
        let line: Int
    }

    public static let shared = TestRunner()

    private var failures: [Failure] = []
    private var currentTest = ""
    private var passed = 0
    private var total = 0

    private init() {}

    public func test(_ name: String, _ body: () throws -> Void) {
        currentTest = name
        total += 1
        let before = failures.count
        do {
            try body()
        } catch {
            record("threw an unexpected error: \(error)", file: #file, line: #line)
        }
        if failures.count == before {
            passed += 1
            print("  ✓ \(name)")
        } else {
            print("  ✗ \(name)")
        }
    }

    func record(_ message: String, file: String, line: Int) {
        failures.append(Failure(
            test: currentTest,
            message: message,
            file: URL(fileURLWithPath: file).lastPathComponent,
            line: line
        ))
    }

    public func section(_ name: String) {
        print("\n\(name)")
    }

    /// Prints the summary and exits with the right status for a shell or CI.
    public func finish() -> Never {
        print("\n" + String(repeating: "─", count: 60))
        if failures.isEmpty {
            print("\(passed)/\(total) tests passed")
            exit(0)
        }
        print("\(passed)/\(total) tests passed, \(failures.count) assertion failure\(failures.count == 1 ? "" : "s"):\n")
        for failure in failures {
            print("  \(failure.test)")
            print("    \(failure.file):\(failure.line) — \(failure.message)")
        }
        exit(1)
    }
}

// MARK: - Assertions

public func expect(
    _ condition: @autoclosure () -> Bool,
    _ message: @autoclosure () -> String,
    file: String = #file,
    line: Int = #line
) {
    if !condition() {
        TestRunner.shared.record(message(), file: file, line: line)
    }
}

public func expectEqual<T: Equatable>(
    _ actual: @autoclosure () -> T,
    _ expected: @autoclosure () -> T,
    _ message: @autoclosure () -> String = "",
    file: String = #file,
    line: Int = #line
) {
    let a = actual()
    let b = expected()
    if a != b {
        let hint = message().isEmpty ? "" : " — \(message())"
        TestRunner.shared.record("expected \(b), got \(a)\(hint)", file: file, line: line)
    }
}

public func expectClose(
    _ actual: @autoclosure () -> Double,
    _ expected: @autoclosure () -> Double,
    accuracy: Double = 0.0001,
    _ message: @autoclosure () -> String = "",
    file: String = #file,
    line: Int = #line
) {
    let a = actual()
    let b = expected()
    if !(abs(a - b) <= accuracy) {
        let hint = message().isEmpty ? "" : " — \(message())"
        TestRunner.shared.record("expected \(b) ± \(accuracy), got \(a)\(hint)", file: file, line: line)
    }
}

public func expectTrue(
    _ condition: @autoclosure () -> Bool,
    _ message: @autoclosure () -> String = "expected true",
    file: String = #file,
    line: Int = #line
) {
    expect(condition(), message(), file: file, line: line)
}

public func expectFalse(
    _ condition: @autoclosure () -> Bool,
    _ message: @autoclosure () -> String = "expected false",
    file: String = #file,
    line: Int = #line
) {
    expect(!condition(), message(), file: file, line: line)
}

public func expectNil<T>(
    _ value: @autoclosure () -> T?,
    _ message: @autoclosure () -> String = "expected nil",
    file: String = #file,
    line: Int = #line
) {
    if let actual = value() {
        TestRunner.shared.record("\(message()), got \(actual)", file: file, line: line)
    }
}

public func expectNotNil<T>(
    _ value: @autoclosure () -> T?,
    _ message: @autoclosure () -> String = "expected a value",
    file: String = #file,
    line: Int = #line
) {
    if value() == nil {
        TestRunner.shared.record(message(), file: file, line: line)
    }
}

public func expectThrows<T>(
    _ body: @autoclosure () throws -> T,
    _ message: @autoclosure () -> String = "expected an error",
    file: String = #file,
    line: Int = #line
) {
    do {
        _ = try body()
        TestRunner.shared.record(message(), file: file, line: line)
    } catch {
        // expected
    }
}

// MARK: - Temporary directories

/// A unique scratch directory that removes itself.
public struct TempDirectory {
    public let url: URL

    public init(_ label: String = "neon-tests") {
        url = FileManager.default.temporaryDirectory
            .appendingPathComponent("\(label)-\(UUID().uuidString)", isDirectory: true)
        try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
    }

    public func subdirectory(_ path: String) -> URL {
        let directory = url.appendingPathComponent(path, isDirectory: true)
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        return directory
    }

    public func write(_ data: Data, to path: String) {
        let target = url.appendingPathComponent(path)
        try? FileManager.default.createDirectory(
            at: target.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try? data.write(to: target)
    }

    public func write(_ text: String, to path: String) {
        write(Data(text.utf8), to: path)
    }

    public func cleanUp() {
        try? FileManager.default.removeItem(at: url)
    }
}
