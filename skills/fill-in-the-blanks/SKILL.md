---
name: fill-in-the-blanks
description: Use this skill when a user describes a song, asks for something like a reference, provides a walkthrough/transcript/tutorial/step-by-step recipe, or wants an ambiguous idea turned into a buildable Neon Studio project. It handles the middle step in the normal flow: user description -> enriched production step-by-step -> agent builds the project. It fills missing arrangement, sound-design, automation, mix, and verification details with labeled plausible defaults instead of blocking on exact samples, presets, MIDI, automation curves, or fader values. Use before Songlab materialization or before continuing a generated song project from an ambiguous transcript.
---

# Fill In The Blanks

Use this for the normal Neon Studio song-generation path:

`user describes song -> Songlab transcript/spec -> fill in missing production detail -> materialized Neon Studio project -> render -> sound check -> iterate`

The goal is not forensic recovery. The goal is a buildable Neon Studio recipe that sounds like it belongs in the requested lane.

## Policy

- Treat missing exact sample names, plugin settings, MIDI notes, automation curves, and fader values as normal reference ambiguity.
- Fill the gap with a plausible production decision and label it as inferred.
- Do not claim an inferred choice is the original source detail.
- Only block when the user explicitly asks for a forensic remake or exact source recovery.
- Do not treat a reference fixture such as Just Cant Stop as the active song unless the user explicitly asks to make that song.
- Preserve explicit source details first; infer only what is missing or under-specified.
- After a render exists, use `does-this-sound-good` or `tools/does_this_sound_good.py` to turn technical/mix issues into the next iteration.

## Agent Flow

Use the integrated Songlab path for real work. Do not run the standalone filler as a replacement for project initialization.

1. Decide routing:
   - Song request: use this skill and Songlab.
   - Developer request about this skill/tool/app/docs: edit code/docs first; only run a song smoke test if needed for verification.
   - Hybrid request: complete the developer change, then run the smallest relevant song-flow check.
2. Create or refresh the Songlab session from the user description, transcript, or walkthrough:
   - transcript file: `python3 tools/songlab.py init --project-id <project-id> --prompt "<brief>" --transcript-file <file>`
   - direct user description: `python3 tools/songlab.py init --project-id <project-id> --prompt "<brief>" --transcript-text "<song description>"`
   - pasted transcript or long description: `python3 tools/songlab.py init --project-id <project-id> --prompt "<brief>" --transcript-stdin`
   - `--prompt` alone is not the enriched song-building path; use a transcript input when the goal is `description -> enriched step-by-step -> materialized project`.
   - `--no-fill-blanks` is only for debugging raw extraction.
3. Read the middle-step artifacts before building further:
   - `songlab/projects/<project-id>/transcript_spec.json`
   - `songlab/projects/<project-id>/transcript_spec.md`
   - `songlab/projects/<project-id>/fill_in_blanks.md`
   - `songlab/projects/<project-id>/session.json`
4. Build from the enriched spec:
   - use explicit source details for any real cues the user gave
   - use `fillInBlanks.decisions` for inferred tempo, key, section flow, roles, lane defaults, automation, sound-design moves, and mix targets
   - keep `.neon.json`, recipe metadata, renderer, stems, and MIDI coherent
5. Render or inspect audio when the task reaches a listenable state.
6. Run sound check when playable audio exists:
   - `python3 tools/does_this_sound_good.py --project-id <project-id> --format markdown`
7. Convert sound-check findings into concrete next edits and log the pass:
   - `python3 tools/songlab.py iterate --project-id <project-id> --note "<what changed and why>"`

## App Flow

The native app uses the same path. Project panel `Transcript`:

1. asks the user to pick a transcript text file
2. asks for project id, prompt, and overwrite behavior
3. runs `/usr/bin/python3 tools/songlab.py init --project-id <id> --prompt <prompt> --transcript-file <file> --force-materialize`
4. reloads projects and opens the materialized `.neon.json`

If you change this flow, rebuild with `npm run build:mac` and run a targeted Computer Use smoke test before marking the TODO complete.

## What To Infer

Infer enough for the next agent step to build without asking for every missing detail:

- arrangement: intro, setup/build, drop or chorus payoff, break/reset, second-drop escalation when implied, outro
- musical defaults: BPM, key center, chord lane, bass/sub rhythm, lead or vocal-chop lane
- sound design: risers, impacts, noise, vocal chops, sample treatment, bass layer, supersaw/lead texture, FX transitions
- production moves: filtering, sidechain, compression, stereo width, reverb/delay throws, automation envelopes
- verification targets: what should be rendered and what the sound checker should verify next

## Output Rules

- Keep inferred items labeled as `inferred` in session summaries, recipe entries, or notes.
- If there is still more to do, record it in `TODO.md` or the Songlab iteration notes instead of marking the task done.
- Do not ask the user for missing details unless the choice would change the song's identity or contradict an explicit request.

## Standalone Tool

Use the standalone tool only when a raw `transcript_spec.json` already exists and you need to inspect or debug enrichment without initializing a full session:

```bash
python3 tools/fill_in_blanks.py --input-json songlab/projects/<project-id>/transcript_spec.json --output-json /tmp/enriched.json --output-md /tmp/fill.md
```

Use the output to decide what a reasonable producer would put in the missing slots.
