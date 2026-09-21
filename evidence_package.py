"""Leima analysis-stamp package (ZIP) format: build and read stamp_format_version=2 packages.

Package layout (flat, fixed names):
    manifest.json
    source.<ext>
    verdict.pdf
    verdict.txt
    verdict.html
    verdict.json
    source-index.json      # optional

manifest.json:
    {
      "stamp_format_version": 2,
      "timestamp": "...",
      "commit": "...",
      "source_file": "source.<ext>",
      "files": {"<name>": "sha256:<hex>", ...},   # every content file except manifest.json/zip itself
      "stamp": {"tx_id": "...", "url": "..."}      # added only after the Arweave publish
    }

`read()` is the only entry point untrusted uploads should go through. It never extracts to
disk and never executes/renders package content; it returns validated bytes in memory.
"""
from __future__ import annotations

import hashlib
import json
import zipfile
import zlib
from dataclasses import dataclass

STAMP_FORMAT_VERSION = 2

MAX_COMPRESSED = 50 * 1024 * 1024
MAX_MEMBER_UNCOMPRESSED = 50 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED = 150 * 1024 * 1024
MAX_MANIFEST_BYTES = 1 * 1024 * 1024
MAX_MEMBERS = 8

MANIFEST_NAME = "manifest.json"
REQUIRED_VERDICT_NAMES = ("verdict.pdf", "verdict.txt", "verdict.html", "verdict.json")
OPTIONAL_NAMES = ("source-index.json",)
PACK_ORDER = ("verdict.pdf", "verdict.txt", "verdict.html", "verdict.json", "source-index.json")


class PackageFormatError(ValueError):
    """Raised for any malformed/tampered/oversized package. Always a clean input error."""


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def strip_stamp(manifest: dict) -> dict:
    return {k: v for k, v in manifest.items() if k != "stamp"}


def build_manifest(
    *,
    timestamp: str,
    commit: str,
    source_filename: str,
    source_bytes: bytes,
    verdict_pdf: bytes,
    verdict_txt: bytes,
    verdict_html: bytes,
    verdict_json: bytes,
    source_index_bytes: bytes | None = None,
) -> dict:
    files = {
        source_filename: f"sha256:{sha256_hex(source_bytes)}",
        "verdict.pdf": f"sha256:{sha256_hex(verdict_pdf)}",
        "verdict.txt": f"sha256:{sha256_hex(verdict_txt)}",
        "verdict.html": f"sha256:{sha256_hex(verdict_html)}",
        "verdict.json": f"sha256:{sha256_hex(verdict_json)}",
    }
    if source_index_bytes is not None:
        files["source-index.json"] = f"sha256:{sha256_hex(source_index_bytes)}"
    return {
        "stamp_format_version": STAMP_FORMAT_VERSION,
        "timestamp": timestamp,
        "commit": commit,
        "source_file": source_filename,
        "files": files,
    }


def pack(
    manifest: dict,
    source_filename: str,
    source_bytes: bytes,
    verdict_pdf: bytes,
    verdict_txt: bytes,
    verdict_html: bytes,
    verdict_json: bytes,
    source_index_bytes: bytes | None = None,
) -> bytes:
    import io as _io

    members = {
        source_filename: source_bytes,
        "verdict.pdf": verdict_pdf,
        "verdict.txt": verdict_txt,
        "verdict.html": verdict_html,
        "verdict.json": verdict_json,
    }
    if source_index_bytes is not None:
        members["source-index.json"] = source_index_bytes

    buf = _io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2, ensure_ascii=False))
        zf.writestr(source_filename, members[source_filename])
        for name in PACK_ORDER:
            if name in members and name != source_filename:
                zf.writestr(name, members[name])
    return buf.getvalue()


@dataclass
class Package:
    manifest: dict
    files: dict[str, bytes]  # filename -> hash-verified raw bytes (excludes manifest.json)

    @property
    def source_filename(self) -> str:
        return self.manifest["source_file"]

    @property
    def source_bytes(self) -> bytes:
        return self.files[self.source_filename]

    def verdict(self, fmt: str) -> bytes:
        return self.files[f"verdict.{fmt}"]

    @property
    def source_index_bytes(self) -> bytes | None:
        return self.files.get("source-index.json")


def _no_dup_keys(pairs):
    seen = set()
    result = {}
    for k, v in pairs:
        if k in seen:
            raise PackageFormatError(f"Duplicate JSON key: {k}")
        seen.add(k)
        result[k] = v
    return result


def _reject_unsafe_name(name: str) -> None:
    if not name or name.endswith("/"):
        raise PackageFormatError(f"Directory entries are not allowed: {name!r}")
    if name.startswith("/") or name.startswith("\\"):
        raise PackageFormatError(f"Absolute paths are not allowed: {name!r}")
    if "\\" in name:
        raise PackageFormatError(f"Backslashes are not allowed in names: {name!r}")
    if "/" in name:
        raise PackageFormatError(f"Nested paths are not allowed: {name!r}")
    if name in (".", "..") or ".." in name.split("/"):
        raise PackageFormatError(f"Path traversal is not allowed: {name!r}")


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    # Unix mode bits stored in the top 16 bits of external_attr; 0o120000 == S_IFLNK.
    mode = info.external_attr >> 16
    return (mode & 0o170000) == 0o120000


