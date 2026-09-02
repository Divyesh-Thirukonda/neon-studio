#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any

from production_rubric import Gap, find_gaps, requirement_by_id, requirements_for_area


SECTION_DEFAULTS: dict[str, dict[str, Any]] = {
    "pre_intro": {
        "label": "Pre-Intro",
        "trackRoles": ["fx", "sample"],
        "techniques": ["filtering", "reverb"],
        "summary": "Inferred pre-intro texture to establish the sound palette before the main groove.",
    },
    "intro": {
        "label": "Intro",
        "trackRoles": ["chords", "lead", "fx"],
        "techniques": ["filtering", "reverb"],
        "summary": "Inferred intro that states the musical DNA without using the full drop energy.",
    },
    "verse": {
        "label": "Verse",
        "trackRoles": ["drums", "bass", "chords", "vocal"],
        "techniques": ["eq", "reverb"],
        "summary": "Inferred verse groove that leaves room for the later build and drop.",
    },
    "pre_build": {
        "label": "Pre-Build",
        "trackRoles": ["drums", "lead", "fx"],
        "techniques": ["automation", "filtering"],
        "summary": "Inferred pre-build handoff that previews the hook before tension rises.",
    },
    "build": {
        "label": "Build",
        "trackRoles": ["drums", "clap", "hat", "lead", "fx", "automation", "noise", "riser"],
        "techniques": ["automation", "filtering", "delay"],
        "summary": "Inferred build that ramps energy with drums, risers, filter movement, and hook teasing.",
    },
    "drop": {
        "label": "Drop",
        "trackRoles": ["drums", "bass", "sub", "chords", "lead", "fx"],
        "techniques": ["sidechain", "eq", "compression", "stereo"],
        "summary": "Inferred main drop where the hook, low end, and drums carry the payoff.",
    },
    "second_drop": {
        "label": "Second Drop",
        "trackRoles": ["drums", "bass", "sub", "chords", "lead", "hat", "ride", "fx"],
        "techniques": ["sidechain", "automation", "stereo", "distortion"],
        "summary": "Inferred second-drop lift that reuses the identity with added width, density, or octave energy.",
    },
    "break": {
        "label": "Break",
        "trackRoles": ["chords", "lead", "vocal", "fx"],
        "techniques": ["reverb", "filtering"],
        "summary": "Inferred break that resets density and creates contrast before the next build.",
    },
    "outro": {
        "label": "Outro",
        "trackRoles": ["chords", "fx"],
        "techniques": ["filtering", "reverb"],
        "summary": "Inferred outro that resolves the section flow without adding new song information.",
    },
}

ESSENTIAL_FLOW = ["intro", "verse", "build", "drop", "outro"]
DROP_FLOW = ["intro", "build", "drop", "outro"]
SECOND_DROP_INSERT = ["break", "build", "second_drop"]

STYLE_DEFAULTS: dict[str, dict[str, Any]] = {
    "dark_bass": {
        "tempo": 150,
        "key": "E minor",
        "progression": ["Em", "D", "C", "Bm"],
        "mixTargets": ["mono low end", "controlled harshness", "wide FX only above the bass"],
    },
    "bright_future_bass": {
        "tempo": 142,
        "key": "E minor",
        "progression": ["Em7", "Cmaj7", "Gadd9", "Dadd9"],
        "mixTargets": ["wide chords", "clean sidechain", "bright but non-brittle lead"],
    },
    "house_pop": {
        "tempo": 124,
        "key": "C major",
        "progression": ["Cmaj7", "Gadd9", "Am7", "Fmaj7"],
        "mixTargets": ["steady kick ownership", "tight bass pocket", "short transition tails"],
    },
    "modern_edm": {
        "tempo": 140,
        "key": "E minor",
        "progression": ["Em7", "Cmaj7", "Gadd9", "Dadd9"],
        "mixTargets": ["clear hook lane", "separated kick and bass", "visible build automation"],
    },
}


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned[:72] or "song-project"


def text_blob(spec: dict[str, Any], prompt: str | None = None) -> str:
    parts = [prompt or "", spec.get("sourcePrompt") or "", spec.get("derivedPrompt") or ""]
    for section in spec.get("sections", []) or []:
        parts.extend(
            [
                section.get("label") or "",
                section.get("summary") or "",
                section.get("excerpt") or "",
                section.get("transcriptText") or "",
                " ".join(section.get("trackRoles", []) or []),
                " ".join(section.get("techniques", []) or []),
            ]
        )
    return normalize_space(" ".join(str(part) for part in parts if part))


def detect_style_lane(spec: dict[str, Any], prompt: str | None = None) -> str:
    text = text_blob(spec, prompt).lower()
    if any(keyword in text for keyword in ("uk bass", "rave", "shadow", "dark", "heavy bass", "laser", "siren")):
        return "dark_bass"
    if any(keyword in text for keyword in ("future bass", "marshmello", "festival", "supersaw", "bright drop")):
        return "bright_future_bass"
    if any(keyword in text for keyword in ("house", "four on the floor", "club", "dance pop")):
        return "house_pop"
    return "modern_edm"


def decision(decisions: list[dict[str, Any]], area: str, detail: str, *, reason: str, confidence: str = "medium") -> None:
    decisions.append(
        {
            "area": area,
            "detail": detail,
            "reason": reason,
            "confidence": confidence,
            "source": "fill_in_blanks",
        }
    )


