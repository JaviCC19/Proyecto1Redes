"""
llm_client.py

Minimal, dependency-light client for the Anthropic Messages API
(https://docs.claude.com/en/api/messages), talking plain HTTPS + JSON.

Only the `requests` library (a generic HTTP client, not an MCP/AI SDK)
is used here; there is no `anthropic` package involved. This satisfies
functionality #1 ("Conexión con un LLM a nivel de su API").

The API key is read from the ANTHROPIC_API_KEY environment variable
(optionally loaded from a local .env file by env_loader.py - see
chatbot.py). It is never hard-coded.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

import requests

API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"


class LLMError(Exception):
    pass


class AnthropicClient:
    """Thin wrapper around a single POST /v1/messages call, including
    support for Anthropic's tool-use (function calling) content blocks,
    which is how this project wires the LLM to the MCP tools."""

    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_MODEL,
                 max_tokens: int = 1024):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise LLMError(
                "ANTHROPIC_API_KEY is not set. Export it or create a .env file "
                "(see README.md)."
            )
        self.model = model
        self.max_tokens = max_tokens

    def create_message(self, messages: list[dict], system: Optional[str] = None,
                        tools: Optional[list[dict]] = None) -> dict:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": _with_cache_breakpoint(messages),
        }
        if system:
            # Prompt caching (https://docs.claude.com/en/docs/build-with-claude/
            # prompt-caching): the system prompt is identical on every turn of
            # the tool-use loop, so marking it as an ephemeral cache breakpoint
            # means Anthropic only pays to *process* it once per ~5 minutes
            # instead of on every single request in the conversation.
            body["system"] = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        if tools:
            # Same idea for the tool schema: it's resent unchanged on every
            # turn too (see mcp_manager.all_tools_for_llm). Marking the last
            # tool definition as a cache breakpoint caches the whole list.
            tools = [dict(t) for t in tools]
            tools[-1] = {**tools[-1], "cache_control": {"type": "ephemeral"}}
            body["tools"] = tools

        resp = requests.post(API_URL, headers=headers, data=json.dumps(body), timeout=60)
        if resp.status_code != 200:
            raise LLMError(f"Anthropic API error {resp.status_code}: {resp.text}")
        return resp.json()


def _with_cache_breakpoint(messages: list[dict]) -> list[dict]:
    """Returns a shallow copy of `messages` with an ephemeral prompt-cache
    breakpoint on the last content block of the last message.

    Every turn of the agent loop resends the *entire* conversation so far
    (the Messages API is stateless - see context.py), so without caching,
    a long conversation gets fully reprocessed as fresh input tokens on
    every single turn. Marking the newest message as a cache breakpoint
    lets Anthropic reuse the cached prefix from the previous turn instead
    of reprocessing everything that came before it - the incremental cost
    of each turn becomes roughly proportional to what's new, not to the
    whole history. Does not mutate the caller's message list or its
    session-persisted originals.
    """
    if not messages:
        return messages
    result = list(messages)
    last = dict(result[-1])
    content = last["content"]
    content = [{"type": "text", "text": content}] if isinstance(content, str) else [dict(b) for b in content]
    if content:
        content[-1] = {**content[-1], "cache_control": {"type": "ephemeral"}}
    last["content"] = content
    result[-1] = last
    return result
