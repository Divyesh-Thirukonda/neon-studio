import AppKit

/// One place every user-visible message goes through.
///
/// The old build wrote everything into a single tiny grey label, so an error and
/// a success looked identical and each message erased the one before it —
/// including "Save failed", which could vanish under an autosave message a
/// fraction of a second later. Now every message carries a severity, transient
/// messages fade on their own, errors do not, and nothing is lost because
/// everything is also appended to an Activity log the user can open.
public final class StatusCenter {
    public static let shared = StatusCenter()

    public enum Severity {
        case info
        case success
        case warning
        case error
        case progress

        var color: NSColor {
            switch self {
            case .info, .progress: return Theme.muted
            case .success: return Theme.success
            case .warning: return Theme.warning
            case .error: return Theme.danger
            }
        }

        var symbol: String {
            switch self {
            case .info: return "info.circle"
            case .success: return "checkmark.circle.fill"
            case .warning: return "exclamationmark.triangle.fill"
            case .error: return "xmark.octagon.fill"
            case .progress: return "clock"
            }
        }

        /// Errors and warnings stay put until something replaces them.
        var autoDismissAfter: TimeInterval? {
            switch self {
            case .success: return 4
            case .info: return 6
            case .warning, .error, .progress: return nil
            }
        }

        var logPrefix: String {
            switch self {
            case .info: return "•"
            case .success: return "✓"
            case .warning: return "!"
            case .error: return "✕"
            case .progress: return "…"
            }
        }
    }

    public struct Entry {
        public let severity: Severity
        public let message: String
        public let detail: String?
        public let date: Date
    }

    public private(set) var current: Entry?
    public private(set) var log: [Entry] = []

    /// Observers are the status bar and the Activity window.
    public var onChange: [(Entry?) -> Void] = []
    public var onLogAppended: [(Entry) -> Void] = []

    private var dismissTimer: Timer?
    private let maximumLogEntries = 500

    private init() {}

    public func post(_ severity: Severity, _ message: String, detail: String? = nil) {
        let entry = Entry(severity: severity, message: message, detail: detail, date: Date())
        current = entry
        log.append(entry)
        if log.count > maximumLogEntries {
            log.removeFirst(log.count - maximumLogEntries)
        }
        onChange.forEach { $0(entry) }
        onLogAppended.forEach { $0(entry) }

        dismissTimer?.invalidate()
        dismissTimer = nil
        if let after = severity.autoDismissAfter {
            dismissTimer = Timer.scheduledTimer(withTimeInterval: after, repeats: false) { [weak self] _ in
                guard let self, let shown = self.current, shown.date == entry.date else { return }
                self.current = nil
                self.onChange.forEach { $0(nil) }
            }
        }
    }

    public func info(_ message: String, detail: String? = nil) { post(.info, message, detail: detail) }
    public func success(_ message: String, detail: String? = nil) { post(.success, message, detail: detail) }
    public func warning(_ message: String, detail: String? = nil) { post(.warning, message, detail: detail) }
    public func progress(_ message: String) { post(.progress, message) }

    /// Errors get both a status entry and a real alert, because a message the
    /// user might miss is not an acceptable way to report a failure.
    public func failure(_ message: String, error: Error? = nil, window: NSWindow? = nil) {
        let detail = (error as? LocalizedError)?.recoverySuggestion
            ?? error?.localizedDescription
        post(.error, message, detail: detail)

        let alert = NSAlert()
        alert.alertStyle = .warning
        alert.messageText = message
        alert.informativeText = detail ?? "Open Window ▸ Activity for details."
        alert.addButton(withTitle: "OK")
        alert.addButton(withTitle: "Show Activity")
        let response: NSApplication.ModalResponse
        if let window, window.isVisible {
            // Sheets keep the failure attached to the document it came from.
            response = alert.runModal()
        } else {
            response = alert.runModal()
        }
        if response == .alertSecondButtonReturn {
            ActivityWindowController.shared.present()
        }
    }

