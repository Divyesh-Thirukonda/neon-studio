Neon Studio native workspace

Neon Studio is one product surface: the native app, `.neon.json` project model, Songlab transcript/materialization tools, generated renderers, stems, skills, and sound checks all serve the same song-building workflow.

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
- `npm run fill-blanks -- --input-json songlab/projects/<project-id>/transcript_spec.json --format markdown`
- `npm run build:mac`
- `npm run open:mac`

Sound check workflow:
- `python3 tools/does_this_sound_good.py --project-id neon-solitude --format markdown`
- `npm run soundcheck -- --project-id neon-solitude --format markdown`
- Native app: Project panel > Check or Options > Does This Sound Good? analyzes the current project state and returns a score, blockers, and next actions.
- The Codex skill lives at `skills/does-this-sound-good/SKILL.md` and uses the same local checker.

Transcript workflow:
- `python3 tools/songlab.py init --project-id neon-solitude --transcript-file walkthrough.txt`
- Direct song ideas can use the same enriched path with `python3 tools/songlab.py init --project-id neon-solitude --prompt "brief" --transcript-text "song description"`
- `python3 tools/songlab.py transcript --project-id neon-solitude --format markdown`
- Codex can also pass transcript text through stdin with `--transcript-stdin`
- Transcript init runs a fill-in-the-blanks pass before materialization, so missing exact source details become labeled inferred defaults instead of blockers
- The filler writes `songlab/projects/<project-id>/fill_in_blanks.md` and embeds `fillInBlanks` decisions in `transcript_spec.json`
- Transcript init auto-materializes a real project when no project exists yet
- The transcript spec now stores normalized per-section `laneEvents` and `laneTransforms`, so exact cues like `lead: 1, 1.5, 2.5`, `lead: E5@1, G5@1.5, B5@2.5`, `lead: E5@1/0.5*0.85, G5@1.5!/0.25`, `lead: bar 1 E5@1 | bars 2-3 copy bar 1 transpose +12`, `lead: bars 1-2 copy intro lead bars 1 reverse`, `lead: bars 1-2 copy intro lead bars 1 skip 1.5`, `drums: bar 1 kick 1!,3*0.8 snare 2g,4! hats 1o*0.9,1.5!,2.5,3.5o`, `drums: bar 1 kick 1,3,4 mute 4`, `drums: bar 2 copy verse drums bars 1 double-time hats ride 1`, `automation: bars 1-8 filter 0.15->0.9`, `automation: bars 1-4 lead.filter 0.2->0.9 ease-in | bars 5-8 drums.volume 0.3->0.8 step | bars 9-12 hat.pan 0.1->0.8 ease-out`, `bass follows chords but skips beat 4`, or `copy drop 1 drums, add ride and double-time hats` survive into actual project generation
- Transcript-driven project generation now emits a section-aware `render_<project>.py` with per-section functions, transcript-conditioned harmony/rhythm defaults, explicit chord/beat/transposition parsing, compact note/drum event attributes (duration, gain, accent, ghost, open-hat, pan), explicit skip/mute/rest beat filtering, note-aware and bar-scoped lane-map reuse, cross-section lane copying, reverse/invert phrase transforms, drum-block reuse, parameter-specific automation-envelope reuse with curve control and target-lane routing, phrase-level reuse parsing (`same melody`, `filled in`, `same notes from the verse`), per-track role helpers, and executable starter stem/mix rendering for common lanes
- Manual project materialization refresh: `python3 tools/songlab.py materialize --project-id neon-solitude --force`

Renderers:
- `render_neon_solitude.py`
- `render_just_cant_stop.py`

Current projects:
- `data/projects/neon-solitude.neon.json`
- `factory/projects/neon-solitude.neon.json`
- `factory/projects/just-cant-stop.neon.json`

Reference recipe fixtures:
- `songlab/projects/just-cant-stop/producer_step_by_step.md` is a reusable recipe fixture for proving that future "make something like this" requests can be translated into buildable Neon Studio projects. It is not an active remake target by default.
