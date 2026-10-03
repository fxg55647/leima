"""Local MCP server over stdio for Claude Desktop and other local MCP clients.

Reuses the JSON-RPC handling of the public /mcp endpoint (mcp_server.handle_message) with the
bridge's own tool list. stdout carries only protocol messages; diagnostics go to stderr.
"""
import json
import sys
from typing import Callable, TextIO

import mcp_server
from mcp_server import ToolError

from .adb import Adb
from .archive import Archive
from .client import list_packages, session, sync
from .config import BridgeConfig
from .errors import BridgeError

SERVER_INFO = {"name": "leima-bridge", "title": "Leima Research Appliance (USB phone)", "version": "0.1.0"}

INSTRUCTIONS = (
    "Controls a physical Android phone running the Leima app over USB. The phone is the browser "
    "and the local evidence store. Call device_status first to see which capabilities the phone "
    "currently offers; only the listed capabilities are implemented. Pairing is done by the person "
    "on the PC and phone (python -m bridge pair), never by the agent."
)

DEVICE_STATUS_TOOL = {
    "name": "device_status",
    "title": "Phone status",
    "description": (
        "Connects to the USB phone and returns the protocol version, app and WebView versions, "
        "device model and the list of implemented capabilities. Errors carry a code such as "
        "NO_DEVICE, DEVICE_UNAUTHORIZED, APP_NOT_LISTENING or NOT_PAIRED with a fix for the person."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "serial": {"type": "string", "description": "ADB serial of the phone; only needed when several are connected."},
        },
        "additionalProperties": False,
    },
    "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
}

_SERIAL = {"serial": {"type": "string", "description": "ADB serial of the phone; only needed when several are connected."}}

PACKAGES_LIST_TOOL = {
    "name": "packages_list",
    "title": "List packages on the phone",
    "description": (
        "Lists finished evidence packages waiting on the phone: package_id, kind (photo, screenshot, "
        "meeting), size, sha256 of the ZIP and creation time. Returns no package content."
    ),
    "inputSchema": {"type": "object", "properties": _SERIAL, "additionalProperties": False},
    "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
}

PACKAGES_SYNC_TOOL = {
    "name": "packages_sync",
    "title": "Move packages to the PC archive",
    "description": (
        "Copies every finished package from the phone to the PC archive, verifies the ZIP hash and "
        "its manifest, stores it unchanged and only then deletes it from the phone. Packages that fail "
        "verification stay on the phone and are reported as failed. Returns one result per package "
        "with its archive path; no package content."
    ),
    "inputSchema": {"type": "object", "properties": _SERIAL, "additionalProperties": False},
    "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
}

PACKAGE_VERIFY_TOOL = {
    "name": "package_verify",
    "title": "Re-verify an archived package",
    "description": (
        "Re-checks a package in the PC archive: its bytes still match the indexed sha256 and its "
        "manifest hashes (and meeting signature) are valid. Proves integrity only, not origin, time "
        "or truth of the content."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {"sha256": {"type": "string", "description": "Full sha256 of the ZIP or a unique prefix (6+ hex characters)."}},
        "required": ["sha256"],
        "additionalProperties": False,
    },
    "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
}

TOOLS = [DEVICE_STATUS_TOOL, PACKAGES_LIST_TOOL, PACKAGES_SYNC_TOOL, PACKAGE_VERIFY_TOOL]


def make_call_tool(adb_factory: Callable[[], Adb] = Adb, config_factory: Callable[[], BridgeConfig] = BridgeConfig,
                   archive_factory: Callable[[], Archive] = Archive):
    def call_tool(name: str, arguments: dict) -> dict:
        try:
            if name == "device_status":
                with session(adb_factory(), config_factory(), arguments.get("serial")) as (device, client):
                    status = client.request("device_status")
                return {"serial": device.serial, **status}
            if name == "packages_list":
                with session(adb_factory(), config_factory(), arguments.get("serial")) as (device, client):
                    return {"serial": device.serial, "packages": list_packages(client)}
            if name == "packages_sync":
                archive = archive_factory()
                with session(adb_factory(), config_factory(), arguments.get("serial")) as (device, client):
                    results = sync(client, device, archive)
                return {"serial": device.serial, "archive": str(archive.root), "results": results}
            if name == "package_verify":
                sha = arguments.get("sha256")
                if not isinstance(sha, str):
                    raise ToolError("sha256 is required")
                return archive_factory().verify_entry(sha)
        except BridgeError as e:
            raise ToolError(str(e)) from e
        raise ToolError(f"Unknown tool: {name}")
    return call_tool


def serve(stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout, call_tool=None) -> None:
    call_tool = call_tool or make_call_tool()
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        else:
            response = mcp_server.handle_message(
                message, call_tool, tools=TOOLS, server_info=SERVER_INFO, instructions=INSTRUCTIONS,
            )
        if response is not None:
            stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            stdout.flush()
