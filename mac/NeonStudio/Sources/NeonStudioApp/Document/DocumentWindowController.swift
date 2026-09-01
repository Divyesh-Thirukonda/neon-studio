import AVFoundation
import AppKit
import NeonStudioKit
import UniformTypeIdentifiers

/// The window for one project.
///
/// Compared with the previous single global controller this window has a real
/// title bar (document name, modified dot, proxy icon), a real `NSToolbar` the
/// user can customise, a three-pane `NSSplitViewController` whose positions are
/// remembered between launches, and a status bar that reports progress and
/// errors distinctly. The 90pt hand-drawn header that duplicated the title bar
/// is gone.
public final class DocumentWindowController: NSWindowController, EditorHost, NSToolbarDelegate, NSWindowDelegate, NSMenuItemValidation {

    // MARK: State

    private let neonDocument: NeonDocument
    public let store: ProjectStore
    private let transport = Transport()

    public var project: LocalProject { neonDocument.project }
    public private(set) var activeTool: ToolId = .select
    public private(set) var playheadBar: Double = 0
    public var isPlaying: Bool { transport.state == .playing }

    public var selectedTrackId: String { project.snapshot.selectedTrackId ?? "" }
    public var selectedClipId: String { project.snapshot.selectedClipId ?? "" }

    private var activeWorkView: WorkView {
        WorkView(rawValue: project.snapshot.activeView ?? "") ?? .playlist
    }

    private var audioRecorder: AVAudioRecorder?
    private var recordingURL: URL?
    /// The bar a take is being punched in at, so it lands there rather than
    /// wherever the playhead drifted to while the count-in ran.
    private var recordingPunchInBar: Double = 0
    private var recordingCountInBars: Int { AppEnvironment.shared.countInBars }
    private var lastSoundCheck: [String: Any]?
    private var runningTask: ToolRunner.Handle?

    // MARK: Views

    private let splitViewController = NSSplitViewController()
    private let trackListPane = TrackListPane()
    private let workAreaPane = WorkAreaPane()
    private let inspectorPane = InspectorPane()
    private let statusBar = StatusBarView()

    private var toolbarPlayItem: NSToolbarItem?
    private var playButton: NSButton?
    private var recordButton: NSButton?
    private var tempoField: NSTextField?
    private var snapPopUp: NSPopUpButton?
    private var loopToggle: NSButton?
    private var zoomSlider: NSSlider?

    private var panes: [DocumentPane] { [trackListPane, workAreaPane, inspectorPane] }

    // MARK: Init

    public init(document: NeonDocument) {
        self.neonDocument = document
        self.store = AppEnvironment.shared.store

        let window = DocumentWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1280, height: 800),
            styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        window.minSize = NSSize(width: 900, height: 560)
        window.titlebarAppearsTransparent = false
        window.toolbarStyle = .unified
        // Remembering the frame is what makes the app feel like it stays where
        // you left it; the old build recentred a fixed-size window every launch.
        window.setFrameAutosaveName("NeonStudioDocumentWindow")
        window.tabbingMode = .preferred
        super.init(window: window)

        window.delegate = self
        shouldCascadeWindows = true
        window.onTransportKey = { [weak self] key in
            guard let self else { return false }
            switch key {
            case .playPause: self.togglePlayback()
            case .goToStart: self.goToStart()
            case .selectTool: self.setActiveTool(.select)
            case .drawTool: self.setActiveTool(.draw)
            case .eraseTool: self.setActiveTool(.erase)
            }
            return true
        }

        configureSplitView()
        configureContent()
        configureToolbar()

        document.onProjectChanged.append { [weak self] _ in
            self?.projectDidChange()
        }
        wireTransport()
        panes.forEach { $0.host = self }

        transport.load(project: project, store: store)
        refreshAll()
        announceProjectReadiness()
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    deinit {
        transport.stop()
        runningTask?.cancel()
    }

    // MARK: Layout

    private func configureSplitView() {
        let sidebar = NSSplitViewItem(sidebarWithViewController: trackListPane)
        sidebar.minimumThickness = 220
        sidebar.maximumThickness = 420
        sidebar.canCollapse = true
        // Named so AppKit restores the widths the user chose.
        sidebar.automaticMaximumThickness = 400

        let main = NSSplitViewItem(viewController: workAreaPane)
        main.minimumThickness = 460
        main.canCollapse = false

        // A real inspector item, not just a third column: this is what makes the
        // toolbar's Hide Inspector button and ⌥⌘I actually work, and what gives
        // the pane the standard inspector look.
        let inspector = NSSplitViewItem(inspectorWithViewController: inspectorPane)
        inspector.minimumThickness = 260
        inspector.maximumThickness = 400
        inspector.canCollapse = true
        inspector.isSpringLoaded = false

        splitViewController.addSplitViewItem(sidebar)
        splitViewController.addSplitViewItem(main)
        splitViewController.addSplitViewItem(inspector)
        splitViewController.splitView.autosaveName = "NeonStudioMainSplit"
        splitViewController.splitView.dividerStyle = .thin
    }

    private func configureContent() {
        let root = NSView()
        root.wantsLayer = true
        root.translatesAutoresizingMaskIntoConstraints = false

        let splitView = splitViewController.view
        splitView.translatesAutoresizingMaskIntoConstraints = false
        let separator = Controls.separator(vertical: false)

        root.addSubview(splitView)
        root.addSubview(separator)
        root.addSubview(statusBar)

        NSLayoutConstraint.activate([
            splitView.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            splitView.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            splitView.topAnchor.constraint(equalTo: root.topAnchor),

            separator.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            separator.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            separator.topAnchor.constraint(equalTo: splitView.bottomAnchor),

            statusBar.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            statusBar.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            statusBar.topAnchor.constraint(equalTo: separator.bottomAnchor),
            statusBar.bottomAnchor.constraint(equalTo: root.bottomAnchor)
        ])

        let hosting = NSViewController()
        hosting.view = root
        // The split controller must be a child so its own lifecycle runs.
        hosting.addChild(splitViewController)
        contentViewController = hosting
    }

    // MARK: Toolbar

    private enum ToolbarID {
        static let transport = NSToolbarItem.Identifier("neon.transport")
        static let tempo = NSToolbarItem.Identifier("neon.tempo")
        static let snap = NSToolbarItem.Identifier("neon.snap")
        static let loop = NSToolbarItem.Identifier("neon.loop")
        static let zoom = NSToolbarItem.Identifier("neon.zoom")
        static let checkMix = NSToolbarItem.Identifier("neon.checkMix")
        static let suggest = NSToolbarItem.Identifier("neon.suggest")
        static let exportMix = NSToolbarItem.Identifier("neon.exportMix")
        static let help = NSToolbarItem.Identifier("neon.help")
    }

    private func configureToolbar() {
        let toolbar = NSToolbar(identifier: "NeonStudioMainToolbar")
        toolbar.delegate = self
        toolbar.displayMode = .iconAndLabel
        toolbar.allowsUserCustomization = true
        toolbar.autosavesConfiguration = true
        window?.toolbar = toolbar
    }

