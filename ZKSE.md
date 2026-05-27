# Zero-Knowledge Semantic Evaluation

*A note on Leima's relationship to zero-knowledge systems and why this approach may have been underexplored.*

---

## Is SAIA a zero-knowledge system?

Perhaps partially.

Formal zero-knowledge proof systems require three properties: *completeness* (if a statement is true, an honest verifier will be convinced), *soundness* (if a statement is false, a dishonest prover cannot convince the verifier), and *zero-knowledge* (the verifier learns nothing beyond the truth of the statement). The mathematical guarantee rests on all three.

SAIA satisfies the zero-knowledge property in a specific, limited sense: the evaluator has zero knowledge of the author's identity, organisational context, or any background information not explicitly submitted as part of the evaluation. The code is assessed in isolation against a fixed, public policy — not against reputation, prior behaviour, or commercial context. In this respect the evaluation is blind.

It does not satisfy soundness in the cryptographic sense. An LLM can be manipulated through adversarial inputs, and its output is probabilistic, not mathematically constrained. The term *zero-knowledge semantic evaluation* (ZKSE) captures this honestly: *semantic* signals that the evaluation operates on meaning and intent rather than formal arithmetic, and *zero-knowledge* refers specifically to the evaluator's contextual blindness — not to a proof system with soundness guarantees.

Whether systems like this deserve a formal category — Zero-Knowledge Semantic Evaluation — is best left for the broader research community to decide. The claim here is narrower: the concept is coherent, the term is not currently used, and the property it names is real and distinct.

---

## The zkLLM connection

In 2024, Haochen Sun et al. published *zkLLM: Zero Knowledge Proofs for Large Language Models* (ACM CCS 2024, [arxiv:2404.16109](https://arxiv.org/abs/2404.16109)), the first specialised zero-knowledge proof system designed for LLM inference. zkLLM can generate a correctness proof for a 13-billion-parameter model in under 15 minutes, with proof sizes under 200 kB, without revealing model weights.

zkLLM solves a real problem: it proves that a specific model with specific weights produced a specific output for a specific input. The verifier does not need to trust the model operator. This is a strong guarantee — but it is a guarantee about the *computation*, not about the *verdict's correctness*. zkLLM does not prove that the model made the right judgment. It proves the model made *a* judgment, exactly as configured.

SAIA does not use zkLLM. The architectural choice is deliberate: zkLLM adds cryptographic proof of inference at the cost of 15 minutes per proof and impracticality for large production models. What SAIA provides instead is a permanent, timestamped, publicly auditable record of the evaluation result — anchored to a specific commit, a specific policy, and a specific moment. Arweave handles the permanence; GitHub handles the provenance; the combination handles the accountability. The trust model is different from zkLLM's, not weaker in all respects: zkLLM proves *how* the computation happened; SAIA proves *that* it happened, and makes the record impossible to alter retroactively.

The residual gap: SAIA cannot prove that the evaluation was performed by a specific model with specific weights. A zkLLM layer could close this gap. Whether that additional proof is worth the operational cost depends on the threat model. For the primary SAIA use case — a named author with reputational stakes — the permanent public record is a sufficient deterrent without hardware-level proof of inference.

---

## An interesting parallel: ZK software auditing

In October 2025, Petrovska et al. published *"Show Me You Comply… Without Showing Me Anything": Zero-Knowledge Software Auditing for AI-Enabled Systems* ([arxiv:2510.26576](https://arxiv.org/abs/2510.26576)). The paper introduces ZKMLOps, a framework for proving AI regulatory compliance — specifically EU AI Act requirements — using formal zero-knowledge proofs (SNARK, STARK, ezkl), without revealing model parameters or training data.

The problem statement is identical to SAIA's: an organisation must demonstrate that its AI system complies with a stated policy, without disclosing proprietary internals. The solution is different: ZKMLOps uses computationally expensive cryptographic proofs; SAIA uses permanent attestation with AI-assisted semantic evaluation.

Neither paper references the other's approach. The SAIA pattern — using an LLM as the evaluator rather than as the subject of a proof — does not appear in the ZK software auditing literature. The inversion is simple but absent: rather than proving *about* a model, use a model to evaluate and record a provable claim.

---

## Why wasn't this invented by the security community?

This is speculative, but worth stating.

The approaches described in zkLLM and ZKMLOps are technically sophisticated and produce strong mathematical guarantees. They are also publishable: a new ZK construction for LLM inference is a contribution to cryptography. A new SNARK circuit for regulatory compliance is a contribution to applied security.

SAIA is not that kind of contribution. It uses existing building blocks — GitHub Actions, a hosting API, Arweave, a language model, a cron schedule — assembled in a specific way to close a specific gap. There is no novel cryptographic construction. A security researcher evaluating SAIA as a research contribution might describe it as an engineering pattern, not an academic result.

This is likely why the approach was underexplored. The security research community optimises for publishable novelty. Practical compositions of existing infrastructure — even ones that close real gaps — do not map well onto conference papers. The incentive structure selects against them.

There is a second factor. The security field has a tendency to conflate the perfect with the useful. Zero-knowledge proofs offer mathematical guarantees; anything short of that is "not really ZK" and therefore not worth naming. The spectrum between "trust us entirely" and "cryptographic proof" is treated as a single undifferentiated region rather than a space with meaningful gradations. SAIA occupies a point in that space — weaker than ZK proofs, significantly stronger than no attestation — that the field has not developed vocabulary for, in part because the vocabulary was reserved for the ideal.

The consequence is a large class of practical trust problems that are formally unsolvable (you cannot write a SNARK for whether a terms-of-service clause is being followed in spirit) but practically addressable — and largely unaddressed, because the framing required to address them fell outside the dominant research paradigm.

SAIA is an attempt to name and fill one such gap.

---

## The real world already operates on imperfect guarantees

Cryptographic soundness is the exception, not the norm. Most of the trust infrastructure that holds society together is probabilistic, interpretive, and openly imperfect — and it works anyway.

**Due diligence** does not mean reading every document. An acquirer samples contracts, auditors test transactions rather than verifying all of them, and analysts triangulate from incomplete information. The process works not because it achieves certainty but because it makes concealment costly and leaves a trail.

**Legal interpretation** is not deterministic. A judge cannot know what a legislature intended; they make the best inference from text, precedent, and reasonable construction. "Reasonable time," "material breach," "good faith" are deliberately undefined — yet billions of contracts are honoured daily, not because the terms are precise but because violation carries consequences.

**Credit ratings** are expert estimates, not proofs. AAA does not mean mathematically safe; it means a rating agency assessed risk using available evidence and professional judgment. The 2008 financial crisis demonstrated the limits of that judgment — but also that the alternative, refusing to operate without mathematical certainty, would mean no capital markets at all.

**Medical diagnosis** is probabilistic. A physician does not know — they form the most defensible inference from symptoms, tests, and population statistics. The standard is not certainty but documented, reasonable process.

In each case, the system is trustworthy not because it eliminates error but because it makes the reasoning transparent, the record durable, and the consequences of deliberate deception real. SAIA operates on the same logic. The AI verdict is not a proof; it is a documented, independent evaluation made at a specific moment by a process that cannot be pressured or bribed, recorded permanently, and attributable to whoever submitted the code. That is not a lesser form of cryptographic soundness. It is a different instrument, suited to a different class of problem — the class the real world is actually made of.
