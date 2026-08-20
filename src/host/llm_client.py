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
            "messages": messages,
        }
        if system:
            body["system"] = system
        if tools:
            body["tools"] = tools

        resp = requests.post(API_URL, headers=headers, data=json.dumps(body), timeout=60)
        if resp.status_code != 200:
            raise LLMError(f"Anthropic API error {resp.status_code}: {resp.text}")
        return resp.json()
