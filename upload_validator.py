"""
Upload validator.html to Arweave permanently.
Run once per version. The resulting tx_id goes into build_manifest() in main.py.

Usage:
    python upload_validator.py
"""
import os
from dotenv import load_dotenv
from irys_sdk import Builder
from irys_sdk.bundle.tags import from_dict as tags_from_dict

load_dotenv()

IRYS_PRIVATE_KEY = os.getenv("IRYS_PRIVATE_KEY")
IRYS_NETWORK = os.getenv("IRYS_NETWORK", "mainnet")
IRYS_RPC_URL = os.getenv("IRYS_RPC_URL")
GATEWAY = "https://devnet.irys.xyz" if IRYS_NETWORK == "devnet" else "https://gateway.irys.xyz"

with open("validator.html", "rb") as f:
    data = f.read()

builder = Builder("ethereum").wallet(IRYS_PRIVATE_KEY).network(IRYS_NETWORK)
if IRYS_RPC_URL:
    builder = builder.rpc_url(IRYS_RPC_URL)
uploader = builder.build()

tags = tags_from_dict({
    "Content-Type": "text/html",
    "App-Name": "Leima",
    "Leima-Type": "validator",
    "Leima-Validator-Version": "1",
})

result = uploader.upload(bytearray(data), tags)
tx_id = result["id"]

print(f"Uploaded: {GATEWAY}/{tx_id}")
print(f"\nAdd this to build_manifest() in main.py:")
print(f'    "validator": "{GATEWAY}/{tx_id}",')
