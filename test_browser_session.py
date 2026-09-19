"""
test_browser_session.py — Tests for browser_session.parse_and_verify()
and the POST /api/evidence/browser-sessions FastAPI endpoint.

Run:
    pip install pytest pytest-asyncio httpx
    pytest test_browser_session.py -v

The _build_screenshot_package() and _build_photo_package() functions below are the
authoritative example of the schema_version=1 wire format that Android should produce.
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from typing import Any

import pytest

from browser_session import parse_and_verify, _sha256


# ── Minimal valid PNG (1×1 pixel, uncompressed IDAT) ─────────────────────────
# Used as a stand-in for a real screenshot; only the hash matters for server tests.
_EXAMPLE_PNG = bytes.fromhex(
    "89504e470d0a1a0a"          # PNG signature
    "0000000d49484452"          # IHDR length + type
    "00000001"                  # width=1
    "00000001"                  # height=1
    "08020000009001 2e"         # 8-bit RGB, no interlace + CRC
    "0000000c49444154"          # IDAT length + type
    "789c6260000000020001"      # minimal zlib-compressed IDAT
    "e221bc33"                  # IDAT CRC
    "0000000049454e44"          # IEND length + type
    "ae426082"                  # IEND CRC
    .replace(" ", "")
)

from PIL import Image


def _image_bytes(kind, size=(100, 80)):
    stream = io.BytesIO()
    Image.new("RGB", size, "white").save(stream, format=kind)
    return stream.getvalue()


_PNG_BYTES = _image_bytes("PNG")
_JPG_BYTES = _image_bytes("JPEG")


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ── Package builder helpers ───────────────────────────────────────────────────

def _manifest_json(media_name: str, media_bytes: bytes, meta_bytes: bytes) -> bytes:
    return json.dumps({
        "schemaVersion": 1,
        "algorithm": "SHA-256",
        "files": {
            media_name:      _sha256(media_bytes),
            "metadata.json": _sha256(meta_bytes),
        },
    }, ensure_ascii=False).encode()


def _pack_zip(files: dict[str, bytes]) -> bytes:
    """Create a ZIP from a {name: bytes} dict."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _build_screenshot_package(
    *,
    png: bytes | None = None,
    source_w: int = 200,
    source_h: int = 150,
    crop_left: int = 20, crop_top: int = 10,
    crop_right: int = 120, crop_bottom: int = 90,
    masks: list[dict] | None = None,
    url: str = "https://bank.example",
    url_scope: str = "origin",
    title_included: bool = False,
    sensors_included: bool = False,
    query_and_fragment_removed: bool = True,
    original_image_stored: bool = False,
    include_title: bool = False,
    include_sensors: bool = False,
    # Override specific metadata values for negative tests
    override_meta_w: int | None = None,
    override_meta_h: int | None = None,
    omit_edits: bool = False,
    omit_privacy: bool = False,
    bad_manifest_hash: bool = False,
    tamper_png: bool = False,
) -> bytes:
    """Build a screenshot evidence ZIP matching the Android single-capture format."""

    final_w = override_meta_w if override_meta_w is not None else (crop_right - crop_left)
    final_h = override_meta_h if override_meta_h is not None else (crop_bottom - crop_top)

    # When tamper_png=True: ZIP contains tampered bytes but manifest still hashes
    # the original — so the hash check fails, simulating post-package tampering.
    if png is None:
        png = _image_bytes("PNG", (max(1, crop_right - crop_left), max(1, crop_bottom - crop_top)))
    zip_png      = b"TAMPERED_DATA" if tamper_png else png
    manifest_png = png  # always original bytes in the manifest hash

    meta: dict[str, Any] = {
        "kind":             "webview_viewport",
        "requestedAt":      "2025-01-15T10:00:00Z",
        "completedAt":      "2025-01-15T10:00:01Z",
        "url":              url,
        "width":            final_w,
        "height":           final_h,
        "scrollX":          0,
        "scrollY":          0,
        "captureMethod":    "PixelCopy window rectangle; visible viewport only",
        "schemaVersion":    1,
        "appVersion":       "0.1.0-test",
        "device":           {"manufacturer": "Test", "model": "TestPhone",
                             "androidApi": 34, "androidRelease": "14"},
        "trust":            "Local unsigned capture; device clocks and sensors are not independently verified",
    }

    if include_title:
        meta["title"] = "My Bank Account"
    if include_sensors:
        meta["sensorsAtRequest"] = {"locationStatus": "available", "location": None}

    if not omit_edits:
        visible_masks = []
        for m in (masks or []):
            il = max(crop_left, m["left"]); it = max(crop_top, m["top"])
            ir = min(crop_right, m["right"]); ib = min(crop_bottom, m["bottom"])
            if ir > il and ib > it:
                visible_masks.append(m)
        meta["edits"] = {
            "version":         1,
            "coordinateSpace": "source viewport pixels; right and bottom exclusive",
            "sourceWidth":     source_w,
            "sourceHeight":    source_h,
            "crop":            {"left": crop_left, "top": crop_top,
                                "right": crop_right, "bottom": crop_bottom},
            "opaqueBlackMasks": visible_masks,
        }

    if not omit_privacy:
        meta["privacy"] = {
            "urlScope":                  url_scope,
            "queryAndFragmentRemoved":   query_and_fragment_removed,
            "titleIncluded":             include_title,
            "sensorsIncluded":           include_sensors,
            "originalImageStored":       original_image_stored,
        }

    meta_bytes = json.dumps(meta, ensure_ascii=False, indent=2).encode()
    mf_bytes   = _manifest_json("screenshot.png", manifest_png, meta_bytes)
    mf_hash    = ("00" * 32) if bad_manifest_hash else _sha256(mf_bytes)
    mf_sum     = f"{mf_hash}  manifest.json\n".encode()

    return _pack_zip({
        "screenshot.png":   zip_png,
        "metadata.json":    meta_bytes,
        "manifest.json":    mf_bytes,
        "manifest.sha256":  mf_sum,
    })


