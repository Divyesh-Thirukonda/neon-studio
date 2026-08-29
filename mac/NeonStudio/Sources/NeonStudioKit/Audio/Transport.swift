import AVFoundation
import Foundation

/// Sample-accurate multi-track playback.
///
/// The previous implementation created one `AVAudioPlayer` per stem and called
/// `play()` on each in a `for` loop, so every stem started a few milliseconds
/// after the one before it — audible as flamming — nothing could change while it
/// played, the loop range had no effect, and there was no playhead. Worse, a
/// project with no rendered stems was completely silent no matter what you drew.
///
/// This drives a single `AVAudioEngine`. Every source is scheduled against one
/// shared host time, each track owns a mixer node whose volume and pan change
/// live, the loop range is honoured, tracks with notes are rendered by
/// `NotePreviewRenderer` so a new project makes sound, and the transport reports
/// a real playhead.
public final class Transport {

    public enum State: Equatable {
        case stopped
        case playing
    }

    // MARK: Callbacks (all delivered on the main queue)

    /// Fires ~30x a second while playing, with the playhead in bars.
    public var onPlayheadMoved: ((Double) -> Void)?
    /// Fires when playback starts or stops for any reason, including reaching the end.
    public var onStateChanged: ((State) -> Void)?
    /// Master output peak in the range 0...1, for the level meter.
    public var onMasterLevel: ((Float) -> Void)?
    /// Real per-track output peaks, keyed by track id, in the range 0...1.
    ///
    /// These are measured at each track's own mixer node, after its gain, pan,
    /// mute and solo have been applied — so a muted track reads zero and a
    /// quiet part reads quiet, which is what a meter is for. The UI previously
    /// showed the master level scaled by each fader, which moved every meter in
    /// lockstep and told you nothing about the individual track.
    public var onTrackLevels: (([String: Float]) -> Void)?
    /// Non-fatal problems worth telling the user about, e.g. an unreadable stem.
    public var onWarning: ((String) -> Void)?

    // MARK: Sources

    private enum Source {
        case file(AVAudioFile)
        /// Rendered from the track's notes and steps.
        case buffer(AVAudioPCMBuffer)

        var sampleRate: Double {
            switch self {
            case .file(let file): return file.processingFormat.sampleRate
            case .buffer(let buffer): return buffer.format.sampleRate
            }
        }

        var frameLength: AVAudioFramePosition {
            switch self {
            case .file(let file): return file.length
            case .buffer(let buffer): return AVAudioFramePosition(buffer.frameLength)
            }
        }

        var format: AVAudioFormat {
            switch self {
            case .file(let file): return file.processingFormat
            case .buffer(let buffer): return buffer.format
            }
        }

        var durationSeconds: Double {
            sampleRate > 0 ? Double(frameLength) / sampleRate : 0
        }
    }

    private struct TrackNode {
        var player: AVAudioPlayerNode
        var mixer: AVAudioMixerNode
        var source: Source
        /// Timeline position, in seconds from bar 0, of this source's first sample.
        var timelineStartSeconds: Double

        var timelineEndSeconds: Double { timelineStartSeconds + source.durationSeconds }
    }

    // MARK: Engine

    private let engine = AVAudioEngine()
    private var trackNodes: [String: TrackNode] = [:]
    private var engineStarted = false
    private var tapInstalled = false

    private var displayTimer: Timer?
    /// Written from the render thread by each track tap, read on the main queue
    /// by the display timer. The lock is held for a dictionary copy only.
    private let levelLock = NSLock()
    private var trackPeaks: [String: Float] = [:]
    private var startHostTime: UInt64 = 0
    private var startBar: Double = 0
    private var secondsPerBar: Double = 2
    private var stopAtSeconds: Double?
    private var loopRange: (start: Double, end: Double)?

    /// How many loop repeats are queued up front.
    private static let maxQueuedLoops = 128

    // MARK: Count-in

    /// Where a recording is to begin, and what the player hears first.
    public struct CountIn {
        /// Bars of clicks before the punch-in. Zero starts immediately.
        public var bars: Int
        /// The bar the take lands on.
        public var punchInBar: Double
        /// The bar the take stops at, if it stops on its own.
        public var punchOutBar: Double?

        public init(bars: Int, punchInBar: Double, punchOutBar: Double? = nil) {
            self.bars = max(0, min(8, bars))
            self.punchInBar = max(0, punchInBar)
            self.punchOutBar = punchOutBar
        }
    }

