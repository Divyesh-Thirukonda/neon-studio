import AppKit
import AVFoundation

struct LocalProject: Decodable {
    let id: String
    let name: String
    let updatedAt: String
    let description: String?
    let keyCenter: String?
    let snapshot: ProjectSnapshot
}

struct ProjectSnapshot: Decodable {
    let bpm: Double
    let loopStartBar: Double?
    let loopEndBar: Double?
    let swing: Double?
    let tracks: [Track]
    let recipe: [RecipeItem]?
}

struct Track: Decodable {
    let id: String
    let name: String
    let kind: String?
    let file: String?
    let color: String?
    let gain: Double?
    let pan: Double?
    let steps: [Int]?
    let instrument: String?
    let clips: [Clip]?
    let effects: [Effect]?
}

struct Clip: Decodable {
    let id: String
    let name: String
    let startBar: Double?
    let bars: Double?
    let lane: String?
    let color: String?
    let type: String?
}

struct Effect: Decodable {
    let id: String
    let name: String
    let active: Bool?
    let amount: Double?
}

struct RecipeItem: Decodable {
    let id: String
    let section: String?
    let label: String
    let detail: String?
    let status: String?
    let trackIds: [String]?
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

enum Palette {
    static let app = NSColor(calibratedRed: 0.055, green: 0.065, blue: 0.075, alpha: 1)
    static let panel = NSColor(calibratedRed: 0.095, green: 0.105, blue: 0.118, alpha: 1)
    static let panelAlt = NSColor(calibratedRed: 0.118, green: 0.128, blue: 0.142, alpha: 1)
    static let panelRaised = NSColor(calibratedRed: 0.15, green: 0.16, blue: 0.18, alpha: 1)
    static let stroke = NSColor(calibratedRed: 0.255, green: 0.27, blue: 0.30, alpha: 1)
    static let subtleStroke = NSColor(calibratedRed: 0.18, green: 0.195, blue: 0.215, alpha: 1)
    static let text = NSColor(calibratedRed: 0.91, green: 0.90, blue: 0.86, alpha: 1)
    static let muted = NSColor(calibratedRed: 0.66, green: 0.67, blue: 0.65, alpha: 1)
    static let dim = NSColor(calibratedRed: 0.44, green: 0.46, blue: 0.49, alpha: 1)
    static let yellow = NSColor(calibratedRed: 1.0, green: 0.79, blue: 0.30, alpha: 1)
    static let blue = NSColor(calibratedRed: 0.42, green: 0.78, blue: 0.96, alpha: 1)
    static let coral = NSColor(calibratedRed: 1.0, green: 0.52, blue: 0.36, alpha: 1)
    static let green = NSColor(calibratedRed: 0.29, green: 0.83, blue: 0.55, alpha: 1)
}

func color(from hex: String?, fallback: NSColor = Palette.blue) -> NSColor {
    guard let hex else { return fallback }
    var cleaned = hex.trimmingCharacters(in: .whitespacesAndNewlines)
    if cleaned.hasPrefix("#") {
        cleaned.removeFirst()
    }

    guard cleaned.count == 6, let value = Int(cleaned, radix: 16) else {
        return fallback
    }

    let red = CGFloat((value >> 16) & 0xff) / 255
    let green = CGFloat((value >> 8) & 0xff) / 255
    let blue = CGFloat(value & 0xff) / 255
    return NSColor(calibratedRed: red, green: green, blue: blue, alpha: 1)
}

func drawText(
    _ text: String,
    in rect: NSRect,
    color: NSColor = Palette.text,
    size: CGFloat = 12,
    weight: NSFont.Weight = .regular,
    alignment: NSTextAlignment = .left,
    lineBreak: NSLineBreakMode = .byTruncatingTail
) {
    let paragraph = NSMutableParagraphStyle()
    paragraph.alignment = alignment
    paragraph.lineBreakMode = lineBreak
    let attributes: [NSAttributedString.Key: Any] = [
        .font: NSFont.systemFont(ofSize: size, weight: weight),
        .foregroundColor: color,
        .paragraphStyle: paragraph
    ]
    NSString(string: text).draw(in: rect, withAttributes: attributes)
}

func roundedFill(_ rect: NSRect, radius: CGFloat, color: NSColor) {
    color.setFill()
    NSBezierPath(roundedRect: rect, xRadius: radius, yRadius: radius).fill()
}

func roundedStroke(_ rect: NSRect, radius: CGFloat, color: NSColor, width: CGFloat = 1) {
    color.setStroke()
    let path = NSBezierPath(roundedRect: rect, xRadius: radius, yRadius: radius)
    path.lineWidth = width
    path.stroke()
}

func makeLabel(
    _ text: String,
    size: CGFloat,
    weight: NSFont.Weight = .regular,
    color: NSColor = Palette.text,
    mono: Bool = false
) -> NSTextField {
    let label = NSTextField(labelWithString: text)
    label.font = mono ? NSFont.monospacedSystemFont(ofSize: size, weight: weight) : NSFont.systemFont(ofSize: size, weight: weight)
    label.textColor = color
    label.lineBreakMode = .byTruncatingTail
    label.translatesAutoresizingMaskIntoConstraints = false
    return label
}

final class ClosureButton: NSButton {
    private let actionHandler: () -> Void
    private let normalColor: NSColor
    private let primary: Bool

    init(
        title: String,
        symbol: String? = nil,
        primary: Bool = false,
        action: @escaping () -> Void
    ) {
        self.actionHandler = action
        self.primary = primary
        self.normalColor = primary ? Palette.yellow : Palette.panelRaised
        super.init(frame: .zero)
        self.title = title
        self.isBordered = false
        self.bezelStyle = .regularSquare
        self.font = NSFont.systemFont(ofSize: 12, weight: .bold)
        self.target = self
        self.action = #selector(runAction)
        self.imagePosition = .imageLeading
        self.translatesAutoresizingMaskIntoConstraints = false
        self.wantsLayer = true
        self.layer?.backgroundColor = normalColor.cgColor
        self.layer?.borderColor = (primary ? Palette.yellow : Palette.stroke).cgColor
        self.layer?.borderWidth = primary ? 0 : 1
        self.layer?.cornerRadius = 8
        self.contentTintColor = primary ? NSColor.black : Palette.text
        updateAttributedTitle()

        if let symbol, let image = NSImage(systemSymbolName: symbol, accessibilityDescription: title) {
            self.image = image
            self.imageScaling = .scaleProportionallyDown
        }
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override var title: String {
        didSet {
            updateAttributedTitle()
        }
    }

    private func updateAttributedTitle() {
        attributedTitle = NSAttributedString(
            string: title,
            attributes: [
                .font: NSFont.systemFont(ofSize: 12, weight: .bold),
                .foregroundColor: primary ? NSColor.black : Palette.text
            ]
        )
    }

    @objc private func runAction() {
        actionHandler()
    }
}

final class LogoView: NSView {
    override var intrinsicContentSize: NSSize { NSSize(width: 50, height: 50) }

