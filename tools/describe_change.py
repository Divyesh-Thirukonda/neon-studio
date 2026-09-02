#!/usr/bin/env python3
"""Turn a plain-words request ("make the drop hit harder") into concrete project edits.

This is the typed counterpart to singing a correction. The user says what they want in
their own words; the tool turns it into clauses in a small explicit vocabulary (an intent, a
direction, a size, a track, a section) and applies the matching edit to a copy of the
project. When it does not understand a clause it says so and lists phrasings it does
understand, rather than guessing and making a random edit.

Reading the words is the only part a language model helps with (see docs/ai.md). When a key
is present the model reads the whole request with the project's tracks and sections and
returns the clauses already normalised; everything it returns is checked against the
project, and the hand-written grammar handles whatever it drops. With no key, `--ai off` or
NEON_AI=off the grammar runs alone, exactly as before. The edits themselves are deterministic
arithmetic either way.

Every edit is recorded as {title, detail, trackIds, section, source, why} so the app can
show it and undo it. The input project is never modified; the result goes to --output.

CLI:
  describe_change.py --root ROOT --project PATH --request "..." --output OUT.neon.json
                     [--format json|markdown] [--ai auto|off]
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from copy import deepcopy
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import daw_agent  # noqa: E402
from llm import Assist, add_ai_argument, assist_from_args  # noqa: E402
from project_materializer import TRACK_BLUEPRINTS, make_track  # noqa: E402


# ---------------------------------------------------------------------------
# Grammar tables. Everything the parser knows lives here so the behaviour is
# inspectable: an intent is a list of phrases, a target is a track or a section,
# an amount is a step count.
# ---------------------------------------------------------------------------

GAIN_STEP = 0.08
EQ_STEP = 0.15
SWING_STEP = 8
WIDTH_STEP = 0.1  # two default steps give the +-0.2 the product spec asks for
SPACE_STEP = 0.15
BPM_STEPS = {1: 4, 2: 8, 3: 10}  # "a lot" is capped at 10 so the song stays recognisable
LENGTH_BARS = 4
HARD_GAIN_STEP = 0.04
HARD_GRIT_STEP = 0.05  # two default steps give the +0.1 grit the product spec asks for

AMOUNT_WORDS = (
    # Checked in order; the first hit wins. Multi-word phrases come first so "a lot" is not
    # read as the single word "a".
    (("a tiny bit", "a touch", "a tad", "a little", "a bit", "slightly", "subtly", "just"), 1),
    (("a lot", "a ton", "a bunch", "way", "much", "really", "massively", "heavily", "seriously", "significantly", "drastically"), 3),
)

# Section words -> canonical section type. "chorus" is the drop for this kind of music.
SECTION_WORDS = {
    "intro": "intro",
    "introduction": "intro",
    "verse": "verse",
    "verses": "verse",
    "pre-build": "pre_build",
    "prebuild": "pre_build",
    "pre build": "pre_build",
    "pre-drop": "pre_build",
    "build": "build",
    "builds": "build",
    "buildup": "build",
    "build-up": "build",
    "build up": "build",
    "riser section": "build",
    "drop": "drop",
    "drops": "drop",
    "chorus": "drop",
    "hook section": "drop",
    "break": "break",
    "breakdown": "break",
    "bridge": "break",
    "outro": "outro",
    "ending": "outro",
    "end": "outro",
}
ORDINAL_WORDS = {"first": 1, "1st": 1, "one": 1, "1": 1, "second": 2, "2nd": 2, "two": 2, "2": 2, "third": 3, "3rd": 3, "3": 3}
WHOLE_SONG_WORDS = ("whole song", "whole track", "whole thing", "entire song", "everything", "the song", "the mix", "overall", "the track", "it all")

# Role aliases -> the words that identify a track of that role in its id or name.
ROLE_ALIASES = {
    "lead": ("lead", "melody", "hook", "topline", "main synth"),
    "bass": ("bass", "bassline"),
    "sub": ("sub", "808", "sub bass"),
    "drums": ("drums", "drum", "kick", "beat", "kit", "percussion"),
    "hat": ("hats", "hat", "hihat", "hihats", "hi-hat", "hi-hats", "ride", "cymbal", "cymbals"),
    "clap": ("clap", "claps", "snare", "snares"),
    "vocal": ("vocal", "vocals", "vox", "voice", "singer", "singing"),
    "chords": ("chords", "chord", "pad", "pads", "keys", "piano", "harmony", "stabs"),
    "fx": ("fx", "effects", "riser", "risers", "sweep", "sweeps", "transitions", "impact", "impacts"),
    "plucks": ("plucks", "pluck", "texture", "arp", "arps"),
    "guitar": ("guitar", "guitars"),
    "sample": ("sample", "samples", "vocal chop", "chop", "chops"),
}
ROLE_WORD_TO_ROLE = {word: role for role, words in ROLE_ALIASES.items() for word in words}

# "add X" roles -> (base blueprint id, new track id, new track name, steps override)
ADD_ROLES = {
    "hats": ("drums", "hats", "Hats", [2, 6, 10, 14]),
    "hat": ("drums", "hats", "Hats", [2, 6, 10, 14]),
    "hihats": ("drums", "hats", "Hats", [2, 6, 10, 14]),
    "hi-hats": ("drums", "hats", "Hats", [2, 6, 10, 14]),
    "riser": ("fx", "riser", "Riser", []),
    "risers": ("fx", "riser", "Riser", []),
    "sub": ("sub", "sub", "Sub", [0, 8]),
    "808": ("sub", "sub", "Sub", [0, 8]),
    "clap": ("drums", "clap", "Clap", [4, 12]),
    "claps": ("drums", "clap", "Clap", [4, 12]),
    "snare": ("drums", "clap", "Clap", [4, 12]),
    "pad": ("chords", "pad", "Pad", []),
    "pads": ("chords", "pad", "Pad", []),
}

# Effect-name keywords. Matching is by substring on the lowercased effect name so the
# project's own naming ("Air EQ", "Kick Duck", "Wide Plate") is honoured.
EFFECT_KEYWORDS = {
    "eq": ("eq", "air", "bright", "filter", "tilt", "high shelf", "lowpass", "low pass", "highpass"),
    "reverb": ("reverb", "verb", "plate", "hall", "room", "space"),
    "delay": ("delay", "echo", "ping"),
    "width": ("stereo", "width", "wide", "spread", "haas"),
    "sidechain": ("sidechain", "duck", "pump"),
    "grit": ("saturat", "distort", "grit", "drive", "clip", "overdrive", "fuzz", "crush"),
}
DEFAULT_EFFECT_NAMES = {"eq": "EQ", "reverb": "Reverb", "delay": "Delay", "width": "Stereo Width", "sidechain": "Sidechain", "grit": "Saturator"}

# Intent table: (intent id, direction, regex). Order matters — the more specific patterns
# (tempo words, "add back", "hit harder") come before the looser single words that would
# otherwise swallow them.
INTENT_PATTERNS: list[tuple[str, int, str]] = [
    ("tempo", +1, r"\b(faster|speed (it )?up|quicker|higher (bpm|tempo)|more tempo|bpm up|tempo up)\b"),
    ("tempo", -1, r"\b(slower|slow (it )?down|lower (bpm|tempo)|less tempo|bpm down|tempo down)\b"),
    ("mute", -1, r"\b(bring back|unmute|un-mute|restore|add back|put back)\b"),
    ("mute", +1, r"\b(mute|remove|take out|get rid of|kill|silence|delete|ditch)\b"),
    ("energy", +1, r"\b(more |extra |some )?(energy|hype|tension|excitement|anticipation|lift)\b|\b(hype (it |up )?|energetic|more exciting)"),
    ("add", +1, r"\b(add|put in|bring in|throw in|introduce|needs? (some |a |more )?)\b"),
    ("bounce", +1, r"\b(more|extra|some)\s+(bounce|swing|groove|shuffle)\b|\b(bouncier|groovier|swingier|swing it|swung|more swing)\b"),
    ("bounce", -1, r"\b(less|no|remove the)\s+(bounce|swing|groove|shuffle)\b|\b(straighter|stiffer|less swung|un-?swing)\b"),
    ("space", +1, r"\b(more|extra|some|bigger|longer)\s+(space|reverb|echo|delay|ambience|ambiance|room|verb|tail|air)\b|\b(wetter|spacier|roomier|more atmospheric|drench)\b"),
    ("space", -1, r"\b(less|no|tighter|shorter)\s+(space|reverb|echo|delay|ambience|ambiance|room|verb|tail)\b|\b(drier|dryer|dry|less wet|less washy)\b"),
    ("width", +1, r"\b(wider|wide|more (width|stereo)|spread (it|out)|open up the stereo|widen)\b"),
    ("width", -1, r"\b(narrower|narrow|more mono|less (wide|width|stereo)|mono it|tighten the stereo|centre it|center it)\b"),
    ("length", +1, r"\b(longer|extend|stretch|lengthen|more bars)\b"),
    ("length", -1, r"\b(shorter|shorten|trim|cut down|fewer bars|tighten up)\b"),
    ("pitch", +1, r"\b(higher|up an octave|octave up|pitch (it )?up|transpose up|raise|an octave higher)\b"),
    ("pitch", -1, r"\b(lower|down an octave|octave down|pitch (it )?down|transpose down|an octave lower)\b"),
    ("gain", +1, r"\b(louder|loud|turn (it |them )?up|bring (it |them )?up|boost|more volume|volume up|push (it )?up|too quiet)\b"),
    ("gain", -1, r"\b(quieter|quiet|turn (it |them )?down|bring (it |them )?down|less volume|volume down|pull (it )?down|too loud|lower the volume)\b"),
    ("tone", +1, r"\b(brighter|bright|brighten|more (top|top end|air|sparkle|presence)|crisper|crispier|shinier)\b"),
    ("tone", -1, r"\b(darker|dark|darken|duller|warmer|mellower|less (bright|top|top end|harsh)|smoother)\b"),
    ("hard", +1, r"\b(harder|hit harder|hits harder|bigger|punchier|punchy|punch|heavier|heavy|slap|slaps|more impact|more power|powerful|fatter|thicker|more aggressive|hit)\b"),
    ("hard", -1, r"\b(softer|smaller|calmer|calm|gentler|gentle|lighter|less intense|less hard|less aggressive|chill it out|tone it down)\b"),
]

SUGGESTIONS = [
    "make the drop hit harder",
    "louder drums in the drop",
    "give the lead more space",
    "make the bass a bit brighter",
    "more bounce",
    "add hats in the second drop",
    "make the build longer",
    "put the lead up an octave",
    "mute the vocals",
    "more energy in the build",
]

CLAUSE_SPLIT = re.compile(r"\s*(?:,|;|\band\b|\bthen\b|\balso\b|\bplus\b)\s*")
POLITE_PREFIX = re.compile(r"^(please|can you|could you|would you|i want|i'd like|i would like|let's|lets|make|give|try to|try|just)\s+", re.IGNORECASE)


@dataclass
class Clause:
    text: str
    intent: Optional[str] = None
    direction: int = 0
    steps: int = 2
    track_id: Optional[str] = None
    section: Optional["Section"] = None
    whole_song: bool = False
    add_role: Optional[str] = None
    # Set only by the model. The grammar never fills these, so the appliers fall back to the
    # fixed step constants whenever they are None.
    amount_value: Optional[float] = None  # in the applier's own unit (bpm, bars, semitones, gain, 0..1 amount, swing points)
    amount_label: Optional[str] = None    # how the person said it, for the restatement ("10 bpm")
    effect: Optional[str] = None          # "reverb" | "delay" | "both" for the space intent
    add_id: Optional[str] = None
    add_name: Optional[str] = None
    add_steps: Optional[list[int]] = None
    why: str = ""
    source: str = "grammar"


@dataclass
class Section:
    type: str
    ordinal: int
    start_bar: int
    end_bar: int  # exclusive
    name: Optional[str] = None  # a described bar range ("bars 32-40") rather than a named section

    @property
    def label(self) -> str:
        if self.name:
            return self.name
        words = self.type.replace("_", " ")
        prefix = {2: "second ", 3: "third "}.get(self.ordinal, f"{self.ordinal}th " if self.ordinal > 3 else "")
        return prefix + words

    @property
    def bars(self) -> int:
        return self.end_bar - self.start_bar

    @property
    def key(self) -> str:
        return f"{self.type}-{self.ordinal}"


# ---------------------------------------------------------------------------
# Project helpers
# ---------------------------------------------------------------------------


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def r2(value: float) -> float:
    return round(value + 0.0, 2)


def tracks_of(project: dict[str, Any]) -> list[dict[str, Any]]:
    return [t for t in project.get("snapshot", {}).get("tracks", []) if isinstance(t, dict)]


def track_by_id(project: dict[str, Any], track_id: str) -> Optional[dict[str, Any]]:
    for track in tracks_of(project):
        if track.get("id") == track_id:
            return track
    return None


def ensure_controls(project: dict[str, Any], track: dict[str, Any]) -> dict[str, Any]:
    controls = project["snapshot"].setdefault("controls", {})
    entry = controls.get(track["id"])
    if not isinstance(entry, dict):
        entry = {
            "gain": float(track.get("gain", 0.8)),
            "pan": float(track.get("pan", 0.0)),
            "mute": False,
            "solo": False,
            "arm": False,
            "sendA": 0.15,
            "sendB": 0.08,
        }
        controls[track["id"]] = entry
    return entry


def words_of(text: str) -> list[str]:
    return [w for w in re.split(r"[^a-z0-9]+", text.lower()) if w]


def classify_section_name(name: str) -> Optional[tuple[str, int]]:
    """Read a clip/recipe name like 'Drop 2 hook' as ('drop', 2)."""
    lowered = name.lower()
    words = words_of(lowered)
    found: Optional[str] = None
    for phrase in sorted(SECTION_WORDS, key=len, reverse=True):
        if re.search(r"\b" + re.escape(phrase) + r"\b", lowered):
            found = SECTION_WORDS[phrase]
            break
    if found is None:
        return None
    ordinal = 1
    for word in words:
        if word in ORDINAL_WORDS and word not in ("one",):
            ordinal = ORDINAL_WORDS[word]
            break
    return found, ordinal


def project_sections(project: dict[str, Any]) -> list[Section]:
    """Derive the arrangement's sections from clip names, since the project has no section list.

    Clips of one type are clustered by bar position rather than by the number in their name:
    "Drop 1 impact" and "Drop hats" share a cluster, and a second cluster further along the
    timeline is the second drop even when nobody wrote "2" in the clip name."""
    snapshot = project.get("snapshot", {})
    spans: dict[str, list[tuple[int, int]]] = {}

    explicit = snapshot.get("sections")
    if isinstance(explicit, list):
        for item in explicit:
            if not isinstance(item, dict) or "startBar" not in item:
                continue
            parsed = classify_section_name(str(item.get("type") or item.get("label") or ""))
            if parsed is None:
                continue
            start = int(item["startBar"])
            spans.setdefault(parsed[0], []).append((start, start + int(item.get("bars", 8))))

    for track in tracks_of(project):
        for clip in track.get("clips", []) or []:
            parsed = classify_section_name(str(clip.get("name", "")))
            if parsed is None:
                continue
            start = int(clip.get("startBar", 0))
            spans.setdefault(parsed[0], []).append((start, start + max(1, int(clip.get("bars", 1)))))

    sections: list[Section] = []
    for kind, ranges in spans.items():
        clusters: list[list[int]] = []
        for start, end in sorted(ranges):
            if clusters and start <= clusters[-1][1]:
                clusters[-1][1] = max(clusters[-1][1], end)
            else:
                clusters.append([start, end])
        for ordinal, (start, end) in enumerate(clusters, start=1):
            sections.append(Section(kind, ordinal, start, end))
    sections.sort(key=lambda s: (s.start_bar, s.ordinal))
    return sections


def song_extent(project: dict[str, Any]) -> tuple[int, int]:
    end = 0
    for track in tracks_of(project):
        for clip in track.get("clips", []) or []:
            end = max(end, int(clip.get("startBar", 0)) + int(clip.get("bars", 0)))
    return 0, max(end, int(project.get("snapshot", {}).get("loopEndBar", 0) or 0))


def tracks_in_section(project: dict[str, Any], section: Section) -> list[dict[str, Any]]:
    hits = []
    for track in tracks_of(project):
        for clip in track.get("clips", []) or []:
            start = int(clip.get("startBar", 0))
            end = start + int(clip.get("bars", 0))
            if start < section.end_bar and end > section.start_bar:
                hits.append(track)
                break
    return hits


def track_roles(track: dict[str, Any]) -> set[str]:
    words = set(words_of(str(track.get("id", ""))) + words_of(str(track.get("name", ""))))
    roles = set()
    for word in words:
        if word in ROLE_WORD_TO_ROLE:
            roles.add(ROLE_WORD_TO_ROLE[word])
    return roles


def find_effect(track: dict[str, Any], kind: str) -> Optional[dict[str, Any]]:
    for effect in track.get("effects", []) or []:
        name = str(effect.get("name", "")).lower()
        if any(key in name for key in EFFECT_KEYWORDS[kind]):
            return effect
    return None


def ensure_effect(track: dict[str, Any], kind: str, start_amount: float = 0.5) -> tuple[dict[str, Any], bool]:
    """Return (effect, created). A missing effect is added so the request still lands."""
    effect = find_effect(track, kind)
    if effect is not None:
        return effect, False
    effects = track.setdefault("effects", [])
    effect = {"id": f"{kind}-{track['id']}", "name": DEFAULT_EFFECT_NAMES[kind], "active": True, "amount": r2(start_amount)}
    effects.append(effect)
    return effect, True


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_amount(text: str) -> int:
    for phrases, steps in AMOUNT_WORDS:
        for phrase in phrases:
            if re.search(r"\b" + re.escape(phrase) + r"\b", text):
                return steps
    return 2


def parse_section(text: str, sections: list[Section]) -> tuple[Optional[Section], Optional[str]]:
    """Return (section, wanted_label). wanted_label is set when the words named a section
    the project does not have, so the caller can report it honestly."""
    lowered = text.lower()
    found_type: Optional[str] = None
    found_phrase = ""
    for phrase in sorted(SECTION_WORDS, key=len, reverse=True):
        # A bare section noun ("shorter build") counts too; none of the intent verbs collide
        # with a section word, so there is no "drop the hats" ambiguity to guard against.
        if re.search(r"\b" + re.escape(phrase) + r"\b", lowered):
            found_type = SECTION_WORDS[phrase]
            found_phrase = phrase
            break
    if found_type is None:
        return None, None
    ordinal = 1
    around = re.search(r"(\w+)\s+" + re.escape(found_phrase) + r"(?:\s+(\w+))?", lowered)
    if around:
        for candidate in (around.group(1), around.group(2)):
            if candidate in ORDINAL_WORDS and candidate not in ("one", "1"):
                ordinal = ORDINAL_WORDS[candidate]
            if candidate == "last":
                ordinal = max([s.ordinal for s in sections if s.type == found_type] or [1])
    for section in sections:
        if section.type == found_type and section.ordinal == ordinal:
            return section, None
    # "the drop" when only a second drop exists still means something concrete.
    same_type = [s for s in sections if s.type == found_type]
    if same_type and ordinal == 1:
        return same_type[0], None
    return None, Section(found_type, ordinal, 0, 0).label


def parse_track(text: str, project: dict[str, Any], skip: set[str]) -> Optional[str]:
    """Fuzzy-match a track by name: 'the lead', 'bass', 'hats', 'vocal', 'chords'."""
    tracks = tracks_of(project)
    if not tracks:
        return None
    lowered = text.lower()
    best_score = 0
    best_id: Optional[str] = None

    # Whole-name match first ("hook lead", "mid bass") so multi-word names win outright.
    for track in tracks:
        name = str(track.get("name", "")).lower()
        if name and re.search(r"\b" + re.escape(name) + r"\b", lowered):
            return str(track["id"])

    clause_words = [w for w in words_of(lowered) if w not in skip]
    for track in tracks:
        track_id = str(track.get("id", ""))
        id_words = set(words_of(track_id))
        name_words = set(words_of(str(track.get("name", ""))))
        roles = track_roles(track)
        score = 0
        for word in clause_words:
            singular = word[:-1] if word.endswith("s") and len(word) > 3 else word
            if word == track_id or singular == track_id:
                score = max(score, 100)
            elif word in id_words or singular in id_words:
                score = max(score, 80)
            elif word in name_words or singular in name_words:
                score = max(score, 60)
            elif ROLE_WORD_TO_ROLE.get(word) in roles or ROLE_WORD_TO_ROLE.get(singular) in roles:
                score = max(score, 40)
            else:
                vocabulary = list(id_words | name_words)
                if len(word) >= 4 and difflib.get_close_matches(word, vocabulary, n=1, cutoff=0.8):
                    score = max(score, 20)
        if score > best_score:
            best_score = score
            best_id = track_id
    return best_id


def intent_words() -> set[str]:
    """Words that belong to the grammar, so the track matcher does not read 'drop' or 'bass'
    out of an intent phrase like 'more bass'? (it should) — but must ignore 'space', 'hit'."""
    words: set[str] = set()
    for _, _, pattern in INTENT_PATTERNS:
        words.update(w for w in re.findall(r"[a-z]+", pattern) if len(w) > 1)
    words.update(SECTION_WORDS)
    words.update(ORDINAL_WORDS)
    words.update({"the", "a", "an", "in", "on", "of", "it", "its", "make", "give", "more", "less", "some", "bit", "lot", "way", "much", "and", "to", "up", "down", "with", "please", "song", "track", "mix", "whole", "step", "steps"})
    return words


GRAMMAR_WORDS = intent_words()


def parse_clause(text: str, project: dict[str, Any], sections: list[Section]) -> tuple[Clause, Optional[str]]:
    """Return (clause, problem). problem is a plain-words reason the clause cannot be applied."""
    cleaned = POLITE_PREFIX.sub("", text.strip().lower()).strip()
    cleaned = POLITE_PREFIX.sub("", cleaned).strip()
    clause = Clause(text=text.strip())
    if not cleaned:
        return clause, "empty request"

    for intent, direction, pattern in INTENT_PATTERNS:
        if re.search(pattern, cleaned):
            clause.intent = intent
            clause.direction = direction
            break
    if clause.intent is None:
        return clause, "no known intent word"

    clause.steps = parse_amount(cleaned)
    clause.whole_song = any(phrase in cleaned for phrase in WHOLE_SONG_WORDS)
    section, missing = parse_section(cleaned, sections)
    clause.section = section
    if missing is not None:
        return clause, f"this project has no {missing} section"

    if clause.intent == "add":
        for role in sorted(ADD_ROLES, key=len, reverse=True):
            if re.search(r"\b" + re.escape(role) + r"\b", cleaned):
                clause.add_role = role
                break
        if clause.add_role is None:
            return clause, "add what? (hats, riser, sub, clap, pad)"
        return clause, None

    if not clause.whole_song:
        clause.track_id = parse_track(cleaned, project, GRAMMAR_WORDS)

    # Intents that need a track and got none. "hard"/"length"/"energy" fall back to a
    # section or the drop; "gain"/"tone"/... with nothing named apply to nothing sensible.
    needs_track = {"tone", "width", "space", "pitch", "mute", "gain"}
    if clause.intent in needs_track and clause.track_id is None:
        if clause.intent == "gain" and (clause.section is not None or clause.whole_song):
            return clause, None
        return clause, "which track? (e.g. the lead, bass, drums, vocals, chords, hats)"
    return clause, None


def restate(clause: Clause, project: dict[str, Any]) -> str:
    """Normalised restatement of one clause, e.g. 'Make the drop hit harder (2 steps)'."""
    steps = f" ({clause.amount_label})" if clause.amount_label else f" ({clause.steps} step{'s' if clause.steps != 1 else ''})"
    section = f" in the {clause.section.label}" if clause.section else ""
    owner = track_by_id(project, clause.track_id or "")
    track = f"the {owner['name']}" if owner else (clause.track_id or "")
    verbs = {
        ("gain", +1): f"Make {track or 'it'} louder{section}",
        ("gain", -1): f"Make {track or 'it'} quieter{section}",
        ("tone", +1): f"Make {track} brighter",
        ("tone", -1): f"Make {track} darker",
        ("hard", +1): f"Make the {clause.section.label if clause.section else (track or 'song')} hit harder",
        ("hard", -1): f"Make the {clause.section.label if clause.section else (track or 'song')} softer",
        ("bounce", +1): "More bounce",
        ("bounce", -1): "Less bounce",
        ("width", +1): f"Make {track} wider",
        ("width", -1): f"Make {track} narrower",
        ("space", +1): f"Give {track} more space",
        ("space", -1): f"Give {track} less space",
        ("tempo", +1): "Faster",
        ("tempo", -1): "Slower",
        ("length", +1): f"Make the {clause.section.label if clause.section else 'outro'} longer",
        ("length", -1): f"Make the {clause.section.label if clause.section else 'outro'} shorter",
        ("pitch", +1): f"Put {track} higher",
        ("pitch", -1): f"Put {track} lower",
        ("mute", +1): f"Mute {track}",
        ("mute", -1): f"Bring back {track}",
        ("add", +1): f"Add {clause.add_role}{section or ' in the drop'}",
        ("energy", +1): f"More energy{section or ' in the build'}",
    }
    base = verbs.get((clause.intent or "", clause.direction), clause.text)
    if clause.intent in ("mute", "add", "energy"):
        return base
    return base + steps


# ---------------------------------------------------------------------------
# Edits. Each returns a list of edit records and mutates `project` in place.
# ---------------------------------------------------------------------------


def edit_record(title: str, detail: str, track_ids: list[str], section: Optional[Section]) -> dict[str, Any]:
    return {"title": title, "detail": detail, "trackIds": track_ids, "section": section.label if section else None}


def magnitude(clause: Clause, default: float) -> float:
    """How much to move: the amount the person stated, else the fixed step arithmetic."""
    return default if clause.amount_value is None else clause.amount_value


def apply_gain(project: dict[str, Any], clause: Clause) -> list[dict[str, Any]]:
    if clause.track_id:
        targets = [track_by_id(project, clause.track_id)]
    elif clause.section:
        targets = [t for t in tracks_in_section(project, clause.section) if t.get("kind") != "automation"]
    else:
        targets = [t for t in tracks_of(project) if t.get("kind") != "automation"]
    delta = magnitude(clause, GAIN_STEP * clause.steps) * clause.direction
    edits = []
    for track in targets:
        if track is None:
            continue
        controls = ensure_controls(project, track)
        before = float(controls.get("gain", track.get("gain", 0.8)))
        after = r2(clamp(before + delta, 0.0, 1.4))
        controls["gain"] = after
        track["gain"] = after
        word = "Louder" if clause.direction > 0 else "Quieter"
        where = f" in the {clause.section.label}" if clause.section else ""
        note = " (gain is per track, so this applies wherever the track plays)" if clause.section else ""
        edits.append(edit_record(f"{word} {track['name']}{where}", f"{track['id']} gain {before:.2f} -> {after:.2f}{note}", [track["id"]], clause.section))
    return edits


def apply_tone(project: dict[str, Any], clause: Clause) -> list[dict[str, Any]]:
    track = track_by_id(project, clause.track_id or "")
    if track is None:
        return []
    effect, created = ensure_effect(track, "eq", 0.5)
    before = float(effect.get("amount", 0.5))
    after = r2(clamp(before + magnitude(clause, EQ_STEP * clause.steps) * clause.direction, 0.0, 1.0))
    effect["amount"] = after
    effect["active"] = True
    word = "Brighter" if clause.direction > 0 else "Darker"
    made = " (added)" if created else ""
    return [edit_record(f"{word} {track['name']}", f"{track['id']} {effect['name']}{made} amount {before:.2f} -> {after:.2f}, active", [track["id"]], None)]


def apply_hard(project: dict[str, Any], clause: Clause) -> list[dict[str, Any]]:
    """Harder = drums and bass up, sidechain on, bass grit up. Softer is the inverse."""
    sections = project_sections(project)
    section = clause.section
    if section is None and clause.track_id is None:
        section = next((s for s in sections if s.type == "drop"), None)
    if clause.track_id:
        pool = [t for t in [track_by_id(project, clause.track_id)] if t]
    elif section is not None:
        pool = tracks_in_section(project, section)
    else:
        pool = tracks_of(project)
    sign = clause.direction
    edits: list[dict[str, Any]] = []
    changed_ids: list[str] = []
    details: list[str] = []
    low_roles = {"drums", "bass", "sub", "clap", "hat"}
    for track in pool:
        roles = track_roles(track)
        if track.get("kind") == "automation":
            continue
        if roles & low_roles or clause.track_id:
            controls = ensure_controls(project, track)
            before = float(controls.get("gain", track.get("gain", 0.8)))
            after = r2(clamp(before + HARD_GAIN_STEP * clause.steps * sign, 0.0, 1.4))
            if after != before:
                controls["gain"] = after
                track["gain"] = after
                details.append(f"{track['id']} gain {before:.2f} -> {after:.2f}")
                changed_ids.append(track["id"])
        duck = find_effect(track, "sidechain")
        if duck is not None and bool(duck.get("active")) != (sign > 0):
            duck["active"] = sign > 0
            details.append(f"{track['id']} {duck['name']} {'on' if sign > 0 else 'off'}")
            if track["id"] not in changed_ids:
                changed_ids.append(track["id"])
        if "bass" in roles or "sub" in roles:
            grit, created = ensure_effect(track, "grit", 0.3) if sign > 0 else (find_effect(track, "grit"), False)
            if grit is not None:
                before_g = float(grit.get("amount", 0.3))
                after_g = r2(clamp(before_g + HARD_GRIT_STEP * clause.steps * sign, 0.0, 1.0))
                grit["amount"] = after_g
                grit["active"] = after_g > 0
                details.append(f"{track['id']} {grit['name']}{' (added)' if created else ''} {before_g:.2f} -> {after_g:.2f}")
                if track["id"] not in changed_ids:
                    changed_ids.append(track["id"])
    if not details:
        return []
    target = section.label if section else (clause.track_id or "song")
    title = f"{'Harder' if sign > 0 else 'Softer'} {target}"
    edits.append(edit_record(title, "; ".join(details), changed_ids, section))
    return edits


def apply_bounce(project: dict[str, Any], clause: Clause) -> list[dict[str, Any]]:
    snapshot = project["snapshot"]
    before = int(snapshot.get("swing", 0) or 0)
    after = int(clamp(before + magnitude(clause, SWING_STEP * clause.steps) * clause.direction, 0, 75))
    snapshot["swing"] = after
    return [edit_record("More bounce" if clause.direction > 0 else "Less bounce", f"swing {before} -> {after}", [], None)]


def apply_width(project: dict[str, Any], clause: Clause) -> list[dict[str, Any]]:
    track = track_by_id(project, clause.track_id or "")
    if track is None:
        return []
    effect, created = ensure_effect(track, "width", 0.4)
    before = float(effect.get("amount", 0.4))
    after = r2(clamp(before + magnitude(clause, WIDTH_STEP * clause.steps) * clause.direction, 0.0, 1.0))
    effect["amount"] = after
    effect["active"] = True
    controls = ensure_controls(project, track)
    pan_before = float(controls.get("pan", track.get("pan", 0.0)))
    # Pan spread pushes an off-centre track further out (wider) or back in (narrower).
    # A centred track has no direction to spread in, so it stays put and we say so.
    factor = 1 + 0.25 * clause.steps * clause.direction
    pan_after = r2(clamp(pan_before * factor, -1.0, 1.0))
    controls["pan"] = pan_after
    track["pan"] = pan_after
    pan_note = f", pan {pan_before:.2f} -> {pan_after:.2f}" if pan_before != 0 else ", pan stays centred"
    word = "Wider" if clause.direction > 0 else "Narrower"
    return [edit_record(f"{word} {track['name']}", f"{track['id']} {effect['name']}{' (added)' if created else ''} amount {before:.2f} -> {after:.2f}, active{pan_note}", [track["id"]], None)]


def apply_space(project: dict[str, Any], clause: Clause) -> list[dict[str, Any]]:
    track = track_by_id(project, clause.track_id or "")
    if track is None:
        return []
    lowered = clause.text.lower()
    kinds = ["delay"] if re.search(r"\b(echo|delay|ping)\b", lowered) and not re.search(r"\b(reverb|verb|space|room)\b", lowered) else ["reverb"]
    if re.search(r"\b(echo|delay)\b", lowered) and re.search(r"\b(reverb|verb|space)\b", lowered):
        kinds = ["reverb", "delay"]
    if clause.effect in ("reverb", "delay"):
        kinds = [clause.effect]
    elif clause.effect == "both":
        kinds = ["reverb", "delay"]
    details = []
    for kind in kinds:
        if clause.direction > 0:
            effect, created = ensure_effect(track, kind, 0.2)
        else:
            effect, created = find_effect(track, kind), False
            if effect is None:
                continue
        before = float(effect.get("amount", 0.2))
        after = r2(clamp(before + magnitude(clause, SPACE_STEP * clause.steps) * clause.direction, 0.0, 1.0))
        effect["amount"] = after
        effect["active"] = after > 0
        details.append(f"{effect['name']}{' (added)' if created else ''} amount {before:.2f} -> {after:.2f}, {'active' if after > 0 else 'off'}")
    if not details:
        return []
    word = "More space for" if clause.direction > 0 else "Less space for"
    return [edit_record(f"{word} {track['name']}", f"{track['id']} " + "; ".join(details), [track["id"]], None)]


def apply_tempo(project: dict[str, Any], clause: Clause) -> list[dict[str, Any]]:
    snapshot = project["snapshot"]
    before = int(snapshot.get("bpm", 120) or 120)
    after = int(clamp(before + int(round(magnitude(clause, BPM_STEPS.get(clause.steps, 8)))) * clause.direction, 40, 250))
    snapshot["bpm"] = after
    return [edit_record("Faster" if clause.direction > 0 else "Slower", f"bpm {before} -> {after}", [], None)]


def apply_length(project: dict[str, Any], clause: Clause) -> list[dict[str, Any]]:
    """Grow or shrink every clip in the section by 4 bars and slide everything after it."""
    sections = project_sections(project)
    section = clause.section
    if section is None:
        section = next((s for s in sections if s.type == "outro"), sections[-1] if sections else None)
    if section is None:
        return []
    bars = max(1, int(round(magnitude(clause, LENGTH_BARS))))
    delta = bars * clause.direction
    if clause.direction < 0 and section.bars <= bars:
        delta = -(section.bars - 1)  # never shrink a section to nothing
    if delta == 0:
        return []
    boundary = section.end_bar
    touched: list[str] = []
    for track in tracks_of(project):
        for clip in track.get("clips", []) or []:
            start = int(clip.get("startBar", 0))
            bars = int(clip.get("bars", 0))
            if start < boundary and start + bars > section.start_bar:
                clip["bars"] = max(1, bars + delta)
                if track["id"] not in touched:
                    touched.append(track["id"])
            elif start >= boundary:
                clip["startBar"] = start + delta
    for lane in project["snapshot"].get("automationLanes", []) or []:
        for point in lane.get("points", []) or []:
            if int(point.get("bar", 0)) >= boundary:
                point["bar"] = int(point["bar"]) + delta
    for note in project["snapshot"].get("notes", []) or []:
        if float(note.get("beat", 0)) >= boundary * 4:
            note["beat"] = float(note["beat"]) + delta * 4
    snapshot = project["snapshot"]
    if int(snapshot.get("loopEndBar", 0) or 0) >= boundary:
        snapshot["loopEndBar"] = int(snapshot["loopEndBar"]) + delta
    word = "Longer" if delta > 0 else "Shorter"
    detail = f"{section.label} {section.bars} -> {section.bars + delta} bars; clips after bar {boundary} moved by {delta:+d}"
    return [edit_record(f"{word} {section.label}", detail, touched, section)]


def apply_pitch(project: dict[str, Any], clause: Clause) -> list[dict[str, Any]]:
    track = track_by_id(project, clause.track_id or "")
    if track is None:
        return []
    notes = project["snapshot"].get("notes", []) or []
    owned = [n for n in notes if n.get("trackId") == track["id"]]
    if not owned and not any(n.get("trackId") for n in notes) and project["snapshot"].get("selectedTrackId") == track["id"]:
        # Older projects keep one un-tagged note list that belongs to the selected track.
        owned = list(notes)
    if not owned:
        return []
    semis = int(round(magnitude(clause, 5 if clause.steps == 1 else 12))) * clause.direction
    for note in owned:
        note["note"] = int(clamp(int(note.get("note", 60)) + semis, 0, 127))
    word = "Higher" if clause.direction > 0 else "Lower"
    return [edit_record(f"{word} {track['name']}", f"{track['id']} {len(owned)} notes transposed {semis:+d} semitones", [track["id"]], None)]


def apply_mute(project: dict[str, Any], clause: Clause) -> list[dict[str, Any]]:
    track = track_by_id(project, clause.track_id or "")
    if track is None:
        return []
    controls = ensure_controls(project, track)
    before = bool(controls.get("mute", False))
    after = clause.direction > 0
    controls["mute"] = after
    title = f"Mute {track['name']}" if after else f"Bring back {track['name']}"
    return [edit_record(title, f"{track['id']} mute {str(before).lower()} -> {str(after).lower()}", [track["id"]], None)]


def apply_add(project: dict[str, Any], clause: Clause) -> list[dict[str, Any]]:
    role = clause.add_role or "hats"
    if role in ADD_ROLES:
        base_id, new_id, new_name, steps = ADD_ROLES[role]
    else:
        # Any other blueprint role, placed by the model (validated against TRACK_BLUEPRINTS first).
        base_id = role
        new_id = clause.add_id or base_id
        new_name = clause.add_name or TRACK_BLUEPRINTS[base_id].name
        steps = list(TRACK_BLUEPRINTS[base_id].steps) if clause.add_steps is None else clause.add_steps
    sections = project_sections(project)
    section = clause.section or next((s for s in sections if s.type == "drop"), None)
    if section is not None:
        start, end = section.start_bar, section.end_bar
    else:
        start, end = song_extent(project)
        end = max(end, start + 8)
    blueprint = replace(TRACK_BLUEPRINTS[base_id], id=new_id, name=new_name, steps=steps)
    track = track_by_id(project, new_id)
    created = False
    if track is None:
        track = make_track(blueprint)
        project["snapshot"].setdefault("tracks", []).append(track)
        created = True
    ensure_controls(project, track)
    clip_id = f"{new_id}-{section.key if section else 'song'}"
    clips = track.setdefault("clips", [])
    if not any(c.get("id") == clip_id for c in clips):
        clips.append({
            "id": clip_id,
            "name": f"{section.label.capitalize() if section else 'Song'} {new_name.lower()}",
            "startBar": start,
            "bars": end - start,
            "lane": new_id,
            "color": track.get("color", "#cccccc"),
            "type": blueprint.clip_type,
        })
    where = section.label if section else "whole song"
    detail = f"{'new track' if created else 'existing track'} {new_id} ({blueprint.instrument}) with clip bars {start}-{end} in the {where}"
    return [edit_record(f"Add {new_name.lower()} in the {where}", detail, [new_id], section)]


def apply_energy(project: dict[str, Any], clause: Clause) -> list[dict[str, Any]]:
    """Rising filter automation plus a riser clip over the build."""
    sections = project_sections(project)
    section = clause.section or next((s for s in sections if s.type == "build"), None)
    if section is None:
        return []
    lane_track = track_by_id(project, "lead") or track_by_id(project, "chords") or next((t for t in tracks_of(project) if t.get("kind") != "automation"), None)
    if lane_track is None:
        return []
    lanes = project["snapshot"].setdefault("automationLanes", [])
    lane_id = f"auto-energy-{section.key}-{lane_track['id']}"
    lanes[:] = [lane for lane in lanes if lane.get("id") != lane_id]
    lanes.append({
        "id": lane_id,
        "trackId": lane_track["id"],
        "parameter": "filter",
        "label": f"{section.label.capitalize()} filter rise",
        "color": lane_track.get("color", "#7dd3fc"),
        "curve": "ease-in",
        "enabled": True,
        "points": [{"bar": section.start_bar, "value": 0.2}, {"bar": section.end_bar, "value": 0.9}],
    })
    fx = track_by_id(project, "fx")
    created = False
    if fx is None:
        fx = make_track(TRACK_BLUEPRINTS["fx"])
        project["snapshot"]["tracks"].append(fx)
        created = True
    ensure_controls(project, fx)
    clip_id = f"fx-riser-{section.key}"
    clips = fx.setdefault("clips", [])
    if not any(c.get("id") == clip_id for c in clips):
        clips.append({"id": clip_id, "name": f"{section.label.capitalize()} riser", "startBar": section.start_bar, "bars": section.bars, "lane": "fx", "color": fx.get("color", "#d78bff"), "type": "audio"})
    detail = f"filter automation on {lane_track['id']} 0.20 -> 0.90 over bars {section.start_bar}-{section.end_bar}; riser clip on fx{' (fx track added)' if created else ''}"
    return [edit_record(f"More energy in the {section.label}", detail, [lane_track["id"], "fx"], section)]


APPLIERS = {
    "gain": apply_gain,
    "tone": apply_tone,
    "hard": apply_hard,
    "bounce": apply_bounce,
    "width": apply_width,
    "space": apply_space,
    "tempo": apply_tempo,
    "length": apply_length,
    "pitch": apply_pitch,
    "mute": apply_mute,
    "add": apply_add,
    "energy": apply_energy,
}


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def split_clauses(request: str) -> list[str]:
    parts = [part.strip(" .!") for part in CLAUSE_SPLIT.split(request)]
    return [part for part in parts if part]


def tactic_suggestions(request: str) -> list[dict[str, Any]]:
    """Ask the DAW agent whether it knows a tactic for this wording. Suggest only, never apply."""
    try:
        ranked = daw_agent.retrieve_features(request, project=None, limit=3)
    except Exception:
        return []
    out = []
    for item in ranked:
        reasons = [r for r in item.get("reasons", []) if not r.startswith("default:") and not r.startswith("role:")]
        # Raw scores are token counts weighted by 4; scale to 0..1 so 0.35 means "at least
        # one real word of the request matched the tactic".
        score = round(min(1.0, float(item.get("score", 0.0)) / 10.0), 3)
        if reasons and score > 0.35:
            out.append({"id": item["id"], "title": item["title"], "score": score})
    return out


# ---------------------------------------------------------------------------
# The model. It reads the whole request with the project's tracks and sections and
# returns clauses in the grammar's own vocabulary. Everything it returns is checked
# against the project below; the grammar gets a go at whatever is dropped.
# ---------------------------------------------------------------------------

MAX_MODEL_CLAUSES = 24  # per request; anything beyond it is reported, never silently dropped
MAX_REQUEST_CHARS = 24000
MAX_WHY_CHARS = 200

# intent -> (unit the person may state, the applier's own unit, low, high). Values arrive in
# the stated unit and are stored in the applier's unit, clamped to the same ranges the
# appliers already work in.
AMOUNT_UNITS: dict[str, tuple[str, float, float]] = {
    "tempo": ("bpm", 1.0, 40.0),
    "length": ("bars", 1.0, 32.0),
    "pitch": ("semitones", 1.0, 24.0),
    "gain": ("gain", 0.01, 0.5),
    "bounce": ("percent", 1.0, 50.0),
    "tone": ("percent", 1.0, 60.0),
    "width": ("percent", 1.0, 60.0),
    "space": ("percent", 1.0, 60.0),
}

MODEL_ROLE = (
    "You turn a music producer's plain-words request into edits for a small DAW called Neon Studio. "
    "You only ever answer in the tool's own vocabulary, listed in the task. You never invent a track id, "
    "a section or an effect: you choose from the lists you are given. When a request could mean two "
    "different things you do not guess, you ask. Answer with JSON only."
)

INTENT_GUIDE = """\
gain (direction 1 louder / -1 quieter): a track's volume. Needs trackId, or a section / wholeSong to move every track playing there. amount unit "gain" (linear; one step is 0.08).
tone (1 brighter / -1 darker): the track's EQ. Needs trackId. amount unit "percent" (one step is 15).
hard (1 hit harder / -1 softer): the punch recipe for a section - drums/bass/sub/clap/hat gain, sidechain on, grit on the bass - or for one track. Use it for "harder", "punchier", "bigger", "heavier", "more impact", "slaps". Defaults to the first drop.
bounce (1 more / -1 less): song-wide swing. amount unit "percent" (one step is 8 swing points).
width (1 wider / -1 narrower): the track's stereo width. Needs trackId. amount unit "percent" (one step is 10).
space (1 more / -1 less): the track's reverb, or its delay when effect is "delay" ("both" for both). Needs trackId. amount unit "percent" (one step is 15).
tempo (1 faster / -1 slower): the song's bpm. amount unit "bpm" (steps 1/2/3 are 4/8/10 bpm).
length (1 longer / -1 shorter): a section, 4 bars unless amount says otherwise; everything after it slides. Defaults to the outro. amount unit "bars".
pitch (1 higher / -1 lower): transpose the track's notes. Needs trackId. steps 1 is 5 semitones, otherwise an octave; amount unit "semitones".
mute (1 mute / -1 bring back): a track. Needs trackId.
add (direction 1): a new track from a blueprint (addRole) with a clip over the section, the first drop when none is named. Optional newId (lowercase, hyphens), name, and addSteps (sixteenth positions 0-15 within a bar that the pattern hits).
energy (direction 1): rising filter automation plus a riser clip over the section, the first build when none is named."""

PLAN_SCHEMA = {
    "clauses": [{
        "text": "the words of the request this clause comes from",
        "intent": "gain",
        "direction": 1,
        "steps": 2,
        "amount": {"unit": "bpm", "value": 8},
        "trackId": "lead",
        "section": {"type": "drop", "ordinal": 1},
        "wholeSong": False,
        "addRole": None,
        "newId": None,
        "name": None,
        "addSteps": None,
        "effect": None,
        "why": "one short sentence: why this edit serves the request",
    }],
    "unresolved": [{
        "text": "the words you could not place",
        "reason": "what was unclear",
        "question": "one clarifying question",
        "suggestions": ["up to three rephrasings that would work in this project"],
    }],
}

EXPLAIN_SCHEMA = {
    "why": [{"index": 0, "why": "one short sentence on why this edit serves the request"}],
    "next": "the single most useful thing to try after this, phrased as a request this tool understands",
}


def track_context(project: dict[str, Any]) -> list[dict[str, Any]]:
    """Tracks as {id, name, kind, roles, effects} - what the model may choose from."""
    out = []
    for track in tracks_of(project):
        effects = [{"name": str(e.get("name", "")), "amount": e.get("amount"), "active": bool(e.get("active", False))}
                   for e in track.get("effects", []) or [] if isinstance(e, dict)]
        out.append({
            "id": str(track.get("id", "")),
            "name": str(track.get("name", "")),
            "kind": str(track.get("kind", "audio")),
            "roles": sorted(track_roles(track)),
            "effects": effects,
        })
    return out


def section_context(sections: list[Section]) -> list[dict[str, Any]]:
    return [{"type": s.type, "ordinal": s.ordinal, "startBar": s.start_bar, "endBar": s.end_bar, "label": s.label} for s in sections]


def add_role_context() -> list[dict[str, str]]:
    roles = [{"addRole": key, "name": TRACK_BLUEPRINTS[key].name, "instrument": TRACK_BLUEPRINTS[key].instrument}
             for key in TRACK_BLUEPRINTS if TRACK_BLUEPRINTS[key].kind != "automation"]
    for short in ("hats", "riser", "sub", "clap", "pad"):
        base, _, name, _ = ADD_ROLES[short]
        if short not in TRACK_BLUEPRINTS:
            roles.append({"addRole": short, "name": name, "instrument": TRACK_BLUEPRINTS[base].instrument})
    return roles


def chunk_request(request: str, limit: int = MAX_REQUEST_CHARS) -> list[str]:
    """A request longer than one call's worth of text is sent in clause-aligned chunks."""
    text = request.strip()
    if len(text) <= limit:
        return [text] if text else []
    chunks: list[str] = []
    current = ""
    for part in split_clauses(text) or [text]:
        piece = part[:limit]
        if current and len(current) + len(piece) + 2 > limit:
            chunks.append(current)
            current = piece
        else:
            current = f"{current}, {piece}" if current else piece
    if current:
        chunks.append(current)
    return chunks


