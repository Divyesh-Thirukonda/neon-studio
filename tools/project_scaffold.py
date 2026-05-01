#!/usr/bin/env python3
from __future__ import annotations

import json
import pprint
import re
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
    focus = "portable Neon Studio project scaffold"
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
            {"id": "section-01", "type": "intro", "label": "Intro", "summary": "Scaffold intro", "trackRoles": ["chords", "lead", "fx"], "plugins": [], "techniques": []},
            {"id": "section-02", "type": "verse", "label": "Verse", "summary": "Scaffold verse", "trackRoles": ["drums", "bass", "chords"], "plugins": [], "techniques": []},
            {"id": "section-03", "type": "build", "label": "Build", "summary": "Scaffold build", "trackRoles": ["drums", "fx", "lead"], "plugins": [], "techniques": ["automation"]},
            {"id": "section-04", "type": "drop", "label": "Drop", "summary": "Scaffold drop", "trackRoles": ["drums", "bass", "chords", "lead", "fx"], "plugins": [], "techniques": []},
            {"id": "section-05", "type": "outro", "label": "Outro", "summary": "Scaffold outro", "trackRoles": ["chords", "fx"], "plugins": [], "techniques": []},
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
    else:
        for fallback in DEFAULT_TRACK_IDS:
            if fallback not in chosen and len(chosen) < 6:
                chosen.append(fallback)
    return chosen


