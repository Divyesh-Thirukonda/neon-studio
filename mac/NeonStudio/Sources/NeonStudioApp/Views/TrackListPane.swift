import AppKit
import AVFoundation
import UniformTypeIdentifiers
import NeonStudioKit

/// The left sidebar: the list of tracks, plus the step sequencer for whichever
/// track is selected.
///
/// This replaces two hand-drawn panels. The old "Browser" drew rows in
/// `draw(_:)` and hit-tested them in `mouseDown` with a *second*, mirrored set
/// of rect maths, so clicking a row frequently opened a different project. The
/// old "Channel Rack" drew a 16-step grid for every track, including audio stems
/// where a step means nothing at all.
///
/// Everything here is a real AppKit control: an `NSTableView` for the rows, real
/// buttons for mute / solo / add / import / delete, and real toggles for the
/// steps. That buys hover, pressed, selected, disabled, focus rings, keyboard
/// operability and VoiceOver for free, all of which the previous build lacked.
final class TrackListPane: BaseDocumentPane, NSTableViewDataSource, NSTableViewDelegate {

    // MARK: Row model
    //
    // A value type snapshot of what a row displays. `refresh()` compares the new
    // models with the old ones so a mute toggle re-configures the visible cells
    // instead of reloading the table out from under a rename in progress.

    private struct RowModel: Equatable {
        let id: String
        let name: String
        let secondary: String
        let colorHex: String?
        let isMuted: Bool
        let isSoloed: Bool
        let isAudible: Bool
    }

    // MARK: Views

    private let headerLabel = makeLabel("TRACKS", font: Theme.Font.captionBold(11), color: Theme.muted)
    private let countLabel = makeLabel("", font: Theme.Font.caption(11), color: Theme.dim)
    private let tableView = TrackTableView()
    private let scrollView = NSScrollView()
    private let dropZone = DropZoneView()
    private var emptyState: EmptyStateView!

    private var addButton: NSButton!
    private var importButton: NSButton!
    private var deleteButton: NSButton!

    private var sequencerDisclosure: NSButton!
    /// A stack, not a plain view, so hiding the grid or the explanation
    /// genuinely collapses the space instead of leaving a hole.
    private let sequencerBody = NSStackView()
    private let sequencerCaption = makeLabel("", font: Theme.Font.caption(11), color: Theme.muted)
    private let unsupportedLabel = makeLabel("", font: Theme.Font.caption(11), color: Theme.muted)
    private let stepsGrid = NSStackView()
    private var stepButtons: [NSButton] = []

    // MARK: State

    private var rows: [RowModel] = []
    /// True while `refresh()` is writing the table's selection, so the delegate
    /// callback doesn't bounce the same selection back into the host.
    private var isSyncingSelection = false
    private var isSequencerExpanded = true

    private static let palette = ["#60c8f8", "#9ef0c0", "#f8d46a", "#f59fcb", "#c4a5ff", "#ffa06a"]

    // MARK: Lifecycle

