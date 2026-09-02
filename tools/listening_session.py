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

Where a language model helps (see docs/ai.md)
    With a key present, the questions are written for *this* song: the model
    reads the section type, the instruments playing in it, what the sound
    check already flagged and what the listener said last time, and rephrases
    the bank's questions to match ("Does the drop hit after the clap roll?").
    The question keys, ids, options and answer maps are always the bank's, so
    answers still map to requirements deterministically. On ``apply`` the
    model reads the free-text notes into requirement ids (keeping the
    person's own words as the quote), writes a why for each step that names
    this song and this answer, and adds a short listener summary. With no
    key, ``--ai off`` or ``NEON_AI=off``, every one of those falls back to the
    tables below and the output is exactly what it was before.
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
from llm import Assist, add_ai_argument, assist_from_args  # noqa: E402
from production_rubric import REQUIREMENTS, requirement_by_id  # noqa: E402


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

# What each question key is for, in the words the model is given when it
# chooses and rephrases questions. The key is the schema; the text is not.
QUESTION_KEY_MEANING: dict[str, str] = {
    "fullness": "how full or sparse the section feels (too empty / just right / too busy)",
    "hum": "whether the main tune is memorable enough to hum here",
    "lands": "whether the drop arrives with impact (only for a drop or chorus)",
    "tension": "whether the tension rises through the section (builds, pre-builds)",
    "rest": "whether the section feels like a rest from the drop (breaks, bridges)",
    "compare": "how a second drop compares to the first one (only for a second drop)",
    "ends": "whether the song ends or just stops (outros)",
    "muddy_harsh": "whether anything sounds muddy (boomy, woolly) or harsh (piercing, brittle)",
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
NOTES_PROMPT = "Anything else?"

# Keys whose answers only make sense for one kind of section. The model may
# choose any other key anywhere; these it may only put where the table would.
KEY_ONLY_FOR: dict[str, tuple[str, ...]] = {
    "lands": ("drop", "second_drop", "song"),
    "compare": ("second_drop",),
    "ends": ("outro", "song"),
}

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
# What the model is told about the song. Small and structured: ids, names,
# kinds, the gaps already on file, the notes from last time. Never audio,
# never a measurement it could restate as its own.
# ---------------------------------------------------------------------------

MAX_CONTEXT_CHARS = 24000
SECTIONS_PER_CALL = 25
MAX_QUESTION_CHARS = 160
MAX_WHY_CHARS = 480
MAX_SUMMARY_CHARS = 600
MAX_ITERATION_NOTE_CHARS = 200

# Words a listener should never be asked about. The bank avoids them; a
# rephrased question that brings one back is replaced by the bank's text.
JARGON = ("sidechain", "hpf", "eq", "automation", "lfo", "compressor", "stereo",
          "transient", "lufs", "khz", "hz", "db", "saturation", "reverb tail")

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def _text(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _has_jargon(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(r"\b" + re.escape(word) + r"\b", lowered) for word in JARGON)


def _numbers_grounded(text: str, allowed: str) -> bool:
    """True when every number in ``text`` also appears in ``allowed``.

    The model writes prose around measurements; it never gets to invent one.
    """
    permitted = set(_NUMBER.findall(allowed))
    return all(number in permitted for number in _NUMBER.findall(text))


def _quote_in(quote: str, text: str) -> bool:
    """Case- and whitespace-insensitive substring check for evidence quotes."""
    needle = re.sub(r"\s+", " ", quote.strip().lower())
    haystack = re.sub(r"\s+", " ", text.lower())
    return bool(needle) and needle in haystack


def _chunks(items: list[Any], size: int, text_of: Any = None) -> list[list[Any]]:
    """Split a batch so no call carries more than ~24k characters of text."""
    chunks: list[list[Any]] = []
    current: list[Any] = []
    current_chars = 0
    for item in items:
        chars = len(text_of(item)) if text_of else 0
        if current and (len(current) >= size or current_chars + chars > MAX_CONTEXT_CHARS):
            chunks.append(current)
            current, current_chars = [], 0
        current.append(item)
        current_chars += chars
    if current:
        chunks.append(current)
    return chunks


def song_context(project: dict[str, Any], spec: Optional[dict[str, Any]]) -> dict[str, Any]:
    snapshot = project.get("snapshot") if isinstance(project.get("snapshot"), dict) else {}
    fill = spec.get("fillInBlanks") if isinstance(spec, dict) and isinstance(spec.get("fillInBlanks"), dict) else {}
    tracks = []
    for track in snapshot.get("tracks") or []:
        if not isinstance(track, dict):
            continue
        tracks.append({
            "id": str(track.get("id") or ""),
            "name": str(track.get("name") or ""),
            "kind": str(track.get("kind") or ""),
            "instrument": str(track.get("instrument") or ""),
        })
    context = {
        "name": str(project.get("name") or project.get("id") or ""),
        "key": str(project.get("keyCenter") or ""),
        "bpm": snapshot.get("bpm"),
        "styleLane": str(fill.get("styleLane") or ""),
        "description": _text(project.get("description"), 400),
        "tracks": tracks,
    }
    return context


def _section_matches(section: dict[str, Any], name: str) -> bool:
    """Does a clip or recipe name ("Build 2 roll") belong to this section?"""
    classified = classify_name(name)
    if classified is None or classified[0] != section.get("type"):
        return False
    own = classify_name(str(section.get("label") or ""))
    own_ordinal = own[1] if own else None
    if classified[1] is None or own_ordinal is None:
        return True
    return classified[1] == own_ordinal


def section_gaps(spec: Optional[dict[str, Any]], section_id: str) -> list[dict[str, Any]]:
    """The gaps already on file for one section, as the model is shown them."""
    if not isinstance(spec, dict):
        return []
    fill = spec.get("fillInBlanks") if isinstance(spec.get("fillInBlanks"), dict) else {}
    gaps: list[dict[str, Any]] = []
    for gap in fill.get("gaps") or []:
        if not isinstance(gap, dict):
            continue
        sections = gap.get("sections") if isinstance(gap.get("sections"), list) else []
        if gap.get("section") == section_id or section_id in sections:
            gaps.append({
                "id": str(gap.get("id") or ""),
                "label": str(gap.get("label") or ""),
                "confidence": str(gap.get("confidence") or ""),
                "evidence": _text(gap.get("evidence"), 200),
            })
    return gaps[:8]


def section_context(section: dict[str, Any], project: dict[str, Any], spec: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Everything known about one section that a question could refer to."""
    snapshot = project.get("snapshot") if isinstance(project.get("snapshot"), dict) else {}
    start = section.get("startBar")
    end = None if start is None else int(start) + int(section.get("bars") or 0)

    playing: list[dict[str, str]] = []
    for track in snapshot.get("tracks") or []:
        if not isinstance(track, dict):
            continue
        clip_names: list[str] = []
        for clip in track.get("clips") or []:
            if not isinstance(clip, dict):
                continue
            try:
                clip_start = int(clip.get("startBar") or 0)
                clip_end = clip_start + max(int(clip.get("bars") or 0), 0)
            except (TypeError, ValueError):
                continue
            overlaps = start is not None and end is not None and clip_start < end and clip_end > int(start)
            if overlaps or (start is None and _section_matches(section, str(clip.get("name") or ""))):
                clip_names.append(str(clip.get("name") or ""))
        if clip_names:
            playing.append({
                "track": str(track.get("name") or track.get("id") or ""),
                "instrument": str(track.get("instrument") or ""),
                "clips": ", ".join(clip_names[:4]),
            })

    recipe: list[str] = []
    for item in snapshot.get("recipe") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("id") or "") == section["id"] or _section_matches(section, str(item.get("section") or "")):
            line = " — ".join(part for part in (str(item.get("label") or ""), _text(item.get("detail"), 200)) if part)
            if line:
                recipe.append(line)

    notes: list[str] = []
    if isinstance(spec, dict):
        for note in spec.get("listeningNotes") or []:
            if isinstance(note, dict) and note.get("section") == section["id"] and note.get("text"):
                notes.append(_text(note.get("text"), 300))

    return {
        "id": section["id"],
        "label": section["label"],
        "type": section["type"],
        "startBar": start,
        "bars": section.get("bars"),
        "playing": playing[:12],
        "recipe": recipe[:4],
        "existingGaps": section_gaps(spec, section["id"]),
        "previousNotes": notes[-4:],
    }


def song_wide_gaps(spec: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
    """Gaps with no section of their own — the sound check's findings mostly."""
    if not isinstance(spec, dict):
        return []
    fill = spec.get("fillInBlanks") if isinstance(spec.get("fillInBlanks"), dict) else {}
    out = []
    for gap in fill.get("gaps") or []:
        if not isinstance(gap, dict) or gap.get("section") or gap.get("sections"):
            continue
        if str(gap.get("confidence") or "") not in ("measured", "human"):
            continue
        out.append({
            "id": str(gap.get("id") or ""),
            "label": str(gap.get("label") or ""),
            "confidence": str(gap.get("confidence") or ""),
            "evidence": _text(gap.get("evidence"), 200),
        })
    return out[:10]


# ---------------------------------------------------------------------------
# Questions.
# ---------------------------------------------------------------------------

def bank_question(section_id: str, key: str) -> dict[str, Any]:
    bank = QUESTION_BANK[key]
    return {
        "id": f"{section_id}.{key}",
        "text": bank["text"],
        "options": list(bank["options"]),
        "maps": {option: list(bank["maps"].get(option, [])) for option in bank["options"]},
    }


def questions_for_section(section: dict[str, Any]) -> list[dict[str, Any]]:
    """The table's questions for a section: the offline path, and the fallback."""
    keys = QUESTIONS_BY_SECTION_TYPE.get(str(section.get("type") or ""), DEFAULT_QUESTIONS)
    questions = [bank_question(section["id"], key) for key in keys]
    questions.append({"id": f"{section['id']}.notes", "text": NOTES_PROMPT, "freeText": True})
    return questions


QUESTIONS_ROLE = f"""You write questions for a listening session: a person who has never opened a DAW listens to one section of an electronic song at a time and answers two or three multiple-choice questions about it.

You are given the song, the instruments playing in each section, what the recipe says the section is for, anything already flagged for that section (by a measured sound check or by the listener last time), and a fixed bank of question KEYS. For each section, choose 2 or 3 keys and write the question in plain words for THIS section: name the instruments or the moment ("after the clap roll", "the hook lead", "the filtered chords"), and when something was already flagged, ask whether it is better now. Put the most section-specific question first.

Rules:
- Use only the keys given. Never invent options; the options are fixed per key and the listener's answer must still mean what the key means.
- A key must keep its meaning: "lands" is only for a drop or chorus, "compare" only for a second drop, "ends" only for an outro, "tension" for a build or pre-build, "rest" for a break.
- Every option must read as a natural answer to your wording: for "muddy_harsh" the answers are "no", "muddy", "harsh", so ask "Does anything sound muddy or harsh?", not "clean or muddy?".
- Plain English. No studio words: no sidechain, EQ, HPF, compressor, LFO, automation, stereo, dB, Hz, transients.
- One sentence, at most {MAX_QUESTION_CHARS} characters, ending with a question mark.
- Do not mention numbers you were not given.
- Also write one short free-text prompt per section ("Anything else about the drop, like the vocal echo?"), at most {MAX_QUESTION_CHARS} characters, ending with a question mark.
- Give a short reason (under 80 characters) for each choice."""


def _questions_schema() -> dict[str, Any]:
    return {
        "sections": [
            {
                "id": "section id from the input",
                "questions": [{"key": "one of the bank keys", "text": "the question in plain words", "reason": "why this question here"}],
                "notesPrompt": "the free-text prompt",
            }
        ]
    }


def model_questions(
    sections: list[dict[str, Any]],
    project: dict[str, Any],
    spec: Optional[dict[str, Any]],
    assist: Assist,
    dropped: list[str],
) -> dict[str, dict[str, Any]]:
    """Ask the model for per-section questions; return {section id: validated answer}.

    A section missing from the answer, or answered badly, is simply absent
    here and gets the table. Everything kept has passed validation: keys
    from the bank, text without jargon, ending in a question mark.
    """
    if not assist.available or not sections:
        return {}
    song = song_context(project, spec)
    accepted: dict[str, dict[str, Any]] = {}
    contexts = [section_context(section, project, spec) for section in sections]
    bank_lines = "\n".join(
        f"- {key}: {QUESTION_KEY_MEANING[key]}. Options: {' | '.join(QUESTION_BANK[key]['options'])}. Default wording: \"{QUESTION_BANK[key]['text']}\""
        for key in QUESTION_BANK
    )
    for chunk in _chunks(contexts, SECTIONS_PER_CALL, text_of=lambda c: json.dumps(c)):
        by_id = {c["id"]: c for c in chunk}
        task = (
            "Song:\n" + json.dumps(song, ensure_ascii=False) + "\n\n"
            "Song-wide findings already on file:\n" + json.dumps(song_wide_gaps(spec), ensure_ascii=False) + "\n\n"
            "Question keys:\n" + bank_lines + "\n\n"
            "Sections, in order:\n" + json.dumps(chunk, ensure_ascii=False, indent=1)
        )
        answer = assist.ask(task, system=QUESTIONS_ROLE, schema=_questions_schema(), expect=dict, max_tokens=8192)
        if not answer:
            continue
        entries = answer.get("sections")
        if not isinstance(entries, list):
            dropped.append("questions: reply had no sections list")
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            section_id = str(entry.get("id") or "")
            if section_id not in by_id:
                dropped.append(f"questions: unknown section {section_id or '(blank)'}")
                continue
            allowed_numbers = json.dumps(by_id[section_id]) + json.dumps(song)
            questions: list[dict[str, Any]] = []
            seen: set[str] = set()
            for item in entry.get("questions") or []:
                if not isinstance(item, dict):
                    continue
                key = str(item.get("key") or "").strip()
                if key not in QUESTION_BANK:
                    dropped.append(f"questions: {section_id} asked for an unknown key {key or '(blank)'}")
                    continue
                if key not in keys_for_section_type(by_id[section_id]["type"]):
                    dropped.append(f"questions: {section_id} ({by_id[section_id]['type']}) cannot take {key}")
                    continue
                if key in seen:
                    continue
                seen.add(key)
                text = _text(item.get("text"), MAX_QUESTION_CHARS + 1)
                usable = bool(text) and len(text) <= MAX_QUESTION_CHARS and text.endswith("?") \
                    and not _has_jargon(text) and _numbers_grounded(text, allowed_numbers)
                if not usable:
                    dropped.append(f"questions: {section_id}.{key} wording rejected, bank text used")
                question = bank_question(section_id, key)
                question["source"] = "model" if usable else "bank"
                if usable:
                    question["bankText"] = QUESTION_BANK[key]["text"]
                    question["text"] = text
                    reason = _text(item.get("reason"), 120)
                    if reason:
                        question["reason"] = reason
                questions.append(question)
                if len(questions) == 3:
                    break
            if len(questions) < 2:
                dropped.append(f"questions: {section_id} got {len(questions)} usable question(s), table used")
                continue
            prompt = _text(entry.get("notesPrompt"), MAX_QUESTION_CHARS + 1)
            prompt_ok = bool(prompt) and len(prompt) <= MAX_QUESTION_CHARS and prompt.endswith("?") \
                and not _has_jargon(prompt) and _numbers_grounded(prompt, allowed_numbers)
            accepted[section_id] = {"questions": questions, "notesPrompt": prompt if prompt_ok else None}
    return accepted


def build_questions(
    project: dict[str, Any],
    spec: Optional[dict[str, Any]] = None,
    assist: Optional[Assist] = None,
) -> dict[str, Any]:
    assist = assist if assist is not None else Assist()
    dropped: list[str] = []
    derived = derive_sections(project)
    modelled = model_questions(derived, project, spec, assist, dropped)
    sections = []
    for section in derived:
        chosen = modelled.get(section["id"])
        if chosen:
            questions = list(chosen["questions"])
            notes = {"id": f"{section['id']}.notes", "text": chosen["notesPrompt"] or NOTES_PROMPT, "freeText": True}
            if chosen["notesPrompt"]:
                notes["source"] = "model"
                notes["bankText"] = NOTES_PROMPT
            questions.append(notes)
        else:
            questions = questions_for_section(section)
        sections.append(
            {
                "id": section["id"],
                "label": section["label"],
                "type": section["type"],
                "startBar": section["startBar"],
                "bars": section["bars"],
                "questions": questions,
            }
        )
    payload = {"ok": True, "project": str(project.get("name") or project.get("id") or ""), "sections": sections}
    payload["ai"] = ai_block(assist, dropped)
    return payload


def ai_block(assist: Assist, dropped: list[str]) -> dict[str, Any]:
    block = assist.report()
    if dropped:
        block["dropped"] = list(dropped)
    return block


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
    lines.append(ai_line(payload))
    return "\n".join(lines).rstrip()


def ai_line(payload: dict[str, Any]) -> str:
    ai = payload.get("ai") if isinstance(payload.get("ai"), dict) else {}
    if ai.get("used"):
        return f"AI: via {ai.get('model') or ai.get('provider')}"
    note = ai.get("note") or ""
    return f"AI: offline rules{' (' + note + ')' if note else ''}"


# ---------------------------------------------------------------------------
# Applying answers.
# ---------------------------------------------------------------------------

def keys_for_section_type(section_type: str) -> list[str]:
    """The bank keys a section of this type could be asked: every key except
    those KEY_ONLY_FOR reserves for other kinds of section. The same list
    gates the model's choices at question time and the answers at apply time."""
    return [key for key in QUESTION_BANK if key not in KEY_ONLY_FOR or section_type in KEY_ONLY_FOR[key]]


def question_index(payload: dict[str, Any]) -> dict[str, tuple[dict[str, Any], dict[str, Any]]]:
    """Every question an answer may refer to.

    The payload's own questions come first. Then the bank keys the section
    could have been asked, so an answer to a question the model chose at
    question time (say ``intro.hum``, which the table never asks) still maps
    through the bank's options and requirement ids exactly as any other -
    while ``intro.lands``, which the model could not have asked, is refused
    here just as it is there.
    """
    index: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for section in payload.get("sections") or []:
        for question in section.get("questions") or []:
            index[question["id"]] = (section, question)
        for key in keys_for_section_type(str(section.get("type") or "")):
            question_id = f"{section['id']}.{key}"
            if question_id not in index:
                index[question_id] = (section, bank_question(section["id"], key))
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


NOTES_ROLE = """You read what a listener wrote after hearing one section of an electronic song, and decide which production requirements (if any) their note is evidence for.

For each note you are given the section, what else the listener answered about it, the steps already on file for it, and the catalogue of requirement ids with what each one fixes. Return, per note:
- requirementIds: the catalogue ids the note is evidence FOR. Empty when the note is praise, neutral, or says something is fine. "the bass isn't muddy at all" is evidence for nothing. A note that wants something back ("the vocal chop is missing in the second half") is evidence for the requirement that puts content in a role.
- quote: the listener's exact words the ids rest on, copied verbatim from the note (a phrase or the whole note).
- meaning: one plain sentence saying what the listener wants changed, or that nothing needs changing.
- doNotTouch: catalogue ids the note says are already right and must be left alone.

Only use ids from the catalogue. Prefer the one or two ids that fit best over a long list."""


def _notes_schema() -> dict[str, Any]:
    return {
        "notes": [
            {
                "index": 0,
                "requirementIds": ["catalogue id"],
                "quote": "exact words from the note",
                "meaning": "one sentence",
                "doNotTouch": ["catalogue id"],
            }
        ]
    }


def catalogue() -> list[dict[str, str]]:
    return [{"id": r.id, "label": r.label, "fixes": _text(r.why, 160)} for r in REQUIREMENTS]


def read_notes(
    notes: list[dict[str, Any]],
    song: dict[str, Any],
    assist: Assist,
    dropped: list[str],
) -> list[dict[str, Any]]:
    """One reading per note: the requirement ids it is evidence for, and why.

    Each note comes in as ``{"section", "label", "type", "text", "answers",
    "existingGaps"}``. The keyword table is the reading unless the model gives
    a better one that validates: known ids, and a quote that really appears
    in the note.
    """
    readings: list[dict[str, Any]] = []
    for note in notes:
        readings.append({
            "section": note["section"],
            "text": note["text"],
            "requirementIds": match_free_text(note["text"]),
            "quote": note["text"],
            "meaning": "",
            "doNotTouch": [],
            "source": "keywords",
        })
    if not assist.available or not notes:
        return readings

    indexed = [{"index": i, **{k: v for k, v in note.items() if k != "section"}, "sectionId": note["section"]} for i, note in enumerate(notes)]
    for chunk in _chunks(indexed, SECTIONS_PER_CALL, text_of=lambda n: n["text"]):
        task = (
            "Song:\n" + json.dumps(song, ensure_ascii=False) + "\n\n"
            "Catalogue:\n" + json.dumps(catalogue(), ensure_ascii=False) + "\n\n"
            "Notes:\n" + json.dumps(chunk, ensure_ascii=False, indent=1)
        )
        answer = assist.ask(task, system=NOTES_ROLE, schema=_notes_schema(), expect=dict, max_tokens=4096)
        if not answer:
            continue
        valid_indices = {n["index"] for n in chunk}
        entries = answer.get("notes")
        if not isinstance(entries, list):
            dropped.append("notes: reply had no notes list")
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            try:
                index = int(entry.get("index"))
            except (TypeError, ValueError):
                continue
            if index not in valid_indices:
                dropped.append(f"notes: answer for a note that does not exist ({index})")
                continue
            text = notes[index]["text"]
            quote = _text(entry.get("quote"), 400)
            if not _quote_in(quote, text):
                dropped.append(f"notes: quote not found in note {index}, keywords used")
                continue
            ids: list[str] = []
            for raw in entry.get("requirementIds") or []:
                requirement_id = str(raw or "").strip()
                if requirement_by_id(requirement_id) is None:
                    dropped.append(f"notes: unknown requirement {requirement_id or '(blank)'} for note {index}")
                    continue
                if requirement_id not in ids:
                    ids.append(requirement_id)
            leave: list[str] = []
            for raw in entry.get("doNotTouch") or []:
                requirement_id = str(raw or "").strip()
                if requirement_by_id(requirement_id) is not None and requirement_id not in leave and requirement_id not in ids:
                    leave.append(requirement_id)
            readings[index].update({
                "requirementIds": ids,
                "quote": quote,
                "meaning": _text(entry.get("meaning"), 240),
                "doNotTouch": leave,
                "source": "model",
            })
    return readings


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


def steps_from_answers(
    payload: dict[str, Any],
    answers: list[Any],
    *,
    song: Optional[dict[str, Any]] = None,
    spec: Optional[dict[str, Any]] = None,
    assist: Optional[Assist] = None,
    dropped: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Turn answers into human-confidence gap dicts.

    One gap per requirement: a second answer that points at the same
    requirement adds its evidence and section rather than a duplicate, since
    the spec keys gaps by id anyway.
    """
    assist = assist if assist is not None else Assist(enabled=False)
    dropped = dropped if dropped is not None else []
    index = question_index(payload)
    gaps: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    notes: list[dict[str, str]] = []
    warnings: list[str] = []
    liked: list[str] = []
    answered = 0

    # Pass one: validate every answer, and gather the notes so they can be
    # read together (one model call for all of them, or the keyword table).
    valid: list[tuple[dict[str, Any], dict[str, Any], Any]] = []
    answers_by_section: dict[str, list[str]] = {}
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
            valid.append((section, question, text))
            continue
        option = str(answer.get("option") or "").strip()
        if option not in question["options"]:
            warnings.append(f"Ignored an answer to {question_id} that is not one of its options: {option or '(blank)'}")
            continue
        valid.append((section, question, option))
        answers_by_section.setdefault(section["id"], []).append(f"{question['text']} -> {option}")

    note_inputs: list[dict[str, Any]] = []
    for section, question, value in valid:
        if question.get("freeText"):
            existing = [g["id"] for g in section_gaps(spec, section["id"])]
            note_inputs.append({
                "section": section["id"],
                "label": section["label"],
                "type": section.get("type", ""),
                "text": value,
                "answers": answers_by_section.get(section["id"], []),
                "existingGaps": existing,
            })
    readings = read_notes(note_inputs, song or {}, assist, dropped)
    reading_iter = iter(readings)

    def record(requirement_ids: list[str], section_id: str, evidence: str, reading: Optional[dict[str, Any]] = None) -> None:
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
            if reading is not None and reading.get("source") == "model":
                gap["reading"] = {"source": "model", "quote": reading["quote"], "reason": reading["meaning"]}
            gaps[requirement_id] = gap
            order.append(requirement_id)

    # Pass two: record, in the order the answers came.
    for section, question, value in valid:
        answered += 1
        if question.get("freeText"):
            reading = next(reading_iter)
            notes.append({"section": section["id"], "label": section["label"], "text": value})
            quote = reading["quote"] if reading.get("source") == "model" else value
            record(reading["requirementIds"], section["id"], f"You wrote about {section['label']}: '{quote}'", reading)
            continue
        evidence = f"You said {section['label']} '{value}' when asked '{question['text']}'"
        ids = list(question["maps"].get(value, []))
        if not ids:
            liked.append(f"{section['label']}: '{question['text']}' -> {value}")
        record(ids, section["id"], evidence)

    return {
        "steps": [gaps[key] for key in order],
        "notes": notes,
        "readings": readings,
        "liked": liked,
        "warnings": warnings,
        "answered": answered,
    }


WHY_ROLE = """You explain production steps to the person who just listened to their own song and answered questions about it.

Each step is a requirement from a fixed catalogue, chosen because of something the listener answered. You are given the song, the listener's answers (including what they said was fine), the section each step is for, the catalogue's generic reason, and — when the sound check measured something for the same requirement — its finding. For each step write a "why" for THIS song and THIS answer: two or three sentences that start from what the listener said, name the section and the instruments involved, and say what the step will change in what they will hear next time. Do not repeat the catalogue's generic sentence; do not restate the step's instructions; never mention a number you were not given.

Also write:
- listenerSummary: two or three sentences for the listener — what they liked, what will change first, in their own terms.
- iterationNote: one line for the project log, under 160 characters, saying what this listening pass asked for."""


def _why_schema() -> dict[str, Any]:
    return {
        "steps": [{"requirementId": "id from the input", "why": "two or three sentences for this song and this answer"}],
        "listenerSummary": "two or three sentences",
        "iterationNote": "one line",
    }


def write_whys(
    steps: list[dict[str, Any]],
    result: dict[str, Any],
    song: dict[str, Any],
    spec: dict[str, Any],
    assist: Assist,
    dropped: list[str],
) -> dict[str, str]:
    """Replace each step's rubric why with one written for this song.

    Mutates the step dicts in place. Returns ``{"listenerSummary", "iterationNote"}``
    when the model gave them; empty otherwise. The rubric's why survives as
    ``rubricWhy`` and ``whySource`` says which one the reader is looking at.
    """
    for step in steps:
        step.setdefault("whySource", "rubric")
    if not assist.available or not result.get("answered"):
        return {}
    fill = spec.get("fillInBlanks") if isinstance(spec.get("fillInBlanks"), dict) else {}
    measured = {}
    for gap in fill.get("gaps") or []:
        if isinstance(gap, dict) and gap.get("confidence") == "measured" and gap.get("id"):
            measured[str(gap["id"])] = _text(gap.get("evidence") or gap.get("step"), 240)
    labels: dict[str, str] = dict(result.get("sectionLabels") or {})

    def describe(step: dict[str, Any]) -> dict[str, Any]:
        return {
            "requirementId": step["id"],
            "label": step["label"],
            "sections": [labels.get(s, s) for s in step.get("sections") or []],
            "because": step.get("evidence", ""),
            "catalogueReason": step.get("why", ""),
            "step": _text(step.get("step"), 300),
            "soundCheckMeasured": measured.get(step["id"], ""),
        }

    extras: dict[str, str] = {}
    by_id = {step["id"]: step for step in steps}
    described = [describe(step) for step in steps]
    chunks = _chunks(described, SECTIONS_PER_CALL, text_of=lambda d: json.dumps(d)) or [[]]
    for chunk_index, chunk in enumerate(chunks):
        task = (
            "Song:\n" + json.dumps(song, ensure_ascii=False) + "\n\n"
            "What the listener said was fine:\n" + json.dumps(result.get("liked") or [], ensure_ascii=False) + "\n\n"
            "What the listener wrote:\n" + json.dumps([n["text"] for n in result.get("notes") or []], ensure_ascii=False) + "\n\n"
            "Steps:\n" + json.dumps(chunk, ensure_ascii=False, indent=1)
        )
        answer = assist.ask(task, system=WHY_ROLE, schema=_why_schema(), expect=dict, max_tokens=8192)
        if not answer:
            continue
        entries = answer.get("steps")
        if not isinstance(entries, list):
            dropped.append("why: reply had no steps list")
            entries = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            requirement_id = str(entry.get("requirementId") or "")
            step = by_id.get(requirement_id)
            if step is None:
                dropped.append(f"why: unknown step {requirement_id or '(blank)'}")
                continue
            why = _text(entry.get("why"), MAX_WHY_CHARS + 1)
            allowed = json.dumps(describe(step)) + json.dumps(song)
            if not why or len(why) > MAX_WHY_CHARS or not _numbers_grounded(why, allowed):
                dropped.append(f"why: rewrite for {requirement_id} rejected, catalogue reason kept")
                continue
            if step.get("whySource") != "model":
                step["rubricWhy"] = step["why"]
            step["why"] = why
            step["whySource"] = "model"
        if chunk_index == 0:
            summary = _text(answer.get("listenerSummary"), MAX_SUMMARY_CHARS + 1)
            allowed = json.dumps(described) + json.dumps(song) + json.dumps(result.get("liked") or []) + json.dumps(result.get("notes") or [])
            if summary and len(summary) <= MAX_SUMMARY_CHARS and _numbers_grounded(summary, allowed):
                extras["listenerSummary"] = summary
            elif summary:
                dropped.append("summary: rejected")
            note = _text(answer.get("iterationNote"), MAX_ITERATION_NOTE_CHARS + 1)
            if note and len(note) <= MAX_ITERATION_NOTE_CHARS and _numbers_grounded(note, allowed):
                extras["iterationNote"] = note
            elif note:
                dropped.append("iteration note: rejected")
    return extras


def apply_answers(
    project: dict[str, Any],
    spec: dict[str, Any],
    answers_payload: dict[str, Any],
    assist: Optional[Assist] = None,
) -> dict[str, Any]:
    """Merge the answers into ``spec`` in place and describe what changed."""
    assist = assist if assist is not None else Assist()
    dropped: list[str] = []
    # The questions are rebuilt offline here: ids, options and maps are the
    # bank's either way, and the model's wording is not needed to map answers.
    payload = build_questions(project, spec, Assist(enabled=False))
    answers = answers_payload.get("answers") if isinstance(answers_payload, dict) else None
    if not isinstance(answers, list):
        raise ValueError("ANSWERS.json must be an object with an \"answers\" list.")
    song = song_context(project, spec)
    result = steps_from_answers(payload, answers, song=song, spec=spec, assist=assist, dropped=dropped)
    result["sectionLabels"] = {s["id"]: s["label"] for s in payload["sections"]}
    extras = write_whys(result["steps"], result, song, spec, assist, dropped)

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
    readings_by_note = {(r["section"], r["text"]): r for r in result["readings"]}
    for note in result["notes"]:
        entry = dict(note)
        reading = readings_by_note.get((note["section"], note["text"]))
        if reading is not None and reading.get("source") == "model":
            entry["reading"] = {"source": "model", "quote": reading["quote"], "reason": reading["meaning"],
                                "requirementIds": list(reading["requirementIds"])}
            if reading.get("doNotTouch"):
                entry["doNotTouch"] = list(reading["doNotTouch"])
        already = any(isinstance(n, dict) and n.get("section") == note["section"] and n.get("text") == note["text"]
                      for n in spec["listeningNotes"])
        if not already:
            spec["listeningNotes"].append(entry)

    def _plural(count: int, word: str) -> str:
        return f"{count} {word}{'' if count == 1 else 's'}"

    summary = f"{_plural(len(landed), 'step')} added from {_plural(result['answered'], 'answer')}"
    if confirmed:
        summary += f" ({len(confirmed)} already measured)"
    if notes_text:
        summary += f", {_plural(len(notes_text), 'note')} kept"
    iteration_note = f"Listening session: {_plural(result['answered'], 'answer')}, {_plural(len(landed), 'step')} added"
    if extras.get("iterationNote"):
        iteration_note += f" — {extras['iterationNote']}"
    out: dict[str, Any] = {
        "ok": True,
        "steps": result["steps"],
        "added": [g["id"] for g in landed],
        "confirmedMeasured": confirmed,
        "notes": notes_text,
        "noteReadings": list(result["readings"]),
        "warnings": result["warnings"],
        "iterationNote": iteration_note,
        "summary": summary,
    }
    if extras.get("listenerSummary"):
        out["listenerSummary"] = extras["listenerSummary"]
    out["ai"] = ai_block(assist, dropped)
    return out


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
    if payload.get("listenerSummary"):
        lines.extend([payload["listenerSummary"], ""])
    if payload.get("steps"):
        lines.extend(["## Steps", ""])
        for step in payload["steps"]:
            lines.append(f"- **{step['label']}** — {step['step']}")
            lines.append(f"  - {step['evidence']}")
            if step.get("whySource") == "model" and step.get("why"):
                lines.append(f"  - Why: {step['why']}")
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
    lines.append(ai_line(payload))
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


def spec_for_questions(root: Path, spec: Optional[str], project_id: Optional[str], project: dict[str, Any]) -> Optional[dict[str, Any]]:
    """The spec, if one can be found, so questions can mention what is on file.

    ``questions`` never needs a spec; the app does not pass one. So this
    looks in the usual places (``--spec``, ``--project-id``, the project's own
    id) and gives up quietly.
    """
    candidates: list[Path] = []
    if spec:
        candidates.append(Path(spec).expanduser().resolve())
    for identifier in (project_id, str(project.get("id") or "")):
        if identifier:
            candidates.append(root / "songlab" / "projects" / identifier / "transcript_spec.json")
    for candidate in candidates:
        try:
            loaded = read_json(candidate)
        except (OSError, ValueError):
            continue
        if isinstance(loaded, dict):
            return loaded
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ask a person whether a Neon Studio project sounds good, and turn the answers into steps.")
    parser.add_argument("--root", default=".", help="Workspace root (holds data/projects and songlab/projects).")
    parser.add_argument("--project", help="Path to a .neon.json file.")
    parser.add_argument("--project-id", help="Project id, e.g. neon-alone. Also used to log the iteration note.")
    parser.add_argument("--spec", help="Path to transcript_spec.json (needed by apply; optional context for questions).")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    add_ai_argument(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)
    questions_cmd = subparsers.add_parser("questions", help="List the questions to ask, per section.")
    apply_cmd = subparsers.add_parser("apply", help="Turn answers into production steps in the spec.")
    apply_cmd.add_argument("--answers", required=True, help="Path to ANSWERS.json: {\"answers\": [{\"questionId\", \"option\" | \"text\"}]}")
    # ``--format`` and ``--ai`` are accepted on either side of the subcommand,
    # because the app writes them last and people write them first. SUPPRESS
    # keeps the subparser from clobbering the top-level value when it is not
    # repeated.
    for sub in (questions_cmd, apply_cmd):
        sub.add_argument("--format", choices=("json", "markdown"), default=argparse.SUPPRESS)
        sub.add_argument("--ai", choices=("auto", "off"), default=argparse.SUPPRESS)
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
    assist = assist_from_args(args)
    try:
        project_path = resolve_project_path(root, args.project, args.project_id)
        project = read_json(project_path)
    except (OSError, ValueError) as exc:
        return fail(f"Could not read the project: {exc}", args.format)

    if args.command == "questions":
        spec = spec_for_questions(root, args.spec, args.project_id, project)
        payload = build_questions(project, spec, assist)
        emit(payload, args.format, render_questions_markdown(payload))
        return 0

    try:
        spec_path = resolve_spec_path(root, args.spec, args.project_id)
        spec = read_json(spec_path)
        answers_payload = read_json(Path(args.answers).expanduser().resolve())
    except (OSError, ValueError) as exc:
        return fail(f"Could not read the inputs: {exc}", args.format)
    try:
        payload = apply_answers(project, spec, answers_payload, assist)
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
