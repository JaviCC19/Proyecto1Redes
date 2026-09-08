# Container image for the remote deployment of the offers MCP server
# (functionality #6). Only the standard library is required (see
# http_server.py / server.py), so the image needs no pip install step
# beyond a plain python:slim base.

FROM python:3.12-slim

WORKDIR /app
COPY server.py offers_data.py http_server.py ./

ENV PORT=8080
EXPOSE 8080

# Lets `docker ps` / orchestrators see server health directly (GET
# /health, added in http_server.py) instead of only inferring it from
# whether the process is still running.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python3 -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8080\")}/health', timeout=2)"

CMD ["python3", "http_server.py"]
