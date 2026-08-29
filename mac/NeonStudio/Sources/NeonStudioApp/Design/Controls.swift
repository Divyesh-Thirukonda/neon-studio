import AppKit

/// The app's control vocabulary.
///
/// These are thin factories over *standard* AppKit controls rather than custom
/// drawn ones. That is deliberate: standard controls come with hover, pressed,
/// disabled and focus-ring states, keyboard operability, and VoiceOver support
/// already correct. The previous build hand-drew every button, so none of that
/// worked and nothing on screen looked clickable.
public enum Controls {

    public enum Style {
        /// The one obvious action in a context.
        case primary
        /// Everything else.
        case standard
        /// Low-emphasis, sits inside a dense toolbar.
        case quiet
        /// Deletes or discards something.
        case destructive
    }

    /// - Parameters:
    ///   - help: shown as a tooltip and read by VoiceOver. Required — a control
    ///     nobody can explain in one sentence usually shouldn't exist.
    @discardableResult
    public static func button(
        title: String,
        symbol: String? = nil,
        help: String,
        style: Style = .standard,
        keyEquivalent: String = "",
        keyEquivalentModifiers: NSEvent.ModifierFlags = [.command],
        action: @escaping () -> Void
    ) -> NSButton {
        let button = ActionButton(title: title, target: nil, action: nil)
        button.handler = action
        button.target = button
        button.action = #selector(ActionButton.invoke)
        button.bezelStyle = .rounded
        button.controlSize = .regular
        button.toolTip = help
        button.setAccessibilityLabel(title)
        button.setAccessibilityHelp(help)
        button.translatesAutoresizingMaskIntoConstraints = false
        if !keyEquivalent.isEmpty {
            button.keyEquivalent = keyEquivalent
            button.keyEquivalentModifierMask = keyEquivalentModifiers
        }
        if let symbol, let image = NSImage(systemSymbolName: symbol, accessibilityDescription: title) {
            button.image = image
            button.imagePosition = title.isEmpty ? .imageOnly : .imageLeading
            button.imageScaling = .scaleProportionallyDown
        }
        apply(style: style, to: button)
        return button
    }

    /// A button that stays visibly pressed while its state is on. Used for the
    /// tool picker and for mute / solo / record-arm, where the old build gave no
    /// indication at all of which option was active.
    @discardableResult
    public static func toggle(
        title: String,
        symbol: String? = nil,
        help: String,
        isOn: Bool = false,
        style: Style = .standard,
        action: @escaping (Bool) -> Void
    ) -> NSButton {
        let button = ToggleButton(title: title, target: nil, action: nil)
        button.toggleHandler = action
        button.target = button
        button.action = #selector(ToggleButton.invoke)
        button.setButtonType(.pushOnPushOff)
        button.bezelStyle = .rounded
        button.state = isOn ? .on : .off
        button.toolTip = help
        button.setAccessibilityLabel(title)
        button.setAccessibilityHelp(help)
        button.translatesAutoresizingMaskIntoConstraints = false
        if let symbol, let image = NSImage(systemSymbolName: symbol, accessibilityDescription: title) {
            button.image = image
            button.imagePosition = title.isEmpty ? .imageOnly : .imageLeading
        }
        apply(style: style, to: button)
        return button
    }

    /// Style only. Making a primary button the *default* button is a separate
    /// decision the caller makes with `makeDefault(_:)`, because a window may
    /// contain several emphasised buttons but only one may answer Return.
    private static func apply(style: Style, to button: NSButton) {
        switch style {
        case .primary:
            button.bezelColor = Theme.accent
        case .standard:
            break
        case .quiet:
            button.bezelStyle = .accessoryBarAction
            button.controlSize = .small
        case .destructive:
            button.contentTintColor = Theme.danger
        }
    }

    /// Marks a button as the one Return activates. Use at most once per window.
    @discardableResult
    public static func makeDefault(_ button: NSButton) -> NSButton {
        button.keyEquivalent = "\r"
        return button
    }

    /// A labelled row for a form. Keeps label and control aligned everywhere.
    public static func formRow(_ label: String, _ control: NSView, help: String? = nil, labelWidth: CGFloat = 150) -> NSStackView {
        let title = makeLabel(label, font: Theme.Font.body(), color: Theme.muted)
        title.alignment = .right
        title.widthAnchor.constraint(equalToConstant: labelWidth).isActive = true
        title.setContentCompressionResistancePriority(.required, for: .horizontal)
        if let help {
            title.toolTip = help
            control.toolTip = help
        }
        control.translatesAutoresizingMaskIntoConstraints = false
        let row = NSStackView(views: [title, control])
        row.orientation = .horizontal
        row.spacing = 10
        row.alignment = .firstBaseline
        row.translatesAutoresizingMaskIntoConstraints = false
        return row
    }