def plan_prompt(project: dict[str, Any], sections: list[Section], request: str) -> str:
    snapshot = project.get("snapshot", {})
    return "\n".join([
        f"Request: {json.dumps(request)}",
        "",
        f"Song: bpm {int(snapshot.get('bpm', 120) or 120)}, swing {int(snapshot.get('swing', 0) or 0)}, key {project.get('keyCenter') or 'unknown'}.",
        f"Tracks (choose trackId from these ids only): {json.dumps(track_context(project))}",
        f"Sections (choose section from these only): {json.dumps(section_context(sections))}",
        f"Blueprints for addRole: {json.dumps(add_role_context())}",
        "",
        "Intents:",
        INTENT_GUIDE,
        "",
        "Rules:",
        "- Return every part of the request as clauses, in order. A clause has exactly one intent; text is the words it came from.",
        "- Carry referents across clauses: 'make the lead louder and give it more space' is two clauses on the lead.",
        "- 'the drums and bass' is one ask about two tracks: one clause per track.",
        "- For an ask with no intent of its own ('the drop feels empty', 'less muddy', 'more groove in the verse'), plan one to four primitive clauses that would get there in this project and give each a why. Prefer the recipe intents (hard, energy) when they fit.",
        "- steps: 1 for 'a bit', 3 for 'a lot' or 'way', 2 otherwise. Give amount only when the request states a quantity ('10 bpm', '8 bars', 'an octave' is 12 semitones; 'make it 130 bpm' is the difference from the current bpm). Otherwise amount is null.",
        "- trackId must be one of the listed ids, section one of the listed sections (type and ordinal). Never invent either. If two tracks fit equally, do not guess: put it in unresolved with a question naming both.",
        "- Anything you cannot place goes in unresolved with a reason, one clarifying question, and up to three rephrasings that would work in this project (use the track names and sections that exist). 'Sound like X' with no X in the project is unresolved.",
        f"- At most {MAX_MODEL_CLAUSES} clauses.",
    ])


