import json
import logging

import httpx
import pytest

from conftest import headers, payload


def test_authentication_and_no_key_exposure(harness):
    client, calls, _ = harness()
    for auth in ({}, {"Authorization": "Bearer invalid"}):
        response = client.post("/v1/chat/completions", headers=auth, json=payload())
        assert response.status_code == 401
        assert "test-upstream-secret" not in response.text
    assert not calls
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 401


@pytest.mark.parametrize("client_name,route", [("life-os", "dev-code"),
                                                ("developer", "portal-normal"),
                                                ("portal", "life-study")])
def test_isolation(harness, client_name, route):
    client, calls, _ = harness()
    assert client.post("/v1/chat/completions", headers=headers(client_name),
                       json=payload(route)).status_code == 403
    models = client.get("/v1/models", headers=headers(client_name)).json()["data"]
    assert route not in {m["id"] for m in models}
    assert not calls


def test_success_metadata_and_sanitization(harness, caplog, success):
    success.update(model="provider-secret-name", api_key="test-upstream-secret")
    client, calls, _ = harness(lambda _: httpx.Response(200, json=success))
    with caplog.at_level(logging.INFO, logger="mg.audit"):
        response = client.post("/v1/chat/completions", headers=headers(key="execution-1"),
                               json=payload())
    assert response.status_code == 200
    assert response.json()["model"] == "dev-light"
    assert response.headers["x-request-id"] in response.json()["id"]
    assert "api_key" not in response.text and "provider-secret-name" not in response.text
    upstream = json.loads(calls[0].content)
    assert upstream["model"] == "free-a" and upstream["stream"] is False
    assert "mg" not in upstream and "idempotency-key" not in calls[0].headers
    assert "2+2?" not in caplog.text and "test-upstream-secret" not in caplog.text
    record = json.loads(next(r.message for r in caplog.records if r.name == "mg.audit"))
    assert record["client"] == "developer" and record["cost_estimate_usd"] == 0
    assert record["usage"]["total_tokens"] == 11


@pytest.mark.parametrize("field,value", [("api_base", "http://attacker"),
                                         ("api_key", "injected"), ("fallbacks", ["paid"]),
                                         ("client", "portal"), ("num_retries", 4)])
def test_no_provider_control_passthrough(harness, field, value):
    client, calls, _ = harness()
    assert client.post("/v1/chat/completions", headers=headers(),
                       json=payload(**{field: value})).status_code == 400
    assert not calls


def test_paid_request_rejected(harness):
    client, calls, _ = harness()
    assert client.post("/v1/chat/completions", headers=headers(),
                       json=payload(mg={"max_cost_class": "PAID"})).status_code == 400
    assert not calls


def test_no_provider(config, harness):
    config.models = []
    client, calls, _ = harness()
    response = client.post("/v1/chat/completions", headers=headers(), json=payload())
    assert response.status_code == 503 and response.json()["error"]["code"] == "NO_ELIGIBLE_FREE_MODEL"
    assert client.get("/health/ready", headers=headers()).json()["status"] == "configured_no_eligible_provider"
    assert not calls


def test_fallback_429_cooldown(config, harness, success):
    from mg_ai.config import Retry429Review
    config.models[0].retry_429_review = Retry429Review(
        adapter="LiteLLMAdapter", provider="openrouter", model=config.models[0].model,
        semantics="REJECTED_BEFORE_EXECUTION", evidence="synthetic mock contract only",
        reviewed_by="test", valid_until=config.models[0].free_verified_until)
    config.models.append(config.models[0].model_copy(update={"id": "free-b"}))
    def handler(request):
        if json.loads(request.content)["model"] == "free-a":
            return httpx.Response(429, headers={"Retry-After": "120"}, text="secret-error")
        return httpx.Response(200, json=success)
    client, calls, state = harness(handler)
    assert client.post("/v1/chat/completions", headers=headers(), json=payload()).status_code == 200
    assert len(calls) == 2 and state.health("free-a")["status"] == "RATE_LIMITED"
    assert client.post("/v1/chat/completions", headers=headers(), json=payload()).status_code == 200
    assert len(calls) == 3


@pytest.mark.parametrize("status", [500, 502, 504, 408, 409])
def test_ambiguous_never_falls_back(config, harness, status):
    config.models.append(config.models[0].model_copy(update={"id": "free-b"}))
    client, calls, state = harness(lambda _: httpx.Response(status, text="provider-key-leak"))
    response = client.post("/v1/chat/completions", headers=headers(key="uncertain"), json=payload())
    assert response.status_code == 502
    assert response.json()["error"]["execution_state"] == "RECONCILIATION_REQUIRED"
    assert "provider-key-leak" not in response.text and len(calls) == 1
    duplicate = client.post("/v1/chat/completions", headers=headers(key="uncertain"), json=payload())
    assert duplicate.status_code == 409 and len(calls) == 1
    assert state.db.execute("SELECT status FROM executions").fetchone()[0] == "AMBIGUOUS"


@pytest.mark.parametrize("exception,code", [(httpx.ConnectTimeout, "NO_ELIGIBLE_FREE_MODEL"),
                                          (httpx.ReadTimeout, "EXECUTION_AMBIGUOUS"),
                                          (httpx.WriteError, "EXECUTION_AMBIGUOUS")])
