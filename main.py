import os
import io
import zipfile

import asyncio
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
import unicodedata
import email as email_lib
from collections import Counter
from email.header import decode_header as _decode_header
from html.parser import HTMLParser as _HTMLParser
from datetime import datetime, timedelta
from urllib.parse import urlparse
from dotenv import load_dotenv
import re
from html import escape as _html_escape
import markdown as _md
import bleach
import requests as http_requests
from fastapi import FastAPI, File, Form, UploadFile, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fpdf.enums import MethodReturnValue
from google.genai import types
from neutral_witness import analyse, analyse_code_review, PASS_LABELS, MODEL
from notary import poll_and_process as _notary_poll
from browser_session import parse_and_verify as _parse_browser_session
import email_eml
from fpdf import FPDF
from irys_sdk import Builder
from irys_sdk.bundle.tags import from_dict as tags_from_dict

load_dotenv()

import logging as _logging
_logging.basicConfig(level=_logging.WARNING)
for _noisy in ("uvicorn.access", "uvicorn.error", "httpx", "httpcore", "google"):
    _logging.getLogger(_noisy).setLevel(_logging.ERROR)


def _patch_urllib3_ssrf_guard():
    """Prevent DNS rebinding by resolving once at socket level and connecting to the pinned IP."""
    try:
        import urllib3.util.connection as _u3conn
    except ImportError:
        return
    _orig = _u3conn.create_connection

    def _ssrf_safe_create_connection(address, *args, **kwargs):
        host, port = address
        try:
            infos = socket.getaddrinfo(host, port or 0, 0, socket.SOCK_STREAM)
        except OSError:
            raise OSError(f"Cannot resolve hostname: {host}")
        resolved_ip = None
        for info in infos:
            ip = info[4][0]
            try:
                addr = ipaddress.ip_address(ip)
            except ValueError:
                continue
            if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
                raise ConnectionError(f"Connection to private/internal address blocked: {ip}")
            if resolved_ip is None:
                resolved_ip = ip
        if resolved_ip is None:
            raise OSError(f"No resolvable address for: {host}")
        return _orig((resolved_ip, port), *args, **kwargs)

    _u3conn.create_connection = _ssrf_safe_create_connection


_patch_urllib3_ssrf_guard()

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

_KV_URL              = os.getenv("KV_REST_API_URL", "")
_KV_TOKEN            = os.getenv("KV_REST_API_TOKEN", "")
_KV_KEY              = "tread_v"
_KV_TTL              = 10  # seconds
_KV_MONITOR_CACHE    = "tread_monitor_cache"
_KV_MONITOR_BASELINE = "tread_monitor_baseline_v2"
_KV_PRE_DEPLOY_PREFIX  = "pre_deploy_"
_KV_PRE_DEPLOY_TTL     = 900  # 15 minutes — covers code review (≤10 min) + deploy
_KV_DEPLOY_INCOMING    = "deploy_incoming"
_KV_DEPLOY_INCOMING_TTL = 300  # 5 minutes — covers code review + deploy cycle

_tread_cache: dict | None = None
_tread_cache_ready = threading.Event()
_PAGES_URL = "https://fxg55647.github.io/leima"

def _check_env() -> None:
    required = {
        "KV_REST_API_URL":    "deploy signals ja monitor cache",
        "KV_REST_API_TOKEN":  "deploy signals ja monitor cache",
        "VERCEL_TOKEN":       "Vercel deployment state",
        "VERCEL_PROJECT_ID":  "Vercel deployment state",
        "IRYS_PRIVATE_KEY":   "Arweave-tallennus",
        "GITHUB_DISPATCH_TOKEN": "GitHub Actions -integraatio",
        "PRE_DEPLOY_TOKEN":   "deploy-incoming autentikointi",
    }
    missing = [k for k, _ in required.items() if not os.getenv(k)]
    if missing:
        for k in missing:
            print(f"WARNING: {k} not set — {required[k]} disabled", flush=True)

_check_env()

_VERCEL_TOKEN      = os.getenv("VERCEL_TOKEN", "")
_VERCEL_PROJECT_ID = os.getenv("VERCEL_PROJECT_ID", "")
_VERCEL_TEAM_ID    = os.getenv("VERCEL_TEAM_ID", "")
_VERCEL_BUILDING   = {"BUILDING", "QUEUED", "INITIALIZING"}

_MONITOR_PATHS = {
    ".github/workflows/tread.yml",
    ".github/workflows/monthly-audit.yml",
    ".github/workflows/code_review.yml",
    "tread_check.py",
    "tread_arweave.py",
    "monthly_audit.py",
    "code_review.py",
    "POLICY.example.md",
}
_GITHUB_REPO = "fxg55647/leima"
_GITHUB_BRANCH = "main"
_monitor_baseline: dict | None = None


def _kv_get(key: str = _KV_KEY) -> dict | None:
    if not _KV_URL or not _KV_TOKEN:
        return None
    try:
        r = http_requests.get(f"{_KV_URL}/get/{key}",
                               headers={"Authorization": f"Bearer {_KV_TOKEN}"}, timeout=3)
        val = r.json().get("result") if r.status_code == 200 else None
        if val:
            padded = val + "=" * (-len(val) % 4)
            return json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
    except Exception:
        pass
    return None


def _kv_set(data: dict, key: str = _KV_KEY, ttl: int = _KV_TTL) -> None:
    if not _KV_URL or not _KV_TOKEN:
        return
    try:
        val = base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")
        http_requests.post(f"{_KV_URL}/set/{key}/{val}?EX={ttl}",
                           headers={"Authorization": f"Bearer {_KV_TOKEN}"}, timeout=3)
    except Exception:
        pass


def _kv_hincrby(key: str, field: str, amount: int = 1) -> None:
    if not _KV_URL or not _KV_TOKEN:
        return
    try:
        http_requests.get(f"{_KV_URL}/hincrby/{key}/{field}/{amount}",
                          headers={"Authorization": f"Bearer {_KV_TOKEN}"}, timeout=3)
    except Exception:
        pass


def _kv_hgetall(key: str) -> dict[str, int]:
    if not _KV_URL or not _KV_TOKEN:
        return {}
    try:
        r = http_requests.get(f"{_KV_URL}/hgetall/{key}",
                              headers={"Authorization": f"Bearer {_KV_TOKEN}"}, timeout=3)
        flat = r.json().get("result") if r.status_code == 200 else None
        if flat:
            return {flat[i]: int(flat[i + 1]) for i in range(0, len(flat), 2)}
    except Exception:
        pass
    return {}


# Sallitut nimet /track-tab -kutsuille — estää mielivaltaisten kenttien ruiskutuksen Redis-hashiin
_TAB_TRACK_NAMES = {
    "cat_text", "cat_claim", "cat_web", "cat_image", "cat_email", "cat_github", "cat_bundle",
    "sub_pdf", "sub_text", "sub_image", "sub_image-url", "sub_web", "sub_github", "sub_bundle", "sub_claim", "sub_email",
}
_KV_TAB_CLICKS = "tab_clicks"


def _validate_deployment_source(source: str, meta: dict) -> tuple[bool, list[str]]:
    """Tarkistaa tuleeko deployment Vercelin GitHub-integraatiosta (ei CLI/dashboard).
    source-kenttä on Vercelin asettama eikä ole muutettavissa --meta-parametreilla.
    Palauttaa (ok, lista poikkeamista)."""
    if source != "git":
        return False, [f"source: got '{source}' expected 'git'"]
    branch = meta.get("githubCommitRef", "")
    if branch and branch != _GITHUB_BRANCH:
        return False, [f"githubCommitRef: got '{branch}' expected '{_GITHUB_BRANCH}'"]
    return True, []


def _fetch_vercel_state() -> tuple[bool | None, str | None, str | None, bool | None, list, bool]:
    """Returns (deploying, live_commit, deploying_commit, source_ok, source_mismatches, api_error)."""
    if not _VERCEL_TOKEN or not _VERCEL_PROJECT_ID:
        return None, None, None, None, [], False
    try:
        params = f"projectId={_VERCEL_PROJECT_ID}&limit=10"
        if _VERCEL_TEAM_ID:
            params += f"&teamId={_VERCEL_TEAM_ID}"
        r = http_requests.get(
            f"https://api.vercel.com/v6/deployments?{params}",
            headers={"Authorization": f"Bearer {_VERCEL_TOKEN}"},
            timeout=10,
        )
        if r.status_code != 200:
            return None, None, None, None, [], True
        deployments = r.json().get("deployments", [])
        if not deployments:
            return None, None, None, None, [], False
        # Only monitor production-target deployments; staging previews are ignored
        prod = next((d for d in deployments if d.get("target") == "production"), None)
        deploying = False
        deploying_commit = None
        source_ok, source_mismatches = None, []
        if prod:
            deploying = prod.get("state") in _VERCEL_BUILDING
            deploying_meta = prod.get("meta") or {}
            deploying_source = prod.get("source", "") if deploying else ""
            deploying_commit = deploying_meta.get("githubCommitSha") if deploying else None
            source_ok, source_mismatches = _validate_deployment_source(deploying_source, deploying_meta) if deploying else (None, [])
        live_commit = None
        for d in deployments:
            if d.get("state") == "READY" and d.get("target") == "production":
                live_commit = (d.get("meta") or {}).get("githubCommitSha")
                break
        return deploying, live_commit, deploying_commit, source_ok, source_mismatches, False
    except Exception:
        return None, None, None, None, [], True