def ensure_unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def make_inferred_section(section_type: str, reason: str) -> dict[str, Any]:
    defaults = SECTION_DEFAULTS[section_type]
    return {
        "id": "",
        "type": section_type,
        "label": defaults["label"],
        "startSeconds": None,
        "endSeconds": None,
        "timecodeStart": None,
        "timecodeEnd": None,
        "summary": defaults["summary"],
        "excerpt": defaults["summary"],
        "transcriptText": "",
        "sourceSegmentCount": 0,
        "trackRoles": list(defaults["trackRoles"]),
        "plugins": [],
        "techniques": list(defaults["techniques"]),
        "ordinalWithinType": 1,
        "inferred": True,
        "fillReason": reason,
    }


def reindex_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counters: defaultdict[str, int] = defaultdict(int)
    for index, section in enumerate(sections, start=1):
        section["id"] = f"section-{index:02d}"
        section_type = str(section.get("type") or "production_notes")
        counters[section_type] += 1
        section["ordinalWithinType"] = counters[section_type]
    return sections


def has_musical_sections(sections: list[dict[str, Any]]) -> bool:
    return any(section.get("type") in SECTION_DEFAULTS for section in sections)


def insert_before_first(sections: list[dict[str, Any]], target_type: str, section: dict[str, Any]) -> None:
    for index, existing in enumerate(sections):
        if existing.get("type") == target_type:
            sections.insert(index, section)
            return
    sections.append(section)


# ---------------------------------------------------------------------------
# Structural repair.
#
# These run before anything else, because the passes after them assume the
# section list is in arrangement order, carries every part the transcript
# described, and knows how long each section is. Ingest cannot guarantee any of
# those: it walks a video top to bottom, and a producer does not narrate a song
# in playback order.
# ---------------------------------------------------------------------------

#: Where each section type sits in a finished arrangement. Ingest emits sections
#: in the order they were *talked about*, which is a different thing.
SECTION_RANK: dict[str, int] = {
    "pre_intro": 0,
    "intro": 1,
    "verse": 2,
    "pre_build": 3,
    "build": 4,
    "drop": 5,
    "break": 6,
    "second_drop": 8,
    "outro": 9,
}

#: Names producers actually use, mapped to the roles the generator understands.
#: Without this an "808" or a "stab" is parsed, stored, and then silently
#: contributes nothing because no track maps to it.
ROLE_ALIASES: dict[str, str] = {
    "808": "sub",
    "sub bass": "sub",
    "subbass": "sub",
    "arp": "pluck",
    "arpeggio": "pluck",
    "pluck": "pluck",
    "chant": "vocal",
    "vox": "vocal",
    "vocal chop": "vocal",
    "chops": "vocal",
    "topline": "vocal",
    "shaker": "hat",
    "perc": "hat",
    "percussion": "hat",
    "tambourine": "hat",
    "hihat": "hat",
    "hi-hat": "hat",
    "open hat": "hat",
    "stab": "chords",
    "pad": "chords",
    "keys": "chords",
    "piano": "chords",
    "string": "chords",
    "strings": "chords",
    "synth": "lead",
    "melody": "lead",
    "riff": "lead",
    "topline synth": "lead",
    "siren": "fx",
    "laser": "fx",
    "sweep": "fx",
    "whoosh": "fx",
    "riser": "riser",
    "impact": "impact",
    "boom": "impact",
    "reverse": "reverse",
    "texture": "noise",
    "atmosphere": "noise",
    "ambience": "noise",
    "breath": "noise",
    "breaths": "noise",
    "kick": "kick",
    "snare": "snare",
    "clap": "clap",
    "crash": "crash",
    "ride": "ride",
}


def normalize_role_aliases(spec: dict[str, Any], decisions: list[dict[str, Any]]) -> None:
    """Fold the words producers use into the roles the generator maps to tracks.

    A walkthrough says "808", "stab", "shaker". The generator knows "sub",
    "chords", "hat". Before this, those parsed cleanly into the spec, looked
    fully specified, and then produced no track at all.
    """
    renamed: set[str] = set()

    def convert(values: Any) -> list[str]:
        out: list[str] = []
        for value in values if isinstance(values, list) else []:
            raw = str(value).strip().lower()
            mapped = ROLE_ALIASES.get(raw, raw)
            if mapped != raw:
                renamed.add(f"{raw} -> {mapped}")
            if mapped not in out:
                out.append(mapped)
        return out

    for section in spec.get("sections", []) or []:
        if isinstance(section, dict):
            section["trackRoles"] = convert(section.get("trackRoles"))

    global_tracks = spec.get("globalTracks")
    if isinstance(global_tracks, list):
        merged: dict[str, dict[str, Any]] = {}
        for item in global_tracks:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            raw = str(item["name"]).strip().lower()
            mapped = ROLE_ALIASES.get(raw, raw)
            if mapped != raw:
                renamed.add(f"{raw} -> {mapped}")
            existing = merged.get(mapped)
            if existing is None:
                merged[mapped] = {**item, "name": mapped}
            else:
                existing["mentions"] = int(existing.get("mentions") or 0) + int(item.get("mentions") or 0)
                existing["sections"] = ensure_unique(
                    list(existing.get("sections") or []) + list(item.get("sections") or [])
                )
        spec["globalTracks"] = list(merged.values())

    if renamed:
        decision(
            decisions,
            "roles",
            f"Normalised producer terms to buildable roles: {', '.join(sorted(renamed)[:6])}.",
            reason="These names parsed fine but mapped to no track, so the parts would have gone missing at build time.",
            confidence="high",
        )