    init() {
        super.init(nibName: nil, bundle: nil)
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    override func viewDidLoad() {
        super.viewDidLoad()
        buildHeader()
        buildTable()
        buildEmptyState()
        buildFooter()
        buildSequencer()
        refresh()
    }

    override func viewDidLayout() {
        super.viewDidLayout()
        // Wrapping labels need a width to lay out against, and the sidebar is
        // resizable, so it can only be known here.
        let available = max(120, view.bounds.width - Theme.Metric.panelPadding * 2)
        unsupportedLabel.preferredMaxLayoutWidth = available
        sequencerCaption.preferredMaxLayoutWidth = available
    }

    // MARK: Construction

    private func buildHeader() {
        let glossary = Controls.glossary("Track", Glossary.long("Track"))
        glossary.controlSize = .small

        let container = NSView()
        container.translatesAutoresizingMaskIntoConstraints = false
        container.addSubview(headerLabel)
        container.addSubview(countLabel)
        container.addSubview(glossary)
        view.addSubview(container)

        headerLabel.setAccessibilityLabel("Tracks")
        headerLabel.setContentCompressionResistancePriority(.required, for: .horizontal)
        countLabel.setAccessibilityLabel("Number of tracks")

        NSLayoutConstraint.activate([
            container.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: Theme.Metric.panelPadding),
            container.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -8),
            container.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor, constant: 10),

            headerLabel.leadingAnchor.constraint(equalTo: container.leadingAnchor),
            headerLabel.centerYAnchor.constraint(equalTo: glossary.centerYAnchor),

            countLabel.leadingAnchor.constraint(equalTo: headerLabel.trailingAnchor, constant: 6),
            countLabel.centerYAnchor.constraint(equalTo: headerLabel.centerYAnchor),
            countLabel.trailingAnchor.constraint(lessThanOrEqualTo: glossary.leadingAnchor, constant: -6),

            glossary.trailingAnchor.constraint(equalTo: container.trailingAnchor),
            glossary.topAnchor.constraint(equalTo: container.topAnchor),
            glossary.bottomAnchor.constraint(equalTo: container.bottomAnchor)
        ])
        headerRow = container
    }

    private var headerRow: NSView!

    private func buildTable() {
        let column = NSTableColumn(identifier: NSUserInterfaceItemIdentifier("track"))
        column.title = "Track"
        column.resizingMask = .autoresizingMask
        column.minWidth = 120

        tableView.addTableColumn(column)
        tableView.headerView = nil
        tableView.rowHeight = 46
        tableView.rowSizeStyle = .custom
        tableView.style = .inset
        tableView.usesAlternatingRowBackgroundColors = false
        tableView.backgroundColor = .clear
        tableView.selectionHighlightStyle = .regular
        tableView.allowsEmptySelection = true
        tableView.allowsMultipleSelection = false
        tableView.allowsColumnReordering = false
        tableView.allowsColumnResizing = false
        tableView.intercellSpacing = NSSize(width: 0, height: 2)
        tableView.columnAutoresizingStyle = .uniformColumnAutoresizingStyle
        tableView.dataSource = self
        tableView.delegate = self
        tableView.target = self
        tableView.doubleAction = #selector(handleDoubleClick)
        tableView.toolTip = AppEnvironment.shared.help(
            "Every sound in the song, one per row. Click a row to work on it, double-click its name to rename it, and drag rows to reorder them.",
            term: "Track"
        )
        tableView.setAccessibilityLabel("Tracks")
        tableView.setAccessibilityHelp("Each row is one instrument or sound. Press Return to rename the selected track.")

        // Reordering and audio import both arrive as drags on this table.
        tableView.registerForDraggedTypes([trackRowPasteboardType, .fileURL])
        tableView.setDraggingSourceOperationMask(.move, forLocal: true)
        tableView.setDraggingSourceOperationMask([], forLocal: false)

        tableView.menuProvider = { [weak self] row in self?.makeContextMenu(for: row) }
        tableView.onDeleteKey = { [weak self] in self?.deleteSelectedTrack() }
        tableView.onRenameKey = { [weak self] row in self?.beginRename(row: row) }

        scrollView.documentView = tableView
        scrollView.hasVerticalScroller = true
        scrollView.autohidesScrollers = true
        scrollView.drawsBackground = false
        scrollView.borderType = .noBorder
        scrollView.translatesAutoresizingMaskIntoConstraints = false

        dropZone.translatesAutoresizingMaskIntoConstraints = false
        dropZone.onDropAudio = { [weak self] urls in self?.importAudio(urls: urls) }
        dropZone.addSubview(scrollView)
        view.addSubview(dropZone)

        NSLayoutConstraint.activate([
            scrollView.leadingAnchor.constraint(equalTo: dropZone.leadingAnchor),
            scrollView.trailingAnchor.constraint(equalTo: dropZone.trailingAnchor),
            scrollView.topAnchor.constraint(equalTo: dropZone.topAnchor),
            scrollView.bottomAnchor.constraint(equalTo: dropZone.bottomAnchor),

            dropZone.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            dropZone.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            dropZone.topAnchor.constraint(equalTo: headerRow.bottomAnchor, constant: 6)
        ])
        let minimumHeight = dropZone.heightAnchor.constraint(greaterThanOrEqualToConstant: 120)
        minimumHeight.priority = .defaultHigh
        minimumHeight.isActive = true
    }

    private func buildEmptyState() {
        let empty = EmptyStateView(
            symbol: "music.note.list",
            title: "No tracks yet",
            body: "A track holds one sound — the drums, the bass, a vocal. Add an empty one, or drag a sound file straight onto this list.",
            actionTitle: "Add your first track",
            action: { [weak self] in self?.addTrack() }
        )
        empty.isHidden = true
        dropZone.addSubview(empty)
        NSLayoutConstraint.activate([
            empty.leadingAnchor.constraint(equalTo: dropZone.leadingAnchor),
            empty.trailingAnchor.constraint(equalTo: dropZone.trailingAnchor),
            empty.topAnchor.constraint(equalTo: dropZone.topAnchor),
            empty.bottomAnchor.constraint(equalTo: dropZone.bottomAnchor)
        ])
        emptyState = empty
    }

    private func buildFooter() {
        addButton = Controls.button(
            title: "Add Track",
            symbol: "plus",
            help: AppEnvironment.shared.help(
                "Adds an empty track to the bottom of the list, ready for a sound or for notes.",
                term: "Track"
            ),
            action: { [weak self] in self?.addTrack() }
        )
        importButton = Controls.button(
            title: "Import Sound…",
            symbol: "square.and.arrow.down",
            help: "Choose a sound file on your Mac. Each file becomes its own track, sized to the length of the recording.",
            action: { [weak self] in self?.presentImportPanel() }
        )
        deleteButton = Controls.button(
            title: "Delete Track",
            symbol: "trash",
            help: "Removes the selected track and everything on it. The sound file on your Mac is not deleted, and ⌘Z puts the track back.",
            style: .destructive,
            action: { [weak self] in self?.deleteSelectedTrack() }
        )

        let topRow = NSStackView(views: [addButton, importButton])
        topRow.orientation = .horizontal
        topRow.distribution = .fillEqually
        topRow.spacing = 6
        topRow.translatesAutoresizingMaskIntoConstraints = false

        let footer = NSStackView(views: [topRow, deleteButton])
        footer.orientation = .vertical
        footer.alignment = .leading
        footer.spacing = 6
        footer.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(footer)

        NSLayoutConstraint.activate([
            footer.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: Theme.Metric.panelPadding),
            footer.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -Theme.Metric.panelPadding),
            footer.topAnchor.constraint(equalTo: dropZone.bottomAnchor, constant: 8),
            topRow.widthAnchor.constraint(equalTo: footer.widthAnchor)
        ])
        footerStack = footer
    }

    private var footerStack: NSStackView!

    private func buildSequencer() {
        let separator = Controls.separator(vertical: false)
        view.addSubview(separator)

        sequencerDisclosure = Controls.toggle(
            title: "Step sequencer",
            symbol: "chevron.down",
            help: AppEnvironment.shared.help(
                "Shows or hides the 16-step pattern grid for the selected track.",
                term: "Step sequencer"
            ),
            isOn: isSequencerExpanded,
            style: .quiet,
            action: { [weak self] isOn in self?.setSequencerExpanded(isOn) }
        )
        sequencerDisclosure.setAccessibilityLabel("Step sequencer section")

        let glossary = Controls.glossary("Step sequencer", Glossary.long("Step sequencer"))
        glossary.controlSize = .small

        let header = NSStackView(views: [sequencerDisclosure, glossary])
        header.orientation = .horizontal
        header.alignment = .centerY
        header.spacing = 4
        header.translatesAutoresizingMaskIntoConstraints = false

        sequencerCaption.lineBreakMode = .byWordWrapping
        sequencerCaption.maximumNumberOfLines = 0
        sequencerCaption.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)

        unsupportedLabel.lineBreakMode = .byWordWrapping
        unsupportedLabel.maximumNumberOfLines = 0
        unsupportedLabel.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        unsupportedLabel.stringValue = "This track plays a recorded sound, so it's arranged as clips in the timeline rather than steps."

        buildStepsGrid()

        sequencerBody.orientation = .vertical
        sequencerBody.alignment = .leading
        sequencerBody.spacing = 6
        sequencerBody.translatesAutoresizingMaskIntoConstraints = false
        sequencerBody.addArrangedSubview(sequencerCaption)
        sequencerBody.addArrangedSubview(stepsGrid)
        sequencerBody.addArrangedSubview(unsupportedLabel)

        let section = NSStackView(views: [header, sequencerBody])
        section.orientation = .vertical
        section.alignment = .leading
        section.spacing = 6
        section.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(section)

        let inset = Theme.Metric.panelPadding
        NSLayoutConstraint.activate([
            separator.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            separator.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            separator.topAnchor.constraint(equalTo: footerStack.bottomAnchor, constant: 10),

            section.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: inset),
            section.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -inset),
            section.topAnchor.constraint(equalTo: separator.bottomAnchor, constant: 8),
            section.bottomAnchor.constraint(equalTo: view.bottomAnchor, constant: -inset),

            sequencerBody.widthAnchor.constraint(equalTo: section.widthAnchor),
            sequencerCaption.widthAnchor.constraint(equalTo: sequencerBody.widthAnchor),
            stepsGrid.widthAnchor.constraint(equalTo: sequencerBody.widthAnchor),
            unsupportedLabel.widthAnchor.constraint(equalTo: sequencerBody.widthAnchor)
        ])
    }

    /// Four rows of four, one row per beat. Grouping them this way is what makes
    /// a pattern readable — "the clap is on beats two and four" is visible at a
    /// glance instead of counted out of sixteen identical squares.
    private func buildStepsGrid() {
        stepsGrid.orientation = .vertical
        stepsGrid.alignment = .leading
        stepsGrid.spacing = 4
        stepsGrid.translatesAutoresizingMaskIntoConstraints = false

        for beat in 0..<4 {
            let beatLabel = makeLabel("Beat \(beat + 1)", font: Theme.Font.caption(11), color: Theme.dim)
            beatLabel.alignment = .right
            beatLabel.widthAnchor.constraint(equalToConstant: 44).isActive = true
            beatLabel.setContentCompressionResistancePriority(.required, for: .horizontal)

            let group = NSStackView()
            group.orientation = .horizontal
            group.distribution = .fillEqually
            group.spacing = 3
            group.translatesAutoresizingMaskIntoConstraints = false

            for slot in 0..<4 {
                let index = beat * 4 + slot
                let button = Controls.toggle(
                    title: "\(index + 1)",
                    help: AppEnvironment.shared.help(
                        "Step \(index + 1) of 16 — the \(ordinal(slot + 1)) sixteenth of beat \(beat + 1). Switch it on to play the sound at this moment.",
                        term: "Step sequencer"
                    ),
                    style: .quiet,
                    action: { [weak self] _ in self?.toggleStep(index) }
                )
                button.setAccessibilityLabel("Step \(index + 1), beat \(beat + 1)")
                button.setAccessibilityHelp("On plays the sound at this point in the bar; off leaves a gap.")
                button.font = Theme.Font.caption(11)
                button.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
                button.heightAnchor.constraint(equalToConstant: Theme.Metric.minimumHitTarget).isActive = true
                group.addArrangedSubview(button)
                stepButtons.append(button)
            }

            // A container with explicit constraints rather than a nested stack:
            // the step buttons must stretch to the full sidebar width, and a
            // stack would leave them at their intrinsic size with the slack
            // distributed somewhere unpredictable.
            let row = NSView()
            row.translatesAutoresizingMaskIntoConstraints = false
            row.addSubview(beatLabel)
            row.addSubview(group)
            stepsGrid.addArrangedSubview(row)

            NSLayoutConstraint.activate([
                row.widthAnchor.constraint(equalTo: stepsGrid.widthAnchor),
                beatLabel.leadingAnchor.constraint(equalTo: row.leadingAnchor),
                beatLabel.centerYAnchor.constraint(equalTo: row.centerYAnchor),
                group.leadingAnchor.constraint(equalTo: beatLabel.trailingAnchor, constant: 6),
                group.trailingAnchor.constraint(equalTo: row.trailingAnchor),
                group.topAnchor.constraint(equalTo: row.topAnchor),
                group.bottomAnchor.constraint(equalTo: row.bottomAnchor)
            ])
        }
    }

    private func ordinal(_ value: Int) -> String {
        switch value {
        case 1: return "first"
        case 2: return "second"
        case 3: return "third"
        default: return "fourth"
        }
    }

    // MARK: Refresh

    override func refresh() {
        guard isViewLoaded else { return }
        let models = makeRowModels()
        let identityChanged = models.map(\.id) != rows.map(\.id)
        let previous = rows
        rows = models

        isSyncingSelection = true
        if identityChanged {
            tableView.reloadData()
        } else if models != previous {
            for (index, model) in models.enumerated() where model != previous[index] {
                if let cell = tableView.view(atColumn: 0, row: index, makeIfNecessary: false) as? TrackRowCellView {
                    configure(cell, with: model)
                }
            }
        }
        syncSelectionFromHost()
        isSyncingSelection = false

        countLabel.stringValue = models.isEmpty
            ? ""
            : (models.count == 1 ? "1 track" : "\(models.count) tracks")
        emptyState.isHidden = !models.isEmpty
        scrollView.isHidden = models.isEmpty
        deleteButton.isEnabled = !models.isEmpty
        updateSequencer()
    }

    private func makeRowModels() -> [RowModel] {
        guard let host else { return [] }
        let project = host.project
        return project.snapshot.tracks.map { track in
            let control = project.control(for: track.id)
            return RowModel(
                id: track.id,
                name: track.name,
                secondary: describe(track),
                colorHex: track.color,
                isMuted: control.mute,
                isSoloed: control.solo,
                isAudible: project.isAudible(track.id)
            )
        }
    }

    private func describe(_ track: Track) -> String {
        var parts: [String] = []
        let instrument = track.instrument?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if !instrument.isEmpty {
            parts.append(instrument)
        } else if let kind = track.kind, !kind.isEmpty {
            parts.append(kind.capitalized)
        } else {
            parts.append("Track")
        }
        let clips = track.clips?.count ?? 0
        switch clips {
        case 0: parts.append("no clips yet")
        case 1: parts.append("1 clip")
        default: parts.append("\(clips) clips")
        }
        return parts.joined(separator: " · ")
    }

    private func syncSelectionFromHost() {
        guard let host else { return }
        guard let index = rows.firstIndex(where: { $0.id == host.selectedTrackId }) else {
            tableView.deselectAll(nil)
            return
        }
        if tableView.selectedRow != index {
            tableView.selectRowIndexes(IndexSet(integer: index), byExtendingSelection: false)
            tableView.scrollRowToVisible(index)
        }
    }

    // MARK: Table data source

    func numberOfRows(in tableView: NSTableView) -> Int { rows.count }

    func tableView(_ tableView: NSTableView, viewFor tableColumn: NSTableColumn?, row: Int) -> NSView? {
        guard row >= 0, row < rows.count else { return nil }
        let identifier = NSUserInterfaceItemIdentifier("TrackRowCellView")
        let cell = (tableView.makeView(withIdentifier: identifier, owner: self) as? TrackRowCellView)
            ?? {
                let created = TrackRowCellView()
                created.identifier = identifier
                return created
            }()
        configure(cell, with: rows[row])
        return cell
    }

    private func configure(_ cell: TrackRowCellView, with model: RowModel) {
        cell.configure(
            name: model.name,
            secondary: model.secondary,
            color: neonColor(from: model.colorHex, fallback: Theme.defaultTrackColor),
            isMuted: model.isMuted,
            isSoloed: model.isSoloed,
            isAudible: model.isAudible
        )
        let trackId = model.id
        cell.onRename = { [weak self] newName in self?.rename(trackId: trackId, to: newName) }
        cell.onMute = { [weak self] isOn in self?.setMute(isOn, trackId: trackId) }
        cell.onSolo = { [weak self] isOn in self?.setSolo(isOn, trackId: trackId) }
    }

    func tableViewSelectionDidChange(_ notification: Notification) {
        guard !isSyncingSelection else { return }
        let row = tableView.selectedRow
        guard row >= 0, row < rows.count else { return }
        host?.selectTrack(rows[row].id)
        updateSequencer()
    }

    // MARK: Drag and drop

    func tableView(_ tableView: NSTableView, pasteboardWriterForRow row: Int) -> NSPasteboardWriting? {
        guard row >= 0, row < rows.count else { return nil }
        let item = NSPasteboardItem()
        item.setString(rows[row].id, forType: trackRowPasteboardType)
        return item
    }

    func tableView(
        _ tableView: NSTableView,
        validateDrop info: NSDraggingInfo,
        proposedRow row: Int,
        proposedDropOperation dropOperation: NSTableView.DropOperation
    ) -> NSDragOperation {
        // Both kinds of drop insert between rows, never onto one, so the
        // insertion line always shows what is about to happen.
        if dropOperation == .on {
            tableView.setDropRow(row, dropOperation: .above)
        }
        if info.draggingPasteboard.string(forType: trackRowPasteboardType) != nil {
            return .move
        }
        return audioURLs(from: info.draggingPasteboard).isEmpty ? [] : .copy
    }

    func tableView(
        _ tableView: NSTableView,
        acceptDrop info: NSDraggingInfo,
        row: Int,
        dropOperation: NSTableView.DropOperation
    ) -> Bool {
        if let draggedId = info.draggingPasteboard.string(forType: trackRowPasteboardType) {
            return move(trackId: draggedId, toRow: row)
        }
        let urls = audioURLs(from: info.draggingPasteboard)
        guard !urls.isEmpty else { return false }
        importAudio(urls: urls, insertingAtRow: row)
        return true
    }

    private func move(trackId: String, toRow row: Int) -> Bool {
        guard let host, let from = rows.firstIndex(where: { $0.id == trackId }) else { return false }
        var destination = row
        if destination > from { destination -= 1 }
        guard destination != from else { return false }
        let name = rows[from].name

        host.edit("Reorder Tracks") { project in
            guard let index = project.snapshot.tracks.firstIndex(where: { $0.id == trackId }) else { return }
            let target = max(0, min(project.snapshot.tracks.count - 1, destination))
            let track = project.snapshot.tracks.remove(at: index)
            project.snapshot.tracks.insert(track, at: target)
        }
        StatusCenter.shared.success("Moved “\(name)” to position \(destination + 1). ⌘Z undoes it.")
        return true
    }

    // MARK: Actions

    private func addTrack() {
        guard let host else { return }
        let index = host.project.snapshot.tracks.count + 1
        let id = makeId("track")
        let color = TrackListPane.palette[index % TrackListPane.palette.count]
        host.edit("Add Track") { project in
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
            project.snapshot.selectedClipId = ""
        }
        StatusCenter.shared.success(
            "Added Track \(index).",
            detail: "Import a sound into it, or write notes for it in the Notes tab. ⌘Z removes it again."
        )
    }

    private func presentImportPanel() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.audio]
        panel.allowsMultipleSelection = true
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        panel.message = "Choose one or more sounds. Each one becomes its own track."
        panel.prompt = "Import"

        let handle: (NSApplication.ModalResponse) -> Void = { [weak self] response in
            guard response == .OK, let self else { return }
            let urls = panel.urls
            guard !urls.isEmpty else { return }
            self.importAudio(urls: urls)
        }

        if let window = view.window {
            panel.beginSheetModal(for: window, completionHandler: handle)
        } else {
            handle(panel.runModal())
        }
    }

    /// Builds a track for each dropped or chosen file. The pane can't reach the
    /// window controller, so it does the work itself — sizing each clip from the
    /// file's real duration rather than guessing a length.
    private func importAudio(urls: [URL], insertingAtRow row: Int? = nil) {
        guard let host, !urls.isEmpty else { return }
        let secondsPerBar = host.project.secondsPerBar
        let existingCount = host.project.snapshot.tracks.count

        var newTracks: [Track] = []
        for (offset, url) in urls.enumerated() {
            let name = String(url.deletingPathExtension().lastPathComponent.prefix(40))
            let duration = (try? AVAudioFile(forReading: url)).map { file in
                Double(file.length) / file.processingFormat.sampleRate
            } ?? 8
            // Quarter-bar resolution: long enough to be honest about the file,
            // tidy enough to line up with the grid.
            let bars = max(0.25, (duration / max(0.0001, secondsPerBar) * 4).rounded() / 4)
            let id = makeId("audio")
            let color = TrackListPane.palette[(existingCount + offset) % TrackListPane.palette.count]
            newTracks.append(Track(
                id: id,
                name: name.isEmpty ? "Imported Sound" : name,
                kind: "audio",
                file: url.path,
                color: color,
                gain: 0.86,
                pan: 0,
                steps: [],
                instrument: "Imported Audio",
                clips: [Clip(
                    id: "\(id)-clip",
                    name: name.isEmpty ? "Imported Sound" : name,
                    startBar: 0,
                    bars: bars,
                    lane: id,
                    color: color,
                    type: "audio"
                )],
                effects: [
                    Effect(id: "eq", name: "EQ", active: false, amount: 0.35),
                    Effect(id: "comp", name: "Compressor", active: false, amount: 0.35)
                ],
                sampleEdit: normalizeSampleEdit(nil)
            ))
        }

        let insertion = row
        let selectedId = newTracks.last?.id ?? ""
        host.edit("Import Audio") { project in
            let target = max(0, min(project.snapshot.tracks.count, insertion ?? project.snapshot.tracks.count))
            project.snapshot.tracks.insert(contentsOf: newTracks, at: target)
            project.snapshot.selectedTrackId = selectedId
            project.snapshot.selectedClipId = ""
        }

        let summary = urls.count == 1
            ? "Imported \(urls[0].lastPathComponent) as a new track."
            : "Imported \(urls.count) sounds as new tracks."
        StatusCenter.shared.success(
            summary,
            detail: "Each one is placed at bar 1, sized to the length of the recording. ⌘Z undoes it."
        )
    }

    private func deleteSelectedTrack() {
        guard let host else { return }
        guard let track = host.project.track(id: host.selectedTrackId) ?? host.project.snapshot.tracks.first else {
            StatusCenter.shared.info("Select a track in the list first, then delete it.")
            return
        }
        guard host.project.snapshot.tracks.count > 1 else {
            StatusCenter.shared.warning(
                "A song needs at least one track, so “\(track.name)” can't be deleted.",
                detail: "Add another track first, then delete this one."
            )
            return
        }

        if AppEnvironment.shared.confirmsDestructiveEdits {
            let alert = NSAlert()
            alert.alertStyle = .warning
            alert.messageText = "Delete the track “\(track.name)”?"
            alert.informativeText = "Its clips, notes and effect settings go with it. The sound file on your Mac is not deleted, and ⌘Z undoes this."
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
        host.edit("Delete Track") { project in
            project.snapshot.tracks.removeAll { $0.id == trackId }
            project.snapshot.controls?[trackId] = nil
            project.snapshot.notes = (project.snapshot.notes ?? []).filter { $0.trackId != trackId }
            project.snapshot.automationLanes = (project.snapshot.automationLanes ?? []).filter { $0.trackId != trackId }
            project.snapshot.selectedTrackId = project.snapshot.tracks.first?.id ?? ""
            project.snapshot.selectedClipId = ""
        }
        StatusCenter.shared.success("Deleted “\(track.name)”. ⌘Z puts it back.")
    }

    private func rename(trackId: String, to newName: String) {
        guard let host else { return }
        let trimmed = newName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let track = host.project.track(id: trackId) else { return }
        guard !trimmed.isEmpty else {
            StatusCenter.shared.warning("A track needs a name, so “\(track.name)” was left as it was.")
            refresh()
            return
        }
        guard trimmed != track.name else { return }
        let oldName = track.name
        host.edit("Rename Track") { project in
            guard let index = project.snapshot.tracks.firstIndex(where: { $0.id == trackId }) else { return }
            project.snapshot.tracks[index].name = String(trimmed.prefix(60))
        }
        StatusCenter.shared.success("Renamed “\(oldName)” to “\(trimmed)”. ⌘Z undoes it.")
    }

    private func setMute(_ isOn: Bool, trackId: String) {
        guard let host, let track = host.project.track(id: trackId) else { return }
        host.edit(isOn ? "Mute Track" : "Unmute Track") { project in
            updateControl(&project, trackId: trackId) { $0.mute = isOn }
        }
        StatusCenter.shared.info(
            isOn ? "Muted “\(track.name)” — it stays in the song but is silent." : "Unmuted “\(track.name)”.",
            detail: "⌘Z undoes it."
        )
    }

    private func setSolo(_ isOn: Bool, trackId: String) {
        guard let host, let track = host.project.track(id: trackId) else { return }
        host.edit(isOn ? "Solo Track" : "Unsolo Track") { project in
            updateControl(&project, trackId: trackId) { $0.solo = isOn }
        }
        StatusCenter.shared.info(
            isOn ? "Soloed “\(track.name)” — every other track is silent until you turn it off." : "Stopped soloing “\(track.name)”.",
            detail: "⌘Z undoes it."
        )
    }

    private func beginRename(row: Int) {
        guard row >= 0, row < rows.count else {
            StatusCenter.shared.info("Select a track first, then press Return to rename it.")
            return
        }
        tableView.scrollRowToVisible(row)
        guard let cell = tableView.view(atColumn: 0, row: row, makeIfNecessary: true) as? TrackRowCellView else { return }
        cell.beginEditingName()
    }

    @objc private func handleDoubleClick() {
        let row = tableView.clickedRow >= 0 ? tableView.clickedRow : tableView.selectedRow
        beginRename(row: row)
    }

    // MARK: Context menu

    private func makeContextMenu(for row: Int) -> NSMenu? {
        let menu = NSMenu()
        menu.autoenablesItems = false

        if row >= 0, row < rows.count {
            let model = rows[row]
            menu.addItem(ClosureMenuItem(title: "Rename “\(model.name)”…") { [weak self] in
                self?.beginRename(row: row)
            })
            menu.addItem(ClosureMenuItem(title: model.isMuted ? "Unmute" : "Mute (silence this track)") { [weak self] in
                self?.setMute(!model.isMuted, trackId: model.id)
            })
            menu.addItem(ClosureMenuItem(title: model.isSoloed ? "Stop soloing" : "Solo (hear only this track)") { [weak self] in
                self?.setSolo(!model.isSoloed, trackId: model.id)
            })
            menu.addItem(.separator())
            menu.addItem(ClosureMenuItem(title: "Show in Arrange") { [weak self] in
                self?.host?.selectTrack(model.id)
                self?.host?.requestFocus(on: .playlist)
            })
            menu.addItem(.separator())
            menu.addItem(ClosureMenuItem(title: "Delete Track") { [weak self] in
                self?.host?.selectTrack(model.id)
                self?.deleteSelectedTrack()
            })
            menu.addItem(.separator())
        }

        menu.addItem(ClosureMenuItem(title: "Add Track") { [weak self] in self?.addTrack() })
        menu.addItem(ClosureMenuItem(title: "Import Sound…") { [weak self] in self?.presentImportPanel() })
        return menu
    }

    // MARK: Step sequencer

    private func setSequencerExpanded(_ expanded: Bool) {
        isSequencerExpanded = expanded
        sequencerDisclosure.image = NSImage(
            systemSymbolName: expanded ? "chevron.down" : "chevron.right",
            accessibilityDescription: expanded ? "Expanded" : "Collapsed"
        )
        sequencerBody.isHidden = !expanded
        updateSequencer()
    }

    private func updateSequencer() {
        guard isViewLoaded else { return }
        sequencerDisclosure.state = isSequencerExpanded ? .on : .off
        sequencerDisclosure.image = NSImage(
            systemSymbolName: isSequencerExpanded ? "chevron.down" : "chevron.right",
            accessibilityDescription: isSequencerExpanded ? "Expanded" : "Collapsed"
        )
        sequencerBody.isHidden = !isSequencerExpanded
        guard isSequencerExpanded else { return }

        guard let track = host?.selectedTrack else {
            sequencerCaption.stringValue = "Add a track to build a pattern."
            stepsGrid.isHidden = true
            unsupportedLabel.isHidden = true
            return
        }

        guard track.supportsStepSequencing else {
            sequencerCaption.stringValue = "\(track.name) — no steps"
            stepsGrid.isHidden = true
            unsupportedLabel.isHidden = false
            return
        }

        stepsGrid.isHidden = false
        unsupportedLabel.isHidden = true
        sequencerCaption.stringValue = "\(track.name) — each button is one sixteenth of a bar."

        let active = Set((track.steps ?? []).map { (($0 % 16) + 16) % 16 })
        for (index, button) in stepButtons.enumerated() {
            let isOn = active.contains(index)
            button.state = isOn ? .on : .off
            button.contentTintColor = isOn ? Theme.accent : Theme.muted
        }
    }

    private func toggleStep(_ index: Int) {
        guard let host, let track = host.selectedTrack else { return }
        guard track.supportsStepSequencing else {
            updateSequencer()
            return
        }
        let trackId = track.id
        let willBeOn = !Set((track.steps ?? []).map { (($0 % 16) + 16) % 16 }).contains(index)

        host.edit("Toggle Step \(index + 1)") { project in
            guard let position = project.snapshot.tracks.firstIndex(where: { $0.id == trackId }) else { return }
            var steps = project.snapshot.tracks[position].steps ?? []
            if steps.contains(index) {
                steps.removeAll { $0 == index }
            } else {
                steps.append(index)
                steps.sort()
            }
            project.snapshot.tracks[position].steps = steps
        }
        StatusCenter.shared.info(
            "Step \(index + 1) is now \(willBeOn ? "on" : "off") for “\(track.name)”.",
            detail: "⌘Z undoes it."
        )
    }
}

