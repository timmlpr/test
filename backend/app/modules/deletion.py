"""M-04 GDPR request generator (Art. 15 access, 16 rectification, 17 erasure) + deadline tracker.
The app never sends requests; the user sends them (mailto, copy, PDF). Not legal advice."""
from __future__ import annotations

import io
from datetime import timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.deps import current_user
from app.core.errors import ApiError
from app.core.events import timeline
from app.db import get_db
from app.models import DeletionRequest, Finding, Identifier, User, now

router = APIRouter(prefix="/requests", tags=["deletion"])
DEFAULT_DAYS = 30

# Per-source templates: known recipients for common German / EU data holders (public privacy contacts).
SOURCE_TEMPLATES = {
    "generic": {"label": "Allgemein", "email": None},
    "people_search": {"label": "Personensuchmaschine", "email": None,
                      "extra": "Bitte entfernen Sie zusätzlich alle Profile und Suchtreffer zu meiner Person aus Ihrem Index."},
    "search_engine": {"label": "Suchmaschine (Auslistung)", "email": None,
                      "extra": "Ich beantrage die Auslistung der genannten URL aus Ihren Suchergebnissen (Art. 17 DSGVO, EuGH C-131/12)."},
    "shop": {"label": "Onlineshop / Kundenkonto", "email": None,
             "extra": "Bitte löschen Sie mein Kundenkonto. Soweit gesetzliche Aufbewahrungspflichten bestehen, schränken Sie die Verarbeitung bitte ein (Art. 18 DSGVO)."},
    "breach": {"label": "Dienst mit Datenleck", "email": None,
               "extra": "Ihr Dienst war von einem Datenleck betroffen. Bitte teilen Sie mir mit, welche meiner Daten betroffen waren (Art. 15, 34 DSGVO)."},
    "association": {"label": "Verein / Organisation", "email": None,
                    "extra": "Bitte entfernen Sie meine Daten insbesondere von öffentlich einsehbaren Webseiten und Listen."},
}

TEXTS = {
    "art17": ("Antrag auf Löschung personenbezogener Daten gemäß Art. 17 DSGVO",
              "hiermit fordere ich Sie auf, sämtliche bei Ihnen über mich gespeicherten personenbezogenen Daten unverzüglich zu "
              "löschen (Art. 17 Abs. 1 DSGVO). Sollten Sie meine Daten an Dritte weitergegeben haben, informieren Sie diese bitte "
              "über meinen Löschantrag (Art. 17 Abs. 2, Art. 19 DSGVO)."),
    "art15": ("Auskunftsersuchen gemäß Art. 15 DSGVO",
              "hiermit bitte ich um Auskunft, ob Sie personenbezogene Daten über mich verarbeiten. Falls ja, bitte ich um eine Kopie "
              "dieser Daten sowie um Angaben zu Verarbeitungszwecken, Empfängern, Speicherdauer und Herkunft der Daten (Art. 15 DSGVO)."),
    "art16": ("Antrag auf Berichtigung gemäß Art. 16 DSGVO",
              "die bei Ihnen über mich gespeicherten Daten sind unrichtig bzw. unvollständig. Bitte berichtigen Sie diese "
              "unverzüglich (Art. 16 DSGVO). Die korrekten Angaben lauten: [BITTE ERGÄNZEN]."),
}
DISCLAIMER = "Hinweis: Diese Vorlage ist keine Rechtsberatung. Sie wurde mit Tracelow erstellt und wird von dir selbst versendet."


def build(kind: str, *, sender_name: str, sender_email: str, recipient: str, url: str | None, template: str, address_form: str) -> tuple[str, str]:
    subject, core = TEXTS[kind]
    extra = SOURCE_TEMPLATES.get(template, SOURCE_TEMPLATES["generic"]).get("extra")
    lines = [f"An: {recipient}", "", "Sehr geehrte Damen und Herren,", "", core]
    if url:
        lines += ["", f"Betroffen ist insbesondere folgende Fundstelle: {url}"]
    if extra:
        lines += ["", extra]
    lines += ["", "Bitte bestätigen Sie mir die Erledigung innerhalb eines Monats (Art. 12 Abs. 3 DSGVO).",
              "Zur Identifikation: Ich bin unter der Absenderadresse dieser Nachricht erreichbar. Bitte fordern Sie zusätzliche "
              "Nachweise nur an, wenn begründete Zweifel an meiner Identität bestehen (Art. 12 Abs. 6 DSGVO).",
              "", "Mit freundlichen Grüßen", sender_name or "[DEIN NAME]", sender_email]
    return subject, "\n".join(lines)


