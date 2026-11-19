"""Setup wizard state, user settings, API keys (masked), health checks, quota, jobs, export, delete-all."""
from __future__ import annotations

import io
import json
import zipfile
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import quota
from ..calendar_sync import IcsError, preview
from ..config import DEFAULT_MODELS, DEFAULT_QUOTAS
from ..crypto import random_token
from ..db import get_db, utcnow
from ..jobs import enqueue
from ..models import (Answer, AuditLog, Calendar, ConsentLog, Deadline, Document, Flashcard, Job, LearnItem, Module,
                      Recording, Secret, TranscriptSegment, User)
from ..providers import registry
from ..security import audit, current_user, verify_password
from ..storage import storage
from .auth import user_out

router = APIRouter(prefix="/api", tags=["settings"])

SETUP_STEPS = ["Konto", "API-Keys", "Stundenplan", "Moodle", "Module", "Import"]


# ---------------------------------------------------------------- wizard
class StepIn(BaseModel):
    step: int
    skipped: bool = False


@router.get("/setup")
def setup_state(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    secrets = {s.provider: s.status for s in db.scalars(select(Secret).where(Secret.user_id == user.id))}
    cals = db.scalars(select(Calendar).where(Calendar.user_id == user.id)).all()
    mods = db.scalars(select(Module).where(Module.user_id == user.id)).all()
    return {"step": user.setup_step, "steps": SETUP_STEPS, "skipped": user.setup_skipped,
            "done": {"1": True, "2": "groq" in secrets and "gemini" in secrets, "3": bool(cals),
                     "4": "moodle" in secrets or any(c.kind == "moodle" for c in cals), "5": bool(mods),
                     "6": False}}


@router.post("/setup/step")
def setup_step(body: StepIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    if body.skipped and body.step not in user.setup_skipped:
        user.setup_skipped = [*user.setup_skipped, body.step]
    user.setup_step = max(user.setup_step, min(7, body.step + 1))
    db.commit()
    return user_out(user)


# ---------------------------------------------------------------- settings
class SettingsIn(BaseModel):
    call_names: list[str] | None = None
    keep_audio: bool | None = None
    consent_reminder: bool | None = None
    answer_mode: str | None = None
    large_type: bool | None = None
    theme: str | None = None
    display_name: str | None = None
    models: dict[str, str] | None = None
    quotas: dict[str, dict[str, float]] | None = None
    review_threshold: float | None = None


@router.patch("/settings")
def update_settings(body: SettingsIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    s = dict(user.settings or {})
    for k, v in body.model_dump(exclude_none=True).items():
        if k == "display_name":
            user.display_name = v[:120]
        elif k == "models":
            s["models"] = {mk: mv for mk, mv in v.items() if mk in DEFAULT_MODELS and mv.strip()}
        elif k == "quotas":
            s["quotas"] = {p: {m: float(x) for m, x in q.items() if m in DEFAULT_QUOTAS.get(p, {})}
                           for p, q in v.items() if p in DEFAULT_QUOTAS}
        else:
            s[k] = v
    user.settings = s
    db.commit()
    return user_out(user)


@router.get("/settings/defaults")
def defaults() -> dict:
    return {"models": DEFAULT_MODELS, "quotas": DEFAULT_QUOTAS}


# ---------------------------------------------------------------- secrets
class SecretIn(BaseModel):
    value: str
    meta: dict | None = None


def _secret_out(row: Secret | None, provider: str) -> dict:
    info = registry.PROVIDERS.get(provider, {})
    if row is None:
        return {"provider": provider, "label": info.get("label", provider), "url": info.get("url", ""),
                "configured": False, "status": "missing", "hint": "", "detail": ""}
    meta = {k: v for k, v in (row.meta or {}).items() if k not in ("password",)}
    return {"provider": provider, "label": info.get("label", provider), "url": info.get("url", ""), "configured": True,
            "status": row.status, "hint": row.hint, "detail": row.status_detail, "meta": meta,
            "checked_at": row.checked_at.isoformat() if row.checked_at else None}


@router.get("/secrets")
def list_secrets(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    rows = {s.provider: s for s in db.scalars(select(Secret).where(Secret.user_id == user.id))}
    return [_secret_out(rows.get(p), p) for p in registry.PROVIDERS]


@router.put("/secrets/{provider}")
def put_secret(provider: str, body: SecretIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if provider not in ("groq", "gemini", "imap", "webdav"):
        raise HTTPException(400, "Unbekannter Anbieter.")
    if len(body.value.strip()) < 8:
        raise HTTPException(422, "Der Key ist zu kurz.")
    meta = None
    if provider in ("imap", "webdav"):
        if not body.meta or not body.meta.get("username") or not (body.meta.get("host") or body.meta.get("url")):
            raise HTTPException(422, "Server und Benutzername fehlen.")
        meta = {k: str(v) for k, v in body.meta.items() if k in ("host", "port", "username", "folder", "url")}
    row = registry.set_secret(db, user, provider, body.value, meta)
    audit(db, user.id, "secret_set", provider)
    db.commit()
    out = _secret_out(row, provider)
    if provider in ("groq", "gemini"):
        ok, msg = registry.test_provider(db, user, provider)
        out = _secret_out(registry.get_secret_row(db, user, provider), provider)
    elif provider in ("imap", "webdav"):
        enqueue(db, f"inbox.{provider}", {}, user_id=user.id, label=f"Eingang: {provider}")
        db.commit()
    return out


@router.post("/secrets/{provider}/test")
def test_secret(provider: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    if provider in ("groq", "gemini"):
        ok, msg = registry.test_provider(db, user, provider)
        return {"ok": ok, "message": msg}
    if provider == "moodle":
        from ..moodle import MoodleError, client_for

        cl = client_for(db, user)
        if not cl:
            return {"ok": False, "message": "Nicht verbunden."}
        try:
            info = cl.call("core_webservice_get_site_info")
            return {"ok": True, "message": f"Verbunden als {info.get('fullname')}"}
        except MoodleError as exc:
            return {"ok": False, "message": str(exc)}
    if provider in ("imap", "webdav"):
        from ..ingest.channels import imap_poll, webdav_sync

        try:
            n = imap_poll(db, user) if provider == "imap" else webdav_sync(db, user)
            return {"ok": True, "message": f"Verbunden. {n} neue Dateien."}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": f"Verbindung fehlgeschlagen: {exc.__class__.__name__}"}
    raise HTTPException(400, "Kein Test verfügbar.")


@router.delete("/secrets/{provider}")
def delete_secret(provider: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    registry.delete_secret(db, user, provider)
    audit(db, user.id, "secret_deleted", provider)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- upload token (iOS Shortcut)
@router.post("/inbox/upload-token")
def new_upload_token(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    user.upload_token = random_token(24)
    audit(db, user.id, "upload_token_rotated")
    db.commit()
    return {"token": user.upload_token}


@router.delete("/inbox/upload-token")
def revoke_upload_token(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    user.upload_token = None
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- health, quota, jobs
@router.get("/health/connections")
def connections(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    rows = {s.provider: s for s in db.scalars(select(Secret).where(Secret.user_id == user.id))}
    out = []
    for p, label, needed in (("groq", "Groq – Spracherkennung", "Live-Transkription, Import alter Aufnahmen"),
                             ("gemini", "Gemini – Antworten", "formulierte Antworten, Zusammenfassungen, Handschrift"),
                             ("moodle", "Moodle", "Dateien, Termine, Ankündigungen")):
        r = rows.get(p)
        out.append({"key": p, "label": label, "status": r.status if r else "missing",
                    "detail": (r.status_detail if r else f"fehlt: {needed}"),
                    "checked_at": r.checked_at.isoformat() if r and r.checked_at else None})
    cals = db.scalars(select(Calendar).where(Calendar.user_id == user.id)).all()
    if cals:
        bad = [c for c in cals if c.last_status.startswith("Fehler")]
        out.append({"key": "calendar", "label": "Stundenplan (ICS)", "status": "error" if bad else "ok",
                    "detail": "; ".join(f"{c.name}: {c.last_status}" for c in cals),
                    "checked_at": max((c.last_sync for c in cals if c.last_sync), default=None)})
    else:
        out.append({"key": "calendar", "label": "Stundenplan (ICS)", "status": "missing",
                    "detail": "fehlt: Kalender-Link", "checked_at": None})
    try:
        used = storage().usage_bytes()
        out.append({"key": "storage", "label": "Speicher (verschlüsselt)", "status": "ok",
                    "detail": f"{used / 1e6:.1f} MB belegt", "checked_at": utcnow().isoformat()})
    except OSError as exc:
        out.append({"key": "storage", "label": "Speicher", "status": "error", "detail": str(exc), "checked_at": None})
    from ..ingest.extract import tesseract_available

    out.append({"key": "ocr", "label": "Texterkennung (OCR)", "status": "ok" if tesseract_available() or
                rows.get("gemini") else "missing",
                "detail": ("Tesseract" if tesseract_available() else "") + (" + Gemini Vision" if rows.get("gemini")
                                                                            else ""),
                "checked_at": None})
    for o in out:
        if hasattr(o.get("checked_at"), "isoformat"):
            o["checked_at"] = o["checked_at"].isoformat()
    return out


@router.get("/quota")
def quota_state(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    return quota.snapshot(db, user)


@router.get("/jobs")
def jobs(user: User = Depends(current_user), db: Session = Depends(get_db), batch: str = "") -> list[dict]:
    q = select(Job).where(Job.user_id == user.id)
    if batch:
        q = q.where(Job.batch == batch)
    else:
        q = q.where((Job.status != "done") | (Job.finished_at >= utcnow() - timedelta(hours=2)))
    return [{"id": j.id, "kind": j.kind, "label": j.label, "status": j.status, "progress": j.progress,
             "error": j.error, "batch": j.batch, "created_at": j.created_at.isoformat()}
            for j in db.scalars(q.order_by(Job.id.desc()).limit(100))]


@router.post("/jobs/{job_id}/retry")
def retry_job(job_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    j = db.get(Job, job_id)
    if not j or j.user_id != user.id:
        raise HTTPException(404)
    j.status, j.attempts, j.run_after, j.error = "queued", 0, utcnow(), ""
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- privacy: export / delete
@router.get("/export")
def export_all(user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        def dump(name, rows, fields):
            zf.writestr(f"{name}.json", json.dumps([{f: (getattr(r, f).isoformat() if hasattr(getattr(r, f), "isoformat")
                                                          else getattr(r, f)) for f in fields} for r in rows],
                                                   ensure_ascii=False, indent=1))

        dump("account", [user], ["email", "display_name", "created_at", "settings"])
        dump("modules", db.scalars(select(Module).where(Module.user_id == user.id)),
             ["id", "name", "short", "lecturer", "exam_date", "lecturer_profile"])
        dump("recordings", db.scalars(select(Recording).where(Recording.user_id == user.id)),
             ["id", "module_id", "title", "started_at", "duration_s"])
        dump("transcripts", db.scalars(select(TranscriptSegment).where(TranscriptSegment.user_id == user.id)),
             ["recording_id", "start_s", "end_s", "text"])
        dump("answers", db.scalars(select(Answer).where(Answer.user_id == user.id)),
             ["question", "text", "level", "percent", "sources", "correction", "created_at"])
        dump("flashcards", db.scalars(select(Flashcard).where(Flashcard.user_id == user.id)), ["front", "back", "due"])
        dump("learn_items", db.scalars(select(LearnItem).where(LearnItem.user_id == user.id)),
             ["kind", "title", "body", "module_id"])
        dump("deadlines", db.scalars(select(Deadline).where(Deadline.user_id == user.id)), ["title", "due", "status"])
        dump("consent_log", db.scalars(select(ConsentLog).where(ConsentLog.user_id == user.id)),
             ["module_id", "statement", "created_at"])
        for d in db.scalars(select(Document).where(Document.user_id == user.id, Document.storage_key.is_not(None))):
            try:
                zf.writestr(f"files/{d.id}_{d.title}", storage().get(d.storage_key))
            except (OSError, ValueError):
                pass
    audit(db, user.id, "export")
    db.commit()
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="lernzentrum-export.zip"'})


class DeleteIn(BaseModel):
    password: str
    confirm: str


@router.post("/delete-all")
def delete_all(body: DeleteIn, response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.confirm != "LÖSCHEN" or not verify_password(user.password_hash, body.password):
        raise HTTPException(403, "Bitte Passwort und das Wort LÖSCHEN eingeben.")
    for d in db.scalars(select(Document).where(Document.user_id == user.id)):
        storage().delete(d.storage_key)
    from ..models import AudioChunk

    for c in db.scalars(select(AudioChunk).where(AudioChunk.user_id == user.id)):
        storage().delete(c.storage_key)
    db.execute(delete(AuditLog).where(AuditLog.user_id == user.id))
    db.delete(user)
    db.commit()
    from ..retrieval.index import bump

    bump()
    response.delete_cookie("lz_session", path="/")
    return {"ok": True}


@router.get("/calendars/preview")
def calendar_preview(url: str, user: User = Depends(current_user)) -> dict:
    try:
        return {"ok": True, "events": preview(url)}
    except IcsError as exc:
        return {"ok": False, "message": str(exc), "events": []}
