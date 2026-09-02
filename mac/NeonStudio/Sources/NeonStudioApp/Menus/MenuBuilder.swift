import AppKit
import NeonStudioKit

/// Builds the whole main menu bar.
///
/// The previous menu bar was missing nearly everything a Mac user expects: no
/// About, no Settings, no Services, no Hide/Show All, no Window menu, and an
/// Edit menu holding only Undo/Redo/Delete — so ⌘C and ⌘V did nothing anywhere
/// in the app, including inside its own text fields. It also bound bare
/// Backspace as a menu key equivalent, which fired while the user was typing,
/// and hijacked ⌘H away from Hide.
///
/// Two rules keep this file honest:
///
/// 1. **Nothing here hardcodes a target.** Every item that a document window
///    handles, and every standard AppKit action, is left with `target = nil` so
///    it travels the responder chain. That is what makes items grey out on
///    their own — `DocumentWindowController` implements `NSMenuItemValidation`
///    and gets consulted for each one.
/// 2. **No key equivalent is used twice.** The full list is written out in
///    `shortcutAudit()` at the bottom of the file so a new item can be checked
///    against it without reading the whole builder.
///
/// Shortcuts that would fire while typing (Space, "v", "b", "e", Backspace) are
/// deliberately *not* menu key equivalents. The canvases handle those keys
/// themselves through the responder chain, where a focused text field wins.
final class MenuBuilder: NSObject {

    static let shared = MenuBuilder()

    private override init() { super.init() }

    // MARK: Retained menus and windows
    //
    // `NSApp` retains the main menu, but the submenus assigned to
    // `servicesMenu` / `windowsMenu` / `helpMenu` and the lazily built glossary
    // window are kept here so nothing is deallocated out from under AppKit.

    private var mainMenu: NSMenu?
    private var servicesMenu: NSMenu?
    private var recentDocumentsMenu: NSMenu?
    private var glossaryWindowController: NSWindowController?

    // MARK: Items whose title or checkmark depends on the front window

    private var playItem: NSMenuItem?
    private var loopItem: NSMenuItem?
    private var toolItems: [ToolId: NSMenuItem] = [:]
    private var viewItems: [WorkView: NSMenuItem] = [:]

    private var appName: String {
        if let name = Bundle.main.object(forInfoDictionaryKey: "CFBundleDisplayName") as? String,
           !name.isEmpty {
            return name
        }
        if let name = Bundle.main.object(forInfoDictionaryKey: "CFBundleName") as? String,
           !name.isEmpty {
            return name
        }
        return "Neon Studio"
    }

    // MARK: - Install

    /// Replaces `NSApp.mainMenu` with a freshly built bar. Safe to call twice.
    func install() {
        toolItems.removeAll()
        viewItems.removeAll()

        let bar = NSMenu()
        bar.addItem(submenu(applicationMenu(), titled: appName))
        bar.addItem(submenu(fileMenu(), titled: "File"))
        bar.addItem(submenu(editMenu(), titled: "Edit"))
        bar.addItem(submenu(trackMenu(), titled: "Track"))
        bar.addItem(submenu(viewMenu(), titled: "View"))
        bar.addItem(submenu(transportMenu(), titled: "Transport"))
        bar.addItem(submenu(toolsMenu(), titled: "Tools"))

        let window = windowMenu()
        bar.addItem(submenu(window, titled: "Window"))

        let help = helpMenu()
        bar.addItem(submenu(help, titled: "Help"))

        mainMenu = bar
        NSApp.mainMenu = bar
        // Assigned after the menus are in the bar so AppKit adds its own
        // entries (the window list, the Help search field) in the right place.
        NSApp.windowsMenu = window
        NSApp.helpMenu = help
    }

    // MARK: - Application menu