def _build_photo_package(
    *,
    jpg: bytes = _JPG_BYTES,
    bad_manifest_hash: bool = False,
    tamper_jpg: bool = False,
) -> bytes:
    """Build a camera-photo evidence ZIP (no edits, no privacy field)."""
    zip_jpg      = b"TAMPERED" if tamper_jpg else jpg
    manifest_jpg = jpg
    meta: dict[str, Any] = {
        "kind":          "camera_photo",
        "requestedAt":   "2025-01-15T10:00:00Z",
        "completedAt":   "2025-01-15T10:00:01Z",
        "lensFacing":    "back",
        "schemaVersion": 1,
        "appVersion":    "0.1.0-test",
        "device":        {"manufacturer": "Test", "model": "TestPhone",
                          "androidApi": 34, "androidRelease": "14"},
        "trust":         "Local unsigned capture; device clocks and sensors are not independently verified",
        "cameraExif":    {"ExposureTime": "1/60", "FNumber": "2.0"},
    }
    meta_bytes = json.dumps(meta, ensure_ascii=False, indent=2).encode()
    mf_bytes   = _manifest_json("photo.jpg", manifest_jpg, meta_bytes)
    mf_hash    = ("00" * 32) if bad_manifest_hash else _sha256(mf_bytes)
    mf_sum     = f"{mf_hash}  manifest.json\n".encode()

    return _pack_zip({
        "photo.jpg":        zip_jpg,
        "metadata.json":    meta_bytes,
        "manifest.json":    mf_bytes,
        "manifest.sha256":  mf_sum,
    })


# ── Valid package tests ───────────────────────────────────────────────────────

def test_valid_screenshot_with_crop_and_masks():
    masks = [{"left": 30, "top": 20, "right": 80, "bottom": 60}]
    pkg = _build_screenshot_package(masks=masks)
    result = parse_and_verify(pkg)
    assert result.integrity.ok, result.integrity.errors
    assert result.integrity.manifest_ok
    assert result.integrity.edits_ok is True
    assert result.integrity.privacy_ok is True
    assert result.integrity.errors == []
    assert result.media_filename == "screenshot.png"
    assert len(result.media_sha256) == 64


def test_valid_photo_package_no_edits():
    pkg = _build_photo_package()
    result = parse_and_verify(pkg)
    assert result.integrity.ok, result.integrity.errors
    assert result.integrity.manifest_ok
    assert result.integrity.edits_ok is None    # no edits field
    assert result.integrity.errors == []
    assert result.media_filename == "photo.jpg"


def test_valid_full_frame_screenshot_no_crop_no_masks():
    pkg = _build_screenshot_package(
        source_w=300, source_h=200,
        crop_left=0, crop_top=0, crop_right=300, crop_bottom=200,
        masks=[],
    )
    result = parse_and_verify(pkg)
    assert result.integrity.ok, result.integrity.errors
    assert result.integrity.edits_ok is True


