"""
Integration tests for src/servers/offers_server/http_server.py - the
functionality #6 (remote) transport. Unlike test_offers_server.py
(which tests handle_message() directly, no I/O), these spin up a real
ThreadingHTTPServer on an OS-assigned free port and talk to it over
actual HTTP, so they also exercise request parsing, status codes and
the MCP_AUTH_TOKEN check - the same code path used against the real
VPS deployment, just on localhost.
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "servers", "offers_server"))


def _post(url: str, payload: dict, token: str | None = None) -> tuple[int, dict | None]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read()
            return resp.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as exc:
        with exc:
            body = exc.read()
            return exc.code, (json.loads(body) if body else None)


class _ServerHarness:
    """Starts http_server on 127.0.0.1:<free port> in a background
    thread for the duration of a test, honoring MCP_AUTH_TOKEN set in
    the environment *before* the module is (re)imported, since the
    module reads it once at import time."""

    def __init__(self, auth_token: str | None = None):
        self.auth_token = auth_token

    def __enter__(self):
        if self.auth_token:
            os.environ["MCP_AUTH_TOKEN"] = self.auth_token
        else:
            os.environ.pop("MCP_AUTH_TOKEN", None)

        global http_server
        import http_server as _http_server_module  # noqa: PLC0415
        importlib.reload(_http_server_module)  # pick up MCP_AUTH_TOKEN change
        http_server = _http_server_module

        from http.server import ThreadingHTTPServer  # noqa: PLC0415
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), http_server.MCPHandler)
        self.port = self.server.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *exc_info):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        os.environ.pop("MCP_AUTH_TOKEN", None)


class TestHttpServerNoAuth(unittest.TestCase):
    def test_health_endpoint(self) -> None:
        with _ServerHarness() as h:
            with urllib.request.urlopen(f"{h.base_url}/health", timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                self.assertEqual(json.loads(resp.read()), {"status": "ok"})

    def test_tools_call_round_trip(self) -> None:
        with _ServerHarness() as h:
            status, body = _post(f"{h.base_url}/mcp", {
                "jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {},
            })
            self.assertEqual(status, 200)
            self.assertIn("list_offers", [t["name"] for t in body["result"]["tools"]])

    def test_notification_gets_202_with_empty_body(self) -> None:
        with _ServerHarness() as h:
            status, body = _post(f"{h.base_url}/mcp", {
                "jsonrpc": "2.0", "method": "notifications/initialized",
            })
            self.assertEqual(status, 202)
            self.assertIsNone(body)

    def test_unknown_path_is_404(self) -> None:
        with _ServerHarness() as h:
            status, _ = _post(f"{h.base_url}/nope", {})
            self.assertEqual(status, 404)

    def test_malformed_json_is_parse_error(self) -> None:
        with _ServerHarness() as h:
            req = urllib.request.Request(f"{h.base_url}/mcp", data=b"not json",
                                          headers={"Content-Type": "application/json"}, method="POST")
            try:
                urllib.request.urlopen(req, timeout=5)
                self.fail("expected HTTPError")
            except urllib.error.HTTPError as exc:
                with exc:
                    self.assertEqual(exc.code, 400)
                    self.assertEqual(json.loads(exc.read())["error"]["code"], -32700)


class TestHttpServerWithAuth(unittest.TestCase):
    def test_missing_token_is_rejected(self) -> None:
        with _ServerHarness(auth_token="s3cr3t") as h:
            status, _ = _post(f"{h.base_url}/mcp", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
            self.assertEqual(status, 401)

    def test_wrong_token_is_rejected(self) -> None:
        with _ServerHarness(auth_token="s3cr3t") as h:
            status, _ = _post(f"{h.base_url}/mcp", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                               token="wrong")
            self.assertEqual(status, 401)

    def test_correct_token_is_accepted(self) -> None:
        with _ServerHarness(auth_token="s3cr3t") as h:
            status, body = _post(f"{h.base_url}/mcp", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                                  token="s3cr3t")
            self.assertEqual(status, 200)
            self.assertIn("tools", body["result"])

    def test_health_endpoint_is_never_gated_by_auth(self) -> None:
        with _ServerHarness(auth_token="s3cr3t") as h:
            with urllib.request.urlopen(f"{h.base_url}/health", timeout=5) as resp:
                self.assertEqual(resp.status, 200)


if __name__ == "__main__":
    unittest.main()
