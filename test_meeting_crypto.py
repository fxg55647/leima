import base64
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

import meeting_crypto

VECTORS_PATH = Path(__file__).parent / "android" / "testdata" / "meeting_crypto_vectors.json"


def _load_vectors():
    with VECTORS_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _b64d(value: str) -> bytes:
    return base64.b64decode(value)


def test_domain_separator_scheme_matches_fixture():
    data = _load_vectors()
    assert data["signatureAlgorithm"] == "SHA256withECDSA"
    assert data["domainSeparatorScheme"] == 'utf8("leima-meeting-v2:" + messageType) + 0x00 + payloadBytes'
    for vector in data["vectors"]:
        expected = meeting_crypto.domain_separator(vector["messageType"]).decode("utf-8")
        assert vector["domainSeparator"] == expected


def test_shared_vectors_verify():
    data = _load_vectors()
    public_key = meeting_crypto.load_public_key_der(_b64d(data["testPublicKeySpkiDerBase64"]))
    assert len(data["vectors"]) >= 1
    for vector in data["vectors"]:
        payload = _b64d(vector["payloadBase64"])
        signature = _b64d(vector["signatureBase64Der"])
        assert meeting_crypto.verify(public_key, vector["messageType"], payload, signature)


def test_tampered_payload_is_rejected():
    data = _load_vectors()
    public_key = meeting_crypto.load_public_key_der(_b64d(data["testPublicKeySpkiDerBase64"]))
    vector = data["vectors"][0]
    payload = bytearray(_b64d(vector["payloadBase64"]))
    payload[-1] ^= 0x01
    signature = _b64d(vector["signatureBase64Der"])
    assert not meeting_crypto.verify(public_key, vector["messageType"], bytes(payload), signature)


def test_wrong_message_type_is_rejected():
    data = _load_vectors()
    public_key = meeting_crypto.load_public_key_der(_b64d(data["testPublicKeySpkiDerBase64"]))
    vector = next(v for v in data["vectors"] if v["messageType"] == "finish_challenge")
    other = next(v for v in data["vectors"] if v["messageType"] == "finish_response")
    payload = _b64d(vector["payloadBase64"])
    signature = _b64d(vector["signatureBase64Der"])
    assert not meeting_crypto.verify(public_key, other["messageType"], payload, signature)


def test_round_trip_with_freshly_generated_key():
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    payload = b'{"hello":"world"}'
    signature = meeting_crypto.sign(private_key, "finish_challenge", payload)
    assert meeting_crypto.verify(public_key, "finish_challenge", payload, signature)


def test_public_key_der_round_trip():
    private_key = ec.generate_private_key(ec.SECP256R1())
    der = meeting_crypto.public_key_der(private_key.public_key())
    loaded = meeting_crypto.load_public_key_der(der)
    assert loaded.public_numbers() == private_key.public_key().public_numbers()


def test_non_p256_key_is_rejected():
    private_key = ec.generate_private_key(ec.SECP384R1())
    der = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    try:
        meeting_crypto.load_public_key_der(der)
        assert False, "expected ValueError for non-P-256 key"
    except ValueError:
        pass
