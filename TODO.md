# Neon Studio Product TODO

Status key:

- `[ ]` Not started
- `[~]` In progress
- `[x]` Done
- `[?]` Blocked

Tracking rule: update the relevant TODO item before starting implementation and again when stopping or finishing. Only mark an item `[x]` when the behavior is fully implemented and verified; otherwise leave the current status and record remaining work or blockers under that item.

## Product Workflow

- `[x]` Align fill-in-the-blanks skill and agent guide with the typical user flow.
  - Scope: make the repo-local skill and `AGENTS.md` clearly route `user describes song -> transcript/spec enrichment -> agent builds project`, including how the native app calls Songlab and when sound check should feed the next iteration.
  - Done: expanded `skills/fill-in-the-blanks/SKILL.md` with agent routing, app flow, direct-description handling, inferred-output rules, and the sound-check iteration loop; refreshed the skill `agents/openai.yaml`; updated `AGENTS.md` and `README.md` to show that direct song descriptions should use transcript inputs, not prompt-only planning.
  - Found/fixed: corrected the skill's iteration-log command from `--notes` to the real `--note` flag after the smoke flow caught the mismatch.
  - Verified: `/usr/bin/python3 -m py_compile tools/fill_in_blanks.py tools/songlab.py tools/ingest_transcript.py tools/project_materializer.py tools/does_this_sound_good.py`; `/usr/bin/python3 tools/songlab.py init --help`; `npm run build:mac`; direct-description smoke with `--transcript-text` created `fill_in_blanks.md`, 16 inferred decisions, full section coverage, and `Fill In The Blanks` recipe entries; generated renderer produced stems; sound check returned actionable low-end/top-end follow-up; `tools/songlab.py iterate --note ...` logged the pass.
  - Cleanup: removed the temporary `flow-alignment-smoke` session/project/renderer/export artifacts created for verification.

- `[x]` Computer Use smoke test for app-integrated fill-in-the-blanks transcript flow.
  - Scope: launch the native app, run the Project `Transcript` action with a temporary ambiguous transcript, confirm Songlab materialization uses the fill-in-the-blanks middle step from the app runtime, and clean up app-support smoke artifacts.
  - Found/fixed: app support still had a stale `tools/songlab.py` because seed copying only filled missing files; `prepareSupportRoot()` now refreshes seeded `tools/` and `skills/` files while still preserving user data/projects.
  - Verified: `npm run build:mac`; launched the native app; Computer Use clicked Project `Transcript`, selected `/tmp/neon-fill-blanks-app-smoke.txt`, set Project ID to `app-fill-blanks-smoke`, materialized from the dialog, and the app opened `App Fill Blanks Smoke`.
  - Verified artifacts: app-support `fill_in_blanks.md` was created; `session.json` recorded fill-in-blanks analysis with 15 inferred decisions; `transcript_spec.json` had intro/build/drop/break/build/second-drop/outro coverage; the materialized `.neon.json` included `Fill In The Blanks` recipe entries; Recipe view showed `16/16 mapped`.
  - Cleanup: removed the temporary app-support smoke session/project/renderer/export paths and `/tmp/neon-fill-blanks-app-smoke.txt`.

- `[x]` Keep the native app and song-generation pipeline documented as one product surface.
  - Current framing: Neon Studio is the app plus its portable project model, Songlab ingestion/materialization, renderers, stems, sound checks, and fixture/reference recipes.
  - Done: cleaned this TODO so it no longer treats Just Cant Stop as an active song-production job separate from the app.
  - Verified: this file now tracks repo/product workflow tasks only.

- `[x]` Add a fill-in-the-blanks workflow between transcript ingest and project materialization.
  - Scope: when a user gives an incomplete song description or walkthrough, infer musically plausible missing arrangement, sound-design, automation, mix, and verification details before the agent builds the project.
  - Done: added `tools/fill_in_blanks.py`, integrated it into `tools/songlab.py init`, added `fill_in_blanks.md` session artifacts, embedded inferred recipe decisions into materialized projects, added the repo-local `fill-in-the-blanks` skill, documented the workflow, and taught generated renderers to sync rendered stems back into `.neon.json` assets for sound-check follow-up.
  - Verified: `/usr/bin/python3 -m py_compile tools/fill_in_blanks.py tools/songlab.py tools/ingest_transcript.py tools/project_materializer.py tools/does_this_sound_good.py`; ambiguous-transcript Songlab smoke test produced inferred intro/build/drop/break/build/second-drop/outro coverage; generated renderer produced stems; `/usr/bin/python3 tools/does_this_sound_good.py --project-id fill-blanks-smoke --format markdown` read those stems and returned actionable low-end/top-end feedback; `npm run fill-blanks -- --input-json /tmp/fill-blanks-raw.json --format markdown`; rerunning the filler on an enriched spec preserves existing decisions; `npm run build:mac`; bundled app seed contains the new tool and skill.
  - Cleanup: removed the temporary `fill-blanks-smoke` project/session/renderer/export artifacts created for verification.

## Completed Native App Work

- `[x]` Add real automation lane editing and storage to the native app.
  - Done: added `snapshot.automationLanes` with normalized editable breakpoint data, legacy automation-track migration, a `+ Lane` control in the native Automation + Scope panel, click-to-edit lane breakpoints, row enable/disable toggling, autosave persistence, and new-project initialization.
  - Verified: `npm run build:mac`; targeted Computer Use smoke test.

- `[x]` Add real sample trim, pitch, and stretch editing to the project model.
  - Done: added `track.sampleEdit` with trim start/end, pitch semitones, stretch ratio, reverse, normalize, and gain data; added a native Sample Edit dialog; updated Sample panel controls to write persisted project state.
  - Verified: `npm run build:mac`; targeted Computer Use smoke test.

- `[x]` Make the native app able to trigger Songlab transcript materialization from a project action.
  - Done: added a Project-panel `Transcript` action that selects a transcript text file, confirms project id/prompt/overwrite behavior, runs `/usr/bin/python3 tools/songlab.py init --project-id ... --prompt ... --transcript-file ... --force-materialize`, reloads projects, and opens the materialized `.neon.json`.
  - Verified: `npm run build:mac`; `/usr/bin/python3 tools/songlab.py init --help`; Computer Use selected a `.txt` transcript and reached the `Materialize Transcript` confirmation dialog.

## Reference Recipe Fixtures

- `[x]` Keep Just Cant Stop as a reference-recipe fixture for future similar-song generation, not as an active remake task.
  - Purpose: prove that a detailed step-by-step reference can be turned into an actionable Neon Studio recipe so future "make something like this" requests have enough arrangement, sound-design, and mix scaffolding.
  - Current artifact: `songlab/projects/just-cant-stop/producer_step_by_step.md`.
  - Note: exact original sample filenames, preset values, MIDI, automation curves, and fader settings are expected to be missing from many references; they should be handled by the fill-in-the-blanks workflow rather than tracked as open repo TODOs.
