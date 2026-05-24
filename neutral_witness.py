"""
neutral_witness.py — the AI analysis layer of Leima.

This module contains all prompts and logic that determine what the AI does with
a document and a claim. It is intentionally isolated from the web framework,
PDF generation, and blockchain code so that anyone can audit exactly what
instructions are given to the model without reading the rest of the codebase.
"""

import os
from datetime import datetime
from google import genai
from google.genai import types

MODEL = "gemini-3.1-flash-lite"

_client: genai.Client | None = None

def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    return _client

_SCOPE = """Leima is a tool for economic activity, scientific work, and the verification of factual claims. It is not a law enforcement tool, does not serve state authorities, and is not designed for resolving disputes between parties.

Because of this, Leima does not make exceptions based on whether content appears illegal or harmful. The scope is defined by purpose, not by content:

Testing, curiosity, humorous or trivial claims, and sports analytics or verification of public sporting events and results are explicitly permitted.

Refuse to analyse any document or claim that appears intended for:
- Surveillance, stalking, or monitoring individuals without their knowledge
- Gossip, exposure of private life, or harvesting personal information about private individuals
- Whistleblowing or reporting on private individuals in ways likely to cause harm
- Restricting or documenting someone's speech or movements for the purpose of intimidation
- Building a case against a private individual outside a legitimate economic or employment context

If the request appears to fall into any of the above categories, respond with exactly:
REJECTED: This request falls outside the permitted use of Leima.

Otherwise, proceed with the analysis."""

def _source_block(source_context: dict | None) -> str:
    if not source_context:
        return (
            "Content analysis mode: assess only what the document contains or states. "
            "Do not evaluate source authenticity, origin, or credibility."
        )
    t = source_context.get("type", "content_only")
    if t == "content_only":
        return (
            "Content analysis mode: assess only what the document contains or states. "
            "Do not evaluate source authenticity, origin, or credibility. "
            "Report findings in terms of the document's content — "
            "e.g. 'the document states that...' or 'the code contains...'"
        )
    if t == "email":
        dkim = source_context.get("dkim", "none")
        domain = source_context.get("sender_domain", "unknown")
        return (
            f"Source type: Email (fetched via IMAP from the user's own mailbox). DKIM: {dkim}. Sender domain: {domain}. "
            "The user has accessed this email from their own account and is using it to prove something about themselves — "
            "for example, their employment history, a transaction they were party to, or a communication they received. "
            "Analysing personal information in this context is permitted because the person whose data is involved "
            "is the one submitting it. Normal topic restrictions still apply: work, business, financial, and factual "
            "claims are within scope; surveillance, stalking, or building a case against a third party are not. "
            "Assess sender identity credibility based on the DKIM result and whether the sender domain "
            "matches the claimed sender. "
            "If the claim names a specific individual as the recipient, verify that this person's name "
            "or email address appears in the To field or email body — if not, flag this as a significant gap."
        )
    elif t == "image_c2pa_valid":
        return (
            "Source type: Image with a valid C2PA cryptographic signature. "
            "The image's origin and authenticity are cryptographically established. "
            "Treat the image content as genuine unless internal inconsistencies suggest otherwise."
        )
    elif t == "image_c2pa_invalid":
        return (
            "Source type: Image with an INVALID C2PA signature. "
            "The image has been modified after the original capture. "
            "Factor this significantly into your credibility assessment."
        )
    elif t == "image_no_c2pa":
        return (
            "Source type: Image without provenance data. "
            "The image's origin cannot be cryptographically verified. "
            "Assess only whether its content supports or contradicts the claim — do not speculate about origin. "
            "Do not draw conclusions about truth value beyond what the image itself shows."
        )
    elif t in ("web", "pdf_url"):
        domain = source_context.get("domain", "unknown")
        label = "Web page" if t == "web" else "PDF document"
        return (
            f"Source type: {label} fetched from {domain}. "
            "Assess the credibility of this domain in relation to the claim. "
            "An authoritative domain within its field (e.g. a stock exchange for market data, "
            "a government site for legal records, a major institution for official statements) "
            "significantly strengthens credibility. An unknown or unrelated domain weakens it."
        )
    else:
        return (
            "Content analysis mode: assess only what the document contains or states. "
            "Do not evaluate source authenticity, origin, or credibility."
        )

def _scope_prompt(question: str) -> str:
    return (
        "You are a scope filter for Leima, a document analysis tool.\n\n"
        + _SCOPE + "\n\n"
        f'The claim to be evaluated is: "{question}"\n\n'
        "Review the document and the claim against the scope rules above. "
        "If the request is permitted, respond with exactly: APPROVED\n"
        "If the request falls outside permitted use, respond with exactly: "
        "REJECTED: This request falls outside the permitted use of Leima."
    )


