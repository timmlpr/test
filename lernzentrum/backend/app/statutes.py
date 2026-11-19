"""Official statutes from gesetze-im-internet.de – the only external source the app uses.

* `get_norm` fetches a single norm page (`/<law>/__<n>.html`) and caches it in the `statutes` table (30 days).
* `load_law` downloads the official XML of a whole law (`/<law>/xml.zip`) for the statute finder.
* `find` ranks cached norms for a free-text question (BM25 over title + text).
"""
from __future__ import annotations

import io
import math
import re
import zipfile
from collections import Counter
from datetime import timedelta
from html import unescape
from xml.etree import ElementTree as ET

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import utcnow
from .models import Statute
from .text import LAW_SLUGS, LAWS, StatuteRef, short, tokens

CACHE_DAYS = 30
UA = {"User-Agent": "Lernzentrum/1.0 (private study app; statute lookup)"}


def slug(law: str) -> str:
    low = law.lower()
    return LAW_SLUGS.get(low, low)


def norm_url(law: str, norm: str) -> str:
    return f"{get_settings().statute_base_url}/{slug(law)}/__{norm.lower()}.html"


def _clean(html: str) -> str:
    html = re.sub(r"<br\s*/?>", "\n", html)
    html = re.sub(r"</(div|p|dd|dt|li)>", "\n", html)
    text = unescape(re.sub(r"<[^>]+>", "", html))
    lines = [" ".join(l.split()) for l in text.splitlines()]
    return "\n".join(l for l in lines if l)


def parse_norm_html(html: str) -> tuple[str, str]:
    """Return (title, text) from a gesetze-im-internet.de norm page."""
    title = ""
    m = re.search(r'<span class="jnenbez">(.*?)</span>(?:&nbsp;|\s)*(?:<span class="jnentitel">(.*?)</span>)?', html, re.S)
    if m:
        title = " ".join(unescape(re.sub(r"<[^>]+>", "", (m.group(1) or "") + " " + (m.group(2) or ""))).split())
    blocks = re.findall(r'<div class="jurAbsatz">(.*?)</div>', html, re.S)
    if not blocks:
        body = re.search(r'<div class="jnhtml">(.*)</div>\s*</div>', html, re.S)
        blocks = [body.group(1)] if body else []
    text = "\n".join(_clean(b) for b in blocks).strip()
    return title, text


def cached(db: Session, law: str, norm: str) -> Statute | None:
    return db.scalar(select(Statute).where(Statute.law == law.lower(), Statute.norm == norm.lower()))


def get_norm(db: Session, law: str, norm: str, *, allow_fetch: bool = True) -> Statute | None:
    law, norm = law.lower(), norm.lower()
    row = cached(db, law, norm)
    fresh = row and not row.demo and row.fetched_at and utcnow() - row.fetched_at < timedelta(days=CACHE_DAYS)
    if fresh or not allow_fetch:
        return row
    try:
        r = httpx.get(norm_url(law, norm), headers=UA, timeout=10, follow_redirects=True)
        if r.status_code != 200:
            return row
        title, text = parse_norm_html(r.content.decode("iso-8859-1", errors="replace")
                                      if "charset=iso" in r.headers.get("content-type", "").lower() else r.text)
    except httpx.HTTPError:
        return row  # offline: keep cached/demo text
    if not text:
        return row
    if row is None:
        row = Statute(law=law, norm=norm)
        db.add(row)
    row.title, row.text, row.url, row.demo, row.fetched_at = title, text, norm_url(law, norm), False, utcnow()
    db.flush()
    return row


def resolve_ref(db: Session, ref: StatuteRef, default_law: str | None, allow_fetch: bool = True) -> Statute | None:
    law = ref.law or default_law
    if not law:
        return None
    return get_norm(db, law, ref.norm, allow_fetch=allow_fetch)


def as_source(st: Statute, absatz: str | None = None) -> dict:
    law = LAWS.get(st.law, st.law.upper())
    label = f"§ {st.norm}{' Abs. ' + absatz if absatz else ''} {law}"
    return {"type": "statute", "law": law, "norm": st.norm, "label": label, "title": st.title, "url": st.url,
            "excerpt": short(st.text, 400), "demo": st.demo}


# ---------------------------------------------------------------- whole-law import (statute finder)
def parse_law_xml(data: bytes) -> list[tuple[str, str, str]]:
    """Parse the official XML (gii-norm.dtd) into (norm, title, text) triples."""
    out = []
    root = ET.fromstring(data)
    for norm in root.iter("norm"):
        meta = norm.find("metadaten")
        if meta is None:
            continue
        enbez = (meta.findtext("enbez") or "").strip()
        m = re.match(r"(?:§|Art)\.?\s*(\d+[a-z]?)", enbez)
        if not m:
            continue
        title = (meta.findtext("titel") or "").strip()
        content = norm.find("textdaten/text/Content")
        if content is None:
            continue
        paras = [" ".join("".join(p.itertext()).split()) for p in content.iter("P")]
        text = "\n".join(p for p in paras if p)
        if text:
            out.append((m.group(1).lower(), f"{enbez} {title}".strip(), text))
    return out


