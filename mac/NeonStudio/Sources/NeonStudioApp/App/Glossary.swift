import Foundation

/// Plain-language definitions for every piece of music-production jargon the
/// interface uses.
///
/// The app is used by people who have never opened a DAW, so no term appears on
/// screen without an explanation reachable from that spot — as a tooltip, as a
/// "?" button, or in the first-run tour. Definitions avoid defining jargon with
/// more jargon.
public enum Glossary {
    public struct Term {
        public let name: String
        public let short: String
        public let long: String
    }

    public static let all: [String: Term] = Dictionary(
        uniqueKeysWithValues: terms.map { ($0.name.lowercased(), $0) }
    )

    public static func term(_ name: String) -> Term? {
        all[name.lowercased()]
    }

    public static func short(_ name: String) -> String {
        term(name)?.short ?? name
    }

    public static func long(_ name: String) -> String {
        term(name)?.long ?? name
    }

    public static let terms: [Term] = [
        Term(
            name: "BPM",
            short: "Tempo — how fast the song is.",
            long: "BPM stands for beats per minute: how fast the song goes. 120 BPM is a typical pop tempo, 90 is relaxed, 150 is fast and energetic. Changing it speeds up or slows down the whole project."
        ),
        Term(
            name: "Bar",
            short: "One measure of music — four beats.",
            long: "A bar is one small chunk of time in a song, normally four beats — the length you'd count \"1, 2, 3, 4\". The numbers along the top of the arrangement are bar numbers, so bar 17 is where the second section usually starts."
        ),
        Term(
            name: "Track",
            short: "One instrument or sound, on its own row.",
            long: "A track holds one sound: the drums, the bass, a vocal. Keeping them apart means you can make the vocal louder without touching the drums."
        ),
        Term(
            name: "Clip",
            short: "A block of sound placed at a point in time.",
            long: "A clip is one chunk of audio or notes sitting on a track at a particular bar. Drag it left or right to move when it plays; drag its edge to make it longer or shorter."
        ),
        Term(
            name: "Stem",
            short: "The finished audio file for one track.",
            long: "A stem is the rendered audio for a single track — for example just the drums, exported as a .wav file. Neon Studio plays the stems it finds for each track."
        ),
        Term(
            name: "Mix",
            short: "The balance of loudness and position between tracks.",
            long: "Mixing is deciding how loud each track is and where it sits between the left and right speakers, so everything can be heard clearly at once."
        ),
        Term(
            name: "Gain",
            short: "How loud this track is.",
            long: "Gain, or volume, is how loud one track plays compared to the others. Turning gain up on the vocal makes the singer stand out."
        ),
        Term(
            name: "Pan",
            short: "Where the sound sits, left to right.",
            long: "Pan places a sound between your left and right speakers. Centre is straight ahead; panning a guitar left and a keyboard right makes both easier to hear."
        ),
        Term(
            name: "Mute",
            short: "Silence this track.",
            long: "Muting a track silences it without deleting anything. Useful for checking what a part actually contributes."
        ),
        Term(
            name: "Solo",
            short: "Hear only this track.",
            long: "Soloing a track silences every other track so you can hear this one on its own. Turn it off to hear the whole song again."
        ),
        Term(
            name: "Arm",
            short: "Ready this track to record onto.",
            long: "Arming a track marks it as the one that will capture audio the next time you record."
        ),
        Term(
            name: "Send",
            short: "How much of this track is fed to a shared effect.",
            long: "A send routes a copy of a track into a shared effect like reverb, so several tracks can sit in the same space. Higher send means more of that effect."
        ),
        Term(
            name: "Snap",
            short: "Makes edits line up to the grid.",
            long: "Snap pulls whatever you drag onto the nearest grid line, so parts stay in time. Set it to 1/4 note for normal work, or Off for free placement."
        ),
        Term(
            name: "Loop",
            short: "Repeat a section over and over.",
            long: "The loop range marks a stretch of bars that plays on repeat, so you can work on one section without restarting the song each time."
        ),
        Term(
            name: "Swing",
            short: "Nudges every other beat late for a bouncier feel.",
            long: "Swing delays every second subdivision slightly, turning a stiff straight rhythm into a looser, bouncier groove. 0 is perfectly straight."
        ),
        Term(
            name: "Automation",
            short: "A setting that changes over time on its own.",
            long: "Automation records how a control moves through the song — for example a filter opening up across a build. Each line is one control, and each dot is a value at a point in time."
        ),
        Term(
            name: "Piano roll",
            short: "The grid where you write melodies note by note.",
            long: "The piano roll shows pitch up the side and time across the bottom. Each block is one note: higher up is a higher pitch, wider is a longer note."
        ),
        Term(
            name: "Step sequencer",
            short: "A 16-button grid for drum patterns.",
            long: "Each of the 16 buttons is one sixteenth of a bar. Switch a button on and the sound plays at that moment — the quickest way to build a drum beat."
        ),
        Term(
            name: "Effect",
            short: "A processor that changes how a track sounds.",
            long: "Effects shape a sound after it is played: reverb adds space, compression evens out loud and quiet parts, EQ makes it brighter or warmer."
        ),
        Term(
            name: "Recipe",
            short: "The step-by-step build plan for this song.",
            long: "The recipe is Neon Studio's checklist of production steps for the song — what each section needs and whether it has been done yet."
        ),
        Term(
            name: "Mixdown",
            short: "One audio file containing the whole song.",
            long: "A mixdown combines every track into a single audio file you can send to somebody or upload. Everything you hear on playback ends up in it."
        ),
        Term(
            name: "Transcript",
            short: "A written description of a song to build from.",
            long: "Paste or choose a text file describing a song — a tutorial, a walkthrough, or just your own description — and Neon Studio turns it into a real project, filling in any details you didn't specify."
        ),
        Term(
            name: "Sound check",
            short: "An automatic review of how the song sounds.",
            long: "Sound check listens to the rendered audio and reports a score, what is working, what is not, and what to try next — loudness, stereo width, and balance between parts."
        ),
        Term(
            name: "Key",
            short: "The set of notes the song is built from.",
            long: "The key is the home note and scale a song uses, like E minor. Notes from the key sound settled together; notes outside it sound tense."
        ),
        Term(
            name: "Pattern",
            short: "A short reusable musical idea.",
            long: "A pattern is a small block of music — a drum beat or a riff — that you can place repeatedly through the arrangement instead of rewriting it."
        ),
        Term(
            name: "Sample",
            short: "A recorded sound you can reshape.",
            long: "A sample is a piece of recorded audio. You can trim it, change its pitch, stretch its length, or play it backwards without altering the original file."
        ),
        Term(
            name: "Velocity",
            short: "How hard a note is played.",
            long: "Velocity is how forcefully a note sounds — a lightly played note is quieter and softer than a hard one."
        )
    ]
}