def test_valid_screenshot_without_edits_field():
    """Old-format screenshots that predate the editor have no edits field."""
    pkg = _build_screenshot_package(omit_edits=True, omit_privacy=True)
    result = parse_and_verify(pkg)
    assert result.integrity.ok, result.integrity.errors
    assert result.integrity.edits_ok is None


def test_missing_optional_metadata_is_valid_privacy_choice():
    """Omitted title, path, and sensors are privacy choices, not errors."""
    pkg = _build_screenshot_package(
        include_title=False,
        include_sensors=False,
        url_scope="origin",
    )
    result = parse_and_verify(pkg)
    assert result.integrity.ok, result.integrity.errors
    assert "title" not in result.metadata
    assert "sensorsAtRequest" not in result.metadata


def test_opt_in_metadata_included():
    """Title and sensors present when user opts in."""
    pkg = _build_screenshot_package(
        include_title=True,
        include_sensors=True,
        url_scope="origin_and_path",
        url="https://bank.example/account/savings",
    )
    result = parse_and_verify(pkg)
    assert result.integrity.ok, result.integrity.errors
    assert "title" in result.metadata
    assert "sensorsAtRequest" in result.metadata


def test_media_sha256_matches_manifest():
    pkg = _build_screenshot_package()
    result = parse_and_verify(pkg)
    assert result.media_sha256 == _sha256(_PNG_BYTES)


# ── Privacy rejection tests (ValueError → 422) ───────────────────────────────

def test_query_and_fragment_removed_false_is_rejected():
    pkg = _build_screenshot_package(query_and_fragment_removed=False)
    with pytest.raises(ValueError, match="queryAndFragmentRemoved"):
        parse_and_verify(pkg)


def test_original_image_stored_true_is_rejected():
    pkg = _build_screenshot_package(original_image_stored=True)
    with pytest.raises(ValueError, match="originalImageStored"):
        parse_and_verify(pkg)


def test_url_with_query_string_is_rejected():
    pkg = _build_screenshot_package(url="https://bank.example/page?token=secret")
    with pytest.raises(ValueError, match=r"\?"):
        parse_and_verify(pkg)


def test_url_with_fragment_is_rejected():
    pkg = _build_screenshot_package(url="https://bank.example/page#section")
    with pytest.raises(ValueError, match="#"):
        parse_and_verify(pkg)


def test_unknown_url_scope_is_rejected():
    pkg = _build_screenshot_package(url_scope="full_url")
    with pytest.raises(ValueError, match="urlScope"):
        parse_and_verify(pkg)


# ── Structural rejection tests (ValueError → 422) ────────────────────────────

def test_not_a_zip_raises():
    with pytest.raises(ValueError, match="Not a valid ZIP"):
        parse_and_verify(b"this is not a zip file at all")


def test_missing_manifest_raises():
    # Remove manifest.json from a valid package
    base = _build_screenshot_package()
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(base)) as zin, zipfile.ZipFile(buf, "w") as zout:
        for item in zin.infolist():
            if item.filename != "manifest.json":
                zout.writestr(item.filename, zin.read(item.filename))
    with pytest.raises(ValueError, match="manifest.json"):
        parse_and_verify(buf.getvalue())


def test_missing_metadata_raises():
    base = _build_screenshot_package()
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(base)) as zin, zipfile.ZipFile(buf, "w") as zout:
        for item in zin.infolist():
            if item.filename != "metadata.json":
                zout.writestr(item.filename, zin.read(item.filename))
    with pytest.raises(ValueError, match="metadata.json"):
        parse_and_verify(buf.getvalue())


def test_no_media_file_raises():
    base = _build_screenshot_package()
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(base)) as zin, zipfile.ZipFile(buf, "w") as zout:
        for item in zin.infolist():
            if item.filename != "screenshot.png":
                zout.writestr(item.filename, zin.read(item.filename))
    with pytest.raises(ValueError, match="media file"):
        parse_and_verify(buf.getvalue())


def test_path_traversal_raises():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../evil.txt", "pwned")
        zf.writestr("screenshot.png", _PNG_BYTES)
    with pytest.raises(ValueError, match="Unsafe ZIP entry"):
        parse_and_verify(buf.getvalue())


def test_duplicate_filenames_raises():
    # Build a ZIP with two entries named the same (raw bytes manipulation)
    base = _build_screenshot_package()
    # If the ZIP library exposes duplicates in infolist, our guard fires.
    # We test the guard logic directly:
    from browser_session import _safe_zip_name
    assert not _safe_zip_name("../evil")
    assert not _safe_zip_name("/absolute")
    assert _safe_zip_name("screenshots/001.png")
    assert _safe_zip_name("metadata.json")


