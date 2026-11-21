"""FastAPI application entry point."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from . import calendar_sync, moodle  # noqa: F401  (register job handlers)
from .config import brand, get_settings
from .db import Base, SessionLocal, engine, get_db, utcnow
from .ingest import channels, pipeline  # noqa: F401
from .jobs import periodic, worker
from .learn import core  # noqa: F401
from .live import pipeline as live_pipeline  # noqa: F401
from .models import AudioChunk, Module, User
from .correction import service as correction_service
from .routers import auth, learn, library, live, moodle as moodle_router, planner, settings as settings_router
from .seed import LIVE_DEMO_BF, seed_demo
from .security import current_user
from .storage import storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("lz")


def init_db() -> None:
    s = get_settings()
    if s.database_url.startswith("sqlite"):
        Base.metadata.create_all(engine)  # dev/tests; production uses Alembic migrations
    if s.demo_mode:
        with SessionLocal() as db:
            seed_demo(db)
            db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if get_settings().run_jobs:
        worker.threads = get_settings().worker_threads
        worker.start()
    yield
    worker.stop()


app = FastAPI(title="Lernzentrum API", version="1.0.0", lifespan=lifespan,
              docs_url="/api/docs" if not get_settings().is_prod else None, openapi_url="/api/openapi.json")

for r in (auth.router, settings_router.router, planner.router, library.router, live.router, learn.router,
          moodle_router.router, correction_service.router):
    app.include_router(r)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    if request.url.path.startswith("/api/") and "cache-control" not in response.headers:
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("unhandled error on %s", request.url.path)
    return JSONResponse({"detail": "Interner Fehler. Bitte erneut versuchen."}, status_code=500)


@app.get("/api/health")
def health(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    return {"status": "ok", "app": brand().get("name"), "time": utcnow().isoformat()}


@app.get("/api/brand")
def brand_info() -> dict:
    return brand()


@app.get("/api/demo/script")
def demo_script(user: User = Depends(current_user)) -> dict:
    return {"module": "BF", "sentences": LIVE_DEMO_BF}


@periodic("retention", 6 * 3600)
def retention() -> None:
    """Delete stored audio older than the module's retention setting (transcripts stay)."""
    with SessionLocal() as db:
        for m in db.scalars(select(Module).where(Module.retention_days.is_not(None))).all():
            cutoff = utcnow() - timedelta(days=m.retention_days)
            from .models import Recording

            q = select(AudioChunk).join(Recording, Recording.id == AudioChunk.recording_id).where(
                Recording.module_id == m.id, AudioChunk.created_at < cutoff, AudioChunk.storage_key.is_not(None))
            for ch in db.scalars(q).all():
                storage().delete(ch.storage_key)
                ch.storage_key = None
        db.commit()
