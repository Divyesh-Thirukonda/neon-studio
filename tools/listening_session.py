#!/usr/bin/env python3
"""A human sound check.

``does_this_sound_good.py`` measures a render. This tool asks a person about
it. The app plays each musical section of a project and puts two or three
plain questions to whoever is listening — no DAW vocabulary, just "does the
drop land?" — and their answers come back here to be turned into concrete
production steps.

Those steps go into the spec's ``fillInBlanks.gaps`` with confidence
``"human"``. They outrank anything the filler merely inferred, because a
person saying "the drop felt empty" is evidence, and they sit beside (but
never overwrite) what the sound check actually measured.

Two subcommands:

    listening_session.py --root ROOT --project PATH questions [--format json|markdown]
    listening_session.py --root ROOT --project PATH --spec SPEC apply --answers ANSWERS.json
        [--project-id ID] [--format json|markdown]

``questions`` derives the musical sections from the project's recipe and clip
spans and returns the questions to ask for each. ``apply`` takes the answers,
maps them to rubric requirements, merges them into the spec, writes the spec
back, and (when a project id is given) logs an iteration note via songlab.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fill_in_blanks import merge_gaps  # noqa: E402
from production_rubric import requirement_by_id  # noqa: E402


TOOLS_DIR = Path(__file__).resolve().parent
BEATS_PER_BAR = 4


# ---------------------------------------------------------------------------
# The question bank.
#
# Every question is worded for someone who has never opened a DAW. The
# ``maps`` say which rubric requirement each answer is evidence for; an answer
# that maps to nothing ("just right") is still worth recording, because it
# tells the next pass what NOT to touch.
# ---------------------------------------------------------------------------

QUESTION_BANK: dict[str, dict[str, Any]] = {
    "fullness": {
        "text": "How full does this part feel?",
        "options": ["too empty", "just right", "too busy"],
        "maps": {
            "too empty": ["roles_need_content", "texture_bed"],
            "just right": [],
            "too busy": ["break_subtraction", "width_budget"],
        },
    },
    "hum": {
        "text": "Can you hum the main tune here?",
        "options": ["easily", "sort of", "not really"],
        "maps": {
            "easily": [],
            "sort of": [],
            "not really": ["hook_carrier_declaration", "hook_contour", "hook_recurrence"],
        },
    },
    "lands": {
        "text": "Does the drop land?",
        "options": ["yes", "it arrives but doesn't land", "it's flat"],
        "maps": {
            "yes": [],
            "it arrives but doesn't land": ["pre_drop_gap", "boundary_transition_fx"],
            "it's flat": ["duck_parameters", "gain_ladder", "low_end_ownership"],
        },
    },
    "tension": {
        "text": "Does the tension rise?",
        "options": ["yes", "a little", "no"],
        "maps": {
            "yes": [],
            "a little": ["build_stepped_ramp", "boundary_transition_fx", "automation_targets_a_lane"],
            "no": ["build_stepped_ramp", "boundary_transition_fx", "automation_targets_a_lane"],
        },
    },
    "rest": {
        "text": "Does this feel like a rest?",
        "options": ["yes", "not different enough", "too long"],
        "maps": {
            "yes": [],
            "not different enough": ["break_subtraction", "contrast_before_repeat"],
            "too long": ["explicit_section_lengths"],
        },
    },
    "compare": {
        "text": "Compared to the first drop, how does this one feel?",
        "options": ["bigger", "the same", "smaller"],
        "maps": {
            "bigger": [],
            "the same": ["repeat_section_variation", "hook_octave_double"],
            "smaller": ["gain_ladder", "section_energy_arc"],
        },
    },
    "ends": {
        "text": "Does it end, or just stop?",
        "options": ["it ends", "it just stops"],
        "maps": {
            "it ends": [],
            "it just stops": ["outro_resolution"],
        },
    },
    "muddy_harsh": {
        "text": "Anything muddy or harsh?",
        "options": ["no", "muddy", "harsh"],
        "maps": {
            "no": [],
            "muddy": ["hpf_ladder", "low_end_ownership"],
            "harsh": ["fx_return_discipline"],
        },
    },
}

# Which two or three questions each kind of section gets. The order is the
# order the app should ask them in: the section-specific question first, so
# the listener answers it while the impression is fresh.
QUESTIONS_BY_SECTION_TYPE: dict[str, list[str]] = {
    "intro": ["fullness", "muddy_harsh"],
    "verse": ["fullness", "hum", "muddy_harsh"],
    "pre_build": ["tension", "fullness"],
    "build": ["tension", "fullness", "muddy_harsh"],
    "drop": ["lands", "fullness", "hum"],
    "second_drop": ["compare", "fullness", "muddy_harsh"],
    "break": ["rest", "hum"],
    "outro": ["ends", "fullness"],
}
DEFAULT_QUESTIONS = ["fullness", "hum", "muddy_harsh"]

# Free-text answers get a light keyword pass. Anything a person writes is kept
# as a note regardless; this only decides whether it ALSO becomes a step.
FREE_TEXT_KEYWORDS: list[tuple[tuple[str, ...], list[str]]] = [
    (("muddy", "mud", "boomy", "woolly", "wooly"), ["hpf_ladder", "low_end_ownership"]),
    (("harsh", "piercing", "shrill", "brittle", "too bright"), ["fx_return_discipline"]),
    (("empty", "thin", "sparse", "hollow", "missing"), ["roles_need_content", "texture_bed"]),
    (("busy", "cluttered", "crowded", "too much going on"), ["break_subtraction", "width_budget"]),
    (("boring", "repetitive", "samey", "same thing"), ["repeat_section_variation", "per_bar_drum_variation"]),
    (("too quiet", "louder", "too loud", "volume"), ["gain_ladder"]),
    (("bass", "sub", "low end", "kick"), ["low_end_ownership", "duck_parameters"]),
    (("tune", "melody", "hook", "catchy"), ["hook_carrier_declaration", "hook_contour"]),
    (("just stops", "abrupt", "ending"), ["outro_resolution"]),
    (("doesn't land", "doesnt land", "no impact", "doesn't hit", "doesnt hit"), ["pre_drop_gap", "boundary_transition_fx"]),
    (("tension", "rise", "ramp"), ["build_stepped_ramp"]),
    (("narrow", "wide", "stereo"), ["width_budget", "mono_below_crossover"]),
    (("too long", "too short", "drags"), ["explicit_section_lengths"]),
]


# ---------------------------------------------------------------------------
# Deriving musical sections from a project.
# ---------------------------------------------------------------------------

# Recipe section names and clip names both use everyday words. Each keyword
# maps to the section type the question bank knows. "hook", "harmony", "mix"
# and the like are recipe headings, not places in the song, so they are not
# here on purpose.
SECTION_KEYWORDS: list[tuple[str, str]] = [
    ("pre[- ]?build", "pre_build"),
    ("pre[- ]?intro", "intro"),
    ("second drop", "second_drop"),
    ("intro", "intro"),
    ("verse", "verse"),
    ("build", "build"),
    ("drop", "drop"),
    ("break", "break"),
    ("chorus", "drop"),
    ("bridge", "break"),
    ("outro", "outro"),
]

# Canonical order, used only when nothing in the project says where a section
# sits in time.
CANONICAL_ORDER = ["intro", "verse", "pre_build", "build", "drop", "break", "second_drop", "outro"]


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "section"


def classify_name(name: str) -> Optional[tuple[str, Optional[int]]]:
    """Read a section type and an ordinal out of a name like "Drop 2".

    Returns ``(type, ordinal)`` or None when the name is not a musical
    section. A second "drop" is promoted to ``second_drop`` because the
    question bank has a specific question for it.
    """
    lowered = name.lower()
    for pattern, section_type in SECTION_KEYWORDS:
        match = re.search(r"\b" + pattern + r"\b\s*(\d+)?", lowered)
        if not match:
            continue
        ordinal = int(match.group(1)) if match.group(1) else None
        if section_type == "drop" and ordinal is not None and ordinal >= 2:
            section_type = "second_drop"
        if section_type == "second_drop":
            ordinal = ordinal or 2
        return section_type, ordinal
    return None


def clip_spans(project: dict[str, Any]) -> list[tuple[str, Optional[int], int, int]]:
    """Every clip in the project as (type, ordinal, startBar, endBar)."""
    snapshot = project.get("snapshot") if isinstance(project.get("snapshot"), dict) else {}
    spans: list[tuple[str, Optional[int], int, int]] = []
    for track in snapshot.get("tracks") or []:
        if not isinstance(track, dict):
            continue
        for clip in track.get("clips") or []:
            if not isinstance(clip, dict):
                continue
            classified = classify_name(str(clip.get("name") or ""))
            if classified is None:
                continue
            try:
                start = int(clip.get("startBar") or 0)
                bars = max(int(clip.get("bars") or 0), 0)
            except (TypeError, ValueError):
                continue
            spans.append((classified[0], classified[1], start, start + bars))
    return spans


def span_for(section_type: str, ordinal: Optional[int], spans: list[tuple[str, Optional[int], int, int]]) -> Optional[tuple[int, int]]:
    """The bar range the clips give a section.

    Numbered clips ("Build 2 roll") are trusted first. Unnumbered ones
    ("Build clap roll") are ambiguous once a song has two builds, so they only
    count when nothing numbered exists, or when the section itself is the
    first (or only) of its kind.
    """
    same_type = [s for s in spans if s[0] == section_type]
    if not same_type:
        return None
    if ordinal is not None:
        numbered = [s for s in same_type if s[1] == ordinal]
        if not numbered and ordinal == 1:
            numbered = [s for s in same_type if s[1] is None]
    else:
        numbered = [s for s in same_type if s[1] is None or s[1] == 1]
        if not numbered:
            numbered = same_type
    if not numbered:
        return None
    start = min(s[2] for s in numbered)
    end = max(s[3] for s in numbered)
    return start, end


def derive_sections(project: dict[str, Any]) -> list[dict[str, Any]]:
    """The musical sections of a project, in bar order.

    Recipe items name the sections; clip spans say where they are. When the
    recipe has no musical sections, the clip names alone are used. When there
    are no clips either, the whole project is one section.
    """
    snapshot = project.get("snapshot") if isinstance(project.get("snapshot"), dict) else {}
    spans = clip_spans(project)
    sections: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    def add(section_id: str, label: str, section_type: str, ordinal: Optional[int], recipe_index: int) -> None:
        if section_id in seen_ids:
            return
        seen_ids.add(section_id)
        span = span_for(section_type, ordinal, spans)
        sections.append(
            {
                "id": section_id,
                "label": label,
                "type": section_type,
                "startBar": span[0] if span else None,
                "bars": (span[1] - span[0]) if span else None,
                "_order": recipe_index,
            }
        )

    for index, item in enumerate(snapshot.get("recipe") or []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("section") or "").strip()
        classified = classify_name(name)
        if classified is None:
            continue
        section_id = str(item.get("id") or slugify(name))
        add(section_id, name, classified[0], classified[1], index)

    if not sections:
        # No recipe to go on: let the clip names define the sections.
        # "Build 1 roll" and "Build clap roll" are the same build: an
        # unnumbered clip and a "1" both mean the first of their kind, and a
        # second drop is already its own type.
        keyed: dict[tuple[str, Optional[int]], int] = {}
        for index, (section_type, ordinal, _start, _end) in enumerate(spans):
            key_ordinal = ordinal if ordinal not in (None, 1) and section_type != "second_drop" else None
            key = (section_type, key_ordinal)
            if key in keyed:
                continue
            keyed[key] = index
            label = section_type.replace("_", " ").title()
            if key_ordinal:
                label = f"{label} {key_ordinal}"
            add(slugify(label), label, section_type, ordinal, index)

    if not sections:
        end = 0
        for track in snapshot.get("tracks") or []:
            for clip in (track.get("clips") or []) if isinstance(track, dict) else []:
                if isinstance(clip, dict):
                    end = max(end, int(clip.get("startBar") or 0) + int(clip.get("bars") or 0))
        if end == 0:
            end = int(snapshot.get("loopEndBar") or 8)
        sections.append({"id": "song", "label": "Whole song", "type": "song", "startBar": 0, "bars": end, "_order": 0})

    # Sections the clips could not place go where the canonical flow puts
    # them, after everything that has a real bar number. Stable sort keeps
    # recipe order for ties.
    def sort_key(section: dict[str, Any]) -> tuple[int, int, int]:
        if section["startBar"] is not None:
            return (0, int(section["startBar"]), section["_order"])
        canonical = CANONICAL_ORDER.index(section["type"]) if section["type"] in CANONICAL_ORDER else len(CANONICAL_ORDER)
        return (1, canonical, section["_order"])

    sections.sort(key=sort_key)
    for section in sections:
        section.pop("_order", None)
    return sections


# ---------------------------------------------------------------------------
# Questions.
# ---------------------------------------------------------------------------

def questions_for_section(section: dict[str, Any]) -> list[dict[str, Any]]:
    keys = QUESTIONS_BY_SECTION_TYPE.get(str(section.get("type") or ""), DEFAULT_QUESTIONS)
    questions: list[dict[str, Any]] = []
    for key in keys:
        bank = QUESTION_BANK[key]
        questions.append(
            {
                "id": f"{section['id']}.{key}",
                "text": bank["text"],
                "options": list(bank["options"]),
                "maps": {option: list(bank["maps"].get(option, [])) for option in bank["options"]},
            }
        )
    questions.append({"id": f"{section['id']}.notes", "text": "Anything else?", "freeText": True})
    return questions


def build_questions(project: dict[str, Any]) -> dict[str, Any]:
    sections = []
    for section in derive_sections(project):
        sections.append(
            {
                "id": section["id"],
                "label": section["label"],
                "type": section["type"],
                "startBar": section["startBar"],
                "bars": section["bars"],
                "questions": questions_for_section(section),
            }
        )
    return {"ok": True, "project": str(project.get("name") or project.get("id") or ""), "sections": sections}


def render_questions_markdown(payload: dict[str, Any]) -> str:
    lines = [f"# Listening Session: {payload.get('project') or 'project'}", ""]
    for section in payload.get("sections") or []:
        where = ""
        if section.get("startBar") is not None:
            where = f" (bars {section['startBar']}–{int(section['startBar']) + int(section['bars'] or 0)})"
        lines.append(f"## {section['label']}{where}")
        lines.append("")
        for question in section.get("questions") or []:
            if question.get("freeText"):
                lines.append(f"- `{question['id']}` {question['text']} _(free text)_")
            else:
                lines.append(f"- `{question['id']}` {question['text']} — {' | '.join(question['options'])}")
        lines.append("")
    return "\n".join(lines).rstrip()


# ---------------------------------------------------------------------------
# Applying answers.
# ---------------------------------------------------------------------------

def question_index(payload: dict[str, Any]) -> dict[str, tuple[dict[str, Any], dict[str, Any]]]:
    index: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for section in payload.get("sections") or []:
        for question in section.get("questions") or []:
            index[question["id"]] = (section, question)
    return index


def match_free_text(text: str) -> list[str]:
    lowered = text.lower()
    ids: list[str] = []
    for keywords, requirement_ids in FREE_TEXT_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            for requirement_id in requirement_ids:
                if requirement_id not in ids:
                    ids.append(requirement_id)
    return ids


def human_gap(requirement_id: str, section_id: str, evidence: str) -> Optional[dict[str, Any]]:
    requirement = requirement_by_id(requirement_id)
    if requirement is None:
        return None
    return {
        "id": requirement.id,
        "requirementId": requirement.id,
        "label": requirement.label,
        "why": requirement.why,
        "step": requirement.step,
        "soundCheckArea": requirement.area,
        "areas": list(requirement.areas),
        "roles": list(requirement.roles),
        "section": section_id,
        "sections": [section_id],
        "confidence": "human",
        "source": "listening-session",
        "evidence": evidence,
    }


def steps_from_answers(payload: dict[str, Any], answers: list[Any]) -> dict[str, Any]:
    """Turn answers into human-confidence gap dicts.

    One gap per requirement: a second answer that points at the same
    requirement adds its evidence and section rather than a duplicate, since
    the spec keys gaps by id anyway.
    """
    index = question_index(payload)
    gaps: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    notes: list[dict[str, str]] = []
    warnings: list[str] = []
    answered = 0

    def record(requirement_ids: list[str], section_id: str, evidence: str) -> None:
        for requirement_id in requirement_ids:
            existing = gaps.get(requirement_id)
            if existing is not None:
                if evidence not in existing["evidence"]:
                    existing["evidence"] = f"{existing['evidence']} {evidence}"
                if section_id not in existing["sections"]:
                    existing["sections"].append(section_id)
                continue
            gap = human_gap(requirement_id, section_id, evidence)
            if gap is None:
                warnings.append(f"The question bank names an unknown requirement: {requirement_id}")
                continue
            gaps[requirement_id] = gap
            order.append(requirement_id)

    for answer in answers:
        if not isinstance(answer, dict):
            warnings.append(f"Ignored an answer that is not an object: {answer!r}")
            continue
        question_id = str(answer.get("questionId") or "")
        entry = index.get(question_id)
        if entry is None:
            warnings.append(f"Ignored an answer to an unknown question: {question_id or '(blank)'}")
            continue
        section, question = entry
        if question.get("freeText"):
            text = str(answer.get("text") or "").strip()
            if not text:
                warnings.append(f"Ignored an empty note for {question_id}")
                continue
            answered += 1
            notes.append({"section": section["id"], "label": section["label"], "text": text})
            record(match_free_text(text), section["id"], f"You wrote about {section['label']}: '{text}'")
            continue
        option = str(answer.get("option") or "").strip()
        if option not in question["options"]:
            warnings.append(f"Ignored an answer to {question_id} that is not one of its options: {option or '(blank)'}")
            continue
        answered += 1
        evidence = f"You said {section['label']} '{option}' when asked '{question['text']}'"
        record(list(question["maps"].get(option, [])), section["id"], evidence)

    return {
        "steps": [gaps[key] for key in order],
        "notes": notes,
        "warnings": warnings,
        "answered": answered,
    }


def apply_answers(
    project: dict[str, Any],
    spec: dict[str, Any],
    answers_payload: dict[str, Any],
) -> dict[str, Any]:
    """Merge the answers into ``spec`` in place and describe what changed."""
    payload = build_questions(project)
    answers = answers_payload.get("answers") if isinstance(answers_payload, dict) else None
    if not isinstance(answers, list):
        raise ValueError("ANSWERS.json must be an object with an \"answers\" list.")
    result = steps_from_answers(payload, answers)

    fill = spec.get("fillInBlanks")
    if not isinstance(fill, dict):
        fill = {}
        spec["fillInBlanks"] = fill
    before = [dict(g) for g in (fill.get("gaps") or []) if isinstance(g, dict)]
    merged = merge_gaps(before, result["steps"])
    fill["gaps"] = merged

    # A step "lands" when the merged spec now carries our version of it. A
    # measured finding with the same id stays put, and that is the right call:
    # the person confirmed what the checker already heard.
    landed = [g for g in merged if g.get("confidence") == "human" and g.get("source") == "listening-session"
              and g.get("id") in {s["id"] for s in result["steps"]}]
    confirmed = [s["id"] for s in result["steps"] if s["id"] not in {g["id"] for g in landed}]

    notes_text = [n["text"] for n in result["notes"]]
    if not isinstance(spec.get("listeningNotes"), list):
        spec["listeningNotes"] = []
    for note in result["notes"]:
        if note not in spec["listeningNotes"]:
            spec["listeningNotes"].append(note)

    def _plural(count: int, word: str) -> str:
        return f"{count} {word}{'' if count == 1 else 's'}"

    summary = f"{_plural(len(landed), 'step')} added from {_plural(result['answered'], 'answer')}"
    if confirmed:
        summary += f" ({len(confirmed)} already measured)"
    if notes_text:
        summary += f", {_plural(len(notes_text), 'note')} kept"
    iteration_note = f"Listening session: {_plural(result['answered'], 'answer')}, {_plural(len(landed), 'step')} added"
    return {
        "ok": True,
        "steps": result["steps"],
        "added": [g["id"] for g in landed],
        "confirmedMeasured": confirmed,
        "notes": notes_text,
        "warnings": result["warnings"],
        "iterationNote": iteration_note,
        "summary": summary,
    }


def log_iteration(project_id: str, note: str, result_text: str) -> Optional[str]:
    """Append the note through songlab.py so it lands in iterations.jsonl.

    Returns a warning string when songlab refuses (no session for that id);
    a missing log line must never fail the listening session itself.
    """
    command = [
        sys.executable,
        str(TOOLS_DIR / "songlab.py"),
        "iterate",
        "--project-id",
        project_id,
        "--note",
        note,
        "--result",
        result_text,
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return f"Could not log the iteration note: {exc}"
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip().splitlines()
        return "Could not log the iteration note: " + (detail[-1] if detail else f"songlab exited {completed.returncode}")
    return None


def render_apply_markdown(payload: dict[str, Any]) -> str:
    lines = ["# Listening Session", "", payload.get("summary", ""), ""]
    if payload.get("steps"):
        lines.extend(["## Steps", ""])
        for step in payload["steps"]:
            lines.append(f"- **{step['label']}** — {step['step']}")
            lines.append(f"  - {step['evidence']}")
        lines.append("")
    if payload.get("notes"):
        lines.extend(["## Notes", ""])
        lines.extend(f"- {note}" for note in payload["notes"])
        lines.append("")
    if payload.get("warnings"):
        lines.extend(["## Warnings", ""])
        lines.extend(f"- {warning}" for warning in payload["warnings"])
        lines.append("")
    lines.append(f"Iteration note: {payload.get('iterationNote', '')}")
    return "\n".join(lines).rstrip()


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------

def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_project_path(root: Path, project: Optional[str], project_id: Optional[str]) -> Path:
    if project:
        return Path(project).expanduser().resolve()
    if not project_id:
        raise FileNotFoundError("Provide --project or --project-id.")
    for candidate in (
        root / "data" / "projects" / f"{project_id}.neon.json",
        root / "factory" / "projects" / f"{project_id}.neon.json",
    ):
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"No project found for {project_id}.")


def resolve_spec_path(root: Path, spec: Optional[str], project_id: Optional[str]) -> Path:
    if spec:
        return Path(spec).expanduser().resolve()
    if not project_id:
        raise FileNotFoundError("Provide --spec or --project-id so the answers have a spec to land in.")
    return root / "songlab" / "projects" / project_id / "transcript_spec.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ask a person whether a Neon Studio project sounds good, and turn the answers into steps.")
    parser.add_argument("--root", default=".", help="Workspace root (holds data/projects and songlab/projects).")
    parser.add_argument("--project", help="Path to a .neon.json file.")
    parser.add_argument("--project-id", help="Project id, e.g. neon-alone. Also used to log the iteration note.")
    parser.add_argument("--spec", help="Path to transcript_spec.json (apply only).")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    subparsers = parser.add_subparsers(dest="command", required=True)
    questions_cmd = subparsers.add_parser("questions", help="List the questions to ask, per section.")
    apply_cmd = subparsers.add_parser("apply", help="Turn answers into production steps in the spec.")
    apply_cmd.add_argument("--answers", required=True, help="Path to ANSWERS.json: {\"answers\": [{\"questionId\", \"option\" | \"text\"}]}")
    # ``--format`` is accepted on either side of the subcommand, because the
    # app writes it last and people write it first. SUPPRESS keeps the
    # subparser from clobbering the top-level value when it is not repeated.
    for sub in (questions_cmd, apply_cmd):
        sub.add_argument("--format", choices=("json", "markdown"), default=argparse.SUPPRESS)
    return parser


def emit(payload: dict[str, Any], fmt: str, markdown: str) -> None:
    if fmt == "markdown":
        print(markdown)
    else:
        # One object on the last line: that is what the app and MCP server parse.
        print(json.dumps(payload, separators=(",", ":")))


def fail(message: str, fmt: str) -> int:
    if fmt == "markdown":
        print(f"Error: {message}")
    else:
        print(json.dumps({"ok": False, "error": message}))
    return 1


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    try:
        project_path = resolve_project_path(root, args.project, args.project_id)
        project = read_json(project_path)
    except (OSError, ValueError) as exc:
        return fail(f"Could not read the project: {exc}", args.format)

    if args.command == "questions":
        payload = build_questions(project)
        emit(payload, args.format, render_questions_markdown(payload))
        return 0

    try:
        spec_path = resolve_spec_path(root, args.spec, args.project_id)
        spec = read_json(spec_path)
        answers_payload = read_json(Path(args.answers).expanduser().resolve())
    except (OSError, ValueError) as exc:
        return fail(f"Could not read the inputs: {exc}", args.format)
    try:
        payload = apply_answers(project, spec, answers_payload)
    except ValueError as exc:
        return fail(str(exc), args.format)
    try:
        spec_path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        return fail(f"Could not write the spec: {exc}", args.format)
    payload["specPath"] = str(spec_path)

    if args.project_id:
        warning = log_iteration(args.project_id, payload["iterationNote"], payload["summary"])
        payload["iterationLogged"] = warning is None
        if warning:
            payload["warnings"].append(warning)
    else:
        payload["iterationLogged"] = False

    emit(payload, args.format, render_apply_markdown(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