def resolve_track_id(project: dict[str, Any], value: Any) -> Optional[str]:
    """A model-given track: exact id, else an exact (case-insensitive) name. Nothing fuzzier."""
    if value is None:
        return None
    wanted = str(value).strip()
    if not wanted:
        return None
    for track in tracks_of(project):
        if str(track.get("id", "")) == wanted:
            return str(track["id"])
    lowered = wanted.lower()
    for track in tracks_of(project):
        if str(track.get("name", "")).lower() == lowered or str(track.get("id", "")).lower() == lowered:
            return str(track["id"])
    return None


def resolve_section(value: Any, sections: list[Section], project: dict[str, Any]) -> tuple[Optional[Section], Optional[str]]:
    """A model-given section: {type, ordinal} that exists, a label that exists, or a bar range inside the song."""
    if value is None or value == "" or value is False:
        return None, None
    if isinstance(value, str):
        lowered = value.strip().lower()
        for section in sections:
            if section.label == lowered or section.key == lowered:
                return section, None
        parsed = classify_section_name(lowered)
        if parsed is None:
            return None, f"this project has no {value!r} section"
        value = {"type": parsed[0], "ordinal": parsed[1]}
    if not isinstance(value, dict):
        return None, "section must be an object"
    if value.get("type"):
        kind = str(value["type"]).strip().lower().replace("-", "_").replace(" ", "_")
        kind = SECTION_WORDS.get(kind, kind)
        try:
            ordinal = int(value.get("ordinal") or 1)
        except (TypeError, ValueError):
            ordinal = 1
        for section in sections:
            if section.type == kind and section.ordinal == ordinal:
                return section, None
        return None, f"this project has no {Section(kind, ordinal, 0, 0).label} section"
    if "startBar" in value and "endBar" in value:
        try:
            start, end = int(value["startBar"]), int(value["endBar"])
        except (TypeError, ValueError):
            return None, "section bars must be integers"
        _, song_end = song_extent(project)
        if start < 0 or end <= start or start >= max(song_end, 1):
            return None, f"bars {start}-{end} are outside the song"
        end = min(end, max(song_end, start + 1))
        return Section("bars", 1, start, end, name=f"bars {start}-{end}"), None
    return None, "section needs a type or a bar range"


