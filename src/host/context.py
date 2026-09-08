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
    def __init__(self, session_id: Optional[str] = None, persist_dir: Optional[str] = None,
                 max_history_turns: int = 20):
        self.session_id = session_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.persist_dir = persist_dir
        self.messages: list[dict[str, Any]] = []
        # Token optimization: as_api_messages() below caps how many human
        # turns get resent to Claude once a conversation grows past this,
        # instead of resending the entire history forever. The full
        # history is still kept in self.messages (and on disk) for
        # logging/persistence - only what's sent to the LLM is windowed.
        self.max_history_turns = max_history_turns
        self._turn_starts: list[int] = []

        if self.persist_dir:
            os.makedirs(self.persist_dir, exist_ok=True)

    @property
    def _path(self) -> Optional[str]:
        if not self.persist_dir:
            return None
        return os.path.join(self.persist_dir, f"session_{self.session_id}.json")

    def add_user_message(self, content: Any) -> None:
        # A plain string content means this is a real human turn (as
        # opposed to the "user" message the tool-use loop sends back with
        # tool_result blocks) - that's the only kind of boundary it's safe
        # to trim the window on, since it's never a dangling tool_result
        # without its matching tool_use.
        if isinstance(content, str):
            self._turn_starts.append(len(self.messages))
        self.messages.append({"role": "user", "content": content})
        self._save()

    def add_assistant_message(self, content: Any) -> None:
        self.messages.append({"role": "assistant", "content": content})
        self._save()

    def as_api_messages(self) -> list[dict[str, Any]]:
        """Returns the message list to send to the Anthropic Messages API
        (list of {"role": ..., "content": ...}), windowed to the last
        `max_history_turns` human turns. This bounds how many tokens get
        resent on every single turn as a conversation grows, instead of
        the cost growing without limit for the lifetime of the session.
        The full, untrimmed history stays in self.messages / on disk."""
        if len(self._turn_starts) <= self.max_history_turns:
            return self.messages
        cutoff = self._turn_starts[-self.max_history_turns]
        return self.messages[cutoff:]

    def _save(self) -> None:
        path = self._path
        if not path:
            return
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"session_id": self.session_id, "messages": self.messages}, fh,
                       ensure_ascii=False, indent=2)
