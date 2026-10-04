import hashlib
import json
from pathlib import Path

import pytest

from research.build import build, validate, web_view, review_fingerprint, review_state, text_view

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
