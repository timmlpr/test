"""M-16 relation graph (own data only, no automatic relationship suggestions) and M-17 assistant."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.provider import ai_status, ask
from app.core.audit import audit
from app.core.deps import current_user, require_feature
from app.core.errors import ApiError
from app.core.guard import check_text
from app.core.plans import limit
from app.db import get_db
from app.models import DeletionRequest, FamilyTreePerson, Finding, Identifier, User, now
from app.modules.findings_service import current_risk

router = APIRouter(tags=["assistant"])


# ------------------------------------------------------------------ M-16 graph
@router.get("/graph")
def graph(user: User = Depends(require_feature("relation_graph")), db: Session = Depends(get_db)):
    nodes = [{"id": "me", "label": user.display_name or "Ich", "type": "me"}]
    edges = []
    idents = db.scalars(select(Identifier).where(Identifier.user_id == user.id)).all()
    for i in idents:
        nodes.append({"id": f"i:{i.id}", "label": i.value, "type": i.kind, "verified": i.verified_at is not None})
        edges.append({"source": "me", "target": f"i:{i.id}", "label": "gehört zu mir"})
    seen_sources: set[str] = set()
    for f in db.scalars(select(Finding).where(Finding.user_id == user.id, Finding.status != "trash")).all():
        src_id = f"s:{f.source}:{f.title}" if f.module == "breach_check" else f"s:{f.source}:{(f.url or '')[:80]}"
        if src_id not in seen_sources:
            seen_sources.add(src_id)
            nodes.append({"id": src_id, "label": f.title, "type": "breach" if f.module == "breach_check" else "source", "risk": f.risk,
                          "url": f.url, "finding_id": f.id, "data_types": f.data_types, "attributable": f.attributable})
        origin = f"i:{f.identifier_id}" if f.identifier_id and any(i.id == f.identifier_id for i in idents) else "me"
        edges.append({"source": origin, "target": src_id, "label": ", ".join(f.data_types or [])})
    for p in db.scalars(select(FamilyTreePerson).where(FamilyTreePerson.user_id == user.id)).all():
        nodes.append({"id": f"f:{p.id}", "label": p.label, "type": "family", "consent": p.consent_confirmed})
        edges.append({"source": "me", "target": f"f:{p.id}", "label": p.relation})
    return {"nodes": nodes, "edges": edges}


class TreeIn(BaseModel):
    label: str = Field(min_length=1, max_length=60)
    relation: str = Field(pattern="^(parent|child|sibling|partner|grandparent|grandchild|other)$")
    consent_confirmed: bool


@router.get("/graph/family")
def tree_list(user: User = Depends(require_feature("relation_graph")), db: Session = Depends(get_db)):
    return [{"id": p.id, "label": p.label, "relation": p.relation, "consent_confirmed": p.consent_confirmed}
            for p in db.scalars(select(FamilyTreePerson).where(FamilyTreePerson.user_id == user.id))]


@router.post("/graph/family")
def tree_add(body: TreeIn, user: User = Depends(require_feature("relation_graph")), db: Session = Depends(get_db)):
    """Self-maintained entry. Requires the member's consent; used only for display – never searched, never linked to findings."""
    if not body.consent_confirmed:
        raise ApiError(400, "consent_required")
    p = FamilyTreePerson(user_id=user.id, label=body.label, relation=body.relation, consent_confirmed=True)
    db.add(p)
    audit(db, "graph.family_added", user.id)
    db.commit()
    return {"id": p.id}


@router.delete("/graph/family/{pid}")
def tree_delete(pid: str, user: User = Depends(require_feature("relation_graph")), db: Session = Depends(get_db)):
    p = db.get(FamilyTreePerson, pid)
    if not p or p.user_id != user.id:
        raise ApiError(404, "not_found")
    db.delete(p)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ M-17 assistant
class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    voice: bool = False


def _cite(f: Finding) -> dict:
    return {"id": f.id, "title": f.title, "url": f.url, "risk": f.risk}


