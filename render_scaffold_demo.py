#!/usr/bin/env python3
from __future__ import annotations

"""
Renderer scaffold for Scaffold Demo.

This file was scaffolded from a transcript-driven Songlab session.
It is not a finished renderer, but it already carries the project structure:
- transcript-derived section plan
- track layout from the scaffolded .neon.json
- section-specific production notes, plugin hints, and techniques

Edit this file when turning the scaffold into a real render implementation.

Primary inputs:
- data/projects/scaffold-demo.neon.json
- factory/projects/scaffold-demo.neon.json
- songlab/projects/scaffold-demo/transcript_spec.json
- songlab/projects/scaffold-demo/project_scaffold.md

Original brief:
Convert the production walkthrough for Scaffold Demo into an original Neon Studio project. Carry over the described arrangement (Intro, Verse, Build, Drop), track roles (chords, lead, bass, clap, noise, drums), and production techniques, but keep the result original and portable.

"""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RenderContext:
    stems: dict[str, np.ndarray] = field(default_factory=dict)
    exports: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


ROOT = Path(__file__).resolve().parent
PROJECT_ID = 'scaffold-demo'
PROJECT_NAME = 'Scaffold Demo'
PROJECT_PATHS = [
    ROOT / "data" / "projects" / f"{PROJECT_ID}.neon.json",
    ROOT / "factory" / "projects" / f"{PROJECT_ID}.neon.json",
]
TRANSCRIPT_SPEC_PATH = ROOT / "songlab" / "projects" / PROJECT_ID / "transcript_spec.json"
SCAFFOLD_SUMMARY_PATH = ROOT / "songlab" / "projects" / PROJECT_ID / "project_scaffold.md"
EXPORTS = ROOT / "exports"
MIDI_DIR = ROOT / "midi"

SR = 44_100
BPM = 142
BEAT = 60.0 / BPM
TOTAL_BARS = 40
TAIL_SECONDS = 4.0

TRACK_IDS = ['chords', 'lead', 'bass', 'clap-stack', 'fx', 'drums', 'guitar', 'hat-ride', 'filter-auto', 'sub']
TRACK_PLAN = [{'id': 'chords',
  'name': 'Chords',
  'instrument': 'Supersaw',
  'kind': 'audio',
  'color': '#ffd166',
  'gain': 0.92,
  'pan': -0.03,
  'steps': [0, 4, 8, 12],
  'clips': [{'name': 'Intro chords', 'startBar': 0, 'bars': 8, 'type': 'pattern'},
            {'name': 'Drop chords', 'startBar': 24, 'bars': 16, 'type': 'pattern'}],
  'effects': ['EQ Eight', 'Reverb', 'Sidechain']},
 {'id': 'lead',
  'name': 'Lead',
  'instrument': 'Square Lead',
  'kind': 'audio',
  'color': '#6fd6ff',
  'gain': 0.84,
  'pan': 0.02,
  'steps': [0, 3, 7, 10, 14],
  'clips': [{'name': 'Intro lead', 'startBar': 0, 'bars': 8, 'type': 'pattern'},
            {'name': 'Drop lead', 'startBar': 24, 'bars': 16, 'type': 'pattern'}],
  'effects': ['Ping Delay', 'Air EQ', 'Sidechain']},
 {'id': 'bass',
  'name': 'Bass',
  'instrument': 'Mid Bass',
  'kind': 'audio',
  'color': '#4ade80',
  'gain': 0.86,
  'pan': 0.0,
  'steps': [0, 6, 10, 13],
  'clips': [{'name': 'Verse bass', 'startBar': 8, 'bars': 8, 'type': 'pattern'},
            {'name': 'Drop bass', 'startBar': 24, 'bars': 16, 'type': 'pattern'}],
  'effects': ['Sidechain', 'Saturator']},
 {'id': 'clap-stack',
  'name': 'Clap Stack',
  'instrument': 'Clap Layer',
  'kind': 'audio',
  'color': '#fb7185',
  'gain': 0.72,
  'pan': 0.02,
  'steps': [4, 12],
  'clips': [{'name': 'Verse clap stack', 'startBar': 8, 'bars': 8, 'type': 'pattern'},
            {'name': 'Build clap stack', 'startBar': 16, 'bars': 8, 'type': 'pattern'}],
  'effects': ['Reverb', 'Stereo Spread']},
 {'id': 'fx',
  'name': 'FX',
  'instrument': 'Transitions',
  'kind': 'audio',
  'color': '#d78bff',
  'gain': 0.72,
  'pan': 0.0,
  'steps': [],
  'clips': [{'name': 'Intro fx', 'startBar': 0, 'bars': 8, 'type': 'audio'},
            {'name': 'Build fx', 'startBar': 16, 'bars': 8, 'type': 'audio'},
            {'name': 'Drop fx', 'startBar': 24, 'bars': 16, 'type': 'audio'}],
  'effects': ['Long Reverb', 'Stereo Spread', 'Sidechain']},
 {'id': 'drums',
  'name': 'Drums',
  'instrument': 'Sampler',
  'kind': 'audio',
  'color': '#ff8d5c',
  'gain': 0.82,
  'pan': 0.0,
  'steps': [0, 4, 8, 12],
  'clips': [{'name': 'Verse drums', 'startBar': 8, 'bars': 8, 'type': 'pattern'}],
  'effects': ['EQ Eight', 'Bus Comp']},
 {'id': 'guitar',
  'name': 'Guitar',
  'instrument': 'Muted Guitar',
  'kind': 'audio',
  'color': '#c4f1be',
  'gain': 0.74,
  'pan': -0.06,
  'steps': [0, 8],
  'clips': [{'name': 'Verse guitar', 'startBar': 8, 'bars': 8, 'type': 'pattern'}],
  'effects': ['Compressor', 'Room']},
 {'id': 'hat-ride',
  'name': 'Hat/Ride',
  'instrument': 'Trap Hat Rack',
  'kind': 'audio',
  'color': '#f4f1a3',
  'gain': 0.68,
  'pan': 0.0,
  'steps': [0, 2, 4, 6, 8, 10, 12, 14],
  'clips': [{'name': 'Verse hat/ride', 'startBar': 8, 'bars': 8, 'type': 'pattern'}],
  'effects': ['Transient Tightener']},
 {'id': 'filter-auto',
  'name': 'Filter Auto',
  'instrument': 'Automation Lane',
  'kind': 'audio',
  'color': '#7dd3fc',
  'gain': 0.0,
  'pan': 0.0,
  'steps': [],
  'clips': [{'name': 'Build filter auto', 'startBar': 16, 'bars': 8, 'type': 'pattern'}],
  'effects': ['Filter Macro']},
 {'id': 'sub',
  'name': 'Sub',
  'instrument': 'Triangle Sub',
  'kind': 'audio',
  'color': '#34d399',
  'gain': 0.9,
  'pan': 0.0,
  'steps': [0, 8],
  'clips': [{'name': 'Drop sub', 'startBar': 24, 'bars': 16, 'type': 'pattern'}],
  'effects': ['Mono Utility', 'Kick Duck', 'Sidechain']}]
