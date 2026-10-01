import os
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from mg_ai.config import Candidate, load_config
from mg_ai.gateway import create_app
from mg_ai.providers import LiteLLMAdapter
from mg_ai.state import State


@pytest.fixture
def config(monkeypatch):
    config = load_config()
    # Gateway contract tests exercise the FREE adapter regardless of the
    # production backend selected for each logical route.
    for route in config.routes.values():
        route.backend = "FREE"
        route.allow_fallbacks = True
    for name, policy in config.clients.items():
        monkeypatch.setenv(policy.token_env, "test-" + name + "x" * 40)
    monkeypatch.setenv("LITELLM_MASTER_KEY", "test-master-" + "m" * 40)
    monkeypatch.setenv("TEST_PROVIDER_KEY", "test-upstream-secret")
    config.models = [Candidate(
        id="free-a", provider="openrouter", model="test/model:free", enabled=True,
        approved=True, context_limit=200000, max_output_tokens=32768,
        credential_env="TEST_PROVIDER_KEY", data_policy_reviewed=True,
        free_verified_until=datetime.now(timezone.utc) + timedelta(days=1),
        free_evidence="synthetic test only", quality_tier="FRONTIER",
        capabilities=config.clients["developer"].allowed_capabilities,
        privacy_classes={"PUBLIC", "INTERNAL"}, health="HEALTHY",
        benchmark_scores={r.task: .9 for r in config.routes.values()},
    )]
    return config


@pytest.fixture
def success():
    return {"choices": [{"index": 0, "message": {"role": "assistant", "content": "4"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11}}


@pytest.fixture
def harness(config, tmp_path, success):
    opened = []

    def make(handler=None):
        calls = []

        def wrapped(request):
            calls.append(request)
            return handler(request) if handler else httpx.Response(200, json=success)

        adapter = LiteLLMAdapter("http://proxy", "test-master", httpx.MockTransport(wrapped))
        state = State(str(tmp_path / f"state-{len(opened)}.sqlite"))
        client = TestClient(create_app(config, state, adapter), raise_server_exceptions=False)
        opened.append((client, state))
        return client, calls, state

    yield make
    for client, state in opened:
        client.close()
        state.db.close()


def headers(client="developer", key=None):
    name = {"developer": "MG_DEV_TOKEN", "portal": "MG_PORTAL_TOKEN", "life-os": "MG_LIFE_OS_TOKEN"}
    result = {"Authorization": "Bearer " + os.environ[name[client]]}
    if key:
        result["Idempotency-Key"] = key
    return result


def payload(model="dev-light", **kwargs):
    return {"model": model, "messages": [{"role": "user", "content": "2+2?"}], **kwargs}
