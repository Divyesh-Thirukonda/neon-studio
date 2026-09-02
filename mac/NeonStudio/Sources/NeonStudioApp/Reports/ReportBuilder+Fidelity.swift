import Foundation

// MARK: - Transcript fidelity

/// Turns the JSON from `tools/transcript_fidelity.py` into a `Report`, and
/// folds it together with the sound check into the single "Check My Mix" report.
///
/// "Does it match what was asked for?" is a different question from "is it
/// good?". A song can score 90 for loudness and balance while quietly dropping
/// the half-time drop the description asked for, or nail every claim in the
/// transcript and still clip. The combined report puts both answers in one
/// window so the reader never has to choose which question to ask.
///
/// Everything here is defensive in the same way `ReportBuilder` is: the tool is
/// a separate program, so a missing key, a renamed status, or an entirely empty
/// object must produce a readable report rather than a crash or the word "nil".
extension ReportBuilder {

    // MARK: Claim status

    /// The four answers the fidelity tool can give about one claim, in the
    /// order the report lists them: good news first, then what needs a fix,
    /// then what a person still has to listen for.
    private enum ClaimStatus: CaseIterable {
        case matched
        case missing
        case contradicted
        case unverifiable

        init(_ raw: String) {
            switch raw.lowercased().trimmingCharacters(in: .whitespacesAndNewlines) {
            case "matched", "match", "matches", "ok", "true", "yes", "pass", "passed":
                self = .matched
            case "missing", "absent", "notfound", "not_found", "not found":
                self = .missing
            case "contradicted", "contradiction", "contradicts", "wrong", "mismatch", "mismatched", "fail", "failed":
                self = .contradicted
            default:
                // Anything the tool invents later lands with the claims a
                // person still has to check, which is the honest default.
                self = .unverifiable
            }
        }

        var sectionTitle: String {
            switch self {
            case .matched: return "Matches the description"
            case .missing: return "Missing"
            case .contradicted: return "Contradicts the description"
            case .unverifiable: return "Couldn't check"
            }
        }

        var marker: String {
            switch self {
            case .matched: return "✓"
            case .missing: return "✗"
            case .contradicted: return "‼"
            case .unverifiable: return "?"
            }
        }
    }

    /// One claim from the tool, already cleaned of anything that could read
    /// as "nil" or an empty dash on screen.
    private struct Claim {
        let status: ClaimStatus
        let claim: String
        let evidence: String
        let verifiedBy: String

        /// "✓ Drop hits at bar 33 — kick doubles at bar 33 (heard in the audio)"
        var line: String {
            var text = "\(status.marker) \(claim)"
            if !evidence.isEmpty {
                text += " — \(evidence)"
            }
            if let strength = strengthNote {
                text += " \(strength)"
            }
            return text
        }

        /// How much to trust the check: hearing it in the render is stronger
        /// than reading it out of the project file, which is stronger than
        /// matching words in the written plan.
        private var strengthNote: String? {
            switch verifiedBy.lowercased() {
            case "audio", "render", "wav", "listen":
                return "(heard in the audio)"
            case "project", "document", "song", "model":
                return "(set in the project)"
            case "spec", "plan", "transcript", "text":
                return "(only in the written plan)"
            default:
                return nil
            }
        }
    }

    // MARK: Fidelity report

    /// Builds the report for `tools/transcript_fidelity.py`.
    ///
    /// Headline is the 0–100 score, the caption is the tool's own summary
    /// ("9 of 11 claims match"), and the body groups every claim by whether it
    /// matched, is missing, contradicts the description, or couldn't be checked
    /// by software at all.
    public static func fidelity(_ json: [String: Any], projectName: String) -> Report {
        let name = fidelityText(json["projectName"]).isEmpty ? projectName : fidelityText(json["projectName"])
        let parsed = parseFidelity(json)

        var sections: [Report.Section] = fidelitySections(parsed)
        if sections.isEmpty {
            sections.append(Report.Section(title: "Result", lines: [fidelityEmptyExplanation(parsed)]))
        }

        return Report(
            title: "Does it match the description?",
            subtitle: name,
            headline: parsed.headline,
            headlineCaption: parsed.caption,
            sections: sections,
            plainText: renderFidelityPlainText(
                title: "Does it match the description?",
                subtitle: name,
                headline: parsed.headline,
                caption: parsed.caption,
                sections: sections
            )
        )
    }

