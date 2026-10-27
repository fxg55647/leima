from types import SimpleNamespace
import pytest
from google.genai import errors
import neutral_witness


def _api_error(code):
    cls = errors.ServerError if code >= 500 else errors.ClientError
    return cls(code, {'error': {'code': code, 'message': 'boom', 'status': 'X'}})


def _client(outcomes, calls):
    outcomes = iter(outcomes)
    def generate(**kwargs):
        calls.append(kwargs)
        item = next(outcomes)
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(text=item)
    return SimpleNamespace(models=SimpleNamespace(generate_content=generate))


@pytest.fixture
def sleeps(monkeypatch):
    slept = []
    monkeypatch.setattr(neutral_witness.time, 'sleep', slept.append)
    return slept


@pytest.mark.parametrize('code', [429, 500, 503])
def test_transient_error_is_retried(sleeps, code):
    calls = []
    client = _client([_api_error(code), 'ok'], calls)
    resp = neutral_witness._generate(client, model='m', contents='x')
    assert resp.text == 'ok'
    assert len(calls) == 2
    assert len(sleeps) == 1 and 1.0 <= sleeps[0] <= 1.5


def test_gives_up_after_three_attempts(sleeps):
    calls = []
    client = _client([_api_error(503)] * 3, calls)
    with pytest.raises(errors.APIError) as exc:
        neutral_witness._generate(client, model='m', contents='x')
    assert exc.value.code == 503
    assert len(calls) == 3
    assert len(sleeps) == 2
    assert 3.0 <= sleeps[1] <= 3.5
    assert sum(sleeps) <= 5.0


@pytest.mark.parametrize('code', [402, 400, 403])
def test_non_transient_error_is_not_retried(sleeps, code):
    calls = []
    client = _client([_api_error(code), 'ok'], calls)
    with pytest.raises(errors.APIError) as exc:
        neutral_witness._generate(client, model='m', contents='x')
    assert exc.value.code == code
    assert len(calls) == 1
    assert sleeps == []


def test_other_exceptions_are_not_retried(sleeps):
    calls = []
    client = _client([RuntimeError('network'), 'ok'], calls)
    with pytest.raises(RuntimeError):
        neutral_witness._generate(client, model='m', contents='x')
    assert len(calls) == 1 and sleeps == []


def test_analyse_survives_transient_503(monkeypatch, sleeps):
    calls = []
    client = _client(['SUPPORT', _api_error(503), 'OPPOSITION',
                      'CATEGORY: Mostly matches\nVERDICT: Paid.\nBody.'], calls)
    monkeypatch.setattr(neutral_witness, '_get_client', lambda: client)
    result = neutral_witness.analyse('Was it paid?', ['Receipt'])
    assert len(calls) == 4
    assert result['summary_verdict'] == 'Paid.'
    assert len(sleeps) == 1


def test_analyse_code_review_retries_429(monkeypatch, sleeps):
    calls = []
    client = _client([_api_error(429), '1. PASS ok\nOVERALL: COMPLIANT'], calls)
    monkeypatch.setattr(neutral_witness, '_get_client', lambda: client)
    result = neutral_witness.analyse_code_review('code', 'rules', 'r/r', 'a' * 40)
    assert result['compliant'] is True
    assert len(calls) == 2


def test_analyse_retries_synthesis_503(monkeypatch, sleeps):
    calls = []
    client = _client(['SUPPORT', 'OPPOSITION', _api_error(503),
                      'CATEGORY: Mostly matches\nVERDICT: Paid.\nBody.'], calls)
    monkeypatch.setattr(neutral_witness, '_get_client', lambda: client)
    result = neutral_witness.analyse('Was it paid?', ['Receipt'])
    assert len(calls) == 4
    assert calls[2] == calls[3]
    assert result['summary_verdict'] == 'Paid.'
