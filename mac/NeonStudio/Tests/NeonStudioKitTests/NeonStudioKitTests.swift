import XCTest
import Foundation
@testable import NeonStudioKit

// Tests for NeonStudioKit: the model, the normalizer, the on-disk library, and
// the small amount of subprocess plumbing that has real logic in it.
//
// Several of these are regression tests for bugs the rewrite fixed, and say so:
// silent project overwrites, daily-colliding ids, and legacy notes leaking
// across tracks.

// MARK: - Fixtures

private enum Fixtures {

    static func track(
        _ id: String,
        name: String? = nil,
        kind: String? = nil,
        file: String? = nil,
        gain: Double? = nil,
        pan: Double? = nil,
        clips: [Clip]? = nil
    ) -> Track {
        Track(
            id: id,
            name: name ?? id.capitalized,
            kind: kind,
            file: file,
            color: "#4ad9d9",
            gain: gain,
            pan: pan,
            clips: clips
        )
    }

    static func clip(_ id: String, start: Double, bars: Double) -> Clip {
        Clip(id: id, name: id.capitalized, startBar: start, bars: bars, lane: nil, color: nil, type: nil)
    }

    static func note(
        _ id: String,
        beat: Double = 0,
        duration: Double = 1,
        pitch: Int = 60,
        velocity: Double = 0.8,
        trackId: String? = nil
    ) -> PianoNote {
        PianoNote(
            id: id,
            beat: beat,
            duration: duration,
            note: pitch,
            velocity: velocity,
            color: "#f26bd8",
            trackId: trackId
        )
    }

    static func control(
        gain: Double = MixerControl.neutral.gain,
        pan: Double = 0,
        mute: Bool = false,
        solo: Bool = false,
        arm: Bool = false
    ) -> MixerControl {
        MixerControl(gain: gain, pan: pan, mute: mute, solo: solo, arm: arm, sendA: 0.15, sendB: 0.08)
    }

    /// A project whose optionals are all nil, as an older file would decode.
    static func bare(id: String = "bare-song") -> LocalProject {
        LocalProject(
            id: id,
            name: "Bare Song",
            updatedAt: "2026-01-01T00:00:00Z",
            snapshot: ProjectSnapshot(
                bpm: 100,
                tracks: [track("drums", name: "Drums"), track("bass", name: "Bass")]
            )
        )
    }

    /// A project with something wrong in nearly every field, used to prove the
    /// normalizer both repairs and settles (idempotence).
    static func messy() -> LocalProject {
        LocalProject(
            id: "Messy Song!!",
            name: "   ",
            createdAt: nil,
            updatedAt: "2026-02-02T12:00:00Z",
            snapshot: ProjectSnapshot(
                version: 2,
                bpm: 128,
                swing: nil,
                snap: nil,
                loopEnabled: nil,
                loopStartBar: -4,
                loopEndBar: 2,
                tracks: [
                    track("lead", name: "Lead", kind: "audio", file: "exports/lead.wav",
                          clips: [clip("lead-a", start: -3, bars: 0.01)]),
                    track("sweep", name: "Auto Filter Sweep", kind: "automation")
                ],
                controls: [
                    "lead": control(gain: 0.31, pan: -0.5),
                    "ghost": control(gain: 0.99)
                ],
                automationLanes: [
                    AutomationLane(
                        id: "lane-live",
                        trackId: "sweep",
                        parameter: "filter",
                        label: "Sweep Filter",
                        color: nil,
                        enabled: nil,
                        curve: nil,
                        points: [
                            AutomationPoint(bar: 12, value: 3.5),
                            AutomationPoint(bar: -1, value: -2)
                        ]
                    ),
                    AutomationLane(
                        id: "lane-orphan",
                        trackId: "ghost",
                        parameter: "gain",
                        label: "Ghost Volume",
                        points: [AutomationPoint(bar: 0, value: 0.5)]
                    )
                ],
                notes: [
                    note("n-legacy", beat: -2, duration: 0.001, pitch: 900, velocity: 4),
                    note("n-lead", trackId: "lead"),
                    note("n-ghost", trackId: "ghost")
                ],
                selectedTrackId: "lead",
                selectedClipId: "clip-that-vanished",
                activeView: "not-a-view",
                patternIndex: 500,
                arrangementMode: "weird",
                recipe: nil
            )
        )
    }
}

// MARK: - Normalization

final class ProjectNormalizerTests: XCTestCase {

    func testNormalizeIsIdempotent() {
        let once = ProjectNormalizer.normalize(Fixtures.messy())
        let twice = ProjectNormalizer.normalize(once)
        XCTAssertEqual(once, twice, "Normalizing an already-normalized project must not change it.")
    }

    func testNormalizeIsIdempotentForBareProject() {
        let once = ProjectNormalizer.normalize(Fixtures.bare())
        let twice = ProjectNormalizer.normalize(once)
        XCTAssertEqual(once, twice)
    }

