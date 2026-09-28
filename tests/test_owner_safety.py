import asyncio
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from conftest import headers, payload
from mg_ai import live_benchmark
from mg_ai.config import Retry429Review
from mg_ai.providers import LiteLLMAdapter
from mg_ai.proxy_config import render
from mg_ai.state import State
from test_operationalization import catalog


def test_portal_cannot_downgrade_or_raise_without_grant(config, harness):
    client, calls, _ = harness()
    for privacy, code in [("PUBLIC", "PRIVACY_DOWNGRADE_FORBIDDEN"),
                          ("CONFIDENTIAL", "CAPABILITY_OR_PRIVACY_FORBIDDEN")]:
        r = client.post('/v1/chat/completions', headers=headers('portal'),
                        json=payload('portal-normal', mg={'privacy_class': privacy}))
        assert r.status_code == 403 and r.json()['error']['code'] == code
    assert not calls


def test_internal_missing_model_and_public_developer(config, harness):
    config.models[0].privacy_classes = {'PUBLIC'}
    config.clients['developer'].default_privacy = 'PUBLIC'
    client, calls, _ = harness()
    r = client.post('/v1/chat/completions', headers=headers('portal'), json=payload('portal-normal'))
    assert r.json()['error']['code'] == 'NO_ELIGIBLE_FREE_MODEL' and not calls
    assert client.post('/v1/chat/completions', headers=headers(),
                       json=payload(mg={'privacy_class': 'PUBLIC'})).status_code == 200


def test_higher_privacy_with_grant_and_eligible_model(config, harness):
    config.clients['portal'].privacy_classes.add('CONFIDENTIAL')
    config.models[0].privacy_classes.add('CONFIDENTIAL')
    config.models[0].confidential_allowed = True
    config.models[0].retention_known = True
    config.models[0].training_use_known = True
    client, calls, _ = harness()
    assert client.post('/v1/chat/completions', headers=headers('portal'),
        json=payload('portal-normal', mg={'privacy_class': 'CONFIDENTIAL'})).status_code == 200
    assert len(calls) == 1


@pytest.mark.parametrize('review', ['missing', 'expired', 'wrong-provider'])
def test_unreviewed_429_never_falls_back(config, harness, review):
    if review != 'missing':
        config.models[0].retry_429_review = Retry429Review(
            adapter='LiteLLMAdapter', provider='nvidia' if review == 'wrong-provider' else 'openrouter',
            model=config.models[0].model, semantics='REJECTED_BEFORE_EXECUTION',
            evidence='mock only', reviewed_by='test',
            valid_until=datetime.now(timezone.utc) + timedelta(days=-1 if review == 'expired' else 1))
    config.models.append(config.models[0].model_copy(update={'id': 'free-b'}))
    client, calls, state = harness(lambda _: httpx.Response(429))
    r = client.post('/v1/chat/completions', headers=headers(key='no-replay'), json=payload())
    assert r.status_code == 502 and len(calls) == 1
    assert state.db.execute('SELECT status FROM executions').fetchone()[0] == 'AMBIGUOUS'


def test_provider_control_persists_and_overrides_model(config, harness, tmp_path):
    client, calls, state = harness()
    db = state.db.execute('PRAGMA database_list').fetchone()[2]
    owner = State(db)
    owner.set_provider_enabled('openrouter', False, 'owner', 'emergency')
    owner.db.close()
    assert client.post('/v1/chat/completions', headers=headers(), json=payload()).status_code == 503
    assert not calls and config.models[0].enabled
    owner = State(db)
    assert not owner.provider_enabled('openrouter')
    owner.set_provider_enabled('openrouter', True, 'owner', 'reviewed recovery')
    config.models[0].enabled = False
    assert client.post('/v1/chat/completions', headers=headers(), json=payload()).status_code == 503
    assert not calls
    config.models[0].enabled = True
    assert client.post('/v1/chat/completions', headers=headers(), json=payload()).status_code == 200
    assert owner.db.execute('SELECT COUNT(*) FROM provider_control_audit').fetchone()[0] == 2
    owner.db.close()


def test_kill_between_selection_and_fallback(config, harness):
    config.models.append(config.models[0].model_copy(update={'id': 'free-b'}))
    def handler(_):
        state.set_provider_enabled('openrouter', False, 'owner', 'during first attempt')
        return httpx.Response(404)
    client, calls, state = harness(handler)
    assert client.post('/v1/chat/completions', headers=headers(), json=payload()).status_code == 503
    assert len(calls) == 1


@pytest.mark.parametrize('blocker', ['campaign', 'dataset', 'manifest', 'provider'])
def test_benchmark_guard_no_dispatch(config, monkeypatch, tmp_path, blocker):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'synthetic-test')
    m = config.models[0].model_copy(update={'credential_env': 'OPENROUTER_API_KEY'})
    if blocker == 'dataset':
        changed = tmp_path / 'synthetic.json'
        changed.write_text('[]')
        monkeypatch.setattr(live_benchmark, 'CASES', changed)
    if blocker == 'manifest':
        manifest = json.loads(live_benchmark.DATASET_MANIFEST.read_text())
        manifest['sha256'] = '0' * 64
        path = tmp_path / 'manifest.json'
        path.write_text(json.dumps(manifest))
        monkeypatch.setattr(live_benchmark, 'DATASET_MANIFEST', path)
    calls = []
    async def check():
        state = State(str(tmp_path / 'run.sqlite'))
        controls = State(str(tmp_path / 'shared.sqlite'))
        if blocker == 'provider':
            controls.set_provider_enabled('openrouter', False, 'owner', 'test stop')
        adapter = LiteLLMAdapter('http://mock', 'synthetic', httpx.MockTransport(lambda r: calls.append(r)))
        try:
            return await live_benchmark.run(m, catalog(m), adapter, state, 'unique', tmp_path / 'r.json',
                approved_by='' if blocker == 'campaign' else 'test', control_state=controls)
        finally:
            await adapter.http.aclose()
            state.db.close()
            controls.db.close()
    if blocker == 'provider':
        assert asyncio.run(check())['blocker'] == 'PROVIDER_DISABLED'
    else:
        with pytest.raises(ValueError):
            asyncio.run(check())
    assert calls == []


def test_no_litellm_retry_or_paid_fallback(config):
    data = render(config)
    assert data['router_settings']['fallbacks'] == []
    assert data['router_settings']['num_retries'] == 0
    assert data['litellm_settings']['num_retries'] == 0
    p = data['model_list'][0]['litellm_params']
    assert p['num_retries'] == 0 and p['extra_body']['provider']['allow_fallbacks'] is False
    assert p['extra_body']['provider']['max_price'] == {'prompt': 0, 'completion': 0}


def test_provider_cli_requires_attribution_and_preserves_restart(tmp_path):
    path = str(tmp_path / 'control.sqlite')
    base = [sys.executable, '-m', 'mg_ai.provider_control']
    denied = subprocess.run(base + ['disable', 'openrouter', '--state', path], capture_output=True)
    assert denied.returncode != 0
    for action, expected in [('disable', False), ('enable', True)]:
        result = subprocess.run(base + [action, 'openrouter', '--state', path,
            '--actor', 'synthetic-owner', '--reason', 'synthetic-test'], capture_output=True, text=True)
        assert result.returncode == 0
        listing = subprocess.run(base + ['list', '--state', path], capture_output=True, text=True)
        assert json.loads(listing.stdout.splitlines()[0])['openrouter'] is expected
    state = State(path)
    assert state.db.execute('SELECT COUNT(*) FROM provider_control_audit').fetchone()[0] == 2
    state.db.close()