def sanitise_id(value: Any) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", str(value or "").strip().lower()).strip("-")


def clause_from_model(item: Any, project: dict[str, Any], sections: list[Section], dropped: list[str]) -> tuple[Optional[Clause], Optional[str]]:
    """Check one model clause against the project. Returns (clause, problem); a problem means the
    clause is dropped (the grammar then gets a go at its text). Ignored fields are noted in `dropped`."""
    if not isinstance(item, dict):
        return None, "clause was not an object"
    text = str(item.get("text") or "").strip()
    intent = str(item.get("intent") or "").strip().lower()
    if intent not in APPLIERS:
        return None, f"unknown intent {intent!r}"
    clause = Clause(text=text or intent, intent=intent, source="model")
    clause.why = str(item.get("why") or "").strip()[:MAX_WHY_CHARS]

    direction: Any = 1 if intent in ("add", "energy") else item.get("direction")
    try:
        direction = int(direction)
    except (TypeError, ValueError):
        direction = 0
    if direction not in (-1, 1):
        return None, "direction must be 1 or -1"
    clause.direction = direction

    try:
        steps = int(item.get("steps") if item.get("steps") is not None else 2)
    except (TypeError, ValueError):
        steps = 2
    clause.steps = int(clamp(steps, 1, 3))

    amount = item.get("amount")
    if isinstance(amount, dict) and amount.get("value") is not None:
        unit = str(amount.get("unit") or "").strip().lower()
        spec = AMOUNT_UNITS.get(intent)
        try:
            value = abs(float(amount["value"]))
        except (TypeError, ValueError):
            value = None
        if spec is None or unit != spec[0] or value is None or value == 0:
            dropped.append(f"ignored amount {amount!r} for {intent}")
        else:
            value = clamp(value, spec[1], spec[2])
            clause.amount_label = f"{value:g} {unit}" if unit != "percent" else f"{value:g}%"
            if unit == "percent" and intent in ("tone", "width", "space"):
                clause.amount_value = value / 100.0
            elif unit in ("bars", "semitones", "bpm"):
                clause.amount_value = float(int(round(value)))
            else:
                clause.amount_value = value
    elif amount not in (None, "", {}):
        dropped.append(f"ignored amount {amount!r} for {intent}")

    clause.whole_song = bool(item.get("wholeSong"))

    wanted_track = item.get("trackId")
    if wanted_track not in (None, ""):
        clause.track_id = resolve_track_id(project, wanted_track)
        if clause.track_id is None:
            return None, f"no track {str(wanted_track)!r} in this project"

    section, problem = resolve_section(item.get("section"), sections, project)
    if problem is not None:
        return None, problem
    clause.section = section

    effect = item.get("effect")
    if effect in ("reverb", "delay", "both"):
        clause.effect = effect
    elif effect not in (None, ""):
        dropped.append(f"ignored effect {effect!r}")

    if intent == "add":
        role = str(item.get("addRole") or "").strip().lower()
        if role in ADD_ROLES:
            clause.add_role = role
        elif role in TRACK_BLUEPRINTS and TRACK_BLUEPRINTS[role].kind != "automation":
            clause.add_role = role
            clause.add_id = sanitise_id(item.get("newId")) or role
            name = str(item.get("name") or "").strip()
            clause.add_name = name[:40] if name else None
            steps16 = item.get("addSteps")
            if isinstance(steps16, list):
                cleaned = sorted({int(s) for s in steps16 if isinstance(s, (int, float)) and 0 <= int(s) <= 15})
                clause.add_steps = cleaned
            elif steps16 not in (None, ""):
                dropped.append(f"ignored addSteps {steps16!r}")
        else:
            return None, f"add what? {role!r} is not a blueprint role"
        return clause, None

    needs_track = {"tone", "width", "space", "pitch", "mute", "gain"}
    if intent in needs_track and clause.track_id is None:
        if intent == "gain" and (clause.section is not None or clause.whole_song):
            return clause, None
        return None, "which track? (e.g. the lead, bass, drums, vocals, chords, hats)"
    return clause, None


