#!/usr/bin/env python3
"""Tests for the model adapter. Nothing here touches the network: every test
injects a transport, and the environment is passed in explicitly."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import llm  # noqa: E402

NO_ENV: dict = {"NEON_CONFIG_DIR": "/nonexistent"}


def gemini_reply(text: str, code: int = 200):
    def transport(url, headers, body, timeout):
        assert "generateContent" in url
        assert headers.get("x-goog-api-key") == "k-gem"
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        return code, json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}]})
    return transport


def anthropic_reply(text: str):
    def transport(url, headers, body, timeout):
        assert url.endswith("/v1/messages")
        assert headers["x-api-key"] == "k-ant" and headers["anthropic-version"]
        assert body["messages"][0]["content"].startswith("task")
        return 200, json.dumps({"content": [{"type": "text", "text": text}]})
    return transport


class DetectionTests(unittest.TestCase):
    def test_off_without_a_key(self) -> None:
        found = llm.detect({**NO_ENV})
        self.assertFalse(found["enabled"])
        self.assertIn("GEMINI_API_KEY", found["reason"])

    def test_gemini_key_wins_by_default(self) -> None:
        found = llm.detect({**NO_ENV, "GEMINI_API_KEY": "a", "ANTHROPIC_API_KEY": "b"})
        self.assertEqual((found["provider"], found["model"]), ("gemini", llm.GEMINI_MODEL))

    def test_switch_picks_provider_and_model(self) -> None:
        found = llm.detect({**NO_ENV, "GEMINI_API_KEY": "a", "ANTHROPIC_API_KEY": "b", "NEON_AI": "anthropic", "NEON_AI_MODEL": "claude-opus-5"})
        self.assertEqual((found["provider"], found["model"]), ("anthropic", "claude-opus-5"))

    def test_neon_ai_off_disables_everything(self) -> None:
        found = llm.detect({**NO_ENV, "GEMINI_API_KEY": "a", "NEON_AI": "off"})
        self.assertFalse(found["enabled"])
        with self.assertRaises(llm.Unavailable):
            llm.Client(env={**NO_ENV, "GEMINI_API_KEY": "a", "NEON_AI": "off"})


class ClientTests(unittest.TestCase):
    def client(self, transport, provider="gemini", key="k-gem"):
        return llm.Client(provider, api_key=key, transport=transport, use_cache=False, env={**NO_ENV})

    def test_gemini_json_round_trip(self) -> None:
        client = self.client(gemini_reply('{"sections": [{"type": "drop", "bars": 16}]}'))
        result = client.ask_json("task", system="sys", schema={"sections": []})
        self.assertEqual(result.data["sections"][0]["type"], "drop")
        self.assertEqual(result.provider, "gemini")
        self.assertFalse(result.cached)

    def test_anthropic_json_round_trip(self) -> None:
        client = self.client(anthropic_reply('{"ok": true}'), provider="anthropic", key="k-ant")
        self.assertEqual(client.ask_json("task").data, {"ok": True})

    def test_fenced_and_prosed_replies_still_parse(self) -> None:
        self.assertEqual(llm.extract_json('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(llm.extract_json('Sure, here it is: {"a": {"b": [1, 2]}} hope that helps'), {"a": {"b": [1, 2]}})
        self.assertEqual(llm.extract_json('[1, 2, 3]'), [1, 2, 3])
        with self.assertRaises(ValueError):
            llm.extract_json("no json here")

    def test_non_json_reply_retries_then_fails_cleanly(self) -> None:
        calls = []

        def transport(url, headers, body, timeout):
            calls.append(body["contents"][0]["parts"][0]["text"])
            return 200, json.dumps({"candidates": [{"content": {"parts": [{"text": "I cannot"}]}}]})
        client = self.client(transport)
        with self.assertRaises(llm.Unavailable) as caught:
            client.ask_json("task")
        self.assertEqual(len(calls), llm.RETRIES + 1)
        self.assertIn("previous reply was not valid JSON", calls[-1])
        self.assertIn("not JSON", str(caught.exception))

    def test_http_error_becomes_unavailable_with_the_reason(self) -> None:
        def transport(url, headers, body, timeout):
            return 403, json.dumps({"error": {"status": "PERMISSION_DENIED", "message": "Your API key was reported as leaked."}})
        client = self.client(transport)
        with self.assertRaises(llm.Unavailable) as caught:
            client.ask_json("task")
        self.assertIn("leaked", str(caught.exception))

    def test_cache_makes_the_second_call_free_and_identical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            transport = gemini_reply('{"n": 1}')
            client = llm.Client("gemini", api_key="k-gem", transport=transport, cache_dir=Path(tmp), env={**NO_ENV})
            first = client.ask_json("task", system="s")
            second = client.ask_json("task", system="s")
            self.assertEqual(client.calls, 1)
            self.assertEqual((first.data, second.data, second.cached), ({"n": 1}, {"n": 1}, True))
            other = client.ask_json("task", system="different")
            self.assertEqual(client.calls, 2)
            self.assertFalse(other.cached)


class AssistTests(unittest.TestCase):
    def test_off_reports_why_and_answers_none(self) -> None:
        assist = llm.Assist(enabled=False)
        self.assertIsNone(assist.ask("anything"))
        self.assertEqual(assist.report(), {"used": False, "provider": None, "model": None, "note": "AI off for this run"})

    def test_no_key_reports_why(self) -> None:
        assist = llm.Assist(env={**NO_ENV})
        self.assertFalse(assist.available)
        self.assertIn("no API key", assist.note)

    def test_ask_returns_data_and_report_says_used(self) -> None:
        client = llm.Client("gemini", api_key="k-gem", transport=gemini_reply('{"edits": []}'), use_cache=False, env={**NO_ENV})
        assist = llm.Assist(client=client)
        self.assertEqual(assist.ask("task", expect=dict), {"edits": []})
        self.assertTrue(assist.report()["used"])
        self.assertEqual(assist.report()["model"], llm.GEMINI_MODEL)

    def test_wrong_shape_is_treated_as_no_answer(self) -> None:
        client = llm.Client("gemini", api_key="k-gem", transport=gemini_reply('[1, 2]'), use_cache=False, env={**NO_ENV})
        assist = llm.Assist(client=client)
        self.assertIsNone(assist.ask("task", expect=dict))
        self.assertIn("wanted dict", assist.note)
        self.assertFalse(assist.used)




class QuotaTests(unittest.TestCase):
    def quota_reply(self, seconds):
        def transport(url, headers, body, timeout):
            return 429, json.dumps({"error": {"code": 429, "status": "RESOURCE_EXHAUSTED",
                                              "message": "You exceeded your current quota.",
                                              "details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": f"{seconds}s"}]}})
        return transport

    def test_retry_after_is_read_from_the_reply(self) -> None:
        self.assertEqual(llm.retry_after_seconds("Please retry in 34.5s."), 34.5)
        self.assertEqual(llm.retry_after_seconds("quota (retry in 7s)"), 7.0)
        self.assertIsNone(llm.retry_after_seconds("no hint here"))

    def test_long_quota_wait_falls_back_at_once_and_trips_the_breaker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            llm._BREAKER.clear()
            calls = []
            transport = self.quota_reply(55)
            def counting(url, headers, body, timeout):
                calls.append(1)
                return transport(url, headers, body, timeout)
            client = llm.Client("gemini", api_key="k", transport=counting, cache_dir=Path(tmp), env={**NO_ENV, "NEON_AI_FALLBACK_MODEL": "off"})
            started = __import__("time").time()
            with self.assertRaises(llm.Unavailable) as caught:
                client.ask_json("task")
            self.assertLess(__import__("time").time() - started, 2.0)
            self.assertEqual(len(calls), 1)
            self.assertIn("over its quota", str(caught.exception))
            # The next call in this process, and in another process reading the
            # same cache dir, does not even ask.
            with self.assertRaises(llm.Unavailable) as again:
                client.ask_json("another task")
            self.assertEqual(len(calls), 1)
            self.assertIn("not asking again", str(again.exception))
            other = llm.Client("gemini", api_key="k", transport=counting, cache_dir=Path(tmp), env={**NO_ENV, "NEON_AI_FALLBACK_MODEL": "off"})
            llm._BREAKER.clear()
            with self.assertRaises(llm.Unavailable):
                other.ask_json("third task")
            self.assertEqual(len(calls), 1)
            llm._BREAKER.clear()

    def test_short_quota_wait_is_honoured_then_succeeds(self) -> None:
        llm._BREAKER.clear()
        state = {"n": 0}
        def transport(url, headers, body, timeout):
            state["n"] += 1
            if state["n"] == 1:
                return 429, json.dumps({"error": {"message": "Please retry in 0.1s."}})
            return 200, json.dumps({"candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}]})
        client = llm.Client("gemini", api_key="k", transport=transport, use_cache=False, env={**NO_ENV})
        self.assertEqual(client.ask_json("task").data, {"ok": True})
        self.assertEqual(state["n"], 2)


class FallbackModelTests(unittest.TestCase):
    def test_quota_on_the_default_moves_the_call_to_flash_lite(self) -> None:
        llm._BREAKER.clear()
        seen = []

        def transport(url, headers, body, timeout):
            seen.append(url.split("/models/")[1].split(":")[0])
            if "lite" not in url:
                return 429, json.dumps({"error": {"message": "quota", "details": [{"retryDelay": "40s"}]}})
            return 200, json.dumps({"candidates": [{"content": {"parts": [{"text": '{"ok": 1}'}]}}]})
        client = llm.Client("gemini", "gemini-flash-latest", api_key="k", transport=transport, use_cache=False, env={**NO_ENV})
        result = client.ask_json("task")
        self.assertEqual(result.data, {"ok": 1})
        self.assertEqual(seen, ["gemini-flash-latest", "gemini-flash-lite-latest"])
        self.assertEqual(result.model, "gemini-flash-lite-latest")
        llm._BREAKER.clear()

    def test_fallback_can_be_switched_off(self) -> None:
        llm._BREAKER.clear()
        client = llm.Client("gemini", "gemini-flash-latest", api_key="k", transport=lambda *a: (429, json.dumps({"error": {"message": "retry in 40s"}})), use_cache=False, env={**NO_ENV, "NEON_AI_FALLBACK_MODEL": "off"})
        with self.assertRaises(llm.Unavailable):
            client.ask_json("task")
        self.assertIsNone(client.fallback_model)
        llm._BREAKER.clear()


if __name__ == "__main__":
    unittest.main()
