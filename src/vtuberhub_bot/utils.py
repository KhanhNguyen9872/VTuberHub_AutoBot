"""Small shared helpers."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .config import VN_TZ


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def today_utc() -> str:
    return now_utc().date().isoformat()


def today_vn() -> str:
    return datetime.now(VN_TZ).date().isoformat()


def fmt_num(value: Any) -> str:
    try:
        return f"{int(value or 0):,}"
    except (TypeError, ValueError):
        return str(value)


def short_text(value: Any, limit: int = 70) -> str:
    text = str(value or "").replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def fmt_time(value: Any) -> str:
    if not value:
        return "-"
    try:
        if isinstance(value, (int, float)):
            dt = datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc)
        else:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.astimezone(VN_TZ).strftime("%d/%m %H:%M")
    except Exception:
        return str(value)[:16]


def fmt_epoch(value: Any) -> str:
    try:
        dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
        return dt.astimezone(VN_TZ).strftime("%d/%m %H:%M")
    except Exception:
        return "-"


def fmt_duration(seconds: Any) -> str:
    try:
        total = max(0, int(seconds or 0))
    except (TypeError, ValueError):
        return "0m"
    hours = total // 3600
    minutes = (total % 3600) // 60
    if hours:
        return f"{hours}h{minutes:02d}m"
    return f"{minutes}m"
