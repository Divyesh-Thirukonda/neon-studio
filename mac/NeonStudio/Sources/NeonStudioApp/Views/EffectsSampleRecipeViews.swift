import AppKit
import AVFoundation
import UniformTypeIdentifiers
import NeonStudioKit

// MARK: - Shared building blocks
//
// Everything in this file is built out of real AppKit controls. The previous
// build drew these three panels by hand inside `draw(_:)` and hit-tested them by
// recomputing pixel rects in `mouseDown`, so the left half of an effect card
// toggled it and the right half set its amount — an interaction nobody could
// guess, with no hover, pressed, disabled or VoiceOver state anywhere.
//
// The only hand-drawn thing left here is the sample waveform, which is a canvas.
// Its geometry lives in exactly one function that both drawing and mouse
// handling call.

/// `NSSwitch` with a closure instead of a target/action pair.
private final class SwitchControl: NSSwitch {
    var handler: ((Bool) -> Void)?

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        target = self
        action = #selector(invoke)
        translatesAutoresizingMaskIntoConstraints = false
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    @objc private func invoke() { handler?(state == .on) }
}

/// `NSStepper` with a closure.
private final class StepperControl: NSStepper {
    var handler: ((Double) -> Void)?

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        target = self
        action = #selector(invoke)
        translatesAutoresizingMaskIntoConstraints = false
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    @objc private func invoke() { handler?(doubleValue) }
}

/// A real checkbox with a closure.
private final class CheckboxControl: NSButton {
    var handler: ((Bool) -> Void)?

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        setButtonType(.switch)
        title = ""
        target = self
        action = #selector(invoke)
        translatesAutoresizingMaskIntoConstraints = false
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    @objc private func invoke() { handler?(state == .on) }
}

/// A panel-coloured card that rows sit on. Drawn rather than layer-filled so it
/// follows Light/Dark and Increase Contrast without extra bookkeeping.
private class NeonCardView: NSView {
    var isHovering = false {
        didSet { if isHovering != oldValue { needsDisplay = true } }
    }

    override func draw(_ dirtyRect: NSRect) {
        let fill = isHovering ? Theme.panelAlt : Theme.panel
        roundedFill(bounds, radius: Theme.Metric.cornerRadius, color: fill)
        roundedStroke(bounds, radius: Theme.Metric.cornerRadius, color: Theme.subtleStroke)
    }
}

/// Formats a 0…1 amount the way the readout beside a slider shows it.
private func neonPercentText(_ value: Double) -> String {
    "\(Int((value * 100).rounded()))%"
}

/// True while the knob is still under the mouse button.
///
/// Sliders here stay continuous so the number beside them tracks the drag, but
/// the document is only written when the drag ends — otherwise a single drag
/// would push fifty entries onto the undo stack.
private func neonSliderIsMidDrag() -> Bool {
    guard let type = NSApp.currentEvent?.type else { return false }
    return type == .leftMouseDragged || type == .leftMouseDown
}

private func neonTimeText(_ seconds: Double) -> String {
    guard seconds.isFinite, seconds > 0 else { return "0.00 seconds" }
    if seconds < 60 { return String(format: "%.2f seconds", seconds) }
    let minutes = Int(seconds) / 60
    let rest = seconds - Double(minutes * 60)
    return String(format: "%d:%05.2f", minutes, rest)
}

private func neonShortTimeText(_ seconds: Double) -> String {
    guard seconds.isFinite, seconds > 0 else { return "0.00" }
    return String(format: "%.2f", seconds)
}

/// Header + scrolling body + empty-state slot, shared by the three panels in
/// this file. Composition rather than a base class so each panel stays a direct
/// `NSView` subclass, as `EditorCanvas` requires.
private final class NeonPaneScaffold {
    let titleLabel = makeLabel("", font: Theme.Font.title(15), color: Theme.text)
    let subtitleLabel = makeLabel("", font: Theme.Font.caption(11), color: Theme.muted)
    let scrollView = NSScrollView()
    let contentStack = NSStackView()

    private let header = NSView()
    private let accessoryStack = NSStackView()
    private let emptyContainer = NSView()

    init(owner: NSView, title: String, subtitle: String) {
        titleLabel.stringValue = title
        subtitleLabel.stringValue = subtitle

        header.translatesAutoresizingMaskIntoConstraints = false
        accessoryStack.orientation = .horizontal
        accessoryStack.alignment = .centerY
        accessoryStack.spacing = 8
        accessoryStack.translatesAutoresizingMaskIntoConstraints = false

        header.addSubview(titleLabel)
        header.addSubview(subtitleLabel)
        header.addSubview(accessoryStack)

        let divider = Controls.separator(vertical: false)

        contentStack.orientation = .vertical
        contentStack.alignment = .leading
        contentStack.spacing = 8
        contentStack.edgeInsets = NSEdgeInsets(top: 12, left: 14, bottom: 18, right: 14)
        contentStack.translatesAutoresizingMaskIntoConstraints = false

        scrollView.translatesAutoresizingMaskIntoConstraints = false
        scrollView.hasVerticalScroller = true
        scrollView.autohidesScrollers = true
        scrollView.borderType = .noBorder
        scrollView.drawsBackground = false
        scrollView.documentView = contentStack

        emptyContainer.translatesAutoresizingMaskIntoConstraints = false
        emptyContainer.isHidden = true

        owner.addSubview(header)
        owner.addSubview(divider)
        owner.addSubview(scrollView)
        owner.addSubview(emptyContainer)

        NSLayoutConstraint.activate([
            header.leadingAnchor.constraint(equalTo: owner.leadingAnchor),
            header.trailingAnchor.constraint(equalTo: owner.trailingAnchor),
            header.topAnchor.constraint(equalTo: owner.topAnchor),

            titleLabel.leadingAnchor.constraint(equalTo: header.leadingAnchor, constant: 14),
            titleLabel.topAnchor.constraint(equalTo: header.topAnchor, constant: 12),
            titleLabel.trailingAnchor.constraint(lessThanOrEqualTo: accessoryStack.leadingAnchor, constant: -10),

            subtitleLabel.leadingAnchor.constraint(equalTo: titleLabel.leadingAnchor),
            subtitleLabel.topAnchor.constraint(equalTo: titleLabel.bottomAnchor, constant: 2),
            subtitleLabel.trailingAnchor.constraint(lessThanOrEqualTo: accessoryStack.leadingAnchor, constant: -10),
            subtitleLabel.bottomAnchor.constraint(equalTo: header.bottomAnchor, constant: -10),

            accessoryStack.trailingAnchor.constraint(equalTo: header.trailingAnchor, constant: -14),
            accessoryStack.centerYAnchor.constraint(equalTo: header.centerYAnchor),

            divider.leadingAnchor.constraint(equalTo: owner.leadingAnchor),
            divider.trailingAnchor.constraint(equalTo: owner.trailingAnchor),
            divider.topAnchor.constraint(equalTo: header.bottomAnchor),

            scrollView.leadingAnchor.constraint(equalTo: owner.leadingAnchor),
            scrollView.trailingAnchor.constraint(equalTo: owner.trailingAnchor),
            scrollView.topAnchor.constraint(equalTo: divider.bottomAnchor),
            scrollView.bottomAnchor.constraint(equalTo: owner.bottomAnchor),

            emptyContainer.leadingAnchor.constraint(equalTo: scrollView.leadingAnchor),
            emptyContainer.trailingAnchor.constraint(equalTo: scrollView.trailingAnchor),
            emptyContainer.topAnchor.constraint(equalTo: scrollView.topAnchor),
            emptyContainer.bottomAnchor.constraint(equalTo: scrollView.bottomAnchor),

            contentStack.leadingAnchor.constraint(equalTo: scrollView.contentView.leadingAnchor),
            contentStack.trailingAnchor.constraint(equalTo: scrollView.contentView.trailingAnchor),
            contentStack.topAnchor.constraint(equalTo: scrollView.contentView.topAnchor)
        ])
    }

    func addAccessory(_ view: NSView) {
        accessoryStack.addArrangedSubview(view)
    }

    /// Adds a full-width row. The stack's `alignment` pins the leading edge; the
    /// trailing constraint added here is what makes rows span the panel.
    func addRow(_ view: NSView) {
        view.translatesAutoresizingMaskIntoConstraints = false
        contentStack.addArrangedSubview(view)
        view.trailingAnchor.constraint(
            equalTo: contentStack.trailingAnchor,
            constant: -contentStack.edgeInsets.right
        ).isActive = true
    }

    func clearRows() {
        for view in contentStack.arrangedSubviews {
            contentStack.removeArrangedSubview(view)
            view.removeFromSuperview()
        }
    }

    /// Swaps the whole body for an empty state, or back again when `view` is nil.
    func showEmpty(_ view: NSView?) {
        for existing in emptyContainer.subviews where existing !== view {
            existing.removeFromSuperview()
        }
        guard let view else {
            emptyContainer.isHidden = true
            scrollView.isHidden = false
            return
        }
        if view.superview !== emptyContainer {
            view.translatesAutoresizingMaskIntoConstraints = false
            emptyContainer.addSubview(view)
            NSLayoutConstraint.activate([
                view.leadingAnchor.constraint(equalTo: emptyContainer.leadingAnchor),
                view.trailingAnchor.constraint(equalTo: emptyContainer.trailingAnchor),
                view.topAnchor.constraint(equalTo: emptyContainer.topAnchor),
                view.bottomAnchor.constraint(equalTo: emptyContainer.bottomAnchor)
            ])
        }
        emptyContainer.isHidden = false
        scrollView.isHidden = true
    }
}

// MARK: - Effects

