import AVFoundation
import Foundation
import NeonStudioKit

/// Covers the note preview renderer and the on-disk envelope — the two places
/// where a silently wrong answer is easiest to ship.
enum AudioTests {

    private static func makeProject(
        bpm: Double = 120,
        tracks: [Track],
        notes: [PianoNote] = []
    ) -> LocalProject {
        ProjectNormalizer.normalize(LocalProject(
            id: "test",
            name: "Test",
            updatedAt: nowISO(),
            snapshot: ProjectSnapshot(bpm: bpm, tracks: tracks, notes: notes)
        ))
    }

    private static var monoFormat: AVAudioFormat {
        AVAudioFormat(standardFormatWithSampleRate: 44_100, channels: 1)!
    }

    static func run() {
        let t = TestRunner.shared
        t.section("Note preview renderer")

        t.test("a track with no notes or steps renders nothing") {
            let track = Track(id: "a", name: "Lead", kind: "instrument")
            expectNil(NotePreviewRenderer.render(
                track: track,
                project: makeProject(tracks: [track]),
                format: monoFormat
            ))
        }

        t.test("notes produce an audible buffer of the right length") {
            let track = Track(id: "a", name: "Lead", kind: "instrument", color: "#60c8f8")
            let notes = [
                PianoNote(id: "n1", beat: 0, duration: 1, note: 60, velocity: 0.9, color: "#60c8f8", trackId: "a"),
                PianoNote(id: "n2", beat: 2, duration: 1, note: 64, velocity: 0.9, color: "#60c8f8", trackId: "a")
            ]
            let project = makeProject(tracks: [track], notes: notes)
            guard let buffer = NotePreviewRenderer.render(track: track, project: project, format: monoFormat) else {
                return expect(false, "expected a rendered buffer")
            }
            // 120 BPM = 0.5s per beat, so the last note ends at beat 3 = 1.5s, plus a tail.
            let seconds = Double(buffer.frameLength) / buffer.format.sampleRate
            expect(seconds > 1.5, "buffer was \(seconds)s, expected more than 1.5s")
            expect(seconds < 3.0, "buffer was \(seconds)s, expected less than 3s")

            guard let samples = buffer.floatChannelData?[0] else {
                return expect(false, "no channel data")
            }
            var peak: Float = 0
            for frame in 0..<Int(buffer.frameLength) { peak = max(peak, abs(samples[frame])) }
            expect(peak > 0.01, "a rendered note must actually be audible, peak was \(peak)")
            expect(peak <= 0.951, "output must stay inside the rails, peak was \(peak)")
        }

        t.test("a track does not sound its neighbour's notes") {
            let lead = Track(id: "lead", name: "Lead")
            let bass = Track(id: "bass", name: "Bass")
            let notes = [
                PianoNote(id: "n1", beat: 0, duration: 1, note: 60, velocity: 0.9, color: "#fff", trackId: "lead")
            ]
            let project = makeProject(tracks: [lead, bass], notes: notes)
            expectNotNil(NotePreviewRenderer.render(track: lead, project: project, format: monoFormat))
            expectNil(NotePreviewRenderer.render(track: bass, project: project, format: monoFormat))
        }

        t.test("a step pattern repeats across the length of its clip") {
            let track = Track(
                id: "drums",
                name: "Kick",
                kind: "drum",
                steps: [0, 4, 8, 12],
                clips: [Clip(id: "c", name: "Kick", startBar: 0, bars: 4)]
            )
            let project = makeProject(tracks: [track])
            let events = NotePreviewRenderer.events(for: track, project: project)
            expectEqual(events.count, 16, "4 steps over 4 bars")
            expectClose(events.first?.start ?? -1, 0)
            // Bar 3 (zero-based) starts at 6s at 120 BPM; the last hit is 12/16 into it.
            expectClose(events.map(\.start).max() ?? 0, 3 * 2.0 + 0.75 * 2.0)
        }

        t.test("steps are ignored for tracks that play a recorded file") {
            // A stem is arranged as clips, not steps, so leftover step data must
            // not add phantom percussion on top of the recording.
            let track = Track(
                id: "stem",
                name: "Drums",
                kind: "audio",
                file: "/tmp/does-not-matter.wav",
                steps: [0, 4, 8, 12],
                clips: [Clip(id: "c", name: "Drums", startBar: 0, bars: 4)]
            )
            expectFalse(track.supportsStepSequencing)
            expectTrue(NotePreviewRenderer.events(for: track, project: makeProject(tracks: [track])).isEmpty)
        }

        t.test("the preview voice follows the track name") {
            func shape(_ name: String) -> NotePreviewRenderer.Voice.Shape {
                NotePreviewRenderer.voice(for: Track(id: "t", name: name)).shape
            }
            expectEqual(shape("Hat/Ride"), .noise)
            expectEqual(shape("Clap Stack"), .noise)
            expectEqual(shape("Sub"), .sine)
            expectEqual(shape("Mid Bass"), .sine)
            expectEqual(shape("Supersaw Chords"), .superSaw)
            expectEqual(shape("Plucks"), .triangle)
            expectEqual(shape("Hook Lead"), .saw)
        }

        t.test("MIDI note numbers convert to the right frequencies") {
            expectClose(NotePreviewRenderer.frequency(forMIDI: 69), 440)
            expectClose(NotePreviewRenderer.frequency(forMIDI: 81), 880)
            expectClose(NotePreviewRenderer.frequency(forMIDI: 57), 220)
        }

        t.test("rendering is deterministic") {
            // Noise is seeded, so the same project previews identically instead
            // of changing under the user between presses of Play.
            let track = Track(
                id: "d",
                name: "Snare",
                steps: [0, 8],
                clips: [Clip(id: "c", name: "x", startBar: 0, bars: 1)]
            )
            let project = makeProject(tracks: [track])
            guard let first = NotePreviewRenderer.render(track: track, project: project, format: monoFormat),
                  let second = NotePreviewRenderer.render(track: track, project: project, format: monoFormat),
                  let a = first.floatChannelData?[0],
                  let b = second.floatChannelData?[0] else {
                return expect(false, "expected two buffers")
            }
            expectEqual(first.frameLength, second.frameLength)
            var mismatches = 0
            for frame in stride(from: 0, to: Int(first.frameLength), by: 97) where a[frame] != b[frame] {
                mismatches += 1
            }
            expectEqual(mismatches, 0, "two renders of the same project differed")
        }

        t.section("Count-in and punch-in")

        t.test("count-in bars are clamped to something sane") {
            expectEqual(Transport.CountIn(bars: -3, punchInBar: 0).bars, 0)
            expectEqual(Transport.CountIn(bars: 99, punchInBar: 0).bars, 8)
            expectEqual(Transport.CountIn(bars: 2, punchInBar: 0).bars, 2)
        }

        t.test("a negative punch-in bar is pulled back to the start") {
            expectClose(Transport.CountIn(bars: 1, punchInBar: -4).punchInBar, 0)
        }

        t.test("punch-out is optional and preserved when given") {
            expectNil(Transport.CountIn(bars: 1, punchInBar: 8).punchOutBar)
            expectClose(Transport.CountIn(bars: 1, punchInBar: 8, punchOutBar: 24).punchOutBar ?? -1, 24)
        }

        t.test("a count-in lasts a whole number of bars at the project tempo") {
            // Two bars at 120 BPM is 4 seconds; the take must land exactly then,
            // which is the whole point of arming the recorder to a host time.
            let project = makeProject(tracks: [Track(id: "a", name: "Lead")])
            expectClose(project.secondsPerBar, 2.0)
            let countIn = Transport.CountIn(bars: 2, punchInBar: 0)
            expectClose(Double(countIn.bars) * project.secondsPerBar, 4.0)
        }

        t.test("a punch range converts to a recording duration") {
            let project = makeProject(tracks: [Track(id: "a", name: "Lead")])
            let countIn = Transport.CountIn(bars: 1, punchInBar: 8, punchOutBar: 24)
            let duration = (countIn.punchOutBar! - countIn.punchInBar) * project.secondsPerBar
            expectClose(duration, 32.0, accuracy: 0.0001, "16 bars at 120 BPM")
        }

        t.section("Project file envelope")

        t.test("machine-local audio paths are reported as not portable") {
            let project = makeProject(tracks: [
                Track(id: "a", name: "Stem", kind: "audio", file: "/Users/somebody/Music/kick.wav")
            ])
            let envelope = ProjectFileEnvelope(project: project)
            expectFalse(envelope.portable, "absolute paths do not survive being sent to another Mac")
            expectEqual(envelope.assetMode, "external-absolute")
        }

        t.test("relative audio paths are reported as portable") {
            let project = makeProject(tracks: [
                Track(id: "a", name: "Stem", kind: "audio", file: "exports/kick.wav")
            ])
            let envelope = ProjectFileEnvelope(project: project)
            expectTrue(envelope.portable)
            expectEqual(envelope.assetMode, "external")
        }

        t.test("embedded assets are always portable") {
            var project = makeProject(tracks: [
                Track(id: "a", name: "Stem", kind: "audio", file: "/Users/somebody/kick.wav")
            ])
            project.assets = [ProjectAsset(trackId: "a", file: "kick.wav", data: "AAAA")]
            let envelope = ProjectFileEnvelope(project: project)
            expectTrue(envelope.portable)
            expectEqual(envelope.assetMode, "embedded")
        }

        t.section("Timestamps and ordering")

        t.test("project dates parse at both ISO-8601 precisions") {
            let withFraction = ProjectStore.parseDate("2026-06-12T04:41:07.221Z")
            let withoutFraction = ProjectStore.parseDate("2026-06-12T04:41:07Z")
            expect(withFraction > withoutFraction, "fractional seconds must not sort before whole ones")
            expectEqual(ProjectStore.parseDate(nil), .distantPast)
            expectEqual(ProjectStore.parseDate("not a date"), .distantPast)
        }

        t.test("ids minted a day apart do not collide") {
            // Regression: the old implementation formatted only HHmmss, so ids
            // repeated every 24 hours and could overwrite each other's files.
            let today = Date(timeIntervalSince1970: 1_700_000_000)
            let tomorrow = today.addingTimeInterval(86_400)
            expect(
                timestampForId(today) != timestampForId(tomorrow),
                "timestamps 24h apart were identical: \(timestampForId(today))"
            )
        }

        t.section("Orphaned automation")

        t.test("automation lanes for a deleted track are dropped, not reattached") {
            // Re-pointing a lane at an unrelated track silently attached one
            // instrument's filter sweep to another and saved that as truth.
            let lane = AutomationLane(
                id: "lane",
                trackId: "deleted-track",
                parameter: "filter",
                label: "Ghost Filter",
                points: [AutomationPoint(bar: 0, value: 0.2), AutomationPoint(bar: 8, value: 0.9)]
            )
            let project = ProjectNormalizer.normalize(LocalProject(
                id: "p",
                name: "P",
                updatedAt: nowISO(),
                snapshot: ProjectSnapshot(
                    bpm: 120,
                    tracks: [Track(id: "alive", name: "Lead")],
                    automationLanes: [lane]
                )
            ))
            expectEqual(project.snapshot.automationLanes?.count ?? -1, 0)
            expectTrue(automationLaneIsOrphaned(lane, tracks: project.snapshot.tracks))
        }

        t.test("automation lanes for a live track survive and get sorted") {
            let lane = AutomationLane(
                id: "lane",
                trackId: "alive",
                parameter: "filter",
                label: "Lead Filter",
                points: [AutomationPoint(bar: 8, value: 0.9), AutomationPoint(bar: 0, value: 0.2)]
            )
            let project = ProjectNormalizer.normalize(LocalProject(
                id: "p",
                name: "P",
                updatedAt: nowISO(),
                snapshot: ProjectSnapshot(
                    bpm: 120,
                    tracks: [Track(id: "alive", name: "Lead")],
                    automationLanes: [lane]
                )
            ))
            expectEqual(project.snapshot.automationLanes?.count ?? -1, 1)
            expectEqual(project.snapshot.automationLanes?.first?.points.map(\.bar) ?? [], [0, 8])
        }
    }
}
