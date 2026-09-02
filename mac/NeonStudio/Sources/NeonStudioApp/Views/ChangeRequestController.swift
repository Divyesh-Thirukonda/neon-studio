import AppKit
import NeonStudioKit

/// "Make the drop hit harder."
///
/// The user types what they want in their own words and it happens. The
/// sentence goes to `describe_change.py`, which parses it with an explicit
/// grammar, applies the matching edits to a copy of the project, and reports
/// exactly what it did and what it did not understand. Everything it did lands
/// as ONE undoable step; everything it did not understand comes back as
/// phrasings the user can click instead of retyping.
///
/// Shown as a transient popover when there is a control to anchor it to, and
/// as a sheet otherwise. The text survives between openings in the same
/// session so a request can be refined rather than started over.
public final class ChangeRequestController: NSObject, NSPopoverDelegate, NSTextViewDelegate {

    // MARK: Constants

    private static let panelWidth: CGFloat = 420
    private static let padding: CGFloat = 16
    private static var contentWidth: CGFloat { panelWidth - padding * 2 }
    private static let placeholderText = "For example: the drums are too loud in the verse"
    private static let autoCloseDelay: TimeInterval = 4

    private static let examples = [
        "make the drop hit harder",
        "the lead is too bright",
        "more bounce in the drums",
        "give the chords more space",
        "the second drop should be bigger",
        "a bit slower"
    ]

    // MARK: State

    private enum Stage {
        /// The field and the example chips.
        case composing
        /// The tool is running; the field is locked and Apply is off.
        case working
        /// Everything applied. A compact summary that closes on its own.
        case applied
        /// Nothing, or only part, applied. The field stays for another go.
        case rephrase
    }

    private weak var host: ToolHost?

    /// Kept between openings so the user can refine a request instead of
    /// retyping it.
    private var requestText = ""
    private var stage: Stage = .composing
    private var runInFlight = false

    private var popover: NSPopover?
    private var sheetWindow: NSWindow?
    private var views: ContentViews?
    private var autoCloseTimer: Timer?
    private var clickToClose: NSClickGestureRecognizer?

    public init(host: ToolHost) {
        self.host = host
        super.init()
    }

    deinit {
        autoCloseTimer?.invalidate()
    }

    // MARK: Presenting

    /// Anchors a popover to `view` when one is given, otherwise runs a sheet on
    /// the host's window (or a plain window if there is no host window yet).
    public func present(relativeTo view: NSView?) {
        dismiss()

        let built = buildContent()
        views = built
        built.textView.string = requestText
        stage = runInFlight ? .working : .composing
        syncFromField()
        applyStage()

        if let view, view.window != nil {
            let controller = NSViewController()
            controller.view = built.container
            let popover = NSPopover()
            popover.behavior = .transient
            popover.animates = !Theme.prefersReducedMotion
            popover.contentViewController = controller
            popover.delegate = self
            built.container.layoutSubtreeIfNeeded()
            popover.contentSize = built.container.fittingSize
            self.popover = popover
            popover.show(relativeTo: view.bounds, of: view, preferredEdge: .maxY)
            return
        }

        let parent = host?.window
        let window = NSWindow(
            contentRect: NSRect(origin: .zero, size: NSSize(width: Self.panelWidth, height: 240)),
            styleMask: parent == nil ? [.titled, .closable] : [.titled],
            backing: .buffered,
            defer: false
        )
        window.title = "What should change?"
        // ARC owns this window; letting AppKit release it on close as well
        // would free it twice.
        window.isReleasedWhenClosed = false
        window.contentView = built.container
        built.container.layoutSubtreeIfNeeded()
        window.setContentSize(built.container.fittingSize)
        window.initialFirstResponder = built.textView
        sheetWindow = window

        if let parent {
            parent.beginSheet(window) { [weak self] _ in
                self?.tearDown()
            }
        } else {
            window.center()
            window.makeKeyAndOrderFront(nil)
        }
        window.makeFirstResponder(built.textView)
    }

    private func dismiss() {
        if let popover {
            self.popover = nil
            popover.close()
        }
        if let window = sheetWindow {
            sheetWindow = nil
            if let parent = window.sheetParent {
                parent.endSheet(window)
            } else {
                window.orderOut(nil)
            }
        }
        tearDown()
    }

