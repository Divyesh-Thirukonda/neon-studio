#!/usr/bin/env python3
"""Turn a hummed or sung take into piano-roll notes for a Neon Studio track.

The app records a mono WAV after a count-in, so the take starts on a known bar.
This tool tracks the pitch of that take, cuts it into notes, quantises the notes
to the project grid, optionally snaps them into the project key, and emits note
dicts in the exact shape the .neon.json "notes" array uses. "Sing what you want
it to sound like" then becomes a real, undoable edit rather than a note in a log.

CLI:
  python3 tools/hum_to_melody.py --input take.wav --bpm 142 --start-bar 8 --track-id lead
      [--snap 1/8] [--key "E minor"] [--no-key-snap] [--color "#60c8f8"] [--format json|markdown]

Only numpy is used. Pitch tracking reuses estimate_f0 / detect_segments from
vocal_autotune.py so both tools hear the voice the same way.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import wave
from pathlib import Path
from typing import Any, Optional

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from vocal_autotune import (  # noqa: E402
    SR,
    detect_segments,
    estimate_f0,
    freq_to_midi,
    nearest_scale_midi,
    read_wav,
)


# Analysis frame: 25 ms window, 10 ms hop. Short enough that a fast run of
# eighth notes at 142 BPM (211 ms each) still gets ~20 frames per note.
FRAME_SECONDS = 0.025
HOP_SECONDS = 0.010
MEDIAN_FRAMES = 5
MIN_CONFIDENCE = 0.3
MIN_HZ = 80.0
MAX_HZ = 1000.0
# A pitch move must hold this far for this long before we call it a new note;
# otherwise vibrato and scoops would shatter one sung note into many.
JUMP_SEMITONES = 0.6
JUMP_HOLD_FRAMES = 3
GAP_SECONDS = 0.060
# Anything shorter than this is a tracking glitch, not a note anyone sang.
MIN_NOTE_FRAMES = 3
# People hum lower than the lead they are imagining; keep the result in the
# range a lead synth actually lives in.
OCTAVE_LOW = 48
OCTAVE_HIGH = 84
VELOCITY_FLOOR = 0.45
VELOCITY_CEIL = 1.0
DEFAULT_COLOR = "#60c8f8"
NO_VOICE_WARNING = "Nothing voiced was detected — try singing closer to the mic."

SNAP_BEATS = {"1/4": 1.0, "1/8": 0.5, "1/16": 0.25, "1/32": 0.125}
NOTE_PITCH_CLASS = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}
MAJOR_INTERVALS = (0, 2, 4, 5, 7, 9, 11)
MINOR_INTERVALS = (0, 2, 3, 5, 7, 8, 10)
PITCH_NAMES_SHARP = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


# --------------------------------------------------------------------------- keys


def parse_key(text: Optional[str]) -> Optional[dict[str, Any]]:
    """Accept "E minor", "E Minor", "Em", "F# major", "Gb major", "e_minor", "Bbm".

    Returns {"root": pitch class, "mode": "major"|"minor", "name": canonical,
    "scale": set of pitch classes} or None when the text is not a key.
    A bare letter ("E") is read as major; a bare lowercase "m" suffix as minor.
    """
    if not text:
        return None
    match = re.match(
        r"^\s*([a-gA-G])\s*([#b♯♭]?)\s*[-_ ]?\s*(major|maj|minor|min|m)?\s*$",
        text.strip(),
        re.IGNORECASE,
    )
    if not match:
        return None
    letter, accidental, mode_text = match.groups()
    # A bare capital "M" is the jazz shorthand for major ("EM"); bare "m" is minor.
    if mode_text == "M":
        mode_text = "major"
    mode_text = (mode_text or "major").lower()
    root = NOTE_PITCH_CLASS[letter.lower()]
    if accidental in ("#", "♯"):
        root += 1
        accidental = "#"
    elif accidental in ("b", "♭"):
        root -= 1
        accidental = "b"
    root %= 12
    mode = "minor" if mode_text in ("minor", "min", "m") else "major"
    intervals = MINOR_INTERVALS if mode == "minor" else MAJOR_INTERVALS
    return {
        "root": root,
        "mode": mode,
        "name": f"{letter.upper()}{accidental} {mode}",
        "scale": {(root + step) % 12 for step in intervals},
    }


def midi_name(midi: int) -> str:
    return f"{PITCH_NAMES_SHARP[midi % 12]}{midi // 12 - 1}"


# ------------------------------------------------------------------- pitch track


def median_filter(values: np.ndarray, width: int) -> np.ndarray:
    """Odd-width running median with edge padding; fills one-frame dropouts."""
    if len(values) == 0 or width <= 1:
        return values
    half = width // 2
    padded = np.pad(values, (half, half), mode="edge")
    stacked = np.stack([padded[i:i + len(values)] for i in range(width)])
    return np.median(stacked, axis=0)


def refine_f0(audio: np.ndarray, center: int, coarse_hz: float) -> float:
    """Re-read the pitch around `center` with a proper local-peak search.

    estimate_f0 takes the argmax of the autocorrelation from the minimum lag
    upward. For pitches under ~150 Hz the shoulder of the zero-lag peak is
    still higher than the true period peak inside a 25 ms frame, so a low hum
    reads as ~720 Hz. Here a 50 ms window is used and only genuine local
    maxima count, the first one close to the best being the fundamental (the
    later ones are its multiples). Falls back to the coarse value when the
    window is too short or has no peaks.
    """
    half = int(0.025 * SR)
    lo = max(0, center - half)
    hi = min(len(audio), center + half)
    segment = audio[lo:hi].astype(np.float32)
    n = len(segment)
    min_lag = int(SR / MAX_HZ)
    max_lag = min(int(SR / MIN_HZ), n - 2)
    if max_lag - min_lag < 3:
        return coarse_hz
    segment = segment - float(np.mean(segment))
    windowed = segment * np.hanning(n).astype(np.float32)
    spec = np.fft.rfft(windowed, n * 2)
    corr = np.fft.irfft(spec * np.conj(spec))[:n]
    if corr[0] <= 1e-9:
        return coarse_hz
    norm = corr / corr[0]
    region = norm[min_lag:max_lag]
    inner = region[1:-1]
    is_peak = (inner > region[:-2]) & (inner >= region[2:]) & (inner > 0.0)
    peak_indices = np.nonzero(is_peak)[0] + 1
    if len(peak_indices) == 0:
        return coarse_hz
    best = float(np.max(region[peak_indices]))
    chosen = int(peak_indices[0])
    for idx in peak_indices:
        if region[idx] >= 0.8 * best:
            chosen = int(idx)
            break
    lag = float(min_lag + chosen)
    # Parabolic interpolation around the peak for sub-sample lag accuracy.
    y0, y1, y2 = float(norm[int(lag) - 1]), float(norm[int(lag)]), float(norm[int(lag) + 1])
    denominator = y0 - 2.0 * y1 + y2
    if abs(denominator) > 1e-9:
        lag += 0.5 * (y0 - y2) / denominator
    return SR / max(lag, 1.0)


def track_pitch(audio: np.ndarray) -> dict[str, np.ndarray]:
    """Per-frame f0 (Hz, 0 when unvoiced), confidence, RMS and voiced flag."""
    frame = int(FRAME_SECONDS * SR)
    hop = int(HOP_SECONDS * SR)
    if len(audio) < frame:
        empty = np.zeros(0, dtype=np.float32)
        return {"f0": empty, "confidence": empty, "rms": empty, "voiced": empty.astype(bool), "hop": hop, "frame": frame}

    count = (len(audio) - frame) // hop + 1
    f0 = np.zeros(count, dtype=np.float32)
    confidence = np.zeros(count, dtype=np.float32)
    rms = np.zeros(count, dtype=np.float32)

    # Coarse gate first: detect_segments finds the sung phrases, so breath
    # noise and room tone between phrases never reach the pitch tracker.
    segments = detect_segments(audio)
    in_phrase = np.zeros(len(audio), dtype=bool)
    for start, end in segments:
        in_phrase[start:end] = True

    for idx in range(count):
        start = idx * hop
        chunk = audio[start:start + frame]
        rms[idx] = float(np.sqrt(np.mean(chunk * chunk) + 1e-12))
        if not in_phrase[start + frame // 2]:
            continue
        hz, conf = estimate_f0(chunk)
        if hz > 0:
            hz = refine_f0(audio, start + frame // 2, hz)
        f0[idx] = hz
        confidence[idx] = conf

    f0 = median_filter(f0, MEDIAN_FRAMES).astype(np.float32)
    confidence = median_filter(confidence, MEDIAN_FRAMES).astype(np.float32)
    voiced = (confidence >= MIN_CONFIDENCE) & (f0 >= MIN_HZ) & (f0 <= MAX_HZ)
    f0 = np.where(voiced, f0, 0.0).astype(np.float32)
    return {
        "f0": f0,
        "confidence": confidence,
        "rms": rms,
        "voiced": voiced,
        "hop": hop,
        "frame": frame,
    }


def segment_notes(track: dict[str, Any]) -> list[dict[str, Any]]:
    """Cut the frame-level pitch track into raw notes (frame indices + midi)."""
    f0 = track["f0"]
    voiced = track["voiced"]
    hop = int(track["hop"])
    gap_frames = max(1, int(round(GAP_SECONDS / HOP_SECONDS)))

    notes: list[dict[str, Any]] = []
    current: list[tuple[int, float]] = []   # (frame index, fractional midi)
    pending: list[tuple[int, float]] = []   # frames that disagree with `current`
    unvoiced_run = 0

    def close_current() -> None:
        nonlocal current, pending
        if len(current) >= MIN_NOTE_FRAMES:
            midis = np.array([m for _, m in current], dtype=np.float64)
            notes.append({
                "startFrame": current[0][0],
                "endFrame": current[-1][0] + 1,
                "midi": float(np.median(midis)),
            })
        current = []
        pending = []

    for idx in range(len(f0)):
        if not voiced[idx]:
            unvoiced_run += 1
            if unvoiced_run >= gap_frames and current:
                close_current()
            continue
        unvoiced_run = 0
        midi = freq_to_midi(float(f0[idx]))
        if not current:
            current.append((idx, midi))
            continue
        reference = float(np.median([m for _, m in current]))
        if abs(midi - reference) > JUMP_SEMITONES:
            pending.append((idx, midi))
            if len(pending) >= JUMP_HOLD_FRAMES:
                # The move held: everything before the pending run is one note,
                # the pending run seeds the next.
                new_note = list(pending)
                pending = []
                close_current()
                current = new_note
        else:
            # A wobble that came back — it belonged to this note all along.
            current.extend(pending)
            pending = []
            current.append((idx, midi))
    if current:
        current.extend(pending)
        close_current()

    for note in notes:
        note["startSeconds"] = note["startFrame"] * hop / SR
        note["endSeconds"] = note["endFrame"] * hop / SR
    return notes


# --------------------------------------------------------------------- quantise


def grid_step_for(snap: str) -> Optional[float]:
    """Beats per grid step; None means "do not quantise"."""
    if snap in (None, "none", "off"):
        return None
    if snap not in SNAP_BEATS:
        raise ValueError(f"Unknown snap {snap!r}; use one of {', '.join(SNAP_BEATS)} or none.")
    return SNAP_BEATS[snap]


def merge_short_notes(notes: list[dict[str, Any]], grid: float) -> list[dict[str, Any]]:
    """Fold notes shorter than a grid step into a same-pitch neighbour.

    Works on unquantised beat positions. A short note only merges when the
    neighbour is the same (rounded) pitch and touches it within one grid step,
    so a genuine quick passing tone on a different pitch survives.
    """
    changed = True
    while changed and len(notes) > 1:
        changed = False
        for idx, note in enumerate(notes):
            if note["endBeat"] - note["startBeat"] >= grid:
                continue
            pitch = int(round(note["midi"]))
            prev_note = notes[idx - 1] if idx > 0 else None
            next_note = notes[idx + 1] if idx + 1 < len(notes) else None
            if prev_note is not None and int(round(prev_note["midi"])) == pitch and note["startBeat"] - prev_note["endBeat"] <= grid:
                prev_note["endBeat"] = max(prev_note["endBeat"], note["endBeat"])
                prev_note["rmsFrames"] = prev_note["rmsFrames"] + note["rmsFrames"]
                del notes[idx]
                changed = True
                break
            if next_note is not None and int(round(next_note["midi"])) == pitch and next_note["startBeat"] - note["endBeat"] <= grid:
                next_note["startBeat"] = min(next_note["startBeat"], note["startBeat"])
                next_note["rmsFrames"] = note["rmsFrames"] + next_note["rmsFrames"]
                del notes[idx]
                changed = True
                break
    return notes


def quantise_notes(notes: list[dict[str, Any]], grid: Optional[float]) -> list[dict[str, Any]]:
    """Snap onsets and durations to the grid, then resolve any resulting overlaps."""
    if grid is None:
        for note in notes:
            note["onset"] = round(note["startBeat"], 3)
            note["duration"] = round(max(0.05, note["endBeat"] - note["startBeat"]), 3)
        return notes

    notes = merge_short_notes(notes, grid)
    for note in notes:
        onset = round(note["startBeat"] / grid) * grid
        length = round((note["endBeat"] - note["startBeat"]) / grid) * grid
        note["onset"] = onset
        note["duration"] = max(grid / 2.0, length)

    notes.sort(key=lambda n: (n["onset"], -n["duration"]))
    resolved: list[dict[str, Any]] = []
    for note in notes:
        if resolved:
            prev_note = resolved[-1]
            if prev_note["onset"] == note["onset"]:
                if int(round(prev_note["midi"])) == int(round(note["midi"])):
                    prev_note["duration"] = max(prev_note["duration"], note["duration"])
                    prev_note["rmsFrames"] = prev_note["rmsFrames"] + note["rmsFrames"]
                # A hummed line is monophonic: two pitches on one grid slot means
                # one of them was a glitch, and the longer one already sorted first.
                continue
            if prev_note["onset"] + prev_note["duration"] > note["onset"]:
                prev_note["duration"] = max(grid / 2.0, note["onset"] - prev_note["onset"])
        resolved.append(note)
    return resolved


# ---------------------------------------------------------------------- analyse


def hum_to_melody(
    audio: np.ndarray,
    bpm: float,
    start_bar: int = 0,
    track_id: str = "lead",
    snap: str = "1/8",
    key: Optional[str] = None,
    key_snap: bool = True,
    color: str = DEFAULT_COLOR,
) -> dict[str, Any]:
    """Analyse a mono 44.1 kHz take and return the JSON-shaped result dict."""
    if bpm <= 0:
        raise ValueError("bpm must be positive")
    grid = grid_step_for(snap)
    warnings: list[str] = []
    key_info = parse_key(key) if key else None
    if key and key_info is None:
        warnings.append(f"Could not read key {key!r}; notes were left chromatic.")
    use_key = key_snap and key_info is not None

    audio = np.asarray(audio, dtype=np.float32)
    track = track_pitch(audio)
    raw_notes = segment_notes(track)
    voiced_frames = int(np.count_nonzero(track["voiced"]))
    voiced_seconds = voiced_frames * HOP_SECONDS
    mean_confidence = float(np.mean(track["confidence"][track["voiced"]])) if voiced_frames else 0.0

    detected: dict[str, Any] = {
        "segments": 0,
        "voicedSeconds": round(voiced_seconds, 3),
        "medianMidi": None,
        "keyUsed": key_info["name"] if use_key else None,
        "octaveShift": 0,
        "confidence": round(mean_confidence, 3),
    }
    if not raw_notes:
        warnings.append(NO_VOICE_WARNING)
        return {"ok": True, "notes": [], "detected": detected, "warnings": warnings}

    detected["segments"] = len(raw_notes)
    if mean_confidence < 0.5:
        warnings.append("Pitch tracking was uncertain on this take; check the notes before committing.")

    # Octave sanity on the raw pitches, before any key snapping.
    median_midi = float(np.median([n["midi"] for n in raw_notes]))
    detected["medianMidi"] = round(median_midi, 2)
    shift = 0
    while median_midi + shift < OCTAVE_LOW:
        shift += 12
    while median_midi + shift > OCTAVE_HIGH:
        shift -= 12
    detected["octaveShift"] = shift
    if shift:
        direction = "up" if shift > 0 else "down"
        warnings.append(f"Melody was shifted {direction} {abs(shift) // 12} octave(s) to sit in the lead range (MIDI {OCTAVE_LOW}–{OCTAVE_HIGH}).")

    # Velocity is relative to the loudest voiced frame of the take, so a quiet
    # room or a loud singer both land in the same 0.45..1.0 span.
    rms = track["rms"]
    peak_rms = float(np.max(rms[track["voiced"]])) if voiced_frames else 1.0
    beats_per_second = bpm / 60.0
    for note in raw_notes:
        note["midi"] += shift
        note["startBeat"] = note["startSeconds"] * beats_per_second
        note["endBeat"] = note["endSeconds"] * beats_per_second
        note["rmsFrames"] = list(rms[note["startFrame"]:note["endFrame"]])

    placed = quantise_notes(raw_notes, grid)

    base_beat = int(start_bar) * 4
    out_notes: list[dict[str, Any]] = []
    for index, note in enumerate(placed, start=1):
        pitch = nearest_scale_midi(note["midi"], key_info["scale"]) if use_key else float(round(note["midi"]))
        frames = np.array(note["rmsFrames"], dtype=np.float64)
        note_rms = float(np.sqrt(np.mean(frames * frames))) if len(frames) else 0.0
        ratio = min(1.0, max(0.0, note_rms / peak_rms if peak_rms > 0 else 0.0))
        velocity = VELOCITY_FLOOR + (VELOCITY_CEIL - VELOCITY_FLOOR) * ratio
        out_notes.append({
            "id": f"hum-{index}",
            "beat": round(base_beat + note["onset"], 3),
            "duration": round(note["duration"], 3),
            "note": int(pitch),
            "velocity": round(velocity, 2),
            "color": color,
            "trackId": track_id,
        })

    return {"ok": True, "notes": out_notes, "detected": detected, "warnings": warnings}


def wav_sample_rate(path: Path) -> int:
    with wave.open(str(path), "rb") as handle:
        return handle.getframerate()


def analyse_file(path: Path, **kwargs: Any) -> dict[str, Any]:
    """Read a WAV (any rate / channel count), resample to 44.1k, analyse."""
    original_rate = wav_sample_rate(path)
    audio, _ = read_wav(path)
    result = hum_to_melody(audio, **kwargs)
    if original_rate != SR:
        result["warnings"].append(f"Take was {original_rate} Hz; resampled to {SR} Hz for analysis.")
    result["input"] = {
        "file": str(path),
        "seconds": round(len(audio) / SR, 3),
        "sampleRate": original_rate,
    }
    return result


# ---------------------------------------------------------------------- output


def render_markdown(result: dict[str, Any], bpm: float, start_bar: int, snap: str) -> str:
    detected = result["detected"]
    info = result.get("input", {})
    lines = ["# Hum to melody", ""]
    if info:
        lines.append(f"- Take: `{Path(info['file']).name}` ({info['seconds']} s, {info['sampleRate']} Hz)")
    lines.append(f"- Tempo {bpm:g} BPM, grid {snap}, start bar {start_bar}, {len(result['notes'])} notes")
    median = detected.get("medianMidi")
    median_text = f"{median} ({midi_name(int(round(median)))})" if median is not None else "n/a"
    lines.append(
        f"- Detected: {detected['segments']} sung segments, {detected['voicedSeconds']} s voiced, "
        f"median MIDI {median_text}, key {detected['keyUsed'] or 'none'}, "
        f"octave shift {detected['octaveShift']:+d}, confidence {detected['confidence']}"
    )
    lines.append("")
    if result["notes"]:
        lines.extend(["| # | Bar | Beat | Dur | MIDI | Note | Vel |", "|---|-----|------|-----|------|------|-----|"])
        for note in result["notes"]:
            bar = int(note["beat"] // 4)
            in_bar = note["beat"] - bar * 4 + 1
            lines.append(
                f"| {note['id'].split('-')[-1]} | {bar} | {in_bar:g} | {note['duration']:g} | "
                f"{note['note']} | {midi_name(note['note'])} | {note['velocity']:.2f} |"
            )
        lines.append("")
    if result["warnings"]:
        lines.extend(["## Warnings", ""])
        lines.extend(f"- {warning}" for warning in result["warnings"])
        lines.append("")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Turn a hummed take into piano-roll notes.")
    parser.add_argument("--input", required=True, help="Mono or stereo WAV recorded after a count-in.")
    parser.add_argument("--bpm", type=float, required=True)
    parser.add_argument("--start-bar", type=int, default=0, help="Bar (0-based) the take starts on.")
    parser.add_argument("--track-id", default="lead")
    parser.add_argument("--snap", default="1/8", help="1/4, 1/8, 1/16, 1/32 or none.")
    parser.add_argument("--key", default=None, help='e.g. "E minor", "F# major", "Gb major", "Em".')
    parser.add_argument("--no-key-snap", action="store_true")
    parser.add_argument("--color", default=DEFAULT_COLOR)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args(argv)

    path = Path(args.input).expanduser()
    try:
        if not path.exists():
            raise FileNotFoundError(f"No such file: {path}")
        result = analyse_file(
            path,
            bpm=args.bpm,
            start_bar=args.start_bar,
            track_id=args.track_id,
            snap=args.snap,
            key=args.key,
            key_snap=not args.no_key_snap,
            color=args.color,
        )
    except Exception as exc:  # the app parses the last line, so failures must be JSON too
        failure = {"ok": False, "error": str(exc)}
        if args.format == "markdown":
            print(f"# Hum to melody\n\nFailed: {exc}")
        print(json.dumps(failure, separators=(",", ":")))
        return 1

    if args.format == "markdown":
        print(render_markdown(result, args.bpm, args.start_bar, args.snap))
    else:
        print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
