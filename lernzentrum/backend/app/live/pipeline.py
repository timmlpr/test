"""Live pipeline: audio chunk → STT → transcript segments → analyzers → events (SSE).

Runs inside the job worker so uploads return immediately. All events are persisted in `live_events`, which makes
the SSE stream resumable after a reconnect (iPad Wi-Fi in lecture halls is flaky).
"""
from __future__ import annotations

import subprocess
import tempfile
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import statutes as st
from ..db import utcnow
from ..jobs import enqueue, handler
from ..models import Answer, AudioChunk, Document, KeyMoment, LiveEvent, Module, NumberFact, Recording, \
    TranscriptSegment, User
from ..providers import registry
from ..providers.base import MissingKey, ProviderError
from ..retrieval.index import index_document, search
from ..storage import storage
from ..text import find_statutes, short, tokens
from . import analyzers
from .answer import answer as make_answer
from .answer import answer_dict, persist
from .context import LiveContext
from .questions import detect

SUGGEST_EVERY_S = 120


def emit(db: Session, rec: Recording, kind: str, payload: dict) -> None:
    db.add(LiveEvent(user_id=rec.user_id, recording_id=rec.id, kind=kind, payload=payload))


def _module(db: Session, rec: Recording) -> Module | None:
    return db.get(Module, rec.module_id) if rec.module_id else None


def answer_and_emit(db: Session, user: User, rec: Recording, ctx: LiveContext, question: str, at_s: float,
                    trigger: str, mode: str | None = None, original: str | None = None) -> list[Answer]:
    mod = _module(db, rec)
    if mod and mod.exam_mode:
        emit(db, rec, "exam_guard", {"message": "Prüfungsmodus aktiv – keine Live-Antworten."})
        return []
    mode = mode or rec.answer_mode
    results = make_answer(db, user, question, module_id=rec.module_id, ctx=ctx, mode=mode,
                          profile=mod.lecturer_profile if mod else None, original=original)
    rows = persist(db, user, results, question=question, module_id=rec.module_id, recording_id=rec.id, at_s=at_s,
                   trigger=trigger, mode=mode, query=ctx.last_query)
    emit(db, rec, "answer", {"answers": [answer_dict(a) for a in rows], "context": ctx.summary()})
    return rows


def _check_corrections(db: Session, user: User, rec: Recording, text: str, at_s: float) -> None:
    since = utcnow() - timedelta(minutes=6)
    recent = db.scalars(select(Answer).where(Answer.recording_id == rec.id, Answer.created_at >= since,
                                             Answer.correction.is_(None))).all()
    for a in recent:
        if a.at_s is not None and at_s <= (a.at_s or 0) + 1:
            continue
        sig = analyzers.detect_correction(a.text, a.question, text)
        if not sig:
            continue
        corrected = text
        llm_check = registry.generate_json(
            db, user,
            f"Gezeigte Antwort: \"{a.text}\"\nFrage: \"{a.question}\"\nDozent sagt danach: \"{text}\"\n"
            "Widerspricht oder korrigiert die Aussage des Dozenten die Antwort? JSON: "
            "{\"contradicts\":true|false,\"corrected_answer\":\"kurze korrigierte Antwort\"}", cache=False)
        if isinstance(llm_check, dict):
            if not llm_check.get("contradicts"):
                continue
            corrected = str(llm_check.get("corrected_answer") or text)
        a.correction = {"statement": short(sig.statement, 300), "reason": sig.reason, "corrected": corrected,
                        "at_s": at_s, "strength": sig.strength}
        a.level, a.percent = "UNSICHER", min(a.percent, 30)
        mod = _module(db, rec)
        if mod is not None:
            prof = dict(mod.lecturer_profile or {})
            prof["corrections"] = (prof.get("corrections", []) + [
                {"question": a.question, "said": short(sig.statement, 300), "at": utcnow().isoformat()}])[-50:]
            mod.lecturer_profile = prof
        emit(db, rec, "correction", {"answer_id": a.id, "group_id": a.group_id, "correction": a.correction})