    public static func slider(
        value: Double,
        min minValue: Double,
        max maxValue: Double,
        help: String,
        accessibilityLabel: String,
        vertical: Bool = false,
        action: @escaping (Double) -> Void
    ) -> NSSlider {
        let slider = ValueSlider(value: value, minValue: minValue, maxValue: maxValue, target: nil, action: nil)
        slider.handler = action
        slider.target = slider
        slider.action = #selector(ValueSlider.invoke)
        slider.isContinuous = true
        slider.isVertical = vertical
        slider.controlSize = .small
        slider.toolTip = help
        slider.setAccessibilityLabel(accessibilityLabel)
        slider.setAccessibilityHelp(help)
        slider.translatesAutoresizingMaskIntoConstraints = false
        return slider
    }

    public static func popUp(
        titles: [String],
        selected: Int,
        help: String,
        accessibilityLabel: String,
        action: @escaping (Int) -> Void
    ) -> NSPopUpButton {
        let popUp = MenuPopUpButton(frame: .zero, pullsDown: false)
        popUp.handler = action
        popUp.addItems(withTitles: titles)
        if selected >= 0, selected < titles.count {
            popUp.selectItem(at: selected)
        }
        popUp.target = popUp
        popUp.action = #selector(MenuPopUpButton.invoke)
        popUp.controlSize = .small
        popUp.font = Theme.Font.caption()
        popUp.toolTip = help
        popUp.setAccessibilityLabel(accessibilityLabel)
        popUp.setAccessibilityHelp(help)
        popUp.translatesAutoresizingMaskIntoConstraints = false
        return popUp
    }

    public static func numberField(
        value: String,
        placeholder: String,
        help: String,
        accessibilityLabel: String,
        width: CGFloat = 72,
        action: @escaping (String) -> Void
    ) -> NSTextField {
        let field = CommitTextField(string: value)
        field.commitHandler = action
        field.placeholderString = placeholder
        field.alignment = .right
        field.font = Theme.Font.mono(12)
        field.controlSize = .small
        field.toolTip = help
        field.setAccessibilityLabel(accessibilityLabel)
        field.setAccessibilityHelp(help)
        field.translatesAutoresizingMaskIntoConstraints = false
        field.widthAnchor.constraint(equalToConstant: width).isActive = true
        return field
    }

    /// A small "?" that reveals a plain-language explanation of a music term.
    /// This is how the app stays usable for someone who has never opened a DAW.
    public static func glossary(_ term: String, _ explanation: String) -> NSButton {
        let button = ActionButton(title: "", target: nil, action: nil)
        button.handler = {
            let alert = NSAlert()
            alert.messageText = term
            alert.informativeText = explanation
            alert.addButton(withTitle: "Got it")
            alert.runModal()
        }
        button.target = button
        button.action = #selector(ActionButton.invoke)
        button.bezelStyle = .helpButton
        button.title = ""
        button.toolTip = "\(term): \(explanation)"
        button.setAccessibilityLabel("What is \(term)?")
        button.setAccessibilityHelp(explanation)
        button.translatesAutoresizingMaskIntoConstraints = false
        return button
    }

    public static func separator(vertical: Bool = true) -> NSBox {
        let box = NSBox()
        box.boxType = .separator
        box.translatesAutoresizingMaskIntoConstraints = false
        if vertical {
            box.widthAnchor.constraint(equalToConstant: 1).isActive = true
        } else {
            box.heightAnchor.constraint(equalToConstant: 1).isActive = true
        }
        return box
    }
}

// MARK: - Closure-backed control subclasses

public final class ActionButton: NSButton {
    public var handler: (() -> Void)?
    @objc func invoke() { handler?() }
}

public final class ToggleButton: NSButton {
    public var toggleHandler: ((Bool) -> Void)?
    @objc func invoke() { toggleHandler?(state == .on) }
}

public final class ValueSlider: NSSlider {
    public var handler: ((Double) -> Void)?
    @objc func invoke() { handler?(doubleValue) }
}

public final class MenuPopUpButton: NSPopUpButton {
    public var handler: ((Int) -> Void)?
    @objc func invoke() { handler?(indexOfSelectedItem) }
}

/// A text field that reports its value when the user commits it (Return or
/// focus loss) rather than on every keystroke.
public final class CommitTextField: NSTextField, NSTextFieldDelegate {
    public var commitHandler: ((String) -> Void)?

    public override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        commonInit()
    }

    public convenience init(string: String) {
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

    public func controlTextDidEndEditing(_ obj: Notification) {
        commitHandler?(stringValue)
    }
}

// MARK: - Panel chrome

/// A titled container. Uses a real `NSVisualEffectView` behind panel content so
/// it matches the rest of macOS instead of a flat hardcoded fill.
public final class PanelView: NSView {
    public let contentView = NSView()
    private let titleLabel: NSTextField
    private let accessoryContainer = NSStackView()

