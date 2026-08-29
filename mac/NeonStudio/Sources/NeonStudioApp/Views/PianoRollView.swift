import AppKit
import NeonStudioKit

/// The note editor for one track.
///
/// Three things were wrong with the previous piano roll and all three are fixed
/// here. It drew from a single global note pool, so every track showed the same
/// notes; notes could only be appended and the only removal was "delete the last
/// one added", regardless of what the user had clicked; and the drawing code and
/// the click code computed their rectangles from separate constants, so a click
/// frequently landed a row away from what it looked like it hit.
///
/// Now notes belong to the selected track, every note can be selected, moved,
/// resized, re-velocitied and deleted individually, and one `Layout` value is the
/// single source of truth for drawing, hit-testing, cursors, tooltips and
/// VoiceOver frames alike.
public final class PianoRollView: NSView, EditorCanvas, NSViewToolTipOwner {

    // MARK: Tunables

    /// Width of the piano keyboard down the left edge.
    private let keyboardWidth: CGFloat = 52
    private let rulerHeight: CGFloat = Theme.Metric.rulerHeight
    private let pitchRowHeight: CGFloat = 16
    /// Lowest and highest pitch always shown, C3 to C6. The range grows to cover
    /// any note outside it rather than hiding notes the user cannot see.
    private let defaultLowNote = 48
    private let defaultHighNote = 84

    /// Horizontal zoom, shared with the arrangement view's zoom control.
    public var pixelsPerBar: CGFloat = 96 {
        didSet {
            guard abs(pixelsPerBar - oldValue) > 0.01 else { return }
            rebuildOverlays()
            needsDisplay = true
        }
    }

    // MARK: State

    public weak var host: EditorHost? {
        didSet { refresh() }
    }

    private var notes: [PianoNote] = []
    private var selectedNoteIds: Set<String> = []
    /// Notes as they should look *during* a drag. Empty when nothing is dragging,
    /// so there is never a second copy of the truth lying around.
    private var dragPreview: [String: PianoNote] = [:]
    private var marqueeRect: NSRect?
    private var hoveredNoteId: String?
    private var highlightedPitch: Int?
    private var playheadBar: Double = 0
    private var contextPoint: NSPoint = .zero

    private var trackingArea: NSTrackingArea?
    private var currentCursor: NSCursor?
    private var accessibilityNotes: [NSAccessibilityElement] = []
    private var lastOverlaySize: NSSize = .zero

    private static let pitchNames = ["C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B"]

    // MARK: Init

