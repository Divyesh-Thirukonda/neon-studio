#!/usr/bin/env python3
"""An MCP server that exposes the Songlab pipeline to coding agents.

Neon Studio's whole flow — paste a description, get a buildable project, render
it, check it, act on what the check said — is a sequence of local tools. That is
exactly the shape MCP was designed for, so a user in Cursor, Claude Code, or any
other MCP client can drive the same pipeline the Mac app drives, in the editor
they already have open.

Run it directly for a smoke test:

    /usr/bin/python3 tools/mcp_server.py --self-test

Wire it into a client by pointing at this file (see `docs/mcp.md`). It speaks
newline-delimited JSON-RPC 2.0 over stdin/stdout and depends on nothing outside
the standard library, so it starts with whatever Python the machine already has.

Design notes:

* Every tool is a thin wrapper over the same functions the CLI and the app call.
  There is no second implementation of anything here, so behaviour cannot drift
  between the editor, the terminal and the app.
* Tools return human-readable text, because the caller is a language model
  deciding what to do next, not a program parsing a struct. Where a machine-
  readable payload matters, it is included as JSON inside that text.
* Long operations (materialise, render) run to completion. Rendering a full song
  takes tens of seconds; the descriptions say so, so an agent can warn the user
  rather than appearing to hang.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "songlab"
SERVER_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _python() -> str:
    """The interpreter to run helper scripts with.

    Prefers the one running this server, so a client that launched us with a
    specific Python does not silently get a different one for the subprocesses.
    """
    return sys.executable or "/usr/bin/python3"


def _run(args: list[str], timeout: int = 900) -> tuple[int, str, str]:
    proc = subprocess.run(
        [_python(), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _safe_id(value: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in "-_" else "-" for c in str(value).lower())
    return cleaned.strip("-_")[:72] or "song-project"


def _project_paths(project_id: str) -> dict[str, Path]:
    pid = _safe_id(project_id)
    return {
        "session": ROOT / "songlab" / "projects" / pid,
        "spec": ROOT / "songlab" / "projects" / pid / "transcript_spec.json",
        "fill": ROOT / "songlab" / "projects" / pid / "fill_in_blanks.md",
        "project": ROOT / "data" / "projects" / f"{pid}.neon.json",
        "renderer": ROOT / f"render_{pid.replace('-', '_')}.py",
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _describe_arrangement(spec: dict[str, Any]) -> str:
    sections = [s for s in spec.get("sections", []) if isinstance(s, dict) and s.get("bars")]
    if not sections:
        return "no arrangement yet"
    parts = " -> ".join(f"{s.get('type')}({s.get('bars')})" for s in sections)
    total = sum(int(s.get("bars") or 0) for s in sections)
    tempo = float(spec.get("tempoHint") or 120) or 120
    minutes = total * (60.0 / tempo * 4.0) / 60.0
    return f"{parts}\n{total} bars, about {minutes:.1f} minutes at {int(tempo)} BPM"


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def tool_build_song(args: dict[str, Any]) -> str:
    """The main entry point: a description in, a buildable project out."""
    project_id = _safe_id(args.get("project_id") or "new-song")
    transcript = args.get("transcript") or ""
    brief = args.get("brief") or "song built from a description"
    if not str(transcript).strip():
        return "Nothing to build from. Pass `transcript` — a description of the song, a tutorial, a walkthrough, or a step-by-step. A couple of sentences is enough; a full transcript is better."

    scratch = ROOT / "songlab" / "projects" / project_id
    scratch.mkdir(parents=True, exist_ok=True)
    transcript_path = scratch / "transcript.txt"
    transcript_path.write_text(str(transcript), encoding="utf-8")

    code, out, err = _run([
        str(TOOLS / "songlab.py"), "init",
        "--project-id", project_id,
        "--prompt", str(brief),
        "--transcript-file", str(transcript_path),
        "--force-materialize",
    ])
    if code != 0:
        return f"Build failed (exit {code}).\n\n{(err or out).strip()[-1500:]}"

    paths = _project_paths(project_id)
    lines = [f"Built `{project_id}`."]
    if paths["spec"].exists():
        spec = _read_json(paths["spec"])
        lines.append(f"\nArrangement:\n{_describe_arrangement(spec)}")
        fill = spec.get("fillInBlanks") or {}
        gaps = fill.get("gaps") or []
        if gaps:
            lines.append(f"\n{len(gaps)} production step(s) the description did not mention were inferred and added to the recipe as `Missing Steps`:")
            for gap in gaps[:8]:
                lines.append(f"  - {gap.get('label')}: {gap.get('step', '')[:150]}")
            if len(gaps) > 8:
                lines.append(f"  ... and {len(gaps) - 8} more")
    lines.append(f"\nFiles:\n  project:  {paths['project']}\n  spec:     {paths['spec']}\n  renderer: {paths['renderer']}")
    lines.append("\nNext: `songlab_render` to produce audio, then `songlab_sound_check`.")
    return "\n".join(lines)


def tool_render(args: dict[str, Any]) -> str:
    project_id = _safe_id(args.get("project_id") or "")
    paths = _project_paths(project_id)
    if not paths["renderer"].exists():
        return f"No renderer for `{project_id}` at {paths['renderer']}. Run `songlab_build_song` first."
    code, out, err = _run([str(paths["renderer"])], timeout=1800)
    if code != 0:
        return f"Render failed (exit {code}).\n\n{(err or out).strip()[-1500:]}"
    stems = [line.strip() for line in out.splitlines() if ".wav" in line]
    return f"Rendered `{project_id}`.\n\n" + "\n".join(stems[-20:])


def tool_sound_check(args: dict[str, Any]) -> str:
    project_id = _safe_id(args.get("project_id") or "")
    code, out, err = _run([
        str(TOOLS / "does_this_sound_good.py"),
        "--root", str(ROOT),
        "--project-id", project_id,
        "--format", "json",
    ])
    if code != 0:
        return f"Sound check failed (exit {code}).\n\n{(err or out).strip()[-1200:]}"
    try:
        report = json.loads(out.strip().splitlines()[-1])
    except Exception:
        return out.strip()[-2000:]

    verdict = report.get("verdict") or {}
    lines = [f"{verdict.get('score')}/100 — {verdict.get('answer')}", ""]
    if report.get("strengths"):
        lines.append("Working:")
        lines += [f"  + {s}" for s in report["strengths"][:4]]
    if report.get("issues"):
        lines.append("\nProblems:")
        for issue in report["issues"][:6]:
            ids = issue.get("requirementIds") or []
            tail = f"  [fix via: {', '.join(ids[:3])}]" if ids else ""
            lines.append(f"  - {issue.get('area')}: {issue.get('detail')}{tail}")
    if report.get("nextActions"):
        lines.append("\nNext:")
        lines += [f"  * {a}" for a in report["nextActions"][:4]]
    lines.append(
        "\nEvery problem is tagged with the production requirements that would have"
        " prevented it. Call `songlab_apply_sound_check` to turn them into concrete"
        " steps in the project's recipe."
    )
    return "\n".join(lines)


def tool_apply_sound_check(args: dict[str, Any]) -> str:
    project_id = _safe_id(args.get("project_id") or "")
    paths = _project_paths(project_id)
    if not paths["spec"].exists():
        return f"No spec for `{project_id}`. Run `songlab_build_song` first."

    code, out, err = _run([
        str(TOOLS / "does_this_sound_good.py"),
        "--root", str(ROOT), "--project-id", project_id, "--format", "json",
    ])
    if code != 0:
        return f"Could not run the sound check (exit {code}).\n\n{(err or out).strip()[-1000:]}"
    report_path = ROOT / "songlab" / "projects" / project_id / "last_sound_check.json"
    report_path.write_text(out.strip().splitlines()[-1], encoding="utf-8")

    code, out, err = _run([
        str(TOOLS / "fill_in_blanks.py"),
        "--input-json", str(paths["spec"]),
        "--feedback-json", str(report_path),
        "--output-json", str(paths["spec"]),
        "--output-md", str(paths["fill"]),
        "--format", "json",
    ])
    if code != 0:
        return f"Could not fold the findings back in (exit {code}).\n\n{(err or out).strip()[-1000:]}"

    spec = _read_json(paths["spec"])
    gaps = (spec.get("fillInBlanks") or {}).get("gaps") or []
    measured = [g for g in gaps if g.get("confidence") == "measured"]
    lines = [f"Folded the sound check into `{project_id}`. {len(measured)} measured step(s) now outrank the inferred ones:"]
    for gap in measured[:8]:
        lines.append(f"  - {gap.get('label')}: {gap.get('step', '')[:150]}")
        if gap.get("evidence"):
            lines.append(f"      {gap['evidence'][:150]}")
    lines.append(f"\nFull report: {paths['fill']}")
    lines.append("Re-materialise with `songlab_build_song` (same project_id) or edit the project directly, then render and check again.")
    return "\n".join(lines)


def tool_suggest_improvements(args: dict[str, Any]) -> str:
    project_id = _safe_id(args.get("project_id") or "")
    paths = _project_paths(project_id)
    if not paths["project"].exists():
        return f"No project at {paths['project']}."
    output = ROOT / "songlab" / "projects" / project_id / "agent_output.neon.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(TOOLS / "daw_agent.py"), "--root", str(ROOT), "apply",
        "--project", str(paths["project"]), "--output", str(output), "--format", "json",
    ]
    if args.get("apply") is True:
        pass
    code, out, err = _run(cmd)
    if code != 0:
        return f"Suggestion run failed (exit {code}).\n\n{(err or out).strip()[-1200:]}"
    try:
        report = json.loads(out.strip().splitlines()[-1])
    except Exception:
        return out.strip()[-2000:]

    lines = [report.get("summary", "Done."), ""]
    for action in (report.get("actions") or [])[:6]:
        lines.append(f"  - {action.get('title')}")
        for message in (action.get("messages") or [])[:2]:
            lines.append(f"      {message}")
    if args.get("apply") is True:
        paths["project"].write_text(output.read_text(encoding="utf-8"), encoding="utf-8")
        lines.append(f"\nApplied to {paths['project']}.")
    else:
        lines.append(f"\nProposed only. The patched project is at {output}; pass apply=true to write it over the real one.")
    return "\n".join(lines)


def tool_list_projects(args: dict[str, Any]) -> str:
    directory = ROOT / "data" / "projects"
    if not directory.exists():
        return "No projects yet."
    rows = []
    for path in sorted(directory.glob("*.neon.json")):
        try:
            data = _read_json(path)
            snap = data.get("snapshot") or {}
            rows.append(f"  {data.get('id', path.stem):28} {int(snap.get('bpm') or 0):>4} BPM  {len(snap.get('tracks') or []):>2} tracks  {data.get('name', '')}")
        except Exception:
            rows.append(f"  {path.stem:28} (unreadable)")
    return "Projects:\n" + "\n".join(rows) if rows else "No projects yet."


def tool_inspect_project(args: dict[str, Any]) -> str:
    project_id = _safe_id(args.get("project_id") or "")
    paths = _project_paths(project_id)
    if not paths["project"].exists():
        return f"No project at {paths['project']}."
    data = _read_json(paths["project"])
    snap = data.get("snapshot") or {}
    lines = [
        f"{data.get('name')}  ({data.get('id')})",
        f"{int(snap.get('bpm') or 0)} BPM, key {data.get('keyCenter') or 'unset'}",
        "",
        "Tracks:",
    ]
    for track in snap.get("tracks") or []:
        clips = len(track.get("clips") or [])
        lines.append(f"  {track.get('name', ''):24} {track.get('instrument', ''):26} {clips} clip(s)  file={'yes' if track.get('file') else 'no'}")
    recipe = snap.get("recipe") or []
    if recipe:
        pending = [r for r in recipe if str(r.get("status", "")).lower() not in ("implemented", "done", "complete", "completed", "ready", "ok")]
        lines.append(f"\nRecipe: {len(recipe)} steps, {len(pending)} still to do")
        for item in pending[:10]:
            lines.append(f"  [ ] {item.get('section', '')}: {item.get('label', '')}")
    return "\n".join(lines)


def tool_production_rubric(args: dict[str, Any]) -> str:
    try:
        import production_rubric as rubric
    except Exception as exc:  # pragma: no cover
        return f"Could not load the rubric: {exc}"
    area = str(args.get("area") or "").strip()
    items = rubric.requirements_for_area(area) if area else rubric.REQUIREMENTS
    if not items:
        return f"Nothing in the rubric matches {area!r}. Areas: {', '.join(rubric.SOUND_CHECK_AREAS)}"
    lines = [f"{len(items)} production requirement(s):", ""]
    for req in items:
        lines.append(f"### {req.id} — {req.label}")
        lines.append(f"  Why:  {req.why}")
        lines.append(f"  Step: {req.step}")
        lines.append(f"  Pre-empts: {', '.join(req.areas) or 'nothing measurable'}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Human-in-the-loop tools
#
# These are the surfaces where a person, not the software, decides. Each one
# wraps a tool the Mac app also calls, so an agent in Cursor and a user at the
# app get identical behaviour.
# ---------------------------------------------------------------------------

def tool_fidelity(args: dict[str, Any]) -> str:
    project_id = _safe_id(args.get("project_id") or "")
    code, out, err = _run([
        str(TOOLS / "transcript_fidelity.py"),
        "--root", str(ROOT), "--project-id", project_id, "--format", "markdown",
    ])
    if code != 0:
        return f"Fidelity check failed (exit {code}).\n\n{(err or out).strip()[-1200:]}"
    return out.strip()[-6000:]


def tool_hum_to_melody(args: dict[str, Any]) -> str:
    wav = str(args.get("wav_path") or "").strip()
    if not wav or not Path(wav).expanduser().exists():
        return "Pass `wav_path` — a WAV of somebody humming or singing. The app records one with a count-in; any mono or stereo WAV works."
    project_id = _safe_id(args.get("project_id") or "")
    paths = _project_paths(project_id) if project_id else None
    bpm = args.get("bpm")
    key = args.get("key")
    if paths and paths["project"].exists():
        data = _read_json(paths["project"])
        bpm = bpm or (data.get("snapshot") or {}).get("bpm")
        key = key or data.get("keyCenter")
    cmd = [
        str(TOOLS / "hum_to_melody.py"),
        "--input", str(Path(wav).expanduser()),
        "--bpm", str(bpm or 120),
        "--start-bar", str(int(args.get("start_bar") or 0)),
        "--track-id", str(args.get("track_id") or "lead"),
        "--snap", str(args.get("snap") or "1/8"),
        "--format", "json",
    ]
    if key:
        cmd += ["--key", str(key)]
    code, out, err = _run(cmd)
    if code != 0:
        return f"Couldn't read the melody (exit {code}).\n\n{(err or out).strip()[-1200:]}"
    try:
        result = json.loads(out.strip().splitlines()[-1])
    except Exception:
        return out.strip()[-2000:]
    notes = result.get("notes") or []
    detected = result.get("detected") or {}
    lines = [f"Heard {len(notes)} note(s) over {detected.get('voicedSeconds', 0)}s"
             + (f", snapped to {detected.get('keyUsed')}" if detected.get("keyUsed") else "") + "."]
    for note in notes[:12]:
        lines.append(f"  beat {note.get('beat'):>5}  MIDI {note.get('note')}  {note.get('duration')} beats  vel {note.get('velocity')}")
    if len(notes) > 12:
        lines.append(f"  ... and {len(notes) - 12} more")
    for warning in result.get("warnings") or []:
        lines.append(f"  ! {warning}")

    if args.get("insert") is True and paths and paths["project"].exists() and notes:
        data = _read_json(paths["project"])
        snapshot = data.setdefault("snapshot", {})
        track_id = str(args.get("track_id") or "lead")
        span_start = min(n["beat"] for n in notes)
        span_end = max(n["beat"] + n["duration"] for n in notes)
        kept = [n for n in (snapshot.get("notes") or [])
                if n.get("trackId") != track_id or n.get("beat", 0) + n.get("duration", 0) <= span_start or n.get("beat", 0) >= span_end]
        snapshot["notes"] = kept + notes
        paths["project"].write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        lines.append(f"\nInserted onto track `{track_id}` in {paths['project'].name}, replacing any notes already in beats {span_start:g}–{span_end:g}.")
    elif args.get("insert") is True:
        lines.append("\nNot inserted: pass a `project_id` whose project exists.")
    else:
        lines.append("\nPass insert=true with a project_id to write these onto the track.")
    return "\n".join(lines)


def tool_variations(args: dict[str, Any]) -> str:
    project_id = _safe_id(args.get("project_id") or "")
    paths = _project_paths(project_id)
    if not paths["project"].exists():
        return f"No project at {paths['project']}."
    out_dir = paths["session"] / "variations"
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(TOOLS / "variations.py"), "--root", str(ROOT),
        "--project", str(paths["project"]),
        "--track-id", str(args.get("track_id") or "lead"),
        "--section", str(args.get("section") or "drop"),
        "--count", str(int(args.get("count") or 3)),
        "--seed", str(int(args.get("seed") or 7)),
        "--output-dir", str(out_dir),
        "--format", "json",
    ]
    code, out, err = _run(cmd, timeout=1200)
    if code != 0:
        return f"Couldn't make alternatives (exit {code}).\n\n{(err or out).strip()[-1200:]}"
    try:
        result = json.loads(out.strip().splitlines()[-1])
    except Exception:
        return out.strip()[-2000:]
    target = result.get("target") or {}
    lines = [f"{len(result.get('variations') or [])} alternative(s) for {target.get('trackName')} in {target.get('section')} (bars {int(target.get('startBar', 0)) + 1}–{int(target.get('startBar', 0) + target.get('bars', 0))}):", ""]
    for v in result.get("variations") or []:
        lines.append(f"  [{v.get('id')}] {v.get('label')}")
        lines.append(f"      {v.get('description')}")
        lines.append(f"      preview: {v.get('preview')}")
        lines.append(f"      project: {v.get('project')}")
    lines.append(f"\n{result.get('previewNote', '')}")
    lines.append("To adopt one, call `songlab_use_variation` with its project path, or copy only that track from it.")
    return "\n".join(lines)


def tool_use_variation(args: dict[str, Any]) -> str:
    project_id = _safe_id(args.get("project_id") or "")
    paths = _project_paths(project_id)
    variant_path = Path(str(args.get("variation_project") or "")).expanduser()
    track_id = str(args.get("track_id") or "")
    if not paths["project"].exists() or not variant_path.exists() or not track_id:
        return "Pass `project_id`, `variation_project` (a path from songlab_variations) and `track_id`."
    real = _read_json(paths["project"])
    variant = _read_json(variant_path)
    real_snap = real.setdefault("snapshot", {})
    var_snap = variant.get("snapshot") or {}
    var_track = next((t for t in var_snap.get("tracks") or [] if t.get("id") == track_id), None)
    if var_track is None:
        return f"The variation has no track `{track_id}`."
    # Only the chosen lane changes. The real stem file stays; the variant
    # cleared it so its preview would synthesise.
    for track in real_snap.get("tracks") or []:
        if track.get("id") == track_id:
            keep_file = track.get("file")
            track.update({k: v for k, v in var_track.items() if k != "file"})
            track["file"] = keep_file
    real_snap["notes"] = [n for n in (real_snap.get("notes") or []) if n.get("trackId") != track_id] + \
                         [n for n in (var_snap.get("notes") or []) if n.get("trackId") == track_id]
    real_snap["automationLanes"] = [l for l in (real_snap.get("automationLanes") or []) if l.get("trackId") != track_id] + \
                                   [l for l in (var_snap.get("automationLanes") or []) if l.get("trackId") == track_id]
    paths["project"].write_text(json.dumps(real, indent=2) + "\n", encoding="utf-8")
    return f"Applied the variation to `{track_id}` in {paths['project'].name}. Re-render to hear it in the full song."


def tool_describe_change(args: dict[str, Any]) -> str:
    project_id = _safe_id(args.get("project_id") or "")
    request = str(args.get("request") or "").strip()
    paths = _project_paths(project_id)
    if not paths["project"].exists():
        return f"No project at {paths['project']}."
    if not request:
        return "Say what should change, in your own words: 'make the drop hit harder', 'the lead is too bright', 'a bit slower'."
    output = paths["session"] / "describe_change_output.neon.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    code, out, err = _run([
        str(TOOLS / "describe_change.py"), "--root", str(ROOT),
        "--project", str(paths["project"]), "--request", request,
        "--output", str(output), "--format", "json",
    ])
    if code != 0:
        return f"Couldn't apply that (exit {code}).\n\n{(err or out).strip()[-1200:]}"
    try:
        result = json.loads(out.strip().splitlines()[-1])
    except Exception:
        return out.strip()[-2000:]
    edits = result.get("edits") or []
    lines = []
    if edits:
        lines.append(f"Done — {result.get('understood', request)}")
        for edit in edits:
            lines.append(f"  - {edit.get('title')}: {edit.get('detail')}")
        if args.get("apply", True) is not False:
            paths["project"].write_text(output.read_text(encoding="utf-8"), encoding="utf-8")
            lines.append(f"\nWritten to {paths['project'].name}.")
        else:
            lines.append(f"\nProposed only; the edited project is at {output}.")
    else:
        lines.append("I didn't understand that yet.")
    if result.get("unresolved"):
        lines.append("\nDidn't understand: " + "; ".join(result["unresolved"]))
    if result.get("suggestions"):
        lines.append("\nThings I do understand:")
        lines += [f"  - {s}" for s in result["suggestions"][:6]]
    if result.get("tactics"):
        lines.append("\nBigger ideas that might fit:")
        lines += [f"  - {t.get('title')} (score {t.get('score')})" for t in result["tactics"][:3]]
    return "\n".join(lines)


def tool_listening_questions(args: dict[str, Any]) -> str:
    project_id = _safe_id(args.get("project_id") or "")
    paths = _project_paths(project_id)
    if not paths["project"].exists():
        return f"No project at {paths['project']}."
    code, out, err = _run([
        str(TOOLS / "listening_session.py"), "--root", str(ROOT),
        "--project", str(paths["project"]), "questions", "--format", "json",
    ])
    if code != 0:
        return f"Couldn't build the questions (exit {code}).\n\n{(err or out).strip()[-1200:]}"
    try:
        result = json.loads(out.strip().splitlines()[-1])
    except Exception:
        return out.strip()[-2000:]
    lines = ["Play each section for the user and ask. Then call `songlab_listening_apply` with their answers.", ""]
    for section in result.get("sections") or []:
        start = int(section.get("startBar", 0))
        lines.append(f"## {section.get('label')} (bars {start + 1}–{start + int(section.get('bars', 0))})")
        for q in section.get("questions") or []:
            if q.get("freeText"):
                lines.append(f"  {q.get('id')}: {q.get('text')} (free text)")
            else:
                lines.append(f"  {q.get('id')}: {q.get('text')}  [{' / '.join(q.get('options') or [])}]")
        lines.append("")
    return "\n".join(lines)


def tool_listening_apply(args: dict[str, Any]) -> str:
    project_id = _safe_id(args.get("project_id") or "")
    paths = _project_paths(project_id)
    answers = args.get("answers")
    if not paths["project"].exists():
        return f"No project at {paths['project']}."
    if not isinstance(answers, list) or not answers:
        return "Pass `answers`: a list of {questionId, option} or {questionId, text} from songlab_listening_questions."
    answers_path = paths["session"] / "listening_answers.json"
    answers_path.parent.mkdir(parents=True, exist_ok=True)
    answers_path.write_text(json.dumps({"answers": answers}, indent=2), encoding="utf-8")
    cmd = [
        str(TOOLS / "listening_session.py"), "--root", str(ROOT),
        "--project", str(paths["project"]),
    ]
    if paths["spec"].exists():
        cmd += ["--spec", str(paths["spec"])]
    cmd += ["apply", "--answers", str(answers_path), "--project-id", project_id, "--format", "markdown"]
    code, out, err = _run(cmd)
    if code != 0:
        return f"Couldn't apply the answers (exit {code}).\n\n{(err or out).strip()[-1200:]}"
    return out.strip()[-4000:]


TOOLS_TABLE: dict[str, tuple[Callable[[dict[str, Any]], str], str, dict[str, Any]]] = {
    "songlab_build_song": (
        tool_build_song,
        "Turn a description of a song into a real, buildable project. Accepts anything from two "
        "sentences to a full tutorial transcript. Extracts the arrangement, track roles and "
        "production cues, infers everything the description left out, and writes a .neon.json "
        "project plus a renderer script. Takes 10-60 seconds.",
        {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Short slug, e.g. 'midnight-drive'."},
                "transcript": {"type": "string", "description": "The description, tutorial, walkthrough or step-by-step. Longer and more specific is better."},
                "brief": {"type": "string", "description": "One line on what the song should be."},
            },
            "required": ["project_id", "transcript"],
        },
    ),
    "songlab_render": (
        tool_render,
        "Render a built project to audio stems and a full mix. Takes 30-120 seconds depending on "
        "song length; tell the user it is running.",
        {
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
            "required": ["project_id"],
        },
    ),
    "songlab_sound_check": (
        tool_sound_check,
        "Judge a rendered project: a score out of 100, what works, what is wrong, and what to do "
        "next. Each problem is tagged with the production requirements that would have prevented it.",
        {
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
            "required": ["project_id"],
        },
    ),
    "songlab_apply_sound_check": (
        tool_apply_sound_check,
        "Run a sound check and fold its findings straight back into the project's plan as concrete, "
        "measured production steps. Use this instead of reading a report and guessing at fixes.",
        {
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
            "required": ["project_id"],
        },
    ),
    "songlab_suggest_improvements": (
        tool_suggest_improvements,
        "Propose production tactics for a project — extra automation, groove variation, macro effect "
        "chains, motif seeds. Proposes by default; pass apply=true to write them into the project.",
        {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "apply": {"type": "boolean", "description": "Write the changes rather than only proposing them."},
            },
            "required": ["project_id"],
        },
    ),
    "songlab_list_projects": (
        tool_list_projects,
        "List every project with its tempo and track count.",
        {"type": "object", "properties": {}},
    ),
    "songlab_inspect_project": (
        tool_inspect_project,
        "Show a project's tracks, clips, audio status and the production steps still outstanding.",
        {
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
            "required": ["project_id"],
        },
    ),
    "songlab_production_rubric": (
        tool_production_rubric,
        "The production requirements Songlab checks a song against — what each one is, why it "
        "matters, and the sound-check finding it prevents. Filter by area, or omit for all.",
        {
            "type": "object",
            "properties": {"area": {"type": "string", "description": "e.g. 'Low end', 'Stereo', 'Arrangement'."}},
        },
    ),
    "songlab_fidelity": (
        tool_fidelity,
        "Does the built song match what the description or tutorial actually said? Checks tempo, "
        "key, section order, every technique the text named (with audio evidence when stems exist), "
        "and explicit numbers. The counterpart to songlab_sound_check: that asks 'is it good', this "
        "asks 'is it what was asked for'.",
        {"type": "object", "properties": {"project_id": {"type": "string"}}, "required": ["project_id"]},
    ),
    "songlab_hum_to_melody": (
        tool_hum_to_melody,
        "Turn a recording of someone humming or singing into piano-roll notes. Pass a WAV path; "
        "optionally a project_id (to pick up its tempo and key) and insert=true to write the notes "
        "onto a track. This is how 'sing what you want it to sound like' becomes literal.",
        {
            "type": "object",
            "properties": {
                "wav_path": {"type": "string"},
                "project_id": {"type": "string"},
                "track_id": {"type": "string", "description": "Default 'lead'."},
                "start_bar": {"type": "integer", "description": "Bar the take began on (0-based). Default 0."},
                "snap": {"type": "string", "description": "Grid: 1/4, 1/8 (default) or 1/16."},
                "bpm": {"type": "number"}, "key": {"type": "string"},
                "insert": {"type": "boolean", "description": "Write the notes into the project."},
            },
            "required": ["wav_path"],
        },
    ),
    "songlab_variations": (
        tool_variations,
        "Write a few musically distinct alternatives for one track in one section and render a short "
        "preview of each, so the user can listen and choose rather than describe. Returns labels, "
        "descriptions and preview WAV paths. About 20 seconds.",
        {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "track_id": {"type": "string"},
                "section": {"type": "string", "description": "A section name like 'Drop', or a bar range '24-40'."},
                "count": {"type": "integer"}, "seed": {"type": "integer"},
            },
            "required": ["project_id", "track_id", "section"],
        },
    ),
    "songlab_use_variation": (
        tool_use_variation,
        "Adopt one alternative from songlab_variations: copies only that track's notes, steps, clips "
        "and automation into the real project, keeping the project's own audio file for the track.",
        {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "variation_project": {"type": "string", "description": "The 'project' path of the chosen variation."},
                "track_id": {"type": "string"},
            },
            "required": ["project_id", "variation_project", "track_id"],
        },
    ),
    "songlab_describe_change": (
        tool_describe_change,
        "Change the song from a plain-English request — 'make the drop hit harder', 'the lead is too "
        "bright', 'more bounce in the drums', 'a bit slower'. Applies by default; pass apply=false to "
        "see the edits without writing them. Says honestly when it does not understand and lists what it can do.",
        {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "request": {"type": "string"},
                "apply": {"type": "boolean"},
            },
            "required": ["project_id", "request"],
        },
    ),
    "songlab_listening_questions": (
        tool_listening_questions,
        "The human sound check, part one: plain questions to ask the user about each section while "
        "it plays ('Does the drop land?', 'Can you hum the main tune?'). Returns questions with their "
        "options and the bar range to play for each.",
        {"type": "object", "properties": {"project_id": {"type": "string"}}, "required": ["project_id"]},
    ),
    "songlab_listening_apply": (
        tool_listening_apply,
        "The human sound check, part two: turn the user's answers into concrete production steps in "
        "the project's plan, marked as human evidence, and log the session.",
        {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "answers": {
                    "type": "array",
                    "items": {"type": "object", "properties": {"questionId": {"type": "string"}, "option": {"type": "string"}, "text": {"type": "string"}}, "required": ["questionId"]},
                },
            },
            "required": ["project_id", "answers"],
        },
    ),
}


# ---------------------------------------------------------------------------
# JSON-RPC plumbing
# ---------------------------------------------------------------------------

def _result(request_id: Any, payload: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": payload}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}

    if method == "initialize":
        return _result(request_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })

    # Notifications carry no id and get no reply.
    if request_id is None:
        return None

    if method == "tools/list":
        return _result(request_id, {
            "tools": [
                {"name": name, "description": description, "inputSchema": schema}
                for name, (_, description, schema) in TOOLS_TABLE.items()
            ]
        })

    if method == "tools/call":
        name = params.get("name")
        entry = TOOLS_TABLE.get(name)
        if entry is None:
            return _error(request_id, -32602, f"Unknown tool: {name}")
        handler = entry[0]
        try:
            text = handler(params.get("arguments") or {})
        except subprocess.TimeoutExpired:
            text = "That took too long and was stopped. Rendering a very long song can exceed the limit; try a shorter arrangement."
        except Exception:
            text = f"The tool raised an error:\n\n{traceback.format_exc()[-1200:]}"
        return _result(request_id, {"content": [{"type": "text", "text": text}]})

    if method in ("ping",):
        return _result(request_id, {})

    return _error(request_id, -32601, f"Unknown method: {method}")


def serve(stdin: io.TextIOBase, stdout: io.TextIOBase) -> None:
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = handle(message)
        if response is None:
            continue
        stdout.write(json.dumps(response) + "\n")
        stdout.flush()


def self_test() -> int:
    """Exercise the protocol without a client, so wiring problems are obvious."""
    checks = 0

    init = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init and init["result"]["serverInfo"]["name"] == SERVER_NAME, init
    checks += 1

    assert handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    checks += 1

    listed = handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tools = listed["result"]["tools"]
    assert len(tools) == len(TOOLS_TABLE), tools
    for tool in tools:
        assert tool["name"] and tool["description"] and tool["inputSchema"]["type"] == "object"
    checks += 1

    unknown = handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "nope"}})
    assert "error" in unknown, unknown
    checks += 1

    listing = handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                      "params": {"name": "songlab_list_projects", "arguments": {}}})
    assert listing["result"]["content"][0]["type"] == "text"
    checks += 1

    rubric = handle({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                     "params": {"name": "songlab_production_rubric", "arguments": {"area": "Low end"}}})
    text = rubric["result"]["content"][0]["text"]
    assert "low_end_ownership" in text, text[:400]
    checks += 1

    # A tool that raises must come back as text, never as a crashed server.
    broken = handle({"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                     "params": {"name": "songlab_inspect_project", "arguments": {}}})
    assert broken["result"]["content"][0]["text"]
    checks += 1

    print(f"mcp_server self-test: {checks}/{checks} checks passed, {len(TOOLS_TABLE)} tools exposed")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        raise SystemExit(self_test())
    serve(sys.stdin, sys.stdout)
