import AppKit
import NeonStudioKit

/// The right-hand column: the properties of whatever is selected.
///
/// The previous inspector was a grid of thirteen identically-styled 10.5pt
/// buttons — New, Save, Import, Audio, Mix, Transcript, Check, Agent, Backup,
/// Vocal, Delete, Rename, Reveal — so a destructive action sat one pixel away
/// from a harmless one and none of them said what they did. Those are commands,
/// not properties, and they now live in the toolbar and the menus where macOS
/// users look for them. What is left here is what an inspector is for: the
/// settings of the song, the selected track, and the selected clip, each one
/// labelled in words with a plain-English explanation attached.
///
/// The section views are built once and only their *values* change on
/// `refresh()`, which runs after every document change. A text field is never
/// written to while the user is typing in it.
public final class InspectorPane: BaseDocumentPane {

    // MARK: - Layout constants
    //
    // One place for every measurement, so rows cannot drift apart.

    private enum Layout {
        static let labelWidth: CGFloat = 76
        static let fieldWidth: CGFloat = 104
        static let numberWidth: CGFloat = 56
        static let smallNumberWidth: CGFloat = 44
        static let rowSpacing: CGFloat = 8
        static let sectionSpacing: CGFloat = 12
        static let outerInset: CGFloat = 12
        static let emptyStateHeight: CGFloat = 176
    }

    /// The six track colours offered in the picker. Deliberately a short, named
    /// list: a full colour well produces unreadable clip labels, and "which
    /// colour did I use for the bass" is easier to answer from six names.
    private static let colorPresets: [(name: String, hex: String)] = [
        ("Blue", "#4FA8F5"),
        ("Purple", "#A97BFF"),
        ("Pink", "#FF6FB5"),
        ("Orange", "#FF9F45"),
        ("Green", "#4CD787"),
        ("Yellow", "#F5D96B")
    ]

    // MARK: - Chrome

    private let scrollView = NSScrollView()
    private let container = InspectorFlippedView()
    private let stack = NSStackView()

    // MARK: - Song section

    private var songPanel: PanelView!
    private var songNameLabel: NSTextField!
    private var tempoField: NSTextField!
    private var keyField: NSTextField!
    private var swingSlider: NSSlider!
    private var swingReadout: NSTextField!
    private var patternField: NSTextField!
    private var patternStepper: InspectorStepper!
    private var arrangementControl: InspectorSegmentedControl!

    // MARK: - Track section

    private var trackPanel: PanelView!
    private var trackNameField: CommitTextField!
    private var instrumentField: CommitTextField!
    private var trackKindLabel: NSTextField!
    private var colorPopUp: NSPopUpButton!
    private var volumeSlider: NSSlider!
    private var volumeReadout: NSTextField!
    private var panSlider: NSSlider!
    private var panReadout: NSTextField!
    private var trackClipCountLabel: NSTextField!
    private var trackNoteCountLabel: NSTextField!
    private var audioFileLabel: NSTextField!
    private var revealAudioButton: NSButton!

    // MARK: - Clip section

    private var clipPanel: PanelView!
    private var clipNameField: CommitTextField!
    private var clipStartField: NSTextField!
    private var clipLengthField: NSTextField!
    private var clipLaneLabel: NSTextField!
    private var deleteClipButton: NSButton!

    // MARK: - Summary section

    private var glancePanel: PanelView!
    private var glanceTrackLabel: NSTextField!
    private var glanceClipLabel: NSTextField!
    private var glanceNoteLabel: NSTextField!
    private var glanceAutomationLabel: NSTextField!
    private var glanceRecipeLabel: NSTextField!
    private var glanceAudioLabel: NSTextField!
    private var audioWarningRow: NSView!
    private var audioWarningLabel: NSTextField!

    // MARK: - Empty state

    private var emptyState: EmptyStateView!

    // MARK: - Init

    public init() {
        super.init(nibName: nil, bundle: nil)
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    // MARK: - Setup

    public override func loadView() {
        super.loadView()
        buildChrome()
        buildSongSection()
        buildEmptyState()
        buildTrackSection()
        buildClipSection()
        buildGlanceSection()
    }

    public override func viewDidLoad() {
        super.viewDidLoad()
        refresh()
    }

    /// Wrapping labels need a definite width before they can report a height.
    public override func viewDidLayout() {
        super.viewDidLayout()
        guard let label = audioWarningLabel else { return }
        let width = label.bounds.width
        if width > 1, abs(label.preferredMaxLayoutWidth - width) > 0.5 {
            label.preferredMaxLayoutWidth = width
            label.invalidateIntrinsicContentSize()
        }
    }

    private func buildChrome() {
        scrollView.translatesAutoresizingMaskIntoConstraints = false
        scrollView.hasVerticalScroller = true
        scrollView.hasHorizontalScroller = false
        scrollView.autohidesScrollers = true
        scrollView.drawsBackground = false
        scrollView.borderType = .noBorder
        scrollView.setAccessibilityLabel("Inspector")
        scrollView.setAccessibilityHelp("Settings for the song, the selected track, and the selected block.")

        container.translatesAutoresizingMaskIntoConstraints = false
        scrollView.documentView = container

        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = Layout.sectionSpacing
        stack.translatesAutoresizingMaskIntoConstraints = false
        container.addSubview(stack)

        view.addSubview(scrollView)

        NSLayoutConstraint.activate([
            scrollView.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            scrollView.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            scrollView.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor),
            scrollView.bottomAnchor.constraint(equalTo: view.bottomAnchor),

            container.leadingAnchor.constraint(equalTo: scrollView.contentView.leadingAnchor),
            container.topAnchor.constraint(equalTo: scrollView.contentView.topAnchor),
            container.widthAnchor.constraint(equalTo: scrollView.contentView.widthAnchor),

            stack.leadingAnchor.constraint(equalTo: container.leadingAnchor, constant: Layout.outerInset),
            stack.trailingAnchor.constraint(equalTo: container.trailingAnchor, constant: -Layout.outerInset),
            stack.topAnchor.constraint(equalTo: container.topAnchor, constant: Layout.outerInset),
            stack.bottomAnchor.constraint(equalTo: container.bottomAnchor, constant: -Layout.outerInset)
        ])
    }

