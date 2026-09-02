#!/usr/bin/env python3
"""Tests for the musical plan a model can hand the materializer.

Nothing here touches the network: every model answer comes from a fake
transport injected through llm.Client, and the process runs with the model off
so a real key on the machine can never leak in. The renderer template is never
loaded from disk with a model in the loop except to check that the plan reached
it and that the emitted file is repeatable.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import llm  # noqa: E402
import project_materializer as pm  # noqa: E402

NO_ENV = {"NEON_CONFIG_DIR": "/nonexistent"}


def section(id_: str, kind: str, label: str, bars: int, summary: str, roles: list[str], techniques: list[str] | None = None, **extra):
    item = {"id": id_, "type": kind, "label": label, "bars": bars, "summary": summary, "trackRoles": roles, "plugins": [], "techniques": techniques or []}
    item.update(extra)
    return item


SPEC = {
    "projectId": "plan-test",
    "titleHint": "Plan Test",
    "tempoHint": 140,
    "keyHints": ["E minor"],
    "sourcePrompt": "dark melodic trap tune with wide drops",
    "sections": [
        section("s1", "intro", "Intro", 4, "soft intro", ["chords", "lead"]),
        section("s2", "drop", "Drop", 4, "big drop", ["drums", "bass", "chords", "lead", "fx", "hat"], ["sidechain"]),
        section("s3", "second_drop", "Second Drop", 4, "second drop, same energy", ["drums", "bass", "chords", "lead"]),
        section("s4", "outro", "Outro", 2, "outro over the stated chords", ["chords"],
                laneEvents={"chords": {"kind": "progressionSymbols", "progressionSymbols": ["Am", "F", "C", "G"]}}),
    ],
    "globalTracks": [{"name": name, "mentions": 1, "sections": []} for name in ("drums", "hat", "bass", "chords", "lead", "fx")],
    "globalPlugins": [],
    "globalTechniques": [],
}

PLAN_REPLY = {
    "tempo": {"bpm": 90, "reason": "ignored, the spec states 140"},
    "key": {"center": "C major", "reason": "ignored, the spec states E minor"},
    "groove": {"swing": 12, "snap": "1/8", "reason": "laid back trap hats"},
    "description": "A dark 140 BPM trap tune in E minor with a wide, sidechained drop.",
    "tracks": {
        "chords": {"name": "Dark Keys", "instrument": "Rhodes"},
        "guitar": {"name": "Nope"},
        "lead": {"instrument": "Whistle Lead"},
    },
    "sections": {
        "s1": {
            "progressionSymbols": ["Em", "C", "G", "D"],
            "progressionReason": "i VI III VII, the classic minor loop",
            "leadMotifKey": "tease",
            "energy": 0.7,
            "fxProfile": {"noiseBed": False, "riser": "yes"},
            "chordEvents": [{"beat": 0, "duration": 3.5}, {"beat": 4.5, "duration": 1}],
        },
        "s2": {
            "drums": {"kicks": [0, 1, 2, 3], "snares": [1, 3], "hats": [0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 7], "hatSpacing": 0.5, "ride": True, "crashBars": [0, 9]},
            "bassEvents": [{"beat": 0, "duration": 0.9}, {"beat": 2, "duration": 0.9}],
            "automation": {"envelopes": [
                {"parameter": "filter", "targetLane": "chords", "start": 0.3, "end": 0.9, "barOffset": 1, "bars": 40, "curve": "exponential"},
                {"parameter": "wobble", "start": 0, "end": 1},
            ]},
            "energy": 1.4,
            "reason": "four on the floor under the drop",
        },
        "s3": {"leadTransposeSemitones": 0, "progressionSymbols": ["Db", "Gb", "Ab", "Bbm"]},
        "s4": {"progressionSymbols": ["Em", "D"]},
        "zz": {"energy": 1.0},
    },
}


class FakeTransport:
    """Answers each call from a list of replies (dicts or raw text) and keeps every prompt."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts: list[str] = []
        self.calls = 0

    def __call__(self, url, headers, body, timeout):
        self.calls += 1
        self.prompts.append(body["contents"][0]["parts"][0]["text"])
        reply = self.replies.pop(0) if self.replies else {}
        text = reply if isinstance(reply, str) else json.dumps(reply)
        return 200, json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}]})