    public init(title: String, help: String? = nil) {
        titleLabel = makeLabel(title.uppercased(), font: Theme.Font.captionBold(11), color: Theme.muted)
        super.init(frame: .zero)
        translatesAutoresizingMaskIntoConstraints = false
        wantsLayer = true
        layer?.cornerRadius = Theme.Metric.cornerRadius
        layer?.borderWidth = 1
        contentView.translatesAutoresizingMaskIntoConstraints = false
        accessoryContainer.orientation = .horizontal
        accessoryContainer.spacing = 6
        accessoryContainer.alignment = .centerY
        accessoryContainer.translatesAutoresizingMaskIntoConstraints = false

        setAccessibilityRole(.group)
        setAccessibilityLabel(title)
        if let help {
            toolTip = help
            titleLabel.toolTip = help
            setAccessibilityHelp(help)
        }

        addSubview(titleLabel)
        addSubview(accessoryContainer)
        addSubview(contentView)

        NSLayoutConstraint.activate([
            titleLabel.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 12),
            titleLabel.topAnchor.constraint(equalTo: topAnchor, constant: 9),

            accessoryContainer.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -8),
            accessoryContainer.centerYAnchor.constraint(equalTo: titleLabel.centerYAnchor),
            accessoryContainer.leadingAnchor.constraint(greaterThanOrEqualTo: titleLabel.trailingAnchor, constant: 8),

            contentView.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 1),
            contentView.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -1),
            contentView.topAnchor.constraint(equalTo: titleLabel.bottomAnchor, constant: 8),
            contentView.bottomAnchor.constraint(equalTo: bottomAnchor, constant: -1)
        ])
        refreshColors()
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    public func addAccessory(_ view: NSView) {
        accessoryContainer.addArrangedSubview(view)
    }

    public var title: String {
        get { titleLabel.stringValue }
        set {
            titleLabel.stringValue = newValue.uppercased()
            setAccessibilityLabel(newValue)
        }
    }

    public override func viewDidChangeEffectiveAppearance() {
        super.viewDidChangeEffectiveAppearance()
        refreshColors()
    }

    private func refreshColors() {
        effectiveAppearance.performAsCurrentDrawingAppearance {
            layer?.backgroundColor = Theme.panel.cgColor
            layer?.borderColor = Theme.subtleStroke.cgColor
        }
    }
}

/// The message shown when a panel has nothing in it yet — always with the exact
/// next step, never a bare "No items".
public final class EmptyStateView: NSView {
    private let stack = NSStackView()
    private let iconView = NSImageView()
    private let titleLabel: NSTextField
    private let bodyLabel: NSTextField
    private var actionButton: NSButton?

    public init(symbol: String, title: String, body: String, actionTitle: String? = nil, action: (() -> Void)? = nil) {
        titleLabel = makeLabel(title, font: Theme.Font.emphasis(13), color: Theme.text)
        bodyLabel = makeLabel(body, font: Theme.Font.body(12), color: Theme.muted)
        super.init(frame: .zero)
        translatesAutoresizingMaskIntoConstraints = false

        iconView.image = NSImage(systemSymbolName: symbol, accessibilityDescription: nil)
        iconView.symbolConfiguration = .init(pointSize: 26, weight: .regular)
        iconView.contentTintColor = Theme.dim
        iconView.translatesAutoresizingMaskIntoConstraints = false

        titleLabel.alignment = .center
        bodyLabel.alignment = .center
        bodyLabel.lineBreakMode = .byWordWrapping
        bodyLabel.maximumNumberOfLines = 4
        bodyLabel.preferredMaxLayoutWidth = 300

        stack.orientation = .vertical
        stack.alignment = .centerX
        stack.spacing = 8
        stack.translatesAutoresizingMaskIntoConstraints = false
        stack.addArrangedSubview(iconView)
        stack.addArrangedSubview(titleLabel)
        stack.addArrangedSubview(bodyLabel)

        if let actionTitle, let action {
            let button = Controls.button(
                title: actionTitle,
                help: body,
                style: .primary,
                action: action
            )
            stack.addArrangedSubview(button)
            stack.setCustomSpacing(14, after: bodyLabel)
            actionButton = button
        }

        addSubview(stack)
        NSLayoutConstraint.activate([
            stack.centerXAnchor.constraint(equalTo: centerXAnchor),
            stack.centerYAnchor.constraint(equalTo: centerYAnchor),
            stack.leadingAnchor.constraint(greaterThanOrEqualTo: leadingAnchor, constant: 20),
            stack.trailingAnchor.constraint(lessThanOrEqualTo: trailingAnchor, constant: -20),
            stack.widthAnchor.constraint(lessThanOrEqualToConstant: 340)
        ])

        setAccessibilityRole(.group)
        setAccessibilityLabel(title)
        setAccessibilityHelp(body)
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    public func update(title: String, body: String) {
        titleLabel.stringValue = title
        bodyLabel.stringValue = body
        setAccessibilityLabel(title)
        setAccessibilityHelp(body)
    }

    public var isActionEnabled: Bool {
        get { actionButton?.isEnabled ?? false }
        set { actionButton?.isEnabled = newValue }
    }
}