def rescue_unclassified_sections(spec: dict[str, Any], decisions: list[dict[str, Any]]) -> None:
    """Give a type to sections that carry real parts but were never classified.

    Ingest labels anything it cannot place as `production_notes`, and the
    materializer drops those — along with every lane event, role and technique
    they carry. A walkthrough that describes a sound before saying where it goes
    ("the bass is a mid-bass with grit") produces exactly that: a section that
    looks fully specified in the spec and silently disappears from the song.
    """
    sections = spec.get("sections")
    if not isinstance(sections, list):
        return

    def has_content(section: dict[str, Any]) -> bool:
        return bool(
            (section.get("trackRoles") or [])
            or (section.get("laneEvents") or {})
            or (section.get("techniques") or [])
        )

    existing_types = {str(s.get("type") or "") for s in sections if isinstance(s, dict)}
    rescued: list[str] = []

    for section in sections:
        if not isinstance(section, dict):
            continue
        if section.get("type") in SECTION_RANK or not has_content(section):
            continue

        roles = {str(r).lower() for r in (section.get("trackRoles") or [])}
        lanes = {str(k).lower() for k in (section.get("laneEvents") or {})}
        signal = roles | lanes
        techniques = {str(t).lower() for t in (section.get("techniques") or [])}

        # Infer the type from what the section is made of. A part carrying kick,
        # bass and lead together is a payoff section; drums plus risers is a
        # build; chords and lead alone is an intro or a break.
        drums = bool(signal & {"kick", "snare", "drums", "clap", "hat"})
        low = bool(signal & {"bass", "sub"})
        melodic = bool(signal & {"lead", "chords"})
        rising = bool(signal & {"riser", "automation", "noise"}) or "automation" in techniques

        if drums and low and melodic:
            inferred = "second_drop" if "drop" in existing_types else "drop"
        elif drums and rising:
            inferred = "build"
        elif drums:
            inferred = "verse"
        elif melodic:
            inferred = "break" if "intro" in existing_types else "intro"
        else:
            continue

        section["type"] = inferred
        section["label"] = SECTION_DEFAULTS.get(inferred, {}).get("label", inferred.title())
        section["rescued"] = True
        existing_types.add(inferred)
        rescued.append(f"{section.get('id', '?')} -> {inferred}")

    if rescued:
        decision(
            decisions,
            "arrangement",
            f"Classified {len(rescued)} described-but-unplaced section(s): {', '.join(rescued[:4])}.",
            reason="They carried real parts and would otherwise have been dropped from the build entirely.",
            confidence="medium",
        )


def order_sections_canonically(spec: dict[str, Any], decisions: list[dict[str, Any]]) -> None:
    """Put the arrangement in playback order.

    Sections come out of ingest in the order the producer *talked* about them,
    and nobody narrates a song front to back — they say "the second drop is where
    it goes crazy, but first the intro is just a filtered chord". Laid out as
    parsed, that puts the biggest section at bar 1.
    """
    sections = spec.get("sections")
    if not isinstance(sections, list) or len(sections) < 2:
        return

    musical = [s for s in sections if isinstance(s, dict) and s.get("type") in SECTION_RANK]
    other = [s for s in sections if not (isinstance(s, dict) and s.get("type") in SECTION_RANK)]
    if len(musical) < 2:
        return

    before = [str(s.get("type")) for s in musical]

    # A second build belongs after the break, not with the first one, so rank by
    # type and then by how many of that type have already been seen.
    seen: dict[str, int] = {}
    keyed: list[tuple[int, int, int, dict[str, Any]]] = []
    for index, section in enumerate(musical):
        kind = str(section.get("type"))
        ordinal = seen.get(kind, 0)
        seen[kind] = ordinal + 1
        rank = SECTION_RANK.get(kind, 5)
        if kind in ("build", "verse", "intro") and ordinal > 0:
            rank += 3  # a repeat of a setup section belongs in the second half
        keyed.append((rank, ordinal, index, section))

    keyed.sort(key=lambda item: (item[0], item[1], item[2]))
    ordered = [item[3] for item in keyed]
    after = [str(s.get("type")) for s in ordered]

    if before == after:
        return

    spec["sections"] = ordered + other
    decision(
        decisions,
        "arrangement",
        f"Reordered sections into playback order: {' -> '.join(after)}.",
        reason=f"They were parsed in the order the walkthrough discussed them ({' -> '.join(before)}), which is not the order the song plays.",
        confidence="high",
    )


