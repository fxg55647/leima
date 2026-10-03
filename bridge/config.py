"""Bridge identity and per-device pairing tokens, stored outside the repository.

Location: %APPDATA%\\Leima\\bridge.json (or $LEIMA_BRIDGE_HOME/bridge.json).
Whoever can read this file can control the paired phones over USB.
"""
import json
import os
import platform
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def bridge_home() -> Path:
    if os.environ.get("LEIMA_BRIDGE_HOME"):
        return Path(os.environ["LEIMA_BRIDGE_HOME"])
    base = os.environ.get("APPDATA") or os.path.join(Path.home(), ".config")
    return Path(base) / "Leima"


class BridgeConfig:
    def __init__(self, path: Path | None = None):
        self.path = path or bridge_home() / "bridge.json"
        self.data = json.loads(self.path.read_text("utf-8")) if self.path.is_file() else {}
        if "bridge_id" not in self.data:
            self.data["bridge_id"] = "b_" + secrets.token_hex(16)
            self.data["bridge_name"] = (platform.node() or "Leima bridge")[:64]
            self.data["devices"] = {}
            self.save()

    @property
    def bridge_id(self) -> str:
        return self.data["bridge_id"]

    @property
    def bridge_name(self) -> str:
        return self.data["bridge_name"]

    def token(self, serial: str) -> str | None:
        return self.data["devices"].get(serial, {}).get("token")

    def set_token(self, serial: str, token: str) -> None:
        self.data["devices"][serial] = {"token": token, "paired_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        self.save()

    def forget(self, serial: str) -> None:
        if self.data["devices"].pop(serial, None) is not None:
            self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=self.path.parent, prefix=".bridge-", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)
        os.replace(temporary, self.path)