    // MARK: Combined "Check My Mix" report

    /// One window for both questions: the sound check ("is it good?") and the
    /// transcript fidelity check ("does it match what was asked for?").
    ///
    /// Either half may be absent. A project that wasn't built from a transcript
    /// has nothing to compare against, and a project with no rendered audio has
    /// nothing to listen to; each case is said out loud rather than hidden.
    public static func combined(
        sound: [String: Any]?,
        fidelity: [String: Any]?,
        projectName: String
    ) -> Report {
        let title = "Check My Mix"
        let subtitle = projectName

        let soundReport = sound.map { soundCheck($0, projectName: projectName) }
        let fidelityParsed = fidelity.map { parseFidelity($0) }

        // Headline and caption.
        let soundHeadline = soundReport?.headline.flatMap { $0.isEmpty ? nil : $0 }
        let soundCaption = soundReport?.headlineCaption.flatMap { $0.isEmpty ? nil : $0 }
        let fidelityHeadline = fidelityParsed?.headline
        let fidelityCaption = fidelityParsed?.caption

        let headline: String?
        let caption: String?
        switch (soundHeadline, fidelityParsed) {
        case let (soundHeadline?, fidelityParsed?):
            headline = "\(soundHeadline) · matches \(fidelityParsed.matchPhrase)"
            var explanation = "The first number is how the song sounds; the rest is how much of the description made it into the song."
            if let soundCaption {
                explanation = "\(soundCaption) \(explanation)"
            }
            caption = explanation
        case (let soundHeadline?, nil):
            headline = soundHeadline
            caption = soundCaption
        case (nil, let fidelityParsed?):
            headline = fidelityHeadline
            caption = fidelityCaption ?? (fidelityParsed.hasClaims ? nil : "The description check didn't return a score.")
        case (nil, nil):
            headline = nil
            caption = soundCaption ?? fidelityCaption
        }

        // Sections: what was asked for first, then how it sounds.
        var sections: [Report.Section] = []
        let fidelityPrefix = "Does it match the description?"
        let soundPrefix = "Does it sound good?"

        if let fidelityParsed {
            let grouped = fidelitySections(fidelityParsed)
            if grouped.isEmpty {
                sections.append(Report.Section(
                    title: fidelityPrefix,
                    lines: [fidelityEmptyExplanation(fidelityParsed)]
                ))
            } else {
                for section in grouped {
                    sections.append(Report.Section(
                        title: "\(fidelityPrefix) — \(section.title)",
                        lines: section.lines
                    ))
                }
            }
        } else {
            sections.append(Report.Section(
                title: fidelityPrefix,
                lines: ["No description to compare against — this project wasn't built from a transcript."]
            ))
        }

        if let soundReport {
            let visible = soundReport.sections.filter { !$0.lines.isEmpty }
            if visible.isEmpty {
                sections.append(Report.Section(
                    title: soundPrefix,
                    lines: ["The sound check finished but didn't report any details. Render the song's audio and run Check My Mix again."]
                ))
            } else {
                for section in visible {
                    sections.append(Report.Section(
                        title: "\(soundPrefix) — \(section.title)",
                        lines: section.lines
                    ))
                }
            }
        } else {
            sections.append(Report.Section(
                title: soundPrefix,
                lines: ["The sound check didn't run, so there's nothing to say about how the song sounds yet. Render the song's audio and run Check My Mix again."]
            ))
        }

        return Report(
            title: title,
            subtitle: subtitle,
            headline: headline,
            headlineCaption: caption,
            sections: sections,
            plainText: renderFidelityPlainText(
                title: title,
                subtitle: subtitle,
                headline: headline,
                caption: caption,
                sections: sections
            )
        )
    }

    // MARK: Parsing

    /// Everything the fidelity JSON said, in a shape the two builders share.
    private struct ParsedFidelity {
        let ok: Bool
        let error: String
        let hasScore: Bool
        let score: Int
        let summary: String
        let claims: [Claim]
        let nextActions: [String]
        let reportedUnverifiable: Int

