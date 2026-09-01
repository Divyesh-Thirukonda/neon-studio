import AppKit
import UniformTypeIdentifiers

// MARK: - Report

/// The result of an analysis or an automated edit, in a form a window can show.
///
/// Sound check and the suggestion agent used to dump their findings into an
/// `NSAlert`: a wall of text nobody could select, copy, scroll, resize, or ever
/// see again once it was dismissed. A report is a small, printable structure
/// instead — a headline, some titled sections of lines, and a plain-text
/// rendering for the clipboard — so the same content can be read at leisure,
/// searched with the eyes, copied into a message, or saved to a file.
public struct Report {

    /// One titled block of findings. `lines` are shown as bullets and are never
    /// pre-formatted with markup; the view owns the presentation.
    public struct Section {
        public let title: String
        public let lines: [String]

        public init(title: String, lines: [String]) {
            self.title = title
            self.lines = lines
        }

        var isEmpty: Bool { lines.isEmpty }
    }

    /// Window title, e.g. "Sound check".
    public let title: String
    /// What the report is about, e.g. the song name.
    public let subtitle: String
    /// The one number or word that answers the question, e.g. "86 / 100".
    public let headline: String?
    /// A sentence under the headline explaining what it means.
    public let headlineCaption: String?
    public let sections: [Section]
    /// Exactly what the Copy button puts on the pasteboard.
    public let plainText: String

    public init(
        title: String,
        subtitle: String,
        headline: String?,
        headlineCaption: String?,
        sections: [Section],
        plainText: String
    ) {
        self.title = title
        self.subtitle = subtitle
        self.headline = headline
        self.headlineCaption = headlineCaption
        self.sections = sections
        self.plainText = plainText
    }
}

// MARK: - ReportBuilder

/// Turns the raw JSON the Python tools print into a `Report`.
///
/// Everything here is defensive: the tools are separate programs that can be
/// updated independently, so a missing key, a renamed key, a string where a
/// number was expected, or an entirely empty object must all produce a readable
/// report rather than a crash or the word "nil" on screen.
public enum ReportBuilder {

    // MARK: Value coercion

    /// Reads an integer out of whatever JSON actually contained.
    ///
    /// `JSONSerialization` hands back `NSNumber`, and a conditional cast to
    /// `Int` fails for a value that was written as `86.0`, which is how the
    /// score arrived as 0 in the old code.
    public static func intValue(_ value: Any?) -> Int {
        switch value {
        case let number as NSNumber:
            let double = number.doubleValue
            return clampToInt(double)
        case let int as Int:
            return int
        case let double as Double:
            return clampToInt(double)
        case let string as String:
            let trimmed = string.trimmingCharacters(in: .whitespacesAndNewlines)
            if let int = Int(trimmed) { return int }
            if let double = Double(trimmed) { return clampToInt(double) }
            return 0
        default:
            return 0
        }
    }

    private static func clampToInt(_ value: Double) -> Int {
        guard value.isFinite else { return 0 }
        let rounded = value.rounded()
        if rounded >= Double(Int.max) { return Int.max }
        if rounded <= Double(Int.min) { return Int.min }
        return Int(rounded)
    }

    /// `nil` for anything that isn't a finite number, including booleans, which
    /// arrive from JSON as `NSNumber` and would otherwise be reported as "1".
    private static func doubleValue(_ value: Any?) -> Double? {
        guard let value else { return nil }
        if isBoolean(value) { return nil }
        switch value {
        case let number as NSNumber:
            return number.doubleValue.isFinite ? number.doubleValue : nil
        case let double as Double:
            return double.isFinite ? double : nil
        case let int as Int:
            return Double(int)
        case let string as String:
            guard let double = Double(string.trimmingCharacters(in: .whitespacesAndNewlines)),
                  double.isFinite else { return nil }
            return double
        default:
            return nil
        }
    }

    private static func isBoolean(_ value: Any) -> Bool {
        guard let number = value as? NSNumber else { return false }
        return CFGetTypeID(number) == CFBooleanGetTypeID()
    }

    /// A trimmed string, or "" — never the description of an Optional.
    private static func text(_ value: Any?) -> String {
        switch value {
        case let string as String:
            return string.trimmingCharacters(in: .whitespacesAndNewlines)
        case let number as NSNumber where !isBoolean(number):
            return number.stringValue
        default:
            return ""
        }
    }

    private static func dictionary(_ value: Any?) -> [String: Any] {
        value as? [String: Any] ?? [:]
    }

