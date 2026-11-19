"""Unit tests: ICS parsing/matching, timetable-based date assignment, dedup/versioning, classification, quota."""
from datetime import datetime, timedelta

import pytest

from app.calendar_sync import current_lecture, parse_events, suggest_modules, sync_calendar
from app.db import SessionLocal
from app.ingest.classify import (assign_by_time, canonical_name, date_from_filename, find_duplicate, guess_kind,
                                 guess_module, match_event_to_module)
from app.ingest.pipeline import extract_deadlines
from app.models import Calendar, Document, Lecture, Module, User
from app.quota import QuotaExceeded, acquire, snapshot

ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//THM//Stundenplan//DE
BEGIN:VEVENT
UID:ssr-1@thm
DTSTART;TZID=Europe/Berlin:20261102T081500
DTEND;TZID=Europe/Berlin:20261102T094500
RRULE:FREQ=WEEKLY;COUNT=12
SUMMARY:Grundlagen im Schuld- und Sachenrecht (VL)
LOCATION:A10.1.01
DESCRIPTION:Prof. Dr. Weber
END:VEVENT
BEGIN:VEVENT
UID:bf-1@thm
DTSTART;TZID=Europe/Berlin:20261103T100000
DTEND;TZID=Europe/Berlin:20261103T113000
RRULE:FREQ=WEEKLY;COUNT=12
SUMMARY:VL Buchführung
LOCATION:A12.0.04
DESCRIPTION:Prof. Dr. Schäfer
END:VEVENT
BEGIN:VEVENT
UID:sport@thm
DTSTART;TZID=Europe/Berlin:20261104T180000
DTEND;TZID=Europe/Berlin:20261104T190000
RRULE:FREQ=WEEKLY;COUNT=4
SUMMARY:Hochschulsport Volleyball
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n").encode()


@pytest.fixture
def db_user():
    db = SessionLocal()
    u = User(email="u@example.com", password_hash="x", settings={})
    db.add(u)
    db.flush()
    mods = [Module(user_id=u.id, name="Grundlagen im Schuld- und Sachenrecht", short="SSR", lecturer="Prof. Dr. Weber",
                   aliases=[]),
            Module(user_id=u.id, name="Buchführung", short="BF", lecturer="Prof. Dr. Schäfer", aliases=[])]
    db.add_all(mods)
    db.flush()
    yield db, u, mods
    db.close()


def test_parse_ics_expands_rrule():
    evs = parse_events(ICS, datetime(2026, 11, 1), datetime(2026, 12, 1))
    ssr = [e for e in evs if "Sachenrecht" in e["title"]]
    assert len(ssr) == 5 and ssr[0]["start"] == datetime(2026, 11, 2, 8, 15)


def test_event_matching(db_user):
    _, _, mods = db_user
    assert match_event_to_module("VL Buchführung", "A12", "", mods).value == mods[1].id
    g = match_event_to_module("Grundlagen im Schuld- und Sachenrecht (VL)", "", "Prof. Dr. Weber", mods)
    assert g.value == mods[0].id and g.confidence >= 0.9
    assert match_event_to_module("Hochschulsport Volleyball", "", "", mods).confidence < 0.72


def test_sync_creates_lectures_and_current(db_user):
    db, u, mods = db_user
    cal = Calendar(user_id=u.id, url="https://example.com/x.ics")
    db.add(cal)
    db.flush()
    sync_calendar(db, cal, ics=ICS)
    lecs = db.query(Lecture).filter(Lecture.user_id == u.id).all()
    assert lecs and {lec.module_id for lec in lecs} == {mods[0].id, mods[1].id}
    first = min(lecs, key=lambda x: x.start)
    cur = current_lecture(db, u, first.start + timedelta(minutes=30))
    assert cur and cur["module_id"] == first.module_id
    assert current_lecture(db, u, first.start - timedelta(hours=5)) is None
    # unmatched recurring events are suggested as modules
    assert any("Volleyball" in s["name"] for s in suggest_modules(db, u.id))
    # idempotent resync
    n = len(lecs)
    sync_calendar(db, cal, ics=ICS)
    assert db.query(Lecture).filter(Lecture.user_id == u.id).count() == n


