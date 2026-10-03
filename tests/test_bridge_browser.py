"""Phase B on the PC side: browser command runner, MCP browser tools and browser packages."""
import base64
import hashlib
import io
import json
import zipfile
from contextlib import contextmanager

import pytest

from bridge.adb import Device
from bridge.archive import Archive
from bridge.client import run_command
from bridge.errors import BridgeError
from bridge import mcp_stdio
from verify_package import verify


class ScriptedClient:
    """Answers requests from a list of callables; records every request it saw."""

    def __init__(self, log, answers):
        self.log = log
        self.answers = answers

    def request(self, method, params=None, timeout=None):
        self.log.append((method, dict(params or {})))
        answer = self.answers.pop(0)
        return answer(method, params) if callable(answer) else answer


def sessions(*clients):
    queue = list(clients)

    @contextmanager
    def open_session():
        client = queue.pop(0)
        if isinstance(client, BridgeError):
            raise client
        yield Device("S", "device"), client
    return open_session


def lost(*_):
    raise BridgeError("CONNECTION_LOST", "usb unplugged")


def test_read_only_commands_have_no_request_id():
    log = []
    assert run_command(sessions(ScriptedClient(log, [{"elements": []}])), "browser.observe") == {"elements": []}
    assert log == [("browser.observe", {})]


def test_mutating_command_is_not_repeated_after_disconnect():
    log = []
    done = {"state": "done", "result": {"url": "https://example.org/next"}}
    result = run_command(sessions(ScriptedClient(log, [lost]), ScriptedClient(log, [done])),
                         "browser.click", {"session_id": "bs", "observation_id": "o", "element_id": "el_1"})
    assert result == {"url": "https://example.org/next", "recovered_after_disconnect": True}
    (first, first_params), (second, second_params) = log
    assert first == "browser.click" and second == "command_status"
    assert second_params == {"request_id": first_params["request_id"]}
    assert first_params["request_id"].startswith("r_")


@pytest.mark.parametrize("status", [{"state": "running"}, {"state": "unknown"}])
def test_unknown_outcome_is_reported_not_retried(status):
    log = []
    with pytest.raises(BridgeError) as e:
        run_command(sessions(ScriptedClient(log, [lost]), ScriptedClient(log, [status])), "browser.navigate", {"url": "https://x.org"})
    assert e.value.code == "COMMAND_OUTCOME_UNKNOWN"
    assert [m for m, _ in log] == ["browser.navigate", "command_status"]


def test_stored_failure_is_raised_and_unreachable_phone_is_unknown():
    log = []
    failed = {"state": "done", "error": {"code": "STALE_OBSERVATION", "message": "old"}}
    with pytest.raises(BridgeError) as e:
        run_command(sessions(ScriptedClient(log, [lost]), ScriptedClient(log, [failed])), "browser.back")
    assert e.value.code == "STALE_OBSERVATION"
    with pytest.raises(BridgeError) as e:
        run_command(sessions(ScriptedClient([], [lost]), BridgeError("APP_NOT_LISTENING", "gone")), "browser.capture")
    assert e.value.code == "COMMAND_OUTCOME_UNKNOWN"


def test_other_errors_pass_through_without_status_query():
    log = []
    def refuse(*_):
        raise BridgeError("URL_NOT_ALLOWED", "http")
    with pytest.raises(BridgeError) as e:
        run_command(sessions(ScriptedClient(log, [refuse])), "browser.navigate", {"url": "http://x"})
    assert e.value.code == "URL_NOT_ALLOWED" and len(log) == 1


def _serve(lines, call_tool):
    out = io.StringIO()
    mcp_stdio.serve(io.StringIO("".join(json.dumps(m) + "\n" for m in lines)), out, call_tool)
    return [json.loads(line) for line in out.getvalue().splitlines()]