    public func toolbarDefaultItemIdentifiers(_ toolbar: NSToolbar) -> [NSToolbarItem.Identifier] {
        [
            .toggleSidebar,
            .sidebarTrackingSeparator,
            ToolbarID.transport,
            ToolbarID.tempo,
            ToolbarID.snap,
            ToolbarID.loop,
            ToolbarID.zoom,
            .flexibleSpace,
            ToolbarID.checkMix,
            ToolbarID.suggest,
            ToolbarID.exportMix,
            ToolbarID.help,
            .toggleInspector
        ]
    }

    public func toolbarAllowedItemIdentifiers(_ toolbar: NSToolbar) -> [NSToolbarItem.Identifier] {
        toolbarDefaultItemIdentifiers(toolbar) + [.space, .flexibleSpace]
    }

    public func toolbar(
        _ toolbar: NSToolbar,
        itemForItemIdentifier itemIdentifier: NSToolbarItem.Identifier,
        willBeInsertedIntoToolbar flag: Bool
    ) -> NSToolbarItem? {
        switch itemIdentifier {
        case ToolbarID.transport:
            return makeTransportItem()
        case ToolbarID.tempo:
            return makeTempoItem()
        case ToolbarID.snap:
            return makeSnapItem()
        case ToolbarID.loop:
            return makeLoopItem()
        case ToolbarID.zoom:
            return makeZoomItem()
        case ToolbarID.checkMix:
            return makeActionItem(
                itemIdentifier,
                label: "Check My Mix",
                symbol: "waveform.badge.magnifyingglass",
                help: AppEnvironment.shared.help(
                    "Listen to the rendered audio and report what's working and what to fix.",
                    term: "Sound check"
                ),
                action: #selector(runSoundCheck(_:))
            )
        case ToolbarID.suggest:
            return makeActionItem(
                itemIdentifier,
                label: "Suggest Ideas",
                symbol: "sparkles",
                help: "Apply proven production tactics to this song. Everything it changes can be undone with one Undo.",
                action: #selector(runDawAgent(_:))
            )
        case ToolbarID.exportMix:
            return makeActionItem(
                itemIdentifier,
                label: "Export Mix",
                symbol: "square.and.arrow.up",
                help: AppEnvironment.shared.help(
                    "Combine every track into one audio file you can share.",
                    term: "Mixdown"
                ),
                action: #selector(exportMixdown(_:))
            )
        case ToolbarID.help:
            return makeActionItem(
                itemIdentifier,
                label: "Guide",
                symbol: "questionmark.circle",
                help: "Take the guided tour of this window again.",
                action: #selector(showTour(_:))
            )
        default:
            return nil
        }
    }

    private func makeActionItem(
        _ identifier: NSToolbarItem.Identifier,
        label: String,
        symbol: String,
        help: String,
        action: Selector
    ) -> NSToolbarItem {
        let item = NSToolbarItem(itemIdentifier: identifier)
        item.label = label
        item.paletteLabel = label
        item.toolTip = help
        item.image = NSImage(systemSymbolName: symbol, accessibilityDescription: label)
        item.target = self
        item.action = action
        item.isBordered = true
        return item
    }

    private func makeTransportItem() -> NSToolbarItem {
        let start = Controls.button(
            title: "",
            symbol: "backward.end.fill",
            help: "Go back to the start of the song. (Return)",
            style: .quiet
        ) { [weak self] in self?.goToStart() }
        start.setAccessibilityLabel("Go to start")

        let play = Controls.toggle(
            title: "",
            symbol: "play.fill",
            help: "Play or stop the song. (Space)",
            style: .primary
        ) { [weak self] _ in self?.togglePlayback() }
        play.setAccessibilityLabel("Play")
        playButton = play

        let record = Controls.toggle(
            title: "",
            symbol: "record.circle",
            help: "Record from your microphone into a new track.",
            style: .destructive
        ) { [weak self] _ in self?.toggleRecording() }
        record.setAccessibilityLabel("Record")
        recordButton = record

        [start, play, record].forEach {
            $0.bezelStyle = .texturedRounded
            $0.imagePosition = .imageOnly
            $0.widthAnchor.constraint(equalToConstant: 36).isActive = true
        }

        let stack = NSStackView(views: [start, play, record])
        stack.orientation = .horizontal
        stack.spacing = 4

        let item = NSToolbarItem(itemIdentifier: ToolbarID.transport)
        item.label = "Transport"
        item.paletteLabel = "Transport"
        item.view = stack
        return item
    }

    private func makeTempoItem() -> NSToolbarItem {
        let field = Controls.numberField(
            value: "\(Int(project.snapshot.bpm))",
            placeholder: "120",
            help: AppEnvironment.shared.help("Set the song's tempo, from 40 to 300.", term: "BPM"),
            accessibilityLabel: "Tempo in beats per minute",
            width: 56
        ) { [weak self] text in
            self?.setTempo(from: text)
        }
        tempoField = field
        let caption = makeLabel("BPM", font: Theme.Font.caption(10), color: Theme.dim)
        caption.setAccessibilityHidden(true)
        let stack = NSStackView(views: [field, caption])
        stack.orientation = .horizontal
        stack.spacing = 4
        stack.alignment = .centerY

        let item = NSToolbarItem(itemIdentifier: ToolbarID.tempo)
        item.label = "Tempo"
        item.paletteLabel = "Tempo"
        item.toolTip = field.toolTip
        item.view = stack
        return item
    }

    private func makeSnapItem() -> NSToolbarItem {
        let values = SnapValue.allCases
        let popUp = Controls.popUp(
            titles: values.map(\.label),
            selected: values.firstIndex(of: snapValue) ?? 3,
            help: AppEnvironment.shared.help(
                "Choose how edits line up to the grid.",
                term: "Snap"
            ),
            accessibilityLabel: "Snap to grid"
        ) { [weak self] index in
            guard let self, index >= 0, index < values.count else { return }
            self.setSnap(values[index])
        }
        snapPopUp = popUp
        popUp.widthAnchor.constraint(equalToConstant: 108).isActive = true

        let item = NSToolbarItem(itemIdentifier: ToolbarID.snap)
        item.label = "Snap"
        item.paletteLabel = "Snap"
        item.toolTip = popUp.toolTip
        item.view = popUp
        return item
    }

    private func makeLoopItem() -> NSToolbarItem {
        let toggle = Controls.toggle(
            title: "Loop",
            symbol: "repeat",
            help: AppEnvironment.shared.help(
                "Repeat the highlighted bars. Drag the yellow bar in the ruler to change the range.",
                term: "Loop"
            ),
            isOn: project.snapshot.loopEnabled == true
        ) { [weak self] isOn in
            self?.setLoopEnabled(isOn)
        }
        loopToggle = toggle
        let item = NSToolbarItem(itemIdentifier: ToolbarID.loop)
        item.label = "Loop"
        item.paletteLabel = "Loop"
        item.toolTip = toggle.toolTip
        item.view = toggle
        return item
    }

