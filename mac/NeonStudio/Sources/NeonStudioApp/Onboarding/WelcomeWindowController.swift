import AppKit
import NeonStudioKit

/// The first thing a new user sees.
///
/// Before this existed, launching Neon Studio dropped somebody who had never
/// opened a DAW straight into a dense three-column editor, and if their library
/// happened to be empty the only guidance on screen was one grey line of small
/// text naming a folder path. This window replaces that with three obvious ways
/// in — open an example, describe a song, or start blank — next to a short
/// explainer written for someone who does not yet know what a track is.
///
/// Everything here is a real AppKit control, so hover, pressed, disabled, focus
/// ring, keyboard operation and VoiceOver all behave the way they do in any
/// other Mac app: Return takes the first choice, Escape closes, and the arrow
/// keys move through the song list.
public final class WelcomeWindowController: NSWindowController, NSTableViewDataSource, NSTableViewDelegate {

    public static let shared = WelcomeWindowController()

    /// Posted when the user asks for the guided tour. The frontmost document
    /// window listens and calls into `TourController`; this window deliberately
    /// knows nothing about which window that is.
    public static let startTourNotification = Notification.Name("NeonStudioStartTour")

    // MARK: Layout constants
    //
    // One definition each, used by both the constraints and the text wrapping
    // widths, so the two can't drift apart.

    private enum Layout {
        static let windowSize = NSSize(width: 720, height: 520)
        static let padding: CGFloat = 20
        static let columnGap: CGFloat = 20
        static let leftColumnWidth: CGFloat = 364
        /// 720 − 2×20 padding − 364 left − 2×20 gap − 1 separator.
        static let rightColumnWidth: CGFloat = 275
        static let explainerTextWidth: CGFloat = rightColumnWidth - 13
        static let choiceHeight: CGFloat = 58
        static let rowHeight: CGFloat = 44
        /// A floor, not a fixed height: the list is the one part of the column
        /// that grows to take up whatever height is left over. Low enough that
        /// the column still fits the window when the "put the examples back"
        /// row appears.
        static let listMinimumHeight: CGFloat = 84
    }

    // MARK: State

    private var projects: [LocalProject] = []

    // MARK: Views

    private let projectTable = NSTableView()
    private let listCard = ThemedView(
        backgroundColor: Theme.panel,
        borderColor: Theme.subtleStroke,
        cornerRadius: Theme.Metric.cornerRadius
    )
    private let listSlot = NSView()
    private var emptyState: EmptyStateView?
    /// Which of the two empty states is currently installed, so it is only
    /// rebuilt when the situation actually changes.
    private var emptyStateOffersRestore: Bool?
    private var openChoice: NSButton!
    private var restoreExamplesButton: NSButton!
    private var showOnLaunchCheckbox: NSButton!

    // MARK: Lifecycle

    private init() {
        let window = NSWindow(
            contentRect: NSRect(origin: .zero, size: Layout.windowSize),
            // No `.resizable`: this window has one job and a fixed amount to
            // say, and a beginner resizing it can only make it worse.
            styleMask: [.titled, .closable],
            backing: .buffered,
            defer: false
        )
        window.title = "Welcome to Neon Studio"
        // The shared instance outlives every close, so the window must not be
        // deallocated out from under it.
        window.isReleasedWhenClosed = false
        super.init(window: window)
        shouldCascadeWindows = false
        window.contentView = buildContent()
        window.initialFirstResponder = projectTable
        window.center()
    }

    required init?(coder: NSCoder) {
        fatalError("WelcomeWindowController is created in code, not from a nib.")
    }

    /// Shows the window, refreshing the song list first so a project saved since
    /// the last time it was open shows up.
    public func present() {
        reloadProjects()
        showOnLaunchCheckbox.state = AppEnvironment.shared.showsWelcomeOnLaunch ? .on : .off
        // Refreshing the list can add a row of controls, and a window that is
        // already on screen does not re-fit itself. Without this the extra row
        // would squeeze the buttons above it instead.
        if let content = window?.contentView {
            content.layoutSubtreeIfNeeded()
            window?.setContentSize(NSSize(
                width: Layout.windowSize.width,
                height: max(Layout.windowSize.height, content.fittingSize.height)
            ))
        }
        window?.center()
        showWindow(nil)
        window?.makeKeyAndOrderFront(nil)
    }

