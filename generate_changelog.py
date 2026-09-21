"""Generate a static changelog page from git log, published to GitHub Pages
alongside the TREAD audit log. Raw commit messages, newest first, grouped by day.
"""
import html
import os
import subprocess
from pathlib import Path

REPO = os.environ.get("GITHUB_REPOSITORY", "fxg55647/leima")
SEP = "\x1f"

log = subprocess.run(
    ["git", "log", "--date=format:%Y-%m-%d",
     f"--pretty=format:%H{SEP}%h{SEP}%ad{SEP}%s"],
    capture_output=True, text=True, check=True,
    encoding="utf-8",
).stdout

groups: dict[str, list[tuple[str, str, str]]] = {}
total = 0
for line in log.splitlines():
    if not line.strip():
        continue
    full_sha, short_sha, date, subject = line.split(SEP, 3)
    groups.setdefault(date, []).append((full_sha, short_sha, subject))
    total += 1

sections = []
for date, commits in groups.items():  # git log is newest-first; dict keeps that order
    items = []
    for full_sha, short_sha, subject in commits:
        url = f"https://github.com/{REPO}/commit/{full_sha}"
        items.append(
            f'<li><code><a href="{url}" target="_blank" rel="noopener noreferrer">'
            f'{short_sha}</a></code> {html.escape(subject)}</li>'
        )
    sections.append(f'<h2>{html.escape(date)}</h2>\n<ul>\n' + "\n".join(items) + "\n</ul>")

page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Leima — changelog</title>
  <style>
    body {{ font-family: "Segoe UI", system-ui, sans-serif; max-width: 960px; margin: 2rem auto; padding: 0 1rem; color: #212529; }}
    h1 {{ font-size: 1.2rem; font-weight: 700; margin-bottom: 0.25rem; }}
    .sub {{ font-size: 0.82rem; color: #6c757d; margin-bottom: 1.5rem; }}
    h2 {{ font-size: 0.85rem; font-weight: 600; color: #6c757d; text-transform: uppercase; letter-spacing: 0.05em; margin: 1.75rem 0 0.5rem; border-bottom: 1px solid #f1f3f5; padding-bottom: 0.25rem; }}
    ul {{ list-style: none; margin: 0; padding: 0; }}
    li {{ font-size: 0.88rem; padding: 0.3rem 0; border-bottom: 1px solid #f8f9fa; }}
    code {{ font-family: "Segoe UI Mono", "Courier New", monospace; font-size: 0.8rem; background: #f1f3f5; padding: 0.05rem 0.35rem; border-radius: 4px; }}
    a {{ color: #0d6efd; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
  <h1>Leima — changelog</h1>
  <p class="sub">Raw commit messages, newest first. Auto-generated on every production deploy. · <a href="audit.html">TREAD audit log</a> · <a href="https://github.com/{REPO}" target="_blank" rel="noopener noreferrer">Repo</a></p>
  {"".join(sections)}
</body>
</html>
"""

Path("pages-output").mkdir(exist_ok=True)
Path("pages-output/changelog.html").write_text(page, encoding="utf-8")
print(f"Generated changelog.html with {total} commits across {len(groups)} days")
