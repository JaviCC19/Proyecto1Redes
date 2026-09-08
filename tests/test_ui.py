"""
Unit tests for src/host/ui.py - the terminal color/formatting helpers
(the "extra" UI credit). Runs with colors force-disabled (as they are
under a test runner, since stdout isn't a TTY) so assertions check the
underlying content/structure rather than exact ANSI byte sequences.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "host"))

import ui  # noqa: E402


class TestUiHelpers(unittest.TestCase):
    def test_banner_contains_title_and_subtitle(self) -> None:
        text = ui.banner("Chatbot CC3067", "Proyecto 1 - Redes")
        self.assertIn("Chatbot CC3067", text)
        self.assertIn("Proyecto 1 - Redes", text)

    def test_banner_without_subtitle_has_no_extra_blank_line(self) -> None:
        text = ui.banner("Solo titulo")
        self.assertEqual(len(text.splitlines()), 3)  # top border, title, bottom border

    def test_user_and_bot_labels_are_distinct(self) -> None:
        self.assertNotEqual(ui.user_prompt(), ui.bot_label())
        self.assertIn("Tú", ui.user_prompt())
        self.assertIn("Bot", ui.bot_label())

    def test_error_and_success_prefix_markers(self) -> None:
        self.assertTrue(ui.error("algo falló").startswith("✗"))
        self.assertTrue(ui.success("listo").startswith("✓"))
        self.assertIn("algo falló", ui.error("algo falló"))

    def test_tool_call_line_truncates_after_three_arguments(self) -> None:
        line = ui.tool_call_line("offers", "match_offers", {
            "interests": ["a"], "preferred_category": "x", "max_budget": 1, "top_n": 3,
        })
        self.assertIn("...", line)
        self.assertIn("match_offers", line)
        self.assertIn("offers", line)

    def test_tool_call_line_no_ellipsis_with_few_arguments(self) -> None:
        line = ui.tool_call_line("offers", "get_offer_details", {"offer_id": "OF-001"})
        self.assertNotIn("...", line)

    def test_token_usage_line_shows_cache_hit_only_when_present(self) -> None:
        with_cache = ui.token_usage_line({"input_tokens": 10, "cache_read_input_tokens": 500, "output_tokens": 20})
        without_cache = ui.token_usage_line({"input_tokens": 10, "output_tokens": 20})
        self.assertIn("cache_hit=500", with_cache)
        self.assertNotIn("cache_hit", without_cache)
        self.assertIn("in=10", without_cache)
        self.assertIn("out=20", without_cache)

    def test_colorize_is_a_no_op_when_disabled(self) -> None:
        # ui._ENABLED is False under the test runner (stdout isn't a tty),
        # so colorize() must return the text unchanged, never raise.
        self.assertEqual(ui.colorize("plain", ui.Color.RED), "plain")

    def test_spinner_is_a_no_op_context_manager_when_disabled(self) -> None:
        with ui.Spinner("Pensando"):
            pass  # must not raise / must not spawn a thread when not a TTY


if __name__ == "__main__":
    unittest.main()
