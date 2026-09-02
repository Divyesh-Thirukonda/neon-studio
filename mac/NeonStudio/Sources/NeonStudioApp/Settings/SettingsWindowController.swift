import AppKit
import NeonStudioKit

/// The Settings window.
///
/// The previous build had no settings at all, and hardcoded `/usr/bin/python3`.
/// On a Mac without Apple's Command Line Tools that path exists but is a stub
/// that fails with an opaque error, so every render, sound check and transcript
/// import broke with no way for the user to point the app at a real interpreter.
/// This window makes the interpreter visible, checkable and changeable, and puts
/// the app's other preferences somewhere a Mac user expects to find them.
final class SettingsWindowController: NSWindowController, NSOpenSavePanelDelegate {

    static let shared: SettingsWindowController = {
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 560, height: 460),
            styleMask: [.titled, .closable],
            backing: .buffered,
            defer: false
        )
        window.title = "Neon Studio Settings"
        window.isReleasedWhenClosed = false
        window.backgroundColor = Theme.app
        let controller = SettingsWindowController(window: window)
        controller.buildInterface()
        return controller
    }()

    // MARK: Constants

    /// The exact remedy for a missing interpreter, shown verbatim. "Python not
    /// found" on its own leaves the user with nothing they can do about it.
    private static let remedy =
        "Install Apple's Command Line Tools by running xcode-select --install in Terminal, then click Auto-detect."
    private static let installCommand = "xcode-select --install"

    /// Width available for content inside a tab, after window and scroll padding.
    private static let contentWidth: CGFloat = 460

    private struct HelperTool {
        let file: String
        /// Plain-English purpose, so a filename is never the only label.
        let purpose: String
        /// Glossary term whose gloss belongs in this row's tooltip, if any.
        let term: String?
    }

    private static let helperTools: [HelperTool] = [
        HelperTool(file: "render_mixdown.py", purpose: "Renders your song to audio", term: "Mixdown"),
        HelperTool(file: "does_this_sound_good.py", purpose: "Checks how the mix sounds", term: "Sound check"),
        HelperTool(file: "daw_agent.py", purpose: "Suggests changes to the song", term: nil),
        HelperTool(file: "songlab.py", purpose: "Writes new song sections", term: nil),
        HelperTool(file: "vocal_autotune.py", purpose: "Tunes a recorded vocal", term: nil),
        HelperTool(file: "fill_in_blanks.py", purpose: "Fills gaps in a sketch", term: nil),
        HelperTool(file: "project_materializer.py", purpose: "Builds a project from a plan", term: "Recipe"),
        HelperTool(file: "ingest_transcript.py", purpose: "Turns a transcript into a plan", term: "Transcript"),
        HelperTool(file: "llm.py", purpose: "Talks to the AI model, when one is on", term: nil)
    ]

    private enum InterpreterState {
        case checking
        case working
        case missing

        var symbol: String {
            switch self {
            case .checking: return "clock"
            case .working: return "checkmark.circle.fill"
            case .missing: return "xmark.octagon.fill"
            }
        }

        var color: NSColor {
            switch self {
            case .checking: return Theme.muted
            case .working: return Theme.success
            case .missing: return Theme.danger
            }
        }
    }

    // MARK: Services

    private let environment = AppEnvironment.shared
    private var store: ProjectStore { environment.store }

    // MARK: General tab

    private var explainTermsBox: NSButton!
    private var welcomeBox: NSButton!
    private var confirmDeleteBox: NSButton!
    private var supportPathLabel: NSTextField!
    private var restoreRow: NSStackView!
    private var restoreButton: NSButton!

    // MARK: Audio & Tools tab

    private var interpreterField: CommitTextField!
    private var autoDetectButton: NSButton!
    private var interpreterIcon: NSImageView!
    private var interpreterLabel: NSTextField!
    private var remedyLabel: NSTextField!
    private var remedyRow: NSView!
    private var copyCommandRow: NSView!
    private var toolRows: [(tool: HelperTool, icon: NSImageView, label: NSTextField)] = []
    private var afconvertIcon: NSImageView!
    private var afconvertLabel: NSTextField!

    /// Stops a slow check from overwriting the answer of a newer one.
    private var verificationToken = 0
    private var runningCheck: ToolRunner.Handle?

    // MARK: AI assistance tab

    private var aiEnabledBox: NSButton!
    private var aiKeyField: CommitSecureTextField!
    private var aiKeyStatusLabel: NSTextField!
    private var aiRemoveKeyButton: NSButton!
    private var aiModelField: CommitTextField!
    private var aiTestButton: NSButton!
    private var aiTestIcon: NSImageView!
    private var aiTestLabel: NSTextField!
    private var pingToken = 0
    private var runningPing: ToolRunner.Handle?

    // MARK: Building

    private func buildInterface() {
        let tabs = NSTabView()
        tabs.translatesAutoresizingMaskIntoConstraints = false
        tabs.font = Theme.Font.body(12)
        tabs.setAccessibilityLabel("Settings sections")

        let general = NSTabViewItem(identifier: "general")
        general.label = "General"
        general.toolTip = "How Neon Studio explains itself, and where it keeps your songs."
        general.view = tabContainer(scrollable(makeGeneralContent()))
        tabs.addTabViewItem(general)

        let tools = NSTabViewItem(identifier: "tools")
        tools.label = "Audio & Tools"
        tools.toolTip = "The Python interpreter and helper tools Neon Studio needs to render and check audio."
        tools.view = tabContainer(scrollable(makeToolsContent()))
        tabs.addTabViewItem(tools)

        let ai = NSTabViewItem(identifier: "ai")
        ai.label = "AI assistance"
        ai.toolTip = "An optional language model that reads descriptions and change requests. Never required."
        ai.view = tabContainer(scrollable(makeAIContent()))
        tabs.addTabViewItem(ai)

        let content = NSView()
        content.addSubview(tabs)
        NSLayoutConstraint.activate([
            tabs.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 14),
            tabs.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -14),
            tabs.topAnchor.constraint(equalTo: content.topAnchor, constant: 12),
            tabs.bottomAnchor.constraint(equalTo: content.bottomAnchor, constant: -14)
        ])
        window?.contentView = content
        window?.center()

        refresh()
    }

    // MARK: Presenting

    func present() {
        refresh()
        guard let window else { return }
        if !window.isVisible {
            window.center()
        }
        showWindow(nil)
        window.makeKeyAndOrderFront(nil)
        NSApp.activate()
        // Python can move between launches — a Homebrew upgrade, a removed
        // Command Line Tools install — so re-check every time the window opens.
        verifyInterpreter()
    }

    // MARK: General tab content

    private func makeGeneralContent() -> NSView {
        let column = makeColumn()

        column.addArrangedSubview(makeSectionHeader("Explanations"))

        explainTermsBox = makeCheckbox(
            title: "Explain music terms",
            help: "Adds plain-English explanations to tooltips and panels.",
            isOn: environment.explainsMusicTerms
        ) { isOn in
            AppEnvironment.shared.explainsMusicTerms = isOn
            StatusCenter.shared.info(
                isOn
                    ? "Music terms will be explained in tooltips."
                    : "Music term explanations are off. You can turn them back on here any time."
            )
        }
        addSetting(
            explainTermsBox,
            caption: "Adds plain-English explanations to tooltips and panels. Turn this off once the words are familiar.",
            to: column
        )

        welcomeBox = makeCheckbox(
            title: "Show the welcome window when Neon Studio opens",
            help: "Opens the window that lists your songs and the bundled examples at launch.",
            isOn: environment.showsWelcomeOnLaunch
        ) { isOn in
            AppEnvironment.shared.showsWelcomeOnLaunch = isOn
            StatusCenter.shared.info(
                isOn
                    ? "The welcome window will open at launch."
                    : "Neon Studio will open straight into a song. The welcome window is still in the Window menu."
            )
        }
        addSetting(
            welcomeBox,
            caption: "The welcome window lists your songs and the examples. With this off, Neon Studio goes straight to a song.",
            to: column
        )

        confirmDeleteBox = makeCheckbox(
            title: "Ask before deleting tracks",
            help: environment.help("Shows a confirmation before a delete removes a track and everything on it.", term: "Track"),
            isOn: environment.confirmsDestructiveEdits
        ) { isOn in
            AppEnvironment.shared.confirmsDestructiveEdits = isOn
            StatusCenter.shared.info(
                isOn
                    ? "Deleting a track will ask first."
                    : "Deleting a track will happen straight away. ⌘Z still undoes it."
            )
        }
        addSetting(
            confirmDeleteBox,
            caption: "With this off, a delete happens immediately. Undo (⌘Z) brings the track back either way.",
            to: column
        )

        addSeparator(to: column)
        column.addArrangedSubview(makeSectionHeader("Guided tour"))

        let tourButton = Controls.button(
            title: "Replay the guided tour next time a project opens",
            symbol: "sparkles",
            help: "Shows the short walkthrough of the arrangement, the mixer and the transport controls again."
        ) {
            AppEnvironment.shared.hasSeenTour = false
            StatusCenter.shared.info(
                "The guided tour will run the next time you open a song.",
                detail: "Open a song, or close and reopen the one you have, to see it."
            )
        }
        column.addArrangedSubview(tourButton)
        column.setCustomSpacing(2, after: tourButton)
        column.addArrangedSubview(
            indented(
                makeCaption("The tour points at the arrangement, the mixer and the transport controls, one step at a time."),
                by: 2
            )
        )

        addSeparator(to: column)
        column.addArrangedSubview(makeSectionHeader("Where your songs live"))

        supportPathLabel = makeLabel(environment.supportRoot.path, font: Theme.Font.mono(12), color: Theme.text)
        supportPathLabel.isSelectable = true
        supportPathLabel.lineBreakMode = .byTruncatingMiddle
        supportPathLabel.toolTip = environment.supportRoot.path
        supportPathLabel.setAccessibilityLabel("Folder that holds your songs, rendered audio and helper tools")

        let revealButton = Controls.button(
            title: "Show in Finder",
            symbol: "folder",
            help: "Opens the folder that holds your songs, your rendered audio and the helper tools."
        ) {
            NSWorkspace.shared.activateFileViewerSelecting([AppEnvironment.shared.supportRoot])
        }

        let pathRow = NSStackView(views: [supportPathLabel, revealButton])
        pathRow.orientation = .horizontal
        pathRow.alignment = .firstBaseline
        pathRow.spacing = 10
        pathRow.translatesAutoresizingMaskIntoConstraints = false
        column.addArrangedSubview(pathRow)
        pathRow.widthAnchor.constraint(equalTo: column.widthAnchor).isActive = true
        column.setCustomSpacing(2, after: pathRow)
        column.addArrangedSubview(
            indented(makeCaption("Every song, rendered stem and helper script Neon Studio uses is kept in this folder."), by: 2)
        )

        restoreButton = Controls.button(
            title: "Restore hidden example projects",
            symbol: "arrow.uturn.backward",
            help: "Brings back the bundled example songs you deleted, so you can open them again."
        ) { [weak self] in
            self?.restoreExamples()
        }
        restoreRow = NSStackView(views: [restoreButton])
        restoreRow.orientation = .horizontal
        restoreRow.alignment = .centerY
        restoreRow.spacing = 8
        restoreRow.translatesAutoresizingMaskIntoConstraints = false
        column.addArrangedSubview(restoreRow)

        return column
    }

    private func restoreExamples() {
        do {
            try store.restoreDeletedFactoryProjects()
            StatusCenter.shared.success(
                "The example songs are back.",
                detail: "Open the welcome window to see them."
            )
        } catch {
            StatusCenter.shared.failure("Couldn't restore the example songs", error: error, window: window)
        }
        refresh()
    }

    // MARK: Audio & Tools tab content

    private func makeToolsContent() -> NSView {
        let column = makeColumn()

        column.addArrangedSubview(makeSectionHeader("Python interpreter"))
        column.addArrangedSubview(
            makeCaption("Neon Studio runs Python to render audio, check the mix and read transcripts. Leave this empty to let Neon Studio find one for you.")
        )

        interpreterField = CommitTextField(string: environment.configuredPythonPath ?? "")
        interpreterField.placeholderString = "Found automatically"
        interpreterField.font = Theme.Font.mono(12)
        interpreterField.toolTip = "The full path of the python3 program to run, for example /opt/homebrew/bin/python3."
        interpreterField.setAccessibilityLabel("Python interpreter path")
        interpreterField.setAccessibilityHelp("The full path of the python3 program Neon Studio should run.")
        interpreterField.translatesAutoresizingMaskIntoConstraints = false
        interpreterField.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        interpreterField.setContentHuggingPriority(.defaultLow, for: .horizontal)
        interpreterField.commitHandler = { [weak self] value in
            self?.applyInterpreterPath(value)
        }

        let chooseButton = Controls.button(
            title: "Choose…",
            symbol: "folder.badge.questionmark",
            help: "Pick the python3 program yourself, if you know where it is."
        ) { [weak self] in
            self?.chooseInterpreter()
        }

        autoDetectButton = Controls.button(
            title: "Auto-detect",
            symbol: "wand.and.stars",
            help: "Tries the usual locations and picks the first Python that actually runs.",
            style: .primary
        ) { [weak self] in
            self?.autoDetectInterpreter()
        }

        let fieldRow = NSStackView(views: [interpreterField, chooseButton, autoDetectButton])
        fieldRow.orientation = .horizontal
        fieldRow.alignment = .firstBaseline
        fieldRow.spacing = 8
        fieldRow.translatesAutoresizingMaskIntoConstraints = false
        column.addArrangedSubview(fieldRow)
        NSLayoutConstraint.activate([
            fieldRow.widthAnchor.constraint(equalTo: column.widthAnchor),
            interpreterField.widthAnchor.constraint(greaterThanOrEqualToConstant: 160)
        ])

        interpreterIcon = makeStatusIcon()
        interpreterLabel = makeCaption("Checking Python…")
        interpreterLabel.preferredMaxLayoutWidth = SettingsWindowController.contentWidth - 26
        interpreterLabel.setAccessibilityLabel("Python status")

        let statusRow = NSStackView(views: [interpreterIcon, interpreterLabel])
        statusRow.orientation = .horizontal
        statusRow.alignment = .firstBaseline
        statusRow.spacing = 8
        statusRow.translatesAutoresizingMaskIntoConstraints = false
        column.addArrangedSubview(statusRow)
        column.setCustomSpacing(4, after: statusRow)

        remedyLabel = makeCaption(SettingsWindowController.remedy)
        remedyLabel.textColor = Theme.warning
        remedyRow = indented(remedyLabel, by: 24)
        remedyRow.isHidden = true
        column.addArrangedSubview(remedyRow)
        column.setCustomSpacing(4, after: remedyRow)

        let copyCommandButton = Controls.button(
            title: "Copy Terminal command",
            symbol: "doc.on.doc",
            help: "Copies “\(SettingsWindowController.installCommand)” so you can paste it into Terminal.",
            style: .quiet
        ) {
            NSPasteboard.general.clearContents()
            NSPasteboard.general.setString(SettingsWindowController.installCommand, forType: .string)
            StatusCenter.shared.success(
                "Copied “\(SettingsWindowController.installCommand)”.",
                detail: "Paste it into Terminal and press Return, then come back and click Auto-detect."
            )
        }
        copyCommandRow = indented(copyCommandButton, by: 24)
        copyCommandRow.isHidden = true
        column.addArrangedSubview(copyCommandRow)

        addSeparator(to: column)
        column.addArrangedSubview(makeSectionHeader("Helper tools"))
        column.addArrangedSubview(
            makeCaption("These ship with Neon Studio. A cross means the file is missing, so the feature beside it won't run.")
        )

        for tool in SettingsWindowController.helperTools {
            let icon = makeStatusIcon()

            let name = makeLabel(tool.file, font: Theme.Font.mono(12), color: Theme.text)
            name.widthAnchor.constraint(equalToConstant: 178).isActive = true

            let purpose = makeLabel(tool.purpose, font: Theme.Font.body(12), color: Theme.muted)
            purpose.setAccessibilityHidden(true)

            let row = NSStackView(views: [icon, name, purpose])
            row.orientation = .horizontal
            row.alignment = .firstBaseline
            row.spacing = 8
            row.translatesAutoresizingMaskIntoConstraints = false
            row.toolTip = environment.help("\(tool.file) — \(tool.purpose).", term: tool.term)
            column.addArrangedSubview(row)

            // The name label carries the whole row for VoiceOver, so the tick or
            // cross is never the only thing that says whether a tool is there.
            toolRows.append((tool: tool, icon: icon, label: name))
        }

        addSeparator(to: column)
        column.addArrangedSubview(makeSectionHeader("Audio converter"))

        afconvertIcon = makeStatusIcon()
        afconvertLabel = makeCaption("")
        afconvertLabel.preferredMaxLayoutWidth = SettingsWindowController.contentWidth - 26
        afconvertLabel.setAccessibilityLabel("Audio converter status")

        let afconvertRow = NSStackView(views: [afconvertIcon, afconvertLabel])
        afconvertRow.orientation = .horizontal
        afconvertRow.alignment = .firstBaseline
        afconvertRow.spacing = 8
        afconvertRow.translatesAutoresizingMaskIntoConstraints = false
        column.addArrangedSubview(afconvertRow)

        return column
    }

    // MARK: AI assistance tab content

    private func makeAIContent() -> NSView {
        let column = makeColumn()

        column.addArrangedSubview(makeSectionHeader("AI assistance"))
        column.addArrangedSubview(
            makeCaption(
                "With a key, Neon Studio asks a language model (Gemini) to read song descriptions, understand change requests in your own words, "
                + "pick questions for Listen With Me, and write the plain-English parts of reports. It is never required: with no key, or with this off, "
                + "every feature works from built-in rules and says so. Measurements — levels, clipping, scores — never come from the model."
            )
        )

        aiEnabledBox = makeCheckbox(
            title: "Use AI assistance when a key is available",
            help: "Lets the helper tools ask the model. Off means built-in rules only, even if a key is set.",
            isOn: environment.aiEnabled
        ) { [weak self] isOn in
            AppEnvironment.shared.aiEnabled = isOn
            StatusCenter.shared.info(
                isOn
                    ? "AI assistance is on. Tools will use the model when a key is available."
                    : "AI assistance is off. Tools use built-in rules only."
            )
            self?.refreshAIStatus()
        }
        addSetting(
            aiEnabledBox,
            caption: "Off means the tools never contact a model, even with a key saved. Each result says which path produced it.",
            to: column
        )

        addSeparator(to: column)
        column.addArrangedSubview(makeSectionHeader("Gemini API key"))

        aiKeyField = CommitSecureTextField(string: "")
        aiKeyField.placeholderString = "Paste a key from Google AI Studio"
        aiKeyField.font = Theme.Font.mono(12)
        aiKeyField.toolTip = "Saved to your Keychain the moment you press Return or leave the field. It is never written to a project, a plan, or a log."
        aiKeyField.setAccessibilityLabel("Gemini API key")
        aiKeyField.setAccessibilityHelp("Saved to the Keychain when committed. Leave empty to keep the key you already have.")
        aiKeyField.translatesAutoresizingMaskIntoConstraints = false
        aiKeyField.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        aiKeyField.setContentHuggingPriority(.defaultLow, for: .horizontal)
        aiKeyField.commitHandler = { [weak self] value in
            self?.saveAIKey(value)
        }

        aiRemoveKeyButton = Controls.button(
            title: "Remove",
            symbol: "trash",
            help: "Deletes the key from your Keychain. A key in ~/.config/neon-studio/gemini_api_key, if any, is used instead.",
            style: .quiet
        ) { [weak self] in
            self?.removeAIKey()
        }

        let keyRow = NSStackView(views: [aiKeyField, aiRemoveKeyButton])
        keyRow.orientation = .horizontal
        keyRow.alignment = .firstBaseline
        keyRow.spacing = 8
        keyRow.translatesAutoresizingMaskIntoConstraints = false
        column.addArrangedSubview(keyRow)
        NSLayoutConstraint.activate([
            keyRow.widthAnchor.constraint(equalTo: column.widthAnchor),
            aiKeyField.widthAnchor.constraint(greaterThanOrEqualToConstant: 200)
        ])

        aiKeyStatusLabel = makeCaption("")
        aiKeyStatusLabel.setAccessibilityLabel("API key status")
        column.addArrangedSubview(indented(aiKeyStatusLabel, by: 2))

        addSeparator(to: column)
        column.addArrangedSubview(makeSectionHeader("Model"))

        aiModelField = CommitTextField(string: environment.aiModel ?? "")
        aiModelField.placeholderString = "gemini-flash-latest (default)"
        aiModelField.font = Theme.Font.mono(12)
        aiModelField.toolTip = "Leave empty for the current Gemini Flash. Set a model name to use that one instead."
        aiModelField.setAccessibilityLabel("Model name")
        aiModelField.translatesAutoresizingMaskIntoConstraints = false
        aiModelField.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        aiModelField.commitHandler = { [weak self] value in
            self?.applyAIModel(value)
        }
        column.addArrangedSubview(aiModelField)
        aiModelField.widthAnchor.constraint(equalTo: column.widthAnchor).isActive = true
        column.setCustomSpacing(2, after: aiModelField)
        column.addArrangedSubview(
            indented(makeCaption("Empty means the current Gemini Flash. Answers are cached, so re-running a tool on the same song costs nothing."), by: 2)
        )

        addSeparator(to: column)
        column.addArrangedSubview(makeSectionHeader("Check it works"))

        aiTestButton = Controls.button(
            title: "Test",
            symbol: "bolt.horizontal",
            help: "Makes one tiny call to the model with the same Python and settings the tools use, and says what came back.",
            style: .primary
        ) { [weak self] in
            self?.runAIPing()
        }
        aiTestIcon = makeStatusIcon()
        aiTestLabel = makeCaption("")
        aiTestLabel.preferredMaxLayoutWidth = SettingsWindowController.contentWidth - 120
        aiTestLabel.setAccessibilityLabel("AI test result")

        let testRow = NSStackView(views: [aiTestButton, aiTestIcon, aiTestLabel])
        testRow.orientation = .horizontal
        testRow.alignment = .firstBaseline
        testRow.spacing = 8
        testRow.translatesAutoresizingMaskIntoConstraints = false
        column.addArrangedSubview(testRow)
        testRow.widthAnchor.constraint(equalTo: column.widthAnchor).isActive = true

        return column
    }

    private func saveAIKey(_ raw: String) {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        // Leaving the field empty (a stray click, a tab through) must not wipe
        // a key that is already saved; Remove is the explicit way to do that.
        guard !trimmed.isEmpty else { return }
        if environment.setGeminiAPIKey(trimmed) {
            aiKeyField.stringValue = ""
            StatusCenter.shared.success("Saved the Gemini key to your Keychain.")
        } else {
            StatusCenter.shared.warning(
                "Couldn't save the key to your Keychain.",
                detail: "As a fallback, put it in ~/.config/neon-studio/gemini_api_key."
            )
        }
        refreshAIStatus()
    }

    private func removeAIKey() {
        environment.setGeminiAPIKey("")
        aiKeyField.stringValue = ""
        StatusCenter.shared.info("Removed the Gemini key from your Keychain.")
        refreshAIStatus()
    }

    private func applyAIModel(_ raw: String) {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        environment.aiModel = trimmed.isEmpty ? nil : trimmed
        aiModelField.stringValue = trimmed
        refreshAIStatus()
    }

    /// One live call through the same interpreter and environment the tools
    /// get, so a green tick here means the tools will actually use the model.
    private func runAIPing() {
        pingToken += 1
        let token = pingToken
        runningPing?.cancel()
        runningPing = nil

        guard environment.aiEnabled else {
            setAITestStatus(.missing, message: "AI assistance is off. Turn it on above, then test.")
            return
        }
        guard let python = environment.pythonExecutable else {
            setAITestStatus(.missing, message: "No working Python — fix that under Audio & Tools first.")
            return
        }
        let script = store.toolURL("llm.py")
        guard FileManager.default.fileExists(atPath: script.path) else {
            setAITestStatus(.missing, message: "llm.py is missing from the helper tools. Reinstall Neon Studio to put it back.")
            return
        }
        setAITestStatus(.checking, message: "Asking the model…")
        aiTestButton.isEnabled = false
        runningPing = environment.toolRunner.run(
            name: "AI test",
            executable: python,
            arguments: [script.path, "--ping"],
            currentDirectory: environment.supportRoot,
            environment: environment.toolEnvironment()
        ) { [weak self] result in
            guard let self, token == self.pingToken else { return }
            self.runningPing = nil
            self.aiTestButton.isEnabled = true
            switch result {
            case .success(let output):
                self.showPing(output.lastJSONObject)
            case .failure(let error):
                self.setAITestStatus(.missing, message: "Couldn't run the test — \(error.localizedDescription)")
            }
        }
        if runningPing == nil, token == pingToken, aiTestButton.isEnabled == false {
            aiTestButton.isEnabled = true
        }
    }

    private func showPing(_ json: [String: Any]) {
        guard !json.isEmpty else {
            setAITestStatus(.missing, message: "The test finished but said nothing. Check Window ▸ Activity.")
            return
        }
        let ok = (json["ok"] as? Bool) ?? ((json["ok"] as? NSNumber)?.boolValue ?? false)
        let model = (json["model"] as? String) ?? ""
        let reason = (json["reason"] as? String) ?? ""
        let seconds: String
        if let number = json["seconds"] as? NSNumber {
            seconds = String(format: "%.1f s", number.doubleValue)
        } else {
            seconds = ""
        }
        if ok {
            let who = model.isEmpty ? "The model" : model
            setAITestStatus(.working, message: "Working — \(who) answered\(seconds.isEmpty ? "" : " in \(seconds)").")
        } else {
            let why = reason.isEmpty ? "no answer came back" : reason
            setAITestStatus(.missing, message: "Not working — \(why)")
        }
    }

    private func setAITestStatus(_ state: InterpreterState, message: String) {
        aiTestIcon.image = NSImage(systemSymbolName: state.symbol, accessibilityDescription: nil)
        aiTestIcon.contentTintColor = state.color
        aiTestLabel.stringValue = message
        aiTestLabel.textColor = state.color
        aiTestLabel.toolTip = message
        aiTestLabel.setAccessibilityValue(message)
    }

    private func refreshAIStatus() {
        guard let aiKeyStatusLabel else { return }
        environment.invalidateAIKeyCache()
        aiEnabledBox?.state = environment.aiEnabled ? .on : .off
        let source = environment.aiKeySource
        let message: String
        switch source {
        case .keychain:
            message = "A key is \(source.description). Paste a new one to replace it."
        case .file:
            message = "A key is \(source.description). Paste one here to keep it in your Keychain instead."
        case .none:
            message = "No key yet. Everything works without one; add a key to let the tools use the model."
        }
        aiKeyStatusLabel.stringValue = message
        aiKeyStatusLabel.textColor = source == .none ? Theme.muted : Theme.success
        aiKeyStatusLabel.toolTip = message
        aiKeyStatusLabel.setAccessibilityValue(message)
        aiRemoveKeyButton?.isHidden = source != .keychain
        if let aiModelField, aiModelField.currentEditor() == nil {
            aiModelField.stringValue = environment.aiModel ?? ""
        }
    }

    // MARK: Interpreter

    private func applyInterpreterPath(_ raw: String) {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        environment.configuredPythonPath = trimmed.isEmpty ? nil : trimmed
        environment.invalidateInterpreterCache()
        interpreterField.stringValue = trimmed
        if trimmed.isEmpty {
            StatusCenter.shared.info("Neon Studio will look for Python on its own.")
        }
        verifyInterpreter()
    }

    private func chooseInterpreter() {
        let panel = NSOpenPanel()
        panel.title = "Choose a Python interpreter"
        panel.message = "Pick the python3 program Neon Studio should use for rendering and analysis."
        panel.prompt = "Use This Python"
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = false
        panel.resolvesAliases = true
        // Interpreters live in /usr/bin and /opt, which the panel hides by default.
        panel.showsHiddenFiles = true
        panel.treatsFilePackagesAsDirectories = true
        // Only folders and executables can be selected — see panel(_:shouldEnable:).
        panel.delegate = self

        let current = interpreterField.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        let startPath = current.isEmpty ? "/usr/bin/python3" : current
        panel.directoryURL = URL(fileURLWithPath: startPath).deletingLastPathComponent()

        let finish: (NSApplication.ModalResponse) -> Void = { [weak self] response in
            guard let self, response == .OK, let url = panel.url else { return }
            self.applyInterpreterPath(url.path)
        }
        if let window, window.isVisible {
            panel.beginSheetModal(for: window, completionHandler: finish)
        } else {
            finish(panel.runModal())
        }
    }

    /// Restricts the open panel to folders and executable files.
    @objc func panel(_ sender: Any, shouldEnable url: URL) -> Bool {
        var isDirectory: ObjCBool = false
        guard FileManager.default.fileExists(atPath: url.path, isDirectory: &isDirectory) else { return false }
        if isDirectory.boolValue { return true }
        return FileManager.default.isExecutableFile(atPath: url.path)
    }

    private func autoDetectInterpreter() {
        autoDetectButton.isEnabled = false
        setInterpreterStatus(.checking, message: "Looking for Python…", remedy: nil)
        // Probing runs each candidate, which can take a second or two. Doing it
        // on the main thread would freeze the window mid-click.
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let found = ToolPaths.candidates.first { ToolPaths.isWorkingInterpreter(URL(fileURLWithPath: $0)) }
            DispatchQueue.main.async {
                guard let self else { return }
                self.autoDetectButton.isEnabled = true
                guard let found else {
                    self.setInterpreterStatus(
                        .missing,
                        message: "Not found — none of the usual places has a working Python.",
                        remedy: SettingsWindowController.remedy
                    )
                    StatusCenter.shared.warning(
                        "No working Python on this Mac.",
                        detail: SettingsWindowController.remedy
                    )
                    return
                }
                self.environment.configuredPythonPath = found
                self.environment.invalidateInterpreterCache()
                self.interpreterField.stringValue = found
                StatusCenter.shared.success("Neon Studio will use the Python at \(found).")
                self.verifyInterpreter()
            }
        }
    }

    /// Resolves the interpreter off the main thread, then confirms it by actually
    /// running `--version` and showing what came back.
    private func verifyInterpreter() {
        verificationToken += 1
        let token = verificationToken
        runningCheck?.cancel()
        runningCheck = nil
        setInterpreterStatus(.checking, message: "Checking Python…", remedy: nil)

        let configured = environment.configuredPythonPath
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let resolved = ToolPaths.pythonExecutable(configured: configured)
            DispatchQueue.main.async {
                guard let self, token == self.verificationToken else { return }
                guard let resolved else {
                    let message: String
                    if let configured, !configured.isEmpty {
                        message = "Not found — nothing runs at \(configured)."
                    } else {
                        message = "Not found — there's no working Python on this Mac."
                    }
                    self.setInterpreterStatus(.missing, message: message, remedy: SettingsWindowController.remedy)
                    return
                }
                self.runVersionCheck(at: resolved, token: token)
            }
        }
    }

    private func runVersionCheck(at url: URL, token: Int) {
        runningCheck = environment.toolRunner.run(
            name: "Python version",
            executable: url,
            arguments: ["--version"],
            currentDirectory: environment.supportRoot
        ) { [weak self] result in
            guard let self, token == self.verificationToken else { return }
            self.runningCheck = nil
            switch result {
            case .success(let output) where output.succeeded:
                // Python 3.4 and later print the version on stdout; older builds
                // used stderr, so take whichever one spoke.
                let raw = output.standardOutput.isEmpty ? output.standardError : output.standardOutput
                let version = SettingsWindowController.firstLine(raw)
                self.setInterpreterStatus(
                    .working,
                    message: "Working — \(version.isEmpty ? "Python" : version) at \(url.path)",
                    remedy: nil
                )
            case .success(let output):
                self.setInterpreterStatus(
                    .missing,
                    message: "Not found — \(url.path) stopped with code \(output.exitCode).",
                    remedy: SettingsWindowController.remedy
                )
            case .failure(let error):
                self.setInterpreterStatus(
                    .missing,
                    message: "Not found — \(error.localizedDescription)",
                    remedy: SettingsWindowController.remedy
                )
            }
        }
    }

    private static func firstLine(_ text: String) -> String {
        text
            .split(separator: "\n")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .first { !$0.isEmpty } ?? ""
    }

    private func setInterpreterStatus(_ state: InterpreterState, message: String, remedy: String?) {
        interpreterIcon.image = NSImage(systemSymbolName: state.symbol, accessibilityDescription: nil)
        interpreterIcon.contentTintColor = state.color
        interpreterLabel.stringValue = message
        interpreterLabel.textColor = state.color
        interpreterLabel.toolTip = message
        interpreterLabel.setAccessibilityValue(message)
        remedyLabel.stringValue = remedy ?? ""
        remedyLabel.toolTip = remedy
        remedyRow.isHidden = remedy == nil
        copyCommandRow.isHidden = remedy == nil
    }

    // MARK: Refresh

    private func refresh() {
        explainTermsBox?.state = environment.explainsMusicTerms ? .on : .off
        welcomeBox?.state = environment.showsWelcomeOnLaunch ? .on : .off
        confirmDeleteBox?.state = environment.confirmsDestructiveEdits ? .on : .off

        supportPathLabel?.stringValue = environment.supportRoot.path
        supportPathLabel?.toolTip = environment.supportRoot.path
        supportPathLabel?.setAccessibilityValue(environment.supportRoot.path)

        let hidden = store.hiddenFactoryProjectCount
        restoreRow?.isHidden = hidden == 0
        if hidden > 0, let restoreButton {
            let title = "Restore \(hidden) hidden example project\(hidden == 1 ? "" : "s")"
            restoreButton.title = title
            restoreButton.setAccessibilityLabel(title)
        }

        refreshAIStatus()

        if let interpreterField {
            let configured = environment.configuredPythonPath ?? ""
            // Never yank the text out from under someone who is mid-edit.
            if interpreterField.currentEditor() == nil, interpreterField.stringValue != configured {
                interpreterField.stringValue = configured
            }
        }

        for entry in toolRows {
            let installed = FileManager.default.fileExists(atPath: store.toolURL(entry.tool.file).path)
            entry.icon.image = NSImage(
                systemSymbolName: installed ? "checkmark.circle.fill" : "xmark.octagon.fill",
                accessibilityDescription: nil
            )
            entry.icon.contentTintColor = installed ? Theme.success : Theme.danger
            entry.label.textColor = installed ? Theme.text : Theme.danger
            entry.label.setAccessibilityLabel(
                "\(entry.tool.file), \(entry.tool.purpose), \(installed ? "installed" : "missing")"
            )
            entry.label.toolTip = installed
                ? "\(entry.tool.file) is installed. \(entry.tool.purpose)."
                : "\(entry.tool.file) is missing, so “\(entry.tool.purpose)” won't run. Reinstalling Neon Studio puts it back."
        }

        if let afconvertLabel, let afconvertIcon {
            let available = ToolPaths.afconvertAvailable
            afconvertIcon.image = NSImage(
                systemSymbolName: available ? "checkmark.circle.fill" : "xmark.octagon.fill",
                accessibilityDescription: nil
            )
            afconvertIcon.contentTintColor = available ? Theme.success : Theme.danger
            let message = available
                ? "Ready — macOS's audio converter (afconvert) is here, so vocal tuning will work."
                : "Missing — vocal tuning needs macOS's audio converter (afconvert), which isn't on this Mac."
            afconvertLabel.stringValue = message
            afconvertLabel.textColor = available ? Theme.muted : Theme.danger
            afconvertLabel.toolTip = message
            afconvertLabel.setAccessibilityValue(message)
        }
    }

    // MARK: View helpers

    private func makeColumn() -> NSStackView {
        let column = NSStackView()
        column.orientation = .vertical
        column.alignment = .leading
        column.spacing = 8
        column.translatesAutoresizingMaskIntoConstraints = false
        return column
    }

    private func makeSectionHeader(_ title: String) -> NSTextField {
        makeLabel(title.uppercased(), font: Theme.Font.captionBold(12), color: Theme.muted)
    }

    private func makeCaption(_ text: String) -> NSTextField {
        let label = makeLabel(text, font: Theme.Font.body(12), color: Theme.muted)
        label.lineBreakMode = .byWordWrapping
        label.maximumNumberOfLines = 0
        label.preferredMaxLayoutWidth = SettingsWindowController.contentWidth - 22
        return label
    }

    private func makeStatusIcon() -> NSImageView {
        let view = NSImageView()
        view.translatesAutoresizingMaskIntoConstraints = false
        view.symbolConfiguration = NSImage.SymbolConfiguration(pointSize: 12, weight: .semibold)
        view.imageScaling = .scaleProportionallyDown
        view.setAccessibilityHidden(true)
        NSLayoutConstraint.activate([
            view.widthAnchor.constraint(equalToConstant: 16),
            view.heightAnchor.constraint(equalToConstant: 16)
        ])
        return view
    }

    /// Added first, then constrained — a constraint between two views with no
    /// common ancestor throws.
    private func addSeparator(to column: NSStackView) {
        let box = Controls.separator(vertical: false)
        column.addArrangedSubview(box)
        box.widthAnchor.constraint(equalTo: column.widthAnchor).isActive = true
    }

    /// A checkbox. `Controls` has no checkbox factory because this is the only
    /// form in the app, but it reuses `ToggleButton` so the closure plumbing
    /// matches every other control here.
    private func makeCheckbox(
        title: String,
        help: String,
        isOn: Bool,
        action: @escaping (Bool) -> Void
    ) -> NSButton {
        let box = ToggleButton(title: title, target: nil, action: nil)
        box.toggleHandler = action
        box.target = box
        box.action = #selector(ToggleButton.invoke)
        box.setButtonType(.switch)
        box.state = isOn ? .on : .off
        box.font = Theme.Font.body(13)
        box.toolTip = help
        box.setAccessibilityLabel(title)
        box.setAccessibilityHelp(help)
        box.translatesAutoresizingMaskIntoConstraints = false
        return box
    }

    /// A checkbox plus the sentence saying what turning it off actually costs.
    private func addSetting(_ control: NSView, caption: String, to column: NSStackView) {
        column.addArrangedSubview(control)
        column.setCustomSpacing(2, after: control)
        column.addArrangedSubview(indented(makeCaption(caption), by: 20))
    }

    private func indented(_ view: NSView, by amount: CGFloat) -> NSView {
        let container = NSView()
        container.translatesAutoresizingMaskIntoConstraints = false
        view.translatesAutoresizingMaskIntoConstraints = false
        container.addSubview(view)
        NSLayoutConstraint.activate([
            view.leadingAnchor.constraint(equalTo: container.leadingAnchor, constant: amount),
            container.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            view.topAnchor.constraint(equalTo: container.topAnchor),
            container.bottomAnchor.constraint(equalTo: view.bottomAnchor)
        ])
        return container
    }

    /// Both tabs scroll: "Audio & Tools" is taller than the window on purpose,
    /// because truncating the tool list would hide the exact row somebody is
    /// looking for.
    private func scrollable(_ content: NSView) -> NSScrollView {
        let scroll = NSScrollView()
        scroll.translatesAutoresizingMaskIntoConstraints = false
        scroll.hasVerticalScroller = true
        scroll.hasHorizontalScroller = false
        scroll.autohidesScrollers = true
        scroll.drawsBackground = false
        scroll.borderType = .noBorder

        let document = FlippedContainer()
        document.translatesAutoresizingMaskIntoConstraints = false
        document.addSubview(content)
        NSLayoutConstraint.activate([
            content.leadingAnchor.constraint(equalTo: document.leadingAnchor, constant: 18),
            document.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: 18),
            content.topAnchor.constraint(equalTo: document.topAnchor, constant: 16),
            document.bottomAnchor.constraint(equalTo: content.bottomAnchor, constant: 16)
        ])
        scroll.documentView = document
        NSLayoutConstraint.activate([
            document.leadingAnchor.constraint(equalTo: scroll.contentView.leadingAnchor),
            document.topAnchor.constraint(equalTo: scroll.contentView.topAnchor),
            document.widthAnchor.constraint(equalTo: scroll.contentView.widthAnchor)
        ])
        return scroll
    }

    /// `NSTabView` sets the frame of its item views, so the item view uses
    /// autoresizing and everything inside it uses constraints.
    private func tabContainer(_ view: NSView) -> NSView {
        let host = NSView()
        host.autoresizingMask = [.width, .height]
        host.addSubview(view)
        NSLayoutConstraint.activate([
            view.leadingAnchor.constraint(equalTo: host.leadingAnchor),
            view.trailingAnchor.constraint(equalTo: host.trailingAnchor),
            view.topAnchor.constraint(equalTo: host.topAnchor),
            view.bottomAnchor.constraint(equalTo: host.bottomAnchor)
        ])
        return host
    }
}

/// Top-down layout inside the scroll views, so content grows downwards and the
/// view opens on the first setting rather than the last.
private final class FlippedContainer: NSView {
    override var isFlipped: Bool { true }
}

/// `CommitTextField` for secrets: the same commit-on-Return-or-blur contract,
/// drawn as dots. Lives here because the API key field is the only one.
private final class CommitSecureTextField: NSSecureTextField, NSTextFieldDelegate {
    var commitHandler: ((String) -> Void)?

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        commonInit()
    }

    convenience init(string: String) {
        self.init(frame: .zero)
        stringValue = string
    }

    required init?(coder: NSCoder) {
        super.init(coder: coder)
        commonInit()
    }

    private func commonInit() {
        delegate = self
        isBezeled = true
        bezelStyle = .roundedBezel
        isEditable = true
        isSelectable = true
    }

    func controlTextDidEndEditing(_ obj: Notification) {
        commitHandler?(stringValue)
    }
}
