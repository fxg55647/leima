import os
import hashlib
import uuid
import json
import imaplib
import email as email_lib
from email.header import decode_header as _decode_header
from datetime import datetime, timedelta
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, UploadFile, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from google import genai
from google.genai import types
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
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

MODEL = "gemini-2.5-flash-lite"

SYSTEM_PROMPT = """You are a document analyst for Stampd, a legal evidence tool.

You ONLY analyse documents related to economic activity. Accepted topics:
- Employment: contracts, salary, dismissals, warnings, references
- Entrepreneurship: invoices, business agreements, company ownership
- Job seeking: applications, offers, rejections
- Loans & debt: loan agreements, payment plans, debt collection
- Insurance: work-related or business insurance policies
- Social benefits: unemployment, sick pay, Kela decisions
- Taxation: tax cards, tax decisions, advance tax
- Investments & ownership: shares, shareholder agreements
- Real estate: rental agreements, purchase contracts
- Education: employer-funded training, professional certifications
- Any contract or agreement with financial or legal consequences

If the document or email is NOT related to any of the above, respond with exactly:
REJECTED: This document does not relate to economic activity and cannot be stamped.

Otherwise, answer the user's question thoroughly and objectively based solely on the document content."""

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


def build_verdict_pdf(question: str, answer: str, timestamp: str, input_hash: str) -> bytes:
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
    pdf.cell(0, 7, "Question:", ln=True)
    pdf.set_font("Helvetica", size=11)
    pdf.multi_cell(0, 6, _safe(question))
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Answer:", ln=True)
    pdf.set_font("Helvetica", size=11)
    pdf.multi_cell(0, 6, _safe(answer))

    return bytes(pdf.output())


def build_manifest(
    timestamp: str,
    model: str,
    input_label: str,
    input_hash: str,
    verdict_hash: str,
    irys_tx: str | None = None,
    email_meta: dict | None = None,
) -> dict:
    manifest = {
        "version": "1",
        "timestamp": timestamp,
        "model": model,
        "input": {"label": input_label, "sha256": input_hash},
        "verdict_pdf": {"sha256": verdict_hash},
        "irys": {"tx_id": irys_tx, "url": f"{IRYS_GATEWAY}/{irys_tx}" if irys_tx else None},
    }
    if email_meta:
        manifest["email_meta"] = email_meta
    return manifest


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


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
            msg = email_lib.message_from_bytes(data[0][1])
            body = _get_body(msg)
            messages.append({
                "subject": _decode_header_value(msg["Subject"]) or "(no subject)",
                "date": msg["Date"] or "",
                "from": _decode_header_value(msg["From"]),
                "to": _decode_header_value(msg.get("To") or ""),
                "message_id": (msg.get("Message-ID") or "").strip(),
                "has_dkim": "DKIM-Signature" in msg,
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


def _irys_upload(data: bytes, content_type: str, tags: dict) -> str:
    builder = Builder("ethereum").wallet(IRYS_PRIVATE_KEY).network(IRYS_NETWORK)
    if IRYS_RPC_URL:
        builder = builder.rpc_url(IRYS_RPC_URL)
    uploader = builder.build()
    all_tags = {"Content-Type": content_type, "App-Name": "Stampd", **tags}
    result = uploader.upload(bytearray(data), tags_from_dict(all_tags))
    return result["id"]


@app.post("/stamp/{session_id}", response_class=HTMLResponse)
async def stamp(request: Request, session_id: str):
    entry = store.get(session_id)
    if not entry:
        return Response(status_code=404)

    try:
        verdict_tx = _irys_upload(
            entry["pdf"],
            "application/pdf",
            {"Stampd-Type": "verdict"},
        )

        entry["manifest"]["irys"]["tx_id"] = verdict_tx
        entry["manifest"]["irys"]["url"] = f"{IRYS_GATEWAY}/{verdict_tx}"

        manifest_bytes = json.dumps(entry["manifest"], indent=2, ensure_ascii=False).encode()
        manifest_tx = _irys_upload(
            manifest_bytes,
            "application/json",
            {"Stampd-Type": "manifest", "Stampd-Verdict-TX": verdict_tx},
        )
    except Exception as e:
        return HTMLResponse(f'<p class="stamp-error">Upload failed: {e}</p>')

    return templates.TemplateResponse(
        "partials/stamp_result.html",
        {
            "request": request,
            "verdict_tx": verdict_tx,
            "manifest_tx": manifest_tx,
            "verdict_url": f"{IRYS_GATEWAY}/{verdict_tx}",
            "manifest_url": f"{IRYS_GATEWAY}/{manifest_tx}",
        },
    )


def _text_to_input_pdf(text: str) -> bytes:
    p = FPDF()
    p.add_page()
    p.set_font("Helvetica", size=11)
    p.multi_cell(0, 6, _safe(text))
    return bytes(p.output())


@app.post("/ask", response_class=HTMLResponse)
async def ask(
    request: Request,
    question: str = Form(...),
    active_tab: str = Form("pdf"),
    text_input: str = Form(""),
    email_session_id: str = Form(""),
    email_idx: str = Form(""),
    pdf_file: UploadFile = File(None),
):
    contents = []
    email_meta = None

    if active_tab == "pdf":
        if not (pdf_file and pdf_file.filename):
            return HTMLResponse('<div class="error">Please upload a PDF file.</div>')
        input_bytes = await pdf_file.read()
        input_label = pdf_file.filename
        contents.append(types.Part.from_bytes(data=input_bytes, mime_type="application/pdf"))

    elif active_tab == "text":
        if not text_input.strip():
            return HTMLResponse('<div class="error">Please paste some text.</div>')
        input_bytes = _text_to_input_pdf(text_input)
        input_label = "text-input"
        contents.append(f"Document content:\n{text_input}")

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
            "has_dkim": msg["has_dkim"],
            "body_sha256": body_hash,
        }
        input_bytes = _text_to_input_pdf(
            f"From: {msg['from']}\nTo: {msg['to']}\nSubject: {msg['subject']}\n"
            f"Date: {msg['date']}\nMessage-ID: {msg['message_id']}\n"
            f"DKIM: {'yes' if msg['has_dkim'] else 'no'}\n"
            f"Body SHA-256: {body_hash}\n\n{body}"
        )
        input_label = f"email: {msg['subject'][:40]}"
        contents.append(f"Email from: {msg['from']}\nSubject: {msg['subject']}\nDate: {msg['date']}\n\n{body}")

    else:
        return HTMLResponse('<div class="error">Unknown input type.</div>')

    contents.append(question)

    response = client.models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
    )
    answer = response.text

    if answer.startswith("REJECTED:"):
        return HTMLResponse(f'<div class="error">{answer}</div>')

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    input_hash = sha256(input_bytes)

    verdict_pdf = build_verdict_pdf(question, answer, timestamp, input_hash)
    verdict_hash = sha256(verdict_pdf)

    manifest = build_manifest(
        timestamp=timestamp,
        model=MODEL,
        input_label=input_label,
        input_hash=input_hash,
        verdict_hash=verdict_hash,
        email_meta=email_meta if active_tab == "email" else None,
    )

    session_id = str(uuid.uuid4())[:12]
    store[session_id] = {"pdf": verdict_pdf, "manifest": manifest}

    return templates.TemplateResponse(
        "partials/answer.html",
        {
            "request": request,
            "answer": answer,
            "filename": input_label,
            "input_hash": input_hash,
            "verdict_hash": verdict_hash,
            "session_id": session_id,
            "timestamp": timestamp,
        },
    )