    // MARK: - Song section

    private func buildSongSection() {
        let (panel, content) = makePanel(
            title: "Song",
            help: "Settings that apply to the whole project."
        )
        songPanel = panel

        songNameLabel = makeValueLabel("")
        let nameHelp = "The project's name. Use File ▸ Rename to change it, so the file on disk is renamed too."
        let nameRow = makeRow("Name", [songNameLabel], help: nameHelp)
        add(nameRow, to: content)

        let tempoHelp = AppEnvironment.shared.help(
            "How fast the song plays. Type a number between 40 and 300 and press Return.",
            term: "BPM"
        )
        tempoField = Controls.numberField(
            value: "120",
            placeholder: "120",
            help: tempoHelp,
            accessibilityLabel: "Tempo in beats per minute",
            width: Layout.numberWidth
        ) { [weak self] text in
            self?.commitTempo(text)
        }
        let tempoRow = makeRow(
            "Tempo",
            [tempoField, Controls.glossary("Tempo (BPM)", Glossary.long("BPM"))],
            help: tempoHelp
        )
        add(tempoRow, to: content)

        let keyHelp = AppEnvironment.shared.help(
            "The home note and scale of the song, for example “E minor”. Leave it empty if you don't know it.",
            term: "Key"
        )
        keyField = makeTextField(
            placeholder: "E minor",
            help: keyHelp,
            accessibilityLabel: "Key of the song",
            width: Layout.fieldWidth
        ) { [weak self] text in
            self?.commitKey(text)
        }
        add(makeRow("Key", [keyField], help: keyHelp), to: content)

        let swingHelp = AppEnvironment.shared.help(
            "Drag right to push every second beat slightly late, for a bouncier groove. 0 is perfectly straight.",
            term: "Swing"
        )
        swingReadout = makeReadout()
        swingSlider = Controls.slider(
            value: 0,
            min: 0,
            max: 75,
            help: swingHelp,
            accessibilityLabel: "Swing amount"
        ) { [weak self] value in
            self?.changeSwing(value)
        }
        let swingGroup = makeSliderGroup(
            title: "Swing",
            help: swingHelp,
            readout: swingReadout,
            slider: swingSlider,
            glossary: Controls.glossary("Swing", Glossary.long("Swing"))
        )
        add(swingGroup, to: content)

        let patternHelp = AppEnvironment.shared.help(
            "Which pattern the Pattern mode edits. Patterns are short musical ideas you can reuse.",
            term: "Pattern"
        )
        patternField = Controls.numberField(
            value: "1",
            placeholder: "1",
            help: patternHelp,
            accessibilityLabel: "Pattern number",
            width: Layout.smallNumberWidth
        ) { [weak self] text in
            self?.commitPattern(text)
        }
        patternStepper = InspectorStepper()
        patternStepper.minValue = 1
        patternStepper.maxValue = 99
        patternStepper.increment = 1
        patternStepper.valueWraps = false
        patternStepper.autorepeat = true
        patternStepper.integerValue = 1
        patternStepper.translatesAutoresizingMaskIntoConstraints = false
        patternStepper.toolTip = patternHelp
        patternStepper.setAccessibilityLabel("Pattern number")
        patternStepper.setAccessibilityHelp(patternHelp)
        patternStepper.target = patternStepper
        patternStepper.action = #selector(InspectorStepper.invoke)
        patternStepper.handler = { [weak self] value in
            self?.commitPattern(String(Int(value)))
        }
        let patternRow = makeRow(
            "Pattern",
            [patternField, patternStepper, Controls.glossary("Pattern", Glossary.long("Pattern"))],
            help: patternHelp
        )
        add(patternRow, to: content)

        let modeHelp = "Song plays the whole arrangement from start to finish. Pattern loops the one pattern you are working on."
        arrangementControl = InspectorSegmentedControl()
        arrangementControl.segmentCount = 2
        arrangementControl.setLabel("Song", forSegment: 0)
        arrangementControl.setLabel("Pattern", forSegment: 1)
        arrangementControl.trackingMode = .selectOne
        arrangementControl.segmentStyle = .automatic
        arrangementControl.controlSize = .small
        arrangementControl.font = Theme.Font.caption()
        arrangementControl.selectedSegment = 0
        arrangementControl.translatesAutoresizingMaskIntoConstraints = false
        arrangementControl.toolTip = modeHelp
        arrangementControl.setAccessibilityLabel("Playback mode")
        arrangementControl.setAccessibilityHelp(modeHelp)
        arrangementControl.target = arrangementControl
        arrangementControl.action = #selector(InspectorSegmentedControl.invoke)
        arrangementControl.handler = { [weak self] index in
            self?.changeArrangementMode(index)
        }
        add(makeRow("Plays", [arrangementControl], help: modeHelp), to: content)

        addSection(panel)
    }

    // MARK: - Empty state

    private func buildEmptyState() {
        emptyState = EmptyStateView(
            symbol: "cursorarrow.click.2",
            title: "Nothing selected",
            body: "Click a track on the left or a block in the timeline to see and change its settings here."
        )
        addSection(emptyState)
        emptyState.heightAnchor.constraint(equalToConstant: Layout.emptyStateHeight).isActive = true
    }

    // MARK: - Track section

