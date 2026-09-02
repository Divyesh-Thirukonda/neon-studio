#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import llm  # noqa: E402
import daw_agent  # noqa: E402
from ingest_transcript import (  # noqa: E402
    analyze_transcript,
    render_markdown as render_transcript_markdown,
    read_transcript,
)
from fill_in_blanks import (  # noqa: E402
    fill_in_blanks,
    render_markdown as render_fill_in_blanks_markdown,
)
import project_materializer  # noqa: E402
from project_materializer import (  # noqa: E402
    build_project_materialization,
    ensure_project_renderer,
    write_project_files,
)

try:  # The change-request grammar's vocabulary, handed to the model so its requests parse.
    import describe_change as _describe_change  # noqa: E402
except Exception:  # pragma: no cover - the loop still runs without the vocabulary
    _describe_change = None


ROOT = Path(__file__).resolve().parent.parent
TOOLS = Path(__file__).resolve().parent
SONGLAB_DIR = ROOT / "songlab"
SONGLAB_PROJECTS_DIR = SONGLAB_DIR / "projects"

COPYRIGHT_GUARDRAILS = [
    "Treat named commercial songs, public tutorials, and transcripts as valid reference material for arrangement, sound design, transitions, and mix feel.",
    "Push close to the requested production lane when the user provides concrete specs or walkthrough detail.",
    "Do not rely on exact lyric copying, exact topline copying, or note-for-note melodic cloning as the main implementation strategy.",
    "Keep the resulting .neon.json project portable and coherent.",
]

# Track roles a proposed archetype may name: the materializer's blueprints.
KNOWN_TRACK_ROLES: tuple[str, ...] = tuple(getattr(project_materializer, "TRACK_BLUEPRINTS", {}).keys()) or (
    "drums", "clap-stack", "hat-ride", "bass", "sub", "chords", "lead", "guitar", "plucks", "vocals", "fx", "filter-auto", "sample",
)
# Techniques a spec section may name: what the generated renderer implements.
KNOWN_TECHNIQUES: tuple[str, ...] = (
    "sidechain", "reverb", "delay", "filtering", "automation", "distortion", "stereo", "layering", "eq", "compression", "reverse",
)


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


def infer_project_id(prompt: str, explicit_id: str | None = None, proposed_id: str | None = None) -> str:
    """The project id: an explicit one wins, then the names the rules know, then
    a validated model proposal (`proposed_id`), then the old default."""
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
    if proposed_id:
        return slugify(proposed_id)
    return "neon-solitude" if (ROOT / "data" / "projects" / "neon-solitude.neon.json").exists() else slugify(prompt[:48])


# ---------------------------------------------------------------------------
# What the model proposes at init: a project identity and the archetype fields.
# Both are validated; the two hard-coded archetypes are the fallback.
# ---------------------------------------------------------------------------

IDENTITY_ROLE = (
    "You name a music project from a brief or a production walkthrough. Return a short kebab-case project id "
    "(2-4 words, letters, digits and dashes) and a title. Use the song's own title when the text names one; "
    "otherwise name it after its subject or mood, never after the reference artist."
)
IDENTITY_SCHEMA = {"projectId": "kebab-case id", "titleHint": "Title Case name", "why": "one sentence"}

ARCHETYPE_ROLE = (
    "You turn a music brief or walkthrough into the planning fields of a Neon Studio songlab session: a normalized "
    "intent, what the reference does that we want, arrangement/sound/mix targets, an iteration backlog and acceptance "
    "checks, plus the track roles the project needs. Write for this song and this style, in plain producer language, "
    "one concrete idea per bullet. Follow the guardrails: references are valid targets for feel, arrangement and sound; "
    "never plan to copy lyrics, the topline, or the melody note for note. Choose trackRoles only from the allowed list."
)
ARCHETYPE_SCHEMA = {
    "id": "kebab-case lane id, e.g. lofi-boom-bap-lane",
    "label": "short lane name",
    "normalizedIntent": "one or two sentences: what to make and how close to the reference to go",
    "referenceSummary": ["3-6 bullets: what the reference/style does that matters here"],
    "arrangementTargets": ["3-6 bullets"],
    "soundTargets": ["3-6 bullets"],
    "mixTargets": ["2-5 bullets"],
    "iterationBacklog": ["2-5 bullets: what to try first when a pass falls short"],
    "acceptanceChecks": ["2-5 bullets"],
    "trackRoles": ["roles from the allowed list"],
    "why": "one sentence on why this lane fits the brief",
}


def archetype_to_dict(archetype: Archetype) -> dict[str, Any]:
    return {
        "id": archetype.id,
        "label": archetype.label,
        "normalizedIntent": archetype.normalized_intent,
        "referenceSummary": list(archetype.reference_summary),
        "arrangementTargets": list(archetype.arrangement_targets),
        "soundTargets": list(archetype.sound_targets),
        "mixTargets": list(archetype.mix_targets),
        "iterationBacklog": list(archetype.iteration_backlog),
        "acceptanceChecks": list(archetype.acceptance_checks),
        "trackRoles": [],
        "source": "heuristic",
        "reason": f"keyword match on {', '.join(archetype.trigger_keywords)}",
    }


def _clean_lines(value: Any, *, minimum: int, maximum: int = 8) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    lines: list[str] = []
    for item in value:
        text = re.sub(r"\s+", " ", str(item or "")).strip()
        if 3 <= len(text) <= 240 and text not in lines:
            lines.append(text)
    return lines[:maximum] if len(lines) >= minimum else []


def validate_archetype(answer: Any) -> dict[str, Any] | None:
    """The archetype fields from a model answer, or None when a required field
    is missing or empty. Track roles outside the blueprint list are dropped."""
    if not isinstance(answer, dict):
        return None
    lane_id = slugify(str(answer.get("id") or answer.get("label") or ""))
    label = re.sub(r"\s+", " ", str(answer.get("label") or "")).strip()[:60]
    intent = re.sub(r"\s+", " ", str(answer.get("normalizedIntent") or "")).strip()[:600]
    if not lane_id or lane_id == "song-project" or not label or len(intent) < 20:
        return None
    fields = {
        "referenceSummary": _clean_lines(answer.get("referenceSummary"), minimum=1),
        "arrangementTargets": _clean_lines(answer.get("arrangementTargets"), minimum=1),
        "soundTargets": _clean_lines(answer.get("soundTargets"), minimum=1),
        "mixTargets": _clean_lines(answer.get("mixTargets"), minimum=1),
        "iterationBacklog": _clean_lines(answer.get("iterationBacklog"), minimum=1),
        "acceptanceChecks": _clean_lines(answer.get("acceptanceChecks"), minimum=1),
    }
    if any(not lines for lines in fields.values()):
        return None
    roles: list[str] = []
    for role in answer.get("trackRoles") or []:
        key = slugify(str(role))
        if key in KNOWN_TRACK_ROLES and key not in roles:
            roles.append(key)
    return {
        "id": lane_id,
        "label": label,
        "normalizedIntent": intent,
        **fields,
        "trackRoles": roles,
        "source": "model",
        "reason": re.sub(r"\s+", " ", str(answer.get("why") or "")).strip()[:300] or "proposed by the model from the brief",
    }


