# Transcript Spec: Neon Alone

## Source Prompt

Create an original Neon Studio track in the production lane of Marshmello's Alone: bright future-bass / melodic trap, 142 BPM, D major, simple emotional hook, huge sidechained drops, clean festival mix. Do not copy exact lyrics, samples, or topline.

## Transcript Overview

- Word count: `481`
- Timecoded: `False`
- Segments: `11`
- Sections: `11`
- Tempo hint: `142`
- Key hints: `D major`

## Derived Prompt

Convert the production walkthrough for Neon Alone into an original Neon Studio project. Carry over the described arrangement (Production Notes, Second Drop, Intro, Verse, Build, Intro), track roles (lead, chords, drums, bass, hat, automation), and production techniques, but keep the result original and portable.

## Fill In The Blanks

- Style lane: `bright_future_bass`
- Decisions: `24`
- Policy: Infer plausible production defaults from the brief; do not claim exact original samples, patches, MIDI, or mix values without evidence.

## Section Map

### Production Notes
- tracks: bass
- Project: Neon Alone, an original future-bass / melodic trap production in the production lane of Marshmello's Alone, not a literal cover. Global tempo: 142 BPM, 4/4.
- lane events: `{"bass": {"events": [{"beat": 0.0, "duration": 0.72}, {"beat": 2.0, "duration": 0.72}], "kind": "beatPattern", "source": "fill_in_blanks"}}`

### Second Drop
- tracks: bass, chords, clap, drums, fx, hat, impact, kick, lead, noise, reverse, ride, riser, sub, vocal | techniques: layering, reverb, reverse, sidechain, automation, stereo, distortion
- Mood: lonely-to-euphoric, bright, simple, chant-like, festival-ready. Sound identity: childlike square/saw lead hook, wide supersaw chords, clean sub plus mid bass, trap/future-bass drums, clap stack, offbeat hats, ride lift in the final drop, white noise risers, reverse tails, i
- lane events: `{"bass": {"events": [{"beat": 0.0, "duration": 0.72}, {"beat": 1.5, "duration": 0.72}, {"beat": 2.5, "duration": 0.72}], "kind": "beatPattern", "source": "fill_in_blanks"}, "chords": {"kind": "progressionSymbols", "progressionSymbols": ["Em7", "Cmaj7", "Gadd9", "Dadd9"], "source": "fill_in_blanks"}, "clap": {"events": [{"beat": 0.5}, {"beat": 1.5}, {"beat": 2.5}, {"beat": 3.5}], "kind": "beatPattern", "source": "natural_language"}, "hat": {"events": [{"beat": 0.0}, {"beat": 0.25}, {"beat": 0.5}, {"beat": 0.75}], "kind": "beatPattern", "source": "fill_in_blanks", "spacingBeats": 0.25}, "kick": {"events": [{"beat": 0.0}, {"beat": 2.0}], "kind": "beatPattern", "source": "fill_in_blanks"}, "lead": {"events": [{"beat": 0.0, "duration": 0.42}, {"beat": 0.5, "duration": 0.42}, {"beat": 1.0, "duration": 0.42}, {"beat": 2.0, "duration": 0.42}, {"beat": 2.5, "duration": 0.42}], "kind": "beatPattern", "motifRole": "hook", "source": "fill_in_blanks"}, "snare": {"events": [{"beat": 1.0}, {"beat": 3.0}], "kind": "beatPattern", "source": "fill_in_blanks"}}`
- lane transforms: `{"drums": {"overrides": {"ride": true}}}`

### Intro
- tracks: chords, lead, fx | techniques: filtering, reverb
- Section 1 Intro bars 1-8: filtered D major chord bed and tiny lead-hook fragments. Chords: Dmaj at beat 1, Amaj at beat 2, Bmin at beat 3, Gmaj at beat 4.
- lane events: `{"chords": {"events": [{"beat": 0.0, "duration": 0.82}, {"beat": 1.0, "duration": 0.82}, {"beat": 2.0, "duration": 0.82}, {"beat": 3.0, "duration": 0.9}], "kind": "progressionSymbols", "progressionSymbols": ["D", "Bmin", "F#"], "source": "natural_language"}, "lead": {"events": [{"beat": 0.0, "duration": 0.5, "gain": 0.6, "note": 69, "noteName": "A4"}, {"beat": 0.5, "duration": 0.5, "gain": 0.55, "note": 66, "noteName": "F#4"}, {"beat": 1.5, "duration": 0.75, "gain": 0.65, "note": 74, "noteName": "D5"}, {"beat": 2.5, "duration": 0.5, "gain": 0.55, "note": 71, "noteName": "B4"}], "kind": "notePattern", "source": "lane_map"}}`

