from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.errors import ApiError
from app.core.plans import limit
from app.models import UserUsage


def consume(db: Session, user, feature: str, limit_key: str, per: str = "day") -> int:
    """Increment a per-user counter and enforce the plan limit. Returns remaining."""
    cap = int(limit(user, limit_key))
    period = utcnow().strftime("%Y-%m-%d" if per == "day" else "%Y-%m")
    row = db.scalar(select(UserUsage).where(UserUsage.user_id == user.id, UserUsage.feature == feature, UserUsage.period == period))
    if row is None:
        row = UserUsage(user_id=user.id, feature=feature, period=period, count=0)
        db.add(row)
    if row.count >= cap:
        raise ApiError(402 if cap == 0 else 429, "plan_limit", feature=feature, limit=cap, per=per)
    row.count += 1
    db.flush()
    return cap - row.count


def remaining(db: Session, user, feature: str, limit_key: str, per: str = "day") -> int:
    cap = int(limit(user, limit_key))
    period = utcnow().strftime("%Y-%m-%d" if per == "day" else "%Y-%m")
    row = db.scalar(select(UserUsage).where(UserUsage.user_id == user.id, UserUsage.feature == feature, UserUsage.period == period))
    return cap - (row.count if row else 0)
