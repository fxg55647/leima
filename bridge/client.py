"""Protocol v1 client (docs/RESEARCH_APPLIANCE_USB_PROTOCOL.md) and the USB session around it."""
import json
import secrets
import socket
from contextlib import contextmanager
from typing import Callable, Iterator

from .adb import Adb, Device, select_device
from .config import BridgeConfig
from .errors import BridgeError

PROTOCOL_VERSION = 1
MAX_LINE_BYTES = 1024 * 1024
REQUEST_TIMEOUT_S = 15
PAIRING_TIMEOUT_S = 130  # phone waits up to 120 s for the person to answer


class PhoneClient:
    def __init__(self, sock: socket.socket):
        self._sock = sock
        self._reader = sock.makefile("rb")
        self._next_id = 1

    @classmethod
    def connect(cls, port: int, host: str = "127.0.0.1") -> "PhoneClient":
        try:
            sock = socket.create_connection((host, port), timeout=REQUEST_TIMEOUT_S)
        except OSError as e:
            raise BridgeError("APP_NOT_LISTENING", f"Could not reach the Leima app: {e}") from e
        return cls(sock)

    def request(self, method: str, params: dict | None = None, timeout: float = REQUEST_TIMEOUT_S) -> dict:
        msg_id = self._next_id
        self._next_id += 1
        line = json.dumps({"id": msg_id, "method": method, "params": params or {}}, separators=(",", ":"))
        self._sock.settimeout(timeout)
        try:
            self._sock.sendall(line.encode("utf-8") + b"\n")
            raw = self._reader.readline(MAX_LINE_BYTES + 1)
        except socket.timeout as e:
            raise BridgeError("CONNECTION_LOST", f"No answer from the phone to {method} within {timeout:.0f} s") from e
        except OSError as e:
            raise BridgeError("CONNECTION_LOST", f"Connection to the phone failed: {e}") from e
        if not raw:
            raise BridgeError("CONNECTION_LOST", "The phone closed the connection")
        if not raw.endswith(b"\n"):
            raise BridgeError("CONNECTION_LOST", "Truncated or oversized response from the phone")
        response = json.loads(raw)
        if "error" in response:
            error = response["error"]
            raise BridgeError(error.get("code", "INTERNAL"), error.get("message", ""))
        if response.get("id") != msg_id:
            raise BridgeError("CONNECTION_LOST", f"Response id {response.get('id')} does not match request {msg_id}")
        return response["result"]

    def hello(self, config: BridgeConfig) -> dict:
        try:
            return self.request("hello", {
                "protocol_versions": [PROTOCOL_VERSION],
                "bridge_id": config.bridge_id,
                "bridge_name": config.bridge_name,
            })
        except BridgeError as e:
            if e.code == "CONNECTION_LOST":
                raise BridgeError(
                    "APP_NOT_LISTENING",
                    "The Leima app is not running on the phone or USB control is switched off.",
                ) from e
            raise

    def close(self) -> None:
        try:
            self.request("bye")
        except BridgeError:
            pass
        finally:
            self._reader.close()
            self._sock.close()


@contextmanager
def connected(adb: Adb, serial: str | None) -> Iterator[tuple[Device, PhoneClient]]:
    """Forwards a port to the chosen device and connects; removes only its own forward afterwards."""
    device = select_device(adb.devices(), serial)
    port = adb.forward(device.serial)
    try:
        client = PhoneClient.connect(port)
        try:
            yield device, client
        finally:
            client.close()
    finally:
        try:
            adb.remove_forward(device.serial, port)
        except BridgeError:
            pass  # device unplugged; adb drops its forwards with it


@contextmanager
def session(adb: Adb, config: BridgeConfig, serial: str | None = None) -> Iterator[tuple[Device, PhoneClient]]:
    """Connected, greeted and authenticated client."""
    with connected(adb, serial) as (device, client):
        hello = client.hello(config)
        token = config.token(device.serial)
        if not token or not hello.get("paired"):
            raise BridgeError("NOT_PAIRED", "This PC is not paired with the phone. Run: python -m bridge pair")
        client.request("auth", {"token": token})
        yield device, client


def new_pairing_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def pair(adb: Adb, config: BridgeConfig, serial: str | None, show_code: Callable[[Device, str], None]) -> Device:
    """Runs pair_begin; [show_code] tells the person which code to compare on the phone."""
    with connected(adb, serial) as (device, client):
        client.hello(config)
        code = new_pairing_code()
        show_code(device, code)
        result = client.request("pair_begin", {"code": code}, timeout=PAIRING_TIMEOUT_S)
        config.set_token(device.serial, result["token"])
        client.request("auth", {"token": result["token"]})
        return device


def unpair(adb: Adb, config: BridgeConfig, serial: str | None) -> Device:
    with session(adb, config, serial) as (device, client):
        client.request("unpair")
    config.forget(device.serial)
    return device
