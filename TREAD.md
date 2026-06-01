# TREAD — Transparent Record of Evaluation, Attestation and Deployment

*TREAD is the deployment integrity layer of the SAIA (Sealed AI Attestations Architecture) pattern. See [ZKSE.md](ZKSE.md) for a discussion of how SAIA relates to zero-knowledge proof systems.*

Open source code is auditable. But "you can read the code" only proves that *some version* of the code is readable — not that it is the version currently running on the server. A hosting provider, a compromised deployment pipeline, or an attacker with account access could replace the running code without touching the git repository. Users would have no way to know.

TREAD (Transparent Record of Evaluation, Attestation and Deployment) is a protocol for closing this gap. The idea is simple: query the hosting provider's API directly — not the application — to find out which git commit is deployed, then verify it exists in the repository and passed the code review before deployment. The record of what was deployed, when, and whether it was reviewed is permanent and independently verifiable.

**What TREAD proves — and what it does not.** TREAD records which commit the hosting provider was asked to deploy and what it reports as currently running. It does not provide cryptographic proof of what code the hosting provider actually executed in memory. That distinction matters: the record is about *intended* deployment, not execution-level attestation. For most threat models — where the concern is an operator quietly swapping application code — this is sufficient. Hardware-level execution attestation would require trusted execution environments (TEEs) or similar infrastructure and remains out of scope for this protocol.

**Open source projects.** For software with a public repository, TREAD makes the intended deployment visible to everyone. Any user, journalist, regulator, or researcher can independently verify which commit is running without trusting the operator's word. This is a meaningful property: it turns "trust us, we run what we say" into a continuously auditable claim.

**Closed source projects.** Open source has never been a trust property in itself — it is one implementation of auditing. In practice, almost nobody reads open source code, and fewer still can evaluate it for security. XZ Utils was open for years; the backdoor went unnoticed. Auditing produces trust only when someone actually looks.

TREAD decouples auditing from visibility. What a user actually needs is not the code in front of their eyes — they need proof that someone competent reviewed it, and that what was reviewed is the same as what is running. TREAD produces this without requiring the code to be public.

This leads to a conclusion worth stating directly: TREAD-protected closed source can offer a stronger auditability guarantee than unreviewed open source. Open source has value elsewhere — in fork rights, as an educational resource, in collective contribution — but on the trust question, the mechanism is what matters, not the visibility.

Open source alone is not sufficient for trust. TREAD is the part that was missing. An organisation can use it to prove to management, a compliance team, a business partner, or a regulatory authority which version of their software was running at a given time — and that it was reviewed against a stated policy before deployment. The audit trail on Arweave is permanent and cannot be retroactively altered, making it useful for post-incident analysis, regulatory reporting, or contractual obligations.

The code never needs to be public. The policy file is public. The verdict is public. The fact that a specific commit was reviewed against a specific policy and deployed is public. What the code actually contains remains private. This is the closed-source trust model: not "read the code and decide", but "an independent auditor checked it, the result is permanent, and the deployed version is monitored continuously."

---

## How Leima implements TREAD

*For a detailed threat model and vulnerability analysis of each component, see [SECURITY_MODEL.md](SECURITY_MODEL.md).*

Leima runs five GitHub Actions workflows on a staggered schedule, together achieving one-minute polling resolution:

```
tread-a: */5 * * * *       ← minutes 0, 5, 10 ...
tread-b: 1-59/5 * * * *    ← minutes 1, 6, 11 ...
tread-c: 2-59/5 * * * *    ← minutes 2, 7, 12 ...
tread-d: 3-59/5 * * * *    ← minutes 3, 8, 13 ...
tread-e: 4-59/5 * * * *    ← minutes 4, 9, 14 ...
```