def resolve_duplicate_sections(spec: dict[str, Any], decisions: list[dict[str, Any]]) -> None:
    """Fold away repeats that are artefacts of parsing rather than arrangement.

    Two things come out of ordering that a song would never do. A second intro
    sitting between a build and a drop is not an intro — a producer returning to
    sparse material mid-song is writing a break. And two payoff sections back to
    back are almost always one section the walkthrough described twice, not two
    drops with nothing between them.
    """
    sections = spec.get("sections")
    if not isinstance(sections, list):
        return
    musical = [s for s in sections if isinstance(s, dict) and s.get("type") in SECTION_RANK]
    if len(musical) < 2:
        return

    changed: list[str] = []

    # A song has one intro. A second sparse section later is a break — that is
    # what returning to thin material in the middle of an arrangement is called.
    seen_intro = False
    for section in musical:
        kind = str(section.get("type"))
        if kind not in ("intro", "pre_intro"):
            continue
        if not seen_intro:
            seen_intro = True
            continue
        section["type"] = "break"
        section["label"] = SECTION_DEFAULTS["break"]["label"]
        changed.append(f"{section.get('id', '?')}: {kind} -> break")

    # Merge EVERY repeat of a type into its first occurrence, not just adjacent
    # ones. A walkthrough returns to the same part over and over — "so then the
    # drop", twenty minutes of detail, "back in the drop" — and ingest makes a
    # new section each time. Left alone that produced a 360-bar arrangement that
    # alternated verse and drop ten times. One section per type, carrying the
    # union of everything said about it, is what the producer actually described.
    merged: list[dict[str, Any]] = []
    first_of_type: dict[str, dict[str, Any]] = {}
    for section in musical:
        kind = str(section.get("type"))
        previous = first_of_type.get(kind)
        if previous is not None:
            previous["trackRoles"] = ensure_unique(
                list(previous.get("trackRoles") or []) + list(section.get("trackRoles") or [])
            )
            previous["techniques"] = ensure_unique(
                list(previous.get("techniques") or []) + list(section.get("techniques") or [])
            )
            lanes = dict(previous.get("laneEvents") or {})
            for lane, payload in (section.get("laneEvents") or {}).items():
                lanes.setdefault(lane, payload)
            previous["laneEvents"] = lanes
            for field in ("summary", "excerpt", "transcriptText"):
                extra = str(section.get(field) or "").strip()
                if extra and extra not in str(previous.get(field) or ""):
                    previous[field] = f"{str(previous.get(field) or '').strip()} {extra}".strip()
            changed.append(f"folded {section.get('id', '?')} into the {kind}")
            continue
        first_of_type[kind] = section
        merged.append(section)

    other = [s for s in sections if not (isinstance(s, dict) and s.get("type") in SECTION_RANK)]

    # Production notes come out of ingest one per paragraph — a long walkthrough
    # produced fifty-eight of them. They describe the whole track, so they are
    # one section carrying everything said.
    notes = [s for s in other if isinstance(s, dict) and s.get("type") == "production_notes"]
    if len(notes) > 1:
        first = notes[0]
        for extra in notes[1:]:
            for field in ("techniques", "plugins", "trackRoles"):
                first[field] = ensure_unique(list(first.get(field) or []) + list(extra.get(field) or []))
            lanes = dict(first.get("laneEvents") or {})
            for lane, payload in (extra.get("laneEvents") or {}).items():
                lanes.setdefault(lane, payload)
            if lanes:
                first["laneEvents"] = lanes
            for field in ("summary", "excerpt", "transcriptText"):
                text = str(extra.get(field) or "").strip()
                if text and text not in str(first.get(field) or ""):
                    first[field] = f"{str(first.get(field) or '').strip()} {text}".strip()
        other = [s for s in other if s is first or not (isinstance(s, dict) and s.get("type") == "production_notes")]
        changed.append(f"folded {len(notes) - 1} production note(s) into one")

    if not changed:
        return

    spec["sections"] = merged + other
    decision(
        decisions,
        "arrangement",
        f"Resolved {len(changed)} duplicated section(s): {', '.join(changed[:4])}.",
        reason="The walkthrough described some parts more than once; laid out literally that produces repeated sections with nothing between them.",
        confidence="medium",
    )


def assign_section_bars(spec: dict[str, Any], decisions: list[dict[str, Any]], style_lane: str) -> None:
    """Give every section a length.

    Without one, the builder falls back to a per-type constant, so every intro is
    eight bars and every drop sixteen no matter what the source said — and the
    timecodes a video transcript already carries go unused.
    """
    sections = spec.get("sections")
    if not isinstance(sections, list):
        return
    musical = [s for s in sections if isinstance(s, dict) and s.get("type") in SECTION_RANK]
    if not musical or all(s.get("bars") for s in musical):
        return

    tempo = float(spec.get("tempoHint") or STYLE_DEFAULTS.get(style_lane, {}).get("tempo") or 140)
    seconds_per_bar = (60.0 / max(tempo, 1)) * 4.0
    from_timecodes = 0

    for section in musical:
        if section.get("bars"):
            continue
        start = section.get("startSeconds")
        end = section.get("endSeconds")
        if isinstance(start, (int, float)) and isinstance(end, (int, float)) and end > start:
            raw = (float(end) - float(start)) / seconds_per_bar
            # Sections are written in fours; anything else is a parsing artefact.
            bars = max(4, int(round(raw / 4.0)) * 4)
            section["bars"] = bars
            from_timecodes += 1
        else:
            section["bars"] = DEFAULT_SECTION_BARS.get(str(section.get("type")), 8)

    total = sum(int(s.get("bars") or 0) for s in musical)
    minutes = total * seconds_per_bar / 60.0
    if from_timecodes:
        detail = f"Set section lengths from the transcript timecodes for {from_timecodes} section(s); the arrangement runs {total} bars (~{minutes:.1f} min at {int(tempo)} BPM)."
        reason = "The video already timed every section and none of it was being used."
    else:
        detail = f"Set section lengths from style defaults; the arrangement runs {total} bars (~{minutes:.1f} min at {int(tempo)} BPM)."
        reason = "No timecodes were available, and a section with no length gets an arbitrary one at build time."
    decision(decisions, "arrangement", detail, reason=reason, confidence="medium" if from_timecodes else "low")


#: Fallback lengths, used only when the transcript has no timecodes.
DEFAULT_SECTION_BARS: dict[str, int] = {
    "pre_intro": 4,
    "intro": 8,
    "verse": 16,
    "pre_build": 4,
    "build": 8,
    "drop": 16,
    "break": 8,
    "second_drop": 16,
    "outro": 8,
}


