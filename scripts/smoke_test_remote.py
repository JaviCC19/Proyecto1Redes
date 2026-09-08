#!/usr/bin/env python3
"""
smoke_test_remote.py

Self-contained check for functionality #6 (remote MCP server) that
does not require an actual cloud deployment to run: it starts
`http_server.py` as a local subprocess (the exact same code that would
run inside the Cloud Run container built from the Dockerfile), points
`OFFERS_REMOTE_URL` at it, and runs the host's MCPManager against it -
proving the HTTP transport and MCPHttpClient work end to end before
spending a real deployment.

Once you've deployed with scripts/deploy_offers_cloud_run.sh, re-run
this same check against the real URL:

    OFFERS_REMOTE_URL=https://<service>.a.run.app python3 scripts/smoke_test_remote.py
"""
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src", "host"))

from logger import InteractionLogger  # noqa: E402
from mcp_manager import MCPManager  # noqa: E402


def main() -> None:
    remote_url = os.environ.get("OFFERS_REMOTE_URL", "").strip()
    local_proc = None

    if not remote_url:
        port = "8123"
        remote_url = f"http://127.0.0.1:{port}"
        server_path = os.path.join(ROOT, "src", "servers", "offers_server", "http_server.py")
        print(f"[smoke] no OFFERS_REMOTE_URL set - starting local http_server.py on {remote_url}")
        env = {**os.environ, "PORT": port}
        local_proc = subprocess.Popen([sys.executable, server_path], env=env)
        time.sleep(1.0)  # give the ThreadingHTTPServer a moment to bind
        os.environ["OFFERS_REMOTE_URL"] = remote_url
    else:
        print(f"[smoke] using OFFERS_REMOTE_URL={remote_url}")

    try:
        # fs/git are disabled below (this script only exercises the offers
        # transport), but they'd share one sandbox dir if enabled - see
        # chatbot.py's WORKSPACE_DIR/GIT_REPO_DIR comment.
        sandbox_dir = os.path.join(ROOT, "workspace")
        logger = InteractionLogger(log_dir=os.path.join(ROOT, "logs"), echo_to_console=False)
        mgr = MCPManager(logger=logger, workspace_dir=sandbox_dir, git_repo_dir=sandbox_dir)
        mgr.start_all(include_fs=False, include_git=False, include_offers=True)

        assert "offers" in mgr.clients, "offers client did not connect"
        tools = [t["name"] for t in mgr.clients["offers"].tools]
        print(f"[smoke] tools/list over HTTP -> {tools}")
        assert set(tools) == {"list_offers", "get_offer_details", "match_offers", "claim_offer"}

        result = mgr.call_tool("offers__match_offers",
                                {"interests": ["musica", "tecnologia"], "max_budget": 300})
        assert result["isError"] is False
        print(f"[smoke] tools/call over HTTP -> {result['content'][0]['text'][:200]}...")

        mgr.close_all()
        print("\nRemote (HTTP) smoke test finished OK.")
    finally:
        if local_proc is not None:
            local_proc.terminate()
            local_proc.wait(timeout=5)


if __name__ == "__main__":
    main()