The policy file (`POLICY.example.md`) is permanently stored on Arweave ([`6Fviz2M3kx6BTkkn2fHrdJ7qtX9hRxV476f31WvUDqvR`](https://gateway.irys.xyz/6Fviz2M3kx6BTkkn2fHrdJ7qtX9hRxV476f31WvUDqvR)). Every code review is measured against this immutable copy — not the file in the repository, which could in principle be edited. The policy that governs each review cannot be changed retroactively.

Each workflow runs `tread_check.py`, which evaluates three conditions for `ok: true` and publishes a combined `status.json` to the `gh-pages` branch:

1. **Deployment safe** — the live commit matches the repository HEAD, or a legitimate deployment is currently in progress
2. **Cron fresh** — at least one of the five TREAD workflows ran within the last 10 minutes
3. **No disabled workflows** — all monitored workflows remain active

`review_ok` (whether the latest code review passed) is tracked and published in `status.json` but does not gate `ok` directly — code review gates deployment via the deploy hook, so a commit that failed review never reaches production in the first place.

The code review (`code_review.py`) runs automatically on every push to `main`. It sends all Python and JavaScript source files together with `POLICY.example.md` to an AI model, which checks whether the code complies with the stated data policy. If a violation is found, the workflow fails and the deployment is blocked — the server continues running the previous commit. Only when the review passes does the workflow trigger a Render deploy via a deploy hook, after which the new commit goes live.

This means code that fails the AI audit never reaches production. The deployment gate is the review itself.

**Limitation: prompt injection in the code review gate.** The review is most reliable when those who write the code have no incentive to deceive the reviewer — for instance, when detecting unintentional policy drift or commercial pressure to quietly weaken a privacy guarantee. Against an external attacker who has compromised the repository or the deployment pipeline, the situation is different: such an actor may embed instructions in comments, string literals, or documentation specifically crafted to manipulate the AI reviewer's verdict, and has no reputational stake in the outcome.

For the primary threat model — a closed-source author who might consider monetizing user data in violation of their stated policy — the calculus is different. That actor's identity is bound to the code. Any prompt injection attempt would be permanently recorded on Arweave and, if discovered, would constitute visible and attributable proof of deliberate deception. The reputational damage would be permanent and irreversible. Prompt injection therefore provides less cover, not more, to a named party operating under their own identity: the permanent record works against them.

The deployment version check is unaffected by either scenario — it is a deterministic comparison of commit hashes and cannot be influenced by code content. The AI analysis component should be understood as an independent evaluation, not a tamper-proof gate against an external adversary.

The full trust chain on every commit:
```
push → code_review.yml → Gemini audits code vs POLICY.example.md
                                    ↓ pass only
                              Render deploy hook → new commit live
                                    ↓
cron (every minute) → tread_check.py → deployment safe?
                                      → cron fresh?
                                      → no disabled workflows?
                                      → review_ok? (tracked separately)
                                                 → status.json → gh-pages (public)
```

The check passes if the deployed commit matches the repository HEAD, the cron workflows are running, and no monitored workflow has been disabled. If an unauthorised deployment has occurred — a commit that did not go through the review gate — `deployment_ok` turns false and the GitHub Actions badge turns red.

**The result is public and independently verifiable.** Anyone can visit the [Actions tab](../../actions) to see the continuous check history, or fetch `status.json` directly. The checks run on GitHub's infrastructure — not Render's — so they cannot be influenced by a compromise of the hosting environment. This does mean GitHub Actions is part of the trust boundary: a compromise of GitHub's infrastructure or the repository's Actions configuration could in principle affect the monitoring results. This is a real but theoretical risk — GitHub is a large platform with its own security controls, and the attack surface is meaningfully different from a single hosting provider. It is worth naming openly rather than treating TREAD as fully independent of all platforms.

**Monitor files are hashed.** `status.json` includes SHA-256 hashes of all monitoring-related files: the five cron workflows, the code review workflow, `tread_check.py`, `code_review.py`, and `POLICY.example.md`. A user or browser extension can compare these hashes across sessions. If a hash has changed, it is a signal to check what changed and why — before submitting any documents. This closes the meta-loop: the monitoring infrastructure is itself monitored by the same mechanism. An attacker who wants to slip in malicious application code must do so in a way that passes the AI code review against an unchanged `POLICY.example.md` — changing both simultaneously is significantly harder and more visible.

**Deploy history check.** Each cron run fetches the 100 most recent Render deployments and verifies that every commit hash exists in the GitHub repository. A commit that was deployed but does not appear in git is a strong indicator of tampering. The result is published in `status.json` as `history.last_mismatch_at` and `history.clean_since`. The Tampermonkey userscript shows this as a human-readable label — "puhdas historia 47 pv" on a clean run, or an orange/red warning if a mismatch was found recently. This builds a verifiable track record: the longer the clean history, the stronger the reputation.

**Cron freshness check.** Each cron run queries the GitHub Actions API for when all five TREAD workflows last ran. If none has run within 10 minutes — twice the expected 5-minute interval — `cron_fresh` is set to false and `ok` turns false. GitHub Actions cron jobs can be delayed during high load; this makes any such delay visible automatically without requiring users to interpret timestamps.

**Deploy history as an audit trail.** Render retains the full deployment history for a service. Even if a malicious deploy were pushed and immediately reverted, it would remain visible in the history — there is no way to silently insert and remove a deployment. Combined with the fact that a Render deploy takes several minutes, any unauthorised code change will appear in a TREAD check before or shortly after the deployment completes.

**Trust boundary:** this approach assumes Render is not actively colluding — i.e., that the Render API reports the actual running commit honestly. A colluding hosting provider could lie in the API response while running different code. Mitigating that threat requires either multiple independent hosting providers each monitoring the others, or hosting-provider-level cryptographic attestation (see [Vision](#vision) below).

It is worth stating the threat hierarchy explicitly, because security analysis often fixates on residual risks without contextualising their magnitude. A hosting provider conspiracy requires a funded company with investors, legal obligations, and hundreds of other customers to commit what would likely be a criminal act and destroy their business in the process. Even broadening this to include an involuntary breach — Render itself becoming the victim of an attack that results in silent code substitution — the realistic annual probability remains on the order of 0.001–0.01%. Maintainer credential theft via phishing, SIM-swapping, or malware is a routine occurrence across the software industry; for a project maintained by a small number of individuals, the realistic annual probability is closer to 1–5%. The more likely threat is an order of magnitude of 100–1000× higher. TREAD addresses the hosting-provider layer. The maintainer-credential layer is addressed by commit signing, hardware security keys, and the automated code review that runs on every push — none of which are perfect, but together they cover the more probable attack surface. A system that is imperfect against a 0.01% threat while robust against a 5% threat is not a weak system.

---

## Checking deployment status

Before using Leima, you can verify the full trust chain in one place:

1. Open the [Actions tab](../../actions) in this repository
2. Check that **TREAD Code Review** is green on the latest commit — the code has been audited against `POLICY.example.md`
3. Check that the five **TREAD A–E** workflows show green on their most recent runs — the running code matches the audited source
4. Optionally fetch [`status.json`](../../raw/refs/heads/gh-pages/status.json) and compare the `monitor_files` hashes against your previous session — if any hash has changed, check what changed and why before submitting documents

If any workflow is red, either a policy violation was detected in the code or a deployment mismatch was found within the last minute. Do not submit sensitive documents until the checks recover.

---

## Independent verification with verify.py

The checks above rely on GitHub's UI and the Actions tab — which are legitimate independent sources, but require navigating to a browser. `verify.py` is a standalone script that can be run from any machine, without logging in to anything, and without contacting the Leima service at all.

```bash
pip install requests
python verify.py
```

([`verify.py`](verify.py))

It uses two independent sources for each monitored file:

**Git history (GitHub API).** For each file in the monitoring infrastructure — the five cron workflows, `tread_check.py`, `tread_arweave.py`, `code_review.py`, and `POLICY.example.md` — it queries GitHub's commit history API to find when the file was last changed. This record is maintained by GitHub, not by Leima. A service operator cannot alter it without leaving a visible trace in the git history, which is append-only on GitHub's infrastructure.

**Arweave record.** It fetches the latest TREAD check result directly from Arweave and reads the `monitor_files` hashes stored there. Since Arweave records are permanent and cannot be retroactively altered, the hashes represent what the monitoring system observed at that moment — independently of any code the Leima service runs today.

If both sources agree and the files are unchanged, the monitoring infrastructure has been consistent and auditable: any commit mismatch during that period would have been detected and recorded, and every change to the monitoring code itself would be visible in git history.

The script also reports the last commit mismatch — when it occurred and when it resolved — so a returning user can assess at a glance whether anything unexpected happened during their absence.

**Pinning to a trusted moment.** If you note the Arweave TX from a run you personally verified, you can compare the current state against that exact historical snapshot:

```bash
python verify.py <tx_id>
```

A TX you trusted six months ago cannot be altered. If the current files match it, nothing relevant has changed since that moment.

**Why this matters for the trust model.** `audit.html` and the Tampermonkey userscript both fetch data served by or through Leima's infrastructure. A sufficiently motivated attacker who had compromised the service could potentially alter what those pages display. `verify.py` does not use Leima's infrastructure at all — it goes directly to GitHub and Arweave, both of which are controlled by independent third parties. It is the closest thing to a trust-free verification path available without hardware attestation.

---

## Real-world incidents

These incidents illustrate different points in the supply chain where code can be silently replaced — and where deployment transparency would have made the manipulation harder to hide.

**PHP git server compromise (2021).** Attackers gained access to PHP's official git server and injected a backdoor directly into the source code. The commits appeared to come from known, trusted developers — everything looked normal. The attack was caught before a release was made. This is a partial fit for TREAD: had the malicious commit been legitimately deployed, TREAD would have reported deployed == repository — which is technically accurate, but no longer means safe. What TREAD would have provided is a permanent, independently verifiable record of exactly which commit reached production and when, making post-incident analysis faster and the timeline harder to dispute. It does not protect against an attacker who has already compromised the repository itself.

**Picreel and Alpaca Forms supply chain attack (2019).** Attackers compromised a web analytics service and several open source form libraries. The malicious code was quietly injected into JavaScript files served to over 4,600 websites. Those sites began leaking user data to an attacker-controlled server. Site owners did not know. Users did not know. The browser showed a perfectly normal page — HTTPS was green — but the runtime JavaScript had been replaced. This is the attack TREAD is most directly designed to make visible: the running code had changed, but nothing in the user's environment reflected that.

Both share the same structure: the trust signal users had — a familiar domain, a green padlock, a known developer's name on a commit — said nothing about what code was actually executing. TREAD adds a missing signal at the runtime end of the chain. Sigstore, SLSA, and reproducible builds address the earlier stages; together they cover the full path from source to running instance.

**On the prevalence of hosting-layer abuse.** In practice, hosting providers and infrastructure operators are rarely caught accessing user data or running modified code — not because it never happens, but because it is very difficult to detect. There is no reliable way for a user to verify what code is actually executing on a remote server, and providers have no strong incentive to make this auditable. The true frequency of quiet abuse is unknowable. TREAD does not eliminate this risk, but it makes any tampering detectable rather than invisible.

---

## Prior art and existing landscape

The problem TREAD addresses is recognised but underserved. Existing approaches fall into three categories:

**Too narrow.** Meta released [Code Verify](https://github.com/facebookincubator/meta-code-verify) (2022), a browser extension that checks WhatsApp Web, Facebook, and Instagram JavaScript against a Cloudflare-hosted reference copy. If the running code differs from the published version, the user is warned immediately. This is essentially the browser extension part of the TREAD vision — but built only for Meta's own services, with Cloudflare as the trusted third party. No general version exists that any project could adopt.

**Too heavy.** Academic and industrial research has gone in a hardware direction. HTTPA extends HTTPS with remote attestation using Intel SGX enclaves, allowing clients to verify that a server is running exactly the published code at the hardware level. Signal uses SGX for contact discovery. This is the strongest possible guarantee — but it requires Intel SGX support, re-architecting code into enclaves, and hosting provider cooperation. It is not a realistic option for small open source projects.

**Wrong layer.** Sigstore, SLSA, and in-toto are supply chain standards that secure the path from source code to build artifact. They answer: "was this binary built from this source?" TREAD answers the next question: "is this binary what is actually running?" The two are complementary — Sigstore covers source → artifact, TREAD covers artifact → running instance.

**In standardisation.** The W3C Web Application Security Working Group has discussed [Source Code Transparency](https://github.com/WICG/source-code-transparency) — a proposal to publish web app bundle hashes to a Certificate Transparency-style log, requiring browsers to verify the running code is in the log before executing it. The problem is recognised, the process is active, but nothing is in production.

**An underserved gap.** Most proposals focus on client-side JavaScript — the code the browser downloads and runs. TREAD focuses on server-side code — the code that runs on the hosting provider and processes user data. For AI services, server-side code is the only relevant surface: models cannot process encrypted data, so there is no E2E architecture to fall back on. Trust rests entirely on what the server code does. This remains an underrepresented problem space.

TREAD's differentiator is that it works with existing building blocks — a hosting provider API, GitHub API, GitHub Actions, and a cron schedule. No browser changes, no hardware enclaves, no new standardisation processes, no partnership agreements. Any project — open or closed source — can adopt it over a weekend. The guarantee is weaker than SGX attestation, but meaningfully stronger than "trust us because we're open source" — and it is deployable today.

---

## Statistical proof and the ZK analogy

*For a deeper discussion of how SAIA relates to zero-knowledge proof systems — including the zkLLM paper, the Zero-Knowledge Semantic Evaluation concept, and why this approach may have been underexplored by the security research community — see [ZKSE.md](ZKSE.md).*

*This section covers the broader Leima trust model — both the AI document analysis and the TREAD deployment layer — and how they relate to cryptographic proof systems.*

Zero-knowledge proofs establish a fact to a verifier without requiring trust in the prover and without revealing the underlying evidence. The guarantee is mathematical: either the proof is valid or it is not, with no probability involved. This is the gold standard for trustless verification, and it is expensive — computationally, architecturally, and operationally.

Leima's approach occupies a different point on the same spectrum. A large language model is a statistical function over its training distribution, and its output on a given input reflects regularities across an enormous corpus of human reasoning. When the same model applies the same instructions to the same document, the results are not random — they are systematic, reproducible within the model's stochastic bounds, and independent of the interests of any human reviewer. This is a weaker and structurally different guarantee than ZK: it does not satisfy soundness in the cryptographic sense, and the LLM's output is probabilistic, not mathematically constrained. Where it shares something with ZK is narrower: the evaluator has no knowledge of the author's identity, organisational context, or background not explicitly submitted — the evaluation is blind in that specific sense. Whether this partial property warrants ZK-adjacent terminology is a question best left to the broader research and security community.

TREAD's code review layer makes this explicit. Every commit is evaluated by an AI against an immutable policy document stored on Arweave. The AI cannot be bribed, pressured, or distracted. It cannot forget to check a clause. The policy it evaluates against cannot be retroactively altered. The result — pass or fail — is recorded permanently. This is not a mathematical proof that the code is safe. It is a statistical proof that an independent reviewer, applying consistent criteria, found no violation. For the threat model it addresses — a small team under commercial pressure quietly weakening a privacy policy — the statistical proof is both sufficient and practical.

The conceptual lineage matters for understanding what Leima is. ZK proofs democratised one class of trustless verification by making it computationally feasible. Leima applies the same underlying ambition — verification without trust, at scale, without expensive infrastructure — to a class of problems ZK cannot reach: natural language documents, human-readable claims, and code that must be reviewed for intent rather than correctness. The mathematical foundation is different (statistical rather than algebraic), the cost is orders of magnitude lower, and the scope is broader. It is not a weaker ZK. It is a different tool solving an adjacent problem.

One residual risk is worth naming: the AI evaluator can in principle be poisoned. A document crafted with adversarial intent — embedded instructions, misleading framing, or content designed to manipulate the model's output — could cause the verdict to misrepresent what the document actually says. In most practical use cases this risk is either negligible or detectable. Documents from official or institutional sources — court records, financial statements, authenticated emails — are not under the adversary's control at the time of stamping; there is no surface for injection. Where the document originates from the submitting party, adversarial manipulation would produce a verdict whose stated reasoning is inconsistent with the source document — visible to any human reviewer who checks the original. The claim submitted by the requester — including any interpretive preferences or instructions attached to it — is always reproduced verbatim in the verdict document. Any adversarial instruction embedded there would be immediately visible to anyone reading the verdict. Explicit prompt injection protection can be applied at the instruction level to reduce susceptibility further. Running multiple independent models simultaneously and requiring agreement across verdicts reduces the risk further still: a successful attack would need to fool several architectures with different training distributions at once. No single mitigation is absolute, but in combination they make undetected manipulation significantly harder than any single-reviewer process — human or automated.

The code review use case has a different risk profile depending on who controls the code. Document analysis typically uses source material from third parties — official authorities, institutions, counterparties — not under the adversary's control, so there is little practical surface for injection. For code review, the distinction matters: an external attacker who controls the code being reviewed can embed adversarial instructions with no reputational stake in the outcome. A closed-source author reviewing their own codebase is in a different position — their identity is attributed to every commit, any manipulation attempt is permanently recorded, and discovery would mean lasting and irreversible damage to their reputation. The code review gate is most effective against the latter threat, which is also the more common one. The deployment version matching provides a separate, stronger guarantee that is not affected by prompt injection in either case.

---

## Adopting TREAD for any project

Any project — open or closed source — can wire TREAD with a small amount of GitHub Actions configuration. No separate infrastructure is needed. Leima exposes a public API that handles the code review step.

**How it works in practice**

1. **Write a policy file.** Describe in plain language what the code is and is not allowed to do: which external services it may call, what data it may store, what it must never transmit. Publish the policy file permanently on Arweave so its contents cannot be changed retroactively.

2. **Add a GitHub Actions workflow.** On each push to `main`, call Leima's `/api/code-review` endpoint with the repository name, the commit SHA, and the URL of your policy file. Leima fetches the source tree from GitHub, reviews it against the policy using AI, and returns a `compliant` result with a permanent Arweave stamp.

   ```yaml
   - name: Code review
     run: |
       RESULT=$(curl -s -X POST \
         -H "Content-Type: application/json" \
         -d '{"repo":"owner/repo","ref":"${{ github.sha }}","rules_url":"https://gateway.irys.xyz/YOUR_POLICY_TX"}' \
         https://leima.io/api/code-review)
       compliant=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['compliant'])")
       if [ "$compliant" != "True" ]; then exit 1; fi
   ```

3. **Gate the deploy.** Place the deploy step after the review step. If the review fails, the workflow exits and the deploy does not run. The code that failed the policy check never reaches production.

4. **Add TREAD monitoring.** Add cron workflows that periodically compare the live commit (via the hosting provider's API) against the GitHub HEAD. Publish the result publicly. Anyone — a regulator, a business partner, a user — can check the status at any time without credentials.

**What this achieves for a closed-source project**

An independent third party (Leima) reviewed the code against a policy that was publicly committed to in advance. The review result is permanently recorded on Arweave and cannot be altered. The deployed version is continuously monitored. The code itself remains private; the process is transparent.

A regulator, auditor, or customer does not need to read the code. They can verify that: a review happened, the policy the review was measured against, whether the code passed, and that the version currently running is the same one that passed. That is a meaningfully stronger claim than "trust us."

**Minimal requirements**

- A GitHub repository (private repositories work; Leima uses a token you supply or the repository's own `GITHUB_TOKEN`)
- A hosting provider with a deployment API (Render, Railway, Fly.io, or others)
- A policy file — a plain text document describing what the code is allowed to do

The policy file is the only thing that needs to be written from scratch. The rest is configuration.

**What this enables beyond end-user trust**

Continuous code review against a fixed policy opens up use cases beyond user-facing trust:

- **Due diligence.** An investor or acquirer can verify, for any commit in the repository's history, whether the code was compliant with the stated policy at that time. The review results are permanently on Arweave — they cannot be produced retroactively to look better than they were. This is a near-real-time audit trail that would normally require a dedicated security team and weeks of work per engagement.

- **Continuous security monitoring.** Every commit is reviewed before it can be deployed. Any change that introduces data exfiltration, an unauthorised external call, or a violation of the stated data handling policy is caught at the gate. The monitoring is not a periodic snapshot — it is continuous and tied to the deployment pipeline. A security team or regulator can check the current status, and the full history, at any time.

- **Compliance reporting.** For regulated industries — fintech, healthcare, legal — the permanent Arweave record provides a timestamped compliance trail without additional tooling. "The code was reviewed against policy X at commit Y on date Z, and passed" is a statement that can be independently verified.

The gap between "we have a security policy" and "we have strong, independently verifiable evidence that the running code follows it" is normally bridged by expensive audits and manual processes. TREAD closes that gap for code-level compliance continuously and automatically.

---

## Vision

The current implementation is a practical first step. The logical end state is a fully automated trust chain that requires no manual verification from users.

**Independent commit auditing.** When a new commit is pushed to the repository, an independent service — operated by a party unrelated to Leima — automatically audits the new code. The audit checks that the new commit does not introduce data exfiltration, does not change the AI prompts in ways that would alter verdicts, and does not connect to unauthorised external services. Results are published publicly before the commit is deployed.

The current implementation (`code_review.py`) is a working example of this idea rather than the end state. A single AI model checking its own host application's code has obvious limitations — the model may have blind spots, and the check runs on the same infrastructure it is auditing. The stronger form involves multiple independent AI models reviewing each commit simultaneously, an external service operated by a party with no relationship to the application, and optionally human reviewers for significant changes. Consensus across independent reviewers is harder to manipulate than a single automated check.

**Visible in the application UI.** The current deployment status and the last audit result are shown directly in the application — not just on GitHub. Users do not need to open a separate page. A mismatch or a failed audit blocks the UI until resolved.

**Userscript (available now).** A Tampermonkey/Greasemonkey userscript ([`tread.user.js`](tread.user.js)) is included in the repository. It uses `GM_xmlhttpRequest` — which runs in the browser extension's isolated context, not the page's JavaScript environment — so a compromised Leima page cannot intercept or spoof the check. On each page load it fetches `status.json`, shows a green banner if everything is in order, and a red warning if not. It also compares `monitor_files` hashes against the previous session using `GM_getValue`/`GM_setValue`, alerting if any monitoring file has changed.

**Browser extension.** A dedicated browser extension would make the same check fully automatic for any TREAD-enabled application without requiring manual userscript installation. No manual check required.

**Hosting platform attestation.** The cleanest solution is for hosting providers to publish cryptographically signed deployment records: *"we certify that service X is running commit Y, signed with our public key."* This would make third-party monitoring unnecessary — the platform itself provides the proof, and any client can verify it. Until hosting platforms offer this natively, external monitoring is the practical alternative.

This is where the loop closes completely. The current TREAD implementation has one residual trust assumption: Render reports the deployed commit honestly. External cron monitoring can detect a mismatch if the running code diverges from what Render reports — but it cannot detect the case where Render actively lies in its own API response while running different code. That requires either multiple independent providers monitoring each other, or the provider itself making a cryptographically verifiable commitment.

A commit ID alone is not sufficient. A provider could report the correct commit ID while running different code entirely. The complete proof requires two things: a signed record of which commit was deployed, and a signed hash of the actual code being executed — not just the identifier of the commit it claims to be running. Only when both are present can a third party verify the full chain without trusting anyone's word.

If a provider like Render natively adopted TREAD — publishing signed records that include both the commit ID and a hash of the deployed code bundle, written to a public ledger such as Arweave — the trust chain would be complete: the code was reviewed before deployment (AI audit), the reviewed code is what was deployed (provider-signed code hash), and the record is permanent and tamper-proof (Arweave). No third party would need to poll, guess, or trust anyone's word. The proof would exist independently of both the application operator and the monitoring infrastructure.

This is a realistic near-term development. Hosting providers already compute and store deployment artifacts internally. Publishing a hash of those artifacts — with no sensitive infrastructure detail exposed — would be a modest engineering effort with a significant trust payoff. The first provider to offer this would have a meaningful differentiator for security-conscious customers.

**Versioned user consent.** When a user first uses an application, they accept what it may do with their data — but that acceptance is tied to a specific, audited version of the code. When a new commit is deployed and passes the audit, the auditor checks whether the new code does anything materially different from what the user already accepted: new data destinations, changed retention behaviour, altered AI prompts, new third-party integrations. If the change is within what was previously accepted, the user is not interrupted. If it falls outside, the user is notified and asked to re-consent before continuing. The terms do not change silently between sessions — the code does not change silently between sessions.

**Deployment freeze windows.** A maintainer will be able to publish a signed, time-bounded commitment — *"no new code will be deployed between T1 and T2"* — written to the public status log. During the window, the pre-push hook blocks any deployment attempt automatically. This gives security-conscious users a window in which to audit the source code and then use the service with a stronger guarantee: not only is the running commit known, but it is contractually frozen for the duration. If a deployment event is detected inside the window anyway — via the cron monitor — it must be treated as a hostile event regardless of the stated reason. A legitimate critical patch does not justify silent deployment during a freeze: the correct response is to end the window early with a public explanation, allow users to re-audit, and open a new window. A deploy that simply appears, even accompanied by a plausible justification, is indistinguishable from a compromised maintainer account offering a cover story. The application UI surfaces this as a distinct high-severity warning, separate from the ordinary "deploying" state, so users can suspend use until the record is explained.

**Standardisation.** TREAD could become a badge and a protocol that any hosted open source project can adopt — analogous to how HTTPS became a baseline expectation. A project that exposes a verifiable deployment status makes a stronger trust claim than one that only publishes source code.

The underlying principle is the same throughout: trust is not granted to a company or a person. It is granted to a specific, verified version of code — and automatically re-evaluated whenever the code changes.
