#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
import wave
from pathlib import Path
from typing import Any

import numpy as np

try:
    import production_rubric
except ImportError:  # pragma: no cover - the checker still works standalone
    production_rubric = None  # type: ignore[assignment]


EPSILON = 1e-12


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def dbfs(value: float) -> float:
    return 20.0 * math.log10(max(float(value), EPSILON))


def safe_project_id(value: str) -> str:
    base = Path(value).name.replace(".neon.json", "")
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", base).strip("-_")
    return cleaned or "project"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def project_path_for(root: Path, project_id: str | None, project_path: str | None) -> Path:
    if project_path:
        return Path(project_path).expanduser().resolve()
    if not project_id:
        raise SystemExit("Provide --project or --project-id.")
    project_id = safe_project_id(project_id)
    candidates = [
        root / "data" / "projects" / f"{project_id}.neon.json",
        root / "factory" / "projects" / f"{project_id}.neon.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise SystemExit(f"No project found for {project_id}.")


def equal_power_pan(pan: float) -> tuple[float, float]:
    pan = clamp(float(pan), -1.0, 1.0)
    angle = (pan + 1.0) * math.pi / 4.0
    return math.cos(angle), math.sin(angle)


def read_wav_stereo(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_rate = wav_file.getframerate()
        width = wav_file.getsampwidth()
        frames = wav_file.getnframes()
        raw = wav_file.readframes(frames)
    if frames == 0:
        return np.zeros((0, 2), dtype=np.float32), sample_rate
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
    return np.nan_to_num(audio.astype(np.float32)), sample_rate


def asset_file_for(track: dict[str, Any], assets: list[dict[str, Any]]) -> str | None:
    file_value = track.get("file")
    if isinstance(file_value, str) and file_value:
        return file_value
    track_id = track.get("id")
    for asset in assets:
        if asset.get("trackId") == track_id and isinstance(asset.get("file"), str):
            return str(asset["file"])
    return None


def audio_path_for(root: Path, file_value: str | None) -> Path | None:
    if not file_value:
        return None
    if file_value.startswith("file://"):
        return Path(file_value[7:]).expanduser()
    if file_value.startswith("/") and not file_value.startswith("/api/audio/"):
        return Path(file_value).expanduser()
    name = Path(file_value).name
    candidates = []
    if file_value.startswith("/api/audio/"):
        candidates.append(root / "exports" / name)
    cleaned = file_value[1:] if file_value.startswith("/") else file_value
    candidates.append(root / cleaned)
    candidates.append(root / "exports" / name)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0] if candidates else None


def expects_audio_file(track: dict[str, Any]) -> bool:
    instrument = str(track.get("instrument") or "").lower()
    track_id = str(track.get("id") or "").lower()
    if "automation lane" in instrument or track_id in {"filter-auto", "automation", "automation-lane"}:
        return False
    if float(track.get("gain", 0.8) or 0.0) <= 0.0 and not track.get("file"):
        return False
    return True


def build_mix(
    root: Path,
    project: dict[str, Any],
) -> tuple[np.ndarray, int, list[dict[str, Any]], list[dict[str, Any]]]:
    snapshot = project.get("snapshot", {})
    tracks = snapshot.get("tracks", [])
    controls = snapshot.get("controls", {})
    assets = project.get("assets", [])
    if not isinstance(tracks, list):
        tracks = []
    if not isinstance(controls, dict):
        controls = {}
    if not isinstance(assets, list):
        assets = []

    solo_active = any(bool(control.get("solo")) for control in controls.values() if isinstance(control, dict))
    loaded: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    sample_rate = 44_100
    max_len = 0

    for track in tracks:
        if not isinstance(track, dict):
            continue
        track_id = str(track.get("id", ""))
        control = controls.get(track_id, {})
        if not isinstance(control, dict):
            control = {}
        if control.get("mute") is True:
            continue
        if solo_active and control.get("solo") is not True:
            continue

        file_value = asset_file_for(track, assets)
        audio_path = audio_path_for(root, file_value)
        if not audio_path or not audio_path.exists():
            if not expects_audio_file(track):
                continue
            missing.append({
                "id": track_id,
                "name": track.get("name") or track_id,
                "file": file_value,
            })
            continue

        try:
            audio, sr = read_wav_stereo(audio_path)
        except Exception as exc:
            missing.append({
                "id": track_id,
                "name": track.get("name") or track_id,
                "file": str(audio_path),
                "error": str(exc),
            })
            continue

        sample_rate = sr
        max_len = max(max_len, len(audio))
        loaded.append({
            "track": track,
            "control": control,
            "path": str(audio_path),
            "audio": audio,
            "sampleRate": sr,
        })

    if not loaded:
        return np.zeros((0, 2), dtype=np.float32), sample_rate, [], missing

    mix = np.zeros((max_len, 2), dtype=np.float32)
    track_reports: list[dict[str, Any]] = []
    for item in loaded:
        track = item["track"]
        control = item["control"]
        audio = item["audio"]
        gain = float(control.get("gain", track.get("gain", 0.8)))
        pan = float(control.get("pan", track.get("pan", 0.0)))
        left, right = equal_power_pan(pan)
        layer = np.zeros_like(mix)
        layer[: len(audio), 0] = audio[:, 0] * gain * left
        layer[: len(audio), 1] = audio[:, 1] * gain * right
        mix += layer
        peak = float(np.max(np.abs(layer))) if len(layer) else 0.0
        rms = float(np.sqrt(np.mean(np.square(layer)))) if len(layer) else 0.0
        track_reports.append({
            "id": track.get("id"),
            "name": track.get("name") or track.get("id"),
            "file": Path(str(item["path"])).name,
            "peakDb": round(dbfs(peak), 2),
            "rmsDb": round(dbfs(rms), 2),
            "gain": round(gain, 3),
            "pan": round(pan, 3),
        })

    return np.nan_to_num(mix), sample_rate, track_reports, missing


def first_last_above(mono: np.ndarray, threshold: float) -> tuple[int | None, int | None]:
    if mono.size == 0:
        return None, None
    active = np.flatnonzero(np.abs(mono) > threshold)
    if active.size == 0:
        return None, None
    return int(active[0]), int(active[-1])


def spectral_profile(mono: np.ndarray, sample_rate: int) -> dict[str, float]:
    if mono.size < 2048:
        return {
            "subRatio": 0.0,
            "bassRatio": 0.0,
            "lowMidRatio": 0.0,
            "midRatio": 0.0,
            "highRatio": 0.0,
            "airRatio": 0.0,
        }

    stride = max(1, mono.size // (sample_rate * 90))
    sample = mono[::stride]
    max_samples = min(sample.size, sample_rate * 90)
    sample = sample[:max_samples].astype(np.float64)
    sample = sample - float(np.mean(sample))
    window = np.hanning(sample.size)
    spectrum = np.abs(np.fft.rfft(sample * window)) ** 2
    freqs = np.fft.rfftfreq(sample.size, d=1.0 / sample_rate)
    total = float(np.sum(spectrum)) or EPSILON

    def ratio(lower: float, upper: float) -> float:
        mask = (freqs >= lower) & (freqs < upper)
        return float(np.sum(spectrum[mask]) / total)

    return {
        "subRatio": round(ratio(20, 60), 4),
        "bassRatio": round(ratio(60, 180), 4),
        "lowMidRatio": round(ratio(180, 500), 4),
        "midRatio": round(ratio(500, 4000), 4),
        "highRatio": round(ratio(4000, 11000), 4),
        "airRatio": round(ratio(11000, min(sample_rate / 2, 20000)), 4),
    }


def audio_metrics(audio: np.ndarray, sample_rate: int) -> dict[str, Any]:
    if audio.size == 0:
        return {
            "seconds": 0.0,
            "peakDb": -120.0,
            "rmsDb": -120.0,
            "crestDb": 0.0,
            "clipPercent": 0.0,
            "stereoCorrelation": 0.0,
            "stereoWidth": 0.0,
            "monoLossDb": 0.0,
            "headSilenceSeconds": 0.0,
            "tailSilenceSeconds": 0.0,
            **spectral_profile(np.array([], dtype=np.float32), sample_rate),
        }
    peak = float(np.max(np.abs(audio)))
    rms = float(np.sqrt(np.mean(np.square(audio))))
    peak_db = dbfs(peak)
    rms_db = dbfs(rms)
    mono = np.mean(audio, axis=1)
    left = audio[:, 0]
    right = audio[:, 1]
    if float(np.std(left)) > EPSILON and float(np.std(right)) > EPSILON:
        correlation = float(np.corrcoef(left, right)[0, 1])
    else:
        correlation = 0.0
    mid = (left + right) * 0.5
    side = (left - right) * 0.5
    mid_rms = float(np.sqrt(np.mean(np.square(mid)))) or EPSILON
    side_rms = float(np.sqrt(np.mean(np.square(side))))
    stereo_rms = float(np.sqrt(np.mean(np.square(audio)))) or EPSILON
    mono_rms = float(np.sqrt(np.mean(np.square(mono)))) or EPSILON
    first, last = first_last_above(mono, 0.003)
    seconds = len(audio) / sample_rate
    head_silence = (first or 0) / sample_rate if first is not None else seconds
    tail_silence = (len(audio) - 1 - (last or 0)) / sample_rate if last is not None else seconds

    return {
        "seconds": round(seconds, 2),
        "peakDb": round(peak_db, 2),
        "rmsDb": round(rms_db, 2),
        "crestDb": round(peak_db - rms_db, 2),
        "clipPercent": round(float(np.mean(np.abs(audio) >= 0.985) * 100.0), 4),
        "stereoCorrelation": round(correlation, 3),
        "stereoWidth": round(side_rms / mid_rms, 3),
        "monoLossDb": round(dbfs(mono_rms) - dbfs(stereo_rms), 2),
        "headSilenceSeconds": round(head_silence, 2),
        "tailSilenceSeconds": round(tail_silence, 2),
        **spectral_profile(mono, sample_rate),
    }


def project_checks(project: dict[str, Any], missing: list[dict[str, Any]], track_reports: list[dict[str, Any]]) -> dict[str, Any]:
    snapshot = project.get("snapshot", {})
    tracks = snapshot.get("tracks", [])
    recipe = snapshot.get("recipe", [])
    controls = snapshot.get("controls", {})
    if not isinstance(tracks, list):
        tracks = []
    if not isinstance(recipe, list):
        recipe = []
    if not isinstance(controls, dict):
        controls = {}
    sections = []
    for item in recipe:
        if isinstance(item, dict):
            section = item.get("section")
            if isinstance(section, str) and section and section not in sections:
                sections.append(section)
    max_clip_end = 0.0
    active_effects = 0
    for track in tracks:
        if not isinstance(track, dict):
            continue
        for clip in track.get("clips", []) or []:
            if isinstance(clip, dict):
                max_clip_end = max(max_clip_end, float(clip.get("startBar", 0) or 0) + float(clip.get("bars", 0) or 0))
        for effect in track.get("effects", []) or []:
            if isinstance(effect, dict) and effect.get("active") is True:
                active_effects += 1
    muted = [
        track_id
        for track_id, control in controls.items()
        if isinstance(control, dict) and control.get("mute") is True
    ]
    solo = [
        track_id
        for track_id, control in controls.items()
        if isinstance(control, dict) and control.get("solo") is True
    ]
    return {
        "bpm": snapshot.get("bpm"),
        "trackCount": len(tracks),
        "audibleTrackCount": len(track_reports),
        "missingAudioCount": len(missing),
        "missingAudio": missing[:8],
        "recipeCount": len(recipe),
        "sections": sections,
        "sectionCount": len(sections),
        "maxClipEndBar": round(max_clip_end, 2),
        "activeEffects": active_effects,
        "mutedTracks": muted,
        "soloTracks": solo,
        "loopEnabled": bool(snapshot.get("loopEnabled")),
        "loopStartBar": snapshot.get("loopStartBar"),
        "loopEndBar": snapshot.get("loopEndBar"),
    }


def add_issue(issues: list[dict[str, str]], severity: str, area: str, detail: str) -> None:
    """Record a finding, tagged with the production requirements that would have
    prevented it.

    The tag is what lets the loop close: `fill_in_blanks.py --feedback-json`
    reads these ids and re-raises exactly those requirements as measured gaps,
    so the next pass fixes the specific thing that went wrong instead of
    re-guessing from scratch."""
    issue: dict[str, Any] = {"severity": severity, "area": area, "detail": detail}
    if production_rubric is not None:
        ids = [r.id for r in production_rubric.requirements_for_area(area)]
        if ids:
            issue["requirementIds"] = ids
    issues.append(issue)


def evaluate(metrics: dict[str, Any], checks: dict[str, Any], track_reports: list[dict[str, Any]]) -> dict[str, Any]:
    score = 78
    issues: list[dict[str, str]] = []
    strengths: list[str] = []
    next_actions: list[str] = []

    if checks["audibleTrackCount"] == 0:
        return {
            "score": 10,
            "label": "Cannot judge",
            "answer": "Cannot judge the sound yet",
            "summary": "No playable audio stems or mix were found for this project.",
            "strengths": [],
            "issues": [{"severity": "high", "area": "Audio", "detail": "No playable audio files were available."}],
            "nextActions": ["Render the project stems or full mix, then run the check again."],
        }

    peak_db = float(metrics["peakDb"])
    rms_db = float(metrics["rmsDb"])
    crest = float(metrics["crestDb"])
    clip_percent = float(metrics["clipPercent"])
    bass_ratio = float(metrics["bassRatio"])
    sub_ratio = float(metrics["subRatio"])
    low_mid_ratio = float(metrics["lowMidRatio"])
    high_ratio = float(metrics["highRatio"]) + float(metrics["airRatio"])
    correlation = float(metrics["stereoCorrelation"])
    mono_loss = float(metrics["monoLossDb"])
    width = float(metrics["stereoWidth"])

    if -9.0 <= rms_db <= -13.5 and 7.0 <= crest <= 13.0:
        strengths.append("The overall loudness and punch are in a usable production range.")
        score += 4
    if checks["audibleTrackCount"] >= 6:
        strengths.append("The session has enough audible layers to read as an arranged production.")
        score += 3
    if checks["recipeCount"] >= 5 and checks["sectionCount"] >= 4:
        strengths.append("The project recipe maps a real section flow instead of a loose loop.")
        score += 3
    if 0.08 <= width <= 0.75 and correlation > 0.15:
        strengths.append("Stereo width looks controlled enough to survive mono playback.")
        score += 2

    if clip_percent > 0.5:
        score -= 22
        add_issue(issues, "high", "Clipping", f"{clip_percent:.2f}% of samples are near full scale.")
        next_actions.append("Pull the master or loudest buses down before adding any more layers.")
    elif clip_percent > 0.05:
        score -= 12
        add_issue(issues, "medium", "Clipping", f"{clip_percent:.2f}% of samples are near full scale.")
        next_actions.append("Lower the hottest tracks or soften the clipper so transient edges stop flattening.")
    if peak_db > -0.2:
        score -= 7
        add_issue(issues, "medium", "Headroom", f"Peak is {peak_db:.2f} dBFS, leaving almost no headroom.")
    elif peak_db < -12:
        score -= 8
        add_issue(issues, "medium", "Level", f"Peak is only {peak_db:.2f} dBFS.")
        next_actions.append("Raise the mix bus or render level after balancing the tracks.")

    if rms_db > -7.5:
        score -= 12
        add_issue(issues, "high", "Density", f"RMS is {rms_db:.2f} dBFS, which is likely over-compressed.")
        next_actions.append("Create more contrast between kick, bass, lead, and ambience instead of pushing all layers forward.")
    elif rms_db < -24:
        score -= 10
        add_issue(issues, "medium", "Level", f"RMS is {rms_db:.2f} dBFS, so the track will feel quiet.")

    if crest < 5:
        score -= 16
        add_issue(issues, "high", "Punch", f"Crest factor is {crest:.2f} dB, so transients are too flat.")
        next_actions.append("Back off bus compression or clipping and restore kick/snare transient contrast.")
    elif crest < 7:
        score -= 8
        add_issue(issues, "medium", "Punch", f"Crest factor is {crest:.2f} dB.")
    elif crest > 20 and rms_db < -18:
        score -= 5
        add_issue(issues, "low", "Consistency", "The mix has large peaks but low average energy.")

    if sub_ratio > 0.32 or bass_ratio > 0.48:
        score -= 10
        add_issue(issues, "high", "Low end", "The low-frequency balance is probably crowding the mix.")
        next_actions.append("High-pass non-bass layers and decide whether kick or bass owns each low-end moment.")
    elif bass_ratio < 0.05 and sub_ratio < 0.03:
        score -= 6
        add_issue(issues, "medium", "Low end", "The mix may not have enough bass weight.")
    if low_mid_ratio > 0.34:
        score -= 5
        add_issue(issues, "medium", "Low mids", "Low mids are heavy enough to risk mud.")
        next_actions.append("Dip 200-500 Hz on pads, reverbs, or stacked melodic layers.")
    if high_ratio > 0.46:
        score -= 7
        add_issue(issues, "medium", "Top end", "High-frequency energy is aggressive.")
        next_actions.append("Tame hats, noise, and bright reverbs before making the lead louder.")
    elif high_ratio < 0.07:
        score -= 6
        add_issue(issues, "medium", "Top end", "The mix may need more air or presence.")

    if correlation < -0.1:
        score -= 12
        add_issue(issues, "high", "Stereo", f"Stereo correlation is {correlation:.2f}.")
        next_actions.append("Narrow or phase-check wide layers, especially reverbs, pads, and doubles.")
    elif mono_loss < -4:
        score -= 8
        add_issue(issues, "medium", "Mono", f"Mono collapse loses {abs(mono_loss):.2f} dB.")
        next_actions.append("Check the hook, bass, and drums in mono and reduce phase-heavy widening.")

    if checks["missingAudioCount"] > 0:
        score -= min(12, checks["missingAudioCount"] * 3)
        add_issue(issues, "medium", "Missing audio", f"{checks['missingAudioCount']} project track(s) point to missing audio.")
        next_actions.append("Fix or remove missing audio references so the app and rendered mix agree.")
    if checks["trackCount"] < 4:
        score -= 8
        add_issue(issues, "medium", "Arrangement", "The project has too few tracks to judge as a finished production.")
    if checks["recipeCount"] == 0:
        score -= 5
        add_issue(issues, "low", "Recipe", "No production recipe is attached to the project.")
    if float(metrics["seconds"]) < 30:
        score -= 5
        add_issue(issues, "low", "Length", "The available audio is shorter than a full-song review target.")

    if not next_actions:
        loudest = sorted(track_reports, key=lambda item: item["rmsDb"], reverse=True)[:3]
        if loudest:
            names = ", ".join(str(item["name"]) for item in loudest)
            next_actions.append(f"Do a focused listen on the loudest lanes: {names}.")
        next_actions.append("Run one human listen pass for hook memorability, transition impact, and emotional payoff.")

    score = int(round(clamp(score, 0, 100)))
    if score >= 82:
        label = "Yes"
        answer = "Yes, this is in a good place"
    elif score >= 68:
        label = "Close"
        answer = "Close, but it still needs polish"
    else:
        label = "Not yet"
        answer = "Not yet"

    if issues:
        top = issues[0]
        summary = f"{answer}. Main concern: {top['area'].lower()} - {top['detail']}"
    else:
        summary = f"{answer}. The technical readout did not find a major blocking issue."

    return {
        "score": score,
        "label": label,
        "answer": answer,
        "summary": summary,
        "strengths": strengths[:4],
        "issues": issues[:8],
        "nextActions": next_actions[:5],
    }


def build_report(root: Path, project_path: Path) -> dict[str, Any]:
    project = read_json(project_path)
    mix, sample_rate, track_reports, missing = build_mix(root, project)
    metrics = audio_metrics(mix, sample_rate)
    checks = project_checks(project, missing, track_reports)
    verdict = evaluate(metrics, checks, track_reports)
    return {
        "ok": True,
        "project": {
            "id": project.get("id") or safe_project_id(project_path.name),
            "name": project.get("name") or safe_project_id(project_path.name),
            "path": str(project_path),
        },
        "verdict": {
            "score": verdict["score"],
            "label": verdict["label"],
            "answer": verdict["answer"],
            "summary": verdict["summary"],
        },
        "metrics": metrics,
        "projectChecks": checks,
        "trackReports": sorted(track_reports, key=lambda item: item["rmsDb"], reverse=True),
        "strengths": verdict["strengths"],
        "issues": verdict["issues"],
        "nextActions": verdict["nextActions"],
    }


def render_markdown(report: dict[str, Any]) -> str:
    project = report["project"]
    verdict = report["verdict"]
    metrics = report["metrics"]
    checks = report["projectChecks"]
    lines = [
        f"# Does This Sound Good: {project['name']}",
        "",
        f"**Verdict:** {verdict['answer']} ({verdict['score']}/100)",
        "",
        verdict["summary"],
        "",
        "## Readout",
        "",
        f"- Audio: {metrics['seconds']}s, peak {metrics['peakDb']} dBFS, RMS {metrics['rmsDb']} dBFS, crest {metrics['crestDb']} dB",
        f"- Stereo: correlation {metrics['stereoCorrelation']}, width {metrics['stereoWidth']}, mono loss {metrics['monoLossDb']} dB",
        f"- Project: {checks['audibleTrackCount']}/{checks['trackCount']} audible tracks, {checks['recipeCount']} recipe items, {checks['sectionCount']} sections",
        "",
    ]
    if report["strengths"]:
        lines.extend(["## What Works", ""])
        lines.extend(f"- {item}" for item in report["strengths"])
        lines.append("")
    if report["issues"]:
        lines.extend(["## Issues", ""])
        for issue in report["issues"]:
            lines.append(f"- [{issue['severity']}] {issue['area']}: {issue['detail']}")
        lines.append("")
    lines.extend(["## Next Actions", ""])
    lines.extend(f"- {item}" for item in report["nextActions"])
    lines.append("")
    loudest = report["trackReports"][:5]
    if loudest:
        lines.extend(["## Loudest Lanes", ""])
        for track in loudest:
            lines.append(f"- {track['name']}: RMS {track['rmsDb']} dB, peak {track['peakDb']} dB, gain {track['gain']}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate whether a Neon Studio project sounds good.")
    parser.add_argument("--root", default=".", help="Workspace or app support root.")
    parser.add_argument("--project-id", help="Project id, e.g. neon-solitude.")
    parser.add_argument("--project", help="Path to a .neon.json file.")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    project_path = project_path_for(root, args.project_id, args.project)
    report = build_report(root, project_path)
    if args.format == "markdown":
        print(render_markdown(report))
    else:
        print(json.dumps(report, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
