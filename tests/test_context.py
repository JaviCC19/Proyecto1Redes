"""
Unit tests for src/host/context.py - specifically the sliding history
window added to as_api_messages() (token-usage optimization: bound how
much of a long conversation gets resent to Claude on every turn).

Plain stdlib unittest, no pytest dependency, run with:
    python3 -m unittest discover -s tests
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "host"))

from context import SessionContext  # noqa: E402


class TestSessionContextWindow(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()

    def test_short_session_returns_full_history(self) -> None:
        s = SessionContext(persist_dir=self.tmpdir, max_history_turns=20)
        s.add_user_message("hola")
        s.add_assistant_message([{"type": "text", "text": "hola, ¿en qué te ayudo?"}])
        self.assertEqual(s.as_api_messages(), s.messages)

    def test_long_session_is_windowed_on_human_turn_boundaries(self) -> None:
        s = SessionContext(persist_dir=self.tmpdir, max_history_turns=3)
        for i in range(6):
            s.add_user_message(f"pregunta {i}")
            s.add_assistant_message([{"type": "text", "text": f"respuesta {i}"}])

        api_messages = s.as_api_messages()
        self.assertEqual(len(s.messages), 12)          # full history kept
        self.assertEqual(len(api_messages), 6)          # only last 3 turns sent
        self.assertEqual(api_messages[0]["content"], "pregunta 3")

    def test_tool_result_messages_never_start_a_window_boundary(self) -> None:
        """A tool_result 'user' message (list content) must never be
        mistaken for a fresh human turn - trimming there would strand a
        tool_result without the tool_use it answers."""
        s = SessionContext(persist_dir=self.tmpdir, max_history_turns=1)
        s.add_user_message("pregunta real 1")
        s.add_assistant_message([{"type": "tool_use", "id": "t1", "name": "x", "input": {}}])
        s.add_user_message([{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}])
        s.add_assistant_message([{"type": "text", "text": "listo"}])
        s.add_user_message("pregunta real 2")
        s.add_assistant_message([{"type": "text", "text": "respuesta 2"}])

        api_messages = s.as_api_messages()
        # Window should start at "pregunta real 2", never mid tool loop.
        self.assertEqual(api_messages[0]["content"], "pregunta real 2")

    def test_full_history_persisted_to_disk_even_when_windowed(self) -> None:
        s = SessionContext(persist_dir=self.tmpdir, max_history_turns=1)
        for i in range(3):
            s.add_user_message(f"pregunta {i}")
            s.add_assistant_message([{"type": "text", "text": f"respuesta {i}"}])

        import json
        with open(s._path, encoding="utf-8") as fh:
            saved = json.load(fh)
        self.assertEqual(len(saved["messages"]), 6)  # nothing lost on disk


if __name__ == "__main__":
    unittest.main()
