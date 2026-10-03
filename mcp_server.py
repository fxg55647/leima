"""Minimal stateless MCP server (Streamable HTTP transport, JSON responses only).

Hand-rolled instead of using the `mcp` SDK: the SDK's streamable-HTTP app needs an ASGI
lifespan-managed session manager, which doesn't fit Vercel's serverless runtime. Leima's
tools are plain request/response calls, so the stateless subset of the protocol is enough:
every POST carries one JSON-RPC message and gets one JSON response, no sessions, no SSE.

Protocol logic only — main.py owns the HTTP route, auth and the tool implementations.
"""
import json
from typing import Callable

SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
SERVER_INFO = {"name": "leima", "title": "Leima citation stamping", "version": "0.1.0"}

INSTRUCTIONS = (
    "Leima independently checks whether a source supports a claim and stamps the result "
    "on Arweave. Call stamp_citation once per claim/source pair you want to cite. Prefer "
    "source_url: Leima then fetches the source itself and the result is marked "
    "fetched_by_leima. source_text alone is marked agent_supplied, meaning Leima cannot "
    "attest that the text really comes from the cited source. The 'verdict' block is an AI "
    "assessment; the 'evidence' block (hashes + Arweave transaction) is the cryptographic "
    "commitment. Report both to the user and never present the verdict as proof."
)

STAMP_CITATION_TOOL = {
    "name": "stamp_citation",
    "title": "Stamp a citation",
    "description": (
        "Check whether a source supports a claim and permanently stamp the result. "
        "Returns the claim, source provenance, an AI verdict, hash evidence with an "
        "Arweave transaction, and a ready-to-use citation string. Takes 20-90 seconds."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "claim": {
                "type": "string",
                "description": "The statement you want to back up with the source, in one or two sentences.",
            },
            "source_url": {
                "type": "string",
                "description": "URL of the web page or PDF that supports the claim. Preferred: Leima fetches it itself.",
            },
            "source_text": {
                "type": "string",
                "description": (
                    "The exact passage you are citing. With source_url, Leima checks the passage "
                    "against the fetched source. Without source_url, this text is the whole source."
                ),
            },
            "source_title": {
                "type": "string",
                "description": "Optional human-readable title of the source, used in the citation string.",
            },
        },
        "required": ["claim"],
        "additionalProperties": False,
    },
    "annotations": {
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
}

TOOLS = [STAMP_CITATION_TOOL]


class ToolError(Exception):
    """Raised by a tool implementation for errors the calling model should see and can fix."""


def _error(msg_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _result(msg_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _negotiate_version(requested) -> str:
    return requested if requested in SUPPORTED_PROTOCOL_VERSIONS else SUPPORTED_PROTOCOL_VERSIONS[0]


def handle_message(message, call_tool: Callable[[str, dict], dict], *, tools: list[dict] = TOOLS,
                   server_info: dict = SERVER_INFO, instructions: str = INSTRUCTIONS) -> dict | None:
    """Handle one JSON-RPC message. Returns the response object, or None for notifications
    and client responses (the HTTP layer answers those with 202 Accepted).

    The keyword arguments let another server (the local USB bridge, bridge/mcp_stdio.py)
    reuse this protocol handling with its own tools."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _error(None, -32600, "Invalid Request")

    method = message.get("method")
    msg_id = message.get("id")
    if method is None or "id" not in message:
        return None  # notification (e.g. notifications/initialized) or a client response

    params = message.get("params") or {}
    if not isinstance(params, dict):
        return _error(msg_id, -32602, "params must be an object")

    if method == "initialize":
        return _result(msg_id, {
            "protocolVersion": _negotiate_version(params.get("protocolVersion")),
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": server_info,
            "instructions": instructions,
        })
    if method == "ping":
        return _result(msg_id, {})
    if method == "tools/list":
        return _result(msg_id, {"tools": tools})
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name not in {t["name"] for t in tools}:
            return _error(msg_id, -32602, f"Unknown tool: {name}")
        if not isinstance(arguments, dict):
            return _error(msg_id, -32602, "arguments must be an object")
        try:
            structured = call_tool(name, arguments)
        except ToolError as e:
            return _result(msg_id, {"content": [{"type": "text", "text": str(e)}], "isError": True})
        return _result(msg_id, {
            "content": [{"type": "text", "text": json.dumps(structured, ensure_ascii=False, indent=2)}],
            "structuredContent": structured,
            "isError": False,
        })
    return _error(msg_id, -32601, f"Method not found: {method}")
