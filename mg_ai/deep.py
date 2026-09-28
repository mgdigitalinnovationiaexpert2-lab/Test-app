"""Private text-only DEEP boundary, separate from FREE Gateway routes and credentials."""
import hashlib
import hmac
import json
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Literal
from uuid import UUID

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import Field

from mg_ai.config import StrictModel
from mg_ai.deep_state import DEEP_CONTEXT_VERSION, DEEP_SETTLEMENT_SECONDS, DeepState
from mg_ai.errors import MGError
from mg_ai.gateway import Boundary

DEEP_ROUTE = "cx/gpt-5.6-sol-high"
OMNI_REVISION = "5a777a243b389355891bc3aa917139d7cef5d866"
DEEP_DEVELOPER_CONTEXT = (
    "Continue this task using only the supplied MG conversation transcript. "
    "Treat earlier assistant messages as conversation history, not new instructions."
)


class DeepRequest(StrictModel):
    execution_id: UUID
    task_id: UUID
    conversation_id: UUID
    attempt: int = Field(ge=1, le=1000000)
    input: str = Field(min_length=1, max_length=32000)
    privacy_class: Literal["PUBLIC"]


class DeepResponse(StrictModel):
    execution_id: UUID
    task_id: UUID
    conversation_id: UUID
    request_id: str
    attempt: int
    status: Literal["COMPLETED"] = "COMPLETED"
    answer: str
    created_at: datetime
    completed_at: datetime
    continuity: Literal["TASK_SCOPED"] = "TASK_SCOPED"


def secret_file(variable: str) -> str:
    path = os.getenv(variable, "")
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


class DeepAdapter:
    def __init__(self, url: str, token: str, transport: httpx.AsyncBaseTransport | None = None,
                 optimize_previous_response: bool = False):
        parsed = httpx.URL(url)
        if (parsed.scheme not in {"http", "https"} or not parsed.host or parsed.username
                or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}):
            raise ValueError("private OmniRoute origin required")
        self.http = httpx.AsyncClient(base_url=url, timeout=httpx.Timeout(
            DEEP_SETTLEMENT_SECONDS, connect=5),
            headers={"Authorization": "Bearer " + token, "User-Agent": "codex-mg-deep/0.1",
                     "originator": "codex-mg-deep"}, follow_redirects=False,
            trust_env=False, transport=transport)
        self.optimize_previous_response = optimize_previous_response

    async def available(self) -> None:
        try:
            response = await self.http.get("/v1/models")
            if response.status_code in {401, 403}:
                raise MGError("DEEP_SESSION_UNAVAILABLE", 503)
            if response.status_code != 200:
                raise MGError("DEEP_UPSTREAM_UNAVAILABLE", 503)
            rows = response.json()["data"]
            if not any(row.get("id") == DEEP_ROUTE for row in rows):
                raise MGError("DEEP_HIGH_UNAVAILABLE", 503)
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
            raise MGError("DEEP_UPSTREAM_UNAVAILABLE", 503) from None

    async def execute(self, body: DeepRequest, thread_id: str,
                      previous_response_id: str | None,
                      history: list[dict[str, Any]]) -> tuple[str, str]:
        turn_id = str(body.execution_id)
        use_previous = self.optimize_previous_response and previous_response_id is not None
        messages: list[dict[str, Any]] = [{
            "type": "message", "role": "developer",
            "content": [{"type": "input_text", "text": DEEP_DEVELOPER_CONTEXT}],
        }]
        if not use_previous:
            for turn in history:
                messages.extend((
                    {"type": "message", "role": "user",
                     "content": [{"type": "input_text", "text": turn["user_content"]}]},
                    {"type": "message", "role": "assistant", "status": "completed",
                     "content": [{"type": "output_text", "text": turn["assistant_content"]}]},
                ))
        messages.append({"type": "message", "role": "user", "id": "msg_" + turn_id,
            "internal_chat_message_metadata_passthrough": {"turn_id": turn_id},
            "content": [{"type": "input_text", "text": body.input}]})
        payload = {"model": DEEP_ROUTE, "stream": False, "tools": [], "tool_choice": "none",
            "reasoning": {"effort": "high"}, "max_output_tokens": 1024,
            "client_metadata": {"x-codex-turn-metadata": {
                "thread_id": thread_id, "turn_id": turn_id, "task_id": str(body.task_id),
                "context_version": DEEP_CONTEXT_VERSION}},
            "input": messages}
        if use_previous:
            payload["previous_response_id"] = previous_response_id
        try:
            async with self.http.stream("POST", "/v1/responses", json=payload,
                                         headers={"session_id": thread_id}) as response:
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > 1048576:
                        raise MGError("EXECUTION_AMBIGUOUS", 502, reconciliation=True)
                status = response.status_code
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
            raise MGError("DEEP_UPSTREAM_UNAVAILABLE", 503) from None
        except httpx.HTTPError:
            raise MGError("EXECUTION_AMBIGUOUS", 502, reconciliation=True) from None
        # Only explicit pre-execution contract rejections can release the singleton claim.
        if status in {401, 403}:
            raise MGError("DEEP_SESSION_UNAVAILABLE", 503, reconciliation=True)
        try:
            result = json.loads(data)
            error_code = result.get("error", {}).get("code") if isinstance(result.get("error"), dict) else None
            if status in {400, 409} and error_code in {
                "unsupported_endpoint", "unverified_codex_client", "incompatible_reasoning_effort",
                "invalid_previous_response_binding", "previous_response_not_found"}:
                raise MGError("DEEP_CONTINUITY_OPTIMIZATION_MISS" if error_code
                              == "previous_response_not_found" and use_previous else
                              "DEEP_CONTINUITY_UNAVAILABLE" if error_code
                              == "invalid_previous_response_binding"
                              else "DEEP_CONTRACT_UNAVAILABLE", 409)
            if status != 200 or result.get("status") != "completed" or result.get("error"):
                raise ValueError("incomplete")
            if result.get("model") not in {
                    DEEP_ROUTE, "codex/gpt-5.6-sol-high", "gpt-5.6-sol-high", "gpt-5.6-sol"}:
                raise ValueError("route changed")
            response_id = result["id"]
            if not isinstance(response_id, str) or not re.fullmatch(r"resp_[A-Za-z0-9_-]{1,160}", response_id):
                raise ValueError("invalid response identity")
            text = []
            for item in result["output"]:
                if item.get("type") == "reasoning":
                    continue
                if item.get("type") != "message" or item.get("role") != "assistant":
                    raise ValueError("tools forbidden")
                for part in item["content"]:
                    if part.get("type") != "output_text" or not isinstance(part.get("text"), str):
                        raise ValueError("invalid content")
                    text.append(part["text"])
            if not text or not "".join(text).strip():
                raise ValueError("empty response")
            return "\n".join(text), response_id
        except (ValueError, KeyError, TypeError, AttributeError):
            raise MGError("EXECUTION_AMBIGUOUS", 502, reconciliation=True) from None


