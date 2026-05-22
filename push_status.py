"""Push pages-output/status.json (and status-log.jsonl) to gh-pages via GitHub API."""
import base64, json, os, sys
from pathlib import Path
import requests

TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO  = os.environ.get("GITHUB_REPOSITORY", "fxg55647/leima")

if not TOKEN:
    print("GITHUB_TOKEN not set — skipping", file=sys.stderr)
    sys.exit(1)

HDR = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def push_file(path: Path, branch: str = "gh-pages") -> bool:
    content = base64.b64encode(path.read_bytes()).decode()
    name = path.name
    url = f"https://api.github.com/repos/{REPO}/contents/{name}"

    # fetch current SHA so we can update rather than create
    r = requests.get(url, headers=HDR, params={"ref": branch}, timeout=10)
    sha = r.json().get("sha") if r.status_code == 200 else None

    payload = {
        "message": "chore: update deployment status",
        "content": content,
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha

    r = requests.put(url, headers=HDR, json=payload, timeout=10)
    if r.status_code in (200, 201):
        print(f"Pushed {name} → {branch}")
        return True
    print(f"Failed to push {name}: {r.status_code} {r.text[:200]}", file=sys.stderr)
    return False


ok = True
for f in ["pages-output/status.json", "pages-output/status-log.jsonl"]:
    p = Path(f)
    if p.exists():
        ok = push_file(p) and ok

sys.exit(0 if ok else 1)