    private func applicationMenu() -> NSMenu {
        let menu = NSMenu()

        add("About \(appName)", to: menu,
            action: selector("orderFrontStandardAboutPanel:"),
            help: "Version and credits for \(appName).")

        menu.addItem(.separator())

        add("Settings…", to: menu,
            action: #selector(showSettingsWindow(_:)),
            key: ",",
            target: self,
            help: "Choose whether music terms are explained, and where Python lives.")

        menu.addItem(.separator())

        let services = NSMenu()
        let servicesItem = add("Services", to: menu, help: "Commands other apps offer for the current selection.")
        servicesItem.submenu = services
        servicesMenu = services
        NSApp.servicesMenu = services

        menu.addItem(.separator())

        add("Hide \(appName)", to: menu,
            action: selector("hide:"),
            key: "h",
            help: "Hide every \(appName) window.")
        add("Hide Others", to: menu,
            action: selector("hideOtherApplications:"),
            key: "h",
            modifiers: [.command, .option],
            help: "Hide every other app's windows.")
        add("Show All", to: menu,
            action: selector("unhideAllApplications:"),
            help: "Bring hidden apps back.")

        menu.addItem(.separator())

        add("Quit \(appName)", to: menu,
            action: selector("terminate:"),
            key: "q",
            help: "Quit \(appName). You are asked about unsaved songs first.")

        return menu
    }

    // MARK: - File menu

    private func fileMenu() -> NSMenu {
        let menu = NSMenu(title: "File")

        add("New", to: menu,
            action: selector("newDocument:"),
            key: "n",
            help: "Start an empty song.")
        add("Open…", to: menu,
            action: selector("openDocument:"),
            key: "o",
            help: "Open a saved song file.")

        let recentItem = add("Open Recent", to: menu, help: "Songs you had open lately.")
        let recent = NSMenu(title: "Open Recent")
        // AppKit fills this menu in only when it can recognise it by identifier.
        recent.identifier = NSUserInterfaceItemIdentifier("NSRecentDocumentsMenu")
        add("Clear Menu", to: recent,
            action: selector("clearRecentDocuments:"),
            help: "Forget the list of recently opened songs. The songs themselves are untouched.")
        recentItem.submenu = recent
        recentDocumentsMenu = recent

        menu.addItem(.separator())

        add("Close", to: menu,
            action: selector("performClose:"),
            key: "w",
            help: "Close this window.")
        add("Save", to: menu,
            action: selector("saveDocument:"),
            key: "s",
            help: "Save changes to this song.")
        add("Save As…", to: menu,
            action: selector("saveDocumentAs:"),
            key: "s",
            modifiers: [.command, .shift],
            help: "Save this song under a new name.")
        add("Duplicate", to: menu,
            action: selector("duplicateDocument:"),
            key: "s",
            modifiers: [.command, .shift, .option],
            help: "Make a copy of this song and open it.")
        add("Rename…", to: menu,
            action: selector("renameDocument:"),
            help: "Give this song a different file name.")
        add("Move To…", to: menu,
            action: selector("moveDocument:"),
            help: "Move this song's file to another folder.")
        add("Revert to Saved", to: menu,
            action: selector("revertDocumentToSaved:"),
            help: "Throw away every change since the last save.")

        menu.addItem(.separator())

        add("Import Audio…", to: menu,
            action: #selector(DocumentWindowController.menuImportAudio(_:)),
            key: "i",
            modifiers: [.command, .shift],
            help: AppEnvironment.shared.help(
                "Add an audio file to the song as a new track.",
                term: "Track"))
        add("Build from a Description…", to: menu,
            action: #selector(DocumentWindowController.menuMaterializeTranscript(_:)),
            help: AppEnvironment.shared.help(
                "Turn a written description of a song into a real project.",
                term: "Transcript"))
        add("Tune a Vocal…", to: menu,
            action: #selector(DocumentWindowController.menuRunVocalLab(_:)),
            help: "Clean up and tune a recorded vocal take.")

        menu.addItem(.separator())

        add("Export Mix…", to: menu,
            action: #selector(DocumentWindowController.exportMixdown(_:)),
            key: "e",
            modifiers: [.command, .shift],
            help: AppEnvironment.shared.help(
                "Write the whole song out as one audio file.",
                term: "Mixdown"))
        add("Reveal Project File", to: menu,
            action: #selector(DocumentWindowController.menuRevealProjectFile(_:)),
            help: "Show this song's file in the Finder.")

        return menu
    }

