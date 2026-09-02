#!/usr/bin/env python3
"""Tests for the MCP server's AI plumbing. Nothing here touches the network:
the one model call goes through an injected transport, and every subprocess
launch is intercepted so the environment and argv handed to it can be checked.

Nothing here changes the process environment at import time. Tests that need
a particular environment pin it with `patch.dict(os.environ, ...)` for their
own duration, so a real key on the machine cannot leak in and nothing leaks out
to the other test modules in the suite."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from typing import Any

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import llm  # noqa: E402
import mcp_server  # noqa: E402

NO_ENV: dict = {"NEON_CONFIG_DIR": "/nonexistent"}


def fake_gemini(text: str):
    def transport(url, headers, body, timeout):
        assert headers.get("x-goog-api-key") == "k"
        return 200, json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}]})
    return transport


def fake_assist(text: str) -> llm.Assist:
    client = llm.Client("gemini", api_key="k", transport=fake_gemini(text), use_cache=False, env=dict(NO_ENV))
    return llm.Assist(client=client)


class Recorder:
    """Stands in for subprocess.run and remembers what it was asked to do."""

    def __init__(self, stdout: str = "{}", returncode: int = 0) -> None:
        self.calls: list[dict[str, Any]] = []
        self.stdout = stdout
        self.returncode = returncode

    def __call__(self, argv, **kwargs):
        self.calls.append({"argv": list(argv), **kwargs})

        class Proc:
            pass

        proc = Proc()
        proc.returncode = self.returncode
        proc.stdout = self.stdout
        proc.stderr = ""
        return proc


class EnvironmentTests(unittest.TestCase):
    def test_scripts_inherit_the_servers_whole_environment(self) -> None:
        base = {"PATH": "/usr/bin", "GEMINI_API_KEY": "abc", "NEON_AI_MODEL": "gemini-x", "OTHER": "1"}
        env = mcp_server._env(ai=True, base=base)
        self.assertEqual(env, base)
        self.assertIsNot(env, base)
        self.assertNotIn("NEON_AI", env)

    def test_default_base_is_the_process_environment(self) -> None:
        with patch.dict(os.environ, {"NEON_AI_MODEL": "gemini-y", "GEMINI_API_KEY": "abc"}, clear=True):
            env = mcp_server._env(ai=True)
        self.assertEqual(env, {"NEON_AI_MODEL": "gemini-y", "GEMINI_API_KEY": "abc"})

    def test_ai_false_turns_the_model_off_even_with_a_key(self) -> None:
        env = mcp_server._env(ai=False, base={"GEMINI_API_KEY": "abc", "NEON_AI": "gemini"})
        self.assertEqual(env["NEON_AI"], "off")
        self.assertFalse(llm.detect({**NO_ENV, **env})["enabled"])

    def test_ai_true_with_a_key_leaves_the_model_on(self) -> None:
        env = mcp_server._env(ai=True, base={"GEMINI_API_KEY": "abc"})
        found = llm.detect({**NO_ENV, **env})
        self.assertTrue(found["enabled"])
        self.assertEqual(found["provider"], "gemini")


class RunTests(unittest.TestCase):
    """Every test pins the process environment with patch.dict for its own
    duration: the real os.environ object is never replaced, so nothing leaks
    into the other modules of the suite."""

    def setUp(self) -> None:
        self._real_run = mcp_server.subprocess.run
        self._environ = patch.dict(os.environ, {"NEON_CONFIG_DIR": "/nonexistent"}, clear=True)
        self._environ.start()
        self.temp = tempfile.TemporaryDirectory()
        self.with_flag = Path(self.temp.name) / "with_flag.py"
        self.with_flag.write_text("from llm import add_ai_argument\n", encoding="utf-8")
        self.without_flag = Path(self.temp.name) / "plain.py"
        self.without_flag.write_text("print('hi')\n", encoding="utf-8")

    def tearDown(self) -> None:
        mcp_server.subprocess.run = self._real_run
        self._environ.stop()
        self.temp.cleanup()

    def test_run_passes_an_explicit_environment(self) -> None:
        recorder = Recorder()
        mcp_server.subprocess.run = recorder
        os.environ.update({"PATH": "/usr/bin", "GEMINI_API_KEY": "abc"})
        mcp_server._run([str(self.without_flag)], ai=True)
        call = recorder.calls[0]
        self.assertEqual(call["env"]["GEMINI_API_KEY"], "abc")
        self.assertEqual(call["cwd"], str(mcp_server.ROOT))
        self.assertEqual(call["argv"][1:], [str(self.without_flag)])

    def test_ai_off_is_only_the_environment_never_a_flag(self) -> None:
        """Scripts that declare --ai before a subcommand (daw_agent.py) reject it
        at the end of argv, so ai=false must never touch the command line."""
        recorder = Recorder()
        mcp_server.subprocess.run = recorder
        os.environ["GEMINI_API_KEY"] = "abc"
        mcp_server._run([str(self.with_flag), "--x"], ai=False)
        mcp_server._run([str(self.without_flag), "--x"], ai=False)
        flagged, plain = recorder.calls
        self.assertEqual(flagged["argv"][1:], [str(self.with_flag), "--x"])
        self.assertEqual(flagged["env"]["NEON_AI"], "off")
        self.assertEqual(plain["argv"][1:], [str(self.without_flag), "--x"])
        self.assertEqual(plain["env"]["NEON_AI"], "off")
        self.assertFalse(llm.detect({**NO_ENV, **flagged["env"]})["enabled"])

    def test_ai_on_never_adds_the_flag(self) -> None:
        recorder = Recorder()
        mcp_server.subprocess.run = recorder
        mcp_server._run([str(self.with_flag)], ai=True)
        self.assertNotIn("--ai", recorder.calls[0]["argv"])

    def test_suggest_improvements_with_ai_false_keeps_daw_agent_argv_intact(self) -> None:
        """The regression: songlab_suggest_improvements ai=false used to exit 2
        with 'unrecognized arguments: --ai off'. The subcommand argv must be
        exactly what daw_agent.py parses, with the model off in the environment."""
        recorder = Recorder(stdout=json.dumps({"summary": "ok", "actions": [],
                                               "ai": {"used": False, "note": "AI off for this run"}}))
        mcp_server.subprocess.run = recorder
        os.environ["GEMINI_API_KEY"] = "abc"
        text = mcp_server.tool_suggest_improvements({"project_id": "neon-alone", "ai": False})
        self.assertEqual(len(recorder.calls), 1)
        argv = recorder.calls[0]["argv"]
        self.assertNotIn("--ai", argv)
        self.assertEqual(argv[2:5], ["--root", str(mcp_server.ROOT), "apply"])
        self.assertEqual(recorder.calls[0]["env"]["NEON_AI"], "off")
        self.assertTrue(text.endswith("(offline rules - AI off for this run)"), text)


class ProvenanceLineTests(unittest.TestCase):
    def test_report_from_a_used_model_names_it(self) -> None:
        assist = fake_assist('{"ok": true}')
        self.assertEqual(assist.ask("q", expect=dict), {"ok": True})
        line = mcp_server._ai_line({"ai": assist.report()})
        self.assertEqual(line, "\n(via gemini-flash-latest)")

    def test_report_from_an_unused_model_says_why(self) -> None:
        assist = llm.Assist(enabled=False)
        line = mcp_server._ai_line({"ai": assist.report()})
        self.assertEqual(line, "\n(offline rules - AI off for this run)")

    def test_no_block_means_no_line(self) -> None:
        self.assertEqual(mcp_server._ai_line({"verdict": {}}), "")
        self.assertEqual(mcp_server._ai_line(None), "")

    def test_model_answer_that_fails_validation_is_reported_as_unused(self) -> None:
        assist = fake_assist('["not", "a", "dict"]')
        self.assertIsNone(assist.ask("q", expect=dict))
        block = assist.report()
        self.assertFalse(block["used"])
        self.assertIn("offline rules", mcp_server._ai_line({"ai": block}))


class ToolSurfaceTests(unittest.TestCase):
    def test_every_model_capable_tool_takes_ai(self) -> None:
        for name in ("songlab_build_song", "songlab_sound_check", "songlab_apply_sound_check",
                     "songlab_suggest_improvements", "songlab_fidelity", "songlab_describe_change",
                     "songlab_listening_questions", "songlab_listening_apply"):
            schema = mcp_server.TOOLS_TABLE[name][2]
            self.assertEqual(schema["properties"]["ai"]["type"], "boolean", name)
            self.assertNotIn("ai", schema.get("required", []), name)

    def test_measurement_only_tools_take_no_ai(self) -> None:
        for name in ("songlab_render", "songlab_hum_to_melody", "songlab_variations", "songlab_use_variation"):
            self.assertNotIn("ai", mcp_server.TOOLS_TABLE[name][2]["properties"], name)

    def _ai_status_text(self) -> str:
        reply = mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                   "params": {"name": "songlab_ai_status", "arguments": {}}})
        return reply["result"]["content"][0]["text"]

    def test_ai_status_with_no_key_says_off_and_why(self) -> None:
        # The status tool reads the real process environment, so pin it for
        # this test only: no key, no NEON_AI switch, no config dir.
        with patch.dict(os.environ, {"NEON_CONFIG_DIR": "/nonexistent"}, clear=True):
            text = self._ai_status_text()
        self.assertIn("AI assistance is off", text)
        self.assertIn("no API key", text)
        payload = json.loads(text.strip().splitlines()[-1])
        self.assertFalse(payload["enabled"])

    def test_ai_status_with_neon_ai_off_names_the_switch(self) -> None:
        with patch.dict(os.environ, {"NEON_CONFIG_DIR": "/nonexistent", "GEMINI_API_KEY": "k", "NEON_AI": "off"}, clear=True):
            text = self._ai_status_text()
        self.assertIn("AI assistance is off", text)
        self.assertIn("NEON_AI=off", text)
        self.assertFalse(json.loads(text.strip().splitlines()[-1])["enabled"])

    def test_describe_change_ai_false_reaches_the_subprocess(self) -> None:
        recorder = Recorder(stdout=json.dumps({"ok": True, "edits": [], "ai": {"used": False, "note": "AI off for this run"}}))
        with patch.dict(os.environ, {"GEMINI_API_KEY": "abc"}, clear=True), \
                patch.object(mcp_server.subprocess, "run", recorder), \
                tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "p.neon.json"
            project.write_text("{}", encoding="utf-8")
            paths = {"project": project, "session": Path(temp), "spec": Path(temp) / "no"}
            with patch.object(mcp_server, "_project_paths", lambda pid: paths):
                text = mcp_server.tool_describe_change({"project_id": "p", "request": "-more bass", "ai": False, "apply": False})
        call = recorder.calls[0]
        self.assertEqual(call["env"]["NEON_AI"], "off")
        self.assertIn("--request=-more bass", call["argv"])
        self.assertIn("(offline rules - AI off for this run)", text)


FIDELITY_REPORT = {
    "projectId": "p", "score": 80, "summary": "close", "claims": [
        {"id": "claim-1", "area": "tempo", "claim": "128 bpm", "status": "matched", "verifiedBy": "project", "evidence": "128"},
    ], "nextActions": [], "nextActionDetails": [],
}


class MarkdownProvenanceTests(unittest.TestCase):
    """songlab_fidelity and songlab_listening_apply return markdown, so the
    trailer has to come from the tool's `ai` block, whichever way it went -
    previously only ai=false got a line, and a silent fallback with ai=true
    (no key, quota) looked exactly like a model answer."""

    def setUp(self) -> None:
        self._environ = patch.dict(os.environ, {"NEON_CONFIG_DIR": "/nonexistent"}, clear=True)
        self._environ.start()

    def tearDown(self) -> None:
        self._environ.stop()

    def _fidelity(self, ai_block: dict, args: dict) -> tuple[str, Recorder]:
        recorder = Recorder(stdout=json.dumps({**FIDELITY_REPORT, "ai": ai_block}))
        with patch.object(mcp_server.subprocess, "run", recorder):
            return mcp_server.tool_fidelity({"project_id": "p", **args}), recorder

    def test_fidelity_names_the_model_when_one_answered(self) -> None:
        text, recorder = self._fidelity({"used": True, "provider": "gemini", "model": "gemini-flash-latest", "note": ""}, {})
        self.assertIn("# Transcript Fidelity: p", text)
        self.assertIn("| 1 | tempo | 128 bpm |", text)
        self.assertTrue(text.endswith("(via gemini-flash-latest)"), text[-200:])
        self.assertIn("--format", recorder.calls[0]["argv"])
        self.assertEqual(recorder.calls[0]["argv"][-1], "json")
        self.assertNotIn("NEON_AI", recorder.calls[0]["env"])

    def test_fidelity_says_why_the_rules_answered_with_ai_on(self) -> None:
        text, _ = self._fidelity({"used": False, "provider": None, "model": None, "note": "no API key"}, {})
        self.assertTrue(text.endswith("(offline rules - no API key)"), text[-200:])

    def test_fidelity_with_ai_false_reports_the_switch(self) -> None:
        text, recorder = self._fidelity({"used": False, "note": "AI off for this run"}, {"ai": False})
        self.assertEqual(recorder.calls[0]["env"]["NEON_AI"], "off")
        self.assertTrue(text.endswith("(offline rules - AI off for this run)"), text[-200:])

    def _listening_apply(self, ai_block: dict, args: dict) -> tuple[str, Recorder]:
        payload = {"summary": "two answers", "steps": [{"label": "Drop", "step": "more sub", "evidence": "listener: thin"}],
                   "notes": [], "warnings": [], "iterationNote": "note", "ai": ai_block}
        recorder = Recorder(stdout=json.dumps(payload))
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "p.neon.json"
            project.write_text("{}", encoding="utf-8")
            paths = {"project": project, "session": Path(temp) / "s", "spec": Path(temp) / "no"}
            with patch.object(mcp_server.subprocess, "run", recorder), patch.object(mcp_server, "_project_paths", lambda pid: paths):
                text = mcp_server.tool_listening_apply({"project_id": "p", "answers": [{"questionId": "q1", "option": "thin"}], **args})
        return text, recorder

    def test_listening_apply_names_the_model_when_one_answered(self) -> None:
        text, recorder = self._listening_apply({"used": True, "provider": "gemini", "model": "gemini-flash-latest"}, {})
        self.assertIn("# Listening Session", text)
        self.assertIn("**Drop**", text)
        self.assertTrue(text.endswith("(via gemini-flash-latest)"), text[-200:])
        argv = recorder.calls[0]["argv"]
        self.assertEqual(argv[argv.index("--format") + 1], "json")

    def test_listening_apply_with_ai_false_reports_the_switch(self) -> None:
        text, recorder = self._listening_apply({"used": False, "note": "AI off for this run"}, {"ai": False})
        self.assertEqual(recorder.calls[0]["env"]["NEON_AI"], "off")
        self.assertTrue(text.endswith("(offline rules - AI off for this run)"), text[-200:])

    def test_listening_apply_with_no_key_says_so_with_ai_on(self) -> None:
        text, _ = self._listening_apply({"used": False, "note": "no API key"}, {})
        self.assertTrue(text.endswith("(offline rules - no API key)"), text[-200:])


if __name__ == "__main__":
    unittest.main()
