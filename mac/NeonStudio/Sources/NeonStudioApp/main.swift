import AppKit

// Entry point. `NSApplicationMain` is not used because the bundle is assembled
// by build.sh rather than by Xcode, so there is no nib to name as the principal
// class; wiring the delegate here is equivalent and easier to follow.
let application = NSApplication.shared
let appDelegate = AppDelegate()
application.delegate = appDelegate
application.setActivationPolicy(.regular)
application.run()
