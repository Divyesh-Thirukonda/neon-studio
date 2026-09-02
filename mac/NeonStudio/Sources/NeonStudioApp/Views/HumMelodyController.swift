import AppKit
import AVFoundation
import NeonStudioKit

/// "Sing what you want it to sound like."
///
/// One sheet on the document window takes somebody from pressing Record to
/// having real notes on the selected track: a count-in, the hum, Stop, a short
/// wait while `hum_to_melody.py` works out the pitches, then a preview of what
/// was heard and one button to put it on the grid. The insert is a single
/// undoable edit, so a take that went wrong costs exactly one ⌘Z.
///
/// Everything reaches the window through `ToolHost`; nothing here knows what
/// kind of window controller is behind it.
final class HumMelodyController: NSObject {

    // MARK: State

    private enum Phase {
        case ready
        case recording
        /// Waiting on something that isn't the user: microphone permission or
        /// the analysis tool.
        case busy(title: String, body: String, detail: String)
        case result
        /// Something went wrong or nothing was heard. `next` is the thing to
        /// try; `retry` says what the Try again button does about it.
        case problem(title: String, body: String, next: String, retry: Retry)
    }

    private enum Retry {
        /// Record a fresh take.
        case record
        /// Run the analysis again on the take already on disk.
        case analyse
        /// Microphone access is off; offer System Settings alongside Record.
        case microphoneSettings
    }

    private struct HeardNote {
        let beat: Double
        let duration: Double
        let midi: Int
        let velocity: Double
        let color: String
    }

    private struct Analysis {
        let notes: [HeardNote]
        let voicedSeconds: Double
        let segments: Int
        let keyUsed: String?
        let octaveShift: Int
        let confidence: Double
        let warnings: [String]
    }

    /// Controllers stay alive for as long as their sheet is up, whatever the
    /// caller does with its reference.
    private static var active: [HumMelodyController] = []

    private static let sheetWidth: CGFloat = 500
    private static let minimumSheetHeight: CGFloat = 360
    private static let maximumSheetHeight: CGFloat = 620
    private static let textWidth: CGFloat = sheetWidth - 40
    private static let previewNoteLimit = 8

    private let host: ToolHost
    private var phase: Phase = .ready

    private var startBar: Double = 0
    private var recordsFromLoopStart = false
    private var trackId = ""
    private var trackName = ""
    private var trackColor: String?
    private var keyCenter: String?

    private var countInBars: Int
    private var snapToKey = false
    private var previousCountIn: Int?
    private var discardTake = false
    private var isDismissed = false
    private var takeURL: URL?
    private var analysis: Analysis?

    private var sheet: HumSheetWindow?
    private let content = NSView()
    private let titleLabel = makeLabel("", font: Theme.Font.title(15), color: Theme.text)
    private let bodyLabel = HumMelodyController.wrappingLabel("", font: Theme.Font.body(13), color: Theme.muted)
    private let stateContainer = NSView()
    private let footer = NSStackView()

    private var elapsedTimer: Timer?
    private var elapsedLabel: NSTextField?
    private var recordingHint: NSTextField?
    private var recordingStartedAt: Date?
    private var toolWatchdog: Timer?
    private var toolFinished = false

    // MARK: Lifecycle

    init(host: ToolHost) {
        self.host = host
        // The Transport ▸ Count-In setting, clamped to the three choices the
        // sheet offers.
        self.countInBars = max(0, min(2, AppEnvironment.shared.countInBars))
        super.init()
    }

