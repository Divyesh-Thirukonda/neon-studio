import AppKit
import AVFoundation

struct LocalProject: Decodable {
    let id: String
    let name: String
    let updatedAt: String
    let snapshot: ProjectSnapshot
}

struct ProjectSnapshot: Decodable {
    let bpm: Double
    let tracks: [Track]
    let recipe: [RecipeItem]?
}

struct Track: Decodable {
    let id: String
    let name: String
    let file: String?
    let color: String
    let gain: Double
    let pan: Double
    let clips: [Clip]
}

struct Clip: Decodable {
    let id: String
    let name: String
    let startBar: Double
    let bars: Double
    let color: String
    let type: String
}

struct RecipeItem: Decodable {
    let id: String
    let label: String
}

final class ProjectStore {
    let rootURL: URL

    init(rootURL: URL) {
        self.rootURL = rootURL
    }

    func loadProjects() -> [LocalProject] {
        let dataDirectory = rootURL.appendingPathComponent("data/projects")
        let publicDirectory = rootURL.appendingPathComponent("public/projects")
        let urls = projectFiles(in: dataDirectory) + projectFiles(in: publicDirectory)
        var seen = Set<String>()
        var projects: [LocalProject] = []

        for url in urls {
            guard let data = try? Data(contentsOf: url),
                  let project = try? JSONDecoder().decode(LocalProject.self, from: data),
                  !seen.contains(project.id) else {
                continue
            }
            seen.insert(project.id)
            projects.append(project)
        }

        return projects.sorted { lhs, rhs in
            lhs.updatedAt > rhs.updatedAt
        }
    }

    private func projectFiles(in directory: URL) -> [URL] {
        guard let urls = try? FileManager.default.contentsOfDirectory(
            at: directory,
            includingPropertiesForKeys: nil
        ) else {
            return []
        }
        return urls.filter { $0.lastPathComponent.hasSuffix(".neon.json") }
    }

    func audioURL(for track: Track) -> URL? {
        guard let file = track.file else { return nil }
        if file.hasPrefix("/api/audio/") {
            return rootURL
                .appendingPathComponent("exports")
                .appendingPathComponent(URL(fileURLWithPath: file).lastPathComponent)
        }
        let cleaned = file.hasPrefix("/") ? String(file.dropFirst()) : file
        return rootURL.appendingPathComponent(cleaned)
    }
}

final class ClosureButton: NSButton {
    private let actionHandler: () -> Void

    init(title: String, bezelStyle: NSButton.BezelStyle = .rounded, action: @escaping () -> Void) {
        self.actionHandler = action
        super.init(frame: .zero)
        self.title = title
        self.bezelStyle = bezelStyle
        self.target = self
        self.action = #selector(runAction)
        self.translatesAutoresizingMaskIntoConstraints = false
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    @objc private func runAction() {
        actionHandler()
    }
}

final class LogoView: NSView {
    override var intrinsicContentSize: NSSize { NSSize(width: 48, height: 48) }

    override func draw(_ dirtyRect: NSRect) {
        let bounds = self.bounds.insetBy(dx: 2, dy: 2)
        NSColor(calibratedRed: 0.18, green: 0.19, blue: 0.21, alpha: 1).setFill()
        NSBezierPath(roundedRect: bounds, xRadius: 8, yRadius: 8).fill()

        let orange = NSBezierPath()
        orange.move(to: NSPoint(x: bounds.minX, y: bounds.maxY))
        orange.line(to: NSPoint(x: bounds.minX + bounds.width * 0.62, y: bounds.maxY))
        orange.line(to: NSPoint(x: bounds.minX, y: bounds.minY + bounds.height * 0.38))
        orange.close()
        NSColor(calibratedRed: 1.0, green: 0.55, blue: 0.36, alpha: 1).setFill()
        orange.fill()

        let green = NSBezierPath()
        green.move(to: NSPoint(x: bounds.minX, y: bounds.minY))
        green.line(to: NSPoint(x: bounds.minX + bounds.width * 0.62, y: bounds.minY))
        green.line(to: NSPoint(x: bounds.minX, y: bounds.minY + bounds.height * 0.62))
        green.close()
        NSColor(calibratedRed: 0.27, green: 0.82, blue: 0.56, alpha: 1).setFill()
        green.fill()

        let blue = NSBezierPath()
        blue.move(to: NSPoint(x: bounds.maxX, y: bounds.minY))
        blue.line(to: NSPoint(x: bounds.maxX, y: bounds.maxY))
        blue.line(to: NSPoint(x: bounds.minX + bounds.width * 0.62, y: bounds.maxY))
        blue.line(to: NSPoint(x: bounds.minX + bounds.width * 0.28, y: bounds.minY))
        blue.close()
        NSColor(calibratedRed: 0.38, green: 0.78, blue: 0.97, alpha: 1).setFill()
        blue.fill()
    }
}

final class PlaylistView: NSView {
    var tracks: [Track] = [] {
        didSet {
            needsDisplay = true
        }
    }

