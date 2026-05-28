"""Post-push hook: seuraa deployta gh run watch:lla.
Exit code 2 herättää agentin tuloksen kanssa (asyncRewake)."""
import io, json, subprocess, sys, time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

TIMEOUT = 600  # 10 minuuttia


def find_run_id(max_wait=60):
    """Odottaa uutta in_progress tai queued code_review-ajoa, palauttaa run ID."""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        r = subprocess.run(
            ["gh", "run", "list", "--limit", "1", "--workflow", "code_review.yml",
             "--branch", "main", "--json", "databaseId,status"],
            capture_output=True, text=True, timeout=15
        )
        if r.returncode == 0 and r.stdout.strip():
            runs = json.loads(r.stdout)
            if runs and runs[0]["status"] in ("in_progress", "queued", "waiting"):
                return runs[0]["databaseId"]
        time.sleep(5)
    return None


def main():
    time.sleep(4)  # anna GitHub:lle hetki rekisteröidä uusi ajo

    run_id = find_run_id()
    if not run_id:
        print("DEPLOY: GitHub Actions -ajoa ei löydy 60s sisällä — tarkista manuaalisesti.")
        sys.exit(2)

    print(f"DEPLOY: seurataan run {run_id}...", flush=True)

    try:
        r = subprocess.run(
            ["gh", "run", "watch", str(run_id), "--exit-status"],
            capture_output=True, text=True, timeout=TIMEOUT
        )
        if r.returncode == 0:
            print(f"DEPLOY OK — run {run_id} valmistui. Koodi on live.")
        else:
            print(f"DEPLOY EPÄONNISTUI — run {run_id}.")
            print(f"Lisätiedot: gh run view {run_id}")
    except subprocess.TimeoutExpired:
        print(f"DEPLOY: aikakatkaisu {TIMEOUT}s — run {run_id} ei valmistunut.")
        print(f"Tarkista: gh run watch {run_id} --exit-status")

    sys.exit(2)  # herättää agentin


main()
