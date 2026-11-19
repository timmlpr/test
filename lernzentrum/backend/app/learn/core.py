"""Learning aids. Each generator works without an LLM (heuristic, grounded in the user's material) and uses Gemini
when available for better wording – always with the material as the only source."""
from __future__ import annotations

import random
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import statutes as st
from ..db import utcnow
from ..jobs import handler
from ..live.analyzers import quantities
from ..models import Answer, Chunk, Deadline, Document, Flashcard, KeyMoment, LearnItem, MockExam, Module, \
    Recording, StudySession, TranscriptSegment, User
from ..providers import registry
from ..text import content_overlap, find_statutes, sentences, short, tokens

DEF_PATTERNS = [
    re.compile(r"^(?:Unter (?:einem |einer |dem |der )?)(?P<term>[A-ZÄÖÜ][\wäöüß\- ]{2,40}?) versteht man (?P<def>.+)$"),
    re.compile(r"^(?:Der |Die |Das |Ein |Eine )?(?P<term>[A-ZÄÖÜ][\wäöüß\-]{3,40}(?: [A-ZÄÖÜ]?[\wäöüß\-]{2,30})?) "
               r"(?:ist|sind|bezeichnet|bedeutet|meint) (?P<def>(?:ein|eine|der|die|das|jede|jeder|alle).+)$"),
]


def definitions(text: str) -> list[tuple[str, str, str]]:
    """(term, definition, sentence) from definitional sentences."""
    out = []
    for s in sentences(text):
        s1 = s.strip()
        if len(s1) > 400 or len(s1.split()) < 5:
            continue
        for rx in DEF_PATTERNS:
            m = rx.match(s1)
            if m:
                term = m["term"].strip()
                if term.lower() in ("das", "dies", "es", "sie", "er") or len(term) < 4:
                    continue
                out.append((term, m["def"].rstrip("."), s1))
                break
    return out


def _module_texts(db: Session, module_id: int, kinds: tuple[str, ...] | None = None) -> list[tuple[Chunk, Document]]:
    q = select(Chunk, Document).join(Document, Document.id == Chunk.document_id).where(Chunk.module_id == module_id)
    if kinds:
        q = q.where(Document.kind.in_(kinds))
    return list(db.execute(q).all())


def _src(c: Chunk, d: Document) -> dict:
    loc = f"Folie {c.page}" if d.kind == "slides" and c.page else f"S. {c.page}" if c.page else \
        (f"{int((c.start_s or 0) // 60)}:{int((c.start_s or 0) % 60):02d}" if c.start_s is not None else "")
    return {"document_id": d.id, "title": d.title, "page": c.page, "start_s": c.start_s,
            "recording_id": d.recording_id, "label": f"{d.title} · {loc}".strip(" ·")}


