"""Waitlist with double opt-in, invite codes & waves, feedback, abuse reports."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.crypto import lookup_hash
from app.core.deps import client_ip, optional_user, req_ip_hash
from app.core.errors import ApiError
from app.core.mailer import send_mail
from app.db import get_db
from app.models import (
    AbuseReport,
    ConsentLog,
    Feedback,
    InviteCode,
    User,
    WaitlistEntry,
    now,
)
from app.settings import brand, get_settings

router = APIRouter(tags=["growth"])


class WaitIn(BaseModel):
    email: EmailStr
    consent: bool
    website: str | None = None  # honeypot – bots fill it, humans never see it


@router.post("/waitlist")
def waitlist(body: WaitIn, request: Request, db: Session = Depends(get_db)):
    ratelimit.hit(f"wait:{client_ip(request)}", 5, 3600)
    if body.website:
        return {"ok": True}  # silently drop bots
    if not body.consent:
        raise ApiError(400, "consent_required")
    h = lookup_hash(body.email)
    e = db.scalar(select(WaitlistEntry).where(WaitlistEntry.email_hash == h))
    if not e:
        e = WaitlistEntry(email=body.email.lower(), email_hash=h)
        db.add(e)
        db.add(ConsentLog(kind="waitlist", subject_ref=h[:16], ip_hash=req_ip_hash(request)))
        db.flush()  # populate token default
    if not e.confirmed_at:
        send_mail(body.email, f"{brand()['name']}: Bitte bestätige deine Anmeldung",
                  f"Du möchtest auf die Warteliste von {brand()['name']}? Dann bestätige hier:\n"
                  f"{get_settings().public_url}/waitlist/confirm?token={e.token}\n\nOhne Bestätigung speichern wir nichts dauerhaft "
                  "(unbestätigte Einträge werden nach 7 Tagen gelöscht).")
    db.commit()
    return {"ok": True}


class TokenIn(BaseModel):
    token: str


@router.post("/waitlist/confirm")
def waitlist_confirm(body: TokenIn, db: Session = Depends(get_db)):
    e = db.scalar(select(WaitlistEntry).where(WaitlistEntry.token == body.token))
    if not e:
        raise ApiError(400, "invalid_or_expired_token")
    e.confirmed_at = e.confirmed_at or now()
    db.commit()
    return {"ok": True}


@router.post("/waitlist/unsubscribe")
def waitlist_unsub(body: TokenIn, db: Session = Depends(get_db)):
    e = db.scalar(select(WaitlistEntry).where(WaitlistEntry.token == body.token))
    if e:
        db.delete(e)
        db.commit()
    return {"ok": True}


class InviteCheckIn(BaseModel):
    code: str = Field(max_length=32)


@router.post("/invite/check")
def invite_check(body: InviteCheckIn, db: Session = Depends(get_db)):
    c = db.get(InviteCode, body.code.strip().upper())
    return {"valid": bool(c and c.used < c.max_uses), "wave": c.wave if c else None}


class FeedbackIn(BaseModel):
    message: str = Field(min_length=3, max_length=4000)
    page: str | None = Field(default=None, max_length=128)
    rating: int | None = Field(default=None, ge=1, le=5)


@router.post("/feedback")
def feedback(body: FeedbackIn, request: Request, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    ratelimit.hit(f"fb:{client_ip(request)}", 10, 3600)
    db.add(Feedback(user_id=user.id if user else None, page=body.page, rating=body.rating, message=body.message))
    db.commit()
    return {"ok": True}


class AbuseIn(BaseModel):
    message: str = Field(min_length=10, max_length=4000)
    contact: str | None = Field(default=None, max_length=200)


@router.post("/abuse")
def abuse(body: AbuseIn, request: Request, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    """Anyone (also non-users) can report suspected misuse, e.g. 'someone searched for me'."""
    ratelimit.hit(f"abuse:{client_ip(request)}", 5, 3600)
    db.add(AbuseReport(reporter_user_id=user.id if user else None, contact=body.contact, message=body.message))
    db.commit()
    return {"ok": True}
