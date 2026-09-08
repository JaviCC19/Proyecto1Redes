#!/usr/bin/env python3
"""
http_server.py

HTTP transport for the offers MCP server (functionality #6: the same
server as functionality #5, now reachable remotely). This is a
simplified implementation of the MCP "Streamable HTTP" transport
(https://modelcontextprotocol.io/specification/2025-11-25/basic/
transports#streamable-http): the client POSTs a single JSON-RPC
message to `/mcp` and receives a single JSON-RPC message back in the
HTTP response body. We do not implement the SSE upgrade path (server-
initiated streaming/multiple messages per request), since this
project's client only ever sends one request and waits for one
response at a time - the same request/response shape already used by
the stdio transport in `server.py`.

Built entirely with the Python standard library (`http.server`,
`json`) - no web framework (Flask/FastAPI) and no MCP SDK, consistent
with the "implement the protocol by hand" requirement that also
applies to the stdio transport.
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from server import handle_message

# Optional shared-secret auth: when MCP_AUTH_TOKEN is set, every request
# to /mcp must carry `Authorization: Bearer <token>`. Left unset for
# local testing; should be set when deployed publicly (Cloud Run, etc.)
AUTH_TOKEN = os.environ.get("MCP_AUTH_TOKEN", "").strip()


class MCPHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:  # quieter, structured-ish access log
        print(f"[offers-http] {self.address_string()} {fmt % args}", file=sys.stderr)

    def _write_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        if not AUTH_TOKEN:
            return True
        return self.headers.get("Authorization") == f"Bearer {AUTH_TOKEN}"

    def do_GET(self) -> None:
        if self.path == "/health":
            self._write_json(200, {"status": "ok"})
            return
        self._write_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/mcp":
            self._write_json(404, {"error": "not found"})
            return
        if not self._authorized():
            self._write_json(401, {"error": "unauthorized"})
            return

        length = int(self.headers.get("Content-Length", "0") or "0")
        raw_body = self.rfile.read(length) if length else b""
        try:
            message = json.loads(raw_body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._write_json(400, {
                "jsonrpc": "2.0", "id": None,
                "error": {"code": -32700, "message": "Parse error"},
            })
            return

        response = handle_message(message)
        if response is None:
            # Notification: MCP Streamable HTTP replies 202 with no body.
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        self._write_json(200, response)


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    host = os.environ.get("HOST", "0.0.0.0")
    server = ThreadingHTTPServer((host, port), MCPHandler)
    auth_note = "auth: required" if AUTH_TOKEN else "auth: disabled (set MCP_AUTH_TOKEN to enable)"
    print(f"[offers-http] listening on {host}:{port} ({auth_note})", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
