import AppKit
import NeonStudioKit

/// The mixing desk: one channel strip per track, plus a master strip at the right.
///
/// The previous mixer drew every fader, button and send by hand and hit-tested
/// them against y-thresholds that no longer matched what had been drawn, so
/// solo, arm and the sends were visible but impossible to change, and "pan"
/// cycled through three magic values instead of being a control you could drag.
///
/// Everything here is a real AppKit control inside a real strip view, so drag,
/// hover, keyboard focus, and VoiceOver all work for free and there is no
/// draw/hit geometry to drift apart. The only custom drawing is the level
/// meters, which are canvases, not controls.
public final class MixerConsoleView: NSView, EditorCanvas {

    // MARK: Host

    public weak var host: EditorHost? {
        didSet { refresh() }
    }

    // MARK: Metrics
    //
    // One place for the strip geometry, shared by layout and `contentSize`, so
    // the scroll view can never disagree with what is actually on screen.

    fileprivate enum Layout {
        static let stripWidth: CGFloat = 132
        static let masterWidth: CGFloat = 152
        static let stripSpacing: CGFloat = 8
        static let edgePadding: CGFloat = 12
        static let minimumHeight: CGFloat = 380
    }

    // MARK: Views

    private let stripStack = NSStackView()
    private let masterStrip = MasterStrip()
    private let divider = Controls.separator(vertical: true)
    private lazy var emptyState = EmptyStateView(
        symbol: "slider.vertical.3",
        title: "No tracks to mix yet",
        body: "A mix is the balance between tracks, so there has to be a track first. "
            + "Add one in Arrange and it will show up here as its own strip.",
        actionTitle: "Go to Arrange",
        action: { [weak self] in
            self?.host?.requestFocus(on: .playlist)
        }
    )

    private var strips: [ChannelStrip] = []
    /// The track identity the current strips were built from. Values update in
    /// place on every refresh; the strips are only torn down and rebuilt when
    /// this changes, so typing a track name cannot pull the field out from
    /// under the insertion point.
    private var builtTrackIds: [String] = []
    private var masterLevel: CGFloat = 0
    /// Peaks measured per track by the engine, keyed by track id.
    private var trackLevels: [String: Float] = [:]

    // MARK: Init

