#!/usr/bin/env python3
"""transcript_fidelity.py - does the output match what the description said?

`does_this_sound_good.py` asks "is it good". This asks "is it what was asked
for". A project can score well on the first and still ignore half of the
tutorial it was built from, so both are needed before a human decides.

Claims come from what the author actually stated: the transcript text and the
parts of the transcript spec that were parsed from it. Nothing under
`fillInBlanks` is used - those are our own inferences, not their words. Every
claim is checked against the rendered stems when they exist, and falls back to
the project file when they do not; the `verifiedBy` field says which, so a
reader never mistakes "the effect is switched on" for "the audio does it".

CLI:
  transcript_fidelity.py --root ROOT --project-id ID [--format json|markdown]
  transcript_fidelity.py --project PATH --spec PATH [--transcript PATH]
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import wave
from pathlib import Path
from typing import Any, Optional

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from vocal_autotune import SR, estimate_f0, freq_to_midi  # noqa: E402

try:
    import llm  # noqa: E402
except ImportError:  # pragma: no cover - keeps the checker usable standalone
    llm = None  # type: ignore[assignment]

try:
    from project_materializer import ROLE_TO_TRACKS  # noqa: E402
except ImportError:  # pragma: no cover - keeps the checker usable standalone
    # A copy of the materializer's table so a broken import does not turn every
    # role claim into "unverifiable". The real table is authoritative.
    ROLE_TO_TRACKS = {
        "drums": ("drums",), "kick": ("drums",), "snare": ("drums",), "clap": ("clap-stack",),
        "hat": ("hat-ride",), "ride": ("hat-ride",), "crash": ("fx",), "bass": ("bass",),
        "sub": ("sub",), "chords": ("chords",), "pad": ("chords",), "lead": ("lead",),
        "guitar": ("guitar",), "pluck": ("plucks",), "vocal": ("vocals",), "noise": ("fx",),
        "riser": ("fx",), "downlifter": ("fx",), "impact": ("fx",), "crowd": ("fx",),
        "reverse": ("fx",), "fx": ("fx",), "automation": ("filter-auto",), "sample": ("sample",),
    }


EPSILON = 1e-12
MUSICAL_TYPES = ("pre_intro", "intro", "verse", "pre_build", "build", "drop", "second_drop", "break", "outro")

# Which stems carry the evidence for each technique, in preference order.
TECHNIQUE_STEMS: dict[str, tuple[str, ...]] = {
    "sidechain": ("sub", "bass"),
    "reverb": ("lead", "chords"),
    "delay": ("lead",),
    "stereo": ("chords", "fx"),
    "filtering": ("lead", "chords"),
    "automation": ("lead", "chords", "drums"),
    "distortion": ("bass", "lead"),
    "layering": ("drums",),
    "eq": ("lead", "chords", "vocals", "bass", "sub"),
    "compression": ("drums", "clap-stack"),
    "reverse": ("fx",),
}

# Effect-name fragments that count as "the project has this kind of effect"
# when no stem is available to listen to.
TECHNIQUE_EFFECT_WORDS: dict[str, tuple[str, ...]] = {
    "sidechain": ("sidechain", "duck", "pump"),
    "reverb": ("reverb", "plate", "hall", "room", "verb"),
    "delay": ("delay", "echo", "ping"),
    "stereo": ("stereo", "width", "wide", "spread", "chorus", "unison"),
    "filtering": ("filter", "lowpass", "low cut", "cutoff", "hpf", "lpf", "highpass"),
    "distortion": ("distort", "saturat", "drive", "clip", "crush"),
    "eq": ("eq", "air", "low cut", "high pass", "highpass"),
    "compression": ("comp", "glue", "limiter"),
    "reverse": ("reverse",),
    "layering": (),
    "automation": (),
}

# Techniques the parser emits that no measurement here can honestly confirm.
UNMEASURABLE_TECHNIQUES = ("resampling", "pitching", "call_response", "tease_hook", "arrangement_reuse")

# Tracks that read as layers of one instrument family when they all have content.
LAYER_FAMILIES: dict[str, tuple[str, ...]] = {
    "drums": ("drums", "clap-stack", "hat-ride"),
    "bass": ("bass", "sub"),
    "lead": ("lead", "lead-double", "plucks"),
    "chords": ("chords", "pad"),
}

SECTION_LABEL_RE = re.compile(
    r"\b(pre[- ]?intro|intro|verse|pre[- ]?build|breakdown|break|build[- ]?up|build|second drop|drop|outro)\b\s*(?:#\s*)?(\d)?",
    re.IGNORECASE,
)
STATED_SECTION_RE = re.compile(
    r"\bsection\s+\d+\s+([A-Za-z][A-Za-z0-9 -]{0,20}?)\s+bars?\s+(\d+)\s*(?:-|to|–)\s*(\d+)",
    re.IGNORECASE,
)
# "Automation: bars 17-24 lead.filter 0.35->0.95 ease-in | drums.volume 0.35->0.85 step"
AUTOMATION_RANGE_RE = re.compile(r"bars?\s+(\d+)\s*(?:-|to|–)\s*(\d+)\s*:?", re.IGNORECASE)
AUTOMATION_MOVE_RE = re.compile(r"([a-z]+)\.([a-z]+)\s+(\d+(?:\.\d+)?)\s*->\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
NUMBER_UNIT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(khz|hz|bpm|db|ms)\b", re.IGNORECASE)
TRANSPOSE_RE = re.compile(r"transpose\s*([+-]?\s*\d+)", re.IGNORECASE)
OCTAVE_DIRECTION_RE = re.compile(r"\boctave\s+(down|up|lower|higher|below|above)\b", re.IGNORECASE)
DROP_TWO_RE = re.compile(r"\b(second drop|drop\s*2|drop two|final drop|last drop)\b", re.IGNORECASE)
NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
# A number followed by one of these is a reading, not a count or a name.
UNIT_AFTER_NUMBER_RE = re.compile(r"\s*(?:%|(?:dBFS|dB|kHz|Hz|ms|s|bars?|BPM|st|semitones?)\b)", re.IGNORECASE)

# ---------------------------------------------------------------------------
# What the model is allowed to do here
#
# Two jobs, both language: read the raw transcript for claims the regexes
# missed, in exactly the shapes the Checker already measures; and, once every
# claim is measured, write the fix for each missed one in terms of the
# project's real tracks and effects, plus the summary. Every claim it adds
# must quote the sentence it read it in, and every name it uses must exist.
# It never touches a measurement or the score.
# ---------------------------------------------------------------------------

KNOWN_TECHNIQUES: tuple[str, ...] = tuple(TECHNIQUE_STEMS) + UNMEASURABLE_TECHNIQUES
CHUNK_CHARS = 24000
MIN_QUOTE_CHARS = 8

CLAIM_ROLE = (
    "You read a music-production transcript and list the concrete, checkable things the author says "
    "the finished track does. You only report what is stated; you never infer, and you never report a "
    "technique, section, role, or number that is not in the text. Every claim carries the exact "
    "sentence (verbatim, copied from the text) you read it in. Use only the section names, technique "
    "names, and role names you are given; skip anything that does not fit them."
)
CLAIM_SCHEMA = {
    "claims": [
        {"kind": "technique", "section": "a section name from the list, or 'whole track'", "technique": "a technique from the list", "quote": "the verbatim sentence"},
        {"kind": "role", "section": "a section name from the list", "role": "a role from the list", "quote": "the verbatim sentence"},
        {"kind": "tempo", "bpm": 120, "quote": "the verbatim sentence"},
        {"kind": "key", "key": "e.g. D major, F# minor", "quote": "the verbatim sentence"},
        {"kind": "automation", "track": "track id from the list, or master", "parameter": "e.g. filter, volume, width", "from": 0.2, "to": 0.8, "firstBar": 1, "lastBar": 8, "quote": "the verbatim sentence"},
        {"kind": "transpose", "section": "a section name from the list", "reference": "the section it is copied from, or null", "semitones": 12, "quote": "the verbatim sentence"},
        {"kind": "octaveDouble", "section": "a section name from the list", "quote": "the verbatim sentence"},
    ]
}

FIX_ROLE = (
    "You are a producer's engineer reading a fidelity report: each claim is something the tutorial said "
    "the track does, with a measured status and the evidence. The statuses, evidence, and score are "
    "measured and final - do not dispute or restate them as if you had listened. For every claim that is "
    "missing or contradicted, write the one edit that would make it true, naming the real track (by its "
    "id from the track list) and, where one exists on that track, the real effect to touch. Rank the fixes "
    "by how much of the tutorial's intent they recover. Every number you write must come from the report. "
    "Write plainly, in the second person."
)
FIX_SCHEMA = {
    "summary": "two to four sentences on how faithful the project is to the transcript and what the biggest gaps are",
    "fixes": [
        {
            "claimId": "the claim id, e.g. claim-03",
            "action": "one concrete instruction naming the track and, if any, the effect and section",
            "track": "track id from the track list, or null",
            "effect": "the name of an effect on that track, or null",
            "section": "a section name from the list, or null",
            "why": "one sentence tying the edit to the measured evidence",
        }
    ],
}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def dbfs(value: float) -> float:
    return 20.0 * math.log10(max(float(value), EPSILON))


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def safe_project_id(value: str) -> str:
    base = Path(value).name.replace(".neon.json", "")
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", base).strip("-_")
    return cleaned or "project"


def normalize_key(value: Optional[str]) -> Optional[str]:
    """'E minor', 'E Minor', 'Em', 'e min', 'Emaj' all become 'e minor' / 'e major'."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip().lower().replace("♯", "#").replace("♭", "b")
    match = re.match(r"^([a-g](?:#|b)?)\s*[-_ ]?\s*(major|minor|maj|min|m|)$", text)
    if not match:
        return None
    root, mode = match.groups()
    mode = mode.strip()
    if mode in ("minor", "min", "m"):
        return f"{root} minor"
    return f"{root} major"


def sentences(text: str) -> list[str]:
    return [sentence for _, sentence in sentence_spans(text)]


def sentence_spans(text: str) -> list[tuple[int, str]]:
    """(character offset, sentence) pairs, so a sentence can be tied back to
    the 'Section N ...' statement that precedes it in the transcript."""
    out: list[tuple[int, str]] = []
    position = 0
    for part in re.split(r"(?<=[.;!?])\s+|\n+", text or ""):
        index = text.find(part, position)
        if index < 0:
            index = position
        if part.strip():
            out.append((index, part.strip()))
        position = index + len(part)
    return out


def chunk_text(text: str, limit: int = CHUNK_CHARS) -> list[str]:
    """Pieces of at most `limit` characters, split at sentence boundaries."""
    if len(text) <= limit:
        return [text] if text.strip() else []
    chunks: list[str] = []
    current = ""
    for _, sentence in sentence_spans(text):
        if current and len(current) + len(sentence) + 1 > limit:
            chunks.append(current)
            current = ""
        while len(sentence) > limit:      # one monstrous run-on: hard split
            chunks.append(sentence[:limit])
            sentence = sentence[limit:]
        current = (current + " " + sentence).strip()
    if current:
        chunks.append(current)
    return chunks


def collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def quote_in_text(quote: str, text: str) -> bool:
    """The evidence rule: the quote must appear in the transcript (whitespace
    collapsed; case is forgiven because models like to fix capitalisation)."""
    needle = collapse_ws(quote)
    if len(needle) < MIN_QUOTE_CHARS:
        return False
    haystack = collapse_ws(text)
    return needle in haystack or needle.lower() in haystack.lower()


def numbers_in(text: str) -> list[float]:
    out: list[float] = []
    for token in NUMBER_RE.findall(text or ""):
        try:
            out.append(float(token))
        except ValueError:
            continue
    return out


def numbers_are_grounded(text: str, facts: str) -> bool:
    """Every number the model wrote must be one it was given (within rounding).
    A small integer with no unit passes: 'Drop 2', '2 of' and 'beat 3' are not
    readings. One with a unit ('cut 3 dB', '2 bars') is a reading and must be
    in the facts like any other."""
    allowed = numbers_in(facts)
    text = text or ""
    for match in NUMBER_RE.finditer(text):
        try:
            value = float(match.group())
        except ValueError:
            continue
        unit_bearing = UNIT_AFTER_NUMBER_RE.match(text, match.end()) is not None
        if 0 <= value <= 4 and value.is_integer() and not unit_bearing:
            continue
        if not any(abs(value - fact) <= max(0.05, abs(fact) * 0.01) for fact in allowed):
            return False
    return True


def parse_section_label(label: str) -> Optional[tuple[str, Optional[int]]]:
    """'Drop 2' -> ('drop', 2); 'Second Drop' -> ('drop', 2); 'Intro' -> ('intro', None)."""
    match = SECTION_LABEL_RE.search(label or "")
    if not match:
        return None
    word = match.group(1).lower().replace("-", " ")
    ordinal = int(match.group(2)) if match.group(2) else None
    if word == "second drop":
        return "drop", 2
    if word in ("breakdown", "break"):
        return "break", ordinal
    if word in ("build", "build up", "buildup"):
        return "build", ordinal
    if word == "pre build":
        return "pre_build", ordinal
    if word == "pre intro":
        return "pre_intro", ordinal
    return word, ordinal


