"""PC side of the USB bridge (bridge/) against a fake phone speaking protocol v1."""
import io
import json
import socket
import threading

import pytest

from bridge.adb import Device, parse_devices, select_device
from bridge.client import PhoneClient, pair, session, unpair
from bridge.config import BridgeConfig
from bridge.errors import BridgeError
from bridge.mcp_stdio import make_call_tool, serve


class FakePhone:
    """Minimal phone: hello, pair_begin (auto-approve), auth, device_status, unpair, bye."""

    def __init__(self, approve=True, close_immediately=False):
        self.approve = approve
        self.close_immediately = close_immediately
        self.tokens = {}  # bridge_id -> token
        self.pair_codes = []
        self.server = socket.socket()
        self.server.bind(("127.0.0.1", 0))
        self.server.listen()
        self.port = self.server.getsockname()[1]
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while True:
            try:
                conn, _ = self.server.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn):
        with conn, conn.makefile("rwb") as f:
            if self.close_immediately:
                return
            bridge_id, authed = None, False
            for raw in f:
                req = json.loads(raw)
                method, params = req["method"], req.get("params", {})
                result, error = {}, None
                if method == "hello":
                    bridge_id = params["bridge_id"]
                    result = {"protocol_version": 1, "app_version": "0.1.0", "paired": bridge_id in self.tokens}
                elif method == "pair_begin":
                    self.pair_codes.append(params["code"])
                    if self.approve:
                        self.tokens[bridge_id] = result_token = f"tok-{len(self.pair_codes)}"
                        result = {"token": result_token}
                    else:
                        error = ("PAIRING_REJECTED", "rejected")
                elif method == "auth":
                    authed = self.tokens.get(bridge_id) == params["token"]
                    result, error = ({"session_id": "s_1"}, None) if authed else ({}, ("AUTH_FAILED", "bad token"))
                elif method == "device_status":
                    result, error = ({"protocol_version": 1, "capabilities": ["device_status"]}, None) if authed \
                        else ({}, ("NOT_AUTHENTICATED", "auth first"))
                elif method == "unpair":
                    self.tokens.pop(bridge_id, None)
                elif method != "bye":
                    error = ("UNKNOWN_METHOD", method)
                body = {"id": req["id"], "error": {"code": error[0], "message": error[1]}} if error else {"id": req["id"], "result": result}
                f.write(json.dumps(body).encode() + b"\n")
                f.flush()
                if method == "bye":
                    return

    def close(self):
        self.server.close()


class FakeAdb:
    def __init__(self, phone, devices=None):
        self.phone = phone
        self._devices = devices or [Device("SERIAL1", "device", "Pixel 7")]
        self.forwards = []
        self.removed = []

    def devices(self):
        return self._devices

    def forward(self, serial):
        self.forwards.append(serial)
        return self.phone.port

    def remove_forward(self, serial, port):
        self.removed.append((serial, port))


@pytest.fixture
def config(tmp_path):
    return BridgeConfig(tmp_path / "bridge.json")


@pytest.fixture
def phone():
    p = FakePhone()
    yield p
    p.close()


def test_parse_devices():
    out = (
        "List of devices attached\n"
        "R58N12345\tdevice usb:1-1 product:x model:Galaxy_S21 device:o1s transport_id:3\n"
        "emulator-5554 unauthorized transport_id:4\n\n"
    )
    assert parse_devices(out) == [
        Device("R58N12345", "device", "Galaxy S21"),
        Device("emulator-5554", "unauthorized", ""),
    ]


@pytest.mark.parametrize("devices,serial,code", [
    ([], None, "NO_DEVICE"),
    ([Device("a", "device"), Device("b", "device")], None, "MULTIPLE_DEVICES"),
    ([Device("a", "unauthorized")], None, "DEVICE_UNAUTHORIZED"),
    ([Device("a", "offline")], None, "DEVICE_OFFLINE"),
    ([Device("a", "device")], "zzz", "NO_DEVICE"),
])
def test_select_device_errors(devices, serial, code):
    with pytest.raises(BridgeError) as e:
        select_device(devices, serial)
    assert e.value.code == code


def test_select_device_by_serial_among_many():
    assert select_device([Device("a", "device"), Device("b", "device")], "b").serial == "b"


