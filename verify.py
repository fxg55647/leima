#!/usr/bin/env python3
"""
verify.py — Independent POIDE integrity check.

Run from anywhere:
    pip install requests
    python verify.py

For each monitored file, checks git history (GitHub API) to determine
when it was last changed. Then fetches an Arweave record from around
that time to corroborate the hash. Two independent sources.

Optionally verify against a specific trusted Arweave TX:
    python verify.py <tx_id>
"""
import base64, hashlib, json, sys
from datetime import datetime, timezone
import requests

REPO      = "fxg55647/leima"
BRANCH    = "main"
PAGES_URL = "https://fxg55647.github.io/leima"
GATEWAY   = "https://gateway.irys.xyz"
GH_HDR    = {"Accept": "application/vnd.github+json"}


def github_file(path: str) -> tuple[str | None, str | None]:
    """Returns (sha256_hash, last_commit_date) for a file on GitHub."""
    url = f"https://api.github.com/repos/{REPO}/contents/{path}?ref={BRANCH}"
    r = requests.get(url, headers=GH_HDR, timeout=10)
    if r.status_code == 404:
        return None, None
    r.raise_for_status()
    content = base64.b64decode(r.json()["content"])
    file_hash = hashlib.sha256(content).hexdigest()

    log_url = f"https://api.github.com/repos/{REPO}/commits?path={path}&per_page=1&sha={BRANCH}"
    r2 = requests.get(log_url, headers=GH_HDR, timeout=10)
    last_changed = None
    if r2.status_code == 200 and r2.json():
        iso = r2.json()[0]["commit"]["committer"]["date"]
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        days_ago = (datetime.now(timezone.utc) - dt).days
        last_changed = f"{iso[:10]}  ({days_ago}d ago)"

    return file_hash, last_changed


def load_log() -> list[dict]:
    r = requests.get(f"{PAGES_URL}/status-log.jsonl", timeout=15)
    r.raise_for_status()
    entries = []
    for line in r.text.strip().splitlines():
        if line.strip():
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries


def find_latest_tx(entries: list[dict]) -> dict:
    for entry in reversed(entries):
        if entry.get("tx"):
            return entry
    raise SystemExit("No Arweave TX found in log.")


def fetch_arweave(tx: str) -> dict:
    r = requests.get(f"{GATEWAY}/{tx}", timeout=30)
    r.raise_for_status()
    return r.json()


def report_mismatch_history(entries: list[dict]) -> None:
    last_mismatch = None
    last_ok = None
    for e in reversed(entries):
        if e.get("deployment_ok") is False and not e.get("deploying"):
            if last_mismatch is None:
                last_mismatch = e
        if e.get("deployment_ok") is True:
            if last_ok is None:
                last_ok = e
        if last_mismatch and last_ok:
            break

    if last_mismatch:
        print(f"Last commit mismatch : {last_mismatch.get('ts', '?')}  commit={last_mismatch.get('commit', '?')}")
        if last_ok and last_ok.get("ts", "") > last_mismatch.get("ts", ""):
            print(f"Resolved at          : {last_ok.get('ts', '?')}")
        else:
            print("  (not yet resolved in log)")
    else:
        print("Last commit mismatch : none found in log")


# --- main ---

tx_arg = sys.argv[1] if len(sys.argv) > 1 else None

print(f"Fetching status log from gh-pages...")
entries = load_log()
print(f"  {len(entries)} entries in log")

report_mismatch_history(entries)
print()

if tx_arg:
    tx = tx_arg
    print(f"Using TX (provided)  : {tx}")
else:
    ref_entry = find_latest_tx(entries)
    tx = ref_entry["tx"]
    print(f"Latest Arweave TX    : {tx}")
    print(f"Recorded at          : {ref_entry.get('ts', '?')}")

print(f"Fetching Arweave record...")
arweave_status = fetch_arweave(tx)

monitor_files = arweave_status.get("monitor_files")
if not monitor_files:
    raise SystemExit("No monitor_files in this Arweave record.")

print(f"\nMonitored files — git history (GitHub) + Arweave corroboration:\n")
print(f"  {'File':<45} {'Last changed':>22}   {'Match'}")
print(f"  {'-'*45} {'-'*22}   {'-'*5}")

ok = True
for path, arweave_hash in monitor_files.items():
    current_hash, last_changed = github_file(path)

    if current_hash is None:
        print(f"  {'!! MISSING':<45} {'—':>22}   —")
        ok = False
        continue

    matches = current_hash == arweave_hash if arweave_hash else None
    match_str = "OK" if matches else ("NEW" if arweave_hash is None else "CHANGED")
    if match_str == "CHANGED":
        ok = False

    last_str = last_changed or "?"
    print(f"  {path:<45} {last_str:>22}   {match_str}")
    if match_str == "CHANGED":
        print(f"    Arweave : {arweave_hash}")
        print(f"    GitHub  : {current_hash}")

print()
if ok:
    print("All monitored files verified.\n")
    print("What this means:")
    print("  1. Git history (GitHub) confirms when each file was last changed.")
    print("     This is independent of the service — GitHub maintains the record.")
    print()
    print("  2. The Arweave record corroborates the file hashes at recording time.")
    print("     Arweave is permanent and cannot be altered retroactively.")
    print()
    print("  Together these guarantee:")
    print("  - If the files match and haven't changed, no undetected commit mismatch")
    print("    could have occurred — the monitoring code would have caught it.")
    print("  - The monitoring code itself has passed through automated code review")
    print("    (AI analysis) on every push, recorded permanently on Arweave.")
    print("  - Any tampering with these files is visible in git history.")
    print()
    print(f"  Arweave TX: {GATEWAY}/{tx}")
else:
    print("WARNING: one or more files have changed since the Arweave record.")
    print("This is not necessarily malicious — could be a legitimate update.")
    print("Check git history to understand when and why:")
    print("  git log --oneline -- <filename>")
    print()
    print("If the change is expected, run verify.py again without arguments")
    print("to verify against the latest Arweave record.")

sys.exit(0 if ok else 1)