def fake_assist(replies):
    transport = FakeTransport(replies)
    client = llm.Client("gemini", api_key="k", transport=transport, use_cache=False, env=dict(NO_ENV))
    return llm.Assist(client=client), transport


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


def strip_volatile(project: dict) -> dict:
    trimmed = deepcopy(project)
    for key in ("createdAt", "updatedAt", "ai", "materialization"):
        trimmed.pop(key, None)
    return trimmed


def emit(project: dict, spec: dict, name: str):
    tmp = Path(tempfile.mkdtemp(prefix="materializer-ai-"))
    path = pm.ensure_project_renderer(tmp, "plan-test", "Plan Test", project, spec, prompt="plan test", overwrite=True)
    text = path.read_text(encoding="utf-8")
    module_spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[module_spec.name] = module
    module_spec.loader.exec_module(module)
    return module, text


class ModelOffTests(PinnedEnvironment):
    def test_no_assist_is_the_heuristic_with_an_ai_block(self) -> None:
        project = pm.build_project_materialization(SPEC, "plan-test", prompt="plan test")
        self.assertEqual(project["ai"], {"used": False, "provider": None, "model": None, "note": "AI off for this run"})
        self.assertEqual(project["materialization"]["source"], "heuristic")
        self.assertEqual(project["materialization"]["plan"], {})
        self.assertFalse(any(item["section"] == "Musical Plan" for item in project["snapshot"]["recipe"]))
        self.assertEqual(project["snapshot"]["bpm"], 140)
        self.assertEqual(project["snapshot"]["tracks"][3]["name"], "Chords")

    def test_ai_off_matches_no_assist(self) -> None:
        off = pm.build_project_materialization(SPEC, "plan-test", prompt="plan test", assist=llm.Assist(enabled=False))
        none = pm.build_project_materialization(SPEC, "plan-test", prompt="plan test", assist=None)
        self.assertEqual(strip_volatile(off), strip_volatile(none))

    def test_unusable_answer_falls_back_and_says_so(self) -> None:
        assist, transport = fake_assist(["not json", "still not json", "nope"])
        project = pm.build_project_materialization(SPEC, "plan-test", prompt="plan test", assist=assist)
        baseline = pm.build_project_materialization(SPEC, "plan-test", prompt="plan test")
        self.assertEqual(strip_volatile(project), strip_volatile(baseline))
        self.assertFalse(project["ai"]["used"])
        self.assertIn("not JSON", project["ai"]["note"])
        self.assertEqual(project["materialization"]["source"], "heuristic")

    def test_a_list_instead_of_a_plan_is_dropped(self) -> None:
        assist, _ = fake_assist([[1, 2, 3]])
        project = pm.build_project_materialization(SPEC, "plan-test", prompt="plan test", assist=assist)
        self.assertFalse(project["ai"]["used"])
        self.assertIn("wanted dict", project["ai"]["note"])


