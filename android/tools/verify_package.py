"""Verify a Leima Android package (photo, screenshot or meeting) against its own manifest.

Shared envelope rules: docs/RESEARCH_APPLIANCE_PACKAGES.md. Standalone on purpose (only the
standard library; meeting signatures additionally need `cryptography`), so anyone can check a
package without the rest of Leima. This proves integrity relative to the manifest only: it does
not authenticate the device, the time or the content.
"""
import base64
import hashlib
import json
import sys
import zipfile

MAX_ENTRY_BYTES = 100 * 1024 * 1024
ENVELOPE = {"manifest.json", "manifest.sha256"}
# kind -> (manifest schemaVersion, exact payload files or None for "any", extra names outside the manifest)
KINDS = {
    "photo": (1, {"photo.jpg", "metadata.json"}, set()),
    "screenshot": (1, {"screenshot.png", "metadata.json"}, set()),
    "meeting": (2, None, {"signature.json"}),
}


def _infer_kind(names):
    if "signature.json" in names:
        return "meeting"
    if "photo.jpg" in names:
        return "photo"
    if "screenshot.png" in names:
        return "screenshot"
    raise ValueError("Cannot determine package kind")


def _verify_meeting_signature(manifest_bytes, signature_json):
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
    except ImportError as e:
        raise ValueError("Verifying meeting signatures requires the 'cryptography' package") from e
    signature = json.loads(signature_json)
    if signature.get("algorithm") != "SHA256withECDSA" or signature.get("curve") != "P-256":
        raise ValueError("Unsupported meeting signature algorithm")
    key = serialization.load_der_public_key(base64.b64decode(signature["publicKeySpkiDerBase64"]))
    if not isinstance(key, ec.EllipticCurvePublicKey) or key.curve.name != "secp256r1":
        raise ValueError("Meeting signature key is not P-256")
    # Same domain separation as meeting_crypto.signed_bytes("manifest", ...).
    signed = b"leima-meeting-v2:manifest" + b"\x00" + manifest_bytes
    try:
        key.verify(base64.b64decode(signature["signatureBase64Der"]), signed, ec.ECDSA(hashes.SHA256()))
    except InvalidSignature as e:
        raise ValueError("Meeting manifest signature is invalid") from e


def verify(source):
    """`source` is a path or a binary file object. Returns a summary dict; raises ValueError."""
    with zipfile.ZipFile(source) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate ZIP entries")
        for name in names:
            if name.startswith(("/", "\\")) or ".." in name.replace("\\", "/").split("/") or ":" in name:
                raise ValueError(f"Unsafe ZIP entry name: {name}")
        if any(info.file_size > MAX_ENTRY_BYTES for info in infos):
            raise ValueError("Entry exceeds 100 MiB verification limit")
        manifest_bytes = archive.read("manifest.json")
        expected = archive.read("manifest.sha256").decode("utf-8").strip()
        if expected != hashlib.sha256(manifest_bytes).hexdigest() + "  manifest.json":
            raise ValueError("Manifest checksum mismatch")
        manifest = json.loads(manifest_bytes)
        if manifest.get("algorithm") != "SHA-256" or not isinstance(manifest.get("files"), dict):
            raise ValueError("Unsupported manifest")
        files = manifest["files"]
        kind = manifest.get("kind") or _infer_kind(set(names))
        if kind not in KINDS:
            raise ValueError(f"Unsupported package kind: {kind}")
        schema_version, payload, extras = KINDS[kind]
        if manifest.get("schemaVersion") != schema_version:
            raise ValueError("Unsupported manifest")
        if payload is not None and set(files) != payload:
            raise ValueError("Unexpected payload files")
        if set(names) != set(files) | ENVELOPE | extras:
            raise ValueError("Unexpected ZIP entries")
        for name, digest in files.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise ValueError(f"Checksum mismatch: {name}")
        if kind == "meeting":
            _verify_meeting_signature(manifest_bytes, archive.read("signature.json"))
            details = json.loads(archive.read("session.json")) if "session.json" in files else {}
        else:
            details = json.loads(archive.read("metadata.json"))
        return {"kind": kind, "manifest": manifest, "details": details}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python verify_package.py evidence.zip")
    try:
        result = verify(sys.argv[1])
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        sys.exit(f"INVALID: {error}")
    print(f"Hashes valid ({result['kind']}). Package is unsigned by any trusted party; origin and timestamps are not authenticated.")
