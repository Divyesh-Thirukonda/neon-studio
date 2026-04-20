#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
import wave
from pathlib import Path

import numpy as np


SR = 44_100
TAIL_SECONDS = 4.0
SCALE_MAP = {
    "e_minor": {0, 2, 4, 6, 7, 9, 11},
    "g_major": {0, 2, 4, 6, 7, 9, 11},
    "a_minor": {0, 2, 4, 5, 7, 9, 11},
    "c_major": {0, 2, 4, 5, 7, 9, 11},
    "chromatic": set(range(12)),
}


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        sample_rate = wav.getframerate()
        sample_width = wav.getsampwidth()
        frames = wav.getnframes()
        raw = wav.readframes(frames)
    if sample_width == 2:
        audio = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif sample_width == 4:
        audio = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported WAV sample width: {sample_width}")
    audio = audio.reshape(-1, channels)
    mono = audio.mean(axis=1)
    if sample_rate != SR and len(mono) > 1:
        old_x = np.linspace(0.0, 1.0, len(mono), endpoint=False)
        new_len = max(1, int(round(len(mono) * SR / sample_rate)))
        new_x = np.linspace(0.0, 1.0, new_len, endpoint=False)
        mono = np.interp(new_x, old_x, mono).astype(np.float32)
        sample_rate = SR
    return mono.astype(np.float32), sample_rate


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


def midi_to_freq(midi: float) -> float:
    return 440.0 * (2.0 ** ((midi - 69.0) / 12.0))


def freq_to_midi(freq: float) -> float:
    return 69.0 + 12.0 * math.log2(max(freq, 1e-6) / 440.0)


def nearest_scale_midi(midi: float, scale: set[int]) -> float:
    rounded = int(round(midi))
    best = rounded
    best_distance = 999.0
    for candidate in range(rounded - 12, rounded + 13):
        if candidate % 12 not in scale:
            continue
        distance = abs(candidate - midi)
        if distance < best_distance:
            best = candidate
            best_distance = distance
    return float(best)


def one_pole_lowpass(x: np.ndarray, cutoff_hz: float) -> np.ndarray:
    rc = 1.0 / (2.0 * math.pi * cutoff_hz)
    dt = 1.0 / SR
    alpha = dt / (rc + dt)
    y = np.empty_like(x, dtype=np.float32)
    prev = 0.0
    for idx, sample in enumerate(x):
        prev += alpha * (float(sample) - prev)
        y[idx] = prev
    return y


def highpass(x: np.ndarray, cutoff_hz: float = 95.0) -> np.ndarray:
    low = one_pole_lowpass(x, cutoff_hz)
    return (x - low).astype(np.float32)


def moving_rms(x: np.ndarray, window: int) -> np.ndarray:
    if len(x) == 0:
        return x
    kernel = np.ones(max(1, window), dtype=np.float32) / max(1, window)
    return np.sqrt(np.convolve(x * x, kernel, mode="same") + 1e-9).astype(np.float32)


def compressor(x: np.ndarray, threshold: float = 0.10, ratio: float = 3.2) -> np.ndarray:
    env = moving_rms(x, int(0.018 * SR))
    over = np.maximum(env / threshold, 1.0)
    gain = over ** (-(1.0 - 1.0 / ratio))
    return (x * gain).astype(np.float32)


def estimate_f0(frame: np.ndarray) -> tuple[float, float]:
    frame = frame.astype(np.float32)
    frame = frame - float(np.mean(frame))
    energy = float(np.sqrt(np.mean(frame * frame)))
    if energy < 0.006:
        return 0.0, 0.0
    n = len(frame)
    windowed = frame * np.hanning(n).astype(np.float32)
    spec = np.fft.rfft(windowed, n * 2)
    corr = np.fft.irfft(spec * np.conj(spec))[:n]
    if corr[0] <= 1e-9:
        return 0.0, 0.0
    min_lag = int(SR / 720.0)
    max_lag = min(int(SR / 75.0), n - 2)
    region = corr[min_lag:max_lag]
    if len(region) == 0:
        return 0.0, 0.0
    peak_offset = int(np.argmax(region))
    lag = min_lag + peak_offset
    confidence = float(corr[lag] / corr[0])
    if confidence < 0.26:
        return 0.0, confidence
    return SR / lag, confidence