    private let totalBars: Double = 72

    override var isFlipped: Bool { true }

    override var intrinsicContentSize: NSSize {
        NSSize(width: 1450, height: max(420, tracks.count * 56 + 40))
    }

    override func draw(_ dirtyRect: NSRect) {
        NSColor(calibratedRed: 0.09, green: 0.10, blue: 0.11, alpha: 1).setFill()
        dirtyRect.fill()

        let leftWidth: CGFloat = 160
        let rowHeight: CGFloat = 56
        let rulerHeight: CGFloat = 34
        let timelineWidth = max(bounds.width - leftWidth - 16, 1000)
        let pixelsPerBar = timelineWidth / CGFloat(totalBars)

        NSColor(calibratedRed: 0.13, green: 0.14, blue: 0.15, alpha: 1).setFill()
        NSRect(x: 0, y: 0, width: leftWidth, height: bounds.height).fill()
        NSRect(x: leftWidth, y: 0, width: timelineWidth, height: rulerHeight).fill()

        for bar in 0...Int(totalBars) {
            let x = leftWidth + CGFloat(bar) * pixelsPerBar
            let path = NSBezierPath()
            path.move(to: NSPoint(x: x, y: 0))
            path.line(to: NSPoint(x: x, y: bounds.height))
            (bar % 4 == 0
             ? NSColor(calibratedRed: 0.31, green: 0.33, blue: 0.36, alpha: 1)
             : NSColor(calibratedRed: 0.20, green: 0.21, blue: 0.23, alpha: 1)).setStroke()
            path.lineWidth = bar % 4 == 0 ? 1.0 : 0.5
            path.stroke()

            if bar % 4 == 0 && bar < Int(totalBars) {
                drawText(
                    "\(bar + 1)",
                    in: NSRect(x: x + 6, y: 10, width: 44, height: 16),
                    color: .secondaryLabelColor,
                    size: 11,
                    weight: .semibold
                )
            }
        }

        for (index, track) in tracks.enumerated() {
            let y = rulerHeight + CGFloat(index) * rowHeight
            let lineRect = NSRect(x: 0, y: y, width: bounds.width, height: rowHeight)
            NSColor(calibratedRed: index.isMultiple(of: 2) ? 0.105 : 0.12, green: 0.11, blue: 0.12, alpha: 1).setFill()
            lineRect.fill()

            drawText(
                track.name,
                in: NSRect(x: 14, y: y + 18, width: leftWidth - 28, height: 18),
                color: .labelColor,
                size: 12,
                weight: .bold
            )

            color(from: track.color).setFill()
            NSBezierPath(ovalIn: NSRect(x: leftWidth - 22, y: y + 23, width: 8, height: 8)).fill()

            for clip in track.clips {
                let clipX = leftWidth + CGFloat(clip.startBar) * pixelsPerBar + 5
                let clipWidth = max(34, CGFloat(clip.bars) * pixelsPerBar - 10)
                let clipRect = NSRect(x: clipX, y: y + 8, width: clipWidth, height: rowHeight - 16)
                let clipColor = color(from: clip.color)
                clipColor.withAlphaComponent(0.42).setFill()
                NSBezierPath(roundedRect: clipRect, xRadius: 5, yRadius: 5).fill()
                clipColor.setStroke()
                NSBezierPath(roundedRect: clipRect, xRadius: 5, yRadius: 5).stroke()
                drawText(
                    clip.name,
                    in: clipRect.insetBy(dx: 8, dy: 10),
                    color: .white,
                    size: 11,
                    weight: .bold
                )
            }
        }
    }

