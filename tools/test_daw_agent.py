#!/usr/bin/env python3
"""Unit tests for the deterministic DAW agent."""

from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import daw_agent
import llm

NO_ENV = {"NEON_CONFIG_DIR": "/nonexistent"}


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


def fake_assist(answers: list) -> tuple[llm.Assist, list[dict]]:
    """An Assist whose model replies with `answers` in order; records the prompts."""
    calls: list[dict] = []
    queue = list(answers)

    def transport(url, headers, body, timeout):
        prompt = body["contents"][0]["parts"][0]["text"]
        calls.append({"prompt": prompt, "system": (body.get("systemInstruction") or {}).get("parts", [{}])[0].get("text", "")})
        answer = queue.pop(0) if queue else {}
        if isinstance(answer, tuple):
            return answer
        return 200, json.dumps({"candidates": [{"content": {"parts": [{"text": json.dumps(answer)}]}, "finishReason": "STOP"}]})

    client = llm.Client("gemini", api_key="k", transport=transport, use_cache=False, env=dict(NO_ENV))
    return llm.Assist(client=client), calls


def sample_project() -> dict:
    return {
        "format": "neon-studio-project",
        "formatVersion": 1,
        "portable": True,
        "assetMode": "external",
        "id": "agent-unit",
        "name": "Agent Unit",
        "createdAt": "2026-01-01T00:00:00Z",
        "updatedAt": "2026-01-01T00:00:00Z",
        "keyCenter": "e_minor",
        "snapshot": {
            "version": 3,
            "bpm": 140,
            "swing": 0,
            "snap": "1/4",
            "loopEnabled": True,
            "loopStartBar": 16,
            "loopEndBar": 24,
            "selectedTrackId": "lead",
            "tracks": [
                {
                    "id": "drums",
                    "name": "Drums",
                    "kind": "pattern",
                    "instrument": "Sampler",
                    "gain": 0.8,
                    "pan": 0,
                    "color": "#ff8d5c",
                    "clips": [
                        {
                            "id": "drums-main",
                            "name": "Main drums",
                            "startBar": 0,
                            "bars": 16,
                            "lane": "drums",
                            "type": "pattern",
                            "color": "#ff8d5c",
                        }
                    ],
                    "effects": [],
                },
                {
                    "id": "lead",
                    "name": "Lead",
                    "kind": "pattern",
                    "instrument": "Lead Synth",
                    "gain": 0.74,
                    "pan": 0,
                    "color": "#60c8f8",
                    "clips": [
                        {
                            "id": "lead-hook",
                            "name": "Hook",
                            "startBar": 16,
                            "bars": 8,
                            "lane": "lead",
                            "type": "pattern",
                            "color": "#60c8f8",
                        }
                    ],
                    "effects": [],
                },
                {
                    "id": "fx",
                    "name": "FX",
                    "kind": "audio",
                    "instrument": "Transition FX",
                    "gain": 0.7,
                    "pan": 0,
                    "color": "#f59fcb",
                    "clips": [],
                    "effects": [],
                },
            ],
            "controls": {},
            "automationLanes": [],
            "notes": [],
            "recipe": [],
        },
    }


