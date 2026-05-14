import os
import hashlib
import uuid
import json
import imaplib
import dkim
import ipaddress
import email as email_lib
from email.header import decode_header as _decode_header
from datetime import datetime, timedelta
from urllib.parse import urlparse
from dotenv import load_dotenv
import re
import markdown as _md
import requests as http_requests
from fastapi import FastAPI, File, Form, UploadFile, Request
import base64
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from google.genai import types
from neutral_witness import analyse, PASS_LABELS, MODEL
from fpdf import FPDF
from irys_sdk import Builder
from irys_sdk.bundle.tags import from_dict as tags_from_dict

load_dotenv()

IRYS_PRIVATE_KEY = os.getenv("IRYS_PRIVATE_KEY")
IRYS_NETWORK = os.getenv("IRYS_NETWORK", "mainnet")
IRYS_RPC_URL = os.getenv("IRYS_RPC_URL")
IRYS_GATEWAY = "https://devnet.irys.xyz" if IRYS_NETWORK == "devnet" else "https://gateway.irys.xyz"

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
templates.env.filters["md"] = lambda text: _md.markdown(text or "", extensions=["nl2br"])

# In-memory store: session_id → {pdf: bytes, manifest: dict}
store: dict[str, dict] = {}
# Email sessions: session_id → list of email dicts
email_sessions: dict[str, list[dict]] = {}


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
    return known.get(domain, f"imap.{domain}")


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


def build_verdict_pdf(question: str, passes: list[tuple[str, str]], timestamp: str, input_hash: str, prompts: list[tuple[str, str]] | None = None) -> bytes:
    pdf = FPDF()
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, _safe("Stampd - verdict"), ln=True)
    pdf.ln(2)

    pdf.set_font("Helvetica", size=9)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 6, f"Timestamp: {timestamp}", ln=True)
    pdf.cell(0, 6, f"Model: {MODEL}", ln=True)
    pdf.cell(0, 6, _safe(f"Input hash (SHA-256): {input_hash}"), ln=True)
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
        html = _md.markdown(text or "", extensions=["nl2br"])
        pdf.write_html(html)

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
        "input": {"label": input_label, "sha256": input_hash},
        "verdict_pdf": {"sha256": verdict_hash},
    }
    if email_meta:
        manifest["email_meta"] = email_meta
    if web_meta:
        manifest["web"] = web_meta
    return manifest


def _fetch_webpage(url: str) -> tuple[bytes, str, str, str]:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http/https URLs are allowed")
    try:
        addr = ipaddress.ip_address(parsed.hostname)
        if addr.is_private or addr.is_loopback or addr.is_link_local:
            raise ValueError("Private/internal addresses are not allowed")
    except ValueError as e:
        if any(w in str(e) for w in ("Private", "internal", "loopback")):
            raise
    resp = http_requests.get(url, timeout=20, allow_redirects=True,
                             headers={"User-Agent": "Stampd/1.0"})
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


@app.get("/version")
async def version():
    return {
        "commit": os.getenv("RENDER_GIT_COMMIT", "unknown"),
        "service": os.getenv("RENDER_SERVICE_NAME", "local"),
        "model": MODEL,
    }


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/validate", response_class=HTMLResponse)
async def validate_page(request: Request):
    return templates.TemplateResponse("validate.html", {"request": request})


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
    try:
        imap = imaplib.IMAP4_SSL(_imap_server(email_user))
        imap.login(email_user, email_password)
        imap.select("INBOX")
        since = datetime.strptime(email_start, "%Y-%m-%d").strftime("%d-%b-%Y")
        before = (datetime.strptime(email_end, "%Y-%m-%d") + timedelta(days=1)).strftime("%d-%b-%Y")
        _, nums = imap.search(None, f'(FROM "{email_sender}" SINCE {since} BEFORE {before})')
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
        imap.logout()
    except Exception as e:
        return HTMLResponse(f'<p class="fetch-error">Connection failed: {e}</p>')

    if not messages:
        return HTMLResponse('<p class="fetch-error">No emails found for this period.</p>')

    session_id = str(uuid.uuid4())[:12]
    email_sessions[session_id] = messages

    return templates.TemplateResponse(
        "partials/email_results.html",
        {"request": request, "messages": messages, "session_id": session_id},
    )