    func testNormalizeFillsEveryOptionalTheUIDependsOn() throws {
        let project = ProjectNormalizer.normalize(Fixtures.bare())
        let snapshot = project.snapshot

        XCTAssertEqual(snapshot.version, neonSnapshotVersion)
        XCTAssertNotNil(snapshot.controls)
        XCTAssertNotNil(snapshot.automationLanes)
        XCTAssertNotNil(snapshot.notes)
        XCTAssertNotNil(snapshot.recipe)
        XCTAssertEqual(snapshot.swing, 0)
        XCTAssertEqual(snapshot.snap, "1/4")
        XCTAssertEqual(snapshot.loopEnabled, false)
        XCTAssertEqual(snapshot.loopStartBar, 0)
        XCTAssertEqual(snapshot.loopEndBar, 16)
        XCTAssertEqual(snapshot.selectedTrackId, "drums")
        XCTAssertEqual(snapshot.selectedClipId, "")
        XCTAssertEqual(snapshot.activeView, WorkView.playlist.rawValue)
        XCTAssertEqual(snapshot.patternIndex, 1)
        XCTAssertEqual(snapshot.arrangementMode, "song")

        let controls = try XCTUnwrap(snapshot.controls)
        XCTAssertEqual(controls.count, 2)
        XCTAssertNotNil(controls["drums"])
        XCTAssertNotNil(controls["bass"])

        // createdAt is backfilled so the UI never shows a blank "created" date.
        XCTAssertEqual(project.createdAt, project.updatedAt)
    }

    func testNormalizeRepairsIdNameAndOutOfRangeValues() {
        let project = ProjectNormalizer.normalize(Fixtures.messy())

        XCTAssertEqual(project.id, "Messy-Song")
        XCTAssertEqual(project.name, "Untitled Project", "A blank name must become something showable.")
        XCTAssertEqual(project.snapshot.activeView, WorkView.playlist.rawValue)
        XCTAssertEqual(project.snapshot.patternIndex, 99, "patternIndex clamps to 1...99.")
        XCTAssertEqual(project.snapshot.arrangementMode, "song")
        XCTAssertEqual(project.snapshot.recipe?.isEmpty, true)
        XCTAssertEqual(project.snapshot.version, neonSnapshotVersion)

        let clip = project.snapshot.tracks[0].clips?.first
        XCTAssertEqual(clip?.startBar, 0, "A negative start bar clamps to the top of the song.")
        XCTAssertEqual(clip?.bars, 0.25, "A clip is never shorter than the minimum grid size.")
    }

    func testNormalizeAlwaysLeavesLoopEndAfterLoopStart() {
        var project = Fixtures.bare()
        project.snapshot.loopStartBar = 20
        project.snapshot.loopEndBar = 4

        let normalized = ProjectNormalizer.normalize(project)
        let start = normalized.snapshot.loopStartBar ?? -1
        let end = normalized.snapshot.loopEndBar ?? -1

        XCTAssertEqual(start, 20)
        XCTAssertGreaterThan(end, start, "An inverted loop range would make the loop brace undraggable.")
    }

    func testNormalizeClampsNegativeLoopStartAndStillOrdersTheRange() {
        let normalized = ProjectNormalizer.normalize(Fixtures.messy())
        let start = normalized.snapshot.loopStartBar ?? -1
        let end = normalized.snapshot.loopEndBar ?? -1

        XCTAssertEqual(start, 0)
        XCTAssertGreaterThan(end, start)
    }

    func testNormalizeClearsSelectedClipIdThatNamesNoClip() {
        var project = Fixtures.bare()
        project.snapshot.tracks[0].clips = [Fixtures.clip("real-clip", start: 0, bars: 4)]
        project.snapshot.selectedClipId = "clip-that-vanished"

        XCTAssertEqual(ProjectNormalizer.normalize(project).snapshot.selectedClipId, "")

        project.snapshot.selectedClipId = "real-clip"
        XCTAssertEqual(ProjectNormalizer.normalize(project).snapshot.selectedClipId, "real-clip")
    }

    func testNormalizeFallsBackToFirstTrackWhenSelectionIsStale() {
        var project = Fixtures.bare()
        project.snapshot.selectedTrackId = "a-track-that-was-deleted"

        XCTAssertEqual(ProjectNormalizer.normalize(project).snapshot.selectedTrackId, "drums")
    }

    // MARK: Legacy note migration

    func testLegacyNotesWithoutTrackIdAreAdoptedOntoTheSelectedTrack() throws {
        var project = Fixtures.bare()
        project.snapshot.selectedTrackId = "bass"
        project.snapshot.notes = [Fixtures.note("legacy-1"), Fixtures.note("legacy-2")]

        let normalized = ProjectNormalizer.normalize(project)
        let notes = try XCTUnwrap(normalized.snapshot.notes)

        XCTAssertEqual(notes.count, 2)
        XCTAssertTrue(notes.allSatisfy { $0.trackId == "bass" })
    }

    func testNotesNamingAMissingTrackAreDroppedRatherThanReassigned() throws {
        var project = Fixtures.bare()
        project.snapshot.notes = [
            Fixtures.note("keep", trackId: "drums"),
            Fixtures.note("orphan", trackId: "a-track-that-was-deleted")
        ]

        let normalized = ProjectNormalizer.normalize(project)
        let notes = try XCTUnwrap(normalized.snapshot.notes)

        XCTAssertEqual(notes.map(\.id), ["keep"], "An orphaned note must not land on an unrelated instrument.")
    }

    func testMigratedNotesAreSeparatedPerTrack() {
        var project = Fixtures.bare()
        project.snapshot.selectedTrackId = "drums"
        project.snapshot.notes = [
            Fixtures.note("legacy"),                       // adopted onto "drums"
            Fixtures.note("bass-1", trackId: "bass"),
            Fixtures.note("bass-2", trackId: "bass")
        ]

        let normalized = ProjectNormalizer.normalize(project)

        XCTAssertEqual(normalized.notes(forTrack: "drums").map(\.id), ["legacy"])
        XCTAssertEqual(normalized.notes(forTrack: "bass").map(\.id), ["bass-1", "bass-2"])
        XCTAssertNotEqual(
            normalized.notes(forTrack: "drums").map(\.id),
            normalized.notes(forTrack: "bass").map(\.id),
            "Pre-v4 files shared one note pool; switching tracks must no longer show the same notes."
        )
    }