    override func draw(_ dirtyRect: NSRect) {
        let rect = bounds.insetBy(dx: 2, dy: 2)
        roundedFill(rect, radius: 9, color: Palette.panelRaised)
        roundedStroke(rect, radius: 9, color: Palette.stroke)

        let orange = NSBezierPath()
        orange.move(to: NSPoint(x: rect.minX, y: rect.maxY))
        orange.line(to: NSPoint(x: rect.minX + rect.width * 0.64, y: rect.maxY))
        orange.line(to: NSPoint(x: rect.minX, y: rect.minY + rect.height * 0.39))
        orange.close()
        Palette.coral.setFill()
        orange.fill()

        let green = NSBezierPath()
        green.move(to: NSPoint(x: rect.minX, y: rect.minY))
        green.line(to: NSPoint(x: rect.minX + rect.width * 0.64, y: rect.minY))
        green.line(to: NSPoint(x: rect.minX, y: rect.minY + rect.height * 0.61))
        green.close()
        Palette.green.setFill()
        green.fill()

        let blue = NSBezierPath()
        blue.move(to: NSPoint(x: rect.maxX, y: rect.minY))
        blue.line(to: NSPoint(x: rect.maxX, y: rect.maxY))
        blue.line(to: NSPoint(x: rect.minX + rect.width * 0.64, y: rect.maxY))
        blue.line(to: NSPoint(x: rect.minX + rect.width * 0.30, y: rect.minY))
        blue.close()
        Palette.blue.setFill()
        blue.fill()
    }
}

final class ReadoutView: NSView {
    private let title: String
    var value: String {
        didSet { needsDisplay = true }
    }

    init(title: String, value: String) {
        self.title = title
        self.value = value
        super.init(frame: .zero)
        translatesAutoresizingMaskIntoConstraints = false
        wantsLayer = true
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override var isFlipped: Bool { true }
    override var intrinsicContentSize: NSSize { NSSize(width: 104, height: 48) }

    override func draw(_ dirtyRect: NSRect) {
        let rect = bounds.insetBy(dx: 1, dy: 1)
        roundedFill(rect, radius: 8, color: Palette.panel)
        roundedStroke(rect, radius: 8, color: Palette.stroke)
        drawText(title.uppercased(), in: NSRect(x: rect.minX + 10, y: rect.minY + 7, width: rect.width - 20, height: 14), color: Palette.dim, size: 9, weight: .black)
        drawText(value, in: NSRect(x: rect.minX + 10, y: rect.minY + 22, width: rect.width - 20, height: 18), color: Palette.text, size: 14, weight: .black, alignment: .left)
    }
}

final class TitledPanel: NSView {
    let contentGuide = NSView()
    private let title: String
    private let accessory: String?

    init(title: String, accessory: String? = nil) {
        self.title = title
        self.accessory = accessory
        super.init(frame: .zero)
        translatesAutoresizingMaskIntoConstraints = false
        wantsLayer = true
        layer?.backgroundColor = Palette.panel.cgColor
        layer?.borderColor = Palette.stroke.cgColor
        layer?.borderWidth = 1
        layer?.cornerRadius = 8
        contentGuide.translatesAutoresizingMaskIntoConstraints = false
        addSubview(contentGuide)

        NSLayoutConstraint.activate([
            contentGuide.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 12),
            contentGuide.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -12),
            contentGuide.topAnchor.constraint(equalTo: topAnchor, constant: 44),
            contentGuide.bottomAnchor.constraint(equalTo: bottomAnchor, constant: -12)
        ])
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override var isFlipped: Bool { true }

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        drawText(title, in: NSRect(x: 14, y: 13, width: bounds.width - 120, height: 20), color: Palette.text, size: 14, weight: .black)
        if let accessory {
            drawText(accessory, in: NSRect(x: bounds.width - 102, y: 13, width: 88, height: 20), color: Palette.muted, size: 11, weight: .bold, alignment: .right)
        }
        Palette.subtleStroke.setStroke()
        let line = NSBezierPath()
        line.move(to: NSPoint(x: 0, y: 43.5))
        line.line(to: NSPoint(x: bounds.width, y: 43.5))
        line.lineWidth = 1
        line.stroke()
    }
}

final class BrowserProjectsView: NSView {
    var projects: [LocalProject] = [] {
        didSet { needsDisplay = true }
    }
    var selectedId: String? {
        didSet { needsDisplay = true }
    }
    var onProjectSelected: ((LocalProject) -> Void)?

    private let rowHeight: CGFloat = 72

    override var isFlipped: Bool { true }
    override var intrinsicContentSize: NSSize {
        NSSize(width: 260, height: max(160, CGFloat(projects.count) * rowHeight + 58))
    }

    override func draw(_ dirtyRect: NSRect) {
        Palette.panel.setFill()
        dirtyRect.fill()

        let search = NSRect(x: 0, y: 0, width: bounds.width, height: 38)
        roundedFill(search, radius: 8, color: NSColor(calibratedRed: 0.07, green: 0.08, blue: 0.09, alpha: 1))
        roundedStroke(search, radius: 8, color: Palette.stroke)
        drawText("Search projects, stems, samples", in: search.insetBy(dx: 34, dy: 11), color: Palette.dim, size: 12, weight: .semibold)
        drawSearchIcon(in: NSRect(x: 12, y: 10, width: 18, height: 18))

        for (index, project) in projects.enumerated() {
            let y = 52 + CGFloat(index) * rowHeight
            let rect = NSRect(x: 0, y: y, width: bounds.width, height: rowHeight - 10)
            let selected = project.id == selectedId
            roundedFill(rect, radius: 8, color: selected ? NSColor(calibratedRed: 0.14, green: 0.20, blue: 0.25, alpha: 1) : Palette.panelAlt)
            roundedStroke(rect, radius: 8, color: selected ? Palette.blue : Palette.subtleStroke, width: selected ? 1.5 : 1)
            drawText(project.name, in: NSRect(x: 14, y: y + 12, width: bounds.width - 28, height: 18), color: Palette.text, size: 13, weight: .black)
            let detail = "\(Int(project.snapshot.bpm)) BPM  \(project.snapshot.tracks.count) tracks  \(project.snapshot.recipe?.count ?? 0) items"
            drawText(detail, in: NSRect(x: 14, y: y + 34, width: bounds.width - 28, height: 16), color: Palette.muted, size: 11, weight: .semibold)
        }
    }

    override func mouseDown(with event: NSEvent) {
        let point = convert(event.locationInWindow, from: nil)
        let primary = project(atVisualY: point.y)
        let mirrored = project(atVisualY: bounds.height - point.y)

        if let mirrored, mirrored.id != selectedId, primary?.id == selectedId {
            onProjectSelected?(mirrored)
            return
        }

        if let project = primary ?? mirrored {
            onProjectSelected?(project)
        }
    }

    private func project(atVisualY y: CGFloat) -> LocalProject? {
        let index = Int((y - 52) / rowHeight)
        guard index >= 0, index < projects.count else { return nil }
        let rowMin = 52 + CGFloat(index) * rowHeight
        let rowMax = rowMin + rowHeight - 10
        guard y >= rowMin, y <= rowMax else { return nil }
        return projects[index]
    }

