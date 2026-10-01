import json
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from conftest import headers, payload
from mg_ai.config import load_config
from mg_ai.deep import DEEP_ROUTE, DeepAdapter, create_deep_app
from mg_ai.deep_state import DEEP_CONTEXT_MAX_CHARS, DeepState
from mg_ai.errors import MGError
from mg_ai.routing import select

TOKEN = 'synthetic-deep-client-' + 'x' * 40


def request_body(**extra):
    body = dict(execution_id=str(uuid4()), task_id=str(uuid4()),
                conversation_id=str(uuid4()), attempt=1, input='2+2?',
                privacy_class='PUBLIC')
    body.update(extra)
    return body


@pytest.fixture
def deep(tmp_path):
    opened = []

    def make(handler=None, enabled=True, optimize_previous=False):
        calls = []

        def upstream(request):
            calls.append(request)
            if handler:
                result = handler(request)
                if result is not None:
                    return result
            if request.url.path == '/v1/models':
                return httpx.Response(200, json={'data': [{'id': DEEP_ROUTE}]})
            count = sum(call.url.path == '/v1/responses' for call in calls)
            return httpx.Response(200, json={'id': f'resp_synthetic_{count}', 'model': DEEP_ROUTE,
                'status': 'completed', 'output': [{'type': 'message', 'role': 'assistant',
                    'content': [{'type': 'output_text', 'text': '4'}]}]})

        state = DeepState(str(tmp_path / f'{len(opened)}.sqlite'))
        if enabled:
            state.configure('enable', 'test', 'synthetic')
            state.configure('session-ready', 'test', 'synthetic')
        adapter = DeepAdapter('http://omniroute:20129', 'synthetic-upstream-only',
                              httpx.MockTransport(upstream), optimize_previous)
        client = TestClient(create_deep_app(state, adapter, TOKEN), raise_server_exceptions=False)
        client.headers['Authorization'] = 'Bearer ' + TOKEN
        opened.append((client, state))
        return client, state, calls

    yield make
    for client, state in opened:
        client.close()
        state.db.close()


def test_first_and_second_turn_preserve_private_continuity(deep):
    client, state, calls = deep()
    first = request_body()
    r = client.post('/internal/deep/execute', json=first)
    result = r.json()
    assert r.status_code == 200 and result['answer'] == '4'
    assert result['continuity'] == 'TASK_SCOPED' and result['status'] == 'COMPLETED'
    assert result['request_id'] == r.headers['x-request-id'] and result['attempt'] == 1
    assert result['task_id'] == first['task_id'] and result['conversation_id'] == first['conversation_id']
    assert result['created_at'] <= result['completed_at']
    assert 'upstream_thread_id' not in result and 'upstream_response_id' not in result
    assert len(calls) == 2 and calls[1].url.path == '/v1/responses'
    sent_first = json.loads(calls[1].content)
    assert sent_first['model'] == DEEP_ROUTE and sent_first['reasoning'] == {'effort': 'high'}
    assert DEEP_ROUTE == 'cx/gpt-5.6-sol-high'
    assert sent_first['tools'] == [] and sent_first['tool_choice'] == 'none'
    assert calls[1].headers['originator'].startswith('codex')
    assert [item['role'] for item in sent_first['input']] == ['developer', 'user']
    metadata = sent_first['client_metadata']['x-codex-turn-metadata']
    assert metadata['turn_id'] == first['execution_id'] and metadata['task_id'] == first['task_id']
    assert metadata['context_version'] == 'mg-deep-transcript-v1'
    assert 'previous_response_id' not in sent_first and '_nativeCodexPassthrough' not in sent_first
    assert state.evidence(first['execution_id'])['status'] == 'COMPLETED'
    first_turn = state.transcript(first['conversation_id'])[0]
    assert first_turn['user_content'] == first['input']
    assert first_turn['assistant_content'] == '4' and first_turn['completed'] is not None
    assert 'synthetic-upstream-only' not in r.text and TOKEN not in r.text

    second = request_body(task_id=first['task_id'], conversation_id=first['conversation_id'],
                          attempt=2)
    second_result = client.post('/internal/deep/execute', json=second).json()
    assert second_result['status'] == 'COMPLETED' and second_result['attempt'] == 2
    sent_second = json.loads(calls[3].content)
    assert 'previous_response_id' not in sent_second
    assert [item['role'] for item in sent_second['input']] == [
        'developer', 'user', 'assistant', 'user'
    ]
    assert sent_second['input'][1]['content'][0]['text'] == first['input']
    assert sent_second['input'][2]['content'][0]['text'] == '4'
    assert sent_second['input'][3]['content'][0]['text'] == second['input']
    second_metadata = sent_second['client_metadata']['x-codex-turn-metadata']
    assert second_metadata['thread_id'] == metadata['thread_id']
    assert state.evidence(second['execution_id'])['status'] == 'COMPLETED'

    third = request_body(task_id=first['task_id'], conversation_id=first['conversation_id'],
                         attempt=3)
    assert client.post('/internal/deep/execute', json=third).status_code == 200
    sent_third = json.loads(calls[5].content)
    assert [item['role'] for item in sent_third['input']] == [
        'developer', 'user', 'assistant', 'user', 'assistant', 'user'
    ]
    assert [turn['attempt'] for turn in state.transcript(first['conversation_id'])] == [1, 2, 3]


