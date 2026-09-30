import json
import math
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import httpx
from jsonschema import ValidationError, validate

from mg_ai.config import Candidate


class Outcome(StrEnum):
    SAFE_TO_RETRY = "SAFE_TO_RETRY"
    RATE_LIMITED_SAFE = "RATE_LIMITED_SAFE"
    FAILED_TERMINAL = "FAILED_TERMINAL"
    EXECUTION_AMBIGUOUS = "EXECUTION_AMBIGUOUS"
    SUCCESS = "SUCCESS"


@dataclass
class Result:
    outcome: Outcome
    response: dict[str, Any] | None = None
    category: str = "NONE"
    retry_after: float = 60
    latency_ms: float = 0


class LiteLLMAdapter:
    def __init__(self, url: str, token: str, transport: httpx.AsyncBaseTransport | None = None):
        self.http = httpx.AsyncClient(base_url=url, headers={"Authorization": f"Bearer {token}"},
                                     timeout=httpx.Timeout(65, connect=5), transport=transport,
                                     follow_redirects=False, trust_env=False)

    async def execute(self, model: Candidate, payload: dict[str, Any]) -> Result:
        start = time.monotonic()
        try:
            # One registered deployment per alias; MG owns all retries and fallback decisions.
            async with self.http.stream("POST", "/v1/chat/completions", json={
                **payload, "model": model.id, "stream": False
            }) as response:
                chunks = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > 4194304:
                        return Result(Outcome.EXECUTION_AMBIGUOUS,
                                      category="UPSTREAM_RESPONSE_TOO_LARGE")
                    chunks.append(chunk)
                response = httpx.Response(response.status_code, headers=response.headers,
                                          content=b"".join(chunks))
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
            return Result(Outcome.SAFE_TO_RETRY, category="PROXY_NOT_REACHED")
        except httpx.HTTPError:
            return Result(Outcome.EXECUTION_AMBIGUOUS, category="DISPATCH_UNCERTAIN")
        latency = (time.monotonic() - start) * 1000
        if response.status_code == 429:
            review = model.retry_429_review
            if (review is None or review.valid_until <= datetime.now(timezone.utc)
                    or review.provider != model.provider or review.model != model.model):
                return Result(Outcome.EXECUTION_AMBIGUOUS,
                              category="UNREVIEWED_429_ACCEPTANCE", latency_ms=latency)
            try:
                retry = float(response.headers.get("retry-after", "60"))
                if not math.isfinite(retry):
                    retry = 60
            except ValueError:
                retry = 60
            return Result(Outcome.RATE_LIMITED_SAFE, category="UPSTREAM_RATE_LIMITED",
                          retry_after=retry, latency_ms=latency)
        if response.status_code in {401, 403, 404}:
            return Result(Outcome.SAFE_TO_RETRY, category="UPSTREAM_CONFIG_REJECTED",
                          retry_after=300, latency_ms=latency)
        if response.status_code >= 500 or response.status_code in {408, 409}:
            return Result(Outcome.EXECUTION_AMBIGUOUS, category="UPSTREAM_EXECUTION_UNCERTAIN",
                          latency_ms=latency)
        if response.status_code != 200:
            return Result(Outcome.FAILED_TERMINAL, category="UPSTREAM_REJECTED", latency_ms=latency)
        try:
            clean = clean_completion(response.json(), payload)
            return Result(Outcome.SUCCESS, clean, latency_ms=latency)
        except (ValueError, KeyError, TypeError, AttributeError, ValidationError):
            return Result(Outcome.EXECUTION_AMBIGUOUS, category="INVALID_UPSTREAM_RESPONSE",
                          latency_ms=latency)


def clean_completion(data: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    choices = data["choices"]
    if not isinstance(choices, list) or len(choices) != 1:
        raise ValueError("invalid choices")
    message = choices[0]["message"]
    content = message.get("content")
    calls = message.get("tool_calls")
    if message.get("role") != "assistant" or not (isinstance(content, str) or calls):
        raise ValueError("invalid message")
    if calls:
        allowed = {t["function"]["name"]: t["function"]
                   for t in payload.get("tools", [])}
        clean_calls = []
        for call in calls:
            if call["type"] != "function" or call["function"]["name"] not in allowed:
                raise ValueError("invalid tool call")
            arguments = json.loads(call["function"]["arguments"])
            if not isinstance(arguments, dict) or not isinstance(call["id"], str):
                raise ValueError("invalid tool arguments or identity")
            function = allowed[call["function"]["name"]]
            if function.get("parameters"):
                validate(arguments, function["parameters"])
            clean_calls.append({"id": call["id"], "type": "function", "function": {
                "name": call["function"]["name"],
                "arguments": call["function"]["arguments"]}})
        calls = clean_calls
    if payload.get("tool_choice") == "required" and not calls:
        raise ValueError("required tool call missing")
    if payload.get("tool_choice") == "none" and calls:
        raise ValueError("tool call forbidden")
    choice = payload.get("tool_choice")
    if isinstance(choice, dict) and (not calls or any(
        call["function"]["name"] != choice["function"]["name"] for call in calls
    )):
        raise ValueError("named tool choice not honored")
    finish = choices[0].get("finish_reason")
    if finish not in {"stop", "length", "tool_calls", "content_filter"}:
        raise ValueError("invalid finish reason")
    fmt = payload.get("response_format")
    if fmt:
        parsed = json.loads(content)
        if fmt["type"] == "json_schema":
            validate(parsed, fmt["json_schema"]["schema"])
        elif not isinstance(parsed, dict):
            raise ValueError("expected object")
    # Upstream extensions, headers and debugging metadata are never returned to clients.
    clean: dict[str, Any] = {"choices": [{"index": 0, "message": {
        "role": "assistant", "content": content},
        "finish_reason": choices[0].get("finish_reason", "stop")}]}
    if calls:
        clean["choices"][0]["message"]["tool_calls"] = calls
    usage = data.get("usage", {})
    clean["usage"] = {key: value for key, value in usage.items()
                      if key in {"prompt_tokens", "completion_tokens", "total_tokens"}
                      and type(value) is int and value >= 0}
    return clean
