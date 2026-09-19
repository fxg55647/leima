import hashlib
import io
import json
import zipfile
import pytest


def downloads(client, session):
    response = client.get(f'/download/{session}/all.zip')
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def validate(client, files):
    return client.post('/validate', files={
        'source_file': ('source.pdf', files['source.pdf']),
        'verdict_file': ('verdict.pdf', files['verdict.pdf']),
        'manifest_file': ('manifest.json', files['manifest.json']),
    })


def test_stamp_download_validate_roundtrip(client, stamped):
    session, records = stamped
    files = downloads(client, session)
    manifest = json.loads(files['manifest.json'])
    assert {k: v for k, v in manifest.items() if k != 'stamp'} == records['test-transaction']
    for fmt in ('pdf', 'txt', 'html', 'json'):
        content = files[f'verdict.{fmt}']
        assert manifest['verdict_formats'][fmt] == 'sha256:' + hashlib.sha256(content).hexdigest()
        assert client.get(f'/download/{session}/verdict.{fmt}').content == content
    assert 'All checks passed' in validate(client, files).text


@pytest.mark.parametrize('target', ['source.pdf', 'verdict.pdf', 'manifest.json', 'chain'])
def test_tampering_is_rejected(client, stamped, target):
    session, records = stamped
    files = downloads(client, session)
    if target == 'chain':
        records['test-transaction']['timestamp'] = 'altered'
    elif target == 'manifest.json':
        manifest = json.loads(files[target])
        manifest['timestamp'] = 'altered'
        files[target] = json.dumps(manifest).encode()
    else:
        files[target] += b'x'
    response = validate(client, files)
    assert response.status_code == 200
    assert 'Validation failed' in response.text
    assert 'All checks passed' not in response.text


def test_gateway_failure_is_not_success(client, stamped, app_module, monkeypatch):
    def unavailable(*a, **k):
        raise TimeoutError('gateway timeout')
    monkeypatch.setattr(app_module.http_requests, 'get', unavailable)
    response = validate(client, downloads(client, stamped[0]))
    assert 'Validation failed' in response.text
    assert 'Fetch failed' in response.text


def test_expired_session_cannot_download_or_stamp(client):
    assert client.get('/download/missing/all.zip').status_code == 404
    assert client.post('/files/missing').status_code == 404
