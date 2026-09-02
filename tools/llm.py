#!/usr/bin/env python3
"""The one place the tools talk to a language model.

Every tool that reads or writes *language* - a transcript, a change request in
plain words, the "why" behind an inferred default, the next thing to try - can
ask a model here. Every one of them also keeps working with no model at all:
the caller passes what it would have decided on its own, and gets that back
when the model is off, unreachable, or answers nonsense. Measurement (onsets,
RMS, duck depth, rendering) never goes through here.

Turning it on
    A key in the environment (GEMINI_API_KEY / GOOGLE_API_KEY, or
    ANTHROPIC_API_KEY) or in ~/.config/neon-studio/<provider>_api_key.
    NEON_AI=off disables it everywhere; NEON_AI=gemini|anthropic picks a
    provider; NEON_AI_MODEL overrides the model.

Keeping runs repeatable
    Answers are cached on disk by (provider, model, prompt) under
    ~/.cache/neon-studio/llm, so re-running a tool on the same input gives the
    same output and costs nothing. NEON_AI_CACHE=off disables the cache.

Stdlib only, Python 3.9. Tests inject a transport and never touch the network.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

GEMINI_MODEL = "gemini-flash-latest"   # tracks the current Flash; override with NEON_AI_MODEL
ANTHROPIC_MODEL = "claude-sonnet-5"
ANTHROPIC_VERSION = "2023-06-01"
CONFIG_DIR = Path(os.environ.get("NEON_CONFIG_DIR") or Path.home() / ".config" / "neon-studio")
CACHE_DIR = Path(os.environ.get("NEON_AI_CACHE") or Path.home() / ".cache" / "neon-studio" / "llm")
TIMEOUT_SECONDS = 60.0
RETRIES = 2
RETRYABLE_HTTP = (429, 500, 502, 503, 504)
# A quota reply that asks us to wait longer than this is treated as "not now":
# the call falls back at once and the breaker below keeps every later call in
# this process (and in other processes, via the cache dir) from waiting too.
MAX_RETRY_WAIT_SECONDS = 12.0
BREAKER_DEFAULT_SECONDS = 60.0
# When the chosen Gemini model is over its free-tier quota, the smaller Flash
# Lite model usually still has room; a call moves over to it rather than
# falling back to the rules. Off with NEON_AI_FALLBACK_MODEL=off.
GEMINI_FALLBACK_MODEL = "gemini-flash-lite-latest"
_BREAKER: Dict[str, float] = {}   # (provider/model) -> epoch seconds until which the model is skipped
_RETRY_IN = re.compile(r"retry(?:\s+in|\s+after)?\s*:?\s*(\d+(?:\.\d+)?)\s*s", re.IGNORECASE)

Transport = Callable[[str, Dict[str, str], Dict[str, Any], float], Tuple[int, str]]


class Unavailable(Exception):
    """The model could not be used. The message says why, in plain words."""


def retry_after_seconds(message: str) -> Optional[float]:
    """The wait a quota reply asked for ("Please retry in 34.5s", retryDelay "34s"), if any."""
    match = _RETRY_IN.search(message or "")
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


@dataclass
class Result:
    data: Any
    text: str
    provider: str
    model: str
    cached: bool = False


# ---------------------------------------------------------------------------
# Keys and provider selection
# ---------------------------------------------------------------------------

def _config_dir(env: Dict[str, str]) -> Path:
    override = env.get("NEON_CONFIG_DIR")
    return Path(override) if override else CONFIG_DIR


def _read_key_file(name: str, env: Optional[Dict[str, str]] = None) -> str:
    env = os.environ if env is None else env
    path = _config_dir(env) / f"{name}_api_key"
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _key_for(provider: str, env: Optional[Dict[str, str]] = None) -> str:
    env = os.environ if env is None else env
    if provider == "gemini":
        return (env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY") or _read_key_file("gemini", env)).strip()
    if provider == "anthropic":
        return (env.get("ANTHROPIC_API_KEY") or _read_key_file("anthropic", env)).strip()
    return ""


def detect(env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """What would happen if a tool asked right now: enabled, provider, model, reason."""
    env = os.environ if env is None else env
    switch = (env.get("NEON_AI") or "auto").strip().lower()
    if switch in ("off", "0", "false", "no"):
        return {"enabled": False, "provider": None, "model": None, "reason": "NEON_AI=off"}
    order = [switch] if switch in ("gemini", "anthropic") else ["gemini", "anthropic"]
    for provider in order:
        if _key_for(provider, env):
            model = (env.get("NEON_AI_MODEL") or "").strip() or (GEMINI_MODEL if provider == "gemini" else ANTHROPIC_MODEL)
            return {"enabled": True, "provider": provider, "model": model, "reason": f"{provider} key found"}
    return {
        "enabled": False, "provider": None, "model": None,
        "reason": "no API key: set GEMINI_API_KEY (or ANTHROPIC_API_KEY), or put one in ~/.config/neon-studio/gemini_api_key",
    }


def status() -> Dict[str, Any]:
    """For tool output and the app's status line."""
    found = detect()
    return {"enabled": found["enabled"], "provider": found["provider"], "model": found["model"], "reason": found["reason"]}


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------

