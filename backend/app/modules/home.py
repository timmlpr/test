"""M-03 risk endpoints and the home screen (score + traffic light + exactly one 'next step')."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import current_user
from app.db import get_db
from app.models import (
    DeletionRequest,
    Finding,
    Identifier,
    RiskSnapshot,
    Scan,
    User,
    now,
)
from app.modules.findings_service import current_risk, finding_view
from app.modules.risk_rules import CAPS, WEIGHTS

router = APIRouter(tags=["risk"])


@router.get("/risk")
def risk(user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = current_risk(db, user)
    return {**r, "caps": CAPS, "weights": WEIGHTS}


@router.get("/risk/history")
def risk_history(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(RiskSnapshot).where(RiskSnapshot.user_id == user.id).order_by(RiskSnapshot.created_at)).all()
    return [{"at": r.created_at, "score": r.score, "factors": r.factors} for r in rows[-180:]]


def next_step(db: Session, user: User, risk: dict) -> dict:
    """Pick the single most effective action. Returns a stable key + link; text is i18n on the client."""
    idents = db.scalars(select(Identifier).where(Identifier.user_id == user.id)).all()
    if not user.email_verified:
        return {"key": "verify_email", "href": "/app/profile"}
    if not any(i.verified_at for i in idents) or not any(i.kind == "name" for i in idents):
        return {"key": "add_identifier", "href": "/app/onboarding"}
    if not db.scalar(select(Scan).where(Scan.user_id == user.id)):
        return {"key": "first_scan", "href": "/app/scan"}
    overdue = db.scalar(select(DeletionRequest).where(DeletionRequest.user_id == user.id, DeletionRequest.status == "sent",
                                                      DeletionRequest.due_at < now()))
    if overdue:
        return {"key": "follow_up_request", "href": f"/app/requests?id={overdue.id}"}
    for a in risk["actions"]:
        if a["impact"] <= 0:
            continue
        if a["module"] == "security_checklist":
            return {"key": "checklist", "href": "/app/checklist", "impact": a["impact"]}
        f = db.get(Finding, a["finding_id"])
        if f and "password" in (f.data_types or []):
            return {"key": "change_password", "href": f"/app/breaches#{f.id}", "finding": f.title, "impact": a["impact"]}
        if f:
            return {"key": "request_deletion", "href": f"/app/requests/new?finding={f.id}", "finding": f.title, "impact": a["impact"]}
    return {"key": "all_good", "href": "/app/monitor"}


@router.get("/home")
def home(user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = current_risk(db, user)
    week = now() - timedelta(days=7)
    new = db.scalars(select(Finding).where(Finding.user_id == user.id, Finding.status == "open", Finding.found_at >= week)
                     .order_by(Finding.found_at.desc()).limit(5)).all()
    reqs = db.scalars(select(DeletionRequest).where(DeletionRequest.user_id == user.id, DeletionRequest.status.in_(["open", "sent"]))
                      .order_by(DeletionRequest.due_at)).all()
    idents = db.scalars(select(Identifier).where(Identifier.user_id == user.id)).all()
    counts = {"open": 0, "high": 0}
    for f in db.scalars(select(Finding).where(Finding.user_id == user.id, Finding.status == "open")):
        counts["open"] += 1
        counts["high"] += f.risk == "high"
    return {
        "risk": {k: r[k] for k in ("score", "light", "factors")},
        "next_step": next_step(db, user, r),
        "new_findings": [finding_view(f) for f in new],
        "deadlines": [{"id": q.id, "recipient": q.recipient, "kind": q.kind, "status": q.status, "due_at": q.due_at,
                       "overdue": bool(q.due_at and q.due_at < now())} for q in reqs[:5]],
        "counts": counts,
        "onboarding": {"identifiers": len(idents), "verified": sum(1 for i in idents if i.verified_at),
                       "scanned": db.scalar(select(Scan.id).where(Scan.user_id == user.id).limit(1)) is not None},
    }
