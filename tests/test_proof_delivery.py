"""Tests for the proof export package and its user-requested email delivery."""

import json

import pytest

from proof_delivery import (
    DeliveryError,
    PACKAGE_FILENAME,
    build_proof_package,
    package_bytes,
    send_proof_email,
)

CREDENTIAL_JWS = "header.payload.signature"
SECRET_B64 = "c2VjcmV0LWJ5dGVz"
TX_ID = "tx-abc"
GATEWAY_URL = "https://gateway.irys.xyz/tx-abc"


def test_build_proof_package_shape():
    package = build_proof_package(CREDENTIAL_JWS, SECRET_B64, TX_ID)
    assert package == {
        "format": "stampd-proof-package-v1",
        "arweaveTxId": TX_ID,
        "signedCredential": CREDENTIAL_JWS,
        "disclosure": {"randomSecret": SECRET_B64},
    }


def test_package_bytes_round_trips_through_json():
    package = build_proof_package(CREDENTIAL_JWS, SECRET_B64, TX_ID)
    assert json.loads(package_bytes(package)) == package


def test_send_proof_email_happy_path():
    package = build_proof_package(CREDENTIAL_JWS, SECRET_B64, TX_ID)
    captured = {}

    def send_fn(to_addr, subject, body, attachment_bytes, filename):
        captured.update(to=to_addr, subject=subject, body=body, attachment=attachment_bytes, filename=filename)

    send_proof_email(package, "alice@example.com", "alice@example.com", send_fn, GATEWAY_URL)

    assert captured["to"] == "alice@example.com"
    assert captured["filename"] == PACKAGE_FILENAME
    assert json.loads(captured["attachment"]) == package
    assert GATEWAY_URL in captured["body"]


def test_send_proof_email_rejects_mismatched_recipient():
    package = build_proof_package(CREDENTIAL_JWS, SECRET_B64, TX_ID)

    def send_fn(*args):
        raise AssertionError("send_fn must not be called when recipients differ")

    with pytest.raises(DeliveryError, match="own recipient address"):
        send_proof_email(package, "alice@example.com", "mallory@example.com", send_fn, GATEWAY_URL)


def test_send_proof_email_wraps_send_failure():
    package = build_proof_package(CREDENTIAL_JWS, SECRET_B64, TX_ID)

    def send_fn(*args):
        raise ConnectionError("smtp down")

    with pytest.raises(DeliveryError, match="email delivery failed"):
        send_proof_email(package, "alice@example.com", "alice@example.com", send_fn, GATEWAY_URL)
