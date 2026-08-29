import AppKit
import UniformTypeIdentifiers

// MARK: - Shared private chrome

/// A plain container that paints a `Theme` colour and can be flipped.
///
/// Dynamic `NSColor`s resolve inside `draw(_:)`, so this follows Light/Dark and
/// the Increase Contrast setting without anybody pinning an `NSAppearance`.
private final class ReportsContainerView: NSView {
    var fillColor: NSColor?
    var usesFlippedCoordinates = false

    override var isFlipped: Bool { usesFlippedCoordinates }

    override func draw(_ dirtyRect: NSRect) {
        guard let fillColor else { return }
        fillColor.setFill()
        dirtyRect.fill()
    }
}

/// Human words for a severity. `logPrefix` is a symbol, which VoiceOver reads as
/// punctuation or skips entirely, so spoken output needs real words.
private func severityWord(_ severity: StatusCenter.Severity) -> String {
    switch severity {
    case .info: return "Note"
    case .success: return "Done"
    case .warning: return "Warning"
    case .error: return "Error"
    case .progress: return "Working"
    }
}

// MARK: - Activity window

/// Everything Neon Studio has done this session, in order, kept forever.
///
/// The status bar shows one message at a time and transient ones fade, so a
/// message the user glanced away from used to be gone for good. This window is
/// the backstop: nothing that was ever posted disappears from it, and it can be
/// copied or saved wholesale when somebody needs to report a problem.
public final class ActivityWindowController: NSWindowController,
                                             NSTableViewDataSource,
                                             NSTableViewDelegate {

    public static let shared = ActivityWindowController()

    // MARK: Identifiers

    private static let whenColumnID = NSUserInterfaceItemIdentifier("neon.activity.when")
    private static let whatColumnID = NSUserInterfaceItemIdentifier("neon.activity.what")
    private static let timeCellID = NSUserInterfaceItemIdentifier("neon.activity.timeCell")
    private static let messageCellID = NSUserInterfaceItemIdentifier("neon.activity.messageCell")
    private static let rowViewID = NSUserInterfaceItemIdentifier("neon.activity.row")

    // MARK: State

    private var entries: [StatusCenter.Entry] = []

    private let scrollView = NSScrollView()
    private let tableView = NSTableView()
    private let emptyState = EmptyStateView(
        symbol: "list.bullet.rectangle.portrait",
        title: "Nothing has happened yet.",
        body: "Every message Neon Studio shows you — saved, exported, rendered, or failed — is listed here as soon as it happens. Play or save the song to see the first one."
    )

    private var copyButton: NSButton?
    private var saveButton: NSButton?
    private var clearButton: NSButton?

    private let timeFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateStyle = .none
        formatter.timeStyle = .medium
        return formatter
    }()

    private let spokenTimeFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateStyle = .none
        formatter.timeStyle = .short
        return formatter
    }()

    // MARK: Init

    private init() {
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 640, height: 420),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.title = "Activity"
        window.minSize = NSSize(width: 460, height: 260)
        // Kept alive across closes: `shared` outlives the window, and releasing
        // it on close would leave a dangling controller.
        window.isReleasedWhenClosed = false
        window.setFrameAutosaveName("NeonStudioActivityWindow")
        super.init(window: window)

        entries = StatusCenter.shared.log
        buildContent()
        window.center()

        StatusCenter.shared.onLogAppended.append { [weak self] entry in
            self?.append(entry)
        }
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    // MARK: Presenting

    public func present() {
        syncFromStatusCenter()
        showWindow(nil)
        window?.makeKeyAndOrderFront(nil)
        NSApp.activate()
        scrollToBottom()
    }

    // MARK: Layout

    private func buildContent() {
        guard let window else { return }

        let root = ReportsContainerView()
        root.fillColor = Theme.app
        root.translatesAutoresizingMaskIntoConstraints = false

        configureTable()

        scrollView.documentView = tableView
        scrollView.hasVerticalScroller = true
        scrollView.hasHorizontalScroller = false
        scrollView.autohidesScrollers = true
        scrollView.borderType = .noBorder
        scrollView.drawsBackground = true
        scrollView.backgroundColor = Theme.panel
        scrollView.translatesAutoresizingMaskIntoConstraints = false

        let copy = Controls.button(
            title: "Copy All",
            symbol: "doc.on.doc",
            help: "Put every message in this list on the clipboard, so you can paste it into a note or a bug report.",
            action: { [weak self] in self?.copyAll() }
        )
        let save = Controls.button(
            title: "Save…",
            symbol: "square.and.arrow.down",
            help: "Save this list as a plain text file you can keep or send to somebody.",
            action: { [weak self] in self?.saveLog() }
        )
        let clear = Controls.button(
            title: "Clear",
            help: "Empty this list. The messages can't be brought back afterwards.",
            style: .destructive,
            action: { [weak self] in self?.clearLog() }
        )
        copyButton = copy
        saveButton = save
        clearButton = clear

        let spacer = NSView()
        spacer.translatesAutoresizingMaskIntoConstraints = false
        spacer.setContentHuggingPriority(.defaultLow, for: .horizontal)

        let footer = NSStackView(views: [clear, spacer, save, copy])
        footer.orientation = .horizontal
        footer.alignment = .centerY
        footer.spacing = 8
        footer.translatesAutoresizingMaskIntoConstraints = false

        let divider = Controls.separator(vertical: false)

        emptyState.isHidden = true

        root.addSubview(scrollView)
        root.addSubview(emptyState)
        root.addSubview(divider)
        root.addSubview(footer)

        NSLayoutConstraint.activate([
            scrollView.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            scrollView.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            scrollView.topAnchor.constraint(equalTo: root.topAnchor),
            scrollView.bottomAnchor.constraint(equalTo: divider.topAnchor),

            emptyState.leadingAnchor.constraint(equalTo: scrollView.leadingAnchor),
            emptyState.trailingAnchor.constraint(equalTo: scrollView.trailingAnchor),
            emptyState.topAnchor.constraint(equalTo: scrollView.topAnchor),
            emptyState.bottomAnchor.constraint(equalTo: scrollView.bottomAnchor),

            divider.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            divider.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            divider.bottomAnchor.constraint(equalTo: footer.topAnchor, constant: -10),

            footer.leadingAnchor.constraint(equalTo: root.leadingAnchor, constant: Theme.Metric.panelPadding),
            footer.trailingAnchor.constraint(equalTo: root.trailingAnchor, constant: -Theme.Metric.panelPadding),
            footer.bottomAnchor.constraint(equalTo: root.bottomAnchor, constant: -Theme.Metric.gutter)
        ])

        window.contentView = root
        updateEmptyState()
    }

    private func configureTable() {
        let whenColumn = NSTableColumn(identifier: ActivityWindowController.whenColumnID)
        whenColumn.title = "When"
        whenColumn.width = 96
        whenColumn.minWidth = 72
        whenColumn.maxWidth = 140

        let whatColumn = NSTableColumn(identifier: ActivityWindowController.whatColumnID)
        whatColumn.title = "What happened"
        whatColumn.width = 480
        whatColumn.minWidth = 220

        tableView.addTableColumn(whenColumn)
        tableView.addTableColumn(whatColumn)
        // A table built in code has no header until it is given one, and without
        // it the two columns are unlabelled and can't be resized by dragging.
        tableView.headerView = NSTableHeaderView()
        tableView.dataSource = self
        tableView.delegate = self
        tableView.style = .fullWidth
        tableView.rowSizeStyle = .custom
        tableView.gridStyleMask = []
        tableView.allowsMultipleSelection = false
        tableView.allowsColumnReordering = false
        tableView.columnAutoresizingStyle = .lastColumnOnlyAutoresizingStyle
        tableView.backgroundColor = Theme.panel
        tableView.usesAlternatingRowBackgroundColors = true
        tableView.setAccessibilityLabel("Activity log")
        tableView.setAccessibilityHelp("Every message Neon Studio has shown you this session, oldest first.")
    }

    // MARK: Data

    /// Re-reads the whole log. Used on open and after anything that could have
    /// moved entries out from under us — `StatusCenter` trims its oldest
    /// entries once the log passes its cap.
    private func syncFromStatusCenter() {
        entries = StatusCenter.shared.log
        tableView.reloadData()
        updateEmptyState()
    }

    private func append(_ entry: StatusCenter.Entry) {
        // Sampled *before* the insert: the list only follows along if the user
        // was already reading the newest message, so scrolling back through
        // history is never yanked away.
        let wasAtBottom = isScrolledToBottom
        let log = StatusCenter.shared.log
        if log.count == entries.count + 1 {
            entries.append(entry)
            tableView.insertRows(at: IndexSet(integer: entries.count - 1), withAnimation: [])
        } else {
            entries = log
            tableView.reloadData()
        }
        updateEmptyState()
        if wasAtBottom { scrollToBottom() }
    }

    private var isScrolledToBottom: Bool {
        guard let documentView = scrollView.documentView else { return true }
        let visible = scrollView.contentView.bounds
        let contentHeight = documentView.bounds.height
        if contentHeight <= visible.height + 1 { return true }
        return visible.maxY >= contentHeight - 4
    }

    private func scrollToBottom() {
        guard !entries.isEmpty else { return }
        tableView.scrollRowToVisible(entries.count - 1)
    }

    private func updateEmptyState() {
        let isEmpty = entries.isEmpty
        emptyState.isHidden = !isEmpty
        // Alternating bands behind an empty-state message just look like noise.
        tableView.usesAlternatingRowBackgroundColors = !isEmpty
        copyButton?.isEnabled = !isEmpty
        saveButton?.isEnabled = !isEmpty
        clearButton?.isEnabled = !isEmpty
    }

    /// What the row as a whole says: time, severity, message, detail.
    private func describe(_ entry: StatusCenter.Entry) -> String {
        "\(spokenTimeFormatter.string(from: entry.date)). \(spokenSummary(entry))"
    }

    /// The message column on its own. The time is deliberately left out — the
    /// time column already speaks it, and repeating it doubles the length of
    /// every row VoiceOver reads.
    private func spokenSummary(_ entry: StatusCenter.Entry) -> String {
        let detail = entry.detail.map { ". \($0)" } ?? ""
        return "\(severityWord(entry.severity)). \(entry.message)\(detail)"
    }

    // MARK: Footer actions

    private func copyAll() {
        let text = StatusCenter.shared.logText()
        guard !text.isEmpty else {
            StatusCenter.shared.warning("There's nothing to copy yet.", detail: "The activity list is empty.")
            return
        }
        let count = entries.count
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
        StatusCenter.shared.success(
            "Copied the activity list.",
            detail: count == 1 ? "1 message is on the clipboard." : "\(count) messages are on the clipboard."
        )
    }

    private func saveLog() {
        let text = StatusCenter.shared.logText()
        guard !text.isEmpty else {
            StatusCenter.shared.warning("There's nothing to save yet.", detail: "The activity list is empty.")
            return
        }
        guard let window else { return }
        let panel = NSSavePanel()
        panel.allowedContentTypes = [.plainText]
        panel.nameFieldStringValue = "Neon Studio Activity.txt"
        panel.canCreateDirectories = true
        panel.message = "Choose where to save a copy of everything Neon Studio has done this session."
        panel.beginSheetModal(for: window) { response in
            guard response == .OK, let url = panel.url else { return }
            do {
                try text.write(to: url, atomically: true, encoding: .utf8)
                StatusCenter.shared.success("Saved the activity list.", detail: url.lastPathComponent)
            } catch {
                StatusCenter.shared.failure("Couldn't save the activity list.", error: error, window: window)
            }
        }
    }

    private func clearLog() {
        guard !entries.isEmpty else { return }
        // There is no undo for this one, so it asks first unless the user has
        // turned confirmations off in Settings.
        if AppEnvironment.shared.confirmsDestructiveEdits {
            let alert = NSAlert()
            alert.alertStyle = .warning
            alert.messageText = "Clear the activity list?"
            alert.informativeText = "The \(entries.count) messages listed here will be removed. This can't be undone, and ⌘Z won't bring them back. Your song is not affected."
            alert.addButton(withTitle: "Clear")
            alert.addButton(withTitle: "Cancel")
            guard alert.runModal() == .alertFirstButtonReturn else { return }
        }
        StatusCenter.shared.clearLog()
        syncFromStatusCenter()
        StatusCenter.shared.info("Cleared the activity list.", detail: "New messages will appear here from now on.")
    }

    // MARK: NSTableViewDataSource

    public func numberOfRows(in tableView: NSTableView) -> Int { entries.count }

    // MARK: NSTableViewDelegate

    public func tableView(_ tableView: NSTableView, heightOfRow row: Int) -> CGFloat {
        guard row >= 0, row < entries.count else { return 28 }
        return entries[row].detail == nil ? 28 : 46
    }

    public func tableView(_ tableView: NSTableView, rowViewForRow row: Int) -> NSTableRowView? {
        guard row >= 0, row < entries.count else { return nil }
        let rowView: NSTableRowView
        if let reused = tableView.makeView(withIdentifier: ActivityWindowController.rowViewID, owner: self) as? NSTableRowView {
            rowView = reused
        } else {
            rowView = NSTableRowView()
            rowView.identifier = ActivityWindowController.rowViewID
        }
        rowView.setAccessibilityLabel(describe(entries[row]))
        return rowView
    }

    public func tableView(_ tableView: NSTableView, viewFor tableColumn: NSTableColumn?, row: Int) -> NSView? {
        guard row >= 0, row < entries.count, let tableColumn else { return nil }
        let entry = entries[row]

        if tableColumn.identifier == ActivityWindowController.whenColumnID {
            let cell = tableView.makeView(withIdentifier: ActivityWindowController.timeCellID, owner: self) as? ActivityTimeCellView
                ?? ActivityTimeCellView(identifier: ActivityWindowController.timeCellID)
            cell.configure(text: timeFormatter.string(from: entry.date),
                           accessibilityLabel: spokenTimeFormatter.string(from: entry.date))
            return cell
        }

        let cell = tableView.makeView(withIdentifier: ActivityWindowController.messageCellID, owner: self) as? ActivityMessageCellView
            ?? ActivityMessageCellView(identifier: ActivityWindowController.messageCellID)
        cell.configure(entry: entry, accessibilityLabel: spokenSummary(entry))
        return cell
    }
}