    private static func stringList(_ value: Any?) -> [String] {
        guard let array = value as? [Any] else { return [] }
        return array.compactMap { item in
            let line = text(item)
            return line.isEmpty ? nil : line
        }
    }

    private static func dictionaryList(_ value: Any?) -> [[String: Any]] {
        if let list = value as? [[String: Any]] { return list }
        guard let list = value as? [Any] else { return [] }
        return list.compactMap { $0 as? [String: Any] }
    }

    // MARK: Sound check

    /// Builds the report for `tools/does_this_sound_good.py`.
    public static func soundCheck(_ json: [String: Any], projectName: String) -> Report {
        let verdict = dictionary(json["verdict"])
        let project = dictionary(json["project"])

        let name = text(project["name"]).isEmpty ? projectName : text(project["name"])
        let score = intValue(verdict["score"])
        let hasScore = verdict["score"] != nil
        let answer = text(verdict["answer"]).isEmpty ? text(verdict["label"]) : text(verdict["answer"])
        let summary = text(verdict["summary"])

        var sections: [Report.Section] = []

        if !summary.isEmpty {
            sections.append(Report.Section(title: "Summary", lines: [summary]))
        }

        let strengths = stringList(json["strengths"])
        if !strengths.isEmpty {
            sections.append(Report.Section(title: "What's working", lines: strengths))
        }

        let issues = issueLines(json["issues"])
        if !issues.isEmpty {
            sections.append(Report.Section(title: "What to fix", lines: issues))
        }

        let nextActions = stringList(json["nextActions"])
        if !nextActions.isEmpty {
            sections.append(Report.Section(title: "Try this next", lines: nextActions))
        }

        let measurements = measurementLines(
            merging: [dictionary(json["projectChecks"]), dictionary(json["metrics"])]
        )
        if !measurements.isEmpty {
            sections.append(Report.Section(title: "Measurements", lines: measurements))
        }

        if sections.isEmpty {
            sections.append(Report.Section(
                title: "Result",
                lines: ["The sound check finished but didn't report any details. Render the song's audio and run it again."]
            ))
        }

        let headline = hasScore ? "\(score) / 100" : nil
        let caption: String?
        if !answer.isEmpty {
            caption = answer
        } else if hasScore {
            caption = "out of 100 for how this song currently sounds"
        } else {
            caption = nil
        }

        return Report(
            title: "Sound check",
            subtitle: name,
            headline: headline,
            headlineCaption: caption,
            sections: sections,
            plainText: renderPlainText(
                title: "Sound check",
                subtitle: name,
                headline: headline,
                caption: caption,
                sections: sections
            )
        )
    }

    /// "Clipping: 0.42% of samples are near full scale." — area and detail read
    /// as one sentence, and either half alone still reads.
    private static func issueLines(_ value: Any?) -> [String] {
        guard let array = value as? [Any] else { return [] }
        return array.compactMap { item -> String? in
            if let plain = item as? String {
                let trimmed = plain.trimmingCharacters(in: .whitespacesAndNewlines)
                return trimmed.isEmpty ? nil : trimmed
            }
            guard let issue = item as? [String: Any] else { return nil }
            let area = text(issue["area"])
            let detail = text(issue["detail"])
            switch (area.isEmpty, detail.isEmpty) {
            case (false, false): return "\(area): \(detail)"
            case (false, true): return area
            case (true, false): return detail
            case (true, true): return nil
            }
        }
    }

    // MARK: Suggestions agent

