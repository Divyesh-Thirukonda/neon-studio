#!/usr/bin/env python3
"""Tests for the model's voice in the reports: does_this_sound_good.py and
the shared rules both report tools follow.

Run with:  /usr/bin/python3 -m unittest tools/test_reports_ai.py

Nothing here touches the network. Every model answer comes from a fake
transport injected through llm.Client, and the environment is pinned so a
real key on the machine can never leak into a test or a CLI subprocess.
The fidelity tool's own model tests live in test_transcript_fidelity.py.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import does_this_sound_good as dtsg  # noqa: E402
import llm  # noqa: E402
import transcript_fidelity as tf  # noqa: E402

SR = 44_100
TOOL = Path(__file__).resolve().parent / "does_this_sound_good.py"
FIDELITY_TOOL = Path(__file__).resolve().parent / "transcript_fidelity.py"
NO_ENV = {"NEON_CONFIG_DIR": "/nonexistent"}
MEASURED = {"answer": "measured", "summary": "measured", "nextActions": "measured"}


class PinnedEnvironment(unittest.TestCase):
    """Model off for every test and every CLI subprocess it starts: no key
    file, no key variables. Pinned in setUp and restored in tearDown - never at
    import time - so this module can never change what another module sees.
    NEON_AI is left alone: other suites set or clear it and check the note."""

    def setUp(self) -> None:
        self._saved_environ = dict(os.environ)
        os.environ["NEON_CONFIG_DIR"] = "/nonexistent"
        for key in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "NEON_AI_MODEL"):
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._saved_environ)


def write_wav(path: Path, mono: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.stack([mono, mono], axis=1).clip(-1, 1) * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(SR)
        handle.writeframes(pcm.tobytes())


def tone(hz: float, seconds: float, level: float) -> np.ndarray:
    t = np.arange(int(seconds * SR)) / SR
    return (np.sin(2 * np.pi * hz * t) * level).astype(np.float32)


def project() -> dict:
    return {
        "id": "fixture",
        "name": "Fixture",
        "snapshot": {
            "bpm": 120,
            "tracks": [
                {"id": "drums", "name": "Drums", "kind": "drum", "instrument": "Kit", "gain": 0.9, "pan": 0.0,
                 "file": "/api/audio/fx_drums.wav", "clips": [{"name": "Drop drums", "startBar": 4, "bars": 8}], "effects": []},
                {"id": "bass", "name": "Mid Bass", "kind": "instrument", "instrument": "Sub", "gain": 0.9, "pan": 0.0,
                 "file": "/api/audio/fx_bass.wav", "clips": [{"name": "Drop bass", "startBar": 4, "bars": 8}],
                 "effects": [{"id": "e1", "name": "Sidechain", "active": True, "amount": 0.7}]},
                {"id": "lead", "name": "Hook Lead", "kind": "instrument", "instrument": "Saw", "gain": 0.8, "pan": 0.2,
                 "file": "/api/audio/fx_lead.wav", "clips": [{"name": "Drop lead", "startBar": 4, "bars": 8}], "effects": []},
            ],
            "controls": {},
            "recipe": [
                {"id": "r1", "section": "Intro", "label": "Intro"},
                {"id": "r2", "section": "Drop", "label": "Drop"},
            ],
        },
    }


class Fixture:
    def __init__(self, tmp: str) -> None:
        self.root = Path(tmp)
        self.path = self.root / "data" / "projects" / "fixture.neon.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(project()))
        write_wav(self.root / "exports" / "fx_drums.wav", tone(60.0, 20.0, 0.3))
        write_wav(self.root / "exports" / "fx_bass.wav", tone(110.0, 20.0, 0.3))
        write_wav(self.root / "exports" / "fx_lead.wav", tone(880.0, 20.0, 0.25))

    def report(self, assist=None) -> dict:
        return dtsg.build_report(self.root, self.path, assist)


def gemini_transport(reply, calls: list = None):
    """A transport answering every call with `reply` (a JSON value, or a
    string sent verbatim so a non-JSON reply can be simulated)."""
    def transport(url, headers, body, timeout):
        if calls is not None:
            system = (body.get("systemInstruction") or {}).get("parts", [{}])[0].get("text", "")
            calls.append((system, body["contents"][0]["parts"][0]["text"]))
        text = reply if isinstance(reply, str) else json.dumps(reply)
        return 200, json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}}]})
    return transport


def fake_assist(reply, calls: list = None) -> llm.Assist:
    client = llm.Client("gemini", api_key="k", transport=gemini_transport(reply, calls), use_cache=False, env=dict(NO_ENV))
    return llm.Assist(client=client)


def good_reply(label: str) -> dict:
    return {
        "answer": f"{label} - the low end is carrying this mix and the lead needs a home",
        "summary": "The mix is loud enough and nothing clips. Mid Bass is the loudest lane, so the Hook Lead has to fight it in the Drop.",
        "nextActions": [
            {"action": "Pull Mid Bass down in the Drop so the Hook Lead reads.", "track": "Mid Bass", "section": "drop",
             "why": "Mid Bass is the loudest lane in the readout."},
            {"action": "High-pass the Hook Lead so it stops adding low mids.", "track": "lead", "section": None,
             "why": "keeps the low end owned by one lane"},
            {"action": "Run one human listen for hook memorability.", "track": None, "section": None, "why": ""},
        ],
    }


class SoundCheckOfflineTests(PinnedEnvironment):
    def test_no_assist_and_disabled_assist_give_the_same_measured_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(tmp)
            plain = fixture.report()
            off = fixture.report(llm.Assist(enabled=False))
        self.assertEqual(json.dumps(plain, sort_keys=True), json.dumps(off, sort_keys=True))
        self.assertEqual(plain["ai"], {"used": False, "provider": None, "model": None, "note": "AI off for this run"})
        self.assertEqual(plain["verdict"]["source"], "heuristic")
        self.assertEqual(plain["verdict"]["sources"], MEASURED)
        self.assertEqual([d["action"] for d in plain["nextActionDetails"]], plain["nextActions"])
        self.assertTrue(all(d["source"] == "heuristic" for d in plain["nextActionDetails"]))
        for key in ("score", "label", "answer", "summary"):
            self.assertIn(key, plain["verdict"])

    def test_cli_ai_off_reports_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(tmp)
            result = subprocess.run(
                [sys.executable, str(TOOL), "--root", tmp, "--project-id", "fixture", "--ai", "off"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout.strip().splitlines()[-1])
            self.assertEqual(payload["ai"]["note"], "AI off for this run")
            self.assertFalse(payload["ai"]["used"])
            markdown = subprocess.run(
                [sys.executable, str(TOOL), "--root", tmp, "--project-id", "fixture", "--ai", "off", "--format", "markdown"],
                capture_output=True, text=True, check=False,
            )
            self.assertIn("offline rules", markdown.stdout)


class SoundCheckModelTests(PinnedEnvironment):
    def test_model_writes_the_words_and_nothing_else(self) -> None:
        calls: list = []
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(tmp)
            off = fixture.report()
            report = fixture.report(fake_assist(good_reply(off["verdict"]["label"]), calls))
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], dtsg.VERDICT_ROLE)
        self.assertIn('"Hook Lead"', calls[0][1])
        # Measured parts are untouched.
        for key in ("metrics", "projectChecks", "trackReports", "strengths", "issues"):
            self.assertEqual(report[key], off[key], key)
        self.assertEqual(report["verdict"]["score"], off["verdict"]["score"])
        self.assertEqual(report["verdict"]["label"], off["verdict"]["label"])
        # Words are the model's.
        self.assertTrue(report["ai"]["used"])
        self.assertEqual(report["verdict"]["source"], "model")
        self.assertEqual(report["verdict"]["sources"], {"answer": "model", "summary": "model", "nextActions": "model"})
        self.assertTrue(report["verdict"]["answer"].startswith(off["verdict"]["label"]))
        self.assertIn("Hook Lead", report["verdict"]["summary"])
        self.assertEqual(len(report["nextActions"]), 3)
        self.assertIn("Pull Mid Bass down", report["nextActions"][0])
        first = report["nextActionDetails"][0]
        self.assertEqual((first["track"], first["section"], first["source"]), ("bass", "Drop", "model"))
        self.assertEqual(report["nextActionDetails"][1]["track"], "lead")
        self.assertIsNone(report["nextActionDetails"][2]["track"])
        self.assertEqual(report["ai"]["note"], "")
        text = dtsg.render_markdown(report)
        self.assertIn("via gemini", text)
        self.assertIn("(answer: model, summary: model, nextActions: model)", text)
        self.assertIn("(Mid Bass is the loudest lane in the readout.)", text)

    def test_invalid_parts_of_the_answer_fall_back_one_by_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(tmp)
            off = fixture.report()
            label = off["verdict"]["label"]
            reply = {
                "answer": "Absolutely stunning, ship it",                 # does not start with the label
                "summary": "The RMS sits at -3.1 dBFS and it clips 40% of the time.",   # invented numbers
                "nextActions": [
                    {"action": "Mute the Vocals in the Drop.", "track": "vocals", "section": "Drop", "why": ""},   # no such track
                    {"action": "Widen the chords in the Bridge.", "track": None, "section": "Bridge", "why": ""}, # no such section
                    {"action": "Cut Drums by 12 dB.", "track": "drums", "section": None, "why": ""},                # invented number
                    {"action": "Trim Mid Bass by 2 dB.", "track": "bass", "section": None, "why": ""},              # small, but it has a unit
                    {"action": "Give the Hook Lead its own space in the Drop.", "track": "Hook Lead", "section": "Drop", "why": "it fights Mid Bass"},
                    "not an object",
                ],
            }
            report = fixture.report(fake_assist(reply))
        self.assertTrue(report["ai"]["used"])
        self.assertEqual(report["verdict"]["answer"], off["verdict"]["answer"])
        self.assertEqual(report["verdict"]["summary"], off["verdict"]["summary"])
        self.assertEqual(report["verdict"]["source"], "heuristic")
        self.assertEqual(report["verdict"]["sources"], {"answer": "measured", "summary": "measured", "nextActions": "model"})
        self.assertEqual(report["nextActions"], ["Give the Hook Lead its own space in the Drop."])
        self.assertEqual(report["nextActionDetails"][0]["track"], "lead")
        note = report["ai"]["note"]
        for fragment in ("answer", "summary", "unknown track 'vocals'", "unknown section 'Bridge'", "ungrounded number", "not an object"):
            self.assertIn(fragment, note)

    def test_provenance_is_per_field_and_the_whole_is_the_models_only_when_every_part_is(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(tmp)
            off = fixture.report()
            label = off["verdict"]["label"]
            reply = {"answer": f"{label} - the low end carries it", "summary": "It peaks at 99 dBFS.", "nextActions": []}
            report = fixture.report(fake_assist(reply))
        self.assertTrue(report["ai"]["used"])
        self.assertEqual(report["verdict"]["sources"], {"answer": "model", "summary": "measured", "nextActions": "measured"})
        self.assertEqual(report["verdict"]["source"], "heuristic", "one field from the model does not make the verdict the model's")
        self.assertEqual(report["verdict"]["answer"], f"{label} - the low end carries it")
        self.assertEqual(report["verdict"]["summary"], off["verdict"]["summary"])
        self.assertEqual(report["nextActions"], off["nextActions"])
        self.assertIn("summary", report["ai"]["note"])
        self.assertIn("nextActions", report["ai"]["note"])
        self.assertNotIn("answer", report["ai"]["note"].split(":", 1)[1])

    def test_nothing_valid_means_the_heuristic_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(tmp)
            off = fixture.report()
            garbage = fixture.report(fake_assist({"answer": 7, "summary": [], "nextActions": "later"}))
            wrong_shape = fixture.report(fake_assist([1, 2, 3]))
            not_json = fixture.report(fake_assist("I would rather not."))
        for report in (garbage, wrong_shape, not_json):
            for key in ("verdict", "nextActions", "metrics", "issues", "strengths"):
                self.assertEqual(report[key], off[key], key)
            self.assertEqual(report["verdict"]["sources"], MEASURED)
        self.assertTrue(garbage["ai"]["used"])
        self.assertIn("kept the heuristic text", garbage["ai"]["note"])
        self.assertFalse(wrong_shape["ai"]["used"])
        self.assertIn("wanted dict", wrong_shape["ai"]["note"])
        self.assertFalse(not_json["ai"]["used"])
        self.assertIn("not JSON", not_json["ai"]["note"])

    def test_model_error_leaves_the_report_alone(self) -> None:
        def broken(url, headers, body, timeout):
            return 403, json.dumps({"error": {"message": "key revoked"}})
        client = llm.Client("gemini", api_key="k", transport=broken, use_cache=False, env=dict(NO_ENV))
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(tmp)
            off = fixture.report()
            report = fixture.report(llm.Assist(client=client))
        self.assertFalse(report["ai"]["used"])
        self.assertIn("gemini 403", report["ai"]["note"])
        report.pop("ai")
        off.pop("ai")
        self.assertEqual(json.dumps(report, sort_keys=True), json.dumps(off, sort_keys=True))

    def test_silent_project_never_asks_the_model(self) -> None:
        calls: list = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "empty.neon.json"
            path.write_text(json.dumps({"id": "empty", "name": "Empty", "snapshot": {"tracks": [], "recipe": []}}))
            report = dtsg.build_report(root, path, fake_assist(good_reply("Yes"), calls))
        self.assertEqual(calls, [])
        self.assertEqual(report["verdict"]["label"], "Cannot judge")
        self.assertFalse(report["ai"]["used"])
        self.assertIn("nothing for the model", report["ai"]["note"])


class GroundingRuleTests(PinnedEnvironment):
    """The one rule both reports share: a number the model writes must be one it was given."""

    def test_numbers_must_come_from_the_facts(self) -> None:
        facts = json.dumps({"rmsDb": -14.27, "peakDb": -0.8, "crestDb": 13.5, "trackCount": 11})
        for helper in (dtsg.numbers_are_grounded, tf.numbers_are_grounded):
            self.assertTrue(helper("RMS is around -14.3 dBFS with 13.5 dB of crest across 11 tracks.", facts))
            self.assertTrue(helper("Drop 2 and beat 3 are fine; no numbers invented.", facts))
            self.assertFalse(helper("RMS is -9 dBFS.", facts))
            self.assertFalse(helper("Cut 250 Hz.", facts))
            self.assertTrue(helper("Nothing numeric here.", facts))

    def test_small_integers_pass_only_without_a_unit(self) -> None:
        facts = json.dumps({"rmsDb": -14.27, "trackCount": 11})
        for helper in (dtsg.numbers_are_grounded, tf.numbers_are_grounded):
            # Counts and names: not readings.
            self.assertTrue(helper("Drop 2 has 3 sections and 4 steps; 11 tracks in all.", facts))
            self.assertTrue(helper("Bar 1 to bar 4 is the intro.", facts))
            # The same digits with a unit are readings, and must be in the facts.
            for phrase in ("cut 3 dB", "pull it down 2dB", "a 4 dBFS ceiling", "boost 2 Hz", "cut 1 kHz",
                           "a 3 ms attack", "wait 2 s", "raise it 3%", "trim 2 bars", "hold 4 BPM", "up 2 st",
                           "up 2 semitones", "cut 3 DB"):
                self.assertFalse(helper(phrase, facts), phrase)
            # A unit-bearing small integer that IS in the facts passes like any other number.
            self.assertTrue(helper("cut 2 dB and open 2 bars", json.dumps({"gainDb": 2, "bars": 2})))

    def test_quote_rule_is_whitespace_and_case_tolerant_but_not_fuzzy(self) -> None:
        text = "Section 2 Drop bars 5-12:\n   sidechain   the bass to the kick."
        self.assertTrue(tf.quote_in_text("sidechain the bass to the kick.", text))
        self.assertTrue(tf.quote_in_text("Sidechain the bass to the KICK.", text))
        self.assertFalse(tf.quote_in_text("sidechain the sub to the kick.", text))
        self.assertFalse(tf.quote_in_text("bass", text))     # too short to count as evidence

    def test_fidelity_cli_ai_off(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data" / "projects").mkdir(parents=True)
            (root / "songlab" / "projects" / "fixture").mkdir(parents=True)
            (root / "data" / "projects" / "fixture.neon.json").write_text(json.dumps(project()))
            (root / "songlab" / "projects" / "fixture" / "transcript_spec.json").write_text(json.dumps(
                {"projectId": "fixture", "tempoHint": 120, "keyHints": [], "sections": [], "timecoded": False}))
            result = subprocess.run(
                [sys.executable, str(FIDELITY_TOOL), "--root", tmp, "--project-id", "fixture", "--ai", "off"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout.strip().splitlines()[-1])
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["ai"]["note"], "AI off for this run")
            self.assertEqual(payload["summarySource"], "heuristic")


if __name__ == "__main__":
    unittest.main()
