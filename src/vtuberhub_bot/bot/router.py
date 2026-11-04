"""Telegram router: one isolated Daemon per private chat."""
from __future__ import annotations

import json
import os
import shutil
import threading
import time
from collections import deque
from typing import Any

import requests

from ..config import BASE_STATE_DIR, MAX_USERS
from ..telegram import telegram_credentials, telegram_send_to
from ..worker.daemon import Daemon

class MultiUserBot:
    """Telegram router: one isolated Daemon per private chat/user."""

    def __init__(self) -> None:
        self.stop_event = threading.Event()
        self.daemons: dict[str, Daemon] = {}
        self.rates: dict[str, deque[float]] = {}
        self.base_dir = BASE_STATE_DIR
        self.users_dir = os.path.join(self.base_dir, "users")
        self.bot_state_path = os.path.join(self.base_dir, "bot.json")
        self.max_users = MAX_USERS
        self.owner_chat = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
        self.offset = self._load_offset()

    def _safe_chat_id(self, chat_id: str) -> str:
        return "".join(
            ch if ch.isalnum() or ch in "-_." else "_" for ch in str(chat_id)
        )

    def _load_offset(self) -> int:
        try:
            with open(self.bot_state_path, encoding="utf-8") as fh:
                data = json.load(fh)
            return int(data.get("offset") or 0)
        except (OSError, ValueError):
            return 0

    def _save_offset(self) -> None:
        try:
            os.makedirs(self.base_dir, mode=0o700, exist_ok=True)
            tmp = self.bot_state_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump({"offset": self.offset}, fh)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.bot_state_path)
            os.chmod(self.bot_state_path, 0o600)
        except OSError as exc:
            print(f"cannot save bot offset: {exc}", flush=True)

    def _migrate_owner(self) -> None:
        if not self.owner_chat:
            return
        owner_dir = os.path.join(
            self.users_dir, self._safe_chat_id(self.owner_chat)
        )
        old_accounts = os.path.join(self.base_dir, "accounts.json")
        if not os.path.exists(old_accounts):
            return
        os.makedirs(owner_dir, mode=0o700, exist_ok=True)
        os.chmod(owner_dir, 0o700)
        copied = False
        for name in ("daemon.json", "accounts.json", "daily.json"):
            src = os.path.join(self.base_dir, name)
            dst = os.path.join(owner_dir, name)
            if os.path.exists(src) and not os.path.exists(dst):
                shutil.copy2(src, dst)
                os.chmod(dst, 0o600)
                copied = True
        for name in os.listdir(self.base_dir):
            if name.startswith("daily_") and name.endswith(".json"):
                src = os.path.join(self.base_dir, name)
                dst = os.path.join(owner_dir, name)
                if os.path.isfile(src) and not os.path.exists(dst):
                    shutil.copy2(src, dst)
                    os.chmod(dst, 0o600)
                    copied = True
        # Preserve the Telegram update offset so old commands are not replayed.
        if not os.path.exists(self.bot_state_path):
            old_daemon = os.path.join(self.base_dir, "daemon.json")
            try:
                with open(old_daemon, encoding="utf-8") as fh:
                    old = json.load(fh)
                self.offset = int(old.get("tg_offset") or self.offset)
                self._save_offset()
            except (OSError, ValueError):
                pass
        if copied:
            print(f"migrated owner state -> {owner_dir}", flush=True)

    def get_daemon(self, chat_id: str) -> Daemon:
        chat_id = str(chat_id)
        if chat_id in self.daemons:
            return self.daemons[chat_id]
        if len(self.daemons) >= self.max_users:
            raise RuntimeError(
                f"bot đã đạt giới hạn {self.max_users} người dùng"
            )
        user_dir = os.path.join(
            self.users_dir, self._safe_chat_id(chat_id)
        )
        os.makedirs(user_dir, mode=0o700, exist_ok=True)
        os.chmod(user_dir, 0o700)
        daemon = Daemon(
            state_dir=user_dir,
            chat_id=chat_id,
            seed_env=(chat_id == self.owner_chat),
        )
        daemon.start_workers()
        self.daemons[chat_id] = daemon
        print(f"user {chat_id} ready", flush=True)
        return daemon

    def load_existing(self) -> None:
        os.makedirs(self.users_dir, mode=0o700, exist_ok=True)
        os.chmod(self.users_dir, 0o700)
        self._migrate_owner()
        for name in sorted(os.listdir(self.users_dir)):
            path = os.path.join(self.users_dir, name)
            if not os.path.isdir(path) or not name.isdigit():
                continue
            try:
                self.get_daemon(name)
            except Exception as exc:
                print(f"cannot load user {name}: {exc}", flush=True)

    def _rate_ok(self, chat_id: str) -> bool:
        now = time.time()
        dq = self.rates.setdefault(chat_id, deque())
        while dq and now - dq[0] > 10:
            dq.popleft()
        if len(dq) >= 10:
            return False
        dq.append(now)
        return True

    def telegram_loop(self) -> None:
        token, owner = telegram_credentials()
        if not token:
            print("multi-user telegram: missing bot token", flush=True)
            return
        print(
            f"multi-user telegram polling (owner {owner or '-'})",
            flush=True,
        )
        while not self.stop_event.is_set():
            try:
                response = requests.get(
                    f"https://api.telegram.org/bot{token}/getUpdates",
                    params={"offset": self.offset, "timeout": 25},
                    timeout=35,
                )
                data = response.json()
                if not data.get("ok"):
                    print(f"telegram getUpdates not ok: {data}", flush=True)
                    time.sleep(5)
                    continue
                for update in data.get("result", []):
                    self.offset = int(update.get("update_id", self.offset)) + 1
                    message = (
                        update.get("message")
                        or update.get("edited_message")
                        or update.get("channel_post")
                    )
                    if not isinstance(message, dict):
                        continue
                    sender = message.get("from") or {}
                    if sender.get("is_bot"):
                        continue
                    chat = message.get("chat") or {}
                    chat_id = str(chat.get("id", ""))
                    if not chat_id:
                        continue
                    if chat.get("type") != "private":
                        telegram_send_to(
                            chat_id,
                            "Bot chỉ hỗ trợ chat riêng (private chat).",
                        )
                        continue
                    text = message.get("text") or ""
                    if not text:
                        continue
                    if not self._rate_ok(chat_id):
                        telegram_send_to(
                            chat_id,
                            "⏳ Chậm thôi, tối đa 10 lệnh/10 giây.",
                        )
                        continue
                    try:
                        daemon = self.get_daemon(chat_id)
                    except Exception as exc:
                        telegram_send_to(chat_id, f"❌ {exc}")
                        continue
                    daemon.handle_command(text, chat_id)
                self._save_offset()
            except Exception as exc:
                print("multi-user telegram error:", exc, flush=True)
                self.stop_event.wait(5)

    def start(self) -> None:
        self.load_existing()
        if self.owner_chat:
            telegram_send_to(
                self.owner_chat,
                "🤖 Bot VTuberVN multi-user đã khởi động.\n"
                "Ai cũng có thể /start, /login và dùng các tính năng.\n"
                "Mỗi người có account/state riêng.",
            )
        threading.Thread(
            target=self.telegram_loop, name="telegram", daemon=True
        ).start()
        print("multi-user bot started", flush=True)
        while not self.stop_event.is_set():
            self.stop_event.wait(5)

    def stop(self, *_args: Any) -> None:
        self.stop_event.set()
        for daemon in list(self.daemons.values()):
            daemon.stop()