    public override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        commonInit()
    }

    public convenience init() {
        self.init(frame: NSRect(x: 0, y: 0, width: 900, height: 520))
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    private func commonInit() {
        setAccessibilityElement(true)
        setAccessibilityRole(.group)
        setAccessibilityLabel("Piano roll")
        setAccessibilityHelp(AppEnvironment.shared.help(
            "Write and edit the notes for the selected track. Pitch runs up the side, time runs across.",
            term: "Piano roll"
        ))
    }

    deinit {
        NotificationCenter.default.removeObserver(self)
    }

    public override var isFlipped: Bool { true }
    public override var isOpaque: Bool { true }
    public override var acceptsFirstResponder: Bool { true }

    public override func becomeFirstResponder() -> Bool {
        needsDisplay = true
        return true
    }

    public override func resignFirstResponder() -> Bool {
        needsDisplay = true
        return true
    }

    // MARK: - Layout: the single source of geometry
    //
    // Everything that has a position on screen — grid lines, keys, notes, the
    // playhead, tooltip rects, VoiceOver frames — is derived from this one value.
    // Nothing recomputes a coordinate from a literal anywhere else in the file.

    private struct Layout {
        let keyboardWidth: CGFloat
        let rulerHeight: CGFloat
        let rowHeight: CGFloat
        let pixelsPerBeat: CGFloat
        let lowNote: Int
        let highNote: Int
        let totalBeats: Double
        /// The part of the canvas on screen right now. The keyboard and the ruler
        /// are pinned to its edges so they stay put while the grid scrolls.
        let visible: NSRect

        var pitchCount: Int { max(1, highNote - lowNote + 1) }
        var contentWidth: CGFloat { keyboardWidth + CGFloat(totalBeats) * pixelsPerBeat + 48 }
        var contentHeight: CGFloat { rulerHeight * 2 + CGFloat(pitchCount) * rowHeight }

        func x(forBeat beat: Double) -> CGFloat {
            keyboardWidth + CGFloat(beat) * pixelsPerBeat
        }

        func beat(forX x: CGFloat) -> Double {
            max(0, Double((x - keyboardWidth) / max(1, pixelsPerBeat)))
        }

        func y(forNote note: Int) -> CGFloat {
            rulerHeight + CGFloat(highNote - note) * rowHeight
        }

        func note(forY y: CGFloat) -> Int {
            let index = Int(floor((y - rulerHeight) / rowHeight))
            return min(highNote, max(lowNote, highNote - index))
        }

        func rowRect(note: Int) -> NSRect {
            NSRect(x: 0, y: y(forNote: note), width: contentWidth, height: rowHeight)
        }

        func rect(for note: PianoNote) -> NSRect {
            NSRect(
                x: x(forBeat: note.beat),
                y: y(forNote: note.note) + 1,
                width: max(6, CGFloat(note.duration) * pixelsPerBeat),
                height: rowHeight - 2
            )
        }

        var rulerRect: NSRect {
            NSRect(x: visible.minX, y: visible.minY, width: visible.width, height: rulerHeight)
        }

        var keyboardRect: NSRect {
            NSRect(
                x: visible.minX,
                y: visible.minY + rulerHeight,
                width: keyboardWidth,
                height: max(0, visible.height - rulerHeight)
            )
        }

        /// The clickable grid: everything that is neither pinned keyboard nor ruler.
        var gridRect: NSRect {
            NSRect(
                x: visible.minX + keyboardWidth,
                y: visible.minY + rulerHeight,
                width: max(0, visible.width - keyboardWidth),
                height: max(0, visible.height - rulerHeight)
            )
        }

        func keyRect(note: Int) -> NSRect {
            NSRect(x: visible.minX, y: y(forNote: note), width: keyboardWidth, height: rowHeight)
        }
    }

    private var pixelsPerBeat: CGFloat { max(9, pixelsPerBar / 4) }

    private func pianoLayout(visible overrideVisible: NSRect? = nil) -> Layout {
        let vis: NSRect
        if let overrideVisible {
            vis = overrideVisible
        } else {
            let onScreen = visibleRect
            vis = onScreen.isEmpty ? bounds : onScreen
        }

        var low = defaultLowNote
        var high = defaultHighNote
        for note in notes {
            low = min(low, note.note - 1)
            high = max(high, note.note + 1)
        }
        for note in dragPreview.values {
            low = min(low, note.note - 1)
            high = max(high, note.note + 1)
        }
        low = max(0, low)
        high = min(127, max(high, low + 12))

        let projectBars = host?.project.contentEndBar ?? 0
        let lastNoteEnd = notes.map { $0.beat + $0.duration }.max() ?? 0
        let totalBeats = max(max(16, projectBars.rounded(.up)) * 4, lastNoteEnd + 8)

        return Layout(
            keyboardWidth: keyboardWidth,
            rulerHeight: rulerHeight,
            rowHeight: pitchRowHeight,
            pixelsPerBeat: pixelsPerBeat,
            lowNote: low,
            highNote: high,
            totalBeats: totalBeats,
            visible: vis
        )
    }

    // MARK: - EditorCanvas

    public func refresh() {
        let trackId = activeTrackId
        notes = (host?.project.notes(forTrack: trackId) ?? []).sorted { lhs, rhs in
            lhs.beat == rhs.beat ? lhs.note < rhs.note : lhs.beat < rhs.beat
        }
        let live = Set(notes.map(\.id))
        selectedNoteIds.formIntersection(live)
        if let hovered = hoveredNoteId, !live.contains(hovered) { hoveredNoteId = nil }
        if let host { playheadBar = host.playheadBar }
        rebuildOverlays()
        needsDisplay = true
    }

    public func playheadDidMove(to bar: Double) {
        guard abs(bar - playheadBar) > 0.0005 else { return }
        let old = playheadRect(forBar: playheadBar)
        playheadBar = bar
        let new = playheadRect(forBar: bar)
        setNeedsDisplay(old)
        setNeedsDisplay(new)
    }

    public func contentSize(fittingVisible visible: NSSize) -> NSSize {
        let l = pianoLayout(visible: NSRect(origin: .zero, size: visible))
        return NSSize(
            width: max(visible.width, l.contentWidth),
            height: max(visible.height, l.contentHeight)
        )
    }

    private func playheadRect(forBar bar: Double) -> NSRect {
        let l = pianoLayout()
        return NSRect(x: l.x(forBeat: bar * 4) - 3, y: bounds.minY, width: 7, height: bounds.height)
    }

    // MARK: - Track helpers

    /// The track whose notes are on screen. Matches `EditorHost.selectedTrack` so
    /// the notes we read and the notes we write always belong to the same track.
    private var activeTrack: Track? {
        guard let host else { return nil }
        return host.project.track(id: host.selectedTrackId) ?? host.project.snapshot.tracks.first
    }

    private var activeTrackId: String { activeTrack?.id ?? "" }

    private var activeTool: ToolId { host?.activeTool ?? .select }

    private var snap: SnapValue { host?.snapValue ?? .quarter }

    /// One snap unit in beats, never zero, so "nudge by one step" always moves.
    private var snapStepBeats: Double { snap == .none ? 0.25 : max(0.0625, snap.beats) }

    private var displayNotes: [PianoNote] {
        dragPreview.isEmpty ? notes : notes.map { dragPreview[$0.id] ?? $0 }
    }

    private func trackColor(for note: PianoNote) -> NSColor {
        neonColor(from: note.color, fallback: neonColor(from: activeTrack?.color, fallback: Theme.defaultTrackColor))
    }

    private static func isBlackKey(_ midi: Int) -> Bool {
        [1, 3, 6, 8, 10].contains(((midi % 12) + 12) % 12)
    }

    /// Middle C is MIDI 60 and is called C4, so MIDI 48 reads "C3".
    private static func noteName(_ midi: Int) -> String {
        let name = pitchNames[((midi % 12) + 12) % 12]
        return "\(name)\(midi / 12 - 1)"
    }

    private static func numberText(_ value: Double) -> String {
        let rounded = (value * 100).rounded() / 100
        if abs(rounded.rounded() - rounded) < 0.005 { return String(Int(rounded.rounded())) }
        return String(format: "%.2f", rounded)
    }

    /// Plain English for a length, because "0.5" means nothing to a beginner.
    private static func durationPhrase(_ beats: Double) -> String {
        switch beats {
        case ..<0.2: return "a very short note"
        case ..<0.3: return "a quarter of a beat long"
        case ..<0.6: return "half a beat long"
        case ..<0.9: return "three quarters of a beat long"
        case ..<1.1: return "one beat long"
        case ..<2.1: return "two beats long"
        case ..<3.1: return "three beats long"
        case ..<4.1: return "four beats long, a whole bar"
        default: return "\(numberText(beats)) beats long"
        }
    }

    private static func velocityPercent(_ velocity: Double) -> Int {
        Int((max(0, min(1, velocity)) * 100).rounded())
    }

    private func describe(_ note: PianoNote) -> String {
        "\(PianoRollView.noteName(note.note)), beat \(PianoRollView.numberText(note.beat + 1)), "
            + "\(PianoRollView.durationPhrase(note.duration)), "
            + "velocity \(PianoRollView.velocityPercent(note.velocity)) percent"
    }

    private func hexString(_ color: NSColor) -> String {
        var result = ""
        effectiveAppearance.performAsCurrentDrawingAppearance {
            guard let rgb = color.usingColorSpace(.sRGB) else { return }
            result = String(
                format: "#%02x%02x%02x",
                Int((rgb.redComponent * 255).rounded()),
                Int((rgb.greenComponent * 255).rounded()),
                Int((rgb.blueComponent * 255).rounded())
            )
        }
        return result
    }

    // MARK: - Drawing

    public override func draw(_ dirtyRect: NSRect) {
        let l = pianoLayout()
        Theme.canvas.setFill()
        dirtyRect.fill()

        drawPitchRows(l, dirty: dirtyRect)
        drawGridLines(l, dirty: dirtyRect)
        drawNotes(l, dirty: dirtyRect)
        drawMarquee()
        drawEmptyState(l)
        drawPlayhead(l)
        drawKeyboard(l)
        drawRuler(l)
        drawFocusIndicator(l)
    }

    /// White-key and black-key colours derived from the theme, so the keyboard
    /// still looks like a keyboard in both Light and Dark Mode.
    private func keyPalette() -> (white: NSColor, black: NSColor, ink: NSColor) {
        let panel = Theme.panel
        let text = Theme.text
        let panelIsLighter = luminance(panel) >= luminance(text)
        let lighter = panelIsLighter ? panel : text
        let darker = panelIsLighter ? text : panel
        return (
            white: lighter.mixed(with: darker, amount: 0.06),
            black: darker.mixed(with: lighter, amount: 0.14),
            ink: darker
        )
    }

    private func luminance(_ color: NSColor) -> CGFloat {
        guard let rgb = color.usingColorSpace(.sRGB) else { return 0.5 }
        return 0.2126 * rgb.redComponent + 0.7152 * rgb.greenComponent + 0.0722 * rgb.blueComponent
    }

    private func drawPitchRows(_ l: Layout, dirty: NSRect) {
        let top = l.note(forY: max(dirty.minY, l.rulerHeight))
        let bottom = l.note(forY: dirty.maxY)
        guard bottom <= top else { return }
        for midi in bottom...top {
            var rect = l.rowRect(note: midi)
            rect.origin.x = dirty.minX
            rect.size.width = dirty.width
            if PianoRollView.isBlackKey(midi) {
                Theme.panelAlt.setFill()
                rect.fill()
            }
            if midi == highlightedPitch {
                Theme.accent.withAlphaComponent(0.18).setFill()
                rect.fill()
            }
            // A firmer line under every B → C boundary marks each octave.
            if ((midi % 12) + 12) % 12 == 0 {
                drawLine(
                    from: NSPoint(x: rect.minX, y: rect.minY),
                    to: NSPoint(x: rect.maxX, y: rect.minY),
                    color: Theme.stroke,
                    width: 1
                )
            } else {
                drawLine(
                    from: NSPoint(x: rect.minX, y: rect.minY),
                    to: NSPoint(x: rect.maxX, y: rect.minY),
                    color: Theme.subtleStroke.withAlphaComponent(0.55),
                    width: 1
                )
            }
        }
    }

    private func drawGridLines(_ l: Layout, dirty: NSRect) {
        var step = 1.0
        let sub = snap.beats
        if sub > 0, sub < 1, l.pixelsPerBeat * CGFloat(sub) >= 7 { step = sub }

        let firstIndex = max(0, Int(floor(l.beat(forX: dirty.minX) / step)))
        let lastIndex = max(firstIndex, Int(ceil(l.beat(forX: dirty.maxX) / step)))
        guard lastIndex - firstIndex < 4000 else { return }

        let top = max(dirty.minY, l.rulerHeight)
        let bottom = min(dirty.maxY, l.contentHeight)
        guard bottom > top else { return }

        for index in firstIndex...lastIndex {
            let beat = Double(index) * step
            guard beat <= l.totalBeats + step else { break }
            let x = l.x(forBeat: beat).rounded() + 0.5
            let isBar = abs(beat.truncatingRemainder(dividingBy: 4)) < 0.001
            let isBeat = abs(beat.truncatingRemainder(dividingBy: 1)) < 0.001
            let color: NSColor
            if isBar {
                color = Theme.stroke
            } else if isBeat {
                color = Theme.subtleStroke
            } else {
                color = Theme.subtleStroke.withAlphaComponent(0.5)
            }
            drawLine(
                from: NSPoint(x: x, y: top),
                to: NSPoint(x: x, y: bottom),
                color: color,
                width: isBar ? 1.5 : 1
            )
        }
    }

    private func drawNotes(_ l: Layout, dirty: NSRect) {
        for note in displayNotes {
            let rect = l.rect(for: note)
            guard rect.intersects(dirty) else { continue }
            let base = trackColor(for: note)
            // Velocity is the fill opacity: a soft note looks faint, a hard note solid.
            let fill = base.withAlphaComponent(0.28 + 0.72 * CGFloat(max(0, min(1, note.velocity))))
            roundedFill(rect, radius: 3, color: fill)

            let isSelected = selectedNoteIds.contains(note.id)
            if isSelected {
                roundedStroke(rect, radius: 3, color: Theme.text, width: 2)
            } else if note.id == hoveredNoteId {
                roundedStroke(rect, radius: 3, color: Theme.text.withAlphaComponent(0.5), width: 1.5)
            } else {
                roundedStroke(rect, radius: 3, color: base.mixed(with: Theme.text, amount: 0.2), width: 1)
            }

            // The grab handle for resizing, so the draggable edge is visible.
            if rect.width >= 14 {
                let handle = NSRect(x: rect.maxX - 3.5, y: rect.minY + 2, width: 2, height: rect.height - 4)
                roundedFill(handle, radius: 1, color: base.readableForeground.withAlphaComponent(0.55))
            }

            if rect.width >= 34 {
                let label = NSRect(
                    x: rect.minX + 5,
                    y: rect.minY + (rect.height - 13) / 2,
                    width: rect.width - 12,
                    height: 13
                )
                drawText(
                    PianoRollView.noteName(note.note),
                    in: label,
                    color: base.readableForeground,
                    font: Theme.Font.caption(11)
                )
            }
        }
    }

    private func drawMarquee() {
        guard let rect = marqueeRect, rect.width > 1 || rect.height > 1 else { return }
        roundedFill(rect, radius: 2, color: Theme.accent.withAlphaComponent(0.14))
        roundedStroke(rect, radius: 2, color: Theme.accent, width: 1)
    }

    private func drawPlayhead(_ l: Layout) {
        let x = l.x(forBeat: playheadBar * 4).rounded() + 0.5
        drawLine(
            from: NSPoint(x: x, y: l.rulerHeight),
            to: NSPoint(x: x, y: max(l.contentHeight, l.visible.maxY)),
            color: Theme.playhead,
            width: 1.5
        )
    }

    private func drawKeyboard(_ l: Layout) {
        let palette = keyPalette()
        let keyboard = l.keyboardRect
        guard keyboard.height > 0 else { return }
        palette.white.setFill()
        keyboard.fill()

        let top = l.note(forY: keyboard.minY)
        let bottom = l.note(forY: keyboard.maxY)
        guard bottom <= top else { return }

        for midi in bottom...top {
            let rect = l.keyRect(note: midi).intersection(keyboard)
            guard !rect.isEmpty else { continue }
            if PianoRollView.isBlackKey(midi) {
                var black = rect
                black.size.width = rect.width * 0.62
                palette.black.setFill()
                black.fill()
            } else {
                palette.white.setFill()
                rect.fill()
                drawLine(
                    from: NSPoint(x: rect.minX, y: rect.maxY - 0.5),
                    to: NSPoint(x: rect.maxX, y: rect.maxY - 0.5),
                    color: Theme.subtleStroke,
                    width: 1
                )
            }
            if midi == highlightedPitch {
                roundedFill(rect.insetBy(dx: 1, dy: 1), radius: 2, color: Theme.accent.withAlphaComponent(0.35))
            }
            // Only C is labelled, exactly like a real piano roll: "C3", "C4"…
            if ((midi % 12) + 12) % 12 == 0, rect.height >= 11 {
                let label = NSRect(
                    x: rect.minX + 6,
                    y: rect.minY + (rect.height - 13) / 2,
                    width: rect.width - 12,
                    height: 13
                )
                drawText(
                    PianoRollView.noteName(midi),
                    in: label,
                    color: palette.ink,
                    font: Theme.Font.caption(11),
                    alignment: .right
                )
            }
        }

        drawLine(
            from: NSPoint(x: keyboard.maxX - 0.5, y: keyboard.minY),
            to: NSPoint(x: keyboard.maxX - 0.5, y: keyboard.maxY),
            color: Theme.stroke,
            width: 1
        )
    }

    private func drawRuler(_ l: Layout) {
        let ruler = l.rulerRect
        Theme.panel.setFill()
        ruler.fill()
        drawLine(
            from: NSPoint(x: ruler.minX, y: ruler.maxY - 0.5),
            to: NSPoint(x: ruler.maxX, y: ruler.maxY - 0.5),
            color: Theme.stroke,
            width: 1
        )

        let firstBar = max(0, Int(floor(l.beat(forX: ruler.minX + l.keyboardWidth) / 4)) - 1)
        let lastBar = Int(ceil(l.beat(forX: ruler.maxX) / 4)) + 1
        let labelEvery = l.pixelsPerBeat * 4 >= 44 ? 1 : 4
        if lastBar >= firstBar, lastBar - firstBar < 2000 {
            for bar in firstBar...lastBar {
                let x = l.x(forBeat: Double(bar) * 4)
                guard x >= ruler.minX + l.keyboardWidth - 1, x <= ruler.maxX else { continue }
                drawLine(
                    from: NSPoint(x: x.rounded() + 0.5, y: ruler.maxY - 7),
                    to: NSPoint(x: x.rounded() + 0.5, y: ruler.maxY),
                    color: Theme.stroke,
                    width: 1
                )
                guard bar % labelEvery == 0 else { continue }
                drawText(
                    "\(bar + 1)",
                    in: NSRect(x: x + 4, y: ruler.minY + 6, width: 44, height: 14),
                    color: Theme.muted,
                    font: Theme.Font.caption(11)
                )
            }
        }

        // Playhead marker, the one thing in the ruler that is not a bar number.
        let playX = l.x(forBeat: playheadBar * 4)
        if playX >= ruler.minX + l.keyboardWidth - 6, playX <= ruler.maxX {
            let marker = NSBezierPath()
            marker.move(to: NSPoint(x: playX - 5, y: ruler.maxY - 9))
            marker.line(to: NSPoint(x: playX + 5, y: ruler.maxY - 9))
            marker.line(to: NSPoint(x: playX, y: ruler.maxY - 1))
            marker.close()
            Theme.playhead.setFill()
            marker.fill()
        }

        // The keyboard's corner, so bar numbers never slide under the keys.
        let corner = NSRect(x: ruler.minX, y: ruler.minY, width: l.keyboardWidth, height: ruler.height)
        Theme.panelAlt.setFill()
        corner.fill()
        drawText(
            "Pitch",
            in: NSRect(x: corner.minX + 6, y: corner.minY + 6, width: corner.width - 12, height: 14),
            color: Theme.dim,
            font: Theme.Font.caption(11)
        )
        drawLine(
            from: NSPoint(x: corner.maxX - 0.5, y: corner.minY),
            to: NSPoint(x: corner.maxX - 0.5, y: corner.maxY),
            color: Theme.stroke,
            width: 1
        )
    }

    private func drawEmptyState(_ l: Layout) {
        guard notes.isEmpty else { return }
        let title: String
        let body: String
        if let track = activeTrack {
            title = "No notes on \(track.name) yet."
            body = "Choose the Draw tool and click the grid to write one. "
                + "Higher up the grid is a higher note; wider is a longer note."
        } else if host?.project.snapshot.tracks.isEmpty ?? true {
            title = "This song has no tracks yet."
            body = "Add a track in the list on the left, then come back here to write its notes."
        } else {
            title = "No track selected."
            body = "Pick a track in the list on the left to write notes for it."
        }

        let grid = l.gridRect
        guard grid.width > 160, grid.height > 90 else { return }
        let card = NSRect(
            x: grid.midX - 190,
            y: grid.midY - 48,
            width: 380,
            height: 96
        ).intersection(grid)
        guard card.width > 120 else { return }

        roundedFill(card, radius: Theme.Metric.cornerRadius, color: Theme.panel.withAlphaComponent(0.94))
        roundedStroke(card, radius: Theme.Metric.cornerRadius, color: Theme.subtleStroke, width: 1)
        drawText(
            title,
            in: NSRect(x: card.minX + 16, y: card.minY + 14, width: card.width - 32, height: 20),
            color: Theme.text,
            font: Theme.Font.emphasis(13),
            alignment: .center
        )
        drawText(
            body,
            in: NSRect(x: card.minX + 16, y: card.minY + 36, width: card.width - 32, height: 48),
            color: Theme.muted,
            font: Theme.Font.body(12),
            alignment: .center,
            lineBreak: .byWordWrapping
        )
    }

    private func drawFocusIndicator(_ l: Layout) {
        guard window?.firstResponder === self, window?.isKeyWindow == true else { return }
        roundedStroke(
            l.gridRect.insetBy(dx: 1.5, dy: 1.5),
            radius: 4,
            color: Theme.accent.withAlphaComponent(0.6),
            width: 2
        )
    }

    // MARK: - Hit testing

    private enum NoteDragMode {
        case move
        case resizeEnd
    }

    private func note(at point: NSPoint, layout l: Layout) -> (note: PianoNote, mode: NoteDragMode)? {
        guard l.gridRect.contains(point) else { return nil }
        for note in displayNotes.reversed() {
            let rect = l.rect(for: note)
            guard rect.insetBy(dx: -1, dy: 0).contains(point) else { continue }
            let edge = min(ClipDragMode.edgeWidth, rect.width * 0.4)
            let mode: NoteDragMode = point.x >= rect.maxX - edge ? .resizeEnd : .move
            return (note, mode)
        }
        return nil
    }

    // MARK: - Mouse

    public override func mouseDown(with event: NSEvent) {
        window?.makeFirstResponder(self)
        let point = convert(event.locationInWindow, from: nil)
        let l = pianoLayout()

        if l.rulerRect.contains(point) {
            beginPlayheadDrag(from: point, layout: l)
            return
        }
        if l.keyboardRect.contains(point) {
            selectPitchRow(at: point, layout: l)
            return
        }
        guard l.gridRect.contains(point) else { return }

        if let hit = note(at: point, layout: l) {
            if activeTool == .erase {
                erase(hit.note)
                return
            }
            if event.modifierFlags.contains(.option) {
                selectIfNeeded(hit.note, extending: false)
                beginVelocityDrag(anchor: hit.note, from: point)
                return
            }
            selectIfNeeded(hit.note, extending: event.modifierFlags.contains(.shift))
            if hit.mode == .resizeEnd {
                beginResizeDrag(anchor: hit.note, from: point, layout: l)
            } else {
                beginMoveDrag(anchor: hit.note, from: point, layout: l)
            }
            return
        }

        // Empty grid.
        if activeTool == .erase {
            StatusCenter.shared.info("Nothing to erase there. The Erase tool deletes the note you click.")
            return
        }
        if activeTool == .draw || event.clickCount >= 2 {
            addNote(at: point, layout: l)
            return
        }
        beginMarquee(from: point, layout: l, extending: event.modifierFlags.contains(.shift))
    }

    public override func mouseMoved(with event: NSEvent) {
        let point = convert(event.locationInWindow, from: nil)
        let l = pianoLayout()
        updateCursor(at: point, layout: l)

        let hit = note(at: point, layout: l)?.note.id
        guard hit != hoveredNoteId else { return }
        if let previous = hoveredNoteId, let old = displayNotes.first(where: { $0.id == previous }) {
            setNeedsDisplay(l.rect(for: old).insetBy(dx: -3, dy: -3))
        }
        hoveredNoteId = hit
        if let hit, let current = displayNotes.first(where: { $0.id == hit }) {
            setNeedsDisplay(l.rect(for: current).insetBy(dx: -3, dy: -3))
        }
    }

    public override func mouseExited(with event: NSEvent) {
        if hoveredNoteId != nil {
            hoveredNoteId = nil
            needsDisplay = true
        }
        NSCursor.arrow.set()
        currentCursor = nil
    }

    private func updateCursor(at point: NSPoint, layout l: Layout) {
        let wanted: NSCursor
        if l.rulerRect.contains(point) || l.keyboardRect.contains(point) {
            wanted = .arrow
        } else if let hit = note(at: point, layout: l) {
            wanted = hit.mode == .resizeEnd ? .resizeLeftRight : .openHand
        } else if l.gridRect.contains(point), activeTool == .draw {
            wanted = .crosshair
        } else {
            wanted = .arrow
        }
        guard wanted !== currentCursor else { return }
        currentCursor = wanted
        wanted.set()
    }

    public override func updateTrackingAreas() {
        super.updateTrackingAreas()
        if let trackingArea { removeTrackingArea(trackingArea) }
        let area = NSTrackingArea(
            rect: .zero,
            options: [.mouseEnteredAndExited, .mouseMoved, .activeInKeyWindow, .inVisibleRect],
            owner: self,
            userInfo: nil
        )
        addTrackingArea(area)
        trackingArea = area
    }

    /// The one drag loop every gesture runs through, so a drag always ends with
    /// exactly one undoable edit and never leaves a preview stranded on screen.
    private func runDragLoop(from start: NSPoint, onDrag: (NSPoint) -> Void, onEnd: (NSPoint, Bool) -> Void) {
        var last = start
        var moved = false
        while let event = window?.nextEvent(matching: [.leftMouseDragged, .leftMouseUp]) {
            let point = convert(event.locationInWindow, from: nil)
            if event.type == .leftMouseUp {
                onEnd(point, moved)
                return
            }
            if abs(point.x - start.x) > 2 || abs(point.y - start.y) > 2 { moved = true }
            _ = autoscroll(with: event)
            onDrag(point)
            last = point
        }
        onEnd(last, moved)
    }

    // MARK: - Selection

    private func selectIfNeeded(_ note: PianoNote, extending: Bool) {
        if extending {
            if selectedNoteIds.contains(note.id) {
                selectedNoteIds.remove(note.id)
            } else {
                selectedNoteIds.insert(note.id)
            }
        } else if !selectedNoteIds.contains(note.id) {
            selectedNoteIds = [note.id]
        }
        highlightedPitch = note.note
        needsDisplay = true
        announceSelection()
    }

    private func announceSelection() {
        guard let host else { return }
        if selectedNoteIds.count == 1,
           let only = notes.first(where: { selectedNoteIds.contains($0.id) }) {
            host.status("Selected \(describe(only)). Drag to move it, drag its right edge to make it longer.")
        } else if selectedNoteIds.count > 1 {
            host.status("Selected \(selectedNoteIds.count) notes. Drag to move them, or press Delete to remove them.")
        }
    }

    public override func selectAll(_ sender: Any?) {
        guard !notes.isEmpty else { return }
        selectedNoteIds = Set(notes.map(\.id))
        needsDisplay = true
        StatusCenter.shared.info("Selected all \(notes.count) notes on \(activeTrack?.name ?? "this track").")
    }

    private func selectPitchRow(at point: NSPoint, layout l: Layout) {
        let midi = l.note(forY: point.y)
        highlightedPitch = midi
        needsDisplay = true
        let count = notes.filter { $0.note == midi }.count
        let suffix = count == 0
            ? "Nothing is written on that row yet."
            : "\(count) note\(count == 1 ? "" : "s") on that row."
        host?.status("\(PianoRollView.noteName(midi)) row highlighted. \(suffix) Neon Studio can't preview single notes yet.")
    }

    // MARK: - Editing

    private func mutateNotes(_ actionName: String, ids: Set<String>, _ transform: (inout PianoNote) -> Void) {
        guard let host, !ids.isEmpty else { return }
        host.edit(actionName) { project in
            var all = project.snapshot.notes ?? []
            for index in all.indices where ids.contains(all[index].id) {
                transform(&all[index])
            }
            project.snapshot.notes = all
        }
    }

    private func addNote(at point: NSPoint, layout l: Layout) {
        guard let host else { return }
        guard let track = activeTrack else {
            StatusCenter.shared.warning(
                "Pick a track first.",
                detail: "Notes belong to a track. Choose one in the list on the left, then click the grid."
            )
            return
        }
        let beat = snap.snap(beats: l.beat(forX: point.x))
        let duration = max(0.25, snap.beats)
        let pitch = l.note(forY: point.y)
        let colorHex = track.color ?? hexString(Theme.defaultTrackColor)
        let new = PianoNote(
            id: makeId("note"),
            beat: beat,
            duration: duration,
            note: pitch,
            velocity: 0.8,
            color: colorHex,
            trackId: track.id
        )
        host.edit("Add Note") { project in
            var all = project.snapshot.notes ?? []
            all.append(new)
            project.snapshot.notes = all
        }
        selectedNoteIds = [new.id]
        highlightedPitch = pitch
        needsDisplay = true
        StatusCenter.shared.success(
            "Added \(PianoRollView.noteName(pitch)) at beat \(PianoRollView.numberText(beat + 1)) on \(track.name). ⌘Z undoes it."
        )
    }

    private func erase(_ note: PianoNote) {
        guard let host else { return }
        let id = note.id
        host.edit("Delete Note") { project in
            project.snapshot.notes = (project.snapshot.notes ?? []).filter { $0.id != id }
        }
        selectedNoteIds.remove(id)
        needsDisplay = true
        StatusCenter.shared.success("Deleted \(describe(note)). ⌘Z puts it back.")
    }

    private func deleteSelection() {
        guard host != nil else { return }
        let doomed = selectedNoteIds
        let victims = notes.filter { doomed.contains($0.id) }
        guard !victims.isEmpty else {
            StatusCenter.shared.info("Nothing selected. Click a note first, then press Delete.")
            return
        }
        mutateNotesRemoving(doomed, actionName: "Delete Notes")
        let word = victims.count == 1 ? "note" : "notes"
        let them = victims.count == 1 ? "it" : "them"
        StatusCenter.shared.success("Deleted \(victims.count) \(word). ⌘Z puts \(them) back.")
    }

    private func mutateNotesRemoving(_ ids: Set<String>, actionName: String) {
        guard let host, !ids.isEmpty else { return }
        host.edit(actionName) { project in
            project.snapshot.notes = (project.snapshot.notes ?? []).filter { !ids.contains($0.id) }
        }
        selectedNoteIds.subtract(ids)
        needsDisplay = true
    }

    private func transposeSelection(by semitones: Int) {
        let ids = selectedNoteIds
        let targets = notes.filter { ids.contains($0.id) }
        guard !targets.isEmpty else {
            StatusCenter.shared.info("Nothing selected. Click a note first, then use the arrow keys.")
            return
        }
        let lowest = targets.map(\.note).min() ?? 0
        let highest = targets.map(\.note).max() ?? 127
        let clamped = max(-lowest, min(127 - highest, semitones))
        guard clamped != 0 else {
            StatusCenter.shared.warning("Those notes are already as \(semitones > 0 ? "high" : "low") as they go.")
            return
        }
        mutateNotes("Transpose Notes", ids: ids) { note in
            note.note = max(0, min(127, note.note + clamped))
        }
        highlightedPitch = (highlightedPitch ?? lowest) + clamped
        needsDisplay = true
        let direction = clamped > 0 ? "up" : "down"
        let amount = abs(clamped) == 12 ? "an octave" : "\(abs(clamped)) semitone\(abs(clamped) == 1 ? "" : "s")"
        StatusCenter.shared.success("Moved \(targets.count) note\(targets.count == 1 ? "" : "s") \(direction) \(amount). ⌘Z undoes it.")
    }

    private func nudgeSelection(byBeats delta: Double) {
        let ids = selectedNoteIds
        let targets = notes.filter { ids.contains($0.id) }
        guard !targets.isEmpty else {
            StatusCenter.shared.info("Nothing selected. Click a note first, then use the arrow keys.")
            return
        }
        let earliest = targets.map(\.beat).min() ?? 0
        let clamped = max(-earliest, delta)
        guard abs(clamped) > 0.0001 else {
            StatusCenter.shared.warning("Those notes are already at the start of the song.")
            return
        }
        mutateNotes("Move Notes", ids: ids) { note in
            note.beat = max(0, note.beat + clamped)
        }
        let direction = clamped > 0 ? "later" : "earlier"
        StatusCenter.shared.success(
            "Moved \(targets.count) note\(targets.count == 1 ? "" : "s") \(PianoRollView.numberText(abs(clamped))) beat\(abs(clamped) == 1 ? "" : "s") \(direction). ⌘Z undoes it."
        )
    }

    // MARK: - Drags

    private func beginMoveDrag(anchor: PianoNote, from start: NSPoint, layout l: Layout) {
        let ids = selectedNoteIds.contains(anchor.id) ? selectedNoteIds : [anchor.id]
        let originals = notes.filter { ids.contains($0.id) }
        guard !originals.isEmpty else { return }
        let minBeat = originals.map(\.beat).min() ?? 0
        let lowest = originals.map(\.note).min() ?? 0
        let highest = originals.map(\.note).max() ?? 127
        let startPitch = l.note(forY: start.y)
        let previousCursor = currentCursor
        NSCursor.closedHand.set()

        var deltaBeats = 0.0
        var deltaPitch = 0

        runDragLoop(from: start, onDrag: { point in
            let raw = anchor.beat + (l.beat(forX: point.x) - l.beat(forX: start.x))
            let target = snap.snap(beats: max(0, raw))
            deltaBeats = max(-minBeat, target - anchor.beat)
            deltaPitch = max(-lowest, min(127 - highest, l.note(forY: point.y) - startPitch))

            var preview: [String: PianoNote] = [:]
            for note in originals {
                var moved = note
                moved.beat = max(0, note.beat + deltaBeats)
                moved.note = max(0, min(127, note.note + deltaPitch))
                preview[note.id] = moved
            }
            dragPreview = preview
            needsDisplay = true
        }, onEnd: { _, _ in
            dragPreview.removeAll()
            (previousCursor ?? NSCursor.arrow).set()
            needsDisplay = true
            guard abs(deltaBeats) > 0.0001 || deltaPitch != 0 else { return }
            let beats = deltaBeats
            let pitch = deltaPitch
            mutateNotes("Move Note", ids: ids) { note in
                note.beat = max(0, note.beat + beats)
                note.note = max(0, min(127, note.note + pitch))
            }
            highlightedPitch = anchor.note + pitch
            let label = originals.count == 1
                ? PianoRollView.noteName(anchor.note + pitch)
                : "\(originals.count) notes"
            StatusCenter.shared.success(
                "Moved \(label) to beat \(PianoRollView.numberText(anchor.beat + beats + 1)). ⌘Z undoes it."
            )
        })
    }

    private func beginResizeDrag(anchor: PianoNote, from start: NSPoint, layout l: Layout) {
        let ids = selectedNoteIds.contains(anchor.id) ? selectedNoteIds : [anchor.id]
        let originals = notes.filter { ids.contains($0.id) }
        guard !originals.isEmpty else { return }
        let minimum = 0.0625
        let previousCursor = currentCursor
        NSCursor.resizeLeftRight.set()

        var deltaDuration = 0.0

        runDragLoop(from: start, onDrag: { point in
            let rawEnd = max(anchor.beat + minimum, l.beat(forX: point.x))
            let snappedEnd = snap == .none ? rawEnd : snap.snap(beats: rawEnd)
            let newDuration = max(minimum, snappedEnd - anchor.beat)
            deltaDuration = newDuration - anchor.duration

            var preview: [String: PianoNote] = [:]
            for note in originals {
                var resized = note
                resized.duration = max(minimum, note.duration + deltaDuration)
                preview[note.id] = resized
            }
            dragPreview = preview
            needsDisplay = true
        }, onEnd: { _, _ in
            dragPreview.removeAll()
            (previousCursor ?? NSCursor.arrow).set()
            needsDisplay = true
            guard abs(deltaDuration) > 0.0001 else { return }
            let delta = deltaDuration
            mutateNotes("Resize Note", ids: ids) { note in
                note.duration = max(minimum, note.duration + delta)
            }
            let final = max(minimum, anchor.duration + delta)
            let label = originals.count == 1 ? PianoRollView.noteName(anchor.note) : "\(originals.count) notes"
            StatusCenter.shared.success("\(label) now \(PianoRollView.durationPhrase(final)). ⌘Z undoes it.")
        })
    }

    private func beginVelocityDrag(anchor: PianoNote, from start: NSPoint) {
        let ids = selectedNoteIds.contains(anchor.id) ? selectedNoteIds : [anchor.id]
        let originals = notes.filter { ids.contains($0.id) }
        guard !originals.isEmpty else { return }
        let previousCursor = currentCursor
        NSCursor.resizeUpDown.set()

        var delta = 0.0
        var lastReported = -1

        runDragLoop(from: start, onDrag: { point in
            // The view is flipped, so dragging upward is a decreasing y.
            delta = Double(start.y - point.y) / 110.0

            var preview: [String: PianoNote] = [:]
            for note in originals {
                var changed = note
                changed.velocity = max(0.05, min(1, note.velocity + delta))
                preview[note.id] = changed
            }
            dragPreview = preview
            needsDisplay = true

            let percent = PianoRollView.velocityPercent(max(0.05, min(1, anchor.velocity + delta)))
            if percent != lastReported {
                lastReported = percent
                host?.status("Velocity \(percent) percent — how hard the note is played.")
            }
        }, onEnd: { _, _ in
            dragPreview.removeAll()
            (previousCursor ?? NSCursor.arrow).set()
            needsDisplay = true
            guard abs(delta) > 0.001 else { return }
            let change = delta
            mutateNotes("Change Velocity", ids: ids) { note in
                note.velocity = max(0.05, min(1, note.velocity + change))
            }
            let percent = PianoRollView.velocityPercent(max(0.05, min(1, anchor.velocity + change)))
            let label = originals.count == 1 ? PianoRollView.noteName(anchor.note) : "\(originals.count) notes"
            StatusCenter.shared.success("\(label) set to velocity \(percent) percent. ⌘Z undoes it.")
        })
    }

    private func beginMarquee(from start: NSPoint, layout l: Layout, extending: Bool) {
        let base = extending ? selectedNoteIds : []
        if !extending, !selectedNoteIds.isEmpty {
            selectedNoteIds.removeAll()
            needsDisplay = true
        }

        runDragLoop(from: start, onDrag: { point in
            let rect = NSRect(
                x: min(start.x, point.x),
                y: min(start.y, point.y),
                width: abs(point.x - start.x),
                height: abs(point.y - start.y)
            )
            marqueeRect = rect
            var hits = base
            for note in notes where l.rect(for: note).intersects(rect) {
                hits.insert(note.id)
            }
            selectedNoteIds = hits
            needsDisplay = true
        }, onEnd: { _, moved in
            marqueeRect = nil
            needsDisplay = true
            guard moved else {
                host?.clearClipSelection()
                return
            }
            if selectedNoteIds.isEmpty {
                StatusCenter.shared.info("Nothing in that area. Drag across notes to select them.")
            } else {
                announceSelection()
            }
        })
    }

    private func beginPlayheadDrag(from start: NSPoint, layout l: Layout) {
        func seek(_ point: NSPoint) {
            let bar = l.beat(forX: point.x) / 4
            let snapped = snap == .none ? bar : snap.snap(bars: bar)
            host?.seek(toBar: max(0, snapped))
        }
        seek(start)
        runDragLoop(from: start, onDrag: { point in
            seek(point)
        }, onEnd: { point, moved in
            if moved { seek(point) }
            host?.status("Playhead at bar \(PianoRollView.numberText((playheadBar + 1).rounded(.down))).")
        })
    }

    // MARK: - Keyboard

    public override func keyDown(with event: NSEvent) {
        guard let scalar = event.charactersIgnoringModifiers?.unicodeScalars.first else {
            super.keyDown(with: event)
            return
        }
        let shift = event.modifierFlags.contains(.shift)
        switch Int(scalar.value) {
        case NSDeleteCharacter, NSBackspaceCharacter, NSDeleteFunctionKey:
            deleteSelection()
        case NSUpArrowFunctionKey:
            transposeSelection(by: shift ? 12 : 1)
        case NSDownArrowFunctionKey:
            transposeSelection(by: shift ? -12 : -1)
        case NSLeftArrowFunctionKey:
            nudgeSelection(byBeats: -snapStepBeats)
        case NSRightArrowFunctionKey:
            nudgeSelection(byBeats: snapStepBeats)
        case 27: // Escape
            guard !selectedNoteIds.isEmpty else { super.keyDown(with: event); return }
            selectedNoteIds.removeAll()
            needsDisplay = true
            host?.status("Selection cleared.")
        default:
            super.keyDown(with: event)
        }
    }

    // MARK: - Context menu

    public override func menu(for event: NSEvent) -> NSMenu? {
        let point = convert(event.locationInWindow, from: nil)
        contextPoint = point
        let l = pianoLayout()
        if let hit = note(at: point, layout: l), !selectedNoteIds.contains(hit.note.id) {
            selectedNoteIds = [hit.note.id]
            highlightedPitch = hit.note.note
            needsDisplay = true
        }

        let menu = NSMenu(title: "Notes")
        menu.autoenablesItems = false
        let hasSelection = !notes.filter { selectedNoteIds.contains($0.id) }.isEmpty

        func add(_ title: String, _ selector: Selector, enabled: Bool, help: String) {
            let item = NSMenuItem(title: title, action: selector, keyEquivalent: "")
            item.target = self
            item.isEnabled = enabled
            item.toolTip = help
            menu.addItem(item)
        }

        add("Delete", #selector(contextDelete(_:)), enabled: hasSelection,
            help: "Remove the selected notes. ⌘Z puts them back.")
        add("Duplicate", #selector(contextDuplicate(_:)), enabled: hasSelection,
            help: "Make a copy of the selected notes just after them.")
        menu.addItem(.separator())
        add("Transpose Up an Octave", #selector(contextTransposeUp(_:)), enabled: hasSelection,
            help: AppEnvironment.shared.help("Move the selected notes twelve semitones higher.", term: "Key"))
        add("Transpose Down an Octave", #selector(contextTransposeDown(_:)), enabled: hasSelection,
            help: AppEnvironment.shared.help("Move the selected notes twelve semitones lower.", term: "Key"))
        menu.addItem(.separator())
        let bar = Int(floor(l.beat(forX: point.x) / 4)) + 1
        add("Select All in Bar \(bar)", #selector(contextSelectBar(_:)), enabled: !notes.isEmpty,
            help: AppEnvironment.shared.help("Select every note that starts inside this bar.", term: "Bar"))
        return menu
    }

    @objc private func contextDelete(_ sender: Any?) {
        deleteSelection()
    }

    @objc private func contextDuplicate(_ sender: Any?) {
        guard let host else { return }
        let targets = notes.filter { selectedNoteIds.contains($0.id) }
        guard !targets.isEmpty else { return }
        let start = targets.map(\.beat).min() ?? 0
        let end = targets.map { $0.beat + $0.duration }.max() ?? 0
        let offset = max(snapStepBeats, end - start)
        let copies: [PianoNote] = targets.map { note in
            PianoNote(
                id: makeId("note"),
                beat: note.beat + offset,
                duration: note.duration,
                note: note.note,
                velocity: note.velocity,
                color: note.color,
                trackId: note.trackId ?? activeTrackId
            )
        }
        host.edit("Duplicate Notes") { project in
            var all = project.snapshot.notes ?? []
            all.append(contentsOf: copies)
            project.snapshot.notes = all
        }
        selectedNoteIds = Set(copies.map(\.id))
        needsDisplay = true
        StatusCenter.shared.success(
            "Copied \(copies.count) note\(copies.count == 1 ? "" : "s") \(PianoRollView.numberText(offset)) beat\(offset == 1 ? "" : "s") later. ⌘Z undoes it."
        )
    }

    @objc private func contextTransposeUp(_ sender: Any?) {
        transposeSelection(by: 12)
    }

    @objc private func contextTransposeDown(_ sender: Any?) {
        transposeSelection(by: -12)
    }

    @objc private func contextSelectBar(_ sender: Any?) {
        let l = pianoLayout()
        let bar = floor(l.beat(forX: contextPoint.x) / 4)
        let lower = bar * 4
        let upper = lower + 4
        let hits = notes.filter { $0.beat >= lower - 0.0001 && $0.beat < upper - 0.0001 }
        guard !hits.isEmpty else {
            StatusCenter.shared.info("Bar \(Int(bar) + 1) has no notes on \(activeTrack?.name ?? "this track").")
            return
        }
        selectedNoteIds = Set(hits.map(\.id))
        needsDisplay = true
        StatusCenter.shared.info("Selected \(hits.count) note\(hits.count == 1 ? "" : "s") in bar \(Int(bar) + 1).")
    }

    // MARK: - Scroll-aware chrome

    public override func viewDidMoveToSuperview() {
        super.viewDidMoveToSuperview()
        NotificationCenter.default.removeObserver(self, name: NSView.boundsDidChangeNotification, object: nil)
        if let clipView = enclosingScrollView?.contentView {
            clipView.postsBoundsChangedNotifications = true
            NotificationCenter.default.addObserver(
                self,
                selector: #selector(clipBoundsChanged),
                name: NSView.boundsDidChangeNotification,
                object: clipView
            )
        }
    }

    /// The keyboard and ruler are pinned to the visible edges, so a scroll has to
    /// repaint them.
    @objc private func clipBoundsChanged() {
        needsDisplay = true
    }

    public override func setFrameSize(_ newSize: NSSize) {
        super.setFrameSize(newSize)
        guard newSize != lastOverlaySize else { return }
        lastOverlaySize = newSize
        rebuildOverlays()
    }

    // MARK: - Accessibility and tooltips

    /// VoiceOver gets one element per note, and the tooltip text is computed from
    /// the same `Layout` the drawing uses, so the three can never disagree.
    private func rebuildOverlays() {
        let l = pianoLayout()

        accessibilityNotes = notes.map { note in
            let element = NSAccessibilityElement()
            element.setAccessibilityRole(.button)
            element.setAccessibilityParent(self)
            element.setAccessibilityLabel(describe(note))
            element.setAccessibilityHelp(
                "Note on \(activeTrack?.name ?? "this track"). Drag to move it, drag its right edge to change how long it is."
            )
            element.setAccessibilityFrameInParentSpace(l.rect(for: note))
            return element
        }
        setAccessibilityChildren(accessibilityNotes)

        removeAllToolTips()
        _ = addToolTip(bounds, owner: self, userData: nil)
        for note in notes {
            _ = addToolTip(l.rect(for: note), owner: self, userData: nil)
        }
    }

    public func view(
        _ view: NSView,
        stringForToolTip tag: NSView.ToolTipTag,
        point: NSPoint,
        userData data: UnsafeMutableRawPointer?
    ) -> String {
        let l = pianoLayout()
        if l.rulerRect.contains(point) {
            return AppEnvironment.shared.help(
                "Click or drag here to move the playhead.",
                term: "Bar"
            )
        }
        if l.keyboardRect.contains(point) {
            return "\(PianoRollView.noteName(l.note(forY: point.y))). Click a key to highlight that row."
        }
        if let hit = note(at: point, layout: l) {
            let base = "\(describe(hit.note)). Drag to move, drag the right edge to change its length, "
                + "hold Option and drag up or down to change how hard it is played."
            return AppEnvironment.shared.help(base, term: "Velocity")
        }
        if activeTool == .draw {
            return AppEnvironment.shared.help(
                "Click to write a note here at \(PianoRollView.noteName(l.note(forY: point.y))).",
                term: "Piano roll"
            )
        }
        return AppEnvironment.shared.help(
            "Drag to select notes. Double-click an empty spot to write a new note.",
            term: "Piano roll"
        )
    }
}