TRACK_PLAN_BY_ID = {track["id"]: track for track in TRACK_PLAN}
SECTION_PLAN = [{'id': 'section-01',
  'type': 'intro',
  'label': 'Intro',
  'startBar': 0,
  'bars': 8,
  'summary': 'intro has a simple chord progression and a lead melody with white noise',
  'trackRoles': ['chords', 'lead', 'noise'],
  'trackIds': ['chords', 'lead', 'fx'],
  'plugins': [],
  'techniques': [],
  'recipeDetail': 'intro has a simple chord progression and a lead melody with white noise. '
                  'Tracks: chords, lead, fx',
  'starterDefaults': {'progression': [{'name': 'Em7', 'notes': [52, 55, 59, 62], 'root': 40},
                                      {'name': 'Cmaj7', 'notes': [48, 52, 55, 59], 'root': 36},
                                      {'name': 'Gadd9', 'notes': [43, 47, 50, 55], 'root': 31},
                                      {'name': 'Dadd9', 'notes': [50, 54, 57, 62], 'root': 38}],
                      'chordEvents': [{'beat': 0.0, 'duration': 3.7}],
                      'bassEvents': [{'beat': 0.0, 'duration': 3.85}],
                      'leadMotifKey': 'sparse',
                      'leadMotif': [[{'beat': 0.0, 'duration': 0.45, 'note': 76},
                                     {'beat': 1.02, 'duration': 0.7, 'note': 83},
                                     {'beat': 2.56, 'duration': 0.66, 'note': 76}],
                                    [{'beat': 0.0, 'duration': 0.42, 'note': 79},
                                     {'beat': 1.0, 'duration': 0.68, 'note': 83},
                                     {'beat': 2.56, 'duration': 0.72, 'note': 74}],
                                    [{'beat': 0.0, 'duration': 0.42, 'note': 83},
                                     {'beat': 1.02, 'duration': 0.68, 'note': 83},
                                     {'beat': 2.5, 'duration': 0.72, 'note': 76}],
                                    [{'beat': 0.0, 'duration': 0.4, 'note': 79},
                                     {'beat': 1.45, 'duration': 0.38, 'note': 76},
                                     {'beat': 2.1, 'duration': 0.78, 'note': 79}]],
                      'leadSoft': True,
                      'leadOctaveShift': 0,
                      'drumPattern': {'kicks': [0.0, 1.5, 2.75],
                                      'snares': [1.0, 3.0],
                                      'hats': [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5],
                                      'clapRoll': False,
                                      'hatSpacing': 0.5,
                                      'ride': False,
                                      'crashBars': []},
                      'fxProfile': {'noiseBed': True,
                                    'riser': False,
                                    'downlifter': False,
                                    'crash': False},
                      'energy': 0.85}},
 {'id': 'section-02',
  'type': 'verse',
  'label': 'Verse',
  'startBar': 8,
  'bars': 8,
  'summary': 'verse adds guitar bass and a simple trap beat with kick snare clap and hi-hat',
  'trackRoles': ['bass', 'clap', 'drums', 'guitar', 'hat', 'kick', 'snare'],
  'trackIds': ['bass', 'clap-stack', 'drums', 'guitar', 'hat-ride'],
  'plugins': [],
  'techniques': [],
  'recipeDetail': 'verse adds guitar bass and a simple trap beat with kick snare clap and hi-hat. '
                  'Tracks: bass, clap-stack, drums, guitar, hat-ride',
  'starterDefaults': {'progression': [{'name': 'Em', 'notes': [52, 55, 59, 64], 'root': 40},
                                      {'name': 'D', 'notes': [50, 54, 57, 62], 'root': 38},
                                      {'name': 'C', 'notes': [48, 52, 55, 60], 'root': 36},
                                      {'name': 'Bm', 'notes': [47, 50, 54, 59], 'root': 35}],
                      'chordEvents': [{'beat': 0.0, 'duration': 1.8},
                                      {'beat': 2.0, 'duration': 1.8}],
                      'bassEvents': [{'beat': 0.0, 'duration': 1.45},
                                     {'beat': 2.0, 'duration': 1.35}],
                      'leadMotifKey': 'sparse',
                      'leadMotif': [[{'beat': 0.0, 'duration': 0.45, 'note': 76},
                                     {'beat': 1.02, 'duration': 0.7, 'note': 83},
                                     {'beat': 2.56, 'duration': 0.66, 'note': 76}],
                                    [{'beat': 0.0, 'duration': 0.42, 'note': 79},
                                     {'beat': 1.0, 'duration': 0.68, 'note': 83},
                                     {'beat': 2.56, 'duration': 0.72, 'note': 74}],
                                    [{'beat': 0.0, 'duration': 0.42, 'note': 83},
                                     {'beat': 1.02, 'duration': 0.68, 'note': 83},
                                     {'beat': 2.5, 'duration': 0.72, 'note': 76}],
                                    [{'beat': 0.0, 'duration': 0.4, 'note': 79},
                                     {'beat': 1.45, 'duration': 0.38, 'note': 76},
                                     {'beat': 2.1, 'duration': 0.78, 'note': 79}]],
                      'leadSoft': True,
                      'leadOctaveShift': 0,
                      'drumPattern': {'kicks': [0.0, 1.5, 2.75],
                                      'snares': [1.0, 3.0],
                                      'hats': [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5],
                                      'clapRoll': False,
                                      'hatSpacing': 0.5,
                                      'ride': False,
                                      'crashBars': []},
                      'fxProfile': {'noiseBed': False,
                                    'riser': False,
                                    'downlifter': False,
                                    'crash': False},
                      'energy': 0.85}},
 {'id': 'section-03',
  'type': 'build',
  'label': 'Build',
  'startBar': 16,
  'bars': 8,
  'summary': 'build adds risers downlifters claps and a filter automation',
  'trackRoles': ['automation', 'clap', 'downlifter', 'riser'],
  'trackIds': ['filter-auto', 'clap-stack', 'fx'],
  'plugins': [],
  'techniques': ['automation', 'filtering'],
  'recipeDetail': 'build adds risers downlifters claps and a filter automation. Tracks: '
                  'filter-auto, clap-stack, fx. Techniques: automation, filtering',
  'starterDefaults': {'progression': [{'name': 'Em7', 'notes': [52, 55, 59, 62], 'root': 40},
                                      {'name': 'Cmaj7', 'notes': [48, 52, 55, 59], 'root': 36},
                                      {'name': 'Gadd9', 'notes': [43, 47, 50, 55], 'root': 31},
                                      {'name': 'Dadd9', 'notes': [50, 54, 57, 62], 'root': 38}],
                      'chordEvents': [{'beat': 0.0, 'duration': 1.7},
                                      {'beat': 2.0, 'duration': 1.7}],
                      'bassEvents': [{'beat': 0.0, 'duration': 1.35},
                                     {'beat': 2.0, 'duration': 1.35},
                                     {'beat': 3.35, 'duration': 0.32}],
                      'leadMotifKey': 'sparse',
                      'leadMotif': [[{'beat': 0.0, 'duration': 0.45, 'note': 76},
                                     {'beat': 1.02, 'duration': 0.7, 'note': 83},
                                     {'beat': 2.56, 'duration': 0.66, 'note': 76}],
                                    [{'beat': 0.0, 'duration': 0.42, 'note': 79},
                                     {'beat': 1.0, 'duration': 0.68, 'note': 83},
                                     {'beat': 2.56, 'duration': 0.72, 'note': 74}],
                                    [{'beat': 0.0, 'duration': 0.42, 'note': 83},
                                     {'beat': 1.02, 'duration': 0.68, 'note': 83},
                                     {'beat': 2.5, 'duration': 0.72, 'note': 76}],
                                    [{'beat': 0.0, 'duration': 0.4, 'note': 79},
                                     {'beat': 1.45, 'duration': 0.38, 'note': 76},
                                     {'beat': 2.1, 'duration': 0.78, 'note': 79}]],
                      'leadSoft': False,
                      'leadOctaveShift': 0,
                      'drumPattern': {'kicks': [0.0],
                                      'snares': [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5],
                                      'hats': [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5],
                                      'clapRoll': True,
                                      'hatSpacing': 0.5,
                                      'ride': False,
                                      'crashBars': []},
                      'fxProfile': {'noiseBed': False,
                                    'riser': True,
                                    'downlifter': True,
                                    'crash': False},
                      'energy': 1.05}},
 {'id': 'section-04',
  'type': 'drop',
  'label': 'Drop',
  'startBar': 24,
  'bars': 16,
  'summary': 'drop uses lead chords bass sub crashes crowd and sidechain',
  'trackRoles': ['bass', 'chords', 'crash', 'crowd', 'lead', 'sub'],
  'trackIds': ['bass', 'chords', 'fx', 'lead', 'sub'],
  'plugins': [],
  'techniques': ['sidechain'],
  'recipeDetail': 'drop uses lead chords bass sub crashes crowd and sidechain. Tracks: bass, '
                  'chords, fx, lead, sub. Techniques: sidechain',
  'starterDefaults': {'progression': [{'name': 'Em7', 'notes': [52, 55, 59, 62], 'root': 40},
                                      {'name': 'Cmaj7', 'notes': [48, 52, 55, 59], 'root': 36},
                                      {'name': 'Gadd9', 'notes': [43, 47, 50, 55], 'root': 31},
                                      {'name': 'Dadd9', 'notes': [50, 54, 57, 62], 'root': 38}],
                      'chordEvents': [{'beat': 0.0, 'duration': 0.8},
                                      {'beat': 1.5, 'duration': 0.45},
                                      {'beat': 2.0, 'duration': 0.55},
                                      {'beat': 3.0, 'duration': 0.68}],
                      'bassEvents': [{'beat': 0.0, 'duration': 0.82},
                                     {'beat': 1.5, 'duration': 0.45},
                                     {'beat': 2.0, 'duration': 0.55},
                                     {'beat': 3.0, 'duration': 0.68}],
                      'leadMotifKey': 'dense',
                      'leadMotif': [[{'beat': 0.0, 'duration': 0.45, 'note': 76},
                                     {'beat': 0.52, 'duration': 0.38, 'note': 79},
                                     {'beat': 1.02, 'duration': 0.7, 'note': 83},
                                     {'beat': 2.02, 'duration': 0.42, 'note': 79},
                                     {'beat': 2.56, 'duration': 0.66, 'note': 76}],
                                    [{'beat': 0.0, 'duration': 0.42, 'note': 79},
                                     {'beat': 0.48, 'duration': 0.38, 'note': 81},
                                     {'beat': 1.0, 'duration': 0.68, 'note': 83},
                                     {'beat': 2.04, 'duration': 0.42, 'note': 79},
                                     {'beat': 2.56, 'duration': 0.72, 'note': 74}],
                                    [{'beat': 0.0, 'duration': 0.42, 'note': 83},
                                     {'beat': 0.52, 'duration': 0.38, 'note': 84},
                                     {'beat': 1.02, 'duration': 0.68, 'note': 83},
                                     {'beat': 2.0, 'duration': 0.42, 'note': 79},
                                     {'beat': 2.5, 'duration': 0.72, 'note': 76}],
                                    [{'beat': 0.0, 'duration': 0.4, 'note': 79},
                                     {'beat': 0.46, 'duration': 0.36, 'note': 76},
                                     {'beat': 0.92, 'duration': 0.38, 'note': 74},
                                     {'beat': 1.45, 'duration': 0.38, 'note': 76},
                                     {'beat': 2.1, 'duration': 0.78, 'note': 79}]],
                      'leadSoft': False,
                      'leadOctaveShift': 0,
                      'drumPattern': {'kicks': [0.0, 1.45, 2.0, 3.05],
                                      'snares': [2.0],
                                      'hats': [0.0,
                                               0.25,
                                               0.5,
                                               0.75,
                                               1.0,
                                               1.25,
                                               1.5,
                                               1.75,
                                               2.0,
                                               2.25,
                                               2.5,
                                               2.75,
                                               3.0,
                                               3.25,
                                               3.5,
                                               3.75],
                                      'clapRoll': False,
                                      'hatSpacing': 0.25,
                                      'ride': False,
                                      'crashBars': [0]},
                      'fxProfile': {'noiseBed': False,
                                    'riser': False,
                                    'downlifter': True,
                                    'crash': True},
                      'energy': 1.25}}]