    private func drawSearchIcon(in rect: NSRect) {
        Palette.dim.setStroke()
        let glass = NSBezierPath(ovalIn: NSRect(x: rect.minX, y: rect.minY, width: 11, height: 11))
        glass.lineWidth = 1.7
        glass.stroke()

        let handle = NSBezierPath()
        handle.move(to: NSPoint(x: rect.minX + 10, y: rect.minY + 10))
        handle.line(to: NSPoint(x: rect.maxX, y: rect.maxY))
        handle.lineWidth = 1.7
        handle.stroke()
    }
}

final class ChannelRackView: NSView {
    var tracks: [Track] = [] {
        didSet {
            invalidateIntrinsicContentSize()
            needsDisplay = true
        }
    }

    private let rowHeight: CGFloat = 34
    private let nameWidth: CGFloat = 118

    override var isFlipped: Bool { true }
    override var intrinsicContentSize: NSSize {
        NSSize(width: 520, height: max(210, 34 + CGFloat(tracks.count) * rowHeight))
    }

    override func draw(_ dirtyRect: NSRect) {
        NSColor(calibratedRed: 0.075, green: 0.083, blue: 0.095, alpha: 1).setFill()
        dirtyRect.fill()
        drawText("16-step rack", in: NSRect(x: 0, y: 0, width: 120, height: 20), color: Palette.muted, size: 11, weight: .bold)

        let stepSize: CGFloat = 20
        let stepGap: CGFloat = 7
        for step in 0..<16 {
            let x = nameWidth + CGFloat(step) * (stepSize + stepGap)
            drawText("\(step + 1)", in: NSRect(x: x, y: 6, width: stepSize, height: 16), color: Palette.dim, size: 9, weight: .bold, alignment: .center)
        }

        for (index, track) in tracks.enumerated() {
            let y = 30 + CGFloat(index) * rowHeight
            let rowRect = NSRect(x: 0, y: y, width: bounds.width, height: rowHeight - 4)
            roundedFill(rowRect, radius: 6, color: index.isMultiple(of: 2) ? Palette.panel : Palette.panelAlt)
            let trackColor = color(from: track.color, fallback: Palette.blue)
            roundedFill(NSRect(x: 10, y: y + 10, width: 9, height: 9), radius: 2, color: trackColor)
            drawText(track.name, in: NSRect(x: 26, y: y + 7, width: nameWidth - 30, height: 16), color: Palette.text, size: 11, weight: .bold)

            let activeSteps = Set((track.steps ?? []).map { (($0 % 16) + 16) % 16 })
            for step in 0..<16 {
                let x = nameWidth + CGFloat(step) * (stepSize + stepGap)
                let rect = NSRect(x: x, y: y + 7, width: stepSize, height: 18)
                let active = activeSteps.contains(step)
                roundedFill(rect, radius: 4, color: active ? trackColor : NSColor(calibratedRed: 0.155, green: 0.165, blue: 0.18, alpha: 1))
                if active {
                    roundedStroke(rect.insetBy(dx: 0.5, dy: 0.5), radius: 4, color: NSColor.white.withAlphaComponent(0.18))
                }
            }
        }
    }
}

final class PlaylistView: NSView {
    var tracks: [Track] = [] {
        didSet {
            totalBars = max(64, ceil(maxClipEnd()) + 8)
            invalidateIntrinsicContentSize()
            needsDisplay = true
        }
    }

    private var totalBars: Double = 72
    private let leftWidth: CGFloat = 142
    private let rulerHeight: CGFloat = 34
    private let rowHeight: CGFloat = 50
    private let pixelsPerBar: CGFloat = 38

    override var isFlipped: Bool { true }
    override var intrinsicContentSize: NSSize {
        NSSize(
            width: max(1280, leftWidth + CGFloat(totalBars) * pixelsPerBar + 24),
            height: max(470, rulerHeight + CGFloat(max(tracks.count, 8)) * rowHeight + 26)
        )
    }

    private func maxClipEnd() -> Double {
        tracks
            .flatMap { $0.clips ?? [] }
            .map { ($0.startBar ?? 0) + ($0.bars ?? 0) }
            .max() ?? 64
    }

    override func draw(_ dirtyRect: NSRect) {
        NSColor(calibratedRed: 0.065, green: 0.073, blue: 0.083, alpha: 1).setFill()
        dirtyRect.fill()

        roundedFill(NSRect(x: 0, y: 0, width: leftWidth, height: bounds.height), radius: 0, color: Palette.panel)
        roundedFill(NSRect(x: leftWidth, y: 0, width: bounds.width - leftWidth, height: rulerHeight), radius: 0, color: Palette.panelAlt)

        for bar in 0...Int(totalBars) {
            let x = leftWidth + CGFloat(bar) * pixelsPerBar
            let path = NSBezierPath()
            path.move(to: NSPoint(x: x, y: 0))
            path.line(to: NSPoint(x: x, y: bounds.height))
            let isMajor = bar % 4 == 0
            (isMajor ? Palette.stroke : Palette.subtleStroke).setStroke()
            path.lineWidth = isMajor ? 1 : 0.6
            path.stroke()

            if isMajor && bar < Int(totalBars) {
                drawText("\(bar + 1)", in: NSRect(x: x + 6, y: 9, width: 42, height: 16), color: Palette.muted, size: 10, weight: .black)
            }
        }

        let sectionNames = ["Intro", "Pre", "Drop 1", "Break", "Build", "Drop 2", "Outro"]
        for (index, name) in sectionNames.enumerated() {
            let start = leftWidth + CGFloat(index * 8) * pixelsPerBar
            let rect = NSRect(x: start, y: 0, width: 8 * pixelsPerBar, height: 4)
            let tint: NSColor = index.isMultiple(of: 2) ? Palette.blue.withAlphaComponent(0.55) : Palette.yellow.withAlphaComponent(0.65)
            tint.setFill()
            rect.fill()
            drawText(name, in: NSRect(x: start + 8, y: 17, width: 70, height: 14), color: Palette.dim, size: 9, weight: .bold)
        }

        for (index, track) in tracks.enumerated() {
            let y = rulerHeight + CGFloat(index) * rowHeight
            let rowRect = NSRect(x: 0, y: y, width: bounds.width, height: rowHeight)
            (index.isMultiple(of: 2)
             ? NSColor(calibratedRed: 0.078, green: 0.087, blue: 0.098, alpha: 1)
             : NSColor(calibratedRed: 0.092, green: 0.101, blue: 0.113, alpha: 1)).setFill()
            rowRect.fill()

            Palette.subtleStroke.setStroke()
            let line = NSBezierPath()
            line.move(to: NSPoint(x: 0, y: y))
            line.line(to: NSPoint(x: bounds.width, y: y))
            line.lineWidth = 1
            line.stroke()

            drawText(track.name, in: NSRect(x: 14, y: y + 10, width: leftWidth - 38, height: 16), color: Palette.text, size: 11, weight: .black)
            let meta = track.instrument ?? track.kind ?? "Track"
            drawText(meta, in: NSRect(x: 14, y: y + 27, width: leftWidth - 38, height: 14), color: Palette.dim, size: 9, weight: .semibold)
            roundedFill(NSRect(x: leftWidth - 20, y: y + 20, width: 8, height: 8), radius: 2, color: color(from: track.color))

            for clip in track.clips ?? [] {
                let start = clip.startBar ?? 0
                let bars = clip.bars ?? 1
                let clipX = leftWidth + CGFloat(start) * pixelsPerBar + 5
                let clipWidth = max(34, CGFloat(bars) * pixelsPerBar - 10)
                let clipRect = NSRect(x: clipX, y: y + 7, width: clipWidth, height: rowHeight - 14)
                let clipColor = color(from: clip.color ?? track.color, fallback: Palette.blue)
                roundedFill(clipRect, radius: 5, color: clipColor.withAlphaComponent(0.86))
                roundedStroke(clipRect, radius: 5, color: NSColor.white.withAlphaComponent(0.18))

                let textColor: NSColor = clipColor.brightnessComponent > 0.58 ? NSColor(calibratedWhite: 0.06, alpha: 1) : NSColor.white
                drawText(clip.name, in: clipRect.insetBy(dx: 9, dy: 6), color: textColor, size: 10, weight: .black)

                if (clip.type ?? "audio") == "audio" {
                    drawWaveform(in: clipRect.insetBy(dx: 8, dy: 22), color: textColor.withAlphaComponent(0.35), seed: clip.id.hashValue)
                } else {
                    drawPatternDots(in: clipRect.insetBy(dx: 8, dy: 22), color: textColor.withAlphaComponent(0.38))
                }
            }
        }
    }

