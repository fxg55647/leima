"""
notary.py — email notarization for Leima.

No AI. Verifies DKIM, hashes the raw email, stamps the manifest on Arweave,
and sends a notarized copy to the real recipient.
"""

import hashlib
import json
import imaplib
import smtplib
import dkim
import email as email_lib
from email.header import decode_header as _decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.message import MIMEMessage
from email import encoders
from email.utils import getaddresses
from datetime import datetime


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


def _extract_addresses(raw_header: str) -> list[str]:
    return [addr for _, addr in getaddresses([raw_header]) if addr]


def _verify_dkim(raw: bytes) -> str:
    try:
        return "valid" if dkim.verify(raw) else "invalid"
    except Exception:
        return "invalid"


def extract_meta(raw: bytes) -> dict:
    msg = email_lib.message_from_bytes(raw)
    return {
        "from": _decode_header_value(msg.get("From", "")),
        "to": _decode_header_value(msg.get("To", "")),
        "subject": _decode_header_value(msg.get("Subject", "(no subject)")),
        "date": msg.get("Date", ""),
        "message_id": (msg.get("Message-ID") or "").strip(),
        "dkim": _verify_dkim(raw) if "DKIM-Signature" in msg else "none",
        "email_sha256": hashlib.sha256(raw).hexdigest(),
    }


def build_manifest(meta: dict, timestamp: str) -> dict:
    return {"version": "1", "type": "email-notary", "timestamp": timestamp, **meta}


def _build_notarized_email(to: str, from_addr: str, original_raw: bytes, manifest: dict, gateway: str, leima_url: str = "") -> bytes:
    tx_id = manifest.get("stamp", {}).get("tx_id", "")
    arweave_url = f"{gateway}/{tx_id}" if tx_id else "(not stamped)"
    validate_url = f"{leima_url}/validate?tx={tx_id}" if tx_id and leima_url else ""

    outer = MIMEMultipart()
    outer["From"] = from_addr
    outer["To"] = to
    outer["Subject"] = f"[Leima] Notarisoitu: {manifest.get('subject', '')}"

    verify_line = f"Leima validator: {validate_url}\n" if validate_url else ""
    body = (
        "This email has been notarized by Leima.\n\n"
        f"From:    {manifest.get('from', '')}\n"
        f"To:      {manifest.get('to', '')}\n"
        f"Subject: {manifest.get('subject', '')}\n"
        f"Date:    {manifest.get('date', '')}\n"
        f"DKIM:    {manifest.get('dkim', '')}\n\n"
        f"SHA-256: {manifest.get('email_sha256', '')}\n"
        f"Arweave: {arweave_url}\n"
        f"{verify_line}"
        "\n"
        "--- How to verify ---\n\n"
        f"1. Download the notarization record from Arweave: {arweave_url}\n"
        f"2. Go to the Leima validator: {validate_url or leima_url + '/validate'}\n"
        "3. Upload the downloaded Arweave file together with the original.eml\n"
        "   attached to this email — the validator will confirm this email\n"
        "   and its attachments are authentic.\n\n"
        "You may also forward this email to anyone else at your discretion —\n"
        "they can perform the same verification using the same steps above.\n\n"
        "If Leima is unavailable, search for a compatible Leima validator\n"
        "to verify the record independently.\n"
        "\n---\nLeima — permanent digital notary\n"
    )
    outer.attach(MIMEText(body, "plain", "utf-8"))

    original_msg = email_lib.message_from_bytes(original_raw)
    eml_part = MIMEMessage(original_msg)
    eml_part.add_header("Content-Disposition", "attachment", filename="original.eml")
    outer.attach(eml_part)

    manifest_bytes = json.dumps(manifest, indent=2, ensure_ascii=False).encode()
    json_part = MIMEBase("application", "json")
    json_part.set_payload(manifest_bytes)
    encoders.encode_base64(json_part)
    json_part.add_header("Content-Disposition", "attachment", filename="manifest.json")
    outer.attach(json_part)

    return outer.as_bytes()


def _smtp_send(to: str, msg_bytes: bytes, smtp_host: str, smtp_port: int, smtp_user: str, smtp_password: str, from_addr: str) -> None:
    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(from_addr, [to], msg_bytes)


def poll_and_process(
    imap_host: str,
    imap_user: str,
    imap_password: str,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    notary_from: str,
    irys_upload_fn,
    gateway: str,
    leima_url: str = "",
) -> list[dict]:
    """Poll IMAP inbox for unseen messages, notarize each, and forward to the real recipient."""
    results = []
    imap = imaplib.IMAP4_SSL(imap_host)
    try:
        imap.login(imap_user, imap_password)
        imap.select("INBOX")
        _, nums = imap.search(None, "UNSEEN")

        for num in nums[0].split():
            result: dict = {"num": num.decode()}
            try:
                _, data = imap.fetch(num, "(RFC822)")
                raw = data[0][1]

                meta = extract_meta(raw)

                if meta["dkim"] != "valid":
                    result["error"] = f"DKIM {meta['dkim']} — message rejected"
                    results.append(result)
                    imap.store(num, "+FLAGS", "\\Seen")
                    continue

                msg_parsed = email_lib.message_from_bytes(raw)
                cc_addrs = _extract_addresses(msg_parsed.get("CC", ""))
                recipients = [
                    a for a in _extract_addresses(meta["to"]) + cc_addrs
                    if a.lower() != imap_user.lower()
                ]
                recipients = list(dict.fromkeys(recipients))

                if not recipients:
                    result["error"] = "No valid recipient in To:/CC: fields"
                    results.append(result)
                    imap.store(num, "+FLAGS", "\\Seen")
                    continue

                timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
                manifest = build_manifest(meta, timestamp)

                manifest_bytes = json.dumps(manifest, indent=2, ensure_ascii=False).encode()
                tx_id = irys_upload_fn(manifest_bytes, "application/json", {"Leima-Type": "email-notary"})
                manifest["stamp"] = {"tx_id": tx_id, "url": f"{gateway}/{tx_id}"}

                for to_addr in recipients:
                    msg_bytes = _build_notarized_email(to_addr, notary_from, raw, manifest, gateway, leima_url)
                    _smtp_send(to_addr, msg_bytes, smtp_host, smtp_port, smtp_user, smtp_password, notary_from)

                imap.store(num, "+FLAGS", "\\Seen")
                result.update({
                    "to": recipients,
                    "subject": meta["subject"],
                    "dkim": meta["dkim"],
                    "tx_id": tx_id,
                })

            except Exception as e:
                result["error"] = str(e)
                # Do not mark as Seen — leave UNSEEN so next poll retries

            results.append(result)
    finally:
        imap.logout()

    return results