def ensure_section_flow(spec: dict[str, Any], decisions: list[dict[str, Any]], prompt: str | None = None) -> None:
    sections = [deepcopy(section) for section in spec.get("sections", []) or [] if isinstance(section, dict)]
    text = text_blob(spec, prompt).lower()
    if not has_musical_sections(sections):
        sections = [make_inferred_section(section_type, "No concrete chronological song sections were recoverable.") for section_type in ESSENTIAL_FLOW]
        decision(decisions, "arrangement", "Created a full intro/verse/build/drop/outro skeleton.", reason="The input did not provide a usable section map.")
    else:
        types = [section.get("type") for section in sections]
        if "intro" not in types and "pre_intro" not in types:
            sections.insert(0, make_inferred_section("intro", "Most references need an entry section before the first high-energy moment."))
            decision(decisions, "arrangement", "Added an inferred intro before the first concrete section.", reason="A cold start rarely gives enough context for a generated production.")
        types = [section.get("type") for section in sections]
        if "drop" in types and "build" not in types:
            insert_before_first(sections, "drop", make_inferred_section("build", "A drop reference needs a tension ramp even when the transcript skips it."))
            decision(decisions, "arrangement", "Added an inferred build before the first drop.", reason="The input mentions a payoff/drop but no setup.")
        types = [section.get("type") for section in sections]
        if "drop" not in types and "second_drop" not in types and not any(keyword in text for keyword in ("ambient", "score", "underscore")):
            insert_before_first(sections, "outro", make_inferred_section("drop", "A song request without a payoff still needs a main energy section."))
            decision(decisions, "arrangement", "Added an inferred main drop/payoff section.", reason="No central high-energy section was explicit.")
        types = [section.get("type") for section in sections]
        if ("second drop" in text or "second_drop" in types) and "second_drop" not in types:
            sections.extend(make_inferred_section(section_type, f"Input implies a second-drop escalation but omits the {section_type} step.") for section_type in SECOND_DROP_INSERT)
            decision(decisions, "arrangement", "Added break/build/second-drop escalation after the first drop.", reason="Second-drop language implies an energy reset and rebuild.")
        types = [section.get("type") for section in sections]
        if "outro" not in types:
            sections.append(make_inferred_section("outro", "Generated recipes should have a clean tail even if the source skips it."))
            decision(decisions, "arrangement", "Added an inferred outro.", reason="The source did not define how the arrangement exits.")
    spec["sections"] = reindex_sections(sections)
    spec["sectionCount"] = len(spec["sections"])


def section_default_roles(section_type: str, text: str) -> list[str]:
    defaults = SECTION_DEFAULTS.get(section_type, {}).get("trackRoles", [])
    roles = list(defaults)
    lowered = text.lower()
    if any(keyword in lowered for keyword in ("vocal", "chop", "tag", "vox")):
        roles.append("vocal")
    if any(keyword in lowered for keyword in ("sample", "loop", "slice")):
        roles.append("sample")
    if any(keyword in lowered for keyword in ("guitar", "pluck")):
        roles.extend(["guitar", "pluck"])
    if any(keyword in lowered for keyword in ("siren", "laser", "noise", "riser", "impact")):
        roles.append("fx")
    return ensure_unique(roles)


def ensure_section_roles_and_techniques(spec: dict[str, Any], decisions: list[dict[str, Any]]) -> None:
    for section in spec.get("sections", []) or []:
        section_type = section.get("type")
        local_text = normalize_space(
            " ".join(
                str(part)
                for part in (
                    section.get("label"),
                    section.get("summary"),
                    section.get("excerpt"),
                    section.get("transcriptText"),
                )
                if part
            )
        )
        default_roles = section_default_roles(str(section_type), local_text)
        before_roles = set(section.get("trackRoles") or [])
        section["trackRoles"] = ensure_unique(list(section.get("trackRoles") or []) + default_roles)
        default_techniques = SECTION_DEFAULTS.get(str(section_type), {}).get("techniques", [])
        before_techniques = set(section.get("techniques") or [])
        section["techniques"] = ensure_unique(list(section.get("techniques") or []) + list(default_techniques))
        if set(section["trackRoles"]) - before_roles:
            decision(
                decisions,
                "track roles",
                f"{section['label']}: filled roles {', '.join(sorted(set(section['trackRoles']) - before_roles))}.",
                reason="Section role coverage was incomplete for a buildable arrangement.",
            )
        if set(section["techniques"]) - before_techniques:
            decision(
                decisions,
                "techniques",
                f"{section['label']}: filled techniques {', '.join(sorted(set(section['techniques']) - before_techniques))}.",
                reason="The section needed production moves, not only instrument names.",
            )


def event_list(beats: list[float], **attrs: Any) -> list[dict[str, Any]]:
    return [{"beat": round(float(beat), 2), **attrs} for beat in beats]


def record_lane(section: dict[str, Any], lane: str, payload: dict[str, Any]) -> bool:
    lane_events = section.setdefault("laneEvents", {})
    if lane in lane_events:
        return False
    lane_events[lane] = payload
    return True


