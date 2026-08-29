import AppKit
import QuartzCore

/// The four-step guided tour somebody sees the first time they open a project.
///
/// It is a coach-mark tour over the *real* window rather than a slideshow of
/// screenshots: the part of the app being described stays visible through a hole
/// in a dimmed scrim, so the explanation and the thing it explains are never more
/// than a few points apart. Nothing underneath is clickable while the tour runs,
/// which is deliberate — a half-finished tour plus a half-finished edit is how
/// people end up lost.
///
/// The window controller owns the region list (`tourRegions()`); this class owns
/// presentation, stepping, keyboard handling and cleanup.
final class TourController {

    static let shared = TourController()

    /// One stop on the tour: the view to spotlight and what to say about it.
    struct Region {
        let view: NSView
        let title: String
        let body: String

        init(view: NSView, title: String, body: String) {
            self.view = view
            self.title = title
            self.body = body
        }
    }

    /// Held weakly: the overlay's real owner is the window's content view, so a
    /// window that closes mid-tour cleans itself up without leaving this class
    /// convinced a tour is still running.
    private weak var overlay: TourOverlayView?
    private weak var restoreResponder: NSResponder?
    private var windowObserver: NSObjectProtocol?

    private init() {}

    /// True while a tour is on screen. A second `start` is ignored rather than
    /// stacking two scrims on top of each other.
    var isRunning: Bool { overlay != nil }

    /// - Parameters:
    ///   - force: `true` for Help ▸ Take the Tour, which replays it on demand.
    ///     `false` for the automatic first-run call, which does nothing once the
    ///     user has already been through it.
    func start(in windowController: NSWindowController, regions: [Region], force: Bool) {
        guard !regions.isEmpty else { return }
        guard !isRunning else { return }
        guard force || !AppEnvironment.shared.hasSeenTour else { return }
        guard let window = windowController.window, let contentView = window.contentView else { return }

        // Panes are laid out with Auto Layout; without this the first step can
        // spotlight a frame that hasn't settled yet.
        contentView.layoutSubtreeIfNeeded()

        let overlay = TourOverlayView(regions: regions)
        overlay.frame = contentView.bounds
        overlay.autoresizingMask = [.width, .height]
        overlay.onEnd = { [weak self] in self?.end() }
        contentView.addSubview(overlay, positioned: .above, relativeTo: nil)

        self.overlay = overlay
        restoreResponder = window.firstResponder
        window.makeFirstResponder(overlay)
        overlay.begin()

        windowObserver = NotificationCenter.default.addObserver(
            forName: NSWindow.willCloseNotification,
            object: window,
            queue: .main
        ) { [weak self] _ in
            // The window is going away with the tour unfinished. Tear down
            // quietly and don't mark it as seen — they never got to see it.
            self?.dismissOverlay()
        }
    }

    /// Finishing and skipping are the same outcome: the user is done with the
    /// tour, and they are told how to get it back.
    private func end() {
        guard isRunning else { return }
        dismissOverlay()
        AppEnvironment.shared.hasSeenTour = true
        StatusCenter.shared.info("You can replay this any time from Help ▸ Take the Tour.")
    }

    private func dismissOverlay() {
        if let observer = windowObserver {
            NotificationCenter.default.removeObserver(observer)
            windowObserver = nil
        }
        guard let overlay else { return }
        let window = overlay.window
        overlay.removeFromSuperview()
        self.overlay = nil
        if let responder = restoreResponder, let window, window.isVisible {
            window.makeFirstResponder(responder)
        }
        restoreResponder = nil
    }
}

// MARK: - Overlay

/// The scrim, the hole, and the callout. Everything about where things are drawn
/// comes from `highlightRect(for:)` and `calloutFrame(highlight:size:)`, which are
/// the only two places geometry is computed — drawing, hit blocking and card
/// placement all read from them.
private final class TourOverlayView: NSView {

