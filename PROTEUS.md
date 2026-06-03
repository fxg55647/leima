Proteus is a planned privacy architecture for LLM API usage. The core idea: for every real document, the system generates a set of plausible but fabricated variants and sends them as separate API calls. An outside observer — including the provider — can never be certain which document is genuine, or whether any of them are.

---

# Proteus: Epistemic Privacy for LLM APIs

*Planned feature — June 2026*

> **Note:** This is a concept, not a specification. The core idea is technically grounded, but the right implementation form is an open question — proxy, agent, library, or API wrapper. The architecture below illustrates one plausible form, not a committed design.

---

## The problem with sending documents to AI

Every time you send a sensitive document to an LLM API, you face an uncomfortable truth: someone else sees it. Your legal contracts, patient records, financial data — they all pass through infrastructure you don't control. Encryption protects data in transit. But the moment the model processes your document, it is readable. The provider sees it. Their logs may keep it. Regulatory subpoenas can reach it.

The standard responses — on-premises models, redaction, synthetic data — each carry heavy tradeoffs: cost, capability loss, or incomplete protection. There has been no lightweight middle path.

Proteus is that middle path.

---

## The idea: make the truth indistinguishable

Named after the Greek sea-god who evades capture by constantly changing form, Proteus works on a simple principle: **if an adversary cannot tell which document is real, the information they intercept has no value**.

Rather than preventing access to your document, Proteus makes access useless. For every genuine API call, the system generates *n* plausible but entirely fabricated decoys and sends each as a separate, indistinguishable API request. An outside observer — including the API provider — sees a stream of requests and cannot determine which, if any, contains real data.

This is a shift from technical defense to **epistemic defense**. The adversary does not hit a wall. They hit uncertainty they cannot resolve.

---

## Why this is different

| Method | Mechanism | Failure mode |
|---|---|---|
| Encryption | Blocks access | Binary — once broken, fully broken |
| Redaction | Removes sensitive fields | Data is lost entirely |
| On-premises LLM | No external calls | Cost, limited capability |
| Proteus | Makes intercepted data worthless | Degrades gracefully, never fully collapses |

Encryption fails catastrophically — when it breaks, it breaks completely. Proteus degrades gracefully. Even if an adversary improves their ability to identify real documents, they improve incrementally, not catastrophically.

---

## The mathematics

Let:
- `V` = document value to an adversary
- `n` = number of decoys
- `q` = probability that none of the documents sent are genuine (0–1)
- `a` = adversary's analytical ability to identify the real document (0 = random guess, 1 = always correct)
- `C` = adversary's cost per analysis

**Effective identification probability:**

```
p(a, n, q) = (1−q) × [a + (1−a) × 1/(n+1)]
```

**Damage to adversary (%):**

```
D% = 1 − (1−q) × [a + (1−a) × 1/(n+1)]
```

Sample values:

| Decoys (n) | Null prob. (q) | Adversary ability (a) | Damage to adversary |
|---|---|---|---|
| 3 | 0.0 | 0.0 | 75% |
| 7 | 0.2 | 0.3 | 84% |
| 9 | 0.3 | 0.3 | 87% |
| 15 | 0.3 | 0.2 | 92% |

**Attack becomes unprofitable when:** `n > V/C − 1`

The asymmetry is the strategic point: the defender's cost scales **linearly** (local model inference plus a few extra API calls), while the adversary's burden grows **superlinearly**. This is an unusual security property — the defender is in the stronger economic position.

---

## Red team analysis

The mathematical model is strong, but a real-world adversary has access to indirect signals. Three attack vectors and their mitigations:

### 1. Stylometric fingerprinting

If the real document is human-written and a local model generates decoys, the original stands out. LLMs produce text with characteristic entropy and word selection patterns — a discriminator model can identify the human-written document with near-certainty.

**Mitigation:** The proxy must also rewrite the real document through the local model (preserving all facts). All outbound calls then share the same stylometric "LLM accent."

### 2. Semantic centroid attack

If decoys cluster around the same topic as the real document, an adversary observing multiple calls from the same IP can compute a semantic centroid and recover the essential fact without identifying any single document.

**Mitigation:** Decoys must be **semantically orthogonal** to the original — not just plausible variants of it, but genuinely unrelated content.

### 3. Timing and burst analysis

Dispatching the real document and all decoys simultaneously reveals the group by traffic pattern alone.

**Mitigation:** The proxy maintains a steady stream of synthetic dummy calls at all times. Real documents are absorbed into this continuous stream without creating detectable spikes.

---

## Active defense: poisoned decoys

Some decoys can carry embedded **prompt injection traps** — subtle instructions that activate if the content is fed into another model. If a provider uses data without authorization, or if an adversary runs the intercepted batch through their own pipeline, the poisoned decoys interfere — corrupting outputs or producing detectable artifacts.

Proteus would not merely hide a needle in a haystack. It would make some of the hay actively hostile to anyone searching through it.

---

## Relationship to Leima

Leima and Proteus are mirror images of each other:

- **Leima** answers: *how do you prove a document is genuine and was analyzed at a specific moment?*
- **Proteus** answers: *how do you prevent anyone from knowing which document is genuine?*

Same epistemic problem. Opposite directions. Combined, they form a complete architecture:

| Component | Role |
|---|---|
| **Proteus** | Generates entropy and uncertainty in the open network |
| **Arweave** | Immutable, decentralized storage (permanence) |
| **Leima** | Neutral witness — anchors the real document's hash, proving which of the *n*+1 was genuine |

The owner holds mathematical proof of the authentic document. The outside world sees only noise.

---

## Philosophical foundation

Proteus is **compatible with chaos** — not despite uncertainty but because uncertainty is real. The system does not attempt to close the problem. It restructures the adversary's incentives so that attack becomes economically irrational.


---

## Prior art and publication

This concept was developed and documented on 3 June 2026. A short technical paper (4–6 pages) is planned for arXiv or SSRN.

Suggested title: *"Epistemic Obfuscation via Probabilistic Document Decoys in LLM API Pipelines"*


