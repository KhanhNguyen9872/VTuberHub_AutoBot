"""Socket.IO online-time sessions."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..api.achievements import achievement_snapshot, report_achievements
from ..api.client import Client
from ..config import VN_TZ
from ..features.presence import online_session
from ..utils import fmt_num, short_text, today_utc


class OnlineMixin:
    def do_online_session(
        self, duration_seconds: int | None = None, announce: bool = True
    ) -> bool:
        state = self.get_state()
        account_at_start = self.accounts.active()
        client = self.client()
        before_ach = achievement_snapshot(client)
        if duration_seconds is None:
            hours = max(1, min(12, int(state.get("online_chunk_hours", 6) or 6)))
            duration_seconds = hours * 3600
        duration_seconds = max(30, int(duration_seconds))
        if announce and self.feature("notifications"):
            self.send_telegram(
                "🟢 Online presence bắt đầu\n"
                f"Time: {datetime.now(VN_TZ).strftime('%Y-%m-%d %H:%M %Z')}\n"
                f"Account: {self.accounts.active()}\n"
                f"Duration: {duration_seconds / 3600:.1f} giờ\n"
                "Mục tiêu: online_10h / online_100h (server cộng giờ khi socket đóng)."
            )
        self.update_state(
            online_running=True,
            online_started_at=datetime.now(timezone.utc).isoformat(),
        )
        result = online_session(
            client,
            duration_seconds,
            stop_event=self.stop_event,
            should_stop=self.online_cancel.is_set,
        )
        self.update_state(online_running=False, online_started_at="")
        if self.accounts.active() != account_at_start:
            print("online session account changed; skipping state update", flush=True)
            return False
        new_ach = report_achievements(client, before_ach)
        # Do NOT apply_totals(before, after) here: the online socket runs for
        # hours in parallel with watch sessions, so a whole-window delta would
        # double-count watch EXP.  Today's totals are updated by those tasks.
        totals = self.load_daily()
        elapsed = max(0, int(result.get("elapsed") or 0))
        state = self.get_state()
        if state.get("online_date") != today_utc():
            state["online_date"] = today_utc()
            state["online_seconds"] = 0
        state["online_seconds"] = int(state.get("online_seconds", 0)) + elapsed
        state["online_total_seconds"] = (
            int(state.get("online_total_seconds", 0)) + elapsed
        )
        if result.get("error"):
            state["last_online_result"] = f"error: {short_text(result['error'], 80)}"
        elif elapsed < 60:
            state["last_online_result"] = "tested"
        else:
            state["last_online_result"] = "ok"
        self.update_state(
            online_date=state["online_date"],
            online_seconds=state["online_seconds"],
            online_total_seconds=state["online_total_seconds"],
            last_online_result=state["last_online_result"],
        )
        ach_text = (
            ", ".join(str(a.get("id")) for a in new_ach) if new_ach else "none"
        )
        if announce and self.feature("notifications"):
            self.send_telegram(
                "🟢 Online presence kết thúc\n"
                f"Thời gian: {elapsed / 3600:.1f} giờ\n"
                f"Hôm nay: {state['online_seconds'] / 3600:.1f} giờ | "
                f"Tổng: {state['online_total_seconds'] / 3600:.1f} giờ\n"
                f"Achievements mới: {ach_text}\n"
                f"Today total: +{fmt_num(totals['exp'])} EXP, "
                f"+{fmt_num(totals['coins'])} coins"
            )
        if result.get("error"):
            print(f"online session error: {result['error']}", flush=True)
            return False
        return True
