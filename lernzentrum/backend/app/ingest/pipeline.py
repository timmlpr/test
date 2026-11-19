"""Inbox intake and processing jobs for documents and audio (incl. bulk import of old voice memos)."""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import utcnow
from ..jobs import enqueue, handler
from ..models import Deadline, Document, InboxItem, Lecture, Module, Recording, User
from ..providers import registry
from ..providers.base import MissingKey
from ..retrieval.index import index_document
from ..storage import sha256, storage
from ..text import short, simhash
from .classify import REVIEW_THRESHOLD, assign_by_time, canonical_name, date_from_filename, date_from_text, \
    find_duplicate, guess_kind, guess_module
from .extract import AUDIO_EXT, extract

AUDIO_SEGMENT_S = 600  # Groq free tier: 25 MB per file → split long memos into 10-minute mono 16 kHz parts


def ext_of(filename: str) -> str:
    return "." + filename.lower().rsplit(".", 1)[-1] if "." in filename else ""


def intake(db: Session, user: User, data: bytes, filename: str, mime: str, *, channel: str,
           module_id: int | None = None, file_mtime: datetime | None = None, batch: str = "",
           lecture_id: int | None = None) -> tuple[Document, InboxItem]:
    """Store a file encrypted, register it in the inbox and queue processing."""
    filename = Path(filename).name[:250] or "Datei"
    doc = Document(user_id=user.id, module_id=module_id, lecture_id=lecture_id, title=filename,
                   original_name=filename, mime=mime or "", size=len(data), storage_key=storage().put(data),
                   sha256=sha256(data), source=channel, status="pending",
                   meta={"file_mtime": file_mtime.isoformat() if file_mtime else None,
                         "module_hint": module_id})
    db.add(doc)
    db.flush()
    item = InboxItem(user_id=user.id, document_id=doc.id, channel=channel, status="processing")
    db.add(item)
    db.flush()
    is_audio = ext_of(filename) in AUDIO_EXT or (mime or "").startswith("audio/")
    enqueue(db, "audio.import" if is_audio else "doc.process", {"document_id": doc.id}, user_id=user.id,
            label=f"{'Audio' if is_audio else 'Datei'}: {filename}", batch=batch)
    return doc, item


DEADLINE_RE = re.compile(
    r"(?P<what>(?:abgabe|einreichung|anmeldung|frist|deadline|klausur|prüfung|test|hausarbeit|präsentation)"
    r"[^.\n]{0,60}?)\s*(?:bis(?: zum| spätestens)?|am|spätestens(?: am)?|:)\s*(?P<d>\d{1,2})\.(?P<m>\d{1,2})\.(?P<y>20\d{2})"
    r"(?:,?\s*(?P<h>\d{1,2})[:.](?P<mi>\d{2})\s*Uhr)?", re.I)


def extract_deadlines(text: str) -> list[tuple[str, datetime]]:
    out = []
    for m in DEADLINE_RE.finditer(text):
        try:
            when = datetime(int(m["y"]), int(m["m"]), int(m["d"]), int(m["h"] or 23), int(m["mi"] or 59))
        except ValueError:
            continue
        title = " ".join(m["what"].split()).strip(" :,-")
        out.append((title[:1].upper() + title[1:], when))
    return out


def _apply_classification(db: Session, user: User, doc: Document, item: InboxItem, text: str) -> None:
    hint = (doc.meta or {}).get("module_hint")
    kind = guess_kind(doc.original_name, text, doc.mime)
    mod = guess_module(db, user.id, doc.original_name, text, hint)
    mtime = (doc.meta or {}).get("file_mtime")
    when = date_from_filename(doc.original_name) or date_from_text(text) or \
        (datetime.fromisoformat(mtime) if mtime else None)
    doc.kind = doc.kind if doc.kind not in ("other", "") and doc.source == "moodle" else str(kind.value)
    doc.doc_date = when
    module = db.get(Module, mod.value) if mod.value else None
    conf = min(kind.confidence if kind.value != "other" else 0.7, mod.confidence)
    doc.confidence = round(conf, 2)
    if module:
        doc.module_id = module.id
    first_line = next((l.strip() for l in text.splitlines() if 6 < len(l.strip()) < 70), "")
    doc.title = canonical_name(module.short if module else None, when, doc.kind, ext_of(doc.original_name),
                               first_line if doc.kind in ("slides", "script", "exercise") else "")
    suggestion = {"module_id": mod.value, "module_reason": mod.reason, "module_confidence": mod.confidence,
                  "kind": doc.kind, "kind_confidence": kind.confidence, "date": when.isoformat() if when else None,
                  "title": doc.title}
    item.suggestion = suggestion
    if mod.confidence < REVIEW_THRESHOLD or module is None:
        doc.needs_review, item.status = True, "review"
        doc.review_reason = f"Modul unsicher ({int(mod.confidence * 100)} %, {mod.reason})"
    else:
        item.status = "sorted"


