"""Modules, timetable (calendars, events, lectures), home screen, dashboards, deadlines, announcements."""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..calendar_sync import TZ, IcsError, current_lecture, normalize_url, suggest_modules, sync_calendar, sync_lectures
from ..config import brand
from ..db import get_db, utcnow
from ..models import (Announcement, Answer, Calendar, Deadline, Document, Event, Flashcard, InboxItem, LearnItem,
                      Lecture, Module, Recording, User)
from ..security import current_user

router = APIRouter(prefix="/api", tags=["planner"])


def now_local() -> datetime:
    return datetime.now(TZ).replace(tzinfo=None)


def module_out(m: Module) -> dict:
    return {"id": m.id, "name": m.name, "short": m.short, "color": m.color, "lecturer": m.lecturer,
            "aliases": m.aliases, "exam_date": m.exam_date.isoformat() if m.exam_date else None,
            "exam_mode": m.exam_mode, "retention_days": m.retention_days, "ects": m.ects,
            "moodle_course_id": m.moodle_course_id, "archived": m.archived}


def _own(db: Session, model, oid: int, user: User):
    row = db.get(model, oid)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "Nicht gefunden.")
    return row


# ---------------------------------------------------------------- modules
class ModuleIn(BaseModel):
    name: str
    short: str | None = None
    color: str | None = None
    lecturer: str = ""
    aliases: list[str] = []
    exam_date: datetime | None = None
    ects: int = 5
    retention_days: int | None = None


class ModulePatch(BaseModel):
    name: str | None = None
    short: str | None = None
    color: str | None = None
    lecturer: str | None = None
    aliases: list[str] | None = None
    exam_date: datetime | None = None
    exam_mode: bool | None = None
    ects: int | None = None
    retention_days: int | None = None
    archived: bool | None = None
    clear_exam_date: bool = False


def make_short(name: str) -> str:
    words = [w for w in name.replace("-", " ").split() if w[:1].isupper() and len(w) > 2]
    s = "".join(w[0] for w in words[:4]).upper()
    return s if len(s) >= 2 else name[:4].upper()


