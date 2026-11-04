"""Offline smoke tests for the package core."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vtuberhub_bot.config import DEFAULT_FEATURES, FAN_BADGE_SECONDS
from vtuberhub_bot.storage import (
    load_daily_state,
    load_state,
    save_daily_state,
    save_state,
)
from vtuberhub_bot.utils import fmt_duration, fmt_num
from vtuberhub_bot.worker.daemon import Daemon


class CoreTests(unittest.TestCase):
    def test_default_features(self) -> None:
        self.assertTrue(DEFAULT_FEATURES["watch"])
        self.assertTrue(DEFAULT_FEATURES["online"])
        self.assertFalse(DEFAULT_FEATURES["fan_multi"])

    def test_formatting(self) -> None:
        self.assertEqual(fmt_num(129600), "129,600")
        self.assertEqual(fmt_duration(FAN_BADGE_SECONDS), "36h00m")
        self.assertEqual(fmt_duration(125), "2m")

    def test_state_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "daemon.json")
            state = load_state(path)
            state["features"]["fan"] = True
            state["watch_seconds"] = 300
            save_state(state, path)
            loaded = load_state(path)
            self.assertTrue(loaded["features"]["fan"])
            self.assertEqual(loaded["watch_seconds"], 300)

    def test_daily_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            save_daily_state(
                {"date": "2026-01-01", "exp": 30, "coins": 0,
                 "contribution": 0, "runs": 1},
                tmp,
                "demo",
            )
            # A different UTC day resets to zero.
            loaded = load_daily_state(tmp, "demo")
            self.assertEqual(loaded["exp"], 0)
            self.assertEqual(loaded["runs"], 0)

    def test_daemon_mro(self) -> None:
        names = [c.__name__ for c in Daemon.__mro__]
        self.assertIn("BaseWorker", names)
        self.assertIn("WatchMixin", names)
        self.assertIn("FanMixin", names)
        self.assertIn("CommandsMixin", names)


if __name__ == "__main__":
    unittest.main()
