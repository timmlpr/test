"""Collect (Art. 20) and purge (Art. 17) all data of one user."""
from __future__ import annotations

import os

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import models as m
from app.core.audit import audit

USER_TABLES = [m.Identifier, m.ConsentLog, m.Scan, m.Finding, m.RiskSnapshot, m.DeletionRequest, m.Subscription, m.Purchase,
               m.ChecklistState, m.Notification, m.TimelineEvent, m.MailSubscription, m.Document, m.Reminder, m.FamilyTreePerson,
               m.Report, m.OAuthAccount, m.Passkey, m.PushSubscription, m.Upload]
SKIP_COLS = {"password_hash", "totp_secret", "recovery_codes", "code_hash", "public_key", "email_hash", "value_hash", "keys"}


def _row(obj) -> dict:
    out = {}
    for c in obj.__table__.columns:
        if c.name in SKIP_COLS:
            continue
        v = getattr(obj, c.name)
        out[c.name] = v.isoformat() if hasattr(v, "isoformat") else v
    return out


def collect(db: Session, user: m.User) -> dict:
    data = {"user": _row(user)}
    for t in USER_TABLES:
        data[t.__tablename__] = [_row(r) for r in db.scalars(select(t).where(t.user_id == user.id))]
    vault = db.get(m.EstateVault, user.id)
    data["estate_vault"] = _row(vault) if vault else None
    ms = db.get(m.MonitorSettings, user.id)
    data["monitor_settings"] = _row(ms) if ms else None
    return data


def purge(db: Session, user: m.User) -> None:
    for up in db.scalars(select(m.Upload).where(m.Upload.user_id == user.id)):
        try:
            os.remove(up.path)
        except OSError:
            pass
    uid = user.id
    for t in USER_TABLES:
        db.execute(delete(t).where(t.user_id == uid))
    db.execute(delete(m.UserUsage).where(m.UserUsage.user_id == uid))
    db.execute(delete(m.AiUsage).where(m.AiUsage.user_id == uid))
    for extra in (m.EstateVault, m.MonitorSettings):
        if (row := db.get(extra, uid)) is not None:
            db.delete(row)
    grp = db.scalar(select(m.FamilyGroup).where(m.FamilyGroup.owner_id == uid))
    if grp:
        db.delete(grp)
    db.execute(delete(m.FamilyMember).where(m.FamilyMember.user_id == uid))
    db.delete(user)
    audit(db, "profile.account_deleted", None)  # no user id kept
    db.commit()
