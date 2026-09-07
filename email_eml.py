"""
email_eml.py — parse an uploaded .eml file for the Leima email tab.

Preserves exact original bytes for hashing/DKIM by splitting MIME parts manually
(boundary scanning) instead of relying on the stdlib email package's semantic tree,
which may re-serialize headers/bodies when a sub-message is turned back into bytes.
The stdlib email package is still used, but only for decoding a single leaf part's
own header block (RFC 2047/2231, charset, transfer-encoding) — never to reconstruct
bytes that get hashed or DKIM-verified.
"""

from __future__ import annotations

import base64
import quopri
import re
from dataclasses import dataclass, field
from email.header import decode_header as _decode_header
from email.parser import BytesHeaderParser
from email.utils import parseaddr

import bleach
import dkim

MAX_EML_BYTES = 20 * 1024 * 1024
MAX_MIME_PARTS = 500
MAX_NESTING_DEPTH = 8
MAX_ANALYSIS_TEXT_CHARS = 200_000
PARSER_VERSION = "1"

_HEADER_PARSER = BytesHeaderParser()


def _decode_header_value(value) -> str:
    if not value:
        return ""
    parts = _decode_header(value)
    result = []
    for part, enc in parts:
        if isinstance(part, bytes):
            try:
                result.append(part.decode(enc or "utf-8", errors="replace"))
            except (LookupError, ValueError):
                result.append(part.decode("utf-8", errors="replace"))
        else:
            result.append(part)
    return " ".join(result)


@dataclass
class MimeNode:
    raw: bytes
    header_bytes: bytes
    body_bytes: bytes
    content_type: str
    params: dict
    disposition: str | None
    filename: str | None
    charset: str | None
    cte: str | None
    depth: int
    path: str
    is_message_rfc822: bool = False
    truncated: bool = False
    children: list["MimeNode"] = field(default_factory=list)
    decoded_bytes: bytes = b""

    def header(self, name: str) -> str:
        msg = _HEADER_PARSER.parsebytes(self.header_bytes)
        return msg.get(name, "") or ""

    def header_decoded(self, name: str) -> str:
        return _decode_header_value(self.header(name))


def _split_header_body(raw: bytes) -> tuple[bytes, bytes]:
    for sep in (b"\r\n\r\n", b"\n\n"):
        idx = raw.find(sep)
        if idx != -1:
            return raw[:idx], raw[idx + len(sep):]
    return raw, b""


def _decode_cte(body: bytes, cte: str | None) -> bytes:
    cte = (cte or "7bit").strip().lower()
    try:
        if cte == "base64":
            return base64.b64decode(body, validate=False)
        if cte == "quoted-printable":
            return quopri.decodestring(body)
    except Exception:
        return body
    return body


class _PartCounter:
    def __init__(self) -> None:
        self.count = 0


def parse_mime(raw: bytes) -> tuple[MimeNode, list[str]]:
    warnings: list[str] = []
    counter = _PartCounter()
    root = _parse_node(raw, depth=0, path="0", counter=counter, warnings=warnings)
    return root, warnings


