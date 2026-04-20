#!/usr/bin/env python3
"""
Render an original future-bass/festival EDM track package.

This intentionally does not copy the melody, recording, stems, or session for any
commercial song. It makes a compatible "in the lane" production sketch with
WAV stems and MIDI parts that can be imported into a DAW.
"""

from __future__ import annotations

import math
import json
import struct
import wave
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


SR = 44_100
BPM = 104
BEAT = 60.0 / BPM
PPQ = 480
TOTAL_BARS = 72
TAIL_SECONDS = 4.0
TOTAL_SECONDS = TOTAL_BARS * 4 * BEAT + TAIL_SECONDS
N_SAMPLES = int(TOTAL_SECONDS * SR)
ROOT = Path(__file__).resolve().parent
EXPORTS = ROOT / "exports"
MIDI_DIR = ROOT / "midi"

rng = np.random.default_rng(1207)


def beat_to_seconds(beat: float) -> float:
    return beat * BEAT


def bar_beat(bar: int, beat: float = 0.0) -> float:
    return bar * 4.0 + beat


def note_to_freq(midi_note: int) -> float:
    return 440.0 * (2.0 ** ((midi_note - 69) / 12.0))


def stereo_buffer() -> np.ndarray:
    return np.zeros((N_SAMPLES, 2), dtype=np.float32)


def equal_power_pan(pan: float) -> tuple[float, float]:
    pan = float(np.clip(pan, -1.0, 1.0))
    angle = (pan + 1.0) * math.pi / 4.0
    return math.cos(angle), math.sin(angle)


def add_mono(
    target: np.ndarray,
    start_seconds: float,
    audio: np.ndarray,
    gain: float = 1.0,
    pan: float = 0.0,
) -> None:
    start = int(round(start_seconds * SR))
    if start >= len(target):
        return
    end = min(start + len(audio), len(target))
    if end <= start:
        return
    audio = audio[: end - start].astype(np.float32, copy=False) * gain
    left, right = equal_power_pan(pan)
    target[start:end, 0] += audio * left
    target[start:end, 1] += audio * right


def adsr(
    n: int,
    attack: float = 0.005,
    decay: float = 0.06,
    sustain: float = 0.65,
    release: float = 0.08,
) -> np.ndarray:
    a = max(1, int(attack * SR))
    d = max(1, int(decay * SR))
    r = max(1, int(release * SR))
    total_fixed = a + d + r
    if total_fixed > n:
        scale = n / total_fixed
        a = max(1, int(a * scale))
        d = max(1, int(d * scale))
        r = max(1, n - a - d)
    s_len = max(0, n - a - d - r)
    env = np.concatenate(
        [
            np.linspace(0.0, 1.0, a, endpoint=False),
            np.linspace(1.0, sustain, d, endpoint=False),
            np.full(s_len, sustain),
            np.linspace(sustain, 0.0, r, endpoint=True),
        ]
    )
    if len(env) < n:
        env = np.pad(env, (0, n - len(env)))
    return env[:n].astype(np.float32)


def one_pole_lowpass(x: np.ndarray, cutoff_hz: float) -> np.ndarray:
    if cutoff_hz <= 0:
        return x
    rc = 1.0 / (2.0 * math.pi * cutoff_hz)
    dt = 1.0 / SR
    alpha = dt / (rc + dt)
    y = np.empty_like(x, dtype=np.float32)
    prev = 0.0
    for i, sample in enumerate(x):
        prev = prev + alpha * (float(sample) - prev)
        y[i] = prev
    return y


def highpass_noise(n: int) -> np.ndarray:
    x = rng.standard_normal(n).astype(np.float32)
    y = np.empty_like(x)
    y[0] = x[0]
    y[1:] = x[1:] - 0.92 * x[:-1]
    return y


def saw(freq: float, dur: float, phase: float = 0.0) -> np.ndarray:
    n = max(1, int(dur * SR))
    t = np.arange(n, dtype=np.float32) / SR
    p = (freq * t + phase) % 1.0
    return (2.0 * p - 1.0).astype(np.float32)


def square_from_phase(phase: np.ndarray) -> np.ndarray:
    return np.where((phase % 1.0) < 0.5, 1.0, -1.0).astype(np.float32)


def synth_supersaw(freq: float, dur: float, bright: float = 1.0, stab: bool = False) -> np.ndarray:
    n = max(1, int(dur * SR))
    detunes = [-13.0, -7.0, -3.0, 0.0, 4.0, 8.0, 14.0]
    x = np.zeros(n, dtype=np.float32)
    for i, cents in enumerate(detunes):
        f = freq * (2.0 ** (cents / 1200.0))
        x += saw(f, dur, phase=(i * 0.117) % 1.0)
    x /= len(detunes)
    t = np.arange(n, dtype=np.float32) / SR
    x += 0.18 * np.sin(2.0 * np.pi * freq * 0.5 * t).astype(np.float32)
    cutoff = 1900.0 + 3800.0 * bright
    x = one_pole_lowpass(x, cutoff)
    if stab:
        env = adsr(n, attack=0.008, decay=0.11, sustain=0.42, release=0.18)
    else:
        env = adsr(n, attack=0.18, decay=0.7, sustain=0.78, release=0.9)
    return x * env


def synth_bass(freq: float, dur: float) -> np.ndarray:
    n = max(1, int(dur * SR))
    t = np.arange(n, dtype=np.float32) / SR
    phase = np.cumsum(np.full(n, freq, dtype=np.float32)) / SR
    sub = np.sin(2.0 * np.pi * phase).astype(np.float32)
    grit = square_from_phase(phase * 2.0) * 0.18
    click = np.sin(2.0 * np.pi * (freq * 5.0) * t).astype(np.float32) * np.exp(-t * 30.0)
    env = adsr(n, attack=0.004, decay=0.05, sustain=0.78, release=0.08)
    return (sub * 0.9 + grit + click * 0.08) * env


def synth_lead(freq: float, dur: float, soft: bool = False) -> np.ndarray:
    n = max(1, int(dur * SR))
    t = np.arange(n, dtype=np.float32) / SR
    vibrato = 1.0 + 0.004 * np.sin(2.0 * np.pi * 5.4 * t)
    phase = np.cumsum((freq * vibrato).astype(np.float32)) / SR
    sq = square_from_phase(phase)
    tri = (2.0 * np.abs(2.0 * (phase % 1.0) - 1.0) - 1.0).astype(np.float32)
    sine = np.sin(2.0 * np.pi * phase).astype(np.float32)
    x = 0.52 * sq + 0.33 * tri + 0.16 * sine
    x = one_pole_lowpass(x, 2600.0 if soft else 4200.0)
    env = adsr(n, attack=0.012, decay=0.08, sustain=0.58 if soft else 0.72, release=0.12)
    return x * env


def synth_lead_double(freq: float, dur: float) -> np.ndarray:
    n = max(1, int(dur * SR))
    detunes = [-10.0, -4.0, 5.0, 12.0]
    x = np.zeros(n, dtype=np.float32)
    for idx, cents in enumerate(detunes):
        x += saw(freq * (2.0 ** (cents / 1200.0)), dur, phase=0.19 * idx)
    x /= len(detunes)
    t = np.arange(n, dtype=np.float32) / SR
    shimmer = np.sin(2.0 * np.pi * freq * 2.0 * t).astype(np.float32) * 0.16
    x = one_pole_lowpass((x + shimmer).astype(np.float32), 5200.0)
    env = adsr(n, attack=0.018, decay=0.08, sustain=0.62, release=0.18)
    return x * env


def synth_pluck(freq: float, dur: float) -> np.ndarray:
    n = max(1, int(dur * SR))
    t = np.arange(n, dtype=np.float32) / SR
    phase = np.cumsum(np.full(n, freq, dtype=np.float32)) / SR
    x = 0.65 * np.sin(2.0 * np.pi * phase) + 0.35 * saw(freq * 2.0, dur)
    env = np.exp(-t * 6.8).astype(np.float32)
    return one_pole_lowpass((x * env).astype(np.float32), 3800.0)


def synth_guitar_bass(freq: float, dur: float) -> np.ndarray:
    n = max(1, int(dur * SR))
    t = np.arange(n, dtype=np.float32) / SR
    phase = np.cumsum(np.full(n, freq, dtype=np.float32)) / SR
    tri = (2.0 * np.abs(2.0 * (phase % 1.0) - 1.0) - 1.0).astype(np.float32)
    muted_saw = one_pole_lowpass(saw(freq * 2.0, dur, phase=0.31), 1450.0)
    pick = highpass_noise(n) * np.exp(-t * 48.0)
    palm = np.exp(-t * 5.4).astype(np.float32)
    body = np.sin(2.0 * np.pi * freq * 0.5 * t).astype(np.float32) * np.exp(-t * 3.2)
    return (0.52 * tri + 0.30 * muted_saw + 0.10 * pick + 0.25 * body) * palm


def kick() -> np.ndarray:
    dur = 0.62
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    freq = 43.0 + 105.0 * np.exp(-t * 18.0)
    phase = np.cumsum(freq) / SR
    body = np.sin(2.0 * np.pi * phase).astype(np.float32) * np.exp(-t * 7.7)
    thump = np.sin(2.0 * np.pi * 48.0 * t).astype(np.float32) * np.exp(-t * 4.4)
    click = highpass_noise(n) * np.exp(-t * 70.0)
    return (1.15 * body + 0.35 * thump + 0.12 * click).astype(np.float32)


def snare(clap: bool = False) -> np.ndarray:
    dur = 0.52 if clap else 0.44
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    noise = highpass_noise(n)
    env = np.exp(-t * (10.0 if clap else 13.0)).astype(np.float32)
    tone = np.sin(2.0 * np.pi * 185.0 * t).astype(np.float32) * np.exp(-t * 16.0)
    x = noise * env * (0.65 if clap else 0.48) + tone * 0.33
    if clap:
        for delay in [0.012, 0.026, 0.041]:
            d = int(delay * SR)
            if d < n:
                x[d:] += noise[:-d] * np.exp(-t[:-d] * 16.0) * 0.16
    return x.astype(np.float32)


def hat(open_hat: bool = False) -> np.ndarray:
    dur = 0.23 if open_hat else 0.075
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    noise = highpass_noise(n)
    env = np.exp(-t * (10.0 if open_hat else 48.0)).astype(np.float32)
    return (noise * env * (0.20 if open_hat else 0.12)).astype(np.float32)


def crash() -> np.ndarray:
    dur = 2.4
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    noise = highpass_noise(n)
    shimmer = np.sin(2.0 * np.pi * (6200.0 + 1500.0 * np.sin(2.0 * np.pi * 0.21 * t)) * t)
    env = np.exp(-t * 1.25).astype(np.float32)
    return (0.22 * noise * env + 0.025 * shimmer.astype(np.float32) * env).astype(np.float32)


def ride() -> np.ndarray:
    dur = 0.72
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    noise = highpass_noise(n)
    bell = (
        np.sin(2.0 * np.pi * 2700.0 * t)
        + 0.55 * np.sin(2.0 * np.pi * 4050.0 * t)
        + 0.32 * np.sin(2.0 * np.pi * 6120.0 * t)
    ).astype(np.float32)
    env = np.exp(-t * 4.3).astype(np.float32)
    return (0.16 * noise + 0.11 * bell) * env


def riser(dur: float, start_freq: float = 210.0, end_freq: float = 1150.0) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    freqs = np.linspace(start_freq, end_freq, n, dtype=np.float32)
    phase = np.cumsum(freqs) / SR
    tone = np.sin(2.0 * np.pi * phase).astype(np.float32)
    noise = one_pole_lowpass(highpass_noise(n), 5200.0)
    env = np.linspace(0.0, 1.0, n, dtype=np.float32) ** 1.5
    wobble = 0.65 + 0.35 * np.sin(2.0 * np.pi * (4.0 + 9.0 * t / max(dur, 0.001)) * t)
    return (0.24 * tone + 0.18 * noise) * env * wobble.astype(np.float32)


