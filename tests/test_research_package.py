import hashlib
import json
from pathlib import Path

import pytest

from research.build import build, validate, web_view, review_fingerprint, review_state, text_view, assessment_state

EXAMPLE = Path(__file__).resolve().parents[1] / "research/example/research.json"


def sample():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("mutation", [
    lambda d: d['claims'][0]['depends_on'].append('missing'),
    lambda d: d['claims'][0]['depends_on'].append('C2'),
    lambda d: d['claims'][0].update(evidence=[]),
    lambda d: d['sources'][0].update(access='restricted'),
    lambda d: d['sources'][0].update(url='javascript:alert(1)'),
    lambda d: d['stamps'][0].update(permanent=True),
    lambda d: d['game']['scenes'][0]['choices'][0].update(claim='missing'),
])
def test_invalid_research_is_rejected(mutation):
    data = sample()
    mutation(data)
    with pytest.raises(ValueError):
        validate(data)


def test_html_escapes_authored_text():
    data = sample()
    data['claims'][0]['text'] = '<script>alert(1)</script>'
    assert '<script>' not in web_view(data)
    assert '&lt;script&gt;' in web_view(data)


def test_release_is_deterministic_and_links_resolve(tmp_path):
    first = build(EXAMPLE, tmp_path / 'a')
    second = build(EXAMPLE, tmp_path / 'b')
    assert first == second
    manifest = json.loads(first['release-manifest.json'])
    for name, sha in manifest['files'].items():
        assert hashlib.sha256(first[name]).hexdigest() == sha
    crate = json.loads(first['ro-crate-metadata.json'])
    ids = {entity['@id'] for entity in crate['@graph']}
    def check(value):
        if isinstance(value, dict):
            if '@id' in value and value['@id'].startswith('#'):
                assert value['@id'] in ids
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)
    check(crate)


def test_new_topic_keeps_hypotheses_open():
    path = EXAMPLE.parents[1] / 'japan-americas/research.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    validate(data)
    assert all(c['status'] == 'open' and not c['evidence'] for c in data['claims'])
    assert data['stamps'] == []


def reviewed_sample():
    data = sample()
    target = {'kind': 'claim', 'id': 'C1'}
    review = {'id': 'K1', 'target': target, 'type': 'reasoning', 'priority': 1,
              'text': 'Check interpretation', 'basis': 'Distinguish quote from inference',
              'author': {'kind': 'human', 'name': 'Test reviewer'},
              'reviewed_version': data['version'], 'reviewed_target_sha256': review_fingerprint(data, target),
              'sources': ['S1'], 'response': 'Retained exact wording',
              'resolution': {'status': 'accepted', 'rationale': 'Quote checked', 'changes': 'Wording retained'}}
    data['criticisms'] = [review]
    return data, review


def assessed_sample():
    data = sample()
    target = {'kind': 'claim', 'id': 'C1'}
    record = {'id': 'R1', 'target': target, 'date': '2026-10-04',
              'author': {'kind': 'agent', 'name': 'Test reviewer', 'model': 'unknown'},
              'reviewed_version': data['version'], 'reviewed_commit': 'a' * 40,
              'reviewed_target_sha256': review_fingerprint(data, target),
              'verification': {'level': 'report', 'scope': '<C1 report>', 'limitations': 'Sources not read'},
              'outcome': 'no_findings', 'summary': 'No issues within scope', 'criticisms': []}
    data['reviews'] = [record]
    return data, record


def test_no_findings_review_is_exported_without_invented_criticism(tmp_path):
    data, record = assessed_sample()
    validate(data)
    assert not data.get('criticisms')
    path = tmp_path / 'research.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    files = build(path, tmp_path / 'out')
    assert files == build(path, tmp_path / 'again')
    for name in ('article.md', 'audit.md', 'ro-crate-metadata.json'):
        assert b'No issues within scope' in files[name]
        assert b'Sources not read' in files[name]
        assert record['reviewed_commit'].encode() in files[name]
    assert b'&lt;C1 report&gt;' in files['index.html']
    assert b'<C1 report>' not in files['index.html']
    graph = {e['@id']: e for e in json.loads(files['ro-crate-metadata.json'])['@graph']}
    assert graph['#R1']['about'] == {'@id': '#C1'}
    assert graph['#R1']['citation'] == []


def test_review_basis_change_preserves_original_result():
    data, record = assessed_sample()
    assert assessment_state(data, record) == 'current'
    data['claims'][1]['text'] += ' unrelated'
    assert assessment_state(data, record) == 'current'
    data['sources'][0]['quote'] += ' changed'
    validate(data)
    assert assessment_state(data, record) == 'needs_reassessment'
    assert record['outcome'] == 'no_findings'
    assert 'needs_reassessment' in text_view(data)
    assert 'needs_reassessment' in web_view(data)


@pytest.mark.parametrize('field,value', [
    ('id', 'C1'), ('date', '2026-02-30'), ('reviewed_commit', 'abc'),
    ('reviewed_target_sha256', 'abc'), ('verification', None), ('outcome', 'approved'),
    ('outcome', 'findings'), ('criticisms', ['missing']), ('summary', ''),
    ('target', {'kind': 'claim', 'id': 'missing'}),
    ('author', {'kind': 'agent', 'name': 'Agent'})])
def test_invalid_review_is_rejected(field, value):
    data, record = assessed_sample()
    record[field] = value
    with pytest.raises(ValueError):
        validate(data)


