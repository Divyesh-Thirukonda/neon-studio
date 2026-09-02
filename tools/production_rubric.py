#!/usr/bin/env python3
"""The shared vocabulary between filling gaps and judging results.

Neon Studio has two tools that both hold opinions about what makes a song work:

* ``fill_in_blanks.py`` runs BEFORE anything is built. It sees a description and
  has to decide what the person left out.
* ``does_this_sound_good.py`` runs AFTER audio exists. It measures the result and
  says what to fix.

Until now those opinions lived in two places and never met, so the filler would
happily build a project the checker was guaranteed to complain about, and the
only way to find out was to render it. This module is the thing they share: one
list of production requirements, each written so it can be tested *before* the
song exists — against the transcript spec — and each naming the sound-check
dimension it pre-empts.

The point is not to enforce a house style. It is to notice the steps a brief
never mentions. Somebody writes "big future bass drop with a catchy lead" and
says nothing about sidechain, transition FX, or who owns the low end. Every one
of those omissions is predictable, and every one of them is fixable before a
single sample is rendered.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable


# The style lanes fill_in_blanks.py recognises. "all" means every lane.
STYLE_LANES = ("dark_bass", "bright_future_bass", "house_pop", "modern_edm")

# The dimensions does_this_sound_good.py reports against. Keeping the strings
# here means a requirement can name the finding it prevents, and a real report
# can be mapped back onto the requirements that would have avoided it.
SOUND_CHECK_AREAS = (
    "Clipping",
    "Headroom",
    "Level",
    "Density",
    "Punch",
    "Consistency",
    "Low end",
    "Low mids",
    "Top end",
    "Stereo",
    "Mono",
    "Missing audio",
    "Arrangement",
    "Recipe",
    "Length",
)

# Sections that carry the payoff, and the ones that set it up. Used by several
# requirements, so they are named once.
PAYOFF_SECTIONS = ("drop", "second_drop", "chorus")
SETUP_SECTIONS = ("build", "pre_build", "verse")


def _words(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(_words(v) for v in value.values())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_words(v) for v in value)
    return str(value)


def quote_in(text: str, quote: Any) -> bool:
    """True when ``quote`` appears verbatim in ``text`` (case and spacing aside).

    This is the rule that keeps a model honest: it may only claim the author
    said something if it can show the words, and the words have to be there.
    """
    if not isinstance(quote, str):
        return False
    needle = re.sub(r"\s+", " ", quote).strip().strip("\"'\u201c\u201d\u2018\u2019").lower()
    if len(needle) < 4:
        return False
    return needle in re.sub(r"\s+", " ", text).lower()


UNIT_WORDS = (
    "hz", "khz", "hertz", "kilohertz", "db", "dbfs", "lufs", "decibel", "ms", "millisecond", "second",
    "bpm", "bar", "bars", "beat", "beats", "%", "percent", "st", "semitone", "octave",
)

TECHNIQUE_WORDS = (
    "sidechain", "duck", "pump", "high-pass", "highpass", "hpf", "low-cut", "lowcut", "low cut", "high pass",
    "crossover", "mono", "stereo", "wide", "width", "narrow", "centre", "center", "reverb", "delay", "decay",
    "tail", "pre-delay", "predelay", "send", "return", "compress", "limiter", "headroom", "ceiling", "gain",
    "level", "filter", "eq", "band", "split", "phrase", "depth", "release", "attack", "root", "fundamental",
)


def values_evidence(quote: Any) -> bool:
    """True when ``quote`` is substantial enough to show the author set a value.

    ``quote_in`` proves the words exist; this proves they say something. A
    requirement that asks for values (``Requirement.needs_values``) is not
    covered by a four-letter quote like "kick" or "drop" that merely names a
    part: the quote has to be at least three words or fifteen characters and
    carry a digit, a unit or a technique word.
    """
    if not isinstance(quote, str):
        return False
    needle = re.sub(r"\s+", " ", quote).strip().strip("\"'\u201c\u201d\u2018\u2019").lower()
    if len(needle.split()) < 3 and len(needle) < 15:
        return False
    if re.search(r"\d", needle):
        return True
    tokens = set(re.findall(r"[a-z%]+(?:-[a-z]+)?", needle))
    if tokens & set(UNIT_WORDS):
        return True
    return any(word in needle for word in TECHNIQUE_WORDS)


def chunk_text(text: str, size: int = 24000) -> list[str]:
    """Split long prose at sentence or word boundaries into pieces of at most ``size``."""
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    while len(text) > size:
        cut = text.rfind(". ", 0, size)
        if cut < size // 2:
            cut = text.rfind(" ", 0, size)
        if cut <= 0:
            cut = size - 1
        chunks.append(text[: cut + 1].strip())
        text = text[cut + 1:].strip()
    if text:
        chunks.append(text)
    return chunks


class SpecView:
    """Cheap, forgiving read access to a transcript spec.

    Specs come from transcript parsing, so almost every field is optional and
    shapes vary. Every accessor here tolerates missing or oddly-typed data and
    returns something safe, because a requirement check must never be the thing
    that crashes a build.
    """

    def __init__(
        self,
        spec: dict[str, Any],
        prompt: str | None = None,
        intent: dict[str, Any] | None = None,
    ) -> None:
        """
        Two specs, deliberately.

        ``spec`` is the arrangement as it will actually be built, after the
        earlier passes have added sections, roles and lane defaults. Structural
        questions — are there any energy boundaries? is there a lead? — must be
        asked of that, or a one-line brief looks like it has nothing to check and
        every requirement passes vacuously.

        ``intent`` is what the author actually wrote. Coverage questions — did
        they ask for this? — must be asked of *that*, because the earlier passes
        inject "sidechain" and "reverb" into every drop, so asking the enriched
        spec whether sidechain was covered always answers yes.

        Getting these the wrong way round produces a filler that either suggests
        nothing or overrides everything.
        """
        self.spec = spec if isinstance(spec, dict) else {}
        self.intent = intent if isinstance(intent, dict) else self.spec
        self.prompt = prompt or ""

    # -- sections ---------------------------------------------------------

    @property
    def sections(self) -> list[dict[str, Any]]:
        raw = self.spec.get("sections")
        return [s for s in raw if isinstance(s, dict)] if isinstance(raw, list) else []

    @property
    def section_types(self) -> list[str]:
        return [str(s.get("type") or "").lower() for s in self.sections]

    def sections_of(self, *types: str) -> list[dict[str, Any]]:
        wanted = {t.lower() for t in types}
        return [s for s in self.sections if str(s.get("type") or "").lower() in wanted]

    @property
    def payoff_sections(self) -> list[dict[str, Any]]:
        return self.sections_of(*PAYOFF_SECTIONS)

    def has_section(self, *types: str) -> bool:
        return bool(self.sections_of(*types))

    # -- roles, techniques, plugins --------------------------------------

    def section_roles(self, section: dict[str, Any]) -> set[str]:
        raw = section.get("trackRoles")
        return {str(r).lower() for r in raw} if isinstance(raw, list) else set()

    def section_techniques(self, section: dict[str, Any]) -> set[str]:
        raw = section.get("techniques")
        return {str(t).lower() for t in raw} if isinstance(raw, list) else set()

    @property
    def roles(self) -> set[str]:
        found: set[str] = set()
        for section in self.sections:
            found |= self.section_roles(section)
        for item in self.spec.get("globalTracks") or []:
            if isinstance(item, dict) and item.get("name"):
                found.add(str(item["name"]).lower())
        return found

    @property
    def techniques(self) -> set[str]:
        found: set[str] = set()
        for section in self.sections:
            found |= self.section_techniques(section)
        for item in self.spec.get("globalTechniques") or []:
            if isinstance(item, dict) and item.get("name"):
                found.add(str(item["name"]).lower())
            elif isinstance(item, str):
                found.add(item.lower())
        return found

    # -- free text --------------------------------------------------------

    def _prose_parts(self) -> list[str]:
        source = self.intent
        parts = [
            self.prompt,
            _words(source.get("sourcePrompt")),
            _words(source.get("arrangementNotes")),
            _words(source.get("mixNotes")),
            _words(source.get("automationNotes")),
        ]
        # Deliberately NOT coverageChecklist or derivedPrompt: the filler writes
        # those itself, so including them would let a previous run's output count
        # as the author having asked for something.
        raw_sections = source.get("sections")
        if isinstance(raw_sections, list):
            for section in raw_sections:
                if not isinstance(section, dict):
                    continue
                parts.append(_words(section.get("summary")))
                parts.append(_words(section.get("excerpt")))
                parts.append(_words(section.get("transcriptText")))
        return parts

    @property
    def notes(self) -> str:
        """Everything the author wrote as prose, lowercased.

        Requirements check this as well as the structured fields, because a
        walkthrough often states something in a sentence that the parser never
        turned into a role or a technique.
        """
        return re.sub(r"\s+", " ", " ".join(self._prose_parts())).strip().lower()

    @property
    def notes_raw(self) -> str:
        """The same prose with its original casing, for a model to quote from."""
        return re.sub(r"\s+", " ", " ".join(self._prose_parts())).strip()

    def without_prose(self) -> "SpecView":
        """The same spec with everything the author wrote blanked out.

        Asking a requirement against this answers "is it satisfied by structure
        alone?" - by the sections, roles and lane events - as opposed to by a
        keyword the author happened to use. A model may argue with the keyword;
        it may not argue with the structure.
        """
        intent = dict(self.intent)
        for key in ("sourcePrompt", "arrangementNotes", "mixNotes", "automationNotes"):
            intent[key] = ""
        sections = intent.get("sections")
        if isinstance(sections, list):
            intent["sections"] = [
                {**s, "summary": "", "excerpt": "", "transcriptText": ""} if isinstance(s, dict) else s
                for s in sections
            ]
        return SpecView(self.spec, prompt=None, intent=intent)

    def mentions(self, *needles: str) -> bool:
        """True when the author said any of these words anywhere."""
        blob = self.notes
        return any(n.lower() in blob for n in needles)

    def has_technique(self, *needles: str) -> bool:
        pool = " ".join(self.techniques)
        return any(n.lower() in pool for n in needles) or self.mentions(*needles)

    def has_role(self, *needles: str) -> bool:
        pool = " ".join(self.roles)
        return any(n.lower() in pool for n in needles)

    # -- lane data --------------------------------------------------------

    def lane_events(self, section: dict[str, Any]) -> dict[str, Any]:
        raw = section.get("laneEvents")
        return raw if isinstance(raw, dict) else {}

    def has_lane_events(self, section: dict[str, Any], *lanes: str) -> bool:
        events = {k.lower() for k in self.lane_events(section)}
        return any(any(l.lower() in k for k in events) for l in lanes)

    @property
    def total_lane_events(self) -> int:
        return sum(len(self.lane_events(s)) for s in self.sections)

    def lane_keys(self, section: dict[str, Any]) -> set[str]:
        return {str(k).lower() for k in self.lane_events(section)}

    def has_bar_scoped_events(self, section: dict[str, Any], *lanes: str) -> bool:
        """True when some lane varies bar to bar rather than repeating one pattern.

        This is the difference between a part and a loop. The materializer reuses
        an unscoped event list for every bar, so without a ``barOffset``
        somewhere the eighth bar is identical to the first.
        """
        wanted = {l.lower() for l in lanes}
        for name, payload in self.lane_events(section).items():
            if wanted and name.lower() not in wanted:
                continue
            events = payload.get("events") if isinstance(payload, dict) else None
            if isinstance(events, list) and any(
                isinstance(e, dict) and "barOffset" in e for e in events
            ):
                return True
        return False

    def has_transforms(self, section: dict[str, Any]) -> bool:
        raw = section.get("laneTransforms")
        return isinstance(raw, dict) and bool(raw)

    # -- prose with numbers ----------------------------------------------

    def notes_match(self, pattern: str) -> bool:
        """Regex over what the author wrote.

        Used where a requirement is only really satisfied by a *number* — a
        crossover frequency, a decay time, a dB target. Naming the technique
        without a value is the thing this rubric exists to catch.
        """
        try:
            return re.search(pattern, self.notes, re.IGNORECASE) is not None
        except re.error:
            return False

    # -- arrangement shape ------------------------------------------------

    ENERGY_RANK = {
        "pre_intro": 1, "intro": 1, "outro": 1,
        "verse": 2, "break": 2,
        "pre_build": 3, "build": 3,
        "drop": 4, "second_drop": 4, "chorus": 4,
    }

    @property
    def musical_sections(self) -> list[dict[str, Any]]:
        """Sections that occupy time, ignoring parsed production asides."""
        return [
            s for s in self.sections
            if str(s.get("type") or "").lower() in self.ENERGY_RANK
        ]

    def adjacent_pairs(self) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        ordered = self.musical_sections
        return list(zip(ordered, ordered[1:]))

    def rising_pairs(self) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        """Boundaries where energy goes up — where a transition has to happen."""
        out = []
        for outgoing, incoming in self.adjacent_pairs():
            a = self.ENERGY_RANK.get(str(outgoing.get("type") or "").lower(), 0)
            b = self.ENERGY_RANK.get(str(incoming.get("type") or "").lower(), 0)
            if b > a:
                out.append((outgoing, incoming))
        return out

    def repeated_sections(self) -> list[dict[str, Any]]:
        """Every occurrence after the first of a section type.

        A second drop counts as a repeat of the first: it is the single most
        common place a generated arrangement just plays the same thing again.
        """
        seen: dict[str, int] = {}
        repeats: list[dict[str, Any]] = []
        for item in self.musical_sections:
            kind = str(item.get("type") or "").lower()
            family = "drop" if kind in ("drop", "second_drop") else kind
            seen[family] = seen.get(family, 0) + 1
            if seen[family] > 1:
                repeats.append(item)
        return repeats

    def roles_without_events(self) -> set[str]:
        """Roles a section claims but gives nothing to play.

        These become tracks with no clips — silent lanes that make the project
        look fuller than it sounds, and that the sound check reports as missing
        audio."""
        orphans: set[str] = set()
        for item in self.sections:
            lanes = " ".join(self.lane_keys(item))
            for role in self.section_roles(item):
                if role in ("automation", "fx", "riser", "noise", "crash", "impact"):
                    continue  # these are produced by other passes
                if role not in lanes:
                    orphans.add(role)
        return orphans


@dataclass(frozen=True)
class Requirement:
    """One thing a song of this kind needs that a brief usually omits.

    ``covered`` answers "did the author already deal with this?". It returns
    True when the brief mentions it in any form — a role, a technique, or just a
    sentence — because inferring a step somebody already specified is worse than
    useless: it overrides their intent.
    """

    id: str
    label: str
    why: str
    step: str
    area: str
    covered: Callable[[SpecView], bool]
    applies_to: tuple[str, ...] = ("all",)
    roles: tuple[str, ...] = ()
    confidence: str = "medium"
    commonly_omitted: str = ""
    #: Further findings this same step prevents. Setting a level ladder heads off
    #: clipping, headroom and over-compression as much as it does level, and the
    #: backward loop is only useful if a requirement can say so.
    also_prevents: tuple[str, ...] = ()
    #: False when ``covered`` reads only the spec's structure (sections, roles,
    #: lane events) and never the author's words. A model judging coverage is
    #: not asked about those: no quote can make a missing lane event exist.
    prose: bool = True
    #: True when the requirement is only satisfied by values - a frequency, a
    #: depth, a dB target, a bar count. A model may then only mark it covered
    #: with a quote that carries a number, a unit or a technique word: "kick"
    #: or "drop" is not evidence that the author set anything.
    needs_values: bool = False

    def applies(self, style_lane: str) -> bool:
        return "all" in self.applies_to or style_lane in self.applies_to

    @property
    def areas(self) -> tuple[str, ...]:
        return tuple(a for a in (self.area, *self.also_prevents) if a and a != "none")


@dataclass
class Gap:
    """A requirement the brief did not cover, as an actionable step."""

    id: str
    label: str
    why: str
    step: str
    area: str
    roles: tuple[str, ...] = ()
    confidence: str = "medium"
    source: str = "rubric"
    evidence: str = ""

    def as_decision(self) -> dict[str, Any]:
        """Shaped like the decisions fill_in_blanks.py already records, so the
        materializer turns it into a recipe item with no special casing."""
        return {
            "area": f"missing step: {self.label}",
            "detail": self.step,
            "reason": self.why if not self.evidence else f"{self.why} {self.evidence}",
            "confidence": self.confidence,
            "requirementId": self.id,
            "soundCheckArea": self.area,
            "source": self.source,
        }


def _all_payoffs_have(view: SpecView, *needles: str) -> bool:
    payoffs = view.payoff_sections
    if not payoffs:
        return True  # nothing to check yet; section-flow filling handles this
    return all(view.section_techniques(s) & set(needles) or view.mentions(*needles) for s in payoffs)


# ---------------------------------------------------------------------------
# The catalogue.
#
# Each entry is a step that a generated project needs and that a normal brief
# leaves out. Keep `covered` cheap and forgiving: a false "already covered" only
# means we skip a suggestion, but a false "missing" overrides what the author
# actually asked for.
# ---------------------------------------------------------------------------

REQUIREMENTS: list[Requirement] = []


def register(requirement: Requirement) -> Requirement:
    REQUIREMENTS.append(requirement)
    return requirement


# ---------------------------------------------------------------------------
# Low end and space.
#
# Two things wanting the same frequency at the same moment is the most common
# reason a generated arrangement sounds worse than the sum of its parts.
# ---------------------------------------------------------------------------

register(Requirement(
    id="low_end_ownership",
    needs_values=True,
    label="Decide who owns the low end",
    why="With a sub and a bass both playing the fundamental, the two cancel and reinforce unpredictably and the low end reads as loud but shapeless.",
    step=(
        "Split the bottom into two jobs. Give the sub root notes only, on the kick beats, "
        "mono, band 20-90 Hz. Give the mid bass the syncopated rhythm, high-passed around "
        "100 Hz so it stops doubling the fundamental. Say in the mix notes which one owns "
        "each moment."
    ),
    area="Low end",
    roles=("sub", "bass", "kick"),
    commonly_omitted="A brief says 'heavy bass', which is one idea; a mix needs it to be two.",
    covered=lambda v: (
        not (v.has_role("bass") and (v.has_role("sub") or v.has_role("kick")))
        or v.notes_match(r"sub.*(own|below|under|only|root)|owns the low|mono below|high[- ]?pass.*bass|\b\d+ ?hz")
    ),
))

register(Requirement(
    id="duck_parameters",
    needs_values=True,
    label="Say how the sidechain actually ducks",
    why="Naming sidechain without a source, depth or release leaves the generator to guess, and a guess is usually either inaudible or a pumping artefact.",
    step=(
        "Specify the duck: keyed from the kick, depth roughly sub 0.65, bass 0.50, chords 0.45, "
        "pads 0.45, FX 0.30; release about an eighth note at the project tempo; exempt the lead, "
        "snare, clap and impacts so the hook and the transients stay put."
    ),
    area="Low end",
    roles=("sub", "bass", "chords", "kick"),
    commonly_omitted="'Sidechained' is treated as a single switch rather than a set of values.",
    covered=lambda v: (
        not v.payoff_sections
        or v.notes_match(r"(duck|sidechain|pump).{0,80}(\d|depth|release|amount|key|from the kick|exempt)")
    ),
))

register(Requirement(
    id="hpf_ladder",
    needs_values=True,
    label="High-pass everything that is not the low end",
    why="Every melodic and FX layer carries low rumble that adds up into the 200-500 Hz range, which is exactly where the checker reports mud.",
    step=(
        "Give each lane a high-pass: chords 180 Hz, lead 220 Hz (250 in the drop), plucks 250 Hz, "
        "vocals 150 Hz, guitars 120 Hz, FX/risers/noise/crashes 300 Hz. Only the kick, sub and bass "
        "are exempt. Record it as a mix note so the renderer and a human agree."
    ),
    area="Low mids",
    roles=("chords", "lead", "pluck", "vocal", "fx"),
    commonly_omitted="It is invisible work: nothing sounds wrong on any single track, only on all of them at once.",
    covered=lambda v: v.notes_match(r"high[- ]?pass|hpf|hi ?pass|low ?cut|roll(ing)? off the low"),
))

register(Requirement(
    id="mono_below_crossover",
    needs_values=True,
    label="Keep the bottom mono",
    why="Widened low frequencies partially cancel when the track is played in mono, so the bass disappears on phones and club systems.",
    step=(
        "State a mono crossover — 110 Hz for house, 130 for future bass and modern EDM, 150 for "
        "darker bass music — and mark the kick, sub and bass lanes mono. Apply every widener, "
        "chorus and reverb send after the lane's high-pass, never before it."
    ),
    area="Mono",
    also_prevents=("Stereo", "Low end"),
    roles=("sub", "bass", "kick"),
    commonly_omitted="Mono compatibility only shows up on a system nobody is mixing on.",
    covered=lambda v: v.notes_match(r"mono (below|under|bottom|bass)|elliptical|mono[- ]?compat|bass in mono"),
))

register(Requirement(
    id="width_budget",
    needs_values=True,
    label="Decide what is allowed to be wide",
    why="When every layer is widened, nothing sounds wide, the centre hollows out, and stereo correlation drops far enough for the checker to flag it.",
    step=(
        "Assign each lane a width tier: centre-locked (kick, sub, bass, snare body, the main hook), "
        "mid 0.25-0.40 (chords, hats, plucks), wide 0.60-0.80 (the lead octave double, vocal chops, "
        "FX, reverb returns). Keep no more than two or three lanes wide at once."
    ),
    area="Stereo",
    roles=("chords", "lead", "fx", "vocal"),
    commonly_omitted="'Make it wide' is a description of a feeling, not an allocation.",
    covered=lambda v: v.notes_match(r"cent(er|re)[- ]?lock|width (tier|budget)|keep .* (centred|centered|narrow|mono)|only .* wide"),
))

register(Requirement(
    id="fx_return_discipline",
    needs_values=True,
    label="Shape the reverb and delay returns",
    why="Reverb and delay on every lane at default settings is the fastest way to fill 200-500 Hz with wash and lose the transients.",
    step=(
        "Declare two returns with real values. A plate: pre-delay 20 ms, decay 1.4-1.8 s (shorter for "
        "house), high-pass 300 Hz, low-pass 8 kHz, wet capped near 12%, ducked ~30% by the kick. "
        "A ping delay: dotted eighth, feedback 0.30, high-passed, wet under 15%. Name which lanes "
        "are not allowed to send at all — typically the kick, sub and bass."
    ),
    area="Low mids",
    roles=("chords", "vocal", "lead"),
    commonly_omitted="Reverb gets named as an effect, never as a set of numbers.",
    covered=lambda v: (
        not v.has_technique("reverb", "delay")
        or v.notes_match(r"(pre-?delay|decay|tail|wet|damp|return|send).{0,40}\d|\d+ ?(ms|s)\b.{0,30}(reverb|delay|tail)")
    ),
))

register(Requirement(
    id="register_split_layers",
    label="Give stacked melodic layers their own register",
    why="Chords, lead and plucks written in the same octave mask each other, so the hook stops being the loudest idea even when it is the loudest track.",
    step=(
        "Pin registers and rhythmic slots: chords voiced C3-C5 with the top voice at least a fourth "
        "below the lead's lowest note; the hook C5-C6; the octave double at +12 and quieter; plucks "
        "restricted to the hook's rest beats as call-and-response rather than playing underneath it."
    ),
    area="Low mids",
    roles=("chords", "lead", "pluck"),
    commonly_omitted="A brief lists the layers it wants; it does not say where each one sits.",
    covered=lambda v: (
        len({"chords", "lead", "pluck", "vocal"} & v.roles) < 2
        or v.notes_match(r"octave|\+12|register|voicing|above the|below the|inversion")
    ),
))

# ---------------------------------------------------------------------------
# Levels.
# ---------------------------------------------------------------------------

register(Requirement(
    id="gain_ladder",
    needs_values=True,
    label="Set a level ladder and a peak budget",
    why="With no target levels the render is balanced by whatever the generator's defaults happen to be, which is how a mix ends up either quiet or squashed.",
    step=(
        "Write lane offsets relative to the kick: kick 0 dB, sub -2, bass -5, lead -4, clap -6, "
        "chords -7, vocal -8, plucks -12, FX -12, hats -14. Set a master ceiling of -1.0 dBFS and "
        "allow only the drop within a dB of it."
    ),
    area="Level",
    also_prevents=("Clipping", "Headroom", "Density"),
    commonly_omitted="Nobody describes a song in decibels, but every song has them.",
    covered=lambda v: v.notes_match(r"-?\d+(\.\d+)? ?(db|lufs)|headroom|ceiling|gain stag"),
))

register(Requirement(
    id="section_energy_arc",
    label="Give each section an energy target",
    why="Without per-section levels every part renders at the same intensity, so the drop is not actually louder than the verse and the song reads flat.",
    step=(
        "Assign an energy value per section and let it scale the lane gains: intro 0.45, verse 0.70, "
        "build 0.65 rising to 1.00, break 0.40, drop 1.25, second drop 1.35, outro 0.35. The break "
        "must be the quietest thing between the two drops."
    ),
    area="Consistency",
    also_prevents=("Density", "Level"),
    commonly_omitted="'Build up to it' describes a shape without giving it any numbers.",
    covered=lambda v: v.notes_match(r"energy|louder|quieter|intensity|dynamic|level.{0,20}section|section.{0,20}level"),
))

register(Requirement(
    id="velocity_movement",
    label="Vary how hard notes are played",
    why="Every note at the same velocity is what makes programmed music sound programmed, and it flattens the crest factor the checker measures as punch.",
    step=(
        "Accent the kick on the downbeat and the hook's first and highest notes. Mark snares and "
        "claps landing off the grid as ghost notes. Alternate hat gain across the sixteenths "
        "(1.0 / 0.72 / 0.88 / 0.72) instead of leaving them uniform."
    ),
    area="Punch",
    also_prevents=("Density", "Consistency"),
    roles=("kick", "snare", "clap", "hat", "lead"),
    commonly_omitted="Velocity is not something a description mentions; it is something a player does.",
    covered=lambda v: v.notes_match(r"velocit|accent|ghost note|humani[sz]|dynamics"),
))

# ---------------------------------------------------------------------------
# Transitions and arrangement shape.
# ---------------------------------------------------------------------------

register(Requirement(
    id="boundary_transition_fx",
    label="Mark every energy change with a transition",
    why="Sections that simply start next to each other sound edited together rather than written together, and a drop with no lead-in does not land.",
    step=(
        "At each rise in energy put a riser or reverse cymbal in the outgoing section's last bar and "
        "an impact plus crash on the incoming downbeat. At each fall use a downlifter and let a "
        "reverb tail carry across the boundary."
    ),
    area="Arrangement",
    roles=("fx", "riser", "crash", "impact"),
    commonly_omitted="Transitions are the glue nobody describes because they are not parts.",
    covered=lambda v: (
        not v.rising_pairs()
        or v.mentions("riser", "sweep", "impact", "downlifter", "reverse cymbal", "transition", "whoosh")
    ),
))

register(Requirement(
    id="pre_drop_gap",
    label="Leave space in the bar before the drop",
    why="A build that runs at full density straight into the drop gives the drop nothing to be louder than, so the payoff arrives without contrast.",
    step=(
        "Stop the drums and bass after beat 2 of the build's final bar, put a reverse crash in the "
        "gap, and open the drop with an impact on beat 1. The silence is what makes the drop feel big."
    ),
    area="Punch",
    also_prevents=("Clipping", "Density"),
    roles=("kick", "snare", "bass", "fx"),
    commonly_omitted="Everyone describes the drop; almost nobody describes the half-second before it.",
    covered=lambda v: (
        not v.rising_pairs()
        or v.notes_match(r"fake stop|silence|gap|cut (everything|the drums|out)|drop out|beat of silence|breath before")
    ),
))

register(Requirement(
    id="build_stepped_ramp",
    label="Make the build accelerate in stages",
    why="A build with one constant drum pattern and one long filter sweep is a ramp, not a build; tension comes from density changing in steps.",
    step=(
        "Step the hats up across the build: eighths, then sixteenths, then sixteenths with offbeat "
        "claps, then thirty-seconds in the last two bars. Bring the snare in halfway. Use two "
        "automation envelopes rather than one, the second steeper than the first."
    ),
    area="Arrangement",
    roles=("hat", "snare", "automation"),
    commonly_omitted="'Build up' names the section without saying how the tension is produced.",
    covered=lambda v: (
        not v.sections_of("build", "pre_build")
        or any(v.has_bar_scoped_events(s) for s in v.sections_of("build", "pre_build"))
        or v.notes_match(r"double[- ]?time|sixteenth|32nd|thirty-second|step up|faster and faster|accelerat")
    ),
))

register(Requirement(
    id="phrase_end_fill",
    label="Put a fill at the end of each phrase",
    why="An eight-bar loop that repeats identically is heard as a loop; a variation in the eighth bar is what turns repetition into structure.",
    step=(
        "In the last bar of every eight-bar phrase add a snare or clap roll across beats 3 to 4 with "
        "gain rising, an open hat on the final sixteenth, and a crash on the downbeat of the next "
        "phrase."
    ),
    area="Arrangement",
    roles=("snare", "clap", "hat", "crash"),
    commonly_omitted="Fills are assumed. Generators do not assume.",
    covered=lambda v: (
        not v.musical_sections
        or any(v.has_bar_scoped_events(s, "snare", "clap", "hat", "kick", "ride", "crash") for s in v.musical_sections)
        or v.mentions("fill", "roll", "turnaround")
    ),
))

register(Requirement(
    id="per_bar_drum_variation",
    prose=False,
    label="Stop the drums repeating bar for bar",
    why="The renderer reuses an unscoped pattern for every bar, so without bar-scoped events the sixteenth bar of a drop is identical to the first.",
    step=(
        "Scope some drum events to particular bars: an open hat on odd bars, a kick dropped on the "
        "last beat of bar 4, an extra clap on bar 6. Small differences, but they stop the pattern "
        "reading as a loop."
    ),
    area="Punch",
    roles=("kick", "snare", "hat"),
    commonly_omitted="Nobody writes down the bars where a beat should differ.",
    covered=lambda v: (
        not v.musical_sections
        or any(v.has_bar_scoped_events(s, "kick", "snare", "clap", "hat", "ride") for s in v.musical_sections)
    ),
))

register(Requirement(
    id="contrast_before_repeat",
    prose=False,
    label="Put something between the two drops",
    why=(
        "A second drop that follows the first with nothing in between has no contrast to arrive "
        "from, so the biggest moment in the song lands as more of the same."
    ),
    step=(
        "Insert a break and a second build between the drops. The break strips the low end and "
        "leaves chords and a vocal or lead fragment; the build re-accelerates into the second drop. "
        "Without that reset the second drop cannot be a lift, only a repetition."
    ),
    area="Arrangement",
    roles=("chords", "vocal", "fx"),
    commonly_omitted=(
        "'And then a second drop' reads as a complete instruction, but it describes the destination "
        "and not the journey back up to it."
    ),
    covered=lambda v: all(
        not (
            SpecView.ENERGY_RANK.get(str(a.get("type") or "").lower(), 0) == 4
            and SpecView.ENERGY_RANK.get(str(b.get("type") or "").lower(), 0) == 4
        )
        for a, b in v.adjacent_pairs()
    ),
))

register(Requirement(
    id="break_subtraction",
    label="Make the break subtractive",
    why="A break that keeps the kick and bass but turns down is not a contrast, so the second drop has nothing to return from.",
    step=(
        "Remove the sub, kick and bass from the break entirely rather than lowering them. Leave "
        "chords and a vocal or lead fragment, filter the chords down across the section, and let a "
        "reverb tail cover the gap."
    ),
    area="Arrangement",
    roles=("sub", "kick", "bass", "chords"),
    commonly_omitted="'Break it down' sounds like a level change; it is really a subtraction.",
    covered=lambda v: (
        not v.sections_of("break")
        or all(not ({"sub", "kick", "bass", "drums"} & v.section_roles(s)) for s in v.sections_of("break"))
        or v.notes_match(r"strip|drop out|remove the (kick|bass|drums)|no drums|only the chords")
    ),
))

register(Requirement(
    id="repeat_section_variation",
    label="Change repeated sections instead of duplicating them",
    why="A second drop identical to the first is the clearest sign of a generated arrangement, and it wastes the one moment the listener is most invested.",
    step=(
        "Copy the earlier section and force at least two additions and one subtraction: an octave "
        "lead double, halved hat spacing plus a ride, a widening automation on the chords, and "
        "something from the first pass removed so the change is audible as a change."
    ),
    area="Arrangement",
    roles=("lead", "hat", "chords"),
    commonly_omitted="'Then the second drop' implies the same drop again unless somebody says otherwise.",
    covered=lambda v: (
        not v.repeated_sections()
        or all(v.has_transforms(s) or v.has_bar_scoped_events(s) for s in v.repeated_sections())
        or v.notes_match(r"bigger|different|add(s|ed)? .*(octave|ride|layer)|vari(ation|ed)|escalat|lift")
    ),
))

register(Requirement(
    id="outro_resolution",
    label="Let the outro actually resolve",
    why="An outro that is just the last section with fewer parts stops rather than ends, and the render tails off at full brightness.",
    step=(
        "Automate the chord filter down from 0.85 to 0.15 and the drum volume from 0.80 to 0.05 "
        "across the outro, keep only a subset of the drop's parts, and place the final impact at the "
        "start of the section rather than the end."
    ),
    area="Arrangement",
    roles=("chords", "automation"),
    commonly_omitted="The ending is the part of a song people forget to describe.",
    covered=lambda v: (
        not v.sections_of("outro")
        or any(v.has_lane_events(s, "automation") for s in v.sections_of("outro"))
        or v.notes_match(r"fade|resolve|filter down|tail off|wind down|ends? (on|with)")
    ),
))

# ---------------------------------------------------------------------------
# The hook. A technically clean track nobody remembers has still failed.
# ---------------------------------------------------------------------------

register(Requirement(
    id="hook_carrier_declaration",
    label="Say which lane carries the hook",
    why="If no lane is declared as the hook, every melodic layer is treated as equally important and none of them ends up being the thing you remember.",
    step=(
        "Name the carrier — the lead for brighter styles, the bass synth for darker ones — plus its "
        "supporting layers, and list the sections where it states the full phrase rather than a "
        "fragment."
    ),
    area="none",
    roles=("lead", "bass"),
    commonly_omitted="'Catchy' describes the goal; it does not say which instrument is responsible for it.",
    covered=lambda v: v.notes_match(r"main (lead|bass|synth|vocal|melody)|hook|topline|the riff|lead line"),
))

register(Requirement(
    id="hook_recurrence",
    label="State the hook often enough to be learned",
    why="A melody heard once or twice is not a hook. Recurrence is what makes it memorable, and generated arrangements routinely state it only in the drops.",
    step=(
        "Aim for at least four statements across the song, with one before the first drop — a "
        "filtered fragment in the intro, the full phrase in both drops, and a stripped callback in "
        "the outro."
    ),
    area="none",
    roles=("lead",),
    commonly_omitted="Repetition feels like padding when you write a description, and like the song when you hear it.",
    covered=lambda v: v.notes_match(r"repeat|recur|comes? back|callback|again in the|throughout|reprise"),
))

register(Requirement(
    id="hook_answer_phrase",
    label="Write the hook as a four-bar phrase, not a one-bar loop",
    why="A single-bar hook is repeated verbatim for every bar of the drop, which is heard as a stuck loop rather than a melody.",
    step=(
        "Expand the hook to four bars: bars 1 and 3 state the question, bar 2 varies its ending, and "
        "bar 4 answers by landing on the tonic or fifth with a longer final note."
    ),
    area="none",
    roles=("lead",),
    commonly_omitted="People hum the one bar they remember and assume the rest.",
    covered=lambda v: (
        not v.payoff_sections
        or any(v.has_bar_scoped_events(s, "lead", "vocal", "bass") for s in v.payoff_sections)
        or v.notes_match(r"four[- ]?bar|4[- ]?bar|phrase|question|answer|call and response")
    ),
))

register(Requirement(
    id="hook_contour",
    label="Keep the hook singable",
    why="An unconstrained melody spreads across two octaves and a dozen pitch classes, which is playable but not hummable, and hummable is the whole point.",
    step=(
        "Constrain the hook: no more than an octave of range, five or fewer distinct pitch classes, "
        "most steps a tone or less, one clear highest note used sparingly, and a rest each bar so "
        "the phrase can breathe."
    ),
    area="none",
    roles=("lead",),
    commonly_omitted="'Catchy' is the requirement; nobody states the constraints that produce it.",
    covered=lambda v: v.notes_match(r"contour|singable|hummable|simple melody|few notes|stepwise|range of|octave range"),
))

register(Requirement(
    id="call_and_response",
    label="Answer the hook in its own gaps",
    why="The rests in a hook are structural. Left empty in every bar the drop feels sparse; filled by a pad it feels crowded; answered by a second voice it feels written.",
    step=(
        "Put a responder in the hook's largest rest — a vocal chop or a short pluck figure — on the "
        "alternate bars only, quieter than the hook and pitched a fourth or fifth above it, so it "
        "answers rather than doubles."
    ),
    area="Arrangement",
    roles=("vocal", "pluck", "fx"),
    commonly_omitted="It only becomes obvious once you hear the gap.",
    covered=lambda v: v.notes_match(r"call and response|answer|respon|counter[- ]?melody|back and forth|trade"),
))

register(Requirement(
    id="hook_octave_double",
    label="Give the lead double its own lane",
    why="A hook thickened by widening the same signal loses level in mono; a genuine second layer an octave up survives the collapse and stays bright.",
    step=(
        "Add a separate lead-double lane at +12 semitones, around 0.55 the level of the hook, "
        "detuned under 8 cents, high-passed at 300 Hz and panned modestly. Use it in the final drop "
        "so the last chorus is the widest moment."
    ),
    area="Stereo",
    roles=("lead",),
    commonly_omitted="'Make the lead huge' sounds like an effect and is actually an arrangement decision.",
    covered=lambda v: (
        not v.has_role("lead")
        or v.notes_match(r"double|octave up|stack|layer the lead|thicken|unison")
    ),
))

# ---------------------------------------------------------------------------
# Texture and detail.
# ---------------------------------------------------------------------------

register(Requirement(
    id="texture_bed",
    label="Run a quiet texture underneath",
    why="Digital arrangements have literal silence between the parts, which reads as small; a continuous low-level bed is most of what makes a record sound finished.",
    step=(
        "Add a noise or crowd bed at roughly 5% gain running from the first verse to the outro, "
        "high-passed at 300 Hz, ducked slightly under the drops. It should be inaudible when "
        "soloed and obvious when muted."
    ),
    area="Top end",
    roles=("noise", "fx"),
    commonly_omitted="By definition you do not notice it, so you do not ask for it.",
    covered=lambda v: v.mentions("noise", "texture", "atmosphere", "ambience", "vinyl", "crowd", "air"),
))

register(Requirement(
    id="single_use_ear_candy",
    label="Put in one sound that happens once",
    why="A song where every element repeats on a grid has nothing to reward a second listen; one unrepeated detail is what makes an arrangement feel authored.",
    step=(
        "Pick one moment — the downbeat of the second drop, or the first bar of the break — and put "
        "something there that appears nowhere else: a reversed vocal swell, a pitch-sweep answer, a "
        "single filtered stab."
    ),
    area="none",
    roles=("fx", "vocal", "sample"),
    commonly_omitted="It is the opposite of a system, so no description implies it.",
    covered=lambda v: v.notes_match(r"once|one[- ]?off|only (in|at|during)|single .*(hit|stab|swell)|ear candy"),
))

register(Requirement(
    id="fx_band_split",
    needs_values=True,
    label="Band-limit the transition FX",
    why="Risers, crashes, noise and impacts stacked on one full-range lane collide with the hook on top and the kick underneath at exactly the loudest moment.",
    step=(
        "Split the FX pile and band-limit each part: risers and noise 400 Hz to 12 kHz, crashes above "
        "250 Hz decaying within two beats, impacts 40-200 Hz and mono. Duck the whole group under the "
        "drop's first bar so the downbeat stays clear."
    ),
    area="Top end",
    roles=("fx", "riser", "crash", "impact"),
    commonly_omitted="FX are described as a group because they are heard as a group.",
    covered=lambda v: (
        len({"riser", "noise", "crash", "impact", "fx", "downlifter"} & v.roles) < 3
        or v.notes_match(r"band|high[- ]?pass.*(fx|riser|crash)|duck.*(fx|riser)|filter.*(riser|crash|impact)")
    ),
))

# ---------------------------------------------------------------------------
# Buildability. A project can be structurally valid and musically empty.
# ---------------------------------------------------------------------------

register(Requirement(
    id="roles_need_content",
    prose=False,
    label="Give every named part something to play",
    why="A role listed in a section but never given events becomes a track with no clips: the project looks fuller than it sounds, and the checker reports it as missing audio.",
    step=(
        "For each role with no lane events, either write a starter pattern for it or take it out of "
        "the section. An empty lane is worse than an absent one, because it hides the fact that the "
        "part was never made."
    ),
    area="Missing audio",
    also_prevents=("Arrangement",),
    commonly_omitted="Naming an instrument feels like adding it.",
    covered=lambda v: not v.roles_without_events(),
))

register(Requirement(
    id="explicit_section_lengths",
    needs_values=True,
    label="Give every section a bar count",
    why=(
        "Without lengths the generator picks its own, so the arrangement the listener hears is not "
        "the one that was described and section boundaries land in arbitrary places."
    ),
    step=(
        "State bars per section: intro 8, verse 16, build 8, drop 16, break 8, second build 8, "
        "second drop 16, outro 8. Check the total against the tempo — that shape is about three "
        "minutes at 140 BPM."
    ),
    area="Length",
    also_prevents=("Arrangement",),
    commonly_omitted="People describe songs in parts, not in bars.",
    covered=lambda v: (
        not v.musical_sections
        or any(s.get("bars") or s.get("barCount") for s in v.musical_sections)
        or v.notes_match(r"\b\d+ ?bars?\b|\b(eight|sixteen|thirty-two)[- ]bar")
    ),
))

register(Requirement(
    id="automation_targets_a_lane",
    label="Point every automation move at a lane",
    why=(
        "An envelope with no target modulates nothing. The project looks automated and renders "
        "completely static, which is the hardest kind of missing work to spot."
    ),
    step=(
        "For each automation move name the lane and the parameter it drives — 'chords filter 0.2 to "
        "0.9 across the build', not 'filter sweep'. An envelope without both is not buildable."
    ),
    area="Arrangement",
    roles=("automation",),
    commonly_omitted="'Filter sweep' names the sound, not the thing being swept.",
    covered=lambda v: (
        not (v.has_role("automation") or v.mentions("automation", "sweep", "envelope"))
        or v.notes_match(r"(filter|volume|pan|width|cutoff|reverb|delay).{0,30}(on|of|for) the \w+|\w+ (filter|volume|pan|width)")
    ),
))

register(Requirement(
    id="hook_key_anchoring",
    label="Keep the hook in the stated key",
    why=(
        "A melody generated from defaults while the chords come from the declared key produces notes "
        "that clash, which sounds like a mistake rather than a choice."
    ),
    step=(
        "Write the hook as explicit note values drawn from the declared key, and transpose the chord "
        "progression to the same tonic. Every pitch in the hook should belong to the scale unless it "
        "is a deliberate passing note."
    ),
    area="none",
    roles=("lead", "chords"),
    commonly_omitted="A key gets stated once and then never connected to the actual notes.",
    covered=lambda v: (
        not v.has_role("lead")
        or v.notes_match(r"\b[a-g](#|b)? ?(major|minor|maj|min)\b.{0,60}(hook|lead|melody|scale)|scale|diatonic|in key")
    ),
))

register(Requirement(
    id="single_motif_family",
    label="Derive every melodic part from one idea",
    why=(
        "Unrelated melodies in the intro, drop and break give a song three identities and no hook; "
        "one idea restated is what makes an arrangement cohere."
    ),
    step=(
        "Pick the drop's hook as canonical and derive the rest from it: the intro states a truncated "
        "filtered version, the break plays it slower or on a different instrument, the outro plays "
        "its first two notes. Same idea, different treatment."
    ),
    area="none",
    roles=("lead",),
    commonly_omitted="Each section gets described on its own, so nothing forces them to be related.",
    covered=lambda v: (
        len([s for s in v.musical_sections if "lead" in v.section_roles(s)]) < 2
        or v.notes_match(r"same (melody|motif|riff|hook|notes)|motif|variation of|derived|reprise|from the (verse|drop|intro)")
    ),
))

register(Requirement(
    id="arrangement_length",
    prose=False,
    label="Make the arrangement long enough to be a song",
    why="Two or three sections render to well under a minute, which is a loop rather than an arrangement, and there is nothing for a mix judgement to be about.",
    step=(
        "Aim for at least intro, verse, build, drop, break, build, second drop and outro. At typical "
        "tempos that is two and a half to three minutes, which is the shortest thing that reads as a "
        "finished track."
    ),
    area="Length",
    also_prevents=("Arrangement", "Recipe"),
    commonly_omitted="A description covers the exciting parts and skips the connective ones.",
    covered=lambda v: len(v.musical_sections) >= 6,
))


# ---------------------------------------------------------------------------
# The model's two jobs here (see docs/ai.md).
#
# 1. Judging coverage. The ``covered`` lambdas above are keyword matches, and
#    keywords lie in both directions: "once the drop hits" covers nothing about
#    ear candy, and "a soft rain recording under everything" is a texture bed
#    that no keyword catches. A model reads the notes and answers per
#    requirement - but it may only mark something covered if it can quote the
#    words, and the quote has to be in the notes.
# 2. Wording the step. The catalogue's steps carry numbers for a generic song.
#    Given this song's sections, tempo and key the model rewrites step and why;
#    the id, area and roles - the things the sound check maps back onto - are
#    never its to change.
#
# Both take an ``asker(task, schema) -> answer | None`` so this module knows
# nothing about providers; fill_in_blanks.py supplies one built on llm.Assist.
# ---------------------------------------------------------------------------

Asker = Callable[[str, dict[str, Any]], Any]

CONFIDENCE_WORDS = ("low", "medium", "high")

COVERAGE_SCHEMA: dict[str, Any] = {
    "requirements": [
        {
            "id": "requirement id from the list",
            "covered": False,
            "quote": "the author's exact words that deal with it, copied verbatim and kept short - or null",
            "reason": "one short sentence",
        }
    ],
}

GAP_TEXT_SCHEMA: dict[str, Any] = {
    "gaps": [
        {
            "id": "gap id from the list",
            "step": "the instruction rewritten for this song: name its sections, tempo, key and parts; keep any numbers realistic",
            "why": "one or two sentences on why this particular song needs it",
            "confidence": "low, medium or high",
        }
    ],
}


class CoverageJudge:
    """Asks a model which requirements the author already dealt with.

    ``verdicts`` maps requirement id to ``{"covered", "quote", "reason"}`` once
    ``judge`` has run. A "covered" verdict is only recorded when its quote is
    really in the notes; anything else is dropped and written to ``dropped``.
    """

    def __init__(self, asker: Asker, *, chunk_chars: int = 24000) -> None:
        self.asker = asker
        self.chunk_chars = chunk_chars
        self.verdicts: dict[str, dict[str, Any]] = {}
        self.dropped: list[str] = []
        self.calls = 0

    def judge(self, view: SpecView, requirements: list[Requirement]) -> dict[str, dict[str, Any]]:
        notes = view.notes_raw
        if not notes or not requirements:
            return self.verdicts
        requirements = [r for r in requirements if r.prose]
        if not requirements:
            return self.verdicts
        ids = {r.id for r in requirements}
        by_id = {r.id: r for r in requirements}
        catalogue = [
            {"id": r.id, "label": r.label, "needs": r.why, "commonlyOmitted": r.commonly_omitted}
            for r in requirements
        ]
        chunks = chunk_text(notes, self.chunk_chars)
        for index, chunk in enumerate(chunks, start=1):
            task = (
                "Below are production requirements a brief usually leaves out, and the notes an author "
                "wrote about one song. For each requirement say whether the author already dealt with "
                "it in these notes. Covered means the author actually addresses what the requirement "
                "asks for - naming a technique with no detail does not cover a requirement that asks "
                "for values. When covered, quote the exact words (verbatim, a short span) that cover it. "
                "Do not guess: when the notes say nothing about it, covered is false and quote is null.\n\n"
                f"Requirements:\n{json.dumps(catalogue, ensure_ascii=False)}\n\n"
                f"Notes (part {index} of {len(chunks)}):\n{chunk}"
            )
            self.calls += 1
            answer = self.asker(task, COVERAGE_SCHEMA)
            if not isinstance(answer, dict):
                continue
            for item in answer.get("requirements") or []:
                if not isinstance(item, dict):
                    continue
                requirement_id = str(item.get("id") or "")
                if requirement_id not in ids:
                    self.dropped.append(f"coverage: unknown requirement {requirement_id!r}")
                    continue
                reason = str(item.get("reason") or "").strip()[:300]
                if item.get("covered") is True:
                    quote = item.get("quote")
                    if not quote_in(notes, quote):
                        self.dropped.append(
                            f"coverage: {requirement_id} marked covered without a quote from the notes; the rule decides"
                        )
                    elif by_id[requirement_id].needs_values and not values_evidence(quote):
                        self.dropped.append(
                            f"coverage: {requirement_id} asks for values and {str(quote).strip()!r} names none; the rule decides"
                        )
                    else:
                        self.verdicts[requirement_id] = {
                            "covered": True,
                            "quote": re.sub(r"\s+", " ", str(quote)).strip(),
                            "reason": reason,
                        }
                elif item.get("covered") is False:
                    # A later chunk cannot un-cover what an earlier one quoted.
                    self.verdicts.setdefault(requirement_id, {"covered": False, "quote": "", "reason": reason})
        return self.verdicts


#: One number, or a range of two ("120-500 Hz", "4 to 8 bars"), followed by a
#: unit. The range has to be read as two numbers: taking "-500" as the second
#: one would make every range with a hyphen look negative.
_NUMBER_WITH_UNIT = re.compile(
    r"(-?\d+(?:\.\d+)?)(?:\s*(?:-|\u2013|\u2014|to)\s*(-?\d+(?:\.\d+)?))?\s*(khz|hz|dbfs|lufs|db|ms|bpm|bars?|%)",
    re.IGNORECASE,
)

#: The bands a number in a mix instruction can plausibly sit in. A step outside
#: them ("high-pass the bass at 2 kHz", "hats at -40 dB") is a hallucination,
#: and the catalogue's own wording is used instead.
PLAUSIBLE_RANGES: dict[str, tuple[float, float]] = {
    "hz": (20.0, 20000.0),
    "khz": (0.02, 20.0),
    "db": (-60.0, 12.0),
    "dbfs": (-60.0, 0.0),
    "lufs": (-40.0, 0.0),
    "ms": (0.0, 5000.0),
    "bpm": (60.0, 220.0),
    "bar": (1.0, 64.0),
    "bars": (1.0, 64.0),
    "%": (0.0, 100.0),
}


def numbers_plausible(text: str) -> bool:
    """False when any unit-bearing number in ``text`` is outside its plausible band."""
    for first, second, unit in _NUMBER_WITH_UNIT.findall(text or ""):
        low, high = PLAUSIBLE_RANGES[unit.lower()]
        for value in (first, second):
            if value and not low <= float(value) <= high:
                return False
    return True


def personalise_gaps(
    asker: Asker,
    gaps: list[Gap],
    context: dict[str, Any],
    *,
    batch: int = 12,
) -> list[str]:
    """Rewrite each gap's step and why for this song, in place. Returns what was dropped.

    Ids, areas and roles are untouched: those are how measured findings map
    back onto requirements. A rewritten step with an implausible number, or
    for an id that was not asked about, is ignored and the catalogue text stays.
    """
    dropped: list[str] = []
    if not gaps:
        return dropped
    by_id = {gap.id: gap for gap in gaps}
    for start in range(0, len(gaps), batch):
        group = gaps[start:start + batch]
        items = [
            {"id": g.id, "label": g.label, "area": g.area, "roles": list(g.roles), "templateStep": g.step, "templateWhy": g.why}
            for g in group
        ]
        task = (
            "These production steps were written for a generic song. Rewrite each one for THIS song: "
            "name its actual sections, parts, tempo and key where they matter, keep the instruction "
            "concrete and buildable, and keep every number inside a realistic range for the unit. "
            "Do not add steps, drop steps, or change ids.\n\n"
            f"Song:\n{json.dumps(context, ensure_ascii=False)}\n\n"
            f"Steps:\n{json.dumps(items, ensure_ascii=False)}"
        )
        answer = asker(task, GAP_TEXT_SCHEMA)
        if not isinstance(answer, dict):
            continue
        for item in answer.get("gaps") or []:
            if not isinstance(item, dict):
                continue
            gap = by_id.get(str(item.get("id") or ""))
            if gap is None:
                dropped.append(f"gap-text: unknown gap {item.get('id')!r}")
                continue
            step = re.sub(r"\s+", " ", str(item.get("step") or "")).strip()[:700]
            why = re.sub(r"\s+", " ", str(item.get("why") or "")).strip()[:500]
            if len(step) < 30 or len(why) < 20:
                dropped.append(f"gap-text: {gap.id} came back too thin; kept the catalogue wording")
                continue
            if not numbers_plausible(step) or not numbers_plausible(why):
                dropped.append(f"gap-text: {gap.id} used an implausible number; kept the catalogue wording")
                continue
            gap.step = step
            gap.why = why
            gap.source = "model"
            confidence = str(item.get("confidence") or "").strip().lower()
            if confidence in CONFIDENCE_WORDS:
                gap.confidence = confidence
    return dropped


def find_gaps(
    spec: dict[str, Any],
    style_lane: str,
    *,
    prompt: str | None = None,
    intent: dict[str, Any] | None = None,
    skip: Iterable[str] = (),
    judge: CoverageJudge | None = None,
) -> list[Gap]:
    """Every requirement this brief does not already cover.

    ``spec`` is the arrangement being built; ``intent`` is what the author wrote.
    See ``SpecView`` for why those have to be different things.

    With a ``judge`` the model's reading of the notes is used where it can be
    trusted: a "covered" verdict backed by a quote hides the gap; a "not
    covered" verdict overrides a keyword match, but never coverage that comes
    from the structure of the spec itself. Without one, or wherever the model
    said nothing usable, the ``covered`` lambdas decide exactly as before.
    """
    view = SpecView(spec, prompt, intent=intent)
    skipped = set(skip)
    applicable = [r for r in REQUIREMENTS if r.id not in skipped and r.applies(style_lane)]
    verdicts: dict[str, dict[str, Any]] = {}
    if judge is not None:
        try:
            verdicts = dict(judge.judge(view, applicable) or {})
        except Exception:
            verdicts = {}
    structural_view: SpecView | None = None
    gaps: list[Gap] = []
    for requirement in applicable:
        try:
            covered = bool(requirement.covered(view))
        except Exception:
            # A malformed spec must never take the pipeline down. Treat an
            # unanswerable check as covered so we stay quiet rather than wrong.
            covered = True
        source = "rubric"
        evidence = ""
        verdict = verdicts.get(requirement.id) if requirement.prose else None
        if verdict is not None:
            if verdict.get("covered"):
                covered = True
            elif covered:
                # A keyword matched, the model read the same words and says they
                # do not deal with it. That only stands if the coverage came
                # from the words: structure is not up for debate.
                if structural_view is None:
                    structural_view = view.without_prose()
                try:
                    structural = bool(requirement.covered(structural_view))
                except Exception:
                    structural = True
                if not structural:
                    covered = False
                    source = "model"
                    reason = str(verdict.get("reason") or "").strip()
                    evidence = f"The notes were read and this was not addressed{': ' + reason if reason else '.'}"
        if covered:
            continue
        gaps.append(
            Gap(
                id=requirement.id,
                label=requirement.label,
                why=requirement.why,
                step=requirement.step,
                area=requirement.area,
                roles=requirement.roles,
                confidence=requirement.confidence,
                source=source,
                evidence=evidence,
            )
        )
    return gaps


def requirements_for_area(area: str) -> list[Requirement]:
    """The requirements that pre-empt a given sound-check finding."""
    lowered = area.strip().lower()
    return [r for r in REQUIREMENTS if lowered in {a.strip().lower() for a in r.areas}]


def requirement_by_id(requirement_id: str) -> Requirement | None:
    for requirement in REQUIREMENTS:
        if requirement.id == requirement_id:
            return requirement
    return None
