"""
mcp_client.py

A hand-written Model Context Protocol (MCP) client implementing the
stdio transport described in the MCP specification
(https://modelcontextprotocol.io/specification/2025-11-25) directly on
top of JSON-RPC 2.0 (https://www.jsonrpc.org/specification).

IMPORTANT (project requirement): this module does NOT use the official
MCP SDK (`mcp` package on PyPI), FastMCP, or any similar library. Every
piece of the protocol - message framing, the initialize handshake,
request/response correlation by id, and tool invocation - is
implemented by hand using only the Python standard library
(subprocess, json, threading).

Transport used: stdio. Each JSON-RPC message is UTF-8 text encoded as a
single JSON object terminated by "\n" (newline-delimited JSON), written
to the child process' stdin and read from its stdout. This matches the
"stdio transport" section of the MCP spec: one message per line, no
Content-Length framing (that framing belongs to LSP, not MCP).

The client is intentionally synchronous/blocking: the chatbot issues
one MCP request at a time and waits for its matching response, which is
enough for this project (a single user driving a single conversation).
A background thread continuously drains stdout (so notifications sent
by the server without being explicitly awaited are never lost and the
pipe never blocks) and another drains stderr (so server side logging
never fills the OS pipe buffer and deadlocks the child process).
"""

from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
from typing import Any, Optional

from logger import InteractionLogger

MCP_PROTOCOL_VERSION = "2025-11-25"


class MCPError(Exception):
    """Raised when a server returns a JSON-RPC error object."""

    def __init__(self, code: int, message: str, data: Any = None):
        super().__init__(f"MCP error {code}: {message}")
        self.code = code
        self.message = message
        self.data = data


class MCPClient:
    """One MCPClient instance == one JSON-RPC session with one MCP server
    (spawned as a local child process communicating over stdio)."""

    def __init__(self, alias: str, command: list[str], logger: InteractionLogger,
                 client_name: str = "cc3067-custom-host", client_version: str = "0.1.0",
                 env: Optional[dict] = None):
        self.alias = alias
        self.command = command
        self.logger = logger
        self.client_name = client_name
        self.client_version = client_version
        self._env = env

        self._proc: Optional[subprocess.Popen] = None
        self._next_id = 1
        self._id_lock = threading.Lock()
        self._pending: dict[int, "queue.Queue[dict]"] = {}
        self._pending_lock = threading.Lock()
        self._notifications: "queue.Queue[dict]" = queue.Queue()
        self._reader_thread: Optional[threading.Thread] = None
        self._stderr_thread: Optional[threading.Thread] = None
        self._closed = False

        self.server_info: Optional[dict] = None
        self.server_capabilities: Optional[dict] = None
        self.tools: list[dict] = []

    # ------------------------------------------------------------------
    # process / transport management
    # ------------------------------------------------------------------
    def start(self) -> None:
        self._proc = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # line buffered
            env=self._env,
        )
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()
        self._stderr_thread = threading.Thread(target=self._stderr_loop, daemon=True)
        self._stderr_thread.start()

    def _read_loop(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        for raw_line in self._proc.stdout:
            line = raw_line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                # Not a JSON-RPC line (some servers print banners); ignore.
                continue

            if "id" in message and message["id"] is not None:
                direction = "response"
            else:
                direction = "notification"
            self.logger.log(self.alias, direction, message)

            if direction == "response":
                with self._pending_lock:
                    q = self._pending.get(message["id"])
                if q is not None:
                    q.put(message)
            else:
                self._notifications.put(message)
        self._closed = True

    def _stderr_loop(self) -> None:
        assert self._proc is not None and self._proc.stderr is not None
        for raw_line in self._proc.stderr:
            line = raw_line.rstrip()
            if line:
                print(f"[MCP][{self.alias}][stderr] {line}", file=sys.stderr)

    # ------------------------------------------------------------------
    # JSON-RPC primitives (hand-rolled, no SDK)
    # ------------------------------------------------------------------
    def _allocate_id(self) -> int:
        with self._id_lock:
            msg_id = self._next_id
            self._next_id += 1
            return msg_id

    def _send(self, payload: dict) -> None:
        assert self._proc is not None and self._proc.stdin is not None
        line = json.dumps(payload)
        self._proc.stdin.write(line + "\n")
        self._proc.stdin.flush()

    def request(self, method: str, params: Optional[dict] = None, timeout: float = 30.0) -> dict:
        """Send a JSON-RPC request and block until the matching response
        arrives. Returns the 'result' field, raises MCPError on failure."""
        msg_id = self._allocate_id()
        payload = {"jsonrpc": "2.0", "id": msg_id, "method": method}
        if params is not None:
            payload["params"] = params

        response_q: "queue.Queue[dict]" = queue.Queue(maxsize=1)
        with self._pending_lock:
            self._pending[msg_id] = response_q

        self.logger.log(self.alias, "request", payload)
        self._send(payload)

        try:
            response = response_q.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError(f"[{self.alias}] no response for method={method} id={msg_id}")
        finally:
            with self._pending_lock:
                self._pending.pop(msg_id, None)

        if "error" in response:
            err = response["error"]
            raise MCPError(err.get("code", -1), err.get("message", "unknown error"), err.get("data"))
        return response.get("result", {})

    def notify(self, method: str, params: Optional[dict] = None) -> None:
        """Send a JSON-RPC notification (no id, no response expected)."""
        payload = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        self.logger.log(self.alias, "request", payload)
        self._send(payload)

    # ------------------------------------------------------------------
    # MCP lifecycle
    # ------------------------------------------------------------------
    def initialize(self) -> None:
        """Perform the MCP handshake: initialize request followed by the
        'notifications/initialized' notification, as mandated by the
        spec's lifecycle section."""
        result = self.request(
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": self.client_name, "version": self.client_version},
            },
        )
        self.server_info = result.get("serverInfo")
        self.server_capabilities = result.get("capabilities")
        self.notify("notifications/initialized")

    def list_tools(self) -> list[dict]:
        result = self.request("tools/list", {})
        self.tools = result.get("tools", [])
        return self.tools

    def call_tool(self, name: str, arguments: dict) -> dict:
        return self.request("tools/call", {"name": name, "arguments": arguments})

    def close(self) -> None:
        if self._proc and self._proc.poll() is None:
            try:
                if self._proc.stdin:
                    self._proc.stdin.close()
                self._proc.terminate()
                self._proc.wait(timeout=5)
            except Exception:
                self._proc.kill()
