# Leima — Use Cases

---

## Due diligence

Due diligence involves one party evaluating another's claims before committing to a transaction. The fundamental problem is that the party being evaluated has an incentive to present their situation favourably, while the evaluating party needs enough information to make a judgment without necessarily receiving everything. Leima addresses both sides of this problem.

**Immediate cryptographic verification.** Due diligence has traditionally meant collecting documents and verifying their authenticity weeks or months later — a manual process with significant lag. Leima compresses this into seconds.

For documents that carry cryptographic provenance, verification happens at submission: a PDF with a digital signature is checked against its RFC 3161 trusted timestamp, the signer's certificate is extracted, and any post-signing modification is detected immediately. The verdict states whether the document is intact or tampered — a hard cryptographic finding, not an AI opinion. For documents without signatures, the Arweave hash commitment means there is no dispute later about what was submitted: the exact content is sealed at the moment of analysis. Both paths eliminate the gap between "documents received" and "documents verified."

**Partial disclosure with hash commitment.** Any material — a contract, a financial statement, a codebase, a patent application — can be partially disclosed. The submitting party shows the evaluating party a redacted or summarised version, and Leima stamps an AI verdict characterising what the document contains: its nature, scope, and the specific claim being evaluated. The cryptographic hash of the full, unredacted document is recorded in the stamp.

If the submitting party later claims they provided different information, or if it emerges that the disclosed version misrepresented the full document, the hash exposes the fraud: the stamp proves exactly what was shown, when, and what the AI concluded from it. The evaluator cannot later claim they were not informed; the submitter cannot later claim they showed something different.

This works for:
- Financial statements where some figures are commercially sensitive
- Contracts where the counterparty's identity is confidential
- Source code where the core algorithm is proprietary but the absence of security vulnerabilities can still be evaluated
- Regulatory filings where certain sections are under embargo

**Investment due diligence — bilateral verification.** When a startup or inventor seeks investment, both parties have legitimate verification needs that are currently difficult to satisfy without expensive intermediaries.

The startup needs to demonstrate that their idea is novel and technically sound without fully disclosing it to someone who might not invest and might later use the information. Leima can stamp an AI verdict against a partial disclosure: *"the submitted material describes a novel approach to X; the technical claims appear coherent and the market problem is credibly stated."* The investor receives a dated, independently verifiable characterisation without receiving the full intellectual property.

The investor needs to demonstrate that they are a legitimate source of capital and not simply gathering ideas from applicants. A startup can request that the investor stamp a claim against their portfolio records or proof of funds: *"this entity has made investments of this scale in this sector."* The stamp provides assurance that the investor is who they say they are, without requiring the startup to take the investor's word alone.

Both parties can demand these stamps before the first substantive meeting. The result is a mutual due diligence record — each party has committed to a characterisation of themselves, timestamped before the negotiation began, which can be referenced if the relationship later becomes disputed.

**Supplier and vendor evaluation.** Before entering a supply agreement, a buyer can request that a supplier stamp claims against their own financial statements, quality certifications, or production capacity records. The AI characterises the evidence; the hash commits to the specific documents provided. If the supplier later fails to perform and disputes what was represented during the negotiation, the stamp is the reference point.

**Regulatory and compliance disclosure.** Organisations subject to regulatory review — for licensing, accreditation, or audit — can stamp their submissions at the time of filing. This creates a record of what was disclosed, in what form, on what date, independent of the regulator's own records. Useful in jurisdictions where regulatory processes are slow, opaque, or subject to dispute.

---

## Consumer documentation

**Service records and receipts.** When a service provider sends a receipt by email — a car service, a repair, an appliance installation — the owner can stamp that email in Leima. The DKIM signature confirms the message came from the service provider's domain. The stamp creates a permanent, tamper-proof record: this work was done, on this date, confirmed by this provider. Useful for warranty claims, insurance disputes, and resale documentation where a buyer wants to verify the service history.

**High-value vehicle and equipment maintenance.** A Ferrari engine overhaul can cost €100,000. At that level, both parties have a strong interest in a tamper-proof record: the owner needs to prove what was done and when, the workshop needs to prove it delivered what it invoiced, and any future buyer will pay a significant premium for a service history they can actually verify. A stamped email from the workshop — DKIM-confirmed from their domain, with the work order attached — creates a record that cannot be silently altered. If a dispute arises about what was or was not done, the hash settles it. The same applies to any high-value asset with meaningful maintenance history: classic cars, race vehicles, aircraft, marine engines, specialist industrial equipment.

**Insurance evidence.** Purchases and valuations sent by email — a jeweller's appraisal, a specialist's estimate, a purchase confirmation — can be stamped at the time of receipt. If the item is later lost, stolen, or damaged, the stamp proves the item existed and was valued at a specific amount on a specific date, before the claim arose. The record cannot be backdated.

**Subscription and terms changes.** When a service changes its terms of service or pricing and notifies users by email, stamping that notification creates a dated record of what was agreed or communicated at that time — useful in disputes about what was promised before a change.

