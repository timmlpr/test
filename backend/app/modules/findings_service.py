"""Shared finding persistence: dedupe by fingerprint, timeline entries, risk snapshots."""
from __future__ import annotations

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.events import timeline
from app.models import ChecklistState, Finding, RiskSnapshot, User, now
from app.modules.risk_rules import F, actions_by_impact, compute

SECURITY_ITEMS_TOTAL = 8


def fingerprint(user_id: str, module: str, source: str, key: str) -> str:
    return hashlib.sha256(f"{user_id}|{module}|{source}|{key}".encode()).hexdigest()


def upsert(db: Session, user: User, *, module: str, source: str, key: str, title: str, url: str | None, data_types: list[str],
           risk: str, details: dict | None = None, occurred_at=None, attributable: bool = True, scan_id: str | None = None,
           identifier_id: str | None = None, is_demo: bool = False) -> tuple[Finding, bool]:
    fp = fingerprint(user.id, module, source, key)
    existing = db.scalar(select(Finding).where(Finding.user_id == user.id, Finding.fingerprint == fp))
    if existing:
        return existing, False
    f = Finding(user_id=user.id, module=module, source=source, title=title, url=url, data_types=sorted(set(data_types)), risk=risk,
                details=json.dumps(details, ensure_ascii=False) if details else None, fingerprint=fp, occurred_at=occurred_at,
                attributable=attributable, scan_id=scan_id, identifier_id=identifier_id, is_demo=is_demo)
    db.add(f)
    db.flush()
    timeline(db, user.id, "finding", title, ref=f.id, risk=risk)
    return f, True


def finding_view(f: Finding) -> dict:
    return {"id": f.id, "module": f.module, "source": f.source, "title": f.title, "url": f.url, "data_types": f.data_types,
            "risk": f.risk, "details": json.loads(f.details) if f.details else None, "found_at": f.found_at,
            "occurred_at": f.occurred_at, "status": f.status, "tags": f.tags or [], "note": f.note,
            "attributable": f.attributable, "is_demo": f.is_demo}


def scoring_inputs(db: Session, user: User) -> tuple[list[F], int, int]:
    rows = db.scalars(select(Finding).where(Finding.user_id == user.id, Finding.status == "open")).all()
    fs = [F(id=r.id, module=r.module, risk=r.risk, data_types=tuple(r.data_types or ()), when=r.occurred_at or r.found_at,
            attributable=r.attributable, title=r.title) for r in rows]
    done = db.scalars(select(ChecklistState).where(ChecklistState.user_id == user.id, ChecklistState.scope == "security",
                                                   ChecklistState.done.is_(True))).all()
    return fs, len(done), SECURITY_ITEMS_TOTAL


def current_risk(db: Session, user: User) -> dict:
    fs, done, total = scoring_inputs(db, user)
    res = compute(fs, done, total)
    return {"score": res.score, "light": res.light, "factors": res.factors,
            "actions": actions_by_impact(fs, done, total)[:10]}


def snapshot(db: Session, user: User) -> dict:
    r = current_risk(db, user)
    last = db.scalar(select(RiskSnapshot).where(RiskSnapshot.user_id == user.id).order_by(RiskSnapshot.created_at.desc()))
    if not last or last.score != r["score"] or (now() - last.created_at).days >= 1:
        db.add(RiskSnapshot(user_id=user.id, score=r["score"], factors=r["factors"]))
    return r
