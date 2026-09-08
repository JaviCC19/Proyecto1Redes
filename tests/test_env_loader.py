"""
Unit tests for src/host/env_loader.py - the dependency-free .env
parser (avoids pulling in python-dotenv for one API key).
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "host"))

from env_loader import load_dotenv  # noqa: E402


class TestLoadDotenv(unittest.TestCase):
    def setUp(self) -> None:
        self._keys_to_clean: list[str] = []

    def tearDown(self) -> None:
        for key in self._keys_to_clean:
            os.environ.pop(key, None)

    def _write_env(self, content: str) -> str:
        fd, path = tempfile.mkstemp(suffix=".env")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        return path

    def test_parses_key_value_pairs(self) -> None:
        self._keys_to_clean += ["TEST_FOO"]
        path = self._write_env("TEST_FOO=bar\n")
        load_dotenv(path)
        self.assertEqual(os.environ["TEST_FOO"], "bar")

    def test_strips_surrounding_quotes(self) -> None:
        self._keys_to_clean += ["TEST_QUOTED", "TEST_SINGLE_QUOTED"]
        path = self._write_env('TEST_QUOTED="hello world"\nTEST_SINGLE_QUOTED=\'hi\'\n')
        load_dotenv(path)
        self.assertEqual(os.environ["TEST_QUOTED"], "hello world")
        self.assertEqual(os.environ["TEST_SINGLE_QUOTED"], "hi")

    def test_ignores_comments_and_blank_lines(self) -> None:
        self._keys_to_clean += ["TEST_REAL"]
        path = self._write_env("# a comment\n\nTEST_REAL=1\n# TEST_COMMENTED=should_not_load\n")
        load_dotenv(path)
        self.assertEqual(os.environ["TEST_REAL"], "1")
        self.assertNotIn("TEST_COMMENTED", os.environ)

    def test_does_not_override_an_already_set_env_var(self) -> None:
        """Real shell/CI env vars must win over .env - matches
        os.environ.setdefault's semantics, used deliberately."""
        self._keys_to_clean += ["TEST_PRESET"]
        os.environ["TEST_PRESET"] = "from_shell"
        path = self._write_env("TEST_PRESET=from_dotenv\n")
        load_dotenv(path)
        self.assertEqual(os.environ["TEST_PRESET"], "from_shell")

    def test_missing_file_is_a_silent_no_op(self) -> None:
        load_dotenv("/nonexistent/path/does-not-exist.env")  # must not raise


if __name__ == "__main__":
    unittest.main()