    private func tearDown() {
        autoCloseTimer?.invalidate()
        autoCloseTimer = nil
        clickToClose = nil
        views = nil
    }

    private func cancel() {
        dismiss()
    }

    private func focusField() {
        guard let v = views, stage != .applied, stage != .working else { return }
        v.textView.window?.makeFirstResponder(v.textView)
    }

    // MARK: NSPopoverDelegate

    public func popoverDidShow(_ notification: Notification) {
        focusField()
    }

    public func popoverDidClose(_ notification: Notification) {
        popover = nil
        tearDown()
    }

    // MARK: NSTextViewDelegate

    public func textDidChange(_ notification: Notification) {
        syncFromField()
    }

    // MARK: Building the panel

    private struct ContentViews {
        let container: ContainerView
        let title: NSTextField
        let intro: NSTextField
        let scroll: NSScrollView
        let textView: RequestTextView
        let placeholder: NSTextField
        let hintLabel: NSTextField
        let examplesFlow: ChipFlowView
        let resultStack: NSStackView
        let resultTitle: NSTextField
        let resultBody: NSTextField
        let resultCaption: NSTextField
        let unresolvedLabel: NSTextField
        let suggestionsHeader: NSTextField
        let suggestionsFlow: ChipFlowView
        let tacticsHeader: NSTextField
        let tacticsFlow: ChipFlowView
        let spinner: NSProgressIndicator
        let workingLabel: NSTextField
        let cancelButton: NSButton
        let applyButton: NSButton
        let closeButton: NSButton
    }

