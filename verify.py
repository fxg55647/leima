#!/usr/bin/env python3
"""
verify.py — Independent POIDE integrity check.

Run from anywhere:
    pip install requests
    python verify.py

Fetches the latest Arweave record independently, reads the monitor_files
hashes stored there, and compares them to the current files on GitHub.
Does not contact the Leima service at all.

Optionally check a specific Arweave TX:
    python verify.py <tx_id>
"""
import base64, hashlib, json, sys
import requests

REPO      = "fxg55647/leima"
BRANCH    = "main"
PAGES_URL = "https://fxg55647.github.io/leima"
GATEWAY   = "https://gateway.irys.xyz"


def github_file_hash(path: str) -> str | None:
    url = f"https://api.github.com/repos/{REPO}/contents/{path}?ref={BRANCH}"
    r = requests.get(url, headers={"Accept": "application/vnd.github+json"}, timeout=10)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    content = base64.b64decode(r.json()["content"])
    return hashlib.sha256(content).hexdigest()


def load_log() -> list[dict]:
    print("Fetching status log from gh-pages...")
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
        print(f"Last commit mismatch : {last_mismatch.get('ts', '?')}  commit={last_mismatch.get('commit','?')}")
        if last_ok and last_ok.get("ts", "") > last_mismatch.get("ts", ""):
            print(f"Resolved at          : {last_ok.get('ts', '?')}")
        else:
            print("  (not yet resolved in log)")
    else:
        print("Last commit mismatch : none found in log")


def fetch_arweave(tx: str) -> dict:
    print(f"Fetching from Arweave: {GATEWAY}/{tx}")
    r = requests.get(f"{GATEWAY}/{tx}", timeout=30)
    r.raise_for_status()
    return r.json()


# --- main ---

tx_arg = sys.argv[1] if len(sys.argv) > 1 else None
entries = load_log()

if tx_arg:
    tx = tx_arg
    ts = "provided manually"
    print(f"Using TX: {tx}")
    arweave_status = fetch_arweave(tx)
else:
    entry = find_latest_tx(entries)
    tx = entry["tx"]
    ts = entry.get("ts", "?")
    print(f"Latest Arweave TX : {tx}")
    print(f"Recorded at       : {ts}")
    arweave_status = fetch_arweave(tx)

report_mismatch_history(entries)
print()

monitor_files = arweave_status.get("monitor_files")
if not monitor_files:
    raise SystemExit(
        "No monitor_files in this Arweave record.\n"
        "Try an older TX that was recorded after monitor_files was added."
    )

recorded_commit = arweave_status.get("expected_commit", "?")[:7]
print(f"GitHub commit at record time: {recorded_commit}")
print(f"\nComparing {len(monitor_files)} files — Arweave record vs GitHub ({REPO}@{BRANCH}):\n")

ok = True
for path, recorded_hash in monitor_files.items():
    current_hash = github_file_hash(path)

    if recorded_hash is None and current_hash is None:
        print(f"  --  {path}  (absent in both)")
    elif current_hash is None:
        print(f"  !!  {path}  MISSING on GitHub")
        ok = False
    elif recorded_hash is None:
        print(f"  ++  {path}  new file (not in Arweave record)")
    elif current_hash == recorded_hash:
        print(f"  OK  {path}")
    else:
        print(f"  !!  {path}  CHANGED")
        print(f"        Arweave : {recorded_hash}")
        print(f"        GitHub  : {current_hash}")
        ok = False

print()
if ok:
    print("All monitored files match the Arweave record.")
    print(f"Arweave record is the ground truth: {GATEWAY}/{tx}")
else:
    print("WARNING: files have changed since the Arweave record.")
    print("Check git history to understand when and why:")
    print("  git log --oneline -- <filename>")

sys.exit(0 if ok else 1)