SECTION_PLAN_BY_ID = {section["id"]: section for section in SECTION_PLAN}


import math
import wave

import numpy as np


TOTAL_SECONDS = TOTAL_BARS * 4 * BEAT + TAIL_SECONDS
N_SAMPLES = int(TOTAL_SECONDS * SR)
STEM_PREFIX = PROJECT_ID.replace("-", "_")
SCAFFOLD_STEM_PREFIX = f"{STEM_PREFIX}_scaffold"
FALLBACK_PROGRESSION = [
    {"name": "Em7", "notes": [52, 55, 59, 62], "root": 40},
    {"name": "Cmaj7", "notes": [48, 52, 55, 59], "root": 36},
    {"name": "Gadd9", "notes": [43, 47, 50, 55], "root": 31},
    {"name": "Dadd9", "notes": [50, 54, 57, 62], "root": 38},
]
FALLBACK_LEAD_MOTIF = [
    [(0.00, 0.45, 76), (0.52, 0.38, 79), (1.02, 0.70, 83), (2.02, 0.42, 79), (2.56, 0.66, 76)],
    [(0.00, 0.42, 79), (0.48, 0.38, 81), (1.00, 0.68, 83), (2.04, 0.42, 79), (2.56, 0.72, 74)],
    [(0.00, 0.42, 83), (0.52, 0.38, 84), (1.02, 0.68, 83), (2.00, 0.42, 79), (2.50, 0.72, 76)],
    [(0.00, 0.40, 79), (0.46, 0.36, 76), (0.92, 0.38, 74), (1.45, 0.38, 76), (2.10, 0.78, 79)],
]


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


def add_mono(target: np.ndarray, start_seconds: float, audio: np.ndarray, gain: float = 1.0, pan: float = 0.0) -> None:
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


def adsr(n: int, attack: float = 0.01, decay: float = 0.08, sustain: float = 0.7, release: float = 0.12) -> np.ndarray:
    attack_n = max(1, int(attack * SR))
    decay_n = max(1, int(decay * SR))
    release_n = max(1, int(release * SR))
    fixed = attack_n + decay_n + release_n
    if fixed > n:
        scale = n / fixed
        attack_n = max(1, int(attack_n * scale))
        decay_n = max(1, int(decay_n * scale))
        release_n = max(1, n - attack_n - decay_n)
    sustain_n = max(0, n - attack_n - decay_n - release_n)
    env = np.concatenate([
        np.linspace(0.0, 1.0, attack_n, endpoint=False),
        np.linspace(1.0, sustain, decay_n, endpoint=False),
        np.full(sustain_n, sustain),
        np.linspace(sustain, 0.0, release_n, endpoint=True),
    ])
    if len(env) < n:
        env = np.pad(env, (0, n - len(env)))
    return env[:n].astype(np.float32)


