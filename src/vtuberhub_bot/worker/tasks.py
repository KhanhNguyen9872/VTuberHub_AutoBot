"""Daily login, music, achievements and one-shot tasks."""
from __future__ import annotations

import random
from datetime import datetime, timezone

from ..api.achievements import achievement_snapshot, report_achievements
from ..api.music import music_farm
from ..config import MUSIC_CAP, VN_TZ
from ..features.presence import trigger_achievements
from ..utils import fmt_num, short_text, today_utc
from .base import serialized


class TasksMixin:
    @serialized
    def do_run_all(self, announce: bool = True) -> bool:
        results: list[str] = []
        state = self.get_state()
        if not self.accounts.active():
            raise RuntimeError("chưa có account active; dùng /login")
        if self.feature("daily") and state.get("last_daily_date") != today_utc():
            try:
                self.do_daily(announce=False)
                results.append("daily ✅")
            except Exception as exc:
                results.append(f"daily ❌ {short_text(exc, 80)}")
        else:
            results.append("daily ⏭️")
        if self.feature("music"):
            try:
                if self.client().songs():
                    self.do_music(announce=False)
                    results.append("music ✅")
                else:
                    results.append("music ⏭️ 0 bài")
            except Exception as exc:
                results.append(f"music ❌ {short_text(exc, 80)}")
        else:
            results.append("music ⏭️ off")
        if self.feature("achievements"):
            try:
                self.do_achievements(announce=False)
                results.append("achievements ✅")
            except Exception as exc:
                results.append(f"achievements ❌ {short_text(exc, 80)}")
        else:
            results.append("achievements ⏭️ off")
        if self.feature("favorite"):
            try:
                self.do_favorite_farm(announce=False, auto_disable=False)
                results.append("favorite ✅")
            except Exception as exc:
                results.append(f"favorite ❌ {short_text(exc, 80)}")
        else:
            results.append("favorite ⏭️ off")
        if self.feature("online"):
            if self.get_state().get("online_running"):
                results.append("online ⏭️ đang chạy")
            else:
                try:
                    self.do_online_session(duration_seconds=70, announce=False)
                    results.append("online ✅")
                except Exception as exc:
                    results.append(f"online ❌ {short_text(exc, 80)}")
        else:
            results.append("online ⏭️ off")
        if self.feature("fan_multi"):
            try:
                self.do_fan_multi_round(self.watch_client or self.client())
                results.append("fan_multi ✅")
            except Exception as exc:
                results.append(f"fan_multi ❌ {short_text(exc, 80)}")
        elif self.feature("watch"):
            try:
                self.do_watch_session(announce=False)
                results.append("watch ✅")
            except Exception as exc:
                results.append(f"watch ❌ {short_text(exc, 80)}")
        else:
            results.append("watch ⏭️ off")
        totals = self.load_daily()
        text = (
            "🏁 Run all xong\n"
            + "\n".join(results)
            + f"\n\nToday: +{fmt_num(totals['exp'])} EXP, "
            f"+{fmt_num(totals['coins'])} coins"
        )
        if announce and self.feature("notifications"):
            self.send_telegram(text)
        return True


    def do_emoji(self) -> bool:
        client = self.client()
        try:
            rooms = client.json("GET", "/api/v2/chat/rooms")
        except RuntimeError as exc:
            text = str(exc)
            if "503" in text or "disabled" in text.lower():
                self.set_feature("emoji", False)
                if self.feature("notifications"):
                    self.send_telegram(
                        "💬 Chat module đang tắt trên live, nên không thể thả emoji. "
                        "Đã tự tắt tính năng emoji."
                    )
                return False
            raise
        rows = rooms if isinstance(rooms, list) else rooms.get("data", [])
        if not rows:
            raise RuntimeError("no chat room available")
        room = rows[0]
        room_id = room.get("id")
        if not room_id:
            raise RuntimeError("chat room has no id")
        client.json(
            "POST",
            f"/api/v2/chat/rooms/{room_id}/messages",
            json={"content": random.choice(["👋", "✨", "🎉", "💜", "🔥"]), "messageType": "text"},
        )
        return True


    @serialized
    def do_daily(self, announce: bool = True) -> bool:
        client = self.client()
        before = client.me()
        before_ach = achievement_snapshot(client)
        daily = client.daily_login()
        after = client.me()
        new_ach = report_achievements(client, before_ach)
        totals = self.apply_totals(before, after)
        self.update_state(last_daily_date=today_utc())
        if announce and self.feature("notifications"):
            exp_gain = int(after.get("exp") or 0) - int(before.get("exp") or 0)
            coin_gain = int(after.get("coins") or 0) - int(before.get("coins") or 0)
            ach_text = (
                ", ".join(str(a.get("id")) for a in new_ach)
                if new_ach
                else "none"
            )
            text = (
                "☀️ VTuberVN daily login\n"
                f"Time: {datetime.now(VN_TZ).strftime('%Y-%m-%d %H:%M %Z')}\n"
                f"Account: {after.get('username')}\n"
                f"Rewarded: {daily.get('rewarded')} | streak: {daily.get('streak')}\n"
                f"EXP: +{exp_gain} | coins: +{coin_gain}\n"
                f"Achievements: {ach_text}\n"
                f"Today total: +{totals['exp']} EXP, +{totals['coins']} coins, "
                f"+{totals['contribution']} contribution ({totals['runs']} runs)"
            )
            self.send_telegram(text)
        return True


    @serialized
    def do_music(self, announce: bool = True) -> bool:
        client = self.client()
        songs = client.songs()
        if not songs:
            self.update_state(last_music_date=today_utc())
            if announce and self.feature("notifications"):
                self.send_telegram(
                    "🎵 VTuberVN music: hiện không có bài nào để farm. "
                    "Sẽ thử lại vào ngày mai."
                )
            return True
        before = client.me()
        before_ach = achievement_snapshot(client)
        gained = music_farm(client, MUSIC_CAP)
        after = client.me()
        new_ach = report_achievements(client, before_ach)
        totals = self.apply_totals(before, after)
        self.update_state(last_music_date=today_utc())
        if announce and self.feature("notifications"):
            ach_text = (
                ", ".join(str(a.get("id")) for a in new_ach)
                if new_ach
                else "none"
            )
            self.send_telegram(
                "🎵 VTuberVN music farm\n"
                f"Time: {datetime.now(VN_TZ).strftime('%Y-%m-%d %H:%M %Z')}\n"
                f"Songs: {len(songs)} | EXP gained: +{gained}\n"
                f"Achievements: {ach_text}\n"
                f"Today total: +{totals['exp']} EXP, +{totals['coins']} coins, "
                f"+{totals['contribution']} contribution ({totals['runs']} runs)"
            )
        return True


    @serialized
    def do_achievements(self, announce: bool = True) -> bool:
        client = self.client()
        before = client.me()
        before_ach = achievement_snapshot(client)
        trigger_achievements(client, 65)
        after = client.me()
        new_ach = report_achievements(client, before_ach)
        totals = self.apply_totals(before, after)
        if announce and self.feature("notifications"):
            text = (
                "🏆 Achievement check\n"
                f"New: {', '.join(str(a.get('id')) for a in new_ach) if new_ach else 'none'}\n"
                f"Today total: +{totals['exp']} EXP, +{totals['coins']} coins"
            )
            self.send_telegram(text)
        return True
