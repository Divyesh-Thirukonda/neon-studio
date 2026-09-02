#!/usr/bin/env python3
"""Unit tests for describe_change: each intent lands as the specific edit it promises."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import describe_change as dc  # noqa: E402
import llm  # noqa: E402


class OfflineCase(unittest.TestCase):
    """The deterministic path is what every test exercises unless it injects a fake model.

    A real key may exist on the machine running this, so each test switches the model off for
    its own duration (the CLI tests inherit it through the environment) and never reads the
    config directory. The environment is restored afterwards: nothing here leaks into other
    test modules, and nothing at import time touches os.environ."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ, {"NEON_AI": "off", "NEON_CONFIG_DIR": "/nonexistent", "GEMINI_API_KEY": "", "ANTHROPIC_API_KEY": ""})
        patcher.start()
        self.addCleanup(patcher.stop)


def clip(clip_id: str, name: str, lane: str, start: int, bars: int) -> dict:
    return {"id": clip_id, "name": name, "startBar": start, "bars": bars, "lane": lane, "color": "#ccc", "type": "pattern"}


def sample_project() -> dict:
    """A small arrangement: intro 0-8, build 8-16, drop 16-32, outro 32-40."""
    tracks = [
        {
            "id": "drums", "name": "Drums", "kind": "audio", "file": None, "instrument": "Sampler",
            "color": "#f80", "gain": 0.8, "pan": 0.0, "steps": [0, 4, 8, 12],
            "effects": [{"id": "sc", "name": "Kick Duck", "active": False, "amount": 0.5}],
            "clips": [clip("d-build", "Build roll", "drums", 8, 8), clip("d-drop", "Drop drums", "drums", 16, 16)],
        },
        {
            "id": "bass", "name": "Mid Bass", "kind": "audio", "file": None, "instrument": "Bass",
            "color": "#0f8", "gain": 0.7, "pan": 0.0, "steps": [0, 8],
            "effects": [
                {"id": "sat", "name": "Saturator", "active": True, "amount": 0.4},
                {"id": "sc", "name": "Sidechain", "active": False, "amount": 0.6},
            ],
            "clips": [clip("b-drop", "Drop bass", "bass", 16, 16)],
        },
        {
            "id": "lead", "name": "Hook Lead", "kind": "audio", "file": None, "instrument": "Saw",
            "color": "#08f", "gain": 0.9, "pan": 0.1, "steps": [],
            "effects": [
                {"id": "eq", "name": "Air EQ", "active": False, "amount": 0.4},
                {"id": "verb", "name": "Plate Reverb", "active": True, "amount": 0.3},
                {"id": "wid", "name": "Stereo Width", "active": True, "amount": 0.5},
            ],
            "clips": [clip("l-intro", "Intro hook", "lead", 0, 8), clip("l-drop", "Drop hook", "lead", 16, 16), clip("l-outro", "Outro hook", "lead", 32, 8)],
        },
        {
            "id": "vocals", "name": "Vox Chops", "kind": "audio", "file": None, "instrument": "Sampler",
            "color": "#f0f", "gain": 0.5, "pan": 0.0, "steps": [],
            "effects": [],
            "clips": [clip("v-drop", "Drop vox", "vocals", 16, 16)],
        },
    ]
    return {
        "id": "unit", "name": "Unit", "keyCenter": "E Minor", "updatedAt": "2026-01-01T00:00:00Z",
        "snapshot": {
            "bpm": 140, "swing": 10, "snap": "1/16", "loopEnabled": True, "loopStartBar": 16, "loopEndBar": 32,
            "selectedTrackId": "lead",
            "tracks": tracks,
            "controls": {
                "drums": {"gain": 0.8, "pan": 0.0, "mute": False, "solo": False, "arm": False, "sendA": 0.1, "sendB": 0.05},
                "bass": {"gain": 0.7, "pan": 0.0, "mute": False, "solo": False, "arm": False, "sendA": 0.1, "sendB": 0.05},
                "lead": {"gain": 0.9, "pan": 0.1, "mute": False, "solo": False, "arm": False, "sendA": 0.1, "sendB": 0.05},
                "vocals": {"gain": 0.5, "pan": 0.0, "mute": False, "solo": False, "arm": False, "sendA": 0.1, "sendB": 0.05},
            },
            "notes": [
                {"id": "n1", "beat": 64.0, "duration": 1.0, "note": 64, "velocity": 0.8, "color": "#08f", "trackId": "lead"},
                {"id": "n2", "beat": 65.0, "duration": 1.0, "note": 67, "velocity": 0.8, "color": "#08f", "trackId": "lead"},
                {"id": "n3", "beat": 130.0, "duration": 1.0, "note": 40, "velocity": 0.8, "color": "#0f8", "trackId": "bass"},
            ],
            "automationLanes": [
                {"id": "auto-x", "trackId": "lead", "parameter": "filter", "label": "x", "points": [{"bar": 8, "value": 0.2}, {"bar": 36, "value": 0.9}]},
            ],
            "recipe": [],
        },
    }


def run(request: str, project: dict | None = None) -> tuple[dict, dict]:
    return dc.describe_change(project or sample_project(), request)