// MARK: - Row cell

/// One track row. Real subviews, so the name is editable, the mute and solo
/// buttons have proper pressed states, and VoiceOver reads the whole row.
private final class TrackRowCellView: NSTableCellView {
    var onRename: ((String) -> Void)?
    var onMute: ((Bool) -> Void)?
    var onSolo: ((Bool) -> Void)?

    private let swatch = NSView()
    private let nameField = CommitTextField(string: "")
    private let secondaryLabel = makeLabel("", font: Theme.Font.caption(11), color: Theme.muted)
    private var muteButton: NSButton!
    private var soloButton: NSButton!
    private var isAudible = true

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        build()
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    private func build() {
        swatch.wantsLayer = true
        swatch.layer?.cornerRadius = 2
        swatch.translatesAutoresizingMaskIntoConstraints = false
        swatch.setAccessibilityElement(false)
        swatch.toolTip = "The colour this track uses in the timeline."

        nameField.isBordered = false
        nameField.isBezeled = false
        nameField.drawsBackground = false
        nameField.isEditable = false
        nameField.isSelectable = false
        nameField.font = Theme.Font.emphasis(13)
        nameField.textColor = Theme.text
        nameField.lineBreakMode = .byTruncatingTail
        nameField.cell?.usesSingleLineMode = true
        nameField.toolTip = "The name of this track. Double-click to rename it."
        nameField.setAccessibilityLabel("Track name")
        nameField.translatesAutoresizingMaskIntoConstraints = false
        nameField.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        nameField.commitHandler = { [weak self] value in
            guard let self else { return }
            self.endEditingName()
            self.onRename?(value)
        }
        textField = nameField

        secondaryLabel.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        secondaryLabel.setAccessibilityElement(false)

        muteButton = Controls.toggle(
            title: "M",
            help: AppEnvironment.shared.help("Mute — silence this track without deleting it.", term: "Mute"),
            style: .standard,
            action: { [weak self] isOn in self?.onMute?(isOn) }
        )
        soloButton = Controls.toggle(
            title: "S",
            help: AppEnvironment.shared.help("Solo — hear only this track.", term: "Solo"),
            style: .standard,
            action: { [weak self] isOn in self?.onSolo?(isOn) }
        )
        for button in [muteButton, soloButton] {
            guard let button else { continue }
            button.controlSize = .regular
            button.font = Theme.Font.captionBold(11)
            button.widthAnchor.constraint(equalToConstant: 30).isActive = true
            button.heightAnchor.constraint(equalToConstant: Theme.Metric.minimumHitTarget + 2).isActive = true
        }

        let textStack = NSStackView(views: [nameField, secondaryLabel])
        textStack.orientation = .vertical
        textStack.alignment = .leading
        textStack.spacing = 1
        textStack.translatesAutoresizingMaskIntoConstraints = false

        addSubview(swatch)
        addSubview(textStack)
        addSubview(muteButton)
        addSubview(soloButton)

        NSLayoutConstraint.activate([
            swatch.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 8),
            swatch.centerYAnchor.constraint(equalTo: centerYAnchor),
            swatch.widthAnchor.constraint(equalToConstant: 4),
            swatch.heightAnchor.constraint(equalToConstant: 30),

            textStack.leadingAnchor.constraint(equalTo: swatch.trailingAnchor, constant: 8),
            textStack.centerYAnchor.constraint(equalTo: centerYAnchor),
            textStack.trailingAnchor.constraint(equalTo: muteButton.leadingAnchor, constant: -6),
            // Both lines span the column, so a long name truncates instead of
            // pushing the mute and solo buttons off the row.
            nameField.widthAnchor.constraint(equalTo: textStack.widthAnchor),
            secondaryLabel.widthAnchor.constraint(equalTo: textStack.widthAnchor),

            muteButton.trailingAnchor.constraint(equalTo: soloButton.leadingAnchor, constant: -4),
            muteButton.centerYAnchor.constraint(equalTo: centerYAnchor),

            soloButton.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -8),
            soloButton.centerYAnchor.constraint(equalTo: centerYAnchor)
        ])
    }

    func configure(
        name: String,
        secondary: String,
        color: NSColor,
        isMuted: Bool,
        isSoloed: Bool,
        isAudible: Bool
    ) {
        self.isAudible = isAudible
        if nameField.currentEditor() == nil {
            nameField.stringValue = name
        }
        secondaryLabel.stringValue = secondary
        swatch.layer?.backgroundColor = color.cgColor
        swatch.alphaValue = isAudible ? 1 : 0.4

        muteButton.state = isMuted ? .on : .off
        muteButton.contentTintColor = isMuted ? Theme.warning : Theme.muted
        muteButton.setAccessibilityLabel("Mute \(name)")
        muteButton.setAccessibilityValue(isMuted ? "On" : "Off")

        soloButton.state = isSoloed ? .on : .off
        soloButton.contentTintColor = isSoloed ? Theme.accent : Theme.muted
        soloButton.setAccessibilityLabel("Solo \(name)")
        soloButton.setAccessibilityValue(isSoloed ? "On" : "Off")

        setAccessibilityElement(true)
        setAccessibilityRole(.group)
        setAccessibilityLabel("\(name), \(secondary)\(isAudible ? "" : ", silent")")
        setAccessibilityHelp("Double-click the name to rename. M mutes, S plays this track on its own.")
        toolTip = "\(name) — \(secondary)"
        applyTextColors()
    }

    func beginEditingName() {
        nameField.isEditable = true
        nameField.isSelectable = true
        nameField.isBezeled = true
        nameField.bezelStyle = .roundedBezel
        nameField.drawsBackground = true
        nameField.textColor = Theme.text
        window?.makeFirstResponder(nameField)
        nameField.currentEditor()?.selectAll(nil)
    }

    private func endEditingName() {
        nameField.isEditable = false
        nameField.isSelectable = false
        nameField.isBezeled = false
        nameField.drawsBackground = false
        applyTextColors()
    }

    override var backgroundStyle: NSView.BackgroundStyle {
        didSet { applyTextColors() }
    }

    /// Selected rows are drawn on the system accent colour, so the row's own
    /// palette would fail contrast there. Swap to the system's selected-text
    /// colours whenever AppKit says the background is emphasized.
    private func applyTextColors() {
        let emphasized = backgroundStyle == .emphasized
        if emphasized {
            nameField.textColor = .alternateSelectedControlTextColor
            secondaryLabel.textColor = NSColor.alternateSelectedControlTextColor.withAlphaComponent(0.85)
        } else {
            nameField.textColor = isAudible ? Theme.text : Theme.dim
            secondaryLabel.textColor = Theme.muted
        }
    }
}