    private func drawWaveform(in rect: NSRect, color: NSColor, seed: Int) {
        guard rect.width > 8, rect.height > 4 else { return }
        color.setStroke()
        let path = NSBezierPath()
        let midY = rect.midY
        var x = rect.minX
        var index = 0
        while x <= rect.maxX {
            let phase = CGFloat(abs((seed + index * 37) % 100)) / 100
            let height = max(2, rect.height * (0.25 + phase * 0.7))
            path.move(to: NSPoint(x: x, y: midY - height / 2))
            path.line(to: NSPoint(x: x, y: midY + height / 2))
            x += 5
            index += 1
        }
        path.lineWidth = 1
        path.stroke()
    }

    private func drawPatternDots(in rect: NSRect, color: NSColor) {
        var x = rect.minX
        color.setFill()
        while x < rect.maxX {
            NSBezierPath(ovalIn: NSRect(x: x, y: rect.midY - 2, width: 4, height: 4)).fill()
            x += 12
        }
    }
}

final class MixerView: NSView {
    var tracks: [Track] = [] {
        didSet {
            invalidateIntrinsicContentSize()
            needsDisplay = true
        }
    }

    override var isFlipped: Bool { true }
    override var intrinsicContentSize: NSSize {
        NSSize(width: max(300, CGFloat(tracks.count) * 66 + 20), height: 360)
    }

    override func draw(_ dirtyRect: NSRect) {
        NSColor(calibratedRed: 0.075, green: 0.083, blue: 0.095, alpha: 1).setFill()
        dirtyRect.fill()

        for (index, track) in tracks.enumerated() {
            let x = 10 + CGFloat(index) * 66
            let strip = NSRect(x: x, y: 8, width: 56, height: bounds.height - 16)
            roundedFill(strip, radius: 7, color: index.isMultiple(of: 2) ? Palette.panel : Palette.panelAlt)
            roundedStroke(strip, radius: 7, color: Palette.subtleStroke)
            drawText(String(format: "%02d", index + 1), in: NSRect(x: x + 8, y: 16, width: 40, height: 14), color: Palette.dim, size: 9, weight: .bold, alignment: .center)
            drawText(track.name, in: NSRect(x: x + 8, y: 34, width: 40, height: 38), color: Palette.text, size: 10, weight: .black, alignment: .center, lineBreak: .byWordWrapping)

            let meter = NSRect(x: x + 10, y: 86, width: 8, height: 160)
            roundedFill(meter, radius: 3, color: NSColor(calibratedRed: 0.08, green: 0.09, blue: 0.10, alpha: 1))
            let gain = CGFloat(max(0.05, min(track.gain ?? 0.7, 1.2))) / 1.2
            let fill = NSRect(x: meter.minX, y: meter.maxY - meter.height * gain, width: meter.width, height: meter.height * gain)
            roundedFill(fill, radius: 3, color: color(from: track.color, fallback: Palette.green))

            let faderTrack = NSRect(x: x + 31, y: 86, width: 6, height: 160)
            roundedFill(faderTrack, radius: 3, color: NSColor(calibratedRed: 0.08, green: 0.09, blue: 0.10, alpha: 1))
            let faderY = faderTrack.maxY - faderTrack.height * gain
            roundedFill(NSRect(x: x + 24, y: faderY - 4, width: 20, height: 8), radius: 3, color: Palette.text)

            let pan = track.pan ?? 0
            let panLabel = pan == 0 ? "C" : String(format: "%+.1f", pan)
            drawText(panLabel, in: NSRect(x: x + 8, y: 260, width: 40, height: 14), color: Palette.muted, size: 9, weight: .bold, alignment: .center)
            roundedFill(NSRect(x: x + 12, y: 284, width: 32, height: 18), radius: 4, color: color(from: track.color, fallback: Palette.blue).withAlphaComponent(0.8))
        }
    }
}

final class AutomationScopeView: NSView {
    var project: LocalProject? {
        didSet { needsDisplay = true }
    }

    override var isFlipped: Bool { true }

    override func draw(_ dirtyRect: NSRect) {
        NSColor(calibratedRed: 0.075, green: 0.083, blue: 0.095, alpha: 1).setFill()
        dirtyRect.fill()

        let left = bounds.insetBy(dx: 14, dy: 12)
        let scopeRect = NSRect(x: left.minX, y: left.minY, width: left.width * 0.42, height: left.height)
        let automationRect = NSRect(x: scopeRect.maxX + 18, y: left.minY, width: left.width - scopeRect.width - 18, height: left.height)

        drawText("Master scope", in: NSRect(x: scopeRect.minX, y: scopeRect.minY, width: scopeRect.width, height: 18), color: Palette.text, size: 12, weight: .black)
        roundedFill(NSRect(x: scopeRect.minX, y: scopeRect.minY + 28, width: scopeRect.width, height: scopeRect.height - 28), radius: 7, color: Palette.panel)
        drawScope(in: NSRect(x: scopeRect.minX + 12, y: scopeRect.minY + 44, width: scopeRect.width - 24, height: scopeRect.height - 58))

        drawText("Automation lanes", in: NSRect(x: automationRect.minX, y: automationRect.minY, width: automationRect.width, height: 18), color: Palette.text, size: 12, weight: .black)
        let box = NSRect(x: automationRect.minX, y: automationRect.minY + 28, width: automationRect.width, height: automationRect.height - 28)
        roundedFill(box, radius: 7, color: Palette.panel)
        drawAutomation(in: box.insetBy(dx: 14, dy: 14))
    }

