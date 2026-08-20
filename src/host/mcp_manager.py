"""
mcp_manager.py

Owns the set of MCP servers the chatbot (host) is connected to:

  * "fs"     -> official Filesystem MCP server (Anthropic reference
                implementation, @modelcontextprotocol/server-filesystem),
                spawned with `npx`.
  * "git"    -> official Git MCP server (Anthropic reference
                implementation, `mcp-server-git` on PyPI).
  * "offers" -> our own custom local MCP server (see
                src/servers/offers_server/server.py), the "caso de uso
                de industria" required by functionality #5.

Every server is driven through the same hand-written MCPClient
(mcp_client.py) - the manual JSON-RPC implementation is identical
regardless of whether the server is an official reference
implementation or our own.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Optional

from logger import InteractionLogger
from mcp_client import MCPClient

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(THIS_DIR)
OFFERS_SERVER_PATH = os.path.join(SRC_DIR, "servers", "offers_server", "server.py")


class MCPManager:
    def __init__(self, logger: InteractionLogger, workspace_dir: str, git_repo_dir: str):
        self.logger = logger
        self.workspace_dir = workspace_dir
        self.git_repo_dir = git_repo_dir
        self.clients: dict[str, MCPClient] = {}

    def _npx_available(self) -> bool:
        return shutil.which("npx") is not None

    @staticmethod
    def _ensure_git_repo(repo_dir: str) -> None:
        """The official Git MCP server (mcp-server-git) refuses to start
        at all when --repository points at a path that is not already a
        valid git repository (it validates eagerly in `serve()` and
        returns before ever opening the stdio transport, so a malformed
        path there just looks like a silent timeout to the client).
        Also, this reference server does not expose a `git_init` tool.
        So the very first time we point it at a workspace, we bootstrap
        an empty repo with a single direct `git init` call - every
        subsequent operation in the demo (creating the README via the
        Filesystem MCP server, then `git_add` / `git_commit` /
        `git_status` via this Git MCP server) goes through MCP."""
        if os.path.isdir(os.path.join(repo_dir, ".git")):
            return
        subprocess.run(["git", "init", repo_dir], check=True, capture_output=True)

    def start_all(self, include_fs: bool = True, include_git: bool = True,
                  include_offers: bool = True) -> None:
        if include_offers:
            self._start("offers", [sys.executable, OFFERS_SERVER_PATH])

        if include_fs:
            if self._npx_available():
                os.makedirs(self.workspace_dir, exist_ok=True)
                self._start("fs", ["npx", "-y", "@modelcontextprotocol/server-filesystem",
                                    self.workspace_dir])
            else:
                print("[warn] npx not found; skipping Filesystem MCP server", file=sys.stderr)

        if include_git:
            os.makedirs(self.git_repo_dir, exist_ok=True)
            self._ensure_git_repo(self.git_repo_dir)
            mcp_git_bin = shutil.which("mcp-server-git")
            if mcp_git_bin:
                self._start("git", [mcp_git_bin, "--repository", self.git_repo_dir])
            else:
                self._start("git", [sys.executable, "-m", "mcp_server_git",
                                     "--repository", self.git_repo_dir])

    def _start(self, alias: str, command: list[str]) -> None:
        client = MCPClient(alias=alias, command=command, logger=self.logger)
        client.start()
        client.initialize()
        client.list_tools()
        self.clients[alias] = client

    def all_tools_for_llm(self) -> list[dict]:
        """Flattens every connected server's tools into Anthropic's tool
        schema, namespacing names as '<alias>__<tool>' so tool calls can
        be routed back to the right MCP server."""
        tools = []
        for alias, client in self.clients.items():
            for tool in client.tools:
                tools.append({
                    "name": f"{alias}__{tool['name']}",
                    "description": f"[{alias}] {tool.get('description', '')}",
                    "input_schema": tool.get("inputSchema", {"type": "object", "properties": {}}),
                })
        return tools

    def call_tool(self, namespaced_name: str, arguments: dict) -> dict:
        alias, _, tool_name = namespaced_name.partition("__")
        client = self.clients.get(alias)
        if client is None:
            raise ValueError(f"Unknown MCP server alias: {alias}")
        return client.call_tool(tool_name, arguments)

    def close_all(self) -> None:
        for client in self.clients.values():
            client.close()
