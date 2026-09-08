#!/usr/bin/env bash
# Deploys the offers MCP server (src/servers/offers_server) to Google
# Cloud Run - functionality #6 (remote MCP server). Builds the image
# from src/servers/offers_server/Dockerfile via Cloud Build and deploys
# it in one step with `gcloud run deploy --source`.
#
# Requirements: `gcloud` CLI installed and authenticated
# (`gcloud auth login`), with a project set
# (`gcloud config set project <id>`) that has the Cloud Run and Cloud
# Build APIs enabled.
#
# Usage:
#   ./scripts/deploy_offers_cloud_run.sh [service-name] [region]
#
# After it finishes, copy the printed service URL into your .env as
# OFFERS_REMOTE_URL, and set OFFERS_AUTH_TOKEN to the same value passed
# here via MCP_AUTH_TOKEN.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER_DIR="$ROOT_DIR/src/servers/offers_server"

SERVICE_NAME="${1:-offers-mcp}"
REGION="${2:-us-central1}"

if [ -z "${MCP_AUTH_TOKEN:-}" ]; then
  echo "[warn] MCP_AUTH_TOKEN is not set in your shell - deploying with auth disabled." >&2
  echo "       Export MCP_AUTH_TOKEN=<some random secret> before running this script to require it." >&2
fi

gcloud run deploy "$SERVICE_NAME" \
  --source "$SERVER_DIR" \
  --region "$REGION" \
  --allow-unauthenticated \
  --set-env-vars "MCP_AUTH_TOKEN=${MCP_AUTH_TOKEN:-}"

echo
echo "Deployed. Set this in your .env:"
echo "  OFFERS_REMOTE_URL=<the Service URL printed above>"
if [ -n "${MCP_AUTH_TOKEN:-}" ]; then
  echo "  OFFERS_AUTH_TOKEN=$MCP_AUTH_TOKEN"
fi
