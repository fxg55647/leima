"""Endpoint tests for the historical email proof demo routes in main.py.

DKIM/DNS verification itself is already covered at the unit level in
test_historical_email_proof.py with an injected dnsfunc. The demo policy's
signing domain ("stampd-demo.example") has no real DNS record, so it cannot
be exercised end-to-end here without a real domain -- these tests instead
monkeypatch check_message_fields (as conftest's `stamped` fixture does for
`analyse`/`_irys_upload`) to test the endpoint plumbing: sessions, error
handling, issuance, anchoring, download and email delivery.
"""

from datetime import datetime, timezone

import pytest

import historical_email_anchor
import historical_email_proof


def _fake_check_result(recipient="alice@example.com"):
    return historical_email_proof.MessageCheckResult(
        recipient_email=recipient,
        signed_date_utc=datetime(2025, 12, 1, tzinfo=timezone.utc),
        signing_domain="stampd-demo.example",
        checks={
            "approvedDkimSigner": True,
            "approvedMessageClass": True,
            "signedRecipient": True,
            "signedDateBeforeCutoff": True,
        },
    )


@pytest.fixture
def checked_ok(app_module, monkeypatch):
    monkeypatch.setattr(app_module.historical_email_proof, "check_message_fields", lambda raw, policy, dnsfunc=None: _fake_check_result())


@pytest.fixture
def checked_rejected(app_module, monkeypatch):
    def fake(raw, policy, dnsfunc=None):
        raise historical_email_proof.RejectedMessage("DKIM signature did not verify")
    monkeypatch.setattr(app_module.historical_email_proof, "check_message_fields", fake)


def test_check_rejects_missing_file(client):
    response = client.post("/api/historical-email-proof/check")
    assert response.status_code in (400, 422)


def test_check_rejects_empty_file(client):
    response = client.post(
        "/api/historical-email-proof/check",
        files={"eml_file": ("empty.eml", b"", "message/rfc822")},
    )
    assert response.status_code == 400
    assert "empty" in response.json()["error"].lower()


def test_check_surfaces_rejection_reason(client, checked_rejected):
    response = client.post(
        "/api/historical-email-proof/check",
        files={"eml_file": ("test.eml", b"From: a@b.com\r\n\r\nbody", "message/rfc822")},
    )
    assert response.status_code == 422
    assert "DKIM" in response.json()["error"]


