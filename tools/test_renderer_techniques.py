#!/usr/bin/env python3
"""Tests for the technique pass carried by every generated renderer.

The effects live in the renderer template inside project_materializer.py, so
the honest way to test them is to emit a renderer for a tiny spec and load the
emitted file. Nothing here reads audio from disk: every signal is synthesised
(a sine, an impulse, seeded noise) so the assertions hold on any machine.
"""
from __future__ import annotations

import importlib.util
import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from project_materializer import build_project_materialization, ensure_project_renderer  # noqa: E402


TINY_SPEC = {
    "projectId": "technique-test",
    "titleHint": "Technique Test",
    "tempoHint": 142,
    "keyHints": ["E minor"],
    "timecoded": False,
    "sections": [
        {"id": "s1", "type": "intro", "label": "Intro", "bars": 2, "summary": "Intro with chords and lead", "trackRoles": ["chords", "lead"], "plugins": [], "techniques": ["reverb"]},
        {"id": "s2", "type": "build", "label": "Build", "bars": 2, "summary": "Build with filter automation", "trackRoles": ["drums", "lead", "chords"], "plugins": [], "techniques": ["automation"]},
        {"id": "s3", "type": "drop", "label": "Drop", "bars": 4, "summary": "Drop with sidechain on the bass and sub", "trackRoles": ["drums", "clap", "bass", "sub", "chords", "lead", "fx"], "plugins": [], "techniques": ["sidechain"]},
        {"id": "s4", "type": "outro", "label": "Outro", "bars": 2, "summary": "Outro", "trackRoles": ["chords"], "plugins": [], "techniques": []},
    ],
    "globalTracks": [{"name": name, "mentions": 1, "sections": []} for name in ("drums", "clap", "bass", "sub", "chords", "lead", "fx")],
    "globalTechniques": [],
    "arrangementNotes": [],
    "mixNotes": [],
    "automationNotes": [],
}


def emit_renderer():
    """Emit a renderer for TINY_SPEC into a temp dir and import it as a module."""
    tmp = Path(tempfile.mkdtemp(prefix="renderer-techniques-"))
    project = build_project_materialization(TINY_SPEC, "technique-test", prompt="technique test")
    path = ensure_project_renderer(tmp, "technique-test", "Technique Test", project, TINY_SPEC, prompt="technique test", overwrite=True)
    spec = importlib.util.spec_from_file_location("render_technique_test", path)
    module = importlib.util.module_from_spec(spec)
    # dataclass field resolution looks the module up in sys.modules, so register
    # it the way a normal import would.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


R = None


def setUpModule() -> None:
    global R
    R = emit_renderer()


def db(value: float) -> float:
    return 20.0 * math.log10(max(float(value), 1e-12))


def rms(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=np.float64)
    return math.sqrt(float(np.mean(x * x))) if x.size else 0.0


def stereo_sine(freq: float, seconds: float, amplitude: float = 0.5) -> np.ndarray:
    t = np.arange(int(seconds * R.SR), dtype=np.float64) / R.SR
    mono = amplitude * np.sin(2.0 * math.pi * freq * t)
    return np.stack([mono, mono], axis=1).astype(np.float32)


def stereo_noise(seconds: float, amplitude: float, seed: int) -> np.ndarray:
    n = int(seconds * R.SR)
    return (np.random.default_rng(seed).standard_normal((n, 2)) * amplitude).astype(np.float32)


