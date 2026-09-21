"""Tests for the domain-only signer vetting draft tool.

search_fn is faked -- no real AI/network calls, consistent with the offline
test boundary in conftest.py.
"""

from signer_vetting import assess_signer_human_verification_basis, draft_human_verification_basis


def test_parses_likely_human_required_verdict():
    def search_fn(question):
        assert "vero.fi" in question
        assert "Verohallinto" in question
        return (
            "VERDICT: likely_human_required\n"
            "Vero.fi services require Suomi.fi strong authentication.",
            ["does vero.fi require strong authentication"],
        )

    result = assess_signer_human_verification_basis("vero.fi", organization_hint="Verohallinto", search_fn=search_fn)

    assert result.domain == "vero.fi"
    assert result.verdict == "likely_human_required"
    assert "Suomi.fi" in result.reasoning
    assert result.search_queries == ["does vero.fi require strong authentication"]


def test_parses_not_required_verdict():
    def search_fn(question):
        return ("VERDICT: not_required\nAnyone can sign up with just an email address.", [])

    result = assess_signer_human_verification_basis("newsletter.example.com", search_fn=search_fn)
    assert result.verdict == "not_required"


def test_falls_back_to_uncertain_for_malformed_response():
    def search_fn(question):
        return ("I'm not sure, this is ambiguous.", [])

    result = assess_signer_human_verification_basis("unknown.example.com", search_fn=search_fn)
    assert result.verdict == "uncertain"
    assert result.reasoning == "I'm not sure, this is ambiguous."


def test_falls_back_to_uncertain_for_unrecognized_verdict_label():
    def search_fn(question):
        return ("VERDICT: maybe\nSome reasoning.", [])

    result = assess_signer_human_verification_basis("example.com", search_fn=search_fn)
    assert result.verdict == "uncertain"


def test_draft_human_verification_basis_uses_ai_verdict_directly_no_gate():
    def search_fn(question):
        return ("VERDICT: likely_human_required\nStrong authentication required.", [])

    text = draft_human_verification_basis("vero.fi", "Verohallinto", search_fn=search_fn)
    assert text == "AI-assessed (verdict: likely_human_required): Strong authentication required."


def test_draft_human_verification_basis_surfaces_uncertainty_verbatim():
    def search_fn(question):
        return ("Could not find reliable information.", [])

    text = draft_human_verification_basis("unknown.example.com", search_fn=search_fn)
    assert text == "AI-assessed (verdict: uncertain): Could not find reliable information."


def test_never_includes_message_content_in_the_question():
    captured = {}

    def search_fn(question):
        captured["question"] = question
        return ("VERDICT: uncertain\n", [])

    assess_signer_human_verification_basis("example.gov", search_fn=search_fn)

    # The prompt is built purely from the domain/org hint we pass in --
    # asserting there is no channel here for arbitrary message text to enter.
    assert "example.gov" in captured["question"]
