import Foundation

// MARK: - Document model
//
// These types are the on-disk `.neon.json` schema. Every field that older files
// might not contain stays optional so previously saved projects keep opening;
// `ProjectNormalizer` fills the gaps after decoding.

public struct LocalProject: Codable, Equatable {
    public var id: String
    public var name: String
    public var createdAt: String?
    public var updatedAt: String
    public var projectFile: String?
    public var assets: [ProjectAsset]?
    public var description: String?
    public var keyCenter: String?
    public var snapshot: ProjectSnapshot

    public init(
        id: String,
        name: String,
        createdAt: String? = nil,
        updatedAt: String,
        projectFile: String? = nil,
        assets: [ProjectAsset]? = nil,
        description: String? = nil,
        keyCenter: String? = nil,
        snapshot: ProjectSnapshot
    ) {
        self.id = id
        self.name = name
        self.createdAt = createdAt
        self.updatedAt = updatedAt
        self.projectFile = projectFile
        self.assets = assets
        self.description = description
        self.keyCenter = keyCenter
        self.snapshot = snapshot
    }
}

public struct ProjectAsset: Codable, Equatable {
    public var trackId: String
    public var file: String
    public var data: String?

    public init(trackId: String, file: String, data: String? = nil) {
        self.trackId = trackId
        self.file = file
        self.data = data
    }
}

public struct ProjectSnapshot: Codable, Equatable {
    public var version: Int?
    public var bpm: Double
    public var swing: Double?
    public var snap: String?
    public var loopEnabled: Bool?
    public var loopStartBar: Double?
    public var loopEndBar: Double?
    public var tracks: [Track]
    public var controls: [String: MixerControl]?
    public var automationLanes: [AutomationLane]?
    public var notes: [PianoNote]?
    public var selectedTrackId: String?
    public var selectedClipId: String?
    public var activeView: String?
    public var patternIndex: Int?
    public var arrangementMode: String?
    public var recipe: [RecipeItem]?

    public init(
        version: Int? = nil,
        bpm: Double,
        swing: Double? = nil,
        snap: String? = nil,
        loopEnabled: Bool? = nil,
        loopStartBar: Double? = nil,
        loopEndBar: Double? = nil,
        tracks: [Track],
        controls: [String: MixerControl]? = nil,
        automationLanes: [AutomationLane]? = nil,
        notes: [PianoNote]? = nil,
        selectedTrackId: String? = nil,
        selectedClipId: String? = nil,
        activeView: String? = nil,
        patternIndex: Int? = nil,
        arrangementMode: String? = nil,
        recipe: [RecipeItem]? = nil
    ) {
        self.version = version
        self.bpm = bpm
        self.swing = swing
        self.snap = snap
        self.loopEnabled = loopEnabled
        self.loopStartBar = loopStartBar
        self.loopEndBar = loopEndBar
        self.tracks = tracks
        self.controls = controls
        self.automationLanes = automationLanes
        self.notes = notes
        self.selectedTrackId = selectedTrackId
        self.selectedClipId = selectedClipId
        self.activeView = activeView
        self.patternIndex = patternIndex
        self.arrangementMode = arrangementMode
        self.recipe = recipe
    }
}

public struct Track: Codable, Equatable {
    public var id: String
    public var name: String
    public var kind: String?
    public var file: String?
    public var color: String?
    public var gain: Double?
    public var pan: Double?
    public var steps: [Int]?
    public var instrument: String?
    public var clips: [Clip]?
    public var effects: [Effect]?
    public var sampleEdit: SampleEdit?

    public init(
        id: String,
        name: String,
        kind: String? = nil,
        file: String? = nil,
        color: String? = nil,
        gain: Double? = nil,
        pan: Double? = nil,
        steps: [Int]? = nil,
        instrument: String? = nil,
        clips: [Clip]? = nil,
        effects: [Effect]? = nil,
        sampleEdit: SampleEdit? = nil
    ) {
        self.id = id
        self.name = name
        self.kind = kind
        self.file = file
        self.color = color
        self.gain = gain
        self.pan = pan
        self.steps = steps
        self.instrument = instrument
        self.clips = clips
        self.effects = effects
        self.sampleEdit = sampleEdit
    }

    /// True when the 16-step rack is a meaningful editor for this track.
    /// Audio stems and automation lanes are arranged as clips, not steps.
    public var supportsStepSequencing: Bool {
        let lowered = (kind ?? "").lowercased()
        if lowered == "automation" { return false }
        if lowered == "audio", file != nil { return false }
        return true
    }
}

public struct Clip: Codable, Equatable {
    public var id: String
    public var name: String
    public var startBar: Double?
    public var bars: Double?
    public var lane: String?
    public var color: String?
    public var type: String?