    public override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        setUp()
    }

    public convenience init() {
        self.init(frame: NSRect(x: 0, y: 0, width: 720, height: Layout.minimumHeight))
    }

    public required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    private func setUp() {
        wantsLayer = true
        translatesAutoresizingMaskIntoConstraints = false

        setAccessibilityRole(.group)
        setAccessibilityLabel("Mixer")
        setAccessibilityHelp(AppEnvironment.shared.help(
            "One strip per track. Set how loud each track is and where it sits between the speakers.",
            term: "Mix"
        ))

        stripStack.orientation = .horizontal
        stripStack.alignment = .top
        stripStack.spacing = Layout.stripSpacing
        stripStack.distribution = .fill
        stripStack.translatesAutoresizingMaskIntoConstraints = false
        stripStack.setAccessibilityRole(.group)
        stripStack.setAccessibilityLabel("Track strips")

        addSubview(stripStack)
        addSubview(divider)
        addSubview(masterStrip)
        addSubview(emptyState)

        let stackTrailing = stripStack.trailingAnchor.constraint(
            lessThanOrEqualTo: divider.leadingAnchor,
            constant: -Layout.stripSpacing
        )
        stackTrailing.priority = .defaultLow

        NSLayoutConstraint.activate([
            stripStack.leadingAnchor.constraint(equalTo: leadingAnchor, constant: Layout.edgePadding),
            stripStack.topAnchor.constraint(equalTo: topAnchor, constant: Layout.edgePadding),
            stripStack.bottomAnchor.constraint(equalTo: bottomAnchor, constant: -Layout.edgePadding),
            stackTrailing,

            masterStrip.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -Layout.edgePadding),
            masterStrip.topAnchor.constraint(equalTo: topAnchor, constant: Layout.edgePadding),
            masterStrip.bottomAnchor.constraint(equalTo: bottomAnchor, constant: -Layout.edgePadding),
            masterStrip.widthAnchor.constraint(equalToConstant: Layout.masterWidth),

            divider.trailingAnchor.constraint(equalTo: masterStrip.leadingAnchor, constant: -Layout.stripSpacing),
            divider.topAnchor.constraint(equalTo: topAnchor, constant: Layout.edgePadding),
            divider.bottomAnchor.constraint(equalTo: bottomAnchor, constant: -Layout.edgePadding),

            emptyState.leadingAnchor.constraint(equalTo: leadingAnchor),
            emptyState.trailingAnchor.constraint(equalTo: trailingAnchor),
            emptyState.topAnchor.constraint(equalTo: topAnchor),
            emptyState.bottomAnchor.constraint(equalTo: bottomAnchor)
        ])

        masterStrip.onClearSolos = { [weak self] in self?.clearAllSolos() }
        refreshColors()
    }

    public override func viewDidChangeEffectiveAppearance() {
        super.viewDidChangeEffectiveAppearance()
        refreshColors()
    }

    private func refreshColors() {
        effectiveAppearance.performAsCurrentDrawingAppearance { [weak self] in
            self?.layer?.backgroundColor = Theme.app.cgColor
        }
    }

    /// Flipped so the strips hang from the top. In an unflipped document view
    /// a console taller than its scroll view anchors to the bottom, which hid
    /// the track names and the M/S/R buttons behind the tab bar.
    public override var isFlipped: Bool { true }

    // MARK: EditorCanvas

    public func refresh() {
        guard let host else {
            teardownStrips()
            showEmptyState(true)
            return
        }
        let project = host.project
        let tracks = project.snapshot.tracks

        showEmptyState(tracks.isEmpty)
        emptyState.isActionEnabled = true

        let ids = tracks.map(\.id)
        if ids != builtTrackIds {
            rebuildStrips(for: tracks)
        }

        for (index, track) in tracks.enumerated() where index < strips.count {
            strips[index].update(
                index: index,
                track: track,
                control: project.control(for: track.id),
                isSelected: track.id == host.selectedTrackId,
                isAudible: project.isAudible(track.id),
                someTrackIsSoloed: project.anyTrackSoloed
            )
        }

        let audible = tracks.filter { project.isAudible($0.id) }.count
        masterStrip.update(
            audibleCount: audible,
            totalCount: tracks.count,
            soloActive: project.anyTrackSoloed
        )
        applyMeterLevels()
    }

    public func playheadDidMove(to bar: Double) {
        // Nothing on the desk is bar-dependent; the meters are level-driven.
    }

    public func contentSize(fittingVisible visible: NSSize) -> NSSize {
        let count = CGFloat(max(strips.count, 0))
        let stripsWidth = count * Layout.stripWidth + max(0, count - 1) * Layout.stripSpacing
        let needed = Layout.edgePadding * 2
            + stripsWidth
            + (count > 0 ? Layout.stripSpacing * 2 + 1 : 0)
            + Layout.masterWidth
        return NSSize(
            width: max(visible.width, needed),
            height: max(visible.height, Layout.minimumHeight)
        )
    }

    // MARK: Metering

    /// The engine taps every track's own mixer node, so these are real per-track
    /// peaks measured after that track's gain, pan, mute and solo — a muted
    /// track reads zero and a quiet part reads quiet. Earlier this showed the
    /// master level scaled by each fader, which moved every meter in lockstep
    /// and told you nothing about the individual track.
    public func updateMasterLevel(_ level: Float) {
        let clamped = CGFloat(max(0, min(1, level)))
        guard abs(clamped - masterLevel) > 0.002 else { return }
        masterLevel = clamped
        applyMeterLevels()
    }

    /// Real per-track peaks, measured at each track's own mixer node.
    public func updateTrackLevels(_ levels: [String: Float]) {
        trackLevels = levels
        applyMeterLevels()
    }

    private func applyMeterLevels() {
        let playing = host?.isPlaying ?? false
        for strip in strips {
            let measured = trackLevels[strip.trackId].map { CGFloat($0) }
            strip.updateMeter(measured: measured, isPlaying: playing)
        }
        masterStrip.setLevel(playing ? masterLevel : 0, isPlaying: playing)
    }

    // MARK: Strip construction

    private func showEmptyState(_ show: Bool) {
        emptyState.isHidden = !show
        stripStack.isHidden = show
        divider.isHidden = show
        masterStrip.isHidden = show
    }

    private func teardownStrips() {
        for strip in strips {
            stripStack.removeArrangedSubview(strip)
            strip.removeFromSuperview()
        }
        strips.removeAll()
        builtTrackIds = []
    }

    private func rebuildStrips(for tracks: [Track]) {
        teardownStrips()
        for track in tracks {
            let strip = ChannelStrip(trackId: track.id)
            strip.host = host
            strip.onSelect = { [weak self] id in self?.host?.selectTrack(id) }
            stripStack.addArrangedSubview(strip)
            NSLayoutConstraint.activate([
                strip.widthAnchor.constraint(equalToConstant: Layout.stripWidth),
                strip.heightAnchor.constraint(equalTo: stripStack.heightAnchor)
            ])
            strips.append(strip)
        }
        builtTrackIds = tracks.map(\.id)
        invalidateIntrinsicContentSize()
    }

    // MARK: Actions

    private func clearAllSolos() {
        guard let host, host.project.anyTrackSoloed else { return }
        host.edit("Clear Solos") { project in
            var controls = project.snapshot.controls ?? [:]
            for key in controls.keys {
                controls[key]?.solo = false
            }
            project.snapshot.controls = controls
        }
        StatusCenter.shared.success("Cleared every solo — all tracks can be heard again. ⌘Z undoes it.")
    }

    private func unmuteAll() {
        guard let host else { return }
        let muted = (host.project.snapshot.controls ?? [:]).values.filter(\.mute).count
        guard muted > 0 else {
            StatusCenter.shared.info("Nothing is muted.")
            return
        }
        host.edit("Unmute All Tracks") { project in
            var controls = project.snapshot.controls ?? [:]
            for key in controls.keys {
                controls[key]?.mute = false
            }
            project.snapshot.controls = controls
        }
        StatusCenter.shared.success("Unmuted \(muted) track\(muted == 1 ? "" : "s"). ⌘Z undoes it.")
    }

    private func resetStrip(_ strip: ChannelStrip) {
        guard let host, let track = host.project.track(id: strip.trackId) else { return }
        let id = strip.trackId
        host.edit("Reset Track Mix") { project in
            var controls = project.snapshot.controls ?? [:]
            var control = controls[id] ?? MixerControl.neutral
            control.gain = MixerControl.neutral.gain
            control.pan = 0
            control.sendA = MixerControl.neutral.sendA
            control.sendB = MixerControl.neutral.sendB
            controls[id] = control
            project.snapshot.controls = controls
        }
        StatusCenter.shared.success("Reset the mix settings for \(track.name). ⌘Z undoes it.")
    }

    // MARK: Right-click

    public override func menu(for event: NSEvent) -> NSMenu? {
        let point = convert(event.locationInWindow, from: nil)
        let menu = NSMenu(title: "Mixer")
        menu.autoenablesItems = false

        if let strip = strip(at: point), let track = host?.project.track(id: strip.trackId) {
            menu.addItem(ClosureMenuItem(title: "Select “\(track.name)”") { [weak self] in
                self?.host?.selectTrack(strip.trackId)
            })
            menu.addItem(ClosureMenuItem(title: "Reset “\(track.name)” Volume, Pan and Sends") { [weak self] in
                self?.resetStrip(strip)
            })
            menu.addItem(NSMenuItem.separator())
        }

        let clear = ClosureMenuItem(title: "Clear All Solos") { [weak self] in self?.clearAllSolos() }
        clear.isEnabled = host?.project.anyTrackSoloed == true
        menu.addItem(clear)

        let unmute = ClosureMenuItem(title: "Unmute All Tracks") { [weak self] in self?.unmuteAll() }
        unmute.isEnabled = (host?.project.snapshot.controls ?? [:]).values.contains(where: \.mute)
        menu.addItem(unmute)

        menu.addItem(NSMenuItem.separator())
        menu.addItem(ClosureMenuItem(title: "Go to Arrange") { [weak self] in
            self?.host?.requestFocus(on: .playlist)
        })
        return menu
    }

    private func strip(at point: NSPoint) -> ChannelStrip? {
        strips.first { $0.bounds.contains($0.convert(point, from: self)) }
    }
}