    /// Opens the sheet. Pass the bar the playhead is on: that is where the
    /// notes land unless the loop is on, in which case the host records from
    /// the loop start and the notes follow it there.
    func start(startBar: Double = 0) {
        guard sheet == nil else { return }
        guard let window = host.window else {
            StatusCenter.shared.warning("Open a song first, then hum a melody into it.")
            return
        }
        guard window.attachedSheet == nil else {
            StatusCenter.shared.warning("Finish the dialog that's already open, then try Hum a Melody again.")
            return
        }
        let project = host.project
        guard !project.snapshot.tracks.isEmpty else {
            StatusCenter.shared.warning(
                "Add a track first.",
                detail: "Your hummed notes need a track to live on. Use Track ▸ Add Track, then try Hum a Melody again."
            )
            return
        }

        let track = project.track(id: project.snapshot.selectedTrackId ?? "") ?? project.snapshot.tracks[0]
        trackId = track.id
        trackName = track.name
        trackColor = track.color
        let trimmedKey = (project.keyCenter ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        keyCenter = trimmedKey.isEmpty ? nil : trimmedKey
        snapToKey = keyCenter != nil

        // Mirror the host's punch-in rule so the notes and the take agree on
        // where they start. The tool takes whole bars.
        if project.snapshot.loopEnabled == true {
            self.startBar = max(0, (project.snapshot.loopStartBar ?? 0).rounded(.down))
            recordsFromLoopStart = true
        } else {
            self.startBar = max(0, startBar.rounded(.down))
            recordsFromLoopStart = false
        }

        HumMelodyController.active.append(self)
        let sheet = makeSheet()
        self.sheet = sheet
        phase = .ready
        render()
        window.beginSheet(sheet, completionHandler: nil)
    }

    private func close() {
        guard !isDismissed else { return }
        isDismissed = true
        stopElapsedTimer()
        toolWatchdog?.invalidate()
        toolWatchdog = nil
        restoreCountIn()
        if let sheet {
            (sheet.sheetParent ?? host.window)?.endSheet(sheet)
            sheet.orderOut(nil)
        }
        HumMelodyController.active.removeAll { $0 === self }
    }

    /// Escape, or the Cancel button, from any state.
    private func cancel() {
        switch phase {
        case .recording:
            discardTake = true
            host.finishTake()
            StatusCenter.shared.info("Recording thrown away. Nothing was added to \(trackName).")
        case .busy:
            StatusCenter.shared.info("Hum a Melody cancelled. Nothing was added to \(trackName).")
        default:
            StatusCenter.shared.info("Hum a Melody closed. Nothing was added to \(trackName).")
        }
        close()
    }

    // MARK: Sheet construction

    private func makeSheet() -> HumSheetWindow {
        let size = NSSize(width: Self.sheetWidth, height: Self.minimumSheetHeight)
        let sheet = HumSheetWindow(
            contentRect: NSRect(origin: .zero, size: size),
            styleMask: [.titled],
            backing: .buffered,
            defer: false
        )
        sheet.title = "Hum a melody"
        sheet.isReleasedWhenClosed = false
        sheet.onCancel = { [weak self] in self?.cancel() }

        let root = ThemedBackgroundView { Theme.panel }
        // A window sizes its content view with the autoresizing mask; this one
        // view opts back in and everything inside it uses constraints.
        root.translatesAutoresizingMaskIntoConstraints = true
        root.autoresizingMask = [.width, .height]
        root.frame = NSRect(origin: .zero, size: size)
        root.setAccessibilityRole(.group)
        root.setAccessibilityLabel("Hum a melody")

        content.translatesAutoresizingMaskIntoConstraints = false
        stateContainer.translatesAutoresizingMaskIntoConstraints = false
        footer.orientation = .horizontal
        footer.alignment = .centerY
        footer.spacing = 8
        footer.translatesAutoresizingMaskIntoConstraints = false

        titleLabel.setAccessibilityRole(.staticText)
        bodyLabel.setAccessibilityRole(.staticText)

        for view in [titleLabel, bodyLabel, stateContainer, footer] {
            content.addSubview(view)
        }
        root.addSubview(content)

        // The content can be taller than the window for a moment between a
        // state change and the resize that follows it; a non-required bottom
        // edge keeps that from logging as an unsatisfiable layout.
        let bottom = content.bottomAnchor.constraint(equalTo: root.bottomAnchor)
        bottom.priority = .defaultHigh

        NSLayoutConstraint.activate([
            content.topAnchor.constraint(equalTo: root.topAnchor),
            content.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            content.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            content.widthAnchor.constraint(equalToConstant: Self.sheetWidth),
            bottom,

            titleLabel.topAnchor.constraint(equalTo: content.topAnchor, constant: 20),
            titleLabel.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 20),
            titleLabel.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -20),

            bodyLabel.topAnchor.constraint(equalTo: titleLabel.bottomAnchor, constant: 6),
            bodyLabel.leadingAnchor.constraint(equalTo: titleLabel.leadingAnchor),
            bodyLabel.trailingAnchor.constraint(equalTo: titleLabel.trailingAnchor),

            stateContainer.topAnchor.constraint(equalTo: bodyLabel.bottomAnchor, constant: 16),
            stateContainer.leadingAnchor.constraint(equalTo: titleLabel.leadingAnchor),
            stateContainer.trailingAnchor.constraint(equalTo: titleLabel.trailingAnchor),

            footer.topAnchor.constraint(greaterThanOrEqualTo: stateContainer.bottomAnchor, constant: 16),
            footer.leadingAnchor.constraint(equalTo: titleLabel.leadingAnchor),
            footer.trailingAnchor.constraint(equalTo: titleLabel.trailingAnchor),
            footer.bottomAnchor.constraint(equalTo: content.bottomAnchor, constant: -16)
        ])

