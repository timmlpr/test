"""Quota manager: counts requests per source per day (persisted), throttles, records errors."""
from __future__ import annotations

from sqlalchemy import select

from app.adapters.base import QuotaExceeded
from app.core.clock import utcnow
from app.db import SessionLocal
from app.models import QuotaUsage


class QuotaManager:
    def _row(self, db, source: str, day: str) -> QuotaUsage:
        row = db.scalar(select(QuotaUsage).where(QuotaUsage.source == source, QuotaUsage.day == day))
        if row is None:
            row = QuotaUsage(source=source, day=day, count=0, errors=0)
            db.add(row)
        return row

    def take(self, source: str, per_day: int) -> None:
        day = utcnow().strftime("%Y-%m-%d")
        with SessionLocal() as db:
            row = self._row(db, source, day)
            if row.count >= per_day:
                raise QuotaExceeded(source, "quota_exceeded")
            row.count += 1
            db.commit()

    def error(self, source: str) -> None:
        day = utcnow().strftime("%Y-%m-%d")
        with SessionLocal() as db:
            self._row(db, source, day).errors += 1
            db.commit()

    def usage(self, source: str) -> tuple[int, int]:
        day = utcnow().strftime("%Y-%m-%d")
        with SessionLocal() as db:
            row = db.scalar(select(QuotaUsage).where(QuotaUsage.source == source, QuotaUsage.day == day))
            return (row.count, row.errors) if row else (0, 0)


quota = QuotaManager()


def first_available(adapters, call):
    """Fallback chain: try each enabled adapter in order; return (adapter_name, result, errors)."""
    from app.adapters.base import SourceUnavailable

    errors = []
    for a in adapters:
        if not a.enabled():
            continue
        try:
            return a.meta.name, call(a), errors
        except SourceUnavailable as e:
            errors.append({"source": e.source, "reason": e.reason})
    return None, None, errors