def spec_section_key(section: dict[str, Any]) -> Optional[tuple[str, int]]:
    """The author's own 'Section N Drop 1 bars 25-40' wins over the parser's
    type label, because the parser has been seen to file a drop under 'intro'."""
    stated = STATED_SECTION_RE.search(str(section.get("transcriptText") or ""))
    if stated:
        parsed = parse_section_label(stated.group(1))
        if parsed:
            return parsed[0], parsed[1] or 1
    section_type = str(section.get("type") or "")
    if section_type not in MUSICAL_TYPES:
        return None
    ordinal = int(section.get("ordinalWithinType") or 1)
    if section_type == "second_drop":
        return "drop", 2
    return section_type, ordinal


# ---------------------------------------------------------------------------
# Project reading
# ---------------------------------------------------------------------------


def project_path_for(root: Path, project_id: Optional[str], project_path: Optional[str]) -> Path:
    if project_path:
        return Path(project_path).expanduser().resolve()
    if not project_id:
        raise ValueError("Provide --project or --project-id.")
    project_id = safe_project_id(project_id)
    for candidate in (root / "data" / "projects" / f"{project_id}.neon.json",
                      root / "factory" / "projects" / f"{project_id}.neon.json"):
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"No project found for {project_id}.")


def spec_path_for(root: Path, project_id: Optional[str], spec_path: Optional[str]) -> Path:
    if spec_path:
        return Path(spec_path).expanduser().resolve()
    if not project_id:
        raise ValueError("Provide --spec or --project-id.")
    candidate = root / "songlab" / "projects" / safe_project_id(project_id) / "transcript_spec.json"
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"No transcript spec found for {project_id}.")


def transcript_text_for(spec_path: Path, spec: dict[str, Any], explicit: Optional[str]) -> str:
    if explicit:
        path = Path(explicit).expanduser()
        if path.exists():
            return path.read_text(encoding="utf-8")
    sibling = spec_path.parent / "transcript.txt"
    if sibling.exists():
        return sibling.read_text(encoding="utf-8")
    # No file: the per-section text the parser kept is still the author's words.
    return "\n".join(str(section.get("transcriptText") or "") for section in spec.get("sections", []))


def audio_path_for(root: Path, file_value: Optional[str]) -> Optional[Path]:
    if not file_value:
        return None
    if file_value.startswith("file://"):
        return Path(file_value[7:]).expanduser()
    if file_value.startswith("/") and not file_value.startswith("/api/audio/"):
        return Path(file_value).expanduser()
    name = Path(file_value).name
    cleaned = file_value[1:] if file_value.startswith("/") else file_value
    for candidate in (root / "exports" / name, root / cleaned):
        if candidate.exists():
            return candidate
    return None


def tracks_by_id(project: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for track in project.get("snapshot", {}).get("tracks", []) or []:
        if isinstance(track, dict) and track.get("id"):
            out[str(track["id"])] = track
    return out


def track_file(project: dict[str, Any], track_id: str) -> Optional[str]:
    track = tracks_by_id(project).get(track_id)
    if track and isinstance(track.get("file"), str) and track["file"]:
        return str(track["file"])
    for asset in project.get("assets", []) or []:
        if isinstance(asset, dict) and asset.get("trackId") == track_id and isinstance(asset.get("file"), str):
            return str(asset["file"])
    return None


def track_has_content(root: Path, project: dict[str, Any], track_id: str) -> tuple[bool, str]:
    """A track counts as audible when its audio file exists on disk, or it has
    notes or steps the mixdown would synthesise, or (automation lanes) it drives
    at least one lane. Returns (has_content, why)."""
    track = tracks_by_id(project).get(track_id)
    if track is None:
        return False, "no such track"
    snapshot = project.get("snapshot", {})
    path = audio_path_for(root, track_file(project, track_id))
    if path is not None and path.exists():
        return True, f"audio {path.name}"
    if track.get("kind") == "automation":
        lanes = [lane for lane in snapshot.get("automationLanes", []) or []
                 if isinstance(lane, dict) and len(lane.get("points") or []) >= 2]
        if lanes:
            return True, f"{len(lanes)} automation lane(s)"
        return False, "no automation lanes"
    notes = [note for note in snapshot.get("notes", []) or []
             if isinstance(note, dict) and str(note.get("trackId", "")) == track_id]
    if notes:
        return True, f"{len(notes)} notes"
    steps = [step for step in (track.get("steps") or []) if isinstance(step, (int, float))]
    if steps and track.get("kind") in ("drum", "instrument"):
        return True, f"{len(steps)} steps"
    if track_file(project, track_id):
        return False, f"file missing on disk ({Path(str(track_file(project, track_id))).name})"
    return False, "no audio, notes, or steps"


def project_section_spans(project: dict[str, Any]) -> dict[tuple[str, int], tuple[float, float]]:
    """Section spans in 0-indexed bars, read off the clip names ('Drop 1 drums'
    at bar 24 for 16 bars). Clips whose name has no ordinal are folded into an
    overlapping span of the same type when one exists."""
    spans: dict[tuple[str, int], list[float]] = {}
    plain: list[tuple[str, float, float]] = []
    for track in project.get("snapshot", {}).get("tracks", []) or []:
        for clip in (track.get("clips") or []) if isinstance(track, dict) else []:
            if not isinstance(clip, dict):
                continue
            parsed = parse_section_label(str(clip.get("name") or ""))
            if not parsed:
                continue
            start = float(clip.get("startBar") or 0)
            end = start + float(clip.get("bars") or 0)
            base, ordinal = parsed
            if ordinal is None:
                plain.append((base, start, end))
                continue
            key = (base, ordinal)
            current = spans.setdefault(key, [start, end])
            current[0] = min(current[0], start)
            current[1] = max(current[1], end)
    for base, start, end in plain:
        same = [key for key in spans if key[0] == base]
        overlapping = [key for key in same if spans[key][0] < end and start < spans[key][1]]
        if overlapping:
            key = overlapping[0]
        else:
            # A plain "Drop" next to a "Second Drop" is the first drop, not a
            # third one: take the lowest ordinal nobody has claimed.
            ordinal = 1
            while (base, ordinal) in spans:
                ordinal += 1
            key = (base, ordinal)
        current = spans.setdefault(key, [start, end])
        current[0] = min(current[0], start)
        current[1] = max(current[1], end)
    return {key: (value[0], value[1]) for key, value in spans.items()}


def project_section_order(project: dict[str, Any], spans: dict[tuple[str, int], tuple[float, float]]) -> list[tuple[str, int]]:
    order: list[tuple[str, int]] = []
    for item in project.get("snapshot", {}).get("recipe", []) or []:
        if not isinstance(item, dict):
            continue
        parsed = parse_section_label(str(item.get("section") or ""))
        if not parsed:
            continue
        base, ordinal = parsed
        key = (base, ordinal or 1)
        if key not in order:
            order.append(key)
    if order:
        return order
    return [key for key, _ in sorted(spans.items(), key=lambda kv: kv[1][0])]


def whole_song_span(project: dict[str, Any], spans: dict[tuple[str, int], tuple[float, float]]) -> tuple[float, float]:
    end = 0.0
    for track in project.get("snapshot", {}).get("tracks", []) or []:
        for clip in (track.get("clips") or []) if isinstance(track, dict) else []:
            if isinstance(clip, dict):
                end = max(end, float(clip.get("startBar") or 0) + float(clip.get("bars") or 0))
    for _, (_, span_end) in spans.items():
        end = max(end, span_end)
    return 0.0, end


# ---------------------------------------------------------------------------
# Audio analysis
# ---------------------------------------------------------------------------


class StemCache:
    """Loads each stem once. Mono is what most checks use; stereo is kept for
    the width check."""

    def __init__(self, root: Path, project: dict[str, Any]) -> None:
        self.root = root
        self.project = project
        self._cache: dict[str, Optional[tuple[np.ndarray, np.ndarray]]] = {}

    def path(self, track_id: str) -> Optional[Path]:
        path = audio_path_for(self.root, track_file(self.project, track_id))
        return path if path is not None and path.exists() else None

    def load(self, track_id: str) -> Optional[tuple[np.ndarray, np.ndarray]]:
        if track_id in self._cache:
            return self._cache[track_id]
        path = self.path(track_id)
        result = None
        if path is not None:
            try:
                result = read_wav_both(path)
            except Exception:
                result = None
        self._cache[track_id] = result
        return result

    def mono(self, track_id: str) -> Optional[np.ndarray]:
        loaded = self.load(track_id)
        return loaded[0] if loaded else None

    def stereo(self, track_id: str) -> Optional[np.ndarray]:
        loaded = self.load(track_id)
        return loaded[1] if loaded else None


def read_wav_both(path: Path) -> tuple[np.ndarray, np.ndarray]:
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        sample_rate = handle.getframerate()
        width = handle.getsampwidth()
        raw = handle.readframes(handle.getnframes())
    if width == 2:
        audio = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 4:
        audio = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported WAV sample width: {width}")
    audio = audio.reshape(-1, channels)
    if channels == 1:
        audio = np.repeat(audio, 2, axis=1)
    elif channels > 2:
        audio = audio[:, :2]
    if sample_rate != SR and len(audio) > 1:
        old_x = np.linspace(0.0, 1.0, len(audio), endpoint=False)
        new_len = max(1, int(round(len(audio) * SR / sample_rate)))
        new_x = np.linspace(0.0, 1.0, new_len, endpoint=False)
        audio = np.stack([np.interp(new_x, old_x, audio[:, 0]), np.interp(new_x, old_x, audio[:, 1])], axis=1).astype(np.float32)
    mono = np.nan_to_num(audio.mean(axis=1)).astype(np.float32)
    return mono, np.nan_to_num(audio).astype(np.float32)


def slice_seconds(x: np.ndarray, start_s: float, end_s: float) -> np.ndarray:
    a = max(0, int(start_s * SR))
    b = max(a, min(len(x), int(end_s * SR)))
    return x[a:b]


def rms_envelope(x: np.ndarray, win_s: float, hop_s: float) -> np.ndarray:
    n = max(1, int(win_s * SR))
    hop = max(1, int(hop_s * SR))
    if len(x) < n:
        return np.zeros(0, dtype=np.float64)
    squares = np.concatenate([[0.0], np.cumsum(x.astype(np.float64) ** 2)])
    starts = np.arange(0, len(x) - n + 1, hop)
    return np.sqrt((squares[starts + n] - squares[starts]) / n + EPSILON)


def rms_db(x: np.ndarray) -> float:
    if x.size == 0:
        return -120.0
    return dbfs(float(np.sqrt(np.mean(x.astype(np.float64) ** 2))))


def is_silent(x: np.ndarray) -> bool:
    return rms_db(x) < -55.0


def lowpass_fft(x: np.ndarray, cutoff_hz: float) -> np.ndarray:
    """Brick-wall lowpass. Used to isolate kicks in a drum stem; the exact shape
    of the filter does not matter, only that hats and claps drop out."""
    if x.size < 16:
        return x
    spectrum = np.fft.rfft(x.astype(np.float64))
    freqs = np.fft.rfftfreq(len(x), d=1.0 / SR)
    spectrum[freqs > cutoff_hz] = 0.0
    return np.fft.irfft(spectrum, n=len(x)).astype(np.float32)


def detect_onsets(x: np.ndarray, hop_s: float = 0.005, min_gap_s: float = 0.06) -> list[float]:
    """Onset times in seconds: envelope samples that jump 2.5x over 10 ms and
    clear a quarter of the section's loudest level."""
    env = rms_envelope(x, 0.01, hop_s)
    if env.size < 3:
        return []
    threshold = float(np.max(env)) * 0.25
    if threshold < 1e-4:
        return []
    onsets: list[int] = []
    min_gap = int(min_gap_s / hop_s)
    for i in range(2, len(env)):
        if env[i] > threshold and env[i] > env[i - 2] * 2.5 and (not onsets or i - onsets[-1] > min_gap):
            onsets.append(i)
    return [i * hop_s for i in onsets]


def sidechain_dip_db(bass: np.ndarray, kick_onsets: list[float]) -> Optional[float]:
    """Median dB by which the bass level right after each kick sits below the
    level it recovers to (or the level just before). A note that simply starts
    on the kick reads as ~0 dB; a ducked one reads as the depth of the duck."""
    env = rms_envelope(bass, 0.02, 0.01)
    if env.size == 0:
        return None
    dips: list[float] = []
    for onset in kick_onsets:
        j = int(onset / 0.01)
        during = env[j:j + 3]                # 0-40 ms after the kick
        after = env[j + 6:j + 22]            # 60-220 ms after: where a duck releases
        if during.size == 0 or after.size == 0:
            continue
        floor = float(np.min(during))
        recovered = float(np.max(after))
        before = float(env[j - 2]) if j >= 2 else recovered
        reference = max(recovered, before)
        if reference < 10 ** (-60 / 20):
            continue                          # bass is not playing here
        dips.append(20.0 * math.log10(reference / max(floor, EPSILON)))
    if len(dips) < 4:
        return None
    return float(np.median(dips))


def decay_time_30db(x: np.ndarray, section_seconds: float) -> Optional[tuple[float, bool]]:
    """Seconds for the envelope to fall 30 dB after the last onset inside the
    section. `x` should run past the section end so the tail is visible.
    Returns (seconds, truncated) where truncated means the next note arrived
    before the tail reached -30 dB, so the true decay is at least that long."""
    hop = 0.005
    env = rms_envelope(x, 0.01, hop)
    onsets = detect_onsets(x, hop)
    inside = [t for t in onsets if t < section_seconds]
    if not inside or env.size == 0:
        return None
    last = inside[-1]
    following = [t for t in onsets if t > last + 0.05]
    start = int(last / hop)
    peak_index = start + int(np.argmax(env[start:start + 40])) if start < env.size else start
    peak = float(env[min(peak_index, env.size - 1)])
    if peak < 1e-4:
        return None
    limit = int(following[0] / hop) if following else env.size
    target = peak * (10 ** (-30 / 20))
    for k in range(peak_index, min(limit, env.size)):
        if env[k] < target:
            return (k - peak_index) * hop, False
    return (min(limit, env.size) - peak_index) * hop, True


def tail_residual_db(x: np.ndarray, after_s: float = 0.25, min_gap_s: float = 0.3) -> Optional[tuple[float, int]]:
    """How much of a note is still there `after_s` after it peaks, in dB, taken
    over every note that is followed by at least `min_gap_s` of no new onset.
    A dry synth with a short release is far below -40 dB by then; a reverb or
    delay send leaves it in the -30s or above. Returns (median dB, notes used)."""
    hop = 0.005
    env = rms_envelope(x, 0.01, hop)
    onsets = detect_onsets(x, hop)
    if env.size == 0 or not onsets:
        return None
    readings: list[float] = []
    for index, onset in enumerate(onsets):
        next_onset = onsets[index + 1] if index + 1 < len(onsets) else len(env) * hop
        if next_onset - onset < min_gap_s:
            continue
        start = int(onset / hop)
        window = env[start:start + 40]
        if window.size == 0:
            continue
        peak_index = start + int(np.argmax(window))
        peak = float(env[peak_index])
        later = peak_index + int(after_s / hop)
        if peak < 1e-4 or later >= env.size or later >= int(next_onset / hop):
            continue
        readings.append(20.0 * math.log10(max(float(env[later]), EPSILON) / peak))
    if not readings:
        return None
    return float(np.median(readings)), len(readings)


def band_share_db(x: np.ndarray, low_hz: float, high_hz: float) -> float:
    """Energy inside a band relative to the whole signal, in dB (0 = everything)."""
    if x.size == 0:
        return -120.0
    spectrum = np.abs(np.fft.rfft(x.astype(np.float64))) ** 2
    freqs = np.fft.rfftfreq(len(x), 1.0 / SR)
    total = float(np.sum(spectrum))
    if total <= EPSILON:
        return -120.0
    inside = float(np.sum(spectrum[(freqs >= low_hz) & (freqs < high_hz)]))
    return 10.0 * math.log10(max(inside, EPSILON) / total)


def envelope_autocorrelation_peak(x: np.ndarray, lag_s: float, hop_s: float = 0.005) -> Optional[tuple[float, bool]]:
    """Normalised autocorrelation of the level envelope at one lag, plus whether
    that lag is a local maximum (a real periodicity rather than a slope)."""
    env = rms_envelope(x, 0.01, hop_s)
    if env.size < 8:
        return None
    env = env - float(np.mean(env))
    if float(np.std(env)) < 1e-6:
        return None
    lag = int(round(lag_s / hop_s))
    if lag + 4 >= env.size:
        return None
    spectrum = np.fft.rfft(env, 2 * env.size)
    corr = np.fft.irfft(spectrum * np.conj(spectrum))[:env.size]
    corr = corr / max(float(corr[0]), EPSILON)
    window = corr[max(0, lag - 3):lag + 4]
    return float(corr[lag]), bool(corr[lag] >= float(np.max(window)))


def side_mid_ratio(stereo: np.ndarray) -> float:
    if stereo.size == 0:
        return 0.0
    mid = (stereo[:, 0] + stereo[:, 1]) * 0.5
    side = (stereo[:, 0] - stereo[:, 1]) * 0.5
    return float(np.sum(side.astype(np.float64) ** 2) / (np.sum(mid.astype(np.float64) ** 2) + EPSILON))


def spectral_centroid(x: np.ndarray) -> float:
    if x.size < 64:
        return 0.0
    frame = x.astype(np.float64) - float(np.mean(x))
    spectrum = np.abs(np.fft.rfft(frame * np.hanning(frame.size))) ** 2
    freqs = np.fft.rfftfreq(frame.size, d=1.0 / SR)
    return float(np.sum(freqs * spectrum) / (np.sum(spectrum) + EPSILON))


def playing_crest_factor(x: np.ndarray, window_s: float = 0.05) -> Optional[float]:
    """Peak over RMS, with the RMS taken only where the lane is sounding. A
    sparse phrase's rests would otherwise make any tone look clean."""
    if x.size == 0:
        return None
    env = rms_envelope(x, window_s, window_s / 2)
    if env.size == 0:
        return None
    playing = env[env > float(np.max(env)) * 0.05]
    if playing.size == 0:
        return None
    rms = float(np.sqrt(np.mean(playing.astype(np.float64) ** 2)))
    if rms < 1e-5:
        return None
    return float(np.max(np.abs(x))) / rms


def crest_factor(x: np.ndarray) -> Optional[float]:
    if x.size == 0:
        return None
    rms = float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))
    if rms < 1e-5:
        return None
    return float(np.max(np.abs(x))) / rms


