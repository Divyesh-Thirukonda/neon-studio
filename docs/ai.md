# AI in the tools: where a model helps, and the rules it works under

Neon Studio's pipeline measures sound and follows a script. Both of those are
deterministic and stay that way. What a language model is good at is the
*language and judgement* in between: reading a rambling YouTube tutorial,
turning "make the drop hit harder" into edits, deciding that a song described
as "lo-fi, rainy, slow" should not default to 142 BPM, and writing the "why"
next to every inferred step so a person can disagree with it.

This page is the contract. Every tool that talks to a model follows it.

## Turning it on

- Put a Gemini key in `~/.config/neon-studio/gemini_api_key` (or export
  `GEMINI_API_KEY`). An Anthropic key works the same way
  (`anthropic_api_key` / `ANTHROPIC_API_KEY`).
- In the Mac app: Settings ▸ AI assistance. The key lives in the Keychain and
  is handed to the tools as an environment variable; it is never written to a
  project file, a spec, or a log.
- `NEON_AI=off` turns it off everywhere; every tool also takes `--ai off`.
- Nothing needs a key to work. With no key, every tool does exactly what it did
  before, and says so in its output.

## The adapter: `tools/llm.py`

```python
from llm import Assist, add_ai_argument, assist_from_args

add_ai_argument(parser)            # --ai auto|off
assist = assist_from_args(args)    # or Assist(enabled=...) / Assist(client=fake)

answer = assist.ask(task_text, system=ROLE_TEXT, schema={...}, expect=dict)
# answer is the model's JSON, or None. assist.note says why it was None.
payload["ai"] = assist.report()    # {"used": bool, "provider", "model", "note"}
```

- Stdlib only, Python 3.9. Gemini via REST (`gemini-flash-latest` by default,
  the alias Google keeps pointed at the current Flash; `NEON_AI_MODEL` overrides
  it; thinking kept low unless a caller asks for `thinking="high"`).
- Answers are cached on disk by (provider, model, prompt), so re-running a tool
  on the same input is repeatable and free. `NEON_AI_CACHE=off` disables it.
- `Unavailable` never escapes a tool: `Assist.ask` returns None and records the
  reason.

## Rules for every integration

1. **The heuristic is the fallback, not the exception.** The existing code path
   runs whenever the model is off, unreachable, slow, or answers something that
   does not validate. A tool never fails because the model did.
2. **Validate everything the model returns against what exists.** Section
   types come from the tool's own enum; track ids and section ids must be in the
   project; techniques come from the known list; numbers are clamped to the
   ranges the code already uses. Anything else is dropped, and the drop is
   noted.
3. **Evidence or it did not happen.** When the model tags something in a
   transcript (a plugin, a technique, a tempo), it returns the quote it read it
   in, and the quote must appear in the text. That is what stops "Marshmello
   uses Serum" from tagging Serum on every section.
4. **Measurement never goes through the model.** Onsets, RMS, duck depth, crest
   factor, fidelity scores, rendering: unchanged. The model may write the prose
   around a measurement, never the measurement.
5. **Say what happened.** Every tool's JSON carries an `ai` block. Decisions the
   model made carry `"source": "model"` (and the reason it gave); decisions the
   heuristic made keep their existing source. The app shows "via Gemini" or
   "offline rules" in the status line.
6. **Keep the model's context small and structured.** Send segments with
   indices rather than a whole transcript when the answer refers back to
   segments; send track lists as `{id, name, kind, roles}`; cap any text at
   ~24k characters per call and chunk beyond that.
7. **Tests never touch the network.** Inject `llm.Client(transport=fake, ...)`
   through `Assist(client=...)` or a module-level factory; run every existing
   test with the model off (unset keys, `NEON_CONFIG_DIR=/nonexistent`) so the
   deterministic path stays covered.
8. **One call per question, batched.** Per-section questions go out as one call
   over all sections (or chunks of ~25), never one call per section.
9. **The app and MCP are thin.** They pass the environment through and read
   the `ai` block; the judgement lives in the tools.

## Where it is used

| Tool | Model does | Heuristic keeps doing |
|---|---|---|
| `ingest_transcript.py` | segment a raw transcript into sections; tag roles/plugins/techniques with quotes; tempo, key, title, genre; cross-section reuse; drum/lane patterns from prose; notes and the derived prompt | timecode splitting, the compact lane DSL, everything when off |
| `fill_in_blanks.py` / `production_rubric.py` | style lane and defaults for *this* song; naming unplaced sections; completing the arrangement with song-specific summaries; judging which requirements the author already covered (with quotes); song-specific step and why text | bar arithmetic, structural repair passes, requirement ids and areas |
| `project_materializer.py` | tempo/key/groove; a chord progression per section; drum patterns and lane rhythms from the description; track names and instruments; an arrangement when the spec has none; automation envelopes | the renderer, every technique implementation, the gain ladder |
| `describe_change.py` | the whole request into normalised clauses (intent, track, section, size, explicit amounts); recipes for compound asks; clarifying questions for what it cannot place; a why per edit | applying edits; the grammar as fallback |
| `listening_session.py` | section-specific questions; free-text notes into requirement ids with the person's words kept; a why per step | the question bank and answer map as fallback |
| `daw_agent.py` | choosing and ordering tactics for the project and feedback; tactic parameters within the existing schema; the summary and why | applying tactics |
| `does_this_sound_good.py` / `transcript_fidelity.py` | the plain-English verdict, summary, ranked next actions; fidelity claim extraction from the raw transcript; actionable fixes per missed claim | every measurement and score |
| `songlab.py iterate --ai` | the loop: read the sound check and fidelity report, propose the next spec edits or change requests, apply, re-render, re-check, stop when nothing improves | rendering and checking |

## Cost and latency

A raw tutorial transcript costs one or two calls at ingest; an app action
(Ask for a Change, Listen With Me) costs one. Cached answers cost nothing.
`gemini-flash-latest` with thinking low answers a structured question in one
to three seconds; with thinking high, planning calls take longer and are used only in the
iterate loop.