    public init(
        id: String,
        name: String,
        startBar: Double? = nil,
        bars: Double? = nil,
        lane: String? = nil,
        color: String? = nil,
        type: String? = nil
    ) {
        self.id = id
        self.name = name
        self.startBar = startBar
        self.bars = bars
        self.lane = lane
        self.color = color
        self.type = type
    }
}

public struct Effect: Codable, Equatable {
    public var id: String
    public var name: String
    public var active: Bool?
    public var amount: Double?

    public init(id: String, name: String, active: Bool? = nil, amount: Double? = nil) {
        self.id = id
        self.name = name
        self.active = active
        self.amount = amount
    }
}

public struct SampleEdit: Codable, Equatable {
    public var trimStart: Double?
    public var trimEnd: Double?
    public var pitchSemitones: Double?
    public var stretch: Double?
    public var reverse: Bool?
    public var normalize: Bool?
    public var gain: Double?

    public init(
        trimStart: Double? = nil,
        trimEnd: Double? = nil,
        pitchSemitones: Double? = nil,
        stretch: Double? = nil,
        reverse: Bool? = nil,
        normalize: Bool? = nil,
        gain: Double? = nil
    ) {
        self.trimStart = trimStart
        self.trimEnd = trimEnd
        self.pitchSemitones = pitchSemitones
        self.stretch = stretch
        self.reverse = reverse
        self.normalize = normalize
        self.gain = gain
    }
}

public struct MixerControl: Codable, Equatable {
    public var gain: Double
    public var pan: Double
    public var mute: Bool
    public var solo: Bool
    public var arm: Bool
    public var sendA: Double
    public var sendB: Double

    public init(
        gain: Double,
        pan: Double,
        mute: Bool,
        solo: Bool,
        arm: Bool,
        sendA: Double,
        sendB: Double
    ) {
        self.gain = gain
        self.pan = pan
        self.mute = mute
        self.solo = solo
        self.arm = arm
        self.sendA = sendA
        self.sendB = sendB
    }

    public static let neutral = MixerControl(
        gain: 0.82,
        pan: 0,
        mute: false,
        solo: false,
        arm: false,
        sendA: 0.15,
        sendB: 0.08
    )
}

public struct AutomationLane: Codable, Equatable {
    public var id: String
    public var trackId: String
    public var parameter: String
    public var label: String
    public var color: String?
    public var enabled: Bool?
    public var curve: String?
    public var points: [AutomationPoint]

    public init(
        id: String,
        trackId: String,
        parameter: String,
        label: String,
        color: String? = nil,
        enabled: Bool? = nil,
        curve: String? = nil,
        points: [AutomationPoint]
    ) {
        self.id = id
        self.trackId = trackId
        self.parameter = parameter
        self.label = label
        self.color = color
        self.enabled = enabled
        self.curve = curve
        self.points = points
    }
}

public struct AutomationPoint: Codable, Equatable {
    public var bar: Double
    public var value: Double
    public var curve: String?

    public init(bar: Double, value: Double, curve: String? = nil) {
        self.bar = bar
        self.value = value
        self.curve = curve
    }
}

public struct PianoNote: Codable, Equatable {
    public var id: String
    public var beat: Double
    public var duration: Double
    public var note: Int
    public var velocity: Double
    public var color: String
    /// Added in schema v4. Older files stored one global note pool with no owner;
    /// `ProjectNormalizer` assigns those to the project's selected track on load.
    public var trackId: String?

    public init(
        id: String,
        beat: Double,
        duration: Double,
        note: Int,
        velocity: Double,
        color: String,
        trackId: String? = nil
    ) {
        self.id = id
        self.beat = beat
        self.duration = duration
        self.note = note
        self.velocity = velocity
        self.color = color
        self.trackId = trackId
    }
}

public struct RecipeItem: Codable, Equatable {
    public var id: String
    public var section: String?
    public var label: String
    public var detail: String?
    public var status: String?
    public var trackIds: [String]?

    public init(
        id: String,
        section: String? = nil,
        label: String,
        detail: String? = nil,
        status: String? = nil,
        trackIds: [String]? = nil
    ) {
        self.id = id
        self.section = section
        self.label = label
        self.detail = detail
        self.status = status
        self.trackIds = trackIds
    }

    /// Whether this production step counts as finished.
    ///
    /// Defined once, here, because two panels each had their own idea of it and
    /// disagreed: the generators write `"implemented"`, which one list
    /// recognised and the other did not, so the same project read "15 of 15
    /// steps done" in one panel and "0 of 15" in the other.
    public static let doneStatuses: Set<String> = [
        "implemented", "done", "complete", "completed", "ready", "ok"
    ]

