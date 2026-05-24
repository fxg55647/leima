"""
Upload the current POIDE status.json to Arweave and append the tx_id to the
cumulative log (pages-output/status-log.jsonl).

Run after poide_check.py. Exits 0 on success, 1 on failure — but poide-run.yml
marks this step continue-on-error so a failure never blocks the POIDE check itself.
"""
import json, os, sys
from datetime import datetime, timezone
from pathlib import Path

import requests as http
from irys_sdk import Builder
from irys_sdk.bundle.tags import from_dict as tags_from_dict

IRYS_PRIVATE_KEY = os.environ.get("IRYS_PRIVATE_KEY", "")
IRYS_NETWORK     = os.environ.get("IRYS_NETWORK", "mainnet")
IRYS_RPC_URL     = os.environ.get("IRYS_RPC_URL", "")
PAGES_URL        = os.environ.get("GITHUB_PAGES_URL", "https://fxg55647.github.io/leima")
GATEWAY          = "https://devnet.irys.xyz" if IRYS_NETWORK == "devnet" else "https://gateway.irys.xyz"

if not IRYS_PRIVATE_KEY:
    print("IRYS_PRIVATE_KEY not set — skipping Arweave upload", file=sys.stderr)
    sys.exit(0)

status_path = Path("pages-output/status.json")
log_path    = Path("pages-output/status-log.jsonl")

status = json.loads(status_path.read_text())

builder = Builder("ethereum").wallet(IRYS_PRIVATE_KEY).network(IRYS_NETWORK)
if IRYS_RPC_URL:
    builder = builder.rpc_url(IRYS_RPC_URL)
uploader = builder.build()

tags = tags_from_dict({
    "Content-Type":    "application/json",
    "App-Name":        "Leima",
    "Leima-Type":      "poide-status",
    "Checked-At":      status.get("checked_at", ""),
    "Deploy-Ok":       str(status.get("ok", False)).lower(),
})

result = uploader.upload(bytearray(status_path.read_bytes()), tags)
tx_id  = result["id"]

# Fetch existing log from gh-pages if not already present locally
if not log_path.exists():
    try:
        r = http.get(f"{PAGES_URL}/status-log.jsonl", timeout=10)
        if r.status_code == 200 and r.text.strip():
            log_path.write_bytes(r.content)
    except Exception:
        pass

entry = {
    "ts":            status.get("checked_at", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")),
    "tx":            tx_id,
    "ok":            status.get("ok", False),
    "commit":        (status.get("deployed_commit") or "")[:7],
    "deploy_status":        status.get("deploy_status", ""),
    "deployment_ok":        status.get("deployment_ok", False),
    "review_ok":            status.get("review_ok", False),
    "rapid_deploy_warning": status.get("rapid_deploy_warning", False),
}
with log_path.open("a") as f:
    f.write(json.dumps(entry) + "\n")

print(f"Uploaded: {GATEWAY}/{tx_id}")
