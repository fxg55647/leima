import hashlib, os, sys, json, requests
from datetime import datetime, timezone
from pathlib import Path

POIDE_WORKFLOWS   = ["poide-a.yml"]
MAX_CRON_AGE_MIN  = 10  # 5-min schedule with 2× headroom

MONITOR_FILES = [
    ".github/workflows/poide-a.yml",
    ".github/workflows/poide-run.yml",
    ".github/workflows/monthly-audit.yml",
    ".github/workflows/code_review.yml",
    "poide_check.py",
    "poide_arweave.py",
    "monthly_audit.py",
    "code_review.py",
    "POLICY.example.md",
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
GITHUB_REPO       = os.environ.get("GITHUB_REPO", "fxg55647/leima")
GITHUB_BRANCH     = os.environ.get("GITHUB_BRANCH", "main")
GITHUB_TOKEN      = os.environ.get("GITHUB_TOKEN", "")

_IN_PROGRESS      = {"build_in_progress", "update_in_progress", "pre_deploy_in_progress"}
_COMPLETED        = {"live", "deactivated"}


def render_state():
    if not RENDER_API_KEY or not RENDER_SERVICE_ID:
        return None, "not_configured", False, None, None
    headers = {"Authorization": f"Bearer {RENDER_API_KEY}"}

    svc_resp = requests.get(
        f"https://api.render.com/v1/services/{RENDER_SERVICE_ID}",
        headers=headers,
        timeout=10,
    )
    svc_resp.raise_for_status()
    svc = svc_resp.json()
    service_url = svc.get("serviceDetails", {}).get("url") or svc.get("url", "")

    resp = requests.get(
        f"https://api.render.com/v1/services/{RENDER_SERVICE_ID}/deploys?limit=20",
        headers=headers,
        timeout=10,
    )
    resp.raise_for_status()
    deploys = resp.json()
    deploying = bool(deploys and deploys[0].get("deploy", {}).get("status") in _IN_PROGRESS)
    deploying_commit = (
        deploys[0].get("deploy", {}).get("commit", {}).get("id") if deploying else None
    )
    for item in deploys:
        deploy = item.get("deploy", {})
        if deploy.get("status") == "live":
            return deploy.get("commit", {}).get("id"), "live", deploying, service_url, deploying_commit
    return None, "no_live_deploy", deploying, service_url, deploying_commit


def github_commit():
    gh_headers = {"Accept": "application/vnd.github.sha"}
    if GITHUB_TOKEN:
        gh_headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    resp = requests.get(
        f"https://api.github.com/repos/{GITHUB_REPO}/commits/{GITHUB_BRANCH}",
        headers=gh_headers,
        timeout=10,
    )
    if resp.status_code != 200:
        return None
    return resp.text.strip()


def check_workflow_states() -> dict[str, str]:
    """Returns {workflow_filename: state} where state is active/disabled_inactivity/etc."""
    gh_headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        gh_headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    states = {}
    for workflow in POIDE_WORKFLOWS:
        resp = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/{workflow}",
            headers=gh_headers,
            timeout=10,
        )
        if resp.status_code == 200:
            states[workflow] = resp.json().get("state", "unknown")
        else:
            states[workflow] = "unknown"
    return states


def check_cron_freshness() -> bool | None:
    """True = at least one cron ran within window; False = all stale or API unreachable; None = no runs exist yet."""
    cutoff = datetime.now(timezone.utc).timestamp() - MAX_CRON_AGE_MIN * 60
    found_any = False
    any_api_success = False
    for workflow in POIDE_WORKFLOWS:
        resp = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/{workflow}/runs"
            f"?per_page=1&branch={GITHUB_BRANCH}",
            headers={"Accept": "application/vnd.github+json"},
            timeout=10,
        )
        if resp.status_code != 200:
            continue
        any_api_success = True
        runs = resp.json().get("workflow_runs", [])
        if not runs:
            continue
        found_any = True
        updated = runs[0].get("updated_at", "")
        if updated:
            ts = datetime.fromisoformat(updated.replace("Z", "+00:00")).timestamp()
            if ts > cutoff:
                return True
    if not any_api_success:
        return False  # all requests failed (rate limit / network) — assume stale
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

    return {
        "scanned_deploys": scanned,
        "last_mismatch_at": last_mismatch_at,
        "last_mismatch_commit": last_mismatch_commit,
        "clean_since": oldest_at if last_mismatch_at is None else None,
        "deploys_last_hour": deploys_in_window,
    }


