"""
browser_session.py — Parsing and integrity verification for Leima Android evidence packages.

─── Current single-capture format (schemaVersion=1) ────────────────────────────────────

ZIP contains exactly:
    screenshot.png  OR  photo.jpg   — final processed image; original is never stored
    metadata.json                   — capture metadata (see fields below)
    manifest.json                   — file hash manifest
    manifest.sha256                 — hash of manifest.json

manifest.json:
    {
      "schemaVersion": 1,
      "algorithm": "SHA-256",
      "files": { "<media>": "<hex>", "metadata.json": "<hex>" }
    }

manifest.sha256 (sha256sum format, two spaces):
    "<sha256hex>  manifest.json\\n"

metadata.json fields for screenshot packages (after editor):
    kind                 "webview_viewport"
    requestedAt          ISO-8601 device time at capture request
    url                  sanitised URL (query and fragment always removed)
    width                final image pixel width  (= crop.right − crop.left)
    height               final image pixel height (= crop.bottom − crop.top)
    schemaVersion        1
    appVersion           app version string
    device               {manufacturer, model, androidApi, androidRelease}
    trust                fixed disclaimer string
    edits                see below (present for screenshots, absent for photos)
    privacy              see below (present for screenshots, absent for photos)

edits sub-object:
    version              1 (only supported value)
    coordinateSpace      "source viewport pixels; right and bottom exclusive"
    sourceWidth          original captured viewport width in pixels
    sourceHeight         original captured viewport height in pixels
    crop                 {left, top, right, bottom} — source px, right/bottom exclusive
    opaqueBlackMasks     [{left, top, right, bottom}, ...] — in source coordinates;
                         only masks that intersect the crop are included (Android pre-filters)

privacy sub-object:
    urlScope             "origin" or "origin_and_path"
    queryAndFragmentRemoved  true  (always; rejected if false)
    titleIncluded        bool  (false = title omitted; valid privacy choice)
    sensorsIncluded      bool  (false = sensors omitted; valid privacy choice)
    originalImageStored  false (always; rejected if true)

─── Future session format ───────────────────────────────────────────────────────────────

Not yet implemented in Android. A future schema_version or explicit package_type field
will distinguish session packages. Session packages will add session.json and events.jsonl.
Each capture in a session carries its own edits and privacy fields. The session format
is versioned separately from the single-capture format.

─── Privacy enforcement ─────────────────────────────────────────────────────────────────

The following raise ValueError (HTTP 422 "rejected"), not merely integrity_failed:
  - privacy.queryAndFragmentRemoved is not true
  - privacy.originalImageStored is not false
  - privacy.urlScope is not "origin" or "origin_and_path"
  - URL contains "?" or "#" regardless of privacy declaration

Missing title, path, or sensor data is a valid privacy choice and is never an error.
The server never fetches URLs from the package.
Images are not stored in server memory after reception.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
import re
import warnings
from urllib.parse import urlsplit
from collections import deque
from PIL import Image, UnidentifiedImageError
from dataclasses import dataclass, field

# ── Limits ─────────────────────────────────────────────────────────────────────
MAX_ZIP_BYTES         = 50 * 1024 * 1024   # 50 MB compressed
MAX_UNZIPPED_BYTES    = 100 * 1024 * 1024  # 100 MB total uncompressed
MAX_MEDIA_BYTES       = 20 * 1024 * 1024   # 20 MB for the image file
MAX_IMAGE_PIXELS = 25_000_000


class EvidenceBodyLimitMiddleware:
    """Bound multipart bodies before FastAPI parses/spools an uploaded file."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('method') != 'POST' or scope.get('path') != '/api/evidence/browser-sessions':
            return await self.app(scope, receive, send)
        limit = MAX_ZIP_BYTES + 1024 * 1024  # bounded multipart overhead
        chunks = deque()
        size = 0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            size += len(message.get('body', b''))
            if size > limit:
                await send({'type': 'http.response.start', 'status': 413, 'headers': [(b'content-type', b'application/json')]})
                await send({'type': 'http.response.body', 'body': b'{"status":"rejected","error":"Upload too large"}'})
                return
            chunks.append(message)
            if not message.get('more_body', False):
                break
        async def replay():
            return chunks.popleft() if chunks else await receive()
        await self.app(scope, replay, send)

