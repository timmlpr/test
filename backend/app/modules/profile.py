"""Own profile & identifiers with ownership proof; settings; Art. 20 export; one-click deletion.

Ownership rules (H1):
  email   – confirmation link to that address
  phone   – one-time code via SMS adapter (or dev outbox in demo/dev)
  domain  – DNS TXT record `fadeprint-verify=<token>`
  name/city/username – own-data declaration (timestamped consent) + verified account email,
                       capped by the anomaly lock (max distinct names, config/plans.json)
"""
from __future__ import annotations

import re
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.audit import audit
from app.core.crypto import lookup_hash
from app.core.deps import current_user, req_ip_hash
from app.core.errors import ApiError
from app.core.events import timeline
from app.core.guard import check_text, is_plate_like
from app.core.mailer import send_mail
from app.core.security import SESSION_COOKIE, token_hash
from app.db import get_db
from app.models import ConsentLog, Identifier, OneTimeToken, User, now
from app.settings import brand, get_settings, plans

router = APIRouter(prefix="/profile", tags=["profile"])
KINDS = {"name", "email", "phone", "city", "username", "domain"}
VALIDATORS = {
    "email": re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$"),
    "phone": re.compile(r"^\+?[0-9 ()/-]{6,20}$"),
    "domain": re.compile(r"^(?=.{3,253}$)([a-z0-9-]{1,63}\.)+[a-z]{2,63}$"),
    "name": re.compile(r"^[\wÀ-ž' .-]{2,80}$"),
    "city": re.compile(r"^[\wÀ-ž' .-]{2,80}$"),
    "username": re.compile(r"^[\w.@-]{2,60}$"),
}


def ident_view(i: Identifier) -> dict:
    return {"id": i.id, "kind": i.kind, "value": i.value, "verified": i.verified_at is not None, "verified_at": i.verified_at,
            "own_data_confirmed_at": i.own_data_confirmed_at, "created_at": i.created_at}


def own_names(db: Session, user: User) -> list[str]:
    return [i.value for i in db.scalars(select(Identifier).where(Identifier.user_id == user.id, Identifier.kind == "name"))]


