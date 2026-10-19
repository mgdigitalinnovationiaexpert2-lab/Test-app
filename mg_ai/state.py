"""Compatibility alias; the gateway journal lives in mg_ai.database."""
from mg_ai.database.gateway_repository import GatewayRepository

State = GatewayRepository
__all__ = ["GatewayRepository", "State"]