// MARK: - Channel strip

/// One track's controls. Every value here is a real control bound to
/// `project.snapshot.controls[trackId]`, which is the same dictionary the audio
/// engine mixes from, so moving a fader is audible immediately.
private final class ChannelStrip: NSView {

    let trackId: String
    weak var host: EditorHost?
    var onSelect: ((String) -> Void)?

    private var control = MixerControl.neutral
    private var isAudibleNow = true
    private var isSelected = false
    private var silencedBySolo = false
    private var trackName = ""

    // Header
    private let headerView = NSView()
    private let numberLabel = makeLabel("1", font: Theme.Font.mono(11, weight: .semibold), color: Theme.dim)
    private let nameField = CommitTextField(string: "")

    private let colorButton: NSButton
    private let muteButton: NSButton
    private let soloButton: NSButton
    private let armButton: NSButton

    private let volumeCaption = makeLabel("Volume", font: Theme.Font.caption(11), color: Theme.muted)
    private let faderRow = NSView()
    private let fader: NSSlider
    private let meter = LevelMeterView()
    private let gainReadout = makeLabel("0.0 dB", font: Theme.Font.mono(11), color: Theme.text)

    private let sendACaption = makeLabel("Send A", font: Theme.Font.caption(11), color: Theme.muted)
    private let sendAValue = makeLabel("0%", font: Theme.Font.mono(11), color: Theme.muted)
    private let sendASlider: NSSlider

    private let sendBCaption = makeLabel("Send B", font: Theme.Font.caption(11), color: Theme.muted)
    private let sendBValue = makeLabel("0%", font: Theme.Font.mono(11), color: Theme.muted)
    private let sendBSlider: NSSlider

    private let panCaption = makeLabel("Pan", font: Theme.Font.caption(11), color: Theme.muted)
    private let panValue = makeLabel("C", font: Theme.Font.mono(11), color: Theme.muted)
    private let panSlider: NSSlider

    private let stateLabel = makeLabel("", font: Theme.Font.caption(11), color: Theme.warning)

    private static let presetColors: [(name: String, hex: String)] = [
        ("Blue", "#4aa3ff"),
        ("Teal", "#2fd4c2"),
        ("Green", "#5ed07a"),
        ("Amber", "#f2b23c"),
        ("Coral", "#ff6f61"),
        ("Violet", "#a97bff")
    ]