class PlanValidationTests(PinnedEnvironment):
    @classmethod
    def setUpClass(cls) -> None:
        cls.assist, cls.transport = fake_assist([PLAN_REPLY])
        cls.project = pm.build_project_materialization(SPEC, "plan-test", prompt="plan test", assist=cls.assist)
        cls.plan = cls.project["materialization"]["plan"]
        cls.dropped = cls.project["materialization"]["dropped"]
        cls.section_plan = {s["id"]: s for s in pm.render_section_plan(cls.project, SPEC)}

    def test_one_call_carried_every_section(self) -> None:
        self.assertEqual(self.transport.calls, 1)
        for section_id in ("s1", "s2", "s3", "s4"):
            self.assertIn(f'"id": "{section_id}"', self.transport.prompts[0])
        self.assertIn('"tempoHint": 140', self.transport.prompts[0])

    def test_ai_block_and_sources(self) -> None:
        self.assertTrue(self.project["ai"]["used"])
        self.assertEqual(self.project["ai"]["provider"], "gemini")
        self.assertEqual(self.project["materialization"]["source"], "model")
        decisions = self.project["materialization"]["decisions"]
        self.assertTrue(decisions)
        self.assertTrue(all(item["source"] == "model" for item in decisions))
        plan_steps = [item for item in self.project["snapshot"]["recipe"] if item["section"] == "Musical Plan"]
        self.assertTrue(plan_steps)
        self.assertTrue(all(item["status"] == "inferred" and "(via model)" in item["detail"] for item in plan_steps))

    def test_stated_tempo_and_key_win(self) -> None:
        self.assertNotIn("tempo", self.plan)
        self.assertNotIn("key", self.plan)
        self.assertEqual(self.project["snapshot"]["bpm"], 140)
        self.assertEqual(self.project["keyCenter"], "E Minor")

    def test_groove_and_description(self) -> None:
        self.assertEqual(self.project["snapshot"]["swing"], 12)
        self.assertEqual(self.project["snapshot"]["snap"], "1/8")
        self.assertEqual(self.project["description"], PLAN_REPLY["description"])

    def test_track_names_only_for_lanes_in_the_project(self) -> None:
        tracks = {t["id"]: t for t in self.project["snapshot"]["tracks"]}
        self.assertEqual((tracks["chords"]["name"], tracks["chords"]["instrument"]), ("Dark Keys", "Rhodes"))
        self.assertEqual((tracks["lead"]["name"], tracks["lead"]["instrument"]), ("Lead", "Whistle Lead"))
        self.assertNotIn("guitar", tracks)
        self.assertTrue(any(note.startswith("tracks.guitar") for note in self.dropped))
        # Ids, colours and effect chains are not the model's to change.
        self.assertEqual(tracks["chords"]["color"], pm.TRACK_BLUEPRINTS["chords"].color)
        self.assertEqual([e["name"] for e in tracks["chords"]["effects"]][:2], ["EQ Eight", "Reverb"])

    def test_progression_in_key_lands_through_the_parser(self) -> None:
        defaults = self.section_plan["s1"]["starterDefaults"]
        self.assertEqual([chord["name"] for chord in defaults["progression"]], ["Em", "C", "G", "D"])
        self.assertEqual(defaults["progression"][0]["notes"], pm.chord_symbol_to_shape("Em")["notes"])
        self.assertEqual(self.section_plan["s1"]["laneEvents"]["chords"]["progressionSource"], "model")

    def test_progression_outside_the_key_is_dropped(self) -> None:
        names = [chord["name"] for chord in self.section_plan["s3"]["starterDefaults"]["progression"]]
        self.assertNotIn("Db", names)
        self.assertTrue(any(note.startswith("s3.progressionSymbols") and "outside E minor" in note for note in self.dropped))

    def test_chords_the_producer_named_win(self) -> None:
        self.assertTrue(any(note.startswith("s4.progressionSymbols") for note in self.dropped))
        self.assertNotIn("s4", self.plan["sections"])
        names = [chord["name"] for chord in self.section_plan["s4"]["starterDefaults"]["progression"]]
        self.assertEqual(names, ["Am", "F", "C", "G"])

    def test_lead_motif_energy_fx_and_chord_rhythm(self) -> None:
        defaults = self.section_plan["s1"]["starterDefaults"]
        self.assertEqual(defaults["leadMotifKey"], "tease")
        self.assertEqual(defaults["energy"], 0.7)
        self.assertEqual(defaults["references"]["energySource"], "model")
        self.assertFalse(defaults["fxProfile"]["noiseBed"])   # an intro would default to True
        self.assertFalse(defaults["fxProfile"]["riser"])      # "yes" is not a boolean, so the heuristic stands
        self.assertEqual(defaults["chordEvents"], [{"beat": 0.0, "duration": 3.5}])
        self.assertEqual(defaults["references"]["chordEventSource"], "model")

    def test_drums_land_as_lane_events_the_renderer_plays(self) -> None:
        pattern = self.section_plan["s2"]["starterDefaults"]["drumPattern"]
        self.assertEqual(pattern["kicks"], [0.0, 1.0, 2.0, 3.0])
        self.assertEqual([e["beat"] for e in pattern["eventData"]["kicks"]], [0.0, 1.0, 2.0, 3.0])
        self.assertEqual(pattern["snares"], [1.0, 3.0])
        self.assertEqual(pattern["hats"], [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5])  # the 7 was outside the bar
        self.assertTrue(pattern["ride"])
        self.assertEqual(pattern["crashBars"], [0])  # bar 9 is outside a 4-bar section
        self.assertEqual(self.section_plan["s2"]["laneEvents"]["kick"]["source"], "model")

    def test_bass_rhythm_and_automation(self) -> None:
        defaults = self.section_plan["s2"]["starterDefaults"]
        self.assertEqual(defaults["bassEvents"], [{"beat": 0.0, "duration": 0.9}, {"beat": 2.0, "duration": 0.9}])
        self.assertEqual(defaults["references"]["bassEventSource"], "model")
        self.assertEqual(defaults["energy"], 1.4)
        envelopes = defaults["automationProfile"]["envelopes"]
        self.assertEqual(len(envelopes), 1)  # "wobble" is not a parameter the renderer knows
        self.assertEqual(envelopes[0]["curve"], "exp")
        self.assertEqual(envelopes[0]["bars"], 3)  # 40 bars from bar 1 clamps to the 3 left in the section
        self.assertEqual(envelopes[0]["targetTrackId"], "chords")
        self.assertEqual(defaults["automationProfile"]["source"], "model")

    def test_second_drop_can_keep_its_octave(self) -> None:
        self.assertEqual(self.section_plan["s3"]["starterDefaults"]["leadOctaveShift"], 0)
        baseline = {s["id"]: s for s in pm.render_section_plan(pm.build_project_materialization(SPEC, "plan-test"), SPEC)}
        self.assertEqual(baseline["s3"]["starterDefaults"]["leadOctaveShift"], 12)

    def test_unknown_section_is_dropped(self) -> None:
        self.assertNotIn("zz", self.plan["sections"])
        self.assertTrue(any(note.startswith("sections.zz") for note in self.dropped))

    def test_renderer_is_repeatable_and_carries_the_plan(self) -> None:
        module, text = emit(self.project, SPEC, "render_plan_test_a")
        _module2, text_again = emit(self.project, SPEC, "render_plan_test_b")
        self.assertEqual(text, text_again)
        baseline = pm.build_project_materialization(SPEC, "plan-test", prompt="plan test")
        _module3, heuristic_text = emit(baseline, SPEC, "render_plan_test_c")
        self.assertNotEqual(text, heuristic_text)
        drop = next(dict(s) for s in module.SECTION_PLAN if s["id"] == "s2")
        self.assertEqual(len(module._kick_onsets_for_section(drop)), 4 * drop["bars"])
        self.assertEqual(module.TRACK_PLAN_BY_ID["chords"]["instrument"], "Rhodes")


