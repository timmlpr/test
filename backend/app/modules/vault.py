"""M-12 subscription guard, M-13 document scanner, M-14 digital estate (all premium)."""
from __future__ import annotations

import email
import io
import mailbox
import re
import secrets
import tempfile
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta
from email.utils import parseaddr, parsedate_to_datetime

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.deps import require_feature
from app.core.errors import ApiError
from app.core.events import timeline
from app.core.mailer import send_mail
from app.db import get_db
from app.models import Document, EstateVault, MailSubscription, Reminder, User, now
from app.settings import get_settings

router = APIRouter(tags=["vault"])
MAX_UPLOAD = 50 * 1024 * 1024

# ------------------------------------------------------------------ M-12 subscription guard
AMOUNT_RE = re.compile(r"(\d{1,4}[.,]\d{2})\s?(?:€|EUR)|(?:€|EUR)\s?(\d{1,4}[.,]\d{2})")
SUB_WORDS = re.compile(r"(abo|abonnement|subscription|mitgliedschaft|monatlich|jährlich|verlängert|rechnung|invoice|beitrag)", re.I)
ACCOUNT_WORDS = re.compile(r"(willkommen|welcome|konto (wurde )?erstellt|registrierung|bestätige deine e-mail|verify your email|account created)", re.I)
YEARLY = re.compile(r"(jährlich|jahresabo|annual|yearly|pro jahr)", re.I)


def classify_message(headers: dict, body: str) -> dict | None:
    """Metadata-only classification. Returns None for personal mail (no List-Unsubscribe, no commercial signals)."""
    sender = headers.get("from", "")
    name, addr = parseaddr(sender)
    if not addr or "@" not in addr:
        return None
    domain = addr.split("@", 1)[1].lower()
    subject = headers.get("subject", "")
    text = f"{subject}\n{body[:4000]}"
    unsub = headers.get("list-unsubscribe")
    amount = None
    if SUB_WORDS.search(text):
        m = AMOUNT_RE.search(text)
        if m:
            amount = float((m.group(1) or m.group(2)).replace(",", "."))
    if amount is not None:
        cat = "subscription"
    elif ACCOUNT_WORDS.search(text):
        cat = "account"
    elif unsub:
        cat = "newsletter"
    else:
        return None
    link = None
    if unsub:
        urls = re.findall(r"<([^>]+)>", unsub)
        link = next((u for u in urls if u.startswith("https://")), urls[0] if urls else None)
    return {"sender": name or addr, "domain": domain, "category": cat, "amount": amount,
            "interval": ("year" if YEARLY.search(text) else "month") if amount else None, "unsubscribe": link}


def _iter_messages(data: bytes, filename: str):
    name = filename.lower()
    if name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for info in z.infolist()[:5000]:
                if info.filename.lower().endswith((".eml", ".mbox")) and info.file_size < 20 * 1024 * 1024:
                    yield from _iter_messages(z.read(info), info.filename)
        return
    if name.endswith(".eml"):
        yield email.message_from_bytes(data)
        return
    with tempfile.NamedTemporaryFile(suffix=".mbox") as tmp:  # mailbox needs a path; deleted on close
        tmp.write(data)
        tmp.flush()
        for i, msg in enumerate(mailbox.mbox(tmp.name)):
            if i > 20000:
                break
            yield msg


def _body_text(msg) -> str:
    try:
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    return (part.get_payload(decode=True) or b"").decode(part.get_content_charset() or "utf-8", "replace")
            return ""
        return (msg.get_payload(decode=True) or b"").decode(msg.get_content_charset() or "utf-8", "replace")
    except Exception:  # noqa: BLE001
        return ""