    init(trackId: String) {
        self.trackId = trackId

        colorButton = Controls.button(
            title: "Colour",
            help: "Pick the colour this track uses in the arrangement.",
            style: .quiet,
            action: {}
        )
        // These stay `.standard` rather than `.quiet`: a rounded bezel is the
        // one style whose `bezelColor` reliably fills, and mute / solo / arm
        // have to be unmistakably on or off at a glance.
        muteButton = Controls.toggle(
            title: "M",
            help: AppEnvironment.shared.help("Silence this track without deleting anything.", term: "Mute"),
            style: .standard,
            action: { _ in }
        )
        soloButton = Controls.toggle(
            title: "S",
            help: AppEnvironment.shared.help("Hear only this track. Every other track goes quiet.", term: "Solo"),
            style: .standard,
            action: { _ in }
        )
        armButton = Controls.toggle(
            title: "R",
            help: AppEnvironment.shared.help("Ready this track to record onto.", term: "Arm"),
            style: .standard,
            action: { _ in }
        )
        fader = Controls.slider(
            value: MixerControl.neutral.gain,
            min: 0,
            max: 1.4,
            help: AppEnvironment.shared.help("Drag up and down to set how loud this track is.", term: "Gain"),
            accessibilityLabel: "Volume",
            vertical: true,
            action: { _ in }
        )
        sendASlider = Controls.slider(
            value: 0,
            min: 0,
            max: 1,
            help: AppEnvironment.shared.help("How much of this track is fed to the first shared effect.", term: "Send"),
            accessibilityLabel: "Send A",
            action: { _ in }
        )
        sendBSlider = Controls.slider(
            value: 0,
            min: 0,
            max: 1,
            help: AppEnvironment.shared.help("How much of this track is fed to the second shared effect.", term: "Send"),
            accessibilityLabel: "Send B",
            action: { _ in }
        )
        panSlider = Controls.slider(
            value: 0,
            min: -1,
            max: 1,
            help: AppEnvironment.shared.help("Slide left or right to move the sound between the speakers.", term: "Pan"),
            accessibilityLabel: "Pan",
            action: { _ in }
        )

        super.init(frame: .zero)
        translatesAutoresizingMaskIntoConstraints = false
        wantsLayer = true
        layer?.cornerRadius = Theme.Metric.cornerRadius
        layer?.borderWidth = 1

        setAccessibilityRole(.group)
        setAccessibilityLabel("Track")

        buildLayout()
        wireActions()
        refreshColors()
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    // MARK: Layout

    private func buildLayout() {
        headerView.translatesAutoresizingMaskIntoConstraints = false
        headerView.wantsLayer = true
        headerView.layer?.cornerRadius = Theme.Metric.smallCornerRadius

        numberLabel.alignment = .center
        numberLabel.setContentCompressionResistancePriority(.required, for: .horizontal)

        // Left bezeled on purpose: a borderless label-looking field gives no
        // clue it can be typed into, and renaming here has to be discoverable.
        nameField.font = Theme.Font.emphasis(12)
        nameField.controlSize = .small
        nameField.focusRingType = .default
        nameField.lineBreakMode = .byTruncatingTail
        nameField.toolTip = "The track's name. Press Return to rename it."
        nameField.setAccessibilityLabel("Track name")
        nameField.setAccessibilityHelp("Type a new name and press Return to rename this track.")
        nameField.translatesAutoresizingMaskIntoConstraints = false

        headerView.addSubview(numberLabel)
        headerView.addSubview(nameField)
        NSLayoutConstraint.activate([
            numberLabel.leadingAnchor.constraint(equalTo: headerView.leadingAnchor, constant: 6),
            numberLabel.centerYAnchor.constraint(equalTo: headerView.centerYAnchor),
            numberLabel.widthAnchor.constraint(equalToConstant: 16),
            nameField.leadingAnchor.constraint(equalTo: numberLabel.trailingAnchor, constant: 2),
            nameField.trailingAnchor.constraint(equalTo: headerView.trailingAnchor, constant: -4),
            nameField.centerYAnchor.constraint(equalTo: headerView.centerYAnchor),
            headerView.heightAnchor.constraint(equalToConstant: 30)
        ])

        colorButton.font = Theme.Font.caption(11)
        colorButton.imagePosition = .imageLeading

        let toggles = NSStackView(views: [muteButton, soloButton, armButton])
        toggles.orientation = .horizontal
        toggles.distribution = .fillEqually
        toggles.spacing = 4
        toggles.translatesAutoresizingMaskIntoConstraints = false
        for button in [muteButton, soloButton, armButton] {
            button.font = Theme.Font.captionBold(11)
            button.heightAnchor.constraint(equalToConstant: Theme.Metric.minimumHitTarget).isActive = true
        }

        // Volume: a real vertical fader with the meter beside it.
        faderRow.translatesAutoresizingMaskIntoConstraints = false
        faderRow.addSubview(fader)
        faderRow.addSubview(meter)
        let faderHeight = faderRow.heightAnchor.constraint(greaterThanOrEqualToConstant: 100)
        faderHeight.priority = .defaultHigh
        NSLayoutConstraint.activate([
            fader.topAnchor.constraint(equalTo: faderRow.topAnchor),
            fader.bottomAnchor.constraint(equalTo: faderRow.bottomAnchor),
            fader.centerXAnchor.constraint(equalTo: faderRow.centerXAnchor, constant: -14),
            meter.leadingAnchor.constraint(equalTo: fader.trailingAnchor, constant: 12),
            meter.widthAnchor.constraint(equalToConstant: 10),
            meter.topAnchor.constraint(equalTo: faderRow.topAnchor, constant: 3),
            meter.bottomAnchor.constraint(equalTo: faderRow.bottomAnchor, constant: -3),
            faderHeight
        ])
        faderRow.setContentHuggingPriority(NSLayoutConstraint.Priority(1), for: .vertical)
        faderRow.setContentCompressionResistancePriority(NSLayoutConstraint.Priority(240), for: .vertical)

        gainReadout.alignment = .center
        gainReadout.toolTip = AppEnvironment.shared.help(
            "This track's volume in decibels. 0 dB is unchanged; −∞ is silent.",
            term: "Gain"
        )
        gainReadout.setAccessibilityLabel("Volume in decibels")

        volumeCaption.alignment = .center

        let sendARow = Self.captionRow(sendACaption, sendAValue)
        let sendBRow = Self.captionRow(sendBCaption, sendBValue)
        let panRow = Self.captionRow(panCaption, panValue)

        stateLabel.alignment = .center
        stateLabel.maximumNumberOfLines = 2
        stateLabel.lineBreakMode = .byWordWrapping

        let content = NSStackView(views: [
            headerView,
            colorButton,
            toggles,
            volumeCaption,
            faderRow,
            gainReadout,
            sendARow,
            sendASlider,
            sendBRow,
            sendBSlider,
            panRow,
            panSlider,
            stateLabel
        ])
        content.orientation = .vertical
        content.alignment = .centerX
        content.distribution = .fill
        content.spacing = 6
        content.setCustomSpacing(2, after: faderRow)
        content.setCustomSpacing(2, after: sendARow)
        content.setCustomSpacing(2, after: sendBRow)
        content.setCustomSpacing(2, after: panRow)
        content.setCustomSpacing(2, after: volumeCaption)
        content.translatesAutoresizingMaskIntoConstraints = false
        addSubview(content)

        NSLayoutConstraint.activate([
            content.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 8),
            content.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -8),
            content.topAnchor.constraint(equalTo: topAnchor, constant: 8),
            content.bottomAnchor.constraint(equalTo: bottomAnchor, constant: -8)
        ])