class DawAgentTests(PinnedEnvironment):
    def test_retrieval_ranks_expected_source_daw_features(self) -> None:
        project = sample_project()
        cases = {
            "automation clip filter sweep riser": "fl-automation-clips",
            "randomize drums humanize groove velocity": "fl-randomizer-groove",
            "riff machine melody motif variation": "fl-riff-machine-variation",
            "gross beat gate tape stop transition": "fl-gross-beat-transition",
            "patcher macro routing control surface": "fl-patcher-macro-chain",
        }
        for query, expected in cases.items():
            with self.subTest(query=query):
                ranked = daw_agent.retrieve_features(query, project=project, limit=3)
                self.assertEqual(ranked[0]["id"], expected)

    def test_agent_applies_traceable_project_improvements(self) -> None:
        project = sample_project()
        report = daw_agent.run_agent(project, query="automation groove riff transition macro", max_actions=4)
        updated = report["updatedProject"]
        metrics_before = report["metricsBefore"]
        metrics_after = report["metricsAfter"]

        self.assertEqual(updated["id"], project["id"])
        self.assertGreaterEqual(metrics_after["recipeCount"], metrics_before["recipeCount"] + 4)
        self.assertGreater(metrics_after["automationLaneCount"], metrics_before["automationLaneCount"])
        self.assertGreater(metrics_after["clipCount"], metrics_before["clipCount"])
        self.assertGreater(metrics_after["effectCount"], metrics_before["effectCount"])
        self.assertGreater(metrics_after["noteCount"], metrics_before["noteCount"])
        self.assertTrue(daw_agent.controls_cover_tracks(updated))
        self.assertEqual(daw_agent.duplicate_ids(updated), {})

    def test_agent_is_idempotent_for_same_features(self) -> None:
        first = daw_agent.run_agent(sample_project(), query="automation groove riff transition macro", max_actions=4)["updatedProject"]
        second_report = daw_agent.run_agent(copy.deepcopy(first), query="automation groove riff transition macro", max_actions=4)
        second = second_report["updatedProject"]

        self.assertEqual(daw_agent.duplicate_ids(second), {})
        self.assertEqual(
            daw_agent.project_metrics(first)["recipeCount"],
            daw_agent.project_metrics(second)["recipeCount"],
        )
        self.assertEqual(
            daw_agent.project_metrics(first)["automationLaneCount"],
            daw_agent.project_metrics(second)["automationLaneCount"],
        )

    def test_retrieval_quality_check_passes(self) -> None:
        report = daw_agent.retrieval_check(limit=3)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["recallAtK"], 1.0)

    def test_sound_check_feedback_steers_next_agent_query(self) -> None:
        feedback = {
            "verdict": {"summary": "Kick and bass are fighting and the build feels static."},
            "issues": [
                {"area": "Low-end", "detail": "Kick and sub need sidechain separation."},
                {"area": "Arrangement", "detail": "The drop needs more transition energy."},
            ],
            "nextActions": [
                "Add a visible filter automation ramp into the drop.",
                "Tighten the bass ducking against the kick.",
            ],
        }
        query = daw_agent.feedback_query(feedback)
        self.assertIn("sidechain", query)
        self.assertIn("automation clips", query)
        ranked = daw_agent.retrieve_features(query, project=sample_project(), limit=3)
        ids = [item["id"] for item in ranked]
        self.assertIn("fl-automation-clips", ids)
        self.assertTrue({"fl-patcher-macro-chain", "fl-gross-beat-transition"} & set(ids))

    def test_run_agent_without_a_model_reports_ai_off(self) -> None:
        report = daw_agent.run_agent(sample_project(), query="automation", max_actions=1)
        self.assertEqual(report["ai"], {"used": False, "provider": None, "model": None, "note": "AI off for this run"})
        self.assertEqual(report["selectionSource"], "heuristic")
        self.assertEqual(report["selectedFeatures"][0]["decision"]["source"], "heuristic")