    /// The timing a recorder needs to line its take up with the music.
    public struct RecordingSync {
        /// Host time at which the punch-in bar begins.
        public let punchInHostTime: UInt64
        /// Seconds from now until that moment — the count-in length.
        public let leadSeconds: Double
        /// How long to record, when a punch-out was set.
        public let durationSeconds: Double?
    }

    private var clickPlayer: AVAudioPlayerNode?
    private var clickBuffers: (accent: AVAudioPCMBuffer, beat: AVAudioPCMBuffer)?

    public private(set) var state: State = .stopped {
        didSet {
            guard state != oldValue else { return }
            let value = state
            DispatchQueue.main.async { [weak self] in self?.onStateChanged?(value) }
        }
    }

    /// Current playhead in bars. Valid whether or not playback is running.
    public private(set) var playheadBar: Double = 0

    public init() {}

    deinit {
        displayTimer?.invalidate()
        if tapInstalled { engine.mainMixerNode.removeTap(onBus: 0) }
        engine.stop()
    }

    // MARK: Loading

    /// Rebuilds the graph for a project. Safe to call whenever tracks, notes, or
    /// audio files change; it stops playback first.
    public func load(project: LocalProject, store: ProjectStore) {
        stop(notify: false)
        detachAll()
        secondsPerBar = project.secondsPerBar

        let previewFormat = AVAudioFormat(standardFormatWithSampleRate: 44_100, channels: 1)
        var unreadable: [String] = []

        for track in project.snapshot.tracks {
            if let url = store.existingAudioURL(for: track) {
                do {
                    let file = try AVAudioFile(forReading: url)
                    attach(
                        trackId: track.id,
                        source: .file(file),
                        timelineStartSeconds: timelineStart(
                            forStemOf: track,
                            duration: Double(file.length) / file.processingFormat.sampleRate,
                            project: project
                        )
                    )
                } catch {
                    unreadable.append(track.name)
                }
                continue
            }

            if track.file != nil {
                unreadable.append(track.name)
            }

            // No audio file: synthesise the notes and steps so the track is
            // audible instead of silently doing nothing.
            if let previewFormat,
               let buffer = NotePreviewRenderer.render(track: track, project: project, format: previewFormat) {
                attach(trackId: track.id, source: .buffer(buffer), timelineStartSeconds: 0)
            }
        }

        applyMix(project: project)

        if !unreadable.isEmpty {
            let names = unreadable.prefix(3).joined(separator: ", ")
            let extra = unreadable.count > 3 ? " and \(unreadable.count - 3) more" : ""
            DispatchQueue.main.async { [weak self] in
                self?.onWarning?("Couldn't find the sound file for \(names)\(extra).")
            }
        }
    }

    /// Where a stem sits on the timeline.
    ///
    /// Rendered stems in this app are full-length: the renderer writes silence
    /// up to the point the part enters, even though the track's first clip is
    /// drawn at bar 8 or bar 56. Offsetting those by their clip position would
    /// push them a minute late. A file materially shorter than the song, though,
    /// is a one-shot or an imported sound and does belong where its clip sits.
    private func timelineStart(forStemOf track: Track, duration: Double, project: LocalProject) -> Double {
        let clips = track.clips ?? []
        guard let firstClipBar = clips.map({ $0.startBar ?? 0 }).min(), firstClipBar > 0 else { return 0 }
        let songSeconds = max(project.contentEndBar, 1) * project.secondsPerBar
        let looksFullLength = duration >= songSeconds * 0.8
        return looksFullLength ? 0 : firstClipBar * project.secondsPerBar
    }

    private func attach(trackId: String, source: Source, timelineStartSeconds: Double) {
        let player = AVAudioPlayerNode()
        let mixer = AVAudioMixerNode()
        engine.attach(player)
        engine.attach(mixer)
        engine.connect(player, to: mixer, format: source.format)
        engine.connect(mixer, to: engine.mainMixerNode, format: nil)
        installTrackTap(on: mixer, trackId: trackId)
        trackNodes[trackId] = TrackNode(
            player: player,
            mixer: mixer,
            source: source,
            timelineStartSeconds: timelineStartSeconds
        )
    }

    private func detachAll() {
        for (_, node) in trackNodes {
            node.player.stop()
            // The tap has to come off before the node does, otherwise the engine
            // is left rendering into a callback that outlives its node.
            node.mixer.removeTap(onBus: 0)
            engine.detach(node.player)
            engine.detach(node.mixer)
        }
        trackNodes.removeAll()
        levelLock.lock()
        trackPeaks.removeAll()
        levelLock.unlock()
    }