// MARK: - Table subclass

/// Adds a right-click menu and Return / Delete keyboard handling. Everything
/// else — selection, hover, drag insertion lines, VoiceOver — is stock
/// `NSTableView` behaviour, which is exactly why this is a table and not a
/// hand-drawn list.
private final class TrackTableView: NSTableView {
    var menuProvider: ((Int) -> NSMenu?)?
    var onDeleteKey: (() -> Void)?
    var onRenameKey: ((Int) -> Void)?

    override func menu(for event: NSEvent) -> NSMenu? {
        let point = convert(event.locationInWindow, from: nil)
        let clicked = row(at: point)
        if clicked >= 0 {
            selectRowIndexes(IndexSet(integer: clicked), byExtendingSelection: false)
        }
        return menuProvider?(clicked)
    }

    override func keyDown(with event: NSEvent) {
        guard let scalar = event.charactersIgnoringModifiers?.unicodeScalars.first else {
            super.keyDown(with: event)
            return
        }
        switch Int(scalar.value) {
        case NSDeleteCharacter, NSBackspaceCharacter, NSDeleteFunctionKey:
            onDeleteKey?()
        case NSCarriageReturnCharacter, NSEnterCharacter:
            onRenameKey?(selectedRow)
        default:
            super.keyDown(with: event)
        }
    }
}

