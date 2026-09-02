import AppKit
import NeonStudioKit

/// The human sound check.
///
/// `does_this_sound_good.py` measures a render. This window asks the person.
/// Each musical section of the song plays on repeat while two or three plain
/// questions are put to whoever is listening — "Does the drop land?" — and the
/// answers go to `listening_session.py`, which turns them into production steps
/// in the song's build plan. The same steps are added to the project's recipe
/// as a single undoable edit, so ⌘Z takes them back out.
///
/// The window talks to the song only through `ToolHost`: it never reaches into
/// the document window, and the document never has to know it exists.
public final class ListeningSessionWindowController: NSWindowController, NSWindowDelegate {

    // MARK: Model

    private struct Question {
        let id: String
        let text: String
        /// Empty for a free-text question.
        let options: [String]
        let isFreeText: Bool
    }

    private struct Section {
        let id: String
        let label: String
        /// `nil` when the tool could not work out where the section sits in
        /// the song; the whole song is played instead.
        let startBar: Double?
        let bars: Double?
        let questions: [Question]

        var range: (start: Double, bars: Double)? {
            guard let startBar, let bars, bars > 0 else { return nil }
            return (max(0, startBar), bars)
        }
    }

    private enum Answer {
        case option(String)
        case text(String)
    }

    /// A failure the tool reported in its own words, plus the next thing to try.
    private struct SessionError: LocalizedError {
        let message: String
        let nextStep: String
        var errorDescription: String? { message }
        var recoverySuggestion: String? { "\(message)\n\n\(nextStep)" }
    }

    // MARK: Presenting

    /// Nothing else owns a listening session, so the open ones are kept here.
    private static var openControllers: [ListeningSessionWindowController] = []

    /// Opens the session for `host`'s song. If one is already open for the
    /// same song it is brought forward instead of starting a second one that
    /// would fight the first over playback.
    public static func present(host: ToolHost, projectId: String, specPath: URL?) {
        if let existing = openControllers.first(where: { $0.host === host }), existing.window != nil {
            existing.window?.makeKeyAndOrderFront(nil)
            return
        }
        let controller = ListeningSessionWindowController(host: host, projectId: projectId, specPath: specPath)
        openControllers.append(controller)
        controller.position(relativeTo: host.window)
        controller.showWindow(nil)
        controller.window?.makeKeyAndOrderFront(nil)
        controller.loadQuestions()
    }

    // MARK: State

    private weak var host: ToolHost?
    private let projectId: String
    private let specPath: URL?
    private let toolDisplayName = "Listen with me"

    private var sections: [Section] = []
    private var pageIndex = 0
    /// Keyed by question id. A question with no entry is simply not sent.
    private var answers: [String: Answer] = [:]
    private var isApplying = false
    private var isDiscardConfirmed = false
    private var hasFinished = false

    /// The free-text field on the current page, read directly when the page
    /// changes so a note the user typed but never committed is not lost.
    private var currentTextField: NSTextField?
    private var currentTextQuestionId: String?

    private var playbackSyncTimer: Timer?

    // MARK: Views

    private let titleLabel = makeLabel("", font: Theme.Font.title(17), color: Theme.text)
    private let progressLabel = makeLabel("", font: Theme.Font.caption(12), color: Theme.muted)
    private var playToggle: NSButton?

    private let bodyContainer = NSView()
    private var loadingView: NSView?
    private var loadingLabel: NSTextField?
    private var emptyState: EmptyStateView?
    private let scrollView = NSScrollView()
    private let questionStack = NSStackView()

    private var cancelButton: NSButton?
    private var backButton: NSButton?
    private var nextButton: NSButton?
    private var finishButton: NSButton?
    private let footerSpinner = NSProgressIndicator()

    // MARK: Construction