@app.get("/preview-email/{session_id}/{idx}", response_class=HTMLResponse)
async def preview_email(request: Request, session_id: str, idx: int):
    messages = email_sessions.get(session_id)
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
        irys_tx = _irys_upload(record_bytes, "application/json", {"Stampd-Type": "stamp-record"})
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


@app.post("/validate", response_class=HTMLResponse)
async def validate(
    request: Request,
    source_file: UploadFile = File(...),
    verdict_file: UploadFile = File(...),
    manifest_file: UploadFile = File(...),
):
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
            base_manifest = {k: v for k, v in manifest.items() if k != "arweave"}
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
    all_tags = {"Content-Type": content_type, "App-Name": "Stampd", **tags}
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
        content = _md.markdown(text or "", extensions=["nl2br"])
        pass_html += f"<section><h2>{label}</h2>{content}</section>\n"
    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Stampd Verdict</title>
<style>
  body{{font-family:system-ui,sans-serif;max-width:720px;margin:2rem auto;padding:0 1rem;color:#212529}}
  h1{{font-size:1.4rem;margin-bottom:.25rem}} .meta{{color:#6c757d;font-size:.85rem;margin-bottom:1.5rem}}
  .claim{{background:#f0f5ff;border-left:3px solid #0d6efd;padding:.75rem 1rem;margin-bottom:1.5rem;font-weight:600}}
  section{{margin-bottom:2rem}} h2{{font-size:.75rem;text-transform:uppercase;letter-spacing:.07em;color:#adb5bd;margin-bottom:.5rem}}
  p{{margin:0 0 .6em;line-height:1.7}}
</style></head>
<body>
<h1>Stampd Verdict</h1>
<div class="meta">Timestamp: {timestamp} &nbsp;&middot;&nbsp; Model: {MODEL} &nbsp;&middot;&nbsp; Input SHA-256: {input_hash}</div>
<div class="claim">{question}</div>
{pass_html}</body></html>"""
    return html.encode("utf-8")


def build_verdict_json_export(question: str, passes: list[tuple[str, str]], timestamp: str, input_hash: str) -> bytes:
    return json.dumps({
        "claim": question, "timestamp": timestamp, "model": MODEL, "input_hash": input_hash,
        "passes": [{"label": l, "text": t} for l, t in passes],
    }, indent=2, ensure_ascii=False).encode()


PDF_URL_MAX_BYTES = 10 * 1024 * 1024  # 10 MB


def _fetch_pdf_from_url(url: str) -> tuple[bytes, str]:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http/https URLs are allowed")

    try:
        host = parsed.hostname
        addr = ipaddress.ip_address(host)
        if addr.is_private or addr.is_loopback or addr.is_link_local:
            raise ValueError("Private/internal addresses are not allowed")
    except ValueError as e:
        if "Private" in str(e) or "internal" in str(e) or "loopback" in str(e):
            raise
        pass  # hostname is not an IP — OK

    head = http_requests.head(url, timeout=10, allow_redirects=True)
    content_length = head.headers.get("Content-Length")
    if content_length and int(content_length) > PDF_URL_MAX_BYTES:
        raise ValueError(f"File too large (max {PDF_URL_MAX_BYTES // 1024 // 1024} MB)")

    resp = http_requests.get(url, timeout=30, allow_redirects=True, stream=True)
    resp.raise_for_status()

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
                  email_meta: dict | None = None, web_meta: dict | None = None) -> dict:
    result = analyse(question, contents, is_email=email_meta is not None)
    input_hash = sha256(input_bytes)
    verdict_pdf = build_verdict_pdf(question, result["passes"], result["timestamp"], input_hash, prompts=result["prompt_log"])
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
    session_id = str(uuid.uuid4())[:12]
    store[session_id] = {
        "pdf": verdict_pdf, "manifest": manifest, "source": input_bytes,
        "source_ext": source_ext, "source_mime": source_mime,
        "passes": result["passes"], "question": question,
        "timestamp": result["timestamp"], "input_hash": input_hash,
    }
    return {
        "passes": result["passes"],
        "summary_verdict": result["summary_verdict"],
        "timestamp": result["timestamp"],
        "input_hash": input_hash,
        "verdict_pdf": verdict_pdf,
        "verdict_hash": verdict_hash,
        "manifest": manifest,
        "session_id": session_id,
        "input_label": input_label,
    }


@app.post("/ask", response_class=HTMLResponse)
async def ask(
    request: Request,
    question: str = Form(...),
    active_tab: str = Form("pdf"),
    text_input: str = Form(""),
    email_session_id: str = Form(""),
    email_idx: str = Form(""),
    pdf_file: UploadFile = File(None),
    pdf_url: str = Form(""),
    web_url: str = Form(""),
    image_file: UploadFile = File(None),
):
    contents = []
    email_meta = None
    web_meta = None
    source_ext = "pdf"
    source_mime = "application/pdf"

    if active_tab == "image":
        if not image_file or not image_file.filename:
            return HTMLResponse('<div class="error">Please upload an image.</div>')
        mime = _detect_image_mime(image_file.filename)
        if not mime:
            return HTMLResponse('<div class="error">Unsupported image format. Use JPG, PNG, GIF, WebP, HEIC, or HEIF.</div>')
        input_bytes = await image_file.read()
        input_label = image_file.filename
        source_ext = image_file.filename.rsplit(".", 1)[-1].lower()
        source_mime = mime
        contents.append(types.Part.from_bytes(data=input_bytes, mime_type=mime))

    elif active_tab == "pdf":
        if pdf_url.strip():
            try:
                input_bytes, input_label = _fetch_pdf_from_url(pdf_url.strip())
            except Exception as e:
                return HTMLResponse(f'<div class="error">URL error: {e}</div>')
        elif pdf_file and pdf_file.filename:
            input_bytes = await pdf_file.read()
            input_label = pdf_file.filename
        else:
            return HTMLResponse('<div class="error">Please upload a PDF or enter a URL.</div>')
        contents.append(types.Part.from_bytes(data=input_bytes, mime_type="application/pdf"))

    elif active_tab == "text":
        if not text_input.strip():
            return HTMLResponse('<div class="error">Please paste some text.</div>')
        input_bytes = _text_to_input_pdf(text_input)
        input_label = "text-input"
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
        contents.append(f"Web page from: {fetched_url}\nFetched at: {fetched_at}\n\n{page_text}")

    elif active_tab == "email":
        msgs = email_sessions.get(email_session_id)
        if not msgs or not email_idx.isdigit() or int(email_idx) >= len(msgs):
            return HTMLResponse('<div class="error">No email selected.</div>')
        msg = msgs[int(email_idx)]
        body = msg["body"]
        body_hash = sha256(body.encode())
        email_meta = {
            "message_id": msg["message_id"],
            "from": msg["from"],
            "to": msg["to"],
            "date": msg["date"],
            "dkim": msg["dkim"],
            "body_sha256": body_hash,
        }
        input_bytes = _text_to_input_pdf(
            f"From: {msg['from']}\nTo: {msg['to']}\nSubject: {msg['subject']}\n"
            f"Date: {msg['date']}\nMessage-ID: {msg['message_id']}\n"
            f"DKIM: {msg['dkim']}\n"
            f"Body SHA-256: {body_hash}\n\n{body}"
        )
        input_label = f"email: {msg['subject'][:40]}"
        contents.append(f"Email from: {msg['from']}\nSubject: {msg['subject']}\nDate: {msg['date']}\n\n{body}")

    else:
        return HTMLResponse('<div class="error">Unknown input type.</div>')

    contents.append(question)

    try:
        result = _run_analysis(question, contents, input_bytes, input_label,
                               source_ext, source_mime,
                               email_meta, web_meta)
    except ValueError as e:
        return HTMLResponse(f'<div class="error">{e}</div>')

    return templates.TemplateResponse(
        "partials/answer.html",
        {
            "request": request,
            "passes": result["passes"],
            "question": question,
            "summary_verdict": result["summary_verdict"],
            "filename": result["input_label"],
            "input_hash": result["input_hash"],
            "verdict_hash": result["verdict_hash"],
            "session_id": result["session_id"],
            "timestamp": result["timestamp"],
        },
    )


class StampRequest(BaseModel):
    claim: str
    source_type: str  # "pdf_base64" | "pdf_url" | "text"
    source: str       # base64-encoded PDF, URL, or plain text


@app.post("/api/stamp")
async def api_stamp(body: StampRequest):
    claim = body.claim.strip()
    if not claim:
        return JSONResponse({"error": "claim is required"}, status_code=400)

    contents = []
    try:
        if body.source_type == "pdf_base64":
            input_bytes = base64.b64decode(body.source)
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

    manifest = result["manifest"]
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
    try:
        tx_id = _irys_upload(manifest_bytes, "application/json", {"Stampd-Type": "manifest"})
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
