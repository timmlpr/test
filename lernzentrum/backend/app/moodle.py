"""Moodle integration via the official web service API only (no scraping).

Auth paths (detected automatically from `tool_mobile_get_public_config`):
1. Password → token: `login/token.php` with service `moodle_mobile_app`. The password is used once, never stored
   or logged; only the token is kept (envelope-encrypted).
2. SSO sites: token from the Moodle app launch flow (`moodlemobile://token=…`) or the user's security-keys page
   ("Sicherheitsschlüssel" → Moodle mobile web service) pasted once.
3. Fallback: Moodle calendar export (ICS) link + manual upload.
"""
from __future__ import annotations

import base64
import re
import time
from datetime import datetime
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import SessionLocal, utcnow
from .jobs import enqueue, handler, periodic
from .models import Announcement, Deadline, Module, Secret, SyncState, User
from .providers import registry

SERVICE = "moodle_mobile_app"
UA = {"User-Agent": "Lernzentrum/1.0 (Moodle web service client)"}
MAX_FILES_PER_SYNC = 60
MAX_FILE_MB = 80
PAUSE_S = 0.25  # politeness between calls


class MoodleError(Exception):
    def __init__(self, msg: str, code: str = "") -> None:
        super().__init__(msg)
        self.code = code


def normalize_site(url: str) -> str:
    url = url.strip().rstrip("/")
    if not url.startswith("http"):
        url = "https://" + url
    return re.sub(r"/(login|my|course)(/.*)?$", "", url)


def detect(site: str) -> dict:
    """Which login path works for this site? Returns plain-language explanation."""
    site = normalize_site(site)
    try:
        r = httpx.post(f"{site}/lib/ajax/service-nologin.php", params={"info": "tool_mobile_get_public_config"},
                       json=[{"index": 0, "methodname": "tool_mobile_get_public_config", "args": {}}],
                       headers=UA, timeout=15)
        data = r.json()
        cfg = data[0].get("data") if isinstance(data, list) and data and not data[0].get("error") else None
    except (httpx.HTTPError, ValueError):
        cfg = None
    if not cfg:
        return {"site": site, "method": "ics", "sitename": "",
                "explain": "Die Moodle-App-Schnittstelle ist hier nicht erreichbar. Nutze den Kalender-Export (ICS) "
                           "von Moodle und lade Dateien manuell hoch."}
    typ = int(cfg.get("typeoflogin", 1))
    name = cfg.get("sitename", "")
    if typ == 1:
        return {"site": site, "method": "password", "sitename": name,
                "explain": "Du kannst dich direkt mit Moodle-Benutzername und Passwort verbinden. Das Passwort wird "
                           "nur einmal zum Abholen eines Tokens benutzt und nicht gespeichert."}
    launch = f"{site}/admin/tool/mobile/launch.php?" + urlencode(
        {"service": SERVICE, "passport": str(int(time.time())), "urlscheme": "moodlemobile"})
    return {"site": site, "method": "sso", "sitename": name, "launch_url": launch,
            "keys_url": f"{site}/user/managetoken.php",
            "explain": "Deine Hochschule nutzt Single Sign-on. Öffne den Link, melde dich an und kopiere danach den "
                       "Schlüssel „Moodle mobile web service“ von der Seite „Sicherheitsschlüssel“ – oder die "
                       "angezeigte moodlemobile://-Adresse – in das Feld."}


def exchange_password(site: str, username: str, password: str) -> str:
    """Password → token. The password only lives in this call's stack frame."""
    site = normalize_site(site)
    try:
        r = httpx.post(f"{site}/login/token.php", data={"username": username, "password": password, "service": SERVICE},
                       headers=UA, timeout=20)
        data = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise MoodleError("Moodle nicht erreichbar.") from exc
    if "token" in data:
        return data["token"]
    code = data.get("errorcode", "")
    msg = {"invalidlogin": "Benutzername oder Passwort falsch.",
           "enablewsdescription": "Die Hochschule hat den Web-Service-Zugang deaktiviert – nutze den ICS-Weg.",
           "sitemaintenance": "Moodle ist gerade im Wartungsmodus."}.get(code, data.get("error", "Unbekannter Fehler"))
    raise MoodleError(msg, code)


