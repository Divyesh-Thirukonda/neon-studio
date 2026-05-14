---
name: does-this-sound-good
description: Use this skill when the user asks for a production-quality verdict on an actual Neon Studio song, mix, rendered stem set, or .neon project, including whether it sounds good, is ready to ship, needs mix feedback, or has arrangement, loudness, stereo, missing-audio, or next-iteration issues. Do not use it for developer requests to create, improve, debug, or integrate this skill or the app itself.
---

# Does This Sound Good

Use this skill to give a direct production-quality verdict on a real Neon Studio music project. The answer should be concrete: say whether it sounds good, what evidence supports that verdict, and what to fix next.

## Routing Guard

Use this skill only for song-quality review. If the user is asking to edit software, improve this skill, change the app integration, update docs, or alter `tools/does_this_sound_good.py`, treat that as a developer request and do not run the song checker except as targeted validation.

If the request is hybrid, split it:

1. Developer work first, such as script, app, skill, or docs changes.
2. Song-quality validation second, only if the feature needs a real project check.

## Workflow

1. Identify the project.
   - Prefer an explicit `--project-id`.
   - If the app exported a temporary current project, use `--project`.
   - If unclear, inspect `data/projects/*.neon.json`, `factory/projects/*.neon.json`, and current Songlab session files.
2. Run the local checker:
   - `python3 tools/does_this_sound_good.py --project-id <project-id> --format markdown`
   - App-exported current state: `python3 tools/does_this_sound_good.py --root <support-root> --project <current.neon.json> --format markdown`
   - Use `/usr/bin/python3` when matching the native app runtime matters.
3. If stems or the full mix are stale and the request is truly about the rendered song, render with the project generator, then rerun the check.
4. Read the project metadata and checker output before answering. Do not answer from the score alone.
5. Give a verdict in this shape:
   - `Verdict`: yes, close, not yet, or cannot judge.
   - `Evidence`: strongest production positives and biggest technical blockers.
   - `Next`: 2-5 concrete edits, ordered by impact.

## Evidence Rules

The checker is a technical/project analysis, not proof that a human listened to the full track. Be precise:

- Say "the checker reports" or "the technical pass shows" when relying on metrics.
- Mention if no fresh render or no playable audio was available.
- If the user asks for taste-level judgment, add that hook memorability, emotional payoff, and sound-choice taste still need a listen pass unless you actually listened to the audio.
- Do not call a song finished when the report has high-severity clipping, missing-audio, stereo, or low-end issues.

## Evaluation Lens

Prioritize issues that change the listener's impression:

- hook and arrangement clarity
- drop or chorus payoff
- transition energy
- low-end ownership between kick and bass
- clipping, loudness, punch, and headroom
- stereo width and mono compatibility
- harsh highs, muddy low mids, or missing air
- missing audio references or app/project mismatch

Use the numeric score as a starting point, not the full review:

- `82+`: likely good technically; still call out any taste/listen-pass risks.
- `68-81`: close; identify the 1-3 blockers that would most improve listener impact.
- `<68`: not yet; prioritize technical blockers before arrangement polish.
- no playable audio: cannot judge; ask for render/stems only after checking expected project paths.

Do not pad the response with vague praise. Prefer one direct positive and one direct concern over a long list of generic comments.

## App Integration

The native Neon Studio app exposes this as the `Check` project action and `Does This Sound Good?` menu command. Both call `tools/does_this_sound_good.py` against the current project state and show the same score, issues, and next actions in the app.