def plan_with_model(assist: Assist, project: dict[str, Any], request: str) -> Optional[dict[str, Any]]:
    """One call per chunk of the request. Returns {"clauses": [...], "unresolved": [...]} with the
    model's raw items (validation happens per clause, against the sections as they stand then), or
    None when the model is off, unreachable or answered the wrong shape."""
    if not assist.available:
        return None
    sections = project_sections(project)
    clauses: list[Any] = []
    unresolved: list[Any] = []
    answered = False
    for chunk in chunk_request(request):
        answer = assist.ask(plan_prompt(project, sections, chunk), system=MODEL_ROLE, schema=PLAN_SCHEMA, expect=dict)
        if answer is None:
            return None
        got_clauses = answer.get("clauses")
        got_unresolved = answer.get("unresolved")
        if not isinstance(got_clauses, list) and not isinstance(got_unresolved, list):
            assist.note = "model answer had neither clauses nor unresolved"
            return None
        answered = True
        clauses.extend(got_clauses if isinstance(got_clauses, list) else [])
        unresolved.extend(got_unresolved if isinstance(got_unresolved, list) else [])
    if not answered:
        return None
    # The cap is a guard against a runaway answer, not a quiet filter: whatever falls beyond it
    # is handed back by text so the caller can list it as not applied.
    beyond_cap = [str(item.get("text") or "").strip() if isinstance(item, dict) else "" for item in clauses[MAX_MODEL_CLAUSES:]]
    return {
        "clauses": clauses[:MAX_MODEL_CLAUSES],
        "unresolved": unresolved[:MAX_MODEL_CLAUSES],
        "beyondCap": beyond_cap,
        "unresolvedBeyondCap": max(0, len(unresolved) - MAX_MODEL_CLAUSES),
    }