    private func buildTrackSection() {
        let (panel, content) = makePanel(
            title: "Selected track",
            help: AppEnvironment.shared.help(
                "Settings for the track highlighted in the track list.",
                term: "Track"
            )
        )
        trackPanel = panel

        let nameHelp = "What this track is called. The name shows on its row and on every block it holds."
        trackNameField = makeTextField(
            placeholder: "Track name",
            help: nameHelp,
            accessibilityLabel: "Track name",
            width: Layout.fieldWidth
        ) { [weak self] text in
            self?.commitTrackName(text)
        }
        add(makeRow("Name", [trackNameField], help: nameHelp), to: content)

        let instrumentHelp = "The sound this track plays, in your own words — “Sub bass”, “Vocal chop”, “Rim shot”."
        instrumentField = makeTextField(
            placeholder: "Not set",
            help: instrumentHelp,
            accessibilityLabel: "Instrument",
            width: Layout.fieldWidth
        ) { [weak self] text in
            self?.commitInstrument(text)
        }
        add(makeRow("Instrument", [instrumentField], help: instrumentHelp), to: content)

        trackKindLabel = makeValueLabel("")
        add(
            makeRow(
                "Type",
                [trackKindLabel],
                help: "Whether this track plays a recorded sound file or notes you write yourself."
            ),
            to: content
        )

        let colorHelp = "The colour used for this track's row and its blocks in the timeline."
        var colorTitles = InspectorPane.colorPresets.map(\.name)
        colorTitles.append("Other colour")
        colorPopUp = Controls.popUp(
            titles: colorTitles,
            selected: 0,
            help: colorHelp,
            accessibilityLabel: "Track colour"
        ) { [weak self] index in
            self?.changeTrackColor(index)
        }
        for (index, preset) in InspectorPane.colorPresets.enumerated() {
            colorPopUp.item(at: index)?.image = colorSwatch(neonColor(from: preset.hex))
        }
        colorPopUp.widthAnchor.constraint(equalToConstant: Layout.fieldWidth).isActive = true
        add(makeRow("Colour", [colorPopUp], help: colorHelp), to: content)

        let volumeHelp = AppEnvironment.shared.help(
            "How loud this track is compared with the others. 100% is its natural level.",
            term: "Gain"
        )
        volumeReadout = makeReadout()
        volumeSlider = Controls.slider(
            value: MixerControl.neutral.gain,
            min: 0,
            max: 1.4,
            help: volumeHelp,
            accessibilityLabel: "Track volume"
        ) { [weak self] value in
            self?.changeVolume(value)
        }
        add(
            makeSliderGroup(title: "Volume", help: volumeHelp, readout: volumeReadout, slider: volumeSlider),
            to: content
        )

        let panHelp = AppEnvironment.shared.help(
            "Where this track sits between the left and right speakers. Centre is straight ahead.",
            term: "Pan"
        )
        panReadout = makeReadout()
        panSlider = Controls.slider(
            value: 0,
            min: -1,
            max: 1,
            help: panHelp,
            accessibilityLabel: "Track pan"
        ) { [weak self] value in
            self?.changePan(value)
        }
        add(makeSliderGroup(title: "Pan", help: panHelp, readout: panReadout, slider: panSlider), to: content)

        trackClipCountLabel = makeValueLabel("")
        add(
            makeRow(
                "Blocks",
                [trackClipCountLabel],
                help: AppEnvironment.shared.help(
                    "How many blocks of sound this track has in the arrangement.",
                    term: "Clip"
                )
            ),
            to: content
        )

        trackNoteCountLabel = makeValueLabel("")
        add(
            makeRow(
                "Notes",
                [trackNoteCountLabel],
                help: AppEnvironment.shared.help(
                    "How many notes this track has in the note editor.",
                    term: "Piano roll"
                )
            ),
            to: content
        )

        audioFileLabel = makeValueLabel("")
        add(
            makeRow(
                "Sound file",
                [audioFileLabel],
                help: AppEnvironment.shared.help(
                    "The audio file this track plays. Without one, this track is silent.",
                    term: "Stem"
                )
            ),
            to: content
        )

        revealAudioButton = Controls.button(
            title: "Reveal in Finder",
            symbol: "folder",
            help: "Show this track's sound file in a Finder window.",
            style: .quiet
        ) { [weak self] in
            self?.revealAudioFile()
        }
        add(makeButtonRow([revealAudioButton]), to: content)

        addSection(panel)
    }

    // MARK: - Clip section

    private func buildClipSection() {
        let (panel, content) = makePanel(
            title: "Selected block",
            help: AppEnvironment.shared.help(
                "Settings for the block highlighted in the timeline.",
                term: "Clip"
            )
        )
        clipPanel = panel

        let nameHelp = "What this block is called. The name is drawn across the block in the timeline."
        clipNameField = makeTextField(
            placeholder: "Block name",
            help: nameHelp,
            accessibilityLabel: "Block name",
            width: Layout.fieldWidth
        ) { [weak self] text in
            self?.commitClipName(text)
        }
        add(makeRow("Name", [clipNameField], help: nameHelp), to: content)

        let startHelp = AppEnvironment.shared.help(
            "Which bar this block starts on. Bar 1 is the very beginning of the song.",
            term: "Bar"
        )
        clipStartField = Controls.numberField(
            value: "1",
            placeholder: "1",
            help: startHelp,
            accessibilityLabel: "Start bar",
            width: Layout.numberWidth
        ) { [weak self] text in
            self?.commitClipStart(text)
        }
        add(makeRow("Starts at bar", [clipStartField], help: startHelp), to: content)

        let lengthHelp = AppEnvironment.shared.help(
            "How many bars this block lasts. Dragging its right edge in the timeline does the same thing.",
            term: "Bar"
        )
        clipLengthField = Controls.numberField(
            value: "1",
            placeholder: "4",
            help: lengthHelp,
            accessibilityLabel: "Length in bars",
            width: Layout.numberWidth
        ) { [weak self] text in
            self?.commitClipLength(text)
        }
        add(makeRow("Length", [clipLengthField], help: lengthHelp), to: content)

        clipLaneLabel = makeValueLabel("")
        add(
            makeRow(
                "On track",
                [clipLaneLabel],
                help: "The track this block plays on."
            ),
            to: content
        )

        deleteClipButton = Controls.button(
            title: "Delete Block",
            symbol: "trash",
            help: "Remove this block from the song. ⌘Z puts it back.",
            style: .destructive
        ) { [weak self] in
            self?.deleteSelectedClip()
        }
        add(makeButtonRow([deleteClipButton]), to: content)

        addSection(panel)
    }

    // MARK: - Summary section