// MARK: - Activity cells

/// The timestamp column. Monospaced digits so the colons line up down the list.
private final class ActivityTimeCellView: NSTableCellView {
    private let label = makeLabel("", font: Theme.Font.mono(11), color: Theme.dim)

    init(identifier: NSUserInterfaceItemIdentifier) {
        super.init(frame: .zero)
        self.identifier = identifier
        addSubview(label)
        NSLayoutConstraint.activate([
            label.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 8),
            label.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -4),
            label.topAnchor.constraint(equalTo: topAnchor, constant: 6)
        ])
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    func configure(text: String, accessibilityLabel: String) {
        label.stringValue = text
        label.toolTip = text
        setAccessibilityLabel(accessibilityLabel)
    }
}

/// Severity icon, message, and the detail line underneath it.
private final class ActivityMessageCellView: NSTableCellView {
    private let iconView = NSImageView()
    private let messageLabel = makeLabel("", font: Theme.Font.body(12), color: Theme.text)
    private let detailLabel = makeLabel("", font: Theme.Font.body(11), color: Theme.muted)

    init(identifier: NSUserInterfaceItemIdentifier) {
        super.init(frame: .zero)
        self.identifier = identifier

        iconView.translatesAutoresizingMaskIntoConstraints = false
        iconView.symbolConfiguration = .init(pointSize: 11, weight: .semibold)
        iconView.imageScaling = .scaleProportionallyDown
        iconView.setAccessibilityHidden(true)

        messageLabel.setAccessibilityHidden(true)
        detailLabel.setAccessibilityHidden(true)

        let textStack = NSStackView(views: [messageLabel, detailLabel])
        textStack.orientation = .vertical
        textStack.alignment = .leading
        textStack.spacing = 2
        textStack.translatesAutoresizingMaskIntoConstraints = false

        addSubview(iconView)
        addSubview(textStack)

        NSLayoutConstraint.activate([
            iconView.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 4),
            iconView.topAnchor.constraint(equalTo: topAnchor, constant: 7),
            iconView.widthAnchor.constraint(equalToConstant: 14),
            iconView.heightAnchor.constraint(equalToConstant: 14),

            textStack.leadingAnchor.constraint(equalTo: iconView.trailingAnchor, constant: 7),
            textStack.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -8),
            textStack.topAnchor.constraint(equalTo: topAnchor, constant: 5)
        ])
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    func configure(entry: StatusCenter.Entry, accessibilityLabel: String) {
        iconView.image = NSImage(systemSymbolName: entry.severity.symbol, accessibilityDescription: nil)
        iconView.contentTintColor = entry.severity.color

        messageLabel.stringValue = entry.message
        // Errors and warnings are coloured, so a failure can never be mistaken
        // for a success at a glance.
        messageLabel.textColor = (entry.severity == .error || entry.severity == .warning)
            ? entry.severity.color
            : Theme.text

        if let detail = entry.detail, !detail.isEmpty {
            detailLabel.stringValue = detail
            detailLabel.isHidden = false
        } else {
            detailLabel.stringValue = ""
            detailLabel.isHidden = true
        }

        // Rows are one line each; the tooltip and Copy All carry the untruncated
        // text so nothing is only half-readable.
        let full = entry.detail.map { "\(entry.message)\n\($0)" } ?? entry.message
        toolTip = full
        messageLabel.toolTip = full
        detailLabel.toolTip = full
        setAccessibilityLabel(accessibilityLabel)
    }
}