private struct EffectSpec {
    let name: String
    let summary: String
}

/// The standard effects offered by "Add Effect", each with one plain-English
/// line describing what it actually does to the sound.
private enum EffectCatalog {
    static let standard: [EffectSpec] = [
        EffectSpec(name: "EQ", summary: "Turns parts of the sound up or down to make it brighter or warmer."),
        EffectSpec(name: "Compressor", summary: "Evens out the loud and quiet moments so the part sits steadily in the song."),
        EffectSpec(name: "Reverb", summary: "Adds the sound of a room, so the part feels like it was played in a real space."),
        EffectSpec(name: "Delay", summary: "Repeats the sound as fading echoes just after it plays."),
        EffectSpec(name: "Filter", summary: "Takes away the high or the low end — good for build-ups and lo-fi textures."),
        EffectSpec(name: "Chorus", summary: "Layers slightly detuned copies so one sound feels wide and thick."),
        EffectSpec(name: "Distortion", summary: "Adds grit and edge by pushing the sound until it breaks up."),
        EffectSpec(name: "Sidechain", summary: "Dips this track every time the kick drum hits, giving the beat room to breathe."),
        EffectSpec(name: "Limiter", summary: "Holds the loudest peaks back so nothing crackles or clips."),
        EffectSpec(name: "Normalize", summary: "Lifts the whole track to a steady loudness without changing its shape."),
        EffectSpec(name: "Reverse", summary: "Plays the sound backwards, from the end to the start.")
    ]

    static let genericSummary = "Shapes how this track sounds. Turn the amount up for a stronger effect."

    static func summary(for name: String) -> String {
        let lowered = name.lowercased()
        if let exact = standard.first(where: { $0.name.lowercased() == lowered }) {
            return exact.summary
        }
        if let fuzzy = standard.first(where: { lowered.contains($0.name.lowercased()) }) {
            return fuzzy.summary
        }
        return genericSummary
    }
}

/// One effect: a switch, its name, what it does, how strong it is, and a way to
/// remove it. Everything on the row is a standard control, so hover, focus ring,
/// keyboard operation and VoiceOver all work without extra code.
private final class EffectRowView: NeonCardView {
    let effectId: String

    private let switchControl = SwitchControl(frame: .zero)
    private let nameLabel = makeLabel("", font: Theme.Font.emphasis(13), color: Theme.text)
    private let summaryLabel = makeLabel("", font: Theme.Font.body(12), color: Theme.muted)
    private let amountLabel = makeLabel("", font: Theme.Font.mono(11), color: Theme.muted)
    private let detailStack = NSStackView()
    private var slider: NSSlider!
    private var deleteButton: NSButton!
    private var effectName: String

    /// `(newValue, isFinal)` — non-final values arrive continuously during a
    /// drag and only move the readout; the final one is written to the document.
    var onAmount: ((Double, Bool) -> Void)?
    var onToggle: ((Bool) -> Void)?
    var onDelete: (() -> Void)?

    init(effect: Effect) {
        effectId = effect.id
        effectName = effect.name
        super.init(frame: .zero)
        translatesAutoresizingMaskIntoConstraints = false

        let amount = max(0, min(1, effect.amount ?? 0.5))

        switchControl.handler = { [weak self] isOn in self?.onToggle?(isOn) }

        slider = Controls.slider(
            value: amount,
            min: 0,
            max: 1,
            help: "How strong this effect is. Far left is barely there, far right is as much as it goes.",
            accessibilityLabel: "\(effect.name) amount"
        ) { [weak self] value in
            guard let self else { return }
            self.amountLabel.stringValue = neonPercentText(value)
            self.onAmount?(value, !neonSliderIsMidDrag())
        }

        deleteButton = Controls.button(
            title: "",
            symbol: "trash",
            help: "Remove \(effect.name) from this track.",
            style: .destructive
        ) { [weak self] in self?.onDelete?() }

        nameLabel.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        summaryLabel.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        amountLabel.alignment = .right

        detailStack.orientation = .vertical
        detailStack.alignment = .leading
        detailStack.spacing = 2
        detailStack.translatesAutoresizingMaskIntoConstraints = false
        detailStack.addArrangedSubview(nameLabel)
        detailStack.addArrangedSubview(summaryLabel)
        detailStack.setContentHuggingPriority(.defaultLow, for: .horizontal)
        detailStack.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)

        let amountStack = NSStackView(views: [slider, amountLabel])
        amountStack.orientation = .horizontal
        amountStack.alignment = .centerY
        amountStack.spacing = 8
        amountStack.translatesAutoresizingMaskIntoConstraints = false

        let row = NSStackView(views: [switchControl, detailStack, amountStack, deleteButton])
        row.orientation = .horizontal
        row.alignment = .centerY
        row.spacing = 12
        row.translatesAutoresizingMaskIntoConstraints = false
        addSubview(row)

        NSLayoutConstraint.activate([
            row.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 12),
            row.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -10),
            row.topAnchor.constraint(equalTo: topAnchor, constant: 10),
            row.bottomAnchor.constraint(equalTo: bottomAnchor, constant: -10),
            slider.widthAnchor.constraint(equalToConstant: 132),
            amountLabel.widthAnchor.constraint(equalToConstant: 42),
            heightAnchor.constraint(greaterThanOrEqualToConstant: 62)
        ])

        setAccessibilityRole(.group)
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    func update(effect: Effect, trackName: String) {
        effectName = effect.name
        let isOn = effect.active ?? true
        let amount = max(0, min(1, effect.amount ?? 0.5))
        let summary = EffectCatalog.summary(for: effect.name)

        nameLabel.stringValue = effect.name
        nameLabel.textColor = isOn ? Theme.text : Theme.muted
        summaryLabel.stringValue = summary
        summaryLabel.toolTip = summary
        amountLabel.stringValue = neonPercentText(amount)

        let desiredState: NSControl.StateValue = isOn ? .on : .off
        if switchControl.state != desiredState { switchControl.state = desiredState }
        if abs(slider.doubleValue - amount) > 0.0005 { slider.doubleValue = amount }

        // Off effects stay completely operable — only quieter to look at.
        detailStack.alphaValue = isOn ? 1 : 0.55
        slider.alphaValue = isOn ? 1 : 0.55
        amountLabel.alphaValue = isOn ? 1 : 0.55

        let switchHelp = isOn
            ? "\(effect.name) is on for \(trackName). Switch it off to hear the track without it."
            : "\(effect.name) is off. Switch it on to hear it on \(trackName)."
        switchControl.toolTip = AppEnvironment.shared.help(switchHelp, term: "Effect")
        switchControl.setAccessibilityLabel("\(effect.name) on \(trackName)")
        switchControl.setAccessibilityHelp(switchHelp)

        slider.toolTip = AppEnvironment.shared.help(
            "How strong \(effect.name) is on \(trackName). Currently \(neonPercentText(amount)).",
            term: "Effect"
        )
        amountLabel.toolTip = slider.toolTip
        deleteButton.toolTip = "Remove \(effect.name) from \(trackName)."
        deleteButton.setAccessibilityLabel("Remove \(effect.name)")

        toolTip = summary
        setAccessibilityLabel("\(effect.name), \(isOn ? "on" : "off"), amount \(neonPercentText(amount))")
        setAccessibilityHelp(summary)
    }

    // Right-click does the same two things the row does, from wherever the
    // pointer happens to be.
    override func menu(for event: NSEvent) -> NSMenu? {
        let menu = NSMenu(title: effectName)
        let isOn = switchControl.state == .on
        let toggleItem = NSMenuItem(
            title: isOn ? "Turn Off \(effectName)" : "Turn On \(effectName)",
            action: #selector(menuToggle),
            keyEquivalent: ""
        )
        toggleItem.target = self
        menu.addItem(toggleItem)
        menu.addItem(NSMenuItem.separator())
        let removeItem = NSMenuItem(title: "Remove \(effectName)", action: #selector(menuRemove), keyEquivalent: "")
        removeItem.target = self
        menu.addItem(removeItem)
        return menu
    }

    @objc private func menuToggle() {
        let next = switchControl.state != .on
        switchControl.state = next ? .on : .off
        onToggle?(next)
    }

    @objc private func menuRemove() {
        onDelete?()
    }
}

/// The Effects panel: one row per effect on the selected track.
final class EffectsView: NSView, EditorCanvas {

    weak var host: EditorHost? {
        didSet { refresh() }
    }

    private var scaffold: NeonPaneScaffold!
    private var rows: [EffectRowView] = []
    private var renderedKey: [String] = []
    private var addButton: NSButton!

    private lazy var noTrackState = EmptyStateView(
        symbol: "wand.and.rays",
        title: "No track selected",
        body: "Pick a track on the left to see its effects."
    )

