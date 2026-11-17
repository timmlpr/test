"""Accounts: email+password (Argon2id), email verification, TOTP 2FA + recovery codes, password reset,
Sign in with Google / Apple (OIDC, only when configured), passkeys (WebAuthn)."""
from __future__ import annotations

import json
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import httpx
import jwt
import pyotp
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.audit import audit
from app.core.clock import utcnow
from app.core.crypto import lookup_hash
from app.core.deps import client_ip, current_user, pending_2fa_user, req_ip_hash
from app.core.errors import ApiError
from app.core.mailer import send_mail
from app.core.security import (
    SESSION_COOKIE,
    hash_password,
    make_session,
    password_policy_error,
    token_hash,
    verify_password,
)
from app.db import get_db
from app.models import (
    ConsentLog,
    Identifier,
    OAuthAccount,
    OneTimeToken,
    Passkey,
    Referral,
    User,
    now,
)
from app.settings import brand, get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------- helpers
def set_session(resp: Response, user: User, *, mfa: bool, pending: bool = False) -> None:
    s = get_settings()
    resp.set_cookie(SESSION_COOKIE, make_session(user.id, user.session_version, mfa=mfa, pending_2fa=pending),
                    httponly=True, secure=s.cookie_secure, samesite="lax", max_age=None if pending else s.session_days * 86400,
                    path="/")


def user_view(u: User) -> dict:
    from app.core.plans import effective_tier

    return {"id": u.id, "email": u.email, "display_name": u.display_name, "email_verified": u.email_verified,
            "role": u.role, "plan": u.plan, "tier": effective_tier(u), "trial_ends_at": u.trial_ends_at,
            "address_form": u.address_form, "locale": u.locale, "totp_enabled": u.totp_enabled, "is_demo": u.is_demo,
            "is_child": u.is_child, "referral_code": u.referral_code}


def issue_token(db: Session, user_id: str | None, purpose: str, minutes: int, data: dict | None = None) -> str:
    tok = secrets.token_urlsafe(32)
    db.add(OneTimeToken(token_hash=token_hash(tok), user_id=user_id, purpose=purpose,
                        data=json.dumps(data) if data else None, expires_at=now() + timedelta(minutes=minutes)))
    return tok


def take_token(db: Session, tok: str, purpose: str) -> OneTimeToken:
    row = db.get(OneTimeToken, token_hash(tok))
    if not row or row.purpose != purpose or row.expires_at < now():
        raise ApiError(400, "invalid_or_expired_token")
    db.delete(row)
    return row


def send_verification(db: Session, user: User) -> None:
    tok = issue_token(db, user.id, "verify_email", 60 * 24)
    url = f"{get_settings().public_url}/verify-email?token={tok}"
    send_mail(user.email, f"{brand()['name']}: Bitte bestätige deine E-Mail-Adresse",
              f"Hallo,\n\nbitte bestätige deine E-Mail-Adresse:\n{url}\n\nDer Link ist 24 Stunden gültig.\n"
              f"Wenn du dich nicht registriert hast, ignoriere diese Mail.\n\n{brand()['name']}")


def _ensure_email_identifier(db: Session, user: User) -> None:
    """The account email counts as a verified own identifier once the address is confirmed."""
    h = lookup_hash(user.email)
    exists = db.scalar(select(Identifier).where(Identifier.user_id == user.id, Identifier.kind == "email",
                                                Identifier.value_hash == h))
    if not exists:
        db.add(Identifier(user_id=user.id, kind="email", value=user.email, value_hash=h, verified_at=now()))
    elif not exists.verified_at:
        exists.verified_at = now()


# ---------------------------------------------------------------- email + password
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=256)
    display_name: str | None = Field(default=None, max_length=80)
    accept_terms: bool
    referral_code: str | None = None
    invite_code: str | None = None


