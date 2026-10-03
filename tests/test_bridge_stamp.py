"""Phase F on the PC: archived phone captures -> Leima /api/stamp/device-capture -> archive record."""
import hashlib
import json
import types

import pytest

import bridge.leima_api as leima_api
from bridge import mcp_stdio
from bridge.__main__ import main
from bridge.archive import Archive
from bridge.errors import BridgeError
from tests.test_device_capture import browser_package


@pytest.fixture
def leima(client, app_module, monkeypatch):
    """Routes the bridge's HTTP call to the real endpoint in-process, with AI and Arweave mocked."""
    calls = []
    monkeypatch.setattr(app_module, "analyse", lambda q, c, source_context=None: {
        "passes": [("Supporting", "Yes."), ("Opposing", "No."), ("Verdict", "Supported.")],
        "summary_verdict": "Supported.", "verdict_category": "Supported",
        "timestamp": "2026-10-04 10:00:00 UTC", "prompt_log": []})
    monkeypatch.setattr(app_module, "_irys_upload", lambda data, ct, tags: "tx-123")

    def post(url, data=None, files=None, timeout=None):
        calls.append(url)
        r = client.post("/api/stamp/device-capture", data=data, files=files)
        return types.SimpleNamespace(status_code=r.status_code, json=r.json, text=r.text)
    monkeypatch.setattr(leima_api.requests, "post", post)
    return calls


def package_with_policy(policy):
    data = browser_package()
    if policy == "AGENT_READABLE":
        return data
    # rebuild with a different exportPolicy (or none) in metadata
    import io, zipfile
    src = zipfile.ZipFile(io.BytesIO(data))
    metadata = json.loads(src.read("metadata.json"))
    if policy is None:
        metadata.pop("exportPolicy")
    else:
        metadata["exportPolicy"] = policy
    files = {n: src.read(n) for n in ("observation.json", "dom.html", "visible-text.txt", "screenshot.png")}
    files["metadata.json"] = json.dumps(metadata).encode()
    manifest = json.dumps({"schemaVersion": 1, "algorithm": "SHA-256", "kind": "browser",
                           "files": {n: hashlib.sha256(d).hexdigest() for n, d in files.items()}}).encode()
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for name, d in {**files, "manifest.json": manifest,
                        "manifest.sha256": hashlib.sha256(manifest).hexdigest() + "  manifest.json\n"}.items():
            z.writestr(name, d)
    return out.getvalue()


def test_stamp_archived_end_to_end(tmp_path, leima):
    archive = Archive(tmp_path)
    row, _ = archive.store(browser_package())
    result = leima_api.stamp_archived(archive, row["sha256"][:10], "Osinko on 1,20 euroa.", base_url="http://leima.test")
    assert leima == ["http://leima.test/api/stamp/device-capture"]
    assert result["source"]["provenance"] == "device_captured"
    assert result["evidence"]["input_hash"] == row["sha256"]

    stamped = [r for r in archive.rows() if r["event"] == "stamped"]
    assert len(stamped) == 1 and stamped[0]["arweave_tx"] == "tx-123" and stamped[0]["provenance"] == "device_captured"
    stamp_file = tmp_path / stamped[0]["stamp_file"]
    assert stamp_file.parent == (tmp_path / row["path"]).parent
    assert json.loads(stamp_file.read_text("utf-8"))["verdict"]["category"] == "Supported"
    # the package itself is untouched
    assert archive.verify_entry(row["sha256"])["valid"]


@pytest.mark.parametrize("policy", ["LOCAL_ONLY", None])
def test_agent_cannot_export_local_only_or_unknown_captures(tmp_path, leima, policy):
    archive = Archive(tmp_path)
    row, _ = archive.store(package_with_policy(policy))
    with pytest.raises(BridgeError) as e:
        leima_api.stamp_archived(archive, row["sha256"], "claim", by_agent=True)
    assert e.value.code == "CONTENT_WITHHELD" and leima == []
    # the person can still send it
    assert leima_api.stamp_archived(archive, row["sha256"], "claim")["evidence"]["input_hash"] == row["sha256"]


def test_mcp_capture_stamp_tool(tmp_path, leima):
    archive = Archive(tmp_path)
    row, _ = archive.store(browser_package())
    call_tool = mcp_stdio.make_call_tool(archive_factory=lambda: archive)
    result = call_tool("capture_stamp", {"sha256": row["sha256"], "claim": "Osinko on 1,20 euroa."})
    assert result["evidence"]["storage"]["status"] == "submitted" and result["limits"]
    tool = next(t for t in mcp_stdio.TOOLS if t["name"] == "capture_stamp")
    assert "CONTENT_WITHHELD" in tool["description"]


def test_cli_asks_before_sending(tmp_path, leima, monkeypatch, capsys):
    archive = Archive(tmp_path)
    row, _ = archive.store(browser_package())
    monkeypatch.setattr("builtins.input", lambda prompt: "e")
    assert main(["stamp", row["sha256"], "--claim", "c", "--archive", str(tmp_path)]) == 1
    assert leima == [] and "Mitään ei lähetetty" in capsys.readouterr().out

    assert main(["stamp", row["sha256"], "--claim", "c", "--archive", str(tmp_path), "--yes"]) == 0
    out = capsys.readouterr().out
    assert "device_captured" in out and "AI-arvio" in out and "tx-123" in out and "Rajat:" in out


def test_non_browser_capture_is_refused(tmp_path, leima):
    from tests.test_bridge_packages import photo_package
    archive = Archive(tmp_path)
    row, _ = archive.store(photo_package())
    with pytest.raises(BridgeError) as e:
        leima_api.stamp_archived(archive, row["sha256"], "claim")
    assert e.value.code == "NOT_A_BROWSER_CAPTURE" and leima == []