SUPPORTED_SCHEMA_VERSIONS: frozenset[int] = frozenset({1})
KNOWN_MEDIA_NAMES: frozenset[str] = frozenset({"screenshot.png", "photo.jpg"})
SUPPORTED_EDITS_VERSIONS: frozenset[int] = frozenset({1})
VALID_URL_SCOPES: frozenset[str] = frozenset({"origin", "origin_and_path"})


# ── Result types ───────────────────────────────────────────────────────────────

@dataclass
class IntegrityResult:
    manifest_ok: bool = False
    # None = field absent (valid for old packages or photos); True/False if present
    edits_ok: bool | None = None
    privacy_ok: bool | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return (
            self.manifest_ok
            and self.edits_ok is not False
            and self.privacy_ok is not False
            and not self.errors
        )


@dataclass
class ParsedCapture:
    media_filename: str       # "screenshot.png" or "photo.jpg"
    media_sha256: str         # verified hex digest from manifest.files
    metadata: dict            # parsed metadata; receipt stores only a limited summary
    integrity: IntegrityResult


# ── Internal helpers ───────────────────────────────────────────────────────────

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_zip_name(name: str) -> bool:
    """True if the ZIP entry path has no traversal or absolute components."""
    normalized = name.replace("\\", "/")
    if normalized.startswith("/"):
        return False
    return ".." not in normalized.split("/") and bool(normalized)


def _int_field(obj: dict, key: str, errors: list[str]) -> int | None:
    """Extract an integer field; append to errors and return None if missing or wrong type."""
    val = obj.get(key)
    if type(val) is not int:
        errors.append(f"edits.{key} must be an integer, got {type(val).__name__!r}")
        return None
    return val


def _rect_fields(obj: dict, prefix: str, errors: list[str]) -> tuple[int, int, int, int] | None:
    """Extract left/top/right/bottom from a dict; return None if any field is invalid."""
    left  = obj.get("left")
    top   = obj.get("top")
    right = obj.get("right")
    bottom = obj.get("bottom")
    for name, val in [("left", left), ("top", top), ("right", right), ("bottom", bottom)]:
        if type(val) is not int:
            errors.append(f"{prefix}.{name} must be an integer, got {type(val).__name__!r}")
            return None
    return left, top, right, bottom  # type: ignore[return-value]