def track(project: dict, track_id: str) -> dict:
    return next(t for t in project["snapshot"]["tracks"] if t["id"] == track_id)


def effect(project: dict, track_id: str, name: str) -> dict:
    return next(e for e in track(project, track_id)["effects"] if e["name"] == name)


class SectionsTest(OfflineCase):
    def test_sections_are_clustered_by_bar(self):
        sections = {s.key: (s.start_bar, s.end_bar) for s in dc.project_sections(sample_project())}
        self.assertEqual(sections, {"intro-1": (0, 8), "build-1": (8, 16), "drop-1": (16, 32), "outro-1": (32, 40)})

    def test_second_drop_gets_its_own_ordinal(self):
        project = sample_project()
        track(project, "drums")["clips"].append(clip("d-drop2", "Drop drums again", "drums", 48, 16))
        keys = [s.key for s in dc.project_sections(project)]
        self.assertIn("drop-2", keys)


class GainTest(OfflineCase):
    def test_louder_track_default_two_steps(self):
        report, updated = run("louder drums")
        self.assertAlmostEqual(updated["snapshot"]["controls"]["drums"]["gain"], 0.96)
        self.assertEqual(report["edits"][0]["trackIds"], ["drums"])
        self.assertEqual(report["unresolved"], [])

    def test_quieter_a_bit_is_one_step(self):
        _, updated = run("make the lead a bit quieter")
        self.assertAlmostEqual(updated["snapshot"]["controls"]["lead"]["gain"], 0.82)

    def test_louder_a_lot_is_three_steps_and_clamps(self):
        _, updated = run("make the lead way louder")
        self.assertAlmostEqual(updated["snapshot"]["controls"]["lead"]["gain"], 1.14)
        _, updated = run("make the lead way louder", updated)
        self.assertAlmostEqual(updated["snapshot"]["controls"]["lead"]["gain"], 1.38)
        _, updated = run("make the lead way louder", updated)
        self.assertAlmostEqual(updated["snapshot"]["controls"]["lead"]["gain"], 1.4)

    def test_louder_in_section_records_section(self):
        report, updated = run("louder drums in the drop")
        self.assertEqual(report["edits"][0]["section"], "drop")
        self.assertAlmostEqual(updated["snapshot"]["controls"]["drums"]["gain"], 0.96)


class ToneTest(OfflineCase):
    def test_brighter_raises_eq_and_activates(self):
        _, updated = run("make the lead brighter")
        eq = effect(updated, "lead", "Air EQ")
        self.assertAlmostEqual(eq["amount"], 0.7)
        self.assertTrue(eq["active"])

    def test_darker_adds_eq_when_missing(self):
        _, updated = run("darker vocals")
        eq = effect(updated, "vocals", "EQ")
        self.assertAlmostEqual(eq["amount"], 0.2)


class HardTest(OfflineCase):
    def test_harder_drop_pushes_drums_and_bass_and_ducks(self):
        report, updated = run("make the drop hit harder")
        self.assertAlmostEqual(updated["snapshot"]["controls"]["drums"]["gain"], 0.88)
        self.assertAlmostEqual(updated["snapshot"]["controls"]["bass"]["gain"], 0.78)
        self.assertTrue(effect(updated, "drums", "Kick Duck")["active"])
        self.assertTrue(effect(updated, "bass", "Sidechain")["active"])
        self.assertAlmostEqual(effect(updated, "bass", "Saturator")["amount"], 0.5)
        # The lead is in the drop too but is not a low-end track; it stays put.
        self.assertAlmostEqual(updated["snapshot"]["controls"]["lead"]["gain"], 0.9)
        self.assertEqual(report["edits"][0]["section"], "drop")
        self.assertIn("Make the drop hit harder (2 steps)", report["understood"])

    def test_softer_is_the_inverse(self):
        _, harder = run("make the drop hit harder")
        _, back = run("make the drop softer", harder)
        self.assertAlmostEqual(back["snapshot"]["controls"]["drums"]["gain"], 0.8)
        self.assertFalse(effect(back, "drums", "Kick Duck")["active"])
        self.assertAlmostEqual(effect(back, "bass", "Saturator")["amount"], 0.4)


class BounceTest(OfflineCase):
    def test_more_bounce(self):
        _, updated = run("more bounce")
        self.assertEqual(updated["snapshot"]["swing"], 26)

    def test_less_swing_a_lot_clamps_at_zero(self):
        _, updated = run("way less swing")
        self.assertEqual(updated["snapshot"]["swing"], 0)


class WidthTest(OfflineCase):
    def test_wider_lead(self):
        _, updated = run("wider lead")
        self.assertAlmostEqual(effect(updated, "lead", "Stereo Width")["amount"], 0.7)
        self.assertAlmostEqual(updated["snapshot"]["controls"]["lead"]["pan"], 0.15)

    def test_narrower_lead(self):
        _, updated = run("make the lead narrower")
        self.assertAlmostEqual(effect(updated, "lead", "Stereo Width")["amount"], 0.3)
        self.assertAlmostEqual(updated["snapshot"]["controls"]["lead"]["pan"], 0.05)


