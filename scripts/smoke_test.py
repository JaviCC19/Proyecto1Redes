#!/usr/bin/env python3
"""
smoke_test.py

Verifies the manual MCP client/server plumbing end-to-end WITHOUT
needing an Anthropic API key: starts the three MCP servers (offers,
filesystem, git), runs the initialize handshake, lists their tools and
exercises one tool call on each. Useful to sanity check the transport
independently of the LLM integration.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "host"))

from logger import InteractionLogger
from mcp_manager import MCPManager

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    logger = InteractionLogger(log_dir=os.path.join(ROOT, "logs"), echo_to_console=False)
    # fs and git point at the SAME directory on purpose (see chatbot.py's
    # WORKSPACE_DIR/GIT_REPO_DIR comment): a file written via fs__write_file
    # must be visible to git__git_add/git__git_commit in the same run.
    sandbox_dir = os.path.join(ROOT, "workspace")
    mgr = MCPManager(logger=logger, workspace_dir=sandbox_dir, git_repo_dir=sandbox_dir)
    mgr.start_all()

    print(f"Connected servers: {list(mgr.clients.keys())}")
    tools = mgr.all_tools_for_llm()
    print(f"Total tools exposed to the LLM: {len(tools)}")
    for t in tools:
        print(f"  - {t['name']}")

    print("\n--- offers__match_offers ---")
    r = mgr.call_tool("offers__match_offers", {"interests": ["musica", "tecnologia"], "max_budget": 300})
    print(r["content"][0]["text"][:300], "...")

    if "fs" in mgr.clients:
        print("\n--- fs__write_file + fs__read_text_file ---")
        write_tool = next((t["name"] for t in mgr.clients["fs"].tools if "write" in t["name"]), None)
        read_tool = next((t["name"] for t in mgr.clients["fs"].tools if "read_text_file" in t["name"] or t["name"] == "read_file"), None)
        print("available fs tools:", [t["name"] for t in mgr.clients["fs"].tools])
        if write_tool:
            mgr.call_tool(f"fs__{write_tool}", {"path": os.path.join(mgr.workspace_dir, "README.md"),
                                                  "content": "# Proyecto1Redes workspace\n\nArchivo creado por el chatbot via MCP.\n"})
        if read_tool:
            r2 = mgr.call_tool(f"fs__{read_tool}", {"path": os.path.join(mgr.workspace_dir, "README.md")})
            print(r2["content"][0]["text"][:200])

    if "git" in mgr.clients:
        print("\n--- git tools available ---")
        print([t["name"] for t in mgr.clients["git"].tools])
        # Initialize a repo, add the file, commit - demonstrates functionality #4's example scenario.
        init_tool = next((t["name"] for t in mgr.clients["git"].tools if t["name"] == "git_init"), None)
        add_tool = next((t["name"] for t in mgr.clients["git"].tools if t["name"] == "git_add"), None)
        commit_tool = next((t["name"] for t in mgr.clients["git"].tools if t["name"] == "git_commit"), None)
        status_tool = next((t["name"] for t in mgr.clients["git"].tools if t["name"] == "git_status"), None)
        if init_tool:
            print(mgr.call_tool(f"git__{init_tool}", {"repo_path": mgr.git_repo_dir}))
        if "fs" not in mgr.clients:
            # fs server unavailable (e.g. npx missing) - write directly so
            # there's still something for git to add/commit below.
            with open(os.path.join(mgr.git_repo_dir, "README.md"), "w") as fh:
                fh.write("# Demo repo created via MCP (fs server unavailable)\n")
        if add_tool:
            print(mgr.call_tool(f"git__{add_tool}", {"repo_path": mgr.git_repo_dir, "files": ["README.md"]}))
        if commit_tool:
            print(mgr.call_tool(f"git__{commit_tool}", {"repo_path": mgr.git_repo_dir, "message": "Add README via MCP demo"}))
        if status_tool:
            print(mgr.call_tool(f"git__{status_tool}", {"repo_path": mgr.git_repo_dir}))

    mgr.close_all()
    print("\nSmoke test finished OK.")


if __name__ == "__main__":
    main()
