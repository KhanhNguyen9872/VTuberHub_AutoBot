"""Telegram command dispatcher."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..accounts import token_expiry
from ..config import FAN_BADGE_SECONDS, VN_TZ
from ..errors import AccountError
from ..telegram import telegram_send_to
from ..utils import fmt_duration, fmt_num, fmt_time, short_text, today_utc


class CommandsMixin:
    def token_login_reply(self, token: str) -> str:
        token = (token or "").strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
        try:
            account = self.accounts.login_with_token(
                token, make_active=False
            )
            self.switch_account(account["username"])
            self.pause_watch.clear()
            self.favorite_cancel.clear()
            expiry = token_expiry(token)
            expiry_text = ""
            if expiry is not None:
                expiry_text = (
                    "\nToken hết hạn: "
                    + expiry.astimezone(VN_TZ).strftime("%d/%m %H:%M")
                )
            return (
                f"✅ Đã login bằng token: {account['username']}\n"
                f"Lv.{account.get('level')} | EXP {fmt_num(account.get('exp'))}"
                f"{expiry_text}\n"
                "Dùng /accounts để xem list.\n"
                "(Nên xóa tin nhắn chứa token.)"
            )
        except AccountError as exc:
            return f"❌ {exc}"

    def handle_command(self, text: str, chat_id: str) -> None:
        try:
            reply = self._dispatch_command(text)
        except AccountError as exc:
            reply = f"❌ {exc}"
        except Exception as exc:
            reply = f"❌ Lỗi: {type(exc).__name__}: {exc}"
        if reply:
            # Command replies always go back to the allowed chat, even when
            # automatic notifications are disabled.
            telegram_send_to(chat_id, reply)


    def _dispatch_command(self, text: str) -> str:
        raw = (text or "").strip()
        if not raw:
            return ""
        parts = raw.split()
        cmd = parts[0].lower().split("@")[0]
        arg = parts[1].lower() if len(parts) > 1 else ""
        canonical = {"fav": "favorite", "favorites": "favorite"}.get(arg, arg)

        if cmd in ("/start", "/help", "/menu"):
            reply = (
                "🤖 VTuberVN Auto EXP bot\n"
                "Ai cũng có thể dùng; mỗi người có account/state riêng.\n"
                "/help — trợ giúp đầy đủ\n\n"
                "📊 Xem dữ liệu\n"
                "/status — account + tổng hôm nay + features\n"
                "/profile [username] — hồ sơ, level, EXP, rank\n"
                "/rank [exp|contribution] [week|month|all] [N] — BXH\n"
                "/watching — đang xem video nào\n"
                "/achievements [all|unlocked|locked] — thành tựu\n"
                "/videos [N] — video mới nhất\n"
                "/live [N] — đang live\n"
                "/channels [N] — top channel\n"
                "/songs [N] — bài hát\n"
                "/notifications [N] — thông báo web\n"
                "/timeline [N] — timeline\n"
                "/favorites [N] — channel đã favorite\n"
                "/history [N] — lịch sử xem\n"
                "/stats — uptime, RAM, lỗi gần nhất\n"
                "/ping — kiểm tra API\n\n"
                "👥 Account\n"
                "/login <username> <password> — thêm/đăng nhập account\n"
                "/login token <jwt> | /token <jwt> — login bằng token browser (bỏ qua captcha)\n"
                "/logout [username] — xoá account khỏi list switch\n"
                "/switch <username> — đổi account\n"
                "/accounts — danh sách account\n"
                "/whoami — account đang dùng\n\n"
                "⚙️ Điều khiển\n"
                "/features — bật/tắt từng tính năng\n"
                "/on <feature> | /off <feature> — daily, music, watch, emoji, favorite, online, achievements, notifications\n"
                "/run all|daily|music|watch|favorite|online|achievements — chạy ngay\n"
                "/favorite on|off|run|status — farm EXP bằng favorite\n"
                "/online on|off|run|status — presence online cho achievement online_10h/100h\n"
                "/fan status|list|set|search|on|off|next — cày fan cứng 36h/channel\n"
                "/fan multi <2-8>|off|status — watch nhiều tab nhiều channel\n"
                "/set watch_limit <hours>\n"
                "/set favorite_rank <1-100> | /set favorite_exp <EXP|0>\n"
                "/set favorite_rpm <10-120> | /set favorite_batch <2-50>\n"
                "/set online_chunk <1-12> — giờ mỗi lần giữ socket\n"
                "/set fan_limit <1-12> — giờ watch/ngày cho fan mode"
            )
        elif cmd in ("/status", "/info"):
            reply = self.status_text()
        elif cmd == "/features":
            reply = self.features_text()
        elif cmd in ("/rank", "/top", "/bxh", "/leaderboard"):
            sort_field = "exp"
            scope = "all_time"
            limit = 10
            for token in parts[1:]:
                t = token.lower()
                if t in ("exp", "contribution"):
                    sort_field = t
                elif t in ("week", "weekly", "tuan", "tuần"):
                    scope = "weekly"
                elif t in ("month", "monthly", "thang", "tháng"):
                    scope = "monthly"
                elif t in ("all", "all_time", "alltime"):
                    scope = "all_time"
                elif t.isdigit():
                    limit = int(t)
            reply = self.leaderboard_text(sort_field, scope, limit)
        elif cmd in ("/profile", "/me", "/acc"):
            reply = self.profile_text(parts[1] if len(parts) > 1 else None)
        elif cmd in ("/watching", "/watchstatus", "/dangxem"):
            reply = self.watching_text()
        elif cmd in ("/achievements", "/achi"):
            mode = arg if arg in ("all", "unlocked", "locked") else "summary"
            reply = self.achievements_text(mode)
        elif cmd in ("/videos", "/video"):
            reply = self.videos_text(int(arg) if arg.isdigit() else 8, live=False)
        elif cmd == "/live":
            reply = self.videos_text(int(arg) if arg.isdigit() else 8, live=True)
        elif cmd in ("/channels", "/channel"):
            reply = self.channels_text(int(arg) if arg.isdigit() else 10)
        elif cmd in ("/songs", "/music"):
            reply = self.songs_text(int(arg) if arg.isdigit() else 10)
        elif cmd in ("/notifications", "/noti"):
            reply = self.notifications_text(int(arg) if arg.isdigit() else 8)
        elif cmd == "/timeline":
            reply = self.timeline_text(int(arg) if arg.isdigit() else 8)
        elif cmd in ("/favorites", "/favs"):
            reply = self.favorites_text(int(arg) if arg.isdigit() else 15)
        elif cmd == "/history":
            reply = self.history_text(int(arg) if arg.isdigit() else 8)
        elif cmd in ("/stats", "/health"):
            reply = self.stats_text()
        elif cmd == "/ping":
            reply = self.ping_text()
        elif cmd == "/accounts":
            reply = self.accounts_text()
        elif cmd == "/whoami":
            reply = self.profile_text()
        elif cmd in ("/token", "/logintoken"):
            token_parts = raw.split(maxsplit=1)
            if len(token_parts) < 2 or not token_parts[1].strip():
                reply = "Dùng: /token <jwt> (lấy token trong browser)"
            else:
                reply = self.token_login_reply(token_parts[1].strip())
        elif cmd == "/login":
            login_parts = raw.split(maxsplit=2)
            second = login_parts[1].strip() if len(login_parts) > 1 else ""
            if len(login_parts) >= 3 and second.lower() == "token":
                reply = self.token_login_reply(login_parts[2].strip())
            elif (
                len(login_parts) >= 2
                and second.startswith("eyJ")
                and second.count(".") == 2
            ):
                reply = self.token_login_reply(second)
            elif len(login_parts) < 3:
                reply = (
                    "Dùng: /login <username> <password>\n"
                    "Hoặc: /login token <jwt>"
                )
            else:
                username, password = login_parts[1].strip(), login_parts[2]
                account = self.accounts.login(username, password, make_active=False)
                self.switch_account(username)
                self.pause_watch.clear()
                self.favorite_cancel.clear()
                reply = (
                    f"✅ Đã login và switch sang {account.get('username')}\n"
                    f"Lv.{account.get('level')} | EXP {fmt_num(account.get('exp'))}\n"
                    "Dùng /accounts để xem list.\n"
                    "(Nên xóa tin nhắn chứa password.)"
                )
        elif cmd == "/logout":
            username = (parts[1] if len(parts) > 1 else self.accounts.active()).strip()
            if not username:
                reply = "Chưa có account nào để logout."
            else:
                active_before = self.accounts.active()
                if username == active_before:
                    self.pause_watch.set()
                    self.favorite_cancel.set()
                    self.online_cancel.set()
                new_active = self.accounts.logout(username)
                if username == active_before:
                    if new_active:
                        self.switch_account(new_active)
                        reply = (
                            f"✅ Đã logout {username}.\n"
                            f"Đã switch sang {new_active}."
                        )
                    else:
                        self.update_state(active_account="", current_watch={})
                        self.watch_client = None
                        reply = (
                            f"✅ Đã logout {username}.\n"
                            "Không còn account nào; dùng /login để thêm."
                        )
                else:
                    reply = f"✅ Đã xoá {username} khỏi list switch."
        elif cmd == "/switch":
            if not arg:
                reply = self.accounts_text()
            else:
                self.switch_account(arg)
                account = self.accounts.get(arg)
                reply = (
                    f"✅ Đã switch sang {account.get('username')}\n"
                    f"Lv.{account.get('level')} | EXP {fmt_num(account.get('exp'))}"
                )
        elif cmd == "/fan":
            sub = arg or "status"
            state = self.get_state()
            if sub == "multi":
                action = (parts[2].lower() if len(parts) > 2 else "status")
                if action.isdigit():
                    try:
                        channels, names, progress = self.start_fan_multi(
                            int(action)
                        )
                        lines = [f"🔥 Fan multi-tab: {len(channels)} tabs"]
                        for cid in channels:
                            lines.append(
                                f"• {names[cid]} — {progress[cid]}% / 36h"
                            )
                        lines.append(
                            f"Fan limit: {state.get('fan_limit_hours', 8)}h/ngày tổng"
                        )
                        lines.append(
                            "Mỗi tab 5 phút/round; tổng thời gian = N × 5 phút."
                        )
                        reply = "\n".join(lines)
                    except Exception as exc:
                        reply = f"❌ {exc}"
                elif action in ("off", "stop"):
                    self.stop_fan_multi()
                    reply = (
                        "⏹ Fan multi-tab off. Round hiện tại sẽ kết thúc "
                        "trong tối đa 5 phút."
                    )
                elif action in ("status", "info", "list"):
                    reply = self.fan_multi_status_text()
                else:
                    reply = (
                        "Dùng: /fan multi <2-8> | /fan multi off | "
                        "/fan multi status"
                    )
            elif sub in ("status", "info"):
                if state["features"].get("fan_multi"):
                    reply = self.fan_multi_status_text()
                else:
                    reply = self.fan_status_text()
            elif sub == "list":
                limit = (
                    int(parts[2])
                    if len(parts) > 2 and parts[2].isdigit()
                    else 15
                )
                reply = self.fan_list_text(limit)
            elif sub == "search":
                query = " ".join(parts[2:])
                reply = self.search_channels_text(query)
            elif sub == "set":
                target = " ".join(parts[2:])
                try:
                    cid, name, total, pct = self.set_fan_target(target)
                    reply = (
                        f"🔥 Fan target: {name} ({cid})\n"
                        f"Đã xem: {fmt_duration(total)} / 36h ({pct}%)\n"
                        f"Fan mode: on | limit {state.get('fan_limit_hours', 8)}h/ngày"
                    )
                except Exception as exc:
                    reply = f"❌ {exc}"
            elif sub == "on":
                self.set_feature("fan_multi", False)
                self.fan_multi_cancel.set()
                self.set_feature("fan", True)
                if not state.get("fan_channel_id"):
                    try:
                        row = self.pick_fan_target(self.client())
                        cid = str(row["channelId"])
                        total = int(row.get("totalSeconds") or 0)
                        self.update_state(
                            fan_channel_id=cid,
                            fan_channel_name=row.get("name") or cid,
                            fan_last_pct=min(
                                100, int(total * 100 / FAN_BADGE_SECONDS)
                            ),
                            fan_badge_notified=False,
                            fan_video_index=0,
                        )
                        reply = (
                            f"🔥 Fan mode on — target {row.get('name')} "
                            f"({fmt_duration(total)}/36h)"
                        )
                    except Exception as exc:
                        self.set_feature("fan", False)
                        reply = f"❌ Không chọn được target: {exc}"
                else:
                    reply = "🔥 Fan mode on."
            elif sub == "off":
                self.set_feature("fan", False)
                reply = "⏹ Fan mode off. Watch quay lại rotation bình thường."
            elif sub == "next":
                try:
                    row = self.pick_fan_target(
                        self.client(),
                        exclude=state.get("fan_channel_id"),
                    )
                    cid = str(row["channelId"])
                    total = int(row.get("totalSeconds") or 0)
                    self.update_state(
                        fan_channel_id=cid,
                        fan_channel_name=row.get("name") or cid,
                        fan_last_pct=min(
                            100, int(total * 100 / FAN_BADGE_SECONDS)
                        ),
                        fan_badge_notified=False,
                        fan_video_index=0,
                    )
                    self.set_feature("fan_multi", False)
                    self.fan_multi_cancel.set()
                    self.set_feature("fan", True)
                    reply = (
                        f"🔥 Target tiếp theo: {row.get('name')} "
                        f"({fmt_duration(total)}/36h)"
                    )
                except Exception as exc:
                    reply = f"❌ {exc}"
            elif sub == "autonext":
                val = (parts[2] if len(parts) > 2 else "").lower()
                if val in ("on", "off"):
                    self.update_state(fan_auto_next=(val == "on"))
                    reply = f"✅ Fan auto-next = {val}"
                else:
                    reply = "Dùng: /fan autonext on|off"
            else:
                reply = (
                    "Dùng: /fan status | /fan list [N] | "
                    "/fan set <số|channel_id|tên> | /fan search <tên> | "
                    "/fan on|off|next | /fan autonext on|off"
                )
        elif cmd == "/favorite":
            sub = arg or "status"
            state = self.get_state()
            fav_exp = int(state.get("favorite_target_exp", 0) or 0)
            if sub == "on":
                self.set_feature("favorite", True)
                self.request_favorite_farm(announce=True, auto_disable=True)
                reply = "⭐ Bật favorite — đang farm tới target..."
            elif sub == "off":
                self.set_feature("favorite", False)
                self.favorite_cancel.set()
                reply = "❌ Tắt favorite — đã dừng farm."
            elif sub in ("run", "now"):
                self.request_favorite_farm(announce=True, auto_disable=False)
                reply = "⏳ Đang chạy favorite farm tới target..."
            elif sub in ("status", "info"):
                try:
                    me = self.client().me()
                    current = f"{fmt_num(me.get('exp'))} EXP"
                except Exception as exc:
                    current = f"error: {exc}"
                if fav_exp > 0:
                    target = f"{fmt_num(fav_exp)} EXP"
                else:
                    target = f"rank #{int(state.get('favorite_target_rank', 3) or 3)}"
                reply = (
                    "⭐ Favorite farm\n"
                    f"State: {'on' if state['features'].get('favorite') else 'off'}\n"
                    f"Target: {target}\n"
                    f"Current: {current}\n"
                    f"Last: {state.get('last_favorite_result') or '-'} "
                    f"({fmt_num(state.get('last_favorite_exp'))} EXP)\n"
                    f"Rate: {state.get('favorite_rpm', 60)} req/min | "
                    f"batch {state.get('favorite_batch', 50)} ops"
                )
            else:
                reply = "Dùng: /favorite on|off|run|status"
        elif cmd == "/online":
            sub = arg or "status"
            state = self.get_state()
            if sub == "on":
                self.set_feature("online", True)
                self.online_cancel.clear()
                self.run_task("online", self.do_online_session)
                reply = "🟢 Bật online presence — bắt đầu giữ socket..."
            elif sub == "off":
                self.set_feature("online", False)
                self.online_cancel.set()
                reply = "⏹ Tắt online presence — socket sẽ đóng."
            elif sub in ("run", "test"):
                if state.get("online_running"):
                    reply = (
                        "🟢 Session online đang chạy; giờ online sẽ được server "
                        "cộng khi chunk kết thúc."
                    )
                else:
                    self.run_task(
                        "online",
                        self.do_online_session,
                        duration_seconds=70,
                        announce=True,
                    )
                    reply = "⏳ Test online presence 70 giây..."
            elif sub in ("status", "info"):
                chunk = max(
                    1, min(12, int(state.get("online_chunk_hours", 6) or 6))
                )
                online_sec = int(state.get("online_seconds", 0) or 0)
                total_sec = int(state.get("online_total_seconds", 0) or 0)
                if state.get("online_date") != today_utc():
                    online_sec = 0
                with self.task_lock:
                    running = "online" in self.running_tasks
                started = state.get("online_started_at") or ""
                if state.get("online_running"):
                    running = True
                if running and started:
                    try:
                        started_dt = datetime.fromisoformat(
                            str(started).replace("Z", "+00:00")
                        )
                        live_sec = max(
                            0, int((datetime.now(timezone.utc) - started_dt).total_seconds())
                        )
                        online_sec += live_sec
                        total_sec += live_sec
                    except Exception:
                        pass
                reply = (
                    "🟢 Online presence\n"
                    f"State: {'on' if state['features'].get('online') else 'off'}\n"
                    f"Session: {'running từ ' + fmt_time(started) if running and started else ('running' if running else 'idle')}\n"
                    f"Hôm nay: {online_sec / 3600:.1f} giờ | "
                    f"Tổng: {total_sec / 3600:.1f} giờ\n"
                    f"Chunk: {chunk} giờ/lần | "
                    f"Last: {state.get('last_online_result') or '-'}\n"
                    "Mốc: online_10h = 10h, online_100h = 100h"
                )
            else:
                reply = "Dùng: /online on|off|run|status"
        elif cmd in ("/on", "/off"):
            if not arg:
                reply = "Dùng: /on daily | /off music ... | /on all"
            elif arg == "all":
                enabled = cmd == "/on"
                for feature in (
                    "daily",
                    "music",
                    "watch",
                    "favorite",
                    "online",
                    "achievements",
                    "notifications",
                ):
                    self.set_feature(feature, enabled)
                if enabled:
                    self.online_cancel.clear()
                    self.request_favorite_farm(announce=True, auto_disable=True)
                else:
                    self.favorite_cancel.set()
                    self.online_cancel.set()
                reply = f"{'✅ Bật' if enabled else '❌ Tắt'} tất cả tính năng auto."
            elif not self.set_feature(arg, cmd == "/on"):
                reply = f"Không có feature: {arg}"
            else:
                reply = f"{'✅ Bật' if cmd == '/on' else '❌ Tắt'} {arg}"
                if canonical == "favorite":
                    if cmd == "/on":
                        self.request_favorite_farm(announce=True, auto_disable=True)
                        reply += "\n⭐ Favorite farm đang chạy tới target."
                    else:
                        self.favorite_cancel.set()
                        reply += "\n⏹ Đã dừng favorite farm."
                elif canonical == "online":
                    if cmd == "/on":
                        self.online_cancel.clear()
                        self.run_task("online", self.do_online_session)
                        reply += "\n🟢 Online presence sẽ chạy."
                    else:
                        self.online_cancel.set()
                        reply += "\n⏹ Đã dừng online presence."
                elif arg in ("watch", "emoji") and cmd == "/on":
                    reply += "\nThread tương ứng sẽ tự chạy."
        elif cmd == "/run":
            if arg == "all":
                self.run_task("all", self.do_run_all)
                reply = "⏳ Đang chạy all: daily → music → achievements → favorite → online → watch..."
            elif arg in ("daily", "login"):
                self.run_task("daily", self.do_daily)
                reply = "⏳ Đang chạy daily login..."
            elif arg in ("music", "song", "songs"):
                self.run_task("music", self.do_music)
                reply = "⏳ Đang chạy music farm..."
            elif arg in ("watch", "xem"):
                self.run_task("watch", self.do_watch_session)
                reply = "⏳ Đang chạy một watch session..."
            elif arg in ("favorite", "fav", "favorites"):
                self.request_favorite_farm(announce=True, auto_disable=False)
                reply = "⏳ Đang chạy favorite farm tới target..."
            elif arg in ("online", "presence"):
                if self.get_state().get("online_running"):
                    reply = (
                        "🟢 Session online đang chạy; không mở thêm connection. "
                        "Giờ online sẽ cộng khi chunk kết thúc."
                    )
                else:
                    self.run_task(
                        "online",
                        self.do_online_session,
                        duration_seconds=70,
                        announce=True,
                    )
                    reply = "⏳ Test online presence 70 giây..."
            elif arg in ("achievements", "achievement", "achi"):
                self.run_task("achievements", self.do_achievements)
                reply = "⏳ Đang check achievements (socket ~65s)..."
            else:
                reply = "Dùng: /run all|daily|music|watch|favorite|online|achievements"
        elif cmd == "/set":
            if arg == "watch_limit":
                if len(parts) < 3 or not parts[2].isdigit():
                    reply = "Dùng: /set watch_limit 6"
                else:
                    hours = max(1, min(12, int(parts[2])))
                    self.update_state(watch_limit_hours=hours)
                    reply = f"✅ Watch limit = {hours} giờ/ngày"
            elif arg == "favorite_rank":
                if len(parts) < 3 or not parts[2].isdigit():
                    reply = "Dùng: /set favorite_rank 3"
                else:
                    rank = max(1, min(100, int(parts[2])))
                    self.update_state(favorite_target_rank=rank, favorite_target_exp=0)
                    reply = f"✅ Favorite target = top {rank}"
            elif arg == "favorite_exp":
                if len(parts) < 3 or not parts[2].isdigit():
                    reply = "Dùng: /set favorite_exp 22201 (0 = dùng rank)"
                else:
                    exp = max(0, int(parts[2]))
                    self.update_state(favorite_target_exp=exp)
                    reply = (
                        f"✅ Favorite target = {fmt_num(exp)} EXP"
                        if exp > 0
                        else "✅ Favorite target = theo rank"
                    )
            elif arg == "favorite_rpm":
                if len(parts) < 3 or not parts[2].isdigit():
                    reply = "Dùng: /set favorite_rpm 60 (10-120)"
                else:
                    rpm = max(10, min(120, int(parts[2])))
                    self.update_state(favorite_rpm=rpm)
                    reply = f"✅ Favorite rate = {rpm} req/min"
            elif arg == "favorite_batch":
                if len(parts) < 3 or not parts[2].isdigit():
                    reply = "Dùng: /set favorite_batch 50 (2-50)"
                else:
                    batch = max(2, min(50, int(parts[2])))
                    if batch % 2:
                        batch -= 1
                    self.update_state(favorite_batch=batch)
                    reply = f"✅ Favorite batch = {batch} ops"
            elif arg == "online_chunk":
                if len(parts) < 3 or not parts[2].isdigit():
                    reply = "Dùng: /set online_chunk 6 (1-12)"
                else:
                    hours = max(1, min(12, int(parts[2])))
                    self.update_state(online_chunk_hours=hours)
                    reply = f"✅ Online chunk = {hours} giờ/lần"
            elif arg == "fan_limit":
                if len(parts) < 3 or not parts[2].isdigit():
                    reply = "Dùng: /set fan_limit 8 (1-12)"
                else:
                    hours = max(1, min(12, int(parts[2])))
                    self.update_state(fan_limit_hours=hours)
                    reply = f"✅ Fan limit = {hours}h/ngày"
                    if hours > 8:
                        reply += "\n⚠️ >8h sẽ có warning anti-cheat; >12h bị flag."
            else:
                reply = (
                    "Dùng: /set watch_limit 6 | /set favorite_rank 3 | "
                    "/set favorite_exp 22201 | /set favorite_rpm 60 | "
                    "/set favorite_batch 50 | /set online_chunk 6 | /set fan_limit 8"
                )
        else:
            reply = "Lệnh không hợp lệ. Dùng /help."
        return reply