    private enum Metric {
        /// Breathing room between the spotlighted view and the edge of the hole.
        static let highlightPadding: CGFloat = 6
        static let highlightRadius: CGFloat = Theme.Metric.cornerRadius + 2
        /// Distance from the hole to the callout card.
        static let calloutGap: CGFloat = 14
        /// Distance the card keeps from the window edge.
        static let edgeMargin: CGFloat = 18
        static let stepDuration: TimeInterval = 0.18
    }

    private let regions: [TourController.Region]
    private let callout = TourCalloutView()
    private var index = 0
    private var isConfigured = false

    /// Called once, whether the user finished or skipped.
    var onEnd: (() -> Void)?

    /// Animated through `animator()` so the hole slides between steps. Declared
    /// `@objc dynamic` because that is what makes it drivable by
    /// `NSAnimationContext`; see `animation(forKey:)` below.
    @objc dynamic var animatedHighlight: NSRect = .zero {
        didSet { needsDisplay = true }
    }

    init(regions: [TourController.Region]) {
        self.regions = regions
        super.init(frame: .zero)

        callout.onBack = { [weak self] in self?.goBack() }
        callout.onNext = { [weak self] in self?.advance() }
        callout.onSkip = { [weak self] in self?.onEnd?() }
        addSubview(callout)

        setAccessibilityRole(.group)
        setAccessibilityLabel("Guided tour")
        setAccessibilityHelp("A short walkthrough of the window. Press Return for the next step, or Escape to close the tour.")
        toolTip = "Guided tour — click anywhere to continue, or press Escape to close it."
        isConfigured = true
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    // MARK: Stepping

    func begin() {
        show(step: 0, animated: false)
    }

    private func advance() {
        if index + 1 < regions.count {
            show(step: index + 1, animated: true)
        } else {
            onEnd?()
        }
    }

    private func goBack() {
        guard index > 0 else { return }
        show(step: index - 1, animated: true)
    }

    private func show(step: Int, animated: Bool) {
        guard step >= 0, step < regions.count else { return }
        index = step
        let region = regions[step]
        callout.configure(
            step: step + 1,
            of: regions.count,
            title: region.title,
            body: region.body,
            showsBack: step > 0,
            isLastStep: step == regions.count - 1
        )
        layoutForCurrentStep(animated: animated)
        window?.makeFirstResponder(self)
        announce(region)
    }

    private func announce(_ region: TourController.Region) {
        let text = "Step \(index + 1) of \(regions.count). \(region.title). \(region.body)"
        NSAccessibility.post(
            element: callout,
            notification: .announcementRequested,
            userInfo: [
                .announcement: text,
                .priority: NSAccessibilityPriorityLevel.high.rawValue
            ]
        )
    }

    // MARK: Geometry — the single source of truth

    /// The hole, in overlay coordinates. `NSRect.zero` means "no usable frame for
    /// this region", in which case the scrim is drawn solid and the card centres.
    private func highlightRect(for region: TourController.Region) -> NSRect {
        guard region.view.window === window, region.view.superview != nil else { return .zero }
        let converted = region.view.convert(region.view.bounds, to: self)
        let padded = converted.insetBy(dx: -Metric.highlightPadding, dy: -Metric.highlightPadding)
        let visible = padded.intersection(bounds)
        guard visible.width > 4, visible.height > 4 else { return .zero }
        return visible
    }

    private func hasHighlight(_ rect: NSRect) -> Bool {
        rect.width > 4 && rect.height > 4
    }

    /// Picks the side of the hole with room for the card, and never lets the card
    /// leave the window.
    private func calloutFrame(highlight: NSRect, size: NSSize) -> NSRect {
        let available = bounds.insetBy(dx: Metric.edgeMargin, dy: Metric.edgeMargin)
        func clampX(_ x: CGFloat) -> CGFloat {
            let upper = max(available.minX, available.maxX - size.width)
            return min(max(x, available.minX), upper)
        }
        func clampY(_ y: CGFloat) -> CGFloat {
            let upper = max(available.minY, available.maxY - size.height)
            return min(max(y, available.minY), upper)
        }
        func centred() -> NSRect {
            NSRect(
                x: clampX(bounds.midX - size.width / 2),
                y: clampY(bounds.midY - size.height / 2),
                width: size.width,
                height: size.height
            )
        }
        guard hasHighlight(highlight) else { return centred() }

        let alignedY = clampY(highlight.midY - size.height / 2)
        let alignedX = clampX(highlight.midX - size.width / 2)

        let toTheRight = highlight.maxX + Metric.calloutGap
        if toTheRight + size.width <= available.maxX {
            return NSRect(x: toTheRight, y: alignedY, width: size.width, height: size.height)
        }
        let toTheLeft = highlight.minX - Metric.calloutGap - size.width
        if toTheLeft >= available.minX {
            return NSRect(x: toTheLeft, y: alignedY, width: size.width, height: size.height)
        }
        // Below, in screen terms — this view is not flipped, so that is a lower y.
        let below = highlight.minY - Metric.calloutGap - size.height
        if below >= available.minY {
            return NSRect(x: alignedX, y: below, width: size.width, height: size.height)
        }
        let above = highlight.maxY + Metric.calloutGap
        if above + size.height <= available.maxY {
            return NSRect(x: alignedX, y: above, width: size.width, height: size.height)
        }
        return centred()
    }

    private func layoutForCurrentStep(animated: Bool) {
        guard isConfigured, index < regions.count else { return }
        let target = highlightRect(for: regions[index])
        callout.frame = calloutFrame(highlight: target, size: callout.preferredSize())

        if animated && !Theme.prefersReducedMotion {
            NSAnimationContext.runAnimationGroup { context in
                context.duration = Metric.stepDuration
                context.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
                animator().animatedHighlight = target
            }
        } else {
            animatedHighlight = target
        }
    }

    /// Lets `animator().animatedHighlight = …` interpolate a rect that is drawn by
    /// hand rather than backed by a layer property.
    override func animation(forKey key: NSAnimatablePropertyKey) -> Any? {
        if key == "animatedHighlight" {
            let animation = CABasicAnimation()
            animation.duration = Metric.stepDuration
            animation.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
            return animation
        }
        return super.animation(forKey: key)
    }

    override func setFrameSize(_ newSize: NSSize) {
        super.setFrameSize(newSize)
        // The window resized behind the tour; re-spotlight without animating, so
        // the hole tracks the pane instead of lagging behind it.
        layoutForCurrentStep(animated: false)
    }

    // MARK: Drawing

    override var isOpaque: Bool { false }

    override func draw(_ dirtyRect: NSRect) {
        let highlight = animatedHighlight
        let cutOut = hasHighlight(highlight)

        let scrim = NSBezierPath(rect: bounds)
        if cutOut {
            scrim.append(NSBezierPath(
                roundedRect: highlight,
                xRadius: Metric.highlightRadius,
                yRadius: Metric.highlightRadius
            ))
            scrim.windingRule = .evenOdd
        }
        NSColor.black.withAlphaComponent(0.55).setFill()
        scrim.fill()

        guard cutOut else { return }
        roundedStroke(
            highlight.insetBy(dx: -3, dy: -3),
            radius: Metric.highlightRadius + 3,
            color: Theme.accent.withAlphaComponent(0.35),
            width: 3
        )
        roundedStroke(highlight, radius: Metric.highlightRadius, color: Theme.accent, width: 2)
    }

    // MARK: Input

    override var acceptsFirstResponder: Bool { true }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }

