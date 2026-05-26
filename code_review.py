"""
Automated policy compliance audit for Leima.
Reads all Python and JS source files, compares against POLICY.example.md,
and reports whether the code complies with the stated data policy.
Also checks for newly added dependencies that could hide malicious behaviour.
"""
import os, subprocess, sys, time
from pathlib import Path
from google import genai
from google.genai import types

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-3.5-flash"

SKIP_DIRS = {".venv", "__pycache__", ".git", "node_modules", ".github"}
SOURCE_EXTENSIONS = {".py", ".js"}


def collect_sources(root: Path) -> dict[str, str]:
    files = {}
    for path in sorted(root.rglob("*")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix in SOURCE_EXTENSIONS and path.is_file():
            try:
                files[str(path.relative_to(root))] = path.read_text(encoding="utf-8")
            except Exception:
                pass
    return files


def build_prompt(policy: str, sources: dict[str, str]) -> str:
    source_block = "\n\n".join(
        f"### {name}\n```\n{content}\n```"
        for name, content in sources.items()
    )
    return f"""You are a security auditor for Leima, an open source document analysis application.

Your task: verify that the source code below complies with the data policy in POLICY.example.md.

Architecture note: the codebase has three distinct parts:
- User-data path: main.py, neutral_witness.py, notary.py — these handle user documents and emails
- Infrastructure path: poide_check.py, poide_arweave.py, monthly_audit.py — these are deployment integrity monitors that never touch user data
- Developer tools: hooks/pre-push.py — a local git pre-push hook that fetches POIDE status from gh-pages before allowing a push; runs only on the developer's machine, never on the server

Check each of the following, citing specific file and line where relevant:

1. Does any code in the user-data path send document content to a service other than Google Gemini (gemini-3.1-flash-lite) or SMTP (for the email notary flow described in POLICY.example.md)?
2. Does any code write document content or claim text to persistent storage (files, databases, logs)?
3. Does any code add tracking, analytics, cookies, or cross-session identification?
4. Does the AI prompt logic in neutral_witness.py match what POLICY.example.md says the model is instructed to do?
5. Does the Arweave/Irys upload in the user-data path contain anything beyond hashes and metadata?
6. Are there any external HTTP calls in the user-data path not described in POLICY.example.md?

Note: infrastructure scripts (poide_check.py, poide_arweave.py, monthly_audit.py) make HTTP calls to Render API, GitHub API, and Arweave — these are deployment monitoring calls, not user-data calls, and are not in scope for POLICY.example.md compliance. hooks/pre-push.py makes one HTTP call to the gh-pages status log and is a developer tool, not server code.

For each check write one line: PASS or FAIL — and a brief explanation.

End your response with exactly one line:
OVERALL: COMPLIANT
or
OVERALL: VIOLATION — <one sentence summary>

---

## POLICY.example.md

{policy}

---

## Source files

{source_block}
"""


def get_new_packages(root: Path) -> list[str]:
    """Return package names added to requirements.txt in the latest commit."""
    try:
        prev = subprocess.run(
            ["git", "show", "HEAD~1:requirements.txt"],
            capture_output=True, text=True, cwd=root,
        )
        curr = (root / "requirements.txt").read_text(encoding="utf-8")
        if prev.returncode != 0:
            # First commit or no previous version — treat all as new
            prev_lines: set[str] = set()
        else:
            prev_lines = {l.strip().lower() for l in prev.stdout.splitlines() if l.strip() and not l.startswith("#")}
        curr_lines = {l.strip() for l in curr.splitlines() if l.strip() and not l.startswith("#")}
        new = [l for l in curr_lines if l.split("==")[0].split(">=")[0].split("~=")[0].strip().lower() not in
               {p.split("==")[0].split(">=")[0].split("~=")[0].strip().lower() for p in prev_lines}]
        return sorted(new)
    except Exception:
        return []


def build_deps_prompt(new_packages: list[str]) -> str:
    pkg_list = "\n".join(f"- {p}" for p in new_packages)
    return f"""You are a security auditor for Leima, a Python web application that analyses documents using Google Gemini and stores results on Arweave.

The following packages were newly added to requirements.txt in the latest commit:

{pkg_list}

For each package assess:
1. Is it a well-known, widely-used package in the Python ecosystem?
2. Is it plausible that this project (document analysis web service) legitimately needs it?
3. Could it be used to exfiltrate data, execute remote code, or perform actions invisible to source code review — even if the source code itself looks clean?

For each package write one line: SAFE or SUSPICIOUS — and a brief explanation.

End your response with exactly one line:
DEPS: SAFE
or
DEPS: SUSPICIOUS — <one sentence summary of the concern>
"""


def write_summary(text: str, compliant: bool):
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_file:
        return
    status = "✅ COMPLIANT" if compliant else "❌ VIOLATION DETECTED"
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write(f"# POIDE Code Review — {status}\n\n```\n{text}\n```\n")


def call_ai(client, prompt: str, label: str) -> str:
    for attempt in range(3):
        try:
            resp = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0),
            )
            return (resp.text or "").strip()
        except Exception as e:
            print(f"{label} attempt {attempt + 1} failed: {e}", flush=True)
            if attempt < 2:
                time.sleep(15 * (attempt + 1))
            else:
                print(f"::error title=Code review error::{label} API call failed: {e}", flush=True)
                sys.exit(1)
    return ""


if not GEMINI_API_KEY:
    print("::error title=Code review error::GEMINI_API_KEY is not set", flush=True)
    sys.exit(1)

root = Path(__file__).parent
try:
    policy = (root / "POLICY.example.md").read_text(encoding="utf-8")
except FileNotFoundError:
    print("::error title=Code review error::POLICY.example.md not found", flush=True)
    sys.exit(1)

sources = collect_sources(root)
client = genai.Client(api_key=GEMINI_API_KEY)

# --- Policy compliance check ---
result = call_ai(client, build_prompt(policy, sources), "Policy check")
if not result:
    print("::error title=Code review error::Gemini returned an empty response", flush=True)
    sys.exit(1)

print(result)
_last_line = next((l.strip() for l in reversed(result.splitlines()) if l.strip()), "")
compliant = _last_line == "OVERALL: COMPLIANT"

# --- New dependency check ---
new_packages = get_new_packages(root)
deps_safe = True
if new_packages:
    print(f"\n--- Dependency review: {len(new_packages)} new package(s) ---", flush=True)
    for p in new_packages:
        print(f"  + {p}", flush=True)
    deps_result = call_ai(client, build_deps_prompt(new_packages), "Deps check")
    if not deps_result:
        print("::warning title=Deps check::No response from Gemini — skipping", flush=True)
    else:
        print(deps_result, flush=True)
        deps_safe = "DEPS: SAFE" in deps_result
        if not deps_safe:
            susp_line = next((l for l in deps_result.splitlines() if l.startswith("DEPS:")), "DEPS: SUSPICIOUS")
            print(f"::error title=Suspicious dependency::{susp_line}", flush=True)

overall_ok = compliant and deps_safe
write_summary(result + ("\n\n" + deps_result if new_packages and deps_result else ""), overall_ok)

if not compliant:
    violation_line = next((l for l in result.splitlines() if l.startswith("OVERALL:")), "OVERALL: VIOLATION")
    print(f"::error title=Policy violation::{violation_line}", flush=True)

sys.exit(0 if overall_ok else 1)
