"""Admin service: readiness computation over the registry and provider control."""
from typing import Any

from mg_ai.config.models import Configuration
from mg_ai.database.gateway_repository import GatewayRepository
from mg_ai.programmer import ProgrammerAdapter
from mg_ai.routing import select


class AdminService:
    def __init__(self, config: Configuration, state: GatewayRepository,
                 programmer: ProgrammerAdapter | None) -> None:
        self.config = config
        self.state = state
        self.programmer = programmer

    def ready(self, client: str) -> dict[str, Any]:
        self.state.db.execute("SELECT 1")
        config, policy = self.config, self.config.clients[client]
        eligible = {name: len(select(config, policy, config.routes[name],
                                     config.routes[name].capabilities, policy.default_privacy,
                                     0, 1024, self.state)) for name in sorted(policy.routes)}
        for name in policy.routes:
            if config.routes[name].backend == "CODEX":
                eligible[name] = int(bool(self.programmer and self.programmer.configured
                                          and self.state.provider_enabled("omniroute")))
        return {"status": "ready" if any(eligible.values()) else "configured_no_eligible_provider",
                "client": client, "paid_inference": False, "eligible_routes": eligible}
