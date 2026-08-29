# Neon Alone Songlab Plan

## Prompt

Create an original Neon Studio track in the production lane of Marshmello's Alone: bright future-bass / melodic trap, 142 BPM, D major, simple emotional hook, huge sidechained drops, clean festival mix. Do not copy exact lyrics, samples, or topline.

## Normalized Intent

Create a bright future-bass / festival EDM track that pushes close to the emotional and production lane of Marshmello's Alone, using the reference aggressively for arrangement and sound, while avoiding exact topline or lyric cloning.

## Transcript Ingest

- Raw transcript: `songlab/projects/neon-alone/transcript.txt`
- Structured spec: `songlab/projects/neon-alone/transcript_spec.json`
- Coverage summary: `songlab/projects/neon-alone/transcript_spec.md`
- Timecoded: `False`
- Sections: `11`
- Tempo hint: `142`
- Key hints: `D major`
- Fill-in-blanks lane: `bright_future_bass`
- Inferred decisions: `24`
- Top track roles: lead, fx, chords, drums, bass, automation, hat, clap
- Section flow: Production Notes -> Second Drop -> Intro -> Verse -> Build -> Intro -> Production Notes -> Break -> Build -> Drop

## Guardrails

- Treat named commercial songs, public tutorials, and transcripts as valid reference material for arrangement, sound design, transitions, and mix feel.
- Push close to the requested production lane when the user provides concrete specs or walkthrough detail.
- Do not rely on exact lyric copying, exact topline copying, or note-for-note melodic cloning as the main implementation strategy.
- Keep the resulting .neon.json project portable and coherent.

## Current Project

- Project file: `data/projects/neon-alone.neon.json`
- BPM: `142`
- Key: `D Major`
- Tracks: `12`
- Recipe items: `18`
- Main tracks: Lead, FX, Chords, Drums, Bass, Filter Auto, Hat/Ride, Clap Stack, Sub, Vocals

## Target Lane: Marshmello Alone Lane

### Reference Summary
- Simple childlike hook, then fuller filled-in drop hook
- Wide supersaw chords with clean sub/fat bass support
- Trap-leaning kick, clap, and hat grid with restrained density
- Build based on noise, filter sweep, clap roll, teaser lead, and impact
- Second drop should add width, hats/ride motion, and extra sparkle rather than a new song section

### Arrangement Targets
- 16-bar intro and verse that establish hook DNA before the first drop
- First drop should feel open and memorable, not over-arranged
- Mid-song break should strip back to pads or motif fragments
- Eight-bar build should stage tension through filter, roll, riser, and bass print
- Final drop should escalate mostly through width, cymbal energy, and ear candy

### Sound Targets
- Square/saw lead as the center hook voice
- Supersaw chord stack with sidechain pump
- Sub plus mid bass that tracks the chord rhythm
- White-noise uplifters, downlifters, impact, reverse tail, crowd/air bed
- Optional muted guitar or pluck in verse only if it leaves the drop clean

### Mix Targets
- Low end belongs mostly to kick and bass
- Lead should be bright but not brittle
- Claps should feel wider than the core snare
- Build automation should be obvious in both audio and project metadata

## Workflow

### Transcript Ingest
- Goal: Convert the walkthrough transcript into a structured project spec before editing the song.
- Deliverable: transcript.txt copied into the songlab session
- Deliverable: transcript_spec.json with sections, tracks, plugins, and techniques
- Deliverable: transcript_spec.md human-readable coverage summary
- Deliverable: fill_in_blanks.md with inferred defaults for missing production details

### Project Materialization
- Goal: Generate the actual .neon.json project layout, clip map, and renderer entrypoint from the transcript before detailed song work.
- Deliverable: data/projects/<project-id>.neon.json project
- Deliverable: factory/projects/<project-id>.neon.json bundled project
- Deliverable: render_<project>.py generated product renderer if no renderer exists yet

### Reference DNA
- Goal: Convert the user prompt into a concrete target lane with explicit boundaries around what should be matched closely versus only approximated.
- Deliverable: session.json updated with normalized intent
- Deliverable: plan.md with arrangement and mix targets

### Current Project Audit
- Goal: Read the current .neon.json and generator so edits land on the real project, not a stale seed.
- Deliverable: data/projects/neon-alone.neon.json
- Deliverable: factory/projects/neon-alone.neon.json
- Deliverable: render_neon_alone.py (exists)

### Generator / Project Edit
- Goal: Adjust the renderer and project metadata together so arrangement, stems, and recipe stay coherent.
- Deliverable: Updated stem synthesis or arrangement logic
- Deliverable: Updated track/recipe metadata when musical structure changes

### Render + Sync
- Goal: Render the mix, stems, and MIDI and ensure the factory/data project files match.
- Deliverable: exports/neon_alone_full_mix.wav
- Deliverable: midi/neon_alone_arrangement.mid

### Verification Loop
- Goal: Check the result against the acceptance criteria, then log the next gap instead of stopping at a vague impression.
- Deliverable: iteration log entry
- Deliverable: next-pass backlog item

## Acceptance Checks

- Project captures the commercial reference feel without relying on exact topline copying
- The hook is memorable after one listen
- Drop one and drop two share identity but not identical energy
- The .neon.json, stems, MIDI, and bundled app seed all agree on BPM and layout

## Iteration Backlog

- [in_progress] Simplify the hook if it feels too clever
- [in_progress] Make the drop brighter before making it busier
- [pending] Prefer stronger sidechain and spacing over adding extra layers
- [pending] If the final drop is weak, add doubles, crashes, or ear candy before rewriting chords