    override func resetCursorRects() {
        // Clicking the scrim moves the tour on, so say so with the cursor.
        addCursorRect(bounds, cursor: .pointingHand)
    }

    // Every mouse path is swallowed: while the tour is up, the window behind it
    // is a picture, not a control panel.
    override func mouseDown(with event: NSEvent) { advance() }
    override func mouseUp(with event: NSEvent) {}
    override func mouseDragged(with event: NSEvent) {}
    override func rightMouseDown(with event: NSEvent) {}
    override func rightMouseUp(with event: NSEvent) {}
    override func otherMouseDown(with event: NSEvent) {}
    override func otherMouseUp(with event: NSEvent) {}
    override func scrollWheel(with event: NSEvent) {}
    override func menu(for event: NSEvent) -> NSMenu? { nil }

    private enum KeyAction { case advance, back, end, ignore }

    private func keyAction(for event: NSEvent) -> KeyAction {
        switch event.keyCode {
        case 53: return .end                 // Escape
        case 36, 76: return .advance         // Return, Enter
        case 49: return .advance             // Space
        case 124: return .advance            // Right arrow
        case 123: return .back               // Left arrow
        default: return .ignore
        }
    }

    private func perform(_ action: KeyAction) -> Bool {
        switch action {
        case .advance: advance(); return true
        case .back: goBack(); return true
        case .end: onEnd?(); return true
        case .ignore: return false
        }
    }