def ensure_lane_defaults(spec: dict[str, Any], decisions: list[dict[str, Any]], style_lane: str) -> None:
    progression = STYLE_DEFAULTS[style_lane]["progression"]
    for section in spec.get("sections", []) or []:
        section_type = section.get("type")
        roles = set(section.get("trackRoles") or [])
        added: list[str] = []
        if roles & {"chords", "pad", "pluck"}:
            if record_lane(
                section,
                "chords",
                {"kind": "progressionSymbols", "progressionSymbols": progression, "source": "fill_in_blanks"},
            ):
                added.append("chords")
        if roles & {"bass", "sub"}:
            bass_beats = [0.0, 2.0] if section_type not in {"drop", "second_drop"} else [0.0, 1.5, 2.5]
            if record_lane(
                section,
                "bass",
                {"kind": "beatPattern", "events": event_list(bass_beats, duration=0.72), "source": "fill_in_blanks"},
            ):
                added.append("bass")
        if "lead" in roles:
            source = "fill_in_blanks"
            if section_type in {"build", "pre_build"}:
                beats = [0.0, 0.5]
                key = "tease"
            elif section_type in {"drop", "second_drop"}:
                beats = [0.0, 0.5, 1.0, 2.0, 2.5]
                key = "hook"
            else:
                beats = [0.0, 1.0, 2.5]
                key = "motif"
            if record_lane(
                section,
                "lead",
                {"kind": "beatPattern", "events": event_list(beats, duration=0.42), "source": source, "motifRole": key},
            ):
                added.append("lead")
        if roles & {"drums", "kick"}:
            if record_lane(section, "kick", {"kind": "beatPattern", "events": event_list([0.0, 2.0]), "source": "fill_in_blanks"}):
                added.append("kick")
        if roles & {"drums", "snare", "clap"}:
            if record_lane(section, "snare", {"kind": "beatPattern", "events": event_list([1.0, 3.0]), "source": "fill_in_blanks"}):
                added.append("snare")
        if roles & {"clap"}:
            if record_lane(section, "clap", {"kind": "beatPattern", "events": event_list([1.0, 3.0], gain=0.8), "source": "fill_in_blanks"}):
                added.append("clap")
        if roles & {"hat", "ride"}:
            spacing = 0.25 if section_type in {"drop", "second_drop", "build"} else 0.5
            if record_lane(section, "hat", {"kind": "beatPattern", "spacingBeats": spacing, "events": event_list([0.0, spacing, spacing * 2, spacing * 3]), "source": "fill_in_blanks"}):
                added.append("hat")
        if section_type in {"build", "pre_build"} or "automation" in roles:
            if record_lane(
                section,
                "automation",
                {
                    "kind": "automationEnvelope",
                    "envelopes": [{"parameter": "filter", "targetLane": "lead", "start": 0.15, "end": 0.9, "curve": "ease_in", "barOffset": 0, "bars": 8}],
                    "source": "fill_in_blanks",
                },
            ):
                added.append("automation")
        if added:
            decision(
                decisions,
                "lane defaults",
                f"{section['label']}: added {', '.join(added)} starter lane data.",
                reason="No explicit enough lane events existed for those musical roles.",
            )


def rebuild_global_summaries(spec: dict[str, Any]) -> None:
    track_counter: Counter[str] = Counter()
    technique_counter: Counter[str] = Counter()
    plugin_counter: Counter[str] = Counter()
    section_track_refs: defaultdict[str, list[str]] = defaultdict(list)
    section_plugin_refs: defaultdict[str, list[str]] = defaultdict(list)
    for section in spec.get("sections", []) or []:
        section_id = section.get("id")
        for role in section.get("trackRoles", []) or []:
            track_counter[role] += 1
            if section_id:
                section_track_refs[role].append(section_id)
        for plugin in section.get("plugins", []) or []:
            plugin_counter[plugin] += 1
            if section_id:
                section_plugin_refs[plugin].append(section_id)
        for technique in section.get("techniques", []) or []:
            technique_counter[technique] += 1
    spec["globalTracks"] = [
        {"name": role, "mentions": count, "sections": section_track_refs[role]}
        for role, count in track_counter.most_common()
    ]
    spec["globalPlugins"] = [
        {"name": plugin, "mentions": count, "sections": section_plugin_refs[plugin]}
        for plugin, count in plugin_counter.most_common()
    ]
    spec["globalTechniques"] = [
        {"name": technique, "mentions": count}
        for technique, count in technique_counter.most_common()
    ]


def normalize_open_questions(spec: dict[str, Any], decisions: list[dict[str, Any]]) -> None:
    unresolved: list[str] = []
    expected_unknowns: list[str] = []
    for item in spec.get("openQuestions", []) or []:
        lowered = str(item).lower()
        if "bpm" in lowered or "key" in lowered or "tempo" in lowered:
            expected_unknowns.append(str(item))
            continue
        unresolved.append(str(item))
    if expected_unknowns:
        decision(
            decisions,
            "ambiguity",
            "Converted missing tempo/key questions into inferred defaults.",
            reason="Reference-derived recipes often omit exact project settings; these should not block generation.",
        )
    spec["openQuestions"] = unresolved
    if expected_unknowns:
        spec.setdefault("expectedAmbiguities", [])
        spec["expectedAmbiguities"] = ensure_unique(list(spec["expectedAmbiguities"]) + expected_unknowns)


def gaps_from_sound_check(report: dict[str, Any]) -> list[Gap]:
    """Turn a real sound-check report into targeted steps.

    This is the second half of the loop. The first pass guesses what a brief
    left out; once audio exists, the checker measures what actually went wrong,
    and every finding it emits carries the ids of the requirements that would
    have prevented it. Those come back as gaps with `confidence: "measured"` —
    they are not guesses any more, so they outrank the inferred ones and they
    carry the checker's own words as evidence.
    """
    if not isinstance(report, dict):
        return []
    gaps: list[Gap] = []
    seen: set[str] = set()

    for issue in report.get("issues") or []:
        if not isinstance(issue, dict):
            continue
        area = str(issue.get("area") or "")
        detail = str(issue.get("detail") or "").strip()
        ids = issue.get("requirementIds")
        if not isinstance(ids, list) or not ids:
            # Older reports predate the tagging; fall back to the area.
            ids = [r.id for r in requirements_for_area(area)]
        for requirement_id in ids:
            if requirement_id in seen:
                continue
            requirement = requirement_by_id(str(requirement_id))
            if requirement is None:
                continue
            seen.add(requirement.id)
            gaps.append(
                Gap(
                    id=requirement.id,
                    label=requirement.label,
                    why=requirement.why,
                    step=requirement.step,
                    area=requirement.area,
                    roles=requirement.roles,
                    confidence="measured",
                    source="sound-check",
                    evidence=f"The sound check measured this: {detail}" if detail else "",
                )
            )

    # The checker's own next actions are advice a human wrote for this song, so
    # they are worth carrying even when they map to no requirement.
    for action in (report.get("nextActions") or [])[:5]:
        text = str(action).strip()
        if not text or text.lower().startswith("run one human listen"):
            continue
        marker = f"soundcheck-action-{slugify(text)[:40]}"
        if marker in seen:
            continue
        seen.add(marker)
        gaps.append(
            Gap(
                id=marker,
                label="Sound-check follow-up",
                why="The sound check asked for this after listening to the rendered audio.",
                step=text,
                area="Recipe",
                confidence="measured",
                source="sound-check",
            )
        )
    return gaps


