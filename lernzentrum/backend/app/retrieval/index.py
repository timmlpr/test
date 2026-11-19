"""Chunking + hybrid search (BM25 + vectors) with exact source locations.

Index data is decrypted once per (user, module) and cached in memory; any write to chunks bumps a generation
counter that invalidates the cache.
"""
from __future__ import annotations

import math
import threading
from collections import Counter
from dataclasses import dataclass, field

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import Chunk, Document, Recording, User
from ..text import find_statutes, from_blob, local_vector, short, terms, to_blob

_gen = 0
_cache: dict[tuple, "_ModuleIndex"] = {}
_lock = threading.Lock()


def bump() -> None:
    global _gen
    with _lock:
        _gen += 1
        _cache.clear()


# ---------------------------------------------------------------- chunking
def chunk_pages(pages: list[str], size: int = 900, overlap: int = 150) -> list[tuple[int | None, str]]:
    """Split page texts into chunks keeping the page number. Short pages (slides) stay whole."""
    out: list[tuple[int | None, str]] = []
    for i, page in enumerate(pages, start=1):
        page = " ".join(page.split())
        if not page:
            continue
        if len(page) <= size * 1.3:
            out.append((i, page))
            continue
        start = 0
        while start < len(page):
            end = min(len(page), start + size)
            if end < len(page):
                cut = page.rfind(". ", start + size // 2, end)
                end = cut + 1 if cut > 0 else end
            out.append((i, page[start:end].strip()))
            if end >= len(page):
                break
            start = max(end - overlap, start + 1)
    return out


def chunk_transcript(segments: list[tuple[float, float, str]], window_s: float = 60.0) -> list[tuple[float, float, str]]:
    out: list[tuple[float, float, str]] = []
    buf: list[str] = []
    w_start = None
    w_end = 0.0
    for start, end, text in segments:
        if w_start is None:
            w_start = start
        buf.append(text)
        w_end = end
        if end - w_start >= window_s:
            out.append((w_start, w_end, " ".join(buf)))
            buf, w_start = [], None
    if buf and w_start is not None:
        out.append((w_start, w_end, " ".join(buf)))
    return out


def index_document(db: Session, doc: Document, pages: list[str] | None = None,
                   segments: list[tuple[float, float, str]] | None = None) -> int:
    """(Re)build chunks for a document. Returns chunk count."""
    db.execute(delete(Chunk).where(Chunk.document_id == doc.id))
    rows: list[Chunk] = []
    if segments is not None:
        for i, (s, e, t) in enumerate(chunk_transcript(segments)):
            rows.append(Chunk(user_id=doc.user_id, document_id=doc.id, module_id=doc.module_id, ordinal=i,
                              start_s=s, end_s=e, text=t, local_vec=to_blob(local_vector(t))))
    else:
        for i, (p, t) in enumerate(chunk_pages(pages or [])):
            rows.append(Chunk(user_id=doc.user_id, document_id=doc.id, module_id=doc.module_id, ordinal=i,
                              page=p, text=t, local_vec=to_blob(local_vector(t))))
    db.add_all(rows)
    db.flush()
    bump()
    return len(rows)


# ---------------------------------------------------------------- search
@dataclass
class Hit:
    chunk_id: int
    document_id: int
    title: str
    kind: str
    text: str
    score: float
    page: int | None = None
    start_s: float | None = None
    end_s: float | None = None
    recording_id: int | None = None
    module_id: int | None = None
    bm25: float = 0.0
    vec: float = 0.0
    statutes: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        if self.start_s is not None:
            m, s = divmod(int(self.start_s), 60)
            h, m = divmod(m, 60)
            ts = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
            return f"{self.title} · {ts}"
        if self.page:
            return f"{self.title} · {'Folie' if self.kind == 'slides' else 'S.'} {self.page}"
        return self.title

    def as_source(self) -> dict:
        return {"type": "material", "chunk_id": self.chunk_id, "document_id": self.document_id, "title": self.title,
                "kind": self.kind, "page": self.page, "start_s": self.start_s, "end_s": self.end_s,
                "recording_id": self.recording_id, "label": self.label, "excerpt": short(self.text, 280),
                "score": round(self.score, 3), "statutes": self.statutes}


class _ModuleIndex:
    def __init__(self, rows: list[tuple[Chunk, Document]]) -> None:
        self.rows = rows
        self.toks = [terms(c.text) for c, _ in rows]
        self.tf = [Counter(t) for t in self.toks]
        self.df: Counter = Counter()
        for t in self.toks:
            self.df.update(set(t))
        self.n = max(1, len(rows))
        self.avgdl = sum(len(t) for t in self.toks) / self.n if rows else 1.0
        self.local = np.vstack([from_blob(c.local_vec) for c, _ in rows]) if rows else np.zeros((0, 512), np.float32)
        self.gem = [from_blob(c.gemini_vec) for c, _ in rows]
        self.statutes = [{r.key for r in find_statutes(c.text)} for c, _ in rows]

    def bm25(self, q: list[str], k1: float = 1.4, b: float = 0.75) -> np.ndarray:
        scores = np.zeros(len(self.rows), dtype=np.float32)
        for term in set(q):
            df = self.df.get(term)
            if not df:
                continue
            idf = math.log(1 + (self.n - df + 0.5) / (df + 0.5))
            for i, tf in enumerate(self.tf):
                f = tf.get(term)
                if f:
                    dl = len(self.toks[i])
                    scores[i] += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * dl / self.avgdl))
        return scores


