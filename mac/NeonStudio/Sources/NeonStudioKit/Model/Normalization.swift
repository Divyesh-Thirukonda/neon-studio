import Foundation

public let neonSnapshotVersion = 4

// MARK: - Identifiers

/// Turns arbitrary text into a filesystem-safe project id.
///
/// This is deliberately lossy, so two different names can collapse onto the
/// same id. Callers that create a *new* file must run the result through
/// `ProjectStore.uniqueProjectId(basedOn:)` so they never silently overwrite
/// somebody else's project.
public func safeProjectId(_ id: String) -> String {
    let basename = URL(fileURLWithPath: id).lastPathComponent.replacingOccurrences(of: ".neon.json", with: "")
    let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "_-"))
    let cleaned = String(basename.unicodeScalars.map { allowed.contains($0) ? Character($0) : "-" })
        .trimmingCharacters(in: CharacterSet(charactersIn: "-_"))
    return cleaned.isEmpty ? "project-\(timestampForId())" : String(cleaned.prefix(72))
}

public func nowISO() -> String {
    ISO8601DateFormatter().string(from: Date())
}

/// Date *and* time, so ids minted on different days cannot collide. The old
/// implementation used `HHmmss` alone, which repeated every 24 hours.
public func timestampForId(_ date: Date = Date()) -> String {
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.timeZone = TimeZone(secondsFromGMT: 0)
    formatter.dateFormat = "yyyyMMdd-HHmmss"
    return formatter.string(from: date)
}

public func makeId(_ prefix: String) -> String {
    "\(prefix)-\(UUID().uuidString.prefix(8).lowercased())"
}

// MARK: - Defaults

public func makeDefaultControls(for tracks: [Track]) -> [String: MixerControl] {
    var result: [String: MixerControl] = [:]
    for track in tracks {
        result[track.id] = MixerControl(
            gain: track.gain ?? MixerControl.neutral.gain,
            pan: track.pan ?? 0,
            mute: false,
            solo: false,
            arm: false,
            sendA: MixerControl.neutral.sendA,
            sendB: MixerControl.neutral.sendB
        )
    }
    return result
}

public func makeDefaultAutomationLanes(for tracks: [Track]) -> [AutomationLane] {
    tracks.compactMap { track in
        let isAutomationTrack = track.kind?.lowercased() == "automation"
            || track.name.lowercased().contains("auto")
            || (track.clips ?? []).contains { $0.type?.lowercased() == "automation" }
        guard isAutomationTrack else { return nil }

        let firstClip = track.clips?.first
        let startBar = max(0, firstClip?.startBar ?? 0)
        let bars = max(1, firstClip?.bars ?? 8)
        let parameter = inferAutomationParameter(for: track)
        return AutomationLane(
            id: "auto-\(safeProjectId(track.id))-\(safeProjectId(parameter))",
            trackId: track.id,
            parameter: parameter,
            label: "\(track.name) \(parameter.capitalized)",
            color: track.color,
            enabled: true,
            curve: "linear",
            points: [
                AutomationPoint(bar: startBar, value: 0.15, curve: "linear"),
                AutomationPoint(bar: startBar + bars, value: 0.9, curve: "linear")
            ]
        )
    }
}

public func inferAutomationParameter(for track: Track) -> String {
    let text = ([track.name, track.kind, track.instrument] + (track.effects ?? []).map(\.name))
        .compactMap { $0 }
        .joined(separator: " ")
        .lowercased()
    if text.contains("filter") || text.contains("cutoff") { return "filter" }
    if text.contains("reverb") { return "reverb" }
    if text.contains("delay") { return "delay" }
    if text.contains("pan") { return "pan" }
    return "gain"
}

/// Human-readable name for an automation parameter, used in menus and labels.
public func automationParameterDisplayName(_ parameter: String) -> String {
    switch parameter.lowercased() {
    case "gain", "volume": return "Volume"
    case "pan": return "Pan"
    case "filter", "cutoff": return "Filter"
    case "reverb": return "Reverb"
    case "delay": return "Delay"
    case "senda": return "Send A"
    case "sendb": return "Send B"
    default: return parameter.capitalized
    }
}

// MARK: - Normalizers

/// True when this lane still refers to a track that exists.
///
/// Orphaned lanes used to be silently re-pointed at whichever track happened to
/// be first, which quietly attached somebody's filter sweep to an unrelated
/// instrument and then saved that corruption back to disk. They are now dropped
/// during normalization instead.
public func automationLaneIsOrphaned(_ lane: AutomationLane, tracks: [Track]) -> Bool {
    !tracks.contains { $0.id == lane.trackId }
}