// MARK: - Drop zone

/// Wraps the table so a sound file can be dropped anywhere in the sidebar —
/// including onto the empty state, where there is no row to aim at.
private final class DropZoneView: NSView {
    var onDropAudio: (([URL]) -> Void)?

    private var isTargeted = false {
        didSet {
            guard isTargeted != oldValue else { return }
            needsDisplay = true
        }
    }

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        registerForDraggedTypes([.fileURL])
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    override func draggingEntered(_ sender: NSDraggingInfo) -> NSDragOperation {
        guard !audioURLs(from: sender.draggingPasteboard).isEmpty else { return [] }
        isTargeted = true
        return .copy
    }

    override func draggingExited(_ sender: NSDraggingInfo?) {
        isTargeted = false
    }

    override func draggingEnded(_ sender: NSDraggingInfo) {
        isTargeted = false
    }

    override func performDragOperation(_ sender: NSDraggingInfo) -> Bool {
        isTargeted = false
        let urls = audioURLs(from: sender.draggingPasteboard)
        guard !urls.isEmpty else { return false }
        onDropAudio?(urls)
        return true
    }

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        guard isTargeted else { return }
        let target = bounds.insetBy(dx: 6, dy: 6)
        roundedFill(target, radius: Theme.Metric.cornerRadius, color: Theme.accent.withAlphaComponent(0.12))
        roundedStroke(target, radius: Theme.Metric.cornerRadius, color: Theme.accent, width: 2)
        let caption = NSRect(x: target.minX + 12, y: target.midY - 9, width: target.width - 24, height: 18)
        drawText(
            "Drop to add as a new track",
            in: caption,
            color: Theme.accent,
            font: Theme.Font.captionBold(12),
            alignment: .center
        )
    }
}