    private func drawScope(in rect: NSRect) {
        Palette.subtleStroke.setStroke()
        for i in 0..<6 {
            let y = rect.minY + CGFloat(i) * rect.height / 5
            let line = NSBezierPath()
            line.move(to: NSPoint(x: rect.minX, y: y))
            line.line(to: NSPoint(x: rect.maxX, y: y))
            line.lineWidth = 0.7
            line.stroke()
        }

        let path = NSBezierPath()
        let points = 84
        for i in 0..<points {
            let t = CGFloat(i) / CGFloat(points - 1)
            let x = rect.minX + t * rect.width
            let wave = sin(t * CGFloat.pi * 8) * 0.35 + sin(t * CGFloat.pi * 21) * 0.12
            let y = rect.midY + wave * rect.height * 0.42
            if i == 0 {
                path.move(to: NSPoint(x: x, y: y))
            } else {
                path.line(to: NSPoint(x: x, y: y))
            }
        }
        Palette.blue.setStroke()
        path.lineWidth = 2
        path.stroke()
    }

    private func drawAutomation(in rect: NSRect) {
        Palette.subtleStroke.setStroke()
        for i in 0..<5 {
            let x = rect.minX + CGFloat(i) * rect.width / 4
            let line = NSBezierPath()
            line.move(to: NSPoint(x: x, y: rect.minY))
            line.line(to: NSPoint(x: x, y: rect.maxY))
            line.lineWidth = 0.7
            line.stroke()
        }

        let path = NSBezierPath()
        path.move(to: NSPoint(x: rect.minX, y: rect.maxY - rect.height * 0.18))
        path.curve(
            to: NSPoint(x: rect.minX + rect.width * 0.38, y: rect.minY + rect.height * 0.18),
            controlPoint1: NSPoint(x: rect.minX + rect.width * 0.10, y: rect.maxY - rect.height * 0.10),
            controlPoint2: NSPoint(x: rect.minX + rect.width * 0.25, y: rect.minY + rect.height * 0.22)
        )
        path.curve(
            to: NSPoint(x: rect.maxX, y: rect.minY + rect.height * 0.32),
            controlPoint1: NSPoint(x: rect.minX + rect.width * 0.58, y: rect.maxY - rect.height * 0.08),
            controlPoint2: NSPoint(x: rect.minX + rect.width * 0.82, y: rect.minY + rect.height * 0.42)
        )
        Palette.yellow.setStroke()
        path.lineWidth = 2.5
        path.stroke()

        drawText("filter cut  /  reverb throw  /  sidechain", in: NSRect(x: rect.minX, y: rect.maxY - 18, width: rect.width, height: 14), color: Palette.muted, size: 10, weight: .bold)
    }
}

final class RecipeView: NSView {
    var project: LocalProject? {
        didSet { needsDisplay = true }
    }

    override var isFlipped: Bool { true }

    override func draw(_ dirtyRect: NSRect) {
        NSColor(calibratedRed: 0.075, green: 0.083, blue: 0.095, alpha: 1).setFill()
        dirtyRect.fill()
        guard let project else {
            drawText("Open a project", in: bounds.insetBy(dx: 12, dy: 12), color: Palette.muted, size: 12, weight: .bold)
            return
        }

        let meta = project.keyCenter ?? "Local project"
        drawText(project.name, in: NSRect(x: 0, y: 0, width: bounds.width, height: 20), color: Palette.text, size: 13, weight: .black)
        drawText(meta, in: NSRect(x: 0, y: 22, width: bounds.width, height: 16), color: Palette.muted, size: 11, weight: .semibold)

        let recipe = project.snapshot.recipe ?? []
        let shown = recipe.prefix(5)
        var y: CGFloat = 52
        for item in shown {
            roundedFill(NSRect(x: 0, y: y, width: bounds.width, height: 34), radius: 6, color: Palette.panelAlt)
            roundedFill(NSRect(x: 10, y: y + 12, width: 9, height: 9), radius: 2, color: (item.status == "implemented" ? Palette.green : Palette.yellow))
            drawText(item.label, in: NSRect(x: 28, y: y + 8, width: bounds.width - 36, height: 16), color: Palette.text, size: 10, weight: .bold)
            y += 40
        }
    }
}

final class MainWindowController: NSWindowController {
    private let store: ProjectStore
    private var projects: [LocalProject] = []
    private var currentProject: LocalProject?
    private var players: [AVAudioPlayer] = []
    private var keyMonitor: Any?
    private var isPlaying = false

    private let titleLabel = makeLabel("Neon Studio", size: 26, weight: .black)
    private let subtitleLabel = makeLabel("Native Mac DAW shell", size: 12, weight: .bold, color: Palette.muted)
    private let statusLabel = makeLabel("Ready", size: 11, weight: .bold, color: Palette.muted, mono: true)
    private let projectReadout = ReadoutView(title: "Project", value: "None")
    private let bpmReadout = ReadoutView(title: "BPM", value: "--")
    private let barReadout = ReadoutView(title: "Bars", value: "--")
    private let trackReadout = ReadoutView(title: "Tracks", value: "--")
    private let modeReadout = ReadoutView(title: "Mode", value: "Local")
    private let browserView = BrowserProjectsView()
    private let channelRackView = ChannelRackView()
    private let playlistView = PlaylistView()
    private let mixerView = MixerView()
    private let automationScopeView = AutomationScopeView()
    private let recipeView = RecipeView()
    private lazy var playButton = ClosureButton(title: "Play", symbol: "play.fill", primary: true) { [weak self] in
        self?.togglePlayback()
    }

    init(store: ProjectStore) {
        self.store = store
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1380, height: 830),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.title = "Neon Studio"
        window.minSize = NSSize(width: 1120, height: 680)
        window.appearance = NSAppearance(named: .darkAqua)
        window.titlebarAppearsTransparent = true
        super.init(window: window)
        window.contentView = makeRootView()
        installKeyboardMonitor()
        loadProjects()
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    deinit {
        if let keyMonitor {
            NSEvent.removeMonitor(keyMonitor)
        }
    }

    private func makeRootView() -> NSView {
        let root = NSView()
        root.wantsLayer = true
        root.layer?.backgroundColor = Palette.app.cgColor

        let header = makeHeader()
        let body = makeBody()
        header.translatesAutoresizingMaskIntoConstraints = false
        body.translatesAutoresizingMaskIntoConstraints = false
        root.addSubview(header)
        root.addSubview(body)

        NSLayoutConstraint.activate([
            header.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            header.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            header.topAnchor.constraint(equalTo: root.topAnchor),
            header.heightAnchor.constraint(equalToConstant: 104),

            body.leadingAnchor.constraint(equalTo: root.leadingAnchor, constant: 10),
            body.trailingAnchor.constraint(equalTo: root.trailingAnchor, constant: -10),
            body.topAnchor.constraint(equalTo: header.bottomAnchor, constant: 10),
            body.bottomAnchor.constraint(equalTo: root.bottomAnchor, constant: -10)
        ])

        return root
    }

