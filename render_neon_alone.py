#!/usr/bin/env python3
"""Render Neon Alone as an original Marshmello/Alone-lane future-bass sketch.

The reference target is production feel: 142 BPM, D major, simple bright hook,
wide pumped chords, clean sub/mid bass, trap drums, clear builds, and a bigger
second drop. This renderer does not copy the commercial topline, lyrics, sample,
or stems.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import render_neon_solitude as dsp


ROOT = Path(__file__).resolve().parent
EXPORTS = ROOT / "exports"
MIDI_DIR = ROOT / "midi"
PROJECT_ID = "neon-alone"
PROJECT_NAME = "Neon Alone"
SR = dsp.SR
BPM = 142
BEAT = 60.0 / BPM
TOTAL_BARS = 80
TAIL_SECONDS = 4.0
N_SAMPLES = int((TOTAL_BARS * 4 * BEAT + TAIL_SECONDS) * SR)
PROJECT_PATHS = [
    ROOT / "data" / "projects" / f"{PROJECT_ID}.neon.json",
    ROOT / "factory" / "projects" / f"{PROJECT_ID}.neon.json",
]


ASSET_FILES = {
    "drums": "neon_alone_drums.wav",
    "clap-stack": "neon_alone_clap_stack.wav",
    "hat-ride": "neon_alone_hat_ride.wav",
    "sub": "neon_alone_sub.wav",
    "bass": "neon_alone_bass.wav",
    "chords": "neon_alone_chords.wav",
    "lead": "neon_alone_lead.wav",
    "lead-double": "neon_alone_lead_double.wav",
    "plucks": "neon_alone_plucks.wav",
    "vocals": "neon_alone_hook_echo.wav",
    "fx": "neon_alone_fx.wav",
}

TRACK_COLORS = {
    "drums": "#ff8d5c",
    "clap-stack": "#fb7185",
    "hat-ride": "#f4f1a3",
    "sub": "#34d399",
    "bass": "#4ade80",
    "chords": "#ffd166",
    "lead": "#6fd6ff",
    "lead-double": "#9ec5ff",
    "plucks": "#f9a8d4",
    "vocals": "#f59fcb",
    "fx": "#d78bff",
    "filter-auto": "#7dd3fc",
}

SECTIONS = [
    ("Intro", 0, 8, "Filtered D-major hook fragments and soft chord bed."),
    ("Verse", 8, 8, "Sparse hook, plucks, muted synth-guitar feel, and simple drum pocket."),
    ("Build 1", 16, 8, "Lead tease, clap/snare lift, riser, and widening filter automation."),
    ("Drop 1", 24, 16, "Open future-bass drop with square/saw hook and pumped supersaws."),
    ("Break", 40, 8, "Filtered chord reset with echo hook tails and distant air."),
    ("Build 2", 48, 8, "Stronger riser, double-time hats, fake stop, and wider macro lift."),
    ("Drop 2", 56, 16, "Bigger second drop with octave lead double, ride, crashes, and clean sparkle."),
    ("Outro", 72, 8, "Drums drop out into hook echo, chord tail, and downlifter."),
]

CHORDS = [
    ("D", [50, 54, 57, 62], 50),
    ("A", [45, 52, 57, 61], 45),
    ("Bm", [47, 54, 59, 62], 47),
    ("G", [43, 50, 55, 59], 43),
]

INTRO_MOTIF = [
    (0.0, 0.52, 74, 70),
    (0.5, 0.42, 74, 64),
    (1.0, 0.76, 78, 74),
    (2.0, 0.46, 76, 66),
    (2.5, 0.38, 74, 64),
    (3.0, 0.72, 71, 66),
]

DROP_MOTIF = [
    (0.00, 0.46, 74, 114),
    (0.50, 0.38, 74, 96),
    (1.00, 0.76, 78, 114),
    (2.00, 0.46, 76, 102),
    (2.50, 0.38, 74, 98),
    (3.00, 0.72, 71, 102),
]

DROP_PHRASE = [
    DROP_MOTIF,
    [
        (0.00, 0.46, 74, 112),
        (0.50, 0.38, 74, 94),
        (1.00, 0.76, 81, 116),
        (2.00, 0.46, 78, 104),
        (2.50, 0.38, 76, 98),
        (3.00, 0.72, 74, 104),
    ],
    [
        (0.00, 0.46, 74, 112),
        (0.50, 0.38, 74, 94),
        (1.00, 0.76, 78, 114),
        (2.00, 0.46, 76, 102),
        (2.50, 0.38, 74, 98),
        (3.00, 0.72, 69, 100),
    ],
    [
        (0.00, 0.46, 71, 104),
        (0.50, 0.38, 74, 100),
        (1.00, 0.76, 76, 108),
        (2.00, 0.46, 78, 112),
        (2.50, 0.38, 76, 100),
        (3.00, 0.92, 74, 106),
    ],
]

SPARKLE_MOTIF = [
    (3.00, 0.18, 81, 60),
    (3.50, 0.18, 78, 56),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def lane() -> np.ndarray:
    return np.zeros((N_SAMPLES, 2), dtype=np.float32)


def bar_beat(bar: int, beat: float = 0.0) -> float:
    return bar * 4.0 + beat


def beat_to_seconds(beat: float) -> float:
    return beat * BEAT


def add_audio(stem: np.ndarray, bar: int, audio: np.ndarray, gain: float, pan: float = 0.0, beat: float = 0.0) -> None:
    dsp.add_mono(stem, beat_to_seconds(bar_beat(bar, beat)), audio, gain=gain, pan=pan)


def schedule_note(
    stem: np.ndarray,
    midi_events: list[tuple[float, float, int, int]],
    synth,
    bar: int,
    beat: float,
    duration: float,
    note: int,
    velocity: int,
    gain: float,
    pan: float = 0.0,
    audio_extra_beats: float = 0.0,
    **kwargs,
) -> None:
    start = bar_beat(bar, beat)
    audio = synth(dsp.note_to_freq(note), (duration + audio_extra_beats) * BEAT, **kwargs)
    dsp.add_mono(stem, beat_to_seconds(start), audio, gain=gain, pan=pan)
    midi_events.append((start, duration, note, velocity))


def airy_noise(dur: float, high: bool = True) -> np.ndarray:
    n = int(dur * SR)
    noise = dsp.highpass_noise(n)
    if not high:
        noise = dsp.one_pole_lowpass(noise, 1800.0)
    t = np.arange(n, dtype=np.float32) / SR
    return (noise * np.exp(-t * 0.75).astype(np.float32)).astype(np.float32)


def mello_lead(freq: float, dur: float, soft: bool = False) -> np.ndarray:
    n = max(1, int(dur * SR))
    t = np.arange(n, dtype=np.float32) / SR
    vibrato = 1.0 + (0.0018 if soft else 0.0026) * np.sin(2.0 * np.pi * 5.0 * t)
    out = np.zeros(n, dtype=np.float32)
    for idx, cents in enumerate([-5.0, 0.0, 4.0]):
        phase = np.cumsum((freq * (2.0 ** (cents / 1200.0)) * vibrato).astype(np.float32)) / SR
        square = dsp.square_from_phase(phase)
        tri = (2.0 * np.abs(2.0 * (phase % 1.0) - 1.0) - 1.0).astype(np.float32)
        sine = np.sin(2.0 * np.pi * phase).astype(np.float32)
        out += 0.40 * square + 0.35 * tri + 0.16 * sine
        if not soft:
            out += 0.06 * dsp.saw(freq * (2.0 ** (cents / 1200.0)) * 2.0, dur, phase=0.11 * idx)
    out /= 3.0
    out = dsp.one_pole_lowpass(out, 3000.0 if soft else 4550.0)
    env = dsp.adsr(n, attack=0.006 if not soft else 0.014, decay=0.055, sustain=0.66 if soft else 0.78, release=0.10)
    return (dsp.soft_clip(out * 1.18, drive=1.08) * env).astype(np.float32)


def mello_double(freq: float, dur: float) -> np.ndarray:
    n = max(1, int(dur * SR))
    t = np.arange(n, dtype=np.float32) / SR
    out = np.zeros(n, dtype=np.float32)
    for idx, cents in enumerate([-9.0, -3.0, 5.0, 11.0]):
        out += dsp.saw(freq * (2.0 ** (cents / 1200.0)), dur, phase=0.17 * idx)
    out /= 4.0
    out += 0.20 * mello_lead(freq, dur, soft=True)
    out += 0.05 * np.sin(2.0 * np.pi * freq * 2.0 * t).astype(np.float32)
    out = dsp.one_pole_lowpass(out, 5000.0)
    env = dsp.adsr(n, attack=0.010, decay=0.060, sustain=0.62, release=0.14)
    return (out * env).astype(np.float32)


def hook_echo_tone(freq: float, dur: float) -> np.ndarray:
    n = max(1, int(dur * SR))
    t = np.arange(n, dtype=np.float32) / SR
    phase = np.cumsum((freq * (1.0 + 0.0015 * np.sin(2.0 * np.pi * 3.2 * t))).astype(np.float32)) / SR
    tri = (2.0 * np.abs(2.0 * (phase % 1.0) - 1.0) - 1.0).astype(np.float32)
    sine = np.sin(2.0 * np.pi * phase).astype(np.float32)
    breath = dsp.one_pole_lowpass(dsp.highpass_noise(n), 2400.0)
    env = dsp.adsr(n, attack=0.025, decay=0.16, sustain=0.42, release=0.30)
    return dsp.one_pole_lowpass((0.58 * sine + 0.32 * tri + 0.016 * breath) * env, 2700.0)


def sidechain(stem: np.ndarray, amount: float) -> np.ndarray:
    return dsp.apply_ducking(stem, amount=amount, release=0.22)


def widen(stem: np.ndarray, delay_ms: float, amount: float) -> None:
    delay = max(1, int(delay_ms * SR / 1000.0))
    dry = stem.copy()
    stem[delay:, 1] += dry[:-delay, 0] * amount
    stem[:-delay, 0] += dry[delay:, 1] * amount * 0.55
    stem[:, 0] *= 0.96
    stem[:, 1] *= 1.04


def render_chords(stems: dict[str, np.ndarray], midi: dict[str, list[tuple[float, float, int, int]]]) -> None:
    chord_stem = stems["chords"]
    for section_name, start, bars, _ in SECTIONS:
        for bar in range(start, start + bars):
            name, notes, _ = CHORDS[bar % 4]
            in_drop = section_name.startswith("Drop")
            in_build = section_name.startswith("Build")
            in_break = section_name in {"Break", "Outro"}
            bright = 1.00 if in_drop else 0.70 if in_build else 0.44 if in_break else 0.52
            gain = 0.305 if in_drop else 0.20 if in_build else 0.12
            events = [(0.0, 0.92), (1.0, 0.68), (2.0, 0.92), (3.0, 0.68)] if in_drop else [(0.0, 3.75)]
            for beat, dur in events:
                for idx, note in enumerate(notes):
                    schedule_note(
                        chord_stem,
                        midi["chords"],
                        dsp.synth_supersaw,
                        bar,
                        beat,
                        dur,
                        note + (12 if in_drop else 0),
                        84 if in_drop else 62,
                        gain * (0.92 - idx * 0.05),
                        pan=(-0.34 + idx * 0.22),
                        audio_extra_beats=0.25,
                        bright=bright,
                        stab=in_drop,
                    )
            if section_name == "Intro" and bar < 4:
                chord_stem[int(beat_to_seconds(bar_beat(bar)) * SR): int(beat_to_seconds(bar_beat(bar + 1)) * SR)] *= 0.45 + 0.1 * bar
    sidechain(chord_stem, 0.44)
    dsp.add_delay(chord_stem, delay_beats=0.375, feedback=0.34, wet=0.075, repeats=3)
    widen(chord_stem, delay_ms=14.0, amount=0.36)


def render_bass(stems: dict[str, np.ndarray], midi: dict[str, list[tuple[float, float, int, int]]]) -> None:
    for section_name, start, bars, _ in SECTIONS:
        for bar in range(start, start + bars):
            _, _, root = CHORDS[bar % 4]
            if section_name in {"Intro", "Break", "Outro"}:
                if bar % 2 == 0:
                    schedule_note(stems["sub"], midi["sub"], dsp.synth_bass, bar, 0.0, 3.35, root - 12, 70, 0.120, tone=0.12)
                continue
            if section_name == "Verse":
                pattern = [(0.0, 0.70, root - 12), (2.0, 0.70, root - 12)]
                mid_gain = 0.110
            elif section_name.startswith("Build"):
                pattern = [(0.0, 0.80, root - 12), (2.0, 0.75, root - 12), (3.35, 0.28, root)]
                mid_gain = 0.135
            else:
                pattern = [(0.0, 0.80, root - 12), (1.0, 0.42, root - 12), (2.0, 0.80, root - 12), (3.0, 0.42, root - 12)]
                mid_gain = 0.185 if section_name == "Drop 1" else 0.210
            for beat, dur, note in pattern:
                schedule_note(stems["sub"], midi["sub"], dsp.synth_bass, bar, beat, dur, note, 92, 0.178, tone=0.06)
                schedule_note(stems["bass"], midi["bass"], dsp.synth_bass, bar, beat, dur, note + 12, 86, mid_gain, tone=0.72)
    sidechain(stems["sub"], 0.60)
    sidechain(stems["bass"], 0.50)


def render_leads(stems: dict[str, np.ndarray], midi: dict[str, list[tuple[float, float, int, int]]]) -> None:
    for bar in range(0, 8):
        motif = INTRO_MOTIF if bar % 4 in {0, 2} else INTRO_MOTIF[:3]
        for beat, dur, note, vel in motif:
            schedule_note(stems["lead"], midi["lead"], mello_lead, bar, beat, dur, note, vel, 0.078, pan=0.04, soft=True, audio_extra_beats=0.12)
    for bar in range(8, 16):
        if bar % 4 in {1, 3}:
            continue
        motif = INTRO_MOTIF[:4] if bar % 4 == 0 else INTRO_MOTIF[2:]
        for beat, dur, note, vel in motif:
            schedule_note(stems["lead"], midi["lead"], mello_lead, bar, beat, dur, note, vel, 0.086, pan=0.06, soft=True, audio_extra_beats=0.10)
    for bar in range(16, 24):
        lift = (bar - 16) / 8
        octave = 12 if bar >= 20 else 0
        for beat, dur, note, vel in INTRO_MOTIF:
            schedule_note(stems["lead"], midi["lead"], mello_lead, bar, beat, dur * 0.78, note + octave, int(vel + 18 * lift), 0.105 + lift * 0.060, pan=0.06, soft=bar < 20)
    for section_name, start, end, double in [("Drop 1", 24, 40, False), ("Drop 2", 56, 72, True)]:
        for bar in range(start, end):
            motif = DROP_PHRASE[(bar - start) % 4]
            for beat, dur, note, vel in motif:
                schedule_note(stems["lead"], midi["lead"], mello_lead, bar, beat, dur, note, vel, 0.290 if not double else 0.305, pan=0.01, soft=False, audio_extra_beats=0.05)
                if double:
                    schedule_note(stems["lead-double"], midi["lead_double"], mello_double, bar, beat, dur, note + 12, max(64, vel - 12), 0.185, pan=-0.20 if beat < 2 else 0.22, audio_extra_beats=0.05)
            if double and bar % 4 == 3:
                for beat, dur, note, vel in SPARKLE_MOTIF:
                    schedule_note(stems["lead-double"], midi["lead_double"], dsp.synth_pluck, bar, beat, dur, note + 12, vel, 0.050, pan=0.34)
    for bar in range(40, 48):
        for beat, dur, note, vel in INTRO_MOTIF[::2]:
            schedule_note(stems["lead"], midi["lead"], mello_lead, bar, beat, dur * 1.2, note, vel - 8, 0.074, pan=-0.08, soft=True, audio_extra_beats=0.35)
    for bar in range(72, 80):
        fade = max(0.1, (80 - bar) / 8)
        for beat, dur, note, vel in INTRO_MOTIF[:2]:
            schedule_note(stems["lead"], midi["lead"], mello_lead, bar, beat, dur, note, vel, 0.074 * fade, pan=0.0, soft=True, audio_extra_beats=0.45)
    dsp.add_delay(stems["lead"], delay_beats=0.50, feedback=0.34, wet=0.145, repeats=4)
    dsp.add_delay(stems["lead-double"], delay_beats=0.375, feedback=0.30, wet=0.115, repeats=3)
    widen(stems["lead"], delay_ms=9.0, amount=0.18)
    widen(stems["lead-double"], delay_ms=18.0, amount=0.38)


def render_plucks_and_chops(stems: dict[str, np.ndarray], midi: dict[str, list[tuple[float, float, int, int]]]) -> None:
    for bar in range(8, 16):
        _, notes, root = CHORDS[bar % 4]
        for beat, note in [(0.0, root + 12), (2.0, root + 12), (3.0, notes[-1] + 12)]:
            synth = dsp.synth_muted_guitar if beat < 3.0 else dsp.synth_pluck
            gain = 0.050 if beat < 3.0 else 0.060
            schedule_note(stems["plucks"], midi["plucks"], synth, bar, beat, 0.28, note, 52, gain, pan=-0.12 if beat < 2 else 0.16)
    echo_bars = list(range(40, 48, 2)) + [35, 39, 63, 67, 71]
    for idx, bar in enumerate(echo_bars):
        phrase = DROP_PHRASE[idx % len(DROP_PHRASE)]
        for beat, dur, note, vel in phrase[:2]:
            octave = 12 if bar >= 56 else 0
            schedule_note(stems["vocals"], midi["vocals"], hook_echo_tone, bar, beat, dur * 1.15, note + octave, max(48, vel - 40), 0.048, pan=-0.30 if idx % 2 else 0.30, audio_extra_beats=0.25)
    dsp.add_delay(stems["vocals"], delay_beats=0.50, feedback=0.42, wet=0.20, repeats=4)
    widen(stems["plucks"], delay_ms=11.0, amount=0.16)
    widen(stems["vocals"], delay_ms=24.0, amount=0.34)


def render_drums(stems: dict[str, np.ndarray], midi: dict[str, list[tuple[float, float, int, int]]]) -> None:
    for bar in range(8, 16):
        for beat in (0.0, 2.0):
            add_audio(stems["drums"], bar, dsp.kick(), 0.70, beat=beat)
            midi["drums"].append((bar_beat(bar, beat), 0.18, 36, 92))
        for beat in (1.0, 3.0):
            add_audio(stems["drums"], bar, dsp.snare(), 0.42, beat=beat)
            add_audio(stems["clap-stack"], bar, dsp.snare(clap=True), 0.34, pan=0.14, beat=beat)
            midi["drums"].append((bar_beat(bar, beat), 0.12, 38, 76))
            midi["clap"].append((bar_beat(bar, beat), 0.12, 39, 74))
        for step in range(8):
            beat = step * 0.5
            add_audio(stems["hat-ride"], bar, dsp.hat(open_hat=step % 4 == 3), 0.28 if step % 2 else 0.22, pan=0.18, beat=beat)
            midi["hats"].append((bar_beat(bar, beat), 0.06, 42, 46 + (step % 2) * 8))
    for start in (16, 48):
        for bar in range(start, start + 8):
            lift = (bar - start + 1) / 8
            if bar < start + 7:
                add_audio(stems["drums"], bar, dsp.kick(), 0.55, beat=0.0)
                midi["drums"].append((bar_beat(bar), 0.15, 36, 78))
            roll_steps = 4 + int(lift * 12)
            for step in range(roll_steps):
                beat = step * (4.0 / roll_steps)
                add_audio(stems["drums"], bar, dsp.snare(), 0.18 + 0.22 * lift, beat=beat)
                add_audio(stems["clap-stack"], bar, dsp.snare(clap=True), 0.13 + 0.18 * lift, pan=(-0.25 if step % 2 else 0.25), beat=beat)
                midi["drums"].append((bar_beat(bar, beat), 0.08, 38, int(52 + 48 * lift)))
            hat_step = 0.25 if start == 48 else 0.5
            for step in range(int(4 / hat_step)):
                beat = step * hat_step
                add_audio(stems["hat-ride"], bar, dsp.hat(), 0.16 + lift * 0.13, pan=0.20, beat=beat)
                midi["hats"].append((bar_beat(bar, beat), 0.05, 42, int(48 + lift * 32)))
    for section_start, section_end, second in [(24, 40, False), (56, 72, True)]:
        for bar in range(section_start, section_end):
            for beat in (0.0, 2.0):
                add_audio(stems["drums"], bar, dsp.kick(), 0.88 if not second else 0.94, beat=beat)
                midi["drums"].append((bar_beat(bar, beat), 0.18, 36, 112))
            if bar % 4 == 3:
                add_audio(stems["drums"], bar, dsp.kick(), 0.52, beat=3.35)
                midi["drums"].append((bar_beat(bar, 3.35), 0.12, 36, 76))
            for beat in (1.0, 3.0):
                add_audio(stems["drums"], bar, dsp.snare(), 0.48, beat=beat)
                add_audio(stems["clap-stack"], bar, dsp.snare(clap=True), 0.46 if not second else 0.52, pan=0.18, beat=beat)
                midi["drums"].append((bar_beat(bar, beat), 0.14, 38, 108))
                midi["clap"].append((bar_beat(bar, beat), 0.14, 39, 100))
            for step in range(16 if second else 8):
                beat = step * (0.25 if second else 0.5)
                add_audio(stems["hat-ride"], bar, dsp.hat(open_hat=(step % 8 == 7)), 0.22 if not second else 0.28, pan=0.22, beat=beat)
                midi["hats"].append((bar_beat(bar, beat), 0.05, 42, 58 if second else 50))
            if second:
                add_audio(stems["hat-ride"], bar, dsp.ride(), 0.30, pan=-0.24, beat=0.0)
                midi["hats"].append((bar_beat(bar), 0.3, 51, 82))
            if (bar - section_start) % 8 == 0:
                add_audio(stems["hat-ride"], bar, dsp.crash(), 0.42 if second else 0.34, beat=0.0)
                midi["hats"].append((bar_beat(bar), 0.7, 49, 92))


def render_fx(stems: dict[str, np.ndarray]) -> None:
    for bar in range(0, 80, 4):
        gain = 0.018 if bar < 24 else 0.026 if bar < 56 else 0.034
        add_audio(stems["fx"], bar, airy_noise(4 * 4 * BEAT, high=False), gain, pan=-0.12 + (bar % 8) * 0.03)
    for start in (16, 48):
        add_audio(stems["fx"], start, dsp.riser(8 * 4 * BEAT, start_freq=130.0, end_freq=2300.0 if start == 48 else 1650.0), 0.58, pan=0.0)
        add_audio(stems["fx"], start + 7, airy_noise(3.5 * BEAT), 0.18, pan=0.30)
        add_audio(stems["fx"], start + 7, dsp.downlifter(1.2), 0.22, beat=3.0)
    for bar in (24, 40, 56, 72):
        add_audio(stems["fx"], bar, dsp.impact(), 0.70 if bar in (24, 56) else 0.46)
        add_audio(stems["fx"], bar, dsp.downlifter(1.7), 0.28, pan=-0.15)
    for bar in (23, 55):
        reverse = dsp.riser(1.0, start_freq=520.0, end_freq=1100.0)[::-1].copy()
        add_audio(stems["fx"], bar, reverse, 0.34, beat=3.0)
    for bar in range(56, 72, 8):
        add_audio(stems["fx"], bar + 3, dsp.chain_noise(0.55), 0.075, pan=0.30, beat=2.0)
    add_audio(stems["fx"], 72, dsp.downlifter(5.0), 0.35)
    widen(stems["fx"], delay_ms=26.0, amount=0.38)


def build_stems() -> tuple[dict[str, np.ndarray], dict[str, list[tuple[float, float, int, int]]]]:
    stems = {track_id: lane() for track_id in ASSET_FILES}
    midi = {key: [] for key in ["chords", "bass", "sub", "lead", "lead_double", "plucks", "vocals", "drums", "clap", "hats"]}
    render_chords(stems, midi)
    render_bass(stems, midi)
    render_leads(stems, midi)
    render_plucks_and_chops(stems, midi)
    render_drums(stems, midi)
    render_fx(stems)
    sidechain(stems["vocals"], 0.18)
    widen(stems["hat-ride"], delay_ms=9.0, amount=0.20)
    return stems, midi


def track(id_: str, name: str, instrument: str, gain: float, pan: float, clips: list[dict[str, object]], effects: list[dict[str, object]]) -> dict[str, object]:
    return {
        "id": id_,
        "name": name,
        "kind": "audio",
        "instrument": instrument,
        "gain": gain,
        "pan": pan,
        "steps": [0, 4, 8, 12],
        "effects": effects,
        "clips": clips,
        "color": TRACK_COLORS[id_],
        "file": f"/api/audio/{ASSET_FILES[id_]}",
    }


def clip(id_: str, name: str, start: float, bars: float, lane_id: str, type_: str = "audio") -> dict[str, object]:
    return {"id": id_, "name": name, "startBar": start, "bars": bars, "lane": lane_id, "color": TRACK_COLORS[lane_id], "type": type_}


def make_effect(id_: str, name: str, amount: float, active: bool = True) -> dict[str, object]:
    return {"id": id_, "name": name, "active": active, "amount": amount}


def build_tracks() -> list[dict[str, object]]:
    return [
        track("drums", "Drums", "Future Trap Kit", 0.72, 0.0, [
            clip("drums-verse", "Verse kick/snare pocket", 8, 8, "drums", "pattern"),
            clip("drums-build-1", "Build 1 roll", 16, 8, "drums", "pattern"),
            clip("drums-drop-1", "Drop 1 drums", 24, 16, "drums", "pattern"),
            clip("drums-build-2", "Build 2 roll", 48, 8, "drums", "pattern"),
            clip("drums-drop-2", "Drop 2 drums", 56, 16, "drums", "pattern"),
        ], [make_effect("eq", "EQ Eight", 0.56), make_effect("bus-comp", "Bus Comp", 0.60), make_effect("clip", "Soft Clip", 0.36)]),
        track("clap-stack", "Clap Stack", "Wide Clap Layer", 0.62, 0.08, [
            clip("clap-verse", "Verse clap", 8, 8, "clap-stack", "pattern"),
            clip("clap-build-1", "Build clap roll", 16, 8, "clap-stack", "pattern"),
            clip("clap-drop-1", "Drop clap stack", 24, 16, "clap-stack", "pattern"),
            clip("clap-build-2", "Build 2 clap roll", 48, 8, "clap-stack", "pattern"),
            clip("clap-drop-2", "Drop 2 clap stack", 56, 16, "clap-stack", "pattern"),
        ], [make_effect("verb", "Short Plate", 0.38), make_effect("width", "Stereo Spread", 0.46)]),
        track("hat-ride", "Hat/Ride", "Trap Hats + Ride", 0.55, 0.18, [
            clip("hat-verse", "Verse hats", 8, 8, "hat-ride", "pattern"),
            clip("hat-build-1", "Build hats", 16, 8, "hat-ride", "pattern"),
            clip("hat-drop-1", "Drop hats", 24, 16, "hat-ride", "pattern"),
            clip("hat-build-2", "Double-time build hats", 48, 8, "hat-ride", "pattern"),
            clip("hat-drop-2", "Drop 2 ride/crash lift", 56, 16, "hat-ride", "pattern"),
        ], [make_effect("air", "Bright Air EQ", 0.48), make_effect("human", "Velocity Humanize", 0.44)]),
        track("sub", "Sub", "Mono Triangle Sub", 0.92, 0.0, [
            clip("sub-verse", "Verse sub anchors", 8, 8, "sub", "pattern"),
            clip("sub-drop-1", "Drop 1 sub", 24, 16, "sub", "pattern"),
            clip("sub-drop-2", "Drop 2 sub", 56, 16, "sub", "pattern"),
        ], [make_effect("mono", "Mono Utility", 0.90), make_effect("duck", "Kick Duck", 0.70)]),
        track("bass", "Mid Bass", "Saturated Mid Bass", 0.78, 0.0, [
            clip("bass-verse", "Verse bass pulses", 8, 8, "bass", "pattern"),
            clip("bass-build-1", "Build bass lift", 16, 8, "bass", "pattern"),
            clip("bass-drop-1", "Drop 1 mid bass", 24, 16, "bass", "pattern"),
            clip("bass-build-2", "Build 2 bass lift", 48, 8, "bass", "pattern"),
            clip("bass-drop-2", "Drop 2 mid bass", 56, 16, "bass", "pattern"),
        ], [make_effect("sat", "Saturator", 0.48), make_effect("duck", "Sidechain", 0.66)]),
        track("chords", "Supersaw Chords", "Wide Pumped Supersaw", 0.98, -0.04, [
            clip("chords-intro", "Filtered D major bed", 0, 8, "chords", "pattern"),
            clip("chords-verse", "Verse chord bed", 8, 8, "chords", "pattern"),
            clip("chords-build-1", "Build 1 opening chords", 16, 8, "chords", "pattern"),
            clip("chords-drop-1", "Drop 1 pumped stabs", 24, 16, "chords", "pattern"),
            clip("chords-break", "Break filtered chords", 40, 8, "chords", "pattern"),
            clip("chords-build-2", "Build 2 opening chords", 48, 8, "chords", "pattern"),
            clip("chords-drop-2", "Drop 2 wider stabs", 56, 16, "chords", "pattern"),
            clip("chords-outro", "Outro chord tail", 72, 8, "chords", "pattern"),
        ], [make_effect("eq", "Low Cut EQ", 0.70), make_effect("verb", "Wide Plate", 0.42), make_effect("duck", "Sidechain", 0.72)]),
        track("lead", "Hook Lead", "Clean Square/Saw Hook", 0.98, 0.02, [
            clip("lead-intro", "Intro hook fragments", 0, 8, "lead", "pattern"),
            clip("lead-verse", "Verse hook fragments", 8, 8, "lead", "pattern"),
            clip("lead-build-1", "Build 1 hook tease", 16, 8, "lead", "pattern"),
            clip("lead-drop-1", "Drop 1 hook", 24, 16, "lead", "pattern"),
            clip("lead-break", "Break hook echo", 40, 8, "lead", "pattern"),
            clip("lead-build-2", "Build 2 hook tease", 48, 8, "lead", "pattern"),
            clip("lead-drop-2", "Drop 2 hook", 56, 16, "lead", "pattern"),
            clip("lead-outro", "Outro hook echo", 72, 8, "lead", "pattern"),
        ], [make_effect("air", "Air EQ", 0.48), make_effect("delay", "Stereo Delay", 0.44), make_effect("plate", "Plate Reverb", 0.34)]),
        track("lead-double", "Lead Double", "Octave Detune Double", 0.58, -0.08, [
            clip("double-drop-2", "Drop 2 octave double", 56, 16, "lead-double", "pattern"),
        ], [make_effect("width", "Stereo Width", 0.60), make_effect("duck", "Sidechain", 0.32)]),
        track("plucks", "Verse Texture", "Muted Verse Plucks", 0.34, -0.10, [
            clip("plucks-verse", "Sparse verse texture", 8, 8, "plucks", "pattern"),
        ], [make_effect("delay", "Ping Delay", 0.28), make_effect("lpf", "Muted Lowpass", 0.54)]),
        track("vocals", "Hook Echo", "Distant Hook Echo", 0.30, 0.0, [
            clip("echo-break", "Break hook echo", 40, 8, "vocals", "pattern"),
            clip("echo-drop-1", "Drop 1 tail echo", 24, 16, "vocals", "pattern"),
            clip("echo-drop-2", "Drop 2 tail echo", 56, 16, "vocals", "pattern"),
        ], [make_effect("delay", "Stereo Delay", 0.46), make_effect("verb", "Bright Reverb", 0.42)]),
        track("fx", "FX", "Risers / Impacts / Air", 0.66, 0.0, [
            clip("fx-intro-air", "Intro air bed", 0, 8, "fx"),
            clip("fx-build-1", "Build 1 riser", 16, 8, "fx"),
            clip("fx-drop-1", "Drop 1 impact", 24, 1, "fx"),
            clip("fx-break", "Break downlifter", 40, 8, "fx"),
            clip("fx-build-2", "Build 2 riser and fake stop", 48, 8, "fx"),
            clip("fx-drop-2", "Drop 2 impact and sparkle", 56, 16, "fx"),
            clip("fx-outro", "Outro downlifter", 72, 8, "fx"),
        ], [make_effect("hall", "Long Hall", 0.48), make_effect("width", "Stereo Spread", 0.50), make_effect("duck", "Kick Sidechain", 0.34)]),
        {
            "id": "filter-auto",
            "name": "Filter Auto",
            "kind": "automation",
            "instrument": "Automation Lane",
            "gain": 0.0,
            "pan": 0.0,
            "steps": [],
            "effects": [make_effect("cutoff", "Cutoff Macro", 0.92)],
            "clips": [
                clip("auto-intro", "Intro chord filter open", 0, 8, "filter-auto", "automation"),
                clip("auto-build-1", "Build 1 lead filter rise", 16, 8, "filter-auto", "automation"),
                clip("auto-build-2", "Build 2 width/filter rise", 48, 8, "filter-auto", "automation"),
                clip("auto-drop-2", "Drop 2 width push", 56, 16, "filter-auto", "automation"),
            ],
            "color": TRACK_COLORS["filter-auto"],
            "file": None,
        },
    ]


def build_recipe() -> list[dict[str, object]]:
    items = [
        ("foundation", "Foundation", "Original Alone-lane arrangement", "Eight-section 142 BPM D-major future-bass structure with no copied topline.", ["lead", "chords", "drums", "bass", "fx"]),
        ("intro", "Intro", "Filtered hook DNA", "The intro states the D-major emotional identity with filtered chords and small lead fragments.", ["lead", "chords", "fx"]),
        ("verse", "Verse", "Sparse lonely pocket", "Verse keeps the hook intimate with plucks, simple kick/snare, and enough space before the lift.", ["plucks", "lead", "drums", "sub"]),
        ("build-1", "Build 1", "First filter and roll lift", "Build 1 opens the lead filter, raises clap/snare energy, and uses risers to stage drop one.", ["filter-auto", "drums", "clap-stack", "fx"]),
        ("hook", "Hook", "Simple square/saw lead identity", "Intro and drop use the same hook DNA, but the drop contour is original and filled in.", ["lead", "lead-double"]),
        ("chords", "Harmony", "D-A-Bm-G emotional harmonic lane", "D-major chord bed is bright, simple, and sidechained for festival motion.", ["chords"]),
        ("drop-1", "Drop 1", "Open pumped future-bass drop", "Drop 1 keeps the rhythm uncluttered so the hook reads immediately.", ["drums", "bass", "sub", "chords", "lead"]),
        ("break", "Break", "Filtered emotional reset", "Break strips drums away and leaves filtered chords plus quiet hook echo.", ["chords", "lead", "vocals", "fx"]),
        ("build-2", "Build 2", "Higher-tension second lift", "Build 2 uses double-time hats, stronger riser, and wider macro movement before the second drop.", ["filter-auto", "hat-ride", "clap-stack", "fx"]),
        ("drop-2", "Drop 2", "Wider and brighter second drop", "Drop 2 adds octave lead double, ride/crash lift, and small clean sparkle.", ["lead-double", "hat-ride", "vocals", "fx"]),
        ("outro", "Outro", "Hook echo and downlifter", "Outro removes the drums and resolves into chord tail, downlifter, and soft hook echo.", ["lead", "chords", "fx"]),
        ("builds", "Builds", "Filter, riser, and clap-roll tension", "Both builds stage the drop through visible automation, snare/clap rolls, risers, and fake-stop contrast.", ["filter-auto", "drums", "clap-stack", "fx"]),
        ("automation", "Automation", "Visible filter and width macros", "Automation lanes expose chord filter, lead filter, and width movement so the app mirrors the audio lift.", ["filter-auto", "chords", "lead", "fx"]),
        ("low-end", "Mix", "Kick/sub separation", "Sub and mid bass are ducked around the kick, with low-end ownership kept out of lead and chord lanes.", ["drums", "sub", "bass"]),
        ("air", "Mix", "Bright but controlled top end", "Lead, claps, hats, and supersaws carry air while delays and low cuts keep the mix clean.", ["lead", "chords", "hat-ride", "clap-stack"]),
    ]
    return [
        {"id": id_, "section": section, "label": label, "detail": detail, "status": "implemented", "trackIds": track_ids}
        for id_, section, label, detail, track_ids in items
    ]


def build_project() -> dict[str, object]:
    tracks = build_tracks()
    controls = {
        str(track["id"]): {
            "gain": track.get("gain", 0.8),
            "pan": track.get("pan", 0.0),
            "mute": False,
            "solo": False,
            "arm": False,
            "sendA": 0.18 if track["id"] in {"lead", "vocals", "plucks"} else 0.10,
            "sendB": 0.12 if track["id"] in {"chords", "fx"} else 0.06,
        }
        for track in tracks
    }
    automation_lanes = [
        {
            "id": "auto-chords-filter",
            "trackId": "chords",
            "parameter": "filter",
            "label": "Chords Filter",
            "color": TRACK_COLORS["chords"],
            "enabled": True,
            "curve": "ease-in",
            "points": [{"bar": 0, "value": 0.18}, {"bar": 8, "value": 0.55}, {"bar": 24, "value": 0.95}, {"bar": 72, "value": 0.36}],
        },
        {
            "id": "auto-lead-filter",
            "trackId": "lead",
            "parameter": "filter",
            "label": "Lead Filter Rise",
            "color": TRACK_COLORS["lead"],
            "enabled": True,
            "curve": "ease-in",
            "points": [{"bar": 16, "value": 0.24}, {"bar": 24, "value": 0.95}, {"bar": 48, "value": 0.20}, {"bar": 56, "value": 1.0}],
        },
        {
            "id": "auto-master-width",
            "trackId": "fx",
            "parameter": "width",
            "label": "Build Width Macro",
            "color": TRACK_COLORS["fx"],
            "enabled": True,
            "curve": "linear",
            "points": [{"bar": 48, "value": 0.45}, {"bar": 56, "value": 0.85}, {"bar": 72, "value": 0.58}],
        },
    ]
    assets = [{"trackId": track_id, "file": f"/api/audio/{file_name}"} for track_id, file_name in ASSET_FILES.items()]
    return {
        "format": "neon-studio-project",
        "formatVersion": 1,
        "portable": True,
        "assetMode": "external",
        "id": PROJECT_ID,
        "name": PROJECT_NAME,
        "createdAt": "2026-06-12T08:19:41Z",
        "updatedAt": now_iso(),
        "projectFile": None,
        "assets": assets,
        "description": "Original bright future-bass project in the Marshmello Alone production lane; no copied lyrics, samples, or topline.",
        "keyCenter": "D Major",
        "snapshot": {
            "version": 3,
            "bpm": BPM,
            "swing": 14,
            "snap": "1/16",
            "loopEnabled": True,
            "loopStartBar": 56,
            "loopEndBar": 72,
            "tracks": tracks,
            "controls": controls,
            "automationLanes": automation_lanes,
            "notes": [
                # trackId is required from schema v4 on; without it the app has
                # to guess which track a note belongs to.
                {"id": f"hook-{i}", "beat": beat, "duration": dur, "note": note, "velocity": vel / 127, "color": TRACK_COLORS["lead"], "trackId": "lead"}
                for i, (beat, dur, note, vel) in enumerate(DROP_MOTIF)
            ],
            "selectedTrackId": "lead",
            "selectedClipId": "lead-drop-2",
            "activeView": "playlist",
            "patternIndex": 1,
            "arrangementMode": "song",
            "recipe": build_recipe(),
        },
    }


def write_project(project: dict[str, object]) -> None:
    for path in PROJECT_PATHS:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(project, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_outputs(stems: dict[str, np.ndarray], midi: dict[str, list[tuple[float, float, int, int]]]) -> None:
    EXPORTS.mkdir(exist_ok=True)
    MIDI_DIR.mkdir(exist_ok=True)
    gains = {
        "drums": 0.58,
        "clap-stack": 0.42,
        "hat-ride": 0.66,
        "sub": 1.08,
        "bass": 0.92,
        "chords": 1.24,
        "lead": 1.16,
        "lead-double": 0.96,
        "plucks": 0.42,
        "vocals": 0.32,
        "fx": 0.60,
    }
    mix = lane()
    for track_id, audio in stems.items():
        rendered = dsp.soft_clip(audio * gains[track_id], drive=1.12) * 0.92
        dsp.write_wav(EXPORTS / ASSET_FILES[track_id], rendered)
        mix += rendered
    mix = dsp.soft_clip(mix * 0.84, drive=1.22) * 0.94
    dsp.write_wav(EXPORTS / "neon_alone_full_mix.wav", mix)
    arrangement_tracks = [
        ("Chords", 0, 81, midi["chords"]),
        ("Bass", 1, 38, midi["bass"]),
        ("Sub", 2, 38, midi["sub"]),
        ("Lead", 3, 80, midi["lead"]),
        ("Lead Double", 4, 82, midi["lead_double"]),
        ("Plucks", 5, 24, midi["plucks"]),
        ("Hook Echo", 6, 89, midi["vocals"]),
        ("Drums", 9, None, midi["drums"]),
        ("Clap Stack", 9, None, midi["clap"]),
        ("Hat Ride", 9, None, midi["hats"]),
    ]
    dsp.write_midi(MIDI_DIR / "neon_alone_arrangement.mid", arrangement_tracks)
    for filename, track_data in [
        ("neon_alone_chords.mid", [arrangement_tracks[0]]),
        ("neon_alone_bass.mid", [arrangement_tracks[1], arrangement_tracks[2]]),
        ("neon_alone_lead.mid", [arrangement_tracks[3], arrangement_tracks[4]]),
        ("neon_alone_drums.mid", [arrangement_tracks[7], arrangement_tracks[8], arrangement_tracks[9]]),
    ]:
        dsp.write_midi(MIDI_DIR / filename, track_data)


def main() -> int:
    print("Rendering Neon Alone: 142 BPM, D major, original Alone-lane future bass.")
    stems, midi = build_stems()
    write_outputs(stems, midi)
    project = build_project()
    write_project(project)
    print("Generated assets:")
    print("- exports/neon_alone_full_mix.wav")
    print("- exports/neon_alone_*.wav stems")
    print("- midi/neon_alone_arrangement.mid")
    print("- data/projects/neon-alone.neon.json")
    print("- factory/projects/neon-alone.neon.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
