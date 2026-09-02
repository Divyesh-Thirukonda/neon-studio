#!/usr/bin/env python3
from __future__ import annotations

import json
import pprint
import re
import sys
import time
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned[:72] or "song-project"


def stemify(project_id: str) -> str:
    return project_id.replace("-", "_")


def display_name(project_id: str, title_hint: str | None = None) -> str:
    return title_hint or " ".join(part.capitalize() for part in project_id.split("-"))


@dataclass(frozen=True)
class TrackBlueprint:
    id: str
    name: str
    instrument: str
    color: str
    gain: float
    pan: float
    steps: list[int]
    effects: list[dict[str, Any]]
    default_sections: tuple[str, ...]
    clip_type: str = "pattern"
    kind: str = "audio"


TRACK_BLUEPRINTS: dict[str, TrackBlueprint] = {
    "drums": TrackBlueprint(
        id="drums",
        name="Drums",
        instrument="Sampler",
        color="#ff8d5c",
        gain=0.82,
        pan=0.0,
        steps=[0, 4, 8, 12],
        effects=[
            {"id": "eq", "name": "EQ Eight", "active": False, "amount": 0.35},
            {"id": "bus-comp", "name": "Bus Comp", "active": False, "amount": 0.42},
        ],
        default_sections=("verse", "pre_build", "build", "drop", "second_drop"),
    ),
    "clap-stack": TrackBlueprint(
        id="clap-stack",
        name="Clap Stack",
        instrument="Clap Layer",
        color="#fb7185",
        gain=0.72,
        pan=0.02,
        steps=[4, 12],
        effects=[
            {"id": "verb", "name": "Reverb", "active": False, "amount": 0.28},
            {"id": "wide", "name": "Stereo Spread", "active": False, "amount": 0.3},
        ],
        default_sections=("intro", "verse", "build", "drop", "second_drop"),
    ),
    "hat-ride": TrackBlueprint(
        id="hat-ride",
        name="Hat/Ride",
        instrument="Trap Hat Rack",
        color="#f4f1a3",
        gain=0.68,
        pan=0.0,
        steps=[0, 2, 4, 6, 8, 10, 12, 14],
        effects=[
            {"id": "tight", "name": "Transient Tightener", "active": False, "amount": 0.24},
        ],
        default_sections=("verse", "build", "drop", "second_drop"),
    ),
    "bass": TrackBlueprint(
        id="bass",
        name="Bass",
        instrument="Mid Bass",
        color="#4ade80",
        gain=0.86,
        pan=0.0,
        steps=[0, 6, 10, 13],
        effects=[
            {"id": "duck", "name": "Sidechain", "active": False, "amount": 0.55},
            {"id": "sat", "name": "Saturator", "active": False, "amount": 0.32},
        ],
        default_sections=("verse", "build", "drop", "second_drop"),
    ),
    "sub": TrackBlueprint(
        id="sub",
        name="Sub",
        instrument="Triangle Sub",
        color="#34d399",
        gain=0.9,
        pan=0.0,
        steps=[0, 8],
        effects=[
            {"id": "mono", "name": "Mono Utility", "active": True, "amount": 1.0},
            {"id": "duck", "name": "Kick Duck", "active": False, "amount": 0.5},
        ],
        default_sections=("intro", "verse", "drop", "second_drop"),
    ),
    "chords": TrackBlueprint(
        id="chords",
        name="Chords",
        instrument="Supersaw",
        color="#ffd166",
        gain=0.92,
        pan=-0.03,
        steps=[0, 4, 8, 12],
        effects=[
            {"id": "eq", "name": "EQ Eight", "active": False, "amount": 0.4},
            {"id": "verb", "name": "Reverb", "active": False, "amount": 0.36},
        ],
        default_sections=("intro", "verse", "break", "drop", "second_drop", "outro"),
    ),
    "lead": TrackBlueprint(
        id="lead",
        name="Lead",
        instrument="Square Lead",
        color="#6fd6ff",
        gain=0.84,
        pan=0.02,
        steps=[0, 3, 7, 10, 14],
        effects=[
            {"id": "delay", "name": "Ping Delay", "active": False, "amount": 0.34},
            {"id": "air", "name": "Air EQ", "active": False, "amount": 0.28},
        ],
        default_sections=("intro", "pre_build", "build", "drop", "second_drop"),
    ),
    "guitar": TrackBlueprint(
        id="guitar",
        name="Guitar",
        instrument="Muted Guitar",
        color="#c4f1be",
        gain=0.74,
        pan=-0.06,
        steps=[0, 8],
        effects=[
            {"id": "comp", "name": "Compressor", "active": False, "amount": 0.3},
            {"id": "verb", "name": "Room", "active": False, "amount": 0.22},
        ],
        default_sections=("verse", "break"),
    ),
    "plucks": TrackBlueprint(
        id="plucks",
        name="Plucks",
        instrument="Pluck Synth",
        color="#f9a8d4",
        gain=0.76,
        pan=0.06,
        steps=[0, 4, 8, 12],
        effects=[
            {"id": "delay", "name": "Delay", "active": False, "amount": 0.26},
        ],
        default_sections=("intro", "verse", "break"),
    ),
    "vocals": TrackBlueprint(
        id="vocals",
        name="Vocals",
        instrument="Vocal Chop Rack",
        color="#f59fcb",
        gain=0.78,
        pan=0.0,
        steps=[],
        effects=[
            {"id": "delay", "name": "Stereo Delay", "active": False, "amount": 0.42},
            {"id": "verb", "name": "Reverb", "active": False, "amount": 0.34},
        ],
        default_sections=("intro", "pre_build", "build", "drop", "second_drop"),
        clip_type="audio",
    ),
    "fx": TrackBlueprint(
        id="fx",
        name="FX",
        instrument="Transitions",
        color="#d78bff",
        gain=0.72,
        pan=0.0,
        steps=[],
        effects=[
            {"id": "verb", "name": "Long Reverb", "active": False, "amount": 0.46},
            {"id": "width", "name": "Stereo Spread", "active": False, "amount": 0.42},
        ],
        default_sections=("pre_intro", "intro", "build", "drop", "second_drop", "outro"),
        clip_type="audio",
    ),
    "filter-auto": TrackBlueprint(
        id="filter-auto",
        name="Filter Auto",
        instrument="Automation Lane",
        color="#7dd3fc",
        gain=0.0,
        pan=0.0,
        steps=[],
        effects=[
            {"id": "macro", "name": "Filter Macro", "active": True, "amount": 0.62},
        ],
        default_sections=("build", "drop", "second_drop"),
        clip_type="pattern",
        kind="automation",
    ),
    "sample": TrackBlueprint(
        id="sample",
        name="Sample",
        instrument="Sampler",
        color="#cbd5e1",
        gain=0.76,
        pan=0.0,
        steps=[],
        effects=[
            {"id": "sampler", "name": "Sample Start/Stretch", "active": False, "amount": 0.3},
        ],
        default_sections=("intro", "verse", "break", "drop"),
        clip_type="audio",
    ),
}


ROLE_TO_TRACKS: dict[str, tuple[str, ...]] = {
    "drums": ("drums",),
    "kick": ("drums",),
    "snare": ("drums",),
    "clap": ("clap-stack",),
    "hat": ("hat-ride",),
    "ride": ("hat-ride",),
    "crash": ("fx",),
    "bass": ("bass",),
    "sub": ("sub",),
    "chords": ("chords",),
    "pad": ("chords",),
    "lead": ("lead",),
    "guitar": ("guitar",),
    "pluck": ("plucks",),
    "vocal": ("vocals",),
    "noise": ("fx",),
    "riser": ("fx",),
    "downlifter": ("fx",),
    "impact": ("fx",),
    "crowd": ("fx",),
    "reverse": ("fx",),
    "fx": ("fx",),
    "automation": ("filter-auto",),
    "sample": ("sample",),
}


SECTION_BAR_HINTS: dict[str, int] = {
    "pre_intro": 4,
    "intro": 8,
    "verse": 8,
    "pre_build": 4,
    "build": 8,
    "drop": 16,
    "second_drop": 16,
    "break": 8,
    "outro": 8,
    "production_notes": 0,
}


DEFAULT_TRACK_IDS = ("chords", "lead", "bass", "drums", "fx")


def compact_detail(*parts: str | None) -> str:
    return ". ".join(part.strip().rstrip(".") for part in parts if part and part.strip())


def infer_title_from_project(project_id: str, spec: dict[str, Any]) -> str:
    return display_name(project_id, spec.get("titleHint"))


def infer_description(project_name: str, spec: dict[str, Any], prompt: str | None) -> str:
    source = "transcript-driven"
    focus = "portable Neon Studio project"
    if prompt:
        return f"{source.capitalize()} {focus} built from a production walkthrough for {project_name}."
    return f"{source.capitalize()} {focus} built from a production walkthrough."


def infer_key_center(spec: dict[str, Any]) -> str | None:
    hints = spec.get("keyHints") or []
    if not hints:
        return None
    unique = []
    for hint in hints:
        normalized = " ".join(part.capitalize() for part in hint.split())
        if normalized not in unique:
            unique.append(normalized)
    return " / ".join(unique[:2])


def infer_bpm(spec: dict[str, Any], prompt: str | None) -> int:
    if spec.get("tempoHint"):
        return max(60, min(220, int(spec["tempoHint"])))
    text = (prompt or "").lower()
    if "alone" in text or "marshmello" in text:
        return 142
    if "just can't stop" in text or "just cant stop" in text:
        return 150
    return 142


def infer_snap(spec: dict[str, Any]) -> str:
    top_tracks = {item["name"] for item in spec.get("globalTracks", [])[:12]}
    if {"hat", "clap", "snare"} & top_tracks:
        return "1/16"
    return "1/4"


def infer_swing(spec: dict[str, Any]) -> int:
    top_tracks = {item["name"] for item in spec.get("globalTracks", [])[:12]}
    return 18 if {"drums", "hat", "clap"} & top_tracks else 0


def normalized_sections(spec: dict[str, Any]) -> list[dict[str, Any]]:
    sections = [deepcopy(section) for section in spec.get("sections", [])]
    musical = [section for section in sections if SECTION_BAR_HINTS.get(section["type"], 0) > 0]
    if not musical:
        return [
            {"id": "section-01", "type": "intro", "label": "Intro", "summary": "Generated intro", "trackRoles": ["chords", "lead", "fx"], "plugins": [], "techniques": []},
            {"id": "section-02", "type": "verse", "label": "Verse", "summary": "Generated verse", "trackRoles": ["drums", "bass", "chords"], "plugins": [], "techniques": []},
            {"id": "section-03", "type": "build", "label": "Build", "summary": "Generated build", "trackRoles": ["drums", "fx", "lead"], "plugins": [], "techniques": ["automation"]},
            {"id": "section-04", "type": "drop", "label": "Drop", "summary": "Generated drop", "trackRoles": ["drums", "bass", "chords", "lead", "fx"], "plugins": [], "techniques": []},
            {"id": "section-05", "type": "outro", "label": "Outro", "summary": "Generated outro", "trackRoles": ["chords", "fx"], "plugins": [], "techniques": []},
        ]
    return musical


def choose_track_ids(spec: dict[str, Any]) -> list[str]:
    chosen: list[str] = []
    for item in spec.get("globalTracks", []):
        for track_id in ROLE_TO_TRACKS.get(item["name"], ()):
            if track_id not in chosen:
                chosen.append(track_id)
    if not chosen:
        chosen.extend(DEFAULT_TRACK_IDS)
        return chosen

    # Only pad when the spec is too thin to be a song at all. Topping every
    # project up to six lanes invented tracks nobody wrote a part for, which
    # rendered as silence and then counted against the project as missing audio.
    if len(chosen) < 3:
        for fallback in DEFAULT_TRACK_IDS:
            if fallback not in chosen and len(chosen) < 3:
                chosen.append(fallback)
    return chosen


