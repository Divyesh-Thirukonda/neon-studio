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
    "lead": ("lead", "lead line", "drop lead", "square lead", "hook"),
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


def infer_section(text: str) -> tuple[str, str, bool]:
    lowered = text.lower()
    for section_id, label, keywords in SECTION_RULES:
        if any(keyword in lowered for keyword in keywords):
            return section_id, label, True
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
            "sourceSegmentCount": len(item["texts"]),
            "trackRoles": item["trackRoles"],
            "plugins": item["plugins"],
            "techniques": item["techniques"],
        })
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


def infer_title_hint(text: str, project_id: str) -> str | None:
    patterns = (
        r"song(?:\s+is\s+going\s+to\s+be|\s+called)\s+([a-z0-9][a-z0-9' !?-]{2,60})",
        r"how i made my song\s+([a-z0-9][a-z0-9' !?-]{2,60})",
        r"remaking (?:his|her|the) song\s+([a-z0-9][a-z0-9' !?-]{2,60})",
    )
    lowered = text.lower()
    for pattern in patterns:
        match = re.search(pattern, lowered, flags=re.IGNORECASE)
        if match:
            return normalize_space(match.group(1)).title()
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
        "schemaVersion": 1,
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