class ModelSelectionTests(PinnedEnvironment):
    def test_model_choice_is_applied_in_order_with_clamped_params_and_role_routing(self) -> None:
        assist, calls = fake_assist([
            {
                "trackRoles": {"fx": ["lead"], "lead": ["chords", "ghost-role"], "no-such-track": ["drums"]},
                "selectedFeatures": [
                    {"id": "bitwig-modulator-lane", "reason": "the drop never moves", "trackId": "fx",
                     "params": {"parameter": "pan", "points": [{"bar": 16, "value": 0.2}, {"bar": 500, "value": 1.7, "curve": "weird"}], "bogus": 1}},
                    {"id": "not-a-tactic", "reason": "made up"},
                    {"id": "fl-automation-clips", "reason": "the build is static", "params": {"parameter": "filter"}},
                    {"id": "fl-automation-clips", "reason": "repeated"},
                ],
            },
            {"summary": "Panned the FX and opened the lead filter across the build.", "actions": [{"featureId": "bitwig-modulator-lane", "why": "movement without new notes"}, {"featureId": "nope", "why": "x"}]},
        ])
        report = daw_agent.run_agent(sample_project(), query="movement", max_actions=4, assist=assist, feedback={"verdict": {"summary": "static"}})
        self.assertEqual(len(calls), 2, "one call to choose, one to narrate")
        self.assertIn("static", calls[0]["prompt"])
        self.assertEqual([item["id"] for item in report["selectedFeatures"]], ["bitwig-modulator-lane", "fl-automation-clips"])
        self.assertEqual(report["selectionSource"], "model")
        self.assertEqual(report["selectedFeatures"][0]["decision"], {"source": "model", "reason": "the drop never moves"})
        self.assertEqual(report["trackRoles"], {"fx": ["lead"], "lead": ["chords"]})
        self.assertTrue(any("ghost-role" in note for note in report["selectionNotes"]))
        self.assertTrue(any("not-a-tactic" in note for note in report["selectionNotes"]))

        lanes = {lane["id"]: lane for lane in report["updatedProject"]["snapshot"]["automationLanes"]}
        modulator = lanes["agent-width-motion-fx"]
        self.assertEqual(modulator["parameter"], "pan")
        self.assertEqual(modulator["points"][-1], {"bar": 24.0, "value": 1.0, "curve": "linear"}, "bar and value clamped, curve defaulted")
        # The model labelled the FX track as the lead, so the automation ramp lands there instead of on "Lead".
        self.assertEqual(lanes["agent-filter-rise-fx"]["trackId"], "fx")
        self.assertEqual(report["summary"], "Panned the FX and opened the lead filter across the build.")
        self.assertEqual(report["actions"][0]["why"], "movement without new notes")
        self.assertNotIn("why", report["actions"][1])
        self.assertTrue(report["ai"]["used"])
        self.assertEqual(daw_agent.duplicate_ids(report["updatedProject"]), {})

    def test_model_nonsense_falls_back_to_keyword_retrieval(self) -> None:
        assist, calls = fake_assist([{"selectedFeatures": [{"id": "nothing-real"}]}])
        report = daw_agent.run_agent(sample_project(), query="automation groove riff transition macro", max_actions=4, assist=assist)
        expected = [item["id"] for item in daw_agent.retrieve_features("automation groove riff transition macro", project=sample_project(), limit=8)][:4]
        self.assertEqual([item["id"] for item in report["selectedFeatures"]], expected)
        self.assertEqual(report["selectionSource"], "heuristic")
        self.assertIn("no known tactic", report["ai"]["note"])
        self.assertEqual(report["summary"], report["metricsSummary"])
        # The model answered, but nothing of it was used: the ai block agrees with selectionSource,
        # and the heuristic choice is not sent back for narration.
        self.assertFalse(report["ai"]["used"])
        self.assertEqual(len(calls), 1)

    def test_model_error_falls_back_to_keyword_retrieval(self) -> None:
        error = (400, json.dumps({"error": {"message": "bad request"}}))
        assist, calls = fake_assist([error])
        report = daw_agent.run_agent(sample_project(), query="automation", max_actions=2, assist=assist)
        self.assertEqual(report["selectionSource"], "heuristic")
        self.assertFalse(report["ai"]["used"])
        self.assertIn("bad request", report["ai"]["note"])
        self.assertEqual(len(calls), 1, "no narration call after selection fell back")
        self.assertEqual(report["summary"], report["metricsSummary"])

    def test_caller_named_tactics_never_count_as_a_model_use(self) -> None:
        assist, calls = fake_assist([{"summary": "should never be asked", "actions": []}])
        project = sample_project()
        features, _notes = daw_agent.explicit_features(["logic-drummer-fill"], {"logic-drummer-fill": {"trackId": "drums", "bars": 2, "beforeBar": 16}}, project)
        report = daw_agent.run_agent(project, query=None, max_actions=1, assist=assist, features=features)
        self.assertEqual(report["selectionSource"], "caller")
        self.assertFalse(report["ai"]["used"])
        self.assertIn("caller", report["ai"]["note"])
        self.assertEqual(calls, [])
        self.assertEqual(report["summary"], report["metricsSummary"])

    def test_validate_params_keeps_only_the_schema(self) -> None:
        project = sample_project()
        params, notes = daw_agent.validate_params("fl-riff-machine-variation", {
            "trackId": "ghost", "startBar": 200,
            "notes": [{"beat": 2, "note": 300, "duration": 9, "velocity": -1}, {"beat": "x"}, "junk"],
        }, project)
        self.assertNotIn("trackId", params)
        self.assertEqual(params["startBar"], 23.0)
        self.assertEqual(params["notes"], [{"beat": 2.0, "note": 96, "duration": 4.0, "velocity": 0.0}])
        self.assertTrue(any("ghost" in note for note in notes))
        params, notes = daw_agent.validate_params("fl-randomizer-groove", {"humanizeAmount": 3, "swingFloor": 99, "ghostBars": 0}, project)
        self.assertEqual(params, {"humanizeAmount": 1.0, "swingFloor": 30, "ghostBars": 1})
        self.assertEqual(daw_agent.validate_params("no-such", {"a": 1}, project), ({}, ["unknown tactic no-such"]))

    def test_explicit_features_via_cli_skip_the_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_path = root / "p.neon.json"
            project_path.write_text(json.dumps(sample_project()), encoding="utf-8")
            params_path = root / "params.json"
            params_path.write_text(json.dumps({"logic-drummer-fill": {"trackId": "drums", "bars": 2, "beforeBar": 16}}), encoding="utf-8")
            output = root / "out.neon.json"
            import contextlib
            import io
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = daw_agent.main([
                    "--root", tmp, "--ai", "off", "apply", "--project", str(project_path), "--output", str(output),
                    "--feature", "logic-drummer-fill", "--feature", "bogus", "--params-json", str(params_path), "--max-actions", "1",
                ])
            self.assertEqual(code, 0)
            report = json.loads(buffer.getvalue().strip().splitlines()[-1])
            self.assertEqual([a["featureId"] for a in report["actions"]], ["logic-drummer-fill"])
            self.assertEqual(report["selectionSource"], "caller")
            self.assertTrue(any("bogus" in note for note in report["selectionNotes"]))
            clip = next(clip for clip in json.loads(output.read_text())["snapshot"]["tracks"][0]["clips"] if clip["id"].startswith("agent-drum-fill"))
            self.assertEqual((clip["startBar"], clip["bars"]), (14.0, 2))


if __name__ == "__main__":
    unittest.main()