    func testNoteValuesAreClampedIntoPlayableRanges() throws {
        let normalized = ProjectNormalizer.normalize(Fixtures.messy())
        let note = try XCTUnwrap(normalized.snapshot.notes?.first { $0.id == "n-legacy" })

        XCTAssertEqual(note.trackId, "lead")
        XCTAssertEqual(note.beat, 0)
        XCTAssertEqual(note.duration, 0.0625)
        XCTAssertEqual(note.note, 127)
        XCTAssertEqual(note.velocity, 1)
    }

    // MARK: Controls

    func testUserSetControlValuesSurviveNormalization() throws {
        var project = Fixtures.bare()
        project.snapshot.tracks[0].gain = 0.5   // the track's own default
        project.snapshot.controls = ["drums": Fixtures.control(gain: 0.31, pan: -0.75, mute: true)]

        let normalized = ProjectNormalizer.normalize(project)
        let drums = try XCTUnwrap(normalized.snapshot.controls?["drums"])

        XCTAssertEqual(drums.gain, 0.31, accuracy: 1e-9, "A hand-set fader must not snap back to the default.")
        XCTAssertEqual(drums.pan, -0.75, accuracy: 1e-9)
        XCTAssertTrue(drums.mute)
    }

    func testControlsForDeletedTracksAreRemoved() {
        let normalized = ProjectNormalizer.normalize(Fixtures.messy())

        XCTAssertNil(normalized.snapshot.controls?["ghost"])
        XCTAssertEqual(Set(normalized.snapshot.controls?.keys.map { $0 } ?? []), ["lead", "sweep"])
    }

    func testNewTrackGainsANeutralControl() throws {
        var project = ProjectNormalizer.normalize(Fixtures.bare())
        project.snapshot.tracks.append(Fixtures.track("keys", name: "Keys"))

        let normalized = ProjectNormalizer.normalize(project)
        let keys = try XCTUnwrap(normalized.snapshot.controls?["keys"])

        XCTAssertEqual(keys.gain, MixerControl.neutral.gain, accuracy: 1e-9)
        XCTAssertEqual(keys.pan, 0, accuracy: 1e-9)
        XCTAssertFalse(keys.mute)
        XCTAssertFalse(keys.solo)
        XCTAssertFalse(keys.arm)
    }

    // MARK: Automation lanes

    func testOrphanedAutomationLanesAreDroppedAndSurvivorsAreCleanedUp() throws {
        let normalized = ProjectNormalizer.normalize(Fixtures.messy())
        let lanes = try XCTUnwrap(normalized.snapshot.automationLanes)

        XCTAssertEqual(lanes.map(\.id), ["lane-live"], "A lane pointing at a deleted track must not be re-homed.")

        let lane = try XCTUnwrap(lanes.first)
        XCTAssertEqual(lane.enabled, true)
        XCTAssertEqual(lane.curve, "linear")
        XCTAssertEqual(lane.points.map(\.bar), [0, 12], "Points are sorted and negative bars clamp to 0.")
        XCTAssertEqual(lane.points.map(\.value), [0, 1], "Values clamp into 0...1.")
    }

    func testAutomationLanesAreSynthesizedForAutomationTracksWhenAbsent() throws {
        var project = Fixtures.bare()
        project.snapshot.tracks.append(Fixtures.track("sweep", name: "Filter Sweep", kind: "automation"))
        project.snapshot.automationLanes = nil

        let lanes = try XCTUnwrap(ProjectNormalizer.normalize(project).snapshot.automationLanes)

        XCTAssertEqual(lanes.count, 1)
        XCTAssertEqual(lanes.first?.trackId, "sweep")
        XCTAssertEqual(lanes.first?.parameter, "filter")
    }
}

// MARK: - SnapValue

final class SnapValueTests: XCTestCase {

    func testParseMapsKnownRawValue() {
        XCTAssertEqual(SnapValue.parse("1/4"), .quarter)
        XCTAssertEqual(SnapValue.parse("1/1"), .bar)
        XCTAssertEqual(SnapValue.parse("1/16"), .sixteenth)
        XCTAssertEqual(SnapValue.parse("none"), SnapValue.none)
    }

    func testParseFallsBackToQuarterForUnknownAndNil() {
        XCTAssertEqual(SnapValue.parse(nil), .quarter)
        XCTAssertEqual(SnapValue.parse("triplets"), .quarter)
        XCTAssertEqual(SnapValue.parse(""), .quarter)
    }

    func testSnapBarsRoundsToTheNearestGridLine() {
        XCTAssertEqual(SnapValue.quarter.snap(bars: 0.3), 0.25, accuracy: 1e-9)
        XCTAssertEqual(SnapValue.quarter.snap(bars: 0.4), 0.5, accuracy: 1e-9)
        XCTAssertEqual(SnapValue.bar.snap(bars: 3.49), 3, accuracy: 1e-9)
        XCTAssertEqual(SnapValue.bar.snap(bars: 3.51), 4, accuracy: 1e-9)
        XCTAssertEqual(SnapValue.sixteenth.snap(bars: 0.1), 0.125, accuracy: 1e-9)
    }

    func testSnapNonePassesTheValueThroughButStillClampsNegatives() {
        XCTAssertEqual(SnapValue.none.snap(bars: 3.37), 3.37, accuracy: 1e-9)
        XCTAssertEqual(SnapValue.none.snap(bars: -5), 0, accuracy: 1e-9)
        XCTAssertEqual(SnapValue.none.snap(beats: 9.13), 9.13, accuracy: 1e-9)
        XCTAssertEqual(SnapValue.none.snap(beats: -1), 0, accuracy: 1e-9)
    }

