"""POIDE pre-push check -- called by hooks/pre-push shell wrapper."""
import json, os, subprocess, sys, time
from pathlib import Path
import urllib.request as req

LOG_URL  = "https://fxg55647.github.io/leima/status-log.jsonl"
POLL_MAX = 180   # sekuntia
POLL_INT = 15    # sekuntia


def fetch_latest() -> dict | None:
    try:
        with req.urlopen(LOG_URL, timeout=10) as r:
            lines = r.read().decode().strip().splitlines()
        for line in reversed(lines):
            line = line.strip()
            if line:
                return json.loads(line)
    except Exception:
        return None
    return None


def run_code_review() -> bool:
    """Ajaa code_review.py paikallisesti. Palauttaa True jos OK tai avain puuttuu."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("[POIDE] GEMINI_API_KEY ei asetettu -- code review skipataan.", flush=True)
        return True
    print("[POIDE] Ajetaan code review paikallisesti...", flush=True)
    root = Path(__file__).parent.parent
    result = subprocess.run(
        [sys.executable, str(root / "code_review.py")],
        cwd=root,
        env={**os.environ, "GEMINI_API_KEY": api_key},
    )
    if result.returncode != 0:
        print(
            "\n[POIDE] !! PUSH ESTETTY -- code review epaonnistui!\n"
            "  Korjaa policy-rikkomus tai suspicious dependency ennen pushia.\n"
            "  Hatatilanteessa: git push --no-verify\n",
            flush=True,
        )
        return False
    print("[POIDE] Code review OK.", flush=True)
    return True


def main() -> int:
    # --- Code review (jos GEMINI_API_KEY asetettu) ---
    if not run_code_review():
        return 1

    # --- POIDE-statustarkistus ---
    print("[POIDE] Tarkistetaan deployment-status ennen pushausta...", flush=True)

    start = time.time()
    while True:
        entry = fetch_latest()

        if entry is None:
            print("[POIDE] Statusta ei saatu -- sallitaan push (ei esteta verkon ongelmasta).", flush=True)

            return 0

        deploying         = entry.get("deploying", False)
        deployment_ok     = entry.get("deployment_ok", True)
        deploying_commit_ok = entry.get("deploying_commit_ok", False)
        review_conclusion = entry.get("review_conclusion", "")

        # Mismatch is only dangerous if unexplained -- review running/failed means
        # old safe code is still live and the new commit is gated.
        deployment_safe = (
            deployment_ok
            or deploying_commit_ok
            or review_conclusion in ("in_progress", "failure", "")
        )

        if deploying and not deploying_commit_ok:
            # Wrong commit deploying -- wait and recheck
            elapsed = time.time() - start
            if elapsed >= POLL_MAX:
                print(f"[POIDE] Epa-review deploy on ollut kesken jo {POLL_MAX}s -- sallitaan push.", flush=True)
                return 0
            remaining = int(POLL_MAX - elapsed)
            print(f"[POIDE] Deploy kesken (tarkistetaan commit) -- odotetaan {POLL_INT}s... (max {remaining}s jaljella)", flush=True)
            time.sleep(POLL_INT)
            continue

        if not deployment_safe:
            commit = entry.get("commit", "?")[:7]
            ts     = entry.get("ts", "?")
            print(
                f"\n[POIDE] !! PUSH ESTETTY -- selittamaton commit mismatch!\n"
                f"  Aika   : {ts}\n"
                f"  Commit : {commit}\n"
                f"\n"
                f"  Odota kunnes POIDE-tarkistus menee vihreaksi, sitten pushaa uudelleen.\n"
                f"  Hatatilanteessa: git push --no-verify\n",
                flush=True,
            )
            return 1

        print(f"[POIDE] OK -- commit {entry.get('commit','?')[:7]} -- push sallitaan.", flush=True)
        return 0


sys.exit(main())
