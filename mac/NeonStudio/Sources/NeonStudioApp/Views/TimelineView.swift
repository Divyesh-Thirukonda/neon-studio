import AppKit
import AVFoundation
import NeonStudioKit

/// The arrangement canvas: track headers, a bar ruler, the loop range, the
/// playhead, and the clips themselves.
///
/// Three rules shape this file.
///
/// 1. **One geometry.** Every rectangle a user can click is produced by exactly
///    one function, and `draw(_:)` and the mouse handlers both call it. The old
///    build recomputed pixel rects separately in drawing and in `mouseDown`, so
///    the two drifted and clicks landed on the wrong clip.
/// 2. **Everything you'd try to drag, drags.** Clips move, clip edges resize,
///    the loop ends and its middle drag, and the ruler scrubs — each with a
///    live preview, a cursor that says so before you press, and a single
///    undoable commit on mouse-up.
/// 3. **Nothing is a mystery.** Every region answers a tooltip, VoiceOver gets
///    a real element per clip and per track header, and an empty arrangement
///    says what to do next instead of showing a blank grid.
public final class TimelineView: NSView, EditorCanvas, NSViewToolTipOwner {

    // MARK: - Layout constants
    //
    // The ruler is the standard height plus a dedicated lane for the loop
    // brace, so scrubbing and loop dragging never fight over the same pixels —
    // the way the cycle bar sits above the ruler in every DAW people arrive
    // here from.

    private static let loopLaneHeight: CGFloat = 14
    private static let sectionBandHeight: CGFloat = 14
    private static let rulerTotalHeight: CGFloat =
        Theme.Metric.rulerHeight + TimelineView.loopLaneHeight
    /// How close to an end of the loop brace counts as grabbing that end.
    private static let loopHandleWidth: CGFloat = 9
    /// Shortest clip the user can drag a clip down to.
    private static let minimumClipBars: Double = 0.25

    // MARK: - State

    /// Layout maths shared with hit-testing. Rebuilt in `refresh()`.
    var geometry = TimelineGeometry(rulerHeight: TimelineView.rulerTotalHeight)

    public weak var host: EditorHost? {
        didSet { refresh() }
    }

    /// Zoom, in points per bar. The window's zoom slider and the View menu both
    /// drive this.
    public var pixelsPerBar: CGFloat {
        get { geometry.pixelsPerBar }
        set {
            let clamped = max(8, min(240, newValue))
            guard abs(clamped - geometry.pixelsPerBar) > 0.001 else { return }
            geometry.pixelsPerBar = clamped
            invalidateIntrinsicContentSize()
            rebuildAccessibilityChildren()
            rebuildToolTipRegion()
            window?.invalidateCursorRects(for: self)
            needsDisplay = true
        }
    }

    private var rowCount = 0
    private var sectionMarkers: [SectionMarker] = []
    private var displayedPlayheadBar: Double = 0

    /// Which tracks actually have their audio file on disk, resolved once per
    /// refresh. Drawing must never hit the filesystem: a full redraw touches
    /// every clip, and a per-clip existence check during a drag would stutter.
    private var audioURLsByTrack: [String: URL] = [:]

    /// Live drag state. While either of these is non-nil the canvas draws the
    /// proposed result instead of the stored one, so what you see during the
    /// drag is what you get when you let go.
    private var clipDragPreview: ClipDragPreview?
    private var loopPreview: (start: Double, end: Double)?

    /// Peaks per audio file, read once. Keyed by file path and shared between
    /// documents because the same stem often appears in several projects.
    private static var peakCache: [String: [Float]] = [:]
    private static let peakResolution = 1200
    private var pendingPeakLoads: Set<String> = []

    /// Set by `menu(for:)` so the context-menu actions know what was clicked.
    private var contextPoint: NSPoint = .zero
    private var contextClip: (trackId: String, clipId: String, name: String)?

    private var accessibilityChildElements: [NSAccessibilityElement] = []
    private var lastAccessibilityHeight: CGFloat = 0

    // MARK: - Life cycle