    /// Builds the report for `tools/daw_agent.py`.
    public static func agent(_ json: [String: Any], projectName: String) -> Report {
        let project = dictionary(json["project"])
        let name = text(project["name"]).isEmpty ? projectName : text(project["name"])

        let actions = dictionaryList(json["actions"])
        let before = dictionary(json["metricsBefore"])
        let after = dictionary(json["metricsAfter"])

        var sections: [Report.Section] = []

        var summaryLines: [String] = []
        let summary = text(json["summary"])
        if !summary.isEmpty {
            summaryLines.append(summary)
        }
        let query = text(json["query"])
        if !query.isEmpty {
            summaryLines.append("Asked for: \(query)")
        }
        if summaryLines.isEmpty {
            summaryLines.append(
                actions.isEmpty
                    ? "The suggestion run finished without changing anything."
                    : "Applied \(actions.count) suggestion\(actions.count == 1 ? "" : "s") to \(name)."
            )
        }
        sections.append(Report.Section(title: "Summary", lines: summaryLines))

        let changes = actions.compactMap { action -> String? in
            let title = text(action["title"]).isEmpty
                ? humanize(text(action["featureId"]))
                : text(action["title"])
            let messages = stringList(action["messages"])
            let heading = title.isEmpty ? "Change" : title
            if messages.isEmpty {
                return "\(heading) — nothing needed changing here."
            }
            // The tool's messages are sentence fragments with no punctuation of
            // their own, so joining them with a space runs them together into
            // one unreadable line.
            var detail = messages.joined(separator: "; ")
            if let last = detail.last, !".!?".contains(last) { detail.append(".") }
            return "\(heading) — \(detail)"
        }
        if !changes.isEmpty {
            sections.append(Report.Section(title: "What changed", lines: changes))
        }

        let comparison = comparisonLines(before: before, after: after)
        if !comparison.isEmpty {
            sections.append(Report.Section(title: "Before and after", lines: comparison))
        }

        if changes.isEmpty && comparison.isEmpty {
            sections.append(Report.Section(
                title: "What changed",
                lines: ["Nothing was changed. The song already covers the ideas the suggestions looked for."]
            ))
        }

        let caption: String
        switch actions.count {
        case 0: caption = "changes applied — nothing needed adjusting."
        case 1: caption = "change applied — one Undo (⌘Z) reverts it."
        default: caption = "changes applied — one Undo (⌘Z) reverts all of them."
        }

        return Report(
            title: "Suggestions",
            subtitle: name,
            headline: "\(actions.count)",
            headlineCaption: caption,
            sections: sections,
            plainText: renderPlainText(
                title: "Suggestions",
                subtitle: name,
                headline: "\(actions.count)",
                caption: caption,
                sections: sections
            )
        )
    }

    /// "recipe steps 15 → 18", with unchanged values marked rather than hidden,
    /// so the list answers "did anything happen?" on its own.
    private static func comparisonLines(before: [String: Any], after: [String: Any]) -> [String] {
        var keys: [String] = []
        for key in metricOrder where before[key] != nil || after[key] != nil {
            keys.append(key)
        }
        let extras = Set(before.keys).union(after.keys)
            .subtracting(keys)
            .filter { doubleValue(before[$0]) != nil || doubleValue(after[$0]) != nil }
        keys.append(contentsOf: extras.sorted())

        var changed: [String] = []
        var unchanged: [String] = []
        for key in keys {
            let start = doubleValue(before[key])
            let end = doubleValue(after[key])
            guard start != nil || end != nil else { continue }
            let style = metricStyles[key]
            let label = style?.shortLabel ?? humanize(key).lowercased()
            let unit = style?.unit ?? .plain
            let startText = start.map { formatted($0, unit: unit) } ?? "—"
            let endText = end.map { formatted($0, unit: unit) } ?? "—"
            if let start, let end, start == end {
                unchanged.append("\(label) \(startText) → \(endText) (unchanged)")
            } else {
                changed.append("\(label) \(startText) → \(endText)")
            }
        }
        // What moved comes first, so the section answers "did anything actually
        // happen?" without the reader scanning a column of identical numbers.
        return changed + unchanged
    }

    // MARK: Measurements

    /// Every numeric value the tool reported, in a stable, readable order and
    /// with the key names translated out of engineering shorthand. Later
    /// dictionaries win, so specific audio metrics override project counts.
    private static func measurementLines(merging sources: [[String: Any]]) -> [String] {
        var merged: [String: Any] = [:]
        for source in sources {
            for (key, value) in source {
                merged[key] = value
            }
        }
        guard !merged.isEmpty else { return [] }

        var ordered: [String] = metricOrder.filter { merged[$0] != nil }
        let extras = Set(merged.keys)
            .subtracting(ordered)
            .filter { doubleValue(merged[$0]) != nil }
        ordered.append(contentsOf: extras.sorted())

        return ordered.compactMap { key -> String? in
            guard let number = doubleValue(merged[key]) else { return nil }
            let style = metricStyles[key]
            let label = style?.label ?? humanize(key)
            return "\(label): \(formatted(number, unit: style?.unit ?? .plain))"
        }
    }

    private enum MetricUnit {
        /// Already a decibel value.
        case decibels
        /// Already a percentage.
        case percent
        /// A 0–1 share of the whole, shown as a percentage.
        case fraction
        case seconds
        case ratio
        case count
        case tempo
        case bars
        case plain
    }

    private struct MetricStyle {
        /// Title case, for the Measurements list.
        let label: String
        /// Lower case, for "recipe steps 15 → 18".
        let shortLabel: String
        let unit: MetricUnit
    }

