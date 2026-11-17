"""Background jobs (APScheduler, in-process): monitor, reminders, retention limits."""
from __future__ import annotations

import logging
import os
from datetime import timedelta

from sqlalchemy import delete, select

from app.core.events import notify
from app.core.mailer import send_mail
from app.db import SessionLocal
from app.models import (
    AiCache,
    AuditLog,
    DeletionRequest,
    Finding,
    Notification,
    OneTimeToken,
    Reminder,
    Upload,
    User,
    WaitlistEntry,
    now,
)
from app.settings import brand, get_settings

log = logging.getLogger("fadeprint.jobs")

RETENTION = {  # documented in docs/PRIVACY.md (deletion & retention concept)
    "trash_days": 30, "waitlist_unconfirmed_days": 7, "ai_cache_days": 30, "audit_days": 365, "notifications_days": 180,
}


def reminders() -> int:
    n = 0
    with SessionLocal() as db:
        for r in db.scalars(select(DeletionRequest).where(DeletionRequest.status == "sent", DeletionRequest.due_at < now(),
                                                          DeletionRequest.reminded_at.is_(None))).all():
            user = db.get(User, r.user_id)
            notify(db, r.user_id, "Frist abgelaufen", f"{r.recipient} hat die Frist für deine Anfrage überschritten. "
                                                       "Du kannst nachfassen oder dich bei der Datenschutzbehörde beschweren.", "medium",
                   f"/app/requests?id={r.id}")
            send_mail(user.email, f"{brand()['name']}: Frist abgelaufen", f"Die Frist für deine Anfrage an {r.recipient} ist abgelaufen.\n"
                                                                          f"{get_settings().public_url}/app/requests")
            r.reminded_at = now()
            n += 1
        for rem in db.scalars(select(Reminder).where(Reminder.done.is_(False), Reminder.notified.is_(False), Reminder.due_at < now())).all():
            notify(db, rem.user_id, "Erinnerung", rem.title, "low", "/app/documents")
            rem.notified = True
            n += 1
        db.commit()
    return n


def retention() -> dict:
    t = now()
    out = {}
    with SessionLocal() as db:
        out["trash"] = db.execute(delete(Finding).where(Finding.status == "trash", Finding.trashed_at < t - timedelta(days=RETENTION["trash_days"]))).rowcount
        out["waitlist"] = db.execute(delete(WaitlistEntry).where(WaitlistEntry.confirmed_at.is_(None),
                                                                 WaitlistEntry.created_at < t - timedelta(days=RETENTION["waitlist_unconfirmed_days"]))).rowcount
        out["tokens"] = db.execute(delete(OneTimeToken).where(OneTimeToken.expires_at < t)).rowcount
        out["ai_cache"] = db.execute(delete(AiCache).where(AiCache.created_at < t - timedelta(days=RETENTION["ai_cache_days"]))).rowcount
        out["audit"] = db.execute(delete(AuditLog).where(AuditLog.created_at < t - timedelta(days=RETENTION["audit_days"]))).rowcount
        out["notifications"] = db.execute(delete(Notification).where(Notification.created_at < t - timedelta(days=RETENTION["notifications_days"]))).rowcount
        for up in db.scalars(select(Upload).where(Upload.expires_at < t)).all():
            try:
                os.remove(up.path)
            except OSError:
                pass
            db.delete(up)
        db.commit()
    return out


def start_scheduler():
    from apscheduler.schedulers.background import BackgroundScheduler

    from app.modules.monitor import scheduled_monitor

    sched = BackgroundScheduler(timezone="Europe/Berlin")
    sched.add_job(scheduled_monitor, "interval", hours=1, id="monitor", max_instances=1, coalesce=True)
    sched.add_job(reminders, "interval", minutes=30, id="reminders", max_instances=1, coalesce=True)
    sched.add_job(retention, "cron", hour=3, minute=17, id="retention")
    sched.start()
    return sched