class TempoKeyAndArrangementTests(PinnedEnvironment):
    def test_tempo_and_key_are_taken_when_the_spec_has_none(self) -> None:
        spec = deepcopy(SPEC)
        spec.pop("tempoHint")
        spec["keyHints"] = []
        assist, _ = fake_assist([{
            "tempo": {"bpm": 90, "reason": "the walkthrough calls it a slow, heavy trap tune"},
            "key": {"center": "F# minor", "reason": "the hook sits on F#"},
            "sections": {
                "s1": {"progressionSymbols": ["F#m", "D", "A", "E"]},
                "s2": {"progressionSymbols": ["C", "F", "Bb", "Eb"]},
            },
        }])
        project = pm.build_project_materialization(spec, "plan-test", prompt="plan test", assist=assist)
        self.assertEqual(project["snapshot"]["bpm"], 90)
        self.assertEqual(project["keyCenter"], "F# Minor")
        plan = project["materialization"]["plan"]
        self.assertEqual(plan["sections"]["s1"]["progressionSymbols"], ["F#m", "D", "A", "E"])
        self.assertNotIn("s2", plan["sections"])
        self.assertTrue(any("outside F# minor" in note for note in project["materialization"]["dropped"]))
        decisions = {item["area"]: item for item in project["materialization"]["decisions"]}
        self.assertEqual(decisions["tempo"]["detail"], "90 BPM")
        self.assertIn("slow", decisions["tempo"]["reason"])

    def test_bad_tempo_and_key_are_dropped(self) -> None:
        spec = deepcopy(SPEC)
        spec.pop("tempoHint")
        spec["keyHints"] = []
        assist, _ = fake_assist([{"tempo": {"bpm": 999}, "key": {"center": "purple"}, "groove": {"swing": 90, "snap": "1/3"}}])
        project = pm.build_project_materialization(spec, "plan-test", prompt="plan test", assist=assist)
        self.assertEqual(project["snapshot"]["bpm"], 142)
        self.assertIsNone(project["keyCenter"])
        self.assertEqual(project["snapshot"]["swing"], 18)
        self.assertEqual(project["snapshot"]["snap"], "1/16")
        dropped = project["materialization"]["dropped"]
        self.assertEqual(len(dropped), 4)

    def test_arrangement_is_proposed_when_the_spec_has_no_sections(self) -> None:
        spec = {"projectId": "lofi", "titleHint": "Rainy Lofi", "sourcePrompt": "lo-fi hip hop, rainy, slow, dusty drums", "sections": [], "globalTracks": []}
        assist, transport = fake_assist([{
            "tempo": {"bpm": 78, "reason": "lo-fi sits around 80"},
            "key": {"center": "D minor"},
            "arrangement": [
                {"id": "section-01", "type": "intro", "label": "Rain In", "bars": 4, "summary": "vinyl noise and filtered keys", "trackRoles": ["chords", "fx"], "techniques": ["filtering"]},
                {"id": "section-02", "type": "verse", "label": "Verse", "bars": 8, "summary": "dusty drums under the keys", "trackRoles": ["drums", "bass", "chords"], "techniques": ["nonsense"]},
                {"id": "section-03", "type": "chorus", "label": "Chorus", "bars": 8, "summary": "not a type the renderer knows", "trackRoles": ["drums"]},
                {"id": "section-04", "type": "drop", "label": "Hook", "bars": 8, "summary": "keys open up", "trackRoles": ["drums", "bass", "chords", "lead", "unicorn"]},
                {"id": "section-05", "type": "outro", "label": "Rain Out", "bars": 4, "summary": "keys fade", "trackRoles": ["chords", "fx"]},
            ],
            "tracks": {"chords": {"name": "Rhodes", "instrument": "Electric Piano"}, "hat-ride": {"name": "Nope"}},
            "sections": {"section-01": {"energy": 0.6}, "section-04": {"drums": {"kicks": [0, 1.5, 2.5], "snares": [1, 3]}}},
        }])
        project = pm.build_project_materialization(spec, "lofi", prompt=spec["sourcePrompt"], assist=assist)
        self.assertEqual(transport.calls, 1)
        self.assertIn('"sectionTypes"', transport.prompts[0])
        plan = project["materialization"]["plan"]
        self.assertEqual([s["type"] for s in plan["arrangement"]], ["intro", "verse", "drop", "outro"])
        self.assertEqual([s["id"] for s in plan["arrangement"]], ["section-01", "section-02", "section-03", "section-04"])
        self.assertEqual(plan["arrangement"][1]["techniques"], [])
        self.assertEqual(plan["arrangement"][2]["trackRoles"], ["drums", "bass", "chords", "lead"])
        # The model's "section-04" was its fourth item, which became the third section.
        self.assertEqual(set(plan["sections"]), {"section-01", "section-03"})
        self.assertEqual(project["snapshot"]["bpm"], 78)
        self.assertEqual(project["keyCenter"], "D Minor")
        track_ids = [t["id"] for t in project["snapshot"]["tracks"]]
        self.assertEqual(track_ids, ["chords", "fx", "drums", "bass", "lead"])
        self.assertEqual(project["snapshot"]["tracks"][0]["name"], "Rhodes")
        self.assertTrue(any(note.startswith("tracks.hat-ride") for note in project["materialization"]["dropped"]))
        clips = [(c["startBar"], c["bars"]) for c in project["snapshot"]["tracks"][0]["clips"]]
        self.assertEqual(clips, [(0, 4), (4, 8), (12, 8), (20, 4)])
        section_plan = {s["id"]: s for s in pm.render_section_plan(project, spec)}
        self.assertEqual(section_plan["section-03"]["starterDefaults"]["drumPattern"]["kicks"], [0.0, 1.5, 2.5])
        self.assertEqual(section_plan["section-01"]["starterDefaults"]["energy"], 0.6)
        recipe_sections = [item["section"] for item in project["snapshot"]["recipe"]]
        self.assertIn("Rain In", recipe_sections)
        self.assertIn("Musical Plan", recipe_sections)

    def test_arrangement_with_too_little_in_it_keeps_the_skeleton(self) -> None:
        spec = {"projectId": "thin", "sections": [], "globalTracks": []}
        assist, _ = fake_assist([{"arrangement": [{"type": "chorus", "bars": 8}]}])
        project = pm.build_project_materialization(spec, "thin", assist=assist)
        self.assertNotIn("arrangement", project["materialization"]["plan"])
        self.assertEqual(len({c["startBar"] for t in project["snapshot"]["tracks"] for c in t["clips"]}), 5)