def snare_hf_ratio_db(drums: np.ndarray, beat_s: float) -> Optional[float]:
    """Energy above 5 kHz relative to the whole spectrum in the 50 ms after each
    beat-2 and beat-4 position. A drum layer stacked on the snare shows up as
    extra top; a bare 808-style snare does not."""
    window = int(0.05 * SR)
    ratios: list[float] = []
    total_beats = int(len(drums) / (beat_s * SR))
    for beat in range(total_beats):
        if beat % 4 not in (1, 3):
            continue
        start = int(beat * beat_s * SR)
        chunk = drums[start:start + window]
        if chunk.size < window // 2 or float(np.max(np.abs(chunk))) < 0.01:
            continue
        spectrum = np.abs(np.fft.rfft(chunk.astype(np.float64) * np.hanning(chunk.size))) ** 2
        freqs = np.fft.rfftfreq(chunk.size, d=1.0 / SR)
        total = float(np.sum(spectrum)) + EPSILON
        ratios.append(10.0 * math.log10(float(np.sum(spectrum[freqs > 5000.0])) / total + EPSILON))
    if len(ratios) < 2:
        return None
    return float(np.median(ratios))


def spectral_fundamental(frame: np.ndarray, floor_hz: float = 50.0, ceiling_hz: float = 5000.0) -> Optional[float]:
    """Strongest spectral peak, walked down by octaves while a sub-harmonic is
    still at least 30% as strong. Used to fix the octave of estimate_f0, whose
    autocorrelation search stops at 720 Hz and reports the sub-octave for
    anything higher - exactly the range a transposed or doubled lead lives in."""
    if frame.size < 64:
        return None
    spectrum = np.abs(np.fft.rfft(frame.astype(np.float64) * np.hanning(frame.size)))
    freqs = np.fft.rfftfreq(frame.size, d=1.0 / SR)
    mask = (freqs > floor_hz) & (freqs < ceiling_hz)
    if not np.any(mask):
        return None
    index = int(np.argmax(spectrum * mask))
    if spectrum[index] <= 0:
        return None
    half = int(round(index / 2))
    while half > 2 and spectrum[half] > 0.3 * spectrum[index] and freqs[half] > floor_hz:
        index = half
        half = int(round(index / 2))
    return float(freqs[index])


def median_f0_hz(x: np.ndarray) -> Optional[float]:
    """Median fundamental over voiced frames. estimate_f0 gates voicing; the
    spectral peak settles which octave the note is in (see spectral_fundamental).
    Subs below 75 Hz still read as a harmonic - callers prefer bass/lead stems."""
    frame = 4096
    hop = 2048
    values: list[float] = []
    for start in range(0, len(x) - frame, hop):
        chunk = x[start:start + frame]
        f0, confidence = estimate_f0(chunk)
        if f0 <= 0 or confidence <= 0.3:
            continue
        peak = spectral_fundamental(chunk)
        # The spectrum decides the octave (and the note, above 720 Hz where
        # the autocorrelation search cannot reach); estimate_f0 only says
        # whether the frame is pitched at all.
        values.append(peak if peak is not None else f0)
    if len(values) < 8:
        return None
    return float(np.median(values))


# ---------------------------------------------------------------------------
# Claims
# ---------------------------------------------------------------------------


