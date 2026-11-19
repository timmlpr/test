"""Account: register (single user), login/logout, passkeys (WebAuthn), me."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from webauthn import (generate_authentication_options, generate_registration_options, options_to_json,
                      verify_authentication_response, verify_registration_response)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import PublicKeyCredentialDescriptor

from ..config import brand, get_settings
from ..db import get_db
from ..models import Passkey, User
from ..security import (audit, clear_session, client_ip, current_user, hash_password, issue_session, limiter,
                        password_problems, verify_password)

router = APIRouter(prefix="/api/auth", tags=["auth"])
_challenges: dict[str, bytes] = {}


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    display_name: str = ""


class LoginIn(BaseModel):
    email: EmailStr
    password: str


def user_out(u: User) -> dict:
    s = u.settings or {}
    return {"id": u.id, "email": u.email, "display_name": u.display_name, "is_demo": u.is_demo,
            "setup_step": u.setup_step, "setup_done": u.setup_step >= 7, "setup_skipped": u.setup_skipped,
            "settings": {k: s.get(k) for k in ("call_names", "keep_audio", "consent_reminder", "answer_mode",
                                               "large_type", "theme", "models", "quotas", "review_threshold")}}


@router.get("/status")
def status(db: Session = Depends(get_db)) -> dict:
    real_users = db.scalar(select(func.count(User.id)).where(User.is_demo.is_(False))) or 0
    s = get_settings()
    return {"registration_open": s.allow_registration and real_users == 0, "demo": s.demo_mode,
            "demo_login": {"email": "demo@lernzentrum.app", "password": "Lernzentrum2026"} if s.demo_mode else None,
            "brand": brand()}


@router.post("/register")
def register(body: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    limiter.check(f"reg:{client_ip(request)}", 5, 3600)
    real_users = db.scalar(select(func.count(User.id)).where(User.is_demo.is_(False))) or 0
    if real_users > 0 or not get_settings().allow_registration:
        raise HTTPException(403, "Es gibt bereits ein Konto. Lernzentrum ist für eine Person eingerichtet.")
    if problem := password_problems(body.password):
        raise HTTPException(422, problem)
    if db.scalar(select(User).where(User.email == body.email.lower())):
        raise HTTPException(409, "Diese E-Mail ist schon registriert.")
    user = User(email=body.email.lower(), password_hash=hash_password(body.password),
                display_name=body.display_name.strip()[:120], setup_step=2,
                settings={"consent_reminder": True, "keep_audio": True, "answer_mode": "short", "call_names": []})
    db.add(user)
    db.flush()
    audit(db, user.id, "register")
    db.commit()
    issue_session(response, user)
    return user_out(user)


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    limiter.check(f"login:{client_ip(request)}", 10, 300)
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not verify_password(user.password_hash, body.password):
        audit(db, user.id if user else None, "login_failed")
        db.commit()
        raise HTTPException(401, "E-Mail oder Passwort stimmt nicht.")
    audit(db, user.id, "login")
    db.commit()
    issue_session(response, user)
    return user_out(user)


@router.post("/logout")
def logout(response: Response) -> dict:
    clear_session(response)
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)) -> dict:
    return user_out(user)


# ---------------------------------------------------------------- passkeys
def _rp(request: Request) -> tuple[str, str]:
    origin = get_settings().public_url.rstrip("/")
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "localhost")
    rp_id = origin.split("://", 1)[-1].split(":")[0].split("/")[0] or host.split(":")[0]
    return rp_id, origin


@router.post("/passkey/register/options")
def passkey_register_options(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rp_id, _ = _rp(request)
    existing = db.scalars(select(Passkey).where(Passkey.user_id == user.id)).all()
    opts = generate_registration_options(
        rp_id=rp_id, rp_name=brand().get("name", "Lernzentrum"), user_id=str(user.id).encode(), user_name=user.email,
        exclude_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(p.credential_id)) for p in existing])
    _challenges[f"reg:{user.id}"] = opts.challenge
    return json.loads(options_to_json(opts))


@router.post("/passkey/register/verify")
def passkey_register_verify(payload: dict, request: Request, user: User = Depends(current_user),
                            db: Session = Depends(get_db)) -> dict:
    rp_id, origin = _rp(request)
    challenge = _challenges.pop(f"reg:{user.id}", None)
    if not challenge:
        raise HTTPException(400, "Bitte erneut versuchen.")
    try:
        v = verify_registration_response(credential=payload, expected_challenge=challenge, expected_rp_id=rp_id,
                                         expected_origin=origin)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Passkey konnte nicht geprüft werden: {exc}") from exc
    db.add(Passkey(user_id=user.id, credential_id=bytes_to_base64url(v.credential_id), public_key=v.credential_public_key,
                   sign_count=v.sign_count, label=payload.get("label", "Face ID / Touch ID")[:120]))
    audit(db, user.id, "passkey_added")
    db.commit()
    return {"ok": True}


class EmailIn(BaseModel):
    email: EmailStr


@router.post("/passkey/login/options")
def passkey_login_options(body: EmailIn, request: Request, db: Session = Depends(get_db)):
    limiter.check(f"pk:{client_ip(request)}", 20, 300)
    rp_id, _ = _rp(request)
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    creds = db.scalars(select(Passkey).where(Passkey.user_id == user.id)).all() if user else []
    if not creds:
        raise HTTPException(404, "Für diese E-Mail ist kein Passkey eingerichtet.")
    opts = generate_authentication_options(rp_id=rp_id, allow_credentials=[
        PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id)) for c in creds])
    _challenges[f"auth:{user.id}"] = opts.challenge
    return json.loads(options_to_json(opts))


@router.post("/passkey/login/verify")
def passkey_login_verify(payload: dict, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    rp_id, origin = _rp(request)
    cred = db.scalar(select(Passkey).where(Passkey.credential_id == payload.get("id", "")))
    if not cred:
        raise HTTPException(401, "Unbekannter Passkey.")
    challenge = _challenges.pop(f"auth:{cred.user_id}", None)
    if not challenge:
        raise HTTPException(400, "Bitte erneut versuchen.")
    try:
        v = verify_authentication_response(credential=payload, expected_challenge=challenge, expected_rp_id=rp_id,
                                           expected_origin=origin, credential_public_key=cred.public_key,
                                           credential_current_sign_count=cred.sign_count)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(401, "Passkey-Anmeldung fehlgeschlagen.") from exc
    cred.sign_count = v.new_sign_count
    user = db.get(User, cred.user_id)
    audit(db, user.id, "login_passkey")
    db.commit()
    issue_session(response, user)
    return user_out(user)