        var hasClaims: Bool { !claims.isEmpty }
        var matchedCount: Int { claims.filter { $0.status == .matched }.count }
        var unverifiableCount: Int {
            let counted = claims.filter { $0.status == .unverifiable }.count
            return counted > 0 ? counted : max(0, reportedUnverifiable)
        }

        /// "<score> / 100" when the tool gave a score, otherwise a score
        /// worked out from the claims so the headline never goes blank while
        /// there is something to say. Nothing at all when there is nothing.
        var headline: String? {
            if hasScore { return "\(score) / 100" }
            guard hasClaims else { return nil }
            let derived = Int((Double(matchedCount) / Double(claims.count) * 100).rounded())
            return "\(derived) / 100"
        }

        /// The tool's summary, or a sentence built from the claims.
        var caption: String? {
            if !summary.isEmpty { return summary }
            if hasClaims {
                return "\(matchedCount) of \(claims.count) claim\(claims.count == 1 ? "" : "s") match"
            }
            if !ok, !error.isEmpty { return "The description check couldn't finish." }
            return nil
        }

        /// The phrase after "matches" in the combined headline, so it reads
        /// "86 / 100 · matches 9 of 11 claims" rather than "…matches 9 of 11
        /// claims match".
        var matchPhrase: String {
            // The tool's own summary is the authority ("9 of 11 claims match");
            // only its trailing verb goes, so the headline doesn't double up.
            let trimmed = summary.trimmingCharacters(in: .whitespacesAndNewlines)
            var stripped = trimmed
            var didStrip = false
            for suffix in [" matched.", " matched", " matches.", " matches", " match.", " match"] {
                if stripped.lowercased().hasSuffix(suffix) {
                    stripped = String(stripped.dropLast(suffix.count))
                    didStrip = true
                    break
                }
            }
            if didStrip, !stripped.isEmpty {
                return stripped.prefix(1).lowercased() + String(stripped.dropFirst())
            }
            if hasClaims {
                return "\(matchedCount) of \(claims.count) claim\(claims.count == 1 ? "" : "s")"
            }
            if hasScore { return "\(score)% of the description" }
            if !trimmed.isEmpty {
                return trimmed.prefix(1).lowercased() + String(trimmed.dropFirst())
            }
            return "an unknown share of the description"
        }
    }

    private static func parseFidelity(_ json: [String: Any]) -> ParsedFidelity {
        let claims = fidelityDictionaries(json["claims"]).compactMap { raw -> Claim? in
            var claim = fidelityText(raw["claim"])
            if claim.isEmpty { claim = fidelityText(raw["text"]) }
            if claim.isEmpty { claim = fidelityText(raw["title"]) }
            if claim.isEmpty {
                // A claim with no words is still a claim about *something*;
                // the area ("drums", "arrangement") is better than dropping it.
                let area = fidelityText(raw["area"])
                if area.isEmpty { return nil }
                claim = "Something about the \(area.lowercased())"
            }
            let evidence = fidelityText(raw["evidence"]).isEmpty
                ? fidelityText(raw["detail"])
                : fidelityText(raw["evidence"])
            return Claim(
                status: ClaimStatus(fidelityText(raw["status"])),
                claim: claim,
                evidence: evidence,
                verifiedBy: fidelityText(raw["verifiedBy"])
            )
        }

        let okValue = json["ok"]
        let ok = okValue == nil ? true : fidelityBool(okValue)

        return ParsedFidelity(
            ok: ok,
            error: fidelityText(json["error"]),
            hasScore: json["score"] != nil && !fidelityText(json["score"]).isEmpty,
            score: min(100, max(0, intValue(json["score"]))),
            summary: fidelityText(json["summary"]),
            claims: claims,
            nextActions: fidelityStrings(json["nextActions"]),
            reportedUnverifiable: intValue(json["unverifiable"])
        )
    }

    // MARK: Sections

