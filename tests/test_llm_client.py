"""
Unit tests for src/host/llm_client.py - the Anthropic prompt-caching
breakpoints added to create_message() (token-usage optimization). No
network calls: requests.post is monkeypatched to capture the outgoing
payload instead of hitting the real API.
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "host"))

import llm_client  # noqa: E402


def _fake_post_capturing(sink: dict):
    def _fake_post(url, headers, data, timeout):
        sink["body"] = json.loads(data)
        sink["url"] = url
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn"}
        return response
    return _fake_post


class TestPromptCaching(unittest.TestCase):
    def setUp(self) -> None:
        self.client = llm_client.AnthropicClient(api_key="sk-test")
        self.messages = [
            {"role": "user", "content": "Quien fue Alan Turing?"},
            {"role": "assistant", "content": [{"type": "text", "text": "Fue un matemático..."}]},
            {"role": "user", "content": "En que fecha nació?"},
        ]
        self.tools = [
            {"name": "t1", "description": "d1", "input_schema": {}},
            {"name": "t2", "description": "d2", "input_schema": {}},
        ]

    def test_system_prompt_gets_a_cache_breakpoint(self) -> None:
        sink: dict = {}
        with patch("llm_client.requests.post", _fake_post_capturing(sink)):
            self.client.create_message(messages=self.messages, system="eres un asistente")
        self.assertEqual(
            sink["body"]["system"],
            [{"type": "text", "text": "eres un asistente", "cache_control": {"type": "ephemeral"}}],
        )

    def test_only_last_tool_gets_the_cache_breakpoint(self) -> None:
        sink: dict = {}
        with patch("llm_client.requests.post", _fake_post_capturing(sink)):
            self.client.create_message(messages=self.messages, tools=self.tools)
        self.assertNotIn("cache_control", sink["body"]["tools"][0])
        self.assertEqual(sink["body"]["tools"][-1]["cache_control"], {"type": "ephemeral"})

    def test_last_message_content_block_gets_the_cache_breakpoint(self) -> None:
        sink: dict = {}
        with patch("llm_client.requests.post", _fake_post_capturing(sink)):
            self.client.create_message(messages=self.messages)
        last_sent = sink["body"]["messages"][-1]
        self.assertEqual(
            last_sent["content"],
            [{"type": "text", "text": "En que fecha nació?", "cache_control": {"type": "ephemeral"}}],
        )

    def test_original_message_objects_are_never_mutated(self) -> None:
        """create_message must not leak cache_control into the caller's
        (session-persisted) message objects - only the copy sent over the
        wire should carry it."""
        sink: dict = {}
        original_last = dict(self.messages[-1])
        with patch("llm_client.requests.post", _fake_post_capturing(sink)):
            self.client.create_message(messages=self.messages)
        self.assertEqual(self.messages[-1], original_last)
        self.assertIsInstance(self.messages[-1]["content"], str)

    def test_empty_messages_list_is_handled(self) -> None:
        sink: dict = {}
        with patch("llm_client.requests.post", _fake_post_capturing(sink)):
            self.client.create_message(messages=[])
        self.assertEqual(sink["body"]["messages"], [])


if __name__ == "__main__":
    unittest.main()
