import AppKit
import NeonStudioKit

/// A `.neon.json` project, as a real macOS document.
///
/// Making this an `NSDocument` is the architectural change that removes most of
/// the app's hand-rolled machinery. The previous single-window controller
/// re-implemented open, save, import, delete, autosave and undo itself — badly —
/// while still not offering the things users expect from any Mac app. Adopting
/// `NSDocument` deletes that code and gets, for free and correct:
///
/// * File ▸ Open Recent, and double-clicking a `.neon.json` in the Finder
/// * Save, Save As, Duplicate, Rename, Move To, Revert To Saved
/// * autosave-in-place plus Versions (browse and restore earlier saves)
/// * the modified dot and proxy icon in the title bar, and drag-out of the proxy
/// * "You have unsaved changes" on close and on quit
/// * several projects open at once, each in its own window
/// * window and split-position restoration across launches
///
/// Undo is `NSUndoManager`, so the Edit menu reads "Undo Set Tempo" rather than
/// a bare "Undo", and history is per-document instead of one global stack that
/// was thrown away whenever another project was opened.
/// `@objc(NeonDocument)` pins the Objective-C class name, because Info.plist's
/// `NSDocumentClass` is resolved by name and Swift would otherwise mangle it to
/// `NeonStudioApp.NeonDocument`.
@objc(NeonDocument)
public final class NeonDocument: NSDocument {

    public static let documentTypeName = "studio.neon.project"

    /// The whole editable state. Mutate through `mutate(_:_:)` so undo and the
    /// change count stay correct.
    public private(set) var project: LocalProject = NeonDocument.emptyProject()

    /// Callbacks fired after any change to `project`. The window controller and
    /// its panels register here rather than polling.
    public var onProjectChanged: [(LocalProject) -> Void] = []

    /// Set when the document was opened from the project library rather than
    /// from a file the user picked, so "Reveal in Finder" can find it again.
    public var libraryURL: URL?

    private let store: ProjectStore

    public override init() {
        self.store = AppEnvironment.shared.store
        super.init()
        hasUndoManager = true
    }

    // MARK: NSDocument

    public override class var autosavesInPlace: Bool { true }

    public override class var preservesVersions: Bool { true }

    public override var displayName: String! {
        get { fileURL == nil ? project.name : super.displayName }
        set { super.displayName = newValue }
    }

    public override func makeWindowControllers() {
        let controller = DocumentWindowController(document: self)
        addWindowController(controller)
    }

    public override func data(ofType typeName: String) throws -> Data {
        var snapshot = project
        snapshot.updatedAt = nowISO()
        return try store.encode(snapshot)
    }

    public override func read(from data: Data, ofType typeName: String) throws {
        let loaded = try store.decode(data, fallbackName: fileURL?.lastPathComponent ?? "project.neon.json")
        project = loaded
        // Reading replaces the document wholesale, so previous undo steps no
        // longer describe anything real.
        undoManager?.removeAllActions()
        notify()
    }

    public override func writableTypes(for saveOperation: NSDocument.SaveOperationType) -> [String] {
        [NeonDocument.documentTypeName]
    }

    /// Keeps the double extension intact when the user does Save As, so the file
    /// stays `something.neon.json` and not `something.json`.
    public override func prepareSavePanel(_ savePanel: NSSavePanel) -> Bool {
        savePanel.allowedContentTypes = []
        savePanel.allowsOtherFileTypes = true
        savePanel.isExtensionHidden = false
        if savePanel.nameFieldStringValue.isEmpty || !savePanel.nameFieldStringValue.hasSuffix(".neon.json") {
            let base = safeProjectId(project.name.lowercased())
            savePanel.nameFieldStringValue = "\(base).neon.json"
        }
        savePanel.message = "Neon Studio projects are plain text, so they open on any Mac and work with version control."
        return true
    }

    // MARK: Editing

    /// The single entry point for every change that should be undoable.
    ///
    /// - Parameter actionName: user-facing, appears in the Edit menu as
    ///   "Undo <actionName>". Written in title case, e.g. "Set Tempo".
    public func mutate(_ actionName: String, _ body: (inout LocalProject) -> Void) {
        var next = project
        body(&next)
        next.updatedAt = nowISO()
        apply(ProjectNormalizer.normalize(next), actionName: actionName)
    }

    private func apply(_ next: LocalProject, actionName: String) {
        guard next != project else { return }
        let previous = project
        undoManager?.registerUndo(withTarget: self) { document in
            document.apply(previous, actionName: actionName)
        }
        undoManager?.setActionName(actionName)
        project = next
        notify()
    }

    /// Selection and view state persist with the project but are not edits.
    /// Routing them through `mutate` would flood the undo stack with "Undo
    /// Select Track" and mark the document dirty every time somebody clicked —
    /// which is exactly what the old build did, rewriting the entire JSON file
    /// to disk on every single click.
    public func updateTransientState(_ body: (inout LocalProject) -> Void) {
        var next = project
        body(&next)
        guard next != project else { return }
        project = next
        notify()
    }

    /// Replaces the document wholesale, for tools that rewrite the project
    /// (the DAW Agent). Undoable as one step.
    public func replaceProject(_ next: LocalProject, actionName: String) {
        var incoming = ProjectNormalizer.normalize(next)
        // Keep the identity of the open document; a tool writing to a temp file
        // must not be able to rename or re-id the project behind the user's back.
        incoming.id = project.id
        incoming.name = project.name
        incoming.createdAt = project.createdAt
        incoming.updatedAt = nowISO()
        apply(incoming, actionName: actionName)
    }

    private func notify() {
        let snapshot = project
        onProjectChanged.forEach { $0(snapshot) }
    }

    // MARK: Factories

    public static func emptyProject(named name: String = "Untitled Song") -> LocalProject {
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
                Effect(id: "eq", name: "EQ", active: false, amount: 0.35),
                Effect(id: "comp", name: "Compressor", active: false, amount: 0.35)
            ],
            sampleEdit: normalizeSampleEdit(nil)
        )
        return ProjectNormalizer.normalize(LocalProject(
            id: makeId("project"),
            name: name,
            createdAt: now,
            updatedAt: now,
            description: "A new Neon Studio project",
            snapshot: ProjectSnapshot(
                bpm: 120,
                tracks: [track],
                selectedTrackId: track.id,
                activeView: WorkView.playlist.rawValue
            )
        ))
    }

    /// Builds a document around an existing project loaded from the library.
    public static func makeUntitled(with project: LocalProject, libraryURL: URL?) throws -> NeonDocument {
        let document = NeonDocument()
        document.project = ProjectNormalizer.normalize(project)
        document.libraryURL = libraryURL
        document.fileType = NeonDocument.documentTypeName
        document.makeWindowControllers()
        return document
    }
}