def test_check_creates_session_on_success(client, checked_ok):
    response = client.post(
        "/api/historical-email-proof/check",
        files={"eml_file": ("test.eml", b"From: a@b.com\r\n\r\nbody", "message/rfc822")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["session_id"]
    assert body["signing_domain"] == "stampd-demo.example"
    assert all(body["checks"].values())


def test_issue_unknown_session_returns_404(client):
    response = client.post("/api/historical-email-proof/does-not-exist/issue")
    assert response.status_code == 404


@pytest.fixture
def checked_session(client, checked_ok):
    response = client.post(
        "/api/historical-email-proof/check",
        files={"eml_file": ("test.eml", b"From: a@b.com\r\n\r\nbody", "message/rfc822")},
    )
    return response.json()["session_id"]


def test_issue_publishes_anchor_and_stores_package(client, checked_session, app_module, monkeypatch):
    monkeypatch.setattr(app_module, "_irys_upload", lambda data, content_type, tags: "tx-demo-1")

    response = client.post(f"/api/historical-email-proof/{checked_session}/issue")

    assert response.status_code == 200
    body = response.json()
    assert body["arweave_tx_id"] == "tx-demo-1"
    assert body["credential_jws"].count(".") == 2

    entry = app_module.historical_email_proof_sessions[checked_session]
    assert entry["package"]["arweaveTxId"] == "tx-demo-1"


def test_issue_twice_is_rejected(client, checked_session, app_module, monkeypatch):
    monkeypatch.setattr(app_module, "_irys_upload", lambda data, content_type, tags: "tx-demo-1")
    client.post(f"/api/historical-email-proof/{checked_session}/issue")

    response = client.post(f"/api/historical-email-proof/{checked_session}/issue")
    assert response.status_code == 409


def test_issue_surfaces_anchor_failure(client, checked_session, app_module, monkeypatch):
    def failing_upload(data, content_type, tags):
        raise RuntimeError("irys down")
    monkeypatch.setattr(app_module, "_irys_upload", failing_upload)

    response = client.post(f"/api/historical-email-proof/{checked_session}/issue", )
    assert response.status_code == 502
    assert "anchor failed" in response.json()["detail"]


def test_issue_retries_anchor_without_reissuing_after_failure(client, checked_session, app_module, monkeypatch):
    def failing_upload(data, content_type, tags):
        raise RuntimeError("irys down")
    monkeypatch.setattr(app_module, "_irys_upload", failing_upload)
    first = client.post(f"/api/historical-email-proof/{checked_session}/issue")
    assert first.status_code == 502
    issued_after_failure = app_module.historical_email_proof_sessions[checked_session]["issued"]

    monkeypatch.setattr(app_module, "_irys_upload", lambda data, content_type, tags: "tx-retry-1")
    second = client.post(f"/api/historical-email-proof/{checked_session}/issue")

    assert second.status_code == 200
    assert second.json()["arweave_tx_id"] == "tx-retry-1"
    assert second.json()["credential_jws"] == issued_after_failure.credential_jws

    # The download must now work -- the failed first attempt must not have
    # left the session permanently stuck as "issued but no package".
    download = client.get(f"/api/historical-email-proof/{checked_session}/download")
    assert download.status_code == 200

    third = client.post(f"/api/historical-email-proof/{checked_session}/issue")
    assert third.status_code == 409


def test_download_requires_issued_credential(client, checked_session):
    response = client.get(f"/api/historical-email-proof/{checked_session}/download")
    assert response.status_code == 404


def test_download_returns_package_after_issue(client, checked_session, app_module, monkeypatch):
    monkeypatch.setattr(app_module, "_irys_upload", lambda data, content_type, tags: "tx-demo-1")
    client.post(f"/api/historical-email-proof/{checked_session}/issue")

    response = client.get(f"/api/historical-email-proof/{checked_session}/download")
    assert response.status_code == 200
    assert response.json()["arweaveTxId"] == "tx-demo-1"
    assert "attachment" in response.headers["content-disposition"]


def test_email_requires_smtp_configuration(client, checked_session, app_module, monkeypatch):
    monkeypatch.setattr(app_module, "_irys_upload", lambda data, content_type, tags: "tx-demo-1")
    client.post(f"/api/historical-email-proof/{checked_session}/issue")
    monkeypatch.setattr(app_module, "NOTARY_SMTP_USER", None)

    response = client.post(f"/api/historical-email-proof/{checked_session}/email")
    assert response.status_code == 503


def test_email_sends_to_verified_recipient_only(client, checked_session, app_module, monkeypatch):
    monkeypatch.setattr(app_module, "_irys_upload", lambda data, content_type, tags: "tx-demo-1")
    client.post(f"/api/historical-email-proof/{checked_session}/issue")

    monkeypatch.setattr(app_module, "NOTARY_SMTP_USER", "user")
    monkeypatch.setattr(app_module, "NOTARY_SMTP_PASSWORD", "pw")

    captured = {}

    def fake_smtp_send(to_addr, msg_bytes, host, port, user, password, from_addr):
        captured["to"] = to_addr
        captured["msg_bytes"] = msg_bytes

    monkeypatch.setattr(app_module, "_notary_smtp_send", fake_smtp_send)

    response = client.post(f"/api/historical-email-proof/{checked_session}/email")
    assert response.status_code == 200
    assert captured["to"] == "alice@example.com"
    assert b"stampd-proof.json" in captured["msg_bytes"]


def test_email_enforces_minimum_interval_between_sends(client, checked_session, app_module, monkeypatch):
    monkeypatch.setattr(app_module, "_irys_upload", lambda data, content_type, tags: "tx-demo-1")
    client.post(f"/api/historical-email-proof/{checked_session}/issue")
    monkeypatch.setattr(app_module, "NOTARY_SMTP_USER", "user")
    monkeypatch.setattr(app_module, "NOTARY_SMTP_PASSWORD", "pw")
    monkeypatch.setattr(app_module, "_notary_smtp_send", lambda *a: None)

    first = client.post(f"/api/historical-email-proof/{checked_session}/email")
    assert first.status_code == 200

    second = client.post(f"/api/historical-email-proof/{checked_session}/email")
    assert second.status_code == 429


def test_email_enforces_max_sends_per_session(client, checked_session, app_module, monkeypatch):
    monkeypatch.setattr(app_module, "_irys_upload", lambda data, content_type, tags: "tx-demo-1")
    client.post(f"/api/historical-email-proof/{checked_session}/issue")
    monkeypatch.setattr(app_module, "NOTARY_SMTP_USER", "user")
    monkeypatch.setattr(app_module, "NOTARY_SMTP_PASSWORD", "pw")
    monkeypatch.setattr(app_module, "_notary_smtp_send", lambda *a: None)
    monkeypatch.setattr(app_module, "HISTORICAL_EMAIL_MIN_SEND_INTERVAL_SECONDS", 0)

    entry = app_module.historical_email_proof_sessions[checked_session]
    entry["email_send_count"] = app_module.HISTORICAL_EMAIL_MAX_SENDS_PER_SESSION

    response = client.post(f"/api/historical-email-proof/{checked_session}/email")
    assert response.status_code == 429
