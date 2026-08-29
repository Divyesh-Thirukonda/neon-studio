#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import re
import wave
from pathlib import Path

import numpy as np


def equal_power_pan(pan: float) -> tuple[float, float]:
    pan = float(np.clip(pan, -1.0, 1.0))
    angle = (pan + 1.0) * math.pi / 4.0
    return math.cos(angle), math.sin(angle)


def read_wav_stereo(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_rate = wav_file.getframerate()
        width = wav_file.getsampwidth()
        frames = wav_file.getnframes()
        raw = wav_file.readframes(frames)
    if width == 2:
        audio = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 4:
        audio = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported WAV sample width: {width}")
    audio = audio.reshape(-1, channels)
    if channels == 1:
        audio = np.repeat(audio, 2, axis=1)
    elif channels > 2:
        audio = audio[:, :2]
    return audio.astype(np.float32), sample_rate


def write_wav(path: Path, audio: np.ndarray, sample_rate: int) -> None:
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
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm16.tobytes())


def soft_clip(audio: np.ndarray, drive: float = 1.08) -> np.ndarray:
    return np.tanh(audio * drive) / np.tanh(drive)


def resolve_audio_path(root: Path, track: dict[str, object], assets: list[dict[str, object]]) -> Path | None:
    """Resolve a track's audio the same way the app does.

    The app accepts absolute paths, ``file://`` URLs, legacy ``/api/audio/...``
    paths and paths relative to the workspace root. Looking only in
    ``exports/`` meant a sound the user imported from anywhere else played in
    the app but went silently missing from the exported mix.
    """
    candidates: list[str] = []
    file_value = track.get("file")
    if isinstance(file_value, str) and file_value:
        candidates.append(file_value)
    track_id = track.get("id")
    for asset in assets:
        if asset.get("trackId") == track_id and isinstance(asset.get("file"), str):
            candidates.append(str(asset["file"]))

    for value in candidates:
        if value.startswith("file://"):
            path = Path(value[len("file://"):])
        elif value.startswith("/api/audio/"):
            path = root / "exports" / Path(value).name
        elif value.startswith("/"):
            path = Path(value)
        else:
            path = root / value
        if path.exists():
            return path
        # Fall back to the exports folder, which is where renderers write.
        fallback = root / "exports" / Path(value).name
        if fallback.exists():
            return fallback
    return None


# --- Note and step preview synthesis -----------------------------------------
#
# Mirrors NeonStudioKit's NotePreviewRenderer so that a mixdown contains
# everything the app plays. Without this, notes drawn in the piano roll and
# patterns switched on in the step sequencer were audible in the app but
# silently absent from every exported file.

SHAPE_SINE, SHAPE_TRIANGLE, SHAPE_SAW, SHAPE_SUPERSAW, SHAPE_NOISE = range(5)

PREVIEW_MAX_SECONDS = 300.0


def preview_voice(track: dict[str, object]) -> dict[str, float | int]:
    text = " ".join(
        str(track.get(key) or "") for key in ("name", "kind", "instrument")
    ).lower()

    def voice(shape, attack, decay, sustain, release, level):
        return {
            "shape": shape, "attack": attack, "decay": decay,
            "sustain": sustain, "release": release, "level": level,
        }

    if any(word in text for word in ("hat", "cymbal", "ride", "shaker")):
        return voice(SHAPE_NOISE, 0.001, 0.045, 0.0, 0.02, 0.22)
    if "clap" in text or "snare" in text:
        return voice(SHAPE_NOISE, 0.001, 0.16, 0.0, 0.05, 0.34)
    if "kick" in text or "drum" in text or "sub" in text:
        return voice(SHAPE_SINE, 0.001, 0.22, 0.0, 0.05, 0.5)
    if "bass" in text:
        return voice(SHAPE_SINE, 0.004, 0.14, 0.55, 0.08, 0.42)
    if "pluck" in text or "bell" in text or "key" in text:
        return voice(SHAPE_TRIANGLE, 0.002, 0.24, 0.12, 0.14, 0.32)
    if "chord" in text or "pad" in text or "string" in text:
        return voice(SHAPE_SUPERSAW, 0.05, 0.3, 0.7, 0.35, 0.2)
    return voice(SHAPE_SAW, 0.006, 0.18, 0.55, 0.16, 0.26)


def supports_step_sequencing(track: dict[str, object]) -> bool:
    kind = str(track.get("kind") or "").lower()
    if kind == "automation":
        return False
    if kind == "audio" and track.get("file"):
        return False
    return True


def percussion_pitch(track: dict[str, object]) -> int:
    text = " ".join(str(track.get(key) or "") for key in ("name", "instrument")).lower()
    if "hat" in text or "ride" in text or "cymbal" in text:
        return 90
    if "clap" in text or "snare" in text:
        return 72
    if "kick" in text:
        return 36
    if "sub" in text or "bass" in text:
        return 40
    return 60


def midi_to_frequency(note: int) -> float:
    return 440.0 * (2.0 ** ((float(note) - 69.0) / 12.0))


