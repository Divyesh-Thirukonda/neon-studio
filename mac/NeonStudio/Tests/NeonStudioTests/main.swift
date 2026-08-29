import Foundation

// Entry point for `swift run NeonStudioTests`. Each suite registers its cases
// with the shared runner; `finish()` prints a summary and sets the exit status.
print("Neon Studio — NeonStudioKit tests")

ModelTests.run()
StoreTests.run()
AudioTests.run()

TestRunner.shared.finish()
