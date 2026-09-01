import AppKit

/// The document window, with the single-key transport shortcuts a DAW needs.
///
/// Space and Return have to be caught before the focused control sees them —
/// an `NSTableView` consumes Space for type-select, so a plain `keyDown` on the
/// window controller never runs while the track list has focus. But they must
/// NOT be caught while somebody is typing. That is the exact trap the previous
/// build fell into: it used an app-wide `NSEvent` monitor that swallowed Space
/// and Backspace everywhere, so you could not put a space in a project name and
/// pressing Backspace to fix a typo deleted a track from the song instead.
///
/// The rule here is narrow and checkable: handle the key only when nothing is
/// being edited, only when no modifier is held, and only after AppKit has had
/// its chance at menu key equivalents.
final class DocumentWindow: NSWindow {

    /// Return true to consume the key.
    var onTransportKey: ((TransportKey) -> Bool)?

    enum TransportKey {
        case playPause
        case goToStart
        case selectTool
        case drawTool
        case eraseTool
    }

    override func performKeyEquivalent(with event: NSEvent) -> Bool {
        if super.performKeyEquivalent(with: event) { return true }

        let modifiers = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
        guard modifiers.isEmpty else { return false }
        guard !isEditingText else { return false }

        switch event.keyCode {
        case 49: // Space
            return onTransportKey?(.playPause) ?? false
        case 36, 76: // Return, Enter
            return onTransportKey?(.goToStart) ?? false
        default:
            break
        }

        // Letter shortcuts stay clear of anything that uses typing itself —
        // a table's type-select is a real feature and should keep working.
        guard !firstResponderUsesTypeSelect else { return false }
        switch event.charactersIgnoringModifiers?.lowercased() {
        case "v": return onTransportKey?(.selectTool) ?? false
        case "b": return onTransportKey?(.drawTool) ?? false
        case "e": return onTransportKey?(.eraseTool) ?? false
        default: return false
        }
    }

    /// True while a field editor or any other text view has focus.
    private var isEditingText: Bool {
        guard let responder = firstResponder else { return false }
        if responder is NSText { return true }
        if let view = responder as? NSView, view.isKind(of: NSTextView.self) { return true }
        if responder is NSTextField { return true }
        return false
    }

    private var firstResponderUsesTypeSelect: Bool {
        guard let responder = firstResponder else { return false }
        return responder is NSTableView || responder is NSOutlineView
    }
}
