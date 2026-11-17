"""Family plan: members join only with their own confirmed consent (invite link + own login).
Child profiles (<16) only by a guardian with an explicit consent notice (Art. 8 GDPR)."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.crypto import lookup_hash
from app.core.deps import current_user, req_ip_hash
from app.core.errors import ApiError
from app.core.security import hash_password
from app.db import get_db
from app.models import ConsentLog, FamilyGroup, FamilyMember, User
from app.settings import get_settings

router = APIRouter(prefix="/family", tags=["family"])


def _group(db: Session, user: User) -> FamilyGroup:
    g = db.scalar(select(FamilyGroup).where(FamilyGroup.owner_id == user.id))
    if not g or user.plan != "family_owner":
        raise ApiError(402, "family_plan_required")
    return g


def _members(db: Session, g: FamilyGroup) -> list[FamilyMember]:
    return db.scalars(select(FamilyMember).where(FamilyMember.group_id == g.id, FamilyMember.status != "removed")).all()


@router.get("")
def get_family(user: User = Depends(current_user), db: Session = Depends(get_db)):
    g = db.scalar(select(FamilyGroup).where(FamilyGroup.owner_id == user.id))
    if not g:
        m = db.scalar(select(FamilyMember).where(FamilyMember.user_id == user.id, FamilyMember.status == "active"))
        return {"role": "member" if m else "none"}
    ms = _members(db, g)
    return {"role": "owner", "seats": g.seats, "used": 1 + len(ms),
            "members": [{"id": m.id, "label": m.label, "status": m.status, "is_child": m.is_child,
                         "invite_link": f"{get_settings().public_url}/family/join?token={m.invite_token}" if m.status == "invited" else None}
                        for m in ms]}


class InviteIn(BaseModel):
    label: str = Field(max_length=60)


@router.post("/invite")
def invite(body: InviteIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    g = _group(db, user)
    if 1 + len(_members(db, g)) >= g.seats:
        raise ApiError(400, "no_free_seat")
    m = FamilyMember(group_id=g.id, invite_token=secrets.token_urlsafe(24), label=body.label, status="invited")
    db.add(m)
    db.commit()
    return {"id": m.id, "invite_link": f"{get_settings().public_url}/family/join?token={m.invite_token}"}


class JoinIn(BaseModel):
    token: str
    consent: bool  # member confirms they want to join and understand what the owner can see (only seat usage)


@router.post("/join")
def join(body: JoinIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not body.consent:
        raise ApiError(400, "consent_required")
    m = db.scalar(select(FamilyMember).where(FamilyMember.invite_token == body.token, FamilyMember.status == "invited"))
    if not m:
        raise ApiError(400, "invalid_or_expired_token")
    g = db.get(FamilyGroup, m.group_id)
    if g.owner_id == user.id:
        raise ApiError(400, "cannot_join_own_family")
    m.user_id, m.status, m.invite_token = user.id, "active", None
    if user.plan == "free":
        user.plan = "family_member"
    db.add(ConsentLog(user_id=user.id, kind="family_join", subject_ref=g.id, ip_hash=req_ip_hash(request)))
    audit(db, "family.join", user.id)
    db.commit()
    return {"ok": True}


class ChildIn(BaseModel):
    label: str = Field(max_length=60)
    login_email: str = Field(max_length=200)
    password: str = Field(min_length=10, max_length=256)
    birth_year: int = Field(ge=2000, le=2030)
    guardian_consent: bool


@router.post("/child")
def add_child(body: ChildIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Guardian creates a child profile. The child gets an own login; guardian consent is logged."""
    g = _group(db, user)
    if not body.guardian_consent:
        raise ApiError(400, "guardian_consent_required")
    if 1 + len(_members(db, g)) >= g.seats:
        raise ApiError(400, "no_free_seat")
    if db.scalar(select(User).where(User.email_hash == lookup_hash(body.login_email))):
        raise ApiError(409, "email_taken")
    child = User(email=body.login_email.lower(), email_hash=lookup_hash(body.login_email), password_hash=hash_password(body.password),
                 email_verified=True, is_child=True, guardian_id=user.id, plan="family_member", display_name=body.label)
    db.add(child)
    db.flush()
    db.add(FamilyMember(group_id=g.id, user_id=child.id, label=body.label, status="active", is_child=True))
    db.add(ConsentLog(user_id=user.id, kind="guardian", subject_ref=child.id, ip_hash=req_ip_hash(request)))
    audit(db, "family.child_created", user.id)
    db.commit()
    return {"ok": True, "child_id": child.id}


@router.delete("/members/{mid}")
def remove_member(mid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    g = _group(db, user)
    m = db.get(FamilyMember, mid)
    if not m or m.group_id != g.id:
        raise ApiError(404, "not_found")
    m.status = "removed"
    if m.user_id and (mu := db.get(User, m.user_id)) and mu.plan == "family_member":
        mu.plan = "free"
    db.commit()
    return {"ok": True}


@router.post("/leave")
def leave(user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = db.scalar(select(FamilyMember).where(FamilyMember.user_id == user.id, FamilyMember.status == "active"))
    if not m:
        raise ApiError(404, "not_found")
    m.status = "removed"
    if user.plan == "family_member":
        user.plan = "free"
    db.commit()
    return {"ok": True}
