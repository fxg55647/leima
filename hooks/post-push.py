"""Post-push hook -- seuraa POIDE-statuslogia koodiarvion ja deployn varmistamiseksi."""
import io, json, sys, time
import urllib.request as req
import subprocess

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

LOG_URL = "https://fxg55647.github.io/leima/status-log.jsonl"

POLL_INT       = 30   # sekuntia POIDE-pollausvälillä
REVIEW_TIMEOUT = 600  # 10 min code reviewlle (POIDE-cron voi lagata)
DEPLOY_TIMEOUT = 600  # 10 min deploylle


def pushed_commit() -> str:
    r = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip()


def sha_match(a: str, b: str) -> bool:
    """Tosi jos SHA-merkkijonot jakavat saman prefiksin (min 7 merkkia)."""
    n = min(len(a), len(b))
    return n >= 7 and a[:n] == b[:n]


def fetch_poide() -> dict | None:
    """Hakee POIDE-statuslogin viimeisimman rivin. Nayttaa virheen jos haku epäonnistuu."""
    try:
        with req.urlopen(LOG_URL, timeout=10) as r:
            lines = r.read().decode().strip().splitlines()
        for line in reversed(lines):
            line = line.strip()
            if line:
                return json.loads(line)
    except Exception as e:
        print(f"[deploy] Varoitus: POIDE-lokin haku epaonnistui: {e}", flush=True)
    return None


def wait_for_review(commit: str) -> bool | None:
    """Odottaa POIDE-lokin review_ok=True kommitille.

    Palauttaa:
      True  -- koodiarvio hyvaksytty
      False -- koodiarvio epaonnistui (2 POIDE-paivitysta perakkaain samalle commitille)
      None  -- timeout
    """
    print(f"[deploy] Odotetaan code review commit {commit[:7]}...", flush=True)
    print(f"[deploy] (Pollaan {LOG_URL} joka {POLL_INT}s)", flush=True)
    deadline = time.time() + REVIEW_TIMEOUT
    last_ts = None
    false_new_entries = 0

    while time.time() < deadline:
        entry = fetch_poide()
        if entry:
            entry_commit = (entry.get("commit") or "").strip()
            ts = entry.get("ts") or entry.get("timestamp", "")

            if sha_match(commit, entry_commit):
                review_ok = entry.get("review_ok")
                run_url = entry.get("actions_run_url", "")

                if review_ok is True:
                    return True

                if ts != last_ts:
                    last_ts = ts
                    if review_ok is False:
                        false_new_entries += 1
                        if false_new_entries >= 2:
                            print(f"[deploy] FAIL Code review epaonnistui.", flush=True)
                            if run_url:
                                print(f"[deploy] Ajo: {run_url}", flush=True)
                            return False
                        print(
                            f"[deploy] Code review False "
                            f"(POIDE-paivitys {false_new_entries}/2, ajo saattaa olla kesken)...",
                            flush=True,
                        )
                    else:
                        print(f"[deploy] Code review: {review_ok}...", flush=True)
                # else: sama POIDE-entry uudelleen, ei tulosteta

            else:
                if ts != last_ts:
                    last_ts = ts
                    print(
                        f"[deploy] POIDE: commit {entry_commit or '?'},"
                        f" odotetaan {commit[:7]}...",
                        flush=True,
                    )

        time.sleep(POLL_INT)

    return None


def wait_for_deploy(commit: str) -> bool:
    """Odottaa POIDE-lokin deployment_ok=True. Palauttaa True jos onnistuu."""
    print(f"[deploy] Odotetaan deployta commit {commit[:7]}...", flush=True)
    deadline = time.time() + DEPLOY_TIMEOUT
    last_ts = None

    while time.time() < deadline:
        entry = fetch_poide()
        if entry:
            entry_commit = (entry.get("commit") or "").strip()
            ts = entry.get("ts") or entry.get("timestamp", "")

            if sha_match(commit, entry_commit):
                if entry.get("deployment_ok"):
                    return True
                if ts != last_ts:
                    last_ts = ts
                    deploying = entry.get("deploying", False)
                    status = "kaynnissa" if deploying else "odottaa"
                    print(f"[deploy] Deploy: {status}...", flush=True)

            else:
                if ts != last_ts:
                    last_ts = ts
                    print(
                        f"[deploy] POIDE: commit {entry_commit or '?'},"
                        f" odotetaan {commit[:7]}...",
                        flush=True,
                    )

        time.sleep(POLL_INT)

    return False


def main() -> int:
    commit = pushed_commit()
    print(f"[deploy] Commit: {commit[:7]}", flush=True)

    result = wait_for_review(commit)

    if result is None:
        print(
            f"[deploy] !! Code review ei valmistunut {REVIEW_TIMEOUT}s sisalla"
            f" -- tarkista GitHub Actions.",
            flush=True,
        )
        return 0
    if result is False:
        print(f"[deploy] Deploy peruuntui.", flush=True)
        return 0

    print("[deploy] OK Code review hyvaksytty.", flush=True)

    if wait_for_deploy(commit):
        print(f"[deploy] OK Deploy valmis -- {commit[:7]} on live.", flush=True)
    else:
        print(
            f"[deploy] !! Deploy ei valmistunut {DEPLOY_TIMEOUT}s sisalla"
            f" -- tarkista Render.",
            flush=True,
        )

    return 0


sys.exit(main())