### Verse
- tracks: automation, bass, chords, fx, lead, drums, vocal | techniques: automation, filtering, eq, reverb
- Automation: bars 1-8 chords.filter 0.2->0.55 ease-in, fx.width 0.35->0.7. Section 2 Verse bars 9-16: keep the same harmonic DNA but make the hook sparse and intimate.
- lane events: `{"automation": {"envelopes": [{"barOffset": 0, "bars": 8, "curve": "ease_in", "end": 0.55, "parameter": "filter", "start": 0.2, "targetLane": "chords"}], "kind": "automationEnvelope", "source": "lane_map"}, "bass": {"events": [{"beat": 0.0, "duration": 0.72}, {"beat": 2.0, "duration": 0.72}], "kind": "beatPattern", "source": "fill_in_blanks"}, "chords": {"kind": "progressionSymbols", "progressionSymbols": ["Em7", "Cmaj7", "Gadd9", "Dadd9"], "source": "fill_in_blanks"}, "kick": {"events": [{"beat": 0.0}, {"beat": 2.0}], "kind": "beatPattern", "source": "fill_in_blanks"}, "lead": {"events": [{"beat": 0.0, "duration": 0.42}, {"beat": 1.0, "duration": 0.42}, {"beat": 2.5, "duration": 0.42}], "kind": "beatPattern", "motifRole": "motif", "source": "fill_in_blanks"}, "snare": {"events": [{"beat": 1.0}, {"beat": 3.0}], "kind": "beatPattern", "source": "fill_in_blanks"}}`
- lane transforms: `{"bass": {"followChords": true, "omitBeats": [3.0]}}`

### Build
- tracks: clap, crowd, drums, hat, kick, lead, pluck, riser, snare, fx, automation, noise, guitar | techniques: filtering, layering, tease_hook, automation, delay
- Drums: kick 1,3 snare 2,4 hats 1.5,2.5,3.5. Add a muted pluck double and soft air bed.
- lane events: `{"automation": {"envelopes": [{"barOffset": 0, "bars": 8, "curve": "ease_in", "end": 0.9, "parameter": "filter", "start": 0.15, "targetLane": "lead"}], "kind": "automationEnvelope", "source": "fill_in_blanks"}, "chords": {"kind": "progressionSymbols", "progressionSymbols": ["Em7", "Cmaj7", "Gadd9", "Dadd9"], "source": "fill_in_blanks"}, "clap": {"events": [{"beat": 1.0, "gain": 0.8}, {"beat": 3.0, "gain": 0.8}], "kind": "beatPattern", "source": "fill_in_blanks"}, "hat": {"events": [{"beat": 0.5}, {"beat": 1.5}, {"beat": 2.5}, {"beat": 2.0}, {"beat": 0.0}], "kind": "beatPattern", "source": "lane_map", "spacingBeats": 1.0}, "kick": {"events": [{"beat": 0.0}, {"beat": 2.0}], "kind": "beatPattern", "source": "lane_map"}, "lead": {"events": [{"beat": 0.0, "duration": 0.42}, {"beat": 0.5, "duration": 0.42}], "kind": "beatPattern", "motifRole": "tease", "source": "fill_in_blanks"}, "snare": {"events": [{"beat": 1.0}, {"beat": 3.0}], "kind": "beatPattern", "source": "lane_map"}}`

