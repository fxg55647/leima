import os
import base64
import hashlib
import uuid
import json
import time
import threading
import imaplib
import socket
import dkim
import ipaddress
import email as email_lib
from email.header import decode_header as _decode_header
from datetime import datetime, timedelta
from urllib.parse import urlparse
from dotenv import load_dotenv
import re
from html import escape as _html_escape
import markdown as _md
import bleach
import requests as http_requests
from fastapi import FastAPI, File, Form, UploadFile, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from google.genai import types
from neutral_witness import analyse, analyse_code_review, PASS_LABELS, MODEL
from notary import poll_and_process as _notary_poll
from fpdf import FPDF
from irys_sdk import Builder
from irys_sdk.bundle.tags import from_dict as tags_from_dict

load_dotenv()

IRYS_PRIVATE_KEY = os.getenv("IRYS_PRIVATE_KEY")
IRYS_NETWORK = os.getenv("IRYS_NETWORK", "mainnet")
IRYS_RPC_URL = os.getenv("IRYS_RPC_URL")
IRYS_GATEWAY = "https://devnet.irys.xyz" if IRYS_NETWORK == "devnet" else "https://gateway.irys.xyz"

NOTARY_IMAP_HOST = os.getenv("NOTARY_IMAP_HOST", "imap.gmail.com")
NOTARY_IMAP_USER = os.getenv("NOTARY_IMAP_USER")
NOTARY_IMAP_PASSWORD = os.getenv("NOTARY_IMAP_PASSWORD")
NOTARY_SMTP_HOST = os.getenv("NOTARY_SMTP_HOST", "smtp.gmail.com")
NOTARY_SMTP_PORT = int(os.getenv("NOTARY_SMTP_PORT", "587"))
NOTARY_SMTP_USER = os.getenv("NOTARY_SMTP_USER")
NOTARY_SMTP_PASSWORD = os.getenv("NOTARY_SMTP_PASSWORD")
NOTARY_FROM = os.getenv("NOTARY_FROM", "Leima <noreply@leima.io>")
NOTARY_POLL_TOKEN = os.getenv("NOTARY_POLL_TOKEN")
LEIMA_URL = os.getenv("LEIMA_URL", "https://leima.io")

_poide_cache: dict | None = None
_poide_cache_ready = threading.Event()
_PAGES_URL = "https://fxg55647.github.io/leima"

def _poide_dispatcher():
    global _poide_cache
    token = os.getenv("GITHUB_DISPATCH_TOKEN", "")
    dispatch_url = "https://api.github.com/repos/fxg55647/leima/actions/workflows/poide-a.yml/dispatches"
    api_log_url = "https://api.github.com/repos/fxg55647/leima/contents/status-log.jsonl?ref=gh-pages"
    cdn_log_url = "https://fxg55647.github.io/leima/status-log.jsonl"
    api_hdrs = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    cache_populated = False
    while True:
        try:
            if token:
                r = http_requests.get(api_log_url, headers=api_hdrs, timeout=10)
                if r.status_code == 200:
                    content = base64.b64decode(r.json()["content"]).decode()
                    lines = [l for l in content.strip().splitlines() if l]
                    if lines:
                        _poide_cache = json.loads(lines[-1])
                        _poide_cache_ready.set()
                        cache_populated = True
            else:
                r = http_requests.get(cdn_log_url, timeout=10)
                if r.status_code == 200:
                    lines = [l for l in r.text.strip().splitlines() if l]
                    if lines:
                        _poide_cache = json.loads(lines[-1])
                        _poide_cache_ready.set()
                        cache_populated = True
        except Exception:
            pass
        if token:
            try:
                http_requests.post(dispatch_url, headers=api_hdrs, json={"ref": "main"}, timeout=10)
            except Exception:
                pass
        time.sleep(30 if cache_populated else 5)

threading.Thread(target=_poide_dispatcher, daemon=True).start()

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
_MD_ALLOWED_TAGS = ["p", "strong", "em", "ul", "ol", "li", "blockquote", "code", "pre", "br", "h1", "h2", "h3"]
templates.env.filters["md"] = lambda text: bleach.clean(
    _md.markdown(text or "", extensions=["nl2br"]),
    tags=_MD_ALLOWED_TAGS, strip=True
)

# In-memory store: session_id → {pdf: bytes, manifest: dict}
store: dict[str, dict] = {}
# Email sessions: session_id → list of email dicts
email_sessions: dict[str, list[dict]] = {}

SESSION_TTL = 3600  # seconds

def _evict_old_sessions() -> None:
    cutoff = time.time() - SESSION_TTL
    for d in (store, email_sessions):
        stale = [k for k, v in d.items() if v.get("_stored_at", 0) < cutoff]
        for k in stale:
            d.pop(k, None)


def _session_eviction_loop() -> None:
    while True:
        time.sleep(300)
        _evict_old_sessions()

threading.Thread(target=_session_eviction_loop, daemon=True).start()


def _imap_server(user_email: str) -> str:
    domain = user_email.split("@")[-1].lower()
    known = {
        "gmail.com": "imap.gmail.com",
        "googlemail.com": "imap.gmail.com",
        "outlook.com": "imap-mail.outlook.com",
        "hotmail.com": "imap-mail.outlook.com",
        "live.com": "imap-mail.outlook.com",
        "yahoo.com": "imap.mail.yahoo.com",
    }
    host = known.get(domain, f"imap.{domain}")
    if domain not in known:
        try:
            _check_ssrf(f"https://{host}/")
        except ValueError as e:
            raise ValueError(f"IMAP host not allowed: {e}") from None
    return host


def _decode_header_value(value) -> str:
    if not value:
        return ""
    parts = _decode_header(value)
    result = []
    for part, enc in parts:
        if isinstance(part, bytes):
            result.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            result.append(part)
    return " ".join(result)


def _get_body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition", "")):
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
    payload = msg.get_payload(decode=True)
    if payload:
        charset = msg.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")
    return ""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


_UNICODE_MAP = str.maketrans({
    "—": "-", "–": "-",
    "‘": "'", "’": "'",
    "“": '"', "”": '"',
    "…": "...",
    "·": "*", "•": "*",
})

def _safe(text: str) -> str:
    text = text.translate(_UNICODE_MAP)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _source_assessment_text(source_context: dict | None) -> str:
    if not source_context:
        return "Content analysis mode — source credibility not assessed."
    t = source_context.get("type", "content_only")
    if t == "content_only":
        return "Content analysis mode — source credibility not assessed."
    if t == "email":
        parts = ["Email (IMAP)", f"DKIM: {source_context.get('dkim', 'none')}"]
        if source_context.get("sender_domain"):
            parts.append(f"Sender domain: {source_context['sender_domain']}")
        return " — ".join(parts)
    elif t == "image_c2pa_valid":
        s = "Image — C2PA: valid — Origin cryptographically established"
        if source_context.get("c2pa_generator"):
            s += f" — Generator: {source_context['c2pa_generator']}"
        return s
    elif t == "image_c2pa_invalid":
        return "Image — C2PA: INVALID — Modified after capture. Content assessed against claim only."
    elif t == "image_no_c2pa":
        return "Image — No C2PA provenance. Content assessed against claim only."
    elif t == "web":
        parts = [f"Web page — Domain: {source_context.get('domain', 'unknown')}"]
        if source_context.get("fetched_at"):
            parts.append(f"Fetched: {source_context['fetched_at']}")
        return " — ".join(parts)
    elif t == "pdf_url":
        parts = [f"PDF from URL — Domain: {source_context.get('domain', 'unknown')}"]
        if source_context.get("fetched_at"):
            parts.append(f"Fetched: {source_context['fetched_at']}")
        return " — ".join(parts)
    elif t == "pdf_signed":
        signer = source_context.get("sig_signer") or source_context.get("sig_signer_org") or "unknown"
        ts = source_context.get("sig_timestamp", "")
        rfc = " — RFC 3161 timestamp" if source_context.get("sig_rfc3161") else " — claimed time"
        tsa = f" via {source_context['sig_tsa']}" if source_context.get("sig_tsa") else ""
        return f"PDF — Digital signature detected — Signer: {signer} — Signed: {ts}{rfc}{tsa}"
    elif t == "pdf_unsigned":
        return "PDF — No digital signature detected"
    else:
        return "Document (uploaded) — No verifiable origin. Content assessed against claim only."


