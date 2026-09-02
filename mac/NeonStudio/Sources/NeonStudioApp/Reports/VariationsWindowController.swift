import AppKit
import AVFoundation
import NeonStudioKit

// MARK: - VariationsWindowController

/// "Here are three ways this could go — which do you like?"
///
/// The window asks `tools/variations.py` for three alternatives to one track's
/// part in one section, plays a short preview of each next to the original,
/// and lets the person choose by ear instead of by reading a diff. Choosing one
/// lands as a single undoable edit that touches only that track's part in that
/// section; nothing else in the song is replaced.
///
/// Everything the window does goes through `ToolHost`: it never reaches into
/// the document window, so it can be opened from anywhere that has a host.
public final class VariationsWindowController: NSWindowController, NSWindowDelegate, AVAudioPlayerDelegate {

    // MARK: Lifetime

    /// These windows belong to no document, so nothing else holds them. Without
    /// this they would deallocate the moment `present` returned.
    private static var openControllers: [VariationsWindowController] = []

    /// Opens the window immediately, then starts writing the alternatives.
    ///
    /// - Parameters:
    ///   - trackId: the track whose part is varied. Only this track changes.
    ///   - section: a section name ("Drop", "Second Drop"). May be empty, in
    ///     which case the bar range is used instead.
    ///   - startBar: 0-based first bar of the section, as clips store it.
    ///   - bars: how many bars the section lasts.
    public static func present(host: ToolHost, trackId: String, section: String, startBar: Double, bars: Double) {
        let controller = VariationsWindowController(
            host: host,
            trackId: trackId,
            section: section,
            startBar: startBar,
            bars: bars
        )
        openControllers.append(controller)
        controller.position(relativeTo: host.window)
        controller.showWindow(nil)
        controller.window?.makeKeyAndOrderFront(nil)
        controller.run()
    }

    // MARK: Types

    /// What the tool actually varied, which can differ from what was asked for
    /// when it resolved a track by name or a section by its clips.
    private struct Target {
        var trackId: String
        var trackName: String
        var section: String
        var startBar: Double
        var bars: Double
        var laneKind: String
    }

    private struct Variation {
        let id: String
        let label: String
        let description: String
        let projectURL: URL
        let previewURL: URL?
        let noteChanges: Int
        let stepChanges: Int
        let automationChanges: Int

        /// "6 notes", "3 steps · 2 automation points", or a plain statement
        /// that nothing differs — never a bare zero.
        var changeSummary: String {
            var parts: [String] = []
            if noteChanges > 0 { parts.append(pluralized(noteChanges, "note")) }
            if stepChanges > 0 { parts.append(pluralized(stepChanges, "step")) }
            if automationChanges > 0 { parts.append(pluralized(automationChanges, "automation point")) }
            return parts.isEmpty ? "Same as the original" : parts.joined(separator: " · ")
        }
    }

    private enum Playing {
        case nothing
        /// The song itself, looping the section through the host's transport.
        case original(since: Date)
        /// A rendered preview file, by row index.
        case variation(Int)
    }

    // MARK: State

    private weak var host: ToolHost?
    private let requestedTrackId: String
    private let requestedSection: String
    private let requestedStartBar: Double
    private let requestedBars: Double
    private let trackNameAtOpen: String
    private let songName: String

    /// Each "Try three more" bumps this so the tool draws different recipes.
    private var seed = 7
    private var isRunning = false
    /// Set after a section name could not be found, so the second attempt
    /// asks by bar numbers instead of by name.
    private var usesBarRange = false
    private var runStartedAt = Date()
    private var logIndexAtStart = 0
    private var tempExportURL: URL?

    private var target: Target?
    private var variations: [Variation] = []
    private var previewNote = ""

    private var player: AVAudioPlayer?
    private var playing: Playing = .nothing
    private var progressTimer: Timer?
    private var hostWindowObserver: NSObjectProtocol?

    // MARK: Views

    private let stateContainer = NSView()
    private var stateView: NSView?
    private let titleLabel: NSTextField
    private let subtitleLabel: MultilineLabel
    private let noteLabel: MultilineLabel
    private var moreButton: NSButton?
    private var closeButton: NSButton?
    private var originalRow: VariationRowView?
    private var rows: [VariationRowView] = []

    // MARK: Construction

    private init(host: ToolHost, trackId: String, section: String, startBar: Double, bars: Double) {
        self.host = host
        requestedTrackId = trackId
        requestedSection = section.trimmingCharacters(in: .whitespacesAndNewlines)
        requestedStartBar = max(0, startBar.isFinite ? startBar : 0)
        requestedBars = max(0, bars.isFinite ? bars : 0)
        trackNameAtOpen = host.project.snapshot.tracks.first { $0.id == trackId }?.name ?? trackId
        songName = host.project.name

        titleLabel = makeLabel("", font: Theme.Font.title(15), color: Theme.text)
        subtitleLabel = MultilineLabel(text: "", font: Theme.Font.body(12), color: Theme.muted)
        noteLabel = MultilineLabel(text: "", font: Theme.Font.caption(11), color: Theme.dim)

        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 660, height: 540),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.isReleasedWhenClosed = false
        window.contentMinSize = NSSize(width: 560, height: 420)
        window.minSize = NSSize(width: 560, height: 420)
        window.tabbingMode = .disallowed
        window.subtitle = songName
        super.init(window: window)