// MARK: - Small helpers

private let trackRowPasteboardType = NSPasteboard.PasteboardType("studio.neon.tracklist.row")

/// A menu item that runs a closure, so the context menu can be built inline
/// instead of routing every command through a selector.
private final class ClosureMenuItem: NSMenuItem {
    private let handler: () -> Void

    init(title: String, handler: @escaping () -> Void) {
        self.handler = handler
        super.init(title: title, action: #selector(invoke), keyEquivalent: "")
        target = self
        isEnabled = true
    }

    required init(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    @objc private func invoke() { handler() }
}

/// Audio files on a pasteboard, filtered by content type rather than by file
/// extension, so a `.wav` that is really a text file is refused up front.
private func audioURLs(from pasteboard: NSPasteboard) -> [URL] {
    let options: [NSPasteboard.ReadingOptionKey: Any] = [
        .urlReadingFileURLsOnly: true,
        .urlReadingContentsConformToTypes: [UTType.audio.identifier]
    ]
    let objects = pasteboard.readObjects(forClasses: [NSURL.self], options: options) as? [URL]
    return objects ?? []
}

/// Reads a track's mixer control, applies a change, and writes it back —
/// creating the defaults first if this project has never had controls.
private func updateControl(_ project: inout LocalProject, trackId: String, _ body: (inout MixerControl) -> Void) {
    var controls = project.snapshot.controls ?? makeDefaultControls(for: project.snapshot.tracks)
    var control = controls[trackId] ?? MixerControl.neutral
    body(&control)
    controls[trackId] = control
    project.snapshot.controls = controls
}
