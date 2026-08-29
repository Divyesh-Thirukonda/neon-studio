import AVFoundation
import Foundation

/// Turns piano-roll notes and step-sequencer patterns into audio.
///
/// Until now a brand-new project could never make a sound: playback only ever
/// opened `track.file`, so notes you drew and steps you switched on were silent
/// and there was no way to tell whether anything had worked. This renders those
/// tracks offline into a buffer that the transport schedules exactly like a
/// recorded stem, so it stays in perfect sync with everything else.
///
/// It is a preview instrument, not a synthesiser to write records with — simple
/// oscillators with an envelope, chosen from the track's name and instrument.
public enum NotePreviewRenderer {

    /// Safety cap. A track asking for more than this is truncated rather than
    /// allocating hundreds of megabytes.
    public static let maximumSeconds: Double = 300

    public struct Voice {
        public enum Shape: Equatable {
            case sine        // subs and low bass
            case triangle    // plucks and bells
            case saw         // leads
            case superSaw    // chords and pads
            case noise       // hats, claps, snares
        }
        public var shape: Shape
        public var attack: Double
        public var decay: Double
        public var sustain: Double
        public var release: Double
        public var level: Double
    }

    /// Picks a preview sound from what the track calls itself. Deliberately
    /// coarse — the point is that a bass sounds low and a hat sounds like a tick,
    /// so the user can tell their edit landed.
    public static func voice(for track: Track) -> Voice {
        let text = [track.name, track.kind, track.instrument]
            .compactMap { $0 }
            .joined(separator: " ")
            .lowercased()

        if text.contains("hat") || text.contains("cymbal") || text.contains("ride") || text.contains("shaker") {
            return Voice(shape: .noise, attack: 0.001, decay: 0.045, sustain: 0, release: 0.02, level: 0.22)
        }
        if text.contains("clap") || text.contains("snare") {
            return Voice(shape: .noise, attack: 0.001, decay: 0.16, sustain: 0, release: 0.05, level: 0.34)
        }
        if text.contains("kick") || text.contains("drum") || text.contains("sub") {
            return Voice(shape: .sine, attack: 0.001, decay: 0.22, sustain: 0, release: 0.05, level: 0.5)
        }
        if text.contains("bass") {
            return Voice(shape: .sine, attack: 0.004, decay: 0.14, sustain: 0.55, release: 0.08, level: 0.42)
        }
        if text.contains("pluck") || text.contains("bell") || text.contains("key") {
            return Voice(shape: .triangle, attack: 0.002, decay: 0.24, sustain: 0.12, release: 0.14, level: 0.32)
        }
        if text.contains("chord") || text.contains("pad") || text.contains("string") {
            return Voice(shape: .superSaw, attack: 0.05, decay: 0.3, sustain: 0.7, release: 0.35, level: 0.2)
        }
        return Voice(shape: .saw, attack: 0.006, decay: 0.18, sustain: 0.55, release: 0.16, level: 0.26)
    }

    /// Events a track contributes, in seconds from bar 0.
    public struct Event {
        public var start: Double
        public var duration: Double
        public var frequency: Double
        public var velocity: Double
    }

    /// Renders one track's notes and steps. Returns nil when the track has
    /// nothing to play, so the transport can skip it entirely.
    public static func render(
        track: Track,
        project: LocalProject,
        format: AVAudioFormat
    ) -> AVAudioPCMBuffer? {
        let events = self.events(for: track, project: project)
        guard !events.isEmpty else { return nil }

        let voice = self.voice(for: track)
        let tail = voice.release + voice.decay + 0.25
        let end = min(maximumSeconds, (events.map { $0.start + $0.duration }.max() ?? 0) + tail)
        guard end > 0 else { return nil }

        let sampleRate = format.sampleRate
        let frameCount = AVAudioFrameCount(end * sampleRate)
        guard frameCount > 0,
              let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: frameCount),
              let channel = buffer.floatChannelData?[0] else {
            return nil
        }
        buffer.frameLength = frameCount
        for frame in 0..<Int(frameCount) { channel[frame] = 0 }

        var noiseState: UInt32 = 0x2545_F491
        for event in events {
            render(
                event: event,
                voice: voice,
                into: channel,
                frameCount: Int(frameCount),
                sampleRate: sampleRate,
                noiseState: &noiseState
            )
        }

        // Keep the sum inside the rails without squashing dynamics when it
        // already fits.
        var peak: Float = 0
        for frame in 0..<Int(frameCount) { peak = max(peak, abs(channel[frame])) }
        if peak > 0.95 {
            let scale = 0.95 / peak
            for frame in 0..<Int(frameCount) { channel[frame] *= scale }
        }