# ---------------------------------------------------------------- post-lecture package
def build_package(db: Session, user: User, rec: Recording) -> dict:
    segs = db.scalars(select(TranscriptSegment).where(TranscriptSegment.recording_id == rec.id)
                      .order_by(TranscriptSegment.start_s)).all()
    text = " ".join(s.text for s in segs)
    mid = rec.module_id
    out = {"summary": 0, "flashcards": 0, "open_questions": 0, "exam_passages": 0, "terms": 0}
    if not text.strip():
        return out
    db.query(LearnItem).filter(LearnItem.recording_id == rec.id).delete()
    llm = registry.generate_json(
        db, user,
        "Erstelle aus diesem Vorlesungstranskript (einzige Quelle!) JSON mit: summary (5-8 Stichpunkte als Liste), "
        "flashcards (bis 10 {front,back}), open_questions (Liste unklarer Punkte), terms (bis 10 {term,definition}). "
        "Nichts erfinden, nur was im Transkript steht.\n\nTranskript:\n" + short(text, 24000),
        tier="lite", max_tokens=3000) if registry.llm_for(db, user) else None
    if isinstance(llm, dict):
        summary_pts = [str(x) for x in llm.get("summary", [])][:8]
        cards = [(c.get("front", ""), c.get("back", "")) for c in llm.get("flashcards", []) if isinstance(c, dict)]
        open_q = [str(x) for x in llm.get("open_questions", [])][:8]
        terms = [(t.get("term", ""), t.get("definition", "")) for t in llm.get("terms", []) if isinstance(t, dict)]
        engine = "gemini"
    else:
        sents = [s for s in sentences(text) if len(s.split()) >= 7]
        freq = Counter(t for t in tokens(text) if len(t) > 4)
        ranked = sorted(sents, key=lambda s: -sum(freq[t] for t in set(tokens(s))) / (len(tokens(s)) + 4))
        order = {s: i for i, s in enumerate(sents)}
        summary_pts = sorted(ranked[:6], key=lambda s: order[s])
        defs = definitions(text)
        cards = [(f"Was versteht man unter „{t}“?", d) for t, d, _ in defs[:10]]
        for ref in find_statutes(text)[:4]:
            if ref.law:
                norm = st.get_norm(db, ref.law, ref.norm, allow_fetch=False)
                if norm and norm.text:
                    cards.append((f"Was regelt {ref.label}?", short(norm.text, 300)))
        open_q = [s for s in sentences(text) if s.endswith("?") and len(s.split()) > 4][:6]
        terms = [(t, d) for t, d, _ in defs[:10]]
        engine = "extraktiv"
    db.add(LearnItem(user_id=user.id, module_id=mid, recording_id=rec.id, kind="summary",
                     title=f"Zusammenfassung {rec.title}", body="\n".join(f"• {p}" for p in summary_pts),
                     data={"engine": engine}, source={"recording_id": rec.id}))
    out["summary"] = 1
    for front, back in cards:
        if front and back and mid:
            db.add(Flashcard(user_id=user.id, module_id=mid, front=front, back=back,
                             source={"recording_id": rec.id, "label": rec.title}))
            out["flashcards"] += 1
    for q in open_q:
        db.add(LearnItem(user_id=user.id, module_id=mid, recording_id=rec.id, kind="open_question", title=q,
                         source={"recording_id": rec.id}))
        out["open_questions"] += 1
    for km in db.scalars(select(KeyMoment).where(KeyMoment.recording_id == rec.id)):
        db.add(LearnItem(user_id=user.id, module_id=mid, recording_id=rec.id, kind="exam_passage", title=km.cue,
                         body=km.text, source={"recording_id": rec.id, "start_s": km.at_s}))
        out["exam_passages"] += 1
    for t, d in terms:
        if t and d:
            upsert_term(db, user, mid, t, d, {"recording_id": rec.id, "label": rec.title})
            out["terms"] += 1
    rec.package_status = "done"
    db.flush()
    return out


@handler("learn.package")
def package_job(db: Session, job) -> None:
    rec = db.get(Recording, job.payload["recording_id"])
    if rec is None:
        return
    user = db.get(User, rec.user_id)
    job.payload = {**job.payload, "result": build_package(db, user, rec)}
    db.commit()


def upsert_term(db: Session, user: User, module_id: int | None, term: str, definition: str, source: dict) -> None:
    existing = db.scalar(select(LearnItem).where(LearnItem.user_id == user.id, LearnItem.kind == "term",
                                                 LearnItem.module_id == module_id, LearnItem.title == term))
    if existing:
        return
    db.add(LearnItem(user_id=user.id, module_id=module_id, kind="term", title=term, body=definition, source=source))


def build_glossary(db: Session, user: User, module_id: int) -> int:
    n = 0
    for c, d in _module_texts(db, module_id):
        for term, definition, _ in definitions(c.text):
            upsert_term(db, user, module_id, term, definition, _src(c, d))
            n += 1
    db.flush()
    return n