        window.delegate = self
        window.contentView = makeContentView()
        refreshHeader()
        observeHostWindow(host.window)
    }

    public required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    // MARK: Derived labels

    private var trackName: String { target?.trackName ?? trackNameAtOpen }
    private var sectionStartBar: Double { target?.startBar ?? requestedStartBar }
    private var sectionBars: Double { target?.bars ?? requestedBars }

    /// The section as a person would say it: the name when there is one,
    /// otherwise the bars.
    private var sectionLabel: String {
        if let target, !target.section.isEmpty { return target.section }
        if !requestedSection.isEmpty { return requestedSection }
        return barRangeLabel(start: requestedStartBar, bars: requestedBars)
    }

    /// "bars 25–32", counted from 1 the way the ruler shows them.
    private func barRangeLabel(start: Double, bars: Double) -> String {
        let first = Int(start.rounded()) + 1
        let last = max(first, Int((start + bars).rounded()))
        return first == last ? "bar \(first)" : "bars \(first)–\(last)"
    }

    /// The `--section` value: the name the caller gave, or the 0-based bar
    /// range the tool also understands ("24-32").
    private var sectionArgument: String {
        if !usesBarRange, !requestedSection.isEmpty { return requestedSection }
        let start = Int(requestedStartBar.rounded())
        let end = max(start + 1, Int((requestedStartBar + requestedBars).rounded()))
        return "\(start)-\(end)"
    }

    /// Length of the section in seconds at the song's tempo, for the original
    /// row's progress bar (the host loops the section but does not report a
    /// position).
    private var sectionSeconds: Double {
        let bpm = host?.project.snapshot.bpm ?? 120
        let safeBPM = (bpm.isFinite && bpm > 0) ? bpm : 120
        return max(0.25, sectionBars * 4 * 60 / safeBPM)
    }

    private func refreshHeader() {
        let range = barRangeLabel(start: sectionStartBar, bars: sectionBars)
        // The section name the tool was given may be a 0-based bar span
        // ("56-72"); people read the same bars as 57–72, so show those.
        let title = "Alternatives for \(trackName) in \(range)"
        window?.title = title
        titleLabel.stringValue = title
        titleLabel.setAccessibilityLabel(title)
        subtitleLabel.stringValue = "\(range.prefix(1).uppercased())\(range.dropFirst()) · Listen to each one, then choose. Nothing in the song changes until you press Use this."
        window?.contentView?.setAccessibilityLabel("\(title), \(songName)")
    }

    // MARK: Layout

    private func makeContentView() -> NSView {
        let root = ThemedBackgroundView { Theme.app }
        // A window resizes its content view with the autoresizing mask, so this
        // one view opts back in; everything inside it uses constraints.
        root.translatesAutoresizingMaskIntoConstraints = true
        root.autoresizingMask = [.width, .height]
        root.frame = NSRect(x: 0, y: 0, width: 660, height: 540)
        root.setAccessibilityRole(.group)

        let header = makeHeaderView()
        let headerSeparator = Controls.separator(vertical: false)
        let footerSeparator = Controls.separator(vertical: false)
        let footer = makeFooterView()

        stateContainer.translatesAutoresizingMaskIntoConstraints = false

        for subview in [header, headerSeparator, stateContainer, footerSeparator, footer] {
            subview.translatesAutoresizingMaskIntoConstraints = false
            root.addSubview(subview)
        }

        NSLayoutConstraint.activate([
            header.topAnchor.constraint(equalTo: root.topAnchor),
            header.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            header.trailingAnchor.constraint(equalTo: root.trailingAnchor),

            headerSeparator.topAnchor.constraint(equalTo: header.bottomAnchor),
            headerSeparator.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            headerSeparator.trailingAnchor.constraint(equalTo: root.trailingAnchor),

            stateContainer.topAnchor.constraint(equalTo: headerSeparator.bottomAnchor),
            stateContainer.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            stateContainer.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            stateContainer.bottomAnchor.constraint(equalTo: footerSeparator.topAnchor),

            footerSeparator.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            footerSeparator.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            footerSeparator.bottomAnchor.constraint(equalTo: footer.topAnchor),

            footer.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            footer.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            footer.bottomAnchor.constraint(equalTo: root.bottomAnchor)
        ])
        return root
    }

    private func makeHeaderView() -> NSView {
        let header = ThemedBackgroundView { Theme.panel }
        header.setAccessibilityRole(.group)
        header.setAccessibilityLabel("What these alternatives are for")

        let titleRow = NSStackView()
        titleRow.orientation = .horizontal
        titleRow.alignment = .centerY
        titleRow.spacing = 6
        titleRow.translatesAutoresizingMaskIntoConstraints = false
        titleRow.addArrangedSubview(titleLabel)
        if AppEnvironment.shared.explainsMusicTerms {
            titleRow.addArrangedSubview(Controls.glossary("Track", Glossary.long("Track")))
        }

        let stack = NSStackView()
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 4
        stack.translatesAutoresizingMaskIntoConstraints = false
        stack.addArrangedSubview(titleRow)
        stack.addArrangedSubview(subtitleLabel)
        subtitleLabel.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true

        header.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: header.leadingAnchor, constant: 20),
            stack.trailingAnchor.constraint(equalTo: header.trailingAnchor, constant: -20),
            stack.topAnchor.constraint(equalTo: header.topAnchor, constant: 14),
            stack.bottomAnchor.constraint(equalTo: header.bottomAnchor, constant: -14)
        ])
        return header
    }

    private func makeFooterView() -> NSView {
        let footer = ThemedBackgroundView { Theme.panel }
        footer.setAccessibilityRole(.group)
        footer.setAccessibilityLabel("Actions")

        noteLabel.setAccessibilityLabel("About the previews")
        noteLabel.setContentHuggingPriority(.defaultLow, for: .horizontal)
        // The caption gives way to the buttons only when the window is
        // narrower than both; otherwise it keeps its line instead of wrapping
        // one word per row.
        noteLabel.setContentCompressionResistancePriority(.defaultHigh, for: .horizontal)
        noteLabel.preferredMaxLayoutWidth = 340
        // MultilineLabel re-measures itself against its own bounds; without a
        // floor that loop settles at one word per line.
        noteLabel.widthAnchor.constraint(greaterThanOrEqualToConstant: 260).isActive = true

        let more = Controls.button(
            title: "Try three more",
            symbol: "arrow.clockwise",
            help: "Ask for three different alternatives. The ones shown now are replaced; the song itself is not touched.",
            action: { [weak self] in self?.requestMore() }
        )
        more.isEnabled = false
        moreButton = more

        let close = Controls.button(
            title: "Close",
            help: "Close this window without changing the song. Esc does the same.",
            keyEquivalent: "\u{1b}",
            keyEquivalentModifiers: [],
            action: { [weak self] in self?.close() }
        )
        closeButton = close

        for button in [more, close] {
            button.setContentHuggingPriority(.required, for: .horizontal)
            button.setContentCompressionResistancePriority(.required, for: .horizontal)
        }
        let stack = NSStackView(views: [noteLabel, more, close])
        stack.orientation = .horizontal
        stack.alignment = .centerY
        stack.spacing = 10
        stack.translatesAutoresizingMaskIntoConstraints = false

        footer.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: footer.leadingAnchor, constant: 20),
            stack.trailingAnchor.constraint(equalTo: footer.trailingAnchor, constant: -16),
            stack.topAnchor.constraint(equalTo: footer.topAnchor, constant: 10),
            stack.bottomAnchor.constraint(equalTo: footer.bottomAnchor, constant: -10)
        ])
        return footer
    }

    // MARK: States

    private func show(_ view: NSView) {
        stateView?.removeFromSuperview()
        stateView = view
        view.translatesAutoresizingMaskIntoConstraints = false
        stateContainer.addSubview(view)
        NSLayoutConstraint.activate([
            view.leadingAnchor.constraint(equalTo: stateContainer.leadingAnchor),
            view.trailingAnchor.constraint(equalTo: stateContainer.trailingAnchor),
            view.topAnchor.constraint(equalTo: stateContainer.topAnchor),
            view.bottomAnchor.constraint(equalTo: stateContainer.bottomAnchor)
        ])
    }

    private func showLoading(_ message: String) {
        let spinner = NSProgressIndicator()
        spinner.style = .spinning
        spinner.controlSize = .regular
        spinner.isIndeterminate = true
        spinner.translatesAutoresizingMaskIntoConstraints = false
        spinner.setAccessibilityLabel("Working")
        spinner.startAnimation(nil)

        let label = MultilineLabel(text: message, font: Theme.Font.body(13), color: Theme.muted)
        label.alignment = .center
        label.setAccessibilityLabel(message)

        let stack = NSStackView(views: [spinner, label])
        stack.orientation = .vertical
        stack.alignment = .centerX
        stack.spacing = 12
        stack.translatesAutoresizingMaskIntoConstraints = false
        label.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true

        let container = NSView()
        container.translatesAutoresizingMaskIntoConstraints = false
        container.setAccessibilityRole(.group)
        container.setAccessibilityLabel("Working")
        container.setAccessibilityHelp(message)
        container.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.centerXAnchor.constraint(equalTo: container.centerXAnchor),
            stack.centerYAnchor.constraint(equalTo: container.centerYAnchor),
            stack.widthAnchor.constraint(lessThanOrEqualToConstant: 380),
            stack.leadingAnchor.constraint(greaterThanOrEqualTo: container.leadingAnchor, constant: 20),
            stack.trailingAnchor.constraint(lessThanOrEqualTo: container.trailingAnchor, constant: -20)
        ])
        show(container)
        StatusCenter.shared.info(message)
    }

    private func showEmpty(symbol: String, title: String, body: String) {
        let empty = EmptyStateView(
            symbol: symbol,
            title: title,
            body: body,
            actionTitle: "Close",
            action: { [weak self] in self?.close() }
        )
        show(empty)
        noteLabel.stringValue = ""
    }

    private func showList() {
        rows = []
        originalRow = nil

        let scrollView = NSScrollView()
        scrollView.hasVerticalScroller = true
        scrollView.hasHorizontalScroller = false
        scrollView.autohidesScrollers = true
        scrollView.drawsBackground = true
        scrollView.backgroundColor = Theme.app
        scrollView.borderType = .noBorder
        scrollView.translatesAutoresizingMaskIntoConstraints = false
        scrollView.setAccessibilityLabel("Alternatives")

        let container = FlippedContainerView()
        container.translatesAutoresizingMaskIntoConstraints = false

        let stack = NSStackView()
        stack.orientation = .vertical
        stack.alignment = .width
        stack.spacing = 10
        stack.translatesAutoresizingMaskIntoConstraints = false
        container.addSubview(stack)

        let range = barRangeLabel(start: sectionStartBar, bars: sectionBars)
        let original = VariationRowView(configuration: .init(
            title: "The original",
            description: "\(trackName) as it is in the song right now, \(range). Play it to compare fairly.",
            chip: "In the song now",
            playHelp: AppEnvironment.shared.help(
                "Play \(range) of the song as it is now, on repeat, so you can compare. Press again to stop. Space does the same while this row is selected.",
                term: "Loop"
            ),
            useTitle: nil,
            useHelp: nil,
            canPlay: true,
            cannotPlayReason: nil
        ))
        original.onTogglePlay = { [weak self] in self?.toggleOriginal() }
        stack.addArrangedSubview(original)
        originalRow = original

        for (index, variation) in variations.enumerated() {
            let row = VariationRowView(configuration: .init(
                title: variation.label,
                description: variation.description,
                chip: variation.changeSummary,
                playHelp: "Play a short preview of ‘\(variation.label)’. Only one preview plays at a time; press again to stop. Space does the same while this row is selected.",
                useTitle: "Use this",
                useHelp: AppEnvironment.shared.help(
                    "Put ‘\(variation.label)’ into the song. Only \(trackName)'s part in \(sectionLabel) changes, and ⌘Z brings the original back. Return does the same while this row is selected.",
                    term: "Track"
                ),
                canPlay: variation.previewURL != nil,
                cannotPlayReason: "No preview was rendered for this one. Press Try three more to render again, or use it and listen in the song."
            ))
            row.onTogglePlay = { [weak self] in self?.toggleVariation(at: index) }
            row.onUse = { [weak self] in self?.use(index) }
            stack.addArrangedSubview(row)
            rows.append(row)
        }

        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: container.leadingAnchor, constant: 16),
            stack.trailingAnchor.constraint(equalTo: container.trailingAnchor, constant: -16),
            stack.topAnchor.constraint(equalTo: container.topAnchor, constant: 14),
            stack.bottomAnchor.constraint(equalTo: container.bottomAnchor, constant: -16)
        ])

        scrollView.documentView = container
        let clip = scrollView.contentView
        NSLayoutConstraint.activate([
            container.leadingAnchor.constraint(equalTo: clip.leadingAnchor),
            container.trailingAnchor.constraint(equalTo: clip.trailingAnchor),
            container.topAnchor.constraint(equalTo: clip.topAnchor)
        ])

        show(scrollView)
        noteLabel.stringValue = previewNote
        noteLabel.toolTip = previewNote.isEmpty ? nil : previewNote
        window?.recalculateKeyViewLoop()
        if let first = rows.first {
            window?.makeFirstResponder(first)
        }
    }

    // MARK: Running the tool

    private func run() {
        guard !isRunning else { return }
        guard let host else {
            hostIsGone()
            return
        }
        if requestedSection.isEmpty, requestedBars <= 0 {
            showEmpty(
                symbol: "rectangle.dashed",
                title: "Which part of the song?",
                body: "Pick a section — a clip, or a range of bars — for \(trackName) first, then ask for alternatives again."
            )
            return
        }

        stopAll()
        isRunning = true
        moreButton?.isEnabled = false
        removeTempExport()
        showLoading("Writing three alternatives and rendering short previews… about 20 seconds.")

        let temp: URL
        do {
            temp = try host.exportProjectToTemporaryFile()
        } catch {
            isRunning = false
            moreButton?.isEnabled = true
            showEmpty(
                symbol: "exclamationmark.triangle",
                title: "Couldn't hand the song to the helper tool.",
                body: "\(error.localizedDescription) Save the song with ⌘S, then press Try three more."
            )
            return
        }
        tempExportURL = temp

        let store = host.store
        let outputDirectory = store.rootURL
            .appendingPathComponent("songlab", isDirectory: true)
            .appendingPathComponent("projects", isDirectory: true)
            .appendingPathComponent(host.project.id, isDirectory: true)
            .appendingPathComponent("variations", isDirectory: true)

        let arguments = [
            store.toolURL("variations.py").path,
            "--root", store.rootURL.path,
            "--project", temp.path,
            "--track-id", requestedTrackId,
            "--section", sectionArgument,
            "--count", "3",
            "--seed", "\(seed)",
            "--output-dir", outputDirectory.path,
            "--format", "json"
        ]

        runStartedAt = Date()
        logIndexAtStart = StatusCenter.shared.log.count
        host.runTool(
            name: "Alternatives",
            progressMessage: "Writing three alternatives for \(trackName)…",
            arguments: arguments
        ) { [weak self] result in
            self?.finishRun(result)
        }

        // `runTool` refuses without ever calling back when Python is missing or
        // another task is already running, and it says so on the status bar
        // before returning. Anything but a progress entry since we asked means
        // the tool never started, and a spinner nobody will ever stop is worse
        // than an honest message.
        if isRunning,
           let last = StatusCenter.shared.log.last,
           last.date >= runStartedAt,
           last.severity == .warning || last.severity == .error {
            isRunning = false
            moreButton?.isEnabled = true
            removeTempExport()
            let detail = last.detail.map { " \($0)" } ?? ""
            showEmpty(
                symbol: "exclamationmark.triangle",
                title: "Couldn't start writing alternatives.",
                body: "\(last.message).\(detail) Once that is sorted out, press Try three more."
            )
        }
    }

    private func requestMore() {
        guard !isRunning else { return }
        seed += 1
        run()
    }

    private func finishRun(_ result: Result<ToolResult, Error>) {
        isRunning = false
        moreButton?.isEnabled = true
        removeTempExport()
        guard let window, window.isVisible else { return }

        switch result {
        case .failure(let error):
            if case ToolError.cancelled = error {
                showEmpty(
                    symbol: "xmark.circle",
                    title: "Cancelled.",
                    body: "No alternatives were written and the song is unchanged. Press Try three more whenever you're ready."
                )
                return
            }
            let reported = toolReportedError()
            // The tool could not find the section by name. The caller also
            // gave us its bars, so ask again that way before giving up.
            if !usesBarRange, requestedBars > 0, !requestedSection.isEmpty,
               let reported, reported.localizedCaseInsensitiveContains("section") {
                usesBarRange = true
                StatusCenter.shared.info(
                    "Couldn't find a section called ‘\(requestedSection)’. Trying \(barRangeLabel(start: requestedStartBar, bars: requestedBars)) instead."
                )
                run()
                return
            }
            showEmpty(
                symbol: "exclamationmark.triangle",
                title: "Couldn't write alternatives for \(trackName).",
                body: failureBody(reported: reported, error: error)
            )

        case .success(let toolResult):
            let json = toolResult.lastJSONObject
            guard json["ok"] as? Bool == true else {
                let reason = (json["error"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                showEmpty(
                    symbol: "exclamationmark.triangle",
                    title: "Couldn't write alternatives for \(trackName).",
                    body: failureBody(reported: reason.isEmpty ? nil : reason, error: nil)
                )
                return
            }
            applyResult(json)
        }
    }

    private func applyResult(_ json: [String: Any]) {
        if let targetJSON = json["target"] as? [String: Any] {
            let resolvedId = (targetJSON["trackId"] as? String) ?? ""
            let resolvedName = (targetJSON["trackName"] as? String) ?? ""
            target = Target(
                trackId: resolvedId.isEmpty ? requestedTrackId : resolvedId,
                trackName: resolvedName.isEmpty ? trackNameAtOpen : resolvedName,
                section: (targetJSON["section"] as? String) ?? requestedSection,
                startBar: doubleValue(targetJSON["startBar"]) ?? requestedStartBar,
                bars: doubleValue(targetJSON["bars"]) ?? requestedBars,
                laneKind: (targetJSON["laneKind"] as? String) ?? ""
            )
        }
        previewNote = ((json["previewNote"] as? String) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)

        variations = ((json["variations"] as? [Any]) ?? []).enumerated().compactMap { index, item -> Variation? in
            guard let dict = item as? [String: Any],
                  let projectPath = dict["project"] as? String, !projectPath.isEmpty else { return nil }
            let changes = (dict["changes"] as? [String: Any]) ?? [:]
            let previewPath = (dict["preview"] as? String) ?? ""
            let label = ((dict["label"] as? String) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            return Variation(
                id: (dict["id"] as? String) ?? "v\(index + 1)",
                label: label.isEmpty ? "Alternative \(index + 1)" : label,
                description: ((dict["description"] as? String) ?? "").trimmingCharacters(in: .whitespacesAndNewlines),
                projectURL: URL(fileURLWithPath: projectPath),
                previewURL: previewPath.isEmpty ? nil : URL(fileURLWithPath: previewPath),
                noteChanges: ReportBuilder.intValue(changes["notes"]),
                stepChanges: ReportBuilder.intValue(changes["steps"]),
                automationChanges: ReportBuilder.intValue(changes["automation"])
            )
        }

        refreshHeader()

        guard !variations.isEmpty else {
            showEmpty(
                symbol: "music.quarternote.3",
                title: "Nothing to vary yet.",
                body: "This track has no notes or steps in \(sectionLabel) to vary. Draw some first, or pick a different track."
            )
            return
        }
        showList()
        StatusCenter.shared.success(
            "\(variations.count) alternative\(variations.count == 1 ? "" : "s") ready for \(trackName). Listen, then choose — nothing changes until you press Use this."
        )
    }

    /// The tool prints `{"ok": false, "error": …}` to stdout and exits 1, so the
    /// host hands back only the exit code and an empty stderr. The line itself
    /// was streamed into the Activity log as progress, and that is where the
    /// real reason can still be found.
    private func toolReportedError() -> String? {
        let log = StatusCenter.shared.log
        let start = min(max(0, logIndexAtStart), log.count)
        for entry in log[start...].reversed() where entry.severity == .progress {
            guard let brace = entry.message.firstIndex(of: "{") else { continue }
            let fragment = String(entry.message[brace...])
            guard fragment.contains("\"ok\": false") || fragment.contains("\"ok\":false") else { continue }
            if let data = fragment.data(using: .utf8),
               let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let error = object["error"] as? String, !error.isEmpty {
                return error
            }
            // The line was cut at 120 characters; salvage what is there.
            if let range = fragment.range(of: "\"error\": \"") ?? fragment.range(of: "\"error\":\"") {
                var text = String(fragment[range.upperBound...])
                if let end = text.range(of: "\"}") {
                    text = String(text[..<end.lowerBound])
                } else if !text.isEmpty {
                    text += "…"
                }
                if !text.isEmpty { return text }
            }
        }
        return nil
    }

    private func failureBody(reported: String?, error: Error?) -> String {
        var sentences: [String] = []
        if let reported, !reported.isEmpty {
            sentences.append(reported.hasSuffix(".") ? reported : "\(reported).")
        } else if let error {
            sentences.append(error.localizedDescription)
            if let suggestion = (error as? LocalizedError)?.recoverySuggestion, !suggestion.isEmpty {
                sentences.append(suggestion)
            }
        }
        sentences.append("Check that \(trackName) has notes, steps, or automation in \(sectionLabel), or pick a different track or section, then press Try three more.")
        return sentences.joined(separator: " ")
    }

    private func hostIsGone() {
        stopAll()
        StatusCenter.shared.warning("The song these alternatives were for has been closed, so there is nothing to change.")
        close()
    }

    // MARK: Playback

    private func toggleOriginal() {
        if case .original = playing {
            stopAll()
            return
        }
        stopAll()
        guard let host else {
            hostIsGone()
            return
        }
        host.playSection(startBar: sectionStartBar, bars: sectionBars)
        playing = .original(since: Date())
        originalRow?.setPlaying(true)
        originalRow?.progress = 0
        startTimer()
    }

    private func toggleVariation(at index: Int) {
        if case .variation(let current) = playing, current == index {
            stopAll()
            return
        }
        stopAll()
        guard index < variations.count, index < rows.count else { return }
        let variation = variations[index]
        guard let url = variation.previewURL else {
            rows[index].setPlaying(false)
            StatusCenter.shared.warning(
                "No preview was rendered for ‘\(variation.label)’.",
                detail: "Press Try three more to render again."
            )
            return
        }
        do {
            let newPlayer = try AVAudioPlayer(contentsOf: url)
            newPlayer.delegate = self
            newPlayer.prepareToPlay()
            guard newPlayer.play() else {
                throw NSError(
                    domain: "studio.neon.variations",
                    code: 1,
                    userInfo: [NSLocalizedDescriptionKey: "The audio system refused to start playback."]
                )
            }
            player = newPlayer
            playing = .variation(index)
            rows[index].setPlaying(true)
            rows[index].progress = 0
            startTimer()
        } catch {
            rows[index].setPlaying(false)
            StatusCenter.shared.warning(
                "Couldn't play the preview for ‘\(variation.label)’.",
                detail: "\(url.lastPathComponent): \(error.localizedDescription) Press Try three more to render it again."
            )
        }
    }

    private func stopAll() {
        switch playing {
        case .nothing:
            break
        case .original:
            host?.stopPlayback()
            originalRow?.setPlaying(false)
            originalRow?.progress = 0
        case .variation(let index):
            player?.stop()
            player = nil
            if index < rows.count {
                rows[index].setPlaying(false)
                rows[index].progress = 0
            }
        }
        playing = .nothing
        stopTimer()
    }

    private func startTimer() {
        guard progressTimer == nil else { return }
        let timer = Timer(timeInterval: 1.0 / 30.0, repeats: true) { [weak self] _ in
            self?.tick()
        }
        RunLoop.main.add(timer, forMode: .common)
        progressTimer = timer
    }

    private func stopTimer() {
        progressTimer?.invalidate()
        progressTimer = nil
    }

    private func tick() {
        switch playing {
        case .nothing:
            stopTimer()
        case .original(let since):
            let elapsed = Date().timeIntervalSince(since)
            // Give the transport a moment to start; after that, if it is no
            // longer playing (Stop in the main window, or nothing to play),
            // the row must not keep claiming that it is.
            if elapsed > 0.5, !(host?.isPlaying ?? false) {
                originalRow?.setPlaying(false)
                originalRow?.progress = 0
                playing = .nothing
                stopTimer()
                return
            }
            let duration = sectionSeconds
            originalRow?.progress = elapsed.truncatingRemainder(dividingBy: duration) / duration
        case .variation(let index):
            guard let player, player.duration > 0, index < rows.count else { return }
            rows[index].progress = player.currentTime / player.duration
        }
    }

    private func finishVariationPlayback() {
        guard case .variation(let index) = playing else { return }
        player = nil
        if index < rows.count {
            rows[index].setPlaying(false)
            rows[index].progress = 0
        }
        playing = .nothing
        stopTimer()
    }

    public func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        DispatchQueue.main.async { [weak self] in
            guard let self, player === self.player else { return }
            self.finishVariationPlayback()
        }
    }

    public func audioPlayerDecodeErrorDidOccur(_ player: AVAudioPlayer, error: Error?) {
        DispatchQueue.main.async { [weak self] in
            guard let self, player === self.player else { return }
            self.finishVariationPlayback()
            StatusCenter.shared.warning("The preview stopped early.", detail: error?.localizedDescription)
        }
    }

    // MARK: Choosing one

    /// Copies ONLY the target track's part out of the variant project and lands
    /// it as one undoable edit. The variant differs from the song on that one
    /// lane by construction, but the user chose a lane, not a project, so the
    /// rest of the song is never replaced — and the track keeps its `file`,
    /// which the tool cleared in the variant so the preview would synthesise.
    private func use(_ index: Int) {
        guard index < variations.count else { return }
        let variation = variations[index]
        guard let host else {
            hostIsGone()
            return
        }
        stopAll()

        guard let loaded = host.store.loadProject(from: variation.projectURL) else {
            StatusCenter.shared.failure(
                "Couldn't read ‘\(variation.label)’",
                error: ProjectStoreError.unreadableProjectFile(variation.projectURL),
                window: window
            )
            return
        }
        let variant = ProjectNormalizer.normalize(loaded)

        let current = host.project
        let targetId: String = {
            if let id = target?.trackId, current.snapshot.tracks.contains(where: { $0.id == id }) { return id }
            return requestedTrackId
        }()
        guard current.snapshot.tracks.contains(where: { $0.id == targetId }) else {
            StatusCenter.shared.warning(
                "\(trackName) is no longer in the song.",
                detail: "The track was removed after these alternatives were written. Close this window and ask again."
            )
            return
        }
        guard let variantTrack = variant.snapshot.tracks.first(where: { $0.id == targetId }) else {
            StatusCenter.shared.warning(
                "‘\(variation.label)’ doesn't contain \(trackName).",
                detail: "The alternative's file doesn't have that track. Press Try three more to write fresh ones."
            )
            return
        }

        let variantNotes = (variant.snapshot.notes ?? []).filter { $0.trackId == targetId }

        // Automation: the track's own lanes always come across. A track of kind
        // "automation" with no lanes of its own hosts the song's macro lanes,
        // and the tool varies whichever of those cross the section; those have
        // other owners, so they are matched by id and taken only when changed.
        let currentLanesById = Dictionary(
            (current.snapshot.automationLanes ?? []).map { ($0.id, $0) },
            uniquingKeysWith: { first, _ in first }
        )
        let hostsMacroLanes = (variantTrack.kind ?? "").lowercased() == "automation"
        let variantLanes = (variant.snapshot.automationLanes ?? []).filter { lane in
            if lane.trackId == targetId { return true }
            guard hostsMacroLanes, let existing = currentLanesById[lane.id] else { return false }
            return existing != lane
        }
        let replacedLaneIds = Set(variantLanes.map(\.id))

        host.edit("Use Alternative: \(variation.label)") { project in
            guard let trackIndex = project.snapshot.tracks.firstIndex(where: { $0.id == targetId }) else { return }
            var track = project.snapshot.tracks[trackIndex]
            track.steps = variantTrack.steps
            track.clips = variantTrack.clips
            track.effects = variantTrack.effects
            // `track.file` is deliberately left alone: the real project keeps its stem.
            project.snapshot.tracks[trackIndex] = track

            var notes = (project.snapshot.notes ?? []).filter { $0.trackId != targetId }
            notes.append(contentsOf: variantNotes)
            project.snapshot.notes = notes

            var lanes = (project.snapshot.automationLanes ?? []).filter {
                $0.trackId != targetId && !replacedLaneIds.contains($0.id)
            }
            lanes.append(contentsOf: variantLanes)
            project.snapshot.automationLanes = lanes
        }

        // `updatedAt` is bumped by every edit, so compare everything but that.
        var before = current
        var after = host.project
        before.updatedAt = ""
        after.updatedAt = ""
        guard before != after else {
            StatusCenter.shared.info(
                "‘\(variation.label)’ is the same as what's already in the song for \(trackName), so nothing changed."
            )
            return
        }

        close()
        StatusCenter.shared.success("Used ‘\(variation.label)’ for \(trackName). ⌘Z brings the original back.")
    }

    // MARK: Cleanup

    private func removeTempExport() {
        guard let tempExportURL else { return }
        self.tempExportURL = nil
        try? FileManager.default.removeItem(at: tempExportURL)
    }

    private func observeHostWindow(_ hostWindow: NSWindow?) {
        guard let hostWindow else { return }
        hostWindowObserver = NotificationCenter.default.addObserver(
            forName: NSWindow.willCloseNotification,
            object: hostWindow,
            queue: .main
        ) { [weak self] _ in
            guard let self, let window = self.window, window.isVisible else { return }
            // The song went away; nothing chosen here could land anywhere.
            self.close()
        }
    }

    public func windowWillClose(_ notification: Notification) {
        stopAll()
        removeTempExport()
        if let hostWindowObserver {
            NotificationCenter.default.removeObserver(hostWindowObserver)
        }
        hostWindowObserver = nil
        // Dropping the last reference synchronously would deallocate `self`
        // while AppKit is still inside this delegate call.
        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            VariationsWindowController.openControllers.removeAll { $0 === self }
        }
    }

    // MARK: Placement

    private func position(relativeTo parent: NSWindow?) {
        guard let window else { return }
        guard let parent else {
            window.center()
            return
        }
        var frame = window.frame
        frame.origin = NSPoint(
            x: parent.frame.midX - frame.width / 2,
            y: parent.frame.midY - frame.height / 2
        )
        if let screen = parent.screen ?? NSScreen.main {
            let visible = screen.visibleFrame
            if visible.width > frame.width {
                frame.origin.x = min(max(frame.origin.x, visible.minX + 8), visible.maxX - frame.width - 8)
            }
            if visible.height > frame.height {
                frame.origin.y = min(max(frame.origin.y, visible.minY + 8), visible.maxY - frame.height - 8)
            }
        }
        window.setFrame(frame, display: false)
    }

    // MARK: JSON helpers

    /// `nil` for anything that isn't a finite number, including booleans, which
    /// arrive from JSON as `NSNumber`.
    private func doubleValue(_ value: Any?) -> Double? {
        guard let value else { return nil }
        if let number = value as? NSNumber {
            if CFGetTypeID(number) == CFBooleanGetTypeID() { return nil }
            return number.doubleValue.isFinite ? number.doubleValue : nil
        }
        if let string = value as? String,
           let parsed = Double(string.trimmingCharacters(in: .whitespacesAndNewlines)),
           parsed.isFinite {
            return parsed
        }
        return nil
    }
}

