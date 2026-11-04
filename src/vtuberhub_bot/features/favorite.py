#!/usr/bin/env python3
"""Shared VTuberVN favorite add/remove EXP farm.

The live backend awards +10 EXP when a channel is added to favorites if no
FAVORITE_ADD activity exists for that channel.  Removing the channel deletes
that activity, so the next add awards +10 again.  The endpoint calls
UsersService.addExp() directly, bypassing GamificationService.awardExp() and
its daily sub-caps.  There is no daily limit on this path.

A PATCH request accepts up to 50 operations, i.e. 25 add/remove pairs =
250 EXP.  Measured on live: ~1.5s/request, ~8-10K EXP/min.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from ..api.client import Client

ProgressCallback = Callable[[dict[str, Any]], None]


def pick_channel(client: Client) -> str:
    """Pick a real channel that is not currently in the user's favorites."""
    favorites = client.json("GET", "/api/v2/users/favorites")
    existing = (
        {str(f.get("id")) for f in favorites}
        if isinstance(favorites, list)
        else set()
    )
    data = client.json("GET", "/api/v2/channels", params={"limit": 100})
    rows = data if isinstance(data, list) else data.get("data", [])
    for row in rows:
        cid = row.get("id")
        if cid and str(cid) not in existing:
            return str(cid)
    raise RuntimeError("no non-favorited channel found in the first 100")


def cleanup(client: Client, channel_id: str) -> None:
    try:
        client.json(
            "PATCH",
            "/api/v2/users/favorites",
            json=[{"op": "remove", "channel_id": channel_id}],
        )
    except Exception as exc:
        print(f"favorite cleanup failed for {channel_id}: {exc}", flush=True)


def farm_to_target(
    client: Client,
    target_exp: int,
    *,
    rpm: float = 60.0,
    batch: int = 50,
    stop_event: Any | None = None,
    should_stop: Callable[[], bool] | None = None,
    progress: ProgressCallback | None = None,
    check_every: int = 2,
) -> dict[str, Any]:
    """Farm EXP with add/remove cycles until target_exp is reached.

    Returns a dict with start, final, gained, requests, elapsed, reached,
    interrupted and error.  The chosen channel is always removed at the end.
    """
    me = client.me()
    start_exp = int(me.get("exp") or 0)
    target_exp = max(int(target_exp), start_exp)
    batch = max(2, min(50, int(batch)))
    if batch % 2:
        batch -= 1
    pairs = batch // 2
    per_request = pairs * 10

    channel_id = pick_channel(client)
    ops: list[dict[str, str]] = []
    for _ in range(pairs):
        ops.append({"op": "add", "channel_id": channel_id})
        ops.append({"op": "remove", "channel_id": channel_id})

    current = start_exp
    sent = 0
    started = time.time()
    interrupted = False
    error: str | None = None
    try:
        while current < target_exp:
            if stop_event is not None and stop_event.is_set():
                interrupted = True
                break
            if should_stop is not None and should_stop():
                interrupted = True
                break
            t0 = time.time()
            client.json("PATCH", "/api/v2/users/favorites", json=ops)
            sent += 1
            if sent % max(1, check_every) == 0 or current + per_request >= target_exp:
                current = int(client.me().get("exp") or 0)
                if progress is not None:
                    elapsed = max(0.001, time.time() - started)
                    progress(
                        {
                            "start": start_exp,
                            "current": current,
                            "target": target_exp,
                            "requests": sent,
                            "elapsed": elapsed,
                            "rate": (current - start_exp) / elapsed * 60,
                            "channel_id": channel_id,
                        }
                    )
            delay = 60.0 / max(1.0, rpm) - (time.time() - t0)
            if delay > 0:
                time.sleep(delay)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        cleanup(client, channel_id)
        try:
            current = int(client.me().get("exp") or current)
        except Exception:
            pass

    elapsed = max(0.001, time.time() - started)
    return {
        "start": start_exp,
        "final": current,
        "gained": current - start_exp,
        "requests": sent,
        "elapsed": elapsed,
        "reached": current >= target_exp,
        "interrupted": interrupted,
        "error": error,
        "channel_id": channel_id,
    }