    private lazy var noEffectsState = EmptyStateView(
        symbol: "wand.and.rays",
        title: "No effects yet",
        body: "Effects shape how a track sounds.",
        actionTitle: "Add Effect",
        action: { [weak self] in self?.presentAddEffectMenu(from: nil) }
    )

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        setup()
    }

    convenience init() {
        self.init(frame: .zero)
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    private func setup() {
        translatesAutoresizingMaskIntoConstraints = false
        wantsLayer = true

        scaffold = NeonPaneScaffold(
            owner: self,
            title: "Effects",
            subtitle: WorkView.plugins.explanation
        )

        addButton = Controls.button(
            title: "Add Effect",
            symbol: "plus",
            help: AppEnvironment.shared.help(
                "Choose an effect to add to the selected track.",
                term: "Effect"
            )
        ) { [weak self] in
            guard let self else { return }
            self.presentAddEffectMenu(from: self.addButton)
        }
        scaffold.addAccessory(Controls.glossary("Effect", Glossary.long("Effect")))
        scaffold.addAccessory(addButton)

        setAccessibilityRole(.group)
        setAccessibilityLabel("Effects")
        setAccessibilityHelp(WorkView.plugins.explanation)
        toolTip = WorkView.plugins.explanation
    }

    // MARK: EditorCanvas

    func refresh() {
        guard let host, let track = host.selectedTrack else {
            scaffold.titleLabel.stringValue = "Effects"
            scaffold.subtitleLabel.stringValue = WorkView.plugins.explanation
            addButton.isEnabled = false
            rows = []
            renderedKey = []
            scaffold.clearRows()
            scaffold.showEmpty(noTrackState)
            return
        }

        addButton.isEnabled = true
        let effects = track.effects ?? []
        let onCount = effects.filter { $0.active ?? true }.count
        scaffold.titleLabel.stringValue = "Effects on \(track.name)"
        scaffold.subtitleLabel.stringValue = effects.isEmpty
            ? WorkView.plugins.explanation
            : "\(onCount) of \(effects.count) switched on. Each row is one effect."

        guard !effects.isEmpty else {
            rows = []
            renderedKey = []
            scaffold.clearRows()
            noEffectsState.update(
                title: "No effects on \(track.name) yet",
                body: "Effects change how a track sounds — reverb adds space, a compressor evens out the loud and quiet parts. Add one to hear the difference."
            )
            noEffectsState.isActionEnabled = true
            scaffold.showEmpty(noEffectsState)
            return
        }

        scaffold.showEmpty(nil)
        let key = [track.id] + effects.map { $0.id }
        if key != renderedKey {
            rebuild(effects: effects, track: track)
        }
        // Rows are updated in place so a slider being dragged is never torn out
        // from under the pointer.
        for (row, effect) in zip(rows, effects) {
            row.update(effect: effect, trackName: track.name)
        }
    }

    /// This panel scrolls its own content, so it always fits the space it is given.
    func contentSize(fittingVisible visible: NSSize) -> NSSize { visible }

    // MARK: Building

    private func rebuild(effects: [Effect], track: Track) {
        scaffold.clearRows()
        rows = effects.map { effect in
            let row = EffectRowView(effect: effect)
            let id = effect.id
            let name = effect.name
            row.onToggle = { [weak self] isOn in self?.setActive(isOn, id: id, name: name) }
            row.onAmount = { [weak self] value, isFinal in
                guard isFinal else { return }
                self?.setAmount(value, id: id, name: name)
            }
            row.onDelete = { [weak self] in self?.removeEffect(id: id, name: name) }
            scaffold.addRow(row)
            return row
        }
        renderedKey = [track.id] + effects.map { $0.id }
    }

    // MARK: Actions

    private func presentAddEffectMenu(from sender: NSView?) {
        guard let host, let track = host.selectedTrack else { return }
        let existing = Set((track.effects ?? []).map { $0.name.lowercased() })
        let menu = NSMenu(title: "Add Effect")
        for spec in EffectCatalog.standard where !existing.contains(spec.name.lowercased()) {
            let item = NSMenuItem(title: spec.name, action: #selector(addEffectFromMenu(_:)), keyEquivalent: "")
            item.target = self
            item.representedObject = spec.name
            item.toolTip = spec.summary
            menu.addItem(item)
        }
        if menu.items.isEmpty {
            menu.addItem(NSMenuItem(
                title: "Every standard effect is already on \(track.name)",
                action: nil,
                keyEquivalent: ""
            ))
        }
        if let sender {
            _ = menu.popUp(
                positioning: nil,
                at: NSPoint(x: 0, y: sender.bounds.height + 4),
                in: sender
            )
        } else {
            _ = menu.popUp(positioning: nil, at: NSPoint(x: bounds.midX, y: bounds.midY), in: self)
        }
    }

    @objc private func addEffectFromMenu(_ sender: NSMenuItem) {
        guard let name = sender.representedObject as? String else { return }
        addEffect(named: name)
    }

    private func addEffect(named name: String) {
        guard let host, let track = host.selectedTrack else { return }
        let trackId = track.id
        host.edit("Add Effect") { project in
            guard let index = project.snapshot.tracks.firstIndex(where: { $0.id == trackId }) else { return }
            var effects = project.snapshot.tracks[index].effects ?? []
            effects.append(Effect(id: makeId("fx"), name: name, active: true, amount: 0.5))
            project.snapshot.tracks[index].effects = effects
        }
        StatusCenter.shared.success(
            "Added \(name) to \(track.name).",
            detail: "It starts halfway up. Press Command-Z to undo."
        )
    }

    private func setActive(_ isOn: Bool, id: String, name: String) {
        guard let track = host?.selectedTrack else { return }
        mutateEffect(id: id, actionName: isOn ? "Turn On \(name)" : "Turn Off \(name)") { effect in
            effect.active = isOn
        }
        StatusCenter.shared.success(
            isOn ? "\(name) is on for \(track.name)." : "\(name) is off for \(track.name).",
            detail: "Press Command-Z to undo."
        )
    }

    private func setAmount(_ value: Double, id: String, name: String) {
        let clamped = max(0, min(1, value))
        mutateEffect(id: id, actionName: "Adjust \(name)") { effect in
            effect.amount = clamped
        }
        StatusCenter.shared.info(
            "\(name) set to \(neonPercentText(clamped)).",
            detail: "Press Command-Z to undo."
        )
    }

    private func removeEffect(id: String, name: String) {
        guard let host, let track = host.selectedTrack else { return }
        let trackId = track.id
        host.edit("Remove Effect") { project in
            guard let index = project.snapshot.tracks.firstIndex(where: { $0.id == trackId }) else { return }
            project.snapshot.tracks[index].effects = (project.snapshot.tracks[index].effects ?? [])
                .filter { $0.id != id }
        }
        StatusCenter.shared.success(
            "Removed \(name) from \(track.name).",
            detail: "Press Command-Z to undo."
        )
    }

    private func mutateEffect(id: String, actionName: String, _ body: (inout Effect) -> Void) {
        guard let host, let track = host.selectedTrack else { return }
        let trackId = track.id
        host.edit(actionName) { project in
            guard let trackIndex = project.snapshot.tracks.firstIndex(where: { $0.id == trackId }) else { return }
            var effects = project.snapshot.tracks[trackIndex].effects ?? []
            guard let effectIndex = effects.firstIndex(where: { $0.id == id }) else { return }
            body(&effects[effectIndex])
            project.snapshot.tracks[trackIndex].effects = effects
        }
    }
}

// MARK: - Sample editor

private struct WaveformData {
    let peaks: [Float]
    let duration: Double
    let sampleRate: Double
    let channelCount: Int

    var isUsable: Bool { duration > 0 && !peaks.isEmpty }

    static let unreadable = WaveformData(peaks: [], duration: 0, sampleRate: 0, channelCount: 0)
}

/// Reads audio peaks once per file and keeps them.
///
/// The cache key includes the file's size and modification date, so re-rendering
/// a stem updates the drawing while normal redraws never touch the disk. All
/// dictionary access happens on the main thread; only decoding runs off it.
private final class WaveformStore {
    static let shared = WaveformStore()

    private var cache: [String: WaveformData] = [:]
    private var waiting: [String: [(WaveformData) -> Void]] = [:]
    private let queue = DispatchQueue(label: "com.neonstudio.waveform", qos: .userInitiated)

    private func key(for url: URL) -> String {
        let values = try? url.resourceValues(forKeys: [.contentModificationDateKey, .fileSizeKey])
        let stamp = values?.contentModificationDate?.timeIntervalSince1970 ?? 0
        let size = values?.fileSize ?? 0
        return "\(url.path)|\(Int(stamp))|\(size)"
    }

    func cached(_ url: URL) -> WaveformData? {
        cache[key(for: url)]
    }

    func load(_ url: URL, completion: @escaping (WaveformData) -> Void) {
        let cacheKey = key(for: url)
        if let hit = cache[cacheKey] {
            completion(hit)
            return
        }
        if waiting[cacheKey] != nil {
            waiting[cacheKey]?.append(completion)
            return
        }
        waiting[cacheKey] = [completion]
        queue.async {
            let data = WaveformStore.read(url)
            DispatchQueue.main.async {
                self.cache[cacheKey] = data
                let callbacks = self.waiting.removeValue(forKey: cacheKey) ?? []
                for callback in callbacks { callback(data) }
            }
        }
    }

    private static func read(_ url: URL, buckets: Int = 1600) -> WaveformData {
        guard let file = try? AVAudioFile(forReading: url) else { return .unreadable }
        let format = file.processingFormat
        let totalFrames = file.length
        guard totalFrames > 0, format.channelCount > 0, format.sampleRate > 0 else { return .unreadable }

        let duration = Double(totalFrames) / format.sampleRate
        let framesPerBucket = max(1, Int(totalFrames) / buckets)
        var peaks = [Float](repeating: 0, count: buckets)

        guard let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 65_536) else { return .unreadable }
        let channelCount = Int(format.channelCount)
        var frameOffset = 0

        while true {
            do {
                try file.read(into: buffer)
            } catch {
                break
            }
            let frames = Int(buffer.frameLength)
            if frames == 0 { break }
            guard let channels = buffer.floatChannelData else { break }
            for frame in 0..<frames {
                var peak: Float = 0
                for channel in 0..<channelCount {
                    peak = max(peak, abs(channels[channel][frame]))
                }
                let bucket = min(buckets - 1, (frameOffset + frame) / framesPerBucket)
                if peak > peaks[bucket] { peaks[bucket] = peak }
            }
            frameOffset += frames
        }

        return WaveformData(
            peaks: peaks,
            duration: duration,
            sampleRate: file.fileFormat.sampleRate,
            channelCount: Int(file.fileFormat.channelCount)
        )
    }
}