@router.get("/identifiers")
def list_identifiers(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [ident_view(i) for i in db.scalars(select(Identifier).where(Identifier.user_id == user.id).order_by(Identifier.created_at))]


class IdentIn(BaseModel):
    kind: str
    value: str = Field(min_length=2, max_length=253)
    own_data: bool  # mandatory checkbox "Das sind meine eigenen Daten"


def _normalise(kind: str, value: str) -> str:
    v = value.strip()
    if kind in ("email", "domain"):
        v = v.lower()
    if kind == "domain":
        v = re.sub(r"^https?://", "", v).split("/")[0].removeprefix("www.")
    if kind == "phone":
        v = re.sub(r"[ ()/-]", "", v)
    return v


@router.post("/identifiers")
def add_identifier(body: IdentIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ratelimit.hit(f"ident:{user.id}", 20, 3600)
    if body.kind not in KINDS:
        raise ApiError(400, "invalid_kind")
    if not body.own_data:
        raise ApiError(400, "own_data_required")
    value = _normalise(body.kind, body.value)
    if not VALIDATORS[body.kind].match(value):
        raise ApiError(400, "invalid_value")
    if body.kind in ("name", "username") and is_plate_like(value):
        raise ApiError(400, "hard_limit", category="plate")
    if body.kind in ("name", "username", "city") and (ref := check_text(value, own_names(db, user) + [value])):
        raise ApiError(400, "hard_limit", **ref.as_dict())
    all_ids = db.scalars(select(Identifier).where(Identifier.user_id == user.id)).all()
    if len(all_ids) >= plans()["abuse"]["max_identifiers"]:
        raise ApiError(400, "too_many_identifiers")
    h = lookup_hash(value)
    if any(i.kind == body.kind and i.value_hash == h for i in all_ids):
        raise ApiError(409, "identifier_exists")
    if body.kind == "name":
        names = {i.value_hash for i in all_ids if i.kind == "name"} | {h}
        if len(names) > plans()["abuse"]["max_distinct_names"]:
            # Anomaly lock: many distinct names on one account points at third-party searching (H1).
            user.locked, user.lock_reason = True, "anomaly_many_names"
            audit(db, "abuse.anomaly_lock", user.id, req_ip_hash(request), names=len(names))
            db.commit()
            raise ApiError(423, "account_locked", "anomaly_many_names")
    ident = Identifier(user_id=user.id, kind=body.kind, value=value, value_hash=h, own_data_confirmed_at=now())
    db.add(ident)
    db.flush()
    db.add(ConsentLog(user_id=user.id, kind="own_data", subject_ref=ident.id, ip_hash=req_ip_hash(request)))
    out: dict = {}
    if body.kind in ("name", "city", "username"):
        if not user.email_verified:
            out["pending_reason"] = "verify_account_email_first"
        else:
            ident.verified_at = now()
    elif body.kind == "email":
        if value == user.email and user.email_verified:
            ident.verified_at = now()
        else:
            _send_ident_link(db, user, ident)
            out["pending_reason"] = "check_inbox"
    elif body.kind == "phone":
        out.update(_send_phone_code(db, user, ident))
    elif body.kind == "domain":
        tok = secrets.token_hex(12)
        ident.code_hash = tok  # not secret: must be published in DNS
        out["dns_txt"] = f"fadeprint-verify={tok}"
        out["pending_reason"] = "add_dns_txt"
    audit(db, "profile.identifier_added", user.id, kind=body.kind)
    timeline(db, user.id, "change", f"Angabe hinzugefügt: {body.kind}")
    db.commit()
    return {**ident_view(ident), **out}


def _send_ident_link(db: Session, user: User, ident: Identifier) -> None:
    tok = secrets.token_urlsafe(32)
    db.add(OneTimeToken(token_hash=token_hash(tok), user_id=user.id, purpose="verify_ident", data=ident.id,
                        expires_at=now() + timedelta(hours=24)))
    send_mail(ident.value, f"{brand()['name']}: Ist das deine Adresse?",
              f"Jemand möchte diese Adresse als eigene Adresse bei {brand()['name']} hinterlegen.\n"
              f"Wenn du das warst, bestätige hier:\n{get_settings().public_url}/verify-identifier?token={tok}\n\n"
              "Wenn nicht, ignoriere diese Mail. Ohne Bestätigung wird nichts geprüft.")


def _send_phone_code(db: Session, user: User, ident: Identifier) -> dict:
    s = get_settings()
    code = f"{secrets.randbelow(1_000_000):06d}"
    ident.code_hash, ident.code_expires, ident.code_attempts = token_hash(code), now() + timedelta(minutes=10), 0
    if s.sms_provider == "none":
        if s.is_prod and not s.demo_mode:
            return {"pending_reason": "sms_unavailable"}
        from app.core.mailer import OUTBOX

        OUTBOX.append({"to": "sms", "subject": "SMS-Code", "text": f"Dein Fadeprint-Code: {code}"})
        return {"pending_reason": "enter_code", "dev_hint": "Code liegt im Dev-Postfach (kein SMS-Anbieter konfiguriert)."}
    raise ApiError(501, "sms_provider_not_implemented")


class VerifyIn(BaseModel):
    code: str | None = None


@router.post("/identifiers/{iid}/verify")
def verify_identifier(iid: str, body: VerifyIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ident = db.get(Identifier, iid)
    if not ident or ident.user_id != user.id:
        raise ApiError(404, "not_found")
    if ident.verified_at:
        return ident_view(ident)
    if ident.kind == "phone":
        if ident.code_attempts >= 5 or not ident.code_expires or ident.code_expires < now():
            raise ApiError(400, "invalid_or_expired_token")
        ident.code_attempts += 1
        if not body.code or token_hash(body.code.strip()) != ident.code_hash:
            db.commit()
            raise ApiError(400, "invalid_code")
    elif ident.kind == "domain":
        from app.adapters.registry import get

        recs = get("dns_doh").records(ident.value).get("TXT", [])
        if not any(f"fadeprint-verify={ident.code_hash}" in r for r in recs):
            raise ApiError(400, "dns_txt_not_found")
    elif ident.kind in ("name", "city", "username"):
        if not user.email_verified:
            raise ApiError(400, "verify_account_email_first")
    elif ident.kind == "email":
        raise ApiError(400, "use_email_link")
    ident.verified_at = now()
    audit(db, "profile.identifier_verified", user.id, kind=ident.kind)
    db.commit()
    return ident_view(ident)


class LinkIn(BaseModel):
    token: str


@router.post("/identifiers/verify-link")
def verify_identifier_link(body: LinkIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.get(OneTimeToken, token_hash(body.token))
    if not row or row.purpose != "verify_ident" or row.expires_at < now() or row.user_id != user.id:
        raise ApiError(400, "invalid_or_expired_token")
    ident = db.get(Identifier, row.data)
    ident.verified_at = now()
    db.delete(row)
    db.commit()
    return ident_view(ident)


@router.delete("/identifiers/{iid}")
def delete_identifier(iid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ident = db.get(Identifier, iid)
    if not ident or ident.user_id != user.id:
        raise ApiError(404, "not_found")
    db.delete(ident)
    db.commit()
    return {"ok": True}


class SettingsIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=80)
    address_form: str | None = Field(default=None, pattern="^(du|sie)$")
    locale: str | None = Field(default=None, pattern="^(de|en)$")


@router.patch("/settings")
def update_settings(body: SettingsIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(user, k, v)
    db.commit()
    from app.modules.auth import user_view

    return {"user": user_view(user)}


class ConsentIn(BaseModel):
    kind: str = Field(pattern="^(mic|ai|cookies|mailbox|push)$")
    granted: bool


@router.post("/consent")
def record_consent(body: ConsentIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.add(ConsentLog(user_id=user.id, kind=body.kind, granted=body.granted, ip_hash=req_ip_hash(request)))
    db.commit()
    return {"ok": True}


@router.get("/export")
def export_data(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Art. 20 GDPR: machine-readable export of everything stored about the user."""
    from app.modules.export_all import collect

    data = collect(db, user)
    audit(db, "profile.export", user.id)
    db.commit()
    return JSONResponse(data, headers={"Content-Disposition": 'attachment; filename="fadeprint-export.json"'})


class DeleteIn(BaseModel):
    confirm: bool


@router.delete("")
def delete_account(body: DeleteIn, response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """One click (plus confirmation) deletes the account and all personal data, incl. uploads."""
    if not body.confirm:
        raise ApiError(400, "confirm_required")
    from app.modules.export_all import purge

    purge(db, user)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}