    func testSnapNeverReturnsANegativeBar() {
        for value in SnapValue.allCases {
            XCTAssertGreaterThanOrEqual(value.snap(bars: -12.5), 0, "\(value) produced a negative bar")
            XCTAssertGreaterThanOrEqual(value.snap(beats: -12.5), 0, "\(value) produced a negative beat")
        }
    }

    func testBeatsIsFourTimesBars() {
        for value in SnapValue.allCases {
            XCTAssertEqual(value.beats, value.bars * 4, accuracy: 1e-9, "\(value) has an inconsistent beat grid")
        }
    }

    func testSnapBeatsRoundsToTheNearestBeatGrid() {
        XCTAssertEqual(SnapValue.quarter.snap(beats: 1.4), 1, accuracy: 1e-9)   // grid = 1 beat
        XCTAssertEqual(SnapValue.quarter.snap(beats: 1.6), 2, accuracy: 1e-9)
        XCTAssertEqual(SnapValue.eighth.snap(beats: 0.3), 0.5, accuracy: 1e-9)  // grid = 0.5 beats
    }

    func testEveryCaseHasALabel() {
        for value in SnapValue.allCases {
            XCTAssertFalse(value.label.isEmpty)
        }
    }
}

// MARK: - Identifiers

final class IdentifierTests: XCTestCase {

    func testSafeProjectIdStripsPathComponentsAndProjectSuffix() {
        XCTAssertEqual(safeProjectId("/Users/someone/Music/cool-song.neon.json"), "cool-song")
        XCTAssertEqual(safeProjectId("cool-song.neon.json"), "cool-song")
        XCTAssertEqual(safeProjectId("data/projects/neon-alone.neon.json"), "neon-alone")
    }

    func testSafeProjectIdReplacesDisallowedCharacters() {
        XCTAssertEqual(safeProjectId("My Song!"), "My-Song")
        XCTAssertEqual(safeProjectId("drum kit:v2"), "drum-kit-v2")
        XCTAssertEqual(safeProjectId("verse 1 (rough)"), "verse-1--rough")
        XCTAssertEqual(safeProjectId("neon_alone-2"), "neon_alone-2", "Letters, digits, - and _ are kept as-is.")
    }

    func testSafeProjectIdTrimsLeadingAndTrailingSeparators() {
        XCTAssertEqual(safeProjectId("--lead--"), "lead")
        XCTAssertEqual(safeProjectId("__lead__"), "lead")
        XCTAssertEqual(safeProjectId("-_lead-_"), "lead")
    }

    func testSafeProjectIdCapsLengthAtSeventyTwo() {
        let long = String(repeating: "a", count: 200)
        XCTAssertEqual(safeProjectId(long).count, 72)
    }

    func testSafeProjectIdNeverReturnsAnEmptyString() {
        let generated = safeProjectId("@@@")
        XCTAssertFalse(generated.isEmpty)
        XCTAssertTrue(generated.hasPrefix("project-"))

        XCTAssertFalse(safeProjectId("...").isEmpty)
        XCTAssertFalse(safeProjectId("---").isEmpty)
    }

    func testSafeProjectIdIsStableWhenAppliedTwice() {
        for raw in ["My Song!", "/tmp/a b/c.neon.json", "--lead--", String(repeating: "z", count: 200)] {
            let once = safeProjectId(raw)
            XCTAssertEqual(safeProjectId(once), once, "safeProjectId must be stable for \(raw)")
        }
    }

    /// Regression: the old implementation formatted "HHmmss" only, so two ids
    /// minted at the same clock time on different days collided.
    func testTimestampForIdIncludesTheDate() {
        let day1 = Date(timeIntervalSince1970: 1_700_000_000)
        let day2 = day1.addingTimeInterval(24 * 60 * 60)

        let first = timestampForId(day1)
        let second = timestampForId(day2)

        XCTAssertNotEqual(first, second, "Ids minted 24 hours apart must differ.")
        XCTAssertEqual(
            String(first.suffix(6)),
            String(second.suffix(6)),
            "The time-of-day portion is identical, which is exactly what used to collide."
        )
        XCTAssertNotEqual(String(first.prefix(8)), String(second.prefix(8)))
        XCTAssertEqual(first.count, 15)   // yyyyMMdd-HHmmss
    }

    func testTimestampForIdIsDeterministicForTheSameDate() {
        let date = Date(timeIntervalSince1970: 1_700_000_000)
        XCTAssertEqual(timestampForId(date), timestampForId(date))
    }

    func testTimestampForIdContainsOnlyIdSafeCharacters() {
        let stamp = timestampForId(Date(timeIntervalSince1970: 1_700_000_000))
        XCTAssertEqual(safeProjectId(stamp), stamp)
    }

    func testMakeIdIsUniqueAcrossManyCalls() {
        let ids = (0..<1000).map { _ in makeId("clip") }
        XCTAssertEqual(Set(ids).count, ids.count, "makeId collided.")
        XCTAssertTrue(ids.allSatisfy { $0.hasPrefix("clip-") })
    }

    func testMakeIdUsesTheGivenPrefix() {
        XCTAssertTrue(makeId("note").hasPrefix("note-"))
        XCTAssertTrue(makeId("auto").hasPrefix("auto-"))
    }
}

// MARK: - Derived project values

final class LocalProjectDerivedValueTests: XCTestCase {

