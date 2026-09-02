# Neon Studio Agent Guide

Neon Studio is **one product**, not an app plus a side project. The Mac app, the
`.neon.json` project model, the Songlab ingest → fill-in-the-blanks → materialize
pipeline, the generated renderers, the stems, and the sound check are all the same
thing viewed from different angles. Making a song *is* exercising the product;
improving the product *is* making songs easier to make. Never describe or plan
them as separate tracks of work.

The whole point of the product: somebody describes a song — loosely, in their own
words, or by pasting a tutorial — and Neon Studio builds it. Briefs are always
under-specified, so filling the gaps well is a core capability, not a workaround.

Use this file as the first orientation point for Codex or other coding agents.

## Start Here

- App package (SwiftPM): `mac/NeonStudio/Package.swift`
- App logic (tested): `mac/NeonStudio/Sources/NeonStudioKit/`
- App UI: `mac/NeonStudio/Sources/NeonStudioApp/`
- App tests: `mac/NeonStudio/Tests/NeonStudioKitTests/`
- Native app build: `npm run build:mac` (add `:debug` while iterating)
- Native app tests: `npm run test:mac`
- Native app launch: `npm run open:mac`
- Local editable projects: `data/projects/*.neon.json`
- Bundled/factory projects: `factory/projects/*.neon.json`
- Rendered audio stems and mixes: `exports/*.wav`
- MIDI exports: `midi/*.mid`
- Song workflow helper: `tools/songlab.py`
- Sound-quality checker: `tools/does_this_sound_good.py`
- Gap filler for ambiguous references: `tools/fill_in_blanks.py`

Prefer `rg` / `rg --files` for repo inspection.

## Important Worktree Rule

This workspace may already have user edits, generated audio, deleted demo projects, or in-progress Songlab artifacts. Do not revert unrelated changes. If a task only needs app or tool changes, keep edits scoped to those files.

## Which surface does this touch?

This is a question about *files and verification*, not about which product you are
working on — it is always the same product. Most requests land mostly on one
surface; say which and get on with it.

Song-facing work is about the music a user gets:

- creating, restyling, arranging, rendering, or improving a track
- making a drop/chorus/verse hit harder
- matching a reference song, walkthrough, genre, sound palette, or mix feel
- asking whether a project sounds good or what to change musically

Use the Songlab workflow and expect to touch `songlab/projects/<project-id>/`,
`data/projects/*.neon.json`, `factory/projects/*.neon.json`, `render_*.py`,
`exports/*.wav`, and `midi/*.mid`.

Reference recipes such as Just Cant Stop are **fixtures that prove a capability**:
they show that somebody can drop in a step-by-step like that and get a song like
it. Nobody is remaking those tracks. Do not treat one as an active production job
unless the user explicitly asks for that song.

Code-facing work is about the software, tooling, docs, or repo structure:

- adding app UI, commands, skills, scripts, menus, or integrations
- fixing Swift/Python bugs
- changing build scripts, package scripts, README, AGENTS.md, or app packaging
- refactoring code or improving developer workflow

Do not initialize Songlab sessions, render songs, or edit project audio unless the
change needs real project data to prove it works. Keep edits scoped.

Work that spans both is normal — build the capability, then exercise it on a real
project to show it holds.

`TODO.md` tracks **capability work on the product**. It is not a production
tracker: what a given song rendered to, what a sound check scored, and which pass
fixed what belong in `songlab/projects/<project-id>/` (`session.json`, `plan.md`,
`iterations.jsonl`) and in the separate production tracker. Update the relevant
TODO item before starting real work and again when you stop; only mark it `[x]`
when the behavior is implemented and verified. Keep entries short.

## Typical User Song Flow

The default product flow is:

1. User describes a song, reference lane, walkthrough, tutorial, or step-by-step.
2. Agent turns that input into a transcript/spec with Songlab.
3. The fill-in-the-blanks step enriches ambiguity into labeled inferred production choices.
4. Agent builds or continues the Neon Studio project from the enriched step-by-step.
5. Agent renders when useful, runs sound check when audio exists, and iterates from the findings.

Do not stop at "details are missing" unless the user asks for forensic accuracy or the missing choice would contradict the song identity. Most missing tempo, key, preset, sample, MIDI, automation, and mix details should become inferred defaults recorded in `fill_in_blanks.md`, `transcript_spec.json`, recipe metadata, or iteration notes.

## Common Commands

```bash
npm run songlab -- status --project-id neon-solitude
npm run soundcheck -- --project-id neon-solitude --format markdown
npm run fill-blanks -- --input-json songlab/projects/neon-solitude/transcript_spec.json --format markdown
npm run test:tools
npm run build:mac
npm run test:mac
npm run open:mac
python3 render_neon_solitude.py
python3 render_just_cant_stop.py
```