def downlifter(dur: float = 1.6) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    freqs = np.linspace(930.0, 85.0, n, dtype=np.float32)
    phase = np.cumsum(freqs) / SR
    tone = np.sin(2.0 * np.pi * phase).astype(np.float32)
    noise = highpass_noise(n) * np.exp(-t * 1.7)
    return (0.28 * tone * np.exp(-t * 1.4) + 0.13 * noise).astype(np.float32)


def impact() -> np.ndarray:
    n = int(1.1 * SR)
    t = np.arange(n, dtype=np.float32) / SR
    low = np.sin(2.0 * np.pi * 46.0 * t).astype(np.float32) * np.exp(-t * 3.7)
    boom = np.sin(2.0 * np.pi * (62.0 + 60.0 * np.exp(-t * 8.0)) * t).astype(np.float32)
    noise = highpass_noise(n) * np.exp(-t * 9.0)
    return (0.7 * low + 0.28 * boom * np.exp(-t * 5.0) + 0.09 * noise).astype(np.float32)


def ghost_pulse() -> np.ndarray:
    dur = 0.12
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    click = highpass_noise(n) * np.exp(-t * 120.0)
    body = np.sin(2.0 * np.pi * 62.0 * t).astype(np.float32) * np.exp(-t * 38.0)
    return (0.18 * click + 0.22 * body).astype(np.float32)


def chain_noise(dur: float) -> np.ndarray:
    n = int(dur * SR)
    out = np.zeros(n, dtype=np.float32)
    hit_times = np.arange(0.08, dur, 0.31)
    for i, hit_time in enumerate(hit_times):
        hit_n = int((0.05 + 0.015 * (i % 3)) * SR)
        start = int(hit_time * SR)
        if start >= n:
            break
        t = np.arange(hit_n, dtype=np.float32) / SR
        freqs = [1460.0 + 80 * (i % 5), 2310.0 + 120 * (i % 4), 3920.0 + 170 * (i % 3)]
        hit = sum(np.sin(2.0 * np.pi * f * t) for f in freqs).astype(np.float32)
        hit *= np.exp(-t * 38.0).astype(np.float32)
        hit += highpass_noise(hit_n) * np.exp(-t * 55.0).astype(np.float32) * 0.22
        end = min(start + hit_n, n)
        out[start:end] += hit[: end - start] * (0.07 + 0.025 * (i % 2))
    return out


def crowd_swell(dur: float) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    noise = one_pole_lowpass(highpass_noise(n), 1800.0)
    murmur = (
        np.sin(2.0 * np.pi * 173.0 * t + 0.4 * np.sin(2.0 * np.pi * 0.31 * t))
        + np.sin(2.0 * np.pi * 233.0 * t + 0.6 * np.sin(2.0 * np.pi * 0.19 * t))
    ).astype(np.float32)
    swell = np.minimum(1.0, np.linspace(0.1, 1.0, n, dtype=np.float32) ** 0.7)
    movement = (0.75 + 0.25 * np.sin(2.0 * np.pi * 0.11 * t)).astype(np.float32)
    return (0.16 * noise + 0.045 * murmur) * swell * movement


def filter_sweep(dur: float, base_freq: float = 220.0) -> np.ndarray:
    n = int(dur * SR)
    if n <= 0:
        return np.zeros(0, dtype=np.float32)
    t = np.arange(n, dtype=np.float32) / SR
    tone = np.zeros(n, dtype=np.float32)
    for ratio, gain in [(1.0, 0.55), (1.5, 0.34), (2.0, 0.26), (3.0, 0.16)]:
        tone += saw(base_freq * ratio, dur, phase=0.07 * ratio) * gain
    sweep = np.linspace(0.0, 1.0, n, dtype=np.float32)
    # Segment the tone through rising static low-pass cuts to emulate automation.
    out = np.zeros(n, dtype=np.float32)
    segments = 24
    for segment in range(segments):
        start = int(segment * n / segments)
        end = int((segment + 1) * n / segments)
        cutoff = 260.0 + 4200.0 * ((segment + 1) / segments) ** 1.7
        out[start:end] = one_pole_lowpass(tone[start:end], cutoff)
    env = (0.2 + 0.8 * sweep) * (0.9 + 0.1 * np.sin(2.0 * np.pi * 4.0 * t))
    return (out * env.astype(np.float32) * 0.35).astype(np.float32)


def apply_ducking(stem: np.ndarray, amount: float = 0.42, release: float = 0.27) -> np.ndarray:
    t = np.arange(len(stem), dtype=np.float32) / SR
    phase = (t / BEAT) % 1.0
    gain = 1.0 - amount * np.exp(-(phase * BEAT) / release)
    stem *= gain[:, None].astype(np.float32)
    return stem


def add_delay(stem: np.ndarray, delay_beats: float, feedback: float, wet: float, repeats: int = 4) -> None:
    delay = int(delay_beats * BEAT * SR)
    if delay <= 0:
        return
    dry = stem.copy()
    for rep in range(1, repeats + 1):
        d = delay * rep
        if d >= len(stem):
            break
        gain = wet * (feedback ** (rep - 1))
        # Cross-feed gives a simple stereo ping-pong.
        stem[d:, 0] += dry[:-d, 1] * gain
        stem[d:, 1] += dry[:-d, 0] * gain


def soft_clip(x: np.ndarray, drive: float = 1.25) -> np.ndarray:
    return np.tanh(x * drive) / np.tanh(drive)


