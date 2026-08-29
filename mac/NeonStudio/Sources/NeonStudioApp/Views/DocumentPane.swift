import AppKit
import NeonStudioKit

/// One of the three columns in a document window.
///
/// The window controller owns the state; panes only read from their `host` and
/// write back through it. `refresh()` is called after every document change and
/// must be cheap enough to run on each edit.
public protocol DocumentPane: NSViewController {
    var host: EditorHost? { get set }
    func refresh()
    func playheadDidMove(to bar: Double)
}

public extension DocumentPane {
    func playheadDidMove(to bar: Double) {}
}

/// A view that repaints its background when the system appearance changes.
///
/// `viewDidChangeEffectiveAppearance` is an `NSView` method, not an
/// `NSViewController` one, so the hook has to live here.
public final class ThemedBackgroundView: NSView {
    private let colorProvider: () -> NSColor

    /// - Parameter color: read on every appearance change, so passing a `Theme`
    ///   colour is enough to make the view follow Light/Dark and Increase Contrast.
    public init(color: @escaping () -> NSColor = { Theme.app }) {
        colorProvider = color
        super.init(frame: .zero)
        translatesAutoresizingMaskIntoConstraints = false
        wantsLayer = true
        applyBackground()
    }

    public override convenience init(frame frameRect: NSRect) {
        self.init()
        self.frame = frameRect
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    public override func viewDidChangeEffectiveAppearance() {
        super.viewDidChangeEffectiveAppearance()
        applyBackground()
    }

    private func applyBackground() {
        effectiveAppearance.performAsCurrentDrawingAppearance { [weak self] in
            guard let self else { return }
            self.layer?.backgroundColor = self.colorProvider().cgColor
        }
    }
}

/// Base class that gives panes a themed background and the host plumbing, so
/// each concrete pane only implements its own content.
public class BaseDocumentPane: NSViewController, DocumentPane {
    public weak var host: EditorHost? {
        didSet { refresh() }
    }

    public override func loadView() {
        let root = ThemedBackgroundView { Theme.app }
        root.frame = NSRect(x: 0, y: 0, width: 320, height: 480)
        view = root
    }

    public func refresh() {}
    public func playheadDidMove(to bar: Double) {}
}