def test_cross_task_isolation_and_conversation_binding(deep):
    client, _, calls = deep()
    first = request_body(input='task-one-private-synthetic')
    assert client.post('/internal/deep/execute', json=first).status_code == 200
    other = request_body(input='task-two-public-synthetic')
    assert client.post('/internal/deep/execute', json=other).status_code == 200
    first_payload, other_payload = json.loads(calls[1].content), json.loads(calls[3].content)
    first_thread = first_payload['client_metadata']['x-codex-turn-metadata']['thread_id']
    other_thread = other_payload['client_metadata']['x-codex-turn-metadata']['thread_id']
    assert first_thread != other_thread and 'previous_response_id' not in other_payload
    assert [item['role'] for item in other_payload['input']] == ['developer', 'user']
    assert first['input'] not in json.dumps(other_payload)
    conflict = request_body(task_id=str(uuid4()), conversation_id=first['conversation_id'], attempt=2)
    response = client.post('/internal/deep/execute', json=conflict)
    assert response.json()['error']['code'] == 'CONVERSATION_TASK_CONFLICT'
    assert len(calls) == 4


def test_duplicate_and_conflicting_execution_id_never_redispatch(deep):
    client, _, calls = deep()
    body = request_body()
    assert client.post('/internal/deep/execute', json=body).status_code == 200
    duplicate = client.post('/internal/deep/execute', json=body)
    assert duplicate.json()['error']['code'] == 'EXECUTION_ALREADY_RECORDED'
    conflicting = {**body, 'input': 'different'}
    conflict = client.post('/internal/deep/execute', json=conflicting)
    assert conflict.json()['error']['code'] == 'IDEMPOTENCY_CONFLICT'
    assert len(calls) == 2


@pytest.mark.parametrize('extra', [{'model': 'other'}, {'tools': []},
                                  {'continuity_token': 'resp_old'}])
def test_invalid_or_continuation_never_dispatches(deep, extra):
    client, _, calls = deep()
    body = request_body()
    body.update(extra)
    assert client.post('/internal/deep/execute', json=body).status_code in {400, 409}
    assert not calls


def test_private_png_attachment_is_staged_verified_and_removed(deep, monkeypatch, tmp_path):
    monkeypatch.setenv('MG_DEEP_ATTACHMENT_ROOT', str(tmp_path / 'attachments'))
    client, _, calls = deep()
    body = request_body(privacy_class='INTERNAL')
    content = b'private-png-synthetic'
    digest = __import__('hashlib').sha256(content).hexdigest()
    body['attachments'] = [{'index': 0, 'filename': 'private.png', 'mime_type': 'image/png',
                            'size_bytes': len(content), 'sha256': digest}]
    staged = client.put(
        f"/internal/deep/executions/{body['execution_id']}/attachments/0",
        content=content,
        headers={'content-type': 'image/png', 'x-mg-filename': 'private.png',
                 'x-mg-size': str(len(content)), 'x-mg-sha256': digest},
    )
    assert staged.status_code == 200 and staged.json()['status'] == 'STAGED'
    response = client.post('/internal/deep/execute', json=body)
    assert response.status_code == 200
    sent = json.loads(calls[1].content)
    part = sent['input'][-1]['content'][1]
    assert part['type'] == 'input_image'
    assert part['image_url'].startswith('data:image/png;base64,')
    assert not (tmp_path / 'attachments' / body['execution_id']).exists()


