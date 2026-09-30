from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from mg_ai.config import Candidate, Client, Configuration
from mg_ai.errors import MGError
from mg_ai.proxy_config import render
from mg_ai.routing import select
from mg_ai.state import State
from mg_ai.gateway import create_app


@pytest.mark.parametrize("updates", [{"approved": False}, {"data_policy_reviewed": False},
                                     {"cost_class": "PAID"}, {"free_evidence": None},
                                     {"free_verified_until": None}, {"model": "paid/model"},
                                     {"provider": "omniroute"}, {"unknown": 1}])
def test_invalid_enabled_registry(config, updates):
    with pytest.raises(ValidationError):
        Candidate.model_validate({**config.models[0].model_dump(), **updates})


def test_duplicate_registry_and_paid_policy(config):
    with pytest.raises(ValidationError):
        Configuration.model_validate({**config.model_dump(), "models": config.models * 2})
    with pytest.raises(ValidationError):
        Client.model_validate({**config.clients["developer"].model_dump(), "paid_allowed": True})


@pytest.mark.parametrize("updates", [{"capabilities": {"TEXT"}}, {"context_limit": 10},
                                     {"privacy_classes": {"PUBLIC"}}, {"cost_class": "PAID"},
                                     {"benchmark_scores": {}}, {"approved": False},
                                     {"quota_remaining": 0}, {"random_router": True},
                                     {"health": "DISABLED"}, {"quality_tier": "LIGHT"}])
def test_eligibility(config, tmp_path, updates):
    config.models[0] = config.models[0].model_copy(update=updates)
    state = State(str(tmp_path / "state.sqlite"))
    assert not select(config, config.clients["developer"], config.routes["dev-code"],
                      {"CODING", "TOOL_CALLING"}, "INTERNAL", 100, 1024, state)
    state.db.close()


def test_expired_free_status(config):
    config.models[0].free_verified_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert not config.models[0].available()


def test_ranking_and_allowlist(config, tmp_path):
    config.models.append(config.models[0].model_copy(update={"id": "free-b", "benchmark_scores": {"GENERAL": .95}}))
    state = State(str(tmp_path / "state.sqlite"))
    args = (config, config.clients["developer"], config.routes["dev-light"], {"TEXT"}, "INTERNAL", 100, 100, state)
    assert select(*args)[0].id == "free-b"
    config.clients["developer"].model_allowlist = {"free-a"}
    assert [m.id for m in select(*args)] == ["free-a"]
    state.db.close()


def test_champion_precedes_higher_raw_score(config, tmp_path):
    config.routes["dev-light"].champion = "free-a"
    config.models.append(config.models[0].model_copy(update={
        "id": "free-b", "benchmark_scores": {"GENERAL": 1.0}
    }))
    state = State(str(tmp_path / "state.sqlite"))
    selected = select(config, config.clients["developer"], config.routes["dev-light"],
                      {"TEXT"}, "INTERNAL", 100, 100, state)
    assert [model.id for model in selected] == ["free-a", "free-b"]
    state.db.close()


def test_champion_is_scoped_to_named_routes(config, tmp_path):
    config.models[0].role = "champion"
    config.routes["dev-code"].champion = "free-a"
    state = State(str(tmp_path / "state.sqlite"))
    assert select(config, config.clients["developer"], config.routes["dev-code"],
                  {"CODING", "TOOL_CALLING"}, "INTERNAL", 100, 100, state)
    assert not select(config, config.clients["developer"], config.routes["dev-light"],
                      {"TEXT"}, "INTERNAL", 100, 100, state)
    state.db.close()


def test_proxy_retries_and_secret_references(config):
    proxy = render(config)
    assert proxy["router_settings"]["fallbacks"] == []
    assert proxy["router_settings"]["num_retries"] == 0
    params = proxy["model_list"][0]["litellm_params"]
    assert params["num_retries"] == 0
    assert params["api_key"] == "os.environ/TEST_PROVIDER_KEY"
    assert params["extra_body"]["provider"]["allow_fallbacks"] is False


def test_restart_journal_budget_and_stale_cooldown(tmp_path):
    path = str(tmp_path / "state.sqlite")
    state = State(path)
    digest = state.admit("portal", 100, 1, "key", b"body", "rid")
    state.execution("portal", digest, "DISPATCHED")
    state.record("model", "RATE_LIMITED_SAFE", 12, 60)
    state.db.close()
    state = State(path)
    with pytest.raises(MGError) as error:
        state.admit("portal", 100, 1, "key", b"body", "new")
    assert error.value.reconciliation
    with pytest.raises(MGError) as error:
        state.admit("portal", 100, 1, "new-key", b"body", "new")
    assert error.value.code == "REQUEST_BUDGET_EXHAUSTED"
    assert state.health("model")["status"] == "RATE_LIMITED"
    state.db.close()


def test_missing_and_duplicate_client_tokens(config, tmp_path, monkeypatch):
    state = State(str(tmp_path / "tokens.sqlite"))
    monkeypatch.delenv("MG_DEV_TOKEN")
    with pytest.raises(ValueError, match="strong token"):
        create_app(config, state)
    monkeypatch.setenv("MG_DEV_TOKEN", "same" * 12)
    monkeypatch.setenv("MG_PORTAL_TOKEN", "same" * 12)
    with pytest.raises(ValueError, match="distinct"):
        create_app(config, state)
    state.db.close()


def test_atomic_monthly_admission(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    path = str(tmp_path / "concurrency.sqlite")
    State(path).db.close()

    def admit(i):
        state = State(path)
        try:
            state.admit("client", 100, 1, str(i), b"body", str(i))
            return True
        except MGError:
            return False
        finally:
            state.db.close()

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(admit, range(8))) == 1