/// The waveform canvas, with two draggable trim grips.
///
/// Drawing and hit-testing both go through `geometry()`; there is no pixel
/// constant duplicated between them.
private final class WaveformStripView: NSView {

    private struct Geometry {
        static let handleWidth: CGFloat = 12
        static let gripHeight: CGFloat = 34

        let plot: NSRect
        let duration: Double

        func x(forSeconds seconds: Double) -> CGFloat {
            guard duration > 0 else { return plot.minX }
            let fraction = min(max(seconds / duration, 0), 1)
            return plot.minX + plot.width * CGFloat(fraction)
        }

        func seconds(forX x: CGFloat) -> Double {
            guard duration > 0, plot.width > 0 else { return 0 }
            let fraction = min(max(Double((x - plot.minX) / plot.width), 0), 1)
            return fraction * duration
        }

        /// The whole-height column a grip can be grabbed anywhere along.
        func handleRect(atSeconds seconds: Double) -> NSRect {
            NSRect(
                x: x(forSeconds: seconds) - Geometry.handleWidth / 2,
                y: plot.minY,
                width: Geometry.handleWidth,
                height: plot.height
            )
        }

        /// The visible grip in the middle of that column.
        func gripRect(atSeconds seconds: Double) -> NSRect {
            let column = handleRect(atSeconds: seconds)
            return NSRect(
                x: column.minX,
                y: column.midY - Geometry.gripHeight / 2,
                width: column.width,
                height: Geometry.gripHeight
            )
        }
    }

    private enum Handle { case start, end }

    var peaks: [Float] = [] { didSet { needsDisplay = true } }
    var duration: Double = 0 { didSet { trimGeometryChanged() } }
    var trimStart: Double = 0 { didSet { trimGeometryChanged() } }
    var trimEnd: Double? { didSet { trimGeometryChanged() } }
    var waveColor: NSColor = Theme.accent { didSet { needsDisplay = true } }
    var message: String? { didSet { needsDisplay = true } }
    var isEnabled: Bool = false { didSet { trimGeometryChanged() } }

    /// Live values while a grip is being dragged — labels follow the drag.
    var onPreview: ((Double, Double?) -> Void)?
    /// Fired once, when the drag ends or a key press changes the trim.
    var onCommit: ((Double, Double?) -> Void)?
    var onResetTrim: (() -> Void)?
    var onReveal: (() -> Void)?

    private var activeHandle: Handle?
    private var draftStart: Double = 0
    private var draftEnd: Double?
    private var menuSeconds: Double = 0

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        translatesAutoresizingMaskIntoConstraints = false
        setAccessibilityRole(.group)
        setAccessibilityLabel("Waveform")
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    private func trimGeometryChanged() {
        needsDisplay = true
        window?.invalidateCursorRects(for: self)
    }

    private func geometry() -> Geometry {
        Geometry(plot: bounds.insetBy(dx: 12, dy: 12), duration: duration)
    }

    private var effectiveStart: Double { activeHandle == nil ? trimStart : draftStart }
    private var effectiveEnd: Double? { activeHandle == nil ? trimEnd : draftEnd }

    // MARK: Drawing

    override func draw(_ dirtyRect: NSRect) {
        roundedFill(bounds, radius: Theme.Metric.cornerRadius, color: Theme.canvas)
        roundedStroke(bounds, radius: Theme.Metric.cornerRadius, color: Theme.subtleStroke)

        let g = geometry()
        drawLine(
            from: NSPoint(x: g.plot.minX, y: g.plot.midY),
            to: NSPoint(x: g.plot.maxX, y: g.plot.midY),
            color: Theme.subtleStroke
        )

        guard isEnabled, duration > 0, !peaks.isEmpty else {
            let text = message ?? "No sound file on this track."
            drawText(
                text,
                in: NSRect(x: g.plot.minX, y: g.plot.midY - 9, width: g.plot.width, height: 18),
                color: Theme.dim,
                font: Theme.Font.body(12),
                alignment: .center
            )
            return
        }

        // Waveform bars, two points apart.
        let columns = max(1, Int(g.plot.width / 2))
        let bars = NSBezierPath()
        let halfHeight = max(2, g.plot.height / 2 - 8)
        for column in 0..<columns {
            let lower = column * peaks.count / columns
            let upper = max(lower + 1, (column + 1) * peaks.count / columns)
            var peak: Float = 0
            for index in lower..<min(upper, peaks.count) {
                peak = max(peak, peaks[index])
            }
            let height = max(1, CGFloat(peak) * halfHeight)
            bars.appendRect(NSRect(
                x: g.plot.minX + CGFloat(column) * 2,
                y: g.plot.midY - height,
                width: 1.4,
                height: height * 2
            ))
        }
        waveColor.setFill()
        bars.fill()

        // Everything outside the trim is shaded, so what will be heard is obvious.
        let startX = g.x(forSeconds: effectiveStart)
        let endX = g.x(forSeconds: effectiveEnd ?? duration)
        let shade = Theme.app.withAlphaComponent(0.72)
        if startX > g.plot.minX {
            NSRect(x: g.plot.minX, y: g.plot.minY, width: startX - g.plot.minX, height: g.plot.height)
                .fill(with: shade)
        }
        if endX < g.plot.maxX {
            NSRect(x: endX, y: g.plot.minY, width: g.plot.maxX - endX, height: g.plot.height)
                .fill(with: shade)
        }

        drawHandle(at: effectiveStart, in: g)
        drawHandle(at: effectiveEnd ?? duration, in: g)

        let caption = "Kept: \(neonShortTimeText(effectiveStart))s to \(neonShortTimeText(effectiveEnd ?? duration))s"
        drawText(
            caption,
            in: NSRect(x: g.plot.minX + 4, y: g.plot.maxY - 15, width: g.plot.width - 8, height: 14),
            color: Theme.muted,
            font: Theme.Font.mono(11)
        )
    }

    private func drawHandle(at seconds: Double, in g: Geometry) {
        let column = g.handleRect(atSeconds: seconds)
        drawLine(
            from: NSPoint(x: column.midX, y: g.plot.minY),
            to: NSPoint(x: column.midX, y: g.plot.maxY),
            color: Theme.accent
        )
        let grip = g.gripRect(atSeconds: seconds)
        roundedFill(grip, radius: 3, color: Theme.accent)
        let line = Theme.accent.readableForeground
        drawLine(
            from: NSPoint(x: grip.midX - 2, y: grip.minY + 9),
            to: NSPoint(x: grip.midX - 2, y: grip.maxY - 9),
            color: line
        )
        drawLine(
            from: NSPoint(x: grip.midX + 2, y: grip.minY + 9),
            to: NSPoint(x: grip.midX + 2, y: grip.maxY - 9),
            color: line
        )
    }

    override func drawFocusRingMask() {
        NSBezierPath(
            roundedRect: bounds,
            xRadius: Theme.Metric.cornerRadius,
            yRadius: Theme.Metric.cornerRadius
        ).fill()
    }

    override var focusRingMaskBounds: NSRect { bounds }

    // MARK: Mouse

    override func resetCursorRects() {
        super.resetCursorRects()
        guard isEnabled, duration > 0 else { return }
        let g = geometry()
        addCursorRect(g.handleRect(atSeconds: trimStart), cursor: .resizeLeftRight)
        addCursorRect(g.handleRect(atSeconds: trimEnd ?? duration), cursor: .resizeLeftRight)
    }

    override func mouseDown(with event: NSEvent) {
        guard isEnabled, duration > 0 else {
            super.mouseDown(with: event)
            return
        }
        window?.makeFirstResponder(self)
        let point = convert(event.locationInWindow, from: nil)
        let g = geometry()
        let startRect = g.handleRect(atSeconds: trimStart).insetBy(dx: -5, dy: 0)
        let endRect = g.handleRect(atSeconds: trimEnd ?? duration).insetBy(dx: -5, dy: 0)

        draftStart = trimStart
        draftEnd = trimEnd

        // Only the two grips drag. A click in the body just takes focus, so a
        // misplaced click can never silently re-trim the sample; use the
        // right-click menu, the fields below, or the arrow keys instead.
        if startRect.contains(point) {
            activeHandle = .start
        } else if endRect.contains(point) {
            activeHandle = .end
        } else {
            activeHandle = nil
        }
        needsDisplay = true
    }

    override func mouseDragged(with event: NSEvent) {
        guard activeHandle != nil else {
            super.mouseDragged(with: event)
            return
        }
        let point = convert(event.locationInWindow, from: nil)
        applyDrag(toSeconds: geometry().seconds(forX: point.x))
        needsDisplay = true
    }

    override func mouseUp(with event: NSEvent) {
        guard activeHandle != nil else {
            super.mouseUp(with: event)
            return
        }
        activeHandle = nil
        // A click on a grip that never moved is not an edit, so it must not put
        // a do-nothing entry on the undo stack.
        let movedStart = abs(draftStart - trimStart) > 0.0005
        let movedEnd = (draftEnd ?? duration) != (trimEnd ?? duration)
        guard movedStart || movedEnd else {
            needsDisplay = true
            return
        }
        onCommit?(draftStart, normalisedEnd(draftEnd))
    }

    private func applyDrag(toSeconds seconds: Double) {
        guard let handle = activeHandle else { return }
        let minimumLength = min(0.01, duration / 100)
        switch handle {
        case .start:
            let limit = (draftEnd ?? duration) - minimumLength
            draftStart = min(max(0, seconds), max(0, limit))
        case .end:
            draftEnd = max(draftStart + minimumLength, min(seconds, duration))
        }
        onPreview?(draftStart, normalisedEnd(draftEnd))
    }