def test_private_attachment_cleanup_endpoint_is_authenticated_and_idempotent(deep, monkeypatch, tmp_path):
    monkeypatch.setenv('MG_DEEP_ATTACHMENT_ROOT', str(tmp_path / 'attachments'))
    client, _, _ = deep()
    execution_id = str(uuid4())
    content = b'private-text'
    digest = __import__('hashlib').sha256(content).hexdigest()
    staged = client.put(f'/internal/deep/executions/{execution_id}/attachments/0', content=content,
        headers={'content-type': 'text/plain', 'x-mg-filename': 'notes.txt',
                 'x-mg-size': str(len(content)), 'x-mg-sha256': digest})
    assert staged.status_code == 200
    assert client.delete(f'/internal/deep/executions/{execution_id}/attachments').status_code == 200
    assert client.delete(f'/internal/deep/executions/{execution_id}/attachments').status_code == 200
    assert not (tmp_path / 'attachments' / execution_id).exists()


def test_session_and_auth_fail_closed(deep):
    client, _, calls = deep(enabled=False)
    r = client.post('/internal/deep/execute', json=request_body())
    assert r.json()['error']['code'] == 'DEEP_SESSION_UNAVAILABLE'
    assert client.post('/internal/deep/execute', json=request_body(),
                       headers={'Authorization': 'Bearer synthetic-free-token'}).status_code == 401
    assert not calls


@pytest.mark.parametrize('failure', ['connect', 'read', '429', 'session', 'wrong-model', 'tools'])
def test_transport_and_response_ambiguity_never_retries(deep, failure):
    def handler(request):
        if request.method == 'GET':
            return None
        if failure == 'connect':
            raise httpx.ConnectError('secret-value')
        if failure == 'read':
            raise httpx.ReadTimeout('secret-value')
        if failure == '429':
            return httpx.Response(429, json={'error': {'message': 'secret-value'}})
        if failure == 'session':
            return httpx.Response(401)
        return httpx.Response(200, json={'id': 'resp_x', 'status': 'completed',
            'model': 'low' if failure == 'wrong-model' else 'high',
            'output': [{'type': 'function_call'}]})
    client, state, calls = deep(handler)
    body = request_body()
    r = client.post('/internal/deep/execute', json=body)
    assert r.status_code in {502, 503} and 'secret-value' not in r.text
    expected = 'NOT_DISPATCHED' if failure == 'connect' else 'EXECUTION_AMBIGUOUS'
    assert state.evidence(body['execution_id'])['status'] == expected
    assert len(calls) == 2
    client.post('/internal/deep/execute', json=body)
    assert len(calls) == 2
    if failure != 'connect':
        assert client.post('/internal/deep/execute', json=request_body()).json()['error']['code'] == 'DEEP_BUSY'
        assert len(calls) == 2


def test_high_missing_is_predispatch(deep):
    client, state, calls = deep(lambda _: httpx.Response(200, json={'data': [{'id': 'low'}]}))
    body = request_body()
    assert client.post('/internal/deep/execute', json=body).json()['error']['code'] == 'DEEP_HIGH_UNAVAILABLE'
    assert len(calls) == 1 and state.evidence(body['execution_id'])['status'] == 'NOT_DISPATCHED'


def test_deterministic_failure_is_terminal_and_never_retried(deep):
    def handler(request):
        if request.method == 'POST':
            return httpx.Response(400, json={'error': {'code': 'unsupported_endpoint'}})
        return None
    client, state, calls = deep(handler)
    body = request_body()
    response = client.post('/internal/deep/execute', json=body)
    assert response.json()['error']['code'] == 'DEEP_CONTRACT_UNAVAILABLE'
    assert state.evidence(body['execution_id'])['status'] == 'FAILED_DETERMINISTIC'
    client.post('/internal/deep/execute', json=body)
    assert len(calls) == 2


