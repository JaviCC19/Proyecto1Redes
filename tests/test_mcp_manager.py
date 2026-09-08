"""
Unit tests for src/host/mcp_manager.py - specifically _start_offers(),
which is what makes functionality #6 (remote server) a pure config
switch instead of a code change: OFFERS_REMOTE_URL unset -> local
stdio subprocess (#5), set -> MCPHttpClient against that URL (#6).

No real subprocess or network call happens here: MCPClient/MCPHttpClient
are monkeypatched with recording fakes so this only tests the manager's
branching logic, not the transports themselves (those already have
their own coverage via smoke_test.py / smoke_test_remote.py, which do
talk to real processes/servers).
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "host"))

import mcp_manager  # noqa: E402


class _FakeClient:
    """Records how it was constructed and that the lifecycle methods
    (start/initialize/list_tools) were called, in order, without doing
    any real I/O."""

    instances: list["_FakeClient"] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls: list[str] = []
        self.tools: list[dict] = []
        _FakeClient.instances.append(self)

    def start(self):
        self.calls.append("start")

    def initialize(self):
        self.calls.append("initialize")

    def list_tools(self):
        self.calls.append("list_tools")
        return self.tools


class TestStartOffers(unittest.TestCase):
    def setUp(self) -> None:
        _FakeClient.instances = []
        self.env_patch = patch.dict(os.environ, {}, clear=False)
        self.env_patch.start()
        os.environ.pop("OFFERS_REMOTE_URL", None)
        os.environ.pop("OFFERS_AUTH_TOKEN", None)

    def tearDown(self) -> None:
        self.env_patch.stop()

    def _manager(self) -> mcp_manager.MCPManager:
        return mcp_manager.MCPManager(logger=object(), workspace_dir="/tmp/ws", git_repo_dir="/tmp/git")

    def test_local_stdio_by_default(self) -> None:
        with patch.object(mcp_manager, "MCPClient", _FakeClient), \
             patch.object(mcp_manager, "MCPHttpClient", _FakeClient):
            mgr = self._manager()
            mgr._start_offers()

        self.assertEqual(len(_FakeClient.instances), 1)
        client = _FakeClient.instances[0]
        self.assertEqual(client.calls, ["start", "initialize", "list_tools"])
        self.assertEqual(client.kwargs["alias"], "offers")
        self.assertIn("command", client.kwargs)  # stdio client takes a subprocess command
        self.assertIs(mgr.clients["offers"], client)

    def test_remote_http_when_env_var_set(self) -> None:
        os.environ["OFFERS_REMOTE_URL"] = "http://example.invalid:8090"
        os.environ["OFFERS_AUTH_TOKEN"] = "secret123"
        with patch.object(mcp_manager, "MCPClient", _FakeClient), \
             patch.object(mcp_manager, "MCPHttpClient", _FakeClient):
            mgr = self._manager()
            mgr._start_offers()

        self.assertEqual(len(_FakeClient.instances), 1)
        client = _FakeClient.instances[0]
        self.assertEqual(client.calls, ["start", "initialize", "list_tools"])
        self.assertEqual(client.kwargs["base_url"], "http://example.invalid:8090")
        self.assertEqual(client.kwargs["auth_token"], "secret123")
        self.assertIs(mgr.clients["offers"], client)


class _RaisingClient:
    def close(self):
        raise RuntimeError("boom")


class _RecordingClient:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class TestCloseAll(unittest.TestCase):
    def test_one_client_raising_does_not_stop_the_others_from_closing(self) -> None:
        mgr = mcp_manager.MCPManager(logger=object(), workspace_dir="/tmp/ws", git_repo_dir="/tmp/git")
        good = _RecordingClient()
        mgr.clients = {"bad": _RaisingClient(), "good": good}

        mgr.close_all()  # must not raise

        self.assertTrue(good.closed)


if __name__ == "__main__":
    unittest.main()
