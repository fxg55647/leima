"""Pre-push check: estää pushin jos code_review.yml on jo käynnissä,
tai jos main.py importtaa paikallisen .py-tiedoston joka ei ole git-seurannassa."""
import ast, io, json, os, subprocess, sys, time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def check_missing_local_imports():
    """Löytää main.py:n paikalliset importit (esim. 'import browser_session')
    joiden vastaava .py-tiedosto on levyllä mutta ei HEAD-committissa.
    Estää bugin jossa uusi moduuli otetaan käyttöön mutta unohdetaan 'git add'."""
    try:
        r = subprocess.run(["git", "show", "HEAD:main.py"], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=10)
        if r.returncode != 0:
            return None
        tree = ast.parse(r.stdout)
    except Exception:
        return None

    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                modules.add(node.module.split(".")[0])

    missing = []
    for mod in sorted(modules):
        local_path = f"{mod}.py"
        if not os.path.exists(local_path):
            continue  # ei paikallinen tiedosto (stdlib/kolmannen osapuolen paketti)
        check = subprocess.run(["git", "cat-file", "-e", f"HEAD:{local_path}"], capture_output=True, timeout=10)
        if check.returncode != 0:
            missing.append(local_path)

    return missing or None


def main():
    missing = check_missing_local_imports()
    if missing:
        result = {
            "continue": False,
            "stopReason": (
                "main.py importtaa paikallisia tiedostoja jotka eivät ole git-seurannassa HEAD-committissa: "
                + ", ".join(missing)
                + " — tämä kaataa tuotannon (ModuleNotFoundError). Aja: git add " + " ".join(missing)
                + " ja committoi ennen pushia."
            )
        }
        print(json.dumps(result))
        sys.exit(0)

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
