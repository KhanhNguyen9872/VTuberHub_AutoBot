"""Telegram API helpers."""
from __future__ import annotations

import os

import requests


def telegram_credentials() -> tuple[str, str]:
    return (
        (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip(),
        (os.getenv("TELEGRAM_CHAT_ID") or "").strip(),
    )


def telegram_send_to(chat_id: str | int, text: str) -> bool:
    token, _ = telegram_credentials()
    if not token or not chat_id:
        return False
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={
                "chat_id": str(chat_id),
                "text": text,
                "disable_web_page_preview": "true",
            },
            timeout=20,
        )
        return response.ok
    except requests.RequestException:
        return False


def send_telegram(text: str) -> bool:
    """Send to the configured owner chat (used by CLI/global notices)."""
    _, chat_id = telegram_credentials()
    if not chat_id:
        print("telegram skipped: TELEGRAM_CHAT_ID missing")
        return False
    ok = telegram_send_to(chat_id, text)
    if ok:
        print("telegram notification sent")
    return ok
