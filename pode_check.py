import hashlib, os, sys, json, requests
from datetime import datetime, timezone
from pathlib import Path

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
GITHUB_REPO       = os.environ.get("GITHUB_REPO", "fxg55647/leima")
GITHUB_BRANCH     = os.environ.get("GITHUB_BRANCH", "main")

_IN_PROGRESS = {"build_in_progress", "update_in_progress", "pre_deploy_in_progress"}


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

deployment_ok = bool(deployed and expected and deployed.startswith(expected[:7]))
review_ok = review_conclusion == "success"
ok = deployment_ok and review_ok and not deploying

result = {
    "ok": ok,
    "deployment_ok": deployment_ok,
    "review_ok": review_ok,
    "deploying": deploying,
    "deployed_commit": deployed,
    "expected_commit": expected,
    "deploy_status": deploy_status,
    "review_conclusion": review_conclusion,
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