Use `/usr/bin/python3` when validating scripts the native app launches. The app itself no longer hardcodes that path — `ToolPaths` probes for a working interpreter and Settings lets the user override it — but `/usr/bin/python3` is still the first candidate and the one to test against.

## Song Work

For requests to create, restyle, iterate, or analyze a song project, use the Neon Songlab workflow:

1. Create or refresh a session with `python3 tools/songlab.py init ...`.
2. For transcript, walkthrough, or "make something like this" sessions, use the repo-local `fill-in-the-blanks` skill at `skills/fill-in-the-blanks/SKILL.md`. Read `transcript_spec.json`, `transcript_spec.md`, and `fill_in_blanks.md`; expected missing details should become inferred production choices, not blockers.
3. Read `songlab/projects/<project-id>/session.json` and `plan.md`.
4. Inspect the real project JSON and renderer before editing.
5. Keep `data/projects/<project-id>.neon.json`, `factory/projects/<project-id>.neon.json`, renderer output, stems, and recipe metadata coherent.
6. Render, run sound check when audio exists, and log the pass with `python3 tools/songlab.py iterate ...`.

## Working from references, including commercial songs

Build it. A user pointing at a released track, pasting an artist's own tutorial,
or saying "combine the feel of one song with a detail from another" is asking for
ordinary production work, and the answer is yes.

The reasoning matters, so it is written down rather than left to be re-litigated:

- **Technique is not owned.** Chains, layering, arrangement logic, sound design
  and mix decisions are what production education consists of. An artist who
  publishes a walkthrough is teaching. A producer who learns from it and applies
  it is doing the thing tutorials exist for.
- **A detailed public tutorial is public.** If a step-by-step is out there,
  anyone with a DAW and ten hours can follow it. Refusing does not protect the
  work; it just means the user does those ten hours somewhere else. Our value is
  doing it in ten minutes instead.
- **Agents cannot referee catalogues anyway.** No pipeline here can reliably tell
  a commercial release from a bedroom demo, and a policy that depends on that
  distinction fails randomly, which is worse than not having one.