    public var isDone: Bool {
        RecipeItem.doneStatuses.contains((status ?? "").lowercased())
    }

    /// The value to write when marking a step done, matching what the Python
    /// tools produce so a round trip through them is stable.
    public static let doneStatus = "implemented"
    public static let notDoneStatus = "planned"
}

public struct ProjectIndex: Codable {
    public struct Entry: Codable {
        public var id: String
        public var file: String
    }
    public var projects: [Entry]?
}

/// The portable envelope actually written to `.neon.json`.
public struct ProjectFileEnvelope: Codable {
    public var format: String
    public var formatVersion: Int
    public var portable: Bool
    public var assetMode: String
    public var id: String
    public var name: String
    public var createdAt: String?
    public var updatedAt: String
    public var projectFile: String?
    public var assets: [ProjectAsset]?
    public var description: String?
    public var keyCenter: String?
    public var snapshot: ProjectSnapshot

    public init(project: LocalProject) {
        self.format = "neon-studio-project"
        self.formatVersion = 1
        // Be honest about portability. A project whose tracks point at absolute
        // paths on this Mac will not find its audio anywhere else, and claiming
        // `portable: true` regardless — as earlier versions did — made a broken
        // hand-off look like a supported one.
        let hasMachineLocalAudio = project.snapshot.tracks.contains { track in
            guard let file = track.file, !file.isEmpty else { return false }
            return file.hasPrefix("/") || file.hasPrefix("file://")
        }
        let hasEmbeddedAssets = project.assets?.contains { $0.data != nil } == true
        self.portable = hasEmbeddedAssets || !hasMachineLocalAudio
        self.assetMode = hasEmbeddedAssets
            ? "embedded"
            : (hasMachineLocalAudio ? "external-absolute" : "external")
        self.id = project.id
        self.name = project.name
        self.createdAt = project.createdAt
        self.updatedAt = project.updatedAt
        self.projectFile = project.projectFile
        self.assets = project.assets
        self.description = project.description
        self.keyCenter = project.keyCenter
        self.snapshot = project.snapshot
    }

    public var project: LocalProject {
        LocalProject(
            id: id,
            name: name,
            createdAt: createdAt,
            updatedAt: updatedAt,
            projectFile: projectFile,
            assets: assets,
            description: description,
            keyCenter: keyCenter,
            snapshot: snapshot
        )
    }
}

// MARK: - View + tool enums

public enum WorkView: String, CaseIterable {
    case playlist
    case piano
    case mixer
    case plugins
    case sample
    case recipe

    /// Producer-facing name.
    public var label: String {
        switch self {
        case .playlist: return "Arrange"
        case .piano: return "Notes"
        case .mixer: return "Mix"
        case .plugins: return "Effects"
        case .sample: return "Sample"
        case .recipe: return "Recipe"
        }
    }

    /// One-line explanation shown as a tooltip and in the plain-language help strip.
    public var explanation: String {
        switch self {
        case .playlist: return "Lay out the song section by section. Each bar is a block of time."
        case .piano: return "Write or edit the melody for the selected track, one note at a time."
        case .mixer: return "Set how loud each track is and where it sits left to right."
        case .plugins: return "Turn effects like reverb and compression on or off for the selected track."
        case .sample: return "Trim, pitch, and reverse the audio file on the selected track."
        case .recipe: return "The step-by-step production checklist for this song."
        }
    }

    public var symbolName: String {
        switch self {
        case .playlist: return "rectangle.split.3x1"
        case .piano: return "pianokeys"
        case .mixer: return "slider.vertical.3"
        case .plugins: return "wand.and.rays"
        case .sample: return "waveform"
        case .recipe: return "checklist"
        }
    }

    public var keyEquivalent: String {
        switch self {
        case .playlist: return "1"
        case .piano: return "2"
        case .mixer: return "3"
        case .plugins: return "4"
        case .sample: return "5"
        case .recipe: return "6"
        }
    }
}

/// Editing tools. Every case here does something real — a tool that had no
/// behavior was removed rather than left on screen as decoration.
public enum ToolId: String, CaseIterable {
    case select
    case draw
    case erase

    public var label: String {
        switch self {
        case .select: return "Select"
        case .draw: return "Draw"
        case .erase: return "Erase"
        }
    }

    public var explanation: String {
        switch self {
        case .select: return "Click to select. Drag to move. Drag an edge to resize."
        case .draw: return "Click an empty spot to create a new clip or note."
        case .erase: return "Click a clip or note to delete it."
        }
    }

    public var symbolName: String {
        switch self {
        case .select: return "cursorarrow"
        case .draw: return "pencil"
        case .erase: return "eraser"
        }
    }
}
