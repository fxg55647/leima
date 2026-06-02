"""Tarkistaa vastaako webhook-SHA tämän agentin viimeistä pushia.

Käyttö: python hooks/webhook_sha_check.py <sha>
Tulostaa JSON: {"is_mine": bool, "push_sha": str|null, "webhook_sha": str, "age_s": int|null}
Exit 0 = täsmää (oma push), 1 = ei täsmää tai push_log puuttuu.
"""
import json, sys, time
from pathlib import Path

PUSH_LOG = Path(__file__).parent.parent / ".claude" / "push_log.json"


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "anna SHA argumenttina"}))
        sys.exit(2)

    webhook_sha = sys.argv[1].strip()

    if not PUSH_LOG.exists():
        print(json.dumps({"is_mine": False, "push_sha": None, "webhook_sha": webhook_sha, "age_s": None}))
        sys.exit(1)

    log = json.loads(PUSH_LOG.read_text(encoding="utf-8"))
    push_sha = log.get("sha", "")
    is_mine = push_sha == webhook_sha or push_sha.startswith(webhook_sha) or webhook_sha.startswith(push_sha[:7])

    try:
        ts = log.get("timestamp", "")
        from datetime import datetime
        pushed_at = datetime.fromisoformat(ts)
        age_s = int((datetime.now() - pushed_at).total_seconds())
    except Exception:
        age_s = None

    result = {"is_mine": is_mine, "push_sha": push_sha, "webhook_sha": webhook_sha, "age_s": age_s}
    print(json.dumps(result))
    sys.exit(0 if is_mine else 1)


main()
