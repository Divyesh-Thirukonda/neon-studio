#!/usr/bin/env python3
"""Tests for transcript_fidelity.py.

Run with:  /usr/bin/python3 -m unittest tools/test_transcript_fidelity.py

Every fixture is synthesised here - a kick click train and a bass tone that
is ducked (or not) at the kicks - so the expected answer is known before the
checker runs, and no test depends on a rendered file that may not exist.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import transcript_fidelity as tf  # noqa: E402

SR = tf.SR
BPM = 120
BAR_S = 240.0 / BPM
BEAT_S = BAR_S / 4.0
TOTAL_BARS = 12          # intro bars 0-4, drop bars 4-12 (0-indexed)
DROP_START_BAR = 4
TOOL = Path(__file__).resolve().parent / "transcript_fidelity.py"


def write_stereo_wav(path: Path, mono: np.ndarray, right: np.ndarray = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    left = np.clip(mono, -1.0, 1.0)
    right = left if right is None else np.clip(right, -1.0, 1.0)
    pcm = (np.stack([left, right], axis=1) * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(SR)
        handle.writeframes(pcm.tobytes())


def kick_onsets_seconds() -> list[float]:
    return [DROP_START_BAR * BAR_S + beat * BEAT_S for beat in range((TOTAL_BARS - DROP_START_BAR) * 4)]


def synth_drums() -> np.ndarray:
    """A 60 Hz sine burst with a sharp attack on every beat of the drop."""
    total = int(TOTAL_BARS * BAR_S * SR)
    out = np.zeros(total, dtype=np.float32)
    burst_len = int(0.08 * SR)
    t = np.arange(burst_len) / SR
    burst = (np.sin(2 * np.pi * 60.0 * t) * np.exp(-t * 40.0)).astype(np.float32)
    for onset in kick_onsets_seconds():
        start = int(onset * SR)
        out[start:start + burst_len] += burst * 0.8
    return out


def synth_bass(ducked: bool) -> np.ndarray:
    """A 55 Hz tone through the drop. When ducked, the gain drops to 0.15 for
    50 ms at each kick and ramps back over the next 150 ms."""
    total = int(TOTAL_BARS * BAR_S * SR)
    t = np.arange(total) / SR
    tone = (np.sin(2 * np.pi * 55.0 * t) * 0.5).astype(np.float32)
    gain = np.zeros(total, dtype=np.float32)
    drop_start = int(DROP_START_BAR * BAR_S * SR)
    gain[drop_start:] = 1.0
    if ducked:
        hold = int(0.05 * SR)
        ramp = int(0.15 * SR)
        for onset in kick_onsets_seconds():
            start = int(onset * SR)
            gain[start:start + hold] = 0.15
            gain[start + hold:start + hold + ramp] = np.linspace(0.15, 1.0, ramp, dtype=np.float32)
    return tone * gain


def base_project(bpm: int = BPM, key: str = "E Minor") -> dict:
    return {
        "id": "fixture",
        "name": "Fixture",
        "keyCenter": key,
        "updatedAt": "2026-01-01T00:00:00Z",
        "snapshot": {
            "bpm": bpm,
            "snap": "1/16",
            "loopEnabled": False,
            "loopStartBar": 0,
            "loopEndBar": TOTAL_BARS,
            "tracks": [
                {"id": "drums", "name": "Drums", "kind": "drum", "file": "/api/audio/fixture_drums.wav",
                 "instrument": "Kit", "color": "#ffffff", "gain": 0.9, "pan": 0.0, "steps": [0, 4, 8, 12],
                 "clips": [{"id": "c1", "name": "Drop drums", "startBar": DROP_START_BAR, "bars": 8, "lane": "drums", "color": "#fff", "type": "pattern"}],
                 "effects": []},
                {"id": "bass", "name": "Bass", "kind": "instrument", "file": "/api/audio/fixture_bass.wav",
                 "instrument": "Sub", "color": "#ffffff", "gain": 0.9, "pan": 0.0, "steps": [],
                 "clips": [{"id": "c2", "name": "Drop bass", "startBar": DROP_START_BAR, "bars": 8, "lane": "bass", "color": "#fff", "type": "pattern"}],
                 "effects": [{"id": "e1", "name": "Sidechain", "active": True, "amount": 0.7}]},
                {"id": "chords", "name": "Chords", "kind": "instrument", "file": None,
                 "instrument": "Pad", "color": "#ffffff", "gain": 0.8, "pan": 0.0, "steps": [],
                 "clips": [{"id": "c3", "name": "Intro chords", "startBar": 0, "bars": 4, "lane": "chords", "color": "#fff", "type": "pattern"}],
                 "effects": []},
            ],
            "controls": {},
            "notes": [{"id": "n1", "beat": 0.0, "duration": 4.0, "note": 52, "velocity": 0.8, "color": "#fff", "trackId": "chords"}],
            "automationLanes": [],
            "recipe": [
                {"id": "r1", "section": "Intro", "label": "Intro", "detail": "", "status": "todo", "trackIds": ["chords"]},
                {"id": "r2", "section": "Drop", "label": "Drop", "detail": "", "status": "todo", "trackIds": ["drums", "bass"]},
            ],
        },
    }


TRANSCRIPT = (
    "Section 1 Intro bars 1-4: filtered pad only.\n"
    "Section 2 Drop bars 5-12: sidechain the bass to the kick. Cut the pad at 474 Hz.\n"
)


def base_spec(tempo: int = BPM, key: str = "E minor") -> dict:
    return {
        "projectId": "fixture",
        "titleHint": "Fixture",
        "tempoHint": tempo,
        "keyHints": [key],
        "timecoded": False,
        "sections": [
            {"id": "s-intro", "type": "intro", "label": "Intro", "bars": 4, "startSeconds": None, "endSeconds": None,
             "summary": "", "excerpt": "", "transcriptText": "Section 1 Intro bars 1-4: filtered pad only.",
             "trackRoles": ["chords"], "techniques": [], "laneEvents": {}, "ordinalWithinType": 1},
            {"id": "s-drop", "type": "drop", "label": "Drop", "bars": 8, "startSeconds": None, "endSeconds": None,
             "summary": "", "excerpt": "", "transcriptText": "Section 2 Drop bars 5-12: sidechain the bass to the kick. Cut the pad at 474 Hz.",
             "trackRoles": ["drums", "bass"], "techniques": ["sidechain"], "laneEvents": {}, "ordinalWithinType": 1},
        ],
        "globalTracks": [],
        "globalTechniques": [{"name": "sidechain", "mentions": 1}],
        "arrangementNotes": [],
        "mixNotes": [],
        "automationNotes": [],
        # Our own inference - must never turn into a claim.
        "fillInBlanks": {"styleLane": "dark_bass", "decisions": [],
                         "gaps": [{"requirementId": "fx_return_discipline", "label": "Reverb on the lead",
                                   "step": "Add reverb", "section": "s-drop", "confidence": "inferred",
                                   "evidence": "inferred", "areas": ["Stereo"]}]},
    }


class Fixture:
    """Writes a root with data/, songlab/, and exports/ into a temp dir."""

    def __init__(self, tmp: str, project: dict = None, spec: dict = None, transcript: str = TRANSCRIPT,
                 ducked: bool = True, stems: bool = True) -> None:
        self.root = Path(tmp)
        self.project = project or base_project()
        self.spec = spec or base_spec()
        project_dir = self.root / "data" / "projects"
        spec_dir = self.root / "songlab" / "projects" / "fixture"
        project_dir.mkdir(parents=True, exist_ok=True)
        spec_dir.mkdir(parents=True, exist_ok=True)
        self.project_path = project_dir / "fixture.neon.json"
        self.spec_path = spec_dir / "transcript_spec.json"
        self.project_path.write_text(json.dumps(self.project))
        self.spec_path.write_text(json.dumps(self.spec))
        (spec_dir / "transcript.txt").write_text(transcript)
        if stems:
            write_stereo_wav(self.root / "exports" / "fixture_drums.wav", synth_drums())
            write_stereo_wav(self.root / "exports" / "fixture_bass.wav", synth_bass(ducked))

    def report(self) -> dict:
        return tf.build_report(self.root, self.project_path, self.spec_path)


def claims_in(report: dict, area: str) -> list[dict]:
    return [c for c in report["claims"] if c["area"] == area]


def claim_matching(report: dict, needle: str) -> dict:
    for claim in report["claims"]:
        if needle.lower() in claim["claim"].lower():
            return claim
    raise AssertionError(f"no claim mentions {needle!r}: {[c['claim'] for c in report['claims']]}")


class SidechainAudioTests(unittest.TestCase):
    """The core promise: audio evidence wins over an effect entry that says 'Sidechain'."""

    def test_ducked_bass_matches_from_audio(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = Fixture(tmp, ducked=True).report()
        claim = claim_matching(report, "uses sidechain")
        self.assertEqual(claim["status"], "matched")
        self.assertEqual(claim["verifiedBy"], "audio")
        self.assertIn("dB", claim["evidence"])
        depth = float(claim["evidence"].split("dips ")[1].split(" dB")[0])
        self.assertGreater(depth, 4.0)

    def test_unducked_bass_is_missing_despite_active_effect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = Fixture(tmp, ducked=False).report()
        claim = claim_matching(report, "uses sidechain")
        self.assertEqual(claim["status"], "missing")
        self.assertEqual(claim["verifiedBy"], "audio")
        self.assertTrue(any("Duck the bass" in action for action in report["nextActions"]), report["nextActions"])

    def test_no_stems_falls_back_to_project_effect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = Fixture(tmp, stems=False).report()
        claim = claim_matching(report, "uses sidechain")
        self.assertEqual(claim["status"], "matched")
        self.assertEqual(claim["verifiedBy"], "project")
        # The bass points at a file that is not on disk and has no notes or
        # steps to synthesise, so it is stated but silent. The drums still
        # count: their steps would be synthesised by the mixdown.
        bass = claim_matching(report, "bass part")
        self.assertEqual(bass["status"], "missing")
        self.assertIn("missing on disk", bass["evidence"])
        self.assertEqual(claim_matching(report, "drums part")["status"], "matched")


class MetadataClaimTests(unittest.TestCase):
    def test_tempo_mismatch_is_contradicted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = Fixture(tmp, project=base_project(bpm=128)).report()
        claim = claims_in(report, "tempo")[0]
        self.assertEqual(claim["status"], "contradicted")
        self.assertIn("128", claim["evidence"])
        self.assertTrue(any("120 BPM" in action for action in report["nextActions"]))

    def test_tempo_within_one_bpm_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = Fixture(tmp, project=base_project(bpm=121)).report()
        self.assertEqual(claims_in(report, "tempo")[0]["status"], "matched")

    def test_key_normalisation(self) -> None:
        self.assertEqual(tf.normalize_key("E minor"), "e minor")
        self.assertEqual(tf.normalize_key("E Minor"), "e minor")
        self.assertEqual(tf.normalize_key("Em"), "e minor")
        self.assertEqual(tf.normalize_key("F#m"), "f# minor")
        self.assertEqual(tf.normalize_key("D major"), "d major")
        self.assertEqual(tf.normalize_key("D"), "d major")
        self.assertIsNone(tf.normalize_key("nope"))
        with tempfile.TemporaryDirectory() as tmp:
            matched = Fixture(tmp, spec=base_spec(key="Em"), project=base_project(key="E Minor")).report()
        self.assertEqual(claims_in(matched, "key")[0]["status"], "matched")
        with tempfile.TemporaryDirectory() as tmp:
            wrong = Fixture(tmp, spec=base_spec(key="D major"), project=base_project(key="E Minor")).report()
        self.assertEqual(claims_in(wrong, "key")[0]["status"], "contradicted")

    def test_section_order_and_lengths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = Fixture(tmp).report()
        order = claims_in(report, "arrangement")[0]
        self.assertEqual(order["status"], "matched")
        self.assertIn("Intro -> Drop", order["claim"])
        lengths = {c["claim"].split(" spans")[0]: c["status"] for c in claims_in(report, "length")}
        self.assertEqual(lengths, {"Intro": "matched", "Drop": "matched"})

        reversed_project = base_project()
        reversed_project["snapshot"]["recipe"].reverse()
        with tempfile.TemporaryDirectory() as tmp:
            report = Fixture(tmp, project=reversed_project).report()
        order = claims_in(report, "arrangement")[0]
        self.assertEqual(order["status"], "contradicted")
        self.assertIn("position 1", order["evidence"])

    def test_section_length_off_by_more_than_four_bars_is_contradicted(self) -> None:
        project = base_project()
        for track in project["snapshot"]["tracks"]:
            for clip in track["clips"]:
                if clip["name"].startswith("Drop"):
                    clip["bars"] = 2
        with tempfile.TemporaryDirectory() as tmp:
            report = Fixture(tmp, project=project).report()
        drop = [c for c in claims_in(report, "length") if c["claim"].startswith("Drop")][0]
        self.assertEqual(drop["status"], "contradicted")
        self.assertIn("2 bars", drop["evidence"])

    def test_stated_but_silent_role_is_missing(self) -> None:
        spec = base_spec()
        spec["sections"][1]["trackRoles"].append("guitar")
        with tempfile.TemporaryDirectory() as tmp:
            report = Fixture(tmp, spec=spec).report()
        guitar = claim_matching(report, "guitar part")
        self.assertEqual(guitar["status"], "missing")
        chords = claim_matching(report, "chords part")
        self.assertEqual(chords["status"], "matched")      # content via notes, no file
        self.assertIn("notes", chords["evidence"])

    def test_fill_in_blanks_never_becomes_a_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = Fixture(tmp).report()
        self.assertFalse(any("reverb" in c["claim"].lower() for c in report["claims"]))


class ExplicitNumberTests(unittest.TestCase):
    def test_unmatched_hz_is_unverifiable_with_quote(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = Fixture(tmp).report()
        claim = claim_matching(report, "474 HZ")
        self.assertEqual(claim["status"], "unverifiable")
        self.assertIn("474 hz", claim["evidence"].lower())
        self.assertIn("Cut the pad", claim["evidence"])
        self.assertEqual(report["unverifiable"], 1)

    def test_hz_named_by_an_effect_matches(self) -> None:
        project = base_project()
        project["snapshot"]["tracks"][2]["effects"].append({"id": "e9", "name": "Low Cut 474 Hz", "active": True, "amount": 0.5})
        with tempfile.TemporaryDirectory() as tmp:
            report = Fixture(tmp, project=project).report()
        self.assertEqual(claim_matching(report, "474 HZ")["status"], "matched")

    def test_automation_statements(self) -> None:
        transcript = TRANSCRIPT + "Automation: bars 1-4 chords.filter 0.2->0.8 ease-in | fx.width 0.3->0.7.\n"
        lane = {"id": "a1", "trackId": "chords", "parameter": "filter", "label": "Chords Filter",
                "points": [{"bar": 0, "value": 0.2}, {"bar": 4, "value": 0.8}]}
        project = base_project()
        project["snapshot"]["automationLanes"] = [lane]
        with tempfile.TemporaryDirectory() as tmp:
            report = Fixture(tmp, project=project, transcript=transcript).report()
        by_claim = {c["claim"]: c for c in claims_in(report, "automation")}
        self.assertEqual(by_claim["chords.filter moves 0.2 -> 0.8 over bars 1-4."]["status"], "matched")
        self.assertEqual(by_claim["fx.width moves 0.3 -> 0.7 over bars 1-4."]["status"], "missing")

        lane["points"] = [{"bar": 0, "value": 0.9}, {"bar": 4, "value": 0.1}]
        with tempfile.TemporaryDirectory() as tmp:
            report = Fixture(tmp, project=project, transcript=transcript).report()
        by_claim = {c["claim"]: c for c in claims_in(report, "automation")}
        self.assertEqual(by_claim["chords.filter moves 0.2 -> 0.8 over bars 1-4."]["status"], "contradicted")


class ScoringAndOutputTests(unittest.TestCase):
    def test_score_counts_only_checkable_claims(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = Fixture(tmp).report()
        matched = sum(1 for c in report["claims"] if c["status"] == "matched")
        checkable = sum(1 for c in report["claims"] if c["status"] != "unverifiable")
        self.assertEqual(report["score"], int(round(100.0 * matched / checkable)))
        self.assertIn(f"{matched} of {checkable}", report["summary"])
        for claim in report["claims"]:
            self.assertIn(claim["status"], ("matched", "missing", "contradicted", "unverifiable"))
            self.assertIn(claim["verifiedBy"], ("audio", "project", "spec"))

    def test_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(tmp)
            first = json.dumps(fixture.report(), sort_keys=True)
            second = json.dumps(fixture.report(), sort_keys=True)
        self.assertEqual(first, second)

    def test_markdown_lists_claims_and_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = Fixture(tmp, ducked=False).report()
        text = tf.render_markdown(report)
        self.assertIn("| Status |", text)
        self.assertIn("missing (audio)", text)
        self.assertIn("## Next Actions", text)

    def test_cli_json_is_last_line_and_failure_is_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Fixture(tmp)
            result = subprocess.run(
                [sys.executable, str(TOOL), "--root", tmp, "--project-id", "fixture", "--format", "json"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout.strip().splitlines()[-1])
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["projectId"], "fixture")
            self.assertIsInstance(payload["score"], int)

            failure = subprocess.run(
                [sys.executable, str(TOOL), "--root", tmp, "--project-id", "does-not-exist"],
                capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(failure.returncode, 0)
            payload = json.loads(failure.stdout.strip().splitlines()[-1])
            self.assertFalse(payload["ok"])
            self.assertIn("error", payload)


class HelperTests(unittest.TestCase):
    def test_parse_section_label(self) -> None:
        self.assertEqual(tf.parse_section_label("Drop 2 drums"), ("drop", 2))
        self.assertEqual(tf.parse_section_label("Second Drop"), ("drop", 2))
        self.assertEqual(tf.parse_section_label("Build 1 riser"), ("build", 1))
        self.assertEqual(tf.parse_section_label("Sparse verse texture"), ("verse", None))
        self.assertEqual(tf.parse_section_label("Breakdown"), ("break", None))
        self.assertIsNone(tf.parse_section_label("Foundation"))
        self.assertIsNone(tf.parse_section_label("Builds"))

    def test_project_section_spans_from_clips(self) -> None:
        spans = tf.project_section_spans(base_project())
        self.assertEqual(spans[("intro", 1)], (0.0, 4.0))
        self.assertEqual(spans[("drop", 1)], (4.0, 12.0))

    def test_median_f0_resolves_octave_above_autocorrelation_range(self) -> None:
        t = np.arange(int(2.0 * SR)) / SR
        low = (np.sin(2 * np.pi * 440.0 * t) * 0.5).astype(np.float32)
        high = (np.sin(2 * np.pi * 880.0 * t) * 0.5).astype(np.float32)
        f_low = tf.median_f0_hz(low)
        f_high = tf.median_f0_hz(high)
        self.assertAlmostEqual(f_low, 440.0, delta=8.0)
        self.assertAlmostEqual(f_high, 880.0, delta=16.0)


if __name__ == "__main__":
    unittest.main()


class NewMeasurementTests(unittest.TestCase):
    """Section ordinals, the reverb residual, brightness, and the eq /
    compression / reverse witnesses."""

    def test_plain_drop_beside_second_drop_is_drop_one(self) -> None:
        project = base_project()
        tracks = project["snapshot"]["tracks"]
        tracks[0]["clips"] = [
            {"id": "a", "name": "Drop drums", "startBar": 8, "bars": 8, "lane": "drums", "color": "#fff", "type": "pattern"},
            {"id": "b", "name": "Second Drop drums", "startBar": 24, "bars": 8, "lane": "drums", "color": "#fff", "type": "pattern"},
        ]
        tracks[1]["clips"] = []
        tracks[2]["clips"] = []
        spans = tf.project_section_spans(project)
        self.assertEqual(spans[("drop", 1)], (8.0, 16.0))
        self.assertEqual(spans[("drop", 2)], (24.0, 32.0))
        self.assertNotIn(("drop", 3), spans)

    @staticmethod
    def notes(wet: bool, count: int = 6, gap: float = 0.5) -> np.ndarray:
        """Short 1 kHz notes with a 5 ms release; the wet ones drag a -10 dB
        tail with a 0.4 s time constant behind them."""
        sr = tf.SR
        total = np.zeros(int((count + 1) * gap * sr), dtype=np.float32)
        t = np.arange(int(0.1 * sr)) / sr
        note = np.sin(2 * np.pi * 1000 * t) * np.minimum(1.0, (0.1 - t) / 0.005)
        tail_t = np.arange(int(gap * sr)) / sr
        tail = np.sin(2 * np.pi * 1000 * tail_t) * np.exp(-tail_t / 0.4) * 0.3
        for index in range(count):
            at = int(index * gap * sr)
            total[at:at + len(note)] += note.astype(np.float32)
            if wet:
                total[at + len(note):at + len(note) + len(tail)] += tail.astype(np.float32)
        return total

    def test_tail_residual_separates_wet_from_dry(self) -> None:
        dry = tf.tail_residual_db(self.notes(wet=False))
        wet = tf.tail_residual_db(self.notes(wet=True))
        self.assertIsNotNone(dry)
        self.assertIsNotNone(wet)
        self.assertLess(dry[0], -40.0)
        self.assertGreater(wet[0], -30.0)

    def test_band_share_reads_where_the_energy_is(self) -> None:
        t = np.arange(tf.SR) / tf.SR
        bright = np.sin(2 * np.pi * 4000 * t).astype(np.float32)
        self.assertGreater(tf.band_share_db(bright, 2000.0, 8000.0), -1.0)
        self.assertLess(tf.band_share_db(bright, 0.0, 100.0), -60.0)

    def checker_with(self, tmp: str, stems: dict) -> "tuple[tf.Checker, tuple[float, float]]":
        """A Checker over a project whose tracks point at the given stems."""
        project = base_project()
        tracks = project["snapshot"]["tracks"]
        for track_id, audio in stems.items():
            existing = next((t for t in tracks if t["id"] == track_id), None)
            if existing is None:
                existing = {"id": track_id, "name": track_id.title(), "kind": "instrument", "instrument": "Synth",
                            "color": "#ffffff", "gain": 0.8, "pan": 0.0, "steps": [], "clips": [], "effects": []}
                tracks.append(existing)
            existing["file"] = f"/api/audio/fixture_{track_id}.wav"
        fixture = Fixture(tmp, project=project, stems=False)
        for track_id, audio in stems.items():
            write_stereo_wav(fixture.root / "exports" / f"fixture_{track_id}.wav", audio)
        checker = tf.Checker(fixture.root, fixture.project, fixture.spec, TRANSCRIPT)
        return checker, (float(DROP_START_BAR), float(DROP_START_BAR + 8))

    @staticmethod
    def bar_seconds() -> float:
        return 4.0 * 60.0 / BPM

    def test_reverse_swell_is_heard_on_the_fx_lane(self) -> None:
        sr = tf.SR
        total = np.zeros(int((DROP_START_BAR + 8) * self.bar_seconds() * sr), dtype=np.float32)
        start = int(DROP_START_BAR * self.bar_seconds() * sr)
        length = int(0.5 * self.bar_seconds() * sr)
        ramp = np.linspace(0.0, 1.0, length) ** 2
        rising = (np.random.default_rng(1).standard_normal(length) * 0.3 * ramp).astype(np.float32)
        total[start - length:start] = rising
        with tempfile.TemporaryDirectory() as tmp:
            checker, span = self.checker_with(tmp, {"fx": total})
            status, evidence = checker.measure_reverse(span)
            self.assertEqual(status, "matched", evidence)
        flat = total.copy()
        flat[start - length:start] = (np.random.default_rng(1).standard_normal(length) * 0.3).astype(np.float32)
        with tempfile.TemporaryDirectory() as tmp:
            checker, span = self.checker_with(tmp, {"fx": flat})
            status, evidence = checker.measure_reverse(span)
            self.assertEqual(status, "missing", evidence)

    def test_eq_reads_the_low_end_share_of_the_melodic_lanes(self) -> None:
        sr = tf.SR
        seconds = (DROP_START_BAR + 8) * self.bar_seconds()
        t = np.arange(int(seconds * sr)) / sr
        clean = (np.sin(2 * np.pi * 1000 * t) * 0.3).astype(np.float32)
        muddy = (clean + np.sin(2 * np.pi * 60 * t) * 0.3).astype(np.float32)
        with tempfile.TemporaryDirectory() as tmp:
            checker, span = self.checker_with(tmp, {"chords": clean})
            status, evidence = checker.measure_eq(span)
            self.assertEqual(status, "matched", evidence)
        with tempfile.TemporaryDirectory() as tmp:
            checker, span = self.checker_with(tmp, {"chords": muddy})
            status, evidence = checker.measure_eq(span)
            self.assertEqual(status, "missing", evidence)
            self.assertIn("chords", evidence)

    def drum_hits(self, levels_db: list) -> np.ndarray:
        sr = tf.SR
        total = np.zeros(int((DROP_START_BAR + 8) * self.bar_seconds() * sr), dtype=np.float32)
        start = DROP_START_BAR * self.bar_seconds()
        t = np.arange(int(0.08 * sr)) / sr
        body = np.random.default_rng(4).standard_normal(len(t)) * np.exp(-t / 0.03) * 0.4
        for index, level in enumerate(levels_db):
            at = int((start + index * 0.5) * sr)
            total[at:at + len(t)] += (body * 10.0 ** (level / 20.0)).astype(np.float32)
        return total

    def test_compression_reads_hit_consistency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            checker, span = self.checker_with(tmp, {"drums": self.drum_hits([0.0, -0.5, 0.0, -0.5] * 4)})
            status, evidence = checker.measure_compression(span)
            self.assertEqual(status, "matched", evidence)
        with tempfile.TemporaryDirectory() as tmp:
            checker, span = self.checker_with(tmp, {"drums": self.drum_hits([0.0, -9.0, -3.0, -6.0] * 4)})
            status, evidence = checker.measure_compression(span)
            self.assertEqual(status, "missing", evidence)