class KeyWordingTests(PinnedEnvironment):
    def test_key_names_in_words_are_parsed(self) -> None:
        self.assertEqual(pm.parse_key_center("F sharp minor"), (6, "minor", "F# minor"))
        self.assertEqual(pm.parse_key_center("E-flat major"), (3, "major", "Eb major"))
        self.assertEqual(pm.parse_key_center("A min"), (9, "minor", "A minor"))
        self.assertEqual(pm.parse_key_center("Bb maj"), (10, "major", "Bb major"))
        self.assertEqual(pm.parse_key_center("Bm"), (11, "minor", "B minor"))
        self.assertIsNone(pm.parse_key_center("purple"))
        self.assertIsNone(pm.parse_key_center("H minor"))

    def test_a_stated_key_in_words_is_never_replaced_by_the_models(self) -> None:
        spec = deepcopy(SPEC)
        spec["keyHints"] = ["F sharp minor"]
        assist, _ = fake_assist([{
            "key": {"center": "C major", "reason": "must not win"},
            "sections": {"s1": {"progressionSymbols": ["F#m", "D", "A", "E"]}, "s2": {"progressionSymbols": ["C", "F", "Bb", "Eb"]}},
        }])
        project = pm.build_project_materialization(spec, "plan-test", prompt="plan test", assist=assist)
        plan = project["materialization"]["plan"]
        self.assertNotIn("key", plan)
        self.assertEqual(project["keyCenter"], "F Sharp Minor")
        self.assertEqual(plan["sections"]["s1"]["progressionSymbols"], ["F#m", "D", "A", "E"])
        self.assertNotIn("s2", plan["sections"], "the stated key, not the model's, is what progressions are checked against")
        self.assertFalse(any(item["area"] == "key" for item in project["materialization"]["decisions"]))

    def test_a_stated_key_the_parser_cannot_read_still_blocks_the_models(self) -> None:
        spec = deepcopy(SPEC)
        spec["keyHints"] = ["the key of the vocal sample"]
        assist, _ = fake_assist([{"key": {"center": "C major", "reason": "must not win"}}])
        project = pm.build_project_materialization(spec, "plan-test", prompt="plan test", assist=assist)
        self.assertNotIn("key", project["materialization"]["plan"])
        self.assertEqual(project["keyCenter"], "The Key Of The Vocal Sample")


