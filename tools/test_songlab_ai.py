#!/usr/bin/env python3
"""Tests for the model-assisted parts of songlab: the iterate loop's decision
step and the archetype/identity proposal at init.

Nothing here touches the network or the real repository: every model answer
comes from an injected transport, every tool the loop drives is replaced by a
fake, and the workspace is a temporary directory. The environment switch that
keeps a real key out is set per test (setUp/tearDown), never at import time."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import llm  # noqa: E402
import songlab  # noqa: E402
from test_daw_agent import sample_project  # noqa: E402

NO_ENV = {"NEON_CONFIG_DIR": "/nonexistent"}


def fake_assist(answers: list[Any]) -> tuple[llm.Assist, list[dict[str, Any]]]:
    """An Assist whose model replies with `answers` in order. Each answer is a
    dict, or a callable taking the prompt and returning one. Records calls."""
    calls: list[dict[str, Any]] = []
    queue = list(answers)

    def transport(url: str, headers: dict, body: dict, timeout: float) -> tuple[int, str]:
        prompt = body["contents"][0]["parts"][0]["text"]
        system = (body.get("systemInstruction") or {}).get("parts", [{}])[0].get("text", "")
        calls.append({"prompt": prompt, "system": system, "thinking": body["generationConfig"].get("thinkingConfig")})
        answer = queue.pop(0) if queue else {"stop": True, "why": "out of answers"}
        if callable(answer):
            answer = answer(prompt)
        if isinstance(answer, tuple):  # (status code, raw text)
            return answer
        return 200, json.dumps({"candidates": [{"content": {"parts": [{"text": json.dumps(answer)}]}, "finishReason": "STOP"}]})

    client = llm.Client("gemini", api_key="k", transport=transport, use_cache=False, env=dict(NO_ENV))
    return llm.Assist(client=client), calls


class ModelOffCase(unittest.TestCase):
    """The deterministic path must never find the real key file: switched off
    per test and restored afterwards so nothing leaks into another module."""

    OFF_ENV = {"NEON_AI": "off", "NEON_CONFIG_DIR": "/nonexistent"}

    def setUp(self) -> None:
        super().setUp()
        self._saved_env = {name: os.environ.get(name) for name in self.OFF_ENV}
        os.environ.update(self.OFF_ENV)

    def tearDown(self) -> None:
        for name, value in self._saved_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        super().tearDown()


class Workspace:
    """A throwaway repository root with one project and one songlab session."""

    def __init__(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="songlab-test-"))
        for sub in ("data/projects", "factory/projects", "exports", "midi"):
            (self.tmp / sub).mkdir(parents=True)
        self.project_id = "agent-unit"
        project = sample_project()
        payload = json.dumps(project, indent=2) + "\n"
        (self.tmp / "data" / "projects" / "agent-unit.neon.json").write_text(payload, encoding="utf-8")
        (self.tmp / "factory" / "projects" / "agent-unit.neon.json").write_text(payload, encoding="utf-8")
        self.saved = (songlab.ROOT, songlab.SONGLAB_DIR, songlab.SONGLAB_PROJECTS_DIR)
        songlab.ROOT = self.tmp
        songlab.SONGLAB_DIR = self.tmp / "songlab"
        songlab.SONGLAB_PROJECTS_DIR = songlab.SONGLAB_DIR / "projects"
        session = songlab.build_session("make a bright future bass track", self.project_id, assist=llm.Assist(enabled=False))
        songlab.write_session_files(self.project_id, session)
        self.session = session

    @property
    def project_path(self) -> Path:
        return self.tmp / "data" / "projects" / "agent-unit.neon.json"

    def project(self) -> dict[str, Any]:
        return json.loads(self.project_path.read_text(encoding="utf-8"))

    def iterations(self) -> list[dict[str, Any]]:
        path = songlab.session_paths(self.project_id)["iterations"]
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def close(self) -> None:
        songlab.ROOT, songlab.SONGLAB_DIR, songlab.SONGLAB_PROJECTS_DIR = self.saved
        shutil.rmtree(self.tmp, ignore_errors=True)


class FakeTools:
    """Replaces the subprocess-driven steps of the loop with recording fakes.
    `scores` are handed out by successive sound checks."""

    def __init__(self, scores: list[int], fidelity: list[Any] | None = None) -> None:
        self.scores = list(scores)
        self.fidelity = list(fidelity or [])
        self.check_calls = 0
        self.ai_choices: set[str] = set()
        self.change_requests: list[str] = []
        self.tactics: list[tuple[str, dict[str, Any]]] = []
        self.renders = 0
        self.saved: dict[str, Callable] = {}

    def install(self) -> "FakeTools":
        fakes = {
            "run_sound_check": self.run_sound_check,
            "run_fidelity": self.run_fidelity,
            "apply_change_request": self.apply_change_request,
            "apply_tactic": self.apply_tactic,
            "rerender_mix": self.rerender_mix,
        }
        for name, fake in fakes.items():
            self.saved[name] = getattr(songlab, name)
            setattr(songlab, name, fake)
        return self

    def uninstall(self) -> None:
        for name, original in self.saved.items():
            setattr(songlab, name, original)

    def run_sound_check(self, project_id: str, session: dict[str, Any], *, ai: str = "auto") -> dict[str, Any]:
        self.check_calls += 1
        self.ai_choices.add(ai)
        score = self.scores.pop(0) if self.scores else 50
        return {
            "ok": True,
            "verdict": {"score": score, "label": "Close", "answer": "Close", "summary": "fake"},
            "metrics": {"rmsDb": -14.0},
            "issues": [{"severity": "medium", "area": "Level", "detail": "The lead is hot.", "requirementIds": ["gain_ladder"]}],
            "nextActions": ["Pull the lead down."],
            "strengths": [],
            "trackReports": [{"id": "lead", "name": "Lead", "rmsDb": -20.0, "gain": 0.74, "pan": 0}],
        }

    def run_fidelity(self, project_id: str, session: dict[str, Any], *, ai: str = "auto") -> Any:
        self.ai_choices.add(ai)
        return self.fidelity.pop(0) if self.fidelity else None

    def _mark(self, marker: str) -> None:
        path = songlab.project_path_for(songlab.read_session("agent-unit"))
        project = json.loads(path.read_text(encoding="utf-8"))
        project.setdefault("markers", []).append(marker)
        path.write_text(json.dumps(project, indent=2) + "\n", encoding="utf-8")

    def apply_change_request(self, project_id: str, session: dict[str, Any], request: str, *, ai: str = "auto") -> dict[str, Any]:
        self.change_requests.append(request)
        self.ai_choices.add(ai)
        if "nonsense" in request:
            return {"applied": False, "edits": [], "unresolved": [f"{request} (no intent)"]}
        self._mark(f"change:{request}")
        return {"applied": True, "understood": request, "edits": [{"title": "Level", "detail": request}], "unresolved": [],
                "ai": {"used": True, "provider": "gemini", "model": "fake", "note": ""}, "aiChoice": ai}

    def apply_tactic(self, project_id: str, session: dict[str, Any], feature_id: str, params: dict[str, Any] | None) -> dict[str, Any]:
        self.tactics.append((feature_id, dict(params or {})))
        self._mark(f"tactic:{feature_id}")
        return {"applied": True, "summary": "fake tactic", "actions": [{"featureId": feature_id, "changed": True, "messages": []}]}

    def rerender_mix(self, project_id: str, session: dict[str, Any]) -> dict[str, Any]:
        self.renders += 1
        return {"ok": True}


def iterate_args(**overrides: Any) -> argparse.Namespace:
    values = {"project_id": "agent-unit", "prompt": None, "note": None, "result": None, "rounds": 3, "ai": "auto"}
    values.update(overrides)
    return argparse.Namespace(**values)


class IterateLoopTests(ModelOffCase):
    def setUp(self) -> None:
        super().setUp()
        self.ws = Workspace()

    def tearDown(self) -> None:
        self.ws.close()
        super().tearDown()

    def test_loop_applies_what_the_model_proposed_and_stops_when_the_score_stalls(self) -> None:
        tools = FakeTools(scores=[80, 84, 84]).install()
        assist, calls = fake_assist([
            {"why": "the lead is 6 dB over the drums", "expectedEffect": "lead level drops", "action": {"kind": "change_request", "request": "make the lead quieter"}},
            {"why": "the build is static", "expectedEffect": "filter movement", "action": {
                "kind": "tactic", "featureId": "fl-automation-clips",
                "params": {"trackId": "lead", "parameter": "filter", "points": [{"bar": 16, "value": 0.2}, {"bar": 500, "value": 1.7, "curve": "weird"}]},
            }},
            {"why": "should not be asked", "action": {"kind": "change_request", "request": "louder drums"}},
        ])
        try:
            payload = songlab.run_iterate_loop("agent-unit", songlab.read_session("agent-unit"), assist, rounds=3, note="the lead feels loud", result=None)
        finally:
            tools.uninstall()

        # The planning call reasons with thinking high and sees the person's note and the check.
        self.assertEqual(calls[0]["thinking"], {"thinkingLevel": "high"})
        self.assertIn("the lead feels loud", calls[0]["prompt"])
        self.assertIn("The lead is hot.", calls[0]["prompt"])
        self.assertEqual(len(calls), 2, "the loop stopped after the round that did not improve")

        # Round 1 was applied through describe_change and kept (80 -> 84).
        self.assertEqual(tools.change_requests, ["make the lead quieter"])
        self.assertEqual(payload["rounds"][0]["before"], {"sound": 80, "fidelity": None})
        self.assertEqual(payload["rounds"][0]["after"], {"sound": 84, "fidelity": None})
        self.assertTrue(payload["rounds"][0]["kept"])
        self.assertEqual(payload["rounds"][0]["action"]["source"], "model")
        self.assertEqual(payload["rounds"][0]["action"]["reason"], "the lead is 6 dB over the drums")

        # Round 2 applied the tactic with clamped parameters, did not improve, and was reverted.
        self.assertEqual(tools.tactics[0][0], "fl-automation-clips")
        points = tools.tactics[0][1]["points"]
        self.assertEqual(points[-1]["value"], 1.0)
        self.assertLessEqual(points[-1]["bar"], 24.0)
        self.assertEqual(points[-1]["curve"], "linear")
        self.assertFalse(payload["rounds"][1]["kept"])
        self.assertIn("did not improve", payload["stopped"])
        self.assertEqual(self.ws.project().get("markers"), ["change:make the lead quieter"], "the rejected round's edit was undone")
        self.assertEqual(tools.renders, 2)
        self.assertEqual(tools.check_calls, 3)
        # every tool the round drove was told the round's --ai choice, and the
        # entry logs describe_change's own model call
        self.assertEqual(tools.ai_choices, {"auto"})
        self.assertEqual(payload["rounds"][0]["toolAi"], {"describe_change": {"used": True, "provider": "gemini", "model": "fake", "note": ""}})
        self.assertNotIn("toolAi", payload["rounds"][1])

        # Every round is in the log with before/after and the ai block; the session remembers both.
        records = self.ws.iterations()
        self.assertEqual([record["round"] for record in records], [1, 2])
        self.assertTrue(all(record["ai"]["used"] for record in records))
        self.assertEqual(records[1]["after"]["sound"], 84)
        session = songlab.read_session("agent-unit")
        statuses = [(item["status"], item.get("source")) for item in session["iterationBacklog"] if item.get("source") == "model"]
        self.assertEqual(statuses, [("done", "model"), ("rejected", "model")])
        self.assertEqual(payload["scoreBefore"], {"sound": 80, "fidelity": None})
        self.assertEqual(payload["scoreAfter"], {"sound": 84, "fidelity": None})
        self.assertTrue(payload["ai"]["used"])
        self.assertTrue((songlab.session_paths("agent-unit")["base"] / "last_sound_check.json").exists())

    def test_model_stop_is_logged_and_nothing_is_applied(self) -> None:
        tools = FakeTools(scores=[86]).install()
        assist, _ = fake_assist([{"stop": True, "why": "no measured issue is left to fix"}])
        try:
            payload = songlab.run_iterate_loop("agent-unit", songlab.read_session("agent-unit"), assist, rounds=3, note=None, result=None)
        finally:
            tools.uninstall()
        self.assertIn("model stopped", payload["stopped"])
        self.assertEqual(tools.change_requests, [])
        self.assertEqual(self.ws.iterations()[0]["action"]["kind"], "stop")

    def test_a_request_the_grammar_rejects_is_reverted_and_stops(self) -> None:
        tools = FakeTools(scores=[70, 70]).install()
        assist, _ = fake_assist([{"why": "w", "action": {"kind": "change_request", "request": "nonsense words"}}])
        try:
            payload = songlab.run_iterate_loop("agent-unit", songlab.read_session("agent-unit"), assist, rounds=2, note=None, result=None)
        finally:
            tools.uninstall()
        self.assertIn("changed nothing", payload["stopped"])
        self.assertNotIn("markers", self.ws.project())
        self.assertEqual(tools.renders, 0)

    def test_invalid_plan_falls_back_to_the_old_iterate(self) -> None:
        tools = FakeTools(scores=[70]).install()
        assist, _ = fake_assist([{"why": "w", "action": {"kind": "teleport"}}])
        try:
            payload = songlab.run_iterate_loop("agent-unit", songlab.read_session("agent-unit"), assist, rounds=2, note="tightened the drums", result="better")
        finally:
            tools.uninstall()
        self.assertIn("no usable plan", payload["stopped"])
        self.assertIn("unknown action kind", payload["ai"]["note"])
        records = self.ws.iterations()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["note"], "tightened the drums")
        self.assertEqual(records[0]["result"], "better")
        self.assertNotIn("action", records[0])

    def test_model_off_keeps_the_old_behaviour(self) -> None:
        tools = FakeTools(scores=[]).install()
        try:
            code = songlab.command_iterate(iterate_args(ai="off", note="rebalanced", result="86/100"))
        finally:
            tools.uninstall()
        self.assertEqual(code, 0)
        self.assertEqual(tools.check_calls, 0)
        records = self.ws.iterations()
        self.assertEqual(records, [{"timestamp": records[0]["timestamp"], "note": "rebalanced", "result": "86/100"}])
        session = songlab.read_session("agent-unit")
        self.assertEqual(session["iterationBacklog"][0]["status"], "in_progress")

    def test_model_off_without_a_note_says_so(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            songlab.command_iterate(iterate_args(ai="off"))
        self.assertIn("--note is required", str(raised.exception))

    def test_spec_decisions_are_refused_for_hand_written_renderers(self) -> None:
        state = {"project": sample_project(), "spec": {"sections": [{"id": "section-01", "type": "drop", "techniques": ["reverb"], "bars": 16}]}, "specEditable": False}
        decision, notes = songlab.validate_decision({"why": "w", "action": {"kind": "spec_decision", "sectionId": "section-01", "addTechniques": ["sidechain"]}}, state)
        self.assertIsNone(decision)
        self.assertIn("hand-written", notes[0])

        state["specEditable"] = True
        decision, notes = songlab.validate_decision(
            {"why": "w", "action": {"kind": "spec_decision", "sectionId": "section-01", "addTechniques": ["sidechain", "reverb", "magic"], "removeTechniques": ["delay"], "bars": 900}},
            state,
        )
        self.assertEqual(decision["addTechniques"], ["sidechain"])
        self.assertEqual(decision["removeTechniques"], [])
        self.assertEqual(decision["bars"], 64)
        self.assertTrue(any("magic" in note for note in notes))
        decision, notes = songlab.validate_decision({"why": "w", "action": {"kind": "spec_decision", "sectionId": "section-99"}}, state)
        self.assertIsNone(decision)
        decision, notes = songlab.validate_decision({"why": "w", "action": {"kind": "tactic", "featureId": "not-a-tactic"}}, state)
        self.assertIsNone(decision)

    def test_round_context_stays_under_the_size_cap(self) -> None:
        state = {
            "project": sample_project(),
            "spec": {"sections": [{"id": f"section-{i:02d}", "type": "drop", "label": "Drop", "bars": 16, "techniques": ["reverb"] * 8, "trackRoles": ["lead"] * 8} for i in range(12)]},
            "soundCheck": {"verdict": {"score": 70}, "issues": [], "nextActions": [], "trackReports": [{"id": str(i), "name": "t" * 40, "rmsDb": -20} for i in range(40)]},
            "fidelity": {"score": 40, "summary": "s", "nextActions": ["x" * 240] * 8, "claims": [{"id": f"claim-{i}", "area": "technique", "claim": "c" * 160, "status": "missing", "evidence": "e" * 200} for i in range(100)]},
            "iterations": [{"timestamp": "t", "note": "n" * 240, "result": "r" * 240} for _ in range(8)],
            "specEditable": True,
        }
        text = songlab.round_context(state, {"normalizedIntent": "i", "archetype": {}, "iterationBacklog": []}, None)
        self.assertLessEqual(len(text), 24000)
        json.loads(text)


class InitProposalTests(ModelOffCase):
    def setUp(self) -> None:
        super().setUp()
        self.ws = Workspace()

    def tearDown(self) -> None:
        self.ws.close()
        super().tearDown()

    def archetype_answer(self) -> dict[str, Any]:
        return {
            "id": "lofi-boom-bap-lane",
            "label": "Lo-fi Boom Bap",
            "normalizedIntent": "Make a slow, dusty boom-bap beat with a warm sampled feel and a lazy swung groove.",
            "referenceSummary": ["Dusty drums with a lazy swing", "Warm sampled keys"],
            "arrangementTargets": ["Two-bar loop that evolves every 8 bars"],
            "soundTargets": ["Vinyl crackle bed", "Round sub"],
            "mixTargets": ["Low end owned by the sub"],
            "iterationBacklog": ["Swing the hats harder before adding layers"],
            "acceptanceChecks": ["The loop nods after one listen"],
            "trackRoles": ["drums", "bass", "keys", "Sample", "vocals"],
            "why": "The brief asks for rainy, slow and lo-fi, which is boom bap, not future bass.",
        }

    def test_archetype_and_identity_come_from_the_model_when_they_validate(self) -> None:
        assist, calls = fake_assist([
            {"projectId": "Rainy Window", "titleHint": "Rainy Window", "why": "the brief is about rain"},
            self.archetype_answer(),
        ])
        prompt = "a slow rainy lo-fi hip hop beat"
        identity = songlab.propose_project_identity(prompt, None, assist)
        self.assertEqual(identity["projectId"], "rainy-window")
        self.assertEqual(songlab.infer_project_id(prompt, None, proposed_id=identity["projectId"]), "rainy-window")
        self.assertEqual(songlab.infer_project_id(prompt, "explicit-id", proposed_id=identity["projectId"]), "explicit-id")

        archetype = songlab.propose_archetype(prompt, None, assist)
        self.assertEqual(archetype["source"], "model")
        self.assertEqual(archetype["trackRoles"], ["drums", "bass", "sample", "vocals"], "unknown roles are dropped")
        self.assertIn("guardrails", calls[1]["prompt"])
        session = songlab.build_session(prompt, "rainy-window", archetype=archetype, assist=assist, title_hint=identity["titleHint"])
        self.assertEqual(session["archetype"]["label"], "Lo-fi Boom Bap")
        self.assertEqual(session["archetype"]["source"], "model")
        self.assertEqual(session["projectName"], "Rainy Window")
        self.assertEqual(session["iterationBacklog"], [{"status": "pending", "focus": "Swing the hats harder before adding layers"}])
        self.assertTrue(session["ai"]["used"])
        self.assertIn("Proposed by the model", songlab.render_plan_markdown(session))
        spec = songlab.build_fallback_spec_from_session(session)
        self.assertEqual(spec["sections"][0]["trackRoles"], ["drums", "bass", "sample", "vocals"])

    def test_bad_answers_fall_back_to_the_keyword_archetype(self) -> None:
        assist, _ = fake_assist([{"projectId": "x"}, {"id": "lane", "label": "L"}])
        self.assertIsNone(songlab.propose_project_identity("a festival future bass banger", None, assist))
        archetype = songlab.propose_archetype("a festival future bass banger", None, assist)
        self.assertEqual(archetype["source"], "heuristic")
        self.assertEqual(archetype["id"], "future-bass-generic")
        self.assertIn("did not validate", assist.note)

    def test_identity_avoids_hand_made_projects(self) -> None:
        (self.ws.tmp / "data" / "projects" / "handmade.neon.json").write_text("{}", encoding="utf-8")
        assist, _ = fake_assist([{"projectId": "Handmade", "titleHint": "Handmade"}, {"projectId": "agent-unit", "titleHint": "Agent Unit"}])
        identity = songlab.propose_project_identity("some song", None, assist)
        self.assertEqual(identity["projectId"], "handmade-2", "a project with no songlab session is not ours to overwrite")
        identity = songlab.propose_project_identity("some song", None, assist)
        self.assertEqual(identity["projectId"], "agent-unit", "a project with a session is re-initialised in place")

    def test_init_with_the_model_off_is_unchanged(self) -> None:
        args = argparse.Namespace(
            prompt="a festival future bass banger", project_id="fresh-song", transcript_text=None, transcript_file=None,
            transcript_stdin=False, no_fill_blanks=False, no_materialize=True, force_materialize=False, ai="off",
        )
        self.assertEqual(songlab.command_init(args), 0)
        session = songlab.read_session("fresh-song")
        self.assertEqual(session["archetype"]["id"], "future-bass-generic")
        self.assertEqual(session["archetype"]["source"], "heuristic")
        self.assertFalse(session["ai"]["used"])
        self.assertEqual(session["ai"]["note"], "AI off for this run")
        self.assertNotIn("projectIdentity", session)


class ToolWiringTests(ModelOffCase):
    """One Assist (or one 'off') reaches every tool init, materialize and the
    loop drive - in-process ones by keyword, subprocesses by --ai and NEON_AI."""

    def setUp(self) -> None:
        super().setUp()
        self.ws = Workspace()

    def tearDown(self) -> None:
        self.ws.close()
        super().tearDown()

    def init_args(self, **overrides: Any) -> argparse.Namespace:
        values = {
            "prompt": None, "project_id": "wired-song", "transcript_text": TRANSCRIPT, "transcript_file": None,
            "transcript_stdin": False, "no_fill_blanks": False, "no_materialize": False, "force_materialize": False, "ai": "off",
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    def record_tools(self, seen: dict[str, list]) -> dict[str, Callable]:
        real_analyze, real_fill = songlab.analyze_transcript, songlab.fill_in_blanks

        def analyze(text, project_id, prompt=None, assist=None):
            seen["ingest"].append(assist)
            return real_analyze(text, project_id, prompt=prompt, assist=llm.Assist(enabled=False))

        def fill(spec, *, prompt=None, sound_check=None, assist=None):
            seen["fill"].append(assist)
            return real_fill(spec, prompt=prompt, assist=llm.Assist(enabled=False))

        def materialize(project_id, session, transcript_spec=None, *, force=False, assist=None):
            seen["materialize"].append(assist)
            return {"skipped": True, "reason": "test"}

        originals = {"analyze_transcript": real_analyze, "fill_in_blanks": real_fill, "materialize_project": songlab.materialize_project}
        songlab.analyze_transcript, songlab.fill_in_blanks, songlab.materialize_project = analyze, fill, materialize
        return originals

    def restore_tools(self, originals: dict[str, Callable]) -> None:
        for name, original in originals.items():
            setattr(songlab, name, original)

    def test_init_with_ai_off_hands_every_tool_an_off_assist(self) -> None:
        seen: dict[str, list] = {"ingest": [], "fill": [], "materialize": []}
        originals = self.record_tools(seen)
        try:
            self.assertEqual(songlab.command_init(self.init_args(ai="off")), 0)
        finally:
            self.restore_tools(originals)
        self.assertEqual([len(seen["ingest"]) >= 1, len(seen["fill"]), len(seen["materialize"])], [True, 1, 1])
        for name, handles in seen.items():
            for handle in handles:
                self.assertIsInstance(handle, llm.Assist, name)
                self.assertFalse(handle.requested, name)
                self.assertFalse(handle.available, name)
        session = songlab.read_session("wired-song")
        self.assertFalse(session["ai"]["used"])
        self.assertEqual(session["ai"]["note"], "AI off for this run")

    def test_init_with_a_model_shares_one_client_with_every_tool(self) -> None:
        assist, _ = fake_assist([
            {"projectId": "wired-song", "titleHint": "Wired Song"},
            {"id": "lane", "label": "L"},   # invalid archetype: keyword lane, so init still completes
        ])
        seen: dict[str, list] = {"ingest": [], "fill": [], "materialize": []}
        originals = self.record_tools(seen)
        real_from_args = llm.assist_from_args
        llm.assist_from_args = lambda args: assist
        try:
            self.assertEqual(songlab.command_init(self.init_args(ai="auto", project_id=None)), 0)
        finally:
            llm.assist_from_args = real_from_args
            self.restore_tools(originals)
        handles = seen["ingest"] + seen["fill"]
        self.assertTrue(handles)
        for handle in handles:
            self.assertIs(handle.client, assist.client, "the same model, one key, one cache")
            self.assertIsNot(handle, assist, "but each tool reports its own questions")
            self.assertTrue(handle.requested)
        # materialize_project takes the session's handle and makes its own child (tested below)
        self.assertEqual(seen["materialize"], [assist])

    def test_child_assists_and_the_ai_choice(self) -> None:
        assist, _ = fake_assist([{"ok": True}])
        child = songlab.tool_assist(assist)
        self.assertIs(child.client, assist.client)
        self.assertFalse(child.used)
        child.ask("say ok", expect=dict)
        self.assertTrue(child.used)
        self.assertFalse(assist.used)
        songlab.absorb(assist, child)
        self.assertTrue(assist.used, "the session's ai block says a tool used the model")
        self.assertEqual(songlab.ai_choice(assist), "auto")

        off = llm.Assist(enabled=False)
        child = songlab.tool_assist(off)
        self.assertFalse(child.requested)
        self.assertEqual(child.note, "AI off for this run")
        self.assertEqual(songlab.ai_choice(off), "off")
        self.assertEqual(songlab.ai_choice(None), "off")

        no_key = llm.Assist(env={"NEON_CONFIG_DIR": "/nonexistent", "NEON_AI": "auto"})
        child = songlab.tool_assist(no_key)
        self.assertTrue(child.requested)
        self.assertFalse(child.available)
        self.assertIn("no API key", child.note)
        self.assertEqual(songlab.ai_choice(no_key), "auto")

    def test_materialize_passes_the_assist_to_the_materializer(self) -> None:
        seen: list = []
        real = songlab.build_project_materialization

        def build(spec, project_id, prompt=None, assist=None):
            seen.append(assist)
            raise RuntimeError("stop here")

        songlab.build_project_materialization = build
        try:
            with self.assertRaises(RuntimeError):
                songlab.materialize_project("agent-unit", self.ws.session, force=True, assist=llm.Assist(enabled=False))
        finally:
            songlab.build_project_materialization = real
        self.assertEqual(len(seen), 1)
        self.assertIsInstance(seen[0], llm.Assist)
        self.assertFalse(seen[0].requested)

    def test_materialize_command_takes_ai(self) -> None:
        args = songlab.build_parser().parse_args(["materialize", "--project-id", "x", "--ai", "off"])
        self.assertEqual(args.ai, "off")
        self.assertEqual(songlab.build_parser().parse_args(["materialize", "--project-id", "x"]).ai, "auto")

    def test_change_requests_carry_the_rounds_ai_choice(self) -> None:
        calls: list = []

        def fake_run_tool(args, timeout=900, *, ai="auto"):
            calls.append(([str(a) for a in args], ai))
            return 0, json.dumps({"edits": [], "unresolved": ["x"], "ai": {"used": False, "provider": None, "model": None, "note": "AI off for this run"}}), ""

        real = songlab.run_tool
        songlab.run_tool = fake_run_tool
        try:
            result = songlab.apply_change_request("agent-unit", self.ws.session, "make the lead quieter", ai="off")
        finally:
            songlab.run_tool = real
        argv, choice = calls[0]
        self.assertEqual(choice, "off")
        self.assertEqual(argv[argv.index("--ai") + 1], "off")
        self.assertTrue(argv[0].endswith("describe_change.py"))
        self.assertFalse(result["applied"])
        self.assertEqual(result["aiChoice"], "off")
        self.assertEqual(result["ai"]["note"], "AI off for this run")

    def test_run_tool_switches_the_model_off_in_the_child(self) -> None:
        saved = os.environ.get("GEMINI_API_KEY")
        os.environ["GEMINI_API_KEY"] = "would-not-be-used"
        os.environ.pop("NEON_AI", None)
        try:
            code, out, _ = songlab.run_tool([songlab.TOOLS / "llm.py"], timeout=60, ai="off")
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["reason"], "NEON_AI=off")
            code, out, _ = songlab.run_tool([songlab.TOOLS / "llm.py"], timeout=60, ai="auto")
            self.assertEqual(code, 0)
            self.assertTrue(json.loads(out)["enabled"], "auto leaves the child's environment alone")
        finally:
            if saved is None:
                os.environ.pop("GEMINI_API_KEY", None)
            else:
                os.environ["GEMINI_API_KEY"] = saved

    def test_renderer_is_generated_needs_the_file(self) -> None:
        self.assertFalse(songlab.renderer_is_generated(None))
        self.assertFalse(songlab.renderer_is_generated(self.ws.tmp / "missing_renderer.py"))
        hand_written = self.ws.tmp / "hand.py"
        hand_written.write_text("print('hi')\n", encoding="utf-8")
        self.assertFalse(songlab.renderer_is_generated(hand_written))
        generated = self.ws.tmp / "generated.py"
        generated.write_text("TRANSCRIPT_SPEC_PATH = 'x'\nSECTION_PLAN = []\n", encoding="utf-8")
        self.assertTrue(songlab.renderer_is_generated(generated))


TRANSCRIPT = "\n".join([
    "0:10 hey everyone today we are going to go over how I made my song wired song so let's get into it",
    "0:30 so it starts out with this pad and I put Serum on it and what I did was layer it with a pluck",
    "1:00 then the build comes in with a riser and the hats go to eighth notes",
    "1:30 the drop has the same melody from the intro but filled in and the kick is on one and three",
    "2:00 and for the mix I put OTT on the lead and that's it for the drop",
])


if __name__ == "__main__":
    unittest.main()