def _validate_edits(meta: dict) -> tuple[bool | None, list[str]]:
    """
    Validate the edits sub-object.  Returns (ok, errors).
    ok=None means no edits field present (not an error).
    """
    edits = meta.get("edits")
    if edits is None:
        return None, []
    if not isinstance(edits, dict):
        raise ValueError('edits must be an object')

    errors: list[str] = []

    version = edits.get("version")
    if type(version) is not int:
        raise ValueError('edits.version must be an integer')
    if version not in SUPPORTED_EDITS_VERSIONS:
        errors.append(f"edits.version {version!r} not supported (supported: {sorted(SUPPORTED_EDITS_VERSIONS)})")
        return False, errors

    source_w = _int_field(edits, "sourceWidth",  errors)
    source_h = _int_field(edits, "sourceHeight", errors)
    if source_w is None or source_h is None:
        return False, errors
    if source_w <= 0 or source_h <= 0:
        errors.append(f"edits.sourceWidth/sourceHeight must be positive, got {source_w}x{source_h}")
        return False, errors

    # Crop validation
    crop = edits.get("crop")
    if not isinstance(crop, dict):
        errors.append("edits.crop must be an object")
        return False, errors

    coords = _rect_fields(crop, "edits.crop", errors)
    if coords is None:
        return False, errors
    cl, ct, cr, cb = coords

    if cl >= cr:
        errors.append(f"edits.crop: left ({cl}) must be < right ({cr})")
    if ct >= cb:
        errors.append(f"edits.crop: top ({ct}) must be < bottom ({cb})")
    if cl < 0 or ct < 0:
        errors.append(f"edits.crop: left/top must be >= 0, got ({cl}, {ct})")
    if cr > source_w:
        errors.append(f"edits.crop: right ({cr}) exceeds sourceWidth ({source_w})")
    if cb > source_h:
        errors.append(f"edits.crop: bottom ({cb}) exceeds sourceHeight ({source_h})")

    if errors:
        return False, errors

    crop_w = cr - cl
    crop_h = cb - ct

    # Final image dimensions must match crop
    meta_w = meta.get("width")
    meta_h = meta.get("height")
    if not isinstance(meta_w, int) or not isinstance(meta_h, int):
        errors.append("metadata width/height must be integers when edits are present")
        return False, errors
    if meta_w != crop_w:
        errors.append(
            f"metadata.width ({meta_w}) does not match crop width ({crop_w} = {cr}−{cl})"
        )
    if meta_h != crop_h:
        errors.append(
            f"metadata.height ({meta_h}) does not match crop height ({crop_h} = {cb}−{ct})"
        )

    # Mask validation: each mask must intersect the crop rectangle
    masks_raw = edits.get("opaqueBlackMasks", [])
    if not isinstance(masks_raw, list):
        errors.append("edits.opaqueBlackMasks must be an array")
        return False, errors

    for i, mask in enumerate(masks_raw):
        if not isinstance(mask, dict):
            errors.append(f"edits.opaqueBlackMasks[{i}] must be an object")
            continue
        mc = _rect_fields(mask, f"edits.opaqueBlackMasks[{i}]", errors)
        if mc is None:
            continue
        ml, mt, mr, mb = mc
        # Intersection with crop: [max(cl,ml), max(ct,mt)] to [min(cr,mr), min(cb,mb)]
        ix_l = max(cl, ml); ix_t = max(ct, mt)
        ix_r = min(cr, mr); ix_b = min(cb, mb)
        if ix_r <= ix_l or ix_b <= ix_t:
            errors.append(
                f"edits.opaqueBlackMasks[{i}] does not intersect crop "
                f"(mask=({ml},{mt},{mr},{mb}), crop=({cl},{ct},{cr},{cb}))"
            )

    ok = len(errors) == 0
    return ok, errors


def _validate_privacy(meta: dict) -> list[str]:
    """
    Validate privacy sub-object.
    Raises ValueError for outright privacy violations (rejected package).
    Returns a list of softer integrity errors (should be empty for well-formed packages).
    """
    privacy = meta.get("privacy")
    if privacy is None:
        return []  # absent in old packages and photos; not an error
    if not isinstance(privacy, dict):
        raise ValueError('privacy must be an object')

    # Hard rejections
    qfr = privacy.get("queryAndFragmentRemoved")
    if qfr is not True:
        raise ValueError(
            "privacy.queryAndFragmentRemoved must be true; "
            f"package declares {qfr!r} — rejected to prevent query parameter leakage"
        )

    ois = privacy.get("originalImageStored")
    if ois is not False:
        raise ValueError(
            "privacy.originalImageStored must be false; "
            f"package declares {ois!r} — rejected"
        )

    url_scope = privacy.get("urlScope")
    if not isinstance(url_scope, str) or url_scope not in VALID_URL_SCOPES:
        raise ValueError(
            f"privacy.urlScope {url_scope!r} is not a recognised value "
            f"(accepted: {sorted(VALID_URL_SCOPES)})"
        )

    # URL content check: query params and fragment must be absent regardless of declaration
    url = str(meta.get("url", ""))
    if "?" in url:
        raise ValueError(
            "URL contains a query string ('?') despite queryAndFragmentRemoved=true — rejected"
        )
    if "#" in url:
        raise ValueError(
            "URL contains a fragment ('#') despite queryAndFragmentRemoved=true — rejected"
        )

    for flag in ('titleIncluded', 'sensorsIncluded'):
        if type(privacy.get(flag)) is not bool:
            raise ValueError(f'privacy.{flag} must be boolean')
    if not privacy['titleIncluded'] and 'title' in meta:
        raise ValueError('title present despite titleIncluded=false')
    if not privacy['sensorsIncluded'] and any(key in meta for key in ('sensorsAtRequest', 'sensorsAtCompletion')):
        raise ValueError('sensor data present despite sensorsIncluded=false')
    if not isinstance(meta.get('url'), str):
        raise ValueError('url must be a string')
    parts = urlsplit(url)
    if parts.scheme != 'https' or not parts.hostname or parts.username is not None or parts.password is not None:
        raise ValueError('url must be HTTPS without credentials')
    if url_scope == 'origin' and parts.path not in ('', '/'):
        raise ValueError('URL path present despite urlScope=origin')

    return []


