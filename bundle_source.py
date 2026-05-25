"""
Bundle all Python and JS source files into a single text file for Leima upload.

Usage:
    python bundle_source.py [commit]

    commit  optional git ref (default: HEAD)

Output: source_bundle.txt
"""
import subprocess, sys
from pathlib import Path

SKIP_DIRS  = {".venv", "__pycache__", ".git", "node_modules", ".github", "hooks"}
SOURCE_EXT = {".py", ".js"}

ref = sys.argv[1] if len(sys.argv) > 1 else "HEAD"
root = Path(__file__).parent

# List files tracked in git at the given ref
result = subprocess.run(
    ["git", "ls-tree", "-r", "--name-only", ref],
    capture_output=True, text=True, cwd=root, check=True, encoding="utf-8",
)
tracked = [p for p in result.stdout.splitlines() if Path(p).suffix in SOURCE_EXT]
tracked = [p for p in tracked if not any(part in SKIP_DIRS for part in Path(p).parts)]
tracked.sort()

parts = []
for path in tracked:
    blob = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        capture_output=True, text=True, cwd=root, encoding="utf-8", errors="replace",
    )
    if blob.returncode == 0:
        parts.append(f"### {path}\n```\n{blob.stdout}\n```")

commit_sha = subprocess.run(
    ["git", "rev-parse", ref],
    capture_output=True, text=True, cwd=root, encoding="utf-8",
).stdout.strip()

header = f"# Leima source bundle\nCommit: {commit_sha}\nFiles: {len(parts)}\n\n"
output = root / "source_bundle.txt"
output.write_text(header + "\n\n".join(parts), encoding="utf-8")
print(f"Wrote {len(parts)} files -> {output}")
print(f"Commit: {commit_sha[:12]}")