class PlanCleaningTests(PinnedEnvironment):
    def test_beats_are_range_checked_after_rounding(self) -> None:
        # 3.999 rounds to 4.0, which is the next bar's first beat, not this bar's last.
        self.assertEqual(pm._clean_beats([3.999, 0.004, 1.5, 3.99, 4.0, -0.2]), [0.0, 1.5, 3.99])
        self.assertIsNone(pm._clean_beats([3.999, 3.996]))
        events = pm._clean_rhythm_events([{"beat": 3.999, "duration": 1}, {"beat": 1, "duration": 0.001}, {"beat": 2.004, "duration": 0.996}], bars=4, chord_flags=False)
        self.assertEqual(events, [{"beat": 2.0, "duration": 1.0}])

    def test_echoed_track_names_are_not_decisions(self) -> None:
        assist, _ = fake_assist([{"tracks": {
            "chords": {"name": "chords", "instrument": "Rhodes"},
            "lead": {"name": "Lead", "instrument": pm.TRACK_BLUEPRINTS["lead"].instrument},
        }}])
        project = pm.build_project_materialization(SPEC, "plan-test", prompt="plan test", assist=assist)
        self.assertEqual(project["materialization"]["plan"]["tracks"], {"chords": {"instrument": "Rhodes"}})
        track_decisions = [item for item in project["materialization"]["decisions"] if item["area"] == "track"]
        self.assertEqual([item["detail"] for item in track_decisions], ["chords: Chords / Rhodes"])
        tracks = {t["id"]: t for t in project["snapshot"]["tracks"]}
        self.assertEqual(tracks["lead"]["name"], "Lead")
        self.assertEqual(tracks["chords"]["instrument"], "Rhodes")


