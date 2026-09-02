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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import describe_change as dc  # noqa: E402


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


class SectionsTest(unittest.TestCase):
    def test_sections_are_clustered_by_bar(self):
        sections = {s.key: (s.start_bar, s.end_bar) for s in dc.project_sections(sample_project())}
        self.assertEqual(sections, {"intro-1": (0, 8), "build-1": (8, 16), "drop-1": (16, 32), "outro-1": (32, 40)})

    def test_second_drop_gets_its_own_ordinal(self):
        project = sample_project()
        track(project, "drums")["clips"].append(clip("d-drop2", "Drop drums again", "drums", 48, 16))
        keys = [s.key for s in dc.project_sections(project)]
        self.assertIn("drop-2", keys)


class GainTest(unittest.TestCase):
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


class ToneTest(unittest.TestCase):
    def test_brighter_raises_eq_and_activates(self):
        _, updated = run("make the lead brighter")
        eq = effect(updated, "lead", "Air EQ")
        self.assertAlmostEqual(eq["amount"], 0.7)
        self.assertTrue(eq["active"])

    def test_darker_adds_eq_when_missing(self):
        _, updated = run("darker vocals")
        eq = effect(updated, "vocals", "EQ")
        self.assertAlmostEqual(eq["amount"], 0.2)


class HardTest(unittest.TestCase):
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


class BounceTest(unittest.TestCase):
    def test_more_bounce(self):
        _, updated = run("more bounce")
        self.assertEqual(updated["snapshot"]["swing"], 26)

    def test_less_swing_a_lot_clamps_at_zero(self):
        _, updated = run("way less swing")
        self.assertEqual(updated["snapshot"]["swing"], 0)


class WidthTest(unittest.TestCase):
    def test_wider_lead(self):
        _, updated = run("wider lead")
        self.assertAlmostEqual(effect(updated, "lead", "Stereo Width")["amount"], 0.7)
        self.assertAlmostEqual(updated["snapshot"]["controls"]["lead"]["pan"], 0.15)

    def test_narrower_lead(self):
        _, updated = run("make the lead narrower")
        self.assertAlmostEqual(effect(updated, "lead", "Stereo Width")["amount"], 0.3)
        self.assertAlmostEqual(updated["snapshot"]["controls"]["lead"]["pan"], 0.05)


class SpaceTest(unittest.TestCase):
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


class TempoTest(unittest.TestCase):
    def test_faster_default(self):
        _, updated = run("faster")
        self.assertEqual(updated["snapshot"]["bpm"], 148)

    def test_slower_a_bit(self):
        _, updated = run("slightly slower")
        self.assertEqual(updated["snapshot"]["bpm"], 136)

    def test_faster_a_lot_is_ten(self):
        _, updated = run("much faster")
        self.assertEqual(updated["snapshot"]["bpm"], 150)


class LengthTest(unittest.TestCase):
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


class PitchTest(unittest.TestCase):
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


class MuteTest(unittest.TestCase):
    def test_mute_and_bring_back(self):
        _, muted = run("mute the vocals")
        self.assertTrue(muted["snapshot"]["controls"]["vocals"]["mute"])
        _, back = run("bring back the vocals", muted)
        self.assertFalse(back["snapshot"]["controls"]["vocals"]["mute"])


class AddTest(unittest.TestCase):
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


class EnergyTest(unittest.TestCase):
    def test_energy_adds_lane_and_riser(self):
        _, updated = run("more energy in the build")
        lane = next(l for l in updated["snapshot"]["automationLanes"] if l["id"].startswith("auto-energy"))
        self.assertEqual(lane["points"], [{"bar": 8, "value": 0.2}, {"bar": 16, "value": 0.9}])
        fx = track(updated, "fx")
        self.assertEqual(fx["clips"][0]["startBar"], 8)
        self.assertEqual(fx["clips"][0]["bars"], 8)


class GrammarTest(unittest.TestCase):
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


class CliTest(unittest.TestCase):
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