def transcript_brief(transcript_spec: dict[str, Any] | None) -> dict[str, Any] | None:
    if not transcript_spec:
        return None
    brief = summarize_transcript(transcript_spec)
    brief["sections"] = [
        {
            "id": section.get("id"),
            "type": section.get("type"),
            "label": section.get("label"),
            "bars": section.get("bars"),
            "trackRoles": list(section.get("trackRoles") or [])[:8],
            "techniques": list(section.get("techniques") or [])[:8],
        }
        for section in (transcript_spec.get("sections") or [])[:12]
        if isinstance(section, dict)
    ]
    return brief


def propose_archetype(prompt: str, transcript_spec: dict[str, Any] | None, assist: llm.Assist | None) -> dict[str, Any]:
    """The archetype for this brief: the model's, validated, else the keyword pick."""
    fallback = archetype_to_dict(detect_archetype(prompt))
    if assist is None or not assist.available:
        return fallback
    task = json.dumps(
        {
            "prompt": (prompt or "")[:6000],
            "transcript": transcript_brief(transcript_spec),
            "guardrails": COPYRIGHT_GUARDRAILS,
            "allowedTrackRoles": list(KNOWN_TRACK_ROLES),
            "shapeExamples": [
                {key: value for key, value in archetype_to_dict(archetype).items() if key not in ("source", "reason", "trackRoles")}
                for archetype in ARCHETYPES
            ],
        },
        indent=1,
    )[:24000]
    answer = assist.ask(task, system=ARCHETYPE_ROLE, schema=ARCHETYPE_SCHEMA, expect=dict)
    proposal = validate_archetype(answer)
    if proposal is None:
        if answer is not None:
            assist.note = "model archetype did not validate; keyword archetype used"
        return fallback
    return proposal


def propose_project_identity(prompt: str | None, transcript_text: str | None, assist: llm.Assist | None) -> dict[str, Any] | None:
    """{projectId, titleHint, why} from the model, validated and made unique
    against hand-made projects; None when the model is off or answers badly."""
    if assist is None or not assist.available:
        return None
    text = (transcript_text or "").strip()
    task = json.dumps({"prompt": (prompt or "")[:4000], "transcript": text[:20000] or None}, indent=1)
    answer = assist.ask(task, system=IDENTITY_ROLE, schema=IDENTITY_SCHEMA, expect=dict)
    if not isinstance(answer, dict):
        return None
    slug = slugify(str(answer.get("projectId") or answer.get("titleHint") or ""))
    if len(slug) < 3 or slug == "song-project":
        assist.note = "model project id did not validate; the usual rules named the project"
        return None
    candidate = slug
    suffix = 2
    while (ROOT / "data" / "projects" / f"{candidate}.neon.json").exists() and not (session_dir(candidate) / "session.json").exists():
        candidate = f"{slug}-{suffix}"
        suffix += 1
    title = re.sub(r"\s+", " ", str(answer.get("titleHint") or "")).strip()[:80]
    return {
        "projectId": candidate,
        "titleHint": title or " ".join(part.capitalize() for part in candidate.split("-")),
        "why": re.sub(r"\s+", " ", str(answer.get("why") or "")).strip()[:300],
        "source": "model",
    }


def tool_assist(parent: llm.Assist | None) -> llm.Assist:
    """A fresh handle on the same model (or the same "off") for one tool the
    session drives, so that tool's `ai` block reports its own questions and
    notes rather than the session's. `absorb` folds `used` back afterwards."""
    if parent is None:
        return llm.Assist(enabled=False)
    if parent.client is None:
        child = llm.Assist(enabled=False)
        child.requested = parent.requested
        child.note = parent.note
        return child
    return llm.Assist(client=parent.client)


def absorb(parent: llm.Assist | None, child: llm.Assist) -> None:
    if parent is not None and child.used:
        parent.used = True


def ai_choice(assist: llm.Assist | None) -> str:
    """The `--ai` value that matches this Assist, for the tools run as subprocesses."""
    return "auto" if assist is not None and assist.requested else "off"


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


def build_phase_plan(archetype: Any, paths: dict[str, Path], transcript_spec: dict[str, Any] | None = None) -> list[dict[str, Any]]:
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
            "gapCount": len(fill.get("gaps") or []),
            "measuredGapCount": len(
                [g for g in (fill.get("gaps") or []) if isinstance(g, dict) and g.get("confidence") == "measured"]
            ),
        } if fill else None,
    }


