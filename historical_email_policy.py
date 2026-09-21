"""Policy schema, normalization, and base64url/JWS-encoding primitives for the
historical email personhood proof. See docs/todo/HISTORICAL_EMAIL_PROOF_PLAN.md.

This module has no dependency on dkimpy or email_eml — it is safe to import
from both the issuing side (historical_email_proof.py) and a standalone
verifying side (proof_verifier.py).
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone

NORMALIZATION_VERSION = "stampd-email-normalization-v1"
COMMITMENT_SCHEME = "stampd-email-v1"


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


@dataclass(frozen=True)
class HistoricalEmailPolicy:
    """A single locked policy version (plan section 7: "julkaistaan muuttumattomana versiona")."""

    policy_id: str
    policy_version: int
    evidence_class: str
    allowed_dkim_signers: tuple[str, ...]
    allowed_subjects: tuple[str, ...]
    cutoff: datetime  # tz-aware, compared in UTC
    human_verification_basis: str
    required_signed_headers: tuple[str, ...] = ("to", "date", "subject")

    def __post_init__(self) -> None:
        if self.cutoff.tzinfo is None:
            raise ValueError("policy cutoff must be timezone-aware")
        if not self.human_verification_basis.strip():
            raise ValueError(
                "human_verification_basis must document why this signer's own "
                "registration process implies human identity verification -- "
                "it cannot be empty (see signer_vetting.draft_human_verification_basis "
                "for an automated best-guess assessment)"
            )
        if not self.allowed_subjects:
            raise ValueError(
                "allowed_subjects must list the exact, boilerplate subject "
                "line(s) for the one vetted message class (plan section 9.1: "
                "'valitaan yksi hyväksyttävä viestiluokka') -- the same "
                "DKIM-approved sender can send other message classes (e.g. a "
                "generic 'thanks for contacting us' reply) that imply nothing "
                "about identity verification, so the signer domain alone is "
                "not sufficient"
            )
        if "subject" not in self.required_signed_headers:
            raise ValueError(
                "'subject' must be in required_signed_headers -- otherwise "
                "allowed_subjects could not be trusted (an unsigned Subject "
                "header can be changed after the fact without breaking DKIM)"
            )

    def canonical_bytes(self) -> bytes:
        payload = {
            "policyId": self.policy_id,
            "policyVersion": self.policy_version,
            "evidenceClass": self.evidence_class,
            "allowedDkimSigners": sorted(self.allowed_dkim_signers),
            "allowedSubjects": sorted(self.allowed_subjects),
            "cutoff": self.cutoff.astimezone(timezone.utc).isoformat(),
            "humanVerificationBasis": self.human_verification_basis,
            "requiredSignedHeaders": sorted(self.required_signed_headers),
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def digest(self) -> str:
        return b64url_encode(hashlib.sha256(self.canonical_bytes()).digest())


def normalize_email(address: str) -> str:
    """stampd-email-normalization-v1 (plan section 4).

    Lowercases only the domain part. Local part is left as-is (no case
    folding, no dot/plus stripping). Ambiguous or unsupported addresses are
    rejected outright rather than guessed at.
    """
    address = address.strip()
    if address.count("@") != 1:
        raise ValueError("unsupported address: must contain exactly one '@'")
    local, domain = address.split("@")
    if not local or not domain:
        raise ValueError("unsupported address: empty local or domain part")
    if any(ord(c) < 0x21 or c in "<>()[]\\," for c in local):
        raise ValueError("unsupported address: disallowed characters in local part")
    domain = domain.strip()
    if not domain.isascii():
        try:
            domain = domain.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise ValueError("unsupported address: invalid internationalized domain") from exc
    return f"{local}@{domain.lower()}"


def compute_email_commitment(normalized_email: str, secret: bytes) -> str:
    """SHA-256 binding of protocol id + normalized email + 32-byte secret (plan section 4).

    Length-prefixing (via null-byte separators, which cannot appear in a
    normalized address) keeps the encoding unambiguous.
    """
    if len(secret) != 32:
        raise ValueError("email binding secret must be exactly 32 bytes")
    data = COMMITMENT_SCHEME.encode("ascii") + b"\x00" + normalized_email.encode("utf-8") + b"\x00" + secret
    return b64url_encode(hashlib.sha256(data).digest())
