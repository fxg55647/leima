# Stampd

**AI verdicts on documents — cryptographically sealed on Arweave.**

Stampd lets you make a claim about a document and get an AI-generated verdict that is permanently stored on the blockchain. The result is independently verifiable by anyone, at any time, without trusting Stampd itself.

---

## What it does

You provide a document and a claim. Stampd runs three independent AI passes:

1. **Support Analysis** — what in the document supports the claim, and under which assumptions
2. **Refutation & Gap Analysis** — what contradicts the claim, or fails to support it
3. **Ambiguity & Scope Audit** — where reasonable disagreement could arise; definitions, time bounds, missing evidence

The verdict is not a binary judgment. Disagreement is treated as signal, not failure.

After analysis you download three files:
- `source.pdf` — the input document (or a PDF rendering of it)
- `verdict.pdf` — the three-pass AI analysis
- `manifest.json` — cryptographic hashes of both files, timestamp, model version, and a permanent Arweave link

The manifest is uploaded to Arweave via Irys. Anyone who later holds all three files can run them through the **Validate** page to confirm nothing has been tampered with.

---

## Use cases

- Proving what a contract said on a specific date
- Verifying claims against employment documents, loan agreements, or invoices
- Preserving the state of a document before a dispute arises
- Extracting evidence from emails (sender, Message-ID, DKIM status, body hash all recorded)
- Poor man's notary, due diligence tool, or patent-style prior art record

Stampd only accepts documents related to economic activity: employment, contracts, loans, taxation, insurance, investments, real estate, business agreements, and social benefits.

---

## Document sources

| Source | Notes |
|--------|-------|
| PDF upload | Direct file upload |
| PDF URL | Fetched server-side, max 10 MB, SSRF-protected |
| Text paste | Converted to PDF for hashing |
| Email (IMAP) | Fetches via IMAP; records Message-ID, DKIM presence, body hash |

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