@router.post("/subs/upload")
async def subs_upload(file: UploadFile = File(...), user: User = Depends(require_feature("subscription_guard")),
                      db: Session = Depends(get_db)):
    """Accepts .mbox / .eml / .zip mail export. Only metadata (sender, category, amount, unsubscribe link) is stored;
    message bodies are parsed in memory and discarded."""
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise ApiError(413, "file_too_large")
    agg: dict[str, dict] = defaultdict(lambda: {"count": 0})
    scanned = 0
    for msg in _iter_messages(data, file.filename or "export.mbox"):
        scanned += 1
        headers = {k.lower(): str(v) for k, v in msg.items() if k.lower() in ("from", "subject", "list-unsubscribe", "date")}
        c = classify_message(headers, _body_text(msg))
        if not c:
            continue
        key = f"{c['domain']}|{c['category']}"
        a = agg[key]
        a.update({k: v for k, v in c.items() if v is not None or k not in a})
        a["count"] += 1
        try:
            d = parsedate_to_datetime(headers.get("date", "")).replace(tzinfo=None)
            a["last"] = max(a.get("last") or d, d)
        except (TypeError, ValueError):
            pass
    db.execute(delete(MailSubscription).where(MailSubscription.user_id == user.id))
    for a in agg.values():
        db.add(MailSubscription(user_id=user.id, sender=a["sender"], sender_domain=a["domain"], category=a["category"],
                                amount=a.get("amount"), interval=a.get("interval"), unsubscribe=a.get("unsubscribe"),
                                last_seen=a.get("last"), message_count=a["count"]))
    timeline(db, user.id, "change", f"Mail-Export analysiert: {len(agg)} Absender erkannt")
    db.commit()
    return {"scanned": scanned, "found": len(agg)}


@router.get("/subs")
def subs_list(user: User = Depends(require_feature("subscription_guard")), db: Session = Depends(get_db)):
    rows = db.scalars(select(MailSubscription).where(MailSubscription.user_id == user.id)).all()
    monthly = sum((r.amount or 0) / (12 if r.interval == "year" else 1) for r in rows if r.category == "subscription")
    return {"items": [{"id": r.id, "sender": r.sender, "domain": r.sender_domain, "category": r.category, "amount": r.amount,
                       "interval": r.interval, "unsubscribe": r.unsubscribe, "last_seen": r.last_seen, "count": r.message_count}
                      for r in sorted(rows, key=lambda r: (r.category, r.sender_domain))],
            "monthly_cost": round(monthly, 2), "counts": {c: sum(r.category == c for r in rows) for c in ("newsletter", "subscription", "account")},
            "mailbox_oauth": {"available": False, "reason": "needs_google_or_microsoft_oauth_app_review"}}


@router.get("/subs/xlsx")
def subs_xlsx(user: User = Depends(require_feature("subscription_guard")), db: Session = Depends(get_db)):
    wb = Workbook()
    ws = wb.active
    ws.title = "Abos"
    ws.append(["Absender", "Domain", "Kategorie", "Betrag (EUR)", "Intervall", "Monatlich (EUR)", "Abmelde-Link", "Zuletzt"])
    for r in db.scalars(select(MailSubscription).where(MailSubscription.user_id == user.id)):
        m = round((r.amount or 0) / (12 if r.interval == "year" else 1), 2) if r.amount else None
        ws.append([r.sender, r.sender_domain, r.category, r.amount, r.interval, m, r.unsubscribe, str(r.last_seen or "")[:10]])
    buf = io.BytesIO()
    wb.save(buf)
    return StreamingResponse(io.BytesIO(buf.getvalue()), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": 'attachment; filename="abos.xlsx"'})


@router.delete("/subs")
def subs_clear(user: User = Depends(require_feature("subscription_guard")), db: Session = Depends(get_db)):
    db.execute(delete(MailSubscription).where(MailSubscription.user_id == user.id))
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ M-13 document scanner
DATE_RE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{2,4})\b")
DEADLINE_CTX = re.compile(r"(frist|kündig|bis zum|spätestens|fällig|zahlbar|widerruf|verlänger|ablauf|endet|laufzeit)", re.I)
SENSITIVE_RE = {"iban": re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,7}\b"),
                "tax_id": re.compile(r"\b(Steuer-?ID|Steueridentifikationsnummer)\b.{0,20}\d{2}\s?\d{3}\s?\d{3}\s?\d{3}", re.I),
                "social_security": re.compile(r"\b\d{2}\s?\d{6}\s?[A-Z]\s?\d{3}\b"),
                "health": re.compile(r"\b(diagnose|befund|krankenkasse|versichertennummer)\b", re.I),
                "birthdate": re.compile(r"\b(geboren|geb\.|geburtsdatum)\b", re.I)}


