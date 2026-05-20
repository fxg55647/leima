"""
Automated policy compliance audit for Leima.
Reads all Python and JS source files, compares against POLICY.md,
and reports whether the code complies with the stated data policy.
"""
import os, sys
from pathlib import Path
from google import genai
from google.genai import types

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-2.5-flash"

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

Check each of the following, citing specific file and line where relevant:

1. Does any code send document content to a service other than Google Gemini (gemini-2.5-flash-lite)?
2. Does any code write document content or claim text to persistent storage (files, databases, logs)?
3. Does any code add tracking, analytics, cookies, or cross-session identification?
4. Does the AI prompt logic in neutral_witness.py match what POLICY.md says the model is instructed to do?
5. Does the Arweave/Irys upload contain anything beyond hashes and metadata?
6. Are there any external HTTP calls not described in POLICY.md?

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
resp = client.models.generate_content(
    model=MODEL,
    contents=build_prompt(policy, sources),
    config=types.GenerateContentConfig(temperature=0),
)
result = resp.text.strip()
print(result)

compliant = "OVERALL: COMPLIANT" in result
write_summary(result, compliant)
sys.exit(0 if compliant else 1)