class SpaceTest(OfflineCase):
    def test_more_space_raises_reverb(self):
        _, updated = run("give the lead more space")
        self.assertAlmostEqual(effect(updated, "lead", "Plate Reverb")["amount"], 0.6)

    def test_more_echo_adds_delay(self):
        _, updated = run("more echo on the lead")
        self.assertAlmostEqual(effect(updated, "lead", "Delay")["amount"], 0.5)
        self.assertTrue(effect(updated, "lead", "Delay")["active"])

    def test_less_reverb_on_a_dry_track_is_unresolved(self):
        report, _ = run("less reverb on the vocals")
        self.assertEqual(report["edits"], [])
        self.assertEqual(len(report["unresolved"]), 1)


class TempoTest(OfflineCase):
    def test_faster_default(self):
        _, updated = run("faster")
        self.assertEqual(updated["snapshot"]["bpm"], 148)

    def test_slower_a_bit(self):
        _, updated = run("slightly slower")
        self.assertEqual(updated["snapshot"]["bpm"], 136)

    def test_faster_a_lot_is_ten(self):
        _, updated = run("much faster")
        self.assertEqual(updated["snapshot"]["bpm"], 150)


class LengthTest(OfflineCase):
    def test_longer_drop_extends_clips_and_shifts_later_material(self):
        _, updated = run("make the drop longer")
        self.assertEqual(next(c for c in track(updated, "drums")["clips"] if c["id"] == "d-drop")["bars"], 20)
        self.assertEqual(next(c for c in track(updated, "lead")["clips"] if c["id"] == "l-outro")["startBar"], 36)
        self.assertEqual(updated["snapshot"]["loopEndBar"], 36)
        self.assertEqual(updated["snapshot"]["automationLanes"][0]["points"][1]["bar"], 40)
        self.assertAlmostEqual(next(n for n in updated["snapshot"]["notes"] if n["id"] == "n3")["beat"], 146.0)

    def test_shorter_build(self):
        _, updated = run("shorter build")
        self.assertEqual(next(c for c in track(updated, "drums")["clips"] if c["id"] == "d-build")["bars"], 4)
        self.assertEqual(next(c for c in track(updated, "drums")["clips"] if c["id"] == "d-drop")["startBar"], 12)


class PitchTest(OfflineCase):
    def test_higher_transposes_only_that_track(self):
        _, updated = run("put the lead higher")
        notes = {n["id"]: n["note"] for n in updated["snapshot"]["notes"]}
        self.assertEqual(notes, {"n1": 76, "n2": 79, "n3": 40})

    def test_a_bit_lower_is_a_fourth(self):
        _, updated = run("make the bass a bit lower")
        self.assertEqual(next(n for n in updated["snapshot"]["notes"] if n["id"] == "n3")["note"], 35)

    def test_track_without_notes_is_unresolved(self):
        report, _ = run("higher drums")
        self.assertEqual(report["edits"], [])
        self.assertTrue(report["unresolved"])


class MuteTest(OfflineCase):
    def test_mute_and_bring_back(self):
        _, muted = run("mute the vocals")
        self.assertTrue(muted["snapshot"]["controls"]["vocals"]["mute"])
        _, back = run("bring back the vocals", muted)
        self.assertFalse(back["snapshot"]["controls"]["vocals"]["mute"])


class AddTest(OfflineCase):
    def test_add_hats_spans_the_drop(self):
        report, updated = run("add hats")
        hats = track(updated, "hats")
        self.assertEqual(hats["instrument"], dc.TRACK_BLUEPRINTS["drums"].instrument)
        self.assertEqual(hats["clips"][0]["startBar"], 16)
        self.assertEqual(hats["clips"][0]["bars"], 16)
        self.assertIn("hats", updated["snapshot"]["controls"])
        self.assertEqual(report["edits"][0]["trackIds"], ["hats"])

    def test_add_riser_in_the_build(self):
        _, updated = run("add a riser in the build")
        riser = track(updated, "riser")
        self.assertEqual(riser["clips"][0]["startBar"], 8)
        self.assertEqual(riser["clips"][0]["bars"], 8)
        self.assertEqual(riser["clips"][0]["type"], "audio")

    def test_add_unknown_role_is_unresolved(self):
        report, _ = run("add cowbell")
        self.assertEqual(report["edits"], [])
        self.assertIn("add what?", report["unresolved"][0])


class EnergyTest(OfflineCase):
    def test_energy_adds_lane_and_riser(self):
        _, updated = run("more energy in the build")
        lane = next(l for l in updated["snapshot"]["automationLanes"] if l["id"].startswith("auto-energy"))
        self.assertEqual(lane["points"], [{"bar": 8, "value": 0.2}, {"bar": 16, "value": 0.9}])
        fx = track(updated, "fx")
        self.assertEqual(fx["clips"][0]["startBar"], 8)
        self.assertEqual(fx["clips"][0]["bars"], 8)