    /// The model stores "to the end of the file" as no value at all.
    private func normalisedEnd(_ end: Double?) -> Double? {
        guard let end else { return nil }
        return end >= duration - 0.0005 ? nil : end
    }

    // MARK: Keyboard

    override var acceptsFirstResponder: Bool { isEnabled }

    override func becomeFirstResponder() -> Bool {
        needsDisplay = true
        return super.becomeFirstResponder()
    }

    override func resignFirstResponder() -> Bool {
        needsDisplay = true
        return super.resignFirstResponder()
    }

    override func keyDown(with event: NSEvent) {
        guard isEnabled, duration > 0,
              let scalar = event.charactersIgnoringModifiers?.unicodeScalars.first else {
            super.keyDown(with: event)
            return
        }
        let movesEnd = event.modifierFlags.contains(.shift)
        let step = event.modifierFlags.contains(.option) ? 0.01 : 0.1
        var start = trimStart
        var end = trimEnd ?? duration

        switch Int(scalar.value) {
        case NSLeftArrowFunctionKey:
            if movesEnd { end = max(start + 0.01, end - step) } else { start = max(0, start - step) }
        case NSRightArrowFunctionKey:
            if movesEnd { end = min(duration, end + step) } else { start = min(end - 0.01, start + step) }
        default:
            super.keyDown(with: event)
            return
        }
        onCommit?(start, normalisedEnd(end))
    }

    // MARK: Menu and accessibility

    override func menu(for event: NSEvent) -> NSMenu? {
        guard isEnabled, duration > 0 else { return nil }
        menuSeconds = geometry().seconds(forX: convert(event.locationInWindow, from: nil).x)
        let menu = NSMenu(title: "Sample")

        let startItem = NSMenuItem(title: "Start Here", action: #selector(menuTrimStartHere), keyEquivalent: "")
        startItem.target = self
        startItem.toolTip = "Skip everything before this point."
        menu.addItem(startItem)

        let endItem = NSMenuItem(title: "End Here", action: #selector(menuTrimEndHere), keyEquivalent: "")
        endItem.target = self
        endItem.toolTip = "Stop playing at this point."
        menu.addItem(endItem)

        menu.addItem(NSMenuItem.separator())

        let resetItem = NSMenuItem(title: "Use the Whole File", action: #selector(menuResetTrim), keyEquivalent: "")
        resetItem.target = self
        resetItem.toolTip = "Clear the trim so the whole sound plays."
        menu.addItem(resetItem)

        menu.addItem(NSMenuItem.separator())

        let revealItem = NSMenuItem(title: "Reveal in Finder", action: #selector(menuReveal), keyEquivalent: "")
        revealItem.target = self
        menu.addItem(revealItem)

        return menu
    }

    @objc private func menuTrimStartHere() {
        let end = trimEnd ?? duration
        onCommit?(min(menuSeconds, max(0, end - 0.01)), normalisedEnd(trimEnd))
    }

    @objc private func menuTrimEndHere() {
        onCommit?(trimStart, normalisedEnd(max(trimStart + 0.01, menuSeconds)))
    }

    @objc private func menuResetTrim() {
        onResetTrim?()
    }

    @objc private func menuReveal() {
        onReveal?()
    }

    /// VoiceOver reaches the two grips as elements of their own.
    override func accessibilityChildren() -> [Any]? {
        guard isEnabled, duration > 0 else { return nil }
        let g = geometry()
        let start = accessibilityHandle(
            frame: g.handleRect(atSeconds: trimStart),
            label: "Trim start, \(neonShortTimeText(trimStart)) seconds"
        )
        let end = accessibilityHandle(
            frame: g.handleRect(atSeconds: trimEnd ?? duration),
            label: "Trim end, \(neonShortTimeText(trimEnd ?? duration)) seconds"
        )
        return [start, end]
    }

    private func accessibilityHandle(frame: NSRect, label: String) -> Any {
        let windowRect = convert(frame, to: nil)
        let screenRect = window?.convertToScreen(windowRect) ?? windowRect
        return NSAccessibilityElement.element(
            withRole: .slider,
            frame: screenRect,
            label: label,
            parent: self
        )
    }
}

/// The Sample panel: what audio a track plays, and how it is reshaped.
final class SampleEditorView: NSView, EditorCanvas {

    weak var host: EditorHost? {
        didSet { refresh() }
    }

    private var scaffold: NeonPaneScaffold!

    private let fileCard = NeonCardView()
    private let fileNameLabel = makeLabel("", font: Theme.Font.emphasis(13), color: Theme.text)
    private let fileSpecLabel = makeLabel("", font: Theme.Font.mono(11), color: Theme.muted)
    private let fileProblemLabel = makeLabel("", font: Theme.Font.body(12), color: Theme.danger)
    private var revealButton: NSButton!
    private var locateButton: NSButton!

    private let waveform = WaveformStripView(frame: .zero)

    private let shapeCard = NeonCardView()
    private var pitchSlider: NSSlider!
    private var pitchStepper: StepperControl!
    private let pitchLabel = makeLabel("", font: Theme.Font.mono(11), color: Theme.muted)
    private var speedSlider: NSSlider!
    private let speedLabel = makeLabel("", font: Theme.Font.mono(11), color: Theme.muted)
    private var normalizeToggle: NSButton!
    private var reverseToggle: NSButton!
    private var trimStartField: NSTextField!
    private var trimEndField: NSTextField!
    private var resetTrimButton: NSButton!

    private var pendingWaveformKey: String?

    private lazy var noTrackState = EmptyStateView(
        symbol: "waveform",
        title: "No track selected",
        body: "Pick a track on the left to see the sound file it plays."
    )

    private lazy var noAudioState = EmptyStateView(
        symbol: "waveform",
        title: "No sound file",
        body: Glossary.long("Sample"),
        actionTitle: "Go to \(WorkView.playlist.label)",
        action: { [weak self] in self?.host?.requestFocus(on: .playlist) }
    )

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        setup()
    }

    convenience init() {
        self.init(frame: .zero)
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    private func setup() {
        translatesAutoresizingMaskIntoConstraints = false
        wantsLayer = true

        scaffold = NeonPaneScaffold(
            owner: self,
            title: "Sample",
            subtitle: WorkView.sample.explanation
        )
        scaffold.addAccessory(Controls.glossary("Sample", Glossary.long("Sample")))

        buildFileCard()
        buildWaveform()
        buildShapeCard()

        setAccessibilityRole(.group)
        setAccessibilityLabel("Sample editor")
        setAccessibilityHelp(WorkView.sample.explanation)
        toolTip = WorkView.sample.explanation
    }

    private func buildFileCard() {
        revealButton = Controls.button(
            title: "Reveal in Finder",
            symbol: "folder",
            help: "Shows this sound file in a Finder window."
        ) { [weak self] in self?.revealInFinder() }

        locateButton = Controls.button(
            title: "Locate File…",
            symbol: "magnifyingglass",
            help: "Choose where this sound file lives now, and point the track at it."
        ) { [weak self] in self?.locateFile() }

        fileNameLabel.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        fileProblemLabel.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)

        let buttons = NSStackView(views: [revealButton, locateButton])
        buttons.orientation = .horizontal
        buttons.spacing = 8
        buttons.alignment = .centerY
        buttons.translatesAutoresizingMaskIntoConstraints = false

        let stack = NSStackView(views: [fileNameLabel, fileSpecLabel, fileProblemLabel, buttons])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 5
        stack.translatesAutoresizingMaskIntoConstraints = false
        fileCard.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: fileCard.leadingAnchor, constant: 12),
            stack.trailingAnchor.constraint(lessThanOrEqualTo: fileCard.trailingAnchor, constant: -12),
            stack.topAnchor.constraint(equalTo: fileCard.topAnchor, constant: 10),
            stack.bottomAnchor.constraint(equalTo: fileCard.bottomAnchor, constant: -10)
        ])
        fileCard.setAccessibilityRole(.group)
        fileCard.setAccessibilityLabel("Sound file")
        scaffold.addRow(fileCard)
    }

    private func buildWaveform() {
        waveform.toolTip = AppEnvironment.shared.help(
            "The shape of the recorded sound. Drag the two grips to choose which part plays; the shaded parts are skipped. With the waveform selected, arrow keys move the start and Shift with arrow keys moves the end.",
            term: "Sample"
        )
        waveform.setAccessibilityHelp(waveform.toolTip)
        waveform.onPreview = { [weak self] start, end in
            self?.updateTrimReadouts(start: start, end: end)
        }
        waveform.onCommit = { [weak self] start, end in
            self?.commitTrim(start: start, end: end)
        }
        waveform.onResetTrim = { [weak self] in
            self?.commitTrim(start: 0, end: nil)
        }
        waveform.onReveal = { [weak self] in self?.revealInFinder() }
        scaffold.addRow(waveform)
        waveform.heightAnchor.constraint(equalToConstant: 156).isActive = true
    }