// MARK: - Row

/// One option in the list: a Play toggle with a progress bar, the label and
/// description, a chip saying what changed, and (for alternatives) Use this.
///
/// The row itself takes keyboard focus so Space and Return work without first
/// tabbing to the exact button, and it shows the standard focus ring so it is
/// obvious which row will respond.
private final class VariationRowView: NSView {

    struct Configuration {
        var title: String
        var description: String
        var chip: String
        var playHelp: String
        var useTitle: String?
        var useHelp: String?
        var canPlay: Bool
        var cannotPlayReason: String?
    }

    var onTogglePlay: (() -> Void)?
    var onUse: (() -> Void)?

    private let playButton: NSButton
    private var useButton: NSButton?
    private let progressBar = NSProgressIndicator()
    private let titleLabel: NSTextField
    private let descriptionLabel: MultilineLabel
    private let chip: ChipView
    private let canPlay: Bool

    /// 0…1 through the preview. Only meaningful while playing.
    var progress: Double = 0 {
        didSet {
            let clamped = progress.isFinite ? max(0, min(1, progress)) : 0
            progressBar.doubleValue = clamped
            progressBar.setAccessibilityValue("\(Int((clamped * 100).rounded())) percent")
        }
    }

    init(configuration: Configuration) {
        canPlay = configuration.canPlay
        titleLabel = makeLabel(configuration.title, font: Theme.Font.emphasis(13), color: Theme.text)
        descriptionLabel = MultilineLabel(text: configuration.description, font: Theme.Font.body(12), color: Theme.muted)
        chip = ChipView(text: configuration.chip)

        var toggleHandler: (() -> Void)?
        playButton = Controls.toggle(
            title: "Play",
            symbol: "play.fill",
            help: configuration.canPlay ? configuration.playHelp : (configuration.cannotPlayReason ?? configuration.playHelp),
            action: { _ in toggleHandler?() }
        )
        super.init(frame: .zero)
        toggleHandler = { [weak self] in self?.onTogglePlay?() }

        translatesAutoresizingMaskIntoConstraints = false
        wantsLayer = true
        layer?.cornerRadius = Theme.Metric.cornerRadius
        layer?.borderWidth = 1

        playButton.isEnabled = configuration.canPlay
        playButton.widthAnchor.constraint(greaterThanOrEqualToConstant: 84).isActive = true
        playButton.setContentHuggingPriority(.required, for: .horizontal)
        playButton.setContentCompressionResistancePriority(.required, for: .horizontal)

        titleLabel.setContentCompressionResistancePriority(.defaultHigh, for: .horizontal)
        titleLabel.toolTip = configuration.title

        progressBar.style = .bar
        progressBar.isIndeterminate = false
        progressBar.minValue = 0
        progressBar.maxValue = 1
        progressBar.doubleValue = 0
        progressBar.controlSize = .small
        progressBar.translatesAutoresizingMaskIntoConstraints = false
        progressBar.setAccessibilityLabel("How far through the preview")
        progressBar.toolTip = "How far through the preview playback is."
        progressBar.setContentHuggingPriority(.defaultLow, for: .horizontal)
        progressBar.widthAnchor.constraint(greaterThanOrEqualToConstant: 120).isActive = true

        let bottomRow = NSStackView(views: [chip, progressBar])
        bottomRow.orientation = .horizontal
        bottomRow.alignment = .centerY
        bottomRow.spacing = 10
        bottomRow.translatesAutoresizingMaskIntoConstraints = false

        let textStack = NSStackView(views: [titleLabel, descriptionLabel, bottomRow])
        textStack.orientation = .vertical
        textStack.alignment = .leading
        textStack.spacing = 4
        textStack.setCustomSpacing(8, after: descriptionLabel)
        textStack.translatesAutoresizingMaskIntoConstraints = false
        textStack.setContentHuggingPriority(.defaultLow, for: .horizontal)
        descriptionLabel.widthAnchor.constraint(equalTo: textStack.widthAnchor).isActive = true
        bottomRow.widthAnchor.constraint(equalTo: textStack.widthAnchor).isActive = true

        var views: [NSView] = [playButton, textStack]
        if let useTitle = configuration.useTitle {
            var useHandler: (() -> Void)?
            let button = Controls.button(
                title: useTitle,
                symbol: "checkmark",
                help: configuration.useHelp ?? "Put this alternative into the song. ⌘Z brings the original back.",
                style: .primary,
                action: { useHandler?() }
            )
            useHandler = { [weak self] in self?.onUse?() }
            button.setContentHuggingPriority(.required, for: .horizontal)
            button.setContentCompressionResistancePriority(.required, for: .horizontal)
            useButton = button
            views.append(button)
        }

        let row = NSStackView(views: views)
        row.orientation = .horizontal
        row.alignment = .centerY
        row.spacing = 14
        row.translatesAutoresizingMaskIntoConstraints = false
        addSubview(row)

        NSLayoutConstraint.activate([
            row.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 14),
            row.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -14),
            row.topAnchor.constraint(equalTo: topAnchor, constant: 12),
            row.bottomAnchor.constraint(equalTo: bottomAnchor, constant: -12)
        ])

        setAccessibilityRole(.group)
        setAccessibilityLabel(configuration.title)
        setAccessibilityHelp("\(configuration.description) \(configuration.chip).")
        toolTip = configuration.description
        refreshColors()
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    func setPlaying(_ isPlaying: Bool) {
        playButton.state = isPlaying ? .on : .off
        playButton.title = isPlaying ? "Stop" : "Play"
        playButton.image = NSImage(
            systemSymbolName: isPlaying ? "stop.fill" : "play.fill",
            accessibilityDescription: isPlaying ? "Stop" : "Play"
        )
        playButton.imagePosition = .imageLeading
        playButton.setAccessibilityLabel(isPlaying ? "Stop" : "Play")
        if !isPlaying { progress = 0 }
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
            self.layer?.borderColor = Theme.subtleStroke.cgColor
        }
    }

    // MARK: Keyboard and focus

    override var acceptsFirstResponder: Bool { true }

    override func becomeFirstResponder() -> Bool {
        needsDisplay = true
        return super.becomeFirstResponder()
    }

    override func resignFirstResponder() -> Bool {
        needsDisplay = true
        return super.resignFirstResponder()
    }

    override func drawFocusRingMask() {
        NSBezierPath(
            roundedRect: bounds,
            xRadius: Theme.Metric.cornerRadius,
            yRadius: Theme.Metric.cornerRadius
        ).fill()
    }

    override var focusRingMaskBounds: NSRect { bounds }

    override func mouseDown(with event: NSEvent) {
        window?.makeFirstResponder(self)
        super.mouseDown(with: event)
    }

    override func keyDown(with event: NSEvent) {
        guard let scalar = event.charactersIgnoringModifiers?.unicodeScalars.first else {
            super.keyDown(with: event)
            return
        }
        switch Int(scalar.value) {
        case 32: // Space
            if canPlay {
                onTogglePlay?()
            } else {
                NSSound.beep()
            }
        case 13, 3: // Return, Enter
            if let onUse {
                onUse()
            } else {
                super.keyDown(with: event)
            }
        default:
            super.keyDown(with: event)
        }
    }
}

