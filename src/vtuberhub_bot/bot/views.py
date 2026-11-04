"""Read-only Telegram views (profile, leaderboard, content, stats)."""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

from ..config import FAN_BADGE_SECONDS, VN_TZ, WATCH_DEFAULT_LIMIT_HOURS
from ..errors import AccountError
from ..utils import fmt_duration, fmt_epoch, fmt_num, fmt_time, short_text, today_utc


class ViewsMixin:
    def watching_text(self) -> str:
        state = self.get_state()
        current = state.get("current_watch") or {}
        watch_sec = int(state.get("watch_seconds", 0) or 0)
        fan_mode = bool(
            state["features"].get("fan")
            or state["features"].get("fan_multi")
        )
        limit_hours = int(
            state.get("fan_limit_hours", 8)
            if fan_mode
            else state.get("watch_limit_hours", WATCH_DEFAULT_LIMIT_HOURS)
        ) or 6
        limit_sec = max(1, limit_hours) * 3600
        lines = ["👀 Watch status", ""]
        if current.get("videoId"):
            elapsed = int(current.get("elapsed", 0) or 0)
            lines += [
                f"Video: {short_text(current.get('title'), 70)}",
                f"Channel: {short_text(current.get('channelName'), 40)}",
                f"Session: {elapsed // 60} phút (bắt đầu {fmt_time(current.get('startedAt'))})",
            ]
        else:
            lines.append("Hiện không có watch session.")
        if state["features"].get("fan_multi"):
            channels = [
                str(c) for c in (state.get("fan_multi_channels") or []) if c
            ]
            names = dict(state.get("fan_multi_names") or {})
            lines.append(f"Multi-tab: {len(channels)} kênh")
            for cid in channels[:8]:
                lines.append(f"  • {short_text(names.get(cid) or cid, 32)}")
        lines += [
            f"Hôm nay: {watch_sec // 60} phút / {limit_sec // 3600} giờ",
            f"Còn lại: {max(0, limit_sec - watch_sec) // 60} phút",
            f"Video kế tiếp: index {state.get('watch_index', 0)}",
        ]
        return "\n".join(lines)


    def leaderboard_text(
        self, sort_field: str = "exp", scope: str = "all_time", limit: int = 10
    ) -> str:
        client = self.client()
        limit = max(3, min(25, int(limit)))
        data = client.json(
            "GET",
            "/api/v2/leaderboard",
            params={"scope": scope, "limit": limit, "sortField": sort_field},
        )
        rows = data if isinstance(data, list) else data.get("data", data.get("items", []))
        me = client.json(
            "GET",
            "/api/v2/leaderboard/me",
            params={"scope": scope, "sortField": sort_field},
        )
        unit = "EXP" if sort_field == "exp" else "điểm"
        title = "🏆 BXH EXP" if sort_field == "exp" else "🏆 BXH cống hiến"
        scope_label = {
            "weekly": "tuần",
            "monthly": "tháng",
            "all_time": "all-time",
        }.get(scope, scope)
        lines = [f"{title} — {scope_label}", ""]
        for idx, row in enumerate(rows[:limit], 1):
            name = short_text(row.get("displayName") or row.get("username") or "?", 32)
            value = row.get("scopeExp")
            if value is None:
                value = row.get("exp") if sort_field == "exp" else row.get("contribution")
            prestige = int(row.get("prestige") or 0)
            star = f" ★{prestige}" if prestige else ""
            lines.append(
                f"{row.get('rank') or idx}. {name} — {fmt_num(value)} {unit} "
                f"(Lv.{row.get('level', '?')}{star})"
            )
        lines.append("")
        lines.append(
            f"Bạn: #{me.get('rank', '?')} — {fmt_num(me.get('scopeExp', 0))} {unit}"
        )
        return "\n".join(lines)


    def features_text(self) -> str:
        state = self.get_state()
        return (
            "⚙️ Features\n"
            + "\n".join(f"{'✅' if v else '❌'} {k}" for k, v in state["features"].items())
            + "\n\n/on <feature> | /off <feature>\n"
            "/run daily|music|watch|favorite|online|achievements\n"
            "/favorite on|off|run|status\n"
            "/online on|off|run|status\n"
            "/fan status|list|set|search|on|off|next\n"
            "/set watch_limit <hours> | /set fan_limit <hours>\n"
            "/set favorite_rank <1-100> | /set favorite_exp <EXP|0>\n"
            "/set favorite_rpm <10-120> | /set favorite_batch <2-50>\n"
            "/set online_chunk <1-12>"
        )


    def status_text(self) -> str:
        state = self.get_state()
        totals = self.load_daily()
        rank_text = ""
        try:
            client = self.client()
            me = client.me()
            self.accounts.update_profile(me)
            account = (
                f"{me.get('username')} | Lv.{me.get('level')} ★{me.get('prestige')}\n"
                f"EXP {fmt_num(me.get('exp'))} | coins {fmt_num(me.get('coins'))} | "
                f"contribution {fmt_num(me.get('contribution'))}"
            )
            try:
                rank_exp = client.json(
                    "GET", "/api/v2/leaderboard/me",
                    params={"scope": "all_time", "sortField": "exp"},
                )
                rank_contrib = client.json(
                    "GET", "/api/v2/leaderboard/me",
                    params={"scope": "all_time", "sortField": "contribution"},
                )
                rank_text = (
                    f"Rank: EXP #{rank_exp.get('rank', '?')} | "
                    f"contribution #{rank_contrib.get('rank', '?')}\n"
                )
            except Exception:
                pass
        except AccountError as exc:
            account = f"⚠️ {exc}"
        except Exception as exc:
            account = f"login/API error: {exc}"
        current = state.get("current_watch") or {}
        watching = (
            short_text(current.get("title"), 55)
            if current.get("videoId")
            else "không"
        )
        features = "\n".join(
            f"  {'✅' if v else '❌'} {k}" for k, v in state["features"].items()
        )
        fav_exp = int(state.get("favorite_target_exp", 0) or 0)
        if fav_exp > 0:
            fav_target = f"{fav_exp:,} EXP"
        else:
            fav_target = f"rank #{int(state.get('favorite_target_rank', 3) or 3)}"
        fav_state = "on" if state["features"].get("favorite") else "off"
        online_sec = int(state.get("online_seconds", 0) or 0)
        online_total = int(state.get("online_total_seconds", 0) or 0)
        if state.get("online_date") != today_utc():
            online_sec = 0
        online_chunk = max(1, min(12, int(state.get("online_chunk_hours", 6) or 6)))
        fan_on = bool(state["features"].get("fan"))
        fan_name = state.get("fan_channel_name") or "-"
        fan_pct = int(state.get("fan_last_pct", 0) or 0)
        fan_limit = max(1, min(12, int(state.get("fan_limit_hours", 8) or 8)))
        fan_multi_on = bool(state["features"].get("fan_multi"))
        fan_multi_count = len(state.get("fan_multi_channels") or [])
        return (
            "🤖 VTuberVN Auto EXP\n"
            f"Time: {datetime.now(VN_TZ).strftime('%Y-%m-%d %H:%M %Z')}\n"
            f"Active: {self.accounts.active() or 'chưa có'}\n"
            f"Account: {account}\n"
            f"{rank_text}"
            f"Đang xem: {watching}\n"
            f"Today: +{totals['exp']} EXP, +{totals['coins']} coins, "
            f"+{totals['contribution']} contribution ({totals['runs']} runs)\n"
            f"Watch today: {int(state.get('watch_seconds', 0)) // 60} phút\n"
            f"Online: {online_sec / 3600:.1f}h hôm nay | "
            f"tổng {online_total / 3600:.1f}h | chunk {online_chunk}h\n"
            f"Fan: {'on' if fan_on else 'off'} | {short_text(fan_name, 30)} | "
            f"{fan_pct}% / 36h | limit {fan_limit}h\n"
            f"Fan multi: {'on' if fan_multi_on else 'off'} | "
            f"{fan_multi_count} tab\n"
            f"Favorite: {fav_state} | target {fav_target} | "
            f"last {state.get('last_favorite_result') or '-'} "
            f"({int(state.get('last_favorite_exp', 0) or 0):,} EXP)\n"
            f"Features:\n{features}\n"
            f"Last daily: {state.get('last_daily_date') or '-'}\n"
            f"Last music: {state.get('last_music_date') or '-'}"
        )


    def stats_text(self) -> str:
        state = self.get_state()
        totals = self.load_daily()
        uptime = max(0, time.time() - self.started_at)
        hours = int(uptime // 3600)
        minutes = int((uptime % 3600) // 60)
        rss = "?"
        try:
            with open("/proc/self/status", encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("VmRSS:"):
                        rss = line.split(":", 1)[1].strip()
                        break
        except OSError:
            pass
        errors = state.get("last_errors") or {}
        error_text = (
            ", ".join(f"{k}@{fmt_epoch(v)}" for k, v in errors.items())
            if errors
            else "none"
        )
        features = ", ".join(
            f"{k}={'on' if v else 'off'}" for k, v in state["features"].items()
        )
        return (
            "📊 Daemon stats\n"
            f"Uptime: {hours}h {minutes}m | PID {os.getpid()} | RAM {rss}\n"
            f"Account: {self.accounts.active() or 'chưa có'}\n"
            f"Features: {features}\n"
            f"Today: +{fmt_num(totals['exp'])} EXP, +{fmt_num(totals['coins'])} coins, "
            f"+{fmt_num(totals['contribution'])} contribution ({totals['runs']} runs)\n"
            f"Watch: {int(state.get('watch_seconds', 0)) // 60} phút | "
            f"Favorite: {'on' if state['features'].get('favorite') else 'off'} "
            f"(target rank #{state.get('favorite_target_rank', 3)})\n"
            f"Online: {int(state.get('online_seconds', 0)) / 3600:.1f}h hôm nay | "
            f"tổng {int(state.get('online_total_seconds', 0)) / 3600:.1f}h | "
            f"chunk {state.get('online_chunk_hours', 6)}h | "
            f"last {state.get('last_online_result') or '-'}\n"
            f"Fan: {'on' if state['features'].get('fan') else 'off'} | "
            f"{state.get('fan_channel_name') or '-'} | "
            f"{int(state.get('fan_last_pct', 0) or 0)}% / 36h | "
            f"limit {state.get('fan_limit_hours', 8)}h\n"
            f"Fan multi: {'on' if state['features'].get('fan_multi') else 'off'} | "
            f"{len(state.get('fan_multi_channels') or [])} tab\n"
            f"Last errors: {error_text}"
        )


    def videos_text(self, limit: int = 8, live: bool = False) -> str:
        client = self.client()
        limit = max(1, min(20, int(limit)))
        path = "/api/v2/live" if live else "/api/v2/videos"
        data = client.json("GET", path, params={"limit": limit})
        rows = data if isinstance(data, list) else data.get("data", [])
        title = "🔴 Đang live" if live else "🎬 Video mới nhất"
        lines = [title, ""]
        for idx, video in enumerate(rows[:limit], 1):
            ch = video.get("channel") or {}
            status = video.get("status", "?")
            if live:
                extra = f"{fmt_num(video.get('liveViewers'))} viewers"
            else:
                extra = f"{fmt_num(video.get('viewCount'))} views"
            lines.append(
                f"{idx}. {short_text(video.get('title'), 65)}\n"
                f"   {short_text(ch.get('name', '?'), 30)} | {status} | {extra}"
            )
        if not rows:
            lines.append("Không có dữ liệu.")
        return "\n".join(lines)


    def profile_text(self, username: str | None = None) -> str:
        client = self.client()
        me = client.me()
        target = me
        if username and str(username).lower() != str(me.get("username", "")).lower():
            target = client.json("GET", f"/api/v2/users/profile/{username}")
        rank_exp = client.json(
            "GET", "/api/v2/leaderboard/me",
            params={"scope": "all_time", "sortField": "exp"},
        )
        rank_contrib = client.json(
            "GET", "/api/v2/leaderboard/me",
            params={"scope": "all_time", "sortField": "contribution"},
        )
        lines = [
            "👤 Profile",
            f"Username: {target.get('username', '?')}",
            f"Display: {target.get('displayName') or target.get('username', '?')}",
            f"Level: {target.get('level', '?')} ★{target.get('prestige', 0)}",
            f"EXP: {fmt_num(target.get('exp'))}",
            f"Coins: {fmt_num(target.get('coins'))}",
            f"Contribution: {fmt_num(target.get('contribution'))}",
        ]
        if target is me:
            lines += [
                f"Rank EXP: #{rank_exp.get('rank', '?')}",
                f"Rank contribution: #{rank_contrib.get('rank', '?')}",
            ]
            try:
                ach = client.json("GET", "/api/v2/achievements")
                unlocked = sum(1 for a in ach if a.get("unlocked"))
                lines.append(f"Achievements: {unlocked}/{len(ach)}")
            except Exception:
                pass
            try:
                favs = client.json("GET", "/api/v2/users/favorites")
                lines.append(f"Favorites: {len(favs) if isinstance(favs, list) else 0}")
            except Exception:
                pass
            if me.get("loginStreak") is not None:
                lines.append(f"Login streak: {me.get('loginStreak')} ngày")
        if target.get("createdAt"):
            lines.append(f"Joined: {fmt_time(target.get('createdAt'))}")
        return "\n".join(lines)


    def accounts_text(self) -> str:
        try:
            self.accounts.update_profile(self.client().me())
        except Exception:
            pass
        rows = self.accounts.list_accounts()
        if not rows:
            return "👥 Chưa có account nào.\nDùng /login <username> <password>."
        lines = ["👥 Accounts", ""]
        for row in rows:
            mark = "✅" if row["active"] else "•"
            lines.append(
                f"{mark} {row['username']} — Lv.{row.get('level', '?')} | "
                f"EXP {fmt_num(row.get('exp'))} | login {fmt_time(row.get('last_login'))}"
            )
        lines.append("")
        lines.append("Dùng /switch <username> để đổi account.")
        return "\n".join(lines)


    def songs_text(self, limit: int = 10) -> str:
        client = self.client()
        data = client.json("GET", "/api/v2/music/songs", params={"limit": limit})
        rows = data.get("songs", []) if isinstance(data, dict) else data
        total = data.get("total", len(rows)) if isinstance(data, dict) else len(rows)
        lines = [f"🎵 Songs: {fmt_num(total)} bài", ""]
        for idx, song in enumerate(rows[:limit], 1):
            artist = song.get("artist") or (song.get("channel") or {}).get("name") or "?"
            lines.append(
                f"{idx}. {short_text(song.get('title') or song.get('name'), 55)} — "
                f"{short_text(artist, 30)}"
            )
        if not rows:
            lines.append("Live hiện có 0 bài; music farm đang chờ.")
        return "\n".join(lines)


    def timeline_text(self, limit: int = 8) -> str:
        client = self.client()
        data = client.json("GET", "/api/v2/timeline", params={"limit": limit})
        rows = data.get("items", []) if isinstance(data, dict) else data
        total = data.get("total", len(rows)) if isinstance(data, dict) else len(rows)
        lines = [f"📅 Timeline: {fmt_num(total)} event", ""]
        for e in rows[:limit]:
            ch = e.get("channel") or {}
            when = e.get("eventDate") or e.get("createdAt") or e.get("startAt")
            lines.append(
                f"• {short_text(e.get('title') or e.get('eventType') or '?', 55)}"
                f" | {short_text(ch.get('name', ''), 25)} | {fmt_time(when)}"
            )
        if not rows:
            lines.append("Timeline đang trống hoặc module bị tắt.")
        return "\n".join(lines)


    def history_text(self, limit: int = 8) -> str:
        client = self.client()
        limit = max(1, min(20, int(limit)))
        rows = client.json("GET", "/api/v2/history", params={"limit": limit})
        if not isinstance(rows, list):
            rows = []
        ids = [str(r.get("videoId")) for r in rows if r.get("videoId")]
        details: dict[str, dict[str, Any]] = {}
        if ids:
            try:
                videos = client.json("POST", "/api/v2/videos/by-ids", json={"ids": ids})
                if isinstance(videos, list):
                    details = {str(v.get("id")): v for v in videos}
            except Exception:
                pass
        lines = ["🕘 Lịch sử xem", ""]
        for idx, row in enumerate(rows[:limit], 1):
            vid = str(row.get("videoId", "?"))
            video = details.get(vid, {})
            ch = video.get("channel") or {}
            lines.append(
                f"{idx}. {short_text(video.get('title') or vid, 60)}\n"
                f"   {short_text(ch.get('name', '?'), 25)} | {fmt_time(row.get('watchedAt'))}"
            )
        if not rows:
            lines.append("Chưa có lịch sử xem.")
        return "\n".join(lines)


    def ping_text(self) -> str:
        started = time.time()
        client = self.client()
        me = client.me()
        latency = (time.time() - started) * 1000
        return (
            f"🏓 API OK — {latency:.0f} ms\n"
            f"User: {me.get('username')} | Lv.{me.get('level')} | "
            f"EXP {fmt_num(me.get('exp'))} | coins {fmt_num(me.get('coins'))}"
        )


    def favorites_text(self, limit: int = 15) -> str:
        client = self.client()
        rows = client.json("GET", "/api/v2/users/favorites")
        if not isinstance(rows, list):
            rows = []
        lines = [f"⭐ Favorites: {len(rows)} channel", ""]
        for idx, ch in enumerate(rows[:limit], 1):
            lines.append(
                f"{idx}. {short_text(ch.get('name', '?'), 35)} — "
                f"{fmt_num(ch.get('subscriberCount'))} sub"
            )
        if not rows:
            lines.append("Chưa favorite channel nào.")
        return "\n".join(lines)


    def achievements_text(self, mode: str = "summary") -> str:
        client = self.client()
        all_ach = client.json("GET", "/api/v2/achievements")
        if not isinstance(all_ach, list):
            all_ach = []
        unlocked = [a for a in all_ach if a.get("unlocked")]
        locked = [a for a in all_ach if not a.get("unlocked")]
        lines = [f"🏆 Achievements: {len(unlocked)}/{len(all_ach)} đã mở", ""]
        show_unlocked = mode in ("summary", "all", "unlocked")
        show_locked = mode in ("summary", "all", "locked")
        if show_unlocked:
            for a in unlocked[:15]:
                lines.append(
                    f"✅ {a.get('name', '?')} (+{fmt_num(a.get('coinReward'))} coins)"
                )
            if len(unlocked) > 15:
                lines.append(f"... +{len(unlocked) - 15} cái khác")
        if show_locked:
            if show_unlocked:
                lines.append("")
            for a in locked[:15]:
                lines.append(f"🔒 {short_text(a.get('name', '?'), 40)} — {short_text(a.get('description', ''), 70)}")
            if len(locked) > 15:
                lines.append(f"... +{len(locked) - 15} cái khác")
        if not all_ach:
            lines.append("Không đọc được danh sách achievement.")
        return "\n".join(lines)


    def notifications_text(self, limit: int = 8) -> str:
        client = self.client()
        limit = max(1, min(20, int(limit)))
        data = client.json("GET", "/api/v2/notifications", params={"limit": limit})
        rows = data.get("items", []) if isinstance(data, dict) else data
        try:
            unread = client.json("GET", "/api/v2/notifications/unread-count").get("count", 0)
        except Exception:
            unread = "?"
        lines = [f"🔔 Notifications: {unread} chưa đọc", ""]
        for n in rows[:limit]:
            mark = "🔵" if not n.get("isRead") else "⚪"
            lines.append(
                f"{mark} {short_text(n.get('title'), 60)}\n"
                f"   {short_text(n.get('message'), 90)} | {fmt_time(n.get('createdAt'))}"
            )
        if not rows:
            lines.append("Không có thông báo.")
        return "\n".join(lines)


    def channels_text(self, limit: int = 10) -> str:
        client = self.client()
        limit = max(1, min(20, int(limit)))
        rows = client.json(
            "GET",
            "/api/v2/channels",
            params={"limit": limit, "sort": "subscriber_count", "order": "desc"},
        )
        if not isinstance(rows, list):
            rows = rows.get("items", [])
        lines = ["📺 Top channel", ""]
        for idx, ch in enumerate(rows[:limit], 1):
            lines.append(
                f"{idx}. {short_text(ch.get('name', '?'), 35)} — "
                f"{fmt_num(ch.get('subscriberCount'))} sub | "
                f"{fmt_num(ch.get('videoCount'))} video"
            )
        if not rows:
            lines.append("Không có dữ liệu.")
        return "\n".join(lines)