def _load(db: Session, user_id: int, module_id: int | None, kinds: tuple[str, ...] | None) -> _ModuleIndex:
    key = (user_id, module_id, kinds, _gen)
    with _lock:
        if key in _cache:
            return _cache[key]
    q = select(Chunk, Document).join(Document, Document.id == Chunk.document_id).where(Chunk.user_id == user_id)
    if module_id is not None:
        q = q.where(Chunk.module_id == module_id)
    if kinds:
        q = q.where(Document.kind.in_(kinds))
    idx = _ModuleIndex(list(db.execute(q).all()))
    with _lock:
        _cache[key] = idx
    return idx


def search(db: Session, user: User, query: str, *, module_id: int | None = None, k: int = 6,
           kinds: tuple[str, ...] | None = None, query_vec: list[float] | None = None,
           boost_statutes: list[str] | None = None, focus: str | None = None) -> list[Hit]:
    idx = _load(db, user.id, module_id, kinds)
    if not idx.rows:
        return []
    q_tokens = terms(query) + (terms(focus) * 2 if focus else [])
    bm = idx.bm25(q_tokens)
    bm_norm = bm / bm.max() if bm.max() > 0 else bm
    qv = local_vector(query)
    cos = idx.local @ qv
    if query_vec is not None:
        gq = np.asarray(query_vec, dtype=np.float32)
        gq = gq / (np.linalg.norm(gq) or 1)
        for i, gv in enumerate(idx.gem):
            if gv is not None and gv.shape == gq.shape:
                cos[i] = float(gv @ gq)
    cos = np.clip(cos, 0, 1)
    score = 0.55 * bm_norm + 0.45 * cos
    # absolute relevance: bm25 alone normalises to 1 even for weak matches → damp by term coverage
    cov_terms = set(terms(focus)) if focus else set(q_tokens)
    coverage = np.array([len(cov_terms & set(t)) / max(1, len(cov_terms)) for t in idx.toks], np.float32)
    score = score * (0.4 + 0.6 * coverage)
    if boost_statutes:
        wanted = set(boost_statutes)
        for i, st in enumerate(idx.statutes):
            if st & wanted:
                score[i] += 0.15
    order = np.argsort(-score)[:k]
    hits: list[Hit] = []
    for i in order:
        if score[i] <= 0.05:
            continue
        c, d = idx.rows[i]
        hits.append(Hit(chunk_id=c.id, document_id=d.id, title=d.title, kind=d.kind, text=c.text,
                        score=float(min(1.0, score[i])), page=c.page, start_s=c.start_s, end_s=c.end_s,
                        recording_id=d.recording_id, module_id=d.module_id, bm25=float(bm_norm[i]),
                        vec=float(cos[i]), statutes=sorted(idx.statutes[i])))
    return hits


def recording_title(db: Session, rec_id: int | None) -> str:
    rec = db.get(Recording, rec_id) if rec_id else None
    return rec.title if rec else ""
