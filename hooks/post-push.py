"""Post-push hook -- waits for GitHub Actions to deploy the new commit to Render."""
import io, json, os, sys, time
import urllib.request as req
import subprocess
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

GITHUB_REPO   = "fxg55647/leima"
GITHUB_BRANCH = "main"
LOG_URL       = "https://fxg55647.github.io/leima/status-log.jsonl"
GH_API_BASE   = f"https://api.github.com/repos/{GITHUB_REPO}"

POLL_INT         = 15   # sekuntia pollausvälillä
REVIEW_TIMEOUT   = 300  # 5 min code review max
DEPLOY_TIMEOUT   = 240  # 4 min deploy max


def pushed_commit() -> str:
    r = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip()


def gh_get(path: str, token: str) -> dict | None:
    url = f"{GH_API_BASE}{path}"
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = req.Request(url, headers=headers)
        with req.urlopen(r, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def wait_for_review(commit: str, token: str) -> str | None:
    """Odottaa code review -ajoa commitille. Palauttaa 'success'/'failure'/None."""
    print(f"[deploy] Odotetaan code review -ajoa commitille {commit[:7]}...", flush=True)
    deadline = time.time() + REVIEW_TIMEOUT
    while time.time() < deadline:
        data = gh_get(
            f"/actions/workflows/code_review.yml/runs?per_page=10&branch={GITHUB_BRANCH}",
            token,
        )
        if data:
            for run in data.get("workflow_runs", []):
                if run.get("head_sha", "").startswith(commit[:20]):
                    status     = run.get("status")
                    conclusion = run.get("conclusion")
                    if status == "completed":
                        return conclusion
                    print(f"[deploy] Code review: {status}...", flush=True)
                    break
            else:
                print("[deploy] Ajo ei ole vielä alkanut...", flush=True)
        time.sleep(POLL_INT)
    return None


def fetch_poide() -> dict | None:
    try:
        with req.urlopen(LOG_URL, timeout=10) as r:
            lines = r.read().decode().strip().splitlines()
        for line in reversed(lines):
            line = line.strip()
            if line:
                return json.loads(line)
    except Exception:
        return None
    return None


def wait_for_deploy(commit: str) -> bool:
    """Odottaa että Render on live commit-SHA:lla. Palauttaa True jos onnistuu."""
    print(f"[deploy] Odotetaan deployta commitille {commit[:7]}...", flush=True)
    deadline = time.time() + DEPLOY_TIMEOUT
    while time.time() < deadline:
        entry = fetch_poide()
        if entry:
            live = entry.get("deployed_commit", "") or ""
            if live.startswith(commit[:20]):
                return True
            deploying = entry.get("deploying", False)
            status = "deploy käynnissä" if deploying else "odottaa"
            print(f"[deploy] Live: {live[:7] or '?'} → tavoite: {commit[:7]} ({status})", flush=True)
        time.sleep(POLL_INT)
    return False


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN", "")
    commit = pushed_commit()

    conclusion = wait_for_review(commit, token)

    if conclusion is None:
        print(f"[deploy] !! Code review ei valmistunut {REVIEW_TIMEOUT}s sisällä.", flush=True)
        return 0
    if conclusion != "success":
        print(f"[deploy] FAIL Code review epäonnistui ({conclusion}) — deploy peruuntui.", flush=True)
        return 0

    print("[deploy] OK Code review hyväksytty.", flush=True)

    if wait_for_deploy(commit):
        print(f"[deploy] OK Deploy valmis — {commit[:7]} on live.", flush=True)
    else:
        print(f"[deploy] !! Deploy ei valmistunut {DEPLOY_TIMEOUT}s sisällä — tarkista Render.", flush=True)

    return 0


sys.exit(main())
