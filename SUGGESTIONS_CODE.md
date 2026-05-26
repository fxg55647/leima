## main.py

- line 437 — Arweave manifest comparison in `/validate` strips the key `"arweave"`, but the code stores the stamp under `"stamp"` (line 350). The `"stamp"` key remains in `base_manifest`, so the equality check will always fail for manifests produced by the current code. The strip should target `"stamp"`.
- line 487–506 — `build_verdict_html_export` interpolates user-supplied `question`, `timestamp`, and `input_hash` directly into an HTML string without HTML-escaping. A claim containing `<script>` or `"` produces malformed or executable HTML in the downloaded file.
- line 260 — `session_id = str(uuid.uuid4())[:12]` truncates to 12 hex characters (48 bits). Using the full UUID hex (`uuid.uuid4().hex`) eliminates unnecessary collision risk at no cost. Same issue at line 584.
- line 255 — The IMAP exception is returned verbatim to the browser: `f'Connection failed: {e}'`. This can leak internal hostnames, credential-rejection details, or other server-side information to the client.
- line 437 — IMAP SEARCH injection: escaping of email sender input is insufficient. IMAP protocol has syntax elements beyond backslashes and quotes. Safer to whitelist allowed characters.
- line 703 — Only `ValueError` from `_run_analysis` is caught in `/ask`. Any other exception from Gemini (network error, SDK exception, etc.) propagates as an unhandled 500 with a raw traceback.
- line 736 — No size limit on the `pdf_base64` payload in `/api/stamp`. A client can send arbitrarily large base64-encoded data; no cap equivalent to `PDF_URL_MAX_BYTES`.
- line 57 — `_imap_server` falls back to `f"imap.{domain}"` for unknown email domains. A malicious address (e.g. `user@internal-host`) routes an IMAP connection to an arbitrary internal host. No private-IP guard here.

## neutral_witness.py

- line 130 — `scope_resp.text` is accessed without a None-guard. The Gemini SDK returns `None` for `.text` when the response is blocked by safety filters. Calling `.strip()` on `None` raises `AttributeError`. Same issue at lines 141 and 149.
- line 155 — Fallback verdict extraction `synth_text.split(".")[0].strip() + "."` silently truncates the verdict if the model does not follow the expected format.

## poide_check.py

- line 32 — `GITHUB_REPO` hard-codes `"fxg55647/leima"` as default. If the env var is unset in a fork or new deployment, all GitHub API calls silently query the wrong repository.
- lines 57–65 — `github_commit()` makes an unauthenticated GitHub API request. Under CI or shared NAT the unauthenticated 60 req/hour limit causes spurious failures.
- line 192 — `deployment_ok` compares only the first 7 characters of the commit SHA. Two distinct commits sharing a 7-char prefix would be considered matching. At least 12 characters is more robust.

## code_review.py

- line 83 — No early check that `GEMINI_API_KEY` is non-empty. When the env var is absent the script crashes with an unhelpful SDK auth error.
- line 80 — `POLICY.example.md` is read without error handling. If the file is missing, the script raises an unhandled `FileNotFoundError` in CI.

## pode.user.js

- line 39 — `JSON.parse(stored)` is called without a try/catch. If the GM storage value is corrupted, this throws and the `changed` variable is never set.
- line 13 — `STATUS_URL` points to a GitHub Pages URL with no integrity check on the fetched JSON. A compromised Pages site can display arbitrary status messages to every userscript user.