def test_missing_previous_response_recovers_with_full_transcript(deep):
    post_count = 0

    def handler(request):
        nonlocal post_count
        if request.method == 'POST':
            post_count += 1
            if post_count == 2:
                sent = json.loads(request.content)
                assert sent['previous_response_id'] == 'resp_synthetic_1'
                return httpx.Response(400, json={
                    'error': {'code': 'previous_response_not_found'}})
        return None

    client, state, calls = deep(handler, optimize_previous=True)
    first = request_body()
    assert client.post('/internal/deep/execute', json=first).status_code == 200
    second = request_body(task_id=first['task_id'], conversation_id=first['conversation_id'],
                          attempt=2)
    response = client.post('/internal/deep/execute', json=second)
    assert response.status_code == 200 and response.json()['answer'] == '4'
    recovered = json.loads(calls[4].content)
    assert 'previous_response_id' not in recovered
    assert [item['role'] for item in recovered['input']] == [
        'developer', 'user', 'assistant', 'user'
    ]
    attempts = state.db.execute(
        'SELECT mode,outcome,provider_dispatch_possible FROM deep_dispatch_attempts '
        'WHERE execution_id=? ORDER BY internal_attempt', (second['execution_id'],)
    ).fetchall()
    assert [tuple(row) for row in attempts] == [
        ('PREVIOUS_RESPONSE_ID', 'DETERMINISTIC_PRE_DISPATCH', 0),
        ('FULL_TRANSCRIPT', 'COMPLETED', 1),
    ]
    assert state.evidence(second['execution_id'])['status'] == 'COMPLETED'
    conversation = state.db.execute(
        'SELECT previous_response_id FROM deep_conversations WHERE conversation_id=?',
        (first['conversation_id'],),
    ).fetchone()
    assert conversation['previous_response_id'] == 'resp_synthetic_3'
    client.post('/internal/deep/execute', json=second)
    assert len(calls) == 5


def test_ambiguous_optimization_attempt_never_replays_full_transcript(deep):
    post_count = 0

    def handler(request):
        nonlocal post_count
        if request.method == 'POST':
            post_count += 1
            if post_count == 2:
                raise httpx.ReadTimeout('uncertain after dispatch')
        return None

    client, state, calls = deep(handler, optimize_previous=True)
    first = request_body()
    assert client.post('/internal/deep/execute', json=first).status_code == 200
    second = request_body(task_id=first['task_id'], conversation_id=first['conversation_id'],
                          attempt=2)
    response = client.post('/internal/deep/execute', json=second)
    assert response.json()['error']['code'] == 'EXECUTION_AMBIGUOUS'
    assert state.evidence(second['execution_id'])['status'] == 'EXECUTION_AMBIGUOUS'
    assert sum(call.method == 'POST' for call in calls) == 2


def test_attempt_sequence_is_enforced_before_dispatch(deep):
    client, _, calls = deep()
    body = request_body(attempt=2)
    response = client.post('/internal/deep/execute', json=body)
    assert response.json()['error']['code'] == 'ATTEMPT_CONFLICT'
    assert not calls


def test_durable_singleton_across_connections_and_kill(tmp_path):
    path = str(tmp_path / 'shared.sqlite')
    first, second = DeepState(path), DeepState(path)
    first.configure('enable', 'test', 'approved synthetic')
    first.configure('session-ready', 'test', 'approved synthetic')
    first.claim('one', 'task-one', 'conversation-one', 1, b'public')
    with pytest.raises(MGError) as exc:
        second.claim('two', 'task-two', 'conversation-two', 1, b'public')
    assert exc.value.code == 'DEEP_BUSY'
    first.mark('one', 'DISPATCHED')
    first.db.close()
    with pytest.raises(MGError) as exc:
        second.claim('three', 'task-three', 'conversation-three', 1, b'public')
    assert exc.value.reconciliation
    second.set_provider_enabled('omniroute', False, 'owner', 'stop')
    assert not second.provider_enabled('omniroute')
    second.db.close()


