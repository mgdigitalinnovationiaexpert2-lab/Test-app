"""Chat service: policy checks, routing selection, admission and fallback execution."""
import hashlib
import hmac
import json
import os
import re
import time
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from mg_ai.common.errors import MGError
from mg_ai.config.constants import PRIVACY_LEVEL
from mg_ai.config.models import Configuration
from mg_ai.database.gateway_repository import GatewayRepository
from mg_ai.modules.chat.dto.chat import ChatRequest
from mg_ai.observability import emit
from mg_ai.programmer import (CODEX_CAPABILITIES, CODEX_CONTEXT_BYTES, CODEX_MODEL,
                              ProgrammerAdapter, responses_payload)
from mg_ai.providers import LiteLLMAdapter, Outcome
from mg_ai.routing import select

IDEMPOTENCY_PATTERN = re.compile(r"[A-Za-z0-9_.:-]{1,128}")


class ChatService:
    def __init__(self, config: Configuration, state: GatewayRepository,
                 adapter: LiteLLMAdapter, programmer: ProgrammerAdapter | None,
                 token_hashes: list[tuple[str, bytes]]) -> None:
        self.config = config
        self.state = state
        self.adapter = adapter
        self.programmer = programmer
        self.token_hashes = token_hashes

    # ------------------------------------------------------------------ auth
    def authenticate(self, request: Request) -> str:
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer ") or len(auth) > 512:
            raise MGError("UNAUTHENTICATED", 401)
        digest = hashlib.sha256(auth[7:].encode()).digest()
        found = None
        for name, stored in self.token_hashes:
            if hmac.compare_digest(digest, stored):
                found = name
        if found is None:
            raise MGError("UNAUTHENTICATED", 401)
        return found

    # ------------------------------------------------------------- registry
    def models(self, client: str) -> dict[str, Any]:
        return {"object": "list", "data": [{"id": route, "object": "model", "owned_by": "maghsoud",
                                            "created": 0}
                                           for route in sorted(self.config.clients[client].routes)]}

    # ------------------------------------------------------------ chat flow
    @staticmethod
    def parse(raw: bytes) -> ChatRequest:
        try:
            return ChatRequest.model_validate_json(raw)
        except ValueError:
            raise MGError("INVALID_REQUEST") from None

    def authorize(self, client: str, body: ChatRequest) -> tuple[Any, Any, set[str], int]:
        """Validate the request against client policy; returns route/privacy/capabilities/context."""
        policy = self.config.clients[client]
        if body.model not in policy.routes:
            raise MGError("ROUTE_FORBIDDEN", 403)
        route = self.config.routes[body.model]
        privacy = body.mg.privacy_class or policy.default_privacy
        if PRIVACY_LEVEL[privacy] < PRIVACY_LEVEL[policy.default_privacy]:
            raise MGError("PRIVACY_DOWNGRADE_FORBIDDEN", 403)
        required = body.capabilities() | route.capabilities
        if privacy not in policy.privacy_classes or not required <= policy.allowed_capabilities:
            raise MGError("CAPABILITY_OR_PRIVACY_FORBIDDEN", 403)
        payload = body.model_dump(mode="json", exclude={"mg", "stream_options"}, exclude_none=True)
        # UTF-8 bytes provide a conservative text token bound, including tools/schema framing.
        context = max(body.mg.context_tokens, len(json.dumps(payload, ensure_ascii=False).encode()))
        return route, privacy, required, context

    @staticmethod
    def canonical(body: ChatRequest) -> bytes:
        canonical_data = body.model_dump(mode="json")
        canonical_data["mg"]["required_capabilities"] = sorted(body.mg.required_capabilities)
        return json.dumps(canonical_data, sort_keys=True).encode()

    async def completions(self, request: Request, client: str, body: ChatRequest) -> Response:
        key = request.headers.get("idempotency-key")
        if key and not IDEMPOTENCY_PATTERN.fullmatch(key):
            raise MGError("INVALID_IDEMPOTENCY_KEY")
        canonical = self.canonical(body)
        if key:
            # Duplicate safety must not depend on current model availability or cooldown.
            self.state.check_duplicate(client, key, canonical)
        route, privacy, required, context = self.authorize(client, body)
        payload = body.model_dump(mode="json", exclude={"mg", "stream_options"}, exclude_none=True)
        if route.backend == "CODEX":
            return await self._codex(request, client, body, privacy, required, context,
                                     payload, key, canonical)
        candidates = select(self.config, self.config.clients[client], route, required, privacy,
                            context, body.max_tokens, self.state, body.mg.latency_preference)
        if not candidates:
            raise MGError("NO_ELIGIBLE_FREE_MODEL", 503, retryable=True)
        rid = request.state.request_id
        digest = self.state.admit(client, self.config.clients[client].requests_per_minute,
                                  self.config.clients[client].monthly_request_limit,
                                  key or rid, canonical, rid)
        for attempt, candidate in enumerate(candidates[:3], 1):
            # Recheck after selection so a newly disabled provider cannot receive a later fallback.
            if not self.state.provider_enabled(candidate.provider):
                continue
            self.state.execution(client, digest, "DISPATCHED")
            try:
                result = await self.adapter.execute(candidate, payload)
            except BaseException:
                self.state.execution(client, digest, "AMBIGUOUS")
                raise MGError("EXECUTION_AMBIGUOUS", 502, reconciliation=True) from None
            self.state.record(candidate.id, result.outcome, result.latency_ms, result.retry_after)
            policy = self.config.clients[client]
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
                self.state.complete(client, digest, response)
                if body.stream:
                    return StreamingResponse(sse(response, bool(body.stream_options and
                                             body.stream_options.get("include_usage"))),
                                             media_type="text/event-stream")
                return JSONResponse(response)
            if result.outcome == Outcome.EXECUTION_AMBIGUOUS:
                self.state.execution(client, digest, "AMBIGUOUS")
                raise MGError("EXECUTION_AMBIGUOUS", 502, reconciliation=True)
            if result.outcome == Outcome.FAILED_TERMINAL:
                self.state.fail(client, digest, "TERMINAL", "UPSTREAM_REJECTED")
                raise MGError("UPSTREAM_REJECTED", 422)
            self.state.fail(client, digest, "SAFE_FAILURE", result.category or "SAFE_FAILURE")
        self.state.fail(client, digest, "SAFE_FAILURE", "NO_ELIGIBLE_FREE_MODEL")
        raise MGError("NO_ELIGIBLE_FREE_MODEL", 503, retryable=True)

    async def _codex(self, request: Request, client: str, body: ChatRequest,
                     privacy: str, required: set[str], context: int,
                     payload: dict[str, Any], key: str | None, canonical: bytes) -> Response:
        """Subscription-backed CODEX path through the private programmer adapter."""
        policy = self.config.clients[client]
        programmer = self.programmer
        state = self.state
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


async def sse(response: dict[str, Any], include_usage: bool) -> Any:
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


def build_token_hashes(config: Configuration) -> list[tuple[str, bytes]]:
    """Hash every configured client token once at startup (constant-time compare later)."""
    token_hashes: list[tuple[str, bytes]] = []
    seen_hashes: set[bytes] = set()
    for client, policy in config.clients.items():
        env_names = [policy.token_env, *sorted(policy.additional_token_envs)]
        for index, env_name in enumerate(env_names):
            token = os.getenv(env_name, "")
            if index > 0 and not token:
                continue
            if len(token) < 32:
                raise ValueError(f"Configure a strong token for {client}")
            digest = hashlib.sha256(token.encode()).digest()
            if digest in seen_hashes:
                raise ValueError("client tokens must be distinct")
            seen_hashes.add(digest)
            token_hashes.append((client, digest))
    return token_hashes
