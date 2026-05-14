#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any


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


def fill_in_blanks(spec: dict[str, Any], *, prompt: str | None = None) -> dict[str, Any]:
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

    ensure_section_flow(enriched, decisions, prompt)
    ensure_section_roles_and_techniques(enriched, decisions)
    ensure_lane_defaults(enriched, decisions, style_lane)
    rebuild_global_summaries(enriched)
    normalize_open_questions(enriched, decisions)

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
        "schemaVersion": 1,
        "styleLane": style_lane,
        "policy": existing_fill.get("policy") or "Infer plausible production defaults from the brief; do not claim exact original samples, patches, MIDI, or mix values without evidence.",
        "decisions": combined_decisions,
        "mixTargets": existing_fill.get("mixTargets") or style["mixTargets"],
        "postRenderLoop": existing_fill.get("postRenderLoop") or [
            "Render the project or inspect existing stems.",
            "Run `python3 tools/does_this_sound_good.py --project-id <project-id> --format markdown`.",
            "Convert the checker's loudness, low-end, stereo, missing-audio, and arrangement findings into the next Songlab iteration note.",
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
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    input_path = Path(args.input_json)
    spec = json.loads(input_path.read_text(encoding="utf-8"))
    enriched = fill_in_blanks(spec, prompt=args.prompt)
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
