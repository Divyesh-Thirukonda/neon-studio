import AppKit
import NeonStudioKit

/// The contract between an editor canvas and the window that owns it.
///
/// Every canvas reads state through this and writes through `edit`, so there is
/// exactly one path for a change: canvas → host → document → undo → callbacks →
/// every canvas refreshes. Previously each view mutated shared controller state
/// directly and the panels could disagree about what was selected.
public protocol EditorHost: AnyObject {
    var project: LocalProject { get }
    var store: ProjectStore { get }
    var selectedTrackId: String { get }
    var selectedClipId: String { get }
    var activeTool: ToolId { get }
    var playheadBar: Double { get }
    var isPlaying: Bool { get }

    func selectTrack(_ trackId: String)
    func selectClip(trackId: String, clipId: String)
    func clearClipSelection()

    /// Records one undoable change. `actionName` is title case and appears in
    /// the Edit menu, e.g. "Move Clip" → "Undo Move Clip".
    func edit(_ actionName: String, _ body: (inout LocalProject) -> Void)

    func seek(toBar bar: Double)
    func status(_ message: String)
    func requestFocus(on view: WorkView)
}

public extension EditorHost {
    var selectedTrack: Track? {
        project.track(id: selectedTrackId) ?? project.snapshot.tracks.first
    }

    var snapValue: SnapValue {
        SnapValue.parse(project.snapshot.snap)
    }
}

/// A canvas that draws part of a project. The window controller refreshes all of
/// them together whenever the document changes.
public protocol EditorCanvas: NSView {
    var host: EditorHost? { get set }
    /// Re-read everything from `host` and redraw.
    func refresh()
    /// Called ~30x/second while the transport runs, for playhead-only redraws
    /// that must not tear down the whole view.
    func playheadDidMove(to bar: Double)
    /// The size this canvas wants inside a scroll view whose visible area is
    /// `visible`. Canvases that never scroll can use the default.
    func contentSize(fittingVisible visible: NSSize) -> NSSize
}

public extension EditorCanvas {
    func playheadDidMove(to bar: Double) {}
    func contentSize(fittingVisible visible: NSSize) -> NSSize { visible }
}

// MARK: - Shared geometry

/// Timeline layout maths, shared by the arrangement canvas and the automation
/// editor so their grids line up exactly.
///
/// Hit-testing and drawing both go through this type. In the previous build each
/// `draw(_:)` computed rects inline and the matching `mouseDown` recomputed them
/// from separate hardcoded constants, so the two drifted apart and clicks landed
/// on the wrong thing.
public struct TimelineGeometry {
    public var headerWidth: CGFloat
    public var rulerHeight: CGFloat
    public var rowHeight: CGFloat
    public var pixelsPerBar: CGFloat
    public var totalBars: Double

    public init(
        headerWidth: CGFloat = Theme.Metric.trackHeaderWidth,
        rulerHeight: CGFloat = Theme.Metric.rulerHeight,
        rowHeight: CGFloat = Theme.Metric.trackRowHeight,
        pixelsPerBar: CGFloat = 44,
        totalBars: Double = 64
    ) {
        self.headerWidth = headerWidth
        self.rulerHeight = rulerHeight
        self.rowHeight = rowHeight
        self.pixelsPerBar = pixelsPerBar
        self.totalBars = totalBars
    }

    public func x(forBar bar: Double) -> CGFloat {
        headerWidth + CGFloat(bar) * pixelsPerBar
    }

    public func bar(forX x: CGFloat) -> Double {
        max(0, Double((x - headerWidth) / max(1, pixelsPerBar)))
    }

    public func y(forRow row: Int) -> CGFloat {
        rulerHeight + CGFloat(row) * rowHeight
    }

    public func row(forY y: CGFloat) -> Int? {
        guard y >= rulerHeight else { return nil }
        return Int((y - rulerHeight) / rowHeight)
    }

    public func rowRect(_ row: Int, width: CGFloat) -> NSRect {
        NSRect(x: 0, y: y(forRow: row), width: width, height: rowHeight)
    }

    public func clipRect(startBar: Double, bars: Double, row: Int) -> NSRect {
        let inset: CGFloat = 3
        return NSRect(
            x: x(forBar: startBar),
            y: y(forRow: row) + inset,
            width: max(8, CGFloat(bars) * pixelsPerBar),
            height: rowHeight - inset * 2
        )
    }

    public var contentWidth: CGFloat {
        headerWidth + CGFloat(totalBars) * pixelsPerBar + 40
    }

    public func contentHeight(rows: Int) -> CGFloat {
        rulerHeight + CGFloat(max(rows, 1)) * rowHeight + 24
    }
}

/// Where on a clip a drag started, which decides what the drag does. Exposed so
/// the cursor can change to match before the user commits to a drag.
public enum ClipDragMode {
    case move
    case resizeStart
    case resizeEnd

    public static let edgeWidth: CGFloat = 7
}
