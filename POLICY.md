# Leima Data Policy

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

**Google Gemini API.** Your document and claim are sent to Google's Gemini API (`gemini-2.5-flash-lite`) for analysis. This is the only external service that receives the content of your document. Google's standard API terms apply to this transmission. If your document contains sensitive personal data, consider anonymising it before submission.

**Nowhere else.** The document is not sent to any other external service, not written to disk, and not retained after your session ends.

---

## What is stored permanently

Only the following is written to the Arweave blockchain, via Irys:

- SHA-256 hash of your document
- SHA-256 hash of the verdict PDF
- Timestamp
- AI model version
- Claim text

The document itself, the verdict text, and any personal data in either are **not** stored on Arweave or anywhere else permanently. The stamp record on Arweave contains fingerprints, not content.

---

## Session handling

Results are held in server memory for the duration of your session — long enough for you to download your files. No database is used. When the server restarts, all session data is gone. Leima has no user accounts and does not track individuals across sessions.

---

## Email input

If you use the email (IMAP) input:
- Your IMAP credentials are used to fetch the selected message and are not stored
- The email content is processed the same way as any other document: sent to Google Gemini, hashed, then discarded
- DKIM validation is performed locally; the result is recorded in the manifest

---

## What the AI is instructed to do

The full AI prompt logic is in `neutral_witness.py`. The model is instructed to:
- Analyse the document against the claim in three independent passes
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

Five automated checks run every minute and verify that the code running on the server matches this published source. Results are public at the [Actions tab](../../actions). If a deployment mismatch is detected, the checks turn red. See [PODE.md](PODE.md) for details.

---

## What an auditor checks when code changes

When a new version of Leima is deployed, an automated auditor compares the new code against this policy and flags any change that would:

- Send document content to a new or different external service
- Write document content or claim text to persistent storage
- Add tracking, analytics, or cross-session identification
- Change what the AI model is instructed to do with your data
- Alter the Arweave stamp record to include more than hashes and metadata

Changes that do not affect any of the above — bug fixes, UI changes, new document sources that follow the same data flow — do not require re-consent.
