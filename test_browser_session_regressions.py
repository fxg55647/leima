import io
import json
import zipfile
import pytest
import browser_session as evidence
from test_browser_session import _build_screenshot_package, _pack_zip, _sha256, _image_bytes


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def altered(*, metadata=None, manifest=None):
    with zipfile.ZipFile(io.BytesIO(_build_screenshot_package())) as source:
        files = {name: source.read(name) for name in source.namelist()}
    if metadata:
        meta = json.loads(files['metadata.json'])
        replacement = metadata(meta)
        files['metadata.json'] = json.dumps(meta if replacement is None else replacement).encode()
    mf = json.loads(files['manifest.json'])
    mf['files']['metadata.json'] = _sha256(files['metadata.json'])
    if manifest:
        replacement = manifest(mf)
        if replacement is not None:
            mf = replacement
    files['manifest.json'] = json.dumps(mf).encode()
    files['manifest.sha256'] = (_sha256(files['manifest.json']) + '  manifest.json\n').encode()
    return _pack_zip(files)


@pytest.mark.parametrize('files', [{}, {'metadata.json': '0'*64}, {'screenshot.png': '0'*64}, [], {'screenshot.png': 3, 'metadata.json': '0'*64}])
def test_requires_both_valid_hash_entries(files):
    with pytest.raises(ValueError):
        evidence.parse_and_verify(altered(manifest=lambda m: m.update(files=files)))


@pytest.mark.parametrize('changes', [
    {'title': 'hidden name'}, {'sensorsAtRequest': {}}, {'sensorsAtCompletion': {}},
    {'url': 'https://bank.example/account'}, {'url': 'https://user:secret@bank.example'},
    {'privacy': []}, {'edits': []}, {'edits': {'version': []}}, {'url': None},
])
def test_invalid_metadata_is_controlled_rejection(changes):
    with pytest.raises(ValueError):
        evidence.parse_and_verify(altered(metadata=lambda m: m.update(changes)))


@pytest.mark.parametrize('part', ['metadata', 'manifest'])
def test_top_level_array_is_rejected(part):
    with pytest.raises(ValueError):
        evidence.parse_and_verify(altered(**{part: lambda m: []}))


def test_declared_hash_does_not_make_non_image_valid():
    result = evidence.parse_and_verify(_build_screenshot_package(png=b'not a PNG'))
    assert not result.integrity.ok


def test_actual_pixel_dimensions_must_match():
    result = evidence.parse_and_verify(_build_screenshot_package(png=_image_bytes('PNG', (1, 1))))
    assert not result.integrity.ok
    assert any('Actual image dimensions' in e for e in result.integrity.errors)


@pytest.mark.anyio
async def test_body_limit_before_multipart_processing(monkeypatch):
    monkeypatch.setattr(evidence, 'MAX_ZIP_BYTES', 10)
    called = False
    async def app(scope, receive, send):
        nonlocal called
        called = True
    messages = iter([
        {'type': 'http.request', 'body': b'a' * (1024*1024), 'more_body': True},
        {'type': 'http.request', 'body': b'b' * 11, 'more_body': True},
    ])
    sent = []
    async def receive():
        return next(messages)
    async def send(message):
        sent.append(message)
    await evidence.EvidenceBodyLimitMiddleware(app)(
        {'type': 'http', 'method': 'POST', 'path': '/api/evidence/browser-sessions'}, receive, send)
    assert not called
    assert sent[0]['status'] == 413


@pytest.mark.anyio
async def test_endpoint_rejects_malformed_metadata():
    from main import app
    from httpx import AsyncClient, ASGITransport
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/api/evidence/browser-sessions', files={
            'package': ('evidence.zip', altered(metadata=lambda m: m.update(edits=[])), 'application/zip')})
    assert response.status_code == 422
