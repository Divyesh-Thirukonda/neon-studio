#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ingest_transcript import (
    analyze_transcript,
    render_markdown as render_transcript_markdown,
    read_transcript,
)
from fill_in_blanks import (
    fill_in_blanks,
    render_markdown as render_fill_in_blanks_markdown,
)
from project_materializer import (
    build_project_materialization,
    ensure_project_renderer,
    write_project_files,
)


ROOT = Path(__file__).resolve().parent.parent
SONGLAB_DIR = ROOT / "songlab"
SONGLAB_PROJECTS_DIR = SONGLAB_DIR / "projects"


@dataclass(frozen=True)
class Archetype:
    id: str
    label: str
    trigger_keywords: tuple[str, ...]
    normalized_intent: str
    reference_summary: list[str]
    arrangement_targets: list[str]
    sound_targets: list[str]
    mix_targets: list[str]
    iteration_backlog: list[str]
    acceptance_checks: list[str]


ARCHETYPES: tuple[Archetype, ...] = (
    Archetype(
        id="marshmello-alone-lane",
        label="Marshmello Alone Lane",
        trigger_keywords=("alone", "marshmello"),
        normalized_intent="Create a bright future-bass / festival EDM track that pushes close to the emotional and production lane of Marshmello's Alone, using the reference aggressively for arrangement and sound, while avoiding exact topline or lyric cloning.",
        reference_summary=[
            "Simple childlike hook, then fuller filled-in drop hook",
            "Wide supersaw chords with clean sub/fat bass support",
            "Trap-leaning kick, clap, and hat grid with restrained density",
            "Build based on noise, filter sweep, clap roll, teaser lead, and impact",
            "Second drop should add width, hats/ride motion, and extra sparkle rather than a new song section",
        ],
        arrangement_targets=[
            "16-bar intro and verse that establish hook DNA before the first drop",
            "First drop should feel open and memorable, not over-arranged",
            "Mid-song break should strip back to pads or motif fragments",
            "Eight-bar build should stage tension through filter, roll, riser, and bass print",
            "Final drop should escalate mostly through width, cymbal energy, and ear candy",
        ],
        sound_targets=[
            "Square/saw lead as the center hook voice",
            "Supersaw chord stack with sidechain pump",
            "Sub plus mid bass that tracks the chord rhythm",
            "White-noise uplifters, downlifters, impact, reverse tail, crowd/air bed",
            "Optional muted guitar or pluck in verse only if it leaves the drop clean",
        ],
        mix_targets=[
            "Low end belongs mostly to kick and bass",
            "Lead should be bright but not brittle",
            "Claps should feel wider than the core snare",
            "Build automation should be obvious in both audio and project metadata",
        ],
        iteration_backlog=[
            "Simplify the hook if it feels too clever",
            "Make the drop brighter before making it busier",
            "Prefer stronger sidechain and spacing over adding extra layers",
            "If the final drop is weak, add doubles, crashes, or ear candy before rewriting chords",
        ],
        acceptance_checks=[
            "Project captures the commercial reference feel without relying on exact topline copying",
            "The hook is memorable after one listen",
            "Drop one and drop two share identity but not identical energy",
            "The .neon.json, stems, MIDI, and bundled app seed all agree on BPM and layout",
        ],
    ),
    Archetype(
        id="future-bass-generic",
        label="Future Bass Generic",
        trigger_keywords=("future bass", "festival", "edm"),
        normalized_intent="Create a hook-first future-bass project with a readable arrangement, clean low end, and a portable Neon Studio session, using any named references as valid production targets rather than reasons to refuse.",
        reference_summary=[
            "Memorable lead motif with simple supporting harmony",
            "Pumped chords and a wide but controlled top end",
            "Build-to-drop contrast more important than raw layer count",
        ],
        arrangement_targets=[
            "Intro, verse, build, drop, break, final drop, outro",
            "Every section should have a reason to exist in the project file",
        ],
        sound_targets=[
            "Lead, chords, bass, drums, FX as obvious primary lanes",
            "Automation and ear-candy lanes only when they have a clear job",
        ],
        mix_targets=[
            "No low-frequency clutter outside bass and kick",
            "Final drop brighter and wider than the first",
        ],
        iteration_backlog=[
            "Simplify the melodic contour before adding countermelodies",
            "Tighten drums before touching mastering-style loudness",
        ],
        acceptance_checks=[
            "Portable project renders with coherent stems and metadata",
            "The drop reads immediately from the recipe and playlist",
        ],
    ),
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned[:72] or "song-project"


def stemify(project_id: str) -> str:
    return project_id.replace("-", "_")


def infer_generator_path(project_id: str) -> Path:
    stem = stemify(project_id)
    candidate = ROOT / f"render_{stem}.py"
    if candidate.exists():
        return candidate
    legacy = ROOT / f"make_{stem}.py"
    if legacy.exists():
        return legacy
    return candidate


def infer_project_paths(project_id: str) -> dict[str, Path]:
    stem = stemify(project_id)
    return {
        "data_project": ROOT / "data" / "projects" / f"{project_id}.neon.json",
        "factory_project": ROOT / "factory" / "projects" / f"{project_id}.neon.json",
        "full_mix": ROOT / "exports" / f"{stem}_full_mix.wav",
        "arrangement_midi": ROOT / "midi" / f"{stem}_arrangement.mid",
        "generator": infer_generator_path(project_id),
    }


def detect_archetype(prompt: str) -> Archetype:
    text = prompt.lower()
    best: tuple[int, Archetype] | None = None
    for archetype in ARCHETYPES:
        score = sum(1 for keyword in archetype.trigger_keywords if keyword in text)
        if score <= 0:
            continue
        if best is None or score > best[0]:
            best = (score, archetype)
    return best[1] if best else ARCHETYPES[-1]


def infer_project_id(prompt: str, explicit_id: str | None = None) -> str:
    if explicit_id:
        return slugify(explicit_id)
    text = prompt.lower()
    if "neon solitude" in text:
        return "neon-solitude"
    if "just can't stop" in text or "just cant stop" in text:
        return "just-cant-stop"
    match = re.search(r"(?:project|song)\s+called\s+([a-z0-9][a-z0-9\s'-]{1,40})", text)
    if match:
        return slugify(match.group(1))
    return "neon-solitude" if (ROOT / "data" / "projects" / "neon-solitude.neon.json").exists() else slugify(prompt[:48])


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def summarize_project(project_path: Path) -> dict[str, Any]:
    raw = load_json(project_path)
    if not raw:
        return {
            "exists": False,
            "path": str(project_path.relative_to(ROOT)),
        }
    snapshot = raw.get("snapshot", {})
    tracks = snapshot.get("tracks", [])
    recipe = snapshot.get("recipe", [])
    return {
        "exists": True,
        "path": str(project_path.relative_to(ROOT)),
        "name": raw.get("name"),
        "description": raw.get("description"),
        "keyCenter": raw.get("keyCenter"),
        "bpm": snapshot.get("bpm"),
        "trackCount": len(tracks),
        "trackNames": [track.get("name") for track in tracks],
        "recipeCount": len(recipe),
        "loopRange": [snapshot.get("loopStartBar"), snapshot.get("loopEndBar")],
        "snap": snapshot.get("snap"),
        "swing": snapshot.get("swing"),
        "generatorLikely": f"render_{stemify(raw.get('id', 'project'))}.py",
    }


def build_phase_plan(archetype: Archetype, paths: dict[str, Path], transcript_spec: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    generator_exists = paths["generator"].exists()
    phases: list[dict[str, Any]] = []
    if transcript_spec:
        phases.append(
            {
                "id": "ingest",
                "title": "Transcript Ingest",
                "goal": "Convert the walkthrough transcript into a structured project spec before editing the song.",
                "deliverables": [
                    "transcript.txt copied into the songlab session",
                    "transcript_spec.json with sections, tracks, plugins, and techniques",
                    "transcript_spec.md human-readable coverage summary",
                    "fill_in_blanks.md with inferred defaults for missing production details",
                ],
            }
        )
        phases.append(
            {
                "id": "materialize",
                "title": "Project Materialization",
                "goal": "Generate the actual .neon.json project layout, clip map, and renderer entrypoint from the transcript before detailed song work.",
                "deliverables": [
                    "data/projects/<project-id>.neon.json project",
                    "factory/projects/<project-id>.neon.json bundled project",
                    "render_<project>.py generated product renderer if no renderer exists yet",
                ],
            }
        )
    phases.extend([
        {
            "id": "plan",
            "title": "Reference DNA",
            "goal": "Convert the user prompt into a concrete target lane with explicit boundaries around what should be matched closely versus only approximated.",
            "deliverables": [
                "session.json updated with normalized intent",
                "plan.md with arrangement and mix targets",
            ],
        },
        {
            "id": "inspect",
            "title": "Current Project Audit",
            "goal": "Read the current .neon.json and generator so edits land on the real project, not a stale seed.",
            "deliverables": [
                str(paths["data_project"].relative_to(ROOT)),
                str(paths["factory_project"].relative_to(ROOT)),
                str(paths["generator"].relative_to(ROOT)) + (" (exists)" if generator_exists else " (create if missing)"),
            ],
        },
        {
            "id": "implement",
            "title": "Generator / Project Edit",
            "goal": "Adjust the renderer and project metadata together so arrangement, stems, and recipe stay coherent.",
            "deliverables": [
                "Updated stem synthesis or arrangement logic",
                "Updated track/recipe metadata when musical structure changes",
            ],
        },
        {
            "id": "render",
            "title": "Render + Sync",
            "goal": "Render the mix, stems, and MIDI and ensure the factory/data project files match.",
            "deliverables": [
                str(paths["full_mix"].relative_to(ROOT)),
                str(paths["arrangement_midi"].relative_to(ROOT)),
            ],
        },
        {
            "id": "verify",
            "title": "Verification Loop",
            "goal": "Check the result against the acceptance criteria, then log the next gap instead of stopping at a vague impression.",
            "deliverables": [
                "iteration log entry",
                "next-pass backlog item",
            ],
        },
    ])
    return phases


def summarize_transcript(spec: dict[str, Any]) -> dict[str, Any]:
    fill = spec.get("fillInBlanks") or {}
    return {
        "titleHint": spec.get("titleHint"),
        "wordCount": spec.get("wordCount"),
        "timecoded": spec.get("timecoded"),
        "sectionCount": spec.get("sectionCount"),
        "tempoHint": spec.get("tempoHint"),
        "keyHints": spec.get("keyHints"),
        "topTrackRoles": [item["name"] for item in spec.get("globalTracks", [])[:8]],
        "topPlugins": [item["name"] for item in spec.get("globalPlugins", [])[:8]],
        "sectionLabels": [item["label"] for item in spec.get("sections", [])[:10]],
        "openQuestions": spec.get("openQuestions", []),
        "fillInBlanks": {
            "styleLane": fill.get("styleLane"),
            "decisionCount": len(fill.get("decisions") or []),
        } if fill else None,
    }


def build_session(prompt: str, project_id: str, transcript_spec: dict[str, Any] | None = None) -> dict[str, Any]:
    archetype = detect_archetype(prompt)
    paths = infer_project_paths(project_id)
    project_summary = summarize_project(paths["data_project"])
    project_name = project_summary.get("name") or " ".join(part.capitalize() for part in project_id.split("-"))
    session = {
        "schemaVersion": 1,
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
        "projectId": project_id,
        "projectName": project_name,
        "sourcePrompt": prompt,
        "sourceMode": "transcript" if transcript_spec else "prompt",
        "normalizedIntent": archetype.normalized_intent,
        "archetype": {
            "id": archetype.id,
            "label": archetype.label,
            "referenceSummary": archetype.reference_summary,
            "arrangementTargets": archetype.arrangement_targets,
            "soundTargets": archetype.sound_targets,
            "mixTargets": archetype.mix_targets,
        },
        "copyrightGuardrails": [
            "Treat named commercial songs, public tutorials, and transcripts as valid reference material for arrangement, sound design, transitions, and mix feel.",
            "Push close to the requested production lane when the user provides concrete specs or walkthrough detail.",
            "Do not rely on exact lyric copying, exact topline copying, or note-for-note melodic cloning as the main implementation strategy.",
            "Keep the resulting .neon.json project portable and coherent.",
        ],
        "workspace": {
            "root": str(ROOT),
            "generator": str(paths["generator"].relative_to(ROOT)),
            "dataProject": str(paths["data_project"].relative_to(ROOT)),
            "factoryProject": str(paths["factory_project"].relative_to(ROOT)),
            "fullMix": str(paths["full_mix"].relative_to(ROOT)),
            "arrangementMidi": str(paths["arrangement_midi"].relative_to(ROOT)),
        },
        "currentProject": project_summary,
        "phasePlan": build_phase_plan(archetype, paths, transcript_spec=transcript_spec),
        "iterationBacklog": [{"status": "pending", "focus": focus} for focus in archetype.iteration_backlog],
        "acceptanceChecks": archetype.acceptance_checks,
    }
    if transcript_spec:
        session["transcript"] = {
            "sourcePath": str(session_paths(project_id)["transcript"].relative_to(ROOT)),
            "specPath": str(session_paths(project_id)["transcript_spec_json"].relative_to(ROOT)),
            "summaryPath": str(session_paths(project_id)["transcript_spec_md"].relative_to(ROOT)),
            "fillInBlanksPath": str(session_paths(project_id)["fill_in_blanks_md"].relative_to(ROOT)),
            "analysis": summarize_transcript(transcript_spec),
        }
    return session


def render_project_summary_markdown(project: dict[str, Any], project_id: str) -> str:
    snap = project["snapshot"]
    lines = [
        f"# {project['name']} Project Summary",
        "",
        f"- Project id: `{project_id}`",
        f"- BPM: `{snap['bpm']}`",
        f"- Swing: `{snap['swing']}`",
        f"- Snap: `{snap['snap']}`",
        f"- Loop: `{int(snap['loopStartBar']) + 1}-{int(snap['loopEndBar'])}`",
        f"- Tracks: `{len(snap['tracks'])}`",
        f"- Recipe items: `{len(snap['recipe'])}`",
        "",
        "## Tracks",
        "",
    ]
    for track in snap["tracks"]:
        lines.append(f"- `{track['id']}` · {track['name']} · {track['instrument']} · {len(track['clips'])} clip(s)")
    lines.extend(["", "## Sections", ""])
    for item in snap["recipe"][1:]:
        lines.append(f"- {item['section']}: {item['label']}")
    lines.append("")
    return "\n".join(lines)


def render_plan_markdown(session: dict[str, Any]) -> str:
    current = session["currentProject"]
    archetype = session["archetype"]
    lines: list[str] = []
    lines.append(f"# {session['projectName']} Songlab Plan")
    lines.append("")
    lines.append("## Prompt")
    lines.append("")
    lines.append(session["sourcePrompt"])
    lines.append("")
    lines.append("## Normalized Intent")
    lines.append("")
    lines.append(session["normalizedIntent"])
    lines.append("")
    transcript = session.get("transcript")
    if transcript:
        analysis = transcript.get("analysis", {})
        lines.append("## Transcript Ingest")
        lines.append("")
        lines.append(f"- Raw transcript: `{transcript['sourcePath']}`")
        lines.append(f"- Structured spec: `{transcript['specPath']}`")
        lines.append(f"- Coverage summary: `{transcript['summaryPath']}`")
        lines.append(f"- Timecoded: `{analysis.get('timecoded')}`")
        lines.append(f"- Sections: `{analysis.get('sectionCount')}`")
        lines.append(f"- Tempo hint: `{analysis.get('tempoHint') or 'unset'}`")
        key_hints = analysis.get("keyHints") or []
        lines.append(f"- Key hints: `{', '.join(key_hints) if key_hints else 'unset'}`")
        fill_analysis = analysis.get("fillInBlanks") or {}
        if fill_analysis:
            lines.append(f"- Fill-in-blanks lane: `{fill_analysis.get('styleLane') or 'unset'}`")
            lines.append(f"- Inferred decisions: `{fill_analysis.get('decisionCount') or 0}`")
        top_tracks = analysis.get("topTrackRoles") or []
        if top_tracks:
            lines.append(f"- Top track roles: {', '.join(top_tracks)}")
        top_plugins = analysis.get("topPlugins") or []
        if top_plugins:
            lines.append(f"- Top plugins: {', '.join(top_plugins)}")
        section_labels = analysis.get("sectionLabels") or []
        if section_labels:
            lines.append(f"- Section flow: {' -> '.join(section_labels)}")
        for item in analysis.get("openQuestions", []) or []:
            lines.append(f"- Open question: {item}")
        lines.append("")
    lines.append("## Guardrails")
    lines.append("")
    for item in session["copyrightGuardrails"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Current Project")
    lines.append("")
    if current.get("exists"):
        lines.append(f"- Project file: `{current['path']}`")
        lines.append(f"- BPM: `{current.get('bpm')}`")
        lines.append(f"- Key: `{current.get('keyCenter') or 'unset'}`")
        lines.append(f"- Tracks: `{current.get('trackCount')}`")
        lines.append(f"- Recipe items: `{current.get('recipeCount')}`")
        track_names = ", ".join(current.get("trackNames", [])[:10])
        if track_names:
            lines.append(f"- Main tracks: {track_names}")
    else:
        lines.append("- No current project file found yet.")
    lines.append("")
    lines.append(f"## Target Lane: {archetype['label']}")
    lines.append("")
    lines.append("### Reference Summary")
    for item in archetype["referenceSummary"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("### Arrangement Targets")
    for item in archetype["arrangementTargets"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("### Sound Targets")
    for item in archetype["soundTargets"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("### Mix Targets")
    for item in archetype["mixTargets"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Workflow")
    lines.append("")
    for phase in session["phasePlan"]:
        lines.append(f"### {phase['title']}")
        lines.append(f"- Goal: {phase['goal']}")
        for item in phase["deliverables"]:
            lines.append(f"- Deliverable: {item}")
        lines.append("")
    lines.append("## Acceptance Checks")
    lines.append("")
    for item in session["acceptanceChecks"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Iteration Backlog")
    lines.append("")
    for item in session["iterationBacklog"]:
        lines.append(f"- [{item['status']}] {item['focus']}")
    lines.append("")
    return "\n".join(lines)


def session_dir(project_id: str) -> Path:
    return SONGLAB_PROJECTS_DIR / project_id


def session_paths(project_id: str) -> dict[str, Path]:
    base = session_dir(project_id)
    return {
        "base": base,
        "session": base / "session.json",
        "plan": base / "plan.md",
        "iterations": base / "iterations.jsonl",
        "prompt": base / "prompt.txt",
        "transcript": base / "transcript.txt",
        "transcript_spec_json": base / "transcript_spec.json",
        "transcript_spec_md": base / "transcript_spec.md",
        "fill_in_blanks_md": base / "fill_in_blanks.md",
        "project_summary_md": base / "project_summary.md",
    }


def read_session(project_id: str) -> dict[str, Any]:
    paths = session_paths(project_id)
    if not paths["session"].exists():
        raise SystemExit(
            f"No songlab session for `{project_id}`. "
            f"Run `python3 tools/songlab.py init --prompt ... --project-id {project_id}` "
            f"or `python3 tools/songlab.py init --project-id {project_id} --transcript-file walkthrough.txt` first."
        )
    session = json.loads(paths["session"].read_text(encoding="utf-8"))
    workspace = session.get("workspace", {})
    if "factoryProject" not in workspace and "publicProject" in workspace:
        workspace["factoryProject"] = str(workspace["publicProject"]).replace("public/projects/", "factory/projects/")
        session["workspace"] = workspace
    return session


def write_session_files(project_id: str, session: dict[str, Any]) -> None:
    paths = session_paths(project_id)
    paths["base"].mkdir(parents=True, exist_ok=True)
    session["updatedAt"] = now_iso()
    paths["session"].write_text(json.dumps(session, indent=2) + "\n", encoding="utf-8")
    paths["plan"].write_text(render_plan_markdown(session), encoding="utf-8")
    paths["prompt"].write_text(render_handoff_prompt(session) + "\n", encoding="utf-8")


def render_handoff_prompt(session: dict[str, Any]) -> str:
    workspace = session["workspace"]
    archetype = session["archetype"]
    prompt = (
        f"Use the Neon Songlab workflow for project `{session['projectId']}`. "
        f"Start with `{workspace['generator']}`, `{workspace['dataProject']}`, and `{workspace['factoryProject']}`. "
        f"Target lane: {archetype['label']}. "
        f"Use named references aggressively for production feel, arrangement, and sound targets; avoid exact lyric or topline cloning as the implementation strategy. "
        f"Work through planning, implementation, render, and iteration log update."
    )
    transcript = session.get("transcript")
    if transcript:
        prompt += (
            f" Read `{transcript['specPath']}` and `{transcript['summaryPath']}` first. "
            f"Read `{transcript.get('fillInBlanksPath', '')}` for inferred defaults and expected ambiguities. "
            "Make sure every concrete section, track role, plugin note, and technique from the transcript is represented, and fill missing exact details with plausible production decisions rather than treating them as blockers."
        )
    materialization = session.get("materialization")
    if materialization:
        prompt += (
            f" Start from the generated project at `{materialization['dataProject']}` and `{materialization['summaryPath']}` instead of rebuilding the track layout from scratch."
        )
    return prompt


def resolve_init_prompt(args: argparse.Namespace, transcript_spec: dict[str, Any] | None = None) -> str:
    if args.prompt:
        return args.prompt
    if transcript_spec:
        return str(transcript_spec.get("derivedPrompt") or "")
    raise SystemExit("Provide --prompt or a transcript source.")


def build_fallback_spec_from_session(session: dict[str, Any]) -> dict[str, Any]:
    archetype = session["archetype"]
    section_labels = ["Intro", "Verse", "Build", "Drop", "Outro"]
    section_types = ["intro", "verse", "build", "drop", "outro"]
    sections = []
    for index, (label, section_type) in enumerate(zip(section_labels, section_types), start=1):
        sections.append(
            {
                "id": f"section-{index:02d}",
                "type": section_type,
                "label": label,
                "summary": f"{label} project generated from the Songlab session.",
                "trackRoles": [role.split()[0].lower() for role in archetype.get("soundTargets", [])[:5] if role],
                "plugins": [],
                "techniques": [],
            }
        )
    return {
        "projectId": session["projectId"],
        "titleHint": session["projectName"],
        "sourcePrompt": session["sourcePrompt"],
        "tempoHint": session["currentProject"].get("bpm"),
        "keyHints": [session["currentProject"].get("keyCenter")] if session["currentProject"].get("keyCenter") else [],
        "sections": sections,
        "globalTracks": [],
        "globalPlugins": [],
        "globalTechniques": [],
    }


def materialize_project(project_id: str, session: dict[str, Any], transcript_spec: dict[str, Any] | None = None, *, force: bool = False) -> dict[str, Any]:
    paths = session_paths(project_id)
    spec = transcript_spec
    if spec is None:
        transcript = session.get("transcript")
        if transcript:
            spec = json.loads((ROOT / transcript["specPath"]).read_text(encoding="utf-8"))
        else:
            spec = build_fallback_spec_from_session(session)
    data_project = ROOT / session["workspace"]["dataProject"]
    if data_project.exists() and not force:
        return {"skipped": True, "reason": "existing-project"}

    project = build_project_materialization(spec, project_id=project_id, prompt=session["sourcePrompt"])
    written = write_project_files(ROOT, project, project_id)
    renderer_path = ensure_project_renderer(
        ROOT,
        project_id,
        project["name"],
        project,
        spec,
        prompt=session["sourcePrompt"],
        overwrite=force,
    )
    paths["project_summary_md"].write_text(render_project_summary_markdown(project, project_id) + "\n", encoding="utf-8")
    session["materialization"] = {
        "generatedAt": now_iso(),
        "dataProject": str(written["data"].relative_to(ROOT)),
        "factoryProject": str(written["factory"].relative_to(ROOT)),
        "renderer": str(renderer_path.relative_to(ROOT)),
        "summaryPath": str(paths["project_summary_md"].relative_to(ROOT)),
    }
    return {"skipped": False, "project": project, "written": written, "renderer": renderer_path}


def command_init(args: argparse.Namespace) -> int:
    transcript_text = None
    transcript_spec = None
    if args.transcript_text or args.transcript_file or args.transcript_stdin:
        transcript_text = read_transcript(args)
        seed_project_id = infer_project_id(args.prompt or transcript_text, args.project_id)
        transcript_spec = analyze_transcript(transcript_text, project_id=seed_project_id, prompt=args.prompt)
        prompt = resolve_init_prompt(args, transcript_spec=transcript_spec)
        project_id = infer_project_id(prompt or transcript_text, args.project_id)
        if project_id != seed_project_id:
            transcript_spec = analyze_transcript(transcript_text, project_id=project_id, prompt=prompt)
        if not args.no_fill_blanks:
            transcript_spec = fill_in_blanks(transcript_spec, prompt=prompt)
    else:
        prompt = resolve_init_prompt(args)
        project_id = infer_project_id(prompt, args.project_id)
    session = build_session(prompt, project_id, transcript_spec=transcript_spec)
    write_session_files(project_id, session)
    if transcript_text is not None and transcript_spec is not None:
        paths = session_paths(project_id)
        paths["transcript"].write_text(transcript_text.strip() + "\n", encoding="utf-8")
        paths["transcript_spec_json"].write_text(json.dumps(transcript_spec, indent=2) + "\n", encoding="utf-8")
        paths["transcript_spec_md"].write_text(render_transcript_markdown(transcript_spec) + "\n", encoding="utf-8")
        paths["fill_in_blanks_md"].write_text(render_fill_in_blanks_markdown(transcript_spec), encoding="utf-8")
    materialize_result = None
    if transcript_spec is not None and not args.no_materialize:
        materialize_result = materialize_project(project_id, session, transcript_spec=transcript_spec, force=args.force_materialize)
        session = build_session(prompt, project_id, transcript_spec=transcript_spec)
        if materialize_result and not materialize_result.get("skipped"):
            session["materialization"] = {
                "generatedAt": now_iso(),
                "dataProject": f"data/projects/{project_id}.neon.json",
                "factoryProject": f"factory/projects/{project_id}.neon.json",
                "renderer": str(materialize_result["renderer"].relative_to(ROOT)),
                "summaryPath": str(session_paths(project_id)["project_summary_md"].relative_to(ROOT)),
            }
        write_session_files(project_id, session)
    print(f"Initialized songlab session for {project_id}")
    print(session_paths(project_id)["session"].relative_to(ROOT))
    print(session_paths(project_id)["plan"].relative_to(ROOT))
    if transcript_spec is not None:
        print(session_paths(project_id)["transcript_spec_json"].relative_to(ROOT))
        print(session_paths(project_id)["fill_in_blanks_md"].relative_to(ROOT))
        if materialize_result and not materialize_result.get("skipped"):
            print(session_paths(project_id)["project_summary_md"].relative_to(ROOT))
    return 0


def command_status(args: argparse.Namespace) -> int:
    project_id = infer_project_id(args.prompt or "", args.project_id)
    paths = session_paths(project_id)
    session = read_session(project_id) if paths["session"].exists() else None
    project_summary = summarize_project(infer_project_paths(project_id)["data_project"])
    payload = {
        "projectId": project_id,
        "sessionExists": bool(session),
        "sessionPath": str(paths["session"].relative_to(ROOT)),
        "currentProject": project_summary,
        "workspace": session.get("workspace") if session else None,
        "transcript": session.get("transcript") if session else None,
        "materialization": session.get("materialization") if session else None,
        "nextBacklog": next((item["focus"] for item in session.get("iterationBacklog", []) if item.get("status") != "done"), None) if session else None,
    }
    print(json.dumps(payload, indent=2))
    return 0


def command_iterate(args: argparse.Namespace) -> int:
    project_id = infer_project_id(args.prompt or "", args.project_id)
    session = read_session(project_id)
    paths = session_paths(project_id)
    paths["base"].mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": now_iso(),
        "note": args.note,
        "result": args.result or "",
    }
    with paths["iterations"].open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    if session.get("iterationBacklog"):
        for item in session["iterationBacklog"]:
            if item.get("status") == "pending":
                item["status"] = "in_progress"
                break
    write_session_files(project_id, session)
    print(f"Logged iteration for {project_id}")
    return 0


def command_prompt(args: argparse.Namespace) -> int:
    project_id = infer_project_id(args.prompt or "", args.project_id)
    session = read_session(project_id)
    print(render_handoff_prompt(session))
    return 0


def command_transcript(args: argparse.Namespace) -> int:
    project_id = infer_project_id(args.prompt or "", args.project_id)
    session = read_session(project_id)
    transcript = session.get("transcript")
    if not transcript:
        raise SystemExit(f"No transcript artifacts for `{project_id}`.")
    spec_path = ROOT / transcript["specPath"]
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    if args.format == "markdown":
        summary_path = ROOT / transcript["summaryPath"]
        print(summary_path.read_text(encoding="utf-8").rstrip())
    else:
        print(json.dumps(payload, indent=2))
    return 0


def command_materialize(args: argparse.Namespace) -> int:
    project_id = infer_project_id(args.prompt or "", args.project_id)
    session = read_session(project_id)
    result = materialize_project(project_id, session, force=args.force)
    if result.get("skipped"):
        print(json.dumps({"projectId": project_id, "skipped": True, "reason": result["reason"]}, indent=2))
        return 0
    session = read_session(project_id)
    session["materialization"] = {
        "generatedAt": now_iso(),
        "dataProject": f"data/projects/{project_id}.neon.json",
        "factoryProject": f"factory/projects/{project_id}.neon.json",
        "renderer": str(result["renderer"].relative_to(ROOT)),
        "summaryPath": str(session_paths(project_id)["project_summary_md"].relative_to(ROOT)),
    }
    write_session_files(project_id, session)
    print(json.dumps({
        "projectId": project_id,
        "dataProject": session["materialization"]["dataProject"],
        "factoryProject": session["materialization"]["factoryProject"],
        "renderer": session["materialization"]["renderer"],
        "summaryPath": session["materialization"]["summaryPath"],
    }, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Neon Studio song planning and iteration helper.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_cmd = subparsers.add_parser("init", help="Create or refresh a songlab session from a user prompt.")
    init_cmd.add_argument("--prompt", help="User request or musical brief. By itself this creates a planning session; transcript inputs trigger fill-in-the-blanks/materialization.")
    init_cmd.add_argument("--project-id", help="Project id, e.g. neon-solitude.")
    init_cmd.add_argument("--transcript-text", help="Raw transcript, walkthrough, step-by-step, or direct song description to enrich and materialize.")
    init_cmd.add_argument("--transcript-file", help="Path to a transcript, walkthrough, step-by-step, or song-description text file.")
    init_cmd.add_argument("--transcript-stdin", action="store_true", help="Read transcript, walkthrough, step-by-step, or direct song description from stdin.")
    init_cmd.add_argument("--no-fill-blanks", action="store_true", help="Keep raw transcript analysis without inferred production defaults.")
    init_cmd.add_argument("--no-materialize", action="store_true", help="Do not auto-generate the real project files when a transcript is provided.")
    init_cmd.add_argument("--force-materialize", action="store_true", help="Allow project materialization to overwrite a missing-or-new project path during init.")
    init_cmd.set_defaults(func=command_init)

    status_cmd = subparsers.add_parser("status", help="Show current songlab and project status.")
    status_cmd.add_argument("--project-id", help="Project id, e.g. neon-solitude.")
    status_cmd.add_argument("--prompt", help="Optional prompt to infer the project id.")
    status_cmd.set_defaults(func=command_status)

    iterate_cmd = subparsers.add_parser("iterate", help="Append an iteration note.")
    iterate_cmd.add_argument("--project-id", help="Project id, e.g. neon-solitude.")
    iterate_cmd.add_argument("--prompt", help="Optional prompt to infer the project id.")
    iterate_cmd.add_argument("--note", required=True, help="What changed this pass.")
    iterate_cmd.add_argument("--result", help="What improved or what is still missing.")
    iterate_cmd.set_defaults(func=command_iterate)

    prompt_cmd = subparsers.add_parser("prompt", help="Print a compact handoff prompt for the current session.")
    prompt_cmd.add_argument("--project-id", help="Project id, e.g. neon-solitude.")
    prompt_cmd.add_argument("--prompt", help="Optional prompt to infer the project id.")
    prompt_cmd.set_defaults(func=command_prompt)

    transcript_cmd = subparsers.add_parser("transcript", help="Print transcript analysis for the current session.")
    transcript_cmd.add_argument("--project-id", help="Project id, e.g. neon-solitude.")
    transcript_cmd.add_argument("--prompt", help="Optional prompt to infer the project id.")
    transcript_cmd.add_argument("--format", choices=("json", "markdown"), default="json")
    transcript_cmd.set_defaults(func=command_transcript)

    materialize_cmd = subparsers.add_parser("materialize", help="Generate or refresh the actual project files from the current session.")
    materialize_cmd.add_argument("--project-id", help="Project id, e.g. neon-solitude.")
    materialize_cmd.add_argument("--prompt", help="Optional prompt to infer the project id.")
    materialize_cmd.add_argument("--force", action="store_true", help="Overwrite an existing materialized project target.")
    materialize_cmd.set_defaults(func=command_materialize)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