// MARK: - Chip

/// A small rounded tag such as "6 notes". Real text, so it can be read, copied
/// by VoiceOver, and resized with the system font.
private final class ChipView: NSView {
    private let label: NSTextField

    init(text: String) {
        label = makeLabel(text, font: Theme.Font.caption(11), color: Theme.muted)
        super.init(frame: .zero)
        translatesAutoresizingMaskIntoConstraints = false
        wantsLayer = true
        layer?.cornerRadius = Theme.Metric.smallCornerRadius

        label.setContentCompressionResistancePriority(.required, for: .horizontal)
        label.setContentHuggingPriority(.required, for: .horizontal)
        addSubview(label)
        NSLayoutConstraint.activate([
            label.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 8),
            label.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -8),
            label.topAnchor.constraint(equalTo: topAnchor, constant: 3),
            label.bottomAnchor.constraint(equalTo: bottomAnchor, constant: -3)
        ])
        setContentHuggingPriority(.required, for: .horizontal)
        setContentCompressionResistancePriority(.required, for: .horizontal)
        setAccessibilityRole(.staticText)
        setAccessibilityLabel(text)
        toolTip = "What this alternative changes: \(text)."
        refreshColors()
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    override func viewDidChangeEffectiveAppearance() {
        super.viewDidChangeEffectiveAppearance()
        refreshColors()
    }

    private func refreshColors() {
        effectiveAppearance.performAsCurrentDrawingAppearance { [weak self] in
            self?.layer?.backgroundColor = Theme.panelRaised.cgColor
        }
    }
}