def http_json(url: str, headers: Dict[str, str], body: Dict[str, Any], timeout: float) -> Tuple[int, str]:
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    request.add_header("Content-Type", "application/json")
    for key, value in headers.items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        payload = error.read().decode("utf-8", errors="replace") if hasattr(error, "read") else ""
        return int(error.code), payload
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise Unavailable(f"network: {error}") from error


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


def extract_json(text: str) -> Any:
    """The JSON object in a model reply, tolerating code fences and lead-in prose."""
    candidate = text.strip()
    fenced = _FENCE.match(candidate)
    if fenced:
        candidate = fenced.group(1)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    start = min([i for i in (candidate.find("{"), candidate.find("[")) if i >= 0] or [-1])
    if start < 0:
        raise ValueError("no JSON in reply")
    depth = 0
    opening = candidate[start]
    closing = "}" if opening == "{" else "]"
    for index in range(start, len(candidate)):
        char = candidate[index]
        if char in "{[":
            depth += 1
        elif char in "}]":
            depth -= 1
            if depth == 0:
                return json.loads(candidate[start:index + 1])
    raise ValueError("unterminated JSON in reply")


class Client:
    """One model, one provider. `ask_json` is the whole interface."""

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        *,
        api_key: Optional[str] = None,
        transport: Optional[Transport] = None,
        cache_dir: Optional[Path] = None,
        use_cache: bool = True,
        timeout: float = TIMEOUT_SECONDS,
        env: Optional[Dict[str, str]] = None,
    ) -> None:
        found = detect(env)
        self.provider = provider or found["provider"]
        if not self.provider:
            raise Unavailable(found["reason"])
        self.model = model or (found["model"] if found["provider"] == self.provider else (GEMINI_MODEL if self.provider == "gemini" else ANTHROPIC_MODEL))
        self.api_key = api_key if api_key is not None else _key_for(self.provider, env)
        if not self.api_key:
            raise Unavailable(f"no {self.provider} API key")
        self.transport = transport or http_json
        self.timeout = timeout
        cache_switch = (os.environ if env is None else env).get("NEON_AI_CACHE", "")
        self.use_cache = use_cache and cache_switch.strip().lower() not in ("off", "0", "false", "no")
        self.cache_dir = cache_dir or CACHE_DIR
        self.calls = 0
        fallback = (os.environ if env is None else env).get("NEON_AI_FALLBACK_MODEL", "").strip()
        self.fallback_model: Optional[str] = None
        if self.provider == "gemini" and fallback.lower() != "off":
            candidate = fallback or GEMINI_FALLBACK_MODEL
            self.fallback_model = candidate if candidate != self.model else None
        self.switched_to_fallback = False
        # Gemini 3.x models think before answering unless told not to; for
        # structured extraction that is 20 s of latency for no gain. Callers
        # that want reasoning pass thinking="high" to ask_json.
        self._thinking_config_supported = True

    # -- public ---------------------------------------------------------

    def ask_json(
        self,
        task: str,
        *,
        system: str = "",
        schema: Optional[Dict[str, Any]] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        thinking: str = "low",
    ) -> Result:
        """Ask for a JSON answer. Raises Unavailable when no usable answer came back.

        thinking: "low" (default) keeps a thinking model's deliberation minimal;
        "high" lets it reason first, for planning tasks where that helps."""
        prompt = task.rstrip()
        if schema is not None:
            prompt += "\n\nReturn only a JSON value matching this shape, with no commentary:\n" + json.dumps(schema, indent=1)
        key = self._cache_key(system, prompt, temperature, thinking)
        cached = self._read_cache(key)
        if cached is not None:
            return Result(cached["data"], cached["text"], self.provider, self.model, cached=True)
        blocked = self._breaker_remaining()
        if blocked > 0 and not self._switch_to_fallback():
            raise Unavailable(f"{self.model} is over its quota; not asking again for {int(blocked)} s")
        last_error = "no attempt"
        for attempt in range(RETRIES + 1):
            try:
                text = self._complete(system, prompt, temperature, max_tokens, thinking)
                data = extract_json(text)
            except Unavailable as error:
                last_error = str(error)
                if "retryable" in last_error:
                    wait = retry_after_seconds(last_error)
                    if wait is not None and wait > MAX_RETRY_WAIT_SECONDS:
                        self._trip_breaker(wait)
                        if self._switch_to_fallback():
                            continue
                        raise Unavailable(f"{self.model} is over its quota (asked to wait {int(wait)} s); using the built-in rules for now") from error
                    if attempt < RETRIES:
                        time.sleep(wait if wait is not None else 1.5 * (attempt + 1))
                        continue
                    self._trip_breaker(BREAKER_DEFAULT_SECONDS)
                    raise
                if "network" in last_error and attempt < RETRIES:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise
            except ValueError as error:
                last_error = f"reply was not JSON ({error})"
                if attempt < RETRIES:
                    prompt = prompt + "\n\nYour previous reply was not valid JSON. Reply with the JSON value only."
                    continue
                raise Unavailable(last_error) from error
            self._write_cache(key, {"data": data, "text": text})
            return Result(data, text, self.provider, self.model)
        raise Unavailable(last_error)

    # -- providers ------------------------------------------------------

    def _complete(self, system: str, prompt: str, temperature: float, max_tokens: int, thinking: str = "low") -> str:
        self.calls += 1
        if self.provider == "gemini":
            return self._gemini(system, prompt, temperature, max_tokens, thinking)
        if self.provider == "anthropic":
            return self._anthropic(system, prompt, temperature, max_tokens)
        raise Unavailable(f"unknown provider {self.provider}")

    def _gemini(self, system: str, prompt: str, temperature: float, max_tokens: int, thinking: str = "low") -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        generation: Dict[str, Any] = {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
            "responseMimeType": "application/json",
        }
        if self._thinking_config_supported:
            generation["thinkingConfig"] = {"thinkingLevel": "high" if thinking == "high" else "low"}
        body: Dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": generation,
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        code, text = self.transport(url, {"x-goog-api-key": self.api_key}, body, self.timeout)
        payload = _parse(text)
        if code == 400 and "thinking" in (_error_message(payload) or "").lower() and self._thinking_config_supported:
            # An older model that does not take a thinking setting: drop it and go again.
            self._thinking_config_supported = False
            return self._gemini(system, prompt, temperature, max_tokens, thinking)
        if code in RETRYABLE_HTTP:
            raise Unavailable(f"retryable gemini {code}: {_error_message(payload) or text[:120]}")
        if code != 200:
            raise Unavailable(f"gemini {code}: {_error_message(payload) or text[:200]}")
        try:
            parts = payload["candidates"][0]["content"]["parts"]
            return "".join(str(part.get("text", "")) for part in parts)
        except (KeyError, IndexError, TypeError):
            reason = None
            try:
                reason = payload["candidates"][0].get("finishReason")
            except (KeyError, IndexError, TypeError, AttributeError):
                pass
            raise Unavailable(f"gemini returned no text ({reason or 'unexpected shape'})")

    def _anthropic(self, system: str, prompt: str, temperature: float, max_tokens: int) -> str:
        url = "https://api.anthropic.com/v1/messages"
        body: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system
        headers = {"x-api-key": self.api_key, "anthropic-version": ANTHROPIC_VERSION}
        code, text = self.transport(url, headers, body, self.timeout)
        payload = _parse(text)
        if code in RETRYABLE_HTTP:
            raise Unavailable(f"retryable anthropic {code}: {_error_message(payload) or text[:120]}")
        if code != 200:
            raise Unavailable(f"anthropic {code}: {_error_message(payload) or text[:200]}")
        try:
            return "".join(str(block.get("text", "")) for block in payload["content"] if block.get("type") == "text")
        except (KeyError, TypeError, AttributeError):
            raise Unavailable("anthropic returned no text")

    # -- breaker ----------------------------------------------------------

    def _switch_to_fallback(self) -> bool:
        """Move this client to the fallback model if one is configured, not yet
        in use, and not itself over quota. Returns True when a retry makes sense."""
        if self.switched_to_fallback or not self.fallback_model:
            return False
        self.model = self.fallback_model
        self.switched_to_fallback = True
        return self._breaker_remaining() <= 0

    def _breaker_key(self) -> str:
        return f"{self.provider}/{self.model}"

    def _breaker_path(self) -> Path:
        return self.cache_dir / f"breaker_{self._breaker_key().replace('/', '_')}.json"

    def _breaker_remaining(self) -> float:
        until = _BREAKER.get(self._breaker_key(), 0.0)
        if until <= 0 and self.use_cache:
            try:
                until = float(json.loads(self._breaker_path().read_text(encoding="utf-8")).get("until", 0.0))
                _BREAKER[self._breaker_key()] = until
            except (OSError, ValueError, json.JSONDecodeError, AttributeError):
                until = 0.0
        return max(0.0, until - time.time())

    def _trip_breaker(self, seconds: float) -> None:
        until = time.time() + max(5.0, min(float(seconds), 3600.0))
        _BREAKER[self._breaker_key()] = until
        if self.use_cache:
            try:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                self._breaker_path().write_text(json.dumps({"until": until, "model": self.model}), encoding="utf-8")
            except OSError:
                pass

    # -- cache ------------------------------------------------------------

    def _cache_key(self, system: str, prompt: str, temperature: float, thinking: str = "low") -> str:
        digest = hashlib.sha256()
        for piece in (self.provider, self.model, str(temperature), thinking, system, prompt):
            digest.update(piece.encode("utf-8"))
            digest.update(b"\x00")
        return digest.hexdigest()

    def _read_cache(self, key: str) -> Optional[Dict[str, Any]]:
        if not self.use_cache:
            return None
        path = self.cache_dir / f"{key}.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _write_cache(self, key: str, value: Dict[str, Any]) -> None:
        if not self.use_cache:
            return
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            (self.cache_dir / f"{key}.json").write_text(json.dumps(value), encoding="utf-8")
        except OSError:
            pass


