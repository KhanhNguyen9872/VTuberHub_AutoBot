"""Favorite add/remove EXP farm."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..api.client import Client
from ..config import VN_TZ
from ..features.favorite import farm_to_target
from ..utils import fmt_num, short_text, today_utc
from .base import serialized


class FavoriteMixin:
    def favorite_target(self, client: Client) -> int:
        state = self.get_state()
        absolute = int(state.get("favorite_target_exp", 0) or 0)
        if absolute > 0:
            return absolute
        rank = max(1, min(100, int(state.get("favorite_target_rank", 3) or 3)))
        data = client.json(
            "GET",
            "/api/v2/leaderboard",
            params={"scope": "all_time", "limit": 100, "sortField": "exp"},
        )
        rows = data if isinstance(data, list) else data.get("data", data.get("items", []))
        if not rows:
            raise RuntimeError("leaderboard is empty")
        rank = min(rank, len(rows))
        row = rows[rank - 1]
        target = int(row.get("exp") or 0) + 1
        name = row.get("username") or (row.get("user") or {}).get("username") or "?"
        print(f"favorite target: rank #{rank} {name} = {target} EXP", flush=True)
        return target


    @serialized
    def do_favorite_farm(
        self, announce: bool = True, auto_disable: bool = True
    ) -> bool:
        try:
            state = self.get_state()
            client = self.client()
            before = client.me()
            start_exp = int(before.get("exp") or 0)
            target = self.favorite_target(client)
            if target <= start_exp:
                self.update_state(
                    last_favorite_date=today_utc(),
                    last_favorite_exp=start_exp,
                    last_favorite_result="already",
                )
                if auto_disable:
                    self.set_feature("favorite", False)
                if announce and self.feature("notifications"):
                    self.send_telegram(
                        "⭐ Favorite farm: đã đạt target\n"
                        f"EXP hiện tại: {start_exp:,}\n"
                        f"Target: {target:,}"
                    )
                return True

            if announce and self.feature("notifications"):
                self.send_telegram(
                    "⭐ Favorite farm bắt đầu\n"
                    f"Time: {datetime.now(VN_TZ).strftime('%Y-%m-%d %H:%M %Z')}\n"
                    f"EXP: {start_exp:,} -> {target:,} (+{target - start_exp:,})\n"
                    f"Rate: {float(state.get('favorite_rpm', 60) or 60):g} req/min | "
                    f"batch {int(state.get('favorite_batch', 50) or 50)} ops"
                )

            last_milestone = 0

            def on_progress(info: dict[str, Any]) -> None:
                nonlocal last_milestone
                span = max(1, int(info["target"]) - int(info["start"]))
                pct = int((int(info["current"]) - int(info["start"])) / span * 100)
                milestone = min(75, pct // 25 * 25)
                print(
                    f"  favorite {info['current']:,}/{info['target']:,} EXP | "
                    f"{info['requests']} req | {info['rate']:,.0f} EXP/min",
                    flush=True,
                )
                if (
                    milestone > last_milestone
                    and announce
                    and self.feature("notifications")
                ):
                    last_milestone = milestone
                    self.send_telegram(
                        f"⭐ Favorite farm {milestone}%\n"
                        f"EXP {info['current']:,}/{info['target']:,} | "
                        f"{info['rate']:,.0f} EXP/min"
                    )

            result = farm_to_target(
                client,
                target,
                rpm=float(state.get("favorite_rpm", 60) or 60),
                batch=int(state.get("favorite_batch", 50) or 50),
                stop_event=self.stop_event,
                should_stop=self.favorite_cancel.is_set,
                progress=on_progress,
            )
            after = client.me()
            totals = self.apply_totals(before, after)
            final_exp = int(after.get("exp") or 0)
            self.update_state(
                last_favorite_date=today_utc(),
                last_favorite_exp=final_exp,
                last_favorite_result=("reached" if result["reached"] else "stopped"),
            )
            if result.get("error"):
                raise RuntimeError(str(result["error"]))
            if result["reached"]:
                if auto_disable:
                    self.set_feature("favorite", False)
                if announce and self.feature("notifications"):
                    self.send_telegram(
                        "⭐ Favorite farm xong\n"
                        f"EXP: {result['start']:,} -> {result['final']:,} "
                        f"(+{result['gained']:,})\n"
                        f"Requests: {result['requests']} | "
                        f"{result['elapsed'] / 60:.1f} phút | "
                        f"{result['gained'] / max(0.001, result['elapsed']) * 60:,.0f} EXP/min\n"
                        f"Today: +{totals['exp']:,} EXP, +{totals['coins']:,} coins\n"
                        + ("Đã đạt target, tự tắt feature favorite." if auto_disable else "")
                    )
            elif announce and self.feature("notifications"):
                self.send_telegram(
                    "⏹ Favorite farm dừng\n"
                    f"EXP: {result['start']:,} -> {result['final']:,} "
                    f"(+{result['gained']:,})\n"
                    f"Requests: {result['requests']} | chưa đạt target"
                )
            return bool(result["reached"])
        finally:
            self.pause_watch.clear()


    def request_favorite_farm(
        self, announce: bool = True, auto_disable: bool = True
    ) -> None:
        self.favorite_cancel.clear()
        self.pause_watch.set()
        self.run_task(
            "favorite",
            self.do_favorite_farm,
            announce=announce,
            auto_disable=auto_disable,
        )
