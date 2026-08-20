"""
logger.py

Lightweight logger for every JSON-RPC interaction (request / response /
notification) exchanged between the host (chatbot) and any MCP server
(local or remote). This satisfies functionality #3 of the project:

    "Mantener y mostrar un log sobre todas las interacciones (solicitudes
    y respuestas) con los servidores MCP."

The logger prints a compact, human readable line to stdout (so the user
can watch the traffic live while chatting) and also appends a full JSON
record to a log file so it can be reviewed / attached to the report
later (and, eventually, correlated with a Wireshark capture for the
JSON-RPC over HTTP transport used by the remote server in part 6).

No third-party logging framework is used: this is a small, self
contained module built with the Python standard library only.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from datetime import datetime, timezone

_LOCK = threading.Lock()


class InteractionLogger:
    """Records every JSON-RPC message that crosses the MCP transport.

    One instance is shared by every MCPClient (see mcp_client.py) so all
    servers (filesystem, git, offers, ...) end up in the same log file,
    tagged with the server alias that produced/received the message.
    """

    def __init__(self, log_dir: str = "logs", filename: str = "mcp_interactions.log",
                 echo_to_console: bool = True) -> None:
        os.makedirs(log_dir, exist_ok=True)
        self.path = os.path.join(log_dir, filename)
        self.echo_to_console = echo_to_console
        # Start every run with a clear separator so it is easy to see
        # where a new chatbot session begins inside the same log file.
        with _LOCK, open(self.path, "a", encoding="utf-8") as fh:
            fh.write(f"\n===== new session started {self._now()} =====\n")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="milliseconds")

    def log(self, server_alias: str, direction: str, message: dict) -> None:
        """direction is one of: 'request', 'response', 'notification'."""
        record = {
            "timestamp": self._now(),
            "server": server_alias,
            "direction": direction,
            "message": message,
        }
        line = json.dumps(record, ensure_ascii=False)
        with _LOCK:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
            if self.echo_to_console:
                print(self._format_console(server_alias, direction, message), file=sys.stderr)

    @staticmethod
    def _format_console(server_alias: str, direction: str, message: dict) -> str:
        arrow = {"request": "-->", "response": "<--", "notification": "..."}.get(direction, "?")
        method = message.get("method")
        if method:
            summary = f"method={method}"
        elif "result" in message:
            summary = "result"
        elif "error" in message:
            summary = f"error={message['error']}"
        else:
            summary = ""
        msg_id = message.get("id", "")
        return f"[MCP][{server_alias}] {arrow} id={msg_id} {summary}"
