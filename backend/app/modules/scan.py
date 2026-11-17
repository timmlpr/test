"""M-01 privacy scan + M-02 breach check + M-10 password range proxy + M-20 results database."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters import registry
from app.adapters.base import SourceUnavailable
from app.adapters.demo import Demo
from app.core import ratelimit
from app.core.audit import audit
from app.core.deps import current_user
from app.core.errors import ApiError
from app.core.plans import has_feature
from app.core.usage import consume, remaining
from app.db import get_db
from app.models import Finding, Identifier, Scan, User, now
from app.modules.findings_service import finding_view, snapshot, upsert
from app.settings import get_settings

router = APIRouter(tags=["scan"])
HIGH_TYPES = {"password", "payment", "id_document", "health", "address", "phone", "security_qa"}


def breach_risk(types: list[str]) -> str:
    s = set(types)
    if s & {"password", "payment", "id_document", "health", "security_qa"}:
        return "high"
    if s & {"address", "phone", "birthdate", "location"}:
        return "medium"
    return "low"


def verified_identifiers(db: Session, user: User, ids: list[str] | None, kinds: set[str] | None = None) -> list[Identifier]:
    """H1: scans run ONLY on identifiers that exist, belong to the caller and are verified."""
    q = select(Identifier).where(Identifier.user_id == user.id)
    rows = db.scalars(q).all()
    if ids is not None:
        by_id = {r.id: r for r in rows}
        for i in ids:
            if i not in by_id:
                raise ApiError(403, "identifier_not_owned")
            if not by_id[i].verified_at:
                raise ApiError(403, "identifier_not_verified")
        rows = [by_id[i] for i in ids]
    rows = [r for r in rows if r.verified_at and (kinds is None or r.kind in kinds)]
    return rows


def use_demo(user: User) -> bool:
    return get_settings().demo_mode and user.is_demo


# ------------------------------------------------------------------- M-02 breach check
def run_breach_check(db: Session, user: User, idents: list[Identifier], scan: Scan) -> dict:
    new, errors, sources = 0, [], set()
    for ident in idents:
        if ident.kind != "email":
            continue
        if use_demo(user):
            src, result = "demo", Demo().breaches(ident.value)
        else:
            chain = [registry.get("hibp_email"), registry.get("xposedornot")]
            src, result, errs = registry_first(chain, lambda a, v=ident.value: a.breaches(v))
            errors += errs
            if src is None:
                continue
        sources.add(src)
        for b in result:
            year = b.get("year")
            occurred = datetime(int(year), 1, 1) if year and str(year).isdigit() else None
            _, is_new = upsert(db, user, module="breach_check", source=src, key=f"{ident.id}:{b['name']}",
                               title=f"Datenleck: {b['name']}", url=b.get("reference"), data_types=b.get("data_types", []),
                               risk=breach_risk(b.get("data_types", [])), occurred_at=occurred, scan_id=scan.id,
                               identifier_id=ident.id, is_demo=src == "demo",
                               details={"service": b["name"], "domain": b.get("domain"), "year": year, "description": b.get("description"),
                                        "verified": b.get("verified"), "records": b.get("records"), "email_ref": ident.id,
                                        "actions": breach_actions(b.get("data_types", []))})
            new += int(is_new)
    return {"new": new, "errors": errors, "sources": sorted(sources)}


def registry_first(chain, call):
    from app.adapters.quota import first_available

    return first_available(chain, call)


def breach_actions(types: list[str]) -> list[str]:
    acts = []
    if "password" in types:
        acts.append("change_password_everywhere")
        acts.append("enable_2fa")
    if "payment" in types:
        acts.append("check_bank_statements")
    if "address" in types or "phone" in types:
        acts.append("expect_phishing")
    if "birthdate" in types or "id_document" in types:
        acts.append("watch_identity_theft")
    acts.append("request_deletion")
    return acts


@router.post("/breach/check")
def breach_check(user: User = Depends(current_user), db: Session = Depends(get_db)):
    ratelimit.hit(f"breach:{user.id}", 5, 60)
    idents = verified_identifiers(db, user, None, {"email"})
    if not idents:
        raise ApiError(400, "no_verified_email")
    consume(db, user, "breach_check", "breach_check_per_month", per="month")
    scan = Scan(user_id=user.id, kind="breach")
    db.add(scan)
    db.flush()
    res = run_breach_check(db, user, idents, scan)
    scan.summary, scan.new_count = res, res["new"]
    if res["errors"] and not res["sources"]:
        scan.status = "failed"
    snapshot(db, user)
    audit(db, "scan.breach", user.id, count=len(idents))
    db.commit()
    return {"scan_id": scan.id, **res, "remaining": remaining(db, user, "breach_check", "breach_check_per_month", "month")}


@router.get("/breach")
def breach_list(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Finding).where(Finding.user_id == user.id, Finding.module == "breach_check", Finding.status != "trash")
                      .order_by(Finding.occurred_at.desc())).all()
    return {"items": [finding_view(r) for r in rows],
            "remaining": remaining(db, user, "breach_check", "breach_check_per_month", "month")}


# ------------------------------------------------------------------- M-01 privacy scan
class ScanIn(BaseModel):
    identifier_ids: list[str] | None = Field(default=None, max_length=20)
    deep: bool = False


def run_privacy_scan(db: Session, user: User, idents: list[Identifier], scan: Scan, deep: bool) -> dict:
    new, errors, sources = 0, [], set()
    names = [i for i in idents if i.kind == "name"]
    if use_demo(user):
        for h in Demo().search(names[0].value if names else user.email):
            _, is_new = upsert(db, user, module="privacy_scan", source=h["source"], key=h["url"], title=h["title"], url=h["url"],
                               data_types=[h["data_type"]], risk=h["risk"], scan_id=scan.id, attributable=h.get("attributable", True),
                               is_demo=True, details={"snippet": h["snippet"]})
            new += int(is_new)
        sources.add("demo")
    else:
        for ident in names:
            city = next((i.value for i in idents if i.kind == "city"), None)
            try:
                hits = registry.get("wikipedia").search(ident.value) if registry.get("wikipedia").enabled() else []
                sources.add("wikipedia")
            except SourceUnavailable as e:
                errors.append({"source": e.source, "reason": e.reason})
                hits = []
            for h in hits:
                # Same name ≠ same person. Wikipedia matches are flagged "not reliably attributable".
                _, is_new = upsert(db, user, module="privacy_scan", source="wikipedia", key=h["url"], title=h["title"], url=h["url"],
                                   data_types=["name"], risk="low", attributable=False, scan_id=scan.id, identifier_id=ident.id,
                                   details={"snippet": h["snippet"], "note": "not_reliably_attributable"})
                new += int(is_new)
            if deep:
                phrase = f"{ident.value} {city}" if city else ident.value
                chain = [registry.get("brave_search"), registry.get("google_cse")]
                src, hits, errs = registry_first(chain, lambda a, p=phrase: a.search(p))
                errors += errs
                for h in hits or []:
                    sources.add(src)
                    risk = classify_hit(h)
                    _, is_new = upsert(db, user, module="privacy_scan", source=src, key=h["url"], title=h["title"], url=h["url"],
                                       data_types=risk[1], risk=risk[0], scan_id=scan.id, identifier_id=ident.id,
                                       attributable=False, details={"snippet": h["snippet"], "note": "check_if_this_is_you"})
                    new += int(is_new)
        if deep:
            for ident in idents:
                if ident.kind in ("email", "username"):
                    chain = [registry.get("brave_search")]
                    src, hits, errs = registry_first(chain, lambda a, p=ident.value: a.search(p))
                    errors += errs
                    for h in hits or []:
                        risk = classify_hit(h)
                        _, is_new = upsert(db, user, module="privacy_scan", source=src, key=h["url"], title=h["title"], url=h["url"],
                                           data_types=risk[1] + [ident.kind], risk=risk[0], scan_id=scan.id, identifier_id=ident.id,
                                           details={"snippet": h["snippet"]})
                        new += int(is_new)
    # basic scan also includes email leak check (spec: "email leaks + search hits for own name")
    emails = [i for i in idents if i.kind == "email"]
    if emails:
        b = run_breach_check(db, user, emails, scan)
        new += b["new"]
        errors += b["errors"]
        sources |= set(b["sources"])
    return {"new": new, "errors": errors, "sources": sorted(sources)}


def classify_hit(h: dict) -> tuple[str, list[str]]:
    """Rule-based sensitivity of a web hit from its snippet (no fabrication: only what is visible)."""
    import re

    s = f"{h.get('title', '')} {h.get('snippet', '')}"
    types = []
    if re.search(r"\b\d{5}\s+[A-ZÄÖÜ]", s) or re.search(r"(straße|strasse|weg|allee|platz)\s+\d", s, re.I):
        types.append("address")
    if re.search(r"(\+49|0049|\b0\d{2,4})[\s/-]?\d{3,}", s):
        types.append("phone")
    if re.search(r"(geboren|geb\.|jahrgang|\b(19|20)\d{2}\b)", s, re.I):
        types.append("birthdate")
    if re.search(r"[\w.+-]+@[\w-]+\.\w+", s):
        types.append("email")
    risk = "high" if {"address", "phone"} & set(types) else "medium" if types else "low"
    return risk, types or ["name"]


@router.post("/scan/run")
def scan_run(body: ScanIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ratelimit.hit(f"scan:{user.id}", 5, 60)
    idents = verified_identifiers(db, user, body.identifier_ids)
    if not idents:
        raise ApiError(400, "no_verified_identifiers")
    if body.deep and not has_feature(user, "deep_scan"):
        raise ApiError(402, "premium_required", feature="deep_scan")
    consume(db, user, "deep_scan" if body.deep else "basic_scan", "deep_scan_per_month" if body.deep else "basic_scan_per_month", "month")
    scan = Scan(user_id=user.id, kind="deep" if body.deep else "basic")
    db.add(scan)
    db.flush()
    res = run_privacy_scan(db, user, idents, scan, body.deep)
    scan.summary, scan.new_count = res, res["new"]
    risk = snapshot(db, user)
    audit(db, "scan.run", user.id, kind=scan.kind, identifiers=len(idents))
    db.commit()
    return {"scan_id": scan.id, **res, "risk": risk}


@router.get("/scan/history")
def scan_history(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Scan).where(Scan.user_id == user.id).order_by(Scan.created_at.desc()).limit(50)).all()
    return [{"id": s.id, "kind": s.kind, "status": s.status, "summary": s.summary, "new": s.new_count, "created_at": s.created_at}
            for s in rows]


# ------------------------------------------------------------------- M-10 password (k-anonymity proxy)
@router.get("/password/range/{prefix}")
def password_range(prefix: str, response: Response):
    """Proxy for the Pwned Passwords range API. Receives only a 5-char SHA-1 prefix – never a password."""
    import re

    if not re.fullmatch(r"[0-9A-Fa-f]{5}", prefix):
        raise ApiError(400, "invalid_prefix")
    ratelimit.hit(f"pw:{prefix[:2]}", 600, 60)
    try:
        body = registry.get("pwned_passwords").range(prefix.upper())
    except SourceUnavailable as e:
        raise ApiError(503, "source_unavailable", source=e.source) from e
    response.headers["Cache-Control"] = "private, max-age=3600"
    return Response(body, media_type="text/plain")


# ------------------------------------------------------------------- M-20 results database
@router.get("/findings")
def findings(user: User = Depends(current_user), db: Session = Depends(get_db), q: str | None = None, module: str | None = None,
             source: str | None = None, risk: str | None = None, status: str = "active", tag: str | None = None,
             date_from: datetime | None = Query(default=None, alias="from"), date_to: datetime | None = Query(default=None, alias="to"),
             limit: int = Query(default=200, le=500)):
    stmt = select(Finding).where(Finding.user_id == user.id)
    if status == "active":
        stmt = stmt.where(Finding.status != "trash")
    elif status != "all":
        stmt = stmt.where(Finding.status == status)
    if module:
        stmt = stmt.where(Finding.module == module)
    if source:
        stmt = stmt.where(Finding.source == source)
    if risk:
        stmt = stmt.where(Finding.risk == risk)
    if date_from:
        stmt = stmt.where(Finding.found_at >= date_from)
    if date_to:
        stmt = stmt.where(Finding.found_at <= date_to)
    rows = db.scalars(stmt.order_by(Finding.found_at.desc()).limit(2000)).all()
    items = [finding_view(r) for r in rows]
    # Full-text search happens after decryption (titles/notes are encrypted at rest).
    if q:
        ql = q.lower()
        items = [i for i in items if ql in " ".join(str(x) for x in (i["title"], i["url"], i["note"], i["source"], i["tags"],
                                                                     i["details"])).lower()]
    if tag:
        items = [i for i in items if tag in i["tags"]]
    return {"items": items[:limit], "total": len(items)}


class FindingPatch(BaseModel):
    status: str | None = Field(default=None, pattern="^(open|done|trash)$")
    tags: list[str] | None = Field(default=None, max_length=20)
    note: str | None = Field(default=None, max_length=2000)


@router.patch("/findings/{fid}")
def patch_finding(fid: str, body: FindingPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    f = db.get(Finding, fid)
    if not f or f.user_id != user.id:
        raise ApiError(404, "not_found")
    if body.status:
        f.status = body.status
        f.trashed_at = now() if body.status == "trash" else None
        from app.core.events import timeline

        timeline(db, user.id, "change", f"Status '{body.status}': {f.title}", ref=f.id)
    if body.tags is not None:
        f.tags = [t[:32] for t in body.tags]
    if body.note is not None:
        f.note = body.note
    snapshot(db, user)
    db.commit()
    return finding_view(f)


@router.delete("/findings/trash")
def empty_trash(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Finding).where(Finding.user_id == user.id, Finding.status == "trash")).all()
    for r in rows:
        db.delete(r)
    db.commit()
    return {"deleted": len(rows)}


