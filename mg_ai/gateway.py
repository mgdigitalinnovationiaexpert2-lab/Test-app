import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mg_ai.config import PRIVACY_LEVEL, Configuration, load_config
from mg_ai.errors import MGError
from mg_ai.observability import emit
from mg_ai.providers import LiteLLMAdapter, Outcome
from mg_ai.programmer import (CODEX_CAPABILITIES, CODEX_CONTEXT_BYTES, CODEX_MODEL,
                             ProgrammerAdapter, responses_payload)
from mg_ai.requests import ChatRequest
from mg_ai.config import StrictModel
from mg_ai.routing import select
from mg_ai.state import State


class Boundary:
    def __init__(self, app: ASGIApp, max_body_bytes: int = 1048576) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = str(uuid.uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        chunks: list[bytes] = []
        total = 0
        deadline = time.monotonic() + 10
        try:
            while True:
                message = await asyncio.wait_for(receive(), timeout=max(0, deadline-time.monotonic()))
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                total += len(chunk)
                if total > self.max_body_bytes:
                    raise MGError("REQUEST_TOO_LARGE", 413)
                chunks.append(chunk)
                if not message.get("more_body", False):
                    break
        except (MGError, TimeoutError) as exc:
            error = exc if isinstance(exc, MGError) else MGError("REQUEST_READ_TIMEOUT", 408)
            await JSONResponse(error.body(request_id), status_code=error.status)(scope, receive, send)
            return
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        async def tagged(message: Message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append((b"x-request-id", request_id.encode()))
            await send(message)

        await self.app(scope, replay, tagged)


def create_app(config: Configuration | None = None, state: State | None = None,
               adapter: LiteLLMAdapter | None = None,
               programmer: ProgrammerAdapter | None = None) -> FastAPI:
    config = config or load_config(Path(os.getenv("MG_CONFIG_ROOT", ".")))
    state = state or State(os.getenv("MG_STATE_PATH", ".runtime/state.sqlite"))
    token_hashes: dict[str, bytes] = {}
    for client, policy in config.clients.items():
        token = os.getenv(policy.token_env, "")
        if len(token) < 32:
            raise ValueError(f"Configure a strong token for {client}")
        digest = hashlib.sha256(token.encode()).digest()
        if digest in token_hashes.values():
            raise ValueError("client tokens must be distinct")
        token_hashes[client] = digest
    master = os.getenv("LITELLM_MASTER_KEY", "")
    if adapter is None and (len(master) < 32 or hashlib.sha256(master.encode()).digest()
                            in token_hashes.values()):
        raise ValueError("configure a distinct strong LiteLLM master key")
    adapter = adapter or LiteLLMAdapter(os.getenv("MG_PROXY_URL", "http://127.0.0.1:4000"), master)
    if programmer is None and os.getenv("MG_PROGRAMMER_ENABLED", "false").lower() == "true":
        programmer = ProgrammerAdapter.from_file(
            os.getenv("MG_PROGRAMMER_OMNI_URL", "http://omniroute:20129"),
            os.getenv("MG_PROGRAMMER_TOKEN_FILE", ""))
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        await adapter.http.aclose()
        if programmer:
            await programmer.http.aclose()
        state.db.close()

    app = FastAPI(title="MG AI Infrastructure", version="0.1.0", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(Boundary)

    def authenticate(request: Request) -> str:
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer ") or len(auth) > 512:
            raise MGError("UNAUTHENTICATED", 401)
        digest = hashlib.sha256(auth[7:].encode()).digest()
        found = None
        for name, stored in token_hashes.items():
            if hmac.compare_digest(digest, stored):
                found = name
        if found is None:
            raise MGError("UNAUTHENTICATED", 401)
        return found

    @app.exception_handler(MGError)
    async def mg_error(request: Request, error: MGError) -> JSONResponse:
        return JSONResponse(error.body(request.state.request_id), status_code=error.status,
                            headers={"Retry-After": "60"} if error.retryable else None)

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, error: RequestValidationError) -> JSONResponse:
        return JSONResponse(MGError("INVALID_REQUEST").body(request.state.request_id), status_code=400)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, error: Exception) -> JSONResponse:
        # Exception strings can contain credentials or provider response bodies.
        return JSONResponse(MGError("GATEWAY_UNAVAILABLE", 503,
                                   reconciliation=True).body(request.state.request_id),
                            status_code=503)

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "alive"}

    @app.get("/health/ready")
    async def ready(request: Request) -> dict[str, Any]:
        client = authenticate(request)
        state.db.execute("SELECT 1")
        policy = config.clients[client]
        eligible = {name: len(select(config, policy, config.routes[name],
                                    config.routes[name].capabilities, policy.default_privacy,
                                    0, 1024, state)) for name in sorted(policy.routes)}
        for name in policy.routes:
            if config.routes[name].backend == "CODEX":
                eligible[name] = int(bool(programmer and programmer.configured
                                          and state.provider_enabled("omniroute")))
        return {"status": "ready" if any(eligible.values()) else "configured_no_eligible_provider",
                "client": client, "paid_inference": False, "eligible_routes": eligible}

    @app.get("/v1/models")
    async def models(request: Request) -> dict[str, Any]:
        client = authenticate(request)
        return {"object": "list", "data": [{"id": route, "object": "model", "owned_by": "maghsoud",
                                            "created": 0}
                                           for route in sorted(config.clients[client].routes)]}

    class ReconciliationRequest(StrictModel):
        idempotency_key: str

    @app.post("/internal/executions/reconcile")
    async def reconcile_execution(request: Request, body: ReconciliationRequest) -> dict[str, Any]:
        client = authenticate(request)
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", body.idempotency_key):
            raise MGError("INVALID_IDEMPOTENCY_KEY")
        return state.reconcile(client, body.idempotency_key)

    @app.post("/v1/chat/completions", response_model=None)
    async def chat(request: Request) -> Response:
        client = authenticate(request)
        try:
            body = ChatRequest.model_validate_json(await request.body())
        except ValueError:
            raise MGError("INVALID_REQUEST") from None
        policy = config.clients[client]
        if body.model not in policy.routes:
            raise MGError("ROUTE_FORBIDDEN", 403)
        route = config.routes[body.model]
        privacy = body.mg.privacy_class or policy.default_privacy
        if PRIVACY_LEVEL[privacy] < PRIVACY_LEVEL[policy.default_privacy]:
            raise MGError("PRIVACY_DOWNGRADE_FORBIDDEN", 403)
        required = body.capabilities() | route.capabilities
        if privacy not in policy.privacy_classes or not required <= policy.allowed_capabilities:
            raise MGError("CAPABILITY_OR_PRIVACY_FORBIDDEN", 403)
        key = request.headers.get("idempotency-key")
        if key and not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", key):
            raise MGError("INVALID_IDEMPOTENCY_KEY")
        canonical_data = body.model_dump(mode="json")
        canonical_data["mg"]["required_capabilities"] = sorted(body.mg.required_capabilities)
        canonical = json.dumps(canonical_data, sort_keys=True).encode()
        if key:
            # Duplicate safety must not depend on current model availability or cooldown.
            state.check_duplicate(client, key, canonical)
        payload = body.model_dump(mode="json", exclude={"mg", "stream_options"}, exclude_none=True)
        # UTF-8 bytes provide a conservative text token bound, including tools/schema framing.
        context = max(body.mg.context_tokens, len(json.dumps(payload, ensure_ascii=False).encode()))
        if route.backend == "CODEX":
            if client != "developer" or body.model != "dev-code":
                raise MGError("ROUTE_FORBIDDEN", 403)
            if body.mg.max_cost_class == "FREE":
                raise MGError("SUBSCRIPTION_ROUTE_NOT_FREE", 400)
            if privacy not in {"PUBLIC", "INTERNAL"} or not required <= CODEX_CAPABILITIES:
                raise MGError("CODEX_CAPABILITY_OR_PRIVACY_FORBIDDEN", 403)
            if policy.model_allowlist is not None:
                raise MGError("CODEX_NOT_IN_MODEL_ALLOWLIST", 403)
            if context + body.max_tokens > CODEX_CONTEXT_BYTES:
                raise MGError("CODEX_CONTEXT_LIMIT", 413)
            translated = responses_payload(payload)
            if not programmer or not programmer.configured or not state.provider_enabled("omniroute"):
                raise MGError("CODEX_UNAVAILABLE", 422)
            if programmer.busy.locked():
                raise MGError("CODEX_BUSY", 422)
            async with programmer.busy:
                rid = request.state.request_id
                digest = state.admit(client, policy.requests_per_minute, policy.monthly_request_limit,
                                     key or rid, canonical, rid)
                state.execution(client, digest, "DISPATCHED")
                try:
                    result = await programmer.execute(translated, payload)
                except BaseException:
                    state.execution(client, digest, "AMBIGUOUS")
                    raise MGError("EXECUTION_AMBIGUOUS", 422, reconciliation=True) from None
                state.execution(client, digest, "AMBIGUOUS" if result.outcome == Outcome.EXECUTION_AMBIGUOUS
                                else "TERMINAL")
                if policy.log_metadata:
                    emit(request_id=rid, client=client, route=body.model, provider="omniroute",
                         model="programmer-codex", upstream_model=CODEX_MODEL, attempt=1,
                         result=result.outcome, fallback_count=0, error_category=result.category,
                         latency_ms=result.latency_ms, cost_class="SUBSCRIPTION")
                # SDKs retry 429/5xx automatically; an uncertain coding execution must never replay.
                if result.outcome == Outcome.EXECUTION_AMBIGUOUS:
                    raise MGError("EXECUTION_AMBIGUOUS", 422, reconciliation=True)
                if result.outcome != Outcome.SUCCESS:
                    raise MGError("CODEX_REJECTED", 422)
                response = {**(result.response or {}), "id": f"chatcmpl-mg-{rid}",
                            "object": "chat.completion", "created": int(time.time()),
                            "model": body.model}
                state.complete(client, digest, response)
                response_headers = {"X-MG-Output-Limit": "upstream-best-effort"}
                if body.stream:
                    return StreamingResponse(sse(response, bool(body.stream_options and
                                             body.stream_options.get("include_usage"))),
                                             media_type="text/event-stream", headers=response_headers)
                return JSONResponse(response, headers=response_headers)
        candidates = select(config, policy, route, required, privacy, context, body.max_tokens,
                            state, body.mg.latency_preference)
        if not candidates:
            raise MGError("NO_ELIGIBLE_FREE_MODEL", 503, retryable=True)
        rid = request.state.request_id
        digest = state.admit(client, policy.requests_per_minute, policy.monthly_request_limit,
                             key or rid, canonical, rid)
        for attempt, candidate in enumerate(candidates[:3], 1):
            # Recheck after selection so a newly disabled provider cannot receive a later fallback.
            if not state.provider_enabled(candidate.provider):
                continue
            state.execution(client, digest, "DISPATCHED")
            try:
                result = await adapter.execute(candidate, payload)
            except BaseException:
                state.execution(client, digest, "AMBIGUOUS")
                raise MGError("EXECUTION_AMBIGUOUS", 502, reconciliation=True) from None
            state.record(candidate.id, result.outcome, result.latency_ms, result.retry_after)
            if policy.log_metadata:
                emit(request_id=rid, client=client, route=body.model, provider=candidate.provider,
                     model=candidate.id, attempt=attempt, result=result.outcome,
                     upstream_model=candidate.model, fallback_count=attempt - 1,
                     candidate_sequence=[m.id for m in candidates[:attempt]],
                     error_category=result.category, latency_ms=result.latency_ms,
                     usage=result.response.get("usage", {}) if result.response else {},
                     cost_estimate_usd=0, cost_class="FREE")
            if result.outcome == Outcome.SUCCESS:
                response = {**(result.response or {}), "id": f"chatcmpl-mg-{rid}",
                            "object": "chat.completion", "created": int(time.time()),
                            "model": body.model}
                state.complete(client, digest, response)
                if body.stream:
                    return StreamingResponse(sse(response, bool(body.stream_options and
                                             body.stream_options.get("include_usage"))),
                                             media_type="text/event-stream")
                return JSONResponse(response)
            if result.outcome == Outcome.EXECUTION_AMBIGUOUS:
                state.execution(client, digest, "AMBIGUOUS")
                raise MGError("EXECUTION_AMBIGUOUS", 502, reconciliation=True)
            if result.outcome == Outcome.FAILED_TERMINAL:
                state.fail(client, digest, "TERMINAL", "UPSTREAM_REJECTED")
                raise MGError("UPSTREAM_REJECTED", 422)
            state.fail(client, digest, "SAFE_FAILURE", result.category or "SAFE_FAILURE")
        state.fail(client, digest, "SAFE_FAILURE", "NO_ELIGIBLE_FREE_MODEL")
        raise MGError("NO_ELIGIBLE_FREE_MODEL", 503, retryable=True)

    return app


async def sse(response: dict[str, Any], include_usage: bool) -> AsyncIterator[str]:
    base = {k: response[k] for k in ("id", "created", "model")}
    base["object"] = "chat.completion.chunk"
    message = response["choices"][0]["message"]
    if message.get("tool_calls"):
        message = {**message, "tool_calls": [{**call, "index": i}
                   for i, call in enumerate(message["tool_calls"])]}
    yield "data: " + json.dumps({**base, "choices": [{"index": 0, "delta": message,
                                                       "finish_reason": None}]}) + "\n\n"
    yield "data: " + json.dumps({**base, "choices": [{"index": 0, "delta": {},
                          "finish_reason": response["choices"][0]["finish_reason"]}]}) + "\n\n"
    if include_usage:
        yield "data: " + json.dumps({**base, "choices": [], "usage": response["usage"]}) + "\n\n"
    yield "data: [DONE]\n\n"
