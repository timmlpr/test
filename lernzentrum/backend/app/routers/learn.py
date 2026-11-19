"""Learning center endpoints: flashcards, quiz, mock exams, radar, gaps, contradictions, glossary, statute finder,
case practice, notes enhancer, study plan, statistics, generated items, key moments, numbers."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import statutes as st
from ..db import get_db, utcnow
from ..jobs import enqueue
from ..learn import core
from ..learn.srs import review
from ..models import Document, Flashcard, KeyMoment, LearnItem, MockExam, Module, NumberFact, Recording, \
    StudySession, User
from ..security import current_user
from ..text import LAWS, find_statutes

router = APIRouter(prefix="/api/learn", tags=["learn"])


def _mod(db: Session, mid: int, user: User) -> Module:
    m = db.get(Module, mid)
    if not m or m.user_id != user.id:
        raise HTTPException(404, "Modul nicht gefunden.")
    return m


def card_out(c: Flashcard) -> dict:
    return {"id": c.id, "module_id": c.module_id, "front": c.front, "back": c.back, "source": c.source,
            "due": c.due.isoformat(), "interval_days": c.interval_days, "repetitions": c.repetitions,
            "ease": round(c.ease, 2)}


@router.get("/flashcards")
def flashcards(module_id: int | None = None, due_only: bool = False, user: User = Depends(current_user),
               db: Session = Depends(get_db)) -> list[dict]:
    q = select(Flashcard).where(Flashcard.user_id == user.id)
    if module_id:
        q = q.where(Flashcard.module_id == module_id)
    if due_only:
        q = q.where(Flashcard.due <= utcnow())
    return [card_out(c) for c in db.scalars(q.order_by(Flashcard.due).limit(500))]


class CardIn(BaseModel):
    module_id: int
    front: str
    back: str


@router.post("/flashcards")
def add_card(body: CardIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    _mod(db, body.module_id, user)
    c = Flashcard(user_id=user.id, module_id=body.module_id, front=body.front[:1000], back=body.back[:3000],
                  source={"label": "selbst erstellt"})
    db.add(c)
    db.commit()
    return card_out(c)


class ReviewIn(BaseModel):
    grade: int
    seconds: float = 10


@router.post("/flashcards/{cid}/review")
def review_card(cid: int, body: ReviewIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    c = db.get(Flashcard, cid)
    if not c or c.user_id != user.id:
        raise HTTPException(404)
    review(c, body.grade)
    db.add(StudySession(user_id=user.id, module_id=c.module_id, kind="flashcards", minutes=min(body.seconds, 300) / 60,
                        correct=1 if body.grade >= 3 else 0, total=1, topic=c.front[:200]))
    db.commit()
    return card_out(c)


@router.delete("/flashcards/{cid}")
def delete_card(cid: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    c = db.get(Flashcard, cid)
    if not c or c.user_id != user.id:
        raise HTTPException(404)
    db.delete(c)
    db.commit()
    return {"ok": True}


@router.get("/quiz/{mid}")
def quiz(mid: int, n: int = 8, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    _mod(db, mid, user)
    items = core.quiz_items(db, user, mid, n=n)
    return {"items": items}


class QuizResultIn(BaseModel):
    module_id: int
    correct: int
    total: int
    minutes: float = 5


@router.post("/quiz/result")
def quiz_result(body: QuizResultIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    db.add(StudySession(user_id=user.id, module_id=body.module_id, kind="quiz", minutes=body.minutes,
                        correct=body.correct, total=body.total))
    db.commit()
    return {"ok": True}


def mock_out(e: MockExam, reveal: bool) -> dict:
    items = []
    for it in e.items:
        x = {k: v for k, v in it.items() if reveal or k not in ("answer", "answer_text", "solution")}
        items.append(x)
    return {"id": e.id, "module_id": e.module_id, "title": e.title, "minutes": e.minutes, "items": items,
            "started_at": e.started_at.isoformat() if e.started_at else None,
            "submitted_at": e.submitted_at.isoformat() if e.submitted_at else None, "score": e.score,
            "grade": e.grade, "feedback": e.feedback if reveal else [], "answers": e.answers if reveal else {}}


class MockIn(BaseModel):
    module_id: int
    minutes: int = 30


@router.post("/mock")
def create_mock(body: MockIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    _mod(db, body.module_id, user)
    e = core.build_mock(db, user, body.module_id, body.minutes)
    if not e.items:
        raise HTTPException(422, "Zu wenig Material für eine Probeklausur. Lade Folien hoch oder erzeuge Karteikarten.")
    e.started_at = utcnow()
    db.commit()
    return mock_out(e, False)


@router.get("/mock")
def list_mocks(module_id: int | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(MockExam).where(MockExam.user_id == user.id)
    if module_id:
        q = q.where(MockExam.module_id == module_id)
    return [mock_out(e, e.submitted_at is not None) for e in db.scalars(q.order_by(MockExam.id.desc()).limit(30))]


class SubmitIn(BaseModel):
    answers: dict


@router.post("/mock/{eid}/submit")
def submit_mock(eid: int, body: SubmitIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    e = db.get(MockExam, eid)
    if not e or e.user_id != user.id:
        raise HTTPException(404)
    if e.submitted_at:
        return mock_out(e, True)
    core.submit_mock(db, e, body.answers)
    db.commit()
    return mock_out(e, True)


@router.get("/radar/{mid}")
def radar(mid: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    _mod(db, mid, user)
    return core.exam_radar(db, mid)


@router.get("/gaps/{mid}")
def gaps(mid: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    _mod(db, mid, user)
    return core.gap_finder(db, mid)


@router.get("/contradictions/{mid}")
def contradictions(mid: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    _mod(db, mid, user)
    return core.contradictions(db, user, mid)


@router.get("/glossary")
def glossary(module_id: int | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(LearnItem).where(LearnItem.user_id == user.id, LearnItem.kind == "term")
    if module_id:
        q = q.where(LearnItem.module_id == module_id)
    return [{"id": t.id, "term": t.title, "definition": t.body, "module_id": t.module_id, "source": t.source}
            for t in db.scalars(q.order_by(LearnItem.title))]


@router.post("/glossary/{mid}/build")
def build_glossary(mid: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    _mod(db, mid, user)
    n = core.build_glossary(db, user, mid)
    db.commit()
    return {"found": n}


class TermIn(BaseModel):
    module_id: int | None = None
    term: str
    definition: str


@router.post("/glossary")
def add_term(body: TermIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    core.upsert_term(db, user, body.module_id, body.term.strip()[:200], body.definition[:3000], {"label": "selbst"})
    db.commit()
    return {"ok": True}


class FinderIn(BaseModel):
    question: str
    laws: list[str] | None = None


@router.post("/statutes/find")
def statute_finder(body: FinderIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    direct = []
    for r in find_statutes(body.question):
        if r.law:
            n = st.get_norm(db, r.law, r.norm)
            if n:
                direct.append({**st.as_source(n, r.absatz), "score": 1.0, "text": n.text})
    found = st.find(db, body.question, body.laws)
    db.commit()
    loaded = sorted({row[0] for row in db.execute(select(st.Statute.law).distinct())})
    return {"direct": direct, "results": [{**st.as_source(n), "score": round(s, 2), "text": n.text} for n, s in found],
            "loaded_laws": [LAWS.get(l, l) for l in loaded],
            "hint": None if len(loaded) > 2 else "Lade ganze Gesetze (BGB, HGB, EStG, AO, UStG) für bessere Treffer."}


class LoadLawIn(BaseModel):
    laws: list[str]


@router.post("/statutes/load")
def load_laws(body: LoadLawIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    jobs = []
    for law in body.laws:
        if law.lower() in LAWS:
            j = enqueue(db, "statutes.load", {"law": law.lower()}, user_id=user.id, label=f"Gesetz laden: {LAWS[law.lower()]}")
            jobs.append(j.id)
    db.commit()
    return {"jobs": jobs}


@router.get("/statutes/{law}/{norm}")
def statute(law: str, norm: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    n = st.get_norm(db, law, norm)
    db.commit()
    if not n:
        raise HTTPException(404, "Norm nicht gefunden oder gesetze-im-internet.de nicht erreichbar.")
    return {**st.as_source(n), "text": n.text, "fetched_at": n.fetched_at.isoformat() if n.fetched_at else None}


class CaseIn(BaseModel):
    case: str
    solution: str
    module_id: int | None = None


@router.post("/case")
def case_practice(body: CaseIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    res = core.grade_case(db, user, body.case, body.solution, body.module_id)
    db.commit()
    return res


CASES = [
    {"title": "Kaufpreisanspruch", "module_hint": "Schuld",
     "case": "V verkauft K am 3. März sein gebrauchtes Fahrrad für 300 €. K holt das Rad ab, zahlt aber nicht. "
             "V verlangt Zahlung. Zu Recht?"},
    {"title": "Verjährung", "module_hint": "Schuld",
     "case": "G hat gegen S seit dem 10. Mai 2022 einen fälligen Anspruch auf Rückzahlung eines Darlehens; G kennt "
             "alle Umstände. Am 15. Januar 2026 verklagt G den S. S beruft sich auf Verjährung. Mit Erfolg?"},
    {"title": "Kaufmannseigenschaft", "module_hint": "Buchf",
     "case": "F betreibt einen Onlinehandel mit 12 Angestellten und 4 Mio. € Jahresumsatz, ist aber nicht im "
             "Handelsregister eingetragen. Ist F buchführungspflichtig nach HGB?"},
]


@router.get("/cases")
def cases() -> list[dict]:
    return CASES


@router.get("/notes/{did}/enhance")
def enhance(did: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    d = db.get(Document, did)
    if not d or d.user_id != user.id:
        raise HTTPException(404)
    return {"document_id": d.id, "additions": core.enhance_notes(db, user, d)}


@router.get("/plan")
def plan(days: int = 14, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    return core.study_plan(db, user, days=min(days, 60))


@router.get("/stats")
def stats(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return core.stats(db, user)


@router.get("/items")
def items(kind: str | None = None, module_id: int | None = None, recording_id: int | None = None,
          user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    q = select(LearnItem).where(LearnItem.user_id == user.id, LearnItem.kind != "term")
    if kind:
        q = q.where(LearnItem.kind == kind)
    if module_id:
        q = q.where(LearnItem.module_id == module_id)
    if recording_id:
        q = q.where(LearnItem.recording_id == recording_id)
    return [{"id": i.id, "kind": i.kind, "title": i.title, "body": i.body, "module_id": i.module_id,
             "recording_id": i.recording_id, "source": i.source, "done": i.done, "data": i.data}
            for i in db.scalars(q.order_by(LearnItem.id.desc()).limit(300))]


@router.post("/items/{iid}/done")
def item_done(iid: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    i = db.get(LearnItem, iid)
    if not i or i.user_id != user.id:
        raise HTTPException(404)
    i.done = not i.done
    db.commit()
    return {"done": i.done}


@router.post("/package/{rid}")
def run_package(rid: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    rec = db.get(Recording, rid)
    if not rec or rec.user_id != user.id:
        raise HTTPException(404)
    rec.package_status = "queued"
    enqueue(db, "learn.package", {"recording_id": rid}, user_id=user.id, label=f"Nachbereitung: {rec.title}")
    db.commit()
    return {"ok": True}


@router.get("/moments")
def moments(module_id: int | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(KeyMoment).where(KeyMoment.user_id == user.id)
    if module_id:
        q = q.where(KeyMoment.module_id == module_id)
    return [{"id": m.id, "cue": m.cue, "text": m.text, "at_s": m.at_s, "recording_id": m.recording_id,
             "module_id": m.module_id} for m in db.scalars(q.order_by(KeyMoment.id.desc()).limit(200))]


@router.get("/numbers")
def numbers(module_id: int | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(NumberFact).where(NumberFact.user_id == user.id)
    if module_id:
        q = q.where(NumberFact.module_id == module_id)
    return [{"id": n.id, "kind": n.kind, "value": n.value, "context": n.context, "at_s": n.at_s,
             "recording_id": n.recording_id, "module_id": n.module_id}
            for n in db.scalars(q.order_by(NumberFact.id.desc()).limit(300))]
