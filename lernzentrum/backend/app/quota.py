"""Per-provider quota manager (RPM, RPD, audio seconds) persisted in the DB.

Free-tier defaults come from `config.DEFAULT_QUOTAS`; the user can override them in settings
(`settings["quotas"][provider][metric]`). Daily windows reset at midnight Pacific time for Gemini and UTC for Groq –
we use UTC for both and keep a 5 % safety margin, which is conservative enough.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import DEFAULT_QUOTAS
from .models import QuotaUsage, User

SAFETY = 0.95


class QuotaExceeded(Exception):
    def __init__(self, provider: str, metric: str, retry_after_s: int) -> None:
        super().__init__(f"{provider}: Kontingent {metric} erschöpft")
        self.provider, self.metric, self.retry_after_s = provider, metric, retry_after_s


@dataclass
class QuotaState:
    provider: str
    metric: str
    used: float
    limit: float

    @property
    def remaining(self) -> float:
        return max(0.0, self.limit - self.used)


def _windows(now: datetime) -> dict[str, tuple[str, int]]:
    """metric -> (window key, seconds until reset)."""
    sec_left_min = 60 - now.second
    sec_left_hour = 3600 - now.minute * 60 - now.second
    sec_left_day = 86400 - now.hour * 3600 - now.minute * 60 - now.second
    return {
        "rpm": (now.strftime("%Y-%m-%dT%H:%M"), sec_left_min),
        "rpd": (now.strftime("%Y-%m-%d"), sec_left_day),
        "audio_s_hour": (now.strftime("%Y-%m-%dT%H"), sec_left_hour),
        "audio_s_day": (now.strftime("%Y-%m-%d") + "a", sec_left_day),
    }


def limits_for(user: User, provider: str) -> dict[str, float]:
    base = dict(DEFAULT_QUOTAS.get(provider, {}))
    base.update((user.settings or {}).get("quotas", {}).get(provider, {}))
    return base


def _row(db: Session, user_id: int, provider: str, metric: str, window: str) -> QuotaUsage:
    row = db.scalar(select(QuotaUsage).where(QuotaUsage.user_id == user_id, QuotaUsage.provider == provider,
                                             QuotaUsage.metric == metric, QuotaUsage.window == window))
    if row is None:
        row = QuotaUsage(user_id=user_id, provider=provider, metric=metric, window=window, count=0)
        db.add(row)
        db.flush()
    return row


def acquire(db: Session, user: User, provider: str, *, requests: int = 1, audio_s: float = 0.0,
            now: datetime | None = None) -> None:
    """Reserve quota or raise QuotaExceeded. Commits the counter update with the caller's transaction."""
    now = now or datetime.now(timezone.utc)
    limits = limits_for(user, provider)
    wins = _windows(now)
    planned: list[tuple[QuotaUsage, float]] = []
    for metric, limit in limits.items():
        amount = audio_s if metric.startswith("audio") else requests
        if amount <= 0:
            continue
        window, reset = wins[metric]
        row = _row(db, user.id, provider, metric, window)
        if row.count + amount > limit * SAFETY:
            raise QuotaExceeded(provider, metric, reset)
        planned.append((row, amount))
    for row, amount in planned:
        row.count += amount
    db.flush()


def snapshot(db: Session, user: User, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    wins = _windows(now)
    out = []
    for provider in DEFAULT_QUOTAS:
        for metric, limit in limits_for(user, provider).items():
            window, reset = wins[metric]
            row = db.scalar(select(QuotaUsage).where(QuotaUsage.user_id == user.id, QuotaUsage.provider == provider,
                                                     QuotaUsage.metric == metric, QuotaUsage.window == window))
            used = row.count if row else 0
            out.append({"provider": provider, "metric": metric, "used": round(used, 1), "limit": limit,
                        "reset_in_s": reset, "exhausted": used >= limit * SAFETY})
    return out
