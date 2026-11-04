"""Configuration and constants."""
from __future__ import annotations

import os
from datetime import timezone

try:
    from zoneinfo import ZoneInfo

    VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
except Exception:  # pragma: no cover
    VN_TZ = timezone.utc

DEFAULT_BASE = os.getenv("VTUBERVN_BASE", "https://vtuberhub.vn")
BASE_STATE_DIR = os.getenv("VTUBERVN_STATE_DIR", "/var/lib/vtuberhub-autobot")

DEFAULT_FEATURES = {
    "daily": True,
    "music": True,
    "watch": True,
    "emoji": False,
    "favorite": False,
    "online": True,
    "fan": False,
    "fan_multi": False,
    "achievements": True,
    "notifications": True,
}

ACCOUNT_STATE_FIELDS = (
    "watch_date",
    "watch_seconds",
    "watch_index",
    "last_daily_date",
    "last_music_date",
    "last_summary_date",
    "last_favorite_date",
    "last_favorite_exp",
    "last_favorite_result",
    "favorite_target_rank",
    "favorite_target_exp",
    "current_watch",
    "online_date",
    "online_seconds",
    "online_total_seconds",
    "last_online_result",
    "online_running",
    "online_started_at",
    "fan_channel_id",
    "fan_channel_name",
    "fan_last_pct",
    "fan_badge_notified",
    "fan_video_index",
    "fan_multi_channels",
    "fan_multi_names",
    "fan_multi_progress",
)

WATCH_DEFAULT_LIMIT_HOURS = 6
FAN_BADGE_SECONDS = 129_600  # 36 hours per channel
EMOJI_INTERVAL_SECONDS = 300
ERROR_THROTTLE_SECONDS = 300

MUSIC_CAP = 600
MUSIC_REWARD = 10
MUSIC_GUARD_SECONDS = 185
REQUEST_GAP = 6.2

MAX_USERS = max(1, int(os.getenv("VTUBERVN_MAX_USERS", "20") or 20))
MAX_ACCOUNTS = max(1, int(os.getenv("VTUBERVN_MAX_ACCOUNTS", "5") or 5))