        // Every full-width child tracks the strip width rather than its own
        // intrinsic size, so nothing jitters when a value changes length.
        for child in [headerView, colorButton, toggles, volumeCaption, faderRow, gainReadout,
                      sendARow, sendASlider, sendBRow, sendBSlider, panRow, panSlider, stateLabel] {
            child.widthAnchor.constraint(equalTo: content.widthAnchor).isActive = true
        }
    }

    private static func captionRow(_ caption: NSTextField, _ value: NSTextField) -> NSStackView {
        value.alignment = .right
        value.setContentHuggingPriority(.required, for: .horizontal)
        value.setContentCompressionResistancePriority(.required, for: .horizontal)
        let row = NSStackView(views: [caption, value])
        row.orientation = .horizontal
        row.alignment = .firstBaseline
        row.distribution = .fill
        row.spacing = 4
        row.translatesAutoresizingMaskIntoConstraints = false
        return row
    }

    // MARK: Actions

    private func wireActions() {
        (colorButton as? ActionButton)?.handler = { [weak self] in self?.showColorMenu() }

        (muteButton as? ToggleButton)?.toggleHandler = { [weak self] isOn in
            guard let self else { return }
            self.selectSelf()
            self.editControl(isOn ? "Mute Track" : "Unmute Track") { $0.mute = isOn }
            StatusCenter.shared.success(
                isOn
                    ? "Muted \(self.trackName) — it is silent until you switch M off. ⌘Z undoes it."
                    : "Unmuted \(self.trackName). ⌘Z undoes it."
            )
        }
        (soloButton as? ToggleButton)?.toggleHandler = { [weak self] isOn in
            guard let self else { return }
            self.selectSelf()
            self.editControl(isOn ? "Solo Track" : "Unsolo Track") { $0.solo = isOn }
            StatusCenter.shared.success(
                isOn
                    ? "Soloed \(self.trackName) — every other track is silent while S is on. ⌘Z undoes it."
                    : "Turned solo off for \(self.trackName). ⌘Z undoes it."
            )
        }
        (armButton as? ToggleButton)?.toggleHandler = { [weak self] isOn in
            guard let self else { return }
            self.selectSelf()
            self.editControl(isOn ? "Arm Track" : "Disarm Track") { $0.arm = isOn }
            StatusCenter.shared.success(
                isOn
                    ? "\(self.trackName) is armed — recording will capture onto it. ⌘Z undoes it."
                    : "\(self.trackName) is no longer armed for recording. ⌘Z undoes it."
            )
        }

        (fader as? ValueSlider)?.handler = { [weak self] value in
            guard let self else { return }
            self.selectSelf()
            self.gainReadout.stringValue = Self.decibelText(value)
            self.editControl("Change Volume") { $0.gain = max(0, min(1.4, value)) }
        }
        (sendASlider as? ValueSlider)?.handler = { [weak self] value in
            guard let self else { return }
            self.selectSelf()
            self.sendAValue.stringValue = Self.percentText(value)
            self.editControl("Change Send A") { $0.sendA = max(0, min(1, value)) }
        }
        (sendBSlider as? ValueSlider)?.handler = { [weak self] value in
            guard let self else { return }
            self.selectSelf()
            self.sendBValue.stringValue = Self.percentText(value)
            self.editControl("Change Send B") { $0.sendB = max(0, min(1, value)) }
        }
        (panSlider as? ValueSlider)?.handler = { [weak self] value in
            guard let self else { return }
            self.selectSelf()
            self.panValue.stringValue = Self.panText(value)
            self.editControl("Change Pan") { $0.pan = max(-1, min(1, value)) }
        }

        nameField.commitHandler = { [weak self] text in
            guard let self else { return }
            let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty else {
                self.nameField.stringValue = self.trackName
                StatusCenter.shared.warning("A track needs a name, so the old one was kept.")
                return
            }
            guard trimmed != self.trackName else { return }
            let previous = self.trackName
            let id = self.trackId
            self.selectSelf()
            self.host?.edit("Rename Track") { project in
                guard let index = project.snapshot.tracks.firstIndex(where: { $0.id == id }) else { return }
                project.snapshot.tracks[index].name = trimmed
            }
            StatusCenter.shared.success("Renamed “\(previous)” to “\(trimmed)”. ⌘Z undoes it.")
        }
    }

    private func selectSelf() {
        onSelect?(trackId)
    }

    private func editControl(_ actionName: String, _ body: (inout MixerControl) -> Void) {
        guard let host else { return }
        let id = trackId
        host.edit(actionName) { project in
            var controls = project.snapshot.controls ?? [:]
            var control = controls[id] ?? MixerControl.neutral
            body(&control)
            controls[id] = control
            project.snapshot.controls = controls
        }
    }

    private func showColorMenu() {
        selectSelf()
        let menu = NSMenu(title: "Track colour")
        menu.autoenablesItems = false
        for preset in Self.presetColors {
            let item = ClosureMenuItem(title: preset.name) { [weak self] in
                self?.applyColor(preset.hex, named: preset.name)
            }
            item.image = Self.swatchImage(color: neonColor(from: preset.hex))
            menu.addItem(item)
        }
        menu.popUp(positioning: nil, at: NSPoint(x: 0, y: colorButton.bounds.height + 3), in: colorButton)
    }

    private func applyColor(_ hex: String, named name: String) {
        let id = trackId
        host?.edit("Change Track Colour") { project in
            guard let index = project.snapshot.tracks.firstIndex(where: { $0.id == id }) else { return }
            project.snapshot.tracks[index].color = hex
        }
        StatusCenter.shared.success("\(trackName) is now \(name.lowercased()) in the arrangement. ⌘Z undoes it.")
    }

    // MARK: Click anywhere selects

    override func mouseDown(with event: NSEvent) {
        selectSelf()
        super.mouseDown(with: event)
    }

    // MARK: Updating values

    func update(
        index: Int,
        track: Track,
        control: MixerControl,
        isSelected: Bool,
        isAudible: Bool,
        someTrackIsSoloed: Bool
    ) {
        self.control = control
        self.isSelected = isSelected
        self.isAudibleNow = isAudible
        self.silencedBySolo = !isAudible && !control.mute && someTrackIsSoloed
        self.trackName = track.name

        numberLabel.stringValue = "\(index + 1)"
        numberLabel.toolTip = "Track \(index + 1) of the mix."

        // Never overwrite text the user is in the middle of typing.
        if nameField.currentEditor() == nil, nameField.stringValue != track.name {
            nameField.stringValue = track.name
        }

        setAccessibilityLabel(track.name)
        setAccessibilityHelp("Mixer strip for \(track.name).")

        let color = neonColor(from: track.color, fallback: Theme.defaultTrackColor)
        colorButton.image = Self.swatchImage(color: color)
        colorButton.toolTip = "Pick the colour \(track.name) uses in the arrangement."
        colorButton.setAccessibilityLabel("Colour for \(track.name)")
        meter.accent = color

        setToggle(muteButton, on: control.mute, tint: Theme.warning, label: "Mute \(track.name)")
        setToggle(soloButton, on: control.solo, tint: Theme.accent, label: "Solo \(track.name)")
        setToggle(armButton, on: control.arm, tint: Theme.danger, label: "Arm \(track.name) for recording")

        setSlider(fader, to: control.gain)
        gainReadout.stringValue = Self.decibelText(control.gain)

        setSlider(sendASlider, to: control.sendA)
        sendAValue.stringValue = Self.percentText(control.sendA)

        setSlider(sendBSlider, to: control.sendB)
        sendBValue.stringValue = Self.percentText(control.sendB)

        setSlider(panSlider, to: control.pan)
        panValue.stringValue = Self.panText(control.pan)

        if control.mute {
            stateLabel.stringValue = "Muted"
            stateLabel.textColor = Theme.warning
            toolTip = "Muted — this track is silent. Switch M off to hear it again."
            alphaValue = 0.5
        } else if silencedBySolo {
            stateLabel.stringValue = "Silent — solo elsewhere"
            stateLabel.textColor = Theme.warning
            toolTip = "Silent because another track is soloed."
            alphaValue = 0.74
        } else {
            stateLabel.stringValue = ""
            toolTip = "Mixer strip for \(track.name). Click anywhere on it to select the track."
            alphaValue = 1
        }
        stateLabel.toolTip = toolTip

        meter.toolTip = "This track's own output level while playing, measured after its volume, pan, mute and solo. When stopped it shows where the fader is sitting."
        meter.setAccessibilityLabel("Output level for \(track.name)")

        refreshColors()
    }

    /// - Parameter measured: this track's own peak from the engine, when one is
    ///   available. Nil means the engine is not running.
    func updateMeter(measured: CGFloat?, isPlaying: Bool) {
        guard isAudibleNow else {
            meter.level = 0
            return
        }
        if isPlaying, let measured {
            meter.level = min(1, measured)
        } else {
            // Stopped: show where the fader is sitting, so the strip still reads
            // at a glance rather than going blank.
            meter.level = min(1, CGFloat(max(0, min(1.4, control.gain))) / 1.4)
        }
    }

    private func setToggle(_ button: NSButton, on: Bool, tint: NSColor, label: String) {
        button.state = on ? .on : .off
        button.bezelColor = on ? tint : nil
        button.contentTintColor = on ? tint.readableForeground : Theme.muted
        button.setAccessibilityLabel(label)
        button.setAccessibilityValue(on ? "on" : "off")
    }

    /// Only writes when the value actually differs, so a slider the user is
    /// currently dragging is never yanked back mid-gesture by the refresh that
    /// its own edit triggered.
    private func setSlider(_ slider: NSSlider, to value: Double) {
        if abs(slider.doubleValue - value) > 0.0005 {
            slider.doubleValue = value
        }
    }

    // MARK: Appearance

    override func viewDidChangeEffectiveAppearance() {
        super.viewDidChangeEffectiveAppearance()
        refreshColors()
    }

    private func refreshColors() {
        effectiveAppearance.performAsCurrentDrawingAppearance { [weak self] in
            guard let self else { return }
            self.layer?.backgroundColor = Theme.panel.cgColor
            if self.isSelected {
                self.layer?.borderColor = Theme.accent.cgColor
                self.layer?.borderWidth = 2
                self.headerView.layer?.backgroundColor = Theme.accent.mixed(with: Theme.panel, amount: 0.62).cgColor
            } else if self.silencedBySolo {
                self.layer?.borderColor = Theme.warning.mixed(with: Theme.panel, amount: 0.35).cgColor
                self.layer?.borderWidth = 1.5
                self.headerView.layer?.backgroundColor = Theme.panelAlt.cgColor
            } else {
                self.layer?.borderColor = Theme.subtleStroke.cgColor
                self.layer?.borderWidth = 1
                self.headerView.layer?.backgroundColor = Theme.panelAlt.cgColor
            }
        }
    }

    // MARK: Formatting

    static func decibelText(_ gain: Double) -> String {
        guard gain > 0.0005 else { return "−∞ dB" }
        let db = 20 * log10(gain)
        if abs(db) < 0.05 { return "0.0 dB" }
        return String(format: "%@%.1f dB", db < 0 ? "−" : "+", abs(db))
    }

    static func percentText(_ value: Double) -> String {
        "\(Int((max(0, min(1, value)) * 100).rounded()))%"
    }

    static func panText(_ value: Double) -> String {
        let clamped = max(-1, min(1, value))
        let amount = Int((abs(clamped) * 100).rounded())
        if amount < 3 { return "C" }
        return clamped < 0 ? "L\(amount)" : "R\(amount)"
    }

    static func swatchImage(color: NSColor, size: NSSize = NSSize(width: 12, height: 12)) -> NSImage {
        let image = NSImage(size: size, flipped: false) { rect in
            let inset = rect.insetBy(dx: 0.5, dy: 0.5)
            roundedFill(inset, radius: 3, color: color)
            roundedStroke(inset, radius: 3, color: Theme.subtleStroke)
            return true
        }
        image.isTemplate = false
        return image
    }
}