    private func buildShapeCard() {
        pitchSlider = Controls.slider(
            value: 0,
            min: -24,
            max: 24,
            help: "Moves the sound up or down in pitch. 12 steps is a whole octave.",
            accessibilityLabel: "Pitch in semitones"
        ) { [weak self] value in
            self?.handlePitch(value, commit: !neonSliderIsMidDrag())
        }
        pitchSlider.widthAnchor.constraint(equalToConstant: 200).isActive = true

        pitchStepper = StepperControl(frame: .zero)
        pitchStepper.minValue = -24
        pitchStepper.maxValue = 24
        pitchStepper.increment = 1
        pitchStepper.valueWraps = false
        pitchStepper.toolTip = "Move the pitch one step at a time."
        pitchStepper.setAccessibilityLabel("Pitch step")
        pitchStepper.handler = { [weak self] value in
            self?.handlePitch(value, commit: true)
        }

        speedSlider = Controls.slider(
            value: 1,
            min: 0.25,
            max: 4,
            help: "Plays the sound faster or slower. 100% is exactly as recorded.",
            accessibilityLabel: "Speed"
        ) { [weak self] value in
            self?.handleSpeed(value, commit: !neonSliderIsMidDrag())
        }
        speedSlider.widthAnchor.constraint(equalToConstant: 200).isActive = true

        normalizeToggle = Controls.toggle(
            title: "Even Out Volume",
            symbol: "waveform.badge.plus",
            help: "Lifts the whole sound to a steady loudness without changing its shape. Producers call this normalising."
        ) { [weak self] isOn in self?.setNormalize(isOn) }

        reverseToggle = Controls.toggle(
            title: "Play Backwards",
            symbol: "arrow.uturn.left",
            help: "Plays the sound in reverse, from the end to the start."
        ) { [weak self] isOn in self?.setReverse(isOn) }

        trimStartField = Controls.numberField(
            value: "0.00",
            placeholder: "0.00",
            help: "How many seconds to skip at the beginning.",
            accessibilityLabel: "Trim start in seconds",
            width: 78
        ) { [weak self] text in self?.commitTrimStartText(text) }

        trimEndField = Controls.numberField(
            value: "",
            placeholder: "end",
            help: "The second the sound stops at. Leave it empty to play to the end.",
            accessibilityLabel: "Trim end in seconds",
            width: 78
        ) { [weak self] text in self?.commitTrimEndText(text) }

        resetTrimButton = Controls.button(
            title: "Use the Whole File",
            symbol: "arrow.counterclockwise",
            help: "Clears the trim so the whole sound plays again."
        ) { [weak self] in self?.commitTrim(start: 0, end: nil) }

        let pitchRow = NSStackView(views: [pitchSlider, pitchStepper, pitchLabel])
        pitchRow.orientation = .horizontal
        pitchRow.alignment = .centerY
        pitchRow.spacing = 8

        let speedRow = NSStackView(views: [speedSlider, speedLabel])
        speedRow.orientation = .horizontal
        speedRow.alignment = .centerY
        speedRow.spacing = 8

        let trimRow = NSStackView(views: [
            trimStartField,
            makeLabel("to", font: Theme.Font.caption(11), color: Theme.muted),
            trimEndField,
            makeLabel("seconds", font: Theme.Font.caption(11), color: Theme.muted),
            resetTrimButton
        ])
        trimRow.orientation = .horizontal
        trimRow.alignment = .centerY
        trimRow.spacing = 8

        let toggleRow = NSStackView(views: [normalizeToggle, reverseToggle])
        toggleRow.orientation = .horizontal
        toggleRow.alignment = .centerY
        toggleRow.spacing = 8

        let stack = NSStackView(views: [
            Controls.formRow("Pitch", pitchRow, help: "How high or low the sound plays.", labelWidth: 96),
            Controls.formRow("Speed", speedRow, help: "How fast the sound plays.", labelWidth: 96),
            Controls.formRow("Keep from", trimRow, help: "Which part of the file plays.", labelWidth: 96),
            Controls.formRow("Sound", toggleRow, help: "Two quick changes you can switch on and off.", labelWidth: 96)
        ])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 10
        stack.translatesAutoresizingMaskIntoConstraints = false

        shapeCard.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: shapeCard.leadingAnchor, constant: 12),
            stack.trailingAnchor.constraint(lessThanOrEqualTo: shapeCard.trailingAnchor, constant: -12),
            stack.topAnchor.constraint(equalTo: shapeCard.topAnchor, constant: 12),
            stack.bottomAnchor.constraint(equalTo: shapeCard.bottomAnchor, constant: -12)
        ])
        shapeCard.setAccessibilityRole(.group)
        shapeCard.setAccessibilityLabel("Reshape the sound")
        scaffold.addRow(shapeCard)
    }

    // MARK: EditorCanvas

    func refresh() {
        guard let host, let track = host.selectedTrack else {
            scaffold.titleLabel.stringValue = "Sample"
            scaffold.subtitleLabel.stringValue = WorkView.sample.explanation
            scaffold.showEmpty(noTrackState)
            return
        }

        scaffold.titleLabel.stringValue = "Sample: \(track.name)"

        let declaredFile = (track.file ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        guard !declaredFile.isEmpty else {
            noAudioState.update(
                title: "\(track.name) has no sound file",
                body: "\(Glossary.long("Sample")) Put audio on this track in the \(WorkView.playlist.label) view, then come back here to reshape it."
            )
            scaffold.showEmpty(noAudioState)
            return
        }

        scaffold.showEmpty(nil)

        let edit = normalizeSampleEdit(track.sampleEdit)
        let url = host.store.existingAudioURL(for: track)
        let data = syncWaveform(track: track, url: url, edit: edit)

        // File card
        let displayName = url?.lastPathComponent ?? URL(fileURLWithPath: declaredFile).lastPathComponent
        fileNameLabel.stringValue = displayName
        fileNameLabel.toolTip = url?.path ?? declaredFile
        revealButton.isEnabled = url != nil
        locateButton.isHidden = url != nil

        if let audioURL = url {
            if let data, data.isUsable {
                fileProblemLabel.isHidden = true
                fileSpecLabel.stringValue = String(
                    format: "%@ · %.1f kHz · %@",
                    neonTimeText(data.duration),
                    data.sampleRate / 1000,
                    data.channelCount >= 2 ? "stereo" : "mono"
                )
            } else if WaveformStore.shared.cached(audioURL) != nil {
                fileProblemLabel.isHidden = false
                fileProblemLabel.stringValue = "This file could not be read as audio."
                fileSpecLabel.stringValue = ""
            } else {
                fileProblemLabel.isHidden = true
                fileSpecLabel.stringValue = "Reading the sound file…"
            }
        } else {
            fileProblemLabel.isHidden = false
            fileProblemLabel.stringValue = "This file is not where the project expects it: \(declaredFile)"
            fileSpecLabel.stringValue = "Nothing to play until the file is found."
        }
        fileProblemLabel.toolTip = fileProblemLabel.stringValue
        fileSpecLabel.toolTip = fileSpecLabel.stringValue

        // Shape controls
        let pitch = edit.pitchSemitones ?? 0
        let clampedPitch = max(-24, min(24, pitch))
        if abs(pitchSlider.doubleValue - clampedPitch) > 0.001 { pitchSlider.doubleValue = clampedPitch }
        if abs(pitchStepper.doubleValue - clampedPitch) > 0.001 { pitchStepper.doubleValue = clampedPitch }
        pitchLabel.stringValue = pitchDescription(clampedPitch)

        let speed = max(0.25, min(4, edit.stretch ?? 1))
        if abs(speedSlider.doubleValue - speed) > 0.001 { speedSlider.doubleValue = speed }
        speedLabel.stringValue = speedDescription(speed)

        normalizeToggle.state = (edit.normalize ?? false) ? .on : .off
        reverseToggle.state = (edit.reverse ?? false) ? .on : .off

        updateTrimReadouts(start: edit.trimStart ?? 0, end: edit.trimEnd)
        let trimmed = (edit.trimStart ?? 0) > 0.0005 || edit.trimEnd != nil
        resetTrimButton.isEnabled = trimmed

        if trimmed {
            let fileLength = (data?.isUsable == true) ? data?.duration ?? 0 : 0
            let endText = edit.trimEnd.map { "\(neonShortTimeText($0))s" } ?? "the end"
            let ofLength = fileLength > 0 ? " of \(neonTimeText(fileLength))" : ""
            scaffold.subtitleLabel.stringValue =
                "Playing \(neonShortTimeText(edit.trimStart ?? 0))s to \(endText)\(ofLength)."
        } else {
            scaffold.subtitleLabel.stringValue = WorkView.sample.explanation
        }
    }

    /// This panel scrolls its own content, so it always fits the space it is given.
    func contentSize(fittingVisible visible: NSSize) -> NSSize { visible }

    // MARK: Waveform plumbing

    private func syncWaveform(track: Track, url: URL?, edit: SampleEdit) -> WaveformData? {
        waveform.waveColor = neonColor(from: track.color, fallback: Theme.defaultTrackColor)
        waveform.trimStart = max(0, edit.trimStart ?? 0)
        waveform.trimEnd = edit.trimEnd

        guard let url else {
            waveform.peaks = []
            waveform.duration = 0
            waveform.isEnabled = false
            waveform.message = "The sound file is missing, so there is nothing to draw."
            pendingWaveformKey = nil
            return nil
        }

        if let data = WaveformStore.shared.cached(url) {
            pendingWaveformKey = nil
            if data.isUsable {
                waveform.peaks = data.peaks
                waveform.duration = data.duration
                waveform.isEnabled = true
                waveform.message = nil
                return data
            }
            waveform.peaks = []
            waveform.duration = 0
            waveform.isEnabled = false
            waveform.message = "\(url.lastPathComponent) could not be read as audio."
            return nil
        }

        waveform.peaks = []
        waveform.duration = 0
        waveform.isEnabled = false
        waveform.message = "Reading \(url.lastPathComponent)…"
        let path = url.path
        pendingWaveformKey = path
        WaveformStore.shared.load(url) { [weak self] _ in
            guard let self, self.pendingWaveformKey == path else { return }
            self.pendingWaveformKey = nil
            // The data is cached now, so this pass takes the cached branch.
            self.refresh()
        }
        return nil
    }

    private func updateTrimReadouts(start: Double, end: Double?) {
        if window?.firstResponder !== trimStartField.currentEditor() {
            trimStartField.stringValue = neonShortTimeText(start)
        }
        if window?.firstResponder !== trimEndField.currentEditor() {
            trimEndField.stringValue = end.map { neonShortTimeText($0) } ?? ""
        }
    }

    // MARK: Edits

    private func mutateSample(_ actionName: String, _ body: (inout SampleEdit) -> Void) {
        guard let host, let track = host.selectedTrack else { return }
        let trackId = track.id
        host.edit(actionName) { project in
            guard let index = project.snapshot.tracks.firstIndex(where: { $0.id == trackId }) else { return }
            var edit = normalizeSampleEdit(project.snapshot.tracks[index].sampleEdit)
            body(&edit)
            // Re-normalised so trim start / end, pitch and speed stay inside the
            // ranges every other part of the app relies on.
            project.snapshot.tracks[index].sampleEdit = normalizeSampleEdit(edit)
        }
    }

    private func handlePitch(_ value: Double, commit: Bool) {
        let semitones = max(-24, min(24, value.rounded()))
        pitchLabel.stringValue = pitchDescription(semitones)
        if abs(pitchStepper.doubleValue - semitones) > 0.001 { pitchStepper.doubleValue = semitones }
        if abs(pitchSlider.doubleValue - semitones) > 0.5 { pitchSlider.doubleValue = semitones }
        guard commit else { return }
        mutateSample("Change Pitch") { $0.pitchSemitones = semitones }
        StatusCenter.shared.info(
            "Pitch set to \(pitchDescription(semitones)).",
            detail: "Press Command-Z to undo."
        )
    }

    private func handleSpeed(_ value: Double, commit: Bool) {
        let speed = max(0.25, min(4, value))
        speedLabel.stringValue = speedDescription(speed)
        guard commit else { return }
        mutateSample("Change Speed") { $0.stretch = speed }
        StatusCenter.shared.info(
            "Speed set to \(speedDescription(speed)).",
            detail: "Press Command-Z to undo."
        )
    }

    private func setNormalize(_ isOn: Bool) {
        mutateSample(isOn ? "Turn On Even Out Volume" : "Turn Off Even Out Volume") { $0.normalize = isOn }
        StatusCenter.shared.success(
            isOn ? "This sample will play at a steady loudness." : "The sample keeps its original loudness.",
            detail: "Press Command-Z to undo."
        )
    }

    private func setReverse(_ isOn: Bool) {
        mutateSample(isOn ? "Turn On Play Backwards" : "Turn Off Play Backwards") { $0.reverse = isOn }
        StatusCenter.shared.success(
            isOn ? "This sample will play backwards." : "This sample will play forwards.",
            detail: "Press Command-Z to undo."
        )
    }

    private func commitTrim(start: Double, end: Double?) {
        mutateSample("Trim Sample") { edit in
            edit.trimStart = max(0, start)
            edit.trimEnd = end
        }
        if start <= 0.0005 && end == nil {
            StatusCenter.shared.success("The whole sound file plays again.", detail: "Press Command-Z to undo.")
        } else {
            let endText = end.map { "\(neonShortTimeText($0))s" } ?? "the end"
            StatusCenter.shared.success(
                "Playing from \(neonShortTimeText(start))s to \(endText).",
                detail: "Press Command-Z to undo."
            )
        }
    }

    private func commitTrimStartText(_ text: String) {
        guard let host, let track = host.selectedTrack else { return }
        let edit = normalizeSampleEdit(track.sampleEdit)
        let trimmed = text.trimmingCharacters(in: .whitespaces)
        guard let value = Double(trimmed), value >= 0 else {
            StatusCenter.shared.warning(
                "That trim start isn't a number of seconds.",
                detail: "Type something like 0.75."
            )
            updateTrimReadouts(start: edit.trimStart ?? 0, end: edit.trimEnd)
            return
        }
        commitTrim(start: value, end: edit.trimEnd)
    }

    private func commitTrimEndText(_ text: String) {
        guard let host, let track = host.selectedTrack else { return }
        let edit = normalizeSampleEdit(track.sampleEdit)
        let trimmed = text.trimmingCharacters(in: .whitespaces)
        if trimmed.isEmpty {
            commitTrim(start: edit.trimStart ?? 0, end: nil)
            return
        }
        guard let value = Double(trimmed), value >= 0 else {
            StatusCenter.shared.warning(
                "That trim end isn't a number of seconds.",
                detail: "Type something like 3.5, or leave it empty to play to the end."
            )
            updateTrimReadouts(start: edit.trimStart ?? 0, end: edit.trimEnd)
            return
        }
        commitTrim(start: edit.trimStart ?? 0, end: value)
    }

    // MARK: File actions

    private func revealInFinder() {
        guard let host, let track = host.selectedTrack,
              let url = host.store.existingAudioURL(for: track) else {
            StatusCenter.shared.warning(
                "There is no sound file to show yet.",
                detail: "Use Locate File to point this track at an audio file."
            )
            return
        }
        NSWorkspace.shared.activateFileViewerSelecting([url])
    }

    private func locateFile() {
        guard let host, let track = host.selectedTrack else { return }
        let panel = NSOpenPanel()
        panel.title = "Choose a sound file for \(track.name)"
        panel.message = "Pick the audio file this track should play."
        panel.prompt = "Use This File"
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        panel.allowedContentTypes = [.audio]

        let finish: (NSApplication.ModalResponse) -> Void = { [weak self] response in
            guard let self, response == .OK, let url = panel.url else { return }
            self.relink(track: track, to: url)
        }

        if let window {
            panel.beginSheetModal(for: window, completionHandler: finish)
        } else {
            finish(panel.runModal())
        }
    }

    private func relink(track: Track, to url: URL) {
        guard let host else { return }
        let trackId = track.id
        let path = url.path
        host.edit("Relink Audio File") { project in
            guard let index = project.snapshot.tracks.firstIndex(where: { $0.id == trackId }) else { return }
            project.snapshot.tracks[index].file = path
        }
        StatusCenter.shared.success(
            "\(track.name) now plays \(url.lastPathComponent).",
            detail: "Press Command-Z to undo."
        )
    }

    // MARK: Wording

    private func pitchDescription(_ semitones: Double) -> String {
        let value = Int(semitones.rounded())
        if value == 0 { return "0 — as recorded" }
        let steps = abs(value) == 1 ? "1 step" : "\(abs(value)) steps"
        return value > 0 ? "+\(value) — \(steps) higher" : "\(value) — \(steps) lower"
    }

    private func speedDescription(_ speed: Double) -> String {
        let percent = Int((speed * 100).rounded())
        if percent == 100 { return "100% — as recorded" }
        return percent > 100 ? "\(percent)% — faster" : "\(percent)% — slower"
    }
}

