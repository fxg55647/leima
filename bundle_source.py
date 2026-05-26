"""
Bundle source files and documentation into a single text file for Leima upload.

Includes all .py and .js source files plus README.md and POLICY.md so the
AI reviewer has full context about the project's architecture and data policy.

Usage:
    python bundle_source.py [commit]

    commit  optional git ref (default: HEAD)

Output: source_bundle.txt
"""
import subprocess, sys
from pathlib import Path

SKIP_DIRS  = {".venv", "__pycache__", ".git", "node_modules", "hooks", ".claude"}
SOURCE_EXT = {".py", ".js", ".html", ".yml", ".md"}
DOCS       = {"requirements.txt"}

ref = sys.argv[1] if len(sys.argv) > 1 else "HEAD"
root = Path(__file__).parent

# List files tracked in git at the given ref
result = subprocess.run(
    ["git", "ls-tree", "-r", "--name-only", ref],
    capture_output=True, text=True, cwd=root, check=True, encoding="utf-8",
)
all_tracked = result.stdout.splitlines()

docs    = [p for p in all_tracked if Path(p).name in DOCS]
sources = [p for p in all_tracked if Path(p).suffix in SOURCE_EXT
           and not any(part in SKIP_DIRS for part in Path(p).parts)]
tracked = sorted(docs) + sorted(sources)


def read_blob(path: str) -> str | None:
    r = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        capture_output=True, text=True, cwd=root, encoding="utf-8", errors="replace",
    )
    return r.stdout if r.returncode == 0 else None


parts = []
for path in tracked:
    content = read_blob(path)
    if content is not None:
        parts.append(f"### {path}\n```\n{content}\n```")

commit_sha = subprocess.run(
    ["git", "rev-parse", ref],
    capture_output=True, text=True, cwd=root, encoding="utf-8",
).stdout.strip()

header = f"# Leima source bundle\nCommit: {commit_sha}\nFiles: {len(parts)}\n\n"
output = root / "source_bundle.txt"
output.write_text(header + "\n\n".join(parts), encoding="utf-8")
print(f"Wrote {len(parts)} files -> {output}")
print(f"Commit: {commit_sha[:12]}")