def _parse_node(raw: bytes, depth: int, path: str, counter: _PartCounter, warnings: list[str]) -> MimeNode:
    counter.count += 1
    header_bytes, body_bytes = _split_header_body(raw)
    head_msg = _HEADER_PARSER.parsebytes(header_bytes)
    content_type = (head_msg.get_content_type() or "text/plain").lower()
    params = dict(head_msg.get_params(failobj=[]) or [])
    disposition = head_msg.get_content_disposition()
    filename = head_msg.get_filename()
    if filename:
        filename = _decode_header_value(filename)
    charset = head_msg.get_content_charset()
    cte = head_msg.get("Content-Transfer-Encoding", "7bit")

    node = MimeNode(
        raw=raw, header_bytes=header_bytes, body_bytes=body_bytes,
        content_type=content_type, params=params, disposition=disposition,
        filename=filename, charset=charset, cte=cte, depth=depth, path=path,
    )

    if counter.count > MAX_MIME_PARTS or depth > MAX_NESTING_DEPTH:
        node.truncated = True
        warnings.append(f"Parsing stopped at part {path}: too many parts or too deeply nested.")
        return node

    if content_type.startswith("multipart/"):
        boundary = params.get("boundary")
        if not boundary:
            warnings.append(f"Part {path}: multipart with no boundary parameter — treated as opaque.")
            node.decoded_bytes = body_bytes
            return node
        parts = _split_on_boundary(body_bytes, boundary.encode("utf-8", errors="replace"))
        if parts is None:
            warnings.append(f"Part {path}: could not locate MIME boundary markers.")
            node.decoded_bytes = body_bytes
            return node
        for i, part_raw in enumerate(parts):
            if counter.count > MAX_MIME_PARTS or depth + 1 > MAX_NESTING_DEPTH:
                node.truncated = True
                warnings.append(f"Parsing stopped inside part {path}: too many parts or too deeply nested.")
                break
            child = _parse_node(part_raw, depth + 1, f"{path}.{i}", counter, warnings)
            node.children.append(child)
        return node

    if content_type == "message/rfc822":
        inner_raw = _decode_cte(body_bytes, cte)
        node.is_message_rfc822 = True
        inner = _parse_node(inner_raw, depth + 1, f"{path}.0", counter, warnings)
        node.children.append(inner)
        return node

    node.decoded_bytes = _decode_cte(body_bytes, cte)
    return node


def _find_boundary(body: bytes, delim: bytes, start: int = 0) -> int:
    # RFC 2046: a boundary delimiter must begin at the start of a line.
    pos = start
    while True:
        idx = body.find(delim, pos)
        if idx == -1:
            return -1
        if idx == 0 or body[idx - 1:idx] == b"\n":
            return idx
        pos = idx + 1


def _split_on_boundary(body: bytes, boundary: bytes) -> list[bytes] | None:
    delim = b"--" + boundary
    idx = _find_boundary(body, delim)
    if idx == -1:
        return None
    segments: list[bytes] = []
    pos = idx
    while True:
        start = pos + len(delim)
        if body[start:start + 2] == b"--":
            break
        # skip the CRLF/LF right after the boundary line
        line_end = body.find(b"\n", start)
        if line_end == -1:
            break
        seg_start = line_end + 1
        next_idx = _find_boundary(body, delim, seg_start)
        if next_idx == -1:
            break
        seg = body[seg_start:next_idx]
        # strip the trailing CRLF/LF that precedes the next boundary marker
        if seg.endswith(b"\r\n"):
            seg = seg[:-2]
        elif seg.endswith(b"\n"):
            seg = seg[:-1]
        segments.append(seg)
        pos = next_idx
    return segments if segments else None


def find_node(root: MimeNode, path: str) -> MimeNode | None:
    if not path or path == root.path:
        return root
    target = path.split(".")
    cur = root
    while cur.path != path:
        found = None
        for child in cur.children:
            child_parts = child.path.split(".")
            if child_parts == target[:len(child_parts)]:
                found = child
                break
        if found is None:
            return None
        cur = found
    return cur


def decode_leaf_text(node: MimeNode) -> str:
    charset = node.charset or "utf-8"
    try:
        return node.decoded_bytes.decode(charset, errors="replace")
    except (LookupError, ValueError):
        return node.decoded_bytes.decode("utf-8", errors="replace")


_ALLOWED_HTML_TEXT_TAGS: list[str] = []


_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL)


def html_to_text(html_str: str) -> str:
    import html as _html_mod
    html_str = _SCRIPT_STYLE_RE.sub(" ", html_str or "")
    stripped = bleach.clean(html_str, tags=_ALLOWED_HTML_TEXT_TAGS, attributes={}, strip=True)
    text = _html_mod.unescape(stripped)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _walk(node: MimeNode):
    yield node
    for child in node.children:
        yield from _walk(child)