    private func makeZoomItem() -> NSToolbarItem {
        let slider = Controls.slider(
            value: Double(workAreaPane.pixelsPerBar),
            min: 16,
            max: 160,
            help: "Zoom the arrangement in or out. (⌘+ and ⌘−)",
            accessibilityLabel: "Timeline zoom"
        ) { [weak self] value in
            self?.setZoom(CGFloat(value))
        }
        slider.widthAnchor.constraint(equalToConstant: 92).isActive = true
        zoomSlider = slider

        let item = NSToolbarItem(itemIdentifier: ToolbarID.zoom)
        item.label = "Zoom"
        item.paletteLabel = "Zoom"
        item.toolTip = slider.toolTip
        item.view = slider
        return item
    }

    // MARK: Transport wiring

    private func wireTransport() {
        transport.onPlayheadMoved = { [weak self] bar in
            guard let self else { return }
            self.playheadBar = bar
            self.panes.forEach { $0.playheadDidMove(to: bar) }
        }
        transport.onStateChanged = { [weak self] state in
            self?.renderTransportState(state)
        }
        transport.onMasterLevel = { [weak self] level in
            self?.workAreaPane.updateMasterLevel(level)
        }
        transport.onTrackLevels = { [weak self] levels in
            self?.workAreaPane.updateTrackLevels(levels)
        }
        transport.onWarning = { message in
            StatusCenter.shared.warning(message)
        }
    }

    private func renderTransportState(_ state: Transport.State) {
        let playing = state == .playing
        playButton?.state = playing ? .on : .off
        playButton?.image = NSImage(
            systemSymbolName: playing ? "stop.fill" : "play.fill",
            accessibilityDescription: playing ? "Stop" : "Play"
        )
        playButton?.setAccessibilityLabel(playing ? "Stop" : "Play")
        playButton?.toolTip = playing ? "Stop playback. (Space)" : "Play the song from the playhead. (Space)"
        panes.forEach { $0.refresh() }
    }

    // MARK: EditorHost

    public func selectTrack(_ trackId: String) {
        guard project.track(id: trackId) != nil, trackId != selectedTrackId else { return }
        neonDocument.updateTransientState { project in
            project.snapshot.selectedTrackId = trackId
            project.snapshot.selectedClipId = ""
        }
    }

    public func selectClip(trackId: String, clipId: String) {
        neonDocument.updateTransientState { project in
            project.snapshot.selectedTrackId = trackId
            project.snapshot.selectedClipId = clipId
        }
    }

    public func clearClipSelection() {
        guard !selectedClipId.isEmpty else { return }
        neonDocument.updateTransientState { project in
            project.snapshot.selectedClipId = ""
        }
    }

    public func edit(_ actionName: String, _ body: (inout LocalProject) -> Void) {
        neonDocument.mutate(actionName, body)
    }

    public func seek(toBar bar: Double) {
        let clamped = max(0, bar)
        playheadBar = clamped
        transport.seek(toBar: clamped)
        panes.forEach { $0.playheadDidMove(to: clamped) }
        if isPlaying {
            transport.play(project: project, fromBar: clamped)
        }
    }

    public func status(_ message: String) {
        StatusCenter.shared.info(message)
    }

    public func requestFocus(on view: WorkView) {
        setWorkView(view)
    }

    // MARK: Refresh

    private func projectDidChange() {
        refreshAll()
        // Rebuilding the audio graph is only necessary when the set of audio
        // files changed; gain/pan/mute/solo are applied live instead.
        transport.applyMix(project: project)
    }

    private func refreshAll() {
        panes.forEach { $0.refresh() }
        tempoField?.stringValue = "\(Int(project.snapshot.bpm))"
        if let popUp = snapPopUp, let index = SnapValue.allCases.firstIndex(of: snapValue) {
            popUp.selectItem(at: index)
        }
        loopToggle?.state = project.snapshot.loopEnabled == true ? .on : .off
        // The title is NSDocument's to set: it owns the proxy icon, the file
        // name, and the dot that says there are unsaved changes. Overwriting it
        // here threw all three away.
        synchronizeWindowTitleWithDocumentName()
    }

    /// Tells the user up front how much of this project can actually be heard,
    /// instead of letting them press Play and get silence with no explanation.
    private func announceProjectReadiness() {
        let counts = store.audioTrackCounts(for: project)
        if counts.total == 0 {
            StatusCenter.shared.info("This project has no tracks yet. Add one from the + button in the track list.")
        } else if counts.withAudio == 0 {
            StatusCenter.shared.warning(
                "No audio yet for \(project.name).",
                detail: "None of its \(counts.total) tracks has a sound file, so Play won't make noise. Use Track ▸ Import Audio, or Export Mix to render one."
            )
        } else if counts.withAudio < counts.total {
            StatusCenter.shared.info("\(counts.withAudio) of \(counts.total) tracks have audio ready to play.")
        } else {
            StatusCenter.shared.success("\(project.name) is ready. Press Space to play.")
        }
    }

    // MARK: Playback

    @objc public func togglePlayback() {
        if isPlaying {
            transport.stop()
            StatusCenter.shared.info("Stopped at bar \(Int(playheadBar) + 1).")
            return
        }
        guard !project.snapshot.tracks.isEmpty else {
            StatusCenter.shared.warning("There's nothing to play yet. Add a track first.")
            return
        }
        transport.load(project: project, store: store)
        guard transport.play(project: project, fromBar: playheadBar) else {
            let counts = store.audioTrackCounts(for: project)
            StatusCenter.shared.warning(
                "No audio to play.",
                detail: counts.total == 0
                    ? "Add a track, then import a sound into it."
                    : "None of this project's \(counts.total) tracks points at a sound file that exists on disk."
            )
            return
        }
        StatusCenter.shared.success("Playing \(transport.loadedTrackCount) track\(transport.loadedTrackCount == 1 ? "" : "s").")
    }

    @objc public func goToStart() {
        let wasPlaying = isPlaying
        transport.stop()
        seek(toBar: project.snapshot.loopEnabled == true ? (project.snapshot.loopStartBar ?? 0) : 0)
        if wasPlaying {
            transport.play(project: project, fromBar: playheadBar)
        }
        StatusCenter.shared.info("Back to bar \(Int(playheadBar) + 1).")
    }

    // MARK: Recording

    @objc public func toggleRecording() {
        if audioRecorder != nil {
            finishRecording()
        } else {
            beginRecording()
        }
    }