class GrammarTest(OfflineCase):
    def test_and_joined_clauses_apply_in_order(self):
        report, updated = run("make the drop hit harder and give the lead more space, then mute the vocals")
        self.assertEqual([e["title"] for e in report["edits"]], ["Harder drop", "More space for Hook Lead", "Mute Vox Chops"])
        self.assertTrue(updated["snapshot"]["controls"]["vocals"]["mute"])
        self.assertEqual(report["unresolved"], [])

    def test_fuzzy_track_names(self):
        self.assertEqual(run("louder vox")[0]["edits"][0]["trackIds"], ["vocals"])
        self.assertEqual(run("louder the melody")[0]["edits"][0]["trackIds"], ["lead"])
        self.assertEqual(run("louder kick")[0]["edits"][0]["trackIds"], ["drums"])
        self.assertEqual(run("louder mid bass")[0]["edits"][0]["trackIds"], ["bass"])
        self.assertEqual(run("louder drumz")[0]["edits"][0]["trackIds"], ["drums"])

    def test_unknown_request_yields_no_edits_and_suggestions(self):
        report, updated = run("make it sparkle with glitter")
        self.assertTrue(report["ok"])
        self.assertEqual(report["edits"], [])
        self.assertEqual(len(report["unresolved"]), 1)
        self.assertEqual(len(report["suggestions"]), 6)
        self.assertEqual(updated["snapshot"]["controls"], sample_project()["snapshot"]["controls"])
        for tactic in report["tactics"]:
            self.assertGreater(tactic["score"], 0.35)

    def test_missing_section_is_reported_honestly(self):
        report, _ = run("louder drums in the second drop")
        self.assertEqual(report["edits"], [])
        self.assertIn("no second drop section", report["unresolved"][0])

    def test_partial_understanding_applies_what_it_can(self):
        report, updated = run("more bounce and frobnicate the widget")
        self.assertEqual(updated["snapshot"]["swing"], 26)
        self.assertEqual(len(report["unresolved"]), 1)

    def test_input_is_not_mutated(self):
        project = sample_project()
        before = copy.deepcopy(project)
        run("make the drop hit harder and louder lead and add hats and faster", project)
        self.assertEqual(project, before)

    def test_deterministic(self):
        a = run("make the drop hit harder and give the lead more space")
        b = run("make the drop hit harder and give the lead more space")
        self.assertEqual(a, b)


def fake_model(plan=None, explain=None, code: int = 200):
    """A Gemini transport that answers the planning call with `plan` and the explaining call
    with `explain`, recording every prompt it saw. Nothing touches the network."""
    calls: list[str] = []

    def transport(url, headers, body, timeout):
        prompt = body["contents"][0]["parts"][0]["text"]
        calls.append(prompt)
        answer = explain if "Edits already applied" in prompt else plan
        return code, json.dumps({"candidates": [{"content": {"parts": [{"text": json.dumps(answer)}]}, "finishReason": "STOP"}]})

    client = llm.Client("gemini", api_key="k", transport=transport, use_cache=False, env={"NEON_CONFIG_DIR": "/nonexistent"})
    return dc.Assist(client=client), calls


def strip_ai(report: dict) -> dict:
    return {k: v for k, v in report.items() if k != "ai"}


