"""Library and inbox: uploads (multi-file, share target, iOS Shortcut, mail webhook), documents, review list,
search, bulk audio import."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..ingest.channels import import_mime
from ..ingest.pipeline import confirm_assignment, intake
from ..jobs import enqueue
from ..models import Chunk, Document, Event, InboxItem, Lecture, Module, Recording, User
from ..retrieval.index import bump, search
from ..security import _user_from_request, current_user, limiter
from ..storage import storage
from ..text import short

router = APIRouter(prefix="/api", tags=["library"])


def doc_out(d: Document) -> dict:
    return {"id": d.id, "title": d.title, "original_name": d.original_name, "kind": d.kind, "module_id": d.module_id,
            "lecture_id": d.lecture_id, "recording_id": d.recording_id, "mime": d.mime, "size": d.size,
            "pages": d.pages, "status": d.status, "status_detail": d.status_detail, "source": d.source,
            "doc_date": d.doc_date.isoformat() if d.doc_date else None, "confidence": d.confidence,
            "needs_review": d.needs_review, "review_reason": d.review_reason, "version": d.version,
            "version_of": d.version_of, "meta": {k: v for k, v in (d.meta or {}).items() if k != "done_parts"},
            "created_at": d.created_at.isoformat() if d.created_at else None}


async def _read(f: UploadFile) -> bytes:
    data = await f.read()
    if len(data) > get_settings().max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"{f.filename}: Datei zu groß (max. {get_settings().max_upload_mb} MB).")
    return data


def _mtimes(raw: str | None, n: int) -> list[datetime | None]:
    out: list[datetime | None] = []
    for part in (raw or "").split(","):
        try:
            out.append(datetime.fromtimestamp(int(part) / 1000) if part.strip() else None)
        except ValueError:
            out.append(None)
    return (out + [None] * n)[:n]


@router.post("/documents/upload")
async def upload(files: list[UploadFile] = File(...), module_id: int | None = Form(None),
                 lecture_id: int | None = Form(None), last_modified: str | None = Form(None),
                 channel: str = Form("upload"), user: User = Depends(current_user), db: Session = Depends(get_db)):
    if module_id:
        m = db.get(Module, module_id)
        if not m or m.user_id != user.id:
            raise HTTPException(404, "Modul nicht gefunden.")
    batch = uuid.uuid4().hex[:10]
    out = []
    for f, mt in zip(files, _mtimes(last_modified, len(files))):
        data = await _read(f)
        doc, item = intake(db, user, data, f.filename or "Datei", f.content_type or "",
                           channel=channel if channel in ("upload", "import", "share") else "upload",
                           module_id=module_id, file_mtime=mt, batch=batch, lecture_id=lecture_id)
        out.append(doc_out(doc))
    db.commit()
    return {"batch": batch, "documents": out}


@router.post("/inbox/share")
async def share_target(request: Request, db: Session = Depends(get_db)):
    """PWA share_target (Android/desktop Chromium). iOS Safari does not support share targets."""
    user = _user_from_request(request, db)
    if user is None:
        return RedirectResponse("/login?next=/inbox", status_code=303)
    form = await request.form()
    n = 0
    for v in form.getlist("files"):
        if hasattr(v, "read"):
            data = await v.read()
            intake(db, user, data, v.filename or "Geteilt", v.content_type or "", channel="share")
            n += 1
    text = " ".join(str(form.get(k) or "") for k in ("title", "text", "url")).strip()
    if text and n == 0:
        intake(db, user, text.encode(), "Geteilt.txt", "text/plain", channel="share")
        n = 1
    db.commit()
    return RedirectResponse(f"/inbox?shared={n}", status_code=303)


@router.post("/inbox/drop/{token}")
async def drop(token: str, request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload endpoint for the iOS Shortcut (Share Sheet → "An Lernzentrum senden"). Token is revocable."""
    limiter.check(f"drop:{token[:8]}", 60, 3600)
    user = db.scalar(select(User).where(User.upload_token == token)) if len(token) >= 20 else None
    if user is None:
        raise HTTPException(404, "Unbekannter Link.")
    data = await _read(file)
    doc, _ = intake(db, user, data, file.filename or "Geteilt", file.content_type or "", channel="share")
    db.commit()
    return {"ok": True, "id": doc.id, "message": "Im Lernzentrum-Eingang angekommen."}