def _fetch_github_head(token: str) -> str | None:
    hdrs = {"Accept": "application/vnd.github.sha"}
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    try:
        r = http_requests.get(
            f"https://api.github.com/repos/{_GITHUB_REPO}/commits/{_GITHUB_BRANCH}",
            headers=hdrs, timeout=10,
        )
        return r.text.strip() if r.status_code == 200 else None
    except Exception:
        return None


def _fetch_monitor_hashes(token: str) -> dict | None:
    hdrs = {"Accept": "application/vnd.github+json"}
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    try:
        r = http_requests.get(
            f"https://api.github.com/repos/{_GITHUB_REPO}/git/trees/{_GITHUB_BRANCH}?recursive=1",
            headers=hdrs, timeout=10,
        )
        if r.status_code != 200:
            return None
        return {
            item["path"]: item["sha"]
            for item in r.json().get("tree", [])
            if item["path"] in _MONITOR_PATHS
        }
    except Exception:
        return None



app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
templates.env.filters["b64encode"] = lambda s: base64.b64encode(s.encode("utf-8")).decode("ascii") if isinstance(s, str) else base64.b64encode(s).decode("ascii")
templates.env.globals["deploy_sha"] = os.getenv("VERCEL_GIT_COMMIT_SHA", "")[:7]
_MD_ALLOWED_TAGS = ["p", "strong", "em", "ul", "ol", "li", "blockquote", "code", "pre", "br", "h1", "h2", "h3"]
templates.env.filters["md"] = lambda text: bleach.clean(
    _md.markdown(text or "", extensions=["nl2br"]),
    tags=_MD_ALLOWED_TAGS, strip=True
)

# In-memory store: session_id → {pdf: bytes, manifest: dict}
store: dict[str, dict] = {}
# Email sessions: session_id → list of email dicts
email_sessions: dict[str, list[dict]] = {}
# Uploaded .eml sessions: session_id → {raw, tree, warnings, outer_meta, ...}
eml_sessions: dict[str, dict] = {}
# Browser-session evidence receipts: receipt_id → receipt entry (no image bytes)
browser_session_receipts: dict[str, dict] = {}

SESSION_TTL = 3600  # seconds

def _evict_old_sessions() -> None:
    cutoff = time.time() - SESSION_TTL
    for d in (store, email_sessions, eml_sessions, browser_session_receipts):
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


_VERDICT_CATEGORY_COLORS = {
    "Strongly matches": ((209, 250, 229), (6, 95, 70)),
    "Mostly matches": ((220, 252, 231), (22, 101, 52)),
    "Mostly does not match": ((255, 237, 213), (154, 52, 18)),
    "Does not match": ((254, 226, 226), (153, 27, 27)),
}
_VERDICT_CATEGORY_DEFAULT_COLORS = ((254, 243, 199), (146, 64, 14))


def _category_colors(category: str) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    return _VERDICT_CATEGORY_COLORS.get(category, _VERDICT_CATEGORY_DEFAULT_COLORS)


def _pdf_text_height(pdf: "FPDF", w: float, line_h: float, text: str) -> float:
    return pdf.multi_cell(w, line_h, text, dry_run=True, output=MethodReturnValue.HEIGHT)


def build_verdict_pdf(
    question: str,
    passes: list[tuple[str, str]],
    timestamp: str,
    input_hash: str,
    prompts: list[tuple[str, str]] | None = None,
    source_context: dict | None = None,
    summary_verdict: str = "",
    verdict_category: str = "",
    verdict_prefix: str = "Document (with evaluation)",
    filename: str = "",
) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    page_w = pdf.w - pdf.l_margin - pdf.r_margin
    x0 = pdf.l_margin

    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(13, 110, 253)
    pdf.cell(0, 10, _safe("Leima"), ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(1)

    pdf.set_font("Helvetica", size=9)
    pdf.set_text_color(120, 120, 120)
    if filename:
        pdf.cell(0, 6, _safe(f"File: {filename}"), ln=True)
    pdf.cell(0, 6, f"Timestamp: {timestamp}", ln=True)
    pdf.cell(0, 6, f"Model: {MODEL}", ln=True)
    pdf.cell(0, 6, _safe(f"Commit: {os.getenv('VERCEL_GIT_COMMIT_SHA', 'unknown')}"), ln=True)
    pdf.cell(0, 6, _safe(f"Source: {_source_assessment_text(source_context)}"), ln=True)
    pdf.ln(3)
    pdf.set_text_color(0, 0, 0)

    # --- Claim / verdict header box — mirrors the ".verdict-header" card in the web UI ---
    pad = 4
    inner_w = page_w - 2 * pad
    y0 = pdf.get_y()

    label_h = 4
    pdf.set_font("Helvetica", "I", 10)
    claim_text = _safe(question)
    claim_h = _pdf_text_height(pdf, inner_w, 5, claim_text) or 5
    badge_h = 7 if verdict_category else 0
    summary_text = _safe(summary_verdict)
    pdf.set_font("Helvetica", "B", 12)
    summary_h = _pdf_text_height(pdf, inner_w, 6, summary_text) if summary_text else 0

    box_h = pad * 2 + label_h + 1 + claim_h + 2
    if badge_h:
        box_h += badge_h + 2
    box_h += summary_h

    pdf.set_fill_color(240, 245, 255)
    pdf.rect(x0, y0, page_w, box_h, style="F", round_corners=True, corner_radius=2)
    pdf.set_fill_color(13, 110, 253)
    pdf.rect(x0, y0, 1.2, box_h, style="F")

    cy = y0 + pad
    pdf.set_xy(x0 + pad, cy)
    pdf.set_font("Helvetica", "B", 7)
    pdf.set_text_color(160, 160, 160)
    pdf.cell(inner_w, label_h, _safe("CLAIM VERIFIED"))
    cy += label_h + 1

    pdf.set_xy(x0 + pad, cy)
    pdf.set_font("Helvetica", "I", 10)
    pdf.set_text_color(73, 80, 87)
    pdf.multi_cell(inner_w, 5, claim_text)
    cy += claim_h + 2

    if verdict_category:
        badge_text = f"{verdict_prefix}: {verdict_category}"
        if verdict_category != "Equally supports and contradicts":
            badge_text += " the claim"
        badge_text = _safe(badge_text)
        pdf.set_font("Helvetica", "B", 9)
        bg, fg = _category_colors(verdict_category)
        badge_w = pdf.get_string_width(badge_text) + 6
        pdf.set_fill_color(*bg)
        pdf.rect(x0 + pad, cy, badge_w, badge_h, style="F", round_corners=True, corner_radius=1)
        pdf.set_xy(x0 + pad, cy)
        pdf.set_text_color(*fg)
        pdf.cell(badge_w, badge_h, badge_text, align="C")
        cy += badge_h + 2

    if summary_text:
        pdf.set_xy(x0 + pad, cy)
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(33, 37, 41)
        pdf.multi_cell(inner_w, 6, summary_text)
        cy += summary_h

    pdf.set_xy(x0, y0 + box_h)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    # --- Analysis passes — last pass first (main answer), matching the web UI order ---
    ordered_passes = ([passes[-1]] + list(passes[:-1])) if passes else []
    for label, text in ordered_passes:
        y = pdf.get_y()
        pdf.set_draw_color(222, 226, 230)
        pdf.line(x0, y, x0 + page_w, y)
        pdf.ln(3)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(33, 37, 41)
        pdf.cell(0, 7, _safe(label), ln=True)
        pdf.set_font("Helvetica", size=11)
        pdf.set_text_color(0, 0, 0)
        html = _md.markdown(_safe(text or ""), extensions=["nl2br"])
        pdf.write_html(html)
        pdf.ln(4)

    # --- Hash block — mirrors the ".hash-block" panel in the web UI ---
    hash_pad = 3
    hash_inner_w = page_w - 2 * hash_pad
    hash_row_h = 4
    hash_box_h = hash_pad * 2 + hash_row_h * 2
    if pdf.get_y() + hash_box_h > pdf.page_break_trigger:
        pdf.add_page()
    hy0 = pdf.get_y()
    pdf.set_fill_color(248, 249, 250)
    pdf.set_draw_color(222, 226, 230)
    pdf.rect(x0, hy0, page_w, hash_box_h, style="DF", round_corners=True, corner_radius=2)
    hy = hy0 + hash_pad
    pdf.set_xy(x0 + hash_pad, hy)
    pdf.set_font("Helvetica", "B", 7)
    pdf.set_text_color(160, 160, 160)
    pdf.cell(hash_inner_w, hash_row_h, _safe("INPUT SHA-256"))
    hy += hash_row_h
    pdf.set_xy(x0 + hash_pad, hy)
    pdf.set_font("Courier", size=8)
    pdf.set_text_color(13, 110, 253)
    pdf.cell(hash_inner_w, hash_row_h, _safe(input_hash))
    pdf.set_xy(x0, hy0 + hash_box_h)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(8)

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
    input_hash: str,
    verdict_hash: str,
    verdict_formats: dict | None = None,
    source_index_sha256: str | None = None,
) -> dict:
    m = {
        "stamp_format_version": 1,
        "timestamp": timestamp,
        "commit": os.getenv("VERCEL_GIT_COMMIT_SHA", "unknown"),
        "input": f"sha256:{input_hash}",
        "verdict": f"sha256:{verdict_hash}",
    }
    if verdict_formats:
        m["verdict_formats"] = {fmt: f"sha256:{h}" for fmt, h in verdict_formats.items()}
    if source_index_sha256:
        m["source_index"] = f"sha256:{source_index_sha256}"
    return m


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


