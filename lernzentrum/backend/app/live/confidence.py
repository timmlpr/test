"""Confidence scoring from retrieval evidence (not from model self-report alone).

p = 100 · (0.30·r + 0.25·c + 0.20·q + 0.10·a + 0.08·s + 0.07·m) − caps
  r  best retrieval score of the cited evidence (0..1)
  c  citation coverage: share of answer sentences whose content overlaps ≥ 35 % with a cited passage
  a  agreement: ≥ 2 independent supporting sources (documents/statutes) → 1, one → 0.5
  s  statute match: a cited statute is one the question/context refers to → 1
  q  question coverage: share of the question's own content terms found in the cited passages
  m  model self-rating (0..1), capped weight; 0.5 when no model was used
Caps: question barely covered ≤ 70, sources contradict each other ≤ 60, answer mostly unsupported ≤ 60,
model says "partial" ≤ 74 / "none" ≤ 40, corrected by the lecturer ≤ 30.
Levels: SICHER ≥ 75, PRÜFEN 45–74, UNSICHER < 45. Without any evidence: ≤ 15 % and "keine Quelle".
"""
from __future__ import annotations

from dataclasses import dataclass

from ..text import content_overlap, sentences, terms

SICHER, PRUEFEN, UNSICHER = "SICHER", "PRÜFEN", "UNSICHER"


@dataclass
class Evidence:
    text: str
    score: float  # retrieval score 0..1 (statutes: 1.0 when explicitly referenced)
    source_key: str  # document id or statute key – used for independence
    is_statute: bool = False
    statute_match: bool = False


@dataclass
class Confidence:
    level: str
    percent: int
    why: str
    factors: dict


def level_for(percent: int) -> str:
    if percent >= 75:
        return SICHER
    if percent >= 45:
        return PRUEFEN
    return UNSICHER


def coverage(answer: str, cited: list[Evidence], threshold: float = 0.35) -> float:
    sents = [s for s in sentences(answer) if len(s.split()) >= 3] or ([answer] if answer.strip() else [])
    if not sents or not cited:
        return 0.0
    supported = 0
    for s in sents:
        if max(content_overlap(s, e.text) for e in cited) >= threshold:
            supported += 1
    return supported / len(sents)


GENERIC = {"eigent", "eigentlich", "genau", "denn", "dann", "frage", "gilt", "gelten", "regel", "wann", "welch", "welche"}


def question_coverage(question: str, cited: list[Evidence]) -> float:
    q = {t for t in terms(question) if t not in GENERIC and len(t) > 2}
    if not q:
        return 0.5
    have: set[str] = set()
    for e in cited:
        have |= set(terms(e.text))
    return len(q & have) / len(q)


def score(answer: str, cited: list[Evidence], *, self_rating: float | None = None, corrected: bool = False,
          support_claim: str | None = None, question: str = "", conflict: bool = False) -> Confidence:
    if not cited or not answer.strip():
        return Confidence(UNSICHER, 10 if answer.strip() else 0, "keine Quelle – nichts Passendes in deinen "
                          "Unterlagen oder Gesetzen gefunden", {"r": 0, "c": 0, "a": 0, "s": 0, "m": 0})
    r = max(e.score for e in cited)
    c = coverage(answer, cited)
    independent = {e.source_key for e in cited if e.score >= 0.3 or e.is_statute}
    a = 1.0 if len(independent) >= 2 else 0.5 if independent else 0.0
    s = 1.0 if any(e.statute_match for e in cited) else 0.0
    m = 0.5 if self_rating is None else max(0.0, min(1.0, self_rating))
    q = question_coverage(question, cited) if question else 0.6
    p = 100 * (0.30 * r + 0.25 * c + 0.20 * q + 0.10 * a + 0.08 * s + 0.07 * m)
    if q < 0.5:
        p = min(p, 70)  # sources do not address what was actually asked
    if support_claim == "none":
        p = min(p, 40)
    elif support_claim == "partial":
        p = min(p, 74)
    if corrected:
        p = min(p, 30)
    if conflict:
        p = min(p, 60)  # sources disagree (e.g. outdated script) → never SICHER
    if c < 0.34:
        p = min(p, 60)  # most of the answer is not backed by the cited passages
    pct = int(round(max(0, min(99, p))))
    lvl = level_for(pct)
    why_bits = []
    if s:
        why_bits.append("Gesetzestext direkt zitiert")
    why_bits.append(f"{int(c * 100)} % der Aussagen durch Quelle gedeckt")
    why_bits.append(f"{len(independent)} unabhängige Quelle{'n' if len(independent) != 1 else ''}")
    if r < 0.35:
        why_bits.append("Treffer nur schwach passend")
    if question and q < 0.5:
        why_bits.append("Quellen decken die Frage nur teilweise ab")
    if conflict:
        why_bits.append("Quellen widersprechen sich – Stand/Fassung prüfen")
    if corrected:
        why_bits.append("vom Dozenten korrigiert")
    return Confidence(lvl, pct, "; ".join(why_bits), {"r": round(r, 2), "c": round(c, 2), "q": round(q, 2), "a": a, "s": s,
                                                     "m": m})