    private func beginRecording() {
        // macOS requires explicit consent. The old build never asked, so the
        // first recording silently captured nothing.
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized:
            startRecorder()
        case .notDetermined:
            AVCaptureDevice.requestAccess(for: .audio) { [weak self] granted in
                DispatchQueue.main.async {
                    guard let self else { return }
                    if granted {
                        self.startRecorder()
                    } else {
                        self.recordButton?.state = .off
                        StatusCenter.shared.warning("Microphone access was declined, so there's nothing to record.")
                    }
                }
            }
        case .denied, .restricted:
            recordButton?.state = .off
            let alert = NSAlert()
            alert.messageText = "Neon Studio can't use the microphone"
            alert.informativeText = "Allow microphone access in System Settings ▸ Privacy & Security ▸ Microphone, then try recording again."
            alert.addButton(withTitle: "Open System Settings")
            alert.addButton(withTitle: "Cancel")
            if alert.runModal() == .alertFirstButtonReturn,
               let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone") {
                NSWorkspace.shared.open(url)
            }
        @unknown default:
            recordButton?.state = .off
        }
    }

    private func startRecorder() {
        let inbox = store.vocalInboxDirectory()
        try? FileManager.default.createDirectory(at: inbox, withIntermediateDirectories: true)
        let url = inbox.appendingPathComponent("take_\(timestampForId()).wav")

        // Punch in at the loop start when looping, otherwise at the playhead.
        // Either way the bar is fixed *now*, so the take lands where the user
        // aimed rather than where the playhead ended up after the count-in.
        let punchIn: Double
        let punchOut: Double?
        if project.snapshot.loopEnabled == true {
            punchIn = max(0, project.snapshot.loopStartBar ?? 0)
            punchOut = project.snapshot.loopEndBar
        } else {
            punchIn = playheadBar
            punchOut = nil
        }
        recordingPunchInBar = punchIn

        do {
            let recorder = try AVAudioRecorder(url: url, settings: [
                AVFormatIDKey: kAudioFormatLinearPCM,
                AVSampleRateKey: 48_000,
                AVNumberOfChannelsKey: 1,
                AVLinearPCMBitDepthKey: 24,
                AVLinearPCMIsFloatKey: false,
                AVLinearPCMIsBigEndianKey: false
            ])
            recorder.prepareToRecord()

            transport.load(project: project, store: store)
            let countIn = Transport.CountIn(
                bars: recordingCountInBars,
                punchInBar: punchIn,
                punchOutBar: punchOut
            )
            let sync = transport.playForRecording(project: project, countIn: countIn)

            let started: Bool
            if let sync {
                // Convert the transport's host time into the recorder's own
                // timebase so the clicks, the backing track and the take all
                // start on the same instant.
                let armAt = recorder.deviceCurrentTime + max(0, sync.leadSeconds)
                if let duration = sync.durationSeconds {
                    started = recorder.record(atTime: armAt, forDuration: duration)
                } else {
                    started = recorder.record(atTime: armAt)
                }
            } else {
                // No transport (nothing loaded to play along to) — record now.
                started = recorder.record()
            }

            guard started else {
                throw NSError(domain: "NeonStudio", code: 10, userInfo: [
                    NSLocalizedDescriptionKey: "The audio input didn't start."
                ])
            }
            audioRecorder = recorder
            recordingURL = url
            recordButton?.state = .on

            let bar = Int(punchIn) + 1
            if recordingCountInBars > 0 {
                let beats = recordingCountInBars * 4
                StatusCenter.shared.post(
                    .progress,
                    "Counting in \(beats) beats, then recording from bar \(bar)."
                        + (punchOut.map { " Stops at bar \(Int($0))." } ?? "")
                )
            } else {
                StatusCenter.shared.post(.progress, "Recording from bar \(bar). Press the red button again to stop.")
            }
        } catch {
            recordButton?.state = .off
            transport.stop()
            StatusCenter.shared.failure("Couldn't start recording", error: error, window: window)
        }
    }

    private func finishRecording() {
        audioRecorder?.stop()
        audioRecorder = nil
        recordButton?.state = .off
        transport.stop()
        guard let url = recordingURL, FileManager.default.fileExists(atPath: url.path) else {
            StatusCenter.shared.warning("Recording stopped, but no audio was captured.")
            return
        }
        recordingURL = nil
        let bar = recordingPunchInBar
        addAudioTrack(
            from: url,
            name: "Recording",
            color: "#f59fcb",
            instrument: "Microphone",
            startBar: bar,
            actionName: "Add Recording"
        )
        StatusCenter.shared.success(
            "Recorded a take at bar \(Int(bar) + 1).",
            detail: "Drag its block to move it, or ⌘Z to discard it."
        )
    }

    // MARK: Project edits driven by the toolbar

    private func setTempo(from text: String) {
        let raw = Double(text.trimmingCharacters(in: .whitespaces)) ?? project.snapshot.bpm
        let value = max(40, min(300, raw))
        tempoField?.stringValue = "\(Int(value))"
        guard value != project.snapshot.bpm else { return }
        edit("Set Tempo") { $0.snapshot.bpm = value }
        transport.load(project: project, store: store)
        StatusCenter.shared.success("Tempo is now \(Int(value)) BPM.")
    }

    public func setSnap(_ value: SnapValue) {
        edit("Change Snap") { $0.snapshot.snap = value.rawValue }
        StatusCenter.shared.info(value == .none ? "Snap off — edits move freely." : "Edits snap to \(value.label).")
    }

    public func setLoopEnabled(_ enabled: Bool) {
        edit(enabled ? "Turn On Loop" : "Turn Off Loop") { $0.snapshot.loopEnabled = enabled }
        if enabled {
            let start = Int((project.snapshot.loopStartBar ?? 0) + 1)
            let end = Int(project.snapshot.loopEndBar ?? 16)
            StatusCenter.shared.info("Looping bars \(start)–\(end). Drag the yellow bar in the ruler to change it.")
        } else {
            StatusCenter.shared.info("Loop off.")
        }
        if isPlaying { transport.play(project: project, fromBar: playheadBar) }
    }

    public func setZoom(_ pixelsPerBar: CGFloat) {
        workAreaPane.pixelsPerBar = max(16, min(160, pixelsPerBar))
        zoomSlider?.doubleValue = Double(workAreaPane.pixelsPerBar)
    }

    public func setWorkView(_ view: WorkView) {
        guard view != activeWorkView else { return }
        neonDocument.updateTransientState { $0.snapshot.activeView = view.rawValue }
        StatusCenter.shared.info("\(view.label): \(view.explanation)")
    }

    public func setActiveTool(_ tool: ToolId) {
        activeTool = tool
        panes.forEach { $0.refresh() }
        StatusCenter.shared.info("\(tool.label) tool. \(tool.explanation)")
    }

    // MARK: Menu validation
    //
    // Without this every command stayed permanently enabled and several of them
    // silently did nothing. A greyed-out item is honest; one that looks live and
    // then ignores you is not.

    public func validateMenuItem(_ menuItem: NSMenuItem) -> Bool {
        switch menuItem.action {
        case #selector(menuPlayPause(_:)):
            menuItem.title = isPlaying ? "Stop" : "Play"
            return !project.snapshot.tracks.isEmpty
        case #selector(menuGoToStart(_:)):
            return playheadBar > 0 || isPlaying
        case #selector(menuDeleteSelection(_:)):
            if !selectedClipId.isEmpty {
                menuItem.title = "Delete Clip"
                return true
            }
            menuItem.title = "Delete Track"
            return project.snapshot.tracks.count > 1 && !selectedTrackId.isEmpty
        case #selector(menuToggleLoop(_:)):
            menuItem.state = project.snapshot.loopEnabled == true ? .on : .off
            return true
        case #selector(menuRevealProjectFile(_:)):
            return neonDocument.fileURL != nil || neonDocument.libraryURL != nil
        case #selector(runSoundCheck(_:)):
            // Sound check reads rendered audio; with none there is nothing to hear.
            return store.audioTrackCounts(for: project).withAudio > 0
        case #selector(runDawAgent(_:)), #selector(exportMixdown(_:)),
             #selector(menuMaterializeTranscript(_:)), #selector(menuRunVocalLab(_:)):
            return runningTask == nil
        case #selector(menuSetCountIn(_:)):
            menuItem.state = menuItem.tag == AppEnvironment.shared.countInBars ? .on : .off
            return audioRecorder == nil
        case #selector(menuToggleRecord(_:)):
            menuItem.title = audioRecorder == nil ? "Record" : "Stop Recording"
            return true
        case #selector(menuShowView(_:)):
            menuItem.state = (menuItem.representedObject as? String) == activeWorkView.rawValue ? .on : .off
            return true
        case #selector(menuSelectTool(_:)):
            menuItem.state = (menuItem.representedObject as? String) == activeTool.rawValue ? .on : .off
            return true
        default:
            return true
        }
    }

    // MARK: Menu actions

    @objc func menuPlayPause(_ sender: Any?) { togglePlayback() }
    @objc func menuGoToStart(_ sender: Any?) { goToStart() }
    @objc func menuToggleRecord(_ sender: Any?) { toggleRecording() }
    @objc func menuSetCountIn(_ sender: NSMenuItem) {
        let bars = sender.tag
        AppEnvironment.shared.countInBars = bars
        StatusCenter.shared.info(
            bars == 0
                ? "Count-in off — recording starts the moment you press Record."
                : "Count-in set to \(bars) bar\(bars == 1 ? "" : "s"). Recording starts on the downbeat after the clicks."
        )
        MenuBuilder.shared.updateDynamicItems(for: self)
    }
    @objc func menuZoomIn(_ sender: Any?) { setZoom(workAreaPane.pixelsPerBar * 1.25) }
    @objc func menuZoomOut(_ sender: Any?) { setZoom(workAreaPane.pixelsPerBar / 1.25) }
    @objc func menuToggleLoop(_ sender: Any?) { setLoopEnabled(!(project.snapshot.loopEnabled == true)) }
    @objc func menuEditLoopRange(_ sender: Any?) { editLoopRange() }
    @objc func menuSetTempo(_ sender: Any?) { window?.makeFirstResponder(tempoField) }
    @objc func menuSelectTool(_ sender: NSMenuItem) {
        guard let tool = ToolId(rawValue: sender.representedObject as? String ?? "") else { return }
        setActiveTool(tool)
    }
    @objc func menuShowView(_ sender: NSMenuItem) {
        guard let view = WorkView(rawValue: sender.representedObject as? String ?? "") else { return }
        setWorkView(view)
    }
    @objc func menuImportAudio(_ sender: Any?) { importAudioFile() }
    @objc func menuAddTrack(_ sender: Any?) { addEmptyTrack() }
    @objc func menuDeleteSelection(_ sender: Any?) { deleteSelection() }
    @objc func menuRevealProjectFile(_ sender: Any?) { revealProjectFile() }
    @objc func menuMaterializeTranscript(_ sender: Any?) { materializeTranscript() }
    @objc func menuRunVocalLab(_ sender: Any?) { runVocalLab() }
    @objc func showTour(_ sender: Any?) {
        TourController.shared.start(in: self, regions: tourRegions(), force: true)
    }

    // MARK: Track editing

    public func addEmptyTrack() {
        let index = project.snapshot.tracks.count + 1
        let palette = ["#60c8f8", "#9ef0c0", "#f8d46a", "#f59fcb", "#c4a5ff", "#ffa06a"]
        let color = palette[index % palette.count]
        let id = makeId("track")
        edit("Add Track") { project in
            project.snapshot.tracks.append(Track(
                id: id,
                name: "Track \(index)",
                kind: "audio",
                color: color,
                gain: 0.82,
                pan: 0,
                steps: [],
                instrument: "Empty",
                clips: [],
                effects: [
                    Effect(id: "eq", name: "EQ", active: false, amount: 0.35),
                    Effect(id: "comp", name: "Compressor", active: false, amount: 0.35)
                ],
                sampleEdit: normalizeSampleEdit(nil)
            ))
            project.snapshot.selectedTrackId = id
        }
        StatusCenter.shared.success("Added Track \(index). Import a sound into it, or draw notes in the Notes tab.")
    }

    public func importAudioFile() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.audio, .wav, .mp3, .aiff, .mpeg4Audio]
        panel.allowsMultipleSelection = true
        panel.canChooseDirectories = false
        panel.message = "Choose one or more sounds. Each becomes its own track."
        panel.prompt = "Import"
        guard let window else { return }
        panel.beginSheetModal(for: window) { [weak self] response in
            guard response == .OK, let self else { return }
            let urls = panel.urls
            guard !urls.isEmpty else { return }
            let palette = ["#9ef0c0", "#60c8f8", "#f8d46a", "#c4a5ff", "#ffa06a"]
            for (offset, url) in urls.enumerated() {
                self.addAudioTrack(
                    from: url,
                    name: url.deletingPathExtension().lastPathComponent,
                    color: palette[(self.project.snapshot.tracks.count + offset) % palette.count],
                    instrument: "Imported Audio",
                    startBar: 0,
                    actionName: urls.count == 1 ? "Import Audio" : "Import \(urls.count) Sounds"
                )
            }
            StatusCenter.shared.success(
                urls.count == 1
                    ? "Imported \(urls[0].lastPathComponent)."
                    : "Imported \(urls.count) sounds as new tracks."
            )
        }
    }

    /// Adds an audio file as a track, sizing its clip from the file's real
    /// duration rather than a hardcoded guess.
    @discardableResult
    public func addAudioTrack(
        from url: URL,
        name: String,
        color: String,
        instrument: String,
        startBar: Double,
        actionName: String
    ) -> String {
        let id = makeId(name.lowercased().contains("vocal") ? "vocal" : "audio")
        let duration = (try? AVAudioFile(forReading: url)).map { file in
            Double(file.length) / file.processingFormat.sampleRate
        } ?? 8
        let bars = max(0.25, (duration / project.secondsPerBar * 4).rounded() / 4)
        let isVocal = instrument.localizedCaseInsensitiveContains("vocal")
            || instrument.localizedCaseInsensitiveContains("microphone")
        let track = Track(
            id: id,
            name: String(name.prefix(40)),
            kind: "audio",
            file: url.path,
            color: color,
            gain: 0.86,
            pan: 0,
            steps: [],
            instrument: instrument,
            clips: [Clip(
                id: "\(id)-clip",
                name: url.deletingPathExtension().lastPathComponent,
                startBar: max(0, startBar),
                bars: bars,
                lane: id,
                color: color,
                type: "audio"
            )],
            effects: [
                Effect(id: "eq", name: "EQ", active: false, amount: 0.35),
                Effect(id: "comp", name: "Compressor", active: true, amount: 0.5),
                Effect(id: "delay", name: "Stereo Delay", active: isVocal, amount: 0.34)
            ],
            sampleEdit: normalizeSampleEdit(nil)
        )
        edit(actionName) { project in
            project.snapshot.tracks.append(track)
            project.snapshot.selectedTrackId = id
            project.snapshot.selectedClipId = "\(id)-clip"
            project.snapshot.activeView = WorkView.playlist.rawValue
        }
        transport.load(project: project, store: store)
        return id
    }

    /// Deletes whatever is selected, most specific first, and says what it did.
    public func deleteSelection() {
        if !selectedClipId.isEmpty,
           let clip = project.snapshot.tracks.flatMap({ $0.clips ?? [] }).first(where: { $0.id == selectedClipId }) {
            let clipId = selectedClipId
            edit("Delete Clip") { project in
                for index in project.snapshot.tracks.indices {
                    project.snapshot.tracks[index].clips = (project.snapshot.tracks[index].clips ?? [])
                        .filter { $0.id != clipId }
                }
                project.snapshot.selectedClipId = ""
            }
            StatusCenter.shared.success("Deleted the clip “\(clip.name)”. ⌘Z puts it back.")
            return
        }

        guard let track = project.track(id: selectedTrackId) else {
            StatusCenter.shared.info("Select a clip or a track first, then press Delete.")
            return
        }
        guard project.snapshot.tracks.count > 1 else {
            StatusCenter.shared.warning("A project needs at least one track, so this one can't be deleted.")
            return
        }
        if AppEnvironment.shared.confirmsDestructiveEdits {
            let alert = NSAlert()
            alert.messageText = "Delete the track “\(track.name)”?"
            alert.informativeText = "Its clips, notes and effect settings go with it. The sound file on disk is not deleted, and ⌘Z undoes this."
            alert.alertStyle = .warning
            alert.addButton(withTitle: "Delete Track")
            alert.addButton(withTitle: "Cancel")
            alert.showsSuppressionButton = true
            alert.suppressionButton?.title = "Don't ask again"
            guard alert.runModal() == .alertFirstButtonReturn else { return }
            if alert.suppressionButton?.state == .on {
                AppEnvironment.shared.confirmsDestructiveEdits = false
            }
        }
        let trackId = track.id
        edit("Delete Track") { project in
            project.snapshot.tracks.removeAll { $0.id == trackId }
            project.snapshot.controls?[trackId] = nil
            project.snapshot.notes = (project.snapshot.notes ?? []).filter { $0.trackId != trackId }
            project.snapshot.automationLanes = (project.snapshot.automationLanes ?? []).filter { $0.trackId != trackId }
            project.snapshot.selectedTrackId = project.snapshot.tracks.first?.id ?? ""
            project.snapshot.selectedClipId = ""
        }
        transport.load(project: project, store: store)
        StatusCenter.shared.success("Deleted “\(track.name)”. ⌘Z puts it back.")
    }

    private func editLoopRange() {
        let alert = NSAlert()
        alert.messageText = "Loop these bars"
        alert.informativeText = AppEnvironment.shared.help(
            "Playback will repeat between these two bars. Bar numbers start at 1.",
            term: "Loop"
        )
        let start = Controls.numberField(
            value: "\(Int((project.snapshot.loopStartBar ?? 0) + 1))",
            placeholder: "1",
            help: "First bar of the loop.",
            accessibilityLabel: "Loop start bar",
            action: { _ in }
        )
        let end = Controls.numberField(
            value: "\(Int(project.snapshot.loopEndBar ?? 16))",
            placeholder: "16",
            help: "Last bar of the loop.",
            accessibilityLabel: "Loop end bar",
            action: { _ in }
        )
        let stack = NSStackView(views: [
            Controls.formRow("Start bar", start, labelWidth: 80),
            Controls.formRow("End bar", end, labelWidth: 80)
        ])
        stack.orientation = .vertical
        stack.spacing = 8
        stack.frame = NSRect(x: 0, y: 0, width: 250, height: 60)
        alert.accessoryView = stack
        alert.addButton(withTitle: "Set Loop")
        alert.addButton(withTitle: "Cancel")
        guard alert.runModal() == .alertFirstButtonReturn else { return }

        let startBar = max(1, min(999, Int(start.stringValue) ?? 1))
        let endBar = max(startBar + 1, min(1000, Int(end.stringValue) ?? startBar + 8))
        edit("Set Loop Range") { project in
            project.snapshot.loopEnabled = true
            project.snapshot.loopStartBar = Double(startBar - 1)
            project.snapshot.loopEndBar = Double(endBar)
        }
        StatusCenter.shared.success("Looping bars \(startBar)–\(endBar).")
        if isPlaying { transport.play(project: project, fromBar: playheadBar) }
    }

    public func revealProjectFile() {
        if let url = neonDocument.fileURL ?? neonDocument.libraryURL {
            NSWorkspace.shared.activateFileViewerSelecting([url])
            return
        }
        StatusCenter.shared.info("This project hasn't been saved to a file yet. Use File ▸ Save to choose a location.")
    }

    // MARK: Long-running tools

    /// Every helper tool goes through here, so they all get the same behaviour:
    /// a progress message, a working Cancel button, output streamed into the
    /// Activity log, and errors reported properly instead of being swallowed.
    private func runTool(
        name: String,
        progressMessage: String,
        arguments: [String],
        completion: @escaping (ToolResult) -> Void
    ) {
        guard let python = AppEnvironment.shared.pythonExecutable else {
            StatusCenter.shared.failure(
                "\(name) needs Python",
                error: ToolError.missingExecutable("/usr/bin/python3"),
                window: window
            )
            return
        }
        guard runningTask == nil else {
            StatusCenter.shared.warning("Another task is already running. Wait for it to finish, or cancel it first.")
            return
        }

        statusBar.beginTask(progressMessage) { [weak self] in
            self?.runningTask?.cancel()
        }

        runningTask = AppEnvironment.shared.toolRunner.run(
            name: name,
            executable: python,
            arguments: arguments,
            currentDirectory: store.rootURL,
            onOutputLine: { line in
                StatusCenter.shared.post(.progress, "\(progressMessage) — \(String(line.prefix(120)))")
            },
            completion: { [weak self] result in
                guard let self else { return }
                self.runningTask = nil
                self.statusBar.endTask()
                switch result {
                case .success(let value):
                    completion(value)
                case .failure(let error):
                    if case ToolError.cancelled = error {
                        StatusCenter.shared.info("\(name) cancelled.")
                    } else {
                        StatusCenter.shared.failure("\(name) didn't finish", error: error, window: self.window)
                    }
                }
            }
        )
        if runningTask == nil {
            statusBar.endTask()
        }
    }

    @objc public func runSoundCheck(_ sender: Any?) {
        let counts = store.audioTrackCounts(for: project)
        guard counts.withAudio > 0 else {
            StatusCenter.shared.warning(
                "There's no audio to check yet.",
                detail: "Sound check listens to rendered audio. Import a sound or use Export Mix first."
            )
            return
        }
        let temp = FileManager.default.temporaryDirectory
            .appendingPathComponent("\(project.id)-check-\(timestampForId()).neon.json")
        do {
            try store.exportProject(project, to: temp)
        } catch {
            StatusCenter.shared.failure("Couldn't prepare the sound check", error: error, window: window)
            return
        }
        runTool(
            name: "Sound check",
            progressMessage: "Listening to \(project.name)",
            arguments: [
                store.toolURL("does_this_sound_good.py").path,
                "--root", store.rootURL.path,
                "--project", temp.path,
                "--format", "json"
            ]
        ) { [weak self] result in
            try? FileManager.default.removeItem(at: temp)
            guard let self else { return }
            let analysis = result.lastJSONObject
            guard !analysis.isEmpty else {
                StatusCenter.shared.failure(
                    "Sound check didn't return a result",
                    error: ToolError.noJSON(name: "Sound check"),
                    window: self.window
                )
                return
            }
            self.lastSoundCheck = analysis
            let score = ReportBuilder.intValue(analysis["verdict"].flatMap { ($0 as? [String: Any])?["score"] })
            StatusCenter.shared.success("Sound check: \(score)/100.")
            ReportWindowController.present(
                report: ReportBuilder.soundCheck(analysis, projectName: self.project.name),
                relativeTo: self.window
            )
        }
    }

    @objc public func runDawAgent(_ sender: Any?) {
        let stamp = timestampForId()
        let temp = FileManager.default.temporaryDirectory
        let input = temp.appendingPathComponent("\(project.id)-agent-in-\(stamp).neon.json")
        let output = temp.appendingPathComponent("\(project.id)-agent-out-\(stamp).neon.json")
        let feedback = temp.appendingPathComponent("\(project.id)-agent-feedback-\(stamp).json")

        var arguments = [
            store.toolURL("daw_agent.py").path,
            "--root", store.rootURL.path,
            "apply",
            "--project", input.path,
            "--output", output.path,
            "--format", "json"
        ]
        do {
            try store.exportProject(project, to: input)
            if let lastSoundCheck, JSONSerialization.isValidJSONObject(lastSoundCheck) {
                try JSONSerialization.data(withJSONObject: lastSoundCheck, options: [.prettyPrinted])
                    .write(to: feedback, options: [.atomic])
                arguments.append(contentsOf: ["--feedback-json", feedback.path])
            }
        } catch {
            StatusCenter.shared.failure("Couldn't prepare the suggestion run", error: error, window: window)
            return
        }

        runTool(
            name: "Suggestions",
            progressMessage: "Looking for improvements to \(project.name)",
            arguments: arguments
        ) { [weak self] result in
            defer {
                [input, output, feedback].forEach { try? FileManager.default.removeItem(at: $0) }
            }
            guard let self else { return }
            let report = result.lastJSONObject
            guard let updated = self.store.loadProject(from: output) else {
                StatusCenter.shared.failure(
                    "The suggestion run didn't produce a project",
                    error: ToolError.noJSON(name: "Suggestions"),
                    window: self.window
                )
                return
            }
            // One undo step reverts every change the tool made.
            self.neonDocument.replaceProject(updated, actionName: "Apply Suggestions")
            self.transport.load(project: self.project, store: self.store)
            let applied = (report["actions"] as? [[String: Any]])?.count ?? 0
            StatusCenter.shared.success(
                "Applied \(applied) suggestion\(applied == 1 ? "" : "s"). ⌘Z reverts all of them."
            )
            ReportWindowController.present(
                report: ReportBuilder.agent(report, projectName: self.project.name),
                relativeTo: self.window
            )
        }
    }

    @objc public func exportMixdown(_ sender: Any?) {
        let panel = NSSavePanel()
        panel.allowedContentTypes = [.wav]
        panel.nameFieldStringValue = "\(safeProjectId(project.name.lowercased()))-mix.wav"
        panel.message = "Save one audio file containing every track, mixed together."
        panel.prompt = "Export"
        guard let window else { return }
        panel.beginSheetModal(for: window) { [weak self] response in
            guard response == .OK, let destination = panel.url, let self else { return }
            let temp = FileManager.default.temporaryDirectory
                .appendingPathComponent("\(self.project.id)-mix-\(timestampForId()).neon.json")
            do {
                try self.store.exportProject(self.project, to: temp)
            } catch {
                StatusCenter.shared.failure("Couldn't prepare the export", error: error, window: self.window)
                return
            }
            self.runTool(
                name: "Export Mix",
                progressMessage: "Mixing \(self.project.name) down to one file",
                arguments: [
                    self.store.toolURL("render_mixdown.py").path,
                    "--root", self.store.rootURL.path,
                    "--project", temp.path,
                    "--output", destination.path
                ]
            ) { _ in
                try? FileManager.default.removeItem(at: temp)
                StatusCenter.shared.success(
                    "Exported \(destination.lastPathComponent).",
                    detail: "Saved to \(destination.deletingLastPathComponent().path)"
                )
                NSWorkspace.shared.activateFileViewerSelecting([destination])
            }
        }
    }

    public func materializeTranscript() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        panel.allowedContentTypes = [.plainText, .text, .utf8PlainText]
        panel.allowsOtherFileTypes = true
        panel.message = AppEnvironment.shared.help(
            "Choose a text file describing the song — a tutorial, a walkthrough, or your own notes.",
            term: "Transcript"
        )
        panel.prompt = "Choose"
        guard let window else { return }
        panel.beginSheetModal(for: window) { [weak self] response in
            guard response == .OK, let url = panel.url, let self else { return }
            guard ["txt", "text", "md", "markdown", "srt", "vtt"].contains(url.pathExtension.lowercased()) else {
                StatusCenter.shared.warning("Choose a plain text file (.txt, .md, .srt or .vtt).")
                return
            }
            guard let settings = self.promptTranscriptSettings(for: url) else { return }
            self.runTool(
                name: "Build from description",
                progressMessage: "Turning \(url.lastPathComponent) into a project",
                arguments: [
                    self.store.toolURL("songlab.py").path,
                    "init",
                    "--project-id", settings.projectId,
                    "--prompt", settings.prompt,
                    "--transcript-file", url.path,
                    "--force-materialize"
                ]
            ) { _ in
                guard let built = self.store.loadProjects().first(where: { $0.id == settings.projectId }) else {
                    StatusCenter.shared.warning("The description was processed but no project came back.")
                    return
                }
                do {
                    let document = try NeonDocument.makeUntitled(
                        with: built,
                        libraryURL: self.store.projectURL(for: built.id)
                    )
                    NSDocumentController.shared.addDocument(document)
                    document.showWindows()
                    StatusCenter.shared.success("Built “\(built.name)” from your description.")
                } catch {
                    StatusCenter.shared.failure("Couldn't open the new project", error: error, window: self.window)
                }
            }
        }
    }

    private func promptTranscriptSettings(for url: URL) -> (projectId: String, prompt: String)? {
        let alert = NSAlert()
        alert.messageText = "Build a project from \(url.lastPathComponent)"
        alert.informativeText = "Neon Studio reads your description, fills in anything it doesn't specify with sensible choices, and opens the result as a new project."
        let idField = Controls.numberField(
            value: store.uniqueProjectId(basedOn: url.deletingPathExtension().lastPathComponent),
            placeholder: "my-song",
            help: "A short name with no spaces. This becomes the file name.",
            accessibilityLabel: "Project id",
            width: 220,
            action: { _ in }
        )
        idField.alignment = .left
        let promptField = Controls.numberField(
            value: project.description ?? project.name,
            placeholder: "What kind of song is this?",
            help: "One line describing the song, used to guide the build.",
            accessibilityLabel: "Song brief",
            width: 220,
            action: { _ in }
        )
        promptField.alignment = .left
        let stack = NSStackView(views: [
            Controls.formRow("Name", idField, labelWidth: 60),
            Controls.formRow("About", promptField, labelWidth: 60)
        ])
        stack.orientation = .vertical
        stack.spacing = 8
        stack.frame = NSRect(x: 0, y: 0, width: 310, height: 62)
        alert.accessoryView = stack
        alert.addButton(withTitle: "Build")
        alert.addButton(withTitle: "Cancel")
        guard alert.runModal() == .alertFirstButtonReturn else { return nil }
        let id = safeProjectId(idField.stringValue)
        let prompt = promptField.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        return (id.isEmpty ? store.uniqueProjectId(basedOn: "song") : id, prompt.isEmpty ? project.name : prompt)
    }

    public func runVocalLab() {
        guard ToolPaths.afconvertAvailable else {
            StatusCenter.shared.warning("Vocal tuning needs macOS's afconvert tool, which isn't available here.")
            return
        }
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.audio]
        panel.allowsMultipleSelection = false
        panel.message = "Choose a raw singing take. Neon Studio tunes it and lines it up with this song."
        panel.prompt = "Choose"
        guard let window else { return }
        panel.beginSheetModal(for: window) { [weak self] response in
            guard response == .OK, let input = panel.url, let self else { return }
            guard let settings = self.promptVocalSettings() else { return }
            let stem = safeProjectId(input.deletingPathExtension().lastPathComponent.lowercased())
            let stamp = timestampForId()
            let inbox = self.store.vocalInboxDirectory()
            let exports = self.store.exportsDirectory()
            try? FileManager.default.createDirectory(at: inbox, withIntermediateDirectories: true)
            try? FileManager.default.createDirectory(at: exports, withIntermediateDirectories: true)
            let rawWav = inbox.appendingPathComponent("\(stamp)_\(stem).wav")
            let output = exports.appendingPathComponent("vocal_\(stamp)_\(stem).wav")

            self.statusBar.beginTask("Converting the vocal", cancel: nil)
            AppEnvironment.shared.toolRunner.run(
                name: "Convert vocal",
                executable: ToolPaths.afconvertURL,
                arguments: ["-f", "WAVE", "-d", "LEI16@44100", input.path, rawWav.path],
                currentDirectory: self.store.rootURL
            ) { [weak self] result in
                guard let self else { return }
                self.statusBar.endTask()
                if case .failure(let error) = result {
                    StatusCenter.shared.failure("Couldn't convert the vocal", error: error, window: self.window)
                    return
                }
                self.runTool(
                    name: "Vocal tuning",
                    progressMessage: "Tuning \(input.lastPathComponent)",
                    arguments: [
                        self.store.toolURL("vocal_autotune.py").path,
                        "--input", rawWav.path,
                        "--output", output.path,
                        "--name", input.lastPathComponent,
                        "--bpm", "\(self.project.snapshot.bpm)",
                        "--start-bar", "\(settings.startBar)",
                        "--total-bars", "\(max(32, Int(self.project.contentEndBar) + 8))",
                        "--key", settings.key
                    ]
                ) { toolResult in
                    let analysis = toolResult.lastJSONObject
                    let segments = ReportBuilder.intValue(analysis["segments"])
                    // vocal_autotune.py pads the output with silence up to the
                    // requested start bar, so the file already begins at bar 0.
                    // Placing the clip at the start bar as well double-counted
                    // the offset and drew a take entering at bar 17 as a
                    // 75-bar block that stretched the timeline to bar 92.
                    self.addAudioTrack(
                        from: output,
                        name: "Vocal \(stem.replacingOccurrences(of: "_", with: " "))",
                        color: "#f59fcb",
                        instrument: "Tuned Vocal",
                        startBar: 0,
                        actionName: "Add Tuned Vocal"
                    )
                    StatusCenter.shared.success(
                        "Added the tuned vocal, entering at bar \(settings.startBar).",
                        detail: segments > 0 ? "\(segments) phrase\(segments == 1 ? "" : "s") detected." : nil
                    )
                }
            }
        }
    }

    private func promptVocalSettings() -> (startBar: Int, key: String)? {
        let alert = NSAlert()
        alert.messageText = "Tune this vocal"
        alert.informativeText = AppEnvironment.shared.help(
            "Choose where the vocal should come in and which key to tune it to.",
            term: "Key"
        )
        let startField = Controls.numberField(
            value: "\(Int((project.snapshot.loopStartBar ?? 0) + 1))",
            placeholder: "1",
            help: "The bar where the vocal starts.",
            accessibilityLabel: "Start bar",
            action: { _ in }
        )
        let keyField = Controls.numberField(
            value: (project.keyCenter ?? "e_minor").lowercased()
                .replacingOccurrences(of: " / ", with: "_")
                .replacingOccurrences(of: " ", with: "_"),
            placeholder: "e_minor",
            help: "For example c_major or e_minor.",
            accessibilityLabel: "Key",
            width: 140,
            action: { _ in }
        )
        keyField.alignment = .left
        let stack = NSStackView(views: [
            Controls.formRow("Start bar", startField, labelWidth: 80),
            Controls.formRow("Key", keyField, labelWidth: 80)
        ])
        stack.orientation = .vertical
        stack.spacing = 8
        stack.frame = NSRect(x: 0, y: 0, width: 250, height: 62)
        alert.accessoryView = stack
        alert.addButton(withTitle: "Tune")
        alert.addButton(withTitle: "Cancel")
        guard alert.runModal() == .alertFirstButtonReturn else { return nil }
        let bar = max(1, min(999, Int(startField.stringValue) ?? 1))
        let key = keyField.stringValue.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return (bar, key.isEmpty ? "e_minor" : key)
    }

    // MARK: Tour

    private func tourRegions() -> [TourController.Region] {
        [
            TourController.Region(
                view: trackListPane.view,
                title: "Your tracks live here",
                body: "Each row is one instrument or sound. Click a row to work on it. The M and S buttons mute a track or play it on its own."
            ),
            TourController.Region(
                view: workAreaPane.view,
                title: "This is where you build the song",
                body: "Numbers along the top are bars — chunks of time. Drag blocks to move when they play. The tabs above switch between arranging, writing notes, and mixing."
            ),
            TourController.Region(
                view: inspectorPane.view,
                title: "Details about what you selected",
                body: "Whatever you click on the left or in the middle, its settings show up here."
            ),
            TourController.Region(
                view: statusBar,
                title: "Neon Studio tells you what happened",
                body: "Every action reports here. Green means it worked, red means something needs your attention, and Activity keeps the full history."
            )
        ]
    }

    public func startTourIfNeeded() {
        TourController.shared.start(in: self, regions: tourRegions(), force: false)
    }

    // MARK: NSWindowDelegate

    public func windowWillClose(_ notification: Notification) {
        transport.stop()
        runningTask?.cancel()
    }

    public func windowDidBecomeMain(_ notification: Notification) {
        MenuBuilder.shared.updateDynamicItems(for: self)
    }
}