    /// Escape closes, from anywhere in the window.
    public override func cancelOperation(_ sender: Any?) {
        close()
    }

    // MARK: Content

    private func buildContent() -> NSView {
        let root = ThemedView(backgroundColor: Theme.app)
        root.onCancel = { [weak self] in self?.close() }

        let separator = Controls.separator(vertical: false)
        let footer = buildFooter()
        let stack = NSStackView(views: [
            buildHeader(),
            buildColumns(),
            separator,
            footer
        ])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.distribution = .fill
        stack.spacing = 14
        stack.translatesAutoresizingMaskIntoConstraints = false
        root.addSubview(stack)

        // The rule and the footer span the window; a vertical stack aligned to
        // its leading edge would otherwise leave both at their natural width,
        // which would park the tour button next to the checkbox.
        for row in [separator, footer] {
            NSLayoutConstraint.activate([
                row.leadingAnchor.constraint(equalTo: stack.leadingAnchor),
                row.trailingAnchor.constraint(equalTo: stack.trailingAnchor)
            ])
        }

        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: root.leadingAnchor, constant: Layout.padding),
            stack.trailingAnchor.constraint(equalTo: root.trailingAnchor, constant: -Layout.padding),
            stack.topAnchor.constraint(equalTo: root.topAnchor, constant: Layout.padding),
            stack.bottomAnchor.constraint(equalTo: root.bottomAnchor, constant: -Layout.padding),
            root.widthAnchor.constraint(equalToConstant: Layout.windowSize.width),
            root.heightAnchor.constraint(greaterThanOrEqualToConstant: Layout.windowSize.height)
        ])
        return root
    }

    private func buildHeader() -> NSView {
        let icon = NSImageView()
        icon.image = NSApp.applicationIconImage
            ?? NSImage(systemSymbolName: "waveform", accessibilityDescription: nil)
        icon.imageScaling = .scaleProportionallyUpOrDown
        icon.translatesAutoresizingMaskIntoConstraints = false
        icon.setAccessibilityElement(false)
        NSLayoutConstraint.activate([
            icon.widthAnchor.constraint(equalToConstant: 44),
            icon.heightAnchor.constraint(equalToConstant: 44)
        ])

        let title = makeLabel("Welcome to Neon Studio", font: Theme.Font.title(19), color: Theme.text)
        let subtitle = wrappingLabel(
            "Build a song out of layers you can hear and change. Hover anything to find out what it does.",
            width: Layout.windowSize.width - (Layout.padding * 2) - 56,
            font: Theme.Font.body(13),
            color: Theme.muted
        )

        let text = NSStackView(views: [title, subtitle])
        text.orientation = .vertical
        text.alignment = .leading
        text.spacing = 3
        text.translatesAutoresizingMaskIntoConstraints = false

        let header = NSStackView(views: [icon, text])
        header.orientation = .horizontal
        header.alignment = .centerY
        header.spacing = 12
        header.translatesAutoresizingMaskIntoConstraints = false
        header.setAccessibilityRole(.group)
        header.setAccessibilityLabel("Welcome to Neon Studio")
        // Required, not merely high: any spare height in the window belongs to
        // the song list, and a stack view will happily stretch a row that only
        // hugs its content weakly.
        header.setHuggingPriority(.required, for: .vertical)
        return header
    }

    private func buildColumns() -> NSView {
        let left = buildChoices()
        let separator = Controls.separator(vertical: true)
        let right = buildExplainer()

        let columns = NSStackView(views: [left, separator, right])
        columns.orientation = .horizontal
        columns.alignment = .top
        columns.distribution = .fill
        columns.spacing = Layout.columnGap
        columns.translatesAutoresizingMaskIntoConstraints = false

        NSLayoutConstraint.activate([
            left.widthAnchor.constraint(equalToConstant: Layout.leftColumnWidth),
            right.widthAnchor.constraint(equalToConstant: Layout.rightColumnWidth),
            separator.topAnchor.constraint(equalTo: columns.topAnchor),
            separator.bottomAnchor.constraint(equalTo: columns.bottomAnchor)
        ])
        columns.setHuggingPriority(.defaultLow, for: .vertical)
        return columns
    }

    // MARK: Left column — the three ways in

    private func buildChoices() -> NSView {
        let openSongChoice = makeChoice(
            symbol: "music.note.list",
            title: "Open a song to explore",
            detail: "Pick one of the songs below and press Play to hear it.",
            help: openChoiceHelp,
            action: { [weak self] in self?.openSelectedProject() }
        )
        // Return takes the first choice. `keyEquivalentModifierMask` has to be
        // cleared explicitly: an NSButton defaults to ⌘ as its modifier.
        openSongChoice.keyEquivalent = "\r"
        openSongChoice.keyEquivalentModifierMask = []
        openChoice = openSongChoice

        let describeChoice = makeChoice(
            symbol: "wand.and.stars",
            title: "Start from a description",
            detail: "Describe a song in plain words and Neon Studio builds the tracks for you.",
            help: AppEnvironment.shared.help(
                "Creates a new project, then asks you for a text file describing the song you want.",
                term: "Transcript"
            ),
            action: { [weak self] in self?.startFromDescription() }
        )

        let emptyChoice = makeChoice(
            symbol: "plus.rectangle.on.rectangle",
            title: "Start with an empty project",
            detail: "A blank song with one empty track, ready for your own audio.",
            help: AppEnvironment.shared.help(
                "Creates a new project with a single empty track. Add your own audio files to it.",
                term: "Track"
            ),
            action: { [weak self] in self?.startEmptyProject() }
        )

        let openExisting = Controls.button(
            title: "Open an existing project…",
            symbol: "folder",
            help: "Choose a Neon Studio project file (.neon.json) you already have.",
            action: { [weak self] in self?.openExistingProject() }
        )
        openExisting.alignment = .left

        restoreExamplesButton = Controls.button(
            title: "Put the example songs back",
            symbol: "arrow.uturn.backward",
            help: "The example songs that came with Neon Studio were deleted. This puts them back.",
            action: { [weak self] in self?.restoreExampleSongs() }
        )
        restoreExamplesButton.alignment = .left
        restoreExamplesButton.isHidden = true

        // Stacked rather than side by side: two full-length button titles do not
        // fit across this column, and squeezing them truncates both. The restore
        // button is hidden unless it is needed, and a hidden arranged subview
        // takes no space, so normally this is a single row.
        let secondary = NSStackView(views: [openExisting, restoreExamplesButton])
        secondary.orientation = .vertical
        secondary.alignment = .leading
        secondary.spacing = 6
        secondary.translatesAutoresizingMaskIntoConstraints = false
        // Spare vertical space in this column belongs to the song list, not to
        // the buttons under it.
        secondary.setHuggingPriority(.required, for: .vertical)

        let column = NSStackView(views: [
            openSongChoice,
            buildProjectList(),
            describeChoice,
            emptyChoice,
            secondary
        ])
        column.orientation = .vertical
        column.alignment = .leading
        column.distribution = .fill
        column.spacing = 8
        column.translatesAutoresizingMaskIntoConstraints = false
        column.setAccessibilityRole(.group)
        column.setAccessibilityLabel("Ways to start")

        for view in [openSongChoice, describeChoice, emptyChoice] {
            NSLayoutConstraint.activate([
                view.leadingAnchor.constraint(equalTo: column.leadingAnchor),
                view.trailingAnchor.constraint(equalTo: column.trailingAnchor),
                view.heightAnchor.constraint(equalToConstant: Layout.choiceHeight)
            ])
        }
        NSLayoutConstraint.activate([
            listSlot.leadingAnchor.constraint(equalTo: column.leadingAnchor),
            listSlot.trailingAnchor.constraint(equalTo: column.trailingAnchor),
            secondary.leadingAnchor.constraint(equalTo: column.leadingAnchor)
        ])
        return column
    }

    /// The song list plus the empty state that stands in for it. Both live in
    /// the same slot so the column height never jumps between the two.
    private func buildProjectList() -> NSView {
        projectTable.headerView = nil
        projectTable.style = .inset
        projectTable.rowHeight = Layout.rowHeight
        projectTable.rowSizeStyle = .custom
        projectTable.gridStyleMask = []
        projectTable.usesAlternatingRowBackgroundColors = false
        projectTable.backgroundColor = Theme.panel
        projectTable.allowsMultipleSelection = false
        projectTable.allowsEmptySelection = false
        projectTable.allowsColumnResizing = false
        projectTable.dataSource = self
        projectTable.delegate = self
        projectTable.target = self
        projectTable.doubleAction = #selector(handleDoubleClick)
        projectTable.toolTip = AppEnvironment.shared.help(
            "The songs in your library. Select one and press Return, or double-click it, to open it.",
            term: "Track"
        )
        projectTable.setAccessibilityLabel("Songs in your library")
        projectTable.setAccessibilityHelp("Select a song, then press Return to open it.")

        let column = NSTableColumn(identifier: NSUserInterfaceItemIdentifier("song"))
        column.title = "Song"
        column.resizingMask = .autoresizingMask
        projectTable.addTableColumn(column)

        let scroll = NSScrollView()
        scroll.documentView = projectTable
        scroll.hasVerticalScroller = true
        scroll.autohidesScrollers = true
        scroll.borderType = .noBorder
        scroll.drawsBackground = false
        scroll.translatesAutoresizingMaskIntoConstraints = false

        listCard.translatesAutoresizingMaskIntoConstraints = false
        listCard.addSubview(scroll)

        listSlot.translatesAutoresizingMaskIntoConstraints = false
        listSlot.addSubview(listCard)

        NSLayoutConstraint.activate([
            scroll.leadingAnchor.constraint(equalTo: listCard.leadingAnchor, constant: 1),
            scroll.trailingAnchor.constraint(equalTo: listCard.trailingAnchor, constant: -1),
            scroll.topAnchor.constraint(equalTo: listCard.topAnchor, constant: 1),
            scroll.bottomAnchor.constraint(equalTo: listCard.bottomAnchor, constant: -1),

            listCard.leadingAnchor.constraint(equalTo: listSlot.leadingAnchor),
            listCard.trailingAnchor.constraint(equalTo: listSlot.trailingAnchor),
            listCard.topAnchor.constraint(equalTo: listSlot.topAnchor),
            listCard.bottomAnchor.constraint(equalTo: listSlot.bottomAnchor),

            listSlot.heightAnchor.constraint(greaterThanOrEqualToConstant: Layout.listMinimumHeight)
        ])
        // The list is the one thing in the column that should absorb spare
        // height, so it hugs less strongly than the fixed-height choices.
        listSlot.setContentHuggingPriority(.defaultLow, for: .vertical)
        return listSlot
    }

    // MARK: Right column — what any of this means

    private func buildExplainer() -> NSView {
        let heading = makeLabel("What is this?", font: Theme.Font.title(15), color: Theme.text)

        let body = NSStackView()
        body.orientation = .vertical
        body.alignment = .leading
        body.spacing = 10
        body.translatesAutoresizingMaskIntoConstraints = false

        // Wording comes from `Glossary` wherever a term exists, so the tour, the
        // tooltips and this explainer can never drift into saying different
        // things about the same word.
        let paragraphs: [(String, String)] = [
            (
                "A track is one sound",
                Glossary.long("Track")
            ),
            (
                "Time runs left to right",
                Glossary.long("Bar")
            ),
            (
                "Clips are the blocks you move",
                "\(Glossary.short("Clip")) Drag one sideways to change when it plays, or drag its edge to make it longer."
            ),
            (
                "You cannot break anything",
                "Every change can be undone with Command-Z, and the Edit menu names the step it will undo — “Undo Move Clip”, not a bare “Undo”."
            ),
            (
                "AI assistance is optional",
                "Add a Gemini key under Settings ▸ AI assistance and Neon Studio reads descriptions and change requests with a language model; without one, everything still works from built-in rules and says so."
            )
        ]

        for (title, text) in paragraphs {
            let titleLabel = wrappingLabel(
                title,
                width: Layout.explainerTextWidth,
                font: Theme.Font.emphasis(13),
                color: Theme.text
            )
            let bodyLabel = wrappingLabel(
                text,
                width: Layout.explainerTextWidth,
                font: Theme.Font.body(12),
                color: Theme.muted
            )
            let group = NSStackView(views: [titleLabel, bodyLabel])
            group.orientation = .vertical
            group.alignment = .leading
            group.spacing = 2
            group.translatesAutoresizingMaskIntoConstraints = false
            group.setAccessibilityRole(.group)
            group.setAccessibilityLabel(title)
            body.addArrangedSubview(group)
            group.widthAnchor.constraint(equalTo: body.widthAnchor).isActive = true
        }

        // Flipped clip view so the text starts at the top rather than the
        // bottom, and scrolls only if a long-word-wrapping locale needs it to.
        let clip = FlippedClipView()
        clip.drawsBackground = false

        let scroll = NSScrollView()
        scroll.contentView = clip
        scroll.documentView = body
        scroll.hasVerticalScroller = true
        scroll.autohidesScrollers = true
        scroll.borderType = .noBorder
        scroll.drawsBackground = false
        scroll.translatesAutoresizingMaskIntoConstraints = false
        scroll.setAccessibilityLabel("What is this?")

        NSLayoutConstraint.activate([
            body.topAnchor.constraint(equalTo: clip.topAnchor),
            body.leadingAnchor.constraint(equalTo: clip.leadingAnchor),
            body.trailingAnchor.constraint(equalTo: clip.trailingAnchor)
        ])

        let column = NSStackView(views: [heading, scroll])
        column.orientation = .vertical
        column.alignment = .leading
        column.distribution = .fill
        column.spacing = 10
        column.translatesAutoresizingMaskIntoConstraints = false
        column.setAccessibilityRole(.group)
        column.setAccessibilityLabel("What is this?")
        NSLayoutConstraint.activate([
            scroll.leadingAnchor.constraint(equalTo: column.leadingAnchor),
            scroll.trailingAnchor.constraint(equalTo: column.trailingAnchor)
        ])
        scroll.setContentHuggingPriority(.defaultLow, for: .vertical)
        return column
    }

    // MARK: Footer

    private func buildFooter() -> NSView {
        showOnLaunchCheckbox = NSButton(
            checkboxWithTitle: "Show this when Neon Studio opens",
            target: self,
            action: #selector(toggleShowOnLaunch(_:))
        )
        showOnLaunchCheckbox.font = Theme.Font.body(13)
        showOnLaunchCheckbox.state = AppEnvironment.shared.showsWelcomeOnLaunch ? .on : .off
        showOnLaunchCheckbox.toolTip = "When this is off, Neon Studio opens straight into your last song. You can bring this window back from the Help menu."
        showOnLaunchCheckbox.setAccessibilityLabel("Show this window when Neon Studio opens")
        showOnLaunchCheckbox.setAccessibilityHelp("Turn off to go straight to your song next time.")
        showOnLaunchCheckbox.translatesAutoresizingMaskIntoConstraints = false

        let spacer = NSView()
        spacer.translatesAutoresizingMaskIntoConstraints = false
        spacer.setContentHuggingPriority(.defaultLow, for: .horizontal)
        spacer.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)

        let tour = Controls.button(
            title: "Take the tour",
            symbol: "map",
            help: "A short guided walkthrough that points at each part of the window and says what it is for.",
            action: { [weak self] in self?.takeTour() }
        )

        let footer = NSStackView(views: [showOnLaunchCheckbox, spacer, tour])
        footer.orientation = .horizontal
        footer.alignment = .centerY
        footer.distribution = .fill
        footer.spacing = 12
        footer.translatesAutoresizingMaskIntoConstraints = false
        footer.setHuggingPriority(.required, for: .vertical)
        return footer
    }

    // MARK: Choice rows

    /// A large row that reads as one obvious choice: symbol, a title, and a
    /// sentence saying what happens if you press it.
    private func makeChoice(
        symbol: String,
        title: String,
        detail: String,
        help: String,
        action: @escaping () -> Void
    ) -> NSButton {
        let button = Controls.button(title: title, symbol: symbol, help: help, action: action)
        button.bezelStyle = .regularSquare
        button.alignment = .left
        button.imagePosition = .imageLeading
        button.imageHugsTitle = true
        button.imageScaling = .scaleProportionallyDown
        if let image = NSImage(systemSymbolName: symbol, accessibilityDescription: nil)?
            .withSymbolConfiguration(NSImage.SymbolConfiguration(pointSize: 19, weight: .regular)) {
            button.image = image
        }
        if let cell = button.cell as? NSButtonCell {
            cell.usesSingleLineMode = false
            cell.lineBreakMode = .byWordWrapping
            cell.wraps = true
        }
        button.setAccessibilityLabel(title)
        button.setAccessibilityHelp("\(detail) \(help)")
        applyChoiceText(to: button, title: title, detail: detail)
        return button
    }

    private func applyChoiceText(to button: NSButton, title: String, detail: String) {
        let paragraph = NSMutableParagraphStyle()
        paragraph.alignment = .left
        paragraph.lineBreakMode = .byWordWrapping
        paragraph.lineSpacing = 1

        let text = NSMutableAttributedString(
            string: title + "\n",
            attributes: [
                .font: Theme.Font.title(14),
                .foregroundColor: Theme.text,
                .paragraphStyle: paragraph
            ]
        )
        text.append(NSAttributedString(
            string: detail,
            attributes: [
                .font: Theme.Font.body(12),
                .foregroundColor: Theme.muted,
                .paragraphStyle: paragraph
            ]
        ))
        button.attributedTitle = text
    }

    /// Kept in one place because it is used when the button is built and again
    /// every time the selected song changes.
    private var openChoiceHelp: String {
        AppEnvironment.shared.help(
            "Opens the song selected in the list below, in a new window. Nothing you do to it changes the original.",
            term: "Track"
        )
    }

    // MARK: Data

    private func reloadProjects() {
        let store = AppEnvironment.shared.store
        projects = store.loadProjects().sorted {
            $0.name.localizedStandardCompare($1.name) == .orderedAscending
        }
        projectTable.reloadData()

        let hasProjects = !projects.isEmpty
        let removedExamples = store.hiddenFactoryProjectCount > 0
        listCard.isHidden = !hasProjects
        openChoice.isEnabled = hasProjects
        updateEmptyState(hasProjects: hasProjects, offeringRestore: removedExamples)
        // Restoring the examples is offered in exactly one place: down here when
        // there is still a list to add them back to, and inside the empty state
        // when there is not.
        restoreExamplesButton.isHidden = !removedExamples || !hasProjects

        if hasProjects, projectTable.selectedRow < 0 {
            projectTable.selectRowIndexes(IndexSet(integer: 0), byExtendingSelection: false)
        }
        updateOpenChoiceDetail()
    }

    /// Swaps in whichever empty state fits the situation. Neither version
    /// repeats a button that is already sitting a few pixels below it: with the
    /// examples deleted the fix is to put them back, and otherwise the way
    /// forward is the choices around the box.
    private func updateEmptyState(hasProjects: Bool, offeringRestore: Bool) {
        guard !hasProjects else {
            emptyState?.isHidden = true
            return
        }
        if emptyState == nil || emptyStateOffersRestore != offeringRestore {
            emptyState?.removeFromSuperview()
            let view: EmptyStateView
            if offeringRestore {
                view = EmptyStateView(
                    symbol: "arrow.uturn.backward",
                    title: "The example songs were deleted",
                    body: "Put them back to have something to open, or start a song of your own with one of the choices around this box.",
                    actionTitle: "Put the example songs back",
                    action: { [weak self] in self?.restoreExampleSongs() }
                )
            } else {
                view = EmptyStateView(
                    symbol: "tray",
                    title: "No songs in your library yet",
                    body: "Start a song with one of the choices above or below, and it will show up in this list next time."
                )
            }
            listSlot.addSubview(view)
            NSLayoutConstraint.activate([
                view.leadingAnchor.constraint(equalTo: listSlot.leadingAnchor),
                view.trailingAnchor.constraint(equalTo: listSlot.trailingAnchor),
                view.topAnchor.constraint(equalTo: listSlot.topAnchor),
                view.bottomAnchor.constraint(equalTo: listSlot.bottomAnchor)
            ])
            emptyState = view
            emptyStateOffersRestore = offeringRestore
        }
        emptyState?.isHidden = false
    }

    /// The first choice names the song it will open, so pressing Return is never
    /// a guess about which one you are about to get.
    private func updateOpenChoiceDetail() {
        let title = "Open a song to explore"
        let detail: String
        let label: String
        if let project = selectedProject() {
            let count = project.snapshot.tracks.count
            detail = "Opens “\(project.name)” — \(count) \(count == 1 ? "track" : "tracks") you can play and change."
            label = "Open \(project.name)"
        } else {
            detail = projects.isEmpty
                ? "There are no songs in your library to open yet."
                : "Pick one of the songs below and press Play to hear it."
            label = title
        }
        applyChoiceText(to: openChoice, title: title, detail: detail)
        openChoice.setAccessibilityLabel(label)
        openChoice.setAccessibilityHelp("\(detail) \(openChoiceHelp)")
    }

    private func selectedProject() -> LocalProject? {
        let row = projectTable.selectedRow
        guard row >= 0, row < projects.count else { return nil }
        return projects[row]
    }

    private func describe(_ project: LocalProject) -> String {
        let bpm = Int(project.snapshot.bpm.rounded())
        let count = project.snapshot.tracks.count
        return "\(bpm) BPM · \(count) \(count == 1 ? "track" : "tracks")"
    }

    // MARK: Actions

    @objc private func handleDoubleClick() {
        guard projectTable.clickedRow >= 0 else { return }
        openSelectedProject()
    }

    private func openSelectedProject() {
        guard let project = selectedProject() else {
            StatusCenter.shared.warning(
                "Select a song first.",
                detail: "Click one of the songs in the list, then press Return."
            )
            return
        }
        let store = AppEnvironment.shared.store
        let isExample = store.isFactoryProject(project.id)
        do {
            // Open the real file rather than an untitled copy, so ⌘S saves back
            // where the user expects and the window gets a working proxy icon.
            // For a bundled example this makes the user's own copy first, leaving
            // the pristine original in place for next time.
            let url = try store.fileURLForEditing(project)
            NSDocumentController.shared.openDocument(
                withContentsOf: url,
                display: true
            ) { [weak self] document, _, error in
                guard let self else { return }
                if let error {
                    StatusCenter.shared.failure(
                        "Couldn't open “\(project.name)”.",
                        error: error,
                        window: self.window
                    )
                    return
                }
                (document as? NeonDocument)?.libraryURL = url
                self.close()
                StatusCenter.shared.success(
                    isExample
                        ? "Opened your copy of the example “\(project.name)”."
                        : "Opened “\(project.name)”.",
                    detail: "Press Space to play it. Anything you change can be undone with ⌘Z."
                )
            }
        } catch {
            StatusCenter.shared.failure(
                "Couldn't open “\(project.name)”.",
                error: error,
                window: window
            )
        }
    }

    private func startFromDescription() {
        close()
        NSDocumentController.shared.newDocument(nil)
        guard let controller = frontDocumentWindowController() else {
            StatusCenter.shared.warning(
                "Couldn't open a new project window.",
                detail: "Make a new project with File ▸ New, then choose to build it from a description."
            )
            return
        }
        // Let the new window finish becoming key before it puts up a sheet;
        // a sheet on a window that isn't on screen yet is invisible.
        DispatchQueue.main.async {
            controller.materializeTranscript()
        }
    }

    private func startEmptyProject() {
        close()
        NSDocumentController.shared.newDocument(nil)
        StatusCenter.shared.info(
            "Started a new song.",
            detail: "It has one empty track. Drop an audio file on it, or add more tracks."
        )
    }

    private func openExistingProject() {
        close()
        NSDocumentController.shared.openDocument(nil)
    }

    private func restoreExampleSongs() {
        do {
            try AppEnvironment.shared.store.restoreDeletedFactoryProjects()
            reloadProjects()
            StatusCenter.shared.success("Put the example songs back in your library.")
        } catch {
            StatusCenter.shared.failure(
                "Couldn't restore the example songs.",
                error: error,
                window: window
            )
        }
    }

    private func takeTour() {
        close()
        if frontDocumentWindowController() == nil {
            // The tour points at parts of a document window, so there has to be
            // one to point at.
            NSDocumentController.shared.newDocument(nil)
        }
        DispatchQueue.main.async {
            NotificationCenter.default.post(
                name: WelcomeWindowController.startTourNotification,
                object: nil
            )
        }
    }

    @objc private func toggleShowOnLaunch(_ sender: NSButton) {
        let isOn = sender.state == .on
        AppEnvironment.shared.showsWelcomeOnLaunch = isOn
        StatusCenter.shared.info(
            isOn
                ? "This window will open with Neon Studio."
                : "This window won't open automatically any more.",
            detail: "You can change this in Settings, or reopen it from the Help menu."
        )
    }

    private func frontDocumentWindowController() -> DocumentWindowController? {
        if let controller = NSDocumentController.shared.currentDocument?
            .windowControllers
            .compactMap({ $0 as? DocumentWindowController })
            .first {
            return controller
        }
        return NSApp.windows.compactMap { $0.windowController as? DocumentWindowController }.first
    }

    // MARK: NSTableViewDataSource

    public func numberOfRows(in tableView: NSTableView) -> Int {
        projects.count
    }

    // MARK: NSTableViewDelegate

    public func tableView(_ tableView: NSTableView, viewFor tableColumn: NSTableColumn?, row: Int) -> NSView? {
        guard row >= 0, row < projects.count else { return nil }
        let project = projects[row]
        let cell = ProjectRowView()
        cell.configure(name: project.name, detail: describe(project))
        cell.toolTip = AppEnvironment.shared.help(
            "\(project.name) — \(describe(project)). Double-click to open it.",
            term: "BPM"
        )
        cell.setAccessibilityLabel("\(project.name), \(describe(project))")
        cell.setAccessibilityHelp("Press Return to open this song.")
        return cell
    }

    public func tableViewSelectionDidChange(_ notification: Notification) {
        updateOpenChoiceDetail()
    }
}