// MARK: - Keyboard shortcuts window

/// The real list of what the keys do.
///
/// This replaces an `NSAlert` whose list was partly wrong — it advertised ⌘H as
/// "help", which is macOS's Hide Application; the app was hijacking a system
/// shortcut and then documenting the hijack. Everything listed here is a
/// shortcut the app actually implements.
public final class ShortcutsWindowController: NSWindowController {

    public static let shared = ShortcutsWindowController()

    // MARK: Content

    private struct Shortcut {
        let keys: String
        let what: String
        /// Optional glossary term, so the tooltip can explain the jargon when
        /// the user has explanations switched on.
        let term: String?

        init(_ keys: String, _ what: String, term: String? = nil) {
            self.keys = keys
            self.what = what
            self.term = term
        }
    }

    private struct Group {
        let title: String
        let items: [Shortcut]
    }

    private static let groups: [Group] = [
        Group(title: "Playing", items: [
            Shortcut("Space", "Play, or stop if it's already playing."),
            Shortcut("Return", "Go back to the start of the song."),
            Shortcut("⌘L", "Turn looping on or off.", term: "Loop"),
            Shortcut("⌥⌘L", "Set which bars the loop repeats.", term: "Loop"),
            Shortcut("—", "Recording plays a count-in first. Set how long in Transport ▸ Count-In. With Loop on, the loop range is the punch range and recording stops itself.")
        ]),
        Group(title: "Editing", items: [
            Shortcut("⌘Z", "Undo the last change."),
            Shortcut("⇧⌘Z", "Redo the change you just undid."),
            Shortcut("Delete", "Remove whatever is selected."),
            Shortcut("⌘X ⌘C ⌘V", "Cut, copy, and paste."),
            Shortcut("⌘A", "Select everything."),
            Shortcut("← → ↑ ↓", "Nudge the selection by one step of the grid.", term: "Snap"),
            Shortcut("⇧ + Arrow", "Nudge the selection further, a bar at a time.", term: "Bar"),
            Shortcut("⌥ drag", "Ignore the grid while you drag, for free placement.", term: "Snap")
        ]),
        Group(title: "Views", items: [
            Shortcut("⌘1 – ⌘6", "Arrange, Notes, Mix, Effects, Sample, Recipe."),
            Shortcut("⌘+ ⌘−", "Zoom in and out of the timeline."),
            Shortcut("⌃⌘S", "Show or hide the track list.", term: "Track"),
            Shortcut("⌥⌘I", "Show or hide the inspector on the right.")
        ]),
        Group(title: "Tools", items: [
            Shortcut("V", "Select — click and drag what's already there."),
            Shortcut("B", "Draw — add a clip or a note.", term: "Clip"),
            Shortcut("E", "Erase — remove whatever you click on.")
        ]),
        Group(title: "Files", items: [
            Shortcut("⌘N", "Start a new song."),
            Shortcut("⌘O", "Open a song you saved earlier."),
            Shortcut("⌘S", "Save this song."),
            Shortcut("⇧⌘S", "Save this song as a separate copy."),
            Shortcut("⇧⌘I", "Import a sound as a new track.", term: "Stem"),
            Shortcut("⇧⌘E", "Export the whole song as one audio file.", term: "Mixdown"),
            Shortcut("⇧⌥⌘S", "Duplicate this song into a separate copy."),
            Shortcut("⌃⌘D", "Check my mix and report what to fix.", term: "Sound check"),
            Shortcut("⌥⌘A", "Suggest ideas for what to do next.", term: "Recipe")
        ]),
        Group(title: "Help", items: [
            Shortcut("⌘?", "Show this window."),
            Shortcut("⌘,", "Open Settings.")
        ])
    ]