def _safe_get(url: str, **kwargs) -> tuple[http_requests.Response, str]:
    max_redirects = 10
    for _ in range(max_redirects):
        resp = http_requests.get(url, allow_redirects=False, **kwargs)
        if resp.is_redirect or resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("Location", "")
            if not location:
                return resp, url
            url = http_requests.compat.urljoin(url, location)
            _check_ssrf(url)
        else:
            return resp, url
    raise ValueError("Too many redirects or redirect loop")


_SOURCE_INDEX_FORMAT_VERSION = 1
_SOURCE_INDEX_PROCESSOR = "leima-html-v1"
_SOURCE_INDEX_NORMALIZER = "nfc-whitespace-v1"
_SOURCE_INDEX_CHUNKER = "sentence-500-v1"
_SOURCE_INDEX_MAX_CHARS = 30000


class _TextExtractor(_HTMLParser):
    _SKIP = frozenset(["script", "style", "noscript", "head", "svg", "math", "canvas", "template"])
    _BLOCK = frozenset(["p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "td", "th",
                        "blockquote", "pre", "section", "article", "main", "aside", "tr", "br"])

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self._cur: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip_depth += 1
        if self._skip_depth == 0 and tag in self._BLOCK:
            self._flush()

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip_depth > 0:
            self._skip_depth -= 1
        if self._skip_depth == 0 and tag in self._BLOCK:
            self._flush()

    def handle_data(self, data):
        if self._skip_depth == 0:
            self._cur.append(data)

    def _flush(self):
        t = re.sub(r"[ \t]+", " ", " ".join(self._cur)).strip()
        if t:
            self.blocks.append(t)
        self._cur = []

    def get_text(self) -> str:
        self._flush()
        return "\n\n".join(b for b in self.blocks if b.strip())


def _normalize_text_for_index(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


_SENT_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"“‘\(])")
_CHUNK_MAX = 500


def _chunk_text(text: str) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    raw: list[str] = []
    for para in paragraphs:
        if len(para) <= _CHUNK_MAX:
            raw.append(para)
            continue
        sentences = _SENT_BOUNDARY.split(para)
        cur = ""
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            if not cur:
                cur = sent
            elif len(cur) + 1 + len(sent) <= _CHUNK_MAX:
                cur += " " + sent
            else:
                raw.append(cur)
                cur = sent
        if cur:
            raw.append(cur)
    final: list[str] = []
    for chunk in raw:
        while len(chunk) > _CHUNK_MAX:
            cut = chunk.rfind(" ", 0, _CHUNK_MAX)
            if cut < 1:
                cut = _CHUNK_MAX
            final.append(chunk[:cut].strip())
            chunk = chunk[cut:].strip()
        if chunk:
            final.append(chunk)
    return [c for c in final if c.strip()]


def _build_source_index(requested_url: str, final_url: str, raw_html: str, fetched_at: str) -> tuple[dict, bytes]:
    extractor = _TextExtractor()
    try:
        extractor.feed(raw_html)
    except Exception:
        pass
    normalized = _normalize_text_for_index(extractor.get_text())
    truncated = len(normalized) > _SOURCE_INDEX_MAX_CHARS
    if truncated:
        cut = normalized.rfind(" ", 0, _SOURCE_INDEX_MAX_CHARS)
        normalized = normalized[:cut if cut > 0 else _SOURCE_INDEX_MAX_CHARS]
    full_sha = sha256(normalized.encode("utf-8"))
    chunks_text = _chunk_text(normalized)
    chunks = [{"seq": i, "sha256": sha256(c.encode("utf-8")), "chars": len(c)}
               for i, c in enumerate(chunks_text)]
    index = {
        "format_version": _SOURCE_INDEX_FORMAT_VERSION,
        "processor": _SOURCE_INDEX_PROCESSOR,
        "normalizer": _SOURCE_INDEX_NORMALIZER,
        "chunker": _SOURCE_INDEX_CHUNKER,
        "requested_url": requested_url,
        "final_url": final_url,
        "fetched_at": fetched_at,
        "content_mode": "server_html",
        "truncated": truncated,
        "full_text_sha256": full_sha,
        "total_chars": len(normalized),
        "chunk_count": len(chunks),
        "chunks": chunks,
    }
    index_bytes = json.dumps(index, ensure_ascii=False, indent=2).encode("utf-8")
    return index, index_bytes


def _compute_correspondence(original_index: dict, current_html: str) -> dict:
    for field, expected in [
        ("processor", _SOURCE_INDEX_PROCESSOR),
        ("normalizer", _SOURCE_INDEX_NORMALIZER),
        ("chunker", _SOURCE_INDEX_CHUNKER),
    ]:
        if original_index.get(field) != expected:
            return {"error": f"incompatible_{field}"}

    extractor = _TextExtractor()
    try:
        extractor.feed(current_html)
    except Exception:
        pass
    normalized = _normalize_text_for_index(extractor.get_text())
    truncated = len(normalized) > _SOURCE_INDEX_MAX_CHARS
    if truncated:
        cut = normalized.rfind(" ", 0, _SOURCE_INDEX_MAX_CHARS)
        normalized = normalized[:cut if cut > 0 else _SOURCE_INDEX_MAX_CHARS]
    current_full_sha = sha256(normalized.encode("utf-8"))
    original_full_sha = original_index.get("full_text_sha256", "")

    if current_full_sha == original_full_sha:
        return {
            "exact_match": True,
            "retained_pct": 100.0,
            "new_pct": 0.0,
            "order_changed": False,
            "current_chars": len(normalized),
            "original_chars": original_index.get("total_chars", 0),
            "current_truncated": truncated,
        }

    current_chunks_text = _chunk_text(normalized)
    current_chunk_shas = [sha256(c.encode("utf-8")) for c in current_chunks_text]
    current_chunk_chars = [len(c) for c in current_chunks_text]
    current_total_chars = sum(current_chunk_chars) or 1

    original_chunks = original_index.get("chunks", [])
    original_total_chars = sum(c["chars"] for c in original_chunks) or 1

    current_sha_pool: dict[str, int] = {}
    for h in current_chunk_shas:
        current_sha_pool[h] = current_sha_pool.get(h, 0) + 1

    matched_orig_chars = 0
    curr_positions_of_matched: list[int] = []
    curr_sha_idx: dict[str, list[int]] = {}
    for j, h in enumerate(current_chunk_shas):
        curr_sha_idx.setdefault(h, []).append(j)
    curr_used: dict[int, bool] = {}

    for orig_chunk in original_chunks:
        h = orig_chunk["sha256"]
        available = [p for p in curr_sha_idx.get(h, []) if not curr_used.get(p)]
        if available:
            p = available[0]
            curr_used[p] = True
            matched_orig_chars += orig_chunk["chars"]
            curr_positions_of_matched.append(p)

    orig_sha_pool: dict[str, int] = {}
    for c in original_chunks:
        orig_sha_pool[c["sha256"]] = orig_sha_pool.get(c["sha256"], 0) + 1

    matched_curr_chars = 0
    orig_pool2 = dict(orig_sha_pool)
    for h, chars in zip(current_chunk_shas, current_chunk_chars):
        if orig_pool2.get(h, 0) > 0:
            matched_curr_chars += chars
            orig_pool2[h] -= 1

    retained_pct = round(100 * matched_orig_chars / original_total_chars, 1)
    new_pct = round(100 * (current_total_chars - matched_curr_chars) / current_total_chars, 1)

    order_changed = False
    if len(curr_positions_of_matched) > 1:
        for k in range(1, len(curr_positions_of_matched)):
            if curr_positions_of_matched[k] < curr_positions_of_matched[k - 1]:
                order_changed = True
                break

    return {
        "exact_match": False,
        "retained_pct": retained_pct,
        "new_pct": new_pct,
        "order_changed": order_changed,
        "original_chunk_count": len(original_chunks),
        "current_chunk_count": len(current_chunks_text),
        "original_chars": original_total_chars,
        "current_chars": current_total_chars,
        "matched_chunks": len(curr_positions_of_matched),
        "current_truncated": truncated,
    }


def _fetch_webpage(url: str) -> tuple[bytes, str, str, str, str]:
    """Returns (input_bytes, page_text, final_url, fetched_at, raw_html)."""
    _check_ssrf(url)
    resp, final_url = _safe_get(url, timeout=20, headers={"User-Agent": "Leima/1.0"})
    resp.raise_for_status()
    raw_html = resp.text
    text = re.sub(r"<style[^>]*>.*?</style>", " ", raw_html, flags=re.S)
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())[:30000]
    fetched_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    input_bytes = _text_to_input_pdf(f"URL: {url}\nFetched: {fetched_at}\n\n{text}")
    return input_bytes, text, final_url, fetched_at, raw_html


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