    /// Measures one track's output continuously.
    ///
    /// The tap runs on the render thread, so it does the cheapest possible thing:
    /// a strided peak scan into a dictionary. Publishing happens on the display
    /// timer instead, because fifteen tracks each hopping to the main queue per
    /// buffer would swamp it.
    private func installTrackTap(on mixer: AVAudioMixerNode, trackId: String) {
        let format = mixer.outputFormat(forBus: 0)
        guard format.sampleRate > 0, format.channelCount > 0 else { return }
        mixer.installTap(onBus: 0, bufferSize: 2048, format: format) { [weak self] buffer, _ in
            guard let self, let channels = buffer.floatChannelData else { return }
            var peak: Float = 0
            let frames = Int(buffer.frameLength)
            for channel in 0..<Int(buffer.format.channelCount) {
                let samples = channels[channel]
                for frame in stride(from: 0, to: frames, by: 4) {
                    peak = max(peak, abs(samples[frame]))
                }
            }
            self.levelLock.lock()
            // Decay rather than replace, so a meter falls smoothly instead of
            // flickering between buffers that happen to straddle a transient.
            let previous = self.trackPeaks[trackId] ?? 0
            self.trackPeaks[trackId] = max(min(peak, 1), previous * 0.72)
            self.levelLock.unlock()
        }
    }

    /// Number of tracks that will actually produce sound.
    public var loadedTrackCount: Int { trackNodes.count }

    /// How many audible tracks come from synthesised notes rather than audio
    /// files, so the UI can say so rather than leaving the user guessing.
    public var previewTrackCount: Int {
        trackNodes.values.filter { if case .buffer = $0.source { return true } else { return false } }.count
    }

    // MARK: Live mixing

    /// Applies gain, pan, mute and solo immediately — during playback too.
    public func applyMix(project: LocalProject) {
        for (trackId, node) in trackNodes {
            let control = project.control(for: trackId)
            let audible = project.isAudible(trackId)
            // A mixer node's outputVolume goes above 1.0, so the top of the
            // fader's 0...1.4 range is reachable. `AVAudioPlayer.volume`, which
            // the old code used, clamps at 1.0 and silently discarded it.
            node.mixer.outputVolume = audible ? Float(max(0, min(control.gain, 1.4))) : 0
            node.mixer.pan = Float(max(-1, min(control.pan, 1)))
        }
    }

    public func setMasterVolume(_ value: Float) {
        engine.mainMixerNode.outputVolume = max(0, min(value, 1.5))
    }

    // MARK: Transport

    /// Starts every source against one shared host time so they line up exactly.
    /// - Returns: false when there was nothing to play.
    @discardableResult
    public func play(project: LocalProject, fromBar bar: Double) -> Bool {
        stop(notify: false)
        guard !trackNodes.isEmpty else {
            state = .stopped
            return false
        }

        secondsPerBar = project.secondsPerBar
        let loopEnabled = project.snapshot.loopEnabled == true
        let loopStart = max(0, project.snapshot.loopStartBar ?? 0)
        let loopEnd = max(loopStart + 0.25, project.snapshot.loopEndBar ?? 16)
        loopRange = loopEnabled ? (loopStart, loopEnd) : nil

        var start = max(0, bar)
        if loopEnabled, start >= loopEnd { start = loopStart }

        do {
            if !engine.isRunning {
                engine.prepare()
                try engine.start()
                engineStarted = true
            }
        } catch {
            DispatchQueue.main.async { [weak self] in
                self?.onWarning?("Couldn't start audio: \(error.localizedDescription)")
            }
            state = .stopped
            return false
        }

        installMeterTapIfNeeded()
        applyMix(project: project)

        // One host time shared by every node. The lead gives all the schedule
        // calls time to land before playback actually begins.
        let leadSeconds = 0.15
        let startHost = mach_absolute_time() + AVAudioTime.hostTime(forSeconds: leadSeconds)
        let playFromSeconds = start * secondsPerBar
        var scheduledAnything = false
        var timelineEnd: Double = 0

        for (_, node) in trackNodes {
            timelineEnd = max(timelineEnd, node.timelineEndSeconds)
            var scheduledThisNode = false

            if let loop = loopRange {
                let loopStartSeconds = loop.start * secondsPerBar
                let loopEndSeconds = loop.end * secondsPerBar
                let loopSeconds = loopEndSeconds - loopStartSeconds

                // First pass runs from the playhead to the end of the loop.
                if let first = window(node: node, fromSeconds: playFromSeconds, toSeconds: loopEndSeconds) {
                    schedule(node: node, window: first, baseHost: startHost, extraDelay: 0)
                    scheduledThisNode = true
                }
                // Then whole loop repeats. Each is scheduled at its own explicit
                // host time, because a source that only covers part of the loop
                // needs the silence before it preserved.
                if loopSeconds > 0,
                   let repeated = window(node: node, fromSeconds: loopStartSeconds, toSeconds: loopEndSeconds) {
                    let firstRepeatDelay = loopEndSeconds - playFromSeconds
                    for index in 0..<Self.maxQueuedLoops {
                        let delay = firstRepeatDelay + Double(index) * loopSeconds
                        schedule(node: node, window: repeated, baseHost: startHost, extraDelay: delay)
                    }
                    scheduledThisNode = true
                }
            } else if let whole = window(
                node: node,
                fromSeconds: playFromSeconds,
                toSeconds: node.timelineEndSeconds
            ) {
                schedule(node: node, window: whole, baseHost: startHost, extraDelay: 0)
                scheduledThisNode = true
            }

            if scheduledThisNode {
                node.player.play()
                scheduledAnything = true
            }
        }

        guard scheduledAnything else {
            state = .stopped
            return false
        }

        startHostTime = startHost
        startBar = start
        playheadBar = start
        stopAtSeconds = loopRange == nil ? max(0.1, timelineEnd - playFromSeconds) : nil
        state = .playing
        startDisplayTimer()
        return true
    }