    private func drawText(_ text: String, in rect: NSRect, color: NSColor, size: CGFloat, weight: NSFont.Weight) {
        let attributes: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: size, weight: weight),
            .foregroundColor: color
        ]
        (text as NSString).draw(in: rect, withAttributes: attributes)
    }

    private func color(from hex: String) -> NSColor {
        let cleaned = hex.trimmingCharacters(in: CharacterSet(charactersIn: "#"))
        guard cleaned.count == 6, let value = Int(cleaned, radix: 16) else {
            return NSColor.systemBlue
        }
        return NSColor(
            calibratedRed: CGFloat((value >> 16) & 0xFF) / 255.0,
            green: CGFloat((value >> 8) & 0xFF) / 255.0,
            blue: CGFloat(value & 0xFF) / 255.0,
            alpha: 1.0
        )
    }
}

final class MainWindowController: NSWindowController {
    private let store: ProjectStore
    private var projects: [LocalProject] = []
    private var currentProject: LocalProject?
    private var players: [AVAudioPlayer] = []

    private let projectList = NSStackView()
    private let playlistView = PlaylistView()
    private let titleLabel = NSTextField(labelWithString: "Neon Studio")
    private let subtitleLabel = NSTextField(labelWithString: "Native Mac preview")
    private let statusLabel = NSTextField(labelWithString: "Ready")
    private let trackCountLabel = NSTextField(labelWithString: "No project open")

    init(store: ProjectStore) {
        self.store = store
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1220, height: 760),
            styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        window.title = "Neon Studio"
        window.titlebarAppearsTransparent = true
        window.minSize = NSSize(width: 940, height: 620)
        super.init(window: window)
        buildInterface()
        loadProjects()
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    private func buildInterface() {
        guard let contentView = window?.contentView else { return }
        contentView.wantsLayer = true
        contentView.layer?.backgroundColor = NSColor(calibratedRed: 0.08, green: 0.085, blue: 0.09, alpha: 1).cgColor

        let root = NSStackView()
        root.orientation = .vertical
        root.spacing = 0
        root.translatesAutoresizingMaskIntoConstraints = false
        contentView.addSubview(root)
        NSLayoutConstraint.activate([
            root.leadingAnchor.constraint(equalTo: contentView.leadingAnchor),
            root.trailingAnchor.constraint(equalTo: contentView.trailingAnchor),
            root.topAnchor.constraint(equalTo: contentView.topAnchor),
            root.bottomAnchor.constraint(equalTo: contentView.bottomAnchor)
        ])

        root.addArrangedSubview(makeHeader())
        root.addArrangedSubview(makeBody())
    }

    private func makeHeader() -> NSView {
        let wrapper = NSView()
        wrapper.translatesAutoresizingMaskIntoConstraints = false
        wrapper.heightAnchor.constraint(equalToConstant: 92).isActive = true
        wrapper.wantsLayer = true
        wrapper.layer?.backgroundColor = NSColor(calibratedRed: 0.105, green: 0.11, blue: 0.12, alpha: 1).cgColor

        let logo = LogoView()
        logo.translatesAutoresizingMaskIntoConstraints = false

        titleLabel.font = NSFont.systemFont(ofSize: 28, weight: .black)
        titleLabel.textColor = .labelColor
        subtitleLabel.font = NSFont.systemFont(ofSize: 13, weight: .semibold)
        subtitleLabel.textColor = .secondaryLabelColor

        let titleStack = NSStackView(views: [titleLabel, subtitleLabel])
        titleStack.orientation = .vertical
        titleStack.spacing = 2
        titleStack.translatesAutoresizingMaskIntoConstraints = false

        let playButton = ClosureButton(title: "Play", bezelStyle: .regularSquare) { [weak self] in
            self?.play()
        }
        let stopButton = ClosureButton(title: "Stop", bezelStyle: .regularSquare) { [weak self] in
            self?.stop()
        }
        let vocalButton = ClosureButton(title: "Vocal Lab", bezelStyle: .regularSquare) { [weak self] in
            self?.showVocalLabNotice()
        }

        let controls = NSStackView(views: [playButton, stopButton, vocalButton])
        controls.orientation = .horizontal
        controls.spacing = 8
        controls.translatesAutoresizingMaskIntoConstraints = false

        wrapper.addSubview(logo)
        wrapper.addSubview(titleStack)
        wrapper.addSubview(controls)

        NSLayoutConstraint.activate([
            logo.leadingAnchor.constraint(equalTo: wrapper.leadingAnchor, constant: 24),
            logo.centerYAnchor.constraint(equalTo: wrapper.centerYAnchor, constant: 5),
            logo.widthAnchor.constraint(equalToConstant: 48),
            logo.heightAnchor.constraint(equalToConstant: 48),

            titleStack.leadingAnchor.constraint(equalTo: logo.trailingAnchor, constant: 16),
            titleStack.centerYAnchor.constraint(equalTo: logo.centerYAnchor),
            titleStack.trailingAnchor.constraint(lessThanOrEqualTo: controls.leadingAnchor, constant: -20),

            controls.trailingAnchor.constraint(equalTo: wrapper.trailingAnchor, constant: -24),
            controls.centerYAnchor.constraint(equalTo: logo.centerYAnchor)
        ])

        return wrapper
    }