def github_review_status():
    resp = requests.get(
        f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/code_review.yml/runs"
        f"?per_page=10&branch={GITHUB_BRANCH}",
        headers={"Accept": "application/vnd.github+json"},
        timeout=10,
    )
    if resp.status_code != 200:
        return None, 0
    runs = resp.json().get("workflow_runs", [])
    if not runs:
        return None, 0
    latest = runs[0]
    if latest.get("status") != "completed":
        conclusion = "in_progress"
    else:
        conclusion = latest.get("conclusion")

    consecutive_failures = 0
    for run in runs:
        if run.get("status") != "completed":
            continue
        if run.get("conclusion") == "failure":
            consecutive_failures += 1
        else:
            break

    return conclusion, consecutive_failures


error = None
try:
    deployed, deploy_status, deploying, service_url, deploying_commit = render_state()
except Exception as e:
    deployed, deploy_status, deploying, service_url, deploying_commit, error = None, "error", False, None, None, str(e)

try:
    expected = github_commit()
except Exception as e:
    expected = None
    error = (error + "; " if error else "") + str(e)

try:
    review_conclusion, review_consecutive_failures = github_review_status()
except Exception as e:
    review_conclusion, review_consecutive_failures = None, 0
    error = (error + "; " if error else "") + str(e)

try:
    cron_fresh = check_cron_freshness()
except Exception as e:
    cron_fresh = None
    error = (error + "; " if error else "") + str(e)

try:
    workflow_states = check_workflow_states()
except Exception as e:
    workflow_states = {}
    error = (error + "; " if error else "") + str(e)

disabled_workflows = [w for w, s in workflow_states.items() if s != "active"]

try:
    history = check_deploy_history()
except Exception as e:
    history = {"scanned_deploys": 0, "last_mismatch_at": None, "clean_since": None}
    error = (error + "; " if error else "") + str(e)

deployment_ok = bool(deployed and expected and deployed == expected)
deploying_commit_ok = bool(deploying and deploying_commit and expected and deploying_commit.startswith(expected[:7]))
review_ok = review_conclusion == "success"
# deployment_safe: running code is the expected code, or the mismatch is explained
# by the normal deploy gate (review running or failed → old safe code still live)
deployment_safe = deployment_ok or deploying_commit_ok or review_conclusion in ("in_progress", "failure")
# review_stuck: code review has failed repeatedly — commits are not deploying
REVIEW_STUCK_THRESHOLD = 3
review_stuck = review_consecutive_failures >= REVIEW_STUCK_THRESHOLD
rapid_deploy_warning = history.get("deploys_last_hour", 0) >= RAPID_DEPLOY_THRESHOLD
ok = deployment_safe and (cron_fresh is not False) and not disabled_workflows

result = {
    "ok": ok,
    "rapid_deploy_warning": rapid_deploy_warning,
    "deployment_ok": deployment_ok,
    "review_ok": review_ok,
    "review_consecutive_failures": review_consecutive_failures,
    "review_stuck": review_stuck,
    "deploying": deploying,
    "deploying_commit": deploying_commit,
    "deploying_commit_ok": deploying_commit_ok,
    "deployed_commit": deployed,
    "expected_commit": expected,
    "deploy_status": deploy_status,
    "review_conclusion": review_conclusion,
    "cron_fresh": cron_fresh,
    "workflow_states": workflow_states,
    "disabled_workflows": disabled_workflows,
    "history": history,
    "service_url": service_url or "",
    "repo": GITHUB_REPO,
    "branch": GITHUB_BRANCH,
    "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    "monitor_files": hash_monitor_files(),
    "actions_run_id": os.environ.get("GITHUB_RUN_ID", ""),
    "actions_run_url": (
        f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}"
        f"/{GITHUB_REPO}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"
        if os.environ.get("GITHUB_RUN_ID") else ""
    ),
}
if error:
    result["error"] = error

os.makedirs("pages-output", exist_ok=True)
with open("pages-output/status.json", "w") as f:
    json.dump(result, f, indent=2)

print(json.dumps(result, indent=2))
