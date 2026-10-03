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
from .client import session
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

TOOLS = [DEVICE_STATUS_TOOL]


def make_call_tool(adb_factory: Callable[[], Adb] = Adb, config_factory: Callable[[], BridgeConfig] = BridgeConfig):
    def call_tool(name: str, arguments: dict) -> dict:
        try:
            if name == "device_status":
                with session(adb_factory(), config_factory(), arguments.get("serial")) as (device, client):
                    status = client.request("device_status")
                return {"serial": device.serial, **status}
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
