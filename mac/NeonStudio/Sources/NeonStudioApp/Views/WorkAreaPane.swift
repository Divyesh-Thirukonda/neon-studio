import AppKit
import NeonStudioKit

/// The centre column of a document window: the view switcher, every editing
/// canvas, and the automation strip underneath them.
///
/// Two things changed from the previous build. First, the view switcher is a
/// real `NSSegmentedControl`, so it *shows* which view you are in — the old row
/// of hand-drawn buttons never indicated the current view at all, and you had to
/// guess from the contents. Second, each canvas is created once and kept alive,
/// so scroll position and selection survive switching tabs instead of being
/// rebuilt from scratch every time.
final class WorkAreaPane: BaseDocumentPane, NSSplitViewDelegate {

    // MARK: Canvases
    //
    // Created once, up front, and never thrown away.

    private let timelineView = TimelineView()
    private let pianoRollView = PianoRollView()
    private let mixerConsoleView = MixerConsoleView()
    private let effectsView = EffectsView()
    private let sampleEditorView = SampleEditorView()
    private let recipeView = RecipeView()
    private let automationEditorView = AutomationEditorView()

    private var allCanvases: [EditorCanvas] {
        [timelineView, pianoRollView, mixerConsoleView, effectsView,
         sampleEditorView, recipeView, automationEditorView]
    }

    // MARK: Chrome

    private let topBar = ThemedBackgroundView { Theme.panel }
    private let viewPicker = NSSegmentedControl()
    private let toolPicker = NSSegmentedControl()
    private let explainerLabel = makeLabel("", font: Theme.Font.caption(11), color: Theme.muted)

    private let splitView = NSSplitView()
    private let canvasContainer = ThemedBackgroundView { Theme.canvas }
    private let automationContainer = ThemedBackgroundView { Theme.panelAlt }
    private let automationScrollView = NSScrollView()
    private var automationCollapseButton: NSButton?
    private var automationEmptyState: EmptyStateView?

    /// One scroll view per work view, so each keeps its own scroll offset.
    private var scrollViews: [WorkView: NSScrollView] = [:]

    private var isBuilt = false
    private var isSizingDocument = false
    private var hasPlacedDivider = false
    private var expandedAutomationHeight: CGFloat = 190
    private var automationHasLanes = false

    private let automationHeaderHeight: CGFloat = 30
    private let minimumCanvasHeight: CGFloat = 200

    // MARK: Zoom

    /// Horizontal scale of the bar grid, in points per bar. Deliberately not
    /// stored in the project: how far you happen to be zoomed in is a property
    /// of looking, not of the song.
    var pixelsPerBar: CGFloat = 44 {
        didSet {
            guard abs(pixelsPerBar - oldValue) > 0.01 else { return }
            timelineView.pixelsPerBar = pixelsPerBar
            automationEditorView.pixelsPerBar = pixelsPerBar
            guard isBuilt else { return }
            layoutDocument(of: scrollView(for: .playlist))
            layoutDocument(of: automationScrollView)
        }
    }

    // MARK: Init

