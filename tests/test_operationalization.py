import asyncio
import hashlib
import json
import time
from datetime import datetime, timezone

import httpx
import pytest

from mg_ai.capacity import Capacity, fingerprint, groq_capacity, openrouter_capacity, refresh_openrouter
from mg_ai.discovery import GROQ_SOURCE, SOURCE, groq_proposal, proposal
from mg_ai.live_benchmark import CASES, THRESHOLDS, eligible, payload, run, score_case, summarize
from mg_ai.model_intelligence import ExternalEvidence, recommendations
from mg_ai.providers import LiteLLMAdapter, Outcome, Result
from mg_ai.proxy_config import render
from mg_ai.routing import select
from mg_ai.state import State
from conftest import headers, payload as gateway_payload


def catalog(model):
    return {"source": SOURCE, "refreshed_at": datetime.now(timezone.utc).isoformat(),
            "candidates": [{"model": model.model, "pricing": {"prompt": "0", "completion": "0"}}]}


def test_capacity_unknown_credit_zero_stale_and_rotation():
    c = openrouter_capacity({"limit_remaining": 0, "is_free_tier": True,
                             "rate_limit": {"requests": 999}}, "secret", 100)
    assert c.remaining_requests is None and c.remaining_tokens is None
    assert c.remaining_credits == 0 and not c.blocks("secret", 101)
    c.remaining_requests = 0
    assert c.blocks("secret", 101)
    assert not c.blocks("rotated", 101) and not c.blocks("secret", 401)
    c.requests_reset_at = 105
    assert not c.blocks("secret", 106)
    c.reliable = False
    assert not c.blocks("secret", 101)


def test_openrouter_capacity_whitelist_and_missing_key_no_call():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"data": {"label": "secret-label", "creator_user_id": "private",
                             "limit_remaining": 12, "is_free_tier": True}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        assert refresh_openrouter("", http).health == "UNKNOWN"
        assert calls == []
        result = refresh_openrouter("secret", http)
    assert result.health == "HEALTHY" and result.remaining_credits == 12
    assert "secret-label" not in result.model_dump_json() and "private" not in result.model_dump_json()


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_capacity_auth_failure_and_unavailable(status):
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(status))) as http:
        c = refresh_openrouter("secret", http)
    assert c.blocks("secret") == (status in {401, 403})


def test_groq_header_units_and_untrusted_evidence():
    h = {"x-ratelimit-remaining-requests": "0", "x-ratelimit-remaining-tokens": "12",
         "x-ratelimit-reset-requests": "2m59.56s", "x-ratelimit-reset-tokens": "7.66s"}
    assert not groq_capacity(h, "key", 100).blocks("key", 101)
    c = groq_capacity(h, "key", 100, verified_direct_response=True)
    assert c.requests_reset_at == pytest.approx(279.56)
    assert c.tokens_reset_at == pytest.approx(107.66)
    assert c.blocks("key", 101) and c.remaining_credits is None
    assert groq_capacity({"x-ratelimit-remaining-tokens": "NaN"}, "key", 1).remaining_tokens is None


def test_capacity_persistence_and_routing(config, tmp_path):
    path = str(tmp_path / "capacity.sqlite")
    state = State(path)
    c = Capacity(provider="openrouter", account="TEST_PROVIDER_KEY", checked_at=time.time(),
                 valid_until=time.time()+300, source=SOURCE, reliable=True, remaining_requests=0,
                 credential_fingerprint=fingerprint("test-upstream-secret"))
    state.save_capacity(c)
    state.db.close()
    state = State(path)
    assert state.capacity("openrouter", "TEST_PROVIDER_KEY") == c
    assert not select(config, config.clients["developer"], config.routes["dev-light"],
                      {"TEXT"}, "INTERNAL", 100, 100, state)
    state.db.close()


