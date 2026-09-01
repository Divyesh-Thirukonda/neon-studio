# Neon Studio TODO

Neon Studio is **one product**: the Mac app, the `.neon.json` project model, the
Songlab ingest → fill-in-the-blanks → materialize pipeline, the generated
renderers, the stems, and the sound check are all the same thing. App work and
song-generation work are not separate tracks — a change to either is a change to
Neon Studio.

**This file tracks capability work on the product.** It is not a production
tracker. Individual songs — what got rendered, what a sound check scored, which
iteration fixed what — live in `songlab/projects/<project-id>/` (`session.json`,
`plan.md`, `iterations.jsonl`) and in the separate production tracker. Do not log
song passes here.

Status key: `[ ]` not started · `[~]` in progress · `[x]` done · `[?]` blocked

Rule: update an item before starting real work on it and again when you stop.
Only mark `[x]` when the behavior is implemented and verified; otherwise record
what is left under the item. Keep entries short — the detail belongs in the code,
the commit, or the session artifacts.

## Open

- `[ ]` The generated renderer is audible but not balanced.
  - Every lane now renders real audio, including the vocal/pluck/sample lanes
    that used to emit one near-silent blip per section. But the starter mix is
    not gain-staged: drums peak near 0 dBFS while the melodic lanes sit 30 dB
    down. The renderer prints its own "refine the starter render bodies" note.
  - The `gain_ladder` requirement in the rubric already describes the fix; wire
    it into the generated renderer so the scaffold ships balanced.

- `[ ]` Grow the production rubric as blind spots show up.
  - `tools/production_rubric.py` has 34 requirements. When a generated song comes
    out wrong for a reason nothing in the rubric predicted, that is the signal to
    add one — the rubric is meant to accumulate what we learn.
  - Two rules: detect against what the author wrote, never the enriched spec; and
    never fire for something they already asked for.

## Capabilities that exist

Short list of what the product can already do, so nobody re-implements it.

- `[x]` Native Mac app: document-based (`NSDocument`, `.neon.json` opens from the
  Finder), SwiftPM package with a tested `NeonStudioKit` core, `AVAudioEngine`
  transport with a real playhead and working loop, note/step preview synthesis,
  async helper-tool execution, full menu bar, onboarding and plain-language help.
  See `mac/README.md`.
- `[x]` Songlab pipeline: transcript ingest → fill-in-the-blanks → project
  materialization → generated renderer → stems → sound check → iteration log.
- `[x]` Fill-in-the-blanks handles both kinds of blank: missing *values* (tempo,
  key, section flow, roles, lane data) become labelled inferred defaults, and
  missing *steps* nobody mentioned (sidechain parameters, transition FX, low-end
  ownership, hook recurrence, how a second drop differs) become planned recipe
  items. 34 requirements in `tools/production_rubric.py`, shared with the sound
  check so the filler pre-empts what the checker would flag, and a sound-check
  report can be fed straight back to turn measurements into targeted steps.
- `[x]` Sound check (`tools/does_this_sound_good.py`) scores a rendered project
  and returns strengths, issues and next actions, in the app and on the CLI.
- `[x]` DAW agent (`tools/daw_agent.py`) applies production tactics to a project
  and can be steered by the latest sound check.
- `[x]` Transcript-driven generation preserves precise cues — per-section lane
  events, transforms, drum blocks, automation envelopes, phrase reuse — through
  to the generated renderer. See the transcript section of `README.md`.
- `[x]` The parser recovers a real arrangement from a rambling walkthrough:
  sections are reordered into playback order rather than the order they were
  discussed, every mention of a part folds into one section, described-but-
  unplaced parts are classified instead of dropped, spans come from the
  transcript's own timecodes, and producer terms (808, stab, shaker, arp) map to
  buildable roles. A 53-minute video that produced 360 bars of verse/drop now
  produces an 8-section, 84-bar arrangement.
- `[x]` MCP server (`tools/mcp_server.py`, 8 tools) so Cursor, Claude Code and
  any other MCP client can drive the same pipeline. See `docs/mcp.md`.
- `[x]` Recording has a count-in (Transport ▸ Count-In, off/1/2/4 bars) and
  punch-in/out. The clicks, the backing track and the recorder are armed to one
  shared host time via `AVAudioRecorder.record(atTime:forDuration:)`, so the take
  lands on the intended bar. With Loop on, the loop range is the punch range.
- `[x]` True per-track metering: the engine taps every track's own mixer node, so
  a meter reads that track after its gain, pan, mute and solo rather than the
  master level scaled by the fader.

## Reference fixtures

These exist to prove a capability, not because anyone is making these songs.

- `songlab/projects/just-cant-stop/producer_step_by_step.md` — a detailed
  walkthrough of the kind a user might paste in. It is the test that "somebody
  drops in a step-by-step like this and Neon Studio can build a song like it"
  actually holds. Nobody is remaking that track; the fixture is the point.
  Exact source samples, preset values, MIDI and fader settings are *expected* to
  be missing from references like this — that is the fill-in-the-blanks step's
  job, not an open TODO.
