#!/usr/bin/env python3
"""Tests for the model layer of fill_in_blanks.py and production_rubric.py.

Nothing here touches the network: every test injects a fake transport through
``llm.Client(transport=...)`` and routes on the ``# question:`` tag each
prompt starts with. The model is off for anything that does not inject one,
so a real key on the machine can never leak into a test.

Run with:  /usr/bin/python3 -m unittest tools/test_fill_in_blanks_ai.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import unittest
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import llm  # noqa: E402
import production_rubric as rubric  # noqa: E402
from fill_in_blanks import (  # noqa: E402
    CHORD_SYMBOL_PATTERN,
    build_parser,
    fill_in_blanks,
    merge_gaps,
    parse_key,
    parse_progression,
    parse_tempo,
    render_markdown,
    song_context,
)
from test_fill_in_blanks import section, spec_from  # noqa: E402


QUESTION = re.compile(r"# question: ([\w-]+)")


def fake_transport(answers, calls):
    """A Gemini-shaped transport answering each tagged question from ``answers``.

    A value may be a dict (returned as the JSON reply), a callable taking the
    prompt text, or an int HTTP status to simulate a failure.
    """

    def transport(url, headers, body, timeout):
        text = body["contents"][0]["parts"][0]["text"]
        match = QUESTION.match(text)
        name = match.group(1) if match else "?"
        calls.append((name, text))
        payload = answers.get(name)
        if callable(payload):
            payload = payload(text)
        if isinstance(payload, int):
            return payload, json.dumps({"error": {"message": "simulated"}})
        reply = json.dumps(payload if payload is not None else {})
        return 200, json.dumps({"candidates": [{"content": {"parts": [{"text": reply}]}, "finishReason": "STOP"}]})

    return transport


def make_assist(answers, calls=None):
    client = llm.Client(
        "gemini", api_key="k", transport=fake_transport(answers, [] if calls is None else calls),
        use_cache=False, env={"NEON_CONFIG_DIR": "/nonexistent"},
    )
    return llm.Assist(client=client)


def off():
    return llm.Assist(enabled=False)

PINNED_ENV = {"NEON_AI": "off", "NEON_CONFIG_DIR": "/nonexistent", "GEMINI_API_KEY": "", "ANTHROPIC_API_KEY": ""}


class PinnedEnvironment(unittest.TestCase):
    """Every test runs with the model pinned off and no key on disk, and puts
    the environment back afterwards so no other module sees the change."""

    def setUp(self) -> None:
        super().setUp()
        self._saved_env = {name: os.environ.get(name) for name in PINNED_ENV}
        os.environ.update(PINNED_ENV)

    def tearDown(self) -> None:
        for name, value in self._saved_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        super().tearDown()


def prompts_for(calls, name):
    return [text for question, text in calls if question == name]


def json_after(text, marker):
    """The JSON value that follows ``marker`` in a prompt (the adapter appends
    its own schema text after it, so a plain json.loads would choke)."""
    return json.JSONDecoder().raw_decode(text.split(marker, 1)[1])[0]


class ValidatorTests(PinnedEnvironment):
    def test_tempo_range(self):
        self.assertEqual(parse_tempo(118), 118)
        self.assertEqual(parse_tempo("128.4"), 128)
        self.assertIsNone(parse_tempo(300))
        self.assertIsNone(parse_tempo(20))
        self.assertIsNone(parse_tempo("fast"))
        self.assertIsNone(parse_tempo(None))

    def test_key_forms(self):
        self.assertEqual(parse_key("f# minor"), "F# minor")
        self.assertEqual(parse_key("Bb Maj"), "Bb major")
        self.assertEqual(parse_key("E flat minor"), "Eb minor")
        self.assertIsNone(parse_key("purple"))
        self.assertIsNone(parse_key("F#"))  # no mode: ambiguous, so no key
        self.assertIsNone(parse_key(None))

    def test_progression_symbols_the_materializer_can_voice(self):
        self.assertEqual(parse_progression(["F#m", "D", "A", "E"]), ["F#m", "D", "A", "E"])
        self.assertEqual(parse_progression(["Em7", "Cmaj7", "Gadd9", "Dadd9"]), ["Em7", "Cmaj7", "Gadd9", "Dadd9"])
        self.assertIsNone(parse_progression(["Em", "Q#7"]), "one bad symbol drops the whole list")
        self.assertIsNone(parse_progression(["Em"]), "one chord is not a progression")
        self.assertIsNone(parse_progression(["Em", "C", "G", "D", "Am", "F", "C", "G", "Em"]), "capped at 8")
        self.assertIsNone(parse_progression("Em C G D"))

    def test_chord_pattern_agrees_with_the_materializer(self):
        # fill_in_blanks replicates the materializer's symbol grammar rather than
        # importing it; this is what keeps the two from drifting apart.
        import project_materializer

        for symbol in ("C", "F#m7", "Bbmaj7", "Gadd9", "Dsus4", "Adim", "E5", "G9", "Ebm9", "Cmin", "H", "Cm7b5", "c", "Fmaj13"):
            whole = project_materializer.CHORD_SYMBOL_RE.fullmatch(symbol) is not None
            self.assertEqual(
                CHORD_SYMBOL_PATTERN.match(symbol) is not None, whole,
                f"{symbol!r}: fill_in_blanks and the materializer disagree",
            )

    def test_quote_in_is_verbatim_but_forgiving_about_case_and_spacing(self):
        self.assertTrue(rubric.quote_in("The Kick   ducks the bass hard", "kick ducks the bass"))
        self.assertTrue(rubric.quote_in("said: 'high-pass at 200 Hz'", "“High-pass at 200 Hz”"))
        self.assertFalse(rubric.quote_in("the kick ducks the bass", "vinyl crackle"))
        self.assertFalse(rubric.quote_in("the kick ducks the bass", "the"), "too short to be evidence")
        self.assertFalse(rubric.quote_in("anything", None))

    def test_chunk_text_splits_long_notes_at_boundaries(self):
        text = ("The pad is wide. " * 3000).strip()
        chunks = rubric.chunk_text(text, 24000)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(c) <= 24000 for c in chunks))
        self.assertEqual(" ".join(chunks), text)
        self.assertEqual(rubric.chunk_text("", 100), [])

    def test_numbers_plausible(self):
        self.assertTrue(rubric.numbers_plausible("high-pass the chords at 180 Hz, hats at -14 dB, release 90 ms"))
        self.assertFalse(rubric.numbers_plausible("high-pass the bass at 40 kHz"))
        self.assertFalse(rubric.numbers_plausible("hats at -70 dB"))
        self.assertFalse(rubric.numbers_plausible("a 300 bar intro"))
        self.assertTrue(rubric.numbers_plausible("no numbers here"))

    def test_numbers_plausible_reads_a_range_as_two_positive_numbers(self):
        # "120-500 Hz" is a band, not 120 and minus 500.
        self.assertTrue(rubric.numbers_plausible("mid bass 120-500 Hz, sub 40-90 Hz, a 4-8 bar phrase, 20 to 90 Hz"))
        self.assertTrue(rubric.numbers_plausible("ride the bus between -14 to -10 dB"))
        self.assertFalse(rubric.numbers_plausible("air 40-30000 Hz"), "the far end of a range is checked too")
        self.assertFalse(rubric.numbers_plausible("a 2-300 bar build"))
        self.assertEqual(rubric._NUMBER_WITH_UNIT.findall("120-500 Hz"), [("120", "500", "Hz")])

    def test_values_evidence_needs_more_than_a_part_name(self):
        for thin in ("kick", "drop", "the kick hits", "the bass", None):
            self.assertFalse(rubric.values_evidence(thin), thin)
        for solid in ("high-passed around 100 Hz", "mono below the crossover", "sub sits at 45 hertz", "ducked hard from the kick"):
            self.assertTrue(rubric.values_evidence(solid), solid)

    def test_song_context_stays_under_the_cap(self):
        spec = spec_from(sections=[section("drop", summary="x")])
        spec["sections"][0]["transcriptText"] = "word " * 40000
        for _ in range(4):
            spec["sections"].append(dict(spec["sections"][0], id=f"s-{_}"))
        context = song_context(spec, "a prompt", limit=24000)
        self.assertLessEqual(len(json.dumps(context)), 24000)
        self.assertEqual(context["sections"][0]["id"], "s-drop")


class ModelOffTests(PinnedEnvironment):
    def test_off_and_unreachable_give_the_rule_output(self):
        spec = spec_from(
            sourcePrompt="A big future bass track at 118 BPM",
            sections=[section("drop", roles=["lead"], summary="the drop hits hard")],
        )
        plain = fill_in_blanks(spec, prompt="future bass", assist=off())
        # Every question fails with a server error: the model is on but useless.
        broken = fill_in_blanks(spec, prompt="future bass", assist=make_assist({
            name: 400 for name in ("style", "name-sections", "describe-sections", "section-additions", "coverage", "gap-text", "decision-reasons")
        }))
        self.assertFalse(plain["ai"]["used"])
        self.assertEqual(plain["ai"]["note"], "AI off for this run")
        self.assertFalse(broken["ai"]["used"])
        self.assertTrue(broken["ai"]["dropped"], "every failed question is written down")
        plain.pop("ai")
        broken.pop("ai")
        self.assertEqual(plain, broken, "a failing model must leave the output exactly as the rules made it")

    def test_note_counts_the_questions_that_were_answered(self):
        spec = spec_from(
            sourcePrompt="A big future bass track at 118 BPM",
            sections=[section("drop", roles=["lead"], summary="the drop hits hard")],
        )
        answers = {name: 400 for name in ("style", "name-sections", "describe-sections", "section-additions", "gap-text", "decision-reasons")}
        answers["coverage"] = {"requirements": []}
        calls = []
        enriched = fill_in_blanks(spec, prompt="future bass", assist=make_assist(answers, calls))
        asked = len(calls)
        self.assertGreater(asked, 1)
        self.assertTrue(enriched["ai"]["used"])
        note = enriched["ai"]["note"]
        self.assertRegex(note, rf"^answered 1 of {asked} questions; .+")
        self.assertIn("simulated", note, "the last failure is still named")
        self.assertIn("AI: via", render_markdown(enriched))

    def test_default_assist_reads_the_environment(self):
        # No assist passed: the tool builds one from the environment, which is
        # pinned off here because other suites in a discovery run pop NEON_AI.
        previous = os.environ.get("NEON_AI")
        os.environ["NEON_AI"] = "off"
        try:
            enriched = fill_in_blanks(spec_from(sections=[section("drop")]))
        finally:
            if previous is None:
                os.environ.pop("NEON_AI", None)
            else:
                os.environ["NEON_AI"] = previous
        self.assertFalse(enriched["ai"]["used"])
        self.assertIn("NEON_AI=off", enriched["ai"]["note"])

    def test_markdown_says_offline(self):
        text = render_markdown(fill_in_blanks(spec_from(sections=[section("drop")]), assist=off()))
        self.assertIn("AI: offline rules", text)


class StyleProposalTests(PinnedEnvironment):
    def spec(self):
        return spec_from(
            sourcePrompt="A moody deep house groove, rolling at 118 bpm in F sharp minor, with a filtered piano.",
            sections=[section("drop", roles=["lead", "chords"], summary="the piano hook lands")],
        )

    def test_a_valid_proposal_sets_lane_tempo_key_progression_and_targets(self):
        calls = []
        assist = make_assist({"style": {
            "styleLane": "house_pop", "genreLabel": "deep house", "tempo": 118, "key": "f# minor",
            "progression": ["F#m", "D", "A", "E"], "mixTargets": ["kick and sub locked", "piano sits mid-width"],
            "evidence": "rolling at 118 bpm in F sharp minor", "reason": "The notes say deep house at 118.", "confidence": "high",
        }}, calls)
        enriched = fill_in_blanks(self.spec(), prompt="deep house", assist=assist)
        fill = enriched["fillInBlanks"]
        self.assertEqual(fill["styleLane"], "house_pop")
        self.assertEqual(fill["genreLabel"], "deep house")
        self.assertEqual(enriched["tempoHint"], 118)
        self.assertEqual(enriched["keyHints"], ["F# minor"])
        self.assertEqual(fill["mixTargets"], ["kick and sub locked", "piano sits mid-width"])
        drop = next(s for s in enriched["sections"] if s["type"] == "drop")
        self.assertEqual(drop["laneEvents"]["chords"]["progressionSymbols"], ["F#m", "D", "A", "E"])
        self.assertEqual(drop["laneEvents"]["chords"]["source"], "model")
        tempo = next(d for d in fill["decisions"] if d["area"] == "tempo")
        self.assertEqual(tempo["source"], "model")
        self.assertEqual(tempo["confidence"], "high", "a quote that is in the notes earns the model's confidence")
        self.assertEqual(tempo["evidence"], "rolling at 118 bpm in F sharp minor")
        self.assertEqual(tempo["reason"], "The notes say deep house at 118.")
        self.assertTrue(enriched["ai"]["used"])
        self.assertEqual(len(prompts_for(calls, "style")), 1)

    def test_invalid_values_fall_back_to_the_tables_field_by_field(self):
        assist = make_assist({"style": {
            "styleLane": "lofi_beats", "tempo": 300, "key": "purple", "progression": ["Em", "Q#7"],
            "mixTargets": ["only one"], "evidence": None, "reason": "?", "confidence": "high",
        }})
        spec = spec_from(sourcePrompt="A big future bass track", sections=[section("drop", roles=["chords"])])
        enriched = fill_in_blanks(spec, prompt="future bass", assist=assist)
        fill = enriched["fillInBlanks"]
        self.assertEqual(fill["styleLane"], "bright_future_bass", "the keyword rule decides the lane")
        self.assertEqual(enriched["tempoHint"], 142)
        self.assertEqual(enriched["keyHints"], ["E minor"])
        self.assertEqual(fill["mixTargets"], ["wide chords", "clean sidechain", "bright but non-brittle lead"])
        drop = next(s for s in enriched["sections"] if s["type"] == "drop")
        self.assertEqual(drop["laneEvents"]["chords"]["progressionSymbols"], ["Em7", "Cmaj7", "Gadd9", "Dadd9"])
        self.assertEqual(drop["laneEvents"]["chords"]["source"], "fill_in_blanks")
        dropped = " ".join(enriched["ai"]["dropped"])
        for word in ("lofi_beats", "300", "purple", "progression"):
            self.assertIn(word, dropped)
        tempo = next(d for d in fill["decisions"] if d["area"] == "tempo")
        self.assertEqual(tempo["source"], "fill_in_blanks")

    def test_unquotable_evidence_keeps_the_values_at_low_confidence(self):
        assist = make_assist({"style": {
            "styleLane": "house_pop", "tempo": 124, "key": "C major", "progression": ["C", "G", "Am", "F"],
            "evidence": "we are at 124 in C", "reason": "house", "confidence": "high",
        }})
        enriched = fill_in_blanks(self.spec(), prompt="house", assist=assist)
        tempo = next(d for d in enriched["fillInBlanks"]["decisions"] if d["area"] == "tempo")
        self.assertEqual(tempo["source"], "model")
        self.assertEqual(tempo["confidence"], "low")
        self.assertNotIn("evidence", tempo)
        self.assertTrue(any("evidence quote is not in the notes" in d for d in enriched["ai"]["dropped"]))

    def test_each_value_needs_its_own_words_in_the_quote(self):
        # One quote comes back for the whole answer; "around 78 bpm" says
        # nothing about the key, so only the tempo earns the model's confidence.
        spec = spec_from(sourcePrompt="A lazy lo-fi beat around 78 bpm with dusty piano.", sections=[section("verse", roles=["chords"])])
        assist = make_assist({"style": {
            "styleLane": "modern_edm", "genreLabel": "lo-fi hip hop", "tempo": 78, "key": "C major",
            "progression": ["Cmaj7", "Am7", "Dm7", "G7"], "evidence": "around 78 bpm", "reason": "lo-fi", "confidence": "high",
        }})
        enriched = fill_in_blanks(spec, prompt="lo-fi", assist=assist)
        decisions = enriched["fillInBlanks"]["decisions"]
        self.assertEqual(next(d for d in decisions if d["area"] == "tempo")["confidence"], "high")
        self.assertEqual(next(d for d in decisions if d["area"] == "key")["confidence"], "low")
        self.assertEqual(enriched["keyHints"], ["C major"], "the value is still used, only its confidence is held back")

    def test_settled_defaults_are_not_asked_again(self):
        calls = []
        assist = make_assist({"style": {"styleLane": "dark_bass", "tempo": 150, "key": "E minor"}}, calls)
        spec = self.spec()
        spec["tempoHint"] = 118
        spec["keyHints"] = ["F# minor"]
        spec["fillInBlanks"] = {"styleLane": "house_pop", "mixTargets": ["x", "y"], "gaps": [], "decisions": []}
        enriched = fill_in_blanks(spec, prompt="deep house", assist=assist)
        self.assertEqual(prompts_for(calls, "style"), [])
        self.assertEqual(enriched["fillInBlanks"]["styleLane"], "house_pop")
        self.assertEqual(enriched["tempoHint"], 118)

    def test_a_stated_tempo_is_never_overwritten(self):
        assist = make_assist({"style": {"styleLane": "house_pop", "tempo": 124, "key": "C major"}})
        spec = self.spec()
        spec["tempoHint"] = 96
        enriched = fill_in_blanks(spec, prompt="house", assist=assist)
        self.assertEqual(enriched["tempoHint"], 96)


class SectionNamingTests(PinnedEnvironment):
    def test_the_model_places_an_unplaced_paragraph_from_its_words(self):
        notes = section("production_notes", roles=["chords"])
        notes["id"] = "notes-1"
        notes["transcriptText"] = "In the breakdown I keep only the piano and let the reverb tail hang."
        spec = spec_from(sections=[section("intro", roles=["chords"]), section("drop", roles=["lead", "kick"]), notes])
        assist = make_assist({"name-sections": {"sections": [
            {"id": "notes-1", "type": "break", "label": "Piano Breakdown", "reason": "It says 'in the breakdown I keep only the piano'."},
            {"id": "notes-99", "type": "drop", "label": "?", "reason": "?"},
        ]}})
        enriched = fill_in_blanks(spec, prompt="future bass", assist=assist)
        placed = [s for s in enriched["sections"] if s.get("rescuedBy") == "model"]
        self.assertEqual(len(placed), 1)
        self.assertEqual(placed[0]["type"], "break")
        self.assertEqual(placed[0]["label"], "Piano Breakdown")
        decision = next(d for d in enriched["fillInBlanks"]["decisions"] if d["detail"].startswith("Placed 1"))
        self.assertEqual(decision["source"], "model")
        self.assertIn("in the breakdown", decision["reason"])
        self.assertTrue(any("notes-99" in d for d in enriched["ai"]["dropped"]))

    def test_an_unknown_type_falls_back_to_the_role_rule(self):
        notes = section("production_notes", roles=["kick", "bass", "lead"])
        notes["id"] = "notes-1"
        spec = spec_from(sections=[section("intro", roles=["chords"]), notes])
        assist = make_assist({"name-sections": {"sections": [{"id": "notes-1", "type": "chorus", "label": "x", "reason": "x"}]}})
        enriched = fill_in_blanks(spec, prompt="future bass", assist=assist)
        rescued = [s for s in enriched["sections"] if s.get("rescued")]
        self.assertEqual(len(rescued), 1)
        self.assertEqual(rescued[0]["type"], "drop", "drums + low + melodic is the rule's drop")
        self.assertNotIn("rescuedBy", rescued[0])

    def test_commentary_stays_production_notes(self):
        notes = section("production_notes", roles=["bass"])
        notes["id"] = "notes-1"
        spec = spec_from(sections=[section("intro", roles=["chords"]), section("drop", roles=["lead", "kick"]), notes])
        assist = make_assist({"name-sections": {"sections": [{"id": "notes-1", "type": "production_notes", "label": "", "reason": "It is about the whole track."}]}})
        enriched = fill_in_blanks(spec, prompt="future bass", assist=assist)
        self.assertFalse([s for s in enriched["sections"] if s.get("rescued")])


class InferredSectionTests(PinnedEnvironment):
    def test_inferred_sections_get_song_specific_summaries(self):
        calls = []

        def describe(text):
            ids = re.search(r"Inferred section ids: (.*)$", text, re.MULTILINE).group(1).split(", ")
            intro = ids[0]
            return {"sections": [
                {"id": intro, "label": "Piano Intro", "summary": "Filtered piano states the hook before the drums arrive.",
                 "fillReason": "The notes describe a piano hook that needs a first hearing.", "addRoles": ["chords", "piano"], "addTechniques": ["filtering", "autotune"]},
                {"id": "section-99", "label": "?", "summary": "not a real section", "fillReason": "?"},
            ]}

        assist = make_assist({"describe-sections": describe}, calls)
        spec = spec_from(sourcePrompt="a piano-led future bass tune", sections=[section("drop", roles=["lead"], summary="the piano hook")])
        enriched = fill_in_blanks(spec, prompt="future bass", assist=assist)
        intro = next(s for s in enriched["sections"] if s["type"] == "intro")
        self.assertTrue(intro["inferred"])
        self.assertEqual(intro["summary"], "Filtered piano states the hook before the drums arrive.")
        self.assertEqual(intro["excerpt"], intro["summary"])
        self.assertEqual(intro["label"], "Piano Intro")
        self.assertEqual(intro["summarySource"], "model")
        self.assertIn("chords", intro["trackRoles"])
        self.assertNotIn("piano", intro["trackRoles"])
        self.assertNotIn("autotune", intro["techniques"])
        build = next(s for s in enriched["sections"] if s["type"] == "build")
        self.assertTrue(build["summary"].startswith("Inferred"), "sections the model did not describe keep the table text")
        described = next(d for d in enriched["fillInBlanks"]["decisions"] if d["detail"].startswith("Described"))
        self.assertEqual(described["source"], "model")
        self.assertIn("Piano Intro", described["reason"])
        dropped = " ".join(enriched["ai"]["dropped"])
        self.assertIn("piano", dropped)
        self.assertIn("section-99", dropped)
        self.assertEqual(len(prompts_for(calls, "describe-sections")), 1)

    def test_a_described_section_is_not_described_again(self):
        calls = []
        assist = make_assist({"describe-sections": {"sections": []}}, calls)
        first = fill_in_blanks(spec_from(sections=[section("drop")]), prompt="future bass", assist=assist)
        for item in first["sections"]:
            if item.get("inferred"):
                item["summarySource"] = "model"
        fill_in_blanks(first, prompt="future bass", assist=assist)
        self.assertEqual(len(prompts_for(calls, "describe-sections")), 1)


class SectionAdditionTests(PinnedEnvironment):
    def test_additions_are_validated_and_carry_the_models_reason(self):
        calls = []

        def additions(text):
            context = json_after(text, "Song:\n")
            drop = next(s for s in context["sections"] if s["type"] == "drop")
            return {"sections": [
                {"id": drop["id"], "addRoles": ["vocal", "kazoo"], "addTechniques": ["distortion", "autotune"], "reason": "The notes want a gritty vocal chop over the drop."},
                {"id": "nope", "addRoles": ["lead"], "addTechniques": [], "reason": "x"},
            ]}

        assist = make_assist({"section-additions": additions}, calls)
        spec = spec_from(sections=[section("drop", roles=["lead"], summary="gritty vocal chop over the drop")])
        enriched = fill_in_blanks(spec, prompt="future bass", assist=assist)
        drop = next(s for s in enriched["sections"] if s["type"] == "drop")
        self.assertIn("vocal", drop["trackRoles"])
        self.assertNotIn("kazoo", drop["trackRoles"])
        self.assertIn("distortion", drop["techniques"])
        self.assertNotIn("autotune", drop["techniques"])
        decisions = enriched["fillInBlanks"]["decisions"]
        added = next(d for d in decisions if d["area"] == "techniques" and "distortion" in d["detail"] and d["source"] == "model")
        self.assertEqual(added["reason"], "The notes want a gritty vocal chop over the drop.")
        table = [d for d in decisions if d["area"] == "track roles" and d["source"] == "fill_in_blanks"]
        self.assertTrue(table, "the per-type table still fills the rest")
        dropped = " ".join(enriched["ai"]["dropped"])
        self.assertIn("kazoo", dropped)
        self.assertIn("autotune", dropped)
        self.assertIn("nope", dropped)
        self.assertEqual(len(prompts_for(calls, "section-additions")), 1, "one call over every section")


class CoverageJudgeTests(PinnedEnvironment):
    def notes_spec(self, note):
        return spec_from(
            mixNotes=[note],
            sections=[section("intro", roles=["chords"]), section("build", roles=["drums"]), section("drop", roles=["lead", "kick", "bass", "sub", "chords", "fx", "riser", "noise", "crash"])],
        )

    def test_a_quoted_verdict_hides_the_gap_and_is_recorded(self):
        # No keyword in texture_bed's regex matches this sentence; only reading it does.
        spec = self.notes_spec("A soft rain recording runs under everything at about 5 percent.")
        assist = make_assist({"coverage": {"requirements": [
            {"id": "texture_bed", "covered": True, "quote": "soft rain recording runs under everything", "reason": "That is a texture bed."},
        ]}})
        plain = fill_in_blanks(spec, prompt="future bass", assist=off())
        judged = fill_in_blanks(spec, prompt="future bass", assist=assist)
        self.assertIn("texture_bed", [g["id"] for g in plain["fillInBlanks"]["gaps"]])
        self.assertNotIn("texture_bed", [g["id"] for g in judged["fillInBlanks"]["gaps"]])
        covered = judged["fillInBlanks"]["authorCovered"]
        self.assertEqual(covered, [{"id": "texture_bed", "quote": "soft rain recording runs under everything", "source": "model"}])
        self.assertIn("Already Covered By The Author", render_markdown(judged))

    def test_covered_without_a_real_quote_is_dropped(self):
        spec = self.notes_spec("A soft rain recording runs under everything.")
        assist = make_assist({"coverage": {"requirements": [
            {"id": "texture_bed", "covered": True, "quote": "vinyl crackle everywhere", "reason": "?"},
            {"id": "no_such_requirement", "covered": True, "quote": "soft rain", "reason": "?"},
        ]}})
        judged = fill_in_blanks(spec, prompt="future bass", assist=assist)
        self.assertIn("texture_bed", [g["id"] for g in judged["fillInBlanks"]["gaps"]])
        self.assertNotIn("authorCovered", judged["fillInBlanks"])
        dropped = " ".join(judged["ai"]["dropped"])
        self.assertIn("texture_bed marked covered without a quote", dropped)
        self.assertIn("no_such_requirement", dropped)

    def test_a_value_requirement_is_not_covered_by_a_part_name(self):
        # Nothing here says who owns the low end in the rule's words, so the
        # keyword rule reports the gap. The model may only hide it with words
        # that actually set something: "kick" is in the notes, but says nothing.
        spec = self.notes_spec("The kick hits hard and the sub sits at 45 hertz, nothing else that low.")
        plain = fill_in_blanks(spec, prompt="future bass", assist=off())
        self.assertIn("low_end_ownership", [g["id"] for g in plain["fillInBlanks"]["gaps"]])
        thin = fill_in_blanks(spec, prompt="future bass", assist=make_assist({"coverage": {"requirements": [
            {"id": "low_end_ownership", "covered": True, "quote": "kick", "reason": "The kick is mentioned."},
        ]}}))
        self.assertIn("low_end_ownership", [g["id"] for g in thin["fillInBlanks"]["gaps"]])
        self.assertNotIn("authorCovered", thin["fillInBlanks"])
        self.assertTrue(any("low_end_ownership asks for values" in note for note in thin["ai"]["dropped"]), thin["ai"]["dropped"])
        solid = fill_in_blanks(spec, prompt="future bass", assist=make_assist({"coverage": {"requirements": [
            {"id": "low_end_ownership", "covered": True, "quote": "the sub sits at 45 hertz", "reason": "The sub owns the bottom."},
        ]}}))
        self.assertNotIn("low_end_ownership", [g["id"] for g in solid["fillInBlanks"]["gaps"]])
        self.assertEqual(solid["fillInBlanks"]["authorCovered"][0]["quote"], "the sub sits at 45 hertz")

    def test_the_model_can_overturn_a_keyword_match_but_not_structure(self):
        # "once" trips single_use_ear_candy's regex; the sentence is not about ear candy.
        spec = self.notes_spec("Once the drop hits, keep everything pumping.")
        spec["sections"] += [section("break", roles=["chords"]), section("second_drop", roles=["lead"]), section("outro", roles=["chords"])]
        assist = make_assist({"coverage": {"requirements": [
            {"id": "single_use_ear_candy", "covered": False, "quote": None, "reason": "'Once the drop hits' is about timing, not a one-off sound."},
            {"id": "contrast_before_repeat", "covered": False, "quote": None, "reason": "?"},
            {"id": "arrangement_length", "covered": False, "quote": None, "reason": "?"},
        ]}})
        plain = fill_in_blanks(spec, prompt="future bass", assist=off())
        judged = fill_in_blanks(spec, prompt="future bass", assist=assist)
        plain_ids = [g["id"] for g in plain["fillInBlanks"]["gaps"]]
        judged_ids = [g["id"] for g in judged["fillInBlanks"]["gaps"]]
        self.assertNotIn("single_use_ear_candy", plain_ids, "the keyword rule is fooled by 'once'")
        self.assertIn("single_use_ear_candy", judged_ids, "the model read the sentence and overturned it")
        candy = next(g for g in judged["fillInBlanks"]["gaps"] if g["id"] == "single_use_ear_candy")
        self.assertEqual(candy["source"], "model")
        self.assertIn("about timing", candy["evidence"])
        # Structure is not up for debate: a break sits between the drops and there are six sections.
        self.assertNotIn("contrast_before_repeat", judged_ids)
        self.assertNotIn("arrangement_length", judged_ids)

    def test_structural_requirements_are_never_put_to_the_model(self):
        # roles_need_content reads lane events, not words: a spec with a role
        # that plays nothing has the gap however convincingly a quote is offered.
        calls = []
        spec = spec_from(mixNotes=["lead: D5@1/0.5*0.9, A4@1.5/0.25*0.75"], sections=[section("drop", roles=["lead", "guitar"])])
        assist = make_assist({"coverage": {"requirements": [
            {"id": "roles_need_content", "covered": True, "quote": "D5@1/0.5*0.9", "reason": "events are written out"},
        ]}}, calls)
        judged = fill_in_blanks(spec, prompt="future bass", assist=assist)
        self.assertIn("roles_need_content", [g["id"] for g in judged["fillInBlanks"]["gaps"]])
        self.assertNotIn("authorCovered", judged["fillInBlanks"])
        for text in prompts_for(calls, "coverage"):
            for structural in ("roles_need_content", "arrangement_length", "contrast_before_repeat", "per_bar_drum_variation"):
                self.assertNotIn(f'"id": "{structural}"', text, f"{structural} is structural and should not be asked about")
        self.assertTrue(any("unknown requirement 'roles_need_content'" in d for d in judged["ai"]["dropped"]))

    def test_long_notes_are_chunked_into_several_calls(self):
        calls = []
        long_note = ("The pad is wide and the kick is tight. " * 1400).strip()  # ~55k chars
        spec = self.notes_spec(long_note)
        assist = make_assist({"coverage": {"requirements": []}}, calls)
        fill_in_blanks(spec, prompt="future bass", assist=assist)
        coverage = prompts_for(calls, "coverage")
        self.assertGreaterEqual(len(coverage), 3)
        for text in coverage:
            self.assertIn("Notes (part", text)
            chunk = re.search(r"Notes \(part \d+ of \d+\):\n(.*?)\n\nReturn only", text, re.DOTALL).group(1)
            self.assertLessEqual(len(chunk), 24000, "the notes are chunked to the contract's cap")

    def test_find_gaps_without_a_judge_is_unchanged(self):
        spec = self.notes_spec("Once the drop hits, keep everything pumping.")
        self.assertEqual(
            [g.id for g in rubric.find_gaps(spec, "bright_future_bass")],
            [g.id for g in rubric.find_gaps(spec, "bright_future_bass", judge=None)],
        )


class GapTextTests(PinnedEnvironment):
    def test_steps_are_rewritten_for_this_song_with_sane_numbers(self):
        calls = []

        def gap_text(text):
            return {"gaps": [
                {"id": "hpf_ladder", "step": "In the Drop, high-pass the supersaw chords at 180 Hz and the lead at 220 Hz so the sub owns the bottom at 142 BPM.", "why": "This song stacks wide chords under the lead, which is exactly where mud builds.", "confidence": "high"},
                {"id": "gain_ladder", "step": "Put the hats at -70 dB under the kick and the sub at +20 dB.", "why": "Because the drop needs weight and a clear top end for this song.", "confidence": "medium"},
                {"id": "no_such_gap", "step": "x" * 40, "why": "y" * 30, "confidence": "low"},
            ]}

        assist = make_assist({"gap-text": gap_text}, calls)
        spec = spec_from(sourcePrompt="wide supersaw chords under the lead", sections=[section("drop", roles=["lead", "chords", "sub", "bass", "kick"])])
        enriched = fill_in_blanks(spec, prompt="future bass", assist=assist)
        by_id = {g["id"]: g for g in enriched["fillInBlanks"]["gaps"]}
        hpf = by_id["hpf_ladder"]
        self.assertTrue(hpf["step"].startswith("In the Drop, high-pass"))
        self.assertEqual(hpf["source"], "model")
        self.assertEqual(hpf["confidence"], "high")
        self.assertEqual(hpf["soundCheckArea"], "Low mids", "area is not the model's to change")
        self.assertEqual(hpf["roles"], list(rubric.requirement_by_id("hpf_ladder").roles))
        gain = by_id["gain_ladder"]
        self.assertEqual(gain["step"], rubric.requirement_by_id("gain_ladder").step, "an implausible number keeps the catalogue wording")
        self.assertEqual(gain["source"], "rubric")
        dropped = " ".join(enriched["ai"]["dropped"])
        self.assertIn("gain_ladder used an implausible number", dropped)
        self.assertIn("no_such_gap", dropped)
        # The gap's decision carries the rewritten text and the model source.
        decision = next(d for d in enriched["fillInBlanks"]["decisions"] if d.get("requirementId") == "hpf_ladder")
        self.assertEqual(decision["source"], "model")
        self.assertTrue(decision["detail"].startswith("In the Drop"))
        self.assertLessEqual(len(prompts_for(calls, "gap-text")), 3, "gaps go out in batches of twelve, not one call each")

    def test_model_text_outranks_catalogue_text_once_then_holds(self):
        def gap(source, confidence="medium", step="do the thing"):
            return rubric.Gap(id="a", label="a", why="because it matters here", step=step, area="none", confidence=confidence, source=source)

        table = merge_gaps([], [gap("rubric")])
        upgraded = merge_gaps(table, [gap("model", step="do the thing, for this song")])
        self.assertEqual(upgraded[0]["step"], "do the thing, for this song")
        held = merge_gaps(upgraded, [gap("model", step="a different wording")])
        self.assertEqual(held[0]["step"], "do the thing, for this song", "two model answers tie; the stored one stays")
        measured = merge_gaps(held, [gap("sound-check", confidence="measured", step="measured")])
        self.assertEqual(measured[0]["step"], "measured")
        self.assertEqual(merge_gaps(measured, [gap("model", step="later")])[0]["step"], "measured")


class DecisionReasonTests(PinnedEnvironment):
    def test_reasons_are_rewritten_with_verified_evidence(self):
        calls = []

        def reasons(text):
            items = json_after(text, "Decisions:\n")
            out = []
            for item in items:
                if item["area"] == "tempo":
                    out.append({"index": item["index"], "reason": "The notes never state a BPM, but 'a lazy head-nod groove' at half-time sits around 142.", "evidence": "a lazy head-nod groove", "confidence": "medium"})
                elif item["area"] == "key":
                    out.append({"index": item["index"], "reason": "The tutorial names the key outright.", "evidence": "the tutorial says D major", "confidence": "high"})
                elif item["area"] == "arrangement" and "outro" in item["detail"]:
                    out.append({"index": item["index"], "reason": "The walkthrough stops at the drop, so the song needs a way out that this one does not describe.", "evidence": None, "confidence": "high"})
            out.append({"index": 999, "reason": "nothing here", "evidence": None, "confidence": "low"})
            return {"decisions": out}

        assist = make_assist({"decision-reasons": reasons}, calls)
        spec = spec_from(sourcePrompt="future bass with a lazy head-nod groove", sections=[section("drop", roles=["lead"])])
        enriched = fill_in_blanks(spec, prompt="future bass", assist=assist)
        decisions = enriched["fillInBlanks"]["decisions"]
        tempo = next(d for d in decisions if d["area"] == "tempo")
        self.assertEqual(tempo["source"], "model")
        self.assertEqual(tempo["confidence"], "medium")
        self.assertEqual(tempo["evidence"], "a lazy head-nod groove")
        self.assertIn("head-nod", tempo["reason"])
        key = next(d for d in decisions if d["area"] == "key")
        self.assertEqual(key["source"], "fill_in_blanks", "a quote that is not in the notes keeps the rule's reason")
        self.assertEqual(key["confidence"], "low")
        outro = next(d for d in decisions if d["area"] == "arrangement" and "outro" in d["detail"])
        self.assertEqual(outro["source"], "model")
        self.assertEqual(outro["confidence"], "medium", "no evidence: the rule's confidence is kept")
        self.assertNotIn("evidence", outro)
        dropped = " ".join(enriched["ai"]["dropped"])
        self.assertIn("999", dropped)
        self.assertIn("not in the notes", dropped)
        self.assertEqual(len(prompts_for(calls, "decision-reasons")), 1)
        self.assertIn("_(model)_", render_markdown(enriched))

    def test_rerun_does_not_stack_reworded_decisions(self):
        assist = make_assist({"decision-reasons": lambda text: {"decisions": [
            {"index": item["index"], "reason": f"Because this song ({len(text)}).", "evidence": None, "confidence": "low"}
            for item in json_after(text, "Decisions:\n")
        ]}})
        spec = spec_from(sections=[section("drop", roles=["lead"])])
        once = fill_in_blanks(spec, prompt="future bass", assist=assist)
        twice = fill_in_blanks(deepcopy(once), prompt="future bass", assist=assist)
        keys = lambda run: [(d["area"], d["detail"]) for d in run["fillInBlanks"]["decisions"]]  # noqa: E731
        self.assertEqual(len(keys(twice)), len(set(keys(twice))), "no decision appears twice with different wording")
        self.assertEqual(
            [g["id"] for g in once["fillInBlanks"]["gaps"]],
            [g["id"] for g in twice["fillInBlanks"]["gaps"]],
        )


class CliTests(PinnedEnvironment):
    def test_ai_flag(self):
        args = build_parser().parse_args(["--input-json", "x.json", "--ai", "off"])
        self.assertEqual(args.ai, "off")
        self.assertEqual(build_parser().parse_args(["--input-json", "x.json"]).ai, "auto")
        assist = llm.assist_from_args(args)
        self.assertFalse(assist.available)


if __name__ == "__main__":
    unittest.main()
