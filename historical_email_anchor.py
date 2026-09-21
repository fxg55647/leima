"""Arweave anchoring for the historical email proof (plan section 9.4:
"integroidaan julkaisu, odottava/vahvistettu tila, uudelleenyritykset ja
tallennetun tietueen tarkistus").

Architecture decision (see docs/todo/W3C_VC_MIGRATION_PLAN.md sections 5-6 and
the user's standing Arweave policy): only a minimal SHA-256 digest of the
signed credential is published on-chain. The full JWS, with its issuer,
credentialId, policyId and other metadata, is delivered to the user privately
and never uploaded here. Anything beyond {digestAlgorithm, credentialDigest}
in the anchor payload needs separate sign-off before it is added.

Upload/fetch are injected rather than imported from main.py, so this module
has no dependency on the app's request/session state and stays testable
without network access.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Callable

from historical_email_policy import b64url_encode

ANCHOR_CONTENT_TYPE = "application/json"
ANCHOR_TAGS = {"Leima-Type": "historical-email-anchor"}

UploadFn = Callable[[bytes, str, dict], str]
FetchFn = Callable[[str], bytes]


class AnchorPublishError(Exception):
    def __init__(self, reason: str, retryable: bool = True):
        self.reason = reason
        self.retryable = retryable
        super().__init__(reason)


@dataclass
class AnchorResult:
    tx_id: str
    digest: str
    status: str  # "submitted" | "confirmed"
    gateway_url: str


def compute_credential_digest(credential_jws: str) -> str:
    """SHA-256 over the exact JWS compact string -- the only thing anchored on-chain."""
    return b64url_encode(hashlib.sha256(credential_jws.encode("ascii")).digest())


def _anchor_payload(digest: str) -> bytes:
    return json.dumps(
        {"digestAlgorithm": "sha256", "credentialDigest": digest},
        sort_keys=True,
    ).encode("utf-8")


def publish_anchor(
    credential_jws: str,
    upload_fn: UploadFn,
    gateway_base_url: str,
    max_attempts: int = 3,
    retry_delay_seconds: float = 2.0,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> AnchorResult:
    """Publishing the same credential twice yields the same digest; callers
    should persist tx_id once returned and not re-publish an already-submitted
    anchor just because a later step failed."""

    digest = compute_credential_digest(credential_jws)
    payload = _anchor_payload(digest)

    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            tx_id = upload_fn(payload, ANCHOR_CONTENT_TYPE, dict(ANCHOR_TAGS))
            return AnchorResult(
                tx_id=tx_id,
                digest=digest,
                status="submitted",
                gateway_url=f"{gateway_base_url.rstrip('/')}/{tx_id}",
            )
        except Exception as exc:
            last_error = exc
            if attempt < max_attempts:
                sleep_fn(retry_delay_seconds * attempt)
    raise AnchorPublishError(f"Arweave upload failed after {max_attempts} attempts: {last_error}")


def verify_anchor(
    tx_id: str,
    expected_digest: str,
    fetch_fn: FetchFn,
    gateway_base_url: str,
) -> AnchorResult:
    """A 200 from the gateway alone is not proof of anything; the stored bytes
    are parsed and the digest compared explicitly."""

    try:
        raw = fetch_fn(tx_id)
    except Exception as exc:
        raise AnchorPublishError(f"could not fetch anchor {tx_id!r}: {exc}", retryable=True) from exc

    try:
        stored = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise AnchorPublishError(f"anchor {tx_id!r} is not valid JSON: {exc}", retryable=False) from exc

    if stored.get("digestAlgorithm") != "sha256" or stored.get("credentialDigest") != expected_digest:
        raise AnchorPublishError(f"anchor {tx_id!r} content does not match expected digest", retryable=False)

    return AnchorResult(
        tx_id=tx_id,
        digest=expected_digest,
        status="confirmed",
        gateway_url=f"{gateway_base_url.rstrip('/')}/{tx_id}",
    )
