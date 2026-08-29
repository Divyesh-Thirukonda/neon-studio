# Neon Studio Native Workspace

Neon Studio is one product, not an app plus a side project. The native macOS app,
the `.neon.json` project model, the Songlab pipeline, the generated renderers, the
stems, and the sound check are the same thing viewed from different angles.

Somebody describes a song — loosely, in their own words, or by pasting a tutorial —
and Neon Studio builds it. Briefs are always under-specified, so filling the gaps
well is a core capability rather than a workaround.

The normal path is:

1. A user describes a song, reference lane, walkthrough, tutorial, or step-by-step.
2. Songlab turns that input into a transcript/spec.
3. The fill-in-the-blanks pass converts missing details into labeled inferred production choices.
4. The agent or app builds the Neon Studio project from the enriched step-by-step.
5. The project is rendered, checked, and iterated until it is actually usable.

## Primary App

Neon Studio is a native, document-based macOS app built as a SwiftPM package.
It opens `.neon.json` files the way any Mac app opens its documents — from the
Finder, from Open Recent, several at once — with real Save/Save As/Duplicate/
Revert, autosave-in-place, Versions, and per-document undo.

- App: `mac/build/Neon Studio.app`
- Package: `mac/NeonStudio/Package.swift`
- Logic (unit-tested): `mac/NeonStudio/Sources/NeonStudioKit/`
- UI: `mac/NeonStudio/Sources/NeonStudioApp/`
- Build: `npm run build:mac` — or `npm run build:mac:debug` while developing
- Test: `npm run test:mac`
- Launch: `npm run open:mac`

New to music software? The app opens on a welcome screen with an example song,
runs a short guided tour of the window, explains every music term in place, and
labels its controls in plain English. See `mac/README.md` for the architecture.

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

The middle step between a loose description and a buildable project. It does two
different jobs, and the second one matters more.

**Missing values.** The brief has a field and left it empty — no tempo, no key,
no roles on a section. Filled from the style lane's defaults, labelled inferred,
recorded in `fillInBlanks.decisions`.

**Missing steps.** The brief never raised the subject. Somebody writes "big
future bass drop with a catchy lead" and says nothing about sidechain, transition
FX, who owns the low end, or how the second drop differs from the first. Nobody
left a blank, because nobody thought of it. These come from a production rubric
and land in `fillInBlanks.gaps`, then in the project recipe under `Missing Steps`.

A four-sentence brief currently surfaces around 28 missing steps; a detailed
walkthrough surfaces around 6. It fires in proportion to how under-specified the
input is, and it never fires for something the author actually asked for — saying
"a second drop that's bigger" is enough to suppress the variation requirement.

### The rubric is shared with the sound check

`tools/production_rubric.py` is the vocabulary `fill_in_blanks.py` and
`does_this_sound_good.py` have in common. Every requirement names the sound-check
finding it pre-empts, and every finding the checker emits carries the ids of the
requirements that would have prevented it. Every dimension the checker can report
maps to at least one step, which is what makes the loop closed rather than
decorative:

- **Forwards** — before rendering, the filler asks what the checker would
  complain about and adds those steps up front.
- **Backwards** — after rendering, findings come back as steps marked `measured`,
  carrying the checker's own numbers as evidence. Measured beats inferred.

```bash
npm run soundcheck -- --project-id <id> --format json > /tmp/check.json
npm run fill-blanks -- --input-json songlab/projects/<id>/transcript_spec.json \
    --feedback-json /tmp/check.json --output-json songlab/projects/<id>/transcript_spec.json
```

- Tools: `tools/fill_in_blanks.py`, `tools/production_rubric.py`
- Skill: `skills/fill-in-the-blanks/SKILL.md`
- Tests: `npm run test:tools`
- Session artifact: `songlab/projects/<project-id>/fill_in_blanks.md`
- Spec fields: `fillInBlanks.decisions` and `fillInBlanks.gaps`

Standalone inspection:

```bash
npm run fill-blanks -- --input-json songlab/projects/<project-id>/transcript_spec.json --format markdown
```

## Using it from Cursor or another coding agent

`tools/mcp_server.py` exposes the whole pipeline over MCP, so a user can build a
song from inside their editor: paste a tutorial, get a project, render it, check
it, act on the check. Eight tools, no dependencies beyond the standard library,
and it calls the same functions the CLI and the Mac app call.