def test_discovery_removed_paid_metadata_and_random_rejection(config):
    old = [{"model": "gone:free"}, {"model": "paid:free"}, {"model": "new:free", "context_limit": 10}]
    rows = [{"id": "paid:free", "pricing": {"prompt": "1", "completion": "0"}},
            {"id": "new:free", "context_length": 20, "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "openrouter/free", "pricing": {"prompt": "0", "completion": "0"}}]
    result = proposal(rows, old, config)
    assert result["removed"] == ["gone:free"]
    assert result["no_longer_free"] == ["paid:free"]
    assert result["metadata_changes"][0]["model"] == "new:free"
    assert result["recommendations"][-1]["status"] == "REJECTED"
    assert all(not row["enabled"] for row in result["candidates"])


def test_groq_discovery_and_live_preflight_require_owner_privacy_evidence(config):
    model = config.models[0].model_copy(update={
        "provider": "groq", "model": "openai/gpt-oss-120b",
        "credential_env": "GROQ_API_KEY"
    })
    rows = [{"id": model.model, "active": True, "context_window": 131072,
             "max_completion_tokens": 65536}]
    catalog = groq_proposal(rows, config, owner_confirm_free=True, owner_confirm_zdr=True)
    assert catalog["source"] == GROQ_SOURCE and eligible(model, catalog)
    catalog["global_zdr_confirmed_by_owner"] = False
    assert not eligible(model, catalog)
    config.models = [model]
    params = render(config, {model.id})["model_list"][0]["litellm_params"]
    assert params["model"] == "groq/openai/gpt-oss-120b"
    assert params["api_key"] == "os.environ/GROQ_API_KEY"


def test_privacy_unknown_cannot_approve_confidential(config):
    data = config.models[0].model_dump()
    data["privacy_classes"] = {"CONFIDENTIAL"}
    with pytest.raises(ValueError, match="privacy evidence"):
        type(config.models[0]).model_validate(data)


def test_free_kill_switch_paid_otherwise_qualified_never_dispatches(config, harness):
    config.models[0] = config.models[0].model_copy(update={"cost_class": "PAID"})
    client, calls, _ = harness()
    response = client.post("/v1/chat/completions", headers=headers(), json=gateway_payload())
    assert response.status_code == 503 and response.json()["error"]["code"] == "NO_ELIGIBLE_FREE_MODEL"
    assert len(calls) == 0  # Paid request count and resulting spend are both zero.


def test_disabled_champion_safe_fallback(config, harness):
    config.models.append(config.models[0].model_copy(update={"id": "fallback"}))
    config.routes["dev-light"].champion = "free-a"
    config.models[0].enabled = False
    client, calls, _ = harness()
    assert client.post("/v1/chat/completions", headers=headers(), json=gateway_payload()).status_code == 200
    assert [json.loads(c.content)["model"] for c in calls] == ["fallback"]


def test_live_preflight_prices_expiry_and_pinned_model(config):
    m = config.models[0].model_copy(update={"credential_env": "OPENROUTER_API_KEY"})
    c = catalog(m)
    assert eligible(m, c), {"provider": m.provider, "cost": m.cost_class,
        "model": m.model, "random": m.random_router, "api_base": m.api_base,
        "credential": m.credential_env, "catalog": c}
    assert not eligible(m.model_copy(update={"cost_class": "PAID"}), c)
    assert not eligible(m.model_copy(update={"api_base": "https://other.invalid"}), c)
    c["refreshed_at"] = "2020-01-01T00:00:00+00:00"
    assert not eligible(m, c)


def test_synthetic_scoring_rejects_faithfulness_failure_and_bad_json():
    case = json.loads(CASES.read_text(encoding="utf-8"))[0]
    answer = {**case["expected"], "title": "آموزش ساختگی", "days": 99}
    r = Result(Outcome.SUCCESS, {"choices": [{"message": {"content": json.dumps(answer)}}]})
    scores = score_case(case, r)
    assert scores["persian_script"] == 1 and scores["faithfulness"] < 1
    limits = json.loads(THRESHOLDS.read_text())
    assert not summarize([{"route": "life-study", "scores": scores}], limits)["life-study"]["thresholds_pass"]
    assert score_case(case, Result(Outcome.SUCCESS, {"choices": []}))["structured_output"] == 0


def test_live_runner_missing_key_no_inference(config, monkeypatch, tmp_path):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    m = config.models[0].model_copy(update={"credential_env": "OPENROUTER_API_KEY"})
    calls = []
    async def check():
        adapter = LiteLLMAdapter("http://proxy", "master", httpx.MockTransport(lambda r: calls.append(r)))
        state = State(str(tmp_path / "s.sqlite"))
        report = await run(m, catalog(m), adapter, state, "blocked", tmp_path / "blocked.json", approved_by="test")
        await adapter.http.aclose()
        state.db.close()
        return report
    assert asyncio.run(check())["status"] == "BLOCKED" and calls == []


def test_live_runner_real_adapter_mock_transport_success_and_no_replay(config, monkeypatch, tmp_path):
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-key")
    m = config.models[0].model_copy(update={"credential_env": "OPENROUTER_API_KEY"})
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    calls = []
    def handler(request):
        case = cases[len(calls)]
        calls.append(request)
        answer = dict(case["expected"])
        if case.get("persian_field"):
            answer[case["persian_field"]] = "متن فارسی ساختگی"
        message = {"role": "assistant", "content": json.dumps(answer)}
        if case.get("tool"):
            message["tool_calls"] = [{"id": "call-1", "type": "function", "function": {
                "name": "propose_edit", "arguments": json.dumps(answer)}}]
        return httpx.Response(200, json={"choices": [{"message": message, "finish_reason": "stop"}]})
    async def check():
        adapter = LiteLLMAdapter("http://proxy", "master", httpx.MockTransport(handler))
        state = State(str(tmp_path / "s.sqlite"))
        report = await run(m, catalog(m), adapter, state, "run-1", tmp_path / "success.json", approved_by="test")
        with pytest.raises(ValueError, match="already recorded"):
            await run(m, catalog(m), adapter, state, "run-1", tmp_path / "replay.json", approved_by="test")
        await adapter.http.aclose()
        state.db.close()
        return report
    report = asyncio.run(check())
    assert report["status"] == "COMPLETED" and len(calls) == 5
    assert all(r["thresholds_pass"] for r in report["routes"].values())
    assert report["verified_capabilities"] == [] and report["automatic_promotion"] is False
    assert "متن فارسی ساختگی" not in (tmp_path / "success.json").read_text(encoding="utf-8")


@pytest.mark.parametrize("status,expected", [(500,"RECONCILIATION_REQUIRED"), (429,"RECONCILIATION_REQUIRED"), (200,"RECONCILIATION_REQUIRED")])
def test_live_runner_stops_without_fallback_on_failure(config, monkeypatch, tmp_path, status, expected):
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-key")
    m = config.models[0].model_copy(update={"credential_env": "OPENROUTER_API_KEY"})
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"malformed": True})
    async def check():
        adapter = LiteLLMAdapter("http://proxy", "master", httpx.MockTransport(handler))
        state = State(str(tmp_path / "s.sqlite"))
        report = await run(m, catalog(m), adapter, state, "uncertain", tmp_path / "r.json", approved_by="test")
        await adapter.http.aclose()
        state.db.close()
        return report
    assert asyncio.run(check())["status"] == expected and len(calls) == 1


def test_external_rankings_are_not_champion_authority():
    evidence = ExternalEvidence(model="model:free", source="LiveBench", reference="https://livebench.ai/",
                                observed_at=datetime.now(timezone.utc), metric="score", value=99)
    assert evidence.value == 99
    result = recommendations([], hashlib.sha256(CASES.read_bytes()).hexdigest(), json.loads(THRESHOLDS.read_text()))
    assert all(v["status"] == "BLOCKED" and v["recommended_champion"] is None for v in result.values())
    assert payload(json.loads(CASES.read_text(encoding="utf-8"))[1])["max_tokens"] == 512