# ── Android evidence reception ────────────────────────────────────────────────
#
# State machine:  integrity_ok | integrity_failed → stamped (reserved)
#
# "integrity_ok"     All file hashes verified, edits coordinates valid.
# "integrity_failed" Package arrived but one or more integrity checks failed.
# "rejected"         Structural problem or privacy violation; package not stored.
# "stamped"          Arweave stamp committed (not yet implemented).
#
# Images are never stored in memory — only the SHA-256 hash from manifest.files.
# URLs in the package are never fetched by the server.
# No AI analysis is triggered on receipt; that is a separate, user-initiated step.
# Receipts are evicted after SESSION_TTL alongside other session types.

@app.post("/api/evidence/browser-sessions")
async def receive_browser_session(request: Request, package: UploadFile = File(...)):
    received_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    receipt_id = uuid.uuid4().hex

    raw = await package.read()

    try:
        parsed = _parse_browser_session(raw)
    except ValueError as exc:
        return JSONResponse(
            {
                "receipt_id":  receipt_id,
                "received_at": received_at,
                "status":      "rejected",
                "error":       str(exc),
            },
            status_code=422,
        )

    status = "integrity_ok" if parsed.integrity.ok else "integrity_failed"
    integrity_summary = {
        "manifest_ok":  parsed.integrity.manifest_ok,
        "edits_ok":     parsed.integrity.edits_ok,
        "privacy_ok":   parsed.integrity.privacy_ok,
        "errors":       parsed.integrity.errors,
    }

    _evict_old_sessions()
    browser_session_receipts[receipt_id] = {
        "receipt_id":      receipt_id,
        "received_at":     received_at,
        "status":          status,
        "media_filename":  parsed.media_filename,
        "media_sha256":    parsed.media_sha256,
        "schema_version":  parsed.metadata.get("schemaVersion"),
        "app_version":     parsed.metadata.get("appVersion"),
        "integrity":       integrity_summary,
        "_stored_at":      time.time(),
        "_stamp":          None,  # filled when Arweave stamp is committed
    }

    return JSONResponse(
        {
            "receipt_id":     receipt_id,
            "received_at":    received_at,
            "status":         status,
            "media_filename": parsed.media_filename,
            "media_sha256":   parsed.media_sha256,
            "integrity":      integrity_summary,
        },
        status_code=200,
    )