    private func buildGlanceSection() {
        let (panel, content) = makePanel(
            title: "This song at a glance",
            help: "What the project contains right now."
        )
        glancePanel = panel

        glanceTrackLabel = makeValueLabel("")
        add(
            makeRow(
                "Tracks",
                [glanceTrackLabel],
                help: AppEnvironment.shared.help("How many tracks the song has.", term: "Track")
            ),
            to: content
        )

        glanceClipLabel = makeValueLabel("")
        add(
            makeRow(
                "Blocks",
                [glanceClipLabel],
                help: AppEnvironment.shared.help("How many blocks of sound are laid out.", term: "Clip")
            ),
            to: content
        )

        glanceNoteLabel = makeValueLabel("")
        add(
            makeRow(
                "Notes",
                [glanceNoteLabel],
                help: AppEnvironment.shared.help("How many written notes the song contains.", term: "Piano roll")
            ),
            to: content
        )

        glanceAutomationLabel = makeValueLabel("")
        add(
            makeRow(
                "Moving controls",
                [glanceAutomationLabel],
                help: AppEnvironment.shared.help(
                    "How many controls change by themselves over the song.",
                    term: "Automation"
                )
            ),
            to: content
        )

        glanceRecipeLabel = makeValueLabel("")
        add(
            makeRow(
                "Recipe",
                [glanceRecipeLabel],
                help: AppEnvironment.shared.help("How far through the build plan this song is.", term: "Recipe")
            ),
            to: content
        )

        glanceAudioLabel = makeValueLabel("")
        add(
            makeRow(
                "Audio ready",
                [glanceAudioLabel],
                help: AppEnvironment.shared.help(
                    "How many tracks have a sound file on disk. Only those make noise on Play.",
                    term: "Stem"
                )
            ),
            to: content
        )

        let (warningRow, warningLabel) = makeWarningRow(
            "None of these tracks has a sound file yet, so Play will be silent. Use Track ▸ Import Audio to add one, or Export Mix to render the song."
        )
        audioWarningRow = warningRow
        audioWarningLabel = warningLabel
        add(warningRow, to: content)

        addSection(panel)
    }

    // MARK: - Refresh

    public override func refresh() {
        guard isViewLoaded, songPanel != nil else { return }
        guard let host else {
            songPanel.isHidden = true
            trackPanel.isHidden = true
            clipPanel.isHidden = true
            glancePanel.isHidden = true
            emptyState.isHidden = false
            return
        }

        let project = host.project
        songPanel.isHidden = false
        glancePanel.isHidden = false

        updateSong(project)

        let track = project.track(id: host.selectedTrackId)
        trackPanel.isHidden = track == nil
        if let track {
            updateTrack(track, in: project)
        }

        let selection = selectedClip(in: project, clipId: host.selectedClipId)
        clipPanel.isHidden = selection == nil
        if let selection {
            updateClip(selection.clip, owner: selection.track)
        }

        emptyState.isHidden = !(track == nil && selection == nil)
        updateGlance(project, store: host.store)
    }

    private func updateSong(_ project: LocalProject) {
        setValue(songNameLabel, project.name, name: "Song name")
        songNameLabel.toolTip = "“\(project.name)”. Use File ▸ Rename to change it."

        setFieldValue(tempoField, formattedTempo(project.snapshot.bpm))
        setFieldValue(keyField, project.keyCenter ?? "")

        let swing = max(0, min(75, project.snapshot.swing ?? 0))
        setSliderValue(swingSlider, swing)
        setValue(swingReadout, "\(Int(swing.rounded()))%", name: "Swing")

        let pattern = max(1, min(99, project.snapshot.patternIndex ?? 1))
        setFieldValue(patternField, String(pattern))
        if patternStepper.integerValue != pattern {
            patternStepper.integerValue = pattern
        }

        let isPatternMode = project.snapshot.arrangementMode == "pattern"
        let segment = isPatternMode ? 1 : 0
        if arrangementControl.selectedSegment != segment {
            arrangementControl.selectedSegment = segment
        }
    }

    private func updateTrack(_ track: Track, in project: LocalProject) {
        trackPanel.title = "Selected track — \(track.name)"

        setFieldValue(trackNameField, track.name)
        setFieldValue(instrumentField, track.instrument ?? "")
        setValue(trackKindLabel, friendlyKind(for: track), name: "Track type")

        let presetIndex = InspectorPane.colorPresets.firstIndex {
            $0.hex.caseInsensitiveCompare(track.color ?? "") == .orderedSame
        }
        let selectedColorIndex = presetIndex ?? InspectorPane.colorPresets.count
        if colorPopUp.indexOfSelectedItem != selectedColorIndex {
            colorPopUp.selectItem(at: selectedColorIndex)
        }
        if presetIndex == nil {
            colorPopUp.item(at: InspectorPane.colorPresets.count)?.image = colorSwatch(
                neonColor(from: track.color, fallback: Theme.defaultTrackColor)
            )
        }

        let control = project.control(for: track.id)
        let gain = max(0, min(1.4, control.gain))
        setSliderValue(volumeSlider, gain)
        setValue(volumeReadout, "\(Int((gain * 100).rounded()))%", name: "Volume")

        let pan = max(-1, min(1, control.pan))
        setSliderValue(panSlider, pan)
        setValue(panReadout, panDescription(pan), name: "Pan")

        let clipCount = (track.clips ?? []).count
        setValue(trackClipCountLabel, countPhrase(clipCount, singular: "block", plural: "blocks"), name: "Blocks")

        let noteCount = project.notes(forTrack: track.id).count
        setValue(trackNoteCountLabel, countPhrase(noteCount, singular: "note", plural: "notes"), name: "Notes")

        let existing = host?.store.existingAudioURL(for: track)
        if let existing {
            setValue(audioFileLabel, existing.lastPathComponent, name: "Sound file")
            audioFileLabel.textColor = Theme.text
            audioFileLabel.toolTip = existing.path
            revealAudioButton.isEnabled = true
            revealAudioButton.toolTip = "Show “\(existing.lastPathComponent)” in a Finder window."
        } else if let file = track.file, !file.isEmpty {
            setValue(audioFileLabel, "Missing: \(URL(fileURLWithPath: file).lastPathComponent)", name: "Sound file")
            audioFileLabel.textColor = Theme.warning
            audioFileLabel.toolTip = "This track points at \(file), but that file is not there any more."
            revealAudioButton.isEnabled = false
            revealAudioButton.toolTip = "The file this track points at is missing, so there is nothing to show in the Finder."
        } else {
            setValue(audioFileLabel, "None yet", name: "Sound file")
            audioFileLabel.textColor = Theme.muted
            audioFileLabel.toolTip = "This track has no sound file, so it plays silence."
            revealAudioButton.isEnabled = false
            revealAudioButton.toolTip = "This track has no sound file yet. Use Track ▸ Import Audio to give it one."
        }
    }