def load_law(db: Session, law: str) -> int:
    url = f"{get_settings().statute_base_url}/{slug(law)}/xml.zip"
    r = httpx.get(url, headers=UA, timeout=60, follow_redirects=True)
    r.raise_for_status()
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    xml_name = next(n for n in zf.namelist() if n.endswith(".xml"))
    rows = parse_law_xml(zf.read(xml_name))
    for norm, title, text in rows:
        st = cached(db, law, norm) or Statute(law=law.lower(), norm=norm)
        st.title, st.text, st.url, st.demo, st.fetched_at = title, text, norm_url(law, norm), False, utcnow()
        db.add(st)
    db.flush()
    return len(rows)


def find(db: Session, question: str, laws: list[str] | None = None, k: int = 5) -> list[tuple[Statute, float]]:
    q = select(Statute)
    if laws:
        q = q.where(Statute.law.in_([l.lower() for l in laws]))
    rows = list(db.scalars(q))
    if not rows:
        return []
    qt = set(tokens(question))
    docs = [tokens(f"{r.title} {r.title} {r.text}") for r in rows]
    df: Counter = Counter()
    for d in docs:
        df.update(set(d))
    n = len(rows)
    avg = sum(len(d) for d in docs) / n
    scored = []
    for r, d in zip(rows, docs):
        tf = Counter(d)
        s = 0.0
        for t in qt:
            if t in tf:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                s += idf * tf[t] * 2.2 / (tf[t] + 1.2 * (0.25 + 0.75 * len(d) / avg))
        if s > 0:
            scored.append((r, s))
    scored.sort(key=lambda x: -x[1])
    top = scored[0][1] if scored else 1
    return [(r, s / top) for r, s in scored[:k]]


# Demo excerpts so the app is clickable offline. Marked demo=True and replaced by the official text on first
# online lookup. Only short, stable norms are included.
DEMO_NORMS = [
    ("bgb", "433", "§ 433 Vertragstypische Pflichten beim Kaufvertrag",
     "(1) Durch den Kaufvertrag wird der Verkäufer einer Sache verpflichtet, dem Käufer die Sache zu übergeben und "
     "das Eigentum an der Sache zu verschaffen. Der Verkäufer hat dem Käufer die Sache frei von Sach- und "
     "Rechtsmängeln zu verschaffen.\n(2) Der Käufer ist verpflichtet, dem Verkäufer den vereinbarten Kaufpreis zu "
     "zahlen und die gekaufte Sache abzunehmen."),
    ("bgb", "195", "§ 195 Regelmäßige Verjährungsfrist", "Die regelmäßige Verjährungsfrist beträgt drei Jahre."),
    ("hgb", "1", "§ 1 Istkaufmann",
     "(1) Kaufmann im Sinne dieses Gesetzbuchs ist, wer ein Handelsgewerbe betreibt.\n(2) Handelsgewerbe ist jeder "
     "Gewerbebetrieb, es sei denn, daß das Unternehmen nach Art oder Umfang einen in kaufmännischer Weise "
     "eingerichteten Geschäftsbetrieb nicht erfordert."),
    ("hgb", "238", "§ 238 Buchführungspflicht",
     "(1) Jeder Kaufmann ist verpflichtet, Bücher zu führen und in diesen seine Handelsgeschäfte und die Lage seines "
     "Vermögens nach den Grundsätzen ordnungsmäßiger Buchführung ersichtlich zu machen. Die Buchführung muß so "
     "beschaffen sein, daß sie einem sachverständigen Dritten innerhalb angemessener Zeit einen Überblick über die "
     "Geschäftsvorfälle und über die Lage des Unternehmens vermitteln kann. Die Geschäftsvorfälle müssen sich in "
     "ihrer Entstehung und Abwicklung verfolgen lassen."),
]


def seed_demo_norms(db: Session) -> None:
    for law, norm, title, text in DEMO_NORMS:
        if cached(db, law, norm) is None:
            db.add(Statute(law=law, norm=norm, title=title, text=text, url=norm_url(law, norm), demo=True))
    db.flush()


def _register_jobs() -> None:
    from .jobs import handler

    @handler("statutes.load")
    def load_job(db: Session, job) -> None:
        job.payload = {**job.payload, "norms": load_law(db, job.payload["law"])}
        db.commit()


_register_jobs()
