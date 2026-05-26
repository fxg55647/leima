# POIDE — Proof of Intended Deployment

Open source code is auditable. But "you can read the code" only proves that *some version* of the code is readable — not that it is the version currently running on the server. A hosting provider, a compromised deployment pipeline, or an attacker with account access could replace the running code without touching the git repository. Users would have no way to know.

POIDE (Proof of Intended Deployment) is a protocol for closing this gap. The idea is simple: query the hosting provider's API directly — not the application — to find out which git commit is deployed, then compare it to the public repository. If they match, the code the hosting provider was instructed to run is the code you can read.

**What POIDE proves — and what it does not.** POIDE records which commit the hosting provider was asked to deploy and what it reports as currently running. It does not provide cryptographic proof of what code the hosting provider actually executed in memory. That distinction matters: the proof is about *intended* deployment, not execution-level attestation. For most threat models — where the concern is an operator quietly swapping application code — this is sufficient. Hardware-level execution attestation would require trusted execution environments (TEEs) or similar infrastructure and remains out of scope for this protocol.

**Open source projects.** For software with a public repository, POIDE makes the intended deployment visible to everyone. Any user, journalist, regulator, or researcher can independently verify which commit is running without trusting the operator's word. This is a meaningful property: it turns "trust us, we run what we say" into a continuously auditable claim.

**Closed source projects.** POIDE is equally applicable to proprietary software. An organisation can use it to prove internally — to management, a compliance team, a business partner, or a regulatory authority — which version of their software was running at a given time. The audit trail on Arweave is permanent and cannot be retroactively altered, making it useful for post-incident analysis, regulatory reporting, or contractual obligations.

The code never needs to be public. The policy file is public. The verdict is public. The fact that a specific commit was reviewed against a specific policy and deployed is public. What the code actually contains remains private. This is the closed-source trust model: not "read the code and decide", but "an independent auditor checked it, the result is permanent, and the deployed version is monitored continuously."

---

## How Leima implements POIDE

Leima runs one GitHub Actions workflow (`poide-a.yml`) on a 5-minute schedule:

```
poide-a: */5 * * * *       ← minutes 0, 5, 10 ...
```

