## main.py

- line 57 — `_imap_server` falls back to `f"imap.{domain}"` for unknown email domains. A malicious or mistyped address (e.g. `user@internal-host`) routes an IMAP connection to an arbitrary internal host. There is no private-IP guard here unlike in `_fetch_webpage`/`_fetch_pdf_from_url`.
- line 174–178 — SSRF guard in `_fetch_webpage` only works for raw IP addresses in the URL. `ipaddress.ip_address(parsed.hostname)` raises `ValueError` for any hostname, and the `except` branch only re-raises on specific message strings. Hostnames that resolve to private IPs at connection time (e.g. a DNS name pointing to `169.254.169.254`) pass through silently. The same pattern repeats in `_fetch_pdf_from_url` (lines 526–533).
- line 255 — The IMAP exception is returned verbatim to the browser: `f'Connection failed: {e}'`. This can leak internal hostnames, credential-rejection details, or other server-side information to the client.
- line 260 — `session_id = str(uuid.uuid4())[:12]` truncates to 12 hex characters (48 bits). Using the full UUID hex (`uuid.uuid4().hex`) eliminates unnecessary collision risk at no cost.
- line 437 — Arweave manifest comparison in `/validate` strips the key `"arweave"`, but the code stores the stamp under `"stamp"` (line 350). The `"stamp"` key remains in `base_manifest`, so the equality check will always fail for manifests produced by the current code. The strip should target `"stamp"`.
- line 487–506 — `build_verdict_html_export` interpolates user-supplied `question`, `timestamp`, and `input_hash` directly into an HTML string without HTML-escaping. A claim containing `<script>` or `"` produces malformed or executable HTML in the downloaded file.
- line 536–537 — The HEAD-response `Content-Length` is trusted to enforce the 10 MB cap, but a server can omit or misreport it. The streaming loop (lines 548–553) does enforce the real limit, so the HEAD check is redundant but could give false confidence if the logic is ever refactored.
- line 584 — Same 12-character UUID truncation as line 260 in `_run_analysis`.
- line 703 — Only `ValueError` from `_run_analysis` is caught in `/ask`. Any other exception from Gemini (network error, SDK exception, etc.) propagates as an unhandled 500 with a raw traceback. Should be caught more broadly, or Gemini calls should translate errors into a typed exception.
- line 736 — No size limit on the `pdf_base64` payload in `/api/stamp`. A client can send arbitrarily large base64-encoded data; there is no cap equivalent to the `PDF_URL_MAX_BYTES` check used for URL-sourced PDFs.

## neutral_witness.py

- line 130 — `scope_resp.text` is accessed without a None-guard. The Gemini SDK returns `None` for `.text` when the response is blocked by safety filters (finish reason `SAFETY`/`RECITATION`). Calling `.strip()` on `None` raises `AttributeError`. The same issue exists at lines 141 and 149.
- line 155 — Fallback verdict extraction `synth_text.split(".")[0].strip() + "."` silently truncates the verdict if the model does not follow the expected format. No warning is logged.

## pode_check.py

- line 32 — `GITHUB_REPO` hard-codes `"fxg55647/leima"` as the default. If the environment variable is unset in a fork or new deployment, all GitHub API calls silently query the wrong repository, producing misleading status results.
- lines 57–65 — `github_commit()` makes an unauthenticated GitHub API request. `GITHUB_TOKEN` is read but only used in `check_deploy_history`, not here or in `check_cron_freshness`. Under CI or shared NAT the unauthenticated 60 req/hour limit causes spurious failures.
- line 192 — `deployment_ok` compares only the first 7 characters of the commit SHA (`deployed.startswith(expected[:7])`). Two distinct commits sharing a 7-char prefix would be considered matching. Using at least 12 characters is more robust.

## code_review.py

- line 83 — No early check that `GEMINI_API_KEY` is non-empty. When the env var is absent the script crashes with an unhelpful SDK auth error rather than a clear configuration message.
- line 80 — `POLICY.md` is read without error handling. If the file is missing or renamed, the script raises an unhandled `FileNotFoundError` in CI rather than a readable error message.

## pode.user.js

- line 39 — `JSON.parse(stored)` is called without a try/catch. If the GM storage value is corrupted, this throws and the `changed` variable is never set, causing a silent failure in the banner display logic.
- line 13 — `STATUS_URL` points to a GitHub Pages URL with no integrity check on the fetched JSON. If the repository or Pages site is compromised, an attacker can display arbitrary status messages (e.g. a false "verified" banner) to every userscript user.