def make_track(blueprint: TrackBlueprint, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """A track from its blueprint. `overrides` (from the musical plan) may rename
    the lane and its instrument; the id, kind, colour, gain and effects stay."""
    overrides = overrides or {}
    return {
        "id": blueprint.id,
        "name": str(overrides.get("name") or blueprint.name),
        "kind": blueprint.kind,
        "instrument": str(overrides.get("instrument") or blueprint.instrument),
        "gain": blueprint.gain,
        "pan": blueprint.pan,
        "steps": list(blueprint.steps),
        "effects": deepcopy(blueprint.effects),
        "clips": [],
        "color": blueprint.color,
        "file": None,
    }


def track_ids_for_section(section: dict[str, Any], chosen_tracks: list[str]) -> list[str]:
    mapped: list[str] = []
    for role in section.get("trackRoles", []):
        for track_id in ROLE_TO_TRACKS.get(role, ()):
            if track_id in chosen_tracks and track_id not in mapped:
                mapped.append(track_id)
    if not mapped:
        for track_id in chosen_tracks:
            blueprint = TRACK_BLUEPRINTS[track_id]
            if section["type"] in blueprint.default_sections:
                mapped.append(track_id)
    return mapped


def section_bar_layout(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    current_bar = 0
    laid_out: list[dict[str, Any]] = []
    for section in sections:
        # A section that already knows its length keeps it. The type constant is
        # a fallback, not an override — otherwise the timecodes the transcript
        # carried and the lengths the filler worked out are both thrown away and
        # every intro is eight bars regardless of the source.
        declared = section.get("bars")
        if isinstance(declared, (int, float)) and declared > 0:
            bars = int(round(float(declared)))
        else:
            bars = SECTION_BAR_HINTS.get(section["type"], 8)
        if bars <= 0:
            continue
        placed = deepcopy(section)
        placed["startBar"] = current_bar
        placed["bars"] = bars
        placed["endBar"] = current_bar + bars
        laid_out.append(placed)
        current_bar += bars
    return laid_out


def clip_name(section_label: str, track_name: str) -> str:
    if track_name.lower() in section_label.lower():
        return section_label
    return f"{section_label} {track_name.lower()}"


def infer_clip_type(track_id: str, section: dict[str, Any]) -> str:
    if track_id in {"fx", "vocals", "sample"}:
        return "audio"
    if section["type"] in {"build", "drop", "second_drop"} and track_id in {"lead", "bass", "drums", "clap-stack", "hat-ride"}:
        return "pattern"
    return TRACK_BLUEPRINTS[track_id].clip_type


# Which effect entry on which track the generated renderer actually drives when a
# section names a technique. Kept in step with the technique pass in the
# renderer template: an entry marked active here is one that ducks, rings, or
# widens in the render, not a reminder.
TECHNIQUE_EFFECT_ENTRIES: dict[str, dict[str, tuple[str, str, float]]] = {
    "sidechain": {
        "sub": ("duck", "Kick Duck", 0.65),
        "bass": ("duck", "Sidechain", 0.50),
        "chords": ("duck", "Sidechain", 0.45),
        "plucks": ("duck", "Sidechain", 0.35),
    },
    "reverb": {
        "lead": ("verb", "Reverb", 0.22),
        "chords": ("verb", "Reverb", 0.22),
        "vocals": ("verb", "Reverb", 0.22),
        "plucks": ("verb", "Reverb", 0.22),
    },
    "delay": {
        "lead": ("delay", "Ping Delay", 0.28),
        "vocals": ("delay", "Stereo Delay", 0.28),
    },
    "distortion": {
        "bass": ("sat", "Saturator", 0.32),
        "lead": ("sat", "Saturator", 0.32),
    },
    "stereo": {
        "chords": ("wide", "Stereo Spread", 0.3),
        "plucks": ("wide", "Stereo Spread", 0.3),
        "fx": ("width", "Stereo Spread", 0.42),
    },
    "eq": {
        "lead": ("eq", "Air EQ", 0.3),
        "chords": ("eq", "EQ Eight", 0.3),
        "vocals": ("eq", "EQ Eight", 0.3),
        "plucks": ("eq", "EQ Eight", 0.3),
        "bass": ("eq", "Low Cut", 0.3),
        "sub": ("eq", "Sub EQ", 0.3),
    },
    "compression": {
        "drums": ("comp", "Bus Comp", 0.4),
        "clap-stack": ("comp", "Bus Comp", 0.4),
        "vocals": ("comp", "Compressor", 0.35),
        "guitar": ("comp", "Compressor", 0.35),
    },
    "reverse": {
        "fx": ("reverse", "Reverse Swell", 0.5),
    },
}


def enrich_effects(track: dict[str, Any], section: dict[str, Any], global_plugins: list[str]) -> None:
    effect_names = {effect["name"] for effect in track["effects"]}
    section_plugins = section.get("plugins", [])
    for plugin in section_plugins[:2]:
        if plugin not in effect_names:
            track["effects"].append({"id": slugify(plugin), "name": plugin, "active": False, "amount": 0.3})
            effect_names.add(plugin)
    for technique in section.get("techniques", []):
        entry = TECHNIQUE_EFFECT_ENTRIES.get(str(technique).lower(), {}).get(track["id"])
        if not entry:
            continue
        effect_id, name, amount = entry
        existing = next((effect for effect in track["effects"] if effect["name"] == name), None)
        if existing is not None:
            existing["active"] = True
        else:
            track["effects"].append({"id": effect_id, "name": name, "active": True, "amount": amount})
            effect_names.add(name)
    if "automation" in section.get("techniques", []) and track["id"] == "filter-auto" and "Filter Macro" not in effect_names:
        track["effects"].append({"id": "macro", "name": "Filter Macro", "active": True, "amount": 0.62})
    if global_plugins:
        for plugin in global_plugins[:1]:
            if plugin not in effect_names and len(track["effects"]) < 4:
                track["effects"].append({"id": slugify(plugin), "name": plugin, "active": False, "amount": 0.24})
                break


def make_recipe(section_layout: list[dict[str, Any]], all_track_ids: list[str], spec: dict[str, Any], plan_decisions: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    recipe = [
        {
            "id": "transcript-project",
            "section": "Foundation",
            "label": "Transcript-derived project",
            "detail": "Track layout, clips, and coverage were generated from the transcript before manual sound design and rendering.",
            "status": "mapped",
            "trackIds": all_track_ids,
        }
    ]
    for section in section_layout:
        tracks = section.get("sectionTrackIds", [])
        detail = compact_detail(
            section.get("summary"),
            ("Tracks: " + ", ".join(tracks)) if tracks else None,
            ("Plugins: " + ", ".join(section.get("plugins", [])[:4])) if section.get("plugins") else None,
            ("Techniques: " + ", ".join(section.get("techniques", [])[:4])) if section.get("techniques") else None,
        )
        recipe.append(
            {
                "id": section["id"],
                "section": section["label"],
                "label": section["summary"][:72] or section["label"],
                "detail": detail,
                "status": "mapped",
                "trackIds": tracks,
            }
        )
    for item in spec.get("globalPlugins", [])[:6]:
        if item["mentions"] <= 0:
            continue
        recipe.append(
            {
                "id": f"plugin-{slugify(item['name'])}",
                "section": "Mix / FX",
                "label": f"Use {item['name']}",
                "detail": f"Plugin mentioned {item['mentions']} time(s) in the transcript and should be reflected in the eventual renderer or track effect chain.",
                "status": "mapped",
                "trackIds": all_track_ids[:3],
            }
        )
    fill = spec.get("fillInBlanks") or {}

    # Decisions are blanks filled in fields the transcript already had — tempo,
    # key, section roles. Useful context, but not usually work to do.
    decisions = [
        item
        for item in (fill.get("decisions") or [])
        if isinstance(item, dict) and not item.get("requirementId")
    ]
    for index, item in enumerate(decisions[:8], start=1):
        recipe.append(
            {
                "id": f"fill-{index:02d}",
                "section": "Fill In The Blanks",
                "label": f"{item.get('area', 'inference')}: {item.get('detail', '')}"[:96],
                "detail": f"{item.get('detail', '')} Reason: {item.get('reason', '')}",
                "status": "inferred",
                "trackIds": all_track_ids[:4],
            }
        )

    # What the model decided about the music itself (tempo, chords, drums, lane
    # names) is listed the same way, marked as inferred so a person can disagree.
    tracks_by_section = {section["id"]: section.get("sectionTrackIds", []) for section in section_layout}
    for index, item in enumerate((plan_decisions or [])[:16], start=1):
        section_id = item.get("sectionId")
        if section_id:
            track_ids = tracks_by_section.get(section_id) or all_track_ids[:4]
        elif item.get("area") == "track":
            track_ids = [tid for tid in all_track_ids if str(item.get("detail", "")).startswith(f"{tid}:")] or all_track_ids[:4]
        else:
            track_ids = all_track_ids[:4]
        reason = item.get("reason") or ""
        recipe.append(
            {
                "id": f"plan-{index:02d}",
                "section": "Musical Plan",
                "label": f"{item.get('area', 'plan')}: {item.get('detail', '')}"[:96],
                "detail": f"{item.get('detail', '')}" + (f" Reason: {reason}" if reason else "") + " (via model)",
                "status": "inferred",
                "trackIds": track_ids,
            }
        )

    # Gaps are the other thing entirely: production steps nobody mentioned, which
    # somebody still has to carry out. They get their own recipe section so they
    # read as work rather than as notes, and they stay "planned" until done.
    for index, gap in enumerate((fill.get("gaps") or [])[:16], start=1):
        if not isinstance(gap, dict):
            continue
        measured = gap.get("confidence") == "measured"
        detail = str(gap.get("step") or "")
        why = str(gap.get("why") or "")
        evidence = str(gap.get("evidence") or "")
        parts = [detail]
        if why:
            parts.append(f"Why: {why}")
        if evidence:
            parts.append(evidence)
        area = gap.get("soundCheckArea")
        if area and area != "none" and not measured:
            parts.append(f"Skipping this is what the sound check flags as {area}.")
        recipe.append(
            {
                "id": f"gap-{index:02d}",
                "section": "Missing Steps" if not measured else "Sound Check Follow-Up",
                "label": str(gap.get("label") or "Missing production step")[:96],
                "detail": " ".join(parts),
                "status": "planned",
                "trackIds": _track_ids_for_roles(gap.get("roles") or [], all_track_ids),
            }
        )
    return recipe


def _track_ids_for_roles(roles: list[Any], all_track_ids: list[str]) -> list[str]:
    """Point a step at the tracks it concerns, falling back to the first few.

    Track ids in a materialized project are role-derived slugs, so a substring
    match lands on the right lanes often enough to be useful and never produces
    a wrong-looking empty list."""
    wanted = [str(role).lower() for role in roles if role]
    if not wanted:
        return all_track_ids[:4]
    matched = [tid for tid in all_track_ids if any(role in tid.lower() for role in wanted)]
    return matched[:4] or all_track_ids[:4]


def make_controls(tracks: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        track["id"]: {
            "gain": track["gain"],
            "pan": track["pan"],
            "mute": False,
            "solo": False,
            "arm": False,
            "sendA": 0.15,
            "sendB": 0.08,
        }
        for track in tracks
    }


def infer_loop_range(section_layout: list[dict[str, Any]]) -> tuple[int, int]:
    for section in section_layout:
        if section["type"] == "drop":
            start = section["startBar"]
            return start, start + section["bars"]
    if section_layout:
        return section_layout[0]["startBar"], section_layout[0]["startBar"] + max(8, section_layout[0]["bars"])
    return 0, 16


def build_project_materialization(spec: dict[str, Any], project_id: str, prompt: str | None = None, assist: Any = None) -> dict[str, Any]:
    """The project for a spec.

    `assist` is an llm.Assist. With none (or one that is off, has no key, or
    answers something that does not validate) every decision below comes from
    the same tables and substring rules as before; with one, the musical plan it
    proposes is applied to a copy of the spec first and recorded on the project
    under "materialization", with "ai" saying what happened."""
    plan, extras = propose_musical_plan(spec, project_id, prompt, assist)
    spec = apply_materialization_plan(spec, plan)
    project_name = infer_title_from_project(project_id, spec)
    chosen_track_ids = choose_track_ids(spec)
    lane_names = plan.get("tracks") or {}
    tracks = [make_track(TRACK_BLUEPRINTS[track_id], lane_names.get(track_id)) for track_id in chosen_track_ids]
    track_by_id = {track["id"]: track for track in tracks}

    section_layout = section_bar_layout(normalized_sections(spec))
    global_plugins = [item["name"] for item in spec.get("globalPlugins", [])]

    for section in section_layout:
        section_track_ids = track_ids_for_section(section, chosen_track_ids)
        section["sectionTrackIds"] = section_track_ids
        for track_id in section_track_ids:
            track = track_by_id[track_id]
            clip_index = sum(1 for clip in track["clips"] if clip["startBar"] == section["startBar"])
            track["clips"].append(
                {
                    "id": f"{track_id}-{section['startBar']}-{clip_index + 1}",
                    "name": clip_name(section["label"], track["name"]),
                    "startBar": section["startBar"],
                    "bars": section["bars"],
                    "lane": track_id,
                    "color": track["color"],
                    "type": infer_clip_type(track_id, section),
                }
            )
            enrich_effects(track, section, global_plugins)

    loop_start, loop_end = infer_loop_range(section_layout)
    recipe = make_recipe(section_layout, chosen_track_ids, spec, extras["materialization"]["decisions"])
    bpm = infer_bpm(spec, prompt)
    groove = plan.get("groove") or {}
    project = {
        "format": "neon-studio-project",
        "formatVersion": 1,
        "portable": True,
        "assetMode": "external",
        "id": project_id,
        "name": project_name,
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
        "projectFile": None,
        "assets": None,
        "description": plan.get("description") or infer_description(project_name, spec, prompt),
        "keyCenter": infer_key_center(spec),
        "ai": extras["ai"],
        "materialization": extras["materialization"],
        "snapshot": {
            "version": 3,
            "bpm": bpm,
            "swing": groove["swing"] if "swing" in groove else infer_swing(spec),
            "snap": groove["snap"] if "snap" in groove else infer_snap(spec),
            "loopEnabled": True,
            "loopStartBar": loop_start,
            "loopEndBar": loop_end,
            "tracks": tracks,
            "controls": make_controls(tracks),
            "notes": [],
            "automationLanes": technique_automation_lanes(section_layout),
            "selectedTrackId": tracks[0]["id"] if tracks else "",
            "selectedClipId": tracks[0]["clips"][0]["id"] if tracks and tracks[0]["clips"] else "",
            "activeView": "playlist",
            "patternIndex": 1,
            "arrangementMode": "song",
            "recipe": recipe,
        },
    }
    return project


# ---------------------------------------------------------------------------
# The musical plan
#
# Everything above guesses musical decisions from tables keyed by section type
# and a few substrings. When a model is available, one call asks it for the
# same decisions - tempo, key, groove, a progression per section, drum and
# lane rhythms, a lead motif, transition FX, automation, lane names, an
# arrangement when the spec has none, and a one-line description. The answer
# is validated against what exists (chord symbols through the parser above,
# beats inside the bar, section and track ids in the project) and dropped
# where it does not fit. What survives is written into a copy of the spec in
# the exact shapes the inference hooks already read (tempoHint, keyHints,
# laneEvents, laneTransforms), and the plan is stored on the project. The
# renderer emission only ever reads project + spec, so it stays byte-identical
# for the same pair whether the plan came from the model or from nowhere.
# ---------------------------------------------------------------------------

try:
    from llm import Assist  # noqa: E402
except ImportError:  # pragma: no cover - the adapter ships beside this file
    Assist = None  # type: ignore[assignment,misc]

PLAN_TEXT_CAP = 24_000
PLAN_SECTIONS_PER_CALL = 25
PLAN_SNAP_CHOICES = ("1/4", "1/8", "1/16", "1/32")
PLAN_TECHNIQUES = ("sidechain", "reverb", "delay", "filtering", "automation", "distortion", "stereo", "layering", "eq", "compression", "reverse")
PLAN_AUTOMATION_PARAMETERS = ("filter", "cutoff", "macro", "volume", "reverb", "delay", "pan", "width", "distortion")
PLAN_CURVES = {"linear": "linear", "exp": "exp", "exponential": "exp", "ease_in": "ease_in", "ease_out": "ease_out", "ease_in_out": "ease_in_out", "step": "step"}
PLAN_DRUM_LANES = ("kick", "snare", "clap", "hat", "ride", "crash")
PLAN_DRUM_LIST_KEYS = (("kicks", "kick"), ("snares", "snare"), ("claps", "clap"), ("hats", "hat"), ("rides", "ride"), ("crashes", "crash"))
PLAN_FX_KEYS = ("noiseBed", "riser", "downlifter", "crash")
DIATONIC_MAJOR = (0, 2, 4, 5, 7, 9, 11)
DIATONIC_MINOR = (0, 2, 3, 5, 7, 8, 10, 11)
KEY_CENTER_RE = re.compile(r"^\s*([A-Ga-g])\s*-?\s*(#|b|sharp|flat)?\s*-?\s*(major|minor|maj|min|m)?\s*$", re.IGNORECASE)
KEY_ACCIDENTALS = {"#": "#", "b": "b", "sharp": "#", "flat": "b"}

PLAN_SYSTEM_PROMPT = """You are the musical planner inside Neon Studio, a tool that turns a producer's walkthrough into a starter project. You get the walkthrough, what the transcript already pinned down, the lanes in the project and the sections. You propose the musical decisions the walkthrough leaves open, so the starter render sounds like the song being described rather than a generic default.

Rules:
- Stay in the stated key and style. If the walkthrough states a tempo or key, do not contradict it.
- Chord symbols: a root letter A-G, optional # or b, optional suffix from: maj7 maj9 m m7 m9 min min7 add9 sus2 sus4 dim aug 7 9 5. Examples: Em7, Cmaj7, F#m, Bb, Gadd9. Two to eight chords, one per bar, cycling.
- Beats are zero-based inside one 4/4 bar: 0 is the downbeat, 1 the second beat, 3.5 the last eighth. Every beat is in [0, 4). A four-on-the-floor kick is [0, 1, 2, 3]; a trap half-time snare is [2]; a backbeat is [1, 3].
- Use only the section ids and track ids you are given. Leave out any field you have no opinion on. Do not restate lanes listed as alreadyPinned for a section - those come from the walkthrough and win.
- leadMotifKey: sparse (a few long notes), dense (a busy hook), tease (two-note fragments), dark (lower, minor-leaning). leadTransposeSemitones moves the motif; 12 is up an octave.
- energy scales the section's level: 0.7 quiet intro, 1.0 verse, 1.25 a full drop, never outside 0.5-1.5.
- fxProfile says which transition effects the section actually calls for; automation envelopes run from start to end (0-1) over the given bars.
- tracks: a display name and instrument for each lane that fits this song (e.g. chords -> Rhodes / Electric Piano for lo-fi, Supersaw for future bass). Keep the ids as given.
- When asked for an arrangement, propose 4 to 9 sections in order with ids section-01, section-02, ... using only the listed section types and track roles.
- Every reason is one short sentence in plain words, under 20 words.
Reply with JSON only."""


def _plan_schema(*, first: bool, need_arrangement: bool) -> dict[str, Any]:
    section_shape = {
        "progressionSymbols": ["Em7", "Cmaj7", "G", "D"],
        "progressionReason": "short sentence",
        "chordEvents": [{"beat": 0.0, "duration": 0.8, "stab": True, "bright": 0.9}],
        "bassEvents": [{"beat": 0.0, "duration": 1.45}],
        "leadMotifKey": "sparse | dense | tease | dark",
        "leadTransposeSemitones": 0,
        "drums": {"kicks": [0.0, 2.0], "snares": [1.0, 3.0], "claps": [1.0, 3.0], "hats": [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5], "hatSpacing": 0.5, "ride": False, "clapRoll": False, "crashBars": [0]},
        "fxProfile": {"noiseBed": False, "riser": True, "downlifter": False, "crash": True},
        "automation": {"envelopes": [{"parameter": "filter", "targetLane": "chords", "start": 0.2, "end": 0.95, "barOffset": 0, "bars": 8, "curve": "linear"}]},
        "energy": 1.0,
        "reason": "short sentence",
    }
    schema: dict[str, Any] = {}
    if first:
        schema.update({
            "tempo": {"bpm": 128, "reason": "short sentence"},
            "key": {"center": "E minor", "reason": "short sentence"},
            "groove": {"swing": 0, "snap": "1/16", "reason": "short sentence"},
            "description": "one sentence about the song: style, tempo, key, the standout move",
            "tracks": {"<track id>": {"name": "Rhodes", "instrument": "Electric Piano"}},
        })
        if need_arrangement:
            schema["arrangement"] = [{"id": "section-01", "type": "intro", "label": "Intro", "bars": 8, "summary": "what happens here", "trackRoles": ["chords", "fx"], "techniques": ["filtering"]}]
    schema["sections"] = {"<section id>": section_shape}
    return schema


def parse_key_center(value: Any) -> tuple[int, str, str] | None:
    """'E minor' / 'F# major' / 'Bbm' -> (semitone, mode, 'E minor'); None when it is not a key."""
    if not isinstance(value, str):
        return None
    match = KEY_CENTER_RE.match(value.replace("♭", "b").replace("♯", "#"))
    if not match:
        return None
    letter, accidental, mode = match.groups()
    root = letter.upper() + KEY_ACCIDENTALS.get((accidental or "").lower(), "")
    semitone = NOTE_TO_SEMITONE.get(root)
    if semitone is None:
        return None
    mode_name = "minor" if (mode or "").lower() in {"minor", "min", "m"} else "major"
    return semitone, mode_name, f"{root} {mode_name}"


def spec_key_center(spec: dict[str, Any]) -> tuple[int, str, str] | None:
    for hint in spec.get("keyHints") or []:
        parsed = parse_key_center(hint)
        if parsed:
            return parsed
    return None


def musical_sections(spec: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        section for section in (spec.get("sections") or [])
        if isinstance(section, dict) and SECTION_BAR_HINTS.get(str(section.get("type")), 0) > 0
    ]


def section_inference_text(section: dict[str, Any]) -> str:
    """The same text infer_section_starter_defaults reads, so the plan defers to exactly what it would."""
    return lower_join(
        section.get("summary"),
        section.get("excerpt"),
        section.get("transcriptText"),
        " ".join(section.get("trackRoles", []) or []),
        " ".join(section.get("techniques", []) or []),
    )


def _clean_text(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit].strip()


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if number == number else None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _clean_beats(value: Any, limit: int = 16) -> list[float] | None:
    if not isinstance(value, list):
        return None
    beats: list[float] = []
    for item in value:
        beat = _as_float(item)
        if beat is None:
            continue
        beat = round(beat, 2)  # round first: 3.999 is beat 4, which is the next bar
        if not 0.0 <= beat < 4.0:
            continue
        if beat not in beats:
            beats.append(beat)
    beats.sort()
    return beats[:limit] if beats else None


def _clean_rhythm_events(value: Any, *, bars: int, chord_flags: bool) -> list[dict[str, Any]] | None:
    if not isinstance(value, list):
        return None
    events: list[dict[str, Any]] = []
    seen: set[tuple[int, float]] = set()
    for item in value[:48]:
        if not isinstance(item, dict):
            continue
        beat = _as_float(item.get("beat"))
        duration = _as_float(item.get("duration"))
        if beat is None or duration is None:
            continue
        beat, duration = round(beat, 2), round(duration, 2)  # range-check what will be kept, not the raw value
        if not 0.0 <= beat < 4.0 or not 0.0 < duration <= 4.0:
            continue
        event: dict[str, Any] = {"beat": beat, "duration": duration}
        bar_offset = -1
        if "barOffset" in item:
            offset = _as_int(item.get("barOffset"))
            if offset is None or not 0 <= offset < max(1, bars):
                continue
            event["barOffset"] = offset
            bar_offset = offset
        if chord_flags:
            if isinstance(item.get("stab"), bool):
                event["stab"] = item["stab"]
            bright = _as_float(item.get("bright"))
            if bright is not None and 0.0 <= bright <= 1.0:
                event["bright"] = round(bright, 2)
        key = (bar_offset, event["beat"])
        if key in seen:
            continue
        seen.add(key)
        events.append(event)
    events.sort(key=lambda event: (event.get("barOffset", -1), event["beat"]))
    return events[:16] if events else None


def _clean_drums(value: Any, *, bars: int) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    drums: dict[str, Any] = {}
    for list_key, _lane in PLAN_DRUM_LIST_KEYS:
        beats = _clean_beats(value.get(list_key))
        if beats:
            drums[list_key] = beats
    spacing = _as_float(value.get("hatSpacing"))
    if spacing is not None and 0.125 <= spacing <= 2.0:
        drums["hatSpacing"] = round(spacing, 3)
    for flag in ("ride", "clapRoll"):
        if isinstance(value.get(flag), bool):
            drums[flag] = value[flag]
    crash_bars = value.get("crashBars")
    if isinstance(crash_bars, list):
        cleaned = sorted({offset for offset in (_as_int(item) for item in crash_bars) if offset is not None and 0 <= offset < max(1, bars)})
        if cleaned or not crash_bars:
            drums["crashBars"] = cleaned
    return drums or None


def _clean_envelopes(value: Any, *, bars: int) -> list[dict[str, Any]] | None:
    raw = value.get("envelopes") if isinstance(value, dict) else value
    if not isinstance(raw, list):
        return None
    envelopes: list[dict[str, Any]] = []
    for item in raw[:6]:
        if not isinstance(item, dict):
            continue
        parameter = str(item.get("parameter") or "filter").strip().lower()
        if parameter not in PLAN_AUTOMATION_PARAMETERS:
            continue
        start = _as_float(item.get("start"))
        end = _as_float(item.get("end"))
        if start is None or end is None or not (0.0 <= start <= 1.0 and 0.0 <= end <= 1.0):
            continue
        offset = _as_int(item.get("barOffset", 0)) or 0
        if not 0 <= offset < max(1, bars):
            continue
        length = _as_int(item.get("bars", bars - offset))
        if length is None or length < 1:
            continue
        length = min(length, max(1, bars - offset))
        envelope: dict[str, Any] = {
            "parameter": parameter,
            "start": round(start, 2),
            "end": round(end, 2),
            "barOffset": offset,
            "bars": length,
            "curve": PLAN_CURVES.get(str(item.get("curve") or "linear").strip().lower(), "linear"),
        }
        target = item.get("targetLane") or item.get("targetTrackId")
        if isinstance(target, str) and (target in ROLE_TO_TRACKS or target in TRACK_BLUEPRINTS):
            envelope["targetLane"] = target
        envelopes.append(envelope)
    return envelopes or None


def _progression_fits_key(shapes: list[dict[str, Any]], key: tuple[int, str, str] | None) -> bool:
    if key is None:
        return True
    tonic, mode, _label = key
    scale = DIATONIC_MAJOR if mode == "major" else DIATONIC_MINOR
    fitting = sum(1 for shape in shapes if (int(shape["root"]) - tonic) % 12 in scale)
    return fitting * 2 >= len(shapes)


def _reason(value: Any, *keys: str) -> str:
    if isinstance(value, dict):
        for key in keys or ("reason",):
            text = _clean_text(value.get(key), 200)
            if text:
                return text
    return ""


def plan_section_digest(section: dict[str, Any]) -> dict[str, Any]:
    lane_events = section.get("laneEvents") or {}
    lane_transforms = section.get("laneTransforms") or {}
    digest: dict[str, Any] = {
        "id": section.get("id"),
        "type": section.get("type"),
        "label": section.get("label"),
        "bars": section.get("bars") or SECTION_BAR_HINTS.get(str(section.get("type")), 8),
        "summary": _clean_text(section.get("summary"), 600),
        "trackRoles": list(section.get("trackRoles") or [])[:10],
        "techniques": list(section.get("techniques") or [])[:8],
    }
    excerpt = _clean_text(section.get("excerpt") or section.get("transcriptText"), 400)
    if excerpt and excerpt != digest["summary"]:
        digest["excerpt"] = excerpt
    pinned = sorted(
        str(lane) for lane, payload in lane_events.items()
        if isinstance(payload, dict) and (payload.get("events") or payload.get("progressionSymbols") or payload.get("envelopes"))
    )
    if pinned:
        digest["alreadyPinned"] = pinned
    if isinstance(lane_transforms, dict) and lane_transforms:
        digest["transforms"] = sorted(str(lane) for lane in lane_transforms)
    return digest


def plan_project_digest(spec: dict[str, Any], project_id: str, prompt: str | None, lanes: list[str]) -> dict[str, Any]:
    digest: dict[str, Any] = {
        "id": project_id,
        "title": infer_title_from_project(project_id, spec),
        "prompt": _clean_text(prompt or spec.get("sourcePrompt"), 1500),
        "derivedPrompt": _clean_text(spec.get("derivedPrompt"), 1000),
        "tempoHint": spec.get("tempoHint"),
        "keyHints": list(spec.get("keyHints") or [])[:3],
        "arrangementNotes": [_clean_text(note, 200) for note in (spec.get("arrangementNotes") or [])[:6] if isinstance(note, str)],
        "mixNotes": [_clean_text(note, 200) for note in (spec.get("mixNotes") or [])[:6] if isinstance(note, str)],
        "lanes": [{"id": lane, "name": TRACK_BLUEPRINTS[lane].name, "instrument": TRACK_BLUEPRINTS[lane].instrument} for lane in lanes if lane in TRACK_BLUEPRINTS],
    }
    return {key: value for key, value in digest.items() if value not in (None, "", [])}


def _chunk_digests(digests: list[dict[str, Any]], budget: int) -> list[list[dict[str, Any]]]:
    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_size = 0
    for digest in digests:
        size = len(json.dumps(digest))
        if current and (len(current) >= PLAN_SECTIONS_PER_CALL or current_size + size > budget):
            chunks.append(current)
            current, current_size = [], 0
        current.append(digest)
        current_size += size
    if current or not chunks:
        chunks.append(current)
    return chunks


def ask_musical_plan(spec: dict[str, Any], project_id: str, prompt: str | None, assist: Any) -> tuple[dict[str, Any] | None, list[str]]:
    """One question, batched over every section (chunked when the text is very long). Raw answer, unvalidated."""
    if assist is None or not getattr(assist, "available", False):
        return None, []
    sections = musical_sections(spec)
    need_arrangement = not sections
    lanes = list(TRACK_BLUEPRINTS) if need_arrangement and not spec.get("globalTracks") else choose_track_ids(spec)
    project_digest = plan_project_digest(spec, project_id, prompt, lanes)
    base_size = len(json.dumps(project_digest)) + len(PLAN_SYSTEM_PROMPT) + 2000
    chunks = _chunk_digests([plan_section_digest(section) for section in sections], max(4000, PLAN_TEXT_CAP - base_size))
    merged: dict[str, Any] = {}
    notes: list[str] = []
    for index, chunk in enumerate(chunks):
        first = index == 0
        context: dict[str, Any] = {"project": project_digest}
        if need_arrangement:
            context["sectionTypes"] = [kind for kind, bars in SECTION_BAR_HINTS.items() if bars > 0]
            context["trackRoles"] = list(ROLE_TO_TRACKS)
            context["techniques"] = list(PLAN_TECHNIQUES)
        else:
            context["sections"] = chunk
            if not first:
                context["settled"] = {key: merged[key] for key in ("tempo", "key", "groove") if key in merged}
        asks = []
        if first:
            asks.append("tempo, key and groove (only where the walkthrough does not state them), a one-sentence description, and a name and instrument per lane")
            if need_arrangement:
                asks.append("an arrangement for this song, since the walkthrough gave no sections, and then the per-section plan for the sections you proposed")
        if not need_arrangement:
            asks.append(f"the per-section plan for the {len(chunk)} section(s) listed" + (f" (part {index + 1} of {len(chunks)})" if len(chunks) > 1 else ""))
        task = "Plan this song. Give " + "; ".join(asks) + ".\n\n" + json.dumps(context, indent=1, ensure_ascii=False)
        answer = assist.ask(task, system=PLAN_SYSTEM_PROMPT, schema=_plan_schema(first=first, need_arrangement=need_arrangement), max_tokens=8192, expect=dict)
        if answer is None:
            if first:
                return None, notes  # assist.note already says why
            notes.append(f"plan call {index + 1} of {len(chunks)} failed: {assist.note}")
            continue
        if first:
            merged.update({key: value for key, value in answer.items() if key != "sections"})
        answered_sections = answer.get("sections")
        if isinstance(answered_sections, dict):
            merged.setdefault("sections", {}).update(answered_sections)
    return merged, notes


def validate_musical_plan(raw: Any, spec: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Keep what fits the project; drop and name everything else."""
    plan: dict[str, Any] = {}
    dropped: list[str] = []
    if not isinstance(raw, dict):
        return plan, ["plan: the answer was not an object"]

    tempo = raw.get("tempo")
    if isinstance(tempo, dict) and tempo.get("bpm") is not None:
        bpm = _as_int(tempo.get("bpm"))
        if spec.get("tempoHint"):
            pass  # the walkthrough stated it; the model's number is not used
        elif bpm is None or not 60 <= bpm <= 220:
            dropped.append(f"tempo: {tempo.get('bpm')!r} is not a whole number between 60 and 220")
        else:
            plan["tempo"] = {"bpm": bpm, "reason": _reason(tempo)}

    key = raw.get("key")
    stated_key = spec_key_center(spec)
    if isinstance(key, dict) and key.get("center") is not None:
        parsed = parse_key_center(key.get("center"))
        if spec.get("keyHints"):
            pass  # the walkthrough stated a key, in whatever words; the model's is not used
        elif parsed is None:
            dropped.append(f"key: {key.get('center')!r} is not a key name")
        else:
            plan["key"] = {"center": parsed[2], "reason": _reason(key)}
    plan_key = stated_key or (parse_key_center(plan["key"]["center"]) if "key" in plan else None)

    groove = raw.get("groove")
    if isinstance(groove, dict):
        cleaned: dict[str, Any] = {}
        swing = _as_int(groove.get("swing"))
        if groove.get("swing") is not None:
            if swing is None or not 0 <= swing <= 60:
                dropped.append(f"groove.swing: {groove.get('swing')!r} is not 0-60")
            else:
                cleaned["swing"] = swing
        snap = groove.get("snap")
        if snap is not None:
            if snap in PLAN_SNAP_CHOICES:
                cleaned["snap"] = snap
            else:
                dropped.append(f"groove.snap: {snap!r} is not one of {', '.join(PLAN_SNAP_CHOICES)}")
        if cleaned:
            cleaned["reason"] = _reason(groove)
            plan["groove"] = cleaned

    description = _clean_text(raw.get("description"), 200)
    if description:
        plan["description"] = description

    arrangement_ids: dict[str, str] = {}
    if not musical_sections(spec):
        items = raw.get("arrangement")
        if isinstance(items, list):
            proposed: list[dict[str, Any]] = []
            for item in items[:12]:
                if not isinstance(item, dict):
                    continue
                kind = str(item.get("type") or "").strip().lower()
                if SECTION_BAR_HINTS.get(kind, 0) <= 0:
                    dropped.append(f"arrangement: section type {item.get('type')!r} is not one the renderer knows")
                    continue
                bars = _as_int(item.get("bars"))
                if bars is None or not 1 <= bars <= 64:
                    bars = SECTION_BAR_HINTS[kind]
                canonical = f"section-{len(proposed) + 1:02d}"
                if isinstance(item.get("id"), str):
                    arrangement_ids[item["id"]] = canonical
                roles = [role for role in (item.get("trackRoles") or []) if isinstance(role, str) and role in ROLE_TO_TRACKS][:8] if isinstance(item.get("trackRoles"), list) else []
                techniques = [str(t).lower() for t in (item.get("techniques") or []) if isinstance(t, str) and str(t).lower() in PLAN_TECHNIQUES][:6] if isinstance(item.get("techniques"), list) else []
                proposed.append({
                    "id": canonical,
                    "type": kind,
                    "label": _clean_text(item.get("label"), 40) or kind.replace("_", " ").title(),
                    "bars": bars,
                    "summary": _clean_text(item.get("summary"), 300) or f"Proposed {kind.replace('_', ' ')}",
                    "trackRoles": roles,
                    "plugins": [],
                    "techniques": techniques,
                    "inferred": True,
                    "source": "model",
                })
            if len(proposed) >= 2:
                plan["arrangement"] = proposed
            elif items:
                dropped.append("arrangement: fewer than two usable sections came back")

    if "arrangement" in plan:
        sections_by_id = {section["id"]: section for section in plan["arrangement"]}
    else:
        sections_by_id = {str(section.get("id")): section for section in musical_sections(spec) if section.get("id")}

    raw_sections = raw.get("sections")
    if isinstance(raw_sections, dict):
        planned_sections: dict[str, Any] = {}
        for raw_id, hints in raw_sections.items():
            section_id = arrangement_ids.get(str(raw_id), str(raw_id))
            section = sections_by_id.get(section_id)
            if section is None or not isinstance(hints, dict):
                dropped.append(f"sections.{raw_id}: not a section in this project")
                continue
            cleaned_section = _validate_section_plan(hints, section, plan_key, dropped)
            if cleaned_section:
                planned_sections[section_id] = cleaned_section
        if planned_sections:
            plan["sections"] = planned_sections

    tracks = raw.get("tracks")
    if isinstance(tracks, dict):
        lanes = choose_track_ids(apply_materialization_plan(spec, plan))
        named: dict[str, Any] = {}
        for track_id, value in tracks.items():
            if track_id not in lanes:
                dropped.append(f"tracks.{track_id}: not a lane in this project")
                continue
            if not isinstance(value, dict):
                continue
            entry = {key: text for key, text in (("name", _clean_text(value.get("name"), 40)), ("instrument", _clean_text(value.get("instrument"), 48))) if text}
            blueprint = TRACK_BLUEPRINTS.get(track_id)
            if blueprint is not None:
                # Echoing the lane's own name or instrument decides nothing; do not record it as a decision.
                entry = {key: text for key, text in entry.items() if text.lower() != getattr(blueprint, key).lower()}
            if entry:
                named[track_id] = entry
        if named:
            plan["tracks"] = named
    return plan, dropped


def _validate_section_plan(hints: dict[str, Any], section: dict[str, Any], key: tuple[int, str, str] | None, dropped: list[str]) -> dict[str, Any]:
    section_id = str(section.get("id"))
    bars = int(section.get("bars") or SECTION_BAR_HINTS.get(str(section.get("type")), 8) or 8)
    text = section_inference_text(section)
    lane_events = section.get("laneEvents") or {}
    lane_transforms = section.get("laneTransforms") or {}
    chords_pinned = lane_events.get("chords") or {}
    lead_transform = lane_transforms.get("lead") or {}
    drums_transform = lane_transforms.get("drums") or {}
    cleaned: dict[str, Any] = {}

    symbols = hints.get("progressionSymbols")
    if isinstance(symbols, list) and symbols:
        if chords_pinned.get("progressionSymbols") or extract_explicit_progression(text) or (lane_transforms.get("chords") or {}).get("copyFrom"):
            dropped.append(f"{section_id}.progressionSymbols: the walkthrough already states the chords here")
        else:
            shapes = [chord_symbol_to_shape(str(symbol).strip()) for symbol in symbols[:8] if isinstance(symbol, str)]
            kept = [shape for shape in shapes if shape]
            if len(kept) < 2:
                dropped.append(f"{section_id}.progressionSymbols: {symbols!r} did not parse as two or more chords")
            elif not _progression_fits_key(kept, key):
                dropped.append(f"{section_id}.progressionSymbols: {[s['name'] for s in kept]!r} is mostly outside {key[2] if key else 'the key'}")
            else:
                cleaned["progressionSymbols"] = [shape["name"] for shape in kept]
                cleaned["progressionReason"] = _reason(hints, "progressionReason", "reason")

    if "chordEvents" in hints:
        if chords_pinned.get("events"):
            dropped.append(f"{section_id}.chordEvents: the walkthrough already states the chord rhythm")
        else:
            events = _clean_rhythm_events(hints.get("chordEvents"), bars=bars, chord_flags=True)
            if events:
                cleaned["chordEvents"] = events
            else:
                dropped.append(f"{section_id}.chordEvents: no event had a beat in [0, 4) and a duration in (0, 4]")

    if "bassEvents" in hints:
        bass_transform = lane_transforms.get("bass") or {}
        if (lane_events.get("bass") or {}).get("events") or bass_transform.get("followChords") or bass_transform.get("copyFrom"):
            dropped.append(f"{section_id}.bassEvents: the walkthrough already states the bass rhythm")
        else:
            events = _clean_rhythm_events(hints.get("bassEvents"), bars=bars, chord_flags=False)
            if events:
                cleaned["bassEvents"] = events
            else:
                dropped.append(f"{section_id}.bassEvents: no event had a beat in [0, 4) and a duration in (0, 4]")

    motif_key = hints.get("leadMotifKey")
    if motif_key is not None:
        if lead_transform.get("copyFrom"):
            dropped.append(f"{section_id}.leadMotifKey: the lead here is copied from another section")
        elif motif_key in LEAD_MOTIF_LIBRARY:
            cleaned["leadMotifKey"] = motif_key
        else:
            dropped.append(f"{section_id}.leadMotifKey: {motif_key!r} is not one of {', '.join(LEAD_MOTIF_LIBRARY)}")

    if hints.get("leadTransposeSemitones") is not None:
        shift = _as_int(hints.get("leadTransposeSemitones"))
        if lead_transform.get("transposeSemitones") or parse_transpose_instruction(text):
            dropped.append(f"{section_id}.leadTransposeSemitones: the walkthrough already states a transposition")
        elif shift is None or not -24 <= shift <= 24:
            dropped.append(f"{section_id}.leadTransposeSemitones: {hints.get('leadTransposeSemitones')!r} is not -24..24")
        elif shift != 0 or section.get("type") == "second_drop":
            cleaned["leadTransposeSemitones"] = shift

    drums = hints.get("drums", hints.get("drumOverrides"))
    if drums is not None:
        if any(lane_events.get(lane) for lane in PLAN_DRUM_LANES) or drums_transform.get("copyFrom") or drums_transform.get("overrides"):
            dropped.append(f"{section_id}.drums: the walkthrough already states the drum pattern")
        elif extract_lane_beat_overrides(text):
            dropped.append(f"{section_id}.drums: the walkthrough names drum beats in words; those win")
        else:
            cleaned_drums = _clean_drums(drums, bars=bars)
            if cleaned_drums:
                cleaned["drums"] = cleaned_drums
            else:
                dropped.append(f"{section_id}.drums: nothing usable (beats must be in [0, 4))")

    fx = hints.get("fxProfile")
    if isinstance(fx, dict):
        profile = {name: fx[name] for name in PLAN_FX_KEYS if isinstance(fx.get(name), bool)}
        if profile:
            cleaned["fxProfile"] = profile

    if "automation" in hints:
        if (lane_events.get("automation") or {}).get("envelopes"):
            dropped.append(f"{section_id}.automation: the walkthrough already states the automation")
        else:
            envelopes = _clean_envelopes(hints.get("automation"), bars=bars)
            if envelopes:
                cleaned["automation"] = {"envelopes": envelopes}
            else:
                dropped.append(f"{section_id}.automation: no envelope had a known parameter, 0-1 values and bars inside the section")

    if hints.get("energy") is not None:
        energy = _as_float(hints.get("energy"))
        if energy is None or not 0.5 <= energy <= 1.5:
            dropped.append(f"{section_id}.energy: {hints.get('energy')!r} is not 0.5-1.5")
        else:
            cleaned["energy"] = round(energy, 2)

    if cleaned:
        reason = _reason(hints)
        if reason:
            cleaned["reason"] = reason
    return cleaned


def apply_materialization_plan(spec: dict[str, Any], plan: dict[str, Any] | None) -> dict[str, Any]:
    """A copy of the spec with the plan written in where the inference hooks read.

    Deterministic: the same spec and plan always give the same result, which is
    what keeps the emitted renderer identical between runs."""
    planned = deep_copy_jsonish(spec)
    if not plan:
        return planned
    if plan.get("tempo") and not planned.get("tempoHint"):
        planned["tempoHint"] = int(plan["tempo"]["bpm"])
    if plan.get("key") and not planned.get("keyHints"):
        planned["keyHints"] = [plan["key"]["center"]]
    if plan.get("arrangement") and not musical_sections(planned):
        extra = [section for section in (planned.get("sections") or []) if isinstance(section, dict)]
        planned["sections"] = deep_copy_jsonish(plan["arrangement"]) + extra
        if not planned.get("globalTracks"):
            roles: list[str] = []
            for section in plan["arrangement"]:
                for role in section.get("trackRoles") or []:
                    if role not in roles:
                        roles.append(role)
            planned["globalTracks"] = [
                {"name": role, "mentions": 1, "sections": [s["id"] for s in plan["arrangement"] if role in (s.get("trackRoles") or [])]}
                for role in roles
            ]
    by_id = {str(section.get("id")): section for section in (planned.get("sections") or []) if isinstance(section, dict)}
    for section_id, hints in (plan.get("sections") or {}).items():
        section = by_id.get(section_id)
        if section is None:
            continue
        lane_events = dict(section.get("laneEvents") or {})
        lane_transforms = dict(section.get("laneTransforms") or {})
        if hints.get("progressionSymbols"):
            chords = lane_events.setdefault("chords", {})
            chords.setdefault("kind", "progressionSymbols")
            chords["progressionSymbols"] = list(hints["progressionSymbols"])
            chords["progressionSource"] = "model"
        if hints.get("chordEvents"):
            chords = lane_events.setdefault("chords", {})
            chords.setdefault("kind", "rhythm")
            chords["events"] = deep_copy_jsonish(hints["chordEvents"])
            chords["source"] = "model"
        if hints.get("bassEvents"):
            lane_events["bass"] = {"kind": "rhythm", "events": deep_copy_jsonish(hints["bassEvents"]), "source": "model"}
        if hints.get("leadMotifKey"):
            lead = lane_transforms.setdefault("lead", {})
            lead["motifKey"] = hints["leadMotifKey"]
            lead["motifSource"] = "model"
        if hints.get("leadTransposeSemitones") is not None:
            lead = lane_transforms.setdefault("lead", {})
            lead["transposeSemitones"] = int(hints["leadTransposeSemitones"])
            lead["transposeSource"] = "model"
        drums = hints.get("drums") or {}
        for list_key, lane in PLAN_DRUM_LIST_KEYS:
            if drums.get(list_key):
                lane_events[lane] = {"kind": "beatPattern", "events": [{"beat": beat} for beat in drums[list_key]], "source": "model"}
                if lane == "hat" and drums.get("hatSpacing") is not None:
                    lane_events[lane]["spacingBeats"] = drums["hatSpacing"]
        overrides = {key: drums[key] for key in ("hatSpacing", "ride", "clapRoll", "crashBars") if key in drums}
        if overrides:
            drum_transform = lane_transforms.setdefault("drums", {})
            drum_transform["overrides"] = overrides
            drum_transform["overridesSource"] = "model"
        if hints.get("fxProfile"):
            fx = lane_transforms.setdefault("fx", {})
            fx["profile"] = dict(hints["fxProfile"])
            fx["profileSource"] = "model"
        if hints.get("automation"):
            lane_events["automation"] = {"envelopes": deep_copy_jsonish(hints["automation"]["envelopes"]), "source": "model"}
        if hints.get("energy") is not None:
            block = lane_transforms.setdefault("section", {})
            block["energy"] = float(hints["energy"])
            block["energySource"] = "model"
        if lane_events:
            section["laneEvents"] = lane_events
        if lane_transforms:
            section["laneTransforms"] = lane_transforms
    return planned


def plan_decisions(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """What the model decided, one line each, the way fillInBlanks records its decisions."""
    decisions: list[dict[str, Any]] = []

    def add(area: str, detail: str, reason: str = "", section_id: str | None = None) -> None:
        entry: dict[str, Any] = {"area": area, "detail": detail, "reason": reason, "source": "model"}
        if section_id:
            entry["sectionId"] = section_id
        decisions.append(entry)

    if plan.get("tempo"):
        add("tempo", f"{plan['tempo']['bpm']} BPM", plan["tempo"].get("reason", ""))
    if plan.get("key"):
        add("key", plan["key"]["center"], plan["key"].get("reason", ""))
    if plan.get("groove"):
        groove = plan["groove"]
        parts = [f"swing {groove['swing']}%" if "swing" in groove else "", f"snap {groove['snap']}" if "snap" in groove else ""]
        add("groove", ", ".join(part for part in parts if part), groove.get("reason", ""))
    if plan.get("description"):
        add("description", plan["description"])
    if plan.get("arrangement"):
        add("arrangement", " > ".join(f"{s['label']} ({s['bars']} bars)" for s in plan["arrangement"]), "the walkthrough gave no sections")
    for track_id, entry in (plan.get("tracks") or {}).items():
        add("track", f"{track_id}: {entry.get('name') or TRACK_BLUEPRINTS[track_id].name} / {entry.get('instrument') or TRACK_BLUEPRINTS[track_id].instrument}")
    for section_id, hints in (plan.get("sections") or {}).items():
        reason = hints.get("reason", "")
        if hints.get("progressionSymbols"):
            add("progression", " ".join(hints["progressionSymbols"]), hints.get("progressionReason") or reason, section_id)
        if hints.get("chordEvents"):
            add("chord rhythm", "beats " + " ".join(str(e["beat"]) for e in hints["chordEvents"]), reason, section_id)
        if hints.get("bassEvents"):
            add("bass rhythm", "beats " + " ".join(str(e["beat"]) for e in hints["bassEvents"]), reason, section_id)
        if hints.get("leadMotifKey"):
            add("lead motif", hints["leadMotifKey"] + (f", {hints['leadTransposeSemitones']:+d} st" if hints.get("leadTransposeSemitones") else ""), reason, section_id)
        elif hints.get("leadTransposeSemitones") is not None:
            add("lead transpose", f"{hints['leadTransposeSemitones']:+d} st", reason, section_id)
        if hints.get("drums"):
            drums = hints["drums"]
            bits = [f"{key} {' '.join(str(b) for b in drums[key])}" for key, _lane in PLAN_DRUM_LIST_KEYS if drums.get(key)]
            bits += [f"{key} {drums[key]}" for key in ("hatSpacing", "ride", "clapRoll", "crashBars") if key in drums]
            add("drums", "; ".join(bits), reason, section_id)
        if hints.get("fxProfile"):
            add("fx", ", ".join(f"{name} {'on' if on else 'off'}" for name, on in hints["fxProfile"].items()), reason, section_id)
        if hints.get("automation"):
            add("automation", "; ".join(f"{e['parameter']} {e['start']}->{e['end']} over {e['bars']} bar(s)" + (f" on {e['targetLane']}" if e.get("targetLane") else "") for e in hints["automation"]["envelopes"]), reason, section_id)
        if hints.get("energy") is not None:
            add("energy", str(hints["energy"]), reason, section_id)
    return decisions


def propose_musical_plan(spec: dict[str, Any], project_id: str, prompt: str | None, assist: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """Ask, validate, and describe. Returns (plan, materialization block for the project)."""
    if assist is None and Assist is not None:
        assist = Assist(enabled=False)
    raw, notes = ask_musical_plan(spec, project_id, prompt, assist)
    plan, dropped = validate_musical_plan(raw, spec) if raw is not None else ({}, [])
    report = assist.report() if assist is not None else {"used": False, "provider": None, "model": None, "note": "no model adapter"}
    extra = list(notes)
    if raw is not None and not plan:
        extra.append("the model answered, but nothing in the answer fit this project")
    if dropped:
        extra.append(f"{len(dropped)} answer(s) dropped in validation")
    if extra:
        report["note"] = "; ".join(part for part in [report.get("note") or ""] + extra if part)
    materialization = {
        "source": "model" if plan else "heuristic",
        "plan": plan,
        "decisions": plan_decisions(plan),
        "dropped": dropped,
    }
    return plan, {"ai": report, "materialization": materialization}


# The filter moves the generated renderer performs, as automation lanes in the
# project - so the app's automation view shows what the render does, and a
# fidelity check can see the move without listening.
AUTOMATION_OPEN_TYPES = ("pre_intro", "intro", "verse", "pre_build")
AUTOMATION_CLOSE_TYPES = ("break", "outro")


def technique_automation_lanes(section_layout: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lanes: list[dict[str, Any]] = []
    for section in section_layout:
        techniques = [str(t).strip().lower() for t in (section.get("techniques") or [])]
        kind = str(section.get("type") or "")
        move: tuple[float, float, str] | None = None
        if kind == "build" and ("filtering" in techniques or "automation" in techniques):
            move = (0.15, 0.92, "sweeps open")
        elif "filtering" in techniques and kind in AUTOMATION_OPEN_TYPES:
            move = (0.35, 0.9, "opens")
        elif "filtering" in techniques and kind in AUTOMATION_CLOSE_TYPES:
            move = (0.9, 0.35, "closes")
        elif "automation" in techniques and kind in ("drop", "second_drop"):
            move = (0.45, 0.9, "opens across the drop")
        if move is None:
            continue
        start_bar = float(section.get("startBar") or 0)
        bars = float(section.get("bars") or 0)
        if bars <= 0:
            continue
        lanes.append({
            "id": f"auto-{section.get('id', kind)}-filter",
            "trackId": "filter-auto",
            "parameter": "filter",
            "label": f"{section.get('label') or kind.title()}: filter {move[2]}",
            "color": "#7dd3fc",
            "enabled": True,
            "curve": "exponential",
            "points": [
                {"bar": start_bar, "value": move[0]},
                {"bar": start_bar + bars, "value": move[1]},
            ],
        })
    return lanes


def renderer_section_name(section_type: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", section_type.lower()).strip("_") or "section"


def renderer_function_name(section: dict[str, Any], index: int) -> str:
    return f"{index:02d}_{renderer_section_name(section['type'])}"


def renderer_track_name(track_id: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", track_id.lower()).strip("_") or "track"


def python_literal(value: Any) -> str:
    return pprint.pformat(value, width=100, sort_dicts=False)


def renderer_doc(prompt: str | None, project_id: str, project_name: str) -> str:
    title = prompt or project_name
    return f"""Generated renderer for {project_name}.

This file was generated from a transcript-driven Songlab session.
It already carries the project structure:
- transcript-derived section plan
- track layout from the generated .neon.json
- section-specific production notes, plugin hints, and techniques

Edit this file when turning the generated project into a fuller render implementation.

Primary inputs:
- data/projects/{project_id}.neon.json
- factory/projects/{project_id}.neon.json
- songlab/projects/{project_id}/transcript_spec.json
- songlab/projects/{project_id}/project_summary.md

Original brief:
{title}
"""


def render_track_plan(project: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": track["id"],
            "name": track["name"],
            "instrument": track["instrument"],
            "kind": track["kind"],
            "color": track["color"],
            "gain": track.get("gain", 0.8),
            "pan": track.get("pan", 0.0),
            "steps": list(track.get("steps", [])),
            "clips": [
                {
                    "name": clip["name"],
                    "startBar": clip["startBar"],
                    "bars": clip["bars"],
                    "type": clip["type"],
                }
                for clip in track.get("clips", [])
            ],
            "effects": [effect["name"] for effect in track.get("effects", [])],
        }
        for track in project["snapshot"]["tracks"]
    ]


# Techniques a producer states about the track as a whole ("I put OTT on the
# drums", "everything is high-passed") are processing that stays on, so they
# apply to every section. One-off moves (a reverse, a filter sweep) do not.
WHOLE_TRACK_TECHNIQUES = ("eq", "compression", "distortion", "stereo", "sidechain", "reverb", "delay", "layering")


def whole_track_techniques(spec: dict[str, Any]) -> list[str]:
    found: list[str] = []
    for section in spec.get("sections", []) or []:
        if not isinstance(section, dict) or section.get("type") != "production_notes":
            continue
        for technique in section.get("techniques", []) or []:
            name = str(technique).strip().lower()
            if name in WHOLE_TRACK_TECHNIQUES and name not in found:
                found.append(name)
    return found


def render_section_plan(project: dict[str, Any], spec: dict[str, Any]) -> list[dict[str, Any]]:
    # The musical plan lives on the project, never in the renderer: applying it
    # here (deterministically) is what keeps the emitted file identical for the
    # same project + spec, with or without a model in the loop.
    plan = (project.get("materialization") or {}).get("plan") or {}
    if plan:
        spec = apply_materialization_plan(spec, plan)
    tracks = {track["id"]: track for track in project["snapshot"]["tracks"]}
    recipe_by_section = {item["section"]: item for item in project["snapshot"].get("recipe", [])[1:]}
    sections = normalized_sections(spec)
    layout = section_bar_layout(sections)
    global_techniques = whole_track_techniques(spec)
    plan: list[dict[str, Any]] = []
    defaults_by_section_id: dict[str, dict[str, Any]] = {}
    for section in layout:
        section_track_ids = track_ids_for_section(section, list(tracks.keys()))
        starter_defaults = infer_section_starter_defaults(section, spec, plan, defaults_by_section_id)
        defaults_by_section_id[section["id"]] = starter_defaults
        plan.append(
            {
                "id": section["id"],
                "type": section["type"],
                "label": section["label"],
                "startBar": section["startBar"],
                "bars": section["bars"],
                "summary": section.get("summary"),
                "trackRoles": section.get("trackRoles", []),
                "trackIds": section_track_ids,
                "plugins": section.get("plugins", []),
                "techniques": list(section.get("techniques", []) or []) + [t for t in global_techniques if t not in (section.get("techniques", []) or [])],
                "laneEvents": deep_copy_jsonish(section.get("laneEvents", {}) or {}),
                "laneTransforms": deep_copy_jsonish(section.get("laneTransforms", {}) or {}),
                "recipeDetail": recipe_by_section.get(section["label"], {}).get("detail"),
                "starterDefaults": starter_defaults,
            }
        )
    return plan


ROLE_GUIDANCE: dict[str, str] = {
    "drums": "Program the core groove, kick placement, and transient balance for this section.",
    "clap-stack": "Decide whether this lane is backbeat support, clap roll, or a wider impact layer.",
    "hat-ride": "Define the high-frequency motion, hat density, and any ride/crash escalation.",
    "bass": "Lock bass rhythm to the section pulse and decide the mid-bass character.",
    "sub": "Anchor the low end with note lengths that support the drop without muddying transitions.",
    "chords": "Write the harmonic bed, voicing spread, and sidechain shape for the section.",
    "lead": "Carry the hook or teaser phrase and decide how busy the melodic contour should be.",
    "guitar": "Use this as a lighter support layer so it adds motion without crowding the lead.",
    "plucks": "Place pluck accents where they help define rhythm or harmonic movement.",
    "vocals": "Use chops or phrases only where they reinforce the section identity and transitions.",
    "fx": "Cover risers, impacts, reverses, and spatial glue that mark the section change.",
    "filter-auto": "Shape the macro automation so the arrangement tension is visible and audible.",
    "sample": "Map the sampled texture to the section and decide slice/stretch behavior.",
}


BRIGHT_UPLIFT_PROGRESSION = [
    {"name": "Em7", "notes": [52, 55, 59, 62], "root": 40},
    {"name": "Cmaj7", "notes": [48, 52, 55, 59], "root": 36},
    {"name": "Gadd9", "notes": [43, 47, 50, 55], "root": 31},
    {"name": "Dadd9", "notes": [50, 54, 57, 62], "root": 38},
]

MAJOR_POP_PROGRESSION = [
    {"name": "Cmaj7", "notes": [48, 52, 55, 59], "root": 36},
    {"name": "Gadd9", "notes": [43, 47, 50, 55], "root": 31},
    {"name": "Am7", "notes": [45, 48, 52, 55], "root": 33},
    {"name": "Fmaj7", "notes": [41, 45, 48, 52], "root": 29},
]

DARK_TRAP_PROGRESSION = [
    {"name": "Em", "notes": [52, 55, 59, 64], "root": 40},
    {"name": "D", "notes": [50, 54, 57, 62], "root": 38},
    {"name": "C", "notes": [48, 52, 55, 60], "root": 36},
    {"name": "Bm", "notes": [47, 50, 54, 59], "root": 35},
]

LEAD_MOTIF_LIBRARY: dict[str, list[list[dict[str, float | int]]]] = {
    "sparse": [
        [{"beat": 0.00, "duration": 0.45, "note": 76}, {"beat": 1.02, "duration": 0.70, "note": 83}, {"beat": 2.56, "duration": 0.66, "note": 76}],
        [{"beat": 0.00, "duration": 0.42, "note": 79}, {"beat": 1.00, "duration": 0.68, "note": 83}, {"beat": 2.56, "duration": 0.72, "note": 74}],
        [{"beat": 0.00, "duration": 0.42, "note": 83}, {"beat": 1.02, "duration": 0.68, "note": 83}, {"beat": 2.50, "duration": 0.72, "note": 76}],
        [{"beat": 0.00, "duration": 0.40, "note": 79}, {"beat": 1.45, "duration": 0.38, "note": 76}, {"beat": 2.10, "duration": 0.78, "note": 79}],
    ],
    "dense": [
        [{"beat": 0.00, "duration": 0.45, "note": 76}, {"beat": 0.52, "duration": 0.38, "note": 79}, {"beat": 1.02, "duration": 0.70, "note": 83}, {"beat": 2.02, "duration": 0.42, "note": 79}, {"beat": 2.56, "duration": 0.66, "note": 76}],
        [{"beat": 0.00, "duration": 0.42, "note": 79}, {"beat": 0.48, "duration": 0.38, "note": 81}, {"beat": 1.00, "duration": 0.68, "note": 83}, {"beat": 2.04, "duration": 0.42, "note": 79}, {"beat": 2.56, "duration": 0.72, "note": 74}],
        [{"beat": 0.00, "duration": 0.42, "note": 83}, {"beat": 0.52, "duration": 0.38, "note": 84}, {"beat": 1.02, "duration": 0.68, "note": 83}, {"beat": 2.00, "duration": 0.42, "note": 79}, {"beat": 2.50, "duration": 0.72, "note": 76}],
        [{"beat": 0.00, "duration": 0.40, "note": 79}, {"beat": 0.46, "duration": 0.36, "note": 76}, {"beat": 0.92, "duration": 0.38, "note": 74}, {"beat": 1.45, "duration": 0.38, "note": 76}, {"beat": 2.10, "duration": 0.78, "note": 79}],
    ],
    "tease": [
        [{"beat": 0.00, "duration": 0.34, "note": 76}, {"beat": 0.52, "duration": 0.28, "note": 79}],
        [{"beat": 0.00, "duration": 0.34, "note": 79}, {"beat": 0.48, "duration": 0.28, "note": 81}],
        [{"beat": 0.00, "duration": 0.34, "note": 83}, {"beat": 0.52, "duration": 0.28, "note": 84}],
        [{"beat": 0.00, "duration": 0.34, "note": 79}, {"beat": 0.46, "duration": 0.28, "note": 76}],
    ],
    "dark": [
        [{"beat": 0.00, "duration": 0.50, "note": 71}, {"beat": 1.00, "duration": 0.66, "note": 74}, {"beat": 2.50, "duration": 0.62, "note": 71}],
        [{"beat": 0.00, "duration": 0.46, "note": 74}, {"beat": 0.92, "duration": 0.62, "note": 78}, {"beat": 2.42, "duration": 0.70, "note": 74}],
        [{"beat": 0.00, "duration": 0.50, "note": 78}, {"beat": 1.04, "duration": 0.58, "note": 79}, {"beat": 2.46, "duration": 0.66, "note": 74}],
        [{"beat": 0.00, "duration": 0.44, "note": 74}, {"beat": 1.30, "duration": 0.44, "note": 71}, {"beat": 2.02, "duration": 0.82, "note": 69}],
    ],
}


NOTE_TO_SEMITONE = {
    "C": 0,
    "C#": 1,
    "Db": 1,
    "D": 2,
    "D#": 3,
    "Eb": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "Gb": 6,
    "G": 7,
    "G#": 8,
    "Ab": 8,
    "A": 9,
    "A#": 10,
    "Bb": 10,
    "B": 11,
}

CHORD_QUALITY_INTERVALS: list[tuple[re.Pattern[str], list[int], str]] = [
    (re.compile(r"maj9$", re.IGNORECASE), [0, 4, 7, 11, 14], "maj9"),
    (re.compile(r"maj7$", re.IGNORECASE), [0, 4, 7, 11], "maj7"),
    (re.compile(r"m9$|min9$", re.IGNORECASE), [0, 3, 7, 10, 14], "m9"),
    (re.compile(r"m7$|min7$", re.IGNORECASE), [0, 3, 7, 10], "m7"),
    (re.compile(r"add9$", re.IGNORECASE), [0, 4, 7, 14], "add9"),
    (re.compile(r"sus2$", re.IGNORECASE), [0, 2, 7], "sus2"),
    (re.compile(r"sus4$", re.IGNORECASE), [0, 5, 7], "sus4"),
    (re.compile(r"dim$", re.IGNORECASE), [0, 3, 6], "dim"),
    (re.compile(r"aug$", re.IGNORECASE), [0, 4, 8], "aug"),
    (re.compile(r"m$|min$", re.IGNORECASE), [0, 3, 7], "m"),
    (re.compile(r"9$", re.IGNORECASE), [0, 4, 7, 10, 14], "9"),
    (re.compile(r"7$", re.IGNORECASE), [0, 4, 7, 10], "7"),
    (re.compile(r"5$", re.IGNORECASE), [0, 7], "5"),
]

CHORD_SYMBOL_RE = re.compile(
    r"\b([A-G](?:#|b)?(?:maj9|maj7|min9|min7|min|m9|m7|m|add9|sus2|sus4|dim|aug|9|7|5)?)\b"
)


def overlapping_clips(track: dict[str, Any], section: dict[str, Any]) -> list[dict[str, Any]]:
    section_start = int(section["startBar"])
    section_end = section_start + int(section["bars"])
    relevant: list[dict[str, Any]] = []
    for clip in track.get("clips", []):
        clip_start = int(clip["startBar"])
        clip_end = clip_start + int(clip["bars"])
        if clip_end <= section_start or clip_start >= section_end:
            continue
        relevant.append(clip)
    return relevant


def lower_join(*parts: Any) -> str:
    return " ".join(str(part).lower() for part in parts if part)


def deep_copy_jsonish(value: Any) -> Any:
    return json.loads(json.dumps(value))


def find_section_reference(text: str, prior_sections: list[dict[str, Any]], fallback_section: dict[str, Any] | None = None) -> dict[str, Any] | None:
    lowered = text.lower()
    for keyword, section_type in (
        ("pre intro", "pre_intro"),
        ("intro", "intro"),
        ("verse", "verse"),
        ("pre build", "pre_build"),
        ("build", "build"),
        ("drop", "drop"),
        ("second drop", "second_drop"),
        ("break", "break"),
        ("outro", "outro"),
    ):
        if keyword in lowered:
            for section in reversed(prior_sections):
                if section["type"] == section_type:
                    return section
    return fallback_section


def find_section_by_type(prior_sections: list[dict[str, Any]], section_type: str) -> dict[str, Any] | None:
    for section in reversed(prior_sections):
        if section["type"] == section_type:
            return section
    return None


def extract_referenced_section_type(text: str) -> str | None:
    for pattern, section_type in (
        (r"second drop", "second_drop"),
        (r"pre[\s-]?build", "pre_build"),
        (r"pre[\s-]?intro", "pre_intro"),
        (r"\bintro\b", "intro"),
        (r"\bverse\b", "verse"),
        (r"\bbuild\b", "build"),
        (r"\bdrop\b", "drop"),
        (r"\bbreak\b", "break"),
        (r"\boutro\b", "outro"),
    ):
        if re.search(pattern, text):
            return section_type
    return None


def nearest_prior_with_roles(prior_sections: list[dict[str, Any]], roles: tuple[str, ...]) -> dict[str, Any] | None:
    role_set = set(roles)
    for section in reversed(prior_sections):
        if role_set & set(section.get("trackRoles", [])):
            return section
    return prior_sections[-1] if prior_sections else None


def resolve_lead_reference(text: str, prior_sections: list[dict[str, Any]]) -> dict[str, Any] | None:
    explicit = re.search(r"same melody(?:\s+from\s+the\s+([a-z\s-]+))?", text)
    if explicit:
        target = extract_referenced_section_type(explicit.group(1) or "")
        if target:
            found = find_section_by_type(prior_sections, target)
            if found:
                return found
        return nearest_prior_with_roles(prior_sections, ("lead", "chords", "pluck"))
    return None


def resolve_bass_reference(text: str, prior_sections: list[dict[str, Any]]) -> dict[str, Any] | None:
    explicit = re.search(r"bass .*same notes from the ([a-z\s-]+)", text)
    if not explicit:
        explicit = re.search(r"plays the same notes from the ([a-z\s-]+)", text)
    if explicit:
        target = extract_referenced_section_type(explicit.group(1))
        if target:
            found = find_section_by_type(prior_sections, target)
            if found:
                return found
    if "same notes" in text:
        return nearest_prior_with_roles(prior_sections, ("bass", "sub", "chords"))
    return None


def resolve_chord_reference(text: str, prior_sections: list[dict[str, Any]]) -> dict[str, Any] | None:
    explicit = re.search(r"same (?:chords?|progression)(?:\s+from\s+the\s+([a-z\s-]+))?", text)
    if explicit:
        target = extract_referenced_section_type(explicit.group(1) or "")
        if target:
            found = find_section_by_type(prior_sections, target)
            if found:
                return found
        return nearest_prior_with_roles(prior_sections, ("chords", "pad", "pluck"))
    return None


def resolve_drum_reference(text: str, prior_sections: list[dict[str, Any]]) -> dict[str, Any] | None:
    explicit = re.search(r"same drum(?:s| pattern| beat)?(?:\s+from\s+the\s+([a-z\s-]+))?", text)
    if explicit:
        target = extract_referenced_section_type(explicit.group(1) or "")
        if target:
            found = find_section_by_type(prior_sections, target)
            if found:
                return found
        return nearest_prior_with_roles(prior_sections, ("drums", "kick", "snare", "clap", "hat", "ride"))
    return None


def densify_motif(motif: list[list[dict[str, float | int]]]) -> list[list[dict[str, float | int]]]:
    densified: list[list[dict[str, float | int]]] = []
    for bar in motif:
        ordered = [dict(item) for item in bar]
        extra: list[dict[str, float | int]] = []
        for left, right in zip(ordered, ordered[1:]):
            gap = float(right["beat"]) - float(left["beat"])
            if gap < 0.55:
                continue
            extra.append(
                {
                    "beat": round(float(left["beat"]) + gap / 2.0, 2),
                    "duration": round(min(0.34, max(0.18, gap / 2.4)), 2),
                    "note": int(right["note"]),
                }
            )
        merged = ordered + extra
        merged.sort(key=lambda item: (float(item["beat"]), int(item["note"])))
        densified.append(merged)
    return densified


def lighten_progression(progression: list[dict[str, Any]]) -> list[dict[str, Any]]:
    light: list[dict[str, Any]] = []
    for chord in progression:
        notes = [int(note) for note in chord["notes"]]
        lifted = [note + 1 if idx == len(notes) - 1 and note % 12 in {10, 11} else note for idx, note in enumerate(notes)]
        updated = dict(chord)
        updated["notes"] = lifted
        updated["root"] = int(chord["root"])
        light.append(updated)
    return light


def transpose_progression(progression: list[dict[str, Any]], semitones: int) -> list[dict[str, Any]]:
    shifted: list[dict[str, Any]] = []
    for chord in progression:
        updated = dict(chord)
        updated["notes"] = [int(note) + semitones for note in chord["notes"]]
        updated["root"] = int(chord["root"]) + semitones
        shifted.append(updated)
    return shifted


def transpose_motif(motif: list[list[dict[str, float | int]]], semitones: int) -> list[list[dict[str, float | int]]]:
    shifted: list[list[dict[str, float | int]]] = []
    for bar in motif:
        shifted.append([{**event, "note": int(event["note"]) + semitones} for event in bar])
    return shifted


def chord_symbol_to_shape(symbol: str, *, base_octave: int = 48) -> dict[str, Any] | None:
    match = re.match(r"^([A-G](?:#|b)?)(.*)$", symbol)
    if not match:
        return None
    root_name, suffix = match.groups()
    semitone = NOTE_TO_SEMITONE.get(root_name)
    if semitone is None:
        return None
    intervals = [0, 4, 7]
    normalized_suffix = suffix or ""
    quality_name = "maj"
    for pattern, candidate_intervals, candidate_name in CHORD_QUALITY_INTERVALS:
        if pattern.search(normalized_suffix):
            intervals = candidate_intervals
            quality_name = candidate_name
            break
    root = base_octave + semitone
    return {
        "name": symbol,
        "quality": quality_name,
        "notes": [root + interval for interval in intervals],
        "root": root,
    }


def extract_explicit_progression(text: str) -> list[dict[str, Any]] | None:
    symbols = [match.group(1) for match in CHORD_SYMBOL_RE.finditer(text)]
    if len(symbols) < 2:
        return None
    progression: list[dict[str, Any]] = []
    seen_run: list[str] = []
    for symbol in symbols[:8]:
        shape = chord_symbol_to_shape(symbol)
        if not shape:
            continue
        progression.append(shape)
        seen_run.append(symbol)
    return progression or None


def parse_transpose_instruction(text: str) -> int:
    lowered = text.lower()
    if "down an octave" in lowered:
        return -12
    if "up an octave" in lowered:
        return 12
    match = re.search(r"(?:transpose|transposed|pitched?)\s+(up|down)\s+(\d+)\s*(?:semi(?:tone)?s?|st)\b", lowered)
    if match:
        sign = 1 if match.group(1) == "up" else -1
        return sign * int(match.group(2))
    match = re.search(r"([+-]\d+)\s*(?:semi(?:tone)?s?|st)\b", lowered)
    if match:
        return int(match.group(1))
    return 0


def parse_beat_value(token: str) -> float | None:
    normalized = token.strip().lower()
    if normalized in {"offbeat", "off beat", "off-beat"}:
        return None
    match = re.match(r"(\d(?:\.\d+)?)$", normalized)
    if not match:
        return None
    raw = float(match.group(1))
    if raw < 1.0:
        return round(raw, 2)
    return round(raw - 1.0, 2)


def parse_beat_list(fragment: str) -> list[float]:
    lowered = fragment.lower()
    if "offbeat" in lowered or "off beat" in lowered or "off-beat" in lowered:
        return [0.5, 1.5, 2.5, 3.5]
    tokens = re.findall(r"\d(?:\.\d+)?", lowered)
    beats: list[float] = []
    for token in tokens:
        parsed = parse_beat_value(token)
        if parsed is not None:
            beats.append(parsed)
    return beats


def extract_lane_beat_overrides(text: str) -> dict[str, Any]:
    lowered = text.lower()
    overrides: dict[str, Any] = {}
    stop = r"(?:kick(?: drums?)?|snare(?: drums?)?|clap(?: stacks?)?|hi-hats?|hihats?|hats?|rides?|crashes?)"
    pattern_specs = (
        ("kicks", rf"kick(?: drum)?s?(?:\s+(?:on|at|hits? on|plays? on))?\s+(.+?)(?=(?:\b{stop}\b|[.;]|$))"),
        ("snares", rf"snare(?: drum)?s?(?:\s+(?:on|at|hits? on|plays? on))?\s+(.+?)(?=(?:\b{stop}\b|[.;]|$))"),
        ("claps", rf"clap(?: stack)?s?(?:\s+(?:on|at|hits? on|plays? on))?\s+(.+?)(?=(?:\b{stop}\b|[.;]|$))"),
        ("hats", rf"(?:hi-hat|hihat|hat)s?(?:\s+(?:on|at|hits? on|plays? on))?\s+(.+?)(?=(?:\b{stop}\b|[.;]|$))"),
        ("ride", rf"ride(?:s)?(?:\s+(?:on|at|hits? on|plays? on))?\s+(.+?)(?=(?:\b{stop}\b|[.;]|$))"),
        ("crashBars", rf"crash(?:es)?(?:\s+(?:on|at|hits? on|plays? on))?\s+(.+?)(?=(?:\b{stop}\b|[.;]|$))"),
    )
    for key, pattern in pattern_specs:
        match = re.search(pattern, lowered)
        if not match:
            continue
        beats = parse_beat_list(match.group(1))
        if not beats:
            continue
        if key == "ride":
            overrides["ride"] = True
        elif key == "crashBars":
            overrides["crashBars"] = [int(beat) for beat in beats]
        else:
            overrides[key] = beats
    if "eighth note" in lowered or "eighth-note" in lowered:
        overrides["hatSpacing"] = 0.5
    if "sixteenth note" in lowered or "sixteenth-note" in lowered:
        overrides["hatSpacing"] = 0.25
    if "triplet" in lowered:
        overrides["hatSpacing"] = round(1.0 / 3.0, 3)
    return overrides


def merge_drum_pattern(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overrides.items():
        merged[key] = value
    return merged


def resolve_transform_reference(reference: dict[str, Any] | None, prior_sections: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not reference:
        return None
    section_id = reference.get("sectionId")
    if section_id:
        for section in prior_sections:
            if section.get("id") == section_id:
                return section
    section_type = reference.get("sectionType")
    ordinal = reference.get("ordinal")
    if not section_type:
        return None
    matches = [section for section in prior_sections if section.get("type") == section_type]
    if ordinal is not None:
        for section in matches:
            if section.get("ordinalWithinType") == ordinal:
                return section
    return matches[-1] if matches else None


def progression_from_symbols(symbols: list[str]) -> list[dict[str, Any]] | None:
    progression: list[dict[str, Any]] = []
    for symbol in symbols:
        shape = chord_symbol_to_shape(symbol)
        if shape:
            progression.append(shape)
    return progression or None


def motif_from_lane_events(
    events: list[dict[str, Any]],
    template_motif: list[list[dict[str, float | int]]],
) -> list[list[dict[str, float | int]]]:
    if not events:
        return deep_copy_jsonish(template_motif)
    default_events = [event for event in events if "barOffset" not in event]
    scoped_by_bar: dict[int, list[dict[str, Any]]] = {}
    for event in events:
        if "barOffset" in event:
            scoped_by_bar.setdefault(int(event["barOffset"]), []).append(event)
    total_bars = max(len(template_motif), (max(scoped_by_bar) + 1) if scoped_by_bar else 0)
    if total_bars <= 0:
        total_bars = len(template_motif) or 1
    motif: list[list[dict[str, float | int]]] = []
    for local_bar in range(total_bars):
        template_bar = template_motif[local_bar % len(template_motif)] if template_motif else []
        source_events = scoped_by_bar.get(local_bar) or default_events
        if not source_events:
            motif.append(deep_copy_jsonish(template_bar))
            continue
        notes = [int(item["note"]) for item in template_bar] or [76, 79, 83]
        durations = [float(item["duration"]) for item in template_bar] or [0.42]
        bar_events: list[dict[str, float | int]] = []
        for index, event in enumerate(source_events):
            item: dict[str, float | int] = {
                "beat": round(float(event["beat"]), 2),
                "duration": round(float(event.get("duration", durations[index % len(durations)])), 2),
                "note": int(event.get("note", notes[index % len(notes)])),
            }
            for key in ("accent", "gain", "pan", "ghost"):
                if key in event:
                    item[key] = event[key]
            bar_events.append(item)
        motif.append(bar_events)
    return motif


def materialize_chord_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    materialized: list[dict[str, Any]] = []
    for event in events:
        updated = deep_copy_jsonish(event)
        symbol = updated.get("symbol")
        if symbol and "notes" not in updated:
            shape = chord_symbol_to_shape(str(symbol))
            if shape:
                updated["notes"] = shape["notes"]
                updated["root"] = shape["root"]
                updated["name"] = shape["name"]
        materialized.append(updated)
    return materialized


def lane_events_to_pattern(events: list[dict[str, Any]]) -> list[float]:
    return [round(float(event["beat"]), 2) for event in events if "beat" in event]


def infer_spacing_from_beats(beats: list[float]) -> float | None:
    if len(beats) < 2:
        return None
    diffs = [round(float(right) - float(left), 3) for left, right in zip(beats, beats[1:]) if float(right) > float(left)]
    if not diffs:
        return None
    first = diffs[0]
    if all(abs(diff - first) <= 0.02 for diff in diffs[1:]):
        return first
    return None


def scoped_events_for_bar(events: list[dict[str, Any]], local_bar: int) -> list[dict[str, Any]]:
    scoped = [event for event in events if event.get("barOffset") == local_bar]
    if scoped:
        return scoped
    return [event for event in events if "barOffset" not in event]


def grouped_pattern_for_bar(events: list[dict[str, Any]]) -> tuple[list[float], dict[int, list[float]]]:
    defaults = lane_events_to_pattern([event for event in events if "barOffset" not in event])
    scoped: dict[int, list[float]] = {}
    for event in events:
        if "barOffset" not in event:
            continue
        bar = int(event["barOffset"])
        scoped.setdefault(bar, []).append(round(float(event["beat"]), 2))
    for bar, beats in list(scoped.items()):
        ordered: list[float] = []
        seen: set[float] = set()
        for beat in sorted(beats):
            if beat in seen:
                continue
            seen.add(beat)
            ordered.append(beat)
        scoped[bar] = ordered
    return defaults, scoped


def grouped_event_data_for_bar(events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[int, list[dict[str, Any]]]]:
    defaults = [deep_copy_jsonish({key: value for key, value in event.items() if key != "barOffset"}) for event in events if "barOffset" not in event]
    scoped: dict[int, list[dict[str, Any]]] = {}
    for event in events:
        if "barOffset" not in event:
            continue
        bar = int(event["barOffset"])
        scoped.setdefault(bar, []).append(deep_copy_jsonish({key: value for key, value in event.items() if key != "barOffset"}))
    return defaults, scoped


def bass_events_from_follow_chords(omit_beats: list[float] | None = None) -> list[dict[str, Any]]:
    omit = {round(float(beat), 2) for beat in (omit_beats or [])}
    beats = [beat for beat in [0.0, 1.0, 2.0, 3.0] if round(beat, 2) not in omit]
    if not beats:
        beats = [0.0, 2.0]
    events: list[dict[str, Any]] = []
    for index, beat in enumerate(beats):
        next_beat = beats[index + 1] if index + 1 < len(beats) else 4.0
        duration = round(max(0.35, next_beat - beat - 0.08), 2)
        events.append({"beat": round(beat, 2), "duration": duration})
    return events


def apply_lane_events_to_drum_pattern(base: dict[str, Any], lane_events: dict[str, Any]) -> dict[str, Any]:
    pattern = dict(base)
    scoped_bars: dict[str, dict[str, Any]] = deep_copy_jsonish(pattern.get("scopedBars", {}))
    event_data: dict[str, list[dict[str, Any]]] = deep_copy_jsonish(pattern.get("eventData", {}))
    scoped_event_data: dict[str, dict[str, list[dict[str, Any]]]] = deep_copy_jsonish(pattern.get("scopedEventData", {}))
    mapping = (
        ("kick", "kicks"),
        ("snare", "snares"),
        ("clap", "claps"),
        ("hat", "hats"),
    )
    for lane, target_key in mapping:
        payload = lane_events.get(lane) or {}
        if payload.get("events"):
            defaults, scoped = grouped_pattern_for_bar(payload["events"])
            default_event_data, scoped_event_map = grouped_event_data_for_bar(payload["events"])
            if defaults:
                pattern[target_key] = defaults
                event_data[target_key] = default_event_data
            for bar, beats in scoped.items():
                scoped_bars.setdefault(str(bar), {})[target_key] = beats
                scoped_event_data.setdefault(str(bar), {})[target_key] = scoped_event_map.get(bar, [])
                if lane == "hat":
                    spacing = infer_spacing_from_beats(beats)
                    if spacing is not None:
                        scoped_bars[str(bar)]["hatSpacing"] = spacing
        if lane == "hat" and payload.get("spacingBeats") is not None and payload.get("events"):
            pattern["hatSpacing"] = float(payload["spacingBeats"])
    ride_payload = lane_events.get("ride") or {}
    if ride_payload.get("events"):
        defaults, scoped = grouped_pattern_for_bar(ride_payload["events"])
        default_event_data, scoped_event_map = grouped_event_data_for_bar(ride_payload["events"])
        if defaults:
            pattern["ride"] = True
            pattern["rideBeats"] = defaults
            event_data["rideBeats"] = default_event_data
        for bar, beats in scoped.items():
            scoped_bars.setdefault(str(bar), {})["rideBeats"] = beats
            scoped_bars[str(bar)]["ride"] = True
            scoped_event_data.setdefault(str(bar), {})["rideBeats"] = scoped_event_map.get(bar, [])
    crash_payload = lane_events.get("crash") or {}
    if crash_payload.get("events"):
        defaults, scoped = grouped_pattern_for_bar(crash_payload["events"])
        default_event_data, scoped_event_map = grouped_event_data_for_bar(crash_payload["events"])
        if defaults:
            pattern["crashBeats"] = defaults
            event_data["crashBeats"] = default_event_data
        for bar, beats in scoped.items():
            scoped_bars.setdefault(str(bar), {})["crashBeats"] = beats
            scoped_event_data.setdefault(str(bar), {})["crashBeats"] = scoped_event_map.get(bar, [])
    if scoped_bars:
        pattern["scopedBars"] = scoped_bars
    if event_data:
        pattern["eventData"] = event_data
    if scoped_event_data:
        pattern["scopedEventData"] = scoped_event_data
    return pattern


def infer_automation_profile(section: dict[str, Any], lane_events: dict[str, Any]) -> dict[str, Any]:
    automation_payload = lane_events.get("automation") or {}
    if automation_payload.get("envelopes"):
        envelopes = deep_copy_jsonish(automation_payload["envelopes"])
        for envelope in envelopes:
            target_lane = envelope.get("targetLane")
            if target_lane and not envelope.get("targetTrackId"):
                track_ids = ROLE_TO_TRACKS.get(str(target_lane), ())
                if track_ids:
                    envelope["targetTrackId"] = track_ids[0]
                elif str(target_lane) in TRACK_BLUEPRINTS:
                    envelope["targetTrackId"] = str(target_lane)
        return {
            "source": automation_payload.get("source", "spec"),
            "envelopes": envelopes,
        }
    text = lower_join(section.get("summary"), section.get("excerpt"), section.get("transcriptText"), " ".join(section.get("techniques", [])))
    if "automation" in text or "filter" in text or "macro" in text:
        return {
            "source": "heuristic",
            "envelopes": [
                {
                    "parameter": "filter",
                    "start": 0.15 if section["type"] == "build" else 0.55,
                    "end": 0.92 if section["type"] in {"build", "drop", "second_drop"} else 0.75,
                    "barOffset": 0,
                    "bars": max(1, int(section.get("bars", 4))),
                    "curve": "linear",
                }
            ],
        }
    return {}


def choose_progression_template(spec: dict[str, Any], section: dict[str, Any]) -> list[dict[str, Any]]:
    text = lower_join(
        spec.get("derivedPrompt"),
        spec.get("sourcePrompt"),
        " ".join(spec.get("keyHints", [])),
        section.get("summary"),
        " ".join(section.get("trackRoles", [])),
        " ".join(section.get("techniques", [])),
    )
    if "major" in text and "minor" not in text:
        return MAJOR_POP_PROGRESSION
    if any(keyword in text for keyword in ("dark", "trap", "wonky", "ratchet", "old school", "gritty")):
        return DARK_TRAP_PROGRESSION
    return BRIGHT_UPLIFT_PROGRESSION


def choose_lead_motif_key(section: dict[str, Any]) -> str:
    text = lower_join(section.get("summary"), " ".join(section.get("trackRoles", [])), " ".join(section.get("techniques", [])))
    if any(keyword in text for keyword in ("tease", "sneak", "preview", "teaser")):
        return "tease"
    if any(keyword in text for keyword in ("dark", "wonky", "old school", "ratchet")):
        return "dark"
    if section["type"] in {"drop", "second_drop"} or "filled in" in text:
        return "dense"
    return "sparse"


def infer_chord_events(section: dict[str, Any]) -> list[dict[str, Any]]:
    text = lower_join(section.get("summary"), " ".join(section.get("trackRoles", [])))
    if section["type"] in {"drop", "second_drop"}:
        if "filled in" in text:
            return [{"beat": 0.0, "duration": 0.65, "stab": True, "bright": 0.88}, {"beat": 0.75, "duration": 0.32, "stab": True, "bright": 0.90}, {"beat": 1.5, "duration": 0.40, "stab": True, "bright": 0.92}, {"beat": 2.0, "duration": 0.50, "stab": True, "bright": 0.94}, {"beat": 3.0, "duration": 0.60, "stab": True, "bright": 0.96}]
        if "simple" in text and "filled in" not in text:
            return [{"beat": 0.0, "duration": 1.55}, {"beat": 2.0, "duration": 1.45}]
        return [{"beat": 0.0, "duration": 0.80}, {"beat": 1.5, "duration": 0.45}, {"beat": 2.0, "duration": 0.55}, {"beat": 3.0, "duration": 0.68}]
    if section["type"] == "build":
        return [{"beat": 0.0, "duration": 1.70}, {"beat": 2.0, "duration": 1.70}]
    if section["type"] == "verse" and any(keyword in text for keyword in ("pluck", "guitar")):
        return [{"beat": 0.0, "duration": 1.80}, {"beat": 2.0, "duration": 1.80}]
    return [{"beat": 0.0, "duration": 3.70}]


def infer_bass_events(section: dict[str, Any]) -> list[dict[str, Any]]:
    text = lower_join(section.get("summary"), " ".join(section.get("trackRoles", [])))
    if section["type"] in {"drop", "second_drop"}:
        if "same notes" in text or "plays the same notes" in text:
            return [{"beat": 0.0, "duration": 1.45}, {"beat": 2.0, "duration": 1.35}]
        return [{"beat": 0.0, "duration": 0.82}, {"beat": 1.5, "duration": 0.45}, {"beat": 2.0, "duration": 0.55}, {"beat": 3.0, "duration": 0.68}]
    if section["type"] == "build":
        return [{"beat": 0.0, "duration": 1.35}, {"beat": 2.0, "duration": 1.35}, {"beat": 3.35, "duration": 0.32}]
    if "simple trap beat" in text or section["type"] == "verse":
        return [{"beat": 0.0, "duration": 1.45}, {"beat": 2.0, "duration": 1.35}]
    return [{"beat": 0.0, "duration": 3.85}]


def infer_drum_pattern(section: dict[str, Any]) -> dict[str, Any]:
    text = lower_join(section.get("summary"), " ".join(section.get("trackRoles", [])), " ".join(section.get("techniques", [])))
    if section["type"] == "build":
        return {
            "kicks": [0.0],
            "snares": [step * 0.5 for step in range(8)],
            "hats": [step * 0.5 for step in range(8)],
            "claps": [step * 0.5 for step in range(8)],
            "clapRoll": True,
            "hatSpacing": 0.5,
            "ride": False,
            "crashBars": [],
        }
    ride_enabled = "ride" in text or section["type"] == "second_drop"
    hat_spacing = 0.25 if any(keyword in text for keyword in ("fast hi-hat", "speed", "ride")) or section["type"] in {"drop", "second_drop"} else 0.5
    if "simple trap beat" in text:
        return {
            "kicks": [0.0, 1.5, 2.75],
            "snares": [1.0, 3.0],
            "claps": [1.0, 3.0],
            "hats": [round(step * 0.5, 2) for step in range(8)],
            "clapRoll": False,
            "hatSpacing": 0.5,
            "ride": False,
            "crashBars": [],
        }
    return {
        "kicks": [0.0, 1.45, 2.0, 3.05] if section["type"] in {"drop", "second_drop"} else [0.0, 1.5, 2.75],
        "snares": [1.0, 3.0] if section["type"] not in {"drop", "second_drop"} else [2.0],
        "claps": [1.0, 3.0] if section["type"] not in {"drop", "second_drop"} else [2.0],
        "hats": [round(step * hat_spacing, 2) for step in range(int(4 / hat_spacing))],
        "clapRoll": False,
        "hatSpacing": hat_spacing,
        "ride": ride_enabled,
        "crashBars": [0] if section["type"] in {"drop", "second_drop"} or "crash" in text else [],
    }


def infer_fx_profile(section: dict[str, Any]) -> dict[str, bool]:
    text = lower_join(section.get("summary"), " ".join(section.get("trackRoles", [])), " ".join(section.get("techniques", [])))
    profile = {
        "noiseBed": any(keyword in text for keyword in ("white noise", "noise", "breath")) or section["type"] in {"intro", "pre_intro"},
        "riser": any(keyword in text for keyword in ("riser", "uplifter", "rise")) or section["type"] == "build",
        "downlifter": any(keyword in text for keyword in ("downlifter", "down lifter", "reverse")) or section["type"] in {"build", "drop", "outro"},
        "crash": "crash" in text or section["type"] in {"drop", "second_drop"},
    }
    # laneTransforms.fx.profile is where the musical plan says which transition
    # effects this section actually calls for; only booleans for known keys land.
    stated = ((section.get("laneTransforms") or {}).get("fx") or {}).get("profile")
    if isinstance(stated, dict):
        for name in profile:
            if isinstance(stated.get(name), bool):
                profile[name] = stated[name]
    return profile


def infer_section_starter_defaults(
    section: dict[str, Any],
    spec: dict[str, Any],
    prior_sections: list[dict[str, Any]],
    prior_defaults: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    text = lower_join(
        section.get("summary"),
        section.get("excerpt"),
        section.get("transcriptText"),
        " ".join(section.get("trackRoles", [])),
        " ".join(section.get("techniques", [])),
    )
    section_lane_events = deep_copy_jsonish(section.get("laneEvents", {}) or {})
    section_lane_transforms = deep_copy_jsonish(section.get("laneTransforms", {}) or {})
    fallback_reference = prior_sections[-1] if prior_sections else None
    reference_section = find_section_reference(text, prior_sections, fallback_reference)
    reference_defaults = prior_defaults.get(reference_section["id"], {}) if reference_section else {}
    lead_reference_section = resolve_transform_reference((section_lane_transforms.get("lead") or {}).get("copyFrom"), prior_sections)
    if lead_reference_section is None:
        lead_reference_section = resolve_lead_reference(text, prior_sections)
    lead_reference_defaults = prior_defaults.get(lead_reference_section["id"], {}) if lead_reference_section else {}
    bass_reference_section = resolve_transform_reference((section_lane_transforms.get("bass") or {}).get("copyFrom"), prior_sections)
    if bass_reference_section is None:
        bass_reference_section = resolve_bass_reference(text, prior_sections)
    bass_reference_defaults = prior_defaults.get(bass_reference_section["id"], {}) if bass_reference_section else {}
    chord_reference_section = resolve_transform_reference((section_lane_transforms.get("chords") or {}).get("copyFrom"), prior_sections)
    if chord_reference_section is None:
        chord_reference_section = resolve_chord_reference(text, prior_sections)
    chord_reference_defaults = prior_defaults.get(chord_reference_section["id"], {}) if chord_reference_section else {}
    drum_reference_section = resolve_transform_reference((section_lane_transforms.get("drums") or {}).get("copyFrom"), prior_sections)
    if drum_reference_section is None:
        drum_reference_section = resolve_drum_reference(text, prior_sections)
    drum_reference_defaults = prior_defaults.get(drum_reference_section["id"], {}) if drum_reference_section else {}
    progression = choose_progression_template(spec, section)
    lead_motif_key = choose_lead_motif_key(section)
    stated_motif_key = (section_lane_transforms.get("lead") or {}).get("motifKey")
    if stated_motif_key in LEAD_MOTIF_LIBRARY:
        lead_motif_key = str(stated_motif_key)
    lead_soft = section["type"] in {"intro", "verse", "break", "outro"} and lead_motif_key != "dense"
    chord_lane_events = section_lane_events.get("chords") or {}
    explicit_progression = progression_from_symbols(chord_lane_events.get("progressionSymbols") or [])
    if explicit_progression is None:
        explicit_progression = extract_explicit_progression(text)
    if explicit_progression:
        progression = explicit_progression
    lead_shift = int((section_lane_transforms.get("lead") or {}).get("transposeSemitones") or 0)
    if lead_shift == 0:
        lead_shift = parse_transpose_instruction(text)
    # A second drop jumps an octave unless the plan said, in so many words, not to.
    plan_kept_octave = (section_lane_transforms.get("lead") or {}).get("transposeSource") == "model" and (section_lane_transforms.get("lead") or {}).get("transposeSemitones") == 0
    if section["type"] == "second_drop" and lead_shift == 0 and not plan_kept_octave:
        lead_shift = 12
    lead_motif = deep_copy_jsonish(LEAD_MOTIF_LIBRARY[lead_motif_key])
    reference_notes: dict[str, Any] = {}
    lead_transform = section_lane_transforms.get("lead") or {}
    if lead_transform.get("copyFrom") and lead_reference_defaults.get("leadMotif"):
        lead_motif = deep_copy_jsonish(lead_reference_defaults["leadMotif"])
        lead_motif_key = str(lead_reference_defaults.get("leadMotifKey", lead_motif_key))
        reference_notes["leadSourceSectionId"] = lead_reference_section["id"] if lead_reference_section else None
        if lead_transform.get("transform") == "fill_in":
            lead_motif = densify_motif(lead_motif)
            lead_motif_key = "dense"
            reference_notes["leadTransform"] = "fill_in"
    elif "same melody" in text and lead_reference_defaults.get("leadMotif"):
        lead_motif = deep_copy_jsonish(lead_reference_defaults["leadMotif"])
        lead_motif_key = str(lead_reference_defaults.get("leadMotifKey", lead_motif_key))
        reference_notes["leadSourceSectionId"] = lead_reference_section["id"] if lead_reference_section else None
        if "filled in" in text:
            lead_motif = densify_motif(lead_motif)
            lead_motif_key = "dense"
            reference_notes["leadTransform"] = "fill_in"
    elif "filled in" in text and lead_motif_key != "dense":
        lead_motif = densify_motif(lead_motif)
        lead_motif_key = "dense"
    lead_lane_events = section_lane_events.get("lead") or {}
    if lead_lane_events.get("events"):
        lead_motif = motif_from_lane_events(lead_lane_events["events"], lead_motif)
        reference_notes["leadEventSource"] = lead_lane_events.get("source", "spec")
    if lead_shift:
        lead_motif = transpose_motif(lead_motif, lead_shift)
        reference_notes["leadTransposeSemitones"] = lead_shift
    chord_transform = section_lane_transforms.get("chords") or {}
    if chord_transform.get("copyFrom") and chord_reference_defaults.get("progression"):
        progression = deep_copy_jsonish(chord_reference_defaults["progression"])
        reference_notes["chordProgressionSourceSectionId"] = chord_reference_section["id"] if chord_reference_section else None
    elif chord_reference_defaults.get("progression") and "same chord" in text:
        progression = deep_copy_jsonish(chord_reference_defaults["progression"])
        reference_notes["chordProgressionSourceSectionId"] = chord_reference_section["id"] if chord_reference_section else None
    if chord_lane_events.get("events"):
        chord_events = materialize_chord_events(chord_lane_events["events"])
        reference_notes["chordEventSource"] = chord_lane_events.get("source", "spec")
    else:
        chord_events = None
    bass_lane_events = section_lane_events.get("bass") or {}
    bass_transform = section_lane_transforms.get("bass") or {}
    if bass_lane_events.get("events"):
        bass_events = deep_copy_jsonish(bass_lane_events["events"])
        reference_notes["bassEventSource"] = bass_lane_events.get("source", "spec")
    else:
        bass_events = None
    if bass_transform.get("followChords"):
        bass_events = bass_events_from_follow_chords(bass_transform.get("omitBeats"))
        reference_notes["bassFollowChords"] = True
        if bass_transform.get("omitBeats"):
            reference_notes["bassOmitBeats"] = [round(float(beat), 2) for beat in bass_transform["omitBeats"]]
    elif (bass_transform.get("copyFrom") or "same notes" in text or "plays the same notes" in text):
        if bass_reference_defaults.get("progression"):
            progression = deep_copy_jsonish(bass_reference_defaults["progression"])
            reference_notes["progressionSourceSectionId"] = bass_reference_section["id"] if bass_reference_section else None
        if bass_events is None and bass_reference_defaults.get("bassEvents"):
            bass_events = deep_copy_jsonish(bass_reference_defaults["bassEvents"])
            reference_notes["bassSourceSectionId"] = bass_reference_section["id"] if bass_reference_section else None
        elif bass_events is None:
            bass_events = infer_bass_events(section)
        if chord_events is None and bass_reference_defaults.get("chordEvents"):
            chord_events = deep_copy_jsonish(bass_reference_defaults["chordEvents"])
            reference_notes["chordSourceSectionId"] = bass_reference_section["id"] if bass_reference_section else None
        elif chord_events is None:
            chord_events = infer_chord_events(section)
    else:
        if bass_events is None:
            bass_events = infer_bass_events(section)
        if chord_events is None:
            chord_events = infer_chord_events(section)
    if lead_shift and explicit_progression and any(keyword in text for keyword in ("chords up", "progression up", "transpose chords", "transpose progression")):
        progression = transpose_progression(progression, lead_shift)
        reference_notes["progressionTransposeSemitones"] = lead_shift
    if "happy" in text and "dark" not in text and reference_defaults.get("progression"):
        progression = lighten_progression(reference_defaults["progression"])
    drum_pattern = infer_drum_pattern(section)
    drum_transform = section_lane_transforms.get("drums") or {}
    if drum_transform.get("copyFrom") and drum_reference_defaults.get("drumPattern"):
        drum_pattern = deep_copy_jsonish(drum_reference_defaults["drumPattern"])
        reference_notes["drumSourceSectionId"] = drum_reference_section["id"] if drum_reference_section else None
    elif drum_reference_defaults.get("drumPattern") and "same drum" in text:
        drum_pattern = deep_copy_jsonish(drum_reference_defaults["drumPattern"])
        reference_notes["drumSourceSectionId"] = drum_reference_section["id"] if drum_reference_section else None
    drum_pattern = apply_lane_events_to_drum_pattern(drum_pattern, section_lane_events)
    if any(section_lane_events.get(lane) for lane in ("kick", "snare", "clap", "hat", "ride", "crash")):
        reference_notes["drumEventLanes"] = sorted(lane for lane in ("kick", "snare", "clap", "hat", "ride", "crash") if section_lane_events.get(lane))
    if drum_transform.get("overrides"):
        drum_pattern = merge_drum_pattern(drum_pattern, drum_transform["overrides"])
        reference_notes["drumOverrides"] = sorted(drum_transform["overrides"].keys())
    beat_overrides = extract_lane_beat_overrides(text)
    if beat_overrides and not any(section_lane_events.get(lane) for lane in ("kick", "snare", "clap", "hat", "ride", "crash")):
        drum_pattern = merge_drum_pattern(drum_pattern, beat_overrides)
        reference_notes["explicitBeatOverrides"] = sorted(beat_overrides.keys())
    automation_profile = infer_automation_profile(section, section_lane_events)
    if automation_profile.get("envelopes"):
        reference_notes["automationSource"] = automation_profile.get("source", "spec")
    energy = 1.25 if section["type"] in {"drop", "second_drop"} else (1.05 if section["type"] == "build" else 0.85)
    stated_energy = (section_lane_transforms.get("section") or {}).get("energy")
    if isinstance(stated_energy, (int, float)) and not isinstance(stated_energy, bool) and 0.5 <= float(stated_energy) <= 1.5:
        energy = round(float(stated_energy), 2)
        reference_notes["energySource"] = str((section_lane_transforms.get("section") or {}).get("energySource") or "spec")
    defaults = {
        "progression": progression,
        "chordEvents": chord_events,
        "bassEvents": bass_events,
        "leadMotifKey": lead_motif_key,
        "leadMotif": lead_motif,
        "leadSoft": lead_soft,
        "leadOctaveShift": lead_shift,
        "drumPattern": drum_pattern,
        "fxProfile": infer_fx_profile(section),
        "automationProfile": automation_profile,
        "energy": energy,
    }
    if reference_notes:
        defaults["references"] = reference_notes
    return defaults


def role_guidance(track_id: str) -> str:
    return ROLE_GUIDANCE.get(track_id, "Translate the transcript cues into a concrete part for this lane.")


def render_role_helper_name(section: dict[str, Any], index: int, track_id: str) -> str:
    return f"render_{renderer_function_name(section, index)}_{renderer_track_name(track_id)}"


def render_role_helper_functions(section_plan: list[dict[str, Any]], track_plan: list[dict[str, Any]]) -> str:
    track_by_id = {track["id"]: track for track in track_plan}
    blocks: list[str] = []
    for index, section in enumerate(section_plan, start=1):
        for track_id in section.get("trackIds", []):
            track = track_by_id[track_id]
            helper_name = render_role_helper_name(section, index, track_id)
            clips = overlapping_clips(track, section)
            lines = [
                f"def {helper_name}(ctx: RenderContext, section: dict) -> None:",
                f'    """{section["label"]} / {track["name"]} role helper."""',
                f"    track = TRACK_PLAN_BY_ID[{track_id!r}]",
                f"    # Instrument: {track['instrument']}",
                f"    # Guidance: {role_guidance(track_id)}",
            ]
            if section.get("plugins"):
                lines.append(f"    # Section plugin hints: {', '.join(section['plugins'])}")
            if section.get("techniques"):
                lines.append(f"    # Section techniques: {', '.join(section['techniques'])}")
            if track.get("effects"):
                lines.append(f"    # Track effects: {', '.join(track['effects'])}")
            if clips:
                lines.append("    # Relevant clips in this section:")
                for clip in clips:
                    lines.append(
                        f"    # - {clip['name']} (bars {clip['startBar'] + 1}-{clip['startBar'] + clip['bars']}, {clip['type']})"
                    )
            else:
                lines.append("    # No overlapping clips were materialized for this lane yet.")
            lines.extend(
                [
                    "    # TODO: Refine or replace the starter render body for this lane.",
                    "    ctx.notes.append(",
                    f"        f\"    -> {track['name']}: {{track['instrument']}} | effects {{', '.join(track.get('effects', [])) or 'none'}}\"",
                    "    )",
                    "    _render_lane_starter(ctx, section, track)",
                    f"    _render_track_baseline(ctx, {track_id!r}, section['startBar'], section['bars'], note=track['name'])",
                    "",
                ]
            )
            blocks.append("\n".join(lines))
    return "\n\n".join(blocks).rstrip() + "\n"


def render_section_functions(section_plan: list[dict[str, Any]], track_plan: list[dict[str, Any]]) -> str:
    track_names = {track["id"]: track["name"] for track in track_plan}
    blocks: list[str] = []
    for index, section in enumerate(section_plan, start=1):
        fn = renderer_function_name(section, index)
        lines = [
            f"def render_{fn}(ctx: RenderContext) -> None:",
            f'    """{section["label"]}: bars {section["startBar"] + 1}-{section["startBar"] + section["bars"]}."""',
            f"    section = SECTION_PLAN_BY_ID[{section['id']!r}]",
            "    # Transcript summary:",
            f"    # {section['summary'] or section['label']}",
        ]
        if section.get("recipeDetail"):
            lines.extend([
                "    # Scaffold detail:",
                f"    # {section['recipeDetail']}",
            ])
        if section.get("trackRoles"):
            lines.append(f"    # Track roles: {', '.join(section['trackRoles'])}")
        if section.get("plugins"):
            lines.append(f"    # Plugin hints: {', '.join(section['plugins'])}")
        if section.get("techniques"):
            lines.append(f"    # Techniques: {', '.join(section['techniques'])}")
        if section.get("laneEvents"):
            lines.append(f"    # Lane events: {json.dumps(section['laneEvents'], sort_keys=True)}")
        if section.get("laneTransforms"):
            lines.append(f"    # Lane transforms: {json.dumps(section['laneTransforms'], sort_keys=True)}")
        if section.get("trackIds"):
            lines.append("    # Tracks to touch in this section:")
            for track_id in section["trackIds"]:
                lines.append(f"    # - {track_id}: {track_names.get(track_id, track_id)}")
        lines.extend([
            "    _log_section(ctx, section)",
            "    # Refine the role helpers below with the final synthesis and sample arrangement.",
        ])
        for track_id in section.get("trackIds", []):
            lines.append(f"    {render_role_helper_name(section, index, track_id)}(ctx, section)")
        if not section.get("trackIds"):
            lines.append("    # TODO: No track ids were inferred for this section yet.")
        lines.append("")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks).rstrip() + "\n"


def render_runtime_support() -> str:
    return '''
import json
import math
import wave

import numpy as np


TOTAL_SECONDS = TOTAL_BARS * 4 * BEAT + TAIL_SECONDS
N_SAMPLES = int(TOTAL_SECONDS * SR)
STEM_PREFIX = PROJECT_ID.replace("-", "_")
FALLBACK_PROGRESSION = [
    {"name": "Em7", "notes": [52, 55, 59, 62], "root": 40},
    {"name": "Cmaj7", "notes": [48, 52, 55, 59], "root": 36},
    {"name": "Gadd9", "notes": [43, 47, 50, 55], "root": 31},
    {"name": "Dadd9", "notes": [50, 54, 57, 62], "root": 38},
]
FALLBACK_LEAD_MOTIF = [
    [(0.00, 0.45, 76), (0.52, 0.38, 79), (1.02, 0.70, 83), (2.02, 0.42, 79), (2.56, 0.66, 76)],
    [(0.00, 0.42, 79), (0.48, 0.38, 81), (1.00, 0.68, 83), (2.04, 0.42, 79), (2.56, 0.72, 74)],
    [(0.00, 0.42, 83), (0.52, 0.38, 84), (1.02, 0.68, 83), (2.00, 0.42, 79), (2.50, 0.72, 76)],
    [(0.00, 0.40, 79), (0.46, 0.36, 76), (0.92, 0.38, 74), (1.45, 0.38, 76), (2.10, 0.78, 79)],
]


def beat_to_seconds(beat: float) -> float:
    return beat * BEAT


def bar_beat(bar: int, beat: float = 0.0) -> float:
    return bar * 4.0 + beat


def note_to_freq(midi_note: int) -> float:
    return 440.0 * (2.0 ** ((midi_note - 69) / 12.0))


def stereo_buffer() -> np.ndarray:
    return np.zeros((N_SAMPLES, 2), dtype=np.float32)


def equal_power_pan(pan: float) -> tuple[float, float]:
    pan = float(np.clip(pan, -1.0, 1.0))
    angle = (pan + 1.0) * math.pi / 4.0
    return math.cos(angle), math.sin(angle)


def add_mono(target: np.ndarray, start_seconds: float, audio: np.ndarray, gain: float = 1.0, pan: float = 0.0) -> None:
    start = int(round(start_seconds * SR))
    if start >= len(target):
        return
    end = min(start + len(audio), len(target))
    if end <= start:
        return
    audio = audio[: end - start].astype(np.float32, copy=False) * gain
    left, right = equal_power_pan(pan)
    target[start:end, 0] += audio * left
    target[start:end, 1] += audio * right


def adsr(n: int, attack: float = 0.01, decay: float = 0.08, sustain: float = 0.7, release: float = 0.12) -> np.ndarray:
    attack_n = max(1, int(attack * SR))
    decay_n = max(1, int(decay * SR))
    release_n = max(1, int(release * SR))
    fixed = attack_n + decay_n + release_n
    if fixed > n:
        scale = n / fixed
        attack_n = max(1, int(attack_n * scale))
        decay_n = max(1, int(decay_n * scale))
        release_n = max(1, n - attack_n - decay_n)
    sustain_n = max(0, n - attack_n - decay_n - release_n)
    env = np.concatenate([
        np.linspace(0.0, 1.0, attack_n, endpoint=False),
        np.linspace(1.0, sustain, decay_n, endpoint=False),
        np.full(sustain_n, sustain),
        np.linspace(sustain, 0.0, release_n, endpoint=True),
    ])
    if len(env) < n:
        env = np.pad(env, (0, n - len(env)))
    return env[:n].astype(np.float32)


def highpass_noise(n: int) -> np.ndarray:
    x = np.random.default_rng(1408).standard_normal(n).astype(np.float32)
    y = np.empty_like(x)
    y[0] = x[0]
    y[1:] = x[1:] - 0.94 * x[:-1]
    return y


def one_pole_lowpass(x: np.ndarray, cutoff_hz: float) -> np.ndarray:
    if cutoff_hz <= 0:
        return x.astype(np.float32, copy=False)
    rc = 1.0 / (2.0 * math.pi * cutoff_hz)
    dt = 1.0 / SR
    alpha = dt / (rc + dt)
    y = np.empty_like(x, dtype=np.float32)
    prev = 0.0
    for i, sample in enumerate(x):
        prev = prev + alpha * (float(sample) - prev)
        y[i] = prev
    return y


def saw(freq: float, dur: float, phase: float = 0.0) -> np.ndarray:
    n = max(1, int(dur * SR))
    t = np.arange(n, dtype=np.float32) / SR
    p = (freq * t + phase) % 1.0
    return (2.0 * p - 1.0).astype(np.float32)


def synth_supersaw(freq: float, dur: float, bright: float = 0.8, stab: bool = False) -> np.ndarray:
    n = max(1, int(dur * SR))
    t = np.arange(n, dtype=np.float32) / SR
    out = np.zeros(n, dtype=np.float32)
    for idx, cents in enumerate([-11.0, -5.0, 0.0, 4.0, 9.0]):
        out += saw(freq * (2.0 ** (cents / 1200.0)), dur, phase=0.11 * idx)
    out /= 5.0
    out += 0.10 * np.sin(2.0 * np.pi * freq * 0.5 * t).astype(np.float32)
    out = one_pole_lowpass(out, 1800.0 + 4200.0 * bright)
    env = adsr(n, attack=0.012 if stab else 0.06, decay=0.10, sustain=0.54 if stab else 0.76, release=0.10 if stab else 0.34)
    return (out * env).astype(np.float32)


def synth_bass(freq: float, dur: float, grit: float = 0.4) -> np.ndarray:
    n = max(1, int(dur * SR))
    t = np.arange(n, dtype=np.float32) / SR
    phase = np.cumsum(np.full(n, freq, dtype=np.float32)) / SR
    sine = np.sin(2.0 * np.pi * phase).astype(np.float32)
    sq = np.where((phase % 1.0) < 0.5, 1.0, -1.0).astype(np.float32) * grit * 0.16
    env = adsr(n, attack=0.003, decay=0.06, sustain=0.82, release=0.07)
    return (0.88 * sine + sq) * env


def synth_lead(freq: float, dur: float, soft: bool = False) -> np.ndarray:
    n = max(1, int(dur * SR))
    t = np.arange(n, dtype=np.float32) / SR
    vibrato = 1.0 + 0.003 * np.sin(2.0 * math.pi * 5.0 * t)
    phase = np.cumsum((freq * vibrato).astype(np.float32)) / SR
    sq = np.where((phase % 1.0) < 0.5, 1.0, -1.0).astype(np.float32)
    tri = (2.0 * np.abs(2.0 * (phase % 1.0) - 1.0) - 1.0).astype(np.float32)
    out = 0.56 * sq + 0.28 * tri
    out = one_pole_lowpass(out, 2600.0 if soft else 4200.0)
    env = adsr(n, attack=0.010, decay=0.07, sustain=0.62 if soft else 0.76, release=0.08)
    return out * env


def synth_pluck(freq: float, dur: float) -> np.ndarray:
    n = max(1, int(dur * SR))
    t = np.arange(n, dtype=np.float32) / SR
    out = 0.62 * np.sin(2.0 * np.pi * freq * t) + 0.24 * saw(freq * 2.0, dur)
    env = np.exp(-t * 7.5).astype(np.float32)
    return one_pole_lowpass((out * env).astype(np.float32), 2600.0)


def kick() -> np.ndarray:
    dur = 0.52
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    freq = 48.0 + 110.0 * np.exp(-t * 18.0)
    phase = np.cumsum(freq) / SR
    body = np.sin(2.0 * np.pi * phase).astype(np.float32) * np.exp(-t * 7.0)
    click = highpass_noise(n) * np.exp(-t * 80.0).astype(np.float32) * 0.06
    return (1.14 * body + click).astype(np.float32)


def snare(clap: bool = False) -> np.ndarray:
    dur = 0.42 if not clap else 0.48
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    noise = highpass_noise(n) * np.exp(-t * (14.0 if not clap else 10.0)).astype(np.float32)
    tone = np.sin(2.0 * np.pi * 190.0 * t).astype(np.float32) * np.exp(-t * 18.0) * 0.28
    return (noise * (0.46 if not clap else 0.64) + tone).astype(np.float32)


def hat(open_hat: bool = False) -> np.ndarray:
    dur = 0.18 if open_hat else 0.07
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    return (highpass_noise(n) * np.exp(-t * (11.0 if open_hat else 52.0)).astype(np.float32) * (0.18 if open_hat else 0.12)).astype(np.float32)


def crash() -> np.ndarray:
    dur = 1.8
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    return (highpass_noise(n) * np.exp(-t * 1.25).astype(np.float32) * 0.24).astype(np.float32)


def riser(dur: float, start_freq: float = 220.0, end_freq: float = 1600.0) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    freqs = np.linspace(start_freq, end_freq, n, dtype=np.float32)
    phase = np.cumsum(freqs) / SR
    tone = np.sin(2.0 * np.pi * phase).astype(np.float32)
    noise = one_pole_lowpass(highpass_noise(n), 5400.0)
    env = np.linspace(0.0, 1.0, n, dtype=np.float32) ** 1.4
    return (0.18 * tone + 0.14 * noise) * env


def downlifter(dur: float = 1.2) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    noise = highpass_noise(n) * np.exp(-t * 1.6).astype(np.float32)
    tone = np.sin(2.0 * np.pi * (380.0 - 240.0 * t / max(dur, 0.001)) * t).astype(np.float32)
    return (0.18 * noise + 0.08 * tone).astype(np.float32)


def _track_buffer(ctx: RenderContext, track_id: str) -> np.ndarray:
    key = track_id.replace("-", "_")
    if key not in ctx.stems:
        ctx.stems[key] = stereo_buffer()
    return ctx.stems[key]


def _section_defaults(section: dict) -> dict:
    return section.get("starterDefaults", {}) or {}


def _progression_for_bar(section: dict, bar: int) -> dict:
    progression = _section_defaults(section).get("progression") or FALLBACK_PROGRESSION
    return progression[bar % len(progression)]


def _lead_motif_for_section(section: dict) -> list[list[dict]]:
    return _section_defaults(section).get("leadMotif") or FALLBACK_LEAD_MOTIF


def scoped_events_for_bar(events: list[dict], local_bar: int) -> list[dict]:
    scoped = [event for event in events if event.get("barOffset") == local_bar]
    if scoped:
        return scoped
    return [event for event in events if "barOffset" not in event]


def _drum_values_for_bar(drum_pattern: dict, key: str, local_bar: int, fallback: list[float]) -> list[float]:
    scoped = (drum_pattern.get("scopedBars") or {}).get(str(local_bar), {})
    values = scoped.get(key)
    if values is not None:
        return values
    return drum_pattern.get(key) or fallback


def _drum_flag_for_bar(drum_pattern: dict, key: str, local_bar: int, fallback: bool = False) -> bool:
    scoped = (drum_pattern.get("scopedBars") or {}).get(str(local_bar), {})
    if key in scoped:
        return bool(scoped[key])
    return bool(drum_pattern.get(key, fallback))


def _drum_event_data_for_bar(drum_pattern: dict, key: str, local_bar: int, fallback: list[float]) -> list[dict]:
    scoped = (drum_pattern.get("scopedEventData") or {}).get(str(local_bar), {})
    if key in scoped:
        return scoped[key]
    defaults = (drum_pattern.get("eventData") or {}).get(key)
    if defaults:
        return defaults
    return [{"beat": float(beat)} for beat in fallback]


def _schedule_note(buffer: np.ndarray, start_beat: float, duration_beats: float, midi_note: int, synth, *, gain: float, pan: float = 0.0, **kwargs) -> None:
    audio = synth(note_to_freq(midi_note), duration_beats * BEAT, **kwargs)
    add_mono(buffer, beat_to_seconds(start_beat), audio, gain=gain, pan=pan)


def _curve_progress(progress: np.ndarray, curve: str) -> np.ndarray:
    curve = str(curve or "linear").lower()
    if curve == "exp":
        return np.power(progress, 2.0).astype(np.float32)
    if curve == "ease_in":
        return np.power(progress, 1.6).astype(np.float32)
    if curve == "ease_out":
        return (1.0 - np.power(1.0 - progress, 1.6)).astype(np.float32)
    if curve == "ease_in_out":
        eased = np.where(progress < 0.5, 2.0 * progress * progress, 1.0 - np.power(-2.0 * progress + 2.0, 2.0) / 2.0)
        return eased.astype(np.float32)
    if curve == "step":
        return np.where(progress < 0.5, 0.0, 1.0).astype(np.float32)
    return progress.astype(np.float32)


def _starter_chords(ctx: RenderContext, section: dict, track: dict) -> None:
    buffer = _track_buffer(ctx, track["id"])
    defaults = _section_defaults(section)
    for local_bar, bar in enumerate(range(section["startBar"], section["startBar"] + section["bars"])):
        chord = _progression_for_bar(section, bar)
        chord_events = scoped_events_for_bar(defaults.get("chordEvents") or [{"beat": 0.0, "duration": 3.7}], local_bar)
        for event in chord_events:
            onset = float(event["beat"])
            dur = float(event["duration"])
            stab = bool(event.get("stab", section["type"] in {"drop", "second_drop"}))
            bright = float(event.get("bright", 0.55 if section["type"] == "build" else (0.84 if stab else 0.30)))
            event_notes = event.get("notes") or chord["notes"]
            for idx, note in enumerate(event_notes):
                accent_gain = 1.18 if event.get("accent") else 1.0
                event_gain = float(event.get("gain", 1.0))
                _schedule_note(buffer, bar_beat(bar, onset), dur, int(note), synth_supersaw, gain=track.get("gain", 0.8) * (0.10 if stab else 0.06) * float(defaults.get("energy", 1.0)) * accent_gain * event_gain, pan=float(event.get("pan", -0.45 + idx * 0.30)), bright=bright, stab=stab)


def _starter_bass(ctx: RenderContext, section: dict, track: dict) -> None:
    buffer = _track_buffer(ctx, track["id"])
    defaults = _section_defaults(section)
    for local_bar, bar in enumerate(range(section["startBar"], section["startBar"] + section["bars"])):
        root = int(_progression_for_bar(section, bar)["root"])
        bass_events = scoped_events_for_bar(defaults.get("bassEvents") or [{"beat": 0.0, "duration": 3.85}], local_bar)
        for event in bass_events:
            onset = float(event["beat"])
            dur = float(event["duration"])
            accent_gain = 1.15 if event.get("accent") else (0.7 if event.get("ghost") else 1.0)
            gain = track.get("gain", 0.8) * (0.20 if section["type"] in {"drop", "second_drop"} else 0.10) * float(defaults.get("energy", 1.0)) * float(event.get("gain", 1.0)) * accent_gain
            target_note = int(event.get("note", root + int(event.get("octaveShift", 0))))
            _schedule_note(buffer, bar_beat(bar, onset), dur, target_note, synth_bass, gain=gain, pan=float(event.get("pan", track.get("pan", 0.0))), grit=float(event.get("grit", 0.46)))


def _starter_sub(ctx: RenderContext, section: dict, track: dict) -> None:
    buffer = _track_buffer(ctx, track["id"])
    defaults = _section_defaults(section)
    for bar in range(section["startBar"], section["startBar"] + section["bars"]):
        root = int(_progression_for_bar(section, bar)["root"]) - 12
        _schedule_note(buffer, bar_beat(bar), 3.85, root, synth_bass, gain=track.get("gain", 0.8) * 0.12 * float(defaults.get("energy", 1.0)), pan=0.0, grit=0.12)


def _starter_lead(ctx: RenderContext, section: dict, track: dict) -> None:
    buffer = _track_buffer(ctx, track["id"])
    defaults = _section_defaults(section)
    soft = bool(defaults.get("leadSoft", section["type"] in {"intro", "verse", "break", "outro"}))
    transpose = int(defaults.get("leadOctaveShift", 0))
    motif = _lead_motif_for_section(section)
    for local_bar, bar in enumerate(range(section["startBar"], section["startBar"] + section["bars"])):
        bar_motif = motif[local_bar % len(motif)]
        for event in bar_motif:
            onset = float(event["beat"])
            dur = float(event["duration"])
            note = int(event["note"])
            if soft and onset > 2.6 and local_bar % 2 == 0:
                continue
            accent_gain = 1.18 if event.get("accent") else (0.72 if event.get("ghost") else 1.0)
            _schedule_note(buffer, bar_beat(bar, onset), dur, note + transpose, synth_lead, gain=track.get("gain", 0.8) * (0.10 if not soft else 0.06) * float(defaults.get("energy", 1.0)) * float(event.get("gain", 1.0)) * accent_gain, pan=float(event.get("pan", (-0.08 if (local_bar + int(onset * 10)) % 2 else 0.08))), soft=soft)


DEFAULT_KICK_BEATS = [0.0, 1.5, 2.75]
DEFAULT_SNARE_BEATS = [1.0, 3.0]


def _kick_events_for_bar(drum_pattern: dict, local_bar: int) -> list[dict]:
    return _drum_event_data_for_bar(drum_pattern, "kicks", local_bar, DEFAULT_KICK_BEATS)


def _snare_events_for_bar(drum_pattern: dict, local_bar: int) -> list[dict]:
    return _drum_event_data_for_bar(drum_pattern, "snares", local_bar, DEFAULT_SNARE_BEATS)


def _clap_events_for_bar(drum_pattern: dict, local_bar: int) -> list[dict]:
    if _drum_flag_for_bar(drum_pattern, "clapRoll", local_bar):
        return [{"beat": step * 0.5} for step in range(8)]
    return _drum_event_data_for_bar(drum_pattern, "claps", local_bar, _drum_values_for_bar(drum_pattern, "snares", local_bar, DEFAULT_SNARE_BEATS))


def _snare_hit_gain(track: dict, defaults: dict, event: dict) -> float:
    ghost_gain = 0.55 if event.get("ghost") else 1.0
    accent_gain = 1.18 if event.get("accent") else 1.0
    return track.get("gain", 0.8) * 0.34 * float(defaults.get("energy", 1.0)) * float(event.get("gain", 1.0)) * ghost_gain * accent_gain


def _clap_hit_gain(track: dict, defaults: dict, drum_pattern: dict, local_bar: int, event: dict) -> float:
    accent_gain = 1.16 if event.get("accent") else (0.72 if event.get("ghost") else 1.0)
    roll_gain = 0.18 if _drum_flag_for_bar(drum_pattern, "clapRoll", local_bar) else 0.24
    return track.get("gain", 0.8) * roll_gain * float(defaults.get("energy", 1.0)) * float(event.get("gain", 1.0)) * accent_gain


def _kick_onsets_for_section(section: dict) -> list[float]:
    """Absolute onset times (seconds) of every kick in the section's drum pattern.

    The sidechain keys from this list, not from the rendered audio: it is the
    same lookup the drums lane plays from, so the duck lands on the kick even
    when the drums lane is silent in this section (the classic ghost-kick pump)."""
    drum_pattern = _section_defaults(section).get("drumPattern") or {}
    onsets: list[float] = []
    for local_bar, bar in enumerate(range(section["startBar"], section["startBar"] + section["bars"])):
        for event in _kick_events_for_bar(drum_pattern, local_bar):
            onsets.append(beat_to_seconds(bar_beat(bar, float(event["beat"]))))
    return onsets


def _snare_hits_for_section(section: dict, track: dict) -> list[tuple[float, float]]:
    """(onset seconds, gain) for each snare the drums lane plays here, same math as the lane."""
    defaults = _section_defaults(section)
    drum_pattern = defaults.get("drumPattern") or {}
    hits: list[tuple[float, float]] = []
    for local_bar, bar in enumerate(range(section["startBar"], section["startBar"] + section["bars"])):
        for event in _snare_events_for_bar(drum_pattern, local_bar):
            hits.append((beat_to_seconds(bar_beat(bar, float(event["beat"]))), _snare_hit_gain(track, defaults, event)))
    return hits


def _clap_hits_for_section(section: dict, track: dict) -> list[tuple[float, float]]:
    """(onset seconds, gain) for each clap the clap lane plays here, same math as the lane."""
    defaults = _section_defaults(section)
    drum_pattern = defaults.get("drumPattern") or {}
    hits: list[tuple[float, float]] = []
    for local_bar, bar in enumerate(range(section["startBar"], section["startBar"] + section["bars"])):
        for event in _clap_events_for_bar(drum_pattern, local_bar):
            hits.append((beat_to_seconds(bar_beat(bar, float(event["beat"]))), _clap_hit_gain(track, defaults, drum_pattern, local_bar, event)))
    return hits


def _starter_drums(ctx: RenderContext, section: dict, track: dict) -> None:
    buffer = _track_buffer(ctx, track["id"])
    defaults = _section_defaults(section)
    drum_pattern = defaults.get("drumPattern") or {}
    k = kick()
    s = snare(False)
    h = hat(False)
    for local_bar, bar in enumerate(range(section["startBar"], section["startBar"] + section["bars"])):
        kicks = _kick_events_for_bar(drum_pattern, local_bar)
        snares = _snare_events_for_bar(drum_pattern, local_bar)
        hats = _drum_event_data_for_bar(drum_pattern, "hats", local_bar, [step * 0.5 for step in range(8)])
        for event in kicks:
            beat = float(event["beat"])
            accent_gain = 1.18 if event.get("accent") else (0.7 if event.get("ghost") else 1.0)
            add_mono(buffer, beat_to_seconds(bar_beat(bar, beat)), k, gain=track.get("gain", 0.8) * 0.95 * float(defaults.get("energy", 1.0)) * float(event.get("gain", 1.0)) * accent_gain, pan=float(event.get("pan", track.get("pan", 0.0))))
        for event in snares:
            beat = float(event["beat"])
            add_mono(buffer, beat_to_seconds(bar_beat(bar, beat)), s, gain=_snare_hit_gain(track, defaults, event))
        for event in hats:
            beat_value = float(event["beat"])
            open_hat = bool(event.get("open"))
            hat_audio = hat(open_hat)
            accent_gain = 1.15 if event.get("accent") else (0.7 if event.get("ghost") else 1.0)
            base_gain = (0.17 if open_hat else 0.14) + (0.05 if int(beat_value * 2) % 2 else 0.0)
            add_mono(buffer, beat_to_seconds(bar_beat(bar, beat_value)), hat_audio, gain=base_gain * float(event.get("gain", 1.0)) * accent_gain, pan=float(event.get("pan", 0.22)))


def _starter_clap_stack(ctx: RenderContext, section: dict, track: dict) -> None:
    buffer = _track_buffer(ctx, track["id"])
    defaults = _section_defaults(section)
    drum_pattern = defaults.get("drumPattern") or {}
    c = snare(True)
    for local_bar, bar in enumerate(range(section["startBar"], section["startBar"] + section["bars"])):
        for event in _clap_events_for_bar(drum_pattern, local_bar):
            beat = float(event["beat"])
            add_mono(buffer, beat_to_seconds(bar_beat(bar, beat)), c, gain=_clap_hit_gain(track, defaults, drum_pattern, local_bar, event), pan=float(event.get("pan", 0.18)))


def _starter_hat_ride(ctx: RenderContext, section: dict, track: dict) -> None:
    buffer = _track_buffer(ctx, track["id"])
    defaults = _section_defaults(section)
    drum_pattern = defaults.get("drumPattern") or {}
    closed = hat(False)
    open_h = hat(True)
    for local_bar, bar in enumerate(range(section["startBar"], section["startBar"] + section["bars"])):
        hat_events = _drum_event_data_for_bar(drum_pattern, "hats", local_bar, [])
        if hat_events:
            for index, event in enumerate(hat_events):
                beat = float(event["beat"])
                hat_audio = open_h if event.get("open") else closed
                accent_gain = 1.16 if event.get("accent") else (0.72 if event.get("ghost") else 1.0)
                base_gain = track.get("gain", 0.8) * (0.19 if event.get("open") else 0.16) * float(event.get("gain", 1.0)) * accent_gain
                add_mono(buffer, beat_to_seconds(bar_beat(bar, beat)), hat_audio, gain=base_gain, pan=float(event.get("pan", (-0.28 if index % 2 else 0.28))))
        else:
            scoped = (drum_pattern.get("scopedBars") or {}).get(str(local_bar), {})
            spacing = float(scoped.get("hatSpacing", drum_pattern.get("hatSpacing", 0.5)))
            steps = int(4 / spacing)
            for step in range(steps):
                add_mono(buffer, beat_to_seconds(bar_beat(bar, step * spacing)), closed, gain=track.get("gain", 0.8) * 0.16, pan=-0.28 if step % 2 else 0.28)
        if not hat_events:
            add_mono(buffer, beat_to_seconds(bar_beat(bar, 3.5)), open_h, gain=track.get("gain", 0.8) * 0.16, pan=-0.20)
        ride_events = _drum_event_data_for_bar(drum_pattern, "rideBeats", local_bar, ([0.0] if _drum_flag_for_bar(drum_pattern, "ride", local_bar) and bar % 4 == 3 else []))
        for event in ride_events:
            beat = float(event["beat"])
            accent_gain = 1.14 if event.get("accent") else 1.0
            add_mono(buffer, beat_to_seconds(bar_beat(bar, beat)), open_h, gain=track.get("gain", 0.8) * 0.18 * float(event.get("gain", 1.0)) * accent_gain, pan=float(event.get("pan", 0.18)))
        crash_events = _drum_event_data_for_bar(drum_pattern, "crashBeats", local_bar, [])
        if crash_events:
            for event in crash_events:
                beat = float(event["beat"])
                accent_gain = 1.14 if event.get("accent") else 1.0
                add_mono(buffer, beat_to_seconds(bar_beat(bar, beat)), crash(), gain=track.get("gain", 0.8) * 0.18 * float(event.get("gain", 1.0)) * accent_gain, pan=float(event.get("pan", 0.22)))
        elif drum_pattern.get("crashBars") and local_bar in set(int(item) for item in drum_pattern["crashBars"]):
            add_mono(buffer, beat_to_seconds(bar_beat(bar)), crash(), gain=track.get("gain", 0.8) * 0.18, pan=0.22)


def _starter_fx(ctx: RenderContext, section: dict, track: dict) -> None:
    buffer = _track_buffer(ctx, track["id"])
    defaults = _section_defaults(section)
    fx_profile = defaults.get("fxProfile") or {}
    start_seconds = beat_to_seconds(bar_beat(section["startBar"]))
    if fx_profile.get("noiseBed"):
        add_mono(buffer, start_seconds, highpass_noise(int(section["bars"] * 4 * BEAT * SR)) * 0.05, gain=1.0, pan=0.12)
    if fx_profile.get("riser"):
        add_mono(buffer, start_seconds, riser(section["bars"] * 4 * BEAT), gain=track.get("gain", 0.8) * 0.34, pan=-0.12)
    if fx_profile.get("crash"):
        add_mono(buffer, start_seconds, crash(), gain=track.get("gain", 0.8) * 0.20, pan=0.18)
    if fx_profile.get("downlifter"):
        add_mono(buffer, beat_to_seconds(bar_beat(section["startBar"] + section["bars"] - 1, 3.2)), downlifter(), gain=track.get("gain", 0.8) * 0.18, pan=-0.18)


def _starter_guitar(ctx: RenderContext, section: dict, track: dict) -> None:
    buffer = _track_buffer(ctx, track["id"])
    for bar in range(section["startBar"], section["startBar"] + section["bars"]):
        root = int(_progression_for_bar(section, bar)["root"]) + 12
        for onset in [0.0, 0.75, 1.5, 2.0, 3.0]:
            _schedule_note(buffer, bar_beat(bar, onset), 0.30, root, synth_pluck, gain=track.get("gain", 0.8) * 0.08, pan=-0.10)


def _automation_target_buffer(ctx: RenderContext, envelope: dict, fallback_track_id: str) -> np.ndarray:
    target_track_id = envelope.get("targetTrackId")
    if target_track_id and target_track_id in TRACK_PLAN_BY_ID:
        return _track_buffer(ctx, str(target_track_id))
    return _track_buffer(ctx, fallback_track_id)


def _starter_filter_auto(ctx: RenderContext, section: dict, track: dict) -> None:
    defaults = _section_defaults(section)
    automation = defaults.get("automationProfile") or {}
    envelopes = automation.get("envelopes") or []
    if not envelopes:
        buffer = _track_buffer(ctx, track["id"])
        add_mono(buffer, beat_to_seconds(bar_beat(section["startBar"])), riser(section["bars"] * 4 * BEAT, 180.0, 900.0), gain=track.get("gain", 0.8) * 0.12, pan=0.0)
        return
    for envelope in envelopes:
        buffer = _automation_target_buffer(ctx, envelope, track["id"])
        parameter = str(envelope.get("parameter", "filter")).lower()
        curve = str(envelope.get("curve", "linear"))
        bar_offset = int(envelope.get("barOffset", 0))
        bar_count = max(1, int(envelope.get("bars", section["bars"])))
        start = float(envelope.get("start", 0.15))
        end = float(envelope.get("end", 0.9))
        start_seconds = beat_to_seconds(bar_beat(section["startBar"] + bar_offset))
        duration_seconds = bar_count * 4 * BEAT
        gain = track.get("gain", 0.8) * (0.08 + 0.14 * abs(end - start))
        if parameter in {"filter", "cutoff", "macro"}:
            curve_probe = _curve_progress(np.linspace(0.0, 1.0, 64, dtype=np.float32), curve)
            start_freq = 120.0 + 2600.0 * start
            end_freq = 220.0 + 6200.0 * (start + (end - start) * float(curve_probe[-1]))
            add_mono(
                buffer,
                start_seconds,
                riser(duration_seconds, start_freq, end_freq),
                gain=gain,
                pan=0.0,
            )
            continue
        if parameter == "volume":
            n = max(1, int(duration_seconds * SR))
            body = one_pole_lowpass(highpass_noise(n), 1800.0 + 2000.0 * end)
            progress = _curve_progress(np.linspace(0.0, 1.0, n, dtype=np.float32), curve)
            ramp = (max(0.05, start) + (max(0.05, end) - max(0.05, start)) * progress) ** 1.2
            add_mono(buffer, start_seconds, body * ramp, gain=gain * 0.9, pan=0.0)
            continue
        if parameter == "reverb":
            n = max(1, int(duration_seconds * SR))
            tail = one_pole_lowpass(highpass_noise(n), 3200.0)
            shimmer = 0.12 * np.sin(2.0 * np.pi * np.linspace(330.0, 880.0, n, dtype=np.float32) * (np.arange(n, dtype=np.float32) / SR))
            progress = _curve_progress(np.linspace(0.0, 1.0, n, dtype=np.float32), curve)
            env = (start + (end - start) * progress) ** 0.8
            add_mono(buffer, start_seconds, (tail * 0.22 + shimmer) * env, gain=gain, pan=-0.24)
            add_mono(buffer, start_seconds, (tail * 0.22 + shimmer) * env, gain=gain, pan=0.24)
            continue
        if parameter == "delay":
            steps = max(4, bar_count * 4)
            interval = max(0.16, 0.82 - 0.52 * end)
            for step in range(steps):
                progress = float(_curve_progress(np.array([step / max(1, steps - 1)], dtype=np.float32), curve)[0])
                onset = start_seconds + step * interval * BEAT * (0.8 + 0.4 * progress)
                pan = -0.65 if step % 2 else 0.65
                pitch = 74 + (step % 3) * 3
                add_mono(buffer, onset, synth_pluck(note_to_freq(pitch), 0.20 * BEAT), gain=gain * (0.9 - min(0.7, progress)), pan=pan)
            continue
        if parameter == "pan":
            steps = max(6, bar_count * 4)
            for step in range(steps):
                progress = float(_curve_progress(np.array([step / max(1, steps - 1)], dtype=np.float32), curve)[0])
                pan = -0.9 + 1.8 * progress * (1.0 if end >= start else -1.0)
                onset = start_seconds + progress * max(0.0, duration_seconds - 0.16)
                add_mono(buffer, onset, hat(True), gain=gain * 0.75, pan=pan)
            continue
        if parameter == "width":
            steps = max(4, bar_count * 2)
            spread = 0.15 + 0.8 * max(start, end)
            for step in range(steps):
                progress = float(_curve_progress(np.array([step / max(1, steps - 1)], dtype=np.float32), curve)[0])
                onset = start_seconds + progress * max(0.0, duration_seconds - 0.22)
                pulse = highpass_noise(int(0.18 * SR)) * np.linspace(1.0, 0.0, int(0.18 * SR), dtype=np.float32)
                add_mono(buffer, onset, pulse, gain=gain * 0.55, pan=-spread)
                add_mono(buffer, onset, pulse, gain=gain * 0.55, pan=spread)
            continue
        if parameter == "distortion":
            n = max(1, int(duration_seconds * SR))
            t = np.arange(n, dtype=np.float32) / SR
            progress = _curve_progress(np.linspace(0.0, 1.0, n, dtype=np.float32), curve)
            freq = 90.0 + 120.0 * start + (180.0 + 280.0 * end - (90.0 + 120.0 * start)) * progress
            tone = np.sin(2.0 * np.pi * np.cumsum(freq) / SR).astype(np.float32)
            saturated = np.tanh(tone * (1.6 + 4.0 * (start + (end - start) * progress))).astype(np.float32)
            env = 0.2 + 0.6 * start + (0.4 + 0.9 * end - (0.2 + 0.6 * start)) * progress
            add_mono(buffer, start_seconds, saturated * env, gain=gain * 0.85, pan=0.0)
            continue
        start_freq = 120.0 + 2600.0 * start
        end_freq = 220.0 + 6200.0 * end
        add_mono(
            buffer,
            start_seconds,
            riser(duration_seconds, start_freq, end_freq),
            gain=gain,
            pan=0.0,
        )


def _starter_plucks(ctx: RenderContext, section: dict, track: dict) -> None:
    """Plucks answer the lead rather than doubling it.

    They play on the offbeats, an octave above the chord, so they land in the
    gaps a hook leaves rather than competing with it for the same moment."""
    buffer = _track_buffer(ctx, track["id"])
    defaults = _section_defaults(section)
    energy = float(defaults.get("energy", 1.0))
    sparse = section["type"] in {"intro", "break", "outro"}
    offsets = (1.5, 3.5) if sparse else (0.75, 1.5, 2.75, 3.5)
    for local_bar, bar in enumerate(range(section["startBar"], section["startBar"] + section["bars"])):
        chord = _progression_for_bar(section, bar)
        notes = list(chord["notes"]) or [int(chord["root"]) + 12]
        for index, onset in enumerate(offsets):
            # Skip a hit every other bar so the pattern breathes instead of
            # reading as a machine-gun sixteenth line.
            if sparse and local_bar % 2 == 1 and index == 1:
                continue
            note = int(notes[(local_bar + index) % len(notes)]) + 12
            _schedule_note(
                buffer, bar_beat(bar, onset), 0.45, note, synth_pluck,
                gain=track.get("gain", 0.8) * (0.05 if sparse else 0.07) * energy,
                pan=-0.34 if index % 2 else 0.34,
            )


def _starter_vocals(ctx: RenderContext, section: dict, track: dict) -> None:
    """A stand-in for the vocal chop line.

    There is no vocal sample to place, so this renders the hook's own first two
    notes an octave up, short and wide, which is what a chopped topline does
    structurally. It is audible, it sits in the right register, and it answers
    the lead — a real part rather than a placeholder blip."""
    buffer = _track_buffer(ctx, track["id"])
    defaults = _section_defaults(section)
    energy = float(defaults.get("energy", 1.0))
    motif = _lead_motif_for_section(section)
    if not motif:
        return
    for local_bar, bar in enumerate(range(section["startBar"], section["startBar"] + section["bars"])):
        # Chops answer on alternate bars; doubling every bar buries the hook.
        if local_bar % 2 == 0 and section["type"] in {"drop", "second_drop"}:
            continue
        bar_motif = motif[local_bar % len(motif)]
        for index, event in enumerate(bar_motif[:2]):
            onset = float(event["beat"]) + 2.0
            if onset >= 4.0:
                onset -= 2.0
            _schedule_note(
                buffer, bar_beat(bar, onset), 0.35, int(event["note"]) + 12, synth_pluck,
                gain=track.get("gain", 0.8) * 0.055 * energy,
                pan=0.30 if index % 2 else -0.30,
            )


def _starter_sample(ctx: RenderContext, section: dict, track: dict) -> None:
    """A one-shot texture, placed once per section rather than per bar.

    This lane stands in for the found sounds a walkthrough describes but cannot
    hand over — breaths, reverses, one-off oddities. Making it a single accent
    at the section boundary keeps it doing the job those sounds actually do:
    marking a change, not carrying a part."""
    buffer = _track_buffer(ctx, track["id"])
    defaults = _section_defaults(section)
    energy = float(defaults.get("energy", 1.0))
    root = int(_progression_for_bar(section, section["startBar"])["root"])
    add_mono(
        buffer,
        beat_to_seconds(bar_beat(section["startBar"])),
        synth_pluck(note_to_freq(root + 24), 1.2 * BEAT),
        gain=track.get("gain", 0.8) * 0.06 * energy,
        pan=-0.22,
    )
    # A second accent halfway through anything long enough to need one.
    if section["bars"] >= 8:
        middle = section["startBar"] + section["bars"] // 2
        add_mono(
            buffer,
            beat_to_seconds(bar_beat(middle, 2.0)),
            synth_pluck(note_to_freq(root + 19), 0.9 * BEAT),
            gain=track.get("gain", 0.8) * 0.045 * energy,
            pan=0.26,
        )


def _render_lane_starter(ctx: RenderContext, section: dict, track: dict) -> None:
    if track["id"] == "chords":
        _starter_chords(ctx, section, track)
    elif track["id"] == "bass":
        _starter_bass(ctx, section, track)
    elif track["id"] == "sub":
        _starter_sub(ctx, section, track)
    elif track["id"] == "lead":
        _starter_lead(ctx, section, track)
    elif track["id"] == "drums":
        _starter_drums(ctx, section, track)
    elif track["id"] == "clap-stack":
        _starter_clap_stack(ctx, section, track)
    elif track["id"] == "hat-ride":
        _starter_hat_ride(ctx, section, track)
    elif track["id"] == "fx":
        _starter_fx(ctx, section, track)
    elif track["id"] == "guitar":
        _starter_guitar(ctx, section, track)
    elif track["id"] == "filter-auto":
        _starter_filter_auto(ctx, section, track)
    elif track["id"] == "plucks":
        _starter_plucks(ctx, section, track)
    elif track["id"] == "vocals":
        _starter_vocals(ctx, section, track)
    elif track["id"] == "sample":
        _starter_sample(ctx, section, track)


# ---------------------------------------------------------------------------
# Technique pass
#
# Sections arrive with the techniques the transcript named. The functions below
# turn those words into audio. The pass runs once per section after every lane
# has rendered, on the slice of each stem that section owns, so a technique only
# touches the bars the tutorial attached it to. Each effect is a pure function on
# a (samples, 2) float array so it can be checked on a sine without rendering a
# song, and each is plain numpy so the emitted renderer stays self-contained.
# ---------------------------------------------------------------------------

SIDECHAIN_DEPTHS = {"sub": 0.65, "bass": 0.50, "chords": 0.45, "plucks": 0.35}
SIDECHAIN_ATTACK_SECONDS = 0.005
SIDECHAIN_RELEASE_BEATS = 0.5
REVERB_TARGETS = ("lead", "chords", "vocals", "plucks")
REVERB_WET = 0.22
REVERB_DECAY_SECONDS = 1.6
REVERB_HIGHPASS_HZ = 300.0
DELAY_TARGETS = ("lead", "vocals")
DELAY_NOTE_BEATS = 0.75
DELAY_FEEDBACK = 0.38
DELAY_WET = 0.28
SWEEP_TARGETS = ("lead", "chords", "plucks")
SWEEP_START_HZ = 400.0
SWEEP_END_HZ = 12000.0
# "Filtering" outside a build: a producer opens the filter into the song and
# closes it on the way out. Drops are left static; a sweep across a drop is not
# what anyone means by filtering there.
SWEEP_OPEN_TYPES = ("pre_intro", "intro", "verse", "pre_build")
SWEEP_CLOSE_TYPES = ("break", "outro")
SWEEP_OPEN_START_HZ = 600.0
SWEEP_OPEN_END_HZ = 10000.0
DROP_AUTOMATION_START_HZ = 800.0
DROP_AUTOMATION_END_HZ = 12000.0
EQ_HIGHPASS_HZ = 120.0
EQ_HIGHPASS_POLES = 4
EQ_HIGHPASS_TARGETS = ("lead", "chords", "vocals", "plucks", "fx", "guitar", "sample")
EQ_BASS_HIGHPASS_HZ = 60.0
EQ_SUB_LOWPASS_HZ = 120.0
COMPRESSION_TARGETS = ("drums", "clap_stack", "vocals", "guitar")
COMPRESSION_THRESHOLD_DB = -18.0   # under the lane's own loudest moment
COMPRESSION_RATIO = 6.0            # OTT-territory, which is what these tutorials reach for
COMPRESSION_ATTACK_SECONDS = 0.005
COMPRESSION_RELEASE_SECONDS = 0.08
REVERSE_SOURCE_ORDER = ("chords", "lead", "fx")
REVERSE_SWELL_BEATS = 2.0
REVERSE_SWELL_DB = -6.0            # under the source, when the fx lane is empty
REVERSE_SWELL_ABOVE_LANE_DB = 9.0  # over the fx lane's own level, so it reads as a swell
MASTER_DRIVE_DB = 6.0
MASTER_LIMITER_RELEASE_SECONDS = 0.05
DISTORTION_TARGETS = ("bass", "lead")
DISTORTION_DRIVE = 2.2
WIDEN_TARGETS = ("chords", "plucks", "fx")
WIDEN_DELAY_MS = 12.0
WIDEN_LEVEL_DB = -3.0
SNARE_LAYER_DB = -9.0
EFFECT_TAIL_SECONDS = 2.5
HANDLED_TECHNIQUES = ("sidechain", "reverb", "delay", "filtering", "automation", "distortion", "stereo", "layering", "eq", "compression", "reverse")

# Lane offsets relative to the drums, from the rubric's gain_ladder step, keyed
# by stem id. Anything not listed sits at the default so a new lane is never
# accidentally the loudest thing in the mix.
GAIN_LADDER_DB = {
    "drums": 0.0,
    "sub": -7.0,
    "bass": -7.0,
    "lead": -4.0,
    "clap_stack": -6.0,
    "chords": -7.0,
    "vocals": -8.0,
    "plucks": -12.0,
    "fx": -12.0,
    "hat_ride": -14.0,
    "guitar": -6.0,
    "sample": -10.0,
    "filter_auto": -12.0,
}
GAIN_LADDER_DEFAULT_DB = -10.0
GAIN_LADDER_REFERENCE_ORDER = ("drums", "clap_stack", "bass", "sub", "lead", "chords")
MASTER_PEAK_DBFS = -1.0


def db_to_gain(db: float) -> float:
    return float(10.0 ** (db / 20.0))


def _one_pole_scan(x: np.ndarray, a, b, y0: float = 0.0) -> np.ndarray:
    """y[n] = a[n] * y[n-1] + b[n] * x[n], vectorised; a and b may be scalars or arrays.

    numpy has no scan, and a per-sample Python loop over a three-minute stem takes
    minutes. Rewriting the recursion with cumulative products turns each chunk
    into one cumsum. Chunks are kept short enough that the running product cannot
    underflow, and the last output of a chunk seeds the next one."""
    x = np.asarray(x, dtype=np.float64)
    n = len(x)
    out = np.empty(n, dtype=np.float64)
    if n == 0:
        return out
    a_arr = np.broadcast_to(np.asarray(a, dtype=np.float64), (n,))
    b_arr = np.broadcast_to(np.asarray(b, dtype=np.float64), (n,))
    a_min = float(min(max(float(np.min(a_arr)), 1e-3), 1.0))
    chunk = 4096 if a_min >= 1.0 else int(min(4096, max(16, math.floor(-200.0 / math.log10(a_min)))))
    prev = float(y0)
    for start in range(0, n, chunk):
        stop = min(n, start + chunk)
        running = np.cumprod(a_arr[start:stop])
        driven = np.cumsum(b_arr[start:stop] * x[start:stop] / running)
        y = running * (prev + driven)
        out[start:stop] = y
        prev = float(y[-1])
    return out


def lowpass_vectorised(x: np.ndarray, cutoff_hz: float, sr: int = SR) -> np.ndarray:
    """One-pole low-pass, same response as one_pole_lowpass but fast enough for whole stems."""
    rc = 1.0 / (2.0 * math.pi * max(cutoff_hz, 1.0))
    dt = 1.0 / sr
    alpha = dt / (rc + dt)
    return _one_pole_scan(x, 1.0 - alpha, alpha)


def highpass_vectorised(x: np.ndarray, cutoff_hz: float, sr: int = SR) -> np.ndarray:
    """One-pole high-pass: y[n] = a * (y[n-1] + x[n] - x[n-1])."""
    rc = 1.0 / (2.0 * math.pi * max(cutoff_hz, 1.0))
    dt = 1.0 / sr
    a = rc / (rc + dt)
    step = np.diff(np.asarray(x, dtype=np.float64), prepend=0.0)
    return _one_pole_scan(step, a, a)


def sidechain_envelope(n: int, onsets_seconds, sr: int = SR, bpm: float = BPM, attack_seconds: float = SIDECHAIN_ATTACK_SECONDS, release_beats: float = SIDECHAIN_RELEASE_BEATS) -> np.ndarray:
    """0..1 duck amount over n samples: a 5 ms attack into a smooth release lasting an eighth note.

    The release is a smoothstep rather than a straight line because a compressor
    keyed from a kick holds near full reduction while the kick body is still
    sounding and lets go towards the end of the eighth; that is what reads as a
    pump rather than a volume wobble."""
    env = np.zeros(n, dtype=np.float64)
    attack_n = max(1, int(round(attack_seconds * sr)))
    release_n = max(1, int(round(release_beats * (60.0 / bpm) * sr)))
    release_progress = np.linspace(0.0, 1.0, release_n)
    shape = np.concatenate([
        np.linspace(0.0, 1.0, attack_n, endpoint=False),
        1.0 - (3.0 * release_progress ** 2 - 2.0 * release_progress ** 3),
    ])
    for onset in onsets_seconds:
        start = int(round(float(onset) * sr))
        stop = start + len(shape)
        lo = max(start, 0)
        hi = min(stop, n)
        if hi <= lo:
            continue
        env[lo:hi] = np.maximum(env[lo:hi], shape[lo - start:hi - start])
    return env


def apply_sidechain(stereo: np.ndarray, onsets_seconds, depth: float, sr: int = SR, bpm: float = BPM) -> np.ndarray:
    """Duck the signal by `depth` at every kick onset: gain = 1 - depth * envelope."""
    env = sidechain_envelope(len(stereo), onsets_seconds, sr=sr, bpm=bpm)
    gain = (1.0 - float(depth) * env).astype(np.float32)
    return (np.asarray(stereo, dtype=np.float32) * gain[:, None]).astype(np.float32)


def _feedback_comb(x: np.ndarray, delay: int, g: float) -> np.ndarray:
    # y[n] = x[n] + g * y[n - delay]. Blocks of `delay` samples only depend on
    # the previous block, so the recursion vectorises one block at a time.
    n = len(x)
    y = np.zeros(n, dtype=np.float64)
    y[:delay] = x[:delay]
    for start in range(delay, n, delay):
        stop = min(n, start + delay)
        y[start:stop] = x[start:stop] + g * y[start - delay:stop - delay]
    return y


def _allpass(x: np.ndarray, delay: int, g: float) -> np.ndarray:
    # y[n] = -g * x[n] + x[n - delay] + g * y[n - delay]
    n = len(x)
    y = np.zeros(n, dtype=np.float64)
    y[:delay] = -g * x[:delay]
    for start in range(delay, n, delay):
        stop = min(n, start + delay)
        y[start:stop] = -g * x[start:stop] + x[start - delay:stop - delay] + g * y[start - delay:stop - delay]
    return y


REVERB_COMB_DELAYS = (1557, 1617, 1491, 1422)
REVERB_ALLPASS_DELAYS = (556, 341)
REVERB_STEREO_SPREAD = 23


def schroeder_reverb(stereo: np.ndarray, sr: int = SR, decay_seconds: float = REVERB_DECAY_SECONDS) -> np.ndarray:
    """Wet-only Schroeder reverb: four parallel feedback combs into two series allpasses.

    The right channel's delays are nudged by a few samples so the two tails
    decorrelate and the reverb reads as a space rather than a mono echo. The comb
    sum is normalised by its average power gain so `wet` means the same thing
    whatever the decay time."""
    x = np.asarray(stereo, dtype=np.float64)
    out = np.zeros_like(x)
    scale = sr / 44100.0
    for channel in range(x.shape[1]):
        spread = 0 if channel == 0 else REVERB_STEREO_SPREAD
        acc = np.zeros(len(x), dtype=np.float64)
        power_gain = 0.0
        for base in REVERB_COMB_DELAYS:
            delay = max(1, int(round((base + spread) * scale)))
            g = 10.0 ** (-3.0 * delay / (max(decay_seconds, 0.05) * sr))
            acc += _feedback_comb(x[:, channel], delay, g)
            power_gain += 1.0 / (1.0 - g * g)
        acc /= math.sqrt(power_gain)
        for base in REVERB_ALLPASS_DELAYS:
            acc = _allpass(acc, max(1, int(round((base + spread) * scale))), 0.5)
        out[:, channel] = acc
    return out


def apply_reverb(stereo: np.ndarray, sr: int = SR, wet: float = REVERB_WET, decay_seconds: float = REVERB_DECAY_SECONDS, highpass_hz: float = REVERB_HIGHPASS_HZ) -> np.ndarray:
    """Dry plus a reverb send. The send is high-passed so the tail never sits on the low end."""
    x = np.asarray(stereo, dtype=np.float64)
    send = np.stack([
        lowpass_vectorised(highpass_vectorised(x[:, channel], highpass_hz, sr), 7000.0, sr)
        for channel in range(x.shape[1])
    ], axis=1)
    return (x + float(wet) * schroeder_reverb(send, sr, decay_seconds)).astype(np.float32)


def apply_pingpong_delay(stereo: np.ndarray, sr: int = SR, bpm: float = BPM, note_beats: float = DELAY_NOTE_BEATS, feedback: float = DELAY_FEEDBACK, wet: float = DELAY_WET, max_repeats: int = 16) -> np.ndarray:
    """Stereo ping-pong: the mono sum repeats every `note_beats`, first left, then right, fading by `feedback`."""
    x = np.asarray(stereo, dtype=np.float64)
    n = len(x)
    delay = max(1, int(round(note_beats * (60.0 / bpm) * sr)))
    mono = 0.5 * (x[:, 0] + x[:, 1])
    echoes = np.zeros_like(x)
    amp = 1.0
    for repeat in range(1, max_repeats + 1):
        offset = repeat * delay
        if offset >= n or amp < 1e-3:
            break
        echoes[offset:, (repeat - 1) % 2] += amp * mono[:n - offset]
        amp *= feedback
    return (x + float(wet) * echoes).astype(np.float32)


def apply_filter_sweep(stereo: np.ndarray, sr: int = SR, start_hz: float = SWEEP_START_HZ, end_hz: float = SWEEP_END_HZ) -> np.ndarray:
    """One-pole low-pass whose cutoff glides from start_hz to end_hz across the whole array.

    The glide is exponential in frequency (constant octaves per second), which is
    how a filter knob turned steadily sounds; a linear sweep spends almost all of
    its time already open."""
    x = np.asarray(stereo, dtype=np.float64)
    n = len(x)
    if n == 0:
        return np.asarray(stereo, dtype=np.float32)
    progress = np.linspace(0.0, 1.0, n)
    cutoff = start_hz * (end_hz / start_hz) ** progress
    dt = 1.0 / sr
    alpha = dt / (1.0 / (2.0 * math.pi * cutoff) + dt)
    out = np.empty_like(x)
    for channel in range(x.shape[1]):
        out[:, channel] = _one_pole_scan(x[:, channel], 1.0 - alpha, alpha)
    return out.astype(np.float32)


def _sweep_range_for(section_type: str, techniques: list) -> "tuple[float, float] | None":
    """Where a filter goes for this section, or None when nothing should move."""
    if section_type == "build" and ("filtering" in techniques or "automation" in techniques):
        return SWEEP_START_HZ, SWEEP_END_HZ
    if "filtering" not in techniques:
        return None
    if section_type in SWEEP_OPEN_TYPES:
        return SWEEP_OPEN_START_HZ, SWEEP_OPEN_END_HZ
    if section_type in SWEEP_CLOSE_TYPES:
        return SWEEP_OPEN_END_HZ, SWEEP_OPEN_START_HZ
    return None


def _drop_automation_range(section_type: str, techniques: list) -> "tuple[float, float] | None":
    if section_type in ("drop", "second_drop") and "automation" in techniques:
        return DROP_AUTOMATION_START_HZ, DROP_AUTOMATION_END_HZ
    return None


def _one_pole_alpha(cutoff_hz: float, sr: int) -> float:
    dt = 1.0 / sr
    return dt / (1.0 / (2.0 * math.pi * max(1.0, cutoff_hz)) + dt)


def apply_lowpass(stereo: np.ndarray, sr: int = SR, cutoff_hz: float = EQ_SUB_LOWPASS_HZ, poles: int = 2) -> np.ndarray:
    """Cascaded one-pole low-pass: two poles give the 12 dB/octave slope of a stock EQ band."""
    x = np.asarray(stereo, dtype=np.float64)
    if x.size == 0:
        return np.asarray(stereo, dtype=np.float32)
    alpha = _one_pole_alpha(cutoff_hz, sr)
    out = x.copy()
    for _ in range(max(1, poles)):
        for channel in range(out.shape[1]):
            out[:, channel] = _one_pole_scan(out[:, channel], 1.0 - alpha, alpha)
    return out.astype(np.float32)


def apply_highpass(stereo: np.ndarray, sr: int = SR, cutoff_hz: float = EQ_HIGHPASS_HZ, poles: int = 2) -> np.ndarray:
    """High-pass as the input minus its low-passed copy, one pole at a time."""
    x = np.asarray(stereo, dtype=np.float64)
    if x.size == 0:
        return np.asarray(stereo, dtype=np.float32)
    alpha = _one_pole_alpha(cutoff_hz, sr)
    out = x.copy()
    for _ in range(max(1, poles)):
        for channel in range(out.shape[1]):
            out[:, channel] = out[:, channel] - _one_pole_scan(out[:, channel], 1.0 - alpha, alpha)
    return out.astype(np.float32)


def apply_compressor(stereo: np.ndarray, sr: int = SR, threshold_db: float = COMPRESSION_THRESHOLD_DB, ratio: float = COMPRESSION_RATIO,
                     attack_seconds: float = COMPRESSION_ATTACK_SECONDS, release_seconds: float = COMPRESSION_RELEASE_SECONDS) -> np.ndarray:
    """Feed-forward RMS compressor with make-up so the loudest hit lands where it was.

    The threshold is relative to the block's own peak, so the amount of squash
    does not depend on how hot the lane was rendered. The follower is the larger
    of a fast and a slow one-pole, which is the cheap way to get a fast attack
    and a slow release without a per-sample loop."""
    x = np.asarray(stereo, dtype=np.float64)
    peak = float(np.max(np.abs(x))) if x.size else 0.0
    if peak <= 1e-9:
        return np.asarray(stereo, dtype=np.float32)
    power = np.mean(x * x, axis=1)
    fast = _one_pole_alpha(1.0 / (2.0 * math.pi * max(attack_seconds, 1e-4)), sr)
    slow = _one_pole_alpha(1.0 / (2.0 * math.pi * max(release_seconds, 1e-3)), sr)
    env = np.sqrt(np.maximum(_one_pole_scan(power, 1.0 - fast, fast), _one_pole_scan(power, 1.0 - slow, slow)))
    # Threshold against the follower's own loudest moment, not the sample peak:
    # a drum hit's RMS sits 10-15 dB under its transient, and a threshold set
    # from the transient never gets crossed.
    threshold = float(np.max(env)) * (10.0 ** (threshold_db / 20.0))
    over = np.maximum(env / max(threshold, 1e-12), 1.0)
    gain = over ** (1.0 / max(ratio, 1.0) - 1.0)
    y = x * gain[:, None]
    out_peak = float(np.max(np.abs(y))) if y.size else 0.0
    if out_peak > 1e-12:
        y *= peak / out_peak
    return y.astype(np.float32)


def limiter_gain_curve(stereo: np.ndarray, sr: int = SR, drive_db: float = MASTER_DRIVE_DB, ceiling_db: float = MASTER_PEAK_DBFS,
                       release_seconds: float = MASTER_LIMITER_RELEASE_SECONDS) -> np.ndarray:
    """Per-sample gain (drive included) that pushes the mix up by drive_db and
    holds every peak at the ceiling.

    Gain reduction is instant on the way in (no overshoot, so no clip) and
    released through a one-pole, which is what keeps it from sounding like a
    clipper. Returned as a curve so the same gain can be applied to every stem:
    the stems then still add up to the mastered mix, and the app - which plays
    the stems - sits at the same level as the file."""
    x = np.asarray(stereo, dtype=np.float64) * (10.0 ** (drive_db / 20.0))
    if x.size == 0:
        return np.ones(0, dtype=np.float64)
    ceiling = 10.0 ** (ceiling_db / 20.0)
    amplitude = np.max(np.abs(x), axis=1)
    desired = np.minimum(1.0, ceiling / np.maximum(amplitude, 1e-9))
    release = _one_pole_alpha(1.0 / (2.0 * math.pi * max(release_seconds, 1e-3)), sr)
    smoothed = _one_pole_scan(desired, 1.0 - release, release, y0=1.0)
    return np.minimum(desired, smoothed) * (10.0 ** (drive_db / 20.0))


def apply_peak_limiter(stereo: np.ndarray, sr: int = SR, drive_db: float = MASTER_DRIVE_DB, ceiling_db: float = MASTER_PEAK_DBFS,
                       release_seconds: float = MASTER_LIMITER_RELEASE_SECONDS) -> np.ndarray:
    """The mix through limiter_gain_curve, with a hard clip as a guard, not the design."""
    x = np.asarray(stereo, dtype=np.float64)
    if x.size == 0:
        return np.asarray(stereo, dtype=np.float32)
    curve = limiter_gain_curve(x, sr, drive_db, ceiling_db, release_seconds)
    ceiling = 10.0 ** (ceiling_db / 20.0)
    return np.clip(x * curve[:, None], -ceiling, ceiling).astype(np.float32)


def reverse_swell(source: np.ndarray, level_db: float = REVERSE_SWELL_DB, reference_peak: "float | None" = None,
                  target_rms: "float | None" = None) -> np.ndarray:
    """The classic reverse: the first thing you hear, played backwards into itself.

    With target_rms the loud end of the swell (its last quarter) lands at that
    RMS - what the ear compares against the lane it sits on; a chord slice has
    a 13 dB crest, so scaling by peak would leave it under the bed. Otherwise
    the swell peaks level_db under reference_peak or the source's own peak."""
    x = np.asarray(source, dtype=np.float64)[::-1].copy()
    n = len(x)
    if n == 0:
        return np.zeros((0, 2), dtype=np.float32)
    ramp = np.linspace(0.0, 1.0, n) ** 2
    x *= ramp[:, None]
    if target_rms is not None:
        loud_end = x[-max(1, n // 4):]
        current = math.sqrt(float(np.mean(loud_end * loud_end))) if loud_end.size else 0.0
        if current > 1e-9:
            x *= float(target_rms) / current
        return x.astype(np.float32)
    peak = float(np.max(np.abs(x))) if x.size else 0.0
    target = float(reference_peak) if reference_peak else float(np.max(np.abs(source)))
    if peak > 1e-9:
        x *= (10.0 ** (level_db / 20.0)) * target / peak
    return x.astype(np.float32)


def noise_riser(duration_seconds: float, sr: int = SR, seed: int = 2203) -> np.ndarray:
    """A white-noise riser: two decorrelated noise channels opening up and swelling to the end."""
    n = max(1, int(duration_seconds * sr))
    rng = np.random.default_rng(seed)
    noise = np.stack([rng.standard_normal(n), rng.standard_normal(n)], axis=1)
    swept = apply_filter_sweep(noise, sr, 600.0, 14000.0).astype(np.float64)
    env = np.linspace(0.0, 1.0, n) ** 2.0
    return (0.14 * swept * env[:, None]).astype(np.float32)


def apply_soft_clip(stereo: np.ndarray, drive: float = DISTORTION_DRIVE) -> np.ndarray:
    """tanh saturation, driven relative to the signal's own peak and returned at its original RMS.

    Driving relative to the peak means the amount of grit does not depend on
    how hot the lane happened to be rendered; matching the RMS afterwards means
    turning distortion on never turns the part up."""
    x = np.asarray(stereo, dtype=np.float64)
    peak = float(np.max(np.abs(x))) if x.size else 0.0
    if peak <= 1e-9:
        return np.asarray(stereo, dtype=np.float32)
    rms_in = math.sqrt(float(np.mean(x * x)))
    y = np.tanh(float(drive) * x / peak)
    rms_out = math.sqrt(float(np.mean(y * y)))
    if rms_out > 1e-12:
        y *= rms_in / rms_out
    return y.astype(np.float32)


def apply_haas_widener(stereo: np.ndarray, sr: int = SR, delay_ms: float = WIDEN_DELAY_MS, level_db: float = WIDEN_LEVEL_DB) -> np.ndarray:
    """Haas widening: each channel gets a short delayed copy of itself, added on the left and
    subtracted on the right, so the side signal grows while the mono sum is unchanged."""
    x = np.asarray(stereo, dtype=np.float64)
    delay = max(1, int(round(delay_ms / 1000.0 * sr)))
    g = db_to_gain(level_db)
    out = x.copy()
    if delay < len(x):
        out[delay:, 0] += g * x[:-delay, 0]
        out[delay:, 1] -= g * x[:-delay, 1]
    out /= math.sqrt(1.0 + g * g)
    return out.astype(np.float32)


def snare_layer_burst(sr: int = SR, seed: int = 9021) -> np.ndarray:
    """A 110 ms band-passed noise burst, peak-normalised, to sit under a snare or clap."""
    n = max(1, int(0.11 * sr))
    t = np.arange(n, dtype=np.float64) / sr
    noise = np.random.default_rng(seed).standard_normal(n)
    shaped = lowpass_vectorised(highpass_vectorised(noise, 900.0, sr), 5000.0, sr) * np.exp(-t * 32.0)
    peak = float(np.max(np.abs(shaped)))
    return (shaped / peak if peak > 0 else shaped).astype(np.float32)


def apply_snare_layer(stereo: np.ndarray, hits, sr: int = SR, relative_db: float = SNARE_LAYER_DB) -> np.ndarray:
    """Add a noise layer under each (onset_seconds, hit_peak) at relative_db below the hit's own peak."""
    out = np.array(stereo, dtype=np.float32, copy=True)
    burst = snare_layer_burst(sr)
    left, right = equal_power_pan(0.0)
    level = db_to_gain(relative_db)
    n = len(out)
    for onset, hit_peak in hits:
        start = int(round(float(onset) * sr))
        stop = min(n, start + len(burst))
        if start < 0 or stop <= start:
            continue
        chunk = burst[:stop - start] * (float(hit_peak) * level)
        out[start:stop, 0] += chunk * left
        out[start:stop, 1] += chunk * right
    return out


def stem_level_db(audio: np.ndarray, sr: int = SR, window_seconds: float = 0.1) -> float:
    """Level of a stem while it is actually playing, in dBFS.

    Whole-file RMS punishes a lane that rests for half the song, and the peak is
    set by one crash. The 95th percentile of 100 ms window RMS tracks the hits
    for a drum lane and the sustain for a pad, which is the level a fader is set
    against. Silence reports -120."""
    x = np.asarray(audio, dtype=np.float64)
    if x.ndim == 2:
        power = np.mean(x * x, axis=1)
    else:
        power = x * x
    window = max(1, int(window_seconds * sr))
    usable = (len(power) // window) * window
    if usable == 0:
        return -120.0
    window_power = power[:usable].reshape(-1, window).mean(axis=1)
    loudest = float(window_power.max())
    if loudest <= 1e-20:
        return -120.0
    playing = window_power[window_power > loudest * 1e-6]
    return float(10.0 * math.log10(float(np.percentile(playing, 95)) + 1e-20))


def gain_ladder_scales(stems: dict) -> dict:
    """Per-stem linear scale so each lane sits at its GAIN_LADDER_DB offset from the drums.

    Silent stems keep a scale of 1.0. When there is no drums stem the next lane in
    GAIN_LADDER_REFERENCE_ORDER anchors the ladder and the offsets shift with it."""
    levels = {stem_id: stem_level_db(audio) for stem_id, audio in stems.items()}
    audible = [stem_id for stem_id, level in levels.items() if level > -100.0]
    if not audible:
        return {stem_id: 1.0 for stem_id in stems}
    reference = next((stem_id for stem_id in GAIN_LADDER_REFERENCE_ORDER if stem_id in audible), audible[0])
    reference_offset = GAIN_LADDER_DB.get(reference, GAIN_LADDER_DEFAULT_DB)
    scales = {}
    for stem_id in stems:
        if stem_id not in audible:
            scales[stem_id] = 1.0
            continue
        target = levels[reference] + GAIN_LADDER_DB.get(stem_id, GAIN_LADDER_DEFAULT_DB) - reference_offset
        scales[stem_id] = db_to_gain(target - levels[stem_id])
    return scales


def master_peak_scale(mix: np.ndarray, peak_dbfs: float = MASTER_PEAK_DBFS) -> float:
    """The single gain that puts the mix's peak at peak_dbfs. Silence returns 1.0."""
    peak = float(np.max(np.abs(mix))) if np.asarray(mix).size else 0.0
    if peak <= 1e-12:
        return 1.0
    return db_to_gain(peak_dbfs) / peak


def _section_window(section: dict) -> tuple[int, int]:
    start = int(round(beat_to_seconds(bar_beat(section["startBar"])) * SR))
    end = int(round(beat_to_seconds(bar_beat(section["startBar"] + section["bars"])) * SR))
    return max(0, min(start, N_SAMPLES)), max(0, min(end, N_SAMPLES))


def _process_window(stem: np.ndarray, start: int, end: int, effect, tail_samples: int = 0) -> None:
    """Run `effect` on the section's slice of a stem, in place.

    A reverb or delay keeps ringing after the section ends. Feeding the effect
    the slice plus silence and ADDING whatever comes out past the end to the
    next section keeps the tail, without processing the next section's notes."""
    n = end - start
    if n <= 0:
        return
    tail = max(0, min(int(tail_samples), len(stem) - end))
    block = np.zeros((n + tail, stem.shape[1]), dtype=np.float32)
    block[:n] = stem[start:end]
    out = effect(block)
    stem[start:end] = out[:n]
    if tail > 0:
        stem[end:end + tail] += out[n:n + tail]


def _sample_peak(audio: np.ndarray) -> float:
    return float(np.max(np.abs(audio))) if np.asarray(audio).size else 0.0


def apply_section_techniques(ctx: RenderContext, section: dict) -> list[str]:
    """Apply the techniques the section lists to the stems over the section's bars.

    Returns one human-readable line per technique that changed audio. A section
    that lists nothing is left untouched."""
    techniques = [str(item).strip().lower() for item in (section.get("techniques") or [])]
    if not techniques:
        return []
    start, end = _section_window(section)
    if end <= start:
        return []
    stems = ctx.stems
    section_tracks = set(section.get("trackIds") or [])
    section_start_seconds = start / SR
    tail = int(EFFECT_TAIL_SECONDS * SR)
    applied: list[str] = []

    if "layering" in techniques:
        layered: list[str] = []
        if "drums" in section_tracks and "drums" in stems:
            track = TRACK_PLAN_BY_ID.get("drums", {})
            snare_peak = _sample_peak(snare(False))
            hits = [(onset, gain * snare_peak) for onset, gain in _snare_hits_for_section(section, track)]
            if hits:
                stems["drums"][:] = apply_snare_layer(stems["drums"], hits)
                layered.append(f"drums x{len(hits)}")
        if "clap-stack" in section_tracks and "clap_stack" in stems:
            track = TRACK_PLAN_BY_ID.get("clap-stack", {})
            clap_peak = _sample_peak(snare(True))
            hits = [(onset, gain * clap_peak) for onset, gain in _clap_hits_for_section(section, track)]
            if hits:
                stems["clap_stack"][:] = apply_snare_layer(stems["clap_stack"], hits)
                layered.append(f"clap_stack x{len(hits)}")
        if layered:
            applied.append(f"layering: noise layer {SNARE_LAYER_DB:.0f} dB under {', '.join(layered)}")

    sweep = _sweep_range_for(str(section.get("type") or ""), techniques)
    if sweep is not None:
        lo, hi = sweep
        targets = [key for key in SWEEP_TARGETS if key in stems]
        for key in targets:
            _process_window(stems[key], start, end, lambda block, lo=lo, hi=hi: apply_filter_sweep(block, SR, lo, hi))
        if targets:
            applied.append(f"filter {'opens' if hi > lo else 'closes'}: {lo:.0f} Hz -> {hi:.0f} Hz on {', '.join(targets)}")
    elif "filtering" in techniques and section.get("type") in ("drop", "second_drop"):
        applied.append("filtering: left static in the drop (a sweep across a drop is not what a producer means by it)")
    motion = _drop_automation_range(str(section.get("type") or ""), techniques)
    if motion is not None and "lead" in stems:
        lo, hi = motion
        _process_window(stems["lead"], start, end, lambda block, lo=lo, hi=hi: apply_filter_sweep(block, SR, lo, hi))
        applied.append(f"automation: the lead opens {lo:.0f} Hz -> {hi:.0f} Hz across the drop")
    if "distortion" in techniques:
        targets = [key for key in DISTORTION_TARGETS if key in stems]
        for key in targets:
            _process_window(stems[key], start, end, lambda block: apply_soft_clip(block, DISTORTION_DRIVE))
        if targets:
            applied.append(f"distortion: tanh drive {DISTORTION_DRIVE} on {', '.join(targets)}")

    if "eq" in techniques:
        cut: list[str] = []
        for key in EQ_HIGHPASS_TARGETS:
            if key in stems and key.replace("_", "-") in section_tracks:
                _process_window(stems[key], start, end, lambda block: apply_highpass(block, SR, EQ_HIGHPASS_HZ, EQ_HIGHPASS_POLES))
                cut.append(key)
        parts = []
        if cut:
            parts.append(f"high-pass {EQ_HIGHPASS_HZ:.0f} Hz on {', '.join(cut)}")
        if "bass" in stems and "bass" in section_tracks:
            _process_window(stems["bass"], start, end, lambda block: apply_highpass(block, SR, EQ_BASS_HIGHPASS_HZ))
            parts.append(f"bass high-passed {EQ_BASS_HIGHPASS_HZ:.0f} Hz")
        if "sub" in stems and "sub" in section_tracks:
            _process_window(stems["sub"], start, end, lambda block: apply_lowpass(block, SR, EQ_SUB_LOWPASS_HZ))
            parts.append(f"sub low-passed {EQ_SUB_LOWPASS_HZ:.0f} Hz so it owns the bottom alone")
        if parts:
            applied.append("eq: " + "; ".join(parts))
    if "compression" in techniques:
        targets = [key for key in COMPRESSION_TARGETS if key in stems and key.replace("_", "-") in section_tracks]
        for key in targets:
            _process_window(stems[key], start, end, lambda block: apply_compressor(block, SR))
        if targets:
            applied.append(f"compression: {COMPRESSION_RATIO:.0f}:1 above {COMPRESSION_THRESHOLD_DB:.0f} dB (peak-relative), "
                           f"{COMPRESSION_ATTACK_SECONDS * 1000:.0f} ms / {COMPRESSION_RELEASE_SECONDS * 1000:.0f} ms on {', '.join(targets)}")
    if "reverse" in techniques:
        if section["startBar"] <= 0:
            applied.append("reverse: nothing plays before the first bar to swell into it")
        else:
            length = int(round(REVERSE_SWELL_BEATS * BEAT * SR))
            source_key = next((key for key in REVERSE_SOURCE_ORDER if key in stems and key.replace("_", "-") in section_tracks
                               and float(np.max(np.abs(stems[key][start:start + length]))) > 1e-6), None)
            if source_key is not None and start - length >= 0:
                fx_stem = _track_buffer(ctx, "fx")
                lane_level = stem_level_db(fx_stem)
                if lane_level > -100.0:
                    swell = reverse_swell(stems[source_key][start:start + length], target_rms=db_to_gain(lane_level + REVERSE_SWELL_ABOVE_LANE_DB))
                    level_note = f"+{REVERSE_SWELL_ABOVE_LANE_DB:.0f} dB over the fx lane's level"
                else:
                    swell = reverse_swell(stems[source_key][start:start + length], REVERSE_SWELL_DB)
                    level_note = f"{REVERSE_SWELL_DB:.0f} dB under the {source_key}"
                fx_stem[start - length:start] += swell
                applied.append(f"reverse: the first {REVERSE_SWELL_BEATS:.0f} beats of {source_key} reversed into bar {section['startBar']} on fx, {level_note}")
    if section.get("type") == "build" and ("filtering" in techniques or "automation" in techniques):
        # The fx lane already renders a riser across any build it plays in; only
        # add one when the build has no fx lane to carry it.
        fx_profile = _section_defaults(section).get("fxProfile") or {}
        riser_present = "fx" in section_tracks and bool(fx_profile.get("riser"))
        if not riser_present:
            last_bar = section["startBar"] + section["bars"] - 1
            riser_start = beat_to_seconds(bar_beat(last_bar))
            fx_gain = float(TRACK_PLAN_BY_ID.get("fx", {}).get("gain", 0.72)) * 0.34
            burst = noise_riser(4.0 * BEAT) * np.float32(fx_gain)
            fx_stem = _track_buffer(ctx, "fx")
            add_mono(fx_stem, riser_start, burst[:, 0], gain=1.0, pan=-0.4)
            add_mono(fx_stem, riser_start, burst[:, 1], gain=1.0, pan=0.4)
            applied.append(f"riser: white-noise riser on fx over bar {last_bar + 1}")

    if "sidechain" in techniques:
        onsets = [onset - section_start_seconds for onset in _kick_onsets_for_section(section)]
        ducked: list[str] = []
        for key, depth in SIDECHAIN_DEPTHS.items():
            if key not in stems:
                continue
            _process_window(stems[key], start, end, lambda block, depth=depth: apply_sidechain(block, onsets, depth, SR, BPM))
            ducked.append(f"{key} {depth:.2f}")
        if ducked and onsets:
            applied.append(f"sidechain: {len(onsets)} kick onsets ducking {', '.join(ducked)}")

    if "delay" in techniques:
        targets = [key for key in DELAY_TARGETS if key in stems]
        for key in targets:
            _process_window(stems[key], start, end, lambda block: apply_pingpong_delay(block, SR, BPM), tail_samples=tail)
        if targets:
            applied.append(f"delay: dotted-eighth ping-pong, feedback {DELAY_FEEDBACK}, wet {DELAY_WET} on {', '.join(targets)}")

    if "reverb" in techniques:
        targets = [key for key in REVERB_TARGETS if key in stems]
        for key in targets:
            _process_window(stems[key], start, end, lambda block: apply_reverb(block, SR), tail_samples=tail)
        if targets:
            applied.append(f"reverb: {REVERB_DECAY_SECONDS} s decay, wet {REVERB_WET}, HPF {REVERB_HIGHPASS_HZ:.0f} Hz on {', '.join(targets)}")

    if "stereo" in techniques:
        targets = [key for key in WIDEN_TARGETS if key in stems]
        widen_tail = int(WIDEN_DELAY_MS / 1000.0 * SR) + 1
        for key in targets:
            _process_window(stems[key], start, end, lambda block: apply_haas_widener(block, SR), tail_samples=widen_tail)
        if targets:
            applied.append(f"stereo: Haas {WIDEN_DELAY_MS:.0f} ms at {WIDEN_LEVEL_DB:.0f} dB on {', '.join(targets)}")

    return applied


def apply_song_techniques(ctx: RenderContext) -> None:
    """Run the technique pass for every section, in song order, and note what happened."""
    for section in SECTION_PLAN:
        techniques = [str(item).strip().lower() for item in (section.get("techniques") or [])]
        if not techniques:
            continue
        applied = apply_section_techniques(ctx, section)
        unhandled = [item for item in techniques if item not in HANDLED_TECHNIQUES]
        label = f"{section['label']} bars {section['startBar'] + 1}-{section['startBar'] + section['bars']}"
        if applied:
            ctx.notes.append(f"  ~ {label} techniques applied:")
            for line in applied:
                ctx.notes.append(f"      {line}")
        else:
            ctx.notes.append(f"  ~ {label}: no listed technique had a lane to act on")
        if unhandled:
            ctx.notes.append(f"      not rendered (no implementation yet): {', '.join(unhandled)}")


def _write_wav(path: Path, audio: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(audio, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(SR)
        handle.writeframes(pcm.tobytes())


def write_outputs(ctx: RenderContext) -> dict[str, str]:
    """Write every stem and the full mix, balanced by the gain ladder.

    Dividing the sum by the stem count left the melodic lanes tens of dB under
    the drums, because each lane was rendered at whatever level its synth
    happened to produce. The ladder sets every lane at its rubric offset from
    the drums, then one master gain puts the mix's peak at MASTER_PEAK_DBFS.
    The stems on disk get the same scales so they add up to the mix."""
    EXPORTS.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, str] = {}
    scales = gain_ladder_scales(ctx.stems)
    mix = stereo_buffer()
    for stem_id, audio in ctx.stems.items():
        audio *= np.float32(scales.get(stem_id, 1.0))
        mix += audio
    master = master_peak_scale(mix, MASTER_PEAK_DBFS)
    mix *= np.float32(master)
    # The master: the balance pushed up into a peak limiter. The limiter's gain
    # curve goes onto every stem too, so the stems still sum to the mix and the
    # app (which plays the stems) is as loud as the file.
    curve = limiter_gain_curve(mix, SR, MASTER_DRIVE_DB, MASTER_PEAK_DBFS).astype(np.float32)
    ceiling = np.float32(db_to_gain(MASTER_PEAK_DBFS))
    ladder_notes: list[str] = []
    for stem_id, audio in ctx.stems.items():
        audio *= np.float32(master)
        audio *= curve[:, None]
        np.clip(audio, -ceiling, ceiling, out=audio)
        stem_path = EXPORTS / f"{STEM_PREFIX}_{stem_id}.wav"
        _write_wav(stem_path, audio)
        outputs[stem_id] = str(stem_path)
        ladder_notes.append(f"{stem_id} {GAIN_LADDER_DB.get(stem_id, GAIN_LADDER_DEFAULT_DB):+.0f} dB -> {stem_level_db(audio):.1f} dBFS")
    mix_path = EXPORTS / f"{STEM_PREFIX}_full_mix.wav"
    # The stems are the balance; the mix is the balance through a master. A
    # peak-limited mix sits at a normal listening level without the stems
    # losing the punch a producer would want to keep working with.
    limited = np.clip(mix * curve[:, None], -ceiling, ceiling)
    _write_wav(mix_path, limited)
    outputs["full_mix"] = str(mix_path)
    ctx.notes.append(f"  = gain ladder (relative to drums), master peak {MASTER_PEAK_DBFS:.1f} dBFS:")
    for line in ladder_notes:
        ctx.notes.append(f"      {line}")
    rms = float(np.sqrt(np.mean(limited.astype(np.float64) ** 2))) if limited.size else 0.0
    peak = float(np.max(np.abs(limited))) if limited.size else 0.0
    rms_db = 20.0 * math.log10(max(rms, 1e-9))
    ctx.notes.append(f"  = master: +{MASTER_DRIVE_DB:.0f} dB into a peak limiter at {MASTER_PEAK_DBFS:.1f} dBFS -> "
                     f"RMS {rms_db:.1f} dBFS, crest {20.0 * math.log10(max(peak, 1e-9)) - rms_db:.1f} dB")
    ctx.exports = outputs
    return outputs


def sync_project_assets(outputs: dict[str, str]) -> None:
    assets: list[dict[str, str]] = []
    for track in TRACK_PLAN:
        stem_key = track["id"].replace("-", "_")
        output_path = outputs.get(stem_key)
        if not output_path:
            continue
        file_value = f"/api/audio/{Path(output_path).name}"
        assets.append({"trackId": track["id"], "file": file_value})
    if not assets:
        return
    for project_path in PROJECT_PATHS:
        if not project_path.exists():
            continue
        project = json.loads(project_path.read_text(encoding="utf-8"))
        snapshot = project.setdefault("snapshot", {})
        for track in snapshot.get("tracks", []) or []:
            track_id = track.get("id")
            for asset in assets:
                if asset["trackId"] == track_id:
                    track["file"] = asset["file"]
                    break
        project["assets"] = assets
        project_path.write_text(json.dumps(project, indent=2) + "\\n", encoding="utf-8")
'''


def ensure_project_renderer(root: Path, project_id: str, project_name: str, project: dict[str, Any], spec: dict[str, Any], prompt: str | None = None, overwrite: bool = False) -> Path:
    path = root / f"render_{stemify(project_id)}.py"
    if path.exists() and not overwrite:
        return path
    section_plan = render_section_plan(project, spec)
    track_plan = render_track_plan(project)
    render_order = [renderer_function_name(section, index) for index, section in enumerate(section_plan, start=1)]
    role_helper_functions = render_role_helper_functions(section_plan, track_plan)
    section_functions = render_section_functions(section_plan, track_plan)
    runtime_support = render_runtime_support()
    bpm = project["snapshot"]["bpm"]
    total_bars = max((clip["startBar"] + clip["bars"] for track in project["snapshot"]["tracks"] for clip in track.get("clips", [])), default=16)
    tail_seconds = 4.0
    track_ids = [track["id"] for track in project["snapshot"]["tracks"]]
    generated = f'''#!/usr/bin/env python3
from __future__ import annotations

"""
{renderer_doc(prompt, project_id, project_name)}
"""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RenderContext:
    stems: dict[str, np.ndarray] = field(default_factory=dict)
    exports: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


ROOT = Path(__file__).resolve().parent
PROJECT_ID = {project_id!r}
PROJECT_NAME = {project_name!r}
PROJECT_PATHS = [
    ROOT / "data" / "projects" / f"{{PROJECT_ID}}.neon.json",
    ROOT / "factory" / "projects" / f"{{PROJECT_ID}}.neon.json",
]
TRANSCRIPT_SPEC_PATH = ROOT / "songlab" / "projects" / PROJECT_ID / "transcript_spec.json"
PROJECT_SUMMARY_PATH = ROOT / "songlab" / "projects" / PROJECT_ID / "project_summary.md"
EXPORTS = ROOT / "exports"
MIDI_DIR = ROOT / "midi"

SR = 44_100
BPM = {bpm}
BEAT = 60.0 / BPM
TOTAL_BARS = {total_bars}
TAIL_SECONDS = {tail_seconds}

TRACK_IDS = {python_literal(track_ids)}
TRACK_PLAN = {python_literal(track_plan)}
TRACK_PLAN_BY_ID = {{track["id"]: track for track in TRACK_PLAN}}
SECTION_PLAN = {python_literal(section_plan)}
SECTION_PLAN_BY_ID = {{section["id"]: section for section in SECTION_PLAN}}

{runtime_support}


def _log_section(ctx: RenderContext, section: dict) -> None:
    ctx.notes.append(
        f"{{section['label']}} bars {{section['startBar'] + 1}}-{{section['startBar'] + section['bars']}}: {{section.get('summary', '')}}"
    )


def _render_track_baseline(ctx: RenderContext, track_id: str, start_bar: int, bars: int, *, note: str) -> None:
    ctx.notes.append(f"  - {{track_id}} @ bars {{start_bar + 1}}-{{start_bar + bars}} :: {{note}}")


def describe_plan() -> None:
    print(f"Generated renderer for {{PROJECT_NAME}}")
    print(f"BPM: {{BPM}} | Bars: {{TOTAL_BARS}}")
    print("Tracks:")
    for track in TRACK_PLAN:
        print(f"  - {{track['id']}} :: {{track['instrument']}} :: {{len(track['clips'])}} clip(s)")
    print("Sections:")
    for section in SECTION_PLAN:
        print(
            f"  - {{section['label']}} bars {{section['startBar'] + 1}}-{{section['startBar'] + section['bars']}} "
            f":: tracks {{', '.join(section.get('trackIds', [])) or 'none'}}"
        )

{role_helper_functions}

{section_functions}
def render_song() -> RenderContext:
    ctx = RenderContext()
'''
    for fn in render_order:
        generated += f"    render_{fn}(ctx)\n"
    generated += '''
    # Every lane is rendered; now make the sections sound the way the transcript
    # said they should (sidechain, reverb, delay, sweeps, saturation, width, layers).
    apply_song_techniques(ctx)
    return ctx


def main() -> int:
    describe_plan()
    ctx = render_song()
    outputs = write_outputs(ctx)
    sync_project_assets(outputs)
    print("")
    print("Section notes:")
    for line in ctx.notes:
        print(line)
    print("")
    print("Outputs:")
    for key, value in outputs.items():
        print(f"  - {key}: {value}")
    print("")
    print("TODO: refine the starter render bodies with project-specific sound design.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''
    path.write_text(
        generated,
        encoding="utf-8",
    )
    return path


def write_project_files(root: Path, project: dict[str, Any], project_id: str) -> dict[str, Path]:
    data_path = root / "data" / "projects" / f"{project_id}.neon.json"
    factory_path = root / "factory" / "projects" / f"{project_id}.neon.json"
    data_path.parent.mkdir(parents=True, exist_ok=True)
    factory_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(project, indent=2) + "\n"
    data_path.write_text(payload, encoding="utf-8")
    factory_path.write_text(payload, encoding="utf-8")
    return {"data": data_path, "factory": factory_path}


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Materialize a transcript spec into a Neon Studio project, with a musical plan from a model when one is available.")
    parser.add_argument("spec", help="path to a transcript_spec.json")
    parser.add_argument("--project-id", help="project id (default: the spec's projectId, else the title)")
    parser.add_argument("--prompt", help="the original brief (default: the spec's sourcePrompt)")
    parser.add_argument("--out-root", help="write data/projects, factory/projects and render_<id>.py under this root instead of printing the project")
    parser.add_argument("--spec-out", help="also write the spec with the plan applied to this path")
    parser.add_argument("--overwrite", action="store_true", help="replace an existing renderer under --out-root")
    if Assist is not None:
        from llm import add_ai_argument, assist_from_args
        add_ai_argument(parser)
    args = parser.parse_args(argv)

    spec_path = Path(args.spec)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    project_id = args.project_id or spec.get("projectId") or slugify(str(spec.get("titleHint") or spec_path.parent.name))
    prompt = args.prompt or spec.get("sourcePrompt")
    assist = assist_from_args(args) if Assist is not None else None
    started = time.time()
    project = build_project_materialization(spec, project_id, prompt=prompt, assist=assist)
    seconds = round(time.time() - started, 2)
    plan = project["materialization"]["plan"]
    layout = section_bar_layout(normalized_sections(apply_materialization_plan(spec, plan)))
    report: dict[str, Any] = {
        "projectId": project_id,
        "name": project["name"],
        "bpm": project["snapshot"]["bpm"],
        "keyCenter": project["keyCenter"],
        "swing": project["snapshot"]["swing"],
        "snap": project["snapshot"]["snap"],
        "description": project["description"],
        "tracks": [{"id": t["id"], "name": t["name"], "instrument": t["instrument"]} for t in project["snapshot"]["tracks"]],
        "sections": [{"id": s["id"], "type": s["type"], "label": s["label"], "bars": s["bars"]} for s in layout],
        "seconds": seconds,
        "ai": project["ai"],
        "materialization": project["materialization"],
    }
    if args.out_root:
        root = Path(args.out_root)
        written = write_project_files(root, project, project_id)
        renderer = ensure_project_renderer(root, project_id, project["name"], project, spec, prompt=prompt, overwrite=args.overwrite)
        report["written"] = {"data": str(written["data"]), "factory": str(written["factory"]), "renderer": str(renderer)}
    else:
        report["project"] = project
    if args.spec_out:
        Path(args.spec_out).write_text(json.dumps(apply_materialization_plan(spec, plan), indent=2) + "\n", encoding="utf-8")
        report["specOut"] = args.spec_out
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
