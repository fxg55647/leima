"""Receiving-service verification library for historical email attestations
(plan section 6). Deliberately does not import dkim/email_eml — a real
receiving party (e.g. Reddit) only ever handles the issued JWS + disclosure
package, never a raw .eml.
"""

from __future__ import annotations

import hmac

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from historical_email_policy import HistoricalEmailPolicy, compute_email_commitment, normalize_email
from historical_email_proof import (
    CREDENTIAL_TYPE,
    CREDENTIAL_VERSION,
    RejectedMessage,
    b64url_decode,
    verify_jws,
)

__all__ = ["RejectedMessage", "verify_attestation"]


def verify_attestation(
    credential_jws: str,
    disclosure_secret_b64: str,
    verified_recipient_email: str,
    policy: HistoricalEmailPolicy,
    trusted_issuer_keys: dict[str, Ed25519PublicKey],
) -> dict:
    """Plan section 6, steps 2-4. The caller is responsible for step 1 (resolving
    its own trusted, already-verified email for the logged-in account) and
    steps 5-6 (attaching the result to the account, revocation/staleness checks).

    Raises RejectedMessage with a reason on any failure. Returns the
    credential payload dict only when every check passes.
    """

    payload = verify_jws(credential_jws, trusted_issuer_keys)

    if payload.get("type") != CREDENTIAL_TYPE or payload.get("version") != CREDENTIAL_VERSION:
        raise RejectedMessage("unsupported credential type or version")

    if payload.get("policyId") != policy.policy_id or payload.get("policyDigest") != policy.digest():
        raise RejectedMessage("credential does not match the expected, locked policy")

    checks = payload.get("checks") or {}
    required = ("approvedDkimSigner", "signedRecipient", "signedDateBeforeCutoff")
    if not all(checks.get(name) is True for name in required):
        raise RejectedMessage("credential checks were not all satisfied")

    try:
        secret = b64url_decode(disclosure_secret_b64)
        own_normalized = normalize_email(verified_recipient_email)
        expected_commitment = compute_email_commitment(own_normalized, secret)
    except ValueError as exc:
        raise RejectedMessage(str(exc)) from exc

    credential_commitment = payload.get("emailCommitment", "")
    if not hmac.compare_digest(expected_commitment, credential_commitment):
        raise RejectedMessage("email commitment does not match this account's verified address")

    return payload
