"""Phase D: package transfer phone -> PC archive, the shared verifier and the archive index."""
import base64
import hashlib
import io
import json
import zipfile

import pytest
from cryptography.hazmat.primitives.asymmetric import ec

import meeting_crypto
from bridge.adb import Device
from bridge.archive import Archive
from bridge.client import sync
from bridge.errors import BridgeError
from bridge.mcp_stdio import make_call_tool
from verify_package import verify


def _zip(entries: dict) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return out.getvalue()


def photo_package(metadata=None, kind="photo", tamper=False) -> bytes:
    metadata = metadata or {"schemaVersion": 1, "kind": "camera_photo", "requestedAt": "2026-10-03T09:00:12.5Z",
                            "device": {"model": "Pixel 7"}}
    media = "screenshot.png" if kind == "screenshot" else "photo.jpg"
    files = {media: b"image bytes", "metadata.json": json.dumps(metadata).encode()}
    manifest_obj = {"schemaVersion": 1, "algorithm": "SHA-256", "files": {n: hashlib.sha256(d).hexdigest() for n, d in files.items()}}
    if kind:
        manifest_obj["kind"] = kind
    manifest = json.dumps(manifest_obj).encode()
    if tamper:
        files[media] += b"!"
    return _zip({**files, "manifest.json": manifest, "manifest.sha256": hashlib.sha256(manifest).hexdigest() + "  manifest.json\n"})


def meeting_package(tamper_signature=False) -> bytes:
    key = ec.generate_private_key(ec.SECP256R1())
    files = {"session.json": b'{"schemaVersion":2,"startedAtUtc":"2026-10-03T08:45:00Z"}', "captures/c1.jpg": b"jpeg"}
    manifest = json.dumps({"schemaVersion": 2, "algorithm": "SHA-256", "kind": "meeting",
                           "files": {n: hashlib.sha256(d).hexdigest() for n, d in files.items()}}).encode()
    signature = meeting_crypto.sign(key, "manifest", manifest)
    if tamper_signature:
        signature = meeting_crypto.sign(key, "manifest", manifest + b" ")
    signature_json = json.dumps({
        "algorithm": "SHA256withECDSA", "curve": "P-256",
        "publicKeySpkiDerBase64": base64.b64encode(meeting_crypto.public_key_der(key.public_key())).decode(),
        "signatureBase64Der": base64.b64encode(signature).decode(),
    }).encode()
    return _zip({**files, "manifest.json": manifest, "signature.json": signature_json,
                 "manifest.sha256": hashlib.sha256(manifest).hexdigest() + "  manifest.json\n"})


# ---- shared verifier ---------------------------------------------------------------------------

def test_verifier_accepts_all_kinds_and_old_packages_without_kind():
    assert verify(io.BytesIO(photo_package()))["kind"] == "photo"
    assert verify(io.BytesIO(photo_package(kind="screenshot")))["kind"] == "screenshot"
    assert verify(io.BytesIO(photo_package(kind=None)))["kind"] == "photo"
    result = verify(io.BytesIO(meeting_package()))
    assert result["kind"] == "meeting" and result["details"]["startedAtUtc"] == "2026-10-03T08:45:00Z"


@pytest.mark.parametrize("data", [
    photo_package(tamper=True),
    meeting_package(tamper_signature=True),
    _zip({"../evil": b"x", "manifest.json": b"{}", "manifest.sha256": b""}),
])
def test_verifier_rejects_tampered_and_unsafe(data):
    with pytest.raises(ValueError):
        verify(io.BytesIO(data))


# ---- archive -----------------------------------------------------------------------------------

def test_archive_stores_unchanged_bytes_in_kind_date_folders(tmp_path):
    archive = Archive(tmp_path)
    data = photo_package(metadata={"requestedAt": "2026-10-03T10:15:00Z", "url": "https://Pankki.fi/tili"}, kind="screenshot")
    row, status = archive.store(data, "Pixel 7")
    sha = hashlib.sha256(data).hexdigest()
    assert status == "archived"
    assert row["path"] == f"screenshot/2026/10/2026-10-03_101500_pankki.fi_{sha[:8]}/package.zip"
    assert (tmp_path / row["path"]).read_bytes() == data
    assert row["domain"] == "pankki.fi" and row["captured_at"] == "2026-10-03T10:15:00Z" and row["verified"]
    assert not list(tmp_path.rglob("*.partial"))

    again, status = archive.store(data, "Pixel 7")
    assert status == "already_archived" and again["path"] == row["path"]
    assert len(archive.rows()) == 1


def test_archive_refuses_invalid_package(tmp_path):
    with pytest.raises(BridgeError) as e:
        Archive(tmp_path).store(photo_package(tamper=True))
    assert e.value.code == "PACKAGE_INVALID"
    assert not (tmp_path / "index.jsonl").exists()


def test_tags_and_reverification_detect_later_changes(tmp_path):
    archive = Archive(tmp_path)
    row, _ = archive.store(meeting_package())
    assert row["kind"] == "meeting" and row["path"].startswith("meeting/2026/10/2026-10-03_084500_")
    archive.tag(row["sha256"][:8], "case-42")
    assert archive.tags(row["sha256"]) == ["case-42"]
    assert archive.verify_entry(row["sha256"][:8])["valid"]

    path = tmp_path / row["path"]
    path.write_bytes(path.read_bytes() + b"x")
    with pytest.raises(BridgeError) as e:
        archive.verify_entry(row["sha256"])
    assert e.value.code == "PACKAGE_INVALID"
    with pytest.raises(BridgeError):
        archive.find("abc")  # too short


