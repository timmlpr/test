"""Timetable import via ICS/webcal subscription links (read-only, no password).

Events are expanded (RRULE) for −30…+180 days, matched to modules (fuzzy title/lecturer), and turned into
lectures. Unmatched or low-confidence events show up in the review list.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import recurring_ical_events
from icalendar import Calendar as ICal
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import SessionLocal, utcnow
from .ingest.classify import match_event_to_module
from .jobs import enqueue, handler, periodic
from .models import Calendar, Event, Lecture, Module, User

TZ = ZoneInfo("Europe/Berlin")
MATCH_THRESHOLD = 0.72
PAST_DAYS, FUTURE_DAYS = 120, 200


class IcsError(Exception):
    pass


def normalize_url(url: str) -> str:
    url = url.strip()
    if url.startswith("webcal://"):
        url = "https://" + url[len("webcal://"):]
    if not re.match(r"^https?://", url):
        raise IcsError("Bitte einen Link beginnend mit webcal:// oder https:// einfügen.")
    return url


def fetch_ics(url: str) -> bytes:
    try:
        r = httpx.get(normalize_url(url), timeout=20, follow_redirects=True,
                      headers={"User-Agent": "Lernzentrum/1.0 (calendar subscription)"})
    except httpx.HTTPError as exc:
        raise IcsError(f"Kalender nicht erreichbar ({exc.__class__.__name__}).") from exc
    if r.status_code != 200:
        raise IcsError(f"Kalender antwortet mit HTTP {r.status_code}. Ist der Link öffentlich/freigegeben?")
    if b"BEGIN:VCALENDAR" not in r.content[:2000]:
        raise IcsError("Unter dem Link liegt kein Kalender (ICS).")
    return r.content


def _naive_local(v) -> datetime:
    if isinstance(v, datetime):
        if v.tzinfo:
            return v.astimezone(TZ).replace(tzinfo=None)
        return v
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day)
    raise ValueError(v)


def parse_events(ics: bytes, start: datetime, end: datetime) -> list[dict]:
    cal = ICal.from_ical(ics)
    out = []
    for comp in recurring_ical_events.of(cal).between(start, end):
        try:
            s = _naive_local(comp.get("DTSTART").dt)
            e_raw = comp.get("DTEND")
            e = _naive_local(e_raw.dt) if e_raw else s + timedelta(minutes=90)
        except (ValueError, AttributeError):
            continue
        out.append({"uid": str(comp.get("UID", ""))[:250] or f"{s.isoformat()}-{comp.get('SUMMARY')}",
                    "start": s, "end": e, "title": str(comp.get("SUMMARY", "Termin"))[:300],
                    "location": str(comp.get("LOCATION", ""))[:300],
                    "description": str(comp.get("DESCRIPTION", ""))[:2000]})
    out.sort(key=lambda x: x["start"])
    return out


def preview(url: str, n: int = 3) -> list[dict]:
    now = datetime.now(TZ).replace(tzinfo=None)
    events = parse_events(fetch_ics(url), now, now + timedelta(days=60))
    return [{"title": e["title"], "start": e["start"].isoformat(), "end": e["end"].isoformat(),
             "location": e["location"]} for e in events[:n]]


def sync_calendar(db: Session, cal: Calendar, ics: bytes | None = None) -> dict:
    now = datetime.now(TZ).replace(tzinfo=None)
    data = ics if ics is not None else fetch_ics(cal.url)
    events = parse_events(data, now - timedelta(days=PAST_DAYS), now + timedelta(days=FUTURE_DAYS))
    modules = list(db.scalars(select(Module).where(Module.user_id == cal.user_id, Module.archived.is_(False))))
    existing = {(e.uid, e.start): e for e in db.scalars(select(Event).where(Event.calendar_id == cal.id))}
    seen = set()
    created = updated = 0
    for ev in events:
        key = (ev["uid"], ev["start"])
        seen.add(key)
        row = existing.get(key)
        if row is None:
            row = Event(user_id=cal.user_id, calendar_id=cal.id, uid=ev["uid"], start=ev["start"],
                        source="moodle" if cal.kind == "moodle" else "ics")
            db.add(row)
            created += 1
        else:
            updated += 1
        row.end, row.title, row.location, row.description = ev["end"], ev["title"], ev["location"], ev["description"]
        if not row.match_confirmed:
            g = match_event_to_module(row.title, row.location, row.description, modules)
            row.module_id = g.value if g.confidence >= MATCH_THRESHOLD else None
            row.match_score = g.confidence
    for key, row in existing.items():
        if key not in seen and row.start >= now - timedelta(days=PAST_DAYS):
            db.delete(row)
    db.flush()
    if cal.kind == "timetable":
        sync_lectures(db, cal.user_id)
    cal.last_sync, cal.last_status = utcnow(), f"ok: {len(events)} Termine"
    db.flush()
    return {"events": len(events), "created": created, "updated": updated}


def sync_lectures(db: Session, user_id: int) -> None:
    """One lecture per matched timetable event (idempotent)."""
    evs = db.scalars(select(Event).where(Event.user_id == user_id, Event.source == "ics")).all()
    lecs = {lec.event_id: lec for lec in db.scalars(select(Lecture).where(Lecture.user_id == user_id,
                                                                          Lecture.event_id.is_not(None)))}
    for ev in evs:
        lec = lecs.get(ev.id)
        if ev.module_id is None:
            if lec is not None:
                db.delete(lec)
            continue
        if lec is None:
            db.add(Lecture(user_id=user_id, module_id=ev.module_id, event_id=ev.id, start=ev.start, end=ev.end,
                           title=ev.title, source="calendar"))
        else:
            lec.module_id, lec.start, lec.end, lec.title = ev.module_id, ev.start, ev.end, ev.title
    db.flush()


def current_lecture(db: Session, user: User, now: datetime | None = None) -> dict | None:
    """Lecture running now (or starting within 15 min / ended within 10 min) – used for one-tap start."""
    now = now or datetime.now(TZ).replace(tzinfo=None)
    lec = db.scalar(select(Lecture).where(Lecture.user_id == user.id, Lecture.start <= now + timedelta(minutes=15),
                                          Lecture.end >= now - timedelta(minutes=10)).order_by(Lecture.start))
    if lec is None:
        return None
    mod = db.get(Module, lec.module_id)
    return {"lecture_id": lec.id, "module_id": lec.module_id, "module": mod.name if mod else "",
            "title": lec.title, "start": lec.start.isoformat(), "end": lec.end.isoformat()}


def suggest_modules(db: Session, user_id: int) -> list[dict]:
    """Auto-detect modules from recurring unmatched event titles (setup wizard step 5)."""
    from collections import Counter

    evs = db.scalars(select(Event).where(Event.user_id == user_id, Event.module_id.is_(None),
                                         Event.source == "ics")).all()
    cleaned = Counter()
    lecturers: dict[str, str] = {}
    for e in evs:
        t = re.sub(r"\s*[\(\[].*?[\)\]]", "", e.title)
        t = re.sub(r"\b(VL|Vorlesung|Ü|Übung|Tutorium|SU|PR)\b[:\s-]*", "", t, flags=re.I).strip(" -:")
        if len(t) >= 4:
            cleaned[t] += 1
            m = re.search(r"(Prof\.?\s*(?:Dr\.?\s*)?[A-ZÄÖÜ][\wäöüß-]+|Dr\.?\s*[A-ZÄÖÜ][\wäöüß-]+)",
                          f"{e.description} {e.location}")
            if m:
                lecturers[t] = m.group(1)
    return [{"name": n, "count": c, "lecturer": lecturers.get(n, "")} for n, c in cleaned.most_common(12) if c >= 2]


@handler("calendar.sync")
def sync_job(db: Session, job) -> None:
    cal = db.get(Calendar, job.payload["calendar_id"])
    if cal is None:
        return
    try:
        job.payload = {**job.payload, "result": sync_calendar(db, cal)}
    except IcsError as exc:
        cal.last_status = f"Fehler: {exc}"
    db.commit()


@periodic("calendar.poll", 30 * 60)
def poll_all() -> None:
    with SessionLocal() as db:
        for cal in db.scalars(select(Calendar)).all():
            if cal.last_sync is None or utcnow() - cal.last_sync > timedelta(minutes=25):
                enqueue(db, "calendar.sync", {"calendar_id": cal.id}, user_id=cal.user_id, label="Kalender-Abgleich")
        db.commit()