    private func makeBody() -> NSView {
        let split = NSSplitView()
        split.isVertical = true
        split.dividerStyle = .thin
        split.translatesAutoresizingMaskIntoConstraints = false

        let sidebar = makeSidebar()
        let main = makeMainPanel()
        split.addArrangedSubview(sidebar)
        split.addArrangedSubview(main)
        sidebar.widthAnchor.constraint(equalToConstant: 300).isActive = true

        return split
    }

    private func makeSidebar() -> NSView {
        let wrapper = NSView()
        wrapper.wantsLayer = true
        wrapper.layer?.backgroundColor = NSColor(calibratedRed: 0.11, green: 0.115, blue: 0.125, alpha: 1).cgColor
        wrapper.translatesAutoresizingMaskIntoConstraints = false

        let heading = NSTextField(labelWithString: "Projects")
        heading.font = NSFont.systemFont(ofSize: 16, weight: .black)
        heading.textColor = .labelColor
        heading.translatesAutoresizingMaskIntoConstraints = false

        projectList.orientation = .vertical
        projectList.alignment = .leading
        projectList.spacing = 8
        projectList.translatesAutoresizingMaskIntoConstraints = false

        let scroll = NSScrollView()
        scroll.documentView = projectList
        scroll.hasVerticalScroller = true
        scroll.drawsBackground = false
        scroll.translatesAutoresizingMaskIntoConstraints = false

        wrapper.addSubview(heading)
        wrapper.addSubview(scroll)

        NSLayoutConstraint.activate([
            heading.leadingAnchor.constraint(equalTo: wrapper.leadingAnchor, constant: 18),
            heading.trailingAnchor.constraint(equalTo: wrapper.trailingAnchor, constant: -18),
            heading.topAnchor.constraint(equalTo: wrapper.topAnchor, constant: 18),

            scroll.leadingAnchor.constraint(equalTo: wrapper.leadingAnchor, constant: 12),
            scroll.trailingAnchor.constraint(equalTo: wrapper.trailingAnchor, constant: -12),
            scroll.topAnchor.constraint(equalTo: heading.bottomAnchor, constant: 12),
            scroll.bottomAnchor.constraint(equalTo: wrapper.bottomAnchor, constant: -12),

            projectList.widthAnchor.constraint(equalTo: scroll.widthAnchor, constant: -20)
        ])

        return wrapper
    }

    private func makeMainPanel() -> NSView {
        let wrapper = NSView()
        wrapper.translatesAutoresizingMaskIntoConstraints = false
        wrapper.wantsLayer = true
        wrapper.layer?.backgroundColor = NSColor(calibratedRed: 0.085, green: 0.09, blue: 0.10, alpha: 1).cgColor

        trackCountLabel.font = NSFont.systemFont(ofSize: 13, weight: .bold)
        trackCountLabel.textColor = .secondaryLabelColor
        trackCountLabel.translatesAutoresizingMaskIntoConstraints = false

        statusLabel.font = NSFont.monospacedSystemFont(ofSize: 12, weight: .semibold)
        statusLabel.textColor = .secondaryLabelColor
        statusLabel.translatesAutoresizingMaskIntoConstraints = false

        let scroll = NSScrollView()
        scroll.documentView = playlistView
        scroll.hasVerticalScroller = true
        scroll.hasHorizontalScroller = true
        scroll.autohidesScrollers = false
        scroll.drawsBackground = false
        scroll.translatesAutoresizingMaskIntoConstraints = false

        wrapper.addSubview(trackCountLabel)
        wrapper.addSubview(statusLabel)
        wrapper.addSubview(scroll)

        NSLayoutConstraint.activate([
            trackCountLabel.leadingAnchor.constraint(equalTo: wrapper.leadingAnchor, constant: 18),
            trackCountLabel.topAnchor.constraint(equalTo: wrapper.topAnchor, constant: 16),
            trackCountLabel.trailingAnchor.constraint(lessThanOrEqualTo: statusLabel.leadingAnchor, constant: -12),

            statusLabel.trailingAnchor.constraint(equalTo: wrapper.trailingAnchor, constant: -18),
            statusLabel.centerYAnchor.constraint(equalTo: trackCountLabel.centerYAnchor),

            scroll.leadingAnchor.constraint(equalTo: wrapper.leadingAnchor, constant: 14),
            scroll.trailingAnchor.constraint(equalTo: wrapper.trailingAnchor, constant: -14),
            scroll.topAnchor.constraint(equalTo: trackCountLabel.bottomAnchor, constant: 12),
            scroll.bottomAnchor.constraint(equalTo: wrapper.bottomAnchor, constant: -14)
        ])

        return wrapper
    }

