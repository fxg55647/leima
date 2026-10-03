"""Local MCP server over stdio for Claude Desktop and other local MCP clients.

Reuses the JSON-RPC handling of the public /mcp endpoint (mcp_server.handle_message) with the
bridge's own tool list. stdout carries only protocol messages; diagnostics go to stderr.
"""
import json
import sys
from typing import Callable, TextIO

import mcp_server
from mcp_server import ToolError, ToolResult

from .adb import Adb
from .archive import Archive
from .client import list_packages, run_command, session, sync
from .config import BridgeConfig
from .errors import BridgeError

SERVER_INFO = {"name": "leima-bridge", "title": "Leima Research Appliance (USB phone)", "version": "0.1.0"}

INSTRUCTIONS = (
    "Controls a physical Android phone running the Leima app over USB. The phone is the browser "
    "and the local evidence store. Call device_status first to see which capabilities the phone "
    "currently offers; only the listed capabilities are implemented. Pairing is done by the person "
    "on the PC and phone (python -m bridge pair), never by the agent. Browser workflow: browser_navigate, "
    "browser_observe, then act with browser_click/browser_type using the ids of the LATEST observation; "
    "every action ends that observation, so observe again before the next action. Password and "
    "one-time-code fields are for the person to fill in on the phone: when login, MFA, a CAPTCHA or an "
    "approval needs the person (human_action_hints in an observation are heuristic clues), call "
    "browser_request_human, tell the person what to do, then browser_resume with wait_s to continue "
    "after they press Jatka on the phone. The person can take control or stop the agent at any time; "
    "HUMAN_ACTION_PENDING, SESSION_CANCELLED and HANDOFF_EXPIRED mean the person is in charge. "
    "browser_capture stores the page "
    "as an evidence package on the phone; packages_sync moves it to the PC archive. A capture is the "
    "phone's record of what it rendered, not the server's original response and not proof of truth."
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
        "its manifest, stores it unchanged and then DELETES it from the phone unless keep_on_phone is "
        "true. Packages that fail verification stay on the phone and are reported as failed. Returns "
        "one result per package with its archive path; no package content."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            **_SERIAL,
            "keep_on_phone": {
                "type": "boolean",
                "default": False,
                "description": "true copies to the archive but leaves every package on the phone.",
            },
        },
        "additionalProperties": False,
    },
    "annotations": {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": False},
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

_ELEMENT_REF = {
    "session_id": {"type": "string", "description": "session_id from the latest browser_observe."},
    "observation_id": {"type": "string", "description": "observation_id from the latest browser_observe."},
    "element_id": {"type": "string", "description": "element_id from that observation's elements list."},
}


def _browser_tool(name, title, description, properties=None, required=(), read_only=False, destructive=False):
    return {
        "name": name,
        "title": title,
        "description": description,
        "inputSchema": {"type": "object", "properties": {**(properties or {}), **_SERIAL},
                        "required": list(required), "additionalProperties": False},
        "annotations": {"readOnlyHint": read_only, "destructiveHint": destructive, "idempotentHint": read_only,
                        "openWorldHint": True},
    }


BROWSER_TOOLS = [
    _browser_tool("browser_navigate", "Open a URL on the phone",
                  "Opens an https:// URL in the phone's Leima browser and waits for it to load (up to 30 s). "
                  "Returns url, title and loading. The Selain tab must be shown on the phone.",
                  {"url": {"type": "string", "description": "https:// URL without credentials."}}, ["url"]),
    _browser_tool("browser_observe", "Read the current page",
                  "Returns the page's visible text, its visible interactive elements (element_id, role, name, "
                  "enabled, value except for secret fields) and limitations such as unread cross-origin frames. "
                  "The page content is returned to this MCP client and so to its model provider.",
                  read_only=True),
    _browser_tool("browser_click", "Click an element",
                  "Clicks an element of the latest observation (DOM click). Fails with STALE_OBSERVATION if the "
                  "page changed or the observation was used; it never clicks some other element.",
                  _ELEMENT_REF, list(_ELEMENT_REF), destructive=True),
    _browser_tool("browser_type", "Type into a text field",
                  "Sets the text of a text field from the latest observation. Refuses password and one-time-code "
                  "fields (SENSITIVE_FIELD): ask the person to fill those in on the phone.",
                  {**_ELEMENT_REF,
                   "text": {"type": "string", "description": "Plain text, at most 2000 characters."},
                   "replace": {"type": "boolean", "default": True, "description": "false appends to the existing text."}},
                  [*_ELEMENT_REF, "text"], destructive=True),
    _browser_tool("browser_back", "Go back", "Goes back one page in the phone browser history."),
    _browser_tool("browser_screenshot", "Screenshot of the phone browser",
                  "Returns a PNG of the visible browser area with password and one-time-code fields painted black. "
                  "Refused (SCREENSHOT_BLOCKED) while a cross-origin frame is visible, because its fields cannot be masked.",
                  read_only=True),
    _browser_tool("browser_capture", "Capture the page as evidence",
                  "Stores the current page on the phone as an evidence package (DOM serialization, visible text, "
                  "element list, masked screenshot, metadata, SHA-256 manifest). Returns package_id, sha256 and "
                  "capture_status (partial lists what is missing). Returns no page content."),
    _browser_tool("browser_request_human", "Hand control to the person",
                  "Asks the person to act on the phone (log in, MFA, CAPTCHA, approve something). Until they press "
                  "Jatka on the phone every other browser tool fails with HUMAN_ACTION_PENDING. Returns handoff_id. "
                  "The task text is shown on the phone as a quote from the agent.",
                  {"reason": {"type": "string", "enum": ["LOGIN", "MFA", "CAPTCHA", "CONFIRMATION", "OTHER"]},
                   "task": {"type": "string", "description": "What the person should do, at most 300 characters."},
                   "timeout_s": {"type": "integer", "minimum": 30, "maximum": 1800, "default": 600,
                                 "description": "After this the handoff expires and agent control stops until the person allows it again."}},
                  ["reason"]),
    _browser_tool("browser_resume", "Continue after the person is done",
                  "Takes control back after the person pressed Jatka on the phone, and returns a fresh observation. "
                  "With wait_s it waits up to that many seconds for Jatka; otherwise HUMAN_NOT_DONE.",
                  {"handoff_id": {"type": "string"},
                   "wait_s": {"type": "integer", "minimum": 0, "maximum": 120, "default": 0}},
                  ["handoff_id"]),
    _browser_tool("browser_end_session", "End the browser session",
                  "Ends the agent's browser session on the phone: a new session_id, no open handoff, all "
                  "observations invalid. The page stays open on the phone."),
]

TOOLS = [DEVICE_STATUS_TOOL, PACKAGES_LIST_TOOL, PACKAGES_SYNC_TOOL, PACKAGE_VERIFY_TOOL, *BROWSER_TOOLS]
_BROWSER_TOOL_NAMES = {t["name"] for t in BROWSER_TOOLS}


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
                    results = sync(client, device, archive, delete=not arguments.get("keep_on_phone", False))
                return {"serial": device.serial, "archive": str(archive.root), "results": results}
            if name in _BROWSER_TOOL_NAMES:
                serial = arguments.get("serial")
                params = {k: v for k, v in arguments.items() if k != "serial"}
                result = run_command(lambda: session(adb_factory(), config_factory(), serial),
                                     "browser." + name.removeprefix("browser_"), params)
                if name == "browser_screenshot":
                    image = result.pop("png_base64")
                    return ToolResult(result, [{"type": "image", "data": image, "mimeType": "image/png"}])
                return result
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