# ---- sync over the protocol --------------------------------------------------------------------

class FakePackagePhone:
    """In-memory phone client: packages.list/read/delete with the real chunking contract."""

    def __init__(self, packages: dict, chunk=7, corrupt=None):
        self.packages = dict(packages)
        self.chunk = chunk
        self.corrupt = corrupt
        self.deleted = []

    def request(self, method, params=None, timeout=None):
        params = params or {}
        if method == "packages.list":
            return {"packages": [
                {"package_id": pid, "kind": "photo", "size": len(d), "sha256": hashlib.sha256(d).hexdigest(), "created_at": "x"}
                for pid, d in self.packages.items()]}
        if method == "packages.read":
            data = self.packages[params["package_id"]]
            if params["package_id"] == self.corrupt:
                data = data[:-1] + b"?"
            piece = data[params["offset"]:params["offset"] + min(self.chunk, params["length"])]
            return {"offset": params["offset"], "data_base64": base64.b64encode(piece).decode(),
                    "eof": params["offset"] + len(piece) >= len(data)}
        if method == "packages.delete":
            assert hashlib.sha256(self.packages[params["package_id"]]).hexdigest() == params["sha256"]
            self.deleted.append(params["package_id"])
            del self.packages[params["package_id"]]
            return {"deleted": True}
        raise AssertionError(method)


def test_sync_archives_then_deletes_and_keeps_failures_on_phone(tmp_path):
    good, bad, broken = photo_package(), photo_package(tamper=True), meeting_package()
    phone = FakePackagePhone({"evidence:a": good, "evidence:b": bad, "meeting:c": broken}, corrupt="meeting:c")
    archive = Archive(tmp_path)
    results = {r["package_id"]: r for r in sync(phone, Device("S", "device", "Pixel 7"), archive)}

    assert results["evidence:a"]["status"] == "archived" and results["evidence:a"]["deleted_from_phone"]
    assert results["evidence:b"]["status"] == "failed" and "PACKAGE_INVALID" in results["evidence:b"]["error"]
    assert results["meeting:c"]["status"] == "failed" and "PACKAGE_TRANSFER_MISMATCH" in results["meeting:c"]["error"]
    assert phone.deleted == ["evidence:a"]
    assert set(phone.packages) == {"evidence:b", "meeting:c"}
    assert [r["sha256"] for r in archive.rows()] == [hashlib.sha256(good).hexdigest()]


def test_sync_keep_leaves_phone_untouched_and_rerun_is_idempotent(tmp_path):
    data = photo_package()
    archive = Archive(tmp_path)
    phone = FakePackagePhone({"evidence:a": data})
    assert sync(phone, Device("S", "device"), archive, delete=False)[0]["status"] == "archived"
    assert phone.deleted == []
    assert sync(phone, Device("S", "device"), archive)[0]["status"] == "already_archived"
    assert phone.deleted == ["evidence:a"]
    assert len(archive.rows()) == 1


@pytest.mark.parametrize("damage", ["corrupt", "missing"])
def test_resync_repairs_damaged_archive_copy_before_deleting_phone_copy(tmp_path, damage):
    data = photo_package()
    archive = Archive(tmp_path)
    phone = FakePackagePhone({"evidence:a": data})
    sync(phone, Device("S", "device"), archive, delete=False)
    path = tmp_path / archive.rows()[0]["path"]
    if damage == "corrupt":
        path.write_bytes(b"bit rot")
    else:
        path.unlink()

    result = sync(phone, Device("S", "device"), archive)[0]
    assert result["status"] == "repaired" and result["deleted_from_phone"]
    assert path.read_bytes() == data
    repaired = [r for r in archive.rows() if r["event"] == "repaired"]
    assert len(repaired) == 1 and repaired[0]["reason"] == ("hash_mismatch" if damage == "corrupt" else "missing")
    assert archive.verify_entry(result["sha256"])["valid"]


def test_resync_never_deletes_when_phone_copy_is_invalid_even_if_archived(tmp_path):
    # Same sha256 cannot differ in content, but an invalid package must never count as archived.
    archive = Archive(tmp_path)
    phone = FakePackagePhone({"evidence:b": photo_package(tamper=True)})
    assert sync(phone, Device("S", "device"), archive)[0]["status"] == "failed"
    assert phone.deleted == []


def test_mcp_sync_is_destructive_and_can_keep_packages(tmp_path, monkeypatch):
    from bridge import mcp_stdio
    tool = next(t for t in mcp_stdio.TOOLS if t["name"] == "packages_sync")
    assert tool["annotations"]["destructiveHint"] is True
    assert tool["inputSchema"]["properties"]["keep_on_phone"]["type"] == "boolean"

    phone = FakePackagePhone({"evidence:a": photo_package()})
    archive = Archive(tmp_path)

    class FakeSession:
        def __init__(self, *args):
            pass

        def __enter__(self):
            return Device("S", "device"), phone

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(mcp_stdio, "session", FakeSession)
    call_tool = mcp_stdio.make_call_tool(lambda: None, lambda: None, lambda: archive)
    kept = call_tool("packages_sync", {"keep_on_phone": True})
    assert kept["results"][0]["status"] == "archived" and phone.deleted == []
    moved = call_tool("packages_sync", {})
    assert moved["results"][0]["deleted_from_phone"] and phone.deleted == ["evidence:a"]


def test_mcp_package_verify_tool(tmp_path):
    archive = Archive(tmp_path)
    row, _ = archive.store(photo_package())
    call_tool = make_call_tool(archive_factory=lambda: archive)
    assert call_tool("package_verify", {"sha256": row["sha256"][:10]})["valid"]
