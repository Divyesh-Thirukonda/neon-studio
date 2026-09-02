#!/usr/bin/env python3
"""DAW-inspired agent for Neon Studio projects.

Applying a tactic is deterministic: every applier writes the same clip, lane,
effect, or note ids for the same project, so re-running is idempotent. What a
model may do (see docs/ai.md) is choose *which* tactics fit the project and the
feedback, in what order and why, label each track with a role, propose the
numbers each tactic uses within the schema the appliers already emit, and write
the summary. Every one of those answers is validated against the catalog, the
project's track ids, and the numeric ranges below; anything else is dropped and
the keyword retrieval / literal defaults run instead.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import llm  # noqa: E402


DEFAULT_QUERY = "improve the project with automation clips, randomizer humanize drums, groove velocity, riff variation, transition energy, macro controls, and mix staging"


@dataclass(frozen=True)
class DawFeature:
    id: str
    source: str
    title: str
    summary: str
    intents: tuple[str, ...]
    roles: tuple[str, ...]
    actions: tuple[str, ...]
    default_priority: float


CATALOG: tuple[DawFeature, ...] = (
    DawFeature(
        id="fl-automation-clips",
        source="FL Studio automation clips",
        title="Draw tension with editable automation clips",
        summary="Add visible filter or macro ramps that shape builds, drops, and transitions.",
        intents=("automation", "clip", "filter", "sweep", "riser", "cutoff", "tension", "build"),
        roles=("lead", "bass", "fx", "chords"),
        actions=("automation_lane", "recipe"),
        default_priority=9.0,
    ),
    DawFeature(
        id="fl-randomizer-groove",
        source="FL Studio piano-roll randomizer and graph editor",
        title="Humanize drums with controlled randomizer-style groove",
        summary="Add ghost-note/fill clips, velocity-humanize effect intent, and a minimum swing floor.",
        intents=("randomizer", "humanize", "humanization", "groove", "drums", "hats", "velocity", "swing", "ghost"),
        roles=("drums", "hat", "percussion"),
        actions=("clip", "effect", "swing", "recipe"),
        default_priority=8.0,
    ),
    DawFeature(
        id="fl-riff-machine-variation",
        source="FL Studio Riff Machine",
        title="Generate riff variation cues",
        summary="Seed a short motif variation in the piano lane and a matching pattern clip.",
        intents=("riff", "melody", "lead", "motif", "variation", "piano", "notes", "hook"),
        roles=("lead", "melody", "chords", "synth"),
        actions=("notes", "clip", "recipe"),
        default_priority=7.0,
    ),
    DawFeature(
        id="fl-gross-beat-transition",
        source="FL Studio Gross Beat-style gating",
        title="Add gated/tape-stop transition energy",
        summary="Mark the transition lane with a gated tail effect and pre-drop clip cue.",
        intents=("gross", "beat", "gate", "gated", "tape", "stop", "stutter", "transition", "drop"),
        roles=("fx", "lead", "vocal", "drums"),
        actions=("effect", "clip", "recipe"),
        default_priority=6.0,
    ),
    DawFeature(
        id="fl-patcher-macro-chain",
        source="FL Studio Patcher and control surface macros",
        title="Create macro-chain control intent",
        summary="Add macro effects and a macro lane so later passes can bind multiple parameters.",
        intents=("patcher", "macro", "control", "surface", "routing", "chain", "modulation"),
        roles=("selected", "lead", "bass", "fx"),
        actions=("effect", "automation_lane", "recipe"),
        default_priority=5.5,
    ),
    DawFeature(
        id="ableton-capture-midi",
        source="Ableton Live Capture MIDI-style recall",
        title="Capture loop idea checkpoints",
        summary="Add a recipe checkpoint that preserves the current loop as an agent follow-up target.",
        intents=("capture", "midi", "idea", "loop", "checkpoint", "recall", "improv"),
        roles=("lead", "chords", "bass"),
        actions=("recipe",),
        default_priority=3.5,
    ),
    DawFeature(
        id="logic-drummer-fill",
        source="Logic Pro Drummer-style arrangement fills",
        title="Place section-aware drum fill cues",
        summary="Add short fill clips before section changes and mark them as variation targets.",
        intents=("drummer", "fill", "fills", "section", "arrangement", "pre", "drop"),
        roles=("drums", "percussion"),
        actions=("clip", "recipe"),
        default_priority=4.5,
    ),
    DawFeature(
        id="bitwig-modulator-lane",
        source="Bitwig-style modulators",
        title="Add modulation-lane movement",
        summary="Create a small pan or width modulation lane for motion without changing notes.",
        intents=("modulator", "modulation", "motion", "width", "pan", "movement", "lfo"),
        roles=("lead", "chords", "fx"),
        actions=("automation_lane", "recipe"),
        default_priority=4.0,
    ),
)


RETRIEVAL_CASES: tuple[tuple[str, str], ...] = (
    ("automation clip filter sweep riser", "fl-automation-clips"),
    ("randomize drums humanize groove velocity", "fl-randomizer-groove"),
    ("riff machine melody motif variation", "fl-riff-machine-variation"),
    ("gross beat gate tape stop transition", "fl-gross-beat-transition"),
    ("patcher macro routing control surface", "fl-patcher-macro-chain"),
    ("capture midi idea loop checkpoint", "ableton-capture-midi"),
    ("drummer fill before section drop", "logic-drummer-fill"),
    ("modulator width pan motion lfo", "bitwig-modulator-lane"),
)


TOKEN_RE = re.compile(r"[a-z0-9]+")
ROLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "selected": (),
    "drums": ("drum", "kick", "snare", "clap", "hat", "ride", "perc"),
    "hat": ("hat", "hihat", "hi-hat", "ride"),
    "percussion": ("perc", "drum", "hat", "clap", "snare"),
    "bass": ("bass", "sub", "808"),
    "lead": ("lead", "melody", "hook", "riff", "pluck", "synth"),
    "melody": ("lead", "melody", "hook", "riff", "vocal"),
    "chords": ("chord", "pad", "keys", "supersaw"),
    "synth": ("synth", "lead", "pluck", "pad"),
    "fx": ("fx", "effect", "riser", "downlifter", "sweep", "noise", "transition"),
    "vocal": ("vocal", "voice", "vox", "chop"),
}


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def feature_text(feature: DawFeature) -> str:
    return " ".join(
        [
            feature.id.replace("-", " "),
            feature.source,
            feature.title,
            feature.summary,
            " ".join(feature.intents),
            " ".join(feature.roles),
            " ".join(feature.actions),
        ]
    ).lower()


FEATURE_TOKEN_SETS = {feature.id: set(tokenize(feature_text(feature))) for feature in CATALOG}


def safe_id(text: str, fallback: str = "agent") -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", text).strip("-_").lower()
    return (cleaned or fallback)[:72]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def deep_copy_jsonish(value: Any) -> Any:
    return copy.deepcopy(value)


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or "snapshot" not in data:
        raise ValueError(f"{path} is not a Neon Studio project JSON")
    return data


def read_feedback(path: Path | None, text: str | None) -> Any:
    if path:
        raw = path.read_text(encoding="utf-8")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
    if text:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return None


def feedback_query(feedback: Any) -> str:
    if feedback is None:
        return ""
    fragments: list[str] = []
    if isinstance(feedback, str):
        fragments.append(feedback)
    elif isinstance(feedback, dict):
        verdict = feedback.get("verdict") if isinstance(feedback.get("verdict"), dict) else {}
        fragments.extend(str(verdict.get(key, "")) for key in ("answer", "summary"))
        fragments.extend(str(item) for item in feedback.get("nextActions", []) or [])
        for issue in feedback.get("issues", []) or []:
            if isinstance(issue, dict):
                fragments.extend(str(issue.get(key, "")) for key in ("area", "detail", "severity"))
        project_checks = feedback.get("projectChecks") if isinstance(feedback.get("projectChecks"), dict) else {}
        fragments.extend(str(project_checks.get(key, "")) for key in ("audibleTrackCount", "recipeCount", "sectionCount"))
    else:
        fragments.append(str(feedback))

    raw = " ".join(fragment for fragment in fragments if fragment).lower()
    expansions = ["sound check feedback"]
    keyword_expansions = (
        (("clip", "clipping", "limiter", "hot", "flattening", "transient"), "mix staging macro duck soft clip"),
        (("kick", "bass", "sub", "low", "mono", "phase"), "sidechain bass macro duck mixer routing"),
        (("harsh", "bright", "brittle", "top", "sibilance"), "macro eq filter automation"),
        (("static", "flat", "energy", "build", "drop", "transition"), "automation clips gross beat transition riser"),
        (("drum", "groove", "swing", "human", "velocity"), "randomizer groove velocity humanize"),
        (("hook", "lead", "melody", "riff", "motif"), "riff machine variation melody"),
        (("wide", "stereo", "width", "movement", "pan"), "modulator width pan motion"),
        (("empty", "missing", "sparse", "arrangement", "section"), "drummer fill capture midi checkpoint"),
    )
    for keywords, expansion in keyword_expansions:
        if any(keyword in raw for keyword in keywords):
            expansions.append(expansion)
    if raw:
        expansions.append(raw)
    return " ".join(expansions)


def effective_query(base_query: str | None, feedback_path: str | None, feedback_text: str | None) -> str | None:
    feedback_path_obj = Path(feedback_path).expanduser() if feedback_path else None
    feedback = read_feedback(feedback_path_obj, feedback_text)
    feedback_part = feedback_query(feedback)
    if base_query and feedback_part:
        return f"{base_query} {feedback_part}"
    return base_query or feedback_part or None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def resolve_project_path(root: Path, project_id: str | None, project_path: str | None) -> Path:
    if project_path:
        path = Path(project_path).expanduser()
        return path if path.is_absolute() else (root / path)
    if not project_id:
        raise ValueError("Pass --project-id or --project")
    safe = safe_id(project_id)
    candidates = [
        root / "data" / "projects" / f"{safe}.neon.json",
        root / "factory" / "projects" / f"{safe}.neon.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Could not find project {safe} under data/projects or factory/projects")


def snapshot(project: dict[str, Any]) -> dict[str, Any]:
    return project.setdefault("snapshot", {})


def project_tracks(project: dict[str, Any]) -> list[dict[str, Any]]:
    tracks = snapshot(project).setdefault("tracks", [])
    return tracks if isinstance(tracks, list) else []


def track_text(track: dict[str, Any]) -> str:
    effects = " ".join(str(effect.get("name", "")) for effect in track.get("effects", []) if isinstance(effect, dict))
    clips = " ".join(str(clip.get("name", "")) for clip in track.get("clips", []) if isinstance(clip, dict))
    return " ".join(
        str(track.get(key, ""))
        for key in ("id", "name", "kind", "instrument", "color")
    ) + f" {effects} {clips}"


def infer_roles(project: dict[str, Any]) -> set[str]:
    roles: set[str] = set()
    for track in project_tracks(project):
        lowered = track_text(track).lower()
        for role, keywords in ROLE_KEYWORDS.items():
            if role == "selected":
                continue
            if any(keyword in lowered for keyword in keywords):
                roles.add(role)
    if snapshot(project).get("selectedTrackId"):
        roles.add("selected")
    return roles


def total_bars(project: dict[str, Any]) -> float:
    snap = snapshot(project)
    clip_end = 0.0
    for track in project_tracks(project):
        for clip in track.get("clips", []) or []:
            if not isinstance(clip, dict):
                continue
            clip_end = max(clip_end, float(clip.get("startBar", 0) or 0) + float(clip.get("bars", 0) or 0))
    lane_end = 0.0
    for lane in snap.get("automationLanes", []) or []:
        for point in lane.get("points", []) or []:
            lane_end = max(lane_end, float(point.get("bar", 0) or 0))
    loop_end = float(snap.get("loopEndBar", 0) or 0)
    return max(16.0, clip_end, lane_end + 1.0, loop_end)


def project_metrics(project: dict[str, Any]) -> dict[str, int | float]:
    snap = snapshot(project)
    tracks = project_tracks(project)
    clips = [clip for track in tracks for clip in (track.get("clips", []) or []) if isinstance(clip, dict)]
    effects = [effect for track in tracks for effect in (track.get("effects", []) or []) if isinstance(effect, dict)]
    recipe = snap.get("recipe", []) or []
    automation = snap.get("automationLanes", []) or []
    notes = snap.get("notes", []) or []
    return {
        "trackCount": len(tracks),
        "clipCount": len(clips),
        "effectCount": len(effects),
        "automationLaneCount": len(automation),
        "recipeCount": len(recipe),
        "agentRecipeCount": sum(1 for item in recipe if isinstance(item, dict) and str(item.get("id", "")).startswith("agent-")),
        "noteCount": len(notes),
        "bars": total_bars(project),
    }


def project_context_text(project: dict[str, Any] | None) -> str:
    if not project:
        return ""
    snap = snapshot(project)
    pieces = [
        str(project.get("id", "")),
        str(project.get("name", "")),
        str(project.get("description", "")),
        str(project.get("keyCenter", "")),
        str(snap.get("activeView", "")),
        str(snap.get("arrangementMode", "")),
    ]
    pieces.extend(track_text(track) for track in project_tracks(project))
    for item in snap.get("recipe", []) or []:
        if isinstance(item, dict):
            pieces.append(" ".join(str(item.get(key, "")) for key in ("section", "label", "detail", "status")))
    return " ".join(pieces)


def retrieve_features(query: str | None, project: dict[str, Any] | None = None, limit: int = 5) -> list[dict[str, Any]]:
    normalized_query = (query or DEFAULT_QUERY).strip() or DEFAULT_QUERY
    query_tokens = tokenize(normalized_query)
    query_token_set = set(query_tokens)
    context_tokens = set(tokenize(project_context_text(project)))
    roles = infer_roles(project) if project else set()
    scored: list[tuple[float, DawFeature, list[str]]] = []

    for feature in CATALOG:
        feature_tokens = FEATURE_TOKEN_SETS[feature.id]
        matched_query = sorted(query_token_set & feature_tokens)
        matched_context = sorted((context_tokens & feature_tokens) - set(matched_query))
        role_matches = sorted(set(feature.roles) & roles)
        score = feature.default_priority * 0.2
        score += len(matched_query) * 4.0
        score += min(4, len(matched_context)) * 0.6
        score += len(role_matches) * 1.4
        for intent in feature.intents:
            if intent in normalized_query.lower():
                score += 1.5
        if project:
            metrics = project_metrics(project)
            if "automation_lane" in feature.actions and metrics["automationLaneCount"] == 0:
                score += 1.0
            if "clip" in feature.actions and metrics["clipCount"] < max(1, metrics["trackCount"]):
                score += 0.8
            if "notes" in feature.actions and metrics["noteCount"] == 0:
                score += 0.8
        reasons = matched_query + [f"role:{role}" for role in role_matches]
        if not reasons:
            reasons = [f"default:{feature.default_priority:g}"]
        scored.append((score, feature, reasons))

    scored.sort(key=lambda item: (-item[0], item[1].id))
    return [
        {
            "id": feature.id,
            "source": feature.source,
            "title": feature.title,
            "summary": feature.summary,
            "score": round(score, 3),
            "reasons": reasons,
            "actions": list(feature.actions),
        }
        for score, feature, reasons in scored[:limit]
    ]


def default_control(track: dict[str, Any]) -> dict[str, Any]:
    return {
        "gain": float(track.get("gain", 0.82) or 0.82),
        "pan": float(track.get("pan", 0) or 0),
        "mute": False,
        "solo": False,
        "arm": False,
        "sendA": 0.15,
        "sendB": 0.08,
    }


def ensure_controls(project: dict[str, Any]) -> None:
    snap = snapshot(project)
    controls = snap.setdefault("controls", {})
    if not isinstance(controls, dict):
        controls = {}
        snap["controls"] = controls
    for track in project_tracks(project):
        track_id = str(track.get("id", ""))
        if track_id:
            controls.setdefault(track_id, default_control(track))


def selected_track(project: dict[str, Any]) -> dict[str, Any] | None:
    selected_id = str(snapshot(project).get("selectedTrackId", "") or "")
    return next((track for track in project_tracks(project) if track.get("id") == selected_id), None)


def find_track(project: dict[str, Any], roles: tuple[str, ...]) -> dict[str, Any] | None:
    tracks = project_tracks(project)
    if not tracks:
        return None
    for role in roles:
        if role == "selected":
            track = selected_track(project)
            if track:
                return track
            continue
        keywords = ROLE_KEYWORDS.get(role, (role,))
        for track in tracks:
            lowered = track_text(track).lower()
            if any(keyword in lowered for keyword in keywords):
                return track
    return tracks[0]


def track_by_id(project: dict[str, Any], track_id: Any) -> dict[str, Any] | None:
    wanted = str(track_id or "")
    if not wanted:
        return None
    return next((track for track in project_tracks(project) if str(track.get("id", "")) == wanted), None)


def pick_track(
    project: dict[str, Any],
    roles: tuple[str, ...],
    params: dict[str, Any] | None = None,
    role_map: dict[str, list[str]] | None = None,
) -> dict[str, Any] | None:
    """The track a tactic edits: the caller's explicit choice, else a track the
    model labelled with one of the wanted roles, else the keyword scan."""
    explicit = track_by_id(project, (params or {}).get("trackId"))
    if explicit is not None:
        return explicit
    if role_map:
        for role in roles:
            if role == "selected":
                selected = selected_track(project)
                if selected is not None:
                    return selected
                continue
            for track in project_tracks(project):
                if role in (role_map.get(str(track.get("id", ""))) or []):
                    return track
    return find_track(project, roles)


# ---------------------------------------------------------------------------
# Tactic parameters. Each applier has literal defaults; a caller (or the model)
# may pass a dict shaped like the entry below, and `validate_params` clamps it
# to the ranges the appliers already use. Anything unknown is dropped.
# ---------------------------------------------------------------------------

CURVES = ("linear", "ease-in", "ease-out", "sine")
LANE_PARAMETERS = ("filter", "macro", "width", "pan", "gain", "cutoff", "resonance", "send")
MODULATOR_PARAMETERS = ("width", "pan")
MIDI_NOTE_RANGE = (36, 96)
MAX_POINTS = 8
MAX_NOTES = 16

PARAM_SCHEMA: dict[str, dict[str, Any]] = {
    "fl-automation-clips": {
        "trackId": "a track id from the project",
        "parameter": "one of " + "|".join(LANE_PARAMETERS),
        "points": [{"bar": "bar inside the song", "value": "0-1", "curve": "one of " + "|".join(CURVES)}],
    },
    "fl-randomizer-groove": {"trackId": "a drum/percussion track id", "humanizeAmount": "0-1", "swingFloor": "0-30", "ghostBars": "1-8"},
    "fl-riff-machine-variation": {
        "trackId": "a melodic track id",
        "startBar": "bar inside the song",
        "notes": [{"beat": "0-16, beats after startBar", "note": "MIDI 36-96", "duration": "0.1-4 beats", "velocity": "0-1"}],
    },
    "fl-gross-beat-transition": {"trackId": "a track id", "amount": "0-1", "bars": "1-4", "endBar": "bar the transition lands on"},
    "fl-patcher-macro-chain": {
        "trackId": "a track id",
        "eqAmount": "0-1",
        "duckAmount": "0-1",
        "points": [{"bar": "bar inside the song", "value": "0-1", "curve": "one of " + "|".join(CURVES)}],
    },
    "ableton-capture-midi": {"trackId": "a track id", "startBar": "bar inside the song", "endBar": "bar inside the song, after startBar"},
    "logic-drummer-fill": {"trackId": "a drum track id", "bars": "1-2", "beforeBar": "the section boundary the fill leads into"},
    "bitwig-modulator-lane": {
        "trackId": "a track id",
        "parameter": "one of " + "|".join(MODULATOR_PARAMETERS),
        "points": [{"bar": "bar inside the song", "value": "0-1", "curve": "one of " + "|".join(CURVES)}],
    },
}


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _clamped(value: Any, low: float, high: float) -> float | None:
    number = _number(value)
    if number is None:
        return None
    return max(low, min(high, number))


def clean_points(points: Any, bars: float, notes: list[str], label: str) -> list[dict[str, Any]]:
    """Automation points inside the song, values 0-1, known curves, sorted by bar.
    Fewer than two usable points means the applier keeps its own shape."""
    if not isinstance(points, list):
        if points is not None:
            notes.append(f"{label}: points must be a list")
        return []
    cleaned: list[dict[str, Any]] = []
    for point in points[:MAX_POINTS]:
        if not isinstance(point, dict):
            continue
        bar = _clamped(point.get("bar"), 0.0, bars)
        value = _clamped(point.get("value"), 0.0, 1.0)
        if bar is None or value is None:
            notes.append(f"{label}: dropped a point without a numeric bar and value")
            continue
        curve = str(point.get("curve") or "linear").strip().lower()
        if curve not in CURVES:
            curve = "linear"
        cleaned.append({"bar": round(bar, 2), "value": round(value, 3), "curve": curve})
    cleaned.sort(key=lambda item: item["bar"])
    if len(cleaned) < 2:
        if cleaned:
            notes.append(f"{label}: fewer than two usable points, keeping the default shape")
        return []
    return cleaned


def validate_params(feature_id: str, params: Any, project: dict[str, Any] | None) -> tuple[dict[str, Any], list[str]]:
    """Clamp a tactic's parameters to the appliers' own ranges. Returns
    (clean params, notes about what was dropped or clamped)."""
    notes: list[str] = []
    if feature_id not in PARAM_SCHEMA:
        return {}, [f"unknown tactic {feature_id}"]
    if not isinstance(params, dict):
        if params not in (None, {}, []):
            notes.append(f"{feature_id}: params must be an object")
        return {}, notes
    bars = total_bars(project) if project else 64.0
    clean: dict[str, Any] = {}
    track_id = params.get("trackId")
    if track_id is not None:
        if project is not None and track_by_id(project, track_id) is not None:
            clean["trackId"] = str(track_id)
        else:
            notes.append(f"{feature_id}: track {track_id!r} is not in the project")

    def take(key: str, low: float, high: float, integer: bool = False) -> None:
        if key not in params:
            return
        value = _clamped(params.get(key), low, high)
        if value is None:
            notes.append(f"{feature_id}: {key} is not a number")
            return
        clean[key] = int(round(value)) if integer else round(value, 3)

    if feature_id == "fl-automation-clips":
        parameter = str(params.get("parameter") or "").strip().lower()
        if parameter:
            if parameter in LANE_PARAMETERS:
                clean["parameter"] = parameter
            else:
                notes.append(f"{feature_id}: parameter {parameter!r} is not one of {', '.join(LANE_PARAMETERS)}")
        points = clean_points(params.get("points"), bars, notes, feature_id)
        if points:
            clean["points"] = points
    elif feature_id == "fl-randomizer-groove":
        take("humanizeAmount", 0.0, 1.0)
        take("swingFloor", 0.0, 30.0, integer=True)
        take("ghostBars", 1.0, 8.0, integer=True)
    elif feature_id == "fl-riff-machine-variation":
        take("startBar", 0.0, max(0.0, bars - 1.0))
        raw_notes = params.get("notes")
        if isinstance(raw_notes, list):
            kept: list[dict[str, Any]] = []
            for note in raw_notes[:MAX_NOTES]:
                if not isinstance(note, dict):
                    continue
                beat = _clamped(note.get("beat"), 0.0, 16.0)
                pitch = _clamped(note.get("note"), MIDI_NOTE_RANGE[0], MIDI_NOTE_RANGE[1])
                if beat is None or pitch is None:
                    notes.append(f"{feature_id}: dropped a note without a numeric beat and MIDI note")
                    continue
                duration = _clamped(note.get("duration"), 0.1, 4.0)
                velocity = _clamped(note.get("velocity"), 0.0, 1.0)
                kept.append({
                    "beat": round(beat, 2),
                    "note": int(round(pitch)),
                    "duration": round(duration if duration is not None else 0.5, 2),
                    "velocity": round(velocity if velocity is not None else 0.75, 2),
                })
            if kept:
                kept.sort(key=lambda item: item["beat"])
                clean["notes"] = kept
            else:
                notes.append(f"{feature_id}: no usable notes, keeping the default motif")
        elif raw_notes is not None:
            notes.append(f"{feature_id}: notes must be a list")
    elif feature_id == "fl-gross-beat-transition":
        take("amount", 0.0, 1.0)
        take("bars", 1.0, 4.0, integer=True)
        take("endBar", 1.0, bars)
    elif feature_id == "fl-patcher-macro-chain":
        take("eqAmount", 0.0, 1.0)
        take("duckAmount", 0.0, 1.0)
        points = clean_points(params.get("points"), bars, notes, feature_id)
        if points:
            clean["points"] = points
    elif feature_id == "ableton-capture-midi":
        take("startBar", 0.0, max(0.0, bars - 1.0))
        take("endBar", 1.0, bars)
        if "startBar" in clean and "endBar" in clean and clean["endBar"] <= clean["startBar"]:
            notes.append(f"{feature_id}: endBar must come after startBar, keeping the loop window")
            clean.pop("startBar")
            clean.pop("endBar")
    elif feature_id == "logic-drummer-fill":
        take("bars", 1.0, 2.0, integer=True)
        take("beforeBar", 1.0, bars)
    elif feature_id == "bitwig-modulator-lane":
        parameter = str(params.get("parameter") or "").strip().lower()
        if parameter:
            if parameter in MODULATOR_PARAMETERS:
                clean["parameter"] = parameter
            else:
                notes.append(f"{feature_id}: parameter {parameter!r} is not one of {', '.join(MODULATOR_PARAMETERS)}")
        points = clean_points(params.get("points"), bars, notes, feature_id)
        if points:
            clean["points"] = points
    for key in params:
        if key not in clean and key not in PARAM_SCHEMA[feature_id] and key != "trackId":
            notes.append(f"{feature_id}: ignored unknown parameter {key!r}")
    return clean, notes


def ensure_effect(track: dict[str, Any], effect_id: str, name: str, amount: float) -> tuple[bool, str]:
    effects = track.setdefault("effects", [])
    for effect in effects:
        if isinstance(effect, dict) and effect.get("id") == effect_id:
            effect["active"] = True
            effect["amount"] = max(float(effect.get("amount", amount) or amount), amount)
            return False, f"refreshed effect {name} on {track.get('name', track.get('id'))}"
    effects.append({"id": effect_id, "name": name, "active": True, "amount": round(max(0, min(1, amount)), 2)})
    return True, f"added effect {name} to {track.get('name', track.get('id'))}"


def ensure_clip(track: dict[str, Any], clip: dict[str, Any]) -> tuple[bool, str]:
    clips = track.setdefault("clips", [])
    for existing in clips:
        if isinstance(existing, dict) and existing.get("id") == clip["id"]:
            return False, f"kept clip {clip['name']} on {track.get('name', track.get('id'))}"
    clips.append(clip)
    return True, f"added clip {clip['name']} to {track.get('name', track.get('id'))}"


def ensure_lane(project: dict[str, Any], lane: dict[str, Any]) -> tuple[bool, str]:
    lanes = snapshot(project).setdefault("automationLanes", [])
    for existing in lanes:
        if isinstance(existing, dict) and existing.get("id") == lane["id"]:
            existing.update({key: value for key, value in lane.items() if key != "id"})
            return False, f"refreshed automation lane {lane['label']}"
    lanes.append(lane)
    return True, f"added automation lane {lane['label']}"


def ensure_recipe(project: dict[str, Any], item: dict[str, Any]) -> tuple[bool, str]:
    recipe = snapshot(project).setdefault("recipe", [])
    for existing in recipe:
        if isinstance(existing, dict) and existing.get("id") == item["id"]:
            existing.update(item)
            return False, f"refreshed recipe item {item['label']}"
    recipe.append(item)
    return True, f"added recipe item {item['label']}"


def ensure_notes(project: dict[str, Any], notes: list[dict[str, Any]]) -> tuple[bool, str]:
    existing_notes = snapshot(project).setdefault("notes", [])
    existing_ids = {note.get("id") for note in existing_notes if isinstance(note, dict)}
    inserted = [note for note in notes if note["id"] not in existing_ids]
    existing_notes.extend(inserted)
    if inserted:
        return True, f"added {len(inserted)} piano-roll motif notes"
    return False, "kept existing agent motif notes"


def loop_window(project: dict[str, Any], minimum_bars: float = 4.0) -> tuple[float, float]:
    snap = snapshot(project)
    bars = total_bars(project)
    start = float(snap.get("loopStartBar", 0) or 0)
    end = float(snap.get("loopEndBar", 0) or 0)
    if end <= start:
        end = min(bars, start + max(minimum_bars, 8.0))
    if start >= bars:
        start = max(0.0, bars - max(minimum_bars, 8.0))
        end = bars
    return max(0.0, start), max(start + minimum_bars, min(bars, end))


def key_root_midi(project: dict[str, Any]) -> int:
    key = str(project.get("keyCenter", "") or "").lower()
    roots = {
        "c": 60,
        "c#": 61,
        "db": 61,
        "d": 62,
        "d#": 63,
        "eb": 63,
        "e": 64,
        "f": 65,
        "f#": 66,
        "gb": 66,
        "g": 67,
        "g#": 68,
        "ab": 68,
        "a": 69,
        "a#": 70,
        "bb": 70,
        "b": 71,
    }
    match = re.match(r"([a-g](?:#|b)?)", key)
    return roots.get(match.group(1), 64) if match else 64


def agent_recipe_item(feature: DawFeature, detail: str, track_ids: list[str]) -> dict[str, Any]:
    return {
        "id": f"agent-{feature.id}",
        "section": "DAW Agent",
        "label": feature.title,
        "detail": f"{feature.source}: {detail}",
        "status": "implemented",
        "trackIds": track_ids,
    }


def apply_automation_clips(project: dict[str, Any], feature: DawFeature, params: dict[str, Any] | None = None, role_map: dict[str, list[str]] | None = None) -> list[str]:
    params = params or {}
    track = pick_track(project, ("lead", "bass", "fx", "chords"), params, role_map)
    if not track:
        return ["no track available for automation clip"]
    start, end = loop_window(project)
    mid = start + (end - start) * 0.62
    track_id = str(track.get("id", "track"))
    parameter = str(params.get("parameter") or "filter")
    points = params.get("points") or [
        {"bar": round(start, 2), "value": 0.16, "curve": "ease-in"},
        {"bar": round(mid, 2), "value": 0.48, "curve": "ease-in"},
        {"bar": round(end, 2), "value": 0.9, "curve": "linear"},
    ]
    lane = {
        "id": f"agent-filter-rise-{safe_id(track_id)}",
        "trackId": track_id,
        "parameter": parameter,
        "label": f"Agent {parameter} rise",
        "color": track.get("color", "#f8d66d"),
        "enabled": True,
        "curve": "ease-in",
        "points": [dict(point) for point in points],
    }
    changed, lane_message = ensure_lane(project, lane)
    first_bar, last_bar = points[0]["bar"], points[-1]["bar"]
    detail = f"visible {parameter}-ramp lane from bar {first_bar:g} to {last_bar:g} for build/drop tension"
    _, recipe_message = ensure_recipe(project, agent_recipe_item(feature, detail, [track_id]))
    return [lane_message, recipe_message, "automation applied" if changed else "automation already present"]


def apply_randomizer_groove(project: dict[str, Any], feature: DawFeature, params: dict[str, Any] | None = None, role_map: dict[str, list[str]] | None = None) -> list[str]:
    params = params or {}
    track = pick_track(project, ("drums", "hat", "percussion"), params, role_map)
    if not track:
        return ["no drum or percussion track available for groove humanization"]
    snap = snapshot(project)
    start, _ = loop_window(project)
    start = max(0.0, start - (start % 4))
    track_id = str(track.get("id", "drums"))
    clip = {
        "id": f"agent-groove-ghosts-{safe_id(track_id)}",
        "name": "Agent groove ghosts",
        "startBar": round(start, 2),
        "bars": int(params.get("ghostBars") or 4),
        "lane": track_id,
        "color": track.get("color", "#ff8d5c"),
        "type": "pattern",
    }
    _, clip_message = ensure_clip(track, clip)
    _, effect_message = ensure_effect(track, "agent-humanize", "Humanize Velocity", float(params.get("humanizeAmount", 0.42)))
    swing_floor = int(params.get("swingFloor", 8))
    current_swing = float(snap.get("swing", 0) or 0)
    if current_swing < swing_floor:
        snap["swing"] = swing_floor
        swing_message = f"raised swing floor to {swing_floor}"
    else:
        swing_message = f"kept existing swing {current_swing:g}"
    detail = "randomizer-style ghost notes and velocity intent without destructive drum rewrites"
    _, recipe_message = ensure_recipe(project, agent_recipe_item(feature, detail, [track_id]))
    return [clip_message, effect_message, swing_message, recipe_message]


def apply_riff_variation(project: dict[str, Any], feature: DawFeature, params: dict[str, Any] | None = None, role_map: dict[str, list[str]] | None = None) -> list[str]:
    params = params or {}
    track = pick_track(project, ("lead", "melody", "chords", "synth"), params, role_map)
    if not track:
        return ["no melodic track available for riff variation"]
    start, _ = loop_window(project)
    if "startBar" in params:
        start = float(params["startBar"])
    track_id = str(track.get("id", "lead"))
    clip = {
        "id": f"agent-riff-variation-{safe_id(track_id)}",
        "name": "Agent riff variation",
        "startBar": round(start, 2),
        "bars": 4,
        "lane": track_id,
        "color": track.get("color", "#60c8f8"),
        "type": "pattern",
    }
    _, clip_message = ensure_clip(track, clip)
    root = key_root_midi(project)
    motif = [
        {"beat": 0.0, "note": root + 12, "velocity": 0.74, "duration": 0.7},
        {"beat": 0.5, "note": root + 15, "velocity": 0.68, "duration": 0.45},
        {"beat": 1.25, "note": root + 19, "velocity": 0.82, "duration": 0.45},
        {"beat": 2.0, "note": root + 22, "velocity": 0.76, "duration": 0.7},
        {"beat": 2.75, "note": root + 19, "velocity": 0.7, "duration": 0.45},
        {"beat": 3.5, "note": root + 15, "velocity": 0.66, "duration": 0.45},
    ]
    if params.get("notes"):
        motif = list(params["notes"])
    notes = [
        {
            "id": f"agent-riff-{index + 1}",
            "beat": round(start * 4 + float(event["beat"]), 2),
            "duration": float(event.get("duration", 0.5)),
            "note": int(event["note"]),
            "velocity": float(event.get("velocity", 0.75)),
            "color": track.get("color", "#60c8f8"),
            # Notes belong to a track from schema v4 on. Without this the app
            # falls back to whichever track happens to be selected.
            "trackId": track_id,
        }
        for index, event in enumerate(motif)
    ]
    _, note_message = ensure_notes(project, notes)
    detail = "riff-machine-style motif seed in the loop window for later manual or agent iteration"
    _, recipe_message = ensure_recipe(project, agent_recipe_item(feature, detail, [track_id]))
    return [clip_message, note_message, recipe_message]


def apply_gross_beat_transition(project: dict[str, Any], feature: DawFeature, params: dict[str, Any] | None = None, role_map: dict[str, list[str]] | None = None) -> list[str]:
    params = params or {}
    track = pick_track(project, ("fx", "lead", "vocal", "drums"), params, role_map)
    if not track:
        return ["no FX, lead, vocal, or drum track available for transition cue"]
    _, end = loop_window(project)
    if "endBar" in params:
        end = float(params["endBar"])
    bars = int(params.get("bars") or 2)
    start = max(0.0, end - bars)
    track_id = str(track.get("id", "fx"))
    _, effect_message = ensure_effect(track, "agent-gate-tapestop", "Gate / Tape Stop", float(params.get("amount", 0.58)))
    clip = {
        "id": f"agent-gate-tail-{safe_id(track_id)}",
        "name": "Agent gated tail",
        "startBar": round(start, 2),
        "bars": bars,
        "lane": track_id,
        "color": track.get("color", "#f59fcb"),
        "type": "automation",
    }
    _, clip_message = ensure_clip(track, clip)
    detail = f"gated/tape-stop cue over the final {bars} bars before bar {end:g}"
    _, recipe_message = ensure_recipe(project, agent_recipe_item(feature, detail, [track_id]))
    return [effect_message, clip_message, recipe_message]


def apply_patcher_macro(project: dict[str, Any], feature: DawFeature, params: dict[str, Any] | None = None, role_map: dict[str, list[str]] | None = None) -> list[str]:
    params = params or {}
    track = pick_track(project, ("selected", "lead", "bass", "fx"), params, role_map)
    if not track:
        return ["no selected or primary track available for macro chain"]
    start, end = loop_window(project)
    track_id = str(track.get("id", "track"))
    _, eq_message = ensure_effect(track, "agent-macro-eq", "Macro EQ", float(params.get("eqAmount", 0.45)))
    _, duck_message = ensure_effect(track, "agent-macro-duck", "Macro Duck", float(params.get("duckAmount", 0.36)))
    points = params.get("points") or [
        {"bar": round(start, 2), "value": 0.25, "curve": "linear"},
        {"bar": round((start + end) / 2, 2), "value": 0.65, "curve": "linear"},
        {"bar": round(end, 2), "value": 0.42, "curve": "linear"},
    ]
    lane = {
        "id": f"agent-macro-{safe_id(track_id)}",
        "trackId": track_id,
        "parameter": "macro",
        "label": "Agent macro control",
        "color": track.get("color", "#9ef0c0"),
        "enabled": True,
        "curve": "linear",
        "points": [dict(point) for point in points],
    }
    _, lane_message = ensure_lane(project, lane)
    detail = "patcher-style macro chain with EQ and ducking targets ready for binding"
    _, recipe_message = ensure_recipe(project, agent_recipe_item(feature, detail, [track_id]))
    return [eq_message, duck_message, lane_message, recipe_message]


def apply_capture_midi(project: dict[str, Any], feature: DawFeature, params: dict[str, Any] | None = None, role_map: dict[str, list[str]] | None = None) -> list[str]:
    params = params or {}
    snap = snapshot(project)
    start, end = loop_window(project)
    if "startBar" in params and "endBar" in params:
        start, end = float(params["startBar"]), float(params["endBar"])
    track = pick_track(project, ("lead", "chords", "bass"), params, role_map)
    track_ids = [str(track.get("id"))] if track else []
    snap["loopEnabled"] = True
    snap["loopStartBar"] = round(start, 2)
    snap["loopEndBar"] = round(end, 2)
    detail = f"loop checkpoint preserved from bar {start:g} to {end:g} for recall and next-agent iteration"
    _, recipe_message = ensure_recipe(project, agent_recipe_item(feature, detail, track_ids))
    return [recipe_message, "loop checkpoint enabled"]


def apply_logic_drummer_fill(project: dict[str, Any], feature: DawFeature, params: dict[str, Any] | None = None, role_map: dict[str, list[str]] | None = None) -> list[str]:
    params = params or {}
    track = pick_track(project, ("drums", "percussion"), params, role_map)
    if not track:
        return ["no drum track available for fill cue"]
    _, end = loop_window(project)
    if "beforeBar" in params:
        end = float(params["beforeBar"])
    bars = int(params.get("bars") or 1)
    start = max(0.0, end - bars)
    track_id = str(track.get("id", "drums"))
    clip = {
        "id": f"agent-drum-fill-{safe_id(track_id)}",
        "name": "Agent pre-drop fill",
        "startBar": round(start, 2),
        "bars": bars,
        "lane": track_id,
        "color": track.get("color", "#ff8d5c"),
        "type": "pattern",
    }
    _, clip_message = ensure_clip(track, clip)
    detail = f"section-aware {bars}-bar fill cue before bar {end:g}"
    _, recipe_message = ensure_recipe(project, agent_recipe_item(feature, detail, [track_id]))
    return [clip_message, recipe_message]


def apply_bitwig_modulator(project: dict[str, Any], feature: DawFeature, params: dict[str, Any] | None = None, role_map: dict[str, list[str]] | None = None) -> list[str]:
    params = params or {}
    track = pick_track(project, ("lead", "chords", "fx"), params, role_map)
    if not track:
        return ["no melodic or FX track available for modulation lane"]
    start, end = loop_window(project)
    track_id = str(track.get("id", "track"))
    parameter = str(params.get("parameter") or "width")
    points = params.get("points") or [
        {"bar": round(start, 2), "value": 0.46, "curve": "sine"},
        {"bar": round(start + (end - start) * 0.33, 2), "value": 0.7, "curve": "sine"},
        {"bar": round(start + (end - start) * 0.66, 2), "value": 0.38, "curve": "sine"},
        {"bar": round(end, 2), "value": 0.58, "curve": "sine"},
    ]
    lane = {
        "id": f"agent-width-motion-{safe_id(track_id)}",
        "trackId": track_id,
        "parameter": parameter,
        "label": f"Agent {parameter} motion",
        "color": track.get("color", "#a7f3d0"),
        "enabled": True,
        "curve": "sine",
        "points": [dict(point) for point in points],
    }
    _, lane_message = ensure_lane(project, lane)
    detail = f"modulator-style {parameter} motion lane for movement without rewriting notes"
    _, recipe_message = ensure_recipe(project, agent_recipe_item(feature, detail, [track_id]))
    return [lane_message, recipe_message]


APPLIERS = {
    "fl-automation-clips": apply_automation_clips,
    "fl-randomizer-groove": apply_randomizer_groove,
    "fl-riff-machine-variation": apply_riff_variation,
    "fl-gross-beat-transition": apply_gross_beat_transition,
    "fl-patcher-macro-chain": apply_patcher_macro,
    "ableton-capture-midi": apply_capture_midi,
    "logic-drummer-fill": apply_logic_drummer_fill,
    "bitwig-modulator-lane": apply_bitwig_modulator,
}


def apply_features(
    project: dict[str, Any],
    ranked: list[dict[str, Any]],
    max_actions: int,
    role_map: dict[str, list[str]] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    feature_by_id = {feature.id: feature for feature in CATALOG}
    updated = deep_copy_jsonish(project)
    ensure_controls(updated)
    actions: list[dict[str, Any]] = []
    for candidate in ranked[:max_actions]:
        feature = feature_by_id[candidate["id"]]
        applier = APPLIERS[feature.id]
        before = project_metrics(updated)
        messages = applier(updated, feature, params=candidate.get("params") or None, role_map=role_map)
        ensure_controls(updated)
        after = project_metrics(updated)
        changed = any(after[key] != before[key] for key in after)
        action = {
            "featureId": feature.id,
            "source": feature.source,
            "title": feature.title,
            "changed": changed,
            "messages": messages,
            "metricsBefore": before,
            "metricsAfter": after,
        }
        if candidate.get("decision"):
            action["decision"] = dict(candidate["decision"])
        if candidate.get("params"):
            action["params"] = dict(candidate["params"])
        actions.append(action)
    updated["updatedAt"] = now_iso()
    return updated, actions


# ---------------------------------------------------------------------------
# Choosing tactics. `retrieve_features` is the keyword ranking and always
# works; `select_features` asks the model for the same list (plus per-track
# roles and per-tactic parameters) and falls back to the ranking when the
# answer is missing or does not validate.
# ---------------------------------------------------------------------------

SELECT_ROLE = (
    "You plan which DAW-style tactics an automated agent should apply to a Neon Studio project. "
    "You are given the project's tracks, its metrics, the caller's request or sound-check feedback, "
    "and a catalog of tactics with the parameters each accepts. Choose only tactics from the catalog, "
    "order them by how much they would help this project, and give a one-sentence reason each in plain words "
    "a producer would use. Name the track each tactic should edit by its id. Only propose parameters that "
    "fit the stated ranges; leave a tactic's parameters empty to use its defaults. Also label every track with "
    "roles from the allowed list. Never invent tracks, tactics, or numbers outside the ranges."
)

SELECT_SCHEMA = {
    "trackRoles": {"<track id>": ["role from the allowed list"]},
    "selectedFeatures": [
        {
            "id": "tactic id from the catalog",
            "reason": "one sentence: why this tactic, for this project and feedback",
            "trackId": "track id to edit, or null",
            "params": {"...": "parameters from the tactic's schema, or an empty object"},
        }
    ],
}

NARRATE_ROLE = (
    "You write the short report for an automated DAW agent that just edited a Neon Studio project. "
    "Only describe actions whose `changed` flag is true; say plainly when nothing changed. "
    "Use the track names given. Do not invent measurements or effects that are not in the action messages."
)

NARRATE_SCHEMA = {
    "summary": "one or two sentences: what changed in the project and why it should help",
    "actions": [{"featureId": "tactic id", "why": "one sentence, in the producer's words"}],
}


def track_summaries(project: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for track in project_tracks(project):
        lowered = track_text(track).lower()
        roles = sorted(
            role for role, keywords in ROLE_KEYWORDS.items()
            if role != "selected" and any(keyword in lowered for keyword in keywords)
        )
        out.append({
            "id": str(track.get("id", "")),
            "name": str(track.get("name", "")),
            "kind": str(track.get("kind", "")),
            "instrument": str(track.get("instrument", "")),
            "gain": track.get("gain"),
            "effects": [str(effect.get("name", "")) for effect in (track.get("effects") or []) if isinstance(effect, dict)][:6],
            "clips": [str(clip.get("name", "")) for clip in (track.get("clips") or []) if isinstance(clip, dict)][:6],
            "keywordRoles": roles,
        })
    return out


def feedback_summary(feedback: Any) -> Any:
    """A compact view of sound-check feedback for the model."""
    if feedback is None:
        return None
    if isinstance(feedback, str):
        return feedback[:2000]
    if isinstance(feedback, dict):
        verdict = feedback.get("verdict") if isinstance(feedback.get("verdict"), dict) else {}
        return {
            "verdict": {key: verdict.get(key) for key in ("score", "answer", "summary") if key in verdict},
            "issues": [
                {key: issue.get(key) for key in ("severity", "area", "detail", "requirementIds") if key in issue}
                for issue in (feedback.get("issues") or [])[:8] if isinstance(issue, dict)
            ],
            "nextActions": [str(item) for item in (feedback.get("nextActions") or [])[:6]],
            "metrics": feedback.get("metrics") if isinstance(feedback.get("metrics"), dict) else None,
        }
    return str(feedback)[:2000]


def catalog_summary() -> list[dict[str, Any]]:
    return [
        {
            "id": feature.id,
            "title": feature.title,
            "summary": feature.summary,
            "roles": list(feature.roles),
            "actions": list(feature.actions),
            "params": PARAM_SCHEMA.get(feature.id, {}),
        }
        for feature in CATALOG
    ]


def feature_record(feature: DawFeature, score: float, reasons: list[str], decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": feature.id,
        "source": feature.source,
        "title": feature.title,
        "summary": feature.summary,
        "score": round(score, 3),
        "reasons": reasons,
        "actions": list(feature.actions),
        "decision": decision,
    }


def validate_selection(answer: Any, project: dict[str, Any] | None, limit: int) -> tuple[list[dict[str, Any]], dict[str, list[str]], list[str]]:
    """Keep only catalog ids, project track ids, allowed roles and in-range
    parameters from the model's answer. Returns (ranked, trackRoles, notes)."""
    notes: list[str] = []
    ranked: list[dict[str, Any]] = []
    role_map: dict[str, list[str]] = {}
    if not isinstance(answer, dict):
        return ranked, role_map, ["model answer was not an object"]
    feature_by_id = {feature.id: feature for feature in CATALOG}
    known_roles = set(ROLE_KEYWORDS) - {"selected"}
    known_tracks = {str(track.get("id", "")) for track in project_tracks(project)} if project else set()

    raw_roles = answer.get("trackRoles")
    if isinstance(raw_roles, dict):
        for track_id, roles in raw_roles.items():
            if str(track_id) not in known_tracks:
                notes.append(f"dropped roles for unknown track {track_id!r}")
                continue
            if isinstance(roles, str):
                roles = [roles]
            if not isinstance(roles, list):
                continue
            kept = [str(role).strip().lower() for role in roles if str(role).strip().lower() in known_roles]
            dropped = [str(role) for role in roles if str(role).strip().lower() not in known_roles]
            if dropped:
                notes.append(f"dropped unknown roles {dropped} on track {track_id}")
            if kept:
                role_map[str(track_id)] = kept

    seen: set[str] = set()
    for position, item in enumerate(answer.get("selectedFeatures") or []):
        if not isinstance(item, dict):
            continue
        feature_id = str(item.get("id") or "").strip()
        feature = feature_by_id.get(feature_id)
        if feature is None:
            notes.append(f"dropped unknown tactic {feature_id!r}")
            continue
        if feature_id in seen:
            notes.append(f"dropped repeated tactic {feature_id}")
            continue
        seen.add(feature_id)
        params_in = item.get("params") if isinstance(item.get("params"), dict) else {}
        params_in = dict(params_in)
        if item.get("trackId"):
            params_in["trackId"] = item.get("trackId")
        params, param_notes = validate_params(feature_id, params_in, project)
        notes.extend(param_notes)
        reason = str(item.get("reason") or "").strip()[:300] or "chosen by the model"
        score = max(0.0, 1.0 - position * (1.0 / max(1, limit)))
        record = feature_record(feature, score, [reason], {"source": "model", "reason": reason})
        if params:
            record["params"] = params
        ranked.append(record)
        if len(ranked) >= limit:
            break
    return ranked, role_map, notes


