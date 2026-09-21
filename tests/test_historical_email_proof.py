"""Generic-testdata pipeline tests for the historical email personhood proof
(docs/todo/HISTORICAL_EMAIL_PROOF_PLAN.md, phase "paikallinen kokonaisuus").

Everything here is synthetic: a locally generated RSA key stands in for a
government mail server's DKIM key, and a fake dnsfunc stands in for DNS —
no network access, matching the offline test boundary in conftest.py.
"""

import base64
from datetime import datetime, timedelta, timezone

import dkim
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from historical_email_policy import HistoricalEmailPolicy, normalize_email
from historical_email_proof import RejectedMessage, check_message_fields, issue_credential
from proof_verifier import verify_attestation

SIGNER_DOMAIN = b"gov.example.test"
SELECTOR = b"test-selector"


@pytest.fixture(scope="module")
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="module")
def rsa_key_pem(rsa_key):
    return rsa_key.private_bytes(Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption())


@pytest.fixture(scope="module")
def dnsfunc(rsa_key):
    pub_der = rsa_key.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    record = "v=DKIM1; k=rsa; p=" + base64.b64encode(pub_der).decode("ascii")
    expected_name = SELECTOR + b"._domainkey." + SIGNER_DOMAIN + b"."

    def _dnsfunc(name, timeout=5):
        assert name == expected_name
        return record

    return _dnsfunc


@pytest.fixture
def issuer_keys():
    private_key = Ed25519PrivateKey.generate()
    return private_key, private_key.public_key()


def build_raw_email(
    to_addr: str,
    date_str: str,
    rsa_key_pem: bytes,
    from_addr: str = "notifications@gov.example.test",
    subject: str = "Notice of registration",
    include_headers=None,
    length=False,
    extra_to_addr: str | None = None,
):
    to_lines = f"To: {to_addr}\r\n"
    if extra_to_addr is not None:
        to_lines += f"To: {extra_to_addr}\r\n"
    unsigned = (
        f"From: {from_addr}\r\n"
        f"{to_lines}"
        f"Subject: {subject}\r\n"
        f"Date: {date_str}\r\n"
        f"Message-ID: <fixed-test-id@gov.example.test>\r\n"
        f"MIME-Version: 1.0\r\n"
        f"Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "This is a test notification body.\r\n"
    ).encode("ascii")

    sig_header = dkim.sign(
        unsigned,
        selector=SELECTOR,
        domain=SIGNER_DOMAIN,
        privkey=rsa_key_pem,
        include_headers=include_headers,
        length=length,
    )
    return sig_header + unsigned


@pytest.fixture(scope="module")
def policy():
    return HistoricalEmailPolicy(
        policy_id="stampd-historical-email-test-v1",
        policy_version=1,
        evidence_class="test-notification",
        allowed_dkim_signers=(SIGNER_DOMAIN.decode(),),
        cutoff=datetime(2026, 1, 1, tzinfo=timezone.utc),
        human_verification_basis="test fixture -- not a real vetting decision",
    )


VALID_DATE = "Mon, 01 Dec 2025 12:00:00 +0000"
AFTER_CUTOFF_DATE = "Thu, 15 Jan 2026 12:00:00 +0000"


class TestCheckMessageFields:
    def test_accepts_valid_message(self, rsa_key_pem, dnsfunc, policy):
        raw = build_raw_email("alice@example.com", VALID_DATE, rsa_key_pem)
        result = check_message_fields(raw, policy, dnsfunc=dnsfunc)
        assert result.recipient_email == normalize_email("alice@example.com")
        assert result.signing_domain == SIGNER_DOMAIN.decode()
        assert all(result.checks.values())

    def test_rejects_date_after_cutoff(self, rsa_key_pem, dnsfunc, policy):
        raw = build_raw_email("alice@example.com", AFTER_CUTOFF_DATE, rsa_key_pem)
        with pytest.raises(RejectedMessage, match="cutoff"):
            check_message_fields(raw, policy, dnsfunc=dnsfunc)

    def test_rejects_unapproved_signer_domain(self, rsa_key_pem, dnsfunc, policy):
        other_policy = HistoricalEmailPolicy(
            policy_id=policy.policy_id,
            policy_version=policy.policy_version,
            evidence_class=policy.evidence_class,
            allowed_dkim_signers=("someone-else.example.test",),
            cutoff=policy.cutoff,
            human_verification_basis=policy.human_verification_basis,
        )
        raw = build_raw_email("alice@example.com", VALID_DATE, rsa_key_pem)
        with pytest.raises(RejectedMessage, match="approved signer"):
            check_message_fields(raw, other_policy, dnsfunc=dnsfunc)

    def test_rejects_partial_body_signature(self, rsa_key_pem, dnsfunc, policy):
        raw = build_raw_email("alice@example.com", VALID_DATE, rsa_key_pem, length=True)
        with pytest.raises(RejectedMessage, match="partial body signature"):
            check_message_fields(raw, policy, dnsfunc=dnsfunc)

    def test_rejects_unsigned_recipient_and_date(self, rsa_key_pem, dnsfunc, policy):
        raw = build_raw_email(
            "alice@example.com", VALID_DATE, rsa_key_pem,
            include_headers=[b"from", b"subject"],
        )
        with pytest.raises(RejectedMessage, match="not covered by DKIM signature"):
            check_message_fields(raw, policy, dnsfunc=dnsfunc)

    def test_rejects_tampered_body(self, rsa_key_pem, dnsfunc, policy):
        raw = build_raw_email("alice@example.com", VALID_DATE, rsa_key_pem)
        tampered = raw.replace(b"test notification body", b"forged notification body")
        with pytest.raises(RejectedMessage, match="DKIM"):
            check_message_fields(tampered, policy, dnsfunc=dnsfunc)

    def test_rejects_duplicate_to_header(self, rsa_key_pem, dnsfunc, policy):
        # Both To headers present *before* signing, so the DKIM signature itself
        # stays valid — the ambiguity must be caught by our own check, not DKIM's.
        raw = build_raw_email(
            "alice@example.com", VALID_DATE, rsa_key_pem, extra_to_addr="mallory@example.com",
        )
        with pytest.raises(RejectedMessage, match="exactly one"):
            check_message_fields(raw, policy, dnsfunc=dnsfunc)


