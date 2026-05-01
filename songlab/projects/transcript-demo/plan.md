# Transcript Demo Songlab Plan

## Prompt

Convert the production walkthrough for Down So This Song Starts Out With A Simple Chord Progression into an original Neon Studio project. Carry over the described arrangement (Production Notes, Intro, Verse, Build, Drop), track roles (clap, drums, hat, kick, snare, bass), and production techniques, but keep the result original and portable.

## Normalized Intent

Create an original hook-first future-bass project with a readable arrangement, clean low end, and a portable Neon Studio session.

## Transcript Ingest

- Raw transcript: `songlab/projects/transcript-demo/transcript.txt`
- Structured spec: `songlab/projects/transcript-demo/transcript_spec.json`
- Coverage summary: `songlab/projects/transcript-demo/transcript_spec.md`
- Timecoded: `True`
- Sections: `5`
- Tempo hint: `unset`
- Key hints: `unset`
- Top track roles: clap, drums, hat, kick, snare, bass, chords, noise
- Section flow: Production Notes -> Intro -> Verse -> Build -> Drop
- Open question: Transcript does not explicitly state a BPM.
- Open question: Transcript does not clearly state the key.

## Guardrails

- Do not copy the named song melody, lyrics, or stems exactly.
- Treat references as a palette, emotion, arrangement, and mixing lane.
- Keep the resulting .neon.json project portable and original.

## Current Project

- No current project file found yet.

## Target Lane: Future Bass Generic

### Reference Summary
- Memorable lead motif with simple supporting harmony
- Pumped chords and a wide but controlled top end
- Build-to-drop contrast more important than raw layer count

### Arrangement Targets
- Intro, verse, build, drop, break, final drop, outro
- Every section should have a reason to exist in the project file

### Sound Targets
- Lead, chords, bass, drums, FX as obvious primary lanes
- Automation and ear-candy lanes only when they have a clear job

### Mix Targets
- No low-frequency clutter outside bass and kick
- Final drop brighter and wider than the first

## Workflow

### Transcript Ingest
- Goal: Convert the walkthrough transcript into a structured project spec before editing the song.
- Deliverable: transcript.txt copied into the songlab session
- Deliverable: transcript_spec.json with sections, tracks, plugins, and techniques
- Deliverable: transcript_spec.md human-readable coverage summary

### Reference DNA
- Goal: Convert the user prompt into an original target lane with explicit guardrails.
- Deliverable: session.json updated with normalized intent
- Deliverable: plan.md with arrangement and mix targets

### Current Project Audit
- Goal: Read the current .neon.json and generator so edits land on the real project, not a stale seed.
- Deliverable: data/projects/transcript-demo.neon.json
- Deliverable: factory/projects/transcript-demo.neon.json
- Deliverable: render_transcript_demo.py (create if missing)

### Generator / Project Edit
- Goal: Adjust the renderer and project metadata together so arrangement, stems, and recipe stay coherent.
- Deliverable: Updated stem synthesis or arrangement logic
- Deliverable: Updated track/recipe metadata when musical structure changes

### Render + Sync
- Goal: Render the mix, stems, and MIDI and ensure the factory/data project files match.
- Deliverable: exports/transcript_demo_full_mix.wav
- Deliverable: midi/transcript_demo_arrangement.mid

### Verification Loop
- Goal: Check the result against the acceptance criteria, then log the next gap instead of stopping at a vague impression.
- Deliverable: iteration log entry
- Deliverable: next-pass backlog item

## Acceptance Checks

- Portable project renders with coherent stems and metadata
- The drop reads immediately from the recipe and playlist

## Iteration Backlog

- [pending] Simplify the melodic contour before adding countermelodies
- [pending] Tighten drums before touching mastering-style loudness