@router.get("/modules")
def list_modules(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    return [module_out(m) for m in db.scalars(select(Module).where(Module.user_id == user.id).order_by(Module.name))]


@router.post("/modules")
def create_module(body: ModuleIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    palette = brand().get("module_palette", ["#2F5D8C"])
    count = db.scalar(select(func.count(Module.id)).where(Module.user_id == user.id)) or 0
    m = Module(user_id=user.id, name=body.name.strip()[:200], short=(body.short or make_short(body.name))[:20],
               color=body.color or palette[count % len(palette)], lecturer=body.lecturer, aliases=body.aliases,
               exam_date=body.exam_date, ects=body.ects, retention_days=body.retention_days)
    db.add(m)
    db.flush()
    for cal in db.scalars(select(Calendar).where(Calendar.user_id == user.id)):
        try:
            sync_calendar(db, cal)
        except IcsError:
            _rematch_events(db, user)
    db.commit()
    return module_out(m)


def _rematch_events(db: Session, user: User) -> None:
    from ..calendar_sync import MATCH_THRESHOLD
    from ..ingest.classify import match_event_to_module

    mods = list(db.scalars(select(Module).where(Module.user_id == user.id, Module.archived.is_(False))))
    for ev in db.scalars(select(Event).where(Event.user_id == user.id, Event.match_confirmed.is_(False))):
        g = match_event_to_module(ev.title, ev.location, ev.description, mods)
        ev.module_id = g.value if g.confidence >= MATCH_THRESHOLD else None
        ev.match_score = g.confidence
    sync_lectures(db, user.id)


@router.patch("/modules/{mid}")
def patch_module(mid: int, body: ModulePatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = _own(db, Module, mid, user)
    data = body.model_dump(exclude_none=True)
    clear = data.pop("clear_exam_date", False)
    for k, v in data.items():
        setattr(m, k, v)
    if clear:
        m.exam_date = None
    db.commit()
    return module_out(m)


@router.delete("/modules/{mid}")
def delete_module(mid: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    m = _own(db, Module, mid, user)
    db.delete(m)
    db.commit()
    return {"ok": True}


class ProfileIn(BaseModel):
    notes: str = ""
    terms: list[str] | None = None


@router.get("/modules/{mid}/profile")
def get_profile(mid: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    m = _own(db, Module, mid, user)
    p = m.lecturer_profile or {}
    return {"notes": p.get("notes", ""), "terms": p.get("terms", []), "corrections": p.get("corrections", [])[-20:],
            "lectures": p.get("lectures", 0), "lecturer": m.lecturer}


@router.put("/modules/{mid}/profile")
def put_profile(mid: int, body: ProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = _own(db, Module, mid, user)
    p = dict(m.lecturer_profile or {})
    p["notes"] = body.notes[:4000]
    if body.terms is not None:
        p["terms"] = [t.strip() for t in body.terms if t.strip()][:60]
    m.lecturer_profile = p
    db.commit()
    return get_profile(mid, user, db)


@router.get("/modules/{mid}/dashboard")
def dashboard(mid: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    m = _own(db, Module, mid, user)
    now = now_local()
    cards_total = db.scalar(select(func.count(Flashcard.id)).where(Flashcard.module_id == mid)) or 0
    cards_due = db.scalar(select(func.count(Flashcard.id)).where(Flashcard.module_id == mid,
                                                                 Flashcard.due <= utcnow())) or 0
    cards_known = db.scalar(select(func.count(Flashcard.id)).where(Flashcard.module_id == mid,
                                                                   Flashcard.repetitions >= 2)) or 0
    lectures_past = db.scalar(select(func.count(Lecture.id)).where(Lecture.module_id == mid, Lecture.start <= now)) or 0
    lectures_total = db.scalar(select(func.count(Lecture.id)).where(Lecture.module_id == mid)) or 0
    recs = db.scalars(select(Recording).where(Recording.module_id == mid).order_by(Recording.started_at.desc())
                      .limit(8)).all()
    docs = db.scalars(select(Document).where(Document.module_id == mid, Document.status.in_(["ready", "waiting"]))
                      .order_by(Document.created_at.desc()).limit(50)).all()
    open_q = db.scalars(select(LearnItem).where(LearnItem.module_id == mid, LearnItem.kind == "open_question",
                                                LearnItem.done.is_(False)).limit(10)).all()
    deadlines = db.scalars(select(Deadline).where(Deadline.module_id == mid, Deadline.due >= now - timedelta(days=1),
                                                  Deadline.status.in_(["accepted", "proposed"]))
                           .order_by(Deadline.due).limit(10)).all()
    ann = db.scalars(select(Announcement).where(Announcement.module_id == mid)
                     .order_by(Announcement.posted_at.desc()).limit(5)).all()
    next_lec = db.scalar(select(Lecture).where(Lecture.module_id == mid, Lecture.start >= now).order_by(Lecture.start))
    progress = round(0.5 * (cards_known / cards_total if cards_total else 0) +
                     0.5 * (lectures_past / lectures_total if lectures_total else 0), 2)
    from ..learn.core import gap_finder

    gaps = gap_finder(db, mid)
    return {
        "module": module_out(m), "progress": progress,
        "exam_in_days": (m.exam_date.date() - now.date()).days if m.exam_date else None,
        "cards": {"total": cards_total, "due": cards_due, "known": cards_known},
        "lectures": {"past": lectures_past, "total": lectures_total,
                     "next": {"start": next_lec.start.isoformat(), "title": next_lec.title} if next_lec else None},
        "recordings": [{"id": r.id, "title": r.title, "started_at": r.started_at.isoformat(), "duration_s": r.duration_s,
                        "status": r.status, "package_status": r.package_status} for r in recs],
        "documents": [{"id": d.id, "title": d.title, "kind": d.kind, "pages": d.pages, "status": d.status,
                       "doc_date": d.doc_date.isoformat() if d.doc_date else None} for d in docs],
        "open_questions": [{"id": q.id, "title": q.title} for q in open_q],
        "gaps": gaps[:5], "gap_count": len(gaps),
        "deadlines": [deadline_out(d) for d in deadlines],
        "announcements": [{"id": a.id, "title": a.title, "body": a.body[:400], "author": a.author,
                           "posted_at": a.posted_at.isoformat(), "read": a.read} for a in ann],
        "next_tasks": _next_tasks(cards_due, open_q, gaps, m),
    }


def _next_tasks(cards_due: int, open_q: list, gaps: list, m: Module) -> list[str]:
    tasks = []
    if cards_due:
        tasks.append(f"{cards_due} Karteikarten wiederholen")
    if open_q:
        tasks.append(f"{len(open_q)} offene Fragen klären")
    if gaps:
        tasks.append(f"{len(gaps)} Folienabschnitte nacharbeiten (nicht besprochen)")
    if m.exam_date:
        tasks.append("Probeklausur schreiben")
    return tasks


# ---------------------------------------------------------------- calendars & events
class CalendarIn(BaseModel):
    url: str
    name: str = "Stundenplan"
    kind: str = "timetable"


@router.get("/calendars")
def list_calendars(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    out = []
    for c in db.scalars(select(Calendar).where(Calendar.user_id == user.id)):
        url = c.url
        out.append({"id": c.id, "name": c.name, "kind": c.kind, "url_hint": url[:28] + "…" if len(url) > 30 else url,
                    "last_sync": c.last_sync.isoformat() if c.last_sync else None, "last_status": c.last_status})
    return out


@router.post("/calendars")
def add_calendar(body: CalendarIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    try:
        url = normalize_url(body.url)
    except IcsError as exc:
        raise HTTPException(422, str(exc)) from exc
    cal = Calendar(user_id=user.id, url=url, name=body.name[:120], kind=body.kind if body.kind in
                   ("timetable", "moodle") else "timetable")
    db.add(cal)
    db.flush()
    try:
        res = sync_calendar(db, cal)
    except IcsError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc
    db.commit()
    return {"id": cal.id, **res}


@router.post("/calendars/{cid}/sync")
def resync(cid: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    cal = _own(db, Calendar, cid, user)
    try:
        res = sync_calendar(db, cal)
    except IcsError as exc:
        cal.last_status = f"Fehler: {exc}"
        db.commit()
        raise HTTPException(422, str(exc)) from exc
    db.commit()
    return res


@router.delete("/calendars/{cid}")
def delete_calendar(cid: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    cal = _own(db, Calendar, cid, user)
    db.delete(cal)
    db.flush()
    sync_lectures(db, user.id)
    db.commit()
    return {"ok": True}


def event_out(e: Event, mods: dict[int, Module]) -> dict:
    m = mods.get(e.module_id) if e.module_id else None
    return {"id": e.id, "title": e.title, "start": e.start.isoformat(), "end": e.end.isoformat(),
            "location": e.location, "module_id": e.module_id, "module": m.short if m else None,
            "color": m.color if m else None, "match_score": e.match_score, "confirmed": e.match_confirmed,
            "source": e.source}


@router.get("/events")
def events(start: datetime | None = None, days: int = 7, user: User = Depends(current_user),
           db: Session = Depends(get_db)) -> list[dict]:
    start = start or now_local().replace(hour=0, minute=0, second=0, microsecond=0)
    mods = {m.id: m for m in db.scalars(select(Module).where(Module.user_id == user.id))}
    rows = db.scalars(select(Event).where(Event.user_id == user.id, Event.start >= start,
                                          Event.start < start + timedelta(days=min(days, 62))).order_by(Event.start))
    return [event_out(e, mods) for e in rows]


class EventMatchIn(BaseModel):
    module_id: int | None


@router.post("/events/{eid}/module")
def set_event_module(eid: int, body: EventMatchIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ev = _own(db, Event, eid, user)
    same = db.scalars(select(Event).where(Event.user_id == user.id, Event.title == ev.title)).all()
    for e in same:  # apply to the whole series
        e.module_id, e.match_confirmed, e.match_score = body.module_id, True, 1.0
    if body.module_id:
        m = _own(db, Module, body.module_id, user)
        if ev.title not in m.aliases:
            m.aliases = [*m.aliases, ev.title][:20]
    sync_lectures(db, user.id)
    db.commit()
    return {"ok": True, "updated": len(same)}


@router.get("/modules-suggestions")
def module_suggestions(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    return suggest_modules(db, user.id)


@router.get("/lectures/current")
def lecture_now(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return {"current": current_lecture(db, user, now_local())}


# ---------------------------------------------------------------- deadlines & announcements
def deadline_out(d: Deadline) -> dict:
    return {"id": d.id, "title": d.title, "due": d.due.isoformat(), "module_id": d.module_id, "source": d.source,
            "status": d.status}


class DeadlineIn(BaseModel):
    title: str
    due: datetime
    module_id: int | None = None


class DeadlinePatch(BaseModel):
    status: str | None = None
    title: str | None = None
    due: datetime | None = None
    module_id: int | None = None


@router.get("/deadlines")
def list_deadlines(include_proposed: bool = True, user: User = Depends(current_user),
                   db: Session = Depends(get_db)) -> list[dict]:
    st = ["accepted", "proposed"] if include_proposed else ["accepted"]
    rows = db.scalars(select(Deadline).where(Deadline.user_id == user.id, Deadline.status.in_(st),
                                             Deadline.due >= now_local() - timedelta(days=1)).order_by(Deadline.due))
    return [deadline_out(d) for d in rows]


@router.post("/deadlines")
def add_deadline(body: DeadlineIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    d = Deadline(user_id=user.id, title=body.title[:300], due=body.due, module_id=body.module_id, status="accepted")
    db.add(d)
    db.commit()
    return deadline_out(d)


@router.patch("/deadlines/{did}")
def patch_deadline(did: int, body: DeadlinePatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = _own(db, Deadline, did, user)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(d, k, v)
    db.commit()
    return deadline_out(d)


@router.get("/deadlines/{did}/ics")
def deadline_ics(did: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Calendar entry proposal as .ics (opens directly in iPad Calendar)."""
    from fastapi import Response

    d = _own(db, Deadline, did, user)
    stamp = d.due.strftime("%Y%m%dT%H%M%S")
    body = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Lernzentrum//DE\r\nBEGIN:VEVENT\r\n"
            f"UID:lz-deadline-{d.id}@lernzentrum\r\nDTSTAMP:{utcnow().strftime('%Y%m%dT%H%M%SZ')}\r\n"
            f"DTSTART;TZID=Europe/Berlin:{stamp}\r\nDTEND;TZID=Europe/Berlin:{stamp}\r\n"
            f"SUMMARY:{d.title}\r\nBEGIN:VALARM\r\nTRIGGER:-P1D\r\nACTION:DISPLAY\r\nDESCRIPTION:{d.title}\r\n"
            "END:VALARM\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
    return Response(body, media_type="text/calendar",
                    headers={"Content-Disposition": f'attachment; filename="frist-{d.id}.ics"'})


@router.get("/announcements")
def announcements(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(Announcement).where(Announcement.user_id == user.id)
                      .order_by(Announcement.posted_at.desc()).limit(50))
    return [{"id": a.id, "title": a.title, "body": a.body, "author": a.author, "module_id": a.module_id,
             "posted_at": a.posted_at.isoformat(), "read": a.read} for a in rows]


@router.post("/announcements/{aid}/read")
def read_announcement(aid: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    a = _own(db, Announcement, aid, user)
    a.read = True
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- home
@router.get("/home")
def home(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    now = now_local()
    day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    mods = {m.id: m for m in db.scalars(select(Module).where(Module.user_id == user.id, Module.archived.is_(False)))}
    today = db.scalars(select(Event).where(Event.user_id == user.id, Event.start >= day0,
                                           Event.start < day0 + timedelta(days=1), Event.source == "ics")
                       .order_by(Event.start)).all()
    lec_by_event = {lec.event_id: lec.id for lec in db.scalars(select(Lecture).where(
        Lecture.user_id == user.id, Lecture.start >= day0, Lecture.start < day0 + timedelta(days=1)))}
    review = db.scalar(select(func.count(InboxItem.id)).where(InboxItem.user_id == user.id,
                                                              InboxItem.status == "review")) or 0
    unmatched = db.scalar(select(func.count(Event.id)).where(Event.user_id == user.id, Event.module_id.is_(None),
                                                             Event.source == "ics", Event.start >= day0)) or 0
    due_cards = db.scalar(select(func.count(Flashcard.id)).where(Flashcard.user_id == user.id,
                                                                 Flashcard.due <= utcnow())) or 0
    from ..learn.core import study_plan

    plan = [t for t in study_plan(db, user, days=2, now=now) if not t.get("deadline")][:4]
    deadlines = list_deadlines(True, user, db)[:6]
    last_answers = db.scalars(select(Answer).where(Answer.user_id == user.id).order_by(Answer.id.desc()).limit(3))
    return {
        "greeting": user.display_name or "",
        "now": now.isoformat(),
        "current": current_lecture(db, user, now),
        "today": [{**event_out(e, mods), "lecture_id": lec_by_event.get(e.id), "running": e.start <= now <= e.end}
                  for e in today],
        "deadlines": deadlines,
        "modules": [{**module_out(m), "due_cards": db.scalar(select(func.count(Flashcard.id)).where(
            Flashcard.module_id == m.id, Flashcard.due <= utcnow())) or 0,
            "exam_in_days": (m.exam_date.date() - now.date()).days if m.exam_date else None} for m in mods.values()],
        "review_count": review, "unmatched_events": unmatched, "due_cards": due_cards, "plan": plan,
        "recent_answers": [{"question": a.question, "level": a.level, "percent": a.percent} for a in last_answers],
        "unread_announcements": db.scalar(select(func.count(Announcement.id)).where(
            Announcement.user_id == user.id, Announcement.read.is_(False))) or 0,
    }