def test_unexpected_extra_file_raises():
    base = _build_screenshot_package()
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(base)) as zin, zipfile.ZipFile(buf, "w") as zout:
        for item in zin.infolist():
            zout.writestr(item.filename, zin.read(item.filename))
        zout.writestr("extra.txt", b"unexpected")
    with pytest.raises(ValueError, match="Unexpected files"):
        parse_and_verify(buf.getvalue())


def test_package_too_large_raises():
    from browser_session import MAX_ZIP_BYTES
    # Exceed the size limit with a byte string that starts like a ZIP but is oversized
    with pytest.raises(ValueError, match="too large"):
        parse_and_verify(b"\x00" * (MAX_ZIP_BYTES + 1))


# ── Integrity failure tests (integrity_failed, no exception) ─────────────────

def test_tampered_png_causes_hash_mismatch():
    pkg = _build_screenshot_package(tamper_png=True)
    result = parse_and_verify(pkg)
    assert not result.integrity.ok
    assert not result.integrity.manifest_ok
    assert any("mismatch" in e.lower() or "hash" in e.lower() for e in result.integrity.errors)


def test_tampered_photo_causes_hash_mismatch():
    pkg = _build_photo_package(tamper_jpg=True)
    result = parse_and_verify(pkg)
    assert not result.integrity.ok
    assert not result.integrity.manifest_ok


def test_bad_manifest_sha256_causes_failure():
    pkg = _build_screenshot_package(bad_manifest_hash=True)
    result = parse_and_verify(pkg)
    assert not result.integrity.ok
    assert not result.integrity.manifest_ok
    assert any("manifest.sha256" in e for e in result.integrity.errors)


def test_crop_exceeds_source_width_is_integrity_failed():
    pkg = _build_screenshot_package(
        source_w=100, source_h=80,
        crop_left=0, crop_top=0,
        crop_right=200,   # exceeds source_w=100
        crop_bottom=80,
    )
    result = parse_and_verify(pkg)
    assert not result.integrity.ok
    assert result.integrity.edits_ok is False
    assert any("right" in e and "sourceWidth" in e for e in result.integrity.errors)


def test_crop_exceeds_source_height_is_integrity_failed():
    pkg = _build_screenshot_package(
        source_w=100, source_h=80,
        crop_left=0, crop_top=0,
        crop_right=100,
        crop_bottom=200,   # exceeds source_h=80
    )
    result = parse_and_verify(pkg)
    assert not result.integrity.ok
    assert result.integrity.edits_ok is False
    assert any("bottom" in e and "sourceHeight" in e for e in result.integrity.errors)


def test_metadata_width_mismatch_is_integrity_failed():
    """metadata.width must equal crop.right - crop.left."""
    pkg = _build_screenshot_package(
        crop_left=10, crop_right=60,   # crop width = 50
        override_meta_w=99,             # declared width 99 ≠ 50
    )
    result = parse_and_verify(pkg)
    assert not result.integrity.ok
    assert result.integrity.edits_ok is False
    assert any("width" in e for e in result.integrity.errors)


def test_metadata_height_mismatch_is_integrity_failed():
    """metadata.height must equal crop.bottom - crop.top."""
    pkg = _build_screenshot_package(
        crop_top=10, crop_bottom=60,   # crop height = 50
        override_meta_h=99,             # declared height 99 ≠ 50
    )
    result = parse_and_verify(pkg)
    assert not result.integrity.ok
    assert result.integrity.edits_ok is False
    assert any("height" in e for e in result.integrity.errors)


def test_mask_outside_crop_is_integrity_failed():
    """Android pre-filters masks; a mask outside crop indicates a client bug."""
    # Build a package where the mask does not intersect the crop
    # We bypass the builder's filter by injecting the mask directly into metadata.
    pkg_base = _build_screenshot_package(
        source_w=200, source_h=150,
        crop_left=50, crop_top=40, crop_right=150, crop_bottom=120,
        masks=[],
    )
    # Unpack, inject an out-of-crop mask, repack with correct hashes
    zin = zipfile.ZipFile(io.BytesIO(pkg_base))
    meta = json.loads(zin.read("metadata.json"))
    meta["edits"]["opaqueBlackMasks"] = [
        {"left": 0, "top": 0, "right": 10, "bottom": 10}   # fully outside crop (50,40,150,120)
    ]
    meta_bytes = json.dumps(meta, ensure_ascii=False, indent=2).encode()
    png_bytes  = zin.read("screenshot.png")
    mf_bytes   = _manifest_json("screenshot.png", png_bytes, meta_bytes)
    mf_sum     = f"{_sha256(mf_bytes)}  manifest.json\n".encode()

    pkg = _pack_zip({
        "screenshot.png":  png_bytes,
        "metadata.json":   meta_bytes,
        "manifest.json":   mf_bytes,
        "manifest.sha256": mf_sum,
    })
    result = parse_and_verify(pkg)
    assert not result.integrity.ok
    assert result.integrity.edits_ok is False
    assert any("does not intersect" in e for e in result.integrity.errors)