    func testContentEndBarUsesTheFurthestClipEnd() {
        var project = Fixtures.bare()
        project.snapshot.tracks[0].clips = [
            Fixtures.clip("a", start: 0, bars: 4),
            Fixtures.clip("b", start: 8, bars: 6)     // ends at 14
        ]
        project.snapshot.tracks[1].clips = [Fixtures.clip("c", start: 2, bars: 3)]

        XCTAssertEqual(project.contentEndBar, 14, accuracy: 1e-9)
    }

    func testContentEndBarAlsoAccountsForAutomationPoints() {
        var project = Fixtures.bare()
        project.snapshot.tracks[0].clips = [Fixtures.clip("a", start: 0, bars: 4)]
        project.snapshot.automationLanes = [
            AutomationLane(
                id: "lane",
                trackId: "drums",
                parameter: "gain",
                label: "Drums Volume",
                points: [AutomationPoint(bar: 2, value: 0.2), AutomationPoint(bar: 22, value: 0.9)]
            )
        ]

        XCTAssertEqual(project.contentEndBar, 22, accuracy: 1e-9, "Automation extends the timeline too.")
    }

    func testContentEndBarIsZeroForAnEmptyProject() {
        XCTAssertEqual(Fixtures.bare().contentEndBar, 0, accuracy: 1e-9)
    }

    func testSecondsPerBarAtOneTwentyBPM() {
        var project = Fixtures.bare()
        project.snapshot.bpm = 120
        XCTAssertEqual(project.secondsPerBar, 2.0, accuracy: 1e-9)

        project.snapshot.bpm = 60
        XCTAssertEqual(project.secondsPerBar, 4.0, accuracy: 1e-9)
    }

    func testSecondsPerBarFallsBackInsteadOfDividingByZero() {
        var project = Fixtures.bare()

        project.snapshot.bpm = 0
        XCTAssertEqual(project.secondsPerBar, 2.0, accuracy: 1e-9, "Zero BPM must fall back to 120.")
        XCTAssertTrue(project.secondsPerBar.isFinite)

        project.snapshot.bpm = -45
        XCTAssertEqual(project.secondsPerBar, 2.0, accuracy: 1e-9)
        XCTAssertTrue(project.secondsPerBar.isFinite)
    }

    func testTrackLookupAndControlFallback() {
        var project = Fixtures.bare()
        project.snapshot.controls = ["drums": Fixtures.control(gain: 0.4)]

        XCTAssertEqual(project.track(id: "bass")?.name, "Bass")
        XCTAssertNil(project.track(id: "nope"))
        XCTAssertEqual(project.control(for: "drums").gain, 0.4, accuracy: 1e-9)
        XCTAssertEqual(project.control(for: "nope"), MixerControl.neutral, "Unknown tracks read as neutral.")
    }

    func testMutedTrackIsNotAudible() {
        var project = Fixtures.bare()
        project.snapshot.controls = [
            "drums": Fixtures.control(mute: true),
            "bass": Fixtures.control()
        ]

        XCTAssertFalse(project.isAudible("drums"))
        XCTAssertTrue(project.isAudible("bass"))
    }

    func testWithNoSoloEveryUnmutedTrackIsAudible() {
        var project = Fixtures.bare()
        project.snapshot.controls = ["drums": Fixtures.control(), "bass": Fixtures.control()]

        XCTAssertFalse(project.anyTrackSoloed)
        XCTAssertTrue(project.isAudible("drums"))
        XCTAssertTrue(project.isAudible("bass"))
    }

    func testSoloSilencesEveryOtherTrack() {
        var project = Fixtures.bare()
        project.snapshot.tracks.append(Fixtures.track("keys", name: "Keys"))
        project.snapshot.controls = [
            "drums": Fixtures.control(),
            "bass": Fixtures.control(solo: true),
            "keys": Fixtures.control()
        ]

        XCTAssertTrue(project.anyTrackSoloed)
        XCTAssertTrue(project.isAudible("bass"))
        XCTAssertFalse(project.isAudible("drums"))
        XCTAssertFalse(project.isAudible("keys"))
    }

    func testMuteBeatsSoloOnTheSameTrack() {
        var project = Fixtures.bare()
        project.snapshot.controls = [
            "drums": Fixtures.control(mute: true, solo: true),
            "bass": Fixtures.control(solo: true)
        ]

        XCTAssertFalse(project.isAudible("drums"), "A muted track stays silent even when it is also soloed.")
        XCTAssertTrue(project.isAudible("bass"))
    }
}

// MARK: - ProjectStore

final class ProjectStoreTests: XCTestCase {

    private var root: URL!
    private var store: ProjectStore!