def preview_events(track: dict[str, object], snapshot: dict[str, object]) -> list[tuple[float, float, float, float]]:
    """(start_seconds, duration_seconds, frequency, velocity) for one track."""
    bpm = float(snapshot.get("bpm") or 120) or 120.0
    seconds_per_bar = (60.0 / bpm) * 4.0
    seconds_per_beat = seconds_per_bar / 4.0
    track_id = str(track.get("id", ""))
    events: list[tuple[float, float, float, float]] = []

    for note in snapshot.get("notes") or []:
        if not isinstance(note, dict) or str(note.get("trackId", "")) != track_id:
            continue
        events.append((
            max(0.0, float(note.get("beat", 0))) * seconds_per_beat,
            max(0.03, float(note.get("duration", 0.25)) * seconds_per_beat),
            midi_to_frequency(int(note.get("note", 60))),
            min(1.0, max(0.05, float(note.get("velocity", 0.8)))),
        ))

    steps = [int(s) % 16 for s in (track.get("steps") or []) if isinstance(s, (int, float))]
    if steps and supports_step_sequencing(track):
        clips = [c for c in (track.get("clips") or []) if isinstance(c, dict)]
        starts = [float(c.get("startBar") or 0) for c in clips]
        ends = [float(c.get("startBar") or 0) + float(c.get("bars") or 1) for c in clips]
        first_bar = min(starts) if starts else 0.0
        last_bar = max(ends) if ends else first_bar + 1.0
        frequency = midi_to_frequency(percussion_pitch(track))
        bar = first_bar
        while bar < last_bar and (bar - first_bar) * seconds_per_bar < PREVIEW_MAX_SECONDS:
            for step in steps:
                events.append((
                    (bar + step / 16.0) * seconds_per_bar,
                    seconds_per_bar / 16.0,
                    frequency,
                    1.0 if step % 4 == 0 else 0.72,
                ))
            bar += 1.0

    events.sort(key=lambda event: event[0])
    return events


def render_preview_track(
    track: dict[str, object],
    snapshot: dict[str, object],
    sample_rate: int,
) -> np.ndarray | None:
    """Render one track's notes and steps to stereo float audio, or None."""
    events = preview_events(track, snapshot)
    if not events:
        return None

    voice = preview_voice(track)
    tail = float(voice["release"]) + float(voice["decay"]) + 0.25
    end = min(PREVIEW_MAX_SECONDS, max(start + duration for start, duration, _, _ in events) + tail)
    total = int(end * sample_rate)
    if total <= 0:
        return None

    mono = np.zeros(total, dtype=np.float32)
    # Seeded so a project always renders the same way, run to run.
    rng = np.random.default_rng(0x2545F491)
    shape = int(voice["shape"])

    for start, duration, frequency, velocity in events:
        start_frame = int(start * sample_rate)
        if start_frame >= total:
            continue
        sustain_frames = int(duration * sample_rate)
        release_frames = max(1, int(float(voice["release"]) * sample_rate))
        length = min(sustain_frames + release_frames, total - start_frame)
        if length <= 0:
            continue

        attack_frames = max(1, int(float(voice["attack"]) * sample_rate))
        decay_frames = max(1, int(float(voice["decay"]) * sample_rate))
        sustain_level = float(voice["sustain"])

        offsets = np.arange(length, dtype=np.float32)
        envelope = np.empty(length, dtype=np.float32)
        attack_end = min(attack_frames, length)
        envelope[:attack_end] = offsets[:attack_end] / attack_frames
        decay_end = min(attack_frames + decay_frames, length)
        if decay_end > attack_end:
            t = (offsets[attack_end:decay_end] - attack_frames) / decay_frames
            envelope[attack_end:decay_end] = 1.0 - t * (1.0 - sustain_level)
        sustain_end = min(max(sustain_frames, decay_end), length)
        if sustain_end > decay_end:
            envelope[decay_end:sustain_end] = sustain_level
        if length > sustain_end:
            t = (offsets[sustain_end:] - sustain_frames) / release_frames
            envelope[sustain_end:] = np.maximum(0.0, sustain_level * (1.0 - t))

        phase = (np.arange(length, dtype=np.float64) * (frequency / sample_rate)) % 1.0
        if shape == SHAPE_SINE:
            wave_data = np.sin(2 * np.pi * phase)
        elif shape == SHAPE_TRIANGLE:
            wave_data = 2 * np.abs(2 * (phase - np.floor(phase + 0.5))) - 1
        elif shape == SHAPE_SAW:
            wave_data = 2 * (phase - np.floor(phase + 0.5))
        elif shape == SHAPE_SUPERSAW:
            a = 2 * (phase - np.floor(phase + 0.5))
            b = 2 * ((phase * 1.006) - np.floor(phase * 1.006 + 0.5))
            c = 2 * ((phase * 0.994) - np.floor(phase * 0.994 + 0.5))
            wave_data = (a + b + c) / 3
        else:
            wave_data = rng.uniform(-1.0, 1.0, length)

        amplitude = float(voice["level"]) * velocity
        mono[start_frame:start_frame + length] += (wave_data * envelope * amplitude).astype(np.float32)

    peak = float(np.max(np.abs(mono))) if mono.size else 0.0
    if peak > 0.95:
        mono *= 0.95 / peak
    return np.repeat(mono.reshape(-1, 1), 2, axis=1)