def centered_resample(frame: np.ndarray, ratio: float) -> np.ndarray:
    if abs(ratio - 1.0) < 0.002:
        return frame
    n = len(frame)
    center = (n - 1) / 2.0
    positions = (np.arange(n, dtype=np.float32) - center) * ratio + center
    return np.interp(positions, np.arange(n, dtype=np.float32), frame, left=0.0, right=0.0).astype(np.float32)


def pitch_correct(x: np.ndarray, scale_name: str, retune: float = 0.88) -> tuple[np.ndarray, dict[str, float]]:
    scale = SCALE_MAP.get(scale_name, SCALE_MAP["e_minor"])
    frame_size = 2048
    hop = 512
    out = np.zeros(len(x) + frame_size, dtype=np.float32)
    weight = np.zeros(len(x) + frame_size, dtype=np.float32)
    window = np.hanning(frame_size).astype(np.float32)
    detected: list[float] = []
    shifts: list[float] = []

    for start in range(0, max(1, len(x) - frame_size), hop):
        frame = x[start:start + frame_size]
        if len(frame) < frame_size:
            frame = np.pad(frame, (0, frame_size - len(frame)))
        f0, confidence = estimate_f0(frame)
        shifted = frame
        if f0 > 0 and confidence > 0.26:
            midi = freq_to_midi(f0)
            target_midi = nearest_scale_midi(midi, scale)
            corrected_midi = midi + (target_midi - midi) * retune
            target_freq = midi_to_freq(corrected_midi)
            ratio = np.clip(target_freq / f0, 0.88, 1.14)
            shifted = centered_resample(frame, ratio)
            detected.append(midi)
            shifts.append(float(corrected_midi - midi))
        blended = (0.22 * frame + 0.78 * shifted) * window
        out[start:start + frame_size] += blended
        weight[start:start + frame_size] += window

    out = out[:len(x)]
    weight = weight[:len(x)]
    tuned = np.divide(out, np.maximum(weight, 1e-5)).astype(np.float32)
    return tuned, {
        "voicedFrames": float(len(detected)),
        "averageMidi": float(np.mean(detected)) if detected else 0.0,
        "averageCorrectionSemitones": float(np.mean(np.abs(shifts))) if shifts else 0.0,
    }


def detect_segments(x: np.ndarray) -> list[tuple[int, int]]:
    frame = int(0.025 * SR)
    hop = int(0.010 * SR)
    if len(x) < frame:
        return [(0, len(x))]
    rms = []
    starts = []
    for start in range(0, len(x) - frame, hop):
        chunk = x[start:start + frame]
        rms.append(float(np.sqrt(np.mean(chunk * chunk) + 1e-9)))
        starts.append(start)
    rms_arr = np.array(rms, dtype=np.float32)
    threshold = max(0.012, float(np.percentile(rms_arr, 65)) * 0.55, float(np.max(rms_arr)) * 0.07)
    active = rms_arr > threshold
    segments: list[tuple[int, int]] = []
    start_idx: int | None = None
    for idx, is_active in enumerate(active):
        if is_active and start_idx is None:
            start_idx = starts[idx]
        if not is_active and start_idx is not None:
            end = starts[idx] + frame
            if end - start_idx > int(0.18 * SR):
                segments.append((max(0, start_idx - int(0.06 * SR)), min(len(x), end + int(0.08 * SR))))
            start_idx = None
    if start_idx is not None:
        segments.append((max(0, start_idx - int(0.06 * SR)), len(x)))

    merged: list[tuple[int, int]] = []
    for start, end in segments:
        if not merged or start - merged[-1][1] > int(0.28 * SR):
            merged.append((start, end))
        else:
            prev_start, _ = merged[-1]
            merged[-1] = (prev_start, end)
    return merged or [(0, len(x))]


def add_delay(stereo: np.ndarray, delay_seconds: float, feedback: float, wet: float, repeats: int = 4) -> None:
    delay = int(delay_seconds * SR)
    dry = stereo.copy()
    for rep in range(1, repeats + 1):
        offset = delay * rep
        if offset >= len(stereo):
            break
        gain = wet * (feedback ** (rep - 1))
        stereo[offset:, 0] += dry[:-offset, 1] * gain
        stereo[offset:, 1] += dry[:-offset, 0] * gain