def test_unresolved_reconciliation_releases_slot_but_blocks_conversation(tmp_path):
    state = DeepState(str(tmp_path / 'reconciliation.sqlite'))
    state.configure('enable', 'test', 'synthetic')
    state.configure('session-ready', 'test', 'synthetic')
    state.claim('ambiguous', 'task-one', 'conversation-one', 1, b'public')
    state.mark('ambiguous', 'DISPATCHED')
    state.mark('ambiguous', 'EXECUTION_AMBIGUOUS')

    with pytest.raises(MGError) as pending:
        state.reconcile('ambiguous', 'UNRESOLVED', 'owner', 'no conclusive upstream record')
    assert pending.value.code == 'RECONCILIATION_SETTLEMENT_PENDING'
    assert state.db.execute('SELECT execution_id FROM deep_claim').fetchone()[0] == 'ambiguous'

    state.db.execute("UPDATE deep_runs SET settle_after=0 WHERE execution_id='ambiguous'")
    state.reconcile('ambiguous', 'UNRESOLVED', 'owner', 'settlement bound elapsed; no evidence')
    assert state.evidence('ambiguous')['status'] == 'EXECUTION_AMBIGUOUS'
    assert state.evidence('ambiguous')['reconciliation_outcome'] == 'UNRESOLVED'
    with pytest.raises(MGError) as duplicate:
        state.claim('ambiguous', 'task-one', 'conversation-one', 1, b'public')
    assert duplicate.value.code == 'EXECUTION_ALREADY_RECORDED'
    with pytest.raises(MGError) as blocked:
        state.claim('next', 'task-one', 'conversation-one', 2, b'public next')
    assert blocked.value.code == 'DEEP_RECONCILIATION_REQUIRED'

    state.claim('unrelated', 'task-two', 'conversation-two', 1, b'public other')
    audit = state.db.execute(
        'SELECT outcome,actor,evidence FROM deep_reconciliation_audit WHERE execution_id=?',
        ('ambiguous',),
    ).fetchone()
    assert tuple(audit) == ('UNRESOLVED', 'owner', 'settlement bound elapsed; no evidence')
    state.db.close()


def test_confirmed_failure_reconciliation_continues_from_last_completed_response(tmp_path):
    state = DeepState(str(tmp_path / 'confirmed-failed.sqlite'))
    state.configure('enable', 'test', 'synthetic')
    state.configure('session-ready', 'test', 'synthetic')
    state.claim('first', 'task', 'conversation', 1, b'first', 'first user')
    state.mark('first', 'DISPATCHED')
    state.mark('first', 'COMPLETED', 'resp_confirmed', 'first answer')
    state.claim('second', 'task', 'conversation', 2, b'second', 'second user')
    state.mark('second', 'DISPATCHED')
    state.mark('second', 'EXECUTION_AMBIGUOUS')
    state.reconcile('second', 'CONFIRMED_FAILED', 'owner',
                    'existing HTTP 400 proves pre-provider rejection')
    claim = state.claim('third', 'task', 'conversation', 3, b'third', 'third user')
    assert claim['previous_response_id'] == 'resp_confirmed'
    assert state.evidence('second')['status'] == 'FAILED_DETERMINISTIC'
    state.mark('third', 'NOT_DISPATCHED')
    state.db.close()


def test_only_final_answer_is_persisted_when_upstream_contains_reasoning(deep):
    def handler(request):
        if request.method == 'POST':
            return httpx.Response(200, json={'id': 'resp_safe', 'model': DEEP_ROUTE,
                'status': 'completed', 'output': [
                    {'type': 'reasoning', 'summary': [{'text': 'hidden reasoning'}]},
                    {'type': 'message', 'role': 'assistant', 'content': [
                        {'type': 'output_text', 'text': 'final answer'}]},
                ]})
        return None

    client, state, _ = deep(handler)
    body = request_body()
    assert client.post('/internal/deep/execute', json=body).status_code == 200
    stored = json.dumps(state.transcript(body['conversation_id']))
    assert 'final answer' in stored and 'hidden reasoning' not in stored
    assert 'synthetic-upstream-only' not in stored


