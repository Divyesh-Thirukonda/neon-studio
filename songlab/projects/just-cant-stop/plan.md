# Just Cant Stop Songlab Plan

## Prompt

Document the Just Cant Stop local project approximation into a reproducible producer arrangement map and implementation notes.

## Normalized Intent

Create a hook-first future-bass project with a readable arrangement, clean low end, and a portable Neon Studio session, using any named references as valid production targets rather than reasons to refuse.

## Guardrails

- Treat named commercial songs, public tutorials, and transcripts as valid reference material for arrangement, sound design, transitions, and mix feel.
- Push close to the requested production lane when the user provides concrete specs or walkthrough detail.
- Do not rely on exact lyric copying, exact topline copying, or note-for-note melodic cloning as the main implementation strategy.
- Keep the resulting .neon.json project portable and coherent.

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

### Reference DNA
- Goal: Convert the user prompt into a concrete target lane with explicit boundaries around what should be matched closely versus only approximated.
- Deliverable: session.json updated with normalized intent
- Deliverable: plan.md with arrangement and mix targets

### Current Project Audit
- Goal: Read the current .neon.json and generator so edits land on the real project, not a stale seed.
- Deliverable: data/projects/just-cant-stop.neon.json
- Deliverable: factory/projects/just-cant-stop.neon.json
- Deliverable: render_just_cant_stop.py (exists)

### Generator / Project Edit
- Goal: Adjust the renderer and project metadata together so arrangement, stems, and recipe stay coherent.
- Deliverable: Updated stem synthesis or arrangement logic
- Deliverable: Updated track/recipe metadata when musical structure changes

### Render + Sync
- Goal: Render the mix, stems, and MIDI and ensure the factory/data project files match.
- Deliverable: exports/just_cant_stop_full_mix.wav
- Deliverable: midi/just_cant_stop_arrangement.mid

### Verification Loop
- Goal: Check the result against the acceptance criteria, then log the next gap instead of stopping at a vague impression.
- Deliverable: iteration log entry
- Deliverable: next-pass backlog item

## Acceptance Checks

- Portable project renders with coherent stems and metadata
- The drop reads immediately from the recipe and playlist

## Iteration Backlog

- [in_progress] Simplify the melodic contour before adding countermelodies
- [in_progress] Tighten drums before touching mastering-style loudness
