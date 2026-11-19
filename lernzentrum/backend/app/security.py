"""Password hashing (Argon2id), signed session cookies, CSRF (double submit), rate limiting, audit."""
from __future__ import annotations

import hmac
import threading
import time
from collections import defaultdict, deque

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from .config import get_settings
from .crypto import random_token
from .db import get_db
from .models import AuditLog, User

SESSION_COOKIE = "lz_session"
CSRF_COOKIE = "lz_csrf"
SESSION_MAX_AGE = 60 * 60 * 24 * 30

_ph = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=2)  # Argon2id defaults


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(hashed: str, pw: str) -> bool:
    try:
        return _ph.verify(hashed, pw)
    except (VerificationError, InvalidHashError):
        return False


def password_problems(pw: str) -> str | None:
    if len(pw) < 10:
        return "Das Passwort braucht mindestens 10 Zeichen."
    if pw.lower() == pw or not any(c.isdigit() for c in pw):
        return "Bitte Groß-/Kleinbuchstaben und mindestens eine Zahl verwenden."
    return None


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().session_secret, salt="lz-session")


def issue_session(response: Response, user: User) -> None:
    s = get_settings()
    token = _serializer().dumps({"uid": user.id, "n": random_token(8)})
    response.set_cookie(SESSION_COOKIE, token, max_age=SESSION_MAX_AGE, httponly=True, samesite="lax",
                        secure=s.cookie_secure or s.is_prod, path="/")
    response.set_cookie(CSRF_COOKIE, random_token(16), max_age=SESSION_MAX_AGE, httponly=False, samesite="strict",
                        secure=s.cookie_secure or s.is_prod, path="/")


def clear_session(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


def _user_from_request(request: Request, db: Session) -> User | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    try:
        data = _serializer().loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    return db.get(User, data.get("uid"))


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = _user_from_request(request, db)
    if not user:
        raise HTTPException(401, "Bitte melde dich an.")
    if request.method not in SAFE_METHODS:
        header = request.headers.get("x-csrf-token", "")
        cookie = request.cookies.get(CSRF_COOKIE, "")
        if not cookie or not hmac.compare_digest(header, cookie):
            raise HTTPException(403, "CSRF-Prüfung fehlgeschlagen. Bitte Seite neu laden.")
    return user


def optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    return _user_from_request(request, db)


class RateLimiter:
    """Simple in-memory sliding window limiter (single process)."""

    def __init__(self) -> None:
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, per_s: int) -> None:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > per_s:
                q.popleft()
            if len(q) >= limit:
                raise HTTPException(429, "Zu viele Versuche. Bitte kurz warten.")
            q.append(now)


limiter = RateLimiter()


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")


def audit(db: Session, user_id: int | None, action: str, detail: str = "") -> None:
    """Audit log entry. Never pass secrets in `detail`."""
    db.add(AuditLog(user_id=user_id, action=action, detail=detail[:500]))