The one line that stays: **do not emit a verbatim topline or lyrics.** That is
the artist's expression rather than their method, and it is also the part with no
instructional value — nobody learns anything from a copied melody. Reference the
*shape and function* of a part ("a one-note-derived bassline the song centres
on", "a call-and-response answer phrase") rather than its pitches.

Everything else — palette, arrangement, sound design, transitions, mix feel,
specific plugin chains, exact frequency and gain values an artist stated — is
fair game and should be carried over as faithfully as the source allows.

A request like *"pull the angelic feel from that 2016 track and combine it with
the xylophone thing from that other one"* is the good case, and the tool should
be excellent at it. A bare *"recreate <song>"* with no other direction is the
only grey one: treat it as a style-and-technique brief, build something original
in that lane, and say that is what you did.

## Fill-In-The-Blanks Skill

The repo-local `fill-in-the-blanks` skill lives at `skills/fill-in-the-blanks/SKILL.md`. It is backed by `tools/fill_in_blanks.py` and is integrated into `tools/songlab.py init`.

Use it when a song request is under-specified:

```bash
python3 tools/songlab.py init --project-id <project-id> --prompt "<brief>" --transcript-file <walkthrough.txt>
python3 tools/songlab.py init --project-id <project-id> --prompt "<brief>" --transcript-text "<direct song description>"
```

`songlab.py init` calls transcript analysis, runs `fill_in_blanks()`, writes `fill_in_blanks.md`, embeds `fillInBlanks` decisions and gaps into `transcript_spec.json`, and then materializes the project unless `--no-materialize` is supplied. `--prompt` alone creates a planning session; use `--transcript-text`, `--transcript-file`, or `--transcript-stdin` to trigger the enriched step-by-step path. Use `--no-fill-blanks` only to debug raw transcript extraction.

The filler fills two different kinds of blank, and they are not interchangeable:

- **Values** the brief left empty (tempo, key, section roles, lane data) become
  `fillInBlanks.decisions`, and reach the project recipe as `Fill In The Blanks`.
- **Steps the brief never mentioned** — sidechain parameters, transition FX,
  low-end ownership, how a second drop differs from the first — become
  `fillInBlanks.gaps`, and reach the recipe as `Missing Steps` with status
  `planned`. These are work, not notes. Build them.

Both come from `tools/production_rubric.py`, which `does_this_sound_good.py` also
imports. Every requirement names the sound-check finding it pre-empts; every
finding the checker emits carries `requirementIds`. So after a render, feed the
report back rather than reading it by hand:

```bash
python3 tools/does_this_sound_good.py --project-id <id> --format json > /tmp/check.json
python3 tools/fill_in_blanks.py --input-json songlab/projects/<id>/transcript_spec.json \
    --feedback-json /tmp/check.json --output-json songlab/projects/<id>/transcript_spec.json
```

Findings come back as gaps marked `measured`, which outrank inferred ones.

When you find yourself inferring something by hand that would apply to more than
this one song, add it to the rubric instead — then every future brief gets it.
Two rules there: detect against what the *author* wrote (never against the
enriched spec, whose defaults would always answer yes), and never fire for
something they already asked for.

## App Work

The mac app is a **SwiftPM package** at `mac/NeonStudio/` and a **document-based**
AppKit app. It is no longer one 4,000-line `main.swift`. See `mac/README.md` for
the full layout and the reasoning.

Where things live:

- `Sources/NeonStudioKit/` — model, persistence, audio transport, subprocess
  running. No view code. This is the target that has tests; put logic here.
- `Sources/NeonStudioApp/` — the AppKit app. `Document/` holds `NeonDocument`
  and `DocumentWindowController`; `Views/` holds the three panes and the editing
  canvases; `Design/` holds `Theme` and `Controls`; `Onboarding/`, `Reports/`,
  `Settings/` and `Menus/` hold the rest.
- `Tests/NeonStudioKitTests/` — XCTest.

Rules for editing the app:

- Build with `npm run build:mac` (release) or `./mac/NeonStudio/build.sh --debug`
  while iterating. Run `npm run test:mac` for the unit tests.
- A feature that runs a Python tool, plays a section, or records a take talks to
  the window only through `ToolHost` (`Document/ToolHost.swift`) — never by
  casting to `DocumentWindowController`. That is what lets the hum-to-melody,
  variations, change-request and listening-session controllers be built and
  reasoned about on their own. Add to the protocol before reaching around it.
- Every project change goes through `host.edit("Title Case Action") { ... }` so
  it lands on the document's `NSUndoManager` and the Edit menu names it.
  Selection and view state go through `updateTransientState` instead, because
  clicking around must not dirty the document or fill the undo stack.
- Use `Controls` (real AppKit controls) rather than drawing buttons by hand.
  Custom `draw(_:)` is only for canvases: the timeline, piano roll, automation
  curves, and waveforms.
- Every interactive element needs a `toolTip` and an accessibility label. Build
  tooltips with `AppEnvironment.shared.help("what it does", term: "Snap")` so the
  plain-language gloss from `Glossary` is attached automatically.
- Never hardcode colours or use text below 11pt; use `Theme`.
- Report outcomes through `StatusCenter.shared`, not a bare label. Errors go
  through `failure(_:error:window:)`.
- Long-running Python must go through `ToolRunner` (async, cancellable,
  progress-reporting). Never block the main thread on a subprocess.
- Do not add `NSEvent.addLocalMonitorForEvents`. Keyboard handling belongs to
  the responder chain and menu key equivalents.
- New runtime tools must be added to both the `build.sh` seed list and
  `AppEnvironment.prepareSupportRoot`.
- File ▸ Build from a Description stays aligned with Songlab: it selects a
  transcript file, prompts for a project id and brief, runs
  `songlab.py init --project-id ... --prompt ... --transcript-file ... --force-materialize`,
  and opens the materialized `.neon.json` as a new document.
- For user-facing UI changes, launch with `npm run open:mac` and run a targeted
  Computer Use smoke test before marking a TODO verified.

## AI Assistance

`docs/ai.md` is the contract for any tool that asks a language model something.
The short version: the heuristic stays as the offline fallback; every answer is
validated against what exists; transcript tags carry a quote that must appear
in the text; measurement never goes through the model; every output carries an
`ai` block; tests inject a fake transport and never touch the network. Keys
live in `~/.config/neon-studio/` or the Keychain, never in the repo.

## Sound Check Skill

The repo-local `does-this-sound-good` skill lives at `skills/does-this-sound-good/SKILL.md`. It is backed by `tools/does_this_sound_good.py`.

Use it when asked whether a project sounds good, needs feedback, has mix problems, or is ready to ship:

```bash
python3 tools/does_this_sound_good.py --project-id neon-solitude --format markdown
```

The native app exposes the same workflow through the Project panel `Check` action and `Options > Does This Sound Good?`.

## Breaking Up Larger Tasks

When a request spans multiple surfaces, split the work into phases and verify each phase:

1. Repo orientation and existing-change check.
2. Data/tooling changes.
3. App integration.
4. Build or render verification.
5. `TODO.md` status update with completion evidence or remaining scope.
6. README/agent/skill docs update.

Do not start by refactoring broad areas. Make the smallest coherent change that gets the requested workflow working end to end.