    private func updateClip(_ clip: Clip, owner: Track) {
        clipPanel.title = "Selected block — \(clip.name)"
        setFieldValue(clipNameField, clip.name)
        setFieldValue(clipStartField, trimmedNumber((clip.startBar ?? 0) + 1))
        setFieldValue(clipLengthField, trimmedNumber(clip.bars ?? 1))
        setValue(clipLaneLabel, clip.lane ?? owner.name, name: "On track")
        deleteClipButton.toolTip = "Remove “\(clip.name)” from \(owner.name). ⌘Z puts it back."
    }

    private func updateGlance(_ project: LocalProject, store: ProjectStore) {
        let tracks = project.snapshot.tracks
        setValue(
            glanceTrackLabel,
            countPhrase(tracks.count, singular: "track", plural: "tracks"),
            name: "Tracks"
        )

        let clipCount = tracks.reduce(0) { $0 + ($1.clips ?? []).count }
        setValue(glanceClipLabel, countPhrase(clipCount, singular: "block", plural: "blocks"), name: "Blocks")

        let noteCount = (project.snapshot.notes ?? []).count
        setValue(glanceNoteLabel, countPhrase(noteCount, singular: "note", plural: "notes"), name: "Notes")

        let laneCount = (project.snapshot.automationLanes ?? []).count
        setValue(glanceAutomationLabel, countPhrase(laneCount, singular: "lane", plural: "lanes"), name: "Moving controls")

        let recipe = project.snapshot.recipe ?? []
        let done = recipe.filter(\.isDone).count
        setValue(
            glanceRecipeLabel,
            recipe.isEmpty ? "No steps yet" : "\(done) of \(recipe.count) steps done",
            name: "Recipe"
        )

        let counts = store.audioTrackCounts(for: project)
        setValue(
            glanceAudioLabel,
            "\(counts.withAudio) of \(counts.total) tracks have audio",
            name: "Audio ready"
        )
        glanceAudioLabel.textColor = counts.withAudio == 0 && counts.total > 0 ? Theme.warning : Theme.text
        audioWarningRow.isHidden = !(counts.total > 0 && counts.withAudio == 0)
    }

    // MARK: - Song edits

    private func commitTempo(_ text: String) {
        guard let host else { return }
        let current = host.project.snapshot.bpm
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let entered = Double(trimmed), entered.isFinite else {
            setFieldValue(tempoField, formattedTempo(current))
            StatusCenter.shared.warning(
                "Tempo has to be a number between 40 and 300, so it stayed at \(Int(current)).",
                detail: "“\(trimmed)” isn't a number. 120 is a typical pop tempo."
            )
            return
        }
        let clamped = min(300, max(40, entered))
        setFieldValue(tempoField, formattedTempo(clamped))
        guard abs(clamped - current) > 0.0001 else { return }
        host.edit("Set Tempo") { $0.snapshot.bpm = clamped }
        if abs(clamped - entered) > 0.0001 {
            StatusCenter.shared.warning(
                "Tempo has to be between 40 and 300, so \(Int(entered)) became \(Int(clamped)). ⌘Z undoes it."
            )
        } else {
            StatusCenter.shared.success("Tempo is now \(Int(clamped)) beats per minute. ⌘Z undoes it.")
        }
    }

    private func commitKey(_ text: String) {
        guard let host else { return }
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        let current = host.project.keyCenter ?? ""
        guard trimmed != current else { return }
        host.edit("Set Key") { $0.keyCenter = trimmed.isEmpty ? nil : trimmed }
        if trimmed.isEmpty {
            StatusCenter.shared.success("Cleared the key. ⌘Z undoes it.")
        } else {
            StatusCenter.shared.success("The song's key is now \(trimmed). ⌘Z undoes it.")
        }
    }

    private func changeSwing(_ value: Double) {
        let rounded = max(0, min(75, value.rounded()))
        setValue(swingReadout, "\(Int(rounded))%", name: "Swing")
        guard isCommitEvent(), let host else { return }
        let current = host.project.snapshot.swing ?? 0
        guard abs(rounded - current) > 0.0001 else { return }
        host.edit("Change Swing") { $0.snapshot.swing = rounded }
        StatusCenter.shared.success(
            rounded == 0
                ? "Swing is off, so the rhythm is perfectly straight. ⌘Z undoes it."
                : "Swing is now \(Int(rounded))%, so every second beat lands slightly late. ⌘Z undoes it."
        )
    }

    private func commitPattern(_ text: String) {
        guard let host else { return }
        let current = max(1, min(99, host.project.snapshot.patternIndex ?? 1))
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let entered = Int(trimmed) else {
            setFieldValue(patternField, String(current))
            patternStepper.integerValue = current
            StatusCenter.shared.warning("A pattern number has to be a whole number from 1 to 99, so it stayed at \(current).")
            return
        }
        let clamped = max(1, min(99, entered))
        setFieldValue(patternField, String(clamped))
        patternStepper.integerValue = clamped
        guard clamped != current else { return }
        host.edit("Change Pattern") { $0.snapshot.patternIndex = clamped }
        StatusCenter.shared.success("Now editing pattern \(clamped). ⌘Z undoes it.")
    }

    private func changeArrangementMode(_ index: Int) {
        guard let host else { return }
        let mode = index == 1 ? "pattern" : "song"
        guard mode != (host.project.snapshot.arrangementMode ?? "song") else { return }
        host.edit("Change Arrangement Mode") { $0.snapshot.arrangementMode = mode }
        StatusCenter.shared.success(
            mode == "pattern"
                ? "Playback now loops the current pattern instead of the whole song. ⌘Z undoes it."
                : "Playback now runs the whole song from start to finish. ⌘Z undoes it."
        )
    }

    // MARK: - Track edits

