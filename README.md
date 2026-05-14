# Neon Studio Native Workspace

Neon Studio is one product surface: the native macOS app, `.neon.json` project model, Songlab transcript/materialization tools, generated renderers, stems, skills, and sound checks all serve the same song-building workflow.

The normal path is:

1. A user describes a song, reference lane, walkthrough, tutorial, or step-by-step.
2. Songlab turns that input into a transcript/spec.
3. The fill-in-the-blanks pass converts missing details into labeled inferred production choices.
4. The agent or app builds the Neon Studio project from the enriched step-by-step.
5. The project is rendered, checked, and iterated until it is actually usable.

## Primary App

- `mac/build/Neon Studio.app`
- Source: `mac/NeonStudio/Sources/main.swift`
- Build: `npm run build:mac`
- Launch: `npm run open:mac`

## Core Project Data

- `data/projects/*.neon.json` for local editable project state
- `factory/projects/*.neon.json` for bundled starter/factory projects
- `exports/*.wav` for rendered stems and mixdowns
- `midi/*.mid` for arrangement exports

## Song Workflow

Use Songlab for song creation, restyling, transcript ingestion, reference recipes, and iteration:

```bash
python3 tools/songlab.py init --project-id <project-id> --prompt "<brief>"
python3 tools/songlab.py status --project-id <project-id>
python3 tools/songlab.py iterate --project-id <project-id> --note "<what changed>"
```

For an under-specified song idea or walkthrough, use a transcript input so the enriched step-by-step path runs:

```bash
python3 tools/songlab.py init --project-id <project-id> --prompt "<brief>" --transcript-text "<song description>"
python3 tools/songlab.py init --project-id <project-id> --prompt "<brief>" --transcript-file walkthrough.txt
```

`--prompt` alone creates a planning session. `--transcript-text`, `--transcript-file`, and `--transcript-stdin` trigger transcript analysis, fill-in-the-blanks, and project materialization.

## Fill In The Blanks

The fill-in-the-blanks workflow is the middle step between a loose user description and a buildable project. It preserves explicit details and labels inferred defaults for missing tempo, key, section flow, sound design, automation, mix targets, and verification needs.

- Tool: `tools/fill_in_blanks.py`
- Skill: `skills/fill-in-the-blanks/SKILL.md`
- Session artifact: `songlab/projects/<project-id>/fill_in_blanks.md`
- Spec field: `fillInBlanks` in `songlab/projects/<project-id>/transcript_spec.json`

Standalone inspection:

```bash
npm run fill-blanks -- --input-json songlab/projects/<project-id>/transcript_spec.json --format markdown
```

## Sound Check Workflow

- `python3 tools/does_this_sound_good.py --project-id neon-solitude --format markdown`
- `npm run soundcheck -- --project-id neon-solitude --format markdown`
- Native app: Project panel > Check or Options > Does This Sound Good? analyzes the current project state and returns a score, blockers, and next actions.
- The Codex skill lives at `skills/does-this-sound-good/SKILL.md` and uses the same local checker.

## Transcript Workflow

```bash
python3 tools/songlab.py init --project-id neon-solitude --prompt "brief" --transcript-file walkthrough.txt
python3 tools/songlab.py transcript --project-id neon-solitude --format markdown
```

Codex can also pass transcript text through stdin with `--transcript-stdin`.

Transcript init runs fill-in-the-blanks before materialization, so missing exact source details become labeled inferred defaults instead of blockers. The filler writes `songlab/projects/<project-id>/fill_in_blanks.md`, embeds `fillInBlanks` decisions in `transcript_spec.json`, and auto-materializes a real project unless `--no-materialize` is supplied.

- The transcript spec now stores normalized per-section `laneEvents` and `laneTransforms`, so exact cues like `lead: 1, 1.5, 2.5`, `lead: E5@1, G5@1.5, B5@2.5`, `lead: E5@1/0.5*0.85, G5@1.5!/0.25`, `lead: bar 1 E5@1 | bars 2-3 copy bar 1 transpose +12`, `lead: bars 1-2 copy intro lead bars 1 reverse`, `lead: bars 1-2 copy intro lead bars 1 skip 1.5`, `drums: bar 1 kick 1!,3*0.8 snare 2g,4! hats 1o*0.9,1.5!,2.5,3.5o`, `drums: bar 1 kick 1,3,4 mute 4`, `drums: bar 2 copy verse drums bars 1 double-time hats ride 1`, `automation: bars 1-8 filter 0.15->0.9`, `automation: bars 1-4 lead.filter 0.2->0.9 ease-in | bars 5-8 drums.volume 0.3->0.8 step | bars 9-12 hat.pan 0.1->0.8 ease-out`, `bass follows chords but skips beat 4`, or `copy drop 1 drums, add ride and double-time hats` survive into actual project generation
- Transcript-driven project generation now emits a section-aware `render_<project>.py` with per-section functions, transcript-conditioned harmony/rhythm defaults, explicit chord/beat/transposition parsing, compact note/drum event attributes (duration, gain, accent, ghost, open-hat, pan), explicit skip/mute/rest beat filtering, note-aware and bar-scoped lane-map reuse, cross-section lane copying, reverse/invert phrase transforms, drum-block reuse, parameter-specific automation-envelope reuse with curve control and target-lane routing, phrase-level reuse parsing (`same melody`, `filled in`, `same notes from the verse`), per-track role helpers, and executable starter stem/mix rendering for common lanes
- Manual project materialization refresh: `python3 tools/songlab.py materialize --project-id neon-solitude --force`

## Native App Transcript Flow

The Project panel `Transcript` action uses the same Songlab path:

1. Select a transcript text file.
2. Confirm project id, prompt, and overwrite behavior.
3. The app runs `/usr/bin/python3 tools/songlab.py init --project-id ... --prompt ... --transcript-file ... --force-materialize`.
4. The app reloads local projects and opens the materialized `.neon.json`.

After native UI or runtime-tool changes, rebuild with `npm run build:mac`, launch with `npm run open:mac`, and run a targeted Computer Use smoke test.

## Renderers

- `render_neon_solitude.py`
- `render_just_cant_stop.py`

## Current Projects

- `data/projects/neon-solitude.neon.json`
- `factory/projects/neon-solitude.neon.json`
- `factory/projects/just-cant-stop.neon.json`

## Reference Recipe Fixtures

- `songlab/projects/just-cant-stop/producer_step_by_step.md` is a reusable recipe fixture for proving that future "make something like this" requests can be translated into buildable Neon Studio projects. It is not an active remake target by default.
