import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Capability = str
Intent = Literal["LIGHT", "WORKHORSE", "FRONTIER"]
Privacy = Literal["PUBLIC", "INTERNAL", "CONFIDENTIAL"]
PRIVACY_LEVEL = {"PUBLIC": 0, "INTERNAL": 1, "CONFIDENTIAL": 2}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Retry429Review(StrictModel):
    adapter: Literal["LiteLLMAdapter"]
    provider: str
    model: str
    semantics: Literal["REJECTED_BEFORE_EXECUTION"]
    evidence: str = Field(min_length=1)
    reviewed_by: str = Field(min_length=1)
    valid_until: datetime

    @model_validator(mode="after")
    def dated(self) -> Self:
        if self.valid_until.tzinfo is None:
            raise ValueError("429 review expiry must include timezone")
        return self


class Candidate(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    provider: Literal["openrouter", "groq", "nvidia", "openai-compatible", "direct", "omniroute"]
    model: str
    enabled: bool = False
    approved: bool = False
    cost_class: Literal["FREE", "PAID"] = "FREE"
    cost_tier: str = "zero"
    quality_tier: Intent = "LIGHT"
    capabilities: set[Capability] = Field(default_factory=lambda: {"TEXT"})
    context_limit: int = Field(gt=0)
    max_output_tokens: int = Field(default=4096, gt=0)
    credential_env: str = Field(pattern=r"^[A-Z][A-Z0-9_]+$")
    api_base: str | None = None
    privacy_classes: set[Privacy] = {"PUBLIC"}
    data_policy_url: str | None = None
    data_policy_reviewed: bool = False
    retention_known: bool = False
    training_use_known: bool = False
    confidential_allowed: bool = False
    free_verified_until: datetime | None = None
    free_evidence: str | None = None
    promotional: bool = False
    random_router: bool = False
    health: Literal["HEALTHY", "DEGRADED", "RATE_LIMITED", "UNAVAILABLE", "DISABLED"] = "DISABLED"
    latency_ms: float = Field(default=0, ge=0)
    failure_rate: float = Field(default=0, ge=0, le=1)
    quota_remaining: int | None = Field(default=None, ge=0)
    benchmark_scores: dict[str, float] = Field(default_factory=dict)
    coding_suitability: str = "unreviewed"
    reasoning_suitability: str = "unreviewed"
    persian_suitability: str = "unreviewed"
    role: Literal["champion", "challenger", "candidate"] = "candidate"
    idempotency_guaranteed: Literal[False] = False
    retry_429_review: Retry429Review | None = None

    @model_validator(mode="after")
    def safety(self) -> Self:
        if self.retry_429_review and (self.retry_429_review.provider != self.provider
                                      or self.retry_429_review.model != self.model):
            raise ValueError("429 review must match provider and upstream model")
        if self.model == "openrouter/free" and not self.random_router:
            raise ValueError("random router must be explicitly identified")
        if self.free_verified_until and self.free_verified_until.tzinfo is None:
            raise ValueError("free verification expiry must include timezone")
        if self.enabled:
            if "CONFIDENTIAL" in self.privacy_classes and not (
                self.confidential_allowed and self.retention_known and self.training_use_known
            ):
                raise ValueError("confidential workloads require explicit privacy evidence")
            if self.provider == "omniroute":
                raise ValueError("OmniRoute is reserved, not enabled")
            if not self.approved or not self.data_policy_reviewed:
                raise ValueError("enabled models require approval and privacy review")
            if self.cost_class != "FREE":
                raise ValueError("paid execution requires a future audited spend ledger")
            if not self.free_evidence or not self.free_verified_until:
                raise ValueError("free status requires evidence and expiry")
            if self.provider == "openrouter" and not (
                self.model.endswith(":free") or self.model == "openrouter/free"
            ):
                raise ValueError("OpenRouter free execution requires an explicit free identifier")
        if any(not 0 <= score <= 1 for score in self.benchmark_scores.values()):
            raise ValueError("benchmark scores must be normalized to [0,1]")
        return self

    def available(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        return bool(self.enabled and self.approved and os.getenv(self.credential_env)
                    and self.cost_class == "FREE" and self.free_verified_until
                    and self.free_verified_until > now and self.quota_remaining != 0
                    and self.health not in {"DISABLED", "UNAVAILABLE", "RATE_LIMITED"})


class Route(StrictModel):
    backend: Literal["FREE", "CODEX"] = "FREE"
    allow_fallbacks: bool = True
    intent: Intent
    capabilities: set[Capability]
    task: str
    min_quality: float = Field(default=0.6, ge=0, le=1)
    champion: str | None = None
    allow_random: bool = False


class Client(StrictModel):
    token_env: str
    routes: set[str]
    paid_allowed: Literal[False] = False
    monthly_budget_usd: Literal[0] = 0
    requests_per_minute: int = Field(gt=0)
    monthly_request_limit: int | None = Field(default=None, gt=0)
    model_allowlist: set[str] | None = None
    allowed_capabilities: set[Capability]
    privacy_classes: set[Privacy]
    default_privacy: Privacy
    log_metadata: bool = True
    log_content: Literal[False] = False


class Configuration(StrictModel):
    models: list[Candidate]
    routes: dict[str, Route]
    clients: dict[str, Client]

    @model_validator(mode="after")
    def references(self) -> Self:
        ids = [m.id for m in self.models]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate model id")
        if set(self.clients) != {"portal", "life-os", "developer"}:
            raise ValueError("all three clients must be configured")
        for client in self.clients.values():
            if not client.routes <= self.routes.keys():
                raise ValueError("unknown client route")
            if client.default_privacy not in client.privacy_classes:
                raise ValueError("invalid default privacy")
            if client.model_allowlist and not client.model_allowlist <= set(ids):
                raise ValueError("unknown model allowlist entry")
        for route in self.routes.values():
            if route.champion and route.champion not in ids:
                raise ValueError("unknown champion")
            if any(m.id == route.champion and (m.random_router or m.model == "openrouter/free")
                   for m in self.models):
                raise ValueError("random router cannot be Champion")
        for name, route in self.routes.items():
            if route.backend == "CODEX" and (name != "dev-code" or route.champion is not None):
                raise ValueError("Codex is reserved for the dedicated dev-code route")
        if any(self.routes[name].backend == "CODEX"
               for client, policy in self.clients.items() if client != "developer"
               for name in policy.routes):
            raise ValueError("Codex route is programmer-only")
        return self


def load_config(root: Path = Path(".")) -> Configuration:
    return Configuration(models=json.loads((root / "model-registry/models.json").read_text()),
                         routes=json.loads((root / "routing/routes.json").read_text()),
                         clients=json.loads((root / "policies/clients.json").read_text()))
