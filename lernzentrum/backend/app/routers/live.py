"""Live mode API: consent + start, chunk upload, SSE events, manual answers, finish."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import SessionLocal, get_db, utcnow
from ..jobs import enqueue
from ..live.answer import answer as make_answer
from ..live.answer import answer_dict, persist
from ..live.context import LiveContext
from ..live.pipeline import answer_and_emit, emit, ingest_segments
from ..models import (Answer, AudioChunk, ConsentLog, KeyMoment, Lecture, LiveEvent, Module, NumberFact, Recording,
                      TranscriptSegment, User)
from ..security import audit, current_user
from ..storage import storage
from ..text import sentences

router = APIRouter(prefix="/api", tags=["live"])

CONSENT_TEXT = ("Ich bestätige, dass die Lehrperson und alle Anwesenden der Aufnahme zugestimmt haben. "
                "Die Aufnahme dient nur meinem privaten Lernen.")


def _rec(db: Session, rid: int, user: User) -> Recording:
    r = db.get(Recording, rid)
    if not r or r.user_id != user.id:
        raise HTTPException(404, "Aufnahme nicht gefunden.")
    return r


def rec_out(db: Session, r: Recording) -> dict:
    m = db.get(Module, r.module_id) if r.module_id else None
    return {"id": r.id, "title": r.title, "module_id": r.module_id, "module": m.name if m else None,
            "module_short": m.short if m else None, "color": m.color if m else None, "lecture_id": r.lecture_id,
            "started_at": r.started_at.isoformat(), "ended_at": r.ended_at.isoformat() if r.ended_at else None,
            "duration_s": r.duration_s, "status": r.status, "source": r.source, "live_answers": r.live_answers,
            "answer_mode": r.answer_mode, "exam_mode": bool(m and m.exam_mode), "package_status": r.package_status,
            "participation": r.participation or [], "context": LiveContext.from_json(r.context).summary()}


class StartIn(BaseModel):
    module_id: int | None = None
    lecture_id: int | None = None
    consent: bool = False
    title: str | None = None


@router.get("/consent-text")
def consent_text() -> dict:
    return {"text": CONSENT_TEXT,
            "info": "Vorlesungen dürfen nur mit Einverständnis der Lehrperson und der Anwesenden aufgezeichnet werden "
                    "(Recht am eigenen Wort, § 201 StGB; DSGVO). Lernzentrum speichert deine Bestätigung mit "
                    "Zeitstempel. In Prüfungen darf die App nicht verwendet werden."}


@router.post("/recordings/start")
def start(body: StartIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    reminder = (user.settings or {}).get("consent_reminder", True)
    if reminder and not body.consent:
        raise HTTPException(428, "Bitte bestätige zuerst die Einwilligung aller Anwesenden.")
    module_id, lecture_id = body.module_id, body.lecture_id
    if lecture_id:
        lec = db.get(Lecture, lecture_id)
        if not lec or lec.user_id != user.id:
            raise HTTPException(404, "Vorlesung nicht gefunden.")
        module_id = module_id or lec.module_id
    mod = db.get(Module, module_id) if module_id else None
    if module_id and (not mod or mod.user_id != user.id):
        raise HTTPException(404, "Modul nicht gefunden.")
    consent = ConsentLog(user_id=user.id, module_id=module_id,
                         statement=CONSENT_TEXT if body.consent else "Erinnerung deaktiviert – keine Bestätigung")
    db.add(consent)
    db.flush()
    title = body.title or f"{mod.short if mod else 'Aufnahme'} {utcnow():%d.%m.%Y %H:%M}"
    rec = Recording(user_id=user.id, module_id=module_id, lecture_id=lecture_id, consent_id=consent.id, title=title,
                    live_answers=not (mod and mod.exam_mode),
                    answer_mode=(user.settings or {}).get("answer_mode", "short"))
    db.add(rec)
    db.flush()
    if mod and mod.exam_mode:
        emit(db, rec, "exam_guard", {"message": "Prüfungsmodus aktiv – Live-Antworten sind ausgeschaltet. "
                                                "Die App darf in Prüfungen nicht verwendet werden."})
    audit(db, user.id, "recording_start", f"rec={rec.id} module={module_id}")
    db.commit()
    return rec_out(db, rec)


@router.post("/recordings/{rid}/chunks")
async def upload_chunk(rid: int, file: UploadFile = File(...), seq: int = Form(...), offset_s: float = Form(0),
                       duration_s: float = Form(0), late: bool = Form(False), user: User = Depends(current_user),
                       db: Session = Depends(get_db)) -> dict:
    rec = _rec(db, rid, user)
    data = await file.read()
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(413, "Audio-Abschnitt zu groß.")
    existing = db.scalar(select(AudioChunk).where(AudioChunk.recording_id == rid, AudioChunk.seq == seq))
    if existing:
        return {"ok": True, "duplicate": True}
    ch = AudioChunk(user_id=user.id, recording_id=rid, seq=seq, offset_s=offset_s, duration_s=duration_s,
                    storage_key=storage().put(data), mime=file.content_type or "audio/webm", late=late)
    db.add(ch)
    db.flush()
    if late:
        emit(db, rec, "gap", {"seq": seq, "offset_s": offset_s, "message": "Offline-Lücke wird nachträglich "
                                                                          "transkribiert."})
    enqueue(db, "live.chunk", {"chunk_id": ch.id}, user_id=user.id, label=f"Transkription {rec.title} #{seq}",
            batch=f"rec{rid}")
    db.commit()
    return {"ok": True, "chunk_id": ch.id}


class SimIn(BaseModel):
    text: str
    start_s: float | None = None
    seconds_per_sentence: float = 6.0


@router.post("/recordings/{rid}/simulate")
def simulate(rid: int, body: SimIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Feed text as if it had been transcribed (demo mode, tests, typing what the lecturer says)."""
    rec = _rec(db, rid, user)
    t = body.start_s if body.start_s is not None else (rec.duration_s or 0)
    segs = []
    for s in sentences(body.text) or [body.text]:
        segs.append((t, t + body.seconds_per_sentence, s))
        t += body.seconds_per_sentence
    ingest_segments(db, user, rec, segs)
    db.commit()
    return {"ok": True, "segments": len(segs)}