def extract_deadlines(text: str) -> list[dict]:
    out = []
    for m in DATE_RE.finditer(text):
        d, mo, y = (int(x) for x in m.groups())
        y = y + 2000 if y < 100 else y
        try:
            dt = datetime(y, mo, d)
        except ValueError:
            continue
        # context = same sentence only (a date's keyword must not leak in from the previous sentence)
        before = re.split(r"(?<!\d)[.!?]\s", text[max(0, m.start() - 100): m.start()])[-1]
        after = re.split(r"(?<!\d)[.!?](\s|$)", text[m.end(): m.end() + 60])[0]
        ctx = before + m.group(0) + after
        if DEADLINE_CTX.search(ctx):
            out.append({"date": dt.date().isoformat(), "context": re.sub(r"\s+", " ", ctx).strip()[:160]})
    return out


def detect_sensitive(text: str) -> list[str]:
    return [k for k, r in SENSITIVE_RE.items() if r.search(text)]


def _ocr(data: bytes, filename: str) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader

        text = "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages[:50])
        if text.strip():
            return text
    if name.endswith(".txt"):
        return data.decode("utf-8", "replace")
    try:
        import pytesseract  # optional; installed in Docker image
        from PIL import Image

        return pytesseract.image_to_string(Image.open(io.BytesIO(data)), lang="deu+eng")
    except Exception as e:  # noqa: BLE001
        raise ApiError(422, "ocr_unavailable", "Texterkennung für Fotos ist hier nicht installiert. PDF mit Text funktioniert.") from e


@router.post("/documents")
async def doc_upload(file: UploadFile = File(...), user: User = Depends(require_feature("document_scanner")), db: Session = Depends(get_db)):
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise ApiError(413, "file_too_large")
    text = _ocr(data, file.filename or "upload")
    deadlines = extract_deadlines(text)
    doc = Document(user_id=user.id, title=(file.filename or "Dokument")[:120], text=text[:200_000], deadlines=deadlines,
                   sensitive=detect_sensitive(text))
    db.add(doc)
    db.flush()
    for dl in deadlines:
        due = datetime.fromisoformat(dl["date"])
        if due > now():
            db.add(Reminder(user_id=user.id, title=f"Frist: {doc.title}", due_at=due - timedelta(days=7), ref=doc.id))
    timeline(db, user.id, "change", f"Dokument gescannt: {len(deadlines)} Fristen erkannt", ref=doc.id)
    db.commit()
    return {"id": doc.id, "title": doc.title, "deadlines": deadlines, "sensitive": doc.sensitive, "chars": len(text)}


@router.get("/documents")
def doc_list(user: User = Depends(require_feature("document_scanner")), db: Session = Depends(get_db)):
    docs = db.scalars(select(Document).where(Document.user_id == user.id).order_by(Document.created_at.desc())).all()
    rems = db.scalars(select(Reminder).where(Reminder.user_id == user.id, Reminder.done.is_(False)).order_by(Reminder.due_at)).all()
    return {"items": [{"id": d.id, "title": d.title, "deadlines": d.deadlines, "sensitive": d.sensitive, "created_at": d.created_at,
                       "preview": d.text[:400]} for d in docs],
            "reminders": [{"id": r.id, "title": r.title, "due_at": r.due_at, "ref": r.ref} for r in rems]}


@router.delete("/documents/{did}")
def doc_delete(did: str, user: User = Depends(require_feature("document_scanner")), db: Session = Depends(get_db)):
    d = db.get(Document, did)
    if not d or d.user_id != user.id:
        raise ApiError(404, "not_found")
    db.execute(delete(Reminder).where(Reminder.ref == did, Reminder.user_id == user.id))
    db.delete(d)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ M-14 digital estate