class Checker:
    def __init__(self, root: Path, project: dict[str, Any], spec: dict[str, Any], transcript: str,
                 assist: Any = None) -> None:
        self.root = root
        self.project = project
        self.spec = spec
        self.transcript = transcript or ""
        # An llm.Assist, or None for "the model is off": the report is then
        # exactly the regex-and-measurement one.
        self.assist = assist
        self._model_context: Optional[dict[str, Any]] = None
        self.model_dropped: list[str] = []
        self.snapshot = project.get("snapshot", {}) or {}
        self.bpm = float(self.snapshot.get("bpm") or 120.0) or 120.0
        self.bar_s = 240.0 / self.bpm
        self.beat_s = self.bar_s / 4.0
        self.stems = StemCache(root, project)
        self.spans = project_section_spans(project)
        self.order = project_section_order(project, self.spans)
        self.claims: list[dict[str, Any]] = []
        self.actions: list[str] = []
        self._counter = 0
        self.statements = self.stated_statements()
        # Bases that occur more than once get their ordinal shown ("Drop 1").
        keys = {key for key, _ in self.statements} | set(self.spans)
        bases = [key[0] for key in keys]
        self.multi = {base for base in bases if bases.count(base) > 1}

    def stated_statements(self) -> list[tuple[tuple[str, int], tuple[int, int]]]:
        """Every 'Section N Label bars A-B' the author wrote, in order, keyed
        by (position, key, (first_bar, last_bar))."""
        out: list[tuple[tuple[str, int], tuple[int, int]]] = []
        self._statement_positions: list[int] = []
        for match in STATED_SECTION_RE.finditer(self.transcript):
            parsed = parse_section_label(match.group(1))
            if not parsed:
                continue
            key = (parsed[0], parsed[1] or 1)
            if key in [item[0] for item in out]:
                continue
            out.append((key, (int(match.group(2)), int(match.group(3)))))
            self._statement_positions.append(match.start())
        return out

    def key_at(self, position: int) -> Optional[tuple[str, int]]:
        """The section the author was describing at a character offset."""
        found: Optional[tuple[str, int]] = None
        for (key, _), start in zip(self.statements, self._statement_positions):
            if start <= position:
                found = key
        return found

    def section_key(self, section: dict[str, Any]) -> Optional[tuple[str, int]]:
        """Own 'Section N' statement first; then wherever the section's text
        sits in the transcript; then the parser's type label."""
        text = str(section.get("transcriptText") or "")
        if STATED_SECTION_RE.search(text):
            return spec_section_key(section)
        if self.statements and text:
            probe = sentences(text)[0][:40] if sentences(text) else ""
            position = self.transcript.find(probe) if probe else -1
            if position >= 0:
                located = self.key_at(position)
                if located is not None:
                    return located
        return spec_section_key(section)

    def label(self, key: tuple[str, int]) -> str:
        base, ordinal = key
        name = base.replace("_", "-").title()
        if ordinal > 1 or base in self.multi:
            return f"{name} {ordinal}"
        return name

    def section_display(self, section: dict[str, Any]) -> str:
        key = self.section_key(section)
        return self.label(key) if key else str(section.get("label") or section.get("type") or "section")

    # -- bookkeeping -------------------------------------------------------

    def add(self, area: str, claim: str, source: str, status: str, evidence: str, verified_by: str,
            action: Optional[str] = None) -> dict[str, Any]:
        self._counter += 1
        record = {
            "id": f"claim-{self._counter:02d}",
            "area": area,
            "claim": claim,
            "source": source,
            "status": status,
            "evidence": evidence,
            "verifiedBy": verified_by,
        }
        if self._model_context:
            # A claim the model read out of the transcript: say so, and keep
            # the sentence it read it in next to the measurement.
            record["source"] = "model"
            record["quote"] = self._model_context.get("quote", "")
            record["reason"] = self._model_context.get("reason", "")
        self.claims.append(record)
        if action and status in ("missing", "contradicted") and action not in self.actions:
            self.actions.append(action)
        return record

    def musical_sections(self) -> list[dict[str, Any]]:
        return [s for s in self.spec.get("sections", []) if isinstance(s, dict) and self.section_key(s)]

    def span_for(self, section: dict[str, Any]) -> Optional[tuple[float, float]]:
        """Bar span (0-indexed) in the project for a spec section; production
        notes apply to the whole song."""
        if section.get("type") == "production_notes":
            return whole_song_span(self.project, self.spans)
        key = self.section_key(section)
        if key is None:
            return None
        return self.spans.get(key)

    def stem_slice(self, track_id: str, span: tuple[float, float], stereo: bool = False,
                   tail_bars: float = 0.0) -> Optional[np.ndarray]:
        audio = self.stems.stereo(track_id) if stereo else self.stems.mono(track_id)
        if audio is None:
            return None
        return slice_seconds(audio, span[0] * self.bar_s, (span[1] + tail_bars) * self.bar_s)

    def section_tracks(self, section: dict[str, Any]) -> list[str]:
        ids: list[str] = []
        for role in section.get("trackRoles", []) or []:
            for track_id in ROLE_TO_TRACKS.get(str(role), ()):
                if track_id not in ids:
                    ids.append(track_id)
        return ids

    # -- global claims -----------------------------------------------------

    def check_tempo(self) -> None:
        hint = self.spec.get("tempoHint")
        if not isinstance(hint, (int, float)) or hint <= 0:
            return
        diff = abs(float(hint) - self.bpm)
        status = "matched" if diff <= 1.0 else "contradicted"
        self.add("tempo", f"The track runs at {int(hint)} BPM.", "transcript", status,
                 f"project bpm is {self.bpm:g}", "project",
                 f"Set the project tempo to {int(hint)} BPM (it is {self.bpm:g}).")

    def check_key(self) -> None:
        hints = [h for h in self.spec.get("keyHints", []) or [] if isinstance(h, str)]
        if not hints:
            return
        stated = normalize_key(hints[0])
        actual_raw = self.project.get("keyCenter")
        actual = normalize_key(actual_raw)
        if stated is None:
            self.add("key", f"The key is {hints[0]}.", "transcript", "unverifiable",
                     f"could not read '{hints[0]}' as a key", "spec")
            return
        if actual is None:
            status, evidence = "missing", f"project has no key centre (keyCenter={actual_raw!r})"
        elif actual == stated:
            status, evidence = "matched", f"project keyCenter is {actual_raw}"
        else:
            status, evidence = "contradicted", f"project keyCenter is {actual_raw}"
        self.add("key", f"The key is {hints[0]}.", "transcript", status, evidence, "project",
                 f"Set the project key centre to {hints[0]}.")

    def stated_sections(self) -> list[tuple[tuple[str, int], Optional[tuple[int, int]], str]]:
        """(key, (first_bar, last_bar) 1-indexed or None, source) in the
        author's order. Explicit 'Section N X bars A-B' statements are used
        when the transcript has at least two; otherwise the spec's sections."""
        stated: list[tuple[tuple[str, int], Optional[tuple[int, int]], str]] = []
        for key, bars in self.statements:
            stated.append((key, bars, "transcript"))
        if len(stated) >= 2:
            return stated
        stated = []
        for section in self.musical_sections():
            key = self.section_key(section)
            if key is None or key in [item[0] for item in stated]:
                continue
            bars: Optional[tuple[int, int]] = None
            if self.spec.get("timecoded"):
                start_s = section.get("startSeconds")
                end_s = section.get("endSeconds")
                length = section.get("bars")
                if isinstance(start_s, (int, float)) and isinstance(end_s, (int, float)) and end_s > start_s:
                    tempo = float(self.spec.get("tempoHint") or self.bpm)
                    first = int(round(start_s / (240.0 / tempo))) + 1
                    count = int(round((end_s - start_s) / (240.0 / tempo)))
                    bars = (first, first + max(1, count) - 1)
                elif isinstance(length, (int, float)) and length > 0:
                    bars = (0, int(length) - 1)  # length only; start unknown
            stated.append((key, bars, str(section.get("id") or "spec")))
        return stated

    def check_section_order(self) -> None:
        stated = self.stated_sections()
        if len(stated) < 2:
            return
        stated_keys = [item[0] for item in stated]
        project_keys = [key for key in self.order if key in stated_keys]
        absent = [key for key in stated_keys if key not in self.order and key not in self.spans]
        claim = "Sections run " + " -> ".join(self.label(k) for k in stated_keys) + "."
        if absent:
            self.add("arrangement", claim, "transcript", "missing",
                     "project has no section for " + ", ".join(self.label(k) for k in absent),
                     "project", "Add the missing section(s): " + ", ".join(self.label(k) for k in absent) + ".")
            return
        if not project_keys:
            self.add("arrangement", claim, "transcript", "unverifiable",
                     "project recipe and clip names carry no section labels", "project")
            return
        for index, key in enumerate(stated_keys):
            if index >= len(project_keys) or project_keys[index] != key:
                found = self.label(project_keys[index]) if index < len(project_keys) else "nothing"
                self.add("arrangement", claim, "transcript", "contradicted",
                         f"first mismatch at position {index + 1}: expected {self.label(key)}, project has {found}",
                         "project", f"Reorder the arrangement so {self.label(key)} comes at position {index + 1}.")
                return
        self.add("arrangement", claim, "transcript", "matched",
                 "project recipe order: " + " -> ".join(self.label(k) for k in project_keys), "project")

    def check_section_lengths(self) -> None:
        for key, bars, source in self.stated_sections():
            if bars is None:
                continue
            first, last = bars
            length = last - first + 1
            if first <= 0:
                claim = f"{self.label(key)} is {length} bars long."
            else:
                claim = f"{self.label(key)} spans bars {first}-{last} ({length} bars)."
            span = self.spans.get(key)
            if span is None:
                self.add("length", claim, source, "missing", "no clips in the project belong to that section",
                         "project", f"Add clips for {self.label(key)} covering bars {first}-{last}.")
                continue
            actual_len = span[1] - span[0]
            actual_first = int(span[0]) + 1
            evidence = f"project clips span bars {actual_first}-{int(span[1])} ({actual_len:g} bars)"
            if abs(actual_len - length) <= 4:
                status = "matched"
            else:
                status = "contradicted"
            self.add("length", claim, source, status, evidence, "project",
                     f"Resize {self.label(key)} to {length} bars (project has {actual_len:g}).")

    def check_track_roles(self) -> None:
        mentions: dict[str, dict[str, list[str]]] = {}
        unknown: dict[str, list[str]] = {}
        for section in self.spec.get("sections", []) or []:
            if not isinstance(section, dict):
                continue
            label = self.section_display(section)
            for role in section.get("trackRoles", []) or []:
                role = str(role)
                targets = ROLE_TO_TRACKS.get(role, ())
                if not targets:
                    unknown.setdefault(role, []).append(label)
                for track_id in targets:
                    entry = mentions.setdefault(track_id, {"roles": [], "sections": []})
                    if role not in entry["roles"]:
                        entry["roles"].append(role)
                    if label not in entry["sections"]:
                        entry["sections"].append(label)
        for track_id, entry in mentions.items():
            roles = "/".join(entry["roles"])
            where = ", ".join(entry["sections"][:4]) + (" ..." if len(entry["sections"]) > 4 else "")
            has_content, why = track_has_content(self.root, self.project, track_id)
            article = "An" if roles[:1] in "aeiou" else "A"
            claim = f"{article} {roles} part plays in {where}."
            status = "matched" if has_content else "missing"
            self.add("tracks", claim, entry["sections"][0] if entry["sections"] else "transcript", status,
                     f"track '{track_id}': {why}", "project",
                     f"Give the '{track_id}' track ({roles}) audio, notes, or steps - it is named but silent.")
        for role, labels in unknown.items():
            self.add("tracks", f"A {role} part plays in {', '.join(labels[:3])}.", "transcript", "unverifiable",
                     f"no track mapping exists for role '{role}'", "spec")

    # -- techniques --------------------------------------------------------

    def check_techniques(self) -> None:
        for section in self.spec.get("sections", []) or []:
            if not isinstance(section, dict):
                continue
            key = self.section_key(section)
            is_notes = section.get("type") == "production_notes"
            if key is None and not is_notes:
                continue
            label = "the whole track" if is_notes else self.label(key)  # type: ignore[arg-type]
            span = self.span_for(section)
            for technique in section.get("techniques", []) or []:
                technique = str(technique)
                self.check_technique(section, technique, label, span)

    def check_technique(self, section: dict[str, Any], technique: str, label: str,
                        span: Optional[tuple[float, float]]) -> None:
        source = str(section.get("id") or "spec")
        claim = f"{label.capitalize() if label.startswith('the') else label} uses {technique.replace('_', ' ')}."
        if technique in UNMEASURABLE_TECHNIQUES:
            self.add("technique", claim, source, "unverifiable",
                     f"no measurement here can confirm '{technique}' honestly", "spec")
            return
        if span is None:
            self.add("technique", claim, source, "unverifiable",
                     "the project has no clips for that section, so there is nothing to measure", "project")
            return
        if span[1] <= span[0]:
            self.add("technique", claim, source, "unverifiable", "section span is empty", "project")
            return
        result = None
        if technique in TECHNIQUE_STEMS and section.get("type") == "production_notes":
            result = self.measure_across_sections(technique)
        if result is None and technique in TECHNIQUE_STEMS:
            result = self.measure(technique, section, span)
        if result is not None:
            status, evidence = result
            self.add("technique", claim, source, status, evidence, "audio",
                     self.technique_action(technique, label, evidence))
            return
        self.project_fallback(technique, section, claim, source, label)

    def technique_action(self, technique: str, label: str, evidence: str) -> str:
        templates = {
            "sidechain": f"Duck the bass/sub by at least 4 dB after each kick in {label} ({evidence}).",
            "reverb": f"Lengthen the lead/chords reverb tail in {label} to more than 0.5 s ({evidence}).",
            "delay": f"Add an eighth or dotted-eighth delay to the lead in {label} ({evidence}).",
            "stereo": f"Widen the chords/fx in {label} - side/mid energy should exceed 0.15 ({evidence}).",
            "filtering": f"Automate the filter in {label} so the last bar is at least 40% brighter than the first ({evidence}).",
            "automation": f"Make the automation in {label} audible - filter or level should move across the section ({evidence}).",
            "distortion": f"Saturate the bass/lead in {label} until the crest factor drops below 4 ({evidence}).",
            "layering": f"Layer the drums in {label} so snare hits carry energy above 5 kHz ({evidence}).",
        }
        return templates.get(technique, f"Add the stated {technique} to {label} ({evidence}).")

    def measure(self, technique: str, section: dict[str, Any], span: tuple[float, float]) -> Optional[tuple[str, str]]:
        """Audio evidence for one technique in one section, or None when no
        usable stem exists (the caller then falls back to the project file)."""
        if technique == "sidechain":
            return self.measure_sidechain(span)
        if technique == "reverb":
            return self.measure_reverb(span)
        if technique == "delay":
            return self.measure_delay(span)
        if technique == "stereo":
            return self.measure_stereo(span)
        if technique in ("filtering", "automation"):
            return self.measure_movement(technique, section, span)
        if technique == "distortion":
            return self.measure_distortion(span)
        if technique == "layering":
            return self.measure_layering(span)
        if technique == "eq":
            return self.measure_eq(span)
        if technique == "compression":
            return self.measure_compression(span)
        if technique == "reverse":
            return self.measure_reverse(span)
        return None

    def measure_across_sections(self, technique: str) -> Optional[tuple[str, str]]:
        """A whole-track technique, measured in every musical section that can
        be measured. Parts are mixed at different levels on purpose, so one
        measurement over the whole song would read the arrangement as a fault."""
        results: list[tuple[str, str, str]] = []
        for musical in self.musical_sections():
            key = self.section_key(musical)
            span = self.span_for(musical)
            if key is None or span is None or span[1] <= span[0]:
                continue
            reading = self.measure(technique, musical, span)
            if reading is None or reading[0] == "unverifiable":
                continue
            results.append((self.label(key), reading[0], reading[1]))
        if not results:
            return None
        matched = [label for label, status, _ in results if status == "matched"]
        missing = [(label, evidence) for label, status, evidence in results if status != "matched"]
        summary = f"measured in {len(results)} sections: matched in {', '.join(matched) or 'none'}"
        if missing:
            summary += "; not in " + ", ".join(f"{label} ({evidence})" for label, evidence in missing[:2])
        status = "matched" if len(matched) * 3 >= len(results) * 2 else "missing"
        return status, summary

    def measure_eq(self, span: tuple[float, float]) -> Optional[tuple[str, str]]:
        """EQ as a producer means it here: the melodic lanes carry no low end,
        and the sub carries nothing but low end."""
        readings: list[str] = []
        failures: list[str] = []
        for stem in TECHNIQUE_STEMS["eq"]:
            audio = self.stem_slice(stem, span)
            if audio is None or is_silent(audio):
                continue
            if stem == "sub":
                share = band_share_db(audio, 250.0, SR / 2)
                readings.append(f"sub above 250 Hz {share:.0f} dB")
                if share > -20.0:
                    failures.append(stem)
            else:
                limit = 60.0 if stem == "bass" else 100.0
                share = band_share_db(audio, 0.0, limit)
                readings.append(f"{stem} below {limit:.0f} Hz {share:.0f} dB")
                if share > -20.0:
                    failures.append(stem)
        if not readings:
            return None
        evidence = "energy share " + ", ".join(readings)
        if failures:
            return "missing", evidence + f"; {', '.join(failures)} still carry that band"
        return "matched", evidence

    def measure_compression(self, span: tuple[float, float]) -> Optional[tuple[str, str]]:
        """Compression on a drum lane is heard as hits that sit at one level:
        the body of each hit (20-60 ms in) lands within a couple of dB of the
        others. A fast-attack compressor can raise the crest factor, so the
        peak is not the witness; the bodies are."""
        readings: list[tuple[str, float, float, int]] = []
        for stem in TECHNIQUE_STEMS["compression"]:
            audio = self.stem_slice(stem, span)
            if audio is None or is_silent(audio):
                continue
            onsets = detect_onsets(audio)
            bodies: list[float] = []
            for onset in onsets:
                body = slice_seconds(audio, onset + 0.02, onset + 0.06)
                if body.size:
                    bodies.append(rms_db(body))
            if len(bodies) < 4:
                continue
            levels = np.array(bodies)
            readings.append((stem, float(np.std(levels)), float(np.max(levels) - np.min(levels)), len(bodies)))
        if not readings:
            return None
        stem, spread, extent, count = min(readings, key=lambda item: item[1])
        detail = ", ".join(f"{name} std {std:.1f} dB over {n} hits (range {rng:.1f})" for name, std, rng, n in readings)
        evidence = f"{stem} hit bodies sit within {extent:.1f} dB of each other ({detail}; uncompressed kick/snare programming spreads 9-12 dB)"
        return ("matched" if spread < 3.0 else "missing"), evidence

    def measure_reverse(self, span: tuple[float, float]) -> Optional[tuple[str, str]]:
        """A reverse swell rises into the section: the two beats before it start
        quiet and end loud on the FX lane."""
        beats = 2.0
        start_s = (span[0] - beats / 4.0) * self.bar_s
        if start_s < 0:
            return "unverifiable", "the section starts the song, so nothing can swell into it"
        stereo = self.stems.mono("fx")
        if stereo is None:
            return None
        audio = slice_seconds(stereo, start_s, span[0] * self.bar_s)
        if audio.size == 0 or is_silent(audio):
            return "missing", "the FX lane is silent in the two beats before the section"
        quarter = max(1, len(audio) // 4)
        levels = [rms_db(audio[index * quarter:(index + 1) * quarter]) for index in range(4)]
        rise = levels[-1] - levels[0]
        monotonic = all(levels[index + 1] >= levels[index] - 1.0 for index in range(3))
        evidence = f"fx level over the two beats before the section {levels[0]:.0f} -> {levels[-1]:.0f} dB ({rise:+.0f} dB, {'rising' if monotonic else 'not steadily rising'})"
        return ("matched" if rise > 6.0 and monotonic else "missing"), evidence

    def measure_sidechain(self, span: tuple[float, float]) -> Optional[tuple[str, str]]:
        drums = self.stem_slice("drums", span)
        if drums is None or is_silent(drums):
            return None
        kicks = detect_onsets(lowpass_fft(drums, 150.0))
        if len(kicks) < 4:
            return None
        readings: list[tuple[str, float]] = []
        for stem in TECHNIQUE_STEMS["sidechain"]:
            audio = self.stem_slice(stem, span)
            if audio is None or is_silent(audio):
                continue
            dip = sidechain_dip_db(audio, kicks)
            if dip is not None:
                readings.append((stem, dip))
        if not readings:
            return None
        stem, dip = max(readings, key=lambda item: item[1])
        detail = ", ".join(f"{name} {value:.1f} dB" for name, value in readings)
        evidence = f"{stem} RMS dips {dip:.1f} dB at {len(kicks)} kick onsets ({detail})"
        return ("matched" if dip > 4.0 else "missing"), evidence

    def measure_reverb(self, span: tuple[float, float]) -> Optional[tuple[str, str]]:
        readings: list[tuple[str, float, bool]] = []
        for stem in TECHNIQUE_STEMS["reverb"]:
            audio = self.stem_slice(stem, span, tail_bars=2.0)
            if audio is None or is_silent(audio):
                continue
            decay = decay_time_30db(audio, (span[1] - span[0]) * self.bar_s)
            if decay is not None:
                readings.append((stem, decay[0], decay[1]))
        if not readings:
            return None
        stem, seconds, truncated = max(readings, key=lambda item: item[1])
        detail = ", ".join(f"{name} {value:.2f}s{'+' if cut else ''}" for name, value, cut in readings)
        evidence = f"-30 dB decay after the last {stem} onset takes {seconds:.2f} s ({detail})"
        if seconds > 0.5:
            return "matched", evidence
        # Dense parts never leave room for a full tail; look at what stays
        # behind each note that is followed by a rest instead.
        residuals: list[tuple[str, float, int]] = []
        for name in TECHNIQUE_STEMS["reverb"]:
            audio = self.stem_slice(name, span, tail_bars=1.0)
            if audio is None or is_silent(audio):
                continue
            residual = tail_residual_db(audio)
            if residual is not None:
                residuals.append((name, residual[0], residual[1]))
        if residuals:
            name, level, count = max(residuals, key=lambda item: item[1])
            evidence += f"; {name} still {level:.0f} dB 250 ms after a note before a rest ({count} notes; a dry release is under -40)"
            if level > -30.0:
                return "matched", evidence
        if truncated:
            return "unverifiable", evidence + "; the next note arrived before the tail finished"
        return "missing", evidence

    def measure_delay(self, span: tuple[float, float]) -> Optional[tuple[str, str]]:
        audio = self.stem_slice("lead", span)
        if audio is None or is_silent(audio):
            return None
        lags = (("eighth", self.beat_s / 2.0), ("dotted-eighth", self.beat_s * 0.75), ("quarter", self.beat_s))
        # A ping-pong delay is the only thing that puts side energy on a mono
        # lead, and its echoes alternate channels - so the side signal's
        # envelope repeats at the delay time while the played notes stay in the
        # mid. That witness is not fooled by a busy eighth-note melody.
        wide = self.stem_slice("lead", span, stereo=True)
        if wide is not None:
            side = ((wide[:, 0] - wide[:, 1]) * 0.5).astype(np.float32)
            ratio = side_mid_ratio(wide)
            if ratio > 0.01 and not is_silent(side):
                best_side: Optional[tuple[str, float, bool]] = None
                for name, lag in lags:
                    reading = envelope_autocorrelation_peak(side, lag)
                    if reading is None:
                        continue
                    value, is_peak = reading
                    if best_side is None or (is_peak and value > best_side[1]):
                        best_side = (name, value, is_peak)
                if best_side is not None and best_side[2] and best_side[1] > 0.2:
                    name, value, _ = best_side
                    return "matched", (f"lead side-signal envelope repeats at the {name} lag ({value:.2f}, a local peak); "
                                       f"side/mid {ratio:.3f} on a lead that is otherwise mono")
        best: Optional[tuple[str, float, bool]] = None
        for name, lag in lags[:2]:
            reading = envelope_autocorrelation_peak(audio, lag)
            if reading is None:
                continue
            value, is_peak = reading
            if best is None or (is_peak and value > best[1]):
                best = (name, value, is_peak)
        if best is None:
            return None
        name, value, is_peak = best
        evidence = (f"lead envelope autocorrelation at the {name} lag is {value:.2f}"
                    f" ({'a local peak' if is_peak else 'not a peak'}; note this also reads played {name}-note rhythms as repeats)")
        return ("matched" if is_peak and value > 0.2 else "missing"), evidence

    def measure_stereo(self, span: tuple[float, float]) -> Optional[tuple[str, str]]:
        readings: list[tuple[str, float]] = []
        for stem in TECHNIQUE_STEMS["stereo"]:
            audio = self.stem_slice(stem, span, stereo=True)
            if audio is None or is_silent(audio.mean(axis=1)):
                continue
            readings.append((stem, side_mid_ratio(audio)))
        if not readings:
            return None
        stem, ratio = max(readings, key=lambda item: item[1])
        detail = ", ".join(f"{name} {value:.3f}" for name, value in readings)
        evidence = f"{stem} side/mid energy ratio is {ratio:.3f} ({detail})"
        return ("matched" if ratio > 0.15 else "missing"), evidence

    def measure_movement(self, technique: str, section: dict[str, Any], span: tuple[float, float]) -> Optional[tuple[str, str]]:
        """Filter/automation: spectral centroid of the last audible bar versus
        the first. Builds must brighten; other sections may move either way.
        For 'automation' a level move of 6 dB also counts."""
        rising_types = ("build", "pre_build", "intro", "verse")
        key = self.section_key(section)
        must_rise = bool(key and key[0] in rising_types)
        readings: list[str] = []
        passed = False
        stems = TECHNIQUE_STEMS[technique]
        for stem in stems:
            audio = self.stem_slice(stem, span)
            if audio is None or is_silent(audio):
                continue
            bars = int(span[1] - span[0])
            bar_len = int(self.bar_s * SR)
            # Compare the first and last bars that actually sound: a closed
            # filter or a fake stop can leave an edge bar silent.
            audible = [index for index in range(bars)
                       if not is_silent(audio[index * bar_len:(index + 1) * bar_len])]
            if len(audible) < 2 or audible[-1] - audible[0] < 2:
                continue
            first = audio[audible[0] * bar_len:(audible[0] + 1) * bar_len]
            last = audio[audible[-1] * bar_len:(audible[-1] + 1) * bar_len]
            c0, c1 = spectral_centroid(first), spectral_centroid(last)
            change = c1 / max(c0, 1.0) - 1.0
            readings.append(f"{stem} centroid {c0:.0f} -> {c1:.0f} Hz ({change:+.0%})")
            if (change > 0.4) or (not must_rise and change < -0.4):
                passed = True
            b0, b1 = band_share_db(first, 2000.0, 8000.0), band_share_db(last, 2000.0, 8000.0)
            brightness = b1 - b0
            readings.append(f"{stem} 2-8 kHz share {b0:.0f} -> {b1:.0f} dB ({brightness:+.0f} dB)")
            if (brightness > 6.0) or (not must_rise and brightness < -6.0):
                passed = True
            if technique == "automation":
                level = rms_db(last) - rms_db(first)
                if abs(level) > 6.0:
                    readings.append(f"{stem} level {level:+.1f} dB")
                    passed = True
                wide = self.stem_slice(stem, span, stereo=True)
                if wide is not None:
                    w0 = side_mid_ratio(wide[audible[0] * bar_len:(audible[0] + 1) * bar_len])
                    w1 = side_mid_ratio(wide[audible[-1] * bar_len:(audible[-1] + 1) * bar_len])
                    if max(w0, w1) > 0.02 and abs(w1 - w0) > 0.4 * max(w0, w1):
                        readings.append(f"{stem} width {w0:.3f} -> {w1:.3f}")
                        passed = True
        if not readings:
            return None
        return ("matched" if passed else "missing"), "; ".join(readings)

    def measure_distortion(self, span: tuple[float, float]) -> Optional[tuple[str, str]]:
        readings: list[tuple[str, float]] = []
        for stem in TECHNIQUE_STEMS["distortion"]:
            audio = self.stem_slice(stem, span)
            if audio is None or is_silent(audio):
                continue
            crest = playing_crest_factor(audio)
            if crest is not None:
                readings.append((stem, crest))
        if not readings:
            return None
        stem, crest = min(readings, key=lambda item: item[1])
        detail = ", ".join(f"{name} {value:.2f}" for name, value in readings)
        evidence = f"{stem} crest factor while playing is {crest:.2f} ({detail}; a clean tone sits near 1.4-3, driven ones under 4)"
        return ("matched" if crest < 4.0 else "missing"), evidence

    def measure_layering(self, span: tuple[float, float]) -> Optional[tuple[str, str]]:
        drums = self.stem_slice("drums", span)
        if drums is None or is_silent(drums):
            return None
        ratio = snare_hf_ratio_db(drums, self.beat_s)
        if ratio is None:
            return None
        evidence = f"snare-position drum hits carry {ratio:.1f} dB of energy above 5 kHz relative to total (a weak proxy for a stacked layer)"
        return ("matched" if ratio > -25.0 else "missing"), evidence

    def project_fallback(self, technique: str, section: dict[str, Any], claim: str, source: str, label: str) -> None:
        tracks = tracks_by_id(self.project)
        candidates = list(TECHNIQUE_STEMS.get(technique, ())) + self.section_tracks(section)
        candidates = [t for i, t in enumerate(candidates) if t in tracks and t not in candidates[:i]]
        if technique == "layering":
            families = []
            for family, members in LAYER_FAMILIES.items():
                present = [m for m in members if m in tracks and track_has_content(self.root, self.project, m)[0]]
                if len(present) > 1:
                    families.append(f"{family}: {'+'.join(present)}")
            if families:
                self.add("technique", claim, source, "matched", "project layers " + "; ".join(families), "project")
            else:
                self.add("technique", claim, source, "missing", "no instrument family has more than one track with content",
                         "project", f"Add a second layer for at least one instrument family in {label}.")
            return
        if technique == "automation":
            span = self.span_for(section)
            lanes = []
            for lane in self.snapshot.get("automationLanes", []) or []:
                points = [p for p in (lane.get("points") or []) if isinstance(p, dict)]
                if span and any(span[0] <= float(p.get("bar", -1)) <= span[1] for p in points) and len(points) >= 2:
                    lanes.append(f"{lane.get('trackId')}.{lane.get('parameter')}")
            if lanes:
                self.add("technique", claim, source, "matched", "automation lanes in that span: " + ", ".join(lanes), "project")
            else:
                self.add("technique", claim, source, "missing", "no automation lane has points inside that section",
                         "project", f"Add an automation lane that moves across {label}.")
            return
        words = TECHNIQUE_EFFECT_WORDS.get(technique)
        if not words:
            self.add("technique", claim, source, "unverifiable", f"no stem or effect check exists for '{technique}'", "spec")
            return
        hits = []
        for track_id in candidates:
            for effect in tracks[track_id].get("effects", []) or []:
                name = str(effect.get("name") or "").lower()
                if effect.get("active") is True and any(word in name for word in words):
                    hits.append(f"{track_id}: {effect.get('name')}")
        if hits:
            self.add("technique", claim, source, "matched", "active effect " + "; ".join(hits[:3]), "project")
        else:
            self.add("technique", claim, source, "missing",
                     f"no active {technique} effect on {', '.join(candidates) or 'the section tracks'}", "project",
                     f"Add an active {technique} effect to {', '.join(candidates[:2]) or 'the section tracks'} for {label}.")

    # -- pitch relations ---------------------------------------------------

    def section_f0(self, track_id: str, key: tuple[str, int]) -> Optional[float]:
        span = self.spans.get(key)
        if span is None:
            return None
        audio = self.stem_slice(track_id, span)
        if audio is None or is_silent(audio):
            return None
        return median_f0_hz(audio)

    def check_octave_relations(self) -> None:
        """'second drop an octave down', 'add octave double', 'transpose +12'."""
        drop_one, drop_two = ("drop", 1), ("drop", 2)
        handled: set[str] = set()
        for position, sentence in sentence_spans(self.transcript):
            key = self.key_at(position) if self.statements else self.spec_key_for_sentence(sentence)
            if key is not None:
                if re.search(r"\boctave\s+(double|layer|up double|stack)", sentence, re.IGNORECASE) and f"double:{key}" not in handled:
                    handled.add(f"double:{key}")
                    self.check_octave_double(key, "transcript")
                transpose = TRANSPOSE_RE.search(sentence)
                if transpose and f"transpose:{key}" not in handled:
                    handled.add(f"transpose:{key}")
                    semis = int(transpose.group(1).replace(" ", ""))
                    self.check_transpose(sentence, key, semis)
            direction = OCTAVE_DIRECTION_RE.search(sentence)
            if direction and DROP_TWO_RE.search(sentence):
                downward = direction.group(1).lower() in ("down", "lower", "below")
                claim = f"The second drop sits an octave {'down' if downward else 'up'} from the first."
                stem = "bass" if downward and self.stems.path("bass") else "lead"
                f_one = self.section_f0(stem, drop_one)
                f_two = self.section_f0(stem, drop_two)
                if f_one is None or f_two is None:
                    self.add("pitch", claim, "transcript", "unverifiable",
                             f"could not estimate {stem} pitch in both drops", "audio")
                    continue
                semis = freq_to_midi(f_two) - freq_to_midi(f_one)
                evidence = f"{stem} median f0 {f_one:.0f} Hz -> {f_two:.0f} Hz ({semis:+.1f} semitones)"
                expected = -12.0 if downward else 12.0
                status = "matched" if abs(semis - expected) <= 2.0 else "contradicted"
                self.add("pitch", claim, "transcript", status, evidence, "audio",
                         f"Transpose the {stem} in Drop 2 by {expected:+.0f} semitones ({evidence}).")

    def spec_key_for_sentence(self, sentence: str) -> Optional[tuple[str, int]]:
        """Without 'Section N' statements, a sentence belongs to whichever spec
        section carried it."""
        probe = sentence[:40]
        for section in self.musical_sections():
            if probe and probe in str(section.get("transcriptText") or ""):
                return self.section_key(section)
        return None

    def check_octave_double(self, key: tuple[str, int], source: str) -> None:
        claim = f"{self.label(key)} adds an octave double to the lead."
        span = self.spans.get(key)
        if span is None:
            self.add("pitch", claim, source, "unverifiable", "no project span for that section", "project")
            return
        lead = self.section_f0("lead", key)
        double = self.section_f0("lead-double", key)
        if lead is not None and double is not None:
            semis = abs(freq_to_midi(double) - freq_to_midi(lead))
            evidence = f"lead-double median f0 {double:.0f} Hz vs lead {lead:.0f} Hz ({semis:.1f} semitones apart)"
            status = "matched" if 10.0 <= semis <= 14.0 else "contradicted"
            self.add("pitch", claim, source, status, evidence, "audio",
                     f"Pitch the lead double in {self.label(key)} a full octave from the lead ({evidence}).")
            return
        if self.stems.path("lead-double") is not None:
            self.add("pitch", claim, source, "missing", "the lead-double stem is silent in that section", "audio",
                     f"Render the lead double in {self.label(key)}.")
            return
        track = tracks_by_id(self.project).get("lead-double")
        if track is None:
            self.add("pitch", claim, source, "missing", "no lead-double track exists", "project",
                     f"Add a lead-double track an octave from the lead in {self.label(key)}.")
            return
        clips = [c for c in (track.get("clips") or []) if isinstance(c, dict)
                 and float(c.get("startBar") or 0) < span[1] and float(c.get("startBar") or 0) + float(c.get("bars") or 0) > span[0]]
        if clips:
            self.add("pitch", claim, source, "matched", f"lead-double clip '{clips[0].get('name')}' covers the section (interval not checked)", "project")
        else:
            self.add("pitch", claim, source, "missing", "lead-double track has no clip in that section", "project",
                     f"Place a lead-double clip in {self.label(key)}.")

    def check_transpose(self, sentence: str, key: tuple[str, int], semis: int,
                        reference: Optional[tuple[str, int]] = None) -> None:
        # "copy intro lead ... transpose +12": the reference is the section the
        # sentence names; failing that, the section before this one.
        for match in SECTION_LABEL_RE.finditer(sentence) if reference is None else ():
            parsed = parse_section_label(match.group(0))
            if parsed and (parsed[0], parsed[1] or 1) != key:
                reference = (parsed[0], parsed[1] or 1)
                break
        if reference is None:
            keys = [item[0] for item in self.stated_sections()]
            if key in keys and keys.index(key) > 0:
                reference = keys[keys.index(key) - 1]
        source = "transcript"
        if reference is None:
            self.add("pitch", f"{self.label(key)} lead is transposed {semis:+d} semitones.", source, "unverifiable",
                     "no reference section to compare against", "spec")
            return
        claim = f"{self.label(key)} lead is the {self.label(reference)} lead transposed {semis:+d} semitones."
        f_ref = self.section_f0("lead", reference)
        f_now = self.section_f0("lead", key)
        if f_ref is None or f_now is None:
            self.add("pitch", claim, source, "unverifiable", "could not estimate lead pitch in both sections", "audio")
            return
        measured = freq_to_midi(f_now) - freq_to_midi(f_ref)
        evidence = f"lead median f0 {f_ref:.0f} Hz -> {f_now:.0f} Hz ({measured:+.1f} semitones)"
        status = "matched" if abs(measured - semis) <= 2.0 else "contradicted"
        self.add("pitch", claim, source, status, evidence, "audio",
                 f"Transpose the {self.label(key)} lead {semis:+d} semitones from {self.label(reference)} ({evidence}).")

    # -- explicit numbers ----------------------------------------------------

    def check_automation_statements(self) -> None:
        seen: set[str] = set()
        moves: list[tuple[str, str, str, str, str, str]] = []
        ranges = list(AUTOMATION_RANGE_RE.finditer(self.transcript))
        for index, range_match in enumerate(ranges):
            first, last = range_match.groups()
            # The moves for one bar range run until the next bar range, the
            # next line, or the next sentence; "|" or "," separate several
            # moves for the same range.
            stop = ranges[index + 1].start() if index + 1 < len(ranges) else len(self.transcript)
            rest = self.transcript[range_match.end():stop].split("\n", 1)[0]
            rest = re.split(r"(?<=[a-z])\.\s|\.\s+(?=[A-Z])", rest, maxsplit=1)[0]
            for move in AUTOMATION_MOVE_RE.finditer(rest):
                moves.append((first, last) + move.groups())
        for first, last, track, parameter, start_v, end_v in moves:
            statement = f"{first}-{last} {track}.{parameter} {start_v}->{end_v}"
            if statement in seen:
                continue
            seen.add(statement)
            try:
                start_value, end_value = float(start_v), float(end_v)
            except ValueError:
                continue
            self.check_automation_move(first, last, track, parameter, start_value, end_value)

    def check_automation_move(self, first: str, last: str, track: str, parameter: str,
                              start_value: float, end_value: float) -> None:
        """One stated move 'track.parameter a->b over bars first-last' against
        the project's automation lanes. Shared by the regex and model paths."""
        lanes = [lane for lane in self.snapshot.get("automationLanes", []) or [] if isinstance(lane, dict)]
        first_bar, last_bar = int(first) - 1, int(last)   # to 0-indexed [start, end)
        claim = f"{track}.{parameter} moves {start_value:g} -> {end_value:g} over bars {first}-{last}."
        action = f"Add an automation lane {track}.{parameter} {start_value:g}->{end_value:g} over bars {first}-{last}."
        matching = [lane for lane in lanes if self.lane_matches(lane, track, parameter)]
        if not matching:
            self.add("automation", claim, "transcript", "missing", f"no {track}.{parameter} automation lane in the project",
                     "project", action)
            return
        best = None
        for lane in matching:
            points = sorted((p for p in (lane.get("points") or []) if isinstance(p, dict)), key=lambda p: float(p.get("bar", 0)))
            inside = [p for p in points if first_bar <= float(p.get("bar", -1)) <= last_bar]
            if len(points) < 2 or not inside:
                continue
            bars = [float(p.get("bar", 0)) for p in points]
            values = [float(p.get("value", 0)) for p in points]
            v0 = float(np.interp(first_bar, bars, values))
            v1 = float(np.interp(last_bar, bars, values))
            best = (lane, v0, v1)
            break
        if best is None:
            self.add("automation", claim, "transcript", "missing",
                     f"lane {track}.{parameter} exists but has no points inside bars {first}-{last}", "project", action)
            return
        lane, v0, v1 = best
        evidence = f"lane {lane.get('trackId')}.{lane.get('parameter')} reads {v0:.2f} -> {v1:.2f} across bars {first}-{last}"
        same_direction = (v1 - v0) * (end_value - start_value) > 0 or abs(end_value - start_value) < 1e-6
        close = abs(v0 - start_value) <= 0.15 and abs(v1 - end_value) <= 0.15
        status = "matched" if same_direction and close else "contradicted"
        self.add("automation", claim, "transcript", status, evidence, "project", action)

    @staticmethod
    def lane_matches(lane: dict[str, Any], track: str, parameter: str) -> bool:
        aliases = {"filter": ("filter", "cutoff"), "cutoff": ("filter", "cutoff"),
                   "volume": ("volume", "gain", "level"), "gain": ("volume", "gain", "level")}
        wanted = aliases.get(parameter.lower(), (parameter.lower(),))
        lane_param = str(lane.get("parameter") or "").lower()
        lane_label = str(lane.get("label") or "").lower()
        if not (lane_param in wanted or any(w in lane_label for w in wanted)):
            return False
        if track.lower() == "master":
            return True
        lane_track = str(lane.get("trackId") or "").lower()
        return lane_track == track.lower() or lane_track.startswith(track.lower())

    def check_explicit_numbers(self) -> None:
        haystack: list[str] = []
        for track in self.snapshot.get("tracks", []) or []:
            if isinstance(track, dict):
                haystack.append(str(track.get("instrument") or ""))
                haystack.extend(str(e.get("name") or "") for e in (track.get("effects") or []) if isinstance(e, dict))
        for lane in self.snapshot.get("automationLanes", []) or []:
            if isinstance(lane, dict):
                haystack.append(f"{lane.get('label')} {lane.get('parameter')}")
        for item in self.snapshot.get("recipe", []) or []:
            if isinstance(item, dict):
                haystack.append(f"{item.get('label')} {item.get('detail')}")
        blob = " ".join(haystack).lower()
        tempo_hint = self.spec.get("tempoHint")
        seen: set[str] = set()
        for match in NUMBER_UNIT_RE.finditer(self.transcript):
            number, unit = match.group(1), match.group(2).lower()
            token = f"{number} {unit}"
            if token in seen:
                continue
            seen.add(token)
            start = max(0, match.start() - 40)
            quote = re.sub(r"\s+", " ", self.transcript[start:match.end() + 30]).strip()
            claim = f"The description states {number} {unit.upper() if unit != 'ms' else 'ms'}."
            if unit == "bpm":
                if isinstance(tempo_hint, (int, float)) and abs(float(number) - float(tempo_hint)) < 0.5:
                    continue   # already covered by the tempo claim
                status = "matched" if abs(float(number) - self.bpm) <= 1.0 else "contradicted"
                self.add("numbers", claim, "transcript", status, f"project bpm is {self.bpm:g}", "project",
                         f"Set the tempo to {number} BPM.")
                continue
            pattern = re.compile(r"\b" + re.escape(number) + r"\s*" + re.escape(unit) + r"\b")
            if pattern.search(blob):
                self.add("numbers", claim, "transcript", "matched", f"project names '{token}' in an effect, lane, or recipe entry", "project")
            else:
                self.add("numbers", claim, "transcript", "unverifiable", f"nothing in the project carries '{token}': \"{quote}\"", "spec")

    # -- driver ------------------------------------------------------------

    # -- the model: claims the regexes missed ------------------------------

    @property
    def model_available(self) -> bool:
        return bool(self.assist is not None and getattr(self.assist, "available", False))

    def known_section_keys(self) -> list[tuple[str, int]]:
        keys: list[tuple[str, int]] = []
        for key, _ in self.statements:
            if key not in keys:
                keys.append(key)
        for key in self.order:
            if key not in keys:
                keys.append(key)
        for key in sorted(self.spans, key=lambda k: self.spans[k][0]):
            if key not in keys:
                keys.append(key)
        for section in self.musical_sections():
            key = self.section_key(section)
            if key is not None and key not in keys:
                keys.append(key)
        return keys

    def resolve_section(self, name: Any, keys: list[tuple[str, int]]) -> Optional[tuple[str, int]]:
        """A section name the model wrote back -> one of the keys it was given."""
        if not isinstance(name, str) or not name.strip():
            return None
        wanted = collapse_ws(name).lower()
        for key in keys:
            if self.label(key).lower() == wanted:
                return key
        parsed = parse_section_label(name)
        if parsed:
            key = (parsed[0], parsed[1] or 1)
            if key in keys:
                return key
        return None

    def extract_model_claims(self) -> list[dict[str, Any]]:
        """Ask the model for claims in the transcript, one call per ~24k-char
        chunk, and keep only the ones that validate: a quote that appears in
        the text, and names that exist (sections, techniques, roles, tracks)."""
        if not self.model_available or not self.transcript.strip():
            return []
        keys = self.known_section_keys()
        section_names = [self.label(key) for key in keys]
        track_ids = sorted(tracks_by_id(self.project))
        roles = sorted(ROLE_TO_TRACKS)
        kept: list[dict[str, Any]] = []
        seen: set[str] = set()
        for index, chunk in enumerate(chunk_text(self.transcript, CHUNK_CHARS)):
            task = (
                "Transcript chunk {n}. List every checkable claim the author makes about the finished track.\n"
                "Sections you may name: {sections}\n"
                "Techniques you may name: {techniques}\n"
                "Roles you may name: {roles}\n"
                "Track ids you may name (for automation): {tracks}\n"
                "Rules: quote the exact sentence for every claim; skip anything whose section, technique, "
                "role, or track is not in the lists; do not infer, do not add production advice of your own; "
                "a 'whole track' technique is one the author states for the mix as a whole.\n\nTEXT:\n{text}"
            ).format(n=index + 1, sections=", ".join(section_names) or "(none known)",
                     techniques=", ".join(KNOWN_TECHNIQUES), roles=", ".join(roles),
                     tracks=", ".join(track_ids) or "(none)", text=chunk)
            answer = self.assist.ask(task, system=CLAIM_ROLE, schema=CLAIM_SCHEMA)
            # Models answer this one as {"claims": [...]} or as the bare list.
            raw_claims = answer.get("claims") if isinstance(answer, dict) else answer
            if not isinstance(raw_claims, list):
                self.model_dropped.append(f"chunk {index + 1}: answer was not a list of claims")
                continue
            for raw in raw_claims:
                valid = self.validate_model_claim(raw, keys, track_ids)
                if valid is None:
                    continue
                signature = json.dumps({k: v for k, v in valid.items() if k != "quote"}, sort_keys=True)
                if signature in seen:
                    continue
                seen.add(signature)
                kept.append(valid)
        return kept

    def validate_model_claim(self, raw: Any, keys: list[tuple[str, int]], track_ids: list[str]) -> Optional[dict[str, Any]]:
        if not isinstance(raw, dict):
            self.model_dropped.append("claim that was not an object")
            return None
        kind = str(raw.get("kind") or "")
        quote = raw.get("quote")
        if not isinstance(quote, str) or not quote_in_text(quote, self.transcript):
            self.model_dropped.append(f"{kind or 'claim'} whose quote is not in the transcript")
            return None
        quote = collapse_ws(quote)
        out: dict[str, Any] = {"kind": kind, "quote": quote}
        if kind == "technique":
            technique = str(raw.get("technique") or "").strip().lower().replace(" ", "_")
            if technique not in KNOWN_TECHNIQUES:
                self.model_dropped.append(f"technique '{raw.get('technique')}' is not one the checker measures")
                return None
            name = raw.get("section")
            if isinstance(name, str) and collapse_ws(name).lower() in ("whole track", "the whole track", "mix", "master", "global"):
                out.update({"technique": technique, "section": None})
                return out
            key = self.resolve_section(name, keys)
            if key is None:
                self.model_dropped.append(f"technique '{technique}' in unknown section '{name}'")
                return None
            out.update({"technique": technique, "section": key})
            return out
        if kind == "role":
            role = str(raw.get("role") or "").strip().lower()
            if role not in ROLE_TO_TRACKS:
                self.model_dropped.append(f"role '{raw.get('role')}' has no track mapping")
                return None
            if role not in quote.lower():
                self.model_dropped.append(f"role '{role}' is not named in its quote")
                return None
            key = self.resolve_section(raw.get("section"), keys)
            if key is None:
                self.model_dropped.append(f"role '{role}' in unknown section '{raw.get('section')}'")
                return None
            out.update({"role": role, "section": key})
            return out
        if kind == "tempo":
            bpm = raw.get("bpm")
            if not isinstance(bpm, (int, float)) or isinstance(bpm, bool) or not 40 <= float(bpm) <= 300:
                self.model_dropped.append(f"tempo '{bpm}' out of range")
                return None
            out.update({"bpm": float(bpm)})
            return out
        if kind == "key":
            if normalize_key(raw.get("key")) is None:
                self.model_dropped.append(f"key '{raw.get('key')}' could not be read as a key")
                return None
            out.update({"key": str(raw.get("key")).strip()})
            return out
        if kind == "automation":
            track = str(raw.get("track") or "").strip().lower()
            parameter = str(raw.get("parameter") or "").strip().lower()
            if track != "master" and track not in track_ids:
                self.model_dropped.append(f"automation on unknown track '{raw.get('track')}'")
                return None
            # The sentence has to name the track it is about: 'chords.filter
            # 0.2->0.55' must not be filed under some other lane that exists.
            names = [track, f"{track}.{parameter}"]
            if track != "master":
                names.append(str(tracks_by_id(self.project)[track].get("name") or "").strip().lower())
            if not any(name and name in quote.lower() for name in names):
                self.model_dropped.append(f"automation filed under '{track}' but its quote does not name that track")
                return None
            if not re.fullmatch(r"[a-z]+", parameter):
                self.model_dropped.append(f"automation parameter '{raw.get('parameter')}' is not a plain word")
                return None
            values = [raw.get("from"), raw.get("to")]
            bars = [raw.get("firstBar"), raw.get("lastBar")]
            if any(not isinstance(v, (int, float)) or isinstance(v, bool) for v in values + bars):
                self.model_dropped.append(f"automation {track}.{parameter} with non-numeric values")
                return None
            start_value, end_value = float(values[0]), float(values[1])
            first, last = int(bars[0]), int(bars[1])
            if not (0.0 <= start_value <= 1.0 and 0.0 <= end_value <= 1.0 and 1 <= first <= last <= 999):
                self.model_dropped.append(f"automation {track}.{parameter} with values outside 0-1 or bad bars")
                return None
            out.update({"track": track, "parameter": parameter, "from": start_value, "to": end_value,
                        "firstBar": first, "lastBar": last})
            return out
        if kind == "transpose":
            key = self.resolve_section(raw.get("section"), keys)
            semis = raw.get("semitones")
            if key is None or not isinstance(semis, (int, float)) or isinstance(semis, bool) or not -24 <= int(semis) <= 24:
                self.model_dropped.append(f"transpose in '{raw.get('section')}' by '{semis}'")
                return None
            reference = self.resolve_section(raw.get("reference"), keys) if raw.get("reference") else None
            out.update({"section": key, "semitones": int(semis), "reference": reference})
            return out
        if kind == "octaveDouble":
            key = self.resolve_section(raw.get("section"), keys)
            if key is None:
                self.model_dropped.append(f"octave double in unknown section '{raw.get('section')}'")
                return None
            out.update({"section": key})
            return out
        self.model_dropped.append(f"unknown claim kind '{kind}'")
        return None

    def check_model_claims(self) -> None:
        """Measure the model's claims with the same code paths as the spec's.
        Anything the regexes already produced is dropped later as a duplicate,
        so the model only ever adds claims - it never replaces a measurement."""
        claims = self.extract_model_claims()
        spec_roles = {str(role) for section in self.spec.get("sections", []) or [] if isinstance(section, dict)
                      for role in (section.get("trackRoles") or [])}
        for item in claims:
            self._model_context = {"quote": item["quote"], "reason": "stated in the transcript; the parser did not carry it"}
            try:
                self.check_one_model_claim(item, spec_roles)
            finally:
                self._model_context = None

    def check_one_model_claim(self, item: dict[str, Any], spec_roles: set[str]) -> None:
        kind = item["kind"]
        if kind == "technique":
            key = item["section"]
            if key is None:
                pseudo = {"id": "model", "type": "production_notes", "trackRoles": [], "techniques": [item["technique"]]}
                self.check_technique(pseudo, item["technique"], "the whole track", self.span_for(pseudo))
                return
            pseudo = {"id": "model", "type": "second_drop" if key == ("drop", 2) else key[0],
                      "ordinalWithinType": key[1], "trackRoles": [], "techniques": [item["technique"]]}
            self.check_technique(pseudo, item["technique"], self.label(key), self.spans.get(key))
            return
        if kind == "role":
            role = item["role"]
            if role in spec_roles:
                return   # check_track_roles already measured it
            label = self.label(item["section"])
            for track_id in ROLE_TO_TRACKS.get(role, ()):
                has_content, why = track_has_content(self.root, self.project, track_id)
                article = "An" if role[:1] in "aeiou" else "A"
                self.add("tracks", f"{article} {role} part plays in {label}.", "transcript",
                         "matched" if has_content else "missing", f"track '{track_id}': {why}", "project",
                         f"Give the '{track_id}' track ({role}) audio, notes, or steps in {label} - it is named but silent.")
            return
        if kind == "tempo":
            hint = self.spec.get("tempoHint")
            if isinstance(hint, (int, float)) and hint > 0:
                return   # check_tempo already measured it
            bpm = item["bpm"]
            status = "matched" if abs(bpm - self.bpm) <= 1.0 else "contradicted"
            self.add("tempo", f"The track runs at {int(bpm)} BPM.", "transcript", status,
                     f"project bpm is {self.bpm:g}", "project",
                     f"Set the project tempo to {int(bpm)} BPM (it is {self.bpm:g}).")
            return
        if kind == "key":
            if [h for h in self.spec.get("keyHints", []) or [] if isinstance(h, str)]:
                return   # check_key already measured it
            stated = normalize_key(item["key"])
            actual_raw = self.project.get("keyCenter")
            actual = normalize_key(actual_raw)
            if actual is None:
                status, evidence = "missing", f"project has no key centre (keyCenter={actual_raw!r})"
            elif actual == stated:
                status, evidence = "matched", f"project keyCenter is {actual_raw}"
            else:
                status, evidence = "contradicted", f"project keyCenter is {actual_raw}"
            self.add("key", f"The key is {item['key']}.", "transcript", status, evidence, "project",
                     f"Set the project key centre to {item['key']}.")
            return
        if kind == "automation":
            self.check_automation_move(str(item["firstBar"]), str(item["lastBar"]), item["track"], item["parameter"],
                                       item["from"], item["to"])
            return
        if kind == "transpose":
            self.check_transpose(item["quote"], item["section"], item["semitones"], item.get("reference"))
            return
        if kind == "octaveDouble":
            self.check_octave_double(item["section"], "transcript")

    # -- the model: fixes and the summary ----------------------------------

    def report_facts(self, result: dict[str, Any]) -> dict[str, Any]:
        tracks = []
        for track_id, track in tracks_by_id(self.project).items():
            tracks.append({
                "id": track_id,
                "name": str(track.get("name") or track_id),
                "kind": str(track.get("kind") or ""),
                "effects": [{"name": str(e.get("name") or ""), "active": bool(e.get("active")), "amount": e.get("amount")}
                            for e in (track.get("effects") or []) if isinstance(e, dict)],
            })
        lanes = [f"{lane.get('trackId')}.{lane.get('parameter')}" for lane in self.snapshot.get("automationLanes", []) or []
                 if isinstance(lane, dict)]
        return {
            "score": result["score"],
            "scoreWithoutModelClaims": result["scoreWithoutModelClaims"],
            "modelClaimCount": result["modelClaimCount"],
            "measured": result["summary"],
            "claims": [{k: c.get(k) for k in ("id", "area", "claim", "status", "evidence", "verifiedBy")} for c in result["claims"]],
            "heuristicNextActions": result["nextActions"],
            "tracks": tracks,
            "automationLanes": lanes,
            "sections": [self.label(key) for key in self.known_section_keys()],
            "bpm": self.bpm,
        }

    def humanize(self, result: dict[str, Any]) -> None:
        """The summary and one ranked fix per missed claim, in the project's
        own track and effect names. The score and every claim's status are
        already final; the model only writes words about them."""
        if not self.model_available or not result["claims"]:
            return
        facts = self.report_facts(result)
        facts_text = json.dumps(facts, indent=1)
        fixable = [c["id"] for c in result["claims"] if c["status"] in ("missing", "contradicted")]
        task = (
            "Here is the measured fidelity report for one project. Write the summary, and for each claim "
            f"with status missing or contradicted ({', '.join(fixable) or 'none'}) one concrete fix, ranked "
            "most valuable first. Name tracks by id from the track list and effects by their exact names on "
            "that track; use section names from the section list. The summary may describe ONLY the claims "
            "listed with status missing or contradicted, in their own words; it must not mention lengths, "
            "timecodes, or any gap that is not a listed claim, and when every claim matched it says so. "
            "Section lengths were set by the arrangement rules on purpose and are never a gap.\n\nREPORT:\n" + facts_text
        )
        answer = self.assist.ask(task, system=FIX_ROLE, schema=FIX_SCHEMA, expect=dict)
        if not isinstance(answer, dict):
            return
        dropped: list[str] = []
        summary = answer.get("summary")
        if isinstance(summary, str) and summary.strip() and len(summary) <= 900 and numbers_are_grounded(summary, facts_text):
            result["summary"] = result["summary"] + ". " + collapse_ws(summary)
            result["summarySource"] = "model"
        else:
            dropped.append("summary")
        by_id = {c["id"]: c for c in result["claims"]}
        track_map = {t["id"]: t for t in facts["tracks"]}
        section_names = {name.lower(): name for name in facts["sections"]}
        fixes: list[dict[str, Any]] = []
        used: set[str] = set()
        raw_fixes = answer.get("fixes")
        for raw in raw_fixes if isinstance(raw_fixes, list) else []:
            if not isinstance(raw, dict):
                dropped.append("fix that was not an object")
                continue
            claim_id = str(raw.get("claimId") or "")
            claim = by_id.get(claim_id)
            if claim is None or claim["status"] not in ("missing", "contradicted"):
                dropped.append(f"fix for '{claim_id}' (not a missed claim)")
                continue
            action = raw.get("action")
            if not isinstance(action, str) or not action.strip() or len(action) > 300 or not numbers_are_grounded(action, facts_text):
                dropped.append(f"fix for {claim_id} (empty, too long, or ungrounded number)")
                continue
            track = raw.get("track")
            track = str(track).strip() if isinstance(track, str) and track.strip() else None
            if track is not None and track not in track_map:
                dropped.append(f"fix for {claim_id} naming unknown track '{track}'")
                continue
            effect = raw.get("effect")
            effect = str(effect).strip() if isinstance(effect, str) and effect.strip() else None
            if effect is not None:
                names = {e["name"].lower(): e["name"] for e in track_map[track]["effects"]} if track else {}
                if effect.lower() not in names:
                    dropped.append(f"fix for {claim_id} naming unknown effect '{effect}' on '{track}'")
                    continue
                effect = names[effect.lower()]
            section = raw.get("section")
            section = section_names.get(collapse_ws(section).lower()) if isinstance(section, str) and section.strip() else None
            if isinstance(raw.get("section"), str) and raw.get("section").strip() and section is None:
                dropped.append(f"fix for {claim_id} naming unknown section '{raw.get('section')}'")
                continue
            if claim_id in used:
                dropped.append(f"second fix for {claim_id} (one per claim)")
                continue
            why = raw.get("why")
            why = collapse_ws(why) if isinstance(why, str) and numbers_are_grounded(why, facts_text) else ""
            fix = {"claimId": claim_id, "action": collapse_ws(action), "track": track, "effect": effect,
                   "section": section, "why": why, "source": "model"}
            claim["fix"] = fix
            fixes.append(fix)
            used.add(claim_id)
        if fixes:
            result["nextActions"] = [fix["action"] for fix in fixes][:10]
            result["nextActionDetails"] = fixes[:10]
        else:
            dropped.append("nextActions")
        if dropped:
            self.assist.note = "kept the heuristic text for: " + "; ".join(dropped[:6])

    # -- driver ------------------------------------------------------------

    def run(self) -> dict[str, Any]:
        self.check_tempo()
        self.check_key()
        self.check_section_order()
        self.check_section_lengths()
        self.check_track_roles()
        self.check_techniques()
        self.check_octave_relations()
        self.check_automation_statements()
        self.check_explicit_numbers()
        self.check_model_claims()
        matched = sum(1 for c in self.claims if c["status"] == "matched")
        unverifiable = sum(1 for c in self.claims if c["status"] == "unverifiable")
        # The parser can chunk one described section into two spec sections, so
        # the same claim ("Drop 2 uses sidechain") was counted twice and the
        # score's denominator drifted. One claim per (area, statement).
        seen: set = set()
        unique: list = []
        for claim in self.claims:
            key = (str(claim.get("area", "")), str(claim.get("claim", "")).strip().lower())
            if key in seen:
                continue
            seen.add(key)
            unique.append(claim)
        self.claims = unique
        unverifiable = sum(1 for claim in self.claims if claim.get("status") == "unverifiable")
        matched = sum(1 for claim in self.claims if claim.get("status") == "matched")
        checkable = len(self.claims) - unverifiable
        score = int(round(100.0 * matched / checkable)) if checkable else 0
        # Claims the model read add to the denominator, so the score with
        # them is not the score `--ai off` gives. Both are reported: the
        # second is what the regex-and-measurement path alone would say.
        own = [claim for claim in self.claims if claim.get("source") != "model"]
        model_claim_count = len(self.claims) - len(own)
        own_matched = sum(1 for claim in own if claim.get("status") == "matched")
        own_checkable = sum(1 for claim in own if claim.get("status") != "unverifiable")
        score_without_model = int(round(100.0 * own_matched / own_checkable)) if own_checkable else 0
        summary = f"{matched} of {checkable} checkable claims match"
        if unverifiable:
            summary += f" ({unverifiable} unverifiable)"
        if model_claim_count:
            summary += (f"; {model_claim_count} claim{'s' if model_claim_count != 1 else ''} came from the model"
                        f" (without them: {own_matched} of {own_checkable}, score {score_without_model})")
        if not self.claims:
            summary = "No claims could be extracted from the transcript."
        result = {
            "ok": True,
            "projectId": str(self.project.get("id") or self.spec.get("projectId") or "project"),
            "score": score,
            "scoreWithoutModelClaims": score_without_model,
            "modelClaimCount": model_claim_count,
            "summary": summary,
            "claims": self.claims,
            "matched": matched,
            "checkable": checkable,
            "unverifiable": unverifiable,
            "stemsUsed": sorted(t for t, loaded in self.stems._cache.items() if loaded is not None),
            "nextActions": self.actions[:10],
            "nextActionDetails": [{"action": action, "source": "heuristic"} for action in self.actions[:10]],
            "summarySource": "heuristic",
        }
        self.humanize(result)
        if self.assist is not None:
            report = self.assist.report()
            if self.model_dropped:
                report["dropped"] = self.model_dropped[:12]
            result["ai"] = report
        return result


def build_report(root: Path, project_path: Path, spec_path: Path, transcript_path: Optional[str] = None,
                 assist: Any = None) -> dict[str, Any]:
    """The report. `assist` is an llm.Assist; None (the library default) means
    the model is off and the report is exactly the regex-and-measurement one."""
    project = read_json(project_path)
    spec = read_json(spec_path)
    transcript = transcript_text_for(spec_path, spec, transcript_path)
    if assist is None and llm is not None:
        assist = llm.Assist(enabled=False)
    return Checker(root, project, spec, transcript, assist).run()


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Transcript Fidelity: {report['projectId']}",
        "",
        f"**Score:** {report['score']}/100 - {report['summary']}",
    ]
    if report.get("modelClaimCount"):
        lines.append(f"**Score without the model's claims:** {report.get('scoreWithoutModelClaims')}/100")
    lines += [
        "",
        "| # | Area | Claim | Status | Evidence |",
        "|---|------|-------|--------|----------|",
    ]
    for claim in report["claims"]:
        status = claim["status"]
        if status in ("matched", "missing", "contradicted"):
            status = f"{status} ({claim['verifiedBy']})"
        cell = lambda text: str(text).replace("|", "\\|")  # noqa: E731
        lines.append(f"| {claim['id'].replace('claim-', '')} | {claim['area']} | {cell(claim['claim'])} | {status} | {cell(claim['evidence'])} |")
    lines.extend(["", "## Next Actions", ""])
    details = report.get("nextActionDetails") or []
    if report["nextActions"]:
        for index, item in enumerate(report["nextActions"]):
            detail = details[index] if index < len(details) and isinstance(details[index], dict) else {}
            tail = ""
            if detail.get("claimId"):
                tail += f" [{str(detail['claimId']).replace('claim-', '#')}]"
            if detail.get("why"):
                tail += f" - {detail['why']}"
            lines.append(f"- {item}{tail}")
    else:
        lines.append("- Nothing stated in the description is missing from the project.")
    lines.append("")
    ai = report.get("ai") or {}
    if ai:
        lines.append(f"_Claims and fixes: {'via ' + str(ai.get('provider')) if ai.get('used') else 'offline rules'}"
                     + (f" - {ai['note']}" if ai.get("note") else "") + "_")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check a Neon Studio project against what its transcript said.")
    parser.add_argument("--root", default=".", help="Workspace root (holds data/, songlab/, exports/).")
    parser.add_argument("--project-id", help="Project id, e.g. neon-alone.")
    parser.add_argument("--project", help="Path to a .neon.json file.")
    parser.add_argument("--spec", help="Path to a transcript_spec.json file.")
    parser.add_argument("--transcript", help="Path to the transcript text (defaults to the spec's sibling transcript.txt).")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    if llm is not None:
        llm.add_ai_argument(parser)
    args = parser.parse_args()

    try:
        root = Path(args.root).expanduser().resolve()
        project_path = project_path_for(root, args.project_id, args.project)
        spec_path = spec_path_for(root, args.project_id, args.spec)
        assist = llm.assist_from_args(args) if llm is not None else None
        report = build_report(root, project_path, spec_path, args.transcript, assist)
    except Exception as exc:  # the caller parses the last line, so it must be JSON
        if args.format == "markdown":
            print(f"Transcript fidelity failed: {exc}")
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    if args.format == "markdown":
        print(render_markdown(report))
    else:
        print(json.dumps(report, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
