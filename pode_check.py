import hashlib, os, sys, json, requests
from datetime import datetime, timezone
from pathlib import Path

PODE_WORKFLOWS    = [f"pode-{c}.yml" for c in "abcde"]
MAX_CRON_AGE_MIN  = 10  # 5-min schedule with 2× headroom

MONITOR_FILES = [
    ".github/workflows/pode-a.yml",
    ".github/workflows/pode-b.yml",
    ".github/workflows/pode-c.yml",
    ".github/workflows/pode-d.yml",
    ".github/workflows/pode-e.yml",
    ".github/workflows/code_review.yml",
    "pode_check.py",
    "code_review.py",
    "POLICY.md",
]


def hash_monitor_files() -> dict[str, str | None]:
    root = Path(__file__).parent
    return {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        if (root / name).exists() else None
        for name in MONITOR_FILES
    }

RENDER_API_KEY    = os.environ.get("RENDER_API_KEY", "")
RENDER_SERVICE_ID = os.environ.get("RENDER_SERVICE_ID", "")
RENDER_SERVICE_URL = os.environ.get("RENDER_SERVICE_URL", "")
GITHUB_REPO       = os.environ.get("GITHUB_REPO", "fxg55647/leima")
GITHUB_BRANCH     = os.environ.get("GITHUB_BRANCH", "main")
GITHUB_TOKEN      = os.environ.get("GITHUB_TOKEN", "")

_IN_PROGRESS      = {"build_in_progress", "update_in_progress", "pre_deploy_in_progress"}
_COMPLETED        = {"live", "deactivated"}


def render_state():
    if not RENDER_API_KEY or not RENDER_SERVICE_ID:
        return None, "not_configured", False
    resp = requests.get(
        f"https://api.render.com/v1/services/{RENDER_SERVICE_ID}/deploys?limit=5",
        headers={"Authorization": f"Bearer {RENDER_API_KEY}"},
        timeout=10,
    )
    resp.raise_for_status()
    deploys = resp.json()
    deploying = bool(deploys and deploys[0].get("deploy", {}).get("status") in _IN_PROGRESS)
    for item in deploys:
        deploy = item.get("deploy", {})
        if deploy.get("status") == "live":
            return deploy.get("commit", {}).get("id"), "live", deploying
    return None, "no_live_deploy", deploying


def github_commit():
    resp = requests.get(
        f"https://api.github.com/repos/{GITHUB_REPO}/commits/{GITHUB_BRANCH}",
        headers={"Accept": "application/vnd.github.sha"},
        timeout=10,
    )
    if resp.status_code != 200:
        return None
    return resp.text.strip()


def check_cron_freshness() -> bool | None:
    """True = at least one cron ran within window; False = all stale; None = no data yet."""
    cutoff = datetime.now(timezone.utc).timestamp() - MAX_CRON_AGE_MIN * 60
    found_any = False
    for workflow in PODE_WORKFLOWS:
        resp = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/{workflow}/runs"
            f"?per_page=1&branch={GITHUB_BRANCH}",
            headers={"Accept": "application/vnd.github+json"},
            timeout=10,
        )
        if resp.status_code != 200:
            continue
        runs = resp.json().get("workflow_runs", [])
        if not runs:
            continue
        found_any = True
        updated = runs[0].get("updated_at", "")
        if updated:
            ts = datetime.fromisoformat(updated.replace("Z", "+00:00")).timestamp()
            if ts > cutoff:
                return True
    return False if found_any else None


RAPID_DEPLOY_WINDOW_MIN = 60   # sliding window for burst detection
RAPID_DEPLOY_THRESHOLD  = 10   # deploys in that window triggers warning


