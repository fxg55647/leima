import json

import pytest

KEY = 'test-mcp-key'


def rpc(method, params=None, msg_id=1):
    message = {'jsonrpc': '2.0', 'id': msg_id, 'method': method}
    if params is not None:
        message['params'] = params
    return message


@pytest.fixture
def mcp(client, app_module, monkeypatch):
    monkeypatch.setenv('LEIMA_MCP_KEYS', f'other-key, {KEY}')
    calls = []
    def analyse(question, contents, source_context=None):
        calls.append({'question': question, 'contents': contents, 'source_context': source_context})
        return {
            'passes': [('Supporting', 'The text says paid.'), ('Opposing', 'No signature.'),
                       ('Verdict', 'Supported.')],
            'summary_verdict': 'Payment supported.', 'verdict_category': 'Supported',
            'timestamp': '2026-01-01 00:00:00 UTC', 'prompt_log': [],
        }
    monkeypatch.setattr(app_module, 'analyse', analyse)
    uploads = []
    def upload(data, content_type, tags):
        uploads.append(json.loads(data))
        return 'mcp-tx'
    monkeypatch.setattr(app_module, '_irys_upload', upload)

    def post(message, auth=f'Bearer {KEY}', **kwargs):
        headers = {'Authorization': auth} if auth else {}
        return client.post('/mcp', json=message, headers=headers, **kwargs)
    post.calls = calls
    post.uploads = uploads
    return post


def test_disabled_without_configured_keys(client, monkeypatch):
    monkeypatch.delenv('LEIMA_MCP_KEYS', raising=False)
    assert client.post('/mcp', json=rpc('tools/list')).status_code == 503


def test_rejects_missing_or_wrong_key(mcp):
    assert mcp(rpc('tools/list'), auth=None).status_code == 401
    assert mcp(rpc('tools/list'), auth='Bearer nope').status_code == 401


def test_key_in_query_string(client, mcp):
    assert client.post(f'/mcp?key={KEY}', json=rpc('tools/list')).status_code == 200


def test_initialize_and_tools_list(mcp):
    init = mcp(rpc('initialize', {'protocolVersion': '2025-06-18', 'capabilities': {},
                                  'clientInfo': {'name': 't', 'version': '1'}})).json()
    assert init['result']['protocolVersion'] == '2025-06-18'
    assert 'tools' in init['result']['capabilities']
    assert mcp({'jsonrpc': '2.0', 'method': 'notifications/initialized'}).status_code == 202
    tools = mcp(rpc('tools/list')).json()['result']['tools']
    assert [t['name'] for t in tools] == ['stamp_citation']


def test_unknown_protocol_version_falls_back_to_latest(mcp):
    init = mcp(rpc('initialize', {'protocolVersion': '1999-01-01'})).json()
    assert init['result']['protocolVersion'] == '2025-06-18'


def test_unknown_method_and_batch(mcp):
    assert mcp(rpc('resources/list')).json()['error']['code'] == -32601
    assert mcp([rpc('ping')]).status_code == 400


def test_get_is_not_supported(client):
    assert client.get('/mcp').status_code == 405


def test_stamp_citation_with_agent_supplied_text(mcp):
    response = mcp(rpc('tools/call', {'name': 'stamp_citation', 'arguments': {
        'claim': 'Invoice 42 was paid.', 'source_text': 'Receipt: invoice 42 paid in full.',
        'source_title': 'Receipt 42',
    }})).json()
    result = response['result']
    assert result['isError'] is False
    data = result['structuredContent']
    assert json.loads(result['content'][0]['text']) == data
    assert data['claim'] == 'Invoice 42 was paid.'
    assert data['source']['provenance'] == 'agent_supplied'
    assert data['verdict']['nature'] == 'ai_assessment'
    assert data['verdict']['category'] == 'Supported'
    assert data['evidence']['nature'] == 'hash_commitment'
    assert data['evidence']['arweave_tx'] == 'mcp-tx'
    assert data['citation'].startswith('Receipt 42 (submitted 2026-01-01).')
    assert len(mcp.uploads) == 1
    # Arweave gets the hash record only — never the claim or the source text.
    uploaded = json.dumps(mcp.uploads[0])
    assert 'Invoice 42 was paid' not in uploaded
    assert 'paid in full' not in uploaded


def test_stamp_citation_fetches_url_and_hashes_cited_passage(mcp, app_module, monkeypatch):
    fetched = []
    def fetch(url):
        fetched.append(url)
        html = '<html><body>Invoice 42 paid in full.</body></html>'
        return b'%PDF-fake', 'Invoice 42 paid in full.', url, '2026-01-01 00:00:00 UTC', html
    monkeypatch.setattr(app_module, '_fetch_webpage', fetch)
    data = mcp(rpc('tools/call', {'name': 'stamp_citation', 'arguments': {
        'claim': 'Invoice 42 was paid.', 'source_url': 'https://example.com/receipt',
        'source_text': 'paid in full',
    }})).json()['result']['structuredContent']
    assert fetched == ['https://example.com/receipt']
    assert data['source']['provenance'] == 'fetched_by_leima'
    assert data['source']['cited_passage'] == 'paid in full'
    assert 'paid in full' in mcp.calls[0]['question']
    assert mcp.calls[0]['source_context']['type'] == 'web'


@pytest.mark.parametrize('arguments, message', [
    ({'source_text': 'x'}, 'claim is required'),
    ({'claim': 'x'}, 'source_url'),
    ({'claim': 'x', 'source_url': 'file:///etc/passwd'}, 'http(s)'),
])
def test_stamp_citation_tool_errors(mcp, arguments, message):
    result = mcp(rpc('tools/call', {'name': 'stamp_citation', 'arguments': arguments})).json()['result']
    assert result['isError'] is True
    assert message in result['content'][0]['text']
    assert mcp.uploads == []