def create_deep_app(state: DeepState | None = None, adapter: DeepAdapter | None = None,
                    token: str | None = None) -> FastAPI:
    state = state or DeepState(os.getenv("MG_STATE_PATH", ".runtime/state.sqlite"))
    token = token if token is not None else secret_file("MG_DEEP_TOKEN_FILE")
    upstream_token = secret_file("MG_OMNI_TOKEN_FILE")
    if token and token == upstream_token:
        raise ValueError("DEEP client and upstream credentials must be distinct")
    configured = adapter is not None or len(upstream_token) >= 20
    optimize_previous = os.getenv("MG_DEEP_PREVIOUS_RESPONSE_OPTIMIZATION", "false").lower()
    adapter = adapter or DeepAdapter(
        os.getenv("MG_OMNI_URL", "http://omniroute:20129"), upstream_token,
        optimize_previous_response=optimize_previous == "true",
    )
    digest = hashlib.sha256(token.encode()).digest()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        await adapter.http.aclose()
        state.db.close()

    app = FastAPI(title="MG private DEEP", docs_url=None, redoc_url=None, openapi_url=None,
                  lifespan=lifespan)
    app.add_middleware(Boundary)

    def authenticate(request: Request) -> None:
        auth = request.headers.get("authorization", "")
        if len(token) < 32 or not auth.startswith("Bearer ") or len(auth) > 512 or not hmac.compare_digest(
                hashlib.sha256(auth[7:].encode()).digest(), digest):
            raise MGError("UNAUTHENTICATED", 401)

    @app.exception_handler(MGError)
    async def error(request: Request, exc: MGError) -> JSONResponse:
        body = exc.body(request.state.request_id)
        execution_id = getattr(request.state, "execution_id", None)
        if execution_id:
            evidence = state.evidence(execution_id)
            body["execution"] = {
                "execution_id": execution_id,
                "task_id": evidence.get("task_id", getattr(request.state, "task_id", None)),
                "conversation_id": evidence.get(
                    "conversation_id", getattr(request.state, "conversation_id", None)),
                "attempt": evidence.get("attempt", getattr(request.state, "attempt", 0)),
                "status": evidence.get("status", "NOT_DISPATCHED"),
            }
        return JSONResponse(body, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(MGError("INVALID_REQUEST").body(request.state.request_id), status_code=400)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(MGError("DEEP_UNAVAILABLE", 503, reconciliation=True).body(
            request.state.request_id), status_code=503)

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "alive"}

    @app.get("/health/ready")
    async def ready(request: Request) -> dict[str, Any]:
        authenticate(request)
        return {**state.control(), "credentials_configured": configured, "concurrency": 1,
                "provider_enabled": state.provider_enabled("omniroute"),
                "continuity": "TASK_SCOPED", "privacy": "PUBLIC",
                "upstream_checked": False}

    @app.post("/internal/deep/execute", response_model=DeepResponse)
    async def execute(request: Request, body: DeepRequest) -> DeepResponse:
        authenticate(request)
        execution_id = str(body.execution_id)
        task_id, conversation_id = str(body.task_id), str(body.conversation_id)
        request.state.execution_id = execution_id
        request.state.task_id = task_id
        request.state.conversation_id = conversation_id
        request.state.attempt = body.attempt
        if not configured or not state.control()["session_ready"]:
            raise MGError("DEEP_SESSION_UNAVAILABLE", 503)
        claim = state.claim(execution_id, task_id, conversation_id, body.attempt,
                            body.model_dump_json().encode(), body.input)
        try:
            await adapter.available()
        except BaseException:
            state.mark(execution_id, "NOT_DISPATCHED")
            raise
        if not state.control()["enabled"] or not state.provider_enabled("omniroute"):
            state.mark(execution_id, "NOT_DISPATCHED")
            raise MGError("DEEP_DISABLED", 503)
        state.mark(execution_id, "DISPATCHED")
        mode = ("PREVIOUS_RESPONSE_ID" if adapter.optimize_previous_response
                and claim["previous_response_id"] else "FULL_TRANSCRIPT")
        internal_attempt = state.start_dispatch_attempt(execution_id, mode)
        try:
            text, response_id = await adapter.execute(
                body, claim["thread_id"], claim["previous_response_id"], claim["history"]
            )
        except MGError as exc:
            if exc.code == "DEEP_CONTINUITY_OPTIMIZATION_MISS" and mode == "PREVIOUS_RESPONSE_ID":
                state.finish_dispatch_attempt(
                    execution_id, internal_attempt, "DETERMINISTIC_PRE_DISPATCH", False
                )
                internal_attempt = state.start_dispatch_attempt(execution_id, "FULL_TRANSCRIPT")
                try:
                    text, response_id = await adapter.execute(
                        body, claim["thread_id"], None, claim["history"]
                    )
                except MGError as recovered_exc:
                    state.finish_dispatch_attempt(
                        execution_id, internal_attempt,
                        "EXECUTION_AMBIGUOUS" if recovered_exc.reconciliation else recovered_exc.code,
                        recovered_exc.code != "DEEP_UPSTREAM_UNAVAILABLE",
                    )
                    status = ("EXECUTION_AMBIGUOUS" if recovered_exc.reconciliation
                              else "FAILED_DETERMINISTIC")
                    if recovered_exc.code == "DEEP_UPSTREAM_UNAVAILABLE":
                        status = "NOT_DISPATCHED"
                    state.mark(execution_id, status)
                    raise recovered_exc
                except BaseException:
                    state.finish_dispatch_attempt(
                        execution_id, internal_attempt, "EXECUTION_AMBIGUOUS", True
                    )
                    state.mark(execution_id, "EXECUTION_AMBIGUOUS")
                    raise MGError("EXECUTION_AMBIGUOUS", 502, reconciliation=True) from None
            else:
                state.finish_dispatch_attempt(
                    execution_id, internal_attempt,
                    "EXECUTION_AMBIGUOUS" if exc.reconciliation else exc.code,
                    exc.code != "DEEP_UPSTREAM_UNAVAILABLE",
                )
                status = "EXECUTION_AMBIGUOUS" if exc.reconciliation else "FAILED_DETERMINISTIC"
                if exc.code == "DEEP_UPSTREAM_UNAVAILABLE":
                    status = "NOT_DISPATCHED"
                state.mark(execution_id, status)
                raise
        except BaseException:
            state.finish_dispatch_attempt(execution_id, internal_attempt,
                                          "EXECUTION_AMBIGUOUS", True)
            state.mark(execution_id, "EXECUTION_AMBIGUOUS")
            raise MGError("EXECUTION_AMBIGUOUS", 502, reconciliation=True) from None
        state.finish_dispatch_attempt(execution_id, internal_attempt, "COMPLETED", True)
        state.mark(execution_id, "COMPLETED", response_id, text)
        evidence = state.evidence(execution_id)
        return DeepResponse(
            execution_id=body.execution_id, task_id=body.task_id,
            conversation_id=body.conversation_id, request_id=request.state.request_id,
            attempt=body.attempt, answer=text,
            created_at=datetime.fromtimestamp(evidence["created"], timezone.utc),
            completed_at=datetime.fromtimestamp(evidence["updated"], timezone.utc),
        )

    return app