# How much a gap's confidence is worth when two gaps name the same requirement.
# "measured" is what the sound check heard in the render; "human" is what a
# person said after listening (listening_session.py); everything else is a
# guess made before any audio existed. A person's ear beats a guess, and a
# measurement is never overwritten by either.
CONFIDENCE_RANK: dict[str, int] = {"measured": 3, "human": 2}


def confidence_rank(confidence: Any) -> int:
    return CONFIDENCE_RANK.get(str(confidence or ""), 1)


def merge_gaps(existing: list[dict[str, Any]], found: list[Any]) -> list[dict[str, Any]]:
    """Combine gaps, letting a stronger finding replace a weaker one.

    ``found`` holds ``Gap`` objects from the rubric, or ready-made gap dicts
    (the listening session builds those, because it needs to carry a section
    id that ``Gap`` has no field for). Either way the winner is decided by
    ``confidence_rank``: measured >= human > inferred.
    """
    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in list(existing or []):
        if not isinstance(item, dict):
            continue
        key = str(item.get("id") or item.get("requirementId") or len(order))
        if key not in by_id:
            order.append(key)
        by_id[key] = item
    for gap in found:
        if isinstance(gap, dict):
            payload = dict(gap)
            gap_id = str(payload.get("id") or payload.get("requirementId") or "")
            if not gap_id:
                continue
            payload.setdefault("id", gap_id)
        else:
            gap_id = gap.id
            payload = {
                "id": gap.id,
                "label": gap.label,
                "why": gap.why,
                "step": gap.step,
                "soundCheckArea": gap.area,
                "roles": list(gap.roles),
                "confidence": gap.confidence,
                "source": gap.source,
            }
            if gap.evidence:
                payload["evidence"] = gap.evidence
        previous = by_id.get(gap_id)
        if previous is None:
            order.append(gap_id)
            by_id[gap_id] = payload
            continue
        # A stronger finding beats a weaker one; otherwise keep what we had,
        # so re-running the filler never churns a stable spec.
        if confidence_rank(payload.get("confidence")) > confidence_rank(previous.get("confidence")):
            by_id[gap_id] = payload
    return [by_id[key] for key in order if key in by_id]


def fill_in_blanks(
    spec: dict[str, Any],
    *,
    prompt: str | None = None,
    sound_check: dict[str, Any] | None = None,
) -> dict[str, Any]:
    enriched = deepcopy(spec)
    existing_fill = deepcopy(enriched.get("fillInBlanks") or {})
    existing_decisions = existing_fill.get("decisions") or []
    decisions: list[dict[str, Any]] = []
    style_lane = str(existing_fill.get("styleLane") or detect_style_lane(enriched, prompt))
    style = STYLE_DEFAULTS[style_lane]

    if not enriched.get("tempoHint"):
        enriched["tempoHint"] = style["tempo"]
        decision(decisions, "tempo", f"Set BPM to {style['tempo']}.", reason=f"{style_lane} uses this as a practical starter tempo.", confidence="low")
    if not enriched.get("keyHints"):
        enriched["keyHints"] = [style["key"]]
        decision(decisions, "key", f"Set key hint to {style['key']}.", reason="No explicit key was available; the renderer needs a harmonic center.", confidence="low")

    normalize_role_aliases(enriched, decisions)
    rescue_unclassified_sections(enriched, decisions)
    order_sections_canonically(enriched, decisions)
    resolve_duplicate_sections(enriched, decisions)
    reindex_sections(enriched.get("sections") or [])
    assign_section_bars(enriched, decisions, style_lane)

    ensure_section_flow(enriched, decisions, prompt)
    # ensure_section_flow inserts whatever the arrangement was missing, and it
    # inserts in place rather than in order, so canonicalise once more now that
    # the final set of sections is known.
    order_sections_canonically(enriched, decisions)
    reindex_sections(enriched.get("sections") or [])
    assign_section_bars(enriched, decisions, style_lane)

    ensure_section_roles_and_techniques(enriched, decisions)
    ensure_lane_defaults(enriched, decisions, style_lane)
    rebuild_global_summaries(enriched)
    normalize_open_questions(enriched, decisions)

    # Everything above fills blanks in fields the transcript already had. This
    # pass is the other half of the job: production steps the brief never
    # mentioned at all, found by asking what a song of this kind needs and what
    # the sound check would later complain about.
    # Structure comes from the enriched spec — the arrangement that will actually
    # be built, including the sections the passes above just added. Intent comes
    # from the original, because those same passes inject "sidechain" and
    # "reverb" into every drop, and asking the enriched spec whether the author
    # covered something would always answer yes.
    found_gaps = find_gaps(enriched, style_lane, prompt=prompt, intent=spec)
    if sound_check:
        found_gaps = found_gaps + gaps_from_sound_check(sound_check)
    gaps = merge_gaps(existing_fill.get("gaps") or [], found_gaps)
    for gap in found_gaps:
        decisions.append(gap.as_decision())

    coverage = list(enriched.get("coverageChecklist", []) or [])
    coverage.append("Fill-in-blanks pass: every musical section has roles, techniques, and starter lane data where practical.")
    coverage.append("Exact-source details remain optional evidence, not blockers, unless the user explicitly asks for a forensic remake.")
    enriched["coverageChecklist"] = ensure_unique(coverage)
    combined_decisions: list[dict[str, Any]] = []
    seen_decisions: set[str] = set()
    for item in list(existing_decisions) + decisions:
        marker = json.dumps(item, sort_keys=True)
        if marker in seen_decisions:
            continue
        seen_decisions.add(marker)
        combined_decisions.append(item)
    enriched["fillInBlanks"] = {
        "schemaVersion": 2,
        "styleLane": style_lane,
        "gaps": gaps,
        "policy": existing_fill.get("policy") or "Infer plausible production defaults from the brief; do not claim exact original samples, patches, MIDI, or mix values without evidence.",
        "decisions": combined_decisions,
        "mixTargets": existing_fill.get("mixTargets") or style["mixTargets"],
        "postRenderLoop": [
            "Render the project or inspect existing stems.",
            "Run `python3 tools/does_this_sound_good.py --project-id <project-id> --format json > check.json`.",
            "Feed it straight back: `python3 tools/fill_in_blanks.py --input-json <spec> --feedback-json check.json`."
            " Every finding is tagged with the requirements that would have prevented it, so the next pass"
            " gets measured steps instead of fresh guesses.",
            "Re-materialize and log the pass with `python3 tools/songlab.py iterate --project-id <id> --note ...`.",
        ],
    }
    enriched["derivedPrompt"] = enriched.get("derivedPrompt") or (
        f"Build an original Neon Studio project from the reference recipe using inferred {style_lane} defaults where details are missing."
    )
    return enriched