    /// Width of the key column. Every chip is right-aligned inside it, so the
    /// gap between the keys and their descriptions is identical on every row.
    private static let keyColumnWidth: CGFloat = 132

    // MARK: Init

    private init() {
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 560, height: 560),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.title = "Keyboard Shortcuts"
        window.minSize = NSSize(width: 460, height: 320)
        window.isReleasedWhenClosed = false
        window.setFrameAutosaveName("NeonStudioShortcutsWindow")
        super.init(window: window)

        buildContent()
        window.center()
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    // MARK: Presenting

    public func present() {
        showWindow(nil)
        window?.makeKeyAndOrderFront(nil)
        NSApp.activate()
    }

    // MARK: Layout

    private func buildContent() {
        guard let window else { return }

        let root = ReportsContainerView()
        root.fillColor = Theme.app
        root.translatesAutoresizingMaskIntoConstraints = false

        let note = makeLabel(
            "Anything you change can be undone with ⌘Z.",
            font: Theme.Font.body(13),
            color: Theme.muted
        )
        note.isSelectable = true
        note.lineBreakMode = .byWordWrapping
        note.maximumNumberOfLines = 2
        note.toolTip = "Every edit in Neon Studio is undoable, so it is safe to try things."
        note.setAccessibilityLabel("Anything you change can be undone with Command Z.")

        let divider = Controls.separator(vertical: false)

        let stack = NSStackView()
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 5
        stack.translatesAutoresizingMaskIntoConstraints = false

        var isFirstGroup = true
        var previous: NSView?
        for group in ShortcutsWindowController.groups {
            let header = makeLabel(
                group.title.uppercased(),
                font: Theme.Font.captionBold(12),
                color: Theme.muted
            )
            header.isSelectable = true
            header.setAccessibilityRole(.staticText)
            header.setAccessibilityLabel(group.title)
            stack.addArrangedSubview(header)
            if let previous, !isFirstGroup {
                stack.setCustomSpacing(20, after: previous)
            }
            stack.setCustomSpacing(9, after: header)
            previous = header
            isFirstGroup = false

            for item in group.items {
                let row = makeRow(item)
                stack.addArrangedSubview(row)
                row.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true
                previous = row
            }
        }

        let content = ReportsContainerView()
        content.usesFlippedCoordinates = true
        content.translatesAutoresizingMaskIntoConstraints = false
        content.addSubview(stack)

        let scrollView = NSScrollView()
        scrollView.hasVerticalScroller = true
        scrollView.hasHorizontalScroller = false
        scrollView.autohidesScrollers = true
        scrollView.borderType = .noBorder
        scrollView.drawsBackground = true
        scrollView.backgroundColor = Theme.panel
        scrollView.translatesAutoresizingMaskIntoConstraints = false
        scrollView.documentView = content

        root.addSubview(note)
        root.addSubview(divider)
        root.addSubview(scrollView)

        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 22),
            stack.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -22),
            stack.topAnchor.constraint(equalTo: content.topAnchor, constant: 18),
            content.bottomAnchor.constraint(equalTo: stack.bottomAnchor, constant: 24),

            content.leadingAnchor.constraint(equalTo: scrollView.contentView.leadingAnchor),
            content.topAnchor.constraint(equalTo: scrollView.contentView.topAnchor),
            content.widthAnchor.constraint(equalTo: scrollView.contentView.widthAnchor),

            note.leadingAnchor.constraint(equalTo: root.leadingAnchor, constant: Theme.Metric.panelPadding + 10),
            note.trailingAnchor.constraint(equalTo: root.trailingAnchor, constant: -Theme.Metric.panelPadding),
            note.topAnchor.constraint(equalTo: root.topAnchor, constant: 14),

            divider.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            divider.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            divider.topAnchor.constraint(equalTo: note.bottomAnchor, constant: 12),

            scrollView.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            scrollView.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            scrollView.topAnchor.constraint(equalTo: divider.bottomAnchor),
            scrollView.bottomAnchor.constraint(equalTo: root.bottomAnchor)
        ])

        window.contentView = root
    }

    private func makeRow(_ shortcut: Shortcut) -> NSView {
        let chip = ShortcutKeyChipView(key: shortcut.keys)

        let keyColumn = NSView()
        keyColumn.translatesAutoresizingMaskIntoConstraints = false
        keyColumn.addSubview(chip)
        // High, not required: an unusually wide key combination widens its own
        // row rather than breaking the layout.
        let width = keyColumn.widthAnchor.constraint(
            equalToConstant: ShortcutsWindowController.keyColumnWidth
        )
        width.priority = .defaultHigh
        NSLayoutConstraint.activate([
            width,
            chip.trailingAnchor.constraint(equalTo: keyColumn.trailingAnchor),
            chip.topAnchor.constraint(equalTo: keyColumn.topAnchor),
            chip.bottomAnchor.constraint(equalTo: keyColumn.bottomAnchor),
            chip.leadingAnchor.constraint(greaterThanOrEqualTo: keyColumn.leadingAnchor)
        ])

        let help = AppEnvironment.shared.help(shortcut.what, term: shortcut.term)

        let description = makeLabel(shortcut.what, font: Theme.Font.body(13), color: Theme.text)
        description.isSelectable = true
        description.toolTip = help
        description.setContentHuggingPriority(.defaultLow, for: .horizontal)
        description.setAccessibilityHidden(true)

        let row = NSStackView(views: [keyColumn, description])
        row.orientation = .horizontal
        row.alignment = .centerY
        row.spacing = 14
        row.translatesAutoresizingMaskIntoConstraints = false
        row.toolTip = help
        // One VoiceOver stop per row, reading the key and what it does together
        // rather than two disconnected fragments.
        row.setAccessibilityElement(true)
        row.setAccessibilityRole(.staticText)
        row.setAccessibilityLabel("\(shortcut.keys): \(shortcut.what)")
        row.setAccessibilityHelp(help)
        return row
    }
}