def build_verdict_pdf(question: str, passes: list[tuple[str, str]], timestamp: str, input_hash: str, prompts: list[tuple[str, str]] | None = None, source_context: dict | None = None) -> bytes:
    pdf = FPDF()
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, _safe("Leima - verdict"), ln=True)
    pdf.ln(2)

    pdf.set_font("Helvetica", size=9)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 6, f"Timestamp: {timestamp}", ln=True)
    pdf.cell(0, 6, f"Model: {MODEL}", ln=True)
    pdf.cell(0, 6, _safe(f"Commit: {os.getenv('RENDER_GIT_COMMIT', 'unknown')}"), ln=True)
    pdf.cell(0, 6, _safe(f"Input hash (SHA-256): {input_hash}"), ln=True)
    pdf.cell(0, 6, _safe(f"Source: {_source_assessment_text(source_context)}"), ln=True)
    pdf.ln(4)

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Claim:", ln=True)
    pdf.set_font("Helvetica", size=11)
    pdf.multi_cell(0, 6, _safe(question))

    for label, text in passes:
        pdf.ln(6)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, _safe(label), ln=True)
        pdf.set_font("Helvetica", size=11)
        html = _md.markdown(_safe(text or ""), extensions=["nl2br"])
        pdf.write_html(html)

    pdf.ln(10)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 6, "Note", ln=True)
    pdf.set_font("Helvetica", size=9)
    pdf.multi_cell(0, 5, _safe(
        "A prompt injection attack — text deliberately embedded in a document to manipulate AI behaviour — "
        "can alter the analysis produced by this tool. Such content is typically found in dubious websites "
        "and suspicious emails; it is rare in official sources. Use your own judgement when evaluating this verdict."
    ))
    pdf.set_text_color(0, 0, 0)

    return bytes(pdf.output())


def build_manifest(
    timestamp: str,
    model: str,
    input_label: str,
    input_hash: str,
    verdict_hash: str,

    email_meta: dict | None = None,
    web_meta: dict | None = None,
) -> dict:
    manifest = {
        "version": "1",
        "timestamp": timestamp,
        "model": model,
        "commit": os.getenv("RENDER_GIT_COMMIT", "unknown"),

        "input": {"label": input_label, "sha256": input_hash},
        "verdict_pdf": {"sha256": verdict_hash},
    }
    if email_meta:
        manifest["email_meta"] = email_meta
    if web_meta:
        manifest["web"] = web_meta
    return manifest


_CR_SKIP_DIRS = {".venv", "__pycache__", ".git", "node_modules", ".github", "hooks"}
_CR_SOURCE_EXT = {".py", ".js"}


def _github_fetch_tree(repo: str, commit_sha: str, token: str = "") -> list[dict]:
    """Fetch all source and doc files from the repo tree at commit_sha."""
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    commit_r = http_requests.get(
        f"https://api.github.com/repos/{repo}/commits/{commit_sha}",
        headers=headers, timeout=10,
    )
    commit_r.raise_for_status()
    tree_sha = commit_r.json()["commit"]["tree"]["sha"]
    tree_r = http_requests.get(
        f"https://api.github.com/repos/{repo}/git/trees/{tree_sha}?recursive=1",
        headers=headers, timeout=15,
    )
    tree_r.raise_for_status()
    from pathlib import Path as _P
    paths = [
        item["path"] for item in tree_r.json().get("tree", [])
        if item["type"] == "blob"
        and _P(item["path"]).suffix in _CR_SOURCE_EXT
        and not any(part in _CR_SKIP_DIRS for part in _P(item["path"]).parts)
        and item.get("size", 0) <= 500_000
    ]
    return _github_fetch_files(repo, commit_sha, paths, token)


def _github_resolve_commit(repo: str, ref: str, token: str = "") -> str:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = http_requests.get(
        f"https://api.github.com/repos/{repo}/commits/{ref}",
        headers=headers, timeout=10,
    )
    if r.status_code == 404:
        raise ValueError(f"Repository or ref not found: {repo}@{ref}")
    if r.status_code == 401:
        raise ValueError("Invalid or missing GitHub token for private repository")
    r.raise_for_status()
    return r.json()["sha"]


def _github_fetch_files(repo: str, commit_sha: str, paths: list[str], token: str = "") -> list[dict]:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    results = []
    for path in paths:
        r = http_requests.get(
            f"https://api.github.com/repos/{repo}/contents/{path}?ref={commit_sha}",
            headers=headers, timeout=10,
        )
        if r.status_code == 404:
            raise ValueError(f"File not found in commit: {path}")
        r.raise_for_status()
        data = r.json()
        if data.get("type") != "file":
            raise ValueError(f"Path is not a file: {path}")
        if data.get("size", 0) > 500_000:
            raise ValueError(f"File too large (max 500 kB): {path}")
        content = base64.b64decode(data["content"])
        blob = b"blob " + str(len(content)).encode() + b"\0" + content
        computed_sha = hashlib.sha1(blob).hexdigest()
        verified = computed_sha == data["sha"]
        results.append({
            "path": path,
            "content": content.decode("utf-8", errors="replace"),
            "blob_sha": data["sha"],
            "verified": verified,
        })
    return results


def _check_ssrf(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http/https URLs are allowed")
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise ValueError("No hostname in URL")
    if host in ("localhost", "0.0.0.0"):
        raise ValueError("Private/internal addresses are not allowed")
    try:
        addr = ipaddress.ip_address(host)
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            raise ValueError("Private/internal addresses are not allowed")
        return
    except ValueError as e:
        if "Private" in str(e) or "internal" in str(e) or "loopback" in str(e) or "reserved" in str(e):
            raise
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        raise ValueError(f"Cannot resolve hostname: {host}")
    for info in infos:
        ip_str = info[4][0]
        addr = ipaddress.ip_address(ip_str)
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            raise ValueError(f"URL resolves to private/internal address: {ip_str}")


def _safe_get(url: str, **kwargs) -> http_requests.Response:
    max_redirects = 10
    for _ in range(max_redirects):
        resp = http_requests.get(url, allow_redirects=False, **kwargs)
        if resp.is_redirect or resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("Location", "")
            if not location:
                break
            url = http_requests.compat.urljoin(url, location)
            _check_ssrf(url)
        else:
            return resp
    raise ValueError("Too many redirects or redirect loop")


def _fetch_webpage(url: str) -> tuple[bytes, str, str, str]:
    _check_ssrf(url)
    parsed = urlparse(url)
    resp = _safe_get(url, timeout=20, headers={"User-Agent": "Leima/1.0"})
    resp.raise_for_status()
    html = resp.text
    text = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.S)
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())[:30000]
    fetched_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    input_bytes = _text_to_input_pdf(f"URL: {url}\nFetched: {fetched_at}\n\n{text}")
    return input_bytes, text, url, fetched_at


