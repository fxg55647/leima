"""
Fetch status-log.jsonl from gh-pages, compute a monthly summary for the
previous calendar month, upload it to Arweave, and print the tx_id and URL
so the GitHub Action can commit them to the repo.
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

now = datetime.now(timezone.utc)
year, month = (now.year - 1, 12) if now.month == 1 else (now.year, now.month - 1)
month_str = f"{year}-{month:02d}"

r = http.get(f"{PAGES_URL}/status-log.jsonl", timeout=30)
r.raise_for_status()

entries = [json.loads(line) for line in r.text.strip().splitlines() if line.strip()]
month_entries = [e for e in entries if e.get("ts", "").startswith(month_str)]

if not month_entries:
    print(f"No entries found for {month_str}", file=sys.stderr)
    sys.exit(1)

total     = len(month_entries)
ok_count  = sum(1 for e in month_entries if e.get("ok"))
uptime    = round(ok_count / total * 100, 2)

seen, deploy_count = set(), 0
for e in month_entries:
    c = e.get("commit", "")
    if c and c not in seen:
        seen.add(c)
        deploy_count += 1

failed_windows = [e for e in month_entries if not e.get("ok")]

def _count_status(entries, status):
    return sum(1 for e in entries if e.get("deploy_status") == status)

summary = {
    "type":                      "poide-monthly-summary",
    "month":                     month_str,
    "total_checks":              total,
    "ok_checks":                 ok_count,
    "uptime_pct":                uptime,
    "deploy_count":              deploy_count,
    "failed_windows":            len(failed_windows),
    "failures_not_configured":   _count_status(failed_windows, "not_configured"),
    "failures_error":            _count_status(failed_windows, "error"),
    "failures_no_live_deploy":   _count_status(failed_windows, "no_live_deploy"),
    "failures_commit_mismatch":  sum(1 for e in failed_windows if not e.get("deployment_ok") and e.get("deploy_status") == "live"),
    "generated_at":              now.strftime("%Y-%m-%d %H:%M:%S UTC"),
}

builder = Builder("ethereum").wallet(IRYS_PRIVATE_KEY).network(IRYS_NETWORK)
if IRYS_RPC_URL:
    builder = builder.rpc_url(IRYS_RPC_URL)
uploader = builder.build()

tags = tags_from_dict({
    "Content-Type": "application/json",
    "App-Name":     "Leima",
    "Leima-Type":   "poide-monthly-summary",
    "Month":        month_str,
})

result = uploader.upload(bytearray(json.dumps(summary, indent=2).encode()), tags)
tx_id  = result["id"]
url    = f"{GATEWAY}/{tx_id}"

summary["arweave_tx"]  = tx_id
summary["arweave_url"] = url

print(f"MONTH={month_str}")
print(f"TX={tx_id}")
print(f"URL={url}")
print(json.dumps(summary, indent=2), file=sys.stderr)