### Intro
- tracks: automation, bass, drums, fx, lead, riser, chords | techniques: arrangement_reuse, automation, filtering, reverb
- Lead: copy intro lead bars 1 transpose +12, then repeat filled in. Automation: bars 17-24 lead.filter 0.35->0.95 ease-in | drums.volume 0.35->0.85 step | fx.riser 0.2->1.
- lane events: `{"automation": {"envelopes": [{"barOffset": 16, "bars": 8, "curve": "ease_in", "end": 0.95, "parameter": "filter", "start": 0.35, "targetLane": "lead"}, {"curve": "step", "end": 0.85, "parameter": "volume", "start": 0.35, "targetLane": "drums"}], "kind": "automationEnvelope", "source": "lane_map"}, "bass": {"events": [{"beat": 0.0, "duration": 0.72}, {"beat": 2.0, "duration": 0.72}], "kind": "beatPattern", "source": "fill_in_blanks"}, "chords": {"kind": "progressionSymbols", "progressionSymbols": ["Em7", "Cmaj7", "Gadd9", "Dadd9"], "source": "fill_in_blanks"}, "kick": {"events": [{"beat": 0.0}, {"beat": 2.0}], "kind": "beatPattern", "source": "fill_in_blanks"}, "lead": {"events": [{"beat": 0.0, "duration": 0.28}, {"beat": 0.0, "duration": 0.82}, {"beat": 1.0, "duration": 0.45}], "kind": "beatPattern", "source": "lane_map"}, "snare": {"events": [{"beat": 1.0}, {"beat": 3.0}], "kind": "beatPattern", "source": "fill_in_blanks"}}`
- lane transforms: `{"lead": {"transform": "fill_in", "transposeSemitones": 12}}`

### Production Notes
- tracks: bass, chords, clap, crash, drums, hat, kick, lead, snare, sub | techniques: layering, sidechain
- Use wide supersaw chords with sidechain, sub root pulses, mid bass, clap stack, offbeat hats, simple memorable lead hook with a different contour from the reference. Drums: kick 1,3 snare 2,4 hats 1.5,2.5,3.5 crash 1.
- lane events: `{"bass": {"events": [{"beat": 0.0, "duration": 0.72}, {"beat": 2.0, "duration": 0.72}], "kind": "beatPattern", "source": "fill_in_blanks"}, "chords": {"kind": "progressionSymbols", "progressionSymbols": ["Em7", "Cmaj7", "Gadd9", "Dadd9"], "source": "fill_in_blanks"}, "clap": {"events": [{"beat": 1.0, "gain": 0.8}, {"beat": 3.0, "gain": 0.8}], "kind": "beatPattern", "source": "fill_in_blanks"}, "hat": {"events": [{"beat": 0.5}, {"beat": 1.5}, {"beat": 2.5}, {"beat": 0.0}], "kind": "beatPattern", "source": "lane_map", "spacingBeats": 1.0}, "kick": {"events": [{"beat": 0.0}, {"beat": 2.0}], "kind": "beatPattern", "source": "lane_map"}, "lead": {"events": [{"beat": 0.0, "duration": 0.5, "gain": 0.9, "note": 74, "noteName": "D5"}, {"beat": 0.5, "duration": 0.25, "gain": 0.75, "note": 69, "noteName": "A4"}, {"beat": 1.0, "duration": 0.5, "gain": 0.92, "note": 78, "noteName": "F#5"}, {"beat": 1.75, "duration": 0.25, "gain": 0.7, "note": 76, "noteName": "E5"}, {"beat": 2.25, "duration": 0.5, "gain": 0.8, "note": 71, "noteName": "B4"}], "kind": "notePattern", "source": "lane_map"}, "snare": {"events": [{"beat": 1.0}, {"beat": 3.0}], "kind": "beatPattern", "source": "lane_map"}}`

### Break
- tracks: automation, chords, lead, reverse, vocal, fx | techniques: automation, filtering, reverb, reverse, sidechain
- Automation: bars 25-40 chords.volume 0.95->0.88 sidechain | lead.width 0.55->0.78. Section 5 Break bars 41-48: strip to filtered chords, echo lead tails, tiny vocal-chop-like synth syllables without words, and reverse cymbal tail.
- lane events: `{"automation": {"envelopes": [{"barOffset": 24, "bars": 16, "curve": "linear", "end": 0.88, "parameter": "volume", "start": 0.95, "targetLane": "chords"}, {"curve": "linear", "end": 0.78, "parameter": "width", "start": 0.55, "targetLane": "lead"}], "kind": "automationEnvelope", "source": "lane_map"}, "chords": {"kind": "progressionSymbols", "progressionSymbols": ["Em7", "Cmaj7", "Gadd9", "Dadd9"], "source": "fill_in_blanks"}, "lead": {"events": [{"beat": 0.0, "duration": 0.42}, {"beat": 1.0, "duration": 0.42}, {"beat": 2.5, "duration": 0.42}], "kind": "beatPattern", "motifRole": "motif", "source": "fill_in_blanks"}}`