def parse_pasted_token(text: str) -> str:
    """Accepts a raw 32-hex token or `moodlemobile://token=BASE64(signature:::token[:::privatetoken])`."""
    text = text.strip()
    if re.fullmatch(r"[0-9a-f]{32}", text):
        return text
    m = re.search(r"token=([A-Za-z0-9+/=_-]+)", text)
    if m:
        raw = m.group(1)
        raw += "=" * (-len(raw) % 4)
        try:
            decoded = base64.b64decode(raw.replace("-", "+").replace("_", "/")).decode()
        except (ValueError, UnicodeDecodeError) as exc:
            raise MoodleError("Die Adresse enthält keinen lesbaren Token.") from exc
        parts = decoded.split(":::")
        if len(parts) >= 2 and re.fullmatch(r"[0-9a-f]{32}", parts[1]):
            return parts[1]
    raise MoodleError("Kein gültiger Moodle-Token erkannt.")


class MoodleClient:
    def __init__(self, site: str, token: str) -> None:
        self.site, self.token = normalize_site(site), token

    def call(self, fn: str, **params) -> dict | list:
        flat: dict[str, str] = {}

        def put(prefix: str, v) -> None:
            if isinstance(v, (list, tuple)):
                for i, x in enumerate(v):
                    put(f"{prefix}[{i}]", x)
            elif isinstance(v, dict):
                for k, x in v.items():
                    put(f"{prefix}[{k}]", x)
            else:
                flat[prefix] = str(int(v) if isinstance(v, bool) else v)

        for k, v in params.items():
            put(k, v)
        time.sleep(PAUSE_S)
        try:
            r = httpx.post(f"{self.site}/webservice/rest/server.php", headers=UA, timeout=30,
                           data={"wstoken": self.token, "wsfunction": fn, "moodlewsrestformat": "json", **flat})
            data = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise MoodleError(f"Moodle nicht erreichbar ({fn}).") from exc
        if isinstance(data, dict) and data.get("exception"):
            code = data.get("errorcode", "")
            if code in ("invalidtoken", "accessexception"):
                raise MoodleError("Moodle-Token ungültig oder widerrufen – bitte neu verbinden.", code)
            raise MoodleError(data.get("message", "Moodle-Fehler"), code)
        return data

    def download(self, fileurl: str) -> bytes:
        sep = "&" if "?" in fileurl else "?"
        url = fileurl.replace("/pluginfile.php", "/webservice/pluginfile.php") \
            if "/webservice/pluginfile.php" not in fileurl else fileurl
        r = httpx.get(f"{url}{sep}token={self.token}", headers=UA, timeout=120, follow_redirects=True)
        r.raise_for_status()
        return r.content


def client_for(db: Session, user: User) -> MoodleClient | None:
    row = registry.get_secret_row(db, user, "moodle")
    if not row:
        return None
    return MoodleClient(row.meta.get("site", ""), registry.get_secret(db, user, "moodle"))


def link(db: Session, user: User, site: str, token: str) -> dict:
    cl = MoodleClient(site, token)
    info = cl.call("core_webservice_get_site_info")
    registry.set_secret(db, user, "moodle", token, {"site": cl.site, "userid": info.get("userid"),
                                                    "sitename": info.get("sitename", ""),
                                                    "fullname": info.get("fullname", "")})
    row = registry.get_secret_row(db, user, "moodle")
    row.status, row.status_detail, row.checked_at = "ok", f"Verbunden als {info.get('fullname', '')}", utcnow()
    db.flush()
    return {"sitename": info.get("sitename"), "fullname": info.get("fullname")}


def _match_course(course: dict, modules: list[Module]) -> Module | None:
    from .ingest.classify import match_event_to_module

    for m in modules:
        if m.moodle_course_id == course["id"]:
            return m
    g = match_event_to_module(course.get("fullname", ""), "", course.get("shortname", ""), modules)
    if g.value and g.confidence >= 0.75:
        m = next(x for x in modules if x.id == g.value)
        m.moodle_course_id = course["id"]
        return m
    return None


def _state(db: Session, user: User, key: str) -> SyncState | None:
    return db.scalar(select(SyncState).where(SyncState.user_id == user.id, SyncState.source == "moodle",
                                             SyncState.key == key))


