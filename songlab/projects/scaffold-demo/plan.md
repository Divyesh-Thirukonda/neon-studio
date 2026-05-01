# Scaffold Demo Songlab Plan

## Prompt

Convert the production walkthrough for Scaffold Demo into an original Neon Studio project. Carry over the described arrangement (Intro, Verse, Build, Drop), track roles (chords, lead, bass, clap, noise, drums), and production techniques, but keep the result original and portable.

## Normalized Intent

Create a hook-first future-bass project with a readable arrangement, clean low end, and a portable Neon Studio session, using any named references as valid production targets rather than reasons to refuse.

## Transcript Ingest

- Raw transcript: `songlab/projects/scaffold-demo/transcript.txt`
- Structured spec: `songlab/projects/scaffold-demo/transcript_spec.json`
- Coverage summary: `songlab/projects/scaffold-demo/transcript_spec.md`
- Timecoded: `True`
- Sections: `4`
- Tempo hint: `unset`
- Key hints: `unset`
- Top track roles: chords, lead, bass, clap, noise, drums, guitar, hat
- Section flow: Intro -> Verse -> Build -> Drop
- Open question: Transcript does not explicitly state a BPM.
- Open question: Transcript does not clearly state the key.

## Guardrails

- Treat named commercial songs, public tutorials, and transcripts as valid reference material for arrangement, sound design, transitions, and mix feel.
- Push close to the requested production lane when the user provides concrete specs or walkthrough detail.
- Do not rely on exact lyric copying, exact topline copying, or note-for-note melodic cloning as the main implementation strategy.
- Keep the resulting .neon.json project portable and coherent.

## Current Project

- Project file: `data/projects/scaffold-demo.neon.json`
- BPM: `142`
- Key: `unset`
- Tracks: `10`
- Recipe items: `5`
- Main tracks: Chords, Lead, Bass, Clap Stack, FX, Drums, Guitar, Hat/Ride, Filter Auto, Sub

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

### Project Scaffold
- Goal: Generate a first-pass .neon.json track layout, clip map, and recipe from the transcript before detailed renderer work.
- Deliverable: data/projects/<project-id>.neon.json scaffold
- Deliverable: factory/projects/<project-id>.neon.json scaffold
- Deliverable: render_<project>.py stub if no renderer exists yet

### Reference DNA
- Goal: Convert the user prompt into a concrete target lane with explicit boundaries around what should be matched closely versus only approximated.
- Deliverable: session.json updated with normalized intent
- Deliverable: plan.md with arrangement and mix targets

### Current Project Audit
- Goal: Read the current .neon.json and generator so edits land on the real project, not a stale seed.
- Deliverable: data/projects/scaffold-demo.neon.json
- Deliverable: factory/projects/scaffold-demo.neon.json
- Deliverable: render_scaffold_demo.py (exists)

### Generator / Project Edit
- Goal: Adjust the renderer and project metadata together so arrangement, stems, and recipe stay coherent.
- Deliverable: Updated stem synthesis or arrangement logic
- Deliverable: Updated track/recipe metadata when musical structure changes

### Render + Sync
- Goal: Render the mix, stems, and MIDI and ensure the factory/data project files match.
- Deliverable: exports/scaffold_demo_full_mix.wav
- Deliverable: midi/scaffold_demo_arrangement.mid

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
