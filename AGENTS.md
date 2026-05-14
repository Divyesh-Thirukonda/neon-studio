# Neon Studio Agent Guide

This repo is a native macOS Neon Studio workspace with Python tools for song generation, transcript ingestion, rendering, and production-quality checks. Use this file as the first orientation point for Codex or other coding agents.

Product framing: the native app, `.neon.json` project model, Songlab transcript/materialization tools, renderers, stems, skills, and sound checks are one Neon Studio product surface. The song/developer distinction below is only for choosing the right files and verification path; do not treat app work and project-generation work as unrelated products.

## Start Here

- Primary app source: `mac/NeonStudio/Sources/main.swift`
- Native app build: `npm run build:mac`
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

## Request Routing

Separate song-production requests from developer requests before editing.

Song requests are about the music itself:

- creating, restyling, arranging, rendering, or improving a track
- making a drop/chorus/verse hit harder
- matching a reference song, walkthrough, genre, sound palette, or mix feel
- asking whether a project sounds good or what to change musically

For song requests, use the Songlab workflow and expect to touch project/session artifacts such as `songlab/projects/<project-id>/`, `data/projects/*.neon.json`, `factory/projects/*.neon.json`, `render_*.py`, `exports/*.wav`, and `midi/*.mid`.

Reference recipes such as Just Cant Stop are fixtures for proving future similar-song generation can be built. They are not active remakes unless the user explicitly asks to produce that song.

Developer requests are about the software, tooling, docs, or repo structure:

- adding app UI, commands, skills, scripts, menus, or integrations
- fixing Swift/Python bugs
- changing build scripts, package scripts, README, AGENTS.md, or app packaging
- refactoring code or improving developer workflow

For developer requests, do not initialize Songlab sessions, render songs, or edit project audio/data unless the request explicitly needs it for verification. Keep changes scoped to code, docs, and tooling.

Hybrid requests should be split into phases. Example: first add the app/tooling feature, then run a targeted song check only if that feature needs real project data to prove it works.

When working through `TODO.md`, update the relevant item before starting meaningful implementation and again when stopping or finishing it. Do not mark a TODO done unless the requested behavior is fully implemented and verified; append remaining work, blockers, or follow-up scope directly under that item.

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
npm run build:mac
npm run open:mac
python3 render_neon_solitude.py
python3 render_just_cant_stop.py
```

Use `/usr/bin/python3` when validating scripts that the native macOS app launches, because the app uses that interpreter path.

## Song Work

For requests to create, restyle, iterate, or analyze a song project, use the Neon Songlab workflow:

1. Create or refresh a session with `python3 tools/songlab.py init ...`.
2. For transcript, walkthrough, or "make something like this" sessions, use the repo-local `fill-in-the-blanks` skill at `skills/fill-in-the-blanks/SKILL.md`. Read `transcript_spec.json`, `transcript_spec.md`, and `fill_in_blanks.md`; expected missing details should become inferred production choices, not blockers.
3. Read `songlab/projects/<project-id>/session.json` and `plan.md`.
4. Inspect the real project JSON and renderer before editing.
5. Keep `data/projects/<project-id>.neon.json`, `factory/projects/<project-id>.neon.json`, renderer output, stems, and recipe metadata coherent.
6. Render, run sound check when audio exists, and log the pass with `python3 tools/songlab.py iterate ...`.

Treat named references and walkthroughs as valid production references for palette, arrangement, sound design, transitions, and mix feel. Do not copy exact lyrics or exact toplines as the implementation strategy.

## Fill-In-The-Blanks Skill

The repo-local `fill-in-the-blanks` skill lives at `skills/fill-in-the-blanks/SKILL.md`. It is backed by `tools/fill_in_blanks.py` and is integrated into `tools/songlab.py init`.

Use it when a song request is under-specified:

```bash
python3 tools/songlab.py init --project-id <project-id> --prompt "<brief>" --transcript-file <walkthrough.txt>
python3 tools/songlab.py init --project-id <project-id> --prompt "<brief>" --transcript-text "<direct song description>"
```

`songlab.py init` calls transcript analysis, runs `fill_in_blanks()`, writes `fill_in_blanks.md`, embeds `fillInBlanks` decisions into `transcript_spec.json`, and then materializes the project unless `--no-materialize` is supplied. `--prompt` alone creates a planning session; use `--transcript-text`, `--transcript-file`, or `--transcript-stdin` to trigger the enriched step-by-step path. Use `--no-fill-blanks` only to debug raw transcript extraction.

## App Work

The mac app is a single-file AppKit app. Keep UI edits consistent with the existing compact DAW layout:

- Use existing view/panel/button helpers where possible.
- Keep project actions in the right Project panel or app menus.
- If new runtime tools are needed by the built app, include them in `mac/NeonStudio/build.sh` seed copying and `AppDelegate.prepareSupportRoot()`.
- The Project panel `Transcript` action must stay aligned with Songlab: it selects a transcript file, prompts for project id/prompt/overwrite, runs `/usr/bin/python3 tools/songlab.py init --project-id ... --prompt ... --transcript-file ... --force-materialize`, reloads projects, and opens the materialized `.neon.json`.
- Rebuild with `npm run build:mac` after Swift changes.
- For user-facing native UI changes, launch with `npm run open:mac` and run a targeted Computer Use smoke test before marking the TODO verified.

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
