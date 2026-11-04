"""JSON state persistence (per user / per account)."""
from __future__ import annotations

import json
import os
import shutil
from typing import Any

from .config import (
    ACCOUNT_STATE_FIELDS,
    BASE_STATE_DIR,
    DEFAULT_FEATURES,
    WATCH_DEFAULT_LIMIT_HOURS,
)
from .utils import today_utc


def default_state() -> dict[str, Any]:
    state: dict[str, Any] = {
        "features": dict(DEFAULT_FEATURES),
        "last_daily_date": "",
        "last_music_date": "",
        "last_summary_date": "",
        "watch_date": "",
        "watch_seconds": 0,
        "watch_limit_hours": WATCH_DEFAULT_LIMIT_HOURS,
        "watch_index": 0,
        "tg_offset": 0,
        "last_errors": {},
        "morning_retry_at": 0,
        "favorite_target_rank": 3,
        "favorite_target_exp": 0,
        "favorite_rpm": 60,
        "favorite_batch": 50,
        "last_favorite_date": "",
        "last_favorite_exp": 0,
        "last_favorite_result": "",
        "current_watch": {},
        "online_chunk_hours": 6,
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
        "fan_limit_hours": 8,
        "fan_auto_next": True,
        "fan_last_check": "",
        "fan_multi_channels": [],
        "fan_multi_names": {},
        "fan_multi_progress": {},
        "fan_multi_count": 4,
        "fan_multi_last_round": "",
        "active_account": "",
        "account_states": {},
    }
    return state


def load_state(path: str | None = None) -> dict[str, Any]:
    target = path or os.path.join(BASE_STATE_DIR, "daemon.json")
    try:
        with open(target, encoding="utf-8") as fh:
            state = json.load(fh)
        if not isinstance(state, dict):
            state = {}
    except (OSError, ValueError):
        state = {}
    defaults = default_state()
    for key, value in defaults.items():
        state.setdefault(key, value)
    features = dict(DEFAULT_FEATURES)
    if isinstance(state.get("features"), dict):
        for key, value in state["features"].items():
            if key in features:
                features[key] = bool(value)
    state["features"] = features
    for key in ACCOUNT_STATE_FIELDS:
        if key not in state:
            state[key] = defaults.get(key)
    return state


def save_state(state: dict[str, Any], path: str | None = None) -> None:
    target = path or os.path.join(BASE_STATE_DIR, "daemon.json")
    try:
        os.makedirs(os.path.dirname(target), mode=0o700, exist_ok=True)
        os.chmod(os.path.dirname(target), 0o700)
        tmp = target + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False, indent=1)
        os.chmod(tmp, 0o600)
        os.replace(tmp, target)
        os.chmod(target, 0o600)
    except OSError as exc:
        print(f"cannot save state: {exc}")


def daily_path(state_dir: str | None = None, account: str | None = None) -> str:
    base = state_dir or BASE_STATE_DIR
    name = account or "default"
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in name)
    return os.path.join(base, f"daily_{safe}.json")


def load_daily_state(
    state_dir: str | None = None, account: str | None = None
) -> dict[str, Any]:
    path = daily_path(state_dir, account)
    if not os.path.exists(path):
        base = state_dir or BASE_STATE_DIR
        legacy = os.path.join(base, "daily.json")
        legacy_account = (os.getenv("VTUBERVN_USERNAME") or "").strip()
        if account and account == legacy_account and os.path.exists(legacy):
            try:
                shutil.copyfile(legacy, path)
            except OSError:
                pass
    try:
        with open(path, encoding="utf-8") as fh:
            state = json.load(fh)
        if not isinstance(state, dict):
            state = {}
    except (OSError, ValueError):
        state = {}
    if state.get("date") != today_utc():
        state = {
            "date": today_utc(),
            "exp": 0,
            "coins": 0,
            "contribution": 0,
            "runs": 0,
        }
    for key in ("exp", "coins", "contribution", "runs"):
        state[key] = int(state.get(key) or 0)
    return state


def save_daily_state(
    state: dict[str, Any],
    state_dir: str | None = None,
    account: str | None = None,
) -> None:
    path = daily_path(state_dir, account)
    try:
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False, indent=1)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    except OSError as exc:
        print(f"cannot save daily state: {exc}")