def highpass_noise(n: int) -> np.ndarray:
    x = np.random.default_rng(1408).standard_normal(n).astype(np.float32)
    y = np.empty_like(x)
    y[0] = x[0]
    y[1:] = x[1:] - 0.94 * x[:-1]
    return y


def one_pole_lowpass(x: np.ndarray, cutoff_hz: float) -> np.ndarray:
    if cutoff_hz <= 0:
        return x.astype(np.float32, copy=False)
    rc = 1.0 / (2.0 * math.pi * cutoff_hz)
    dt = 1.0 / SR
    alpha = dt / (rc + dt)
    y = np.empty_like(x, dtype=np.float32)
    prev = 0.0
    for i, sample in enumerate(x):
        prev = prev + alpha * (float(sample) - prev)
        y[i] = prev
    return y


def saw(freq: float, dur: float, phase: float = 0.0) -> np.ndarray:
    n = max(1, int(dur * SR))
    t = np.arange(n, dtype=np.float32) / SR
    p = (freq * t + phase) % 1.0
    return (2.0 * p - 1.0).astype(np.float32)


def synth_supersaw(freq: float, dur: float, bright: float = 0.8, stab: bool = False) -> np.ndarray:
    n = max(1, int(dur * SR))
    t = np.arange(n, dtype=np.float32) / SR
    out = np.zeros(n, dtype=np.float32)
    for idx, cents in enumerate([-11.0, -5.0, 0.0, 4.0, 9.0]):
        out += saw(freq * (2.0 ** (cents / 1200.0)), dur, phase=0.11 * idx)
    out /= 5.0
    out += 0.10 * np.sin(2.0 * np.pi * freq * 0.5 * t).astype(np.float32)
    out = one_pole_lowpass(out, 1800.0 + 4200.0 * bright)
    env = adsr(n, attack=0.012 if stab else 0.06, decay=0.10, sustain=0.54 if stab else 0.76, release=0.10 if stab else 0.34)
    return (out * env).astype(np.float32)


def synth_bass(freq: float, dur: float, grit: float = 0.4) -> np.ndarray:
    n = max(1, int(dur * SR))
    t = np.arange(n, dtype=np.float32) / SR
    phase = np.cumsum(np.full(n, freq, dtype=np.float32)) / SR
    sine = np.sin(2.0 * np.pi * phase).astype(np.float32)
    sq = np.where((phase % 1.0) < 0.5, 1.0, -1.0).astype(np.float32) * grit * 0.16
    env = adsr(n, attack=0.003, decay=0.06, sustain=0.82, release=0.07)
    return (0.88 * sine + sq) * env


def synth_lead(freq: float, dur: float, soft: bool = False) -> np.ndarray:
    n = max(1, int(dur * SR))
    t = np.arange(n, dtype=np.float32) / SR
    vibrato = 1.0 + 0.003 * np.sin(2.0 * math.pi * 5.0 * t)
    phase = np.cumsum((freq * vibrato).astype(np.float32)) / SR
    sq = np.where((phase % 1.0) < 0.5, 1.0, -1.0).astype(np.float32)
    tri = (2.0 * np.abs(2.0 * (phase % 1.0) - 1.0) - 1.0).astype(np.float32)
    out = 0.56 * sq + 0.28 * tri
    out = one_pole_lowpass(out, 2600.0 if soft else 4200.0)
    env = adsr(n, attack=0.010, decay=0.07, sustain=0.62 if soft else 0.76, release=0.08)
    return out * env


def synth_pluck(freq: float, dur: float) -> np.ndarray:
    n = max(1, int(dur * SR))
    t = np.arange(n, dtype=np.float32) / SR
    out = 0.62 * np.sin(2.0 * np.pi * freq * t) + 0.24 * saw(freq * 2.0, dur)
    env = np.exp(-t * 7.5).astype(np.float32)
    return one_pole_lowpass((out * env).astype(np.float32), 2600.0)


def kick() -> np.ndarray:
    dur = 0.52
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    freq = 48.0 + 110.0 * np.exp(-t * 18.0)
    phase = np.cumsum(freq) / SR
    body = np.sin(2.0 * np.pi * phase).astype(np.float32) * np.exp(-t * 7.0)
    click = highpass_noise(n) * np.exp(-t * 80.0).astype(np.float32) * 0.06
    return (1.14 * body + click).astype(np.float32)


def snare(clap: bool = False) -> np.ndarray:
    dur = 0.42 if not clap else 0.48
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    noise = highpass_noise(n) * np.exp(-t * (14.0 if not clap else 10.0)).astype(np.float32)
    tone = np.sin(2.0 * np.pi * 190.0 * t).astype(np.float32) * np.exp(-t * 18.0) * 0.28
    return (noise * (0.46 if not clap else 0.64) + tone).astype(np.float32)


def hat(open_hat: bool = False) -> np.ndarray:
    dur = 0.18 if open_hat else 0.07
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    return (highpass_noise(n) * np.exp(-t * (11.0 if open_hat else 52.0)).astype(np.float32) * (0.18 if open_hat else 0.12)).astype(np.float32)


def crash() -> np.ndarray:
    dur = 1.8
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    return (highpass_noise(n) * np.exp(-t * 1.25).astype(np.float32) * 0.24).astype(np.float32)


def riser(dur: float, start_freq: float = 220.0, end_freq: float = 1600.0) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    freqs = np.linspace(start_freq, end_freq, n, dtype=np.float32)
    phase = np.cumsum(freqs) / SR
    tone = np.sin(2.0 * np.pi * phase).astype(np.float32)
    noise = one_pole_lowpass(highpass_noise(n), 5400.0)
    env = np.linspace(0.0, 1.0, n, dtype=np.float32) ** 1.4
    return (0.18 * tone + 0.14 * noise) * env


def downlifter(dur: float = 1.2) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    noise = highpass_noise(n) * np.exp(-t * 1.6).astype(np.float32)
    tone = np.sin(2.0 * np.pi * (380.0 - 240.0 * t / max(dur, 0.001)) * t).astype(np.float32)
    return (0.18 * noise + 0.08 * tone).astype(np.float32)


def _track_buffer(ctx: RenderContext, track_id: str) -> np.ndarray:
    key = track_id.replace("-", "_")
    if key not in ctx.stems:
        ctx.stems[key] = stereo_buffer()
    return ctx.stems[key]


def _section_defaults(section: dict) -> dict:
    return section.get("starterDefaults", {}) or {}


def _progression_for_bar(section: dict, bar: int) -> dict:
    progression = _section_defaults(section).get("progression") or FALLBACK_PROGRESSION
    return progression[bar % len(progression)]


def _lead_motif_for_section(section: dict) -> list[list[dict]]:
    return _section_defaults(section).get("leadMotif") or FALLBACK_LEAD_MOTIF


def _schedule_note(buffer: np.ndarray, start_beat: float, duration_beats: float, midi_note: int, synth, *, gain: float, pan: float = 0.0, **kwargs) -> None:
    audio = synth(note_to_freq(midi_note), duration_beats * BEAT, **kwargs)
    add_mono(buffer, beat_to_seconds(start_beat), audio, gain=gain, pan=pan)