    /// The slice of a source covering the timeline range `[from, to)`.
    private struct PlaybackWindow {
        var delaySeconds: Double
        var frameOffset: AVAudioFramePosition
        var frameCount: AVAudioFrameCount
    }

    private func window(node: TrackNode, fromSeconds: Double, toSeconds: Double) -> PlaybackWindow? {
        guard toSeconds > fromSeconds else { return nil }
        let rate = node.source.sampleRate
        guard rate > 0 else { return nil }

        let localFrom = fromSeconds - node.timelineStartSeconds
        let localTo = min(toSeconds - node.timelineStartSeconds, node.source.durationSeconds)
        let clampedFrom = max(0, localFrom)
        guard localTo > clampedFrom else { return nil }

        return PlaybackWindow(
            delaySeconds: max(0, node.timelineStartSeconds - fromSeconds),
            frameOffset: AVAudioFramePosition(clampedFrom * rate),
            frameCount: AVAudioFrameCount(max(1, (localTo - clampedFrom) * rate))
        )
    }

    private func schedule(node: TrackNode, window: PlaybackWindow, baseHost: UInt64, extraDelay: Double) {
        let delay = window.delaySeconds + extraDelay
        let host = delay > 0 ? baseHost + AVAudioTime.hostTime(forSeconds: delay) : baseHost
        let time = AVAudioTime(hostTime: host)

        switch node.source {
        case .file(let file):
            guard window.frameOffset < file.length else { return }
            let frames = min(window.frameCount, AVAudioFrameCount(file.length - window.frameOffset))
            guard frames > 0 else { return }
            node.player.scheduleSegment(
                file,
                startingFrame: window.frameOffset,
                frameCount: frames,
                at: time,
                completionHandler: nil
            )
        case .buffer(let buffer):
            guard let slice = self.slice(buffer, from: window.frameOffset, frames: window.frameCount) else { return }
            node.player.scheduleBuffer(slice, at: time, options: [], completionHandler: nil)
        }
    }

    /// `scheduleBuffer` has no frame-offset variant, so starting mid-buffer
    /// means handing it a copy of the remainder.
    private func slice(
        _ buffer: AVAudioPCMBuffer,
        from offset: AVAudioFramePosition,
        frames requested: AVAudioFrameCount
    ) -> AVAudioPCMBuffer? {
        guard offset >= 0, offset < AVAudioFramePosition(buffer.frameLength) else { return nil }
        let available = AVAudioFrameCount(AVAudioFramePosition(buffer.frameLength) - offset)
        let count = min(requested, available)
        guard count > 0 else { return nil }
        if offset == 0, count == buffer.frameLength { return buffer }
        guard let copy = AVAudioPCMBuffer(pcmFormat: buffer.format, frameCapacity: count),
              let source = buffer.floatChannelData,
              let destination = copy.floatChannelData else {
            return nil
        }
        copy.frameLength = count
        for channel in 0..<Int(buffer.format.channelCount) {
            memcpy(
                destination[channel],
                source[channel] + Int(offset),
                Int(count) * MemoryLayout<Float>.size
            )
        }
        return copy
    }

