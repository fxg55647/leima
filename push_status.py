"""Push status files to gh-pages as a single commit via GitHub Trees API."""
import base64, os, sys
from pathlib import Path
import requests

TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO  = os.environ.get("GITHUB_REPOSITORY", "fxg55647/leima")
BRANCH = "gh-pages"

if not TOKEN:
    print("GITHUB_TOKEN not set — skipping", file=sys.stderr)
    sys.exit(1)

HDR = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
BASE = f"https://api.github.com/repos/{REPO}"


def api(method, path, **kwargs):
    r = requests.request(method, f"{BASE}{path}", headers=HDR, timeout=10, **kwargs)
    r.raise_for_status()
    return r.json()


def push_all(files: list[tuple[str, Path]]) -> bool:
    existing = [(name, p) for name, p in files if p.exists()]
    if not existing:
        print("No files to push", file=sys.stderr)
        return True

    ref_data = api("GET", f"/git/ref/heads/{BRANCH}")
    base_sha = ref_data["object"]["sha"]
    base_tree = api("GET", f"/git/commits/{base_sha}")["tree"]["sha"]

    tree = []
    for name, path in existing:
        content = base64.b64encode(path.read_bytes()).decode()
        blob = api("POST", "/git/blobs", json={"content": content, "encoding": "base64"})
        tree.append({"path": name, "mode": "100644", "type": "blob", "sha": blob["sha"]})

    new_tree = api("POST", "/git/trees", json={"base_tree": base_tree, "tree": tree})
    new_commit = api("POST", "/git/commits", json={
        "message": "chore: update deployment status",
        "tree": new_tree["sha"],
        "parents": [base_sha],
    })
    api("PATCH", f"/git/refs/heads/{BRANCH}", json={"sha": new_commit["sha"]})

    names = ", ".join(name for name, _ in existing)
    print(f"Pushed {names} → {BRANCH} ({new_commit['sha'][:7]})")
    return True


FILES = [
    ("status.json",      Path("pages-output/status.json")),
    ("status-log.jsonl", Path("pages-output/status-log.jsonl")),
    ("audit.html",       Path("audit.html")),
]

ok = push_all(FILES)
sys.exit(0 if ok else 1)

