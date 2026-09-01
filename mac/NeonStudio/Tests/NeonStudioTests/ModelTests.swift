import Foundation
import NeonStudioKit

/// Normalization, migrations, snap maths, and identifiers.
enum ModelTests {

    private static func project(
        tracks: [Track],
        notes: [PianoNote]? = nil,
        controls: [String: MixerControl]? = nil,
        selectedTrackId: String? = nil,
        selectedClipId: String? = nil,
        loopStart: Double? = nil,
        loopEnd: Double? = nil
    ) -> LocalProject {
        LocalProject(
            id: "demo",
            name: "Demo",
            updatedAt: "2026-01-01T00:00:00Z",
            snapshot: ProjectSnapshot(
                bpm: 120,
                loopStartBar: loopStart,
                loopEndBar: loopEnd,
                tracks: tracks,
                controls: controls,
                notes: notes,
                selectedTrackId: selectedTrackId,
                selectedClipId: selectedClipId
            )
        )
    }

    static func run() {
        let t = TestRunner.shared
        t.section("Normalization")

        t.test("normalize is idempotent") {
            let raw = project(tracks: [Track(id: "a", name: "Lead")])
            let once = ProjectNormalizer.normalize(raw)
            let twice = ProjectNormalizer.normalize(once)
            expectTrue(once == twice, "normalizing twice differed from normalizing once")
        }

        t.test("normalize fills every optional the UI depends on") {
            let normalized = ProjectNormalizer.normalize(project(tracks: [Track(id: "a", name: "Lead")]))
            let snapshot = normalized.snapshot
            expectNotNil(snapshot.controls)
            expectNotNil(snapshot.automationLanes)
            expectNotNil(snapshot.notes)
            expectNotNil(snapshot.recipe)
            expectEqual(snapshot.snap, "1/4")
            expectEqual(snapshot.swing, 0)
            expectEqual(snapshot.loopEnabled, false)
            expectEqual(snapshot.activeView, WorkView.playlist.rawValue)
            expectEqual(snapshot.patternIndex, 1)
            expectEqual(snapshot.arrangementMode, "song")
            expectEqual(snapshot.selectedTrackId, "a")
            expectEqual(snapshot.version, neonSnapshotVersion)
            expectNotNil(normalized.createdAt)
        }

        t.test("an empty project name becomes Untitled Project") {
            var raw = project(tracks: [Track(id: "a", name: "Lead")])
            raw.name = "   "
            expectEqual(ProjectNormalizer.normalize(raw).name, "Untitled Project")
        }

        t.test("loop end is always after loop start") {
            let normalized = ProjectNormalizer.normalize(project(
                tracks: [Track(id: "a", name: "Lead")],
                loopStart: 20,
                loopEnd: 4
            ))
            let start = normalized.snapshot.loopStartBar ?? 0
            let end = normalized.snapshot.loopEndBar ?? 0
            expect(end > start, "loop was \(start)–\(end)")
        }

        t.test("a stale selected clip id is cleared") {
            let normalized = ProjectNormalizer.normalize(project(
                tracks: [Track(id: "a", name: "Lead", clips: [Clip(id: "real", name: "Clip")])],
                selectedClipId: "gone"
            ))
            expectEqual(normalized.snapshot.selectedClipId, "")
        }

        t.test("a stale selected track id falls back to the first track") {
            let normalized = ProjectNormalizer.normalize(project(
                tracks: [Track(id: "a", name: "Lead"), Track(id: "b", name: "Bass")],
                selectedTrackId: "deleted"
            ))
            expectEqual(normalized.snapshot.selectedTrackId, "a")
        }

        t.section("Note migration")

        t.test("legacy notes with no owner are adopted by the selected track") {
            // Schema v3 kept one global note pool, so every track showed the same
            // notes. They now belong to whichever track was selected on save.
            let notes = [PianoNote(id: "n", beat: 0, duration: 1, note: 60, velocity: 0.8, color: "#fff")]
            let normalized = ProjectNormalizer.normalize(project(
                tracks: [Track(id: "a", name: "Lead"), Track(id: "b", name: "Bass")],
                notes: notes,
                selectedTrackId: "b"
            ))
            expectEqual(normalized.snapshot.notes?.first?.trackId, "b")
            expectEqual(normalized.notes(forTrack: "b").count, 1)
            expectEqual(normalized.notes(forTrack: "a").count, 0)
        }

        t.test("notes belonging to a deleted track are dropped") {
            let notes = [
                PianoNote(id: "keep", beat: 0, duration: 1, note: 60, velocity: 0.8, color: "#fff", trackId: "a"),
                PianoNote(id: "drop", beat: 0, duration: 1, note: 60, velocity: 0.8, color: "#fff", trackId: "gone")
            ]
            let normalized = ProjectNormalizer.normalize(project(
                tracks: [Track(id: "a", name: "Lead")],
                notes: notes
            ))
            expectEqual(normalized.snapshot.notes?.count ?? -1, 1)
            expectEqual(normalized.snapshot.notes?.first?.id, "keep")
        }

        t.test("note values are clamped into range") {
            let notes = [
                PianoNote(id: "n", beat: -5, duration: 0, note: 999, velocity: 4, color: "#fff", trackId: "a")
            ]
            let normalized = ProjectNormalizer.normalize(project(tracks: [Track(id: "a", name: "Lead")], notes: notes))
            guard let note = normalized.snapshot.notes?.first else { return expect(false, "note was dropped") }
            expectClose(note.beat, 0)
            expect(note.duration > 0, "duration must be positive")
            expectEqual(note.note, 127)
            expectClose(note.velocity, 1)
        }

        t.section("Mixer controls")

        t.test("a user-set gain survives normalization") {
            var control = MixerControl.neutral
            control.gain = 1.21
            control.solo = true
            let normalized = ProjectNormalizer.normalize(project(
                tracks: [Track(id: "a", name: "Lead")],
                controls: ["a": control]
            ))
            expectClose(normalized.control(for: "a").gain, 1.21)
            expectTrue(normalized.control(for: "a").solo)
        }

        t.test("controls for a deleted track are removed and new tracks gain one") {
            let normalized = ProjectNormalizer.normalize(project(
                tracks: [Track(id: "a", name: "Lead"), Track(id: "new", name: "Pad")],
                controls: ["a": MixerControl.neutral, "gone": MixerControl.neutral]
            ))
            expectEqual(normalized.snapshot.controls?.count ?? -1, 2)
            expectNil(normalized.snapshot.controls?["gone"])
            expectNotNil(normalized.snapshot.controls?["new"])
        }

        t.section("Audibility")

        t.test("mute, solo and neither behave as a musician expects") {
            var muted = MixerControl.neutral
            muted.mute = true
            var soloed = MixerControl.neutral
            soloed.solo = true

            let plain = ProjectNormalizer.normalize(project(
                tracks: [Track(id: "a", name: "A"), Track(id: "b", name: "B")],
                controls: ["a": MixerControl.neutral, "b": MixerControl.neutral]
            ))
            expectTrue(plain.isAudible("a"))
            expectTrue(plain.isAudible("b"))
            expectFalse(plain.anyTrackSoloed)

            let withMute = ProjectNormalizer.normalize(project(
                tracks: [Track(id: "a", name: "A"), Track(id: "b", name: "B")],
                controls: ["a": muted, "b": MixerControl.neutral]
            ))
            expectFalse(withMute.isAudible("a"))
            expectTrue(withMute.isAudible("b"))

            let withSolo = ProjectNormalizer.normalize(project(
                tracks: [Track(id: "a", name: "A"), Track(id: "b", name: "B")],
                controls: ["a": soloed, "b": MixerControl.neutral]
            ))
            expectTrue(withSolo.anyTrackSoloed)
            expectTrue(withSolo.isAudible("a"))
            expectFalse(withSolo.isAudible("b"), "a soloed track silences the others")
        }

        t.section("Derived values")

        t.test("contentEndBar accounts for clips and automation alike") {
            let lane = AutomationLane(
                id: "l",
                trackId: "a",
                parameter: "gain",
                label: "A Volume",
                points: [AutomationPoint(bar: 0, value: 0.2), AutomationPoint(bar: 40, value: 0.9)]
            )
            let withClips = ProjectNormalizer.normalize(project(
                tracks: [Track(id: "a", name: "A", clips: [Clip(id: "c", name: "C", startBar: 8, bars: 16)])]
            ))
            expectClose(withClips.contentEndBar, 24)

            var withAutomation = project(
                tracks: [Track(id: "a", name: "A", clips: [Clip(id: "c", name: "C", startBar: 0, bars: 4)])]
            )
            withAutomation.snapshot.automationLanes = [lane]
            expectClose(ProjectNormalizer.normalize(withAutomation).contentEndBar, 40)
        }

        t.test("secondsPerBar is correct and never divides by zero") {
            var p = project(tracks: [Track(id: "a", name: "A")])
            p.snapshot.bpm = 120
            expectClose(p.secondsPerBar, 2.0)
            p.snapshot.bpm = 0
            expectClose(p.secondsPerBar, 2.0, accuracy: 0.0001, "a zero tempo must fall back, not divide by zero")
            p.snapshot.bpm = -50
            expect(p.secondsPerBar > 0, "a negative tempo must not produce negative time")
        }

        t.section("Snap")

        t.test("snap values parse, including unknown ones") {
            expectEqual(SnapValue.parse("1/4"), .quarter)
            expectEqual(SnapValue.parse("1/16"), .sixteenth)
            expectEqual(SnapValue.parse(nil), .quarter)
            expectEqual(SnapValue.parse("banana"), .quarter)
            expectEqual(SnapValue.parse("none"), SnapValue.none)
        }

        t.test("snapping rounds to the nearest grid line") {
            expectClose(SnapValue.quarter.snap(bars: 1.13), 1.25)
            expectClose(SnapValue.quarter.snap(bars: 1.10), 1.0)
            expectClose(SnapValue.bar.snap(bars: 2.6), 3.0)
            expectClose(SnapValue.sixteenth.snap(bars: 0.10), 0.125)
        }

        t.test("snap off passes the value through but still clamps negatives") {
            expectClose(SnapValue.none.snap(bars: 3.37), 3.37)
            expectClose(SnapValue.none.snap(bars: -2), 0)
        }

        t.test("beats are four times bars") {
            for value in SnapValue.allCases {
                expectClose(value.beats, value.bars * 4, accuracy: 0.0000001, "\(value.rawValue)")
            }
        }

        t.section("Identifiers")

        t.test("safeProjectId strips paths, suffixes and unsafe characters") {
            expectEqual(safeProjectId("/tmp/some dir/Neon Alone.neon.json"), "Neon-Alone")
            expectEqual(safeProjectId("hello/world"), "world")
            expectEqual(safeProjectId("--trimmed--"), "trimmed")
            expectEqual(safeProjectId("a b/c!d"), "c-d")
            expectFalse(safeProjectId("").isEmpty, "an empty id must still produce something usable")
            expectFalse(safeProjectId("///").isEmpty)
            expect(safeProjectId(String(repeating: "x", count: 200)).count <= 72, "ids are capped at 72 characters")
        }

        t.test("makeId returns unique values") {
            var seen = Set<String>()
            for _ in 0..<500 { seen.insert(makeId("clip")) }
            expectEqual(seen.count, 500)
            expectTrue(makeId("clip").hasPrefix("clip-"))
        }

        t.section("Automation parameter names")

        t.test("parameters are inferred from what the track is called") {
            expectEqual(inferAutomationParameter(for: Track(id: "a", name: "Filter Sweep")), "filter")
            expectEqual(inferAutomationParameter(for: Track(id: "a", name: "Big Reverb")), "reverb")
            expectEqual(inferAutomationParameter(for: Track(id: "a", name: "Ping Delay")), "delay")
            expectEqual(inferAutomationParameter(for: Track(id: "a", name: "Auto Pan")), "pan")
            expectEqual(inferAutomationParameter(for: Track(id: "a", name: "Lead")), "gain")
        }

        t.test("parameters get plain-English display names") {
            expectEqual(automationParameterDisplayName("gain"), "Volume")
            expectEqual(automationParameterDisplayName("sendA"), "Send A")
            expectEqual(automationParameterDisplayName("cutoff"), "Filter")
            expectEqual(automationParameterDisplayName("weird"), "Weird")
        }

        t.section("Recipe status")

        t.test("every status the tools write counts as done") {
            // Regression: two panels each had their own idea of "done" and the
            // one that omitted "implemented" — the value every generator writes —
            // reported 0 of 15 steps beside a list showing 15 of 15.
            func done(_ status: String?) -> Bool {
                RecipeItem(id: "x", label: "x", status: status).isDone
            }
            expectTrue(done("implemented"), "the value the Python tools write")
            expectTrue(done("Implemented"))
            expectTrue(done("done"))
            expectTrue(done("complete"))
            expectTrue(done("completed"))
            expectTrue(done("ready"))
            expectTrue(done("ok"))
            expectFalse(done("planned"))
            expectFalse(done(nil))
            expectFalse(done(""))
            expectTrue(RecipeItem.doneStatuses.contains(RecipeItem.doneStatus))
            expectFalse(RecipeItem.doneStatuses.contains(RecipeItem.notDoneStatus))
        }

        t.section("Step sequencing")

        t.test("only tracks without a recorded file support steps") {
            expectTrue(Track(id: "a", name: "Kick", kind: "drum").supportsStepSequencing)
            expectFalse(Track(id: "a", name: "Kick", kind: "audio", file: "/x.wav").supportsStepSequencing)
            expectFalse(Track(id: "a", name: "Sweep", kind: "automation").supportsStepSequencing)
            expectTrue(Track(id: "a", name: "Kick", kind: "audio").supportsStepSequencing, "an audio track with no file yet is still writable")
        }
    }
}
