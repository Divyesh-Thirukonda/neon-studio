import AppKit
import NeonStudioKit

/// The automation editor: one scrollable row per automated control, with the
/// curve drawn against the same bar grid the arrangement uses.
///
/// What changed from the previous build:
/// * every lane is reachable — the view sizes itself to *all* lanes and scrolls,
///   instead of drawing only the two or three that happened to fit,
/// * points are draggable in both time and value, can be added with a
///   double-click and deleted from the context menu, instead of a single click
///   teleporting a point to wherever the pointer landed,
/// * lanes can be switched off or deleted from their own header,
/// * one geometry function per element, used by drawing *and* hit-testing, so a
///   click can never land somewhere other than what it looks like it hits.
final class AutomationEditorView: NSView, EditorCanvas {

    // MARK: - Layout constants
    //
    // Everything positional derives from these plus `TimelineGeometry`, which is
    // shared with the arrangement canvas so the two grids line up bar for bar.

    private static let toolbarHeight: CGFloat = 40
    private static let rulerStripHeight: CGFloat = 20
    private static let laneHeight: CGFloat = 64
    /// Vertical padding between a lane row and its curve area.
    private static let curveInset: CGFloat = 12
    private static let pointRadius: CGFloat = 5.5
    private static let headerPadding: CGFloat = 12
    private static let laneControlHeight: CGFloat = 20
    private static let toggleWidth: CGFloat = 76
    private static let deleteWidth: CGFloat = 30

    // MARK: - Host

    weak var host: EditorHost? {
        didSet { refresh() }
    }

    /// Horizontal zoom, in points per bar. The pane keeps this in step with the
    /// arrangement so both views scroll and zoom together.
    var pixelsPerBar: CGFloat = 44 {
        didSet {
            guard abs(pixelsPerBar - oldValue) > 0.01 else { return }
            sizeToFitContent()
            invalidateCursorAndAccessibility()
            needsDisplay = true
        }
    }

    // MARK: - State

    private struct PointRef: Equatable {
        var laneIndex: Int
        var pointIndex: Int
    }

    private struct PointDrag {
        let laneId: String
        let laneIndex: Int
        let pointIndex: Int
        let originalBar: Double
        let originalValue: Double
        var bar: Double
        var value: Double
        var moved: Bool
    }

    private var lanes: [AutomationLane] = []
    private var playheadBar: Double = 0
    private var drag: PointDrag?
    private var hover: PointRef?
    private var selection: PointRef?
    private var trackingAreaRef: NSTrackingArea?
    /// Held so the menu (and the closures its items own) outlive `menu(for:)`.
    private var contextMenuHolder: NSMenu?
    private var laneRows: [LaneRow] = []
    private var laneElements: [NSAccessibilityElement] = []

    private struct LaneRow {
        let laneId: String
        let toggle: NSButton
        let delete: NSButton
    }

    // MARK: - Subviews

    private let toolbar = ToolbarStrip()
    private let toolbarStack = NSStackView()
    private let summaryLabel = makeLabel("", font: Theme.Font.caption(11), color: Theme.muted)
    private var addLaneButton: NSButton?
    private var parameterPopUp: NSPopUpButton?
    private var emptyState: EmptyStateView?

    /// Index 0 picks a parameter that isn't already automated on that track;
    /// the rest name one explicitly.
    private static let parameterOptions: [(title: String, parameter: String?)] = [
        ("Pick one for me", nil),
        ("Volume", "gain"),
        ("Pan", "pan"),
        ("Filter", "filter"),
        ("Reverb", "reverb"),
        ("Delay", "delay"),
        ("Send A", "sendA"),
        ("Send B", "sendB")
    ]

    private static let cyclingParameters = ["filter", "pan", "sendA", "reverb", "delay", "gain"]