    /// The order measurements are listed in: what the song sounds like first,
    /// then what the project contains.
    private static let metricOrder: [String] = [
        "seconds", "peakDb", "rmsDb", "crestDb", "clipPercent",
        "stereoWidth", "stereoCorrelation", "monoLossDb",
        "headSilenceSeconds", "tailSilenceSeconds",
        "subRatio", "bassRatio", "lowMidRatio", "midRatio", "highRatio", "airRatio",
        "bpm", "trackCount", "audibleTrackCount", "missingAudioCount",
        "recipeCount", "agentRecipeCount", "automationLaneCount",
        "clipCount", "noteCount", "effectCount", "activeEffects",
        "sectionCount", "maxClipEndBar", "bars"
    ]

    private static let metricStyles: [String: MetricStyle] = [
        "seconds": MetricStyle(label: "Length", shortLabel: "length", unit: .seconds),
        "peakDb": MetricStyle(label: "Loudest peak", shortLabel: "loudest peak", unit: .decibels),
        "rmsDb": MetricStyle(label: "Average loudness", shortLabel: "average loudness", unit: .decibels),
        "crestDb": MetricStyle(label: "Punch (peak above average)", shortLabel: "punch", unit: .decibels),
        "clipPercent": MetricStyle(label: "Samples that distort", shortLabel: "distorted samples", unit: .percent),
        "stereoWidth": MetricStyle(label: "Stereo width", shortLabel: "stereo width", unit: .ratio),
        "stereoCorrelation": MetricStyle(label: "How alike left and right are", shortLabel: "left/right likeness", unit: .ratio),
        "monoLossDb": MetricStyle(label: "Loudness lost in mono", shortLabel: "mono loss", unit: .decibels),
        "headSilenceSeconds": MetricStyle(label: "Silence before the music", shortLabel: "silence at the start", unit: .seconds),
        "tailSilenceSeconds": MetricStyle(label: "Silence after the music", shortLabel: "silence at the end", unit: .seconds),
        "subRatio": MetricStyle(label: "Deep bass energy", shortLabel: "deep bass energy", unit: .fraction),
        "bassRatio": MetricStyle(label: "Bass energy", shortLabel: "bass energy", unit: .fraction),
        "lowMidRatio": MetricStyle(label: "Lower middle energy", shortLabel: "lower middle energy", unit: .fraction),
        "midRatio": MetricStyle(label: "Middle energy", shortLabel: "middle energy", unit: .fraction),
        "highRatio": MetricStyle(label: "High energy", shortLabel: "high energy", unit: .fraction),
        "airRatio": MetricStyle(label: "Sparkle at the very top", shortLabel: "sparkle", unit: .fraction),
        "bpm": MetricStyle(label: "Tempo", shortLabel: "tempo", unit: .tempo),
        "trackCount": MetricStyle(label: "Tracks", shortLabel: "tracks", unit: .count),
        "audibleTrackCount": MetricStyle(label: "Tracks you can hear", shortLabel: "audible tracks", unit: .count),
        "missingAudioCount": MetricStyle(label: "Tracks with missing audio", shortLabel: "tracks missing audio", unit: .count),
        "recipeCount": MetricStyle(label: "Recipe steps", shortLabel: "recipe steps", unit: .count),
        "agentRecipeCount": MetricStyle(label: "Recipe steps added by suggestions", shortLabel: "suggested recipe steps", unit: .count),
        "automationLaneCount": MetricStyle(label: "Automation lanes", shortLabel: "automation lanes", unit: .count),
        "clipCount": MetricStyle(label: "Clips", shortLabel: "clips", unit: .count),
        "noteCount": MetricStyle(label: "Notes", shortLabel: "notes", unit: .count),
        "effectCount": MetricStyle(label: "Effects", shortLabel: "effects", unit: .count),
        "activeEffects": MetricStyle(label: "Effects switched on", shortLabel: "effects switched on", unit: .count),
        "sectionCount": MetricStyle(label: "Sections", shortLabel: "sections", unit: .count),
        "maxClipEndBar": MetricStyle(label: "Last bar with a clip", shortLabel: "last clip bar", unit: .bars),
        "bars": MetricStyle(label: "Length in bars", shortLabel: "bars", unit: .bars)
    ]