class EstateIn(BaseModel):
    ciphertext: str = Field(max_length=2_000_000)  # AES-GCM, encrypted in the browser (PBKDF2 from user passphrase)
    salt: str = Field(max_length=64)
    iv: str = Field(max_length=64)
    trusted_email: str | None = Field(default=None, max_length=200)
    unlock_delay_days: int = Field(default=30, ge=3, le=365)


def _vault(db: Session, user: User) -> EstateVault:
    v = db.get(EstateVault, user.id)
    if not v:
        v = EstateVault(user_id=user.id)
        db.add(v)
        db.flush()
    return v


@router.get("/estate")
def estate_get(user: User = Depends(require_feature("digital_estate")), db: Session = Depends(get_db)):
    v = _vault(db, user)
    db.commit()
    return {"ciphertext": v.ciphertext, "salt": v.salt, "iv": v.iv, "trusted_email": v.trusted_email,
            "unlock_delay_days": v.unlock_delay_days, "unlock_requested_at": v.unlock_requested_at, "released_at": v.released_at,
            "updated_at": v.updated_at}


@router.put("/estate")
def estate_put(body: EstateIn, user: User = Depends(require_feature("digital_estate")), db: Session = Depends(get_db)):
    v = _vault(db, user)
    v.ciphertext, v.salt, v.iv, v.unlock_delay_days, v.updated_at = body.ciphertext, body.salt, body.iv, body.unlock_delay_days, now()
    if body.trusted_email != v.trusted_email:
        v.trusted_email = body.trusted_email
        v.unlock_token = secrets.token_urlsafe(24) if body.trusted_email else None
        if body.trusted_email:
            send_mail(body.trusted_email, "Du wurdest als Vertrauensperson benannt",
                      "Eine Person hat dich bei Fadeprint als Vertrauensperson für ihren digitalen Nachlass benannt.\n"
                      "Im Ernstfall kannst du hier die Freigabe anfragen. Die Person wird informiert und kann widersprechen:\n"
                      f"{get_settings().public_url}/estate/request?token={v.unlock_token}\n\n"
                      "Zum Entschlüsseln brauchst du zusätzlich das Kennwort, das dir die Person persönlich gegeben hat.")
    audit(db, "estate.updated", user.id)
    db.commit()
    return {"ok": True}


class UnlockIn(BaseModel):
    token: str


@router.post("/estate/unlock-request")
def estate_unlock_request(body: UnlockIn, db: Session = Depends(get_db)):
    """Trusted person requests release. Owner is notified and can veto during the delay."""
    v = db.scalar(select(EstateVault).where(EstateVault.unlock_token == body.token))
    if not v or not v.trusted_email:
        raise ApiError(400, "invalid_or_expired_token")
    if not v.unlock_requested_at:
        v.unlock_requested_at = now()
        owner = db.get(User, v.user_id)
        send_mail(owner.email, "Freigabe deines digitalen Nachlasses angefragt",
                  f"Deine Vertrauensperson hat die Freigabe angefragt. Ohne Widerspruch wird der verschlüsselte Inhalt in "
                  f"{v.unlock_delay_days} Tagen freigegeben. Widersprechen: {get_settings().public_url}/app/estate")
        db.commit()
    release_at = v.unlock_requested_at + timedelta(days=v.unlock_delay_days)
    if now() >= release_at:
        v.released_at = v.released_at or now()
        db.commit()
        return {"status": "released", "ciphertext": v.ciphertext, "salt": v.salt, "iv": v.iv}
    return {"status": "waiting", "release_at": release_at}


@router.post("/estate/veto")
def estate_veto(user: User = Depends(require_feature("digital_estate")), db: Session = Depends(get_db)):
    v = _vault(db, user)
    v.unlock_requested_at, v.released_at = None, None
    audit(db, "estate.veto", user.id)
    db.commit()
    return {"ok": True}
