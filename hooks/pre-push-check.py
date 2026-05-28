"""Pre-push check: estää pushin jos code_review.yml on jo käynnissä."""
import io, json, subprocess, sys, time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

def main():
    r = subprocess.run(
        ["gh", "run", "list", "--limit", "3", "--workflow", "code_review.yml",
         "--branch", "main", "--json", "databaseId,status,createdAt"],
        capture_output=True, text=True, timeout=15
    )
    if r.returncode != 0 or not r.stdout.strip():
        # gh ei saatavilla tai virhe → sallitaan push
        sys.exit(0)

    runs = json.loads(r.stdout)
    in_progress = [run for run in runs if run.get("status") == "in_progress"]

    if not in_progress:
        sys.exit(0)

    run = in_progress[0]
    run_id = run["databaseId"]
    created = run.get("createdAt", "")[:16].replace("T", " ")

    # Blokataan push ja kerrotaan tilanteesta
    result = {
        "continue": False,
        "stopReason": (
            f"GitHub Actions käynnissä (run {run_id}, alkanut {created}). "
            f"Peru: gh run cancel {run_id} — tai odota: gh run watch {run_id} --exit-status"
        )
    }
    print(json.dumps(result))
    sys.exit(0)

main()