def select_features(
    query: str | None,
    project: dict[str, Any] | None,
    *,
    assist: llm.Assist | None = None,
    feedback: Any = None,
    limit: int = 5,
) -> dict[str, Any]:
    """The tactics to apply, in order. Returns {"ranked", "trackRoles", "notes", "source"}."""
    heuristic = retrieve_features(query, project=project, limit=limit)
    for item in heuristic:
        item["decision"] = {"source": "heuristic", "reason": "keyword overlap: " + ", ".join(item["reasons"])}
    fallback = {"ranked": heuristic, "trackRoles": {}, "notes": [], "source": "heuristic"}
    if assist is None or not assist.available or project is None:
        return fallback
    task = json.dumps(
        {
            "request": (query or "").strip() or None,
            "feedback": feedback_summary(feedback),
            "project": {
                "id": project.get("id"),
                "name": project.get("name"),
                "description": str(project.get("description") or "")[:600],
                "keyCenter": project.get("keyCenter"),
                "bpm": snapshot(project).get("bpm"),
                "loop": [snapshot(project).get("loopStartBar"), snapshot(project).get("loopEndBar")],
                "bars": total_bars(project),
                "metrics": project_metrics(project),
                "tracks": track_summaries(project),
                "automationLanes": [
                    {"trackId": lane.get("trackId"), "parameter": lane.get("parameter")}
                    for lane in (snapshot(project).get("automationLanes") or []) if isinstance(lane, dict)
                ][:12],
            },
            "allowedRoles": sorted(set(ROLE_KEYWORDS) - {"selected"}),
            "catalog": catalog_summary(),
            "howMany": limit,
        },
        indent=1,
    )[:24000]
    answer = assist.ask(task, system=SELECT_ROLE, schema=SELECT_SCHEMA, expect=dict)
    if answer is None:
        fallback["notes"] = [f"model unavailable ({assist.note}); keyword retrieval used"]
        return fallback
    ranked, role_map, notes = validate_selection(answer, project, limit)
    if not ranked:
        assist.note = "model chose no known tactic; keyword retrieval used"
        fallback["notes"] = notes + [assist.note]
        return fallback
    return {"ranked": ranked, "trackRoles": role_map, "notes": notes, "source": "model"}