    override func keyDown(with event: NSEvent) {
        if perform(keyAction(for: event)) { return }
        super.keyDown(with: event)
    }

    /// Return and Escape are also claimed here, so a default button elsewhere in
    /// the window can't steal them out from under the tour. Space and the arrow
    /// keys are deliberately *not* claimed at this stage — they stay available to
    /// whichever tour button has keyboard focus.
    override func performKeyEquivalent(with event: NSEvent) -> Bool {
        guard window != nil, superview != nil else { return false }
        switch keyAction(for: event) {
        case .advance where event.keyCode == 36 || event.keyCode == 76:
            return perform(.advance)
        case .end:
            return perform(.end)
        default:
            return false
        }
    }
}

// MARK: - Callout card

/// The floating explanation: step counter, title, body, and the three things the
/// user can do about it.
private final class TourCalloutView: NSView {

    private enum Metric {
        static let contentWidth: CGFloat = 300
        static let padding: CGFloat = 16
    }

    var onBack: (() -> Void)?
    var onNext: (() -> Void)?
    var onSkip: (() -> Void)?

    private let stepLabel = makeLabel("", font: Theme.Font.captionBold(11), color: Theme.accent)
    private let titleLabel = makeLabel("", font: Theme.Font.title(15), color: Theme.text)
    private let bodyLabel = makeLabel("", font: Theme.Font.body(13), color: Theme.muted)
    private let hintLabel = makeLabel(
        "Return moves on. Escape closes the tour.",
        font: Theme.Font.caption(11),
        color: Theme.dim
    )
    private let backButton: NSButton
    private let nextButton: NSButton
    private let skipButton: NSButton
    private let stack = NSStackView()