def explain_with_model(assist: Assist, project: dict[str, Any], request: str, report: dict[str, Any]) -> bool:
    """After the edits are computed, one call writes the why per edit and one next suggestion.
    It annotates only: nothing about the edits or the project changes here. Returns True when
    the model answered (so the why text is the model's), False when the caller's text stands."""
    if not assist.available or not report["edits"]:
        return False
    summary = [{"index": i, "title": e["title"], "detail": e["detail"], "section": e.get("section"), "trackIds": e.get("trackIds", [])}
               for i, e in enumerate(report["edits"])]
    tracks = [{"id": t["id"], "name": t["name"], "roles": t["roles"]} for t in track_context(project)]
    prompt = "\n".join([
        f"Request: {json.dumps(request[:MAX_REQUEST_CHARS])}",
        f"Understood as: {json.dumps(report['understood'])}",
        f"Edits already applied (do not change or add any): {json.dumps(summary)}",
        f"Tracks: {json.dumps(tracks)}",
        "",
        "For each edit index write one short plain sentence saying why it serves the request. Do not quote numbers beyond those in the detail and do not promise how it will sound.",
        "Then write 'next': the single most useful thing to try after this, as a request in this tool's vocabulary (louder/quieter, brighter/darker, hit harder/softer, more/less bounce, wider/narrower, more/less space, faster/slower, longer/shorter, higher/lower, mute/bring back, add <role>, more energy), naming a track or section that exists.",
    ])
    answer = assist.ask(prompt, system=MODEL_ROLE, schema=EXPLAIN_SCHEMA, expect=dict)
    if answer is None:
        return False
    whys = answer.get("why")
    if isinstance(whys, list):
        for entry in whys:
            if not isinstance(entry, dict):
                continue
            try:
                index = int(entry.get("index"))
            except (TypeError, ValueError):
                continue
            why = str(entry.get("why") or "").strip()
            if 0 <= index < len(report["edits"]) and why:
                report["edits"][index]["why"] = why[:MAX_WHY_CHARS]
    nxt = answer.get("next")
    if isinstance(nxt, str) and nxt.strip():
        report["next"] = nxt.strip()[:MAX_WHY_CHARS]
    return True