    // MARK: - Edit menu

    private func editMenu() -> NSMenu {
        let menu = NSMenu(title: "Edit")

        add("Undo", to: menu,
            action: selector("undo:"),
            key: "z",
            help: "Take back the last change.")
        add("Redo", to: menu,
            action: selector("redo:"),
            key: "z",
            modifiers: [.command, .shift],
            help: "Put back the change you just undid.")

        menu.addItem(.separator())

        add("Cut", to: menu, action: selector("cut:"), key: "x",
            help: "Remove the selected text and put it on the clipboard.")
        add("Copy", to: menu, action: selector("copy:"), key: "c",
            help: "Put the selection on the clipboard.")
        add("Paste", to: menu, action: selector("paste:"), key: "v",
            help: "Insert what is on the clipboard.")
        // No key equivalent: binding bare Backspace here fired while the user
        // was typing in a text field.
        add("Delete", to: menu, action: selector("delete:"),
            help: "Remove the selected text.")
        add("Select All", to: menu, action: selector("selectAll:"), key: "a",
            help: "Select everything in the current field or list.")

        menu.addItem(.separator())

        // Also no key equivalent. The canvases handle the Delete key themselves
        // through the responder chain, so a focused text field always wins.
        add("Delete Selection", to: menu,
            action: #selector(DocumentWindowController.menuDeleteSelection(_:)),
            help: AppEnvironment.shared.help(
                "Remove the selected clip, or the selected track if no clip is selected. ⌘Z undoes it.",
                term: "Clip"))

        menu.addItem(.separator())

        add("Emoji & Symbols", to: menu,
            action: selector("orderFrontCharacterPalette:"),
            key: " ",
            modifiers: [.command, .control],
            help: "Open the character picker.")

        return menu
    }

    // MARK: - Track menu

    private func trackMenu() -> NSMenu {
        let menu = NSMenu(title: "Track")

        add("Add Track", to: menu,
            action: #selector(DocumentWindowController.menuAddTrack(_:)),
            key: "t",
            help: AppEnvironment.shared.help(
                "Add an empty row for another instrument or sound. ⌘Z undoes it.",
                term: "Track"))
        // Deliberately no key equivalent here — ⇧⌘I already lives in the File menu.
        add("Import Audio…", to: menu,
            action: #selector(DocumentWindowController.menuImportAudio(_:)),
            help: AppEnvironment.shared.help(
                "Add an audio file to the song as a new track.",
                term: "Stem"))

        menu.addItem(.separator())

        add("Delete Selected Track", to: menu,
            action: #selector(DocumentWindowController.menuDeleteSelection(_:)),
            help: AppEnvironment.shared.help(
                "Remove the selected track and everything on it. ⌘Z undoes it.",
                term: "Track"))

        return menu
    }

    // MARK: - View menu

    private func viewMenu() -> NSMenu {
        let menu = NSMenu(title: "View")

        for view in WorkView.allCases {
            let item = add(view.label, to: menu,
                           action: #selector(DocumentWindowController.menuShowView(_:)),
                           key: view.keyEquivalent,
                           help: view.explanation,
                           represented: view.rawValue)
            viewItems[view] = item
        }

        menu.addItem(.separator())

        add("Zoom In", to: menu,
            action: #selector(DocumentWindowController.menuZoomIn(_:)),
            key: "+",
            help: "Show fewer bars, larger.")
        add("Zoom Out", to: menu,
            action: #selector(DocumentWindowController.menuZoomOut(_:)),
            key: "-",
            help: "Show more bars at once, smaller.")

        menu.addItem(.separator())

        add("Show/Hide Track List", to: menu,
            action: selector("toggleSidebar:"),
            key: "s",
            modifiers: [.command, .control],
            help: "Show or hide the list of tracks on the left.")
        add("Show/Hide Inspector", to: menu,
            action: selector("toggleInspector:"),
            key: "i",
            modifiers: [.command, .option],
            help: "Show or hide the details panel on the right.")

        menu.addItem(.separator())

        // AppKit retitles this to "Exit Full Screen" on its own.
        add("Enter Full Screen", to: menu,
            action: selector("toggleFullScreen:"),
            key: "f",
            modifiers: [.command, .control],
            help: "Fill the screen with this window.")

        return menu
    }

