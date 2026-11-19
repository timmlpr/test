"""Moodle connection endpoints. The password is accepted once, exchanged for a token and discarded."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import moodle
from ..calendar_sync import IcsError, normalize_url, sync_calendar
from ..db import get_db
from ..jobs import enqueue
from ..models import Calendar, User
from ..providers import registry
from ..security import audit, client_ip, current_user, limiter

router = APIRouter(prefix="/api/moodle", tags=["moodle"])


class SiteIn(BaseModel):
    site: str = "https://moodle.thm.de"


@router.post("/detect")
def detect(body: SiteIn, user: User = Depends(current_user)) -> dict:
    return moodle.detect(body.site)


class PasswordIn(BaseModel):
    site: str
    username: str
    password: str


@router.post("/link/password")
def link_password(body: PasswordIn, request: Request, user: User = Depends(current_user),
                  db: Session = Depends(get_db)) -> dict:
    limiter.check(f"moodle:{client_ip(request)}", 6, 600)
    try:
        token = moodle.exchange_password(body.site, body.username, body.password)
    except moodle.MoodleError as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        body.password = ""  # drop the password reference immediately; it is never stored or logged
    try:
        info = moodle.link(db, user, body.site, token)
    except moodle.MoodleError as exc:
        raise HTTPException(422, str(exc)) from exc
    audit(db, user.id, "moodle_linked", "password-exchange")
    enqueue(db, "moodle.sync", {}, user_id=user.id, label="Moodle: erster Abgleich")
    db.commit()
    return {"ok": True, **info}


class TokenIn(BaseModel):
    site: str
    token: str


@router.post("/link/token")
def link_token(body: TokenIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    try:
        token = moodle.parse_pasted_token(body.token)
        info = moodle.link(db, user, body.site, token)
    except moodle.MoodleError as exc:
        raise HTTPException(422, str(exc)) from exc
    audit(db, user.id, "moodle_linked", "token")
    enqueue(db, "moodle.sync", {}, user_id=user.id, label="Moodle: erster Abgleich")
    db.commit()
    return {"ok": True, **info}


class IcsIn(BaseModel):
    url: str


@router.post("/link/ics")
def link_ics(body: IcsIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    try:
        cal = Calendar(user_id=user.id, url=normalize_url(body.url), name="Moodle-Kalender", kind="moodle")
        db.add(cal)
        db.flush()
        res = sync_calendar(db, cal)
    except IcsError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc
    _deadlines_from_moodle_ics(db, user, cal)
    db.commit()
    return {"ok": True, **res}


def _deadlines_from_moodle_ics(db: Session, user: User, cal: Calendar) -> None:
    from sqlalchemy import select

    from ..models import Deadline, Event

    for ev in db.scalars(select(Event).where(Event.calendar_id == cal.id)):
        ref = f"moodle-ics:{ev.uid}"
        if not db.scalar(select(Deadline).where(Deadline.user_id == user.id, Deadline.source_ref == ref)):
            db.add(Deadline(user_id=user.id, module_id=ev.module_id, title=ev.title, due=ev.start, source="moodle",
                            source_ref=ref, status="accepted"))


@router.get("/status")
def status(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    row = registry.get_secret_row(db, user, "moodle")
    if not row:
        return {"linked": False}
    return {"linked": True, "status": row.status, "detail": row.status_detail, "site": row.meta.get("site"),
            "sitename": row.meta.get("sitename"), "fullname": row.meta.get("fullname"),
            "last_sync": row.meta.get("last_sync"), "last_stats": row.meta.get("last_stats")}


@router.post("/sync")
def sync_now(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    if not registry.get_secret_row(db, user, "moodle"):
        raise HTTPException(409, "Moodle ist nicht verbunden.")
    job = enqueue(db, "moodle.sync", {}, user_id=user.id, label="Moodle-Abgleich")
    db.commit()
    return {"job_id": job.id}


@router.delete("/link")
def revoke(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    registry.delete_secret(db, user, "moodle")
    audit(db, user.id, "moodle_unlinked")
    db.commit()
    return {"ok": True, "hint": "Token gelöscht. Du kannst ihn zusätzlich in Moodle unter „Sicherheitsschlüssel“ "
                                "zurücksetzen."}
