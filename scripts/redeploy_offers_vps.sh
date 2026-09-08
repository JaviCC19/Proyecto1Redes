#!/usr/bin/env bash
# Redeploys the offers MCP server (functionality #6) to a remote host
# already running it via Docker (see the "Remote: HTTP" section in
# src/servers/offers_server/README.md for the first-time setup).
#
# Uses `rsync -a --delete` instead of `scp -r` on purpose: scp -r into
# an *existing* remote directory copies the source directory itself
# one level too deep (e.g. /opt/offers-mcp/offers_server/*.py instead
# of /opt/offers-mcp/*.py) and silently leaves the old files in place
# for `docker build` to pick up - which is exactly what happened the
# first time this was done by hand. rsync with a trailing slash on the
# source syncs *contents* into the destination and removes anything
# stale, so this can't recur.
#
# Usage:
#   ./scripts/redeploy_offers_vps.sh user@host [remote_dir] [container_port] [auth_token]
# Defaults: remote_dir=/opt/offers-mcp, container_port=8090, auth_token=$MCP_AUTH_TOKEN env var
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 user@host [remote_dir] [container_port] [auth_token]" >&2
  exit 1
fi

TARGET="$1"
REMOTE_DIR="${2:-/opt/offers-mcp}"
PORT="${3:-8090}"
TOKEN="${4:-${MCP_AUTH_TOKEN:-}}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER_DIR="$ROOT_DIR/src/servers/offers_server"

echo "[redeploy] syncing $SERVER_DIR/ -> $TARGET:$REMOTE_DIR/"
ssh "$TARGET" "mkdir -p $REMOTE_DIR"
rsync -a --delete "$SERVER_DIR"/ "$TARGET:$REMOTE_DIR"/

echo "[redeploy] rebuilding and restarting the container"
ssh "$TARGET" "cd $REMOTE_DIR && \
  docker build --no-cache -t offers-mcp . && \
  docker stop offers-mcp 2>/dev/null || true; \
  docker rm offers-mcp 2>/dev/null || true; \
  docker run -d --restart unless-stopped --name offers-mcp -p ${PORT}:8080 \
    ${TOKEN:+-e MCP_AUTH_TOKEN=$TOKEN} offers-mcp && \
  sleep 1 && curl -s http://127.0.0.1:${PORT}/health"

echo
echo "[redeploy] done."