class ModelTest(OfflineCase):
    """The model reads the request; the code checks every answer against the project."""

    def test_off_keeps_the_grammar_output_and_says_so(self):
        report, updated = run("louder drums")
        ai = report["ai"]
        self.assertEqual(set(ai), {"used", "planned", "explained", "provider", "model", "note", "dropped"})
        self.assertEqual((ai["used"], ai["planned"], ai["explained"], ai["provider"], ai["model"], ai["dropped"]),
                         (False, "grammar", "template", None, None, []))
        self.assertTrue(ai["note"])  # a reason is always given; which one depends on the environment
        self.assertEqual(report["edits"][0]["source"], "grammar")
        self.assertEqual(report["edits"][0]["why"], "")
        self.assertEqual(report["questions"], [])
        self.assertEqual(report["next"], "")
        explicit, updated2 = dc.describe_change(sample_project(), "louder drums", assist=dc.Assist(enabled=False))
        self.assertEqual(strip_ai(explicit), strip_ai(report))
        self.assertFalse(explicit["ai"]["used"])
        self.assertIn("AI off for this run", explicit["ai"]["note"])
        self.assertEqual(updated, updated2)

    def test_no_key_and_switched_off_both_report_a_reason(self):
        with mock.patch.dict(os.environ, {"NEON_AI": "auto", "NEON_CONFIG_DIR": "/nonexistent", "GEMINI_API_KEY": "", "GOOGLE_API_KEY": "", "ANTHROPIC_API_KEY": ""}):
            no_key, _ = run("louder drums")
        with mock.patch.dict(os.environ, {"NEON_AI": "off"}):
            switched_off, _ = run("louder drums")
        for report in (no_key, switched_off):
            self.assertFalse(report["ai"]["used"])
            self.assertEqual(report["ai"]["planned"], "grammar")
            self.assertEqual(report["ai"]["explained"], "template")
            self.assertTrue(report["ai"]["note"])
        self.assertIn("no API key", no_key["ai"]["note"])
        self.assertIn("NEON_AI=off", switched_off["ai"]["note"])
        self.assertEqual(strip_ai(no_key), strip_ai(switched_off))

    def test_model_plans_a_request_the_grammar_cannot_parse(self):
        # "the drop feels empty" has no intent word; the model plans primitives with a why each,
        # including an "add" from a blueprint role the ADD_ROLES table does not know.
        assist, calls = fake_model(
            plan={
                "clauses": [
                    {"text": "the drop feels empty", "intent": "add", "direction": 1, "steps": 2, "addRole": "hat-ride",
                     "newId": "Drop Hats!", "name": "Drop hats", "addSteps": [2, 6, 10, 14], "section": {"type": "drop", "ordinal": 1},
                     "why": "hats fill the top end of a sparse drop"},
                    {"text": "the drop feels empty", "intent": "hard", "direction": 1, "steps": 1, "section": {"type": "drop", "ordinal": 1},
                     "why": "a little more low-end weight under the hats"},
                ],
                "unresolved": [],
            },
            explain={"why": [{"index": 0, "why": "Sixteenth hats give the drop motion."}], "next": "give the lead more space"},
        )
        report, updated = dc.describe_change(sample_project(), "the drop feels empty", assist=assist)
        self.assertEqual(report["unresolved"], [])
        self.assertEqual([e["title"] for e in report["edits"]], ["Add drop hats in the drop", "Harder drop"])
        hats = track(updated, "drop-hats")
        self.assertEqual(hats["instrument"], dc.TRACK_BLUEPRINTS["hat-ride"].instrument)
        self.assertEqual(hats["steps"], [2, 6, 10, 14])
        self.assertEqual((hats["clips"][0]["startBar"], hats["clips"][0]["bars"]), (16, 16))
        self.assertAlmostEqual(updated["snapshot"]["controls"]["drums"]["gain"], 0.84)  # one step of the hard recipe
        self.assertEqual([e["source"] for e in report["edits"]], ["model", "model"])
        self.assertEqual(report["edits"][0]["why"], "Sixteenth hats give the drop motion.")  # the second call refined it
        self.assertEqual(report["edits"][1]["why"], "a little more low-end weight under the hats")  # the planner's why stays
        self.assertEqual(report["next"], "give the lead more space")
        self.assertEqual(report["ai"]["used"], True)
        self.assertEqual(report["ai"]["planned"], "model")
        self.assertEqual(report["ai"]["explained"], "model")
        self.assertEqual(report["ai"]["provider"], "gemini")
        self.assertEqual(report["ai"]["dropped"], [])
        self.assertEqual(len(calls), 2)
        # The model was given the project, not asked to imagine one.
        self.assertIn('"id": "drums"', calls[0])
        self.assertIn('"type": "drop"', calls[0])
        self.assertIn('"addRole": "hat-ride"', calls[0])
        self.assertIn("the drop feels empty", calls[0])

    def test_model_asks_instead_of_guessing(self):
        assist, calls = fake_model(plan={
            "clauses": [],
            "unresolved": [{
                "text": "make it sound like the tutorial",
                "reason": "there is no tutorial reference in this project",
                "question": "Which part of the tutorial: the drop's punch, or the lead's space?",
                "suggestions": ["make the drop hit harder", "give the Hook Lead more space", "add hats in the drop"],
            }],
        })
        report, updated = dc.describe_change(sample_project(), "make it sound like the tutorial", assist=assist)
        self.assertEqual(report["edits"], [])
        self.assertEqual(report["unresolved"], ["make it sound like the tutorial (there is no tutorial reference in this project)"])
        self.assertEqual(report["questions"], ["Which part of the tutorial: the drop's punch, or the lead's space?"])
        self.assertEqual(report["suggestions"], ["make the drop hit harder", "give the Hook Lead more space", "add hats in the drop"])
        self.assertEqual(updated["snapshot"], sample_project()["snapshot"])
        self.assertTrue(report["ai"]["used"])
        self.assertEqual(report["ai"]["planned"], "model")
        self.assertEqual(report["ai"]["explained"], "template")
        self.assertIn("nothing to explain", report["ai"]["note"])
        self.assertEqual(len(calls), 1)  # nothing to explain, so no second call

    def test_a_question_is_not_overridden_by_the_grammar(self):
        # The grammar would happily apply "louder lead"; the model saw an ambiguity and asked.
        assist, _ = fake_model(plan={"clauses": [], "unresolved": [{"text": "louder lead", "reason": "two tracks carry the melody", "question": "The Hook Lead or the Vox Chops?", "suggestions": []}]})
        report, _ = dc.describe_change(sample_project(), "louder lead", assist=assist)
        self.assertEqual(report["edits"], [])
        self.assertEqual(report["questions"], ["The Hook Lead or the Vox Chops?"])
        self.assertEqual(report["suggestions"], dc.SUGGESTIONS[:6])  # no rephrasings offered, so the fixed list

    def test_invalid_answers_are_dropped_and_the_grammar_gets_a_go(self):
        assist, _ = fake_model(plan={
            "clauses": [
                {"text": "louder drums", "intent": "frobnicate", "direction": 1},                         # unknown intent -> grammar applies it
                {"text": "louder kazoo", "intent": "gain", "direction": 1, "trackId": "kazoo"},           # no such track -> unresolved
                {"text": "louder bass in the second drop", "intent": "gain", "direction": 1, "trackId": "bass", "section": {"type": "drop", "ordinal": 2}},
                {"text": "way quieter lead", "intent": "gain", "direction": -1, "steps": 9, "trackId": "Hook Lead", "amount": {"unit": "bars", "value": 4}},
                {"text": "add cowbell", "intent": "add", "addRole": "cowbell"},
                "not an object",
            ],
            "unresolved": [{"text": "mute the vocals", "reason": "unsure"}],   # no question: the grammar gets a go and succeeds
        })
        report, updated = dc.describe_change(sample_project(), "ignored: the fake answers regardless", assist=assist, explain=False)
        self.assertAlmostEqual(updated["snapshot"]["controls"]["drums"]["gain"], 0.96)
        self.assertEqual(report["edits"][0]["source"], "grammar")
        self.assertAlmostEqual(updated["snapshot"]["controls"]["lead"]["gain"], 0.66)  # steps clamped to 3, wrong-unit amount ignored
        self.assertEqual(report["edits"][1]["source"], "model")
        self.assertTrue(updated["snapshot"]["controls"]["vocals"]["mute"])
        self.assertEqual(report["unresolved"], [
            "louder kazoo (no track 'kazoo' in this project)",
            "louder bass in the second drop (this project has no second drop section)",
            "add cowbell (add what? 'cowbell' is not a blueprint role)",
            "ignored: the fake answers regardless (clause was not an object)",
        ])
        self.assertAlmostEqual(updated["snapshot"]["controls"]["bass"]["gain"], 0.7)
        self.assertNotIn("kazoo", [t["id"] for t in updated["snapshot"]["tracks"]])
        dropped = "\n".join(report["ai"]["dropped"])
        self.assertIn("frobnicate", dropped)
        self.assertIn("kazoo", dropped)
        self.assertIn("ignored amount", dropped)
        self.assertIn(f"{len(report['ai']['dropped'])} model clause(s) failed validation", report["ai"]["note"])  # never silently

    def test_model_failure_falls_back_to_the_grammar(self):
        assist, calls = fake_model(plan={"error": {"message": "bad key"}}, code=400)
        with_model, updated = dc.describe_change(sample_project(), "make the drop hit harder and give the lead more space", assist=assist)
        without, expected = run("make the drop hit harder and give the lead more space")
        self.assertEqual(strip_ai(with_model), strip_ai(without))
        self.assertEqual(updated, expected)
        self.assertFalse(with_model["ai"]["used"])
        self.assertEqual((with_model["ai"]["planned"], with_model["ai"]["explained"]), ("grammar", "template"))
        self.assertIn("gemini 400", with_model["ai"]["note"])
        # A grammar plan is not sent back to the model for its why text: one planning attempt
        # (a 400 is not retried), no explain call, no model prose anywhere in the result.
        self.assertEqual(len(calls), 1)
        self.assertTrue(all(e["why"] == "" and e["source"] == "grammar" for e in with_model["edits"]))
        self.assertEqual(with_model["next"], "")

    def test_wrong_shape_falls_back_to_the_grammar(self):
        assist, calls = fake_model(plan=["a list is not a plan"], explain={"why": [{"index": 0, "why": "must not appear"}], "next": "must not appear"})
        report, _ = dc.describe_change(sample_project(), "louder drums", assist=assist)
        self.assertEqual(report["edits"][0]["source"], "grammar")
        self.assertEqual(report["edits"][0]["why"], "")
        self.assertEqual(report["next"], "")
        self.assertFalse(report["ai"]["used"])
        self.assertEqual(report["ai"]["planned"], "grammar")
        self.assertEqual(report["ai"]["explained"], "template")
        self.assertEqual(len(calls), 1)  # the explain call is never made for a grammar plan

    def test_a_chunk_that_fails_keeps_used_honest(self):
        # The first chunk answers, the second fails: the plan is abandoned and the grammar
        # reads the whole request, so nothing of the model's shaped the result.
        calls: list[str] = []

        def transport(url, headers, body, timeout):
            calls.append(body["contents"][0]["parts"][0]["text"])
            if len(calls) == 1:
                return 200, json.dumps({"candidates": [{"content": {"parts": [{"text": json.dumps({"clauses": [], "unresolved": []})}]}}]})
            return 400, json.dumps({"error": {"message": "second chunk refused"}})

        client = llm.Client("gemini", api_key="k", transport=transport, use_cache=False, env={"NEON_CONFIG_DIR": "/nonexistent"})
        assist = dc.Assist(client=client)
        long_request = ", ".join(["louder drums"] * 3000)
        report, updated = dc.describe_change(sample_project(), long_request, assist=assist)
        self.assertTrue(assist.used)  # the adapter saw one good answer...
        self.assertFalse(report["ai"]["used"])  # ...but the tool reports what shaped the edits
        self.assertEqual((report["ai"]["planned"], report["ai"]["explained"]), ("grammar", "template"))
        self.assertIn("second chunk refused", report["ai"]["note"])
        self.assertEqual(len(calls), 2)
        self.assertTrue(report["edits"])
        self.assertTrue(all(e["source"] == "grammar" for e in report["edits"]))

    def test_explain_failure_keeps_the_planners_why(self):
        calls: list[str] = []
        plan = {"clauses": [{"text": "louder drums", "intent": "gain", "direction": 1, "steps": 2, "trackId": "drums", "why": "the planner's reason"}], "unresolved": []}

        def transport(url, headers, body, timeout):
            prompt = body["contents"][0]["parts"][0]["text"]
            calls.append(prompt)
            if "Edits already applied" in prompt:
                return 400, json.dumps({"error": {"message": "explain refused"}})
            return 200, json.dumps({"candidates": [{"content": {"parts": [{"text": json.dumps(plan)}]}}]})

        client = llm.Client("gemini", api_key="k", transport=transport, use_cache=False, env={"NEON_CONFIG_DIR": "/nonexistent"})
        report, _ = dc.describe_change(sample_project(), "louder drums", assist=dc.Assist(client=client))
        self.assertEqual(len(calls), 2)
        self.assertEqual(report["edits"][0]["source"], "model")
        self.assertEqual(report["edits"][0]["why"], "the planner's reason")
        self.assertEqual(report["next"], "")
        self.assertTrue(report["ai"]["used"])
        self.assertEqual((report["ai"]["planned"], report["ai"]["explained"]), ("model", "template"))
        self.assertIn("explain refused", report["ai"]["note"])
        self.assertIn("planner's", report["ai"]["note"])

    def test_clauses_beyond_the_cap_are_reported_not_dropped(self):
        self.assertGreaterEqual(dc.MAX_MODEL_CLAUSES, 24)
        count = dc.MAX_MODEL_CLAUSES + 3
        clauses = [{"text": f"louder drums #{i}", "intent": "gain", "direction": 1, "steps": 1, "trackId": "drums"} for i in range(count)]
        assist, calls = fake_model(plan={"clauses": clauses, "unresolved": [{"text": f"u{i}", "reason": "r", "question": f"q{i}?"} for i in range(count)]},
                                   explain={"why": [], "next": ""})
        report, updated = dc.describe_change(sample_project(), "…", assist=assist)
        gains = [e for e in report["edits"] if e["title"].startswith("Louder")]
        self.assertEqual(len(gains), dc.MAX_MODEL_CLAUSES)
        self.assertEqual(len(report["questions"]), dc.MAX_MODEL_CLAUSES)
        overflow = [u for u in report["unresolved"] if "not applied" in u]
        self.assertEqual(len(overflow), 1)
        self.assertIn(f"3 more clause(s) the model planned were not applied (at most {dc.MAX_MODEL_CLAUSES} per request", overflow[0])
        self.assertIn(f"'louder drums #{dc.MAX_MODEL_CLAUSES}'", overflow[0])
        self.assertTrue(any("3 more item(s) the model could not place were not listed" in u for u in report["unresolved"]))
        self.assertIn("3 more clause(s) the model planned were not applied", report["ai"]["note"])
        self.assertIn("3 more item(s) the model could not place were not listed", report["ai"]["note"])
        self.assertIn(f"At most {dc.MAX_MODEL_CLAUSES} clauses", calls[0])

    def test_within_the_cap_nothing_is_reported_as_beyond_it(self):
        clauses = [{"text": f"louder drums #{i}", "intent": "gain", "direction": 1, "steps": 1, "trackId": "drums"} for i in range(dc.MAX_MODEL_CLAUSES)]
        assist, _ = fake_model(plan={"clauses": clauses, "unresolved": []}, explain={"why": [], "next": ""})
        report, _ = dc.describe_change(sample_project(), "…", assist=assist)
        self.assertEqual(len(report["edits"]), dc.MAX_MODEL_CLAUSES)
        self.assertEqual(report["unresolved"], [])
        self.assertNotIn("not applied", report["ai"]["note"])

    def test_explicit_amounts_are_honoured_and_clamped(self):
        assist, _ = fake_model(plan={
            "clauses": [
                {"text": "10 bpm faster", "intent": "tempo", "direction": 1, "steps": 2, "amount": {"unit": "bpm", "value": 10}},
                {"text": "make the build 8 bars longer", "intent": "length", "direction": 1, "steps": 2, "section": {"type": "build", "ordinal": 1}, "amount": {"unit": "bars", "value": 8}},
                {"text": "put the lead up an octave", "intent": "pitch", "direction": 1, "steps": 2, "trackId": "lead", "amount": {"unit": "semitones", "value": 12}},
                {"text": "a lot more swing", "intent": "bounce", "direction": 1, "steps": 3, "amount": {"unit": "percent", "value": 900}},
                {"text": "the lead 20% brighter", "intent": "tone", "direction": 1, "steps": 2, "trackId": "lead", "amount": {"unit": "percent", "value": 20}},
            ],
            "unresolved": [],
        }, explain={"why": [], "next": ""})
        report, updated = dc.describe_change(sample_project(), "…", assist=assist)
        self.assertEqual(report["unresolved"], [])
        self.assertEqual(updated["snapshot"]["bpm"], 150)
        self.assertEqual(next(c for c in track(updated, "drums")["clips"] if c["id"] == "d-build")["bars"], 16)
        self.assertEqual(next(c for c in track(updated, "drums")["clips"] if c["id"] == "d-drop")["startBar"], 24)
        notes = {n["id"]: n["note"] for n in updated["snapshot"]["notes"]}
        self.assertEqual((notes["n1"], notes["n2"]), (76, 79))
        self.assertEqual(updated["snapshot"]["swing"], 60)  # 900 clamped to 50 points, on top of 10
        self.assertAlmostEqual(effect(updated, "lead", "Air EQ")["amount"], 0.6)
        self.assertIn("Faster (10 bpm)", report["understood"])
        self.assertIn("Make the build longer (8 bars)", report["understood"])
        self.assertIn("Make the Hook Lead brighter (20%)", report["understood"])
        self.assertEqual(report["next"], "")

    def test_referents_and_two_tracks_in_one_ask(self):
        assist, _ = fake_model(plan={
            "clauses": [
                {"text": "make the drums and bass louder", "intent": "gain", "direction": 1, "steps": 2, "trackId": "drums"},
                {"text": "make the drums and bass louder", "intent": "gain", "direction": 1, "steps": 2, "trackId": "bass"},
                {"text": "give it more echo", "intent": "space", "direction": 1, "steps": 2, "trackId": "bass", "effect": "delay"},
                {"text": "everything a bit quieter", "intent": "gain", "direction": -1, "steps": 1, "wholeSong": True},
            ],
            "unresolved": [],
        }, explain={"why": [{"index": 9, "why": "out of range"}, {"index": 2, "why": "Delay gives the bass a tail."}], "next": "make the drop hit harder"})
        report, updated = dc.describe_change(sample_project(), "make the drums and bass louder, give it more echo, everything a bit quieter", assist=assist)
        self.assertEqual(report["unresolved"], [])
        self.assertAlmostEqual(updated["snapshot"]["controls"]["drums"]["gain"], 0.88)   # +0.16 then -0.08
        self.assertAlmostEqual(updated["snapshot"]["controls"]["bass"]["gain"], 0.78)
        self.assertAlmostEqual(updated["snapshot"]["controls"]["lead"]["gain"], 0.82)
        self.assertAlmostEqual(effect(updated, "bass", "Delay")["amount"], 0.5)
        self.assertEqual(report["edits"][2]["why"], "Delay gives the bass a tail.")
        self.assertEqual(report["next"], "make the drop hit harder")

    def test_long_requests_are_chunked(self):
        assist, calls = fake_model(plan={"clauses": [], "unresolved": []})
        long_request = ", ".join(["louder drums"] * 3000)  # ~39k characters
        self.assertGreater(len(long_request), dc.MAX_REQUEST_CHARS)
        dc.describe_change(sample_project(), long_request, assist=assist)
        self.assertGreaterEqual(len(calls), 2)
        for prompt in calls:
            self.assertLessEqual(len(prompt), dc.MAX_REQUEST_CHARS + 8000)  # request chunk plus the fixed guide and schema

    def test_deterministic_with_a_fake_model(self):
        plan = {"clauses": [{"text": "louder drums", "intent": "gain", "direction": 1, "steps": 2, "trackId": "drums", "why": "w"}], "unresolved": []}
        a = dc.describe_change(sample_project(), "louder drums", assist=fake_model(plan=plan, explain={"why": [], "next": "n"})[0])
        b = dc.describe_change(sample_project(), "louder drums", assist=fake_model(plan=plan, explain={"why": [], "next": "n"})[0])
        self.assertEqual(a, b)


