"""POIDE pre-push check -- called by hooks/pre-push shell wrapper."""
import json, sys, time
from pathlib import Path
import urllib.request as req

LOG_URL      = "https://fxg55647.github.io/leima/status-log.jsonl"
POLL_MAX     = 180   # sekuntia
POLL_INT     = 15    # sekuntia
MIN_INTERVAL = 240   # sekuntia viimeisesta pushista (Render deploy ~2-5 min)

# Tallennetaan viimeisen pushin aika .git-hakemistoon
_GIT_DIR = Path(__file__).parent.parent / ".git"
_STAMP   = _GIT_DIR / "LAST_PUSH"


def read_last_push() -> float:
    try:
        return float(_STAMP.read_text().strip())
    except Exception:
        return 0.0


def write_last_push():
    try:
        _STAMP.write_text(str(time.time()))
    except Exception:
        pass


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


def main() -> int:
    # --- Cooldown-tarkistus ---
    last = read_last_push()
    if last:
        elapsed = time.time() - last
        if elapsed < MIN_INTERVAL:
            wait = int(MIN_INTERVAL - elapsed)
            print(
                f"\n[POIDE] !! PUSH ESTETTY -- edellisesta pushista vain {int(elapsed)}s.\n"
                f"  Render deploy kestaa ~4 min. Odota {wait}s ennen seuraavaa pushia.\n"
                f"  Hatatilanteessa: git push --no-verify\n",
                flush=True,
            )
            return 1

    # --- POIDE-statustarkistus ---
    print("[POIDE] Tarkistetaan deployment-status ennen pushausta...", flush=True)

    start = time.time()
    while True:
        entry = fetch_latest()

        if entry is None:
            print("[POIDE] Statusta ei saatu -- sallitaan push (ei esteta verkon ongelmasta).", flush=True)
            write_last_push()
            return 0

        deploying     = entry.get("deploying", False)
        deployment_ok = entry.get("deployment_ok", True)

        if deploying:
            elapsed = time.time() - start
            if elapsed >= POLL_MAX:
                print(f"[POIDE] Deploy on ollut kesken jo {POLL_MAX}s -- sallitaan push.", flush=True)
                write_last_push()
                return 0
            remaining = int(POLL_MAX - elapsed)
            print(f"[POIDE] Deploy kesken -- odotetaan {POLL_INT}s... (max {remaining}s jaljella)", flush=True)
            time.sleep(POLL_INT)
            continue

        if deployment_ok is False:
            commit = entry.get("commit", "?")[:7]
            ts     = entry.get("ts", "?")
            print(
                f"\n[POIDE] !! PUSH ESTETTY -- commit mismatch havaittu!\n"
                f"  Aika   : {ts}\n"
                f"  Commit : {commit}\n"
                f"\n"
                f"  Odota kunnes POIDE-tarkistus menee vihreaksi, sitten pushaa uudelleen.\n"
                f"  Hatatilanteessa: git push --no-verify\n",
                flush=True,
            )
            return 1

        print(f"[POIDE] OK -- commit {entry.get('commit','?')[:7]} -- push sallitaan.", flush=True)
        write_last_push()
        return 0


sys.exit(main())
