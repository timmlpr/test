"""Password hashing (Argon2id), signed session cookies, CSRF double-submit tokens."""
from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.settings import get_settings

_ph = PasswordHasher()  # argon2-cffi default = Argon2id, RFC 9106 low-memory profile

SESSION_COOKIE = "fp_session"
CSRF_COOKIE = "fp_csrf"
CSRF_HEADER = "x-csrf-token"


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(hashed: str | None, pw: str) -> bool:
    if not hashed:
        return False
    try:
        return _ph.verify(hashed, pw)
    except (VerificationError, InvalidHashError):
        return False


def password_policy_error(pw: str) -> str | None:
    if len(pw) < 10:
        return "password_too_short"
    if len(pw) > 256:
        return "password_too_long"
    return None


def make_session(user_id: str, version: int, *, mfa: bool, pending_2fa: bool = False) -> str:
    s = get_settings()
    payload = {
        "sub": user_id,
        "v": version,
        "mfa": mfa,
        "p2fa": pending_2fa,
        "exp": datetime.now(UTC) + (timedelta(minutes=10) if pending_2fa else timedelta(days=s.session_days)),
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, s.secret_key, algorithm="HS256")


def read_session(token: str) -> dict | None:
    try:
        return jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def new_csrf() -> str:
    return secrets.token_urlsafe(24)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def ip_hash(ip: str | None) -> str | None:
    """Daily-salted IP hash: allows abuse correlation for one day without storing IPs."""
    if not ip:
        return None
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    return hashlib.sha256(f"{day}:{ip}:{get_settings().secret_key}".encode()).hexdigest()