// MARK: - Private views

/// A view whose background and border are Theme colours, re-resolved whenever
/// the system appearance changes. Layer colours are static `CGColor`s, so a
/// dynamic `NSColor` has to be re-read rather than assigned once.
private final class ThemedView: NSView {
    private let backgroundColor: NSColor
    private let borderColor: NSColor?
    private let cornerRadius: CGFloat

    /// Called when the user presses Escape anywhere inside this view.
    var onCancel: (() -> Void)?

    init(backgroundColor: NSColor, borderColor: NSColor? = nil, cornerRadius: CGFloat = 0) {
        self.backgroundColor = backgroundColor
        self.borderColor = borderColor
        self.cornerRadius = cornerRadius
        super.init(frame: .zero)
        wantsLayer = true
        translatesAutoresizingMaskIntoConstraints = false
        applyColors()
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    override func viewDidChangeEffectiveAppearance() {
        super.viewDidChangeEffectiveAppearance()
        applyColors()
    }

    override func cancelOperation(_ sender: Any?) {
        onCancel?()
    }

    private func applyColors() {
        effectiveAppearance.performAsCurrentDrawingAppearance {
            layer?.cornerRadius = cornerRadius
            layer?.backgroundColor = backgroundColor.cgColor
            if let borderColor {
                layer?.borderWidth = 1
                layer?.borderColor = borderColor.cgColor
            } else {
                layer?.borderWidth = 0
            }
        }
    }
}

/// Makes a scroll view lay its content out from the top down, which is what
/// every reader expects of a column of prose.
private final class FlippedClipView: NSClipView {
    override var isFlipped: Bool { true }
}

/// One row of the song list: the name, and what it is in one line.
private final class ProjectRowView: NSTableCellView {
    private let nameLabel = makeLabel("", font: Theme.Font.emphasis(13), color: Theme.text)
    private let detailLabel = makeLabel("", font: Theme.Font.body(12), color: Theme.muted)

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        let stack = NSStackView(views: [nameLabel, detailLabel])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 1
        stack.translatesAutoresizingMaskIntoConstraints = false
        addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 8),
            stack.trailingAnchor.constraint(lessThanOrEqualTo: trailingAnchor, constant: -8),
            stack.centerYAnchor.constraint(equalTo: centerYAnchor)
        ])
        textField = nameLabel
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    func configure(name: String, detail: String) {
        nameLabel.stringValue = name
        detailLabel.stringValue = detail
    }

    /// Keeps both lines readable when the row is the selected, focused one and
    /// AppKit paints it with the accent colour behind.
    override var backgroundStyle: NSView.BackgroundStyle {
        didSet {
            let emphasized = backgroundStyle == .emphasized
            nameLabel.textColor = emphasized ? .alternateSelectedControlTextColor : Theme.text
            detailLabel.textColor = emphasized
                ? NSColor.alternateSelectedControlTextColor.withAlphaComponent(0.85)
                : Theme.muted
        }
    }
}

// MARK: - Helpers

/// A label that wraps at a known width. The window is a fixed size, so the
/// width is an exact constant rather than something recomputed on resize —
/// which also keeps the enclosing stack views unambiguous.
private func wrappingLabel(
    _ text: String,
    width: CGFloat,
    font: NSFont,
    color: NSColor
) -> NSTextField {
    let label = makeLabel(text, font: font, color: color)
    label.lineBreakMode = .byWordWrapping
    label.maximumNumberOfLines = 0
    label.preferredMaxLayoutWidth = width
    label.setContentCompressionResistancePriority(.required, for: .vertical)
    label.widthAnchor.constraint(equalToConstant: width).isActive = true
    return label
}