def window_rms_envelope(x: np.ndarray, window_seconds: float = 0.01) -> np.ndarray:
    mono = np.mean(np.asarray(x, dtype=np.float64) ** 2, axis=1) if x.ndim == 2 else np.asarray(x, dtype=np.float64) ** 2
    window = max(1, int(window_seconds * R.SR))
    usable = (len(mono) // window) * window
    return np.sqrt(mono[:usable].reshape(-1, window).mean(axis=1))


def decay_seconds_to(x: np.ndarray, drop_db: float) -> float:
    """Time at which the 10 ms RMS envelope last sits above (peak - drop_db)."""
    env = window_rms_envelope(x)
    peak = env.max()
    above = np.nonzero(env > peak * (10.0 ** (-drop_db / 20.0)))[0]
    return float(above[-1] + 1) * 0.01 if above.size else 0.0


def spectral_centroid(x: np.ndarray) -> float:
    """Power-weighted centroid: where the energy sits, not where the bins are."""
    mono = np.mean(np.asarray(x, dtype=np.float64), axis=1)
    power = np.abs(np.fft.rfft(mono)) ** 2
    freqs = np.fft.rfftfreq(len(mono), 1.0 / R.SR)
    return float(np.sum(freqs * power) / max(np.sum(power), 1e-12))


def band_power(x: np.ndarray, low_hz: float, high_hz: float) -> float:
    mono = np.mean(np.asarray(x, dtype=np.float64), axis=1)
    power = np.abs(np.fft.rfft(mono)) ** 2
    freqs = np.fft.rfftfreq(len(mono), 1.0 / R.SR)
    mask = (freqs >= low_hz) & (freqs < high_hz)
    return float(np.mean(power[mask])) if mask.any() else 0.0


def section_by_type(section_type: str) -> dict:
    return next(dict(section) for section in R.SECTION_PLAN if section["type"] == section_type)


class EmittedRendererTests(unittest.TestCase):
    def test_renderer_exposes_effects_and_pass(self) -> None:
        for name in ("apply_sidechain", "apply_reverb", "apply_pingpong_delay", "apply_filter_sweep", "apply_soft_clip", "apply_haas_widener", "apply_snare_layer", "gain_ladder_scales", "master_peak_scale", "apply_section_techniques", "apply_song_techniques"):
            self.assertTrue(callable(getattr(R, name, None)), name)
        self.assertEqual(R.SIDECHAIN_DEPTHS, {"sub": 0.65, "bass": 0.50, "chords": 0.45, "plucks": 0.35})

    def test_kick_onsets_are_where_the_drums_lane_hits(self) -> None:
        drop = section_by_type("drop")
        drum_pattern = drop["starterDefaults"]["drumPattern"]
        onsets = R._kick_onsets_for_section(drop)
        expected = sum(len(R._kick_events_for_bar(drum_pattern, local_bar)) for local_bar in range(drop["bars"]))
        self.assertEqual(len(onsets), expected)
        self.assertGreater(len(onsets), 0)
        # Render only the drums lane and check a kick transient starts at each onset.
        ctx = R.RenderContext()
        R._starter_drums(ctx, drop, R.TRACK_PLAN_BY_ID["drums"])
        drums = ctx.stems["drums"]
        span = int(0.005 * R.SR)
        for onset in onsets:
            index = int(round(onset * R.SR))
            before = rms(drums[index - span:index])
            after = rms(drums[index:index + span])
            self.assertGreater(after, 3.0 * before + 1e-6, f"no kick transient at {onset:.3f} s")


class SidechainTests(unittest.TestCase):
    def test_bass_ducks_more_than_6_db_within_30_ms_of_a_kick(self) -> None:
        bass = stereo_sine(55.0, 2.0, amplitude=0.5)
        onsets = [0.5, 1.0]
        out = R.apply_sidechain(bass, onsets, R.SIDECHAIN_DEPTHS["bass"], R.SR, R.BPM)
        onset = int(0.5 * R.SR)
        window = slice(onset, onset + int(0.030 * R.SR))
        audible = np.abs(bass[window, 0]) > 0.05
        gain = out[window, 0][audible] / bass[window, 0][audible]
        deepest_db = db(float(gain.min()))
        self.assertLess(deepest_db, -6.0, f"deepest duck within 30 ms was only {deepest_db:.2f} dB")
        # Untouched before the first kick, and back to unity an eighth note later.
        before = slice(0, onset - 1)
        self.assertTrue(np.array_equal(out[before], bass[before]))
        eighth = int(0.5 * (60.0 / R.BPM) * R.SR)
        settled = out[onset + eighth + 400, 0] / bass[onset + eighth + 400, 0]
        self.assertGreater(settled, 0.99)

    def test_sub_rms_dips_by_more_than_8_db(self) -> None:
        sub = stereo_sine(110.0, 1.0, amplitude=0.4)
        out = R.apply_sidechain(sub, [0.25], R.SIDECHAIN_DEPTHS["sub"], R.SR, R.BPM)
        onset = int(0.25 * R.SR)
        window = slice(onset + int(0.005 * R.SR), onset + int(0.030 * R.SR))
        dip_db = db(rms(out[window])) - db(rms(sub[window]))
        self.assertLess(dip_db, -8.0, f"sub RMS dip was {dip_db:.2f} dB")


class ReverbTests(unittest.TestCase):
    def test_impulse_decay_extends_past_0_8_seconds(self) -> None:
        impulse = np.zeros((int(3.0 * R.SR), 2), dtype=np.float32)
        impulse[0] = 1.0
        wet = R.schroeder_reverb(impulse, R.SR, R.REVERB_DECAY_SECONDS)
        self.assertLess(decay_seconds_to(impulse, 40.0), 0.02)
        tail = decay_seconds_to(wet, 40.0)
        self.assertGreater(tail, 0.8, f"-40 dB decay was only {tail:.2f} s")

    def test_send_is_high_passed(self) -> None:
        # Noise rather than a sine: a single tone lands on or between comb
        # resonances, so only a band average shows what the send filter did.
        noise = stereo_noise(4.0, 0.2, seed=21)
        wet = R.apply_reverb(noise, R.SR) - noise
        low_ratio = 10.0 * math.log10(band_power(wet, 20.0, 120.0) / band_power(noise, 20.0, 120.0))
        mid_ratio = 10.0 * math.log10(band_power(wet, 1000.0, 3000.0) / band_power(noise, 1000.0, 3000.0))
        self.assertLess(low_ratio - mid_ratio, -9.0, f"low band {low_ratio:+.1f} dB vs mid band {mid_ratio:+.1f} dB")


class DelayTests(unittest.TestCase):
    def test_echoes_alternate_channels_at_dotted_eighths(self) -> None:
        impulse = np.zeros((int(3.0 * R.SR), 2), dtype=np.float32)
        impulse[0] = 1.0
        out = R.apply_pingpong_delay(impulse, R.SR, R.BPM)
        lag = int(round(0.75 * (60.0 / R.BPM) * R.SR))
        for repeat in (1, 2, 3):
            window = slice(repeat * lag - 4, repeat * lag + 5)
            left = float(np.sum(out[window, 0] ** 2))
            right = float(np.sum(out[window, 1] ** 2))
            if repeat % 2 == 1:
                self.assertGreater(left, right * 100.0, f"repeat {repeat} should sit left")
            else:
                self.assertGreater(right, left * 100.0, f"repeat {repeat} should sit right")
        self.assertAlmostEqual(float(out[lag, 0]), R.DELAY_WET, delta=0.01)
        self.assertAlmostEqual(float(out[2 * lag, 1]), R.DELAY_WET * R.DELAY_FEEDBACK, delta=0.01)


class FilterSweepTests(unittest.TestCase):
    def test_centroid_rises_from_first_bar_to_last(self) -> None:
        bar_seconds = 4.0 * R.BEAT
        noise = stereo_noise(4.0 * bar_seconds, 0.2, seed=7)
        swept = R.apply_filter_sweep(noise, R.SR, R.SWEEP_START_HZ, R.SWEEP_END_HZ)
        bar = int(bar_seconds * R.SR)
        first = spectral_centroid(swept[:bar])
        last = spectral_centroid(swept[-bar:])
        self.assertGreater(last, first * 3.0, f"centroid {first:.0f} Hz -> {last:.0f} Hz")


class SoftClipTests(unittest.TestCase):
    def test_crest_factor_drops_and_rms_holds(self) -> None:
        signal = stereo_sine(110.0, 1.0, amplitude=0.4) + stereo_sine(165.0, 1.0, amplitude=0.25)
        clipped = R.apply_soft_clip(signal, R.DISTORTION_DRIVE)
        crest_in = db(np.max(np.abs(signal))) - db(rms(signal))
        crest_out = db(np.max(np.abs(clipped))) - db(rms(clipped))
        self.assertLess(crest_out, crest_in - 0.5)
        self.assertLess(abs(db(rms(clipped)) - db(rms(signal))), 1.0)


class WidenerTests(unittest.TestCase):
    def test_widens_chords_and_leaves_bass_identical(self) -> None:
        drop = section_by_type("drop")
        drop["techniques"] = ["stereo"]
        start, end = R._section_window(drop)
        ctx = R.RenderContext()
        chords = R.stereo_buffer()
        bass = R.stereo_buffer()
        tone = stereo_sine(220.0, (end - start) / R.SR, amplitude=0.3)
        chords[start:end] = tone
        bass[start:end] = stereo_sine(55.0, (end - start) / R.SR, amplitude=0.3)
        bass_before = bass.copy()
        ctx.stems["chords"] = chords
        ctx.stems["bass"] = bass
        applied = R.apply_section_techniques(ctx, drop)
        self.assertTrue(any(line.startswith("stereo") for line in applied))
        side_before = rms(tone[:, 0] - tone[:, 1])
        side_after = rms(ctx.stems["chords"][start:end, 0] - ctx.stems["chords"][start:end, 1])
        self.assertLess(side_before, 1e-6)
        self.assertGreater(side_after, 0.05)
        self.assertTrue(np.array_equal(ctx.stems["bass"], bass_before))

    def test_mono_sum_is_preserved(self) -> None:
        tone = stereo_sine(440.0, 0.5, amplitude=0.3)
        wide = R.apply_haas_widener(tone, R.SR)
        scale = 1.0 / math.sqrt(1.0 + R.db_to_gain(R.WIDEN_LEVEL_DB) ** 2)
        np.testing.assert_allclose(wide[:, 0] + wide[:, 1], (tone[:, 0] + tone[:, 1]) * scale, atol=1e-4)


class SnareLayerTests(unittest.TestCase):
    def test_layer_sits_9_db_under_the_hit(self) -> None:
        silence = np.zeros((R.SR, 2), dtype=np.float32)
        out = R.apply_snare_layer(silence, [(0.25, 0.8)], R.SR, R.SNARE_LAYER_DB)
        onset = int(0.25 * R.SR)
        self.assertEqual(float(np.max(np.abs(out[:onset]))), 0.0)
        expected_peak = 0.8 * R.db_to_gain(-9.0) * R.equal_power_pan(0.0)[0]
        self.assertAlmostEqual(float(np.max(np.abs(out[onset:onset + R.SR // 8]))), expected_peak, delta=expected_peak * 0.05)


class GainLadderTests(unittest.TestCase):
    def test_offsets_relative_to_drums_and_master_peak(self) -> None:
        raw_levels = {"drums": 0.3, "bass": 0.02, "chords": 0.5, "lead": 0.05, "hat_ride": 0.2, "fx": 0.01, "sub": 0.09}
        stems = {name: stereo_noise(2.0, level, seed=index) for index, (name, level) in enumerate(raw_levels.items(), start=11)}
        scales = R.gain_ladder_scales(stems)
        balanced = {name: stems[name] * np.float32(scales[name]) for name in stems}
        levels = {name: R.stem_level_db(audio) for name, audio in balanced.items()}
        for name, level in levels.items():
            expected = levels["drums"] + R.GAIN_LADDER_DB[name]
            self.assertAlmostEqual(level, expected, delta=0.5, msg=f"{name} sits at {level - levels['drums']:+.1f} dB, wanted {R.GAIN_LADDER_DB[name]:+.1f}")
        self.assertEqual(max(levels, key=levels.get), "drums")
        mix = sum(balanced.values())
        master = R.master_peak_scale(mix, R.MASTER_PEAK_DBFS)
        self.assertAlmostEqual(float(np.max(np.abs(mix * master))), R.db_to_gain(R.MASTER_PEAK_DBFS), delta=1e-3)

    def test_silent_stems_are_left_alone(self) -> None:
        stems = {"drums": stereo_noise(1.0, 0.3, seed=3), "vocals": np.zeros((R.SR, 2), dtype=np.float32)}
        scales = R.gain_ladder_scales(stems)
        self.assertEqual(scales["vocals"], 1.0)
        self.assertEqual(R.master_peak_scale(stems["vocals"]), 1.0)


class SectionPassTests(unittest.TestCase):
    def test_no_techniques_means_no_change(self) -> None:
        drop = section_by_type("drop")
        drop["techniques"] = []
        ctx = R.RenderContext()
        ctx.stems["bass"] = stereo_noise(R.N_SAMPLES / R.SR, 0.2, seed=5)
        before = ctx.stems["bass"].copy()
        self.assertEqual(R.apply_section_techniques(ctx, drop), [])
        self.assertTrue(np.array_equal(ctx.stems["bass"], before))

    def test_sidechain_touches_only_the_section_and_only_ducked_lanes(self) -> None:
        drop = section_by_type("drop")
        drop["techniques"] = ["sidechain"]
        start, end = R._section_window(drop)
        ctx = R.RenderContext()
        ctx.stems["bass"] = stereo_noise(R.N_SAMPLES / R.SR, 0.2, seed=8)
        ctx.stems["lead"] = stereo_noise(R.N_SAMPLES / R.SR, 0.2, seed=9)
        bass_before = ctx.stems["bass"].copy()
        lead_before = ctx.stems["lead"].copy()
        applied = R.apply_section_techniques(ctx, drop)
        self.assertTrue(any(line.startswith("sidechain") for line in applied))
        self.assertTrue(np.array_equal(ctx.stems["bass"][:start], bass_before[:start]))
        self.assertTrue(np.array_equal(ctx.stems["bass"][end:], bass_before[end:]))
        self.assertFalse(np.array_equal(ctx.stems["bass"][start:end], bass_before[start:end]))
        self.assertTrue(np.array_equal(ctx.stems["lead"], lead_before))

    def test_build_sweep_adds_a_riser_when_no_fx_lane_carries_one(self) -> None:
        build = section_by_type("build")
        self.assertNotIn("fx", build["trackIds"])
        build["techniques"] = ["automation"]
        ctx = R.RenderContext()
        ctx.stems["lead"] = stereo_noise(R.N_SAMPLES / R.SR, 0.2, seed=4)
        applied = R.apply_section_techniques(ctx, build)
        self.assertTrue(any(line.startswith("riser") for line in applied))
        self.assertIn("fx", ctx.stems)
        last_bar_start = int(R.beat_to_seconds(R.bar_beat(build["startBar"] + build["bars"] - 1)) * R.SR)
        self.assertEqual(float(np.max(np.abs(ctx.stems["fx"][:last_bar_start - 1]))), 0.0)
        self.assertGreater(rms(ctx.stems["fx"][last_bar_start:last_bar_start + int(4 * R.BEAT * R.SR)]), 1e-3)


if __name__ == "__main__":
    unittest.main()


class NewTechniqueTests(unittest.TestCase):
    """EQ, compression, the reverse swell, typed sweeps and the master limiter."""

    def test_highpass_removes_low_end_and_keeps_mids(self) -> None:
        x = stereo_sine(50.0, 1.0, 0.4) + stereo_sine(1000.0, 1.0, 0.4)
        y = R.apply_highpass(x, R.SR, R.EQ_HIGHPASS_HZ, R.EQ_HIGHPASS_POLES)
        self.assertLess(db(band_power(y, 40, 60)) - db(band_power(x, 40, 60)), -24.0)
        self.assertGreater(db(band_power(y, 900, 1100)) - db(band_power(x, 900, 1100)), -3.0)

    def test_lowpass_keeps_sub_and_removes_highs(self) -> None:
        x = stereo_sine(50.0, 1.0, 0.4) + stereo_sine(2000.0, 1.0, 0.4)
        y = R.apply_lowpass(x, R.SR, R.EQ_SUB_LOWPASS_HZ)
        self.assertLess(db(band_power(y, 1900, 2100)) - db(band_power(x, 1900, 2100)), -36.0)
        self.assertGreater(db(band_power(y, 40, 60)) - db(band_power(x, 40, 60)), -4.0)

    @staticmethod
    def programmed_hits(levels_db: list, seconds: float = 4.0) -> np.ndarray:
        """Sixteen drum hits with accents: a click plus a decaying noise body."""
        n = int(seconds * R.SR)
        x = np.zeros((n, 2), dtype=np.float64)
        rng = np.random.default_rng(3)
        t = np.arange(int(0.12 * R.SR)) / R.SR
        body = rng.standard_normal(len(t)) * np.exp(-t / 0.04) * 0.3
        for index, level in enumerate(levels_db):
            at = int(index * 0.25 * R.SR)
            gain = 10.0 ** (level / 20.0)
            x[at:at + 90, :] += (gain * 0.9 * np.hanning(90))[:, None]
            x[at:at + len(t), :] += (gain * body)[:, None]
        return x.astype(np.float32)

    @staticmethod
    def body_levels(x: np.ndarray, count: int = 16) -> np.ndarray:
        out = []
        for index in range(count):
            at = int(index * 0.25 * R.SR)
            segment = np.asarray(x[at + int(0.02 * R.SR):at + int(0.06 * R.SR)], dtype=np.float64)
            out.append(db(math.sqrt(float(np.mean(segment ** 2)))))
        return np.array(out)

    def test_compressor_evens_out_hit_bodies_and_keeps_the_peak(self) -> None:
        x = self.programmed_hits([0, -6, -3, -9] * 4)
        y = R.apply_compressor(x, R.SR)
        before, after = self.body_levels(x), self.body_levels(y)
        self.assertGreater(before.max() - before.min(), 8.0)
        self.assertLess(after.max() - after.min(), (before.max() - before.min()) - 4.0)
        self.assertAlmostEqual(float(np.max(np.abs(y))), float(np.max(np.abs(x))), delta=1e-3)

    def test_limiter_holds_the_ceiling_and_raises_the_level(self) -> None:
        x = stereo_noise(2.0, 0.2, seed=7)
        x[R.SR:R.SR + 200] *= 4.0     # one spike the drive would push over
        y = R.apply_peak_limiter(x, R.SR)
        ceiling = R.db_to_gain(R.MASTER_PEAK_DBFS)
        self.assertLessEqual(float(np.max(np.abs(y))), ceiling + 1e-4)
        self.assertGreater(db(rms(y)) - db(rms(x)), 3.0)
        curve = R.limiter_gain_curve(x, R.SR)
        self.assertEqual(len(curve), len(x))
        # The curve is the drive everywhere the mix is under the ceiling.
        self.assertAlmostEqual(float(curve[100]), R.db_to_gain(R.MASTER_DRIVE_DB), delta=1e-3)
        self.assertLess(float(curve[R.SR + 10]), R.db_to_gain(R.MASTER_DRIVE_DB))

    def test_reverse_swell_rises_into_its_end(self) -> None:
        t = np.arange(int(0.8 * R.SR)) / R.SR
        source = np.stack([np.sin(2 * math.pi * 440 * t) * np.exp(-t / 0.2)] * 2, axis=1).astype(np.float32)
        swell = R.reverse_swell(source, -6.0, reference_peak=0.5)
        self.assertAlmostEqual(float(np.max(np.abs(swell))), 0.25, delta=0.01)
        quarter = len(swell) // 4
        self.assertGreater(db(rms(swell[-quarter:])) - db(rms(swell[:quarter])), 6.0)

    def test_sweep_ranges_follow_the_section_type(self) -> None:
        self.assertEqual(R._sweep_range_for("intro", ["filtering"]), (R.SWEEP_OPEN_START_HZ, R.SWEEP_OPEN_END_HZ))
        self.assertEqual(R._sweep_range_for("outro", ["filtering"]), (R.SWEEP_OPEN_END_HZ, R.SWEEP_OPEN_START_HZ))
        self.assertEqual(R._sweep_range_for("build", ["automation"]), (R.SWEEP_START_HZ, R.SWEEP_END_HZ))
        self.assertIsNone(R._sweep_range_for("drop", ["filtering"]))
        self.assertIsNone(R._sweep_range_for("verse", ["reverb"]))
        self.assertEqual(R._drop_automation_range("second_drop", ["automation"]), (R.DROP_AUTOMATION_START_HZ, R.DROP_AUTOMATION_END_HZ))
        self.assertIsNone(R._drop_automation_range("build", ["automation"]))

    def test_new_techniques_are_handled_and_reflected_in_project_effects(self) -> None:
        from project_materializer import TECHNIQUE_EFFECT_ENTRIES
        for technique in ("eq", "compression", "reverse"):
            self.assertIn(technique, R.HANDLED_TECHNIQUES)
            self.assertIn(technique, TECHNIQUE_EFFECT_ENTRIES)
        self.assertEqual(TECHNIQUE_EFFECT_ENTRIES["compression"]["drums"][1], "Bus Comp")

    def test_section_pass_applies_eq_compression_and_reverse(self) -> None:
        drop = section_by_type("drop")
        drop["techniques"] = ["eq", "compression", "reverse"]
        drop["trackIds"] = ["chords", "sub", "drums", "fx"]
        seconds = R.N_SAMPLES / R.SR
        ctx = R.RenderContext()
        ctx.stems["chords"] = stereo_sine(50.0, seconds, 0.3) + stereo_sine(1000.0, seconds, 0.3)
        ctx.stems["sub"] = stereo_sine(50.0, seconds, 0.3) + stereo_sine(2000.0, seconds, 0.3)
        hits = self.programmed_hits([0, -6, -3, -9] * 4, seconds=seconds)
        ctx.stems["drums"] = hits.copy()
        ctx.stems["fx"] = np.zeros((R.N_SAMPLES, 2), dtype=np.float32)
        lines = R.apply_section_techniques(ctx, drop)
        self.assertTrue(any(line.startswith("eq:") for line in lines), lines)
        self.assertTrue(any(line.startswith("compression:") for line in lines), lines)
        self.assertTrue(any(line.startswith("reverse:") for line in lines), lines)
        start, end = R._section_window(drop)
        inside = ctx.stems["chords"][start:end]
        self.assertLess(db(band_power(inside, 40, 60)) - db(band_power(stereo_sine(50.0, seconds, 0.3)[start:end], 40, 60)), -24.0)
        self.assertLess(db(band_power(ctx.stems["sub"][start:end], 1900, 2100)) - db(band_power(stereo_sine(2000.0, seconds, 0.3)[start:end], 1900, 2100)), -36.0)
        length = int(round(R.REVERSE_SWELL_BEATS * R.BEAT * R.SR))
        before = ctx.stems["fx"][start - length:start]
        self.assertGreater(float(np.max(np.abs(before))), 0.05)
        quarter = len(before) // 4
        self.assertGreater(db(rms(before[-quarter:])) - db(rms(before[:quarter])), 6.0)
        # Nothing outside the section moved, and nothing landed on the fx lane after it.
        self.assertTrue(np.array_equal(ctx.stems["drums"][end + R.SR:], hits[end + R.SR:]))
        self.assertEqual(float(np.max(np.abs(ctx.stems["fx"][start:]))), 0.0)
