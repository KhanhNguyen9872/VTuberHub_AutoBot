"""Five-minute watch sessions."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from ..api.client import Client
from ..utils import today_utc
from .base import serialized


class WatchMixin:
    @serialized
    def do_watch_session(
        self,
        announce: bool = True,
        client: Client | None = None,
        channel_id: str | None = None,
    ) -> bool:
        client = client or self.client()
        before = client.me()
        state = self.get_state()
        if channel_id is None and self.feature("fan"):
            channel_id = (state.get("fan_channel_id") or "").strip() or None
        if channel_id:
            data = client.json(
                "GET",
                "/api/v2/videos",
                params={"channel_id": channel_id, "limit": 20},
            )
            videos = data if isinstance(data, list) else data.get("data", [])
            candidates = [
                v for v in videos if isinstance(v, dict) and v.get("id")
            ]
            if not candidates:
                data = client.json(
                    "GET",
                    f"/api/v2/channels/{channel_id}/videos",
                    params={"limit": 20},
                )
                videos = data if isinstance(data, list) else data.get("data", [])
                candidates = [
                    v for v in videos if isinstance(v, dict) and v.get("id")
                ]
            if not candidates:
                raise RuntimeError(f"channel {channel_id} has no videos")
            index = int(state.get("fan_video_index", 0) or 0) % len(candidates)
            video = candidates[index]
            self.update_state(fan_video_index=(index + 1) % len(candidates))
            target_channel_id = channel_id
            if not isinstance(video.get("channel"), dict):
                video["channel"] = {
                    "id": channel_id,
                    "name": state.get("fan_channel_name") or channel_id,
                }
        else:
            data = client.json("GET", "/api/v2/videos", params={"limit": 20})
            videos = data if isinstance(data, list) else data.get("data", [])
            candidates = [
                v
                for v in videos
                if isinstance(v, dict)
                and v.get("id")
                and isinstance(v.get("channel"), dict)
                and v["channel"].get("id")
            ]
            if not candidates:
                raise RuntimeError("no video with channelId available")
            # Rotate channels/videos: one 5-minute session per channel, then next.
            index = int(state.get("watch_index", 0) or 0) % len(candidates)
            video = candidates[index]
            self.update_state(watch_index=(index + 1) % len(candidates))
            target_channel_id = video["channel"]["id"]
        video_id = video["id"]
        token = client.json("GET", "/api/v2/watch/token")["token"]
        session_id = str(uuid.uuid4())
        base = {
            "sessionId": session_id,
            "channelId": target_channel_id,
            "videoId": video_id,
            "isLive": video.get("status") == "live",
            "_token": token,
        }
        elapsed = 0
        ended = False
        totals = self.load_daily()

        def flush_totals(count_run: bool = False) -> dict[str, Any]:
            nonlocal before, totals
            try:
                current = client.me()
            except Exception:
                return totals
            totals = self.apply_totals(before, current, count_run=count_run)
            before = current
            return totals

        try:
            client.json(
                "POST",
                "/api/v2/watch/event",
                json={**base, "eventType": "watch.start", "currentTime": 0},
            )
            self.update_state(
                current_watch={
                    "videoId": video_id,
                    "title": video.get("title") or video_id,
                    "channelId": target_channel_id,
                    "channelName": video["channel"].get("name") or target_channel_id,
                    "sessionId": session_id,
                    "startedAt": datetime.now(timezone.utc).isoformat(),
                    "elapsed": 0,
                }
            )
            for i in range(5):
                if self.stop_event.wait(60):
                    break
                if not self.feature("watch"):
                    break
                if self.pause_watch.is_set():
                    break
                client.json(
                    "POST",
                    "/api/v2/watch/event",
                    json={
                        **base,
                        "eventType": "watch.keepalive",
                        "currentTime": (i + 1) * 60,
                    },
                )
                elapsed = (i + 1) * 60
                state = self.get_state()
                if state.get("watch_date") != today_utc():
                    state["watch_date"] = today_utc()
                    state["watch_seconds"] = 0
                state["watch_seconds"] = int(state.get("watch_seconds", 0)) + 60
                current_watch = dict(state.get("current_watch") or {})
                current_watch["elapsed"] = elapsed
                self.update_state(
                    watch_date=state["watch_date"],
                    watch_seconds=state["watch_seconds"],
                    current_watch=current_watch,
                )
                # Each keepalive awards EXP immediately; record it now so a
                # daemon restart cannot lose the day's totals.
                flush_totals()
        finally:
            if not ended:
                try:
                    client.json(
                        "POST",
                        "/api/v2/watch/event",
                        json={
                            **base,
                            "eventType": "watch.end",
                            "currentTime": elapsed,
                        },
                    )
                    ended = True
                except Exception:
                    print(f"watch.end failed for session {session_id}", flush=True)
            totals = flush_totals(count_run=True)
            self.update_state(current_watch={})
        if announce and self.feature("notifications"):
            state = self.get_state()
            minutes = int(state.get("watch_seconds", 0)) // 60
            self.send_telegram(
                "👀 Watch session\n"
                f"Video: {video.get('title', video_id)}\n"
                f"Channel: {video['channel'].get('name', channel_id)}\n"
                f"Watch today: {minutes} phút\n"
                f"Today total: +{totals['exp']} EXP, +{totals['coins']} coins, "
                f"+{totals['contribution']} contribution ({totals['runs']} runs)"
            )
        return True
