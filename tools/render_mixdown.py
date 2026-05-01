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
    file_value = track.get("file")
    file_name = None
    if isinstance(file_value, str):
        file_name = Path(file_value).name
    if not file_name:
        track_id = track.get("id")
        for asset in assets:
            if asset.get("trackId") == track_id and isinstance(asset.get("file"), str):
                file_name = Path(str(asset["file"])).name
                break
    if not file_name:
        return None
    return root / "exports" / file_name


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
    loaded: list[tuple[dict[str, object], dict[str, object], np.ndarray]] = []
    sample_rate = 44_100
    max_len = 0

    for track in tracks:
        if not isinstance(track, dict):
            continue
        track_id = str(track.get("id", ""))
        control = controls.get(track_id, {}) if isinstance(controls, dict) else {}
        if control.get("mute") is True:
            continue
        if solo_active and control.get("solo") is not True:
            continue
        audio_path = resolve_audio_path(root, track, assets if isinstance(assets, list) else [])
        if not audio_path or not audio_path.exists():
            continue
        audio, sr = read_wav_stereo(audio_path)
        sample_rate = sr
        loaded.append((track, control if isinstance(control, dict) else {}, audio))
        max_len = max(max_len, len(audio))

    if not loaded:
        raise SystemExit("No playable audio tracks found")

    mix = np.zeros((max_len, 2), dtype=np.float32)
    for track, control, audio in loaded:
        gain = float(control.get("gain", track.get("gain", 0.8)))
        pan = float(control.get("pan", track.get("pan", 0.0)))
        left, right = equal_power_pan(pan)
        layer = np.zeros_like(mix)
        layer[: len(audio), 0] = audio[:, 0] * gain * left
        layer[: len(audio), 1] = audio[:, 1] * gain * right
        mix += layer

    mix = soft_clip(mix, drive=1.08) * 0.94
    output_path = Path(args.output)
    write_wav(output_path, mix, sample_rate)
    print(json.dumps({
        "ok": True,
        "file": output_path.name,
        "tracksMixed": len(loaded),
        "sampleRate": sample_rate,
        "seconds": round(max_len / sample_rate, 2),
        "sizeKb": round(os.path.getsize(output_path) / 1024, 1) if output_path.exists() else 0,
    }))


if __name__ == "__main__":
    main()