def _parse(text: str) -> Any:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {}


def _error_message(payload: Any) -> str:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = str(error.get("message") or error.get("status") or "")
            for detail in error.get("details") or []:
                delay = detail.get("retryDelay") if isinstance(detail, dict) else None
                if delay and "retry" not in message.lower():
                    message += f" (retry in {delay})"
            return message
        if isinstance(error, str):
            return error
    return ""


# ---------------------------------------------------------------------------
# What tools actually call
# ---------------------------------------------------------------------------

class Assist:
    """A tool's handle on the model, with the bookkeeping the tool reports.

    `ask` returns the model's JSON or None; `note` says why it was None, in
    words a person can read in the tool's output. The tool decides what to do
    with None - always the thing it would have done anyway.
    """

    def __init__(self, enabled: bool = True, *, client: Optional[Client] = None, env: Optional[Dict[str, str]] = None) -> None:
        self.requested = enabled
        self.client: Optional[Client] = None
        self.note = ""
        self.used = False
        if not enabled:
            self.note = "AI off for this run"
            return
        if client is not None:
            self.client = client
            return
        try:
            self.client = Client(env=env)
        except Unavailable as error:
            self.note = str(error)

    @property
    def available(self) -> bool:
        return self.client is not None

    def ask(self, task: str, *, system: str = "", schema: Optional[Dict[str, Any]] = None,
            temperature: float = 0.0, max_tokens: int = 4096, thinking: str = "low", expect: Optional[type] = None) -> Any:
        if self.client is None:
            return None
        try:
            result = self.client.ask_json(task, system=system, schema=schema, temperature=temperature,
                                          max_tokens=max_tokens, thinking=thinking)
        except Unavailable as error:
            self.note = str(error)
            return None
        if expect is not None and not isinstance(result.data, expect):
            self.note = f"model answered with {type(result.data).__name__}, wanted {expect.__name__}"
            return None
        self.used = True
        return result.data

    def report(self) -> Dict[str, Any]:
        """The `ai` block every tool puts in its JSON output."""
        return {
            "used": self.used,
            "provider": self.client.provider if self.client else None,
            "model": self.client.model if self.client else None,
            "note": self.note,
        }


