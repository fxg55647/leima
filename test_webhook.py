"""Debug-työkalu webhook-putken testaukseen.

Käyttö:
  python test_webhook.py              # lähettää fake code_review_failed
  python test_webhook.py success      # lähettää fake success
  python test_webhook.py raw "viesti" # vapaa viesti
"""
import hashlib, hmac, json, os, subprocess, sys
from pathlib import Path


def load_secret() -> str:
    env = Path(".env")
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("CLAUDE_WEBHOOK_SECRET="):
                return line.split("=", 1)[1].strip()
    return os.environ.get("CLAUDE_WEBHOOK_SECRET", "")


def get_hookdeck_url():
    env = Path(".env")
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("CLAUDE_WEBHOOK_URL="):
                return line.split("=", 1)[1].strip()
    return "https://hkdk.events/34q8u1lhk1bfxk"


def sign(body: str, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()


def send(payload: dict, url: str):
    secret = load_secret()
    body = json.dumps(payload)
    sig = sign(body, secret) if secret else ""
    headers = ["-H", "Content-Type: application/json"]
    if sig:
        headers += ["-H", f"X-Webhook-Signature: {sig}"]
    r = subprocess.run(
        ["curl", "-s", "-X", "POST", url, *headers, "-d", body],
        capture_output=True, text=True, timeout=10
    )
    return r.stdout


def fake_sha():
    r = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else "deadbeef00000000"


def main():
    url = get_hookdeck_url()
    sha = fake_sha()
    mode = sys.argv[1] if len(sys.argv) > 1 else "fail"

    if mode == "success":
        payload = {
            "event": "code_review_done",
            "conclusion": "success",
            "run_id": "TEST",
            "sha": sha,
            "branch": "staging",
            "message": f"[TESTI] code_review.yml onnistui — SHA {sha[:7]}"
        }
    elif mode == "raw":
        msg = sys.argv[2] if len(sys.argv) > 2 else "testi"
        payload = {"event": "test", "message": msg}
    else:
        payload = {
            "event": "code_review_failed",
            "run_id": "TEST",
            "sha": sha,
            "branch": "staging",
            "message": f"[TESTI] code_review.yml feilasi — SHA {sha[:7]} — gh run view TEST --log-failed"
        }

    print(f"Lahetetaan: {url}")
    print(f"Payload: {json.dumps(payload, ensure_ascii=False)}")
    resp = send(payload, url)
    print(f"Vastaus: {resp}")

    parsed = json.loads(resp) if resp else {}
    if parsed.get("status") == "SUCCESS":
        print("OK - Hookdeck vastaanotti. Jos Claude ei saa ilmoitusta, ongelma on tunnelissa tai sessiossa.")
    else:
        print("VIRHE - Hookdeck ei vastannut odotetulla tavalla.")


main()