@router.post("/inbox/mail/{token}")
async def mail_webhook(token: str, request: Request, db: Session = Depends(get_db)):
    """Raw MIME webhook (e.g. from a mail forwarding service). Same token as the Shortcut link."""
    limiter.check(f"mail:{token[:8]}", 120, 3600)
    user = db.scalar(select(User).where(User.upload_token == token)) if len(token) >= 20 else None
    if user is None:
        raise HTTPException(404, "Unbekannter Link.")
    raw = await request.body()
    if len(raw) > 80 * 1024 * 1024:
        raise HTTPException(413)
    n = import_mime(db, user, raw)
    db.commit()
    return {"ok": True, "attachments": n}


@router.get("/documents")
def list_documents(module_id: int | None = None, kind: str | None = None, q: str | None = None,
                   user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    stmt = select(Document).where(Document.user_id == user.id, Document.status != "superseded")
    if module_id:
        stmt = stmt.where(Document.module_id == module_id)
    if kind:
        stmt = stmt.where(Document.kind == kind)
    rows = db.scalars(stmt.order_by(Document.created_at.desc()).limit(500)).all()
    if q:
        ql = q.lower()
        rows = [d for d in rows if ql in d.title.lower() or ql in d.original_name.lower()]
    return [doc_out(d) for d in rows]


def _own_doc(db: Session, did: int, user: User) -> Document:
    d = db.get(Document, did)
    if not d or d.user_id != user.id:
        raise HTTPException(404, "Nicht gefunden.")
    return d


@router.get("/documents/{did}")
def get_document(did: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    d = _own_doc(db, did, user)
    chunks = db.scalars(select(Chunk).where(Chunk.document_id == d.id).order_by(Chunk.ordinal)).all()
    pages: dict[int, str] = {}
    for c in chunks:
        if c.page:
            pages[c.page] = (pages.get(c.page, "") + " " + c.text).strip()
    return {**doc_out(d), "text": short(d.text or "", 20000), "page_texts": [{"page": p, "text": t}
                                                                         for p, t in sorted(pages.items())]}


@router.get("/documents/{did}/file")
def get_file(did: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    d = _own_doc(db, did, user)
    if not d.storage_key or not storage().exists(d.storage_key):
        raise HTTPException(404, "Datei nicht (mehr) gespeichert.")
    from urllib.parse import quote

    return Response(storage().get(d.storage_key), media_type=d.mime or "application/octet-stream",
                    headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(d.title)}",
                             "Cache-Control": "private, max-age=600"})


class DocPatch(BaseModel):
    module_id: int | None = None
    lecture_id: int | None = None
    kind: str | None = None
    title: str | None = None


@router.patch("/documents/{did}")
def patch_document(did: int, body: DocPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = _own_doc(db, did, user)
    if body.module_id is not None or body.kind or body.lecture_id:
        confirm_assignment(db, d, body.module_id if body.module_id is not None else d.module_id, body.lecture_id,
                           body.kind)
    if body.title:
        d.title = body.title[:300]
    db.commit()
    return doc_out(d)


@router.delete("/documents/{did}")
def delete_document(did: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    d = _own_doc(db, did, user)
    storage().delete(d.storage_key)
    db.delete(d)
    db.commit()
    bump()
    return {"ok": True}


@router.post("/documents/{did}/reprocess")
def reprocess(did: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    d = _own_doc(db, did, user)
    d.status = "pending"
    enqueue(db, "audio.import" if d.kind == "audio" else "doc.process", {"document_id": d.id}, user_id=user.id,
            label=f"Neu verarbeiten: {d.title}")
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- inbox & review
@router.get("/inbox")
def inbox(status: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    stmt = select(InboxItem, Document).join(Document, Document.id == InboxItem.document_id) \
        .where(InboxItem.user_id == user.id)
    if status:
        stmt = stmt.where(InboxItem.status == status)
    rows = db.execute(stmt.order_by(InboxItem.id.desc()).limit(200)).all()
    return [{"id": i.id, "status": i.status, "channel": i.channel, "note": i.note, "suggestion": i.suggestion,
             "created_at": i.created_at.isoformat(), "document": doc_out(d)} for i, d in rows]


class ConfirmIn(BaseModel):
    module_id: int | None
    lecture_id: int | None = None
    kind: str | None = None


@router.post("/inbox/{iid}/confirm")
def confirm(iid: int, body: ConfirmIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    item = db.get(InboxItem, iid)
    if not item or item.user_id != user.id:
        raise HTTPException(404)
    d = db.get(Document, item.document_id)
    confirm_assignment(db, d, body.module_id, body.lecture_id, body.kind)
    db.commit()
    return {"ok": True, "document": doc_out(d)}


@router.post("/inbox/{iid}/dismiss")
def dismiss(iid: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    item = db.get(InboxItem, iid)
    if not item or item.user_id != user.id:
        raise HTTPException(404)
    d = db.get(Document, item.document_id) if item.document_id else None
    if item.status == "duplicate" and d:
        storage().delete(d.storage_key)
        db.delete(d)
    else:
        item.status = "rejected"
    db.commit()
    bump()
    return {"ok": True}


@router.get("/review")
def review_list(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Everything that needs a human decision: low-confidence documents/recordings and unmatched events."""
    items = inbox("review", user, db)
    from datetime import timedelta

    from ..calendar_sync import TZ

    now = datetime.now(TZ).replace(tzinfo=None)
    evs = db.scalars(select(Event).where(Event.user_id == user.id, Event.module_id.is_(None), Event.source == "ics",
                                         Event.start >= now - timedelta(days=60)).order_by(Event.start)).all()
    series: dict[str, dict] = {}
    for e in evs:
        s = series.setdefault(e.title, {"event_id": e.id, "title": e.title, "count": 0, "next": e.start.isoformat(),
                                        "location": e.location, "score": e.match_score})
        s["count"] += 1
    lectures = db.scalars(select(Lecture).where(Lecture.user_id == user.id, Lecture.start >= now - timedelta(days=200))
                          .order_by(Lecture.start.desc()).limit(300)).all()
    return {"items": items, "events": list(series.values()),
            "lectures": [{"id": lec.id, "module_id": lec.module_id, "title": lec.title, "start": lec.start.isoformat()}
                         for lec in lectures]}


# ---------------------------------------------------------------- search
@router.get("/search")
def do_search(q: str, module_id: int | None = None, user: User = Depends(current_user),
              db: Session = Depends(get_db)) -> dict:
    from .. import statutes as st
    from ..providers import registry
    from ..text import find_statutes

    qvec = None
    emb = registry.embed(db, user, [q])
    if emb:
        qvec = emb[0]
    hits = search(db, user, q, module_id=module_id, k=20, query_vec=qvec,
                  boost_statutes=[r.key for r in find_statutes(q) if r.law])
    mods = {m.id: m for m in db.scalars(select(Module).where(Module.user_id == user.id))}
    norms = []
    for r in find_statutes(q):
        if r.law:
            n = st.get_norm(db, r.law, r.norm)
            if n:
                norms.append(st.as_source(n, r.absatz))
    db.commit()
    return {"query": q, "statutes": norms, "hits": [
        {**h.as_source(), "module": mods[h.module_id].short if h.module_id in mods else None,
         "color": mods[h.module_id].color if h.module_id in mods else None} for h in hits]}


@router.get("/recordings/{rid}/audio")
def recording_audio(rid: int, seq: int = 0, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from ..models import AudioChunk

    rec = db.get(Recording, rid)
    if not rec or rec.user_id != user.id:
        raise HTTPException(404)
    ch = db.scalar(select(AudioChunk).where(AudioChunk.recording_id == rid, AudioChunk.seq == seq))
    if ch and ch.storage_key:
        return Response(storage().get(ch.storage_key), media_type=ch.mime)
    doc = db.scalar(select(Document).where(Document.recording_id == rid, Document.kind == "audio"))
    if doc and doc.storage_key:
        return Response(storage().get(doc.storage_key), media_type=doc.mime or "audio/mp4")
    raise HTTPException(404, "Audio nicht gespeichert.")