def _match_slide(db: Session, user: User, rec: Recording, ctx: LiveContext) -> None:
    if not rec.module_id:
        return
    hits = search(db, user, ctx.transcript(90), module_id=rec.module_id, k=1, kinds=("slides",))
    if not hits or hits[0].score < 0.3:
        return
    h = hits[0]
    cur = ctx.slide or {}
    if cur.get("document_id") == h.document_id and cur.get("page") == h.page:
        return
    ctx.slide = {"document_id": h.document_id, "page": h.page, "title": h.title, "label": h.label,
                 "excerpt": short(h.text, 300), "score": round(h.score, 2)}
    emit(db, rec, "slide", ctx.slide)


def ingest_segments(db: Session, user: User, rec: Recording, segments: list[tuple[float, float, str]],
                    *, late: bool = False) -> None:
    ctx = LiveContext.from_json(rec.context)
    call_names = (user.settings or {}).get("call_names", [])
    to_adjudicate: list[TranscriptSegment] = []
    seen_norms = {s["key"] for s in ctx.statutes}
    for start, end, text in segments:
        text = text.strip()
        if not text:
            continue
        flags: list[str] = ["late"] if late else []
        original = text
        text, edits = correct_segment(db, user, rec, ctx, text)
        if any(e["status"] in ("check", "unclear") for e in edits):
            flags.append("corrected?")
        ctx.add(start, end, text)
        cues = analyzers.keyword_alerts(text)
        if cues:
            flags.append("keyword")
            db.add(KeyMoment(user_id=user.id, module_id=rec.module_id, recording_id=rec.id, at_s=start,
                             cue=cues[0], text=short(text, 400)))
            emit(db, rec, "keyword", {"cue": cues[0], "text": short(text, 200), "at_s": start})
        for n in analyzers.numbers(text):
            db.add(NumberFact(user_id=user.id, module_id=rec.module_id, recording_id=rec.id, at_s=start, kind=n.kind,
                              value=n.value, context=n.context))
            emit(db, rec, "number", {"kind": n.kind, "value": n.value, "context": n.context, "at_s": start})
        for ref in find_statutes(text):
            law = ref.law or ctx.default_law
            key = f"{(law or '?').lower()}:{ref.norm}"
            if not law or key in seen_norms:
                continue
            seen_norms.add(key)
            norm = st.get_norm(db, law, ref.norm, allow_fetch=not late)
            payload = {"key": key, "label": f"§ {ref.norm} {law}", "found": bool(norm and norm.text)}
            if norm:
                payload.update(st.as_source(norm, ref.absatz))
            emit(db, rec, "statute", payload)
        if not late:
            _check_corrections(db, user, rec, text, start)
        questions = detect(text, call_names)
        if questions:
            flags.append("question")
        seg = TranscriptSegment(user_id=user.id, recording_id=rec.id, start_s=start, end_s=end, text=text, flags=flags,
                                original_text=original, edits=edits)
        db.add(seg)
        db.flush()
        if any(e["status"] in ("check", "unclear") for e in edits):
            to_adjudicate.append(seg)
        emit(db, rec, "transcript", {"id": seg.id, "start_s": start, "end_s": end, "text": text, "flags": flags,
                                     "original": original, "edits": edits})
        if not late and rec.live_answers:
            unsure = any(e["status"] in ("check", "unclear") for e in edits)
            for q in questions[:2]:
                answer_and_emit(db, user, rec, ctx, q.text, start, "auto", original=original if unsure else None)
    if not late:
        _match_slide(db, user, rec, ctx)
        last = (rec.context or {}).get("_suggested_at", -1e9)
        if ctx.now - last >= SUGGEST_EVERY_S:
            slide_terms = []
            if ctx.slide:
                slide_terms = [w for w in ctx.slide.get("excerpt", "").split() if len(w) > 7][:6]
            cur = ctx.current_statute()
            sugg = analyzers.suggest_questions(ctx.topic_words(), cur["label"] if cur else None, slide_terms,
                                               ctx.transcript())
            if sugg:
                emit(db, rec, "suggestions", {"questions": sugg})
            rec.context = ctx.to_json() | {"_suggested_at": ctx.now}
        else:
            rec.context = ctx.to_json() | {"_suggested_at": last}
    else:
        rec.context = ctx.to_json() | {"_suggested_at": (rec.context or {}).get("_suggested_at", -1e9)}
    rec.duration_s = max(rec.duration_s or 0, ctx.now)
    from ..correction.service import schedule_llm

    schedule_llm(db, user, rec, [s.id for s in to_adjudicate])
    db.flush()