def narrate_actions(
    actions: list[dict[str, Any]],
    before: dict[str, Any],
    after: dict[str, Any],
    project: dict[str, Any],
    assist: llm.Assist | None,
) -> dict[str, Any] | None:
    """The model's summary and per-action why. None when the model is off or
    answers something that does not fit the actions that ran."""
    if assist is None or not assist.available or not actions:
        return None
    names = {str(track.get("id", "")): str(track.get("name", "")) for track in project_tracks(project)}
    task = json.dumps(
        {
            "project": {"id": project.get("id"), "name": project.get("name"), "trackNames": names},
            "actions": [
                {
                    "featureId": action["featureId"],
                    "title": action["title"],
                    "changed": action["changed"],
                    "messages": action["messages"],
                    "reason": (action.get("decision") or {}).get("reason"),
                }
                for action in actions
            ],
            "metricsBefore": before,
            "metricsAfter": after,
        },
        indent=1,
    )[:24000]
    answer = assist.ask(task, system=NARRATE_ROLE, schema=NARRATE_SCHEMA, expect=dict)
    if not isinstance(answer, dict):
        return None
    summary = str(answer.get("summary") or "").strip()
    known = {action["featureId"] for action in actions}
    whys: dict[str, str] = {}
    for item in answer.get("actions") or []:
        if isinstance(item, dict) and str(item.get("featureId")) in known and str(item.get("why") or "").strip():
            whys[str(item["featureId"])] = str(item["why"]).strip()[:300]
    if not summary and not whys:
        return None
    return {"summary": summary[:600], "whys": whys}


