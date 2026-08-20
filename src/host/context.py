"""
context.py

Session/conversation context manager (functionality #2: "Mantener
contexto en una sesión"). Keeps the running list of Anthropic Messages
API turns (user / assistant, including tool_use / tool_result blocks)
so that follow-up questions ("¿en que fecha nació?" after "¿Quien fue
Alan Turing?") are answered correctly - the whole history is resent to
the API on every turn, which is how the Messages API keeps state
(it is stateless server-side).

A session can optionally be persisted to disk as JSON so it survives
across separate runs of the chatbot, but by default it just lives in
memory for the duration of the process.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Optional


class SessionContext:
    def __init__(self, session_id: Optional[str] = None, persist_dir: Optional[str] = None):
        self.session_id = session_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.persist_dir = persist_dir
        self.messages: list[dict[str, Any]] = []

        if self.persist_dir:
            os.makedirs(self.persist_dir, exist_ok=True)

    @property
    def _path(self) -> Optional[str]:
        if not self.persist_dir:
            return None
        return os.path.join(self.persist_dir, f"session_{self.session_id}.json")

    def add_user_message(self, content: Any) -> None:
        self.messages.append({"role": "user", "content": content})
        self._save()

    def add_assistant_message(self, content: Any) -> None:
        self.messages.append({"role": "assistant", "content": content})
        self._save()

    def as_api_messages(self) -> list[dict[str, Any]]:
        """Returns the message list exactly as the Anthropic Messages API
        expects it (list of {"role": ..., "content": ...})."""
        return self.messages

    def _save(self) -> None:
        path = self._path
        if not path:
            return
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"session_id": self.session_id, "messages": self.messages}, fh,
                       ensure_ascii=False, indent=2)
