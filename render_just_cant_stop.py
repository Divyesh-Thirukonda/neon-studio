#!/usr/bin/env python3
"""
Render an original dark trap/festival project inspired by the provided
"Just Can't Stop" walkthrough.

The output follows the production techniques in the transcript, but it does
not copy the commercial recording, melody, samples, tags, or vocal phrases.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import render_neon_solitude as dsp


ROOT = Path(__file__).resolve().parent
EXPORTS = ROOT / "exports"
PROJECTS = ROOT / "factory" / "projects"

BPM = 150
TOTAL_BARS = 72
TAIL_SECONDS = 4.0
KEY_CENTER = "F minor / Ab major"

dsp.BPM = BPM
dsp.BEAT = 60.0 / BPM
dsp.TOTAL_BARS = TOTAL_BARS
dsp.TAIL_SECONDS = TAIL_SECONDS
dsp.TOTAL_SECONDS = TOTAL_BARS * 4 * dsp.BEAT + TAIL_SECONDS
dsp.N_SAMPLES = int(dsp.TOTAL_SECONDS * dsp.SR)
dsp.rng = np.random.default_rng(5071)


def seconds_at(bar: float, beat: float = 0.0) -> float:
    return (bar * 4.0 + beat) * dsp.BEAT


def note(note_number: int) -> float:
    return dsp.note_to_freq(note_number)


def lane() -> np.ndarray:
    return dsp.stereo_buffer()


def add(target: np.ndarray, bar: float, audio: np.ndarray, gain: float = 1.0, pan: float = 0.0, beat: float = 0.0) -> None:
    dsp.add_mono(target, seconds_at(bar, beat), audio, gain=gain, pan=pan)


def env_len(dur: float) -> int:
    return max(1, int(dur * dsp.SR))


def sample_bass_synth(freq: float, dur: float, motion: float = 1.0) -> np.ndarray:
    n = env_len(dur)
    t = np.arange(n, dtype=np.float32) / dsp.SR
    base = (
        0.44 * dsp.saw(freq, dur, phase=0.11)
        + 0.28 * dsp.saw(freq * 0.5, dur, phase=0.37)
        + 0.18 * dsp.saw(freq * 1.5, dur, phase=0.23)
    )
    grit = np.sin(2.0 * np.pi * (freq * 2.01) * t + 0.8 * np.sin(2.0 * np.pi * 2.2 * t)).astype(np.float32)
    grains = np.sin(2.0 * np.pi * (freq * 7.0 + 24.0 * np.sin(2.0 * np.pi * 6.0 * t)) * t).astype(np.float32)
    wobble = (0.62 + 0.38 * np.sin(2.0 * np.pi * motion * t + 0.3)).astype(np.float32)
    x = (base + 0.22 * grit + 0.08 * grains) * wobble
    x = dsp.one_pole_lowpass(x.astype(np.float32), 1800.0)
    drive = np.tanh(x * 2.6) / np.tanh(2.6)
    return drive * dsp.adsr(n, attack=0.04, decay=0.18, sustain=0.78, release=0.22)


def analog_layer(freq: float, dur: float) -> np.ndarray:
    n = env_len(dur)
    t = np.arange(n, dtype=np.float32) / dsp.SR
    drift = 1.0 + 0.003 * np.sin(2.0 * np.pi * 0.41 * t)
    phase = np.cumsum((freq * drift).astype(np.float32)) / dsp.SR
    tri = (2.0 * np.abs(2.0 * (phase % 1.0) - 1.0) - 1.0).astype(np.float32)
    saw = dsp.saw(freq * 0.5, dur, phase=0.19)
    return dsp.one_pole_lowpass((0.72 * tri + 0.28 * saw).astype(np.float32), 520.0) * dsp.adsr(n, 0.02, 0.12, 0.68, 0.18)


def dark_room_layer(freq: float, dur: float) -> np.ndarray:
    n = env_len(dur)
    pad = 0.42 * dsp.synth_supersaw(freq, dur, bright=0.32) + 0.22 * dsp.synth_supersaw(freq * 1.498, dur, bright=0.18)
    smear = dsp.one_pole_lowpass(dsp.highpass_noise(n), 1500.0) * 0.035
    return (pad + smear).astype(np.float32) * dsp.adsr(n, 0.35, 0.8, 0.72, 1.0)


def breath(dur: float) -> np.ndarray:
    n = env_len(dur)
    t = np.arange(n, dtype=np.float32) / dsp.SR
    noise = dsp.one_pole_lowpass(dsp.highpass_noise(n), 2600.0)
    return noise * np.sin(np.linspace(0.0, np.pi, n, dtype=np.float32)) * (0.10 + 0.04 * np.sin(2.0 * np.pi * 5.1 * t))


def vocal_chop(freq: float, dur: float, bright: float = 1.0) -> np.ndarray:
    n = env_len(dur)
    t = np.arange(n, dtype=np.float32) / dsp.SR
    carrier = (
        0.55 * np.sin(2.0 * np.pi * freq * t)
        + 0.32 * np.sin(2.0 * np.pi * freq * 2.01 * t + 0.35)
        + 0.16 * np.sin(2.0 * np.pi * freq * 3.02 * t + 0.85)
    ).astype(np.float32)
    formant = (
        0.30 * np.sin(2.0 * np.pi * (720.0 + 18.0 * np.sin(2.0 * np.pi * 3.2 * t)) * t)
        + 0.22 * np.sin(2.0 * np.pi * (1180.0 + 26.0 * np.sin(2.0 * np.pi * 4.1 * t)) * t)
    ).astype(np.float32)
    x = carrier + bright * formant
    x = dsp.one_pole_lowpass(x, 3600.0 + 1800.0 * bright)
    return np.tanh(x * 1.8) * dsp.adsr(n, 0.006, 0.08, 0.5, 0.08)


def fresh_air_chop(freq: float, dur: float) -> np.ndarray:
    n = env_len(dur)
    x = vocal_chop(freq, dur, bright=1.35)
    sparkle = dsp.highpass_noise(n) * dsp.adsr(n, 0.002, 0.03, 0.16, 0.05) * 0.06
    return np.tanh((x + sparkle) * 1.35)


def rave_stab(freq: float, dur: float) -> np.ndarray:
    n = env_len(dur)
    fifth = dsp.saw(freq * 1.5, dur, phase=0.28)
    seventh = dsp.saw(freq * 1.78, dur, phase=0.42)
    root = dsp.square_from_phase(np.cumsum(np.full(n, freq, dtype=np.float32)) / dsp.SR)
    x = 0.42 * root + 0.26 * fifth + 0.22 * seventh + 0.08 * dsp.highpass_noise(n)
    x = np.tanh(x * 2.2)
    return dsp.one_pole_lowpass(x.astype(np.float32), 3100.0) * dsp.adsr(n, 0.01, 0.08, 0.38, 0.12)


def wamp_synth(freq: float, dur: float, rate: float = 2.0, harsh: float = 1.0) -> np.ndarray:
    n = env_len(dur)
    t = np.arange(n, dtype=np.float32) / dsp.SR
    phase = np.cumsum(np.full(n, freq, dtype=np.float32)) / dsp.SR
    wave = 0.42 * dsp.saw(freq, dur, phase=0.07) + 0.32 * dsp.square_from_phase(phase * 1.01)
    noise = dsp.highpass_noise(n) * 0.12
    wobble = (0.48 + 0.52 * np.maximum(0.0, np.sin(2.0 * np.pi * rate * t))).astype(np.float32)
    x = dsp.one_pole_lowpass(((wave + noise) * wobble).astype(np.float32), 420.0 + 1200.0 * harsh)
    return np.tanh(x * (2.1 + harsh)) * dsp.adsr(n, 0.005, 0.06, 0.76, 0.08)


def lead_layer(freq: float, dur: float) -> np.ndarray:
    n = env_len(dur)
    t = np.arange(n, dtype=np.float32) / dsp.SR
    phase = np.cumsum((freq * (1.0 + 0.006 * np.sin(2.0 * np.pi * 5.8 * t))).astype(np.float32)) / dsp.SR
    core = 0.42 * dsp.square_from_phase(phase) + 0.24 * dsp.saw(freq * 2.0, dur, phase=0.15)
    phase_dist = np.sin(2.0 * np.pi * (phase + 0.16 * np.sin(2.0 * np.pi * phase * 3.0))).astype(np.float32)
    sizzle = dsp.highpass_noise(n) * 0.035
    x = np.tanh((core + 0.28 * phase_dist + sizzle) * 2.4)
    return dsp.one_pole_lowpass(x.astype(np.float32), 6100.0) * dsp.adsr(n, 0.008, 0.08, 0.62, 0.12)


def sub_patch(freq: float, dur: float, long: bool = False) -> np.ndarray:
    n = env_len(dur)
    t = np.arange(n, dtype=np.float32) / dsp.SR
    tri = (2.0 * np.abs(2.0 * ((freq * t) % 1.0) - 1.0) - 1.0).astype(np.float32)
    sine = np.sin(2.0 * np.pi * freq * t).astype(np.float32)
    noise_drive = dsp.one_pole_lowpass(dsp.highpass_noise(n), 900.0) * 0.045
    x = np.tanh((0.72 * tri + 0.35 * sine + noise_drive) * 2.8)
    env = dsp.adsr(n, 0.006, 0.08, 0.88 if long else 0.72, 0.18)
    return x * env


def laser(dur: float, down: bool = False) -> np.ndarray:
    n = env_len(dur)
    t = np.arange(n, dtype=np.float32) / dsp.SR
    curve = np.linspace(1.0, 0.0, n, dtype=np.float32) if down else np.linspace(0.0, 1.0, n, dtype=np.float32)
    freq = 210.0 + 1800.0 * (curve ** 2)
    phase = np.cumsum(freq) / dsp.SR
    return np.tanh(np.sin(2.0 * np.pi * phase).astype(np.float32) * 2.4) * np.exp(-t * 2.6).astype(np.float32)


def glitch_tail(freq: float, dur: float) -> np.ndarray:
    n = env_len(dur)
    t = np.arange(n, dtype=np.float32) / dsp.SR
    x = lead_layer(freq, dur)
    gate = ((np.sin(2.0 * np.pi * 11.0 * t) > 0.15) | (np.sin(2.0 * np.pi * 17.0 * t + 0.2) > 0.62)).astype(np.float32)
    return x * gate * np.linspace(1.0, 0.0, n, dtype=np.float32)


def slow_attack_crash() -> np.ndarray:
    crash = dsp.crash()
    n = len(crash)
    rise = np.minimum(1.0, np.linspace(0.0, 2.0, n, dtype=np.float32))
    return crash * rise


def make_clip(id_: str, name: str, start: int, bars: int, lane_id: str, color: str, type_: str = "audio") -> dict:
    return {"id": id_, "name": name, "startBar": start, "bars": bars, "lane": lane_id, "color": color, "type": type_}


def make_effect(id_: str, name: str, amount: float, active: bool = True) -> dict:
    return {"id": id_, "name": name, "active": active, "amount": amount}


def make_track(id_: str, name: str, file_name: str, color: str, gain: float, pan: float, steps: list[int], instrument: str, clips: list[dict], effects: list[dict], kind: str = "audio") -> dict:
    return {
        "id": id_,
        "name": name,
        "kind": kind,
        "file": f"/api/audio/{file_name}",
        "color": color,
        "gain": gain,
        "pan": pan,
        "steps": steps,
        "instrument": instrument,
        "clips": clips,
        "effects": effects,
    }


def make_notes() -> list[dict]:
    pattern = [
        (0.0, 0.5, 72), (0.5, 0.5, 75), (1.0, 0.75, 77), (2.0, 0.5, 75),
        (2.5, 0.5, 70), (3.0, 0.75, 68), (4.0, 0.5, 72), (4.5, 0.5, 77),
        (5.0, 0.5, 80), (5.5, 0.5, 77), (6.0, 0.5, 75), (7.0, 0.75, 70),
    ]
    notes = []
    for copy, offset in enumerate([0, 32, 64, 96]):
        for idx, (beat, dur, midi) in enumerate(pattern):
            notes.append({
                "id": f"jcs-note-{copy}-{idx}",
                "beat": beat + offset,
                "duration": dur,
                "note": midi + (12 if copy == 1 else 0),
                "velocity": 0.88,
                "color": "#8bd3ff",
            })
    return notes


def render() -> None:
    EXPORTS.mkdir(parents=True, exist_ok=True)
    PROJECTS.mkdir(parents=True, exist_ok=True)

    stems = {
        "sample_bass_synth": lane(),
        "analog_bass": lane(),
        "room_layer": lane(),
        "clap_stack": lane(),
        "breaths": lane(),
        "vocal_chops": lane(),
        "risers": lane(),
        "prebuild_drums": lane(),
        "rave_generator": lane(),
        "lead_tease": lane(),
        "random_filler": lane(),
        "drop_drums": lane(),
        "drop_vocals": lane(),
        "drop_lead": lane(),
        "sub": lane(),
        "crash_layers": lane(),
        "glitch_tail": lane(),
        "second_drop_synths": lane(),
        "sirens_lasers": lane(),
        "transition_fx": lane(),
    }

    bass_pattern = [(0.0, 1.5, 41), (1.75, 0.75, 41), (2.75, 0.75, 44), (3.5, 0.5, 39)]
    for bar in [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 48, 50, 52, 54]:
        for beat, dur, midi in bass_pattern:
            add(stems["sample_bass_synth"], bar, sample_bass_synth(note(midi), dur * dsp.BEAT, motion=0.35 + (bar % 4) * 0.08), 0.38, -0.04, beat)
            add(stems["analog_bass"], bar, analog_layer(note(midi - 12), dur * dsp.BEAT), 0.26, 0.02, beat)

    for bar in [8, 12, 16, 20, 48, 52]:
        for chord in ([53, 56, 60], [51, 55, 58], [49, 53, 56], [48, 51, 55]):
            for midi in chord:
                add(stems["room_layer"], bar + (midi % 4) * 0.02, dark_room_layer(note(midi), 3.8 * dsp.BEAT), 0.22, (midi % 3 - 1) * 0.18)

    for bar in range(8, 72):
        if bar in range(24, 32) or bar in range(56, 64):
            continue
        for beat in [1.0, 3.0]:
            add(stems["clap_stack"], bar, dsp.snare(clap=True), 0.46, -0.10, beat)
            add(stems["clap_stack"], bar, dsp.snare(clap=True), 0.30, 0.18, beat + 0.035)
            add(stems["clap_stack"], bar, dsp.snare(), 0.24, 0.02, beat + 0.08)
        if bar >= 32:
            add(stems["clap_stack"], bar, dsp.snare(), 0.18, -0.24, 2.5)

    for bar in [2, 6, 10, 14, 18, 22, 30, 46, 54, 62]:
        add(stems["breaths"], bar, breath(0.8), 0.42, -0.62, 0.2)
        add(stems["breaths"], bar, breath(0.7), 0.36, 0.70, 2.35)

    vocal_notes = [72, 75, 77, 70, 72, 80, 77, 75]
    for bar in [12, 16, 20, 24, 32, 36, 40, 44, 48, 56, 64, 68]:
        for idx, midi in enumerate(vocal_notes):
            beat = (idx * 0.5) % 4.0
            source = fresh_air_chop if bar in [16, 20, 24, 56, 64, 68] else vocal_chop
            add(stems["vocal_chops"], bar, source(note(midi), 0.34 * dsp.BEAT), 0.24 + 0.02 * (idx % 2), -0.36 if idx % 2 else 0.34, beat)

    for bar in [0, 4, 14, 22, 24, 28, 30, 54, 56, 60, 62, 70]:
        add(stems["risers"], bar, dsp.riser(2.0 * dsp.BEAT, 180.0, 1600.0), 0.28, -0.12)
        add(stems["risers"], bar + 1, dsp.downlifter(1.6 * dsp.BEAT), 0.22, 0.18)
    for bar in [8, 24, 32, 48, 56, 64, 71]:
        add(stems["transition_fx"], bar, dsp.impact(), 0.56, 0.0)
    add(stems["transition_fx"], 0, dsp.downlifter(2.2), 0.35, -0.2)

    for bar in list(range(24, 32)) + list(range(56, 64)):
        for beat in np.arange(0, 4, 0.5):
            gain = 0.18 + 0.018 * (bar % 4) + 0.018 * beat
            add(stems["prebuild_drums"], bar, dsp.snare(clap=True), gain, -0.16 if int(beat * 2) % 2 else 0.18, float(beat))
        for beat in [0, 2]:
            add(stems["prebuild_drums"], bar, dsp.kick(), 0.38, 0, beat)
        if bar in [30, 31, 62, 63]:
            for beat in np.arange(0, 4, 0.25):
                add(stems["prebuild_drums"], bar, dsp.hat(), 0.12 + 0.02 * beat, 0.34, float(beat))

    for bar in [16, 20, 24, 26, 28, 56, 58, 60, 62]:
        for beat, midi in [(0.0, 65), (1.0, 68), (2.0, 63), (2.75, 70), (3.25, 68)]:
            add(stems["rave_generator"], bar, rave_stab(note(midi), 0.46 * dsp.BEAT), 0.34, -0.18 if beat < 2 else 0.22, beat)

    tease_notes = [72, 75, 77, 75, 70, 72, 80, 77]
    for bar in [28, 29, 30, 31, 60, 61, 62, 63]:
        for idx, midi in enumerate(tease_notes):
            add(stems["lead_tease"], bar, lead_layer(note(midi + (12 if bar < 32 else 0)), 0.22 * dsp.BEAT), 0.18, -0.28 if idx % 2 else 0.28, idx * 0.5)

    for bar in [24, 25, 27, 29, 31, 48, 50, 52, 54, 56, 59, 61, 63, 68, 70]:
        add(stems["random_filler"], bar, wamp_synth(note(58 + (bar % 5)), 0.72 * dsp.BEAT, rate=3.0 + (bar % 3), harsh=0.75), 0.12, -0.52 + (bar % 4) * 0.34, 1.25)
        add(stems["random_filler"], bar, breath(0.45), 0.15, 0.58, 3.1)

    for bar in list(range(32, 48)) + list(range(64, 72)):
        add(stems["drop_drums"], bar, dsp.kick(), 0.84, 0.0, 0.0)
        add(stems["drop_drums"], bar, dsp.kick(), 0.54, 0.0, 2.0)
        add(stems["drop_drums"], bar, dsp.snare(clap=True), 0.62, -0.08, 1.0)
        add(stems["drop_drums"], bar, dsp.snare(clap=True), 0.55, 0.08, 3.0)
        for beat in np.arange(0, 4, 0.25):
            add(stems["drop_drums"], bar, dsp.hat(), 0.11 if beat % 1 else 0.14, 0.34, float(beat))
        if bar % 4 == 0:
            add(stems["crash_layers"], bar, slow_attack_crash(), 0.40, -0.28)
            add(stems["crash_layers"], bar, dsp.hat(open_hat=True), 0.30, 0.36)
            add(stems["crash_layers"], bar, dsp.snare(), 0.12, 0.0, 0.05)
        if bar % 8 == 4:
            add(stems["crash_layers"], bar, dsp.ride(), 0.20, 0.44)

    drop_pattern = [(0.0, 0.5, 72), (0.5, 0.5, 75), (1.0, 0.75, 77), (2.0, 0.5, 75), (2.5, 0.5, 70), (3.0, 0.5, 68)]
    for bar in range(32, 48):
        for beat, dur, midi in drop_pattern:
            add(stems["drop_lead"], bar, lead_layer(note(midi + 12), dur * dsp.BEAT), 0.32, -0.16 if beat < 2 else 0.18, beat)
            add(stems["drop_lead"], bar, wamp_synth(note(midi), dur * dsp.BEAT, rate=2.0, harsh=1.0), 0.24, 0.0, beat)
        if bar % 4 == 3:
            add(stems["glitch_tail"], bar, glitch_tail(note(77), 0.9 * dsp.BEAT), 0.28, 0.42, 3.0)

    for bar in range(64, 72):
        for beat, dur, midi in drop_pattern:
            add(stems["second_drop_synths"], bar, wamp_synth(note(midi - 12), dur * dsp.BEAT, rate=1.5, harsh=1.35), 0.42, -0.10, beat)
            add(stems["second_drop_synths"], bar, lead_layer(note(midi), dur * dsp.BEAT), 0.24, 0.20, beat)
        if bar % 2 == 0:
            add(stems["sirens_lasers"], bar, laser(0.95 * dsp.BEAT, down=bar % 4 == 0), 0.28, -0.42, 3.0)

    for bar in list(range(32, 48)) + list(range(64, 72)):
        root = 29 if bar >= 64 else 41
        add(stems["sub"], bar, sub_patch(note(root), 3.8 * dsp.BEAT, long=True), 0.52, 0.0)
        if bar % 4 == 2:
            add(stems["sub"], bar, sub_patch(note(root + 3), 1.5 * dsp.BEAT), 0.32, 0.0, 2.0)

    for bar in [32, 36, 40, 44, 64, 68]:
        for idx, midi in enumerate([72, 70, 75, 77]):
            add(stems["drop_vocals"], bar, vocal_chop(note(midi), 0.42 * dsp.BEAT, bright=1.2), 0.30, -0.55 if idx % 2 else 0.55, idx)
        add(stems["drop_vocals"], bar, fresh_air_chop(note(65), 0.36 * dsp.BEAT), 0.22, 0.0, 2.5)

    for bar in [44, 45, 46, 47, 64, 66, 68, 70]:
        add(stems["sirens_lasers"], bar, laser(0.65 * dsp.BEAT, down=False), 0.23, 0.52, 0.5)
        add(stems["sirens_lasers"], bar, laser(0.65 * dsp.BEAT, down=True), 0.18, -0.52, 2.5)

    for name in [
        "sample_bass_synth", "analog_bass", "room_layer", "vocal_chops", "rave_generator",
        "lead_tease", "random_filler", "drop_vocals", "drop_lead", "second_drop_synths",
        "sirens_lasers", "glitch_tail", "transition_fx"
    ]:
        dsp.apply_ducking(stems[name], amount=0.18 if name in ["transition_fx", "sirens_lasers"] else 0.34, release=0.18)

    for name, args in {
        "vocal_chops": (0.5, 0.42, 0.26, 5),
        "drop_vocals": (0.375, 0.48, 0.32, 6),
        "lead_tease": (0.25, 0.38, 0.22, 4),
        "drop_lead": (0.375, 0.42, 0.22, 4),
        "second_drop_synths": (0.25, 0.35, 0.16, 3),
        "glitch_tail": (0.25, 0.45, 0.36, 5),
        "transition_fx": (0.5, 0.38, 0.18, 4),
    }.items():
        dsp.add_delay(stems[name], *args)

    gains = {
        "sample_bass_synth": 0.72,
        "analog_bass": 0.54,
        "room_layer": 0.50,
        "clap_stack": 0.70,
        "breaths": 0.60,
        "vocal_chops": 0.68,
        "risers": 0.72,
        "prebuild_drums": 0.72,
        "rave_generator": 0.64,
        "lead_tease": 0.58,
        "random_filler": 0.54,
        "drop_drums": 0.86,
        "drop_vocals": 0.74,
        "drop_lead": 0.78,
        "sub": 0.82,
        "crash_layers": 0.68,
        "glitch_tail": 0.62,
        "second_drop_synths": 0.82,
        "sirens_lasers": 0.64,
        "transition_fx": 0.74,
    }

    full_mix = lane()
    for name, stem in stems.items():
        full_mix += stem * gains[name]
    full_mix = dsp.soft_clip(full_mix, drive=1.45) * 0.92

    dsp.write_wav(EXPORTS / "just_cant_stop_full_mix.wav", full_mix)
    for name, stem in stems.items():
        stem_audio = dsp.soft_clip(stem * gains[name], drive=1.12) * 0.90
        dsp.write_wav(EXPORTS / f"just_cant_stop_{name}.wav", stem_audio)

    colors = {
        "sample_bass_synth": "#5de1b2",
        "analog_bass": "#8ad8a0",
        "room_layer": "#a88cff",
        "clap_stack": "#ff9a72",
        "breaths": "#d8ecff",
        "vocal_chops": "#f6a6d7",
        "risers": "#d885ff",
        "prebuild_drums": "#ffb45a",
        "rave_generator": "#ffdf6e",
        "lead_tease": "#8bd3ff",
        "random_filler": "#c9ff7a",
        "drop_drums": "#ff704f",
        "drop_vocals": "#ff82c0",
        "drop_lead": "#62c8ff",
        "sub": "#45d18e",
        "crash_layers": "#f0f7a8",
        "glitch_tail": "#cfa6ff",
        "second_drop_synths": "#7fa7ff",
        "sirens_lasers": "#ff5f71",
        "transition_fx": "#d885ff",
    }

    track_specs = [
        ("sample_bass_synth", "Sample Bass Synth", 0.72, -0.04, [0, 3, 7, 10], "Granular one-note bass-synth sample", [(0, 24, "Pre-intro and intro bass-synth line"), (48, 8, "Second-part bass-synth callback")], [
            make_effect("sample-loop", "Long Sample Loop Stretch", 0.72),
            make_effect("filter-drive", "Driven Lowpass Filter", 0.66),
            make_effect("multiband", "Dank Sauce Multiband", 0.58),
        ]),
        ("analog_bass", "Analog Bass", 0.54, 0.02, [0, 7, 10], "Simple analog hardware bass layer", [(0, 24, "Analog support under sample bass"), (48, 8, "Analog callback")], [
            make_effect("super-six", "Super Six Analog Layer", 0.62),
            make_effect("lowpass", "Warm Lowpass", 0.52),
        ]),
        ("room_layer", "Dark Room Layer", 0.50, -0.12, [0, 4, 8, 12], "Dark Omnisphere-style room/delay layer", [(8, 16, "Dark intro harmony room"), (48, 8, "Second section room layer")], [
            make_effect("omni", "Omnisphere Sonic Extension Layer", 0.66),
            make_effect("room", "Springy Room Reverb", 0.58),
            make_effect("delay", "Stereo Delay", 0.46),
        ]),
        ("clap_stack", "Same Clap Stack", 0.70, 0.04, [4, 12], "Layered random claps reused through the song", [(8, 16, "Intro and bridge claps"), (32, 16, "Drop clap stack"), (64, 8, "Second drop clap stack")], [
            make_effect("same-claps", "Same Claps Throughout", 1.0),
            make_effect("room", "Valhalla Room Layer", 0.42),
        ]),
        ("breaths", "Stereo Breaths", 0.60, 0.0, [2, 7, 11, 15], "Random wide breath texture", [(2, 22, "Intro breath spread"), (46, 18, "Background breath fills")], [
            make_effect("wide", "Stereo Spread", 0.82),
            make_effect("air", "High Air Shelf", 0.58),
        ]),
        ("vocal_chops", "Fresh Vocal Chops", 0.68, 0.0, [0, 2, 5, 8, 10, 13], "Synthetic vocal loop and chopped bright vocal bits", [(12, 20, "Looped and chopped vocal prebuild"), (56, 16, "Second build chopped vocal")], [
            make_effect("fresh-air", "Fresh Air Mid/High Brightener", 0.86),
            make_effect("pingpong", "Left/Right Delay", 0.72),
            make_effect("chorus", "Chorus Tag Brightener", 0.36),
        ]),
        ("risers", "Dynamic Risers", 0.72, 0.0, [0, 8, 12, 15], "Dynamic risers, sweeps, and downlifters", [(0, 8, "Dramatic pre-intro sweeps"), (22, 10, "Build risers"), (54, 10, "Second build risers")], [
            make_effect("transit", "Transit-style Macro Rise", 0.78),
            make_effect("noise-up", "White Noise Up", 0.68),
        ]),
        ("prebuild_drums", "Build Loop", 0.72, 0.0, [0, 2, 4, 6, 8, 10, 12, 14], "Hype prebuild loop with trap snares and hats", [(24, 8, "Green-room style build loop"), (56, 8, "Second build loop")], [
            make_effect("chants", "Chant/Trap Snare Loop", 0.56),
            make_effect("white-noise", "Big Snare White Noise", 0.52),
        ]),
        ("rave_generator", "Rave Generator", 0.64, 0.0, [0, 4, 8, 11], "Old-school rave stab fourth/fifth/seventh color", [(16, 16, "Beat and bloody pulp-style stabs"), (56, 8, "Second build old-school stabs")], [
            make_effect("ott", "OTT-style Multiband", 0.58),
            make_effect("crystalline", "Crystalline Metallic Reverb", 0.48),
        ]),
        ("lead_tease", "Lead Tease", 0.58, 0.0, [0, 2, 4, 7, 10, 12], "Drop lead teased in the build", [(28, 4, "First drop lead preview"), (60, 4, "Second drop lead preview")], [
            make_effect("og-trap", "OG Trap Lead Tease", 0.66),
            make_effect("delay", "Bouncing Delay", 0.52),
        ]),
        ("random_filler", "Random Filler", 0.54, 0.0, [1, 5, 9, 13], "Low background space-filler sounds", [(24, 8, "Build wacky filler"), (48, 16, "Humanoid/vocoder-style background"), (68, 4, "Outro filler chaos")], [
            make_effect("humanoid", "Humanoid Vocoder Texture", 0.54),
            make_effect("mono-space", "Low Space Filler", 0.42),
        ]),
        ("drop_drums", "Drop Drums", 0.86, 0.0, [0, 2, 4, 8, 12, 14], "Clicky kick, trap hats, snares", [(32, 16, "First drop drums"), (64, 8, "Second drop drums")], [
            make_effect("pultec", "Pultec-style Kick Low Boost", 0.64),
            make_effect("tiny-hat-eq", "Tiny Hat Highpass 474 Hz", 0.74),
            make_effect("brute-force", "Brute Force Drum Stack", 0.62),
        ]),
        ("drop_vocals", "Drop Vocals", 0.74, 0.0, [0, 3, 6, 9, 12], "Hectic vocal rhythm and call-response breaks", [(32, 16, "Top-of-session drop vocal rhythm"), (64, 8, "Second drop vocal tags")], [
            make_effect("hectic-delay", "Hectic Ping-Pong Delay", 0.82),
            make_effect("call-response", "Call Response Breaks", 0.64),
        ]),
        ("drop_lead", "Drop Lead", 0.78, 0.0, [0, 2, 5, 8, 11, 14], "Wave-shaped lead group with sizzle and low cuts", [(32, 16, "First drop lead up octave")], [
            make_effect("wave-shaper", "Melda-style Wave Shaper", 0.76),
            make_effect("clipper", "Clipper", 0.54),
            make_effect("low-cut", "EQ Low Cut", 0.72),
            make_effect("snapheap", "Snap Heap Phase Distortion", 0.58),
            make_effect("crystalline", "Crystalline Metallic Reverb", 0.42),
        ]),
        ("sub", "Driven Sub", 0.82, 0.0, [0, 8], "Triangle/saw sub with white-noise filter drive", [(32, 16, "Long drawn-out sub under wamps"), (64, 8, "Second drop sub continuity")], [
            make_effect("triangle", "Triangle/Saw Sub Core", 0.64),
            make_effect("bright-white", "Bright White Into Filter Drive", 0.74),
            make_effect("sidechain", "Sidechain", 0.64),
        ]),
        ("crash_layers", "Crash Layers", 0.68, 0.0, [0, 8], "Open hats, slow-attack snare, operator noise crash stack", [(32, 16, "Drop crash stack"), (64, 8, "Second drop crash stack")], [
            make_effect("open-hat", "Pitched-down Open Hat", 0.48),
            make_effect("snare-crash", "Slow Attack Snare Crash", 0.42),
            make_effect("operator-noise", "Operator White Noise", 0.62),
        ]),
        ("glitch_tail", "Glitch Tail", 0.62, 0.12, [3, 7, 11, 15], "Chopped lead reverb tail and trashy glitch fill", [(35, 12, "Chopped reverb-tail fills")], [
            make_effect("trash", "Trash Glitch Chop", 0.58),
            make_effect("reverb-tail", "Frozen Reverb Tail", 0.66),
        ]),
        ("second_drop_synths", "Second Drop Synths", 0.82, -0.02, [0, 4, 8, 12], "Huge preset-style second drop synths", [(64, 8, "Big nuke second drop synth")], [
            make_effect("big-nuke", "Big Nuke Preset Layer", 0.76),
            make_effect("polysat", "PolySaturator Harmonics", 0.58),
            make_effect("serum-fx", "Serum FX Preset Chain", 0.54),
            make_effect("soothe", "Soothe Resonance Ducking", 0.42),
            make_effect("eq250", "Low Cut at 250", 0.66),
        ]),
        ("sirens_lasers", "Sirens Lasers", 0.64, 0.0, [3, 7, 11, 15], "Old-trap siren and laser accents", [(44, 4, "First drop siren answer"), (64, 8, "Second drop lasers")], [
            make_effect("pitch-rise", "Quick Pitch Rise/Fall", 0.82),
            make_effect("mono", "Mono Utility", 0.44),
            make_effect("vintage-verb", "VintageVerb Color Now", 0.46),
        ]),
        ("transition_fx", "Transit Macro FX", 0.74, 0.0, [0, 15], "Transit/Endless Smile transition processing", [(0, 8, "Intro reverse and impact drama"), (24, 8, "First build transition macro"), (56, 8, "Second build transition macro"), (70, 2, "Ending transition")], [
            make_effect("transit2", "Transit 2 Gritty Delays", 0.84),
            make_effect("macro", "Highpass/Lowpass/Notch Macro", 0.78),
        ]),
    ]

    tracks = []
    for stem_name, title, gain, pan, steps, instrument, clip_specs, effects in track_specs:
        color = colors[stem_name]
        tracks.append(make_track(
            stem_name.replace("_", "-"),
            title,
            f"just_cant_stop_{stem_name}.wav",
            color,
            gain,
            pan,
            steps,
            instrument,
            [make_clip(f"{stem_name}-{start}", label, start, bars, stem_name.replace("_", "-"), color) for start, bars, label in clip_specs],
            effects,
        ))

    controls = {
        track["id"]: {"gain": track["gain"], "pan": track["pan"], "mute": False, "solo": False, "arm": False, "sendA": 0.18, "sendB": 0.12}
        for track in tracks
    }

    recipe = [
        ("chronological", "Foundation", "Chronological walkthrough layout", "Project sections are arranged as pre-intro, intro, bridge/prebuild, build, drop, second part, second build, second drop.", ["transition-fx", "sample-bass-synth", "drop-drums"]),
        ("sample-selection", "Foundation", "Sample-selection-first workflow", "Tracks are split around long main samples, found textures, and selected one-shot layers rather than over-designed patches.", ["sample-bass-synth", "breaths", "random-filler"]),
        ("least-layers", "Foundation", "Least necessary layers principle", "The heavy sounds are few focused lanes, with extra layers only where the transcript calls them out.", ["drop-lead", "second-drop-synths", "sub"]),
        ("pre-intro-drama", "Intro", "Extra drama before the main loop", "Transit Macro FX and Risers create the dramatic sweep/reverse opening before the bass-synth line lands.", ["transition-fx", "risers"]),
        ("reverse-first-sound", "Intro", "Reverse of the first synth sound", "The opening FX lane includes reverse/downlifter motion into the first bass-synth phrase.", ["transition-fx", "sample-bass-synth"]),
        ("main-sample-bass", "Intro", "Long one-note sample as main synth", "Sample Bass Synth acts like the long source sample, stretched into the central bass-synth line.", ["sample-bass-synth"]),
        ("analog-layer", "Intro", "Simple analog bass layer", "Analog Bass doubles the sampled synth with a simple warm hardware-style layer.", ["analog-bass"]),
        ("same-claps", "Intro", "Layered random claps", "Same Clap Stack reuses the same claps in the intro, build, and drops.", ["clap-stack"]),
        ("omni-room", "Intro", "Omnisphere-style room/delay layer", "Dark Room Layer carries the room and delay color from the walkthrough.", ["room-layer"]),
        ("darker-melody", "Intro", "Darker melody direction", "The harmony and lead notes use a darker minor center instead of the earlier happy future-bass melody shape.", ["room-layer", "drop-lead"]),
        ("breaths", "Intro", "Wide breath texture", "Stereo Breaths are random wide details that fill the intro spread.", ["breaths"]),
        ("vocal-found", "Intro", "Found vocal idea", "Fresh Vocal Chops provide the vocal-sample role with synthetic, original chops.", ["vocal-chops"]),
        ("dynamic-risers", "Intro", "Dynamic risers into the next section", "Dynamic Risers mark every major lift into the following sections.", ["risers"]),
        ("hype-prebuild", "Build", "Lit hype bridge/prebuild", "Build Loop, Fresh Vocal Chops, and Rave Generator create the high-energy prebuild bridge.", ["prebuild-drums", "vocal-chops", "rave-generator"]),
        ("vocal-loop", "Build", "Looped vocal with chopped edits", "Fresh Vocal Chops repeats and slices the vocal rhythm through the bridge and build.", ["vocal-chops"]),
        ("fresh-air", "Build", "Fresh Air brightness", "Fresh Vocal Chops has a Fresh Air mid/high brightener slot.", ["vocal-chops"]),
        ("sonic-extension", "Build", "Sonic-extension-style preset source", "Rave Generator and Dark Room Layer represent the preset-pack sounds with post-processing.", ["rave-generator", "room-layer"]),
        ("dank-sauce", "Build", "Dank Sauce / OTT-style compression", "Rave Generator has OTT-style multiband processing, and the bass synth has a multiband slot.", ["rave-generator", "sample-bass-synth"]),
        ("crystalline", "Build", "Crystalline metallic reverb", "Rave Generator and Drop Lead both include Crystalline-style metallic reverb slots.", ["rave-generator", "drop-lead"]),
        ("reverb-dynamics", "Mix", "Dry versus wet reverb dynamics", "Driven Sub stays dry while room, lead, and rave lanes carry distinct reverb spaces.", ["sub", "room-layer", "drop-lead", "rave-generator"]),
        ("bouncing-delays", "Build", "Left/right bouncing delays", "Lead Tease and vocal lanes use ping-pong/bouncing delay effect slots and rendered delay tails.", ["lead-tease", "vocal-chops", "drop-vocals"]),
        ("rave-generator", "Build", "Old-school Rave Generator color", "Rave Generator uses fourth/fifth/seventh-style stab coloration before the drop.", ["rave-generator"]),
        ("lead-tease", "Build", "Tease the drop lead in the build", "Lead Tease sneaks the drop line into the buildup.", ["lead-tease"]),
        ("green-room-loop", "Build", "Trap build-loop sample role", "Build Loop covers the chant/trap snare/white-noise build loop role.", ["prebuild-drums"]),
        ("random-build-filler", "Build", "Random background filler in build", "Random Filler adds low background space between build hits.", ["random-filler"]),
        ("drop-vocals-top", "Drop", "Vocals at the top of the drop session", "Drop Vocals is a dedicated top lane with rhythmic chops and delays.", ["drop-vocals"]),
        ("call-response", "Drop", "Call-response vocal breaks", "Drop Vocals marks the beat breaks where vocal answers signal a change.", ["drop-vocals"]),
        ("hiphop-tag", "Drop", "Tag-like vocal moment", "Drop Vocals contains original tag-like vocal chops, not copied commercial tags.", ["drop-vocals"]),
        ("clicky-kick", "Drop", "Big clicky kick", "Drop Drums uses a clicky kick with a Pultec-style low boost slot.", ["drop-drums"]),
        ("pultec-kick", "Mix", "Pultec-style kick low boost", "Drop Drums exposes the Pultec-style kick low boost from the walkthrough.", ["drop-drums"]),
        ("snare-layers", "Drop", "Three-layer snare/clap stack", "Same Clap Stack layers clap, snare, and offbeat snare elements.", ["clap-stack"]),
        ("jingle-snare", "Drop", "Jingle/snare color", "Same Clap Stack and Crash Layers hold extra transient color without over-EQ.", ["clap-stack", "crash-layers"]),
        ("offbeat-snare", "Drop", "Offbeat trap snare layer", "Same Clap Stack includes offbeat snare support around the main backbeat.", ["clap-stack"]),
        ("tiny-hat", "Drop", "Tiny high hat that never changes", "Drop Drums carries a simple repeating tiny hat rhythm.", ["drop-drums"]),
        ("hat-highpass", "Mix", "Hat high-pass around 474 Hz", "Drop Drums includes a Tiny Hat Highpass 474 Hz effect slot.", ["drop-drums"]),
        ("crash-stack", "Drop", "Crash stack with open hat, snare, and noise", "Crash Layers separates open hats, slow-attack snare, and operator-style white noise.", ["crash-layers"]),
        ("mid-side-concept", "Mix", "Middle/side coverage for cymbals", "Crash Layers and Stereo Breaths are panned/wide so the high end covers middle and sides.", ["crash-layers", "breaths"]),
        ("serum-wamp", "Drop", "Simple Serum-style wamp synth", "Drop Lead and Second Drop Synths use basic-shape wamp synthesis with post-processing.", ["drop-lead", "second-drop-synths"]),
        ("noise-filter-drive", "Drop", "White noise routed into driven filter", "Driven Sub and Drop Lead include noise/filter-drive style grit.", ["sub", "drop-lead"]),
        ("lead-sizzle", "Drop", "High sizzle layer completing the lead", "Drop Lead includes high sizzle and wave-shaped brightness.", ["drop-lead"]),
        ("wave-shaper", "Drop", "Wave shaper and clipper on lead", "Drop Lead has wave shaper and clipper effect slots.", ["drop-lead"]),
        ("low-cut-lead", "Mix", "Cut lows out of the lead", "Drop Lead includes EQ Low Cut before the sub owns the low end.", ["drop-lead", "sub"]),
        ("snapheap-phase", "Drop", "Snap Heap phase distortion", "Drop Lead includes a Snap Heap phase distortion slot.", ["drop-lead"]),
        ("glitch-tail", "Drop", "Chopped/glitched reverb tail", "Glitch Tail renders the chopped frozen reverb-tail idea.", ["glitch-tail"]),
        ("chaos-filler", "Drop", "Chaotic background filler", "Random Filler runs through drop and build sections as low background chaos.", ["random-filler"]),
        ("sub-patch", "Drop", "Just Cant Stop sub patch", "Driven Sub uses triangle/saw core plus bright white noise into a driven filter.", ["sub"]),
        ("long-sub", "Drop", "Long drawn-out sub under wamps", "Driven Sub sustains through wamp moments instead of retriggering every wobble.", ["sub"]),
        ("first-drop-octave", "Drop", "First drop lead up an octave", "Drop Lead labels the first drop as an octave-up lead layer.", ["drop-lead"]),
        ("second-part-vocoder", "Drop", "Humanoid/vocoder background in second part", "Random Filler includes the humanoid/vocoder-style background role.", ["random-filler"]),
        ("second-drop", "Drop", "Second drop with new huge sound", "Second Drop Synths adds the later, bigger preset-style synth layer.", ["second-drop-synths"]),
        ("big-nuke", "Drop", "Big nuke preset-style second drop", "Second Drop Synths has a Big Nuke preset layer slot.", ["second-drop-synths"]),
        ("old-trap-sirens", "Drop", "Old-trap sirens and lasers", "Sirens Lasers handles the Flosstradamus/Uzi-era trap laser gesture.", ["sirens-lasers"]),
        ("pitch-rise-fall", "Drop", "Pitch rise/fall laser modulation", "Sirens Lasers includes quick pitch rise/fall processing.", ["sirens-lasers"]),
        ("polysaturator", "Mix", "PolySaturator harmonics", "Second Drop Synths includes PolySaturator-style harmonic enhancement.", ["second-drop-synths"]),
        ("serum-fx", "Mix", "Serum FX preset chain", "Second Drop Synths includes a Serum FX preset-chain slot.", ["second-drop-synths"]),
        ("mono-utility", "Mix", "Mono utility on second drop layer", "Sirens Lasers includes mono utility processing.", ["sirens-lasers"]),
        ("vintage-verb", "Mix", "VintageVerb Color Now", "Sirens Lasers includes VintageVerb Color Now.", ["sirens-lasers"]),
        ("ott-soothe", "Mix", "OTT/multiband and Soothe cleanup", "Second Drop Synths includes OTT-style treatment and Soothe resonance ducking.", ["second-drop-synths"]),
        ("eq250", "Mix", "Simple low cut around 250", "Second Drop Synths includes the quick low cut at 250 idea.", ["second-drop-synths"]),
        ("transit", "Advanced", "Transit/Endless Smile-style transition control", "Transit Macro FX has Transit 2 gritty delays and macro filter movement.", ["transition-fx"]),
        ("share-sauce", "Advanced", "Plugin-chain documentation in project file", "The recipe and effect slots document the sauce so the project file explains the walkthrough.", ["drop-lead", "second-drop-synths", "transition-fx"]),
    ]

    recipe_items = [
        {
            "id": id_,
            "section": section,
            "label": label,
            "detail": detail,
            "status": "implemented",
            "trackIds": track_ids,
        }
        for id_, section, label, detail, track_ids in recipe
    ]

    snapshot = {
        "version": 3,
        "bpm": BPM,
        "swing": 12,
        "snap": "1/8",
        "loopEnabled": True,
        "loopStartBar": 32,
        "loopEndBar": 48,
        "tracks": tracks,
        "controls": controls,
        "notes": make_notes(),
        "selectedTrackId": "drop-lead",
        "selectedClipId": "drop_lead-32",
        "activeView": "playlist",
        "patternIndex": 1,
        "arrangementMode": "song",
        "recipe": recipe_items,
    }
    assets = [{"trackId": track["id"], "file": track["file"]} for track in tracks]
    project = {
        "format": "neon-studio-project",
        "formatVersion": 1,
        "portable": True,
        "assetMode": "external",
        "id": "just-cant-stop",
        "name": "Just Cant Stop",
        "createdAt": "2026-04-19T00:00:00.000Z",
        "updatedAt": "2026-04-19T00:00:00.000Z",
        "description": "Original dark trap/festival production following the supplied walkthrough techniques without copying the commercial song.",
        "keyCenter": KEY_CENTER,
        "assets": assets,
        "snapshot": snapshot,
    }
    (PROJECTS / "just-cant-stop.neon.json").write_text(json.dumps(project, indent=2) + "\n", encoding="utf-8")

    print(f"Rendered Just Cant Stop: {len(stems)} stems, {len(recipe_items)} recipe items")


if __name__ == "__main__":
    render()
