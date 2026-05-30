# Continuous Physical Attestation — The Inspector Protocol

Physical due diligence has traditionally meant sending someone to look at something. The result is a point-in-time snapshot: one person's account of what they saw, on one day, recorded in a report that is easy to dispute and impossible to verify independently. The Inspector Protocol is a different approach: a standardised observation process that produces a continuous, cryptographically anchored record of what was seen, when, and under what conditions.

The protocol does not claim to prove perfect truth. It claims something more modest and more useful: here is a documented observation chain, here is an AI analysis of what it shows, and here is a permanent record that neither party can alter retroactively.

---

## The core principle

The Inspector Protocol is not drone-specific. A drone, a person walking with a camera, a smartphone mounted on a vehicle, or a fixed camera on a building all implement the same protocol. The observer is irrelevant to the trust model. What matters is the observation process:

- Observations are made according to a standardised protocol, not at the observer's discretion
- The system directs what to capture and when — not the person submitting the evidence
- The captured data includes not just images but telemetry, timestamps, and GPS
- An independent AI analyses the observations and characterises what they show
- The full record — raw data, AI analysis, and chain of evidence — is cryptographically stamped and permanently stored

Because the system controls when and what is captured, a party wishing to present favourable evidence cannot simply choose the best angle or the best moment. The observation is directed; the evidence is what the protocol collected, not what the submitter selected.

---

## Challenge-response verification

The strongest anti-spoofing mechanism in the protocol is the challenge-response layer. At random intervals during an observation session, the system issues instructions that could not have been anticipated in advance:

> *"Move to the northwest corner and tilt the camera down."*
> *"Return to the entrance and pan left."*
> *"Show the underside of the roof at the far end."*

An observer presenting pre-recorded footage cannot respond to these challenges in real time. An observer physically present must comply. The challenge-response record — the instruction, the timestamp, and the footage captured in response — becomes part of the stamped evidence.

This does not make fabrication impossible. It makes it dramatically more expensive: an adversary must fabricate not just a static scene but a dynamic, responsive environment that answers unpredictable instructions in real time. For most practical threat models, this cost is prohibitive.

---

## What is captured

A single observation session produces:

- **Image and video frames** — taken at intervals specified by the protocol, plus in response to challenges
- **GPS coordinates** — tied to each frame, establishing location independently of the observer's account
- **Telemetry** — altitude, orientation, movement, and timing data where available
- **HTTP metadata** — if the device streams through a network connection, request headers and timestamps provide additional anchoring
- **DOM or sensor snapshots** — the raw data as it arrived at the capture device, before any processing

All of this is hashed and sent to Leima before the session ends. The AI analyses the full record and produces a characterisation of what the observation shows: what is present, what has changed since the last inspection, what appears consistent or inconsistent with prior records.

---

## Why this is stronger than a single video

A conventional video or photograph:

- Can be taken at any time the submitter chooses
- Can be edited before submission
- Provides no independent verification of location or timing
- Cannot be challenged or interrogated after the fact

An Inspector Protocol session:

- Is directed by the system, not the submitter
- Includes GPS, telemetry, and timestamps bound to the raw data
- Includes challenge-response interactions that require real-time compliance
- Produces a continuous observation chain, not a selected moment
- Compares automatically to prior sessions, making inconsistencies visible

To fabricate a convincing Inspector Protocol record, an adversary must simultaneously fake the physical environment, the GPS data, the telemetry, the response to unpredictable challenges, and the consistency with prior observation history. Each layer raises the cost of deception independently.

---

## AI's role

The AI in this protocol is not a judge. It is a sensor, an analyst, and a comparator.

On each session, the AI:

- Characterises what the observation shows in plain language
- Compares the current session to prior sessions and identifies changes
- Flags inconsistencies — between stated claims and what is visible, or between the current record and previous ones
- Produces a preliminary assessment, not a final verdict

Examples of what the AI might report:

> *"Roof condition consistent with prior inspection. No new damage visible."*
> *"Approximately 20 solar panels visible, up from 12 in the previous session."*
> *"Construction appears to have reached framing stage. Foundation visible in prior session is now enclosed."*
> *"Significant tree clearance observed on the eastern boundary since last month."*
> *"Possible water pooling visible near the northwest corner. Not present in prior record."*

The value of the AI is not that it is always right. It is that it applies consistent criteria across sessions, has no stake in the outcome, and cannot be socially pressured. Its analysis is sealed at the moment it is produced and cannot be revised after the fact.

The underlying observation process would be useful even without AI analysis. The AI scales it: what would otherwise require a human expert to review hours of footage is reduced to a structured summary that a counterparty, lender, or regulator can read in seconds.

---

## Connection to Leima

The Inspector Protocol is implemented as a Leima integration. The observation device — a drone controller app, a mobile camera application, or any device running the Inspector client — connects to Leima's API. The captured data is submitted as a session bundle; Leima analyses it and returns a stamped verdict and manifest.

