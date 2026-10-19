"""DEEP controller: private HTTP boundary for executions and staged attachments."""
import hashlib
import hmac
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from mg_ai.common.errors import MGError
from mg_ai.modules.deep.dto.deep import (
    DEEP_ATTACHMENT_LIMIT,
    DeepRequest,
    DeepResponse,
    attachment_metadata_from_headers,
)

router = APIRouter()

# Injected once by the DEEP composition root via configure().
_service = None
_token_digest = None


def configure(service, token: str | None) -> None:
    """Inject the DeepService and the raw client token (validated at request time)."""
    global _service, _token_digest
    _service = service
    _token_digest = (hashlib.sha256(token.encode()).digest()
                     if token and len(token) >= 32 else None)


def authenticate(request: Request) -> None:
    if _token_digest is None or len(_token_digest) != 32 or not auth.startswith("Bearer ") \
            or len(auth) > 512 or not hmac.compare_digest(
                hashlib.sha256(auth[7:].encode()).digest(), _token_digest):
        raise MGError("UNAUTHENTICATED", 401)


@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/health/ready")
async def ready(request: Request) -> dict[str, Any]:
    authenticate(request)
    return router.state.service.readiness()


@router.put("/internal/deep/executions/{execution_id}/attachments/{index}")
async def stage_attachment(request: Request, execution_id: UUID, index: int) -> dict[str, Any]:
    authenticate(request)
    if index < 0 or index >= DEEP_ATTACHMENT_LIMIT:
        raise MGError("DEEP_ATTACHMENT_LIMIT_EXCEEDED", 400)
    data = await request.body()
    try:
        metadata = attachment_metadata_from_headers(index, request.headers, data)
    except (KeyError, ValueError, ValidationError):
        raise MGError("DEEP_ATTACHMENT_METADATA_INVALID", 400) from None
    return router.state.service.stage_attachment(str(execution_id), index, metadata, data)


@router.delete("/internal/deep/executions/{execution_id}/attachments")
async def clear_attachments(request: Request, execution_id: UUID) -> dict[str, str]:
    authenticate(request)
    router.state.service.remove_staged_attachments(str(execution_id))
    return {"status": "REMOVED"}


@router.post("/internal/deep/execute", response_model=DeepResponse)
async def execute(request: Request, body: DeepRequest) -> DeepResponse:
    authenticate(request)
    request.state.execution_id = str(body.execution_id)
    request.state.task_id = str(body.task_id)
    request.state.conversation_id = str(body.conversation_id)
    request.state.attempt = body.attempt
    text, evidence = await router.state.service.execute(request.state.request_id, body)
    return DeepResponse(
        execution_id=body.execution_id, task_id=body.task_id,
        conversation_id=body.conversation_id, request_id=request.state.request_id,
        attempt=body.attempt, answer=text,
        created_at=datetime.fromtimestamp(evidence["created"], UTC),
        completed_at=datetime.fromtimestamp(evidence["updated"], UTC),
    )


def error_response(request: Request, exc: MGError) -> JSONResponse:
    """Shared exception-handler body: attach execution evidence when known."""
    service = router.state.service
    body = exc.body(request.state.request_id)
    execution_id = getattr(request.state, "execution_id", None)
    if execution_id:
        evidence = service.state.evidence(execution_id)
        body["execution"] = {
            "execution_id": execution_id,
            "task_id": evidence.get("task_id", getattr(request.state, "task_id", None)),
            "conversation_id": evidence.get(
                "conversation_id", getattr(request.state, "conversation_id", None)),
            "attempt": evidence.get("attempt", getattr(request.state, "attempt", 0)),
            "status": evidence.get("status", "NOT_DISPATCHED"),
        }
    return JSONResponse(body, status_code=exc.status)