    public func clearLog() {
        log.removeAll()
        onLogAppended.forEach { _ in }
    }

    public func logText() -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm:ss"
        return log.map { entry in
            let detail = entry.detail.map { " — \($0)" } ?? ""
            return "\(formatter.string(from: entry.date))  \(entry.severity.logPrefix)  \(entry.message)\(detail)"
        }.joined(separator: "\n")
    }
}

/// The persistent status strip at the bottom of a document window: current
/// message, a progress spinner for long work, and a shortcut into the log.
public final class StatusBarView: NSView {
    private let iconView = NSImageView()
    private let messageLabel = makeLabel("", font: Theme.Font.caption(12), color: Theme.muted)
    private let spinner = NSProgressIndicator()
    private let cancelButton: NSButton
    private let logButton: NSButton
    private var onCancel: (() -> Void)?

    public init() {
        var cancelAction: (() -> Void)?
        cancelButton = Controls.button(
            title: "Cancel",
            help: "Stop the task that's running.",
            style: .quiet,
            action: { cancelAction?() }
        )
        logButton = Controls.button(
            title: "Activity",
            symbol: "list.bullet.rectangle.portrait",
            help: "Show everything Neon Studio has done in this session.",
            style: .quiet,
            action: { ActivityWindowController.shared.present() }
        )
        super.init(frame: .zero)
        cancelAction = { [weak self] in self?.onCancel?() }

        translatesAutoresizingMaskIntoConstraints = false
        wantsLayer = true

        iconView.translatesAutoresizingMaskIntoConstraints = false
        iconView.symbolConfiguration = .init(pointSize: 11, weight: .semibold)
        iconView.setAccessibilityHidden(true)

        spinner.style = .spinning
        spinner.controlSize = .small
        spinner.isDisplayedWhenStopped = false
        spinner.translatesAutoresizingMaskIntoConstraints = false

        messageLabel.setAccessibilityRole(.staticText)
        messageLabel.setAccessibilityLabel("Status")

        cancelButton.isHidden = true

        let stack = NSStackView(views: [spinner, iconView, messageLabel, NSView(), cancelButton, logButton])
        stack.orientation = .horizontal
        stack.alignment = .centerY
        stack.spacing = 7
        stack.translatesAutoresizingMaskIntoConstraints = false
        addSubview(stack)

        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 12),
            stack.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -10),
            stack.centerYAnchor.constraint(equalTo: centerYAnchor),
            heightAnchor.constraint(equalToConstant: 28)
        ])

        StatusCenter.shared.onChange.append { [weak self] entry in
            self?.render(entry)
        }
        render(StatusCenter.shared.current)
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    /// Shows a spinner and a Cancel button for the duration of a long task.
    public func beginTask(_ message: String, cancel: (() -> Void)?) {
        onCancel = cancel
        cancelButton.isHidden = cancel == nil
        spinner.startAnimation(nil)
        StatusCenter.shared.progress(message)
    }

    public func endTask() {
        onCancel = nil
        cancelButton.isHidden = true
        spinner.stopAnimation(nil)
    }

    private func render(_ entry: StatusCenter.Entry?) {
        guard let entry else {
            messageLabel.stringValue = "Ready"
            messageLabel.textColor = Theme.dim
            iconView.image = nil
            setAccessibilityValue("Ready")
            return
        }
        messageLabel.stringValue = entry.detail.map { "\(entry.message) — \($0)" } ?? entry.message
        messageLabel.textColor = entry.severity.color
        messageLabel.toolTip = messageLabel.stringValue
        iconView.image = NSImage(systemSymbolName: entry.severity.symbol, accessibilityDescription: nil)
        iconView.contentTintColor = entry.severity.color
        setAccessibilityValue(messageLabel.stringValue)
        if entry.severity == .error || entry.severity == .warning {
            NSAccessibility.post(element: messageLabel as Any, notification: .announcementRequested)
        }
    }
}