    /// Starts playback with a count-in, and reports exactly when the punch-in
    /// bar begins so a recorder can be armed to the same instant.
    ///
    /// This is what makes a count-in worth having: the clicks, the backing
    /// track and the recorder are all pinned to one host time, so the take lands
    /// on the beat rather than wherever the user's reaction time put it. Before
    /// this, recording started the moment the button was pressed and the take
    /// always landed at the playhead with no way to prepare.
    @discardableResult
    public func playForRecording(project: LocalProject, countIn: CountIn) -> RecordingSync? {
        stop(notify: false)
        secondsPerBar = project.secondsPerBar

        do {
            if !engine.isRunning {
                engine.prepare()
                try engine.start()
                engineStarted = true
            }
        } catch {
            DispatchQueue.main.async { [weak self] in
                self?.onWarning?("Couldn't start audio: \(error.localizedDescription)")
            }
            return nil
        }

        installMeterTapIfNeeded()
        applyMix(project: project)

        let leadSeconds = Double(countIn.bars) * secondsPerBar
        // The same 0.15s of slack the transport uses elsewhere, so every
        // schedule call has landed before the first click sounds.
        let originHost = mach_absolute_time() + AVAudioTime.hostTime(forSeconds: 0.15)
        let punchInHost = originHost + AVAudioTime.hostTime(forSeconds: leadSeconds)

        if countIn.bars > 0 {
            scheduleCountIn(bars: countIn.bars, startingAt: originHost)
        }

        // Play the existing material underneath, starting at the punch-in bar,
        // so the performer has the song to play along to.
        let playFromSeconds = countIn.punchInBar * secondsPerBar
        var timelineEnd: Double = 0
        for (_, node) in trackNodes {
            timelineEnd = max(timelineEnd, node.timelineEndSeconds)
            guard let window = window(
                node: node,
                fromSeconds: playFromSeconds,
                toSeconds: node.timelineEndSeconds
            ) else { continue }
            schedule(node: node, window: window, baseHost: punchInHost, extraDelay: 0)
            node.player.play()
        }

        startHostTime = punchInHost
        startBar = countIn.punchInBar
        playheadBar = countIn.punchInBar
        loopRange = nil
        stopAtSeconds = countIn.punchOutBar.map { max(0.1, ($0 - countIn.punchInBar) * secondsPerBar) }
            ?? max(0.1, timelineEnd - playFromSeconds)
        state = .playing
        startDisplayTimer()

        return RecordingSync(
            punchInHostTime: punchInHost,
            leadSeconds: AVAudioTime.seconds(forHostTime: punchInHost - mach_absolute_time()),
            durationSeconds: countIn.punchOutBar.map { max(0.1, ($0 - countIn.punchInBar) * secondsPerBar) }
        )
    }

    /// Schedules the count-in clicks: an accent on beat one, a plainer tick on
    /// the rest, so the player can hear where the bar starts.
    private func scheduleCountIn(bars: Int, startingAt originHost: UInt64) {
        let format = AVAudioFormat(standardFormatWithSampleRate: 44_100, channels: 1)
        guard let format else { return }

        if clickBuffers == nil {
            guard let accent = Self.makeClick(format: format, frequency: 1600, level: 0.36),
                  let beat = Self.makeClick(format: format, frequency: 1100, level: 0.22) else { return }
            clickBuffers = (accent, beat)
        }
        guard let buffers = clickBuffers else { return }

        let player: AVAudioPlayerNode
        if let existing = clickPlayer {
            player = existing
        } else {
            player = AVAudioPlayerNode()
            engine.attach(player)
            engine.connect(player, to: engine.mainMixerNode, format: format)
            clickPlayer = player
        }
        player.stop()

        let secondsPerBeat = secondsPerBar / 4
        for bar in 0..<bars {
            for beat in 0..<4 {
                let offset = Double(bar) * secondsPerBar + Double(beat) * secondsPerBeat
                let time = AVAudioTime(hostTime: originHost + AVAudioTime.hostTime(forSeconds: offset))
                player.scheduleBuffer(beat == 0 ? buffers.accent : buffers.beat, at: time, options: [], completionHandler: nil)
            }
        }
        player.play()
    }

