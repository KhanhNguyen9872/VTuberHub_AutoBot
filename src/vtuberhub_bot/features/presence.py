#!/usr/bin/env python3
"""Socket.IO presence session for VTuberVN online-time achievements.

The backend accumulates `totalOnlineMinutes` only when the user's final
socket connection disconnects (notifications.gateway.ts: handleDisconnect).
Achievements online_10h (600 min) and online_100h (6000 min) are checked at
that moment.  This module keeps a presence socket open for a configurable
chunk, disconnects, waits for the server to process the disconnect, then the
caller can reconnect for the next chunk.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from ..api.client import Client

try:
    import socketio
except ImportError:  # pragma: no cover
    socketio = None


def online_session(
    client: Client,
    duration_seconds: int,
    *,
    stop_event: Any | None = None,
    should_stop: Callable[[], bool] | None = None,
    settle_seconds: int = 10,
) -> dict[str, Any]:
    """Connect, stay online for duration_seconds, then disconnect.

    Returns {connected, elapsed, error}.  `elapsed` is the number of seconds
    the socket was actually connected.  The server increments online minutes
    on disconnect; settle_seconds gives it time to run that handler.
    """
    if socketio is None:
        raise RuntimeError("python-socketio is not installed")
    token = client.session.headers.get("Authorization", "")
    if token.startswith("Bearer "):
        token = token[7:]
    if not token:
        raise RuntimeError("no JWT token for presence socket")

    sio = socketio.Client(
        reconnection=False,
        request_timeout=20,
        ssl_verify=not client.insecure,
    )
    started = 0.0
    ended_at = 0.0
    error: str | None = None
    connected = False
    try:
        sio.connect(
            client.base,
            auth={"token": token},
            socketio_path="api/socket.io/",
            transports=["websocket"],
            wait_timeout=20,
        )
        connected = True
        started = time.time()
        deadline = started + max(1, int(duration_seconds))
        while time.time() < deadline:
            if stop_event is not None and stop_event.is_set():
                break
            if should_stop is not None and should_stop():
                break
            if not sio.connected:
                break
            time.sleep(1)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        ended_at = time.time()
        try:
            if sio.connected:
                sio.disconnect()
        except Exception:
            pass
        if settle_seconds > 0:
            end = time.time() + settle_seconds
            while time.time() < end:
                if stop_event is not None and stop_event.is_set():
                    break
                time.sleep(0.5)
    elapsed = int(ended_at - started) if started and ended_at else 0
    return {"connected": connected, "elapsed": elapsed, "error": error}


def trigger_achievements(client: Client, wait_seconds: int = 65) -> None:
    """Connect to the notification gateway for one minute and disconnect.

    The backend increments totalOnlineMinutes and calls checkAndUnlock() when
    the last socket disconnects. This is enough to trigger level achievements
    (and online-time achievements if the account already has enough minutes).
    """
    if socketio is None:
        print("python-socketio is not installed; skip --trigger-achievements")
        return
    token = client.session.headers.get("Authorization", "")
    if token.startswith("Bearer "):
        token = token[7:]
    if not token:
        print("no token for socket connection")
        return

    sio = socketio.Client(
        reconnection=False,
        request_timeout=15,
        ssl_verify=not client.insecure,
    )
    try:
        sio.connect(
            client.base,
            auth={"token": token},
            socketio_path="api/socket.io/",
            transports=["websocket"],
            wait_timeout=15,
        )
        print(f"socket connected; waiting {wait_seconds}s before disconnect...")
        time.sleep(max(5, wait_seconds))
        sio.disconnect()
        time.sleep(3)
        print("socket disconnected; achievement check triggered")
    except Exception as exc:
        print("socket trigger failed:", exc)
        try:
            sio.disconnect()
        except Exception:
            pass