    override func setUpWithError() throws {
        try super.setUpWithError()
        root = URL(fileURLWithPath: NSTemporaryDirectory(), isDirectory: true)
            .appendingPathComponent("NeonStudioKitTests-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        store = ProjectStore(rootURL: root)
    }

    override func tearDownWithError() throws {
        if let root, FileManager.default.fileExists(atPath: root.path) {
            try FileManager.default.removeItem(at: root)
        }
        store = nil
        root = nil
        try super.tearDownWithError()
    }

    // MARK: Helpers

    private func makeProject(id: String, name: String, updatedAt: String = "2026-01-01T00:00:00Z") -> LocalProject {
        LocalProject(
            id: id,
            name: name,
            createdAt: updatedAt,
            updatedAt: updatedAt,
            snapshot: ProjectSnapshot(
                bpm: 120,
                tracks: [Fixtures.track("drums", name: "Drums", clips: [Fixtures.clip("c1", start: 0, bars: 4)])]
            )
        )
    }

    private func writeFile(_ data: Data, to url: URL) throws {
        try FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try data.write(to: url, options: [.atomic])
    }

    /// Writes projects into `factory/projects/` plus the index the store reads.
    private func installFactoryProjects(_ projects: [LocalProject]) throws {
        var entries: [String] = []
        for project in projects {
            let relative = "projects/\(project.id).neon.json"
            try writeFile(
                try store.encode(project),
                to: root.appendingPathComponent("factory").appendingPathComponent(relative)
            )
            entries.append("{\"id\": \"\(project.id)\", \"file\": \"\(relative)\"}")
        }
        let json = "{\"projects\": [\(entries.joined(separator: ", "))]}"
        try writeFile(
            Data(json.utf8),
            to: root.appendingPathComponent("factory/projects/index.json")
        )
    }

    private func markDeleted(_ ids: [String]) throws {
        let json = "[\(ids.map { "\"\($0)\"" }.joined(separator: ", "))]"
        try writeFile(Data(json.utf8), to: store.deletedURL())
    }

    private func touchFile(at url: URL) throws {
        try writeFile(Data("not really audio".utf8), to: url)
    }

    // MARK: Encoding

    func testEncodeDecodeRoundTripPreservesTheProject() throws {
        let project = makeProject(id: "round-trip", name: "Round Trip")
        let expected = ProjectNormalizer.normalize(project)

        let decoded = try store.decode(try store.encode(project), fallbackName: "round-trip.neon.json")

        XCTAssertEqual(decoded, expected)
    }

    func testDecodeAcceptsTheBareLocalProjectShape() throws {
        let project = makeProject(id: "bare-shape", name: "Bare Shape")
        let data = try JSONEncoder().encode(project)

        let decoded = try store.decode(data, fallbackName: "bare-shape.neon.json")

        XCTAssertEqual(decoded.id, "bare-shape")
        XCTAssertEqual(decoded.name, "Bare Shape")
        XCTAssertEqual(decoded.snapshot.version, neonSnapshotVersion, "decode normalizes on the way in.")
    }

    func testDecodeAcceptsTheEnvelopeShape() throws {
        let project = makeProject(id: "envelope-shape", name: "Envelope Shape")
        let data = try JSONEncoder().encode(ProjectFileEnvelope(project: project))

        let decoded = try store.decode(data, fallbackName: "envelope-shape.neon.json")

        XCTAssertEqual(decoded.id, "envelope-shape")
        XCTAssertEqual(decoded.name, "Envelope Shape")
        XCTAssertEqual(decoded.snapshot.tracks.count, 1)
    }

    func testDecodeThrowsNotANeonProjectForUnrelatedJSON() {
        let data = Data(#"{"hello": "world", "items": [1, 2, 3]}"#.utf8)

        XCTAssertThrowsError(try store.decode(data, fallbackName: "shopping-list.json")) { error in
            guard case ProjectStoreError.notANeonProject = error else {
                return XCTFail("Expected notANeonProject, got \(error)")
            }
        }
    }

    func testDecodeThrowsNotANeonProjectForNonJSONData() {
        let data = Data("this file is a wav, not a project".utf8)

        XCTAssertThrowsError(try store.decode(data, fallbackName: "kick.wav")) { error in
            guard case ProjectStoreError.notANeonProject = error else {
                return XCTFail("Expected notANeonProject, got \(error)")
            }
        }
    }

    func testProjectStoreErrorsExplainThemselvesInPlainLanguage() {
        let error = ProjectStoreError.notANeonProject(URL(fileURLWithPath: "/tmp/kick.wav"))
        XCTAssertEqual(error.errorDescription?.isEmpty, false)
        XCTAssertEqual(error.recoverySuggestion?.isEmpty, false)
        XCTAssertEqual(ProjectStoreError.unreadableProjectFile(URL(fileURLWithPath: "/tmp/x")).errorDescription?.isEmpty, false)
    }

    // MARK: Unique ids

    func testUniqueProjectIdReturnsTheCandidateWhenItIsFree() {
        XCTAssertEqual(store.uniqueProjectId(basedOn: "my-song"), "my-song")
    }

    /// Regression: the store used to overwrite whatever file already held the id.
    func testUniqueProjectIdAppendsASuffixInsteadOfOverwriting() throws {
        try writeFile(try store.encode(makeProject(id: "my-song", name: "Mine")), to: store.projectURL(for: "my-song"))

        XCTAssertEqual(store.uniqueProjectId(basedOn: "my-song"), "my-song-2")

        try writeFile(try store.encode(makeProject(id: "my-song-2", name: "Mine 2")), to: store.projectURL(for: "my-song-2"))
        XCTAssertEqual(store.uniqueProjectId(basedOn: "my-song"), "my-song-3")
    }

    func testUniqueProjectIdSanitizesTheCandidateFirst() {
        XCTAssertEqual(store.uniqueProjectId(basedOn: "My Song!"), "My-Song")
    }

    func testSaveProjectWritesToTheExpectedLocationAndNormalizes() throws {
        let saved = try store.saveProject(makeProject(id: "saved-song", name: "Saved Song"))

        XCTAssertEqual(saved.snapshot.version, neonSnapshotVersion)
        XCTAssertTrue(FileManager.default.fileExists(atPath: store.projectURL(for: "saved-song").path))

        let reloaded = try XCTUnwrap(store.loadProject(from: store.projectURL(for: "saved-song")))
        XCTAssertEqual(reloaded, saved)
    }

    // MARK: Audio paths

    func testAudioURLResolvesAbsolutePaths() throws {
        let track = Fixtures.track("lead", file: "/Users/test/audio/kick.wav")
        let url = try XCTUnwrap(store.audioURL(for: track))

        XCTAssertTrue(url.isFileURL)
        XCTAssertEqual(url.path, "/Users/test/audio/kick.wav")
    }

    func testAudioURLResolvesFileURLs() throws {
        let track = Fixtures.track("lead", file: "file:///Users/test/audio/snare.wav")
        let url = try XCTUnwrap(store.audioURL(for: track))

        XCTAssertTrue(url.isFileURL)
        XCTAssertEqual(url.path, "/Users/test/audio/snare.wav")
    }

    func testAudioURLResolvesLegacyAPIAudioPathsIntoExports() throws {
        let track = Fixtures.track("lead", file: "/api/audio/neon_alone_lead.wav")
        let url = try XCTUnwrap(store.audioURL(for: track))

        XCTAssertEqual(url.path, store.exportsDirectory().appendingPathComponent("neon_alone_lead.wav").path)
    }

    func testAudioURLResolvesRelativePathsAgainstTheRoot() throws {
        let track = Fixtures.track("lead", file: "exports/bass.wav")
        let url = try XCTUnwrap(store.audioURL(for: track))

        XCTAssertEqual(url.path, store.exportsDirectory().appendingPathComponent("bass.wav").path)
    }

    func testAudioURLIsNilWhenTheTrackHasNoFile() {
        XCTAssertNil(store.audioURL(for: Fixtures.track("silent")))
        XCTAssertNil(store.audioURL(for: Fixtures.track("silent", file: "")))
    }

    func testExistingAudioURLOnlyReturnsFilesThatAreReallyThere() throws {
        try touchFile(at: store.exportsDirectory().appendingPathComponent("kick.wav"))

        XCTAssertNotNil(store.existingAudioURL(for: Fixtures.track("kick", file: "exports/kick.wav")))
        XCTAssertNil(store.existingAudioURL(for: Fixtures.track("ghost", file: "exports/ghost.wav")))
    }

    func testAudioTrackCountsCountsOnlyTracksWhoseFileExists() throws {
        try touchFile(at: store.exportsDirectory().appendingPathComponent("kick.wav"))
        try touchFile(at: store.exportsDirectory().appendingPathComponent("bass.wav"))

        var project = makeProject(id: "counts", name: "Counts")
        project.snapshot.tracks = [
            Fixtures.track("kick", file: "exports/kick.wav"),
            Fixtures.track("bass", file: "exports/bass.wav"),
            Fixtures.track("lead", file: "exports/lead.wav"),   // never written
            Fixtures.track("silent")                            // no file at all
        ]

        let counts = store.audioTrackCounts(for: project)

        XCTAssertEqual(counts.withAudio, 2)
        XCTAssertEqual(counts.total, 4)
    }

    func testFullMixURLIsNilUntilTheMixExists() throws {
        let project = makeProject(id: "neon-alone", name: "Neon Alone")
        XCTAssertNil(store.fullMixURL(for: project))

        try touchFile(at: store.exportsDirectory().appendingPathComponent("neon_alone_full_mix.wav"))
        XCTAssertNotNil(store.fullMixURL(for: project))
    }

    // MARK: Library

    func testLoadProjectsMergesFactoryAndStoredProjects() throws {
        try installFactoryProjects([
            makeProject(id: "factory-a", name: "Factory A", updatedAt: "2026-03-01T00:00:00Z")
        ])
        try store.saveProject(makeProject(id: "mine", name: "Mine", updatedAt: "2026-03-02T00:00:00Z"))

        let projects = store.loadProjects()

        XCTAssertEqual(Set(projects.map(\.id)), ["factory-a", "mine"])
        XCTAssertEqual(projects.first?.id, "mine", "The most recently updated project sorts first.")
    }

    func testLoadProjectsPrefersTheStoredCopyForASharedId() throws {
        try installFactoryProjects([
            makeProject(id: "shared", name: "Factory Version", updatedAt: "2026-01-01T00:00:00Z")
        ])
        try store.saveProject(makeProject(id: "shared", name: "My Version", updatedAt: "2026-04-01T00:00:00Z"))

        let projects = store.loadProjects()
        let shared = try XCTUnwrap(projects.first { $0.id == "shared" })

        XCTAssertEqual(projects.count, 1, "The factory copy must not appear alongside the user's edit.")
        XCTAssertEqual(shared.name, "My Version")
        XCTAssertEqual(shared.projectFile, "projects/shared.neon.json", "Factory metadata fills the gaps.")
    }

    func testLoadProjectsHonoursTheDeletedProjectsMarker() throws {
        try installFactoryProjects([
            makeProject(id: "factory-a", name: "Factory A"),
            makeProject(id: "factory-b", name: "Factory B")
        ])
        try markDeleted(["factory-b"])

        let ids = store.loadProjects().map(\.id)

        XCTAssertEqual(ids, ["factory-a"])
        XCTAssertEqual(store.hiddenFactoryProjectCount, 1)
    }

    func testRestoreDeletedFactoryProjectsBringsThemBack() throws {
        try installFactoryProjects([
            makeProject(id: "factory-a", name: "Factory A"),
            makeProject(id: "factory-b", name: "Factory B")
        ])
        try markDeleted(["factory-b"])
        XCTAssertEqual(store.loadProjects().count, 1)

        try store.restoreDeletedFactoryProjects()

        XCTAssertEqual(store.hiddenFactoryProjectCount, 0)
        XCTAssertEqual(Set(store.loadProjects().map(\.id)), ["factory-a", "factory-b"])
    }

    func testSavingAProjectUnhidesIt() throws {
        try installFactoryProjects([makeProject(id: "factory-a", name: "Factory A")])
        try markDeleted(["factory-a"])
        XCTAssertEqual(store.hiddenFactoryProjectCount, 1)

        try store.saveProject(makeProject(id: "factory-a", name: "Back Again"))

        XCTAssertEqual(store.hiddenFactoryProjectCount, 0)
    }

    func testLoadProjectsIsEmptyForAFreshLibrary() {
        XCTAssertTrue(store.loadProjects().isEmpty)
    }

    func testLoadProjectsSkipsUnreadableFilesRatherThanFailing() throws {
        try store.saveProject(makeProject(id: "good", name: "Good"))
        try writeFile(Data("{ not json".utf8), to: store.dataDirectory().appendingPathComponent("broken.neon.json"))

        XCTAssertEqual(store.loadProjects().map(\.id), ["good"])
    }

    func testImportProjectGivesTheCopyAFreshId() throws {
        let original = try store.saveProject(makeProject(id: "shared-name", name: "Shared Name"))
        let exportURL = root.appendingPathComponent("hand-off.neon.json")
        try store.exportProject(original, to: exportURL)

        let imported = try store.importProject(from: exportURL)

        XCTAssertEqual(imported.id, "shared-name-2", "Importing must never clobber the existing project.")
        XCTAssertTrue(FileManager.default.fileExists(atPath: store.projectURL(for: "shared-name").path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: store.projectURL(for: "shared-name-2").path))
    }

    func testImportProjectThrowsForAFileThatIsNotAProject() throws {
        let url = root.appendingPathComponent("notes.txt")
        try writeFile(Data("just some lyrics".utf8), to: url)

        XCTAssertThrowsError(try store.importProject(from: url)) { error in
            guard case ProjectStoreError.unreadableProjectFile = error else {
                return XCTFail("Expected unreadableProjectFile, got \(error)")
            }
        }
    }

    func testParseDateHandlesBothISOPrecisions() {
        let plain = ProjectStore.parseDate("2026-06-12T04:41:07Z")
        let fractional = ProjectStore.parseDate("2026-06-12T04:41:07.221Z")

        XCTAssertGreaterThan(fractional, plain, "Fractional seconds must sort after the whole second.")
        XCTAssertEqual(ProjectStore.parseDate(nil), .distantPast)
        XCTAssertEqual(ProjectStore.parseDate("whenever"), .distantPast)
    }

    func testLocationHelpersLiveUnderTheRoot() {
        XCTAssertTrue(store.dataDirectory().path.hasPrefix(root.path))
        XCTAssertTrue(store.exportsDirectory().path.hasPrefix(root.path))
        XCTAssertTrue(store.vocalInboxDirectory().path.hasPrefix(root.path))
        XCTAssertTrue(store.toolURL("daw_agent.py").path.hasPrefix(root.path))
        XCTAssertEqual(store.toolURL("daw_agent.py").lastPathComponent, "daw_agent.py")
        XCTAssertEqual(store.projectURL(for: "My Song!").lastPathComponent, "My-Song.neon.json")
    }
}