def ai_block(assist: llm.Assist, plan: dict[str, Any]) -> dict[str, Any]:
    """The `ai` block, kept consistent with `selectionSource`: `used` is true
    only when the model's selection is the one applied. A fall back to keyword
    retrieval - model over quota, unreachable, or choosing nothing known - is
    not a use even though a call went out, and neither is a caller's own list."""
    block = assist.report()
    if plan["source"] != "model":
        block["used"] = False
        if plan["source"] == "caller" and assist.available and not block["note"]:
            block["note"] = "tactics named by the caller; the model was not asked"
    return block


def run_agent(
    project: dict[str, Any],
    query: str | None,
    max_actions: int = 4,
    *,
    assist: llm.Assist | None = None,
    feedback: Any = None,
    features: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Choose and apply tactics. `features` (ranked records from
    `explicit_features`) bypasses selection entirely, for callers that already
    decided what to apply. The model narrates only the tactics it chose: when
    selection fell back to keyword retrieval the summary stays the measured
    one, so `selectionSource` and the `ai` block always agree."""
    if assist is None:
        assist = llm.Assist(enabled=False)
    before = project_metrics(project)
    if features is not None:
        plan = {"ranked": features, "trackRoles": {}, "notes": [], "source": "caller"}
    else:
        plan = select_features(query, project, assist=assist, feedback=feedback, limit=max(8, max_actions))
    ranked = plan["ranked"]
    updated, actions = apply_features(project, ranked, max_actions=max_actions, role_map=plan.get("trackRoles") or None)
    after = project_metrics(updated)
    metrics_summary = summarize_actions(actions, before, after)
    summary = metrics_summary
    narration = narrate_actions(actions, before, after, project, assist) if plan["source"] == "model" else None
    if narration:
        if narration["summary"]:
            summary = narration["summary"]
        for action in actions:
            why = narration["whys"].get(action["featureId"])
            if why:
                action["why"] = why
                action["messages"] = list(action["messages"]) + [f"why: {why}"]
    return {
        "project": {"id": updated.get("id"), "name": updated.get("name")},
        "query": query or DEFAULT_QUERY,
        "selectedFeatures": ranked[:max_actions],
        "selectionSource": plan["source"],
        "trackRoles": plan.get("trackRoles") or {},
        "selectionNotes": plan.get("notes") or [],
        "actions": actions,
        "metricsBefore": before,
        "metricsAfter": after,
        "summary": summary,
        "metricsSummary": metrics_summary,
        "ai": ai_block(assist, plan),
        "updatedProject": updated,
    }


def explicit_features(feature_ids: list[str], params_by_id: dict[str, Any] | None, project: dict[str, Any] | None) -> tuple[list[dict[str, Any]], list[str]]:
    """Ranked records for tactics a caller named directly (`--feature`)."""
    feature_by_id = {feature.id: feature for feature in CATALOG}
    ranked: list[dict[str, Any]] = []
    notes: list[str] = []
    for position, raw in enumerate(feature_ids):
        feature_id = str(raw).strip()
        feature = feature_by_id.get(feature_id)
        if feature is None:
            notes.append(f"unknown tactic {feature_id!r}")
            continue
        params, param_notes = validate_params(feature_id, (params_by_id or {}).get(feature_id), project)
        notes.extend(param_notes)
        record = feature_record(feature, 1.0 - position * 0.05, ["requested"], {"source": "caller", "reason": "requested by name"})
        if params:
            record["params"] = params
        ranked.append(record)
    return ranked, notes


def summarize_actions(actions: list[dict[str, Any]], before: dict[str, Any], after: dict[str, Any]) -> str:
    changed_count = sum(1 for action in actions if action.get("changed"))
    return (
        f"Applied {changed_count}/{len(actions)} DAW-agent tactics: "
        f"recipe {before['recipeCount']}->{after['recipeCount']}, "
        f"automation {before['automationLaneCount']}->{after['automationLaneCount']}, "
        f"clips {before['clipCount']}->{after['clipCount']}."
    )


def collect_project_paths(root: Path) -> list[Path]:
    seen: set[str] = set()
    paths: list[Path] = []
    for base in (root / "data" / "projects", root / "factory" / "projects"):
        if not base.exists():
            continue
        for path in sorted(base.glob("*.neon.json")):
            project_id = path.stem.removesuffix(".neon")
            if project_id in seen:
                continue
            seen.add(project_id)
            paths.append(path)
    return paths


def duplicate_ids(project: dict[str, Any]) -> dict[str, list[str]]:
    checks: dict[str, list[str]] = {}
    snap = snapshot(project)
    groups = {
        "tracks": [track.get("id") for track in project_tracks(project) if isinstance(track, dict)],
        "clips": [
            clip.get("id")
            for track in project_tracks(project)
            for clip in (track.get("clips", []) or [])
            if isinstance(clip, dict)
        ],
        "automationLanes": [
            lane.get("id")
            for lane in (snap.get("automationLanes", []) or [])
            if isinstance(lane, dict)
        ],
        "recipe": [item.get("id") for item in (snap.get("recipe", []) or []) if isinstance(item, dict)],
        "notes": [note.get("id") for note in (snap.get("notes", []) or []) if isinstance(note, dict)],
    }
    for label, ids in groups.items():
        filtered = [str(item) for item in ids if item]
        dupes = sorted({item for item in filtered if filtered.count(item) > 1})
        if dupes:
            checks[label] = dupes
    return checks


def controls_cover_tracks(project: dict[str, Any]) -> bool:
    controls = snapshot(project).get("controls", {}) or {}
    return all(track.get("id") in controls for track in project_tracks(project))


def offline_eval(root: Path, query: str | None, max_actions: int) -> dict[str, Any]:
    results = []
    for path in collect_project_paths(root):
        original = read_json(path)
        report = run_agent(original, query=query, max_actions=max_actions)
        updated = report["updatedProject"]
        before = report["metricsBefore"]
        after = report["metricsAfter"]
        duplicates = duplicate_ids(updated)
        failures: list[str] = []
        if len(report["actions"]) < max_actions:
            failures.append("agent selected fewer actions than requested")
        if after["recipeCount"] < before["recipeCount"] + min(2, max_actions):
            failures.append("recipe evidence did not increase enough")
        if after["automationLaneCount"] < before["automationLaneCount"]:
            failures.append("automation lane count regressed")
        if after["clipCount"] < before["clipCount"]:
            failures.append("clip count regressed")
        if after["trackCount"] != before["trackCount"]:
            failures.append("track count changed unexpectedly")
        if duplicates:
            failures.append(f"duplicate ids found: {duplicates}")
        if not controls_cover_tracks(updated):
            failures.append("mixer controls do not cover all tracks")
        results.append(
            {
                "path": str(path),
                "projectId": original.get("id"),
                "passed": not failures,
                "failures": failures,
                "summary": report["summary"],
                "metricsBefore": before,
                "metricsAfter": after,
                "features": [item["id"] for item in report["selectedFeatures"]],
            }
        )
    passed = sum(1 for item in results if item["passed"])
    total = len(results)
    return {
        "name": "daw-agent-offline-eval",
        "passed": passed,
        "total": total,
        "passRate": round(passed / total, 4) if total else 0.0,
        "results": results,
        "status": "pass" if total and passed == total else "fail",
    }


def retrieval_check(limit: int = 3) -> dict[str, Any]:
    cases = []
    reciprocal_ranks = []
    hits = 0
    for query, expected in RETRIEVAL_CASES:
        ranked = retrieve_features(query, project=None, limit=max(limit, len(CATALOG)))
        ids = [item["id"] for item in ranked]
        rank = ids.index(expected) + 1 if expected in ids else None
        hit = rank is not None and rank <= limit
        if hit:
            hits += 1
        reciprocal_ranks.append(1.0 / rank if rank else 0.0)
        cases.append(
            {
                "query": query,
                "expected": expected,
                "rank": rank,
                "hitAtK": hit,
                "top": ids[:limit],
            }
        )
    recall = hits / len(RETRIEVAL_CASES)
    mrr = sum(reciprocal_ranks) / len(reciprocal_ranks)
    return {
        "name": "daw-agent-retrieval-quality",
        "k": limit,
        "recallAtK": round(recall, 4),
        "mrr": round(mrr, 4),
        "cases": cases,
        "status": "pass" if recall >= 1.0 and mrr >= 0.95 else "fail",
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    if report.get("name") == "daw-agent-offline-eval":
        lines = [
            "# DAW Agent Offline Eval",
            "",
            f"- Status: {report['status']}",
            f"- Passed: {report['passed']}/{report['total']}",
            f"- Pass rate: {report['passRate']}",
            "",
        ]
        for result in report["results"]:
            lines.append(f"## {result['projectId']}")
            lines.append(f"- Passed: {result['passed']}")
            lines.append(f"- Features: {', '.join(result['features'])}")
            lines.append(f"- {result['summary']}")
            if result["failures"]:
                lines.append(f"- Failures: {'; '.join(result['failures'])}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"
    if report.get("name") == "daw-agent-retrieval-quality":
        lines = [
            "# DAW Agent Retrieval Quality",
            "",
            f"- Status: {report['status']}",
            f"- Recall@{report['k']}: {report['recallAtK']}",
            f"- MRR: {report['mrr']}",
            "",
        ]
        for case in report["cases"]:
            lines.append(
                f"- `{case['query']}` -> expected `{case['expected']}`, rank {case['rank']}, top {', '.join(case['top'])}"
            )
        return "\n".join(lines) + "\n"

    if "metrics" in report and "actions" not in report:
        lines = [
            "# DAW Agent Suggestions",
            "",
            f"- Project: {report['project']['name']} (`{report['project']['id']}`)",
            f"- Query: {report['query']}",
            f"- Tracks: {report['metrics']['trackCount']}",
            f"- Clips: {report['metrics']['clipCount']}",
            f"- Automation lanes: {report['metrics']['automationLaneCount']}",
            "",
            "## Retrieved Tactics",
        ]
        for feature in report["selectedFeatures"]:
            lines.append(f"- {feature['id']} score={feature['score']}: {feature['title']} ({feature['source']})")
        return "\n".join(lines) + "\n"

    lines = [
        "# DAW Agent",
        "",
        f"- Project: {report['project']['name']} (`{report['project']['id']}`)",
        f"- {report['summary']}",
        "",
        "## Applied Tactics",
    ]
    for action in report["actions"]:
        lines.append(f"- {action['title']} ({action['source']}): {'; '.join(action['messages'])}")
    lines.append("")
    lines.append("## Retrieval")
    for feature in report["selectedFeatures"]:
        lines.append(f"- {feature['id']} score={feature['score']}: {feature['title']}")
    return "\n".join(lines) + "\n"


def emit(report: dict[str, Any], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(report, sort_keys=True))
    else:
        print(render_markdown_report(report), end="")


def strip_project_from_report(report: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(report)
    cleaned.pop("updatedProject", None)
    return cleaned


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply deterministic DAW-inspired agent tactics to Neon Studio projects.")
    parser.add_argument("--root", default=".", help="Repository or app-support root containing data/projects and factory/projects.")
    llm.add_ai_argument(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_project_args(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("--project-id", help="Project id under data/projects or factory/projects.")
        subparser.add_argument("--project", help="Direct path to a .neon.json project file.")
        subparser.add_argument("--query", help="Intent query for retrieval.")
        subparser.add_argument("--feedback-json", help="Sound-check JSON file to fold into retrieval.")
        subparser.add_argument("--feedback-text", help="Sound-check text to fold into retrieval.")
        subparser.add_argument("--max-actions", type=int, default=4, help="Number of tactics to apply or preview.")
        subparser.add_argument("--feature", action="append", default=None, help="Apply this tactic id (repeatable, in order) instead of choosing; see `catalog`.")
        subparser.add_argument("--params-json", help="JSON file mapping tactic id -> parameters, used with --feature.")
        subparser.add_argument("--format", choices=("json", "markdown"), default="json")

    suggest = subparsers.add_parser("suggest", help="Retrieve DAW tactics for a project without writing changes.")
    add_project_args(suggest)

    apply = subparsers.add_parser("apply", help="Apply DAW tactics and write an updated project JSON.")
    add_project_args(apply)
    apply.add_argument("--output", help="Output .neon.json path. Required unless --in-place is passed.")
    apply.add_argument("--in-place", action="store_true", help="Write changes back to the source project file.")

    eval_parser = subparsers.add_parser("offline-eval", help="Run deterministic offline eval over local project fixtures.")
    eval_parser.add_argument("--query", help="Intent query for retrieval.")
    eval_parser.add_argument("--max-actions", type=int, default=4)
    eval_parser.add_argument("--format", choices=("json", "markdown"), default="markdown")

    retrieval = subparsers.add_parser("retrieval-check", help="Run local retrieval quality checks over the DAW catalog.")
    retrieval.add_argument("--k", type=int, default=3)
    retrieval.add_argument("--format", choices=("json", "markdown"), default="markdown")

    feedback = subparsers.add_parser("feedback-query", help="Convert sound-check feedback into a DAW-agent retrieval query.")
    feedback.add_argument("--feedback-json", help="Sound-check JSON file.")
    feedback.add_argument("--feedback-text", help="Sound-check text.")
    feedback.add_argument("--format", choices=("json", "markdown"), default="markdown")

    catalog = subparsers.add_parser("catalog", help="List available DAW tactics.")
    catalog.add_argument("--format", choices=("json", "markdown"), default="markdown")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(args.root).expanduser().resolve()

    try:
        if args.command == "catalog":
            report = {
                "name": "daw-agent-catalog",
                "features": [
                    {
                        "id": feature.id,
                        "source": feature.source,
                        "title": feature.title,
                        "summary": feature.summary,
                        "intents": list(feature.intents),
                        "actions": list(feature.actions),
                    }
                    for feature in CATALOG
                ],
            }
            if args.format == "json":
                emit(report, "json")
            else:
                for feature in report["features"]:
                    print(f"- {feature['id']}: {feature['title']} ({feature['source']})")
            return 0

        if args.command == "retrieval-check":
            report = retrieval_check(limit=args.k)
            emit(report, args.format)
            return 0 if report["status"] == "pass" else 1

        if args.command == "feedback-query":
            query = effective_query(None, args.feedback_json, args.feedback_text) or ""
            report = {"name": "daw-agent-feedback-query", "query": query}
            if args.format == "json":
                emit(report, "json")
            else:
                print(query)
            return 0 if query else 1

        if args.command == "offline-eval":
            report = offline_eval(root, query=args.query, max_actions=max(1, args.max_actions))
            emit(report, args.format)
            return 0 if report["status"] == "pass" else 1

        path = resolve_project_path(root, args.project_id, args.project)
        project = read_json(path)
        feedback = read_feedback(Path(args.feedback_json).expanduser() if args.feedback_json else None, args.feedback_text)
        query = effective_query(args.query, args.feedback_json, args.feedback_text)
        assist = llm.assist_from_args(args)
        explicit = None
        explicit_notes: list[str] = []
        if args.feature:
            params_by_id = None
            if args.params_json:
                params_by_id = json.loads(Path(args.params_json).expanduser().read_text(encoding="utf-8"))
            explicit, explicit_notes = explicit_features(args.feature, params_by_id, project)
            if not explicit:
                raise ValueError("no known tactic in --feature: " + "; ".join(explicit_notes))

        if args.command == "suggest":
            if explicit is not None:
                plan = {"ranked": explicit, "trackRoles": {}, "notes": explicit_notes, "source": "caller"}
            else:
                plan = select_features(query, project, assist=assist, feedback=feedback, limit=max(1, args.max_actions))
            report = {
                "project": {"id": project.get("id"), "name": project.get("name")},
                "query": query or DEFAULT_QUERY,
                "metrics": project_metrics(project),
                "selectedFeatures": plan["ranked"],
                "selectionSource": plan["source"],
                "trackRoles": plan["trackRoles"],
                "selectionNotes": plan["notes"],
                "ai": ai_block(assist, plan),
            }
            emit(report, args.format)
            return 0

        if args.command == "apply":
            if not args.output and not args.in_place:
                raise ValueError("apply requires --output or --in-place")
            report = run_agent(
                project, query=query, max_actions=max(1, args.max_actions),
                assist=assist, feedback=feedback, features=explicit,
            )
            if explicit_notes:
                report["selectionNotes"] = list(report.get("selectionNotes") or []) + explicit_notes
            output_path = path if args.in_place else Path(args.output).expanduser()
            if not output_path.is_absolute():
                output_path = root / output_path
            write_json(output_path, report["updatedProject"])
            cleaned = strip_project_from_report(report)
            cleaned["output"] = str(output_path)
            emit(cleaned, args.format)
            return 0

        parser.error(f"unknown command {args.command}")
    except Exception as exc:
        print(f"daw_agent.py: {exc}", file=sys.stderr)
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
