"""Shared ECDSA P-256/SHA-256 signing scheme for the Leima meeting-proof v2 protocol.

Every signed message (QR envelope or package manifest) is signed over
``domain_separator(message_type) + b"\\x00" + payload_bytes`` — never over a
re-serialized JSON object — so a verifier never has to reproduce the sender's
exact JSON encoding. The domain separator is delimited with a NUL byte so no
separator can be a byte-for-byte prefix of another separator plus payload.

Signature and public-key encodings match what Android's java.security /
Keystore APIs produce by default: ASN.1 DER ECDSA signatures and DER
SubjectPublicKeyInfo public keys. See android/docs/meeting_v2_schema.md and
android/testdata/meeting_crypto_vectors.json for the cross-language test
vectors that pin this scheme.
"""

from __future__ import annotations

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

DOMAIN_PREFIX = "leima-meeting-v2"


def domain_separator(message_type: str) -> bytes:
    return f"{DOMAIN_PREFIX}:{message_type}".encode("utf-8")


def signed_bytes(message_type: str, payload: bytes) -> bytes:
    return domain_separator(message_type) + b"\x00" + payload


def sign(private_key: ec.EllipticCurvePrivateKey, message_type: str, payload: bytes) -> bytes:
    return private_key.sign(signed_bytes(message_type, payload), ec.ECDSA(hashes.SHA256()))


def verify(public_key: ec.EllipticCurvePublicKey, message_type: str, payload: bytes, signature: bytes) -> bool:
    try:
        public_key.verify(signature, signed_bytes(message_type, payload), ec.ECDSA(hashes.SHA256()))
        return True
    except InvalidSignature:
        return False


def public_key_der(public_key: ec.EllipticCurvePublicKey) -> bytes:
    return public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def load_public_key_der(der: bytes) -> ec.EllipticCurvePublicKey:
    key = serialization.load_der_public_key(der)
    if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
        raise ValueError("expected a P-256 (secp256r1) EC public key")
    return key
