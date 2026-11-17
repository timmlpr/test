from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.plans import has_feature
from app.core.security import SESSION_COOKIE, ip_hash, read_session
from app.db import get_db
from app.models import User


def client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else None)


def req_ip_hash(request: Request) -> str | None:
    return ip_hash(client_ip(request))


def _load(request: Request, db: Session, allow_pending: bool = False) -> User | None:
    tok = request.cookies.get(SESSION_COOKIE)
    if not tok:
        auth = request.headers.get("authorization", "")
        tok = auth[7:] if auth.lower().startswith("bearer ") else None
    if not tok:
        return None
    data = read_session(tok)
    if not data or (data.get("p2fa") and not allow_pending):
        return None
    user = db.get(User, data["sub"])
    if not user or user.session_version != data.get("v"):
        return None
    request.state.mfa = bool(data.get("mfa"))
    return user


def optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    return _load(request, db)


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = _load(request, db)
    if not user:
        raise ApiError(401, "not_authenticated")
    if user.locked:
        raise ApiError(423, "account_locked", user.lock_reason)
    return user


def pending_2fa_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = _load(request, db, allow_pending=True)
    if not user:
        raise ApiError(401, "not_authenticated")
    return user


def admin_user(request: Request, user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise ApiError(403, "forbidden")
    if not (user.totp_enabled and getattr(request.state, "mfa", False)):
        raise ApiError(403, "admin_requires_2fa")
    return user


def require_feature(feature: str):
    def dep(user: User = Depends(current_user)) -> User:
        if not has_feature(user, feature):
            raise ApiError(402, "premium_required", feature=feature)
        return user

    return dep