```bash
npm run mcp:test          # verify the server without a client attached
```

Wiring for Cursor and Claude Code, the tool list, and the loop it is designed
for are in [`docs/mcp.md`](docs/mcp.md).

## Working from references

Neon Studio builds from references, including commercial songs. Technique is not
owned — chains, layering, arrangement and mix decisions are what production
tutorials teach — and a published step-by-step is already public. The point of
the tool is doing in ten minutes what would otherwise take ten hours in a DAW.

The one thing it will not do is emit a verbatim topline or lyrics, which is the
artist's expression rather than their method and teaches nobody anything. Melodic
references are carried as shape and function, not pitches.

`songlab/projects/just-cant-stop/` is the worked example: a producer's own
53-minute video breakdown, the raw transcript, and
[`producer_step_by_step.md`](songlab/projects/just-cant-stop/producer_step_by_step.md)
— a complete DAW-neutral production document generated from it, with every
plugin he named plus a generic substitute for each.

## Sound Check Workflow

- `python3 tools/does_this_sound_good.py --project-id neon-solitude --format markdown`
- `npm run soundcheck -- --project-id neon-solitude --format markdown`
- Native app: the Check My Mix toolbar button, or Tools > Check My Mix, analyzes the current project state and returns a score, blockers, and next actions in a report window you can copy or save.
- The Codex skill lives at `skills/does-this-sound-good/SKILL.md` and uses the same local checker.

## DAW Agent Workflow

The DAW Agent transfers source-DAW-inspired tactics into Neon Studio projects through a local retrieval catalog and deterministic project patcher. It can add recipe evidence, automation lanes, groove/fill clips, macro-chain effects, and piano-roll motif seeds without rewriting unrelated project data.

```bash
npm run daw-agent -- suggest --project-id neon-solitude --format markdown
npm run daw-agent -- apply --project-id neon-solitude --output /tmp/neon-agent.neon.json --format markdown
npm run daw-agent -- offline-eval --format markdown
npm run daw-agent -- retrieval-check --format markdown
```

For iterative work after a sound check, pass the sound-check JSON back into the agent:

```bash
npm run daw-agent -- apply --project-id neon-solitude --feedback-json /tmp/soundcheck.json --output /tmp/neon-agent.neon.json --format markdown
```

Native app: the Suggest Ideas toolbar button, or Tools > Suggest Ideas, applies the same path to the open project. If the session has a recent Check My Mix result, it steers retrieval before applying changes. Everything the agent changes lands as a single undo step, so one Cmd-Z reverts the whole run, and the result is shown in a scrollable, copyable report window.

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

File > Build from a Description uses the same Songlab path:

1. Choose a transcript text file (`.txt`, `.md`, `.srt` or `.vtt`).
2. Confirm the project name and a one-line brief.
3. The app runs `songlab.py init --project-id ... --prompt ... --transcript-file ... --force-materialize`
   in the background, streaming progress into the status bar and the Activity log.
   It can be cancelled, and the window stays responsive throughout.
4. The materialized `.neon.json` opens as a new document window.

The Python interpreter is discovered rather than hardcoded, and can be set under
Neon Studio > Settings > Audio & Tools when the automatic choice is wrong.

After native UI or runtime-tool changes, rebuild with `npm run build:mac`, run
`npm run test:mac`, launch with `npm run open:mac`, and run a targeted Computer
Use smoke test.

## Renderers

- `render_neon_solitude.py`
- `render_just_cant_stop.py`

## Current Projects

- `data/projects/neon-solitude.neon.json`
- `factory/projects/neon-solitude.neon.json`
- `factory/projects/just-cant-stop.neon.json`

## Reference Fixtures

`songlab/projects/just-cant-stop/producer_step_by_step.md` is a detailed walkthrough
of the kind a user might paste in. It exists to prove a capability: somebody drops
in a step-by-step like that and Neon Studio can build a song *like* it. Nobody is
remaking that track, and it is not an active production target.

References like this always omit the exact samples, preset values, MIDI and fader
settings. That is expected — filling those gaps is the fill-in-the-blanks step's
job, not a blocker and not an open task.
