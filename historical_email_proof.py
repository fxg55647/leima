"""Issuing side of the historical email personhood proof (plan sections 3-5, 7).

Given a raw .eml message and a locked HistoricalEmailPolicy, decides whether
the message qualifies and, if so, mints a signed JWS credential plus a
private disclosure secret. See docs/todo/HISTORICAL_EMAIL_PROOF_PLAN.md.
"""

from __future__ import annotations

import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from email.parser import BytesHeaderParser
from email.utils import parseaddr, parsedate_to_datetime

import dkim
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from historical_email_policy import (
    COMMITMENT_SCHEME,
    NORMALIZATION_VERSION,
    HistoricalEmailPolicy,
    b64url_decode,
    b64url_encode,
    compute_email_commitment,
    normalize_email,
)

CREDENTIAL_TYPE = "HistoricalEmailAttestation"
CREDENTIAL_VERSION = 1
ALLOWED_JWS_ALGORITHMS = ("EdDSA",)

_HEADER_PARSER = BytesHeaderParser()


class RejectedMessage(Exception):
    """Raised whenever a message or credential fails a check. `.reason` is
    meant to be logged, not necessarily shown verbatim to the end user."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass
class MessageCheckResult:
    recipient_email: str
    signed_date_utc: datetime
    signing_domain: str
    checks: dict[str, bool]


def _single_header(msg, name: str) -> str:
    values = msg.get_all(name) or []
    if len(values) != 1:
        raise RejectedMessage(f"expected exactly one {name!r} header, found {len(values)}")
    return values[0]


def _signed_header_names(signature_fields: dict) -> set[str]:
    raw = signature_fields.get(b"h", b"")
    return {h.strip().lower() for h in raw.decode("ascii", errors="replace").split(":") if h.strip()}


def check_message_fields(raw: bytes, policy: HistoricalEmailPolicy, dnsfunc=None) -> MessageCheckResult:
    """Plan section 5. Raises RejectedMessage on any failure; never silently
    downgrades a check (policy is all-or-nothing)."""

    msg = _HEADER_PARSER.parsebytes(raw)
    if len(msg.get_all("DKIM-Signature") or []) != 1:
        raise RejectedMessage("expected exactly one DKIM-Signature header")

    verify_kwargs = {}
    if dnsfunc is not None:
        verify_kwargs["dnsfunc"] = dnsfunc
    d = dkim.DKIM(raw)
    try:
        valid = d.verify(**verify_kwargs)
    except dkim.DKIMException as exc:
        raise RejectedMessage(f"DKIM verification error: {exc}") from exc
    if not valid:
        raise RejectedMessage("DKIM signature did not verify")

    domain = d.domain.decode("ascii", errors="replace") if isinstance(d.domain, bytes) else str(d.domain)
    if domain not in policy.allowed_dkim_signers:
        raise RejectedMessage(f"DKIM signing domain {domain!r} is not an approved signer for this policy")

    signature_fields = d.signature_fields or {}
    if b"l" in signature_fields:
        raise RejectedMessage("partial body signature (l= tag) is not accepted")

    signed_headers = _signed_header_names(signature_fields)
    missing = set(policy.required_signed_headers) - signed_headers
    if missing:
        raise RejectedMessage(f"required headers not covered by DKIM signature: {sorted(missing)}")

    to_header = _single_header(msg, "To")
    _, to_addr = parseaddr(to_header)
    if not to_addr:
        raise RejectedMessage("could not parse a single address out of the To header")
    try:
        recipient_email = normalize_email(to_addr)
    except ValueError as exc:
        raise RejectedMessage(str(exc)) from exc

    date_header = _single_header(msg, "Date")
    try:
        signed_date = parsedate_to_datetime(date_header)
    except (TypeError, ValueError) as exc:
        raise RejectedMessage(f"unparsable Date header: {exc}") from exc
    if signed_date.tzinfo is None:
        raise RejectedMessage("Date header has no timezone offset; cannot verify against cutoff")
    signed_date_utc = signed_date.astimezone(timezone.utc)
    if signed_date_utc >= policy.cutoff:
        raise RejectedMessage(f"signed date {signed_date_utc.isoformat()} is not before policy cutoff")

    checks = {
        "approvedDkimSigner": True,
        "signedRecipient": True,
        "signedDateBeforeCutoff": True,
    }
    return MessageCheckResult(
        recipient_email=recipient_email,
        signed_date_utc=signed_date_utc,
        signing_domain=domain,
        checks=checks,
    )


def _jws_header(kid: str) -> dict:
    return {"alg": "EdDSA", "typ": "JWT", "kid": kid}


def sign_jws(payload: dict, private_key: Ed25519PrivateKey, kid: str) -> str:
    header_b64 = b64url_encode(json.dumps(_jws_header(kid), sort_keys=True, separators=(",", ":")).encode("utf-8"))
    payload_b64 = b64url_encode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = private_key.sign(signing_input)
    return f"{header_b64}.{payload_b64}.{b64url_encode(signature)}"


def verify_jws(token: str, trusted_issuer_keys: dict[str, Ed25519PublicKey]) -> dict:
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
    except ValueError as exc:
        raise RejectedMessage("malformed credential (expected header.payload.signature)") from exc

    header = json.loads(b64url_decode(header_b64))
    if header.get("alg") not in ALLOWED_JWS_ALGORITHMS:
        raise RejectedMessage(f"unsupported JWS algorithm {header.get('alg')!r}")

    kid = header.get("kid")
    public_key = trusted_issuer_keys.get(kid)
    if public_key is None:
        raise RejectedMessage(f"unknown or untrusted issuer key id {kid!r}")

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    try:
        public_key.verify(b64url_decode(signature_b64), signing_input)
    except InvalidSignature as exc:
        raise RejectedMessage("credential signature does not verify") from exc

    return json.loads(b64url_decode(payload_b64))


@dataclass
class IssuedCredential:
    credential_jws: str
    disclosure_secret_b64: str
    recipient_email: str


def issue_credential(
    raw_email: bytes,
    policy: HistoricalEmailPolicy,
    issuer_id: str,
    issuer_kid: str,
    issuer_private_key: Ed25519PrivateKey,
    dnsfunc=None,
) -> IssuedCredential:
    """Plan section 3."""

    check = check_message_fields(raw_email, policy, dnsfunc=dnsfunc)

    secret = secrets.token_bytes(32)
    email_commitment = compute_email_commitment(check.recipient_email, secret)
    issued_at = datetime.now(timezone.utc)

    payload = {
        "type": CREDENTIAL_TYPE,
        "version": CREDENTIAL_VERSION,
        "issuer": issuer_id,
        "credentialId": str(uuid.uuid4()),
        "policyId": policy.policy_id,
        "policyDigest": policy.digest(),
        "cutoff": policy.cutoff.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "emailCommitment": email_commitment,
        "commitmentScheme": COMMITMENT_SCHEME,
        "normalization": NORMALIZATION_VERSION,
        "evidenceClass": policy.evidence_class,
        "checks": check.checks,
        "issuedAt": issued_at.isoformat().replace("+00:00", "Z"),
        "statusReference": "local-test:no-revocation-mechanism-yet",
    }
    credential_jws = sign_jws(payload, issuer_private_key, issuer_kid)
    return IssuedCredential(
        credential_jws=credential_jws,
        disclosure_secret_b64=b64url_encode(secret),
        recipient_email=check.recipient_email,
    )