    /// A short decaying sine. Deliberately not a sample: a click has to exist on
    /// a brand-new install with no content, and this needs no asset.
    private static func makeClick(format: AVAudioFormat, frequency: Double, level: Float) -> AVAudioPCMBuffer? {
        let seconds = 0.045
        let frames = AVAudioFrameCount(format.sampleRate * seconds)
        guard frames > 0,
              let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: frames),
              let channel = buffer.floatChannelData?[0] else { return nil }
        buffer.frameLength = frames
        for frame in 0..<Int(frames) {
            let t = Double(frame) / format.sampleRate
            let envelope = exp(-t * 90)
            channel[frame] = Float(sin(2 * .pi * frequency * t) * envelope) * level
        }
        return buffer
    }

    public func stop() {
        stop(notify: true)
    }

    private func stop(notify: Bool) {
        displayTimer?.invalidate()
        displayTimer = nil
        for (_, node) in trackNodes where node.player.isPlaying {
            node.player.stop()
        }
        clickPlayer?.stop()
        stopAtSeconds = nil
        loopRange = nil
        state = .stopped
        levelLock.lock()
        let silenced = trackPeaks.mapValues { _ in Float(0) }
        trackPeaks.removeAll()
        levelLock.unlock()
        if notify {
            DispatchQueue.main.async { [weak self] in
                self?.onMasterLevel?(0)
                self?.onTrackLevels?(silenced)
            }
        }
    }

    /// Moves the playhead without starting playback.
    public func seek(toBar bar: Double) {
        playheadBar = max(0, bar)
        let value = playheadBar
        DispatchQueue.main.async { [weak self] in self?.onPlayheadMoved?(value) }
    }

    // MARK: Playhead

    private func startDisplayTimer() {
        displayTimer?.invalidate()
        let timer = Timer(timeInterval: 1.0 / 30.0, repeats: true) { [weak self] _ in
            self?.tick()
        }
        // .common keeps the playhead moving while a menu is open or a splitter is
        // being dragged, instead of freezing until the user lets go.
        RunLoop.main.add(timer, forMode: .common)
        displayTimer = timer
    }

    private func tick() {
        guard state == .playing else { return }
        let now = mach_absolute_time()
        guard now > startHostTime else { return }
        let elapsed = AVAudioTime.seconds(forHostTime: now - startHostTime)

        if let stopAt = stopAtSeconds, elapsed >= stopAt {
            // Everything has finished. Park the playhead at the end rather than
            // leaving the button stuck on "Stop" forever, which is what happened
            // before because nothing ever observed completion.
            let endBar = startBar + stopAt / secondsPerBar
            stop(notify: true)
            playheadBar = endBar
            DispatchQueue.main.async { [weak self] in self?.onPlayheadMoved?(endBar) }
            return
        }

        var bar = startBar + elapsed / secondsPerBar
        if let loop = loopRange, bar >= loop.end {
            let span = loop.end - loop.start
            if span > 0 {
                bar = loop.start + (bar - loop.end).truncatingRemainder(dividingBy: span)
            }
        }
        playheadBar = bar
        DispatchQueue.main.async { [weak self] in self?.onPlayheadMoved?(bar) }
        publishTrackLevels()
    }

    private func publishTrackLevels() {
        guard onTrackLevels != nil else { return }
        levelLock.lock()
        let snapshot = trackPeaks
        // Decay every meter each tick so a track that stops playing falls to
        // zero instead of freezing at its last peak.
        for (key, value) in trackPeaks {
            trackPeaks[key] = value * 0.72
        }
        levelLock.unlock()
        DispatchQueue.main.async { [weak self] in self?.onTrackLevels?(snapshot) }
    }

    // MARK: Metering

    private func installMeterTapIfNeeded() {
        guard !tapInstalled else { return }
        let mixer = engine.mainMixerNode
        let format = mixer.outputFormat(forBus: 0)
        guard format.sampleRate > 0, format.channelCount > 0 else { return }
        mixer.installTap(onBus: 0, bufferSize: 2048, format: format) { [weak self] buffer, _ in
            guard let self, let channels = buffer.floatChannelData else { return }
            var peak: Float = 0
            let frames = Int(buffer.frameLength)
            for channel in 0..<Int(buffer.format.channelCount) {
                let samples = channels[channel]
                for frame in stride(from: 0, to: frames, by: 4) {
                    peak = max(peak, abs(samples[frame]))
                }
            }
            DispatchQueue.main.async { self.onMasterLevel?(min(peak, 1)) }
        }
        tapInstalled = true
    }
}