def _starter_chords(ctx: RenderContext, section: dict, track: dict) -> None:
    buffer = _track_buffer(ctx, track["id"])
    defaults = _section_defaults(section)
    for bar in range(section["startBar"], section["startBar"] + section["bars"]):
        chord = _progression_for_bar(section, bar)
        chord_events = defaults.get("chordEvents") or [{"beat": 0.0, "duration": 3.7}]
        for event in chord_events:
            onset = float(event["beat"])
            dur = float(event["duration"])
            stab = bool(event.get("stab", section["type"] in {"drop", "second_drop"}))
            bright = float(event.get("bright", 0.55 if section["type"] == "build" else (0.84 if stab else 0.30)))
            for idx, note in enumerate(chord["notes"]):
                _schedule_note(buffer, bar_beat(bar, onset), dur, int(note), synth_supersaw, gain=track.get("gain", 0.8) * (0.10 if stab else 0.06) * float(defaults.get("energy", 1.0)), pan=-0.45 + idx * 0.30, bright=bright, stab=stab)


def _starter_bass(ctx: RenderContext, section: dict, track: dict) -> None:
    buffer = _track_buffer(ctx, track["id"])
    defaults = _section_defaults(section)
    for bar in range(section["startBar"], section["startBar"] + section["bars"]):
        root = int(_progression_for_bar(section, bar)["root"])
        bass_events = defaults.get("bassEvents") or [{"beat": 0.0, "duration": 3.85}]
        for event in bass_events:
            onset = float(event["beat"])
            dur = float(event["duration"])
            gain = track.get("gain", 0.8) * (0.20 if section["type"] in {"drop", "second_drop"} else 0.10) * float(defaults.get("energy", 1.0))
            _schedule_note(buffer, bar_beat(bar, onset), dur, root + int(event.get("octaveShift", 0)), synth_bass, gain=gain, pan=track.get("pan", 0.0), grit=float(event.get("grit", 0.46)))


def _starter_sub(ctx: RenderContext, section: dict, track: dict) -> None:
    buffer = _track_buffer(ctx, track["id"])
    defaults = _section_defaults(section)
    for bar in range(section["startBar"], section["startBar"] + section["bars"]):
        root = int(_progression_for_bar(section, bar)["root"]) - 12
        _schedule_note(buffer, bar_beat(bar), 3.85, root, synth_bass, gain=track.get("gain", 0.8) * 0.12 * float(defaults.get("energy", 1.0)), pan=0.0, grit=0.12)


def _starter_lead(ctx: RenderContext, section: dict, track: dict) -> None:
    buffer = _track_buffer(ctx, track["id"])
    defaults = _section_defaults(section)
    soft = bool(defaults.get("leadSoft", section["type"] in {"intro", "verse", "break", "outro"}))
    transpose = int(defaults.get("leadOctaveShift", 0))
    motif = _lead_motif_for_section(section)
    for local_bar, bar in enumerate(range(section["startBar"], section["startBar"] + section["bars"])):
        bar_motif = motif[local_bar % len(motif)]
        for event in bar_motif:
            onset = float(event["beat"])
            dur = float(event["duration"])
            note = int(event["note"])
            if soft and onset > 2.6 and local_bar % 2 == 0:
                continue
            _schedule_note(buffer, bar_beat(bar, onset), dur, note + transpose, synth_lead, gain=track.get("gain", 0.8) * (0.10 if not soft else 0.06) * float(defaults.get("energy", 1.0)), pan=-0.08 if (local_bar + int(onset * 10)) % 2 else 0.08, soft=soft)


def _starter_drums(ctx: RenderContext, section: dict, track: dict) -> None:
    buffer = _track_buffer(ctx, track["id"])
    defaults = _section_defaults(section)
    drum_pattern = defaults.get("drumPattern") or {}
    k = kick()
    s = snare(False)
    h = hat(False)
    for bar in range(section["startBar"], section["startBar"] + section["bars"]):
        kicks = drum_pattern.get("kicks") or [0.0, 1.5, 2.75]
        snares = drum_pattern.get("snares") or [1.0, 3.0]
        hats = drum_pattern.get("hats") or [step * 0.5 for step in range(8)]
        for beat in kicks:
            add_mono(buffer, beat_to_seconds(bar_beat(bar, float(beat))), k, gain=track.get("gain", 0.8) * 0.95 * float(defaults.get("energy", 1.0)), pan=track.get("pan", 0.0))
        for beat in snares:
            add_mono(buffer, beat_to_seconds(bar_beat(bar, float(beat))), s, gain=track.get("gain", 0.8) * 0.34 * float(defaults.get("energy", 1.0)))
        for beat in hats:
            beat_value = float(beat)
            add_mono(buffer, beat_to_seconds(bar_beat(bar, beat_value)), h, gain=0.14 + (0.05 if int(beat_value * 2) % 2 else 0.0), pan=0.22)


def _starter_clap_stack(ctx: RenderContext, section: dict, track: dict) -> None:
    buffer = _track_buffer(ctx, track["id"])
    defaults = _section_defaults(section)
    drum_pattern = defaults.get("drumPattern") or {}
    c = snare(True)
    for bar in range(section["startBar"], section["startBar"] + section["bars"]):
        beats = [step * 0.5 for step in range(8)] if drum_pattern.get("clapRoll") else (drum_pattern.get("snares") or [1.0, 3.0])
        for beat in beats:
            add_mono(buffer, beat_to_seconds(bar_beat(bar, float(beat))), c, gain=track.get("gain", 0.8) * (0.18 if drum_pattern.get("clapRoll") else 0.24) * float(defaults.get("energy", 1.0)), pan=0.18)


def _starter_hat_ride(ctx: RenderContext, section: dict, track: dict) -> None:
    buffer = _track_buffer(ctx, track["id"])
    defaults = _section_defaults(section)
    drum_pattern = defaults.get("drumPattern") or {}
    closed = hat(False)
    open_h = hat(True)
    for bar in range(section["startBar"], section["startBar"] + section["bars"]):
        spacing = float(drum_pattern.get("hatSpacing", 0.5))
        steps = int(4 / spacing)
        for step in range(steps):
            add_mono(buffer, beat_to_seconds(bar_beat(bar, step * spacing)), closed, gain=track.get("gain", 0.8) * 0.16, pan=-0.28 if step % 2 else 0.28)
        add_mono(buffer, beat_to_seconds(bar_beat(bar, 3.5)), open_h, gain=track.get("gain", 0.8) * 0.16, pan=-0.20)
        if drum_pattern.get("ride") and bar % 4 == 3:
            add_mono(buffer, beat_to_seconds(bar_beat(bar, 0.0)), open_h, gain=track.get("gain", 0.8) * 0.18, pan=0.18)
        if drum_pattern.get("crashBars") and (bar - section["startBar"]) in set(int(item) for item in drum_pattern["crashBars"]):
            add_mono(buffer, beat_to_seconds(bar_beat(bar)), crash(), gain=track.get("gain", 0.8) * 0.18, pan=0.22)


