"""Controle de limites diários, horário ativo e pausas aleatórias."""

from __future__ import annotations

import random
import time
from datetime import datetime

from .config import Config
from .storage import Storage


class RateLimiter:
    def __init__(self, cfg: Config, storage: Storage):
        self.cfg = cfg
        self.storage = storage
        self._caps = {
            "follow": cfg.limits.follows_per_day,
            "like": cfg.limits.likes_per_day,
            "story_like": cfg.limits.story_likes_per_day,
            "dm": cfg.limits.dms_per_day,
        }

    def remaining(self, action: str) -> int:
        return max(0, self._caps[action] - self.storage.count_today(action))

    def allowed(self, action: str) -> bool:
        return self.remaining(action) > 0


def within_active_hours(active_hours: tuple[int, int], now: datetime | None = None) -> bool:
    start, end = active_hours
    hour = (now or datetime.now()).hour
    if start <= end:
        return start <= hour < end
    return hour >= start or hour < end  # janela que passa da meia-noite


def human_pause(bounds: tuple[float, float], sleep=time.sleep) -> float:
    lo, hi = bounds
    seconds = random.uniform(lo, hi)
    sleep(seconds)
    return seconds