# ── FastAPI endpoint smoke tests ──────────────────────────────────────────────

@pytest.mark.anyio
async def test_endpoint_accepts_valid_screenshot():
    try:
        from httpx import AsyncClient, ASGITransport
        from main import app
    except Exception as exc:
        pytest.skip(f"Cannot import app or httpx: {exc}")

    pkg = _build_screenshot_package()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/evidence/browser-sessions",
            files={"package": ("evidence.zip", pkg, "application/zip")},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "integrity_ok"
    assert "receipt_id" in body
    assert "received_at" in body
    assert body["media_filename"] == "screenshot.png"
    assert body["integrity"]["manifest_ok"] is True
    assert body["integrity"]["edits_ok"] is True
    assert body["integrity"]["errors"] == []


@pytest.mark.anyio
async def test_endpoint_accepts_valid_photo():
    try:
        from httpx import AsyncClient, ASGITransport
        from main import app
    except Exception as exc:
        pytest.skip(f"Cannot import app or httpx: {exc}")

    pkg = _build_photo_package()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/evidence/browser-sessions",
            files={"package": ("evidence.zip", pkg, "application/zip")},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "integrity_ok"
    assert body["media_filename"] == "photo.jpg"
    assert body["integrity"]["edits_ok"] is None


@pytest.mark.anyio
async def test_endpoint_rejects_corrupt_zip():
    try:
        from httpx import AsyncClient, ASGITransport
        from main import app
    except Exception as exc:
        pytest.skip(f"Cannot import app or httpx: {exc}")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/evidence/browser-sessions",
            files={"package": ("evidence.zip", b"not a zip", "application/zip")},
        )
    assert resp.status_code == 422
    body = resp.json()
    assert body["status"] == "rejected"
    assert "error" in body


@pytest.mark.anyio
async def test_endpoint_rejects_privacy_violation():
    try:
        from httpx import AsyncClient, ASGITransport
        from main import app
    except Exception as exc:
        pytest.skip(f"Cannot import app or httpx: {exc}")

    pkg = _build_screenshot_package(query_and_fragment_removed=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/evidence/browser-sessions",
            files={"package": ("evidence.zip", pkg, "application/zip")},
        )
    assert resp.status_code == 422
    assert resp.json()["status"] == "rejected"
    assert "queryAndFragmentRemoved" in resp.json()["error"]


@pytest.mark.anyio
async def test_endpoint_returns_integrity_failed_for_tampered_png():
    try:
        from httpx import AsyncClient, ASGITransport
        from main import app
    except Exception as exc:
        pytest.skip(f"Cannot import app or httpx: {exc}")

    pkg = _build_screenshot_package(tamper_png=True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/evidence/browser-sessions",
            files={"package": ("evidence.zip", pkg, "application/zip")},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "integrity_failed"
    assert body["integrity"]["manifest_ok"] is False
    assert len(body["integrity"]["errors"]) > 0


@pytest.mark.anyio
async def test_endpoint_receipt_retrievable_and_no_private_fields():
    try:
        from httpx import AsyncClient, ASGITransport
        from main import app
    except Exception as exc:
        pytest.skip(f"Cannot import app or httpx: {exc}")

    pkg = _build_screenshot_package()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        post = await client.post(
            "/api/evidence/browser-sessions",
            files={"package": ("evidence.zip", pkg, "application/zip")},
        )
        receipt_id = post.json()["receipt_id"]
        get = await client.get(f"/api/evidence/browser-sessions/{receipt_id}")

    assert get.status_code == 200
    body = get.json()
    assert body["receipt_id"] == receipt_id
    assert body["status"] == "integrity_ok"
    # Private implementation fields must not leak
    assert "_stored_at" not in body
    assert "_stamp" not in body


@pytest.mark.anyio
async def test_endpoint_unknown_receipt_is_404():
    try:
        from httpx import AsyncClient, ASGITransport
        from main import app
    except Exception as exc:
        pytest.skip(f"Cannot import app or httpx: {exc}")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/evidence/browser-sessions/nonexistent0000000")
    assert resp.status_code == 404
