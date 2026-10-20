"""Executions controller: internal reconciliation endpoint."""
from typing import Any

from fastapi import APIRouter, Request

from mg_ai.modules.executions.dto.executions import ReconciliationRequest

router = APIRouter()

# Injected once by the gateway composition root via configure().
_service = None
_authenticator = None


def configure(service, chat_service) -> None:
    """Inject the ExecutionsService and the shared authenticator."""
    global _service, _authenticator
    _service = service
    _authenticator = chat_service.authenticate


@router.post("/internal/executions/reconcile")
async def reconcile_execution(request: Request, body: ReconciliationRequest) -> dict[str, Any]:
    client = _authenticator(request)
    return _service.reconcile(client, body.idempotency_key)
