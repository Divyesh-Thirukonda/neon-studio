#!/usr/bin/env python3
"""Tests for hum_to_melody.py — hummed take in, piano-roll notes out.

Run with:  /usr/bin/python3 -m unittest tools/test_hum_to_melody.py

Every take is synthesised here with numpy (sines at known MIDI pitches with
silences between them) so nothing depends on a file that may not exist.
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

from hum_to_melody import (  # noqa: E402
    NO_VOICE_WARNING,
    SR,
    analyse_file,
    hum_to_melody,
    parse_key,
)
from vocal_autotune import midi_to_freq  # noqa: E402

BPM = 142.0
BEAT = 60.0 / BPM
GRID = 0.5  # 1/8 note in beats


def synth_take(events, sr=SR, amplitude=0.5):
    """events: list of (midi, start_beats, length_beats[, amplitude]).

    Returns a float32 mono buffer at `sr` with 5 ms fades on each note so the
    edges do not click and the pitch tracker sees clean sine periods.
    """
    total_beats = max(start + length for _, start, length, *_ in events) + 0.5
    out = np.zeros(int(total_beats * BEAT * sr) + sr // 10, dtype=np.float32)
    for event in events:
        midi, start, length = event[:3]
        amp = event[3] if len(event) > 3 else amplitude
        begin = int(start * BEAT * sr)
        count = int(length * BEAT * sr)
        t = np.arange(count) / sr
        tone = np.sin(2.0 * np.pi * midi_to_freq(midi) * t).astype(np.float32) * amp
        fade = min(int(0.005 * sr), count // 4)
        if fade > 0:
            ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
            tone[:fade] *= ramp
            tone[-fade:] *= ramp[::-1]
        out[begin:begin + count] += tone
    return out


def write_take(path, audio, sr):
    pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sr)
        handle.writeframes(pcm.tobytes())


class SegmentationTests(unittest.TestCase):
    def test_sequence_with_gaps_matches_pitches_onsets_and_durations(self):
        # Four notes, one per beat, each sounding for 0.8 beat with a 0.2 beat
        # (~85 ms) silence — longer than the 60 ms gap rule, so four notes.
        events = [(64, 0.0, 0.8), (67, 1.0, 0.8), (71, 2.0, 0.8), (69, 3.0, 0.8)]
        result = hum_to_melody(synth_take(events), bpm=BPM, start_bar=8, track_id="lead")
        self.assertTrue(result["ok"])
        notes = result["notes"]
        self.assertEqual([n["note"] for n in notes], [64, 67, 71, 69])
        for note, (midi, start, length) in zip(notes, events):
            self.assertAlmostEqual(note["beat"], 32.0 + start, delta=GRID)
            self.assertAlmostEqual(note["duration"], length, delta=GRID)
            self.assertEqual(note["trackId"], "lead")
            self.assertTrue(note["id"].startswith("hum-"))
        self.assertEqual(result["detected"]["octaveShift"], 0)
        self.assertEqual(result["detected"]["segments"], 4)
        self.assertNotIn(NO_VOICE_WARNING, result["warnings"])

    def test_legato_pitch_change_splits_into_two_notes(self):
        # No silence at all between the two pitches: only the >0.6 semitone
        # jump held for 3 frames can separate them.
        events = [(64, 0.0, 1.0), (67, 1.0, 1.0)]
        result = hum_to_melody(synth_take(events), bpm=BPM, start_bar=0)
        self.assertEqual([n["note"] for n in result["notes"]], [64, 67])
        self.assertAlmostEqual(result["notes"][1]["beat"], 1.0, delta=GRID)

    def test_quiet_note_gets_lower_velocity(self):
        events = [(64, 0.0, 0.8, 0.5), (64, 1.0, 0.8, 0.12)]
        result = hum_to_melody(synth_take(events), bpm=BPM)
        self.assertEqual(len(result["notes"]), 2)
        loud, quiet = result["notes"]
        self.assertGreater(loud["velocity"], quiet["velocity"])
        self.assertAlmostEqual(loud["velocity"], 1.0, delta=0.05)
        self.assertGreaterEqual(quiet["velocity"], 0.45)

    def test_beats_are_absolute_from_start_bar(self):
        result = hum_to_melody(synth_take([(64, 0.0, 0.8)]), bpm=BPM, start_bar=8)
        self.assertAlmostEqual(result["notes"][0]["beat"], 32.0, delta=GRID)


class KeyTests(unittest.TestCase):
    def test_parse_key_variants(self):
        self.assertEqual(parse_key("E minor")["scale"], {4, 6, 7, 9, 11, 0, 2})
        self.assertEqual(parse_key("E Minor")["name"], "E minor")
        self.assertEqual(parse_key("Em")["mode"], "minor")
        self.assertEqual(parse_key("F# major")["root"], 6)
        self.assertEqual(parse_key("Gb major")["root"], 6)
        self.assertEqual(parse_key("Gb major")["name"], "Gb major")
        self.assertEqual(parse_key("e_minor")["mode"], "minor")
        self.assertEqual(parse_key("D Major")["scale"], {2, 4, 6, 7, 9, 11, 1})
        self.assertIsNone(parse_key("nope"))

    def test_key_snap_moves_off_scale_pitch_to_nearest_scale_note(self):
        # 68.3 is a slightly sharp G#: not in E minor, and closer to A (69)
        # than to G (67).
        take = synth_take([(68.3, 0.0, 0.8)])
        snapped = hum_to_melody(take, bpm=BPM, key="E minor")
        self.assertEqual(snapped["notes"][0]["note"], 69)
        self.assertEqual(snapped["detected"]["keyUsed"], "E minor")
        chromatic = hum_to_melody(take, bpm=BPM, key="E minor", key_snap=False)
        self.assertEqual(chromatic["notes"][0]["note"], 68)
        self.assertIsNone(chromatic["detected"]["keyUsed"])

    def test_unknown_key_warns_and_stays_chromatic(self):
        result = hum_to_melody(synth_take([(68.3, 0.0, 0.8)]), bpm=BPM, key="purple")
        self.assertEqual(result["notes"][0]["note"], 68)
        self.assertTrue(any("Could not read key" in w for w in result["warnings"]))


class RangeTests(unittest.TestCase):
    def test_low_hum_is_shifted_up_an_octave(self):
        # G2 / A2 / B2 — a low hum whose median (45) is under MIDI 48.
        events = [(43, 0.0, 0.8), (45, 1.0, 0.8), (47, 2.0, 0.8)]
        result = hum_to_melody(synth_take(events), bpm=BPM)
        self.assertEqual(result["detected"]["octaveShift"], 12)
        self.assertEqual([n["note"] for n in result["notes"]], [55, 57, 59])
        self.assertAlmostEqual(result["detected"]["medianMidi"], 45.0, delta=0.2)
        self.assertTrue(any("octave" in w for w in result["warnings"]))


class EdgeCaseTests(unittest.TestCase):
    def test_silence_yields_no_notes_and_a_warning(self):
        result = hum_to_melody(np.zeros(SR * 2, dtype=np.float32), bpm=BPM)
        self.assertTrue(result["ok"])
        self.assertEqual(result["notes"], [])
        self.assertIn(NO_VOICE_WARNING, result["warnings"])
        self.assertEqual(result["detected"]["voicedSeconds"], 0.0)

    def test_48k_input_is_resampled_and_analysed(self):
        events = [(64, 0.0, 0.8), (67, 1.0, 0.8)]
        audio = synth_take(events, sr=48_000)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "take48.wav"
            write_take(path, audio, 48_000)
            result = analyse_file(path, bpm=BPM, start_bar=0, track_id="lead")
        self.assertEqual([n["note"] for n in result["notes"]], [64, 67])
        self.assertAlmostEqual(result["notes"][1]["beat"], 1.0, delta=GRID)
        self.assertEqual(result["input"]["sampleRate"], 48_000)
        self.assertTrue(any("48000" in w for w in result["warnings"]))

    def test_deterministic(self):
        take = synth_take([(64, 0.0, 0.8), (67, 1.0, 0.8)])
        first = hum_to_melody(take, bpm=BPM)
        second = hum_to_melody(take, bpm=BPM)
        self.assertEqual(first, second)


class CliTests(unittest.TestCase):
    def test_cli_json_last_line_is_one_object(self):
        audio = synth_take([(64, 0.0, 0.8), (67, 1.0, 0.8)])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "take.wav"
            write_take(path, audio, SR)
            proc = subprocess.run(
                [sys.executable, str(Path(__file__).resolve().parent / "hum_to_melody.py"),
                 "--input", str(path), "--bpm", "142", "--start-bar", "8", "--track-id", "lead",
                 "--key", "E minor", "--format", "json"],
                capture_output=True, text=True,
            )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertTrue(payload["ok"])
        self.assertEqual([n["note"] for n in payload["notes"]], [64, 67])

    def test_cli_missing_file_fails_with_json_error(self):
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parent / "hum_to_melody.py"),
             "--input", "/nonexistent/take.wav", "--bpm", "142"],
            capture_output=True, text=True,
        )
        self.assertNotEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertFalse(payload["ok"])
        self.assertIn("error", payload)


if __name__ == "__main__":
    unittest.main()
