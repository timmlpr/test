from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Notification, TimelineEvent


def timeline(db: Session, user_id: str, kind: str, title: str, ref: str | None = None, risk: str | None = None) -> None:
    db.add(TimelineEvent(user_id=user_id, kind=kind, title=title[:200], ref=ref, risk=risk))


def notify(db: Session, user_id: str, title: str, body: str, severity: str = "low", link: str | None = None) -> Notification:
    n = Notification(user_id=user_id, title=title[:160], body=body, severity=severity, link=link)
    db.add(n)
    return n
