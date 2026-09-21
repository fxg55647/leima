import hashlib
import io
import json
import time
import zipfile
from types import SimpleNamespace

import pytest


def download_package(client, session):
    response = client.get(f'/download/{session}/package.zip')
    assert response.status_code == 200
    return response.content


def unpack(zip_bytes):
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def repack(files, compresslevel=6):
    """Rebuild a ZIP from a {name: bytes} map, deliberately not matching the app's own
    member order or compression settings — used to prove the packer's ZIP shell doesn't
    matter, only the content bytes and the manifest's file hashes do."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED, compresslevel=compresslevel) as zf:
        for name in sorted(files):
            zf.writestr(name, files[name])
    return buf.getvalue()


def validate(client, zip_bytes):
    return client.post('/validate', files={'package_file': ('package.zip', zip_bytes, 'application/zip')})


@pytest.fixture
def stamp_factory(client, app_module, monkeypatch):
    """Mints one or more independently-verifiable stamps (distinct Arweave tx ids) in a
    single test — needed for bundle coverage, where the `stamped` fixture's single
    hardcoded tx id would make every package collide on the same mocked record."""
    monkeypatch.setattr(app_module, 'analyse', lambda *a, **k: {
        'passes': [('Supporting', 'The receipt says paid.'), ('Opposing', 'No signature.'),
                   ('Verdict', 'Payment is supported by the receipt.')],
        'summary_verdict': 'Payment supported.', 'verdict_category': 'Supported',
        'timestamp': '2026-01-01 00:00:00 UTC', 'prompt_log': [],
    })
    records = {}
    counter = iter(range(1, 1000))

    def upload(data, content_type, tags):
        tx_id = f'test-transaction-{next(counter)}'
        records[tx_id] = json.loads(data)
        return tx_id
    monkeypatch.setattr(app_module, '_irys_upload', upload)

    def get(url, **kwargs):
        tx_id = url.rsplit('/', 1)[-1]
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: records[tx_id])
    monkeypatch.setattr(app_module.http_requests, 'get', get)

    seen = set(app_module.store)

    def make(question='Was the invoice paid?', text='Receipt: invoice 42 paid in full.'):
        response = client.post('/ask', data={'active_tab': 'text', 'question': question, 'text_input': text})
        assert response.status_code == 200, response.text
        session = next(s for s in app_module.store if s not in seen)
        seen.add(session)
        assert client.post(f'/files/{session}').status_code == 200
        return session

    return make


def test_stamp_download_validate_roundtrip(client, stamped):
    session, records = stamped
    zip_bytes = download_package(client, session)
    files = unpack(zip_bytes)
    manifest = json.loads(files['manifest.json'])
    assert {k: v for k, v in manifest.items() if k != 'stamp'} == records['test-transaction']
    assert manifest['stamp_format_version'] == 2
    assert 'source-index.json' not in manifest['files']
    for name, expected in manifest['files'].items():
        assert expected == 'sha256:' + hashlib.sha256(files[name]).hexdigest()
    assert 'All checks passed' in validate(client, zip_bytes).text


def test_repacked_shell_with_same_content_still_validates(client, stamped):
    session, _ = stamped
    files = unpack(download_package(client, session))
    reshelled = repack(files, compresslevel=9)
    assert reshelled != download_package(client, session)  # different ZIP bytes, same content
    assert 'All checks passed' in validate(client, reshelled).text


@pytest.mark.parametrize('target', [
    'source.pdf', 'verdict.pdf', 'verdict.txt', 'verdict.html', 'verdict.json', 'manifest.json', 'chain',
])
def test_tampering_is_rejected(client, stamped, target):
    session, records = stamped
    files = unpack(download_package(client, session))
    if target == 'chain':
        records['test-transaction']['timestamp'] = 'altered'
    elif target == 'manifest.json':
        manifest = json.loads(files[target])
        manifest['timestamp'] = 'altered'
        files[target] = json.dumps(manifest).encode()
    else:
        files[target] += b'x'
    response = validate(client, repack(files))
    assert response.status_code == 200
    assert 'Validation failed' in response.text
    assert 'All checks passed' not in response.text


def test_missing_member_is_rejected(client, stamped):
    session, _ = stamped
    files = unpack(download_package(client, session))
    del files['verdict.txt']
    assert 'Validation failed' in validate(client, repack(files)).text


def test_extra_member_is_rejected(client, stamped):
    session, _ = stamped
    files = unpack(download_package(client, session))
    files['unexpected.txt'] = b'not part of the manifest'
    assert 'Validation failed' in validate(client, repack(files)).text


def test_duplicate_name_is_rejected(client, stamped):
    session, _ = stamped
    zip_bytes = download_package(client, session)
    files = unpack(zip_bytes)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
            if name == 'verdict.txt':
                zf.writestr(name, content)  # duplicate member
    assert 'Validation failed' in validate(client, buf.getvalue()).text


def test_path_traversal_name_is_rejected(client, stamped):
    session, _ = stamped
    files = unpack(download_package(client, session))
    files['../evil.txt'] = files.pop('verdict.txt')
    manifest = json.loads(files['manifest.json'])
    manifest['files']['../evil.txt'] = manifest['files'].pop('verdict.txt')
    files['manifest.json'] = json.dumps(manifest).encode()
    assert 'Validation failed' in validate(client, repack(files)).text


def test_wrong_stamp_format_version_is_rejected(client, stamped):
    session, _ = stamped
    files = unpack(download_package(client, session))
    manifest = json.loads(files['manifest.json'])
    manifest['stamp_format_version'] = 1
    files['manifest.json'] = json.dumps(manifest).encode()
    assert 'Validation failed' in validate(client, repack(files)).text


def test_malformed_manifest_types_are_rejected(client, stamped):
    session, _ = stamped
    files = unpack(download_package(client, session))
    manifest = json.loads(files['manifest.json'])
    manifest['files'] = 'not-an-object'
    files['manifest.json'] = json.dumps(manifest).encode()
    assert 'Validation failed' in validate(client, repack(files)).text


def test_corrupt_zip_is_rejected_cleanly(client):
    response = validate(client, b'this is not a zip file at all')
    assert response.status_code == 200
    assert 'Validation failed' in response.text


def test_gateway_failure_is_not_success(client, stamped, app_module, monkeypatch):
    def unavailable(*a, **k):
        raise TimeoutError('gateway timeout')
    monkeypatch.setattr(app_module.http_requests, 'get', unavailable)
    response = validate(client, download_package(client, stamped[0]))
    assert 'Validation failed' in response.text
    assert 'Fetch failed' in response.text


def test_expired_session_cannot_download_or_stamp(client):
    assert client.get('/download/missing/package.zip').status_code == 404
    assert client.post('/files/missing').status_code == 404


def test_unstamped_session_cannot_download_package(client, app_module):
    app_module.store['pending'] = {'manifest': {}, '_stored_at': time.time()}
    assert client.get('/download/pending/package.zip').status_code == 409


def test_stamp_retry_after_failure_succeeds_without_double_upload(client, app_module, monkeypatch):
    monkeypatch.setattr(app_module, 'analyse', lambda *a, **k: {
        'passes': [('Verdict', 'ok')], 'summary_verdict': 'ok', 'verdict_category': 'Supported',
        'timestamp': '2026-01-01 00:00:00 UTC', 'prompt_log': [],
    })
    calls = {'n': 0}

    def failing_upload(data, content_type, tags):
        calls['n'] += 1
        raise RuntimeError('network down')
    monkeypatch.setattr(app_module, '_irys_upload', failing_upload)

    response = client.post('/ask', data={'active_tab': 'text', 'question': 'q', 'text_input': 'some receipt text'})
    assert response.status_code == 200
    session = next(iter(app_module.store))

    assert client.get(f'/download/{session}/package.zip').status_code == 409
    first = client.post(f'/files/{session}')
    assert first.status_code == 503
    assert calls['n'] == 1
    assert client.get(f'/download/{session}/package.zip').status_code == 409  # still not stamped

    def succeeding_upload(data, content_type, tags):
        calls['n'] += 1
        return 'test-transaction'
    monkeypatch.setattr(app_module, '_irys_upload', succeeding_upload)

    second = client.post(f'/files/{session}')
    assert second.status_code == 200
    assert calls['n'] == 2
    assert client.get(f'/download/{session}/package.zip').status_code == 200

    third = client.post(f'/files/{session}')
    assert third.status_code == 200
    assert calls['n'] == 2  # already stamped: no second Arweave upload


def test_bundle_accepts_multiple_valid_packages(client, app_module, monkeypatch, stamp_factory):
    session_a = stamp_factory(text='Receipt A: invoice 42 paid in full.')
    session_b = stamp_factory(text='Receipt B: invoice 43 paid in full.')
    zip_a = download_package(client, session_a)
    zip_b = download_package(client, session_b)

    monkeypatch.setattr(app_module, 'analyse', lambda *a, **k: {
        'passes': [('Verdict', 'Both receipts are paid.')], 'summary_verdict': 'Both paid.',
        'verdict_category': 'Supported', 'timestamp': '2026-01-02 00:00:00 UTC', 'prompt_log': [],
    })
    response = client.post(
        '/ask', data={'active_tab': 'bundle', 'question': 'Are both invoices paid?'},
        files=[
            ('bundle_packages', ('a.zip', zip_a, 'application/zip')),
            ('bundle_packages', ('b.zip', zip_b, 'application/zip')),
        ],
    )
    assert response.status_code == 200
    assert 'error' not in response.text.lower()


def test_bundle_rejects_before_ai_call_on_invalid_package(client, app_module, monkeypatch, stamp_factory):
    session_a = stamp_factory()
    zip_a = download_package(client, session_a)
    called = {'n': 0}

    def analyse_spy(*a, **k):
        called['n'] += 1
        return {'passes': [], 'summary_verdict': '', 'verdict_category': '', 'timestamp': '', 'prompt_log': []}
    monkeypatch.setattr(app_module, 'analyse', analyse_spy)

    response = client.post(
        '/ask', data={'active_tab': 'bundle', 'question': 'q'},
        files=[
            ('bundle_packages', ('a.zip', zip_a, 'application/zip')),
            ('bundle_packages', ('b.zip', b'not a zip', 'application/zip')),
        ],
    )
    assert response.status_code == 200
    assert called['n'] == 0
    assert 'error' in response.text.lower()


def test_bundle_rejects_before_ai_call_on_unverifiable_anchor(client, app_module, monkeypatch, stamp_factory):
    session_a = stamp_factory()
    zip_a = download_package(client, session_a)

    def unavailable(*a, **k):
        raise TimeoutError('gateway timeout')
    monkeypatch.setattr(app_module.http_requests, 'get', unavailable)

    called = {'n': 0}

    def analyse_spy(*a, **k):
        called['n'] += 1
        return {'passes': [], 'summary_verdict': '', 'verdict_category': '', 'timestamp': '', 'prompt_log': []}
    monkeypatch.setattr(app_module, 'analyse', analyse_spy)

    response = client.post(
        '/ask', data={'active_tab': 'bundle', 'question': 'q'},
        files=[
            ('bundle_packages', ('a.zip', zip_a, 'application/zip')),
            ('bundle_packages', ('b.zip', zip_a, 'application/zip')),
        ],
    )
    assert response.status_code == 200
    assert called['n'] == 0
    assert 'error' in response.text.lower()


def test_correspondence_reports_missing_index_cleanly(client, stamped):
    session, _ = stamped
    zip_bytes = download_package(client, session)
    response = client.post('/check-correspondence', files={'package_file': ('package.zip', zip_bytes, 'application/zip')})
    assert response.status_code == 200
    assert 'not available' in response.text.lower()


def test_correspondence_rejects_package_with_bad_anchor(client, stamped):
    session, records = stamped
    zip_bytes = download_package(client, session)
    records['test-transaction']['timestamp'] = 'altered'
    response = client.post('/check-correspondence', files={'package_file': ('package.zip', zip_bytes, 'application/zip')})
    assert response.status_code == 200
    assert 'anchor could not be verified' in response.text.lower()


def test_anchor_check_does_not_crash_on_non_dict_stamp(app_module):
    # Defense in depth: evidence_package.read() already rejects a non-object `stamp`
    # field, but _check_arweave_anchor must never assume its input already went through
    # that validation (a `manifest.get("stamp") or {}` pattern crashes on a truthy
    # non-dict stamp, e.g. a string, since strings have no .get()).
    result = app_module._check_arweave_anchor({'stamp': 'not-an-object'})
    assert result['ok'] is False
    result = app_module._check_arweave_anchor({})
    assert result['ok'] is False