class TestIssueAndVerify:
    def test_full_roundtrip(self, rsa_key_pem, dnsfunc, policy, issuer_keys):
        private_key, public_key = issuer_keys
        raw = build_raw_email("alice@example.com", VALID_DATE, rsa_key_pem)

        issued = issue_credential(
            raw, policy, issuer_id="stampd-test-issuer", issuer_kid="test-key-1",
            issuer_private_key=private_key, dnsfunc=dnsfunc,
        )
        credential_jws, secret_b64 = issued.credential_jws, issued.disclosure_secret_b64

        payload = verify_attestation(
            credential_jws, secret_b64, "alice@example.com", policy,
            trusted_issuer_keys={"test-key-1": public_key},
        )
        assert payload["type"] == "HistoricalEmailAttestation"
        assert payload["policyId"] == policy.policy_id

    def test_verification_fails_for_wrong_recipient(self, rsa_key_pem, dnsfunc, policy, issuer_keys):
        private_key, public_key = issuer_keys
        raw = build_raw_email("alice@example.com", VALID_DATE, rsa_key_pem)
        issued = issue_credential(
            raw, policy, "stampd-test-issuer", "test-key-1", private_key, dnsfunc=dnsfunc,
        )
        credential_jws, secret_b64 = issued.credential_jws, issued.disclosure_secret_b64
        with pytest.raises(RejectedMessage, match="does not match"):
            verify_attestation(
                credential_jws, secret_b64, "bob@example.com", policy,
                trusted_issuer_keys={"test-key-1": public_key},
            )

    def test_verification_fails_for_unknown_issuer_key(self, rsa_key_pem, dnsfunc, policy, issuer_keys):
        private_key, _ = issuer_keys
        raw = build_raw_email("alice@example.com", VALID_DATE, rsa_key_pem)
        issued = issue_credential(
            raw, policy, "stampd-test-issuer", "test-key-1", private_key, dnsfunc=dnsfunc,
        )
        credential_jws, secret_b64 = issued.credential_jws, issued.disclosure_secret_b64
        with pytest.raises(RejectedMessage, match="untrusted issuer key"):
            verify_attestation(
                credential_jws, secret_b64, "alice@example.com", policy,
                trusted_issuer_keys={},
            )

    def test_verification_fails_for_tampered_signature(self, rsa_key_pem, dnsfunc, policy, issuer_keys):
        private_key, public_key = issuer_keys
        raw = build_raw_email("alice@example.com", VALID_DATE, rsa_key_pem)
        issued = issue_credential(
            raw, policy, "stampd-test-issuer", "test-key-1", private_key, dnsfunc=dnsfunc,
        )
        credential_jws, secret_b64 = issued.credential_jws, issued.disclosure_secret_b64
        header_b64, payload_b64, sig_b64 = credential_jws.split(".")
        tampered = f"{header_b64}.{payload_b64}.{sig_b64[:-4]}AAAA"
        with pytest.raises(RejectedMessage, match="does not verify"):
            verify_attestation(
                tampered, secret_b64, "alice@example.com", policy,
                trusted_issuer_keys={"test-key-1": public_key},
            )

    def test_verification_fails_for_wrong_policy(self, rsa_key_pem, dnsfunc, policy, issuer_keys):
        private_key, public_key = issuer_keys
        raw = build_raw_email("alice@example.com", VALID_DATE, rsa_key_pem)
        issued = issue_credential(
            raw, policy, "stampd-test-issuer", "test-key-1", private_key, dnsfunc=dnsfunc,
        )
        credential_jws, secret_b64 = issued.credential_jws, issued.disclosure_secret_b64
        different_policy = HistoricalEmailPolicy(
            policy_id=policy.policy_id,
            policy_version=2,
            evidence_class=policy.evidence_class,
            allowed_dkim_signers=policy.allowed_dkim_signers,
            cutoff=policy.cutoff,
            human_verification_basis=policy.human_verification_basis,
        )
        with pytest.raises(RejectedMessage, match="locked policy"):
            verify_attestation(
                credential_jws, secret_b64, "alice@example.com", different_policy,
                trusted_issuer_keys={"test-key-1": public_key},
            )
