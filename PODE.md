# PoDe — Proof of Deployment

Open source code is auditable. But "you can read the code" only proves that *some version* of the code is readable — not that it is the version currently running on the server. A hosting provider, a compromised deployment pipeline, or an attacker with account access could replace the running code without touching the git repository. Users would have no way to know.

PoDe (Proof of Deployment) is a protocol for closing this gap. The idea is simple: query the hosting provider's API directly — not the application — to find out which git commit is deployed, then compare it to the public repository. If they match, the code running is the code you can read.

---

## How Leima implements PoDe

Leima runs five GitHub Actions workflows on a staggered schedule, together achieving one-minute polling resolution:

```
pode-a: */5 * * * *       ← minutes 0, 5, 10 ...
pode-b: 1-59/5 * * * *    ← minutes 1, 6, 11 ...
pode-c: 2-59/5 * * * *    ← minutes 2, 7, 12 ...
pode-d: 3-59/5 * * * *    ← minutes 3, 8, 13 ...
pode-e: 4-59/5 * * * *    ← minutes 4, 9, 14 ...
```

Each workflow runs `pode_check.py`, which checks three conditions and publishes a combined `status.json` to the `gh-pages` branch:

1. **Deployment match** — calls the Render API and the GitHub API, verifies the live commit matches the repository HEAD
2. **No deploy in progress** — flags if Render reports an active build or update
3. **Code review passed** — queries the GitHub Actions API for the result of the latest `PoDe Code Review` run

`ok: true` requires all three to pass simultaneously.

The code review (`code_review.py`) runs automatically on every push to `main`. It sends all Python and JavaScript source files together with `POLICY.md` to an AI model, which checks whether the code complies with the stated data policy. If a violation is found, the workflow fails and `review_ok` stays false until a corrected commit is pushed and passes.

The full trust chain on every commit:
```
push → code_review.yml → Gemini audits code vs POLICY.md → pass/fail
                                                                  ↓
cron (every minute) → pode_check.py → deployment match?
                                     → review passed?
                                     → no deploy in progress?
                                                → status.json → gh-pages (public)
```

The check passes if the deployed commit matches the GitHub HEAD and the code review is green. If a deploy is in progress, or if an unauthorised deployment has occurred, the check fails and the GitHub Actions badge turns red.

**The result is public and independently verifiable.** Anyone can visit the [Actions tab](../../actions) to see the continuous check history, or fetch `status.json` directly. The checks run on GitHub's infrastructure — not Render's — so they cannot be influenced by a compromise of the hosting environment.

**Monitor files are hashed.** `status.json` includes SHA-256 hashes of all monitoring-related files: the five cron workflows, the code review workflow, `pode_check.py`, `code_review.py`, and `POLICY.md`. A user or browser extension can compare these hashes across sessions. If a hash has changed, it is a signal to check what changed and why — before submitting any documents. This closes the meta-loop: the monitoring infrastructure is itself monitored by the same mechanism. An attacker who wants to slip in malicious application code must do so in a way that passes the AI code review against an unchanged `POLICY.md` — changing both simultaneously is significantly harder and more visible.

**Deploy history check.** Each cron run fetches the 20 most recent Render deployments and verifies that every commit hash exists in the GitHub repository. A commit that was deployed but does not appear in git is a strong indicator of tampering. The result is published in `status.json` as `history.last_mismatch_at` and `history.clean_since`. The Tampermonkey userscript shows this as a human-readable label — "puhdas historia 47 pv" on a clean run, or an orange/red warning if a mismatch was found recently. This builds a verifiable track record: the longer the clean history, the stronger the reputation.

**Cron freshness check.** Each cron run queries the GitHub Actions API for when all five pode workflows last ran. If none has run within 10 minutes — twice the expected 5-minute interval — `cron_fresh` is set to false and `ok` turns false. GitHub Actions cron jobs can be delayed during high load; this makes any such delay visible automatically without requiring users to interpret timestamps.

**Deploy history as an audit trail.** Render retains the full deployment history for a service. Even if a malicious deploy were pushed and immediately reverted, it would remain visible in the history — there is no way to silently insert and remove a deployment. Combined with the fact that a Render deploy takes longer than one minute, any unauthorised code change will appear in at least one PoDe check before the deployment completes.

