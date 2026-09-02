#!/usr/bin/env python3
"""Tests for the model-backed transcript ingest.

Nothing here touches the network: every model answer comes from a fake
transport injected through ``llm.Client(transport=...)``, and every test runs
with the model switched off in the environment (set in setUp, restored in
tearDown - never at import time) so a real key on the machine cannot leak in.

Run with:  NEON_AI=off /usr/bin/python3 -m unittest tools/test_ingest_ai.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import llm  # noqa: E402
import ingest_transcript as ingest  # noqa: E402

NO_ENV = {"NEON_CONFIG_DIR": "/nonexistent"}

TRANSCRIPT = "\n".join([
    "0:10 hey everyone today we are going to go over how I made my song night drive so let's get into it",
    "0:30 so it starts out with this pad and I put Serum on it and what I did was layer it with a pluck",
    "1:00 then the build comes in with a riser and the hats go to eighth notes and that is about it",
    "1:30 the drop has the same melody from the intro but filled in and the kick is on one and three with the snare on two and four",
    "2:00 and for the mix I put OTT on the lead and that's it for the drop",
    "2:30 also the whole thing is at one forty two by the way and it's in F sharp minor",
])


class ModelOffCase(unittest.TestCase):
    """The deterministic path must be what runs whenever a test does not inject
    a fake - even on a machine that has a real key file. The switch is set per
    test and restored afterwards so it cannot leak into another module."""

    OFF_ENV = {"NEON_AI": "off", "NEON_CONFIG_DIR": "/nonexistent"}

    def setUp(self) -> None:
        super().setUp()
        self._saved_env = {name: os.environ.get(name) for name in self.OFF_ENV}
        os.environ.update(self.OFF_ENV)

    def tearDown(self) -> None:
        for name, value in self._saved_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        super().tearDown()


def fake_transport(answers: dict, calls: list | None = None):
    """A Gemini-shaped transport that routes on the ``# question:`` marker the
    tool puts at the top of every task, and records what was asked."""
    def transport(url, headers, body, timeout):
        assert "generateContent" in url
        assert headers.get("x-goog-api-key") == "k"
        prompt = body["contents"][0]["parts"][0]["text"]
        question = prompt.splitlines()[0].replace("# question:", "").strip()
        if calls is not None:
            calls.append((question, prompt))
        answer = answers.get(question)
        if callable(answer):
            answer = answer(prompt)
        if answer is None:
            return 200, json.dumps({"candidates": [{"content": {"parts": [{"text": "{}"}]}, "finishReason": "STOP"}]})
        return 200, json.dumps({"candidates": [{"content": {"parts": [{"text": json.dumps(answer)}]}, "finishReason": "STOP"}]})
    return transport


def fake_assist(answers: dict, calls: list | None = None) -> llm.Assist:
    client = llm.Client("gemini", api_key="k", transport=fake_transport(answers, calls), use_cache=False, env={**NO_ENV})
    return llm.Assist(client=client)


def off() -> llm.Assist:
    return llm.Assist(enabled=False)


SEGMENTATION = {
    "sections": [
        {"type": "production_notes", "label": "Welcome", "ordinalWithinType": 1, "segmentIndices": [1], "summary": "greets and names the song", "confidence": 0.9},
        {"type": "intro", "label": "Intro", "ordinalWithinType": 1, "segmentIndices": [2], "summary": "pad and pluck", "confidence": 0.9},
        {"type": "build", "label": "Build", "ordinalWithinType": 1, "segmentIndices": [3], "summary": "riser and hats", "confidence": 0.8},
        {"type": "drop", "label": "Drop 1", "ordinalWithinType": 1, "segmentIndices": [4, 5], "summary": "the drop", "confidence": 0.9},
        # invalid: unknown type, out-of-range index, an index already used
        {"type": "chorus", "label": "Chorus", "ordinalWithinType": 1, "segmentIndices": [6], "summary": "x", "confidence": 0.9},
        {"type": "outro", "label": "Outro", "ordinalWithinType": 1, "segmentIndices": [99, 4], "summary": "x", "confidence": 0.9},
        # segment 6 is left out on purpose: it must attach to the section before it
    ]
}


class OffPathTests(ModelOffCase):
    def test_off_reports_and_keeps_shape(self) -> None:
        spec = ingest.analyze_transcript(TRANSCRIPT, "night-drive", assist=off())
        self.assertEqual(spec["ai"]["used"], False)
        self.assertEqual(spec["ai"]["note"], "AI off for this run")
        self.assertEqual(spec["ai"]["questions"], 0)
        self.assertEqual(spec["ai"]["decisions"], [])
        for key in ("schemaVersion", "projectId", "titleHint", "tempoHint", "keyHints", "sections", "globalTracks",
                    "globalPlugins", "globalTechniques", "arrangementNotes", "mixNotes", "automationNotes",
                    "coverageChecklist", "openQuestions", "derivedPrompt", "artistHint", "genreHint"):
            self.assertIn(key, spec)
        self.assertIsNone(spec["tempoHint"])  # 'one forty two' is not a regex hit
        self.assertEqual(spec["keyHints"], [])
        self.assertEqual(spec["titleHint"], "Night Drive")
        for section in spec["sections"]:
            self.assertNotIn("source", section)
            self.assertNotIn("evidence", section)

    def test_environment_off_matches_explicit_off(self) -> None:
        # No assist passed: analyze_transcript builds one from the environment,
        # which this test process has switched off.
        from_env = ingest.analyze_transcript(TRANSCRIPT, "night-drive")
        explicit = ingest.analyze_transcript(TRANSCRIPT, "night-drive", assist=off())
        self.assertEqual(from_env["ai"]["used"], False)
        self.assertEqual({k: v for k, v in from_env.items() if k != "ai"}, {k: v for k, v in explicit.items() if k != "ai"})

    def test_model_nonsense_falls_back_to_the_heuristic(self) -> None:
        # Every question gets an empty object back: nothing validates, so the
        # result is the deterministic one, and the ai block says the model was
        # consulted but produced nothing usable.
        calls: list = []
        spec = ingest.analyze_transcript(TRANSCRIPT, "night-drive", assist=fake_assist({}, calls))
        base = ingest.analyze_transcript(TRANSCRIPT, "night-drive", assist=off())
        self.assertEqual({k: v for k, v in spec.items() if k != "ai"}, {k: v for k, v in base.items() if k != "ai"})
        self.assertGreaterEqual(spec["ai"]["questions"], 5)
        self.assertEqual({question for question, _ in calls}, {"segmentation", "tags", "globals", "lanes", "notes"})


class KeywordBoundaryTests(ModelOffCase):
    def test_common_words_no_longer_tag_instruments(self) -> None:
        self.assertEqual(ingest.extract_matches("and that is what I did, fairly subtle, with pride", ingest.TRACK_KEYWORDS), [])
        self.assertEqual(ingest.extract_matches("a tiny hi-hat, and the 808s, plus an arp", ingest.TRACK_KEYWORDS), ["hat", "pluck", "sub"])
        self.assertIn("hat", ingest.extract_matches("Hats: 1.5,2.5", ingest.TRACK_KEYWORDS))
        self.assertEqual(ingest.extract_matches("dropped the ball on stage", ingest.TRACK_KEYWORDS), [])

    def test_technique_boundaries(self) -> None:
        self.assertEqual(ingest.extract_matches("the frequencies were equal", ingest.TECHNIQUE_KEYWORDS), [])
        self.assertEqual(ingest.extract_matches("some EQ and a sidechain", ingest.TECHNIQUE_KEYWORDS), ["eq", "sidechain"])


class SegmentationTests(ModelOffCase):
    def test_model_sections_are_validated_and_rebuilt(self) -> None:
        spec = ingest.analyze_transcript(TRANSCRIPT, "night-drive", assist=fake_assist({"segmentation": SEGMENTATION}))
        sections = spec["sections"]
        self.assertEqual([s["type"] for s in sections], ["production_notes", "intro", "build", "drop"])
        self.assertEqual([s["label"] for s in sections], ["Welcome", "Intro", "Build", "Drop 1"])
        self.assertEqual([s["ordinalWithinType"] for s in sections], [1, 1, 1, 1])
        # segment 6 (the tempo line) was left out by the model and attaches to the drop
        self.assertEqual(sections[3]["sourceSegmentCount"], 3)
        self.assertIn("one forty two", sections[3]["transcriptText"])
        self.assertEqual(sections[3]["timecodeStart"], "1:30")
        self.assertEqual(sections[3]["timecodeEnd"], "2:30")
        self.assertEqual(sections[3]["source"], "model")
        self.assertEqual(sections[3]["reason"], "the drop")
        self.assertTrue(any(d["field"] == "sections" and d["source"] == "model" for d in spec["ai"]["decisions"]))
        notes = " ".join(spec["ai"]["notes"])
        self.assertIn("not one of", notes)          # 'chorus' dropped
        self.assertIn("out of range or used twice", notes)
        self.assertIn("left out", notes)
        # the standard shape is intact for the rest of the pipeline
        for key in ("id", "type", "label", "startSeconds", "endSeconds", "timecodeStart", "timecodeEnd", "summary",
                    "excerpt", "transcriptText", "sourceSegmentCount", "trackRoles", "plugins", "techniques", "ordinalWithinType"):
            self.assertIn(key, sections[0])

    def test_interleaved_indices_are_repaired_into_contiguous_runs(self) -> None:
        # intro=[2,4] and build=[3] would give an intro whose time range wraps
        # around the build: the intro keeps its longest run and segment 4 goes
        # to the section before it, the build.
        answers = {"segmentation": {"sections": [
            {"type": "production_notes", "label": "Welcome", "segmentIndices": [1], "summary": "hi"},
            {"type": "intro", "label": "Intro", "segmentIndices": [2, 4], "summary": "pad"},
            {"type": "build", "label": "Build", "segmentIndices": [3], "summary": "riser"},
            {"type": "drop", "label": "Drop", "segmentIndices": [5, 6], "summary": "drop"},
        ]}}
        spec = ingest.analyze_transcript(TRANSCRIPT, "night-drive", assist=fake_assist(answers))
        sections = spec["sections"]
        self.assertEqual([s["type"] for s in sections], ["production_notes", "intro", "build", "drop"])
        self.assertEqual([s["sourceSegmentCount"] for s in sections], [1, 1, 2, 2])
        self.assertIn("filled in", sections[2]["transcriptText"])   # segment 4 re-attached to the build
        starts = [s["startSeconds"] for s in sections]
        ends = [s["endSeconds"] for s in sections]
        self.assertEqual(starts, sorted(starts))
        self.assertTrue(all(ends[i] <= starts[i + 1] for i in range(len(sections) - 1)), "no section's time range overlaps the next")
        self.assertIn("not one unbroken run", " ".join(spec["ai"]["notes"]))

    def test_sections_out_of_transcript_order_are_reordered(self) -> None:
        answers = {"segmentation": {"sections": [
            {"type": "drop", "label": "Drop", "segmentIndices": [4, 5, 6], "summary": "drop"},
            {"type": "build", "label": "Build", "segmentIndices": [3], "summary": "riser"},
            {"type": "intro", "label": "Intro", "segmentIndices": [1, 2], "summary": "pad"},
        ]}}
        spec = ingest.analyze_transcript(TRANSCRIPT, "night-drive", assist=fake_assist(answers))
        self.assertEqual([s["type"] for s in spec["sections"]], ["intro", "build", "drop"])
        self.assertEqual([s["timecodeStart"] for s in spec["sections"]], ["0:10", "1:00", "1:30"])
        self.assertIn("not in transcript order", " ".join(spec["ai"]["notes"]))

    def test_contiguous_runs(self) -> None:
        self.assertEqual(ingest.contiguous_runs([6, 1, 3, 4, 4]), [[1], [3, 4], [6]])
        self.assertEqual(ingest.contiguous_runs([]), [])

    def test_long_transcripts_are_chunked(self) -> None:
        long_text = "\n".join(f"{i // 60}:{i % 60:02d} segment number {i} talks about the drop for a while " + ("blah " * 60) for i in range(1, 200))
        calls: list = []
        spec = ingest.analyze_transcript(long_text, "long", assist=fake_assist({}, calls))
        segmentation_calls = [prompt for question, prompt in calls if question == "segmentation"]
        self.assertGreaterEqual(len(segmentation_calls), 2)
        for prompt in segmentation_calls:
            self.assertLess(len(prompt), ingest.TEXT_CHUNK_CHARS + 3000)
        self.assertEqual(spec["segmentCount"], 199)


class TagTests(ModelOffCase):
    def test_tags_need_quotes_from_the_section(self) -> None:
        answers = {
            "segmentation": SEGMENTATION,
            "tags": {"sections": [
                {"id": "section-02", "trackRoles": [
                    {"name": "pad", "quote": "starts out with this pad"},
                    {"name": "pluck", "quote": "layer it with a pluck"},
                    {"name": "hat", "quote": "tinky little hi-hat"},          # not in this section
                    {"name": "theremin", "quote": "starts out with this pad"},  # not a known role
                ], "plugins": [
                    {"name": "serum", "quote": "I put Serum on it"},
                    {"name": "Vital", "quote": "I put Serum on it"},            # unknown plugin not named in its quote
                    {"name": "Omnisphere", "quote": "Omnisphere everywhere"},   # quote not in text
                ], "techniques": [
                    {"name": "layering", "quote": "layer it with a pluck"},
                    {"name": "sidechain", "quote": "starts out with this pad"},  # valid quote, wrong claim: kept (the quote exists)
                    {"name": "ott", "quote": "starts out"},                      # not a technique name
                ]},
                {"id": "section-04", "trackRoles": [], "plugins": [], "techniques": []},
                {"id": "section-99", "trackRoles": [{"name": "kick", "quote": "kick"}], "plugins": [], "techniques": []},
            ]},
        }
        spec = ingest.analyze_transcript(TRANSCRIPT, "night-drive", assist=fake_assist(answers))
        intro = spec["sections"][1]
        self.assertEqual(intro["trackRoles"], ["pad", "pluck"])
        self.assertEqual(intro["plugins"], ["Serum"])
        self.assertEqual(intro["techniques"], ["layering", "sidechain"])
        self.assertEqual(intro["tagSource"], "model")
        self.assertEqual(intro["evidence"]["Serum"], "I put Serum on it")
        # the drop was answered with empty lists: the model's call, not the keywords
        drop = spec["sections"][3]
        self.assertEqual(drop["trackRoles"], [])
        self.assertEqual(drop["plugins"], [])
        # sections the model did not answer keep their keyword tags
        build = spec["sections"][2]
        self.assertNotIn("tagSource", build)
        self.assertIn("hat", build["trackRoles"])
        self.assertIn("riser", build["trackRoles"])
        # globals are recomputed from the validated tags
        self.assertEqual([item["name"] for item in spec["globalPlugins"]], ["Serum"])
        notes = " ".join(spec["ai"]["notes"])
        self.assertIn("quote was not in the section text", notes)
        self.assertIn("outside the known role/technique lists", notes)


class GlobalsTests(ModelOffCase):
    def test_tempo_key_title_with_evidence(self) -> None:
        answers = {"globals": {
            "tempoBpm": 142, "tempoEvidence": "the whole thing is at one forty two", "tempoConfidence": 0.9,
            "key": "F sharp minor", "keyEvidence": "it's in F sharp minor", "keyConfidence": 0.8,
            "title": "Night Drive", "titleEvidence": "how I made my song night drive", "titleConfidence": 0.9,
            "artist": "Marshmello", "artistEvidence": "made by Marshmello",  # not in the text
            "genre": "future bass", "genreEvidence": "the drop has the same melody", "genreConfidence": 0.7,
        }}
        spec = ingest.analyze_transcript(TRANSCRIPT, "night-drive", assist=fake_assist(answers))
        self.assertEqual(spec["tempoHint"], 142)
        self.assertEqual(spec["keyHints"], ["F# minor"])
        self.assertIsNone(spec["artistHint"])
        self.assertEqual(spec["genreHint"], "future bass")
        self.assertNotIn("Transcript does not explicitly state a BPM.", spec["openQuestions"])
        self.assertNotIn("Transcript does not clearly state the key.", spec["openQuestions"])
        decisions = {d["field"]: d for d in spec["ai"]["decisions"]}
        self.assertEqual(decisions["tempoHint"]["evidence"], "the whole thing is at one forty two")
        self.assertEqual(decisions["tempoHint"]["source"], "model")
        self.assertEqual(decisions["keyHints"]["value"], ["F# minor"])
        self.assertIn("dropped artist", " ".join(spec["ai"]["notes"]))
        # the title came from the regex (two words), so the model's is not recorded
        self.assertNotIn("titleHint", decisions)

    def test_tempo_is_clamped_and_needs_a_number_in_the_evidence(self) -> None:
        answers = {"globals": {"tempoBpm": 300, "tempoEvidence": "the whole thing is at one forty two", "tempoConfidence": 0.9}}
        spec = ingest.analyze_transcript(TRANSCRIPT, "night-drive", assist=fake_assist(answers))
        self.assertEqual(spec["tempoHint"], 220)
        answers = {"globals": {"tempoBpm": 140, "tempoEvidence": "so let's get into it", "tempoConfidence": 0.9}}
        spec = ingest.analyze_transcript(TRANSCRIPT, "night-drive", assist=fake_assist(answers))
        self.assertIsNone(spec["tempoHint"])
        answers = {"globals": {"tempoBpm": 142, "tempoEvidence": "the whole thing is at one forty two", "tempoConfidence": 0.2}}
        spec = ingest.analyze_transcript(TRANSCRIPT, "night-drive", assist=fake_assist(answers))
        self.assertIsNone(spec["tempoHint"])

    def test_tempo_evidence_must_carry_a_real_number(self) -> None:
        for quote in ("the whole thing is at one forty two", "a hundred and twenty", "one hundred and forty bpm",
                      "it sits at 128", "ninety", "eighty-five bpm", "one twenty", "two twenty", "one oh five", "one ten"):
            self.assertTrue(ingest.evidence_states_number(quote), quote)
        for quote in ("one", "double the tempo", "half time feel", "one two three four", "so let's get into it",
                      "the first one", "two of them", "forty", "hundred", None, 142):
            self.assertFalse(ingest.evidence_states_number(quote), repr(quote))
        # through the tool: 'double' alone in a real quote from the text is not a number
        text = TRANSCRIPT + "\n3:00 then I double the tempo feel in the second half"
        answers = {"globals": {"tempoBpm": 140, "tempoEvidence": "double the tempo feel", "tempoConfidence": 0.9}}
        spec = ingest.analyze_transcript(text, "night-drive", assist=fake_assist(answers))
        self.assertIsNone(spec["tempoHint"])
        self.assertIn("does not state a number", " ".join(spec["ai"]["notes"]))

    def test_regex_tempo_and_key_win_over_the_model(self) -> None:
        text = TRANSCRIPT + "\n3:00 for the record it is 150 bpm in D major"
        answers = {"globals": {"tempoBpm": 142, "tempoEvidence": "at one forty two", "tempoConfidence": 0.9,
                               "key": "F# minor", "keyEvidence": "F sharp minor", "keyConfidence": 0.9}}
        spec = ingest.analyze_transcript(text, "night-drive", assist=fake_assist(answers))
        self.assertEqual(spec["tempoHint"], 150)
        self.assertEqual(spec["keyHints"], ["D major"])

    def test_key_normalisation(self) -> None:
        self.assertEqual(ingest.normalize_key_hint("F sharp minor"), "F# minor")
        self.assertEqual(ingest.normalize_key_hint("f#m"), "F# minor")
        self.assertEqual(ingest.normalize_key_hint("Gb Major"), "Gb major")
        self.assertEqual(ingest.normalize_key_hint("the key of C"), "C major")
        self.assertEqual(ingest.normalize_key_hint("D♭ min"), "Db minor")
        self.assertIsNone(ingest.normalize_key_hint("H minor"))
        self.assertIsNone(ingest.normalize_key_hint("dorian"))
        self.assertIsNone(ingest.normalize_key_hint(142))

    def test_title_from_model_when_regexes_fail(self) -> None:
        text = TRANSCRIPT.replace("how I made my song night drive", "this one's called night drive")
        answers = {"globals": {"title": "night drive", "titleEvidence": "this one's called night drive", "titleConfidence": 0.9}}
        spec = ingest.analyze_transcript(text, "night-drive", assist=fake_assist(answers))
        self.assertEqual(spec["titleHint"], "Night Drive")
        self.assertTrue(any(d["field"] == "titleHint" for d in spec["ai"]["decisions"]))
        answers = {"globals": {"title": "Alone", "titleEvidence": "so let's get into it", "titleConfidence": 0.9}}
        spec = ingest.analyze_transcript(text, "night-drive", assist=fake_assist(answers))
        self.assertEqual(spec["titleHint"], "Night Drive")  # project-id fallback, model title not named in its evidence


class LaneTests(ModelOffCase):
    def test_transforms_and_patterns_in_materializer_shapes(self) -> None:
        answers = {
            "segmentation": SEGMENTATION,
            "lanes": {"sections": [
                {"id": "section-04", "laneTransforms": {
                    "lead": {"copyFromSectionId": "section-02", "transform": "fill_in", "transposeSemitones": 12, "quote": "the same melody from the intro but filled in"},
                    "chords": {"copyFromSectionId": "section-07", "quote": "the same melody"},   # later/unknown section: no copyFrom, nothing left -> dropped
                    "bass": {"followChords": True, "omitBeats": [4], "quote": "the kick is on one and three"},
                    "drums": {"hatSpacing": 0.24, "ride": True, "quote": "not in the text"},
                }, "drumPatterns": {
                    "kick": {"beats": [1, 3], "quote": "the kick is on one and three"},
                    "snare": {"beats": [2, 4, 9], "quote": "snare on two and four"},
                    "hat": {"spacingBeats": 0.5, "quote": "the kick is on one and three"},
                    "crash": {"beats": [1], "quote": "crash everywhere"},
                }},
                {"id": "section-03", "laneTransforms": {"drums": {"hatSpacing": 0.55, "quote": "the hats go to eighth notes"}}},
            ]},
        }
        spec = ingest.analyze_transcript(TRANSCRIPT, "night-drive", assist=fake_assist(answers))
        drop = spec["sections"][3]
        transforms = drop["laneTransforms"]
        # the regex already found 'same melody from the intro' + 'filled in'; the model adds the transpose
        self.assertEqual(transforms["lead"]["copyFrom"], {"sectionId": "section-02", "sectionType": "intro", "ordinal": 1})
        self.assertEqual(transforms["lead"]["transform"], "fill_in")
        self.assertEqual(transforms["lead"]["transposeSemitones"], 12)
        self.assertEqual(transforms["lead"]["source"], "natural_language+model")  # regex found the copy, the model added the transpose
        self.assertIn("filled in", transforms["lead"]["reason"])
        self.assertNotIn("chords", transforms)
        self.assertEqual(transforms["bass"], {"followChords": True, "omitBeats": [3.0], "source": "model",
                                              "reason": 'stated in the transcript: "the kick is on one and three"'})
        self.assertNotIn("drums", transforms)
        lanes = drop["laneEvents"]
        # 'on one and three' has no digits, so the regex found nothing and the
        # model's spoken-number reading fills kick and snare (beat 9 dropped)
        self.assertEqual(lanes["kick"]["source"], "model")
        self.assertEqual([e["beat"] for e in lanes["kick"]["events"]], [0.0, 2.0])
        self.assertEqual(lanes["kick"]["kind"], "beatPattern")
        self.assertEqual([e["beat"] for e in lanes["snare"]["events"]], [1.0, 3.0])
        # the model fills the hat lane from spacing alone
        self.assertEqual(lanes["hat"]["source"], "model")
        self.assertEqual([e["beat"] for e in lanes["hat"]["events"]], [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5])
        self.assertEqual(lanes["hat"]["spacingBeats"], 0.5)
        self.assertNotIn("crash", lanes)
        build = spec["sections"][2]
        self.assertEqual(build["laneTransforms"]["drums"]["overrides"], {"hatSpacing": 0.5})
        fields = {d["field"] for d in spec["ai"]["decisions"]}
        self.assertIn("laneTransforms.bass", fields)
        self.assertIn("laneEvents.hat", fields)
        self.assertNotIn("laneTransforms.lead", fields)  # merged into a regex hit, not a fresh decision

    def test_regex_pattern_wins_over_the_model(self) -> None:
        text = TRANSCRIPT.replace("the kick is on one and three", "the kick is on 1 and 3")
        answers = {"lanes": {"sections": [{"id": s, "drumPatterns": {"kick": {"beats": [2, 4], "quote": "the kick is on 1 and 3"}}}
                                          for s in ("section-01", "section-02", "section-03", "section-04", "section-05", "section-06")]}}
        spec = ingest.analyze_transcript(text, "night-drive", assist=fake_assist(answers))
        drop = next(s for s in spec["sections"] if "kick is on 1" in s["transcriptText"])
        self.assertEqual(drop["laneEvents"]["kick"]["source"], "natural_language")
        self.assertEqual([e["beat"] for e in drop["laneEvents"]["kick"]["events"]], [0.0, 2.0])
        self.assertIn("already had a pattern", " ".join(spec["ai"]["notes"]))

    def test_model_beats_are_one_based(self) -> None:
        self.assertEqual(ingest._model_beats([1, 1.5, 4.5, 5, 0, "2"]), [0.0, 0.5, 1.0, 3.5])
        self.assertEqual(ingest._model_beats("nope"), [])


class NotesTests(ModelOffCase):
    def test_notes_and_prompt_are_validated(self) -> None:
        answers = {"notes": {
            "arrangementNotes": ["Intro is a filtered pad"] + [f"note {i}" for i in range(20)] + [5, None],
            "mixNotes": ["OTT on the lead", "OTT on the lead"],
            "automationNotes": [],
            "derivedPrompt": "An original future-bass track at 142 BPM in F# minor: pad intro, riser build, a filled-in drop with OTT on the lead.",
            "styleLane": "future bass",
            "mood": ["euphoric", "night", 3],
        }}
        spec = ingest.analyze_transcript(TRANSCRIPT, "night-drive", assist=fake_assist(answers))
        self.assertEqual(len(spec["arrangementNotes"]), 10)
        self.assertEqual(spec["mixNotes"], ["OTT on the lead"])
        self.assertTrue(spec["automationNotes"])  # empty from the model: the keyword lines stay
        self.assertTrue(spec["derivedPrompt"].startswith("An original future-bass track"))
        decisions = {d["field"]: d for d in spec["ai"]["decisions"]}
        self.assertEqual(decisions["styleLane"]["value"], "future bass")
        self.assertEqual(decisions["mood"]["value"], ["euphoric", "night"])
        self.assertTrue(spec["ai"]["used"])
        self.assertEqual(spec["ai"]["provider"], "gemini")

    def test_short_prompt_is_ignored(self) -> None:
        spec = ingest.analyze_transcript(TRANSCRIPT, "night-drive", assist=fake_assist({"notes": {"derivedPrompt": "meh"}}))
        self.assertTrue(spec["derivedPrompt"].startswith("Convert the production walkthrough"))


class QuotaTests(ModelOffCase):
    """The adapter owns waiting (it honours short "retry in" replies and trips
    a breaker on long ones); the tool never sleeps. What the tool does is stop
    asking once the adapter says the model is over its quota."""

    QUIET_ENV = {**NO_ENV, "NEON_AI_FALLBACK_MODEL": "off"}

    def setUp(self) -> None:
        super().setUp()
        self.slept: list = []
        self._real_sleep = llm.time.sleep
        llm.time.sleep = lambda seconds: self.slept.append(seconds)

    def tearDown(self) -> None:
        llm.time.sleep = self._real_sleep
        llm._BREAKER.pop("gemini/quota-test-model", None)
        super().tearDown()

    def client(self, transport) -> llm.Client:
        return llm.Client("gemini", "quota-test-model", api_key="k", transport=transport, use_cache=False, env=dict(self.QUIET_ENV))

    def test_the_tool_has_no_sleep_of_its_own(self) -> None:
        self.assertFalse(hasattr(ingest, "time"))
        self.assertFalse(hasattr(ingest, "rate_limit_wait"))

    def test_quota_notes_are_recognised_and_nothing_else_is(self) -> None:
        self.assertTrue(ingest.quota_exhausted("quota-test-model is over its quota (asked to wait 500 s); using the built-in rules for now"))
        self.assertTrue(ingest.quota_exhausted("quota-test-model is over its quota; not asking again for 42 s"))
        # a retired model's 404 mentions 'generateContent' ('rate' is inside it): not a quota
        self.assertFalse(ingest.quota_exhausted("gemini 404: models/gemini-1.5-flash is not supported for generateContent"))
        self.assertFalse(ingest.quota_exhausted("retryable gemini 429: Quota exceeded. Please retry in 3s."))
        self.assertFalse(ingest.quota_exhausted("reply was not JSON (no JSON in reply)"))
        self.assertFalse(ingest.quota_exhausted(""))

    def test_short_waits_are_the_adapters_business(self) -> None:
        attempts: list = []

        def transport(url, headers, body, timeout):
            attempts.append(1)
            if len(attempts) <= 2:
                return 429, json.dumps({"error": {"message": "Quota exceeded. Please retry in 3.2s."}})
            return 200, json.dumps({"candidates": [{"content": {"parts": [{"text": json.dumps({"tempoBpm": 142, "tempoEvidence": "at one forty two", "tempoConfidence": 0.9})}]}}]})

        ai = ingest.IngestAssist(llm.Assist(client=self.client(transport)))
        answer = ai.ask("globals", "task", schema={})
        self.assertEqual(answer["tempoBpm"], 142)
        self.assertEqual(self.slept, [3.2, 3.2], "the adapter waited exactly what the server asked; the tool added nothing")
        self.assertEqual(ai.questions, 1)
        self.assertFalse(ai.exhausted)
        self.assertEqual(ai.notes, [])

    def test_a_long_wait_skips_the_remaining_questions_without_sleeping(self) -> None:
        attempts: list = []

        def transport(url, headers, body, timeout):
            attempts.append(1)
            return 429, json.dumps({"error": {"message": "Quota exceeded. Please retry in 500s."}})

        ai = ingest.IngestAssist(llm.Assist(client=self.client(transport)))
        self.assertIsNone(ai.ask("tags", "task", schema={}))
        self.assertEqual(self.slept, [], "a wait that long is never slept")
        self.assertEqual(len(attempts), 1)
        self.assertTrue(ai.exhausted)
        self.assertFalse(ai.available)
        self.assertTrue(ai.notes[0].startswith("tags: quota-test-model is over its quota"))
        self.assertTrue(ai.notes[0].endswith("heuristic result kept"))
        self.assertIn("model over its quota for this key; the remaining questions were not asked", ai.notes)
        self.assertIsNone(ai.ask("lanes", "task", schema={}))
        self.assertEqual(ai.questions, 1)
        self.assertEqual(len(attempts), 1)
        self.assertFalse(ai.report()["used"])
        # the breaker the adapter tripped stops a fresh handle on the same model too
        again = ingest.IngestAssist(llm.Assist(client=self.client(transport)))
        self.assertIsNone(again.ask("globals", "task", schema={}))
        self.assertTrue(again.exhausted)
        self.assertIn("not asking again", again.notes[0])
        self.assertEqual(len(attempts), 1)

    def test_a_retired_model_is_not_mistaken_for_a_quota(self) -> None:
        attempts: list = []

        def transport(url, headers, body, timeout):
            attempts.append(1)
            return 404, json.dumps({"error": {"message": "models/quota-test-model is not found for API version v1beta, or is not supported for generateContent."}})

        ai = ingest.IngestAssist(llm.Assist(client=self.client(transport)))
        self.assertIsNone(ai.ask("tags", "task", schema={}))
        self.assertIsNone(ai.ask("lanes", "task", schema={}))
        self.assertEqual(self.slept, [])
        self.assertEqual(len(attempts), 2, "the next question is still asked: this is not a quota")
        self.assertFalse(ai.exhausted)
        self.assertEqual(ai.questions, 2)
        self.assertTrue(ai.notes[0].startswith("tags: gemini 404"))


class ChunkMergeTests(ModelOffCase):
    def group(self, section_type, label, **extra):
        base = {"sectionId": section_type, "label": label, "texts": ["t"], "timecodes": ["0:01"], "startSeconds": 1,
                "endSeconds": 1, "trackRoles": [], "plugins": [], "techniques": [], "source": "model"}
        base.update(extra)
        return base

    def test_same_section_split_by_a_chunk_boundary_is_folded(self) -> None:
        merged = ingest.merge_groups_across_chunks([self.group("drop", "Drop"), self.group("drop", "Drop 1", chunkStart=True)])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["texts"], ["t", "t"])

    def test_adjacent_sections_inside_a_chunk_stay_separate(self) -> None:
        merged = ingest.merge_groups_across_chunks([self.group("drop", "Drop 1"), self.group("drop", "Drop 2")])
        self.assertEqual(len(merged), 2)

    def test_different_ordinals_across_the_boundary_stay_separate(self) -> None:
        merged = ingest.merge_groups_across_chunks([self.group("drop", "Drop 1"), self.group("drop", "Second Drop", chunkStart=True)])
        self.assertEqual(len(merged), 2)
        merged = ingest.merge_groups_across_chunks([self.group("production_notes", "Production Notes"), self.group("production_notes", "Production Notes", chunkStart=True)])
        self.assertEqual(len(merged), 2)


class CliTests(ModelOffCase):
    def test_ai_off_flag_and_markdown_line(self) -> None:
        env = {**os.environ, "NEON_AI": "auto", "NEON_CONFIG_DIR": "/nonexistent", "GEMINI_API_KEY": "", "ANTHROPIC_API_KEY": ""}
        result = subprocess.run(
            [sys.executable, str(TOOLS / "ingest_transcript.py"), "--project-id", "Night Drive", "--transcript-text", TRANSCRIPT, "--ai", "off"],
            capture_output=True, text=True, check=False, env=env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        spec = json.loads(result.stdout)
        self.assertEqual(spec["ai"], {"used": False, "provider": None, "model": None, "note": "AI off for this run",
                                      "questions": 0, "modelCalls": 0, "notes": [], "decisions": []})
        self.assertIn("- AI: `offline rules` (AI off for this run)", ingest.render_markdown(spec))

    def test_no_key_says_so(self) -> None:
        env = {**os.environ, "NEON_AI": "auto", "NEON_CONFIG_DIR": "/nonexistent", "GEMINI_API_KEY": "", "ANTHROPIC_API_KEY": "", "GOOGLE_API_KEY": ""}
        result = subprocess.run(
            [sys.executable, str(TOOLS / "ingest_transcript.py"), "--project-id", "night-drive", "--transcript-text", TRANSCRIPT],
            capture_output=True, text=True, check=False, env=env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        spec = json.loads(result.stdout)
        self.assertFalse(spec["ai"]["used"])
        self.assertIn("no API key", spec["ai"]["note"])


if __name__ == "__main__":
    unittest.main()