@handler("doc.process")
def process_document(db: Session, job) -> None:
    doc = db.get(Document, job.payload["document_id"])
    if doc is None:
        return
    user = db.get(User, doc.user_id)
    item = db.scalar(select(InboxItem).where(InboxItem.document_id == doc.id))
    doc.status = "processing"
    data = storage().get(doc.storage_key)
    ex = extract(data, doc.original_name, doc.mime, db, user)
    text = "\n\n".join(ex.pages)
    doc.text, doc.pages = text, len(ex.pages)
    doc.meta = {**(doc.meta or {}), "extract": ex.method, "notes": ex.notes, "handwriting": ex.handwriting}
    doc.simhash = simhash(text) if len(text) > 200 else ""
    if item is None:
        item = InboxItem(user_id=user.id, document_id=doc.id, channel=doc.source)
        db.add(item)
    dup = find_duplicate(db, user.id, doc.sha256, doc.simhash, doc.original_name, doc.module_id, exclude_id=doc.id)
    _apply_classification(db, user, doc, item, text)
    if dup.status == "duplicate":
        item.status, item.note = "duplicate", dup.reason
        doc.status, doc.version_of = "duplicate", dup.of_id
        db.commit()
        return
    if dup.status == "version":
        prev = db.get(Document, dup.of_id)
        doc.version_of, doc.version = prev.id, (prev.version or 1) + 1
        prev.status = "superseded"
        item.note = dup.reason
        from ..models import Chunk

        db.query(Chunk).filter(Chunk.document_id == prev.id).delete()
    index_document(db, doc, pages=ex.pages)
    for title, when in extract_deadlines(text):
        if when > utcnow() - timedelta(days=1):
            db.add(Deadline(user_id=user.id, module_id=doc.module_id, title=title, due=when, source="document",
                            source_ref=f"doc:{doc.id}"))
    doc.status = "ready"
    if ex.notes:
        doc.status_detail = " ".join(ex.notes)
    db.commit()


# ---------------------------------------------------------------- audio
def ffprobe(data: bytes, suffix: str) -> dict:
    with tempfile.NamedTemporaryFile(suffix=suffix) as f:
        f.write(data)
        f.flush()
        try:
            out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", f.name],
                                 capture_output=True, text=True, timeout=60)
            return json.loads(out.stdout or "{}").get("format", {})
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
            return {}


def recording_time(fmt: dict, filename: str, mtime_iso: str | None) -> tuple[datetime | None, str]:
    tags = {k.lower(): v for k, v in (fmt.get("tags") or {}).items()}
    for key in ("creation_time", "com.apple.quicktime.creationdate", "date"):
        if key in tags:
            try:
                dt = datetime.fromisoformat(tags[key].replace("Z", "+00:00"))
                if dt.tzinfo:
                    from zoneinfo import ZoneInfo

                    dt = dt.astimezone(ZoneInfo("Europe/Berlin")).replace(tzinfo=None)
                return dt, "Metadaten"
            except ValueError:
                pass
    d = date_from_filename(filename)
    if d:
        return d, "Dateiname"
    if mtime_iso:
        return datetime.fromisoformat(mtime_iso), "Änderungsdatum"
    return None, ""


def split_audio(data: bytes, suffix: str, seg_s: int = AUDIO_SEGMENT_S) -> list[tuple[float, bytes]]:
    """Convert to 16 kHz mono and split into segments (offset, bytes) with ffmpeg."""
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / f"in{suffix}"
        src.write_bytes(data)
        pattern = str(Path(tmp) / "part%04d.mp3")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-ac", "1", "-ar", "16000", "-b:a", "48k",
                        "-f", "segment", "-segment_time", str(seg_s), pattern], check=True, timeout=1800)
        parts = sorted(Path(tmp).glob("part*.mp3"))
        return [(i * seg_s, p.read_bytes()) for i, p in enumerate(parts)]


