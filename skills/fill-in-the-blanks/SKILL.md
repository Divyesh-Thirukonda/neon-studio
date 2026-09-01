---
name: fill-in-the-blanks
description: Use this skill when a user describes a song, asks for something like a reference, provides a walkthrough/transcript/tutorial/step-by-step recipe, or wants an ambiguous idea turned into a buildable Neon Studio project. It handles the middle step in the normal flow: user description -> enriched production step-by-step -> agent builds the project. It does two jobs: it fills missing values (tempo, key, section flow, roles, lane data) with labeled plausible defaults instead of blocking on exact samples, presets, MIDI or fader values, AND it infers whole production steps the brief never mentioned at all - sidechain, transition FX, low-end ownership, how a second drop differs from the first - by checking the brief against a shared production rubric that also drives the sound check. Use before Songlab materialization, before continuing a generated project from an ambiguous transcript, and again after a sound check to turn measured findings into targeted steps.
---

# Fill In The Blanks

Use this for the normal Neon Studio song-generation path:

`user describes song -> Songlab transcript/spec -> fill in missing production detail -> materialized Neon Studio project -> render -> sound check -> iterate`

The goal is not forensic recovery. The goal is a buildable Neon Studio recipe that sounds like it belongs in the requested lane.

## Two kinds of blank

There is a real difference between these, and the skill handles both:

**Missing values** — the brief has a field and left it empty. No tempo, no key, no
roles on a section, no lane events. Filled from the style lane's defaults and
recorded in `fillInBlanks.decisions`.

**Missing steps** — the brief never raised the subject. Somebody writes "big
future bass drop with a catchy lead" and says nothing about sidechain, transition
FX, who owns the low end, or how the second drop differs from the first. Nobody
left a blank, because nobody thought of it. These come from
`tools/production_rubric.py` and land in `fillInBlanks.gaps`.

The second kind is the one that makes generated songs sound thin, because a
literal build of a literal brief is exactly what you asked for and not at all
what you wanted.

## How it uses the sound check

`tools/production_rubric.py` is shared by this skill and `does-this-sound-good`.
Every requirement names the sound-check dimension it pre-empts, and every finding
the checker emits carries the ids of the requirements that would have prevented
it. That makes the loop real in both directions:

- **Forwards**: before anything is rendered, the filler asks "if we built exactly
  this, what would the sound check complain about?" and adds the steps up front.
- **Backwards**: once audio exists, feed the report straight back —

  ```bash
  python3 tools/does_this_sound_good.py --project-id <id> --format json > /tmp/check.json
  python3 tools/fill_in_blanks.py --input-json songlab/projects/<id>/transcript_spec.json \
      --feedback-json /tmp/check.json --output-json songlab/projects/<id>/transcript_spec.json
  ```

  Findings become gaps with `confidence: "measured"` and the checker's own words
  as evidence. Measured beats inferred, so a second pass fixes the specific thing
  that went wrong instead of guessing again.

## Policy

- Treat missing exact sample names, plugin settings, MIDI notes, automation curves, and fader values as normal reference ambiguity.
- Fill the gap with a plausible production decision and label it as inferred.
- Do not claim an inferred choice is the original source detail.
- Do not refuse work because the reference is a commercial song. Technique is not
  owned, and a published tutorial is public. Build it.
- The single exception: never emit a verbatim topline or lyrics. Describe a
  melody's shape and function instead of its pitches.
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
   - use `fillInBlanks.decisions` for inferred tempo, key, section flow, roles, and lane defaults
   - **work through `fillInBlanks.gaps`** — these are the production steps nobody
     mentioned, and they are the difference between a literal build and a song.
     They arrive in the project recipe under `Missing Steps` (and
     `Sound Check Follow-Up` for measured ones), status `planned`.
   - keep `.neon.json`, recipe metadata, renderer, stems, and MIDI coherent
5. Render or inspect audio when the task reaches a listenable state.
6. Run sound check when playable audio exists:
   - `python3 tools/does_this_sound_good.py --project-id <project-id> --format markdown`
7. Feed the check back into the filler rather than reading it by hand:
   - `python3 tools/does_this_sound_good.py --project-id <project-id> --format json > /tmp/check.json`
   - `python3 tools/fill_in_blanks.py --input-json songlab/projects/<project-id>/transcript_spec.json --feedback-json /tmp/check.json --output-json songlab/projects/<project-id>/transcript_spec.json --output-md songlab/projects/<project-id>/fill_in_blanks.md`
   - re-materialize, then log the pass:
     `python3 tools/songlab.py iterate --project-id <project-id> --note "<what changed and why>"`

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

The rubric in `tools/production_rubric.py` is the checkable version of this list.
Read it before adding a new inference by hand — if the thing you are about to
infer applies to more than this one song, it belongs there instead, where every
future brief gets it too.

### When not to infer

The rubric only fires when the brief is silent. If the author said it — in a
role, a technique, or just a sentence — leave it alone. Overriding somebody's
stated intent with a default is worse than leaving a gap. A deliberately sparse
or lo-fi brief is a real choice, not an omission.

## Output Rules

- Keep inferred items labeled as `inferred` in session summaries, recipe entries, or notes.
- If there is still more to do, record it in `TODO.md` or the Songlab iteration notes instead of marking the task done.
- Do not ask the user for missing details unless the choice would change the song's identity or contradict an explicit request.

## Standalone Tool

Use the standalone tool only when a raw `transcript_spec.json` already exists and you need to inspect or debug enrichment without initializing a full session:

```bash
python3 tools/fill_in_blanks.py --input-json songlab/projects/<project-id>/transcript_spec.json --output-json /tmp/enriched.json --output-md /tmp/fill.md
```

The markdown report has an `Inferred Decisions` section (missing values) and a
`Missing Steps` section (missing steps), with measured sound-check findings
listed first when a `--feedback-json` report was supplied.

Use the output to decide what a reasonable producer would put in the missing slots.