def test_execution_cannot_complete_before_answer_is_persisted(tmp_path):
    state = DeepState(str(tmp_path / 'atomic-answer.sqlite'))
    state.configure('enable', 'test', 'synthetic')
    state.configure('session-ready', 'test', 'synthetic')
    state.claim('one', 'task', 'conversation', 1, b'one', 'user')
    state.mark('one', 'DISPATCHED')
    with pytest.raises(ValueError, match='requires response identity and answer'):
        state.mark('one', 'COMPLETED', 'resp_one')
    assert state.evidence('one')['status'] == 'DISPATCHED'
    assert state.transcript('conversation')[0]['assistant_content'] is None
    assert state.db.execute('SELECT 1 FROM deep_claim').fetchone()
    state.db.close()


def test_context_overflow_fails_closed_without_truncation(tmp_path):
    state = DeepState(str(tmp_path / 'context-limit.sqlite'))
    state.configure('enable', 'test', 'synthetic')
    state.configure('session-ready', 'test', 'synthetic')
    half = DEEP_CONTEXT_MAX_CHARS // 4
    state.claim('one', 'task', 'conversation', 1, b'one', 'u' * half)
    state.mark('one', 'DISPATCHED')
    state.mark('one', 'COMPLETED', 'resp_one', 'a' * half)
    state.claim('two', 'task', 'conversation', 2, b'two', 'u' * half)
    state.mark('two', 'DISPATCHED')
    state.mark('two', 'COMPLETED', 'resp_two', 'a' * half)
    with pytest.raises(MGError) as overflow:
        state.claim('three', 'task', 'conversation', 3, b'three', 'x')
    assert overflow.value.code == 'DEEP_CONTEXT_LIMIT_EXCEEDED'
    assert not state.evidence('three')
    state.db.close()


def test_operator_cannot_fabricate_completed_ambiguous_execution(tmp_path):
    state = DeepState(str(tmp_path / 'no-fabricated-success.sqlite'))
    state.configure('enable', 'test', 'synthetic')
    state.configure('session-ready', 'test', 'synthetic')
    state.claim('ambiguous', 'task', 'conversation', 1, b'public')
    state.mark('ambiguous', 'DISPATCHED')
    state.mark('ambiguous', 'EXECUTION_AMBIGUOUS')
    with pytest.raises(MGError) as error:
        state.reconcile('ambiguous', 'CONFIRMED_COMPLETED', 'owner', 'unsupported assertion')
    assert error.value.code == 'CONFIRMED_COMPLETION_EVIDENCE_REQUIRED'
    assert state.db.execute('SELECT 1 FROM deep_claim').fetchone()
    assert not state.db.execute('SELECT 1 FROM deep_reconciliation_audit').fetchone()
    state.db.close()


def test_current_free_privacy_and_no_deep_selection(tmp_path, monkeypatch):
    config = load_config()
    state = DeepState(str(tmp_path / 'eligibility.sqlite'))
    for model in config.models:
        monkeypatch.setenv(model.credential_env, 'synthetic-key-only')
    assert 'portal-deep' not in config.routes
    for client_name, route_name in [('life-os', 'life-study'), ('developer', 'dev-code'),
                                     ('portal', 'portal-normal')]:
        policy, route = config.clients[client_name], config.routes[route_name]
        assert not policy.paid_allowed and policy.monthly_budget_usd == 0
        chosen = select(config, policy, route, route.capabilities, policy.default_privacy,
                        100, 100, state)
        assert all(m.provider != 'omniroute' and m.cost_class == 'FREE' for m in chosen)
        expected = ('proposal-nex-pro' if client_name == 'life-os'
                    else 'groq-qwen3-8-27b')
        assert route.champion == expected
        assert [model.id for model in chosen] == [expected]
        if client_name != 'life-os':
            assert policy.default_privacy == 'INTERNAL'
    state.db.close()


def test_free_http_cannot_choose_deep(harness):
    client, calls, _ = harness()
    for route in ['portal-deep', DEEP_ROUTE]:
        assert client.post('/v1/chat/completions', headers=headers('portal'),
                           json=payload(route)).status_code in {400, 403}
    assert not calls