class ScreenshotPhone:
    """Phone side of browser.screenshot + browser.screenshot_read with the real chunk contract."""

    def __init__(self, png: bytes, corrupt=False, policy="AGENT_READABLE"):
        self.png, self.corrupt, self.policy, self.reads = png, corrupt, policy, 0

    def request(self, method, params=None, timeout=None):
        params = params or {}
        if method == "browser.screenshot":
            meta = {"export_policy": self.policy, "url": "https://example.org/", "width": 2, "height": 1, "masked_regions": 1,
                    "screenshot_id": "shot_1", "size": len(self.png), "sha256": hashlib.sha256(self.png).hexdigest()}
            return meta
        assert method == "browser.screenshot_read" and params["screenshot_id"] == "shot_1"
        self.reads += 1
        data = self.png[params["offset"]:params["offset"] + params["length"]]
        if self.corrupt:
            data = data[::-1]
        return {"offset": params["offset"], "data_base64": base64.b64encode(data).decode(),
                "eof": params["offset"] + len(data) >= len(self.png)}


def test_mcp_screenshot_is_read_in_chunks(monkeypatch):
    png = bytes(range(256)) * 4000  # ~1 MB: larger than one protocol line
    phone = ScreenshotPhone(png)
    monkeypatch.setattr(mcp_stdio, "session", lambda *a: sessions(phone)())
    shot = _serve([{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "browser_screenshot", "arguments": {}}}],
                  mcp_stdio.make_call_tool(lambda: None, lambda: None))[0]
    image, text = shot["result"]["content"]
    assert base64.b64decode(image["data"]) == png and image["mimeType"] == "image/png"
    assert phone.reads == 4
    assert "screenshot_id" not in shot["result"]["structuredContent"]
    assert json.loads(text["text"])["masked_regions"] == 1


def test_mcp_screenshot_rejects_corrupted_transfer(monkeypatch):
    monkeypatch.setattr(mcp_stdio, "session", lambda *a: sessions(ScreenshotPhone(b"abcdef" * 10, corrupt=True))())
    shot = _serve([{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "browser_screenshot", "arguments": {}}}],
                  mcp_stdio.make_call_tool(lambda: None, lambda: None))[0]
    assert shot["result"]["isError"] and "SCREENSHOT_FAILED" in shot["result"]["content"][0]["text"]