    // MARK: - Transport menu

    private func transportMenu() -> NSMenu {
        let menu = NSMenu(title: "Transport")

        // No key equivalent: Space as a menu shortcut with an empty modifier
        // mask swallows the space bar everywhere, including in text fields. The
        // window handles Space through the responder chain instead, and the
        // Shortcuts window documents it.
        playItem = add("Play", to: menu,
                       action: #selector(DocumentWindowController.menuPlayPause(_:)),
                       help: "Start or stop playback. Space does the same.")
        add("Go to Start", to: menu,
            action: #selector(DocumentWindowController.menuGoToStart(_:)),
            help: "Move the playhead back to bar 1.")
        add("Record", to: menu,
            action: #selector(DocumentWindowController.menuToggleRecord(_:)),
            help: AppEnvironment.shared.help(
                "Record audio from your microphone into the song.",
                term: "Arm"))

        let countIn = NSMenu(title: "Count-In")
        for (title, bars) in [("Off", 0), ("1 Bar", 1), ("2 Bars", 2), ("4 Bars", 4)] {
            let item = add(title, to: countIn,
                           action: #selector(DocumentWindowController.menuSetCountIn(_:)),
                           help: bars == 0
                            ? "Start recording the instant you press Record."
                            : "Play \(bars * 4) clicks, then start recording on the downbeat.")
            item.tag = bars
        }
        let countInItem = NSMenuItem(title: "Count-In", action: nil, keyEquivalent: "")
        countInItem.submenu = countIn
        countInItem.toolTip = "How many bars of clicks to play before a take starts."
        menu.addItem(countInItem)

        menu.addItem(.separator())

        loopItem = add("Loop", to: menu,
                       action: #selector(DocumentWindowController.menuToggleLoop(_:)),
                       key: "l",
                       help: AppEnvironment.shared.help(
                        "Repeat a stretch of bars while you work.",
                        term: "Loop"))
        add("Set Loop Range…", to: menu,
            action: #selector(DocumentWindowController.menuEditLoopRange(_:)),
            key: "l",
            modifiers: [.command, .option],
            help: AppEnvironment.shared.help(
                "Choose which bars the loop repeats.",
                term: "Loop"))
        add("Set Tempo…", to: menu,
            action: #selector(DocumentWindowController.menuSetTempo(_:)),
            help: AppEnvironment.shared.help(
                "Change how fast the song plays.",
                term: "BPM"))

        menu.addItem(.separator())

        // Again no key equivalents: "v", "b" and "e" with no modifier would fire
        // mid-word. The Shortcuts window lists them as canvas keys.
        for tool in ToolId.allCases {
            let item = add(tool.label, to: menu,
                           action: #selector(DocumentWindowController.menuSelectTool(_:)),
                           help: tool.explanation,
                           represented: tool.rawValue)
            toolItems[tool] = item
        }

        return menu
    }

    // MARK: - Tools menu