class AskIn(BaseModel):
    question: str | None = None
    mode: str | None = None


@router.post("/recordings/{rid}/ask")
def ask_in_lecture(rid: int, body: AskIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Manual "answer this" button. Without text: answers the last question-like passage."""
    rec = _rec(db, rid, user)
    ctx = LiveContext.from_json(rec.context)
    q = (body.question or "").strip()
    trigger = "ask" if q else "manual"
    if not q:
        segs = db.scalars(select(TranscriptSegment).where(TranscriptSegment.recording_id == rid)
                          .order_by(TranscriptSegment.start_s.desc()).limit(4)).all()
        flagged = [s for s in segs if "question" in (s.flags or [])]
        q = flagged[0].text if flagged else " ".join(s.text for s in reversed(segs[:2]))
    if not q:
        raise HTTPException(422, "Noch kein Text zum Beantworten.")
    rows = answer_and_emit(db, user, rec, ctx, q, ctx.now, trigger, body.mode)
    rec.context = {**ctx.to_json(), "_suggested_at": (rec.context or {}).get("_suggested_at", -1e9)}
    db.commit()
    return {"answers": [answer_dict(a) for a in rows]}


class RecPatch(BaseModel):
    answer_mode: str | None = None
    live_answers: bool | None = None
    title: str | None = None
    module_id: int | None = None


@router.patch("/recordings/{rid}")
def patch_recording(rid: int, body: RecPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rec = _rec(db, rid, user)
    mod = db.get(Module, body.module_id or rec.module_id) if (body.module_id or rec.module_id) else None
    if body.answer_mode in ("short", "detailed"):
        rec.answer_mode = body.answer_mode
    if body.live_answers is not None:
        if body.live_answers and mod and mod.exam_mode:
            raise HTTPException(409, "Prüfungsmodus aktiv – Live-Antworten bleiben aus.")
        rec.live_answers = body.live_answers
    if body.title:
        rec.title = body.title[:300]
    if body.module_id:
        rec.module_id = body.module_id
    db.commit()
    return rec_out(db, rec)


class PartIn(BaseModel):
    kind: str  # asked | answered
    text: str = ""


@router.post("/recordings/{rid}/participation")
def participation(rid: int, body: PartIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    rec = _rec(db, rid, user)
    ctx = LiveContext.from_json(rec.context)
    entry = {"kind": "asked" if body.kind == "asked" else "answered", "text": body.text[:300], "at_s": ctx.now,
             "at": utcnow().isoformat()}
    rec.participation = [*(rec.participation or []), entry]
    emit(db, rec, "participation", {"count": len(rec.participation), "entry": entry})
    db.commit()
    return {"count": len(rec.participation), "participation": rec.participation}


@router.post("/recordings/{rid}/finish")
def finish(rid: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    rec = _rec(db, rid, user)
    rec.ended_at, rec.status = utcnow(), "processing"
    emit(db, rec, "status", {"level": "info", "message": "Aufnahme beendet. Nachbereitung läuft …"})
    enqueue(db, "live.finalize", {"recording_id": rec.id}, user_id=user.id, label=f"Abschluss {rec.title}",
            delay_s=0)
    audit(db, user.id, "recording_finish", f"rec={rec.id}")
    db.commit()
    return rec_out(db, rec)


@router.get("/recordings")
def list_recordings(module_id: int | None = None, user: User = Depends(current_user),
                    db: Session = Depends(get_db)) -> list[dict]:
    q = select(Recording).where(Recording.user_id == user.id)
    if module_id:
        q = q.where(Recording.module_id == module_id)
    return [rec_out(db, r) for r in db.scalars(q.order_by(Recording.started_at.desc()).limit(200))]


@router.get("/recordings/{rid}")
def recording_detail(rid: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    rec = _rec(db, rid, user)
    segs = db.scalars(select(TranscriptSegment).where(TranscriptSegment.recording_id == rid)
                      .order_by(TranscriptSegment.start_s)).all()
    answers = db.scalars(select(Answer).where(Answer.recording_id == rid).order_by(Answer.id)).all()
    moments = db.scalars(select(KeyMoment).where(KeyMoment.recording_id == rid).order_by(KeyMoment.at_s)).all()
    numbers = db.scalars(select(NumberFact).where(NumberFact.recording_id == rid).order_by(NumberFact.at_s)).all()
    chunks = db.scalars(select(AudioChunk).where(AudioChunk.recording_id == rid).order_by(AudioChunk.seq)).all()
    return {**rec_out(db, rec),
            "transcript": [{"id": s.id, "start_s": s.start_s, "end_s": s.end_s, "text": s.text, "flags": s.flags}
                           for s in segs],
            "answers": [answer_dict(a) for a in answers],
            "moments": [{"at_s": m.at_s, "cue": m.cue, "text": m.text} for m in moments],
            "numbers": [{"at_s": n.at_s, "kind": n.kind, "value": n.value, "context": n.context} for n in numbers],
            "chunks": [{"seq": c.seq, "offset_s": c.offset_s, "status": c.status, "late": c.late,
                        "has_audio": bool(c.storage_key)} for c in chunks]}


@router.delete("/recordings/{rid}")
def delete_recording(rid: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    rec = _rec(db, rid, user)
    for c in db.scalars(select(AudioChunk).where(AudioChunk.recording_id == rid)):
        storage().delete(c.storage_key)
    db.delete(rec)
    db.commit()
    from ..retrieval.index import bump

    bump()
    return {"ok": True}


def _event_json(e: LiveEvent) -> dict:
    return {"id": e.id, "kind": e.kind, "payload": e.payload, "at": e.created_at.isoformat()}


@router.get("/recordings/{rid}/events")
def poll_events(rid: int, after: int = 0, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _rec(db, rid, user)
    rows = db.scalars(select(LiveEvent).where(LiveEvent.recording_id == rid, LiveEvent.id > after)
                      .order_by(LiveEvent.id).limit(300)).all()
    return [_event_json(e) for e in rows]


@router.get("/recordings/{rid}/stream")
async def stream(rid: int, request: Request, after: int = 0, user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    _rec(db, rid, user)
    last_id = int(request.headers.get("last-event-id") or after or 0)

    async def gen():
        nonlocal last_id
        idle = 0
        yield "retry: 2000\n\n"
        while True:
            if await request.is_disconnected():
                break
            with SessionLocal() as s:
                rows = s.scalars(select(LiveEvent).where(LiveEvent.recording_id == rid, LiveEvent.id > last_id)
                                 .order_by(LiveEvent.id).limit(200)).all()
                out = [_event_json(e) for e in rows]
            for e in out:
                last_id = e["id"]
                yield f"id: {e['id']}\nevent: {e['kind']}\ndata: {json.dumps(e, ensure_ascii=False)}\n\n"
            idle = 0 if out else idle + 1
            if idle and idle % 20 == 0:
                yield ": keepalive\n\n"
            await asyncio.sleep(0.6)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------- ask your material (outside a lecture)
class AskAnyIn(BaseModel):
    question: str
    module_id: int | None = None
    mode: str = "short"


@router.post("/ask")
def ask_any(body: AskAnyIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    mod = db.get(Module, body.module_id) if body.module_id else None
    results = make_answer(db, user, body.question, module_id=body.module_id, mode=body.mode,
                          profile=mod.lecturer_profile if mod else None)
    rows = persist(db, user, results, question=body.question, module_id=body.module_id, recording_id=None,
                   at_s=None, trigger="ask", mode=body.mode)
    db.commit()
    return {"answers": [answer_dict(a) for a in rows]}


@router.get("/answers")
def answer_history(module_id: int | None = None, level: str | None = None, user: User = Depends(current_user),
                   db: Session = Depends(get_db)) -> list[dict]:
    q = select(Answer).where(Answer.user_id == user.id)
    if module_id:
        q = q.where(Answer.module_id == module_id)
    if level:
        q = q.where(Answer.level == level)
    return [answer_dict(a) for a in db.scalars(q.order_by(Answer.id.desc()).limit(300))]


class FeedbackIn(BaseModel):
    feedback: str  # correct | wrong | used


@router.post("/answers/{aid}/feedback")
def answer_feedback(aid: int, body: FeedbackIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = db.get(Answer, aid)
    if not a or a.user_id != user.id:
        raise HTTPException(404)
    a.feedback = body.feedback[:20]
    if body.feedback == "used" and a.recording_id:
        rec = db.get(Recording, a.recording_id)
        if rec:
            rec.participation = [*(rec.participation or []), {"kind": "answered", "text": a.question[:300],
                                                              "at_s": a.at_s, "at": utcnow().isoformat()}]
    db.commit()
    return answer_dict(a)