        sheet.contentView = root
        return sheet
    }

    // MARK: Rendering

    private func render() {
        guard sheet != nil else { return }
        stateContainer.subviews.forEach { $0.removeFromSuperview() }
        footer.arrangedSubviews.forEach { footer.removeView($0) }
        elapsedLabel = nil
        recordingHint = nil

        switch phase {
        case .ready:
            titleLabel.stringValue = "Hum a melody for \(trackName)"
            bodyLabel.stringValue = readyBody()
            install(makeReadyView())
            let record = Controls.button(
                title: "Record",
                symbol: "record.circle",
                help: countInBars == 0
                    ? "Start listening right away. Hum or sing the melody, then press Stop."
                    : "Start listening. You'll hear \(countInBars == 1 ? "one bar" : "two bars") of clicks first, then hum or sing the melody.",
                style: .destructive
            ) { [weak self] in self?.record() }
            Controls.makeDefault(record)
            fillFooter(leading: [], trailing: [cancelButton(), record])

        case .recording:
            titleLabel.stringValue = "Hum a melody for \(trackName)"
            bodyLabel.stringValue = "Listening…"
            install(makeRecordingView())
            let stop = Controls.button(
                title: "Stop",
                symbol: "stop.fill",
                help: "Stop recording and work out which notes you sang.",
                style: .primary
            ) { [weak self] in self?.stopTake() }
            Controls.makeDefault(stop)
            fillFooter(leading: [], trailing: [cancelButton(recordingInProgress: true), stop])

        case .busy(let title, let body, let detail):
            titleLabel.stringValue = title
            bodyLabel.stringValue = body
            install(makeBusyView(detail))
            fillFooter(leading: [], trailing: [cancelButton()])

        case .result:
            guard let analysis else {
                showProblem(
                    title: "Something went missing",
                    body: "The analysis finished but its result is gone.",
                    next: "Press Try again to record another take.",
                    retry: .record
                )
                return
            }
            let count = analysis.notes.count
            titleLabel.stringValue = "Heard \(count) note\(count == 1 ? "" : "s") over \(Self.seconds(analysis.voicedSeconds))"
            bodyLabel.stringValue = "Insert puts them on \(trackName) at bar \(Int(startBar) + 1). "
                + "Replaces notes already in those bars. ⌘Z undoes it."
            install(makeResultView(analysis))
            let tryAgain = Controls.button(
                title: "Try again",
                symbol: "arrow.counterclockwise",
                help: "Throw these notes away and record another take.",
                style: .standard
            ) { [weak self] in self?.reset() }
            let keepVoice = Controls.button(
                title: "Insert and keep my voice",
                help: AppEnvironment.shared.help(
                    "Put the notes on \(trackName) and also add your recording as a new audio track called “Hummed take” at the same bar. ⌘Z undoes both at once.",
                    term: "Track"
                ),
                style: .standard
            ) { [weak self] in self?.insert(keepVoice: true) }
            let insert = Controls.button(
                title: "Insert notes",
                help: AppEnvironment.shared.help(
                    "Put these notes on \(trackName). Notes already in those bars are replaced. ⌘Z undoes it.",
                    term: "Piano roll"
                ),
                style: .primary
            ) { [weak self] in self?.insert(keepVoice: false) }
            Controls.makeDefault(insert)
            fillFooter(leading: [tryAgain], trailing: [cancelButton(), keepVoice, insert])

        case .problem(let title, let body, let next, let retry):
            titleLabel.stringValue = title
            bodyLabel.stringValue = body
            install(makeProblemView(next))
            var trailing: [NSView] = [cancelButton()]
            switch retry {
            case .record:
                let again = Controls.button(
                    title: "Try again",
                    symbol: "record.circle",
                    help: "Go back and record another take.",
                    style: .primary
                ) { [weak self] in self?.reset() }
                Controls.makeDefault(again)
                trailing.append(again)
            case .analyse:
                let recordAgain = Controls.button(
                    title: "Record again",
                    help: "Go back and record a fresh take instead.",
                    style: .standard
                ) { [weak self] in self?.reset() }
                let again = Controls.button(
                    title: "Try again",
                    symbol: "arrow.counterclockwise",
                    help: "Run the analysis again on the take you just recorded.",
                    style: .primary
                ) { [weak self] in
                    guard let self else { return }
                    if let url = self.takeURL {
                        self.analyse(url)
                    } else {
                        self.reset()
                    }
                }
                Controls.makeDefault(again)
                trailing.append(recordAgain)
                trailing.append(again)
            case .microphoneSettings:
                let settings = Controls.button(
                    title: "Open System Settings",
                    help: "Opens the Microphone privacy list so you can switch Neon Studio on.",
                    style: .standard
                ) { [weak self] in self?.openMicrophoneSettings() }
                let again = Controls.button(
                    title: "Try again",
                    symbol: "record.circle",
                    help: "Once the microphone is allowed, record another take.",
                    style: .primary
                ) { [weak self] in self?.reset() }
                Controls.makeDefault(again)
                trailing.append(settings)
                trailing.append(again)
            }
            fillFooter(leading: [], trailing: trailing)
        }

        titleLabel.setAccessibilityLabel(titleLabel.stringValue)
        bodyLabel.setAccessibilityLabel(bodyLabel.stringValue)
        fitSheet()
    }

    private func readyBody() -> String {
        let opening = countInBars == 0
            ? "Press Record, then hum or sing straight away."
            : "Press Record, wait for the clicks, then hum or sing."
        let place = recordsFromLoopStart
            ? "at the start of the loop (bar \(Int(startBar) + 1))"
            : "at the bar the playhead is on (bar \(Int(startBar) + 1))"
        return "\(opening) Press Stop when you're done. Your notes go on the grid \(place)."
    }

    private func install(_ view: NSView) {
        view.translatesAutoresizingMaskIntoConstraints = false
        stateContainer.addSubview(view)
        NSLayoutConstraint.activate([
            view.topAnchor.constraint(equalTo: stateContainer.topAnchor),
            view.leadingAnchor.constraint(equalTo: stateContainer.leadingAnchor),
            view.trailingAnchor.constraint(equalTo: stateContainer.trailingAnchor),
            view.bottomAnchor.constraint(lessThanOrEqualTo: stateContainer.bottomAnchor)
        ])
    }

    private func fillFooter(leading: [NSView], trailing: [NSView]) {
        leading.forEach { footer.addArrangedSubview($0) }
        let spacer = NSView()
        spacer.translatesAutoresizingMaskIntoConstraints = false
        spacer.setContentHuggingPriority(NSLayoutConstraint.Priority(1), for: .horizontal)
        spacer.setContentCompressionResistancePriority(NSLayoutConstraint.Priority(1), for: .horizontal)
        footer.addArrangedSubview(spacer)
        trailing.forEach { footer.addArrangedSubview($0) }
    }

    private func cancelButton(recordingInProgress: Bool = false) -> NSButton {
        Controls.button(
            title: "Cancel",
            help: recordingInProgress
                ? "Stop and throw the recording away. Nothing is added to the song."
                : "Close without adding anything to the song.",
            style: .standard,
            keyEquivalent: "\u{1b}",
            keyEquivalentModifiers: []
        ) { [weak self] in self?.cancel() }
    }

    /// Grows the sheet to fit the current state and shrinks it back afterwards,
    /// so the result table never gets clipped and the ready state never sits
    /// in a mostly empty box.
    private func fitSheet() {
        guard let sheet else { return }
        content.layoutSubtreeIfNeeded()
        let needed = content.fittingSize.height.rounded(.up)
        let height = min(Self.maximumSheetHeight, max(Self.minimumSheetHeight, needed))
        let currentContent = sheet.contentRect(forFrameRect: sheet.frame)
        guard abs(currentContent.height - height) > 0.5 else { return }
        let contentRect = NSRect(
            x: currentContent.minX,
            y: currentContent.maxY - height,
            width: Self.sheetWidth,
            height: height
        )
        let frame = sheet.frameRect(forContentRect: contentRect)
        sheet.setFrame(frame, display: true, animate: !Theme.prefersReducedMotion && sheet.isVisible)
    }

    // MARK: State views

    private func makeReadyView() -> NSView {
        let popUp = Controls.popUp(
            titles: ["Off", "1 bar", "2 bars"],
            selected: countInBars,
            help: AppEnvironment.shared.help(
                "How many bars of clicks you hear before recording starts, so you come in on the beat. Applies to this take only.",
                term: "Bar"
            ),
            accessibilityLabel: "Count-in"
        ) { [weak self] index in
            guard let self else { return }
            self.countInBars = max(0, min(2, index))
            self.bodyLabel.stringValue = self.readyBody()
            self.bodyLabel.setAccessibilityLabel(self.bodyLabel.stringValue)
        }
        let countInRow = Controls.formRow(
            "Count-in",
            popUp,
            help: AppEnvironment.shared.help(
                "How many bars of clicks you hear before recording starts, so you come in on the beat. Applies to this take only.",
                term: "Bar"
            ),
            labelWidth: 90
        )

        let checkbox = NSButton(
            checkboxWithTitle: "Snap notes to the song's key",
            target: self,
            action: #selector(toggleSnapToKey(_:))
        )
        checkbox.translatesAutoresizingMaskIntoConstraints = false
        checkbox.font = Theme.Font.body()
        checkbox.setAccessibilityLabel("Snap notes to the song's key")
        if let keyCenter {
            checkbox.isEnabled = true
            checkbox.state = snapToKey ? .on : .off
            checkbox.toolTip = AppEnvironment.shared.help(
                "Nudges each sung note to the nearest note in \(keyCenter), so a slightly flat or sharp note still fits the song.",
                term: "Key"
            )
        } else {
            checkbox.isEnabled = false
            checkbox.state = .off
            checkbox.toolTip = AppEnvironment.shared.help(
                "This song has no key set, so notes are kept exactly as you sang them. Set a key in the Inspector to turn this on.",
                term: "Key"
            )
        }
        checkbox.setAccessibilityHelp(checkbox.toolTip ?? "")

        let tip = Self.wrappingLabel(
            "Tip: sing one clear note at a time — “da da da” is easier to hear than words.",
            font: Theme.Font.body(12),
            color: Theme.dim
        )

        let stack = NSStackView(views: [countInRow, checkbox, tip])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 12
        stack.setCustomSpacing(18, after: checkbox)
        return stack
    }

    @objc private func toggleSnapToKey(_ sender: NSButton) {
        snapToKey = sender.state == .on
    }

    private func makeRecordingView() -> NSView {
        let dot = NSImageView()
        dot.image = NSImage(systemSymbolName: "record.circle.fill", accessibilityDescription: "Recording")
        dot.symbolConfiguration = .init(pointSize: 20, weight: .regular)
        dot.contentTintColor = Theme.danger
        dot.translatesAutoresizingMaskIntoConstraints = false
        dot.setAccessibilityHidden(true)

        let elapsed = makeLabel("0.0 s", font: Theme.Font.mono(28, weight: .semibold), color: Theme.text)
        elapsed.setAccessibilityLabel("Recording time")
        elapsed.setAccessibilityRole(.staticText)

        let row = NSStackView(views: [dot, elapsed])
        row.orientation = .horizontal
        row.alignment = .centerY
        row.spacing = 8

        let hint = Self.wrappingLabel(
            "Hum or sing now. Press Stop when you're done.",
            font: Theme.Font.body(12),
            color: Theme.muted
        )

        elapsedLabel = elapsed
        recordingHint = hint

        let stack = NSStackView(views: [row, hint])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 8
        return stack
    }

    private func makeBusyView(_ detail: String) -> NSView {
        let spinner = NSProgressIndicator()
        spinner.style = .spinning
        spinner.controlSize = .regular
        spinner.isIndeterminate = true
        spinner.translatesAutoresizingMaskIntoConstraints = false
        spinner.startAnimation(nil)
        spinner.setAccessibilityLabel("Working")

        let label = Self.wrappingLabel(detail, font: Theme.Font.body(12), color: Theme.muted)
        label.preferredMaxLayoutWidth = Self.textWidth - 40

        let row = NSStackView(views: [spinner, label])
        row.orientation = .horizontal
        row.alignment = .centerY
        row.spacing = 10
        return row
    }

    private func makeResultView(_ analysis: Analysis) -> NSView {
        let stack = NSStackView()
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 8

        var summary: [String] = []
        if let key = analysis.keyUsed, !key.isEmpty {
            summary.append("Snapped to \(key)")
        }
        if analysis.segments > analysis.notes.count {
            summary.append("\(analysis.segments) sung phrases")
        }
        if !summary.isEmpty {
            stack.addArrangedSubview(makeLabel(summary.joined(separator: " · "), font: Theme.Font.caption(12), color: Theme.dim))
        }

        let grid = makeNotesGrid(analysis.notes)
        stack.addArrangedSubview(grid)

        let extra = analysis.notes.count - Self.previewNoteLimit
        if extra > 0 {
            let more = makeLabel("…and \(extra) more", font: Theme.Font.caption(12), color: Theme.dim)
            more.setAccessibilityLabel("and \(extra) more notes")
            stack.addArrangedSubview(more)
        }

        for warning in analysis.warnings.prefix(3) {
            stack.addArrangedSubview(makeWarningRow(warning))
        }
        if let first = stack.arrangedSubviews.first, first !== grid {
            stack.setCustomSpacing(6, after: first)
        }
        stack.setCustomSpacing(10, after: grid)
        return stack
    }

    private func makeNotesGrid(_ notes: [HeardNote]) -> NSGridView {
        let header = ["Note", "Where", "Length"].map {
            makeLabel($0, font: Theme.Font.captionBold(11), color: Theme.muted)
        }
        var rows: [[NSView]] = [header]
        for note in notes.prefix(Self.previewNoteLimit) {
            let name = Self.noteName(note.midi)
            let position = Self.positionText(beat: note.beat)
            let length = Self.lengthText(note.duration)
            let nameLabel = makeLabel(name, font: Theme.Font.mono(12, weight: .semibold), color: Theme.text)
            let positionLabel = makeLabel(position, font: Theme.Font.mono(12), color: Theme.muted)
            let lengthLabel = makeLabel(length, font: Theme.Font.mono(12), color: Theme.muted)
            nameLabel.setAccessibilityLabel("Note \(name)")
            positionLabel.setAccessibilityLabel("At \(position)")
            lengthLabel.setAccessibilityLabel("Lasting \(length)")
            rows.append([nameLabel, positionLabel, lengthLabel])
        }
        let grid = NSGridView(views: rows)
        grid.translatesAutoresizingMaskIntoConstraints = false
        grid.rowSpacing = 3
        grid.columnSpacing = 20
        grid.xPlacement = .leading
        grid.yPlacement = .center
        grid.setAccessibilityLabel("The first \(min(notes.count, Self.previewNoteLimit)) notes heard")
        grid.toolTip = "Each row is one note: its name, where it sits in the song, and how long it lasts."
        return grid
    }

    private func makeWarningRow(_ text: String) -> NSView {
        let icon = NSImageView()
        icon.image = NSImage(systemSymbolName: "exclamationmark.triangle.fill", accessibilityDescription: "Warning")
        icon.symbolConfiguration = .init(pointSize: 12, weight: .semibold)
        icon.contentTintColor = Theme.warning
        icon.translatesAutoresizingMaskIntoConstraints = false
        icon.setAccessibilityHidden(true)

        let label = Self.wrappingLabel(text, font: Theme.Font.body(12), color: Theme.warning)
        label.preferredMaxLayoutWidth = Self.textWidth - 24
        label.setAccessibilityLabel("Warning: \(text)")

        let row = NSStackView(views: [icon, label])
        row.orientation = .horizontal
        row.alignment = .firstBaseline
        row.spacing = 6
        return row
    }

    private func makeProblemView(_ next: String) -> NSView {
        let icon = NSImageView()
        icon.image = NSImage(systemSymbolName: "lightbulb", accessibilityDescription: "What to try")
        icon.symbolConfiguration = .init(pointSize: 14, weight: .regular)
        icon.contentTintColor = Theme.warning
        icon.translatesAutoresizingMaskIntoConstraints = false
        icon.setAccessibilityHidden(true)

        let label = Self.wrappingLabel(next, font: Theme.Font.body(12), color: Theme.text)
        label.preferredMaxLayoutWidth = Self.textWidth - 28
        label.setAccessibilityLabel("What to try: \(next)")

        let row = NSStackView(views: [icon, label])
        row.orientation = .horizontal
        row.alignment = .firstBaseline
        row.spacing = 8
        return row
    }

    // MARK: Recording

    private func record() {
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized:
            beginTake()
        case .notDetermined:
            // Ask first. The host's recorder gives up half a second after it
            // is started, which is less time than the permission dialog takes.
            phase = .busy(
                title: "Hum a melody for \(trackName)",
                body: "macOS is asking whether Neon Studio may use the microphone.",
                detail: "Choose Allow in the dialog, and recording starts right after."
            )
            render()
            AVCaptureDevice.requestAccess(for: .audio) { [weak self] granted in
                DispatchQueue.main.async {
                    guard let self, !self.isDismissed else { return }
                    if granted {
                        self.beginTake()
                    } else {
                        self.showMicrophoneDenied()
                    }
                }
            }
        case .denied, .restricted:
            showMicrophoneDenied()
        @unknown default:
            beginTake()
        }
    }

    private func showMicrophoneDenied() {
        showProblem(
            title: "Neon Studio can't use the microphone",
            body: "Microphone access is switched off for Neon Studio, so there's nothing to record.",
            next: "Allow it under System Settings ▸ Privacy & Security ▸ Microphone, then press Try again.",
            retry: .microphoneSettings
        )
    }

    private func openMicrophoneSettings() {
        guard let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone") else { return }
        NSWorkspace.shared.open(url)
    }

    private func beginTake() {
        // The host reads Transport ▸ Count-In when the take starts. Set it for
        // this take and put it back afterwards so the sheet's choice never
        // silently changes the user's setting.
        previousCountIn = AppEnvironment.shared.countInBars
        AppEnvironment.shared.countInBars = countInBars
        discardTake = false
        takeURL = nil
        analysis = nil
        recordingStartedAt = Date()
        phase = .recording
        render()
        startElapsedTimer()

        host.recordTake(progressMessage: "Recording your hum for \(trackName)") { [weak self] url in
            guard let self else { return }
            self.restoreCountIn()
            self.stopElapsedTimer()
            guard !self.discardTake, !self.isDismissed else { return }
            guard let url, FileManager.default.fileExists(atPath: url.path) else {
                self.showProblem(
                    title: "Nothing was captured",
                    body: "The microphone didn't deliver any audio, so there's nothing to turn into notes.",
                    next: "Check that an input is chosen under System Settings ▸ Sound and that nothing else is recording, then press Try again.",
                    retry: .record
                )
                return
            }
            self.takeURL = url
            self.analyse(url)
        }
    }

    private func stopTake() {
        host.finishTake()
    }

    private func restoreCountIn() {
        guard let previous = previousCountIn else { return }
        previousCountIn = nil
        AppEnvironment.shared.countInBars = previous
    }

    private func startElapsedTimer() {
        stopElapsedTimer()
        let timer = Timer(timeInterval: 0.1, repeats: true) { [weak self] _ in
            self?.tickElapsed()
        }
        // Common modes, so the counter keeps moving while a button is held down.
        RunLoop.main.add(timer, forMode: .common)
        elapsedTimer = timer
        tickElapsed()
    }

    private func stopElapsedTimer() {
        elapsedTimer?.invalidate()
        elapsedTimer = nil
    }

    private func tickElapsed() {
        guard let started = recordingStartedAt, let elapsedLabel else { return }
        let total = Date().timeIntervalSince(started)
        let lead = Double(countInBars) * host.project.secondsPerBar
        if total < lead {
            let remaining = max(0, lead - total)
            elapsedLabel.stringValue = "0.0 s"
            elapsedLabel.setAccessibilityValue("Recording starts in \(Int(remaining.rounded(.up))) seconds")
            recordingHint?.stringValue = "Clicks first — \(Self.seconds(remaining)) to go. Start humming when they stop."
        } else {
            let recorded = total - lead
            elapsedLabel.stringValue = Self.seconds(recorded)
            elapsedLabel.setAccessibilityValue("\(Int(recorded.rounded())) seconds recorded")
            recordingHint?.stringValue = "Hum or sing now. Press Stop when you're done."
        }
    }

    // MARK: Analysis

    private func analyse(_ url: URL) {
        toolWatchdog?.invalidate()
        toolWatchdog = nil
        phase = .busy(
            title: "Hum a melody for \(trackName)",
            body: "Working out which notes you sang. This takes a few seconds.",
            detail: "Listening for pitches in \(url.lastPathComponent)…"
        )
        render()

        // The host reports a missing interpreter with an alert but never calls
        // back, so check first and keep the sheet honest.
        guard AppEnvironment.shared.pythonExecutable != nil else {
            let error = ToolError.missingExecutable("/usr/bin/python3")
            showProblem(
                title: "Couldn't turn the hum into notes",
                body: error.errorDescription ?? "Python isn't available.",
                next: error.recoverySuggestion ?? "Install Python, then press Try again.",
                retry: .analyse
            )
            return
        }

        var arguments: [String] = [
            host.store.toolURL("hum_to_melody.py").path,
            "--input", url.path,
            "--bpm", Self.bpmText(host.project.snapshot.bpm),
            "--start-bar", "\(Int(startBar))",
            "--track-id", trackId,
            "--snap", Self.toolSnap(from: host.project.snapshot.snap)
        ]
        if let keyCenter {
            if snapToKey {
                arguments.append(contentsOf: ["--key", keyCenter])
            } else {
                arguments.append("--no-key-snap")
            }
        }
        if let trackColor, !trackColor.isEmpty {
            arguments.append(contentsOf: ["--color", trackColor])
        }
        arguments.append(contentsOf: ["--format", "json"])

        toolFinished = false
        let startedAt = Date()
        host.runTool(
            name: "Hum to melody",
            progressMessage: "Turning your hum into notes",
            arguments: arguments
        ) { [weak self] result in
            guard let self else { return }
            self.toolFinished = true
            self.toolWatchdog?.invalidate()
            self.toolWatchdog = nil
            guard !self.isDismissed else { return }
            switch result {
            case .success(let value):
                self.handleToolOutput(value)
            case .failure(let error):
                if case ToolError.cancelled = error {
                    self.showProblem(
                        title: "Analysis was cancelled",
                        body: "The notes tool was stopped before it finished.",
                        next: "Press Try again to analyse the same take, or Record again for a fresh one.",
                        retry: .analyse
                    )
                } else {
                    let detail = (error as? LocalizedError)?.recoverySuggestion
                    self.showProblem(
                        title: "Couldn't turn the hum into notes",
                        body: error.localizedDescription,
                        next: detail ?? "Open Window ▸ Activity to see what the tool reported, then press Try again.",
                        retry: .analyse
                    )
                }
            }
        }

        // The host declines to start a tool while another one is running, and
        // says so in the status bar rather than calling back. Notice that here
        // so the sheet never spins forever.
        let watchdog = Timer(timeInterval: 1.5, repeats: false) { [weak self] _ in
            guard let self, !self.toolFinished, !self.isDismissed else { return }
            guard let current = StatusCenter.shared.current,
                  current.date >= startedAt,
                  current.severity == .warning || current.severity == .error else { return }
            self.showProblem(
                title: "The notes tool didn't start",
                body: current.message,
                next: "Wait for the other task to finish (or cancel it in the status bar), then press Try again.",
                retry: .analyse
            )
        }
        RunLoop.main.add(watchdog, forMode: .common)
        toolWatchdog = watchdog
    }

    private func handleToolOutput(_ result: ToolResult) {
        let json = result.lastJSONObject
        guard !json.isEmpty else {
            let error = ToolError.noJSON(name: "Hum to melody")
            showProblem(
                title: "Couldn't turn the hum into notes",
                body: error.errorDescription ?? "The tool finished but didn't return a result.",
                next: error.recoverySuggestion ?? "Press Try again.",
                retry: .analyse
            )
            return
        }
        if let ok = json["ok"] as? Bool, !ok {
            let reason = (json["error"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            showProblem(
                title: "Couldn't turn the hum into notes",
                body: reason.isEmpty ? "The tool reported a problem without saying what it was." : reason,
                next: "Press Try again to analyse the same take, or Record again for a fresh one.",
                retry: .analyse
            )
            return
        }

        let detected = json["detected"] as? [String: Any] ?? [:]
        let warnings = (json["warnings"] as? [Any] ?? []).compactMap { item -> String? in
            guard let text = item as? String else { return nil }
            let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
            return trimmed.isEmpty ? nil : trimmed
        }
        let rawNotes: [[String: Any]]
        if let list = json["notes"] as? [[String: Any]] {
            rawNotes = list
        } else {
            rawNotes = (json["notes"] as? [Any] ?? []).compactMap { $0 as? [String: Any] }
        }
        let notes = rawNotes.compactMap { raw -> HeardNote? in
            guard let midi = Self.number(raw["note"]), let beat = Self.number(raw["beat"]) else { return nil }
            let color = (raw["color"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? trackColor ?? ""
            return HeardNote(
                beat: max(0, beat),
                duration: max(0.0625, Self.number(raw["duration"]) ?? 0.5),
                midi: max(0, min(127, Int(midi.rounded()))),
                velocity: max(0.05, min(1, Self.number(raw["velocity"]) ?? 0.8)),
                color: color
            )
        }.sorted { $0.beat < $1.beat }

        let parsed = Analysis(
            notes: notes,
            voicedSeconds: Self.number(detected["voicedSeconds"]) ?? 0,
            segments: Int((Self.number(detected["segments"]) ?? 0).rounded()),
            keyUsed: (detected["keyUsed"] as? String).flatMap { $0.isEmpty ? nil : $0 },
            octaveShift: Int((Self.number(detected["octaveShift"]) ?? 0).rounded()),
            confidence: Self.number(detected["confidence"]) ?? 0,
            warnings: warnings
        )
        analysis = parsed

        guard !parsed.notes.isEmpty else {
            let why = parsed.warnings.first ?? "No sung notes were found in the take."
            showProblem(
                title: "No notes were heard",
                body: why,
                next: "Sing a little louder and closer to the microphone, one clear note at a time, then press Try again.",
                retry: .record
            )
            return
        }
        phase = .result
        render()
    }

    // MARK: Inserting

    private func insert(keepVoice: Bool) {
        guard let analysis, !analysis.notes.isEmpty else {
            showProblem(
                title: "Nothing to insert",
                body: "There are no notes from this take.",
                next: "Press Try again to record another take.",
                retry: .record
            )
            return
        }
        let trackId = self.trackId
        let trackName = self.trackName
        let newNotes = analysis.notes.map { heard in
            PianoNote(
                id: makeId("hum"),
                beat: heard.beat,
                duration: heard.duration,
                note: heard.midi,
                velocity: heard.velocity,
                color: heard.color,
                trackId: trackId
            )
        }
        let spanStart = newNotes.map(\.beat).min() ?? 0
        let spanEnd = newNotes.map { $0.beat + $0.duration }.max() ?? spanStart
        let overlaps: (PianoNote) -> Bool = { note in
            note.trackId == trackId && note.beat < spanEnd && note.beat + note.duration > spanStart
        }
        let replaced = (host.project.snapshot.notes ?? []).filter(overlaps).count

        let apply: (inout LocalProject) -> Void = { project in
            var kept = (project.snapshot.notes ?? []).filter { !overlaps($0) }
            kept.append(contentsOf: newNotes)
            project.snapshot.notes = kept
            project.snapshot.selectedTrackId = trackId
            project.updatedAt = nowISO()
        }

        var voiceTrackName: String?
        if keepVoice {
            guard let takeURL, FileManager.default.fileExists(atPath: takeURL.path) else {
                showProblem(
                    title: "The recording is missing",
                    body: "The take file can't be found any more, so your voice can't be added.",
                    next: "Press Insert notes to keep just the notes, or Try again to record another take.",
                    retry: .record
                )
                return
            }
            let voiceTrack = makeVoiceTrack(url: takeURL)
            voiceTrackName = voiceTrack.name
            // A new audio track has to reach the transport, which only
            // `replaceProject` does. Still one undo step.
            var next = host.project
            apply(&next)
            next.snapshot.tracks.append(voiceTrack)
            host.replaceProject(with: ProjectNormalizer.normalize(next), actionName: "Insert Hummed Melody")
        } else {
            host.edit("Insert Hummed Melody") { project in
                apply(&project)
                project = ProjectNormalizer.normalize(project)
            }
        }

        let count = newNotes.count
        var detail = "See them in the Notes tab."
        if replaced > 0 {
            detail += " Replaced \(replaced) note\(replaced == 1 ? "" : "s") that \(replaced == 1 ? "was" : "were") already in those bars."
        }
        if let voiceTrackName {
            detail += " Your voice is on a new track called “\(voiceTrackName)” at bar \(Int(startBar) + 1)."
        }
        StatusCenter.shared.success(
            "Added \(count) note\(count == 1 ? "" : "s") to \(trackName) from your hum. ⌘Z removes \(count == 1 ? "it" : "them").",
            detail: detail
        )
        close()
    }

    /// Mirrors what the window does for an imported sound, so the take behaves
    /// like any other audio track: one clip at the punch-in bar, sized from the
    /// file's real length.
    private func makeVoiceTrack(url: URL) -> Track {
        let id = makeId("vocal")
        let seconds = (try? AVAudioFile(forReading: url)).map { file in
            Double(file.length) / file.processingFormat.sampleRate
        } ?? 8
        let bars = max(0.25, (seconds / host.project.secondsPerBar * 4).rounded() / 4)
        let name = "Hummed take"
        return Track(
            id: id,
            name: name,
            kind: "audio",
            file: url.path,
            color: trackColor,
            gain: 0.86,
            pan: 0,
            steps: [],
            instrument: "Microphone",
            clips: [Clip(
                id: "\(id)-clip",
                name: name,
                startBar: max(0, startBar),
                bars: bars,
                lane: id,
                color: trackColor,
                type: "audio"
            )],
            effects: [
                Effect(id: "eq", name: "EQ", active: false, amount: 0.35),
                Effect(id: "comp", name: "Compressor", active: true, amount: 0.5),
                Effect(id: "delay", name: "Stereo Delay", active: false, amount: 0.34)
            ],
            sampleEdit: normalizeSampleEdit(nil)
        )
    }

    // MARK: Transitions

    private func reset() {
        toolWatchdog?.invalidate()
        toolWatchdog = nil
        takeURL = nil
        analysis = nil
        phase = .ready
        render()
    }

    private func showProblem(title: String, body: String, next: String, retry: Retry) {
        phase = .problem(title: title, body: body, next: next, retry: retry)
        render()
    }

    // MARK: Formatting helpers

    private static let pitchNames = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

    /// 60 → "C4", 69 → "A4".
    private static func noteName(_ midi: Int) -> String {
        let clamped = max(0, min(127, midi))
        let octave = clamped / 12 - 1
        return "\(pitchNames[clamped % 12])\(octave)"
    }

    /// "bar 5, beat 3" from an absolute beat count.
    private static func positionText(beat: Double) -> String {
        let bar = Int((beat / 4).rounded(.down))
        let inBar = beat - Double(bar) * 4 + 1
        return "bar \(bar + 1), beat \(trimmed(inBar))"
    }

    /// "½ beat", "1 beat", "1½ beats".
    private static func lengthText(_ beats: Double) -> String {
        var whole = Int(beats.rounded(.down))
        var quarters = Int(((beats - Double(whole)) * 4).rounded())
        if quarters == 4 {
            whole += 1
            quarters = 0
        }
        let fractions = ["", "¼", "½", "¾"]
        var text = whole > 0 ? "\(whole)" : ""
        text += fractions[quarters]
        if text.isEmpty {
            text = trimmed(beats)
        }
        let plural = beats > 1.0001 ? "beats" : "beat"
        return "\(text) \(plural)"
    }

    private static func seconds(_ value: Double) -> String {
        String(format: "%.1f s", max(0, value))
    }

    private static func trimmed(_ value: Double) -> String {
        if abs(value - value.rounded()) < 0.001 {
            return "\(Int(value.rounded()))"
        }
        return String(format: "%.2g", value)
    }

    private static func bpmText(_ bpm: Double) -> String {
        let value = bpm > 0 ? bpm : 120
        return trimmed(value)
    }

    /// The tool only knows 1/4, 1/8, 1/16, 1/32 and none. Coarser project grids
    /// fall back to the coarsest the tool offers; no project grid means 1/8.
    private static func toolSnap(from raw: String?) -> String {
        guard let raw, !raw.isEmpty else { return "1/8" }
        switch SnapValue.parse(raw) {
        case .none: return "none"
        case .bar, .half, .quarter: return "1/4"
        case .eighth: return "1/8"
        case .sixteenth: return "1/16"
        }
    }

    /// A finite number out of whatever JSON contained, or nil. Booleans are
    /// `NSNumber` too and must not read as 0 or 1.
    private static func number(_ value: Any?) -> Double? {
        guard let value else { return nil }
        if let number = value as? NSNumber {
            if CFGetTypeID(number) == CFBooleanGetTypeID() { return nil }
            return number.doubleValue.isFinite ? number.doubleValue : nil
        }
        if let double = value as? Double { return double.isFinite ? double : nil }
        if let int = value as? Int { return Double(int) }
        if let string = value as? String,
           let double = Double(string.trimmingCharacters(in: .whitespacesAndNewlines)),
           double.isFinite {
            return double
        }
        return nil
    }

    private static func wrappingLabel(_ text: String, font: NSFont, color: NSColor) -> NSTextField {
        let label = makeLabel(text, font: font, color: color)
        label.lineBreakMode = .byWordWrapping
        label.maximumNumberOfLines = 0
        label.usesSingleLineMode = false
        label.cell?.wraps = true
        label.cell?.isScrollable = false
        label.preferredMaxLayoutWidth = textWidth
        label.setContentCompressionResistancePriority(.required, for: .vertical)
        label.setContentHuggingPriority(.defaultLow, for: .horizontal)
        return label
    }
}

// MARK: - Sheet window

/// Escape closes the sheet from anywhere inside it, even when nothing has
/// keyboard focus.
private final class HumSheetWindow: NSWindow {
    var onCancel: (() -> Void)?

    /// A borderless window refuses key status by default, so every key press
    /// - Escape included - went to the document behind the sheet.
    override var canBecomeKey: Bool { true }

    /// Escape arrives as a plain key press when a popup or checkbox is first
    /// responder and nothing interprets it; route it to Cancel here.
    override func keyDown(with event: NSEvent) {
        if event.keyCode == 53 {
            cancelOperation(nil)
            return
        }
        super.keyDown(with: event)
    }

    override func cancelOperation(_ sender: Any?) {
        onCancel?()
    }
}
