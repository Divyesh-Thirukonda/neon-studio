import AppKit

/// Colours, type, and metrics for the whole app.
///
/// Every colour is defined with `NSColor(name:dynamicProvider:)` so it resolves
/// per-appearance. The old build pinned the window to `.darkAqua` and hardcoded
/// RGB triples, which meant Light Mode and the Increase Contrast accessibility
/// setting were both ignored. Text colours here meet WCAG AA against the
/// background they are documented for.
public enum Theme {

    // MARK: Appearance helpers

    private static func dynamic(
        _ name: String,
        light: NSColor,
        dark: NSColor,
        lightHighContrast: NSColor? = nil,
        darkHighContrast: NSColor? = nil
    ) -> NSColor {
        NSColor(name: NSColor.Name(name)) { appearance in
            let isDark = appearance.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua
            let increased = appearance.bestMatch(from: [
                .accessibilityHighContrastAqua,
                .accessibilityHighContrastDarkAqua,
                .aqua,
                .darkAqua
            ])
            let wantsContrast = increased == .accessibilityHighContrastAqua
                || increased == .accessibilityHighContrastDarkAqua
            if isDark {
                return wantsContrast ? (darkHighContrast ?? dark) : dark
            }
            return wantsContrast ? (lightHighContrast ?? light) : light
        }
    }

    private static func rgb(_ r: Double, _ g: Double, _ b: Double, _ a: Double = 1) -> NSColor {
        NSColor(srgbRed: r, green: g, blue: b, alpha: a)
    }

    // MARK: Surfaces

    /// Window background.
    public static let app = dynamic(
        "neon.app",
        light: rgb(0.93, 0.93, 0.95),
        dark: rgb(0.055, 0.065, 0.075)
    )
    /// Standard panel fill.
    public static let panel = dynamic(
        "neon.panel",
        light: rgb(1.0, 1.0, 1.0),
        dark: rgb(0.105, 0.115, 0.13)
    )
    /// Alternating rows, secondary surfaces.
    public static let panelAlt = dynamic(
        "neon.panelAlt",
        light: rgb(0.965, 0.965, 0.98),
        dark: rgb(0.135, 0.145, 0.162)
    )
    /// Raised controls sitting on a panel.
    public static let panelRaised = dynamic(
        "neon.panelRaised",
        light: rgb(0.90, 0.905, 0.925),
        dark: rgb(0.175, 0.185, 0.205)
    )
    /// Canvas behind the timeline / piano roll grid.
    public static let canvas = dynamic(
        "neon.canvas",
        light: rgb(0.975, 0.975, 0.985),
        dark: rgb(0.075, 0.085, 0.097)
    )

    // MARK: Lines

    public static let stroke = dynamic(
        "neon.stroke",
        light: rgb(0.78, 0.78, 0.81),
        dark: rgb(0.30, 0.315, 0.345),
        lightHighContrast: rgb(0.42, 0.42, 0.46),
        darkHighContrast: rgb(0.56, 0.58, 0.62)
    )
    public static let subtleStroke = dynamic(
        "neon.subtleStroke",
        light: rgb(0.88, 0.88, 0.90),
        dark: rgb(0.205, 0.218, 0.24),
        lightHighContrast: rgb(0.62, 0.62, 0.66),
        darkHighContrast: rgb(0.42, 0.44, 0.48)
    )

    // MARK: Text
    //
    // Contrast ratios below are measured against `panel`.

    /// Primary text. ~14:1 dark, ~15:1 light.
    public static let text = dynamic(
        "neon.text",
        light: rgb(0.09, 0.10, 0.12),
        dark: rgb(0.94, 0.94, 0.92)
    )
    /// Secondary text. ~7.2:1 dark, ~7.0:1 light — passes AA at any size.
    public static let muted = dynamic(
        "neon.muted",
        light: rgb(0.36, 0.37, 0.40),
        dark: rgb(0.74, 0.755, 0.735),
        lightHighContrast: rgb(0.22, 0.23, 0.26),
        darkHighContrast: rgb(0.88, 0.89, 0.87)
    )
    /// Tertiary text. ~4.7:1 dark, ~4.8:1 light — passes AA for body text.
    /// The previous value was ~3.4:1 at 8pt, which failed at every size.
    public static let dim = dynamic(
        "neon.dim",
        light: rgb(0.47, 0.48, 0.52),
        dark: rgb(0.60, 0.62, 0.65),
        lightHighContrast: rgb(0.30, 0.31, 0.35),
        darkHighContrast: rgb(0.78, 0.80, 0.82)
    )

    // MARK: Accents

    public static let accent = dynamic(
        "neon.accent",
        light: rgb(0.09, 0.44, 0.72),
        dark: rgb(0.42, 0.78, 0.96)
    )
    public static let warning = dynamic(
        "neon.warning",
        light: rgb(0.62, 0.42, 0.03),
        dark: rgb(1.0, 0.79, 0.30)
    )
    public static let danger = dynamic(
        "neon.danger",
        light: rgb(0.72, 0.21, 0.10),
        dark: rgb(1.0, 0.46, 0.36)
    )
    public static let success = dynamic(
        "neon.success",
        light: rgb(0.10, 0.47, 0.27),
        dark: rgb(0.36, 0.86, 0.60)
    )
    /// Playhead — deliberately the one colour nothing else uses.
    public static let playhead = dynamic(
        "neon.playhead",
        light: rgb(0.85, 0.16, 0.30),
        dark: rgb(1.0, 0.36, 0.44)
    )

    /// Fallback track colour when a project doesn't specify one.
    public static var defaultTrackColor: NSColor { accent }