# ── Main entry point ───────────────────────────────────────────────────────────

def parse_and_verify(zip_bytes: bytes) -> ParsedCapture:
    if len(zip_bytes) > MAX_ZIP_BYTES:
        raise ValueError('Package too large')
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
            return _parse_and_verify(zip_bytes, archive)
    except zipfile.BadZipFile as exc:
        raise ValueError('Not a valid ZIP file') from exc
    except (NotImplementedError, RuntimeError, UnicodeError, RecursionError) as exc:
        raise ValueError('Invalid or unsupported evidence ZIP/JSON') from exc


def _parse_and_verify(zip_bytes: bytes, zf: zipfile.ZipFile) -> ParsedCapture:
    """
    Parse and integrity-check a single-capture evidence ZIP.

    Raises ValueError for:
      - structural problems (not a ZIP, missing files, bad JSON, unknown schema version)
      - path traversal or duplicate filenames
      - size limits exceeded
      - privacy violations (query params in URL, queryAndFragmentRemoved=false, etc.)

    Returns ParsedCapture for everything else.  Check .integrity.ok and
    .integrity.errors for hash mismatches, invalid edits coordinates, etc.
    A failed integrity check does NOT raise.
    """
    if len(zip_bytes) > MAX_ZIP_BYTES:
        raise ValueError(
            f"Package too large: {len(zip_bytes) // 1024 // 1024} MB "
            f"(max {MAX_ZIP_BYTES // 1024 // 1024} MB)"
        )

    result = IntegrityResult()

    # ── 1. Safety: path traversal and duplicates ────────────────────────────────
    info_list = zf.infolist()
    names = [info.filename for info in info_list]

    for name in names:
        if not _safe_zip_name(name):
            raise ValueError(f"Unsafe ZIP entry name: {name!r}")

    if len(names) != len(set(names)):
        raise ValueError("Duplicate filenames in ZIP")

    # ── 2. Uncompressed size limit ─────────────────────────────────────────────
    total_unzipped = sum(info.file_size for info in info_list)
    if total_unzipped > MAX_UNZIPPED_BYTES:
        raise ValueError(
            f"Uncompressed content too large: {total_unzipped // 1024 // 1024} MB "
            f"(max {MAX_UNZIPPED_BYTES // 1024 // 1024} MB)"
        )

    name_set = set(names)

    # ── 3. Required files ──────────────────────────────────────────────────────
    for required in ("manifest.json", "manifest.sha256", "metadata.json"):
        if required not in name_set:
            raise ValueError(f"Missing required file: {required!r}")

    media_name = next((n for n in KNOWN_MEDIA_NAMES if n in name_set), None)
    if media_name is None:
        raise ValueError(
            f"No recognised media file in ZIP "
            f"(expected one of {sorted(KNOWN_MEDIA_NAMES)}); "
            f"found: {sorted(name_set)}"
        )

    expected_names = {media_name, "metadata.json", "manifest.json", "manifest.sha256"}
    unexpected = name_set - expected_names
    if unexpected:
        raise ValueError(f"Unexpected files in ZIP: {sorted(unexpected)}")
    for entry in info_list:
        limit = MAX_MEDIA_BYTES if entry.filename == media_name else 4 * 1024 * 1024
        if entry.file_size > limit:
            raise ValueError('ZIP entry too large')

    # ── 4. manifest.sha256 → manifest.json ─────────────────────────────────────
    manifest_raw = zf.read("manifest.json")
    checksum_line = zf.read("manifest.sha256").decode("utf-8", errors="replace").strip()

    # Expected format: "<sha256hex>  manifest.json"
    parts = checksum_line.split(None, 1)
    declared_manifest_hash = parts[0] if parts else ""
    actual_manifest_hash = _sha256(manifest_raw)

    manifest_sha_ok = checksum_line == actual_manifest_hash + '  manifest.json'
    if not manifest_sha_ok:
        result.errors.append(
            f"manifest.sha256 mismatch: "
            f"declared={declared_manifest_hash!r} actual={actual_manifest_hash!r}"
        )

    # ── 5. Parse manifest.json ─────────────────────────────────────────────────
    try:
        manifest: dict = json.loads(manifest_raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"manifest.json is not valid JSON: {exc}") from exc

    if not isinstance(manifest, dict):
        raise ValueError('manifest.json must be an object')
    if type(manifest.get('schemaVersion')) is not int or manifest.get("schemaVersion") not in SUPPORTED_SCHEMA_VERSIONS:
        raise ValueError(f"Unsupported manifest schemaVersion: {manifest.get('schemaVersion')!r}")

    if manifest.get("algorithm") != "SHA-256":
        raise ValueError(f"Unsupported hash algorithm: {manifest.get('algorithm')!r}")

    declared_files: dict[str, str] = manifest.get("files", {})
    if not isinstance(declared_files, dict) or set(declared_files) != {media_name, 'metadata.json'}:
        raise ValueError('manifest.files must declare exactly the media and metadata.json hashes')
    if any(not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value) for value in declared_files.values()):
        raise ValueError('Invalid SHA-256 digest in manifest.files')

    # ── 6. Verify declared file hashes ────────────────────────────────────────
    all_hashes_ok = True
    media_sha256 = ""

    for fname, expected_hash in declared_files.items():
        if fname not in name_set:
            result.errors.append(f"manifest.files declares missing file: {fname!r}")
            all_hashes_ok = False
            continue
        actual = _sha256(zf.read(fname))
        if actual != expected_hash:
            result.errors.append(
                f"Hash mismatch for {fname!r}: "
                f"declared={expected_hash!r} actual={actual!r}"
            )
            all_hashes_ok = False
        if fname == media_name:
            media_sha256 = actual

    result.manifest_ok = manifest_sha_ok and all_hashes_ok

    # ── 7. Media size limit ─────────────────────────────────────────────────────
    media_info = zf.getinfo(media_name)
    if media_info.file_size > MAX_MEDIA_BYTES:
        raise ValueError(
            f"Media file too large: {media_info.file_size // 1024 // 1024} MB "
            f"(max {MAX_MEDIA_BYTES // 1024 // 1024} MB)"
        )

    # ── 8. Parse metadata.json ────────────────────────────────────────────────
    try:
        meta: dict = json.loads(zf.read("metadata.json"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"metadata.json is not valid JSON: {exc}") from exc

    if not isinstance(meta, dict):
        raise ValueError('metadata.json must be an object')
    if type(meta.get('schemaVersion')) is not int or meta.get("schemaVersion") not in SUPPORTED_SCHEMA_VERSIONS:
        raise ValueError(f"Unsupported metadata schemaVersion: {meta.get('schemaVersion')!r}")

    # ── 9. Privacy validation (raises on violation) ────────────────────────────
    _validate_privacy(meta)  # raises ValueError on any privacy violation
    result.privacy_ok = True if meta.get('privacy') is not None else None

    # ── 10. Edits validation ───────────────────────────────────────────────────
    edits_ok, edits_errors = _validate_edits(meta)
    result.edits_ok = edits_ok
    result.errors.extend(edits_errors)

    # Decode the actual image, not just the sender's dimension declarations.
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            media = zf.read(media_name)
            with Image.open(io.BytesIO(media)) as image:
                expected_format = 'PNG' if media_name == 'screenshot.png' else 'JPEG'
                if image.format != expected_format or image.width * image.height > MAX_IMAGE_PIXELS:
                    raise ValueError('Unsupported image format or dimensions')
                dimensions = image.size
                image.verify()
            with Image.open(io.BytesIO(media)) as image:
                image.load()
            if media_name == 'screenshot.png' and dimensions != (meta.get('width'), meta.get('height')):
                result.errors.append('Actual image dimensions do not match metadata width/height')
    except (OSError, ValueError, SyntaxError, UnidentifiedImageError, Image.DecompressionBombWarning, Image.DecompressionBombError):
        result.errors.append('Invalid image or image exceeds pixel limit')

    return ParsedCapture(
        media_filename=media_name,
        media_sha256=media_sha256,
        metadata=meta,
        integrity=result,
    )