    private func buildContent() -> ContentViews {
        let width = Self.contentWidth

        let container = ContainerView()
        container.onEscape = { [weak self] in self?.cancel() }
        container.setAccessibilityRole(.group)
        container.setAccessibilityLabel("Describe a change")
        container.setAccessibilityHelp("Type what should change in the song, in your own words, then click Apply.")

        let title = makeLabel("What should change?", font: Theme.Font.title(), color: Theme.text)
        title.setAccessibilityRole(.staticText)
        let intro = makeLabel(
            "Say it the way you'd say it to a producer.",
            font: Theme.Font.body(12),
            color: Theme.muted
        )

        // The field: a real NSTextView so it wraps and scrolls, three lines tall.
        let fieldHelp = AppEnvironment.shared.help(
            "Describe the change in plain words. Name the part (drums, lead, chords) and what should be different. ⌘↩ applies it.",
            term: "Track"
        )
        let textView = RequestTextView(frame: NSRect(x: 0, y: 0, width: width, height: 60))
        textView.onCancel = { [weak self] in self?.cancel() }
        textView.onApply = { [weak self] in self?.apply() }
        textView.minSize = NSSize(width: 0, height: 60)
        textView.maxSize = NSSize(width: CGFloat.greatestFiniteMagnitude, height: CGFloat.greatestFiniteMagnitude)
        textView.isVerticallyResizable = true
        textView.isHorizontallyResizable = false
        textView.autoresizingMask = [.width]
        textView.textContainer?.size = NSSize(width: width, height: CGFloat.greatestFiniteMagnitude)
        textView.textContainer?.widthTracksTextView = true
        textView.isRichText = false
        textView.usesFontPanel = false
        textView.allowsUndo = true
        textView.font = Theme.Font.body()
        textView.textColor = Theme.text
        textView.insertionPointColor = Theme.text
        textView.drawsBackground = true
        textView.backgroundColor = Theme.panel
        textView.textContainerInset = NSSize(width: 4, height: 6)
        // It's an instruction, not prose: keep the characters the user typed.
        textView.isAutomaticQuoteSubstitutionEnabled = false
        textView.isAutomaticDashSubstitutionEnabled = false
        textView.delegate = self
        textView.toolTip = fieldHelp
        textView.setAccessibilityLabel("What should change")
        textView.setAccessibilityHelp(fieldHelp)
        textView.setAccessibilityPlaceholderValue(Self.placeholderText)

        let lineHeight = ceil(NSLayoutManager().defaultLineHeight(for: Theme.Font.body()))
        let fieldHeight = ceil(lineHeight * 3 + textView.textContainerInset.height * 2 + 4)

        let scroll = NSScrollView()
        scroll.translatesAutoresizingMaskIntoConstraints = false
        scroll.hasVerticalScroller = true
        scroll.hasHorizontalScroller = false
        scroll.autohidesScrollers = true
        scroll.borderType = .bezelBorder
        scroll.drawsBackground = true
        scroll.backgroundColor = Theme.panel
        scroll.documentView = textView
        scroll.heightAnchor.constraint(equalToConstant: fieldHeight).isActive = true

        // NSTextView has no placeholder of its own, so one is drawn on top and
        // hidden as soon as there is any text. It never takes clicks.
        let placeholder = PassThroughLabel(labelWithString: Self.placeholderText)
        placeholder.font = Theme.Font.body()
        placeholder.textColor = Theme.dim
        placeholder.lineBreakMode = .byTruncatingTail
        placeholder.translatesAutoresizingMaskIntoConstraints = false
        placeholder.setAccessibilityHidden(true)
        textView.addSubview(placeholder)
        let padding = textView.textContainer?.lineFragmentPadding ?? 5
        NSLayoutConstraint.activate([
            placeholder.leadingAnchor.constraint(
                equalTo: textView.leadingAnchor,
                constant: textView.textContainerInset.width + padding
            ),
            placeholder.topAnchor.constraint(equalTo: textView.topAnchor, constant: textView.textContainerInset.height),
            placeholder.trailingAnchor.constraint(lessThanOrEqualTo: textView.trailingAnchor, constant: -8)
        ])

        let hintLabel = Self.wrappingLabel("", font: Theme.Font.caption(12), color: Theme.warning)
        hintLabel.isHidden = true

        let examplesFlow = ChipFlowView(width: width)
        examplesFlow.setAccessibilityLabel("Examples")
        examplesFlow.setChips(Self.examples.map { example in
            makeChip(example, help: "Puts “\(example)” in the box. Click Apply to make it happen.")
        })

        // Result area, filled in after the tool answers.
        let resultTitle = Self.wrappingLabel("", font: Theme.Font.emphasis(13), color: Theme.text)
        let resultBody = Self.wrappingLabel("", font: Theme.Font.body(12), color: Theme.text)
        let resultCaption = Self.wrappingLabel("", font: Theme.Font.caption(11), color: Theme.dim)
        let unresolvedLabel = Self.wrappingLabel("", font: Theme.Font.body(12), color: Theme.muted)
        let suggestionsHeader = makeLabel("Try saying:", font: Theme.Font.caption(11), color: Theme.muted)
        let suggestionsFlow = ChipFlowView(width: width)
        suggestionsFlow.setAccessibilityLabel("Phrasings that work")
        let tacticsHeader = makeLabel("Or try a bigger idea:", font: Theme.Font.caption(11), color: Theme.muted)
        let tacticsFlow = ChipFlowView(width: width)
        tacticsFlow.setAccessibilityLabel("Bigger ideas")

        let resultStack = NSStackView(views: [
            resultTitle, resultBody, resultCaption, unresolvedLabel,
            suggestionsHeader, suggestionsFlow, tacticsHeader, tacticsFlow
        ])
        resultStack.orientation = .vertical
        resultStack.alignment = .width
        resultStack.spacing = 6
        resultStack.setCustomSpacing(10, after: resultCaption)
        resultStack.setCustomSpacing(10, after: suggestionsFlow)
        resultStack.translatesAutoresizingMaskIntoConstraints = false
        resultStack.setAccessibilityRole(.group)
        resultStack.setAccessibilityLabel("Result")

        // Buttons.
        let spinner = NSProgressIndicator()
        spinner.style = .spinning
        spinner.controlSize = .small
        spinner.isDisplayedWhenStopped = false
        spinner.translatesAutoresizingMaskIntoConstraints = false
        spinner.setAccessibilityLabel("Working")

        let workingLabel = makeLabel("Working out what to change…", font: Theme.Font.caption(12), color: Theme.muted)

        let cancelButton = Controls.button(
            title: "Cancel",
            help: "Closes this panel without changing the song. If a change is already being worked out it still finishes; the status bar's Cancel stops it.",
            keyEquivalent: "\u{1B}",
            keyEquivalentModifiers: [],
            action: { [weak self] in self?.cancel() }
        )
        let applyButton = Controls.button(
            title: "Apply",
            help: "Makes this change to the song as one step. ⌘Z undoes it. Shortcut: ⌘↩.",
            style: .primary,
            keyEquivalent: "\r",
            keyEquivalentModifiers: [.command],
            action: { [weak self] in self?.apply() }
        )
        let closeButton = Controls.button(
            title: "Close",
            help: "Closes this panel. The change stays; ⌘Z undoes it.",
            style: .primary,
            keyEquivalent: "\r",
            keyEquivalentModifiers: [],
            action: { [weak self] in self?.cancel() }
        )
        closeButton.isHidden = true

        let spacer = NSView()
        spacer.translatesAutoresizingMaskIntoConstraints = false
        spacer.setContentHuggingPriority(NSLayoutConstraint.Priority(1), for: .horizontal)
        spacer.setContentCompressionResistancePriority(NSLayoutConstraint.Priority(1), for: .horizontal)

        let buttonRow = NSStackView(views: [spinner, workingLabel, spacer, cancelButton, applyButton, closeButton])
        buttonRow.orientation = .horizontal
        buttonRow.alignment = .centerY
        buttonRow.distribution = .fill
        buttonRow.spacing = 8
        buttonRow.translatesAutoresizingMaskIntoConstraints = false

        let stack = NSStackView(views: [title, intro, scroll, hintLabel, examplesFlow, resultStack, buttonRow])
        stack.orientation = .vertical
        stack.alignment = .width
        stack.spacing = 10
        stack.setCustomSpacing(3, after: title)
        stack.setCustomSpacing(8, after: scroll)
        stack.setCustomSpacing(14, after: resultStack)
        stack.translatesAutoresizingMaskIntoConstraints = false
        container.addSubview(stack)

        // Leading and top pin at required priority, trailing and bottom just
        // under it: the popover and the sheet both size themselves from
        // `fittingSize`, and a one-point disagreement must not become an
        // unsatisfiable-constraints complaint.
        let trailing = stack.trailingAnchor.constraint(equalTo: container.trailingAnchor, constant: -Self.padding)
        trailing.priority = NSLayoutConstraint.Priority(999)
        let bottom = stack.bottomAnchor.constraint(equalTo: container.bottomAnchor, constant: -Self.padding)
        bottom.priority = NSLayoutConstraint.Priority(999)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: container.leadingAnchor, constant: Self.padding),
            stack.topAnchor.constraint(equalTo: container.topAnchor, constant: Self.padding),
            trailing,
            bottom,
            stack.widthAnchor.constraint(equalToConstant: width)
        ])

        let click = NSClickGestureRecognizer(target: self, action: #selector(handleClickToClose(_:)))
        click.isEnabled = false
        container.addGestureRecognizer(click)
        clickToClose = click

        return ContentViews(
            container: container,
            title: title,
            intro: intro,
            scroll: scroll,
            textView: textView,
            placeholder: placeholder,
            hintLabel: hintLabel,
            examplesFlow: examplesFlow,
            resultStack: resultStack,
            resultTitle: resultTitle,
            resultBody: resultBody,
            resultCaption: resultCaption,
            unresolvedLabel: unresolvedLabel,
            suggestionsHeader: suggestionsHeader,
            suggestionsFlow: suggestionsFlow,
            tacticsHeader: tacticsHeader,
            tacticsFlow: tacticsFlow,
            spinner: spinner,
            workingLabel: workingLabel,
            cancelButton: cancelButton,
            applyButton: applyButton,
            closeButton: closeButton
        )
    }

    private func makeChip(_ text: String, help: String) -> NSButton {
        let chip = Controls.button(title: text, help: help, style: .quiet) { [weak self] in
            self?.fill(with: text)
        }
        chip.lineBreakMode = .byTruncatingTail
        return chip
    }

    private static func wrappingLabel(_ text: String, font: NSFont, color: NSColor) -> NSTextField {
        let label = NSTextField(wrappingLabelWithString: text)
        label.font = font
        label.textColor = color
        label.preferredMaxLayoutWidth = contentWidth
        label.translatesAutoresizingMaskIntoConstraints = false
        label.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        label.setContentCompressionResistancePriority(.required, for: .vertical)
        label.setContentHuggingPriority(.required, for: .vertical)
        return label
    }

    @objc private func handleClickToClose(_ sender: NSClickGestureRecognizer) {
        guard stage == .applied else { return }
        dismiss()
    }

    // MARK: Stage → views

    private func applyStage() {
        guard let v = views else { return }
        let composing = stage == .composing
        let working = stage == .working
        let applied = stage == .applied
        let rephrase = stage == .rephrase
        let hasText = !v.textView.string.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty

        v.title.isHidden = applied
        v.intro.isHidden = applied
        v.scroll.isHidden = applied
        v.examplesFlow.isHidden = !composing
        v.hintLabel.isHidden = v.hintLabel.stringValue.isEmpty || applied || working
        v.resultStack.isHidden = !(applied || rephrase)

        v.spinner.isHidden = !working
        if working {
            v.spinner.startAnimation(nil)
        } else {
            v.spinner.stopAnimation(nil)
        }
        v.workingLabel.isHidden = !working

        v.cancelButton.isHidden = applied
        v.applyButton.isHidden = applied
        v.applyButton.isEnabled = !working && hasText
        v.closeButton.isHidden = !applied

        v.textView.isEditable = !working
        v.textView.isSelectable = true
        clickToClose?.isEnabled = applied

        if applied {
            v.container.window?.makeFirstResponder(v.container)
        }
        resizeToFit()
    }

    private func resizeToFit() {
        guard let v = views else { return }
        v.container.layoutSubtreeIfNeeded()
        let size = v.container.fittingSize
        if let popover, popover.isShown {
            popover.contentSize = size
        } else if let window = sheetWindow {
            let target = window.frameRect(forContentRect: NSRect(origin: .zero, size: size))
            var frame = window.frame
            // Keep the sheet hanging from the same place; grow or shrink downwards.
            frame.origin.y += frame.height - target.height
            frame.size = target.size
            window.setFrame(frame, display: true, animate: !Theme.prefersReducedMotion)
        }
    }

    /// Mirrors the field into the placeholder, the Apply button and the text
    /// remembered for next time.
    private func syncFromField() {
        guard let v = views else { return }
        let text = v.textView.string
        requestText = text
        v.placeholder.isHidden = !text.isEmpty
        let hasText = !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        v.applyButton.isEnabled = stage != .working && hasText
        if hasText, !v.hintLabel.isHidden {
            setHint(nil)
        }
    }

    private func fill(with text: String) {
        guard let v = views, stage != .working, stage != .applied else { return }
        v.textView.string = text
        syncFromField()
        v.textView.window?.makeFirstResponder(v.textView)
        v.textView.setSelectedRange(NSRange(location: (text as NSString).length, length: 0))
    }

    private func setHint(_ text: String?) {
        guard let v = views else { return }
        v.hintLabel.stringValue = text ?? ""
        v.hintLabel.isHidden = (text ?? "").isEmpty
        resizeToFit()
    }

    private func showHint(_ text: String) {
        setHint(text)
        NSAccessibility.post(element: views?.hintLabel as Any, notification: .announcementRequested)
    }

    // MARK: Applying

    private func apply() {
        guard let host, let v = views else { return }
        guard stage != .working else { return }
        let text = v.textView.string.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else {
            showHint("Type what should change first, or click one of the examples.")
            focusField()
            return
        }
        requestText = text

        let input: URL
        do {
            input = try host.exportProjectToTemporaryFile()
        } catch {
            StatusCenter.shared.failure("Couldn't prepare the song for the change", error: error, window: host.window)
            return
        }
        let output = FileManager.default.temporaryDirectory
            .appendingPathComponent("\(makeId("change")).neon.json")

        let progressMessage = "Applying “\(Self.shortened(text, limit: 48))”"
        let arguments = [
            host.store.toolURL("describe_change.py").path,
            "--root", host.store.rootURL.path,
            "--project", input.path,
            // Joined with "=" so a request that happens to start with a dash
            // can't be mistaken for a flag.
            "--request=\(text)",
            "--output", output.path,
            "--format", "json"
        ]

        setHint(nil)
        stage = .working
        runInFlight = true
        applyStage()

        host.runTool(name: "Apply Change", progressMessage: progressMessage, arguments: arguments) { [weak self] result in
            defer {
                [input, output].forEach { try? FileManager.default.removeItem(at: $0) }
            }
            guard let self else { return }
            self.runInFlight = false
            switch result {
            case .failure:
                // The host has already told the user what went wrong. Put the
                // panel back so the request can be tried again.
                self.stage = .composing
                self.applyStage()
                self.showHint("That didn't work and nothing was changed. The reason is in the status bar and under Window ▸ Activity.")
            case .success(let toolResult):
                self.handle(toolResult.lastJSONObject, request: text, output: output)
            }
        }

        // The host declines to start a tool when Python is missing or another
        // task is running. It says so through the status bar and never calls
        // back, so the panel has to notice on its own or it would sit on
        // "Working…" forever.
        if !Self.toolStarted(progressMessage) {
            runInFlight = false
            try? FileManager.default.removeItem(at: input)
            stage = .composing
            applyStage()
            showHint("Couldn't start. The status bar says why — sort that out, then click Apply again.")
        }
    }

    /// The host posts a progress entry the moment a tool starts, before
    /// returning; anything else there means it refused.
    private static func toolStarted(_ progressMessage: String) -> Bool {
        guard let current = StatusCenter.shared.current else { return false }
        return current.severity == .progress && current.message.hasPrefix(progressMessage)
    }

    private func handle(_ json: [String: Any], request: String, output: URL) {
        guard let host else { return }

        guard !json.isEmpty else {
            stage = .composing
            applyStage()
            StatusCenter.shared.warning(
                "The change tool didn't return a result",
                detail: "Nothing was changed. Its output is under Window ▸ Activity."
            )
            showHint("The change tool finished without saying what it did, so nothing was changed. Check Window ▸ Activity, then try again.")
            return
        }

        guard (json["ok"] as? Bool) == true else {
            let reason = Self.string(json["error"])
            let shownReason = reason.isEmpty ? "the change tool reported a problem" : reason
            stage = .composing
            applyStage()
            StatusCenter.shared.warning(
                "Couldn't apply “\(Self.shortened(request, limit: 40))”",
                detail: "\(shownReason). Nothing was changed."
            )
            showHint("Couldn't apply that: \(shownReason). Nothing was changed. Try a shorter request, like “make the drop hit harder”.")
            return
        }

        let edits = Self.dictionaryList(json["edits"])
        let unresolved = Self.stringList(json["unresolved"])
        let suggestions = Self.stringList(json["suggestions"])
        let tactics = Self.dictionaryList(json["tactics"])
            .map { Self.string($0["title"]) }
            .filter { !$0.isEmpty }
        var understood = Self.string(json["understood"])

        if edits.isEmpty {
            stage = .rephrase
            populateResult(
                title: "I didn't understand that yet.",
                bullets: [],
                caption: "Nothing was changed.",
                unresolved: unresolved,
                suggestions: suggestions,
                tactics: tactics
            )
            applyStage()
            StatusCenter.shared.warning(
                "Didn't understand “\(Self.shortened(request, limit: 40))”",
                detail: "Nothing was changed. Try one of the suggested phrasings."
            )
            focusField()
            return
        }

        guard let loaded = host.store.loadProject(from: output) else {
            stage = .composing
            applyStage()
            StatusCenter.shared.warning(
                "The change tool didn't produce a song file",
                detail: "Nothing was changed. Try again, or check Window ▸ Activity."
            )
            showHint("The change was worked out but the updated song couldn't be read back, so nothing was changed. Try again.")
            return
        }

        if understood.isEmpty { understood = request }
        let next = ProjectNormalizer.normalize(loaded)
        // One undo step reverts every edit the tool made.
        host.replaceProject(with: next, actionName: "Apply Change: \(Self.shortened(understood, limit: 60))")

        let bullets = edits.map { edit -> String in
            var line = Self.string(edit["title"])
            if line.isEmpty { line = Self.string(edit["detail"]) }
            if line.isEmpty { line = "Change" }
            let section = Self.string(edit["section"])
            return section.isEmpty ? line : "\(line) (\(section))"
        }
        let count = edits.count
        StatusCenter.shared.success(
            "Done — \(understood)",
            detail: "\(count) change\(count == 1 ? "" : "s"). ⌘Z undoes all of it."
        )

        if unresolved.isEmpty {
            stage = .applied
            populateResult(
                title: "Done — \(understood)",
                bullets: bullets,
                caption: "⌘Z undoes all of it.",
                unresolved: [],
                suggestions: [],
                tactics: []
            )
            applyStage()
            scheduleAutoClose()
            return
        }

        // Part applied, part not. Leave only the part that didn't apply in the
        // box, so Apply again retries just that and can't double up the rest.
        stage = .rephrase
        views?.textView.string = unresolved.map(Self.clauseText).joined(separator: ", ")
        syncFromField()
        populateResult(
            title: "Done — \(understood)",
            bullets: bullets,
            caption: "⌘Z undoes all of it. What wasn't understood is still in the box — rephrase it and Apply again.",
            unresolved: unresolved,
            suggestions: suggestions,
            tactics: tactics
        )
        applyStage()
        StatusCenter.shared.warning(
            "Didn't understand: \(unresolved.joined(separator: "; "))",
            detail: "The rest was applied. Rephrase what's left and Apply again."
        )
        focusField()
    }

    private func populateResult(
        title: String,
        bullets: [String],
        caption: String?,
        unresolved: [String],
        suggestions: [String],
        tactics: [String]
    ) {
        guard let v = views else { return }
        v.resultTitle.stringValue = title
        v.resultBody.stringValue = bullets.map { "•  \($0)" }.joined(separator: "\n")
        v.resultBody.isHidden = bullets.isEmpty
        v.resultCaption.stringValue = caption ?? ""
        v.resultCaption.isHidden = (caption ?? "").isEmpty
        v.unresolvedLabel.stringValue = "Didn't understand: " + unresolved.joined(separator: "; ")
        v.unresolvedLabel.isHidden = unresolved.isEmpty
        v.suggestionsHeader.isHidden = suggestions.isEmpty
        v.suggestionsFlow.isHidden = suggestions.isEmpty
        v.suggestionsFlow.setChips(suggestions.map { phrase in
            makeChip(phrase, help: "Puts “\(phrase)” in the box. Click Apply to make it happen.")
        })
        v.tacticsHeader.isHidden = tactics.isEmpty
        v.tacticsFlow.isHidden = tactics.isEmpty
        v.tacticsFlow.setChips(tactics.map { idea in
            makeChip(idea, help: "Puts “\(idea)” in the box — a bigger production idea. Click Apply to try it.")
        })
        NSAccessibility.post(element: v.resultTitle as Any, notification: .announcementRequested)
    }

    private func scheduleAutoClose() {
        autoCloseTimer?.invalidate()
        autoCloseTimer = Timer.scheduledTimer(withTimeInterval: Self.autoCloseDelay, repeats: false) { [weak self] _ in
            self?.dismiss()
        }
    }

    // MARK: JSON helpers

    private static func string(_ value: Any?) -> String {
        switch value {
        case let text as String:
            return text.trimmingCharacters(in: .whitespacesAndNewlines)
        case let number as NSNumber:
            return CFGetTypeID(number) == CFBooleanGetTypeID() ? "" : number.stringValue
        default:
            return ""
        }
    }

    private static func stringList(_ value: Any?) -> [String] {
        guard let array = value as? [Any] else { return [] }
        return array.compactMap { item in
            let line = string(item)
            return line.isEmpty ? nil : line
        }
    }

    private static func dictionaryList(_ value: Any?) -> [[String: Any]] {
        guard let array = value as? [Any] else { return [] }
        return array.compactMap { $0 as? [String: Any] }
    }

    /// The tool reports an unresolved clause as "the words (why)". This is
    /// the words on their own, for putting back in the field.
    private static func clauseText(_ item: String) -> String {
        guard item.hasSuffix(")"), let range = item.range(of: " (", options: .backwards) else { return item }
        let clause = String(item[..<range.lowerBound]).trimmingCharacters(in: .whitespacesAndNewlines)
        return clause.isEmpty ? item : clause
    }

    private static func shortened(_ text: String, limit: Int) -> String {
        let collapsed = text.replacingOccurrences(of: "\n", with: " ")
        guard collapsed.count > limit else { return collapsed }
        return String(collapsed.prefix(limit - 1)).trimmingCharacters(in: .whitespaces) + "…"
    }
}

