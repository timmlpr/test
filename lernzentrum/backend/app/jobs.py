"""DB-backed job queue with worker threads (replaces Celery/RQ for the single-user deployment, see PLAN.md).

Handlers are registered with `@handler("kind")` and receive `(db, job)`. Quota errors re-schedule the job with the
provider's reset time instead of failing it; other errors retry with exponential backoff (max 4 attempts).
"""
from __future__ import annotations

import logging
import threading
import time
import traceback
from datetime import timedelta
from typing import Callable

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .db import SessionLocal, utcnow
from .models import Job
from .quota import QuotaExceeded

log = logging.getLogger("lz.jobs")
HANDLERS: dict[str, Callable[[Session, Job], None]] = {}
PERIODIC: list[tuple[str, int, Callable[[], None]]] = []
MAX_ATTEMPTS = 4


def handler(kind: str):
    def deco(fn):
        HANDLERS[kind] = fn
        return fn

    return deco


def periodic(name: str, every_s: int):
    def deco(fn):
        PERIODIC.append((name, every_s, fn))
        return fn

    return deco


def enqueue(db: Session, kind: str, payload: dict, *, user_id: int | None, label: str = "", batch: str = "",
            delay_s: int = 0) -> Job:
    job = Job(kind=kind, payload=payload, user_id=user_id, label=label, batch=batch,
              run_after=utcnow() + timedelta(seconds=delay_s))
    db.add(job)
    db.flush()
    return job


class TransientError(Exception):
    """Raise to retry later without counting as a hard failure (e.g. network down)."""


def run_job(db: Session, job: Job) -> None:
    fn = HANDLERS.get(job.kind)
    if fn is None:
        job.status, job.error = "error", f"unknown job kind {job.kind}"
        return
    job.attempts += 1
    try:
        fn(db, job)
        if job.status == "running":
            job.status, job.progress, job.finished_at = "done", 1.0, utcnow()
    except QuotaExceeded as exc:
        db.rollback()
        job = db.get(Job, job.id)
        job.status, job.error = "waiting", f"Kontingent erschöpft ({exc.provider}/{exc.metric}) – automatischer Neustart"
        job.attempts -= 1
        job.run_after = utcnow() + timedelta(seconds=exc.retry_after_s + 5)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        job = db.get(Job, job.id)
        log.warning("job %s failed: %s", job.id, traceback.format_exc(limit=3))
        job.error = str(exc)[:1000]
        if job.attempts >= MAX_ATTEMPTS:
            job.status, job.finished_at = "error", utcnow()
        else:
            job.status = "queued"
            job.run_after = utcnow() + timedelta(seconds=15 * 2 ** job.attempts)
    db.commit()


def claim_next(db: Session) -> Job | None:
    job = db.scalar(select(Job).where(Job.status.in_(["queued", "waiting"]), Job.run_after <= utcnow())
                    .order_by(Job.id).limit(1))
    if job is None:
        return None
    res = db.execute(update(Job).where(Job.id == job.id, Job.status == job.status).values(status="running"))
    db.commit()
    if res.rowcount != 1:
        return None
    db.refresh(job)
    return job


def drain(max_jobs: int = 1000) -> int:
    """Run queued jobs synchronously (tests, CLI)."""
    n = 0
    with SessionLocal() as db:
        while n < max_jobs:
            job = claim_next(db)
            if not job:
                break
            run_job(db, job)
            n += 1
    return n


class Worker:
    def __init__(self, threads: int = 2) -> None:
        self.threads = threads
        self._stop = threading.Event()
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        with SessionLocal() as db:  # jobs interrupted by a restart go back to the queue
            db.execute(update(Job).where(Job.status == "running").values(status="queued"))
            db.commit()
        for i in range(self.threads):
            threading.Thread(target=self._loop, name=f"lz-worker-{i}", daemon=True).start()
        threading.Thread(target=self._scheduler, name="lz-scheduler", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                with SessionLocal() as db:
                    job = claim_next(db)
                    if job:
                        run_job(db, job)
                        continue
            except Exception:  # noqa: BLE001
                log.exception("worker loop error")
            self._stop.wait(1.0)

    def _scheduler(self) -> None:
        last: dict[str, float] = {}
        self._stop.wait(5)
        while not self._stop.is_set():
            now = time.monotonic()
            for name, every, fn in PERIODIC:
                if now - last.get(name, -1e9) >= every:
                    last[name] = now
                    try:
                        fn()
                    except Exception:  # noqa: BLE001
                        log.exception("periodic %s failed", name)
            self._stop.wait(20)


worker = Worker()
