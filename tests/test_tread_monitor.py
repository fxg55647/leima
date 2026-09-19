from types import SimpleNamespace
import pytest

SHA = 'a' * 40


@pytest.fixture
def monitor(app_module, monkeypatch):
    app = app_module
    for key, value in {'GITHUB_DISPATCH_TOKEN': 'test', 'VERCEL_GIT_PROVIDER': 'github',
                       'VERCEL_GIT_REPO_OWNER': 'fxg55647', 'VERCEL_GIT_REPO_SLUG': 'leima',
                       'VERCEL_GIT_COMMIT_REF': 'main', 'VERCEL_ENV': 'production'}.items():
        monkeypatch.setenv(key, value)
    state = {'authorized': True, 'hashes': {'tread_check.py': 'original'},
             'vercel': (False, SHA, None, True, [], False), 'api_error': False}
    kv = {app._KV_MONITOR_BASELINE: dict(state['hashes'])}
    monkeypatch.setattr(app, '_kv_get', lambda key=app._KV_KEY: kv.get(key))
    monkeypatch.setattr(app, '_kv_set', lambda value, key=app._KV_KEY, **k: kv.update({key: value}))
    monkeypatch.setattr(app, '_fetch_monitor_hashes', lambda token: state['hashes'])
    monkeypatch.setattr(app, '_fetch_vercel_state', lambda: state['vercel'])
    def get(url, params, **kwargs):
        assert '/actions/workflows/code_review.yml/runs' in url
        if state['api_error']:
            raise TimeoutError('GitHub unavailable')
        if 'head_sha' in params:
            assert params['head_sha'] == SHA
            runs = [{'head_sha': SHA}] if state['authorized'] else []
        else:
            runs = [] if params['status'] == 'in_progress' else [{'head_sha': SHA}]
        return SimpleNamespace(status_code=200, json=lambda: {'workflow_runs': runs})
    monkeypatch.setattr(app.http_requests, 'get', get)
    return state, kv


def test_monitor_change_and_recovery(client, monitor, app_module):
    state, kv = monitor
    assert client.get('/tread-monitor').json()['ok'] is True
    kv.pop(app_module._KV_MONITOR_CACHE)
    state['hashes'] = {'tread_check.py': 'modified'}
    result = client.get('/tread-monitor').json()
    assert result['ok'] is False
    assert result['changed'] == ['tread_check.py']
    kv.pop(app_module._KV_MONITOR_CACHE)
    state['hashes'] = {'tread_check.py': 'original'}
    assert client.get('/tread-monitor').json()['ok'] is True


@pytest.mark.parametrize('authorized', [True, False])
def test_deploy_requires_review_for_exact_sha(client, monitor, authorized):
    state, _ = monitor
    state.update(authorized=authorized, vercel=(True, 'b'*40, SHA, True, [], False))
    result = client.get('/tread-monitor').json()
    assert result['unauthorized_deploy'] is (not authorized)


@pytest.mark.parametrize('sha,source_ok', [(None, True), (SHA, False)])
def test_unknown_deploy_source_is_danger(client, monitor, sha, source_ok):
    state, _ = monitor
    state['vercel'] = (True, 'b'*40, sha, source_ok, ['unexpected source'], False)
    assert client.get('/tread-monitor').json()['unauthorized_deploy'] is True


def test_api_failure_is_explicit(client, monitor):
    state, _ = monitor
    state.update(api_error=True, hashes=None)
    result = client.get('/tread-monitor').json()
    assert result['ok'] is None
    assert result['error'] == 'github_unreachable'
    assert result['github_actions_error'] is True


def test_incoming_signal_is_visible_even_with_cached_result(client, monitor, app_module):
    _, kv = monitor
    client.get('/tread-monitor')
    kv[app_module._KV_DEPLOY_INCOMING] = {'sha': SHA}
    result = client.get('/tread-monitor').json()
    assert result['deploy_incoming'] is True
    assert result['deploy_incoming_sha'] == SHA
