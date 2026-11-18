"""Fadeprint API – application factory, middleware (CSRF, security headers), router wiring."""
from __future__ import annotations

import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.security import CSRF_COOKIE, CSRF_HEADER
from app.settings import brand, get_settings, plans

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("fadeprint")

CSRF_EXEMPT = {"/api/billing/webhook", "/api/auth/oauth/apple/callback"}
SAFE = {"GET", "HEAD", "OPTIONS"}


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        s = get_settings()
        cookie = request.cookies.get(CSRF_COOKIE)
        if request.method not in SAFE and request.url.path not in CSRF_EXEMPT:
            header = request.headers.get(CSRF_HEADER)
            if not cookie or not header or not secrets.compare_digest(cookie, header):
                return JSONResponse({"detail": {"code": "csrf_failed", "message": "csrf_failed"}}, status_code=403)
        resp = await call_next(request)
        if not cookie:
            resp.set_cookie(CSRF_COOKIE, secrets.token_urlsafe(24), httponly=False, secure=s.cookie_secure, samesite="strict", path="/")
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Cache-Control", "no-store")
        return resp


def create_app() -> FastAPI:
    s = get_settings()
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from app.bootstrap import bootstrap

        bootstrap()
        sched = None
        if s.scheduler_enabled:
            from app.jobs import start_scheduler

            sched = start_scheduler()
        yield
        if sched:
            sched.shutdown(wait=False)

    app = FastAPI(title=f"{brand()['name']} API", version="1.0.0", docs_url=None if s.is_prod else "/api/docs",
                  openapi_url=None if s.is_prod else "/api/openapi.json", lifespan=lifespan)
    app.add_middleware(SecurityMiddleware)

    @app.exception_handler(RequestValidationError)
    async def _validation(_, exc: RequestValidationError):
        fields = [".".join(str(x) for x in e["loc"][1:]) for e in exc.errors()]
        return JSONResponse({"detail": {"code": "validation_error", "message": "validation_error", "fields": fields}}, status_code=422)

    @app.exception_handler(Exception)
    async def _unhandled(_, exc: Exception):
        log.exception("unhandled error: %s", type(exc).__name__)
        return JSONResponse({"detail": {"code": "internal_error", "message": "internal_error"}}, status_code=500)

    from app.modules import (
        admin,
        assistant,
        auth,
        billing,
        checklists,
        deletion,
        family,
        growth,
        home,
        monitor,
        profile,
        reports,
        scan,
        tools,
        vault,
    )

    for m in (auth, profile, scan, home, deletion, reports, billing, family, tools, checklists, monitor, vault, assistant, growth, admin):
        app.include_router(m.router, prefix="/api")

    @app.get("/api/health")
    def health():
        from sqlalchemy import text

        from app.db import engine

        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        return {"status": "ok"}

    @app.get("/api/config/public")
    def public_config():
        from app.ai.provider import ai_status
        from app.modules.auth import providers

        return {"brand": {k: v for k, v in brand().items() if k != "operator"}, "operator": brand()["operator"], "plans": plans(),
                "demo_mode": s.demo_mode, "auth": providers(), "ai": ai_status(), "stripe": bool(s.stripe_secret_key),
                "push": bool(s.vapid_public_key), "vapid_public_key": s.vapid_public_key or None}

    if not s.is_prod:
        @app.get("/api/dev/outbox")
        def outbox():
            """Dev/demo only: mails that would have been sent (no SMTP configured)."""
            from app.core.mailer import OUTBOX

            return list(reversed(OUTBOX))

    return app


app = create_app()