class CliTest(OfflineCase):
    def test_cli_ai_off_flag_and_ai_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.neon.json"
            out = Path(tmp) / "out.neon.json"
            src.write_text(json.dumps(sample_project()), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(Path(dc.__file__)), "--root", tmp, "--project", str(src), "--request", "louder drums", "--output", str(out), "--ai", "off"],
                capture_output=True, text=True, check=False, env={**os.environ, "NEON_AI": "auto", "GEMINI_API_KEY": "would-not-be-used"},
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout.strip().splitlines()[-1])
            self.assertIn("AI off for this run", report["ai"]["note"])
            self.assertFalse(report["ai"]["used"])
            self.assertEqual(report["ai"]["planned"], "grammar")
            self.assertEqual(report["edits"][0]["source"], "grammar")

    def test_cli_writes_output_and_leaves_input_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.neon.json"
            out = Path(tmp) / "out.neon.json"
            src.write_text(json.dumps(sample_project()), encoding="utf-8")
            before = src.read_bytes()
            result = subprocess.run(
                [sys.executable, str(Path(dc.__file__)), "--root", tmp, "--project", str(src), "--request", "louder drums", "--output", str(out), "--format", "json"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout.strip().splitlines()[-1])
            self.assertTrue(report["ok"])
            self.assertEqual(report["project"], str(out))
            self.assertEqual(src.read_bytes(), before)
            written = json.loads(out.read_text(encoding="utf-8"))
            self.assertAlmostEqual(written["snapshot"]["controls"]["drums"]["gain"], 0.96)

    def test_cli_missing_project_fails_with_json_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, str(Path(dc.__file__)), "--project", os.path.join(tmp, "nope.neon.json"), "--request", "louder drums", "--output", os.path.join(tmp, "out.json"), "--format", "json"],
                capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            report = json.loads(result.stdout.strip().splitlines()[-1])
            self.assertFalse(report["ok"])
            self.assertIn("error", report)


if __name__ == "__main__":
    unittest.main()
