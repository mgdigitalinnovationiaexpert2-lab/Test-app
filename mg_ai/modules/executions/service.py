"""Executions service: journal lookup for ambiguous or lost executions."""
from typing import Any

from mg_ai.database.gateway_repository import GatewayRepository


class ExecutionsService:
    def __init__(self, state: GatewayRepository) -> None:
        self.state = state

    def reconcile(self, client: str, idempotency_key: str) -> dict[str, Any]:
        return self.state.reconcile(client, idempotency_key)