public func normalizeAutomationLane(_ lane: AutomationLane, tracks: [Track]) -> AutomationLane {
    var next = lane
    let fallbackTrackId = tracks.first?.id ?? "master"
    if !tracks.contains(where: { $0.id == next.trackId }) {
        next.trackId = fallbackTrackId
    }
    if next.parameter.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
        next.parameter = "gain"
    }
    if next.id.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
        next.id = "auto-\(safeProjectId(next.trackId))-\(safeProjectId(next.parameter))"
    }
    if next.label.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
        let trackName = tracks.first { $0.id == next.trackId }?.name ?? "Master"
        next.label = "\(trackName) \(automationParameterDisplayName(next.parameter))"
    }
    next.enabled = next.enabled ?? true
    next.curve = next.curve ?? "linear"
    next.points = next.points
        .map { point in
            AutomationPoint(
                bar: max(0, point.bar),
                value: max(0, min(1, point.value)),
                curve: point.curve ?? next.curve
            )
        }
        .sorted { $0.bar < $1.bar }
    if next.points.isEmpty {
        next.points = [
            AutomationPoint(bar: 0, value: 0.3, curve: next.curve),
            AutomationPoint(bar: 8, value: 0.8, curve: next.curve)
        ]
    }
    return next
}

public func normalizeSampleEdit(_ edit: SampleEdit?) -> SampleEdit {
    let trimStart = max(0, edit?.trimStart ?? 0)
    let rawTrimEnd = edit?.trimEnd
    let trimEnd = rawTrimEnd.map { max(trimStart, $0) }
    return SampleEdit(
        trimStart: trimStart,
        trimEnd: trimEnd,
        pitchSemitones: max(-48, min(48, edit?.pitchSemitones ?? 0)),
        stretch: max(0.25, min(4, edit?.stretch ?? 1)),
        reverse: edit?.reverse ?? false,
        normalize: edit?.normalize ?? false,
        gain: edit?.gain.map { max(0, min(2, $0)) }
    )
}

public enum ProjectNormalizer {
    /// Fills in every optional the UI depends on and migrates older schema
    /// versions forward. Safe to call repeatedly; it is idempotent.
    public static func normalize(_ project: LocalProject) -> LocalProject {
        var next = project
        next.id = safeProjectId(next.id)
        if next.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            next.name = "Untitled Project"
        }
        next.createdAt = next.createdAt ?? next.updatedAt

        next.snapshot.tracks = next.snapshot.tracks.map { track in
            var normalized = track
            if track.sampleEdit != nil || track.file != nil || track.kind?.lowercased() == "audio" {
                normalized.sampleEdit = normalizeSampleEdit(track.sampleEdit)
            }
            normalized.clips = (track.clips ?? []).map { clip in
                var next = clip
                next.startBar = max(0, clip.startBar ?? 0)
                next.bars = max(0.25, clip.bars ?? 1)
                return next
            }
            return normalized
        }

        next.snapshot.swing = next.snapshot.swing ?? 0
        next.snapshot.snap = next.snapshot.snap ?? "1/4"
        next.snapshot.loopEnabled = next.snapshot.loopEnabled ?? false
        next.snapshot.loopStartBar = max(0, next.snapshot.loopStartBar ?? 0)
        next.snapshot.loopEndBar = max(
            (next.snapshot.loopStartBar ?? 0) + 1,
            next.snapshot.loopEndBar ?? 16
        )
        next.snapshot.controls = mergedControls(
            existing: next.snapshot.controls,
            tracks: next.snapshot.tracks
        )

        let automationLanes = next.snapshot.automationLanes ?? makeDefaultAutomationLanes(for: next.snapshot.tracks)
        next.snapshot.automationLanes = automationLanes
            // Drop lanes whose track is gone rather than reattaching them to an
            // arbitrary surviving track and persisting that as if it were real.
            .filter { !automationLaneIsOrphaned($0, tracks: next.snapshot.tracks) }
            .map { normalizeAutomationLane($0, tracks: next.snapshot.tracks) }

