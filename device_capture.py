"""Phone browser captures (Research Appliance `kind: browser` packages) as a Leima source.

The phone, not Leima, acquired these bytes: results built from them carry provenance
`device_captured`, never `fetched_by_leima`. Package format: docs/RESEARCH_APPLIANCE_PACKAGES.md.
Verification reuses the standalone checker in android/tools/verify_package.py.
"""
import hashlib
import io
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "android" / "tools"))
from verify_package import verify  # noqa: E402

PROVENANCE = "device_captured"
ACQUIRED_BY = "A phone running the Leima Android app (WebView). Leima's server did not fetch this source."
METHOD = ("Leima Android browser capture: DOM serialization, document.body.innerText, interactive element "
          "list and a masked PixelCopy screenshot, hashed in a SHA-256 manifest on the phone")
LIMITS = [
    "The capture is the phone's rendering of the page, not the server's original HTTP response.",
    "URL, time and certificate are reported by the phone; the device clock is not independently verified.",
    "The package is not signed by the device; integrity is relative to its own manifest.",
    "DOM, text and screenshot were captured one after another, not as an atomic snapshot.",
    "The AI verdict assesses whether the captured text supports the claim; it is not proof.",
]


class DeviceCaptureError(ValueError):
    pass


@dataclass(frozen=True)
class DeviceCapture:
    package_bytes: bytes
    package_sha256: str
    manifest_sha256: str
    metadata: dict
    visible_text: str

    @property
    def url(self) -> str:
        return self.metadata.get("url") or ""


def parse(package_bytes: bytes) -> DeviceCapture:
    try:
        info = verify(io.BytesIO(package_bytes))
    except Exception as e:  # zipfile, json and verifier errors all mean "not a valid capture"
        raise DeviceCaptureError(f"Package failed verification: {e}") from e
    if info["kind"] != "browser":
        raise DeviceCaptureError(f"Only browser captures can be stamped as a web source, not {info['kind']}")
    with zipfile.ZipFile(io.BytesIO(package_bytes)) as archive:
        manifest_bytes = archive.read("manifest.json")
        visible_text = archive.read("visible-text.txt").decode("utf-8", errors="replace")
    return DeviceCapture(
        package_bytes=package_bytes,
        package_sha256=hashlib.sha256(package_bytes).hexdigest(),
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        metadata=info["details"],
        visible_text=visible_text,
    )


def source_block(capture: DeviceCapture) -> dict:
    """The `source` part of a citation result: who acquired what, and how."""
    m = capture.metadata
    return {
        "url": capture.url or None,
        "title": m.get("title") or None,
        "captured_at": m.get("requestedAt"),
        "provenance": PROVENANCE,
        "acquired_by": ACQUIRED_BY,
        "capture": {
            "package_sha256": capture.package_sha256,
            "manifest_sha256": capture.manifest_sha256,
            "capture_status": m.get("captureStatus"),
            "missing": m.get("missing", []),
            "method": METHOD,
            "clock": m.get("clock") or {"source": "device_wall_clock", "verified": False},
            "app_version": m.get("appVersion"),
            "webview_version": m.get("webViewVersion"),
            "certificate": m.get("certificate"),
            "export_policy_at_capture": m.get("exportPolicy"),
        },
    }


def analysis_text(capture: DeviceCapture) -> str:
    m = capture.metadata
    return (
        "Web page captured on a phone with the Leima Android app (not fetched by Leima).\n"
        f"URL as reported by the phone: {capture.url or 'unknown'}\n"
        f"Title: {m.get('title') or 'unknown'}\n"
        f"Captured at (device clock, not verified): {m.get('requestedAt') or 'unknown'}\n\n"
        f"{capture.visible_text}"
    )