// MARK: - Private helpers

/// A document view whose origin is at the top, so a scroll view shows short
/// content from the first row instead of pinning it to the bottom.
private final class FlippedContainerView: NSView {
    override var isFlipped: Bool { true }
}

/// A selectable label that wraps to the width it is given. `NSTextField` only
/// wraps under Auto Layout once it knows its width, which is what
/// `preferredMaxLayoutWidth` is for.
private final class MultilineLabel: NSTextField {

    init(text: String, font: NSFont, color: NSColor) {
        super.init(frame: .zero)
        stringValue = text
        self.font = font
        textColor = color
        isEditable = false
        isSelectable = true
        isBordered = false
        isBezeled = false
        drawsBackground = false
        usesSingleLineMode = false
        maximumNumberOfLines = 0
        lineBreakMode = .byWordWrapping
        cell?.wraps = true
        cell?.isScrollable = false
        translatesAutoresizingMaskIntoConstraints = false
        setContentHuggingPriority(.defaultLow, for: .horizontal)
        setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        setContentCompressionResistancePriority(.required, for: .vertical)
        setAccessibilityRole(.staticText)
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    override func layout() {
        if abs(preferredMaxLayoutWidth - bounds.width) > 0.5 {
            preferredMaxLayoutWidth = bounds.width
            invalidateIntrinsicContentSize()
        }
        super.layout()
    }
}

private func pluralized(_ count: Int, _ noun: String) -> String {
    count == 1 ? "1 \(noun)" : "\(count) \(noun)s"
}