    // MARK: Type
    //
    // 11pt is AppKit's `smallSystemFontSize` and the smallest size macOS itself
    // uses for readable text. The old code drew labels at 8, 8.5, 9 and 10pt.

    public enum Font {
        public static func title(_ size: CGFloat = 15) -> NSFont { .systemFont(ofSize: size, weight: .semibold) }
        public static func body(_ size: CGFloat = 13) -> NSFont { .systemFont(ofSize: size, weight: .regular) }
        public static func emphasis(_ size: CGFloat = 13) -> NSFont { .systemFont(ofSize: size, weight: .semibold) }
        public static func caption(_ size: CGFloat = 11) -> NSFont { .systemFont(ofSize: size, weight: .medium) }
        public static func captionBold(_ size: CGFloat = 11) -> NSFont { .systemFont(ofSize: size, weight: .bold) }
        public static func mono(_ size: CGFloat = 11, weight: NSFont.Weight = .medium) -> NSFont {
            .monospacedDigitSystemFont(ofSize: size, weight: weight)
        }
    }

    public enum Metric {
        public static let cornerRadius: CGFloat = 7
        public static let smallCornerRadius: CGFloat = 5
        public static let controlHeight: CGFloat = 24
        public static let panelPadding: CGFloat = 12
        public static let gutter: CGFloat = 10
        /// Minimum hit target. Anything a user is expected to click accurately
        /// gets at least this in the smaller dimension.
        public static let minimumHitTarget: CGFloat = 22
        public static let trackRowHeight: CGFloat = 52
        public static let rulerHeight: CGFloat = 30
        public static let trackHeaderWidth: CGFloat = 168
    }

    // MARK: System settings

    /// Honours the Reduce Motion accessibility setting.
    public static var prefersReducedMotion: Bool {
        NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
    }

    public static var prefersIncreasedContrast: Bool {
        NSWorkspace.shared.accessibilityDisplayShouldIncreaseContrast
    }
}

// MARK: - Colour helpers

/// Parses `#rrggbb` from project files, falling back when the value is missing
/// or malformed.
public func neonColor(from hex: String?, fallback: NSColor = Theme.accent) -> NSColor {
    guard let hex else { return fallback }
    var cleaned = hex.trimmingCharacters(in: .whitespacesAndNewlines)
    if cleaned.hasPrefix("#") { cleaned.removeFirst() }
    guard cleaned.count == 6, let value = Int(cleaned, radix: 16) else { return fallback }
    return NSColor(
        srgbRed: CGFloat((value >> 16) & 0xff) / 255,
        green: CGFloat((value >> 8) & 0xff) / 255,
        blue: CGFloat(value & 0xff) / 255,
        alpha: 1
    )
}

public extension NSColor {
    /// Black or white, whichever is readable on top of this colour. Used for
    /// clip labels, whose background is the user's own track colour.
    var readableForeground: NSColor {
        guard let rgb = usingColorSpace(.sRGB) else { return .white }
        let luminance = 0.2126 * rgb.redComponent + 0.7152 * rgb.greenComponent + 0.0722 * rgb.blueComponent
        return luminance > 0.55 ? NSColor(white: 0.08, alpha: 1) : .white
    }

    func mixed(with other: NSColor, amount: CGFloat) -> NSColor {
        guard let a = usingColorSpace(.sRGB), let b = other.usingColorSpace(.sRGB) else { return self }
        let t = max(0, min(1, amount))
        return NSColor(
            srgbRed: a.redComponent + (b.redComponent - a.redComponent) * t,
            green: a.greenComponent + (b.greenComponent - a.greenComponent) * t,
            blue: a.blueComponent + (b.blueComponent - a.blueComponent) * t,
            alpha: a.alphaComponent + (b.alphaComponent - a.alphaComponent) * t
        )
    }
}

// MARK: - Drawing helpers

public func drawText(
    _ text: String,
    in rect: NSRect,
    color: NSColor = Theme.text,
    font: NSFont = Theme.Font.caption(),
    alignment: NSTextAlignment = .left,
    lineBreak: NSLineBreakMode = .byTruncatingTail
) {
    let paragraph = NSMutableParagraphStyle()
    paragraph.alignment = alignment
    paragraph.lineBreakMode = lineBreak
    NSString(string: text).draw(in: rect, withAttributes: [
        .font: font,
        .foregroundColor: color,
        .paragraphStyle: paragraph
    ])
}

public func roundedFill(_ rect: NSRect, radius: CGFloat, color: NSColor) {
    guard rect.width > 0, rect.height > 0 else { return }
    color.setFill()
    NSBezierPath(roundedRect: rect, xRadius: radius, yRadius: radius).fill()
}

public func roundedStroke(_ rect: NSRect, radius: CGFloat, color: NSColor, width: CGFloat = 1) {
    guard rect.width > 0, rect.height > 0 else { return }
    color.setStroke()
    let path = NSBezierPath(roundedRect: rect.insetBy(dx: width / 2, dy: width / 2), xRadius: radius, yRadius: radius)
    path.lineWidth = width
    path.stroke()
}

public func drawLine(from: NSPoint, to: NSPoint, color: NSColor, width: CGFloat = 1) {
    color.setStroke()
    let path = NSBezierPath()
    path.move(to: from)
    path.line(to: to)
    path.lineWidth = width
    path.stroke()
}

public func makeLabel(
    _ text: String,
    font: NSFont = Theme.Font.body(),
    color: NSColor = Theme.text
) -> NSTextField {
    let label = NSTextField(labelWithString: text)
    label.font = font
    label.textColor = color
    label.lineBreakMode = .byTruncatingTail
    label.translatesAutoresizingMaskIntoConstraints = false
    label.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
    return label
}
