#!/usr/bin/env bash
# Convenience launcher for the chatbot host.
# Usage: ./scripts/run_chatbot.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ -d ".venv" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

python3 "$ROOT_DIR/src/host/chatbot.py"