def test_findings_require_matching_criticism_and_no_findings_rejects_it():
    data, record = assessed_sample()
    _, criticism = reviewed_sample()
    data['criticisms'] = [criticism]
    record.update(outcome='findings', criticisms=['K1'])
    validate(data)
    record['outcome'] = 'no_findings'
    with pytest.raises(ValueError):
        validate(data)
    record['outcome'] = 'findings'
    criticism['target'] = {'kind': 'claim', 'id': 'C2'}
    with pytest.raises(ValueError):
        validate(data)


def test_inconclusive_review_and_legacy_package_remain_valid():
    data, record = assessed_sample()
    record['outcome'] = 'inconclusive'
    validate(data)
    assert 'Tarkastus jäi avoimeksi' in text_view(data)
    validate(sample())
    assert '## Kirjatut arvioinnit' not in text_view(sample())


@pytest.mark.parametrize('level', ['report', 'source_check', 'rerun'])
def test_verification_scope_survives_exports_and_is_escaped(tmp_path, level):
    data, review = reviewed_sample()
    review['verification'] = {'level': level, 'scope': '<Checked S1>',
                             'limitations': 'C2 remains unchecked'}
    validate(data)
    path = tmp_path / 'research.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    result = build(path, tmp_path / 'out')
    for name in ('article.md', 'audit.md', 'ro-crate-metadata.json'):
        assert b'<Checked S1>' in result[name]
        assert b'C2 remains unchecked' in result[name]
    assert b'&lt;Checked S1&gt;' in result['index.html']
    assert b'<Checked S1>' not in result['index.html']
    assert review_state(data, review) == 'accepted'


def test_missing_verification_is_explicit_not_assumed():
    data, _ = reviewed_sample()
    validate(data)
    assert 'Tarkastuksen syvyys: ei kirjattu' in text_view(data, True)
    assert 'Tarkastuksen syvyys: ei kirjattu' in web_view(data)


@pytest.mark.parametrize('record', [None, {}, {'level': 'verified'},
    {'level': 'report', 'scope': '', 'limitations': 'Unknown'},
    {'level': 'source_check', 'scope': 'S1', 'limitations': ''}])
def test_invalid_verification_is_rejected(record):
    data, review = reviewed_sample()
    review['verification'] = record
    with pytest.raises(ValueError):
        validate(data)


@pytest.mark.parametrize('change', ['claim', 'source', 'method'])
def test_changed_basis_reopens_review_without_erasing_decision(change):
    data, review = reviewed_sample()
    assert review_state(data, review) == 'accepted'
    if change == 'claim':
        data['claims'][0]['text'] += ' Changed'
    elif change == 'source':
        data['sources'][0]['quote'] += ' Changed'
    else:
        data['method'] += ' Changed'
    validate(data)
    assert review_state(data, review) == 'needs_reassessment'
    assert review['resolution']['status'] == 'accepted'
    assert 'needs_reassessment' in text_view(data, True)
    assert 'needs_reassessment' in web_view(data)


def test_unrelated_claim_edit_does_not_reopen_review():
    data, review = reviewed_sample()
    data['claims'][1]['text'] += ' unrelated edit'
    assert review_state(data, review) == 'accepted'


@pytest.mark.parametrize('change', ['target', 'source', 'decision', 'duplicate'])
def test_invalid_criticism_is_rejected(change):
    data, review = reviewed_sample()
    if change == 'target':
        review['target']['id'] = 'missing'
    elif change == 'source':
        review['sources'] = ['missing']
    elif change == 'decision':
        review['resolution']['rationale'] = ''
    else:
        review['id'] = 'C1'
    with pytest.raises(ValueError):
        validate(data)


def activity_sample():
    data = sample()
    data['actors'] = [{'id': 'P1', 'kind': 'human', 'name': '<Reviewer>'}]
    data['activities'] = [{'id': 'W1', 'kind': 'human_decision', 'actor': 'P1',
                           'date': '2026-10-04', 'description': '<Decision>', 'rationale': 'Scope chosen',
                           'inputs': ['S1'], 'outputs': ['C1'],
                           'tool': {'name': 'Editor', 'version': '1'}}]
    return data


@pytest.mark.parametrize('change', ['actor', 'input', 'output', 'human', 'date', 'duplicate', 'tool'])
def test_invalid_activity_rejected(change):
    data = activity_sample()
    activity = data['activities'][0]
    if change == 'actor':
        activity['actor'] = 'missing'
    elif change in ('input', 'output'):
        activity[change + 's'] = ['missing']
    elif change == 'human':
        data['actors'][0]['kind'] = 'agent'
    elif change == 'date':
        activity['date'] = 'yesterday'
    elif change == 'duplicate':
        activity['id'] = 'C1'
    else:
        activity['tool']['version'] = 7
    with pytest.raises(ValueError):
        validate(data)


def test_activity_graph_and_rendering(tmp_path):
    data = activity_sample()
    validate(data)
    assert '<Decision>' not in web_view(data)
    assert '&lt;Decision&gt;' in web_view(data)
    assert 'Scope chosen' in text_view(data, True)
    path = tmp_path / 'input.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    first = build(path, tmp_path / 'a')
    assert first == build(path, tmp_path / 'b')
    graph = {e['@id']: e for e in json.loads(first['ro-crate-metadata.json'])['@graph']}
    activity = graph['#W1']
    assert activity['@type'] == 'ChooseAction'
    assert activity['agent'] == {'@id': '#P1'}
    assert activity['object'] == [{'@id': '#S1'}]
    assert activity['result'] == [{'@id': '#C1'}]
    assert graph[activity['instrument']['@id']]['softwareVersion'] == '1'
    assert graph['#P1']['@type'] == 'Person'