/// A key combination drawn as a small rounded chip, the way macOS itself shows
/// keys in Help.
private final class ShortcutKeyChipView: NSView {
    private let label: NSTextField

    init(key: String) {
        label = makeLabel(key, font: Theme.Font.mono(12, weight: .semibold), color: Theme.text)
        super.init(frame: .zero)
        translatesAutoresizingMaskIntoConstraints = false
        wantsLayer = true
        layer?.cornerRadius = Theme.Metric.smallCornerRadius
        layer?.borderWidth = 1

        label.alignment = .center
        label.isSelectable = true
        label.lineBreakMode = .byClipping
        label.setContentCompressionResistancePriority(.required, for: .horizontal)
        label.setContentHuggingPriority(.required, for: .horizontal)
        label.setAccessibilityHidden(true)

        addSubview(label)
        NSLayoutConstraint.activate([
            label.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 9),
            label.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -9),
            label.topAnchor.constraint(equalTo: topAnchor, constant: 4),
            label.bottomAnchor.constraint(equalTo: bottomAnchor, constant: -4)
        ])
        setAccessibilityHidden(true)
        refreshColors()
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    override func viewDidChangeEffectiveAppearance() {
        super.viewDidChangeEffectiveAppearance()
        refreshColors()
    }

    private func refreshColors() {
        effectiveAppearance.performAsCurrentDrawingAppearance {
            layer?.backgroundColor = Theme.panelRaised.cgColor
            layer?.borderColor = Theme.subtleStroke.cgColor
        }
    }
}