@router.post("/register")
def register(body: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ratelimit.hit(f"register:{client_ip(request)}", 5, 3600)
    if not body.accept_terms:
        raise ApiError(400, "terms_required")
    if err := password_policy_error(body.password):
        raise ApiError(400, err)
    h = lookup_hash(body.email)
    if db.scalar(select(User).where(User.email_hash == h)):
        # do not reveal account existence in timing-insensitive way: same response shape
        raise ApiError(409, "email_taken")
    s = get_settings()
    user = User(email=body.email.lower(), email_hash=h, password_hash=hash_password(body.password),
                display_name=body.display_name, trial_ends_at=None)
    db.add(user)
    db.flush()
    db.add(ConsentLog(user_id=user.id, kind="terms", version="1", ip_hash=req_ip_hash(request)))
    db.add(ConsentLog(user_id=user.id, kind="privacy", version="1", ip_hash=req_ip_hash(request)))
    if body.referral_code:
        ref = db.scalar(select(User).where(User.referral_code == body.referral_code))
        if ref and ref.id != user.id:
            user.referred_by = ref.id
            db.add(Referral(referrer_id=ref.id, referee_id=user.id))
    send_verification(db, user)
    audit(db, "auth.register", user.id, req_ip_hash(request))
    db.commit()
    set_session(response, user, mfa=False)
    return {"user": user_view(user), "verification_sent": True, "dev_outbox": not s.smtp_host}


class LoginIn(BaseModel):
    email: EmailStr
    password: str


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ratelimit.hit(f"login:{client_ip(request)}", 10, 300)
    ratelimit.hit(f"login-acct:{lookup_hash(body.email)}", 10, 900)
    user = db.scalar(select(User).where(User.email_hash == lookup_hash(body.email)))
    if not user or not verify_password(user.password_hash, body.password):
        audit(db, "auth.login_failed", None, req_ip_hash(request))
        db.commit()
        raise ApiError(401, "invalid_credentials")
    if user.locked:
        raise ApiError(423, "account_locked", user.lock_reason)
    if user.totp_enabled:
        set_session(response, user, mfa=False, pending=True)
        return {"requires_2fa": True}
    set_session(response, user, mfa=False)
    audit(db, "auth.login", user.id, req_ip_hash(request))
    db.commit()
    return {"user": user_view(user)}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.post("/logout-all")
def logout_all(response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.session_version += 1
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"user": user_view(user)}


class TokenIn(BaseModel):
    token: str


@router.post("/verify-email")
def verify_email(body: TokenIn, db: Session = Depends(get_db)):
    row = take_token(db, body.token, "verify_email")
    user = db.get(User, row.user_id)
    if not user:
        raise ApiError(400, "invalid_or_expired_token")
    user.email_verified = True
    _ensure_email_identifier(db, user)
    audit(db, "auth.email_verified", user.id)
    db.commit()
    return {"ok": True}


@router.post("/resend-verification")
def resend(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ratelimit.hit(f"resend:{user.id}", 3, 3600)
    if not user.email_verified:
        send_verification(db, user)
        db.commit()
    return {"ok": True}


class ResetStartIn(BaseModel):
    email: EmailStr


@router.post("/password-reset")
def password_reset_start(body: ResetStartIn, request: Request, db: Session = Depends(get_db)):
    ratelimit.hit(f"reset:{client_ip(request)}", 5, 3600)
    user = db.scalar(select(User).where(User.email_hash == lookup_hash(body.email)))
    if user:
        tok = issue_token(db, user.id, "reset", 30)
        send_mail(user.email, f"{brand()['name']}: Passwort zurücksetzen",
                  f"Hier kannst du ein neues Passwort setzen (30 Minuten gültig):\n"
                  f"{get_settings().public_url}/reset?token={tok}\n\nNicht angefordert? Dann ignoriere diese Mail.")
        db.commit()
    return {"ok": True}  # same answer whether or not the account exists


class ResetIn(BaseModel):
    token: str
    password: str


@router.post("/password-reset/confirm")
def password_reset_confirm(body: ResetIn, db: Session = Depends(get_db)):
    if err := password_policy_error(body.password):
        raise ApiError(400, err)
    row = take_token(db, body.token, "reset")
    user = db.get(User, row.user_id)
    user.password_hash = hash_password(body.password)
    user.session_version += 1
    audit(db, "auth.password_reset", user.id)
    db.commit()
    return {"ok": True}


class ChangePwIn(BaseModel):
    current: str
    new: str


@router.post("/password")
def change_password(body: ChangePwIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.password_hash and not verify_password(user.password_hash, body.current):
        raise ApiError(400, "invalid_credentials")
    if err := password_policy_error(body.new):
        raise ApiError(400, err)
    user.password_hash = hash_password(body.new)
    audit(db, "auth.password_changed", user.id)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- TOTP 2FA + recovery codes
@router.post("/totp/setup")
def totp_setup(user: User = Depends(current_user), db: Session = Depends(get_db)):
    secret = pyotp.random_base32()
    user.totp_secret = secret
    db.commit()
    uri = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=brand()["name"])
    return {"secret": secret, "otpauth_uri": uri}


class CodeIn(BaseModel):
    code: str = Field(min_length=6, max_length=32)


def _new_recovery_codes() -> tuple[list[str], list[str]]:
    codes = [f"{secrets.token_hex(3)}-{secrets.token_hex(3)}" for _ in range(10)]
    return codes, [token_hash(c) for c in codes]


@router.post("/totp/enable")
def totp_enable(body: CodeIn, response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not user.totp_secret or not pyotp.TOTP(user.totp_secret).verify(body.code, valid_window=1):
        raise ApiError(400, "invalid_code")
    codes, hashes = _new_recovery_codes()
    user.totp_enabled, user.recovery_codes = True, hashes
    audit(db, "auth.totp_enabled", user.id)
    db.commit()
    set_session(response, user, mfa=True)
    return {"recovery_codes": codes}


@router.post("/totp/disable")
def totp_disable(body: CodeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not _check_second_factor(user, body.code):
        raise ApiError(400, "invalid_code")
    user.totp_enabled, user.totp_secret, user.recovery_codes = False, None, None
    audit(db, "auth.totp_disabled", user.id)
    db.commit()
    return {"ok": True}


def _check_second_factor(user: User, code: str) -> bool:
    code = code.strip().replace(" ", "")
    if user.totp_secret and len(code) == 6 and code.isdigit() and pyotp.TOTP(user.totp_secret).verify(code, valid_window=1):
        return True
    h = token_hash(code)
    if user.recovery_codes and h in user.recovery_codes:
        user.recovery_codes = [c for c in user.recovery_codes if c != h]  # single use
        return True
    return False


@router.post("/totp/verify")
def totp_verify(body: CodeIn, request: Request, response: Response, user: User = Depends(pending_2fa_user),
                db: Session = Depends(get_db)):
    ratelimit.hit(f"2fa:{user.id}", 8, 600)
    if not _check_second_factor(user, body.code):
        raise ApiError(400, "invalid_code")
    audit(db, "auth.login", user.id, req_ip_hash(request), mfa=True)
    db.commit()
    set_session(response, user, mfa=True)
    return {"user": user_view(user)}


@router.post("/recovery-codes")
def regenerate_codes(body: CodeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not user.totp_enabled or not _check_second_factor(user, body.code):
        raise ApiError(400, "invalid_code")
    codes, hashes = _new_recovery_codes()
    user.recovery_codes = hashes
    db.commit()
    return {"recovery_codes": codes}


# ---------------------------------------------------------------- OAuth / OIDC (Google, Apple)
PROVIDERS = {
    "google": {"auth": "https://accounts.google.com/o/oauth2/v2/auth", "token": "https://oauth2.googleapis.com/token",
               "jwks": "https://www.googleapis.com/oauth2/v3/certs", "issuer": ["https://accounts.google.com", "accounts.google.com"]},
    "apple": {"auth": "https://appleid.apple.com/auth/authorize", "token": "https://appleid.apple.com/auth/token",
              "jwks": "https://appleid.apple.com/auth/keys", "issuer": ["https://appleid.apple.com"]},
}


def _client(provider: str) -> tuple[str, str] | None:
    s = get_settings()
    if provider == "google" and s.google_client_id and s.google_client_secret:
        return s.google_client_id, s.google_client_secret
    if provider == "apple" and s.apple_client_id and s.apple_private_key:
        now_ts = int(utcnow().timestamp())
        secret = jwt.encode({"iss": s.apple_team_id, "iat": now_ts, "exp": now_ts + 3600, "aud": "https://appleid.apple.com",
                             "sub": s.apple_client_id}, s.apple_private_key.replace("\\n", "\n"), algorithm="ES256",
                            headers={"kid": s.apple_key_id})
        return s.apple_client_id, secret
    return None


@router.get("/providers")
def providers():
    return {"google": _client("google") is not None, "apple": bool(get_settings().apple_client_id), "passkeys": True}


@router.get("/oauth/{provider}/start")
def oauth_start(provider: str, db: Session = Depends(get_db)):
    if provider not in PROVIDERS or not _client(provider):
        raise ApiError(404, "provider_not_configured")
    state = issue_token(db, None, f"oauth_{provider}", 10)
    nonce = secrets.token_urlsafe(16)
    db.commit()
    params = {"client_id": _client(provider)[0], "redirect_uri": f"{get_settings().public_url}/api/auth/oauth/{provider}/callback",
              "response_type": "code", "scope": "openid email" + (" name" if provider == "apple" else ""), "state": state,
              "nonce": nonce}
    if provider == "apple":
        params["response_mode"] = "form_post"
    return RedirectResponse(f"{PROVIDERS[provider]['auth']}?{urlencode(params)}")


async def _oauth_finish(provider: str, code: str, state: str, db: Session) -> RedirectResponse:
    take_token(db, state, f"oauth_{provider}")
    cid, secret = _client(provider)
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(PROVIDERS[provider]["token"], data={
            "code": code, "client_id": cid, "client_secret": secret, "grant_type": "authorization_code",
            "redirect_uri": f"{get_settings().public_url}/api/auth/oauth/{provider}/callback"})
    if r.status_code != 200:
        raise ApiError(400, "oauth_failed")
    id_token = r.json()["id_token"]
    key = jwt.PyJWKClient(PROVIDERS[provider]["jwks"]).get_signing_key_from_jwt(id_token)
    claims = jwt.decode(id_token, key.key, algorithms=["RS256", "ES256"], audience=cid, issuer=PROVIDERS[provider]["issuer"])
    email, sub = claims.get("email"), claims["sub"]
    if not email or claims.get("email_verified", True) not in (True, "true"):
        raise ApiError(400, "oauth_email_unverified")
    link = db.scalar(select(OAuthAccount).where(OAuthAccount.provider == provider, OAuthAccount.subject == sub))
    if link:
        user = db.get(User, link.user_id)
    else:
        user = db.scalar(select(User).where(User.email_hash == lookup_hash(email)))
        if not user:
            user = User(email=email.lower(), email_hash=lookup_hash(email), email_verified=True)
            db.add(user)
            db.flush()
            db.add(ConsentLog(user_id=user.id, kind="terms", version="1"))
        user.email_verified = True
        db.add(OAuthAccount(user_id=user.id, provider=provider, subject=sub))
        _ensure_email_identifier(db, user)
    audit(db, "auth.login", user.id, provider=provider)
    db.commit()
    resp = RedirectResponse(f"{get_settings().public_url}/app", status_code=303)
    if user.totp_enabled:
        set_session(resp, user, mfa=False, pending=True)
        resp.headers["location"] = f"{get_settings().public_url}/login?step=2fa"
    else:
        set_session(resp, user, mfa=False)
    return resp


@router.get("/oauth/{provider}/callback")
async def oauth_cb_get(provider: str, code: str, state: str, db: Session = Depends(get_db)):
    return await _oauth_finish(provider, code, state, db)


@router.post("/oauth/{provider}/callback")
async def oauth_cb_post(provider: str, request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    return await _oauth_finish(provider, str(form.get("code")), str(form.get("state")), db)


# ---------------------------------------------------------------- Passkeys (WebAuthn)
def _wa():
    import webauthn
    from webauthn.helpers import options_to_json

    return webauthn, options_to_json


def _origin() -> str:
    return get_settings().public_url.rstrip("/")


@router.post("/passkey/register/begin")
def passkey_register_begin(user: User = Depends(current_user), db: Session = Depends(get_db)):
    webauthn, to_json = _wa()
    from webauthn.helpers import base64url_to_bytes
    from webauthn.helpers.structs import (
        AuthenticatorSelectionCriteria,
        PublicKeyCredentialDescriptor,
        ResidentKeyRequirement,
    )

    existing = db.scalars(select(Passkey).where(Passkey.user_id == user.id)).all()
    opts = webauthn.generate_registration_options(
        rp_id=get_settings().webauthn_rp_id, rp_name=get_settings().webauthn_rp_name, user_id=user.id.encode(),
        user_name=user.email, exclude_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(p.credential_id)) for p in existing],
        authenticator_selection=AuthenticatorSelectionCriteria(resident_key=ResidentKeyRequirement.PREFERRED))
    from webauthn.helpers import bytes_to_base64url

    db.query(OneTimeToken).filter(OneTimeToken.user_id == user.id, OneTimeToken.purpose == "wa_reg").delete()
    db.add(OneTimeToken(token_hash=token_hash(f"wa_reg:{user.id}:{secrets.token_hex(4)}"), user_id=user.id, purpose="wa_reg",
                        data=bytes_to_base64url(opts.challenge), expires_at=now() + timedelta(minutes=5)))
    db.commit()
    return json.loads(to_json(opts))


class PasskeyFinishIn(BaseModel):
    credential: dict
    name: str = "Passkey"


@router.post("/passkey/register/finish")
def passkey_register_finish(body: PasskeyFinishIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    webauthn, _ = _wa()
    from webauthn.helpers import base64url_to_bytes, bytes_to_base64url

    row = db.scalar(select(OneTimeToken).where(OneTimeToken.user_id == user.id, OneTimeToken.purpose == "wa_reg"))
    if not row or row.expires_at < now():
        raise ApiError(400, "challenge_expired")
    try:
        v = webauthn.verify_registration_response(credential=body.credential, expected_challenge=base64url_to_bytes(row.data),
                                                  expected_rp_id=get_settings().webauthn_rp_id, expected_origin=_origin())
    except Exception as e:  # noqa: BLE001
        raise ApiError(400, "passkey_invalid") from e
    db.delete(row)
    db.add(Passkey(user_id=user.id, credential_id=bytes_to_base64url(v.credential_id),
                   public_key=bytes_to_base64url(v.credential_public_key), sign_count=v.sign_count, name=body.name[:64]))
    audit(db, "auth.passkey_added", user.id)
    db.commit()
    return {"ok": True}


@router.post("/passkey/login/begin")
def passkey_login_begin(db: Session = Depends(get_db)):
    webauthn, to_json = _wa()
    from webauthn.helpers import bytes_to_base64url

    opts = webauthn.generate_authentication_options(rp_id=get_settings().webauthn_rp_id)
    handle = secrets.token_urlsafe(16)
    db.add(OneTimeToken(token_hash=token_hash(handle), purpose="wa_auth", data=bytes_to_base64url(opts.challenge),
                        expires_at=now() + timedelta(minutes=5)))
    db.commit()
    return {"handle": handle, "options": json.loads(to_json(opts))}


class PasskeyLoginIn(BaseModel):
    handle: str
    credential: dict


@router.post("/passkey/login/finish")
def passkey_login_finish(body: PasskeyLoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    webauthn, _ = _wa()
    from webauthn.helpers import base64url_to_bytes

    row = take_token(db, body.handle, "wa_auth")
    pk = db.scalar(select(Passkey).where(Passkey.credential_id == body.credential.get("id")))
    if not pk:
        raise ApiError(400, "passkey_unknown")
    try:
        v = webauthn.verify_authentication_response(
            credential=body.credential, expected_challenge=base64url_to_bytes(row.data), expected_rp_id=get_settings().webauthn_rp_id,
            expected_origin=_origin(), credential_public_key=base64url_to_bytes(pk.public_key), credential_current_sign_count=pk.sign_count)
    except Exception as e:  # noqa: BLE001
        raise ApiError(400, "passkey_invalid") from e
    pk.sign_count = v.new_sign_count
    user = db.get(User, pk.user_id)
    audit(db, "auth.login", user.id, req_ip_hash(request), passkey=True)
    db.commit()
    set_session(response, user, mfa=True)  # passkey = phishing-resistant multi-factor
    return {"user": user_view(user)}


@router.get("/passkeys")
def list_passkeys(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [{"id": p.id, "name": p.name, "created_at": p.created_at} for p in db.scalars(select(Passkey).where(Passkey.user_id == user.id))]


@router.delete("/passkeys/{pid}")
def delete_passkey(pid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = db.get(Passkey, pid)
    if not p or p.user_id != user.id:
        raise ApiError(404, "not_found")
    db.delete(p)
    db.commit()
    return {"ok": True}
