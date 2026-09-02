import AppKit
import Foundation
import NeonStudioKit

/// Application-level wiring, and nothing else.
///
/// Neon Studio is a document-based app now, so `NSDocumentController` owns
/// opening, saving, Open Recent, autosave and restoration. This delegate
/// deliberately creates no editor windows of its own: it seeds the support
/// folder, installs the menu bar, shows the welcome window when there is
/// nothing else to look at, and keeps the dynamic menu items pointed at
/// whichever project window is in front.
///
/// Two things the previous build did are specifically *not* done here:
///
/// * There is no `NSEvent.addLocalMonitorForEvents` key monitor. The old one
///   swallowed Space and Delete before any text field could see them, so you
///   could not type a space in the app's own search field or backspace in a
///   rename box. Keyboard handling belongs to the responder chain and to menu
///   key equivalents, both of which `MenuBuilder` sets up.
/// * There is no blocking modal on a cold start. Setup problems (a missing
///   Python interpreter, a seed folder that could not be copied) are reported
///   through `StatusCenter` so launch never stalls behind an alert the user
///   cannot act on yet.
final class AppDelegate: NSObject, NSApplicationDelegate {

    /// Posted by the welcome window and anything else that wants to replay the
    /// guided tour. Kept as a notification so those windows do not need a
    /// reference to whichever project window happens to be in front.
    static let startTourNotification = Notification.Name("NeonStudioStartTour")

    private var observers: [NSObjectProtocol] = []

    /// The tour offers itself once per launch, when the first project window
    /// becomes main — not every time the user switches between windows.
    private var hasOfferedTourThisLaunch = false

    /// Read before `markFirstRunComplete()` clears it, so the welcome window
    /// still knows this was a first launch.
    private var launchedForTheFirstTime = false

    deinit {
        observers.forEach { NotificationCenter.default.removeObserver($0) }
    }

    // MARK: - Launch

    func applicationWillFinishLaunching(_ notification: Notification) {
        // Defaults first: everything below reads them.
        AppEnvironment.registerDefaults()
        // Touching the shared environment seeds
        // ~/Library/Application Support/Neon Studio with the example songs and
        // helper tools. Do it before any window can ask the store for projects.
        _ = AppEnvironment.shared
        // The menu bar has to exist before the app finishes launching, or the
        // first click on it shows Apple's placeholder menu.
        MenuBuilder.shared.install()
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        launchedForTheFirstTime = AppEnvironment.shared.isFirstRun
        installObservers()

        // A document opened by double-clicking a file in the Finder is already
        // open by this point, so the menus can be aimed at it immediately.
        MenuBuilder.shared.updateDynamicItems(for: frontmostDocumentWindowController())

        presentWelcomeIfAppropriate()
        AppEnvironment.shared.markFirstRunComplete()
        reportSetupProblems()

        NSApp.activate(ignoringOtherApps: true)
    }

    private func installObservers() {
        let center = NotificationCenter.default

        observers.append(center.addObserver(
            forName: AppDelegate.startTourNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            self?.startTourInFrontmostWindow()
        })

        observers.append(center.addObserver(
            forName: NSWindow.didBecomeMainNotification,
            object: nil,
            queue: .main
        ) { [weak self] note in
            self?.mainWindowChanged(note.object as? NSWindow)
        })

        // Coming back to the app is the moment a key changed elsewhere (in
        // Keychain Access, or the CLI's config file) should start counting, so
        // the next tool launch reads it fresh instead of a stale cached copy.
        observers.append(center.addObserver(
            forName: NSApplication.didBecomeActiveNotification,
            object: nil,
            queue: .main
        ) { _ in
            AppEnvironment.shared.invalidateAIKeyCache()
        })
    }

    // MARK: - Documents

    /// The welcome window is the first-run surface, so launching does not dump
    /// the user into a blank untitled song they did not ask for and would have
    /// to name and throw away.
    func applicationShouldOpenUntitledFile(_ sender: NSApplication) -> Bool {
        false
    }