The policy file (`POLICY.example.md`) is permanently stored on Arweave ([`6Fviz2M3kx6BTkkn2fHrdJ7qtX9hRxV476f31WvUDqvR`](https://gateway.irys.xyz/6Fviz2M3kx6BTkkn2fHrdJ7qtX9hRxV476f31WvUDqvR)). Every code review is measured against this immutable copy — not the file in the repository, which could in principle be edited. The policy that governs each review cannot be changed retroactively.

Each workflow runs `poide_check.py`, which checks three conditions and publishes a combined `status.json` to the `gh-pages` branch:

1. **Deployment match** — calls the Render API and the GitHub API, verifies the live commit matches the repository HEAD
2. **No deploy in progress** — flags if Render reports an active build or update
3. **Code review passed** — queries the GitHub Actions API for the result of the latest `POIDE Code Review` run

`ok: true` requires all three to pass simultaneously.

The code review (`code_review.py`) runs automatically on every push to `main`. It sends all Python and JavaScript source files together with `POLICY.example.md` to an AI model, which checks whether the code complies with the stated data policy. If a violation is found, the workflow fails and the deployment is blocked — the server continues running the previous commit. Only when the review passes does the workflow trigger a Render deploy via a deploy hook, after which the new commit goes live.

This means code that fails the AI audit never reaches production. The deployment gate is the review itself.

The full trust chain on every commit:
```
push → code_review.yml → Gemini audits code vs POLICY.example.md
                                    ↓ pass only
                              Render deploy hook → new commit live
                                    ↓
cron (every minute) → poide_check.py → deployment match?
                                      → review passed?
                                      → no deploy in progress?
                                                 → status.json → gh-pages (public)
```

The check passes if the deployed commit matches the GitHub HEAD and the code review is green. If an unauthorised deployment has occurred — a commit that did not go through the review gate — the check fails and the GitHub Actions badge turns red.

**The result is public and independently verifiable.** Anyone can visit the [Actions tab](../../actions) to see the continuous check history, or fetch `status.json` directly. The checks run on GitHub's infrastructure — not Render's — so they cannot be influenced by a compromise of the hosting environment.

**Monitor files are hashed.** `status.json` includes SHA-256 hashes of all monitoring-related files: the cron workflow, the code review workflow, `poide_check.py`, `code_review.py`, and `POLICY.example.md`. A user or browser extension can compare these hashes across sessions. If a hash has changed, it is a signal to check what changed and why — before submitting any documents. This closes the meta-loop: the monitoring infrastructure is itself monitored by the same mechanism. An attacker who wants to slip in malicious application code must do so in a way that passes the AI code review against an unchanged `POLICY.example.md` — changing both simultaneously is significantly harder and more visible.

**Deploy history check.** Each cron run fetches the 20 most recent Render deployments and verifies that every commit hash exists in the GitHub repository. A commit that was deployed but does not appear in git is a strong indicator of tampering. The result is published in `status.json` as `history.last_mismatch_at` and `history.clean_since`. The Tampermonkey userscript shows this as a human-readable label — "puhdas historia 47 pv" on a clean run, or an orange/red warning if a mismatch was found recently. This builds a verifiable track record: the longer the clean history, the stronger the reputation.

**Cron freshness check.** Each cron run queries the GitHub Actions API for when `poide-a.yml` last ran. If it has not run within 10 minutes — twice the expected 5-minute interval — `cron_fresh` is set to false and `ok` turns false. GitHub Actions cron jobs can be delayed during high load; this makes any such delay visible automatically without requiring users to interpret timestamps.

**Deploy history as an audit trail.** Render retains the full deployment history for a service. Even if a malicious deploy were pushed and immediately reverted, it would remain visible in the history — there is no way to silently insert and remove a deployment. Combined with the fact that a Render deploy takes several minutes, any unauthorised code change will appear in a POIDE check before or shortly after the deployment completes.

**Trust boundary:** this approach assumes Render is not actively colluding — i.e., that the Render API reports the actual running commit honestly. A colluding hosting provider could lie in the API response while running different code. Mitigating that threat requires either multiple independent hosting providers each monitoring the others, or hosting-provider-level cryptographic attestation (see [Vision](#vision) below).

It is worth stating the threat hierarchy explicitly, because security analysis often fixates on residual risks without contextualising their magnitude. A hosting provider conspiracy requires a funded company with investors, legal obligations, and hundreds of other customers to commit what would likely be a criminal act and destroy their business in the process. Even broadening this to include an involuntary breach — Render itself becoming the victim of an attack that results in silent code substitution — the realistic annual probability remains on the order of 0.001–0.01%. Maintainer credential theft via phishing, SIM-swapping, or malware is a routine occurrence across the software industry; for a project maintained by a small number of individuals, the realistic annual probability is closer to 1–5%. The more likely threat is an order of magnitude of 100–1000× higher. POIDE addresses the hosting-provider layer. The maintainer-credential layer is addressed by commit signing, hardware security keys, and the automated code review that runs on every push — none of which are perfect, but together they cover the more probable attack surface. A system that is imperfect against a 0.01% threat while robust against a 5% threat is not a weak system.

---

## Checking deployment status

Before using Leima, you can verify the full trust chain in one place:

1. Open the [Actions tab](../../actions) in this repository
2. Check that **POIDE Code Review** is green on the latest commit — the code has been audited against `POLICY.example.md`
3. Check that **POIDE A** shows green on its most recent run — the running code matches the audited source
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

**Git history (GitHub API).** For each file in the monitoring infrastructure — `poide-a.yml`, `poide_check.py`, `poide_arweave.py`, `code_review.py`, and `POLICY.example.md` — it queries GitHub's commit history API to find when the file was last changed. This record is maintained by GitHub, not by Leima. A service operator cannot alter it without leaving a visible trace in the git history, which is append-only on GitHub's infrastructure.

**Arweave record.** It fetches the latest POIDE check result directly from Arweave and reads the `monitor_files` hashes stored there. Since Arweave records are permanent and cannot be retroactively altered, the hashes represent what the monitoring system observed at that moment — independently of any code the Leima service runs today.

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

These three attacks illustrate different points in the supply chain where code can be silently replaced — and where deployment transparency would have made the manipulation harder to hide.

**XZ Utils backdoor (2024).** An attacker spent years building trust in the open source community, gradually acquiring maintainer rights to XZ Utils, a compression library present in most Linux distributions. The backdoor was injected not into the visible source code but into the release process — the malicious code appeared in the distributed tarballs but not in the git repository in the same form. It was discovered almost by accident, through a performance anomaly. Had there been public build attestation, verifiable artifact provenance, and continuous runtime checks, the gap between "what the source said" and "what was actually distributed and running" would have been significantly harder to maintain silently.

**PHP git server compromise (2021).** Attackers gained access to PHP's official git server and injected a backdoor directly into the source code. The commits appeared to come from known, trusted developers — everything looked normal. The attack was caught before a release was made, but had it reached production, millions of PHP-powered websites would have been running malicious code from an apparently legitimate source. An immutable deployment log and independent runtime verification would have made the gap between "what was in git" and "what was actually running" immediately visible.

**Picreel and Alpaca Forms supply chain attack (2019).** Attackers compromised a web analytics service and several open source form libraries. The malicious code was quietly injected into JavaScript files served to over 4,600 websites. Those sites began leaking user data to an attacker-controlled server. Site owners did not know. Users did not know. The browser showed a perfectly normal page — HTTPS was green — but the runtime JavaScript had been replaced. This is the attack POIDE is most directly designed to make visible: the running code had changed, but nothing in the user's environment reflected that.

All three share the same structure: the trust signal users had — a familiar domain, a green padlock, a known developer's name on a commit — said nothing about what code was actually executing. POIDE adds the missing signal at the runtime end of the chain. Sigstore, SLSA, and reproducible builds address the earlier stages; together they cover the full path from source to running instance.

---

## Prior art and existing landscape

The problem POIDE addresses is recognised but underserved. Existing approaches fall into three categories:

**Too narrow.** Meta released [Code Verify](https://github.com/facebookincubator/meta-code-verify) (2022), a browser extension that checks WhatsApp Web, Facebook, and Instagram JavaScript against a Cloudflare-hosted reference copy. If the running code differs from the published version, the user is warned immediately. This is essentially the browser extension part of the POIDE vision — but built only for Meta's own services, with Cloudflare as the trusted third party. No general version exists that any project could adopt.

**Too heavy.** Academic and industrial research has gone in a hardware direction. HTTPA extends HTTPS with remote attestation using Intel SGX enclaves, allowing clients to verify that a server is running exactly the published code at the hardware level. Signal uses SGX for contact discovery. This is the strongest possible guarantee — but it requires Intel SGX support, re-architecting code into enclaves, and hosting provider cooperation. It is not a realistic option for small open source projects.

**Wrong layer.** Sigstore, SLSA, and in-toto are supply chain standards that secure the path from source code to build artifact. They answer: "was this binary built from this source?" POIDE answers the next question: "is this binary what is actually running?" The two are complementary — Sigstore covers source → artifact, POIDE covers artifact → running instance.

**In standardisation.** The W3C Web Application Security Working Group has discussed [Source Code Transparency](https://github.com/WICG/source-code-transparency) — a proposal to publish web app bundle hashes to a Certificate Transparency-style log, requiring browsers to verify the running code is in the log before executing it. The problem is recognised, the process is active, but nothing is in production.

**An underserved gap.** Most proposals focus on client-side JavaScript — the code the browser downloads and runs. POIDE focuses on server-side code — the code that runs on the hosting provider and processes user data. For AI services, server-side code is the only relevant surface: models cannot process encrypted data, so there is no E2E architecture to fall back on. Trust rests entirely on what the server code does. This remains an underrepresented problem space.

POIDE's differentiator is that it works with existing building blocks — a hosting provider API, GitHub API, GitHub Actions, and a cron schedule. No browser changes, no hardware enclaves, no new standardisation processes, no partnership agreements. Any open source project can adopt it over a weekend. The guarantee is weaker than SGX attestation, but meaningfully stronger than "trust us because we're open source" — and it is deployable today.

---

## Adopting POIDE for any project

Any project — open or closed source — can wire POIDE with a small amount of GitHub Actions configuration. No separate infrastructure is needed. Leima exposes a public API that handles the code review step.

**How it works in practice**

1. **Write a policy file.** Describe in plain language what the code is and is not allowed to do: which external services it may call, what data it may store, what it must never transmit. Publish the policy file permanently on Arweave so its contents cannot be changed retroactively.

2. **Add a GitHub Actions workflow.** On each push to `main`, call Leima's `/api/code-review` endpoint with the repository name, the commit SHA, and the URL of your policy file. Leima fetches the source tree from GitHub, reviews it against the policy using AI, and returns a `compliant` result with a permanent Arweave stamp.

   ```yaml
   - name: Code review
     run: |
       RESULT=$(curl -s -X POST \
         -H "Content-Type: application/json" \
         -d '{"repo":"owner/repo","ref":"${{ github.sha }}","rules_url":"https://gateway.irys.xyz/YOUR_POLICY_TX"}' \
         https://leima.ai/api/code-review)
       compliant=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['compliant'])")
       if [ "$compliant" != "True" ]; then exit 1; fi
   ```

3. **Gate the deploy.** Place the deploy step after the review step. If the review fails, the workflow exits and the deploy does not run. The code that failed the policy check never reaches production.

4. **Add POIDE monitoring.** Add cron workflows that periodically compare the live commit (via the hosting provider's API) against the GitHub HEAD. Publish the result publicly. Anyone — a regulator, a business partner, a user — can check the status at any time without credentials.

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

The gap between "we have a security policy" and "we can prove the running code follows it" is normally bridged by expensive audits and manual processes. POIDE closes that gap for code-level compliance continuously and automatically.

---

## Vision

The current implementation is a practical first step. The logical end state is a fully automated trust chain that requires no manual verification from users.

**Independent commit auditing.** When a new commit is pushed to the repository, an independent service — operated by a party unrelated to Leima — automatically audits the new code. The audit checks that the new commit does not introduce data exfiltration, does not change the AI prompts in ways that would alter verdicts, and does not connect to unauthorised external services. Results are published publicly before the commit is deployed.

The current implementation (`code_review.py`) is a working example of this idea rather than the end state. A single AI model checking its own host application's code has obvious limitations — the model may have blind spots, and the check runs on the same infrastructure it is auditing. The stronger form involves multiple independent AI models reviewing each commit simultaneously, an external service operated by a party with no relationship to the application, and optionally human reviewers for significant changes. Consensus across independent reviewers is harder to manipulate than a single automated check.

**Visible in the application UI.** The current deployment status and the last audit result are shown directly in the application — not just on GitHub. Users do not need to open a separate page. A mismatch or a failed audit blocks the UI until resolved.

**Userscript (available now).** A Tampermonkey/Greasemonkey userscript ([`poide.user.js`](poide.user.js)) is included in the repository. It uses `GM_xmlhttpRequest` — which runs in the browser extension's isolated context, not the page's JavaScript environment — so a compromised Leima page cannot intercept or spoof the check. On each page load it fetches `status.json`, shows a green banner if everything is in order, and a red warning if not. It also compares `monitor_files` hashes against the previous session using `GM_getValue`/`GM_setValue`, alerting if any monitoring file has changed.

**Browser extension.** A dedicated browser extension would make the same check fully automatic for any POIDE-enabled application without requiring manual userscript installation. No manual check required.

**Hosting platform attestation.** The cleanest solution is for hosting providers to publish cryptographically signed deployment records: *"we certify that service X is running commit Y, signed with our public key."* This would make third-party monitoring unnecessary — the platform itself provides the proof, and any client can verify it. Until hosting platforms offer this natively, external monitoring is the practical alternative.

**Versioned user consent.** When a user first uses an application, they accept what it may do with their data — but that acceptance is tied to a specific, audited version of the code. When a new commit is deployed and passes the audit, the auditor checks whether the new code does anything materially different from what the user already accepted: new data destinations, changed retention behaviour, altered AI prompts, new third-party integrations. If the change is within what was previously accepted, the user is not interrupted. If it falls outside, the user is notified and asked to re-consent before continuing. The terms do not change silently between sessions — the code does not change silently between sessions.

**Standardisation.** POIDE could become a badge and a protocol that any hosted open source project can adopt — analogous to how HTTPS became a baseline expectation. A project that exposes a verifiable deployment status makes a stronger trust claim than one that only publishes source code.

The underlying principle is the same throughout: trust is not granted to a company or a person. It is granted to a specific, verified version of code — and automatically re-evaluated whenever the code changes.
