import time
import os

from mg_ai.config import Candidate, Client, Configuration, Privacy, Route
from mg_ai.state import State

TIERS = {"LIGHT": 0, "WORKHORSE": 1, "FRONTIER": 2}


def select(config: Configuration, policy: Client, route: Route, required: set[str],
           privacy: Privacy, context: int, output: int, state: State,
           latency_preference: str = "quality") -> list[Candidate]:
    candidates: list[Candidate] = []
    if route.backend != "FREE":
        return candidates
    for model in config.models:
        if not route.allow_fallbacks and model.id != route.champion:
            continue
        if not state.provider_enabled(model.provider):
            continue
        if not model.available() or model.cost_class != "FREE":
            continue
        if model.random_router and not route.allow_random:
            continue
        if model.role == "champion" and route.champion != model.id:
            continue
        if policy.model_allowlist is not None and model.id not in policy.model_allowlist:
            continue
        if not required <= model.capabilities or privacy not in model.privacy_classes:
            continue
        if context + output > model.context_limit or output > model.max_output_tokens:
            continue
        if TIERS[model.quality_tier] < TIERS[route.intent]:
            continue
        if model.benchmark_scores.get(route.task, 0) < route.min_quality:
            continue
        if state.health(model.id)["cooldown"] > time.time():
            continue
        capacity = state.capacity(model.provider, model.credential_env)
        if capacity and capacity.blocks(os.getenv(model.credential_env, "")):
            continue
        candidates.append(model)
    return sorted(candidates, key=lambda m: (
        m.id != route.champion,
        -m.benchmark_scores.get(route.task, 0),
        state.health(m.id)["status"] != "HEALTHY",
        -(m.quota_remaining if m.quota_remaining is not None else 0),
        (state.health(m.id)["latency_ms"] or m.latency_ms)
        if latency_preference == "fast" else m.failure_rate,
        m.latency_ms, m.id,
    ))