**Trust boundary:** this approach assumes Render is not actively colluding — i.e., that the Render API reports the actual running commit honestly. A colluding hosting provider could lie in the API response while running different code. Mitigating that threat requires either multiple independent hosting providers each monitoring the others, or hosting-provider-level cryptographic attestation (see [Vision](#vision) below).

---

## Checking deployment status

Before using Leima, you can verify the full trust chain in one place:

1. Open the [Actions tab](../../actions) in this repository
2. Check that **PoDe Code Review** is green on the latest commit — the code has been audited against `POLICY.md`
3. Check that the five **PoDe A–E** workflows show green on their most recent runs — the running code matches the audited source
4. Optionally fetch [`status.json`](../../raw/refs/heads/gh-pages/status.json) and compare the `monitor_files` hashes against your previous session — if any hash has changed, check what changed and why before submitting documents

If any workflow is red, either a policy violation was detected in the code or a deployment mismatch was found within the last minute. Do not submit sensitive documents until the checks recover.

---

## Real-world incidents

**PHP git server compromise (2021).** Attackers gained access to PHP's official git server and injected a backdoor directly into the source code. The commits appeared to come from known, trusted developers — everything looked normal. The attack was caught before a release was made, but had it reached production, millions of PHP-powered websites would have been running malicious code from an apparently legitimate source. PoDe-style monitoring would not have prevented the git compromise, but an immutable deployment log and independent runtime verification would have made the gap between "what was in git" and "what was actually running" immediately visible.

**Picreel and Alpaca Forms supply chain attack (2019).** Attackers compromised a web analytics service and several open source form libraries. The malicious code was quietly injected into JavaScript files served to over 4,600 websites. Those sites began leaking user data to an attacker-controlled server. Site owners did not know. Users did not know. The browser showed a perfectly normal page — HTTPS was green — but the runtime JavaScript had been replaced. This is the attack PoDe is designed to make visible: the running code had changed, but nothing in the user's environment reflected that.

Both incidents share the same structure: the trust signal users had (a familiar domain, a green padlock, a known developer's name on a commit) said nothing about what code was actually executing. PoDe adds the missing signal.

---

## Real-world incidents

These three attacks illustrate different points in the supply chain where code can be silently replaced — and where deployment transparency would have made the manipulation harder to hide.

**XZ Utils backdoor (2024).** An attacker spent years building trust in the open source community, gradually acquiring maintainer rights to XZ Utils, a compression library present in most Linux distributions. The backdoor was injected not into the visible source code but into the release process — the malicious code appeared in the distributed tarballs but not in the git repository in the same form. It was discovered almost by accident, through a performance anomaly. Had there been public build attestation, verifiable artifact provenance, and continuous runtime checks, the gap between "what the source said" and "what was actually distributed and running" would have been significantly harder to maintain silently.

**PHP git server compromise (2021).** Attackers gained access to PHP's official git server and injected a backdoor directly into the source code. The commits appeared to come from known, trusted developers — everything looked normal. The attack was caught before a release was made, but had it reached production, millions of PHP-powered websites would have been running malicious code from an apparently legitimate source. An immutable deployment log and independent runtime verification would have made the gap between "what was in git" and "what was actually running" immediately visible.

**Picreel and Alpaca Forms supply chain attack (2019).** Attackers compromised a web analytics service and several open source form libraries. The malicious code was quietly injected into JavaScript files served to over 4,600 websites. Those sites began leaking user data to an attacker-controlled server. Site owners did not know. Users did not know. The browser showed a perfectly normal page — HTTPS was green — but the runtime JavaScript had been replaced. This is the attack PoDe is most directly designed to make visible: the running code had changed, but nothing in the user's environment reflected that.

All three share the same structure: the trust signal users had — a familiar domain, a green padlock, a known developer's name on a commit — said nothing about what code was actually executing. PoDe adds the missing signal at the runtime end of the chain. Sigstore, SLSA, and reproducible builds address the earlier stages; together they cover the full path from source to running instance.

---

## Prior art and existing landscape

The problem PoDe addresses is recognised but underserved. Existing approaches fall into three categories:

**Too narrow.** Meta released [Code Verify](https://github.com/nicholasgasior/code-verify) (2022), a browser extension that checks WhatsApp Web, Facebook, and Instagram JavaScript against a Cloudflare-hosted reference copy. If the running code differs from the published version, the user is warned immediately. This is essentially the browser extension part of the PoDe vision — but built only for Meta's own services, with Cloudflare as the trusted third party. No general version exists that any project could adopt.

**Too heavy.** Academic and industrial research has gone in a hardware direction. HTTPA extends HTTPS with remote attestation using Intel SGX enclaves, allowing clients to verify that a server is running exactly the published code at the hardware level. Signal uses SGX for contact discovery. This is the strongest possible guarantee — but it requires Intel SGX support, re-architecting code into enclaves, and hosting provider cooperation. It is not a realistic option for small open source projects.

**Wrong layer.** Sigstore, SLSA, and in-toto are supply chain standards that secure the path from source code to build artifact. They answer: "was this binary built from this source?" PoDe answers the next question: "is this binary what is actually running?" The two are complementary — Sigstore covers source → artifact, PoDe covers artifact → running instance.

**In standardisation.** The W3C Web Application Security Working Group has discussed [Source Code Transparency](https://github.com/nicholasgasior/source-code-transparency) — a proposal to publish web app bundle hashes to a Certificate Transparency-style log, requiring browsers to verify the running code is in the log before executing it. The problem is recognised, the process is active, but nothing is in production.

**An underserved gap.** Most proposals focus on client-side JavaScript — the code the browser downloads and runs. PoDe focuses on server-side code — the code that runs on the hosting provider and processes user data. For AI services, server-side code is the only relevant surface: models cannot process encrypted data, so there is no E2E architecture to fall back on. Trust rests entirely on what the server code does. This remains an underrepresented problem space.

PoDe's differentiator is that it works with existing building blocks — a hosting provider API, GitHub API, GitHub Actions, and a cron schedule. No browser changes, no hardware enclaves, no new standardisation processes, no partnership agreements. Any open source project can adopt it over a weekend. The guarantee is weaker than SGX attestation, but meaningfully stronger than "trust us because we're open source" — and it is deployable today.

---

## Vision

The current implementation is a practical first step. The logical end state is a fully automated trust chain that requires no manual verification from users.

**Independent commit auditing.** When a new commit is pushed to the repository, an independent service — operated by a party unrelated to Leima — automatically audits the new code. The audit checks that the new commit does not introduce data exfiltration, does not change the AI prompts in ways that would alter verdicts, and does not connect to unauthorised external services. Results are published publicly before the commit is deployed.

The current implementation (`code_review.py`) is a working example of this idea rather than the end state. A single AI model checking its own host application's code has obvious limitations — the model may have blind spots, and the check runs on the same infrastructure it is auditing. The stronger form involves multiple independent AI models reviewing each commit simultaneously, an external service operated by a party with no relationship to the application, and optionally human reviewers for significant changes. Consensus across independent reviewers is harder to manipulate than a single automated check.

**Visible in the application UI.** The current deployment status and the last audit result are shown directly in the application — not just on GitHub. Users do not need to open a separate page. A mismatch or a failed audit blocks the UI until resolved.

**Userscript (available now).** A Tampermonkey/Greasemonkey userscript ([`pode.user.js`](pode.user.js)) is included in the repository. It uses `GM_xmlhttpRequest` — which runs in the browser extension's isolated context, not the page's JavaScript environment — so a compromised Leima page cannot intercept or spoof the check. On each page load it fetches `status.json`, shows a green banner if everything is in order, and a red warning if not. It also compares `monitor_files` hashes against the previous session using `GM_getValue`/`GM_setValue`, alerting if any monitoring file has changed.

**Browser extension.** A dedicated browser extension would make the same check fully automatic for any PoDe-enabled application without requiring manual userscript installation. No manual check required.

**Hosting platform attestation.** The cleanest solution is for hosting providers to publish cryptographically signed deployment records: *"we certify that service X is running commit Y, signed with our public key."* This would make third-party monitoring unnecessary — the platform itself provides the proof, and any client can verify it. Until hosting platforms offer this natively, external monitoring is the practical alternative.

**Versioned user consent.** When a user first uses an application, they accept what it may do with their data — but that acceptance is tied to a specific, audited version of the code. When a new commit is deployed and passes the audit, the auditor checks whether the new code does anything materially different from what the user already accepted: new data destinations, changed retention behaviour, altered AI prompts, new third-party integrations. If the change is within what was previously accepted, the user is not interrupted. If it falls outside, the user is notified and asked to re-consent before continuing. The terms do not change silently between sessions — the code does not change silently between sessions.

**Standardisation.** PoDe could become a badge and a protocol that any hosted open source project can adopt — analogous to how HTTPS became a baseline expectation. A project that exposes a verifiable deployment status makes a stronger trust claim than one that only publishes source code.

The underlying principle is the same throughout: trust is not granted to a company or a person. It is granted to a specific, verified version of code — and automatically re-evaluated whenever the code changes.
