#!/usr/bin/env python3
"""Thin entrypoint for systemd (keeps the old service command name)."""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from vtuberhub_bot.main import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