def test_config_persists_identity(tmp_path):
    first = BridgeConfig(tmp_path / "bridge.json")
    assert first.bridge_id.startswith("b_") and len(first.bridge_id) == 34
    first.set_token("S", "t")
    second = BridgeConfig(tmp_path / "bridge.json")
    assert second.bridge_id == first.bridge_id and second.token("S") == "t"


def test_pair_then_session_then_unpair(phone, config):
    adb = FakeAdb(phone)
    shown = []
    pair(adb, config, None, lambda device, code: shown.append(code))
    assert shown == phone.pair_codes and len(shown[0]) == 6 and shown[0].isdigit()
    assert config.token("SERIAL1") == "tok-1"

    with session(adb, config) as (device, client):
        assert client.request("device_status")["capabilities"] == ["device_status"]

    unpair(adb, config, None)
    assert config.token("SERIAL1") is None and config.bridge_id not in phone.tokens
    # every forward the bridge created was removed again, and only those
    assert adb.removed == [("SERIAL1", phone.port)] * len(adb.forwards)


def test_session_without_pairing_says_not_paired(phone, config):
    with pytest.raises(BridgeError) as e:
        with session(FakeAdb(phone), config):
            pass
    assert e.value.code == "NOT_PAIRED"


def test_stale_token_is_refused_by_phone(phone, config):
    phone.tokens[config.bridge_id] = "new-token"
    config.set_token("SERIAL1", "old-token")
    with pytest.raises(BridgeError) as e:
        with session(FakeAdb(phone), config):
            pass
    assert e.value.code == "AUTH_FAILED"


def test_rejected_pairing_stores_nothing(config):
    p = FakePhone(approve=False)
    try:
        with pytest.raises(BridgeError) as e:
            pair(FakeAdb(p), config, None, lambda d, c: None)
        assert e.value.code == "PAIRING_REJECTED"
        assert config.token("SERIAL1") is None
    finally:
        p.close()


def test_app_not_listening_when_forward_has_no_peer(config):
    # adb accepts the TCP connection even when nothing listens on the phone, then closes it.
    p = FakePhone(close_immediately=True)
    adb = FakeAdb(p)
    try:
        with pytest.raises(BridgeError) as e:
            with session(adb, config):
                pass
        assert e.value.code == "APP_NOT_LISTENING"
        assert adb.removed == [("SERIAL1", p.port)]
    finally:
        p.close()


def test_mismatched_response_id_is_rejected():
    a, b = socket.socketpair()
    try:
        b.sendall(b'{"id": 99, "result": {}}\n')
        with pytest.raises(BridgeError) as e:
            PhoneClient(a).request("hello")
        assert e.value.code == "CONNECTION_LOST"
    finally:
        a.close()
        b.close()


def _mcp(lines, call_tool):
    out = io.StringIO()
    serve(io.StringIO("".join(json.dumps(m) + "\n" for m in lines)), out, call_tool)
    return [json.loads(line) for line in out.getvalue().splitlines()]


def test_mcp_lists_bridge_tools_only(phone, config):
    responses = _mcp([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ], make_call_tool(lambda: FakeAdb(phone), lambda: config))
    assert [r["id"] for r in responses] == [1, 2]
    assert responses[0]["result"]["serverInfo"]["name"] == "leima-bridge"
    assert [t["name"] for t in responses[1]["result"]["tools"]] == ["device_status"]


def test_mcp_device_status_success_and_error(phone, config):
    call_tool = make_call_tool(lambda: FakeAdb(phone), lambda: config)
    call = {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "device_status", "arguments": {}}}

    unpaired = _mcp([call], call_tool)[0]["result"]
    assert unpaired["isError"] and "NOT_PAIRED" in unpaired["content"][0]["text"]

    pair(FakeAdb(phone), config, None, lambda d, c: None)
    paired = _mcp([call], call_tool)[0]["result"]
    assert not paired["isError"]
    assert paired["structuredContent"]["serial"] == "SERIAL1"
    assert paired["structuredContent"]["capabilities"] == ["device_status"]

    unknown = _mcp([{**call, "params": {"name": "stamp_citation", "arguments": {}}}], call_tool)[0]
    assert unknown["error"]["code"] == -32602