    public override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        setAccessibilityRole(.group)
        setAccessibilityLabel("Arrangement")
        setAccessibilityHelp("The song laid out bar by bar. Each row is a track; each block is a clip.")
        setAccessibilityElement(true)
        rebuildToolTipRegion()
    }

    public required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    public override var isFlipped: Bool { true }
    public override var isOpaque: Bool { true }
    public override var acceptsFirstResponder: Bool { true }

    public override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }

    public override func becomeFirstResponder() -> Bool {
        needsDisplay = true
        return true
    }

    public override func resignFirstResponder() -> Bool {
        needsDisplay = true
        return true
    }

    public override var intrinsicContentSize: NSSize {
        NSSize(width: geometry.contentWidth, height: geometry.contentHeight(rows: rowCount))
    }

    public override func setFrameSize(_ newSize: NSSize) {
        let heightChanged = abs(newSize.height - lastAccessibilityHeight) > 0.5
        super.setFrameSize(newSize)
        if heightChanged {
            lastAccessibilityHeight = newSize.height
            rebuildAccessibilityChildren()
        }
        rebuildToolTipRegion()
    }

    // MARK: - EditorCanvas

    public func refresh() {
        guard let project = currentProject else {
            rowCount = 0
            sectionMarkers = []
            audioURLsByTrack = [:]
            accessibilityChildElements = []
            needsDisplay = true
            return
        }
        geometry.totalBars = max(32, project.contentEndBar.rounded(.up) + 8)
        rowCount = project.snapshot.tracks.count
        sectionMarkers = TimelineView.sectionMarkers(for: project)
        audioURLsByTrack = [:]
        if let store = host?.store {
            for track in project.snapshot.tracks {
                if let url = store.existingAudioURL(for: track) {
                    audioURLsByTrack[track.id] = url
                }
            }
        }
        displayedPlayheadBar = host?.playheadBar ?? 0
        invalidateIntrinsicContentSize()
        rebuildAccessibilityChildren()
        rebuildToolTipRegion()
        window?.invalidateCursorRects(for: self)
        needsDisplay = true
    }

    /// Repaints only the two thin columns the playhead just left and arrived
    /// at. Redrawing the whole canvas 30 times a second made the old build
    /// unusable while playing.
    public func playheadDidMove(to bar: Double) {
        let previous = displayedPlayheadBar
        guard abs(previous - bar) > 0.0001 else { return }
        displayedPlayheadBar = bar
        setNeedsDisplay(playheadDirtyRect(forBar: previous))
        setNeedsDisplay(playheadDirtyRect(forBar: bar))
    }

    public func contentSize(fittingVisible visible: NSSize) -> NSSize {
        NSSize(
            width: max(visible.width, geometry.contentWidth),
            height: max(visible.height, geometry.contentHeight(rows: rowCount))
        )
    }

    private var currentProject: LocalProject? { host?.project }

    // MARK: - Geometry (the single source of truth)

    private var loopLaneRect: NSRect {
        NSRect(x: 0, y: 0, width: bounds.width, height: TimelineView.loopLaneHeight)
    }

    private var sectionBandRect: NSRect {
        NSRect(
            x: 0,
            y: TimelineView.loopLaneHeight,
            width: bounds.width,
            height: TimelineView.sectionBandHeight
        )
    }

    /// The band with the bar numbers in it. Clicking or dragging anywhere here
    /// scrubs.
    private var rulerNumberBandRect: NSRect {
        let top = TimelineView.loopLaneHeight + TimelineView.sectionBandHeight
        return NSRect(x: 0, y: top, width: bounds.width, height: geometry.rulerHeight - top)
    }

    private var gridRect: NSRect {
        NSRect(
            x: geometry.headerWidth,
            y: geometry.rulerHeight,
            width: max(0, bounds.width - geometry.headerWidth),
            height: max(0, bounds.height - geometry.rulerHeight)
        )
    }

    private func headerRect(row: Int) -> NSRect {
        NSRect(
            x: 0,
            y: geometry.y(forRow: row),
            width: geometry.headerWidth,
            height: geometry.rowHeight
        )
    }

    private func rowIndex(at point: NSPoint) -> Int? {
        guard let row = geometry.row(forY: point.y), row >= 0, row < rowCount else { return nil }
        return row
    }

    private func clipRect(_ clip: Clip, row: Int) -> NSRect {
        geometry.clipRect(
            startBar: max(0, clip.startBar ?? 0),
            bars: max(TimelineView.minimumClipBars, clip.bars ?? 1),
            row: row
        )
    }

    private func playheadDirtyRect(forBar bar: Double) -> NSRect {
        NSRect(x: geometry.x(forBar: bar) - 10, y: 0, width: 20, height: bounds.height)
    }

    /// The two grab zones on a loop brace, and the body between them.
    private func loopHandleRects() -> (start: NSRect, end: NSRect, body: NSRect)? {
        guard let loop = effectiveLoop() else { return nil }
        let lane = loopLaneRect
        let startX = geometry.x(forBar: loop.start)
        let endX = geometry.x(forBar: loop.end)
        let handle = TimelineView.loopHandleWidth
        let start = NSRect(x: startX - handle / 2, y: lane.minY, width: handle, height: lane.height)
        let end = NSRect(x: endX - handle / 2, y: lane.minY, width: handle, height: lane.height)
        let body = NSRect(
            x: startX,
            y: lane.minY,
            width: max(0, endX - startX),
            height: lane.height
        )
        return (start, end, body)
    }

    /// The loop range being shown right now — the drag preview while dragging,
    /// otherwise what the project stores. Returns nil when looping is off.
    private func effectiveLoop() -> (start: Double, end: Double)? {
        if let loopPreview { return loopPreview }
        guard let snapshot = currentProject?.snapshot, snapshot.loopEnabled == true else { return nil }
        let start = max(0, snapshot.loopStartBar ?? 0)
        let end = max(start + 1, snapshot.loopEndBar ?? (start + 8))
        return (start, end)
    }

    private struct ClipHit {
        let trackIndex: Int
        let trackId: String
        let trackName: String
        let clipIndex: Int
        let clip: Clip
        let rect: NSRect
        let mode: ClipDragMode
    }

    private func clipHit(at point: NSPoint) -> ClipHit? {
        guard let project = currentProject, let row = rowIndex(at: point) else { return nil }
        let track = project.snapshot.tracks[row]
        let clips = track.clips ?? []
        // Reversed so the clip drawn on top is the one you grab.
        for index in clips.indices.reversed() {
            let rect = clipRect(clips[index], row: row)
            guard rect.contains(point) else { continue }
            let edge = min(ClipDragMode.edgeWidth, rect.width / 3)
            let mode: ClipDragMode
            if point.x - rect.minX <= edge {
                mode = .resizeStart
            } else if rect.maxX - point.x <= edge {
                mode = .resizeEnd
            } else {
                mode = .move
            }
            return ClipHit(
                trackIndex: row,
                trackId: track.id,
                trackName: track.name,
                clipIndex: index,
                clip: clips[index],
                rect: rect,
                mode: mode
            )
        }
        return nil
    }

    // MARK: - Drawing

    public override func draw(_ dirtyRect: NSRect) {
        Theme.canvas.setFill()
        dirtyRect.fill()

        guard let project = currentProject, rowCount > 0 else {
            drawEmptyProjectMessage()
            return
        }

        drawRows(project: project, dirtyRect: dirtyRect)
        drawGridLines(dirtyRect: dirtyRect)
        drawSectionGuides(dirtyRect: dirtyRect)
        drawClips(project: project, dirtyRect: dirtyRect)
        drawDragPreview()
        drawHeaders(project: project, dirtyRect: dirtyRect)
        drawRuler(project: project, dirtyRect: dirtyRect)
        drawPlayhead()

        if !project.snapshot.tracks.contains(where: { !($0.clips ?? []).isEmpty }) {
            drawEmptyArrangementMessage()
        }
        drawFocusRingIfNeeded()
    }

    private func drawRows(project: LocalProject, dirtyRect: NSRect) {
        let selectedTrackId = host?.selectedTrackId ?? ""
        for row in 0..<rowCount {
            let rect = geometry.rowRect(row, width: bounds.width)
            guard rect.intersects(dirtyRect) else { continue }
            let track = project.snapshot.tracks[row]
            let isSelected = track.id == selectedTrackId
            let base = row.isMultiple(of: 2) ? Theme.canvas : Theme.panelAlt.withAlphaComponent(0.45)
            base.setFill()
            rect.fill()
            if isSelected {
                neonColor(from: track.color, fallback: Theme.defaultTrackColor)
                    .withAlphaComponent(0.10)
                    .setFill()
                rect.fill()
            }
            drawLine(
                from: NSPoint(x: 0, y: rect.maxY),
                to: NSPoint(x: bounds.width, y: rect.maxY),
                color: Theme.subtleStroke
            )
        }
    }

    private func drawGridLines(dirtyRect: NSRect) {
        let grid = gridRect
        guard grid.height > 0 else { return }
        let firstBar = max(0, Int(geometry.bar(forX: max(dirtyRect.minX, grid.minX))) - 1)
        let lastBar = min(Int(geometry.totalBars), Int(geometry.bar(forX: dirtyRect.maxX)) + 1)
        guard lastBar >= firstBar else { return }
        for bar in firstBar...lastBar {
            let x = geometry.x(forBar: Double(bar))
            guard x >= grid.minX - 1 else { continue }
            let strong = bar.isMultiple(of: 4)
            drawLine(
                from: NSPoint(x: x, y: grid.minY),
                to: NSPoint(x: x, y: bounds.height),
                color: strong ? Theme.stroke.withAlphaComponent(0.55) : Theme.subtleStroke.withAlphaComponent(0.5)
            )
        }
    }

    private func drawSectionGuides(dirtyRect: NSRect) {
        guard !sectionMarkers.isEmpty else { return }
        for marker in sectionMarkers {
            let x = geometry.x(forBar: marker.bar)
            guard x >= gridRect.minX, x >= dirtyRect.minX - 2, x <= dirtyRect.maxX + 2 else { continue }
            drawLine(
                from: NSPoint(x: x, y: geometry.rulerHeight),
                to: NSPoint(x: x, y: bounds.height),
                color: Theme.accent.withAlphaComponent(0.32),
                width: 1
            )
        }
    }

    private func drawClips(project: LocalProject, dirtyRect: NSRect) {
        let selectedClipId = host?.selectedClipId ?? ""
        for row in 0..<rowCount {
            let track = project.snapshot.tracks[row]
            for clip in track.clips ?? [] {
                if let preview = clipDragPreview, preview.clipId == clip.id { continue }
                let rect = clipRect(clip, row: row)
                guard rect.intersects(dirtyRect) else { continue }
                drawClip(
                    clip,
                    track: track,
                    in: rect,
                    selected: clip.id == selectedClipId,
                    ghost: false
                )
            }
        }
    }

    private func drawClip(_ clip: Clip, track: Track, in rect: NSRect, selected: Bool, ghost: Bool) {
        let color = neonColor(
            from: clip.color ?? track.color,
            fallback: Theme.defaultTrackColor
        )
        let radius = Theme.Metric.smallCornerRadius
        let wantsAudio = expectsAudio(track: track, clip: clip)
        let audioURL = wantsAudio ? audioURLsByTrack[track.id] : nil
        let missingAudio = wantsAudio && audioURL == nil

        if missingAudio {
            // A dashed outline, never a drawn-on waveform: the app must not
            // picture audio that isn't on disk.
            roundedFill(rect, radius: radius, color: color.withAlphaComponent(ghost ? 0.06 : 0.12))
            let path = NSBezierPath(
                roundedRect: rect.insetBy(dx: 1, dy: 1),
                xRadius: radius,
                yRadius: radius
            )
            path.lineWidth = 1.5
            path.setLineDash([5, 4], count: 2, phase: 0)
            color.withAlphaComponent(ghost ? 0.4 : 0.9).setStroke()
            path.stroke()
        } else {
            roundedFill(rect, radius: radius, color: color.withAlphaComponent(ghost ? 0.25 : 0.92))
            roundedStroke(rect, radius: radius, color: color.mixed(with: .black, amount: 0.25))
        }

        let foreground = missingAudio ? Theme.text : color.readableForeground

        if let audioURL, let peaks = peaks(forPath: audioURL.path), rect.width > 6 {
            NSGraphicsContext.saveGraphicsState()
            NSBezierPath(roundedRect: rect, xRadius: radius, yRadius: radius).addClip()
            drawWaveform(peaks, in: rect.insetBy(dx: 2, dy: 3), color: foreground.withAlphaComponent(0.32))
            NSGraphicsContext.restoreGraphicsState()
        }

        if selected && !ghost {
            roundedStroke(rect, radius: radius, color: Theme.text, width: 2)
        }

        guard rect.width > 26 else { return }
        let textRect = NSRect(
            x: rect.minX + 6,
            y: rect.minY + 4,
            width: max(0, rect.width - 12),
            height: 14
        )
        drawText(
            clip.name,
            in: textRect,
            color: foreground,
            font: Theme.Font.captionBold(11)
        )

        guard rect.height > 34 else { return }
        var subtitle = barsLabel(clip.bars ?? 1)
        if missingAudio { subtitle = "Sound file missing" }
        drawText(
            subtitle,
            in: NSRect(x: textRect.minX, y: rect.minY + 19, width: textRect.width, height: 14),
            color: missingAudio ? Theme.danger : foreground.withAlphaComponent(0.78),
            font: Theme.Font.caption(11)
        )
    }

    private func drawDragPreview() {
        guard let preview = clipDragPreview,
              let project = currentProject,
              preview.trackIndex >= 0,
              preview.trackIndex < project.snapshot.tracks.count else { return }
        let track = project.snapshot.tracks[preview.trackIndex]
        let rect = geometry.clipRect(
            startBar: preview.startBar,
            bars: preview.bars,
            row: preview.trackIndex
        )

        // Where it came from, faintly, so the move reads as a move.
        if let originIndex = project.snapshot.tracks.firstIndex(where: { $0.id == preview.originTrackId }),
           let originClip = (project.snapshot.tracks[originIndex].clips ?? []).first(where: { $0.id == preview.clipId }) {
            let originRect = clipRect(originClip, row: originIndex)
            roundedStroke(
                originRect,
                radius: Theme.Metric.smallCornerRadius,
                color: Theme.dim.withAlphaComponent(0.7)
            )
        }

        var previewClip = preview.clip
        previewClip.startBar = preview.startBar
        previewClip.bars = preview.bars
        drawClip(previewClip, track: track, in: rect, selected: true, ghost: false)

        let badge = "Bar \(barNumberLabel(preview.startBar)) · \(barsLabel(preview.bars))"
        let badgeRect = NSRect(x: rect.minX, y: max(geometry.rulerHeight + 2, rect.minY - 17), width: 190, height: 15)
        roundedFill(
            NSRect(x: badgeRect.minX - 2, y: badgeRect.minY - 1, width: badgeWidth(badge) + 10, height: 17),
            radius: 4,
            color: Theme.panelRaised
        )
        drawText(badge, in: badgeRect, color: Theme.text, font: Theme.Font.mono(11))
    }

    private func badgeWidth(_ text: String) -> CGFloat {
        NSString(string: text)
            .size(withAttributes: [.font: Theme.Font.mono(11)])
            .width
    }

    private func drawHeaders(project: LocalProject, dirtyRect: NSRect) {
        let headerColumn = NSRect(x: 0, y: geometry.rulerHeight, width: geometry.headerWidth, height: bounds.height)
        guard headerColumn.intersects(dirtyRect) else { return }
        let selectedTrackId = host?.selectedTrackId ?? ""

        Theme.panel.setFill()
        headerColumn.intersection(dirtyRect).fill()

        for row in 0..<rowCount {
            let rect = headerRect(row: row)
            guard rect.intersects(dirtyRect) else { continue }
            let track = project.snapshot.tracks[row]
            let isSelected = track.id == selectedTrackId
            let color = neonColor(from: track.color, fallback: Theme.defaultTrackColor)

            if isSelected {
                Theme.panelRaised.setFill()
                rect.fill()
                color.setFill()
                NSRect(x: 0, y: rect.minY, width: 3, height: rect.height).fill()
            }

            roundedFill(
                NSRect(x: 9, y: rect.minY + 10, width: 5, height: rect.height - 20),
                radius: 2.5,
                color: color
            )

            let textX: CGFloat = 21
            let textWidth = geometry.headerWidth - textX - 10
            drawText(
                track.name,
                in: NSRect(x: textX, y: rect.minY + 10, width: textWidth, height: 16),
                color: Theme.text,
                font: isSelected ? Theme.Font.emphasis(12) : Theme.Font.body(12)
            )
            drawText(
                headerSubtitle(for: track),
                in: NSRect(x: textX, y: rect.minY + 27, width: textWidth, height: 15),
                color: isMissingItsSound(track) ? Theme.danger : Theme.muted,
                font: Theme.Font.caption(11)
            )

            drawLine(
                from: NSPoint(x: 0, y: rect.maxY),
                to: NSPoint(x: geometry.headerWidth, y: rect.maxY),
                color: Theme.subtleStroke
            )
        }

        drawLine(
            from: NSPoint(x: geometry.headerWidth, y: geometry.rulerHeight),
            to: NSPoint(x: geometry.headerWidth, y: bounds.height),
            color: Theme.stroke
        )
    }

    /// A track that names an audio file which isn't where the project says it
    /// is. Worth saying out loud: it is the difference between "silent because
    /// you muted it" and "silent because the file moved".
    private func isMissingItsSound(_ track: Track) -> Bool {
        track.file != nil && audioURLsByTrack[track.id] == nil
    }

    private func headerSubtitle(for track: Track) -> String {
        var parts: [String] = []
        if let instrument = track.instrument, !instrument.isEmpty {
            parts.append(instrument)
        } else if let kind = track.kind, !kind.isEmpty {
            parts.append(kind.capitalized)
        }
        if isMissingItsSound(track) {
            parts.append("sound file missing")
        } else {
            let count = (track.clips ?? []).count
            parts.append(count == 1 ? "1 clip" : "\(count) clips")
        }
        return parts.joined(separator: " · ")
    }

    private func drawRuler(project: LocalProject, dirtyRect: NSRect) {
        let ruler = NSRect(x: 0, y: 0, width: bounds.width, height: geometry.rulerHeight)
        guard ruler.intersects(dirtyRect) else { return }

        Theme.panel.setFill()
        ruler.intersection(dirtyRect).fill()

        // Loop lane background, so the strip reads as its own control.
        Theme.panelAlt.setFill()
        loopLaneRect.fill()
        drawLine(
            from: NSPoint(x: 0, y: loopLaneRect.maxY),
            to: NSPoint(x: bounds.width, y: loopLaneRect.maxY),
            color: Theme.subtleStroke
        )
        drawLoopBrace()

        // Bar numbers, 1-based: the first bar of a song is "1", not "0".
        let numbers = rulerNumberBandRect
        let firstBar = max(0, Int(geometry.bar(forX: max(dirtyRect.minX, geometry.headerWidth))) - 4)
        let lastBar = min(Int(geometry.totalBars), Int(geometry.bar(forX: dirtyRect.maxX)) + 4)
        if lastBar >= firstBar {
            for bar in stride(from: firstBar - (firstBar % 4), through: lastBar, by: 4) {
                guard bar >= 0 else { continue }
                let x = geometry.x(forBar: Double(bar))
                guard x >= geometry.headerWidth - 1 else { continue }
                drawLine(
                    from: NSPoint(x: x, y: numbers.maxY - 6),
                    to: NSPoint(x: x, y: numbers.maxY),
                    color: Theme.stroke
                )
                drawText(
                    "\(bar + 1)",
                    in: NSRect(x: x + 4, y: numbers.minY + 1, width: 44, height: 14),
                    color: Theme.muted,
                    font: Theme.Font.mono(11)
                )
            }
        }

        drawSectionLabels()

        // The corner above the track headers: tempo, so the numbers along the
        // top have a unit attached to them.
        Theme.panel.setFill()
        NSRect(x: 0, y: 0, width: geometry.headerWidth, height: geometry.rulerHeight).fill()
        drawText(
            "\(Int(project.snapshot.bpm.rounded())) beats per minute",
            in: NSRect(x: 12, y: numbers.minY, width: geometry.headerWidth - 20, height: 16),
            color: Theme.muted,
            font: Theme.Font.caption(11)
        )
        drawLine(
            from: NSPoint(x: 0, y: geometry.rulerHeight),
            to: NSPoint(x: bounds.width, y: geometry.rulerHeight),
            color: Theme.stroke
        )
    }

    private func drawSectionLabels() {
        guard !sectionMarkers.isEmpty else { return }
        let band = sectionBandRect
        for (index, marker) in sectionMarkers.enumerated() {
            let x = geometry.x(forBar: marker.bar)
            guard x >= geometry.headerWidth - 1 else { continue }
            let nextX = index + 1 < sectionMarkers.count
                ? geometry.x(forBar: sectionMarkers[index + 1].bar)
                : bounds.width
            let width = max(0, min(nextX - x - 6, bounds.width - x - 6))
            guard width > 12 else { continue }
            drawLine(
                from: NSPoint(x: x, y: band.minY),
                to: NSPoint(x: x, y: band.maxY),
                color: Theme.accent
            )
            drawText(
                marker.label,
                in: NSRect(x: x + 4, y: band.minY + 1, width: width, height: 13),
                color: Theme.accent,
                font: Theme.Font.captionBold(11)
            )
        }
    }

    private func drawLoopBrace() {
        guard let loop = effectiveLoop(), let handles = loopHandleRects() else { return }
        let body = handles.body
        guard body.width > 0 else { return }
        roundedFill(body, radius: 3, color: Theme.accent.withAlphaComponent(0.35))
        roundedStroke(body, radius: 3, color: Theme.accent)
        Theme.accent.setFill()
        NSRect(x: body.minX, y: body.minY + 2, width: 3, height: body.height - 4).fill()
        NSRect(x: body.maxX - 3, y: body.minY + 2, width: 3, height: body.height - 4).fill()

        let label = "Loop \(barNumberLabel(loop.start))–\(barNumberLabel(loop.end))"
        if body.width > badgeWidth(label) + 18 {
            drawText(
                label,
                in: NSRect(x: body.minX + 8, y: body.minY, width: body.width - 14, height: 13),
                color: Theme.text,
                font: Theme.Font.caption(11)
            )
        }
    }

    private func drawPlayhead() {
        let bar = displayedPlayheadBar
        let x = geometry.x(forBar: bar)
        guard x >= geometry.headerWidth - 1 else { return }
        drawLine(
            from: NSPoint(x: x, y: TimelineView.loopLaneHeight),
            to: NSPoint(x: x, y: bounds.height),
            color: Theme.playhead,
            width: 1.5
        )
        let handle = NSBezierPath()
        let top = rulerNumberBandRect.minY
        handle.move(to: NSPoint(x: x - 6, y: top))
        handle.line(to: NSPoint(x: x + 6, y: top))
        handle.line(to: NSPoint(x: x, y: top + 9))
        handle.close()
        Theme.playhead.setFill()
        handle.fill()
    }

    private func drawEmptyProjectMessage() {
        let text = "This song has no tracks yet. Use Track ▸ Add Track, or import a sound to start."
        drawCentredMessage(text, in: bounds)
    }

    private func drawEmptyArrangementMessage() {
        let text = "Nothing arranged yet. Pick the Draw tool and click a track row to add your first block, or import a sound."
        drawCentredMessage(text, in: visibleRect.intersection(gridRect))
    }

    private func drawCentredMessage(_ text: String, in area: NSRect) {
        guard area.width > 60, area.height > 40 else { return }
        let width = min(420, area.width - 32)
        let rect = NSRect(
            x: area.midX - width / 2,
            y: area.midY - 30,
            width: width,
            height: 64
        )
        drawText(
            text,
            in: rect,
            color: Theme.muted,
            font: Theme.Font.body(12),
            alignment: .center,
            lineBreak: .byWordWrapping
        )
    }

    private func drawFocusRingIfNeeded() {
        guard window?.firstResponder === self, window?.isKeyWindow == true else { return }
        let rect = visibleRect.insetBy(dx: 1.5, dy: 1.5)
        guard rect.width > 4, rect.height > 4 else { return }
        roundedStroke(rect, radius: Theme.Metric.cornerRadius, color: Theme.accent.withAlphaComponent(0.65), width: 2)
    }

    // MARK: - Waveforms

    private func expectsAudio(track: Track, clip: Clip?) -> Bool {
        if track.file != nil { return true }
        if (track.kind ?? "").lowercased() == "audio" { return true }
        if let type = clip?.type?.lowercased(), type == "audio" || type == "sample" { return true }
        return false
    }

    /// Peaks for a file, or nil while they are still being read. The read
    /// happens once per file, off the main thread, and the result is cached —
    /// drawing never touches the disk.
    private func peaks(forPath path: String) -> [Float]? {
        if let cached = TimelineView.peakCache[path] {
            return cached.isEmpty ? nil : cached
        }
        guard !pendingPeakLoads.contains(path) else { return nil }
        pendingPeakLoads.insert(path)
        let url = URL(fileURLWithPath: path)
        DispatchQueue.global(qos: .userInitiated).async {
            let peaks = TimelineView.readPeaks(from: url)
            DispatchQueue.main.async { [weak self] in
                TimelineView.peakCache[path] = peaks
                self?.pendingPeakLoads.remove(path)
                self?.needsDisplay = true
            }
        }
        return nil
    }

    private static func readPeaks(from url: URL) -> [Float] {
        guard let file = try? AVAudioFile(forReading: url) else { return [] }
        let format = file.processingFormat
        let totalFrames = file.length
        guard totalFrames > 0, format.channelCount > 0 else { return [] }

        let chunk = AVAudioFrameCount(min(Int64(262_144), totalFrames))
        guard chunk > 0, let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: chunk) else { return [] }

        var peaks = [Float](repeating: 0, count: peakResolution)
        var frameIndex: Int64 = 0
        let channelCount = Int(format.channelCount)

        while frameIndex < totalFrames {
            do {
                try file.read(into: buffer)
            } catch {
                break
            }
            let frames = Int(buffer.frameLength)
            if frames == 0 { break }
            guard let channels = buffer.floatChannelData else { break }
            for offset in 0..<frames {
                var magnitude: Float = 0
                for channel in 0..<channelCount {
                    magnitude = max(magnitude, abs(channels[channel][offset]))
                }
                let position = Double(frameIndex + Int64(offset)) / Double(totalFrames)
                let slot = min(peakResolution - 1, max(0, Int(position * Double(peakResolution))))
                if magnitude > peaks[slot] { peaks[slot] = magnitude }
            }
            frameIndex += Int64(frames)
        }
        return peaks
    }

    private func drawWaveform(_ peaks: [Float], in rect: NSRect, color: NSColor) {
        guard peaks.count > 1, rect.width > 2, rect.height > 4 else { return }
        let columns = max(2, min(Int(rect.width), 600))
        let half = rect.height / 2
        let midY = rect.midY
        let path = NSBezierPath()

        func value(at column: Int) -> CGFloat {
            let t = Double(column) / Double(columns - 1)
            let index = min(peaks.count - 1, max(0, Int(t * Double(peaks.count - 1))))
            return max(0.02, min(1, CGFloat(peaks[index])))
        }

        for column in 0..<columns {
            let x = rect.minX + rect.width * CGFloat(column) / CGFloat(columns - 1)
            let y = midY - value(at: column) * half
            if column == 0 { path.move(to: NSPoint(x: x, y: y)) } else { path.line(to: NSPoint(x: x, y: y)) }
        }
        for column in stride(from: columns - 1, through: 0, by: -1) {
            let x = rect.minX + rect.width * CGFloat(column) / CGFloat(columns - 1)
            path.line(to: NSPoint(x: x, y: midY + value(at: column) * half))
        }
        path.close()
        color.setFill()
        path.fill()
    }

    // MARK: - Mouse

    public override func mouseDown(with event: NSEvent) {
        window?.makeFirstResponder(self)
        let point = convert(event.locationInWindow, from: nil)

        if point.y < geometry.rulerHeight {
            handleRulerMouseDown(event, at: point)
            return
        }
        if point.x < geometry.headerWidth {
            handleHeaderMouseDown(event, at: point)
            return
        }
        handleGridMouseDown(event, at: point)
    }

    private func handleHeaderMouseDown(_ event: NSEvent, at point: NSPoint) {
        guard let project = currentProject, let row = rowIndex(at: point) else { return }
        host?.selectTrack(project.snapshot.tracks[row].id)
        if event.clickCount == 2 {
            host?.requestFocus(on: .piano)
        }
    }

    private func handleRulerMouseDown(_ event: NSEvent, at point: NSPoint) {
        if loopLaneRect.contains(point) {
            guard let loop = effectiveLoop() else {
                StatusCenter.shared.info(
                    AppEnvironment.shared.help(
                        "Looping is off. Switch Loop on in the toolbar, then drag along this strip to choose the bars that repeat.",
                        term: "Loop"
                    )
                )
                return
            }
            if let handles = loopHandleRects() {
                if handles.start.contains(point) {
                    runLoopDrag(from: point, loop: loop, part: .start)
                    return
                }
                if handles.end.contains(point) {
                    runLoopDrag(from: point, loop: loop, part: .end)
                    return
                }
                if handles.body.contains(point) {
                    runLoopDrag(from: point, loop: loop, part: .body)
                    return
                }
            }
            // Empty part of the lane: drag out a brand new range.
            runLoopCreateDrag(from: point)
            return
        }
        if sectionBandRect.contains(point), let marker = sectionMarker(at: point) {
            host?.seek(toBar: marker.bar)
            StatusCenter.shared.info("Moved the playhead to \(marker.label), bar \(barNumberLabel(marker.bar)).")
            return
        }
        runScrubDrag(from: event)
    }

    private func sectionMarker(at point: NSPoint) -> SectionMarker? {
        for (index, marker) in sectionMarkers.enumerated() {
            let x = geometry.x(forBar: marker.bar)
            let nextX = index + 1 < sectionMarkers.count
                ? geometry.x(forBar: sectionMarkers[index + 1].bar)
                : bounds.width
            if point.x >= x, point.x < nextX { return marker }
        }
        return nil
    }

    private func handleGridMouseDown(_ event: NSEvent, at point: NSPoint) {
        guard let host, let project = currentProject else { return }
        guard let row = rowIndex(at: point) else {
            host.clearClipSelection()
            return
        }
        let track = project.snapshot.tracks[row]
        let hit = clipHit(at: point)

        switch host.activeTool {
        case .erase:
            if let hit {
                deleteClip(trackId: hit.trackId, clipId: hit.clip.id, name: hit.clip.name)
            } else {
                StatusCenter.shared.info("Nothing to erase there. Click a block to delete it.")
            }
            return

        case .draw:
            if let hit {
                host.selectClip(trackId: hit.trackId, clipId: hit.clip.id)
                runClipDrag(startEvent: event, hit: hit)
            } else {
                addClip(onTrack: track, atBar: geometry.bar(forX: point.x), bypassSnap: event.modifierFlags.contains(.option))
            }
            return

        case .select:
            guard let hit else {
                host.selectTrack(track.id)
                host.clearClipSelection()
                return
            }
            host.selectClip(trackId: hit.trackId, clipId: hit.clip.id)
            if event.clickCount == 2 {
                host.requestFocus(on: .piano)
                StatusCenter.shared.info("Opened “\(hit.clip.name)” in Notes, where you edit it note by note.")
                return
            }
            runClipDrag(startEvent: event, hit: hit)
        }
    }

    // MARK: - Drag loops

    private struct ClipDragPreview {
        let clipId: String
        let originTrackId: String
        var clip: Clip
        var trackIndex: Int
        var startBar: Double
        var bars: Double
    }

    private func runClipDrag(startEvent: NSEvent, hit: ClipHit) {
        guard let host else { return }
        let origin = convert(startEvent.locationInWindow, from: nil)
        let originalStart = max(0, hit.clip.startBar ?? 0)
        let originalBars = max(TimelineView.minimumClipBars, hit.clip.bars ?? 1)

        var startBar = originalStart
        var bars = originalBars
        var trackIndex = hit.trackIndex
        var moved = false

        while let event = window?.nextEvent(matching: [.leftMouseDragged, .leftMouseUp]) {
            if event.type == .leftMouseUp { break }
            autoscroll(with: event)
            let point = convert(event.locationInWindow, from: nil)
            let bypassSnap = event.modifierFlags.contains(.option)
            let deltaBars = Double((point.x - origin.x) / max(1, geometry.pixelsPerBar))

            switch hit.mode {
            case .move:
                startBar = max(0, snapped(originalStart + deltaBars, bypass: bypassSnap))
                bars = originalBars
                if let row = geometry.row(forY: point.y) {
                    trackIndex = max(0, min(rowCount - 1, row))
                }
            case .resizeStart:
                let end = originalStart + originalBars
                let proposed = max(0, snapped(originalStart + deltaBars, bypass: bypassSnap))
                startBar = min(proposed, end - TimelineView.minimumClipBars)
                bars = max(TimelineView.minimumClipBars, end - startBar)
            case .resizeEnd:
                startBar = originalStart
                let proposed = snapped(originalStart + originalBars + deltaBars, bypass: bypassSnap)
                bars = max(TimelineView.minimumClipBars, proposed - originalStart)
            }

            moved = true
            clipDragPreview = ClipDragPreview(
                clipId: hit.clip.id,
                originTrackId: hit.trackId,
                clip: hit.clip,
                trackIndex: trackIndex,
                startBar: startBar,
                bars: bars
            )
            needsDisplay = true
        }

        clipDragPreview = nil
        needsDisplay = true

        guard moved else { return }
        let sameBar = abs(startBar - originalStart) < 0.0001
        let sameLength = abs(bars - originalBars) < 0.0001
        let sameTrack = trackIndex == hit.trackIndex
        // Nothing actually changed — leave the undo stack alone.
        guard !(sameBar && sameLength && sameTrack) else { return }

        guard let project = currentProject,
              trackIndex >= 0,
              trackIndex < project.snapshot.tracks.count else { return }
        let destination = project.snapshot.tracks[trackIndex]
        let clipId = hit.clip.id
        let clipName = hit.clip.name
        let sourceTrackId = hit.trackId
        let destinationTrackId = destination.id
        let finalStart = startBar
        let finalBars = bars
        let actionName = hit.mode == .move ? "Move Clip" : "Resize Clip"

        host.edit(actionName) { project in
            guard let sourceIndex = project.snapshot.tracks.firstIndex(where: { $0.id == sourceTrackId }),
                  let clipIndex = (project.snapshot.tracks[sourceIndex].clips ?? []).firstIndex(where: { $0.id == clipId })
            else { return }
            var clip = project.snapshot.tracks[sourceIndex].clips![clipIndex]
            clip.startBar = finalStart
            clip.bars = finalBars
            if sourceTrackId == destinationTrackId {
                project.snapshot.tracks[sourceIndex].clips![clipIndex] = clip
            } else {
                project.snapshot.tracks[sourceIndex].clips!.remove(at: clipIndex)
                guard let targetIndex = project.snapshot.tracks.firstIndex(where: { $0.id == destinationTrackId }) else { return }
                var clips = project.snapshot.tracks[targetIndex].clips ?? []
                clips.append(clip)
                project.snapshot.tracks[targetIndex].clips = clips
                project.snapshot.selectedTrackId = destinationTrackId
            }
            project.snapshot.selectedClipId = clipId
        }

        if hit.mode == .move {
            let where_ = sameTrack
                ? "bar \(barNumberLabel(finalStart))"
                : "bar \(barNumberLabel(finalStart)) on \(destination.name)"
            StatusCenter.shared.success("Moved “\(clipName)” to \(where_). ⌘Z undoes it.")
        } else {
            StatusCenter.shared.success(
                "“\(clipName)” now runs from bar \(barNumberLabel(finalStart)) and is \(barsLabel(finalBars)) long. ⌘Z undoes it."
            )
        }
    }

    private enum LoopDragPart { case start, end, body }

    private func runLoopDrag(from origin: NSPoint, loop: (start: Double, end: Double), part: LoopDragPart) {
        guard let host else { return }
        let originalStart = loop.start
        let originalEnd = loop.end
        var start = originalStart
        var end = originalEnd
        var moved = false

        while let event = window?.nextEvent(matching: [.leftMouseDragged, .leftMouseUp]) {
            if event.type == .leftMouseUp { break }
            autoscroll(with: event)
            let point = convert(event.locationInWindow, from: nil)
            let bypassSnap = event.modifierFlags.contains(.option)
            let deltaBars = Double((point.x - origin.x) / max(1, geometry.pixelsPerBar))

            switch part {
            case .start:
                start = min(snapped(originalStart + deltaBars, bypass: bypassSnap), originalEnd - 1)
                end = originalEnd
            case .end:
                start = originalStart
                end = max(snapped(originalEnd + deltaBars, bypass: bypassSnap), originalStart + 1)
            case .body:
                let length = originalEnd - originalStart
                start = max(0, snapped(originalStart + deltaBars, bypass: bypassSnap))
                end = start + length
            }
            start = max(0, start)
            end = max(start + 1, end)
            moved = true
            loopPreview = (start, end)
            setNeedsDisplay(NSRect(x: 0, y: 0, width: bounds.width, height: geometry.rulerHeight))
        }

        loopPreview = nil
        needsDisplay = true

        guard moved,
              abs(start - originalStart) > 0.0001 || abs(end - originalEnd) > 0.0001 else { return }
        let finalStart = start
        let finalEnd = end
        host.edit("Set Loop Range") { project in
            project.snapshot.loopStartBar = finalStart
            project.snapshot.loopEndBar = finalEnd
            project.snapshot.loopEnabled = true
        }
        StatusCenter.shared.success(
            "Loop now repeats bars \(barNumberLabel(finalStart)) to \(barNumberLabel(finalEnd)). ⌘Z undoes it."
        )
    }

    /// Drag a new loop range out of empty space in the loop lane, the way you
    /// would sweep out a selection.
    private func runLoopCreateDrag(from origin: NSPoint) {
        guard let host else { return }
        let anchor = snapped(geometry.bar(forX: origin.x), bypass: false)
        var start = anchor
        var end = anchor + 1
        var moved = false

        while let event = window?.nextEvent(matching: [.leftMouseDragged, .leftMouseUp]) {
            if event.type == .leftMouseUp { break }
            autoscroll(with: event)
            let point = convert(event.locationInWindow, from: nil)
            let bar = snapped(geometry.bar(forX: point.x), bypass: event.modifierFlags.contains(.option))
            start = max(0, min(anchor, bar))
            end = max(start + 1, max(anchor, bar))
            moved = true
            loopPreview = (start, end)
            setNeedsDisplay(NSRect(x: 0, y: 0, width: bounds.width, height: geometry.rulerHeight))
        }

        loopPreview = nil
        needsDisplay = true
        guard moved else { return }

        let finalStart = start
        let finalEnd = end
        host.edit("Set Loop Range") { project in
            project.snapshot.loopStartBar = finalStart
            project.snapshot.loopEndBar = finalEnd
            project.snapshot.loopEnabled = true
        }
        StatusCenter.shared.success(
            "Loop now repeats bars \(barNumberLabel(finalStart)) to \(barNumberLabel(finalEnd)). ⌘Z undoes it."
        )
    }

    private func runScrubDrag(from startEvent: NSEvent) {
        guard let host else { return }
        func seek(_ event: NSEvent) {
            let point = convert(event.locationInWindow, from: nil)
            let raw = geometry.bar(forX: point.x)
            host.seek(toBar: snapped(raw, bypass: event.modifierFlags.contains(.option)))
        }
        seek(startEvent)
        while let event = window?.nextEvent(matching: [.leftMouseDragged, .leftMouseUp]) {
            if event.type == .leftMouseUp { break }
            autoscroll(with: event)
            seek(event)
        }
    }

    private func snapped(_ bars: Double, bypass: Bool) -> Double {
        guard !bypass, let host else { return max(0, bars) }
        return host.snapValue.snap(bars: bars)
    }

    // MARK: - Edits

    private func addClip(onTrack track: Track, atBar rawBar: Double, bypassSnap: Bool) {
        guard let host else { return }
        let start = max(0, snapped(rawBar, bypass: bypassSnap))
        let snapUnit = host.snapValue.bars
        let length = max(4, snapUnit)
        let clip = Clip(
            id: makeId("clip"),
            name: "\(track.name) bar \(barNumberLabel(start))",
            startBar: start,
            bars: length,
            lane: track.id,
            color: track.color,
            type: track.kind
        )
        let trackId = track.id
        host.edit("Add Clip") { project in
            guard let index = project.snapshot.tracks.firstIndex(where: { $0.id == trackId }) else { return }
            var clips = project.snapshot.tracks[index].clips ?? []
            clips.append(clip)
            project.snapshot.tracks[index].clips = clips
            project.snapshot.selectedTrackId = trackId
            project.snapshot.selectedClipId = clip.id
        }
        StatusCenter.shared.success(
            "Added a \(barsLabel(length)) block on \(track.name) at bar \(barNumberLabel(start)). ⌘Z undoes it."
        )
    }

    private func deleteClip(trackId: String, clipId: String, name: String) {
        guard let host else { return }
        host.edit("Delete Clip") { project in
            guard let index = project.snapshot.tracks.firstIndex(where: { $0.id == trackId }) else { return }
            project.snapshot.tracks[index].clips?.removeAll { $0.id == clipId }
            if project.snapshot.selectedClipId == clipId {
                project.snapshot.selectedClipId = ""
            }
        }
        StatusCenter.shared.success("Deleted “\(name)”. ⌘Z brings it back.")
    }

    private func duplicateClip(trackId: String, clipId: String) {
        guard let host,
              let project = currentProject,
              let track = project.track(id: trackId),
              let clip = (track.clips ?? []).first(where: { $0.id == clipId }) else { return }
        let bars = max(TimelineView.minimumClipBars, clip.bars ?? 1)
        let start = max(0, clip.startBar ?? 0) + bars
        var copy = clip
        copy.id = makeId("clip")
        copy.startBar = start
        let newId = copy.id
        host.edit("Duplicate Clip") { project in
            guard let index = project.snapshot.tracks.firstIndex(where: { $0.id == trackId }) else { return }
            var clips = project.snapshot.tracks[index].clips ?? []
            clips.append(copy)
            project.snapshot.tracks[index].clips = clips
            project.snapshot.selectedClipId = newId
        }
        StatusCenter.shared.success(
            "Copied “\(clip.name)” to bar \(barNumberLabel(start)). ⌘Z undoes it."
        )
    }

    private func splitClip(trackId: String, clipId: String) {
        guard let host,
              let project = currentProject,
              let track = project.track(id: trackId),
              let clip = (track.clips ?? []).first(where: { $0.id == clipId }) else { return }
        let start = max(0, clip.startBar ?? 0)
        let bars = max(TimelineView.minimumClipBars, clip.bars ?? 1)
        let playhead = host.playheadBar
        guard playhead > start + 0.01, playhead < start + bars - 0.01 else {
            StatusCenter.shared.warning(
                "Move the playhead inside “\(clip.name)” first — it splits the block at the red line."
            )
            return
        }
        var tail = clip
        tail.id = makeId("clip")
        tail.startBar = playhead
        tail.bars = start + bars - playhead
        let headBars = playhead - start
        let tailId = tail.id

        host.edit("Split Clip") { project in
            guard let index = project.snapshot.tracks.firstIndex(where: { $0.id == trackId }),
                  let clipIndex = (project.snapshot.tracks[index].clips ?? []).firstIndex(where: { $0.id == clipId })
            else { return }
            project.snapshot.tracks[index].clips![clipIndex].bars = headBars
            project.snapshot.tracks[index].clips!.append(tail)
            project.snapshot.selectedClipId = tailId
        }
        StatusCenter.shared.success(
            "Split “\(clip.name)” at bar \(barNumberLabel(playhead)) into two blocks. ⌘Z undoes it."
        )
    }

    private func renameClip(trackId: String, clipId: String, currentName: String) {
        guard let host else { return }
        let field = NSTextField(string: currentName)
        field.frame = NSRect(x: 0, y: 0, width: 260, height: 24)
        field.font = Theme.Font.body()
        field.setAccessibilityLabel("Clip name")

        let alert = NSAlert()
        alert.messageText = "Rename this block"
        alert.informativeText = "The name shows on the block in the arrangement. Something like “Chorus drums” makes it easy to find later."
        alert.accessoryView = field
        alert.addButton(withTitle: "Rename")
        alert.addButton(withTitle: "Cancel")

        let commit: (NSApplication.ModalResponse) -> Void = { response in
            guard response == .alertFirstButtonReturn else { return }
            let name = field.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !name.isEmpty, name != currentName else { return }
            host.edit("Rename Clip") { project in
                guard let index = project.snapshot.tracks.firstIndex(where: { $0.id == trackId }),
                      let clipIndex = (project.snapshot.tracks[index].clips ?? []).firstIndex(where: { $0.id == clipId })
                else { return }
                project.snapshot.tracks[index].clips![clipIndex].name = name
            }
            StatusCenter.shared.success("Renamed the block to “\(name)”. ⌘Z undoes it.")
        }

        if let window {
            alert.beginSheetModal(for: window, completionHandler: commit)
        } else {
            commit(alert.runModal())
        }
    }

    private func addTrack() {
        guard let host, let project = currentProject else { return }
        let number = project.snapshot.tracks.count + 1
        let palette = ["#60c8f8", "#9ef0c0", "#f8d46a", "#f59fcb", "#c4a5ff", "#ffa06a"]
        let id = makeId("track")
        let track = Track(
            id: id,
            name: "Track \(number)",
            kind: "audio",
            color: palette[number % palette.count],
            gain: 0.82,
            pan: 0,
            steps: [],
            instrument: "Empty",
            clips: [],
            effects: [],
            sampleEdit: normalizeSampleEdit(nil)
        )
        host.edit("Add Track") { project in
            project.snapshot.tracks.append(track)
            project.snapshot.selectedTrackId = id
        }
        StatusCenter.shared.success("Added Track \(number). Draw a block on its row to fill it. ⌘Z undoes it.")
    }

    // MARK: - Keyboard

    private enum KeyCode {
        static let delete: UInt16 = 51
        static let forwardDelete: UInt16 = 117
        static let escape: UInt16 = 53
        static let leftArrow: UInt16 = 123
        static let rightArrow: UInt16 = 124
        static let downArrow: UInt16 = 125
        static let upArrow: UInt16 = 126
    }

    public override func keyDown(with event: NSEvent) {
        let shift = event.modifierFlags.contains(.shift)
        switch event.keyCode {
        case KeyCode.leftArrow:
            nudgeSelectedClip(bars: -nudgeStep(shift: shift), rows: 0)
        case KeyCode.rightArrow:
            nudgeSelectedClip(bars: nudgeStep(shift: shift), rows: 0)
        case KeyCode.upArrow:
            nudgeSelectedClip(bars: 0, rows: -1)
        case KeyCode.downArrow:
            nudgeSelectedClip(bars: 0, rows: 1)
        case KeyCode.delete, KeyCode.forwardDelete:
            deleteSelectedClip()
        case KeyCode.escape:
            host?.clearClipSelection()
        default:
            super.keyDown(with: event)
        }
    }

    public override func cancelOperation(_ sender: Any?) {
        host?.clearClipSelection()
    }

    private func nudgeStep(shift: Bool) -> Double {
        if shift { return 1 }
        let unit = host?.snapValue.bars ?? 0
        return unit > 0 ? unit : 0.25
    }

    private func selectedClipLocation() -> (trackIndex: Int, track: Track, clip: Clip)? {
        guard let project = currentProject, let host, !host.selectedClipId.isEmpty else { return nil }
        for (index, track) in project.snapshot.tracks.enumerated() {
            if let clip = (track.clips ?? []).first(where: { $0.id == host.selectedClipId }) {
                return (index, track, clip)
            }
        }
        return nil
    }

    private func deleteSelectedClip() {
        guard let found = selectedClipLocation() else {
            StatusCenter.shared.info("Select a block first, then press Delete to remove it.")
            return
        }
        deleteClip(trackId: found.track.id, clipId: found.clip.id, name: found.clip.name)
    }

    private func nudgeSelectedClip(bars deltaBars: Double, rows deltaRows: Int) {
        guard let host, let found = selectedClipLocation() else {
            StatusCenter.shared.info("Select a block first — then the arrow keys move it.")
            return
        }
        guard let project = currentProject else { return }
        let start = max(0, found.clip.startBar ?? 0)
        let newStart = max(0, start + deltaBars)
        let targetIndex = max(0, min(project.snapshot.tracks.count - 1, found.trackIndex + deltaRows))
        guard abs(newStart - start) > 0.0001 || targetIndex != found.trackIndex else { return }

        let clipId = found.clip.id
        let clipName = found.clip.name
        let sourceTrackId = found.track.id
        let destination = project.snapshot.tracks[targetIndex]
        let destinationTrackId = destination.id

        host.edit("Move Clip") { project in
            guard let sourceIndex = project.snapshot.tracks.firstIndex(where: { $0.id == sourceTrackId }),
                  let clipIndex = (project.snapshot.tracks[sourceIndex].clips ?? []).firstIndex(where: { $0.id == clipId })
            else { return }
            var clip = project.snapshot.tracks[sourceIndex].clips![clipIndex]
            clip.startBar = newStart
            if sourceTrackId == destinationTrackId {
                project.snapshot.tracks[sourceIndex].clips![clipIndex] = clip
            } else {
                project.snapshot.tracks[sourceIndex].clips!.remove(at: clipIndex)
                guard let index = project.snapshot.tracks.firstIndex(where: { $0.id == destinationTrackId }) else { return }
                var clips = project.snapshot.tracks[index].clips ?? []
                clips.append(clip)
                project.snapshot.tracks[index].clips = clips
                project.snapshot.selectedTrackId = destinationTrackId
            }
            project.snapshot.selectedClipId = clipId
        }

        // Keep the thing the user is steering on screen.
        var moved = found.clip
        moved.startBar = newStart
        scrollToVisible(clipRect(moved, row: targetIndex).insetBy(dx: -24, dy: -12))

        if targetIndex != found.trackIndex {
            StatusCenter.shared.success("Moved “\(clipName)” to \(destination.name). ⌘Z undoes it.")
        } else {
            StatusCenter.shared.success("Moved “\(clipName)” to bar \(barNumberLabel(newStart)). ⌘Z undoes it.")
        }
    }

    // MARK: - Cursors

    public override func resetCursorRects() {
        discardCursorRects()
        let visible = visibleRect
        guard visible.width > 0, visible.height > 0 else { return }

        func add(_ rect: NSRect, _ cursor: NSCursor) {
            let clipped = rect.intersection(visible)
            guard clipped.width > 0.5, clipped.height > 0.5 else { return }
            addCursorRect(clipped, cursor: cursor)
        }

        if let handles = loopHandleRects() {
            add(handles.body, .openHand)
            add(handles.start, .resizeLeftRight)
            add(handles.end, .resizeLeftRight)
        }

        guard let project = currentProject else { return }

        if host?.activeTool == .draw {
            add(gridRect, .crosshair)
        } else if host?.activeTool == .erase {
            add(gridRect, .disappearingItem)
        }

        for row in 0..<rowCount {
            let rowRect = geometry.rowRect(row, width: bounds.width)
            guard rowRect.intersects(visible) else { continue }
            for clip in project.snapshot.tracks[row].clips ?? [] {
                let rect = clipRect(clip, row: row)
                guard rect.intersects(visible) else { continue }
                let edge = min(ClipDragMode.edgeWidth, rect.width / 3)
                add(rect, .openHand)
                add(NSRect(x: rect.minX, y: rect.minY, width: edge, height: rect.height), .resizeLeftRight)
                add(NSRect(x: rect.maxX - edge, y: rect.minY, width: edge, height: rect.height), .resizeLeftRight)
            }
        }
    }

    // MARK: - Tooltips

    private func rebuildToolTipRegion() {
        removeAllToolTips()
        guard bounds.width > 0, bounds.height > 0 else { return }
        addToolTip(bounds, owner: self, userData: nil)
    }

    public func view(
        _ view: NSView,
        stringForToolTip tag: NSView.ToolTipTag,
        point: NSPoint,
        userData data: UnsafeMutableRawPointer?
    ) -> String {
        let environment = AppEnvironment.shared

        if loopLaneRect.contains(point) {
            return environment.help(
                "The loop strip. Drag either end to change where the repeat starts and stops; drag the middle to slide the whole range.",
                term: "Loop"
            )
        }
        if sectionBandRect.contains(point) {
            if let marker = sectionMarker(at: point) {
                return "\(marker.label) starts at bar \(barNumberLabel(marker.bar)). Click to move the playhead here."
            }
            return "Song sections, taken from the recipe."
        }
        if point.y < geometry.rulerHeight {
            return environment.help(
                "Bar numbers. Click or drag to move the playhead. Hold Option to ignore the grid.",
                term: "Bar"
            )
        }
        if point.x < geometry.headerWidth {
            guard let project = currentProject, let row = rowIndex(at: point) else {
                return environment.help("Track names. Click one to work on that track.", term: "Track")
            }
            let track = project.snapshot.tracks[row]
            return environment.help(
                "\(track.name) — \(headerSubtitle(for: track)). Click to select this track.",
                term: "Track"
            )
        }
        if let hit = clipHit(at: point) {
            let start = max(0, hit.clip.startBar ?? 0)
            let bars = max(TimelineView.minimumClipBars, hit.clip.bars ?? 1)
            return environment.help(
                "“\(hit.clip.name)” on \(hit.trackName), bar \(barNumberLabel(start)) to bar \(barNumberLabel(start + bars)). "
                    + "Drag to move it, drag an edge to change its length, double-click to edit its notes.",
                term: "Clip"
            )
        }
        switch host?.activeTool ?? .select {
        case .draw:
            return "Click to add a block here, snapped to the grid."
        case .erase:
            return "Click a block to delete it."
        case .select:
            return environment.help(
                "Empty space on this track. Switch to the Draw tool to add a block here.",
                term: "Clip"
            )
        }
    }

    // MARK: - Context menu

    public override func menu(for event: NSEvent) -> NSMenu? {
        let point = convert(event.locationInWindow, from: nil)
        contextPoint = point
        contextClip = nil

        let menu = NSMenu(title: "Arrangement")
        menu.autoenablesItems = false

        if let hit = clipHit(at: point) {
            contextClip = (hit.trackId, hit.clip.id, hit.clip.name)
            host?.selectClip(trackId: hit.trackId, clipId: hit.clip.id)

            addItem(to: menu, title: "Delete Clip", action: #selector(contextDeleteClip(_:)),
                    help: "Remove this block. ⌘Z brings it back.")
            addItem(to: menu, title: "Duplicate Clip", action: #selector(contextDuplicateClip(_:)),
                    help: "Place a copy of this block straight after it.")
            addItem(to: menu, title: "Rename Clip…", action: #selector(contextRenameClip(_:)),
                    help: "Give this block a name you'll recognise later.")
            addItem(to: menu, title: "Try Alternatives…", action: #selector(contextTryAlternatives(_:)),
                    help: "Hear three different takes on this block and pick one.")

            let start = max(0, hit.clip.startBar ?? 0)
            let bars = max(TimelineView.minimumClipBars, hit.clip.bars ?? 1)
            let playhead = host?.playheadBar ?? 0
            let canSplit = playhead > start + 0.01 && playhead < start + bars - 0.01
            let split = addItem(to: menu, title: "Split at Playhead", action: #selector(contextSplitClip(_:)),
                                help: canSplit
                                    ? "Cut this block in two at the red playhead line."
                                    : "Move the playhead inside this block to split it.")
            split.isEnabled = canSplit
        } else {
            let canAdd = rowIndex(at: point) != nil && point.x >= geometry.headerWidth
            let add = addItem(to: menu, title: "Add Clip Here", action: #selector(contextAddClip(_:)),
                              help: "Create a block on this track at this bar.")
            add.isEnabled = canAdd
            addItem(to: menu, title: "Add Track", action: #selector(contextAddTrack(_:)),
                    help: "Add an empty track to the bottom of the song.")
        }
        return menu
    }

    @objc private func contextTryAlternatives(_ sender: Any?) {
        NSApp.sendAction(#selector(DocumentWindowController.tryAlternatives(_:)), to: nil, from: self)
    }

    @discardableResult
    private func addItem(to menu: NSMenu, title: String, action: Selector, help: String) -> NSMenuItem {
        let item = NSMenuItem(title: title, action: action, keyEquivalent: "")
        item.target = self
        item.isEnabled = true
        item.toolTip = help
        item.setAccessibilityHelp(help)
        menu.addItem(item)
        return item
    }

    @objc private func contextDeleteClip(_ sender: Any?) {
        guard let target = contextClip else { return }
        deleteClip(trackId: target.trackId, clipId: target.clipId, name: target.name)
    }

    @objc private func contextDuplicateClip(_ sender: Any?) {
        guard let target = contextClip else { return }
        duplicateClip(trackId: target.trackId, clipId: target.clipId)
    }

    @objc private func contextRenameClip(_ sender: Any?) {
        guard let target = contextClip else { return }
        renameClip(trackId: target.trackId, clipId: target.clipId, currentName: target.name)
    }

    @objc private func contextSplitClip(_ sender: Any?) {
        guard let target = contextClip else { return }
        splitClip(trackId: target.trackId, clipId: target.clipId)
    }

    @objc private func contextAddClip(_ sender: Any?) {
        guard let project = currentProject, let row = rowIndex(at: contextPoint) else { return }
        addClip(
            onTrack: project.snapshot.tracks[row],
            atBar: geometry.bar(forX: contextPoint.x),
            bypassSnap: false
        )
    }

    @objc private func contextAddTrack(_ sender: Any?) {
        addTrack()
    }

    // MARK: - Accessibility

    public override func accessibilityChildren() -> [Any]? {
        accessibilityChildElements
    }

    public override func accessibilityLabel() -> String? {
        "Arrangement"
    }

    public override func accessibilityRole() -> NSAccessibility.Role? {
        .group
    }

    private func rebuildAccessibilityChildren() {
        guard let project = currentProject else {
            accessibilityChildElements = []
            return
        }
        var elements: [NSAccessibilityElement] = []

        for (row, track) in project.snapshot.tracks.enumerated() {
            let header = NSAccessibilityElement()
            header.setAccessibilityRole(.button)
            header.setAccessibilityParent(self)
            header.setAccessibilityLabel("Track \(row + 1), \(track.name)")
            header.setAccessibilityHelp("\(headerSubtitle(for: track)). Activate to select this track.")
            header.setAccessibilityFrameInParentSpace(accessibilityFrame(for: headerRect(row: row)))
            elements.append(header)

            for clip in track.clips ?? [] {
                let start = max(0, clip.startBar ?? 0)
                let bars = max(TimelineView.minimumClipBars, clip.bars ?? 1)
                let element = NSAccessibilityElement()
                element.setAccessibilityRole(.button)
                element.setAccessibilityParent(self)
                element.setAccessibilityLabel(
                    "\(track.name), clip \(clip.name), bar \(barNumberLabel(start)) to bar \(barNumberLabel(start + bars))"
                )
                element.setAccessibilityHelp(
                    "Arrow keys move the selected clip. Delete removes it."
                )
                element.setAccessibilityFrameInParentSpace(accessibilityFrame(for: clipRect(clip, row: row)))
                elements.append(element)
            }
        }
        accessibilityChildElements = elements
    }

    /// This view is flipped; accessibility frames are not. Converting here
    /// keeps the VoiceOver cursor over the thing it is describing.
    private func accessibilityFrame(for rect: NSRect) -> NSRect {
        NSRect(
            x: rect.minX,
            y: bounds.height - rect.maxY,
            width: rect.width,
            height: rect.height
        )
    }

    // MARK: - Labels

    /// Bars are stored from zero and shown from one, the way musicians count.
    private func barNumberLabel(_ bar: Double) -> String {
        let display = bar + 1
        if abs(display.rounded() - display) < 0.01 {
            return "\(Int(display.rounded()))"
        }
        return String(format: "%.2f", display)
    }

    private func barsLabel(_ bars: Double) -> String {
        if abs(bars.rounded() - bars) < 0.01 {
            let whole = Int(bars.rounded())
            return whole == 1 ? "1 bar" : "\(whole) bars"
        }
        return String(format: "%.2f bars", bars)
    }

    // MARK: - Section markers

    private struct SectionMarker {
        let bar: Double
        let label: String
    }

    /// Derives section positions from the recipe by matching each recipe entry
    /// against the clips named after it — `verse` matches `drums-verse`,
    /// `bass-verse`, and so on, and the section starts at the earliest of them.
    ///
    /// A section is only drawn when at least two clips agree on it. Anything
    /// less and we cannot honestly say where the section is, so nothing is
    /// drawn. Evenly-spaced guesses would be worse than no markers at all:
    /// they'd look authoritative and be wrong.
    private static func sectionMarkers(for project: LocalProject) -> [SectionMarker] {
        let recipe = project.snapshot.recipe ?? []
        guard !recipe.isEmpty else { return [] }

        struct ClipRef {
            let slug: String
            let bar: Double
        }
        let clips: [ClipRef] = project.snapshot.tracks.flatMap { track in
            (track.clips ?? []).map { ClipRef(slug: slug($0.id), bar: max(0, $0.startBar ?? 0)) }
        }
        guard !clips.isEmpty else { return [] }

        var order: [String] = []
        var keysBySection: [String: Set<String>] = [:]
        for item in recipe {
            let name = (item.section ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            guard !name.isEmpty else { continue }
            if keysBySection[name] == nil {
                keysBySection[name] = []
                order.append(name)
            }
            let itemSlug = slug(item.id)
            let sectionSlug = slug(name)
            if !itemSlug.isEmpty { keysBySection[name]?.insert(itemSlug) }
            if !sectionSlug.isEmpty { keysBySection[name]?.insert(sectionSlug) }
        }

        var markers: [SectionMarker] = []
        var usedBars: Set<Double> = []
        for name in order {
            guard let keys = keysBySection[name], !keys.isEmpty else { continue }
            let matches = clips.filter { clip in
                keys.contains { key in clip.slug == key || clip.slug.hasSuffix("-" + key) }
            }
            guard matches.count >= 2, let bar = matches.map(\.bar).min() else { continue }
            guard !usedBars.contains(bar) else { continue }
            usedBars.insert(bar)
            markers.append(SectionMarker(bar: bar, label: name))
        }
        return markers.sorted { $0.bar < $1.bar }
    }

    private static func slug(_ raw: String) -> String {
        var out = ""
        var pendingSeparator = false
        for character in raw.lowercased() {
            if character.isLetter || character.isNumber {
                if pendingSeparator, !out.isEmpty { out.append("-") }
                pendingSeparator = false
                out.append(character)
            } else {
                pendingSeparator = true
            }
        }
        return out
    }
}