@app.post("/notary/poll")
async def notary_poll(request: Request):
    if not NOTARY_POLL_TOKEN or request.headers.get("X-Notary-Token") != NOTARY_POLL_TOKEN:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    if not NOTARY_IMAP_USER or not NOTARY_IMAP_PASSWORD:
        return JSONResponse({"error": "Notary IMAP not configured"}, status_code=503)
    try:
        results = _notary_poll(
            imap_host=NOTARY_IMAP_HOST,
            imap_user=NOTARY_IMAP_USER,
            imap_password=NOTARY_IMAP_PASSWORD,
            smtp_host=NOTARY_SMTP_HOST,
            smtp_port=NOTARY_SMTP_PORT,
            smtp_user=NOTARY_SMTP_USER or NOTARY_IMAP_USER,
            smtp_password=NOTARY_SMTP_PASSWORD or NOTARY_IMAP_PASSWORD,
            notary_from=NOTARY_FROM,
            irys_upload_fn=_irys_upload,
            gateway=IRYS_GATEWAY,
            leima_url=LEIMA_URL,
        )
        return JSONResponse({"processed": len(results), "results": results})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/version")
async def version():
    cache = _poide_cache.copy() if _poide_cache else {}
    return {
        "commit": os.getenv("RENDER_GIT_COMMIT", "unknown"),
        "service": os.getenv("RENDER_SERVICE_NAME", "local"),
        "model": MODEL,
        "poide": {
            "ok": cache.get("ok"),
            "checked_at": cache.get("ts"),
            "verified_commit": cache.get("commit", ""),
            "tx": cache.get("tx"),
            "deploy_status": cache.get("deploy_status"),
            "deployment_ok":        cache.get("deployment_ok"),
            "review_ok":            cache.get("review_ok"),
            "review_stuck":         cache.get("review_stuck"),
            "review_consecutive_failures": cache.get("review_consecutive_failures", 0),
            "deploying":            cache.get("deploying"),
            "deploying_commit":     cache.get("deploying_commit"),
            "deploying_commit_ok":  cache.get("deploying_commit_ok"),
            "commit_matches_poide": (
                bool(running_commit and cache.get("commit") and
                     running_commit.startswith(cache["commit"][:7]))
                if (running_commit := os.getenv("RENDER_GIT_COMMIT", ""))
                else None
            ),
        },
    }


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/validate", response_class=HTMLResponse)
async def validate_page(request: Request, tx: str = ""):
    return templates.TemplateResponse("validate.html", {"request": request, "tx": tx})


@app.post("/fetch-emails", response_class=HTMLResponse)
async def fetch_emails(
    request: Request,
    email_user: str = Form(""),
    email_password: str = Form(""),
    email_sender: str = Form(""),
    email_start: str = Form(""),
    email_end: str = Form(""),
):
    if not all([email_user, email_password, email_sender, email_start, email_end]):
        return HTMLResponse('<p class="fetch-error">Please fill in all fields.</p>')
    if not re.fullmatch(r"[a-zA-Z0-9._%+\-@]+", email_sender):
        return HTMLResponse('<p class="fetch-error">Invalid sender email address.</p>')
    imap = None
    try:
        imap = imaplib.IMAP4_SSL(_imap_server(email_user))
        imap.login(email_user, email_password)
        imap.select("INBOX")
        since = datetime.strptime(email_start, "%Y-%m-%d").strftime("%d-%b-%Y")
        before = (datetime.strptime(email_end, "%Y-%m-%d") + timedelta(days=1)).strftime("%d-%b-%Y")
        _, nums = imap.search(None, "FROM", email_sender, "SINCE", since, "BEFORE", before)
        messages = []
        for num in (nums[0].split() or [])[-50:]:
            _, data = imap.fetch(num, "(RFC822)")
            raw = data[0][1]
            msg = email_lib.message_from_bytes(raw)
            body = _get_body(msg)
            if "DKIM-Signature" in msg:
                try:
                    dkim_valid = dkim.verify(raw)
                except Exception:
                    dkim_valid = False
                dkim_status = "valid" if dkim_valid else "invalid"
            else:
                dkim_status = "none"
            messages.append({
                "subject": _decode_header_value(msg["Subject"]) or "(no subject)",
                "date": msg["Date"] or "",
                "from": _decode_header_value(msg["From"]),
                "to": _decode_header_value(msg.get("To") or ""),
                "message_id": (msg.get("Message-ID") or "").strip(),
                "dkim": dkim_status,
                "body": body,
            })
    except Exception:
        return HTMLResponse('<p class="fetch-error">Could not connect to the email server. Check your settings and try again.</p>')
    finally:
        if imap:
            try:
                imap.logout()
            except Exception:
                pass

    if not messages:
        return HTMLResponse('<p class="fetch-error">No emails found for this period.</p>')

    session_id = uuid.uuid4().hex
    _evict_old_sessions()
    email_sessions[session_id] = {"messages": messages, "_stored_at": time.time()}

    return templates.TemplateResponse(
        "partials/email_results.html",
        {"request": request, "messages": messages, "session_id": session_id},
    )


@app.get("/preview-email/{session_id}/{idx}", response_class=HTMLResponse)
async def preview_email(request: Request, session_id: str, idx: int):
    entry = email_sessions.get(session_id)
    messages = entry["messages"] if entry else None
    if not messages or idx >= len(messages):
        return Response(status_code=404)
    return templates.TemplateResponse(
        "partials/email_preview.html",
        {"request": request, "msg": messages[idx]},
    )


@app.get("/download/{session_id}/source")
async def download_source(session_id: str):
    entry = store.get(session_id)
    if not entry or not entry.get("source"):
        return Response(status_code=404)
    ext = entry.get("source_ext", "pdf")
    mime = entry.get("source_mime", "application/pdf")
    return Response(
        content=entry["source"],
        media_type=mime,
        headers={"Content-Disposition": f"attachment; filename=source.{ext}"},
    )


@app.get("/download/{session_id}/verdict.txt")
async def download_verdict_txt(session_id: str):
    entry = store.get(session_id)
    if not entry:
        return Response(status_code=404)
    return Response(
        content=build_verdict_txt(entry["question"], entry["passes"], entry["timestamp"], entry["input_hash"]),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=verdict.txt"},
    )


@app.get("/download/{session_id}/verdict.html")
async def download_verdict_html(session_id: str):
    entry = store.get(session_id)
    if not entry:
        return Response(status_code=404)
    return Response(
        content=build_verdict_html_export(entry["question"], entry["passes"], entry["timestamp"], entry["input_hash"]),
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=verdict.html"},
    )


@app.get("/download/{session_id}/verdict.json")
async def download_verdict_json_file(session_id: str):
    entry = store.get(session_id)
    if not entry:
        return Response(status_code=404)
    return Response(
        content=build_verdict_json_export(entry["question"], entry["passes"], entry["timestamp"], entry["input_hash"]),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=verdict.json"},
    )