// MARK: - Recipe

/// One production step. The checkbox marks it done; clicking anywhere else
/// selects the track the step is about.
private final class RecipeRowView: NeonCardView {
    let itemId: String

    private let checkbox = CheckboxControl(frame: .zero)
    private let statusDot = NSImageView()
    private let labelField = makeLabel("", font: Theme.Font.emphasis(13), color: Theme.text)
    private let detailField = makeLabel("", font: Theme.Font.body(12), color: Theme.muted)
    private let tracksField = makeLabel("", font: Theme.Font.caption(11), color: Theme.dim)
    private var selectButton: NSButton!
    private var canSelectTrack = false

    var onToggle: ((Bool) -> Void)?
    var onSelect: (() -> Void)?

    init(item: RecipeItem) {
        itemId = item.id
        super.init(frame: .zero)
        translatesAutoresizingMaskIntoConstraints = false

        checkbox.handler = { [weak self] isOn in self?.onToggle?(isOn) }

        statusDot.image = NSImage(systemSymbolName: "circle.fill", accessibilityDescription: nil)
        statusDot.symbolConfiguration = NSImage.SymbolConfiguration(pointSize: 9, weight: .bold)
        statusDot.translatesAutoresizingMaskIntoConstraints = false
        statusDot.setAccessibilityRole(.image)

        selectButton = Controls.button(
            title: "",
            symbol: "arrow.right.circle",
            help: "Select the track this step is about.",
            style: .quiet
        ) { [weak self] in self?.onSelect?() }

        let textStack = NSStackView(views: [labelField, detailField, tracksField])
        textStack.orientation = .vertical
        textStack.alignment = .leading
        textStack.spacing = 2
        textStack.translatesAutoresizingMaskIntoConstraints = false
        textStack.setContentHuggingPriority(.defaultLow, for: .horizontal)
        textStack.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)

        let row = NSStackView(views: [checkbox, statusDot, textStack, selectButton])
        row.orientation = .horizontal
        row.alignment = .centerY
        row.spacing = 10
        row.translatesAutoresizingMaskIntoConstraints = false
        addSubview(row)