def render_markdown(spec: dict[str, Any]) -> str:
    fill = spec.get("fillInBlanks") or {}
    lines = [
        f"# Fill In The Blanks: {spec.get('titleHint') or spec.get('projectId')}",
        "",
        "## Policy",
        "",
        str(fill.get("policy") or "No fill-in-blanks metadata found."),
        "",
        "## Defaults",
        "",
        f"- Style lane: `{fill.get('styleLane', 'unset')}`",
        f"- Tempo: `{spec.get('tempoHint') or 'unset'}`",
        f"- Key: `{', '.join(spec.get('keyHints') or []) or 'unset'}`",
        "",
        "## Inferred Decisions",
        "",
    ]
    decisions = fill.get("decisions") or []
    if decisions:
        for item in decisions:
            lines.append(f"- {item['area']}: {item['detail']} Reason: {item['reason']}")
    else:
        lines.append("- No additional decisions were needed.")
    gaps = fill.get("gaps") or []
    if gaps:
        measured = [g for g in gaps if g.get("confidence") == "measured"]
        human = [g for g in gaps if g.get("confidence") == "human"]
        inferred = [g for g in gaps if g.get("confidence") not in ("measured", "human")]
        lines.extend(["", "## Missing Steps", "", 
                      "Production steps the brief never mentioned, added so the song is buildable"
                      " and so the sound check has less to complain about.", ""])
        if measured:
            lines.extend(["### Measured — the sound check found these in the render", ""])
            for gap in measured:
                lines.append(f"- **{gap.get('label')}** — {gap.get('step')}")
                if gap.get("evidence"):
                    lines.append(f"  - {gap['evidence']}")
        if human:
            if measured:
                lines.append("")
            lines.extend(["### Heard — a person said this after listening", ""])
            for gap in human:
                lines.append(f"- **{gap.get('label')}** — {gap.get('step')}")
                if gap.get("evidence"):
                    lines.append(f"  - {gap['evidence']}")
        if inferred:
            if measured or human:
                lines.extend(["", "### Inferred — not mentioned in the brief", ""])
            for gap in inferred:
                area = gap.get("soundCheckArea")
                suffix = f" _(pre-empts: {area})_" if area and area != "none" else ""
                lines.append(f"- **{gap.get('label')}** — {gap.get('step')}{suffix}")
                lines.append(f"  - Why: {gap.get('why')}")

    lines.extend(["", "## Section Coverage", ""])
    for section in spec.get("sections", []) or []:
        marker = "inferred" if section.get("inferred") else "source"
        roles = ", ".join(section.get("trackRoles", []) or [])
        techniques = ", ".join(section.get("techniques", []) or [])
        lines.append(f"- {section.get('label')}: `{marker}` roles={roles or 'none'} techniques={techniques or 'none'}")
    lines.extend(["", "## Post-Render Loop", ""])
    for item in fill.get("postRenderLoop", []) or []:
        lines.append(f"- {item}")
    if spec.get("expectedAmbiguities"):
        lines.extend(["", "## Expected Ambiguities", ""])
        for item in spec["expectedAmbiguities"]:
            lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Infer useful production defaults for an incomplete Neon Studio transcript spec.")
    parser.add_argument("--input-json", required=True, help="Path to transcript_spec.json.")
    parser.add_argument("--output-json", help="Optional path for the enriched spec.")
    parser.add_argument("--output-md", help="Optional path for the fill-in-blanks report.")
    parser.add_argument("--prompt", help="Optional user prompt or style lane.")
    parser.add_argument(
        "--feedback-json",
        help="Path to a does_this_sound_good.py JSON report. Its findings become measured steps.",
    )
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    input_path = Path(args.input_json)
    spec = json.loads(input_path.read_text(encoding="utf-8"))
    sound_check = None
    if args.feedback_json:
        feedback_path = Path(args.feedback_json)
        if not feedback_path.exists():
            print(f"feedback file not found: {feedback_path}", file=sys.stderr)
            return 2
        sound_check = json.loads(feedback_path.read_text(encoding="utf-8"))
    enriched = fill_in_blanks(spec, prompt=args.prompt, sound_check=sound_check)
    if args.output_json:
        Path(args.output_json).write_text(json.dumps(enriched, indent=2) + "\n", encoding="utf-8")
    if args.output_md:
        Path(args.output_md).write_text(render_markdown(enriched), encoding="utf-8")
    if args.format == "markdown":
        print(render_markdown(enriched).rstrip())
    else:
        print(json.dumps(enriched, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
