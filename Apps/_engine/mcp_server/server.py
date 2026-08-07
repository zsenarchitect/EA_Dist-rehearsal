"""Minimal MCP server using JSON-RPC 2.0 over stdio.

Stdlib-only, Python 3.9 compatible. No external dependencies.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Callable, Dict, List, Optional


class McpServer:
    """Lightweight MCP (Model Context Protocol) server.

    Reads JSON-RPC 2.0 messages from stdin (one JSON object per line),
    dispatches to registered tool handlers, and writes responses to stdout.
    Diagnostic messages go to stderr so they never pollute the protocol stream.
    """

    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description
        self._tools: Dict[str, _ToolEntry] = {}

    # ------------------------------------------------------------------
    # Tool registration
    # ------------------------------------------------------------------

    def tool(
        self,
        name: str,
        description: str,
        handler: Callable[..., Any],
        parameters: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Register a tool.

        Parameters
        ----------
        name:
            Unique tool name exposed to the MCP client.
        description:
            Human-readable description shown in ``tools/list``.
        handler:
            Callable invoked when the client calls ``tools/call`` with
            this tool name.  Receives keyword arguments matching
            *parameters*.
        parameters:
            JSON Schema describing the tool's input.  If ``None``, the
            tool accepts no arguments.
        """
        self._tools[name] = _ToolEntry(
            name=name,
            description=description,
            handler=handler,
            parameters=parameters or {"type": "object", "properties": {}},
        )

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Block forever, processing JSON-RPC messages from stdin."""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                self._send_error(None, -32700, "Parse error")
                continue
            self._handle_message(msg)

    # ------------------------------------------------------------------
    # Protocol dispatch
    # ------------------------------------------------------------------

    def _handle_message(self, msg: Dict[str, Any]) -> None:
        method = msg.get("method", "")
        msg_id = msg.get("id")

        # Notifications (no id) — just acknowledge silently
        if msg_id is None:
            return

        if method == "initialize":
            self._handle_initialize(msg_id, msg.get("params", {}))
        elif method == "notifications/initialized":
            # Client ack — nothing to do
            pass
        elif method == "tools/list":
            self._handle_tools_list(msg_id)
        elif method == "tools/call":
            self._handle_tools_call(msg_id, msg.get("params", {}))
        elif method == "ping":
            self._send_result(msg_id, {})
        else:
            self._send_error(msg_id, -32601, "Method not found: {}".format(method))

    def _handle_initialize(self, msg_id: Any, params: Dict[str, Any]) -> None:
        self._send_result(msg_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {"listChanged": False},
            },
            "serverInfo": {
                "name": self.name,
                "version": "1.0.0",
            },
        })

    def _handle_tools_list(self, msg_id: Any) -> None:
        tools_list: List[Dict[str, Any]] = []
        for entry in self._tools.values():
            tools_list.append({
                "name": entry.name,
                "description": entry.description,
                "inputSchema": entry.parameters,
            })
        self._send_result(msg_id, {"tools": tools_list})

    def _handle_tools_call(self, msg_id: Any, params: Dict[str, Any]) -> None:
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        entry = self._tools.get(tool_name)
        if entry is None:
            self._send_error(msg_id, -32602, "Unknown tool: {}".format(tool_name))
            return

        try:
            result = entry.handler(**arguments)
            # MCP tools/call result must be a content array
            if isinstance(result, bytes):
                import base64
                content = [{"type": "image", "data": base64.b64encode(result).decode("ascii"), "mimeType": "image/png"}]
            elif isinstance(result, str):
                content = [{"type": "text", "text": result}]
            else:
                content = [{"type": "text", "text": json.dumps(result, default=str)}]
            self._send_result(msg_id, {"content": content})
        except Exception as exc:
            self._send_result(msg_id, {
                "content": [{"type": "text", "text": "Error: {}".format(exc)}],
                "isError": True,
            })

    # ------------------------------------------------------------------
    # Wire helpers
    # ------------------------------------------------------------------

    def _send_result(self, msg_id: Any, result: Any) -> None:
        self._write({"jsonrpc": "2.0", "id": msg_id, "result": result})

    def _send_error(self, msg_id: Any, code: int, message: str) -> None:
        self._write({
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": code, "message": message},
        })

    @staticmethod
    def _write(obj: Dict[str, Any]) -> None:
        line = json.dumps(obj, separators=(",", ":"))
        sys.stdout.write(line + "\n")
        sys.stdout.flush()


class _ToolEntry:
    """Internal container for a registered tool."""

    __slots__ = ("name", "description", "handler", "parameters")

    def __init__(
        self,
        name: str,
        description: str,
        handler: Callable[..., Any],
        parameters: Dict[str, Any],
    ) -> None:
        self.name = name
        self.description = description
        self.handler = handler
        self.parameters = parameters
