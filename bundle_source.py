"""
Bundle source files into two focused text files for LLM consumption.

Usage:
    python bundle_source.py [commit]

Output:
    leima_bundle.txt  — document analysis app (main.py, UI, stamping logic)
    tread_bundle.txt  — deployment monitoring protocol (TREAD infra, workflows)
"""
import subprocess, sys
from pathlib import Path

ref = sys.argv[1] if len(sys.argv) > 1 else "HEAD"
root = Path(__file__).parent

LEIMA_INTRO = """This bundle describes Leima (leima.ai), a document analysis and blockchain stamping application.
It answers the question: what does this software do, how does it process documents, and what are its data handling guarantees?
The bundle includes the application backend, AI analysis logic, email notary, UI templates, and data policy."""

TREAD_INTRO = """This bundle describes TREAD (Transparent Record of Evaluation, Attestation and Deployment), a protocol for verifying that a hosted application is running the code it claims to run.
It answers the question: how does the deployment monitoring work, what does it check, and how can an independent party verify it?
The bundle includes the monitoring logic, GitHub Actions workflows, the userscript, and the protocol documentation."""

LEIMA_FILES = {
    "README.md",
    "POLICY.example.md",
    "USECASES.md",
    "ZKSE.md",
    "CONTINUOUS_DD.md",
    "INSPECTION.md",
    "WITNESS_APP.md",
    "PROTEUS.md",
    "COMMUNITY.md",
    "requirements.txt",
    "main.py",
    "neutral_witness.py",
    "notary.py",
    "upload_validator.py",
    "monthly_audit.py",
    ".github/workflows/code_review.yml",
}
LEIMA_DIRS = {"templates"}

TREAD_FILES = {
    "TREAD.md",
    "POLICY.example.md",
    "SECURITY_MODEL.md",
    "requirements.txt",
    "tread_check.py",
    "tread_arweave.py",
    "tread.user.js",
    "verify.py",
    "push_status.py",
    "code_review.py",
    ".github/workflows/tread-a.yml",
    ".github/workflows/tread-b.yml",
    ".github/workflows/tread-c.yml",
    ".github/workflows/tread-d.yml",
    ".github/workflows/tread-e.yml",
    ".github/workflows/tread-run.yml",
    ".github/workflows/code_review.yml",
}


def git_ls() -> list[str]:
    r = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", ref],
        capture_output=True, text=True, cwd=root, check=True, encoding="utf-8",
    )
    return r.stdout.splitlines()


def read_blob(path: str) -> str | None:
    r = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        capture_output=True, text=True, cwd=root, encoding="utf-8", errors="replace",
    )
    return r.stdout if r.returncode == 0 else None


def build_bundle(tracked: list[str], include_files: set[str],
                 include_dirs: set[str], intro: str, title: str) -> list[str]:
    selected = [
        p for p in tracked
        if p in include_files or any(p.startswith(d + "/") for d in include_dirs)
    ]
    parts = []
    for path in sorted(selected):
        content = read_blob(path)
        if content is not None:
            parts.append(f"### {path}\n```\n{content}\n```")
    return parts


commit_sha = subprocess.run(
    ["git", "rev-parse", ref],
    capture_output=True, text=True, cwd=root, encoding="utf-8",
).stdout.strip()

tracked = git_ls()

for name, intro, files, dirs, outfile in [
    ("Leima", LEIMA_INTRO, LEIMA_FILES, LEIMA_DIRS, "leima_bundle.txt"),
    ("TREAD", TREAD_INTRO, TREAD_FILES, set(),      "tread_bundle.txt"),
]:
    parts = build_bundle(tracked, files, dirs, intro, name)
    header = f"# {name} bundle\n{intro}\n\nCommit: {commit_sha}\nFiles: {len(parts)}\n\n"
    out = root / outfile
    out.write_text(header + "\n\n".join(parts), encoding="utf-8")
    print(f"{outfile}: {len(parts)} files, {out.stat().st_size // 1024} kt")

print(f"Commit: {commit_sha[:12]}")