---

## Email notary

The AI verdict flow requires a deliberate action: a user uploads a document, poses a claim, and receives a stamped result. The email notary works differently — it operates automatically, as a side effect of ordinary email communication, with no change in behaviour required from either party.

**How it works.** A sender adds `BCC: stamp@leima.fi` to any email. Leima receives the message, verifies the DKIM signature (confirming that the message genuinely originated from the sender's domain and was not altered in transit), hashes the full email including any attachments, stamps the hash on Arweave, and forwards a notarized copy to the real recipient — the address in the `To:` field. The recipient receives the original message plus a certificate containing the hash, the DKIM result, a permanent Arweave link, and a one-click verification URL.

The sender's domain is the trust anchor. DKIM is not a claim the sender makes about themselves — it is a cryptographic assertion made by their mail server, verifiable against their published DNS records. A notarized email from `huolto@ferrarikeskus.fi` carries the same institutional weight as a letter on headed paper, but with a tamper-proof timestamp and an immutable record that cannot be lost, backdated, or silently altered.

**Receipt and service documentation.** A car workshop, appliance repair company, or specialist service provider adds one BCC address to their outgoing email template. Every customer automatically receives a notarized copy of their receipt, work order, or service confirmation — without the customer needing to do anything. When the car is sold, the buyer can verify the service history by uploading the `.eml` file and checking the Arweave record. The record exists independently of the workshop, the email provider, or the customer's inbox.

**Dispute prevention.** The notarization is symmetric: it proves what was said, not who was right. A message from a landlord stating that a repair was completed, or from a contractor confirming the scope of work, becomes a reference point that neither party can later reinterpret. This is most valuable before a relationship deteriorates — the record captures the agreed state before either side had an incentive to revise it.

**Due diligence correspondence.** Investors and founders conducting due diligence exchange significant commitments by email — term sheet summaries, representations about portfolios or technology, confirmations of financial standing. Adding BCC to this correspondence notarizes the exchange automatically. If a dispute later arises about what was represented before the deal was signed, the notarized record provides the reference point without requiring either party to have anticipated the dispute.

**High-value resale.** For any asset where service history affects value — vehicles, instruments, machinery, art — a body of notarized emails from verified service providers, appraisers, and previous owners builds a chain of custody that a buyer can independently verify. The verification requires only the `.eml` file and the Arweave link included in the notarized copy.

**Verification.** Each notarized email includes a direct link to `leima.fi/validate?tx=<arweave_id>`. Anyone with the original `.eml` file can verify in one step: open the link, upload the file, and receive an immediate confirmation that the email hash matches the Arweave record and that DKIM was valid at the time of notarization.

---

## Art, craft, and collectibles

**Proof of creation.** An artist can establish provenance by emailing documentation of a new work — photographs, sketches, process notes — to themselves or to a trusted party, and stamping that email. The DKIM signature confirms the date and sender. This creates a verifiable record that a specific person created a specific work on or before a specific date: harder to forge than a signature on a canvas, and timestamped independently of the artist's own claim.

**First-owner transfer.** When a work changes hands for the first time, the artist can email the buyer directly with a description of the piece, any provenance documentation, and a statement of transfer. Stamping that email creates a permanent record of the first transfer — linking the artist's identity (via DKIM domain) to the buyer, the work, and the date. Subsequent owners can verify the chain.

**Creation process as evidence.** A series of photographs documenting the creation of a work — from blank canvas to finished piece — provides strong evidence of authorship. When taken with a **C2PA-enabled camera** (already available from manufacturers including Leica, Sony, and Nikon), each photograph carries a cryptographic signature from the camera itself, binding the image to the device, the GPS location, and the timestamp at the moment of capture. Leima can stamp a claim against this series: the combination of C2PA-signed images and a Leima verdict creates a provenance record that is difficult to fabricate even with access to AI image generation tools.

**Restoration and conservation.** A restorer can document the condition of a work before and after treatment by emailing a report with photographs to the owner or a registry. Stamping that email creates a dated, independently verifiable record of the work's state — relevant for insurance, for establishing the scope of the restoration, and for future buyers who want to understand the work's history.

**Collectibles and physical objects.** The same approach applies to any object with a verifiable identity: vintage instruments, watches, wine, historical artefacts. A specialist's email assessment, stamped at the time of receipt, becomes part of the object's verifiable history. Combined with a serial number or unique identifier, multiple stamped records over time build a chain of custody.

---

## Personal credentials and life events

Institutions routinely send emails that carry significant evidentiary weight: universities confirm graduation, employers welcome new hires and attach contracts, banks confirm account opening, government agencies send decisions. These emails are typically trusted because they come from a known domain — and DKIM validation makes that trust verifiable and recordable.

A private individual can stamp almost any significant life event for which they have received a credible email, without needing access to any official verification service.

**Educational credentials.** A university's confirmation email that a student has completed a degree — sent from the institution's domain, DKIM-validated — can be stamped to create a portable, independently verifiable record. The stamp does not replace the official certificate, but it provides a dated, cryptographically anchored reference that is harder to fabricate than a PDF and does not require the issuing institution to be involved in the verification.

**Employment.** A welcome email from an employer — informing a new employee of their start date, role, and onboarding details — establishes that an employment relationship began on a specific date, from a specific organisation. An electronic employment contract attached to or referenced in that email, stamped at the time of receipt, creates a record of the agreed terms that is independent of either party's later recollection. Useful in employment disputes, for visa and residency applications that require proof of employment, and for credit applications that require income verification.

**Proof of relationship with an organisation.** Any email from a company, institution, or authority — confirming a transaction, a membership, a decision, or a status — can be stamped to establish that the relationship existed at a specific point in time. This is useful wherever a person needs to demonstrate a connection that the other party may later deny or be unable to confirm (due to staff turnover, system changes, or organisational restructuring).

The underlying principle is that DKIM shifts the trust question from "do you believe this person?" to "do you trust this domain?" — a much easier question to answer for institutions with established reputations. Leima makes that shift permanent and auditable.

---

## Economic inclusion and access to markets

In many parts of the world, the barrier to economic participation is not capability or effort — it is the inability to prove what you own, what you have done, or what agreements you have made. Banks require collateral that cannot be documented. Buyers require certificates that cost more than the transaction is worth. Leima does not solve these problems entirely, but it lowers the cost of producing credible evidence to near zero.

**Small-scale agriculture.** A farmer who sells produce to a local market or cooperative typically receives payment confirmations, input purchase receipts, and delivery records by email or SMS. Stamping these creates a longitudinal record of economic activity: this farm produced and sold this volume, on these dates, to these buyers. Presented to a microfinance institution or an international buyer conducting due diligence, a body of stamped records can substitute for formal financial statements that the farmer has no means to produce.

**Fishing and maritime activity.** A fishing cooperative can stamp catch records, port authority communications, and buyer confirmations. Combined with GPS track data (where available), this creates an auditable activity record that can support applications for sustainability certification, access to premium markets, or credit.

**Land and property.** In jurisdictions without reliable land registries, proving ownership of a piece of land depends on a chain of documents — purchase agreements, witness statements, tax records — that are often paper-based, incomplete, or disputed. Stamping whatever documentation exists, at the time it is received, builds an incrementally stronger record. It does not replace a functioning registry, but it makes the available evidence harder to deny.

**C2PA-authenticated photographs and drone footage.** A farmer photographing a harvest, a cooperative documenting a fishing catch, or a smallholder recording the boundaries of their land with a drone can use C2PA-enabled cameras to produce images and video that carry a cryptographic signature from the device itself — binding each frame to the GPS location, the device identity, and the timestamp at the moment of capture. Stamping a Leima verdict against this material adds an independent AI characterisation: the size of a crop, the condition of a plot, the scale of an operation. The result is evidence that is difficult to fabricate even with access to generative AI tools, produced entirely from a mobile device, at near-zero cost. Where a formal survey or certified appraisal is unavailable or unaffordable, a body of C2PA-signed media combined with stamped email records provides a credible substitute.

**Professional credentials and work history.** A freelancer or contractor who receives project confirmations, payment records, and client references by email can build a stamped portfolio of work history — verifiable without relying on a centralised platform or a reference that might become unavailable.

**The broader principle.** The infrastructure of trust that wealthy societies take for granted — functioning courts, reliable registries, affordable legal representation — can be partially approximated with tamper-proof records, cryptographic timestamps, and independently verifiable evidence. Combined with C2PA-authenticated media, mobile-native financial instruments, and decentralised identity systems, Leima is one component of a larger toolkit for participation in global economic life without access to the institutions that currently gatekeep it.

---

## Research and prior art

**Timestamping findings.** A researcher who makes a discovery or develops a methodology can stamp a description of it before publication — creating a dated record that establishes priority independent of the journal review timeline.

**Source verification.** When a paper or report makes a claim about what a source says, stamping a verdict against that source at the time of writing creates a permanent, independently verifiable record. Future readers can confirm that the source said what the authors claimed it said, on the date the paper was written.

**AI research agents.** Automated pipelines that retrieve and analyse sources to support a claim can produce stamped records of each source check — a citable, tamper-proof audit trail for the research process itself.

---

## Legal and contractual

**Fixing the terms of an agreement.** A contract, offer letter, or invoice can be stamped before it is acted upon — creating a record of what the document said at the moment both parties relied on it. If the document is later disputed or altered, the stamp provides the reference point.

**Employment disputes.** Stamping offer letters, salary confirmations, policy documents, and HR communications at the time of receipt creates a contemporaneous record that is independent of either party's later recollection.

**Preserving pre-dispute state.** Before a relationship deteriorates, stamping the relevant documents — leases, service agreements, invoices, correspondence — establishes what was agreed before either side had an incentive to reinterpret it.
