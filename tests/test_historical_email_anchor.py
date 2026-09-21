"""Tests for the Arweave anchoring step of the historical email proof.

upload_fn/fetch_fn are fakes -- no network access, consistent with the
offline test boundary in conftest.py. These tests also guard the "hash-only"
Arweave policy: the anchor payload must never grow beyond {digestAlgorithm,
credentialDigest} without an explicit, separate decision.
"""

import json

import pytest

from historical_email_anchor import (
    AnchorPublishError,
    compute_credential_digest,
    publish_anchor,
    verify_anchor,
)

GATEWAY = "https://gateway.irys.xyz"
FAKE_JWS = "header.payload.signature"


def test_digest_is_deterministic():
    assert compute_credential_digest(FAKE_JWS) == compute_credential_digest(FAKE_JWS)


def test_digest_changes_with_credential():
    assert compute_credential_digest(FAKE_JWS) != compute_credential_digest(FAKE_JWS + "x")


def test_publish_anchor_payload_is_hash_only():
    captured = {}

    def upload_fn(data, content_type, tags):
        captured["data"] = data
        captured["content_type"] = content_type
        captured["tags"] = tags
        return "tx-123"

    result = publish_anchor(FAKE_JWS, upload_fn, GATEWAY)

    payload = json.loads(captured["data"])
    assert set(payload.keys()) == {"digestAlgorithm", "credentialDigest"}
    assert payload["credentialDigest"] == compute_credential_digest(FAKE_JWS)
    assert captured["content_type"] == "application/json"
    assert result.tx_id == "tx-123"
    assert result.status == "submitted"
    assert result.gateway_url == f"{GATEWAY}/tx-123"


def test_publish_anchor_retries_then_succeeds():
    attempts = []

    def upload_fn(data, content_type, tags):
        attempts.append(1)
        if len(attempts) < 3:
            raise RuntimeError("network blip")
        return "tx-after-retries"

    sleeps = []
    result = publish_anchor(FAKE_JWS, upload_fn, GATEWAY, max_attempts=3, sleep_fn=sleeps.append)

    assert result.tx_id == "tx-after-retries"
    assert len(attempts) == 3
    assert len(sleeps) == 2  # slept between attempts 1->2 and 2->3, not after the final success


def test_publish_anchor_raises_after_max_attempts():
    def upload_fn(data, content_type, tags):
        raise RuntimeError("permanently down")

    with pytest.raises(AnchorPublishError, match="permanently down"):
        publish_anchor(FAKE_JWS, upload_fn, GATEWAY, max_attempts=2, sleep_fn=lambda s: None)


def test_verify_anchor_success():
    digest = compute_credential_digest(FAKE_JWS)
    stored = json.dumps({"digestAlgorithm": "sha256", "credentialDigest": digest}).encode()

    result = verify_anchor("tx-1", digest, fetch_fn=lambda tx: stored, gateway_base_url=GATEWAY)

    assert result.status == "confirmed"
    assert result.digest == digest
    assert result.gateway_url == f"{GATEWAY}/tx-1"


def test_verify_anchor_rejects_digest_mismatch():
    digest = compute_credential_digest(FAKE_JWS)
    other_digest = compute_credential_digest(FAKE_JWS + "tampered")
    stored = json.dumps({"digestAlgorithm": "sha256", "credentialDigest": other_digest}).encode()

    with pytest.raises(AnchorPublishError, match="does not match"):
        verify_anchor("tx-1", digest, fetch_fn=lambda tx: stored, gateway_base_url=GATEWAY)


def test_verify_anchor_rejects_invalid_json():
    with pytest.raises(AnchorPublishError, match="not valid JSON"):
        verify_anchor("tx-1", "irrelevant", fetch_fn=lambda tx: b"not json", gateway_base_url=GATEWAY)


def test_verify_anchor_wraps_fetch_failure():
    def fetch_fn(tx):
        raise ConnectionError("gateway unreachable")

    with pytest.raises(AnchorPublishError, match="could not fetch"):
        verify_anchor("tx-1", "irrelevant", fetch_fn=fetch_fn, gateway_base_url=GATEWAY)