@handler("audio.import")
def import_audio(db: Session, job) -> None:
    from ..live.pipeline import finalize_recording, ingest_segments

    doc = db.get(Document, job.payload["document_id"])
    if doc is None:
        return
    user = db.get(User, doc.user_id)
    item = db.scalar(select(InboxItem).where(InboxItem.document_id == doc.id))
    data = storage().get(doc.storage_key)
    suffix = ext_of(doc.original_name) or ".m4a"
    fmt = ffprobe(data, suffix)
    duration = float(fmt.get("duration") or 0)
    when, how = recording_time(fmt, doc.original_name, (doc.meta or {}).get("file_mtime"))
    doc.kind, doc.doc_date = "audio", when
    hint = (doc.meta or {}).get("module_hint")
    match = assign_by_time(db, user.id, when, duration)
    module_id = hint or match.module_id
    conf = 1.0 if hint else match.confidence
    rec = db.scalar(select(Recording).where(Recording.id == (doc.recording_id or -1)))
    if rec is None:
        rec = Recording(user_id=user.id, module_id=module_id, lecture_id=match.lecture_id if not hint else None,
                        title=f"Import {doc.original_name}", started_at=when or utcnow(), status="processing",
                        source="import", live_answers=False)
        db.add(rec)
        db.flush()
        doc.recording_id = rec.id
    mod = db.get(Module, module_id) if module_id else None
    doc.module_id = module_id
    doc.confidence = conf
    doc.title = canonical_name(mod.short if mod else None, when, "audio", suffix)
    rec.title = doc.title.rsplit(".", 1)[0]
    if item:
        item.suggestion = {"module_id": module_id, "lecture_id": match.lecture_id, "date": when.isoformat() if when else None,
                           "date_source": how, "module_confidence": conf, "reason": match.reason,
                           "duration_s": duration}
        item.status = "sorted" if conf >= REVIEW_THRESHOLD else "review"
    if conf < REVIEW_THRESHOLD:
        doc.needs_review = True
        doc.review_reason = f"Zuordnung unsicher: {match.reason}" + (f" (Datum aus {how})" if how else "")
    db.commit()
    try:
        registry.stt_for(db, user)
    except MissingKey as exc:
        doc.status, doc.status_detail = "waiting", f"Wartet auf Transkription – {exc}"
        job.status = "waiting"
        job.error = str(exc)
        job.run_after = utcnow() + timedelta(minutes=30)
        db.commit()
        return
    done = set((doc.meta or {}).get("done_parts", []))
    parts = split_audio(data, suffix)
    for i, (offset, part) in enumerate(parts):
        if i in done:
            continue
        res = registry.transcribe(db, user, part, f"part{i}.mp3", "audio/mpeg",
                                  duration_hint=min(AUDIO_SEGMENT_S, max(10.0, duration - offset)))
        segs = [(offset + s.start, offset + s.end, s.text) for s in res.segments] or \
               ([(offset, offset + res.duration, res.text)] if res.text else [])
        ingest_segments(db, user, rec, segs, late=True)
        done.add(i)
        doc.meta = {**(doc.meta or {}), "done_parts": sorted(done)}
        job.progress = len(done) / max(1, len(parts))
        db.commit()
    rec.duration_s = duration or rec.duration_s
    rec.ended_at = (when + timedelta(seconds=duration)) if when else None
    tdoc = finalize_recording(db, rec)
    doc.status = "ready"
    doc.text = short(tdoc.text or "", 2000)
    db.commit()


def confirm_assignment(db: Session, doc: Document, module_id: int | None, lecture_id: int | None,
                       kind: str | None) -> None:
    """User confirmed a review item → apply and re-index under the new module."""
    from ..models import Chunk

    mod = db.get(Module, module_id) if module_id else None
    doc.module_id = module_id
    if kind:
        doc.kind = kind
    if lecture_id:
        doc.lecture_id = lecture_id
        lec = db.get(Lecture, lecture_id)
        if lec and not doc.doc_date:
            doc.doc_date = lec.start
    doc.needs_review, doc.review_reason, doc.confidence = False, "", 1.0
    doc.title = canonical_name(mod.short if mod else None, doc.doc_date, doc.kind, ext_of(doc.original_name))
    db.query(Chunk).filter(Chunk.document_id == doc.id).update({Chunk.module_id: module_id})
    if doc.recording_id:
        rec = db.get(Recording, doc.recording_id)
        if rec:
            rec.module_id, rec.lecture_id = module_id, lecture_id or rec.lecture_id
            tdoc = db.scalar(select(Document).where(Document.recording_id == rec.id, Document.kind == "transcript"))
            if tdoc:
                tdoc.module_id = module_id
                db.query(Chunk).filter(Chunk.document_id == tdoc.id).update({Chunk.module_id: module_id})
    item = db.scalar(select(InboxItem).where(InboxItem.document_id == doc.id))
    if item:
        item.status = "sorted"
    from ..retrieval.index import bump

    bump()
