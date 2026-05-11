# Stampd

**AI verdicts on documents — cryptographically sealed on Arweave.**

Stampd lets you make a claim about a document and get an AI-generated verdict that is permanently and independently verifiable. The document itself never leaves your machine — only a cryptographic fingerprint is published.

---

## What it does

You provide a document and a claim. Stampd runs three AI passes:

1. **Support Analysis** — what in the document supports the claim, and under which assumptions
2. **Refutation & Gap Analysis** — what contradicts the claim, or fails to support it
3. **Synthesis & Verdict** — compares both sides and delivers an honest judgment

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

- Proving what a contract said on a specific date
- Verifying claims against employment documents, loan agreements, or invoices
- Preserving the state of a document before a dispute arises
- Extracting evidence from emails (sender, Message-ID, DKIM status, body hash all recorded)
- Poor man's notary, due diligence tool, or patent-style prior art record
- AI research agents that need a citable, tamper-proof record of a source supporting a claim

Stampd accepts documents related to economic activity (contracts, employment, loans, taxation, insurance, investments, real estate) and scientific or research work (papers, reports, study findings, clinical trials, grant applications).

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