    private func toolsMenu() -> NSMenu {
        let menu = NSMenu(title: "Tools")

        // ⇧⌘D would collide with Duplicate in the File menu, so this is ⌃⌘D.
        add("Check My Mix", to: menu,
            action: #selector(DocumentWindowController.runSoundCheck(_:)),
            key: "d",
            modifiers: [.command, .control],
            help: AppEnvironment.shared.help(
                "Listen to the rendered audio and report what to fix.",
                term: "Sound check"))
        add("Suggest Ideas", to: menu,
            action: #selector(DocumentWindowController.runDawAgent(_:)),
            key: "a",
            modifiers: [.command, .option],
            help: "Ask for concrete suggestions about what this song needs next.")

        menu.addItem(.separator())

        add("Listen With Me…", to: menu,
            action: #selector(DocumentWindowController.startListeningSession(_:)),
            help: "Play each part and answer a few plain questions. Your answers become steps to do.")
        add("Ask for a Change…", to: menu,
            action: #selector(DocumentWindowController.askForChange(_:)),
            key: "k",
            modifiers: [.command, .shift],
            help: "Say what should change in your own words and it happens. ⌘Z undoes it.")
        add("Hum a Melody…", to: menu,
            action: #selector(DocumentWindowController.humMelody(_:)),
            key: "h",
            modifiers: [.command, .shift],
            help: "Sing or hum, and the notes land on the selected track.")
        add("Try Alternatives…", to: menu,
            action: #selector(DocumentWindowController.tryAlternatives(_:)),
            help: "Hear three different takes on the selected track and pick one.")

        return menu
    }

    // MARK: - Window menu

    private func windowMenu() -> NSMenu {
        let menu = NSMenu(title: "Window")

        add("Minimize", to: menu,
            action: selector("performMiniaturize:"),
            key: "m",
            help: "Send this window to the Dock.")
        add("Zoom", to: menu,
            action: selector("performZoom:"),
            help: "Resize this window to fit its content.")

        menu.addItem(.separator())

        add("Activity", to: menu,
            action: #selector(showActivityWindow(_:)),
            target: self,
            help: "Everything the app has reported this session, newest first.")

        menu.addItem(.separator())

        add("Bring All to Front", to: menu,
            action: selector("arrangeInFront:"),
            help: "Bring every \(appName) window forward.")

        return menu
    }

    // MARK: - Help menu

    private func helpMenu() -> NSMenu {
        let menu = NSMenu(title: "Help")

        add("\(appName) Guide", to: menu,
            action: #selector(showWelcomeWindow(_:)),
            target: self,
            help: "The starting point: open an example song or begin your own.")
        add("Take the Tour", to: menu,
            action: #selector(DocumentWindowController.showTour(_:)),
            help: "Walk through the parts of the window one at a time.")
        add("Keyboard Shortcuts", to: menu,
            action: #selector(showShortcutsWindow(_:)),
            key: "?",
            target: self,
            help: "Every shortcut, including the ones that only work on a canvas.")

        menu.addItem(.separator())

        add("Music Terms Explained", to: menu,
            action: #selector(showGlossaryWindow(_:)),
            target: self,
            help: "Plain-English definitions of every studio word the app uses.")

        return menu
    }

    // MARK: - Actions owned by the menu bar itself
    //
    // These four have no document behind them, so unlike everything else they
    // are targeted directly rather than sent down the responder chain.

    @objc private func showSettingsWindow(_ sender: Any?) {
        SettingsWindowController.shared.present()
    }

    @objc private func showActivityWindow(_ sender: Any?) {
        ActivityWindowController.shared.present()
    }

    @objc private func showWelcomeWindow(_ sender: Any?) {
        WelcomeWindowController.shared.present()
    }

    @objc private func showShortcutsWindow(_ sender: Any?) {
        ShortcutsWindowController.shared.present()
    }

    @objc private func showGlossaryWindow(_ sender: Any?) {
        if glossaryWindowController == nil {
            glossaryWindowController = makeGlossaryWindowController()
        }
        glossaryWindowController?.showWindow(nil)
        glossaryWindowController?.window?.makeKeyAndOrderFront(nil)
        NSApp.activate()
    }

    // MARK: - Dynamic state

