"""Classification of incoming material: module, date, document type, canonical name; duplicates/versions;
date-based assignment of recordings to lectures via the timetable.

Everything returns a confidence. Below `REVIEW_THRESHOLD` the item goes to the review list – never guessed silently.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Document, Event, Lecture, Module
from ..text import fold, simhash_distance, tokens

REVIEW_THRESHOLD = 0.6

# patterns are matched against the folded (ä→ae, ß→ss) lowercase name/text; prefixes on purpose (no trailing \b)
KIND_RULES = [
    ("exercise", r"\b(uebung|ubung|aufgabe|tutorium|fallbeispiel|probeklausur|altklausur|klausuraufgabe|loesung|"
                 r"musterloesung|exercise)"),
    ("slides", r"\b(folie|slide|vorlesung|vl ?\d|praesentation|lecture)"),
    ("script", r"\b(skript|script|reader|lehrbuch|handout)"),
    ("notes", r"\b(notiz|mitschrift|goodnotes|notes)"),
]
KIND_LABEL = {"slides": "Folien", "exercise": "Uebung", "script": "Skript", "notes": "Notizen", "transcript": "Transkript",
              "audio": "Aufnahme", "photo": "Foto", "other": "Dokument"}


@dataclass
class Guess:
    value: object
    confidence: float
    reason: str


def guess_kind(filename: str, text: str, mime: str) -> Guess:
    name = re.sub(r"[_\-.]+", " ", fold(filename))
    if mime.startswith("audio/") or re.search(r"\.(m4a|mp3|wav|aac|ogg|opus|caf|flac)$", filename.lower()):
        return Guess("audio", 0.99, "Audiodatei")
    if mime.startswith("image/"):
        return Guess("photo", 0.8, "Bilddatei")
    for kind, rx in KIND_RULES:
        if re.search(rx, name):
            return Guess(kind, 0.85, "Dateiname")
    head = fold(text[:3000])
    for kind, rx in KIND_RULES:
        if re.search(rx, head):
            return Guess(kind, 0.65, "Inhalt")
    if filename.lower().endswith(".pptx"):
        return Guess("slides", 0.75, "PowerPoint")
    # slide decks: many short pages
    return Guess("other", 0.4, "unklar")


def guess_module(db: Session, user_id: int, filename: str, text: str, hint_module_id: int | None = None) -> Guess:
    if hint_module_id:
        return Guess(hint_module_id, 1.0, "vom Nutzer gewählt")
    mods = db.scalars(select(Module).where(Module.user_id == user_id, Module.archived.is_(False))).all()
    if not mods:
        return Guess(None, 0.0, "keine Module angelegt")
    name, body = re.sub(r"[_\-.]+", " ", fold(filename)), fold(text[:6000])
    best, best_s, reason = None, 0.0, ""
    for m in mods:
        names = [m.name, m.short, *m.aliases]
        s_name = max((fuzz.partial_ratio(fold(n), name) / 100 for n in names if len(n) >= 3), default=0)
        s_short = 1.0 if re.search(rf"\b{re.escape(fold(m.short))}\b", name) and len(m.short) >= 2 else 0
        s_body = max((min(1.0, body.count(fold(n)) / 3) for n in names if len(n) >= 4), default=0)
        prof_terms = (m.lecturer_profile or {}).get("terms", [])[:30]
        body_toks = set(tokens(text[:6000]))
        s_terms = len(body_toks & set(prof_terms)) / max(1, min(len(prof_terms), 15)) if prof_terms else 0
        lect = fold(m.lecturer.split()[-1]) if m.lecturer else ""
        s_lect = 0.3 if lect and len(lect) > 3 and lect in body else 0
        s = max(s_short, s_name * 0.9 if s_name > 0.8 else s_name * 0.5, 0.75 * s_body + 0.25 * s_terms + s_lect,
                0.8 * min(1.0, s_terms + s_lect))
        if s > best_s:
            best, best_s = m, s
            reason = "Kürzel im Dateinamen" if s == s_short else "Name im Dateinamen" if s_name > 0.8 else "Inhalt"
    return Guess(best.id if best else None, round(min(best_s, 0.99), 2), reason)


DATE_PATTERNS = [
    (re.compile(r"(20\d{2})[-_.]?(\d{2})[-_.]?(\d{2})[ _T-]?(\d{2})?[:._-]?(\d{2})?[:._-]?(\d{2})?"), "ymd"),
    (re.compile(r"(\d{1,2})\.(\d{1,2})\.(20\d{2}|\d{2})"), "dmy"),
]


def date_from_filename(filename: str) -> datetime | None:
    for rx, kind in DATE_PATTERNS:
        m = rx.search(filename)
        if not m:
            continue
        try:
            if kind == "ymd":
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                h, mi, s = (int(m.group(i) or 0) for i in (4, 5, 6))
                if h > 23 or mi > 59 or s > 59:
                    h = mi = s = 0
                return datetime(y, mo, d, h, mi, s)
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return datetime(y + 2000 if y < 100 else y, mo, d)
        except ValueError:
            continue
    return None


def date_from_text(text: str) -> datetime | None:
    m = re.search(r"\b(\d{1,2})\.(\d{1,2})\.(20\d{2})\b", text[:2000])
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


def canonical_name(module_short: str | None, when: datetime | None, kind: str, ext: str, title_hint: str = "") -> str:
    parts = [re.sub(r"[^A-Za-z0-9ÄÖÜäöüß]", "", module_short or "Allgemein") or "Allgemein"]
    parts.append((when or datetime.now()).strftime("%Y-%m-%d"))
    parts.append(KIND_LABEL.get(kind, "Dokument"))
    if title_hint:
        slug = re.sub(r"[^A-Za-z0-9ÄÖÜäöüß]+", "-", title_hint).strip("-")[:30]
        if slug:
            parts.append(slug)
    return "_".join(parts) + (ext if ext.startswith(".") else f".{ext}" if ext else "")


@dataclass
class DupResult:
    status: str  # new | duplicate | version
    of_id: int | None
    reason: str


def find_duplicate(db: Session, user_id: int, sha: str, simh: str, title: str, module_id: int | None,
                   exclude_id: int | None = None) -> DupResult:
    # only compare with documents that arrived earlier (lower id) – the first copy wins
    earlier = Document.id < exclude_id if exclude_id else Document.id > 0
    exact = db.scalar(select(Document).where(Document.user_id == user_id, Document.sha256 == sha, earlier,
                                             Document.status != "duplicate"))
    if exact:
        return DupResult("duplicate", exact.id, f"identisch mit „{exact.title}“")
    if not simh or simh == "0000000000000000":
        return DupResult("new", None, "")
    cands = db.scalars(select(Document).where(Document.user_id == user_id, Document.simhash != "", earlier,
                                              Document.status.not_in(["duplicate", "superseded"]))).all()
    best, best_d = None, 64
    for c in cands:
        d = simhash_distance(simh, c.simhash)
        if d < best_d:
            best, best_d = c, d
    if best is not None and best_d <= 3:
        return DupResult("duplicate", best.id, f"inhaltsgleich mit „{best.title}“")
    if best is not None and best_d <= 12 and (module_id is None or best.module_id == module_id) and \
            fuzz.token_set_ratio(fold(title), fold(best.title)) >= 60:
        return DupResult("version", best.id, f"neue Version von „{best.title}“")
    return DupResult("new", None, "")


# ---------------------------------------------------------------- timetable matching
def match_event_to_module(title: str, location: str, description: str, modules: list[Module]) -> Guess:
    if not modules:
        return Guess(None, 0.0, "keine Module")
    t = fold(f"{title} {description[:300]}")
    best, best_s = None, 0.0
    for m in modules:
        names = [m.name, *m.aliases]
        s = max(fuzz.token_set_ratio(fold(n), fold(title)) / 100 for n in names)
        s = max(s, max((fuzz.partial_ratio(fold(n), t) / 100 for n in names if len(n) >= 6), default=0) * 0.95)
        if m.short and re.search(rf"\b{re.escape(fold(m.short))}\b", t):
            s = max(s, 0.9)
        if m.lecturer:
            last = fold(m.lecturer.split()[-1])
            if len(last) > 3 and last in fold(f"{title} {description} {location}"):
                s = min(1.0, s + 0.15)
        if s > best_s:
            best, best_s = m, s
    return Guess(best.id if best else None, round(best_s, 2), "Titel/Dozent")


@dataclass
class LectureMatch:
    lecture_id: int | None
    module_id: int | None
    confidence: float
    reason: str


def assign_by_time(db: Session, user_id: int, when: datetime | None, duration_s: float = 0) -> LectureMatch:
    """Assign a recording to a lecture by timestamp (timetable events, ±20 min tolerance, overlap aware)."""
    if when is None:
        return LectureMatch(None, None, 0.0, "kein Aufnahmedatum")
    end = when + timedelta(seconds=max(duration_s, 60))
    window_lo, window_hi = when - timedelta(hours=3), end + timedelta(hours=3)
    lectures = db.scalars(select(Lecture).where(Lecture.user_id == user_id, Lecture.start >= window_lo,
                                                Lecture.start <= window_hi)).all()
    best, best_s, reason = None, 0.0, ""
    for lec in lectures:
        overlap = (min(end, lec.end) - max(when, lec.start)).total_seconds()
        if overlap > 0:
            s = 0.75 + 0.24 * min(1.0, overlap / max(60.0, min(duration_s or 60, (lec.end - lec.start).total_seconds())))
            r = "Aufnahmezeit fällt in die Vorlesung"
        else:
            gap = min(abs((when - lec.end).total_seconds()), abs((lec.start - end).total_seconds()))
            if gap > 20 * 60:
                continue
            s = 0.62 - 0.3 * gap / 1200
            r = f"Aufnahme {int(gap // 60)} min neben der Vorlesung"
        if s > best_s:
            best, best_s, reason = lec, s, r
    if best is None:
        ev = db.scalar(select(Event).where(Event.user_id == user_id, Event.start <= end, Event.end >= when,
                                           Event.module_id.is_not(None)))
        if ev:
            return LectureMatch(None, ev.module_id, 0.55, "Termin im Kalender, aber keine Vorlesung angelegt")
        return LectureMatch(None, None, 0.0, "kein passender Termin im Stundenplan")
    return LectureMatch(best.id, best.module_id, round(best_s, 2), reason)