    // MARK: - Init

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        buildChrome()
    }

    convenience init() {
        self.init(frame: NSRect(x: 0, y: 0, width: 900, height: 320))
    }

    required init?(coder: NSCoder) {
        super.init(coder: coder)
        buildChrome()
    }

    deinit {
        NotificationCenter.default.removeObserver(self)
    }

    override var isFlipped: Bool { true }
    override var acceptsFirstResponder: Bool { true }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }

    private func buildChrome() {
        setAccessibilityRole(.group)
        setAccessibilityLabel("Automation lanes")
        setAccessibilityHelp(AppEnvironment.shared.help(
            "One row per automated control. Drag a dot to change its value, double-click empty space to add one.",
            term: "Automation"
        ))
        toolTip = AppEnvironment.shared.help(
            "Drag a dot to move it. Double-click empty space to add a dot. Right-click for more.",
            term: "Automation"
        )

        toolbar.translatesAutoresizingMaskIntoConstraints = true
        addSubview(toolbar)

        let addButton = Controls.button(
            title: "Add Lane",
            symbol: "plus",
            help: AppEnvironment.shared.help(
                "Adds a new automation lane for the selected track, so one of its settings can change over time.",
                term: "Automation"
            ),
            style: .primary
        ) { [weak self] in
            self?.addLane()
        }
        // `.primary` claims Return; this view is not a dialog, so give it back.
        addButton.keyEquivalent = ""
        addLaneButton = addButton

        let popUp = Controls.popUp(
            titles: Self.parameterOptions.map(\.title),
            selected: 0,
            help: "Which setting a new lane should control. \"Pick one for me\" chooses a setting this track isn't already automating.",
            accessibilityLabel: "Setting for the new lane"
        ) { _ in }
        parameterPopUp = popUp

        let glossaryButton = Controls.glossary("Automation", Glossary.long("Automation"))

        summaryLabel.alignment = .right
        summaryLabel.setAccessibilityRole(.staticText)

        toolbarStack.orientation = .horizontal
        toolbarStack.alignment = .centerY
        toolbarStack.spacing = 8
        toolbarStack.translatesAutoresizingMaskIntoConstraints = false
        toolbarStack.addArrangedSubview(addButton)
        toolbarStack.addArrangedSubview(popUp)
        toolbarStack.addArrangedSubview(glossaryButton)
        toolbar.addSubview(toolbarStack)
        toolbar.addSubview(summaryLabel)

        NSLayoutConstraint.activate([
            toolbarStack.leadingAnchor.constraint(equalTo: toolbar.leadingAnchor, constant: Self.headerPadding),
            toolbarStack.centerYAnchor.constraint(equalTo: toolbar.centerYAnchor),
            summaryLabel.trailingAnchor.constraint(equalTo: toolbar.trailingAnchor, constant: -Self.headerPadding),
            summaryLabel.centerYAnchor.constraint(equalTo: toolbar.centerYAnchor),
            summaryLabel.leadingAnchor.constraint(greaterThanOrEqualTo: toolbarStack.trailingAnchor, constant: 12)
        ])

        let empty = EmptyStateView(
            symbol: "point.topleft.down.curvedto.point.bottomright.up",
            title: "Nothing automated yet",
            body: "Automation makes a setting change over time on its own — like a filter opening up during a build. Add a lane to start.",
            actionTitle: "Add Lane"
        ) { [weak self] in
            self?.addLane()
        }
        addSubview(empty)
        NSLayoutConstraint.activate([
            empty.leadingAnchor.constraint(equalTo: leadingAnchor),
            empty.trailingAnchor.constraint(equalTo: trailingAnchor),
            empty.topAnchor.constraint(equalTo: topAnchor, constant: Self.toolbarHeight),
            empty.bottomAnchor.constraint(equalTo: bottomAnchor)
        ])
        emptyState = empty

        refresh()
    }

    // MARK: - Geometry
    //
    // Every rect below is used by BOTH `draw(_:)` and the mouse handling. Nothing
    // recomputes a position from a literal anywhere else in this file.

    private var totalBars: Double {
        let content = host?.project.contentEndBar ?? 0
        let pointEnd = lanes.flatMap(\.points).map(\.bar).max() ?? 0
        return max(32, (max(content, pointEnd) + 8).rounded(.up))
    }

    private var geometry: TimelineGeometry {
        TimelineGeometry(
            headerWidth: Theme.Metric.trackHeaderWidth,
            rulerHeight: Self.toolbarHeight + Self.rulerStripHeight,
            rowHeight: Self.laneHeight,
            pixelsPerBar: pixelsPerBar,
            totalBars: totalBars
        )
    }

    private var contentWidth: CGFloat {
        max(bounds.width, geometry.contentWidth)
    }

    private func laneRect(_ index: Int) -> NSRect {
        geometry.rowRect(index, width: contentWidth)
    }

    private func headerRect(_ index: Int) -> NSRect {
        let row = laneRect(index)
        return NSRect(x: 0, y: row.minY, width: geometry.headerWidth, height: row.height)
    }

    /// The area a lane's curve is drawn in. Value 1 sits on `minY` (visually the
    /// top, because this view is flipped) and value 0 on `maxY`.
    private func curveRect(_ index: Int) -> NSRect {
        let row = laneRect(index)
        let left = geometry.headerWidth
        let right = geometry.x(forBar: geometry.totalBars)
        return NSRect(
            x: left,
            y: row.minY + Self.curveInset,
            width: max(60, right - left),
            height: max(12, row.height - Self.curveInset * 2)
        )
    }

    private var rulerStripRect: NSRect {
        NSRect(x: 0, y: Self.toolbarHeight, width: contentWidth, height: Self.rulerStripHeight)
    }

    private func toggleFrame(_ index: Int) -> NSRect {
        let row = laneRect(index)
        return NSRect(
            x: Self.headerPadding,
            y: row.minY + 40,
            width: Self.toggleWidth,
            height: Self.laneControlHeight
        )
    }

    private func deleteFrame(_ index: Int) -> NSRect {
        let toggle = toggleFrame(index)
        return NSRect(
            x: toggle.maxX + 8,
            y: toggle.minY,
            width: Self.deleteWidth,
            height: Self.laneControlHeight
        )
    }

    private func laneTitleRect(_ index: Int) -> NSRect {
        let row = laneRect(index)
        return NSRect(
            x: Self.headerPadding,
            y: row.minY + 6,
            width: geometry.headerWidth - Self.headerPadding * 2,
            height: 16
        )
    }

    private func laneSubtitleRect(_ index: Int) -> NSRect {
        let title = laneTitleRect(index)
        return NSRect(x: title.minX, y: title.maxY + 1, width: title.width, height: 15)
    }

    private func y(forValue value: Double, in rect: NSRect) -> CGFloat {
        rect.maxY - CGFloat(clamp01(value)) * rect.height
    }

    private func value(forY y: CGFloat, in rect: NSRect) -> Double {
        guard rect.height > 0 else { return 0 }
        return clamp01(Double((rect.maxY - y) / rect.height))
    }

    private func pointCenter(bar: Double, value: Double, in rect: NSRect) -> NSPoint {
        NSPoint(x: geometry.x(forBar: bar), y: y(forValue: value, in: rect))
    }

    /// The clickable area of a point — a full `minimumHitTarget` square, even
    /// though the dot drawn inside it is smaller.
    private func pointHitRect(bar: Double, value: Double, in rect: NSRect) -> NSRect {
        let center = pointCenter(bar: bar, value: value, in: rect)
        let side = Theme.Metric.minimumHitTarget
        return NSRect(x: center.x - side / 2, y: center.y - side / 2, width: side, height: side)
    }

    private func laneIndex(at point: NSPoint) -> Int? {
        guard let row = geometry.row(forY: point.y), row >= 0, row < lanes.count else { return nil }
        return row
    }

    /// Nearest point to `location` within its hit area, or nil.
    private func pointIndex(at location: NSPoint, inLane index: Int) -> Int? {
        guard index >= 0, index < lanes.count else { return nil }
        let rect = curveRect(index)
        var best: (index: Int, distance: CGFloat)?
        for (i, point) in lanes[index].points.enumerated() {
            let hit = pointHitRect(bar: point.bar, value: point.value, in: rect)
            guard hit.contains(location) else { continue }
            let center = pointCenter(bar: point.bar, value: point.value, in: rect)
            let distance = hypot(center.x - location.x, center.y - location.y)
            if best == nil || distance < best!.distance {
                best = (i, distance)
            }
        }
        return best?.index
    }

    private func clamp01(_ value: Double) -> Double { max(0, min(1, value)) }

    // MARK: - EditorCanvas

    func refresh() {
        lanes = host?.project.snapshot.automationLanes ?? []
        playheadBar = host?.playheadBar ?? 0

        if let selection, selection.laneIndex >= lanes.count {
            self.selection = nil
        }
        hover = nil

        let hasLanes = !lanes.isEmpty
        emptyState?.isHidden = hasLanes
        emptyState?.isActionEnabled = (host?.project.snapshot.tracks.isEmpty == false)
        addLaneButton?.isEnabled = (host?.project.snapshot.tracks.isEmpty == false)
        addLaneButton?.toolTip = addLaneButton?.isEnabled == true
            ? AppEnvironment.shared.help(
                "Adds a new automation lane for the selected track, so one of its settings can change over time.",
                term: "Automation"
            )
            : "Add a track first — an automation lane changes a setting on a track."

        summaryLabel.stringValue = summaryText()
        summaryLabel.setAccessibilityLabel(summaryText())

        rebuildLaneControls()
        sizeToFitContent()
        positionSubviews()
        invalidateCursorAndAccessibility()
        needsDisplay = true
    }

    func playheadDidMove(to bar: Double) {
        let previous = playheadBar
        playheadBar = bar
        guard !lanes.isEmpty else { return }
        for value in [previous, bar] {
            let x = geometry.x(forBar: value)
            setNeedsDisplay(NSRect(x: x - 3, y: 0, width: 6, height: bounds.height))
        }
    }

    func contentSize(fittingVisible visible: NSSize) -> NSSize {
        let width = max(visible.width, geometry.contentWidth)
        let height = lanes.isEmpty
            ? max(visible.height, 260)
            : max(visible.height, geometry.contentHeight(rows: lanes.count))
        return NSSize(width: width, height: height)
    }

    private func summaryText() -> String {
        guard !lanes.isEmpty else { return "" }
        let count = lanes.count
        let points = lanes.reduce(0) { $0 + $1.points.count }
        let lanesWord = count == 1 ? "lane" : "lanes"
        let pointsWord = points == 1 ? "point" : "points"
        return "\(count) \(lanesWord), \(points) \(pointsWord) — drag a dot to change it"
    }

    // MARK: - Sizing and subview placement

    private func sizeToFitContent() {
        guard translatesAutoresizingMaskIntoConstraints,
              let clip = enclosingScrollView?.contentView else { return }
        let target = contentSize(fittingVisible: clip.bounds.size)
        if abs(target.width - frame.width) > 0.5 || abs(target.height - frame.height) > 0.5 {
            setFrameSize(target)
        }
    }

    override func setFrameSize(_ newSize: NSSize) {
        super.setFrameSize(newSize)
        positionSubviews()
    }

    override func layout() {
        super.layout()
        positionSubviews()
    }

    override func viewDidMoveToSuperview() {
        super.viewDidMoveToSuperview()
        observeScrolling()
        sizeToFitContent()
        positionSubviews()
    }

    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        observeScrolling()
        positionSubviews()
    }

    private func observeScrolling() {
        NotificationCenter.default.removeObserver(self, name: NSView.boundsDidChangeNotification, object: nil)
        guard let clip = enclosingScrollView?.contentView else { return }
        clip.postsBoundsChangedNotifications = true
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(scrollBoundsChanged),
            name: NSView.boundsDidChangeNotification,
            object: clip
        )
    }

    @objc private func scrollBoundsChanged() {
        positionToolbar()
    }

    /// Keeps the toolbar pinned to the visible corner rather than letting it
    /// scroll off to the left once the song is wider than the window.
    private func positionToolbar() {
        var area = bounds
        if let clip = enclosingScrollView?.contentView {
            // Converted rather than read straight off the scroll view, so this
            // is still right when the canvas is nested inside the document view.
            let visible = convert(clip.bounds, from: clip).intersection(bounds)
            if !visible.isEmpty { area = visible }
        }
        toolbar.frame = NSRect(
            x: area.minX,
            y: max(bounds.minY, area.minY),
            width: max(area.width, 1),
            height: Self.toolbarHeight
        )
    }

    private func positionSubviews() {
        positionToolbar()
        for (index, row) in laneRows.enumerated() where index < lanes.count {
            row.toggle.frame = toggleFrame(index)
            row.delete.frame = deleteFrame(index)
        }
    }

    // MARK: - Lane header controls

    private func rebuildLaneControls() {
        for row in laneRows {
            row.toggle.removeFromSuperview()
            row.delete.removeFromSuperview()
        }
        laneRows = lanes.map { lane in
            let laneId = lane.id
            let parameterName = automationParameterDisplayName(lane.parameter)
            let toggle = Controls.toggle(
                title: "Enabled",
                help: AppEnvironment.shared.help(
                    "When this is off, \(parameterName.lowercased()) stays where you set it and this lane is ignored.",
                    term: "Automation"
                ),
                isOn: lane.enabled ?? true
            ) { [weak self] isOn in
                self?.setLane(id: laneId, enabled: isOn)
            }
            toggle.controlSize = .small
            toggle.font = Theme.Font.caption(11)
            toggle.translatesAutoresizingMaskIntoConstraints = true
            toggle.setAccessibilityLabel("\(lane.label) enabled")

            let delete = Controls.button(
                title: "",
                symbol: "trash",
                help: "Deletes the \(lane.label) lane and every point on it. ⌘Z brings it back.",
                style: .destructive
            ) { [weak self] in
                self?.deleteLane(id: laneId)
            }
            delete.controlSize = .small
            delete.translatesAutoresizingMaskIntoConstraints = true
            delete.setAccessibilityLabel("Delete the \(lane.label) lane")

            addSubview(toggle)
            addSubview(delete)
            return LaneRow(laneId: laneId, toggle: toggle, delete: delete)
        }
    }

    // MARK: - Drawing

    override func draw(_ dirtyRect: NSRect) {
        roundedFill(dirtyRect, radius: 0, color: Theme.canvas)

        guard !lanes.isEmpty else {
            // The empty state view handles the message; nothing else to draw.
            return
        }

        drawRuler(dirtyRect: dirtyRect)
        for index in lanes.indices {
            drawLane(index, dirtyRect: dirtyRect)
        }
        drawPlayhead(dirtyRect: dirtyRect)
        drawActiveBadge()
    }

    private var barLabelStride: Double {
        let minimumSpacing: CGFloat = 56
        for candidate in [1.0, 2.0, 4.0, 8.0, 16.0, 32.0] where CGFloat(candidate) * pixelsPerBar >= minimumSpacing {
            return candidate
        }
        return 64
    }

    private func drawRuler(dirtyRect: NSRect) {
        let strip = rulerStripRect
        guard strip.intersects(dirtyRect) else { return }
        roundedFill(strip, radius: 0, color: Theme.panelAlt)
        drawLine(
            from: NSPoint(x: strip.minX, y: strip.maxY - 0.5),
            to: NSPoint(x: strip.maxX, y: strip.maxY - 0.5),
            color: Theme.subtleStroke
        )
        drawText(
            "Bars",
            in: NSRect(x: Self.headerPadding, y: strip.minY + 2, width: geometry.headerWidth - Self.headerPadding * 2, height: 15),
            color: Theme.muted,
            font: Theme.Font.captionBold(11)
        )

        let stride = barLabelStride
        var bar = 0.0
        while bar <= geometry.totalBars {
            let x = geometry.x(forBar: bar)
            drawLine(
                from: NSPoint(x: x, y: strip.maxY - 6),
                to: NSPoint(x: x, y: strip.maxY),
                color: Theme.stroke
            )
            drawText(
                "\(Int(bar) + 1)",
                in: NSRect(x: x + 3, y: strip.minY + 2, width: max(24, CGFloat(stride) * pixelsPerBar - 6), height: 14),
                color: Theme.muted,
                font: Theme.Font.mono(11)
            )
            bar += stride
        }
    }

    private func laneColor(_ lane: AutomationLane) -> NSColor {
        let trackColor = host?.project.track(id: lane.trackId)?.color
        return neonColor(from: lane.color ?? trackColor, fallback: Theme.defaultTrackColor)
    }

    private func drawLane(_ index: Int, dirtyRect: NSRect) {
        let row = laneRect(index)
        guard row.intersects(dirtyRect) else { return }

        let lane = lanes[index]
        let isEnabled = lane.enabled ?? true
        let isSelectedTrack = host?.selectedTrackId == lane.trackId
        let base = laneColor(lane)
        let color = isEnabled ? base : base.mixed(with: Theme.panel, amount: 0.6)

        roundedFill(row, radius: 0, color: index % 2 == 0 ? Theme.canvas : Theme.panelAlt)
        roundedFill(headerRect(index), radius: 0, color: Theme.panel)
        drawLine(
            from: NSPoint(x: row.minX, y: row.maxY - 0.5),
            to: NSPoint(x: row.maxX, y: row.maxY - 0.5),
            color: Theme.subtleStroke
        )
        drawLine(
            from: NSPoint(x: geometry.headerWidth - 0.5, y: row.minY),
            to: NSPoint(x: geometry.headerWidth - 0.5, y: row.maxY),
            color: Theme.stroke
        )
        if isSelectedTrack {
            roundedFill(NSRect(x: 0, y: row.minY, width: 3, height: row.height), radius: 0, color: Theme.accent)
        }

        // Header text.
        drawText(
            lane.label,
            in: laneTitleRect(index),
            color: isEnabled ? Theme.text : Theme.dim,
            font: Theme.Font.emphasis(12)
        )
        let trackName = host?.project.track(id: lane.trackId)?.name ?? "Master"
        drawText(
            "\(trackName) · \(automationParameterDisplayName(lane.parameter))",
            in: laneSubtitleRect(index),
            color: Theme.muted,
            font: Theme.Font.caption(11)
        )

        drawGrid(in: index, color: color)
        drawCurve(in: index, color: color, enabled: isEnabled)
    }

    private func drawGrid(in index: Int, color: NSColor) {
        let rect = curveRect(index)
        let row = laneRect(index)
        let stride = pixelsPerBar >= 14 ? 1.0 : 4.0
        var bar = 0.0
        while bar <= geometry.totalBars {
            let x = geometry.x(forBar: bar)
            let strong = bar.truncatingRemainder(dividingBy: 4) == 0
            drawLine(
                from: NSPoint(x: x, y: row.minY),
                to: NSPoint(x: x, y: row.maxY),
                color: strong ? Theme.stroke : Theme.subtleStroke
            )
            bar += stride
        }
        // Halfway guide, so "about half" is readable at a glance.
        drawLine(
            from: NSPoint(x: rect.minX, y: y(forValue: 0.5, in: rect)),
            to: NSPoint(x: rect.maxX, y: y(forValue: 0.5, in: rect)),
            color: Theme.subtleStroke
        )
    }

    /// The points as they should currently appear, including the one being
    /// dragged, sorted by bar.
    private func displayPoints(_ index: Int) -> [AutomationPoint] {
        var points = lanes[index].points
        if let drag, drag.laneIndex == index, drag.pointIndex < points.count {
            points[drag.pointIndex].bar = drag.bar
            points[drag.pointIndex].value = drag.value
        }
        return points.sorted { $0.bar < $1.bar }
    }

    private func drawCurve(in index: Int, color: NSColor, enabled: Bool) {
        let rect = curveRect(index)
        let points = displayPoints(index)
        guard let first = points.first, let last = points.last else { return }

        let line = NSBezierPath()
        line.move(to: NSPoint(x: rect.minX, y: y(forValue: first.value, in: rect)))
        var previousY = y(forValue: first.value, in: rect)
        for point in points {
            let position = pointCenter(bar: point.bar, value: point.value, in: rect)
            let isStep = (point.curve ?? lanes[index].curve ?? "linear").lowercased() == "step"
            if isStep {
                line.line(to: NSPoint(x: position.x, y: previousY))
            }
            line.line(to: position)
            previousY = position.y
        }
        line.line(to: NSPoint(x: rect.maxX, y: y(forValue: last.value, in: rect)))

        // Shaded area beneath the line, so the shape reads even at a glance.
        if let fill = line.copy() as? NSBezierPath {
            fill.line(to: NSPoint(x: rect.maxX, y: rect.maxY))
            fill.line(to: NSPoint(x: rect.minX, y: rect.maxY))
            fill.close()
            color.withAlphaComponent(enabled ? 0.16 : 0.07).setFill()
            fill.fill()
        }

        color.setStroke()
        line.lineWidth = enabled ? 2 : 1
        line.lineJoinStyle = .round
        line.stroke()

        for (pointIndex, point) in points.enumerated() {
            let center = pointCenter(bar: point.bar, value: point.value, in: rect)
            let reference = PointRef(laneIndex: index, pointIndex: pointIndex)
            let radius = Self.pointRadius
            let dot = NSRect(
                x: center.x - radius,
                y: center.y - radius,
                width: radius * 2,
                height: radius * 2
            )
            if hover == reference || selection == reference || isDragging(reference) {
                let ring = dot.insetBy(dx: -4, dy: -4)
                Theme.accent.withAlphaComponent(0.28).setFill()
                NSBezierPath(ovalIn: ring).fill()
            }
            color.setFill()
            NSBezierPath(ovalIn: dot).fill()
            Theme.panel.setStroke()
            let outline = NSBezierPath(ovalIn: dot)
            outline.lineWidth = 1.5
            outline.stroke()
            if selection == reference {
                Theme.accent.setStroke()
                let selected = NSBezierPath(ovalIn: dot.insetBy(dx: -2.5, dy: -2.5))
                selected.lineWidth = 1.5
                selected.stroke()
            }
        }
    }

    private func isDragging(_ reference: PointRef) -> Bool {
        guard let drag else { return false }
        // While dragging, the points are re-sorted for drawing, so compare by
        // the sorted position of the dragged bar rather than the stored index.
        guard drag.laneIndex == reference.laneIndex else { return false }
        let sorted = displayPoints(reference.laneIndex)
        guard reference.pointIndex < sorted.count else { return false }
        let point = sorted[reference.pointIndex]
        return abs(point.bar - drag.bar) < 0.0001 && abs(point.value - drag.value) < 0.0001
    }

    private func drawPlayhead(dirtyRect: NSRect) {
        guard playheadBar >= 0, playheadBar <= geometry.totalBars else { return }
        let x = geometry.x(forBar: playheadBar)
        guard x >= geometry.headerWidth else { return }
        drawLine(
            from: NSPoint(x: x, y: geometry.rulerHeight),
            to: NSPoint(x: x, y: geometry.contentHeight(rows: lanes.count)),
            color: Theme.playhead,
            width: 1.5
        )
    }

    /// The readout that follows the point being dragged or hovered.
    private func drawActiveBadge() {
        let reference: PointRef?
        let bar: Double
        let value: Double
        if let drag {
            reference = PointRef(laneIndex: drag.laneIndex, pointIndex: drag.pointIndex)
            bar = drag.bar
            value = drag.value
        } else if let hover, hover.laneIndex < lanes.count,
                  hover.pointIndex < lanes[hover.laneIndex].points.count {
            reference = hover
            let point = lanes[hover.laneIndex].points[hover.pointIndex]
            bar = point.bar
            value = point.value
        } else {
            return
        }
        guard let reference, reference.laneIndex < lanes.count else { return }

        let lane = lanes[reference.laneIndex]
        let rect = curveRect(reference.laneIndex)
        let center = pointCenter(bar: bar, value: value, in: rect)
        let text = "\(automationParameterDisplayName(lane.parameter)) \(percentText(value))  ·  bar \(barText(bar))"
        drawBadge(text, near: center)
    }

    private func drawBadge(_ text: String, near point: NSPoint) {
        let font = Theme.Font.mono(11, weight: .semibold)
        let size = NSString(string: text).size(withAttributes: [.font: font])
        var rect = NSRect(
            x: point.x + 12,
            y: point.y - size.height - 16,
            width: size.width + 16,
            height: size.height + 8
        )
        let limits = visibleRect.isEmpty ? bounds : visibleRect
        if rect.maxX > limits.maxX - 6 { rect.origin.x = point.x - rect.width - 12 }
        if rect.minX < limits.minX + 6 { rect.origin.x = limits.minX + 6 }
        if rect.minY < limits.minY + 4 { rect.origin.y = point.y + 16 }
        roundedFill(rect, radius: Theme.Metric.smallCornerRadius, color: Theme.panelRaised)
        roundedStroke(rect, radius: Theme.Metric.smallCornerRadius, color: Theme.stroke)
        drawText(
            text,
            in: rect.insetBy(dx: 8, dy: 4),
            color: Theme.text,
            font: font,
            alignment: .center
        )
    }

    private func percentText(_ value: Double) -> String {
        "\(Int((clamp01(value) * 100).rounded()))%"
    }

    /// Bars are shown to people 1-based, matching the ruler.
    private func barText(_ bar: Double) -> String {
        let display = bar + 1
        let rounded = (display * 100).rounded() / 100
        if abs(rounded - rounded.rounded()) < 0.005 {
            return "\(Int(rounded.rounded()))"
        }
        return String(format: "%.2f", rounded)
    }

    // MARK: - Mouse

    override func mouseDown(with event: NSEvent) {
        window?.makeFirstResponder(self)
        let location = convert(event.locationInWindow, from: nil)
        if toolbar.frame.contains(location) { return }
        guard let index = laneIndex(at: location) else {
            selection = nil
            needsDisplay = true
            return
        }

        let lane = lanes[index]
        host?.selectTrack(lane.trackId)

        guard location.x >= geometry.headerWidth else {
            // Header clicks belong to the real buttons living there.
            selection = nil
            needsDisplay = true
            return
        }

        if let pointIndex = pointIndex(at: location, inLane: index) {
            selection = PointRef(laneIndex: index, pointIndex: pointIndex)
            needsDisplay = true
            guard event.clickCount < 2 else { return }
            let point = lane.points[pointIndex]
            drag = PointDrag(
                laneId: lane.id,
                laneIndex: index,
                pointIndex: pointIndex,
                originalBar: point.bar,
                originalValue: point.value,
                bar: point.bar,
                value: point.value,
                moved: false
            )
            NSCursor.closedHand.push()
            return
        }

        if event.clickCount == 2 {
            addPoint(inLane: index, at: location)
            return
        }

        selection = nil
        needsDisplay = true
    }

    override func mouseDragged(with event: NSEvent) {
        guard var current = drag else { return }
        autoscroll(with: event)
        let location = convert(event.locationInWindow, from: nil)
        let rect = curveRect(current.laneIndex)
        let bypassSnap = event.modifierFlags.contains(.option)
        let lockValue = event.modifierFlags.contains(.shift)

        current.bar = snappedBar(geometry.bar(forX: location.x), bypassSnap: bypassSnap)
        current.value = lockValue ? current.originalValue : value(forY: location.y, in: rect)
        if abs(current.bar - current.originalBar) > 0.0001 || abs(current.value - current.originalValue) > 0.0001 {
            current.moved = true
        }
        drag = current
        needsDisplay = true
    }

    override func mouseUp(with event: NSEvent) {
        guard let current = drag else { return }
        drag = nil
        NSCursor.pop()
        guard current.moved else {
            needsDisplay = true
            return
        }
        commitDrag(current)
    }

    override func mouseMoved(with event: NSEvent) {
        updateHover(at: convert(event.locationInWindow, from: nil))
    }

    override func mouseExited(with event: NSEvent) {
        guard hover != nil else { return }
        hover = nil
        needsDisplay = true
    }

    private func updateHover(at location: NSPoint) {
        var next: PointRef?
        if let index = laneIndex(at: location),
           location.x >= geometry.headerWidth,
           let pointIndex = pointIndex(at: location, inLane: index) {
            next = PointRef(laneIndex: index, pointIndex: pointIndex)
        }
        guard next != hover else { return }
        hover = next
        needsDisplay = true
    }

    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        if let trackingAreaRef {
            removeTrackingArea(trackingAreaRef)
        }
        let area = NSTrackingArea(
            rect: .zero,
            options: [.mouseEnteredAndExited, .mouseMoved, .activeInKeyWindow, .inVisibleRect],
            owner: self,
            userInfo: nil
        )
        addTrackingArea(area)
        trackingAreaRef = area
    }

    override func resetCursorRects() {
        super.resetCursorRects()
        guard !lanes.isEmpty else { return }
        let visible = visibleRect
        for index in lanes.indices {
            let rect = curveRect(index)
            guard rect.intersects(visible) else { continue }
            addCursorRect(rect.intersection(visible), cursor: .crosshair)
        }
        // Added last so they take precedence over the curve areas beneath them.
        for index in lanes.indices {
            let rect = curveRect(index)
            guard rect.intersects(visible) else { continue }
            for point in lanes[index].points {
                let hit = pointHitRect(bar: point.bar, value: point.value, in: rect)
                guard hit.intersects(visible) else { continue }
                addCursorRect(hit.intersection(visible), cursor: .openHand)
            }
        }
    }

    private func snappedBar(_ bar: Double, bypassSnap: Bool) -> Double {
        let clamped = max(0, min(geometry.totalBars, bar))
        guard !bypassSnap else { return clamped }
        let snap = host?.snapValue ?? .quarter
        return max(0, min(geometry.totalBars, snap.snap(bars: clamped)))
    }

    // MARK: - Keyboard

    override func keyDown(with event: NSEvent) {
        guard let scalar = event.charactersIgnoringModifiers?.unicodeScalars.first else {
            super.keyDown(with: event)
            return
        }
        let step = (host?.snapValue ?? .quarter).bars
        let barStep = step > 0 ? step : 0.25
        switch Int(scalar.value) {
        case NSDeleteCharacter, NSBackspaceCharacter, NSDeleteFunctionKey:
            deleteSelectedPoint()
        case NSLeftArrowFunctionKey:
            nudgeSelection(bars: -barStep, value: 0)
        case NSRightArrowFunctionKey:
            nudgeSelection(bars: barStep, value: 0)
        case NSUpArrowFunctionKey:
            nudgeSelection(bars: 0, value: 0.05)
        case NSDownArrowFunctionKey:
            nudgeSelection(bars: 0, value: -0.05)
        default:
            super.keyDown(with: event)
        }
    }

    private func nudgeSelection(bars: Double, value: Double) {
        guard let selection, selection.laneIndex < lanes.count else {
            StatusCenter.shared.info("Select a point first — click one, then use the arrow keys to nudge it.")
            return
        }
        let lane = lanes[selection.laneIndex]
        guard selection.pointIndex < lane.points.count else { return }
        let point = lane.points[selection.pointIndex]
        let nextBar = max(0, min(geometry.totalBars, point.bar + bars))
        let nextValue = clamp01(point.value + value)
        applyPointMove(
            laneId: lane.id,
            pointIndex: selection.pointIndex,
            bar: nextBar,
            value: nextValue,
            actionName: "Move Automation Point"
        )
    }

    // MARK: - Context menu

    override func menu(for event: NSEvent) -> NSMenu? {
        let location = convert(event.locationInWindow, from: nil)
        let menu = NSMenu(title: "Automation")

        if let index = laneIndex(at: location), index < lanes.count {
            let lane = lanes[index]
            let laneId = lane.id
            if location.x >= geometry.headerWidth {
                if let pointIndex = pointIndex(at: location, inLane: index) {
                    selection = PointRef(laneIndex: index, pointIndex: pointIndex)
                    needsDisplay = true
                    menu.addItem(BlockMenuItem(title: "Delete Point") { [weak self] in
                        self?.deletePoint(laneId: laneId, pointIndex: pointIndex)
                    })
                } else {
                    menu.addItem(BlockMenuItem(title: "Add Point Here") { [weak self] in
                        self?.addPoint(inLane: index, at: location)
                    })
                }
                menu.addItem(NSMenuItem.separator())
            }
            let isEnabled = lane.enabled ?? true
            menu.addItem(BlockMenuItem(title: isEnabled ? "Turn Lane Off" : "Turn Lane On") { [weak self] in
                self?.setLane(id: laneId, enabled: !isEnabled)
            })
            menu.addItem(BlockMenuItem(title: "Delete Lane") { [weak self] in
                self?.deleteLane(id: laneId)
            })
            menu.addItem(NSMenuItem.separator())
        }

        menu.addItem(BlockMenuItem(title: "Add Lane for the Selected Track") { [weak self] in
            self?.addLane()
        })
        contextMenuHolder = menu
        return menu
    }

    // MARK: - Edits

    private func addLane() {
        guard let host else { return }
        guard let track = host.selectedTrack else {
            StatusCenter.shared.warning(
                "Add a track before adding automation.",
                detail: "Automation changes a setting on a track, so there has to be a track for it to act on."
            )
            return
        }

        let choiceIndex = parameterPopUp?.indexOfSelectedItem ?? 0
        let explicit = Self.parameterOptions.indices.contains(choiceIndex)
            ? Self.parameterOptions[choiceIndex].parameter
            : nil
        let parameter = explicit ?? nextParameter(for: track, in: host.project)
        let displayName = automationParameterDisplayName(parameter)

        let existingIds = Set((host.project.snapshot.automationLanes ?? []).map(\.id))
        let preferredId = "auto-\(safeProjectId(track.id))-\(safeProjectId(parameter))"
        let laneId = existingIds.contains(preferredId) ? makeId("auto") : preferredId

        let endBar = max(4.0, min(16.0, (host.project.contentEndBar > 0 ? host.project.contentEndBar : 8).rounded()))
        let lane = AutomationLane(
            id: laneId,
            trackId: track.id,
            parameter: parameter,
            label: "\(track.name) \(displayName)",
            color: track.color,
            enabled: true,
            curve: "linear",
            points: [
                AutomationPoint(bar: 0, value: 0.3, curve: "linear"),
                AutomationPoint(bar: endBar, value: 0.8, curve: "linear")
            ]
        )

        host.edit("Add Automation Lane") { project in
            var lanes = project.snapshot.automationLanes ?? []
            lanes.append(lane)
            project.snapshot.automationLanes = lanes
        }
        refresh()
        if let index = lanes.firstIndex(where: { $0.id == laneId }) {
            selection = PointRef(laneIndex: index, pointIndex: 0)
            scrollToVisible(laneRect(index))
            needsDisplay = true
        }
        StatusCenter.shared.success(
            "Added a \(displayName) automation lane for \(track.name). ⌘Z undoes it.",
            detail: "Drag its dots to shape how \(displayName.lowercased()) changes through the song."
        )
    }

    /// Picks a setting this track isn't already automating, so a second lane on
    /// the same track is never a duplicate of the first.
    private func nextParameter(for track: Track, in project: LocalProject) -> String {
        let used = Set(
            (project.snapshot.automationLanes ?? [])
                .filter { $0.trackId == track.id }
                .map { $0.parameter.lowercased() }
        )
        let inferred = inferAutomationParameter(for: track)
        if !used.contains(inferred.lowercased()) { return inferred }
        for candidate in Self.cyclingParameters where !used.contains(candidate.lowercased()) {
            return candidate
        }
        return "gain"
    }

    private func addPoint(inLane index: Int, at location: NSPoint) {
        guard let host, index < lanes.count else { return }
        let lane = lanes[index]
        let rect = curveRect(index)
        let bar = snappedBar(geometry.bar(forX: location.x), bypassSnap: false)
        let newValue = value(forY: location.y, in: rect)
        let point = AutomationPoint(bar: bar, value: newValue, curve: lane.curve ?? "linear")

        host.edit("Add Automation Point") { project in
            var lanes = project.snapshot.automationLanes ?? []
            guard let laneIndex = lanes.firstIndex(where: { $0.id == lane.id }) else { return }
            var points = lanes[laneIndex].points
            points.append(point)
            points.sort { $0.bar < $1.bar }
            lanes[laneIndex].points = points
            project.snapshot.automationLanes = lanes
        }
        refresh()
        selectPoint(laneId: lane.id, bar: bar, value: newValue)
        StatusCenter.shared.success(
            "Added a point at bar \(barText(bar)), \(percentText(newValue)). ⌘Z undoes it."
        )
    }

    private func deleteSelectedPoint() {
        guard let selection, selection.laneIndex < lanes.count else {
            StatusCenter.shared.info("Select a point first — click one, then press Delete.")
            return
        }
        deletePoint(laneId: lanes[selection.laneIndex].id, pointIndex: selection.pointIndex)
    }

    private func deletePoint(laneId: String, pointIndex: Int) {
        guard let host, let index = lanes.firstIndex(where: { $0.id == laneId }) else { return }
        let lane = lanes[index]
        guard pointIndex < lane.points.count else { return }
        guard lane.points.count > 1 else {
            StatusCenter.shared.warning(
                "A lane needs at least one point.",
                detail: "Delete the whole \(lane.label) lane instead if you no longer want it."
            )
            return
        }
        let point = lane.points[pointIndex]
        host.edit("Delete Automation Point") { project in
            var lanes = project.snapshot.automationLanes ?? []
            guard let laneIndex = lanes.firstIndex(where: { $0.id == laneId }),
                  pointIndex < lanes[laneIndex].points.count else { return }
            lanes[laneIndex].points.remove(at: pointIndex)
            project.snapshot.automationLanes = lanes
        }
        selection = nil
        refresh()
        StatusCenter.shared.success(
            "Deleted the point at bar \(barText(point.bar)) on \(lane.label). ⌘Z brings it back."
        )
    }

    private func commitDrag(_ current: PointDrag) {
        applyPointMove(
            laneId: current.laneId,
            pointIndex: current.pointIndex,
            bar: current.bar,
            value: current.value,
            actionName: "Move Automation Point"
        )
    }

    private func applyPointMove(laneId: String, pointIndex: Int, bar: Double, value newValue: Double, actionName: String) {
        guard let host, let index = lanes.firstIndex(where: { $0.id == laneId }) else { return }
        let lane = lanes[index]
        guard pointIndex < lane.points.count else { return }
        let clampedBar = max(0, min(geometry.totalBars, bar))
        let clampedValue = clamp01(newValue)

        host.edit(actionName) { project in
            var lanes = project.snapshot.automationLanes ?? []
            guard let laneIndex = lanes.firstIndex(where: { $0.id == laneId }),
                  pointIndex < lanes[laneIndex].points.count else { return }
            var points = lanes[laneIndex].points
            points[pointIndex].bar = clampedBar
            points[pointIndex].value = clampedValue
            points.sort { $0.bar < $1.bar }
            lanes[laneIndex].points = points
            project.snapshot.automationLanes = lanes
        }
        refresh()
        selectPoint(laneId: laneId, bar: clampedBar, value: clampedValue)
        StatusCenter.shared.success(
            "\(automationParameterDisplayName(lane.parameter)) is now \(percentText(clampedValue)) at bar \(barText(clampedBar)). ⌘Z undoes it."
        )
    }

    private func selectPoint(laneId: String, bar: Double, value target: Double) {
        guard let laneIndex = lanes.firstIndex(where: { $0.id == laneId }) else { return }
        guard let pointIndex = lanes[laneIndex].points.firstIndex(where: {
            abs($0.bar - bar) < 0.0001 && abs($0.value - target) < 0.0001
        }) else { return }
        selection = PointRef(laneIndex: laneIndex, pointIndex: pointIndex)
        needsDisplay = true
    }

    private func setLane(id laneId: String, enabled: Bool) {
        guard let host, let lane = lanes.first(where: { $0.id == laneId }) else { return }
        host.edit(enabled ? "Turn Automation Lane On" : "Turn Automation Lane Off") { project in
            var lanes = project.snapshot.automationLanes ?? []
            guard let index = lanes.firstIndex(where: { $0.id == laneId }) else { return }
            lanes[index].enabled = enabled
            project.snapshot.automationLanes = lanes
        }
        refresh()
        StatusCenter.shared.success(
            enabled
                ? "\(lane.label) is on again. ⌘Z undoes it."
                : "\(lane.label) is off — that setting stays where you left it. ⌘Z undoes it."
        )
    }

    private func deleteLane(id laneId: String) {
        guard let host, let lane = lanes.first(where: { $0.id == laneId }) else { return }
        if AppEnvironment.shared.confirmsDestructiveEdits {
            let alert = NSAlert()
            alert.alertStyle = .warning
            alert.messageText = "Delete the \(lane.label) automation lane?"
            alert.informativeText = "Its \(lane.points.count) points go with it. You can bring it back with Undo (⌘Z)."
            alert.addButton(withTitle: "Delete Lane")
            alert.addButton(withTitle: "Cancel")
            guard alert.runModal() == .alertFirstButtonReturn else { return }
        }
        host.edit("Delete Automation Lane") { project in
            project.snapshot.automationLanes = (project.snapshot.automationLanes ?? [])
                .filter { $0.id != laneId }
        }
        selection = nil
        refresh()
        StatusCenter.shared.success("Deleted the \(lane.label) automation lane. ⌘Z brings it back.")
    }

    // MARK: - Accessibility

    private func invalidateCursorAndAccessibility() {
        discardCursorRects()
        window?.invalidateCursorRects(for: self)
        rebuildAccessibilityElements()
    }

    private func rebuildAccessibilityElements() {
        laneElements = lanes.enumerated().map { index, lane in
            let row = laneRect(index)
            let element = NSAccessibilityElement()
            element.setAccessibilityRole(.group)
            element.setAccessibilityLabel(accessibilityLabel(for: lane))
            element.setAccessibilityHelp(AppEnvironment.shared.help(
                "\(automationParameterDisplayName(lane.parameter)) on \(host?.project.track(id: lane.trackId)?.name ?? "this track") over time.",
                term: "Automation"
            ))
            element.setAccessibilityParent(self)
            element.setAccessibilityFrameInParentSpace(row)

            let rect = curveRect(index)
            let children: [Any] = lane.points.enumerated().map { pointIndex, point in
                let hit = pointHitRect(bar: point.bar, value: point.value, in: rect)
                let child = NSAccessibilityElement()
                child.setAccessibilityRole(.slider)
                child.setAccessibilityLabel(
                    "\(lane.label), point \(pointIndex + 1) of \(lane.points.count), bar \(barText(point.bar))"
                )
                child.setAccessibilityValue(percentText(point.value))
                child.setAccessibilityHelp("Drag this dot to change when it happens and how far the setting moves.")
                child.setAccessibilityParent(element)
                child.setAccessibilityFrameInParentSpace(
                    NSRect(x: hit.minX - row.minX, y: hit.minY - row.minY, width: hit.width, height: hit.height)
                )
                return child
            }
            element.setAccessibilityChildren(children)
            return element
        }
    }

    private func accessibilityLabel(for lane: AutomationLane) -> String {
        let count = lane.points.count
        let word = count == 1 ? "point" : "points"
        let state = (lane.enabled ?? true) ? "enabled" : "disabled"
        return "\(lane.label), \(count) \(word), \(state)"
    }

    override func accessibilityChildren() -> [Any]? {
        var children: [Any] = subviews
        children.append(contentsOf: laneElements)
        return children
    }
}

// MARK: - Private helpers

/// The strip at the top of the editor. It is a real subview so its buttons keep
/// their hover, pressed and keyboard behaviour, and it stays pinned to the
/// visible corner while the lanes scroll behind it.
private final class ToolbarStrip: NSView {
    override var isFlipped: Bool { true }

    override func draw(_ dirtyRect: NSRect) {
        roundedFill(bounds, radius: 0, color: Theme.panel)
        drawLine(
            from: NSPoint(x: bounds.minX, y: bounds.maxY - 0.5),
            to: NSPoint(x: bounds.maxX, y: bounds.maxY - 0.5),
            color: Theme.stroke
        )
    }
}

/// A menu item that runs a closure, so the context menu can be built where the
/// context is known instead of through a pile of selectors and tag lookups.
private final class BlockMenuItem: NSMenuItem {
    private let handler: () -> Void

    init(title: String, handler: @escaping () -> Void) {
        self.handler = handler
        super.init(title: title, action: nil, keyEquivalent: "")
        target = self
        action = #selector(fire)
    }

    required init(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    @objc private func fire() {
        handler()
    }
}