    /// The claim groups in reading order, then "Next". Empty groups are left
    /// out, so a song that matched everything shows one clean list.
    private static func fidelitySections(_ parsed: ParsedFidelity) -> [Report.Section] {
        var sections: [Report.Section] = []

        if !parsed.ok {
            let reason = parsed.error.isEmpty
                ? "The description check stopped before it could compare anything."
                : parsed.error
            sections.append(Report.Section(
                title: "Problem",
                lines: [reason, "Make sure the project still has its transcript, then run Check My Mix again."]
            ))
        }

        for status in ClaimStatus.allCases {
            var lines = parsed.claims.filter { $0.status == status }.map { $0.line }
            if status == .unverifiable {
                if lines.isEmpty, parsed.reportedUnverifiable > 0 {
                    let count = parsed.reportedUnverifiable
                    lines.append("? \(count) claim\(count == 1 ? "" : "s") couldn't be checked automatically.")
                }
                if !lines.isEmpty {
                    lines.append("These need the song's audio rendered, or a listen with your own ears, before anyone can say yes or no.")
                }
            }
            if !lines.isEmpty {
                sections.append(Report.Section(title: status.sectionTitle, lines: lines))
            }
        }

        if !parsed.nextActions.isEmpty {
            sections.append(Report.Section(title: "Next", lines: parsed.nextActions))
        } else if parsed.ok, parsed.hasClaims {
            let unmatched = parsed.claims.count - parsed.matchedCount
            let line = unmatched == 0
                ? "Everything the description asked for is in the song. Play it through once to confirm it feels right."
                : "Fix the missing and contradicted items above, render the audio, and run Check My Mix again."
            sections.append(Report.Section(title: "Next", lines: [line]))
        }

        return sections
    }

    /// Why a fidelity result had nothing to list — said plainly, with the
    /// next thing to try.
    private static func fidelityEmptyExplanation(_ parsed: ParsedFidelity) -> String {
        if !parsed.ok {
            return parsed.error.isEmpty
                ? "The description check stopped before it could compare anything. Try running Check My Mix again."
                : "\(parsed.error) Try running Check My Mix again."
        }
        return "The description check finished but found no claims to compare. The project's transcript may be empty; add a description of the song and run Check My Mix again."
    }

    // MARK: Value coercion

    /// A trimmed string, or "" — never the description of an Optional.
    private static func fidelityText(_ value: Any?) -> String {
        switch value {
        case let string as String:
            return string.trimmingCharacters(in: .whitespacesAndNewlines)
        case let number as NSNumber where CFGetTypeID(number) != CFBooleanGetTypeID():
            return number.stringValue
        default:
            return ""
        }
    }

    private static func fidelityBool(_ value: Any?) -> Bool {
        switch value {
        case let bool as Bool:
            return bool
        case let number as NSNumber:
            return number.boolValue
        case let string as String:
            switch string.lowercased().trimmingCharacters(in: .whitespacesAndNewlines) {
            case "true", "yes", "1", "ok": return true
            default: return false
            }
        default:
            return false
        }
    }

    private static func fidelityStrings(_ value: Any?) -> [String] {
        guard let array = value as? [Any] else { return [] }
        return array.compactMap { item -> String? in
            if let dictionary = item as? [String: Any] {
                // Some tools hand back {"action": "..."} objects instead of
                // plain strings; read the obvious keys before giving up.
                for key in ["action", "text", "title", "detail"] {
                    let line = fidelityText(dictionary[key])
                    if !line.isEmpty { return line }
                }
                return nil
            }
            let line = fidelityText(item)
            return line.isEmpty ? nil : line
        }
    }

    private static func fidelityDictionaries(_ value: Any?) -> [[String: Any]] {
        if let list = value as? [[String: Any]] { return list }
        guard let list = value as? [Any] else { return [] }
        return list.compactMap { $0 as? [String: Any] }
    }

    // MARK: Clipboard rendering

    /// The same layout `ReportBuilder` uses for its own reports, so a copied
    /// "Check My Mix" pastes exactly like a copied sound check.
    private static func renderFidelityPlainText(
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
            let continues = caption.first?.isLowercase == true
            lines.append(continues ? "\(headline) \(caption)" : "\(headline) — \(caption)")
        case let (headline?, nil):
            lines.append(headline)
        case let (nil, caption?):
            lines.append(caption)
        case (nil, nil):
            break
        }
        for section in sections where !section.lines.isEmpty {
            lines.append("")
            lines.append(section.title)
            lines.append(String(repeating: "-", count: max(3, section.title.count)))
            lines.append(contentsOf: section.lines.map { "  • \($0)" })
        }
        return lines.joined(separator: "\n") + "\n"
    }
}
