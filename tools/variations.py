#!/usr/bin/env python3
"""Generate a few musically distinct alternatives for one lane in one section.

"Here are three ways this could go, which do you like?" is the most natural
human-in-the-loop move a production tool can make. This tool takes one track
and one section of a .neon.json project, writes ``--count`` variant projects
that differ from the original ONLY on that track, and renders a short preview
of each so the user can listen and pick instead of reading a diff.

What a variation is depends on the lane:

* melodic lane with notes  - contour / rhythm / density / range rewrites of
                             the notes in that section, kept inside the key
* melodic lane, no notes   - a starter phrase from the key, then the same
                             rewrites (the label says it was seeded)
* drum lane (steps)        - off-beat hats, half-time backbeat, last-bar fill
* effects/automation lane  - the lane's endpoint values moved by +/-0.25 and
                             a different curve

Usage:
  variations.py --root ROOT --project PATH --track-id lead --section drop
      [--count 3] [--seed 7] [--output-dir DIR] [--format json|markdown]

``--section`` accepts a section name ("Drop", "Second Drop") or a bar range
("24-40", 0-based like clip startBar).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Optional

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from render_mixdown import is_drum_track, mix_project, percussion_pitch, write_wav  # noqa: E402
from vocal_autotune import nearest_scale_midi  # noqa: E402


PREVIEW_NOTE = "Previews use the built-in instrument for the changed lane."

BEATS_PER_BAR = 4

NOTE_NAMES = {
    "c": 0, "c#": 1, "db": 1, "d": 2, "d#": 3, "eb": 3, "e": 4, "fb": 4, "f": 5,
    "e#": 5, "f#": 6, "gb": 6, "g": 7, "g#": 8, "ab": 8, "a": 9, "a#": 10,
    "bb": 10, "b": 11, "cb": 11,
}

MODE_INTERVALS = {
    "major": (0, 2, 4, 5, 7, 9, 11),
    "maj": (0, 2, 4, 5, 7, 9, 11),
    "ionian": (0, 2, 4, 5, 7, 9, 11),
    "lydian": (0, 2, 4, 6, 7, 9, 11),
    "mixolydian": (0, 2, 4, 5, 7, 9, 10),
    "minor": (0, 2, 3, 5, 7, 8, 10),
    "min": (0, 2, 3, 5, 7, 8, 10),
    "m": (0, 2, 3, 5, 7, 8, 10),
    "aeolian": (0, 2, 3, 5, 7, 8, 10),
    "dorian": (0, 2, 3, 5, 7, 9, 10),
    "phrygian": (0, 1, 3, 5, 7, 8, 10),
    "harmonic minor": (0, 2, 3, 5, 7, 8, 11),
}

SNAP_BEATS = {"1/4": 1.0, "1/8": 0.5, "1/16": 0.25, "1/32": 0.125, "none": 0.25}

EFFECT_WORDS = ("fx", "effect", "riser", "impact", "automation", "macro", "sweep")

# Section names people say versus the names clips carry.
SECTION_ALIASES = {
    "second drop": "drop 2",
    "2nd drop": "drop 2",
    "first drop": "drop 1",
    "1st drop": "drop 1",
    "second build": "build 2",
    "first build": "build 1",
    "pre build": "build",
    "pre-build": "build",
    "prebuild": "build",
    "breakdown": "break",
}


# --- Small helpers -----------------------------------------------------------


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "section"


def normalise_section_name(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    return SECTION_ALIASES.get(cleaned, cleaned)


def parse_key(key_center: Optional[str]) -> Optional[set]:
    """'D Major' -> {2, 4, 6, 7, 9, 11, 1}; None when there is no usable key."""
    if not isinstance(key_center, str) or not key_center.strip():
        return None
    text = key_center.strip().lower().replace("♯", "#").replace("♭", "b")
    match = re.match(r"^([a-g](?:#|b)?)\s*(.*)$", text)
    if not match:
        return None
    root = NOTE_NAMES.get(match.group(1))
    if root is None:
        return None
    mode_text = match.group(2).strip()
    intervals = MODE_INTERVALS.get(mode_text)
    if intervals is None:
        # "Dm", "D min", "D natural minor" and friends.
        if mode_text.startswith("min") or mode_text == "m" or "minor" in mode_text:
            intervals = MODE_INTERVALS["harmonic minor"] if "harmonic" in mode_text else MODE_INTERVALS["minor"]
        elif mode_text == "" or mode_text.startswith("maj"):
            intervals = MODE_INTERVALS["major"]
        else:
            intervals = MODE_INTERVALS["major"]
    return {(root + interval) % 12 for interval in intervals}


def snap_to_key(midi: float, scale: Optional[set]) -> int:
    value = int(round(midi))
    if scale:
        value = int(nearest_scale_midi(float(value), scale))
    return int(clamp(value, 0, 127))


def pitch_name(midi: int) -> str:
    names = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
    return f"{names[int(midi) % 12]}{int(midi) // 12 - 1}"


def note_owner(note: dict, snapshot: dict) -> str:
    """Untagged notes belong to the selected track, the same rule the app uses."""
    owner = note.get("trackId")
    if isinstance(owner, str) and owner:
        return owner
    return str(snapshot.get("selectedTrackId") or "")


def note_signature(note: dict) -> tuple:
    return (
        round(float(note.get("beat", 0)), 4),
        int(note.get("note", 60)),
        round(float(note.get("duration", 0.25)), 4),
        round(float(note.get("velocity", 0.8)), 3),
    )


# --- Project reading ---------------------------------------------------------


def load_project(path: Path) -> dict:
    project = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(project, dict) or not isinstance(project.get("snapshot"), dict):
        raise ValueError(f"{path} is not a .neon.json project (no snapshot).")
    return project


def find_track(snapshot: dict, track_ref: str) -> dict:
    tracks = [t for t in (snapshot.get("tracks") or []) if isinstance(t, dict)]
    for track in tracks:
        if str(track.get("id", "")) == track_ref:
            return track
    wanted = track_ref.strip().lower()
    for track in tracks:
        if str(track.get("name", "")).strip().lower() == wanted:
            return track
    available = ", ".join(str(t.get("id", "?")) for t in tracks) or "none"
    raise ValueError(f"No track with id or name {track_ref!r}. Tracks: {available}.")


def track_notes(snapshot: dict, track_id: str) -> list:
    return [
        n for n in (snapshot.get("notes") or [])
        if isinstance(n, dict) and note_owner(n, snapshot) == track_id
    ]


def track_lanes(snapshot: dict, track_id: str) -> list:
    return [
        lane for lane in (snapshot.get("automationLanes") or [])
        if isinstance(lane, dict) and str(lane.get("trackId", "")) == track_id
    ]


def lane_kind(track: dict, notes: list, lanes: list) -> str:
    """'melodic', 'drums' or 'automation', from what the track is and holds."""
    kind = str(track.get("kind") or "").lower()
    text = " ".join(str(track.get(key) or "") for key in ("name", "instrument", "id")).lower()
    if kind == "automation":
        return "automation"
    if notes:
        return "melodic"
    if is_drum_track(track):
        return "drums"
    if lanes and any(word in text for word in EFFECT_WORDS):
        return "automation"
    if any(word in text for word in EFFECT_WORDS) and not track.get("steps"):
        return "automation"
    return "melodic"


def resolve_section(snapshot: dict, track: dict, section_text: str) -> tuple:
    """(startBar, bars, label) for a section name or a bar range."""
    text = section_text.strip()
    range_match = re.match(r"^(\d+)\s*-\s*(\d+)$", text)
    if range_match:
        start, end = int(range_match.group(1)), int(range_match.group(2))
        if end <= start:
            raise ValueError(f"Bar range {text!r} must end after it starts.")
        return start, end - start, f"bars {start}-{end}"

    wanted = normalise_section_name(text)
    if not wanted:
        raise ValueError("--section is empty.")

    def matches(name: str) -> bool:
        candidate = normalise_section_name(name)
        return candidate == wanted or candidate.startswith(wanted + " ")

    # Recipe entries that carry their own bar positions are the authority.
    for item in snapshot.get("recipe") or []:
        if not isinstance(item, dict):
            continue
        if not isinstance(item.get("startBar"), (int, float)) or not isinstance(item.get("bars"), (int, float)):
            continue
        if matches(str(item.get("section", ""))) or matches(str(item.get("label", ""))):
            return int(item["startBar"]), int(item["bars"]), str(item.get("section") or item.get("label"))

    # Otherwise clips name their section ("Drop 1 hook"). Prefer the target
    # track's own clips, then anyone's; the earliest match wins so "drop"
    # means the first drop.
    target_id = str(track.get("id", ""))
    ordered_tracks = [track] + [
        t for t in (snapshot.get("tracks") or []) if isinstance(t, dict) and str(t.get("id", "")) != target_id
    ]
    for candidate_track in ordered_tracks:
        hits = [
            c for c in (candidate_track.get("clips") or [])
            if isinstance(c, dict) and matches(str(c.get("name", "")))
        ]
        if hits:
            start = min(int(c.get("startBar") or 0) for c in hits)
            bars = max(int(c.get("bars") or 1) for c in hits if int(c.get("startBar") or 0) == start)
            return start, max(1, bars), text

    names = sorted({
        str(c.get("name", "")) for t in ordered_tracks
        for c in (t.get("clips") or []) if isinstance(c, dict) and c.get("name")
    })
    raise ValueError(
        f"Could not find a section called {text!r}. Use a bar range like 24-40, "
        f"or one of the clip names: {', '.join(names) or 'none'}."
    )


# --- Melodic variants --------------------------------------------------------


def seed_from_motif(track_id: str, existing: list, start_beat: float, end_beat: float, color: str) -> list:
    """Tile the track's first phrase across the window so there is something to vary."""
    ordered = sorted(existing, key=lambda n: float(n.get("beat", 0)))
    first_bar = int(float(ordered[0].get("beat", 0)) // BEATS_PER_BAR)
    phrase_start = first_bar * BEATS_PER_BAR
    span = max(
        float(n.get("beat", 0)) + float(n.get("duration", 0.25)) - phrase_start for n in ordered
    )
    phrase_bars = max(1, int(np.ceil(span / BEATS_PER_BAR - 1e-6)))
    phrase = [n for n in ordered if float(n.get("beat", 0)) < phrase_start + phrase_bars * BEATS_PER_BAR]
    period = phrase_bars * BEATS_PER_BAR

    seeded = []
    offset = start_beat
    index = 0
    while offset < end_beat:
        for note in phrase:
            beat = offset + (float(note.get("beat", 0)) - phrase_start)
            if beat >= end_beat:
                continue
            duration = min(float(note.get("duration", 0.25)), end_beat - beat)
            seeded.append({
                "id": f"{track_id}-seed-{index}",
                "beat": round(beat, 4),
                "duration": round(duration, 4),
                "note": int(note.get("note", 60)),
                "velocity": float(note.get("velocity", 0.8)),
                "color": str(note.get("color") or color),
                "trackId": track_id,
            })
            index += 1
        offset += period
    return seeded


def seed_from_key(track_id: str, scale: Optional[set], start_beat: float, end_beat: float, color: str) -> list:
    """Root, fifth, third, octave in a plain 4-beat pattern, repeated per bar."""
    pcs = sorted(scale) if scale else [0, 2, 4, 5, 7, 9, 11]
    root_pc = _scale_root(scale) if scale else 0
    # Keep the phrase around middle C whatever the key: D sits at D4, A at A3.
    root = 60 + root_pc if root_pc <= 6 else 48 + root_pc
    degrees = sorted(((pc - root_pc) % 12) for pc in pcs)
    third = degrees[2] if len(degrees) > 2 else 4
    fifth = degrees[4] if len(degrees) > 4 else 7
    pattern = [(0.0, 0.75, root), (1.0, 0.75, root + fifth), (2.0, 0.75, root + third), (3.0, 1.0, root + 12)]

    seeded = []
    bar = start_beat
    index = 0
    while bar < end_beat:
        for offset, duration, pitch in pattern:
            beat = bar + offset
            if beat >= end_beat:
                continue
            seeded.append({
                "id": f"{track_id}-seed-{index}",
                "beat": round(beat, 4),
                "duration": round(min(duration, end_beat - beat), 4),
                "note": snap_to_key(pitch, scale),
                "velocity": 0.82 if offset in (0.0, 2.0) else 0.7,
                "color": color,
                "trackId": track_id,
            })
            index += 1
        bar += BEATS_PER_BAR
    return seeded


def _scale_root(scale: set) -> int:
    """The tonic is the pitch class whose scale reads as a plain major or minor."""
    for candidate in range(12):
        shifted = {(pc - candidate) % 12 for pc in scale}
        for intervals in (MODE_INTERVALS["major"], MODE_INTERVALS["minor"]):
            if shifted == set(intervals):
                return candidate
    return min(scale)


def _copy_notes(notes: list) -> list:
    return [deepcopy(n) for n in notes]


def variant_contour(notes: list, ctx: dict) -> tuple:
    pitches = [int(n["note"]) for n in notes]
    median = float(np.median(pitches))
    out = _copy_notes(notes)
    for note in out:
        note["note"] = snap_to_key(2.0 * median - int(note["note"]), ctx["scale"])
    return out, "Flipped contour, same rhythm", (
        f"Every interval now moves the opposite direction around {pitch_name(int(round(median)))}; "
        "rhythm and velocities are untouched."
    )


def variant_rhythm(notes: list, ctx: dict) -> tuple:
    grid = ctx["grid"]
    parity = ctx["parity"]
    end_beat = ctx["end_beat"]
    out = sorted(_copy_notes(notes), key=lambda n: (float(n["beat"]), int(n["note"])))
    shifted = 0
    lengthened = 0
    for index, note in enumerate(out):
        beat = float(note["beat"])
        if index % 2 == parity:
            new_beat = beat + grid
            if new_beat + 0.03 < end_beat:
                note["beat"] = round(new_beat, 4)
                shifted += 1
        duration = float(note["duration"])
        if duration >= 0.5:
            note["duration"] = round(min(duration * 1.5, end_beat - float(note["beat"])), 4)
            lengthened += 1
    grid_name = {1.0: "quarter", 0.5: "eighth", 0.25: "sixteenth", 0.125: "thirty-second"}.get(grid, f"{grid}-beat")
    return out, "Busier rhythm, same notes", (
        f"Every other onset ({shifted} of {len(out)}) is pushed one {grid_name} later and "
        f"{lengthened} sustained notes are held 50% longer; pitches are unchanged."
    )


def variant_density(notes: list, ctx: dict) -> tuple:
    ordered = sorted(notes, key=lambda n: (float(n["beat"]), int(n["note"])))
    on_beat = [n for n in ordered if abs(float(n["beat"]) - round(float(n["beat"]))) < 1e-6]
    if len(on_beat) < 2:
        threshold = float(np.median([float(n["velocity"]) for n in ordered]))
        on_beat = [n for n in ordered if float(n["velocity"]) >= threshold]
    kept = _copy_notes(on_beat)
    echo = []
    for index, source in enumerate(ordered[:2]):
        beat = float(source["beat"]) + 2.0
        if beat >= ctx["end_beat"]:
            continue
        copy = deepcopy(source)
        copy["id"] = f"{ctx['track_id']}-echo-{index}"
        copy["beat"] = round(beat, 4)
        copy["note"] = snap_to_key(int(source["note"]) + 12, ctx["scale"])
        copy["velocity"] = round(float(source["velocity"]) * 0.55, 4)
        copy["trackId"] = ctx["track_id"]
        echo.append(copy)
    return kept + echo, "Sparser, with an octave echo", (
        f"Thinned to the strongest beats ({len(kept)} of {len(ordered)} notes kept) and the "
        f"hook's first two notes answer an octave up, half a bar later, at 55% velocity."
    )


def variant_range(notes: list, ctx: dict) -> tuple:
    out = _copy_notes(notes)
    top = max(int(n["note"]) for n in out)
    shift = 12 if top + 12 <= 108 else -12
    for note in out:
        note["note"] = snap_to_key(int(note["note"]) + shift, ctx["scale"])
        note["velocity"] = round(float(note["velocity"]) * 0.75, 4)
    direction = "up" if shift > 0 else "down"
    label = "Higher and softer" if shift > 0 else "Lower and softer"
    return out, label, (
        f"The whole phrase moved {direction} an octave and every velocity pulled back by 25%."
    )


MELODIC_RECIPES: list = [
    ("contour", variant_contour),
    ("rhythm", variant_rhythm),
    ("density", variant_density),
    ("range", variant_range),
]


# --- Drum variants -----------------------------------------------------------


def variant_offbeat(track: dict, ctx: dict) -> tuple:
    steps = sorted(set(int(s) % 16 for s in (track.get("steps") or [])))
    new_steps = sorted(set(steps) | {2, 6, 10, 14})
    return {"steps": new_steps}, "Off-beat hats added", (
        f"Steps 2, 6, 10 and 14 switched on ({len(new_steps) - len(steps)} new hits per bar) for an "
        "off-beat eighth pulse; the step pattern is per-track so it plays wherever this pattern does."
    )


def variant_halftime(track: dict, ctx: dict) -> tuple:
    steps = sorted(set(int(s) % 16 for s in (track.get("steps") or [])))
    backbeats = [s for s in steps if s % 8 == 4]
    if len(backbeats) >= 2:
        removed = [s for s in backbeats if s % 16 == 12]
    else:
        removed = steps[1::2]
    new_steps = [s for s in steps if s not in removed]
    return {"steps": new_steps}, "Half-time feel", (
        f"Every second backbeat dropped (steps {', '.join(str(s) for s in removed) or 'none'}), "
        "so the snare lands once a bar instead of twice; the step pattern is per-track so it "
        "applies wherever this pattern plays."
    )


def variant_fill(track: dict, ctx: dict) -> tuple:
    track_id = ctx["track_id"]
    last_bar = ctx["start_bar"] + ctx["bars"] - 1
    pitch = percussion_pitch(track)
    fill_notes = []
    for index, step in enumerate((12, 13, 14, 15)):
        fill_notes.append({
            "id": f"{track_id}-fill-{last_bar}-{step}",
            "beat": round(last_bar * BEATS_PER_BAR + step / 4.0, 4),
            "duration": 0.25,
            "note": pitch,
            "velocity": round(0.7 + 0.1 * index, 4),
            "color": str(track.get("color") or "#ffffff"),
            "trackId": track_id,
        })
    clip = {
        "id": f"{track_id}-{last_bar}-fill",
        "name": f"{ctx['section_label']} fill",
        "startBar": last_bar,
        "bars": 1,
        "lane": track_id,
        "color": str(track.get("color") or "#ffffff"),
        "type": "pattern",
    }
    return {"notes": fill_notes, "clip": clip}, "Fill into the next section", (
        f"Four sixteenth hits (steps 12-15, rising velocity) written as notes on bar {last_bar + 1} "
        "with a one-bar fill clip, because the step grid cannot vary per bar."
    )


DRUM_RECIPES: list = [
    ("offbeat", variant_offbeat),
    ("halftime", variant_halftime),
    ("fill", variant_fill),
]


# --- Automation variants -----------------------------------------------------


def lane_value_at(lane: dict, bar: float) -> float:
    points = sorted(
        ((float(p.get("bar", 0)), float(p.get("value", 0.5))) for p in (lane.get("points") or []) if isinstance(p, dict)),
    )
    if not points:
        return 0.5
    if bar <= points[0][0]:
        return points[0][1]
    if bar >= points[-1][0]:
        return points[-1][1]
    for (b0, v0), (b1, v1) in zip(points, points[1:]):
        if b0 <= bar <= b1:
            if b1 == b0:
                return v1
            return v0 + (v1 - v0) * (bar - b0) / (b1 - b0)
    return points[-1][1]


def lane_with_endpoints(lane: dict, start_bar: int, end_bar: int) -> dict:
    """A copy of the lane that has explicit points at both ends of the window."""
    out = deepcopy(lane)
    points = [p for p in (out.get("points") or []) if isinstance(p, dict)]
    for bar in (start_bar, end_bar):
        if not any(abs(float(p.get("bar", -1)) - bar) < 1e-6 for p in points):
            points.append({"bar": bar, "value": round(lane_value_at(lane, bar), 4)})
    out["points"] = sorted(points, key=lambda p: float(p.get("bar", 0)))
    return out


def _move_endpoints(lane: dict, start_bar: int, end_bar: int, start_delta: float, end_delta: float, curve: str) -> tuple:
    out = lane_with_endpoints(lane, start_bar, end_bar)
    changed = 0
    for point in out["points"]:
        bar = float(point.get("bar", 0))
        delta = start_delta if abs(bar - start_bar) < 1e-6 else end_delta if abs(bar - end_bar) < 1e-6 else 0.0
        if delta:
            before = float(point.get("value", 0.5))
            point["value"] = round(clamp(before + delta, 0.0, 1.0), 4)
            changed += 1 if abs(point["value"] - before) > 1e-9 else 0
    if out.get("curve") != curve:
        out["curve"] = curve
        changed += 1
    return out, changed


def variant_auto_open(lane: dict, ctx: dict) -> tuple:
    out, changed = _move_endpoints(lane, ctx["start_bar"], ctx["end_bar"], 0.0, 0.25, "ease-in")
    return out, changed, "Opens further", (
        f"{lane.get('label') or lane.get('parameter')} ends 0.25 higher at bar {ctx['end_bar']} "
        "on an ease-in curve, so the sweep arrives with more of a push."
    )


def variant_auto_hold(lane: dict, ctx: dict) -> tuple:
    out, changed = _move_endpoints(lane, ctx["start_bar"], ctx["end_bar"], -0.25, 0.0, "ease-out")
    return out, changed, "Starts lower, same arrival", (
        f"{lane.get('label') or lane.get('parameter')} starts 0.25 lower at bar {ctx['start_bar']} "
        "and eases out to the same end value, so the section opens more gradually."
    )


def variant_auto_steep(lane: dict, ctx: dict) -> tuple:
    out, changed = _move_endpoints(lane, ctx["start_bar"], ctx["end_bar"], -0.25, 0.25, "linear")
    return out, changed, "Steeper sweep", (
        f"{lane.get('label') or lane.get('parameter')} starts 0.25 lower and ends 0.25 higher "
        "on a straight line, so the movement across the section is twice as obvious."
    )


AUTOMATION_RECIPES: list = [
    ("open", variant_auto_open),
    ("hold", variant_auto_hold),
    ("steep", variant_auto_steep),
]


# --- Building variants -------------------------------------------------------


def choose_recipes(recipes: list, count: int, rng: np.random.Generator) -> list:
    """Pick ``count`` recipes; past the catalogue, pairs are composed."""
    order = [recipes[i] for i in rng.permutation(len(recipes))]
    chosen = list(order[:count])
    pairs = [(a, b) for i, a in enumerate(order) for b in order[i + 1:]]
    for pair in pairs:
        if len(chosen) >= count:
            break
        chosen.append(pair)
    while len(chosen) < count:
        chosen.append(order[len(chosen) % len(order)])
    return chosen[:count]


def strip_target_audio(project: dict, track: dict) -> None:
    """Silence the old stem so the preview (and the app) play the edited lane.

    The stem was rendered from the notes the lane used to have; leaving it in
    place means the variation is inaudible. Assets are the second place the
    renderer looks, so they go too.
    """
    track["file"] = None
    track_id = str(track.get("id", ""))
    assets = project.get("assets")
    if isinstance(assets, list):
        project["assets"] = [a for a in assets if not (isinstance(a, dict) and a.get("trackId") == track_id)]


def build_melodic_variant(project: dict, track: dict, ctx: dict, recipe: Any, base_notes: list) -> tuple:
    variant = deepcopy(project)
    snapshot = variant["snapshot"]
    track_id = ctx["track_id"]
    start_beat, end_beat = ctx["start_beat"], ctx["end_beat"]

    steps = recipe if isinstance(recipe, tuple) and isinstance(recipe[0], tuple) else (recipe,)
    notes = _copy_notes(base_notes)
    labels, descriptions = [], []
    for _, fn in steps:
        notes, label, description = fn(notes, ctx)
        labels.append(label)
        descriptions.append(description)
    for index, note in enumerate(notes):
        note["id"] = f"{track_id}-{ctx['slug']}-{ctx['variant_id']}-{index}"
        note["trackId"] = track_id
        note["beat"] = round(clamp(float(note["beat"]), start_beat, end_beat - 0.03), 4)
        note["duration"] = round(max(0.03, min(float(note["duration"]), end_beat - float(note["beat"]))), 4)
        note["velocity"] = round(clamp(float(note["velocity"]), 0.05, 1.0), 4)
    notes.sort(key=lambda n: (float(n["beat"]), int(n["note"])))

    kept = [
        n for n in (snapshot.get("notes") or [])
        if not (isinstance(n, dict) and note_owner(n, snapshot) == track_id and start_beat <= float(n.get("beat", 0)) < end_beat)
    ]
    snapshot["notes"] = kept + notes

    new_track = next(t for t in snapshot["tracks"] if isinstance(t, dict) and str(t.get("id", "")) == track_id)
    strip_target_audio(variant, new_track)

    original_sigs = {note_signature(n) for n in ctx["original_notes"]}
    changed = len(original_sigs ^ {note_signature(n) for n in notes})
    label = " + ".join(labels) if len(labels) > 1 else labels[0]
    if ctx.get("seed_note"):
        description = ctx["seed_note"] + " " + " Then: ".join(descriptions)
        label = f"{label} (seeded phrase)"
    else:
        description = " Then: ".join(descriptions)
    return variant, label, description, {"notes": changed, "steps": 0, "automation": 0}


def build_drum_variant(project: dict, track: dict, ctx: dict, recipe: Any) -> tuple:
    variant = deepcopy(project)
    snapshot = variant["snapshot"]
    track_id = ctx["track_id"]
    new_track = next(t for t in snapshot["tracks"] if isinstance(t, dict) and str(t.get("id", "")) == track_id)

    steps = recipe if isinstance(recipe, tuple) and isinstance(recipe[0], tuple) else (recipe,)
    labels, descriptions = [], []
    before_steps = set(int(s) % 16 for s in (track.get("steps") or []))
    notes_added = 0
    for _, fn in steps:
        patch, label, description = fn(new_track, ctx)
        labels.append(label)
        descriptions.append(description)
        if "steps" in patch:
            new_track["steps"] = list(patch["steps"])
        if "notes" in patch:
            snapshot["notes"] = list(snapshot.get("notes") or []) + patch["notes"]
            notes_added += len(patch["notes"])
        if "clip" in patch:
            new_track["clips"] = list(new_track.get("clips") or []) + [patch["clip"]]
    strip_target_audio(variant, new_track)
    after_steps = set(int(s) % 16 for s in (new_track.get("steps") or []))
    label = " + ".join(labels) if len(labels) > 1 else labels[0]
    return variant, label, " Then: ".join(descriptions), {
        "notes": notes_added, "steps": len(before_steps ^ after_steps), "automation": 0,
    }


def build_automation_variant(project: dict, track: dict, ctx: dict, recipe: Any, lanes: list) -> tuple:
    variant = deepcopy(project)
    snapshot = variant["snapshot"]
    steps = recipe if isinstance(recipe, tuple) and isinstance(recipe[0], tuple) else (recipe,)
    lane_ids = {str(lane.get("id", "")) for lane in lanes}
    all_lanes = [lane for lane in (snapshot.get("automationLanes") or []) if isinstance(lane, dict)]
    labels, descriptions = [], []
    changed_total = 0
    for _, fn in steps:
        rebuilt = []
        for lane in all_lanes:
            if str(lane.get("id", "")) in lane_ids:
                lane, changed, label, description = fn(lane, ctx)
                changed_total += changed
                if label not in labels:
                    labels.append(label)
                descriptions.append(description)
            rebuilt.append(lane)
        all_lanes = rebuilt
    if ctx.get("created_lane"):
        descriptions.insert(0, ctx["created_lane"])
    snapshot["automationLanes"] = all_lanes
    label = " + ".join(labels) if len(labels) > 1 else labels[0]
    return variant, label, " ".join(descriptions), {"notes": 0, "steps": 0, "automation": changed_total}


def generate_variations(
    root: Path,
    project: dict,
    track_ref: str,
    section_text: str,
    count: int = 3,
    seed: int = 7,
    output_dir: Optional[Path] = None,
    render: bool = True,
) -> dict:
    snapshot = project["snapshot"]
    track = find_track(snapshot, track_ref)
    track_id = str(track.get("id", ""))
    start_bar, bars, section_label = resolve_section(snapshot, track, section_text)
    end_bar = start_bar + bars
    start_beat, end_beat = float(start_bar * BEATS_PER_BAR), float(end_bar * BEATS_PER_BAR)
    bpm = float(snapshot.get("bpm") or 120) or 120.0

    notes = track_notes(snapshot, track_id)
    lanes = track_lanes(snapshot, track_id)
    kind = lane_kind(track, notes, lanes)
    if count < 1:
        raise ValueError("--count must be at least 1.")

    project_id = str(project.get("id") or "project")
    if output_dir is None:
        output_dir = root / "songlab" / "projects" / project_id / "variations"
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(section_text)
    rng = np.random.default_rng(int(seed))

    ctx: dict = {
        "track_id": track_id,
        "slug": slug,
        "start_bar": start_bar,
        "end_bar": end_bar,
        "bars": bars,
        "start_beat": start_beat,
        "end_beat": end_beat,
        "section_label": section_label,
        "scale": parse_key(project.get("keyCenter")),
        "grid": SNAP_BEATS.get(str(snapshot.get("snap") or "1/16"), 0.25),
        "parity": int(rng.integers(0, 2)),
    }

    color = str(track.get("color") or "#ffffff")
    variations = []

    if kind == "melodic":
        section_notes = [n for n in notes if start_beat <= float(n.get("beat", 0)) < end_beat]
        ctx["original_notes"] = section_notes
        if section_notes:
            base_notes = [dict(deepcopy(n), trackId=track_id) for n in section_notes]
        elif notes:
            base_notes = seed_from_motif(track_id, notes, start_beat, end_beat, color)
            ctx["seed_note"] = (
                f"The lane had no notes in bars {start_bar + 1}-{end_bar}, so its existing phrase "
                f"was repeated across the section first ({len(base_notes)} notes)."
            )
        else:
            base_notes = seed_from_key(track_id, ctx["scale"], start_beat, end_beat, color)
            ctx["seed_note"] = (
                f"The lane had no notes at all, so a starter phrase (root, fifth, third, octave) from "
                f"{project.get('keyCenter') or 'C major'} was written across the section first ({len(base_notes)} notes)."
            )
        recipes = choose_recipes(MELODIC_RECIPES, count, rng)
        for index, recipe in enumerate(recipes, start=1):
            ctx["variant_id"] = f"v{index}"
            variations.append(build_melodic_variant(project, track, ctx, recipe, base_notes))
    elif kind == "drums":
        recipes = choose_recipes(DRUM_RECIPES, count, rng)
        for index, recipe in enumerate(recipes, start=1):
            ctx["variant_id"] = f"v{index}"
            variations.append(build_drum_variant(project, track, ctx, recipe))
    else:
        if not lanes and str(track.get("kind") or "").lower() == "automation":
            # An automation-kind track without lanes of its own is the visual
            # host for the project's macros; vary the ones that cross the window.
            lanes = [
                lane for lane in (snapshot.get("automationLanes") or [])
                if isinstance(lane, dict) and any(
                    start_bar <= float(p.get("bar", -1)) <= end_bar for p in (lane.get("points") or []) if isinstance(p, dict)
                )
            ]
        if not lanes:
            starter = {
                "id": f"auto-{track_id}-{slug}",
                "trackId": track_id,
                "parameter": "filter",
                "label": f"{track.get('name') or track_id} Filter",
                "color": color,
                "curve": "ease-in",
                "enabled": True,
                "points": [{"bar": start_bar, "value": 0.3}, {"bar": end_bar, "value": 0.8}],
            }
            project = deepcopy(project)
            project["snapshot"]["automationLanes"] = list(project["snapshot"].get("automationLanes") or []) + [starter]
            lanes = [starter]
            ctx["created_lane"] = (
                f"The lane had no automation, so a filter sweep from 0.3 to 0.8 across bars "
                f"{start_bar + 1}-{end_bar} was created first."
            )
        recipes = choose_recipes(AUTOMATION_RECIPES, count, rng)
        for index, recipe in enumerate(recipes, start=1):
            ctx["variant_id"] = f"v{index}"
            variations.append(build_automation_variant(project, track, ctx, recipe, lanes))

    results = []
    for index, (variant, label, description, changes) in enumerate(variations, start=1):
        stem = f"{track_id}-{slug}-v{index}"
        project_path = output_dir / f"{stem}.neon.json"
        project_path.write_text(
            json.dumps(variant, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        preview_path: Optional[Path] = None
        if render:
            preview_path = output_dir / f"{stem}.wav"
            mix, sample_rate, _ = mix_project(root, variant, start_bar=start_bar, bars=bars, solo_track=track_id)
            write_wav(preview_path, mix, sample_rate)
        results.append({
            "id": f"v{index}",
            "label": label,
            "description": description,
            "project": str(project_path),
            "preview": str(preview_path) if preview_path else None,
            "changes": changes,
        })

    result: dict = {
        "ok": True,
        "target": {
            "trackId": track_id,
            "trackName": str(track.get("name") or track_id),
            "section": section_label,
            "startBar": start_bar,
            "bars": bars,
            "laneKind": kind,
            "bpm": bpm,
            "previewSeconds": round(bars * BEATS_PER_BAR * 60.0 / bpm, 3),
        },
        "previewNote": PREVIEW_NOTE,
        "variations": results,
    }
    if kind == "automation":
        # Be honest about what the ear will get: the mixdown renderer ignores
        # automation lanes, so these previews only show the window in context.
        result["previewCaveat"] = (
            "The preview renderer does not apply automation lanes, so these previews sound "
            "like the original; compare the lane values in the project files."
        )
    return result


# --- CLI ---------------------------------------------------------------------


def render_markdown(result: dict) -> str:
    target = result["target"]
    lines = [
        f"# Variations for {target['trackName']} ({target['trackId']}) in {target['section']}",
        "",
        f"Bars {target['startBar'] + 1}-{target['startBar'] + target['bars']} "
        f"({target['bars']} bars, {target['previewSeconds']}s at {target['bpm']:g} BPM), lane kind: {target['laneKind']}.",
        "",
        f"_{result['previewNote']}_",
        "",
    ]
    if result.get("previewCaveat"):
        lines.extend([f"_{result['previewCaveat']}_", ""])
    for variation in result["variations"]:
        changes = variation["changes"]
        lines.append(f"## {variation['id']}: {variation['label']}")
        lines.append("")
        lines.append(variation["description"])
        lines.append("")
        lines.append(
            f"- Changes: {changes['notes']} notes, {changes['steps']} steps, {changes['automation']} automation points"
        )
        lines.append(f"- Project: `{variation['project']}`")
        if variation.get("preview"):
            lines.append(f"- Preview: `{variation['preview']}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a few alternatives for one lane in one section.")
    parser.add_argument("--root", required=True, help="Workspace root (holds exports/ and songlab/).")
    parser.add_argument("--project", required=True, help="Path to the .neon.json project file.")
    parser.add_argument("--track-id", required=True, help="Track id (or name) to vary.")
    parser.add_argument("--section", required=True, help="Section name (\"Drop\", \"Second Drop\") or bar range (\"24-40\").")
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output-dir", default=None, help="Defaults to songlab/projects/<id>/variations/ under --root.")
    parser.add_argument("--no-render", action="store_true", help="Write the variant projects but skip the previews.")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args(argv)

    try:
        root = Path(args.root).expanduser().resolve()
        project = load_project(Path(args.project).expanduser().resolve())
        result = generate_variations(
            root,
            project,
            args.track_id,
            args.section,
            count=args.count,
            seed=args.seed,
            output_dir=Path(args.output_dir).expanduser().resolve() if args.output_dir else None,
            render=not args.no_render,
        )
    except (ValueError, RuntimeError, OSError, KeyError) as error:
        message = str(error) or error.__class__.__name__
        if args.format == "markdown":
            print(f"Error: {message}")
        else:
            print(json.dumps({"ok": False, "error": message}))
        return 1

    if args.format == "markdown":
        print(render_markdown(result))
    else:
        print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
