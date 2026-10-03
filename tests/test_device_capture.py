"""POST /api/stamp/device-capture: phone browser captures as a stamped, device_captured source."""
import hashlib
import io
import json
import zipfile

import pytest


def browser_package(tamper=False, kind="browser", text="Osinko on 1,20 euroa osakkeelta.") -> bytes:
    metadata = {"schemaVersion": 1, "kind": kind, "captureStatus": "complete", "missing": [],
                "requestedAt": "2026-10-04T09:15:00Z", "url": "https://yhtio.example/sijoittajat?token=REDACTED",
                "title": "Sijoittajat", "clock": {"source": "device_wall_clock", "verified": False},
                "appVersion": "0.1.0", "webViewVersion": "129", "exportPolicy": "AGENT_READABLE"}
    files = {"metadata.json": json.dumps(metadata).encode(), "observation.json": b"{}",
             "dom.html": b"<html><body>Osinko</body></html>", "visible-text.txt": text.encode(), "screenshot.png": b"png"}
    manifest = json.dumps({"schemaVersion": 1, "algorithm": "SHA-256", "kind": kind,
                           "files": {n: hashlib.sha256(d).hexdigest() for n, d in files.items()}}).encode()
    if tamper:
        files["visible-text.txt"] += b" (muokattu)"
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for name, data in {**files, "manifest.json": manifest,
                           "manifest.sha256": hashlib.sha256(manifest).hexdigest() + "  manifest.json\n"}.items():
            z.writestr(name, data)
    return out.getvalue()


@pytest.fixture
def stamp(client, app_module, monkeypatch):
    calls, uploads = [], []

    def analyse(question, contents, source_context=None):
        calls.append({"question": question, "contents": contents, "source_context": source_context})
        return {"passes": [("Supporting", "Text states 1,20."), ("Opposing", "None."), ("Verdict", "Supported.")],
                "summary_verdict": "Supported by the captured page.", "verdict_category": "Supported",
                "timestamp": "2026-10-04 09:20:00 UTC", "prompt_log": []}

    def upload(data, content_type, tags):
        uploads.append(json.loads(data))
        return "dev-tx"

    monkeypatch.setattr(app_module, "analyse", analyse)
    monkeypatch.setattr(app_module, "_irys_upload", upload)

    def post(package: bytes, claim="Osinko on 1,20 euroa.", **form):
        return client.post("/api/stamp/device-capture", data={"claim": claim, **form},
                           files={"package": ("capture.zip", package, "application/zip")})
    post.calls, post.uploads = calls, uploads
    return post


def test_capture_is_stamped_as_device_captured_with_three_separate_layers(stamp):
    package = browser_package()
    r = stamp(package, cited_passage="1,20 euroa")
    assert r.status_code == 200, r.text
    body = r.json()
    source, verdict, evidence = body["source"], body["verdict"], body["evidence"]

    assert source["provenance"] == "device_captured"
    assert "fetched_by_leima" not in r.text
    assert "did not fetch" in source["acquired_by"]
    assert source["capture"]["package_sha256"] == hashlib.sha256(package).hexdigest()
    assert source["capture"]["clock"]["verified"] is False
    assert source["url"] == "https://yhtio.example/sijoittajat?token=REDACTED"
    assert source["cited_passage"] == "1,20 euroa"

    assert verdict["nature"] == "ai_assessment" and verdict["category"] == "Supported" and verdict["model"]
    assert evidence["nature"] == "hash_commitment"
    assert evidence["input_hash"] == hashlib.sha256(package).hexdigest()
    assert evidence["arweave_tx"] == "dev-tx"
    assert evidence["storage"]["status"] == "submitted" and evidence["storage"]["confirmation"] == "not_checked"
    assert body["limits"] and any("not the server's original" in limit for limit in body["limits"])

    call = stamp.calls[0]
    assert call["source_context"]["type"] == "device_capture"
    assert call["source_context"]["domain"] == "yhtio.example"
    assert "Osinko on 1,20 euroa osakkeelta." in call["contents"][0]
    assert "not fetched by Leima" in call["contents"][0]


def test_arweave_receives_only_the_hash_manifest(stamp):
    stamp(browser_package())
    (record,) = stamp.uploads
    assert set(record) <= {"stamp_format_version", "timestamp", "commit", "source_file", "files"}
    assert record["source_file"] == "source.zip"
    text = json.dumps(record)
    for private in ("Osinko", "yhtio.example", "Sijoittajat", "device_captured"):
        assert private not in text


def test_devnet_is_never_reported_as_permanent(stamp, app_module, monkeypatch):
    monkeypatch.setattr(app_module, "IRYS_NETWORK", "devnet")
    storage = stamp(browser_package()).json()["evidence"]["storage"]
    assert storage["network"] == "irys-devnet" and storage["permanent"] is False and "not a production" in storage["note"].lower()


@pytest.mark.parametrize("package,status", [
    (browser_package(tamper=True), 422),
    (b"not a zip", 422),
])
def test_invalid_packages_are_rejected_before_analysis(stamp, package, status):
    r = stamp(package)
    assert r.status_code == status
    assert stamp.calls == [] and stamp.uploads == []


def test_only_browser_captures_are_accepted(stamp):
    photo = io.BytesIO()
    files = {"photo.jpg": b"jpeg", "metadata.json": b"{}"}
    manifest = json.dumps({"schemaVersion": 1, "algorithm": "SHA-256", "kind": "photo",
                           "files": {n: hashlib.sha256(d).hexdigest() for n, d in files.items()}}).encode()
    with zipfile.ZipFile(photo, "w") as z:
        for name, data in {**files, "manifest.json": manifest,
                           "manifest.sha256": hashlib.sha256(manifest).hexdigest() + "  manifest.json\n"}.items():
            z.writestr(name, data)
    r = stamp(photo.getvalue())
    assert r.status_code == 422 and "browser" in r.json()["error"]


def test_limits_on_claim_and_size(stamp, app_module, monkeypatch):
    assert stamp(browser_package(), claim="  ").status_code == 400
    monkeypatch.setattr(app_module, "DEVICE_CAPTURE_MAX_BYTES", 100)
    assert stamp(browser_package()).status_code == 413
    assert stamp.calls == []
