"""Programmer Chat Completions bridge to the owner's private Codex subscription."""
import asyncio
import json
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from jsonschema import ValidationError

from mg_ai.errors import MGError
from mg_ai.providers import Outcome, Result, clean_completion

CODEX_MODEL = "cx/gpt-5.6-sol-high"
CODEX_CAPABILITIES = {"TEXT", "CODING", "REASONING", "TOOL_CALLING", "LONG_CONTEXT"}
CODEX_CONTEXT_BYTES = 400_000


def responses_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if any(payload.get(key) is not None for key in ("temperature", "top_p", "stop", "response_format")):
        raise MGError("CODEX_UNSUPPORTED_OPTION", 400)
    items: list[dict[str, Any]] = []
    pending: set[str] = set()
    seen: set[str] = set()
    for message in payload["messages"]:
        role = message["role"]
        content = message.get("content")
        if isinstance(content, list):
            if any(part.get("type") != "text" for part in content):
                raise MGError("CODEX_TEXT_ONLY", 400)
            content = "\n".join(part["text"] for part in content)
        if role == "tool":
            call_id = message.get("tool_call_id")
            if call_id not in pending or not isinstance(content, str):
                raise MGError("INVALID_TOOL_HISTORY", 400)
            pending.remove(call_id)
            items.append({"type": "function_call_output", "call_id": call_id, "output": content})
            continue
        if pending or message.get("tool_call_id") or message.get("name"):
            raise MGError("INVALID_TOOL_HISTORY", 400)
        if content:
            items.append({"type": "message", "role": "developer" if role == "system" else role,
                          "content": [{"type": "output_text" if role == "assistant" else "input_text",
                                       "text": content}],
                          **({"status": "completed"} if role == "assistant" else {})})
        for call in message.get("tool_calls", []):
            try:
                call_id = call["id"]
                function = call["function"]
                if (role != "assistant" or call["type"] != "function" or not isinstance(call_id, str)
                        or not call_id or call_id in seen or not isinstance(function["name"], str)
                        or not isinstance(function["arguments"], str)
                        or not isinstance(json.loads(function["arguments"]), dict)):
                    raise ValueError("invalid call")
                seen.add(call_id)
                pending.add(call_id)
                items.append({"type": "function_call", "call_id": call_id,
                              "name": function["name"], "arguments": function["arguments"]})
            except (KeyError, TypeError, ValueError):
                raise MGError("INVALID_TOOL_HISTORY", 400) from None
    if pending or not items:
        raise MGError("INVALID_TOOL_HISTORY", 400)
    choice = payload.get("tool_choice", "auto" if payload.get("tools") else "none")
    if isinstance(choice, dict):
        choice = {"type": "function", "name": choice["function"]["name"]}
    return {"model": CODEX_MODEL, "input": items, "stream": False,
            "tools": [{"type": "function", **tool["function"],
                       "strict": tool["function"].get("strict", False)}
                      for tool in payload.get("tools", [])],
            "tool_choice": choice, "reasoning": {"effort": "high"},
            "max_output_tokens": payload["max_tokens"]}


def chat_completion(data: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    if (data.get("status") != "completed" or data.get("error") or data.get("model") not in
            {CODEX_MODEL, "codex/gpt-5.6-sol-high", "gpt-5.6-sol-high", "gpt-5.6-sol"}):
        raise ValueError("unexpected response")
    text: list[str] = []
    calls = []
    ids: set[str] = set()
    for item in data["output"]:
        if item["type"] == "reasoning":
            continue
        if item["type"] == "function_call":
            call_id = item["call_id"]
            if not isinstance(call_id, str) or not call_id or call_id in ids:
                raise ValueError("invalid call identity")
            ids.add(call_id)
            calls.append({"id": call_id, "type": "function", "function": {
                "name": item["name"], "arguments": item["arguments"]}})
        elif item["type"] == "message" and item.get("role") == "assistant":
            for part in item["content"]:
                if part["type"] != "output_text" or not isinstance(part["text"], str):
                    raise ValueError("unexpected output")
                text.append(part["text"])
        else:
            raise ValueError("unsupported output")
    usage = data.get("usage") or {}
    normalized = {"choices": [{"message": {"role": "assistant",
        "content": "".join(text) if text else None, **({"tool_calls": calls} if calls else {})},
        "finish_reason": "tool_calls" if calls else "stop"}],
        "usage": {target: usage[source] for source, target in (
            ("input_tokens", "prompt_tokens"), ("output_tokens", "completion_tokens"),
            ("total_tokens", "total_tokens")) if source in usage}}
    return clean_completion(normalized, payload)


class ProgrammerAdapter:
    def __init__(self, url: str, token: str, transport: httpx.AsyncBaseTransport | None = None):
        origin = httpx.URL(url)
        if (origin.scheme not in {"http", "https"} or not origin.host or origin.username
                or origin.password or origin.query or origin.fragment or origin.path not in {"", "/"}):
            raise ValueError("private OmniRoute origin required")
        self.configured = len(token) >= 20
        self.busy = asyncio.Lock()
        self.http = httpx.AsyncClient(base_url=url, timeout=httpx.Timeout(240, connect=5),
            headers={"Authorization": "Bearer " + token, "User-Agent": "codex-mg-programmer/0.1",
                     "originator": "codex-mg-programmer"},
            transport=transport, trust_env=False, follow_redirects=False)

    @classmethod
    def from_file(cls, url: str, path: str) -> "ProgrammerAdapter":
        try:
            token = Path(path).read_text(encoding="utf-8").strip() if path else ""
        except OSError:
            token = ""
        return cls(url, token)

    async def execute(self, translated: dict[str, Any], payload: dict[str, Any]) -> Result:
        start = time.monotonic()
        try:
            async with self.http.stream("POST", "/v1/responses", json=translated,
                                        headers={"session_id": str(uuid4())}) as response:
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > 4_194_304:
                        return Result(Outcome.EXECUTION_AMBIGUOUS, category="RESPONSE_TOO_LARGE")
                status = response.status_code
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
            return Result(Outcome.FAILED_TERMINAL, category="CODEX_NOT_REACHED")
        except httpx.HTTPError:
            return Result(Outcome.EXECUTION_AMBIGUOUS, category="CODEX_DISPATCH_UNCERTAIN")
        if status in {400, 401, 403, 404, 422}:
            return Result(Outcome.FAILED_TERMINAL, category="CODEX_REJECTED")
        try:
            if status != 200:
                raise ValueError("uncertain dispatch")
            clean = chat_completion(json.loads(data), payload)
            return Result(Outcome.SUCCESS, clean, latency_ms=(time.monotonic() - start) * 1000)
        except (ValueError, KeyError, TypeError, AttributeError, ValidationError):
            return Result(Outcome.EXECUTION_AMBIGUOUS, category="CODEX_INVALID_RESPONSE")
