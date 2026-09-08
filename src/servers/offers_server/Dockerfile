# Container image for the remote deployment of the offers MCP server
# (functionality #6). Only the standard library is required (see
# http_server.py / server.py), so the image needs no pip install step
# beyond a plain python:slim base.

FROM python:3.12-slim

WORKDIR /app
COPY server.py offers_data.py http_server.py ./

ENV PORT=8080
EXPOSE 8080

CMD ["python3", "http_server.py"]
