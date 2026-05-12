# Stampd

**AI verdicts on documents — cryptographically sealed on Arweave.**

Due diligence, notarisation, and source verification have always been expensive — not because they are technically complex, but because they require a trusted human to read, judge, and attest. That constraint is gone. AI can read any document with consistent attention, and a blockchain can seal the result permanently. Together they make it possible, for the first time, to produce credible, tamper-proof verdicts on documents for cents rather than hundreds of euros — available to anyone, not just those with legal budgets.

Stampd is built on this insight. You provide a document and a claim. Stampd analyses it, seals the verdict cryptographically, and publishes a permanent record to Arweave. The document is processed server-side and discarded — only a cryptographic fingerprint goes to the blockchain. The result is independently verifiable by anyone, without trusting Stampd itself.

---

## Contents

- [What it does](#what-it-does)
- [How the proof works](#how-the-proof-works)
- [Use cases](#use-cases)
- [Why this matters](#why-this-matters)
- [Document sources](#document-sources)
- [API](#api)
- [Trust model](#trust-model)
- [Stack](#stack)
- [Setup](#setup)
- [Validation](#validation)
- [Deployment](#deployment)

---

## What it does

You provide a document and a claim. Stampd runs three independent AI passes:

1. **Support Analysis** — tasked exclusively with finding what supports the claim, and under which assumptions
2. **Refutation & Gap Analysis** — tasked exclusively with finding what contradicts the claim, or fails to support it
3. **Synthesis & Verdict** — reads both prior analyses and judges which side had stronger arguments and evidence

The first two passes are stateless and adversarial by design: each sees only the document and the claim, not the other's output. This prevents the model from unconsciously anchoring on its first impression. The third pass acts as an honest judge comparing two independent cases rather than summarising its own reasoning.

The result is not a confident binary verdict. It is an epistemic map: what the document actually supports, what it does not, and how certain that conclusion is.

After analysis you download three files:
- `source.pdf` — the input document (or a PDF rendering of it)
- `verdict.pdf` — the three-pass AI analysis
- `manifest.json` — cryptographic hashes of both files, timestamp, model version, and a permanent Arweave link

**The document is not stored on the blockchain or anywhere permanently.** It is processed server-side for AI analysis and then discarded. Only the manifest — containing SHA-256 hashes of both files — is published to Arweave via Irys. Anyone who later holds all three files can run them through the **Validate** page to confirm nothing has been tampered with.

---

## How the proof works

```
source.pdf  ──sha256──►  input.sha256  ──┐
                                          ├──► manifest.json ──► Arweave (permanent)
verdict.pdf ──sha256──►  verdict.sha256 ──┘
```

The Arweave transaction ID in `manifest.json` points to the manifest itself. A validator fetches it from Arweave and compares it to the local copy — if they match, and the file hashes check out, the verdict is proven authentic and unmodified.

---

## Use cases

**Legal & contractual**
- Proving what a contract said on a specific date
- Verifying claims against employment documents, loan agreements, or invoices
- Preserving the state of a document before a dispute arises
- Extracting evidence from emails (sender, Message-ID, DKIM status, body hash all recorded)

**Due diligence**
- Codebase reviews: stamp a claim like "this repository contains no hardcoded credentials" against a specific commit snapshot, creating a dated record that partially mitigates liability
- Tax and financial documents: verify that a specific figure appears in a tax decision or financial statement before acting on it
- Vendor contracts and SLAs: lock in what was agreed before a relationship begins
- Insurance policies: record what was covered on a specific date before filing a claim

**Research & prior art**
- Recording the existence of an idea or finding on a specific date — stronger timestamping than email or a notebook entry
- AI research agents that need a citable, tamper-proof record of a source supporting a claim
- Verifying that a cited source actually says what a paper claims it says

Stampd accepts documents related to economic activity (contracts, employment, loans, taxation, insurance, investments, real estate) and scientific or research work (papers, reports, study findings, clinical trials, grant applications).

---

## Why this matters

When used with an open-source model on a fixed, publicly auditable prompt, AI has a useful property: it applies the same reasoning process to the same input every time, without financial interest, fatigue, or social pressure. It cannot be personally bribed or threatened. The analysis is still only as good as the model and the prompt — both can be biased, and LLMs can hallucinate — but the point is not perfection. The point is that the analysis is sealed before anyone knew there would be a dispute, tied to the exact document, and reproducible by anyone with the same inputs.

Raw AI output alone is not evidence — it can be regenerated, altered, or denied. Stampd changes this by sealing the analysis cryptographically the moment it is made and storing it permanently on Arweave.

For centuries, verifying a claim against a document required a human: expensive, partial, and available only to those who could afford one. A notary confirms existence, not meaning. A lawyer is a party. This created a world where thorough verification was a luxury — where citation checks were skipped, where disputes were settled by whoever had better representation rather than better evidence.

AI changes the economics entirely. Thousands of source references checked overnight, for cents per claim. Documents analysed at consistent quality regardless of who owns them or what is at stake. Sensitive materials examined without the result being gossiped, remembered, or sold.

Stampd is the infrastructure that makes this analysis permanent and verifiable. The verdict is not just an AI output — it is a sealed record: this document, this claim, this analysis, this moment. Anyone can verify it independently, without trusting Stampd itself.

This matters most in low-trust and chaotic societies where institutions are weak, corruption is common, and a small business owner cannot afford a lawyer or assume that paperwork will be honoured. Combined with C2PA-signed images and videos and crypto-native financial instruments, tamper-proof AI verdicts could provide enough verifiable evidence for someone to secure a business loan, pass due diligence with an international buyer, or sell their products on global markets — without needing a functioning notary, a reliable court system, or a bank that trusts them. The infrastructure of trust that wealthy societies take for granted can be approximated, for the first time, at near-zero cost.

---

## Document sources

| Source | Notes |
|--------|-------|
| PDF upload | Direct file upload |
| PDF URL | Fetched server-side, max 10 MB, SSRF-protected |
| Text paste | Converted to PDF for hashing |
| Email (IMAP) | Fetches via IMAP; records Message-ID, DKIM presence, body hash |

---

## API

Agents and automated pipelines can call Stampd directly without the UI:

```
POST /api/stamp
Content-Type: application/json

{
  "claim": "The agreed salary is €3,500 per month",
  "source_type": "pdf_url",   // "pdf_url" | "pdf_base64" | "text"
  "source": "https://example.com/contract.pdf"
}
```

Response:
```json
{
  "verdict": "The document strongly supports the claim.",
  "passes": [
    { "label": "Support Analysis", "text": "..." },
    { "label": "Refutation & Gap Analysis", "text": "..." },
    { "label": "Synthesis & Verdict", "text": "..." }
  ],
  "input_hash": "sha256:...",
  "verdict_hash": "sha256:...",
  "timestamp": "2026-05-12 10:00:00 UTC",
  "model": "gemini-2.5-flash-lite",
  "arweave": { "tx_id": "...", "url": "https://gateway.irys.xyz/..." },
  "manifest": { ... }
}
```

---

## Trust model

**AI reliability**
Stampd's verdicts are only as reliable as the underlying language model. LLMs can misread documents, miss context, or produce confident-sounding but wrong conclusions. Stampd is a tool for structuring and timestamping analysis — not a legal authority. Treat the verdict as a documented first opinion, not a final judgment.

**Document sensitivity**
Documents are sent to Google's Gemini API for analysis. For sensitive materials — personal data, unreleased financials, confidential contracts — consider anonymising or redacting the document before submitting. Replace names, account numbers, and identifying details with placeholders where the claim can still be evaluated without them.

**What Arweave guarantees**
The blockchain record proves that a specific analysis of a specific document existed at a specific time, and that neither has been altered since. It does not prove the analysis is correct, that the document is authentic, or that the claim is true in any legal sense.

**Planned: private AI option**
For organisations that cannot send documents to third-party APIs, a future option will allow routing analysis through a self-hosted or corporate LLM. The stamping and verification layer remains identical — only the AI backend changes.

**Planned: cross-instance integrity monitoring**
Stampd instances will be able to monitor each other via the Render API: each instance can verify that the version currently running matches the expected git commit hash, and publish a signed attestation to Arweave recording that no incidents have occurred. The attestation log will be publicly readable — anyone can query any instance's API to see what version is running and whether its history is clean. This makes Stampd itself auditable by the same mechanism it provides to its users.

---

## Stack

- **Backend** — FastAPI + Uvicorn
- **AI** — Google Gemini 2.5 Flash Lite
- **Blockchain** — Arweave via Irys SDK (Ethereum wallet)
- **Frontend** — HTMX, no JS framework
- **PDF generation** — fpdf2

---

## Setup

```bash
git clone https://github.com/fxg55647/stampd
cd stampd
uv venv --python 3.12
uv pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in:

```env
GEMINI_API_KEY=your-gemini-api-key
IRYS_PRIVATE_KEY=0x...          # Ethereum private key
IRYS_NETWORK=devnet              # or mainnet
IRYS_RPC_URL=https://ethereum-sepolia-rpc.publicnode.com  # devnet only
```

For devnet you need Sepolia ETH in your wallet. Get it from a Sepolia faucet.

```bash
uvicorn main:app --reload
```

---

## Validation

Any party who receives the three files can verify integrity at `/validate`:

- SHA-256 of `source.pdf` matches `manifest.json → input.sha256`
- SHA-256 of `verdict.pdf` matches `manifest.json → verdict_pdf.sha256`
- The manifest fetched from Arweave matches the local `manifest.json` (minus the `arweave` field)

If all three pass, the verdict is authentic and unmodified.

---

## Deployment

Render deployment is configured in `render.yaml`. Set the environment variables in the Render dashboard. Switch `IRYS_NETWORK` to `mainnet` and remove `IRYS_RPC_URL` for production.
