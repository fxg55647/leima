# Leima Data Policy

> **Canonical version:** The binding copy of this policy — the one the production code review audits against — is permanently stored on Arweave at [`6Fviz2M3kx6BTkkn2fHrdJ7qtX9hRxV476f31WvUDqvR`](https://gateway.irys.xyz/6Fviz2M3kx6BTkkn2fHrdJ7qtX9hRxV476f31WvUDqvR). The repository version below is kept for human readability and as a model example for other projects adopting POIDE. The Arweave version is what binds.

This document describes exactly what Leima does with the data you submit. It is written to be verifiable: each claim here can be checked against the source code by anyone, including an automated auditor.

This policy is tied to a specific version of the code. If a future deployment changes any of the behaviours described here, you will be notified before continuing to use the application.

---

## What you submit

When you use Leima, you submit:
- A document (PDF, image, text, web page URL, or email)
- A claim you want evaluated against that document

Neither is stored permanently by Leima.

---

## Where your document goes

**Google Gemini API.** Your document and claim are sent to Google's Gemini API (`gemini-3.1-flash-lite`) for analysis. This is the only external service that receives the content of your document. Google's standard API terms apply to this transmission. If your document contains sensitive personal data, consider anonymising it before submission.

**GitHub API (GitHub tab only).** If you use the GitHub tab, Leima fetches the file contents you specify from the GitHub API (`api.github.com`) using the repository, commit reference, and file paths you provide. Your optional GitHub token is passed directly to the API as a Bearer credential and is never stored. The fetched file contents are then sent to Gemini for analysis in the same way as any other document.

**Nowhere else.** Outside of the above, your document is not sent to any other external service, not written to disk, and not retained after your session ends.

---

## What is stored permanently

Only the following is written to the Arweave blockchain, via Irys:

- SHA-256 hash of your document
- SHA-256 hash of the verdict PDF
- Timestamp
- AI model version
- Input label: the MIME type of the document (e.g. `application/pdf`, `image/jpeg`) for uploaded files, or the source URL for web and PDF URL submissions — original filenames are never stored
- For web-sourced documents: the URL and the time it was fetched
- For email submissions: sender address, subject, date, and DKIM result (see Email notary section)

The document content, the verdict text, and any personal data in either are **not** stored on Arweave permanently. The stamp record contains fingerprints and provenance metadata — not content.

---

## Session handling

Results are held in server memory for one hour from the time of submission, regardless of browser activity. No database is used. When the server restarts, all session data is gone. Leima has no user accounts and does not track individuals across sessions.

---

## Email input (IMAP analysis)

If you use the email (IMAP) input:
- Your IMAP credentials are used to fetch the selected message and are not stored
- The email content is processed the same way as any other document: sent to Google Gemini, hashed, then discarded
- DKIM validation is performed locally; the result is recorded in the manifest

## Email notary

The email notary is a separate flow. When a sender adds `BCC: stamp@leima.fi` to an outgoing email, Leima receives the message via IMAP and:

1. Verifies the DKIM signature locally
2. Computes a SHA-256 hash of the full raw email
3. Writes a manifest containing only metadata and hashes to Arweave/Irys
4. Sends a notarized copy of the email back to the `To:` and `CC:` recipients (and optionally the sender if CC'd) via SMTP — the notarized copy contains the original email as an `.eml` attachment, the manifest as a `.json` attachment, and a verification link

**External services used by this flow:** IMAP server (receiving), SMTP server (sending notarized copy), Arweave/Irys (permanent hash storage). No email content is sent to Google Gemini or any other AI service in this flow.

The following is written to the Arweave blockchain **permanently**:

- Sender address (`From:`)
- Recipient address (`To:`)
- Subject line
- Date header
- Message-ID
- DKIM validation result
- SHA-256 hash of the full email (including attachments)

This is more than fingerprints — it includes the sender and recipient addresses and subject line as plain text, permanently on a public blockchain. Do not use the notary flow for emails containing information you do not want publicly associated with the sender and recipient addresses.

---

## What the AI is instructed to do

The full AI prompt logic is in `neutral_witness.py`. Before any analysis, a scope-check pass evaluates whether the request falls within permitted use. If rejected, no further AI calls are made and no stamp is created. If approved, the model is instructed to:
- Analyse the document against the claim in two independent passes (one identifying supporting evidence, one identifying contradicting evidence), followed by a synthesis pass that weighs the two
- Refuse requests intended for surveillance, stalking, or harassment
- Respond in the language of the claim

The model is not instructed to retain, summarise, or report your data for any other purpose.

---

## What Leima does not do

- Does not sell, share, or transmit your document to any party other than Google Gemini
- Does not log document content or claim text to any persistent storage
- Does not use your data to train models (this is subject to Google's API terms, not Leima's control)
- Does not set tracking cookies or use analytics
- Does not require an account or link submissions to an identity

---

## Deployment integrity

Five automated checks run every minute and verify that the code running on the server matches this published source. Results are public at the [Actions tab](../../actions). If a deployment mismatch is detected, the checks turn red. See [POIDE.md](POIDE.md) for details.

The server makes background HTTP calls to the GitHub API and GitHub Pages CDN to fetch deployment verification status. These calls contain no user data — they fetch only the POIDE status log used to display the integrity indicator in the UI.

---

## What an auditor checks when code changes

When a new version of Leima is deployed, an automated auditor compares the new code against this policy and flags any change that would:

- Send document content to a new or different external service
- Write document content or claim text to persistent storage
- Add tracking, analytics, or cross-session identification
- Change what the AI model is instructed to do with your data
- Alter the Arweave stamp record to include more than hashes and metadata

Changes that do not affect any of the above — bug fixes, UI changes, new document sources that follow the same data flow — do not require re-consent.