    private func makeHeader() -> NSView {
        let header = NSView()
        header.wantsLayer = true
        header.layer?.backgroundColor = NSColor(calibratedRed: 0.105, green: 0.115, blue: 0.128, alpha: 1).cgColor

        let logo = LogoView()
        logo.translatesAutoresizingMaskIntoConstraints = false

        let titleStack = NSStackView(views: [titleLabel, subtitleLabel, statusLabel])
        titleStack.orientation = .vertical
        titleStack.alignment = .leading
        titleStack.spacing = 3
        titleStack.translatesAutoresizingMaskIntoConstraints = false

        let undo = ClosureButton(title: "Undo", symbol: "arrow.uturn.backward") { [weak self] in
            self?.statusLabel.stringValue = "Undo stack ready for project edits"
        }
        let redo = ClosureButton(title: "Redo", symbol: "arrow.uturn.forward") { [weak self] in
            self?.statusLabel.stringValue = "Redo stack ready for project edits"
        }
        let rewind = ClosureButton(title: "Start", symbol: "backward.end.fill") { [weak self] in
            self?.stop()
            self?.statusLabel.stringValue = "Returned to bar 1"
        }
        let record = ClosureButton(title: "Rec", symbol: "record.circle") { [weak self] in
            self?.statusLabel.stringValue = "Recording input is routed through Vocal Lab"
            self?.showVocalLabNotice()
        }
        let help = ClosureButton(title: "Help", symbol: "questionmark.circle") { [weak self] in
            self?.showHelp()
        }

        [undo, redo, rewind, playButton, record, help].forEach { button in
            button.heightAnchor.constraint(equalToConstant: 44).isActive = true
            button.widthAnchor.constraint(greaterThanOrEqualToConstant: button === playButton ? 92 : 78).isActive = true
        }

        let controls = NSStackView(views: [undo, redo, rewind, playButton, record, help])
        controls.orientation = .horizontal
        controls.alignment = .centerY
        controls.spacing = 8
        controls.translatesAutoresizingMaskIntoConstraints = false

        let readouts = NSStackView(views: [projectReadout, bpmReadout, barReadout, trackReadout, modeReadout])
        readouts.orientation = .horizontal
        readouts.alignment = .centerY
        readouts.spacing = 8
        readouts.translatesAutoresizingMaskIntoConstraints = false

        header.addSubview(logo)
        header.addSubview(titleStack)
        header.addSubview(readouts)
        header.addSubview(controls)

        NSLayoutConstraint.activate([
            logo.leadingAnchor.constraint(equalTo: header.leadingAnchor, constant: 18),
            logo.centerYAnchor.constraint(equalTo: header.centerYAnchor),
            logo.widthAnchor.constraint(equalToConstant: 50),
            logo.heightAnchor.constraint(equalToConstant: 50),

            titleStack.leadingAnchor.constraint(equalTo: logo.trailingAnchor, constant: 16),
            titleStack.centerYAnchor.constraint(equalTo: header.centerYAnchor, constant: 2),
            titleStack.widthAnchor.constraint(greaterThanOrEqualToConstant: 240),

            controls.trailingAnchor.constraint(equalTo: header.trailingAnchor, constant: -18),
            controls.centerYAnchor.constraint(equalTo: header.centerYAnchor, constant: 2),

            readouts.leadingAnchor.constraint(equalTo: titleStack.trailingAnchor, constant: 26),
            readouts.trailingAnchor.constraint(lessThanOrEqualTo: controls.leadingAnchor, constant: -24),
            readouts.centerYAnchor.constraint(equalTo: header.centerYAnchor, constant: 2)
        ])

        return header
    }

    private func makeBody() -> NSView {
        let split = NSSplitView()
        split.isVertical = true
        split.dividerStyle = .thin
        split.translatesAutoresizingMaskIntoConstraints = false
        split.wantsLayer = true
        split.layer?.backgroundColor = Palette.app.cgColor

        let left = makeLeftColumn()
        let center = makeCenterColumn()
        let right = makeRightColumn()

        split.addArrangedSubview(left)
        split.addArrangedSubview(center)
        split.addArrangedSubview(right)

        left.widthAnchor.constraint(equalToConstant: 318).isActive = true
        right.widthAnchor.constraint(equalToConstant: 318).isActive = true

        return split
    }

    private func makeLeftColumn() -> NSView {
        let stack = NSStackView()
        stack.orientation = .vertical
        stack.alignment = .width
        stack.distribution = .fill
        stack.spacing = 10
        stack.translatesAutoresizingMaskIntoConstraints = false

        let browserPanel = TitledPanel(title: "Browser", accessory: "Local")
        let browserScroll = NSScrollView()
        browserScroll.documentView = browserView
        browserScroll.hasVerticalScroller = true
        browserScroll.drawsBackground = false
        browserScroll.translatesAutoresizingMaskIntoConstraints = false
        browserPanel.contentGuide.addSubview(browserScroll)
        NSLayoutConstraint.activate([
            browserScroll.leadingAnchor.constraint(equalTo: browserPanel.contentGuide.leadingAnchor),
            browserScroll.trailingAnchor.constraint(equalTo: browserPanel.contentGuide.trailingAnchor),
            browserScroll.topAnchor.constraint(equalTo: browserPanel.contentGuide.topAnchor),
            browserScroll.bottomAnchor.constraint(equalTo: browserPanel.contentGuide.bottomAnchor)
        ])
        browserPanel.heightAnchor.constraint(equalToConstant: 270).isActive = true

        let rackPanel = TitledPanel(title: "Channel Rack", accessory: "P01")
        let rackScroll = NSScrollView()
        rackScroll.documentView = channelRackView
        rackScroll.hasVerticalScroller = true
        rackScroll.hasHorizontalScroller = true
        rackScroll.autohidesScrollers = false
        rackScroll.drawsBackground = false
        rackScroll.translatesAutoresizingMaskIntoConstraints = false
        rackPanel.contentGuide.addSubview(rackScroll)
        NSLayoutConstraint.activate([
            rackScroll.leadingAnchor.constraint(equalTo: rackPanel.contentGuide.leadingAnchor),
            rackScroll.trailingAnchor.constraint(equalTo: rackPanel.contentGuide.trailingAnchor),
            rackScroll.topAnchor.constraint(equalTo: rackPanel.contentGuide.topAnchor),
            rackScroll.bottomAnchor.constraint(equalTo: rackPanel.contentGuide.bottomAnchor)
        ])

        stack.addArrangedSubview(browserPanel)
        stack.addArrangedSubview(rackPanel)
        return stack
    }