def ai_block(assist: Assist, planned: str, explained: str, dropped: list[str], notes: list[str]) -> dict[str, Any]:
    """The `ai` block for the report (docs/ai.md rule 5), unambiguous about what the model did:
    used is True only when the model's answer shaped the result; planned says who read the
    request ("model" or "grammar"); explained says who wrote the why text ("model" or "template")."""
    base = assist.report()
    return {
        "used": planned == "model",
        "planned": planned,
        "explained": explained,
        "provider": base["provider"],
        "model": base["model"],
        "note": "; ".join(n for n in notes if n),
        "dropped": dropped,
    }


NO_EDIT_REASONS = {
    "pitch": "no notes on that track to transpose",
    "hard": "nothing in that section to push",
    "energy": "this project has no build section",
    "space": "no reverb or delay on that track to reduce",
    "length": "no section to change",
}


def describe_change(project: dict[str, Any], request: str, assist: Optional[Assist] = None, explain: bool = True) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply `request` to a deep copy of `project`. Returns (report, updated_project).

    With a model available (see docs/ai.md) the request is read by the model first and every
    clause it returns is validated here; the grammar runs on anything it drops and on the whole
    request when the model is off or fails. The appliers are the same either way."""
    if assist is None:
        assist = Assist()
    updated = deepcopy(project)
    updated.setdefault("snapshot", {})
    report: dict[str, Any] = {"ok": True, "understood": "", "edits": [], "unresolved": [], "suggestions": [], "tactics": [], "questions": [], "next": ""}
    understood: list[str] = []
    dropped: list[str] = []
    model_suggestions: list[str] = []

    def apply(clause: Clause) -> None:
        edits = APPLIERS[clause.intent or ""](updated, clause)
        if not edits:
            report["unresolved"].append(f"{clause.text} ({NO_EDIT_REASONS.get(clause.intent or '', 'nothing to change')})")
            return
        for edit in edits:
            edit["source"] = clause.source
            edit["why"] = clause.why
        understood.append(restate(clause, updated))
        report["edits"].extend(edits)

    def apply_by_grammar(text: str) -> Optional[str]:
        """The grammar's go at one clause. Returns the problem when it could not place it."""
        sections = project_sections(updated)  # recomputed: an earlier clause may have moved bars
        clause, problem = parse_clause(text, updated, sections)
        if problem is not None:
            return problem
        apply(clause)
        return None

    plan = plan_with_model(assist, updated, request)
    planned = "grammar" if plan is None else "model"
    notes: list[str] = []
    if plan is None:
        # The model is off, unreachable, or answered the wrong shape: the grammar reads the
        # whole request and the model is not asked for the why text either, so nothing in the
        # result comes from it.
        notes.append(assist.note or "the model gave no plan")
        for text in split_clauses(request):
            problem = apply_by_grammar(text)
            if problem is not None:
                report["unresolved"].append(f"{text} ({problem})")
    else:
        for item in plan["clauses"]:
            sections = project_sections(updated)
            clause, problem = clause_from_model(item, updated, sections, dropped)
            if clause is not None:
                apply(clause)
                continue
            text = str(item.get("text") or "").strip() if isinstance(item, dict) else ""
            dropped.append(f"dropped model clause {text!r}: {problem}")
            if text and apply_by_grammar(text) is None:
                continue
            report["unresolved"].append(f"{text or request.strip()} ({problem})")
        for entry in plan["unresolved"]:
            if not isinstance(entry, dict):
                continue
            text = str(entry.get("text") or "").strip() or request.strip()
            reason = str(entry.get("reason") or "not understood").strip()
            question = str(entry.get("question") or "").strip()
            # When the model asked a question it saw an ambiguity; the grammar must not guess over
            # it. When it simply could not place the words, the grammar gets a go.
            if not question and apply_by_grammar(text) is None:
                continue
            report["unresolved"].append(f"{text} ({reason})")
            if question:
                report["questions"].append(question[:MAX_WHY_CHARS])
            for suggestion in entry.get("suggestions") or []:
                if isinstance(suggestion, str) and suggestion.strip() and suggestion.strip() not in model_suggestions:
                    model_suggestions.append(suggestion.strip()[:MAX_WHY_CHARS])
        beyond_cap = plan.get("beyondCap") or []
        if beyond_cap:
            shown = ", ".join(repr(t) for t in beyond_cap[:5] if t) + (", …" if len(beyond_cap) > 5 else "")
            message = f"{len(beyond_cap)} more clause(s) the model planned were not applied (at most {MAX_MODEL_CLAUSES} per request; ask for them separately)"
            report["unresolved"].append(f"{message}{': ' + shown if shown else ''}")
            notes.append(message)
        if plan.get("unresolvedBeyondCap"):
            message = f"{plan['unresolvedBeyondCap']} more item(s) the model could not place were not listed (at most {MAX_MODEL_CLAUSES} per request)"
            report["unresolved"].append(message)
            notes.append(message)
        if dropped:
            notes.append(f"{len(dropped)} model clause(s) failed validation and went to the grammar (see dropped)")

    report["understood"] = "; ".join(understood)
    if report["unresolved"]:
        report["suggestions"] = model_suggestions[:6] or SUGGESTIONS[:6]
        report["tactics"] = tactic_suggestions(request)
    explained = "template"
    if explain and plan is not None:
        # Only a plan the model made gets the model's why text; a grammar plan keeps its own words.
        if explain_with_model(assist, updated, request, report):
            explained = "model"
            notes.append("the model read the request and wrote the why text")
        elif not report["edits"]:
            notes.append("the model read the request; nothing to explain")
        else:
            notes.append(f"the model read the request; the why text is the planner's ({assist.note or 'the explain call gave nothing'})")
    elif plan is not None:
        notes.append("the model read the request")
    report["ai"] = ai_block(assist, planned, explained, dropped, notes)
    return report, updated


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Describe change", ""]
    if not report.get("ok", False):
        lines.append(f"Error: {report.get('error')}")
        return "\n".join(lines) + "\n"
    lines.append(f"Understood: {report.get('understood') or '(nothing)'}")
    lines.append("")
    lines.append("## Edits")
    if report["edits"]:
        for edit in report["edits"]:
            where = f" [{edit['section']}]" if edit.get("section") else ""
            why = f" — {edit['why']}" if edit.get("why") else ""
            lines.append(f"- {edit['title']}{where}: {edit['detail']}{why}")
    else:
        lines.append("- none")
    if report["unresolved"]:
        lines.append("")
        lines.append("## Not understood")
        for item in report["unresolved"]:
            lines.append(f"- {item}")
        for question in report.get("questions") or []:
            lines.append(f"- Question: {question}")
        lines.append("")
        lines.append("## Try saying")
        for item in report["suggestions"]:
            lines.append(f"- {item}")
    if report.get("tactics"):
        lines.append("")
        lines.append("## Tactics the DAW agent could apply (not applied)")
        for tactic in report["tactics"]:
            lines.append(f"- {tactic['id']}: {tactic['title']} (score {tactic['score']})")
    if report.get("next"):
        lines.append("")
        lines.append(f"Next: {report['next']}")
    ai = report.get("ai") or {}
    lines.append("")
    lines.append(f"AI: {'via ' + str(ai.get('provider')) + ' ' + str(ai.get('model')) if ai.get('used') else 'offline rules'}" + (f" ({ai['note']})" if ai.get("note") else ""))
    lines.append(f"Project: {report.get('project')}")
    return "\n".join(lines) + "\n"


