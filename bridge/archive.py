"""PC archive of phone packages (docs/RESEARCH_APPLIANCE_PACKAGES.md section 3).

ZIP bytes are stored exactly as received and never modified. index.jsonl is append-only:
`archived` rows describe stored packages, `repaired` rows record a damaged or missing archive
copy rewritten from verified phone bytes, `tag` rows attach tags to them.
"""
import hashlib
import io
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .errors import BridgeError

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "android" / "tools"))
from verify_package import verify  # noqa: E402  standalone verifier shared with third parties


def default_archive_dir() -> Path:
    return Path(os.environ.get("LEIMA_EVIDENCE_DIR") or REPO_ROOT / "evidence")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_time(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_atomic(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".partial")
    with open(partial, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(partial, target)


def _verify_bytes(data: bytes) -> dict:
    try:
        return verify(io.BytesIO(data))
    except Exception as e:  # zipfile/json/KeyError/ValueError: all mean "not a valid package"
        raise BridgeError("PACKAGE_INVALID", f"Package failed verification: {e}") from e


class Archive:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else default_archive_dir()
        self.index_path = self.root / "index.jsonl"

    def rows(self) -> list[dict]:
        if not self.index_path.is_file():
            return []
        with self.index_path.open(encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def archived(self) -> dict[str, dict]:
        return {row["sha256"]: row for row in self.rows() if row.get("event") == "archived"}

    def find(self, sha_prefix: str) -> dict:
        prefix = sha_prefix.lower()
        matches = [row for sha, row in self.archived().items() if sha.startswith(prefix)]
        if len(prefix) < 6 or len(matches) != 1:
            raise BridgeError("PACKAGE_NOT_FOUND", f"No unique archived package for {sha_prefix!r} (give at least 6 hex characters)")
        return matches[0]

    def store(self, data: bytes, device: str = "") -> tuple[dict, str]:
        """Verifies and stores package bytes. Returns (index row, status) where status is
        "archived" (new), "already_archived" (the archived copy still hashes to the same sha256)
        or "repaired" (the archived copy was missing or damaged and was rewritten from [data]).
        Only after this returns may the phone copy be deleted."""
        sha = hashlib.sha256(data).hexdigest()
        info = _verify_bytes(data)
        existing = self.archived().get(sha)
        if existing:
            target = self.root / existing["path"]
            if target.is_file() and _sha256_file(target) == sha:
                return existing, "already_archived"
            reason = "hash_mismatch" if target.is_file() else "missing"
            _write_atomic(target, data)
            self._append({"event": "repaired", "sha256": sha, "path": existing["path"], "reason": reason, "at": _now()})
            return existing, "repaired"
        details = info["details"]
        captured = _parse_time(details.get("requestedAt") or details.get("startedAtUtc"))
        domain = (urlsplit(details["url"]).hostname or "") if isinstance(details.get("url"), str) else ""
        domain = re.sub(r"[^a-z0-9.-]", "", domain.lower())[:64]
        when = captured or datetime.now(timezone.utc)
        folder = "_".join(p for p in (when.strftime("%Y-%m-%d_%H%M%S"), domain, sha[:8]) if p)
        relative = Path(info["kind"]) / when.strftime("%Y") / when.strftime("%m") / folder / "package.zip"
        _write_atomic(self.root / relative, data)
        row = {
            "event": "archived",
            "sha256": sha,
            "kind": info["kind"],
            "path": relative.as_posix(),
            "size": len(data),
            "captured_at": captured.isoformat(timespec="seconds").replace("+00:00", "Z") if captured else None,
            "domain": domain or None,
            "device": device or None,
            "pulled_at": _now(),
            "verified": True,
        }
        self._append(row)
        return row, "archived"

    def tag(self, sha_prefix: str, tag: str) -> dict:
        tag = tag.strip()
        if not tag or len(tag) > 100:
            raise BridgeError("BAD_TAG", "Tag must be 1-100 characters")
        row = {"event": "tag", "sha256": self.find(sha_prefix)["sha256"], "tag": tag, "at": _now()}
        self._append(row)
        return row

    def tags(self, sha256: str) -> list[str]:
        return [row["tag"] for row in self.rows() if row.get("event") == "tag" and row["sha256"] == sha256]

    def verify_entry(self, sha_prefix: str) -> dict:
        """Re-checks an archived ZIP: its bytes still hash to the indexed sha256 and pass verification."""
        row = self.find(sha_prefix)
        path = self.root / row["path"]
        if not path.is_file():
            raise BridgeError("PACKAGE_MISSING", f"Archived file is missing: {path}")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != row["sha256"]:
            raise BridgeError("PACKAGE_INVALID", f"{path} no longer matches its indexed sha256")
        info = _verify_bytes(data)
        return {"sha256": row["sha256"], "kind": info["kind"], "path": str(path), "valid": True,
                "limits": "Integrity relative to the package manifest only; device, time and content are not authenticated."}

    def _append(self, row: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with self.index_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
