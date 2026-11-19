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


def _store_messages(db: Session, user: User, messages, label: str) -> tuple[int, int]:
    """Aggregate (headers, body) pairs per sender+category and replace the user's stored list. Bodies are discarded."""
    agg: dict[str, dict] = defaultdict(lambda: {"count": 0})
    scanned = 0
    for headers, body in messages:
        scanned += 1
        c = classify_message(headers, body)
        if not c:
            continue
        a = agg[f"{c['domain']}|{c['category']}"]
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
    timeline(db, user.id, "change", f"{label} analysiert: {len(agg)} Absender erkannt")
    db.commit()
    return scanned, len(agg)


@router.post("/subs/upload")
async def subs_upload(file: UploadFile = File(...), user: User = Depends(require_feature("subscription_guard")),
                      db: Session = Depends(get_db)):
    """Accepts .mbox / .eml / .zip mail export. Only metadata (sender, category, amount, unsubscribe link) is stored;
    message bodies are parsed in memory and discarded."""
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise ApiError(413, "file_too_large")
    scanned, found = _store_messages(db, user, ((
        {k.lower(): str(v) for k, v in msg.items() if k.lower() in ("from", "subject", "list-unsubscribe", "date")}, _body_text(msg))
        for msg in _iter_messages(data, file.filename or "export.mbox")), "Mail-Export")
    return {"scanned": scanned, "found": found}


@router.get("/subs")
def subs_list(user: User = Depends(require_feature("subscription_guard")), db: Session = Depends(get_db)):
    rows = db.scalars(select(MailSubscription).where(MailSubscription.user_id == user.id)).all()
    monthly = sum((r.amount or 0) / (12 if r.interval == "year" else 1) for r in rows if r.category == "subscription")
    return {"items": [{"id": r.id, "sender": r.sender, "domain": r.sender_domain, "category": r.category, "amount": r.amount,
                       "interval": r.interval, "unsubscribe": r.unsubscribe, "last_seen": r.last_seen, "count": r.message_count}
                      for r in sorted(rows, key=lambda r: (r.category, r.sender_domain))],
            "monthly_cost": round(monthly, 2), "counts": {c: sum(r.category == c for r in rows) for c in ("newsletter", "subscription", "account")},
            "mailbox": _mailbox_status(db, user)}


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


# ------------------------------------------------------------------ M-12 mailbox connection (Gmail, read-only metadata)
GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.metadata"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
MAX_SYNC = 500


def _mailbox_available() -> bool:
    s = get_settings()
    return bool(s.google_client_id and s.google_client_secret)


def _mailbox_status(db: Session, user: User) -> dict:
    from app.models import MailboxConnection

    c = db.get(MailboxConnection, user.id)
    return {"available": _mailbox_available(), "connected": bool(c), "address": c.address if c else None,
            "last_sync": c.last_sync if c else None, "scope": "gmail.metadata"}


def _redirect_uri() -> str:
    return f"{get_settings().public_url}/api/subs/mailbox/callback"


@router.get("/subs/mailbox/start")
def mailbox_start(user: User = Depends(require_feature("subscription_guard")), db: Session = Depends(get_db)):
    """Redirect to Google consent: scope gmail.metadata only (headers, labels – no message bodies, no attachments)."""
    from urllib.parse import urlencode

    from fastapi.responses import RedirectResponse

    from app.core.security import token_hash
    from app.models import OneTimeToken

    if not _mailbox_available():
        raise ApiError(503, "mailbox_unavailable")
    state = secrets.token_urlsafe(24)
    db.add(OneTimeToken(token_hash=token_hash(state), user_id=user.id, purpose="mailbox_oauth", expires_at=now() + timedelta(minutes=10)))
    db.commit()
    params = {"client_id": get_settings().google_client_id, "redirect_uri": _redirect_uri(), "response_type": "code",
              "scope": f"openid email {GMAIL_SCOPE}", "access_type": "offline", "prompt": "consent", "state": state,
              "include_granted_scopes": "false"}
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}")


def _access_token(refresh_token: str) -> str:
    import httpx

    s = get_settings()
    r = httpx.post("https://oauth2.googleapis.com/token", data={"client_id": s.google_client_id, "client_secret": s.google_client_secret,
                                                                "refresh_token": refresh_token, "grant_type": "refresh_token"}, timeout=15)
    if r.status_code != 200:
        raise ApiError(400, "mailbox_reconnect_required")
    return r.json()["access_token"]


