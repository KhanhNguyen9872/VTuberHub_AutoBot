"""Background scheduler and task loops."""
from __future__ import annotations

import threading
import time
import traceback
from datetime import datetime, timezone

from ..config import FAN_BADGE_SECONDS, VN_TZ, WATCH_DEFAULT_LIMIT_HOURS
from ..utils import (
    fmt_duration,
    fmt_num,
    now_utc,
    short_text,
    today_utc,
    today_vn,
)


class LoopsMixin:
    def online_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                if not self.accounts.active():
                    self.stop_event.wait(30)
                    continue
                if not self.feature("online"):
                    self.stop_event.wait(30)
                    continue
                with self.task_lock:
                    if "online" in self.running_tasks:
                        self.stop_event.wait(10)
                        continue
                self.online_cancel.clear()
                self.run_task("online", self.do_online_session)
                self.stop_event.wait(30)
            except Exception as exc:
                self.notify_error("online", exc)
                print(traceback.format_exc(), flush=True)
                self.stop_event.wait(60)


    def start_workers(self) -> None:
        if self.workers_started:
            return
        self.workers_started = True
        active = self.accounts.active()
        state = self.get_state()
        if active and not state.get("active_account"):
            self.update_state(active_account=active)
            self.save_account_state(active)
        elif active and state.get("active_account") != active:
            self.load_account_state(active)
        self.update_state(
            current_watch={},
            online_running=False,
            online_started_at="",
        )
        threading.Thread(
            target=self.scheduler_loop, name="scheduler", daemon=True
        ).start()
        self.watch_thread = threading.Thread(
            target=self.watch_loop, name="watch", daemon=True
        )
        self.watch_thread.start()
        self.emoji_thread = threading.Thread(
            target=self.emoji_loop, name="emoji", daemon=True
        )
        self.emoji_thread.start()
        self.favorite_thread = threading.Thread(
            target=self.favorite_loop, name="favorite", daemon=True
        )
        self.favorite_thread.start()
        self.online_thread = threading.Thread(
            target=self.online_loop, name="online", daemon=True
        )
        self.online_thread.start()
        print(
            f"user {self.chat_id or '?'} workers started",
            flush=True,
        )


    def run_task(self, name: str, fn, *args: Any, **kwargs: Any) -> None:
        with self.task_lock:
            if name in self.running_tasks:
                return
            self.running_tasks.add(name)

        def runner() -> None:
            try:
                fn(*args, **kwargs)
            except Exception as exc:
                self.notify_error(name, exc)
                print(traceback.format_exc(), flush=True)
            finally:
                with self.task_lock:
                    self.running_tasks.discard(name)

        threading.Thread(target=runner, name=f"task-{name}", daemon=True).start()


    def morning_task(self) -> None:
        try:
            if self.feature("daily") and self.get_state().get("last_daily_date") != today_utc():
                self.do_daily()
            if self.feature("music") and self.get_state().get("last_music_date") != today_utc():
                self.do_music()
        except Exception as exc:
            self.update_state(morning_retry_at=time.time() + 600)
            self.notify_error("morning", exc)
            print(traceback.format_exc(), flush=True)
        else:
            self.update_state(morning_retry_at=0)


    def watch_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                state = self.get_state()
                if not self.accounts.active():
                    self.stop_event.wait(30)
                    continue
                if not state["features"].get("watch"):
                    self.stop_event.wait(30)
                    continue
                if self.pause_watch.is_set():
                    self.stop_event.wait(5)
                    continue
                if state.get("watch_date") != today_utc():
                    self.update_state(watch_date=today_utc(), watch_seconds=0)
                    state = self.get_state()
                with self.task_lock:
                    busy = bool(
                        {"morning", "music", "daily", "favorite"} & self.running_tasks
                    )
                if busy:
                    self.stop_event.wait(30)
                    continue
                fan_on = bool(state["features"].get("fan"))
                fan_multi_on = bool(state["features"].get("fan_multi"))
                fan_mode = fan_on or fan_multi_on
                limit_hours = int(
                    state.get("fan_limit_hours", 8)
                    if fan_mode
                    else state.get("watch_limit_hours", WATCH_DEFAULT_LIMIT_HOURS)
                ) or WATCH_DEFAULT_LIMIT_HOURS
                limit = max(1, limit_hours) * 3600
                if int(state.get("watch_seconds", 0)) >= limit:
                    self.stop_event.wait(300)
                    continue
                if self.watch_client is None:
                    self.watch_client = self.client()
                if fan_multi_on:
                    self.do_fan_multi_round(self.watch_client)
                    self.stop_event.wait(10)
                    continue
                if fan_on:
                    target = (state.get("fan_channel_id") or "").strip()
                    if not target:
                        try:
                            row = self.pick_fan_target(self.watch_client)
                        except Exception as exc:
                            self.set_feature("fan", False)
                            self.notify_error("fan", exc)
                            self.stop_event.wait(60)
                            continue
                        target = str(row["channelId"])
                        total = int(row.get("totalSeconds") or 0)
                        self.update_state(
                            fan_channel_id=target,
                            fan_channel_name=row.get("name") or target,
                            fan_last_pct=min(
                                100, int(total * 100 / FAN_BADGE_SECONDS)
                            ),
                            fan_badge_notified=False,
                            fan_video_index=0,
                        )
                        if self.feature("notifications"):
                            self.send_telegram(
                                "🔥 Fan cứng bắt đầu\n"
                                f"Channel: {row.get('name')} ({target})\n"
                                f"Đã xem: {fmt_duration(total)} / 36h\n"
                                f"Fan limit: {limit_hours}h/ngày"
                            )
                    self.do_watch_session(
                        announce=False,
                        client=self.watch_client,
                        channel_id=target,
                    )
                    self.check_fan_progress(self.watch_client, target)
                else:
                    self.do_watch_session(announce=False, client=self.watch_client)
                self.stop_event.wait(10)
            except Exception as exc:
                self.watch_client = None
                self.notify_error("watch", exc)
                print(traceback.format_exc(), flush=True)
                self.stop_event.wait(120)


    def scheduler_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                if not self.accounts.active():
                    self.stop_event.wait(30)
                    continue
                now = now_utc()
                state = self.get_state()
                due_time = now.hour > 0 or now.minute >= 10
                if (
                    due_time
                    and time.time() >= float(state.get("morning_retry_at", 0) or 0)
                    and (
                        (self.feature("daily") and state.get("last_daily_date") != today_utc())
                        or (self.feature("music") and state.get("last_music_date") != today_utc())
                    )
                ):
                    self.run_task("morning", self.morning_task)
                vn = datetime.now(VN_TZ)
                if (
                    vn.hour == 23
                    and vn.minute >= 55
                    and state.get("last_summary_date") != today_vn()
                ):
                    self.run_task("daily_summary", self.send_daily_summary)
            except Exception as exc:
                print("scheduler error:", exc, flush=True)
            self.stop_event.wait(30)


    def send_daily_summary(self) -> None:
        state = self.get_state()
        totals = self.load_daily()
        try:
            client = self.client()
            me = client.me()
            account = f"{me.get('username')} | Lv.{me.get('level')} ★{me.get('prestige')}"
            exp = me.get("exp")
            coins = me.get("coins")
            contribution = me.get("contribution")
        except Exception as exc:
            account = f"error: {exc}"
            exp = coins = contribution = "?"
        text = (
            "📊 Tổng kết hôm nay\n"
            f"Time: {datetime.now(VN_TZ).strftime('%Y-%m-%d %H:%M %Z')}\n"
            f"Account: {account}\n"
            f"Hiện tại: EXP {exp} | coins {coins} | contribution {contribution}\n"
            f"Hôm nay: +{totals['exp']} EXP, +{totals['coins']} coins, "
            f"+{totals['contribution']} contribution ({totals['runs']} runs)\n"
            f"Watch: {int(state.get('watch_seconds', 0)) // 60} phút\n"
            f"Favorite: {'on' if state['features'].get('favorite') else 'off'} | "
            f"target rank #{int(state.get('favorite_target_rank', 3) or 3)} | "
            f"last {state.get('last_favorite_result') or '-'}\n"
            "Features: "
            + ", ".join(
                f"{k}={'on' if v else 'off'}"
                for k, v in state["features"].items()
            )
        )
        self.update_state(last_summary_date=today_vn())
        if self.feature("notifications"):
            self.send_telegram(text)


    def favorite_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                if not self.accounts.active():
                    self.stop_event.wait(30)
                    continue
                if not self.feature("favorite"):
                    self.stop_event.wait(30)
                    continue
                with self.task_lock:
                    if "favorite" in self.running_tasks:
                        self.stop_event.wait(10)
                        continue
                self.request_favorite_farm(auto_disable=True)
                self.stop_event.wait(30)
            except Exception as exc:
                self.notify_error("favorite", exc)
                print(traceback.format_exc(), flush=True)
                self.stop_event.wait(60)


    def emoji_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                if not self.accounts.active():
                    self.stop_event.wait(30)
                    continue
                if not self.feature("emoji"):
                    self.stop_event.wait(30)
                    continue
                self.do_emoji()
                self.stop_event.wait(EMOJI_INTERVAL_SECONDS)
            except Exception as exc:
                self.notify_error("emoji", exc)
                print(traceback.format_exc(), flush=True)
                self.stop_event.wait(300)
