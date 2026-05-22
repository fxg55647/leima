"""
Render B — independent PoDe monitor.
Runs pode_check.py + push_status.py every 60 seconds.
Deploy as a Render Background Worker: start command = python monitor.py
Required env vars: same as pode-run.yml (RENDER_API_KEY, RENDER_SERVICE_ID,
                   GITHUB_TOKEN, optionally IRYS_*)
"""
import os, subprocess, sys, time

INTERVAL = int(os.environ.get("PODE_INTERVAL", "60"))
print(f"Monitor starting — interval {INTERVAL}s", flush=True)

while True:
    try:
        subprocess.run([sys.executable, "pode_check.py"], check=False)
        subprocess.run([sys.executable, "push_status.py"], check=False)
    except Exception as e:
        print(f"Error: {e}", flush=True)

    print(f"Sleeping {INTERVAL}s…", flush=True)
    time.sleep(INTERVAL)
