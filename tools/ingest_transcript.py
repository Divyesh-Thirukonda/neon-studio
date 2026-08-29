#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


SECTION_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("pre_intro", "Pre-Intro", ("pre intro", "pre-intro")),
    ("intro", "Intro", ("intro", "starts out", "first sound", "beginning of the whole project")),
    ("verse", "Verse", ("verse",)),
    ("pre_build", "Pre-Build", ("pre-build", "pre build", "bridge", "hype pre-build", "hype pre build")),
    ("build", "Build", ("build up", "buildup", "build", "riser", "rises up into this next")),
    ("drop", "Drop", ("drop", "first drop")),
    ("second_drop", "Second Drop", ("second drop", "drop two", "final drop")),
    ("break", "Break", ("break", "mid-song break", "middle section")),
    ("outro", "Outro", ("outro", "the end", "end of the song")),
)

TRACK_KEYWORDS: dict[str, tuple[str, ...]] = {
    "lead": ("lead", "lead line", "drop lead", "square lead", "hook", "melody"),
    "chords": ("chord", "chords", "progression", "supersaw"),
    "bass": ("bass", "base", "mid bass", "drop bass", "fat bass"),
    "sub": ("sub", "sub bass"),
    "drums": ("drums", "drum", "trap beat", "drum beat"),
    "kick": ("kick", "kick drum"),
    "snare": ("snare", "snare drum"),
    "clap": ("clap", "claps", "clap stack"),
    "hat": ("hi-hat", "hihat", "hat", "hats"),
    "ride": ("ride",),
    "crash": ("crash", "crashes"),
    "vocal": ("vocal", "vocals", "vocal chop", "tag"),
    "guitar": ("guitar", "guitar bass"),
    "pluck": ("pluck", "plucks"),
    "pad": ("pad", "pads"),
    "noise": ("white noise", "noise sweep", "noise up"),
    "riser": ("riser", "risers", "uplifter"),
    "downlifter": ("down lifter", "downlifter"),
    "impact": ("impact", "impacts"),
    "crowd": ("crowd", "air bed", "air"),
    "reverse": ("reverse", "reversed"),
    "automation": ("automation", "filter automated", "automated filter", "macro"),
    "fx": ("fx", "effect", "ear candy", "filler", "sirens", "laser", "breaths"),
    "sample": ("sample", "sampler"),
}

PLUGIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Serum": ("serum",),
    "Omnisphere": ("omnisphere",),
    "EQ Eight": ("eq eight", "eq8", "graphic eq"),
    "OTT": ("ott",),
    "Crystalline": ("crystalline",),
    "Transit": ("transit", "transit 2"),
    "Fresh Air": ("fresh air",),
    "Snap Heap": ("snap heap", "snapheap"),
    "Kilohearts": ("kilohearts",),
    "Melda Wave Shaper": ("wave shaper", "waveshaper", "melda"),
    "Valhalla Room": ("valhalla room",),
    "VintageVerb": ("vintage verb", "vintageverb"),
    "Soothe": ("soothe",),
    "Operator": ("operator",),
    "Rave Generator": ("rave generator",),
    "Baby Audio": ("baby audio",),
    "Pultec": ("pultec", "p tech", "po tech"),
    "Serum FX": ("serum fx",),
    "PolySaturator": ("polysaturator",),
    "Humanoid": ("humanoid",),
    "Valhalla": ("valhalla",),
    "Slate Fresh Air": ("slate", "fresh air"),
}

TECHNIQUE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "layering": ("layer", "layered", "double", "stack"),
    "sidechain": ("side chain", "sidechain", "duck"),
    "eq": ("eq", "low cut", "high pass", "highpass", "cut out", "boost"),
    "compression": ("compress", "compression", "multiband", "ott"),
    "reverb": ("reverb", "room", "tail"),
    "delay": ("delay", "ping pong", "ping-pong", "bounce left and right"),
    "distortion": ("distortion", "drive", "clipper", "saturator", "saturation"),
    "filtering": ("filter", "lowpass", "highpass", "cutoff"),
    "automation": ("automation", "automated", "macro", "sweep"),
    "resampling": ("rendered out", "freeze", "flatten", "resample"),
    "pitching": ("pitch", "pitched", "autotune"),
    "stereo": ("stereo", "mono", "spread", "left and right", "mid side", "midside"),
    "reverse": ("reverse", "reversed"),
    "call_response": ("call response", "call-response"),
    "tease_hook": ("tease", "teaser lead", "sneak this little guy in"),
    "arrangement_reuse": ("same notes", "same melody", "filled in", "loop that same"),
}

MIX_KEYWORDS = ("eq", "reverb", "delay", "compress", "compression", "bright", "wide", "stereo", "mono", "low end", "sidechain", "distortion", "saturat")
AUTOMATION_KEYWORDS = ("automation", "automated", "filter", "macro", "riser", "downlifter", "sweep", "transition")
ARRANGEMENT_KEYWORDS = ("intro", "verse", "build", "drop", "second drop", "break", "outro", "loop", "same melody", "same notes", "filled in")

ORDINAL_WORDS: dict[str, int] = {
    "one": 1,
    "first": 1,
    "two": 2,
    "second": 2,
    "three": 3,
    "third": 3,
    "four": 4,
    "fourth": 4,
}

LANE_ALIASES: dict[str, tuple[str, ...]] = {
    "lead": ("lead", "melody", "hook"),
    "bass": ("bass", "base", "mid bass"),
    "sub": ("sub", "sub bass"),
    "chords": ("chords", "chord", "progression", "supersaw", "pad"),
    "fx": ("fx", "effect", "effects"),
    "vocal": ("vocal", "vocals", "vocal chop", "tag"),
    "guitar": ("guitar",),
    "pluck": ("pluck", "plucks"),
    "sample": ("sample", "sampler"),
    "automation": ("automation", "filter", "cutoff", "macro"),
    "drums": ("drums", "drum", "beat"),
    "kick": ("kick", "kicks", "kick drum", "kick drums"),
    "snare": ("snare", "snares", "snare drum", "snare drums"),
    "clap": ("clap", "claps", "clap stack", "clap stacks"),
    "hat": ("hat", "hats", "hi-hat", "hi-hats", "hihat", "hihats"),
    "ride": ("ride", "rides"),
    "crash": ("crash", "crashes"),
}

CHORD_SYMBOL_RE = re.compile(
    r"\b([A-G](?:#|b)?(?:maj9|maj7|min9|min7|min|m9|m7|m|add9|sus2|sus4|dim|aug|9|7|5)?)\b"
)