def _fetch_headers(access_token: str, limit: int = MAX_SYNC):
    """Yield (headers, '') for the newest messages. format=metadata never returns bodies."""
    import httpx

    h = {"Authorization": f"Bearer {access_token}"}
    with httpx.Client(timeout=20, headers=h) as c:
        ids, page = [], None
        while len(ids) < limit:
            params = {"maxResults": min(100, limit - len(ids))}
            if page:
                params["pageToken"] = page
            r = c.get(f"{GMAIL_API}/messages", params=params)
            if r.status_code != 200:
                raise ApiError(503, "mailbox_unavailable")
            j = r.json()
            ids += [m["id"] for m in j.get("messages", [])]
            page = j.get("nextPageToken")
            if not page:
                break
        for mid in ids:
            r = c.get(f"{GMAIL_API}/messages/{mid}", params=[("format", "metadata"), ("metadataHeaders", "From"),
                                                              ("metadataHeaders", "Subject"), ("metadataHeaders", "List-Unsubscribe"),
                                                              ("metadataHeaders", "Date")])
            if r.status_code != 200:
                continue
            hdrs = {x["name"].lower(): x["value"] for x in r.json().get("payload", {}).get("headers", [])}
            yield hdrs, ""


def mailbox_sync(db: Session, user: User) -> dict:
    from app.models import MailboxConnection

    conn = db.get(MailboxConnection, user.id)
    if not conn:
        raise ApiError(404, "mailbox_not_connected")
    scanned, found = _store_messages(db, user, _fetch_headers(_access_token(conn.refresh_token)), "Postfach")
    conn.last_sync = now()
    db.commit()
    return {"scanned": scanned, "found": found}


@router.get("/subs/mailbox/callback")
def mailbox_callback(code: str, state: str, user: User = Depends(require_feature("subscription_guard")), db: Session = Depends(get_db)):
    import httpx
    import jwt as pyjwt
    from fastapi.responses import RedirectResponse

    from app.core.security import token_hash
    from app.models import ConsentLog, MailboxConnection, OneTimeToken

    row = db.get(OneTimeToken, token_hash(state))
    if not row or row.purpose != "mailbox_oauth" or row.user_id != user.id or row.expires_at < now():
        raise ApiError(400, "invalid_or_expired_token")
    db.delete(row)
    s = get_settings()
    r = httpx.post("https://oauth2.googleapis.com/token", data={"code": code, "client_id": s.google_client_id,
                                                                "client_secret": s.google_client_secret, "redirect_uri": _redirect_uri(),
                                                                "grant_type": "authorization_code"}, timeout=15)
    if r.status_code != 200 or "refresh_token" not in r.json():
        raise ApiError(400, "oauth_failed")
    tok = r.json()
    if GMAIL_SCOPE not in tok.get("scope", ""):
        raise ApiError(400, "mailbox_scope_missing")
    # id_token received directly from Google’s token endpoint over TLS (OIDC Core 3.1.3.7 allows TLS server validation);
    # it is only used to display the connected address.
    address = pyjwt.decode(tok["id_token"], options={"verify_signature": False}).get("email") if tok.get("id_token") else None
    conn = db.get(MailboxConnection, user.id) or MailboxConnection(user_id=user.id, refresh_token="")
    conn.refresh_token, conn.address, conn.connected_at = tok["refresh_token"], address, now()
    db.merge(conn)
    db.add(ConsentLog(user_id=user.id, kind="mailbox", granted=True))
    audit(db, "mailbox.connected", user.id)
    db.commit()
    try:
        mailbox_sync(db, user)
    except ApiError:
        pass  # connection stays; user can retry sync
    return RedirectResponse(f"{s.public_url}/app/subscriptions?mailbox=connected", status_code=303)


@router.post("/subs/mailbox/sync")
def mailbox_sync_route(user: User = Depends(require_feature("subscription_guard")), db: Session = Depends(get_db)):
    from app.core import ratelimit

    ratelimit.hit(f"mailsync:{user.id}", 5, 3600)
    return mailbox_sync(db, user)


def revoke_mailbox(db: Session, user_id: str) -> None:
    """Revoke at Google (best effort) and delete the stored token."""
    import httpx

    from app.models import ConsentLog, MailboxConnection

    conn = db.get(MailboxConnection, user_id)
    if not conn:
        return
    try:
        httpx.post("https://oauth2.googleapis.com/revoke", params={"token": conn.refresh_token}, timeout=10)
    except httpx.HTTPError:
        pass
    db.delete(conn)
    db.add(ConsentLog(user_id=user_id, kind="mailbox", granted=False))


@router.delete("/subs/mailbox")
def mailbox_disconnect(user: User = Depends(require_feature("subscription_guard")), db: Session = Depends(get_db)):
    revoke_mailbox(db, user.id)
    audit(db, "mailbox.disconnected", user.id)
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
        import pytesseract  # tesseract binary: Docker image, start.sh/start.ps1 install it, or TESSERACT_CMD
        from PIL import Image

        if get_settings().tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = get_settings().tesseract_cmd

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
                      "Eine Person hat dich bei Tracelow als Vertrauensperson für ihren digitalen Nachlass benannt.\n"
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