    private init(host: ToolHost, projectId: String, specPath: URL?) {
        self.host = host
        self.projectId = projectId
        self.specPath = specPath

        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 640, height: 520),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.title = "Listen with me"
        window.subtitle = host.project.name
        window.isReleasedWhenClosed = false
        window.minSize = NSSize(width: 520, height: 420)
        window.contentMinSize = NSSize(width: 520, height: 420)
        window.tabbingMode = .disallowed
        super.init(window: window)
        window.delegate = self
        window.contentView = makeContentView()
    }

    public required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    private func makeContentView() -> NSView {
        let root = ThemedBackgroundView { Theme.app }
        // A window resizes its content view with the autoresizing mask, so this
        // one view opts back in; everything inside it uses constraints.
        root.translatesAutoresizingMaskIntoConstraints = true
        root.autoresizingMask = [.width, .height]
        root.frame = NSRect(x: 0, y: 0, width: 640, height: 520)
        root.setAccessibilityRole(.group)
        root.setAccessibilityLabel("Listen with me")
        root.setAccessibilityHelp("Plays each part of the song and asks what you think of it.")

        let header = makeHeaderView()
        let headerSeparator = Controls.separator(vertical: false)
        let body = makeBodyView()
        let footerSeparator = Controls.separator(vertical: false)
        let footer = makeFooterView()

        for subview in [header, headerSeparator, body, footerSeparator, footer] {
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

            body.topAnchor.constraint(equalTo: headerSeparator.bottomAnchor),
            body.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            body.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            body.bottomAnchor.constraint(equalTo: footerSeparator.topAnchor),

            footerSeparator.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            footerSeparator.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            footerSeparator.bottomAnchor.constraint(equalTo: footer.topAnchor),

            footer.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            footer.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            footer.bottomAnchor.constraint(equalTo: root.bottomAnchor)
        ])
        return root
    }

    // MARK: Header

    private func makeHeaderView() -> NSView {
        let header = ThemedBackgroundView { Theme.panel }
        header.setAccessibilityRole(.group)
        header.setAccessibilityLabel("Which part of the song is playing")

        titleLabel.stringValue = "Listen with me"
        titleLabel.toolTip = AppEnvironment.shared.help(
            "The part of the song these questions are about, and which bars it covers.",
            term: "Bar"
        )
        titleLabel.setAccessibilityLabel("Part of the song")
        titleLabel.lineBreakMode = .byTruncatingTail
        titleLabel.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)

        progressLabel.stringValue = "Getting ready…"
        progressLabel.toolTip = "How far through the song you are."
        progressLabel.setAccessibilityLabel("Progress")

        let textStack = NSStackView(views: [titleLabel, progressLabel])
        textStack.orientation = .vertical
        textStack.alignment = .leading
        textStack.spacing = 3
        textStack.translatesAutoresizingMaskIntoConstraints = false

        let toggle = Controls.toggle(
            title: "Play this part",
            symbol: "play.fill",
            help: AppEnvironment.shared.help(
                "Plays just this part of the song, over and over, while you answer. Press it again to stop.",
                term: "Loop"
            ),
            style: .primary,
            action: { [weak self] isOn in
                self?.setPlaying(isOn)
            }
        )
        toggle.controlSize = .large
        toggle.font = Theme.Font.emphasis(14)
        toggle.isEnabled = false
        toggle.setContentHuggingPriority(.required, for: .horizontal)
        toggle.setContentCompressionResistancePriority(.required, for: .horizontal)
        playToggle = toggle

        let row = NSStackView(views: [textStack, toggle])
        row.orientation = .horizontal
        row.alignment = .centerY
        row.spacing = 16
        row.translatesAutoresizingMaskIntoConstraints = false

        header.addSubview(row)
        NSLayoutConstraint.activate([
            row.leadingAnchor.constraint(equalTo: header.leadingAnchor, constant: 20),
            row.trailingAnchor.constraint(equalTo: header.trailingAnchor, constant: -20),
            row.topAnchor.constraint(equalTo: header.topAnchor, constant: 16),
            row.bottomAnchor.constraint(equalTo: header.bottomAnchor, constant: -16),
            toggle.heightAnchor.constraint(greaterThanOrEqualToConstant: 32)
        ])
        return header
    }

    // MARK: Body

    private func makeBodyView() -> NSView {
        bodyContainer.translatesAutoresizingMaskIntoConstraints = false

        let loading = makeLoadingView()
        loadingView = loading

        scrollView.hasVerticalScroller = true
        scrollView.hasHorizontalScroller = false
        scrollView.autohidesScrollers = true
        scrollView.drawsBackground = true
        scrollView.backgroundColor = Theme.app
        scrollView.borderType = .noBorder
        scrollView.translatesAutoresizingMaskIntoConstraints = false
        scrollView.isHidden = true

        questionStack.orientation = .vertical
        questionStack.alignment = .width
        questionStack.distribution = .fill
        questionStack.spacing = 18
        questionStack.translatesAutoresizingMaskIntoConstraints = false
        questionStack.setAccessibilityRole(.group)
        questionStack.setAccessibilityLabel("Questions about this part")

        let document = FlippedDocumentView()
        document.translatesAutoresizingMaskIntoConstraints = false
        document.addSubview(questionStack)
        scrollView.documentView = document

        bodyContainer.addSubview(loading)
        bodyContainer.addSubview(scrollView)

        NSLayoutConstraint.activate([
            loading.leadingAnchor.constraint(equalTo: bodyContainer.leadingAnchor),
            loading.trailingAnchor.constraint(equalTo: bodyContainer.trailingAnchor),
            loading.topAnchor.constraint(equalTo: bodyContainer.topAnchor),
            loading.bottomAnchor.constraint(equalTo: bodyContainer.bottomAnchor),

            scrollView.leadingAnchor.constraint(equalTo: bodyContainer.leadingAnchor),
            scrollView.trailingAnchor.constraint(equalTo: bodyContainer.trailingAnchor),
            scrollView.topAnchor.constraint(equalTo: bodyContainer.topAnchor),
            scrollView.bottomAnchor.constraint(equalTo: bodyContainer.bottomAnchor),

            document.leadingAnchor.constraint(equalTo: scrollView.contentView.leadingAnchor),
            document.trailingAnchor.constraint(equalTo: scrollView.contentView.trailingAnchor),
            document.topAnchor.constraint(equalTo: scrollView.contentView.topAnchor),
            document.widthAnchor.constraint(equalTo: scrollView.contentView.widthAnchor),

            questionStack.leadingAnchor.constraint(equalTo: document.leadingAnchor, constant: 20),
            questionStack.trailingAnchor.constraint(equalTo: document.trailingAnchor, constant: -20),
            questionStack.topAnchor.constraint(equalTo: document.topAnchor, constant: 18),
            questionStack.bottomAnchor.constraint(equalTo: document.bottomAnchor, constant: -18)
        ])
        return bodyContainer
    }

    private func makeLoadingView() -> NSView {
        let spinner = NSProgressIndicator()
        spinner.style = .spinning
        spinner.controlSize = .regular
        spinner.isIndeterminate = true
        spinner.translatesAutoresizingMaskIntoConstraints = false
        spinner.startAnimation(nil)

        let label = makeLabel("Finding the parts of your song…", font: Theme.Font.body(13), color: Theme.muted)
        label.alignment = .center
        label.setAccessibilityLabel("Status")
        loadingLabel = label

        let stack = NSStackView(views: [spinner, label])
        stack.orientation = .vertical
        stack.alignment = .centerX
        stack.spacing = 10
        stack.translatesAutoresizingMaskIntoConstraints = false

        let container = NSView()
        container.translatesAutoresizingMaskIntoConstraints = false
        container.setAccessibilityRole(.group)
        container.setAccessibilityLabel("Getting ready")
        container.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.centerXAnchor.constraint(equalTo: container.centerXAnchor),
            stack.centerYAnchor.constraint(equalTo: container.centerYAnchor),
            stack.leadingAnchor.constraint(greaterThanOrEqualTo: container.leadingAnchor, constant: 20),
            stack.trailingAnchor.constraint(lessThanOrEqualTo: container.trailingAnchor, constant: -20)
        ])
        return container
    }

    // MARK: Footer

    private func makeFooterView() -> NSView {
        let footer = ThemedBackgroundView { Theme.app }
        footer.setAccessibilityRole(.group)
        footer.setAccessibilityLabel("Move between parts of the song")

        let cancel = Controls.button(
            title: "Cancel",
            help: "Stop playing and close without changing the song. Any answers you've given are thrown away.",
            style: .quiet,
            keyEquivalent: "\u{1b}",
            keyEquivalentModifiers: [],
            action: { [weak self] in self?.requestClose() }
        )
        cancel.controlSize = .regular
        cancelButton = cancel

        let back = Controls.button(
            title: "Back",
            help: "Go back to the previous part of the song. Your answers are kept.",
            action: { [weak self] in self?.goBack() }
        )
        back.isEnabled = false
        backButton = back

        let next = Controls.button(
            title: "Next",
            help: "Move on to the next part of the song. Leaving a question blank is fine.",
            style: .primary,
            action: { [weak self] in self?.goNext() }
        )
        next.isHidden = true
        nextButton = next

        let finish = Controls.button(
            title: "Finish",
            help: AppEnvironment.shared.help(
                "Turns your answers into steps to do in the song's recipe. Undo (⌘Z) takes them back out.",
                term: "Recipe"
            ),
            style: .primary,
            action: { [weak self] in self?.finish() }
        )
        finish.isHidden = true
        finishButton = finish

        footerSpinner.style = .spinning
        footerSpinner.controlSize = .small
        footerSpinner.isIndeterminate = true
        footerSpinner.isDisplayedWhenStopped = false
        footerSpinner.translatesAutoresizingMaskIntoConstraints = false
        footerSpinner.setAccessibilityLabel("Working")

        let spacer = NSView()
        spacer.translatesAutoresizingMaskIntoConstraints = false
        spacer.setContentHuggingPriority(.defaultLow, for: .horizontal)

        let stack = NSStackView(views: [cancel, spacer, footerSpinner, back, next, finish])
        stack.orientation = .horizontal
        stack.alignment = .centerY
        stack.spacing = 8
        stack.translatesAutoresizingMaskIntoConstraints = false

        footer.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: footer.leadingAnchor, constant: Theme.Metric.panelPadding),
            stack.trailingAnchor.constraint(equalTo: footer.trailingAnchor, constant: -Theme.Metric.panelPadding),
            stack.topAnchor.constraint(equalTo: footer.topAnchor, constant: Theme.Metric.gutter),
            stack.bottomAnchor.constraint(equalTo: footer.bottomAnchor, constant: -Theme.Metric.gutter)
        ])
        return footer
    }

    // MARK: Loading the questions

    private func loadQuestions() {
        guard let host else {
            hostWentAway()
            return
        }
        loadingLabel?.stringValue = "Finding the parts of your song…"

        let projectURL: URL
        do {
            projectURL = try host.exportProjectToTemporaryFile()
        } catch {
            StatusCenter.shared.failure("Couldn't hand the song to the listening tool", error: error, window: window)
            close()
            return
        }

        // `--root`, `--project` and `--format` belong to the top-level parser,
        // and argparse rejects them once the subcommand has been named.
        let arguments = [
            host.store.toolURL("listening_session.py").path,
            "--root", host.store.rootURL.path,
            "--project", projectURL.path,
            "--format", "json",
            "questions"
        ]
        host.runTool(
            name: toolDisplayName,
            progressMessage: "Finding the parts of your song…",
            arguments: arguments
        ) { [weak self] result in
            try? FileManager.default.removeItem(at: projectURL)
            guard let self else { return }
            switch result {
            case .failure:
                // The host has already shown the error and how to fix it.
                self.close()
            case .success(let toolResult):
                self.receiveQuestions(toolResult.lastJSONObject)
            }
        }
    }

    private func receiveQuestions(_ json: [String: Any]) {
        guard !json.isEmpty else {
            StatusCenter.shared.failure(
                "\(toolDisplayName) didn't return any questions",
                error: ToolError.noJSON(name: toolDisplayName),
                window: window
            )
            close()
            return
        }
        guard JSONValue.bool(json["ok"]) else {
            let message = JSONValue.string(json["error"])
            StatusCenter.shared.failure(
                "\(toolDisplayName) couldn't read the song",
                error: SessionError(
                    message: message.isEmpty ? "The tool didn't say what went wrong." : message,
                    nextStep: "Save the song (⌘S) and try Listen with me again. If it keeps happening, open Window ▸ Activity for the tool's output."
                ),
                window: window
            )
            close()
            return
        }

        sections = JSONValue.objects(json["sections"]).compactMap(parseSection)
        guard !sections.isEmpty else {
            showEmptyState()
            return
        }
        showWizard()
        showPage(0, autoPlay: true)
    }

    private func parseSection(_ dict: [String: Any]) -> Section? {
        let id = JSONValue.string(dict["id"])
        let label = JSONValue.string(dict["label"])
        guard !id.isEmpty else { return nil }
        let questions = JSONValue.objects(dict["questions"]).compactMap(parseQuestion)
        guard !questions.isEmpty else { return nil }
        return Section(
            id: id,
            label: label.isEmpty ? id.capitalized : label,
            startBar: JSONValue.double(dict["startBar"]),
            bars: JSONValue.double(dict["bars"]),
            questions: questions
        )
    }

    private func parseQuestion(_ dict: [String: Any]) -> Question? {
        let id = JSONValue.string(dict["id"])
        let text = JSONValue.string(dict["text"])
        guard !id.isEmpty, !text.isEmpty else { return nil }
        let isFreeText = JSONValue.bool(dict["freeText"])
        let options = isFreeText ? [] : JSONValue.strings(dict["options"])
        if !isFreeText, options.isEmpty { return nil }
        return Question(id: id, text: text, options: options, isFreeText: isFreeText)
    }

    // MARK: Body states

    private func showEmptyState() {
        loadingView?.isHidden = true
        scrollView.isHidden = true
        titleLabel.stringValue = "Nothing to listen to yet"
        progressLabel.stringValue = ""
        playToggle?.isEnabled = false
        backButton?.isHidden = true
        nextButton?.isHidden = true
        finishButton?.isHidden = true
        cancelButton?.title = "Close"
        cancelButton?.setAccessibilityLabel("Close")
        cancelButton?.toolTip = "Close this window. Nothing in the song changes."

        if emptyState == nil {
            let empty = EmptyStateView(
                symbol: "ear",
                title: "Nothing to listen to yet",
                body: "This project has no sections. Build or arrange something first — an intro, a drop, a chorus — then come back and Neon Studio will play each one and ask what you think.",
                actionTitle: "Close",
                action: { [weak self] in self?.requestClose() }
            )
            bodyContainer.addSubview(empty)
            NSLayoutConstraint.activate([
                empty.leadingAnchor.constraint(equalTo: bodyContainer.leadingAnchor),
                empty.trailingAnchor.constraint(equalTo: bodyContainer.trailingAnchor),
                empty.topAnchor.constraint(equalTo: bodyContainer.topAnchor),
                empty.bottomAnchor.constraint(equalTo: bodyContainer.bottomAnchor)
            ])
            emptyState = empty
        }
        emptyState?.isHidden = false
        StatusCenter.shared.info("Nothing to listen to yet — this project has no sections. Build or arrange something first.")
    }

    private func showWizard() {
        loadingView?.isHidden = true
        emptyState?.isHidden = true
        scrollView.isHidden = false
        playToggle?.isEnabled = true
        backButton?.isHidden = false
        startPlaybackSync()
    }

    // MARK: Pages

    private var currentSection: Section? {
        guard pageIndex >= 0, pageIndex < sections.count else { return nil }
        return sections[pageIndex]
    }

    private func showPage(_ index: Int, autoPlay: Bool) {
        guard index >= 0, index < sections.count else { return }
        commitCurrentPageText()
        // Ending editing before the field is torn down keeps the window's field
        // editor from pointing at a view that is about to disappear.
        window?.makeFirstResponder(nil)
        pageIndex = index
        let section = sections[index]

        titleLabel.stringValue = headerText(for: section)
        titleLabel.setAccessibilityValue(titleLabel.stringValue)
        progressLabel.stringValue = "Section \(index + 1) of \(sections.count)"
        progressLabel.setAccessibilityValue(progressLabel.stringValue)
        updatePlayTooltip(for: section)

        rebuildQuestions(for: section)
        scrollView.contentView.scroll(to: .zero)
        scrollView.reflectScrolledClipView(scrollView.contentView)

        let isLast = index == sections.count - 1
        backButton?.isEnabled = index > 0
        nextButton?.isHidden = isLast
        finishButton?.isHidden = !isLast
        // Only one button may answer Return, and a hidden one must not.
        nextButton?.keyEquivalent = isLast ? "" : "\r"
        finishButton?.keyEquivalent = isLast ? "\r" : ""

        if autoPlay {
            setPlaying(true)
        }
    }

    private func goBack() {
        guard !isApplying, pageIndex > 0 else { return }
        showPage(pageIndex - 1, autoPlay: true)
    }

    private func goNext() {
        guard !isApplying, pageIndex + 1 < sections.count else { return }
        showPage(pageIndex + 1, autoPlay: true)
    }

    private func headerText(for section: Section) -> String {
        if let range = section.range {
            let first = Int(range.start.rounded(.down)) + 1
            let last = max(first, Int((range.start + range.bars).rounded(.up)))
            return "\(section.label) — bars \(first)–\(last)"
        }
        return "\(section.label) — whole song"
    }

    private func updatePlayTooltip(for section: Section) {
        let base: String
        if section.range != nil {
            base = "Plays just \(section.label), over and over, while you answer. Press it again to stop."
        } else {
            base = "Neon Studio couldn't tell where \(section.label) sits in the song, so this plays the whole song on repeat. Press it again to stop."
        }
        playToggle?.toolTip = AppEnvironment.shared.help(base, term: "Loop")
        playToggle?.setAccessibilityHelp(base)
    }

    // MARK: Questions

    private func rebuildQuestions(for section: Section) {
        for view in questionStack.arrangedSubviews {
            questionStack.removeArrangedSubview(view)
            view.removeFromSuperview()
        }
        currentTextField = nil
        currentTextQuestionId = nil

        for question in section.questions {
            let row = question.isFreeText
                ? makeFreeTextRow(question, section: section)
                : makeChoiceRow(question, section: section)
            questionStack.addArrangedSubview(row)
            row.widthAnchor.constraint(equalTo: questionStack.widthAnchor).isActive = true
        }
    }

    private func makeChoiceRow(_ question: Question, section: Section) -> NSView {
        let label = WrappingQuestionLabel(text: question.text, font: Theme.Font.emphasis(13), color: Theme.text)
        label.setAccessibilityLabel(question.text)

        let control = AnswerSegmentedControl()
        control.segmentCount = question.options.count
        control.trackingMode = .selectOne
        control.segmentStyle = .rounded
        control.segmentDistribution = .fit
        control.controlSize = .regular
        control.font = Theme.Font.body(12)
        control.translatesAutoresizingMaskIntoConstraints = false
        for (index, option) in question.options.enumerated() {
            control.setLabel(option, forSegment: index)
            control.setToolTip("Answer “\(option)”. Click it again to clear your answer.", forSegment: index)
        }
        control.selectedSegment = -1
        if case .option(let chosen)? = answers[question.id],
           let index = question.options.firstIndex(of: chosen) {
            control.selectedSegment = index
        }
        control.toolTip = "Click the answer that matches what you hear in \(section.label). Click it again to clear it. Leaving a question blank is fine."
        control.setAccessibilityLabel(question.text)
        control.setAccessibilityHelp("Pick one. Click the chosen answer again to clear it, or leave it blank to skip.")
        control.setContentHuggingPriority(.required, for: .horizontal)
        control.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        control.target = control
        control.action = #selector(AnswerSegmentedControl.invoke)
        control.handler = { [weak self, weak control] index in
            guard let self, let control else { return }
            guard index >= 0, index < question.options.count else {
                self.answers[question.id] = nil
                return
            }
            let option = question.options[index]
            if case .option(let previous)? = self.answers[question.id], previous == option {
                // Clicking the chosen answer again clears it: a segmented
                // control offers no other way to un-answer.
                control.selectedSegment = -1
                self.answers[question.id] = nil
            } else {
                self.answers[question.id] = .option(option)
            }
        }

        let row = NSStackView(views: [label, control])
        row.orientation = .vertical
        row.alignment = .leading
        row.spacing = 6
        row.translatesAutoresizingMaskIntoConstraints = false
        row.setAccessibilityRole(.group)
        row.setAccessibilityLabel(question.text)
        label.widthAnchor.constraint(equalTo: row.widthAnchor).isActive = true
        control.widthAnchor.constraint(lessThanOrEqualTo: row.widthAnchor).isActive = true
        return row
    }

    private func makeFreeTextRow(_ question: Question, section: Section) -> NSView {
        let label = WrappingQuestionLabel(text: question.text, font: Theme.Font.emphasis(13), color: Theme.text)
        label.setAccessibilityLabel(question.text)

        var initial = ""
        if case .text(let stored)? = answers[question.id] {
            initial = stored
        }
        let field = CommitTextField(string: initial)
        field.placeholderString = "Anything you noticed in \(section.label) — a few words is plenty (optional)"
        field.font = Theme.Font.body(13)
        field.controlSize = .regular
        field.usesSingleLineMode = true
        field.lineBreakMode = .byTruncatingTail
        field.toolTip = "Anything you noticed that the questions didn't ask about. It's kept with the song's notes, and words like “muddy” or “too empty” become steps too. Optional."
        field.setAccessibilityLabel(question.text)
        field.setAccessibilityHelp("Type a note about this part of the song, or leave it empty.")
        field.commitHandler = { [weak self] text in
            self?.storeText(text, for: question.id)
        }
        currentTextField = field
        currentTextQuestionId = question.id

        let row = NSStackView(views: [label, field])
        row.orientation = .vertical
        row.alignment = .leading
        row.spacing = 6
        row.translatesAutoresizingMaskIntoConstraints = false
        row.setAccessibilityRole(.group)
        row.setAccessibilityLabel(question.text)
        label.widthAnchor.constraint(equalTo: row.widthAnchor).isActive = true
        field.widthAnchor.constraint(equalTo: row.widthAnchor).isActive = true
        return row
    }

    private func storeText(_ text: String, for questionId: String) {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        answers[questionId] = trimmed.isEmpty ? nil : .text(trimmed)
    }

    private func commitCurrentPageText() {
        guard let field = currentTextField, let questionId = currentTextQuestionId else { return }
        storeText(field.stringValue, for: questionId)
    }

    // MARK: Playback

    private func setPlaying(_ on: Bool) {
        guard let host else {
            hostWentAway()
            return
        }
        if on, let section = currentSection {
            let range = playRange(for: section)
            host.playSection(startBar: range.start, bars: range.bars)
        } else {
            host.stopPlayback()
        }
        // Shown as playing straight away; the sync timer corrects the button
        // within half a second if the host found nothing to play.
        updatePlayToggle(playing: on && (host.isPlaying || on))
    }

    private func playRange(for section: Section) -> (start: Double, bars: Double) {
        if let range = section.range { return range }
        return (0, wholeSongBars())
    }

    private func wholeSongBars() -> Double {
        guard let host else { return 8 }
        var end: Double = 0
        for track in host.project.snapshot.tracks {
            for clip in track.clips ?? [] {
                end = max(end, (clip.startBar ?? 0) + (clip.bars ?? 0))
            }
        }
        if end <= 0 {
            end = host.project.snapshot.loopEndBar ?? 8
        }
        return max(1, end)
    }

    private func updatePlayToggle(playing: Bool) {
        guard let toggle = playToggle else { return }
        toggle.state = playing ? .on : .off
        toggle.title = playing ? "Stop" : "Play this part"
        toggle.image = NSImage(
            systemSymbolName: playing ? "stop.fill" : "play.fill",
            accessibilityDescription: toggle.title
        )
        toggle.setAccessibilityLabel(toggle.title)
    }

    private func startPlaybackSync() {
        playbackSyncTimer?.invalidate()
        playbackSyncTimer = Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { [weak self] _ in
            self?.syncPlayToggle()
        }
    }

    /// Keeps the button honest when playback stops somewhere else — the user
    /// pressed Space in the song's window, or the section had nothing to play.
    private func syncPlayToggle() {
        guard let toggle = playToggle, let host else { return }
        let playing = host.isPlaying
        if (toggle.state == .on) != playing {
            updatePlayToggle(playing: playing)
        }
    }

    // MARK: Finishing

    private var answerPayload: [[String: Any]] {
        var payload: [[String: Any]] = []
        for section in sections {
            for question in section.questions {
                switch answers[question.id] {
                case .option(let option)?:
                    payload.append(["questionId": question.id, "option": option])
                case .text(let text)?:
                    payload.append(["questionId": question.id, "text": text])
                case nil:
                    continue
                }
            }
        }
        return payload
    }

    private func finish() {
        guard !isApplying else { return }
        commitCurrentPageText()
        window?.makeFirstResponder(nil)
        commitCurrentPageText()

        let payload = answerPayload
        guard !payload.isEmpty else {
            askForAtLeastOneAnswer()
            return
        }
        guard let host else {
            hostWentAway()
            return
        }

        setPlaying(false)
        setApplying(true)

        let answersURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("listening-answers-\(timestampForId()).json")
        do {
            let data = try JSONSerialization.data(withJSONObject: ["answers": payload], options: [.prettyPrinted])
            try data.write(to: answersURL, options: [.atomic])
        } catch {
            setApplying(false)
            StatusCenter.shared.failure("Couldn't save your answers", error: error, window: window)
            return
        }

        let projectURL: URL
        do {
            projectURL = try host.exportProjectToTemporaryFile()
        } catch {
            try? FileManager.default.removeItem(at: answersURL)
            setApplying(false)
            StatusCenter.shared.failure("Couldn't hand the song to the listening tool", error: error, window: window)
            return
        }

        // Everything except `--answers` belongs to the top-level parser, and
        // argparse rejects those options once the subcommand has been named.
        var arguments = [
            host.store.toolURL("listening_session.py").path,
            "--root", host.store.rootURL.path,
            "--project", projectURL.path
        ]
        if let specPath {
            arguments += ["--spec", specPath.path]
        }
        arguments += [
            "--project-id", projectId,
            "--format", "json",
            "apply",
            "--answers", answersURL.path
        ]

        let answerCount = payload.count
        // Captured strongly on purpose: the tool has already written the build
        // plan by the time it answers, so the result must land even if the
        // window was closed in the meantime.
        host.runTool(
            name: toolDisplayName,
            progressMessage: "Turning your \(answerCount) answer\(answerCount == 1 ? "" : "s") into steps…",
            arguments: arguments
        ) { result in
            try? FileManager.default.removeItem(at: answersURL)
            try? FileManager.default.removeItem(at: projectURL)
            self.setApplying(false)
            switch result {
            case .failure:
                // The host has shown the error. The answers are still here, so
                // the user can fix the cause and press Finish again.
                StatusCenter.shared.info("Your answers are still here — fix the problem and press Finish again.")
            case .success(let toolResult):
                self.receiveApplied(toolResult.lastJSONObject)
            }
        }
    }

    private func setApplying(_ applying: Bool) {
        isApplying = applying
        backButton?.isEnabled = !applying && pageIndex > 0
        nextButton?.isEnabled = !applying
        finishButton?.isEnabled = !applying
        playToggle?.isEnabled = !applying
        if applying {
            footerSpinner.startAnimation(nil)
        } else {
            footerSpinner.stopAnimation(nil)
        }
    }

    private func receiveApplied(_ json: [String: Any]) {
        guard !json.isEmpty else {
            StatusCenter.shared.failure(
                "\(toolDisplayName) finished but didn't return a result",
                error: ToolError.noJSON(name: toolDisplayName),
                window: window
            )
            return
        }
        guard JSONValue.bool(json["ok"]) else {
            let message = JSONValue.string(json["error"])
            let lowered = message.lowercased()
            let nextStep: String
            if lowered.contains("spec") || lowered.contains("inputs") {
                nextStep = "This song doesn't have a build plan yet (a transcript_spec.json), which is where the steps go. Build the song from a description first, then listen again. Your answers are still here."
            } else if lowered.contains("project") {
                nextStep = "Save the song (⌘S) and press Finish again. Your answers are still here."
            } else {
                nextStep = "Open Window ▸ Activity for the tool's output, then press Finish again. Your answers are still here."
            }
            StatusCenter.shared.failure(
                "Your answers couldn't be turned into steps",
                error: SessionError(
                    message: message.isEmpty ? "The tool didn't say what went wrong." : message,
                    nextStep: nextStep
                ),
                window: window
            )
            return
        }

        let steps = JSONValue.objects(json["steps"])
        let notes = JSONValue.strings(json["notes"])
        let warnings = JSONValue.strings(json["warnings"])
        var summary = JSONValue.string(json["summary"])
        if summary.isEmpty {
            summary = "\(steps.count) step\(steps.count == 1 ? "" : "s") from your answers"
        }

        let addedToRecipe = addStepsToRecipe(steps)
        let report = buildReport(
            steps: steps,
            notes: notes,
            warnings: warnings,
            summary: summary,
            addedToRecipe: addedToRecipe,
            provenance: AIProvenance.read(from: json)
        )

        hasFinished = true
        let parent = host?.window
        ReportWindowController.present(report: report, relativeTo: parent)
        close()

        let detail: String
        if steps.isEmpty {
            detail = "Nothing needed changing — what you heard matches what the song is going for. Your notes are kept with the song's build plan."
        } else if addedToRecipe > 0 {
            detail = "They're in the recipe as steps to do. Check My Mix will look for them next time. Undo (⌘Z) takes them back out."
        } else {
            detail = "They're in the recipe as steps to do. Check My Mix will look for them next time."
        }
        StatusCenter.shared.success(AIProvenance.annotate(summary, from: json), detail: detail)
    }

    /// Lands the tool's steps in the project's recipe as one undoable edit.
    /// Returns how many were new; a step the recipe already lists for the
    /// same section is not added twice.
    private func addStepsToRecipe(_ steps: [[String: Any]]) -> Int {
        guard let host, !steps.isEmpty else { return 0 }
        let labelsById = Dictionary(sections.map { ($0.id, $0.label) }, uniquingKeysWith: { first, _ in first })

        func key(_ section: String?, _ label: String) -> String {
            "\((section ?? "").lowercased())|\(label.lowercased())"
        }

        var seen = Set((host.project.snapshot.recipe ?? []).map { key($0.section, $0.label) })
        var items: [RecipeItem] = []
        for step in steps {
            let label = JSONValue.string(step["label"])
            guard !label.isEmpty else { continue }
            let detail = JSONValue.string(step["step"])
            let sectionId = JSONValue.string(step["section"])
            let sectionLabel: String? = sectionId.isEmpty ? nil : (labelsById[sectionId] ?? sectionId)
            let itemKey = key(sectionLabel, label)
            guard !seen.contains(itemKey) else { continue }
            seen.insert(itemKey)
            items.append(RecipeItem(
                id: makeId("listen"),
                section: sectionLabel,
                label: label,
                detail: detail.isEmpty ? nil : detail,
                status: RecipeItem.notDoneStatus
            ))
        }
        guard !items.isEmpty else { return 0 }

        host.edit("Add Listening Session Steps") { project in
            var recipe = project.snapshot.recipe ?? []
            recipe.append(contentsOf: items)
            project.snapshot.recipe = recipe
        }
        return items.count
    }

    // MARK: Report

    private func buildReport(
        steps: [[String: Any]],
        notes: [String],
        warnings: [String],
        summary: String,
        addedToRecipe: Int,
        provenance: AIProvenance? = nil
    ) -> Report {
        var toldUs: [String] = []
        for section in sections {
            for question in section.questions {
                switch answers[question.id] {
                case .option(let option)?:
                    toldUs.append("\(section.label): \(option)")
                case .text(let text)?:
                    toldUs.append("\(section.label), in your words: “\(text)”")
                case nil:
                    continue
                }
            }
        }
        if toldUs.isEmpty {
            toldUs.append("No answers were given.")
        }

        var toDo: [String] = steps.compactMap { step -> String? in
            let label = JSONValue.string(step["label"])
            let text = JSONValue.string(step["step"])
            switch (label.isEmpty, text.isEmpty) {
            case (false, false): return "\(label): \(text)"
            case (false, true): return label
            case (true, false): return text
            case (true, true): return nil
            }
        }
        if toDo.isEmpty {
            toDo.append("Nothing to change — what you heard matches what the song is going for.")
        } else if addedToRecipe > 0 {
            toDo.append(
                addedToRecipe == 1
                    ? "Added to this song's recipe as a step to do. Undo (⌘Z) takes it back out."
                    : "Added \(addedToRecipe) of these to this song's recipe as steps to do. Undo (⌘Z) takes them back out."
            )
        } else {
            toDo.append("The recipe already lists these, so nothing was added twice.")
        }

        var sections: [Report.Section] = [
            Report.Section(title: "What you told us", lines: toldUs),
            Report.Section(title: "What to do about it", lines: toDo)
        ]
        if !notes.isEmpty {
            sections.append(Report.Section(title: "Your notes", lines: notes))
        }
        if !warnings.isEmpty {
            sections.append(Report.Section(title: "Things to know", lines: warnings))
        }

        let headline = "\(steps.count) step\(steps.count == 1 ? "" : "s")"
        let subtitle = host?.project.name ?? projectId
        return Report(
            title: "Listen with me",
            subtitle: subtitle,
            headline: headline,
            headlineCaption: summary,
            sections: sections,
            plainText: renderPlainText(
                title: "Listen with me",
                subtitle: subtitle,
                headline: headline,
                caption: summary,
                sections: sections
            ),
            footer: provenance?.footerLine
        )
    }

    private func renderPlainText(
        title: String,
        subtitle: String,
        headline: String,
        caption: String,
        sections: [Report.Section]
    ) -> String {
        var lines: [String] = ["\(title) — \(subtitle)", ""]
        lines.append("\(headline) — \(caption)")
        for section in sections where !section.lines.isEmpty {
            lines.append("")
            lines.append(section.title)
            lines.append(String(repeating: "-", count: section.title.count))
            for line in section.lines {
                lines.append("• \(line)")
            }
        }
        return lines.joined(separator: "\n")
    }

    // MARK: Closing

    private var hasAnswers: Bool {
        commitCurrentPageText()
        return !answers.isEmpty
    }

    /// Escape, from anywhere in the window.
    public override func cancelOperation(_ sender: Any?) {
        requestClose()
    }

    private func requestClose() {
        window?.performClose(nil)
    }

    public func windowShouldClose(_ sender: NSWindow) -> Bool {
        if isDiscardConfirmed || hasFinished || !hasAnswers {
            return true
        }
        confirmDiscard()
        return false
    }

    private func confirmDiscard() {
        guard let window else { return }
        let count = answers.count
        let alert = NSAlert()
        alert.alertStyle = .warning
        alert.messageText = "Discard your answers?"
        alert.informativeText = "You've answered \(count) question\(count == 1 ? "" : "s"). Closing now throws \(count == 1 ? "that answer" : "those answers") away. Nothing in the song changes either way."
        alert.addButton(withTitle: "Keep Listening")
        let discard = alert.addButton(withTitle: "Discard")
        discard.hasDestructiveAction = true
        alert.beginSheetModal(for: window) { [weak self] response in
            guard let self, response == .alertSecondButtonReturn else { return }
            self.isDiscardConfirmed = true
            self.close()
        }
    }

    private func askForAtLeastOneAnswer() {
        guard let window else { return }
        let alert = NSAlert()
        alert.alertStyle = .informational
        alert.messageText = "No answers yet"
        alert.informativeText = "Pick an answer to at least one question, or write a note, and Neon Studio will turn it into steps. Or close this window to leave the song exactly as it is."
        alert.addButton(withTitle: "Keep Listening")
        alert.addButton(withTitle: "Close")
        alert.beginSheetModal(for: window) { [weak self] response in
            guard let self, response == .alertSecondButtonReturn else { return }
            self.isDiscardConfirmed = true
            self.close()
        }
    }

    private func hostWentAway() {
        StatusCenter.shared.info("The song's window closed, so the listening session ended. Open the song and choose Listen with me again to continue.")
        isDiscardConfirmed = true
        close()
    }

    public func windowWillClose(_ notification: Notification) {
        playbackSyncTimer?.invalidate()
        playbackSyncTimer = nil
        host?.stopPlayback()
        ListeningSessionWindowController.openControllers.removeAll { $0 === self }
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
}