def test_transport_classification(harness, exception, code):
    def handler(request):
        raise exception("sensitive upstream detail", request=request)
    client, _, _ = harness(handler)
    response = client.post("/v1/chat/completions", headers=headers(), json=payload())
    assert response.json()["error"]["code"] == code
    assert "sensitive" not in response.text


@pytest.mark.parametrize("status", [401, 403, 404])
def test_provider_configuration_rejection(harness, status):
    client, _, state = harness(lambda _: httpx.Response(status, text="raw provider error"))
    response = client.post("/v1/chat/completions", headers=headers(), json=payload())
    assert response.json()["error"]["code"] == "NO_ELIGIBLE_FREE_MODEL"
    assert state.health("free-a")["cooldown"] > 0


def test_malformed_response_and_invalid_structured_output(harness):
    client, calls, _ = harness(lambda _: httpx.Response(200, json={"choices": []}))
    assert client.post("/v1/chat/completions", headers=headers(), json=payload()).status_code == 502
    client2, _, _ = harness()
    fmt = {"type": "json_schema", "json_schema": {"name": "obj", "schema": {"type": "object"}}}
    assert client2.post("/v1/chat/completions", headers=headers(),
                        json=payload(response_format=fmt)).status_code == 502
    assert len(calls) == 1


def test_size_privacy_and_remote_images(harness):
    client, calls, _ = harness()
    assert client.post("/v1/chat/completions", headers=headers(), content=b"x" * 1048577).status_code == 413
    assert client.post("/v1/chat/completions", headers=headers(),
                       json=payload(mg={"privacy_class": "CONFIDENTIAL"})).status_code == 403
    image = [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "http://127.0.0.1"}}]}]
    assert client.post("/v1/chat/completions", headers=headers(),
                       json=payload(messages=image)).status_code == 400
    assert not calls


def test_buffered_stream(harness):
    client, _, _ = harness()
    response = client.post("/v1/chat/completions", headers=headers(),
                           json=payload(stream=True, stream_options={"include_usage": True}))
    assert response.status_code == 200
    assert response.text.endswith("data: [DONE]\n\n") and "chat.completion.chunk" in response.text
    assert "total_tokens" in response.text


def test_rate_and_monthly_limits(config, harness):
    config.clients["developer"].requests_per_minute = 1
    client, calls, _ = harness()
    assert client.post("/v1/chat/completions", headers=headers(), json=payload()).status_code == 200
    assert client.post("/v1/chat/completions", headers=headers(), json=payload()).status_code == 429
    assert len(calls) == 1


def test_idempotency_conflict_and_client_scoping(harness):
    client, calls, _ = harness()
    assert client.post("/v1/chat/completions", headers=headers(key="same"), json=payload()).status_code == 200
    response = client.post("/v1/chat/completions", headers=headers(key="same"), json=payload(max_tokens=2))
    assert response.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert client.post("/v1/chat/completions", headers=headers("portal", "same"),
                       json=payload("portal-normal")).status_code == 200
    assert len(calls) == 2


def test_duplicate_identity_survives_no_eligible_provider(harness):
    client, calls, _ = harness(lambda _: httpx.Response(500))
    first = client.post("/v1/chat/completions", headers=headers(key="only-one"), json=payload())
    assert first.status_code == 502
    second = client.post("/v1/chat/completions", headers=headers(key="only-one"), json=payload())
    assert second.status_code == 409
    assert second.json()["error"]["execution_state"] == "RECONCILIATION_REQUIRED"
    assert len(calls) == 1


def test_tool_call_schema_and_buffered_stream(harness, success):
    success["choices"][0]["message"] = {"role": "assistant", "content": None, "tool_calls": [
        {"id": "call-1", "type": "function", "function": {"name": "add", "arguments": "{\"a\":2}"},
         "provider_debug": "must-not-leak"}]}
    success["choices"][0]["finish_reason"] = "tool_calls"
    client, _, _ = harness(lambda _: httpx.Response(200, json=success))
    tool = {"type": "function", "function": {"name": "add", "parameters": {
        "type": "object", "properties": {"a": {"type": "integer"}}, "required": ["a"]}}}
    response = client.post("/v1/chat/completions", headers=headers(),
                           json=payload("dev-code", tools=[tool], tool_choice="required", stream=True))
    assert response.status_code == 200 and "tool_calls" in response.text
    assert "must-not-leak" not in response.text


def test_inferred_tool_capability(config, harness):
    config.models[0].capabilities.discard("TOOL_CALLING")
    client, calls, _ = harness()
    tool = {"type": "function", "function": {"name": "add"}}
    response = client.post("/v1/chat/completions", headers=headers(), json=payload(tools=[tool]))
    assert response.status_code == 503 and not calls


def test_invalid_retry_after_is_bounded(harness):
    client, _, state = harness(lambda _: httpx.Response(429, headers={"Retry-After": "NaN"}))
    response = client.post("/v1/chat/completions", headers=headers(), json=payload())
    assert response.status_code == 502 and state.health("free-a")["cooldown"] > 0