def write_wav(path: Path, audio: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    audio = np.nan_to_num(audio, nan=0.0, posinf=0.0, neginf=0.0)
    peak = float(np.max(np.abs(audio))) or 1.0
    if peak > 0.98:
        audio = audio * (0.98 / peak)
    pcm = np.clip(audio, -1.0, 1.0)
    pcm16 = (pcm * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(SR)
        wav.writeframes(pcm16.tobytes())


def var_len(value: int) -> bytes:
    buffer = value & 0x7F
    value >>= 7
    out = []
    while value:
        out.append((buffer | 0x80) & 0xFF)
        buffer = value & 0x7F
        value >>= 7
    out.append(buffer & 0xFF)
    return bytes(reversed(out))


def midi_track_chunk(name: str, channel: int, events: list[tuple[float, float, int, int]], program: int | None) -> bytes:
    data = bytearray()
    data.extend(var_len(0))
    data.extend(b"\xff\x03")
    encoded_name = name.encode("ascii", errors="replace")
    data.extend(var_len(len(encoded_name)))
    data.extend(encoded_name)
    if program is not None:
        data.extend(var_len(0))
        data.extend(bytes([0xC0 | channel, program & 0x7F]))

    midi_events: list[tuple[int, int, bytes]] = []
    for start_beat, duration_beats, note, velocity in events:
        start_tick = max(0, int(round(start_beat * PPQ)))
        end_tick = max(start_tick + 1, int(round((start_beat + duration_beats) * PPQ)))
        midi_events.append((start_tick, 1, bytes([0x90 | channel, note & 0x7F, velocity & 0x7F])))
        midi_events.append((end_tick, 0, bytes([0x80 | channel, note & 0x7F, 0])))
    midi_events.sort(key=lambda item: (item[0], item[1]))

    current_tick = 0
    for tick, _, payload in midi_events:
        data.extend(var_len(tick - current_tick))
        data.extend(payload)
        current_tick = tick
    data.extend(var_len(0))
    data.extend(b"\xff\x2f\x00")
    return b"MTrk" + struct.pack(">I", len(data)) + bytes(data)


def tempo_track() -> bytes:
    data = bytearray()
    tempo = int(round(60_000_000 / BPM))
    data.extend(var_len(0))
    data.extend(b"\xff\x03\x08Conductor")
    data.extend(var_len(0))
    data.extend(b"\xff\x51\x03" + tempo.to_bytes(3, "big"))
    data.extend(var_len(0))
    data.extend(b"\xff\x58\x04\x04\x02\x18\x08")
    data.extend(var_len(0))
    data.extend(b"\xff\x2f\x00")
    return b"MTrk" + struct.pack(">I", len(data)) + bytes(data)


def write_midi(path: Path, tracks: list[tuple[str, int, int | None, list[tuple[float, float, int, int]]]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    chunks = [tempo_track()]
    for name, channel, program, events in tracks:
        chunks.append(midi_track_chunk(name, channel, events, program))
    header = b"MThd" + struct.pack(">IHHH", 6, 1, len(chunks), PPQ)
    path.write_bytes(header + b"".join(chunks))


def schedule_note(
    stem: np.ndarray,
    midi_events: list[tuple[float, float, int, int]],
    synth,
    start_beat: float,
    duration_beats: float,
    midi_note: int,
    velocity: int,
    gain: float,
    pan: float = 0.0,
    audio_extra_beats: float = 0.0,
    **synth_kwargs,
) -> None:
    dur = (duration_beats + audio_extra_beats) * BEAT
    audio = synth(note_to_freq(midi_note), dur, **synth_kwargs)
    add_mono(stem, beat_to_seconds(start_beat), audio, gain=gain, pan=pan)
    midi_events.append((start_beat, duration_beats, midi_note, velocity))


def render() -> None:
    EXPORTS.mkdir(exist_ok=True)
    MIDI_DIR.mkdir(exist_ok=True)

    drums = stereo_buffer()
    bass = stereo_buffer()
    chords = stereo_buffer()
    lead = stereo_buffer()
    fx = stereo_buffer()
    guitar_bass = stereo_buffer()
    hat_ride = stereo_buffer()
    frozen_build_bass = stereo_buffer()
    filter_automation = stereo_buffer()
    crowd_sidechain = stereo_buffer()
    lead_double = stereo_buffer()
    clap_stack = stereo_buffer()
    ghost_sidechain = stereo_buffer()
    ear_candy = stereo_buffer()

    midi_chords: list[tuple[float, float, int, int]] = []
    midi_bass: list[tuple[float, float, int, int]] = []
    midi_lead: list[tuple[float, float, int, int]] = []
    midi_plucks: list[tuple[float, float, int, int]] = []
    midi_drums: list[tuple[float, float, int, int]] = []
    midi_guitar_bass: list[tuple[float, float, int, int]] = []
    midi_hat_ride: list[tuple[float, float, int, int]] = []
    midi_lead_double: list[tuple[float, float, int, int]] = []
    midi_clap_stack: list[tuple[float, float, int, int]] = []

    progression = [
        {"name": "Em9", "notes": [52, 55, 59, 62, 66], "root": 28},
        {"name": "Cmaj7", "notes": [48, 52, 55, 59, 64], "root": 36},
        {"name": "Gadd9", "notes": [43, 50, 55, 59, 62], "root": 31},
        {"name": "Dsus2", "notes": [50, 57, 62, 66, 69], "root": 38},
    ]

    def chord_for_bar(bar: int) -> dict[str, list[int] | int | str]:
        return progression[bar % len(progression)]

    # Intro and breakdown pads.
    for bar in list(range(0, 16)) + list(range(32, 40)) + list(range(64, 72)):
        chord = chord_for_bar(bar)
        bright = 0.22 if bar < 8 else 0.38
        gain = 0.070 if bar < 8 else 0.092
        if bar >= 64:
            gain *= max(0.18, 1.0 - (bar - 64) / 8.0)
        for idx, note in enumerate(chord["notes"]):
            schedule_note(
                chords,
                midi_chords,
                synth_supersaw,
                bar_beat(bar),
                3.85,
                int(note),
                62,
                gain,
                pan=(-0.55 + idx * 0.275),
                audio_extra_beats=0.6,
                bright=bright,
                stab=False,
            )

    # Drop chord stabs and build chords.
    stab_rhythm = [(0.0, 0.82), (1.45, 0.48), (2.0, 0.58), (3.05, 0.72)]
    for bar in list(range(16, 32)) + list(range(48, 64)):
        chord = chord_for_bar(bar)
        for onset, dur in stab_rhythm:
            for idx, note in enumerate(chord["notes"]):
                schedule_note(
                    chords,
                    midi_chords,
                    synth_supersaw,
                    bar_beat(bar, onset),
                    dur,
                    int(note),
                    92,
                    0.180,
                    pan=(-0.62 + idx * 0.31),
                    audio_extra_beats=0.18,
                    bright=0.92,
                    stab=True,
                )

    for bar in range(40, 48):
        chord = chord_for_bar(bar)
        lift = (bar - 40) / 8.0
        for idx, note in enumerate(chord["notes"]):
            schedule_note(
                chords,
                midi_chords,
                synth_supersaw,
                bar_beat(bar),
                3.72,
                int(note),
                72 + int(lift * 16),
                0.090 + lift * 0.052,
                pan=(-0.52 + idx * 0.26),
                audio_extra_beats=0.35,
                bright=0.45 + lift * 0.44,
                stab=False,
            )

    # Plucks: a small arpeggiated motif for intro/build texture.
    for section_start, section_end, vel_base in [(4, 16, 67), (40, 48, 76)]:
        for bar in range(section_start, section_end):
            chord = chord_for_bar(bar)
            arp_notes = list(chord["notes"])[1:] + [list(chord["notes"])[-1] + 12]
            for step in range(8):
                note = int(arp_notes[step % len(arp_notes)])
                schedule_note(
                    lead,
                    midi_plucks,
                    synth_pluck,
                    bar_beat(bar, step * 0.5),
                    0.28,
                    note,
                    vel_base + (step % 3) * 5,
                    0.055 if section_start == 4 else 0.075,
                    pan=-0.3 if step % 2 else 0.3,
                    audio_extra_beats=0.16,
                )

    # Bass follows the same bounce as the chord stabs with a few pickup notes.
    for bar in list(range(16, 32)) + list(range(48, 64)):
        root = int(chord_for_bar(bar)["root"])
        for onset, dur in stab_rhythm:
            schedule_note(
                bass,
                midi_bass,
                synth_bass,
                bar_beat(bar, onset),
                dur,
                root,
                104,
                0.26,
                pan=0.0,
                audio_extra_beats=0.04,
            )
        if bar % 4 == 3:
            schedule_note(
                bass,
                midi_bass,
                synth_bass,
                bar_beat(bar, 3.55),
                0.25,
                root + 12,
                86,
                0.12,
                pan=0.0,
                audio_extra_beats=0.03,
            )

    # Soft bass in the verse.
    for bar in range(8, 16):
        root = int(chord_for_bar(bar)["root"]) + 12
        schedule_note(bass, midi_bass, synth_bass, bar_beat(bar), 1.45, root, 72, 0.100)
        schedule_note(bass, midi_bass, synth_bass, bar_beat(bar, 2.0), 1.45, root, 70, 0.090)

    # Muted guitar-bass style layer used in the verse and build.
    guitar_rhythm = [(0.0, 0.42), (0.74, 0.30), (1.45, 0.38), (2.0, 0.46), (3.05, 0.34)]
    for bar in list(range(8, 16)) + list(range(40, 48)):
        root = int(chord_for_bar(bar)["root"]) + 12
        lift = 0.25 if bar >= 40 else 0.0
        for onset, dur in guitar_rhythm:
            schedule_note(
                guitar_bass,
                midi_guitar_bass,
                synth_guitar_bass,
                bar_beat(bar, onset),
                dur,
                root + (12 if onset > 2.8 and bar % 4 == 3 else 0),
                76 + int(lift * 24),
                0.110 + lift * 0.035,
                pan=-0.08,
                audio_extra_beats=0.04,
            )

    # Frozen/rendered build bass: an explicit audio stem that mirrors the build notes.
    for bar in range(40, 48):
        root = int(chord_for_bar(bar)["root"]) + 12
        lift = (bar - 40) / 8.0
        for onset, dur in [(0.0, 1.35), (2.0, 1.35), (3.35, 0.32)]:
            schedule_note(
                frozen_build_bass,
                midi_bass,
                synth_bass,
                bar_beat(bar, onset),
                dur,
                root,
                82 + int(lift * 18),
                0.115 + lift * 0.045,
                pan=0.0,
                audio_extra_beats=0.03,
            )

    # Filter automation rendered as an audible sweep layer through the build.
    for bar in range(40, 48):
        root = int(chord_for_bar(bar)["root"]) + 24
        add_mono(
            filter_automation,
            beat_to_seconds(bar_beat(bar)),
            filter_sweep(4 * BEAT, note_to_freq(root)),
            gain=0.23 + 0.04 * ((bar - 40) / 8.0),
            pan=0.0,
        )

    # Original lead hook. Short rests and repeated accents keep it energetic
    # without quoting a commercial top line.
    hook = [
        [(0.00, 0.46, 76), (0.52, 0.42, 79), (1.05, 0.70, 83), (2.00, 0.42, 86), (2.52, 0.38, 83), (3.04, 0.68, 79)],
        [(0.00, 0.42, 84), (0.50, 0.44, 83), (1.02, 0.54, 79), (1.72, 0.38, 76), (2.18, 0.42, 81), (2.72, 0.68, 79)],
        [(0.00, 0.40, 83), (0.46, 0.42, 86), (0.98, 0.74, 88), (2.00, 0.40, 86), (2.48, 0.42, 83), (3.00, 0.70, 81)],
        [(0.00, 0.44, 79), (0.55, 0.38, 83), (1.04, 0.38, 81), (1.54, 0.38, 79), (2.12, 0.78, 76), (3.08, 0.40, 74), (3.55, 0.34, 76)],
    ]

    def add_hook(start_bar: int, bars: int, gain: float, variation: int = 0) -> None:
        for bar_offset in range(bars):
            pattern = hook[bar_offset % len(hook)]
            transpose = 12 if bar_offset >= 8 and variation else 0
            for onset, dur, note in pattern:
                if variation and bar_offset % 8 == 7 and onset > 2.5:
                    note += 2
                schedule_note(
                    lead,
                    midi_lead,
                    synth_lead,
                    bar_beat(start_bar + bar_offset, onset),
                    dur,
                    note + transpose,
                    104 if gain > 0.09 else 80,
                    gain,
                    pan=0.05 if (bar_offset + int(onset * 10)) % 2 else -0.05,
                    audio_extra_beats=0.10,
                    soft=gain < 0.08,
                )

    def add_hook_double(start_bar: int, bars: int, gain: float, variation: int = 0) -> None:
        for bar_offset in range(bars):
            pattern = hook[bar_offset % len(hook)]
            transpose = 12 if bar_offset >= 8 and variation else 0
            for onset, dur, note in pattern:
                if onset > 3.2 and bar_offset % 2 == 0:
                    continue
                doubled_note = note + transpose + (12 if note < 83 else 0)
                schedule_note(
                    lead_double,
                    midi_lead_double,
                    synth_lead_double,
                    bar_beat(start_bar + bar_offset, onset),
                    max(0.24, dur * 0.92),
                    doubled_note,
                    86,
                    gain,
                    pan=-0.42 if (bar_offset + int(onset * 10)) % 2 else 0.42,
                    audio_extra_beats=0.12,
                )

    add_hook(16, 16, 0.180, variation=0)
    add_hook(48, 16, 0.190, variation=1)
    add_hook(32, 8, 0.070, variation=0)
    add_hook_double(16, 16, 0.135, variation=0)
    add_hook_double(48, 16, 0.150, variation=1)

    # Drums.
    k = kick()
    s = snare(False)
    c = snare(True)
    h = hat(False)
    oh = hat(True)
    cr = crash()
    gp = ghost_pulse()
    for bar in range(8, 16):
        for b in [0.0, 2.0]:
            add_mono(drums, beat_to_seconds(bar_beat(bar, b)), k, gain=0.68)
            midi_drums.append((bar_beat(bar, b), 0.20, 36, 88))
        add_mono(drums, beat_to_seconds(bar_beat(bar, 2.0)), c, gain=0.42)
        midi_drums.append((bar_beat(bar, 2.0), 0.20, 39, 78))
        add_mono(clap_stack, beat_to_seconds(bar_beat(bar, 2.0)), c, gain=0.28, pan=0.08)
        midi_clap_stack.append((bar_beat(bar, 2.0), 0.18, 39, 66))
        for step in range(8):
            add_mono(drums, beat_to_seconds(bar_beat(bar, step * 0.5)), h, gain=0.45 if step % 2 else 0.34, pan=0.22)
            midi_drums.append((bar_beat(bar, step * 0.5), 0.08, 42, 52 if step % 2 else 42))

    drop_bars = list(range(16, 32)) + list(range(48, 64))
    for bar in drop_bars:
        for b in [0.0, 1.45, 2.0, 3.05]:
            add_mono(drums, beat_to_seconds(bar_beat(bar, b)), k, gain=0.96)
            add_mono(ghost_sidechain, beat_to_seconds(bar_beat(bar, b)), gp, gain=0.46)
            midi_drums.append((bar_beat(bar, b), 0.18, 36, 112))
        for b in [2.0]:
            add_mono(drums, beat_to_seconds(bar_beat(bar, b)), s, gain=0.92)
            add_mono(drums, beat_to_seconds(bar_beat(bar, b + 0.02)), c, gain=0.44, pan=-0.05)
            add_mono(clap_stack, beat_to_seconds(bar_beat(bar, b - 0.012)), s, gain=0.34, pan=-0.18)
            add_mono(clap_stack, beat_to_seconds(bar_beat(bar, b + 0.018)), c, gain=0.58, pan=0.20)
            add_mono(clap_stack, beat_to_seconds(bar_beat(bar, b + 0.048)), c, gain=0.22, pan=-0.34)
            midi_drums.append((bar_beat(bar, b), 0.20, 38, 112))
            midi_drums.append((bar_beat(bar, b + 0.02), 0.18, 39, 82))
            midi_clap_stack.append((bar_beat(bar, b), 0.18, 38, 96))
            midi_clap_stack.append((bar_beat(bar, b + 0.02), 0.18, 39, 92))
        for step in range(8):
            vel = 58 + (14 if step % 2 else 0)
            add_mono(drums, beat_to_seconds(bar_beat(bar, step * 0.5)), h, gain=0.38 + 0.09 * (step % 2), pan=0.28)
            midi_drums.append((bar_beat(bar, step * 0.5), 0.08, 42, vel))
        if bar % 4 == 3:
            for b in [3.5, 3.75]:
                add_mono(drums, beat_to_seconds(bar_beat(bar, b)), h, gain=0.58, pan=-0.32)
                midi_drums.append((bar_beat(bar, b), 0.07, 42, 78))
        if bar in [16, 24, 48, 56]:
            add_mono(drums, beat_to_seconds(bar_beat(bar)), cr, gain=0.76, pan=-0.18)
            midi_drums.append((bar_beat(bar), 1.0, 49, 96))

    # Dedicated hat/ride/crash layer for the drop variation.
    rd = ride()
    for bar in range(48, 64):
        for step in range(16):
            b = step * 0.25
            gain = 0.22 + (0.10 if step % 4 in [1, 3] else 0.0)
            add_mono(hat_ride, beat_to_seconds(bar_beat(bar, b)), h, gain=gain, pan=0.36 if step % 2 else -0.18)
            midi_hat_ride.append((bar_beat(bar, b), 0.05, 42, 52 + (step % 4) * 5))
        if bar >= 56:
            for b in [0.0, 1.0, 2.0, 3.0]:
                add_mono(hat_ride, beat_to_seconds(bar_beat(bar, b)), rd, gain=0.55, pan=-0.34)
                midi_hat_ride.append((bar_beat(bar, b), 0.18, 51, 80))
        if bar in [48, 52, 56, 60]:
            add_mono(hat_ride, beat_to_seconds(bar_beat(bar)), cr, gain=0.55, pan=0.22)
            midi_hat_ride.append((bar_beat(bar), 1.0, 49, 92))

    for bar in range(40, 48):
        add_mono(drums, beat_to_seconds(bar_beat(bar)), k, gain=0.72)
        add_mono(ghost_sidechain, beat_to_seconds(bar_beat(bar)), gp, gain=0.42)
        midi_drums.append((bar_beat(bar), 0.18, 36, 94))
        density = 0.5 if bar < 44 else 0.25
        steps = int(4 / density)
        for step in range(steps):
            b = step * density
            lift = (bar - 40 + step / max(steps, 1)) / 8.0
            add_mono(drums, beat_to_seconds(bar_beat(bar, b)), s, gain=0.22 + lift * 0.55, pan=(-0.12 if step % 2 else 0.12))
            add_mono(clap_stack, beat_to_seconds(bar_beat(bar, b)), c if step % 2 else s, gain=0.12 + lift * 0.34, pan=0.22 if step % 2 else -0.22)
            midi_drums.append((bar_beat(bar, b), 0.10, 38, int(45 + lift * 55)))
            midi_clap_stack.append((bar_beat(bar, b), 0.10, 39 if step % 2 else 38, int(44 + lift * 50)))
            if step % 2 == 0:
                add_mono(drums, beat_to_seconds(bar_beat(bar, b)), h, gain=0.32 + lift * 0.28, pan=0.24)
                midi_drums.append((bar_beat(bar, b), 0.06, 42, int(48 + lift * 35)))

    # FX transitions and impacts.
    for bar in [16, 32, 40, 48, 64]:
        add_mono(fx, beat_to_seconds(bar_beat(bar)), impact(), gain=0.70, pan=0.0)
        add_mono(fx, beat_to_seconds(bar_beat(bar, 0.05)), downlifter(), gain=0.52, pan=0.15)
    add_mono(fx, beat_to_seconds(bar_beat(12)), riser(4 * BEAT, 180, 760), gain=0.50, pan=0.0)
    add_mono(fx, beat_to_seconds(bar_beat(40)), riser(8 * 4 * BEAT, 160, 1450), gain=0.62, pan=0.0)
    add_mono(fx, beat_to_seconds(bar_beat(47, 3.65)), snare(True), gain=1.0, pan=0.0)
    add_mono(fx, beat_to_seconds(bar_beat(40)), chain_noise(8 * 4 * BEAT), gain=0.88, pan=-0.24)

    # Ear-candy transition lane: reverse tails, bright pitch blips, and extra fills.
    for bar in [15, 31, 47, 63]:
        add_mono(ear_candy, beat_to_seconds(bar_beat(bar, 3.15)), riser(0.8 * BEAT, 520, 2100), gain=0.26, pan=-0.35)
        add_mono(ear_candy, beat_to_seconds(bar_beat(bar, 3.55)), downlifter(0.65), gain=0.30, pan=0.36)
    for bar in [14, 30, 46, 62]:
        chord = chord_for_bar(bar)
        for idx, note in enumerate(list(chord["notes"])[-3:]):
            add_mono(
                ear_candy,
                beat_to_seconds(bar_beat(bar, 2.5 + idx * 0.25)),
                synth_pluck(note_to_freq(int(note) + 24), 0.32 * BEAT),
                gain=0.11,
                pan=-0.45 + idx * 0.45,
            )
    for bar in [16, 24, 48, 56]:
        add_mono(ear_candy, beat_to_seconds(bar_beat(bar, 0.08)), crash(), gain=0.22, pan=0.42)

    # Sidechained crowd swell in the drop.
    add_mono(crowd_sidechain, beat_to_seconds(bar_beat(48)), crowd_swell(16 * 4 * BEAT), gain=0.96, pan=0.0)

    # Mix effects.
    apply_ducking(chords, amount=0.34, release=0.22)
    apply_ducking(bass, amount=0.24, release=0.17)
    apply_ducking(guitar_bass, amount=0.18, release=0.16)
    apply_ducking(frozen_build_bass, amount=0.30, release=0.18)
    apply_ducking(filter_automation, amount=0.44, release=0.24)
    apply_ducking(crowd_sidechain, amount=0.68, release=0.30)
    apply_ducking(lead_double, amount=0.42, release=0.22)
    apply_ducking(clap_stack, amount=0.12, release=0.12)
    apply_ducking(ear_candy, amount=0.36, release=0.24)
    add_delay(lead, delay_beats=0.75, feedback=0.48, wet=0.28, repeats=5)
    add_delay(lead_double, delay_beats=0.75, feedback=0.34, wet=0.22, repeats=4)
    add_delay(chords, delay_beats=1.5, feedback=0.30, wet=0.11, repeats=3)
    add_delay(fx, delay_beats=2.0, feedback=0.30, wet=0.18, repeats=4)
    add_delay(ear_candy, delay_beats=0.5, feedback=0.42, wet=0.24, repeats=5)

    # Section fades.
    fade_len = int(2.0 * SR)
    intro = np.linspace(0.0, 1.0, fade_len, dtype=np.float32)
    for stem in [drums, bass, chords, lead, fx, guitar_bass, hat_ride, frozen_build_bass, filter_automation, crowd_sidechain, lead_double, clap_stack, ghost_sidechain, ear_candy]:
        stem[:fade_len] *= intro[:, None]
        stem[-fade_len:] *= intro[::-1, None]

    stems = {
        "drums": drums,
        "bass": bass,
        "chords": chords,
        "lead_and_plucks": lead,
        "fx": fx,
        "guitar_bass": guitar_bass,
        "hat_ride": hat_ride,
        "frozen_build_bass": frozen_build_bass,
        "filter_automation": filter_automation,
        "crowd_sidechain": crowd_sidechain,
        "lead_double": lead_double,
        "clap_stack": clap_stack,
        "ghost_sidechain": ghost_sidechain,
        "ear_candy": ear_candy,
    }

    mix = np.zeros_like(drums)
    stem_gains = {
        "drums": 0.76,
        "bass": 0.90,
        "chords": 1.10,
        "lead_and_plucks": 1.25,
        "fx": 0.58,
        "guitar_bass": 0.72,
        "hat_ride": 0.58,
        "frozen_build_bass": 0.78,
        "filter_automation": 0.56,
        "crowd_sidechain": 0.62,
        "lead_double": 0.88,
        "clap_stack": 0.72,
        "ghost_sidechain": 0.16,
        "ear_candy": 0.78,
    }
    for name, stem in stems.items():
        mix += stem * stem_gains[name]

    mix = soft_clip(mix, drive=1.35) * 0.92

    write_wav(EXPORTS / "neon_solitude_full_mix.wav", mix)
    for name, stem in stems.items():
        stem_audio = soft_clip(stem * stem_gains[name], drive=1.15) * 0.90
        write_wav(EXPORTS / f"neon_solitude_{name}.wav", stem_audio)

    arrangement_tracks = [
        ("Chords", 0, 81, midi_chords),
        ("Bass", 1, 38, midi_bass),
        ("Lead", 2, 80, midi_lead),
        ("Plucks", 3, 11, midi_plucks),
        ("Drums", 9, None, midi_drums),
        ("Guitar Bass", 4, 34, midi_guitar_bass),
        ("Hat Ride", 9, None, midi_hat_ride),
        ("Lead Double", 5, 82, midi_lead_double),
        ("Clap Stack", 9, None, midi_clap_stack),
    ]
    write_midi(MIDI_DIR / "neon_solitude_arrangement.mid", arrangement_tracks)
    write_midi(MIDI_DIR / "neon_solitude_chords.mid", [arrangement_tracks[0]])
    write_midi(MIDI_DIR / "neon_solitude_bass.mid", [arrangement_tracks[1]])
    write_midi(MIDI_DIR / "neon_solitude_lead.mid", [arrangement_tracks[2]])
    write_midi(MIDI_DIR / "neon_solitude_plucks.mid", [arrangement_tracks[3]])
    write_midi(MIDI_DIR / "neon_solitude_drums.mid", [arrangement_tracks[4]])
    write_midi(MIDI_DIR / "neon_solitude_guitar_bass.mid", [arrangement_tracks[5]])
    write_midi(MIDI_DIR / "neon_solitude_hat_ride.mid", [arrangement_tracks[6]])
    write_midi(MIDI_DIR / "neon_solitude_lead_double.mid", [arrangement_tracks[7]])
    write_midi(MIDI_DIR / "neon_solitude_clap_stack.mid", [arrangement_tracks[8]])

    notes = f"""Neon Solitude - original EDM production package

Tempo: {BPM} BPM
Key center: E minor / G major
Length: {TOTAL_BARS} bars, {TOTAL_SECONDS:.1f} seconds including tail

Files:
- exports/neon_solitude_full_mix.wav
- exports/neon_solitude_drums.wav
- exports/neon_solitude_bass.wav
- exports/neon_solitude_chords.wav
- exports/neon_solitude_lead_and_plucks.wav
- exports/neon_solitude_fx.wav
- exports/neon_solitude_guitar_bass.wav
- exports/neon_solitude_hat_ride.wav
- exports/neon_solitude_frozen_build_bass.wav
- exports/neon_solitude_filter_automation.wav
- exports/neon_solitude_crowd_sidechain.wav
- exports/neon_solitude_lead_double.wav
- exports/neon_solitude_clap_stack.wav
- exports/neon_solitude_ghost_sidechain.wav
- exports/neon_solitude_ear_candy.wav
- midi/neon_solitude_arrangement.mid
- midi/neon_solitude_chords.mid
- midi/neon_solitude_bass.mid
- midi/neon_solitude_lead.mid
- midi/neon_solitude_plucks.mid
- midi/neon_solitude_drums.mid
- midi/neon_solitude_guitar_bass.mid
- midi/neon_solitude_hat_ride.mid
- midi/neon_solitude_lead_double.mid
- midi/neon_solitude_clap_stack.mid

DAW import:
1. Set the project tempo to {BPM} BPM.
2. Import the WAV stems at bar 1, beat 1.
3. Import the arrangement MIDI if you want to replace the synth sounds.
4. Put a sidechain/pump compressor or volume shaper on chords and bass for a stronger drop.

Next/Tailwind studio:
1. Run npm run dev.
2. Open http://127.0.0.1:5173/.
3. Open the seeded Neon Solitude project from the home screen.
4. Use Save to keep local edits, Backup to export a .json copy, and Restore to import one.
5. The Recipe tab tracks 23 implemented production items, including the deeper Lead Double, Clap Stack, Ghost Key, and Ear Candy lanes.

This is an original track in a bright future-bass/festival style. It does not
reuse commercial stems, lyrics, or melody from "Alone".
"""
    (ROOT / "README.md").write_text(notes, encoding="utf-8")


def synth_la_pluck(freq: float, dur: float, tone: float = 0.5) -> np.ndarray:
    n = max(1, int(dur * SR))
    t = np.arange(n, dtype=np.float32) / SR
    detune = 1.0 + 0.0018 * np.sin(2.0 * np.pi * 5.1 * t)
    phase = np.cumsum((freq * detune).astype(np.float32)) / SR
    body = (
        0.62 * np.sin(2.0 * np.pi * phase)
        + 0.22 * np.sin(2.0 * np.pi * phase * 2.01)
        + 0.12 * np.sin(2.0 * np.pi * phase * 3.02)
    ).astype(np.float32)
    transient = highpass_noise(n) * np.exp(-t * 78.0).astype(np.float32) * 0.06
    knock = np.sin(2.0 * np.pi * (freq * 0.5) * t).astype(np.float32) * np.exp(-t * 16.0)
    env = np.exp(-t * (4.2 + 1.9 * tone)).astype(np.float32)
    out = one_pole_lowpass((body + transient + 0.13 * knock) * env, 2600.0 + 2400.0 * tone)
    return out.astype(np.float32)


def synth_vocal_chop(freq: float, dur: float, vowel: float = 0.5) -> np.ndarray:
    n = max(1, int(dur * SR))
    t = np.arange(n, dtype=np.float32) / SR
    vibrato = 1.0 + 0.0035 * np.sin(2.0 * np.pi * 5.8 * t)
    phase = np.cumsum((freq * vibrato).astype(np.float32)) / SR
    carrier = 0.58 * np.sin(2.0 * np.pi * phase) + 0.30 * saw(freq, dur, phase=0.12)
    form_a = 0.5 + 0.5 * np.sin(2.0 * np.pi * (620.0 + 240.0 * vowel) * t + 0.6)
    form_b = 0.5 + 0.5 * np.sin(2.0 * np.pi * (1120.0 + 460.0 * vowel) * t + 1.3)
    breath = highpass_noise(n) * 0.035
    chop_env = adsr(n, attack=0.006, decay=0.045, sustain=0.50, release=0.075)
    gate = (0.76 + 0.24 * np.sin(2.0 * np.pi * 8.0 * t + vowel)).astype(np.float32)
    out = (carrier * (0.68 + 0.22 * form_a + 0.10 * form_b) + breath) * chop_env * gate
    return one_pole_lowpass(out.astype(np.float32), 5200.0)


def synth_heaven_pad(freq: float, dur: float, bright: float = 0.5) -> np.ndarray:
    n = max(1, int(dur * SR))
    t = np.arange(n, dtype=np.float32) / SR
    out = np.zeros(n, dtype=np.float32)
    for idx, cents in enumerate([-8.0, -3.5, 0.0, 5.0, 11.0]):
        out += saw(freq * (2.0 ** (cents / 1200.0)), dur, phase=0.09 * idx) * (0.18 + 0.03 * idx)
    out += 0.28 * np.sin(2.0 * np.pi * freq * 0.5 * t).astype(np.float32)
    out += one_pole_lowpass(highpass_noise(n), 3600.0 + bright * 2600.0) * 0.035
    out = one_pole_lowpass(out, 1400.0 + 4200.0 * bright)
    env = adsr(n, attack=0.55, decay=0.75, sustain=0.82, release=1.35)
    shimmer = (0.88 + 0.12 * np.sin(2.0 * np.pi * 0.13 * t + freq * 0.01)).astype(np.float32)
    return (out * env * shimmer).astype(np.float32)


def synth_808(freq: float, dur: float, end_freq: float | None = None, tone: float = 0.6) -> np.ndarray:
    n = max(1, int(dur * SR))
    t = np.arange(n, dtype=np.float32) / SR
    if end_freq is None:
        freqs = np.full(n, freq, dtype=np.float32)
    else:
        freqs = np.linspace(freq, end_freq, n, dtype=np.float32)
    freqs += 26.0 * np.exp(-t * 32.0).astype(np.float32)
    phase = np.cumsum(freqs) / SR
    sine = np.sin(2.0 * np.pi * phase).astype(np.float32)
    tri = (2.0 * np.abs(2.0 * (phase % 1.0) - 1.0) - 1.0).astype(np.float32)
    grit = np.tanh((0.78 * sine + 0.26 * tri) * (1.25 + tone * 1.2))
    click = highpass_noise(n) * np.exp(-t * 95.0).astype(np.float32) * 0.035
    env = adsr(n, attack=0.002, decay=0.08, sustain=0.86, release=0.11)
    return (0.76 * sine + 0.30 * grit + click) * env


def synth_guitar_pluck(freq: float, dur: float) -> np.ndarray:
    n = max(1, int(dur * SR))
    t = np.arange(n, dtype=np.float32) / SR
    phase = np.cumsum(np.full(n, freq, dtype=np.float32)) / SR
    string = (
        0.54 * np.sin(2.0 * np.pi * phase)
        + 0.22 * np.sin(2.0 * np.pi * phase * 2.0)
        + 0.13 * saw(freq * 1.01, dur, phase=0.22)
    ).astype(np.float32)
    pick = highpass_noise(n) * np.exp(-t * 62.0).astype(np.float32) * 0.07
    env = np.exp(-t * 5.8).astype(np.float32)
    return one_pole_lowpass((string + pick) * env, 3100.0)


def synth_bell(freq: float, dur: float) -> np.ndarray:
    n = max(1, int(dur * SR))
    t = np.arange(n, dtype=np.float32) / SR
    partials = (
        0.62 * np.sin(2.0 * np.pi * freq * t)
        + 0.26 * np.sin(2.0 * np.pi * freq * 2.02 * t)
        + 0.15 * np.sin(2.0 * np.pi * freq * 3.91 * t)
    ).astype(np.float32)
    env = np.exp(-t * 3.0).astype(np.float32)
    return partials * env


def rim() -> np.ndarray:
    n = int(0.18 * SR)
    t = np.arange(n, dtype=np.float32) / SR
    tone = (
        np.sin(2.0 * np.pi * 870.0 * t)
        + 0.55 * np.sin(2.0 * np.pi * 1510.0 * t)
        + 0.28 * np.sin(2.0 * np.pi * 2420.0 * t)
    ).astype(np.float32)
    noise = highpass_noise(n) * 0.12
    return (tone + noise) * np.exp(-t * 42.0).astype(np.float32) * 0.24


def shaker(dur: float = 0.07) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    return highpass_noise(n) * np.exp(-t * 52.0).astype(np.float32) * 0.10


def add_808(
    stem: np.ndarray,
    midi_events: list[tuple[float, float, int, int]],
    start_beat: float,
    duration_beats: float,
    midi_note: int,
    velocity: int,
    gain: float,
    pan: float = 0.0,
    slide_to: int | None = None,
) -> None:
    end_freq = note_to_freq(slide_to) if slide_to is not None else None
    audio = synth_808(note_to_freq(midi_note), duration_beats * BEAT, end_freq=end_freq)
    add_mono(stem, beat_to_seconds(start_beat), audio, gain=gain, pan=pan)
    midi_events.append((start_beat, duration_beats, midi_note, velocity))


def _clip(track_id: str, suffix: str, name: str, start_bar: int, bars: int, clip_type: str = "audio") -> dict[str, object]:
    return {
        "id": f"{track_id}-{suffix}",
        "name": name,
        "startBar": start_bar,
        "bars": bars,
        "lane": track_id,
        "color": TRACK_COLORS[track_id],
        "type": clip_type,
    }


TRACK_COLORS = {
    "drums": "#ff8d5c",
    "bass": "#45d18e",
    "chords": "#ffcd5a",
    "lead": "#60c8f8",
    "fx": "#d885ff",
    "guitar-bass": "#f3b26a",
    "hat-ride": "#f7e27a",
    "frozen-build-bass": "#6ee7b7",
    "filter-automation": "#7dd3fc",
    "crowd-sidechain": "#c084fc",
    "lead-double": "#93c5fd",
    "clap-stack": "#fb7185",
    "ghost-sidechain": "#94a3b8",
    "ear-candy": "#f0abfc",
}


def update_neon_project_files() -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    asset_files = {
        "drums": "neon_solitude_drums.wav",
        "bass": "neon_solitude_bass.wav",
        "chords": "neon_solitude_chords.wav",
        "lead": "neon_solitude_lead_and_plucks.wav",
        "fx": "neon_solitude_fx.wav",
        "guitar-bass": "neon_solitude_guitar_bass.wav",
        "hat-ride": "neon_solitude_hat_ride.wav",
        "frozen-build-bass": "neon_solitude_frozen_build_bass.wav",
        "filter-automation": "neon_solitude_filter_automation.wav",
        "crowd-sidechain": "neon_solitude_crowd_sidechain.wav",
        "lead-double": "neon_solitude_lead_double.wav",
        "clap-stack": "neon_solitude_clap_stack.wav",
        "ghost-sidechain": "neon_solitude_ghost_sidechain.wav",
        "ear-candy": "neon_solitude_ear_candy.wav",
    }
    assets = [{"trackId": track_id, "file": f"/api/audio/{file_name}"} for track_id, file_name in asset_files.items()]

    track_specs = [
        {
            "id": "drums",
            "name": "Sunset Drums",
            "instrument": "LA Drum Rack",
            "gain": 0.82,
            "pan": 0.0,
            "steps": [0, 3, 6, 8, 11, 14],
            "clips": [
                _clip("drums", "intro", "Snap intro pocket", 4, 4, "pattern"),
                _clip("drums", "verse", "Lean pocket drums", 8, 8, "audio"),
                _clip("drums", "hook", "Hook drums", 16, 16, "audio"),
                _clip("drums", "break", "Break fill drums", 32, 8, "audio"),
                _clip("drums", "build", "Build snare lift", 40, 8, "audio"),
                _clip("drums", "final", "Final hook drums", 48, 16, "audio"),
            ],
            "effects": [
                {"id": "eq", "name": "Pultec Low Lift", "active": True, "amount": 0.46},
                {"id": "comp", "name": "Glue Comp", "active": True, "amount": 0.58},
                {"id": "clip", "name": "Soft Clip", "active": True, "amount": 0.34},
            ],
        },
        {
            "id": "bass",
            "name": "Velvet 808",
            "instrument": "Saturated 808/Sub",
            "gain": 0.92,
            "pan": 0.0,
            "steps": [0, 6, 10, 13],
            "clips": [
                _clip("bass", "verse", "Verse 808 bounce", 8, 8, "audio"),
                _clip("bass", "hook", "Hook 808 slides", 16, 16, "audio"),
                _clip("bass", "break", "Break low sustain", 32, 8, "audio"),
                _clip("bass", "build", "Build 808 answer", 40, 8, "audio"),
                _clip("bass", "final", "Final 808 slides", 48, 16, "audio"),
            ],
            "effects": [
                {"id": "drive", "name": "Warm Drive", "active": True, "amount": 0.42},
                {"id": "sidechain", "name": "Kick Sidechain", "active": True, "amount": 0.58},
                {"id": "mono", "name": "Mono Below 120", "active": True, "amount": 0.82},
            ],
        },
        {
            "id": "chords",
            "name": "Heaven Pad",
            "instrument": "Air Pad + Sidechain Stabs",
            "gain": 0.95,
            "pan": 0.0,
            "steps": [0, 4, 8, 12],
            "clips": [
                _clip("chords", "intro", "Heaven opening pad", 0, 16, "audio"),
                _clip("chords", "hook", "Sidechained hook pad", 16, 16, "audio"),
                _clip("chords", "break", "Sky break chords", 32, 8, "audio"),
                _clip("chords", "build", "Rising filtered pad", 40, 8, "audio"),
                _clip("chords", "final", "Final hook stabs", 48, 16, "audio"),
                _clip("chords", "outro", "Palm-tree outro pad", 64, 8, "audio"),
            ],
            "effects": [
                {"id": "eq", "name": "Low Cut EQ", "active": True, "amount": 0.70},
                {"id": "delay", "name": "Dotted Ping Delay", "active": True, "amount": 0.34},
                {"id": "reverb", "name": "Shimmer Plate", "active": True, "amount": 0.48},
                {"id": "duck", "name": "Pump Sidechain", "active": True, "amount": 0.52},
            ],
        },
        {
            "id": "lead",
            "name": "Vocal Pluck Hook",
            "instrument": "Vocal Chop Synth",
            "gain": 0.98,
            "pan": 0.02,
            "steps": [0, 2, 5, 7, 10, 12, 15],
            "clips": [
                _clip("lead", "intro", "Beach pluck motif", 4, 12, "audio"),
                _clip("lead", "hook", "Vocal-pluck hook", 16, 16, "audio"),
                _clip("lead", "break", "Soft break hook", 32, 8, "audio"),
                _clip("lead", "build", "Hook teaser", 40, 8, "audio"),
                _clip("lead", "final", "Final hook variation", 48, 16, "audio"),
            ],
            "effects": [
                {"id": "fresh", "name": "Fresh Air Shelf", "active": True, "amount": 0.56},
                {"id": "delay", "name": "Stereo Throw Delay", "active": True, "amount": 0.48},
                {"id": "plate", "name": "Bright Plate", "active": True, "amount": 0.36},
                {"id": "spread", "name": "Micro Width", "active": True, "amount": 0.44},
            ],
        },
        {
            "id": "fx",
            "name": "LA FX",
            "instrument": "Risers, Impacts, Air",
            "gain": 0.66,
            "pan": 0.0,
            "steps": [0, 8],
            "clips": [
                _clip("fx", "intro-air", "Ocean-air intro", 0, 8, "audio"),
                _clip("fx", "pre-hook", "Pre-hook reverse", 14, 2, "audio"),
                _clip("fx", "hook-impact", "Hook impact", 16, 1, "audio"),
                _clip("fx", "break", "Break downlifter", 32, 8, "audio"),
                _clip("fx", "build", "Build sweep and chants", 40, 8, "audio"),
                _clip("fx", "final-impact", "Final impact", 48, 1, "audio"),
                _clip("fx", "outro", "Outro air", 64, 8, "audio"),
            ],
            "effects": [
                {"id": "eq", "name": "Air EQ", "active": True, "amount": 0.62},
                {"id": "reverb", "name": "Wide Hall", "active": True, "amount": 0.54},
                {"id": "transit", "name": "Transit Macro", "active": True, "amount": 0.44},
            ],
        },
        {
            "id": "guitar-bass",
            "name": "Muted Guitar Pluck",
            "instrument": "Palm Pluck",
            "gain": 0.62,
            "pan": -0.06,
            "steps": [0, 3, 6, 10, 13],
            "clips": [
                _clip("guitar-bass", "verse", "Muted sunset guitar", 8, 8, "audio"),
                _clip("guitar-bass", "break", "Break guitar answers", 32, 8, "audio"),
                _clip("guitar-bass", "build", "Build guitar bounce", 40, 8, "audio"),
            ],
            "effects": [
                {"id": "amp", "name": "Clean Amp", "active": True, "amount": 0.30},
                {"id": "lowpass", "name": "Palm Lowpass", "active": True, "amount": 0.44},
                {"id": "delay", "name": "Slap Delay", "active": True, "amount": 0.28},
            ],
        },
        {
            "id": "hat-ride",
            "name": "Hat/Ride Motion",
            "instrument": "Trap Hat Grid",
            "gain": 0.48,
            "pan": 0.12,
            "steps": [1, 3, 5, 7, 9, 11, 13, 15],
            "clips": [
                _clip("hat-ride", "hook", "Hook shaker hats", 16, 16, "audio"),
                _clip("hat-ride", "final", "Final 16th hats + ride", 48, 16, "audio"),
            ],
            "effects": [
                {"id": "bright-eq", "name": "Bright EQ", "active": True, "amount": 0.52},
                {"id": "human", "name": "Velocity Humanize", "active": True, "amount": 0.48},
            ],
        },
        {
            "id": "frozen-build-bass",
            "name": "Build 808 Print",
            "instrument": "Rendered Build 808",
            "gain": 0.64,
            "pan": 0.0,
            "steps": [0, 6, 10],
            "clips": [_clip("frozen-build-bass", "build", "CPU-saved build 808", 40, 8, "audio")],
            "effects": [
                {"id": "duck", "name": "Kick Sidechain", "active": True, "amount": 0.52},
                {"id": "low-cut", "name": "Low Cut EQ", "active": True, "amount": 0.38},
            ],
        },
        {
            "id": "filter-automation",
            "name": "Filter Glow",
            "instrument": "Build Filter Automation",
            "gain": 0.54,
            "pan": 0.0,
            "steps": [0],
            "clips": [_clip("filter-automation", "build", "Rising filter glow", 40, 8, "automation")],
            "effects": [
                {"id": "cutoff", "name": "Cutoff Automation", "active": True, "amount": 0.92},
                {"id": "transit", "name": "Endless Smile Macro", "active": True, "amount": 0.50},
            ],
        },
        {
            "id": "crowd-sidechain",
            "name": "Crowd/Air Duck",
            "instrument": "Sidechained Crowd Bed",
            "gain": 0.50,
            "pan": 0.0,
            "steps": [0, 4, 8, 12],
            "clips": [
                _clip("crowd-sidechain", "hook", "Hook crowd shimmer", 16, 16, "audio"),
                _clip("crowd-sidechain", "final", "Final crowd lift", 48, 16, "audio"),
            ],
            "effects": [
                {"id": "kickduck", "name": "Kick Sidechain", "active": True, "amount": 0.78},
                {"id": "wide", "name": "Stereo Crowd Spread", "active": True, "amount": 0.68},
            ],
        },
        {
            "id": "lead-double",
            "name": "Hook Double",
            "instrument": "Octave Pluck Double",
            "gain": 0.64,
            "pan": 0.0,
            "steps": [0, 2, 5, 7, 10, 12, 15],
            "clips": [
                _clip("lead-double", "hook", "Wide hook double", 16, 16, "audio"),
                _clip("lead-double", "final", "Final octave answer", 48, 16, "audio"),
            ],
            "effects": [
                {"id": "low-cut", "name": "Low Cut EQ", "active": True, "amount": 0.76},
                {"id": "micro-delay", "name": "Micro Delay", "active": True, "amount": 0.38},
                {"id": "wide", "name": "Stereo Widener", "active": True, "amount": 0.56},
            ],
        },
        {
            "id": "clap-stack",
            "name": "Snap/Clap Stack",
            "instrument": "Layered Clap Stack",
            "gain": 0.52,
            "pan": 0.0,
            "steps": [4, 12],
            "clips": [
                _clip("clap-stack", "verse", "Verse snaps", 8, 8, "audio"),
                _clip("clap-stack", "hook", "Hook clap stack", 16, 16, "audio"),
                _clip("clap-stack", "build", "Build clap roll", 40, 8, "audio"),
                _clip("clap-stack", "final", "Final clap stack", 48, 16, "audio"),
            ],
            "effects": [
                {"id": "transient", "name": "Transient Shaper", "active": True, "amount": 0.50},
                {"id": "room", "name": "Short Room", "active": True, "amount": 0.36},
            ],
        },
        {
            "id": "ghost-sidechain",
            "name": "Ghost Sidechain",
            "instrument": "Muted Key Trigger",
            "gain": 0.14,
            "pan": 0.0,
            "steps": [0, 6, 10, 13],
            "clips": [
                _clip("ghost-sidechain", "hook", "Hook ghost trigger", 16, 16, "audio"),
                _clip("ghost-sidechain", "build", "Build ghost trigger", 40, 8, "audio"),
                _clip("ghost-sidechain", "final", "Final ghost trigger", 48, 16, "audio"),
            ],
            "effects": [
                {"id": "key-out", "name": "Sidechain Key Output", "active": True, "amount": 1.0},
                {"id": "trim", "name": "Monitor Trim", "active": True, "amount": 0.18},
            ],
        },
        {
            "id": "ear-candy",
            "name": "Sparkle Fills",
            "instrument": "Bells, Reverse, Tags",
            "gain": 0.62,
            "pan": 0.0,
            "steps": [3, 7, 11, 15],
            "clips": [
                _clip("ear-candy", "intro", "Intro glass flecks", 0, 8, "audio"),
                _clip("ear-candy", "pre", "Pre-hook sparkles", 14, 2, "audio"),
                _clip("ear-candy", "hook", "Hook answer candy", 16, 16, "audio"),
                _clip("ear-candy", "build", "Build stereo candy", 40, 8, "audio"),
                _clip("ear-candy", "final", "Final hook candy", 48, 16, "audio"),
            ],
            "effects": [
                {"id": "highpass", "name": "Highpass EQ", "active": True, "amount": 0.78},
                {"id": "delay", "name": "Tempo Delay", "active": True, "amount": 0.44},
                {"id": "plate", "name": "Shimmer Plate", "active": True, "amount": 0.50},
                {"id": "spread", "name": "Stereo Spread", "active": True, "amount": 0.62},
            ],
        },
    ]

    notes: list[dict[str, object]] = []
    hook_notes = [
        [(0.00, 0.42, 71), (0.50, 0.38, 74), (1.00, 0.56, 76), (1.75, 0.32, 79), (2.20, 0.42, 76), (2.80, 0.58, 74)],
        [(0.00, 0.42, 69), (0.48, 0.36, 71), (0.96, 0.44, 74), (1.58, 0.38, 76), (2.28, 0.78, 71)],
        [(0.00, 0.42, 67), (0.50, 0.38, 71), (1.00, 0.56, 74), (1.72, 0.34, 76), (2.22, 0.38, 74), (2.78, 0.62, 71)],
        [(0.00, 0.38, 66), (0.50, 0.36, 69), (0.98, 0.38, 71), (1.52, 0.38, 74), (2.18, 0.72, 69), (3.12, 0.30, 71)],
    ]
    for bar_offset in range(8):
        for onset, dur, note in hook_notes[bar_offset % 4]:
            notes.append({
                "id": f"la-hook-{bar_offset}-{onset:.2f}",
                "beat": bar_offset * 4 + onset,
                "duration": dur,
                "note": note,
                "velocity": 0.86,
                "color": TRACK_COLORS["lead"],
            })

    recipe = [
        {"id": "la-feel", "section": "Foundation", "label": "2016 LA bounce palette", "detail": "The session is rebuilt around a 104 BPM tropical-trap pocket with warm 808s, snaps, airy pads, guitar plucks, vocal-chop hooks, and wide crowd air.", "status": "implemented", "trackIds": ["drums", "bass", "chords", "lead"]},
        {"id": "bittersweet-key", "section": "Foundation", "label": "Bittersweet major/minor lift", "detail": "E minor / G major voicings keep the track sunny but slightly emotional, with 7ths and 9ths for the heavenly top end.", "status": "implemented", "trackIds": ["chords", "lead"]},
        {"id": "sunset-drums", "section": "Verse", "label": "Dancehall-pop drum pocket", "detail": "Kicks, rim clicks, snaps, shakers, and claps are spaced to feel loose and expensive instead of over-packed.", "status": "implemented", "trackIds": ["drums", "clap-stack", "hat-ride"]},
        {"id": "velvet-808", "section": "Verse", "label": "Velvet 808 bounce", "detail": "Saturated low notes and short pitch slides create the Black Beatles / radio-trap low-end movement without crowding the hook.", "status": "implemented", "trackIds": ["bass", "ghost-sidechain"]},
        {"id": "guitar-pluck", "section": "Verse", "label": "Muted guitar pluck answers", "detail": "Palm-muted plucks give the verse the breezy pocket and leave room for the hook to arrive.", "status": "implemented", "trackIds": ["guitar-bass"]},
        {"id": "heaven-pad", "section": "Intro", "label": "Heaven pad intro", "detail": "Long air-pad voicings and bell flecks set the emotional color before drums enter.", "status": "implemented", "trackIds": ["chords", "ear-candy", "fx"]},
        {"id": "vocal-hook", "section": "Drop", "label": "Vocal-chop lead hook", "detail": "The main hook uses a chopped-vocal style synth, a pluck double, and ping-pong delay throws for a polished pop-EDM topline feel.", "status": "implemented", "trackIds": ["lead", "lead-double"]},
        {"id": "hook-responses", "section": "Drop", "label": "Call-and-response hook fills", "detail": "Sparkle fills, bell answers, reverse tails, and downlifters mark the hook transitions so the arrangement feels intentional.", "status": "implemented", "trackIds": ["ear-candy", "fx"]},
        {"id": "sidechain-bed", "section": "Mix", "label": "Musical sidechain pump", "detail": "Pads, hooks, crowd air, and filter sweeps are ducked around the kick for a modern bounce while the drums stay clean.", "status": "implemented", "trackIds": ["ghost-sidechain", "chords", "crowd-sidechain"]},
        {"id": "build", "section": "Build", "label": "Eight-bar lift", "detail": "The build stacks clap rolls, 808 answers, rising filter glow, risers, and hook teasers before the final hook hits.", "status": "implemented", "trackIds": ["drums", "clap-stack", "frozen-build-bass", "filter-automation", "lead"]},
        {"id": "final-hook", "section": "Drop", "label": "Full second hook", "detail": "The second hook adds faster hat motion, ride accents, more crowd air, octave answers, and extra ear candy for an 80-percent production-ready lift.", "status": "implemented", "trackIds": ["hat-ride", "lead-double", "crowd-sidechain", "ear-candy"]},
        {"id": "mix-balance", "section": "Mix", "label": "Production balance pass", "detail": "Stems are gain-staged through soft clipping, with controlled sub, brighter lead shelves, and separate clap/hat buses for later finishing.", "status": "implemented", "trackIds": ["drums", "bass", "lead", "clap-stack", "hat-ride"]},
    ]

    controls = {
        spec["id"]: {
            "gain": spec["gain"],
            "pan": spec["pan"],
            "mute": False,
            "solo": False,
            "arm": False,
            "sendA": 0.18 if spec["id"] in {"lead", "lead-double", "ear-candy", "chords"} else 0.08,
            "sendB": 0.12 if spec["id"] in {"fx", "crowd-sidechain", "ear-candy"} else 0.04,
        }
        for spec in track_specs
    }

    project_paths = [ROOT / "data" / "projects" / "neon-solitude.neon.json", ROOT / "public" / "projects" / "neon-solitude.neon.json"]
    for path in project_paths:
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
        else:
            raw = {
                "format": "neon-studio-project",
                "formatVersion": 1,
                "portable": True,
                "id": "neon-solitude",
                "name": "Neon Solitude",
                "createdAt": now,
                "snapshot": {},
            }
        snapshot = raw.get("snapshot", {})
        raw.update({
            "format": "neon-studio-project",
            "formatVersion": 1,
            "portable": True,
            "assetMode": "external",
            "id": "neon-solitude",
            "name": "Neon Solitude",
            "description": "A warmer LA Mix rebuilt as original 2016-inspired tropical-trap/pop EDM.",
            "keyCenter": "E minor / G major",
            "updatedAt": now,
            "assets": assets,
        })
        snapshot.update({
            "version": 3,
            "bpm": BPM,
            "swing": 26,
            "snap": "1/8",
            "loopEnabled": True,
            "loopStartBar": 16,
            "loopEndBar": 32,
            "tracks": [
                {
                    "id": spec["id"],
                    "name": spec["name"],
                    "kind": "audio",
                    "file": f"/api/audio/{asset_files[spec['id']]}",
                    "color": TRACK_COLORS[spec["id"]],
                    "gain": spec["gain"],
                    "pan": spec["pan"],
                    "steps": spec["steps"],
                    "instrument": spec["instrument"],
                    "clips": spec["clips"],
                    "effects": spec["effects"],
                }
                for spec in track_specs
            ],
            "controls": controls,
            "notes": notes,
            "selectedTrackId": "lead",
            "selectedClipId": "lead-hook",
            "activeView": "playlist",
            "patternIndex": 1,
            "arrangementMode": "song",
            "recipe": recipe,
        })
        raw["snapshot"] = snapshot
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")


def render() -> None:
    EXPORTS.mkdir(exist_ok=True)
    MIDI_DIR.mkdir(exist_ok=True)

    stems = {
        "drums": stereo_buffer(),
        "bass": stereo_buffer(),
        "chords": stereo_buffer(),
        "lead_and_plucks": stereo_buffer(),
        "fx": stereo_buffer(),
        "guitar_bass": stereo_buffer(),
        "hat_ride": stereo_buffer(),
        "frozen_build_bass": stereo_buffer(),
        "filter_automation": stereo_buffer(),
        "crowd_sidechain": stereo_buffer(),
        "lead_double": stereo_buffer(),
        "clap_stack": stereo_buffer(),
        "ghost_sidechain": stereo_buffer(),
        "ear_candy": stereo_buffer(),
    }

    midi_chords: list[tuple[float, float, int, int]] = []
    midi_bass: list[tuple[float, float, int, int]] = []
    midi_lead: list[tuple[float, float, int, int]] = []
    midi_plucks: list[tuple[float, float, int, int]] = []
    midi_drums: list[tuple[float, float, int, int]] = []
    midi_guitar: list[tuple[float, float, int, int]] = []
    midi_hat: list[tuple[float, float, int, int]] = []
    midi_double: list[tuple[float, float, int, int]] = []
    midi_clap: list[tuple[float, float, int, int]] = []

    progression = [
        {"name": "Em9", "notes": [52, 55, 59, 62, 67], "root": 28},
        {"name": "Cmaj9", "notes": [48, 52, 55, 59, 62], "root": 36},
        {"name": "G6/9", "notes": [43, 47, 50, 55, 59, 64], "root": 31},
        {"name": "D6sus", "notes": [50, 54, 57, 62, 66], "root": 38},
    ]

    def chord_for_bar(bar: int) -> dict[str, object]:
        return progression[(bar // 2) % len(progression)]

    # Airy harmonic bed.
    for bar in range(0, 72, 2):
        chord = chord_for_bar(bar)
        if 16 <= bar < 32:
            bright, gain = 0.70, 0.073
        elif 48 <= bar < 64:
            bright, gain = 0.78, 0.081
        elif 40 <= bar < 48:
            lift = (bar - 40) / 8.0
            bright, gain = 0.42 + lift * 0.35, 0.060 + lift * 0.020
        elif bar >= 64:
            bright, gain = 0.36, 0.060 * max(0.22, 1.0 - (bar - 64) / 8.0)
        else:
            bright, gain = 0.44, 0.065
        for idx, note in enumerate(chord["notes"]):
            schedule_note(
                stems["chords"],
                midi_chords,
                synth_heaven_pad,
                bar_beat(bar),
                7.6,
                int(note),
                68,
                gain,
                pan=-0.58 + idx * 0.22,
                audio_extra_beats=0.65,
                bright=bright,
            )

    # Sidechained hook chord flickers.
    for bar in list(range(16, 32)) + list(range(48, 64)):
        chord = chord_for_bar(bar)
        for onset, dur in [(0.0, 0.52), (1.48, 0.42), (2.50, 0.44), (3.25, 0.38)]:
            for idx, note in enumerate(list(chord["notes"])[1:]):
                schedule_note(
                    stems["chords"],
                    midi_chords,
                    synth_supersaw,
                    bar_beat(bar, onset),
                    dur,
                    int(note),
                    88,
                    0.055,
                    pan=-0.48 + idx * 0.28,
                    audio_extra_beats=0.18,
                    bright=0.72,
                    stab=True,
                )

    # Muted guitar and tropical plucks in the verses.
    guitar_rhythm = [(0.0, 0.34), (0.74, 0.28), (1.50, 0.36), (2.50, 0.30), (3.25, 0.34)]
    for bar in list(range(8, 16)) + list(range(32, 40)) + list(range(40, 48)):
        root = int(chord_for_bar(bar)["root"]) + 12
        for idx, (onset, dur) in enumerate(guitar_rhythm):
            schedule_note(
                stems["guitar_bass"],
                midi_guitar,
                synth_guitar_pluck,
                bar_beat(bar, onset),
                dur,
                root + (7 if idx in {2, 4} else 0),
                73,
                0.105 if bar < 40 else 0.087,
                pan=-0.22 if idx % 2 else 0.18,
                audio_extra_beats=0.04,
            )

    arp_pattern = [0, 2, 4, 5, 4, 2, 1, 2]
    for section_start, section_end, gain in [(4, 16, 0.055), (32, 40, 0.050), (40, 48, 0.048), (64, 70, 0.040)]:
        for bar in range(section_start, section_end):
            chord = chord_for_bar(bar)
            source_notes = list(chord["notes"]) + [list(chord["notes"])[-1] + 12]
            for step, arp_index in enumerate(arp_pattern):
                note = int(source_notes[arp_index % len(source_notes)]) + 12
                schedule_note(
                    stems["lead_and_plucks"],
                    midi_plucks,
                    synth_la_pluck,
                    bar_beat(bar, step * 0.5),
                    0.30,
                    note,
                    68,
                    gain,
                    pan=-0.34 if step % 2 else 0.30,
                    audio_extra_beats=0.10,
                    tone=0.62,
                )

    # Main vocal-chop hook.
    hook = [
        [(0.00, 0.42, 71), (0.50, 0.38, 74), (1.00, 0.56, 76), (1.75, 0.32, 79), (2.20, 0.42, 76), (2.80, 0.58, 74)],
        [(0.00, 0.42, 69), (0.48, 0.36, 71), (0.96, 0.44, 74), (1.58, 0.38, 76), (2.28, 0.78, 71)],
        [(0.00, 0.42, 67), (0.50, 0.38, 71), (1.00, 0.56, 74), (1.72, 0.34, 76), (2.22, 0.38, 74), (2.78, 0.62, 71)],
        [(0.00, 0.38, 66), (0.50, 0.36, 69), (0.98, 0.38, 71), (1.52, 0.38, 74), (2.18, 0.72, 69), (3.12, 0.30, 71)],
    ]

    def add_hook(start_bar: int, bars: int, gain: float, final: bool = False, soft: bool = False) -> None:
        for bar_offset in range(bars):
            for onset, dur, note in hook[bar_offset % 4]:
                note_out = note + (12 if final and bar_offset >= 8 else 0)
                if final and bar_offset % 8 == 7 and onset >= 2.0:
                    note_out += 2
                schedule_note(
                    stems["lead_and_plucks"],
                    midi_lead,
                    synth_vocal_chop,
                    bar_beat(start_bar + bar_offset, onset),
                    dur,
                    note_out,
                    96 if not soft else 72,
                    gain,
                    pan=0.08 if int(onset * 10 + bar_offset) % 2 else -0.08,
                    audio_extra_beats=0.08,
                    vowel=(bar_offset % 4) / 3.0,
                )
                if not soft and (onset < 2.3 or final):
                    schedule_note(
                        stems["lead_double"],
                        midi_double,
                        synth_la_pluck,
                        bar_beat(start_bar + bar_offset, onset + 0.01),
                        max(0.22, dur * 0.85),
                        note_out + 12,
                        82,
                        gain * (0.52 if final else 0.44),
                        pan=0.42 if int(onset * 10 + bar_offset) % 2 else -0.42,
                        audio_extra_beats=0.10,
                        tone=0.88,
                    )

    add_hook(16, 16, 0.150, final=False)
    add_hook(32, 8, 0.052, soft=True)
    add_hook(40, 8, 0.043, soft=True)
    add_hook(48, 16, 0.162, final=True)

    # 808/sub movement.
    bass_pattern = [(0.0, 0.95, 0), (1.48, 0.44, 0), (2.50, 0.72, 0), (3.28, 0.34, 12)]
    for bar in list(range(8, 16)) + list(range(16, 32)) + list(range(32, 40)) + list(range(48, 64)):
        root = int(chord_for_bar(bar)["root"])
        section_gain = 0.115 if bar < 16 or 32 <= bar < 40 else 0.175
        for onset, dur, add_note in bass_pattern:
            slide = root + add_note + (2 if onset > 3.0 and bar % 4 == 3 else 0)
            add_808(
                stems["bass"],
                midi_bass,
                bar_beat(bar, onset),
                dur,
                root + add_note,
                86 if section_gain < 0.14 else 108,
                section_gain,
                slide_to=slide if add_note else None,
            )
    for bar in range(40, 48):
        root = int(chord_for_bar(bar)["root"])
        lift = (bar - 40) / 8.0
        for onset, dur in [(0.0, 0.80), (1.50, 0.38), (2.50, 0.52), (3.34, 0.30)]:
            add_808(stems["frozen_build_bass"], midi_bass, bar_beat(bar, onset), dur, root, 82 + int(lift * 22), 0.120 + lift * 0.045, slide_to=root + 12 if onset > 3.0 else None)

    # Build filter glow and transition macro lane.
    for bar in range(40, 48):
        root = int(chord_for_bar(bar)["root"]) + 24
        lift = (bar - 40) / 8.0
        add_mono(stems["filter_automation"], beat_to_seconds(bar_beat(bar)), filter_sweep(4 * BEAT, note_to_freq(root)), gain=0.18 + lift * 0.08, pan=0.0)
    add_mono(stems["filter_automation"], beat_to_seconds(bar_beat(47, 2.0)), riser(2 * BEAT, 700, 2400), gain=0.34, pan=0.0)

    # Drums and percussion.
    k = kick()
    s = snare(False)
    c = snare(True)
    h = hat(False)
    oh = hat(True)
    rm = rim()
    sh = shaker()
    cr = crash()
    gp = ghost_pulse()
    kick_patterns = {
        "verse": [0.0, 1.48, 2.72],
        "hook": [0.0, 0.74, 1.48, 2.50, 3.26],
        "build": [0.0, 2.0],
    }

    def add_kick(bar: int, beat: float, gain: float) -> None:
        add_mono(stems["drums"], beat_to_seconds(bar_beat(bar, beat)), k, gain=gain)
        add_mono(stems["ghost_sidechain"], beat_to_seconds(bar_beat(bar, beat)), gp, gain=0.38)
        midi_drums.append((bar_beat(bar, beat), 0.18, 36, int(92 + gain * 18)))

    for bar in range(4, 8):
        for b in [1.0, 3.0]:
            add_mono(stems["clap_stack"], beat_to_seconds(bar_beat(bar, b)), rm, gain=0.44, pan=-0.10 if b < 2 else 0.12)
            midi_clap.append((bar_beat(bar, b), 0.10, 37, 62))
        for step in range(4):
            add_mono(stems["hat_ride"], beat_to_seconds(bar_beat(bar, step + 0.50)), sh, gain=0.26, pan=0.24)
            midi_hat.append((bar_beat(bar, step + 0.50), 0.06, 42, 44))

    for bar in range(8, 16):
        for b in kick_patterns["verse"]:
            add_kick(bar, b, 0.62)
        for b in [1.0, 3.0]:
            add_mono(stems["drums"], beat_to_seconds(bar_beat(bar, b)), rm, gain=0.42, pan=-0.12)
            add_mono(stems["clap_stack"], beat_to_seconds(bar_beat(bar, b + 0.012)), c, gain=0.22, pan=0.18)
            midi_drums.append((bar_beat(bar, b), 0.10, 37, 66))
            midi_clap.append((bar_beat(bar, b), 0.12, 39, 58))
        for step in range(8):
            swing_offset = 0.025 if step % 2 else 0.0
            add_mono(stems["hat_ride"], beat_to_seconds(bar_beat(bar, step * 0.5 + swing_offset)), sh, gain=0.30 + 0.08 * (step % 2), pan=0.30 if step % 2 else -0.18)
            midi_hat.append((bar_beat(bar, step * 0.5 + swing_offset), 0.06, 42, 48 + step % 2 * 8))

    for bar in list(range(16, 32)) + list(range(48, 64)):
        final = bar >= 48
        for b in kick_patterns["hook"]:
            add_kick(bar, b, 0.88 if not final else 0.92)
        for b in [1.0, 3.0]:
            add_mono(stems["drums"], beat_to_seconds(bar_beat(bar, b)), s, gain=0.55, pan=0.0)
            add_mono(stems["drums"], beat_to_seconds(bar_beat(bar, b + 0.018)), c, gain=0.28, pan=0.15)
            add_mono(stems["clap_stack"], beat_to_seconds(bar_beat(bar, b - 0.010)), rm, gain=0.30, pan=-0.22)
            add_mono(stems["clap_stack"], beat_to_seconds(bar_beat(bar, b + 0.022)), c, gain=0.48, pan=0.22)
            midi_drums.append((bar_beat(bar, b), 0.15, 38, 98))
            midi_clap.append((bar_beat(bar, b), 0.15, 39, 90))
        for step in range(8):
            add_mono(stems["hat_ride"], beat_to_seconds(bar_beat(bar, step * 0.5)), h if final else sh, gain=0.34 + 0.10 * (step % 2), pan=0.30 if step % 2 else -0.22)
            midi_hat.append((bar_beat(bar, step * 0.5), 0.06, 42, 54 + step % 2 * 12))
        if final:
            for step in range(16):
                if step % 4 in [1, 3] or bar % 4 == 3:
                    add_mono(stems["hat_ride"], beat_to_seconds(bar_beat(bar, step * 0.25)), h, gain=0.23, pan=-0.34 if step % 2 else 0.32)
                    midi_hat.append((bar_beat(bar, step * 0.25), 0.05, 42, 48 + step % 4 * 4))
        if bar in [16, 24, 48, 56]:
            add_mono(stems["drums"], beat_to_seconds(bar_beat(bar)), cr, gain=0.58, pan=-0.18)
            add_mono(stems["fx"], beat_to_seconds(bar_beat(bar)), impact(), gain=0.54, pan=0.0)
            midi_drums.append((bar_beat(bar), 1.0, 49, 86))
        if final and bar >= 56:
            for b in [0.0, 2.0]:
                add_mono(stems["hat_ride"], beat_to_seconds(bar_beat(bar, b)), ride(), gain=0.34, pan=-0.26)
                midi_hat.append((bar_beat(bar, b), 0.20, 51, 72))

    for bar in range(32, 40):
        for b in [0.0, 2.72]:
            add_kick(bar, b, 0.46)
        add_mono(stems["clap_stack"], beat_to_seconds(bar_beat(bar, 3.0)), c, gain=0.22, pan=0.18)

    for bar in range(40, 48):
        lift = (bar - 40) / 8.0
        for b in kick_patterns["build"]:
            add_kick(bar, b, 0.54 + 0.15 * lift)
        density = 0.5 if bar < 44 else 0.25
        steps = int(4 / density)
        for step in range(steps):
            b = step * density
            g = 0.18 + lift * 0.52 + (step / max(steps, 1)) * 0.12
            add_mono(stems["drums"], beat_to_seconds(bar_beat(bar, b)), s, gain=g, pan=-0.18 if step % 2 else 0.18)
            add_mono(stems["clap_stack"], beat_to_seconds(bar_beat(bar, b + 0.012)), c if step % 2 else rm, gain=g * 0.55, pan=0.22 if step % 2 else -0.22)
            midi_drums.append((bar_beat(bar, b), 0.08, 38, int(48 + lift * 52)))
            midi_clap.append((bar_beat(bar, b), 0.08, 39, int(46 + lift * 48)))
            if step % 2 == 0:
                add_mono(stems["hat_ride"], beat_to_seconds(bar_beat(bar, b)), h, gain=0.24 + lift * 0.20, pan=0.24)
                midi_hat.append((bar_beat(bar, b), 0.05, 42, int(46 + lift * 30)))

    # FX, crowd, tags, and sparkle details.
    for bar in [0, 16, 32, 40, 48, 64]:
        add_mono(stems["fx"], beat_to_seconds(bar_beat(bar)), downlifter(1.35), gain=0.22 if bar == 0 else 0.34, pan=0.20)
    add_mono(stems["fx"], beat_to_seconds(bar_beat(0)), crowd_swell(8 * 4 * BEAT), gain=0.18, pan=0.0)
    add_mono(stems["fx"], beat_to_seconds(bar_beat(14)), riser(2 * 4 * BEAT, 180, 1320), gain=0.42, pan=0.0)
    add_mono(stems["fx"], beat_to_seconds(bar_beat(40)), riser(8 * 4 * BEAT, 150, 1700), gain=0.55, pan=0.0)
    add_mono(stems["fx"], beat_to_seconds(bar_beat(47, 3.68)), c, gain=0.78, pan=0.0)
    add_mono(stems["fx"], beat_to_seconds(bar_beat(40)), chain_noise(8 * 4 * BEAT), gain=0.36, pan=-0.20)
    for start_bar, gain in [(16, 0.34), (48, 0.48)]:
        crowd = crowd_swell(16 * 4 * BEAT)
        add_mono(stems["crowd_sidechain"], beat_to_seconds(bar_beat(start_bar)), crowd, gain=gain, pan=0.0)
    for bar in [7, 15, 31, 39, 47, 63]:
        add_mono(stems["ear_candy"], beat_to_seconds(bar_beat(bar, 3.25)), riser(0.65 * BEAT, 480, 2200), gain=0.24, pan=-0.38)
        add_mono(stems["ear_candy"], beat_to_seconds(bar_beat(bar, 3.62)), downlifter(0.55), gain=0.20, pan=0.38)
    for bar in [0, 4, 14, 18, 22, 30, 46, 50, 54, 58, 62]:
        chord = chord_for_bar(bar)
        for idx, note in enumerate(list(chord["notes"])[-3:]):
            add_mono(stems["ear_candy"], beat_to_seconds(bar_beat(bar, 0.25 + idx * 0.36)), synth_bell(note_to_freq(int(note) + 24), 0.45 * BEAT), gain=0.075, pan=-0.42 + idx * 0.42)

    # Mix processing.
    for name, amount, release in [
        ("chords", 0.38, 0.25),
        ("bass", 0.22, 0.18),
        ("lead_and_plucks", 0.18, 0.20),
        ("lead_double", 0.30, 0.21),
        ("guitar_bass", 0.16, 0.15),
        ("frozen_build_bass", 0.28, 0.18),
        ("filter_automation", 0.44, 0.24),
        ("crowd_sidechain", 0.62, 0.30),
        ("ear_candy", 0.24, 0.24),
    ]:
        apply_ducking(stems[name], amount=amount, release=release)
    add_delay(stems["lead_and_plucks"], delay_beats=0.75, feedback=0.42, wet=0.26, repeats=5)
    add_delay(stems["lead_double"], delay_beats=0.75, feedback=0.34, wet=0.20, repeats=4)
    add_delay(stems["guitar_bass"], delay_beats=0.50, feedback=0.24, wet=0.12, repeats=3)
    add_delay(stems["chords"], delay_beats=1.50, feedback=0.28, wet=0.10, repeats=3)
    add_delay(stems["fx"], delay_beats=1.00, feedback=0.28, wet=0.16, repeats=4)
    add_delay(stems["ear_candy"], delay_beats=0.50, feedback=0.46, wet=0.28, repeats=5)

    fade_len = int(2.0 * SR)
    fade = np.linspace(0.0, 1.0, fade_len, dtype=np.float32)
    for stem in stems.values():
        stem[:fade_len] *= fade[:, None]
        stem[-fade_len:] *= fade[::-1, None]

    stem_gains = {
        "drums": 0.82,
        "bass": 0.96,
        "chords": 1.06,
        "lead_and_plucks": 1.18,
        "fx": 0.58,
        "guitar_bass": 0.66,
        "hat_ride": 0.54,
        "frozen_build_bass": 0.68,
        "filter_automation": 0.54,
        "crowd_sidechain": 0.54,
        "lead_double": 0.74,
        "clap_stack": 0.64,
        "ghost_sidechain": 0.12,
        "ear_candy": 0.70,
    }
    mix = np.zeros_like(stems["drums"])
    for name, stem in stems.items():
        mix += stem * stem_gains[name]
    mix = soft_clip(mix, drive=1.22) * 0.91

    write_wav(EXPORTS / "neon_solitude_full_mix.wav", mix)
    for name, stem in stems.items():
        write_wav(EXPORTS / f"neon_solitude_{name}.wav", soft_clip(stem * stem_gains[name], drive=1.10) * 0.90)

    arrangement_tracks = [
        ("Heaven Pad", 0, 89, midi_chords),
        ("Velvet 808", 1, 38, midi_bass),
        ("Vocal Hook", 2, 80, midi_lead),
        ("Tropical Plucks", 3, 12, midi_plucks),
        ("Sunset Drums", 9, None, midi_drums),
        ("Muted Guitar", 4, 25, midi_guitar),
        ("Hat Ride", 9, None, midi_hat),
        ("Hook Double", 5, 82, midi_double),
        ("Snap Clap", 9, None, midi_clap),
    ]
    write_midi(MIDI_DIR / "neon_solitude_arrangement.mid", arrangement_tracks)
    write_midi(MIDI_DIR / "neon_solitude_chords.mid", [arrangement_tracks[0]])
    write_midi(MIDI_DIR / "neon_solitude_bass.mid", [arrangement_tracks[1]])
    write_midi(MIDI_DIR / "neon_solitude_lead.mid", [arrangement_tracks[2]])
    write_midi(MIDI_DIR / "neon_solitude_plucks.mid", [arrangement_tracks[3]])
    write_midi(MIDI_DIR / "neon_solitude_drums.mid", [arrangement_tracks[4]])
    write_midi(MIDI_DIR / "neon_solitude_guitar_bass.mid", [arrangement_tracks[5]])
    write_midi(MIDI_DIR / "neon_solitude_hat_ride.mid", [arrangement_tracks[6]])
    write_midi(MIDI_DIR / "neon_solitude_lead_double.mid", [arrangement_tracks[7]])
    write_midi(MIDI_DIR / "neon_solitude_clap_stack.mid", [arrangement_tracks[8]])

    update_neon_project_files()

    notes = f"""Neon Solitude - LA Mix production package

Tempo: {BPM} BPM
Key center: E minor / G major
Length: {TOTAL_BARS} bars, {TOTAL_SECONDS:.1f} seconds including tail

This pass rebuilds the current project as an original 2016-inspired LA
tropical-trap/pop EDM record: warm 808 bounce, loose snaps, air pads, muted
guitar plucks, vocal-chop hook layers, crowd shimmer, and transition candy.

Generated assets:
- exports/neon_solitude_full_mix.wav
- exports/neon_solitude_*.wav stems
- midi/neon_solitude_arrangement.mid and part MIDI files
- data/projects/neon-solitude.neon.json
- public/projects/neon-solitude.neon.json
"""
    (ROOT / "README.md").write_text(notes, encoding="utf-8")


if __name__ == "__main__":
    render()
