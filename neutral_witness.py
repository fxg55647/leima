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

Testing, curiosity, and humorous or trivial claims are explicitly permitted.

Refuse to analyse any document or claim that appears intended for:
- Surveillance, stalking, or monitoring individuals without their knowledge
- Gossip, exposure of private life, or harvesting personal information about private individuals
- Whistleblowing or reporting on private individuals in ways likely to cause harm
- Restricting or documenting someone's speech or movements for the purpose of intimidation
- Building a case against a private individual outside a legitimate economic or employment context

If the request appears to fall into any of the above categories, respond with exactly:
REJECTED: This request falls outside the permitted use of Leima.

Otherwise, proceed with the analysis."""

_EMAIL_IDENTITY = """If the document is an email, also assess sender identity credibility: consider the DKIM validation result (valid/invalid/none), whether the From address domain matches the sending infrastructure, and any other signals that might indicate the sender is not who they claim to be. State your assessment explicitly."""

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


def _build_pass_prompts(is_email: bool, question: str = "") -> list[str]:
    email_block = _EMAIL_IDENTITY + "\n\n" if is_email else ""
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
        + email_block + language
    )
    p2 = (
        "You are a document analyst for Leima, a legal evidence tool.\n\n"
        "Identify ONLY what in the document contradicts the claim, or fails to support it. "
        "Note what is absent, inconsistent, or requires assumptions not stated in the document. "
        "Quote directly when relevant. Do not consider supporting evidence.\n\n"
        + email_block + language
    )
    return [p1, p2]

PASS_PROMPTS = _build_pass_prompts(is_email=False, question="the claim")

PASS_LABELS = [
    "Support Analysis",
    "Refutation & Gap Analysis",
    "Synthesis & Verdict",
]


def _synthesis_prompt(question: str, support: str, refutation: str) -> str:
    return f"""You are the final judge for Leima, a legal evidence tool.

The claim being evaluated: "{question}"

Two independent analysts have reviewed the document:

SUPPORT ANALYST:
{support}

REFUTATION ANALYST:
{refutation}

Your task: compare the two analyses objectively. First, check whether the refutation actually addresses the specific claim — not a related issue, not a broader context, but the exact claim as stated. A refutation that is technically true but does not contradict the claim should be discounted. Then assess which side had stronger direct evidence for or against the claim itself.

If the evidence clearly favours one side, say so directly. Do not hedge. A clear verdict is more useful than a balanced non-answer.

Start your response with exactly one line in this format:
VERDICT: <one sentence in the same language as the claim, max 15 words, e.g. "The document strongly supports the claim." or "The refutation is more convincing — the claim lacks direct support.">

Then on a new line, explain your reasoning: which arguments were stronger and why. Be direct.

""" + f'The user\'s claim is: "{question}". Respond entirely in the same language as this claim.'


def analyse(question: str, contents: list, is_email: bool = False) -> dict:
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

    pass_prompts = _build_pass_prompts(is_email, question)
    passes = []
    for prompt, label in zip(pass_prompts, PASS_LABELS):
        resp = client.models.generate_content(
            model=MODEL,
            contents=contents,
            config=types.GenerateContentConfig(system_instruction=prompt),
        )
        passes.append((label, resp.text or ""))

    synth = _synthesis_prompt(question, passes[0][1], passes[1][1])
    synth_resp = client.models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(system_instruction=synth),
    )
    synth_text = (synth_resp.text or "").strip()
    if synth_text.startswith("VERDICT:"):
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
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "prompt_log": prompt_log,
    }