def check_deploy_history() -> dict:
    if not RENDER_API_KEY or not RENDER_SERVICE_ID:
        return {"scanned_deploys": 0, "last_mismatch_at": None, "clean_since": None}

    resp = requests.get(
        f"https://api.render.com/v1/services/{RENDER_SERVICE_ID}/deploys?limit=100",
        headers={"Authorization": f"Bearer {RENDER_API_KEY}"},
        timeout=10,
    )
    resp.raise_for_status()

    gh_headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        gh_headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    last_mismatch_at = None
    last_mismatch_commit = None
    oldest_at = None
    scanned = 0
    window_cutoff = datetime.now(timezone.utc).timestamp() - RAPID_DEPLOY_WINDOW_MIN * 60
    deploys_in_window = 0

    for item in resp.json():
        deploy = item.get("deploy", {})
        if deploy.get("status") not in _COMPLETED:
            continue
        commit_id = deploy.get("commit", {}).get("id")
        created_at = deploy.get("createdAt") or deploy.get("created_at")
        if not commit_id:
            continue

        scanned += 1
        if oldest_at is None or (created_at and created_at < oldest_at):
            oldest_at = created_at

        if created_at:
            try:
                ts = datetime.fromisoformat(created_at.replace("Z", "+00:00")).timestamp()
                if ts > window_cutoff:
                    deploys_in_window += 1
            except ValueError:
                pass

        r = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/commits/{commit_id}",
            headers=gh_headers,
            timeout=10,
        )
        if r.status_code == 404:
            if last_mismatch_at is None or (created_at and created_at > last_mismatch_at):
                last_mismatch_at = created_at
                last_mismatch_commit = commit_id[:7]

    rapid_deploy_warning = deploys_in_window >= RAPID_DEPLOY_THRESHOLD

    return {
        "scanned_deploys": scanned,
        "last_mismatch_at": last_mismatch_at,
        "last_mismatch_commit": last_mismatch_commit,
        "clean_since": oldest_at if last_mismatch_at is None else None,
        "deploys_last_hour": deploys_in_window,
        "rapid_deploy_warning": rapid_deploy_warning,
    }


def github_review_status():
    resp = requests.get(
        f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/code_review.yml/runs"
        f"?per_page=1&branch={GITHUB_BRANCH}",
        headers={"Accept": "application/vnd.github+json"},
        timeout=10,
    )
    if resp.status_code != 200:
        return None
    runs = resp.json().get("workflow_runs", [])
    if not runs:
        return None
    run = runs[0]
    if run.get("status") != "completed":
        return "in_progress"
    return run.get("conclusion")


error = None
try:
    deployed, deploy_status, deploying = render_state()
except Exception as e:
    deployed, deploy_status, deploying, error = None, "error", False, str(e)

try:
    expected = github_commit()
except Exception as e:
    expected = None
    error = (error + "; " if error else "") + str(e)

try:
    review_conclusion = github_review_status()
except Exception as e:
    review_conclusion = None
    error = (error + "; " if error else "") + str(e)

try:
    cron_fresh = check_cron_freshness()
except Exception as e:
    cron_fresh = None
    error = (error + "; " if error else "") + str(e)

try:
    history = check_deploy_history()
except Exception as e:
    history = {"scanned_deploys": 0, "last_mismatch_at": None, "clean_since": None}
    error = (error + "; " if error else "") + str(e)

deployment_ok = bool(deployed and expected and deployed.startswith(expected[:7]))
review_ok = review_conclusion == "success"
rapid_warning = history.get("rapid_deploy_warning", False)
ok = deployment_ok and review_ok and not deploying and (cron_fresh is not False) and not rapid_warning

result = {
    "ok": ok,
    "deployment_ok": deployment_ok,
    "review_ok": review_ok,
    "deploying": deploying,
    "deployed_commit": deployed,
    "expected_commit": expected,
    "deploy_status": deploy_status,
    "review_conclusion": review_conclusion,
    "cron_fresh": cron_fresh,
    "rapid_deploy_warning": rapid_warning,
    "history": history,
    "repo": GITHUB_REPO,
    "branch": GITHUB_BRANCH,
    "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    "monitor_files": hash_monitor_files(),
}
if error:
    result["error"] = error

os.makedirs("pages-output", exist_ok=True)
with open("pages-output/status.json", "w") as f:
    json.dump(result, f, indent=2)

print(json.dumps(result, indent=2))
sys.exit(0 if ok else 1)
