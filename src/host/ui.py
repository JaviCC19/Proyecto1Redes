"""
ui.py

Small terminal UI layer for the chatbot host (the "extra" UI credit
mentioned in the assignment: "psicología del color, organización de
los elementos gráficos, usabilidad"). Pure ANSI escape codes - no
curses, no `rich`/`colorama` dependency - so it stays consistent with
the rest of the project's "standard library only" approach on the host
side.

Color choices follow conventional color psychology for CLIs so the
mapping is learnable at a glance rather than decorative: green for
success/the bot's replies, red for errors, yellow for MCP tool-call
activity (something is happening, not yet resolved), cyan for the
user's own input, dim gray for secondary/system text. Output is kept
readable when colors are unavailable (piped output, `NO_COLOR` set,
`--no-color`), per Nielsen's "visibility of system status" and
"aesthetic and minimalist design" heuristics: every colored line still
makes sense in plain text.
"""

from __future__ import annotations

import itertools
import os
import sys
import threading
import time

_ENABLED = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


class Color:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"


def _c(text: str, *codes: str) -> str:
    if not _ENABLED or not codes:
        return text
    return "".join(codes) + text + Color.RESET


def colorize(text: str, *codes: str) -> str:
    """Public entry point for _c(), for callers outside this module
    (e.g. logger.py coloring its console-only interaction log)."""
    return _c(text, *codes)


def banner(title: str, subtitle: str = "") -> str:
    width = max(len(title), len(subtitle)) + 4
    top = "┌" + "─" * width + "┐"
    bottom = "└" + "─" * width + "┘"
    lines = [top, f"│  {title.ljust(width - 2)}│"]
    if subtitle:
        lines.append(f"│  {subtitle.ljust(width - 2)}│")
    lines.append(bottom)
    return _c("\n".join(lines), Color.BOLD, Color.CYAN)


def user_prompt() -> str:
    return _c("Tú", Color.BOLD, Color.CYAN) + _c(" › ", Color.DIM)


def bot_label() -> str:
    return _c("Bot", Color.BOLD, Color.GREEN) + _c(" › ", Color.DIM)


def system(text: str) -> str:
    return _c(text, Color.DIM)


def error(text: str) -> str:
    return _c(f"✗ {text}", Color.RED, Color.BOLD)


def success(text: str) -> str:
    return _c(f"✓ {text}", Color.GREEN)


def tool_call_line(server_alias: str, tool_name: str, arguments: dict) -> str:
    args_preview = ", ".join(f"{k}={v!r}" for k, v in list(arguments.items())[:3])
    if len(arguments) > 3:
        args_preview += ", ..."
    tag = _c(f" {server_alias} ", Color.BOLD)
    return _c("⚙ ", Color.YELLOW) + _c(f"[{server_alias}] ", Color.YELLOW, Color.BOLD) + \
        _c(f"{tool_name}({args_preview})", Color.YELLOW)


class Spinner:
    """Minimal single-line spinner shown while waiting on the Anthropic
    API (visibility of system status: without it, a slow response looks
    indistinguishable from a hang). No-op when output isn't a TTY."""

    _FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, label: str = "Pensando"):
        self.label = label
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _spin(self) -> None:
        for frame in itertools.cycle(self._FRAMES):
            if self._stop.is_set():
                break
            sys.stdout.write(f"\r{_c(frame, Color.YELLOW)} {system(self.label + '...')}  ")
            sys.stdout.flush()
            time.sleep(0.08)
        sys.stdout.write("\r" + " " * (len(self.label) + 6) + "\r")
        sys.stdout.flush()

    def __enter__(self) -> "Spinner":
        if _ENABLED:
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._thread is not None:
            self._stop.set()
            self._thread.join(timeout=1)
