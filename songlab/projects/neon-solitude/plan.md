# Neon Solitude Songlab Plan

## Prompt

recreate Alone by Marshmello

## Normalized Intent

Create an original bright future-bass / festival EDM track in the emotional lane of Marshmello's Alone without copying the melody, lyrics, or arrangement bar-for-bar.

## Guardrails

- Do not copy the named song melody, lyrics, or stems exactly.
- Treat references as a palette, emotion, arrangement, and mixing lane.
- Keep the resulting .neon.json project portable and original.

## Current Project

- Project file: `data/projects/neon-solitude.neon.json`
- BPM: `142`
- Key: `E minor / G major`
- Tracks: `14`
- Recipe items: `23`
- Main tracks: Drums, Bass, Chords, Lead, FX, Guitar Bass, Hat/Ride, Frozen Bass, Filter Auto, Crowd Duck

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

### Reference DNA
- Goal: Convert the user prompt into an original target lane with explicit guardrails.
- Deliverable: session.json updated with normalized intent
- Deliverable: plan.md with arrangement and mix targets

### Current Project Audit
- Goal: Read the current .neon.json and generator so edits land on the real project, not a stale seed.
- Deliverable: data/projects/neon-solitude.neon.json
- Deliverable: factory/projects/neon-solitude.neon.json
- Deliverable: render_neon_solitude.py (exists)

### Generator / Project Edit
- Goal: Adjust the renderer and project metadata together so arrangement, stems, and recipe stay coherent.
- Deliverable: Updated stem synthesis or arrangement logic
- Deliverable: Updated track/recipe metadata when musical structure changes

### Render + Sync
- Goal: Render the mix, stems, and MIDI and ensure the factory/data project files match.
- Deliverable: exports/neon_solitude_full_mix.wav
- Deliverable: midi/neon_solitude_arrangement.mid

### Verification Loop
- Goal: Check the result against the acceptance criteria, then log the next gap instead of stopping at a vague impression.
- Deliverable: iteration log entry
- Deliverable: next-pass backlog item

## Acceptance Checks

- Project remains original and avoids the commercial topline
- The hook is memorable after one listen
- Drop one and drop two share identity but not identical energy
- The .neon.json, stems, MIDI, and bundled app seed all agree on BPM and layout

## Iteration Backlog

- [pending] Simplify the hook if it feels too clever
- [pending] Make the drop brighter before making it busier
- [pending] Prefer stronger sidechain and spacing over adding extra layers
- [pending] If the final drop is weak, add doubles, crashes, or ear candy before rewriting chords