        next.snapshot.selectedTrackId = resolvedSelectedTrackId(next)
        next.snapshot.selectedClipId = resolvedSelectedClipId(next)
        next.snapshot.notes = migratedNotes(next)
        next.snapshot.activeView = WorkView(rawValue: next.snapshot.activeView ?? "")?.rawValue
            ?? WorkView.playlist.rawValue
        next.snapshot.patternIndex = max(1, min(99, next.snapshot.patternIndex ?? 1))
        next.snapshot.arrangementMode = next.snapshot.arrangementMode == "pattern" ? "pattern" : "song"
        next.snapshot.recipe = next.snapshot.recipe ?? []
        next.snapshot.version = neonSnapshotVersion
        return next
    }

    /// Keeps user-set mixer values, drops controls for tracks that no longer
    /// exist, and adds neutral controls for tracks that gained one.
    private static func mergedControls(existing: [String: MixerControl]?, tracks: [Track]) -> [String: MixerControl] {
        var defaults = makeDefaultControls(for: tracks)
        guard let existing else { return defaults }
        let liveIds = Set(tracks.map(\.id))
        for (id, control) in existing where liveIds.contains(id) {
            defaults[id] = control
        }
        return defaults
    }

    private static func resolvedSelectedTrackId(_ project: LocalProject) -> String {
        let ids = Set(project.snapshot.tracks.map(\.id))
        if let current = project.snapshot.selectedTrackId, ids.contains(current) {
            return current
        }
        return project.snapshot.tracks.first?.id ?? ""
    }

    private static func resolvedSelectedClipId(_ project: LocalProject) -> String {
        let clipIds = Set(project.snapshot.tracks.flatMap { ($0.clips ?? []).map(\.id) })
        if let current = project.snapshot.selectedClipId, clipIds.contains(current) {
            return current
        }
        return ""
    }

    /// Schema v3 and earlier kept one global note pool with no owning track, so
    /// switching tracks showed the same notes. Adopt orphans onto the track that
    /// was selected when the file was written, and drop notes whose track is gone.
    private static func migratedNotes(_ project: LocalProject) -> [PianoNote] {
        let ids = Set(project.snapshot.tracks.map(\.id))
        let fallback = project.snapshot.selectedTrackId.flatMap { ids.contains($0) ? $0 : nil }
            ?? project.snapshot.tracks.first?.id
        return (project.snapshot.notes ?? []).compactMap { note in
            var next = note
            next.beat = max(0, note.beat)
            next.duration = max(0.0625, note.duration)
            next.note = max(0, min(127, note.note))
            next.velocity = max(0.05, min(1, note.velocity))
            if let owner = note.trackId {
                // The note already names an owner. If that track is gone the
                // note goes with it — reassigning it would drop somebody's
                // melody onto an unrelated instrument.
                guard ids.contains(owner) else { return nil }
                next.trackId = owner
                return next
            }
            // No owner at all means a pre-v4 file, where notes were one global
            // pool. Adopt those onto the track that was selected when it was saved.
            guard let fallback else { return nil }
            next.trackId = fallback
            return next
        }
    }
}

// MARK: - Derived values

public extension LocalProject {
    /// Last bar containing content, used to size the timeline and the ruler.
    var contentEndBar: Double {
        let clipEnd = snapshot.tracks
            .flatMap { $0.clips ?? [] }
            .map { ($0.startBar ?? 0) + ($0.bars ?? 0) }
            .max() ?? 0
        let automationEnd = (snapshot.automationLanes ?? [])
            .flatMap(\.points)
            .map(\.bar)
            .max() ?? 0
        return max(clipEnd, automationEnd)
    }

    var secondsPerBar: Double {
        let bpm = snapshot.bpm > 0 ? snapshot.bpm : 120
        return (60.0 / bpm) * 4.0
    }

    func track(id: String) -> Track? {
        snapshot.tracks.first { $0.id == id }
    }

    func control(for trackId: String) -> MixerControl {
        snapshot.controls?[trackId] ?? MixerControl.neutral
    }

    func notes(forTrack trackId: String) -> [PianoNote] {
        (snapshot.notes ?? []).filter { $0.trackId == trackId }
    }

    var anyTrackSoloed: Bool {
        (snapshot.controls ?? [:]).values.contains { $0.solo }
    }

    /// True when this track should be heard given the current mute/solo state.
    func isAudible(_ trackId: String) -> Bool {
        let control = control(for: trackId)
        if control.mute { return false }
        if anyTrackSoloed { return control.solo }
        return true
    }
}

// MARK: - Snap

public enum SnapValue: String, CaseIterable {
    case none
    case bar = "1/1"
    case half = "1/2"
    case quarter = "1/4"
    case eighth = "1/8"
    case sixteenth = "1/16"

    public var label: String {
        switch self {
        case .none: return "Off"
        case .bar: return "Bar"
        case .half: return "1/2 note"
        case .quarter: return "1/4 note"
        case .eighth: return "1/8 note"
        case .sixteenth: return "1/16 note"
        }
    }

    /// Grid size expressed in bars.
    public var bars: Double {
        switch self {
        case .none: return 0
        case .bar: return 1
        case .half: return 0.5
        case .quarter: return 0.25
        case .eighth: return 0.125
        case .sixteenth: return 0.0625
        }
    }

    /// Grid size expressed in beats, for the piano roll.
    public var beats: Double { bars * 4 }

    public static func parse(_ raw: String?) -> SnapValue {
        guard let raw else { return .quarter }
        return SnapValue(rawValue: raw) ?? .quarter
    }

    public func snap(bars value: Double) -> Double {
        guard self != .none, bars > 0 else { return max(0, value) }
        return max(0, (value / bars).rounded() * bars)
    }

    public func snap(beats value: Double) -> Double {
        guard self != .none, beats > 0 else { return max(0, value) }
        return max(0, (value / beats).rounded() * beats)
    }
}