// MARK: - Supporting views

/// The panel's root. Escape closes it from anywhere inside, including when
/// nothing is focused after the field has been hidden.
private final class ContainerView: NSView {
    var onEscape: (() -> Void)?

    override var acceptsFirstResponder: Bool { true }

    override func keyDown(with event: NSEvent) {
        if event.keyCode == 53 {
            onEscape?()
            return
        }
        super.keyDown(with: event)
    }
}

/// The request field. Escape closes the panel instead of opening the text
/// system's completion list, and ⌘↩ applies even when the Apply button can't
/// take the shortcut, so the user gets a reply rather than a stray newline.
private final class RequestTextView: NSTextView {
    var onCancel: (() -> Void)?
    var onApply: (() -> Void)?

    override func keyDown(with event: NSEvent) {
        if event.keyCode == 53 {
            onCancel?()
            return
        }
        let isReturn = event.keyCode == 36 || event.keyCode == 76
        if isReturn, event.modifierFlags.contains(.command) {
            onApply?()
            return
        }
        super.keyDown(with: event)
    }
}

/// A label that clicks pass straight through, for the placeholder that sits
/// over the text view.
private final class PassThroughLabel: NSTextField {
    override func hitTest(_ point: NSPoint) -> NSView? { nil }
}

/// Lays out chips left to right, wrapping onto new rows at a fixed width.
/// NSStackView can't wrap, and a phrase list of unknown length has to.
private final class ChipFlowView: NSView {
    private let layoutWidth: CGFloat
    private let spacing: CGFloat = 6
    private let rowSpacing: CGFloat = 6
    private var chips: [NSView] = []

