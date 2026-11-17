"""M-05 monitor (premium): scheduled re-scans, 'new since last check', web push + email with severity filter and
quiet hours. M-15 timeline and notifications."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import current_user, require_feature
from app.core.events import notify
from app.core.mailer import send_mail
from app.db import SessionLocal, get_db
from app.models import (
    Finding,
    MonitorSettings,
    Notification,
    PushSubscription,
    Scan,
    TimelineEvent,
    User,
    now,
)
from app.settings import brand, get_settings

router = APIRouter(tags=["monitor"])
log = logging.getLogger("fadeprint.monitor")
SEV = {"low": 0, "medium": 1, "high": 2}


def _settings(db: Session, user: User) -> MonitorSettings:
    s = db.get(MonitorSettings, user.id)
    if not s:
        s = MonitorSettings(user_id=user.id)
        db.add(s)
        db.flush()
    return s


def _view(s: MonitorSettings) -> dict:
    return {k: getattr(s, k) for k in ("enabled", "frequency", "min_severity", "quiet_start", "quiet_end", "push", "email", "last_run")}


@router.get("/monitor/settings")
def get_monitor(user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = _settings(db, user)
    db.commit()
    return {**_view(s), "vapid_public_key": get_settings().vapid_public_key or None}


class MonitorIn(BaseModel):
    enabled: bool
    frequency: str = Field(pattern="^(daily|weekly)$")
    min_severity: str = Field(pattern="^(low|medium|high)$")
    quiet_start: int = Field(ge=0, le=23)
    quiet_end: int = Field(ge=0, le=23)
    push: bool
    email: bool


@router.put("/monitor/settings")
def put_monitor(body: MonitorIn, user: User = Depends(require_feature("monitor")), db: Session = Depends(get_db)):
    s = _settings(db, user)
    for k, v in body.model_dump().items():
        setattr(s, k, v)
    db.commit()
    return _view(s)


def in_quiet_hours(hour: int, start: int, end: int) -> bool:
    if start == end:
        return False
    if start > end:  # spans midnight, e.g. 22–7
        return hour >= start or hour < end
    return start <= hour < end


def run_monitor_for(db: Session, user: User, force_hour: int | None = None) -> dict:
    """Re-scan all verified identifiers, diff against existing findings, alert per settings."""
    from app.models import Identifier
    from app.modules.findings_service import snapshot
    from app.modules.scan import run_privacy_scan

    s = _settings(db, user)
    idents = [i for i in db.scalars(select(Identifier).where(Identifier.user_id == user.id)) if i.verified_at]
    scan = Scan(user_id=user.id, kind="monitor")
    db.add(scan)
    db.flush()
    before = now()
    res = run_privacy_scan(db, user, idents, scan, deep=False) if idents else {"new": 0, "errors": [], "sources": []}
    scan.summary, scan.new_count = res, res["new"]
    s.last_run = now()
    new = db.scalars(select(Finding).where(Finding.user_id == user.id, Finding.scan_id == scan.id, Finding.created_at >= before)).all()
    relevant = [f for f in new if SEV[f.risk] >= SEV[s.min_severity]]
    snapshot(db, user)
    if relevant:
        title = f"{len(relevant)} neue Funde seit dem letzten Check"
        body = "; ".join(f.title for f in relevant[:3])
        worst = max(relevant, key=lambda f: SEV[f.risk]).risk
        n = notify(db, user.id, title, body, worst, "/app/results?new=1")
        hour = force_hour if force_hour is not None else datetime.now().hour
        if not in_quiet_hours(hour, s.quiet_start, s.quiet_end):
            if s.push:
                send_push(db, user, title, body)
            if s.email:
                send_mail(user.email, f"{brand()['name']}: {title}", f"{body}\n\nDetails: {get_settings().public_url}/app/results")
        else:
            n.body += " (Benachrichtigung wegen Ruhezeit zurückgehalten)"
    db.commit()
    return {"new": res["new"], "alerted": len(relevant)}


@router.post("/monitor/run")
def monitor_run(user: User = Depends(require_feature("monitor")), db: Session = Depends(get_db)):
    from app.core import ratelimit

    ratelimit.hit(f"monitor:{user.id}", 3, 3600)
    return run_monitor_for(db, user)


def scheduled_monitor() -> None:
    """APScheduler job: hourly; runs users whose frequency is due."""
    from app.core.plans import has_feature

    with SessionLocal() as db:
        for s in db.scalars(select(MonitorSettings).where(MonitorSettings.enabled.is_(True))).all():
            due = timedelta(days=1 if s.frequency == "daily" else 7)
            if s.last_run and now() - s.last_run < due:
                continue
            user = db.get(User, s.user_id)
            if user and has_feature(user, "monitor") and not user.locked:
                try:
                    run_monitor_for(db, user)
                except Exception:  # noqa: BLE001 – one user's failure must not stop the loop
                    log.exception("monitor run failed")
                    db.rollback()


def send_push(db: Session, user: User, title: str, body: str) -> int:
    s = get_settings()
    if not (s.vapid_private_key and s.vapid_public_key):
        return 0
    from pywebpush import WebPushException, webpush

    sent = 0
    for sub in db.scalars(select(PushSubscription).where(PushSubscription.user_id == user.id)).all():
        try:
            webpush({"endpoint": sub.endpoint, "keys": json.loads(sub.keys)}, json.dumps({"title": title, "body": body, "url": "/app"}),
                    vapid_private_key=s.vapid_private_key, vapid_claims={"sub": f"mailto:{brand()['support_email']}"})
            sent += 1
        except WebPushException as e:
            if e.response is not None and e.response.status_code in (404, 410):
                db.delete(sub)
    return sent


class PushIn(BaseModel):
    endpoint: str = Field(max_length=1000)
    keys: dict


@router.post("/push/subscribe")
def push_subscribe(body: PushIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.add(PushSubscription(user_id=user.id, endpoint=body.endpoint, keys=json.dumps(body.keys)))
    db.commit()
    return {"ok": True}


@router.get("/notifications")
def notifications(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(50)).all()
    return {"items": [{"id": n.id, "title": n.title, "body": n.body, "severity": n.severity, "read": n.read, "link": n.link,
                       "created_at": n.created_at} for n in rows], "unread": sum(not n.read for n in rows)}


@router.post("/notifications/read")
def notifications_read(user: User = Depends(current_user), db: Session = Depends(get_db)):
    for n in db.scalars(select(Notification).where(Notification.user_id == user.id, Notification.read.is_(False))):
        n.read = True
    db.commit()
    return {"ok": True}


@router.get("/timeline")
def get_timeline(user: User = Depends(current_user), db: Session = Depends(get_db), until: datetime | None = None,
                 kind: str | None = None, limit: int = Query(default=300, le=1000)):
    stmt = select(TimelineEvent).where(TimelineEvent.user_id == user.id)
    if until:
        stmt = stmt.where(TimelineEvent.at <= until)
    if kind:
        stmt = stmt.where(TimelineEvent.kind == kind)
    rows = db.scalars(stmt.order_by(TimelineEvent.at.desc()).limit(limit)).all()
    first = db.scalar(select(TimelineEvent.at).where(TimelineEvent.user_id == user.id).order_by(TimelineEvent.at).limit(1))
    return {"items": [{"id": e.id, "kind": e.kind, "title": e.title, "ref": e.ref, "risk": e.risk, "at": e.at} for e in rows],
            "range": {"from": first, "to": now()}}