### Build
- tracks: automation, drums, hat, lead, riser, clap, fx, noise | techniques: automation, filtering, layering, delay
- Section 6 Build 2 bars 49-56: copy build 1 but add double-time hats, stronger riser, fake stop before drop. Automation: bars 49-56 lead.filter 0.2->1 ease-in | drums.volume 0.25->0.95 step | master.width 0.45->0.85.
- lane events: `{"automation": {"envelopes": [{"barOffset": 48, "bars": 8, "curve": "ease_in", "end": 1.0, "parameter": "filter", "start": 0.2, "targetLane": "lead"}, {"curve": "step", "end": 0.95, "parameter": "volume", "start": 0.25, "targetLane": "drums"}, {"curve": "linear", "end": 0.85, "parameter": "width", "start": 0.45}], "kind": "automationEnvelope", "source": "lane_map"}, "clap": {"events": [{"beat": 1.0, "gain": 0.8}, {"beat": 3.0, "gain": 0.8}], "kind": "beatPattern", "source": "fill_in_blanks"}, "hat": {"events": [{"beat": 0.0}, {"beat": 0.25}, {"beat": 0.5}, {"beat": 0.75}], "kind": "beatPattern", "source": "fill_in_blanks", "spacingBeats": 0.25}, "kick": {"events": [{"beat": 0.0}, {"beat": 2.0}], "kind": "beatPattern", "source": "fill_in_blanks"}, "lead": {"events": [{"beat": 0.0, "duration": 0.42}, {"beat": 0.5, "duration": 0.42}], "kind": "beatPattern", "motifRole": "tease", "source": "fill_in_blanks"}, "snare": {"events": [{"beat": 1.0}, {"beat": 3.0}], "kind": "beatPattern", "source": "fill_in_blanks"}}`
- lane transforms: `{"drums": {"overrides": {"hatSpacing": 0.25}}}`

### Drop
- tracks: bass, chords, crash, drums, fx, hat, lead, ride, sub | techniques: layering, sidechain, eq, compression, stereo
- Copy drop 1 drums, add ride on beat 1 and double-time hats. Copy drop 1 lead, add octave double and sparkle counter notes.
- lane events: `{"bass": {"events": [{"beat": 0.0, "duration": 0.72}, {"beat": 1.5, "duration": 0.72}, {"beat": 2.5, "duration": 0.72}], "kind": "beatPattern", "source": "fill_in_blanks"}, "chords": {"kind": "progressionSymbols", "progressionSymbols": ["Em7", "Cmaj7", "Gadd9", "Dadd9"], "source": "fill_in_blanks"}, "crash": {"events": [{"beat": 4.0}, {"beat": 6.0}, {"beat": 5.0}, {"beat": 4.0}, {"beat": 3.0}], "kind": "beatPattern", "source": "natural_language"}, "hat": {"events": [{"beat": 0.0}, {"beat": 0.25}, {"beat": 0.5}, {"beat": 0.75}], "kind": "beatPattern", "source": "fill_in_blanks", "spacingBeats": 0.25}, "kick": {"events": [{"beat": 0.0}, {"beat": 2.0}], "kind": "beatPattern", "source": "fill_in_blanks"}, "lead": {"events": [{"beat": 0.0, "duration": 0.42}, {"beat": 0.5, "duration": 0.42}, {"beat": 1.0, "duration": 0.42}, {"beat": 2.0, "duration": 0.42}, {"beat": 2.5, "duration": 0.42}], "kind": "beatPattern", "motifRole": "hook", "source": "fill_in_blanks"}, "ride": {"events": [{"beat": 0.0}], "kind": "beatPattern", "source": "natural_language"}, "snare": {"events": [{"beat": 1.0}, {"beat": 3.0}], "kind": "beatPattern", "source": "fill_in_blanks"}}`
- lane transforms: `{"drums": {"copyFrom": {"ordinal": 2, "sectionId": "section-09", "sectionType": "build"}, "overrides": {"hatSpacing": 0.25, "ride": true}}}`