    init(width: CGFloat) {
        layoutWidth = width
        super.init(frame: .zero)
        translatesAutoresizingMaskIntoConstraints = false
        setAccessibilityRole(.group)
        setContentHuggingPriority(.required, for: .vertical)
        setContentCompressionResistancePriority(.required, for: .vertical)
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    override var isFlipped: Bool { true }

    func setChips(_ views: [NSView]) {
        chips.forEach { $0.removeFromSuperview() }
        chips = views
        for chip in views {
            // Frames are set by hand below; leaving Auto Layout in charge of
            // these would have it zero them out.
            chip.translatesAutoresizingMaskIntoConstraints = true
            chip.autoresizingMask = []
            addSubview(chip)
        }
        invalidateIntrinsicContentSize()
        needsLayout = true
    }

    @discardableResult
    private func arrange(commit: Bool) -> CGFloat {
        var x: CGFloat = 0
        var y: CGFloat = 0
        var rowHeight: CGFloat = 0
        for chip in chips {
            var size = chip.intrinsicContentSize
            if size.width <= 0 || size.height <= 0 {
                size = chip.fittingSize
            }
            size.height = max(size.height, Theme.Metric.minimumHitTarget)
            size.width = min(size.width, layoutWidth)
            if x > 0, x + size.width > layoutWidth {
                x = 0
                y += rowHeight + rowSpacing
                rowHeight = 0
            }
            if commit {
                chip.frame = NSRect(x: x, y: y, width: size.width, height: size.height)
            }
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
        return chips.isEmpty ? 0 : y + rowHeight
    }

    override var intrinsicContentSize: NSSize {
        NSSize(width: layoutWidth, height: arrange(commit: false))
    }

    override func layout() {
        super.layout()
        arrange(commit: true)
    }
}