        NSLayoutConstraint.activate([
            row.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 12),
            row.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -10),
            row.topAnchor.constraint(equalTo: topAnchor, constant: 9),
            row.bottomAnchor.constraint(equalTo: bottomAnchor, constant: -9),
            heightAnchor.constraint(greaterThanOrEqualToConstant: Theme.Metric.minimumHitTarget * 2)
        ])

        setAccessibilityRole(.group)
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    func update(item: RecipeItem, trackNames: [String]) {
        let isDone = item.isDone
        canSelectTrack = !trackNames.isEmpty

        checkbox.state = isDone ? .on : .off
        checkbox.toolTip = isDone
            ? "This step is marked done. Click to mark it as still to do."
            : "Mark this step done once you have made the change."
        checkbox.setAccessibilityLabel("\(item.label) done")
        checkbox.setAccessibilityHelp(checkbox.toolTip)

        statusDot.contentTintColor = isDone ? Theme.success : Theme.warning
        statusDot.toolTip = isDone ? "Done" : "Not done yet"
        statusDot.setAccessibilityLabel(isDone ? "Done" : "Not done yet")

        labelField.stringValue = item.label
        labelField.toolTip = item.label

        let detail = (item.detail ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        detailField.stringValue = detail
        detailField.toolTip = detail
        detailField.isHidden = detail.isEmpty

        if trackNames.isEmpty {
            tracksField.stringValue = "No track linked to this step"
        } else {
            tracksField.stringValue = "Tracks: " + trackNames.joined(separator: ", ")
        }
        tracksField.toolTip = tracksField.stringValue

        selectButton.isHidden = trackNames.isEmpty
        if let first = trackNames.first {
            selectButton.toolTip = "Select \(first) in the track list."
            selectButton.setAccessibilityLabel("Select \(first)")
        }

        toolTip = detail.isEmpty ? item.label : "\(item.label) — \(detail)"
        setAccessibilityLabel("\(item.label), \(isDone ? "done" : "not done yet")")
        setAccessibilityHelp(toolTip)
        needsDisplay = true
    }

    override func mouseDown(with event: NSEvent) {
        guard canSelectTrack else {
            super.mouseDown(with: event)
            return
        }
        onSelect?()
    }

    override func resetCursorRects() {
        super.resetCursorRects()
        guard canSelectTrack else { return }
        addCursorRect(bounds, cursor: .pointingHand)
    }

    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        for area in trackingAreas { removeTrackingArea(area) }
        addTrackingArea(NSTrackingArea(
            rect: .zero,
            options: [.mouseEnteredAndExited, .activeInKeyWindow, .inVisibleRect],
            owner: self,
            userInfo: nil
        ))
    }

    override func mouseEntered(with event: NSEvent) {
        if canSelectTrack { isHovering = true }
    }

    override func mouseExited(with event: NSEvent) {
        isHovering = false
    }

    override func menu(for event: NSEvent) -> NSMenu? {
        let menu = NSMenu(title: labelField.stringValue)
        let isDone = checkbox.state == .on
        let toggleItem = NSMenuItem(
            title: isDone ? "Mark Step Not Done" : "Mark Step Done",
            action: #selector(menuToggle),
            keyEquivalent: ""
        )
        toggleItem.target = self
        menu.addItem(toggleItem)
        if canSelectTrack {
            menu.addItem(NSMenuItem.separator())
            let selectItem = NSMenuItem(title: "Select the Track", action: #selector(menuSelect), keyEquivalent: "")
            selectItem.target = self
            menu.addItem(selectItem)
        }
        return menu
    }

    @objc private func menuToggle() {
        let next = checkbox.state != .on
        checkbox.state = next ? .on : .off
        onToggle?(next)
    }

    @objc private func menuSelect() {
        onSelect?()
    }
}

/// The Recipe panel: every production step, grouped by the section it belongs
/// to, with an honest count of how many are actually done.
final class RecipeView: NSView, EditorCanvas {

    weak var host: EditorHost? {
        didSet { refresh() }
    }

    private var scaffold: NeonPaneScaffold!
    private let countLabel = makeLabel("", font: Theme.Font.mono(11), color: Theme.muted)
    private let progress = NSProgressIndicator()
    private var rows: [RecipeRowView] = []
    private var renderedKey: [String] = []

    private lazy var emptyState = EmptyStateView(
        symbol: "checklist",
        title: "No recipe for this song yet",
        body: "\(Glossary.long("Recipe")) This project doesn't have one — you can still build the song by hand in the \(WorkView.playlist.label) view.",
        actionTitle: "Go to \(WorkView.playlist.label)",
        action: { [weak self] in self?.host?.requestFocus(on: .playlist) }
    )

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        setup()
    }

    convenience init() {
        self.init(frame: .zero)
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    private func setup() {
        translatesAutoresizingMaskIntoConstraints = false
        wantsLayer = true

        scaffold = NeonPaneScaffold(
            owner: self,
            title: "Recipe",
            subtitle: WorkView.recipe.explanation
        )

        progress.style = .bar
        progress.isIndeterminate = false
        progress.controlSize = .small
        progress.minValue = 0
        progress.maxValue = 1
        progress.doubleValue = 0
        progress.translatesAutoresizingMaskIntoConstraints = false
        progress.widthAnchor.constraint(equalToConstant: 150).isActive = true

        scaffold.addAccessory(countLabel)
        scaffold.addAccessory(progress)
        scaffold.addAccessory(Controls.glossary("Recipe", Glossary.long("Recipe")))

        setAccessibilityRole(.group)
        setAccessibilityLabel("Recipe")
        setAccessibilityHelp(WorkView.recipe.explanation)
        toolTip = WorkView.recipe.explanation
    }

    // MARK: EditorCanvas

    func refresh() {
        let items = host?.project.snapshot.recipe ?? []
        guard !items.isEmpty else {
            rows = []
            renderedKey = []
            scaffold.clearRows()
            countLabel.stringValue = ""
            progress.doubleValue = 0
            progress.isHidden = true
            countLabel.isHidden = true
            scaffold.showEmpty(emptyState)
            return
        }

        countLabel.isHidden = false
        progress.isHidden = false
        scaffold.showEmpty(nil)

        let done = items.filter(\.isDone).count
        let fraction = Double(done) / Double(items.count)
        countLabel.stringValue = "\(done) of \(items.count) steps done"
        countLabel.toolTip = "\(done) of the \(items.count) steps in this recipe are marked done."
        progress.doubleValue = fraction
        progress.toolTip = countLabel.toolTip
        progress.setAccessibilityLabel("Recipe progress: \(done) of \(items.count) steps done")
        scaffold.subtitleLabel.stringValue = done == items.count
            ? "Every step is done."
            : "\(items.count - done) still to do. Tick a step off when you have made the change."

        // Rebuild only when the list itself changed, so ticking a box keeps
        // keyboard focus and the scroll position where they were.
        let key = RecipeView.key(for: items)
        if key != renderedKey {
            rebuild(items: items)
        }
        // Rows are grouped by section, so they are matched to items by id rather
        // than by position.
        var byId: [String: RecipeItem] = [:]
        for item in items where byId[item.id] == nil { byId[item.id] = item }
        for row in rows {
            guard let item = byId[row.itemId] else { continue }
            row.update(item: item, trackNames: trackNames(for: item))
        }
    }

    private static func key(for items: [RecipeItem]) -> [String] {
        items.map { "\($0.id)|\($0.section ?? "")" }
    }

    /// This panel scrolls its own content, so it always fits the space it is given.
    func contentSize(fittingVisible visible: NSSize) -> NSSize { visible }

    // MARK: Building

    private func rebuild(items: [RecipeItem]) {
        scaffold.clearRows()
        rows = []

        // Sections in first-appearance order — nothing is hardcoded, so a
        // section the tools invent still shows up.
        var sectionOrder: [String] = []
        var grouped: [String: [RecipeItem]] = [:]
        for item in items {
            let section = (item.section ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let name = section.isEmpty ? "Steps" : section
            if grouped[name] == nil {
                grouped[name] = []
                sectionOrder.append(name)
            }
            grouped[name]?.append(item)
        }

        for section in sectionOrder {
            let header = makeLabel(section.uppercased(), font: Theme.Font.captionBold(11), color: Theme.muted)
            header.toolTip = "Steps for \(section)."
            scaffold.addRow(header)
            for item in grouped[section] ?? [] {
                let row = RecipeRowView(item: item)
                let id = item.id
                row.onToggle = { [weak self] isDone in self?.setDone(isDone, id: id) }
                row.onSelect = { [weak self] in self?.selectTrack(for: id) }
                scaffold.addRow(row)
                rows.append(row)
            }
        }

        renderedKey = RecipeView.key(for: items)
    }

    private func trackNames(for item: RecipeItem) -> [String] {
        guard let project = host?.project else { return [] }
        return (item.trackIds ?? []).compactMap { project.track(id: $0)?.name }
    }

    // MARK: Actions

    private func setDone(_ isDone: Bool, id: String) {
        guard let host else { return }
        let label = host.project.snapshot.recipe?.first(where: { $0.id == id })?.label ?? "this step"
        host.edit(isDone ? "Mark Step Done" : "Mark Step Not Done") { project in
            guard var recipe = project.snapshot.recipe,
                  let index = recipe.firstIndex(where: { $0.id == id }) else { return }
            recipe[index].status = isDone ? RecipeItem.doneStatus : RecipeItem.notDoneStatus
            project.snapshot.recipe = recipe
        }
        StatusCenter.shared.success(
            isDone ? "Marked \(label) done." : "Marked \(label) as still to do.",
            detail: "Press Command-Z to undo."
        )
    }

    private func selectTrack(for id: String) {
        guard let host,
              let item = host.project.snapshot.recipe?.first(where: { $0.id == id }),
              let trackId = (item.trackIds ?? []).first(where: { host.project.track(id: $0) != nil }),
              let track = host.project.track(id: trackId) else { return }
        host.selectTrack(trackId)
        StatusCenter.shared.info("Selected \(track.name).", detail: "This step is about that track.")
    }
}

// MARK: - Private drawing helper

private extension NSRect {
    func fill(with color: NSColor) {
        roundedFill(self, radius: 2, color: color)
    }
}