// MARK: - Master strip

/// The master strip reports what the engine actually knows: the overall output
/// level, how many tracks can currently be heard, and whether a solo is hiding
/// the rest of the song. There is no master gain in the project format, so none
/// is invented here — a fader that saved nowhere would be a lie.
private final class MasterStrip: NSView {

    var onClearSolos: (() -> Void)?

    private let titleLabel = makeLabel("Master", font: Theme.Font.emphasis(13), color: Theme.text)
    private let subtitleLabel = makeLabel("Whole song", font: Theme.Font.caption(11), color: Theme.muted)
    private let meter = LevelMeterView()
    private let stateLabel = makeLabel("Stopped", font: Theme.Font.caption(11), color: Theme.muted)
    private let audibleLabel = makeLabel("", font: Theme.Font.caption(11), color: Theme.muted)
    private let soloBadge = makeLabel("Solo active", font: Theme.Font.captionBold(11), color: Theme.warning)
    private let clearSolosButton: NSButton

    init() {
        clearSolosButton = Controls.button(
            title: "Clear Solos",
            help: AppEnvironment.shared.help(
                "Switch solo off on every track so the whole song can be heard again.",
                term: "Solo"
            ),
            style: .standard,
            action: {}
        )
        super.init(frame: .zero)
        translatesAutoresizingMaskIntoConstraints = false
        wantsLayer = true
        layer?.cornerRadius = Theme.Metric.cornerRadius
        layer?.borderWidth = 1

        setAccessibilityRole(.group)
        setAccessibilityLabel("Master")
        setAccessibilityHelp("The overall output of the song, and which tracks can currently be heard.")

        titleLabel.alignment = .center
        subtitleLabel.alignment = .center
        stateLabel.alignment = .center
        audibleLabel.alignment = .center
        audibleLabel.maximumNumberOfLines = 2
        audibleLabel.lineBreakMode = .byWordWrapping
        soloBadge.alignment = .center

        meter.accent = Theme.success
        meter.toolTip = "Shows the output level while playing."
        meter.setAccessibilityLabel("Master output level")

        clearSolosButton.font = Theme.Font.caption(11)
        clearSolosButton.controlSize = .small
        (clearSolosButton as? ActionButton)?.handler = { [weak self] in self?.onClearSolos?() }

        let meterRow = NSView()
        meterRow.translatesAutoresizingMaskIntoConstraints = false
        meterRow.addSubview(meter)
        let meterHeight = meterRow.heightAnchor.constraint(greaterThanOrEqualToConstant: 110)
        meterHeight.priority = .defaultHigh
        NSLayoutConstraint.activate([
            meter.centerXAnchor.constraint(equalTo: meterRow.centerXAnchor),
            meter.widthAnchor.constraint(equalToConstant: 16),
            meter.topAnchor.constraint(equalTo: meterRow.topAnchor),
            meter.bottomAnchor.constraint(equalTo: meterRow.bottomAnchor),
            meterHeight
        ])
        meterRow.setContentHuggingPriority(NSLayoutConstraint.Priority(1), for: .vertical)
        meterRow.setContentCompressionResistancePriority(NSLayoutConstraint.Priority(240), for: .vertical)

        let content = NSStackView(views: [
            titleLabel,
            subtitleLabel,
            meterRow,
            stateLabel,
            audibleLabel,
            soloBadge,
            clearSolosButton
        ])
        content.orientation = .vertical
        content.alignment = .centerX
        content.distribution = .fill
        content.spacing = 6
        content.setCustomSpacing(2, after: titleLabel)
        content.translatesAutoresizingMaskIntoConstraints = false
        addSubview(content)

        NSLayoutConstraint.activate([
            content.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 10),
            content.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -10),
            content.topAnchor.constraint(equalTo: topAnchor, constant: 10),
            content.bottomAnchor.constraint(equalTo: bottomAnchor, constant: -10)
        ])
        for child in [titleLabel, subtitleLabel, meterRow, stateLabel, audibleLabel, soloBadge, clearSolosButton] {
            child.widthAnchor.constraint(equalTo: content.widthAnchor).isActive = true
        }

        refreshColors()
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    func update(audibleCount: Int, totalCount: Int, soloActive: Bool) {
        audibleLabel.stringValue = totalCount == 0
            ? "No tracks yet"
            : "\(audibleCount) of \(totalCount) track\(totalCount == 1 ? "" : "s") can be heard"
        audibleLabel.toolTip = "Muted tracks, and tracks hidden by a solo, are not counted."

        soloBadge.isHidden = !soloActive
        clearSolosButton.isHidden = !soloActive
        clearSolosButton.isEnabled = soloActive
        soloBadge.toolTip = AppEnvironment.shared.help(
            "A track is soloed, so everything else is silent right now.",
            term: "Solo"
        )
        soloBadge.setAccessibilityLabel("Warning: a solo is active")
        refreshColors()
    }

    func setLevel(_ level: CGFloat, isPlaying: Bool) {
        meter.level = level
        stateLabel.stringValue = isPlaying ? "Playing" : "Stopped"
        stateLabel.toolTip = isPlaying
            ? "The meter is showing the live output level."
            : "Press Space to play and the meter will move."
    }

    override func viewDidChangeEffectiveAppearance() {
        super.viewDidChangeEffectiveAppearance()
        refreshColors()
    }

    private func refreshColors() {
        effectiveAppearance.performAsCurrentDrawingAppearance { [weak self] in
            guard let self else { return }
            self.layer?.backgroundColor = Theme.panelAlt.cgColor
            self.layer?.borderColor = self.soloBadge.isHidden
                ? Theme.stroke.cgColor
                : Theme.warning.cgColor
        }
    }
}

