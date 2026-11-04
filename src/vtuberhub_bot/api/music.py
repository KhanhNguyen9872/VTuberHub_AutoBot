"""Music listening farm."""
from __future__ import annotations

import time
from typing import Any

from ..config import MUSIC_CAP, MUSIC_GUARD_SECONDS, REQUEST_GAP
from .client import Client

def music_farm(client: Client, target_exp: int = MUSIC_CAP) -> int:
    songs = client.songs()
    if not songs:
        print("no songs available")
        return 0

    before = client.exp()
    last_played: dict[str, float] = {}
    attempts = 0
    no_gain = 0
    print(
        f"songs={len(songs)} target_music_exp={target_exp} "
        f"(server guard {MUSIC_GUARD_SECONDS}s/song, 10 req/min)"
    )

    while client.exp() - before < target_exp:
        now = time.time()
        eligible = [
            song
            for song in songs
            if now - last_played.get(str(song["id"]), 0) >= MUSIC_GUARD_SECONDS
        ]
        if not eligible:
            # Wait until the earliest song becomes eligible again
            earliest = min(
                last_played.get(str(song["id"]), 0) + MUSIC_GUARD_SECONDS
                for song in songs
            )
            wait = max(1.0, earliest - time.time()) + 1
            print(f"  all songs on 3-minute guard, waiting {wait:.0f}s...")
            time.sleep(wait)
            continue

        song = eligible[0]
        song_id = str(song["id"])
        prev_exp = client.exp()
        response = client.play_song(song_id)
        attempts += 1
        last_played[song_id] = time.time()
        current_exp = client.exp()
        if current_exp > prev_exp:
            no_gain = 0
            print(
                f"  play {attempts}: +{current_exp - prev_exp} EXP "
                f"({current_exp - before}/{target_exp})"
            )
        else:
            no_gain += 1
            print(f"  play {attempts}: no EXP (cap reached or guarded)")
            if no_gain >= 8:
                print("  no EXP gain after 8 attempts, stopping")
                break
        if response.status_code not in (200, 201):
            print(f"  play endpoint returned {response.status_code}")
        time.sleep(REQUEST_GAP)

    gained = client.exp() - before
    print(f"music EXP gained: {gained} (attempts={attempts})")
    return gained