def _build_pass_prompts(source_context: dict | None, question: str = "") -> list[str]:
    source_block = _source_block(source_context) + "\n\n"
    language = (
        f'The user\'s claim is: "{question}". '
        'Detect the language of this claim and respond entirely in that language — '
        'not in English unless the claim itself is in English. '
        'Direct quotes from the document must be reproduced verbatim in their original language — do not translate them.'
    )
    p1 = (
        "You are a document analyst for Leima, a legal evidence tool.\n\n"
        "Identify ONLY what in the document supports the claim, and under which assumptions. "
        "Be specific. Quote directly from the document using quotation marks. "
        "Do not consider contradictions or gaps.\n\n"
        + source_block + language
    )
    p2 = (
        "You are a document analyst for Leima, a legal evidence tool.\n\n"
        "Identify ONLY what in the document contradicts the claim, or fails to support it. "
        "Note what is absent, inconsistent, or requires assumptions not stated in the document. "
        "Quote directly when relevant. Do not consider supporting evidence.\n\n"
        + source_block + language
    )
    return [p1, p2]

PASS_PROMPTS = _build_pass_prompts(source_context=None, question="the claim")

PASS_LABELS = [
    "Supporting evidence",
    "Contradicting evidence",
    "Verdict",
]


def _synthesis_prompt(question: str, support: str, refutation: str, source_context: dict | None = None) -> str:
    content_only = (source_context or {}).get("type") == "content_only"
    content_only_note = (
        "\nThis is a content analysis — do not assert whether the claim is true in an absolute sense. "
        "Frame your verdict in terms of what the document states or contains.\n"
    ) if content_only else ""
    return f"""You are the final judge for Leima, a legal evidence tool.

The claim being evaluated: "{question}"

Two independent analysts have reviewed the document:

SUPPORT ANALYST:
{support}

REFUTATION ANALYST:
{refutation}

Your task: compare the two analyses objectively. First, check whether the refutation actually addresses the specific claim — not a related issue, not a broader context, but the exact claim as stated. A refutation that is technically true but does not contradict the claim should be discounted. Then assess which side had stronger direct evidence for or against the claim itself.

If the evidence clearly favours one side, say so directly. Do not hedge. A clear verdict is more useful than a balanced non-answer.
{content_only_note}
Start your response with exactly two lines in this format:
CATEGORY: <exactly one of: Strongly matches / Mostly matches / Equally supports and contradicts / Mostly does not match / Does not match>
VERDICT: <one sentence in the same language as the claim, max 15 words, e.g. "The document strongly supports the claim." or "The refutation is more convincing — the claim lacks direct support.">

Then on a new line, explain your reasoning: which arguments were stronger and why. Be direct.

""" + f'The user\'s claim is: "{question}". Use exactly one of the five English CATEGORY strings listed above (Strongly matches / Mostly matches / Equally supports and contradicts / Mostly does not match / Does not match). Respond to VERDICT and the explanation entirely in the same language as this claim.'


def analyse(question: str, contents: list, source_context: dict | None = None) -> dict:
    """
    Run three-pass neutral witness analysis on a document.

    `contents` is a list of Gemini content parts (PDF bytes or text strings)
    followed by the claim string. Returns a dict with passes, summary_verdict,
    timestamp, and prompt_log.

    Raises ValueError with a REJECTED: message if the document is out of scope.
    """
    client = _get_client()

    scope_resp = client.models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(system_instruction=_scope_prompt(question)),
    )
    scope_text = (scope_resp.text or "").strip()
    if not scope_text.startswith("APPROVED"):
        raise ValueError(scope_text or "Model returned no response during scope check")

    pass_prompts = _build_pass_prompts(source_context, question)
    passes = []
    for prompt, label in zip(pass_prompts, PASS_LABELS):
        resp = client.models.generate_content(
            model=MODEL,
            contents=contents,
            config=types.GenerateContentConfig(system_instruction=prompt),
        )
        passes.append((label, resp.text or ""))

    synth = _synthesis_prompt(question, passes[0][1], passes[1][1], source_context)
    synth_resp = client.models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(system_instruction=synth),
    )
    synth_text = (synth_resp.text or "").strip()
    verdict_category = "Epävarma"
    if synth_text.startswith("CATEGORY:"):
        lines = synth_text.split("\n", 3)
        verdict_category = lines[0].removeprefix("CATEGORY:").strip()
        rest_lines = lines[1:]
        if rest_lines and rest_lines[0].startswith("VERDICT:"):
            summary_verdict = rest_lines[0].removeprefix("VERDICT:").strip()
            synthesis_body = "\n".join(rest_lines[1:]).strip()
        else:
            summary_verdict = ""
            synthesis_body = "\n".join(rest_lines).strip()
    elif synth_text.startswith("VERDICT:"):
        first_line, _, rest = synth_text.partition("\n")
        summary_verdict = first_line.removeprefix("VERDICT:").strip()
        synthesis_body = rest.strip()
    else:
        summary_verdict = synth_text.split(".")[0].strip() + "."
        synthesis_body = synth_text
    passes.append((PASS_LABELS[2], synthesis_body))

    prompt_log = (
        list(zip(PASS_LABELS[:2], pass_prompts))
        + [(PASS_LABELS[2], synth)]
    )

    return {
        "passes": passes,
        "summary_verdict": summary_verdict,
        "verdict_category": verdict_category,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "prompt_log": prompt_log,
    }
