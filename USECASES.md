# Leima — Use Cases

---

## Consumer documentation

**Service records and receipts.** When a service provider sends a receipt by email — a car service, a repair, an appliance installation — the owner can stamp that email in Leima. The DKIM signature confirms the message came from the service provider's domain. The stamp creates a permanent, tamper-proof record: this work was done, on this date, confirmed by this provider. Useful for warranty claims, insurance disputes, and resale documentation where a buyer wants to verify the service history.

**Insurance evidence.** Purchases and valuations sent by email — a jeweller's appraisal, a specialist's estimate, a purchase confirmation — can be stamped at the time of receipt. If the item is later lost, stolen, or damaged, the stamp proves the item existed and was valued at a specific amount on a specific date, before the claim arose. The record cannot be backdated.

**Subscription and terms changes.** When a service changes its terms of service or pricing and notifies users by email, stamping that notification creates a dated record of what was agreed or communicated at that time — useful in disputes about what was promised before a change.

---

## Art, craft, and collectibles

**Proof of creation.** An artist can establish provenance by emailing documentation of a new work — photographs, sketches, process notes — to themselves or to a trusted party, and stamping that email. The DKIM signature confirms the date and sender. This creates a verifiable record that a specific person created a specific work on or before a specific date: harder to forge than a signature on a canvas, and timestamped independently of the artist's own claim.

**First-owner transfer.** When a work changes hands for the first time, the artist can email the buyer directly with a description of the piece, any provenance documentation, and a statement of transfer. Stamping that email creates a permanent record of the first transfer — linking the artist's identity (via DKIM domain) to the buyer, the work, and the date. Subsequent owners can verify the chain.

**Creation process as evidence.** A series of photographs documenting the creation of a work — from blank canvas to finished piece — provides strong evidence of authorship. When taken with a **C2PA-enabled camera** (already available from manufacturers including Leica, Sony, and Nikon), each photograph carries a cryptographic signature from the camera itself, binding the image to the device, the GPS location, and the timestamp at the moment of capture. Leima can stamp a claim against this series: the combination of C2PA-signed images and a Leima verdict creates a provenance record that is difficult to fabricate even with access to AI image generation tools.

**Restoration and conservation.** A restorer can document the condition of a work before and after treatment by emailing a report with photographs to the owner or a registry. Stamping that email creates a dated, independently verifiable record of the work's state — relevant for insurance, for establishing the scope of the restoration, and for future buyers who want to understand the work's history.

**Collectibles and physical objects.** The same approach applies to any object with a verifiable identity: vintage instruments, watches, wine, historical artefacts. A specialist's email assessment, stamped at the time of receipt, becomes part of the object's verifiable history. Combined with a serial number or unique identifier, multiple stamped records over time build a chain of custody.

---

## Economic inclusion and access to markets

In many parts of the world, the barrier to economic participation is not capability or effort — it is the inability to prove what you own, what you have done, or what agreements you have made. Banks require collateral that cannot be documented. Buyers require certificates that cost more than the transaction is worth. Leima does not solve these problems entirely, but it lowers the cost of producing credible evidence to near zero.

**Small-scale agriculture.** A farmer who sells produce to a local market or cooperative typically receives payment confirmations, input purchase receipts, and delivery records by email or SMS. Stamping these creates a longitudinal record of economic activity: this farm produced and sold this volume, on these dates, to these buyers. Presented to a microfinance institution or an international buyer conducting due diligence, a body of stamped records can substitute for formal financial statements that the farmer has no means to produce.

**Fishing and maritime activity.** A fishing cooperative can stamp catch records, port authority communications, and buyer confirmations. Combined with GPS track data (where available), this creates an auditable activity record that can support applications for sustainability certification, access to premium markets, or credit.

**Land and property.** In jurisdictions without reliable land registries, proving ownership of a piece of land depends on a chain of documents — purchase agreements, witness statements, tax records — that are often paper-based, incomplete, or disputed. Stamping whatever documentation exists, at the time it is received, builds an incrementally stronger record. It does not replace a functioning registry, but it makes the available evidence harder to deny.

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
