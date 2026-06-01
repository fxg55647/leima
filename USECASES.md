# Leima — Use Cases

---

## Due diligence

Due diligence involves one party evaluating another's claims before committing to a transaction. The fundamental problem is that the party being evaluated has an incentive to present their situation favourably, while the evaluating party needs enough information to make a judgment without necessarily receiving everything. Leima addresses both sides of this problem.

**Immediate cryptographic verification.** Due diligence has traditionally meant collecting documents and verifying their authenticity weeks or months later — a manual process with significant lag. Leima compresses this into seconds.

For documents that carry cryptographic provenance, verification happens at submission: a PDF with a digital signature is checked against its RFC 3161 trusted timestamp, the signer's certificate is extracted, and any post-signing modification is detected immediately. The verdict states whether the document is intact or tampered — a hard cryptographic finding, not an AI opinion. For documents without signatures, the Arweave hash commitment means there is no dispute later about what was submitted: the exact content is sealed at the moment of analysis. Both paths eliminate the gap between "documents received" and "documents verified."

**Partial disclosure with hash commitment.** Any material — a contract, a financial statement, a codebase, a patent application — can be partially disclosed. The submitting party shows the evaluating party a redacted or summarised version, and Leima stamps an AI verdict characterising what the document contains: its nature, scope, and the specific claim being evaluated. The cryptographic hash of the full, unredacted document is recorded in the stamp.

If the submitting party later claims they provided different information, or if it emerges that the disclosed version misrepresented the full document, the hash exposes the fraud: the stamp establishes a tamper-evident record of exactly what was shown, when, and what the AI concluded from it. The evaluator cannot later claim they were not informed; the submitter cannot later claim they showed something different.

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

## Legal and regulatory compliance

A common problem in business and science is establishing whether a specific situation is consistent with a stated rule — a law, a regulation, a contract clause, or an internal policy. Traditionally this requires a lawyer, which is expensive and slow. For many routine questions, the actual analytical task is straightforward: does the described situation match or conflict with what the document says?

**How it works.** The user combines two things in a single document: the relevant law or contract text, and a description of the situation being evaluated. The claim is then stated plainly — for example, *"the situation described in this document is consistent with the stated regulation"* — and Leima analyses it. The AI identifies which provisions are relevant, what the document says about them, and whether the described situation satisfies or violates those provisions. The verdict is stamped and permanently recorded.

This is not legal advice. Leima assesses what the document states and whether the described situation matches it. It does not advise on legal strategy, predict court outcomes, or represent either party. The value is a dated, tamper-proof record of what a neutral analytical reading of the document concluded — before any dispute arose.

**Business compliance.** A company can submit a contract clause alongside a description of their current practice and ask whether the practice is within the agreed terms. An employer can submit a collective agreement and a proposed staffing decision and ask whether the decision is consistent with the agreement. A procurement officer can submit a tender specification and a supplier's response and ask whether the response meets the stated requirements.

**Regulatory filing.** A company preparing a regulatory submission can stamp an analysis of their documentation against the relevant requirements before filing. This creates a record of what was checked, when, and what conclusion was reached — independent of the regulator's own assessment. If the filing is later challenged, the stamp shows that compliance was assessed at the time of submission, not constructed retroactively.

**Scientific and research contexts.** Researchers can evaluate whether a proposed study design is consistent with an ethics guideline, whether a published claim is supported by the cited regulation, or whether a data handling practice falls within a stated data protection framework. The result is a verifiable, timestamped analysis rather than an informal opinion.

---

## Consumer documentation

**Service records and receipts.** When a service provider sends a receipt by email — a car service, a repair, an appliance installation — the owner can stamp that email in Leima. The DKIM signature confirms the message came from the service provider's domain. The stamp creates a permanent, tamper-proof record: this work was done, on this date, confirmed by this provider. Useful for warranty claims, insurance disputes, and resale documentation where a buyer wants to verify the service history.

**High-value vehicle and equipment maintenance.** A Ferrari engine overhaul can cost €100,000. At that level, both parties have a strong interest in a tamper-proof record: the owner needs to prove what was done and when, the workshop needs to prove it delivered what it invoiced, and any future buyer will pay a significant premium for a service history they can actually verify. A stamped email from the workshop — DKIM-confirmed from their domain, with the work order attached — creates a record that cannot be silently altered. If a dispute arises about what was or was not done, the hash settles it. The same applies to any high-value asset with meaningful maintenance history: classic cars, race vehicles, aircraft, marine engines, specialist industrial equipment.