def classic_answer(db: Session, user: User, msg: str) -> dict:
    """Rule-based answers over the user's own dataset. Always cites findings and ends with one next step."""
    t = msg.lower()
    open_f = db.scalars(select(Finding).where(Finding.user_id == user.id, Finding.status == "open")).all()
    risk = current_risk(db, user)
    if re.search(r"überfällig|ueberfaellig|frist|deadline|anfrage|antrag", t):
        reqs = db.scalars(select(DeletionRequest).where(DeletionRequest.user_id == user.id, DeletionRequest.status == "sent")).all()
        overdue = [r for r in reqs if r.due_at and r.due_at < now()]
        if not reqs:
            return {"text": "Du hast noch keine Anfrage als „gesendet“ markiert. Nächster Schritt: Erstelle eine Löschanfrage für deinen wichtigsten Fund.",
                    "citations": [], "action": {"href": "/app/requests", "label": "Anfragen öffnen"}}
        txt = (f"{len(overdue)} von {len(reqs)} gesendeten Anfragen sind überfällig: " + ", ".join(r.recipient for r in overdue)
               if overdue else f"Keine Anfrage ist überfällig. {len(reqs)} laufen noch.")
        return {"text": txt + " Nächster Schritt: " + ("Schicke eine Erinnerung an die erste Stelle." if overdue else "Warte die Frist ab."),
                "citations": [{"id": r.id, "title": r.recipient, "url": None, "risk": "medium"} for r in overdue[:5]],
                "action": {"href": "/app/requests", "label": "Anfragen öffnen"}}
    if re.search(r"leck|leak|breach|gehackt", t):
        leaks = [f for f in open_f if f.module == "breach_check"]
        if not leaks:
            return {"text": "Für deine bestätigten E-Mail-Adressen sind keine offenen Datenlecks gespeichert. Nächster Schritt: Starte den Leck-Check, falls er länger her ist.",
                    "citations": [], "action": {"href": "/app/breaches", "label": "Leck-Check"}}
        pw = [f for f in leaks if "password" in (f.data_types or [])]
        return {"text": f"Du bist in {len(leaks)} Datenlecks enthalten, davon {len(pw)} mit Passwörtern. "
                        "Nächster Schritt: Ändere das Passwort beim zuerst genannten Dienst und überall, wo du es auch nutzt.",
                "citations": [_cite(f) for f in (pw or leaks)[:5]], "action": {"href": "/app/breaches", "label": "Lecks ansehen"}}
    if re.search(r"score|wert|punkte|ampel", t):
        f = risk["factors"]
        top = max((k for k in f if k != "protection"), key=lambda k: f[k])
        return {"text": f"Dein Risiko-Wert ist {risk['score']} von 100 ({ {'green': 'grün', 'yellow': 'gelb', 'red': 'rot'}[risk['light']] }). "
                        f"Den größten Anteil hat der Faktor „{top}“ mit {f[top]} Punkten. Nächster Schritt: siehe Startseite, „Nächster Schritt“.",
                "citations": [], "action": {"href": "/app/risk", "label": "Score erklärt"}}
    # default: biggest risk
    acts = [a for a in risk["actions"] if a["finding_id"] and a["impact"] > 0]
    if not acts:
        return {"text": "Ich sehe aktuell keinen offenen Fund mit großer Wirkung. Nächster Schritt: Arbeite die Sicherheits-Checkliste weiter ab.",
                "citations": [], "action": {"href": "/app/checklist", "label": "Checkliste"}}
    f = db.get(Finding, acts[0]["finding_id"])
    return {"text": f"Dein größtes Datenrisiko ist gerade: „{f.title}“ (Risiko {f.risk}). Wenn du das erledigst, sinkt dein Wert um etwa "
                    f"{acts[0]['impact']} Punkte. Nächster Schritt: " +
                    ("Passwort ändern und 2-Faktor einschalten." if "password" in (f.data_types or []) else "Löschanfrage erstellen."),
            "citations": [_cite(f)], "action": {"href": f"/app/requests/new?finding={f.id}", "label": "Jetzt erledigen"}}


@router.get("/assistant/status")
def assistant_status(user: User = Depends(current_user)):
    return ai_status()


@router.post("/assistant/chat")
def chat(body: ChatIn, user: User = Depends(require_feature("ai_assistant")), db: Session = Depends(get_db)):
    names = [i.value for i in db.scalars(select(Identifier).where(Identifier.user_id == user.id, Identifier.kind == "name"))]
    if ref := check_text(body.message, names):
        audit(db, "assistant.refused", user.id, category=ref.category)
        db.commit()
        return {"text": ref.message_de, "refused": True, "category": ref.category, "citations": [], "mode": "guard"}
    base = classic_answer(db, user, body.message)
    status = ai_status()
    if status["available"]:
        ctx = "\n".join(f"[{c['id']}] {c['title']} ({c['risk']})" for c in base["citations"]) or "keine"
        prompt = (f"Frage der Person: {body.message}\n\nRegelbasierte Antwort: {base['text']}\nRelevante eigene Funde:\n{ctx}\n\n"
                  "Formuliere eine kurze, freundliche Antwort (max. 4 Sätze) und nenne genau einen nächsten Schritt. "
                  "Erfinde keine Fakten; nutze nur die Angaben oben.")
        ai = ask(db, user, prompt, names + [user.email], int(limit(user, "ai_per_day")))
        if ai:
            return {**base, "text": ai, "mode": "ai", "provider": status["provider"]}
    return {**base, "mode": "classic"}