def _starter_fx(ctx: RenderContext, section: dict, track: dict) -> None:
    buffer = _track_buffer(ctx, track["id"])
    defaults = _section_defaults(section)
    fx_profile = defaults.get("fxProfile") or {}
    start_seconds = beat_to_seconds(bar_beat(section["startBar"]))
    if fx_profile.get("noiseBed"):
        add_mono(buffer, start_seconds, highpass_noise(int(section["bars"] * 4 * BEAT * SR)) * 0.05, gain=1.0, pan=0.12)
    if fx_profile.get("riser"):
        add_mono(buffer, start_seconds, riser(section["bars"] * 4 * BEAT), gain=track.get("gain", 0.8) * 0.34, pan=-0.12)
    if fx_profile.get("crash"):
        add_mono(buffer, start_seconds, crash(), gain=track.get("gain", 0.8) * 0.20, pan=0.18)
    if fx_profile.get("downlifter"):
        add_mono(buffer, beat_to_seconds(bar_beat(section["startBar"] + section["bars"] - 1, 3.2)), downlifter(), gain=track.get("gain", 0.8) * 0.18, pan=-0.18)


def _starter_guitar(ctx: RenderContext, section: dict, track: dict) -> None:
    buffer = _track_buffer(ctx, track["id"])
    for bar in range(section["startBar"], section["startBar"] + section["bars"]):
        root = int(_progression_for_bar(section, bar)["root"]) + 12
        for onset in [0.0, 0.75, 1.5, 2.0, 3.0]:
            _schedule_note(buffer, bar_beat(bar, onset), 0.30, root, synth_pluck, gain=track.get("gain", 0.8) * 0.08, pan=-0.10)


def _starter_filter_auto(ctx: RenderContext, section: dict, track: dict) -> None:
    buffer = _track_buffer(ctx, track["id"])
    add_mono(buffer, beat_to_seconds(bar_beat(section["startBar"])), riser(section["bars"] * 4 * BEAT, 180.0, 900.0), gain=track.get("gain", 0.8) * 0.12, pan=0.0)


def _starter_sample(ctx: RenderContext, section: dict, track: dict) -> None:
    buffer = _track_buffer(ctx, track["id"])
    add_mono(buffer, beat_to_seconds(bar_beat(section["startBar"])), synth_pluck(note_to_freq(72), 0.30 * BEAT), gain=track.get("gain", 0.8) * 0.08, pan=0.0)


def _render_lane_starter(ctx: RenderContext, section: dict, track: dict) -> None:
    if track["id"] == "chords":
        _starter_chords(ctx, section, track)
    elif track["id"] == "bass":
        _starter_bass(ctx, section, track)
    elif track["id"] == "sub":
        _starter_sub(ctx, section, track)
    elif track["id"] == "lead":
        _starter_lead(ctx, section, track)
    elif track["id"] == "drums":
        _starter_drums(ctx, section, track)
    elif track["id"] == "clap-stack":
        _starter_clap_stack(ctx, section, track)
    elif track["id"] == "hat-ride":
        _starter_hat_ride(ctx, section, track)
    elif track["id"] == "fx":
        _starter_fx(ctx, section, track)
    elif track["id"] == "guitar":
        _starter_guitar(ctx, section, track)
    elif track["id"] == "filter-auto":
        _starter_filter_auto(ctx, section, track)
    elif track["id"] in {"sample", "plucks", "vocals"}:
        _starter_sample(ctx, section, track)