    init() {
        var back: (() -> Void)?
        var next: (() -> Void)?
        var skip: (() -> Void)?
        backButton = Controls.button(
            title: "Back",
            help: "Go back to the previous step of the tour.",
            action: { back?() }
        )
        nextButton = Controls.button(
            title: "Next",
            help: "Show the next step of the tour.",
            style: .primary,
            action: { next?() }
        )
        skipButton = Controls.button(
            title: "Skip tour",
            help: "Close the tour now. You can start it again from Help ▸ Take the Tour.",
            style: .quiet,
            action: { skip?() }
        )
        super.init(frame: .zero)
        back = { [weak self] in self?.onBack?() }
        next = { [weak self] in self?.onNext?() }
        skip = { [weak self] in self?.onSkip?() }

        wantsLayer = true
        layer?.cornerRadius = Theme.Metric.cornerRadius
        layer?.borderWidth = 1
        layer?.shadowColor = NSColor.black.cgColor
        layer?.shadowOpacity = 0.35
        layer?.shadowRadius = 16
        layer?.shadowOffset = CGSize(width: 0, height: -5)

        for label in [titleLabel, bodyLabel, hintLabel] {
            label.lineBreakMode = .byWordWrapping
            label.maximumNumberOfLines = 0
            label.preferredMaxLayoutWidth = Metric.contentWidth
        }

        let buttons = NSStackView(views: [skipButton, NSView(), backButton, nextButton])
        buttons.orientation = .horizontal
        buttons.alignment = .centerY
        buttons.spacing = 8
        buttons.translatesAutoresizingMaskIntoConstraints = false
        // The empty view is the flexible gap that pushes Back / Next right.
        buttons.views[1].setContentHuggingPriority(.init(1), for: .horizontal)

        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 6
        stack.translatesAutoresizingMaskIntoConstraints = false
        stack.addArrangedSubview(stepLabel)
        stack.addArrangedSubview(titleLabel)
        stack.addArrangedSubview(bodyLabel)
        stack.addArrangedSubview(hintLabel)
        stack.addArrangedSubview(buttons)
        stack.setCustomSpacing(10, after: bodyLabel)
        stack.setCustomSpacing(12, after: hintLabel)
        addSubview(stack)

        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: leadingAnchor, constant: Metric.padding),
            stack.topAnchor.constraint(equalTo: topAnchor, constant: Metric.padding),
            stack.widthAnchor.constraint(equalToConstant: Metric.contentWidth),
            stack.bottomAnchor.constraint(lessThanOrEqualTo: bottomAnchor, constant: -Metric.padding),
            buttons.widthAnchor.constraint(equalTo: stack.widthAnchor)
        ])

        setAccessibilityRole(.group)
        setAccessibilityLabel("Tour step")
        refreshColors()
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    func configure(step: Int, of total: Int, title: String, body: String, showsBack: Bool, isLastStep: Bool) {
        stepLabel.stringValue = "STEP \(step) OF \(total)"
        stepLabel.setAccessibilityLabel("Step \(step) of \(total)")
        titleLabel.stringValue = title
        bodyLabel.stringValue = body
        backButton.isHidden = !showsBack

        let nextTitle = isLastStep ? "Done" : "Next"
        let nextHelp = isLastStep
            ? "Close the tour and start working on the song."
            : "Show the next step of the tour."
        nextButton.title = nextTitle
        nextButton.toolTip = nextHelp
        nextButton.setAccessibilityLabel(nextTitle)
        nextButton.setAccessibilityHelp(nextHelp)

        setAccessibilityLabel("Tour step \(step) of \(total): \(title)")
        setAccessibilityHelp(body)
        toolTip = body
        needsLayout = true
        layoutSubtreeIfNeeded()
    }

    /// The size the card needs for its current text. Used by the overlay to place
    /// it — the card is positioned by frame, and lays its own contents out with
    /// Auto Layout inside that frame.
    func preferredSize() -> NSSize {
        layoutSubtreeIfNeeded()
        let height = stack.fittingSize.height + Metric.padding * 2
        return NSSize(
            width: Metric.contentWidth + Metric.padding * 2,
            height: ceil(max(height, 96))
        )
    }

    // The card is not the scrim: clicking its background must not advance the
    // tour, only its buttons act.
    override func mouseDown(with event: NSEvent) {}
    override func mouseUp(with event: NSEvent) {}
    override func rightMouseDown(with event: NSEvent) {}

    override func resetCursorRects() {
        addCursorRect(bounds, cursor: .arrow)
    }

    override func viewDidChangeEffectiveAppearance() {
        super.viewDidChangeEffectiveAppearance()
        refreshColors()
    }

    private func refreshColors() {
        effectiveAppearance.performAsCurrentDrawingAppearance {
            layer?.backgroundColor = Theme.panel.cgColor
            layer?.borderColor = Theme.stroke.cgColor
        }
    }
}
