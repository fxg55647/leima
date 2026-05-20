# Leima

**Tamper-proof records of AI document analysis.**

Due diligence, notarisation, and source verification have always been expensive — not because they are technically complex, but because they require a trusted human to read, judge, and attest. That bottleneck is no longer absolute. AI can read any document with consistent attention, and a blockchain can seal the result permanently. Together they make it possible, for the first time, to produce credible, tamper-proof verdicts on documents for cents rather than hundreds of euros — available to anyone, not just those with legal budgets.

Leima is built on this insight. You provide a document and a claim. Leima analyses it, seals the verdict cryptographically, and publishes a permanent record to Arweave. The document is processed server-side and discarded — only a cryptographic fingerprint goes to the blockchain. The result is independently verifiable by anyone, without trusting Leima itself.

Leima produces two things at once: a cryptographic proof that a specific document existed and was analysed at a specific time, and an expert opinion on what that document actually says about your claim — both sealed together permanently.

---

## Contents

- [What it does](#what-it-does)
- [How the proof works](#how-the-proof-works)
- [Use cases](#use-cases) — see also [USECASES.md](USECASES.md) for extended examples
- [Why this matters](#why-this-matters)
- [Document sources](#document-sources)
- [API](#api)
- [Trust model](#trust-model)
- [Stack](#stack)
- [Setup](#setup)
- [Validation](#validation)
- [Deployment](#deployment)
- [Deployment integrity (PoDe)](#deployment-integrity-pode)
- [Data policy](POLICY.md)

---

## What it does

You provide a document and a claim. Leima runs three independent AI passes:

1. **Support Analysis** — tasked exclusively with finding what supports the claim, and under which assumptions
2. **Refutation & Gap Analysis** — tasked exclusively with finding what contradicts the claim, or fails to support it
3. **Synthesis & Verdict** — reads both prior analyses and judges which side had stronger arguments and evidence

The first two passes are stateless and adversarial by design: each sees only the document and the claim, not the other's output. This prevents the model from unconsciously anchoring on its first impression. The third pass acts as an honest judge comparing two independent cases rather than summarising its own reasoning.

The result is not a confident binary verdict. It is an epistemic map: what the document actually supports, what it does not, and how certain that conclusion is.

After analysis you download three files:
- `source` — the input document in its original format (PDF, image, or a PDF rendering of text/web input)
- `verdict.pdf` — the three-pass AI analysis (also available as TXT, HTML, or JSON)
- `manifest.json` — cryptographic hashes of both files, timestamp, model version, and a link to the stamp record on Arweave

**The document is not stored on the blockchain or anywhere permanently.** It is processed server-side for AI analysis and then discarded. A stamp record — containing SHA-256 hashes of both files — is published to Arweave via Irys. The `manifest.json` you download contains this stamp record plus the Arweave transaction ID pointing to it. Anyone who later holds all three files can run them through the **Validate** page to confirm nothing has been tampered with.

---

## How the proof works

```
source.pdf  ──sha256──►  input.sha256  ──┐
                                          ├──► stamp record ──► Arweave (permanent)
verdict.pdf ──sha256──►  verdict.sha256 ──┘                          │
                                                                      ▼
                                                    manifest.json (stamp.tx_id points here)
```

The stamp record is the immutable on-chain object: it contains the hashes, timestamp, and model, but no Arweave link (since that ID doesn't exist yet when it's created). The `manifest.json` you download is the stamp record plus a `stamp` field with the Arweave transaction ID and URL. A validator fetches the stamp record from Arweave and compares it to `manifest.json` (minus the `stamp` field) — if they match, and the file hashes check out, the verdict is proven authentic and unmodified.

---

## Use cases

**Consumer documentation**
- Stamping service receipts received by email — car repairs, appliance installations, specialist appraisals — for insurance claims, warranty disputes, or resale
- Recording purchases and valuations before a loss occurs, so the evidence predates the claim

**Art and collectibles**
- Artists proving creation and first-owner transfer via a stamped email — DKIM confirms the sender's domain and date
- Creation process documented with C2PA-signed photographs (already supported by cameras from Leica, Sony, Nikon): cryptographic timestamps from the device itself, combined with a Leima verdict, create provenance that is difficult to fabricate
- Restoration and conservation records; collectibles chain of custody

**Legal and contractual**
- Proving what a contract, offer letter, or invoice said on a specific date
- Preserving pre-dispute state of agreements, leases, and correspondence
- Employment disputes: salary confirmations, policy documents, HR communications

**Economic inclusion**
- Small-scale farmers and fishing cooperatives building stamped records of sales, inputs, and activity — usable as evidence for microfinance or access to premium markets
- Professionals in jurisdictions without reliable registries establishing verifiable work history and agreements from email records alone

**Research and due diligence**
- Timestamping findings before publication to establish priority
- Verifying that a cited source says what a paper claims it says, at the time of writing
- Codebase reviews: stamping a claim against a specific commit snapshot

For extended examples and context see [USECASES.md](USECASES.md).

---

## Why this matters

When used with an open-source model on a fixed, publicly auditable prompt, AI has a useful property: it applies the same reasoning process to the same input every time, without financial interest, fatigue, or social pressure. It cannot be personally bribed or threatened. The analysis is still only as good as the model and the prompt — both can be biased, and LLMs can hallucinate — but the point is not perfection. The point is that the analysis is sealed before anyone knew there would be a dispute, tied to the exact document, and reproducible by anyone with the same inputs.

Raw AI output alone is not evidence — it can be regenerated, altered, or denied. Leima changes this by sealing the analysis cryptographically the moment it is made and storing it permanently on Arweave.

For centuries, verifying a claim against a document required a human: expensive, partial, and available only to those who could afford one. A notary confirms existence, not meaning. A lawyer is a party. This created a world where thorough verification was a luxury — where citation checks were skipped, where disputes were settled by whoever had better representation rather than better evidence.

AI changes the economics entirely. Thousands of source references checked overnight, for cents per claim. Documents analysed at consistent quality regardless of who owns them or what is at stake. Sensitive materials examined without the result being gossiped, remembered, or sold.

Leima is the infrastructure that makes this analysis permanent and verifiable. The verdict is not just an AI output — it is a sealed record: this document, this claim, this analysis, this moment. Anyone can verify it independently, without trusting Leima itself.

We call this role the **neutral witness** — an AI that has no stake in the outcome, no memory of previous cases, and no relationship with either party.

This matters most in low-trust and chaotic societies where institutions are weak, corruption is common, and a small business owner cannot afford a lawyer or assume that paperwork will be honoured. Combined with C2PA-signed images and videos and crypto-native financial instruments, tamper-proof AI verdicts could provide enough verifiable evidence for someone to secure a business loan, pass due diligence with an international buyer, or sell their products on global markets — without needing a functioning notary, a reliable court system, or a bank that trusts them. The infrastructure of trust that wealthy societies take for granted can be approximated, for the first time, at near-zero cost.

---

## Document sources

| Source | Notes |
|--------|-------|
| PDF upload | Direct file upload |
| PDF URL | Fetched server-side, max 10 MB, SSRF-protected |
| Image | JPG, PNG, GIF, WebP, HEIC, HEIF — analysed directly, original file preserved |
| Text paste | Converted to PDF for hashing |
| Web page | HTML fetched server-side, stripped to text; URL and fetch timestamp recorded in stamp record |
| Email (IMAP) | Fetches via IMAP; validates DKIM signature (valid / invalid / none), records Message-ID and body hash |

---

## API

Agents and automated pipelines can call Leima directly without the UI:

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
  "stamp": { "tx_id": "...", "url": "https://gateway.irys.xyz/..." },
  "manifest": { ... }
}
```

---

## Threat model

| Threat | Covered? | Notes |
|--------|----------|-------|
| Verdict modified after creation | Yes | Hash mismatch detected on validation |
| Source file modified after creation | Yes | Hash mismatch detected on validation |
| Manifest altered locally | Yes | Compared against immutable Arweave copy |
| Code violates stated data policy | Yes | AI audits all source files against POLICY.md on every commit; workflow fails and PoDe turns red if a violation is found |
| Malicious code change slipped in unnoticed | Yes | Every commit triggers a code review; Render deploy takes longer than one minute; PoDe polls every minute; Render returns full deploy history so no deploy can be hidden retroactively |
| Deployed commit not present in git repository | Yes | History check verifies every recent Render deploy commit exists in GitHub; mismatch is recorded in status.json and shown in Tampermonkey userscript |
| Hosting provider (Render) swaps running code silently | Partly | PoDe detects mismatches within ~1 minute; Render API reporting the actual running commit honestly is a residual trust assumption |
| Leima lies during original run | Partly | Full prompt logic is isolated in `neutral_witness.py` and audited on every commit |
| AI verdict is wrong | No | Reviewable first opinion only — not a legal authority |
| Document is fake before upload | No | Leima timestamps existence, does not authenticate origin |
| Email body altered after sending | Partly | DKIM validates signed headers and body scope — coverage depends on sender configuration |
| Human sender identity false | No | DKIM proves domain, not individual identity; LLM assesses credibility signals |
| Sensitive data exposure to AI provider | Partly | Redaction recommended; privacy-committed AI provider planned |

---

## Trust model

For a complete description of what data Leima collects, where it goes, and what triggers re-consent when code changes, see [POLICY.md](POLICY.md).

**AI reliability**
Leima's verdicts are only as reliable as the underlying language model. LLMs can misread documents, miss context, or produce confident-sounding but wrong conclusions. Leima is a tool for structuring and timestamping analysis — not a legal authority. Treat the verdict as a documented first opinion, not a final judgment.

The full AI prompt logic is isolated in `neutral_witness.py` — a single file that anyone can read to verify exactly what instructions are given to the model, without reading the rest of the codebase.

**Email authentication**
For emails, Leima validates the DKIM signature cryptographically (result: valid / invalid / none) and records it in the manifest. A valid DKIM result confirms the message was not altered in transit and was sent by the claimed domain — but does not prove the human sender is who they claim to be. The neutral witness is instructed to assess sender identity credibility based on DKIM result, domain consistency, and other available signals, and to state its assessment explicitly in the verdict.

**Document sensitivity**
Documents are sent to Google's Gemini API for analysis. For sensitive materials — personal data, unreleased financials, confidential contracts — consider anonymising or redacting the document before submitting. Replace names, account numbers, and identifying details with placeholders where the claim can still be evaluated without them.

For the email input, a planned pre-processing filter will automatically strip personal data from message bodies before sending to the AI — retaining only what is needed to evaluate the claim. This is particularly relevant for email threads that contain third-party personal data the user may not have the right to share with external APIs.

**What Arweave guarantees**
The blockchain record proves that a specific analysis of a specific document existed at a specific time, and that neither has been altered since. It does not prove the analysis is correct, that the document is authentic, or that the claim is true in any legal sense.

**You do not need to trust the authors**
Leima is open source. You can read the code, verify that the prompts and logic match what is described here, and run your own instance. Trust in the software does not require trust in the people who wrote it.

**Deployment integrity monitoring (PoDe)**
Open source code is auditable — but only if the running code is the same as the published code. Leima implements PoDe (Proof of Deployment): five GitHub Actions workflows run on a staggered schedule, together achieving one-minute polling resolution. Each workflow queries the Render API for the deployed commit and the GitHub API for the repository HEAD, and publishes the result publicly. Anyone can verify deployment integrity without credentials, at any time.

See [PODE.md](PODE.md) for a full description of the protocol, the current implementation, the longer-term vision, real-world incidents where deployment transparency would have helped (XZ Utils, PHP git compromise, Picreel), and how PoDe relates to existing approaches such as Sigstore and Meta Code Verify.

One residual trust assumption remains: Render, as the hosting provider, could in principle report a false commit hash while running different code. This is a different category of risk than ordinary vulnerabilities — it requires the hosting provider to actively conspire against users. See PODE.md for a discussion of how this could be mitigated.

**Planned: privacy-committed AI providers**
A future option will allow switching to AI providers that operate under strict, publicly auditable privacy commitments — where documents are contractually guaranteed not to be used for training or retained after the request. The stamping and verification layer remains identical; only the AI backend changes. This preserves the trust model while reducing reliance on Google's standard API terms.

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
git clone https://github.com/fxg55647/leima
cd leima
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

- SHA-256 of `source` matches `manifest.json → input.sha256`
- SHA-256 of `verdict.pdf` matches `manifest.json → verdict_pdf.sha256`
- The stamp record fetched from Arweave matches the local `manifest.json` (minus the `stamp` field)

If all three pass, the verdict is authentic and unmodified.

---

## Deployment

Connect the GitHub repository in the Render dashboard and set the environment variables. Switch `IRYS_NETWORK` to `mainnet` and remove `IRYS_RPC_URL` for production.

---

## Deployment integrity (PoDe)

Five GitHub Actions workflows run on a staggered schedule and together poll deployment status every minute. Each run checks three conditions: the live Render commit matches the GitHub repository HEAD, the latest automated code review passed, and the deploy history contains no commits absent from git. Results are published to the `gh-pages` branch as `status.json`.

Before submitting sensitive documents, verify that the PoDe Code Review and the five PoDe A–E workflows show green on the [Actions tab](../../actions). See [PODE.md](PODE.md) for the full protocol description.