def read(data: bytes, *, max_bytes: int = MAX_COMPRESSED) -> Package:
    if len(data) > max_bytes:
        raise PackageFormatError(f"Package exceeds {max_bytes} bytes")
    if not data:
        raise PackageFormatError("Empty upload")

    import io as _io

    try:
        zf = zipfile.ZipFile(_io.BytesIO(data))
        infos = zf.infolist()
    except (zipfile.BadZipFile, EOFError, OSError, UnicodeDecodeError) as e:
        raise PackageFormatError(f"Not a valid ZIP file: {e}") from e

    if len(infos) > MAX_MEMBERS:
        raise PackageFormatError(f"Too many members in package (max {MAX_MEMBERS})")

    seen_names: set[str] = set()
    total_uncompressed = 0
    for info in infos:
        name = info.filename
        _reject_unsafe_name(name)
        if name in seen_names:
            raise PackageFormatError(f"Duplicate member name: {name}")
        seen_names.add(name)

        if _is_symlink(info):
            raise PackageFormatError(f"Symlink members are not allowed: {name}")
        if info.flag_bits & 0x1:
            raise PackageFormatError(f"Encrypted members are not allowed: {name}")
        if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            raise PackageFormatError(f"Unsupported compression method for: {name}")
        if info.file_size > MAX_MEMBER_UNCOMPRESSED:
            raise PackageFormatError(f"Member too large: {name}")
        total_uncompressed += info.file_size
        if total_uncompressed > MAX_TOTAL_UNCOMPRESSED:
            raise PackageFormatError("Package uncompressed size exceeds limit")

    if MANIFEST_NAME not in seen_names:
        raise PackageFormatError("Missing manifest.json")

    manifest_info = zf.getinfo(MANIFEST_NAME)
    if manifest_info.file_size > MAX_MANIFEST_BYTES:
        raise PackageFormatError("manifest.json exceeds size limit")

    try:
        raw_members: dict[str, bytes] = {}
        running_total = 0
        for info in infos:
            with zf.open(info) as fh:
                content = fh.read(MAX_MEMBER_UNCOMPRESSED + 1)
            if len(content) > MAX_MEMBER_UNCOMPRESSED:
                raise PackageFormatError(f"Member too large: {info.filename}")
            running_total += len(content)
            if running_total > MAX_TOTAL_UNCOMPRESSED:
                raise PackageFormatError("Package uncompressed size exceeds limit")
            raw_members[info.filename] = content
    except (zipfile.BadZipFile, RuntimeError, OSError, EOFError, zlib.error) as e:
        raise PackageFormatError(f"Corrupt package member: {e}") from e

    try:
        manifest_text = raw_members[MANIFEST_NAME].decode("utf-8")
    except UnicodeDecodeError as e:
        raise PackageFormatError(f"manifest.json is not valid UTF-8: {e}") from e
    try:
        manifest = json.loads(manifest_text, object_pairs_hook=_no_dup_keys)
    except json.JSONDecodeError as e:
        raise PackageFormatError(f"manifest.json is not valid JSON: {e}") from e

    if not isinstance(manifest, dict):
        raise PackageFormatError("manifest.json must be a JSON object")
    if manifest.get("stamp_format_version") != STAMP_FORMAT_VERSION:
        raise PackageFormatError("Unsupported or missing stamp_format_version")
    if "stamp" in manifest and not isinstance(manifest["stamp"], dict):
        raise PackageFormatError("manifest.json: stamp must be an object")

    source_filename = manifest.get("source_file")
    if not isinstance(source_filename, str) or not source_filename:
        raise PackageFormatError("manifest.json: source_file must be a non-empty string")

    files_map = manifest.get("files")
    if not isinstance(files_map, dict) or not files_map:
        raise PackageFormatError("manifest.json: files must be a non-empty object")
    for k, v in files_map.items():
        if not isinstance(k, str) or not isinstance(v, str) or not v.startswith("sha256:"):
            raise PackageFormatError("manifest.json: files entries must map name -> 'sha256:<hex>'")

    if source_filename not in files_map:
        raise PackageFormatError("manifest.json: source_file is not listed in files")
    for required in REQUIRED_VERDICT_NAMES:
        if required not in files_map:
            raise PackageFormatError(f"manifest.json: missing required file entry {required!r}")
    for name in files_map:
        if name not in REQUIRED_VERDICT_NAMES and name != source_filename and name not in OPTIONAL_NAMES:
            raise PackageFormatError(f"manifest.json: unexpected file entry {name!r}")

    expected_member_names = set(files_map.keys()) | {MANIFEST_NAME}
    if seen_names != expected_member_names:
        missing = expected_member_names - seen_names
        extra = seen_names - expected_member_names
        detail = []
        if missing:
            detail.append(f"missing: {sorted(missing)}")
        if extra:
            detail.append(f"unexpected: {sorted(extra)}")
        raise PackageFormatError(f"Package contents do not match manifest files map ({'; '.join(detail)})")

    content_files: dict[str, bytes] = {}
    for name, expected in files_map.items():
        actual_bytes = raw_members[name]
        actual_hash = f"sha256:{sha256_hex(actual_bytes)}"
        if actual_hash != expected:
            raise PackageFormatError(f"Hash mismatch for {name}")
        content_files[name] = actual_bytes

    return Package(manifest=manifest, files=content_files)