**Insurance evidence.** Purchases and valuations sent by email — a jeweller's appraisal, a specialist's estimate, a purchase confirmation — can be stamped at the time of receipt. If the item is later lost, stolen, or damaged, the stamp provides strong evidence that the item existed and was valued at a specific amount on a specific date, before the claim arose. The record cannot be backdated.

**Subscription and terms changes.** When a service changes its terms of service or pricing and notifies users by email, stamping that notification creates a dated record of what was agreed or communicated at that time — useful in disputes about what was promised before a change.

---

## Email notary

The AI verdict flow requires a deliberate action: a user uploads a document, poses a claim, and receives a stamped result. The email notary works differently — it operates automatically, as a side effect of ordinary email communication, with no change in behaviour required from either party.

**How it works.** A sender adds `BCC: stamp@leima.fi` to any email. Leima receives the message, verifies the DKIM signature (confirming that the message genuinely originated from the sender's domain and was not altered in transit), hashes the full email including any attachments, stamps the hash on Arweave, and forwards a notarized copy to the real recipient — the address in the `To:` field. The recipient receives the original message plus a certificate containing the hash, the DKIM result, a permanent Arweave link, and a one-click verification URL.

The sender's domain is the trust anchor. DKIM is not a claim the sender makes about themselves — it is a cryptographic assertion made by their mail server, verifiable against their published DNS records. A notarized email from `huolto@ferrarikeskus.fi` carries the same institutional weight as a letter on headed paper, but with a tamper-proof timestamp and an immutable record that cannot be lost, backdated, or silently altered.

**Receipt and service documentation.** A car workshop, appliance repair company, or specialist service provider adds one BCC address to their outgoing email template. Every customer automatically receives a notarized copy of their receipt, work order, or service confirmation — without the customer needing to do anything. When the car is sold, the buyer can verify the service history by uploading the `.eml` file and checking the Arweave record. The record exists independently of the workshop, the email provider, or the customer's inbox.

**Dispute prevention.** The notarization is symmetric: it records what was said, not who was right. A message from a landlord stating that a repair was completed, or from a contractor confirming the scope of work, becomes a reference point that neither party can later reinterpret. This is most valuable before a relationship deteriorates — the record captures the agreed state before either side had an incentive to revise it.

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

---

## Service entry and exit

Stamping should become standard practice at two moments in any significant service relationship: when you commit to it, and when you leave it.

**At the start.** When signing up for a service, stamp the terms of service, the pricing page, and any promotional offer that influenced the decision. These are the promises made before the relationship began. If the service later changes its terms, raises its prices, or removes a feature it advertised, the entry stamp establishes what was agreed at the outset — before either party had any incentive to misrepresent it.

**At the end.** When cancelling or leaving a service, stamp the confirmation: the cancellation email, any data deletion notice, the final invoice, the stated reason for termination. If a billing dispute arises after cancellation, or if the provider later claims the account was never properly closed, the exit stamp provides a dated record of the state at the moment of departure.

The combination creates a verifiable bracket around the entire service relationship. Neither the provider nor the user can later rewrite what was agreed at the beginning or what happened at the end. For any service that handles money, personal data, or contractual commitments, this should be as routine as keeping a copy of the contract.

---

## Planned features

*The following use cases describe capabilities under development. They are listed here to illustrate the direction of the platform and to invite early feedback from potential users.*

---

### Continuous corporate due diligence

A company publishes a continuously updated evidence package — bank balances, cash flows, accounting exports, invoicing data, contract lists — with each source hashed at the moment of retrieval, analysed by AI, and stamped permanently. The source list is explicit: which accounting system, which bank accounts, which payment processors. An auditor can confirm coverage — that the listed sources constitute the company's material financial records — without conducting a full-scope audit. The AI runs continuously, flagging inconsistencies across sources and deviations from prior periods. Trust accumulates through the history: a company with two years of consistent, uncontradicted evidence packages has demonstrated something no single point-in-time audit can establish. For small companies that cannot afford institutional verification, this is a lightweight trust infrastructure that is meaningfully stronger than self-reported figures. See [CONTINUOUS_DD.md](CONTINUOUS_DD.md) for a full description.

---

### Continuous physical inspection

A standardised observation protocol — conducted by drone, by a person carrying a camera, or by any capture device — produces a continuous, cryptographically anchored record of a physical location or asset over time. The system directs what to capture and when; the observer follows instructions. A challenge-response layer requires real-time compliance with unpredictable commands, making pre-recorded or fabricated footage significantly harder to present convincingly. The AI analyses each session, compares it to prior sessions, and flags changes and inconsistencies.

Applications include construction progress monitoring for lenders, pre-sale property condition records, forestry and environmental change detection, agricultural verification for microfinance, and incremental trust-building for borrowers without credit history. See [INSPECTION.md](INSPECTION.md) for a full description of the protocol, the trust model, and the range of use cases.

---

### Evidence bundles

A single stamp covering multiple documents of different types — PDFs, emails, photographs, contracts — submitted together as a coherent body of evidence. The AI evaluates the bundle as a whole, assessing internal consistency and the combined support for a claim rather than treating each document in isolation.

**Property condition.** A landlord or insurer documenting the state of a property can submit photographs from multiple angles, a written inventory, and a signed inspection report in a single bundle. The AI assesses whether the photographs are internally consistent — whether the condition shown in the exterior shots is consistent with the interior photographs, whether the stated condition matches what is visible — and stamps a verdict covering the full set. If a dispute later arises about the property's condition at move-in or move-out, the bundle provides a coherent, independently verifiable record that is harder to dispute than any single document.

**Damage assessment.** An insurance claimant submitting evidence of damage — photographs of a vehicle, a repair estimate, a police report — can bundle all materials into a single stamped record. The AI evaluates consistency across the documents: whether the described damage matches the photographic evidence, whether the estimate is plausible given what is shown. A verdict that covers the full bundle is more useful to an adjuster than individual stamps on each piece of evidence.

**Transaction with supporting evidence.** A sale or purchase involving multiple documents — a purchase agreement, proof of funds, identity confirmation, and photographs of the item — can be stamped as a single bundle, creating a coherent record of the complete transaction rather than a collection of separately-stamped pieces.

---

### API response stamping

A user provides an API endpoint, authentication credentials, and any required parameters. Leima calls the API directly and stamps the response — acting as an independent third party that attests to what the API returned at a specific moment. The user cannot have manipulated the response in transit, because Leima is the one making the call. TREAD deployment monitoring ensures that Leima's own code has not been altered, completing the trust chain.

**Financial and market data.** A contract whose terms reference a specific exchange rate, commodity price, or index value at a specific date can be anchored to an independently stamped API call. If a dispute arises about what the rate actually was, the stamp provides a reference point that neither party controls.

**Prediction markets and information credentialing.** Before a contested outcome resolves, an API call to an authoritative data source — a sports result, an election outcome, a scientific measurement — can be stamped independently. The stamp records what the source reported, at the moment it reported it, without requiring either party to have preserved a screenshot that the other could dispute.

**AI model output.** An API call to a language model can be stamped at the moment of execution: this prompt, this model, this response, this date. If a model is later updated or its behaviour changes, the stamp provides a verifiable record of what it said before the change. Useful for auditing AI-assisted decisions in regulated contexts, or for establishing what a model's output was at a specific point in a workflow.

**Regulatory and official data.** A government or regulatory API response — a public record, a compliance status, an official statistic — can be stamped at the moment of retrieval. If the underlying data is later revised, the stamp establishes what the official source reported at the time a decision was made.

---

### Satellite imagery analysis

Leima retrieves satellite imagery for a specified location and date range from a third-party imagery provider and stamps an AI analysis of the images. The retrieval is performed by Leima directly, establishing an independent record of what the imagery showed at a given time.

**Land use and boundary disputes.** In jurisdictions without reliable land registries, a stamped analysis of satellite imagery showing the boundaries, use, and condition of a plot of land on a specific date provides evidence that is difficult to fabricate and independent of either party's claims. Changes in land use — cultivation, construction, clearance — can be documented over time, building a verifiable record that strengthens or undermines competing claims.

**Agricultural evidence for microfinance.** A smallholder seeking credit can submit a claim that a specific plot is under active cultivation. A stamped satellite analysis showing crops on a specific date — corroborating email records and C2PA-signed ground-level photographs — builds a body of evidence that a microfinance institution can assess without conducting a physical inspection.

**Environmental monitoring.** Deforestation, flooding, construction, and other land changes can be documented over time with stamped imagery. For environmental disputes, carbon credit verification, or regulatory compliance, a series of independently stamped satellite analyses provides a timeline that is harder to dispute than self-reported data.

---

### Video

Support for video submissions — uploaded directly or provided by URL — with AI analysis of the content and a cryptographic stamp covering both the video file and the verdict.

**Security and incident footage.** A property owner or business can stamp security camera footage of an incident at the time it is captured, before any dispute arises about whether it has been edited. The hash commits to the exact content of the file; the AI characterises what the footage shows.

**C2PA-signed video.** An increasing number of cameras — including smartphones from major manufacturers — produce video with embedded C2PA signatures binding each frame to the device identity, GPS coordinates, and capture timestamp. Leima can verify the C2PA signature at submission and incorporate the cryptographic provenance into the stamp, producing a record that establishes not just that a video was stamped at a particular moment but that it was captured by a specific device at a specific location.

**Process and progress documentation.** A contractor or service provider can document the progress of a project — construction, renovation, installation — with a series of stamped video records. Each stamp establishes the state of the work at that date, creating a timeline that can be referenced in payment disputes or defect claims.

**Expert testimony and assessments.** A specialist recording a verbal assessment — an appraiser, a surveyor, a medical professional — can produce a stamped video record of their findings. The stamp captures the assessment at the moment it was made, before any dispute arose, and establishes that the recording has not been edited since.

---

### Service availability and latency monitoring

Leima periodically fetches a specified URL or API endpoint and stamps the response — recording the HTTP status, response time, and content hash at each check. The stamps build an independently verifiable timeline of a service's availability and behaviour that neither the service operator nor the monitoring party can retroactively alter.

**Downtime documentation.** If a service is down at the moment Leima checks it, the stamp records the failure: this endpoint returned this error at this time. If a dispute later arises about whether an outage occurred — an SLA claim, a refund request, a contractual penalty — the stamped record provides a reference point that does not depend on either party's self-reported logs.

**Latency and degradation.** Response times are recorded at each check. A pattern of slow responses or intermittent failures — difficult to prove after the fact from a user's own observations — is documented in a permanent, tamper-proof timeline. Useful for SLA enforcement, supplier negotiations, or demonstrating to a regulator that a service repeatedly failed to meet stated performance commitments.

**Content changes.** Because each stamp includes a hash of the response body, changes in the content of a page or API response are detectable over time. If a service quietly alters its terms, prices, or functionality between formal updates, the stamp history shows exactly when the change occurred.

---

### Bring-your-own-AI stamping

A user provides their own API credentials for any AI service — OpenAI, Anthropic, Gemini, Mistral, or any other — along with a prompt. Leima sends the request using those credentials, receives the response, and stamps both: this prompt, this model, this version, this response, at this time. The user controls the credentials and the prompt; Leima's role is to act as an independent witness to what was sent and what came back.

**Documenting harmful or surprising outputs.** If a model produces something harmful, biased, factually wrong, or otherwise notable, the stamp creates a permanent, verifiable record that cannot be dismissed as a screenshot. The record establishes that this specific model, at this specific version, produced this specific output — before the provider had any opportunity to patch or deny it. A screenshot can be fabricated; a stamped API call cannot.

**Tracking model behaviour over time.** Models are silently updated. A response that a model gave six months ago may no longer be reproducible with the same prompt and model name — the underlying weights may have changed without any public announcement. Stamping outputs at the time they are generated creates a historical record of what a model actually said, independent of what it says now.

**Regulatory and compliance evidence.** In regulated contexts — healthcare, finance, legal — automated AI-assisted decisions may be subject to audit. A stamped record of the exact prompt and response, tied to a specific model version, provides a basis for explaining and defending the decision. If a regulator later questions what the system produced, the stamp is the answer.

**Research and journalism.** A researcher or journalist documenting AI behaviour — testing for bias, probing for policy violations, comparing models — can produce a body of stamped evidence that is independently verifiable. The record shows not just what was claimed about the model's output, but what the model actually returned, at a specific moment, under specific conditions.

---

### Multi-model consensus

For high-stakes verdicts, Leima runs the same document and claim through multiple independent AI models simultaneously and requires agreement across all of them before issuing a stamp. A successful prompt injection or model manipulation would need to fool every architecture at once — a significantly harder task than targeting a single model.

**Fraud-resistant verification.** In contexts where the stakes are high enough that an adversary might attempt to manipulate the AI verdict — large financial transactions, contested legal claims, high-value asset appraisals — requiring consensus across independent models raises the bar for a successful attack. Each model has a different training distribution, different blind spots, and different susceptibility to adversarial inputs.

**Regulatory contexts.** A verdict that three independent AI systems agree on carries more evidentiary weight than a single-model output, particularly in regulated industries where the methodology of an automated decision may be subject to scrutiny. Multi-model consensus provides a basis for explaining that the verdict was not the product of a single opaque system.