@app.get("/api/evidence/browser-sessions/{receipt_id}")
async def get_browser_session_receipt(receipt_id: str):
    entry = browser_session_receipts.get(receipt_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Receipt not found or expired")
    return {k: v for k, v in entry.items() if not k.startswith("_")}


class TabTrackRequest(BaseModel):
    name: str


@app.post("/track-tab")
async def track_tab(body: TabTrackRequest):
    if body.name in _TAB_TRACK_NAMES:
        _kv_hincrby(_KV_TAB_CLICKS, body.name)
    return Response(status_code=204)


@app.get("/admin/tab-stats", response_class=HTMLResponse)
async def tab_stats(key: str = ""):
    admin_secret = os.getenv("ADMIN_SECRET", "")
    if not admin_secret or key != admin_secret:
        raise HTTPException(status_code=401)
    counts = _kv_hgetall(_KV_TAB_CLICKS)
    rows = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    total = sum(counts.values())
    body = "".join(
        f"<tr><td>{_html_escape(name)}</td><td style='text-align:right'>{n}</td></tr>"
        for name, n in rows
    ) or "<tr><td colspan='2'>No clicks recorded yet</td></tr>"
    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>Tab click stats</title>
<style>body{{font-family:system-ui,sans-serif;max-width:600px;margin:2rem auto;padding:0 1rem}}
table{{width:100%;border-collapse:collapse}} td,th{{padding:.4rem .6rem;border-bottom:1px solid #ddd}}
th{{text-align:left}}</style></head><body>
<h2>Tab click stats</h2><p>Total tracked clicks: {total}</p>
<table><tr><th>Tab</th><th style="text-align:right">Clicks</th></tr>{body}</table>
</body></html>"""
    return HTMLResponse(html)


@app.get("/version")
async def version():
    if _tread_cache is not None:
        cache = _tread_cache.copy()
    else:
        cache = _kv_get()
        if cache is None:
            try:
                # status.json is small and updates fast; status-log.jsonl is large and CDN-cached
                r = http_requests.get(
                    _PAGES_URL + "/status.json",
                    params={"t": int(time.time() // 30)},  # 30s cache-busting
                    timeout=8,
                )
                cache = r.json() if r.status_code == 200 else {}
            except Exception:
                cache = {}
            if cache:
                _kv_set(cache)
    github_token = os.getenv("GITHUB_DISPATCH_TOKEN") or os.getenv("GITHUB_TOKEN", "")
    return {
        "model": MODEL,
        "security_model": "1.0",
        "github_authed": bool(github_token),
        "tread": {
            "ok":                          cache.get("ok"),
            "checked_at":                  cache.get("checked_at") or cache.get("ts"),
            "tx":                          cache.get("tx"),
            "review_ok":                   cache.get("review_ok"),
            "review_stuck":                cache.get("review_stuck"),
            "review_consecutive_failures": cache.get("review_consecutive_failures", 0),
        },
    }


_KV_TREAD_CRON_LAST = "tread_cron_last_dispatch"
_TREAD_CRON_COOLDOWN = 50  # seconds — prevents double-firing from concurrent deployments

@app.get("/tread-cron")
async def tread_cron(request: Request):
    cron_secret = os.getenv("CRON_SECRET", "")
    if cron_secret:
        if request.headers.get("Authorization", "") != f"Bearer {cron_secret}":
            raise HTTPException(status_code=401)
    token = os.getenv("GITHUB_DISPATCH_TOKEN", "")
    if not token:
        return JSONResponse({"dispatched": False, "error": "no_token"}, status_code=500)

    # Preview/staging deployments skip dispatch — GHA cron (*/5 min) is sufficient there
    if os.getenv("VERCEL_ENV", "production") != "production":
        return {"dispatched": False, "reason": "non-production deployment"}

    # Rate limit: skip dispatch if another instance already dispatched within cooldown window
    last = _kv_get(_KV_TREAD_CRON_LAST)
    if last and time.time() - last.get("ts", 0) < _TREAD_CRON_COOLDOWN:
        return {"dispatched": False, "reason": "cooldown", "next_in": round(_TREAD_CRON_COOLDOWN - (time.time() - last["ts"]))}

    try:
        r = http_requests.post(
            f"https://api.github.com/repos/{_GITHUB_REPO}/actions/workflows/tread.yml/dispatches",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={"ref": _GITHUB_BRANCH},
            timeout=10,
        )
        if r.status_code == 204:
            _kv_set({"ts": time.time()}, _KV_TREAD_CRON_LAST, ttl=_TREAD_CRON_COOLDOWN + 10)
        return {"dispatched": r.status_code == 204}
    except Exception as e:
        return JSONResponse({"dispatched": False, "error": str(e)}, status_code=500)


@app.get("/tread-monitor")
async def tread_monitor():
    try:
        return await _tread_monitor_inner()
    except Exception as e:
        import traceback
        return JSONResponse({"ok": None, "error": "monitor_exception", "detail": str(e), "traceback": traceback.format_exc()[-500:], "cached_at": time.time()})


async def _tread_monitor_inner():
    token = os.getenv("GITHUB_DISPATCH_TOKEN") or os.getenv("GITHUB_TOKEN", "")
    now = time.time()

    # Return cached result if fresh, but always inject live deploy_incoming
    cached = _kv_get(_KV_MONITOR_CACHE)
    if cached and now - cached.get("cached_at", 0) < 10:
        incoming = _kv_get(_KV_DEPLOY_INCOMING)
        if incoming:
            cached = dict(cached)
            cached["deploy_incoming"] = True
            cached["deploy_incoming_sha"] = incoming.get("sha")
        return cached

    def _fetch_last_review_sha():
        if not token:
            return None
        try:
            r = http_requests.get(
                f"https://api.github.com/repos/{_GITHUB_REPO}/actions/workflows/code_review.yml/runs",
                params={"status": "completed", "conclusion": "success", "per_page": 1},
                headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                timeout=8,
            )
            if r.status_code == 200:
                runs = r.json().get("workflow_runs", [])
                return runs[0].get("head_sha") if runs else None
        except Exception:
            pass
        return None

    def _fetch_review_in_progress():
        if not token:
            return False
        try:
            r = http_requests.get(
                f"https://api.github.com/repos/{_GITHUB_REPO}/actions/workflows/code_review.yml/runs",
                params={"per_page": 1, "status": "in_progress"},
                headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                timeout=8,
            )
            return bool(r.status_code == 200 and r.json().get("workflow_runs"))
        except Exception:
            return None  # API error — distinguishable from False (no runs)

    def _check_deploy_authorized(sha):
        if not sha or not token:
            return None
        try:
            r = http_requests.get(
                f"https://api.github.com/repos/{_GITHUB_REPO}/actions/workflows/code_review.yml/runs",
                params={"head_sha": sha, "status": "completed", "conclusion": "success", "per_page": 1},
                headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                timeout=8,
            )
            if r.status_code == 200:
                return bool(r.json().get("workflow_runs"))
        except Exception:
            pass
        return None

    # Fetch git tree SHAs, Vercel deploy state, review status and deploy signal in parallel
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        f_hashes = ex.submit(_fetch_monitor_hashes, token)
        f_vercel = ex.submit(_fetch_vercel_state)
        f_review = ex.submit(_fetch_review_in_progress)
        f_last_review = ex.submit(_fetch_last_review_sha)
        f_incoming = ex.submit(_kv_get, _KV_DEPLOY_INCOMING)
        hashes = f_hashes.result()
        vercel_deploying, vercel_live_commit, deploying_commit, source_ok, source_mismatches, vercel_api_error = f_vercel.result()
        review_in_progress_raw = f_review.result()
        github_actions_error = review_in_progress_raw is None
        review_in_progress = bool(review_in_progress_raw)
        review_completed_sha = f_last_review.result()
        incoming_data = f_incoming.result()
        deploy_incoming = bool(incoming_data)
        deploy_incoming_sha = incoming_data.get("sha") if incoming_data else None

    # Tarkista deploymentin lähde ja code review
    unauthorized_deploy = False
    deployment_source_warning = source_mismatches if source_mismatches else []
    if vercel_deploying:
        if source_ok is False:
            # Deployment ei tule odotetusta GitHub-reposta/branchista
            unauthorized_deploy = True
        elif not deploying_commit:
            # Ei GitHub-integraatiota — tuntematon deploy
            unauthorized_deploy = True
        else:
            authorized = _check_deploy_authorized(deploying_commit)
            if authorized is False:
                unauthorized_deploy = True

    # Tarkista server-side Vercel system env -muuttujat (ei operaattorin asetettavissa)
    expected_org, expected_repo = _GITHUB_REPO.split("/")
    sys_env_checks = {
        "VERCEL_GIT_PROVIDER":    (os.getenv("VERCEL_GIT_PROVIDER", ""),    "github"),
        "VERCEL_GIT_REPO_OWNER":  (os.getenv("VERCEL_GIT_REPO_OWNER", ""),  expected_org),
        "VERCEL_GIT_REPO_SLUG":   (os.getenv("VERCEL_GIT_REPO_SLUG", ""),   expected_repo),
        "VERCEL_GIT_COMMIT_REF":  (os.getenv("VERCEL_GIT_COMMIT_REF", ""),  _GITHUB_BRANCH),
        "VERCEL_ENV":             (os.getenv("VERCEL_ENV", ""),              "production"),
    }
    sys_env_mismatches = {k: {"actual": actual, "expected": expected}
                          for k, (actual, expected) in sys_env_checks.items()
                          if actual != expected}

    if not hashes:
        result = {"ok": None, "error": "github_unreachable", "deploying": vercel_deploying, "unauthorized_deploy": unauthorized_deploy, "review_in_progress": review_in_progress, "review_completed_sha": review_completed_sha, "deploy_incoming": deploy_incoming, "deploy_incoming_sha": deploy_incoming_sha, "deployment_source_warning": deployment_source_warning, "sys_env_mismatches": sys_env_mismatches, "vercel_api_error": vercel_api_error, "github_actions_error": github_actions_error, "cached_at": now}
        _kv_set(result, _KV_MONITOR_CACHE, ttl=10)
        return result

    # Get or set baseline
    baseline = _kv_get(_KV_MONITOR_BASELINE)
    if baseline is None:
        _kv_set(hashes, _KV_MONITOR_BASELINE, ttl=3600)  # 1 hour
        result = {"ok": True, "changed": [], "baseline_set": True, "hashes": hashes, "deploying": vercel_deploying, "unauthorized_deploy": unauthorized_deploy, "review_in_progress": review_in_progress, "review_completed_sha": review_completed_sha, "deploy_incoming": deploy_incoming, "deploy_incoming_sha": deploy_incoming_sha, "deployment_source_warning": deployment_source_warning, "sys_env_mismatches": sys_env_mismatches, "vercel_api_error": vercel_api_error, "github_actions_error": github_actions_error, "cached_at": now}
    else:
        changed = [p for p, sha in hashes.items() if baseline.get(p) != sha]
        result = {"ok": len(changed) == 0, "changed": changed, "hashes": hashes, "deploying": vercel_deploying, "unauthorized_deploy": unauthorized_deploy, "review_in_progress": review_in_progress, "review_completed_sha": review_completed_sha, "deploy_incoming": deploy_incoming, "deploy_incoming_sha": deploy_incoming_sha, "deployment_source_warning": deployment_source_warning, "sys_env_mismatches": sys_env_mismatches, "vercel_api_error": vercel_api_error, "github_actions_error": github_actions_error, "cached_at": now}

    # Suppress mismatch alarm if a pre-deploy signal exists for the current/deploying commit
    pre_deploy_active = False
    if not result.get("ok"):
        for candidate in filter(None, [deploying_commit, vercel_live_commit]):
            if _kv_get(f"{_KV_PRE_DEPLOY_PREFIX}{candidate}"):
                pre_deploy_active = True
                break
    result["pre_deploy_active"] = pre_deploy_active

    _kv_set(result, _KV_MONITOR_CACHE, ttl=10)
    return result


def _validate_deploy_token(request: Request):
    token = os.getenv("PRE_DEPLOY_TOKEN", "")
    if not token or request.headers.get("Authorization", "") != f"Bearer {token}":
        raise HTTPException(status_code=401)

def _parse_sha(body: dict) -> str:
    sha = (body.get("sha") or "").strip()
    if not sha or len(sha) != 40 or not all(c in "0123456789abcdef" for c in sha):
        raise HTTPException(status_code=400, detail="Invalid sha")
    return sha

@app.post("/api/deploy-incoming")
async def api_deploy_incoming(request: Request):
    _validate_deploy_token(request)
    body = await request.json()
    sha = _parse_sha(body)
    _kv_set({"sha": sha, "ts": time.time()}, _KV_DEPLOY_INCOMING, ttl=_KV_DEPLOY_INCOMING_TTL)
    return {"ok": True, "sha": sha}

@app.post("/api/pre-deploy")
async def api_pre_deploy(request: Request):
    _validate_deploy_token(request)
    body = await request.json()
    sha = _parse_sha(body)
    _kv_set({"sha": sha, "ts": time.time()}, f"{_KV_PRE_DEPLOY_PREFIX}{sha}", ttl=_KV_PRE_DEPLOY_TTL)
    return {"ok": True, "sha": sha}



def _readme_intro() -> str:
    try:
        text = open(os.path.join(os.path.dirname(__file__), "README.md"), encoding="utf-8").read()
        intro = text.split("---")[0].strip()
        return _md.markdown(intro)
    except Exception as e:
        print(f"_readme_intro error: {e!r}")
        return ""


def _tread_intro() -> str:
    try:
        text = open(os.path.join(os.path.dirname(__file__), "TREAD.md"), encoding="utf-8").read()
        intro = text.split("---")[0].strip()
        paras = [p.strip() for p in intro.split("\n\n") if p.strip()
                 and not p.strip().startswith("#")
                 and not (p.strip().startswith("*") and p.strip().endswith("*"))]
        excerpt = "\n\n".join(paras[:2])
        return _md.markdown(excerpt)
    except Exception as e:
        print(f"_tread_intro error: {e!r}")
        return ""

def _proteus_intro() -> str:
    try:
        text = open(os.path.join(os.path.dirname(__file__), "PROTEUS.md"), encoding="utf-8").read()
        intro = text.split("---")[0].strip()
        return _md.markdown(intro)
    except Exception as e:
        print(f"_proteus_intro error: {e!r}")
        return ""

def _community_intro() -> str:
    try:
        text = open(os.path.join(os.path.dirname(__file__), "COMMUNITY.md"), encoding="utf-8").read()
        paras = [p.strip() for p in text.split("\n\n") if p.strip() and not p.strip().startswith("#")]
        excerpt = "\n\n".join(paras[:2])
        return _md.markdown(excerpt)
    except Exception as e:
        print(f"_community_intro error: {e!r}")
        return ""

def _md_intro(filename: str, label: str, n_paras: int = 2) -> str:
    try:
        text = open(os.path.join(os.path.dirname(__file__), filename), encoding="utf-8").read()
        paras = [p.strip() for p in text.split("\n\n") if p.strip() and p.strip() != "---" and not re.match(r"^#\s", p.strip())]
        selected, chars = [], 0
        for p in paras:
            selected.append(p)
            chars += len(p)
            if chars >= 300:
                break
        html = _md.markdown("\n\n".join(selected))
        html = re.sub(r"<h[1-6][^>]*>(.*?)</h[1-6]>", r"<strong>\1</strong>", html)
        return html.replace("<hr />", "").replace("<hr>", "")
    except Exception as e:
        print(f"_{label}_intro error: {e!r}")
        return ""

def _zkse_intro() -> str:
    return _md_intro("ZKSE.md", "zkse")

def _usecases_intro() -> str:
    return _md_intro("USECASES.md", "usecases")

_DOCS: dict[str, tuple[str, str]] = {
    "readme":     ("README.md",        "How it works"),
    "usecases":   ("USECASES.md",      "Use cases"),
    "security":   ("SECURITY_MODEL.md","Data policy"),
    "tread":      ("TREAD.md",         "TREAD — What is this?"),
    "community":  ("COMMUNITY.md",     "Open Source"),
    "zkse":       ("ZKSE.md",          "Zero-Knowledge Semantic Evaluation"),
    "policy":     ("POLICY.example.md","Data policy"),
    "inspection": ("INSPECTION.md",    "Inspection protocol"),
    "proteus":    ("PROTEUS.md",       "Proteus — Epistemic Privacy for LLM APIs"),
    "cost-of-safety":        ("COST-OF-SAFETY.md",        "The Cost of Safety? — A Four-Field Framework for AI Agent Ethics"),
    "turvallisuuden-hinta":  ("TURVALLISUUDEN-HINTA.md", "Optimaalinen turvattomuus? — nelikenttä tekoälyagenttien etiikalle"),
    "insurance-for-agents":  ("INSURANCE-FOR-AGENTS.md", "Insuring the Agent — A Decentralised Protocol for AI Agent Risk"),
}

# Reverse map: filename.md → /docs/slug (for rewriting internal links)
_DOC_LINKS: dict[str, str] = {
    filename: f"/docs/{slug}" for slug, (filename, _) in _DOCS.items()
}

def _fix_doc_links(html: str) -> str:
    """Rewrite .md hrefs to /docs/slug; add target=_blank to external links."""
    def replace(m: re.Match) -> str:
        href = m.group(1)
        if href in _DOC_LINKS:
            return f'href="{_DOC_LINKS[href]}"'
        if href.startswith("http://") or href.startswith("https://"):
            return f'href="{href}" target="_blank" rel="noopener"'
        return m.group(0)
    return re.sub(r'href="([^"]+)"', replace, html)

@app.get("/docs/{name}", response_class=HTMLResponse)
async def doc_page(request: Request, name: str):
    mapping = _DOCS.get(name)
    if not mapping:
        raise HTTPException(status_code=404)
    filename, title = mapping
    try:
        path = os.path.join(os.path.dirname(__file__), filename)
        text = open(path, encoding="utf-8").read()
        content = _md.markdown(text, extensions=["tables", "fenced_code", "nl2br", "toc"])
        content = _fix_doc_links(content)
    except FileNotFoundError:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("doc.html", {"request": request, "title": title, "content": content, "readme_intro": _readme_intro(), "tread_intro": _tread_intro(), "community_intro": _community_intro(), "proteus_intro": _proteus_intro()})


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "readme_intro": _readme_intro(), "tread_intro": _tread_intro(), "community_intro": _community_intro(), "proteus_intro": _proteus_intro(), "usecases_intro": _usecases_intro(), "zkse_intro": _zkse_intro()})


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


def _eml_meta(node) -> dict:
    return {
        "from": node.header_decoded("From"),
        "to": node.header_decoded("To"),
        "subject": node.header_decoded("Subject") or "(no subject)",
        "date": node.header("Date"),
        "message_id": node.header("Message-ID").strip(),
    }


def _eml_preview_context(request: Request, session_id: str, root, warnings: list[str], selected_path: str) -> dict:
    outer_dkim = email_eml.verify_dkim_raw(root.raw)
    outer_meta = _eml_meta(root)
    attachments = email_eml.list_attachments(root)

    selected = None
    if selected_path and selected_path != root.path:
        sel_node = email_eml.find_node(root, selected_path)
        if sel_node is not None:
            sel_meta = _eml_meta(sel_node)
            sel_dkim = email_eml.verify_dkim_raw(sel_node.raw)
            selected = {
                "path": selected_path,
                "meta": sel_meta,
                "dkim": sel_dkim,
                "aligned": email_eml.check_alignment(sel_dkim["signing_domain"], sel_meta["from"]),
            }

    body_source_node = email_eml.find_node(root, selected_path) if selected else root
    body_text, body_warnings = email_eml.get_body_text(body_source_node)
    quote_hint = email_eml.detect_quoted_forward(body_text)

    return {
        "request": request,
        "session_id": session_id,
        "outer_meta": outer_meta,
        "outer_dkim": outer_dkim,
        "outer_aligned": email_eml.check_alignment(outer_dkim["signing_domain"], outer_meta["from"]),
        "attachments": attachments,
        "body_text": body_text,
        "warnings": warnings + body_warnings,
        "quote_hint": quote_hint,
        "selected": selected,
        "selected_path": selected_path,
    }


@app.post("/upload-eml", response_class=HTMLResponse)
async def upload_eml(request: Request, eml_file: UploadFile = File(None)):
    if not eml_file or not eml_file.filename:
        return HTMLResponse('<p class="fetch-error">Please choose a .eml file.</p>')
    raw = await eml_file.read()
    if not raw:
        return HTMLResponse('<p class="fetch-error">The file is empty.</p>')
    if len(raw) > email_eml.MAX_EML_BYTES:
        return HTMLResponse('<p class="fetch-error">File too large (max 20 MB).</p>')
    try:
        root, warnings = email_eml.parse_mime(raw)
    except Exception:
        return HTMLResponse('<p class="fetch-error">Could not parse this file as an email (.eml).</p>')
    if not root.header_bytes.strip() or not (root.header("From") or root.header("Subject") or root.header("Date")):
        return HTMLResponse('<p class="fetch-error">No recognizable email headers found — is this really a .eml file?</p>')

    session_id = uuid.uuid4().hex
    _evict_old_sessions()
    eml_sessions[session_id] = {"raw": raw, "tree": root, "warnings": warnings, "_stored_at": time.time()}

    return templates.TemplateResponse(
        "partials/eml_preview.html",
        _eml_preview_context(request, session_id, root, warnings, selected_path=""),
    )


@app.get("/preview-eml-part/{session_id}/{path:path}", response_class=HTMLResponse)
async def preview_eml_part(request: Request, session_id: str, path: str):
    entry = eml_sessions.get(session_id)
    if not entry:
        return Response(status_code=404)
    root = entry["tree"]
    node = root if not path else email_eml.find_node(root, path)
    if node is None:
        return Response(status_code=404)
    return templates.TemplateResponse(
        "partials/eml_preview.html",
        _eml_preview_context(request, session_id, root, entry["warnings"], selected_path=path),
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
        content=entry["verdict_txt"],
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=verdict.txt"},
    )


@app.get("/download/{session_id}/verdict.html")
async def download_verdict_html(session_id: str):
    entry = store.get(session_id)
    if not entry:
        return Response(status_code=404)
    return Response(
        content=entry["verdict_html"],
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=verdict.html"},
    )


@app.get("/download/{session_id}/verdict.json")
async def download_verdict_json_file(session_id: str):
    entry = store.get(session_id)
    if not entry:
        return Response(status_code=404)
    return Response(
        content=entry["verdict_json"],
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
        return HTMLResponse(f'<p class="error">Arweave upload failed: {_html_escape(str(e))}</p>', status_code=503)

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
            "has_source_index": bool(entry.get("source_index")),
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


@app.get("/download/{session_id}/source-index.json")
async def download_source_index(session_id: str):
    entry = store.get(session_id)
    if not entry or not entry.get("source_index"):
        return Response(status_code=404)
    return Response(
        content=entry["source_index"],
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=source-index.json"},
    )


@app.get("/download/{session_id}/all.zip")
async def download_all_zip(session_id: str):
    entry = store.get(session_id)
    if not entry:
        return Response(status_code=404)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if entry.get("source"):
            zf.writestr(f"source.{entry.get('source_ext', 'pdf')}", entry["source"])
        if entry.get("pdf"):
            zf.writestr("verdict.pdf", entry["pdf"])
        zf.writestr(
            "verdict.txt",
            build_verdict_txt(entry["question"], entry["passes"], entry["timestamp"], entry["input_hash"]),
        )
        zf.writestr(
            "verdict.html",
            build_verdict_html_export(entry["question"], entry["passes"], entry["timestamp"], entry["input_hash"]),
        )
        zf.writestr(
            "verdict.json",
            build_verdict_json_export(entry["question"], entry["passes"], entry["timestamp"], entry["input_hash"]),
        )
        zf.writestr("manifest.json", json.dumps(entry["manifest"], indent=2, ensure_ascii=False))
        if entry.get("source_index"):
            zf.writestr("source-index.json", entry["source_index"])

    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=leima-stamp.zip"},
    )


@app.get("/verdict-fragment/{session_id}")
async def verdict_fragment(request: Request, session_id: str):
    entry = store.get(session_id)
    if not entry:
        return HTMLResponse('<div class="error">Result not found — it may have expired.</div>', status_code=404)
    return templates.TemplateResponse(
        "partials/answer.html",
        {
            "request": request,
            "passes": entry["passes"],
            "question": entry["question"],
            "summary_verdict": entry.get("summary_verdict", ""),
            "verdict_category": entry.get("verdict_category", ""),
            "verdict_prefix": "Document (with evaluation)",
            "filename": entry.get("input_label", "browser capture"),
            "input_hash": entry["input_hash"],
            "verdict_hash": entry.get("verdict_hash", ""),
            "session_id": session_id,
            "timestamp": entry["timestamp"],
            "tread_snap": _tread_cache,
            "irys_gateway": IRYS_GATEWAY,
            "c2pa": None,
            "web_search_queries": entry.get("web_search_queries", []),
        },
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
    source_expected = manifest.get("input", "").removeprefix("sha256:")
    results.append({
        "label": "Source PDF hash",
        "ok": source_actual == source_expected,
        "expected": source_expected,
        "actual": source_actual,
    })

    # 2. Verdict hash
    verdict_actual = sha256(verdict_bytes)
    verdict_expected = manifest.get("verdict", "").removeprefix("sha256:")
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


def _fetch_web_context(question: str) -> tuple[str, list[str]]:
    try:
        from neutral_witness import _get_client, MODEL
        client = _get_client()
        resp = client.models.generate_content(
            model=MODEL,
            contents=f'Search the web and find relevant factual context for evaluating this claim: "{question}". Summarize what authoritative sources say.',
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
        text = (resp.text or "").strip()
        queries: list[str] = []
        try:
            gm = resp.candidates[0].grounding_metadata
            if gm and gm.web_search_queries:
                queries = list(gm.web_search_queries)
        except Exception:
            pass
        return text, queries
    except Exception:
        return "", []


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
        "cryptographically_verified": False,
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

    resp, _ = _safe_get(url, timeout=30, stream=True)
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
                  source_context: dict | None = None,
                  verdict_prefix: str = "Document (with evaluation)",
                  source_index_bytes: bytes | None = None) -> dict:
    tread_snap = _tread_cache.copy() if _tread_cache else None

    result = analyse(question, contents, source_context=source_context)
    input_hash = sha256(input_bytes)
    verdict_pdf = build_verdict_pdf(
        question, result["passes"], result["timestamp"], input_hash,
        prompts=result["prompt_log"], source_context=source_context,
        summary_verdict=result["summary_verdict"],
        verdict_category=result.get("verdict_category", ""),
        verdict_prefix=verdict_prefix,
        filename=input_label,
    )
    verdict_hash = sha256(verdict_pdf)
    verdict_txt = build_verdict_txt(question, result["passes"], result["timestamp"], input_hash)
    verdict_html_bytes = build_verdict_html_export(question, result["passes"], result["timestamp"], input_hash)
    verdict_json_bytes = build_verdict_json_export(question, result["passes"], result["timestamp"], input_hash)
    source_index_hash = sha256(source_index_bytes) if source_index_bytes else None
    manifest = build_manifest(
        timestamp=result["timestamp"],
        input_hash=input_hash,
        verdict_hash=verdict_hash,
        verdict_formats={
            "pdf": verdict_hash,
            "txt": sha256(verdict_txt),
            "html": sha256(verdict_html_bytes),
            "json": sha256(verdict_json_bytes),
        },
        source_index_sha256=source_index_hash,
    )
    if tread_snap and tread_snap.get("tx"):
        manifest["tread"] = {
            "tx": tread_snap["tx"],
            "url": f"{IRYS_GATEWAY}/{tread_snap['tx']}",
            "checked_at": tread_snap.get("ts", ""),
            "commit": tread_snap.get("commit", ""),
            "ok": tread_snap.get("ok", False),
        }
    session_id = uuid.uuid4().hex
    _evict_old_sessions()
    store[session_id] = {
        "pdf": verdict_pdf, "manifest": manifest, "source": input_bytes,
        "source_ext": source_ext, "source_mime": source_mime,
        "passes": result["passes"], "question": question,
        "timestamp": result["timestamp"], "input_hash": input_hash,
        "verdict_hash": verdict_hash,
        "verdict_txt": verdict_txt,
        "verdict_html": verdict_html_bytes,
        "verdict_json": verdict_json_bytes,
        "summary_verdict": result["summary_verdict"],
        "verdict_category": result.get("verdict_category", ""),
        "input_label": input_label,
        "source_index": source_index_bytes,
        "web_search_queries": (source_context or {}).get("web_search_queries", []),
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
        "tread_snap": tread_snap,
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
    email_raw: str = Form(""),
    eml_session_id: str = Form(""),
    eml_part_path: str = Form(""),
    pdf_file: UploadFile = File(None),
    pdf_url: str = Form(""),
    web_url: str = Form(""),
    image_file: UploadFile = File(None),
    image_url: str = Form(""),
    assess_credibility: str = Form(""),
    gh_repo: str = Form(""),
    gh_ref: str = Form("main"),
    gh_token: str = Form(""),
    gh_paths: str = Form(""),
    review_mode: str = Form("claim"),
    rules_url: str = Form(""),
    bundle_manifests: list[UploadFile] = File([]),
    bundle_verdicts: list[UploadFile] = File([]),
    use_web_search: str = Form(""),
):
    if review_mode != "code_review" and not question.strip():
        return HTMLResponse('<div class="error">Please enter a claim.</div>')

    contents = []
    c2pa_info = None
    email_manifest_extra = None
    source_context = None
    source_ext = "pdf"
    source_mime = "application/pdf"
    source_index_bytes: bytes | None = None

    MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB

    if active_tab == "image":
        if image_url.strip():
            try:
                _check_ssrf(image_url.strip())
                resp, _ = _safe_get(image_url.strip(), timeout=20, stream=True)
                resp.raise_for_status()
                ct = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
                url_ext = image_url.strip().rsplit(".", 1)[-1].lower() if "." in image_url else ""
                mime = ct if ct in _IMAGE_MIMES.values() else _IMAGE_MIMES.get(url_ext)
                if not mime:
                    return HTMLResponse('<div class="error">URL does not point to a supported image format.</div>')
                chunks, total = [], 0
                for chunk in resp.iter_content(chunk_size=65536):
                    total += len(chunk)
                    if total > MAX_UPLOAD_BYTES:
                        return HTMLResponse('<div class="error">Image too large (max 20 MB).</div>')
                    chunks.append(chunk)
                input_bytes = b"".join(chunks)
            except ValueError as e:
                return HTMLResponse(f'<div class="error">{e}</div>')
            except Exception as e:
                return HTMLResponse(f'<div class="error">Could not fetch image: {e}</div>')
            c2pa_info = _check_c2pa(input_bytes, mime)
            input_label = image_url.strip()
            source_ext = url_ext or mime.split("/")[-1]
            source_mime = mime
        elif image_file and image_file.filename:
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
        else:
            return HTMLResponse('<div class="error">Please upload an image or enter a URL.</div>')
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
            input_bytes, page_text, fetched_url, fetched_at, raw_html = _fetch_webpage(web_url.strip())
        except Exception as e:
            return HTMLResponse(f'<div class="error">URL error: {e}</div>')
        _, source_index_bytes = _build_source_index(web_url.strip(), fetched_url, raw_html, fetched_at)
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
                rules_resp, _ = _safe_get(rules_url.strip(), timeout=15)
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

    elif active_tab == "email" and eml_session_id:
        _eml_entry = eml_sessions.get(eml_session_id)
        if not _eml_entry:
            return HTMLResponse('<div class="error">Uploaded email not found or expired. Please upload it again.</div>')
        root = _eml_entry["tree"]
        outer_raw = _eml_entry["raw"]
        node = root if not eml_part_path else email_eml.find_node(root, eml_part_path)
        if node is None:
            return HTMLResponse('<div class="error">Selected message part not found.</div>')

        outer_dkim = email_eml.verify_dkim_raw(outer_raw)
        forwarded_of = None
        excluded = []

        if eml_part_path and eml_part_path != root.path:
            # Selected an inner message/rfc822 part — verify it independently of the outer wrapper.
            sel_dkim = email_eml.verify_dkim_raw(node.raw)
            meta = _eml_meta(node)
            body_text, body_warnings = email_eml.get_body_text(node)
            dkim_for_analysis = sel_dkim
            forwarded_of = {"outer_dkim_status": outer_dkim["status"]}
            outer_attachments = email_eml.list_attachments(root)
            excluded.extend(
                f"{a['filename']} ({a['content_type']}, {a['size']} bytes)"
                for a in outer_attachments if a["path"] != node.path
            )
        else:
            meta = _eml_meta(root)
            body_text, body_warnings = email_eml.get_body_text(root)
            dkim_for_analysis = outer_dkim
            excluded.extend(
                f"{a['filename']} ({a['content_type']}, {a['size']} bytes)"
                for a in email_eml.list_attachments(root)
            )

        analysis_text = email_eml.build_analysis_text(
            meta, body_text, dkim_for_analysis, excluded,
            _eml_entry.get("warnings", []) + body_warnings, forwarded_of,
        )
        aligned = email_eml.check_alignment(dkim_for_analysis["signing_domain"], meta["from"])

        source_context = {
            "type": "email_eml_forwarded" if forwarded_of else "email_eml",
            "dkim_status": dkim_for_analysis["status"],
            "signing_domain": dkim_for_analysis["signing_domain"],
            "aligned": aligned,
            "body_length_limit": dkim_for_analysis["body_length_limit"],
            "outer_dkim_status": outer_dkim["status"] if forwarded_of else None,
            "sender_domain": meta["from"].split("@")[-1].rstrip(">").strip() if "@" in meta["from"] else "",
        }
        input_bytes = outer_raw
        input_label = "email-eml" + (f":{eml_part_path}" if forwarded_of else "")
        source_ext = "eml"
        source_mime = "message/rfc822"
        contents.append(analysis_text)

        email_manifest_extra = {
            "dkim": {
                "status": outer_dkim["status"],
                "signing_domain": outer_dkim["signing_domain"],
                "aligned": email_eml.check_alignment(outer_dkim["signing_domain"], _eml_meta(root)["from"]),
                "body_length_limit": outer_dkim["body_length_limit"],
            },
            "parser_version": email_eml.PARSER_VERSION,
            "scope": "headers + body analyzed; attachments not analyzed; content bound only via the original .eml hash",
            "checked_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        }
        if forwarded_of:
            email_manifest_extra["selected_part_path"] = eml_part_path
            email_manifest_extra["selected_part_sha256"] = sha256(node.raw)
            email_manifest_extra["selected_dkim"] = {
                "status": dkim_for_analysis["status"],
                "signing_domain": dkim_for_analysis["signing_domain"],
                "aligned": aligned,
                "body_length_limit": dkim_for_analysis["body_length_limit"],
            }
        email_manifest_extra["analyzed_text_sha256"] = sha256(analysis_text.encode())

    elif active_tab == "email":
        if email_raw.strip():
            try:
                body = base64.b64decode(email_raw.encode()).decode("utf-8")
            except Exception:
                body = email_raw
            msg = {"from": "", "to": "", "subject": "(email)", "date": "", "message_id": "", "dkim": "unknown", "body": body}
        else:
            _entry = email_sessions.get(email_session_id)
            msgs = _entry["messages"] if _entry else None
            if not msgs or not email_idx.isdigit() or int(email_idx) >= len(msgs):
                return HTMLResponse('<div class="error">No email selected.</div>')
            msg = msgs[int(email_idx)]
        body = msg["body"]
        body_hash = sha256(body.encode())
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

    elif active_tab == "bundle":
        manifest_uploads = [f for f in bundle_manifests if f and f.filename]
        verdict_uploads = [f for f in bundle_verdicts if f and f.filename]
        if len(manifest_uploads) < 2:
            return HTMLResponse('<div class="error">Add at least 2 stamp pairs to create a bundle.</div>')
        if len(manifest_uploads) > 10:
            return HTMLResponse('<div class="error">Maximum 10 stamps per bundle.</div>')
        if verdict_uploads and len(verdict_uploads) != len(manifest_uploads):
            return HTMLResponse('<div class="error">Upload a verdict.pdf for each manifest, or leave all verdict fields empty.</div>')
        stamps = []
        for i, mf in enumerate(manifest_uploads):
            try:
                raw = await mf.read()
                mdata = json.loads(raw)
            except Exception:
                return HTMLResponse(f'<div class="error">Could not read {_html_escape(mf.filename or "file")}: not valid JSON.</div>')
            if not isinstance(mdata, dict) or mdata.get("stamp_format_version") != 1:
                return HTMLResponse(f'<div class="error">{_html_escape(mf.filename or "file")} is not a valid Leima manifest.</div>')
            pdf_text = ""
            if i < len(verdict_uploads):
                vf = verdict_uploads[i]
                if vf and vf.filename:
                    try:
                        import io as _io
                        from pypdf import PdfReader
                        pdf_bytes = await vf.read()
                        reader = PdfReader(_io.BytesIO(pdf_bytes))
                        pdf_text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
                    except Exception:
                        pdf_text = ""
            stamps.append({
                "filename": mf.filename or "",
                "timestamp": mdata.get("timestamp", ""),
                "question": mdata.get("question", ""),
                "verdict_summary": mdata.get("verdict_summary", ""),
                "verdict_category": mdata.get("verdict_category", ""),
                "model": mdata.get("model", ""),
                "tx_id": mdata.get("stamp", {}).get("tx_id", "") if isinstance(mdata.get("stamp"), dict) else "",
                "pdf_text": pdf_text,
            })
        lines = ["Bundle of uploaded Leima stamps:\n"]
        for i, s in enumerate(stamps, 1):
            lines.append(f"Stamp {i} — {s['filename']}")
            if s["timestamp"]:
                lines.append(f"  Sealed at: {s['timestamp']}")
            if s["question"]:
                lines.append(f"  Verified claim: {s['question']}")
            if s["verdict_summary"]:
                lines.append(f"  Verdict summary: {s['verdict_summary']}")
            if s["verdict_category"]:
                lines.append(f"  Category: {s['verdict_category']}")
            if s["pdf_text"]:
                lines.append(f"  Full verdict:\n{s['pdf_text']}")
            lines.append("")
        bundle_text = "\n".join(lines)
        input_bytes = bundle_text.encode("utf-8")
        input_label = f"bundle:{len(stamps)}-stamps"
        source_context = {"type": "bundle", "count": len(stamps), "stamps": stamps}
        contents.append(bundle_text)

    elif active_tab == "claim":
        input_bytes = question.encode("utf-8")
        input_label = "claim-only"
        source_context = {"type": "claim_only"}
        source_ext = "txt"
        source_mime = "text/plain"
        # contents stays empty — question appended below by common code

    else:
        return HTMLResponse('<div class="error">Unknown input type.</div>')

    if question.strip():
        contents.append(question)

    if assess_credibility == "1_web":
        assess_credibility = "1"
        use_web_search = "1"

    if assess_credibility != "1":
        source_context = {"type": "content_only"}

    verdict_prefix = "Document (with evaluation)" if assess_credibility == "1" else "Document"

    if use_web_search == "1" and question.strip():
        web_ctx, web_queries = _fetch_web_context(question)
        if web_ctx:
            contents.append(f"Web search context:\n{web_ctx}")
            if source_context is None:
                source_context = {}
            source_context["web_search"] = True
            if web_queries:
                source_context["web_search_queries"] = web_queries

    try:
        result = _run_analysis(question, contents, input_bytes, input_label,
                               source_ext, source_mime,
                               source_context, verdict_prefix,
                               source_index_bytes=source_index_bytes)
    except ValueError as e:
        return HTMLResponse(f'<div class="error">{e}</div>')
    except Exception:
        return HTMLResponse('<div class="error">Analysis failed. Please try again.</div>')

    if active_tab == "image" and c2pa_info:
        store[result["session_id"]]["manifest"]["c2pa"] = c2pa_info

    if active_tab == "email" and email_manifest_extra:
        store[result["session_id"]]["manifest"]["email"] = email_manifest_extra

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
            "tread_snap": result.get("tread_snap"),
            "irys_gateway": IRYS_GATEWAY,
            "c2pa": c2pa_info if active_tab == "image" else None,
        },
    )


_CORRESPONDENCE_MAX_BYTES = 5 * 1024 * 1024  # 5 MB


@app.post("/check-correspondence", response_class=HTMLResponse)
async def check_correspondence(
    request: Request,
    manifest_file: UploadFile = File(...),
    source_index_file: UploadFile = File(...),
):
    if manifest_file.size and manifest_file.size > _CORRESPONDENCE_MAX_BYTES:
        return HTMLResponse('<p class="corr-error">manifest.json too large.</p>')
    if source_index_file.size and source_index_file.size > _CORRESPONDENCE_MAX_BYTES:
        return HTMLResponse('<p class="corr-error">source-index.json too large.</p>')

    manifest_bytes = await manifest_file.read()
    index_bytes = await source_index_file.read()

    try:
        manifest = json.loads(manifest_bytes)
    except Exception:
        return HTMLResponse('<p class="corr-error">manifest.json is not valid JSON.</p>')
    try:
        original_index = json.loads(index_bytes)
    except Exception:
        return HTMLResponse('<p class="corr-error">source-index.json is not valid JSON.</p>')

    # Verify format
    if original_index.get("format_version") != _SOURCE_INDEX_FORMAT_VERSION:
        return HTMLResponse('<p class="corr-error">source-index.json format version not supported.</p>')

    # Integrity: manifest must contain the source_index hash
    manifest_index_field = manifest.get("source_index", "")
    if not manifest_index_field:
        return templates.TemplateResponse(
            "partials/correspondence_result.html",
            {"request": request, "error": "no_index_in_manifest",
             "analysis_url": original_index.get("final_url", original_index.get("requested_url", ""))},
        )

    expected_hash = manifest_index_field.removeprefix("sha256:")
    actual_hash = sha256(index_bytes)
    if actual_hash != expected_hash:
        return templates.TemplateResponse(
            "partials/correspondence_result.html",
            {"request": request, "error": "index_hash_mismatch",
             "expected_hash": expected_hash, "actual_hash": actual_hash},
        )

    # Re-fetch current page
    target_url = original_index.get("final_url") or original_index.get("requested_url", "")
    if not target_url:
        return HTMLResponse('<p class="corr-error">No URL in source-index.json.</p>')

    try:
        resp, final_url = _safe_get(target_url, timeout=20, headers={"User-Agent": "Leima/1.0"})
        resp.raise_for_status()
        current_html = resp.text
        current_chars_preview = len(current_html)
    except Exception as e:
        return templates.TemplateResponse(
            "partials/correspondence_result.html",
            {"request": request, "error": "fetch_failed", "fetch_error": str(e),
             "target_url": target_url, "analysis_url": original_index.get("final_url", ""),
             "analysis_timestamp": manifest.get("timestamp", ""),
             "current_timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")},
        )

    checked_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    corr = _compute_correspondence(original_index, current_html)

    return templates.TemplateResponse(
        "partials/correspondence_result.html",
        {
            "request": request,
            "error": corr.get("error"),
            "analysis_url": original_index.get("final_url", original_index.get("requested_url", "")),
            "current_url": final_url,
            "analysis_timestamp": manifest.get("timestamp", ""),
            "checked_at": checked_at,
            "hash_ok": True,
            "exact_match": corr.get("exact_match", False),
            "retained_pct": corr.get("retained_pct"),
            "new_pct": corr.get("new_pct"),
            "order_changed": corr.get("order_changed", False),
            "original_chars": corr.get("original_chars", 0),
            "current_chars": corr.get("current_chars", 0),
            "current_truncated": corr.get("current_truncated", False),
            "original_truncated": original_index.get("truncated", False),
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
        rules_resp, _ = _safe_get(body.rules_url.strip(), timeout=15)
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
