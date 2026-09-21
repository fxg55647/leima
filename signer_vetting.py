"""AI-assisted, search-grounded drafting tool for a policy's
human_verification_basis (docs/todo/HISTORICAL_EMAIL_PROOF_PLAN.md section 9.1:
"valitaan yksi hyväksyttävä viestiluokka").

This looks at a DKIM signing DOMAIN only -- never at any individual message's
content, subject, or body. Message content is attacker-influenceable even
inside a validly DKIM-signed email (a legitimate sender can echo back a
free-text field the sender supplied), so any per-message AI judgment would be
a prompt-injection surface. Researching an organization's own known
registration process, using its name and domain rather than message text, does
not have that problem.

This is not part of the per-message issuance or verification path -- it runs
once when a policy is authored, not per credential. There is no human review
gate: the verdict is the best available machine judgment and is used
directly as the policy's human_verification_basis text. Per Leima's
two-layer model, this stays a soft, practical-guidance judgment -- it never
substitutes for or overrides the hard cryptographic checks (DKIM validity,
approved signer, signed message class, cutoff, email binding) in
historical_email_proof.py, which remain the hard guarantee regardless of
what this function concludes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

SearchFn = Callable[[str], tuple[str, list[str]]]

VALID_VERDICTS = ("likely_human_required", "not_required", "uncertain")


@dataclass
class SignerVettingResult:
    domain: str
    verdict: str  # one of VALID_VERDICTS
    reasoning: str
    search_queries: list[str] = field(default_factory=list)


def _default_search(question: str) -> tuple[str, list[str]]:
    from google.genai import types
    from neutral_witness import MODEL, _get_client

    client = _get_client()
    resp = client.models.generate_content(
        model=MODEL,
        contents=question,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
        ),
    )
    text = (resp.text or "").strip()
    queries: list[str] = []
    try:
        gm = resp.candidates[0].grounding_metadata
        if gm and gm.web_search_queries:
            queries = list(gm.web_search_queries)
    except Exception:
        pass
    return text, queries


def assess_signer_human_verification_basis(
    domain: str,
    organization_hint: str = "",
    search_fn: SearchFn = _default_search,
) -> SignerVettingResult:
    subject = f"the domain '{domain}'"
    if organization_hint:
        subject += f" (organization: {organization_hint})"

    question = (
        f"Research {subject} as an email sender. Does registering for an "
        "account with this sender, or being sent an official notification by "
        "it, typically require the recipient to have already proven their "
        "real-world identity to a human or a regulated process -- for example "
        "a bank's strong customer authentication, a government-issued ID "
        "check, or an in-person verification step? Could a script or bot "
        "instead obtain such a notification at scale without a real person "
        "behind it? Respond with the first line exactly one of "
        "'VERDICT: likely_human_required', 'VERDICT: not_required', or "
        "'VERDICT: uncertain', then on the following lines explain your "
        "reasoning and cite what you found."
    )
    text, queries = search_fn(question)

    verdict = "uncertain"
    reasoning = text
    if text.startswith("VERDICT:"):
        first_line, _, rest = text.partition("\n")
        candidate = first_line.removeprefix("VERDICT:").strip()
        reasoning = rest.strip()
        if candidate in VALID_VERDICTS:
            verdict = candidate

    return SignerVettingResult(domain=domain, verdict=verdict, reasoning=reasoning, search_queries=queries)


def draft_human_verification_basis(
    domain: str,
    organization_hint: str = "",
    search_fn: SearchFn = _default_search,
) -> str:
    """Runs the automated assessment and formats it directly as ready-to-use
    policy.human_verification_basis text -- the model's best available guess,
    used as-is. An 'uncertain' verdict is included verbatim rather than
    hidden, so it stays visible to anyone reading the locked policy later."""
    result = assess_signer_human_verification_basis(domain, organization_hint, search_fn)
    return f"AI-assessed (verdict: {result.verdict}): {result.reasoning}"
