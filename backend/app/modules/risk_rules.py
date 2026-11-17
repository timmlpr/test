"""M-03 risk score: transparent, pure-function rule set (0 = barely exposed, 100 = highly exposed).

Factors (each capped):            cap
  findability  – open search hits   20   (3 points per attributable hit)
  sensitivity  – data types exposed 25   (weights below, per distinct type)
  leaks        – breaches           25   (5 per breach, +5 if passwords leaked)
  recency      – events < 24 months 10   (2 per recent finding)
  visibility   – high-risk web hits 20   (5 per high-risk search hit)
  protection   – security checklist −15  (proportional to completed items)
Traffic light: 0–33 green, 34–66 yellow, 67–100 red.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.core.clock import utcnow

WEIGHTS = {"payment": 8, "id_document": 8, "health": 8, "password": 6, "address": 5, "security_qa": 5, "phone": 4,
           "birthdate": 4, "location": 3, "ip": 2, "name": 1, "email": 1, "username": 1}
CAPS = {"findability": 20, "sensitivity": 25, "leaks": 25, "recency": 10, "visibility": 20, "protection": 15}


@dataclass(frozen=True)
class F:
    """Minimal finding view for scoring."""

    id: str
    module: str  # privacy_scan | breach_check | ...
    risk: str
    data_types: tuple[str, ...] = ()
    when: datetime | None = None
    attributable: bool = True
    title: str = ""


@dataclass
class ScoreResult:
    score: int
    light: str
    factors: dict[str, int]
    explanations: dict[str, str] = field(default_factory=dict)


def light(score: int) -> str:
    return "green" if score <= 33 else "yellow" if score <= 66 else "red"


def compute(findings: list[F], checklist_done: int = 0, checklist_total: int = 0, now: datetime | None = None) -> ScoreResult:
    now = now or utcnow()
    active = [f for f in findings if f.attributable]
    hits = [f for f in active if f.module == "privacy_scan"]
    leaks = [f for f in active if f.module == "breach_check"]
    types = {t for f in active for t in f.data_types}
    factors = {
        "findability": min(CAPS["findability"], 3 * len(hits)),
        "sensitivity": min(CAPS["sensitivity"], sum(WEIGHTS.get(t, 1) for t in types)),
        "leaks": min(CAPS["leaks"], 5 * len(leaks) + (5 if any("password" in f.data_types for f in leaks) else 0)),
        "recency": min(CAPS["recency"], 2 * sum(1 for f in active if f.when and f.when > now - timedelta(days=730))),
        "visibility": min(CAPS["visibility"], 5 * sum(1 for f in hits if f.risk == "high")),
        "protection": -round(CAPS["protection"] * (checklist_done / checklist_total)) if checklist_total else 0,
    }
    score = max(0, min(100, sum(factors.values())))
    return ScoreResult(score=score, light=light(score), factors=factors)


def actions_by_impact(findings: list[F], checklist_done: int, checklist_total: int, now: datetime | None = None) -> list[dict]:
    """For each open finding, how many points would the score drop if it were resolved? Sorted desc."""
    base = compute(findings, checklist_done, checklist_total, now).score
    out = []
    for f in findings:
        if not f.attributable:
            continue
        rest = [x for x in findings if x.id != f.id]
        gain = base - compute(rest, checklist_done, checklist_total, now).score
        out.append({"finding_id": f.id, "title": f.title, "module": f.module, "impact": gain, "risk": f.risk})
    if checklist_total and checklist_done < checklist_total:
        gain = base - compute(findings, checklist_done + 1, checklist_total, now).score
        out.append({"finding_id": None, "title": "checklist_next", "module": "security_checklist", "impact": gain, "risk": "low"})
    rank = {"high": 0, "medium": 1, "low": 2}
    out.sort(key=lambda a: (-a["impact"], rank.get(a["risk"], 3)))
    return out