    private func makeCenterColumn() -> NSView {
        let stack = NSStackView()
        stack.orientation = .vertical
        stack.alignment = .width
        stack.distribution = .fill
        stack.spacing = 10
        stack.translatesAutoresizingMaskIntoConstraints = false

        let toolbar = makePlaylistToolbar()
        toolbar.heightAnchor.constraint(equalToConstant: 54).isActive = true

        let playlistPanel = TitledPanel(title: "Playlist", accessory: "Arrangement")
        let playlistScroll = NSScrollView()
        playlistScroll.documentView = playlistView
        playlistScroll.hasVerticalScroller = true
        playlistScroll.hasHorizontalScroller = true
        playlistScroll.autohidesScrollers = false
        playlistScroll.drawsBackground = false
        playlistScroll.translatesAutoresizingMaskIntoConstraints = false
        playlistPanel.contentGuide.addSubview(playlistScroll)
        NSLayoutConstraint.activate([
            playlistScroll.leadingAnchor.constraint(equalTo: playlistPanel.contentGuide.leadingAnchor),
            playlistScroll.trailingAnchor.constraint(equalTo: playlistPanel.contentGuide.trailingAnchor),
            playlistScroll.topAnchor.constraint(equalTo: playlistPanel.contentGuide.topAnchor),
            playlistScroll.bottomAnchor.constraint(equalTo: playlistPanel.contentGuide.bottomAnchor)
        ])

        let scopePanel = TitledPanel(title: "Automation + Scope", accessory: "Live")
        automationScopeView.translatesAutoresizingMaskIntoConstraints = false
        scopePanel.contentGuide.addSubview(automationScopeView)
        NSLayoutConstraint.activate([
            automationScopeView.leadingAnchor.constraint(equalTo: scopePanel.contentGuide.leadingAnchor),
            automationScopeView.trailingAnchor.constraint(equalTo: scopePanel.contentGuide.trailingAnchor),
            automationScopeView.topAnchor.constraint(equalTo: scopePanel.contentGuide.topAnchor),
            automationScopeView.bottomAnchor.constraint(equalTo: scopePanel.contentGuide.bottomAnchor)
        ])
        scopePanel.heightAnchor.constraint(equalToConstant: 182).isActive = true

        stack.addArrangedSubview(toolbar)
        stack.addArrangedSubview(playlistPanel)
        stack.addArrangedSubview(scopePanel)
        return stack
    }

