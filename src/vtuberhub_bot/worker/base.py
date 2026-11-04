"""Base worker: state, accounts, totals and lifecycle."""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from functools import wraps
from typing import Any

from ..accounts import AccountManager
from ..api.client import Client
from ..config import (
    ACCOUNT_STATE_FIELDS,
    BASE_STATE_DIR,
    DEFAULT_FEATURES,
    VN_TZ,
    WATCH_DEFAULT_LIMIT_HOURS,
)
from ..storage import (
    load_daily_state,
    load_state,
    save_daily_state,
    save_state,
)
from ..telegram import telegram_send_to


def serialized(method):
    """Serialize account operations so totals are not double-counted."""

    @wraps(method)
    def wrapper(self, *args: Any, **kwargs: Any):
        with self.account_lock:
            return method(self, *args, **kwargs)

    return wrapper


class BaseWorker:
    def __init__(
        self,
        state_dir: str | None = None,
        chat_id: str = "",
        seed_env: bool = True,
    ) -> None:
        self.state_dir = state_dir or os.getenv("VTUBERVN_STATE_DIR", BASE_STATE_DIR)
        self.state_path = os.path.join(self.state_dir, "daemon.json")
        os.makedirs(self.state_dir, mode=0o700, exist_ok=True)
        os.chmod(self.state_dir, 0o700)
        self.chat_id = str(chat_id or "")
        self.accounts = AccountManager(
            self.state_dir, seed_env=seed_env
        )
        self.workers_started = False
        self.stop_event = threading.Event()
        self.state_lock = threading.RLock()
        self.totals_lock = threading.RLock()
        self.task_lock = threading.RLock()
        self.account_lock = threading.RLock()
        self.started_at = time.time()
        self.pause_watch = threading.Event()
        self.favorite_cancel = threading.Event()
        self.online_cancel = threading.Event()
        self.fan_multi_cancel = threading.Event()
        self.running_tasks: set[str] = set()
        self.watch_thread: threading.Thread | None = None
        self.emoji_thread: threading.Thread | None = None
        self.favorite_thread: threading.Thread | None = None
        self.online_thread: threading.Thread | None = None
        self.watch_client: Client | None = None


    def switch_account(self, username: str) -> str:
        username = (username or "").strip()
        if not username:
            raise RuntimeError("username trống")
        state = self.get_state()
        current = (state.get("active_account") or "").strip()
        if username == current:
            return current
        self.pause_watch.set()
        self.favorite_cancel.set()
        self.online_cancel.set()
        self.fan_multi_cancel.set()
        try:
            with self.account_lock:
                if current:
                    self.save_account_state(current)
                self.accounts.switch(username)
                self.load_account_state(username)
                self.watch_client = None
        finally:
            self.pause_watch.clear()
            self.favorite_cancel.clear()
        return username


    def client(self, username: str | None = None) -> Client:
        return self.accounts.client(username)


    def set_feature(self, feature: str, enabled: bool) -> bool:
        feature = feature.strip().lower()
        aliases = {
            "login": "daily",
            "songs": "music",
            "song": "music",
            "xem": "watch",
            "chat": "emoji",
            "fav": "favorite",
            "favorites": "favorite",
            "achievement": "achievements",
            "notify": "notifications",
        }
        feature = aliases.get(feature, feature)
        with self.state_lock:
            state = load_state(self.state_path)
            if feature not in state["features"]:
                return False
            state["features"][feature] = enabled
            save_state(state, self.state_path)
        return True


    def load_account_state(self, username: str) -> None:
        state = self.get_state()
        saved = (state.get("account_states") or {}).get(username, {})
        defaults = {
            "watch_date": "",
            "watch_seconds": 0,
            "watch_index": 0,
            "last_daily_date": "",
            "last_music_date": "",
            "last_summary_date": "",
            "last_favorite_date": "",
            "last_favorite_exp": 0,
            "last_favorite_result": "",
            "favorite_target_rank": 3,
            "favorite_target_exp": 0,
            "current_watch": {},
            "online_date": "",
            "online_seconds": 0,
            "online_total_seconds": 0,
            "last_online_result": "",
            "online_running": False,
            "online_started_at": "",
            "fan_channel_id": "",
            "fan_channel_name": "",
            "fan_last_pct": 0,
            "fan_badge_notified": False,
            "fan_video_index": 0,
            "fan_multi_channels": [],
            "fan_multi_names": {},
            "fan_multi_progress": {},
        }
        update = dict(defaults)
        update.update({k: v for k, v in saved.items() if k in ACCOUNT_STATE_FIELDS})
        update["active_account"] = username
        update["current_watch"] = {}
        self.update_state(**update)


    def get_state(self) -> dict[str, Any]:
        with self.state_lock:
            return load_state(self.state_path)


    def stop(self, *_args: Any) -> None:
        self.stop_event.set()


    def feature(self, name: str) -> bool:
        return bool(self.get_state()["features"].get(name))


    def apply_totals(
        self,
        before: dict[str, Any],
        after: dict[str, Any],
        count_run: bool = True,
    ) -> dict[str, Any]:
        exp = int(after.get("exp") or 0) - int(before.get("exp") or 0)
        coins = int(after.get("coins") or 0) - int(before.get("coins") or 0)
        contribution = int(after.get("contribution") or 0) - int(
            before.get("contribution") or 0
        )
        with self.totals_lock:
            totals = self.load_daily()
            totals["exp"] += exp
            totals["coins"] += coins
            totals["contribution"] += contribution
            if count_run:
                totals["runs"] += 1
            self.save_daily(totals)
        return totals


    def save_account_state(self, username: str | None = None) -> None:
        state = self.get_state()
        name = (username or state.get("active_account") or self.accounts.active()).strip()
        if not name:
            return
        saved = {key: state.get(key) for key in ACCOUNT_STATE_FIELDS}
        # The watch/online sessions are dead once we switch away.
        saved["current_watch"] = {}
        saved["online_running"] = False
        saved["online_started_at"] = ""
        account_states = dict(state.get("account_states") or {})
        account_states[name] = saved
        self.update_state(account_states=account_states)


    def save_daily(self, state: dict[str, Any]) -> None:
        account = self.accounts.active() or "default"
        save_daily_state(state, self.state_dir, account)


    def send_telegram(self, text: str) -> bool:
        if not self.chat_id:
            return False
        return telegram_send_to(self.chat_id, text)


    def notify_error(self, task: str, exc: BaseException) -> None:
        state = self.get_state()
        last = float(state.get("last_errors", {}).get(task, 0) or 0)
        if time.time() - last < ERROR_THROTTLE_SECONDS:
            return
        state["last_errors"] = dict(state.get("last_errors") or {})
        state["last_errors"][task] = time.time()
        self.update_state(last_errors=state["last_errors"])
        text = (
            f"❌ VTuberVN auto lỗi: {task}\n"
            f"Time: {datetime.now(VN_TZ).strftime('%Y-%m-%d %H:%M %Z')}\n"
            f"{type(exc).__name__}: {exc}"
        )
        print(text, flush=True)
        if self.feature("notifications"):
            self.send_telegram(text)


    def update_state(self, **kwargs: Any) -> dict[str, Any]:
        with self.state_lock:
            state = load_state(self.state_path)
            state.update(kwargs)
            save_state(state, self.state_path)
            return state


    def load_daily(self) -> dict[str, Any]:
        account = self.accounts.active() or "default"
        return load_daily_state(self.state_dir, account)