@app.post("/files/{session_id}", response_class=HTMLResponse)
async def files(request: Request, session_id: str, formats: list[str] = Form(default=[])):
    entry = store.get(session_id)
    if not entry:
        return Response(status_code=404)

    if not formats:
        formats = ["pdf"]

    stamp_record = {k: v for k, v in entry["manifest"].items() if k != "stamp"}
    record_bytes = json.dumps(stamp_record, indent=2, ensure_ascii=False).encode()

    try:
        irys_tx = _irys_upload(record_bytes, "application/json", {"Leima-Type": "stamp-record"})
    except Exception as e:
        return HTMLResponse(f'<p class="error">Arweave upload failed: {e}</p>')

    irys_url = f"{IRYS_GATEWAY}/{irys_tx}"
    entry["manifest"] = {**stamp_record, "stamp": {"tx_id": irys_tx, "url": irys_url}}

    return templates.TemplateResponse(
        "partials/files.html",
        {
            "request": request,
            "session_id": session_id,
            "irys_tx": irys_tx,
            "irys_url": irys_url,
            "formats": formats,
            "source_ext": entry.get("source_ext", "pdf"),
        },
    )


@app.get("/download/{session_id}/verdict.pdf")
async def download_verdict(session_id: str):
    entry = store.get(session_id)
    if not entry:
        return Response(status_code=404)
    return Response(
        content=entry["pdf"],
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=verdict.pdf"},
    )


@app.get("/download/{session_id}/manifest.json")
async def download_manifest(session_id: str):
    entry = store.get(session_id)
    if not entry:
        return Response(status_code=404)
    return Response(
        content=json.dumps(entry["manifest"], indent=2, ensure_ascii=False),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=manifest.json"},
    )


async def _validate_notary(request: Request, tx_id: str, eml_file) -> HTMLResponse:
    if not eml_file or not eml_file.filename:
        return HTMLResponse('<p class="error">Please upload the .eml file.</p>')
    eml_bytes = await eml_file.read()

    try:
        resp = http_requests.get(f"{IRYS_GATEWAY}/{tx_id}", timeout=15)
        resp.raise_for_status()
        manifest = resp.json()
    except Exception as e:
        return HTMLResponse(f'<p class="error">Could not fetch manifest from Arweave: {e}</p>')

    results = []

    email_actual = sha256(eml_bytes)
    email_expected = manifest.get("email_sha256", "")
    results.append({
        "label": "Email hash",
        "ok": email_actual == email_expected,
        "expected": email_expected,
        "actual": email_actual,
    })

    dkim_status = manifest.get("dkim", "none")
    results.append({
        "label": "DKIM (at time of notarization)",
        "ok": dkim_status == "valid",
        "expected": "valid",
        "actual": dkim_status,
    })

    results.append({
        "label": "Arweave record",
        "ok": True,
        "expected": "",
        "actual": f"Verified at {IRYS_GATEWAY}/{tx_id}",
    })

    all_ok = all(r["ok"] for r in results)
    return templates.TemplateResponse(
        "partials/validation_result.html",
        {"request": request, "results": results, "all_ok": all_ok},
    )


@app.post("/validate", response_class=HTMLResponse)
async def validate(
    request: Request,
    tx_id: str = Form(""),
    eml_file: UploadFile = File(None),
    source_file: UploadFile = File(None),
    verdict_file: UploadFile = File(None),
    manifest_file: UploadFile = File(None),
):
    if tx_id:
        return await _validate_notary(request, tx_id, eml_file)
    if not source_file or not source_file.filename:
        return HTMLResponse('<p class="error">Please upload a source file.</p>')
    if not verdict_file or not verdict_file.filename:
        return HTMLResponse('<p class="error">Please upload a verdict file.</p>')
    if not manifest_file or not manifest_file.filename:
        return HTMLResponse('<p class="error">Please upload a manifest file.</p>')
    _validate_max = 50 * 1024 * 1024
    if source_file.size and source_file.size > _validate_max:
        return HTMLResponse('<p class="error">Source file too large (max 50 MB).</p>')
    if verdict_file.size and verdict_file.size > _validate_max:
        return HTMLResponse('<p class="error">Verdict file too large (max 50 MB).</p>')
    if manifest_file.size and manifest_file.size > _validate_max:
        return HTMLResponse('<p class="error">Manifest file too large (max 50 MB).</p>')
    source_bytes = await source_file.read()
    verdict_bytes = await verdict_file.read()
    manifest_bytes = await manifest_file.read()

    try:
        manifest = json.loads(manifest_bytes)
    except Exception:
        return HTMLResponse('<p class="error">manifest.json is not valid JSON.</p>')

    results = []

    # 1. Source hash
    source_actual = sha256(source_bytes)
    source_expected = manifest.get("input", {}).get("sha256", "")
    results.append({
        "label": "Source PDF hash",
        "ok": source_actual == source_expected,
        "expected": source_expected,
        "actual": source_actual,
    })

    # 2. Verdict hash
    verdict_actual = sha256(verdict_bytes)
    verdict_expected = manifest.get("verdict_pdf", {}).get("sha256", "")
    results.append({
        "label": "Verdict PDF hash",
        "ok": verdict_actual == verdict_expected,
        "expected": verdict_expected,
        "actual": verdict_actual,
    })

    # 3. Arweave manifest integrity
    arweave = manifest.get("stamp") or manifest.get("arweave") or manifest.get("irys") or {}
    tx_id = arweave.get("tx_id")
    arweave_check = {"label": "Arweave manifest", "ok": False, "expected": "", "actual": ""}
    if not tx_id:
        arweave_check["actual"] = "No arweave.tx_id in manifest"
    else:
        try:
            resp = http_requests.get(f"{IRYS_GATEWAY}/{tx_id}", timeout=15)
            resp.raise_for_status()
            arweave_manifest = resp.json()
            base_manifest = {k: v for k, v in manifest.items() if k != "stamp"}
            arweave_check["ok"] = arweave_manifest == base_manifest
            if not arweave_check["ok"]:
                arweave_check["actual"] = "Arweave content does not match local manifest"
            else:
                arweave_check["actual"] = f"Verified at {IRYS_GATEWAY}/{tx_id}"
        except Exception as e:
            arweave_check["actual"] = f"Fetch failed: {e}"
    results.append(arweave_check)

    all_ok = all(r["ok"] for r in results)
    return templates.TemplateResponse(
        "partials/validation_result.html",
        {"request": request, "results": results, "all_ok": all_ok},
    )


def _irys_upload(data: bytes, content_type: str, tags: dict) -> str:
    builder = Builder("ethereum").wallet(IRYS_PRIVATE_KEY).network(IRYS_NETWORK)
    if IRYS_RPC_URL:
        builder = builder.rpc_url(IRYS_RPC_URL)
    uploader = builder.build()
    all_tags = {"Content-Type": content_type, "App-Name": "Leima", **tags}
    result = uploader.upload(bytearray(data), tags_from_dict(all_tags))
    return result["id"]




_IMAGE_MIMES = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "png": "image/png", "gif": "image/gif",
    "webp": "image/webp", "heic": "image/heic", "heif": "image/heif",
}

def _detect_image_mime(filename: str) -> str | None:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return _IMAGE_MIMES.get(ext)


