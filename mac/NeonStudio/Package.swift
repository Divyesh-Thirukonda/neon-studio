// swift-tools-version:5.9
import PackageDescription

// Note on testing: the test target is a plain executable, not a `.testTarget`.
// XCTest and swift-testing both ship with Xcode, and this project is built with
// Apple's Command Line Tools alone (`swift build`, no .xcodeproj). A `swift test`
// invocation therefore fails with "no such module 'XCTest'" on the toolchain the
// project actually documents. `Tests/NeonStudioTests` uses a small assertion
// harness instead, runs with `swift run NeonStudioTests`, and exits non-zero on
// failure so it works in CI and in a plain terminal.
let package = Package(
    name: "NeonStudio",
    platforms: [.macOS(.v14)],
    targets: [
        // Pure logic: model, persistence, audio transport, subprocess tooling.
        // No AppKit view code lives here so it stays testable.
        .target(
            name: "NeonStudioKit",
            path: "Sources/NeonStudioKit"
        ),
        // The AppKit application itself.
        .executableTarget(
            name: "NeonStudioApp",
            dependencies: ["NeonStudioKit"],
            path: "Sources/NeonStudioApp"
        ),
        .executableTarget(
            name: "NeonStudioTests",
            dependencies: ["NeonStudioKit"],
            path: "Tests/NeonStudioTests"
        )
    ]
)