def test_assign_recording_by_time(db_user):
    db, u, mods = db_user
    start = datetime(2026, 11, 2, 8, 15)
    db.add(Lecture(user_id=u.id, module_id=mods[0].id, start=start, end=start + timedelta(minutes=90)))
    db.flush()
    inside = assign_by_time(db, u.id, start + timedelta(minutes=3), 85 * 60)
    assert inside.module_id == mods[0].id and inside.confidence >= 0.75
    near = assign_by_time(db, u.id, start - timedelta(minutes=10), 5 * 60)
    assert near.module_id == mods[0].id and 0.3 < near.confidence < 0.75  # → review list
    none = assign_by_time(db, u.id, start + timedelta(days=2), 600)
    assert none.module_id is None and none.confidence == 0
    assert assign_by_time(db, u.id, None).confidence == 0


def test_dates_from_filenames():
    assert date_from_filename("20261102 081732.m4a") == datetime(2026, 11, 2, 8, 17, 32)
    assert date_from_filename("Aufnahme_2026-11-03.m4a") == datetime(2026, 11, 3)
    assert date_from_filename("BWL 12.11.2026 Folien.pdf") == datetime(2026, 11, 12)
    assert date_from_filename("Neue Aufnahme 12.m4a") is None


def test_dedupe_and_versions(db_user):
    db, u, mods = db_user
    from app.seed import SLIDES

    text = " ".join(SLIDES["SSR"][1])
    from app.text import simhash

    d = Document(user_id=u.id, module_id=mods[0].id, title="SSR_Folien_Kapitel3.pdf", sha256="abc",
                 simhash=simhash(text))
    db.add(d)
    db.flush()
    assert find_duplicate(db, u.id, "abc", "", "x", None).status == "duplicate"
    assert find_duplicate(db, u.id, "zzz", simhash(text), "Kopie.pdf", None).status == "duplicate"
    v2 = text.replace("Gutachtenstil", "Gutachtenstil (überarbeitet)") + " Neu: Beim Versendungskauf gilt § 447 BGB."
    res = find_duplicate(db, u.id, "yyy", simhash(v2), "SSR_Folien_Kapitel3_v2.pdf", mods[0].id)
    assert res.status in ("version", "duplicate")
    assert find_duplicate(db, u.id, "qqq", simhash("Völlig anderer Text über Bilanzen und Konten. " * 8), "a",
                          None).status == "new"


def test_classification(db_user):
    db, u, mods = db_user
    assert guess_kind("BF_Folien_VL3.pdf", "", "application/pdf").value == "slides"
    assert guess_kind("Übungsblatt 2.pdf", "", "application/pdf").value == "exercise"
    assert guess_kind("memo.m4a", "", "audio/mp4").value == "audio"
    g = guess_module(db, u.id, "BF_Uebung.pdf", "")
    assert g.value == mods[1].id and g.confidence >= 0.6
    weak = guess_module(db, u.id, "Scan_0042.pdf", "Notizen ohne Bezug")
    assert weak.confidence < 0.6
    assert canonical_name("BWL", datetime(2026, 11, 12), "slides", ".pdf") == "BWL_2026-11-12_Folien.pdf"


def test_deadline_extraction():
    found = extract_deadlines("Die Abgabe der Hausarbeit ist bis zum 15.01.2027, 12:00 Uhr möglich.")
    assert found and found[0][1] == datetime(2027, 1, 15, 12, 0)


def test_quota_manager_limits_and_snapshot(db_user):
    db, u, _ = db_user
    u.settings = {"quotas": {"gemini_flash": {"rpm": 3, "rpd": 100}}}
    now = datetime(2026, 11, 19, 10, 0, 5)
    acquire(db, u, "gemini_flash", now=now)
    acquire(db, u, "gemini_flash", now=now)
    with pytest.raises(QuotaExceeded) as exc:
        acquire(db, u, "gemini_flash", now=now)  # 3 * 0.95 safety margin → third call blocked
    assert exc.value.metric == "rpm" and exc.value.retry_after_s <= 60
    acquire(db, u, "gemini_flash", now=now + timedelta(minutes=1))  # new minute window
    # audio seconds budget
    u.settings = {"quotas": {"groq_stt": {"audio_s_hour": 100}}}
    with pytest.raises(QuotaExceeded):
        acquire(db, u, "groq_stt", audio_s=200, now=now)
    snap = snapshot(db, u, now)
    assert any(s["provider"] == "gemini_flash" and s["metric"] == "rpd" and s["used"] == 3 for s in snap)