def _check_c2pa(image_bytes: bytes, mime: str) -> dict | None:
    """Returns C2PA manifest summary, or None if library not available."""
    try:
        import c2pa
        import io
        reader = c2pa.Reader(mime, io.BytesIO(image_bytes))
        report_json = reader.json()
        if not report_json:
            return {"present": False}
        data = json.loads(report_json)
        active = data.get("active_manifest")
        if not active or active not in data.get("manifests", {}):
            return {"present": False}
        m = data["manifests"][active]
        bad = [s for s in data.get("validation_status", [])
               if "mismatch" in s.get("code", "") or "error" in s.get("code", "").lower()]
        actions = []
        location = None
        for assertion in m.get("assertions", []):
            label = assertion.get("label", "")
            data = assertion.get("data", {})
            if label == "c2pa.actions":
                for a in data.get("actions", []):
                    act = a.get("action", "")
                    if act:
                        actions.append(act.removeprefix("c2pa."))
            elif label == "stds.exif":
                lat = data.get("EXIF:GPSLatitude") or data.get("exif:GPSLatitude")
                lon = data.get("EXIF:GPSLongitude") or data.get("exif:GPSLongitude")
                lat_ref = data.get("EXIF:GPSLatitudeRef") or data.get("exif:GPSLatitudeRef", "")
                lon_ref = data.get("EXIF:GPSLongitudeRef") or data.get("exif:GPSLongitudeRef", "")
                alt = data.get("EXIF:GPSAltitude") or data.get("exif:GPSAltitude")
                if lat is not None and lon is not None:
                    if lat_ref.upper() == "S":
                        lat = -abs(float(lat))
                    if lon_ref.upper() == "W":
                        lon = -abs(float(lon))
                    location = {"lat": float(lat), "lon": float(lon)}
                    if alt is not None:
                        location["alt"] = float(alt)
            elif label == "c2pa.location.precise":
                lat = data.get("latitude")
                lon = data.get("longitude")
                if lat is not None and lon is not None:
                    location = {"lat": float(lat), "lon": float(lon)}
                    if data.get("altitude") is not None:
                        location["alt"] = float(data["altitude"])
        sig = m.get("signature_info", {})
        return {
            "present": True,
            "valid": len(bad) == 0,
            "generator": m.get("claim_generator", ""),
            "signer": sig.get("issuer", ""),
            "signed_at": sig.get("time", ""),
            "actions": actions,
            "location": location,
        }
    except ImportError:
        return None
    except Exception:
        return {"present": False}


def _check_pdf_signatures(pdf_bytes: bytes) -> dict | None:
    """Check PDF for digital signatures and RFC 3161 timestamps."""
    try:
        import io as _io
        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        reader = PdfReader(_io.BytesIO(pdf_bytes))
        root = reader.trailer["/Root"]
        acroform = root.get("/AcroForm")
        if not acroform:
            return {"signed": False}
        if hasattr(acroform, "get_object"):
            acroform = acroform.get_object()
        fields = acroform.get("/Fields", [])
    except Exception:
        return {"signed": False}

    results = []
    for field_ref in fields:
        try:
            field = field_ref.get_object() if hasattr(field_ref, "get_object") else field_ref
            if field.get("/FT") != "/Sig" or "/V" not in field:
                continue
            sig = field["/V"]
            if hasattr(sig, "get_object"):
                sig = sig.get_object()
            entry: dict = {}
            # Claimed signing time and name from PDF dict
            if "/M" in sig:
                raw_m = str(sig["/M"]).strip("D:'")
                entry["timestamp"] = raw_m
                entry["timestamp_rfc3161"] = False
            if "/Name" in sig:
                entry["signer_cn"] = str(sig["/Name"])
            # Parse CMS bytes for richer info
            if "/Contents" in sig:
                cms_bytes = sig["/Contents"]
                if isinstance(cms_bytes, bytes):
                    _enrich_from_cms(cms_bytes, entry)
            results.append(entry)
        except Exception:
            pass

    if not results:
        return {"signed": False}
    first = results[0]
    return {
        "signed": True,
        "rfc3161": first.get("timestamp_rfc3161", False),
        "count": len(results),
        "signer": first.get("signer_cn") or first.get("signer_org") or "",
        "signer_org": first.get("signer_org", ""),
        "timestamp": first.get("timestamp"),
        "tsa": first.get("tsa", ""),
        "signatures": results,
    }


def _enrich_from_cms(raw: bytes, entry: dict) -> None:
    """Parse CMS/PKCS7 bytes to extract signer cert info and RFC 3161 timestamp."""
    try:
        from asn1crypto import cms, tsp
        ci = cms.ContentInfo.load(raw)
        if ci["content_type"].native != "signed_data":
            return
        sd = ci["content"]
        # Signer certificate — first cert in the bag is usually the leaf
        certs = sd.get("certificates")
        if certs:
            for cc in certs:
                try:
                    cert = cc.chosen
                    subj = cert.subject
                    for rdn in subj.chosen:
                        for atv in rdn:
                            oid = atv["type"].dotted
                            if oid == "2.5.4.3":
                                entry["signer_cn"] = atv["value"].native
                            elif oid == "2.5.4.10":
                                entry["signer_org"] = atv["value"].native
                    break
                except Exception:
                    pass
        # RFC 3161 timestamp in unsigned attributes
        for si in sd["signer_infos"]:
            try:
                for attr in si["unsigned_attrs"]:
                    if attr["type"].native != "signature_time_stamp_token":
                        continue
                    for v in attr["values"]:
                        try:
                            tst_ci = cms.ContentInfo.load(v.dump())
                            tst_sd = tst_ci["content"]
                            encap = tst_sd["encap_content_info"]
                            tst_info = tsp.TSTInfo.load(
                                encap["content"].parsed.dump()
                            )
                            entry["timestamp"] = tst_info["gen_time"].native.isoformat()
                            entry["timestamp_rfc3161"] = True
                            tsa_field = tst_info["tsa"]
                            if tsa_field.name != "absent":
                                entry["tsa"] = str(tsa_field.chosen.human_friendly)
                        except Exception:
                            pass
            except Exception:
                pass
    except Exception:
        pass


def build_verdict_txt(question: str, passes: list[tuple[str, str]], timestamp: str, input_hash: str) -> bytes:
    lines = ["STAMPD VERDICT", "=" * 40,
             f"Timestamp: {timestamp}", f"Model: {MODEL}", f"Input SHA-256: {input_hash}",
             "", f"Claim: {question}", ""]
    for label, text in passes:
        lines += [f"\n{label}", "-" * len(label), text, ""]
    return "\n".join(lines).encode("utf-8")


def build_verdict_html_export(question: str, passes: list[tuple[str, str]], timestamp: str, input_hash: str) -> bytes:
    pass_html = ""
    for label, text in passes:
        content = bleach.clean(
            _md.markdown(text or "", extensions=["nl2br"]),
            tags=_MD_ALLOWED_TAGS, strip=True,
        )
        pass_html += f"<section><h2>{label}</h2>{content}</section>\n"
    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Leima Verdict</title>
