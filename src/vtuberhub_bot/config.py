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
DEFAULT_USER_AGENT = os.getenv(
    "VTUBERVN_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
)


def browser_headers(base: str) -> dict[str, str]:
    origin = base.rstrip("/")
    return {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        "Origin": origin,
        "Referer": f"{origin}/",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "sec-ch-ua": '"Chromium";v="140", "Not_A Brand";v="24", "Google Chrome";v="140"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    }

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