def _write_wav(path: Path, audio: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(audio, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(SR)
        handle.writeframes(pcm.tobytes())


def write_outputs(ctx: RenderContext) -> dict[str, str]:
    EXPORTS.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, str] = {}
    mix = stereo_buffer()
    for stem_id, audio in ctx.stems.items():
        stem_path = EXPORTS / f"{SCAFFOLD_STEM_PREFIX}_{stem_id}.wav"
        _write_wav(stem_path, audio)
        outputs[stem_id] = str(stem_path)
        mix += audio
    mix /= max(1, len(ctx.stems))
    mix_path = EXPORTS / f"{SCAFFOLD_STEM_PREFIX}_full_mix.wav"
    _write_wav(mix_path, mix)
    outputs["full_mix"] = str(mix_path)
    ctx.exports = outputs
    return outputs



def _log_section(ctx: RenderContext, section: dict) -> None:
    ctx.notes.append(
        f"{section['label']} bars {section['startBar'] + 1}-{section['startBar'] + section['bars']}: {section.get('summary', '')}"
    )


def _placeholder_track(ctx: RenderContext, track_id: str, start_bar: int, bars: int, *, note: str) -> None:
    ctx.notes.append(f"  - {track_id} @ bars {start_bar + 1}-{start_bar + bars} :: {note}")


def describe_plan() -> None:
    print(f"Renderer scaffold for {PROJECT_NAME}")
    print(f"BPM: {BPM} | Bars: {TOTAL_BARS}")
    print("Tracks:")
    for track in TRACK_PLAN:
        print(f"  - {track['id']} :: {track['instrument']} :: {len(track['clips'])} clip(s)")
    print("Sections:")
    for section in SECTION_PLAN:
        print(
            f"  - {section['label']} bars {section['startBar'] + 1}-{section['startBar'] + section['bars']} "
            f":: tracks {', '.join(section.get('trackIds', [])) or 'none'}"
        )

def render_01_intro_chords(ctx: RenderContext, section: dict) -> None:
    """Intro / Chords role stub."""
    track = TRACK_PLAN_BY_ID['chords']
    # Instrument: Supersaw
    # Guidance: Write the harmonic bed, voicing spread, and sidechain shape for the section.
    # Track effects: EQ Eight, Reverb, Sidechain
    # Relevant clips in this section:
    # - Intro chords (bars 1-8, pattern)
    # TODO: Refine or replace the starter render body for this lane.
    ctx.notes.append(
        f"    -> Chords: {track['instrument']} | effects {', '.join(track.get('effects', [])) or 'none'}"
    )
    _render_lane_starter(ctx, section, track)
    _placeholder_track(ctx, 'chords', section['startBar'], section['bars'], note=track['name'])


def render_01_intro_lead(ctx: RenderContext, section: dict) -> None:
    """Intro / Lead role stub."""
    track = TRACK_PLAN_BY_ID['lead']
    # Instrument: Square Lead
    # Guidance: Carry the hook or teaser phrase and decide how busy the melodic contour should be.
    # Track effects: Ping Delay, Air EQ, Sidechain
    # Relevant clips in this section:
    # - Intro lead (bars 1-8, pattern)
    # TODO: Refine or replace the starter render body for this lane.
    ctx.notes.append(
        f"    -> Lead: {track['instrument']} | effects {', '.join(track.get('effects', [])) or 'none'}"
    )
    _render_lane_starter(ctx, section, track)
    _placeholder_track(ctx, 'lead', section['startBar'], section['bars'], note=track['name'])


def render_01_intro_fx(ctx: RenderContext, section: dict) -> None:
    """Intro / FX role stub."""
    track = TRACK_PLAN_BY_ID['fx']
    # Instrument: Transitions
    # Guidance: Cover risers, impacts, reverses, and spatial glue that mark the section change.
    # Track effects: Long Reverb, Stereo Spread, Sidechain
    # Relevant clips in this section:
    # - Intro fx (bars 1-8, audio)
    # TODO: Refine or replace the starter render body for this lane.
    ctx.notes.append(
        f"    -> FX: {track['instrument']} | effects {', '.join(track.get('effects', [])) or 'none'}"
    )
    _render_lane_starter(ctx, section, track)
    _placeholder_track(ctx, 'fx', section['startBar'], section['bars'], note=track['name'])


def render_02_verse_bass(ctx: RenderContext, section: dict) -> None:
    """Verse / Bass role stub."""
    track = TRACK_PLAN_BY_ID['bass']
    # Instrument: Mid Bass
    # Guidance: Lock bass rhythm to the section pulse and decide the mid-bass character.
    # Track effects: Sidechain, Saturator
    # Relevant clips in this section:
    # - Verse bass (bars 9-16, pattern)
    # TODO: Refine or replace the starter render body for this lane.
    ctx.notes.append(
        f"    -> Bass: {track['instrument']} | effects {', '.join(track.get('effects', [])) or 'none'}"
    )
    _render_lane_starter(ctx, section, track)
    _placeholder_track(ctx, 'bass', section['startBar'], section['bars'], note=track['name'])


def render_02_verse_clap_stack(ctx: RenderContext, section: dict) -> None:
    """Verse / Clap Stack role stub."""
    track = TRACK_PLAN_BY_ID['clap-stack']
    # Instrument: Clap Layer
    # Guidance: Decide whether this lane is backbeat support, clap roll, or a wider impact layer.
    # Track effects: Reverb, Stereo Spread
    # Relevant clips in this section:
    # - Verse clap stack (bars 9-16, pattern)
    # TODO: Refine or replace the starter render body for this lane.
    ctx.notes.append(
        f"    -> Clap Stack: {track['instrument']} | effects {', '.join(track.get('effects', [])) or 'none'}"
    )
    _render_lane_starter(ctx, section, track)
    _placeholder_track(ctx, 'clap-stack', section['startBar'], section['bars'], note=track['name'])


def render_02_verse_drums(ctx: RenderContext, section: dict) -> None:
    """Verse / Drums role stub."""
    track = TRACK_PLAN_BY_ID['drums']
    # Instrument: Sampler
    # Guidance: Program the core groove, kick placement, and transient balance for this section.
    # Track effects: EQ Eight, Bus Comp
    # Relevant clips in this section:
    # - Verse drums (bars 9-16, pattern)
    # TODO: Refine or replace the starter render body for this lane.
    ctx.notes.append(
        f"    -> Drums: {track['instrument']} | effects {', '.join(track.get('effects', [])) or 'none'}"
    )
    _render_lane_starter(ctx, section, track)
    _placeholder_track(ctx, 'drums', section['startBar'], section['bars'], note=track['name'])


def render_02_verse_guitar(ctx: RenderContext, section: dict) -> None:
    """Verse / Guitar role stub."""
    track = TRACK_PLAN_BY_ID['guitar']
    # Instrument: Muted Guitar
    # Guidance: Use this as a lighter support layer so it adds motion without crowding the lead.
    # Track effects: Compressor, Room
    # Relevant clips in this section:
    # - Verse guitar (bars 9-16, pattern)
    # TODO: Refine or replace the starter render body for this lane.
    ctx.notes.append(
        f"    -> Guitar: {track['instrument']} | effects {', '.join(track.get('effects', [])) or 'none'}"
    )
    _render_lane_starter(ctx, section, track)
    _placeholder_track(ctx, 'guitar', section['startBar'], section['bars'], note=track['name'])


def render_02_verse_hat_ride(ctx: RenderContext, section: dict) -> None:
    """Verse / Hat/Ride role stub."""
    track = TRACK_PLAN_BY_ID['hat-ride']
    # Instrument: Trap Hat Rack
    # Guidance: Define the high-frequency motion, hat density, and any ride/crash escalation.
    # Track effects: Transient Tightener
    # Relevant clips in this section:
    # - Verse hat/ride (bars 9-16, pattern)
    # TODO: Refine or replace the starter render body for this lane.
    ctx.notes.append(
        f"    -> Hat/Ride: {track['instrument']} | effects {', '.join(track.get('effects', [])) or 'none'}"
    )
    _render_lane_starter(ctx, section, track)
    _placeholder_track(ctx, 'hat-ride', section['startBar'], section['bars'], note=track['name'])


def render_03_build_filter_auto(ctx: RenderContext, section: dict) -> None:
    """Build / Filter Auto role stub."""
    track = TRACK_PLAN_BY_ID['filter-auto']
    # Instrument: Automation Lane
    # Guidance: Shape the macro automation so the arrangement tension is visible and audible.
    # Section techniques: automation, filtering
    # Track effects: Filter Macro
    # Relevant clips in this section:
    # - Build filter auto (bars 17-24, pattern)
    # TODO: Refine or replace the starter render body for this lane.
    ctx.notes.append(
        f"    -> Filter Auto: {track['instrument']} | effects {', '.join(track.get('effects', [])) or 'none'}"
    )
    _render_lane_starter(ctx, section, track)
    _placeholder_track(ctx, 'filter-auto', section['startBar'], section['bars'], note=track['name'])


def render_03_build_clap_stack(ctx: RenderContext, section: dict) -> None:
    """Build / Clap Stack role stub."""
    track = TRACK_PLAN_BY_ID['clap-stack']
    # Instrument: Clap Layer
    # Guidance: Decide whether this lane is backbeat support, clap roll, or a wider impact layer.
    # Section techniques: automation, filtering
    # Track effects: Reverb, Stereo Spread
    # Relevant clips in this section:
    # - Build clap stack (bars 17-24, pattern)
    # TODO: Refine or replace the starter render body for this lane.
    ctx.notes.append(
        f"    -> Clap Stack: {track['instrument']} | effects {', '.join(track.get('effects', [])) or 'none'}"
    )
    _render_lane_starter(ctx, section, track)
    _placeholder_track(ctx, 'clap-stack', section['startBar'], section['bars'], note=track['name'])


def render_03_build_fx(ctx: RenderContext, section: dict) -> None:
    """Build / FX role stub."""
    track = TRACK_PLAN_BY_ID['fx']
    # Instrument: Transitions
    # Guidance: Cover risers, impacts, reverses, and spatial glue that mark the section change.
    # Section techniques: automation, filtering
    # Track effects: Long Reverb, Stereo Spread, Sidechain
    # Relevant clips in this section:
    # - Build fx (bars 17-24, audio)
    # TODO: Refine or replace the starter render body for this lane.
    ctx.notes.append(
        f"    -> FX: {track['instrument']} | effects {', '.join(track.get('effects', [])) or 'none'}"
    )
    _render_lane_starter(ctx, section, track)
    _placeholder_track(ctx, 'fx', section['startBar'], section['bars'], note=track['name'])


def render_04_drop_bass(ctx: RenderContext, section: dict) -> None:
    """Drop / Bass role stub."""
    track = TRACK_PLAN_BY_ID['bass']
    # Instrument: Mid Bass
    # Guidance: Lock bass rhythm to the section pulse and decide the mid-bass character.
    # Section techniques: sidechain
    # Track effects: Sidechain, Saturator
    # Relevant clips in this section:
    # - Drop bass (bars 25-40, pattern)
    # TODO: Refine or replace the starter render body for this lane.
    ctx.notes.append(
        f"    -> Bass: {track['instrument']} | effects {', '.join(track.get('effects', [])) or 'none'}"
    )
    _render_lane_starter(ctx, section, track)
    _placeholder_track(ctx, 'bass', section['startBar'], section['bars'], note=track['name'])


def render_04_drop_chords(ctx: RenderContext, section: dict) -> None:
    """Drop / Chords role stub."""
    track = TRACK_PLAN_BY_ID['chords']
    # Instrument: Supersaw
    # Guidance: Write the harmonic bed, voicing spread, and sidechain shape for the section.
    # Section techniques: sidechain
    # Track effects: EQ Eight, Reverb, Sidechain
    # Relevant clips in this section:
    # - Drop chords (bars 25-40, pattern)
    # TODO: Refine or replace the starter render body for this lane.
    ctx.notes.append(
        f"    -> Chords: {track['instrument']} | effects {', '.join(track.get('effects', [])) or 'none'}"
    )
    _render_lane_starter(ctx, section, track)
    _placeholder_track(ctx, 'chords', section['startBar'], section['bars'], note=track['name'])


def render_04_drop_fx(ctx: RenderContext, section: dict) -> None:
    """Drop / FX role stub."""
    track = TRACK_PLAN_BY_ID['fx']
    # Instrument: Transitions
    # Guidance: Cover risers, impacts, reverses, and spatial glue that mark the section change.
    # Section techniques: sidechain
    # Track effects: Long Reverb, Stereo Spread, Sidechain
    # Relevant clips in this section:
    # - Drop fx (bars 25-40, audio)
    # TODO: Refine or replace the starter render body for this lane.
    ctx.notes.append(
        f"    -> FX: {track['instrument']} | effects {', '.join(track.get('effects', [])) or 'none'}"
    )
    _render_lane_starter(ctx, section, track)
    _placeholder_track(ctx, 'fx', section['startBar'], section['bars'], note=track['name'])


def render_04_drop_lead(ctx: RenderContext, section: dict) -> None:
    """Drop / Lead role stub."""
    track = TRACK_PLAN_BY_ID['lead']
    # Instrument: Square Lead
    # Guidance: Carry the hook or teaser phrase and decide how busy the melodic contour should be.
    # Section techniques: sidechain
    # Track effects: Ping Delay, Air EQ, Sidechain
    # Relevant clips in this section:
    # - Drop lead (bars 25-40, pattern)
    # TODO: Refine or replace the starter render body for this lane.
    ctx.notes.append(
        f"    -> Lead: {track['instrument']} | effects {', '.join(track.get('effects', [])) or 'none'}"
    )
    _render_lane_starter(ctx, section, track)
    _placeholder_track(ctx, 'lead', section['startBar'], section['bars'], note=track['name'])


def render_04_drop_sub(ctx: RenderContext, section: dict) -> None:
    """Drop / Sub role stub."""
    track = TRACK_PLAN_BY_ID['sub']
    # Instrument: Triangle Sub
    # Guidance: Anchor the low end with note lengths that support the drop without muddying transitions.
    # Section techniques: sidechain
    # Track effects: Mono Utility, Kick Duck, Sidechain
    # Relevant clips in this section:
    # - Drop sub (bars 25-40, pattern)
    # TODO: Refine or replace the starter render body for this lane.
    ctx.notes.append(
        f"    -> Sub: {track['instrument']} | effects {', '.join(track.get('effects', [])) or 'none'}"
    )
    _render_lane_starter(ctx, section, track)
    _placeholder_track(ctx, 'sub', section['startBar'], section['bars'], note=track['name'])


def render_01_intro(ctx: RenderContext) -> None:
    """Intro: bars 1-8."""
    section = SECTION_PLAN_BY_ID['section-01']
    # Transcript summary:
    # intro has a simple chord progression and a lead melody with white noise
    # Scaffold detail:
    # intro has a simple chord progression and a lead melody with white noise. Tracks: chords, lead, fx
    # Track roles: chords, lead, noise
    # Tracks to touch in this section:
    # - chords: Chords
    # - lead: Lead
    # - fx: FX
    _log_section(ctx, section)
    # TODO: Replace the role helper stubs below with real synthesis / sample arrangement.
    render_01_intro_chords(ctx, section)
    render_01_intro_lead(ctx, section)
    render_01_intro_fx(ctx, section)


def render_02_verse(ctx: RenderContext) -> None:
    """Verse: bars 9-16."""
    section = SECTION_PLAN_BY_ID['section-02']
    # Transcript summary:
    # verse adds guitar bass and a simple trap beat with kick snare clap and hi-hat
    # Scaffold detail:
    # verse adds guitar bass and a simple trap beat with kick snare clap and hi-hat. Tracks: bass, clap-stack, drums, guitar, hat-ride
    # Track roles: bass, clap, drums, guitar, hat, kick, snare
    # Tracks to touch in this section:
    # - bass: Bass
    # - clap-stack: Clap Stack
    # - drums: Drums
    # - guitar: Guitar
    # - hat-ride: Hat/Ride
    _log_section(ctx, section)
    # TODO: Replace the role helper stubs below with real synthesis / sample arrangement.
    render_02_verse_bass(ctx, section)
    render_02_verse_clap_stack(ctx, section)
    render_02_verse_drums(ctx, section)
    render_02_verse_guitar(ctx, section)
    render_02_verse_hat_ride(ctx, section)


def render_03_build(ctx: RenderContext) -> None:
    """Build: bars 17-24."""
    section = SECTION_PLAN_BY_ID['section-03']
    # Transcript summary:
    # build adds risers downlifters claps and a filter automation
    # Scaffold detail:
    # build adds risers downlifters claps and a filter automation. Tracks: filter-auto, clap-stack, fx. Techniques: automation, filtering
    # Track roles: automation, clap, downlifter, riser
    # Techniques: automation, filtering
    # Tracks to touch in this section:
    # - filter-auto: Filter Auto
    # - clap-stack: Clap Stack
    # - fx: FX
    _log_section(ctx, section)
    # TODO: Replace the role helper stubs below with real synthesis / sample arrangement.
    render_03_build_filter_auto(ctx, section)
    render_03_build_clap_stack(ctx, section)
    render_03_build_fx(ctx, section)


def render_04_drop(ctx: RenderContext) -> None:
    """Drop: bars 25-40."""
    section = SECTION_PLAN_BY_ID['section-04']
    # Transcript summary:
    # drop uses lead chords bass sub crashes crowd and sidechain
    # Scaffold detail:
    # drop uses lead chords bass sub crashes crowd and sidechain. Tracks: bass, chords, fx, lead, sub. Techniques: sidechain
    # Track roles: bass, chords, crash, crowd, lead, sub
    # Techniques: sidechain
    # Tracks to touch in this section:
    # - bass: Bass
    # - chords: Chords
    # - fx: FX
    # - lead: Lead
    # - sub: Sub
    _log_section(ctx, section)
    # TODO: Replace the role helper stubs below with real synthesis / sample arrangement.
    render_04_drop_bass(ctx, section)
    render_04_drop_chords(ctx, section)
    render_04_drop_fx(ctx, section)
    render_04_drop_lead(ctx, section)
    render_04_drop_sub(ctx, section)

def render_song() -> RenderContext:
    ctx = RenderContext()
    render_01_intro(ctx)
    render_02_verse(ctx)
    render_03_build(ctx)
    render_04_drop(ctx)

    return ctx


def main() -> int:
    describe_plan()
    ctx = render_song()
    outputs = write_outputs(ctx)
    print("")
    print("Section notes:")
    for line in ctx.notes:
        print(line)
    print("")
    print("Outputs:")
    for key, value in outputs.items():
        print(f"  - {key}: {value}")
    print("")
    print("TODO: refine the starter render bodies and then sync the final project metadata.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
