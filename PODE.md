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

Each workflow runs `pode_check.py`, which:

1. Calls the Render API: *"which commit is currently live on this service?"*
2. Calls the GitHub API: *"what is the latest commit on the main branch?"*
3. Compares them
4. Writes the result to `status.json` on the `gh-pages` branch

The check passes if the deployed commit matches the GitHub HEAD. If a deploy is in progress, or if an unauthorised deployment has occurred, the check fails and the GitHub Actions badge turns red.

**The result is public and independently verifiable.** Anyone can visit the [Actions tab](../../actions) to see the continuous check history, or fetch `status.json` directly. The checks run on GitHub's infrastructure — not Render's — so they cannot be influenced by a compromise of the hosting environment.

**Trust boundary:** this approach assumes Render is not actively colluding — i.e., that the Render API reports the actual running commit honestly. A colluding hosting provider could lie in the API response while running different code. Mitigating that threat requires either multiple independent hosting providers each monitoring the others, or hosting-provider-level cryptographic attestation (see [Vision](#vision) below).

---

## Checking deployment status

Before using Leima, you can verify that the running code matches the published source:

1. Open the [Actions tab](../../actions) in this repository
2. Check that the five PoDe workflows show green on their most recent runs
3. Note the timestamp of the last successful check

If any workflow is red, a deployment mismatch was detected within the last minute. Do not submit sensitive documents until the checks recover.

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