    init() {
        super.init(nibName: nil, bundle: nil)
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    deinit {
        NotificationCenter.default.removeObserver(self)
    }

    // MARK: Building

    override func loadView() {
        super.loadView()
        buildTopBar()
        buildSplitView()
        assemble()
        isBuilt = true
        // Push the current zoom into the canvases: it may have been set from the
        // toolbar before the window ever laid itself out.
        timelineView.pixelsPerBar = pixelsPerBar
        automationEditorView.pixelsPerBar = pixelsPerBar
        refresh()
    }

    private func buildTopBar() {
        topBar.translatesAutoresizingMaskIntoConstraints = false
        topBar.wantsLayer = true

        configureViewPicker()
        configureToolPicker()

        explainerLabel.alignment = .right
        explainerLabel.lineBreakMode = .byTruncatingTail
        explainerLabel.maximumNumberOfLines = 1
        explainerLabel.setContentHuggingPriority(.defaultLow, for: .horizontal)
        explainerLabel.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        explainerLabel.setAccessibilityRole(.staticText)
        explainerLabel.setAccessibilityLabel("What this view is for")

        let row = NSStackView(views: [viewPicker, toolPicker, explainerLabel])
        row.orientation = .horizontal
        row.alignment = .centerY
        row.distribution = .fill
        row.spacing = Theme.Metric.gutter
        row.translatesAutoresizingMaskIntoConstraints = false

        let hairline = Controls.separator(vertical: false)

        topBar.addSubview(row)
        topBar.addSubview(hairline)
        NSLayoutConstraint.activate([
            row.leadingAnchor.constraint(equalTo: topBar.leadingAnchor, constant: Theme.Metric.panelPadding),
            row.trailingAnchor.constraint(equalTo: topBar.trailingAnchor, constant: -Theme.Metric.panelPadding),
            row.topAnchor.constraint(equalTo: topBar.topAnchor, constant: 8),
            row.bottomAnchor.constraint(equalTo: topBar.bottomAnchor, constant: -8),

            hairline.leadingAnchor.constraint(equalTo: topBar.leadingAnchor),
            hairline.trailingAnchor.constraint(equalTo: topBar.trailingAnchor),
            hairline.bottomAnchor.constraint(equalTo: topBar.bottomAnchor)
        ])
    }

    private func configureViewPicker() {
        let views = WorkView.allCases
        viewPicker.segmentCount = views.count
        viewPicker.trackingMode = .selectOne
        viewPicker.segmentStyle = .automatic
        viewPicker.segmentDistribution = .fit
        viewPicker.controlSize = .regular
        viewPicker.font = Theme.Font.caption(11)
        viewPicker.translatesAutoresizingMaskIntoConstraints = false
        viewPicker.target = self
        viewPicker.action = #selector(viewPickerChanged(_:))
        viewPicker.setContentHuggingPriority(.defaultHigh, for: .horizontal)
        viewPicker.setContentCompressionResistancePriority(.required, for: .horizontal)

        for (index, view) in views.enumerated() {
            viewPicker.setLabel(view.label, forSegment: index)
            if let image = NSImage(systemSymbolName: view.symbolName, accessibilityDescription: view.label) {
                viewPicker.setImage(image, forSegment: index)
                viewPicker.setImageScaling(.scaleProportionallyDown, forSegment: index)
            }
            let help = AppEnvironment.shared.help(
                "\(view.explanation) (⌘\(view.keyEquivalent))",
                term: glossaryTerm(for: view)
            )
            viewPicker.setToolTip(help, forSegment: index)
        }
        viewPicker.selectedSegment = 0
        viewPicker.toolTip = "Switch between arranging, writing notes, mixing, and the rest."
        viewPicker.setAccessibilityLabel("Editor view")
        viewPicker.setAccessibilityHelp("Chooses what the middle of the window shows.")
    }

    private func configureToolPicker() {
        let tools = ToolId.allCases
        toolPicker.segmentCount = tools.count
        toolPicker.trackingMode = .selectOne
        toolPicker.segmentStyle = .automatic
        toolPicker.segmentDistribution = .fit
        toolPicker.controlSize = .regular
        toolPicker.font = Theme.Font.caption(11)
        toolPicker.translatesAutoresizingMaskIntoConstraints = false
        toolPicker.target = self
        toolPicker.action = #selector(toolPickerChanged(_:))
        toolPicker.setContentHuggingPriority(.defaultHigh, for: .horizontal)
        toolPicker.setContentCompressionResistancePriority(.required, for: .horizontal)

        for (index, tool) in tools.enumerated() {
            toolPicker.setLabel(tool.label, forSegment: index)
            if let image = NSImage(systemSymbolName: tool.symbolName, accessibilityDescription: tool.label) {
                toolPicker.setImage(image, forSegment: index)
                toolPicker.setImageScaling(.scaleProportionallyDown, forSegment: index)
            }
            toolPicker.setToolTip(tool.explanation, forSegment: index)
        }
        toolPicker.selectedSegment = 0
        toolPicker.toolTip = "What clicking does: select, draw something new, or erase."
        toolPicker.setAccessibilityLabel("Editing tool")
        toolPicker.setAccessibilityHelp("Chooses what a click on the canvas does.")
    }

    private func buildSplitView() {
        canvasContainer.translatesAutoresizingMaskIntoConstraints = false
        canvasContainer.wantsLayer = true
        canvasContainer.setAccessibilityRole(.group)

        for view in WorkView.allCases {
            let scroll = makeScrollView(for: canvas(for: view), horizontal: scrollsHorizontally(view))
            scrollViews[view] = scroll
            scroll.isHidden = true
            canvasContainer.addSubview(scroll)
            NSLayoutConstraint.activate([
                scroll.leadingAnchor.constraint(equalTo: canvasContainer.leadingAnchor),
                scroll.trailingAnchor.constraint(equalTo: canvasContainer.trailingAnchor),
                scroll.topAnchor.constraint(equalTo: canvasContainer.topAnchor),
                scroll.bottomAnchor.constraint(equalTo: canvasContainer.bottomAnchor)
            ])
        }

        buildAutomationSection()

        splitView.translatesAutoresizingMaskIntoConstraints = false
        splitView.isVertical = false
        splitView.dividerStyle = .thin
        splitView.arrangesAllSubviews = false
        // Named so the height the user chose for the automation strip comes back
        // the next time they open a song.
        splitView.autosaveName = "NeonStudioWorkAreaSplit"
        splitView.delegate = self
        splitView.addArrangedSubview(canvasContainer)
        splitView.addArrangedSubview(automationContainer)
        splitView.setHoldingPriority(NSLayoutConstraint.Priority(rawValue: 250), forSubviewAt: 0)
        splitView.setHoldingPriority(NSLayoutConstraint.Priority(rawValue: 260), forSubviewAt: 1)
        splitView.setAccessibilityLabel("Editor and automation")
    }

    private func buildAutomationSection() {
        automationContainer.translatesAutoresizingMaskIntoConstraints = false
        automationContainer.wantsLayer = true
        automationContainer.setAccessibilityRole(.group)
        automationContainer.setAccessibilityLabel("Automation")

        let header = NSView()
        header.translatesAutoresizingMaskIntoConstraints = false

        let title = makeLabel("Automation", font: Theme.Font.captionBold(11), color: Theme.muted)
        title.setContentCompressionResistancePriority(.required, for: .horizontal)

        let helpButton = Controls.glossary("Automation", Glossary.long("Automation"))

        let collapse = Controls.button(
            title: "Hide",
            symbol: "chevron.down",
            help: "Hide the automation strip to give the editor more room.",
            style: .quiet
        ) { [weak self] in
            self?.toggleAutomationCollapsed()
        }
        automationCollapseButton = collapse

        let spacer = NSView()
        spacer.translatesAutoresizingMaskIntoConstraints = false
        spacer.setContentHuggingPriority(.defaultLow, for: .horizontal)

        let row = NSStackView(views: [title, helpButton, spacer, collapse])
        row.orientation = .horizontal
        row.alignment = .centerY
        row.spacing = 6
        row.translatesAutoresizingMaskIntoConstraints = false

        let hairline = Controls.separator(vertical: false)
        header.addSubview(row)
        header.addSubview(hairline)
        NSLayoutConstraint.activate([
            row.leadingAnchor.constraint(equalTo: header.leadingAnchor, constant: Theme.Metric.panelPadding),
            row.trailingAnchor.constraint(equalTo: header.trailingAnchor, constant: -8),
            row.centerYAnchor.constraint(equalTo: header.centerYAnchor),
            hairline.leadingAnchor.constraint(equalTo: header.leadingAnchor),
            hairline.trailingAnchor.constraint(equalTo: header.trailingAnchor),
            hairline.topAnchor.constraint(equalTo: header.topAnchor)
        ])

        configure(scrollView: automationScrollView, for: automationEditorView, horizontal: true)

        let empty = EmptyStateView(
            symbol: "point.topleft.down.curvedto.point.bottomright.up",
            title: "No automation yet",
            body: "Automation makes a setting change over time — a fade-in, or a filter opening up. Add a lane for each track to start drawing one.",
            actionTitle: "Add Automation Lanes",
            action: { [weak self] in self?.addDefaultAutomationLanes() }
        )
        empty.isHidden = true
        automationEmptyState = empty

        automationContainer.addSubview(header)
        automationContainer.addSubview(automationScrollView)
        automationContainer.addSubview(empty)
        NSLayoutConstraint.activate([
            header.leadingAnchor.constraint(equalTo: automationContainer.leadingAnchor),
            header.trailingAnchor.constraint(equalTo: automationContainer.trailingAnchor),
            header.topAnchor.constraint(equalTo: automationContainer.topAnchor),
            header.heightAnchor.constraint(equalToConstant: automationHeaderHeight),

            automationScrollView.leadingAnchor.constraint(equalTo: automationContainer.leadingAnchor),
            automationScrollView.trailingAnchor.constraint(equalTo: automationContainer.trailingAnchor),
            automationScrollView.topAnchor.constraint(equalTo: header.bottomAnchor),
            automationScrollView.bottomAnchor.constraint(equalTo: automationContainer.bottomAnchor),

            empty.leadingAnchor.constraint(equalTo: automationContainer.leadingAnchor),
            empty.trailingAnchor.constraint(equalTo: automationContainer.trailingAnchor),
            empty.topAnchor.constraint(equalTo: header.bottomAnchor),
            empty.bottomAnchor.constraint(equalTo: automationContainer.bottomAnchor)
        ])
    }

    private func assemble() {
        view.addSubview(topBar)
        view.addSubview(splitView)
        NSLayoutConstraint.activate([
            topBar.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            topBar.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            topBar.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor),

            splitView.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            splitView.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            splitView.topAnchor.constraint(equalTo: topBar.bottomAnchor),
            splitView.bottomAnchor.constraint(equalTo: view.bottomAnchor)
        ])
    }