# ---------------------------------------------------------------- quiz & mock exam
def quiz_items(db: Session, user: User, module_id: int, n: int = 8, seed: int | None = None) -> list[dict]:
    """Multiple choice from flashcards (distractors = other cards' backs) + cloze from material sentences."""
    rnd = random.Random(seed)
    cards = list(db.scalars(select(Flashcard).where(Flashcard.module_id == module_id)))
    items: list[dict] = []
    rnd.shuffle(cards)
    for c in cards[: n // 2 + 2]:
        others = [o.back for o in cards if o.id != c.id]
        if len(others) < 2:
            break
        opts = rnd.sample(others, min(3, len(others))) + [c.back]
        rnd.shuffle(opts)
        items.append({"type": "mc", "question": c.front, "options": [short(o, 200) for o in opts],
                      "answer": opts.index(c.back), "source": c.source, "points": 2})
    sents = [(s, c, d) for c, d in _module_texts(db, module_id) for s in sentences(c.text)
             if 8 <= len(s.split()) <= 35]
    rnd.shuffle(sents)
    for s, c, d in sents:
        if len(items) >= n:
            break
        cands = [w for w in re.findall(r"\b[A-ZÄÖÜ][a-zäöüß]{6,}\b|\b\d+(?:,\d+)?\s?(?:%|Jahre|Euro|€)", s)]
        if not cands:
            continue
        gap = max(cands, key=len)
        items.append({"type": "cloze", "question": s.replace(gap, "_____", 1), "answer_text": gap,
                      "source": _src(c, d), "points": 1})
    return items[:n]


def grade_item(item: dict, given) -> tuple[float, str]:
    if item["type"] == "mc":
        ok = given is not None and int(given) == item["answer"]
        return (item["points"] if ok else 0.0), ("Richtig." if ok else f"Richtig wäre: {item['options'][item['answer']]}")
    if item["type"] == "cloze":
        ok = isinstance(given, str) and tokens(given) == tokens(item["answer_text"])
        return (item["points"] if ok else 0.0), ("Richtig." if ok else f"Lösung: {item['answer_text']}")
    if item["type"] == "open":
        ov = content_overlap(item.get("solution", ""), given or "")
        pts = round(item["points"] * min(1.0, ov / 0.6), 1)
        return pts, f"Abdeckung der Musterlösung: {int(ov * 100)} %. Muster: {short(item.get('solution', ''), 300)}"
    return 0.0, ""


GRADE_TABLE = [(95, "1,0"), (90, "1,3"), (85, "1,7"), (80, "2,0"), (75, "2,3"), (70, "2,7"), (65, "3,0"),
               (60, "3,3"), (55, "3,7"), (50, "4,0"), (0, "5,0")]


def grade_for(percent: float) -> str:
    return next(g for p, g in GRADE_TABLE if percent >= p)


def build_mock(db: Session, user: User, module_id: int, minutes: int = 30) -> MockExam:
    items = quiz_items(db, user, module_id, n=10)
    for c, d in _module_texts(db, module_id, ("slides", "script"))[:40]:
        refs = [r for r in find_statutes(c.text) if r.law]
        if refs and len([i for i in items if i["type"] == "open"]) < 2:
            items.append({"type": "open", "question": f"Erläutere {refs[0].label} und seine Voraussetzungen.",
                          "solution": c.text, "source": _src(c, d), "points": 5})
    mod = db.get(Module, module_id)
    exam = MockExam(user_id=user.id, module_id=module_id, title=f"Probeklausur {mod.short if mod else ''}",
                    minutes=minutes, items=items)
    db.add(exam)
    db.flush()
    return exam


def submit_mock(db: Session, exam: MockExam, answers: dict) -> MockExam:
    total = sum(i["points"] for i in exam.items) or 1
    got, fb = 0.0, []
    for idx, item in enumerate(exam.items):
        pts, msg = grade_item(item, answers.get(str(idx)))
        got += pts
        fb.append({"points": pts, "max": item["points"], "feedback": msg})
    late = exam.started_at and (utcnow() - exam.started_at).total_seconds() > exam.minutes * 60 + 60
    exam.answers, exam.feedback, exam.submitted_at = answers, fb, utcnow()
    exam.score = round(100 * got / total, 1)
    exam.grade = grade_for(exam.score)
    db.add(StudySession(user_id=exam.user_id, module_id=exam.module_id, kind="mock",
                        minutes=exam.minutes, correct=int(got), total=int(total),
                        topic="Zeit überschritten" if late else ""))
    db.flush()
    return exam


# ---------------------------------------------------------------- radar, gaps, contradictions
def exam_radar(db: Session, module_id: int) -> list[dict]:
    """Topics weighted by keyword cues, repetition across lectures and corrections."""
    weights: Counter = Counter()
    evidence: dict[str, list] = defaultdict(list)
    for km in db.scalars(select(KeyMoment).where(KeyMoment.module_id == module_id)):
        for t in set(tokens(km.text)):
            if len(t) > 4:
                weights[t] += 3
                evidence[t].append({"recording_id": km.recording_id, "start_s": km.at_s, "cue": km.cue})
    per_rec: dict[str, set] = defaultdict(set)
    for seg in db.scalars(select(TranscriptSegment).join(Recording, Recording.id == TranscriptSegment.recording_id)
                          .where(Recording.module_id == module_id)):
        for t in set(tokens(seg.text)):
            if len(t) > 5:
                per_rec[t].add(seg.recording_id)
    for t, recs in per_rec.items():
        if len(recs) >= 2:
            weights[t] += len(recs)
    for ref_text in [s.text for s in db.scalars(select(TranscriptSegment).join(Recording).where(
            Recording.module_id == module_id))]:
        for r in find_statutes(ref_text):
            weights[r.label] += 2
    top = weights.most_common(15)
    mx = top[0][1] if top else 1
    return [{"topic": t, "score": round(w / mx, 2), "evidence": evidence.get(t, [])[:3]} for t, w in top]


def gap_finder(db: Session, module_id: int) -> list[dict]:
    """Slide/script pages whose key terms were never mentioned in any transcript of the module."""
    transcript_toks: set[str] = set()
    for c, _ in _module_texts(db, module_id, ("transcript",)):
        transcript_toks |= set(tokens(c.text))
    if not transcript_toks:
        return []
    gaps = []
    for c, d in _module_texts(db, module_id, ("slides", "script")):
        toks = [t for t in set(tokens(c.text)) if len(t) > 5]
        if len(toks) < 4:
            continue
        covered = len([t for t in toks if t in transcript_toks]) / len(toks)
        if covered < 0.3:
            gaps.append({"source": _src(c, d), "coverage": round(covered, 2), "excerpt": short(c.text, 200),
                         "missing": [t for t in toks if t not in transcript_toks][:6]})
    return sorted(gaps, key=lambda g: g["coverage"])[:20]


def contradictions(db: Session, user: User, module_id: int) -> list[dict]:
    """Numbers that differ between slides/scripts and lecturer statements on the same topic."""
    mats = _module_texts(db, module_id, ("slides", "script", "exercise"))
    trans = _module_texts(db, module_id, ("transcript",))
    out = []
    for c1, d1 in mats:
        q1 = quantities(c1.text)
        if not q1:
            continue
        for s1 in sentences(c1.text):
            qs1 = quantities(s1)
            if not qs1:
                continue
            for c2, d2 in trans:
                for s2 in sentences(c2.text):
                    qs2 = quantities(s2)
                    shared = set(qs1) & set(qs2)
                    if not shared or content_overlap(s1, s2) < 0.4:
                        continue
                    for unit in shared:
                        if not qs1[unit] & qs2[unit]:
                            out.append({"material": {"text": short(s1, 220), **_src(c1, d1)},
                                        "lecturer": {"text": short(s2, 220), **_src(c2, d2)}, "unit": unit})
    seen, uniq = set(), []
    for o in out:
        k = (o["material"]["text"], o["lecturer"]["text"])
        if k not in seen:
            seen.add(k)
            uniq.append(o)
    return uniq[:20]


# ---------------------------------------------------------------- case practice (Gutachtenstil)
GUTACHTEN_STEPS = [
    ("Obersatz", r"\b(könnte|kann)\b.{0,120}\b(haben|zustehen|sein|vorliegen)\b|\bin betracht kommt\b"),
    ("Definition/Voraussetzungen", r"\b(voraussetzung|setzt voraus|ist gegeben, wenn|versteht man|definiert|"
                                   r"tatbestand(?:smerkmal)?)\b"),
    ("Subsumtion", r"\b(hier|vorliegend|im vorliegenden fall|im fall|fraglich ist|vorliegend hat)\b"),
    ("Ergebnis", r"\b(somit|folglich|also|im ergebnis|daher|demnach|ergebnis)\b"),
]


def grade_case(db: Session, user: User, case: str, solution: str, module_id: int | None) -> dict:
    checks = [{"step": name, "ok": bool(re.search(rx, solution, re.I | re.S))} for name, rx in GUTACHTEN_STEPS]
    refs = find_statutes(solution)
    case_refs = find_statutes(case)
    norms = []
    for r in refs[:4]:
        if r.law:
            n = st.get_norm(db, r.law, r.norm, allow_fetch=True)
            norms.append({"label": r.label, "found": bool(n), "excerpt": short(n.text, 300) if n else ""})
    feedback = None
    if registry.llm_for(db, user):
        sources = "\n".join(f"[{n['label']}] {n['excerpt']}" for n in norms if n["found"])
        feedback = registry.generate(
            db, user,
            f"Fall:\n{case}\n\nLösung des Studierenden:\n{solution}\n\nNormtexte (einzige Rechtsquelle):\n{sources}\n\n"
            "Gib Feedback zum Gutachtenstil (Obersatz, Definition, Subsumtion, Ergebnis) und zur Normanwendung. "
            "Maximal 8 kurze Punkte, Du-Form. Wenn Normen fehlen, sage welche Prüfungsschritte fehlen, ohne Normen "
            "zu erfinden.", tier="lite", max_tokens=900)
    score = sum(c["ok"] for c in checks) / len(checks)
    tips = [f"{c['step']} fehlt oder ist nicht erkennbar." for c in checks if not c["ok"]]
    if not refs:
        tips.append("Nenne die Anspruchsgrundlage/Norm mit Paragraph und Gesetz (z. B. § 433 Abs. 2 BGB).")
    if case_refs and not set(r.key for r in case_refs) & set(r.key for r in refs):
        tips.append("Die im Sachverhalt genannten Normen tauchen in deiner Lösung nicht auf.")
    if module_id:
        db.add(StudySession(user_id=user.id, module_id=module_id, kind="case", minutes=15,
                            correct=sum(c["ok"] for c in checks), total=len(checks)))
    return {"checks": checks, "score": round(score, 2), "tips": tips, "norms": norms, "llm_feedback": feedback}


# ---------------------------------------------------------------- notes enhancer
def enhance_notes(db: Session, user: User, doc: Document) -> list[dict]:
    """Transcript passages from the same lecture/day that the handwritten notes do not cover."""
    if not doc.text:
        return []
    note_toks = set(tokens(doc.text))
    q = select(TranscriptSegment).join(Recording, Recording.id == TranscriptSegment.recording_id) \
        .where(Recording.user_id == user.id)
    if doc.lecture_id:
        q = q.where(Recording.lecture_id == doc.lecture_id)
    elif doc.doc_date:
        day = doc.doc_date.replace(hour=0, minute=0, second=0)
        q = q.where(Recording.started_at >= day, Recording.started_at < day + timedelta(days=1))
    elif doc.module_id:
        q = q.where(Recording.module_id == doc.module_id)
    out = []
    for seg in db.scalars(q.order_by(TranscriptSegment.start_s)):
        toks = [t for t in set(tokens(seg.text)) if len(t) > 4]
        if len(toks) < 4:
            continue
        missing = [t for t in toks if t not in note_toks]
        if len(missing) / len(toks) > 0.7 and ("keyword" in (seg.flags or []) or len(toks) > 8):
            out.append({"recording_id": seg.recording_id, "start_s": seg.start_s, "text": seg.text,
                        "important": "keyword" in (seg.flags or [])})
    return out[:25]


# ---------------------------------------------------------------- study plan & stats
def study_plan(db: Session, user: User, days: int = 14, now: datetime | None = None) -> list[dict]:
    now = now or utcnow()
    mods = db.scalars(select(Module).where(Module.user_id == user.id, Module.archived.is_(False))).all()
    tasks: list[dict] = []
    for d in range(days):
        day = (now + timedelta(days=d)).date()
        budget = 90 if day.weekday() < 5 else 150
        weights = []
        for m in mods:
            w = m.ects or 5
            if m.exam_date:
                left = (m.exam_date.date() - day).days
                if left < 0:
                    continue
                w *= 3 if left <= 14 else 1.5 if left <= 42 else 1
            due = db.query(Flashcard).filter(Flashcard.module_id == m.id, Flashcard.due <= datetime.combine(
                day, datetime.max.time())).count()
            weights.append((m, w, due))
        tot = sum(w for _, w, _ in weights) or 1
        for m, w, due in sorted(weights, key=lambda x: -x[1])[:3]:
            mins = int(budget * w / tot // 5 * 5) or 10
            kind = "Karteikarten" if due else "Wiederholen"
            if m.exam_date and (m.exam_date.date() - day).days <= 10:
                kind = "Probeklausur"
            tasks.append({"date": day.isoformat(), "module_id": m.id, "module": m.short, "color": m.color,
                          "task": f"{kind} {m.name}" + (f" ({due} fällige Karten)" if due and kind == "Karteikarten"
                                                        else ""), "minutes": mins})
        for dl in db.scalars(select(Deadline).where(Deadline.user_id == user.id, Deadline.status != "dismissed",
                                                    Deadline.due >= datetime.combine(day, datetime.min.time()),
                                                    Deadline.due < datetime.combine(day, datetime.min.time())
                                                    + timedelta(days=1))):
            tasks.append({"date": day.isoformat(), "module_id": dl.module_id, "module": "", "color": "#B5523B",
                          "task": f"Frist: {dl.title}", "minutes": 0, "deadline": True})
    return tasks


def stats(db: Session, user: User) -> dict:
    sessions = db.scalars(select(StudySession).where(StudySession.user_id == user.id)).all()
    mods = {m.id: m for m in db.scalars(select(Module).where(Module.user_id == user.id))}
    per_mod: dict[int, dict] = defaultdict(lambda: {"minutes": 0.0, "correct": 0, "total": 0})
    per_day: Counter = Counter()
    for s in sessions:
        pm = per_mod[s.module_id or 0]
        pm["minutes"] += s.minutes
        pm["correct"] += s.correct
        pm["total"] += s.total
        per_day[s.created_at.date().isoformat()] += s.minutes
    rec_minutes = defaultdict(float)
    for r in db.scalars(select(Recording).where(Recording.user_id == user.id)):
        rec_minutes[r.module_id or 0] += (r.duration_s or 0) / 60
    modules = []
    for mid, m in mods.items():
        pm = per_mod.get(mid, {"minutes": 0, "correct": 0, "total": 0})
        acc = pm["correct"] / pm["total"] if pm["total"] else None
        modules.append({"module_id": mid, "name": m.name, "short": m.short, "color": m.color,
                        "study_minutes": round(pm["minutes"]), "lecture_minutes": round(rec_minutes[mid]),
                        "accuracy": round(acc, 2) if acc is not None else None})
    answers = db.scalars(select(Answer).where(Answer.user_id == user.id)).all()
    levels = Counter(a.level for a in answers)
    return {"modules": modules, "per_day": [{"date": d, "minutes": round(v)} for d, v in sorted(per_day.items())][-30:],
            "answers": dict(levels), "strengths": [m["short"] for m in modules if (m["accuracy"] or 0) >= 0.75],
            "weaknesses": [m["short"] for m in modules if m["accuracy"] is not None and m["accuracy"] < 0.6]}
