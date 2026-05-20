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

**Deploy history as an audit trail.** Render retains the full deployment history for a service. Even if a malicious deploy were pushed and immediately reverted, it would remain visible in the history — there is no way to silently insert and remove a deployment. Combined with the fact that a Render deploy takes longer than one minute, any unauthorised code change will appear in at least one PoDe check before the deployment completes.

**Trust boundary:** this approach assumes Render is not actively colluding — i.e., that the Render API reports the actual running commit honestly. A colluding hosting provider could lie in the API response while running different code. Mitigating that threat requires either multiple independent hosting providers each monitoring the others, or hosting-provider-level cryptographic attestation (see [Vision](#vision) below).

---

## Checking deployment status

Before using Leima, you can verify the full trust chain in one place:

1. Open the [Actions tab](../../actions) in this repository
2. Check that **PoDe Code Review** is green on the latest commit — the code has been audited against `POLICY.md`
3. Check that the five **PoDe A–E** workflows show green on their most recent runs — the running code matches the audited source

If any workflow is red, either a policy violation was detected in the code or a deployment mismatch was found within the last minute. Do not submit sensitive documents until the checks recover.

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

**Visible in the application UI.** The current deployment status and the last audit result are shown directly in the application — not just on GitHub. Users do not need to open a separate page. A mismatch or a failed audit blocks the UI until resolved.

**Browser extension.** A browser extension checks PoDe status automatically when the user navigates to any participating application. If the running code does not match the audited source, the extension warns the user before they interact. No manual check required.

**Hosting platform attestation.** The cleanest solution is for hosting providers to publish cryptographically signed deployment records: *"we certify that service X is running commit Y, signed with our public key."* This would make third-party monitoring unnecessary — the platform itself provides the proof, and any client can verify it. Until hosting platforms offer this natively, external monitoring is the practical alternative.

**Versioned user consent.** When a user first uses an application, they accept what it may do with their data — but that acceptance is tied to a specific, audited version of the code. When a new commit is deployed and passes the audit, the auditor checks whether the new code does anything materially different from what the user already accepted: new data destinations, changed retention behaviour, altered AI prompts, new third-party integrations. If the change is within what was previously accepted, the user is not interrupted. If it falls outside, the user is notified and asked to re-consent before continuing. The terms do not change silently between sessions — the code does not change silently between sessions.

**Standardisation.** PoDe could become a badge and a protocol that any hosted open source project can adopt — analogous to how HTTPS became a baseline expectation. A project that exposes a verifiable deployment status makes a stronger trust claim than one that only publishes source code.

The underlying principle is the same throughout: trust is not granted to a company or a person. It is granted to a specific, verified version of code — and automatically re-evaluated whenever the code changes.