// MARK: - ToolResult

final class ToolResultTests: XCTestCase {

    private func result(stdout: String, exitCode: Int32 = 0) -> ToolResult {
        ToolResult(standardOutput: stdout, standardError: "", exitCode: exitCode)
    }

    func testLastJSONObjectFindsJSONFollowedByProgressLines() {
        let output = """
        Rendering stems...
        {"ok": true, "score": 86}
        Cleaning up temporary files
        Done.
        """

        let json = result(stdout: output).lastJSONObject

        XCTAssertEqual(json["ok"] as? Bool, true)
        XCTAssertEqual(json["score"] as? Int, 86)
    }

    func testLastJSONObjectToleratesBlankLinesAndIndentation() {
        let output = "\n\nrendering\n\n   {\"score\": 42}   \n\n\n"

        XCTAssertEqual(result(stdout: output).lastJSONObject["score"] as? Int, 42)
    }

    func testLastJSONObjectPrefersTheFinalObject() {
        let output = """
        {"stage": "one"}
        working
        {"stage": "two"}
        wrapping up
        """

        XCTAssertEqual(result(stdout: output).lastJSONObject["stage"] as? String, "two")
    }

    func testLastJSONObjectSkipsLinesThatOnlyLookLikeJSON() {
        let output = """
        {"stage": "real"}
        {this is not json}
        """

        XCTAssertEqual(result(stdout: output).lastJSONObject["stage"] as? String, "real")
    }