def sync(db: Session, user: User, cl: MoodleClient) -> dict:
    from .ingest.pipeline import intake

    meta = registry.get_secret_row(db, user, "moodle").meta
    uid = meta.get("userid") or cl.call("core_webservice_get_site_info")["userid"]
    courses = cl.call("core_enrol_get_users_courses", userid=uid)
    modules = list(db.scalars(select(Module).where(Module.user_id == user.id, Module.archived.is_(False))))
    stats = {"courses": len(courses), "files": 0, "deadlines": 0, "announcements": 0, "unmatched": []}
    files_budget = MAX_FILES_PER_SYNC
    course_map: dict[int, Module | None] = {}
    for c in courses:
        mod = _match_course(c, modules)
        course_map[c["id"]] = mod
        if mod is None:
            stats["unmatched"].append(c.get("fullname"))
        contents = cl.call("core_course_get_contents", courseid=c["id"])
        for section in contents:
            for cm in section.get("modules", []):
                for f in cm.get("contents", []) or []:
                    if f.get("type") != "file" or not f.get("fileurl"):
                        continue
                    key = f"{c['id']}:{cm.get('id')}:{f.get('filepath', '/')}{f.get('filename')}"
                    fp = f"{f.get('timemodified', 0)}:{f.get('filesize', 0)}"
                    stt = _state(db, user, key)
                    if stt and stt.fingerprint == fp:
                        continue
                    if files_budget <= 0 or (f.get("filesize") or 0) > MAX_FILE_MB * 1024 * 1024:
                        continue
                    data = cl.download(f["fileurl"])
                    files_budget -= 1
                    doc, _ = intake(db, user, data, f.get("filename", "moodle.pdf"), f.get("mimetype", ""),
                                    channel="moodle", module_id=mod.id if mod else None,
                                    file_mtime=datetime.fromtimestamp(f.get("timemodified") or time.time()))
                    doc.meta = {**doc.meta, "moodle": {"course": c.get("fullname"), "activity": cm.get("name"),
                                                       "section": section.get("name")}}
                    if stt is None:
                        stt = SyncState(user_id=user.id, source="moodle", key=key)
                        db.add(stt)
                    stt.fingerprint, stt.document_id, stt.updated_at = fp, doc.id, utcnow()
                    stats["files"] += 1
        db.commit()
    # deadlines from calendar action events + assignments
    try:
        ev = cl.call("core_calendar_get_action_events_by_timesort", timesortfrom=int(time.time()), limitnum=50)
        for e in ev.get("events", []):
            mod = course_map.get((e.get("course") or {}).get("id"))
            ref = f"moodle-event:{e['id']}"
            if db.scalar(select(Deadline).where(Deadline.user_id == user.id, Deadline.source_ref == ref)):
                continue
            db.add(Deadline(user_id=user.id, module_id=mod.id if mod else None, title=e.get("name", "Termin"),
                            due=datetime.fromtimestamp(e.get("timesort") or e.get("timestart")), source="moodle",
                            source_ref=ref, status="accepted"))
            stats["deadlines"] += 1
    except MoodleError:
        pass
    # announcements (news forums)
    try:
        forums = cl.call("mod_forum_get_forums_by_courses", courseids=list(course_map))
        for f in forums:
            if f.get("type") != "news":
                continue
            disc = cl.call("mod_forum_get_forum_discussions", forumid=f["id"], perpage=10)
            mod = course_map.get(f.get("course"))
            for d in disc.get("discussions", []):
                ext = f"moodle-disc:{d.get('discussion')}"
                if db.scalar(select(Announcement).where(Announcement.user_id == user.id,
                                                        Announcement.external_id == ext)):
                    continue
                body = re.sub(r"<[^>]+>", " ", d.get("message", ""))
                db.add(Announcement(user_id=user.id, module_id=mod.id if mod else None, external_id=ext,
                                    title=d.get("subject") or d.get("name", "Ankündigung"),
                                    body=" ".join(body.split())[:4000], author=d.get("userfullname", ""),
                                    posted_at=datetime.fromtimestamp(d.get("created") or time.time())))
                stats["announcements"] += 1
    except MoodleError:
        pass
    row = registry.get_secret_row(db, user, "moodle")
    row.meta = {**row.meta, "last_sync": utcnow().isoformat(), "last_stats": {k: v for k, v in stats.items()
                                                                               if k != "unmatched"}}
    row.status, row.checked_at = "ok", utcnow()
    db.commit()
    return stats


@handler("moodle.sync")
def sync_job(db: Session, job) -> None:
    user = db.get(User, job.user_id)
    cl = client_for(db, user)
    if cl is None:
        return
    try:
        job.payload = {**job.payload, "result": sync(db, user, cl)}
    except MoodleError as exc:
        row = registry.get_secret_row(db, user, "moodle")
        row.status, row.status_detail = "error", str(exc)
        if exc.code not in ("invalidtoken", "accessexception"):
            raise
    db.commit()


@periodic("moodle.poll", 60 * 60)
def poll_all() -> None:
    with SessionLocal() as db:
        for row in db.scalars(select(Secret).where(Secret.provider == "moodle", Secret.status != "error")).all():
            enqueue(db, "moodle.sync", {}, user_id=row.user_id, label="Moodle-Abgleich")
        db.commit()