def view(r: DeletionRequest) -> dict:
    from urllib.parse import quote

    mailto = f"mailto:{r.recipient_email or ''}?subject={quote(r.subject)}&body={quote(r.body)}"
    return {"id": r.id, "kind": r.kind, "recipient": r.recipient, "recipient_email": r.recipient_email, "subject": r.subject,
            "body": r.body, "status": r.status, "sent_at": r.sent_at, "due_at": r.due_at, "finding_id": r.finding_id,
            "created_at": r.created_at, "mailto": mailto, "overdue": bool(r.due_at and r.status == "sent" and r.due_at < now()),
            "disclaimer": DISCLAIMER}


@router.get("/templates")
def templates():
    return {"templates": SOURCE_TEMPLATES, "kinds": {k: v[0] for k, v in TEXTS.items()}, "default_days": DEFAULT_DAYS, "disclaimer": DISCLAIMER}


@router.get("")
def list_requests(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(DeletionRequest).where(DeletionRequest.user_id == user.id).order_by(DeletionRequest.created_at.desc())).all()
    return [view(r) for r in rows]


class RequestIn(BaseModel):
    kind: str = Field(pattern="^(art15|art16|art17)$")
    recipient: str = Field(min_length=2, max_length=200)
    recipient_email: str | None = Field(default=None, max_length=200)
    finding_id: str | None = None
    template: str = "generic"
    url: str | None = Field(default=None, max_length=1000)
    days: int = Field(default=DEFAULT_DAYS, ge=7, le=90)


@router.post("")
def create_request(body: RequestIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    url = body.url
    if body.finding_id:
        f = db.get(Finding, body.finding_id)
        if not f or f.user_id != user.id:
            raise ApiError(404, "not_found")
        url = url or f.url
    name = next((i.value for i in db.scalars(select(Identifier).where(Identifier.user_id == user.id, Identifier.kind == "name"))),
                user.display_name or "")
    subject, text = build(body.kind, sender_name=name, sender_email=user.email, recipient=body.recipient, url=url,
                          template=body.template, address_form=user.address_form)
    r = DeletionRequest(user_id=user.id, finding_id=body.finding_id, kind=body.kind, recipient=body.recipient,
                        recipient_email=body.recipient_email, subject=subject, body=text, status="open",
                        due_at=now() + timedelta(days=body.days))
    db.add(r)
    db.flush()
    timeline(db, user.id, "request", f"Anfrage erstellt ({body.kind.upper()}): {body.recipient}", ref=r.id)
    audit(db, "request.created", user.id, kind=body.kind)
    db.commit()
    return view(r)


class PatchIn(BaseModel):
    status: str | None = Field(default=None, pattern="^(open|sent|done|rejected)$")
    body: str | None = Field(default=None, max_length=20000)
    days: int | None = Field(default=None, ge=7, le=90)


@router.patch("/{rid}")
def patch_request(rid: str, body: PatchIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = db.get(DeletionRequest, rid)
    if not r or r.user_id != user.id:
        raise ApiError(404, "not_found")
    if body.body is not None:
        r.body = body.body
    if body.status:
        r.status = body.status
        if body.status == "sent":
            r.sent_at = now()
            r.due_at = now() + timedelta(days=body.days or DEFAULT_DAYS)
        if body.status == "done" and r.finding_id and (f := db.get(Finding, r.finding_id)):
            f.status = "done"
        timeline(db, user.id, "request", f"Anfrage {body.status}: {r.recipient}", ref=r.id)
    db.commit()
    return view(r)


@router.delete("/{rid}")
def delete_request(rid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = db.get(DeletionRequest, rid)
    if not r or r.user_id != user.id:
        raise ApiError(404, "not_found")
    db.delete(r)
    db.commit()
    return {"ok": True}


@router.get("/{rid}/pdf")
def request_pdf(rid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = db.get(DeletionRequest, rid)
    if not r or r.user_id != user.id:
        raise ApiError(404, "not_found")
    from app.modules.pdf import letter_pdf

    data = letter_pdf(r.subject, r.body, DISCLAIMER)
    return StreamingResponse(io.BytesIO(data), media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="anfrage-{r.kind}-{r.id[:6]}.pdf"'})