    private func commitTrackName(_ text: String) {
        guard let host, let track = host.project.track(id: host.selectedTrackId) else { return }
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            setFieldValue(trackNameField, track.name)
            StatusCenter.shared.warning("A track needs a name, so it stayed “\(track.name)”.")
            return
        }
        guard trimmed != track.name else { return }
        mutateSelectedTrack("Rename Track") { $0.name = trimmed }
        StatusCenter.shared.success("Renamed “\(track.name)” to “\(trimmed)”. ⌘Z undoes it.")
    }

    private func commitInstrument(_ text: String) {
        guard let host, let track = host.project.track(id: host.selectedTrackId) else { return }
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed != (track.instrument ?? "") else { return }
        mutateSelectedTrack("Set Instrument") { $0.instrument = trimmed.isEmpty ? nil : trimmed }
        StatusCenter.shared.success(
            trimmed.isEmpty
                ? "Cleared the instrument for \(track.name). ⌘Z undoes it."
                : "\(track.name) is now described as “\(trimmed)”. ⌘Z undoes it."
        )
    }

    private func changeTrackColor(_ index: Int) {
        guard let host, let track = host.project.track(id: host.selectedTrackId) else { return }
        guard index >= 0, index < InspectorPane.colorPresets.count else {
            // "Other colour" only ever describes the colour a file already has,
            // so choosing it should not silently change anything.
            let presetIndex = InspectorPane.colorPresets.firstIndex {
                $0.hex.caseInsensitiveCompare(track.color ?? "") == .orderedSame
            }
            colorPopUp.selectItem(at: presetIndex ?? InspectorPane.colorPresets.count)
            return
        }
        let preset = InspectorPane.colorPresets[index]
        guard preset.hex.caseInsensitiveCompare(track.color ?? "") != .orderedSame else { return }
        mutateSelectedTrack("Change Track Colour") { $0.color = preset.hex }
        StatusCenter.shared.success("\(track.name) is now \(preset.name.lowercased()). ⌘Z undoes it.")
    }

    private func changeVolume(_ value: Double) {
        let clamped = max(0, min(1.4, value))
        setValue(volumeReadout, "\(Int((clamped * 100).rounded()))%", name: "Volume")
        guard isCommitEvent(), let host, let track = host.project.track(id: host.selectedTrackId) else { return }
        guard abs(clamped - host.project.control(for: track.id).gain) > 0.001 else { return }
        mutateSelectedControl("Change Volume") { $0.gain = clamped }
        StatusCenter.shared.success(
            "\(track.name) is now at \(Int((clamped * 100).rounded()))% volume. ⌘Z undoes it."
        )
    }

    private func changePan(_ value: Double) {
        let clamped = max(-1, min(1, value))
        setValue(panReadout, panDescription(clamped), name: "Pan")
        guard isCommitEvent(), let host, let track = host.project.track(id: host.selectedTrackId) else { return }
        guard abs(clamped - host.project.control(for: track.id).pan) > 0.001 else { return }
        mutateSelectedControl("Change Pan") { $0.pan = clamped }
        StatusCenter.shared.success("\(track.name) now sits \(panDescription(clamped).lowercased()). ⌘Z undoes it.")
    }

    private func revealAudioFile() {
        guard let host,
              let track = host.project.track(id: host.selectedTrackId),
              let url = host.store.existingAudioURL(for: track) else {
            StatusCenter.shared.info("This track has no sound file yet. Use Track ▸ Import Audio to add one.")
            return
        }
        NSWorkspace.shared.activateFileViewerSelecting([url])
    }

    // MARK: - Clip edits

    private func commitClipName(_ text: String) {
        guard let host, let selection = selectedClip(in: host.project, clipId: host.selectedClipId) else { return }
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            setFieldValue(clipNameField, selection.clip.name)
            StatusCenter.shared.warning("A block needs a name, so it stayed “\(selection.clip.name)”.")
            return
        }
        guard trimmed != selection.clip.name else { return }
        mutateSelectedClip("Rename Clip") { $0.name = trimmed }
        StatusCenter.shared.success("Renamed the block to “\(trimmed)”. ⌘Z undoes it.")
    }

    private func commitClipStart(_ text: String) {
        guard let host, let selection = selectedClip(in: host.project, clipId: host.selectedClipId) else { return }
        let current = selection.clip.startBar ?? 0
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let entered = Double(trimmed), entered.isFinite else {
            setFieldValue(clipStartField, trimmedNumber(current + 1))
            StatusCenter.shared.warning("A start bar has to be a number, so “\(selection.clip.name)” did not move.")
            return
        }
        let clamped = max(0, entered - 1)
        setFieldValue(clipStartField, trimmedNumber(clamped + 1))
        guard abs(clamped - current) > 0.0001 else { return }
        mutateSelectedClip("Move Clip") { $0.startBar = clamped }
        StatusCenter.shared.success(
            "“\(selection.clip.name)” now starts at bar \(trimmedNumber(clamped + 1)). ⌘Z undoes it."
        )
    }

    private func commitClipLength(_ text: String) {
        guard let host, let selection = selectedClip(in: host.project, clipId: host.selectedClipId) else { return }
        let current = selection.clip.bars ?? 1
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let entered = Double(trimmed), entered.isFinite else {
            setFieldValue(clipLengthField, trimmedNumber(current))
            StatusCenter.shared.warning("A length has to be a number of bars, so “\(selection.clip.name)” is unchanged.")
            return
        }
        let clamped = max(0.25, min(512, entered))
        setFieldValue(clipLengthField, trimmedNumber(clamped))
        guard abs(clamped - current) > 0.0001 else { return }
        mutateSelectedClip("Resize Clip") { $0.bars = clamped }
        StatusCenter.shared.success(
            "“\(selection.clip.name)” is now \(trimmedNumber(clamped)) bars long. ⌘Z undoes it."
        )
    }

    private func deleteSelectedClip() {
        guard let host, let selection = selectedClip(in: host.project, clipId: host.selectedClipId) else {
            StatusCenter.shared.info("Select a block in the timeline first.")
            return
        }
        let name = selection.clip.name
        let clipId = selection.clip.id
        // Clearing the selection inside the same edit means one ⌘Z brings back
        // both the block and the fact that it was selected.
        host.edit("Delete Clip") { project in
            for index in project.snapshot.tracks.indices {
                project.snapshot.tracks[index].clips = (project.snapshot.tracks[index].clips ?? [])
                    .filter { $0.id != clipId }
            }
            project.snapshot.selectedClipId = ""
        }
        StatusCenter.shared.success("Deleted the block “\(name)”. ⌘Z puts it back.")
    }

    // MARK: - Editing helpers

    private func mutateSelectedTrack(_ actionName: String, _ body: (inout Track) -> Void) {
        guard let host else { return }
        let trackId = host.selectedTrackId
        host.edit(actionName) { project in
            guard let index = project.snapshot.tracks.firstIndex(where: { $0.id == trackId }) else { return }
            body(&project.snapshot.tracks[index])
        }
    }

    private func mutateSelectedControl(_ actionName: String, _ body: (inout MixerControl) -> Void) {
        guard let host else { return }
        let trackId = host.selectedTrackId
        host.edit(actionName) { project in
            guard project.track(id: trackId) != nil else { return }
            var controls = project.snapshot.controls ?? [:]
            var control = controls[trackId] ?? project.control(for: trackId)
            body(&control)
            controls[trackId] = control
            project.snapshot.controls = controls
            // Mirrored onto the track so a file saved now still sounds right if
            // it is later opened by something that reads only the track fields.
            if let index = project.snapshot.tracks.firstIndex(where: { $0.id == trackId }) {
                project.snapshot.tracks[index].gain = control.gain
                project.snapshot.tracks[index].pan = control.pan
            }
        }
    }

    private func mutateSelectedClip(_ actionName: String, _ body: (inout Clip) -> Void) {
        guard let host else { return }
        let clipId = host.selectedClipId
        guard !clipId.isEmpty else { return }
        host.edit(actionName) { project in
            for trackIndex in project.snapshot.tracks.indices {
                var clips = project.snapshot.tracks[trackIndex].clips ?? []
                guard let clipIndex = clips.firstIndex(where: { $0.id == clipId }) else { continue }
                body(&clips[clipIndex])
                project.snapshot.tracks[trackIndex].clips = clips
                return
            }
        }
    }

    private func selectedClip(in project: LocalProject, clipId: String) -> (track: Track, clip: Clip)? {
        guard !clipId.isEmpty else { return nil }
        for track in project.snapshot.tracks {
            if let clip = (track.clips ?? []).first(where: { $0.id == clipId }) {
                return (track, clip)
            }
        }
        return nil
    }

    /// True when a slider's action came from the end of a drag or from the
    /// keyboard, rather than from the middle of a drag. Continuous sliders give
    /// a live readout, but only committed values become undo steps — otherwise
    /// one drag would bury the Edit menu under hundreds of "Undo Change Volume".
    private func isCommitEvent() -> Bool {
        guard let event = NSApp.currentEvent else { return true }
        switch event.type {
        case .leftMouseDragged, .rightMouseDragged, .otherMouseDragged, .mouseMoved:
            return false
        default:
            return true
        }
    }

    // MARK: - Value helpers

    private func setFieldValue(_ field: NSTextField, _ text: String) {
        // Never overwrite what somebody is in the middle of typing.
        guard field.currentEditor() == nil else { return }
        if field.stringValue != text {
            field.stringValue = text
        }
    }

    private func setValue(_ label: NSTextField, _ text: String, name: String) {
        if label.stringValue != text {
            label.stringValue = text
        }
        label.setAccessibilityLabel("\(name): \(text)")
    }

    private func setSliderValue(_ slider: NSSlider, _ value: Double) {
        guard abs(slider.doubleValue - value) > 0.0001 else { return }
        slider.doubleValue = value
    }

    private func formattedTempo(_ bpm: Double) -> String {
        trimmedNumber(bpm)
    }

    private func trimmedNumber(_ value: Double) -> String {
        if abs(value - value.rounded()) < 0.001 {
            return String(Int(value.rounded()))
        }
        return String(format: "%.2f", value)
    }

    private func countPhrase(_ count: Int, singular: String, plural: String) -> String {
        count == 1 ? "1 \(singular)" : "\(count) \(plural)"
    }

    private func panDescription(_ pan: Double) -> String {
        if abs(pan) < 0.02 { return "Centre" }
        let percent = Int((abs(pan) * 100).rounded())
        return pan < 0 ? "\(percent)% left" : "\(percent)% right"
    }

    private func friendlyKind(for track: Track) -> String {
        switch (track.kind ?? "").lowercased() {
        case "audio": return "Recorded sound"
        case "automation": return "Moving control"
        case "instrument", "synth": return "Played instrument"
        case "drum", "drums", "percussion": return "Drums"
        case "": return track.file == nil ? "Written notes" : "Recorded sound"
        default: return (track.kind ?? "").capitalized
        }
    }

    private func colorSwatch(_ color: NSColor) -> NSImage {
        NSImage(size: NSSize(width: 12, height: 12), flipped: false) { rect in
            let path = NSBezierPath(roundedRect: rect.insetBy(dx: 0.5, dy: 0.5), xRadius: 3, yRadius: 3)
            color.setFill()
            path.fill()
            Theme.subtleStroke.setStroke()
            path.lineWidth = 1
            path.stroke()
            return true
        }
    }

    // MARK: - View building helpers

    private func makePanel(title: String, help: String) -> (PanelView, NSStackView) {
        let panel = PanelView(title: title, help: help)
        let content = NSStackView()
        content.orientation = .vertical
        content.alignment = .leading
        content.spacing = Layout.rowSpacing
        content.translatesAutoresizingMaskIntoConstraints = false
        panel.contentView.addSubview(content)
        NSLayoutConstraint.activate([
            content.leadingAnchor.constraint(equalTo: panel.contentView.leadingAnchor, constant: 12),
            content.trailingAnchor.constraint(equalTo: panel.contentView.trailingAnchor, constant: -12),
            content.topAnchor.constraint(equalTo: panel.contentView.topAnchor),
            content.bottomAnchor.constraint(equalTo: panel.contentView.bottomAnchor, constant: -12)
        ])
        return (panel, content)
    }

    /// Adds a section to the scrolling column at full width.
    private func addSection(_ view: NSView) {
        stack.addArrangedSubview(view)
        view.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true
    }

    /// Adds a row inside a panel at full width, so every row's label column
    /// lines up with every other one.
    private func add(_ row: NSView, to content: NSStackView) {
        content.addArrangedSubview(row)
        row.widthAnchor.constraint(equalTo: content.widthAnchor).isActive = true
    }

    private func makeRow(
        _ title: String,
        _ controls: [NSView],
        help: String,
        alignment: NSLayoutConstraint.Attribute = .centerY
    ) -> NSStackView {
        let label = makeLabel(title, font: Theme.Font.body(12), color: Theme.muted)
        label.alignment = .right
        label.toolTip = help
        label.setAccessibilityLabel(title)
        label.widthAnchor.constraint(equalToConstant: Layout.labelWidth).isActive = true

        let row = NSStackView(views: [label] + controls + [makeSpacer()])
        row.orientation = .horizontal
        row.alignment = alignment
        row.distribution = .fill
        row.spacing = 8
        row.translatesAutoresizingMaskIntoConstraints = false
        row.setAccessibilityRole(.group)
        row.setAccessibilityLabel(title)
        row.setAccessibilityHelp(help)
        return row
    }

    /// A slider gets its own two-line group: title and readout above, the full
    /// width of the track below, so the handle is easy to grab even when the
    /// inspector is at its narrowest.
    private func makeSliderGroup(
        title: String,
        help: String,
        readout: NSTextField,
        slider: NSSlider,
        glossary: NSButton? = nil
    ) -> NSStackView {
        let label = makeLabel(title, font: Theme.Font.body(12), color: Theme.muted)
        label.toolTip = help
        label.setAccessibilityLabel(title)

        var headerViews: [NSView] = [label, makeSpacer(), readout]
        if let glossary {
            headerViews.append(glossary)
        }
        let header = NSStackView(views: headerViews)
        header.orientation = .horizontal
        header.alignment = .centerY
        header.distribution = .fill
        header.spacing = 6
        header.translatesAutoresizingMaskIntoConstraints = false

        slider.setContentHuggingPriority(NSLayoutConstraint.Priority(1), for: .horizontal)

        let group = NSStackView(views: [header, slider])
        group.orientation = .vertical
        group.alignment = .leading
        group.spacing = 2
        group.translatesAutoresizingMaskIntoConstraints = false
        group.setAccessibilityRole(.group)
        group.setAccessibilityLabel(title)
        group.setAccessibilityHelp(help)

        NSLayoutConstraint.activate([
            header.widthAnchor.constraint(equalTo: group.widthAnchor),
            slider.widthAnchor.constraint(equalTo: group.widthAnchor)
        ])
        return group
    }

    private func makeButtonRow(_ views: [NSView]) -> NSStackView {
        let row = NSStackView(views: views + [makeSpacer()])
        row.orientation = .horizontal
        row.alignment = .centerY
        row.distribution = .fill
        row.spacing = 8
        row.translatesAutoresizingMaskIntoConstraints = false
        return row
    }

    private func makeWarningRow(_ text: String) -> (NSView, NSTextField) {
        let icon = NSImageView()
        icon.image = NSImage(systemSymbolName: "exclamationmark.triangle.fill", accessibilityDescription: "Warning")
        icon.symbolConfiguration = .init(pointSize: 12, weight: .semibold)
        icon.contentTintColor = Theme.warning
        icon.translatesAutoresizingMaskIntoConstraints = false
        icon.setAccessibilityLabel("Warning")

        let label = makeLabel(text, font: Theme.Font.caption(11), color: Theme.warning)
        label.lineBreakMode = .byWordWrapping
        label.maximumNumberOfLines = 0
        label.toolTip = text
        label.setAccessibilityLabel(text)

        let row = NSStackView(views: [icon, label])
        row.orientation = .horizontal
        row.alignment = .top
        row.distribution = .fill
        row.spacing = 6
        row.translatesAutoresizingMaskIntoConstraints = false
        row.setAccessibilityRole(.group)
        row.setAccessibilityLabel("Warning")
        row.setAccessibilityHelp(text)

        NSLayoutConstraint.activate([
            icon.widthAnchor.constraint(equalToConstant: 14),
            label.widthAnchor.constraint(equalTo: row.widthAnchor, constant: -20)
        ])
        return (row, label)
    }

    private func makeSpacer() -> NSView {
        let spacer = NSView()
        spacer.translatesAutoresizingMaskIntoConstraints = false
        spacer.setContentHuggingPriority(NSLayoutConstraint.Priority(1), for: .horizontal)
        spacer.setContentCompressionResistancePriority(NSLayoutConstraint.Priority(1), for: .horizontal)
        return spacer
    }

    private func makeValueLabel(_ text: String) -> NSTextField {
        let label = makeLabel(text, font: Theme.Font.body(12), color: Theme.text)
        label.lineBreakMode = .byTruncatingTail
        return label
    }

    private func makeReadout() -> NSTextField {
        let label = makeLabel("", font: Theme.Font.mono(11), color: Theme.text)
        label.alignment = .right
        label.setContentHuggingPriority(.defaultHigh, for: .horizontal)
        return label
    }

    private func makeTextField(
        placeholder: String,
        help: String,
        accessibilityLabel: String,
        width: CGFloat,
        commit: @escaping (String) -> Void
    ) -> CommitTextField {
        let field = CommitTextField(string: "")
        field.commitHandler = commit
        field.placeholderString = placeholder
        field.font = Theme.Font.body(12)
        field.controlSize = .small
        field.alignment = .left
        field.usesSingleLineMode = true
        field.lineBreakMode = .byTruncatingTail
        field.toolTip = help
        field.setAccessibilityLabel(accessibilityLabel)
        field.setAccessibilityHelp(help)
        field.translatesAutoresizingMaskIntoConstraints = false
        field.widthAnchor.constraint(equalToConstant: width).isActive = true
        return field
    }
}

// MARK: - Small local controls
//
// Closure-backed variants of the two AppKit controls `Controls` does not cover.
// They exist only in this file.

private final class InspectorStepper: NSStepper {
    var handler: ((Double) -> Void)?
    @objc func invoke() { handler?(doubleValue) }
}

private final class InspectorSegmentedControl: NSSegmentedControl {
    var handler: ((Int) -> Void)?
    @objc func invoke() { handler?(selectedSegment) }
}

/// Scroll views start at the top only when their document view is flipped.
private final class InspectorFlippedView: NSView {
    override var isFlipped: Bool { true }
}
