"""Achievement snapshot/diff helpers."""
from __future__ import annotations

from typing import Any

from .client import Client

def achievement_snapshot(client: Client) -> dict[str, dict[str, Any]]:
    return {
        str(a.get("id")): a
        for a in client.achievements()
        if isinstance(a, dict) and a.get("id")
    }


def report_achievements(
    client: Client, before: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    after = achievement_snapshot(client)
    # before is the full snapshot; compare unlocked state instead of keys
    unlocked = [
        a
        for a in after.values()
        if bool(a.get("unlocked")) and not bool(before.get(str(a.get("id")), {}).get("unlocked"))
    ]
    total_coins = sum(int(a.get("coinReward") or 0) for a in unlocked)
    if unlocked:
        print("achievements newly unlocked:")
        for a in unlocked:
            print(f"  + {a.get('id')} ({a.get('name')}) -> {a.get('coinReward')} coins")
        print(f"achievement coins gained: {total_coins}")
    else:
        print("achievements newly unlocked: none")
    return unlocked
