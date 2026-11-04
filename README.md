# VTuberHub AutoBot

Bot Telegram multi-user cho `vtuberhub.vn`: tự động daily login, watch, music,
online presence, favorite EXP, fan badge và các lệnh xem dữ liệu.

## Tính năng

- **Multi-user**: mọi private chat đều dùng được; mỗi chat có account/state riêng.
- **Account**: `/login`, `/logout`, `/switch`, `/accounts`, token + password lưu file `600`.
- **Auto**:
  - daily login, music farm, watch 5 phút/channel
  - online presence cho achievement `online_10h` / `online_100h`
  - favorite add/remove EXP farm (không cap)
  - fan badge 36h/channel, single-target và multi-tab
  - achievement checks
- **Telegram**:
  - `/status`, `/profile`, `/rank`, `/watching`, `/features`
  - `/videos`, `/live`, `/channels`, `/songs`, `/achievements`, `/notifications`,
    `/timeline`, `/favorites`, `/history`, `/stats`, `/ping`
  - `/run all|daily|music|watch|favorite|online|achievements`
  - `/on`, `/off`, `/set`
  - `/favorite`, `/online`, `/fan`

## Cấu trúc

```text
src/vtuberhub_bot/
  config.py          # env + constants
  utils.py           # time/format helpers
  storage.py         # JSON state, daily totals
  telegram.py        # Telegram send helpers
  accounts.py        # multi-account session manager
  api/
    client.py        # HTTP API client
    achievements.py  # achievement snapshot/diff
    music.py         # music farm
  features/
    favorite.py      # favorite add/remove farm
    presence.py      # Socket.IO presence + achievement trigger
  worker/
    base.py          # state/accounts/totals/lifecycle
    tasks.py         # daily/music/achievements/emoji
    watch.py         # watch session
    favorite.py      # favorite mixin
    online.py        # online mixin
    fan.py           # fan badge mixin
    loops.py         # scheduler + background loops
    daemon.py        # composed per-user Daemon
  bot/
    views.py         # read-only Telegram views
    commands.py      # command dispatcher
    router.py        # MultiUserBot (Telegram polling)
  main.py
scripts/auto_exp_daemon.py
systemd/vtuberhub-autobot.service
```

## Cài đặt

```bash
python3 -m venv venv
. venv/bin/activate
pip install -r requirements.txt

sudo mkdir -p /var/lib/vtuberhub-autobot
sudo cp .env.example /etc/vtuberhub-autobot.env
sudo chmod 600 /etc/vtuberhub-autobot.env
# sửa token/chat ID/state dir

PYTHONPATH=src python scripts/auto_exp_daemon.py
```

Systemd:

```bash
sudo cp systemd/vtuberhub-autobot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vtuberhub-autobot.service
journalctl -u vtuberhub-autobot.service -f
```

## State

```text
/var/lib/vtuberhub-autobot/
  bot.json                     # Telegram update offset
  users/<chat_id>/
    accounts.json              # username/password/JWT, mode 600
    daemon.json                # features + per-account state
    daily_<account>.json       # daily totals
```

- Thư mục user `700`, file `600`.
- `VTUBERVN_MAX_USERS` mặc định 20.
- `VTUBERVN_MAX_ACCOUNTS` mặc định 5.
- Bot chỉ hỗ trợ private chat; group bị từ chối.
- Rate limit 10 lệnh/10 giây mỗi chat.

## Fan badge

Backend cấp fan badge khi `total_seconds >= 129.600` (36 giờ) cho cùng channel.
UI web chỉ hiển thị progress 24h, nhưng badge thật ở 36h.

```text
/fan list
/fan set <số|channel_id|tên>
/fan search <tên>
/fan on | off | next
/fan multi 4          # 4 tab, 4 channel khác nhau
/fan multi status
/fan multi off
/set fan_limit 8
```

- Một tab: 36h / 8h mỗi ngày ≈ 4,5 ngày/channel.
- Multi-tab: farm nhiều channel song song, nhưng tổng thời gian watch bị cộng dồn.
- Cùng channel mở nhiều tab: chỉ session primary được credit.
- Anti-cheat: >8h warning, >12h flag, >20h violation.

## Ghi chú bảo mật

- `accounts.json` lưu password để tự re-login; file mode `600`, thư mục `700`.
- `/login` gửi password qua Telegram; nên xóa tin nhắn sau khi login.
- Không commit `.env`, token, state.