NOTE_TO_SEMITONE: dict[str, int] = {
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

SEMITONE_TO_NOTE = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned[:72] or "song-project"


def timecode_to_seconds(value: str) -> int:
    parts = [int(part) for part in value.split(":")]
    if len(parts) == 2:
        minutes, seconds = parts
        return minutes * 60 + seconds
    hours, minutes, seconds = parts
    return hours * 3600 + minutes * 60 + seconds


def seconds_to_timecode(value: int) -> str:
    minutes, seconds = divmod(max(0, value), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def strip_spoken_timestamp_prefix(text: str) -> str:
    patterns = (
        r"^\d+\s*seconds?",
        r"^\d+\s*secondss?",
        r"^\d+\s*minutes?,\s*\d+\s*seconds?",
        r"^\d+\s*minute,\s*\d+\s*seconds?",
    )
    cleaned = text.strip()
    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip(" ,-")
    return cleaned


def first_sentences(text: str, limit: int = 2) -> str:
    pieces = re.split(r"(?<=[.!?])\s+", normalize_space(text))
    summary = " ".join(piece for piece in pieces[:limit] if piece)
    summary = summary or normalize_space(text)
    return summary[:280]


def extract_matches(text: str, table: dict[str, tuple[str, ...]]) -> list[str]:
    lowered = text.lower()
    found: list[str] = []
    for canonical, keywords in table.items():
        if any(keyword in lowered for keyword in keywords):
            found.append(canonical)
    return sorted(found)


def deep_copy_jsonish(value: Any) -> Any:
    return json.loads(json.dumps(value))


def canonical_lane(value: str) -> str | None:
    lowered = normalize_space(value).lower()
    for lane, aliases in LANE_ALIASES.items():
        if lowered == lane or lowered in aliases:
            return lane
    return None


def parse_ordinal_token(value: str) -> int | None:
    lowered = normalize_space(value).lower()
    if lowered.isdigit():
        return int(lowered)
    return ORDINAL_WORDS.get(lowered)


def extract_section_reference_descriptor(text: str) -> dict[str, Any] | None:
    lowered = text.lower()
    for pattern, section_type in (
        (r"(?:drop\s+(\d+|one|two|three|four)|(?:first|second|third|fourth)\s+drop)", "drop"),
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
        match = re.search(pattern, lowered)
        if not match:
            continue
        ordinal: int | None = None
        if match.groups():
            ordinal = parse_ordinal_token(next((group for group in match.groups() if group), ""))
        elif section_type == "drop":
            if "first drop" in lowered:
                ordinal = 1
            elif "second drop" in lowered:
                ordinal = 2
            elif "third drop" in lowered:
                ordinal = 3
        return {"sectionType": section_type, "ordinal": ordinal}
    return None


def resolve_section_reference(
    descriptor: dict[str, Any] | None,
    prior_sections: list[dict[str, Any]],
    *,
    roles: tuple[str, ...] = (),
) -> dict[str, Any] | None:
    if descriptor:
        section_type = descriptor.get("sectionType")
        ordinal = descriptor.get("ordinal")
        matches = [section for section in prior_sections if section.get("type") == section_type]
        if ordinal is not None:
            for section in matches:
                if section.get("ordinalWithinType") == ordinal:
                    return section
        if matches:
            return matches[-1]
    if roles:
        role_set = set(roles)
        for section in reversed(prior_sections):
            if role_set & set(section.get("trackRoles", [])):
                return section
    return prior_sections[-1] if prior_sections else None


def reference_payload(
    descriptor: dict[str, Any] | None,
    resolved: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not descriptor and not resolved:
        return None
    payload: dict[str, Any] = {}
    if resolved:
        payload["sectionId"] = resolved["id"]
        payload["sectionType"] = resolved["type"]
        if resolved.get("ordinalWithinType"):
            payload["ordinal"] = resolved["ordinalWithinType"]
    elif descriptor:
        payload["sectionType"] = descriptor.get("sectionType")
        if descriptor.get("ordinal") is not None:
            payload["ordinal"] = descriptor["ordinal"]
    return payload or None


def resolve_reference_payload(reference: dict[str, Any] | None, prior_sections: list[dict[str, Any]]) -> dict[str, Any] | None:
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


def parse_transpose_instruction(text: str) -> int:
    lowered = text.lower()
    if "down an octave" in lowered:
        return -12
    if "up an octave" in lowered:
        return 12
    match = re.search(r"transpose\s*([+-]\d+)\b", lowered)
    if match:
        return int(match.group(1))
    match = re.search(r"(?:transpose|transposed|pitched?)\s+(up|down)\s+(\d+)\s*(?:semi(?:tone)?s?|st)\b", lowered)
    if match:
        return int(match.group(2)) if match.group(1) == "up" else -int(match.group(2))
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
    return round(raw - 1.0, 2) if raw >= 1.0 else round(raw, 2)


def parse_beat_list(fragment: str) -> list[float]:
    lowered = fragment.lower()
    if "offbeat" in lowered or "off beat" in lowered or "off-beat" in lowered:
        return [0.5, 1.5, 2.5, 3.5]
    beats: list[float] = []
    for token in re.findall(r"\d(?:\.\d+)?", lowered):
        parsed = parse_beat_value(token)
        if parsed is not None:
            beats.append(parsed)
    return beats


def extract_omit_beats(fragment: str) -> list[float]:
    omitted: list[float] = []
    for pattern in (
        r"(?:skip|omit|mute|rest)(?:\s+beats?)?\s+([^|;]+)",
        r"rest@(\d(?:\.\d+)?)",
    ):
        for match in re.finditer(pattern, fragment.lower()):
            text = match.group(1)
            omitted.extend(parse_beat_list(text))
    deduped: list[float] = []
    for beat in omitted:
        marker = round(float(beat), 2)
        if marker not in deduped:
            deduped.append(marker)
    return deduped


def filter_events_by_omit_beats(events: list[dict[str, Any]], omit_beats: list[float]) -> list[dict[str, Any]]:
    if not events or not omit_beats:
        return events
    omitted = {round(float(beat), 2) for beat in omit_beats}
    return [event for event in events if round(float(event.get("beat", -999.0)), 2) not in omitted]


def extract_curve(fragment: str) -> str:
    lowered = fragment.lower()
    if "ease-in-out" in lowered or "ease in out" in lowered:
        return "ease_in_out"
    if "ease-in" in lowered or "ease in" in lowered:
        return "ease_in"
    if "ease-out" in lowered or "ease out" in lowered:
        return "ease_out"
    if "exponential" in lowered or re.search(r"\bexp\b", lowered):
        return "exp"
    if "step" in lowered or "stepped" in lowered:
        return "step"
    return "linear"


def extract_compact_event_attributes(suffix: str, *, lane: str) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    normalized = suffix.strip().lower()
    if not normalized:
        return attrs
    if "!" in normalized:
        attrs["accent"] = True
    if "g" in normalized:
        attrs["ghost"] = True
    if lane == "hat" and "o" in normalized:
        attrs["open"] = True
    duration_match = re.search(r"/\s*(\d(?:\.\d+)?)", normalized)
    if duration_match:
        attrs["duration"] = round(float(duration_match.group(1)), 2)
    gain_match = re.search(r"[*x]\s*([0-9]+(?:\.[0-9]+)?)", normalized)
    if gain_match:
        gain = normalize_level(gain_match.group(1))
        if gain is not None:
            attrs["gain"] = gain
    pan_match = re.search(r"p(-?[0-9]+(?:\.[0-9]+)?)", normalized)
    if pan_match:
        try:
            attrs["pan"] = round(max(-1.0, min(1.0, float(pan_match.group(1)))), 2)
        except ValueError:
            pass
    return attrs


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


def note_name_to_midi(token: str) -> int | None:
    match = re.match(r"^([A-G](?:#|b)?)(-?\d+)$", normalize_space(token))
    if not match:
        return None
    note_name, octave_text = match.groups()
    semitone = NOTE_TO_SEMITONE.get(note_name)
    if semitone is None:
        return None
    octave = int(octave_text)
    return (octave + 1) * 12 + semitone


def midi_to_note_name(midi_note: int) -> str:
    octave = midi_note // 12 - 1
    note_name = SEMITONE_TO_NOTE[midi_note % 12]
    return f"{note_name}{octave}"


def finalize_lane_events(
    timed_items: list[dict[str, Any]],
    *,
    lane: str,
    default_tail: float | None = None,
) -> list[dict[str, Any]]:
    if not timed_items:
        return []
    ordered = sorted(timed_items, key=lambda item: float(item["beat"]))
    if default_tail is None:
        default_tail = 0.7 if lane == "bass" else (0.45 if lane == "lead" else 0.9)
    min_gap = 0.28 if lane == "lead" else 0.45
    events: list[dict[str, Any]] = []
    for index, item in enumerate(ordered):
        next_beat = float(ordered[index + 1]["beat"]) if index + 1 < len(ordered) else None
        if next_beat is None:
            duration = default_tail
        else:
            gap = max(0.12, next_beat - float(item["beat"]))
            duration = min(max(min_gap, gap * 0.82), 1.6 if lane in {"bass", "chords"} else 0.9)
        event = deep_copy_jsonish(item)
        event["beat"] = round(float(item["beat"]), 2)
        event["duration"] = round(float(item.get("duration", duration)), 2)
        events.append(event)
    return events


def beats_to_events(beats: list[float], lane: str) -> list[dict[str, Any]]:
    if not beats:
        return []
    return finalize_lane_events([{"beat": float(beat)} for beat in beats], lane=lane)


def extract_note_events(fragment: str, lane: str) -> list[dict[str, Any]]:
    timed_items: list[dict[str, Any]] = []
    pattern = re.compile(r"\b([A-G](?:#|b)?-?\d+)\s*(?:@|on)\s*(\d(?:\.\d+)?)([^,\s|;]*)", flags=re.IGNORECASE)
    for note_token, beat_token, suffix in pattern.findall(fragment):
        midi_note = note_name_to_midi(note_token)
        beat = parse_beat_value(beat_token)
        if midi_note is None or beat is None:
            continue
        item = {"beat": beat, "note": midi_note, "noteName": note_token.upper()}
        item.update(extract_compact_event_attributes(suffix, lane=lane))
        timed_items.append(item)
    return finalize_lane_events(timed_items, lane=lane)


def extract_chord_events(fragment: str) -> list[dict[str, Any]]:
    timed_items: list[dict[str, Any]] = []
    pattern = re.compile(
        r"\b([A-G](?:#|b)?(?:maj9|maj7|min9|min7|min|m9|m7|m|add9|sus2|sus4|dim|aug|9|7|5)?)\s*(?:@|on)\s*(\d(?:\.\d+)?)([^,\s|;]*)",
        flags=re.IGNORECASE,
    )
    for symbol, beat_token, suffix in pattern.findall(fragment):
        beat = parse_beat_value(beat_token)
        if beat is None:
            continue
        item = {"beat": beat, "symbol": symbol}
        item.update(extract_compact_event_attributes(suffix, lane="chords"))
        timed_items.append(item)
    return finalize_lane_events(timed_items, lane="chords", default_tail=0.95)


def lower_join(*parts: Any) -> str:
    return " ".join(str(part).lower() for part in parts if part)


def merge_nested_payload(target: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = deep_copy_jsonish(target)
    for key, value in updates.items():
        if isinstance(value, list) and isinstance(merged.get(key), list):
            if key == "progressionSymbols":
                seen = list(merged[key])
                for item in value:
                    if item not in seen:
                        seen.append(item)
                merged[key] = seen
            else:
                seen_markers: set[str] = set()
                combined: list[Any] = []
                for item in list(merged[key]) + list(value):
                    marker = json.dumps(item, sort_keys=True)
                    if marker in seen_markers:
                        continue
                    seen_markers.add(marker)
                    combined.append(deep_copy_jsonish(item))
                merged[key] = combined
            continue
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_nested_payload(merged[key], value)
        else:
            merged[key] = deep_copy_jsonish(value)
    return merged


def record_lane_event(lane_events: dict[str, Any], lane: str, payload: dict[str, Any]) -> None:
    current = lane_events.get(lane, {})
    lane_events[lane] = merge_nested_payload(current, payload)


def normalize_level(value: str) -> float | None:
    try:
        parsed = float(value)
    except ValueError:
        return None
    if parsed > 1.0:
        parsed = parsed / 100.0
    return round(max(0.0, min(1.0, parsed)), 3)


def apply_bar_offsets(events: list[dict[str, Any]], bar_offsets: list[int] | None) -> list[dict[str, Any]]:
    if not bar_offsets:
        return events
    expanded: list[dict[str, Any]] = []
    for bar_offset in bar_offsets:
        for event in events:
            updated = dict(event)
            updated["barOffset"] = int(bar_offset)
            expanded.append(updated)
    return expanded


def extract_bar_scoped_segments(fragment: str) -> list[tuple[list[int] | None, str]]:
    pieces = [piece.strip(" ,") for piece in re.split(r"\s*\|\s*", fragment) if piece.strip(" ,")]
    if not pieces:
        return [(None, fragment)]
    scoped: list[tuple[list[int] | None, str]] = []
    any_scoped = False
    for piece in pieces:
        match = re.match(r"bars?\s+(\d+)(?:\s*-\s*(\d+))?\s*:?\s*(.+)$", piece, flags=re.IGNORECASE)
        if not match:
            scoped.append((None, piece))
            continue
        any_scoped = True
        start = int(match.group(1))
        end = int(match.group(2) or start)
        bar_offsets = list(range(max(1, start) - 1, max(start, end)))
        scoped.append((bar_offsets, match.group(3).strip()))
    return scoped if any_scoped else [(None, fragment)]


def extract_automation_envelopes(fragment: str, bar_offsets: list[int] | None) -> list[dict[str, Any]]:
    envelopes: list[dict[str, Any]] = []
    pattern = re.compile(
        r"(?:\b(lead|bass|sub|chords?|drums?|kick(?: drum)?s?|snare(?: drum)?s?|clap(?: stack)?s?|hi-hats?|hihats?|hats?|rides?|crashes?|fx|vocals?|guitar|plucks?|sample)\b\s*(?:[.:]\s*|\s+))?\b(filter|cutoff|macro|volume|reverb|delay|pan|width|distortion)\b.*?(?:from\s*)?([0-9]+(?:\.[0-9]+)?)\s*(?:to|->)\s*([0-9]+(?:\.[0-9]+)?)(?:\s*over\s*(\d+)\s*bars?)?([^|;]*)",
        flags=re.IGNORECASE,
    )
    for target_lane_token, parameter, start_text, end_text, bars_text, tail in pattern.findall(fragment):
        start = normalize_level(start_text)
        end = normalize_level(end_text)
        if start is None or end is None:
            continue
        envelope: dict[str, Any] = {
            "parameter": parameter.lower(),
            "start": start,
            "end": end,
            "curve": extract_curve(tail or fragment),
        }
        target_lane = canonical_lane(target_lane_token) if target_lane_token else None
        if target_lane:
            envelope["targetLane"] = target_lane
        if bar_offsets:
            envelope["barOffset"] = bar_offsets[0]
            envelope["bars"] = int(bars_text or len(bar_offsets))
        elif bars_text:
            envelope["barOffset"] = 0
            envelope["bars"] = int(bars_text)
        envelopes.append(envelope)
    return envelopes


def extract_progression_symbols(text: str) -> list[str]:
    symbols: list[str] = []
    for match in CHORD_SYMBOL_RE.finditer(text):
        symbol = match.group(1)
        # In free prose, tokens like E5 / G4 are usually note names with octave,
        # not power-chord symbols. Skip those here and let note-aware lane parsing handle them.
        if note_name_to_midi(symbol) is not None:
            continue
        symbols.append(symbol)
    deduped: list[str] = []
    for symbol in symbols[:8]:
        if not deduped or deduped[-1] != symbol:
            deduped.append(symbol)
    return deduped


def extract_phrase_transforms(fragment: str) -> list[str]:
    lowered = fragment.lower()
    transforms: list[str] = []
    if "mirror" in lowered:
        transforms.append("mirror")
    if "reverse" in lowered or "retrograde" in lowered:
        transforms.append("reverse")
    if "invert" in lowered or "inversion" in lowered:
        transforms.append("invert")
    return transforms


def extract_copy_source(prefix: str, current_lane: str, prior_sections: list[dict[str, Any]]) -> tuple[str, dict[str, Any] | None]:
    normalized = normalize_space(re.sub(r"^(?:from\s+the\s+|from\s+)", "", prefix, flags=re.IGNORECASE))
    source_lane = current_lane
    if normalized:
        candidates: list[tuple[str, str]] = []
        for lane, aliases in LANE_ALIASES.items():
            for alias in (lane, *aliases):
                candidates.append((alias, lane))
        for alias, lane in sorted(candidates, key=lambda item: len(item[0]), reverse=True):
            if re.search(rf"\b{re.escape(alias)}\b", normalized, flags=re.IGNORECASE):
                source_lane = lane
                break
    descriptor = extract_section_reference_descriptor(normalized)
    resolved = resolve_section_reference(descriptor, prior_sections, roles=(source_lane,))
    return source_lane, reference_payload(descriptor, resolved)


def extract_copy_bar_operation(
    fragment: str,
    *,
    current_lane: str,
    prior_sections: list[dict[str, Any]],
) -> dict[str, Any] | None:
    lowered = fragment.lower()
    prefix = ""
    match = re.search(r"copy\s+(.*?)\s+bars?\s+(\d+)(?:\s*-\s*(\d+))?", lowered)
    if match:
        prefix = normalize_space(match.group(1))
        start = int(match.group(2))
        end = int(match.group(3) or start)
    else:
        match = re.search(r"copy\s+bars?\s+(\d+)(?:\s*-\s*(\d+))?", lowered)
        if not match:
            return None
        start = int(match.group(1))
        end = int(match.group(2) or start)
    source_lane, source_reference = extract_copy_source(prefix, current_lane, prior_sections)
    payload: dict[str, Any] = {
        "sourceBarOffsets": list(range(max(1, start) - 1, max(start, end))),
        "transposeSemitones": parse_transpose_instruction(lowered),
        "sourceLane": source_lane,
    }
    omit_beats = extract_omit_beats(lowered)
    if omit_beats:
        payload["omitBeats"] = omit_beats
    if source_reference:
        payload["sourceReference"] = source_reference
    if "double-time hats" in lowered or "double time hats" in lowered:
        payload["hatSpacingScale"] = 0.5
    if "half-time hats" in lowered or "half time hats" in lowered:
        payload["hatSpacingScale"] = 2.0
    ride_match = re.search(r"ride(?:s)?(?:\s+(?:on|at))?\s+([^.;]+)", lowered)
    if ride_match:
        beats = parse_beat_list(ride_match.group(1))
        payload["rideBeats"] = beats or [0.0]
    elif "add ride" in lowered or re.search(r"\bride\b", lowered):
        payload["rideBeats"] = [0.0]
    crash_match = re.search(r"crash(?:es)?(?:\s+(?:on|at))?\s+([^.;]+)", lowered)
    if crash_match:
        beats = parse_beat_list(crash_match.group(1))
        if beats:
            payload["crashBeats"] = beats
    transforms = extract_phrase_transforms(lowered)
    if transforms:
        payload["phraseTransforms"] = transforms
    return payload


def copy_events_across_bars(
    source_events: list[dict[str, Any]],
    *,
    source_bars: list[int],
    target_bars: list[int],
    lane: str,
    transpose_semitones: int = 0,
) -> list[dict[str, Any]]:
    if not target_bars:
        return []
    explicit_by_bar: dict[int, list[dict[str, Any]]] = {}
    defaults: list[dict[str, Any]] = []
    for event in source_events:
        if "barOffset" in event:
            explicit_by_bar.setdefault(int(event["barOffset"]), []).append(deep_copy_jsonish(event))
        else:
            defaults.append(deep_copy_jsonish(event))
    if not source_bars:
        source_bars = sorted(explicit_by_bar) or [0]
    copied: list[dict[str, Any]] = []
    for index, target_bar in enumerate(target_bars):
        source_bar = source_bars[index % len(source_bars)]
        events = explicit_by_bar.get(source_bar) or defaults
        for event in events:
            updated = deep_copy_jsonish(event)
            updated["barOffset"] = int(target_bar)
            if transpose_semitones and "note" in updated:
                updated["note"] = int(updated["note"]) + transpose_semitones
                updated["noteName"] = midi_to_note_name(int(updated["note"]))
            copied.append(updated)
    return copied


def apply_phrase_transforms(
    copied_events: list[dict[str, Any]],
    *,
    lane: str,
    transforms: list[str],
) -> list[dict[str, Any]]:
    if not copied_events or not transforms:
        return copied_events
    transformed = [deep_copy_jsonish(event) for event in copied_events]
    by_bar: dict[int, list[dict[str, Any]]] = {}
    for event in transformed:
        by_bar.setdefault(int(event.get("barOffset", 0)), []).append(event)
    for bar_events in by_bar.values():
        ordered = sorted(bar_events, key=lambda item: (float(item.get("beat", 0.0)), float(item.get("duration", 0.0))))
        if any(mode in transforms for mode in ("reverse", "mirror")):
            for event in ordered:
                duration = float(event.get("duration", 0.0))
                event["beat"] = round(max(0.0, 4.0 - float(event.get("beat", 0.0)) - duration), 2)
        if lane in {"lead", "bass"} and any(mode in transforms for mode in ("invert", "mirror")):
            pitch_events = [event for event in ordered if "note" in event]
            if pitch_events:
                pivot = int(pitch_events[0]["note"])
                for event in pitch_events:
                    mirrored = pivot - (int(event["note"]) - pivot)
                    event["note"] = mirrored
                    event["noteName"] = midi_to_note_name(int(event["note"]))
        bar_events.sort(key=lambda item: (float(item.get("beat", 0.0)), int(item.get("note", 0))))
    return transformed


def expand_hat_copy_modifiers(
    copied_events: list[dict[str, Any]],
    *,
    target_bars: list[int],
    spacing_scale: float | None,
) -> list[dict[str, Any]]:
    if not copied_events or spacing_scale is None:
        return copied_events
    expanded: list[dict[str, Any]] = []
    for target_bar in target_bars:
        bar_events = [event for event in copied_events if int(event.get("barOffset", -1)) == int(target_bar)]
        beats = sorted(float(event["beat"]) for event in bar_events if "beat" in event)
        spacing = infer_spacing_from_beats(beats) or 1.0
        new_spacing = max(0.125, round(spacing * spacing_scale, 3))
        steps = int(round(4.0 / new_spacing))
        for step in range(steps):
            expanded.append({"barOffset": int(target_bar), "beat": round(step * new_spacing, 2)})
    return finalize_lane_events(expanded, lane="hat")


def extract_drum_block_events(fragment: str, bar_offsets: list[int] | None) -> dict[str, dict[str, Any]]:
    lane_pattern = r"(kick(?: drum)?s?|snare(?: drum)?s?|clap(?: stack)?s?|hi-hats?|hihats?|hats?|rides?|crashes?)"
    matches = list(re.finditer(rf"\b{lane_pattern}\b", fragment, flags=re.IGNORECASE))
    extracted: dict[str, dict[str, Any]] = {}
    if not matches:
        return extracted
    for index, match in enumerate(matches):
        lane = canonical_lane(normalize_space(match.group(1)))
        if not lane:
            continue
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(fragment)
        subfragment = fragment[start:end].strip(" ,")
        compact_matches = list(re.finditer(r"(\d(?:\.\d+)?)([^,\s|;]*)", subfragment))
        events: list[dict[str, Any]] = []
        for compact in compact_matches:
            beat = parse_beat_value(compact.group(1))
            if beat is None:
                continue
            item: dict[str, Any] = {"beat": round(float(beat), 2)}
            item.update(extract_compact_event_attributes(compact.group(2), lane=lane))
            events.append(item)
        if not events:
            beats = parse_beat_list(subfragment)
            if not beats and lane in {"ride", "crash"} and subfragment:
                beats = [0.0]
            events = [{"beat": round(float(beat), 2)} for beat in beats]
        if not events:
            continue
        events = filter_events_by_omit_beats(events, extract_omit_beats(subfragment))
        if not events:
            continue
        events = apply_bar_offsets(events, bar_offsets)
        payload: dict[str, Any] = {"kind": "beatPattern", "events": events, "source": "lane_map"}
        if lane == "hat":
            spacing = infer_spacing_from_beats([float(event["beat"]) for event in events if "beat" in event])
            if spacing is not None:
                payload["spacingBeats"] = spacing
        extracted[lane] = payload
    return extracted


def apply_drum_copy_operation(
    lane_events: dict[str, Any],
    *,
    source_lane_payloads: dict[str, Any] | None,
    source_bars: list[int],
    target_bars: list[int],
    modifiers: dict[str, Any],
) -> None:
    source_lane_payloads = source_lane_payloads or lane_events
    for lane in ("kick", "snare", "clap", "hat", "ride", "crash"):
        current_payload = source_lane_payloads.get(lane) or {}
        current_events = current_payload.get("events") or []
        copied = copy_events_across_bars(
            current_events,
            source_bars=source_bars,
            target_bars=target_bars,
            lane=lane,
            transpose_semitones=0,
        )
        if lane == "hat" and modifiers.get("hatSpacingScale") is not None:
            copied = expand_hat_copy_modifiers(
                copied,
                target_bars=target_bars,
                spacing_scale=float(modifiers["hatSpacingScale"]),
            )
        if copied:
            copied = filter_events_by_omit_beats(copied, [float(beat) for beat in modifiers.get("omitBeats", [])])
        if copied:
            payload: dict[str, Any] = {
                "kind": "beatPattern",
                "events": copied,
                "source": "lane_copy",
            }
            if lane == "hat":
                beats = [float(event["beat"]) for event in copied if "beat" in event and "barOffset" not in event]
                spacing = infer_spacing_from_beats(beats)
                if spacing is not None:
                    payload["spacingBeats"] = spacing
            record_lane_event(lane_events, lane, payload)
    if modifiers.get("rideBeats"):
        ride_events = []
        for target_bar in target_bars:
            for beat in modifiers["rideBeats"]:
                ride_events.append({"barOffset": int(target_bar), "beat": round(float(beat), 2)})
        record_lane_event(lane_events, "ride", {"kind": "beatPattern", "events": ride_events, "source": "lane_copy"})
    if modifiers.get("crashBeats"):
        crash_events = []
        for target_bar in target_bars:
            for beat in modifiers["crashBeats"]:
                crash_events.append({"barOffset": int(target_bar), "beat": round(float(beat), 2)})
        record_lane_event(lane_events, "crash", {"kind": "beatPattern", "events": crash_events, "source": "lane_copy"})


def extract_colon_lane_maps(text: str, lane_events: dict[str, Any], prior_sections: list[dict[str, Any]]) -> None:
    label_pattern = r"(lead|melody|hook|bass|chords?|progression|automation|filter|cutoff|macro|drums?|kick(?: drum)?s?|snare(?: drum)?s?|clap(?: stack)?s?|hi-hats?|hihats?|hats?|rides?|crashes?)"
    label_re = re.compile(rf"\b{label_pattern}\s*:", flags=re.IGNORECASE)
    for line in re.split(r"[\n;]+", text):
        matches = list(label_re.finditer(line))
        for index, match in enumerate(matches):
            lane_token = normalize_space(match.group(1))
            lane = canonical_lane(lane_token)
            if not lane:
                continue
            fragment_start = match.end()
            fragment_end = matches[index + 1].start() if index + 1 < len(matches) else len(line)
            fragment = line[fragment_start:fragment_end]
            fragment = re.sub(r"\band\s+$", "", fragment, flags=re.IGNORECASE).strip(" ,")
            if not fragment:
                continue
            scoped_segments = extract_bar_scoped_segments(fragment)
            if lane == "automation":
                envelopes: list[dict[str, Any]] = []
                for bar_offsets, scoped_fragment in scoped_segments:
                    envelopes.extend(extract_automation_envelopes(scoped_fragment, bar_offsets))
                if envelopes:
                    record_lane_event(
                        lane_events,
                        lane,
                        {
                            "kind": "automationEnvelope",
                            "envelopes": envelopes,
                            "source": "lane_map",
                        },
                    )
                continue
            if lane == "drums":
                for bar_offsets, scoped_fragment in scoped_segments:
                    copy_operation = extract_copy_bar_operation(
                        scoped_fragment,
                        current_lane=lane,
                        prior_sections=prior_sections,
                    )
                    if copy_operation and bar_offsets:
                        source_payloads = lane_events
                        if copy_operation.get("sourceReference"):
                            resolved = resolve_reference_payload(copy_operation["sourceReference"], prior_sections)
                            if resolved:
                                source_payloads = deep_copy_jsonish(resolved.get("laneEvents", {}) or {})
                        apply_drum_copy_operation(
                            lane_events,
                            source_lane_payloads=source_payloads,
                            source_bars=copy_operation.get("sourceBarOffsets", []),
                            target_bars=bar_offsets,
                            modifiers=copy_operation,
                        )
                        continue
                    for nested_lane, payload in extract_drum_block_events(scoped_fragment, bar_offsets).items():
                        record_lane_event(lane_events, nested_lane, payload)
                continue
            collected_events: list[dict[str, Any]] = []
            progression_symbols: list[str] = []
            spacing_hint: float | None = None
            prior_lane_events = deep_copy_jsonish((lane_events.get(lane) or {}).get("events", []))
            for bar_offsets, scoped_fragment in scoped_segments:
                copy_operation = extract_copy_bar_operation(
                    scoped_fragment,
                    current_lane=lane,
                    prior_sections=prior_sections,
                )
                if copy_operation and bar_offsets:
                    source_events = prior_lane_events + collected_events
                    if copy_operation.get("sourceReference"):
                        resolved = resolve_reference_payload(copy_operation["sourceReference"], prior_sections)
                        source_lane = str(copy_operation.get("sourceLane") or lane)
                        if resolved:
                            source_events = deep_copy_jsonish(
                                ((resolved.get("laneEvents", {}) or {}).get(source_lane) or {}).get("events", [])
                            )
                    copied = copy_events_across_bars(
                        source_events,
                        source_bars=copy_operation.get("sourceBarOffsets", []),
                        target_bars=bar_offsets,
                        lane=lane,
                        transpose_semitones=int(copy_operation.get("transposeSemitones", 0)),
                    )
                    copied = apply_phrase_transforms(
                        copied,
                        lane=lane,
                        transforms=list(copy_operation.get("phraseTransforms", [])),
                    )
                    copied = filter_events_by_omit_beats(copied, [float(beat) for beat in copy_operation.get("omitBeats", [])])
                    if copied:
                        collected_events.extend(copied)
                        continue
                if lane in {"lead", "bass"}:
                    note_events = apply_bar_offsets(extract_note_events(scoped_fragment, lane), bar_offsets)
                    note_events = filter_events_by_omit_beats(note_events, extract_omit_beats(scoped_fragment))
                    if note_events:
                        collected_events.extend(note_events)
                        continue
                if lane == "chords":
                    chord_events = apply_bar_offsets(extract_chord_events(scoped_fragment), bar_offsets)
                    chord_events = filter_events_by_omit_beats(chord_events, extract_omit_beats(scoped_fragment))
                    if chord_events:
                        collected_events.extend(chord_events)
                        progression_symbols.extend(
                            [event["symbol"] for event in chord_events if event.get("symbol")]
                        )
                        continue
                beat_values = parse_beat_list(scoped_fragment)
                if not beat_values:
                    continue
                if lane in {"lead", "bass", "chords"}:
                    events = apply_bar_offsets(beats_to_events(beat_values, lane), bar_offsets)
                    events = filter_events_by_omit_beats(events, extract_omit_beats(scoped_fragment))
                    collected_events.extend(events)
                else:
                    scoped_events = [{"beat": round(float(beat), 2)} for beat in beat_values]
                    events = apply_bar_offsets(scoped_events, bar_offsets)
                    events = filter_events_by_omit_beats(events, extract_omit_beats(scoped_fragment))
                    collected_events.extend(events)
                    spacing = infer_spacing_from_beats(beat_values)
                    if lane == "hat" and spacing is not None:
                        spacing_hint = spacing
            if not collected_events:
                continue
            payload: dict[str, Any] = {
                "kind": "notePattern" if lane in {"lead", "bass"} and any("note" in item for item in collected_events) else ("chordPattern" if lane == "chords" and any("symbol" in item for item in collected_events) else "beatPattern"),
                "events": collected_events,
                "source": "lane_map",
            }
            if lane == "chords" and progression_symbols:
                deduped_symbols: list[str] = []
                for symbol in progression_symbols:
                    if symbol not in deduped_symbols:
                        deduped_symbols.append(symbol)
                payload["progressionSymbols"] = deduped_symbols
            if lane == "hat" and spacing_hint is not None:
                payload["spacingBeats"] = spacing_hint
            record_lane_event(lane_events, lane, payload)


def extract_natural_lane_events(text: str, lane_events: dict[str, Any]) -> None:
    structured_label_pattern = r"\b(?:lead|melody|hook|bass|chords?|progression|automation|filter|cutoff|macro|drums?|kick(?: drum)?s?|snare(?: drum)?s?|clap(?: stack)?s?|hi-hats?|hihats?|hats?|rides?|crashes?)\s*:"
    lines = []
    for line in re.split(r"[\n;]+", text):
        if re.search(structured_label_pattern, line, flags=re.IGNORECASE):
            continue
        lines.append(line)
    lowered = "\n".join(lines).lower()
    stop = r"(?:kick(?: drums?)?|snare(?: drums?)?|clap(?: stacks?)?|hi-hats?|hihats?|hats?|rides?|crashes?)"
    pattern_specs = (
        ("kick", rf"kick(?: drum)?s?(?:\s+(?:on|at|hits? on|plays? on))?\s+(.+?)(?=(?:\b{stop}\b|[.;]|$))"),
        ("snare", rf"snare(?: drum)?s?(?:\s+(?:on|at|hits? on|plays? on))?\s+(.+?)(?=(?:\b{stop}\b|[.;]|$))"),
        ("clap", rf"clap(?: stack)?s?(?:\s+(?:on|at|hits? on|plays? on))?\s+(.+?)(?=(?:\b{stop}\b|[.;]|$))"),
        ("hat", rf"(?:hi-hat|hihat|hat)s?(?:\s+(?:on|at|hits? on|plays? on))?\s+(.+?)(?=(?:\b{stop}\b|[.;]|$))"),
        ("ride", rf"ride(?:s)?(?:\s+(?:on|at|hits? on|plays? on))?\s+(.+?)(?=(?:\b{stop}\b|[.;]|$))"),
        ("crash", rf"crash(?:es)?(?:\s+(?:on|at|hits? on|plays? on))?\s+(.+?)(?=(?:\b{stop}\b|[.;]|$))"),
    )
    for lane, pattern in pattern_specs:
        match = re.search(pattern, lowered)
        if not match:
            continue
        beats = parse_beat_list(match.group(1))
        if not beats:
            continue
        payload: dict[str, Any] = {
            "kind": "beatPattern",
            "events": [{"beat": round(float(beat), 2)} for beat in beats],
            "source": "natural_language",
        }
        if lane == "hat":
            spacing = infer_spacing_from_beats(beats)
            if spacing is not None:
                payload["spacingBeats"] = spacing
        record_lane_event(lane_events, lane, payload)
    if "eighth note" in lowered or "eighth-note" in lowered:
        record_lane_event(lane_events, "hat", {"spacingBeats": 0.5, "source": "natural_language"})
    if "sixteenth note" in lowered or "sixteenth-note" in lowered:
        record_lane_event(lane_events, "hat", {"spacingBeats": 0.25, "source": "natural_language"})
    if "triplet" in lowered:
        record_lane_event(lane_events, "hat", {"spacingBeats": round(1.0 / 3.0, 3), "source": "natural_language"})


def extract_lane_transforms(text: str, prior_sections: list[dict[str, Any]]) -> dict[str, Any]:
    lowered = text.lower()
    transforms: dict[str, Any] = {}

    lead_match = re.search(r"same melody(?:\s+from\s+the\s+([a-z0-9\s-]+))?", lowered)
    if lead_match:
        descriptor = extract_section_reference_descriptor(lead_match.group(1) or "")
        resolved = resolve_section_reference(descriptor, prior_sections, roles=("lead", "chords", "pluck"))
        payload: dict[str, Any] = {}
        copy_from = reference_payload(descriptor, resolved)
        if copy_from:
            payload["copyFrom"] = copy_from
        if "filled in" in lowered:
            payload["transform"] = "fill_in"
        if payload:
            transforms["lead"] = payload
    elif "filled in" in lowered:
        transforms["lead"] = {"transform": "fill_in"}

    chord_match = re.search(r"same (?:chords?|progression)(?:\s+from\s+the\s+([a-z0-9\s-]+))?", lowered)
    if chord_match:
        descriptor = extract_section_reference_descriptor(chord_match.group(1) or "")
        resolved = resolve_section_reference(descriptor, prior_sections, roles=("chords", "pad", "pluck"))
        copy_from = reference_payload(descriptor, resolved)
        if copy_from:
            transforms["chords"] = {"copyFrom": copy_from}

    bass_payload: dict[str, Any] = {}
    bass_match = re.search(r"bass .*same notes from the ([a-z0-9\s-]+)", lowered)
    if not bass_match:
        bass_match = re.search(r"plays the same notes from the ([a-z0-9\s-]+)", lowered)
    if bass_match:
        descriptor = extract_section_reference_descriptor(bass_match.group(1))
        resolved = resolve_section_reference(descriptor, prior_sections, roles=("bass", "sub", "chords"))
        copy_from = reference_payload(descriptor, resolved)
        if copy_from:
            bass_payload["copyFrom"] = copy_from
        bass_payload["mode"] = "same_notes"
    if re.search(r"bass .*follow(?:s|ing)? chords", lowered):
        bass_payload["followChords"] = True
    omit_match = re.search(r"skip(?:s|ping)? beats?\s+([^.;]+)", lowered)
    if not omit_match:
        omit_match = re.search(r"omit(?:s|ting)? beats?\s+([^.;]+)", lowered)
    if omit_match and ("bass" in lowered or bass_payload.get("followChords")):
        omit_beats = parse_beat_list(omit_match.group(1))
        if omit_beats:
            bass_payload["omitBeats"] = omit_beats
    if bass_payload:
        transforms["bass"] = bass_payload

    drum_payload: dict[str, Any] = {}
    copy_drums = re.search(r"copy\s+([a-z0-9\s-]+?)\s+drums?(.*?)(?:[.;]|$)", lowered)
    if copy_drums:
        descriptor = extract_section_reference_descriptor(copy_drums.group(1))
        resolved = resolve_section_reference(descriptor, prior_sections, roles=("drums", "kick", "snare", "clap", "hat", "ride"))
        copy_from = reference_payload(descriptor, resolved)
        if copy_from:
            drum_payload["copyFrom"] = copy_from
        tail = copy_drums.group(2)
    else:
        same_drums = re.search(r"same drum(?:s| pattern| beat)?(?:\s+from\s+the\s+([a-z0-9\s-]+))?", lowered)
        tail = ""
        if same_drums:
            descriptor = extract_section_reference_descriptor(same_drums.group(1) or "")
            resolved = resolve_section_reference(descriptor, prior_sections, roles=("drums", "kick", "snare", "clap", "hat", "ride"))
            copy_from = reference_payload(descriptor, resolved)
            if copy_from:
                drum_payload["copyFrom"] = copy_from
    overrides: dict[str, Any] = {}
    tail_text = lower_join(lowered, tail if "tail" in locals() else "")
    if "double-time hats" in tail_text or "double time hats" in tail_text:
        overrides["hatSpacing"] = 0.25
    if "half-time hats" in tail_text or "half time hats" in tail_text:
        overrides["hatSpacing"] = 1.0
    if "ride" in tail_text:
        overrides["ride"] = True
    if overrides:
        drum_payload["overrides"] = overrides
    if drum_payload:
        transforms["drums"] = drum_payload

    transpose = parse_transpose_instruction(lowered)
    if transpose:
        transforms["lead"] = merge_nested_payload(transforms.get("lead", {}), {"transposeSemitones": transpose})

    return transforms


def extract_lane_directives(text: str, prior_sections: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    lane_events: dict[str, Any] = {}
    lane_transforms = extract_lane_transforms(text, prior_sections)
    extract_colon_lane_maps(text, lane_events, prior_sections)
    extract_natural_lane_events(text, lane_events)
    progression_symbols = extract_progression_symbols(text)
    if len(progression_symbols) >= 2:
        record_lane_event(
            lane_events,
            "chords",
            {
                "kind": "progressionSymbols",
                "progressionSymbols": progression_symbols,
                "source": "natural_language",
            },
        )
    return lane_events, lane_transforms


def infer_section(text: str) -> tuple[str, str, bool]:
    lowered = text.lower()
    best: tuple[int, int, str, str] | None = None
    for section_id, label, keywords in SECTION_RULES:
        for keyword in keywords:
            position = lowered.find(keyword)
            if position == -1:
                continue
            score = (position, -len(keyword))
            if best is None or score < (best[0], best[1]):
                best = (position, -len(keyword), section_id, label)
    if best:
        return best[2], best[3], True
    return "production_notes", "Production Notes", False


def extract_timecoded_segments(text: str) -> list[dict[str, Any]]:
    pattern = re.compile(r"(?<!\d)(\d{1,2}:\d{2}(?::\d{2})?)(?!\d)")
    matches = list(pattern.finditer(text))
    if not matches:
        return []
    segments: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        raw_chunk = text[start:end]
        chunk = normalize_space(strip_spoken_timestamp_prefix(raw_chunk))
        if not chunk:
            continue
        seconds = timecode_to_seconds(match.group(1))
        segments.append({
            "index": len(segments) + 1,
            "timecode": match.group(1),
            "startSeconds": seconds,
            "text": chunk,
        })
    return segments


def fallback_segments(text: str) -> list[dict[str, Any]]:
    blocks = [normalize_space(block) for block in re.split(r"\n\s*\n+", text) if normalize_space(block)]
    if not blocks:
        blocks = [normalize_space(text)] if normalize_space(text) else []
    segments: list[dict[str, Any]] = []
    for block in blocks:
        sentences = [piece for piece in re.split(r"(?<=[.!?])\s+", block) if piece]
        if len(sentences) <= 3:
            chunks = [block]
        else:
            chunks = [" ".join(sentences[i:i + 3]) for i in range(0, len(sentences), 3)]
        for chunk in chunks:
            cleaned = normalize_space(chunk)
            if cleaned:
                segments.append({
                    "index": len(segments) + 1,
                    "timecode": None,
                    "startSeconds": None,
                    "text": cleaned,
                })
    return segments


def merge_sections(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for segment in segments:
        section_id, label, explicit = infer_section(segment["text"])
        current = {
            "segmentIndex": segment["index"],
            "sectionId": section_id,
            "label": label,
            "explicit": explicit,
            "startSeconds": segment["startSeconds"],
            "endSeconds": segment["startSeconds"],
            "timecodes": [segment["timecode"]] if segment["timecode"] else [],
            "texts": [segment["text"]],
            "trackRoles": extract_matches(segment["text"], TRACK_KEYWORDS),
            "plugins": extract_matches(segment["text"], PLUGIN_KEYWORDS),
            "techniques": extract_matches(segment["text"], TECHNIQUE_KEYWORDS),
        }
        if (
            merged
            and merged[-1]["sectionId"] == current["sectionId"]
            and (current["explicit"] or merged[-1]["explicit"])
        ):
            merged[-1]["texts"].append(segment["text"])
            merged[-1]["trackRoles"] = sorted(set(merged[-1]["trackRoles"] + current["trackRoles"]))
            merged[-1]["plugins"] = sorted(set(merged[-1]["plugins"] + current["plugins"]))
            merged[-1]["techniques"] = sorted(set(merged[-1]["techniques"] + current["techniques"]))
            if segment["timecode"]:
                merged[-1]["timecodes"].append(segment["timecode"])
            if segment["startSeconds"] is not None:
                merged[-1]["endSeconds"] = segment["startSeconds"]
        else:
            merged.append(current)

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(merged, start=1):
        start = item["startSeconds"]
        end = item["endSeconds"]
        normalized.append({
            "id": f"section-{index:02d}",
            "type": item["sectionId"],
            "label": item["label"],
            "startSeconds": start,
            "endSeconds": end,
            "timecodeStart": seconds_to_timecode(start) if start is not None else None,
            "timecodeEnd": seconds_to_timecode(end) if end is not None else None,
            "summary": first_sentences(" ".join(item["texts"])),
            "excerpt": " ".join(item["texts"])[:420],
            "transcriptText": " ".join(item["texts"]),
            "sourceSegmentCount": len(item["texts"]),
            "trackRoles": item["trackRoles"],
            "plugins": item["plugins"],
            "techniques": item["techniques"],
        })
    counters: defaultdict[str, int] = defaultdict(int)
    for section in normalized:
        counters[section["type"]] += 1
        section["ordinalWithinType"] = counters[section["type"]]
    return normalized


def collect_lines_by_keywords(segments: list[dict[str, Any]], keywords: tuple[str, ...], limit: int = 8) -> list[str]:
    lines: list[str] = []
    for segment in segments:
        lowered = segment["text"].lower()
        if any(keyword in lowered for keyword in keywords):
            line = first_sentences(segment["text"], limit=1)
            if line not in lines:
                lines.append(line)
        if len(lines) >= limit:
            break
    return lines


#: Words that end a title and begin a sentence. Speech has no punctuation, so
#: "how I made my song just can't stop so I'm going to walk you through it" runs
#: straight past the title unless something stops it.
#: Only true sentence connectives and speech filler. Pronouns are deliberately
#: absent — "Shape of You", "It Girl" and "Call Me" are all real titles, and the
#: word cap already stops a runaway match.
_TITLE_STOP_WORDS = (
    "so", "and", "because", "which", "but", "then", "when", "while",
    "that", "today", "okay", "alright", "um", "uh", "like", "basically",
    "obviously", "anyways", "anyway",
)


def _title_case(value: str) -> str:
    """Title-case without breaking contractions.

    ``str.title()`` capitalises after an apostrophe, which turns "just can't
    stop" into "Just Can'T Stop"."""
    return " ".join(
        word[:1].upper() + word[1:] if word else word
        for word in value.split()
    )


def _trim_title(raw: str) -> str:
    """Cut a spoken phrase down to the part that is plausibly a song title.

    Titles are short. Anything past the first few words is the sentence carrying
    on, and taking it produced project names like "Just Can'T Stop So I'M Going
    To Walk You Guys Through It Chro".
    """
    words = normalize_space(raw).split()
    kept: list[str] = []
    for index, word in enumerate(words):
        bare = word.strip(".,!?'\"").lower()
        # Allow a stop word as the very first word ("It Girl"), never after.
        if index > 0 and bare in _TITLE_STOP_WORDS:
            break
        kept.append(word)
        if len(kept) >= 6:
            break
    return " ".join(kept).strip(" -")


def infer_title_hint(text: str, project_id: str) -> str | None:
    patterns = (
        r"song(?:\s+is\s+going\s+to\s+be|\s+is\s+called|\s+called)\s+([a-z0-9][a-z0-9' !?-]{2,60})",
        r"how i made my song\s+([a-z0-9][a-z0-9' !?-]{2,60})",
        r"remaking (?:his|her|the) song\s+([a-z0-9][a-z0-9' !?-]{2,60})",
    )
    lowered = text.lower()
    for pattern in patterns:
        match = re.search(pattern, lowered, flags=re.IGNORECASE)
        if match:
            trimmed = _trim_title(match.group(1))
            if len(trimmed) >= 3:
                return _title_case(trimmed)
    if project_id:
        return " ".join(part.capitalize() for part in project_id.split("-"))
    return None


def infer_prompt_from_transcript(spec: dict[str, Any]) -> str:
    title = spec.get("titleHint") or spec.get("projectId") or "song project"
    arrangement = ", ".join(section["label"] for section in spec.get("sections", [])[:6]) or "chronological sections"
    tracks = ", ".join(item["name"] for item in spec.get("globalTracks", [])[:6]) or "lead, chords, bass, drums, FX"
    return (
        f"Convert the production walkthrough for {title} into an original Neon Studio project. "
        f"Carry over the described arrangement ({arrangement}), track roles ({tracks}), and production techniques, "
        f"but keep the result original and portable."
    )


def analyze_transcript(text: str, project_id: str, prompt: str | None = None) -> dict[str, Any]:
    cleaned = normalize_space(text.replace("\r", "\n"))
    segments = extract_timecoded_segments(cleaned)
    timecoded = bool(segments)
    if not segments:
        segments = fallback_segments(cleaned)
    sections = merge_sections(segments)
    prior_sections: list[dict[str, Any]] = []
    for section in sections:
        lane_events, lane_transforms = extract_lane_directives(section.get("transcriptText", section["summary"]), prior_sections)
        if lane_events:
            section["laneEvents"] = lane_events
        if lane_transforms:
            section["laneTransforms"] = lane_transforms
        prior_sections.append(section)

    track_counter: Counter[str] = Counter()
    plugin_counter: Counter[str] = Counter()
    technique_counter: Counter[str] = Counter()
    section_track_refs: defaultdict[str, list[str]] = defaultdict(list)
    section_plugin_refs: defaultdict[str, list[str]] = defaultdict(list)
    for section in sections:
        for track in section["trackRoles"]:
            track_counter[track] += 1
            section_track_refs[track].append(section["id"])
        for plugin in section["plugins"]:
            plugin_counter[plugin] += 1
            section_plugin_refs[plugin].append(section["id"])
        for technique in section["techniques"]:
            technique_counter[technique] += 1

    bpm_match = re.search(r"\b([6-9]\d|1\d\d|2[0-2]\d)\s*bpm\b", cleaned, flags=re.IGNORECASE)
    key_matches = sorted(set(match.strip() for match in re.findall(r"\b([A-G][#b]?\s*(?:major|minor))\b", cleaned, flags=re.IGNORECASE)))
    title_hint = infer_title_hint(cleaned, project_id)

    coverage = [f"{section['label']}: {', '.join(section['trackRoles'][:6]) or 'no concrete track roles detected'}" for section in sections[:10]]
    if track_counter:
        coverage.append("Global track roles: " + ", ".join(track for track, _ in track_counter.most_common(10)))
    if plugin_counter:
        coverage.append("Plugin mentions: " + ", ".join(plugin for plugin, _ in plugin_counter.most_common(10)))

    spec = {
        "schemaVersion": 2,
        "projectId": project_id,
        "titleHint": title_hint,
        "sourcePrompt": prompt,
        "wordCount": len(cleaned.split()),
        "timecoded": timecoded,
        "segmentCount": len(segments),
        "sectionCount": len(sections),
        "durationHintSeconds": max((segment["startSeconds"] or 0) for segment in segments) if timecoded else None,
        "tempoHint": int(bpm_match.group(1)) if bpm_match else None,
        "keyHints": key_matches,
        "sections": sections,
        "globalTracks": [
            {"name": track, "mentions": count, "sections": section_track_refs[track]}
            for track, count in track_counter.most_common()
        ],
        "globalPlugins": [
            {"name": plugin, "mentions": count, "sections": section_plugin_refs[plugin]}
            for plugin, count in plugin_counter.most_common()
        ],
        "globalTechniques": [
            {"name": technique, "mentions": count}
            for technique, count in technique_counter.most_common()
        ],
        "arrangementNotes": collect_lines_by_keywords(segments, ARRANGEMENT_KEYWORDS, limit=10),
        "mixNotes": collect_lines_by_keywords(segments, MIX_KEYWORDS, limit=10),
        "automationNotes": collect_lines_by_keywords(segments, AUTOMATION_KEYWORDS, limit=8),
        "coverageChecklist": coverage,
        "openQuestions": [
            item
            for item in (
                None if bpm_match else "Transcript does not explicitly state a BPM.",
                None if key_matches else "Transcript does not clearly state the key.",
                None if sections else "Could not recover chronological sections from the transcript.",
            )
            if item
        ],
        "derivedPrompt": None,  # filled by caller for transparency
    }
    spec["derivedPrompt"] = infer_prompt_from_transcript(spec)
    return spec


def render_markdown(spec: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# Transcript Spec: {spec.get('titleHint') or spec['projectId']}")
    lines.append("")
    if spec.get("sourcePrompt"):
        lines.append("## Source Prompt")
        lines.append("")
        lines.append(spec["sourcePrompt"])
        lines.append("")
    lines.append("## Transcript Overview")
    lines.append("")
    lines.append(f"- Word count: `{spec['wordCount']}`")
    lines.append(f"- Timecoded: `{spec['timecoded']}`")
    lines.append(f"- Segments: `{spec['segmentCount']}`")
    lines.append(f"- Sections: `{spec['sectionCount']}`")
    lines.append(f"- Tempo hint: `{spec['tempoHint'] or 'unset'}`")
    lines.append(f"- Key hints: `{', '.join(spec['keyHints']) if spec['keyHints'] else 'unset'}`")
    lines.append("")
    lines.append("## Derived Prompt")
    lines.append("")
    lines.append(spec["derivedPrompt"])
    lines.append("")
    fill = spec.get("fillInBlanks") or {}
    if fill:
        lines.append("## Fill In The Blanks")
        lines.append("")
        lines.append(f"- Style lane: `{fill.get('styleLane') or 'unset'}`")
        lines.append(f"- Decisions: `{len(fill.get('decisions') or [])}`")
        lines.append(f"- Policy: {fill.get('policy')}")
        lines.append("")
    lines.append("## Section Map")
    lines.append("")
    for section in spec["sections"]:
        lines.append(f"### {section['label']}")
        details = []
        if section["timecodeStart"]:
            details.append(section["timecodeStart"])
        if section["trackRoles"]:
            details.append("tracks: " + ", ".join(section["trackRoles"]))
        if section["plugins"]:
            details.append("plugins: " + ", ".join(section["plugins"]))
        if section["techniques"]:
            details.append("techniques: " + ", ".join(section["techniques"]))
        if details:
            lines.append(f"- {' | '.join(details)}")
        lines.append(f"- {section['summary']}")
        if section.get("laneEvents"):
            lines.append(f"- lane events: `{json.dumps(section['laneEvents'], sort_keys=True)}`")
        if section.get("laneTransforms"):
            lines.append(f"- lane transforms: `{json.dumps(section['laneTransforms'], sort_keys=True)}`")
        lines.append("")
    if spec["globalTracks"]:
        lines.append("## Global Track Roles")
        lines.append("")
        for item in spec["globalTracks"][:16]:
            lines.append(f"- {item['name']}: {item['mentions']} mention(s)")
        lines.append("")
    if spec["globalPlugins"]:
        lines.append("## Plugin Mentions")
        lines.append("")
        for item in spec["globalPlugins"][:16]:
            lines.append(f"- {item['name']}: {item['mentions']} mention(s)")
        lines.append("")
    if spec["mixNotes"]:
        lines.append("## Mix Notes")
        lines.append("")
        for item in spec["mixNotes"]:
            lines.append(f"- {item}")
        lines.append("")
    if spec["automationNotes"]:
        lines.append("## Automation Notes")
        lines.append("")
        for item in spec["automationNotes"]:
            lines.append(f"- {item}")
        lines.append("")
    if spec["coverageChecklist"]:
        lines.append("## Coverage Checklist")
        lines.append("")
        for item in spec["coverageChecklist"]:
            lines.append(f"- {item}")
        lines.append("")
    if spec["openQuestions"]:
        lines.append("## Open Questions")
        lines.append("")
        for item in spec["openQuestions"]:
            lines.append(f"- {item}")
        lines.append("")
    return "\n".join(lines)


def read_transcript(args: argparse.Namespace) -> str:
    if getattr(args, "transcript_text", None):
        return args.transcript_text
    if getattr(args, "transcript_file", None):
        return Path(args.transcript_file).read_text(encoding="utf-8")
    if getattr(args, "transcript_stdin", False):
        import sys

        return sys.stdin.read()
    raise SystemExit("Provide one of --transcript-text, --transcript-file, or --transcript-stdin.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Parse a production walkthrough transcript into a structured song spec.")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--prompt", help="Optional prompt or style lane.")
    parser.add_argument("--transcript-text", help="Raw transcript text.")
    parser.add_argument("--transcript-file", help="Path to a transcript text file.")
    parser.add_argument("--transcript-stdin", action="store_true", help="Read transcript text from stdin.")
    parser.add_argument("--output-json", help="Optional output JSON file path.")
    parser.add_argument("--output-md", help="Optional output markdown file path.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    text = read_transcript(args)
    spec = analyze_transcript(text, project_id=slugify(args.project_id), prompt=args.prompt)
    if args.output_json:
        Path(args.output_json).write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    if args.output_md:
        Path(args.output_md).write_text(render_markdown(spec) + "\n", encoding="utf-8")
    print(json.dumps(spec, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
