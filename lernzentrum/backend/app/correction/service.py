"""Kontext-Korrektur – DB side: LLM adjudicator (layer 4), batch re-correction job, settings/vocabulary/rules API."""
from __future__ import annotations

import difflib

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..jobs import enqueue, handler
from ..models import Document, LiveEvent, Module, Recording, TranscriptSegment, User
from ..providers import registry
from ..quota import QuotaExceeded
from ..security import current_user
from .engine import CORE, apply_edits

DEFAULTS = {"enabled": True, "mode": "balanced", "auto": 90, "mark": 60, "llm": True, "max_edit_ratio": 0.2}
MODES = {"conservative": (95, 75), "balanced": (90, 60), "aggressive": (85, 50)}


def settings_of(user: User) -> dict:
    return {**DEFAULTS, **(user.settings or {}).get("correction", {})}


def _status(conf: int, s: dict) -> str:
    return "applied" if conf >= s["auto"] else "check" if conf >= s["mark"] else "unclear"


def needs_llm(edits: list[dict]) -> bool:
    return any(e["status"] in ("check", "unclear") and e.get("candidates") for e in edits) or \
        any(e["status"] == "check" for e in edits)


# ---------------------------------------------------------------- layer 4: Gemini adjudicator
def validate_llm(original: str, edits: list[dict], answer: dict, max_ratio: float) -> dict[str, tuple[str, float]]:
    """Accept only replacements of known correction candidates; reject anything that paraphrases."""
    allowed: dict[str, set[str]] = {}
    for e in edits:
        if e["status"] in ("check", "unclear"):
            allowed.setdefault(e["from"], set()).update(
                {c["to"] for c in e.get("candidates") or []} | ({e["to"]} if e.get("to") else set()))
    text = str(answer.get("corrected_text", ""))
    sm = difflib.SequenceMatcher(None, original, text)
    changed = sum(max(i2 - i1, j2 - j1) for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal")
    budget = sum(len(f) + 4 for f in allowed) + max_ratio * len(original)  # candidate spans + small slack
    if not text or changed > budget:
        return {}
    out: dict[str, tuple[str, float]] = {}
    conf = float(answer.get("confidence", 0.5) or 0.5)
    for ed in answer.get("edits") or []:
        frm, to = str(ed.get("from", "")), str(ed.get("to", ""))
        if frm in allowed and (to in allowed[frm] or to.lower() in CORE):
            out[frm] = (to, conf if conf <= 1 else conf / 100)
    return out


def adjudicate(db: Session, user: User, seg: TranscriptSegment, context: str, slide: str = "") -> bool:
    s = settings_of(user)
    edits = [dict(e) for e in seg.edits or []]
    open_edits = [e for e in edits if e["status"] in ("check", "unclear")]
    if not open_edits:
        return False
    cand = "\n".join(f"- „{e['from']}“ → Kandidaten: {', '.join(c['to'] for c in e.get('candidates') or []) or e.get('to')}"
                     for e in open_edits)
    prompt = (
        "Du prüfst ein automatisches Vorlesungstranskript (Jura/Steuern/BWL). Ändere NUR die gelisteten Stellen, "
        "und nur zu einem der Kandidaten. Nichts umformulieren, nichts hinzufügen oder weglassen.\n"
        f"Kontext davor: {context[-600:]}\nAktuelle Folie: {slide[:300]}\n"
        f"Segment (Original): {seg.original_text}\nUnsichere Stellen:\n{cand}\n"
        'JSON: {"corrected_text":"…","edits":[{"from":"…","to":"…","reason":"…"}],"confidence":0.0}')
    data = registry.generate_json(db, user, prompt, tier="lite", max_tokens=400)
    if not isinstance(data, dict):
        return False
    picks = validate_llm(seg.original_text or seg.text, edits, data, s["max_edit_ratio"])
    if not picks:
        return False
    for e in edits:
        if e["from"] in picks and e["status"] in ("check", "unclear"):
            to, c = picks[e["from"]]
            e["to"] = to
            e["confidence"] = min(95, max(e["confidence"], round(0.5 * e["confidence"] + 50 * c)))
            e["status"] = _status(e["confidence"], s)
            e["layer"] = "llm"
            e["reason"] += " · von KI im Kontext bestätigt"
    seg.edits = edits
    seg.text = apply_edits(seg.original_text or seg.text, edits)
    return True


@handler("correction.llm")
def llm_job(db: Session, job) -> None:
    user = db.get(User, job.user_id)
    rec = db.get(Recording, job.payload["recording_id"])
    if registry.llm_for(db, user) is None:
        return
    slide = ((rec.context or {}).get("slide") or {}).get("excerpt", "")
    for sid in job.payload["segment_ids"]:
        seg = db.get(TranscriptSegment, sid)
        if seg is None:
            continue
        before = db.scalars(select(TranscriptSegment).where(TranscriptSegment.recording_id == rec.id,
                                                            TranscriptSegment.start_s < seg.start_s)
                            .order_by(TranscriptSegment.start_s.desc()).limit(3)).all()
        try:
            changed = adjudicate(db, user, seg, " ".join(b.text for b in reversed(before)), slide)
        except QuotaExceeded:
            db.add(LiveEvent(user_id=user.id, recording_id=rec.id, kind="status",
                             payload={"level": "info", "message": "Kontext-Korrektur: KI-Kontingent erschöpft – Regeln aktiv."}))
            db.commit()
            return
        if changed:
            db.add(LiveEvent(user_id=user.id, recording_id=rec.id, kind="transcript_update",
                             payload={"id": seg.id, "text": seg.text, "original": seg.original_text, "edits": seg.edits}))
        db.commit()


def schedule_llm(db: Session, user: User, rec: Recording, segment_ids: list[int]) -> None:
    s = settings_of(user)
    if not segment_ids or not s["llm"] or not s["enabled"]:
        return
    if registry.llm_for(db, user) is None:
        if not (rec.context or {}).get("_llm_notice"):
            db.add(LiveEvent(user_id=user.id, recording_id=rec.id, kind="status", payload={
                "level": "info", "message": "Kontext-Korrektur: KI-Prüfung übersprungen (kein Gemini-Key) – Regeln aktiv."}))
            rec.context = {**(rec.context or {}), "_llm_notice": True}
        return
    enqueue(db, "correction.llm", {"recording_id": rec.id, "segment_ids": segment_ids}, user_id=user.id,
            label="Kontext-Korrektur (KI)")


# ---------------------------------------------------------------- batch re-correction
def recorrect_recording(db: Session, user: User, rec: Recording) -> int:
    from ..live.context import LiveContext
    from ..live.pipeline import correct_segment

    ctx = LiveContext()
    segs = db.scalars(select(TranscriptSegment).where(TranscriptSegment.recording_id == rec.id)
                      .order_by(TranscriptSegment.start_s)).all()
    changed = 0
    for seg in segs:
        original = seg.original_text or seg.text
        if seg.original_text is None:
            seg.original_text = original
        text, edits = correct_segment(db, user, rec, ctx, original)
        decided = {(e["start"], e["end"], e["from"]): e for e in seg.edits or []
                   if e["status"] in ("accepted", "undone")}
        for e in edits:  # keep the user's decisions → re-running is idempotent
            old = decided.get((e["start"], e["end"], e["from"]))
            if old:
                e["status"], e["to"] = old["status"], old.get("to")
        text = apply_edits(original, edits)
        if text != seg.text or edits != (seg.edits or []):
            changed += 1
        seg.text, seg.edits = text, edits
        ctx.add(seg.start_s, seg.end_s, text)
    tdoc = db.scalar(select(Document).where(Document.recording_id == rec.id, Document.kind == "transcript"))
    if tdoc is not None:
        from ..retrieval.index import index_document

        tdoc.text = "\n".join(s.text for s in segs)
        index_document(db, tdoc, segments=[(s.start_s, s.end_s, s.text, s.original_text) for s in segs])
    return changed


@handler("correction.recorrect")
def recorrect_job(db: Session, job) -> None:
    user = db.get(User, job.user_id)
    recs = db.scalars(select(Recording).where(Recording.user_id == user.id,
                                              Recording.module_id == job.payload["module_id"])).all()
    total = 0
    for i, rec in enumerate(recs):
        total += recorrect_recording(db, user, rec)
        job.progress = (i + 1) / max(1, len(recs))
        db.commit()
    job.payload = {**job.payload, "changed_segments": total, "recordings": len(recs)}
    db.commit()


# ---------------------------------------------------------------- API
router = APIRouter(prefix="/api/correction", tags=["correction"])


class SettingsIn(BaseModel):
    enabled: bool | None = None
    mode: str | None = None
    auto: int | None = None
    mark: int | None = None
    llm: bool | None = None
    max_edit_ratio: float | None = None


@router.get("/settings")
def get_settings_(user: User = Depends(current_user)) -> dict:
    return settings_of(user)


@router.put("/settings")
def put_settings(body: SettingsIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    s = settings_of(user)
    patch = body.model_dump(exclude_none=True)
    if patch.get("mode") in MODES and "auto" not in patch:
        patch["auto"], patch["mark"] = MODES[patch["mode"]]
    s.update(patch)
    if not (0 <= s["mark"] <= s["auto"] <= 100):
        raise HTTPException(422, "Schwellen: 0 ≤ markieren ≤ automatisch ≤ 100.")
    user.settings = {**(user.settings or {}), "correction": s}
    db.commit()
    return s


class VocabIn(BaseModel):
    term: str
    module_id: int | None = None


@router.get("/vocabulary")
def vocab(user: User = Depends(current_user)) -> list[dict]:
    return (user.settings or {}).get("correction_vocab", [])


@router.post("/vocabulary")
def add_vocab(body: VocabIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    term = body.term.strip()[:80]
    if not term:
        raise HTTPException(422, "Begriff fehlt.")
    items = [v for v in vocab(user) if not (v["term"] == term and v.get("module_id") == body.module_id)]
    items.append({"term": term, "module_id": body.module_id})
    user.settings = {**(user.settings or {}), "correction_vocab": items}
    db.commit()
    return items


@router.delete("/vocabulary")
def del_vocab(term: str, module_id: int | None = None, user: User = Depends(current_user),
              db: Session = Depends(get_db)) -> list[dict]:
    items = [v for v in vocab(user) if not (v["term"] == term and v.get("module_id") == module_id)]
    user.settings = {**(user.settings or {}), "correction_vocab": items}
    db.commit()
    return items


@router.get("/rules")
def rules(user: User = Depends(current_user)) -> list[dict]:
    return [{"from": k, **v} for k, v in (user.settings or {}).get("correction_rules", {}).items()]


@router.delete("/rules/{key}")
def del_rule(key: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    r = dict((user.settings or {}).get("correction_rules", {}))
    r.pop(key, None)
    user.settings = {**(user.settings or {}), "correction_rules": r}
    db.commit()
    return rules(user)


@router.get("/export")
def export(user: User = Depends(current_user)) -> dict:
    s = user.settings or {}
    return {"version": 1, "settings": settings_of(user), "vocabulary": s.get("correction_vocab", []),
            "rules": s.get("correction_rules", {})}


@router.post("/import")
def import_(body: dict, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    try:
        v = [{"term": str(x["term"])[:80], "module_id": x.get("module_id")} for x in body.get("vocabulary", [])]
        r = {str(k)[:80]: {"to": str(x["to"])[:80], "module_id": x.get("module_id")}
             for k, x in (body.get("rules") or {}).items()}
    except (KeyError, TypeError, AttributeError) as exc:
        raise HTTPException(422, "Ungültige Datei.") from exc
    user.settings = {**(user.settings or {}), "correction_vocab": v, "correction_rules": r}
    db.commit()
    return {"vocabulary": len(v), "rules": len(r)}


@router.post("/modules/{mid}/recorrect")
def recorrect(mid: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    m = db.get(Module, mid)
    if not m or m.user_id != user.id:
        raise HTTPException(404)
    job = enqueue(db, "correction.recorrect", {"module_id": mid}, user_id=user.id,
                  label=f"Transkripte neu korrigieren: {m.short}", batch=f"recorrect{mid}")
    db.commit()
    return {"job_id": job.id, "batch": job.batch}

