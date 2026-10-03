"""Protocol v1 client (docs/RESEARCH_APPLIANCE_USB_PROTOCOL.md) and the USB session around it."""
import base64
import hashlib
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
READ_CHUNK_BYTES = 256 * 1024  # phone maximum (PackageRepository.MAX_READ_BYTES)


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


def list_packages(client: PhoneClient) -> list[dict]:
    try:
        return client.request("packages.list")["packages"]
    except BridgeError as e:
        if e.code == "UNKNOWN_METHOD":
            raise BridgeError("APP_TOO_OLD", "The Leima app on the phone does not support package transfer; update it.") from e
        raise


def read_package(client: PhoneClient, package: dict) -> bytes:
    """Reads a package in chunks and checks size and sha256 against the listing."""
    data = bytearray()
    while True:
        chunk = client.request("packages.read", {
            "package_id": package["package_id"], "offset": len(data), "length": READ_CHUNK_BYTES,
        })
        if chunk["offset"] != len(data):
            raise BridgeError("PACKAGE_TRANSFER_MISMATCH", f"Phone returned offset {chunk['offset']}, expected {len(data)}")
        data += base64.b64decode(chunk["data_base64"])
        if chunk["eof"]:
            break
        if len(data) > package["size"]:
            raise BridgeError("PACKAGE_TRANSFER_MISMATCH", "Phone sent more bytes than listed")
    if len(data) != package["size"] or hashlib.sha256(data).hexdigest() != package["sha256"]:
        raise BridgeError("PACKAGE_TRANSFER_MISMATCH", f"{package['package_id']} did not arrive intact")
    return bytes(data)


def sync(client: PhoneClient, device: Device, archive, delete: bool = True,
         progress: Callable[[dict], None] = lambda result: None) -> list[dict]:
    """Moves every finished package to [archive]. The phone copy is deleted only after the ZIP is
    verified and durably stored (or was already archived with the same sha256)."""
    results = []
    for package in list_packages(client):
        result = {"package_id": package["package_id"], "kind": package["kind"], "sha256": package["sha256"]}
        try:
            row, existed = archive.store(read_package(client, package), device.model)
            result.update(status="already_archived" if existed else "archived", path=row["path"])
            if delete:
                client.request("packages.delete", {"package_id": package["package_id"], "sha256": package["sha256"]})
                result["deleted_from_phone"] = True
        except BridgeError as e:
            if e.code == "CONNECTION_LOST":
                raise
            result.update(status="failed", error=str(e))
        results.append(result)
        progress(result)
    return results
