import AppKit
import NeonStudioKit

/// What a human-in-the-loop feature needs from the window that owns it.
///
/// The hum-to-melody flow, the variations picker, the plain-language change
/// panel and the listening session all follow the same shape: run a helper
/// tool against the current project, play something back to the user, and
/// land the result as one undoable edit. They get exactly that surface and
/// nothing else, so they cannot reach into the window controller's internals
/// and each can be built and tested on its own.
public protocol ToolHost: AnyObject {
    var window: NSWindow? { get }
    var project: LocalProject { get }
    var store: ProjectStore { get }
    var isPlaying: Bool { get }

    /// Runs one of the Python tools off the main thread. `completion` is
    /// called on the main queue exactly once. Progress and errors are reported
    /// through the status bar automatically; the caller only handles success.
    func runTool(
        name: String,
        progressMessage: String,
        arguments: [String],
        completion: @escaping (Result<ToolResult, Error>) -> Void
    )

    /// Writes the current project to a temporary `.neon.json` so a tool can
    /// read it. The caller removes it when done.
    func exportProjectToTemporaryFile() throws -> URL

    /// One undoable change, named for the Edit menu ("Undo Insert Hummed Melody").
    func edit(_ actionName: String, _ body: (inout LocalProject) -> Void)

    /// Replaces the whole project as one undoable step, keeping its identity.
    func replaceProject(with next: LocalProject, actionName: String)

    /// Plays a bar range on repeat so the user can listen while answering a
    /// question or comparing an option. Stops any current playback first.
    func playSection(startBar: Double, bars: Double)
    func stopPlayback()

    /// Records a take from the microphone with the count-in the user chose,
    /// then hands back the file WITHOUT adding it to the project. The caller
    /// decides what to do with it. `completion` receives nil when the user
    /// cancelled or nothing was captured.
    func recordTake(progressMessage: String, completion: @escaping (URL?) -> Void)

    /// Stops a recording started with `recordTake`, triggering its completion.
    func finishTake()
}