<style>
  body{{font-family:system-ui,sans-serif;max-width:720px;margin:2rem auto;padding:0 1rem;color:#212529}}
  h1{{font-size:1.4rem;margin-bottom:.25rem}} .meta{{color:#6c757d;font-size:.85rem;margin-bottom:1.5rem}}
  .claim{{background:#f0f5ff;border-left:3px solid #0d6efd;padding:.75rem 1rem;margin-bottom:1.5rem;font-weight:600}}
  section{{margin-bottom:2rem}} h2{{font-size:.75rem;text-transform:uppercase;letter-spacing:.07em;color:#adb5bd;margin-bottom:.5rem}}
  p{{margin:0 0 .6em;line-height:1.7}}
</style></head>
<body>
<h1>Leima Verdict</h1>
<div class="meta">Timestamp: {_html_escape(timestamp)} &nbsp;&middot;&nbsp; Model: {_html_escape(MODEL)} &nbsp;&middot;&nbsp; Input SHA-256: {_html_escape(input_hash)}</div>
<div class="claim">{_html_escape(question)}</div>
{pass_html}</body></html>"""
    return html.encode("utf-8")


def build_verdict_json_export(question: str, passes: list[tuple[str, str]], timestamp: str, input_hash: str) -> bytes:
    return json.dumps({
        "claim": question, "timestamp": timestamp, "model": MODEL, "input_hash": input_hash,
        "passes": [{"label": l, "text": t} for l, t in passes],
    }, indent=2, ensure_ascii=False).encode()


PDF_URL_MAX_BYTES = 10 * 1024 * 1024  # 10 MB


def _fetch_pdf_from_url(url: str) -> tuple[bytes, str]:
    _check_ssrf(url)
    parsed = urlparse(url)

    resp = _safe_get(url, timeout=30, stream=True)
    resp.raise_for_status()
    content_length = resp.headers.get("Content-Length")
    if content_length and int(content_length) > PDF_URL_MAX_BYTES:
        resp.close()
        raise ValueError(f"File too large (max {PDF_URL_MAX_BYTES // 1024 // 1024} MB)")

    content_type = resp.headers.get("Content-Type", "")
    if "pdf" not in content_type and not url.lower().endswith(".pdf"):
        raise ValueError(f"URL does not point to a PDF (Content-Type: {content_type})")

    chunks = []
    total = 0
    for chunk in resp.iter_content(chunk_size=65536):
        total += len(chunk)
        if total > PDF_URL_MAX_BYTES:
            raise ValueError(f"File too large (max {PDF_URL_MAX_BYTES // 1024 // 1024} MB)")
        chunks.append(chunk)

    data = b"".join(chunks)
    label = parsed.path.split("/")[-1] or parsed.netloc
    return data, label


def _text_to_input_pdf(text: str) -> bytes:
    p = FPDF()
    p.add_page()
    p.set_font("Helvetica", size=11)
    p.multi_cell(0, 6, _safe(text))
    return bytes(p.output())


def _run_analysis(question: str, contents: list, input_bytes: bytes, input_label: str,
                  source_ext: str = "pdf", source_mime: str = "application/pdf",
                  email_meta: dict | None = None, web_meta: dict | None = None,
                  source_context: dict | None = None) -> dict:
    _poide_cache_ready.wait(timeout=10)
    poide_snap = _poide_cache.copy() if _poide_cache else None

    result = analyse(question, contents, source_context=source_context)
    input_hash = sha256(input_bytes)
    verdict_pdf = build_verdict_pdf(question, result["passes"], result["timestamp"], input_hash, prompts=result["prompt_log"], source_context=source_context)
    verdict_hash = sha256(verdict_pdf)
    manifest = build_manifest(
        timestamp=result["timestamp"],
        model=MODEL,
        input_label=input_label,
        input_hash=input_hash,
        verdict_hash=verdict_hash,

        email_meta=email_meta,
        web_meta=web_meta,
    )
    if poide_snap and poide_snap.get("tx"):
        manifest["poide"] = {
            "tx": poide_snap["tx"],
            "url": f"{IRYS_GATEWAY}/{poide_snap['tx']}",
            "checked_at": poide_snap.get("ts", ""),
            "commit": poide_snap.get("commit", ""),
            "ok": poide_snap.get("ok", False),
        }
    session_id = uuid.uuid4().hex
    _evict_old_sessions()
    store[session_id] = {
        "pdf": verdict_pdf, "manifest": manifest, "source": input_bytes,
        "source_ext": source_ext, "source_mime": source_mime,
        "passes": result["passes"], "question": question,
        "timestamp": result["timestamp"], "input_hash": input_hash,
        "_stored_at": time.time(),
    }
    return {
        "passes": result["passes"],
        "summary_verdict": result["summary_verdict"],
        "verdict_category": result.get("verdict_category", "Epävarma"),
        "timestamp": result["timestamp"],
        "input_hash": input_hash,
        "verdict_pdf": verdict_pdf,
        "verdict_hash": verdict_hash,
        "manifest": manifest,
        "poide_snap": poide_snap,
        "session_id": session_id,
        "input_label": input_label,
    }


@app.post("/ask", response_class=HTMLResponse)
async def ask(
    request: Request,
    question: str = Form(""),
    active_tab: str = Form("pdf"),
    text_input: str = Form(""),
    email_session_id: str = Form(""),
    email_idx: str = Form(""),
    pdf_file: UploadFile = File(None),
    pdf_url: str = Form(""),
    web_url: str = Form(""),
    image_file: UploadFile = File(None),
    assess_credibility: str = Form(""),
    gh_repo: str = Form(""),
    gh_ref: str = Form("main"),
    gh_token: str = Form(""),
    gh_paths: str = Form(""),
    review_mode: str = Form("claim"),
    rules_url: str = Form(""),
):
    if review_mode != "code_review" and not question.strip():
        return HTMLResponse('<div class="error">Please enter a claim.</div>')

    contents = []
    email_meta = None
    web_meta = None
    c2pa_info = None
    source_context = None
    source_ext = "pdf"
    source_mime = "application/pdf"

    MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB

    if active_tab == "image":
        if not image_file or not image_file.filename:
            return HTMLResponse('<div class="error">Please upload an image.</div>')
        mime = _detect_image_mime(image_file.filename)
        if not mime:
            return HTMLResponse('<div class="error">Unsupported image format. Use JPG, PNG, GIF, WebP, HEIC, or HEIF.</div>')
        if image_file.size and image_file.size > MAX_UPLOAD_BYTES:
            return HTMLResponse('<div class="error">File too large (max 20 MB).</div>')
        input_bytes = await image_file.read()
        c2pa_info = _check_c2pa(input_bytes, mime)
        input_label = mime
        source_ext = image_file.filename.rsplit(".", 1)[-1].lower()
        source_mime = mime
        contents.append(types.Part.from_bytes(data=input_bytes, mime_type=mime))
        if c2pa_info and c2pa_info.get("present"):
            source_context = {
                "type": "image_c2pa_valid" if c2pa_info.get("valid") else "image_c2pa_invalid",
                "c2pa_generator": c2pa_info.get("generator", ""),
                "c2pa_signer": c2pa_info.get("signer", ""),
                "c2pa_location": c2pa_info.get("location"),
                "c2pa_location_present": bool(c2pa_info.get("location")),
            }
        else:
            source_context = {"type": "image_no_c2pa"}

    elif active_tab == "pdf":
        if pdf_url.strip():
            try:
                input_bytes, input_label = _fetch_pdf_from_url(pdf_url.strip())
            except Exception as e:
                return HTMLResponse(f'<div class="error">URL error: {e}</div>')
            parsed = urlparse(pdf_url.strip())
            source_context = {"type": "pdf_url", "domain": parsed.netloc, "url": pdf_url.strip()}
        elif pdf_file and pdf_file.filename:
            if pdf_file.size and pdf_file.size > MAX_UPLOAD_BYTES:
                return HTMLResponse('<div class="error">File too large (max 20 MB).</div>')
            input_bytes = await pdf_file.read()
            input_label = "application/pdf"
            sig_info = _check_pdf_signatures(input_bytes)
            if sig_info and sig_info.get("signed"):
                source_context = {
                    "type": "pdf_signed",
                    "sig_signer": sig_info.get("signer", ""),
                    "sig_signer_org": sig_info.get("signer_org", ""),
                    "sig_timestamp": sig_info.get("timestamp"),
                    "sig_rfc3161": sig_info.get("rfc3161", False),
                    "sig_tsa": sig_info.get("tsa", ""),
                    "sig_count": sig_info.get("count", 1),
                }
            else:
                source_context = {"type": "pdf_unsigned"}
        else:
            return HTMLResponse('<div class="error">Please upload a PDF or enter a URL.</div>')
        contents.append(types.Part.from_bytes(data=input_bytes, mime_type="application/pdf"))

    elif active_tab == "text":
        if not text_input.strip():
            return HTMLResponse('<div class="error">Please paste some text.</div>')
        if len(text_input) > 500_000:
            return HTMLResponse('<div class="error">Text is too long (max 500 000 characters).</div>')
        input_bytes = _text_to_input_pdf(text_input)
        input_label = "text-input"
        source_context = None
        contents.append(f"Document content:\n{text_input}")

    elif active_tab == "web":
        if not web_url.strip():
            return HTMLResponse('<div class="error">Please enter a URL.</div>')
        try:
            input_bytes, page_text, fetched_url, fetched_at = _fetch_webpage(web_url.strip())
        except Exception as e:
            return HTMLResponse(f'<div class="error">URL error: {e}</div>')
        web_meta = {"url": fetched_url, "fetched_at": fetched_at}
        input_label = fetched_url
        parsed = urlparse(fetched_url)
        source_context = {"type": "web", "domain": parsed.netloc, "fetched_at": fetched_at, "url": fetched_url}
        contents.append(f"Web page from: {fetched_url}\nFetched at: {fetched_at}\n\n{page_text}")

    elif active_tab == "github":
        gh_repo  = gh_repo.strip().removeprefix("https://github.com/").strip("/")
        gh_ref   = gh_ref.strip() or "main"
        gh_token = gh_token.strip()
        gh_paths_list = [p.strip() for p in gh_paths.splitlines() if p.strip()]
        gh_paths = gh_paths_list
        if not gh_repo or "/" not in gh_repo:
            return HTMLResponse('<div class="error">Enter a valid repository (owner/repo).</div>')
        try:
            commit_sha = _github_resolve_commit(gh_repo, gh_ref, gh_token)
            if review_mode == "code_review":
                files = _github_fetch_tree(gh_repo, commit_sha, gh_token)
            else:
                if not gh_paths:
                    return HTMLResponse('<div class="error">Enter at least one file path.</div>')
                if len(gh_paths) > 20:
                    return HTMLResponse('<div class="error">Maximum 20 files per request.</div>')
                files = _github_fetch_files(gh_repo, commit_sha, gh_paths, gh_token)
        except Exception as e:
            return HTMLResponse(f'<div class="error">GitHub error: {e}</div>')
        all_verified = all(f["verified"] for f in files)
        unverified = [f["path"] for f in files if not f["verified"]]
        blob_hashes = {f["path"]: f["blob_sha"] for f in files}
        bundled = "\n\n".join(
            f"### {f['path']}\n```\n{f['content']}\n```" for f in files
        )
        input_label = f"github:{gh_repo}@{commit_sha[:7]}"
        input_bytes = bundled.encode("utf-8")
        source_context = {
            "type": "github_commit",
            "repo": gh_repo,
            "commit": commit_sha,
            "commit_short": commit_sha[:7],
            "paths": gh_paths,
            "all_verified": all_verified,
            "unverified_paths": unverified,
            "blob_hashes": blob_hashes,
        }
        contents.append(bundled)

        if review_mode == "code_review":
            if not rules_url.strip():
                return HTMLResponse('<div class="error">Enter a rules URL for code review.</div>')
            try:
                _check_ssrf(rules_url.strip())
                rules_resp = _safe_get(rules_url.strip(), timeout=15)
                rules_text = rules_resp.text
            except Exception as e:
                return HTMLResponse(f'<div class="error">Could not fetch rules: {e}</div>')
            try:
                cr = analyse_code_review(bundled, rules_text, gh_repo, commit_sha)
            except Exception:
                return HTMLResponse('<div class="error">Code review analysis failed. Please try again.</div>')
            manifest_cr = {
                "type": "code_review",
                "repo": gh_repo,
                "commit": commit_sha,
                "rules_url": rules_url.strip(),
                "compliant": cr["compliant"],
                "timestamp": cr["timestamp"],
                "verdict": cr["verdict"],
                "blob_hashes": blob_hashes,
            }
            try:
                tx_id = _irys_upload(
                    json.dumps(manifest_cr, ensure_ascii=False, indent=2).encode(),
                    "application/json",
                    {"Leima-Type": "code-review"},
                )
                arweave_url = f"{IRYS_GATEWAY}/{tx_id}"
            except Exception:
                tx_id = ""
                arweave_url = ""
            status_color = "#198754" if cr["compliant"] else "#dc3545"
            status_label = "COMPLIANT" if cr["compliant"] else "VIOLATION"
            checks_html = "".join(
                f'<li style="margin:.3rem 0">{_html_escape(l)}</li>'
                for l in cr["verdict"].splitlines() if l.strip()
            )
            arweave_html = (
                f'<p style="margin-top:1rem">Arweave: <a href="{_html_escape(arweave_url)}" target="_blank">{_html_escape(arweave_url)}</a></p>'
                if arweave_url else ""
            )
            return HTMLResponse(f"""
<div style="border-left:4px solid {status_color};padding:.75rem 1rem;margin-bottom:1rem;background:#f8f9fa;border-radius:4px">
  <strong style="color:{status_color};font-size:1.1rem">{status_label}</strong>
  <span style="color:#6c757d;font-size:.85rem;margin-left:.75rem">{_html_escape(cr["timestamp"])}</span>
</div>
<ul style="list-style:none;padding:0;font-size:.9rem">{checks_html}</ul>
<p style="font-size:.8rem;color:#6c757d;margin-top:.5rem">
  Repo: {_html_escape(gh_repo)} · Commit: {_html_escape(commit_sha[:12])} ·
  Rules: <a href="{_html_escape(rules_url.strip())}" target="_blank">{_html_escape(rules_url.strip())}</a>
</p>
{arweave_html}
""")

    elif active_tab == "email":
        _entry = email_sessions.get(email_session_id)
        msgs = _entry["messages"] if _entry else None
        if not msgs or not email_idx.isdigit() or int(email_idx) >= len(msgs):
            return HTMLResponse('<div class="error">No email selected.</div>')
        msg = msgs[int(email_idx)]
        body = msg["body"]
        body_hash = sha256(body.encode())
        email_meta = {
            "dkim": msg["dkim"],
            "body_sha256": body_hash,
        }
        sender_domain = msg["from"].split("@")[-1].rstrip(">").strip() if "@" in msg["from"] else ""
        source_context = {"type": "email", "dkim": msg["dkim"], "sender_domain": sender_domain}
        input_bytes = _text_to_input_pdf(
            f"From: {msg['from']}\nTo: {msg['to']}\nSubject: {msg['subject']}\n"
            f"Date: {msg['date']}\nMessage-ID: {msg['message_id']}\n"
            f"DKIM: {msg['dkim']}\n"
            f"Body SHA-256: {body_hash}\n\n{body}"
        )
        input_label = "email"
        contents.append(f"Email from: {msg['from']}\nSubject: {msg['subject']}\nDate: {msg['date']}\n\n{body}")

    else:
        return HTMLResponse('<div class="error">Unknown input type.</div>')

    if question.strip():
        contents.append(question)

    if assess_credibility != "1":
        source_context = {"type": "content_only"}

    verdict_prefix = "Document (with evaluation)" if assess_credibility == "1" else "Document"

    try:
        result = _run_analysis(question, contents, input_bytes, input_label,
                               source_ext, source_mime,
                               email_meta, web_meta, source_context)
    except ValueError as e:
        return HTMLResponse(f'<div class="error">{e}</div>')
    except Exception:
        return HTMLResponse('<div class="error">Analysis failed. Please try again.</div>')

    if active_tab == "image" and c2pa_info:
        store[result["session_id"]]["manifest"]["c2pa"] = c2pa_info

    return templates.TemplateResponse(
        "partials/answer.html",
        {
            "request": request,
            "passes": result["passes"],
            "question": question,
            "summary_verdict": result["summary_verdict"],
            "verdict_category": result["verdict_category"],
            "verdict_prefix": verdict_prefix,
            "filename": result["input_label"],
            "input_hash": result["input_hash"],
            "verdict_hash": result["verdict_hash"],
            "session_id": result["session_id"],
            "timestamp": result["timestamp"],
            "poide_snap": result.get("poide_snap"),
            "irys_gateway": IRYS_GATEWAY,
            "c2pa": c2pa_info if active_tab == "image" else None,
        },
    )


class StampRequest(BaseModel):
    claim: str
    source_type: str  # "pdf_base64" | "pdf_url" | "text"
    source: str       # base64-encoded PDF, URL, or plain text


class CodeReviewRequest(BaseModel):
    repo: str          # owner/repo
    ref: str = "main"  # branch, tag, or commit SHA
    rules_url: str     # URL to policy/rules document (raw text)
    token: str = ""    # GitHub token for private repos


@app.post("/api/stamp")
async def api_stamp(body: StampRequest):
    claim = body.claim.strip()
    if not claim:
        return JSONResponse({"error": "claim is required"}, status_code=400)

    contents = []
    try:
        if body.source_type == "pdf_base64":
            if len(body.source) > 20 * 1024 * 1024 * 4 // 3:
                return JSONResponse({"error": "File too large (max 20 MB)"}, status_code=400)
            input_bytes = base64.b64decode(body.source)
            if not input_bytes.startswith(b"%PDF-"):
                return JSONResponse({"error": "source is not a valid PDF"}, status_code=400)
            input_label = "api-upload.pdf"
            contents.append(types.Part.from_bytes(data=input_bytes, mime_type="application/pdf"))
        elif body.source_type == "pdf_url":
            input_bytes, input_label = _fetch_pdf_from_url(body.source.strip())
            contents.append(types.Part.from_bytes(data=input_bytes, mime_type="application/pdf"))
        elif body.source_type == "text":
            if not body.source.strip():
                return JSONResponse({"error": "source is empty"}, status_code=400)
            input_bytes = _text_to_input_pdf(body.source)
            input_label = "api-text"
            contents.append(f"Document content:\n{body.source}")
        else:
            return JSONResponse({"error": "source_type must be pdf_base64, pdf_url, or text"}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    contents.append(claim)

    try:
        result = _run_analysis(claim, contents, input_bytes, input_label)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=422)
    except Exception as e:
        return JSONResponse({"error": f"Analysis failed: {e}"}, status_code=500)

    manifest = result["manifest"]
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
    try:
        tx_id = _irys_upload(manifest_bytes, "application/json", {"Leima-Type": "manifest"})
    except Exception as e:
        return JSONResponse({"error": f"Arweave upload failed: {e}"}, status_code=502)

    irys_url = f"{IRYS_GATEWAY}/{tx_id}"
    full_manifest = {**manifest, "stamp": {"tx_id": tx_id, "url": irys_url}}
    store[result["session_id"]]["manifest"] = full_manifest

    return JSONResponse({
        "verdict": result["summary_verdict"],
        "passes": [{"label": label, "text": text} for label, text in result["passes"]],
        "input_hash": result["input_hash"],
        "verdict_hash": result["verdict_hash"],
        "timestamp": result["timestamp"],
        "model": MODEL,
        "stamp": {"tx_id": tx_id, "url": irys_url},
        "manifest": full_manifest,
    })


@app.post("/api/code-review")
async def api_code_review(body: CodeReviewRequest):
    repo = body.repo.strip().removeprefix("https://github.com/").strip("/")
    if not repo or "/" not in repo:
        return JSONResponse({"error": "repo must be owner/repo"}, status_code=400)
    if not body.rules_url.strip():
        return JSONResponse({"error": "rules_url is required"}, status_code=400)

    try:
        _check_ssrf(body.rules_url.strip())
        rules_resp = _safe_get(body.rules_url.strip(), timeout=15)
        rules_text = rules_resp.text
    except Exception as e:
        return JSONResponse({"error": f"Could not fetch rules: {e}"}, status_code=400)

    try:
        commit_sha = _github_resolve_commit(repo, body.ref.strip() or "main", body.token)
        files = _github_fetch_tree(repo, commit_sha, body.token)
    except Exception as e:
        return JSONResponse({"error": f"GitHub error: {e}"}, status_code=400)

    if not files:
        return JSONResponse({"error": "No source files found in repository"}, status_code=400)

    bundled = "\n\n".join(
        f"### {f['path']}\n```\n{f['content']}\n```" for f in files
    )

    try:
        cr = analyse_code_review(bundled, rules_text, repo, commit_sha)
    except Exception:
        return JSONResponse({"error": "Analysis failed"}, status_code=500)

    manifest = {
        "type": "code_review",
        "repo": repo,
        "commit": commit_sha,
        "rules_url": body.rules_url.strip(),
        "compliant": cr["compliant"],
        "timestamp": cr["timestamp"],
        "verdict": cr["verdict"],
        "files_reviewed": len(files),
        "blob_hashes": {f["path"]: f["blob_sha"] for f in files},
    }
    try:
        tx_id = _irys_upload(
            json.dumps(manifest, ensure_ascii=False, indent=2).encode(),
            "application/json",
            {"Leima-Type": "code-review"},
        )
        arweave_url = f"{IRYS_GATEWAY}/{tx_id}"
    except Exception:
        tx_id = ""
        arweave_url = ""

    return JSONResponse({
        "compliant": cr["compliant"],
        "verdict": cr["verdict"],
        "commit": commit_sha,
        "files_reviewed": len(files),
        "timestamp": cr["timestamp"],
        "rules_url": body.rules_url.strip(),
        **({"stamp": {"tx_id": tx_id, "url": arweave_url}} if tx_id else {}),
    })
