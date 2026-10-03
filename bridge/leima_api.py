"""Sends an archived phone capture to Leima for an AI verdict and a hash stamp (phase F).

This exports the capture's content (DOM, text, screenshot) to Leima's server and its AI provider.
Only a hash manifest goes on to Arweave. See docs/RESEARCH_APPLIANCE_ARCHITECTURE.md section 6b.
"""
import io
import json
import os
import zipfile

import requests

from .errors import BridgeError

DEFAULT_LEIMA_URL = "https://leima.io"
MAX_UPLOAD_BYTES = 4 * 1024 * 1024  # server limit (DEVICE_CAPTURE_MAX_BYTES)


def leima_url() -> str:
    return os.environ.get("LEIMA_URL", DEFAULT_LEIMA_URL).rstrip("/")


def capture_metadata(package: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        return json.loads(archive.read("metadata.json"))


def stamp_capture(package: bytes, claim: str, cited_passage: str = "", base_url: str | None = None) -> dict:
    if len(package) > MAX_UPLOAD_BYTES:
        raise BridgeError("PACKAGE_TOO_LARGE", f"Leima accepts captures up to {MAX_UPLOAD_BYTES // 1024 // 1024} MB")
    url = f"{base_url or leima_url()}/api/stamp/device-capture"
    try:
        response = requests.post(url, data={"claim": claim, "cited_passage": cited_passage},
                                 files={"package": ("capture.zip", package, "application/zip")}, timeout=240)
    except requests.RequestException as e:
        raise BridgeError("LEIMA_UNREACHABLE", f"Could not reach {url}: {e}") from e
    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.status_code != 200:
        raise BridgeError("STAMP_FAILED", f"Leima answered {response.status_code}: {body.get('error') or response.text[:200]}")
    return body


def stamp_archived(archive, sha_prefix: str, claim: str, cited_passage: str = "", by_agent: bool = False,
                   base_url: str | None = None) -> dict:
    """Re-verifies an archived browser capture, sends it to Leima and records the stamp next to it.
    [by_agent] captures must have been agent-readable when taken; others need the person (CLI)."""
    row = archive.find(sha_prefix)
    archive.verify_entry(row["sha256"])
    if row["kind"] != "browser":
        raise BridgeError("NOT_A_BROWSER_CAPTURE", f"Only browser captures can be stamped as a web source, not {row['kind']}")
    package = (archive.root / row["path"]).read_bytes()
    if by_agent and capture_metadata(package).get("exportPolicy") != "AGENT_READABLE":
        raise BridgeError("CONTENT_WITHHELD", "This capture was local-only on the phone; only the person can send it "
                                              "to Leima: python -m bridge stamp <sha256> --claim ...")
    result = stamp_capture(package, claim, cited_passage, base_url)
    if result.get("evidence", {}).get("input_hash") != row["sha256"]:
        raise BridgeError("STAMP_MISMATCH", "Leima stamped different bytes than the archived capture")
    archive.record_stamp(row, result)
    return result