    private func loadProjects() {
        projects = store.loadProjects()
        projectList.arrangedSubviews.forEach { view in
            projectList.removeArrangedSubview(view)
            view.removeFromSuperview()
        }

        if projects.isEmpty {
            let empty = NSTextField(labelWithString: "No .neon.json projects found.")
            empty.textColor = .secondaryLabelColor
            projectList.addArrangedSubview(empty)
            statusLabel.stringValue = "No projects at \(store.rootURL.path)"
            return
        }

        for project in projects {
            let label = "\(project.name)\n\(Int(project.snapshot.bpm)) BPM · \(project.snapshot.tracks.count) tracks"
            let button = ClosureButton(title: label, bezelStyle: .regularSquare) { [weak self] in
                self?.open(project)
            }
            button.alignment = .left
            button.lineBreakMode = .byWordWrapping
            button.heightAnchor.constraint(equalToConstant: 62).isActive = true
            button.widthAnchor.constraint(equalToConstant: 256).isActive = true
            projectList.addArrangedSubview(button)
        }

        open(projects[0])
    }

    private func open(_ project: LocalProject) {
        stop()
        currentProject = project
        titleLabel.stringValue = project.name
        subtitleLabel.stringValue = "\(Int(project.snapshot.bpm)) BPM · \(project.snapshot.tracks.count) tracks · \(project.snapshot.recipe?.count ?? 0) recipe items"
        trackCountLabel.stringValue = "Playlist"
        playlistView.tracks = project.snapshot.tracks
        playlistView.setFrameSize(playlistView.intrinsicContentSize)
        statusLabel.stringValue = "Opened \(project.name)"
    }

    private func play() {
        guard let project = currentProject else {
            statusLabel.stringValue = "Open a project first"
            return
        }
        stop()

        for track in project.snapshot.tracks {
            guard let url = store.audioURL(for: track),
                  FileManager.default.fileExists(atPath: url.path) else {
                continue
            }
            do {
                let player = try AVAudioPlayer(contentsOf: url)
                player.volume = Float(max(0, min(track.gain, 1.4)))
                player.pan = Float(max(-1, min(track.pan, 1)))
                player.prepareToPlay()
                player.play()
                players.append(player)
            } catch {
                statusLabel.stringValue = "Could not play \(track.name)"
            }
        }

        statusLabel.stringValue = players.isEmpty ? "No audio stems found" : "Playing \(players.count) stems"
    }

    private func stop() {
        players.forEach { player in
            player.stop()
            player.currentTime = 0
        }
        players.removeAll()
        if currentProject != nil {
            statusLabel.stringValue = "Stopped"
        }
    }

    private func showVocalLabNotice() {
        let alert = NSAlert()
        alert.messageText = "Vocal Lab"
        alert.informativeText = "The web app already has the first automatic vocal tuner. The native app can use the same Python processor next; this Mac preview proves projects and stems can run outside the browser."
        alert.addButton(withTitle: "OK")
        alert.runModal()
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var windowController: MainWindowController?

    func applicationDidFinishLaunching(_ notification: Notification) {
        let bundleURL = Bundle.main.bundleURL
        let rootURL = bundleURL
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()

        let controller = MainWindowController(store: ProjectStore(rootURL: rootURL))
        windowController = controller
        controller.window?.center()
        controller.showWindow(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