    /// Clicking the Dock icon with every project window closed should show
    /// something, and the welcome window is the one place that lists the user's
    /// songs and offers to start a new one.
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if !flag {
            WelcomeWindowController.shared.present()
        }
        return true
    }

    /// Standard document-app behaviour: closing the last project leaves the app
    /// running with its menu bar, so File ▸ Open Recent still works.
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        false
    }

    func applicationSupportsSecureRestorableState(_ app: NSApplication) -> Bool {
        true
    }

    // MARK: - Welcome

    private func presentWelcomeIfAppropriate() {
        let wanted = AppEnvironment.shared.showsWelcomeOnLaunch || launchedForTheFirstTime
        guard wanted, NSDocumentController.shared.documents.isEmpty else { return }
        // One turn of the run loop, so a document still being opened from a
        // launch AppleEvent gets the chance to register itself first.
        DispatchQueue.main.async {
            guard NSDocumentController.shared.documents.isEmpty else { return }
            WelcomeWindowController.shared.present()
        }
    }

    // MARK: - Menus and the tour

    private func mainWindowChanged(_ window: NSWindow?) {
        let controller = window?.windowController as? DocumentWindowController
        MenuBuilder.shared.updateDynamicItems(for: controller)

        guard let controller, !hasOfferedTourThisLaunch else { return }
        hasOfferedTourThisLaunch = true
        // After layout, so the tour highlights real view frames rather than
        // the zero rects a freshly ordered-in window still reports.
        DispatchQueue.main.async {
            controller.startTourIfNeeded()
        }
    }

    /// Replays the tour on request, whether or not the user has seen it before.
    private func startTourInFrontmostWindow() {
        guard let controller = frontmostDocumentWindowController() else {
            StatusCenter.shared.info(
                "Open a song to take the tour.",
                detail: "The tour points at the parts of a project window, so it needs a project open."
            )
            return
        }
        // Once the tour has been asked for explicitly, do not also offer it
        // when this window becomes main.
        hasOfferedTourThisLaunch = true
        controller.window?.makeKeyAndOrderFront(nil)
        controller.showTour(nil)
    }

    private func frontmostDocumentWindowController() -> DocumentWindowController? {
        if let controller = NSApp.mainWindow?.windowController as? DocumentWindowController {
            return controller
        }
        if let controller = NSApp.keyWindow?.windowController as? DocumentWindowController {
            return controller
        }
        for document in NSDocumentController.shared.documents {
            for windowController in document.windowControllers {
                if let controller = windowController as? DocumentWindowController {
                    return controller
                }
            }
        }
        return nil
    }

    // MARK: - Setup problems

    /// Reported, never fatal. A missing Python interpreter only disables
    /// rendering and analysis; everything else in the app still works, and the
    /// user finds out in plain language instead of by a button that silently
    /// does nothing.
    private func reportSetupProblems() {
        for warning in AppEnvironment.shared.setupWarnings {
            StatusCenter.shared.warning(warning, detail: "Open Window ▸ Activity for the full list.")
        }

        // Probing runs each candidate interpreter, and on a Mac without Apple's
        // Command Line Tools /usr/bin/python3 is a stub that can stall. Doing it
        // here on the main thread would delay the first window appearing.
        DispatchQueue.global(qos: .utility).async {
            let missing = AppEnvironment.shared.pythonExecutable == nil
            guard missing else { return }
            DispatchQueue.main.async {
                StatusCenter.shared.warning(
                    "Neon Studio can't find Python, so rendering and sound check are switched off.",
                    detail: "Everything else works. Open Neon Studio ▸ Settings and choose a Python 3 program to turn them back on."
                )
            }
        }
    }

    // MARK: - Responder-chain actions

    // Menu items that act on the app rather than on a document end up here when
    // they are sent to the responder chain. Each one opens a window the user
    // could otherwise only reach by accident.

    @objc func showWelcomeWindow(_ sender: Any?) {
        WelcomeWindowController.shared.present()
    }

    @objc func showSettingsWindow(_ sender: Any?) {
        SettingsWindowController.shared.present()
    }

    @objc func showActivityWindow(_ sender: Any?) {
        ActivityWindowController.shared.present()
    }

    @objc func showKeyboardShortcuts(_ sender: Any?) {
        ShortcutsWindowController.shared.present()
    }

    @objc func startGuidedTour(_ sender: Any?) {
        startTourInFrontmostWindow()
    }
}
