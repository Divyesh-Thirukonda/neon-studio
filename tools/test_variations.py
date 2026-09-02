#!/usr/bin/env python3
"""Tests for variations.py and the preview window/solo options in render_mixdown.

Run with:  /usr/bin/python3 -m unittest tools/test_variations.py

Everything is synthesised: the fixture project has no audio files, so every
preview comes from the built-in instrument and the suite never depends on a
stem that may not exist.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
import wave
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import render_mixdown  # noqa: E402
import variations  # noqa: E402


E_MINOR = {4, 6, 7, 9, 11, 0, 2}
BPM = 128


def fixture_project() -> dict:
    """A small project: lead with a hook in bars 24-40, drums, a bare bass, an FX lane."""
    lead_notes = []
    hook = [(0.0, 76, 0.5), (0.5, 79, 0.5), (1.0, 83, 1.0), (2.0, 81, 0.5), (2.5, 79, 0.5), (3.0, 76, 1.0)]
    for bar in range(24, 40):
        for index, (offset, pitch, duration) in enumerate(hook):
            lead_notes.append({
                "id": f"lead-{bar}-{index}",
                "beat": bar * 4 + offset,
                "duration": duration,
                "note": pitch,
                "velocity": 0.9 if offset in (0.0, 2.0) else 0.7,
                "color": "#60c8f8",
                "trackId": "lead",
            })

    def clip(track_id, name, start, bars):
        return {"id": f"{track_id}-{start}", "name": name, "startBar": start, "bars": bars,
                "lane": track_id, "color": "#ffffff", "type": "pattern"}

    return {
        "id": "test-song",
        "name": "Test Song",
        "keyCenter": "E Minor",
        "updatedAt": "2026-01-01T00:00:00Z",
        "assets": [],
        "snapshot": {
            "bpm": BPM,
            "snap": "1/16",
            "loopEnabled": False,
            "loopStartBar": 24,
            "loopEndBar": 40,
            "selectedTrackId": "lead",
            "tracks": [
                {"id": "drums", "name": "Drums", "kind": "drum", "file": None, "instrument": "Kit",
                 "color": "#ff8d5c", "gain": 0.8, "pan": 0.0, "steps": [0, 4, 8, 12],
                 "clips": [clip("drums", "Verse drums", 8, 16), clip("drums", "Drop drums", 24, 16)], "effects": []},
                {"id": "lead", "name": "Lead", "kind": "instrument", "file": None, "instrument": "Lead Synth",
                 "color": "#60c8f8", "gain": 0.8, "pan": 0.0, "steps": [],
                 "clips": [clip("lead", "Intro lead", 0, 8), clip("lead", "Drop lead", 24, 16)], "effects": []},
                {"id": "bass", "name": "Bass", "kind": "instrument", "file": None, "instrument": "Mono Bass",
                 "color": "#a0ffa0", "gain": 0.8, "pan": 0.0, "steps": [],
                 "clips": [clip("bass", "Drop bass", 24, 16)], "effects": []},
                {"id": "fx", "name": "FX", "kind": "audio", "file": None, "instrument": "Risers",
                 "color": "#d78bff", "gain": 0.8, "pan": 0.0, "steps": [],
                 "clips": [clip("fx", "Build riser", 16, 8)], "effects": []},
            ],
            "controls": {},
            "notes": lead_notes,
            "automationLanes": [
                {"id": "auto-fx", "trackId": "fx", "parameter": "filter", "label": "Riser Filter",
                 "color": "#d78bff", "curve": "ease-in", "enabled": True,
                 "points": [{"bar": 16, "value": 0.3}, {"bar": 24, "value": 0.9}]},
            ],
            "recipe": [
                {"id": "drop", "section": "Drop", "label": "Main drop", "detail": "", "status": "planned",
                 "trackIds": ["lead", "drums"], "startBar": 24, "bars": 16},
            ],
        },
    }


def without_track(project: dict, track_id: str) -> dict:
    """Everything in a project that is not the given track, for diffing."""
    stripped = deepcopy(project)
    snapshot = stripped["snapshot"]
    snapshot["tracks"] = [t for t in snapshot["tracks"] if t["id"] != track_id]
    snapshot["notes"] = [n for n in snapshot["notes"] if variations.note_owner(n, snapshot) != track_id]
    snapshot["automationLanes"] = [l for l in snapshot["automationLanes"] if l["trackId"] != track_id]
    stripped["assets"] = [a for a in stripped.get("assets", []) if a.get("trackId") != track_id]
    return stripped


def wav_seconds(path: str) -> float:
    with wave.open(path, "rb") as handle:
        return handle.getnframes() / handle.getframerate()


class VariationsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = fixture_project()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_tool(self, track_id: str, section: str, count: int = 3, seed: int = 7, render: bool = True, subdir: str = "out") -> dict:
        return variations.generate_variations(
            self.root, deepcopy(self.project), track_id, section,
            count=count, seed=seed, output_dir=self.root / subdir, render=render,
        )

    def test_writes_count_variants_that_only_touch_the_target(self) -> None:
        result = self.run_tool("lead", "Drop", count=4, render=False)
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["variations"]), 4)
        self.assertEqual(result["target"]["laneKind"], "melodic")
        self.assertEqual((result["target"]["startBar"], result["target"]["bars"]), (24, 16))
        baseline = without_track(self.project, "lead")
        seen = set()
        for variation in result["variations"]:
            path = Path(variation["project"])
            self.assertTrue(path.exists(), path)
            written = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(without_track(written, "lead"), baseline, "a variant changed more than the target track")
            lead = next(t for t in written["snapshot"]["tracks"] if t["id"] == "lead")
            self.assertIsNone(lead["file"], "the stale stem must be cleared so the edit is audible")
            self.assertTrue(variation["label"])
            self.assertTrue(variation["description"])
            self.assertGreater(variation["changes"]["notes"], 0)
            seen.add(json.dumps(written["snapshot"]["notes"], sort_keys=True))
        self.assertEqual(len(seen), 4, "the four variants should all be different")

    def test_notes_stay_in_key_and_inside_the_section(self) -> None:
        result = self.run_tool("lead", "Drop", count=4, render=False)
        for variation in result["variations"]:
            written = json.loads(Path(variation["project"]).read_text(encoding="utf-8"))
            section_notes = [n for n in written["snapshot"]["notes"] if n["trackId"] == "lead" and 96 <= n["beat"] < 160]
            self.assertTrue(section_notes)
            for note in section_notes:
                self.assertIn(note["note"] % 12, E_MINOR, f"{variation['label']} left the key: {note}")
                self.assertLessEqual(note["beat"] + note["duration"], 160.0 + 1e-6)
                self.assertGreaterEqual(note["velocity"], 0.05)
                self.assertLessEqual(note["velocity"], 1.0)
            # Notes outside the section are untouched.
            outside = [n for n in written["snapshot"]["notes"] if n["trackId"] == "lead" and not 96 <= n["beat"] < 160]
            self.assertEqual(outside, [n for n in self.project["snapshot"]["notes"] if not 96 <= n["beat"] < 160])

    def test_section_by_bar_range_matches_section_by_name(self) -> None:
        by_name = self.run_tool("lead", "Drop", render=False, subdir="a")
        by_range = self.run_tool("lead", "24-40", render=False, subdir="b")
        for left, right in zip(by_name["variations"], by_range["variations"]):
            notes_left = json.loads(Path(left["project"]).read_text())["snapshot"]["notes"]
            notes_right = json.loads(Path(right["project"]).read_text())["snapshot"]["notes"]
            self.assertEqual(
                [variations.note_signature(n) for n in notes_left],
                [variations.note_signature(n) for n in notes_right],
            )

    def test_unknown_section_is_an_error(self) -> None:
        with self.assertRaises(ValueError):
            self.run_tool("lead", "Chorus", render=False)
        with self.assertRaises(ValueError):
            self.run_tool("nope", "Drop", render=False)

    def test_drum_fill_variant_adds_hits(self) -> None:
        result = self.run_tool("drums", "Drop", count=3, render=False)
        self.assertEqual(result["target"]["laneKind"], "drums")
        labels = [v["label"] for v in result["variations"]]
        fill = next(v for v in result["variations"] if v["label"].startswith("Fill"))
        written = json.loads(Path(fill["project"]).read_text(encoding="utf-8"))
        drums = next(t for t in written["snapshot"]["tracks"] if t["id"] == "drums")

        def hits_in_window(track, notes):
            per_bar = len(set(track["steps"]))
            fill_notes = [n for n in notes if n.get("trackId") == "drums" and 96 <= n["beat"] < 160]
            return per_bar * 16 + len(fill_notes)

        original_hits = hits_in_window(self.project["snapshot"]["tracks"][0], self.project["snapshot"]["notes"])
        self.assertGreater(hits_in_window(drums, written["snapshot"]["notes"]), original_hits)
        self.assertEqual(fill["changes"]["notes"], 4)
        fill_notes = [n for n in written["snapshot"]["notes"] if n.get("trackId") == "drums"]
        self.assertTrue(all(39 * 4 + 3 <= n["beat"] < 160 for n in fill_notes), "fill hits belong on the last bar")
        self.assertTrue(any(c["startBar"] == 39 and c["bars"] == 1 for c in drums["clips"]), "fill gets its own clip")
        self.assertEqual(without_track(written, "drums"), without_track(self.project, "drums"))
        self.assertIn("Off-beat hats added", labels)
        self.assertIn("Half-time feel", labels)

    def test_previews_exist_and_have_the_section_length(self) -> None:
        result = self.run_tool("lead", "Drop", count=2)
        expected = 16 * 4 * 60.0 / BPM
        for variation in result["variations"]:
            self.assertTrue(Path(variation["preview"]).exists())
            self.assertAlmostEqual(wav_seconds(variation["preview"]), expected, delta=0.1)
        self.assertEqual(result["previewNote"], variations.PREVIEW_NOTE)

    def test_same_seed_is_byte_identical(self) -> None:
        first = self.run_tool("lead", "Drop", count=4, seed=3, render=False, subdir="one")
        second = self.run_tool("lead", "Drop", count=4, seed=3, render=False, subdir="two")
        for left, right in zip(first["variations"], second["variations"]):
            self.assertEqual(Path(left["project"]).read_bytes(), Path(right["project"]).read_bytes())
            self.assertEqual(left["label"], right["label"])

    def test_melodic_lane_without_notes_gets_a_seeded_phrase(self) -> None:
        result = self.run_tool("bass", "Drop", count=2, render=False)
        self.assertEqual(result["target"]["laneKind"], "melodic")
        for variation in result["variations"]:
            self.assertIn("seeded", variation["label"])
            written = json.loads(Path(variation["project"]).read_text(encoding="utf-8"))
            bass_notes = [n for n in written["snapshot"]["notes"] if n.get("trackId") == "bass"]
            self.assertTrue(bass_notes)
            self.assertTrue(all(n["note"] % 12 in E_MINOR for n in bass_notes))
            self.assertTrue(all(96 <= n["beat"] < 160 for n in bass_notes))

    def test_automation_lane_endpoints_move_by_a_quarter(self) -> None:
        result = self.run_tool("fx", "16-24", count=3, render=False)
        self.assertEqual(result["target"]["laneKind"], "automation")
        self.assertIn("previewCaveat", result)
        for variation in result["variations"]:
            written = json.loads(Path(variation["project"]).read_text(encoding="utf-8"))
            lane = next(l for l in written["snapshot"]["automationLanes"] if l["id"] == "auto-fx")
            values = {p["bar"]: p["value"] for p in lane["points"]}
            self.assertGreater(variation["changes"]["automation"], 0)
            self.assertTrue(all(0.0 <= v <= 1.0 for v in values.values()))
            start_delta = round(values[16] - 0.3, 4)
            end_delta = round(values[24] - 0.9, 4)
            self.assertIn(start_delta, (0.0, -0.25))
            self.assertIn(end_delta, (0.0, 0.1))  # 0.9 + 0.25 clamps to 1.0
            self.assertNotEqual((start_delta, end_delta, lane["curve"]), (0.0, 0.0, "ease-in"))
            self.assertEqual(without_track(written, "fx"), without_track(self.project, "fx"))

    def test_key_parsing(self) -> None:
        self.assertEqual(variations.parse_key("E Minor"), E_MINOR)
        self.assertEqual(variations.parse_key("D major"), {2, 4, 6, 7, 9, 11, 1})
        self.assertEqual(variations.parse_key("Bb Dorian"), {10, 0, 1, 3, 5, 7, 8})
        self.assertIsNone(variations.parse_key(None))
        self.assertIsNone(variations.parse_key("???"))


class RenderMixdownWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = fixture_project()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_window_crops_to_exact_length(self) -> None:
        mix, sample_rate, info = render_mixdown.mix_project(self.root, self.project, start_bar=24, bars=8)
        expected = 8 * 4 * 60.0 / BPM
        self.assertAlmostEqual(len(mix) / sample_rate, expected, delta=0.01)
        self.assertEqual((info["startBar"], info["bars"]), (24, 8))
        # A window past the end of the song is padded, not truncated.
        mix, sample_rate, _ = render_mixdown.mix_project(self.root, self.project, start_bar=400, bars=2)
        self.assertAlmostEqual(len(mix) / sample_rate, 2 * 4 * 60.0 / BPM, delta=0.01)
        self.assertEqual(float(abs(mix).max()), 0.0)

    def test_solo_track_keeps_drums_for_context(self) -> None:
        _, _, lead_info = render_mixdown.mix_project(self.root, self.project, solo_track="lead")
        self.assertEqual(lead_info["tracksMixed"], 2)  # lead + drums
        _, _, drum_info = render_mixdown.mix_project(self.root, self.project, solo_track="drums")
        self.assertEqual(drum_info["tracksMixed"], 1)
        with self.assertRaises(RuntimeError):
            render_mixdown.mix_project(self.root, self.project, solo_track="ghost")

    def test_default_mix_is_unchanged_by_the_new_options(self) -> None:
        mix, sample_rate, info = render_mixdown.mix_project(self.root, self.project)
        self.assertNotIn("startBar", info)
        self.assertNotIn("soloTrack", info)
        self.assertGreater(len(mix) / sample_rate, 39 * 4 * 60.0 / BPM)


if __name__ == "__main__":
    unittest.main()