def stem_timeline_offset(
    track: dict[str, object],
    duration_seconds: float,
    snapshot: dict[str, object],
) -> float:
    """Seconds of silence before a stem starts, matching the app's transport.

    Rendered stems are full-length even when their first clip is drawn at bar 8,
    so offsetting those by the clip position would push them a minute late. A
    file materially shorter than the song is a one-shot and does belong where
    its clip sits.
    """
    clips = [c for c in (track.get("clips") or []) if isinstance(c, dict)]
    starts = [float(c.get("startBar") or 0) for c in clips]
    if not starts:
        return 0.0
    first_bar = min(starts)
    if first_bar <= 0:
        return 0.0
    bpm = float(snapshot.get("bpm") or 120) or 120.0
    seconds_per_bar = (60.0 / bpm) * 4.0
    content_end_bar = max(
        [float(c.get("startBar") or 0) + float(c.get("bars") or 0)
         for t in (snapshot.get("tracks") or []) if isinstance(t, dict)
         for c in (t.get("clips") or []) if isinstance(c, dict)] or [1.0]
    )
    song_seconds = max(content_end_bar, 1.0) * seconds_per_bar
    if duration_seconds >= song_seconds * 0.8:
        return 0.0
    return first_bar * seconds_per_bar


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, help="Workspace or support root containing exports/")
    parser.add_argument("--project", required=True, help="Path to the .neon.json project file")
    parser.add_argument("--output", required=True, help="Where to write the rendered mixdown WAV")
    args = parser.parse_args()

    root = Path(args.root)
    project_path = Path(args.project)
    project = json.loads(project_path.read_text(encoding="utf-8"))
    snapshot = project.get("snapshot", {})
    tracks = snapshot.get("tracks", [])
    controls = snapshot.get("controls", {})
    assets = project.get("assets", [])

    solo_active = any(bool(control.get("solo")) for control in controls.values()) if isinstance(controls, dict) else False
    loaded: list[tuple[dict[str, object], dict[str, object], np.ndarray, int]] = []
    sample_rate = 44_100
    max_len = 0
    synthesised = 0

    # Resolve the sample rate from the first real audio file, so synthesised
    # tracks are generated to match rather than being resampled.
    for track in tracks:
        if not isinstance(track, dict):
            continue
        probe = resolve_audio_path(root, track, assets if isinstance(assets, list) else [])
        if probe and probe.exists():
            with wave.open(str(probe), "rb") as probe_file:
                sample_rate = probe_file.getframerate()
            break

    for track in tracks:
        if not isinstance(track, dict):
            continue
        track_id = str(track.get("id", ""))
        control = controls.get(track_id, {}) if isinstance(controls, dict) else {}
        if not isinstance(control, dict):
            control = {}
        if control.get("mute") is True:
            continue
        if solo_active and control.get("solo") is not True:
            continue

        audio_path = resolve_audio_path(root, track, assets if isinstance(assets, list) else [])
        if audio_path and audio_path.exists():
            audio, sr = read_wav_stereo(audio_path)
            sample_rate = sr
            offset = int(stem_timeline_offset(track, len(audio) / sr, snapshot) * sr)
        else:
            preview = render_preview_track(track, snapshot, sample_rate)
            if preview is None:
                continue
            audio = preview
            offset = 0
            synthesised += 1

        loaded.append((track, control, audio, offset))
        max_len = max(max_len, offset + len(audio))

    if not loaded:
        raise SystemExit(
            "Nothing to mix: no track has an audio file, any notes, or any steps switched on."
        )

    mix = np.zeros((max_len, 2), dtype=np.float32)
    for track, control, audio, offset in loaded:
        gain = float(control.get("gain", track.get("gain", 0.8)))
        pan = float(control.get("pan", track.get("pan", 0.0)))
        left, right = equal_power_pan(pan)
        end = offset + len(audio)
        mix[offset:end, 0] += audio[:, 0] * gain * left
        mix[offset:end, 1] += audio[:, 1] * gain * right

    mix = soft_clip(mix, drive=1.08) * 0.94
    output_path = Path(args.output)
    write_wav(output_path, mix, sample_rate)
    print(json.dumps({
        "ok": True,
        "file": output_path.name,
        "tracksMixed": len(loaded),
        "tracksSynthesised": synthesised,
        "sampleRate": sample_rate,
        "seconds": round(max_len / sample_rate, 2),
        "sizeKb": round(os.path.getsize(output_path) / 1024, 1) if output_path.exists() else 0,
    }))


if __name__ == "__main__":
    main()
