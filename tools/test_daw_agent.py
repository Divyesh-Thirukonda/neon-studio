#!/usr/bin/env python3
"""Unit tests for the deterministic DAW agent."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import daw_agent


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


class DawAgentTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
