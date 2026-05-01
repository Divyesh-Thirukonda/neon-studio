#!/usr/bin/env python3
"""
Render Neon Solitude as an original bright future-bass/festival EDM sketch.

The goal is to sit in the lane of a mid-2010s uplifting Marshmello-style drop:
simple hook, wide supersaws, trap drums, filtered builds, and crowd/white-noise
energy. This generator does not copy a commercial melody, stem, or session.
"""

from __future__ import annotations

import json
import math
import struct
import wave
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


SR = 44_100
BPM = 142
BEAT = 60.0 / BPM
PPQ = 480
TOTAL_BARS = 72
TAIL_SECONDS = 4.0
TOTAL_SECONDS = TOTAL_BARS * 4 * BEAT + TAIL_SECONDS
N_SAMPLES = int(TOTAL_SECONDS * SR)
ROOT = Path(__file__).resolve().parent
EXPORTS = ROOT / "exports"
MIDI_DIR = ROOT / "midi"
PROJECT_PATHS = [
    ROOT / "data" / "projects" / "neon-solitude.neon.json",
    ROOT / "factory" / "projects" / "neon-solitude.neon.json",
]

rng = np.random.default_rng(1408)

ASSET_FILES = {
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

TRACK_COLORS = {
    "drums": "#ff8d5c",
    "bass": "#4ade80",
    "chords": "#ffd166",
    "lead": "#6fd6ff",
    "fx": "#d78bff",
    "guitar-bass": "#f1ad72",
    "hat-ride": "#f4f1a3",
    "frozen-build-bass": "#7de2bf",
    "filter-automation": "#7dd3fc",
    "crowd-sidechain": "#c084fc",
    "lead-double": "#9ec5ff",
    "clap-stack": "#fb7185",
    "ghost-sidechain": "#94a3b8",
    "ear-candy": "#f0abfc",
}

DEFAULT_TRACK_LAYOUT = [
    {
        "id": "drums",
        "name": "Drums",
        "kind": "audio",
        "instrument": "Sampler",
        "gain": 0.78,
        "pan": 0.0,
        "steps": [0, 3, 6, 8, 11, 14],
        "effects": [
            {"id": "eq", "name": "EQ Eight", "active": True, "amount": 0.50},
            {"id": "bus-comp", "name": "Bus Comp", "active": True, "amount": 0.56},
            {"id": "soft-clip", "name": "Soft Clip", "active": True, "amount": 0.38},
        ],
        "clips": [
            {"id": "drums-8a", "name": "Verse drums", "startBar": 8, "bars": 8, "lane": "drums", "color": TRACK_COLORS["drums"], "type": "audio"},
            {"id": "drums-8b", "name": "Marsh rhythm kick", "startBar": 8, "bars": 8, "lane": "drums", "color": TRACK_COLORS["drums"], "type": "pattern"},
            {"id": "drums-8c", "name": "Snare + clap backbeat", "startBar": 8, "bars": 8, "lane": "drums", "color": TRACK_COLORS["drums"], "type": "pattern"},
            {"id": "drums-8d", "name": "Trap hi-hat", "startBar": 8, "bars": 8, "lane": "drums", "color": TRACK_COLORS["drums"], "type": "pattern"},
            {"id": "drums-16", "name": "Drop drums", "startBar": 16, "bars": 16, "lane": "drums", "color": TRACK_COLORS["drums"], "type": "audio"},
            {"id": "drums-40a", "name": "Build drums", "startBar": 40, "bars": 8, "lane": "drums", "color": TRACK_COLORS["drums"], "type": "audio"},
            {"id": "drums-40b", "name": "Build different kick", "startBar": 40, "bars": 8, "lane": "drums", "color": TRACK_COLORS["drums"], "type": "pattern"},
            {"id": "drums-40c", "name": "Build snare/clap roll", "startBar": 40, "bars": 8, "lane": "drums", "color": TRACK_COLORS["drums"], "type": "pattern"},
            {"id": "drums-48", "name": "Final drums", "startBar": 48, "bars": 16, "lane": "drums", "color": TRACK_COLORS["drums"], "type": "audio"},
        ],
    },
    {
        "id": "bass",
        "name": "Bass",
        "kind": "audio",
        "instrument": "Sub Synth",
        "gain": 0.90,
        "pan": 0.0,
        "steps": [0, 6, 10, 13],
        "effects": [
            {"id": "eq", "name": "Low Cut EQ", "active": True, "amount": 0.44},
            {"id": "duck", "name": "Sidechain", "active": True, "amount": 0.60},
            {"id": "sat", "name": "Saturator", "active": True, "amount": 0.38},
        ],
        "clips": [
            {"id": "bass-8", "name": "Verse bass", "startBar": 8, "bars": 8, "lane": "bass", "color": TRACK_COLORS["bass"], "type": "audio"},
            {"id": "bass-16a", "name": "Drop bass", "startBar": 16, "bars": 16, "lane": "bass", "color": TRACK_COLORS["bass"], "type": "audio"},
            {"id": "bass-16b", "name": "Fat drop bass", "startBar": 16, "bars": 16, "lane": "bass", "color": TRACK_COLORS["bass"], "type": "pattern"},
            {"id": "bass-40", "name": "Rendered/frozen build bass", "startBar": 40, "bars": 8, "lane": "bass", "color": TRACK_COLORS["bass"], "type": "pattern"},
            {"id": "bass-48", "name": "Final bass", "startBar": 48, "bars": 16, "lane": "bass", "color": TRACK_COLORS["bass"], "type": "audio"},
        ],
    },
    {
        "id": "chords",
        "name": "Chords",
        "kind": "audio",
        "instrument": "Supersaw",
        "gain": 1.0,
        "pan": -0.04,
        "steps": [0, 4, 8, 12],
        "effects": [
            {"id": "eq", "name": "EQ Eight", "active": True, "amount": 0.72},
            {"id": "delay", "name": "Ping Delay", "active": True, "amount": 0.34},
            {"id": "verb", "name": "Reverb", "active": True, "amount": 0.46},
        ],
        "clips": [
            {"id": "chords-0", "name": "Simple happy chord progression", "startBar": 0, "bars": 16, "lane": "chords", "color": TRACK_COLORS["chords"], "type": "audio"},
            {"id": "chords-16", "name": "Drop stabs", "startBar": 16, "bars": 16, "lane": "chords", "color": TRACK_COLORS["chords"], "type": "audio"},
            {"id": "chords-40", "name": "Build pad", "startBar": 40, "bars": 8, "lane": "chords", "color": TRACK_COLORS["chords"], "type": "audio"},
            {"id": "chords-48", "name": "Final stabs", "startBar": 48, "bars": 16, "lane": "chords", "color": TRACK_COLORS["chords"], "type": "audio"},
            {"id": "chords-64", "name": "Outro pad", "startBar": 64, "bars": 8, "lane": "chords", "color": TRACK_COLORS["chords"], "type": "audio"},
        ],
    },
    {
        "id": "lead",
        "name": "Lead",
        "kind": "audio",
        "instrument": "Square Lead",
        "gain": 1.0,
        "pan": 0.06,
        "steps": [0, 2, 5, 7, 10, 12, 15],
        "effects": [
            {"id": "eq", "name": "EQ Eight", "active": True, "amount": 0.66},
            {"id": "delay", "name": "Stereo Delay", "active": True, "amount": 0.48},
            {"id": "plate", "name": "Plate", "active": True, "amount": 0.42},
        ],
        "clips": [
            {"id": "lead-4", "name": "Simple happy intro melody", "startBar": 4, "bars": 12, "lane": "lead", "color": TRACK_COLORS["lead"], "type": "audio"},
            {"id": "lead-16", "name": "Filled-in drop lead", "startBar": 16, "bars": 16, "lane": "lead", "color": TRACK_COLORS["lead"], "type": "audio"},
            {"id": "lead-32", "name": "Break hook", "startBar": 32, "bars": 8, "lane": "lead", "color": TRACK_COLORS["lead"], "type": "audio"},
            {"id": "lead-48", "name": "Final filled-in hook", "startBar": 48, "bars": 16, "lane": "lead", "color": TRACK_COLORS["lead"], "type": "audio"},
        ],
    },
    {
        "id": "fx",
        "name": "FX",
        "kind": "audio",
        "instrument": "Sampler",
        "gain": 0.72,
        "pan": 0.08,
        "steps": [0, 8],
        "effects": [
            {"id": "eq", "name": "EQ Eight", "active": True, "amount": 0.58},
            {"id": "hall", "name": "Hall", "active": True, "amount": 0.46},
            {"id": "spread", "name": "Stereo Spread", "active": True, "amount": 0.38},
            {"id": "duck", "name": "Kick Sidechain", "active": True, "amount": 0.34},
        ],
        "clips": [
            {"id": "fx-0", "name": "Intro white noise", "startBar": 0, "bars": 8, "lane": "fx", "color": TRACK_COLORS["fx"], "type": "audio"},
            {"id": "fx-12a", "name": "Riser", "startBar": 12, "bars": 4, "lane": "fx", "color": TRACK_COLORS["fx"], "type": "audio"},
            {"id": "fx-12b", "name": "White noise up", "startBar": 12, "bars": 4, "lane": "fx", "color": TRACK_COLORS["fx"], "type": "audio"},
            {"id": "fx-15", "name": "Reverse transition", "startBar": 15, "bars": 1, "lane": "fx", "color": TRACK_COLORS["fx"], "type": "audio"},
            {"id": "fx-16", "name": "Impact", "startBar": 16, "bars": 1, "lane": "fx", "color": TRACK_COLORS["fx"], "type": "audio"},
            {"id": "fx-40a", "name": "Long build", "startBar": 40, "bars": 8, "lane": "fx", "color": TRACK_COLORS["fx"], "type": "audio"},
            {"id": "fx-40b", "name": "Downlifters", "startBar": 40, "bars": 8, "lane": "fx", "color": TRACK_COLORS["fx"], "type": "audio"},
            {"id": "fx-40c", "name": "Chain noise layer", "startBar": 40, "bars": 8, "lane": "fx", "color": TRACK_COLORS["fx"], "type": "audio"},
            {"id": "fx-48a", "name": "Impact", "startBar": 48, "bars": 1, "lane": "fx", "color": TRACK_COLORS["fx"], "type": "audio"},
            {"id": "fx-48b", "name": "Crowd sidechain swell", "startBar": 48, "bars": 16, "lane": "fx", "color": TRACK_COLORS["fx"], "type": "audio"},
            {"id": "fx-64", "name": "Outro impact", "startBar": 64, "bars": 1, "lane": "fx", "color": TRACK_COLORS["fx"], "type": "audio"},
        ],
    },
    {
        "id": "guitar-bass",
        "name": "Guitar Bass",
        "kind": "audio",
        "instrument": "Muted guitar-style bass preset",
        "gain": 0.58,
        "pan": -0.08,
        "steps": [0, 3, 6, 10, 13],
        "effects": [
            {"id": "amp", "name": "Clean Amp", "active": True, "amount": 0.30},
            {"id": "lpf", "name": "Muted Lowpass", "active": True, "amount": 0.42},
        ],
        "clips": [
            {"id": "guitar-bass-8", "name": "Verse guitar bass sound", "startBar": 8, "bars": 8, "lane": "guitar-bass", "color": TRACK_COLORS["guitar-bass"], "type": "audio"},
            {"id": "guitar-bass-40", "name": "Build bass notes", "startBar": 40, "bars": 8, "lane": "guitar-bass", "color": TRACK_COLORS["guitar-bass"], "type": "audio"},
        ],
    },
    {
        "id": "hat-ride",
        "name": "Hat/Ride",
        "kind": "audio",
        "instrument": "Fast trap hats and ride layer",
        "gain": 0.52,
        "pan": 0.16,
        "steps": [1, 3, 5, 7, 9, 11, 13, 15],
        "effects": [
            {"id": "eq", "name": "Bright EQ", "active": True, "amount": 0.52},
            {"id": "human", "name": "Velocity Humanize", "active": True, "amount": 0.44},
        ],
        "clips": [
            {"id": "hat-ride-48a", "name": "Fast hi-hat speed-up", "startBar": 48, "bars": 16, "lane": "hat-ride", "color": TRACK_COLORS["hat-ride"], "type": "audio"},
            {"id": "hat-ride-56", "name": "Ride variation", "startBar": 56, "bars": 8, "lane": "hat-ride", "color": TRACK_COLORS["hat-ride"], "type": "audio"},
            {"id": "hat-ride-48b", "name": "Crashes on drop", "startBar": 48, "bars": 16, "lane": "hat-ride", "color": TRACK_COLORS["hat-ride"], "type": "audio"},
        ],
    },
    {
        "id": "frozen-build-bass",
        "name": "Frozen Bass",
        "kind": "audio",
        "instrument": "Rendered build bass audio",
        "gain": 0.70,
        "pan": 0.0,
        "steps": [0, 6, 10],
        "effects": [
            {"id": "duck", "name": "Kick Sidechain", "active": True, "amount": 0.54},
            {"id": "eq", "name": "Low Cut EQ", "active": True, "amount": 0.38},
        ],
        "clips": [
            {"id": "frozen-build-bass-40", "name": "CPU-saved rendered build bass", "startBar": 40, "bars": 8, "lane": "frozen-build-bass", "color": TRACK_COLORS["frozen-build-bass"], "type": "audio"},
        ],
    },
    {
        "id": "filter-automation",
        "name": "Filter Auto",
        "kind": "automation",
        "instrument": "Rendered cutoff sweep",
        "gain": 0.58,
        "pan": 0.0,
        "steps": [0],
        "effects": [
            {"id": "cutoff", "name": "Cutoff Automation", "active": True, "amount": 0.92},
            {"id": "duck", "name": "Kick Sidechain", "active": True, "amount": 0.48},
        ],
        "clips": [
            {"id": "filter-automation-40", "name": "Automated filter sweep", "startBar": 40, "bars": 8, "lane": "filter-automation", "color": TRACK_COLORS["filter-automation"], "type": "automation"},
        ],
    },
    {
        "id": "crowd-sidechain",
        "name": "Crowd Duck",
        "kind": "audio",
        "instrument": "Crowd swell sampler",
        "gain": 0.62,
        "pan": 0.04,
        "steps": [0, 4, 8, 12],
        "effects": [
            {"id": "duck", "name": "Kick Sidechain", "active": True, "amount": 0.82},
            {"id": "wide", "name": "Stereo Crowd Spread", "active": True, "amount": 0.62},
        ],
        "clips": [
            {"id": "crowd-sidechain-48", "name": "Crowd sidechained to kick", "startBar": 48, "bars": 16, "lane": "crowd-sidechain", "color": TRACK_COLORS["crowd-sidechain"], "type": "audio"},
        ],
    },
    {
        "id": "lead-double",
        "name": "Lead Double",
        "kind": "audio",
        "instrument": "Detuned square/saw support",
        "gain": 0.74,
        "pan": -0.16,
        "steps": [0, 2, 5, 7, 10, 12, 15],
        "effects": [
            {"id": "eq", "name": "Low Cut EQ", "active": True, "amount": 0.74},
            {"id": "delay", "name": "Micro Delay", "active": True, "amount": 0.36},
            {"id": "wide", "name": "Stereo Widener", "active": True, "amount": 0.56},
            {"id": "duck", "name": "Kick Sidechain", "active": True, "amount": 0.42},
        ],
        "clips": [
            {"id": "lead-double-16", "name": "Wide drop lead double", "startBar": 16, "bars": 16, "lane": "lead-double", "color": TRACK_COLORS["lead-double"], "type": "audio"},
            {"id": "lead-double-48", "name": "Final hook double", "startBar": 48, "bars": 16, "lane": "lead-double", "color": TRACK_COLORS["lead-double"], "type": "audio"},
        ],
    },
    {
        "id": "clap-stack",
        "name": "Clap Stack",
        "kind": "audio",
        "instrument": "Layered clap/snare bus",
        "gain": 0.56,
        "pan": 0.04,
        "steps": [4, 12],
        "effects": [
            {"id": "transient", "name": "Transient Shaper", "active": True, "amount": 0.48},
            {"id": "bus", "name": "Bus Comp", "active": True, "amount": 0.40},
            {"id": "room", "name": "Short Room", "active": True, "amount": 0.32},
        ],
        "clips": [
            {"id": "clap-stack-8", "name": "Verse clap layer", "startBar": 8, "bars": 8, "lane": "clap-stack", "color": TRACK_COLORS["clap-stack"], "type": "audio"},
            {"id": "clap-stack-16", "name": "Drop clap stack", "startBar": 16, "bars": 16, "lane": "clap-stack", "color": TRACK_COLORS["clap-stack"], "type": "audio"},
            {"id": "clap-stack-40", "name": "Build clap roll layer", "startBar": 40, "bars": 8, "lane": "clap-stack", "color": TRACK_COLORS["clap-stack"], "type": "audio"},
            {"id": "clap-stack-48", "name": "Final clap stack", "startBar": 48, "bars": 16, "lane": "clap-stack", "color": TRACK_COLORS["clap-stack"], "type": "audio"},
        ],
    },
    {
        "id": "ghost-sidechain",
        "name": "Ghost Key",
        "kind": "send",
        "instrument": "Silent-ish sidechain trigger",
        "gain": 0.20,
        "pan": 0.0,
        "steps": [0, 6, 10, 13],
        "effects": [
            {"id": "key-out", "name": "Sidechain Key Output", "active": True, "amount": 1.0},
            {"id": "trim", "name": "Monitor Trim", "active": True, "amount": 0.18},
        ],
        "clips": [
            {"id": "ghost-sidechain-16", "name": "Drop ghost trigger", "startBar": 16, "bars": 16, "lane": "ghost-sidechain", "color": TRACK_COLORS["ghost-sidechain"], "type": "audio"},
            {"id": "ghost-sidechain-40", "name": "Build ghost trigger", "startBar": 40, "bars": 8, "lane": "ghost-sidechain", "color": TRACK_COLORS["ghost-sidechain"], "type": "audio"},
            {"id": "ghost-sidechain-48", "name": "Final ghost trigger", "startBar": 48, "bars": 16, "lane": "ghost-sidechain", "color": TRACK_COLORS["ghost-sidechain"], "type": "audio"},
        ],
    },
    {
        "id": "ear-candy",
        "name": "Ear Candy",
        "kind": "audio",
        "instrument": "Transition fills and sparkle",
        "gain": 0.66,
        "pan": 0.18,
        "steps": [3, 7, 11, 15],
        "effects": [
            {"id": "hp", "name": "Highpass EQ", "active": True, "amount": 0.78},
            {"id": "delay", "name": "Tempo Delay", "active": True, "amount": 0.44},
            {"id": "plate", "name": "Plate Reverb", "active": True, "amount": 0.48},
            {"id": "spread", "name": "Stereo Spread", "active": True, "amount": 0.62},
        ],
        "clips": [
            {"id": "ear-candy-14", "name": "Pre-drop sparkle fills", "startBar": 14, "bars": 2, "lane": "ear-candy", "color": TRACK_COLORS["ear-candy"], "type": "audio"},
            {"id": "ear-candy-30", "name": "Drop exit fills", "startBar": 30, "bars": 2, "lane": "ear-candy", "color": TRACK_COLORS["ear-candy"], "type": "audio"},
            {"id": "ear-candy-46", "name": "Build sparkle fills", "startBar": 46, "bars": 2, "lane": "ear-candy", "color": TRACK_COLORS["ear-candy"], "type": "audio"},
            {"id": "ear-candy-48", "name": "Final drop ear candy", "startBar": 48, "bars": 16, "lane": "ear-candy", "color": TRACK_COLORS["ear-candy"], "type": "audio"},
        ],
    },
]

DEFAULT_RECIPE = [
    {"id": "future-bass", "section": "Foundation", "label": "Future-bass presets plus trap drums", "detail": "Supersaw chords, square lead, sub/fat bass, and trap drum patterns are separated into tracks.", "status": "implemented", "trackIds": ["chords", "lead", "bass", "drums"]},
    {"id": "intro-chords", "section": "Intro", "label": "Simple happy chord progression", "detail": "Open voicings in E minor / G major set the emotional lane before the hook lands.", "status": "implemented", "trackIds": ["chords"]},
    {"id": "intro-melody", "section": "Intro", "label": "Simple happy melody", "detail": "A sparse square-lead motif previews the drop hook without exhausting it.", "status": "implemented", "trackIds": ["lead"]},
    {"id": "intro-noise", "section": "Intro", "label": "White noise and white-noise-up", "detail": "Noise beds, reverse swells, and risers mark the intro transition.", "status": "implemented", "trackIds": ["fx"]},
    {"id": "verse-clap", "section": "Intro", "label": "Clap into the verse", "detail": "The section change gets a dedicated clap impact and reverse pickup.", "status": "implemented", "trackIds": ["clap-stack", "fx"]},
    {"id": "verse-sub", "section": "Intro", "label": "Sub bass and reverse transition", "detail": "Low-end support appears around the verse handoff so the drop energy feels earned.", "status": "implemented", "trackIds": ["bass", "fx"]},
    {"id": "guitar-layer", "section": "Verse", "label": "Guitar-bass style verse sound", "detail": "A muted synthetic guitar layer gives the verse movement while staying light.", "status": "implemented", "trackIds": ["guitar-bass"]},
    {"id": "verse-drums", "section": "Verse", "label": "Kick rhythm, snare, and hi-hat trap beat", "detail": "The verse pocket uses a simple Marsh-style kick bounce, clap backbeat, and crisp hats.", "status": "implemented", "trackIds": ["drums", "clap-stack"]},
    {"id": "build-drums", "section": "Build", "label": "Build snares, claps, and different kick", "detail": "The build swaps to rising snare rolls with a simpler kick pattern that opens space for tension.", "status": "implemented", "trackIds": ["drums", "clap-stack"]},
    {"id": "build-fx", "section": "Build", "label": "Downlifters, chains, riser", "detail": "Noise lifts, chain texture, downlifters, and impacts make the build feel expensive.", "status": "implemented", "trackIds": ["fx"]},
    {"id": "build-frozen", "section": "Build", "label": "Rendered bass for CPU", "detail": "A separate printed build-bass lane mirrors the lift notes so the section can stay clean.", "status": "implemented", "trackIds": ["frozen-build-bass"]},
    {"id": "build-lead", "section": "Build", "label": "Filled-in drop lead from intro melody", "detail": "The hook is teased in shorter phrases before the final drop opens up.", "status": "implemented", "trackIds": ["lead", "lead-double"]},
    {"id": "build-filter", "section": "Build", "label": "Automated filter", "detail": "A rendered filter lane gives the build a visible sweep and brighter macro rise.", "status": "implemented", "trackIds": ["filter-automation"]},
    {"id": "drop-bass", "section": "Drop", "label": "Fat drop bass plus sub bass", "detail": "The drop bass doubles the chord rhythm with both sub weight and bright mid grit.", "status": "implemented", "trackIds": ["bass"]},
    {"id": "mix-eq", "section": "Mix", "label": "EQ out lower frequencies", "detail": "Leads, doubles, and upper layers keep the low end out of the bass lane.", "status": "implemented", "trackIds": ["lead", "lead-double", "chords"]},
    {"id": "drop-drums", "section": "Drop", "label": "Drop trap drums", "detail": "Kick, snare, clap, and hats are arranged to support the supersaw stabs without overfilling the grid.", "status": "implemented", "trackIds": ["drums", "clap-stack"]},
    {"id": "hat-ride", "section": "Drop", "label": "Speed-up hats or ride variation", "detail": "The second drop escalates with faster hats, extra fills, ride hits, and crashes.", "status": "implemented", "trackIds": ["hat-ride"]},
    {"id": "crowd", "section": "Drop", "label": "Crowd effect sidechained to kick", "detail": "Crowd air blooms under the second drop and ducks around each kick for motion.", "status": "implemented", "trackIds": ["crowd-sidechain", "ghost-sidechain"]},
    {"id": "lead-double", "section": "Advanced", "label": "Wide lead double support", "detail": "A detuned octave double adds width without taking over the center of the hook.", "status": "implemented", "trackIds": ["lead-double"]},
    {"id": "clap-stack", "section": "Advanced", "label": "Layered clap/snare stack", "detail": "Separate transient layers let the clap bus feel brighter and larger than a single one-shot.", "status": "implemented", "trackIds": ["clap-stack"]},
    {"id": "ghost-key", "section": "Advanced", "label": "Ghost sidechain key lane", "detail": "Ghost Key gives the project a dedicated trigger lane for ducking synths and FX independently from the audible kick.", "status": "implemented", "trackIds": ["ghost-sidechain"]},
    {"id": "sparkle", "section": "Advanced", "label": "Ear-candy fills and transition sparkle", "detail": "Bell fills, reverse tails, and bright pitch effects keep the drop-to-drop flow alive.", "status": "implemented", "trackIds": ["ear-candy", "fx"]},
    {"id": "arrangement", "section": "Foundation", "label": "Full intro, verse, build, drop arrangement", "detail": "The arrangement covers intro, verse, drop one, break, build, final drop, and outro as a full portable project file.", "status": "implemented", "trackIds": ["drums", "bass", "chords", "lead", "fx"]},
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


def adsr(n: int, attack: float = 0.005, decay: float = 0.08, sustain: float = 0.7, release: float = 0.12) -> np.ndarray:
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


def highpass_noise(n: int) -> np.ndarray:
    x = rng.standard_normal(n).astype(np.float32)
    y = np.empty_like(x)
    y[0] = x[0]
    y[1:] = x[1:] - 0.94 * x[:-1]
    return y


def saw(freq: float, dur: float, phase: float = 0.0) -> np.ndarray:
    n = max(1, int(dur * SR))
    t = np.arange(n, dtype=np.float32) / SR
    p = (freq * t + phase) % 1.0
    return (2.0 * p - 1.0).astype(np.float32)


def square_from_phase(phase: np.ndarray) -> np.ndarray:
    return np.where((phase % 1.0) < 0.5, 1.0, -1.0).astype(np.float32)


def synth_supersaw(freq: float, dur: float, bright: float = 0.7, stab: bool = False) -> np.ndarray:
    n = max(1, int(dur * SR))
    t = np.arange(n, dtype=np.float32) / SR
    out = np.zeros(n, dtype=np.float32)
    detunes = [-13.0, -7.0, -3.0, 0.0, 4.0, 8.0, 14.0]
    for idx, cents in enumerate(detunes):
        out += saw(freq * (2.0 ** (cents / 1200.0)), dur, phase=0.13 * idx)
    out /= len(detunes)
    out += 0.18 * np.sin(2.0 * np.pi * freq * 0.5 * t).astype(np.float32)
    out = one_pole_lowpass(out, 1600.0 + 4800.0 * bright)
    env = adsr(n, attack=0.01 if stab else 0.18, decay=0.12 if stab else 0.70, sustain=0.54 if stab else 0.78, release=0.12 if stab else 0.95)
    return (out * env).astype(np.float32)


def synth_bass(freq: float, dur: float, tone: float = 0.5) -> np.ndarray:
    n = max(1, int(dur * SR))
    t = np.arange(n, dtype=np.float32) / SR
    phase = np.cumsum(np.full(n, freq, dtype=np.float32)) / SR
    sine = np.sin(2.0 * np.pi * phase).astype(np.float32)
    sub = np.sin(2.0 * np.pi * phase * 0.5).astype(np.float32) * 0.15
    square = square_from_phase(phase * 2.0) * (0.14 + tone * 0.10)
    click = highpass_noise(n) * np.exp(-t * 70.0).astype(np.float32) * 0.05
    env = adsr(n, attack=0.003, decay=0.07, sustain=0.82, release=0.08)
    return (0.86 * sine + sub + square + click) * env


def synth_square_lead(freq: float, dur: float, soft: bool = False) -> np.ndarray:
    n = max(1, int(dur * SR))
    t = np.arange(n, dtype=np.float32) / SR
    vibrato = 1.0 + 0.0035 * np.sin(2.0 * np.pi * 5.2 * t)
    phase = np.cumsum((freq * vibrato).astype(np.float32)) / SR
    square = square_from_phase(phase)
    tri = (2.0 * np.abs(2.0 * (phase % 1.0) - 1.0) - 1.0).astype(np.float32)
    sine = np.sin(2.0 * np.pi * phase).astype(np.float32)
    out = 0.52 * square + 0.30 * tri + 0.18 * sine
    out = one_pole_lowpass(out, 2400.0 if soft else 4200.0)
    env = adsr(n, attack=0.010, decay=0.07, sustain=0.60 if soft else 0.74, release=0.10)
    return (out * env).astype(np.float32)


def synth_lead_double(freq: float, dur: float) -> np.ndarray:
    n = max(1, int(dur * SR))
    t = np.arange(n, dtype=np.float32) / SR
    detunes = [-11.0, -5.0, 4.0, 10.0]
    out = np.zeros(n, dtype=np.float32)
    for idx, cents in enumerate(detunes):
        out += saw(freq * (2.0 ** (cents / 1200.0)), dur, phase=0.15 * idx)
    out /= len(detunes)
    out += 0.14 * np.sin(2.0 * np.pi * freq * 2.0 * t).astype(np.float32)
    out = one_pole_lowpass(out, 5200.0)
    env = adsr(n, attack=0.012, decay=0.08, sustain=0.66, release=0.16)
    return (out * env).astype(np.float32)


def synth_pluck(freq: float, dur: float) -> np.ndarray:
    n = max(1, int(dur * SR))
    t = np.arange(n, dtype=np.float32) / SR
    phase = np.cumsum(np.full(n, freq, dtype=np.float32)) / SR
    out = 0.68 * np.sin(2.0 * np.pi * phase) + 0.32 * saw(freq * 2.0, dur)
    env = np.exp(-t * 6.6).astype(np.float32)
    out = one_pole_lowpass((out * env).astype(np.float32), 3600.0)
    return out


def synth_muted_guitar(freq: float, dur: float) -> np.ndarray:
    n = max(1, int(dur * SR))
    t = np.arange(n, dtype=np.float32) / SR
    phase = np.cumsum(np.full(n, freq, dtype=np.float32)) / SR
    tri = (2.0 * np.abs(2.0 * (phase % 1.0) - 1.0) - 1.0).astype(np.float32)
    muted = one_pole_lowpass(saw(freq * 2.0, dur, phase=0.29), 1350.0)
    pick = highpass_noise(n) * np.exp(-t * 54.0).astype(np.float32)
    body = np.sin(2.0 * np.pi * freq * 0.5 * t).astype(np.float32) * np.exp(-t * 4.0)
    palm = np.exp(-t * 6.2).astype(np.float32)
    return (0.50 * tri + 0.28 * muted + 0.12 * pick + 0.22 * body) * palm


def kick() -> np.ndarray:
    dur = 0.60
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    freq = 45.0 + 115.0 * np.exp(-t * 18.0)
    phase = np.cumsum(freq) / SR
    body = np.sin(2.0 * np.pi * phase).astype(np.float32) * np.exp(-t * 7.0)
    thump = np.sin(2.0 * np.pi * 52.0 * t).astype(np.float32) * np.exp(-t * 4.2)
    click = highpass_noise(n) * np.exp(-t * 85.0).astype(np.float32)
    return (1.18 * body + 0.32 * thump + 0.11 * click).astype(np.float32)


def snare(clap: bool = False) -> np.ndarray:
    dur = 0.48 if clap else 0.42
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    noise = highpass_noise(n)
    env = np.exp(-t * (10.0 if clap else 14.0)).astype(np.float32)
    tone = np.sin(2.0 * np.pi * 188.0 * t).astype(np.float32) * np.exp(-t * 18.0)
    out = noise * env * (0.65 if clap else 0.48) + tone * 0.30
    if clap:
        for delay in [0.011, 0.024, 0.039]:
            d = int(delay * SR)
            if d < n:
                out[d:] += noise[:-d] * np.exp(-t[:-d] * 18.0).astype(np.float32) * 0.15
    return out.astype(np.float32)


def hat(open_hat: bool = False) -> np.ndarray:
    dur = 0.22 if open_hat else 0.075
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    noise = highpass_noise(n)
    env = np.exp(-t * (11.0 if open_hat else 50.0)).astype(np.float32)
    return (noise * env * (0.20 if open_hat else 0.13)).astype(np.float32)


def ride() -> np.ndarray:
    dur = 0.72
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    noise = highpass_noise(n)
    bell = (
        np.sin(2.0 * np.pi * 2700.0 * t)
        + 0.55 * np.sin(2.0 * np.pi * 4050.0 * t)
        + 0.28 * np.sin(2.0 * np.pi * 6120.0 * t)
    ).astype(np.float32)
    env = np.exp(-t * 4.0).astype(np.float32)
    return (0.15 * noise + 0.11 * bell) * env


def crash() -> np.ndarray:
    dur = 2.4
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    noise = highpass_noise(n)
    shimmer = np.sin(2.0 * np.pi * (6100.0 + 1300.0 * np.sin(2.0 * np.pi * 0.19 * t)) * t).astype(np.float32)
    env = np.exp(-t * 1.18).astype(np.float32)
    return (0.22 * noise * env + 0.024 * shimmer * env).astype(np.float32)


def riser(dur: float, start_freq: float = 180.0, end_freq: float = 1400.0) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    freqs = np.linspace(start_freq, end_freq, n, dtype=np.float32)
    phase = np.cumsum(freqs) / SR
    tone = np.sin(2.0 * np.pi * phase).astype(np.float32)
    noise = one_pole_lowpass(highpass_noise(n), 5200.0)
    env = np.linspace(0.0, 1.0, n, dtype=np.float32) ** 1.5
    wobble = 0.70 + 0.30 * np.sin(2.0 * np.pi * (4.0 + 8.0 * t / max(dur, 0.001)) * t)
    return (0.24 * tone + 0.18 * noise) * env * wobble.astype(np.float32)


def downlifter(dur: float = 1.6) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    freqs = np.linspace(940.0, 90.0, n, dtype=np.float32)
    phase = np.cumsum(freqs) / SR
    tone = np.sin(2.0 * np.pi * phase).astype(np.float32)
    noise = highpass_noise(n) * np.exp(-t * 1.8).astype(np.float32)
    return (0.28 * tone * np.exp(-t * 1.4).astype(np.float32) + 0.12 * noise).astype(np.float32)


def impact() -> np.ndarray:
    n = int(1.1 * SR)
    t = np.arange(n, dtype=np.float32) / SR
    low = np.sin(2.0 * np.pi * 46.0 * t).astype(np.float32) * np.exp(-t * 3.7).astype(np.float32)
    boom = np.sin(2.0 * np.pi * (62.0 + 60.0 * np.exp(-t * 8.0)) * t).astype(np.float32)
    noise = highpass_noise(n) * np.exp(-t * 9.0).astype(np.float32)
    return (0.72 * low + 0.26 * boom * np.exp(-t * 5.0).astype(np.float32) + 0.08 * noise).astype(np.float32)


def ghost_pulse() -> np.ndarray:
    dur = 0.12
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    click = highpass_noise(n) * np.exp(-t * 120.0).astype(np.float32)
    body = np.sin(2.0 * np.pi * 62.0 * t).astype(np.float32) * np.exp(-t * 38.0).astype(np.float32)
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
    out = np.zeros(n, dtype=np.float32)
    segments = 24
    for segment in range(segments):
        start = int(segment * n / segments)
        end = int((segment + 1) * n / segments)
        cutoff = 260.0 + 4200.0 * ((segment + 1) / segments) ** 1.7
        out[start:end] = one_pole_lowpass(tone[start:end], cutoff)
    env = (0.2 + 0.8 * np.linspace(0.0, 1.0, n, dtype=np.float32)) * (0.9 + 0.1 * np.sin(2.0 * np.pi * 4.0 * t))
    return (out * env.astype(np.float32) * 0.35).astype(np.float32)


def apply_ducking(stem: np.ndarray, amount: float = 0.4, release: float = 0.25) -> np.ndarray:
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
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(2)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SR)
        wav_file.writeframes(pcm16.tobytes())


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


def load_blueprint() -> dict[str, object]:
    for path in PROJECT_PATHS:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return {
        "format": "neon-studio-project",
        "formatVersion": 1,
        "portable": True,
        "id": "neon-solitude",
        "name": "Neon Solitude",
        "createdAt": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "updatedAt": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "snapshot": {
            "tracks": DEFAULT_TRACK_LAYOUT,
            "recipe": DEFAULT_RECIPE,
            "controls": {},
            "notes": [],
            "selectedTrackId": "lead",
            "selectedClipId": "lead-16",
            "activeView": "playlist",
            "patternIndex": 1,
            "arrangementMode": "song",
            "loopEnabled": True,
            "loopStartBar": 16,
            "loopEndBar": 32,
            "snap": "1/4",
            "swing": 18,
        },
    }


def merge_track_layout(blueprint_tracks: list[dict[str, object]] | None) -> list[dict[str, object]]:
    defaults = {track["id"]: track for track in DEFAULT_TRACK_LAYOUT}
    if not blueprint_tracks:
        return json.loads(json.dumps(DEFAULT_TRACK_LAYOUT))
    merged: list[dict[str, object]] = []
    seen: set[str] = set()
    for track in blueprint_tracks:
        track_id = str(track.get("id", ""))
        if track_id in defaults:
            base = json.loads(json.dumps(defaults[track_id]))
            base["color"] = track.get("color") or defaults[track_id].get("color") or TRACK_COLORS.get(track_id, "#7dd3fc")
            merged.append(base)
            seen.add(track_id)
    for track in DEFAULT_TRACK_LAYOUT:
        if track["id"] not in seen:
            merged.append(json.loads(json.dumps(track)))
    for track in merged:
        track["file"] = f"/api/audio/{ASSET_FILES[track['id']]}"
        track["color"] = track.get("color") or TRACK_COLORS[track["id"]]
    return merged


def build_controls(tracks: list[dict[str, object]], blueprint_controls: dict[str, object] | None) -> dict[str, object]:
    controls: dict[str, object] = {}
    for track in tracks:
        track_id = str(track["id"])
        current = dict((blueprint_controls or {}).get(track_id, {}))
        current.update({
            "gain": track.get("gain", current.get("gain", 0.8)),
            "pan": track.get("pan", current.get("pan", 0.0)),
            "mute": current.get("mute", False),
            "solo": current.get("solo", False),
            "arm": current.get("arm", False),
            "sendA": current.get("sendA", 0.18 if track_id in {"lead", "lead-double", "ear-candy", "chords"} else 0.08),
            "sendB": current.get("sendB", 0.12 if track_id in {"fx", "crowd-sidechain", "ear-candy"} else 0.04),
        })
        controls[track_id] = current
    return controls


def build_preview_notes(hook: list[list[tuple[float, float, int]]]) -> list[dict[str, object]]:
    notes: list[dict[str, object]] = []
    for bar_offset in range(8):
        pattern = hook[bar_offset % len(hook)]
        octave = 12 if bar_offset >= 4 and bar_offset % 4 in {1, 2} else 0
        for onset, dur, note in pattern:
            notes.append({
                "id": f"lead-preview-{bar_offset}-{int(onset * 100)}",
                "beat": bar_offset * 4 + onset,
                "duration": dur,
                "note": note + octave,
                "velocity": 0.84 if bar_offset < 4 else 0.88,
                "color": TRACK_COLORS["lead"],
            })
    return notes


def update_project_files(hook: list[list[tuple[float, float, int]]]) -> None:
    blueprint = load_blueprint()
    snapshot = dict(blueprint.get("snapshot", {}))
    blueprint_tracks = snapshot.get("tracks")
    tracks = merge_track_layout(blueprint_tracks if isinstance(blueprint_tracks, list) else None)
    recipe = snapshot.get("recipe")
    if not isinstance(recipe, list) or not recipe:
        recipe = DEFAULT_RECIPE
    notes = build_preview_notes(hook)
    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    assets = [{"trackId": track_id, "file": f"/api/audio/{file_name}"} for track_id, file_name in ASSET_FILES.items()]

    for path in PROJECT_PATHS:
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
        else:
            raw = dict(blueprint)
        current_snapshot = dict(raw.get("snapshot", {}))
        controls = build_controls(tracks, current_snapshot.get("controls") if isinstance(current_snapshot.get("controls"), dict) else None)
        raw.update({
            "format": "neon-studio-project",
            "formatVersion": 1,
            "portable": True,
            "assetMode": "external",
            "id": "neon-solitude",
            "name": "Neon Solitude",
            "description": "Original bright future-bass/festival EDM project rebuilt in a Marshmello-inspired Alone lane without reusing the commercial melody.",
            "keyCenter": "E minor / G major",
            "createdAt": raw.get("createdAt") or blueprint.get("createdAt") or now,
            "updatedAt": now,
            "assets": assets,
        })
        current_snapshot.update({
            "version": 3,
            "bpm": BPM,
            "swing": 18,
            "snap": "1/4",
            "loopEnabled": True,
            "loopStartBar": 16,
            "loopEndBar": 32,
            "tracks": tracks,
            "controls": controls,
            "notes": notes,
            "selectedTrackId": "lead",
            "selectedClipId": "lead-16",
            "activeView": "playlist",
            "patternIndex": 1,
            "arrangementMode": "song",
            "recipe": recipe,
        })
        raw["snapshot"] = current_snapshot
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")


def render() -> None:
    EXPORTS.mkdir(exist_ok=True)
    MIDI_DIR.mkdir(exist_ok=True)

    stems = {track_id.replace("-", "_"): stereo_buffer() for track_id in ASSET_FILES}
    midi_chords: list[tuple[float, float, int, int]] = []
    midi_bass: list[tuple[float, float, int, int]] = []
    midi_lead: list[tuple[float, float, int, int]] = []
    midi_drums: list[tuple[float, float, int, int]] = []
    midi_guitar: list[tuple[float, float, int, int]] = []
    midi_hat: list[tuple[float, float, int, int]] = []
    midi_double: list[tuple[float, float, int, int]] = []
    midi_clap: list[tuple[float, float, int, int]] = []

    progression = [
        {"name": "Em9", "notes": [52, 55, 59, 62, 66], "root": 28},
        {"name": "Cmaj7", "notes": [48, 52, 55, 59, 64], "root": 36},
        {"name": "Gadd9", "notes": [43, 50, 55, 59, 62], "root": 31},
        {"name": "Dsus2", "notes": [50, 57, 62, 66, 69], "root": 38},
    ]

    def chord_for_bar(bar: int) -> dict[str, object]:
        return progression[bar % len(progression)]

    # Long intro/break pads.
    for bar in list(range(0, 16)) + list(range(32, 40)) + list(range(64, 72)):
        chord = chord_for_bar(bar)
        bright = 0.24 if bar < 8 else 0.38
        gain = 0.070 if bar < 8 else 0.090
        if bar >= 64:
            gain *= max(0.18, 1.0 - (bar - 64) / 8.0)
        for idx, note in enumerate(chord["notes"]):
            schedule_note(
                stems["chords"],
                midi_chords,
                synth_supersaw,
                bar_beat(bar),
                3.85,
                int(note),
                62,
                gain,
                pan=-0.55 + idx * 0.275,
                audio_extra_beats=0.60,
                bright=bright,
                stab=False,
            )

    # Drop and final-drop chord stabs.
    stab_rhythm = [(0.0, 0.82), (1.45, 0.48), (2.0, 0.58), (3.05, 0.72)]
    for bar in list(range(16, 32)) + list(range(48, 64)):
        chord = chord_for_bar(bar)
        for onset, dur in stab_rhythm:
            for idx, note in enumerate(chord["notes"]):
                schedule_note(
                    stems["chords"],
                    midi_chords,
                    synth_supersaw,
                    bar_beat(bar, onset),
                    dur,
                    int(note),
                    92,
                    0.178,
                    pan=-0.62 + idx * 0.31,
                    audio_extra_beats=0.18,
                    bright=0.92,
                    stab=True,
                )

    # Build pad opening up.
    for bar in range(40, 48):
        chord = chord_for_bar(bar)
        lift = (bar - 40) / 8.0
        for idx, note in enumerate(chord["notes"]):
            schedule_note(
                stems["chords"],
                midi_chords,
                synth_supersaw,
                bar_beat(bar),
                3.72,
                int(note),
                72 + int(lift * 16),
                0.090 + lift * 0.052,
                pan=-0.52 + idx * 0.26,
                audio_extra_beats=0.35,
                bright=0.45 + lift * 0.44,
                stab=False,
            )

    # Intro melody and break hook.
    hook = [
        [(0.00, 0.46, 76), (0.52, 0.42, 79), (1.05, 0.70, 83), (2.00, 0.42, 86), (2.52, 0.38, 83), (3.04, 0.68, 79)],
        [(0.00, 0.42, 84), (0.50, 0.44, 83), (1.02, 0.54, 79), (1.72, 0.38, 76), (2.18, 0.42, 81), (2.72, 0.68, 79)],
        [(0.00, 0.40, 83), (0.46, 0.42, 86), (0.98, 0.74, 88), (2.00, 0.40, 86), (2.48, 0.42, 83), (3.00, 0.70, 81)],
        [(0.00, 0.44, 79), (0.55, 0.38, 83), (1.04, 0.38, 81), (1.54, 0.38, 79), (2.12, 0.78, 76), (3.08, 0.40, 74), (3.55, 0.34, 76)],
    ]

    def add_hook(start_bar: int, bars: int, gain: float, variation: int = 0, soft: bool = False) -> None:
        for bar_offset in range(bars):
            pattern = hook[bar_offset % len(hook)]
            transpose = 12 if bar_offset >= 8 and variation else 0
            for onset, dur, note in pattern:
                note_out = note + transpose
                if variation and bar_offset % 8 == 7 and onset > 2.5:
                    note_out += 2
                schedule_note(
                    stems["lead"],
                    midi_lead,
                    synth_square_lead,
                    bar_beat(start_bar + bar_offset, onset),
                    dur,
                    note_out,
                    104 if gain > 0.09 else 80,
                    gain,
                    pan=0.05 if (bar_offset + int(onset * 10)) % 2 else -0.05,
                    audio_extra_beats=0.10,
                    soft=soft,
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
                    stems["lead_double"],
                    midi_double,
                    synth_lead_double,
                    bar_beat(start_bar + bar_offset, onset),
                    max(0.24, dur * 0.92),
                    doubled_note,
                    86,
                    gain,
                    pan=-0.42 if (bar_offset + int(onset * 10)) % 2 else 0.42,
                    audio_extra_beats=0.12,
                )

    # Sparse intro melody.
    add_hook(4, 12, 0.078, variation=0, soft=True)
    add_hook(16, 16, 0.182, variation=0, soft=False)
    add_hook(32, 8, 0.070, variation=0, soft=True)
    add_hook(48, 16, 0.194, variation=1, soft=False)
    add_hook_double(16, 16, 0.138, variation=0)
    add_hook_double(48, 16, 0.152, variation=1)

    # Verse and build guitar-bass layer.
    guitar_rhythm = [(0.0, 0.42), (0.74, 0.30), (1.45, 0.38), (2.0, 0.46), (3.05, 0.34)]
    for bar in list(range(8, 16)) + list(range(40, 48)):
        root = int(chord_for_bar(bar)["root"]) + 12
        lift = 0.25 if bar >= 40 else 0.0
        for onset, dur in guitar_rhythm:
            schedule_note(
                stems["guitar_bass"],
                midi_guitar,
                synth_muted_guitar,
                bar_beat(bar, onset),
                dur,
                root + (12 if onset > 2.8 and bar % 4 == 3 else 0),
                76 + int(lift * 24),
                0.110 + lift * 0.035,
                pan=-0.08,
                audio_extra_beats=0.04,
            )

    # Bass.
    for bar in range(8, 16):
        root = int(chord_for_bar(bar)["root"]) + 12
        schedule_note(stems["bass"], midi_bass, synth_bass, bar_beat(bar), 1.45, root, 72, 0.100)
        schedule_note(stems["bass"], midi_bass, synth_bass, bar_beat(bar, 2.0), 1.45, root, 70, 0.090)
    for bar in list(range(16, 32)) + list(range(48, 64)):
        root = int(chord_for_bar(bar)["root"])
        for onset, dur in stab_rhythm:
            schedule_note(
                stems["bass"],
                midi_bass,
                synth_bass,
                bar_beat(bar, onset),
                dur,
                root,
                106,
                0.265,
                audio_extra_beats=0.04,
            )
        if bar % 4 == 3:
            schedule_note(stems["bass"], midi_bass, synth_bass, bar_beat(bar, 3.55), 0.25, root + 12, 88, 0.12, audio_extra_beats=0.03)
    for bar in range(40, 48):
        root = int(chord_for_bar(bar)["root"]) + 12
        lift = (bar - 40) / 8.0
        for onset, dur in [(0.0, 1.35), (2.0, 1.35), (3.35, 0.32)]:
            schedule_note(
                stems["frozen_build_bass"],
                midi_bass,
                synth_bass,
                bar_beat(bar, onset),
                dur,
                root,
                82 + int(lift * 18),
                0.118 + lift * 0.045,
                audio_extra_beats=0.03,
            )

    # Build filter macro.
    for bar in range(40, 48):
        root = int(chord_for_bar(bar)["root"]) + 24
        add_mono(
            stems["filter_automation"],
            beat_to_seconds(bar_beat(bar)),
            filter_sweep(4 * BEAT, note_to_freq(root)),
            gain=0.24 + 0.04 * ((bar - 40) / 8.0),
        )

    # Drums.
    k = kick()
    s = snare(False)
    c = snare(True)
    h = hat(False)
    rd = ride()
    cr = crash()
    gp = ghost_pulse()
    for bar in range(8, 16):
        for beat in [0.0, 1.48, 2.72]:
            add_mono(stems["drums"], beat_to_seconds(bar_beat(bar, beat)), k, gain=0.70)
            midi_drums.append((bar_beat(bar, beat), 0.18, 36, 90))
        for beat in [1.0, 3.0]:
            add_mono(stems["drums"], beat_to_seconds(bar_beat(bar, beat)), s, gain=0.42, pan=-0.06)
            add_mono(stems["clap_stack"], beat_to_seconds(bar_beat(bar, beat + 0.018)), c, gain=0.30, pan=0.18)
            midi_drums.append((bar_beat(bar, beat), 0.12, 38, 74))
            midi_clap.append((bar_beat(bar, beat), 0.12, 39, 66))
        for step in range(8):
            gain = 0.42 if step % 2 else 0.32
            add_mono(stems["drums"], beat_to_seconds(bar_beat(bar, step * 0.5)), h, gain=gain, pan=0.22)
            midi_drums.append((bar_beat(bar, step * 0.5), 0.06, 42, 50 if step % 2 else 40))

    drop_bars = list(range(16, 32)) + list(range(48, 64))
    for bar in drop_bars:
        final = bar >= 48
        for beat in [0.0, 1.45, 2.0, 3.05]:
            add_mono(stems["drums"], beat_to_seconds(bar_beat(bar, beat)), k, gain=0.96 if not final else 1.0)
            add_mono(stems["ghost_sidechain"], beat_to_seconds(bar_beat(bar, beat)), gp, gain=0.46)
            midi_drums.append((bar_beat(bar, beat), 0.18, 36, 112))
        add_mono(stems["drums"], beat_to_seconds(bar_beat(bar, 2.0)), s, gain=0.92)
        add_mono(stems["drums"], beat_to_seconds(bar_beat(bar, 2.02)), c, gain=0.42, pan=-0.05)
        add_mono(stems["clap_stack"], beat_to_seconds(bar_beat(bar, 1.99)), s, gain=0.34, pan=-0.18)
        add_mono(stems["clap_stack"], beat_to_seconds(bar_beat(bar, 2.02)), c, gain=0.58, pan=0.20)
        add_mono(stems["clap_stack"], beat_to_seconds(bar_beat(bar, 2.05)), c, gain=0.22, pan=-0.34)
        midi_drums.append((bar_beat(bar, 2.0), 0.20, 38, 112))
        midi_clap.append((bar_beat(bar, 2.0), 0.18, 39, 92))
        for step in range(8):
            vel = 58 + (14 if step % 2 else 0)
            add_mono(stems["drums"], beat_to_seconds(bar_beat(bar, step * 0.5)), h, gain=0.38 + 0.09 * (step % 2), pan=0.28)
            midi_hat.append((bar_beat(bar, step * 0.5), 0.08, 42, vel))
        if bar % 4 == 3:
            for beat in [3.5, 3.75]:
                add_mono(stems["drums"], beat_to_seconds(bar_beat(bar, beat)), h, gain=0.58, pan=-0.32)
                midi_hat.append((bar_beat(bar, beat), 0.06, 42, 80))
        if bar in [16, 24, 48, 56]:
            add_mono(stems["drums"], beat_to_seconds(bar_beat(bar)), cr, gain=0.76, pan=-0.18)
            midi_drums.append((bar_beat(bar), 1.0, 49, 96))
        if final:
            for step in range(16):
                if step % 4 in {1, 3} or bar % 4 == 3:
                    add_mono(stems["hat_ride"], beat_to_seconds(bar_beat(bar, step * 0.25)), h, gain=0.22, pan=-0.32 if step % 2 else 0.32)
                    midi_hat.append((bar_beat(bar, step * 0.25), 0.05, 42, 56))
            if bar >= 56:
                for beat in [0.0, 1.0, 2.0, 3.0]:
                    add_mono(stems["hat_ride"], beat_to_seconds(bar_beat(bar, beat)), rd, gain=0.55, pan=-0.34)
                    midi_hat.append((bar_beat(bar, beat), 0.18, 51, 82))
            if bar in [48, 52, 56, 60]:
                add_mono(stems["hat_ride"], beat_to_seconds(bar_beat(bar)), cr, gain=0.55, pan=0.22)
                midi_hat.append((bar_beat(bar), 1.0, 49, 92))

    # Build drums.
    for bar in range(40, 48):
        add_mono(stems["drums"], beat_to_seconds(bar_beat(bar)), k, gain=0.72)
        add_mono(stems["ghost_sidechain"], beat_to_seconds(bar_beat(bar)), gp, gain=0.42)
        midi_drums.append((bar_beat(bar), 0.18, 36, 94))
        density = 0.5 if bar < 44 else 0.25
        steps = int(4 / density)
        for step in range(steps):
            beat = step * density
            lift = (bar - 40 + step / max(steps, 1)) / 8.0
            add_mono(stems["drums"], beat_to_seconds(bar_beat(bar, beat)), s, gain=0.22 + lift * 0.55, pan=-0.12 if step % 2 else 0.12)
            add_mono(stems["clap_stack"], beat_to_seconds(bar_beat(bar, beat)), c if step % 2 else s, gain=0.12 + lift * 0.34, pan=0.22 if step % 2 else -0.22)
            midi_drums.append((bar_beat(bar, beat), 0.10, 38, int(45 + lift * 55)))
            midi_clap.append((bar_beat(bar, beat), 0.10, 39 if step % 2 else 38, int(44 + lift * 50)))
            if step % 2 == 0:
                add_mono(stems["drums"], beat_to_seconds(bar_beat(bar, beat)), h, gain=0.32 + lift * 0.28, pan=0.24)
                midi_hat.append((bar_beat(bar, beat), 0.05, 42, int(48 + lift * 35)))

    # FX and transitions.
    for bar in [16, 32, 40, 48, 64]:
        add_mono(stems["fx"], beat_to_seconds(bar_beat(bar)), impact(), gain=0.70, pan=0.0)
        add_mono(stems["fx"], beat_to_seconds(bar_beat(bar, 0.05)), downlifter(), gain=0.52, pan=0.15)
    add_mono(stems["fx"], beat_to_seconds(bar_beat(0)), crowd_swell(8 * 4 * BEAT), gain=0.15)
    add_mono(stems["fx"], beat_to_seconds(bar_beat(12)), riser(4 * BEAT, 180, 760), gain=0.48)
    add_mono(stems["fx"], beat_to_seconds(bar_beat(12)), riser(4 * BEAT, 240, 2200), gain=0.18)
    add_mono(stems["fx"], beat_to_seconds(bar_beat(15, 3.20)), downlifter(0.75), gain=0.24, pan=-0.28)
    add_mono(stems["fx"], beat_to_seconds(bar_beat(40)), riser(8 * 4 * BEAT, 160, 1450), gain=0.62)
    add_mono(stems["fx"], beat_to_seconds(bar_beat(47, 3.65)), c, gain=1.0)
    add_mono(stems["fx"], beat_to_seconds(bar_beat(40)), chain_noise(8 * 4 * BEAT), gain=0.88, pan=-0.24)

    # Ear candy and crowd.
    for bar in [15, 31, 47, 63]:
        add_mono(stems["ear_candy"], beat_to_seconds(bar_beat(bar, 3.15)), riser(0.8 * BEAT, 520, 2100), gain=0.26, pan=-0.35)
        add_mono(stems["ear_candy"], beat_to_seconds(bar_beat(bar, 3.55)), downlifter(0.65), gain=0.30, pan=0.36)
    for bar in [14, 30, 46, 62]:
        chord = chord_for_bar(bar)
        for idx, note in enumerate(list(chord["notes"])[-3:]):
            add_mono(
                stems["ear_candy"],
                beat_to_seconds(bar_beat(bar, 2.5 + idx * 0.25)),
                synth_pluck(note_to_freq(int(note) + 24), 0.32 * BEAT),
                gain=0.11,
                pan=-0.45 + idx * 0.45,
            )
    for bar in [16, 24, 48, 56]:
        add_mono(stems["ear_candy"], beat_to_seconds(bar_beat(bar, 0.08)), crash(), gain=0.22, pan=0.42)
    add_mono(stems["crowd_sidechain"], beat_to_seconds(bar_beat(48)), crowd_swell(16 * 4 * BEAT), gain=0.96)

    # Mix processing.
    apply_ducking(stems["chords"], amount=0.36, release=0.22)
    apply_ducking(stems["bass"], amount=0.24, release=0.17)
    apply_ducking(stems["guitar_bass"], amount=0.18, release=0.16)
    apply_ducking(stems["frozen_build_bass"], amount=0.30, release=0.18)
    apply_ducking(stems["filter_automation"], amount=0.44, release=0.24)
    apply_ducking(stems["crowd_sidechain"], amount=0.68, release=0.30)
    apply_ducking(stems["lead_double"], amount=0.42, release=0.22)
    apply_ducking(stems["clap_stack"], amount=0.12, release=0.12)
    apply_ducking(stems["ear_candy"], amount=0.36, release=0.24)
    add_delay(stems["lead"], delay_beats=0.75, feedback=0.48, wet=0.28, repeats=5)
    add_delay(stems["lead_double"], delay_beats=0.75, feedback=0.34, wet=0.22, repeats=4)
    add_delay(stems["chords"], delay_beats=1.50, feedback=0.30, wet=0.11, repeats=3)
    add_delay(stems["fx"], delay_beats=2.0, feedback=0.30, wet=0.18, repeats=4)
    add_delay(stems["ear_candy"], delay_beats=0.5, feedback=0.42, wet=0.24, repeats=5)

    fade_len = int(2.0 * SR)
    fade = np.linspace(0.0, 1.0, fade_len, dtype=np.float32)
    for stem in stems.values():
        stem[:fade_len] *= fade[:, None]
        stem[-fade_len:] *= fade[::-1, None]

    stem_gains = {
        "drums": 0.80,
        "bass": 0.94,
        "chords": 1.10,
        "lead": 1.22,
        "fx": 0.58,
        "guitar_bass": 0.70,
        "hat_ride": 0.58,
        "frozen_build_bass": 0.76,
        "filter_automation": 0.56,
        "crowd_sidechain": 0.60,
        "lead_double": 0.84,
        "clap_stack": 0.70,
        "ghost_sidechain": 0.12,
        "ear_candy": 0.76,
    }
    mix = np.zeros_like(stems["drums"])
    for name, stem in stems.items():
        mix += stem * stem_gains[name]
    mix = soft_clip(mix, drive=1.28) * 0.91

    write_wav(EXPORTS / "neon_solitude_full_mix.wav", mix)
    for track_id, file_name in ASSET_FILES.items():
        stem_name = track_id.replace("-", "_")
        write_wav(EXPORTS / file_name, soft_clip(stems[stem_name] * stem_gains[stem_name], drive=1.10) * 0.90)

    arrangement_tracks = [
        ("Chords", 0, 81, midi_chords),
        ("Bass", 1, 38, midi_bass),
        ("Lead", 2, 80, midi_lead),
        ("Drums", 9, None, midi_drums),
        ("Guitar Bass", 4, 34, midi_guitar),
        ("Hat Ride", 9, None, midi_hat),
        ("Lead Double", 5, 82, midi_double),
        ("Clap Stack", 9, None, midi_clap),
    ]
    write_midi(MIDI_DIR / "neon_solitude_arrangement.mid", arrangement_tracks)
    write_midi(MIDI_DIR / "neon_solitude_chords.mid", [arrangement_tracks[0]])
    write_midi(MIDI_DIR / "neon_solitude_bass.mid", [arrangement_tracks[1]])
    write_midi(MIDI_DIR / "neon_solitude_lead.mid", [arrangement_tracks[2]])
    write_midi(MIDI_DIR / "neon_solitude_drums.mid", [arrangement_tracks[3]])
    write_midi(MIDI_DIR / "neon_solitude_guitar_bass.mid", [arrangement_tracks[4]])
    write_midi(MIDI_DIR / "neon_solitude_hat_ride.mid", [arrangement_tracks[5]])
    write_midi(MIDI_DIR / "neon_solitude_lead_double.mid", [arrangement_tracks[6]])
    write_midi(MIDI_DIR / "neon_solitude_clap_stack.mid", [arrangement_tracks[7]])

    update_project_files(hook)

    readme = f"""Neon Solitude - future-bass production package

Tempo: {BPM} BPM
Key center: E minor / G major
Length: {TOTAL_BARS} bars, {TOTAL_SECONDS:.1f} seconds including tail

This pass rebuilds the current song into a bright, simple, hook-first
future-bass/festival EDM lane: supersaw chords, square-lead hook, trap drums,
filtered build, crowd air, and widened doubles. The track is original and does
not reuse commercial stems, lyrics, or melody from Marshmello's "Alone".

Generated assets:
- exports/neon_solitude_full_mix.wav
- exports/neon_solitude_*.wav stems
- midi/neon_solitude_arrangement.mid and part MIDI files
- data/projects/neon-solitude.neon.json
- factory/projects/neon-solitude.neon.json
"""
    (ROOT / "README.md").write_text(readme, encoding="utf-8")


if __name__ == "__main__":
    render()
