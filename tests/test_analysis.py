from types import SimpleNamespace
import pytest
import neutral_witness


def test_independent_passes_and_synthesis(monkeypatch):
    calls = []
    replies = iter(['SUPPORT_MARKER', 'OPPOSITION_MARKER',
                    'CATEGORY: Supported\nVERDICT: Supported by receipt.\nReasoned synthesis.'])
    def generate(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(text=next(replies))
    monkeypatch.setattr(neutral_witness, '_get_client', lambda: SimpleNamespace(
        models=SimpleNamespace(generate_content=generate)))
    result = neutral_witness.analyse('Was it paid?', ['Receipt: paid'])
    assert len(calls) == 3
    assert 'SUPPORT_MARKER' not in calls[1]['config'].system_instruction
    assert 'SUPPORT_MARKER' in calls[2]['config'].system_instruction
    assert 'OPPOSITION_MARKER' in calls[2]['config'].system_instruction
    assert all(call['contents'] == ['Receipt: paid'] for call in calls)
    assert result['summary_verdict'] == 'Supported by receipt.'
    assert len(result['passes']) == 3


def test_rejected_document_stops_pipeline(monkeypatch):
    calls = []
    def generate(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(text='REJECTED: unsupported document')
    monkeypatch.setattr(neutral_witness, '_get_client', lambda: SimpleNamespace(
        models=SimpleNamespace(generate_content=generate)))
    with pytest.raises(ValueError, match='REJECTED'):
        neutral_witness.analyse('Claim', ['Document'])
    assert len(calls) == 1