    private static func formatted(_ value: Double, unit: MetricUnit) -> String {
        guard value.isFinite else { return "—" }
        switch unit {
        case .decibels:
            return "\(number(value, places: 1)) dB"
        case .percent:
            return "\(number(value, places: 2))%"
        case .fraction:
            return "\(number(value * 100, places: 1))%"
        case .seconds:
            if abs(value) >= 60 {
                let whole = Int(value.rounded())
                return "\(number(value, places: 1)) seconds (\(whole / 60)m \(whole % 60)s)"
            }
            return "\(number(value, places: 2)) seconds"
        case .ratio:
            return number(value, places: 2)
        case .count:
            return number(value, places: 0)
        case .tempo:
            return "\(number(value, places: 1)) beats per minute"
        case .bars:
            // The label already says which bar quantity this is, so a "bar"
            // prefix here would read "bars bar 80".
            return number(value, places: 1)
        case .plain:
            return number(value, places: 2)
        }
    }

    /// Fixed decimals, then trailing zeros trimmed, so 0.50 reads "0.5" and
    /// 12.00 reads "12".
    private static func number(_ value: Double, places: Int) -> String {
        guard value.isFinite else { return "—" }
        if places <= 0 { return String(format: "%.0f", value) }
        var text = String(format: "%.\(places)f", value)
        if text.contains(".") {
            while text.hasSuffix("0") { text.removeLast() }
            if text.hasSuffix(".") { text.removeLast() }
        }
        return text.isEmpty ? "0" : text
    }

    /// "automationLaneCount" -> "Automation lane count". The fallback for keys
    /// a future version of a tool adds without this file knowing about them.
    private static func humanize(_ key: String) -> String {
        guard !key.isEmpty else { return "" }
        var words: [String] = []
        var current = ""
        for character in key {
            if character == "_" || character == "-" || character == " " || character == "." {
                if !current.isEmpty { words.append(current); current = "" }
                continue
            }
            if character.isUppercase, !current.isEmpty {
                words.append(current)
                current = ""
            }
            current.append(contentsOf: String(character).lowercased())
        }
        if !current.isEmpty { words.append(current) }
        guard !words.isEmpty else { return key }

        let expanded = words.map { word -> String in
            switch word {
            case "db": return "dB"
            case "bpm": return "BPM"
            case "rms": return "average level"
            case "id": return "ID"
            default: return word
            }
        }
        let sentence = expanded.joined(separator: " ")
        return sentence.prefix(1).uppercased() + String(sentence.dropFirst())
    }

    // MARK: Clipboard rendering

    private static func renderPlainText(
        title: String,
        subtitle: String,
        headline: String?,
        caption: String?,
        sections: [Report.Section]
    ) -> String {
        var lines: [String] = [title]
        if !subtitle.isEmpty { lines.append(subtitle) }
        switch (headline, caption) {
        case let (headline?, caption?):
            // "86 / 100 — Yes, this is in a good place", but "4 changes
            // applied…": a caption that continues the headline as a sentence
            // starts lower case and must not be broken by a dash.
            let continues = caption.first?.isLowercase == true
            lines.append(continues ? "\(headline) \(caption)" : "\(headline) — \(caption)")
        case let (headline?, nil): lines.append(headline)
        case let (nil, caption?): lines.append(caption)
        case (nil, nil): break
        }
        for section in sections where !section.isEmpty {
            lines.append("")
            lines.append(section.title)
            lines.append(String(repeating: "-", count: max(3, section.title.count)))
            lines.append(contentsOf: section.lines.map { "  • \($0)" })
        }
        return lines.joined(separator: "\n") + "\n"
    }
}

// MARK: - ReportWindowController

/// A real window for a report: scrollable, resizable, selectable, copyable, and
/// still there after you look away from it.
public final class ReportWindowController: NSWindowController, NSWindowDelegate {

    /// Report windows are independent of any document, so nothing else holds
    /// them. Without this they would deallocate the moment `present` returned.
    private static var openControllers: [ReportWindowController] = []

    private let report: Report

    /// Shows the report in its own window near `parent`. Deliberately not a
    /// sheet: a sheet blocks the song you are reading the report about, and the
    /// point of the report is to act on it while it's open.
    public static func present(report: Report, relativeTo window: NSWindow?) {
        let controller = ReportWindowController(report: report)
        openControllers.append(controller)
        controller.position(relativeTo: window)
        controller.showWindow(nil)
        controller.window?.makeKeyAndOrderFront(nil)
    }

    // MARK: Construction