def test_mcp_browser_tools(monkeypatch):
    log = []
    answers = [{"url": "https://example.org/", "title": "Ex", "loading": False}]
    monkeypatch.setattr(mcp_stdio, "session", lambda *a: sessions(ScriptedClient(log, answers))())
    call_tool = mcp_stdio.make_call_tool(lambda: None, lambda: None)
    nav = _serve([{"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                   "params": {"name": "browser_navigate", "arguments": {"url": "https://example.org/", "serial": "S"}}}], call_tool)[0]
    assert nav["result"]["structuredContent"]["title"] == "Ex"
    assert log[0][0] == "browser.navigate" and "serial" not in log[0][1] and "request_id" in log[0][1]


def test_mcp_browser_tool_annotations():
    tools = {t["name"]: t for t in mcp_stdio.TOOLS}
    assert tools["browser_click"]["annotations"]["destructiveHint"] is True
    assert tools["browser_observe"]["annotations"]["readOnlyHint"] is True
    assert set(tools["browser_type"]["inputSchema"]["required"]) == {"session_id", "observation_id", "element_id", "text"}


def browser_package(status="complete", missing=(), screenshot=True) -> bytes:
    metadata = {"schemaVersion": 1, "kind": "browser", "captureStatus": status, "missing": list(missing),
                "requestedAt": "2026-10-03T14:30:12Z", "url": "https://example.org/a?token=REDACTED"}
    files = {"metadata.json": json.dumps(metadata).encode(), "observation.json": b"{}",
             "dom.html": b"<html></html>", "visible-text.txt": b"Hello"}
    if screenshot:
        files["screenshot.png"] = b"png"
    manifest = json.dumps({"schemaVersion": 1, "algorithm": "SHA-256", "kind": "browser",
                           "files": {n: hashlib.sha256(d).hexdigest() for n, d in files.items()}}).encode()
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for name, data in {**files, "manifest.json": manifest,
                           "manifest.sha256": hashlib.sha256(manifest).hexdigest() + "  manifest.json\n"}.items():
            z.writestr(name, data)
    return out.getvalue()


def test_browser_packages_verify_and_archive(tmp_path):
    assert verify(io.BytesIO(browser_package()))["kind"] == "browser"
    assert verify(io.BytesIO(browser_package("partial", [{"file": "screenshot.png", "reason": "SCREENSHOT_BLOCKED"}], screenshot=False)))
    row, status = Archive(tmp_path).store(browser_package())
    assert status == "archived" and row["kind"] == "browser" and row["domain"] == "example.org"
    assert row["path"].startswith("browser/2026/10/2026-10-03_143012_example.org_")


@pytest.mark.parametrize("data", [
    browser_package(screenshot=False),                    # complete but screenshot missing
    browser_package("partial"),                           # partial without saying what is missing
    browser_package("done"),                              # unknown status
])
def test_inconsistent_browser_packages_are_rejected(data):
    with pytest.raises(ValueError):
        verify(io.BytesIO(data))


class TimeoutRecorder:
    def __init__(self):
        self.calls = []

    def request(self, method, params=None, timeout=None):
        self.calls.append((method, dict(params or {}), timeout))
        return {"ok": True}


def test_handoff_commands_use_request_id_and_long_wait():
    rec = TimeoutRecorder()

    @contextmanager
    def open_session():
        yield Device("S", "device"), rec

    run_command(open_session, "browser.request_human", {"reason": "LOGIN", "task": "Kirjaudu"})
    run_command(open_session, "browser.resume", {"handoff_id": "ho_1", "wait_s": 120})
    run_command(open_session, "browser.end_session")
    (m1, p1, _), (m2, p2, t2), (m3, p3, _) = rec.calls
    assert m1 == "browser.request_human" and p1["request_id"].startswith("r_")
    assert m2 == "browser.resume" and "request_id" not in p2 and t2 >= 120 + 30
    assert m3 == "browser.end_session" and p3 == {}


def test_handoff_tools_are_listed():
    tools = {t["name"]: t for t in mcp_stdio.TOOLS}
    assert tools["browser_request_human"]["inputSchema"]["properties"]["reason"]["enum"] == ["LOGIN", "MFA", "CAPTCHA", "CONFIRMATION", "OTHER"]
    assert tools["browser_resume"]["inputSchema"]["required"] == ["handoff_id"]
    assert "browser_end_session" in tools


def test_bridge_strips_content_when_phone_says_local_only():
    leaky = {"export_policy": "LOCAL_ONLY", "url": "https://bank.example", "visible_text": "Saldo", "title": "Tili",
             "elements": [{"element_id": "el_1", "role": "link", "name": "Tiliote", "href": "https://bank.example/x"}],
             "observation": {"visible_text": "nested"}}
    out = mcp_stdio.enforce_local_only(leaky)
    assert "Saldo" not in json.dumps(out) and "Tiliote" not in json.dumps(out) and "nested" not in json.dumps(out)
    assert out["content_withheld"] and out["elements"] == [{"element_id": "el_1", "role": "link"}]
    readable = {"export_policy": "AGENT_READABLE", "visible_text": "Uutinen"}
    assert mcp_stdio.enforce_local_only(dict(readable)) == readable


def test_local_only_screenshot_never_returns_an_image(monkeypatch):
    # An older or buggy app that still offers a screenshot under LOCAL_ONLY: the bridge never reads it.
    phone = ScreenshotPhone(b"secret-pixels", policy="LOCAL_ONLY")
    monkeypatch.setattr(mcp_stdio, "session", lambda *a: sessions(phone)())
    response = _serve([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                        "params": {"name": "browser_screenshot", "arguments": {}}}],
                      mcp_stdio.make_call_tool(lambda: None, lambda: None))[0]
    assert response["result"]["isError"] and "CONTENT_WITHHELD" in response["result"]["content"][0]["text"]
    assert phone.reads == 0