def build_session(
    prompt: str,
    project_id: str,
    transcript_spec: dict[str, Any] | None = None,
    *,
    archetype: dict[str, Any] | None = None,
    assist: llm.Assist | None = None,
    title_hint: str | None = None,
) -> dict[str, Any]:
    if archetype is None:
        archetype = propose_archetype(prompt, transcript_spec, assist)
    if assist is None:
        assist = llm.Assist(enabled=False)
    paths = infer_project_paths(project_id)
    project_summary = summarize_project(paths["data_project"])
    project_name = project_summary.get("name") or title_hint or " ".join(part.capitalize() for part in project_id.split("-"))
    session = {
        "schemaVersion": 1,
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
        "projectId": project_id,
        "projectName": project_name,
        "sourcePrompt": prompt,
        "sourceMode": "transcript" if transcript_spec else "prompt",
        "normalizedIntent": archetype["normalizedIntent"],
        "archetype": {
            "id": archetype["id"],
            "label": archetype["label"],
            "referenceSummary": list(archetype["referenceSummary"]),
            "arrangementTargets": list(archetype["arrangementTargets"]),
            "soundTargets": list(archetype["soundTargets"]),
            "mixTargets": list(archetype["mixTargets"]),
            "trackRoles": list(archetype.get("trackRoles") or []),
            "source": archetype.get("source", "heuristic"),
            "reason": archetype.get("reason", ""),
        },
        "copyrightGuardrails": list(COPYRIGHT_GUARDRAILS),
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
        "iterationBacklog": [{"status": "pending", "focus": focus} for focus in archetype["iterationBacklog"]],
        "acceptanceChecks": list(archetype["acceptanceChecks"]),
        "ai": assist.report(),
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
    if archetype.get("source") == "model":
        lines.append(f"- Proposed by the model: {archetype.get('reason') or 'from the brief'}")
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
                "trackRoles": list(archetype.get("trackRoles") or [])[:6] or [role.split()[0].lower() for role in archetype.get("soundTargets", [])[:5] if role],
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


def materialize_project(project_id: str, session: dict[str, Any], transcript_spec: dict[str, Any] | None = None, *,
                        force: bool = False, assist: llm.Assist | None = None) -> dict[str, Any]:
    """Build the project files from the spec. `assist` is the session's model
    handle; None (or one that is off) means the materializer's rules alone."""
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

    child = tool_assist(assist)
    project = build_project_materialization(spec, project_id=project_id, prompt=session["sourcePrompt"], assist=child)
    absorb(assist, child)
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
    assist = llm.assist_from_args(args)
    transcript_text = None
    transcript_spec = None
    identity = None
    if args.transcript_text or args.transcript_file or args.transcript_stdin:
        transcript_text = read_transcript(args)
    if not args.project_id:
        if transcript_text is not None or args.prompt:
            identity = propose_project_identity(args.prompt, transcript_text, assist)
    proposed_id = identity["projectId"] if identity else None
    title_hint = identity["titleHint"] if identity else None
    if transcript_text is not None:
        seed_project_id = infer_project_id(args.prompt or transcript_text, args.project_id, proposed_id=proposed_id)
        # The same model handle (or the same "off") goes to every tool init
        # drives, so --ai off is honoured end to end and each tool's ai block
        # says what it did. Cached answers make the second analysis free.
        ingest_assist = tool_assist(assist)
        transcript_spec = analyze_transcript(transcript_text, project_id=seed_project_id, prompt=args.prompt, assist=ingest_assist)
        prompt = resolve_init_prompt(args, transcript_spec=transcript_spec)
        project_id = infer_project_id(prompt or transcript_text, args.project_id, proposed_id=proposed_id)
        if project_id != seed_project_id:
            ingest_assist = tool_assist(assist)
            transcript_spec = analyze_transcript(transcript_text, project_id=project_id, prompt=prompt, assist=ingest_assist)
        absorb(assist, ingest_assist)
        if title_hint and not transcript_spec.get("titleHint"):
            transcript_spec["titleHint"] = title_hint
        if not args.no_fill_blanks:
            fill_assist = tool_assist(assist)
            transcript_spec = fill_in_blanks(transcript_spec, prompt=prompt, assist=fill_assist)
            absorb(assist, fill_assist)
    else:
        prompt = resolve_init_prompt(args)
        project_id = infer_project_id(prompt, args.project_id, proposed_id=proposed_id)
    archetype = propose_archetype(prompt, transcript_spec, assist)
    session = build_session(prompt, project_id, transcript_spec=transcript_spec, archetype=archetype, assist=assist, title_hint=title_hint)
    if identity:
        session["projectIdentity"] = identity
    write_session_files(project_id, session)
    if transcript_text is not None and transcript_spec is not None:
        paths = session_paths(project_id)
        paths["transcript"].write_text(transcript_text.strip() + "\n", encoding="utf-8")
        paths["transcript_spec_json"].write_text(json.dumps(transcript_spec, indent=2) + "\n", encoding="utf-8")
        paths["transcript_spec_md"].write_text(render_transcript_markdown(transcript_spec) + "\n", encoding="utf-8")
        paths["fill_in_blanks_md"].write_text(render_fill_in_blanks_markdown(transcript_spec), encoding="utf-8")
    materialize_result = None
    if transcript_spec is not None and not args.no_materialize:
        materialize_result = materialize_project(project_id, session, transcript_spec=transcript_spec, force=args.force_materialize, assist=assist)
        session = build_session(prompt, project_id, transcript_spec=transcript_spec, archetype=archetype, assist=assist, title_hint=title_hint)
        if identity:
            session["projectIdentity"] = identity
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
    ai_report = session.get("ai") or {}
    lane = session["archetype"]
    print(f"Lane: {lane['label']} ({lane.get('source', 'heuristic')}); ai: {'used' if ai_report.get('used') else 'not used'}{' - ' + ai_report['note'] if ai_report.get('note') else ''}")
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


# ---------------------------------------------------------------------------
# The iterate loop. With the model off, `iterate` appends a note and advances
# the archetype backlog, exactly as before. With the model on it reads the
# latest sound check, the fidelity report, the spec and the log, asks for one
# concrete next step, applies it through the existing tools, re-renders,
# re-checks, and keeps going while the score improves.
# ---------------------------------------------------------------------------

class LoopError(Exception):
    """A tool the loop drives failed. The message is what it said."""


def run_tool(args: list[Any], timeout: int = 900, *, ai: str = "auto") -> tuple[int, str, str]:
    """Run one of the tools as a subprocess. `ai` is the caller's --ai choice:
    "off" switches the model off in the child's environment too, whether or
    not the tool takes the flag itself."""
    env = dict(os.environ)
    if ai == "off":
        env["NEON_AI"] = "off"
    proc = subprocess.run(
        [sys.executable, *[str(item) for item in args]],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    return proc.returncode, proc.stdout, proc.stderr


def parse_json_output(text: str) -> dict[str, Any]:
    """The JSON a tool printed: the whole output, else its last line."""
    stripped = text.strip()
    try:
        value = json.loads(stripped)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    for line in reversed(stripped.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    return value
            except json.JSONDecodeError:
                continue
    raise LoopError(f"tool printed no JSON: {stripped[-300:]}")


def project_path_for(session: dict[str, Any]) -> Path:
    return ROOT / session["workspace"]["dataProject"]


def renderer_path_for(session: dict[str, Any]) -> Path | None:
    materialization = session.get("materialization") or {}
    candidate = materialization.get("renderer") or session.get("workspace", {}).get("generator")
    return (ROOT / candidate) if candidate else None


def renderer_is_generated(path: Path | None) -> bool:
    """True when the renderer was written by project_materializer from the
    spec, so a spec edit plus re-materialize actually changes the render.
    Hand-written renderers ignore the spec and must not be overwritten."""
    if path is None or not path.exists():
        return False
    try:
        head = path.read_text(encoding="utf-8")[:6000]
    except OSError:
        return False
    return "TRANSCRIPT_SPEC_PATH" in head and "SECTION_PLAN" in head


def run_sound_check(project_id: str, session: dict[str, Any], *, ai: str = "auto") -> dict[str, Any]:
    """The measured sound check for the project as it is on disk."""
    code, out, err = run_tool(
        [TOOLS / "does_this_sound_good.py", "--root", ROOT, "--project", project_path_for(session), "--format", "json"],
        timeout=600,
        ai=ai,
    )
    if code != 0:
        raise LoopError(f"sound check failed (exit {code}): {(err or out).strip()[-400:]}")
    return parse_json_output(out)


def run_fidelity(project_id: str, session: dict[str, Any], *, ai: str = "auto") -> dict[str, Any] | None:
    transcript = session.get("transcript")
    if not transcript:
        return None
    spec_path = ROOT / transcript["specPath"]
    if not spec_path.exists():
        return None
    code, out, err = run_tool(
        [TOOLS / "transcript_fidelity.py", "--root", ROOT, "--project", project_path_for(session), "--spec", spec_path, "--format", "json"],
        timeout=600,
        ai=ai,
    )
    if code != 0:
        return {"ok": False, "score": None, "summary": f"fidelity check failed (exit {code}): {(err or out).strip()[-300:]}", "claims": [], "nextActions": []}
    return parse_json_output(out)


def apply_change_request(project_id: str, session: dict[str, Any], request: str, *, ai: str = "auto") -> dict[str, Any]:
    """Run describe_change on the project; write it back when it produced edits.
    `ai` is the round's --ai choice: describe_change may use the model too
    (its own second call, to place the words the grammar cannot), and its
    `ai` block comes back in the result so the iteration entry logs it."""
    project_path = project_path_for(session)
    output = session_paths(project_id)["base"] / "iterate_change.neon.json"
    code, out, err = run_tool(
        [TOOLS / "describe_change.py", "--root", ROOT, "--project", project_path, "--request", request, "--output", output, "--format", "json", "--ai", ai],
        timeout=600,
        ai=ai,
    )
    if code != 0:
        raise LoopError(f"describe_change failed (exit {code}): {(err or out).strip()[-400:]}")
    report = parse_json_output(out)
    edits = report.get("edits") or []
    applied = bool(edits) and output.exists()
    if applied:
        shutil.copyfile(output, project_path)
    if output.exists():
        output.unlink()
    return {
        "applied": applied,
        "understood": report.get("understood"),
        "edits": [{"title": edit.get("title"), "detail": edit.get("detail"), "section": edit.get("section")} for edit in edits if isinstance(edit, dict)][:12],
        "unresolved": list(report.get("unresolved") or [])[:6],
        "ai": report.get("ai"),
        "aiChoice": ai,
    }


def apply_tactic(project_id: str, session: dict[str, Any], feature_id: str, params: dict[str, Any] | None) -> dict[str, Any]:
    """Apply one DAW-agent tactic with validated parameters. The agent's own
    model is off here: the loop already made the decision."""
    project_path = project_path_for(session)
    base = session_paths(project_id)["base"]
    output = base / "iterate_tactic.neon.json"
    params_path = base / "iterate_tactic_params.json"
    params_path.write_text(json.dumps({feature_id: params or {}}), encoding="utf-8")
    code, out, err = run_tool(
        [
            TOOLS / "daw_agent.py", "--root", ROOT, "--ai", "off", "apply",
            "--project", project_path, "--output", output,
            "--feature", feature_id, "--params-json", params_path,
            "--max-actions", "1", "--format", "json",
        ],
        timeout=600,
    )
    params_path.unlink(missing_ok=True)
    if code != 0:
        output.unlink(missing_ok=True)
        raise LoopError(f"daw_agent failed (exit {code}): {(err or out).strip()[-400:]}")
    report = parse_json_output(out)
    actions = report.get("actions") or []
    applied = any(action.get("changed") for action in actions) and output.exists()
    if applied:
        shutil.copyfile(output, project_path)
    output.unlink(missing_ok=True)
    return {
        "applied": applied,
        "summary": report.get("summary"),
        "actions": [{"featureId": a.get("featureId"), "changed": a.get("changed"), "messages": a.get("messages")} for a in actions],
        "selectionNotes": report.get("selectionNotes") or [],
    }


def apply_spec_decision(project_id: str, session: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    """Edit one spec section, re-materialize the project and renderer, and
    re-render the stems. Only reachable when the renderer is generated."""
    paths = session_paths(project_id)
    spec = load_json(paths["transcript_spec_json"])
    if not spec:
        raise LoopError("no transcript spec to edit")
    section = next((item for item in spec.get("sections") or [] if isinstance(item, dict) and item.get("id") == decision["sectionId"]), None)
    if section is None:
        raise LoopError(f"section {decision['sectionId']} is not in the spec")
    changes: list[str] = []
    techniques = [str(item) for item in (section.get("techniques") or [])]
    for technique in decision.get("addTechniques") or []:
        if technique not in techniques:
            techniques.append(technique)
            changes.append(f"added technique {technique}")
    for technique in decision.get("removeTechniques") or []:
        if technique in techniques:
            techniques.remove(technique)
            changes.append(f"removed technique {technique}")
    section["techniques"] = techniques
    if decision.get("bars") is not None and int(decision["bars"]) != section.get("bars"):
        changes.append(f"bars {section.get('bars')} -> {int(decision['bars'])}")
        section["bars"] = int(decision["bars"])
    if not changes:
        return {"applied": False, "changes": []}
    paths["transcript_spec_json"].write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    paths["transcript_spec_md"].write_text(render_transcript_markdown(spec) + "\n", encoding="utf-8")
    paths["fill_in_blanks_md"].write_text(render_fill_in_blanks_markdown(spec), encoding="utf-8")
    materialize_project(project_id, session, transcript_spec=spec, force=True)
    render = run_renderer(project_id, session)
    return {"applied": True, "section": decision["sectionId"], "changes": changes, "render": render}


def run_renderer(project_id: str, session: dict[str, Any]) -> dict[str, Any]:
    renderer = renderer_path_for(session)
    if renderer is None or not renderer.exists():
        raise LoopError("no renderer to run")
    code, out, err = run_tool([renderer], timeout=1800)
    if code != 0:
        raise LoopError(f"renderer failed (exit {code}): {(err or out).strip()[-400:]}")
    return {"ok": True, "tail": out.strip().splitlines()[-3:]}


def rerender_mix(project_id: str, session: dict[str, Any]) -> dict[str, Any]:
    """Refresh the full mix from the stems and the project's current levels."""
    output = ROOT / session["workspace"]["fullMix"]
    output.parent.mkdir(parents=True, exist_ok=True)
    code, out, err = run_tool(
        [TOOLS / "render_mixdown.py", "--root", ROOT, "--project", project_path_for(session), "--output", output],
        timeout=900,
    )
    if code != 0:
        raise LoopError(f"render_mixdown failed (exit {code}): {(err or out).strip()[-400:]}")
    try:
        return parse_json_output(out)
    except LoopError:
        return {"ok": True}


class FileSnapshot:
    """Copies of the files a round may touch, so a round that does not improve
    the score is undone completely."""

    def __init__(self, paths: list[Path]) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="songlab-iterate-"))
        self.entries: list[tuple[Path, Path | None]] = []
        seen: set[Path] = set()
        for index, path in enumerate(paths):
            if path in seen:
                continue
            seen.add(path)
            if path.exists() and path.is_file():
                saved = self.tmp / f"{index}-{path.name}"
                shutil.copy2(path, saved)
                self.entries.append((path, saved))
            else:
                self.entries.append((path, None))

    def restore(self) -> None:
        for path, saved in self.entries:
            if saved is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(saved, path)
            elif path.exists():
                path.unlink()

    def cleanup(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)


def round_paths(project_id: str, session: dict[str, Any], kind: str) -> list[Path]:
    paths = session_paths(project_id)
    workspace = session["workspace"]
    stem = stemify(project_id)
    touched = [
        ROOT / workspace["dataProject"],
        ROOT / workspace["factoryProject"],
        ROOT / workspace["fullMix"],
        paths["base"] / "last_sound_check.json",
    ]
    if kind == "spec_decision":
        touched += [
            paths["transcript_spec_json"],
            paths["transcript_spec_md"],
            paths["fill_in_blanks_md"],
            paths["project_summary_md"],
        ]
        renderer = renderer_path_for(session)
        if renderer is not None:
            touched.append(renderer)
        touched += sorted((ROOT / "exports").glob(f"{stem}_*.wav")) if (ROOT / "exports").exists() else []
        touched += sorted((ROOT / "midi").glob(f"{stem}_*.mid")) if (ROOT / "midi").exists() else []
    return touched


def read_iterations(project_id: str, limit: int = 8) -> list[dict[str, Any]]:
    path = session_paths(project_id)["iterations"]
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records[-limit:]


def loop_state(project_id: str, session: dict[str, Any], *, use_cached_check: bool, ai: str = "auto") -> dict[str, Any]:
    """Everything a round looks at: the project, the spec, the sound check
    (last_sound_check.json when present and allowed, else a fresh run), the
    fidelity report, and the log."""
    paths = session_paths(project_id)
    project = load_json(project_path_for(session)) or {}
    spec = load_json(paths["transcript_spec_json"]) if session.get("transcript") else None
    cached = paths["base"] / "last_sound_check.json"
    check = load_json(cached) if use_cached_check and cached.exists() else None
    check_source = "last_sound_check.json"
    if not check or not isinstance(check.get("verdict"), dict):
        check = run_sound_check(project_id, session, ai=ai)
        check_source = "does_this_sound_good"
        paths["base"].mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps(check) + "\n", encoding="utf-8")
    fidelity = run_fidelity(project_id, session, ai=ai) if spec else None
    renderer = renderer_path_for(session)
    return {
        "project": project,
        "spec": spec,
        "soundCheck": check,
        "soundCheckSource": check_source,
        "fidelity": fidelity,
        "iterations": read_iterations(project_id),
        "specEditable": bool(spec) and renderer_is_generated(renderer),
        "rendererGenerated": renderer_is_generated(renderer),
    }


def score_of(state: dict[str, Any]) -> dict[str, Any]:
    verdict = (state.get("soundCheck") or {}).get("verdict") or {}
    fidelity = state.get("fidelity") or {}
    sound = verdict.get("score")
    fid = fidelity.get("score") if isinstance(fidelity, dict) else None
    return {
        "sound": int(sound) if isinstance(sound, (int, float)) else None,
        "fidelity": int(fid) if isinstance(fid, (int, float)) else None,
    }


def improved(before: dict[str, Any], after: dict[str, Any]) -> bool:
    """Better means a higher sound-check score, or the same score with a higher
    fidelity score. Anything else is not an improvement."""
    b_sound, a_sound = before.get("sound") or 0, after.get("sound") or 0
    if a_sound != b_sound:
        return a_sound > b_sound
    return (after.get("fidelity") or 0) > (before.get("fidelity") or 0)


PLAN_ROLE = (
    "You run one round of an improvement loop on a Neon Studio song project. You see the measured sound check "
    "(score 0-100, issues, next actions, per-track levels), the transcript-fidelity report when the song was built "
    "from a description (which stated claims the render does not match), the spec, the project's tracks and sections, "
    "and the log of earlier rounds with their before/after scores. Propose exactly ONE next step the tools can apply, "
    "with why and the effect you expect on the scores. Kinds:\n"
    "- change_request: a plain-words request the change grammar understands. Use the given intents (louder/quieter, "
    "brighter/darker, wider/narrower, more space/drier, harder/softer, faster/slower, mute/bring back, longer/shorter, "
    "up an octave/down an octave, more energy, add hats/riser/sub/clap/pad), a track name or role from the track list, "
    "and optionally a section such as 'in the drop' or 'in the second drop'. One clause per request, like the examples.\n"
    "- tactic: a DAW-agent tactic id from the catalog, with parameters inside its schema and a trackId from the project.\n"
    "- spec_decision (only when allowed): a change to one spec section - add or remove techniques from the allowed list, "
    "or set its bar count - which re-materializes and re-renders the whole song.\n"
    "Prefer the smallest change that addresses the highest-severity measured issue or the most musically important "
    "fidelity miss. Never repeat a step the log shows was rejected. Never invent tracks, sections, tactics, or numbers "
    "outside the given ranges. If no step is likely to raise the scores, answer stop=true and say why."
)

PLAN_SCHEMA = {
    "stop": False,
    "why": "one or two sentences: what the evidence says and why this step",
    "expectedEffect": "what should change in the sound-check or fidelity result",
    "action": {
        "kind": "change_request | tactic | spec_decision",
        "request": "for change_request: the plain-words request",
        "featureId": "for tactic: a catalog id",
        "params": {"...": "for tactic: parameters from that tactic's schema"},
        "sectionId": "for spec_decision: a spec section id",
        "addTechniques": ["for spec_decision"],
        "removeTechniques": ["for spec_decision"],
        "bars": "for spec_decision: integer or null",
    },
}


def change_vocabulary(project: dict[str, Any]) -> dict[str, Any]:
    intents: list[str] = []
    for entry in getattr(_describe_change, "INTENT_PATTERNS", []) or []:
        try:
            name = entry[0]
        except (TypeError, IndexError):
            continue
        if name not in intents:
            intents.append(str(name))
    tracks = project.get("snapshot", {}).get("tracks", []) if isinstance(project.get("snapshot"), dict) else []
    sections: list[str] = []
    if _describe_change is not None and tracks:
        try:
            sections = [section.label for section in _describe_change.project_sections(project)]
        except Exception:
            sections = []
    return {
        "intents": intents or ["gain", "tone", "width", "space", "hard", "bounce", "tempo", "length", "pitch", "mute", "add", "energy"],
        "trackNames": [str(track.get("name") or track.get("id")) for track in tracks if isinstance(track, dict)],
        "sections": sections,
        "examples": list(getattr(_describe_change, "SUGGESTIONS", []) or [])[:10],
    }


def compact_check(check: dict[str, Any], limit_tracks: int = 14) -> dict[str, Any]:
    metrics = check.get("metrics") if isinstance(check.get("metrics"), dict) else {}
    return {
        "verdict": check.get("verdict"),
        "metrics": {key: metrics[key] for key in list(metrics)[:20]},
        "issues": (check.get("issues") or [])[:8],
        "strengths": (check.get("strengths") or [])[:4],
        "nextActions": (check.get("nextActions") or [])[:6],
        "trackReports": [
            {key: item.get(key) for key in ("id", "name", "rmsDb", "peakDb", "gain", "pan")}
            for item in (check.get("trackReports") or [])[:limit_tracks] if isinstance(item, dict)
        ],
    }


def compact_fidelity(report: dict[str, Any] | None, limit_claims: int = 12) -> dict[str, Any] | None:
    if not report:
        return None
    misses = [
        {"id": claim.get("id"), "area": claim.get("area"), "claim": str(claim.get("claim") or "")[:160], "status": claim.get("status"), "evidence": str(claim.get("evidence") or "")[:200]}
        for claim in (report.get("claims") or [])
        if isinstance(claim, dict) and claim.get("status") in ("missing", "contradicted")
    ]
    return {
        "score": report.get("score"),
        "summary": report.get("summary"),
        "nextActions": [str(item)[:240] for item in (report.get("nextActions") or [])[:8]],
        "unmatchedClaims": misses[:limit_claims],
    }


def compact_spec(spec: dict[str, Any] | None) -> dict[str, Any] | None:
    if not spec:
        return None
    fill = spec.get("fillInBlanks") or {}
    return {
        "tempoHint": spec.get("tempoHint"),
        "keyHints": spec.get("keyHints"),
        "styleLane": fill.get("styleLane"),
        "sections": [
            {
                "id": section.get("id"),
                "type": section.get("type"),
                "label": section.get("label"),
                "bars": section.get("bars"),
                "techniques": list(section.get("techniques") or [])[:8],
                "trackRoles": list(section.get("trackRoles") or [])[:8],
            }
            for section in (spec.get("sections") or [])[:12] if isinstance(section, dict)
        ],
        "gaps": [
            {"id": gap.get("id"), "confidence": gap.get("confidence"), "step": str(gap.get("step") or "")[:140]}
            for gap in (fill.get("gaps") or [])[:8] if isinstance(gap, dict)
        ],
    }


def compact_log(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for record in records:
        entry: dict[str, Any] = {"timestamp": record.get("timestamp"), "note": str(record.get("note") or "")[:240]}
        if record.get("action"):
            entry["action"] = {key: value for key, value in record["action"].items() if key in ("kind", "request", "featureId", "sectionId", "reason")}
            entry["before"] = record.get("before")
            entry["after"] = record.get("after")
            entry["kept"] = record.get("kept")
        elif record.get("result"):
            entry["result"] = str(record.get("result"))[:240]
        out.append(entry)
    return out


def round_context(state: dict[str, Any], session: dict[str, Any], person_note: str | None) -> str:
    """The planning prompt, kept under ~24k characters by shedding detail."""
    project = state["project"]
    snapshot = project.get("snapshot", {}) if isinstance(project.get("snapshot"), dict) else {}
    context: dict[str, Any] = {
        "project": {
            "id": project.get("id"),
            "name": project.get("name"),
            "description": str(project.get("description") or "")[:500],
            "bpm": snapshot.get("bpm"),
            "keyCenter": project.get("keyCenter"),
            "tracks": [
                {
                    "id": track.get("id"),
                    "name": track.get("name"),
                    "instrument": track.get("instrument"),
                    "gain": track.get("gain"),
                    "pan": track.get("pan"),
                    "effects": [str(effect.get("name")) for effect in (track.get("effects") or []) if isinstance(effect, dict)][:6],
                }
                for track in (snapshot.get("tracks") or []) if isinstance(track, dict)
            ][:16],
            "automationLanes": [
                {"trackId": lane.get("trackId"), "parameter": lane.get("parameter")}
                for lane in (snapshot.get("automationLanes") or []) if isinstance(lane, dict)
            ][:12],
        },
        "goal": {
            "normalizedIntent": session.get("normalizedIntent"),
            "mixTargets": (session.get("archetype") or {}).get("mixTargets"),
            "backlog": [item.get("focus") for item in (session.get("iterationBacklog") or []) if item.get("status") != "done"][:6],
        },
        "personNote": person_note,
        "soundCheck": compact_check(state["soundCheck"]),
        "fidelity": compact_fidelity(state.get("fidelity")),
        "spec": compact_spec(state.get("spec")),
        "log": compact_log(state.get("iterations") or []),
        "whatTheCheckHears": (
            "The sound check mixes the rendered stems using each track's gain, pan and mute from the project file; "
            "effect and automation edits are recorded in the project but only heard after a re-render. "
            + ("A spec_decision re-renders the whole song, so techniques it adds are heard."
               if state.get("specEditable") else
               "This project's renderer is hand-written, so only level, pan and mute changes are audible to the check this round.")
        ),
        "allowed": {
            "change_request": change_vocabulary(project),
            "tactic": daw_agent.catalog_summary(),
            "spec_decision": (
                {"sectionIds": [section.get("id") for section in (state.get("spec") or {}).get("sections") or [] if isinstance(section, dict)], "techniques": list(KNOWN_TECHNIQUES)}
                if state.get("specEditable") else "not available for this project"
            ),
        },
    }
    text = json.dumps(context, indent=1)
    if len(text) > 24000 and context["fidelity"]:
        context["fidelity"]["unmatchedClaims"] = context["fidelity"]["unmatchedClaims"][:4]
        text = json.dumps(context, indent=1)
    if len(text) > 24000:
        context["soundCheck"]["trackReports"] = context["soundCheck"]["trackReports"][:6]
        context["allowed"]["tactic"] = [{key: item[key] for key in ("id", "title", "summary")} for item in context["allowed"]["tactic"]]
        text = json.dumps(context, indent=1)
    if len(text) > 24000:
        context["log"] = context["log"][-3:]
        context["spec"] = None
        text = json.dumps(context, indent=1)
    return text[:24000]


def validate_decision(answer: Any, state: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    """The model's round as something the tools can apply, or None with the
    reasons it was rejected."""
    notes: list[str] = []
    if not isinstance(answer, dict):
        return None, ["model answer was not an object"]
    why = re.sub(r"\s+", " ", str(answer.get("why") or "")).strip()[:600]
    expected = re.sub(r"\s+", " ", str(answer.get("expectedEffect") or "")).strip()[:300]
    if answer.get("stop") is True:
        return {"stop": True, "why": why or "the model saw nothing likely to raise the score", "expectedEffect": expected}, notes
    action = answer.get("action")
    if not isinstance(action, dict):
        return None, ["no action in the model answer"]
    kind = str(action.get("kind") or "").strip()
    decision: dict[str, Any] = {"stop": False, "kind": kind, "why": why, "expectedEffect": expected}
    if kind == "change_request":
        request = re.sub(r"\s+", " ", str(action.get("request") or "")).strip()[:300]
        if not request:
            return None, ["change_request without a request"]
        decision["request"] = request
        return decision, notes
    if kind == "tactic":
        feature_id = str(action.get("featureId") or "").strip()
        if feature_id not in {feature.id for feature in daw_agent.CATALOG}:
            return None, [f"unknown tactic {feature_id!r}"]
        params, param_notes = daw_agent.validate_params(feature_id, action.get("params"), state.get("project"))
        notes.extend(param_notes)
        decision["featureId"] = feature_id
        decision["params"] = params
        return decision, notes
    if kind == "spec_decision":
        if not state.get("specEditable"):
            return None, ["spec_decision is not available for this project (hand-written renderer or no spec)"]
        spec = state.get("spec") or {}
        section_ids = {str(section.get("id")) for section in spec.get("sections") or [] if isinstance(section, dict)}
        section_id = str(action.get("sectionId") or "").strip()
        if section_id not in section_ids:
            return None, [f"unknown section {section_id!r}"]
        section = next(item for item in spec["sections"] if str(item.get("id")) == section_id)
        add = [str(item).strip().lower() for item in (action.get("addTechniques") or []) if str(item).strip()]
        remove = [str(item).strip().lower() for item in (action.get("removeTechniques") or []) if str(item).strip()]
        dropped = [item for item in add if item not in KNOWN_TECHNIQUES]
        if dropped:
            notes.append(f"dropped unknown techniques {dropped}")
        add = [item for item in add if item in KNOWN_TECHNIQUES and item not in (section.get("techniques") or [])]
        remove = [item for item in remove if item in (section.get("techniques") or [])]
        bars = action.get("bars")
        bars_value = None
        if isinstance(bars, (int, float)) and not isinstance(bars, bool):
            bars_value = max(2, min(64, int(round(bars))))
            if bars_value == section.get("bars"):
                bars_value = None
        if not add and not remove and bars_value is None:
            return None, ["spec_decision changes nothing that exists"]
        decision.update({"sectionId": section_id, "addTechniques": add, "removeTechniques": remove, "bars": bars_value})
        return decision, notes
    return None, [f"unknown action kind {kind!r}"]


def plan_round(state: dict[str, Any], session: dict[str, Any], assist: llm.Assist, person_note: str | None) -> tuple[dict[str, Any] | None, list[str]]:
    task = round_context(state, session, person_note)
    answer = assist.ask(task, system=PLAN_ROLE, schema=PLAN_SCHEMA, thinking="high", max_tokens=2048, expect=dict)
    if answer is None:
        return None, [assist.note or "no answer"]
    decision, notes = validate_decision(answer, state)
    if decision is None:
        assist.note = "model plan did not validate: " + "; ".join(notes)
    return decision, notes


def apply_decision(project_id: str, session: dict[str, Any], decision: dict[str, Any], *, ai: str = "auto") -> dict[str, Any]:
    kind = decision["kind"]
    if kind == "change_request":
        result = apply_change_request(project_id, session, decision["request"], ai=ai)
    elif kind == "tactic":
        result = apply_tactic(project_id, session, decision["featureId"], decision.get("params"))
    else:
        result = apply_spec_decision(project_id, session, decision)
    if result.get("applied") and kind != "spec_decision":
        result["render"] = rerender_mix(project_id, session)
    return result


def describe_decision(decision: dict[str, Any]) -> str:
    kind = decision["kind"]
    if kind == "change_request":
        return f"change request: {decision['request']}"
    if kind == "tactic":
        return f"tactic {decision['featureId']}" + (f" {json.dumps(decision['params'])}" if decision.get("params") else "")
    parts = []
    if decision.get("addTechniques"):
        parts.append("add " + ", ".join(decision["addTechniques"]))
    if decision.get("removeTechniques"):
        parts.append("remove " + ", ".join(decision["removeTechniques"]))
    if decision.get("bars") is not None:
        parts.append(f"bars={decision['bars']}")
    return f"spec {decision['sectionId']}: " + "; ".join(parts)


def append_iteration(project_id: str, record: dict[str, Any]) -> None:
    paths = session_paths(project_id)
    paths["base"].mkdir(parents=True, exist_ok=True)
    with paths["iterations"].open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def legacy_iterate(project_id: str, session: dict[str, Any], note: str, result: str | None) -> None:
    """What `iterate` has always done: log the note, advance the backlog."""
    record = {
        "timestamp": now_iso(),
        "note": note,
        "result": result or "",
    }
    append_iteration(project_id, record)
    if session.get("iterationBacklog"):
        for item in session["iterationBacklog"]:
            if item.get("status") == "pending":
                item["status"] = "in_progress"
                break
    write_session_files(project_id, session)


def run_iterate_loop(project_id: str, session: dict[str, Any], assist: llm.Assist, rounds: int, note: str | None, result: str | None) -> dict[str, Any]:
    """Plan, apply, re-render, re-check; keep going while the score improves.
    The round's --ai choice goes to every tool it drives as a subprocess."""
    ai = ai_choice(assist)
    state = loop_state(project_id, session, use_cached_check=True, ai=ai)
    start_score = score_of(state)
    before = dict(start_score)
    records: list[dict[str, Any]] = []
    stopped = ""
    for number in range(1, max(1, rounds) + 1):
        decision, notes = plan_round(state, session, assist, note if number == 1 else None)
        if decision is None:
            stopped = "model gave no usable plan: " + "; ".join(notes)
            if number == 1 and note:
                legacy_iterate(project_id, session, note, result)
                stopped += " (logged the note as before)"
            break
        if decision.get("stop"):
            stopped = "model stopped: " + decision["why"]
            records.append({
                "timestamp": now_iso(),
                "note": f"[ai round {number}] stop: {decision['why']}",
                "result": f"score {before['sound']} / fidelity {before['fidelity']}; no step proposed",
                "round": number,
                "action": {"kind": "stop", "source": "model", "reason": decision["why"], "expectedEffect": decision.get("expectedEffect")},
                "before": before,
                "after": before,
                "kept": False,
                "ai": assist.report(),
            })
            append_iteration(project_id, records[-1])
            break
        snapshot_files = FileSnapshot(round_paths(project_id, session, decision["kind"]))
        record: dict[str, Any] = {
            "timestamp": now_iso(),
            "round": number,
            "action": {
                key: value for key, value in decision.items() if key not in ("stop", "why", "expectedEffect")
            },
            "before": before,
            "validationNotes": notes,
            "ai": assist.report(),
        }
        record["action"].update({"source": "model", "reason": decision["why"], "expectedEffect": decision.get("expectedEffect")})
        try:
            applied = apply_decision(project_id, session, decision, ai=ai)
        except (LoopError, subprocess.TimeoutExpired) as error:
            snapshot_files.restore()
            snapshot_files.cleanup()
            record.update({
                "note": f"[ai round {number}] {decision['why']}",
                "result": f"{describe_decision(decision)} failed: {error}",
                "after": before,
                "kept": False,
                "applied": {"applied": False, "error": str(error)},
            })
            append_iteration(project_id, record)
            records.append(record)
            stopped = f"round {number} failed: {error}"
            break
        if not applied.get("applied"):
            snapshot_files.restore()
            snapshot_files.cleanup()
            record.update({
                "note": f"[ai round {number}] {decision['why']}",
                "result": f"{describe_decision(decision)} changed nothing" + (": " + "; ".join(applied.get("unresolved") or []) if applied.get("unresolved") else ""),
                "after": before,
                "kept": False,
                "applied": applied,
            })
            append_iteration(project_id, record)
            records.append(record)
            stopped = f"round {number} changed nothing in the project"
            break
        state = loop_state(project_id, session, use_cached_check=False, ai=ai)
        after = score_of(state)
        kept = improved(before, after)
        if not kept:
            snapshot_files.restore()
        snapshot_files.cleanup()
        record.update({
            "note": f"[ai round {number}] {decision['why']}",
            "result": f"{describe_decision(decision)}: sound {before['sound']} -> {after['sound']}, fidelity {before['fidelity']} -> {after['fidelity']} ({'kept' if kept else 'reverted'})",
            "after": after,
            "kept": kept,
            "applied": applied,
        })
        if decision["kind"] == "change_request" and applied.get("ai") is not None:
            # describe_change made its own model call inside this round: say so.
            record["toolAi"] = {"describe_change": applied["ai"]}
        append_iteration(project_id, record)
        records.append(record)
        session.setdefault("iterationBacklog", []).append({
            "status": "done" if kept else "rejected",
            "focus": f"{describe_decision(decision)} - {decision['why']}"[:240],
            "source": "model",
        })
        if not kept:
            stopped = f"round {number} did not improve the score (sound {before['sound']} -> {after['sound']}, fidelity {before['fidelity']} -> {after['fidelity']}); reverted"
            state = loop_state(project_id, session, use_cached_check=True, ai=ai)
            break
        before = after
    else:
        stopped = f"reached --rounds {rounds}"
    write_session_files(project_id, session)
    return {
        "projectId": project_id,
        "rounds": records,
        "stopped": stopped,
        "scoreBefore": start_score,
        "scoreAfter": before,
        "ai": assist.report(),
    }


def command_iterate(args: argparse.Namespace) -> int:
    project_id = infer_project_id(args.prompt or "", args.project_id)
    session = read_session(project_id)
    paths = session_paths(project_id)
    paths["base"].mkdir(parents=True, exist_ok=True)
    assist = llm.assist_from_args(args)
    if not assist.available:
        if not args.note:
            raise SystemExit(f"--note is required when the model is off ({assist.note}).")
        legacy_iterate(project_id, session, args.note, args.result)
        print(f"Logged iteration for {project_id}")
        return 0
    payload = run_iterate_loop(project_id, session, assist, rounds=args.rounds, note=args.note, result=args.result)
    print(json.dumps(payload, indent=2))
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
    assist = llm.assist_from_args(args)
    result = materialize_project(project_id, session, force=args.force, assist=assist)
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
        "ai": result["project"].get("ai") or assist.report(),
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
    llm.add_ai_argument(init_cmd)
    init_cmd.set_defaults(func=command_init)

    status_cmd = subparsers.add_parser("status", help="Show current songlab and project status.")
    status_cmd.add_argument("--project-id", help="Project id, e.g. neon-solitude.")
    status_cmd.add_argument("--prompt", help="Optional prompt to infer the project id.")
    status_cmd.set_defaults(func=command_status)

    iterate_cmd = subparsers.add_parser("iterate", help="Append an iteration note; with a model key, plan and apply the next rounds.")
    iterate_cmd.add_argument("--project-id", help="Project id, e.g. neon-solitude.")
    iterate_cmd.add_argument("--prompt", help="Optional prompt to infer the project id.")
    iterate_cmd.add_argument("--note", help="What changed this pass (required when the model is off; context for it when on).")
    iterate_cmd.add_argument("--result", help="What improved or what is still missing.")
    iterate_cmd.add_argument("--rounds", type=int, default=3, help="With the model on: how many plan/apply/check rounds to run at most (default 3).")
    llm.add_ai_argument(iterate_cmd)
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
    llm.add_ai_argument(materialize_cmd)
    materialize_cmd.set_defaults(func=command_materialize)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