def vocal_chain(mono: np.ndarray, scale_name: str) -> tuple[np.ndarray, dict[str, float]]:
    mono = mono.astype(np.float32)
    mono = mono - float(np.mean(mono))
    mono = highpass(mono, 90.0)
    tuned, analysis = pitch_correct(mono, scale_name)
    tuned = compressor(tuned)
    breath_band = highpass(tuned, 5600.0)
    tuned = tuned + breath_band * 0.10
    tuned = np.tanh(tuned * 1.35).astype(np.float32) / math.tanh(1.35)
    peak = float(np.max(np.abs(tuned))) or 1.0
    tuned = tuned * min(1.0, 0.72 / peak)

    stereo = np.zeros((len(tuned), 2), dtype=np.float32)
    stereo[:, 0] = tuned
    stereo[:, 1] = tuned
    double_delay_l = int(0.011 * SR)
    double_delay_r = int(0.019 * SR)
    if double_delay_l < len(tuned):
        stereo[double_delay_l:, 0] += tuned[:-double_delay_l] * 0.13
    if double_delay_r < len(tuned):
        stereo[double_delay_r:, 1] += tuned[:-double_delay_r] * 0.13
    add_delay(stereo, 0.185, feedback=0.34, wet=0.15, repeats=3)
    add_delay(stereo, 0.375, feedback=0.26, wet=0.09, repeats=4)
    return stereo, analysis


def place_segments(raw: np.ndarray, segments: list[tuple[int, int]], bpm: float, start_bar: int, total_bars: int, scale_name: str) -> tuple[np.ndarray, dict[str, object]]:
    beat_seconds = 60.0 / bpm
    total_seconds = total_bars * 4.0 * beat_seconds + TAIL_SECONDS
    out = np.zeros((int(total_seconds * SR), 2), dtype=np.float32)
    current_beat = max(0.0, (start_bar - 1) * 4.0)
    placements = []
    all_analysis = []
    previous_end = segments[0][0]

    for idx, (start, end) in enumerate(segments):
        raw_gap_seconds = max(0.0, (start - previous_end) / SR)
        if idx > 0:
            current_beat += min(max(raw_gap_seconds / beat_seconds, 0.45), 1.50)
        current_beat = round(current_beat * 2.0) / 2.0
        processed, analysis = vocal_chain(raw[start:end], scale_name)
        fade = min(int(0.018 * SR), len(processed) // 3)
        if fade > 0:
            ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
            processed[:fade] *= ramp[:, None]
            processed[-fade:] *= ramp[::-1, None]
        start_sample = int(current_beat * beat_seconds * SR)
        end_sample = min(start_sample + len(processed), len(out))
        if end_sample > start_sample:
            out[start_sample:end_sample] += processed[:end_sample - start_sample]
        duration_beats = len(processed) / SR / beat_seconds
        placements.append({
            "segment": idx + 1,
            "bar": int(current_beat // 4) + 1,
            "beat": round((current_beat % 4) + 1, 2),
            "durationBeats": round(duration_beats, 2),
        })
        all_analysis.append(analysis)
        current_beat += duration_beats
        previous_end = end

    peak = float(np.max(np.abs(out))) or 1.0
    if peak > 0:
        out *= min(1.0, 0.86 / peak)
    return out, {
        "segments": len(segments),
        "placements": placements,
        "voicedFrames": int(sum(item["voicedFrames"] for item in all_analysis)),
        "averageCorrectionSemitones": round(float(np.mean([item["averageCorrectionSemitones"] for item in all_analysis])) if all_analysis else 0.0, 3),
    }


def safe_name(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", Path(name).stem).strip("_").lower()
    return cleaned[:42] or "vocal"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--bpm", type=float, required=True)
    parser.add_argument("--start-bar", type=int, default=17)
    parser.add_argument("--total-bars", type=int, default=72)
    parser.add_argument("--key", default="e_minor")
    args = parser.parse_args()

    raw, _ = read_wav(Path(args.input))
    segments = detect_segments(raw)
    processed, analysis = place_segments(raw, segments, args.bpm, args.start_bar, args.total_bars, args.key)
    output_path = Path(args.output)
    write_wav(output_path, processed)
    print(json.dumps({
        "ok": True,
        "file": output_path.name,
        "name": safe_name(args.name),
        "durationSeconds": round(len(processed) / SR, 2),
        **analysis,
    }))


if __name__ == "__main__":
    main()
