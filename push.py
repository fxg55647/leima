#!/usr/bin/env python3
"""git push + odota code review valmistumista."""
import subprocess, sys, time, json
from datetime import datetime, timezone

WORKFLOW   = "code_review.yml"
POLL_SEC   = 30
MAX_MIN    = 8
FIND_TRIES = 10


def run(cmd, **kw):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, **kw)


def gh_json(cmd):
    r = run(cmd)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except Exception:
        return None


def push():
    r = subprocess.run("git push", shell=True)
    return r.returncode == 0


def find_run(after: datetime):
    for _ in range(FIND_TRIES):
        time.sleep(5)
        data = gh_json(f"gh run list --workflow {WORKFLOW} --limit 1 --json databaseId,createdAt,status")
        if not data:
            continue
        run_time = datetime.fromisoformat(data[0]["createdAt"].replace("Z", "+00:00"))
        if run_time > after:
            return data[0]["databaseId"]
    return None


def wait_for_review(run_id):
    attempts = (MAX_MIN * 60) // POLL_SEC
    for i in range(attempts):
        time.sleep(POLL_SEC)
        data = gh_json(f"gh run view {run_id} --json status,conclusion")
        if not data:
            continue
        print(f"  [{i+1}/{attempts}] {data['status']}...")
        if data["status"] == "completed":
            return data["conclusion"]
    return "timeout"


if __name__ == "__main__":
    print("Pushataan...")
    push_time = datetime.now(timezone.utc)
    if not push():
        print("Push epäonnistui.")
        sys.exit(1)

    print("Etsitään code review -ajoa...")
    run_id = find_run(push_time)
    if not run_id:
        print("Code review -ajoa ei löydy.")
        sys.exit(1)

    print(f"Seurataan run {run_id} ({POLL_SEC}s välein, max {MAX_MIN} min)...")
    conclusion = wait_for_review(run_id)

    if conclusion == "success":
        print("CODE REVIEW: läpäisty ✓")
    elif conclusion == "timeout":
        print(f"CODE REVIEW: timeout {MAX_MIN} min jälkeen — tarkista manuaalisesti")
        sys.exit(1)
    else:
        print(f"CODE REVIEW: FEILASI ({conclusion}) — gh run view {run_id}")
        sys.exit(1)
