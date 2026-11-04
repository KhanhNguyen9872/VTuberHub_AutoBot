"""Composed per-user worker."""
from __future__ import annotations

from ..bot.commands import CommandsMixin
from ..bot.views import ViewsMixin
from .base import BaseWorker
from .fan import FanMixin
from .favorite import FavoriteMixin
from .loops import LoopsMixin
from .online import OnlineMixin
from .tasks import TasksMixin
from .watch import WatchMixin


class Daemon(
    BaseWorker,
    TasksMixin,
    WatchMixin,
    FavoriteMixin,
    OnlineMixin,
    FanMixin,
    LoopsMixin,
    ViewsMixin,
    CommandsMixin,
):
    """One isolated automation runtime for one Telegram chat."""