    public init(report: Report) {
        self.report = report
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 620, height: 580),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.title = report.title
        window.subtitle = report.subtitle
        window.isReleasedWhenClosed = false
        window.contentMinSize = NSSize(width: 520, height: 420)
        window.minSize = NSSize(width: 520, height: 420)
        window.tabbingMode = .disallowed
        super.init(window: window)
        window.delegate = self
        window.contentView = makeContentView()
    }

    public required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    private func makeContentView() -> NSView {
        let root = ThemedBackgroundView { Theme.app }
        // A window resizes its content view with the autoresizing mask, so this
        // one view opts back in; everything inside it uses constraints.
        root.translatesAutoresizingMaskIntoConstraints = true
        root.autoresizingMask = [.width, .height]
        root.frame = NSRect(x: 0, y: 0, width: 620, height: 580)
        root.setAccessibilityRole(.group)
        root.setAccessibilityLabel("\(report.title) for \(report.subtitle)")

        let header = makeHeaderView()
        let headerSeparator = Controls.separator(vertical: false)
        let body = makeBodyScrollView()
        let footerSeparator = Controls.separator(vertical: false)
        let footer = makeFooterView()

        for subview in [header, headerSeparator, body, footerSeparator, footer] {
            subview.translatesAutoresizingMaskIntoConstraints = false
            root.addSubview(subview)
        }

        NSLayoutConstraint.activate([
            header.topAnchor.constraint(equalTo: root.topAnchor),
            header.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            header.trailingAnchor.constraint(equalTo: root.trailingAnchor),

            headerSeparator.topAnchor.constraint(equalTo: header.bottomAnchor),
            headerSeparator.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            headerSeparator.trailingAnchor.constraint(equalTo: root.trailingAnchor),

            body.topAnchor.constraint(equalTo: headerSeparator.bottomAnchor),
            body.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            body.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            body.bottomAnchor.constraint(equalTo: footerSeparator.topAnchor),

            footerSeparator.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            footerSeparator.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            footerSeparator.bottomAnchor.constraint(equalTo: footer.topAnchor),

            footer.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            footer.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            footer.bottomAnchor.constraint(equalTo: root.bottomAnchor)
        ])
        return root
    }

    // MARK: Header

    private func makeHeaderView() -> NSView {
        let header = ThemedBackgroundView { Theme.panel }
        header.setAccessibilityRole(.group)
        header.setAccessibilityLabel("Summary of this report")

        let stack = NSStackView()
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 2
        stack.translatesAutoresizingMaskIntoConstraints = false

        let titleLabel = makeLabel(report.title, font: Theme.Font.title(15), color: Theme.text)
        stack.addArrangedSubview(titleLabel)

        if !report.subtitle.isEmpty {
            let subtitleLabel = makeLabel(report.subtitle, font: Theme.Font.body(12), color: Theme.muted)
            stack.addArrangedSubview(subtitleLabel)
        }

        if let headline = report.headline, !headline.isEmpty {
            let headlineLabel = makeLabel(
                headline,
                font: .systemFont(ofSize: 28, weight: .semibold),
                color: Theme.text
            )
            headlineLabel.setAccessibilityLabel("Result: \(headline)")
            if let previous = stack.arrangedSubviews.last {
                stack.setCustomSpacing(12, after: previous)
            }
            stack.addArrangedSubview(headlineLabel)
        }

        if let caption = report.headlineCaption, !caption.isEmpty {
            let captionLabel = WrappingLabel(text: caption, font: Theme.Font.body(12), color: Theme.muted)
            stack.addArrangedSubview(captionLabel)
            captionLabel.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true
        }

        header.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: header.leadingAnchor, constant: 20),
            stack.trailingAnchor.constraint(equalTo: header.trailingAnchor, constant: -20),
            stack.topAnchor.constraint(equalTo: header.topAnchor, constant: 16),
            stack.bottomAnchor.constraint(equalTo: header.bottomAnchor, constant: -16)
        ])
        return header
    }

    // MARK: Body

    private func makeBodyScrollView() -> NSScrollView {
        let scrollView = NSScrollView()
        scrollView.hasVerticalScroller = true
        scrollView.hasHorizontalScroller = false
        scrollView.autohidesScrollers = true
        scrollView.drawsBackground = true
        scrollView.backgroundColor = Theme.app
        scrollView.borderType = .noBorder
        scrollView.translatesAutoresizingMaskIntoConstraints = false
        scrollView.setAccessibilityLabel("Report details")

        let container = FlippedView()
        container.translatesAutoresizingMaskIntoConstraints = false

        let stack = NSStackView()
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 20
        stack.translatesAutoresizingMaskIntoConstraints = false
        container.addSubview(stack)

        let visibleSections = report.sections.filter { !$0.isEmpty }
        if visibleSections.isEmpty {
            let empty = EmptyStateView(
                symbol: "text.magnifyingglass",
                title: "Nothing to report yet",
                body: "This run finished without any findings. Try it again once the song has audio to listen to."
            )
            stack.addArrangedSubview(empty)
            empty.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true
            empty.heightAnchor.constraint(greaterThanOrEqualToConstant: 220).isActive = true
        } else {
            for section in visibleSections {
                let view = makeSectionView(section)
                stack.addArrangedSubview(view)
                view.widthAnchor.constraint(equalTo: stack.widthAnchor).isActive = true
            }
        }

        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: container.leadingAnchor, constant: 20),
            stack.trailingAnchor.constraint(equalTo: container.trailingAnchor, constant: -20),
            stack.topAnchor.constraint(equalTo: container.topAnchor, constant: 18),
            stack.bottomAnchor.constraint(equalTo: container.bottomAnchor, constant: -22)
        ])

        scrollView.documentView = container
        let clip = scrollView.contentView
        NSLayoutConstraint.activate([
            container.leadingAnchor.constraint(equalTo: clip.leadingAnchor),
            container.trailingAnchor.constraint(equalTo: clip.trailingAnchor),
            container.topAnchor.constraint(equalTo: clip.topAnchor)
        ])
        return scrollView
    }

    private func makeSectionView(_ section: Report.Section) -> NSView {
        let container = NSStackView()
        container.orientation = .vertical
        container.alignment = .leading
        container.spacing = 7
        container.translatesAutoresizingMaskIntoConstraints = false
        container.setAccessibilityRole(.group)
        container.setAccessibilityLabel(section.title)

        let titleLabel = makeLabel(section.title, font: Theme.Font.emphasis(13), color: Theme.text)
        container.addArrangedSubview(titleLabel)
        container.setCustomSpacing(9, after: titleLabel)

        for line in section.lines {
            let row = makeBulletRow(line)
            container.addArrangedSubview(row)
            row.widthAnchor.constraint(equalTo: container.widthAnchor).isActive = true
        }
        return container
    }

    /// A bullet beside wrapping, selectable text — so a long finding hangs
    /// under itself rather than under the bullet, and the user can select the
    /// sentence to paste into a search.
    private func makeBulletRow(_ line: String) -> NSView {
        let bullet = makeLabel("•", font: Theme.Font.body(12), color: Theme.dim)
        bullet.setAccessibilityHidden(true)
        bullet.setContentHuggingPriority(.required, for: .horizontal)
        bullet.setContentCompressionResistancePriority(.required, for: .horizontal)
        bullet.widthAnchor.constraint(equalToConstant: 9).isActive = true

        let body = WrappingLabel(text: line, font: Theme.Font.body(12), color: Theme.text)
        body.toolTip = line
        body.setAccessibilityLabel(line)

        let row = NSStackView(views: [bullet, body])
        row.orientation = .horizontal
        row.alignment = .firstBaseline
        row.distribution = .fill
        row.spacing = 8
        row.translatesAutoresizingMaskIntoConstraints = false
        return row
    }

    // MARK: Footer

    private func makeFooterView() -> NSView {
        let footer = ThemedBackgroundView { Theme.panel }
        footer.setAccessibilityRole(.group)
        footer.setAccessibilityLabel("Report actions")

        let copyButton = Controls.button(
            title: "Copy",
            symbol: "doc.on.doc",
            help: "Copy this whole report to the clipboard so you can paste it somewhere else."
        ) { [weak self] in
            self?.copyToPasteboard()
        }

        let saveButton = Controls.button(
            title: "Save as Text…",
            symbol: "square.and.arrow.down",
            help: "Save this report as a plain text file you can keep or send to somebody."
        ) { [weak self] in
            self?.saveAsText()
        }

        let doneButton = Controls.button(
            title: "Done",
            help: "Close this report. You can run the check again at any time.",
            style: .primary,
            keyEquivalent: "\r",
            keyEquivalentModifiers: []
        ) { [weak self] in
            self?.close()
        }

        let spacer = NSView()
        spacer.translatesAutoresizingMaskIntoConstraints = false
        spacer.setContentHuggingPriority(NSLayoutConstraint.Priority(1), for: .horizontal)
        spacer.setContentCompressionResistancePriority(NSLayoutConstraint.Priority(1), for: .horizontal)

        let stack = NSStackView(views: [copyButton, saveButton, spacer, doneButton])
        stack.orientation = .horizontal
        stack.alignment = .centerY
        stack.distribution = .fill
        stack.spacing = 10
        stack.translatesAutoresizingMaskIntoConstraints = false

        footer.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: footer.leadingAnchor, constant: 16),
            stack.trailingAnchor.constraint(equalTo: footer.trailingAnchor, constant: -16),
            stack.topAnchor.constraint(equalTo: footer.topAnchor, constant: 12),
            stack.bottomAnchor.constraint(equalTo: footer.bottomAnchor, constant: -12)
        ])
        return footer
    }

    // MARK: Actions

    private func copyToPasteboard() {
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        pasteboard.setString(report.plainText, forType: .string)
        StatusCenter.shared.success(
            "Copied the \(report.title.lowercased()) report to the clipboard.",
            detail: "Paste it into any message or note."
        )
    }

    private func saveAsText() {
        let panel = NSSavePanel()
        panel.allowedContentTypes = [.plainText]
        panel.nameFieldStringValue = suggestedFileName()
        panel.message = "Save this report as a plain text file."
        panel.prompt = "Save"
        panel.canCreateDirectories = true

        let handler: (NSApplication.ModalResponse) -> Void = { [weak self] response in
            guard response == .OK, let url = panel.url, let self else { return }
            self.write(to: url)
        }
        if let window, window.isVisible {
            panel.beginSheetModal(for: window, completionHandler: handler)
        } else {
            handler(panel.runModal())
        }
    }

    private func write(to url: URL) {
        do {
            try report.plainText.write(to: url, atomically: true, encoding: .utf8)
            StatusCenter.shared.success(
                "Saved the report to \(url.lastPathComponent).",
                detail: url.deletingLastPathComponent().path
            )
        } catch {
            StatusCenter.shared.failure("Couldn't save the report", error: error, window: window)
        }
    }

    private func suggestedFileName() -> String {
        let raw = report.subtitle.isEmpty ? report.title : "\(report.title) - \(report.subtitle)"
        let cleaned = raw.components(separatedBy: CharacterSet(charactersIn: "/\\:*?\"<>|"))
            .joined(separator: "-")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return "\(cleaned.isEmpty ? "Report" : cleaned).txt"
    }

    // MARK: Placement and lifetime

    private func position(relativeTo parent: NSWindow?) {
        guard let window else { return }
        guard let parent else {
            window.center()
            return
        }
        var frame = window.frame
        frame.origin = NSPoint(
            x: parent.frame.midX - frame.width / 2,
            y: parent.frame.midY - frame.height / 2
        )
        if let screen = parent.screen ?? NSScreen.main {
            let visible = screen.visibleFrame
            if visible.width > frame.width {
                frame.origin.x = min(max(frame.origin.x, visible.minX + 8), visible.maxX - frame.width - 8)
            }
            if visible.height > frame.height {
                frame.origin.y = min(max(frame.origin.y, visible.minY + 8), visible.maxY - frame.height - 8)
            }
        }
        window.setFrame(frame, display: false)
    }

    public func windowWillClose(_ notification: Notification) {
        // Dropping the last reference synchronously would deallocate `self`
        // while AppKit is still inside this delegate call.
        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            ReportWindowController.openControllers.removeAll { $0 === self }
        }
    }
}