def make_track(blueprint: TrackBlueprint) -> dict[str, Any]:
    return {
        "id": blueprint.id,
        "name": blueprint.name,
        "kind": blueprint.kind,
        "instrument": blueprint.instrument,
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


def enrich_effects(track: dict[str, Any], section: dict[str, Any], global_plugins: list[str]) -> None:
    effect_names = {effect["name"] for effect in track["effects"]}
    section_plugins = section.get("plugins", [])
    for plugin in section_plugins[:2]:
        if plugin not in effect_names:
            track["effects"].append({"id": slugify(plugin), "name": plugin, "active": False, "amount": 0.3})
            effect_names.add(plugin)
    if "sidechain" in section.get("techniques", []) and "Sidechain" not in effect_names:
        track["effects"].append({"id": "duck", "name": "Sidechain", "active": False, "amount": 0.55})
    if "automation" in section.get("techniques", []) and track["id"] == "filter-auto" and "Filter Macro" not in effect_names:
        track["effects"].append({"id": "macro", "name": "Filter Macro", "active": True, "amount": 0.62})
    if global_plugins:
        for plugin in global_plugins[:1]:
            if plugin not in effect_names and len(track["effects"]) < 4:
                track["effects"].append({"id": slugify(plugin), "name": plugin, "active": False, "amount": 0.24})
                break


def make_recipe(section_layout: list[dict[str, Any]], all_track_ids: list[str], spec: dict[str, Any]) -> list[dict[str, Any]]:
    recipe = [
        {
            "id": "transcript-scaffold",
            "section": "Foundation",
            "label": "Transcript-derived scaffold",
            "detail": "Track layout, clips, and coverage were generated from the transcript before manual sound design and rendering.",
            "status": "mapped",
            "trackIds": all_track_ids,
        }
    ]
    for section in section_layout:
        tracks = section.get("scaffoldTrackIds", [])
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
    return recipe


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


def build_project_scaffold(spec: dict[str, Any], project_id: str, prompt: str | None = None) -> dict[str, Any]:
    project_name = infer_title_from_project(project_id, spec)
    chosen_track_ids = choose_track_ids(spec)
    tracks = [make_track(TRACK_BLUEPRINTS[track_id]) for track_id in chosen_track_ids]
    track_by_id = {track["id"]: track for track in tracks}

    section_layout = section_bar_layout(normalized_sections(spec))
    global_plugins = [item["name"] for item in spec.get("globalPlugins", [])]

    for section in section_layout:
        scaffold_track_ids = track_ids_for_section(section, chosen_track_ids)
        section["scaffoldTrackIds"] = scaffold_track_ids
        for track_id in scaffold_track_ids:
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
    recipe = make_recipe(section_layout, chosen_track_ids, spec)
    bpm = infer_bpm(spec, prompt)
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
        "description": infer_description(project_name, spec, prompt),
        "keyCenter": infer_key_center(spec),
        "snapshot": {
            "version": 3,
            "bpm": bpm,
            "swing": infer_swing(spec),
            "snap": infer_snap(spec),
            "loopEnabled": True,
            "loopStartBar": loop_start,
            "loopEndBar": loop_end,
            "tracks": tracks,
            "controls": make_controls(tracks),
            "notes": [],
            "selectedTrackId": tracks[0]["id"] if tracks else "",
            "selectedClipId": tracks[0]["clips"][0]["id"] if tracks and tracks[0]["clips"] else "",
            "activeView": "playlist",
            "patternIndex": 1,
            "arrangementMode": "song",
            "recipe": recipe,
        },
    }
    return project


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
    return f"""Renderer scaffold for {project_name}.

This file was scaffolded from a transcript-driven Songlab session.
It is not a finished renderer, but it already carries the project structure:
- transcript-derived section plan
- track layout from the scaffolded .neon.json
- section-specific production notes, plugin hints, and techniques

Edit this file when turning the scaffold into a real render implementation.

Primary inputs:
- data/projects/{project_id}.neon.json
- factory/projects/{project_id}.neon.json
- songlab/projects/{project_id}/transcript_spec.json
- songlab/projects/{project_id}/project_scaffold.md

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


def render_section_plan(project: dict[str, Any], spec: dict[str, Any]) -> list[dict[str, Any]]:
    tracks = {track["id"]: track for track in project["snapshot"]["tracks"]}
    recipe_by_section = {item["section"]: item for item in project["snapshot"].get("recipe", [])[1:]}
    sections = normalized_sections(spec)
    layout = section_bar_layout(sections)
    plan: list[dict[str, Any]] = []
    for section in layout:
        scaffold_track_ids = track_ids_for_section(section, list(tracks.keys()))
        plan.append(
            {
                "id": section["id"],
                "type": section["type"],
                "label": section["label"],
                "startBar": section["startBar"],
                "bars": section["bars"],
                "summary": section.get("summary"),
                "trackRoles": section.get("trackRoles", []),
                "trackIds": scaffold_track_ids,
                "plugins": section.get("plugins", []),
                "techniques": section.get("techniques", []),
                "recipeDetail": recipe_by_section.get(section["label"], {}).get("detail"),
                "starterDefaults": infer_section_starter_defaults(section, spec),
            }
        )
    return plan


ROLE_STUB_GUIDANCE: dict[str, str] = {
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
            "clapRoll": True,
            "hatSpacing": 0.5,
            "ride": False,
            "crashBars": [],
        }
    ride_enabled = "ride" in text or section["type"] == "second_drop"
    hat_spacing = 0.25 if any(keyword in text for keyword in ("fast hi-hat", "speed", "ride")) or section["type"] in {"drop", "second_drop"} else 0.5
    return {
        "kicks": [0.0, 1.45, 2.0, 3.05] if section["type"] in {"drop", "second_drop"} else [0.0, 1.5, 2.75],
        "snares": [1.0, 3.0] if section["type"] not in {"drop", "second_drop"} else [2.0],
        "hats": [round(step * hat_spacing, 2) for step in range(int(4 / hat_spacing))],
        "clapRoll": False,
        "hatSpacing": hat_spacing,
        "ride": ride_enabled,
        "crashBars": [0] if section["type"] in {"drop", "second_drop"} or "crash" in text else [],
    }


def infer_fx_profile(section: dict[str, Any]) -> dict[str, bool]:
    text = lower_join(section.get("summary"), " ".join(section.get("trackRoles", [])), " ".join(section.get("techniques", [])))
    return {
        "noiseBed": any(keyword in text for keyword in ("white noise", "noise", "breath")) or section["type"] in {"intro", "pre_intro"},
        "riser": any(keyword in text for keyword in ("riser", "uplifter", "rise")) or section["type"] == "build",
        "downlifter": any(keyword in text for keyword in ("downlifter", "down lifter", "reverse")) or section["type"] in {"build", "drop", "outro"},
        "crash": "crash" in text or section["type"] in {"drop", "second_drop"},
    }


def infer_section_starter_defaults(section: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    progression = choose_progression_template(spec, section)
    lead_motif_key = choose_lead_motif_key(section)
    text = lower_join(section.get("summary"), " ".join(section.get("trackRoles", [])), " ".join(section.get("techniques", [])))
    lead_soft = section["type"] in {"intro", "verse", "break", "outro"} and lead_motif_key != "dense"
    octave_shift = 12 if "up an octave" in text else 0
    if section["type"] == "second_drop":
        octave_shift = max(octave_shift, 12)
    defaults = {
        "progression": progression,
        "chordEvents": infer_chord_events(section),
        "bassEvents": infer_bass_events(section),
        "leadMotifKey": lead_motif_key,
        "leadMotif": LEAD_MOTIF_LIBRARY[lead_motif_key],
        "leadSoft": lead_soft,
        "leadOctaveShift": octave_shift,
        "drumPattern": infer_drum_pattern(section),
        "fxProfile": infer_fx_profile(section),
        "energy": 1.25 if section["type"] in {"drop", "second_drop"} else (1.05 if section["type"] == "build" else 0.85),
    }
    return defaults


def role_guidance(track_id: str) -> str:
    return ROLE_STUB_GUIDANCE.get(track_id, "Translate the transcript cues into a concrete part for this lane.")


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
                f'    """{section["label"]} / {track["name"]} role stub."""',
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
                lines.append("    # No overlapping clips were scaffolded for this lane yet.")
            lines.extend(
                [
                    "    # TODO: Refine or replace the starter render body for this lane.",
                    "    ctx.notes.append(",
                    f"        f\"    -> {track['name']}: {{track['instrument']}} | effects {{', '.join(track.get('effects', [])) or 'none'}}\"",
                    "    )",
                    "    _render_lane_starter(ctx, section, track)",
                    f"    _placeholder_track(ctx, {track_id!r}, section['startBar'], section['bars'], note=track['name'])",
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
        if section.get("trackIds"):
            lines.append("    # Tracks to touch in this section:")
            for track_id in section["trackIds"]:
                lines.append(f"    # - {track_id}: {track_names.get(track_id, track_id)}")
        lines.extend([
            "    _log_section(ctx, section)",
            "    # TODO: Replace the role helper stubs below with real synthesis / sample arrangement.",
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
import math
import wave

import numpy as np


TOTAL_SECONDS = TOTAL_BARS * 4 * BEAT + TAIL_SECONDS
N_SAMPLES = int(TOTAL_SECONDS * SR)
STEM_PREFIX = PROJECT_ID.replace("-", "_")
SCAFFOLD_STEM_PREFIX = f"{STEM_PREFIX}_scaffold"
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


def _schedule_note(buffer: np.ndarray, start_beat: float, duration_beats: float, midi_note: int, synth, *, gain: float, pan: float = 0.0, **kwargs) -> None:
    audio = synth(note_to_freq(midi_note), duration_beats * BEAT, **kwargs)
    add_mono(buffer, beat_to_seconds(start_beat), audio, gain=gain, pan=pan)


def _starter_chords(ctx: RenderContext, section: dict, track: dict) -> None:
    buffer = _track_buffer(ctx, track["id"])
    defaults = _section_defaults(section)
    for bar in range(section["startBar"], section["startBar"] + section["bars"]):
        chord = _progression_for_bar(section, bar)
        chord_events = defaults.get("chordEvents") or [{"beat": 0.0, "duration": 3.7}]
        for event in chord_events:
            onset = float(event["beat"])
            dur = float(event["duration"])
            stab = bool(event.get("stab", section["type"] in {"drop", "second_drop"}))
            bright = float(event.get("bright", 0.55 if section["type"] == "build" else (0.84 if stab else 0.30)))
            for idx, note in enumerate(chord["notes"]):
                _schedule_note(buffer, bar_beat(bar, onset), dur, int(note), synth_supersaw, gain=track.get("gain", 0.8) * (0.10 if stab else 0.06) * float(defaults.get("energy", 1.0)), pan=-0.45 + idx * 0.30, bright=bright, stab=stab)


def _starter_bass(ctx: RenderContext, section: dict, track: dict) -> None:
    buffer = _track_buffer(ctx, track["id"])
    defaults = _section_defaults(section)
    for bar in range(section["startBar"], section["startBar"] + section["bars"]):
        root = int(_progression_for_bar(section, bar)["root"])
        bass_events = defaults.get("bassEvents") or [{"beat": 0.0, "duration": 3.85}]
        for event in bass_events:
            onset = float(event["beat"])
            dur = float(event["duration"])
            gain = track.get("gain", 0.8) * (0.20 if section["type"] in {"drop", "second_drop"} else 0.10) * float(defaults.get("energy", 1.0))
            _schedule_note(buffer, bar_beat(bar, onset), dur, root + int(event.get("octaveShift", 0)), synth_bass, gain=gain, pan=track.get("pan", 0.0), grit=float(event.get("grit", 0.46)))


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
            _schedule_note(buffer, bar_beat(bar, onset), dur, note + transpose, synth_lead, gain=track.get("gain", 0.8) * (0.10 if not soft else 0.06) * float(defaults.get("energy", 1.0)), pan=-0.08 if (local_bar + int(onset * 10)) % 2 else 0.08, soft=soft)


def _starter_drums(ctx: RenderContext, section: dict, track: dict) -> None:
    buffer = _track_buffer(ctx, track["id"])
    defaults = _section_defaults(section)
    drum_pattern = defaults.get("drumPattern") or {}
    k = kick()
    s = snare(False)
    h = hat(False)
    for bar in range(section["startBar"], section["startBar"] + section["bars"]):
        kicks = drum_pattern.get("kicks") or [0.0, 1.5, 2.75]
        snares = drum_pattern.get("snares") or [1.0, 3.0]
        hats = drum_pattern.get("hats") or [step * 0.5 for step in range(8)]
        for beat in kicks:
            add_mono(buffer, beat_to_seconds(bar_beat(bar, float(beat))), k, gain=track.get("gain", 0.8) * 0.95 * float(defaults.get("energy", 1.0)), pan=track.get("pan", 0.0))
        for beat in snares:
            add_mono(buffer, beat_to_seconds(bar_beat(bar, float(beat))), s, gain=track.get("gain", 0.8) * 0.34 * float(defaults.get("energy", 1.0)))
        for beat in hats:
            beat_value = float(beat)
            add_mono(buffer, beat_to_seconds(bar_beat(bar, beat_value)), h, gain=0.14 + (0.05 if int(beat_value * 2) % 2 else 0.0), pan=0.22)


def _starter_clap_stack(ctx: RenderContext, section: dict, track: dict) -> None:
    buffer = _track_buffer(ctx, track["id"])
    defaults = _section_defaults(section)
    drum_pattern = defaults.get("drumPattern") or {}
    c = snare(True)
    for bar in range(section["startBar"], section["startBar"] + section["bars"]):
        beats = [step * 0.5 for step in range(8)] if drum_pattern.get("clapRoll") else (drum_pattern.get("snares") or [1.0, 3.0])
        for beat in beats:
            add_mono(buffer, beat_to_seconds(bar_beat(bar, float(beat))), c, gain=track.get("gain", 0.8) * (0.18 if drum_pattern.get("clapRoll") else 0.24) * float(defaults.get("energy", 1.0)), pan=0.18)


def _starter_hat_ride(ctx: RenderContext, section: dict, track: dict) -> None:
    buffer = _track_buffer(ctx, track["id"])
    defaults = _section_defaults(section)
    drum_pattern = defaults.get("drumPattern") or {}
    closed = hat(False)
    open_h = hat(True)
    for bar in range(section["startBar"], section["startBar"] + section["bars"]):
        spacing = float(drum_pattern.get("hatSpacing", 0.5))
        steps = int(4 / spacing)
        for step in range(steps):
            add_mono(buffer, beat_to_seconds(bar_beat(bar, step * spacing)), closed, gain=track.get("gain", 0.8) * 0.16, pan=-0.28 if step % 2 else 0.28)
        add_mono(buffer, beat_to_seconds(bar_beat(bar, 3.5)), open_h, gain=track.get("gain", 0.8) * 0.16, pan=-0.20)
        if drum_pattern.get("ride") and bar % 4 == 3:
            add_mono(buffer, beat_to_seconds(bar_beat(bar, 0.0)), open_h, gain=track.get("gain", 0.8) * 0.18, pan=0.18)
        if drum_pattern.get("crashBars") and (bar - section["startBar"]) in set(int(item) for item in drum_pattern["crashBars"]):
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


def _starter_filter_auto(ctx: RenderContext, section: dict, track: dict) -> None:
    buffer = _track_buffer(ctx, track["id"])
    add_mono(buffer, beat_to_seconds(bar_beat(section["startBar"])), riser(section["bars"] * 4 * BEAT, 180.0, 900.0), gain=track.get("gain", 0.8) * 0.12, pan=0.0)


def _starter_sample(ctx: RenderContext, section: dict, track: dict) -> None:
    buffer = _track_buffer(ctx, track["id"])
    add_mono(buffer, beat_to_seconds(bar_beat(section["startBar"])), synth_pluck(note_to_freq(72), 0.30 * BEAT), gain=track.get("gain", 0.8) * 0.08, pan=0.0)


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
    elif track["id"] in {"sample", "plucks", "vocals"}:
        _starter_sample(ctx, section, track)


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
    EXPORTS.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, str] = {}
    mix = stereo_buffer()
    for stem_id, audio in ctx.stems.items():
        stem_path = EXPORTS / f"{SCAFFOLD_STEM_PREFIX}_{stem_id}.wav"
        _write_wav(stem_path, audio)
        outputs[stem_id] = str(stem_path)
        mix += audio
    mix /= max(1, len(ctx.stems))
    mix_path = EXPORTS / f"{SCAFFOLD_STEM_PREFIX}_full_mix.wav"
    _write_wav(mix_path, mix)
    outputs["full_mix"] = str(mix_path)
    ctx.exports = outputs
    return outputs
'''


def ensure_renderer_stub(root: Path, project_id: str, project_name: str, project: dict[str, Any], spec: dict[str, Any], prompt: str | None = None, overwrite: bool = False) -> Path:
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
SCAFFOLD_SUMMARY_PATH = ROOT / "songlab" / "projects" / PROJECT_ID / "project_scaffold.md"
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


def _placeholder_track(ctx: RenderContext, track_id: str, start_bar: int, bars: int, *, note: str) -> None:
    ctx.notes.append(f"  - {{track_id}} @ bars {{start_bar + 1}}-{{start_bar + bars}} :: {{note}}")


def describe_plan() -> None:
    print(f"Renderer scaffold for {{PROJECT_NAME}}")
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
    return ctx


def main() -> int:
    describe_plan()
    ctx = render_song()
    outputs = write_outputs(ctx)
    print("")
    print("Section notes:")
    for line in ctx.notes:
        print(line)
    print("")
    print("Outputs:")
    for key, value in outputs.items():
        print(f"  - {key}: {value}")
    print("")
    print("TODO: refine the starter render bodies and then sync the final project metadata.")
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
