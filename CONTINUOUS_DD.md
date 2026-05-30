# Continuous Corporate Due Diligence

Conventional due diligence produces a snapshot. An auditor or analyst reviews documents at a point in time, forms a judgment, and issues a report. The report is already partially out of date when it is published. It covers what was disclosed, not what is actually happening, and it reflects the interests of whoever commissioned it.

Continuous due diligence is a different model: a permanent, independently verifiable record of a company's financial and operational state, updated continuously, accessible to any authorised counterparty at any time. Not *here is last month's report* but *here is the ongoing observation history and what the AI has found in it.*

---

## The evidence package

A company operating under continuous due diligence publishes — or makes available to specific counterparties — a continuously updated evidence package. The package is not a curated presentation. It is a structured record of raw data pulled from operational systems, hashed at the moment of retrieval, analysed by AI, and stamped permanently.

The package can include any combination of:

- Bank account balances and transaction flows
- Cash flow statements generated directly from accounting software
- Accounts receivable and payable ledgers
- ERP or accounting system exports (Procountor, Netvisor, SAP, QuickBooks, and others)
- Invoicing data — issued and received
- Debt schedules and credit facility utilisation
- Contract lists with counterparty identities and values
- Supply chain data and inventory snapshots
- Web-rendered views of live dashboards and portals, captured via the Inspector browser protocol

Each source in the package is recorded with:

- A cryptographic hash of the raw data at the moment of retrieval
- A timestamp and the retrieval method
- The origin — which system, which account, which API endpoint
- The AI analysis of that source
- Any anomalies or inconsistencies flagged

Nothing in the package can be silently altered after the fact. The hash commits to the exact state of the data at the moment it was captured.

---

## Source listing and auditor confirmation

The most important transparency feature of the package is the explicit source list. Every source used in the AI analysis is named: which accounting system, which bank accounts, which payment processors, which ERP modules.

A counterparty reviewing the package sees not only what was found but what was looked at. The gap between the listed sources and what an informed party would expect to see — a missing bank account, an absent payment processor, an unnamed entity — is itself information.

An auditor can review the source list and provide a confirmation scoped specifically to coverage:

> *"Based on our review, the data sources listed in this package appear to constitute the company's material financial records and primary bank accounts as of the date of this statement."*

This is a different, narrower, and cheaper engagement than a full audit. The auditor is not certifying the accuracy of every figure. They are certifying that the right sources were included — that the evidence package is not constructed from a cherry-picked subset of the company's actual financial activity.

The AI handles the analysis. The auditor handles the coverage question. The combination provides assurance that was previously available only from a full-scope engagement.

---

## AI as a continuous inconsistency detector

The AI's role in continuous due diligence is not to render a verdict on the company's health. It is to identify what does not fit.

On each update cycle, the AI:

- Compares the current data against prior periods and flags deviations
- Checks internal consistency across sources — whether invoicing data is consistent with bank receipts, whether inventory levels are consistent with purchase orders, whether payroll is consistent with headcount
- Identifies patterns that typically precede financial distress: deteriorating receivables, concentrating revenue, increasing payables relative to cash
- Flags new entities, accounts, or relationships that were not present in previous periods
- Notes the absence of expected data — a month with no invoicing, a bank account that stopped transacting

The AI is not always right. Its flags are signals, not findings. But the signals are produced continuously, consistently, and without any stake in the outcome. A human reviewer examining a series of AI-flagged anomalies over twelve months has a qualitatively different picture of a company than one reviewing a single point-in-time audit.

---

## Trust through history

A single evidence package, however well constructed, proves only what was true at one moment. The value of continuous due diligence accumulates over time.

A counterparty reviewing a company with twelve months of continuous evidence packages can observe:

- Whether the AI's characterisations have been consistent or erratic
- Whether figures that appeared in early packages match what later audits confirmed
- Whether the source list has remained stable or whether accounts and systems have appeared and disappeared
- Whether anomalies flagged by the AI were subsequently explained or remained unexplained

If an auditor later confirms that the AI's analysis during a given period was substantially accurate — that the figures it reported reflected actual financial activity — that confirmation retroactively strengthens every package in that period. The history becomes more reliable in both directions as subsequent evidence accumulates.

This is the mechanism by which continuous due diligence produces the equivalent of a credit track record without requiring a credit history. A company that has maintained a clean, consistent evidence package for two years, with periodic auditor coverage confirmations, has demonstrated something that no single point-in-time audit can establish: that its reported situation has been honest over time.

---

## Lightweight trust infrastructure for small companies

Large companies access institutional trust through expensive mechanisms: Big Four audits, credit ratings, exchange listing requirements, regulatory filings. These are not available to small companies at meaningful cost.

A small company operating under continuous due diligence has access to a different class of evidence, produced at near-zero marginal cost:

- A permanent, tamper-proof record of its financial history
- AI analysis that runs continuously without requiring management time
- Auditor confirmation scoped to coverage rather than full-scope verification
- A verifiable evidence package that any counterparty can review

This does not replace formal audit for purposes that legally require it. It fills the gap that currently exists between "trust us" — which is what most small companies offer — and full institutional verification — which most small companies cannot afford.

For a founder seeking investment, a company seeking a supplier credit line, or a small business competing for a contract that requires financial references, a two-year continuous due diligence history is meaningfully stronger evidence than a single year-end balance sheet.

---

## What counterparties can verify

Anyone reviewing the evidence package can independently confirm:

1. That each source hash matches the raw data provided — the data has not been altered since retrieval
2. That each package is stamped on Arweave — the record is permanent and predates any dispute
3. That the AI analysis was applied to the data as represented — the analysis cannot be revised retroactively
4. That the source list names real, verifiable systems — the coverage can be checked against what the company's industry would typically use

The Arweave record means that the history cannot be rewritten. A company cannot retrospectively remove an anomaly that the AI flagged six months ago, or add a source to a package that was published without it. The record is what it was at the time it was published.

---

## What this does not prove

Continuous due diligence is transparent about its limitations. The system does not claim:

- That the data provided by operational systems is itself accurate — a sufficiently motivated party could falsify the underlying systems before data is pulled
- That the source list is complete — the auditor confirmation addresses coverage, but an undisclosed entity or account is not detectable from the package alone
- That the AI's analysis is correct — it is a signal, not a finding, and it operates on what was provided

These limitations are real. They are also present in conventional due diligence, which faces the same constraints with higher cost and lower frequency. The continuous model does not eliminate these risks. It makes deviation from honest reporting more visible, more persistent, and harder to sustain undetected over time.

---

## The broader principle

Continuous due diligence is one application of a general infrastructure: raw data retrieved from operational systems, hashed at the moment of retrieval, analysed by AI, and permanently recorded. The same infrastructure underlies the Inspector Protocol for physical assets, the browser-based session capture for financial account verification, and Leima's document stamping.

What changes between applications is the source: a drone, a browser session, an accounting system API. What remains constant is the trust model: observations are made, hashed, analysed, and sealed at the moment they occur. The record cannot be altered. The history accumulates. Trust follows from the consistency of that history over time.

The ambition is an observation infrastructure for economic activity — not a system that certifies truth at a single moment, but a system that makes sustained dishonesty progressively harder to maintain.