def get_body_node(root: MimeNode) -> MimeNode | None:
    """Prefer text/plain; fall back to text/html; else first text leaf found."""
    def find_alternative(n: MimeNode) -> MimeNode | None:
        if n.content_type == "multipart/alternative":
            return n
        for c in n.children:
            found = find_alternative(c)
            if found:
                return found
        return None

    alt = find_alternative(root)
    if alt:
        plain = next((c for c in alt.children if c.content_type == "text/plain"), None)
        if plain:
            return plain
        html_node = next((c for c in alt.children if c.content_type == "text/html"), None)
        if html_node:
            return html_node

    plain_leaf = None
    html_leaf = None
    for n in _walk(root):
        if n.is_message_rfc822 or n.children:
            continue
        if (n.disposition or "").lower() == "attachment":
            continue
        if n.content_type == "text/plain" and plain_leaf is None:
            plain_leaf = n
        elif n.content_type == "text/html" and html_leaf is None:
            html_leaf = n
    return plain_leaf or html_leaf


def get_body_text(root: MimeNode) -> tuple[str, list[str]]:
    warnings: list[str] = []
    node = get_body_node(root)
    if node is None:
        return "", ["No text/plain or text/html body part found."]
    text = decode_leaf_text(node)
    if node.content_type == "text/html":
        text = html_to_text(text)
        warnings.append("Body was HTML — text extracted and rendered active content stripped.")
    if len(text) > MAX_ANALYSIS_TEXT_CHARS:
        text = text[:MAX_ANALYSIS_TEXT_CHARS]
        warnings.append(f"Body text truncated at {MAX_ANALYSIS_TEXT_CHARS} characters for analysis.")
    return text, warnings


def _walk_skip_nested(node: MimeNode):
    """Like _walk, but does not descend into message/rfc822 children — a forwarded
    message is reported as one unit, not exploded into its own internal parts."""
    yield node
    if node.is_message_rfc822:
        return
    for child in node.children:
        yield from _walk_skip_nested(child)


def list_attachments(root: MimeNode) -> list[dict]:
    out = []
    body_node = get_body_node(root)
    for n in _walk_skip_nested(root):
        if n.path == root.path:
            continue
        if n.is_message_rfc822:
            inner = n.children[0] if n.children else None
            out.append({
                "path": inner.path if inner else n.path,
                "content_type": "message/rfc822",
                "filename": n.filename or (inner.header_decoded("Subject") if inner else "") or "(forwarded message)",
                "size": len(n.body_bytes),
                "is_nested_message": True,
                "inner_from": inner.header_decoded("From") if inner else "",
                "inner_subject": inner.header_decoded("Subject") if inner else "",
                "inner_date": inner.header("Date") if inner else "",
            })
            continue
        if n.content_type.startswith("multipart/"):
            continue
        if n is body_node:
            continue
        out.append({
            "path": n.path,
            "content_type": n.content_type,
            "filename": n.filename or "(unnamed)",
            "size": len(n.decoded_bytes),
            "is_nested_message": False,
            "inner_from": "", "inner_subject": "", "inner_date": "",
        })
    return out