def _duration(data: bytes, suffix: str) -> float:
    with tempfile.NamedTemporaryFile(suffix=suffix) as f:
        f.write(data)
        f.flush()
        try:
            out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                  f.name], capture_output=True, text=True, timeout=30)
            return float(out.stdout.strip() or 0)
        except (ValueError, OSError, subprocess.TimeoutExpired):
            return 0.0


def _whisper_prompt(db: Session, rec: Recording) -> str:
    """Layer 1: per-module vocabulary bias for Whisper (≤ 600 chars, rotated by the current topic)."""
    from ..correction.lexicon import subject_laws

    mod = _module(db, rec)
    ctx = LiveContext.from_json(rec.context)
    laws = sorted(subject_laws(mod.name if mod else "")) or ["BGB", "HGB", "EStG", "AO", "UStG"]
    parts = [f"Vorlesung {mod.name}, {mod.lecturer}." if mod else "Vorlesung."]
    parts.append("Gesetze: " + ", ".join(laws[:8]) + ".")
    cur = [s["label"] for s in ctx.statutes[-3:]]
    if cur:
        parts.append("Zuletzt: " + ", ".join(cur) + ".")
    owner = db.get(User, rec.user_id)
    own = [t["term"] for t in (owner.settings or {}).get("correction_vocab", [])
           if t.get("module_id") in (None, rec.module_id)]
    vocab = [*own, *ctx.topic_words(), *(mod.lecturer_profile or {}).get("vocab", [])] if mod else own
    if vocab:
        parts.append("Begriffe: " + ", ".join(dict.fromkeys(vocab)) + ".")
    return " ".join(parts)[:600]


def correct_segment(db: Session, user: User, rec: Recording, ctx: LiveContext, text: str) -> tuple[str, list[dict]]:
    """Kontext-Korrektur (layers 2/3/5) with module, lecture context, materials and the user's own rules."""
    from ..correction.engine import Ctx, correct
    from ..correction.lexicon import loaded_sections, subject_laws
    from ..retrieval.index import _load

    settings = (user.settings or {}).get("correction", {})
    if settings.get("enabled") is False:
        return text, []
    mod = _module(db, rec)
    keys: set[str] = set()
    if rec.module_id:
        for st in _load(db, user.id, rec.module_id, None).statutes:
            keys |= st
    rules = {k: v for k, v in (user.settings or {}).get("correction_rules", {}).items()
             if v.get("module_id") in (None, rec.module_id)}
    c = Ctx(module_name=mod.name if mod else "", subject_laws=subject_laws(mod.name if mod else ""),
            recent_laws={s["law"] for s in ctx.statutes if s.get("law")}, material_keys=keys,
            user_rules={k: v["to"] for k, v in rules.items()},
            vocab={t["term"] for t in (user.settings or {}).get("correction_vocab", [])
                   if t.get("module_id") in (None, rec.module_id)},
            weights={k.split("|", 1)[1]: v for k, v in (user.settings or {}).get("correction_weights", {}).items()
                     if k.split("|", 1)[0] == str(rec.module_id)},
            auto=int(settings.get("auto", 90)), mark=int(settings.get("mark", 60)))
    return correct(text, c, sections=lambda law: loaded_sections(db, law))