class WalkthroughWinsTests(PinnedEnvironment):
    def test_pinned_lanes_and_worded_beats_are_not_overridden(self) -> None:
        spec = deepcopy(SPEC)
        spec["sections"][0]["laneEvents"] = {"chords": {"kind": "progressionSymbols", "progressionSymbols": ["Em", "G"], "events": [{"beat": 0.0, "duration": 3.9}]}, "bass": {"events": [{"beat": 0.0, "duration": 1.0}]}}
        spec["sections"][0]["laneTransforms"] = {"lead": {"transposeSemitones": -12, "copyFrom": {"sectionId": "s0"}}, "drums": {"overrides": {"ride": True}}}
        spec["sections"][1]["summary"] = "kick on 1 and 3, snare on 2 and 4"
        assist, transport = fake_assist([{"sections": {
            "s1": {"progressionSymbols": ["Am", "C"], "chordEvents": [{"beat": 1, "duration": 1}], "bassEvents": [{"beat": 1, "duration": 1}], "leadMotifKey": "dense", "leadTransposeSemitones": 7, "drums": {"kicks": [0]}},
            "s2": {"drums": {"kicks": [0, 1, 2, 3]}},
        }}])
        project = pm.build_project_materialization(spec, "plan-test", assist=assist)
        context = llm.extract_json(transport.prompts[0])
        self.assertEqual(context["sections"][0]["alreadyPinned"], ["bass", "chords"])
        self.assertEqual(context["sections"][0]["transforms"], ["drums", "lead"])
        self.assertEqual(project["materialization"]["plan"], {})
        dropped = "\n".join(project["materialization"]["dropped"])
        for field in ("s1.progressionSymbols", "s1.chordEvents", "s1.bassEvents", "s1.leadMotifKey", "s1.leadTransposeSemitones", "s1.drums", "s2.drums"):
            self.assertIn(field, dropped)
        self.assertIn("names drum beats in words", dropped)
        self.assertTrue(project["ai"]["used"])
        self.assertIn("nothing in the answer fit", project["ai"]["note"])


