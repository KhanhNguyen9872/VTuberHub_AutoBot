#!/usr/bin/env python3
"""Multi-account session manager for the VTuberVN Telegram bot.

Stores one entry per account in accounts.json (mode 600):
  username, password (needed for automatic re-login), JWT token,
  display name, level, exp, timestamps.

The JWT is reused while valid.  If it expires, the manager logs in again
with the stored password.  /logout removes the account from the switch list.
"""

from __future__ import annotations

import base64
import json
import os
import threading
from datetime import datetime, timezone
from typing import Any

from .api.client import Client
from .config import BASE_STATE_DIR, DEFAULT_BASE, MAX_ACCOUNTS
from .errors import (
    AccountError,
    describe_account_error,
    login_error_message,
    parse_api_error,
)


def token_expiry(token: str) -> datetime | None:
    """Read the exp claim from a JWT without verifying the signature."""
    try:
        payload = (token or "").split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        exp = int(data.get("exp") or 0)
        if exp:
            return datetime.fromtimestamp(exp, tz=timezone.utc)
    except Exception:
        pass
    return None


class AccountManager:
    def __init__(
        self, state_dir: str | None = None, seed_env: bool = True
    ) -> None:
        self.state_dir = state_dir or os.getenv(
            "VTUBERVN_STATE_DIR", BASE_STATE_DIR
        )
        self.accounts_path = os.path.join(self.state_dir, "accounts.json")
        self.seed_env = seed_env
        self.max_accounts = MAX_ACCOUNTS
        self.lock = threading.RLock()
        self.data = self._load()
        self._seed()

    # ── persistence ─────────────────────────────────────────────────────

    def _load(self) -> dict[str, Any]:
        try:
            with open(self.accounts_path, encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict):
                data = {}
        except (OSError, ValueError):
            data = {}
        data.setdefault("active", "")
        data.setdefault("seeded", False)
        accounts = data.get("accounts")
        if not isinstance(accounts, dict):
            accounts = {}
        data["accounts"] = accounts
        return data

    def _save(self) -> None:
        try:
            os.makedirs(self.state_dir, mode=0o700, exist_ok=True)
            os.chmod(self.state_dir, 0o700)
            tmp = self.accounts_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, ensure_ascii=False, indent=1)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.accounts_path)
            os.chmod(self.accounts_path, 0o600)
        except OSError as exc:
            print(f"cannot save accounts: {exc}", flush=True)

    def _seed(self) -> None:
        """Create the first account from the systemd EnvironmentFile."""
        with self.lock:
            if self.data["accounts"]:
                if not self.data.get("seeded"):
                    self.data["seeded"] = True
                if self.data.get("active") not in self.data["accounts"]:
                    self.data["active"] = next(iter(self.data["accounts"]), "")
                self._save()
                return
            if not self.seed_env:
                return
            if self.data.get("seeded"):
                # The user logged out every account; do not resurrect the
                # EnvironmentFile account on the next restart.
                return
            username = (os.getenv("VTUBERVN_USERNAME") or "").strip()
            password = os.getenv("VTUBERVN_PASSWORD") or ""
            if not username or not password:
                return
        try:
            self.login(username, password, make_active=True)
            with self.lock:
                self.data["seeded"] = True
                self._save()
            print(f"account seeded: {username}", flush=True)
        except Exception as exc:
            print(f"account seed failed: {exc}", flush=True)

    # ── queries ─────────────────────────────────────────────────────────

    def active(self) -> str:
        with self.lock:
            return str(self.data.get("active") or "")

    def list_accounts(self) -> list[dict[str, Any]]:
        with self.lock:
            active = self.data.get("active", "")
            rows = []
            for name, acc in self.data["accounts"].items():
                rows.append(
                    {
                        "username": name,
                        "active": name == active,
                        "display_name": acc.get("display_name") or name,
                        "level": acc.get("level"),
                        "exp": acc.get("exp"),
                        "last_login": acc.get("last_login"),
                        "last_error": acc.get("last_error"),
                    }
                )
            rows.sort(key=lambda r: (not r["active"], str(r["username"]).lower()))
            return rows

    def get(self, username: str | None = None) -> dict[str, Any]:
        with self.lock:
            name = (username or self.data.get("active") or "").strip()
            if not name or name not in self.data["accounts"]:
                raise AccountError("account không tồn tại")
            return dict(self.data["accounts"][name])

    def update_profile(self, me: dict[str, Any]) -> None:
        """Refresh cached display name / level / EXP for an account."""
        name = (me.get("username") or "").strip()
        if not name:
            return
        with self.lock:
            acc = self.data["accounts"].get(name)
            if not acc:
                return
            acc["display_name"] = me.get("displayName") or name
            acc["level"] = me.get("level")
            acc["exp"] = me.get("exp")
            self._save()

    # ── authentication ──────────────────────────────────────────────────

    def _new_client(self, token: str | None = None) -> Client:
        return Client(
            DEFAULT_BASE,
            token,
            os.getenv("VTUBERVN_INSECURE") == "1",
        )

    def login(
        self, username: str, password: str, make_active: bool = True
    ) -> dict[str, Any]:
        username = (username or "").strip()
        if not username or not password:
            raise AccountError("username/password trống")
        with self.lock:
            if (
                username not in self.data["accounts"]
                and len(self.data["accounts"]) >= self.max_accounts
            ):
                raise AccountError(
                    f"đã đạt giới hạn {self.max_accounts} account"
                )
        client = self._new_client()
        try:
            client.login(username, password)
            me = client.me()
        except Exception as exc:
            raise AccountError(login_error_message(username, exc)) from exc
        token = client.session.headers.get("Authorization", "")
        if token.startswith("Bearer "):
            token = token[7:]
        now = datetime.now(timezone.utc).isoformat()
        with self.lock:
            if (
                username not in self.data["accounts"]
                and len(self.data["accounts"]) >= self.max_accounts
            ):
                raise AccountError(
                    f"đã đạt giới hạn {self.max_accounts} account"
                )
            old = self.data["accounts"].get(username, {})
            self.data["accounts"][username] = {
                "username": username,
                "password": password,
                "token": token,
                "user_id": me.get("id"),
                "display_name": me.get("displayName") or username,
                "level": me.get("level"),
                "exp": me.get("exp"),
                "added_at": old.get("added_at") or now,
                "last_login": now,
                "last_error": "",
            }
            if make_active or not self.data.get("active"):
                self.data["active"] = username
            self.data["seeded"] = True
            self._save()
            return dict(self.data["accounts"][username])

    def login_with_token(
        self, token: str, make_active: bool = True
    ) -> dict[str, Any]:
        """Login by pasting a browser JWT (bypasses captcha/password login)."""
        token = (token or "").strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
        if not token:
            raise AccountError("token trống")
        client = self._new_client(token)
        try:
            me = client.json("GET", "/api/v2/users/me")
        except Exception as exc:
            status, message, body = parse_api_error(exc)
            code = message.lower()
            if "banned" in code or "banned" in str(exc).lower():
                raise AccountError("Tài khoản đã bị cấm.") from exc
            if status == 401 or "invalid" in code or "expired" in code:
                raise AccountError(
                    "Token không hợp lệ hoặc đã hết hạn. "
                    "Lấy token mới từ browser rồi thử lại."
                ) from exc
            raise AccountError(describe_account_error(exc)) from exc
        username = (me.get("username") or "").strip()
        if not username:
            raise AccountError("Token không trả về username.")
        now = datetime.now(timezone.utc).isoformat()
        with self.lock:
            if (
                username not in self.data["accounts"]
                and len(self.data["accounts"]) >= self.max_accounts
            ):
                raise AccountError(
                    f"đã đạt giới hạn {self.max_accounts} account"
                )
            old = self.data["accounts"].get(username, {})
            self.data["accounts"][username] = {
                "username": username,
                "password": old.get("password") or "",
                "token": token,
                "auth_method": "token",
                "user_id": me.get("id"),
                "display_name": me.get("displayName") or username,
                "level": me.get("level"),
                "exp": me.get("exp"),
                "added_at": old.get("added_at") or now,
                "last_login": now,
                "last_error": "",
            }
            if make_active or not self.data.get("active"):
                self.data["active"] = username
            self.data["seeded"] = True
            self._save()
            return dict(self.data["accounts"][username])

    def logout(self, username: str | None = None) -> str:
        with self.lock:
            name = (username or self.data.get("active") or "").strip()
            if not name or name not in self.data["accounts"]:
                raise AccountError("account không tồn tại")
            del self.data["accounts"][name]
            if self.data.get("active") == name:
                self.data["active"] = next(iter(self.data["accounts"]), "")
            self._save()
            return self.data.get("active", "")

    def switch(self, username: str) -> dict[str, Any]:
        username = (username or "").strip()
        with self.lock:
            if username not in self.data["accounts"]:
                raise AccountError("account không tồn tại")
            self.data["active"] = username
            self._save()
        client = self.client(username)
        me = client.me()
        with self.lock:
            acc = self.data["accounts"][username]
            acc["display_name"] = me.get("displayName") or username
            acc["level"] = me.get("level")
            acc["exp"] = me.get("exp")
            acc["last_login"] = datetime.now(timezone.utc).isoformat()
            acc["last_error"] = ""
            self._save()
            return dict(acc)

    def client(self, username: str | None = None) -> Client:
        """Return a client for the active (or named) account.

        Reuses the saved JWT; on expiry logs in again with the saved password.
        """
        with self.lock:
            name = (username or self.data.get("active") or "").strip()
            if not name or name not in self.data["accounts"]:
                raise AccountError("chưa có account active; dùng /login")
            acc = dict(self.data["accounts"][name])
        token = acc.get("token")
        if token:
            client = self._new_client(token)
            try:
                client.me()
                return client
            except Exception:
                pass
        password = acc.get("password")
        if not password:
            raise AccountError("session hết hạn; dùng /login hoặc /token lại")
        client = self._new_client()
        try:
            client.login(name, password)
            me = client.me()
        except Exception as exc:
            raise AccountError(login_error_message(name, exc)) from exc
        new_token = client.session.headers.get("Authorization", "")
        if new_token.startswith("Bearer "):
            new_token = new_token[7:]
        with self.lock:
            if name in self.data["accounts"]:
                self.data["accounts"][name]["token"] = new_token
                self.data["accounts"][name]["last_login"] = datetime.now(
                    timezone.utc
                ).isoformat()
                self.data["accounts"][name]["level"] = me.get("level")
                self.data["accounts"][name]["exp"] = me.get("exp")
                self.data["accounts"][name]["last_error"] = ""
                self._save()
        return client
