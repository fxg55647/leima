import os, sys, json, requests
from datetime import datetime, timezone

RENDER_API_KEY    = os.environ.get("RENDER_API_KEY", "")
RENDER_SERVICE_ID = os.environ.get("RENDER_SERVICE_ID", "")
GITHUB_REPO       = os.environ.get("GITHUB_REPO", "fxg55647/leima")
GITHUB_BRANCH     = os.environ.get("GITHUB_BRANCH", "main")


def render_commit():
    if not RENDER_API_KEY or not RENDER_SERVICE_ID:
        return None, "not_configured"
    resp = requests.get(
        f"https://api.render.com/v1/services/{RENDER_SERVICE_ID}/deploys?limit=5",
        headers={"Authorization": f"Bearer {RENDER_API_KEY}"},
        timeout=10,
    )
    resp.raise_for_status()
    for item in resp.json():
        deploy = item.get("deploy", {})
        if deploy.get("status") == "live":
            return deploy.get("commit", {}).get("id"), "live"
    return None, "no_live_deploy"


def github_commit():
    resp = requests.get(
        f"https://api.github.com/repos/{GITHUB_REPO}/commits/{GITHUB_BRANCH}",
        headers={"Accept": "application/vnd.github.sha"},
        timeout=10,
    )
    if resp.status_code != 200:
        return None
    return resp.text.strip()


error = None
try:
    deployed, deploy_status = render_commit()
except Exception as e:
    deployed, deploy_status, error = None, "error", str(e)

try:
    expected = github_commit()
except Exception as e:
    expected = None
    error = (error + "; " if error else "") + str(e)

ok = bool(deployed and expected and deployed.startswith(expected[:7]))

result = {
    "ok": ok,
    "deployed_commit": deployed,
    "expected_commit": expected,
    "deploy_status": deploy_status,
    "repo": GITHUB_REPO,
    "branch": GITHUB_BRANCH,
    "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
}
if error:
    result["error"] = error

os.makedirs("pages-output", exist_ok=True)
with open("pages-output/status.json", "w") as f:
    json.dump(result, f, indent=2)

print(json.dumps(result, indent=2))
sys.exit(0 if ok else 1)