// MARK: - Private views

/// A document view whose origin is at the top, so a scroll view shows short
/// content from the first line instead of pinning it to the bottom.
private final class FlippedView: NSView {
    override var isFlipped: Bool { true }
}

/// A selectable label that wraps to the width it is given.
///
/// `NSTextField` only wraps under Auto Layout once it knows the width it will
/// be laid out at, which is what `preferredMaxLayoutWidth` is for; without this
/// every finding would be truncated to one line with a "…".
private final class WrappingLabel: NSTextField {

    init(text: String, font: NSFont, color: NSColor) {
        super.init(frame: .zero)
        stringValue = text
        self.font = font
        textColor = color
        isEditable = false
        isSelectable = true
        isBordered = false
        isBezeled = false
        drawsBackground = false
        usesSingleLineMode = false
        maximumNumberOfLines = 0
        lineBreakMode = .byWordWrapping
        cell?.wraps = true
        cell?.isScrollable = false
        translatesAutoresizingMaskIntoConstraints = false
        setContentHuggingPriority(.defaultLow, for: .horizontal)
        setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        setContentCompressionResistancePriority(.required, for: .vertical)
        setAccessibilityRole(.staticText)
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    override func layout() {
        if abs(preferredMaxLayoutWidth - bounds.width) > 0.5 {
            preferredMaxLayoutWidth = bounds.width
            invalidateIntrinsicContentSize()
        }
        super.layout()
    }
}