class BatchingTests(PinnedEnvironment):
    def test_many_sections_go_out_in_chunks_of_twenty_five(self) -> None:
        spec = deepcopy(SPEC)
        spec["sections"] = [section(f"sec-{i:02d}", "verse", f"Verse {i}", 2, f"verse number {i}", ["drums", "chords"]) for i in range(60)]

        class EchoTransport(FakeTransport):
            def __call__(self, url, headers, body, timeout):
                self.calls += 1
                text = body["contents"][0]["parts"][0]["text"]
                self.prompts.append(text)
                context = llm.extract_json(text)
                ids = [item["id"] for item in context.get("sections", [])]
                answer = {"sections": {section_id: {"energy": 1.1, "reason": "echo"} for section_id in ids}}
                if "settled" not in context:
                    answer["groove"] = {"swing": 5, "snap": "1/16"}
                return 200, json.dumps({"candidates": [{"content": {"parts": [{"text": json.dumps(answer)}]}}]})

        transport = EchoTransport([])
        client = llm.Client("gemini", api_key="k", transport=transport, use_cache=False, env=dict(NO_ENV))
        project = pm.build_project_materialization(spec, "plan-test", assist=llm.Assist(client=client))
        self.assertEqual(transport.calls, 3)
        for prompt in transport.prompts:
            self.assertLessEqual(len(llm.extract_json(prompt)["sections"]), 25)
        self.assertIn('"settled"', transport.prompts[1])
        self.assertEqual(len(project["materialization"]["plan"]["sections"]), 60)
        self.assertEqual(project["snapshot"]["swing"], 5)

    def test_very_long_summaries_are_chunked_by_size(self) -> None:
        spec = deepcopy(SPEC)
        spec["sections"] = [section(f"sec-{i:02d}", "verse", f"Verse {i}", 2, "words " * 120, ["chords"]) for i in range(40)]
        digests = [pm.plan_section_digest(s) for s in spec["sections"]]
        chunks = pm._chunk_digests(digests, 6000)
        self.assertGreater(len(chunks), 2)
        self.assertEqual(sum(len(chunk) for chunk in chunks), 40)
        for chunk in chunks:
            self.assertLessEqual(len(json.dumps(chunk)), 6000 + 1200)


class CommandLineTests(PinnedEnvironment):
    def test_ai_off_prints_a_report_with_an_ai_block(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="materializer-cli-"))
        spec_path = tmp / "transcript_spec.json"
        spec_path.write_text(json.dumps(SPEC), encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = pm.main([str(spec_path), "--ai", "off", "--out-root", str(tmp / "root"), "--spec-out", str(tmp / "planned.json")])
        self.assertEqual(code, 0)
        report = json.loads(out.getvalue())
        self.assertEqual(report["ai"]["note"], "AI off for this run")
        self.assertEqual(report["projectId"], "plan-test")
        self.assertEqual(report["bpm"], 140)
        self.assertTrue(Path(report["written"]["renderer"]).exists())
        self.assertTrue((tmp / "planned.json").exists())
        self.assertEqual([s["id"] for s in report["sections"]], ["s1", "s2", "s3", "s4"])


if __name__ == "__main__":
    unittest.main()
