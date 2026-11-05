"""HTTP client for the VTuberHub public/user API."""
from __future__ import annotations

import sys
import time
from typing import Any

import requests
import urllib3

from ..config import browser_headers

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class Client:
    def __init__(self, base: str, token: str | None, insecure: bool) -> None:
        self.base = base.rstrip("/")
        self.insecure = insecure
        self.session = requests.Session()
        self.session.verify = not insecure
        self.session.headers.update(browser_headers(self.base))
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"

    def request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        url = f"{self.base}{path}"
        last: requests.Response | None = None
        for attempt in range(6):
            try:
                response = self.session.request(method, url, timeout=30, **kwargs)
            except requests.RequestException as exc:
                print(f"  network error: {exc}", file=sys.stderr)
                time.sleep(2 + attempt * 2)
                continue
            last = response
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                wait = int(retry_after) if retry_after and retry_after.isdigit() else 3 + attempt * 2
                print(f"  429, waiting {wait}s...")
                time.sleep(wait)
                continue
            if response.status_code >= 500:
                time.sleep(2 + attempt * 2)
                continue
            return response
        if last is None:
            raise RuntimeError(f"{method} {path} failed without response")
        return last

    def json(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self.request(method, path, **kwargs)
        if response.status_code >= 400:
            raise RuntimeError(
                f"{method} {path} -> {response.status_code}: {response.text[:300]}"
            )
        if not response.content:
            return None
        return response.json()

    def login(self, username: str, password: str) -> str:
        data = self.json(
            "POST",
            "/api/auth/login",
            json={"username": username, "password": password},
        )
        token = (data or {}).get("jwt") or (data or {}).get("accessToken")
        if not token:
            raise RuntimeError(f"login response has no jwt: {str(data)[:300]}")
        self.session.headers["Authorization"] = f"Bearer {token}"
        return token

    def me(self) -> dict[str, Any]:
        for path in ("/api/v2/users/me", "/api/auth/me"):
            try:
                data = self.json("GET", path)
                if isinstance(data, dict):
                    return data
            except RuntimeError:
                continue
        raise RuntimeError("cannot read current user profile")

    def exp(self) -> int:
        return int(self.me().get("exp") or 0)

    def achievements(self) -> list[dict[str, Any]]:
        me = self.me()
        user_id = me.get("id")
        params = {"userId": user_id} if user_id else None
        data = self.json("GET", "/api/v2/achievements", params=params)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("data") or data.get("items") or []
        return []

    def daily_login(self) -> dict[str, Any]:
        for path in ("/api/v2/users/daily-login", "/api/auth/daily-login"):
            try:
                return self.json("POST", path)
            except RuntimeError:
                continue
        raise RuntimeError("daily login endpoint failed")

    def channels(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        page = 1
        while page <= 20:
            data = self.json(
                "GET", "/api/v2/channels", params={"limit": 1000, "page": page}
            )
            if isinstance(data, list):
                batch = data
            elif isinstance(data, dict):
                batch = data.get("data") or data.get("items") or []
            else:
                break
            added = 0
            for channel in batch:
                if not isinstance(channel, dict) or not channel.get("id"):
                    continue
                cid = str(channel["id"])
                if cid not in seen:
                    seen.add(cid)
                    result.append(channel)
                    added += 1
            total_pages = None
            total = None
            if isinstance(data, dict):
                meta = data.get("meta") or data.get("pagination") or {}
                total_pages = meta.get("totalPages") or data.get("totalPages")
                total = meta.get("total") or data.get("total")
            if total is not None and len(result) >= int(total):
                break
            if total_pages is not None and page >= int(total_pages):
                break
            if added == 0 or len(batch) < 1000:
                break
            page += 1
        return result

    def favorites(self) -> list[str]:
        data = self.json("GET", "/api/v2/users/favorites")
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            rows = data.get("data") or data.get("items") or []
        else:
            rows = []
        return [str(row["id"]) for row in rows if isinstance(row, dict) and row.get("id")]

    def add_favorites(self, channel_ids: list[str]) -> None:
        for offset in range(0, len(channel_ids), 50):
            batch = channel_ids[offset : offset + 50]
            operations = [{"op": "add", "channel_id": cid} for cid in batch]
            self.json("PATCH", "/api/v2/users/favorites", json=operations)
            print(f"  favorites +{len(batch)} ({offset + len(batch)}/{len(channel_ids)})")
            time.sleep(0.4)

    def remove_favorites(self, channel_ids: list[str]) -> None:
        for offset in range(0, len(channel_ids), 50):
            batch = channel_ids[offset : offset + 50]
            operations = [{"op": "remove", "channel_id": cid} for cid in batch]
            self.json("PATCH", "/api/v2/users/favorites", json=operations)
            print(f"  favorites -{len(batch)} ({offset + len(batch)}/{len(channel_ids)})")
            time.sleep(0.4)

    def songs(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        page = 1
        while page <= 20:
            data = self.json(
                "GET", "/api/v2/music/songs", params={"limit": 100, "page": page}
            )
            if isinstance(data, dict):
                batch = data.get("songs") or data.get("items") or []
                total = data.get("total")
            elif isinstance(data, list):
                batch = data
                total = None
            else:
                break
            added = 0
            for song in batch:
                if not isinstance(song, dict) or not song.get("id"):
                    continue
                sid = str(song["id"])
                if sid not in seen:
                    seen.add(sid)
                    result.append(song)
                    added += 1
            if total is not None and len(result) >= int(total):
                break
            if added == 0 or len(batch) < 100:
                break
            page += 1
        return result

    def play_song(self, song_id: str) -> requests.Response:
        return self.request("POST", f"/api/v2/music/songs/{song_id}/play")