    private func makePlaylistToolbar() -> NSView {
        let toolbar = NSView()
        toolbar.wantsLayer = true
        toolbar.layer?.backgroundColor = Palette.panel.cgColor
        toolbar.layer?.borderColor = Palette.stroke.cgColor
        toolbar.layer?.borderWidth = 1
        toolbar.layer?.cornerRadius = 8
        toolbar.translatesAutoresizingMaskIntoConstraints = false

        let tools = [
            ("Select", "cursorarrow"),
            ("Draw", "pencil"),
            ("Brush", "paintbrush"),
            ("Split", "scissors"),
            ("Mute", "speaker.slash"),
            ("Zoom", "plus.magnifyingglass")
        ].map { title, symbol in
            ClosureButton(title: title, symbol: symbol) { [weak self] in
                self?.statusLabel.stringValue = "\(title) tool selected"
            }
        }

        tools.forEach { button in
            button.heightAnchor.constraint(equalToConstant: 34).isActive = true
        }

        let stack = NSStackView(views: tools)
        stack.orientation = .horizontal
        stack.spacing = 8
        stack.alignment = .centerY
        stack.translatesAutoresizingMaskIntoConstraints = false

        let snap = makeLabel("Snap: 1/4   Loop: On   Scroll: vertical + horizontal", size: 11, weight: .bold, color: Palette.muted, mono: true)

        toolbar.addSubview(stack)
        toolbar.addSubview(snap)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: toolbar.leadingAnchor, constant: 12),
            stack.centerYAnchor.constraint(equalTo: toolbar.centerYAnchor),
            snap.trailingAnchor.constraint(equalTo: toolbar.trailingAnchor, constant: -14),
            snap.centerYAnchor.constraint(equalTo: toolbar.centerYAnchor),
            snap.leadingAnchor.constraint(greaterThanOrEqualTo: stack.trailingAnchor, constant: 14)
        ])
        return toolbar
    }

    private func makeRightColumn() -> NSView {
        let stack = NSStackView()
        stack.orientation = .vertical
        stack.alignment = .width
        stack.distribution = .fill
        stack.spacing = 10
        stack.translatesAutoresizingMaskIntoConstraints = false

        let mixerPanel = TitledPanel(title: "Mixer", accessory: "Bus")
        let mixerScroll = NSScrollView()
        mixerScroll.documentView = mixerView
        mixerScroll.hasHorizontalScroller = true
        mixerScroll.hasVerticalScroller = true
        mixerScroll.autohidesScrollers = false
        mixerScroll.drawsBackground = false
        mixerScroll.translatesAutoresizingMaskIntoConstraints = false
        mixerPanel.contentGuide.addSubview(mixerScroll)
        NSLayoutConstraint.activate([
            mixerScroll.leadingAnchor.constraint(equalTo: mixerPanel.contentGuide.leadingAnchor),
            mixerScroll.trailingAnchor.constraint(equalTo: mixerPanel.contentGuide.trailingAnchor),
            mixerScroll.topAnchor.constraint(equalTo: mixerPanel.contentGuide.topAnchor),
            mixerScroll.bottomAnchor.constraint(equalTo: mixerPanel.contentGuide.bottomAnchor)
        ])

        let projectPanel = TitledPanel(title: "Project", accessory: "Portable")
        recipeView.translatesAutoresizingMaskIntoConstraints = false
        projectPanel.contentGuide.addSubview(recipeView)

        let vocal = ClosureButton(title: "Vocal Lab", symbol: "waveform.badge.mic") { [weak self] in
            self?.showVocalLabNotice()
        }
        let reveal = ClosureButton(title: "Reveal JSON", symbol: "doc.text.magnifyingglass") { [weak self] in
            self?.revealCurrentProject()
        }
        vocal.heightAnchor.constraint(equalToConstant: 34).isActive = true
        reveal.heightAnchor.constraint(equalToConstant: 34).isActive = true

        let actions = NSStackView(views: [vocal, reveal])
        actions.orientation = .horizontal
        actions.alignment = .centerY
        actions.spacing = 8
        actions.translatesAutoresizingMaskIntoConstraints = false
        projectPanel.contentGuide.addSubview(actions)

        NSLayoutConstraint.activate([
            recipeView.leadingAnchor.constraint(equalTo: projectPanel.contentGuide.leadingAnchor),
            recipeView.trailingAnchor.constraint(equalTo: projectPanel.contentGuide.trailingAnchor),
            recipeView.topAnchor.constraint(equalTo: projectPanel.contentGuide.topAnchor),
            recipeView.bottomAnchor.constraint(equalTo: actions.topAnchor, constant: -8),
            actions.leadingAnchor.constraint(equalTo: projectPanel.contentGuide.leadingAnchor),
            actions.trailingAnchor.constraint(equalTo: projectPanel.contentGuide.trailingAnchor),
            actions.bottomAnchor.constraint(equalTo: projectPanel.contentGuide.bottomAnchor)
        ])
        projectPanel.heightAnchor.constraint(equalToConstant: 290).isActive = true

        stack.addArrangedSubview(mixerPanel)
        stack.addArrangedSubview(projectPanel)
        return stack
    }

    private func loadProjects() {
        projects = store.loadProjects()
        browserView.projects = projects
        browserView.setFrameSize(browserView.intrinsicContentSize)
        browserView.onProjectSelected = { [weak self] project in
            self?.open(project)
        }

        if let first = projects.first {
            open(first)
        } else {
            statusLabel.stringValue = "No .neon.json projects found at \(store.rootURL.path)"
        }
    }

    private func open(_ project: LocalProject) {
        stop(updateStatus: false)
        currentProject = project
        browserView.selectedId = project.id
        titleLabel.stringValue = project.name

        let itemCount = project.snapshot.recipe?.count ?? 0
        subtitleLabel.stringValue = "\(Int(project.snapshot.bpm)) BPM  \(project.snapshot.tracks.count) tracks  \(itemCount) recipe items"
        projectReadout.value = project.name
        bpmReadout.value = "\(Int(project.snapshot.bpm))"
        let totalBars = Int(maxClipEnd(project))
        barReadout.value = "\(totalBars)"
        trackReadout.value = "\(project.snapshot.tracks.count)"
        modeReadout.value = project.keyCenter ?? "Local"

        channelRackView.tracks = project.snapshot.tracks
        channelRackView.setFrameSize(channelRackView.intrinsicContentSize)
        playlistView.tracks = project.snapshot.tracks
        playlistView.setFrameSize(playlistView.intrinsicContentSize)
        mixerView.tracks = project.snapshot.tracks
        mixerView.setFrameSize(mixerView.intrinsicContentSize)
        automationScopeView.project = project
        recipeView.project = project

        statusLabel.stringValue = "Opened \(project.name)"
    }

    private func maxClipEnd(_ project: LocalProject) -> Double {
        project.snapshot.tracks
            .flatMap { $0.clips ?? [] }
            .map { ($0.startBar ?? 0) + ($0.bars ?? 0) }
            .max() ?? 64
    }

    private func togglePlayback() {
        isPlaying ? stop() : play()
    }

    private func play() {
        guard let project = currentProject else {
            statusLabel.stringValue = "Open a project first"
            return
        }

        stop(updateStatus: false)
        for track in project.snapshot.tracks {
            guard let url = store.audioURL(for: track),
                  FileManager.default.fileExists(atPath: url.path) else {
                continue
            }

            do {
                let player = try AVAudioPlayer(contentsOf: url)
                player.volume = Float(max(0, min(track.gain ?? 0.75, 1.4)))
                player.pan = Float(max(-1, min(track.pan ?? 0, 1)))
                player.prepareToPlay()
                player.play()
                players.append(player)
            } catch {
                statusLabel.stringValue = "Could not play \(track.name)"
            }
        }

        isPlaying = !players.isEmpty
        playButton.title = isPlaying ? "Stop" : "Play"
        playButton.image = NSImage(systemSymbolName: isPlaying ? "stop.fill" : "play.fill", accessibilityDescription: playButton.title)
        statusLabel.stringValue = players.isEmpty ? "No audio stems found" : "Playing \(players.count) stems"
    }

    private func stop(updateStatus: Bool = true) {
        players.forEach { player in
            player.stop()
            player.currentTime = 0
        }
        players.removeAll()
        isPlaying = false
        playButton.title = "Play"
        playButton.image = NSImage(systemSymbolName: "play.fill", accessibilityDescription: "Play")
        if updateStatus, currentProject != nil {
            statusLabel.stringValue = "Stopped"
        }
    }

    private func revealCurrentProject() {
        guard let project = currentProject else { return }
        let paths = [
            store.rootURL.appendingPathComponent("data/projects/\(project.id).neon.json"),
            store.rootURL.appendingPathComponent("public/projects/\(project.id).neon.json")
        ]
        if let url = paths.first(where: { FileManager.default.fileExists(atPath: $0.path) }) {
            NSWorkspace.shared.activateFileViewerSelecting([url])
            statusLabel.stringValue = "Revealed \(url.lastPathComponent)"
        } else {
            statusLabel.stringValue = "Project JSON not found on disk"
        }
    }

    private func showVocalLabNotice() {
        let alert = NSAlert()
        alert.messageText = "Vocal Lab"
        alert.informativeText = "The web app has the automatic vocal upload/tune flow. This native shell loads the same projects and stems; the next native step is wiring the same Python vocal processor into this panel."
        alert.addButton(withTitle: "OK")
        alert.runModal()
    }

    private func showHelp() {
        let alert = NSAlert()
        alert.messageText = "Neon Studio Shortcuts"
        alert.informativeText = """
        Space: Play or stop
        Cmd+H: Open this help menu
        Cmd+R: Return to bar 1
        Cmd+Z / Shift+Cmd+Z: Undo and redo placeholders

        Panels use native split dividers, and the playlist, mixer, and channel rack scroll vertically and horizontally.
        """
        alert.addButton(withTitle: "OK")
        alert.runModal()
    }

    private func installKeyboardMonitor() {
        keyMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
            guard let self else { return event }
            let key = event.charactersIgnoringModifiers?.lowercased() ?? ""
            let flags = event.modifierFlags.intersection(.deviceIndependentFlagsMask)

            if flags.contains(.command), key == "h" {
                self.showHelp()
                return nil
            }
            if flags.contains(.command), key == "r" {
                self.stop()
                self.statusLabel.stringValue = "Returned to bar 1"
                return nil
            }
            if flags.contains(.command), key == "z" {
                self.statusLabel.stringValue = flags.contains(.shift) ? "Redo stack ready for project edits" : "Undo stack ready for project edits"
                return nil
            }
            if event.keyCode == 49 {
                self.togglePlayback()
                return nil
            }
            return event
        }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var windowController: MainWindowController?

    func applicationDidFinishLaunching(_ notification: Notification) {
        installMenu()
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

    private func installMenu() {
        let mainMenu = NSMenu()
        let appMenuItem = NSMenuItem()
        mainMenu.addItem(appMenuItem)

        let appMenu = NSMenu()
        appMenu.addItem(NSMenuItem(title: "Quit Neon Studio", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"))
        appMenuItem.submenu = appMenu

        let helpMenuItem = NSMenuItem()
        mainMenu.addItem(helpMenuItem)
        let helpMenu = NSMenu(title: "Help")
        let help = NSMenuItem(title: "Neon Studio Help", action: #selector(showMenuHelp(_:)), keyEquivalent: "h")
        help.keyEquivalentModifierMask = [.command]
        help.target = self
        helpMenu.addItem(help)
        helpMenuItem.submenu = helpMenu
        NSApp.mainMenu = mainMenu
    }

    @objc private func showMenuHelp(_ sender: Any?) {
        guard let controller = windowController else { return }
        controller.window?.makeKeyAndOrderFront(nil)
        let event = NSEvent.keyEvent(
            with: .keyDown,
            location: .zero,
            modifierFlags: [.command],
            timestamp: 0,
            windowNumber: controller.window?.windowNumber ?? 0,
            context: nil,
            characters: "h",
            charactersIgnoringModifiers: "h",
            isARepeat: false,
            keyCode: 4
        )
        if let event {
            NSApp.postEvent(event, atStart: true)
        }
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