    func testLastJSONObjectIsEmptyWhenTheToolPrintedNoJSON() {
        XCTAssertTrue(result(stdout: "Rendering...\nDone.\n").lastJSONObject.isEmpty)
        XCTAssertTrue(result(stdout: "").lastJSONObject.isEmpty)
        XCTAssertTrue(result(stdout: "[1, 2, 3]").lastJSONObject.isEmpty, "A bare array is not a result object.")
    }

    func testSucceededTracksTheExitCode() {
        XCTAssertTrue(result(stdout: "", exitCode: 0).succeeded)
        XCTAssertFalse(result(stdout: "", exitCode: 1).succeeded)
        XCTAssertFalse(result(stdout: "", exitCode: -9).succeeded)
    }

    func testToolErrorsExplainThemselvesInPlainLanguage() {
        let errors: [ToolError] = [
            .missingExecutable("/usr/bin/python3"),
            .missingScript(URL(fileURLWithPath: "/tmp/tools/daw_agent.py")),
            .failed(name: "Sound check", exitCode: 2, standardError: "boom"),
            .cancelled(name: "Mixdown"),
            .noJSON(name: "Sound check")
        ]

        for error in errors {
            XCTAssertEqual(error.errorDescription?.isEmpty, false, "\(error) has no message")
        }
    }
}
