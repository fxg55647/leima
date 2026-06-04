import hashlib, os, sys, json, requests
from datetime import datetime, timezone
from pathlib import Path

TREAD_WORKFLOWS   = ["tread.yml"]
MAX_CRON_AGE_MIN  = 10  # 5-min schedule with 2× headroom

MONITOR_FILES = [
    ".github/workflows/tread.yml",
    ".github/workflows/monthly-audit.yml",
    ".github/workflows/code_review.yml",
    "tread_check.py",
    "tread_arweave.py",
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

VERCEL_TOKEN      = os.environ.get("VERCEL_TOKEN", "")
VERCEL_PROJECT_ID = os.environ.get("VERCEL_PROJECT_ID", "")
VERCEL_TEAM_ID    = os.environ.get("VERCEL_TEAM_ID", "")
GITHUB_REPO       = os.environ.get("GITHUB_REPO", "fxg55647/leima")
GITHUB_BRANCH     = os.environ.get("GITHUB_BRANCH", "main")
GITHUB_TOKEN      = os.environ.get("GITHUB_TOKEN", "")

_COMPLETED        = {"live", "deactivated"}
_VERCEL_BUILDING  = {"BUILDING", "QUEUED", "INITIALIZING"}


def validate_deployment_source(meta: dict) -> tuple[bool, list]:
    """Tarkistaa tuleeko deployment odotetusta GitHub-reposta/branchista."""
    expected_org, expected_repo = GITHUB_REPO.split("/")
    org = meta.get("githubOrg") or meta.get("githubCommitOrg", "")
    repo = meta.get("githubRepo") or meta.get("githubCommitRepo", "")
    ref = meta.get("githubCommitRef", "")
    if not org and not repo:
        return False, ["no_github_integration_meta"]
    mismatches = []
    if org and org != expected_org:
        mismatches.append(f"githubOrg: got '{org}' expected '{expected_org}'")
    if repo and repo != expected_repo:
        mismatches.append(f"githubRepo: got '{repo}' expected '{expected_repo}'")
    if ref and ref != GITHUB_BRANCH:
        mismatches.append(f"githubCommitRef: got '{ref}' expected '{GITHUB_BRANCH}'")
    return len(mismatches) == 0, mismatches


def vercel_state():
    """Returns (live_commit, deploying, deploying_commit, service_url, source_ok, source_mismatches)."""
    if not VERCEL_TOKEN or not VERCEL_PROJECT_ID:
        return None, False, None, None, None, []
    headers = {"Authorization": f"Bearer {VERCEL_TOKEN}"}
    params = f"projectId={VERCEL_PROJECT_ID}&limit=10"
    if VERCEL_TEAM_ID:
        params += f"&teamId={VERCEL_TEAM_ID}"
    resp = requests.get(
        f"https://api.vercel.com/v6/deployments?{params}",
        headers=headers,
        timeout=10,
    )
    resp.raise_for_status()
    deployments = resp.json().get("deployments", [])
    if not deployments:
        return None, False, None, None, None, []
    first = deployments[0]
    deploying = first.get("state") in _VERCEL_BUILDING
    deploying_meta = first.get("meta") or {}
    deploying_commit = deploying_meta.get("githubCommitSha") if deploying else None
    source_ok, source_mismatches = validate_deployment_source(deploying_meta) if deploying else (None, [])
    live_commit = None
    service_url = None
    for d in deployments:
        if d.get("state") == "READY" and d.get("target") == "production":
            live_commit = (d.get("meta") or {}).get("githubCommitSha")
            if d.get("url"):
                service_url = f"https://{d['url']}"
            break
    return live_commit, deploying, deploying_commit, service_url, source_ok, source_mismatches


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
        print(f"github_commit: HTTP {resp.status_code} — {resp.text[:200]}", file=sys.stderr)
        return None, resp.status_code
    return resp.text.strip(), 200


def check_workflow_states() -> dict[str, str]:
    """Returns {workflow_filename: state} where state is active/disabled_inactivity/etc."""
    gh_headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        gh_headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    states = {}
    for workflow in TREAD_WORKFLOWS:
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
    for workflow in TREAD_WORKFLOWS:
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
    gh_headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        gh_headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    last_mismatch_at = None
    last_mismatch_commit = None
    oldest_at = None
    scanned = 0
    window_cutoff = datetime.now(timezone.utc).timestamp() - RAPID_DEPLOY_WINDOW_MIN * 60
    deploys_in_window = 0

    # Kerää (commit_id, created_at) -parit kaikista lähteistä
    entries = []

    if VERCEL_TOKEN and VERCEL_PROJECT_ID:
        try:
            params = f"projectId={VERCEL_PROJECT_ID}&limit=20&state=READY&target=production"
            if VERCEL_TEAM_ID:
                params += f"&teamId={VERCEL_TEAM_ID}"
            resp = requests.get(
                f"https://api.vercel.com/v6/deployments?{params}",
                headers={"Authorization": f"Bearer {VERCEL_TOKEN}"},
                timeout=10,
            )
            resp.raise_for_status()
            for d in resp.json().get("deployments", []):
                commit_id = (d.get("meta") or {}).get("githubCommitSha")
                created_at = d.get("createdAt")
                if created_at:
                    try:
                        created_at = datetime.fromtimestamp(
                            created_at / 1000, tz=timezone.utc
                        ).isoformat()
                    except Exception:
                        pass
                if commit_id:
                    entries.append((commit_id, created_at))
        except Exception:
            pass

    for commit_id, created_at in entries:
        scanned += 1
        if oldest_at is None or (created_at and created_at < oldest_at):
            oldest_at = created_at

        if created_at:
            try:
                ts = datetime.fromisoformat(str(created_at).replace("Z", "+00:00")).timestamp()
                if ts > window_cutoff:
                    deploys_in_window += 1
            except ValueError:
                pass

        if commit_id:
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
    vercel_deployed, vercel_deploying, vercel_deploying_commit, vercel_service_url, vercel_source_ok, vercel_source_mismatches = vercel_state()
except Exception as e:
    vercel_deployed, vercel_deploying, vercel_deploying_commit, vercel_service_url, vercel_source_ok, vercel_source_mismatches = None, False, None, None, None, []
    error = str(e)

github_commit_status = 200
try:
    expected, github_commit_status = github_commit()
except Exception as e:
    expected = None
    github_commit_status = None
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

deployment_ok = bool(vercel_deployed and expected and (
    vercel_deployed.startswith(expected[:7]) or expected.startswith(vercel_deployed[:7])
))
deploying_commit_ok = bool(
    vercel_deploying and vercel_deploying_commit and expected and
    vercel_deploying_commit.startswith(expected[:7])
)
review_ok = review_conclusion == "success"
github_commit_unknown = expected is None
# deployment_safe: running code is the expected code, or the mismatch is explained
# by the normal deploy gate (review running or failed → old safe code still live)
deployment_safe = deployment_ok or deploying_commit_ok or review_conclusion in ("in_progress", "failure")
# review_stuck: code review has failed repeatedly — commits are not deploying
REVIEW_STUCK_THRESHOLD = 3
review_stuck = (review_consecutive_failures or 0) >= REVIEW_STUCK_THRESHOLD
rapid_deploy_warning = history.get("deploys_last_hour", 0) >= RAPID_DEPLOY_THRESHOLD
# When GitHub API fails to return expected commit, the result is indeterminate (null),
# not a mismatch (false). Returning false would be a false positive danger alarm.
if github_commit_unknown:
    ok = None
else:
    ok = deployment_safe and (cron_fresh is not False) and not disabled_workflows

result = {
    "ok": ok,
    "rapid_deploy_warning": rapid_deploy_warning,
    "deployment_ok": deployment_ok,
    "github_commit_unknown": github_commit_unknown,
    "github_commit_http_status": github_commit_status,
    "vercel_deployed_commit": vercel_deployed,
    "vercel_deploying": vercel_deploying,
    "vercel_service_url": vercel_service_url or "",
    "vercel_source_ok": vercel_source_ok,
    "vercel_source_mismatches": vercel_source_mismatches,
    "review_ok": review_ok,
    "review_consecutive_failures": review_consecutive_failures,
    "review_stuck": review_stuck,
    "deploying_commit_ok": deploying_commit_ok,
    "expected_commit": expected,
    "review_conclusion": review_conclusion,
    "cron_fresh": cron_fresh,
    "workflow_states": workflow_states,
    "disabled_workflows": disabled_workflows,
    "history": history,
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

