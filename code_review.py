"""
Automated policy compliance audit for Leima.
Reads all Python and JS source files, compares against POLICY.md,
and reports whether the code complies with the stated data policy.
"""
import os, sys, time
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

Your task: verify that the source code below complies with the data policy in POLICY.md.

Architecture note: the codebase has two distinct parts:
- User-data path: main.py, neutral_witness.py, notary.py — these handle user documents and emails
- Infrastructure path: pode_check.py, pode_arweave.py, monthly_audit.py — these are deployment integrity monitors that never touch user data

Check each of the following, citing specific file and line where relevant:

1. Does any code in the user-data path send document content to a service other than Google Gemini (gemini-3.1-flash-lite) or SMTP (for the email notary flow described in POLICY.md)?
2. Does any code write document content or claim text to persistent storage (files, databases, logs)?
3. Does any code add tracking, analytics, cookies, or cross-session identification?
4. Does the AI prompt logic in neutral_witness.py match what POLICY.md says the model is instructed to do?
5. Does the Arweave/Irys upload in the user-data path contain anything beyond hashes and metadata?
6. Are there any external HTTP calls in the user-data path not described in POLICY.md?

Note: infrastructure scripts (pode_check.py, pode_arweave.py, monthly_audit.py) make HTTP calls to Render API, GitHub API, and Arweave — these are deployment monitoring calls, not user-data calls, and are not in scope for POLICY.md compliance.

For each check write one line: PASS or FAIL — and a brief explanation.

End your response with exactly one line:
OVERALL: COMPLIANT
or
OVERALL: VIOLATION — <one sentence summary>

---

## POLICY.md

{policy}

---

## Source files

{source_block}
"""


def write_summary(text: str, compliant: bool):
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_file:
        return
    status = "✅ COMPLIANT" if compliant else "❌ VIOLATION DETECTED"
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write(f"# PoDe Code Review — {status}\n\n```\n{text}\n```\n")


root = Path(__file__).parent
policy = (root / "POLICY.md").read_text(encoding="utf-8")
sources = collect_sources(root)

client = genai.Client(api_key=GEMINI_API_KEY)
prompt = build_prompt(policy, sources)
result = ""
for attempt in range(3):
    try:
        resp = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0),
        )
        result = (resp.text or "").strip()
        break
    except Exception as e:
        print(f"Attempt {attempt + 1} failed: {e}", flush=True)
        if attempt < 2:
            time.sleep(15 * (attempt + 1))
        else:
            print(f"::error title=Code review error::API call failed after 3 attempts: {e}", flush=True)
            sys.exit(1)

if not result:
    print("::error title=Code review error::Gemini returned an empty response", flush=True)
    sys.exit(1)

print(result)

compliant = "OVERALL: COMPLIANT" in result
write_summary(result, compliant)

if not compliant:
    violation_line = next((l for l in result.splitlines() if l.startswith("OVERALL:")), "OVERALL: VIOLATION")
    print(f"::error title=Policy violation::{violation_line}", flush=True)

sys.exit(0 if compliant else 1)
