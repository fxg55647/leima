"""
neutral_witness.py — the AI analysis layer of Stampd.

This module contains all prompts and logic that determine what the AI does with
a document and a claim. It is intentionally isolated from the web framework,
PDF generation, and blockchain code so that anyone can audit exactly what
instructions are given to the model without reading the rest of the codebase.
"""

import os
from datetime import datetime
from google import genai
from google.genai import types

MODEL = "gemini-2.5-flash-lite"

_client: genai.Client | None = None

def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    return _client

_SCOPE = """You ONLY analyse documents related to economic activity or scientific/research work. Accepted topics:
- Employment: contracts, salary, dismissals, warnings, references
- Entrepreneurship: invoices, business agreements, company ownership
- Job seeking: applications, offers, rejections
- Loans & debt: loan agreements, payment plans, debt collection
- Insurance: work-related or business insurance policies
- Social benefits: unemployment, sick pay, Kela decisions
- Taxation: tax cards, tax decisions, advance tax
- Investments & ownership: shares, shareholder agreements
- Real estate: rental agreements, purchase contracts
- Education: employer-funded training, professional certifications
- Any contract or agreement with financial or legal consequences
- Scientific & research: academic papers, research reports, study findings, journal articles, grant applications, data analyses, clinical trials, experiment results
- Encyclopedic & reference: Wikipedia articles, historical records, factual reference material, news articles, official publications
- Any document where a factual claim can be verified against the source

If the document is clearly not factual in nature and contains no verifiable claims (e.g. fiction, entertainment, spam), respond with exactly:
REJECTED: This document does not contain verifiable factual claims and cannot be stamped."""

_EMAIL_IDENTITY = """If the document is an email, also assess sender identity credibility: consider the DKIM validation result (valid/invalid/none), whether the From address domain matches the sending infrastructure, and any other signals that might indicate the sender is not who they claim to be. State your assessment explicitly."""

PASS_PROMPTS = [
    f"""You are a document analyst for Stampd, a legal evidence tool.
{_SCOPE}

Otherwise: identify ONLY what in the document supports the claim, and under which assumptions. Be specific. Quote directly from the document using quotation marks. Do not consider contradictions or gaps.

{_EMAIL_IDENTITY}""",

    f"""You are a document analyst for Stampd, a legal evidence tool.
{_SCOPE}

Otherwise: identify ONLY what in the document contradicts the claim, or fails to support it. Note what is absent, inconsistent, or requires assumptions not stated in the document. Quote directly when relevant. Do not consider supporting evidence.

{_EMAIL_IDENTITY}""",
]

PASS_LABELS = [
    "Support Analysis",
    "Refutation & Gap Analysis",
    "Synthesis & Verdict",
]


def _synthesis_prompt(question: str, support: str, refutation: str) -> str:
    return f"""You are the final judge for Stampd, a legal evidence tool.

The claim being evaluated: "{question}"

Two independent analysts have reviewed the document:

SUPPORT ANALYST:
{support}

REFUTATION ANALYST:
{refutation}

Your task: compare the two analyses objectively. Which side had stronger arguments and better evidence from the document? Consider the quality of quotes, the directness of the evidence, and the logical strength of each case.

Start your response with exactly one line in this format:
VERDICT: <one sentence in the same language as the claim, max 15 words, e.g. "The document strongly supports the claim." or "The refutation is more convincing — the claim lacks direct support.">

Then on a new line, explain your reasoning: which arguments were stronger and why. Be direct."""


def analyse(question: str, contents: list) -> dict:
    """
    Run three-pass neutral witness analysis on a document.

    `contents` is a list of Gemini content parts (PDF bytes or text strings)
    followed by the claim string. Returns a dict with passes, summary_verdict,
    timestamp, and prompt_log.

    Raises ValueError with a REJECTED: message if the document is out of scope.
    """
    client = _get_client()
    passes = []
    for prompt, label in zip(PASS_PROMPTS, PASS_LABELS):
        resp = client.models.generate_content(
            model=MODEL,
            contents=contents,
            config=types.GenerateContentConfig(system_instruction=prompt),
        )
        text = resp.text
        if text.startswith("REJECTED:"):
            raise ValueError(text)
        passes.append((label, text))

    synth = _synthesis_prompt(question, passes[0][1], passes[1][1])
    synth_resp = client.models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(system_instruction=synth),
    )
    synth_text = synth_resp.text.strip()
    if synth_text.startswith("VERDICT:"):
        first_line, _, rest = synth_text.partition("\n")
        summary_verdict = first_line.removeprefix("VERDICT:").strip()
        synthesis_body = rest.strip()
    else:
        summary_verdict = synth_text.split(".")[0].strip() + "."
        synthesis_body = synth_text
    passes.append((PASS_LABELS[2], synthesis_body))

    prompt_log = (
        list(zip(PASS_LABELS[:2], PASS_PROMPTS))
        + [(PASS_LABELS[2], synth)]
    )

    return {
        "passes": passes,
        "summary_verdict": summary_verdict,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "prompt_log": prompt_log,
    }