def add_ai_argument(parser: Any) -> None:
    """`--ai auto|off` on a tool's argparse parser."""
    parser.add_argument("--ai", choices=("auto", "off"), default="auto",
                        help="auto: use a model when a key is available; off: never (the heuristics run alone)")


def assist_from_args(args: Any) -> Assist:
    return Assist(enabled=getattr(args, "ai", "auto") != "off")


def ping() -> Dict[str, Any]:
    """One tiny live call: is the key good, which model answered, how long it took."""
    found = detect()
    if not found["enabled"]:
        return {"ok": False, **found}
    started = time.time()
    try:
        client = Client(use_cache=False)
        result = client.ask_json('Reply with the JSON {"ok": true}', max_tokens=64)
        ok = isinstance(result.data, dict) and result.data.get("ok") is True
        return {"ok": ok, "provider": client.provider, "model": client.model,
                "seconds": round(time.time() - started, 2), "reason": "answered" if ok else f"unexpected reply {result.text[:60]!r}"}
    except Unavailable as error:
        return {"ok": False, "provider": found["provider"], "model": found["model"],
                "seconds": round(time.time() - started, 2), "reason": str(error)}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Language-model adapter status")
    parser.add_argument("--ping", action="store_true", help="make one tiny live call and report")
    options = parser.parse_args()
    print(json.dumps(ping() if options.ping else status(), indent=2))