def emit(report: dict[str, Any], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(report, sort_keys=True))
    else:
        print(render_markdown(report), end="")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Turn a plain-words request into concrete Neon Studio project edits.")
    parser.add_argument("--root", default=".", help="Repository root; relative --project/--output paths resolve against it.")
    parser.add_argument("--project", required=True, help="Path to the input .neon.json (never modified).")
    parser.add_argument("--request", required=True, help="What should change, in your own words.")
    parser.add_argument("--output", required=True, help="Where to write the edited .neon.json.")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    add_ai_argument(parser)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    project_path = Path(args.project).expanduser()
    if not project_path.is_absolute():
        project_path = root / project_path
    output_path = Path(args.output).expanduser()
    if not output_path.is_absolute():
        output_path = root / output_path

    try:
        with open(project_path, "r", encoding="utf-8") as handle:
            project = json.load(handle)
        if not isinstance(project, dict) or not isinstance(project.get("snapshot"), dict):
            raise ValueError(f"{project_path} is not a .neon.json project (no snapshot)")
        report, updated = describe_change(project, args.request, assist=assist_from_args(args))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(updated, handle, indent=2, sort_keys=True)
            handle.write("\n")
        report["project"] = str(output_path)
        emit(report, args.format)
        return 0
    except Exception as exc:
        emit({"ok": False, "error": str(exc)}, args.format)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