### Outro
- tracks: automation, chords, downlifter, drums, impact, lead, fx | techniques: automation, filtering, reverb, sidechain
- Automation: bars 57-72 lead.width 0.7->0.92 | chords.filter 0.75->1. Section 8 Outro bars 73-80: remove drums, leave filtered hook echo, chord tail, downlifter, and final impact decay.
- lane events: `{"automation": {"envelopes": [{"barOffset": 56, "bars": 16, "curve": "linear", "end": 0.92, "parameter": "width", "start": 0.7, "targetLane": "lead"}, {"curve": "linear", "end": 1.0, "parameter": "filter", "start": 0.75, "targetLane": "chords"}], "kind": "automationEnvelope", "source": "lane_map"}, "chords": {"kind": "progressionSymbols", "progressionSymbols": ["Em7", "Cmaj7", "Gadd9", "Dadd9"], "source": "fill_in_blanks"}, "kick": {"events": [{"beat": 0.0}, {"beat": 2.0}], "kind": "beatPattern", "source": "fill_in_blanks"}, "lead": {"events": [{"beat": 0.0, "duration": 0.42}, {"beat": 1.0, "duration": 0.42}, {"beat": 2.5, "duration": 0.42}], "kind": "beatPattern", "motifRole": "motif", "source": "fill_in_blanks"}, "snare": {"events": [{"beat": 1.0}, {"beat": 3.0}], "kind": "beatPattern", "source": "fill_in_blanks"}}`

## Global Track Roles

- lead: 10 mention(s)
- fx: 9 mention(s)
- chords: 8 mention(s)
- drums: 8 mention(s)
- bass: 6 mention(s)
- automation: 6 mention(s)
- hat: 5 mention(s)
- clap: 4 mention(s)
- riser: 4 mention(s)
- kick: 3 mention(s)
- noise: 3 mention(s)
- sub: 3 mention(s)
- vocal: 3 mention(s)
- impact: 2 mention(s)
- reverse: 2 mention(s)
- ride: 2 mention(s)

## Mix Notes

- Mood: lonely-to-euphoric, bright, simple, chant-like, festival-ready.
- Use wide supersaw chords with sidechain, sub root pulses, mid bass, clap stack, offbeat hats, simple memorable lead hook with a different contour from the reference.
- Automation: bars 25-40 chords.volume 0.95->0.88 sidechain | lead.width 0.55->0.78.
- Copy drop 1 drums, add ride on beat 1 and double-time hats.
- Automation: bars 57-72 lead.width 0.7->0.92 | chords.filter 0.75->1.

## Automation Notes

- Mood: lonely-to-euphoric, bright, simple, chant-like, festival-ready.
- Section 1 Intro bars 1-8: filtered D major chord bed and tiny lead-hook fragments.
- Automation: bars 1-8 chords.filter 0.2->0.55 ease-in, fx.width 0.35->0.7.
- Drums: kick 1,3 snare 2,4 hats 1.5,2.5,3.5.
- Lead: copy intro lead bars 1 transpose +12, then repeat filled in.
- Automation: bars 25-40 chords.volume 0.95->0.88 sidechain | lead.width 0.55->0.78.
- Section 6 Build 2 bars 49-56: copy build 1 but add double-time hats, stronger riser, fake stop before drop.
- Automation: bars 57-72 lead.width 0.7->0.92 | chords.filter 0.75->1.

## Coverage Checklist

- Production Notes: bass
- Second Drop: bass, chords, clap, drums, fx, hat
- Intro: chords, lead
- Verse: automation, bass, chords, fx, lead
- Build: clap, crowd, drums, hat, kick, lead
- Intro: automation, bass, drums, fx, lead, riser
- Production Notes: bass, chords, clap, crash, drums, hat
- Break: automation, chords, lead, reverse, vocal
- Build: automation, drums, hat, lead, riser
- Drop: bass, chords, crash, drums, fx, hat
- Global track roles: lead, chords, drums, bass, hat, automation, fx, riser, clap, kick
- Fill-in-blanks pass: every musical section has roles, techniques, and starter lane data where practical.
- Exact-source details remain optional evidence, not blockers, unless the user explicitly asks for a forensic remake.

