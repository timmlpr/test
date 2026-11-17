"""Admin area (role=admin AND TOTP-verified session): keys, quotas, waitlist waves, invite codes, audit, abuse."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters import registry
from app.adapters.base import SourceUnavailable
from app.core.audit import audit
from app.core.deps import admin_user
from app.core.errors import ApiError
from app.core.mailer import send_mail
from app.db import get_db
from app.models import (
    AbuseReport,
    AuditLog,
    Feedback,
    Finding,
    InviteCode,
    SourceKey,
    Subscription,
    User,
    Voucher,
    WaitlistEntry,
    now,
)
from app.settings import brand, get_settings

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats")
def stats(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    return {"users": db.scalar(select(func.count(User.id))), "locked": db.scalar(select(func.count(User.id)).where(User.locked.is_(True))),
            "premium": db.scalar(select(func.count(Subscription.id)).where(Subscription.status.in_(["active", "trialing"]))),
            "findings": db.scalar(select(func.count(Finding.id))),
            "waitlist": db.scalar(select(func.count(WaitlistEntry.id)).where(WaitlistEntry.confirmed_at.is_not(None))),
            "abuse_open": db.scalar(select(func.count(AbuseReport.id)).where(AbuseReport.status == "new"))}


@router.get("/sources")
def sources(_: User = Depends(admin_user)):
    return registry.describe()


class KeyIn(BaseModel):
    value: str = Field(min_length=4, max_length=500)


@router.put("/keys/{source}")
def put_key(source: str, body: KeyIn, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    if source not in registry.ADAPTERS or not registry.ADAPTERS[source].meta.permitted:
        raise ApiError(400, "unknown_or_not_permitted")
    row = db.get(SourceKey, source) or SourceKey(source=source, value="")
    row.value, row.enabled, row.updated_at = body.value.strip(), True, now()
    db.merge(row)
    audit(db, "admin.key_set", admin.id, source=source)
    db.commit()
    return {"ok": True}


@router.delete("/keys/{source}")
def delete_key(source: str, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    row = db.get(SourceKey, source)
    if row:
        db.delete(row)
        audit(db, "admin.key_deleted", admin.id, source=source)
        db.commit()
    return {"ok": True}


@router.post("/keys/{source}/test")
def test_key(source: str, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    a = registry.ADAPTERS.get(source)
    if not a:
        raise ApiError(404, "not_found")
    try:
        result = a.test()
    except SourceUnavailable as e:
        result = f"error: {e.reason}"
    row = db.get(SourceKey, source)
    if row:
        row.last_test = f"{now():%Y-%m-%d %H:%M} {result}"
        db.commit()
    return {"result": result}


@router.get("/audit")
def audit_log(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(300)).all()
    return [{"at": r.created_at, "user_id": r.user_id, "action": r.action, "meta": r.meta} for r in rows]


@router.get("/waitlist")
def waitlist(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(WaitlistEntry).order_by(WaitlistEntry.created_at)).all()
    return [{"id": r.id, "email": r.email, "confirmed": r.confirmed_at is not None, "wave": r.wave, "approved": r.approved,
             "invite_code": r.invite_code, "created_at": r.created_at} for r in rows]


class WaveIn(BaseModel):
    wave: int = Field(ge=1)
    cap: int = Field(ge=1, le=1000)


@router.post("/waitlist/approve")
def approve_wave(body: WaveIn, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    """Approve the next `cap` confirmed entries (FIFO) into wave N and send each a personal invite code."""
    rows = db.scalars(select(WaitlistEntry).where(WaitlistEntry.confirmed_at.is_not(None), WaitlistEntry.approved.is_(False))
                      .order_by(WaitlistEntry.created_at).limit(body.cap)).all()
    for r in rows:
        code = secrets.token_hex(4).upper()
        db.add(InviteCode(code=code, wave=body.wave, max_uses=1))
        r.approved, r.wave, r.invite_code = True, body.wave, code
        send_mail(r.email, f"{brand()['name']}: Du bist dabei!",
                  f"Dein Einladungscode: {code}\nRegistrieren: {get_settings().public_url}/register?invite={code}")
    audit(db, "admin.wave_approved", admin.id, wave=body.wave, count=len(rows))
    db.commit()
    return {"approved": len(rows)}


class CodesIn(BaseModel):
    wave: int = 1
    count: int = Field(ge=1, le=500)
    max_uses: int = Field(default=1, ge=1, le=1000)


@router.post("/invite-codes")
def invite_codes(body: CodesIn, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    codes = []
    for _ in range(body.count):
        c = secrets.token_hex(4).upper()
        db.add(InviteCode(code=c, wave=body.wave, max_uses=body.max_uses))
        codes.append(c)
    db.commit()
    return {"codes": codes}


class VoucherIn(BaseModel):
    code: str = Field(min_length=4, max_length=32)
    free_months: int = Field(ge=1, le=12)
    max_uses: int = Field(ge=1, le=100000)


@router.post("/vouchers")
def create_voucher(body: VoucherIn, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    db.merge(Voucher(code=body.code.upper(), free_months=body.free_months, max_uses=body.max_uses))
    db.commit()
    return {"ok": True}


@router.get("/feedback")
def list_feedback(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    return [{"at": f.created_at, "page": f.page, "rating": f.rating, "message": f.message}
            for f in db.scalars(select(Feedback).order_by(Feedback.created_at.desc()).limit(200))]


@router.get("/abuse")
def list_abuse(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    return [{"id": a.id, "at": a.created_at, "contact": a.contact, "message": a.message, "status": a.status}
            for a in db.scalars(select(AbuseReport).order_by(AbuseReport.created_at.desc()).limit(200))]


class UnlockIn(BaseModel):
    user_id: str


@router.post("/users/unlock")
def unlock_user(body: UnlockIn, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    u = db.get(User, body.user_id)
    if not u:
        raise ApiError(404, "not_found")
    u.locked, u.lock_reason = False, None
    audit(db, "admin.user_unlocked", admin.id, target=u.id)
    db.commit()
    return {"ok": True}


@router.get("/users/locked")
def locked_users(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    return [{"id": u.id, "reason": u.lock_reason, "created_at": u.created_at} for u in db.scalars(select(User).where(User.locked.is_(True)))]