        // Fill any remaining channels with a copy so the buffer matches `format`.
        if let data = buffer.floatChannelData, format.channelCount > 1 {
            for extra in 1..<Int(format.channelCount) {
                memcpy(data[extra], channel, Int(frameCount) * MemoryLayout<Float>.size)
            }
        }
        return buffer
    }

    public static func events(for track: Track, project: LocalProject) -> [Event] {
        let secondsPerBeat = project.secondsPerBar / 4
        var events: [Event] = []

        for note in project.notes(forTrack: track.id) {
            events.append(Event(
                start: note.beat * secondsPerBeat,
                duration: max(0.03, note.duration * secondsPerBeat),
                frequency: frequency(forMIDI: note.note),
                velocity: max(0.05, min(1, note.velocity))
            ))
        }

        // Step patterns repeat every bar for as long as the track's clips run.
        // Without clips there is nothing to place them against, so one bar is
        // rendered as an audible preview of the pattern.
        let steps = (track.steps ?? []).map { (($0 % 16) + 16) % 16 }
        if !steps.isEmpty, track.supportsStepSequencing {
            let clips = track.clips ?? []
            let firstBar = clips.map { $0.startBar ?? 0 }.min() ?? 0
            let lastBar = clips.map { ($0.startBar ?? 0) + ($0.bars ?? 1) }.max() ?? (firstBar + 1)
            let stepFrequency = frequency(forMIDI: percussionPitch(for: track))
            var bar = firstBar
            while bar < lastBar, (bar - firstBar) * project.secondsPerBar < maximumSeconds {
                for step in steps {
                    events.append(Event(
                        start: (bar + Double(step) / 16) * project.secondsPerBar,
                        duration: project.secondsPerBar / 16,
                        frequency: stepFrequency,
                        velocity: step % 4 == 0 ? 1.0 : 0.72
                    ))
                }
                bar += 1
            }
        }

        return events.sorted { $0.start < $1.start }
    }

    private static func render(
        event: Event,
        voice: Voice,
        into channel: UnsafeMutablePointer<Float>,
        frameCount: Int,
        sampleRate: Double,
        noiseState: inout UInt32
    ) {
        let startFrame = Int(event.start * sampleRate)
        guard startFrame < frameCount else { return }
        let sustainFrames = Int(event.duration * sampleRate)
        let releaseFrames = Int(voice.release * sampleRate)
        let total = min(sustainFrames + releaseFrames, frameCount - startFrame)
        guard total > 0 else { return }

        let attackFrames = max(1, Int(voice.attack * sampleRate))
        let decayFrames = max(1, Int(voice.decay * sampleRate))
        let amplitude = Float(voice.level * event.velocity)
        let step = event.frequency / sampleRate
        var phase = 0.0

        for offset in 0..<total {
            let envelope: Double
            if offset < attackFrames {
                envelope = Double(offset) / Double(attackFrames)
            } else if offset < attackFrames + decayFrames {
                let t = Double(offset - attackFrames) / Double(decayFrames)
                envelope = 1 - t * (1 - voice.sustain)
            } else if offset < sustainFrames {
                envelope = voice.sustain
            } else {
                let t = Double(offset - sustainFrames) / Double(max(1, releaseFrames))
                envelope = max(0, voice.sustain * (1 - t))
            }
            guard envelope > 0 else { continue }

            let sample: Double
            switch voice.shape {
            case .sine:
                sample = sin(2 * .pi * phase)
            case .triangle:
                sample = 2 * abs(2 * (phase - floor(phase + 0.5))) - 1
            case .saw:
                sample = 2 * (phase - floor(phase + 0.5))
            case .superSaw:
                // Three slightly detuned saws, the cheapest convincing "wide" sound.
                let a = 2 * (phase - floor(phase + 0.5))
                let b = 2 * ((phase * 1.006) - floor(phase * 1.006 + 0.5))
                let c = 2 * ((phase * 0.994) - floor(phase * 0.994 + 0.5))
                sample = (a + b + c) / 3
            case .noise:
                // xorshift keeps this deterministic, so the same project always
                // renders the same preview.
                noiseState ^= noiseState << 13
                noiseState ^= noiseState >> 17
                noiseState ^= noiseState << 5
                sample = Double(Int32(bitPattern: noiseState)) / Double(Int32.max)
            }

            phase += step
            if phase >= 1 { phase -= floor(phase) }
            channel[startFrame + offset] += Float(sample * envelope) * amplitude
        }
    }

    public static func frequency(forMIDI note: Int) -> Double {
        440 * pow(2, Double(note - 69) / 12)
    }

    /// Rough pitch for a step-sequenced percussion track, so a kick thumps and a
    /// hat ticks instead of everything sounding the same.
    public static func percussionPitch(for track: Track) -> Int {
        let text = [track.name, track.instrument].compactMap { $0 }.joined(separator: " ").lowercased()
        if text.contains("hat") || text.contains("ride") || text.contains("cymbal") { return 90 }
        if text.contains("clap") || text.contains("snare") { return 72 }
        if text.contains("kick") { return 36 }
        if text.contains("sub") || text.contains("bass") { return 40 }
        return 60
    }
}