// MARK: - Level meter

/// A thin vertical bar. This is a canvas, not a control — there is nothing to
/// click, so custom drawing is the right tool here.
private final class LevelMeterView: NSView {

    var accent: NSColor = Theme.success {
        didSet { needsDisplay = true }
    }

    /// 0...1. Set from the transport's measured level for this track.
    var level: CGFloat = 0 {
        didSet {
            let clamped = max(0, min(1, level))
            if clamped != level { level = clamped; return }
            guard abs(oldValue - level) > 0.002 else { return }
            setAccessibilityValue("\(Int((level * 100).rounded())) percent")
            needsDisplay = true
        }
    }

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        translatesAutoresizingMaskIntoConstraints = false
        wantsLayer = true
        setAccessibilityRole(.levelIndicator)
        setAccessibilityLabel("Output level")
        setAccessibilityValue("0 percent")
    }

    convenience init() {
        self.init(frame: .zero)
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    override var isFlipped: Bool { false }

    // MARK: Geometry — one function, used by every drawing pass.

    private var trackRect: NSRect { bounds }

    private func fillRect(for level: CGFloat) -> NSRect {
        let track = trackRect
        let height = max(0, min(1, level)) * track.height
        return NSRect(x: track.minX, y: track.minY, width: track.width, height: height)
    }

    override func draw(_ dirtyRect: NSRect) {
        let track = trackRect
        let radius = min(3, track.width / 2)
        roundedFill(track, radius: radius, color: Theme.canvas)
        roundedStroke(track, radius: radius, color: Theme.subtleStroke)

        let fill = fillRect(for: level)
        guard fill.height > 0.5 else { return }

        NSGraphicsContext.saveGraphicsState()
        NSBezierPath(roundedRect: track, xRadius: radius, yRadius: radius).addClip()
        roundedFill(fill, radius: radius, color: color(for: level))
        NSGraphicsContext.restoreGraphicsState()
    }

    private func color(for level: CGFloat) -> NSColor {
        if level > 0.95 { return Theme.danger }
        if level > 0.82 { return Theme.warning }
        return accent
    }
}

// MARK: - Menu plumbing

/// A menu item that runs a closure, so context menus can be built inline
/// without a selector for each action.
private final class ClosureMenuItem: NSMenuItem {
    private let handler: () -> Void

    init(title: String, handler: @escaping () -> Void) {
        self.handler = handler
        super.init(title: title, action: nil, keyEquivalent: "")
        target = self
        action = #selector(invoke)
        isEnabled = true
    }

    required init(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    @objc private func invoke() { handler() }
}