_QUOTE_PATTERNS = [
    re.compile(r"^-{2,}\s*(Original Message|Forwarded [Mm]essage|Alkuper[äa]inen viesti)\s*-{2,}", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^On .{3,80} wrote:\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^(From|Lähettäjä):\s*.+$", re.IGNORECASE | re.MULTILINE),
]


def detect_quoted_forward(text: str) -> dict | None:
    if not text:
        return None
    for pat in _QUOTE_PATTERNS:
        m = pat.search(text)
        if m:
            return {"marker": m.group(0).strip(), "offset": m.start()}
    quote_lines = sum(1 for line in text.splitlines() if line.strip().startswith(">"))
    if quote_lines >= 3:
        return {"marker": "> quoted lines", "offset": None}
    return None


class _NullLogger:
    def debug(self, *a, **k):
        pass

    def info(self, *a, **k):
        pass

    def warning(self, *a, **k):
        pass

    def error(self, *a, **k):
        pass

    def isEnabledFor(self, *a, **k):
        return False


def verify_dkim_raw(raw: bytes) -> dict:
    header_bytes, _ = _split_header_body(raw)
    if b"dkim-signature" not in header_bytes.lower():
        return {"status": "none", "signing_domain": None, "auid": None,
                 "body_length_limit": None, "error": None}

    result = {"status": "invalid", "signing_domain": None, "auid": None,
              "body_length_limit": None, "error": None}
    try:
        d = dkim.DKIM(raw, logger=_NullLogger())
        ok = d.verify()
    except dkim.DKIMException as e:
        result["error"] = str(e)
        return result
    except Exception as e:
        return {"status": "check_error", "signing_domain": None, "auid": None,
                 "body_length_limit": None, "error": str(e)}

    result["status"] = "valid" if ok else "invalid"
    domain = getattr(d, "domain", None)
    if domain:
        result["signing_domain"] = domain.decode("utf-8", errors="replace") if isinstance(domain, bytes) else str(domain)
    sig = getattr(d, "signature_fields", None) or {}
    if b"l" in sig:
        try:
            result["body_length_limit"] = int(sig[b"l"])
        except (ValueError, TypeError):
            pass
    if b"i" in sig:
        auid = sig[b"i"]
        result["auid"] = auid.decode("utf-8", errors="replace") if isinstance(auid, bytes) else str(auid)
    return result


def check_alignment(signing_domain: str | None, from_header: str) -> bool | None:
    if not signing_domain or not from_header:
        return None
    _, addr = parseaddr(from_header)
    if "@" not in addr:
        return None
    from_domain = addr.rsplit("@", 1)[-1].lower().strip()
    signing_domain = signing_domain.lower().strip()
    return from_domain == signing_domain or from_domain.endswith("." + signing_domain)


def _dkim_summary(dkim_result: dict, from_header: str) -> str:
    status = dkim_result["status"]
    if status == "none":
        return "No DKIM signature present."
    if status == "check_error":
        return f"DKIM verification could not be performed ({dkim_result.get('error', 'unknown error')})."
    domain = dkim_result.get("signing_domain") or "unknown"
    aligned = check_alignment(dkim_result.get("signing_domain"), from_header)
    align_str = {
        True: "matches the From address domain",
        False: "does NOT match the From address domain",
        None: "alignment with the From address domain could not be determined",
    }[aligned]
    coverage = ""
    if dkim_result.get("body_length_limit") is not None:
        coverage = f" WARNING: only the first {dkim_result['body_length_limit']} bytes of the body were covered by the signature (l= tag) — content after that point is unsigned."
    verb = "verified" if status == "valid" else "present but failed verification"
    return f"DKIM signature {verb}, signing domain '{domain}' ({align_str}).{coverage}"


def build_analysis_text(
    meta: dict,
    body_text: str,
    dkim_result: dict,
    excluded: list[str],
    parse_warnings: list[str],
    forwarded_of: dict | None = None,
) -> str:
    lines = [
        "=== Message headers (as stated by the message; not independently verified except DKIM) ===",
        f"From: {meta.get('from', '')}",
        f"To: {meta.get('to', '')}",
        f"Subject: {meta.get('subject', '')}",
        f"Date: {meta.get('date', '')}",
        f"Message-ID: {meta.get('message_id', '')}",
        "",
        "=== Origin check (performed by Leima on the original uploaded bytes) ===",
        _dkim_summary(dkim_result, meta.get("from", "")),
    ]
    if forwarded_of:
        lines.append(
            "This message was selected from inside a forwarded/attached email (message/rfc822). "
            "Its DKIM result above is independent of the outer/forwarding message's DKIM result — "
            f"outer message DKIM: {forwarded_of.get('outer_dkim_status', 'unknown')}. "
            "A valid signature on the outer message does not verify this inner message's sender."
        )
    if parse_warnings:
        lines.append("")
        lines.append("=== Parsing notes ===")
        lines.extend(f"- {w}" for w in parse_warnings)
    if excluded:
        lines.append("")
        lines.append("=== Content excluded from analysis ===")
        lines.extend(f"- {e}" for e in excluded)
        lines.append(
            "Attachments are included in the original .eml file's hash but their content has not been analyzed."
        )
    lines.append("")
    lines.append("=== Message body ===")
    lines.append(body_text)
    return "\n".join(lines)
