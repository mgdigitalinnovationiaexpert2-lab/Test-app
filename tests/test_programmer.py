import json

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient

from conftest import headers, payload
from mg_ai.config import Configuration, load_config
from mg_ai.gateway import create_app
from mg_ai.programmer import CODEX_MODEL, ProgrammerAdapter, responses_payload
from mg_ai.providers import LiteLLMAdapter
from mg_ai.requests import ChatRequest
from mg_ai.state import State

TOOL = {"type": "function", "function": {"name": "read_file", "parameters": {
    "type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}}
CALL = {"id": "call_fixture", "type": "function", "function": {
    "name": "read_file", "arguments": '{"path":"fixture.py"}'}}


def completed(output):
    return {"model": CODEX_MODEL, "status": "completed", "output": output,
            "usage": {"input_tokens": 20, "output_tokens": 4, "total_tokens": 24}}


def text_response(text="DONE"):
    return completed([{"type": "message", "role": "assistant", "content": [
        {"type": "output_text", "text": text}]}])


@pytest.fixture
def programmer(config, tmp_path):
    opened = []

    def make(handler=None):
        config.routes["dev-code"].backend = "CODEX"
        config.routes["dev-code"].champion = None
        calls, free_calls = [], []

        def wrapped(request):
            calls.append(request)
            return handler(request) if handler else httpx.Response(200, json=text_response())

        def free(request):
            free_calls.append(request)
            return httpx.Response(200, json={"choices": [{"message": {
                "role": "assistant", "content": "FREE"}, "finish_reason": "stop"}]})

        upstream = ProgrammerAdapter("http://omniroute:20129", "synthetic-" + "x" * 32,
                                     httpx.MockTransport(wrapped))
        adapter = LiteLLMAdapter("http://proxy", "synthetic-master", httpx.MockTransport(free))
        state = State(str(tmp_path / f"programmer-{len(opened)}.sqlite"))
        client = TestClient(create_app(config, state, adapter, upstream),
                            raise_server_exceptions=False)
        opened.append(client)
        return client, calls, free_calls, state

    yield make
    for client in opened:
        client.close()


def test_tool_roundtrip_stream_and_long_system(programmer):
    outputs = [completed([{"type": "function_call", "call_id": CALL["id"],
                          **CALL["function"]}]), text_response()]
    client, calls, free, state = programmer(
        lambda _: httpx.Response(200, json=outputs.pop(0)))
    messages = [{"role": "system", "content": "coding context " * 6000},
                {"role": "user", "content": "Inspect fixture.py"}]
    first = client.post("/v1/chat/completions", headers=headers(key="coding-1"), json=payload(
        "dev-code", messages=messages, tools=[TOOL], tool_choice="required", stream=True,
        stream_options={"include_usage": True}, max_tokens=16384))
    assert first.status_code == 200 and "text/event-stream" in first.headers["content-type"]
    chunks = [json.loads(line[6:]) for line in first.text.splitlines()
              if line.startswith("data: ") and line != "data: [DONE]"]
    assert chunks[0]["choices"][0]["delta"]["tool_calls"][0]["id"] == CALL["id"]
    assert chunks[1]["choices"][0]["finish_reason"] == "tool_calls"
    assert chunks[2]["usage"]["total_tokens"] == 24
    assert first.text.endswith("data: [DONE]\n\n")
    sent = json.loads(calls[0].content)
    assert sent["input"][0]["content"][0]["text"] == messages[0]["content"]
    assert sent["input"][0]["role"] == "developer"
    assert sent["max_output_tokens"] == 16384 and sent["tools"][0]["name"] == "read_file"
    messages += [{"role": "assistant", "tool_calls": [CALL]},
                 {"role": "tool", "tool_call_id": CALL["id"], "content": "def add(a,b): return a+b"}]
    second = client.post("/v1/chat/completions", headers=headers(key="coding-2"), json=payload(
        "dev-code", messages=messages, tools=[TOOL]))
    assert second.status_code == 200
    assert second.json()["choices"][0]["message"]["content"] == "DONE"
    history = json.loads(calls[1].content)["input"]
    assert history[-2]["type"] == "function_call"
    assert history[-1] == {"type": "function_call_output", "call_id": CALL["id"],
                           "output": "def add(a,b): return a+b"}
    assert len(calls) == 2 and not free
    assert all(row[0] == "SUCCESS" for row in state.db.execute("SELECT status FROM executions"))


@pytest.mark.parametrize("kind", ["read_timeout", "429", "500", "invalid_model", "invalid_tool"])
def test_ambiguity_is_nonretryable_and_never_falls_back(programmer, kind):
    def handler(request):
        if kind == "read_timeout":
            raise httpx.ReadTimeout("sensitive-upstream-text")
        if kind in {"429", "500"}:
            return httpx.Response(int(kind), json={"error": "sensitive-upstream-text"})
        data = text_response()
        if kind == "invalid_model":
            data["model"] = "other"
        else:
            data = completed([{"type": "function_call", "call_id": "call_bad",
                               "name": "forbidden", "arguments": "{}"}])
        return httpx.Response(200, json=data)
    client, calls, free, state = programmer(handler)
    response = client.post("/v1/chat/completions", headers=headers(key="once"),
                           json=payload("dev-code"))
    assert response.status_code == 422
    assert response.json()["error"]["execution_state"] == "RECONCILIATION_REQUIRED"
    assert response.json()["error"]["retryable"] is False
    assert "sensitive-upstream-text" not in response.text
    assert state.db.execute("SELECT status FROM executions").fetchone()[0] == "AMBIGUOUS"
    duplicate = client.post("/v1/chat/completions", headers=headers(key="once"),
                            json=payload("dev-code"))
    assert duplicate.status_code == 409
    assert len(calls) == 1 and not free


def test_route_isolation_and_readiness(programmer):
    client, calls, free, _ = programmer()
    assert client.get("/health/ready", headers=headers()).json()["eligible_routes"]["dev-code"] == 1
    assert client.post("/v1/chat/completions", headers=headers("portal"),
                       json=payload("dev-code")).status_code == 403
    assert client.post("/v1/chat/completions", headers=headers(),
                       json=payload("dev-light")).status_code == 200
    assert client.post("/v1/chat/completions", headers=headers("portal"),
                       json=payload("portal-normal")).status_code == 200
    assert not calls and len(free) == 2


@pytest.mark.parametrize("extra", [
    {"temperature": 0.5}, {"mg": {"max_cost_class": "FREE"}},
    {"messages": [{"role": "tool", "tool_call_id": "unknown", "content": "data"}]},
    {"messages": [{"role": "assistant", "tool_calls": [CALL]}]},
    {"messages": [{"role": "user", "content": "x" * 400_000}]},
])
def test_invalid_requests_do_not_dispatch(programmer, extra):
    client, calls, free, _ = programmer()
    response = client.post("/v1/chat/completions", headers=headers(),
                           json=payload("dev-code", **extra))
    assert response.status_code in {400, 413}
    assert not calls and not free


def test_configuration_and_deployment_are_scoped():
    from pathlib import Path
    config = load_config()
    assert config.routes["dev-code"].backend == "CODEX"
    assert all(route.backend == "FREE" for name, route in config.routes.items() if name != "dev-code")
    assert config.routes["dev-light"].champion == "groq-qwen3-8-27b"
    assert not config.routes["dev-light"].allow_fallbacks
    overlay = yaml.safe_load(Path("deploy/programmer.compose.yaml").read_text())
    assert set(overlay["services"]) == {"gateway"}
    assert overlay["networks"]["programmer_upstream"]["external"] is True
    invalid = config.model_dump()
    invalid["clients"]["portal"]["routes"].add("dev-code")
    with pytest.raises(ValueError, match="programmer-only"):
        Configuration.model_validate(invalid)


def test_multiple_tool_results_and_named_choice():
    second = {**CALL, "id": "call_second"}
    body = ChatRequest.model_validate(payload("dev-code", tools=[TOOL],
        tool_choice={"type": "function", "function": {"name": "read_file"}}, messages=[
            {"role": "assistant", "tool_calls": [CALL, second]},
            {"role": "tool", "tool_call_id": CALL["id"], "content": "first"},
            {"role": "tool", "tool_call_id": second["id"], "content": "second"}]))
    translated = responses_payload(body.model_dump(exclude_none=True))
    assert translated["tool_choice"] == {"type": "function", "name": "read_file"}
    assert len(translated["input"]) == 4
