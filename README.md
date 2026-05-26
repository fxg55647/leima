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
- [A public good](#a-public-good)
- [Contributing](#contributing)
- [Document sources](#document-sources)
- [API](#api)
- [Trust model](#trust-model)
- [Threat model](#threat-model)
- [Stack](#stack)
- [Setup](#setup)
- [Validation](#validation)
- [Deployment](#deployment)
- [Deployment integrity (POIDE)](#deployment-integrity-poide)
- [Independent verification (verify.py)](#independent-verification-verifypy)
- [Self-characterisation for due diligence (bundle_source.py)](#self-characterisation-for-due-diligence-bundle_sourcepy)
- [Developer pre-push hook](#developer-pre-push-hook)
- [Data policy](POLICY.example.md)

---

## What it does

You provide a document and a claim. Leima runs three independent AI passes:

1. **Supporting evidence** — tasked exclusively with finding what supports the claim, and under which assumptions
2. **Contradicting evidence** — tasked exclusively with finding what contradicts the claim, or fails to support it
3. **Verdict** — reads both prior analyses and judges which side had stronger arguments and evidence

The first two passes are stateless and adversarial by design: each sees only the document and the claim, not the other's output. This prevents the model from unconsciously anchoring on its first impression. The third pass acts as an honest judge comparing two independent cases rather than summarising its own reasoning.

The result is not a confident binary verdict. It is an epistemic map: what the document actually supports, what it does not, and how certain that conclusion is.

After analysis you download three files:
- `source` — the input document in its original format (PDF, image, or a PDF rendering of text/web input)
- `verdict.pdf` — the three-pass AI analysis (also available as TXT, HTML, or JSON)
- `manifest.json` — cryptographic hashes of both files, timestamp, model version, and a link to the stamp record on Arweave

**The document is not stored on the blockchain or anywhere permanently.** It is processed server-side for AI analysis and then discarded. A stamp record — containing SHA-256 hashes of both files — is published to Arweave via Irys. The `manifest.json` you download contains this stamp record plus the Arweave transaction ID pointing to it. Anyone who later holds all three files can run them through the **Validate** page to confirm nothing has been tampered with.

Leima produces guarantees that work independently of each other:

**Cryptographic source integrity — where the document comes from.** For documents that carry their own cryptographic provenance, Leima verifies it at submission time:
- **PDF with digital signature (RFC 3161):** the document's integrity is proven from the moment of signing. Leima extracts the signer certificate, the RFC 3161 trusted timestamp, and the Timestamp Authority. If the document was modified after signing, this is detected and flagged immediately — not discovered months later in a review.
- **Image with C2PA signature:** origin and capture authenticity are cryptographically established from the camera or device.
- **Email with DKIM:** the sender's domain is verified against their published DNS records.

For unsigned documents there is no pre-existing provenance to verify — but the next layer still applies.

**Hash commitment — the submission layer.** The SHA-256 hash of your document is sealed on Arweave at the moment of stamping. If anyone later claims the document said something different, or substitutes a different version, the hash mismatch is provable. This does not require trusting AI — it requires only that SHA-256 is collision-resistant, which is a mathematical fact. A hash mismatch after the fact is evidence of tampering: at minimum a contractual breach, potentially fraud.

**AI verdict — the practical layer.** The analysis characterises what the document actually says about the claim, captured before either party had an incentive to misrepresent it. An insurance adjuster, a lender, or a due diligence analyst can use this to guide their work and accelerate decisions — not as a legal authority, but as an independent first opinion made before any dispute arose. Its value comes from timing and independence, not from being infallible.

These layers serve different purposes and can be relied on for different things. The hash commitment is a hard guarantee regardless of whether the AI analysis was correct. For signed documents, the source integrity layer adds a further guarantee that predates the submission itself.

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

**Due diligence**
- Any material — contracts, financial statements, code, patent applications — can be partially disclosed: the AI characterises the content and stamps a verdict, while the hash commits to the full document. If fraudulent or misleading data was provided, the hash exposes it later
- Startups and inventors seeking investment can disclose enough for an AI verdict ("novel approach, coherent technical claims") without surrendering full intellectual property
- Investors can be required to stamp proof of funds or portfolio history — bilateral verification before the first meeting, without a trusted intermediary
- Suppliers, vendors, and counterparties can be held to their representations at the time of negotiation

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

**Personal credentials**
- Any email from a trusted domain can be stamped: degree completion notices, employer welcome emails, electronic contracts — DKIM proves the sender's domain, Leima timestamps the content
- Portable proof of employment, education, or institutional relationships without requiring the issuing party to participate in verification

**Economic inclusion**
- Small-scale farmers and fishing cooperatives building stamped records of sales, inputs, and activity — usable as evidence for microfinance or access to premium markets
- Professionals in jurisdictions without reliable registries establishing verifiable work history and agreements from email records alone

**Research and due diligence**
- Timestamping findings before publication to establish priority
- Verifying that a cited source says what a paper claims it says, at the time of writing
- Codebase reviews: stamping a claim against a specific commit snapshot

**Prediction markets and information credentialing**
- A tipster on a platform such as Polymarket can prove they possessed a document supporting a claim *before* the outcome was known — without revealing the document's contents. The stamp establishes the existence and date of the evidence; the verdict characterises what it shows; the hash commits to the full document for later disclosure if needed
- This creates a primitive that did not previously exist: *provable knowledge without disclosure*. A person can credibly signal "I know something material about this event" in a way that can be verified after the fact, within the bounds of applicable law

For extended examples and context see [USECASES.md](USECASES.md).

---

## Why this matters

Leima's value does not depend on AI being infallible. It rests on two separate foundations.

The first is cryptographic. The SHA-256 hash of the document is sealed permanently before anyone knows there will be a dispute. If the document is later altered or substituted, the hash exposes it — provably, without interpretation. In a due diligence context, a hash mismatch is not a matter of opinion: it is evidence of tampering, and with it a contractual or criminal case. No court needs to evaluate an AI verdict for this to hold.

The second is practical. AI applies the same reasoning process to the same input every time, without financial interest, fatigue, or social pressure. The analysis is not infallible — LLMs can misread documents and hallucinate — but it was made independently, before any dispute arose, and it is sealed. An insurance adjuster, a lender, or a counterparty in due diligence can use it to orient their own judgment faster and more cheaply than commissioning a human review. They do not need to treat the verdict as authoritative; they use it as a documented first opinion made at the right moment.

Raw AI output alone is worth little — it can be regenerated, altered, or denied. Leima changes this by sealing the analysis cryptographically the moment it is made and storing it permanently on Arweave.

For centuries, verifying a claim against a document required a human: expensive, partial, and available only to those who could afford one. A notary confirms existence, not meaning. A lawyer is a party. This created a world where thorough verification was a luxury — where citation checks were skipped, where disputes were settled by whoever had better representation rather than better evidence.

AI changes the economics entirely. Thousands of source references checked overnight, for cents per claim. Documents analysed at consistent quality regardless of who owns them or what is at stake. Sensitive materials examined without the result being gossiped, remembered, or sold.

Leima is the infrastructure that makes this analysis permanent and verifiable. The verdict is not just an AI output — it is a sealed record: this document, this claim, this analysis, this moment. Anyone can verify it independently, without trusting Leima itself.

We call this role the **neutral witness** — an AI that has no stake in the outcome, no memory of previous cases, and no relationship with either party.

This matters most in low-trust and chaotic societies where institutions are weak, corruption is common, and a small business owner cannot afford a lawyer or assume that paperwork will be honoured. Combined with C2PA-signed images and videos and crypto-native financial instruments, tamper-proof AI verdicts could provide enough verifiable evidence for someone to secure a business loan, pass due diligence with an international buyer, or sell their products on global markets — without needing a functioning notary, a reliable court system, or a bank that trusts them. The infrastructure of trust that wealthy societies take for granted can be approximated, for the first time, at near-zero cost.

There is a paradox here. In wealthy countries with strong institutions — Germany, for example — a notary is not just a tradition but a legal requirement for certain transactions. Leima does not compete there, because legislation protects the incumbent. In countries where that infrastructure never existed, there is nothing to compete with. A farmer in Kenya or a contractor in Ukraine does not bypass the notary system; it was never there to bypass. The table is empty, and infrastructure builds directly on what is available now.

This is the inverse of the usual leapfrog story. Normally, developing countries skip outdated technology — landlines, then straight to mobile. Here, it is developed countries that are locked in, because their existing institutions were built before better alternatives existed and are now protected by the rules those institutions helped create. If the notary system were designed from scratch today, it would not look like a notary.

---

## A public good

The value Leima creates depends on its neutrality. A neutral witness cannot have a financial stake in verdicts. A permanent record loses meaning if the infrastructure can be shut down by a single owner. These properties are structurally incompatible with a standard commercial model — the moment a company controls the service and needs to extract revenue from it, the neutrality that makes it useful begins to erode.

The natural form for this kind of infrastructure is a commons: open source, governed collectively, funded in a way that does not create incentives to alter verdicts or restrict access. Token-based governance is one credible path — a protocol token that funds ongoing development and infrastructure costs while keeping the service accessible to anyone, with governance rights distributed to holders rather than concentrated in a founding entity. This is how protocol-layer infrastructure like Ethereum and Uniswap is structured: no single party controls it, and no single party can shut it down.

The goal is a service that is free or near-free to use, sustainable without a corporate owner, and governed by no one with an interest in its verdicts. That is the only governance model consistent with the role of a neutral witness.

---

## Contributing

Leima is designed to be a public good. That only works if it is built and governed by more than one person.

Contributions of any kind are welcome: code, bug reports, use cases, feedback on the trust model, testing against real documents, integrations, translations, or simply spreading the word to someone who would benefit from this.

**Contributions are recorded permanently.** Every accepted contribution — code merged to main, a documented use case, a verified bug, a substantive improvement to the trust model or documentation — is stamped to Arweave using Leima itself. The record is immutable: who contributed, what they contributed, and when. This is not a spreadsheet that can be edited later.

**If the project is ever tokenised, the on-chain contribution history is the basis for distribution.** The intent is that early contributors are not forgotten. If governance tokens are issued to fund infrastructure and keep the service free, the stamped record determines each contributor's share — evaluated with AI assistance against the contribution history at that time. This is not a guarantee; it is a commitment that is credible precisely because the record cannot be altered.

Early contributors take on more uncertainty than later ones. That is acknowledged, and it is part of what the record captures.

The long-term goal is for Leima to become independent of any individual or founding group entirely. A neutral witness that depends on specific people to remain honest is only as trustworthy as those people. The target state is infrastructure governed by protocol and community — where no single person or organisation can alter verdicts, restrict access, or shut it down. Getting there requires building the contributor base, the governance model, and the technical decentralisation in parallel. That process starts with the first contributors.

To get involved: open an issue or pull request on GitHub, or contact via the repository. No contribution is too small to record.

---

## Document sources

| Source | Notes |
|--------|-------|
| PDF upload | Direct file upload. If the PDF contains a digital signature, Leima verifies it using RFC 3161: signer identity, trusted timestamp, and document integrity are extracted and included in the verdict |
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
    { "label": "Supporting evidence", "text": "..." },
    { "label": "Contradicting evidence", "text": "..." },
    { "label": "Verdict", "text": "..." }
  ],
  "input_hash": "a3f1c8...(64-char hex)",
  "verdict_hash": "9e2d47...(64-char hex)",
  "timestamp": "2026-05-12 10:00:00 UTC",
  "model": "gemini-3.1-flash-lite",
  "stamp": { "tx_id": "...", "url": "https://gateway.irys.xyz/..." },
  "manifest": { ... }
}
```

---

## Trust model

For a complete description of what data Leima collects, where it goes, and what triggers re-consent when code changes, see [POLICY.example.md](POLICY.example.md).

**Two layers: hash commitment and AI verdict**
Leima's legal and practical weight comes from two mechanisms that work independently. The hash commitment is a hard guarantee: if anyone alters a document after it has been stamped, the SHA-256 mismatch is provable without any reliance on AI. A mismatch is grounds for a contractual or fraud claim regardless of whether the AI analysis was correct. The AI verdict is the practical layer: an independent opinion made before any dispute arose, useful for guiding human decisions — an insurance adjuster's assessment, a lender's judgment, a due diligence review — without needing to be treated as a legal authority. Do not conflate the two: the hash commitment stands on its own.

**AI reliability**
Leima's verdicts are only as reliable as the underlying language model. LLMs can misread documents, miss context, or produce confident-sounding but wrong conclusions. Treat the verdict as a documented first opinion, not a final judgment. The full AI prompt logic is isolated in `neutral_witness.py` — a single file that anyone can read to verify exactly what instructions are given to the model.

**Email authentication**
For emails, Leima validates the DKIM signature cryptographically (result: valid / invalid / none) and records it in the manifest. A valid DKIM result confirms the message was not altered in transit and was sent by the claimed domain — but does not prove the human sender is who they claim to be. The neutral witness is instructed to assess sender identity credibility based on DKIM result, domain consistency, and other available signals, and to state its assessment explicitly in the verdict.

**Document sensitivity**
Documents are sent to Google's Gemini API for analysis. For sensitive materials — personal data, unreleased financials, confidential contracts — consider anonymising or redacting the document before submitting. Replace names, account numbers, and identifying details with placeholders where the claim can still be evaluated without them.

For the email input, consider redacting or summarising message bodies that contain third-party personal data before submitting — particularly in email threads where other parties' information appears.

**What Arweave guarantees**
Arweave is a decentralised storage network designed for permanent data. Unlike cloud storage where a provider can shut down or delete data, Arweave stores each piece of data across many independent nodes. Anyone can run a node and is paid from an endowment funded by the original upload fee. The endowment is sized on the assumption that storage costs decline continuously — and as costs fall, the same endowment covers an ever-longer period. The economic model targets storage on the order of centuries.

In practice, permanence also has a simpler backstop: in twenty years, everything currently stored on Arweave will fit on a single consumer drive. The cost of keeping it is negligible; the incentive to do so — mining rewards, archival interest, or simply not needing the space for anything else — is sufficient. Data that exists in many places and costs almost nothing to keep tends to survive.

The blockchain record proves that a specific analysis of a specific document existed at a specific time, and that neither has been altered since. It does not prove the analysis is correct, that the document is authentic, or that the claim is true in any legal sense.

**You do not need to trust the authors**
Leima is open source. You can read the code, verify that the prompts and logic match what is described here, and run your own instance. Trust in the software does not require trust in the people who wrote it.

**Deployment integrity monitoring (POIDE)**
Open source code is auditable — but only if the running code is the same as the published code. Leima implements POIDE (Proof of Intended Deployment): every push to `main` triggers an automated code review against `POLICY.example.md`; Render auto-deploy is disabled, so the deploy hook fires only if the review passes. Five GitHub Actions workflows then run on a staggered schedule, together achieving one-minute polling resolution, querying the Render API for the deployed commit and the GitHub API for the repository HEAD, and publishing the result publicly. Code that fails the review never reaches production. Anyone can verify deployment integrity without credentials, at any time.

`POLICY.example.md` is permanently stored on Arweave ([`6Fviz2M3kx6BTkkn2fHrdJ7qtX9hRxV476f31WvUDqvR`](https://gateway.irys.xyz/6Fviz2M3kx6BTkkn2fHrdJ7qtX9hRxV476f31WvUDqvR)). Every code review is measured against this immutable copy — not the file in the repository, which could in principle be edited. The policy the AI uses cannot be quietly changed after the fact.

See [POIDE.md](POIDE.md) for a full description of the protocol, the current implementation, the longer-term vision, real-world incidents where deployment transparency would have helped (XZ Utils, PHP git compromise, Picreel), and how POIDE relates to existing approaches such as Sigstore and Meta Code Verify.

One residual trust assumption remains: Render, as the hosting provider, could in principle report a false commit hash while running different code. This is a different category of risk than ordinary vulnerabilities — it requires the hosting provider to actively conspire against users. See POIDE.md for a discussion of how this could be mitigated.

**Planned: privacy-committed AI providers**
A future option will allow switching to AI providers that operate under strict, publicly auditable privacy commitments — where documents are contractually guaranteed not to be used for training or retained after the request. The stamping and verification layer remains identical; only the AI backend changes. This preserves the trust model while reducing reliance on Google's standard API terms.

---

## Threat model

| Threat | Covered? | Notes |
|--------|----------|-------|
| Verdict modified after creation | Yes | Hash mismatch detected on validation |
| Source file modified after creation | Yes | Hash mismatch detected on validation |
| Manifest altered locally | Yes | Compared against immutable Arweave copy |
| Code violates stated data policy | Yes | AI audits all source files against POLICY.example.md on every commit; workflow fails and POIDE turns red if a violation is found |
| Malicious code change slipped in unnoticed | Yes | Every commit triggers a code review; Render auto-deploy is disabled — deploy hook fires only on review success; POIDE polls every minute; Render returns full deploy history so no deploy can be hidden retroactively |
| Deployed commit not present in git repository | Yes | History check verifies every recent Render deploy commit exists in GitHub; mismatch is recorded in status.json and shown in Tampermonkey userscript |
| Hosting provider (Render) swaps running code silently | Partly | POIDE detects mismatches within ~1 minute; Render API reporting the actual running commit honestly is a residual trust assumption |
| Leima lies during original run | Partly | Full prompt logic is isolated in `neutral_witness.py` and audited on every commit |
| AI verdict is wrong | Partly | The hash commitment stands regardless — document tampering is still provable. The AI analysis is a first opinion, not a legal authority |
| Document is fake before upload | No | Leima timestamps existence, does not authenticate origin |
| Email body altered after sending | Partly | DKIM validates signed headers and body scope — coverage depends on sender configuration |
| Human sender identity false | No | DKIM proves domain, not individual identity; LLM assesses credibility signals |
| Sensitive data exposure to AI provider | Partly | Redaction recommended; privacy-committed AI provider planned |

---

## Economic case

Deployment transparency has historically required either expensive infrastructure or accepting "trust us" as the answer. This has had a real cost.

**A provable record of intent.** Every POIDE check is written permanently to Arweave. This means a small company can at any point in time prove — to a customer, a regulator, an auditor, or a court — exactly what source code they were asking their hosting provider to run, and when. They cannot prove that the hosting provider executed it exactly as instructed; that residual assumption is documented openly. But the record of intent is permanent, tamper-proof, and independently verifiable without asking the company for anything. For regulated industries or contractual disputes, this is a meaningful guarantee that previously required expensive third-party auditing infrastructure.

**Lost opportunity.** Small operators have had no mechanism to demonstrate that the code they claim to run is the code actually running. Large players substitute brand reputation for technical transparency. This locks small operators out of trust-sensitive markets — legal, financial, medical, research — not because their code is worse, but because they lack the tools to prove it. Use cases that could be automated have stayed manual. Services that could exist have not been built.

**Why not TEE?** Hardware-level trusted execution environments (Intel SGX, AMD SEV) provide the strongest possible guarantee: cryptographic proof of what code is executing in memory. They also cost orders of magnitude more to implement and require hosting provider cooperation. The question is whether that cost is justified by the risk it covers.

The realistic threat hierarchy is not symmetrical. Maintainer credential theft — phishing, SIM-swapping, malware, insider action — is a routine occurrence across the software industry. For a small project, the realistic annual probability is 1–5%. A hosting provider infrastructure breach deep enough to silently swap running code is a different category of event: it has not been publicly documented at major managed hosting providers, and would require capabilities well beyond opportunistic attacks. The realistic annual probability is orders of magnitude lower — and deliberate collusion by a company with investors, legal obligations, and hundreds of other customers is lower still.

POIDE covers the large realistic risk. TEE would additionally cover the small theoretical one — at roughly 1000x the cost, to address a threat that is roughly 100–1000x less likely. The marginal cost per covered risk unit is prohibitive.

**Comparison.**

| Approach | Cost | What it proves |
|---|---|---|
| Fully on-chain (Ethereum) | Very high per operation | Execution is public and deterministic — but LLMs cannot run on-chain |
| TEE (SGX/SEV) | 50k–500k+ to implement | Code executing in memory matches the published source |
| Formal audit | 20k–100k+, one-time snapshot | Code complies with stated policy at a point in time |
| POIDE | Near zero | Hosting provider was instructed to run the audited commit; continuous, permanent record |
| Nothing | Zero | "Trust us" |

For AI applications specifically, fully on-chain execution is not a realistic option: language models cannot run in the EVM, and document processing at this scale is impossible on-chain. Given that off-chain computation is unavoidable, POIDE represents the practical optimum — meaningful attestation with existing building blocks, deployable over a weekend, with a permanent audit trail that no retroactive action can alter.

---

## Stack

- **Backend** — FastAPI + Uvicorn
- **AI** — Google Gemini 3.1 Flash Lite
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

**Email notary (optional).** To enable the BCC notarisation flow, add:

```env
NOTARY_IMAP_HOST=imap.gmail.com
NOTARY_IMAP_USER=stamp@yourdomain.com
NOTARY_IMAP_PASSWORD=your-app-password
NOTARY_SMTP_HOST=smtp.gmail.com
NOTARY_SMTP_PORT=587
NOTARY_SMTP_USER=stamp@yourdomain.com   # defaults to NOTARY_IMAP_USER
NOTARY_SMTP_PASSWORD=your-app-password  # defaults to NOTARY_IMAP_PASSWORD
NOTARY_FROM=Leima <stamp@yourdomain.com>
NOTARY_POLL_TOKEN=random-secret-string  # authenticates POST /notary/poll
LEIMA_URL=https://yourdomain.com        # used to build verify links in outgoing emails
```

Trigger polling by calling `POST /notary/poll` with header `X-Notary-Token: <NOTARY_POLL_TOKEN>` — from a cron job or Render scheduled task.

```bash
uvicorn main:app --reload
```

---

## Validation

**AI verdict flow.** Any party who receives the three files can verify integrity at `/validate`:

- SHA-256 of `source` matches `manifest.json → input.sha256`
- SHA-256 of `verdict.pdf` matches `manifest.json → verdict_pdf.sha256`
- The stamp record fetched from Arweave matches the local `manifest.json` (minus the `stamp` field)

If all three pass, the verdict is authentic and unmodified.

**Email notary flow.** Each notarised email contains a direct link to `/validate?tx=<arweave_id>`. Open the link, upload the `original.eml` attachment from the same email, and the page confirms that the email hash matches the Arweave record and that DKIM was valid at the time of notarisation. No other files are needed.

---

## Deployment

Connect the GitHub repository in the Render dashboard. Create a **Web Service** with:

- **Build command:** `pip install -r requirements.txt`
- **Start command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`

Set all environment variables from `.env.example`. Switch `IRYS_NETWORK` to `mainnet` and remove `IRYS_RPC_URL` for production.

**Disable Render auto-deploy.** In the Render service settings, turn off automatic deploys from git. Deployment is handled by the GitHub Actions workflow instead — a push to `main` triggers the code review, and the deploy hook fires only if the review passes. Set the deploy hook URL as a GitHub Actions secret named `RENDER_DEPLOY_HOOK`. Code that fails the review is never deployed.

To enable the email notary, add a **Cron Job** service pointing at `POST /notary/poll` with the `X-Notary-Token` header, running at whatever interval you want (e.g. every minute).

---

## Deployment integrity (POIDE)

The full trust chain on every commit:

```
push → code_review.yml → AI audits code vs POLICY.example.md
                                   ↓ pass only
                             RENDER_DEPLOY_HOOK → new commit live on Render
                                   ↓
cron (every minute) → deployment match? → review passed? → no deploy in progress?
                                                        → status.json → gh-pages (public)
```

Five GitHub Actions workflows run on a staggered schedule and together poll deployment status every minute. Each run checks three conditions: the live Render commit matches the GitHub repository HEAD, the latest automated code review passed, and the deploy history contains no commits absent from git. Results are published to the `gh-pages` branch as `status.json`.

Because Render auto-deploy is disabled, a commit that fails the code review is never deployed — the server continues running the previous commit until a passing commit is pushed.

Before submitting sensitive documents, verify that the POIDE Code Review and the five POIDE A–E workflows show green on the [Actions tab](../../actions). See [POIDE.md](POIDE.md) for the full protocol description.

---

## Independent verification (verify.py)

`verify.py` is a standalone script you can run from anywhere — on your own machine, without contacting the Leima service at all — to confirm that the monitoring infrastructure has not been tampered with.

```bash
pip install requests
python verify.py
```

It checks two independent sources for each monitored file:

1. **Git history (GitHub API)** — confirms when each file was last changed. This record is maintained by GitHub, not by Leima, and cannot be altered by the service operator.
2. **Arweave record** — fetches the latest POIDE check result from Arweave (permanent, immutable) and compares the stored file hashes to what is currently on GitHub.

If both sources agree and the files are unchanged, this provides a meaningful guarantee: the monitoring code has been auditable and consistent, any commit mismatch since the last change would have been detected and recorded, and the monitoring code itself has passed automated AI code review on every push.

The output also shows the last commit mismatch — when it occurred, which commit was involved, and when it resolved — so you can assess at a glance whether anything unexpected happened while you were away.

**Pinning to a specific trusted moment.** If you note down the Arweave TX from a run you personally verified, you can compare the current state against that exact historical snapshot:

```bash
python verify.py <tx_id>
```

Arweave records cannot be altered retroactively. A TX you trusted six months ago is still exactly what it was then — and if the current files match it, nothing has changed in between.

---

## Self-characterisation for due diligence (bundle_source.py)

`bundle_source.py` bundles the entire codebase — source files, `README.md`, `POLICY.example.md`, and `requirements.txt` — into a single `source_bundle.txt` ready for Leima upload.

```bash
python bundle_source.py          # HEAD
python bundle_source.py abc1234  # specific commit
```

Upload `source_bundle.txt` to Leima with a claim such as:

> *"This application source code does not send user documents to any third-party service other than Google Gemini."*

Leima produces a hash of the bundle, an AI characterisation, and a permanent Arweave stamp. The stamp can be shared with investors, partners, or auditors as independently verifiable evidence of what the code does — without revealing the source itself.

Because `README.md` and `POLICY.example.md` are included first, the AI reviewer has full context about the project's architecture and data policy before reading the code.

The claim and AI analysis are permanently public on Arweave. To anonymise specific details in the result — company names, individuals, amounts — add a privacy directive to your claim: *"keep [company name] private"*. The AI will replace those details with generic placeholders throughout its analysis.

---

## Developer pre-push hook

A git hook prevents accidentally pushing during an active commit mismatch or mid-deploy, which would widen the mismatch window.

Two files: `hooks/pre-push` is a shell wrapper that finds Python automatically (tries the project venv first), and `hooks/pre-push.py` contains the logic.

```bash
cp hooks/pre-push .git/hooks/pre-push
chmod +x .git/hooks/pre-push   # Linux/macOS only
```

Before every `git push`, the hook fetches the latest POIDE status. If a deploy is in progress it waits (up to 3 minutes). If a mismatch is active it blocks the push and explains why. Override with `git push --no-verify` if needed.
