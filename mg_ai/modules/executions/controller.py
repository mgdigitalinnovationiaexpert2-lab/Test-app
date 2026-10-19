"""Executions controller: internal reconciliation endpoint."""
from typing import Any

from fastapi import APIRouter, Request

from mg_ai.modules.executions.dto.executions import ReconciliationRequest

router = APIRouter()


def configure(service, chat_service) -> None:
    """Inject the ExecutionsService and the shared authenticator."""
    router.state.service = service
    router.state.authenticator = chat_service.authenticate


@router.post("/internal/executions/reconcile")
async def reconcile_execution(request: Request, body: ReconciliationRequest) -> dict[str, Any]:
    client = router.state.authenticator(request)
    return router.state.service.reconcile(client, body.idempotency_key)
