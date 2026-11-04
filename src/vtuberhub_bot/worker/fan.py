"""Fan badge farming: single target and multi-tab rounds."""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from ..api.client import Client
from ..config import FAN_BADGE_SECONDS
from ..utils import fmt_duration, fmt_num, short_text, today_utc


class FanMixin:
    def do_fan_multi_round(self, client: Client) -> None:
        state = self.get_state()
        channels = [
            str(c) for c in (state.get("fan_multi_channels") or []) if c
        ]
        if not channels:
            self.set_feature("fan_multi", False)
            return
        fan_limit = max(1, min(12, int(state.get("fan_limit_hours", 8) or 8)))
        limit = fan_limit * 3600
        watch_sec = int(state.get("watch_seconds", 0) or 0)
        round_seconds = len(channels) * 300
        if watch_sec + round_seconds > limit:
            self.stop_event.wait(300)
            return
        self.fan_multi_cancel.clear()
        primary = channels[0]
        raw = channels[1:]
        results: dict[str, int] = {}
        threads: list[threading.Thread] = []
        for cid in raw:
            t = threading.Thread(
                target=self._raw_watch_worker,
                args=(cid, 300, results),
                name=f"multi-{cid[:8]}",
                daemon=True,
            )
            t.start()
            threads.append(t)
        try:
            self.do_watch_session(
                announce=False, client=client, channel_id=primary
            )
        finally:
            for t in threads:
                t.join(timeout=360)
        raw_elapsed = sum(int(v or 0) for v in results.values())
        if raw_elapsed:
            state = self.get_state()
            if state.get("watch_date") != today_utc():
                state["watch_date"] = today_utc()
                state["watch_seconds"] = 0
            state["watch_seconds"] = (
                int(state.get("watch_seconds", 0)) + raw_elapsed
            )
            self.update_state(
                watch_date=state["watch_date"],
                watch_seconds=state["watch_seconds"],
            )
        self.update_state(
            fan_multi_last_round=datetime.now(timezone.utc).isoformat()
        )
        self.check_fan_multi_progress(client)


    def start_fan_multi(self, count: int) -> tuple[list[str], dict[str, str], dict[str, int]]:
        count = max(2, min(8, int(count)))
        client = self.client()
        rows = self.fan_rows(client, 100)
        targets = [r for r in rows if not r.get("hasFanBadge")][:count]
        if len(targets) < 2:
            raise RuntimeError("cần ít nhất 2 channel chưa có fan badge")
        channels = [str(r["channelId"]) for r in targets]
        names = {
            str(r["channelId"]): str(r.get("name") or r["channelId"])
            for r in targets
        }
        progress = {
            str(r["channelId"]): min(
                100,
                int(int(r.get("totalSeconds") or 0) * 100 / FAN_BADGE_SECONDS),
            )
            for r in targets
        }
        self.update_state(
            fan_multi_channels=channels,
            fan_multi_names=names,
            fan_multi_progress=progress,
            fan_multi_count=count,
        )
        self.set_feature("fan", False)
        self.set_feature("fan_multi", True)
        self.fan_multi_cancel.clear()
        return channels, names, progress


    def fan_rows(self, client: Client, limit: int = 100) -> list[dict[str, Any]]:
        data = client.json(
            "GET", "/api/v2/watch/top-channels", params={"limit": limit}
        )
        rows = data if isinstance(data, list) else data.get("data", [])
        return [
            row
            for row in rows
            if isinstance(row, dict) and row.get("channelId")
        ]


    def check_fan_multi_progress(self, client: Client) -> None:
        state = self.get_state()
        channels = [
            str(c) for c in (state.get("fan_multi_channels") or []) if c
        ]
        if not channels:
            return
        try:
            rows = self.fan_rows(client, 100)
        except Exception:
            return
        by_id = {str(r.get("channelId")): r for r in rows}
        names = dict(state.get("fan_multi_names") or {})
        progress = dict(state.get("fan_multi_progress") or {})
        remaining = list(channels)
        for cid in list(channels):
            row = by_id.get(cid)
            if not row:
                continue
            total = int(row.get("totalSeconds") or 0)
            pct = min(100, int(total * 100 / FAN_BADGE_SECONDS))
            last = int(progress.get(cid, 0) or 0)
            progress[cid] = pct
            names[cid] = row.get("name") or names.get(cid) or cid
            if row.get("hasFanBadge"):
                if self.feature("notifications"):
                    self.send_telegram(
                        "🎉 Fan cứng unlocked (multi-tab)!\n"
                        f"Channel: {names.get(cid)}\n"
                        f"Tổng watch: {fmt_duration(total)} (>= 36h)"
                    )
                if cid in remaining:
                    remaining.remove(cid)
                progress.pop(cid, None)
                names.pop(cid, None)
            elif pct >= 50 > last and self.feature("notifications"):
                self.send_telegram(
                    "🔥 Fan cứng multi 50%\n"
                    f"Channel: {names.get(cid)}\n"
                    f"Đã xem: {fmt_duration(total)} / 36h"
                )
        self.update_state(
            fan_multi_channels=remaining,
            fan_multi_names=names,
            fan_multi_progress=progress,
        )
        if not remaining:
            self.set_feature("fan_multi", False)
            if self.feature("notifications"):
                self.send_telegram(
                    "🔥 Fan cứng multi-tab: tất cả channel đã đạt badge. "
                    "Đã tắt multi mode."
                )


    def fan_multi_status_text(self) -> str:
        state = self.get_state()
        channels = [
            str(c) for c in (state.get("fan_multi_channels") or []) if c
        ]
        names = dict(state.get("fan_multi_names") or {})
        progress = dict(state.get("fan_multi_progress") or {})
        fan_limit = max(1, min(12, int(state.get("fan_limit_hours", 8) or 8)))
        watch_sec = int(state.get("watch_seconds", 0) or 0)
        lines = [
            "🔥 Fan cứng multi-tab",
            f"State: {'on' if state['features'].get('fan_multi') else 'off'}",
            f"Tabs: {len(channels)} channel",
            "",
        ]
        for cid in channels:
            lines.append(
                f"• {short_text(names.get(cid) or cid, 35)} — "
                f"{int(progress.get(cid, 0) or 0)}% / 36h"
            )
        if not channels:
            lines.append("Chưa có channel nào.")
        remaining_seconds = 0.0
        for cid in channels:
            pct = float(progress.get(cid, 0) or 0)
            remaining_seconds += max(0.0, FAN_BADGE_SECONDS * (100.0 - pct) / 100.0)
        days = remaining_seconds / (fan_limit * 3600) if fan_limit else 0
        lines += [
            "",
            f"Fan limit: {fan_limit}h/ngày (tổng tất cả tab)",
            f"Watch hôm nay: {watch_sec // 60} phút / {fan_limit} giờ",
            f"ETA hoàn tất tất cả: ~{days:.1f} ngày",
            "Mỗi tab 5 phút/round; tổng thời gian = N × 5 phút.",
        ]
        return "\n".join(lines)


    def _raw_watch_worker(
        self, channel_id: str, duration: int, results: dict[str, int]
    ) -> None:
        client: Client | None = None
        base: dict[str, Any] | None = None
        elapsed = 0
        ended = False
        try:
            client = self.client()
            data = client.json(
                "GET",
                "/api/v2/videos",
                params={"channel_id": channel_id, "limit": 1},
            )
            rows = data if isinstance(data, list) else data.get("data", [])
            video = next((v for v in rows if isinstance(v, dict) and v.get("id")), None)
            if not video:
                raise RuntimeError("no video")
            token = client.json("GET", "/api/v2/watch/token")["token"]
            base = {
                "sessionId": str(uuid.uuid4()),
                "channelId": channel_id,
                "videoId": video["id"],
                "isLive": video.get("status") == "live",
                "_token": token,
            }
            client.json(
                "POST",
                "/api/v2/watch/event",
                json={**base, "eventType": "watch.start", "currentTime": 0},
            )
            for i in range(max(1, duration // 60)):
                if self.stop_event.wait(60):
                    break
                if self.fan_multi_cancel.is_set():
                    break
                if not self.feature("watch"):
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
        except Exception as exc:
            print(f"multi watch {channel_id} error: {exc}", flush=True)
        finally:
            try:
                if client is not None and base is not None and not ended:
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
                pass
            results[channel_id] = elapsed


    def set_fan_target(self, arg: str) -> tuple[str, str, int, int]:
        arg = (arg or "").strip()
        if not arg:
            raise RuntimeError("Dùng /fan set <số|channel_id|tên>")
        client = self.client()
        row: dict[str, Any] | None = None
        if arg.isdigit():
            rows = self.fan_rows(client, 100)
            idx = int(arg) - 1
            if 0 <= idx < len(rows):
                row = rows[idx]
        elif arg.upper().startswith("UC") or len(arg) > 20:
            try:
                ch = client.json("GET", f"/api/v2/channels/{arg}")
                row = {
                    "channelId": ch.get("id") or arg,
                    "name": ch.get("name") or arg,
                    "totalSeconds": 0,
                    "hasFanBadge": False,
                }
            except Exception:
                row = None
        if row is None:
            q = arg.lower()
            try:
                rows = self.fan_rows(client, 100)
            except Exception:
                rows = []
            row = next(
                (r for r in rows if q in str(r.get("name") or "").lower()),
                None,
            )
        if row is None:
            try:
                channels = client.channels()
            except Exception:
                channels = []
            match = next(
                (c for c in channels if q in str(c.get("name") or "").lower()),
                None,
            )
            if match:
                row = {
                    "channelId": match.get("id"),
                    "name": match.get("name"),
                    "totalSeconds": 0,
                    "hasFanBadge": False,
                }
        if not row or not row.get("channelId"):
            raise RuntimeError("không tìm thấy channel")
        cid = str(row["channelId"])
        name = str(row.get("name") or cid)
        total = int(row.get("totalSeconds") or 0)
        pct = min(100, int(total * 100 / FAN_BADGE_SECONDS))
        self.update_state(
            fan_channel_id=cid,
            fan_channel_name=name,
            fan_last_pct=pct,
            fan_badge_notified=False,
            fan_video_index=0,
        )
        self.set_feature("fan_multi", False)
        self.fan_multi_cancel.set()
        self.set_feature("fan", True)
        return cid, name, total, pct


    def stop_fan_multi(self) -> None:
        self.set_feature("fan_multi", False)
        self.fan_multi_cancel.set()


    def search_channels_text(self, query: str, limit: int = 10) -> str:
        q = (query or "").strip().lower()
        if not q:
            return "Dùng: /fan search <tên channel>"
        client = self.client()
        channels = client.channels()
        matches = [
            c for c in channels if q in str(c.get("name") or "").lower()
        ][:limit]
        lines = [f"🔍 Channel khớp '{query}'", ""]
        for c in matches:
            lines.append(
                f"• {short_text(c.get('name'), 40)} — {c.get('id')} "
                f"({fmt_num(c.get('subscriberCount'))} sub)"
            )
        if not matches:
            lines.append("Không tìm thấy.")
        return "\n".join(lines)


    def pick_fan_target(
        self, client: Client, exclude: str | None = None
    ) -> dict[str, Any]:
        for row in self.fan_rows(client, 100):
            cid = str(row.get("channelId") or "")
            if not cid or row.get("hasFanBadge"):
                continue
            if exclude and cid == exclude:
                continue
            return row
        raise RuntimeError("không còn channel nào chưa đạt fan badge trong top watch")


    def fan_status_text(self) -> str:
        state = self.get_state()
        target = (state.get("fan_channel_id") or "").strip()
        name = state.get("fan_channel_name") or "-"
        pct = int(state.get("fan_last_pct", 0) or 0)
        fan_limit = max(1, min(12, int(state.get("fan_limit_hours", 8) or 8)))
        watch_sec = int(state.get("watch_seconds", 0) or 0)
        limit_sec = max(1, fan_limit) * 3600
        total = None
        if target:
            try:
                rows = self.fan_rows(self.client(), 100)
                row = next(
                    (r for r in rows if str(r.get("channelId")) == target),
                    None,
                )
                if row:
                    total = int(row.get("totalSeconds") or 0)
                    pct = min(100, int(total * 100 / FAN_BADGE_SECONDS))
            except Exception:
                pass
        lines = [
            "🔥 Fan cứng",
            f"State: {'on' if state['features'].get('fan') else 'off'}",
            f"Target: {short_text(name, 40)} ({target or '-'})",
            f"Progress: {pct}% / 36h",
        ]
        if total is not None:
            remaining = max(0, FAN_BADGE_SECONDS - total)
            days = remaining / (fan_limit * 3600) if fan_limit else 0
            lines.append(f"Đã xem: {fmt_duration(total)} / 36h")
            lines.append(f"ETA: ~{days:.1f} ngày ({fan_limit}h/ngày)")
        lines += [
            f"Fan limit: {fan_limit}h/ngày",
            f"Watch hôm nay: {watch_sec // 60} phút / {fan_limit} giờ",
            f"Auto-next: {'on' if state.get('fan_auto_next', True) else 'off'}",
            "UI web hiển thị 24h; badge thật ở 36h.",
        ]
        return "\n".join(lines)


    def fan_list_text(self, limit: int = 15) -> str:
        client = self.client()
        rows = self.fan_rows(client, 100)
        lines = ["🔥 Fan cứng — top channel đã xem", ""]
        for idx, row in enumerate(rows[:limit], 1):
            total = int(row.get("totalSeconds") or 0)
            pct = min(100.0, total * 100.0 / FAN_BADGE_SECONDS)
            if row.get("hasFanBadge"):
                state_text = "✅ Fan cứng"
            else:
                state_text = f"{pct:.1f}% / 36h"
            lines.append(
                f"{idx}. {short_text(row.get('name'), 35)} — "
                f"{fmt_duration(total)} ({state_text})"
            )
        if not rows:
            lines.append("Chưa có dữ liệu watch.")
        lines.append("")
        lines.append("UI web hiển thị mốc 24h; badge thật grant ở 36h.")
        lines.append("Dùng /fan set <số> hoặc /fan search <tên>.")
        return "\n".join(lines)


    def check_fan_progress(self, client: Client, channel_id: str) -> None:
        state = self.get_state()
        try:
            rows = self.fan_rows(client, 100)
        except Exception:
            return
        row = next(
            (r for r in rows if str(r.get("channelId")) == str(channel_id)),
            None,
        )
        if not row:
            return
        total = int(row.get("totalSeconds") or 0)
        badge = bool(row.get("hasFanBadge"))
        pct = min(100.0, total * 100.0 / FAN_BADGE_SECONDS)
        last_pct = int(state.get("fan_last_pct", 0) or 0)
        name = row.get("name") or state.get("fan_channel_name") or channel_id
        self.update_state(
            fan_last_pct=int(pct),
            fan_last_check=datetime.now(timezone.utc).isoformat(),
        )
        for milestone in (10, 25, 50, 75, 90):
            if pct >= milestone > last_pct and self.feature("notifications"):
                self.send_telegram(
                    f"🔥 Fan cứng {milestone}%\n"
                    f"Channel: {name}\n"
                    f"Đã xem: {fmt_duration(total)} / 36h\n"
                    f"Còn: {fmt_duration(max(0, FAN_BADGE_SECONDS - total))}"
                )
        if badge:
            if not state.get("fan_badge_notified"):
                self.update_state(fan_badge_notified=True)
                if self.feature("notifications"):
                    self.send_telegram(
                        "🎉 Fan cứng unlocked!\n"
                        f"Channel: {name}\n"
                        f"Tổng watch: {fmt_duration(total)} (>= 36h)\n"
                        f"Badge đã được server cấp."
                    )
                if self.get_state().get("fan_auto_next", True):
                    try:
                        nxt = self.pick_fan_target(client, exclude=channel_id)
                        ntotal = int(nxt.get("totalSeconds") or 0)
                        self.update_state(
                            fan_channel_id=nxt["channelId"],
                            fan_channel_name=nxt.get("name") or nxt["channelId"],
                            fan_last_pct=min(
                                100, int(ntotal * 100 / FAN_BADGE_SECONDS)
                            ),
                            fan_badge_notified=False,
                            fan_video_index=0,
                        )
                        if self.feature("notifications"):
                            self.send_telegram(
                                "🔥 Fan cứng — target tiếp theo\n"
                                f"Channel: {nxt.get('name')} ({nxt['channelId']})\n"
                                f"Đã xem: {fmt_duration(ntotal)} / 36h"
                            )
                    except Exception as exc:
                        self.set_feature("fan", False)
                        self.update_state(fan_channel_id="", fan_channel_name="")
                        if self.feature("notifications"):
                            self.send_telegram(
                                "🔥 Fan cứng: không còn channel chưa badge. "
                                f"Đã tắt fan mode ({short_text(exc, 80)})."
                            )
                else:
                    self.set_feature("fan", False)
                    self.update_state(fan_channel_id="", fan_channel_name="")
                    if self.feature("notifications"):
                        self.send_telegram(
                            "🔥 Fan cứng xong. Đã tắt fan mode (auto-next off)."
                        )
        elif total >= FAN_BADGE_SECONDS and not state.get("fan_badge_notified"):
            # The server grants on affinity sync; if the top-channels cache is
            # slightly stale, keep the target for one more session.
            if self.feature("notifications"):
                self.send_telegram(
                    "🔥 Fan cứng: đã đủ 36h, chờ server grant badge...\n"
                    f"Channel: {name}"
                )
            self.update_state(fan_badge_notified=True)