@handler("live.chunk")
def process_chunk(db: Session, job) -> None:
    ch = db.get(AudioChunk, job.payload["chunk_id"])
    if ch is None or ch.status == "done":
        return
    rec = db.get(Recording, ch.recording_id)
    user = db.get(User, ch.user_id)
    data = storage().get(ch.storage_key)
    suffix = ".mp4" if "mp4" in ch.mime or "aac" in ch.mime else ".webm"
    dur = ch.duration_s or _duration(data, suffix)
    try:
        res = registry.transcribe(db, user, data, f"chunk{ch.seq}{suffix}", ch.mime, duration_hint=dur,
                                  prompt=_whisper_prompt(db, rec))
    except MissingKey as exc:
        ch.status = "error"
        emit(db, rec, "status", {"level": "error", "message": f"Transkription nicht möglich – {exc}. "
                                 "Audio bleibt gespeichert und wird nach Eingabe des Keys verarbeitet.",
                                 "missing": exc.what})
        db.commit()
        return
    except ProviderError as exc:
        if not exc.transient:
            ch.status = "error"
            emit(db, rec, "status", {"level": "error", "message": str(exc)})
            db.commit()
            return
        raise
    segs = [(ch.offset_s + s.start, ch.offset_s + s.end, s.text) for s in res.segments] or \
           ([(ch.offset_s, ch.offset_s + (res.duration or dur), res.text)] if res.text else [])
    ingest_segments(db, user, rec, segs, late=ch.late)
    ch.status, ch.duration_s = "done", res.duration or dur
    if not (user.settings or {}).get("keep_audio", True):
        storage().delete(ch.storage_key)
        ch.storage_key = None
    db.commit()


def finalize_recording(db: Session, rec: Recording) -> Document:
    """Store the full transcript as a searchable document and queue the post-lecture package."""
    segs = db.scalars(select(TranscriptSegment).where(TranscriptSegment.recording_id == rec.id)
                      .order_by(TranscriptSegment.start_s)).all()
    doc = db.scalar(select(Document).where(Document.recording_id == rec.id, Document.kind == "transcript"))
    if doc is None:
        doc = Document(user_id=rec.user_id, module_id=rec.module_id, lecture_id=rec.lecture_id, recording_id=rec.id,
                       kind="transcript", title=f"Transkript {rec.title or ''}".strip(), source=rec.source,
                       doc_date=rec.started_at, status="ready")
        db.add(doc)
        db.flush()
    doc.text = "\n".join(s.text for s in segs)
    doc.module_id = rec.module_id
    index_document(db, doc, segments=[(s.start_s, s.end_s, s.text, s.original_text) for s in segs])
    terms = [t for t in tokens(doc.text or "") if len(t) > 6]
    mod = _module(db, rec)
    if mod is not None and terms:
        from collections import Counter

        prof = dict(mod.lecturer_profile or {})
        cnt = Counter(prof.get("term_counts", {}))
        cnt.update(terms)
        prof["term_counts"] = dict(cnt.most_common(200))
        prof["terms"] = [t for t, _ in cnt.most_common(40)]
        prof["lectures"] = prof.get("lectures", 0) + 1
        mod.lecturer_profile = prof
    rec.status = "done"
    rec.package_status = "queued"
    enqueue(db, "learn.package", {"recording_id": rec.id}, user_id=rec.user_id,
            label=f"Nachbereitung: {rec.title or 'Aufnahme'}")
    db.flush()
    return doc


@handler("live.finalize")
def finalize_job(db: Session, job) -> None:
    rec = db.get(Recording, job.payload["recording_id"])
    pending = db.scalars(select(AudioChunk).where(AudioChunk.recording_id == rec.id,
                                                  AudioChunk.status == "pending")).all()
    if pending and job.attempts < 3:
        raise RuntimeError("Audio wird noch transkribiert – erneuter Versuch")
    finalize_recording(db, rec)
    db.commit()