// MARK: - JSON coercion

/// Reads values out of whatever the tool actually printed. `JSONSerialization`
/// hands back `NSNumber` for booleans and numbers alike and `NSNull` for
/// `null`, so every accessor here tolerates the wrong type and returns a
/// sensible nothing rather than crashing or showing "nil".
private enum JSONValue {
    static func string(_ value: Any?) -> String {
        switch value {
        case let string as String:
            return string.trimmingCharacters(in: .whitespacesAndNewlines)
        case let number as NSNumber where !isBoolean(number):
            return number.stringValue
        default:
            return ""
        }
    }

    static func bool(_ value: Any?) -> Bool {
        if let number = value as? NSNumber { return number.boolValue }
        if let string = value as? String { return ["true", "yes", "1"].contains(string.lowercased()) }
        return false
    }

    static func double(_ value: Any?) -> Double? {
        switch value {
        case let number as NSNumber where !isBoolean(number):
            return number.doubleValue.isFinite ? number.doubleValue : nil
        case let string as String:
            guard let double = Double(string.trimmingCharacters(in: .whitespacesAndNewlines)), double.isFinite else {
                return nil
            }
            return double
        default:
            return nil
        }
    }

    static func strings(_ value: Any?) -> [String] {
        guard let array = value as? [Any] else { return [] }
        return array.compactMap { item in
            let text = string(item)
            return text.isEmpty ? nil : text
        }
    }

    static func objects(_ value: Any?) -> [[String: Any]] {
        guard let array = value as? [Any] else { return [] }
        return array.compactMap { $0 as? [String: Any] }
    }

    private static func isBoolean(_ number: NSNumber) -> Bool {
        CFGetTypeID(number) == CFBooleanGetTypeID()
    }
}

// MARK: - Private views

/// A segmented control that reports through a closure, matching the other
/// closure-backed controls in `Controls`.
private final class AnswerSegmentedControl: NSSegmentedControl {
    var handler: ((Int) -> Void)?
    @objc func invoke() { handler?(selectedSegment) }
}

/// A label that wraps to the width it is given. Questions can be long
/// sentences, and a truncated question is one nobody can answer.
private final class WrappingQuestionLabel: NSTextField {
    init(text: String, font: NSFont, color: NSColor) {
        super.init(frame: .zero)
        stringValue = text
        self.font = font
        textColor = color
        isEditable = false
        isSelectable = false
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

/// Scroll content anchored at the top, the way a list of questions reads.
private final class FlippedDocumentView: NSView {
    override var isFlipped: Bool { true }
}
