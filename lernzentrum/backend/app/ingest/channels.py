"""Extra intake channels: e-mail (IMAP poll or raw-MIME webhook) and cloud folder (WebDAV).

Credentials (IMAP/WebDAV passwords) are app passwords the user creates for this purpose; they are stored
envelope-encrypted like API keys.
"""
from __future__ import annotations

import email
import imaplib
from email import policy
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import SessionLocal, utcnow
from ..jobs import enqueue, handler, periodic
from ..models import Secret, SyncState, User
from ..providers import registry
from .pipeline import intake

MAX_ATTACH_MB = 60


def import_mime(db: Session, user: User, raw: bytes) -> int:
    msg = email.message_from_bytes(raw, policy=policy.default)
    try:
        when = parsedate_to_datetime(msg["date"]).replace(tzinfo=None) if msg["date"] else None
    except (TypeError, ValueError):
        when = None
    n = 0
    for part in msg.iter_attachments():
        name = part.get_filename()
        data = part.get_payload(decode=True) or b""
        if not name or not data or len(data) > MAX_ATTACH_MB * 1024 * 1024:
            continue
        intake(db, user, data, name, part.get_content_type(), channel="mail", file_mtime=when)
        n += 1
    if n == 0:
        body = msg.get_body(preferencelist=("plain",))
        text = body.get_content() if body else ""
        if text.strip():
            subject = (msg["subject"] or "Mail").strip()[:80]
            intake(db, user, text.encode(), f"{subject}.txt", "text/plain", channel="mail", file_mtime=when)
            n = 1
    db.flush()
    return n


def imap_poll(db: Session, user: User) -> int:
    row = registry.get_secret_row(db, user, "imap")
    if row is None:
        return 0
    meta, password = row.meta, registry.get_secret(db, user, "imap")
    conn = imaplib.IMAP4_SSL(meta["host"], int(meta.get("port", 993)), timeout=30)
    try:
        conn.login(meta["username"], password)
        conn.select(meta.get("folder", "INBOX"))
        typ, data = conn.search(None, "UNSEEN")
        n = 0
        for num in (data[0].split() if typ == "OK" else [])[:30]:
            typ, msg_data = conn.fetch(num, "(RFC822)")
            if typ == "OK" and msg_data and isinstance(msg_data[0], tuple):
                n += import_mime(db, user, msg_data[0][1])
                conn.store(num, "+FLAGS", "\\Seen")
        row.status, row.status_detail, row.checked_at = "ok", f"{n} Anhänge importiert", utcnow()
        db.commit()
        return n
    finally:
        try:
            conn.logout()
        except Exception:  # noqa: BLE001
            pass


def webdav_list(url: str, username: str, password: str) -> list[dict]:
    body = ('<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:getlastmodified/><d:getcontentlength/>'
            '<d:getetag/><d:resourcetype/><d:getcontenttype/></d:prop></d:propfind>')
    r = httpx.request("PROPFIND", url, auth=(username, password), headers={"Depth": "1"}, content=body, timeout=30)
    if r.status_code not in (207, 200):
        raise RuntimeError(f"WebDAV antwortet mit {r.status_code}")
    ns = {"d": "DAV:"}
    out = []
    for resp in ET.fromstring(r.content).findall("d:response", ns):
        href = resp.findtext("d:href", default="", namespaces=ns)
        prop = resp.find("d:propstat/d:prop", ns)
        if prop is None or prop.find("d:resourcetype/d:collection", ns) is not None:
            continue
        out.append({"href": href, "etag": prop.findtext("d:getetag", default="", namespaces=ns),
                    "modified": prop.findtext("d:getlastmodified", default="", namespaces=ns),
                    "type": prop.findtext("d:getcontenttype", default="", namespaces=ns)})
    return out


def webdav_sync(db: Session, user: User) -> int:
    row = registry.get_secret_row(db, user, "webdav")
    if row is None:
        return 0
    meta, password = row.meta, registry.get_secret(db, user, "webdav")
    base = meta["url"].rstrip("/") + "/"
    origin = "/".join(base.split("/")[:3])
    n = 0
    for f in webdav_list(base, meta["username"], password)[:200]:
        key = f["href"]
        state = db.scalar(select(SyncState).where(SyncState.user_id == user.id, SyncState.source == "webdav",
                                                  SyncState.key == key))
        if state and state.fingerprint == f["etag"]:
            continue
        r = httpx.get(origin + f["href"], auth=(meta["username"], password), timeout=120)
        if r.status_code != 200:
            continue
        try:
            mtime = parsedate_to_datetime(f["modified"]).replace(tzinfo=None) if f["modified"] else None
        except (TypeError, ValueError):
            mtime = None
        name = httpx.URL(origin + f["href"]).path.rsplit("/", 1)[-1]
        from urllib.parse import unquote

        doc, _ = intake(db, user, r.content, unquote(name), f["type"], channel="webdav", file_mtime=mtime)
        if state is None:
            state = SyncState(user_id=user.id, source="webdav", key=key)
            db.add(state)
        state.fingerprint, state.document_id, state.updated_at = f["etag"], doc.id, utcnow()
        n += 1
    row.status, row.status_detail, row.checked_at = "ok", f"{n} neue Dateien", utcnow()
    db.commit()
    return n


@handler("inbox.imap")
def imap_job(db: Session, job) -> None:
    imap_poll(db, db.get(User, job.user_id))


@handler("inbox.webdav")
def webdav_job(db: Session, job) -> None:
    webdav_sync(db, db.get(User, job.user_id))


@periodic("inbox.poll", 15 * 60)
def poll_all() -> None:
    with SessionLocal() as db:
        for row in db.scalars(select(Secret).where(Secret.provider.in_(["imap", "webdav"]))).all():
            enqueue(db, f"inbox.{row.provider}", {}, user_id=row.user_id, label=f"Eingang: {row.provider}")
        db.commit()

