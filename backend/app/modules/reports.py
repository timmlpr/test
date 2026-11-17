"""M-19 reports: honest free preview, versioned full reports (premium or one-time purchase), PDF/XLSX, compare."""
from __future__ import annotations

import io
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import current_user
from app.core.errors import ApiError
from app.core.events import timeline
from app.core.plans import has_feature
from app.db import get_db
from app.models import Finding, Purchase, Report, User, now
from app.modules.findings_service import current_risk, finding_view

router = APIRouter(prefix="/reports", tags=["reports"])


def _summary(db: Session, user: User) -> tuple[dict, list[dict]]:
    rows = db.scalars(select(Finding).where(Finding.user_id == user.id, Finding.status == "open")).all()
    r = current_risk(db, user)
    summary = {"score": r["score"], "light": r["light"], "factors": r["factors"], "total": len(rows),
               "high": sum(f.risk == "high" for f in rows), "medium": sum(f.risk == "medium" for f in rows),
               "breaches": sum(f.module == "breach_check" for f in rows), "hits": sum(f.module == "privacy_scan" for f in rows)}
    return summary, [finding_view(f) for f in rows], r["actions"]


@router.get("/preview")
def preview(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Free preview: counts only, details locked. Calm wording, no countdowns."""
    summary, _, _ = _summary(db, user)
    unlocked = has_feature(user, "full_report") or _unused_purchase(db, user) is not None
    return {"summary": {k: summary[k] for k in ("score", "light", "total", "high", "medium", "breaches", "hits")},
            "unlocked": unlocked}


def _unused_purchase(db: Session, user: User) -> Purchase | None:
    return db.scalar(select(Purchase).where(Purchase.user_id == user.id, Purchase.product == "one_time_report",
                                            Purchase.consumed.is_(False)))


@router.post("")
def create_report(user: User = Depends(current_user), db: Session = Depends(get_db)):
    kind = "full"
    if not has_feature(user, "full_report"):
        p = _unused_purchase(db, user)
        if not p:
            raise ApiError(402, "purchase_required", product="one_time_report")
        p.consumed, kind = True, "onetime"
    summary, findings, actions = _summary(db, user)
    version = (db.scalar(select(func.max(Report.version)).where(Report.user_id == user.id)) or 0) + 1
    plan = [{"title": a["title"] if a["title"] != "checklist_next" else "Nächsten Punkt der Sicherheits-Checkliste erledigen",
             "impact": a["impact"], "finding_id": a["finding_id"]} for a in actions if a["impact"] > 0]
    data = {"version": version, "created_at": now().isoformat(), "summary": summary, "findings": findings, "plan": plan}
    rep = Report(user_id=user.id, version=version, kind=kind, data=json.dumps(data, default=str, ensure_ascii=False))
    db.add(rep)
    timeline(db, user.id, "change", f"Report Version {version} erstellt", ref=rep.id)
    db.commit()
    return {"id": rep.id, "version": version, "kind": kind}


@router.get("")
def list_reports(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Report).where(Report.user_id == user.id).order_by(Report.version.desc())).all()
    out = []
    for r in rows:
        d = json.loads(r.data)
        out.append({"id": r.id, "version": r.version, "kind": r.kind, "created_at": r.created_at, "summary": d["summary"]})
    return out


def _get(db: Session, user: User, rid: str) -> dict:
    r = db.get(Report, rid)
    if not r or r.user_id != user.id:
        raise ApiError(404, "not_found")
    return json.loads(r.data)


@router.get("/{rid}")
def get_report(rid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _get(db, user, rid)


@router.get("/{rid}/pdf")
def report_pdf(rid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from app.modules.pdf import report_pdf as render

    d = _get(db, user, rid)
    return StreamingResponse(io.BytesIO(render(d)), media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="fadeprint-report-v{d["version"]}.pdf"'})


@router.get("/{rid}/xlsx")
def report_xlsx(rid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = _get(db, user, rid)
    wb = Workbook()
    ws = wb.active
    ws.title = "Zusammenfassung"
    head = Font(bold=True, color="FFFFFF")
    fill = PatternFill("solid", fgColor="2563EB")
    ws.append(["Kennzahl", "Wert"])
    for k, v in d["summary"].items():
        ws.append([k, json.dumps(v) if isinstance(v, dict) else v])
    ws2 = wb.create_sheet("Funde")
    ws2.append(["Risiko", "Modul", "Quelle", "Titel", "Link", "Datentypen", "Gefunden", "Zuordenbar"])
    for f in d["findings"]:
        ws2.append([f["risk"], f["module"], f["source"], f["title"], f["url"], ", ".join(f["data_types"]), str(f["found_at"])[:10],
                    "ja" if f["attributable"] else "nicht sicher"])
    ws3 = wb.create_sheet("Lösch-Plan")
    ws3.append(["#", "Schritt", "Wirkung (Punkte)"])
    for i, a in enumerate(d["plan"], 1):
        ws3.append([i, a["title"], a["impact"]])
    for sheet in (ws, ws2, ws3):
        for c in sheet[1]:
            c.font, c.fill = head, fill
        for col in sheet.columns:
            sheet.column_dimensions[col[0].column_letter].width = min(60, max(10, *(len(str(c.value or "")) for c in col)))
    buf = io.BytesIO()
    wb.save(buf)
    return StreamingResponse(io.BytesIO(buf.getvalue()),
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="fadeprint-report-v{d["version"]}.xlsx"'})


@router.get("/compare/{a}/{b}")
def compare(a: str, b: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Before/after: score delta and which findings were resolved or added between two versions."""
    ra, rb = _get(db, user, a), _get(db, user, b)
    ida = {f["id"]: f for f in ra["findings"]}
    idb = {f["id"]: f for f in rb["findings"]}
    return {"before": {"version": ra["version"], "score": ra["summary"]["score"], "total": ra["summary"]["total"]},
            "after": {"version": rb["version"], "score": rb["summary"]["score"], "total": rb["summary"]["total"]},
            "resolved": [ida[i]["title"] for i in ida.keys() - idb.keys()],
            "added": [idb[i]["title"] for i in idb.keys() - ida.keys()],
            "score_delta": rb["summary"]["score"] - ra["summary"]["score"]}