    /// Refreshes the titles and checkmarks that depend on the front window.
    ///
    /// `DocumentWindowController.validateMenuItem` already does this as each
    /// menu opens; this exists so the bar is also correct when something else
    /// changes state — switching windows, or finishing playback — without the
    /// user having pulled a menu down. A nil controller means no song window is
    /// frontmost, so everything reverts to its neutral state.
    func updateDynamicItems(for controller: DocumentWindowController?) {
        let hasDocument = controller != nil

        playItem?.title = controller?.isPlaying == true ? "Stop" : "Play"
        playItem?.isEnabled = hasDocument && !(controller?.project.snapshot.tracks.isEmpty ?? true)

        loopItem?.state = controller?.project.snapshot.loopEnabled == true ? .on : .off
        loopItem?.isEnabled = hasDocument

        let activeTool = controller?.activeTool
        for (tool, item) in toolItems {
            item.state = tool == activeTool ? .on : .off
            item.isEnabled = hasDocument
        }

        let activeView: WorkView? = controller.map {
            WorkView(rawValue: $0.project.snapshot.activeView ?? "") ?? .playlist
        }
        for (view, item) in viewItems {
            item.state = view == activeView ? .on : .off
            item.isEnabled = hasDocument
        }
    }

    // MARK: - Building blocks

    /// Wraps a menu in the bar-level item that carries it.
    private func submenu(_ menu: NSMenu, titled title: String) -> NSMenuItem {
        let item = NSMenuItem(title: title, action: nil, keyEquivalent: "")
        menu.title = title
        item.submenu = menu
        return item
    }

    /// One menu item. `target` stays nil unless the action belongs to this
    /// class, so items reach the responder chain and validate themselves.
    @discardableResult
    private func add(
        _ title: String,
        to menu: NSMenu,
        action: Selector? = nil,
        key: String = "",
        modifiers: NSEvent.ModifierFlags = [.command],
        target: AnyObject? = nil,
        help: String? = nil,
        represented: Any? = nil
    ) -> NSMenuItem {
        let item = NSMenuItem(title: title, action: action, keyEquivalent: key)
        item.keyEquivalentModifierMask = key.isEmpty ? [] : modifiers
        item.target = target
        item.toolTip = help
        item.representedObject = represented
        menu.addItem(item)
        return item
    }

    /// Standard AppKit actions have no Swift-visible declaration to point
    /// `#selector` at. Going through a function rather than writing
    /// `Selector("undo:")` inline also keeps the compiler from suggesting
    /// `#selector` for names that have no Swift counterpart.
    private func selector(_ name: String) -> Selector {
        Selector(name)
    }

    // MARK: - Shortcut audit
    //
    // Every key equivalent in the bar, so a new one can be checked without
    // reading the builder. No pair repeats.
    //
    //   ⌘,  Settings          ⌘N  New              ⌘O  Open
    //   ⌘W  Close             ⌘S  Save             ⌘H  Hide
    //   ⌘Q  Quit              ⌘Z  Undo             ⌘X  Cut
    //   ⌘C  Copy              ⌘V  Paste            ⌘A  Select All
    //   ⌘T  Add Track         ⌘L  Loop             ⌘M  Minimize
    //   ⌘?  Shortcuts         ⌘+  Zoom In          ⌘−  Zoom Out
    //   ⌘1…⌘6  the six views
    //   ⇧⌘S Save As           ⇧⌘Z Redo             ⇧⌘I Import Audio
    //   ⇧⌘E Export Mix
    //   ⌥⇧⌘S Duplicate
    //   ⌥⌘H Hide Others       ⌥⌘I Inspector        ⌥⌘L Loop Range
    //   ⌥⌘A Suggest Ideas
    //   ⌃⌘Space Emoji         ⌃⌘S Track List       ⌃⌘D Check My Mix
    //   ⌃⌘F Full Screen
    //
    // Intentionally unbound in the menu bar, because they would fire while
    // typing: Space (play/stop), Delete (delete selection), V/B/E (tools).

    // MARK: - Glossary window

