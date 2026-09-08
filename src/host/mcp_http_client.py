"""
mcp_http_client.py

Hand-written MCP client for the remote (HTTP) transport - functionality
#6. This is the network counterpart of `MCPClient` in `mcp_client.py`
(which speaks the stdio transport to a local child process): same
public surface (`start`, `initialize`, `list_tools`, `call_tool`,
`close`), same hand-rolled JSON-RPC 2.0 message shapes and id
correlation, same shared `InteractionLogger`, but talking to a remote
`offers_server/http_server.py` process (e.g. deployed on Cloud Run)
over plain HTTPS POST requests instead of a local pipe.

Only `requests` (already used by `llm_client.py` for the Anthropic API,
see the project's "no SDK" note) is used to perform the HTTP calls; no
MCP SDK is involved anywhere in this file - every JSON-RPC message is
built and parsed by hand, exactly like the stdio client.
"""

from __future__ import annotations

import threading
from typing import Any, Optional

import requests

from logger import InteractionLogger
from mcp_client import MCPError

MCP_PROTOCOL_VERSION = "2025-11-25"


class MCPHttpClient:
    """One MCPHttpClient instance == one JSON-RPC session with one MCP
    server reachable over HTTP (functionality #6: the remote offers
    server, deployed with the Dockerfile in src/servers/offers_server/).
    """

    def __init__(self, alias: str, base_url: str, logger: InteractionLogger,
                 client_name: str = "cc3067-custom-host", client_version: str = "0.1.0",
                 auth_token: Optional[str] = None, timeout: float = 30.0):
        self.alias = alias
        self.base_url = base_url.rstrip("/")
        self.logger = logger
        self.client_name = client_name
        self.client_version = client_version
        self.auth_token = auth_token
        self.timeout = timeout

        self._next_id = 1
        self._id_lock = threading.Lock()
        self._session = requests.Session()

        self.server_info: Optional[dict] = None
        self.server_capabilities: Optional[dict] = None
        self.tools: list[dict] = []

    # ------------------------------------------------------------------
    # process / transport management (no subprocess here: the server
    # already runs remotely, so "start" is a no-op kept for interface
    # symmetry with MCPClient so MCPManager can treat both the same way)
    # ------------------------------------------------------------------
    def start(self) -> None:
        return None

    # ------------------------------------------------------------------
    # JSON-RPC primitives (hand-rolled, no SDK)
    # ------------------------------------------------------------------
    def _allocate_id(self) -> int:
        with self._id_lock:
            msg_id = self._next_id
            self._next_id += 1
            return msg_id

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers

    def request(self, method: str, params: Optional[dict] = None, timeout: Optional[float] = None) -> dict:
        """Send a JSON-RPC request over HTTPS POST and block for the
        matching response, which the simplified Streamable HTTP
        transport returns synchronously as the HTTP response body."""
        msg_id = self._allocate_id()
        payload = {"jsonrpc": "2.0", "id": msg_id, "method": method}
        if params is not None:
            payload["params"] = params

        self.logger.log(self.alias, "request", payload)
        try:
            resp = self._session.post(
                f"{self.base_url}/mcp", json=payload, headers=self._headers(),
                timeout=timeout or self.timeout,
            )
        except requests.RequestException as exc:
            raise MCPError(-32000, f"HTTP transport error talking to '{self.alias}': {exc}")

        try:
            response = resp.json()
        except ValueError:
            raise MCPError(resp.status_code, f"Non-JSON response from '{self.alias}': {resp.text[:200]}")

        self.logger.log(self.alias, "response", response)

        if "error" in response:
            err = response["error"]
            raise MCPError(err.get("code", -1), err.get("message", "unknown error"), err.get("data"))
        return response.get("result", {})

    def notify(self, method: str, params: Optional[dict] = None) -> None:
        """Send a JSON-RPC notification (no id, no result expected). Per
        the Streamable HTTP transport this gets a bare 202 Accepted."""
        payload = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        self.logger.log(self.alias, "request", payload)
        try:
            self._session.post(f"{self.base_url}/mcp", json=payload, headers=self._headers(),
                                timeout=self.timeout)
        except requests.RequestException as exc:
            raise MCPError(-32000, f"HTTP transport error talking to '{self.alias}': {exc}")

    # ------------------------------------------------------------------
    # MCP lifecycle (identical shape to MCPClient.initialize)
    # ------------------------------------------------------------------
    def initialize(self) -> None:
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
        self._session.close()
