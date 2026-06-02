"""HMAC-SHA256 -verifikaatio proxy: Hookdeck :8787 → (tarkistus) → Claude :8788

Käynnistys: python webhook_proxy.py
Hookdeck komento: hookdeck listen 8787 github-actions-ci --output compact
"""
import hashlib, hmac, os
from pathlib import Path
import httpx
from fastapi import FastAPI, Request, Response
import uvicorn

CLAUDE_PORT = 8788
PROXY_PORT = 8787

app = FastAPI()


def load_secret() -> str:
    env = Path(".env")
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("CLAUDE_WEBHOOK_SECRET="):
                return line.split("=", 1)[1].strip()
    return os.environ.get("CLAUDE_WEBHOOK_SECRET", "")


def verify_signature(secret: str, body: bytes, sig_header: str) -> bool:
    if not sig_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig_header)


@app.post("/{path:path}")
async def proxy(request: Request, path: str):
    body = await request.body()
    secret = load_secret()

    if not secret:
        return Response("CLAUDE_WEBHOOK_SECRET puuttuu .env:stä", status_code=500)

    sig = request.headers.get("x-webhook-signature", "")
    if not verify_signature(secret, body, sig):
        print(f"[proxy] HYLÄTTY — virheellinen allekirjoitus (sig={sig[:20]}...)")
        return Response("Invalid signature", status_code=403)

    print(f"[proxy] OK — välitetään Claudelle")
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"http://localhost:{CLAUDE_PORT}/{path}",
            content=body,
            headers={"Content-Type": request.headers.get("content-type", "application/json")},
            timeout=10,
        )
    return Response(r.content, status_code=r.status_code)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PROXY_PORT, log_level="warning")
