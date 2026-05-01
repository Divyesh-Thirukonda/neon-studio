Neon Studio native workspace

Primary app:
- `mac/build/Neon Studio.app`
- source: `mac/NeonStudio/Sources/main.swift`

Core project data:
- `data/projects/*.neon.json` for local editable project state
- `factory/projects/*.neon.json` for bundled starter/factory projects
- `exports/*.wav` for rendered stems and mixdowns
- `midi/*.mid` for arrangement exports

Song workflow:
- `python3 tools/songlab.py ...`
- `npm run songlab -- ...`
- `npm run build:mac`
- `npm run open:mac`

Transcript workflow:
- `python3 tools/songlab.py init --project-id neon-solitude --transcript-file walkthrough.txt`
- `python3 tools/songlab.py transcript --project-id neon-solitude --format markdown`
- Codex can also pass transcript text through stdin with `--transcript-stdin`
- Transcript init auto-generates a first-pass project scaffold when no project exists yet
- The scaffold now also emits a section-aware `render_<project>.py` with per-section functions, transcript-conditioned harmony/rhythm defaults, per-track role helper stubs, and executable starter stem/mix rendering for common lanes
- Manual scaffold refresh: `python3 tools/songlab.py scaffold --project-id neon-solitude --force`

Renderers:
- `render_neon_solitude.py`
- `render_just_cant_stop.py`

Current projects:
- `data/projects/neon-solitude.neon.json`
- `factory/projects/neon-solitude.neon.json`
- `factory/projects/just-cant-stop.neon.json`
