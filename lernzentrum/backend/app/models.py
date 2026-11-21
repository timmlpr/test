"""SQLAlchemy models. Every user-owned row carries `user_id` so the schema is tenant-ready."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .crypto import EncryptedText
from .db import Base, utcnow


def _id() -> Mapped[int]:
    return mapped_column(Integer, primary_key=True)


def _uid() -> Mapped[int]:
    return mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime, default=utcnow)


# ---------------------------------------------------------------- account
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = _id()
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(120), default="")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    setup_step: Mapped[int] = mapped_column(Integer, default=1)  # 1..6, 7 = done
    setup_skipped: Mapped[list] = mapped_column(JSON, default=list)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    upload_token: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    created_at: Mapped[datetime] = _created()


class Passkey(Base):
    __tablename__ = "passkeys"
    id: Mapped[int] = _id()
    user_id: Mapped[int] = _uid()
    credential_id: Mapped[str] = mapped_column(String(512), unique=True)
    public_key: Mapped[bytes] = mapped_column(LargeBinary)
    sign_count: Mapped[int] = mapped_column(Integer, default=0)
    label: Mapped[str] = mapped_column(String(120), default="Passkey")
    created_at: Mapped[datetime] = _created()


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = _id()
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80))
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _created()


class Secret(Base):
    """Envelope-encrypted third-party credential (Groq key, Gemini key, Moodle token, IMAP password …)."""

    __tablename__ = "secrets"
    __table_args__ = (UniqueConstraint("user_id", "provider"),)
    id: Mapped[int] = _id()
    user_id: Mapped[int] = _uid()
    provider: Mapped[str] = mapped_column(String(40))
    sealed: Mapped[str] = mapped_column(Text)
    hint: Mapped[str] = mapped_column(String(40), default="")
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="untested")  # ok | error | untested
    status_detail: Mapped[str] = mapped_column(Text, default="")
    checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = _created()


# ---------------------------------------------------------------- modules & timetable
class Module(Base):
    __tablename__ = "modules"
    id: Mapped[int] = _id()
    user_id: Mapped[int] = _uid()
    name: Mapped[str] = mapped_column(String(200))
    short: Mapped[str] = mapped_column(String(20))
    color: Mapped[str] = mapped_column(String(9), default="#2F5D8C")
    lecturer: Mapped[str] = mapped_column(String(200), default="")
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    exam_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    exam_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    retention_days: Mapped[int | None] = mapped_column(Integer, nullable=True)  # audio retention
    lecturer_profile: Mapped[dict] = mapped_column(JSON, default=dict)
    moodle_course_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ects: Mapped[int] = mapped_column(Integer, default=5)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _created()


class Calendar(Base):
    __tablename__ = "calendars"
    id: Mapped[int] = _id()
    user_id: Mapped[int] = _uid()
    name: Mapped[str] = mapped_column(String(120), default="Stundenplan")
    url: Mapped[str] = mapped_column(EncryptedText)
    kind: Mapped[str] = mapped_column(String(20), default="timetable")  # timetable | moodle
    last_sync: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_status: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _created()


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (UniqueConstraint("calendar_id", "uid", "start"),)
    id: Mapped[int] = _id()
    user_id: Mapped[int] = _uid()
    calendar_id: Mapped[int | None] = mapped_column(ForeignKey("calendars.id", ondelete="CASCADE"), nullable=True)
    uid: Mapped[str] = mapped_column(String(255))
    start: Mapped[datetime] = mapped_column(DateTime, index=True)
    end: Mapped[datetime] = mapped_column(DateTime)
    title: Mapped[str] = mapped_column(String(300))
    location: Mapped[str] = mapped_column(String(300), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(20), default="ics")  # ics | moodle
    module_id: Mapped[int | None] = mapped_column(ForeignKey("modules.id", ondelete="SET NULL"), nullable=True)
    match_score: Mapped[float] = mapped_column(Float, default=0.0)
    match_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)


class Lecture(Base):
    __tablename__ = "lectures"
    id: Mapped[int] = _id()
    user_id: Mapped[int] = _uid()
    module_id: Mapped[int] = mapped_column(ForeignKey("modules.id", ondelete="CASCADE"), index=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id", ondelete="SET NULL"), nullable=True)
    start: Mapped[datetime] = mapped_column(DateTime)
    end: Mapped[datetime] = mapped_column(DateTime)
    title: Mapped[str] = mapped_column(String(300), default="")
    source: Mapped[str] = mapped_column(String(20), default="calendar")


# ---------------------------------------------------------------- library
class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = _id()
    user_id: Mapped[int] = _uid()
    module_id: Mapped[int | None] = mapped_column(ForeignKey("modules.id", ondelete="SET NULL"), nullable=True, index=True)
    lecture_id: Mapped[int | None] = mapped_column(ForeignKey("lectures.id", ondelete="SET NULL"), nullable=True)
    recording_id: Mapped[int | None] = mapped_column(ForeignKey("recordings.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), default="other")
    title: Mapped[str] = mapped_column(String(300))
    original_name: Mapped[str] = mapped_column(String(300), default="")
    mime: Mapped[str] = mapped_column(String(120), default="")
    size: Mapped[int] = mapped_column(Integer, default=0)
    storage_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sha256: Mapped[str] = mapped_column(String(64), default="", index=True)
    simhash: Mapped[str] = mapped_column(String(32), default="")
    version_of: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    pages: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    doc_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="upload")
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|processing|ready|error
    status_detail: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    review_reason: Mapped[str] = mapped_column(Text, default="")
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = _created()


class Chunk(Base):
    __tablename__ = "chunks"
    id: Mapped[int] = _id()
    user_id: Mapped[int] = _uid()
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    module_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    end_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    text: Mapped[str] = mapped_column(EncryptedText)
    alt_text: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)  # raw STT where corrected (search only)
    local_vec: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    gemini_vec: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)


# ---------------------------------------------------------------- recordings & live
class ConsentLog(Base):
    __tablename__ = "consent_log"
    id: Mapped[int] = _id()
    user_id: Mapped[int] = _uid()
    module_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    statement: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()


class Recording(Base):
    __tablename__ = "recordings"
    id: Mapped[int] = _id()
    user_id: Mapped[int] = _uid()
    module_id: Mapped[int | None] = mapped_column(ForeignKey("modules.id", ondelete="SET NULL"), nullable=True, index=True)
    lecture_id: Mapped[int | None] = mapped_column(ForeignKey("lectures.id", ondelete="SET NULL"), nullable=True)
    consent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(300), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_s: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="live")  # live|processing|done|imported
    source: Mapped[str] = mapped_column(String(20), default="live")  # live | import | demo
    live_answers: Mapped[bool] = mapped_column(Boolean, default=True)
    answer_mode: Mapped[str] = mapped_column(String(10), default="short")
    context: Mapped[dict] = mapped_column(JSON, default=dict)
    package_status: Mapped[str] = mapped_column(String(20), default="none")
    participation: Mapped[list] = mapped_column(JSON, default=list)


class AudioChunk(Base):
    __tablename__ = "audio_chunks"
    __table_args__ = (UniqueConstraint("recording_id", "seq"),)
    id: Mapped[int] = _id()
    user_id: Mapped[int] = _uid()
    recording_id: Mapped[int] = mapped_column(ForeignKey("recordings.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    offset_s: Mapped[float] = mapped_column(Float, default=0.0)
    duration_s: Mapped[float] = mapped_column(Float, default=0.0)
    storage_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    mime: Mapped[str] = mapped_column(String(80), default="audio/webm")
    late: Mapped[bool] = mapped_column(Boolean, default=False)  # uploaded after an offline gap
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|done|error|quota
    created_at: Mapped[datetime] = _created()


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"
    id: Mapped[int] = _id()
    user_id: Mapped[int] = _uid()
    recording_id: Mapped[int] = mapped_column(ForeignKey("recordings.id", ondelete="CASCADE"), index=True)
    start_s: Mapped[float] = mapped_column(Float)
    end_s: Mapped[float] = mapped_column(Float)
    text: Mapped[str] = mapped_column(EncryptedText)
    speaker: Mapped[str] = mapped_column(String(40), default="")
    flags: Mapped[list] = mapped_column(JSON, default=list)  # question, keyword, gap, correction
    original_text: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)  # raw STT, never modified
    edits: Mapped[list] = mapped_column(JSON, default=list)  # Kontext-Korrektur edits (see correction/engine.py)


class LiveEvent(Base):
    """Append-only event log of a recording, streamed to the client via SSE."""

    __tablename__ = "live_events"
    id: Mapped[int] = _id()
    user_id: Mapped[int] = _uid()
    recording_id: Mapped[int] = mapped_column(ForeignKey("recordings.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = _created()


class Answer(Base):
    __tablename__ = "answers"
    id: Mapped[int] = _id()
    user_id: Mapped[int] = _uid()
    module_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    recording_id: Mapped[int | None] = mapped_column(ForeignKey("recordings.id", ondelete="SET NULL"), nullable=True)
    at_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    question: Mapped[str] = mapped_column(EncryptedText)
    resolved_query: Mapped[str] = mapped_column(Text, default="")
    trigger: Mapped[str] = mapped_column(String(20), default="auto")  # auto | manual | ask
    mode: Mapped[str] = mapped_column(String(10), default="short")
    group_id: Mapped[str] = mapped_column(String(40), default="")  # candidate readings share a group
    reading: Mapped[str] = mapped_column(Text, default="")
    reading_prob: Mapped[float] = mapped_column(Float, default=1.0)
    text: Mapped[str] = mapped_column(EncryptedText)
    detail: Mapped[str] = mapped_column(Text, default="")
    level: Mapped[str] = mapped_column(String(10))
    percent: Mapped[int] = mapped_column(Integer)
    why: Mapped[str] = mapped_column(Text, default="")
    sources: Mapped[list] = mapped_column(JSON, default=list)
    engine: Mapped[str] = mapped_column(String(20), default="extractive")
    correction: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    feedback: Mapped[str] = mapped_column(String(20), default="")
    created_at: Mapped[datetime] = _created()


class KeyMoment(Base):
    __tablename__ = "key_moments"
    id: Mapped[int] = _id()
    user_id: Mapped[int] = _uid()
    module_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    recording_id: Mapped[int | None] = mapped_column(ForeignKey("recordings.id", ondelete="CASCADE"), nullable=True)
    at_s: Mapped[float] = mapped_column(Float, default=0.0)
    cue: Mapped[str] = mapped_column(String(60))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()


class NumberFact(Base):
    __tablename__ = "number_facts"
    id: Mapped[int] = _id()
    user_id: Mapped[int] = _uid()
    module_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    recording_id: Mapped[int | None] = mapped_column(ForeignKey("recordings.id", ondelete="CASCADE"), nullable=True)
    at_s: Mapped[float] = mapped_column(Float, default=0.0)
    kind: Mapped[str] = mapped_column(String(20))  # amount|percent|date|deadline|duration|number
    value: Mapped[str] = mapped_column(String(120))
    context: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()


class Statute(Base):
    __tablename__ = "statutes"
    __table_args__ = (UniqueConstraint("law", "norm"),)
    id: Mapped[int] = _id()
    law: Mapped[str] = mapped_column(String(20), index=True)  # bgb, hgb, estg …
    norm: Mapped[str] = mapped_column(String(20))  # "433", "15a", "Art 3"
    title: Mapped[str] = mapped_column(String(400), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(String(300), default="")
    demo: Mapped[bool] = mapped_column(Boolean, default=False)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# ---------------------------------------------------------------- learning
class Flashcard(Base):
    __tablename__ = "flashcards"
    id: Mapped[int] = _id()
    user_id: Mapped[int] = _uid()
    module_id: Mapped[int] = mapped_column(ForeignKey("modules.id", ondelete="CASCADE"), index=True)
    front: Mapped[str] = mapped_column(Text)
    back: Mapped[str] = mapped_column(Text)
    source: Mapped[dict] = mapped_column(JSON, default=dict)
    ease: Mapped[float] = mapped_column(Float, default=2.5)
    interval_days: Mapped[int] = mapped_column(Integer, default=0)
    repetitions: Mapped[int] = mapped_column(Integer, default=0)
    due: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    lapses: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = _created()


class LearnItem(Base):
    """Generic generated learning artefact: summary, open question, exam passage, quiz item, glossary term, gap …"""

    __tablename__ = "learn_items"
    id: Mapped[int] = _id()
    user_id: Mapped[int] = _uid()
    module_id: Mapped[int | None] = mapped_column(ForeignKey("modules.id", ondelete="CASCADE"), nullable=True, index=True)
    recording_id: Mapped[int | None] = mapped_column(ForeignKey("recordings.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    title: Mapped[str] = mapped_column(String(400), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    source: Mapped[dict] = mapped_column(JSON, default=dict)
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _created()


class MockExam(Base):
    __tablename__ = "mock_exams"
    id: Mapped[int] = _id()
    user_id: Mapped[int] = _uid()
    module_id: Mapped[int] = mapped_column(ForeignKey("modules.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    minutes: Mapped[int] = mapped_column(Integer, default=30)
    items: Mapped[list] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    grade: Mapped[str | None] = mapped_column(String(10), nullable=True)
    feedback: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = _created()


class StudySession(Base):
    __tablename__ = "study_sessions"
    id: Mapped[int] = _id()
    user_id: Mapped[int] = _uid()
    module_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(20))  # flashcards|quiz|mock|case|lecture|reading
    minutes: Mapped[float] = mapped_column(Float, default=0)
    correct: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    topic: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = _created()


class Deadline(Base):
    __tablename__ = "deadlines"
    id: Mapped[int] = _id()
    user_id: Mapped[int] = _uid()
    module_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(300))
    due: Mapped[datetime] = mapped_column(DateTime, index=True)
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual|moodle|document|lecture
    source_ref: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(20), default="proposed")  # proposed|accepted|done|dismissed
    created_at: Mapped[datetime] = _created()


class Announcement(Base):
    __tablename__ = "announcements"
    id: Mapped[int] = _id()
    user_id: Mapped[int] = _uid()
    module_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    external_id: Mapped[str] = mapped_column(String(80), default="")
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text, default="")
    author: Mapped[str] = mapped_column(String(200), default="")
    posted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    read: Mapped[bool] = mapped_column(Boolean, default=False)


class InboxItem(Base):
    """Something that arrived in the inbox and was auto-sorted or awaits confirmation."""

    __tablename__ = "inbox_items"
    id: Mapped[int] = _id()
    user_id: Mapped[int] = _uid()
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=True)
    channel: Mapped[str] = mapped_column(String(20))  # upload|share|mail|webdav|moodle|import
    status: Mapped[str] = mapped_column(String(20), default="sorted")  # sorted|review|duplicate|merged|rejected
    suggestion: Mapped[dict] = mapped_column(JSON, default=dict)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _created()


class SyncState(Base):
    __tablename__ = "sync_state"
    __table_args__ = (UniqueConstraint("user_id", "source", "key"),)
    id: Mapped[int] = _id()
    user_id: Mapped[int] = _uid()
    source: Mapped[str] = mapped_column(String(20))  # moodle|webdav|imap
    key: Mapped[str] = mapped_column(String(300))
    fingerprint: Mapped[str] = mapped_column(String(200), default="")
    document_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ---------------------------------------------------------------- infrastructure
class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = _id()
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)  # queued|running|done|error|waiting
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    label: Mapped[str] = mapped_column(String(300), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    run_after: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    batch: Mapped[str] = mapped_column(String(40), default="", index=True)
    created_at: Mapped[datetime] = _created()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class QuotaUsage(Base):
    __tablename__ = "quota_usage"
    __table_args__ = (UniqueConstraint("user_id", "provider", "metric", "window"),)
    id: Mapped[int] = _id()
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    provider: Mapped[str] = mapped_column(String(30))
    metric: Mapped[str] = mapped_column(String(20))  # rpm|rpd|audio_s_hour|audio_s_day
    window: Mapped[str] = mapped_column(String(20))  # e.g. 2026-11-19 or 2026-11-19T10:05
    count: Mapped[float] = mapped_column(Float, default=0)


class CacheEntry(Base):
    __tablename__ = "cache"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()


Index("ix_events_user_start", Event.user_id, Event.start)