    // MARK: Scroll views

    private func makeScrollView(for canvas: EditorCanvas, horizontal: Bool) -> NSScrollView {
        let scroll = NSScrollView()
        configure(scrollView: scroll, for: canvas, horizontal: horizontal)
        return scroll
    }

    private func configure(scrollView scroll: NSScrollView, for canvas: EditorCanvas, horizontal: Bool) {
        scroll.translatesAutoresizingMaskIntoConstraints = false
        scroll.drawsBackground = false
        scroll.borderType = .noBorder
        scroll.hasVerticalScroller = true
        scroll.hasHorizontalScroller = horizontal
        scroll.autohidesScrollers = true
        scroll.horizontalScrollElasticity = horizontal ? .allowed : .none
        scroll.contentView.drawsBackground = false
        // A scroll view's document view is positioned by the frame we assign in
        // layoutDocument(of:). A canvas that turned its autoresizing mask off
        // would have that frame ignored by Auto Layout and be laid out at its
        // own fitting size, anchored at the document origin — which in an
        // unflipped scroll view is the BOTTOM, so its header ended up off the
        // bottom of the panel and its rows were never visible.
        canvas.translatesAutoresizingMaskIntoConstraints = true
        scroll.documentView = canvas
        scroll.contentView.postsFrameChangedNotifications = true
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(clipViewFrameChanged(_:)),
            name: NSView.frameDidChangeNotification,
            object: scroll.contentView
        )
    }

    private func scrollsHorizontally(_ view: WorkView) -> Bool {
        switch view {
        case .playlist, .piano, .mixer, .sample: return true
        case .plugins, .recipe: return false
        }
    }

    private func canvas(for view: WorkView) -> EditorCanvas {
        switch view {
        case .playlist: return timelineView
        case .piano: return pianoRollView
        case .mixer: return mixerConsoleView
        case .plugins: return effectsView
        case .sample: return sampleEditorView
        case .recipe: return recipeView
        }
    }

    private func scrollView(for view: WorkView) -> NSScrollView {
        scrollViews[view] ?? automationScrollView
    }

    @objc private func clipViewFrameChanged(_ note: Notification) {
        guard let clip = note.object as? NSClipView,
              let scroll = clip.enclosingScrollView else { return }
        layoutDocument(of: scroll)
    }

    /// The single place a canvas's document size is decided, so the scroll view
    /// and the canvas can never disagree about how big the content is.
    private func layoutDocument(of scroll: NSScrollView) {
        guard !isSizingDocument else { return }
        guard let canvas = scroll.documentView as? EditorCanvas else { return }
        let visible = scroll.contentSize
        guard visible.width > 1, visible.height > 1 else { return }
        isSizingDocument = true
        defer { isSizingDocument = false }

        let wanted = canvas.contentSize(fittingVisible: visible)
        let size = NSSize(
            width: max(wanted.width, visible.width),
            height: max(wanted.height, visible.height)
        )
        if abs(canvas.frame.width - size.width) > 0.5 || abs(canvas.frame.height - size.height) > 0.5 {
            canvas.frame = NSRect(origin: .zero, size: size)
            canvas.needsDisplay = true
        }
    }

    override func viewDidLayout() {
        super.viewDidLayout()
        guard isBuilt else { return }
        placeDividerIfNeeded()
        layoutDocument(of: scrollView(for: activeWorkView))
        layoutDocument(of: automationScrollView)
    }

    // MARK: Split view

    private func placeDividerIfNeeded() {
        guard !hasPlacedDivider else { return }
        let total = splitView.bounds.height
        guard total > minimumCanvasHeight + automationHeaderHeight else { return }
        hasPlacedDivider = true
        let current = automationContainer.frame.height
        // Only impose a default when the autosaved position is missing or silly.
        guard current < automationHeaderHeight + 8 || current > total * 0.6 else {
            expandedAutomationHeight = current
            updateAutomationChrome()
            return
        }
        let wanted = min(expandedAutomationHeight, total * 0.35)
        splitView.setPosition(total - splitView.dividerThickness - wanted, ofDividerAt: 0)
        updateAutomationChrome()
    }

    private var isAutomationCollapsed: Bool {
        automationContainer.frame.height <= automationHeaderHeight + 6
    }

    private func toggleAutomationCollapsed() {
        let total = splitView.bounds.height
        guard total > 0 else { return }
        if isAutomationCollapsed {
            let wanted = max(120, min(expandedAutomationHeight, total * 0.5))
            splitView.setPosition(total - splitView.dividerThickness - wanted, ofDividerAt: 0)
            StatusCenter.shared.info("Automation strip shown.")
        } else {
            expandedAutomationHeight = automationContainer.frame.height
            splitView.setPosition(total - splitView.dividerThickness - automationHeaderHeight, ofDividerAt: 0)
            StatusCenter.shared.info("Automation strip hidden. Click Show to bring it back.")
        }
        updateAutomationChrome()
    }

    /// The one place that decides what the automation strip shows: the collapse
    /// button's wording, and which of the editor and the empty state is visible.
    private func updateAutomationChrome() {
        let collapsed = isAutomationCollapsed
        if let button = automationCollapseButton {
            button.title = collapsed ? "Show" : "Hide"
            button.image = NSImage(
                systemSymbolName: collapsed ? "chevron.up" : "chevron.down",
                accessibilityDescription: collapsed ? "Show" : "Hide"
            )
            let help = collapsed
                ? "Show the automation strip under the editor."
                : "Hide the automation strip to give the editor more room."
            button.toolTip = help
            button.setAccessibilityLabel(collapsed ? "Show automation" : "Hide automation")
            button.setAccessibilityHelp(help)
        }
        let showEditor = !collapsed && automationHasLanes
        let showEmpty = !collapsed && !automationHasLanes
        if automationScrollView.isHidden == showEditor {
            automationScrollView.isHidden = !showEditor
        }
        if let empty = automationEmptyState, empty.isHidden == showEmpty {
            empty.isHidden = !showEmpty
        }
    }

    func splitView(_ splitView: NSSplitView, constrainMinCoordinate proposedMinimumPosition: CGFloat, ofSubviewAt dividerIndex: Int) -> CGFloat {
        max(proposedMinimumPosition, minimumCanvasHeight)
    }

    func splitView(_ splitView: NSSplitView, constrainMaxCoordinate proposedMaximumPosition: CGFloat, ofSubviewAt dividerIndex: Int) -> CGFloat {
        let floorPosition = splitView.bounds.height - splitView.dividerThickness - automationHeaderHeight
        return min(proposedMaximumPosition, max(minimumCanvasHeight, floorPosition))
    }

    func splitViewDidResizeSubviews(_ notification: Notification) {
        guard isBuilt else { return }
        if !isAutomationCollapsed {
            expandedAutomationHeight = automationContainer.frame.height
        }
        updateAutomationChrome()
        layoutDocument(of: scrollView(for: activeWorkView))
        layoutDocument(of: automationScrollView)
    }

    // MARK: Actions

    @objc private func viewPickerChanged(_ sender: NSSegmentedControl) {
        let views = WorkView.allCases
        let index = sender.selectedSegment
        guard index >= 0, index < views.count else { return }
        host?.requestFocus(on: views[index])
        refresh()
    }

    @objc private func toolPickerChanged(_ sender: NSSegmentedControl) {
        let tools = ToolId.allCases
        let index = sender.selectedSegment
        guard index >= 0, index < tools.count else { return }
        if let controller = host as? DocumentWindowController {
            controller.setActiveTool(tools[index])
        }
        refresh()
    }

    private func addDefaultAutomationLanes() {
        guard let host else { return }
        guard !host.project.snapshot.tracks.isEmpty else {
            StatusCenter.shared.warning("Add a track first — automation needs something to control.")
            return
        }
        host.edit("Add Automation Lanes") { project in
            project.snapshot.automationLanes = makeDefaultAutomationLanes(for: project.snapshot.tracks)
        }
        StatusCenter.shared.success(
            "Added an automation lane for each track. Drag a point to shape it. ⌘Z undoes this."
        )
    }

    // MARK: State

    private var activeWorkView: WorkView {
        WorkView(rawValue: host?.project.snapshot.activeView ?? "") ?? .playlist
    }

    private func glossaryTerm(for view: WorkView) -> String {
        switch view {
        case .playlist: return "Bar"
        case .piano: return "Piano roll"
        case .mixer: return "Mix"
        case .plugins: return "Effect"
        case .sample: return "Sample"
        case .recipe: return "Recipe"
        }
    }

    // MARK: DocumentPane

    override func refresh() {
        guard isBuilt else { return }

        for canvas in allCanvases where canvas.host !== host {
            canvas.host = host
        }

        let active = activeWorkView
        if let index = WorkView.allCases.firstIndex(of: active), viewPicker.selectedSegment != index {
            viewPicker.selectedSegment = index
        }

        let tool = host?.activeTool ?? .select
        if let index = ToolId.allCases.firstIndex(of: tool), toolPicker.selectedSegment != index {
            toolPicker.selectedSegment = index
        }

        // Tools only mean something where you can draw or erase; showing them
        // over the mixer would just be three buttons that do nothing.
        let toolsApply = (active == .playlist || active == .piano)
        if toolPicker.isHidden == toolsApply {
            toolPicker.isHidden = !toolsApply
        }

        let explains = AppEnvironment.shared.explainsMusicTerms
        explainerLabel.stringValue = explains ? active.explanation : ""
        explainerLabel.toolTip = active.explanation
        if explainerLabel.isHidden == explains {
            explainerLabel.isHidden = !explains
        }

        canvasContainer.setAccessibilityLabel("\(active.label) editor")
        canvasContainer.setAccessibilityHelp(active.explanation)

        for (view, scroll) in scrollViews {
            let shouldShow = (view == active)
            if scroll.isHidden == shouldShow {
                scroll.isHidden = !shouldShow
            }
        }

        refreshAutomationState()

        let visible = scrollView(for: active)
        canvas(for: active).refresh()
        layoutDocument(of: visible)

        automationEditorView.refresh()
        layoutDocument(of: automationScrollView)
    }

    private func refreshAutomationState() {
        let lanes = host?.project.snapshot.automationLanes ?? []
        let hasTracks = !(host?.project.snapshot.tracks.isEmpty ?? true)
        automationHasLanes = !lanes.isEmpty

        if let empty = automationEmptyState {
            empty.isActionEnabled = hasTracks
            if hasTracks {
                empty.update(
                    title: "No automation yet",
                    body: "Automation makes a setting change over time — a fade-in, or a filter opening up. Add a lane for each track to start drawing one."
                )
            } else {
                empty.update(
                    title: "No tracks to automate",
                    body: "Add a track first. Once a song has tracks, you can make their volume or pan change over time here."
                )
            }
        }
        updateAutomationChrome()
    }

    override func playheadDidMove(to bar: Double) {
        guard isBuilt else { return }
        canvas(for: activeWorkView).playheadDidMove(to: bar)
        automationEditorView.playheadDidMove(to: bar)
    }

    // MARK: Master level

    /// Called ~30x/second while the transport runs. Only the mixer draws it, so
    /// nothing else is touched.
    func updateMasterLevel(_ level: Float) {
        mixerConsoleView.updateMasterLevel(level)
    }

    /// Real per-track peaks from the engine, forwarded to the console.
    func updateTrackLevels(_ levels: [String: Float]) {
        mixerConsoleView.updateTrackLevels(levels)
    }
}

// MARK: - Helpers

