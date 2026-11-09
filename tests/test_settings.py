"""Tests for settings.toml checks."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import ROOT  # noqa: F401  (adds src to sys.path)

import settings


def _write(text: str) -> Path:
    handle = tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False)
    handle.write(text)
    handle.close()
    return Path(handle.name)


class SettingsTest(unittest.TestCase):
    def test_repository_file_is_correct(self) -> None:
        cfg = settings.load()
        self.assertIn("running", cfg.activity_types)
        for key in cfg.detail_activity_types:
            self.assertIn(key, cfg.activity_types)

    def test_empty_lists_are_correct(self) -> None:
        cfg = settings.load(_write("activity_types = []\ndetail_activity_types = []\n"))
        self.assertEqual(cfg.activity_types, ())

    def test_errors(self) -> None:
        cases = {
            "missing list": "activity_types = ['running']\n",
            "uppercase key": "activity_types = ['Running']\ndetail_activity_types = []\n",
            "detail not in activity types": "activity_types = ['cycling']\ndetail_activity_types = ['running']\n",
            "same key two times": "activity_types = ['running', 'running']\ndetail_activity_types = []\n",
            "not a list": "activity_types = 'running'\ndetail_activity_types = []\n",
            "syntax error": "activity_types = [running\n",
        }
        for name, text in cases.items():
            with self.subTest(name), self.assertRaises(settings.SettingsError):
                settings.load(_write(text))

    def test_missing_file(self) -> None:
        with self.assertRaises(settings.SettingsError):
            settings.load(Path(tempfile.gettempdir()) / "does-not-exist.toml")


if __name__ == "__main__":
    unittest.main()
