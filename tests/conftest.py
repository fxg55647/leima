"""Offline test boundary. Never load developer credentials or call real services."""
import os
import socket
import pytest
import requests

os.environ['PYTHON_DOTENV_DISABLED'] = '1'


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError('Unexpected external service call in offline test')
    monkeypatch.setattr(requests.sessions.Session, 'request', blocked)
    original_connect = socket.socket.connect
    def connect(sock, address):
        if isinstance(address, tuple) and address[0] not in ('127.0.0.1', '::1', 'localhost'):
            blocked()
        return original_connect(sock, address)
    monkeypatch.setattr(socket.socket, 'connect', connect)


@pytest.fixture
def app_module(monkeypatch):
    import main
    monkeypatch.setattr(main, 'store', {})
    monkeypatch.setattr(main, '_tread_cache', None)
    monkeypatch.setattr(main, '_kv_get', lambda *a, **k: None)
    monkeypatch.setattr(main, '_kv_set', lambda *a, **k: None)
    return main


@pytest.fixture
def client(app_module):
    from fastapi.testclient import TestClient
    with TestClient(app_module.app) as client:
        yield client


@pytest.fixture
def stamped(client, app_module, monkeypatch):
    """Real analysis/export/stamp pipeline, fake only AI and Irys boundaries."""
    monkeypatch.setattr(app_module, 'analyse', lambda *a, **k: {
        'passes': [('Supporting', 'The receipt says paid.'), ('Opposing', 'No signature.'),
                   ('Verdict', 'Payment is supported by the receipt.')],
        'summary_verdict': 'Payment supported.', 'verdict_category': 'Supported',
        'timestamp': '2026-01-01 00:00:00 UTC', 'prompt_log': [],
    })
    records = {}
    def upload(data, content_type, tags):
        import json
        records['test-transaction'] = json.loads(data)
        return 'test-transaction'
    monkeypatch.setattr(app_module, '_irys_upload', upload)
    response = client.post('/ask', data={
        'active_tab': 'text', 'question': 'Was the invoice paid?',
        'text_input': 'Receipt: invoice 42 paid in full.',
    })
    assert response.status_code == 200
    assert len(app_module.store) == 1, response.text
    session = next(iter(app_module.store))
    assert client.post(f'/files/{session}').status_code == 200
    from types import SimpleNamespace
    def get(url, **kwargs):
        assert url == app_module.IRYS_GATEWAY + '/test-transaction'
        return SimpleNamespace(raise_for_status=lambda: None,
                               json=lambda: records['test-transaction'])
    monkeypatch.setattr(app_module.http_requests, 'get', get)
    return session, records