The stamped record includes the full chain: the raw observation data, the AI analysis, the GPS and telemetry, and a permanent Arweave transaction ID. The manifest links back to any prior sessions, building a verifiable history that can be independently audited.

For devices running the Inspector client on Android, the session bundle is signed with a key stored in the Android hardware keystore before submission. Android's Key Attestation mechanism allows Leima to verify that the signing key was generated in hardware and has not been exported — providing a chain of custody from the physical device to the Arweave record.

---

## Use cases

### Construction and real estate

A drone or site operative with a camera follows the inspection protocol on a regular schedule — weekly or monthly. The AI tracks construction progress against prior sessions: new structures, completed sections, material changes, and anomalies.

**For lenders.** A construction loan can be tied to verified progress milestones rather than self-reported updates. The lender receives a stamped inspection record at each disbursement stage; the borrower cannot claim progress that is not visible in the protocol record.

**For buyers.** A property listed for sale can include a stamped inspection record — *Roof Proof* — covering the condition of the roof, the exterior, and any documented defects. The buyer receives an independently verifiable assessment that predates the negotiation, not a report commissioned by the seller.

**For insurers.** The pre-loss condition of a property is documented in an inspection history that predates any claim. A dispute about whether damage existed before a policy was taken out becomes a question of what the protocol record shows, not a credibility contest between the claimant and the adjuster.

---

### Housing associations and property management

A regular inspection schedule — monthly or quarterly — produces a continuous record of roof condition, facade deterioration, drainage problems, and accumulated snow loads. Changes that develop slowly over years, and that residents may not notice until they become serious, are visible in the inspection history as early anomalies.

---

### Forestry and environment

A monthly flight or ground survey over a defined area produces a change record: hectares cleared, new growth, storm damage, water levels. The record is independently verifiable and cannot be retroactively altered to conceal logging, flooding, or other changes.

For carbon credit verification, conservation agreements, or environmental compliance, the inspection history provides a continuous evidentiary record rather than periodic self-reported data.

---

### Agriculture

Seasonal inspection records document crop coverage, irrigation, soil condition, and harvest progress. A microfinance institution seeking to verify that a loan was used for its stated purpose — planting a specific crop on a specific plot — can request an inspection record rather than conducting a physical visit.

Combined with Leima's document stamping for purchase receipts, delivery records, and buyer confirmations, the inspection record becomes part of a longitudinal evidence portfolio that accumulates credibility over time.

---

### Development finance and microloans

**The incremental trust model.** A borrower who cannot provide a credit history or collateral can build a verified track record through a series of small, documented transactions:

1. A first loan finances a single piece of equipment or a small installation
2. An Inspector Protocol session verifies that the asset exists and is operational
3. A subsequent session verifies it is still present and in use
4. A second loan, larger, is extended based on the verified record
5. The pattern repeats

Trust is built through the history of the inspection chain, not through a single document or a prior relationship. The lender does not need to send someone to verify each stage; the protocol record is the verification.

---

### Fisheries and maritime monitoring

A vessel operator can submit a session record documenting departure location, route, catch handling, and port arrival. The challenge-response mechanism makes it difficult to present a record fabricated from prior footage. Combined with AIS transponder data and port authority communications stamped through Leima, the session record contributes to a verifiable activity log.

For sustainability certification, access to premium markets, or compliance with catch quotas, the inspection record provides documentation that does not depend on the operator's self-reporting alone.

---

## What this does not prove

The Inspector Protocol documents what was observed under a standardised process. It does not:

- Prove that the observer's device was not compromised before the session
- Prove that the physical environment shown is the environment claimed (the AI can compare to prior sessions and flag inconsistencies, but a sufficiently elaborate physical fabrication is not ruled out)
- Replace a professional surveyor's report for legal or regulatory purposes where such a report is required

These are real limitations. They are worth stating directly rather than obscuring. The protocol raises the cost of deception significantly. It does not make deception impossible. For most practical purposes — lender verification, insurance documentation, progress monitoring, microfinance — the bar it sets is sufficient.

---

## The broader principle

The Inspector Protocol is one instance of a general pattern: any continuous observation process, conducted under a standardised protocol, with the system directing what is observed, can produce a cryptographically anchored record that is significantly harder to fabricate than self-reported evidence.

The observer is interchangeable — drone, person, vehicle, fixed camera. The protocol is what matters. The value is not in any single observation but in the accumulating history: the longer and more consistent the record, the harder it becomes to introduce a fabrication without creating a visible discontinuity.

A single stamped observation says: *this is what was seen, at this time, under these conditions.* A series of stamped observations says: *this is what has been consistently visible, across these sessions, over this period.* The second claim is substantially stronger — and it is produced automatically, as a byproduct of following the protocol, at near-zero marginal cost per session.
