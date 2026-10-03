"""ADB access for the bridge: device listing and the bridge's own port forward. Nothing else.

The bridge never exposes a generic `adb shell`; every ADB call it makes is in this module.
"""
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .errors import BridgeError

SOCKET_NAME = "fi.leima.android.bridge"


@dataclass(frozen=True)
class Device:
    serial: str
    state: str  # "device", "unauthorized", "offline", ...
    model: str = ""


def find_adb() -> str:
    candidates = [os.environ.get("LEIMA_ADB"), shutil.which("adb")]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(str(Path(local) / "Android" / "Sdk" / "platform-tools" / "adb.exe"))
    android_home = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    if android_home:
        candidates.append(str(Path(android_home) / "platform-tools" / ("adb.exe" if os.name == "nt" else "adb")))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise BridgeError("ADB_NOT_FOUND", "adb not found. Install Android platform-tools or set LEIMA_ADB.")


def parse_devices(output: str) -> list[Device]:
    devices = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices") or line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        model = next((p.split(":", 1)[1] for p in parts[2:] if p.startswith("model:")), "")
        devices.append(Device(serial=parts[0], state=parts[1], model=model.replace("_", " ")))
    return devices


def select_device(devices: list[Device], serial: str | None) -> Device:
    if serial:
        device = next((d for d in devices if d.serial == serial), None)
        if device is None:
            raise BridgeError("NO_DEVICE", f"Device {serial} is not connected.")
    else:
        if not devices:
            raise BridgeError("NO_DEVICE", "No Android device connected over USB.")
        if len(devices) > 1:
            listed = ", ".join(f"{d.serial} ({d.model or d.state})" for d in devices)
            raise BridgeError("MULTIPLE_DEVICES", f"Several devices connected; choose one with --serial: {listed}")
        device = devices[0]
    if device.state == "unauthorized":
        raise BridgeError("DEVICE_UNAUTHORIZED", "Accept the USB debugging prompt on the phone, then try again.")
    if device.state != "device":
        raise BridgeError("DEVICE_OFFLINE", f"Device {device.serial} is {device.state}.")
    return device


class Adb:
    def __init__(self, path: str | None = None):
        self.path = path or find_adb()

    def _run(self, *args: str) -> str:
        try:
            done = subprocess.run([self.path, *args], capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise BridgeError("ADB_FAILED", f"adb {' '.join(args)} failed: {e}") from e
        if done.returncode != 0:
            raise BridgeError("ADB_FAILED", f"adb {' '.join(args)} failed: {(done.stderr or done.stdout).strip()}")
        return done.stdout

    def devices(self) -> list[Device]:
        return parse_devices(self._run("devices", "-l"))

    def forward(self, serial: str) -> int:
        """Forwards a free local TCP port to the app's abstract socket; returns the port."""
        out = self._run("-s", serial, "forward", "tcp:0", f"localabstract:{SOCKET_NAME}").strip()
        try:
            return int(out.splitlines()[-1])
        except (ValueError, IndexError) as e:
            raise BridgeError("ADB_FAILED", f"Unexpected adb forward output: {out!r}") from e

    def remove_forward(self, serial: str, port: int) -> None:
        self._run("-s", serial, "forward", "--remove", f"tcp:{port}")
