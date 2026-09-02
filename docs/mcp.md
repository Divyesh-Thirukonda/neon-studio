# Using Neon Studio from Cursor, Claude Code, or any MCP client

`tools/mcp_server.py` exposes the whole Songlab pipeline over MCP, so somebody
can build a song from inside the editor they already have open — paste a
tutorial, get a project, render it, check it, act on the check.

It speaks newline-delimited JSON-RPC 2.0 over stdin/stdout, depends on nothing
outside the Python standard library, and calls exactly the same functions the
CLI and the Mac app call. There is no second implementation, so behaviour cannot
drift between surfaces.

## Wiring it up

### Cursor

`~/.cursor/mcp.json`, or `.cursor/mcp.json` in a project:

```json
{
  "mcpServers": {
    "songlab": {
      "command": "/usr/bin/python3",
      "args": ["/absolute/path/to/summer/tools/mcp_server.py"]
    }
  }
}
```

### Claude Code

```bash
claude mcp add songlab -- /usr/bin/python3 /absolute/path/to/summer/tools/mcp_server.py
```

### Anything else

Any MCP client that can launch a stdio server works. Point it at
`/usr/bin/python3 tools/mcp_server.py` with the repository as the working
directory. Paths inside the server resolve relative to the repository root, so
it does not matter where the client is launched from.

### Check it works

```bash
python3 tools/mcp_server.py --self-test
```

That exercises the handshake, the tool list, an unknown-tool error, and a real
tool call without needing a client attached. `python3 -m unittest
tools/test_mcp_server.py` covers the AI plumbing with no network.

### Optional: let the tools use a language model

Nothing needs a model. With one, the tools read descriptions and change
requests with it and write the prose in their reports; every measurement stays
deterministic (see [`docs/ai.md`](ai.md)). Every script the server launches
inherits the server's own environment, whole - nothing is filtered or forwarded
by name - and `tools/llm.py` reads `GEMINI_API_KEY`, `NEON_AI`, `NEON_AI_MODEL`
and `NEON_CONFIG_DIR` from there. So put them in the client's `env` block:

```json
{
  "mcpServers": {
    "songlab": {
      "command": "/usr/bin/python3",
      "args": ["/absolute/path/to/summer/tools/mcp_server.py"],
      "env": {
        "GEMINI_API_KEY": "...",
        "NEON_AI_MODEL": "gemini-flash-latest"
      }
    }
  }
}
```

A key in `~/.config/neon-studio/gemini_api_key` works too, with no `env`
block. `NEON_AI=off` in the `env` block turns the model off for every call.

Per call, every model-capable tool takes an optional `ai` boolean (default
`true`); `ai=false` forces the built-in rules for that one call — the only
thing the server changes is to set `NEON_AI=off` in that one script's
environment; it never edits the command line, so scripts with subcommands
behave the same. Every result, whichever way it went, ends with a line taken
from the tool's own `ai` block saying which path answered — `(via
gemini-flash-latest)` or `(offline rules - no API key …)` — so an agent can
tell the user why a fallback happened, including a silent one (no key, quota)
with `ai=true`. `songlab_ai_status` says what the next call would do.

## The tools

| Tool | What it does |
| --- | --- |
| `songlab_build_song` | A description in, a buildable project out. Anything from two sentences to a full tutorial transcript. 10–60s. |
| `songlab_render` | Render the project to stems and a full mix. 30–120s. |
| `songlab_sound_check` | Score the render, say what is wrong, tag each problem with the requirements that would have prevented it. |
| `songlab_apply_sound_check` | Run the check and fold its findings back into the plan as measured production steps. |
| `songlab_suggest_improvements` | Propose production tactics; `apply=true` writes them. |
| `songlab_list_projects` | Every project with tempo and track count. |
| `songlab_inspect_project` | Tracks, clips, audio status, and the steps still outstanding. |
| `songlab_production_rubric` | The requirements a song is checked against, and why each matters. |
| `songlab_fidelity` | Does the song match what the description *said*? Tempo, key, section order, every named technique (with audio evidence), explicit numbers. |
| `songlab_hum_to_melody` | A WAV of someone humming → piano-roll notes, snapped to the project's grid and key. `insert=true` writes them to a track. |
| `songlab_variations` | Three musically distinct alternatives for one track in one section, each with a short preview WAV. |
| `songlab_use_variation` | Adopt one alternative — only that track changes. |
| `songlab_describe_change` | "Make the drop hit harder" → concrete edits. Honest when it doesn't understand. |
| `songlab_listening_questions` | The human sound check, part one: plain questions per section, with the bars to play. |
| `songlab_listening_apply` | Part two: the user's answers become production steps marked as human evidence. |
| `songlab_ai_status` | Whether the tools would use a language model right now (provider, model), or why not. No network call. |

Tools that take `ai` (default `true`): `songlab_build_song`, `songlab_sound_check`,
`songlab_apply_sound_check`, `songlab_suggest_improvements`, `songlab_fidelity`,
`songlab_describe_change`, `songlab_listening_questions`, `songlab_listening_apply`.
Rendering, humming, and alternatives are measurement and synthesis; they never
touch a model and take no `ai` parameter.

## The loop it is designed for

```
songlab_build_song          paste the description or tutorial
songlab_render              make audio
songlab_fidelity            does it match what was said?
songlab_sound_check         does it sound good, to the software?
songlab_listening_questions does it sound good, to the person?  (play each section, ask)
songlab_listening_apply     their answers become steps
songlab_apply_sound_check   the measurements become steps
                            ... edit, re-render, check again
```

Two ways the person edits without touching a control:

```
songlab_describe_change     "make the drop hit harder" — typed, in their own words
songlab_hum_to_melody       a WAV of them humming — sung, literally
songlab_variations          "here are three ways this could go" — chosen, by listening
```

The fourth step is the one worth knowing about. Every problem the sound check
reports carries the ids of the production requirements that would have prevented
it, so the fix does not have to be re-derived from a prose report. Folding the
report back in produces steps marked `measured`, carrying the checker's own
numbers as evidence, which outrank anything that was merely inferred.

## What a session looks like

> **User:** Here's a tutorial for a track I like — build me something in that
> style. *(pastes transcript)*

The agent calls `songlab_build_song`. It comes back with the arrangement it
extracted and a list of the production steps the tutorial never mentioned —
sidechain parameters, low-end ownership, transition FX — because a tutorial
always leaves those out.

> **User:** Render it and tell me how it sounds.

`songlab_render`, then `songlab_sound_check`. Say it scores 69 with a low-end
problem.

> **User:** Fix that.

`songlab_apply_sound_check` turns the measured finding into a specific step in
the project's recipe, with the measurement attached. The agent then edits the
renderer against that step rather than guessing.

## Notes

- **Long calls.** Building and rendering are synchronous and can take a minute.
  The tool descriptions say so, so a client can warn rather than appear hung.
- **Everything is local by default.** The server runs local Python against
  local files and makes no network call of its own. The one exception is opt-in:
  with a Gemini key in the client's `env` block (or in
  `~/.config/neon-studio/gemini_api_key`), the tools may ask the model; without
  one they never do, and say so in every result.
- **`project_id` is a slug.** It becomes the filename, so it is normalised to
  lowercase alphanumerics and dashes.