    private func makeGlossaryWindowController() -> NSWindowController {
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 560, height: 620),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.title = "Music Terms Explained"
        window.minSize = NSSize(width: 420, height: 320)
        window.isReleasedWhenClosed = false
        window.setFrameAutosaveName("NeonStudioGlossaryWindow")

        let root = GlossaryBackdropView()
        root.translatesAutoresizingMaskIntoConstraints = false

        let heading = makeLabel(
            "Every studio word this app uses, in plain English.",
            font: Theme.Font.title(15),
            color: Theme.text
        )
        heading.setAccessibilityLabel("Every studio word this app uses, in plain English.")
        root.addSubview(heading)

        let scroll = NSScrollView()
        scroll.translatesAutoresizingMaskIntoConstraints = false
        scroll.hasVerticalScroller = true
        scroll.autohidesScrollers = true
        scroll.borderType = .noBorder
        scroll.drawsBackground = true
        scroll.backgroundColor = Theme.panel
        root.addSubview(scroll)

        let document = GlossaryBackdropView()
        document.translatesAutoresizingMaskIntoConstraints = false

        let stack = NSStackView()
        stack.translatesAutoresizingMaskIntoConstraints = false
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 18
        document.addSubview(stack)
        scroll.documentView = document

        for term in Glossary.terms {
            let name = makeLabel(term.name, font: Theme.Font.emphasis(14), color: Theme.text)
            name.isSelectable = true
            stack.addArrangedSubview(name)
            name.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true

            let detail = NSTextField(wrappingLabelWithString: term.long)
            detail.translatesAutoresizingMaskIntoConstraints = false
            detail.font = Theme.Font.body(12)
            detail.textColor = Theme.muted
            detail.isSelectable = true
            detail.drawsBackground = false
            detail.setAccessibilityLabel("\(term.name). \(term.long)")
            stack.addArrangedSubview(detail)
            detail.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true

            stack.setCustomSpacing(4, after: name)
        }

        let clip = scroll.contentView
        NSLayoutConstraint.activate([
            heading.leadingAnchor.constraint(equalTo: root.leadingAnchor, constant: 20),
            heading.trailingAnchor.constraint(equalTo: root.trailingAnchor, constant: -20),
            heading.topAnchor.constraint(equalTo: root.topAnchor, constant: 18),

            scroll.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            scroll.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            scroll.topAnchor.constraint(equalTo: heading.bottomAnchor, constant: 14),
            scroll.bottomAnchor.constraint(equalTo: root.bottomAnchor),

            document.leadingAnchor.constraint(equalTo: clip.leadingAnchor),
            document.trailingAnchor.constraint(equalTo: clip.trailingAnchor),
            document.topAnchor.constraint(equalTo: clip.topAnchor),

            stack.leadingAnchor.constraint(equalTo: document.leadingAnchor, constant: 20),
            stack.trailingAnchor.constraint(equalTo: document.trailingAnchor, constant: -20),
            stack.topAnchor.constraint(equalTo: document.topAnchor, constant: 16),
            stack.bottomAnchor.constraint(equalTo: document.bottomAnchor, constant: -24)
        ])

        let container = NSView()
        container.addSubview(root)
        NSLayoutConstraint.activate([
            root.leadingAnchor.constraint(equalTo: container.leadingAnchor),
            root.trailingAnchor.constraint(equalTo: container.trailingAnchor),
            root.topAnchor.constraint(equalTo: container.topAnchor),
            root.bottomAnchor.constraint(equalTo: container.bottomAnchor)
        ])
        window.contentView = container
        window.center()

        return NSWindowController(window: window)
    }
}

/// Flipped so the glossary starts scrolled to the first term rather than the
/// last, and painted so the window matches the rest of the app in either
/// appearance without anybody setting an explicit `NSAppearance`.
private final class GlossaryBackdropView: NSView {
    override var isFlipped: Bool { true }

    override func draw(_ dirtyRect: NSRect) {
        Theme.panel.setFill()
        dirtyRect.fill()
    }
}
