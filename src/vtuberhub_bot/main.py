"""Package entrypoint."""
from __future__ import annotations

import signal
import traceback

from .bot.router import MultiUserBot

def main() -> int:
    bot = MultiUserBot()
    signal.signal(signal.SIGTERM, bot.stop)
    signal.signal(signal.SIGINT, bot.stop)
    try:
        bot.start()
    except Exception as exc:
        print("fatal multi-user bot error:", exc, flush=True)
        print(traceback.format_exc(), flush=True)
        return 1
    return 0
