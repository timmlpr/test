"""Grounded answer generation.

Evidence = module materials (hybrid search) + referenced statutes. Gemini (if configured) must answer ONLY from
numbered passages and cite them; otherwise an extractive answer is built from the best evidence sentences.
Confidence is always computed by `confidence.score` from the evidence.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from .. import statutes as st
from ..models import Answer, User
from ..providers import registry
from ..retrieval.index import Hit, search
from ..text import concepts, content_overlap, find_statutes, sentences, short, terms
from .confidence import Evidence, score
from .context import LiveContext, ResolvedQuestion, resolve

SYSTEM = (
    "Du bist ein Lernassistent für ein Studium Steuern und Rechnungswesen (Steuerrecht, BGB, HGB, BWL, Buchführung). "
    "Antworte ausschließlich auf Grundlage der nummerierten Quellen [S1], [S2] … Allgemeinwissen ist KEINE Quelle. "
    "Wenn die Quellen die Frage nicht beantworten, sage das ehrlich und setze support auf 'none'. "
    "Schreibe sachlich, deutsch, kurze Sätze. Zitiere Quellen im Text als [S1]."
)


@dataclass
class EvidenceItem:
    sid: str
    evidence: Evidence
    source: dict


@dataclass
class AnswerResult:
    reading: str
    probability: float
    short: str
    detailed: str
    sources: list[dict]
    level: str
    percent: int
    why: str
    engine: str
    factors: dict = field(default_factory=dict)


def gather_evidence(db: Session, user: User, rq: ResolvedQuestion, module_id: int | None,
                    allow_fetch: bool = True) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    wanted = set(rq.statute_keys())
    explicit = {r.norm for r in find_statutes(rq.question)}
    for ref in rq.statutes[:3]:
        norm = st.resolve_ref(db, ref, None, allow_fetch=allow_fetch)
        if norm and norm.text:
            key = f"{norm.law}:{norm.norm}"
            named = ref.norm in explicit  # named in the question itself vs. taken from lecture context
            items.append(EvidenceItem(f"S{len(items) + 1}",
                                      Evidence(norm.text, 1.0 if named else 0.5, key, True, named),
                                      st.as_source(norm, ref.absatz)))
    qvec = None
    emb = registry.embed(db, user, [rq.query]) if registry.llm_for(db, user) else None
    if emb:
        qvec = emb[0]
    hits: list[Hit] = search(db, user, rq.query, module_id=module_id, k=6, query_vec=qvec,
                             boost_statutes=list(wanted), focus=rq.question)
    for h in hits:
        match = bool(set(h.statutes) & wanted)
        items.append(EvidenceItem(f"S{len(items) + 1}", Evidence(h.text, h.score, f"doc:{h.document_id}", False, match),
                                  h.as_source()))
    return items


EXPECT = [
    ("amount", re.compile(r"\b(wie ?viel|wie hoch|ab welche\w*|bis zu welche\w*|welche\w* (betrag|grenze|summe|umsatz|"
                          r"gewinn|höhe|wert)|grenze|betrag)\b", re.I)),
    ("dur", re.compile(r"\b(wie lange|wann verjähr\w*|welche frist|frist)\b", re.I)),
    ("percent", re.compile(r"\b(prozent|steuersatz|satz|quote)\b", re.I)),
]


def expected_kinds(question: str) -> set[str]:
    """What kind of answer the question asks for (amount, duration, percent) – used as a ranking hint."""
    return {k for k, rx in EXPECT if rx.search(question)}


def _has_kind(sentence: str, kinds: set[str]) -> bool:
    from .analyzers import quantities

    q = quantities(sentence)
    return any((("amount" in kinds and "amount" in q), ("percent" in kinds and "percent" in q),
                ("dur" in kinds and any(u not in ("amount", "percent") for u in q))))


def _extractive(question: str, query: str, items: list[EvidenceItem], n: int) -> tuple[str, list[EvidenceItem]]:
    """Pick the evidence sentences that best cover the question's concepts (IDF-weighted over the candidates)."""
    import math

    focus = concepts(question)
    kinds = expected_kinds(question)
    ctx_all = set(terms(query.replace(question, " ")))
    ctx_terms = ctx_all - set().union(*focus) if focus else ctx_all
    cands: list[tuple[str, EvidenceItem, set[str]]] = []
    for it in items:
        for s in sentences(it.evidence.text):
            if len(s.split()) >= 4:
                cands.append((s, it, set(terms(s))))
    if not cands:
        return "", []
    n_c = len(cands)
    chunk_terms = {id(it): set(terms(it.evidence.text)) for it in items}
    # concepts already talked about in the lecture context weigh less than what is new in the question
    idf = [math.log(1 + n_c / (1 + sum(1 for _, _, ts in cands if ts & c))) * (0.5 if c & ctx_all else 1.0)
           for c in focus]
    total = sum(idf) or 1.0
    scored: list[tuple[float, str, EvidenceItem]] = []
    for s, it, ts in cands:
        cov = sum(w for c, w in zip(focus, idf) if ts & c) / total
        # the passage as a whole (incl. its heading) must be about the question, not just the sentence
        chunk_cov = sum(w for c, w in zip(focus, idf) if chunk_terms[id(it)] & c) / total
        head = set(terms(" ".join(s.split()[:6])))
        lead = sum(w for c, w in zip(focus, idf) if head & c) / total
        ctx = len(ts & ctx_terms) / max(1, len(ctx_terms))
        typed = 0.6 if kinds and _has_kind(s, kinds) else 0.0
        sc = (2 * cov + 1.0 * chunk_cov + 0.3 * lead + 0.4 * ctx + typed) * (0.7 + 0.3 * it.evidence.score)
        scored.append((sc, s, it))
    scored.sort(key=lambda x: -x[0])
    chosen: list[tuple[str, EvidenceItem]] = []
    for sc, s, it in scored:
        if sc <= 0.1 or any(content_overlap(s, c) > 0.8 for c, _ in chosen):
            continue
        chosen.append((s, it))
        if len(chosen) >= n:
            break
    text = " ".join(f"{s} [{it.sid}]" for s, it in chosen)
    used = []
    for _, it in chosen:
        if it not in used:
            used.append(it)
    return text, used


def sources_conflict(text: str) -> bool:
    """Two statements on the same topic with different numbers (e.g. outdated script vs. new slide)."""
    from .analyzers import quantities

    sents = [x for x in sentences(_strip_cites(text)) if quantities(x)]
    for i, a in enumerate(sents):
        qa = quantities(a)
        for b in sents[i + 1:]:
            qb = quantities(b)
            if content_overlap(a, b) >= 0.3 and any(u in qb and not qa[u] & qb[u] for u in qa):
                return True
    return False


def _strip_cites(text: str) -> str:
    import re

    return re.sub(r"\s*\[S\d+(?:,\s*S\d+)*\]", "", text).strip()


def _llm_answer(db: Session, user: User, rq: ResolvedQuestion, ctx: LiveContext | None, items: list[EvidenceItem],
                mode: str, profile: dict | None) -> list[dict] | None:
    passages = "\n\n".join(f"[{it.sid}] ({it.source['label']})\n{short(it.evidence.text, 1400)}" for it in items)
    ctx_txt = ""
    if ctx:
        ctx_txt = (f"Kontext der Vorlesung (nur zum Verständnis der Frage, keine Quelle): "
                   f"{short(ctx.transcript(180), 900)}\nAktuelle Norm: "
                   f"{(ctx.current_statute() or {}).get('label', '-')}\n")
    prof = ""
    if profile and profile.get("notes"):
        prof = f"Hinweise zum Dozenten (Formulierungen/Schwerpunkte): {short(profile['notes'], 400)}\n"
    prompt = (
        f"{ctx_txt}{prof}Frage aus der Vorlesung: \"{rq.question}\"\n"
        f"Aufgelöste Frage (mit Kontext): \"{short(rq.query, 400)}\"\n\nQuellen:\n{passages}\n\n"
        "Wenn die Frage mehrdeutig ist, gib bis zu 3 Lesarten mit Wahrscheinlichkeiten (Summe 1). Sonst genau eine. "
        "Antworte als JSON: {\"readings\":[{\"reading\":\"…\",\"probability\":0.0,\"short\":\"2-3 sprechbare Zeilen "
        "mit [S#]\",\"detailed\":\"ausführlich mit [S#], ggf. Gutachtenstil-Hinweis\",\"citations\":[\"S1\"],"
        "\"support\":\"direct|partial|none\",\"self_confidence\":0.0}]}"
    )
    data = registry.generate_json(db, user, prompt, system=SYSTEM, tier="flash" if mode == "detailed" else "lite",
                                  max_tokens=1400)
    if not isinstance(data, dict) or not isinstance(data.get("readings"), list):
        return None
    return data["readings"][:3]


def _ambiguous_extractive(question: str, items: list[EvidenceItem]) -> list[list[EvidenceItem]]:
    """Without an LLM, offer two readings only for vague questions (≤ 1 own concept, e.g. "Und warum gilt das?")
    whose two best material hits point to different norms with similar scores. Otherwise one reading."""
    if len(concepts(question)) > 1:
        return [items]
    mats = [i for i in items if not i.evidence.is_statute]
    if len(mats) >= 2 and mats[0].evidence.score - mats[1].evidence.score < 0.08:
        a, b = set(mats[0].source.get("statutes", [])), set(mats[1].source.get("statutes", []))
        if a and b and not a & b:
            statutes = [i for i in items if i.evidence.is_statute]
            return [[mats[0], *statutes], [mats[1], *statutes]]
    return [items]


def _reading_label(item: EvidenceItem) -> str:
    first = sentences(item.evidence.text)[:1]
    head = first[0] if first else item.source.get("label", "")
    return short(head.rstrip("."), 70)


def answer(db: Session, user: User, question: str, *, module_id: int | None, ctx: LiveContext | None = None,
           mode: str = "short", profile: dict | None = None, allow_fetch: bool = True,
           original: str | None = None) -> list[AnswerResult]:
    ctx = ctx or LiveContext()
    rq = resolve(question, ctx)
    items = gather_evidence(db, user, rq, module_id, allow_fetch=allow_fetch)
    by_sid = {it.sid: it for it in items}
    results: list[AnswerResult] = []
    if original and profile is not None:
        profile = {**profile, "notes": f"{profile.get('notes', '')} Unsicher korrigiertes Transkript, Original: "
                                      f"„{original[:300]}“"}
    readings = _llm_answer(db, user, rq, ctx, items, mode, profile) if items else None
    if readings:
        for r in readings:
            cited = [by_sid[c] for c in r.get("citations", []) if c in by_sid]
            short_t, detail_t = str(r.get("short", "")), str(r.get("detailed", ""))
            conf = score(_strip_cites(detail_t or short_t), [c.evidence for c in cited],
                         self_rating=float(r.get("self_confidence", 0.5) or 0.5), support_claim=r.get("support"),
                         question=rq.question, conflict=sources_conflict(" ".join(c.evidence.text for c in cited)))
            results.append(AnswerResult(r.get("reading") or question, float(r.get("probability", 1.0) or 1.0),
                                        short_t, detail_t, [c.source | {"sid": c.sid} for c in cited], conf.level,
                                        conf.percent, conf.why, "gemini", conf.factors))
    else:
        groups = _ambiguous_extractive(question, items) if items else [[]]
        for g_i, group in enumerate(groups):
            evid = group if len(groups) > 1 else items
            short_t, used = _extractive(question, rq.query, evid, 2)
            detail_t, used_d = _extractive(question, rq.query, evid, 5)
            conf = score(_strip_cites(detail_t), [u.evidence for u in used_d], question=rq.question,
                         conflict=sources_conflict(detail_t))
            prob = 1.0 if len(groups) == 1 else round((0.6 if g_i == 0 else 0.4), 2)
            reading = question if len(groups) == 1 else f"im Sinne von „{_reading_label(group[0])}“"
            results.append(AnswerResult(reading, prob, short_t or "Keine Quelle gefunden.", detail_t or short_t,
                                        [u.source | {"sid": u.sid} for u in used_d or used], conf.level, conf.percent,
                                        conf.why + ("; extraktiv (kein Gemini-Key)" if used_d else ""), "extractive",
                                        conf.factors))
    results.sort(key=lambda r: -r.probability)
    ctx.last_question, ctx.last_query = question, rq.query
    return results


def persist(db: Session, user: User, results: list[AnswerResult], *, question: str, module_id: int | None,
            recording_id: int | None, at_s: float | None, trigger: str, mode: str, query: str = "") -> list[Answer]:
    group = uuid.uuid4().hex[:12]
    rows = []
    for r in results:
        row = Answer(user_id=user.id, module_id=module_id, recording_id=recording_id, at_s=at_s, question=question,
                     resolved_query=query[:2000], trigger=trigger, mode=mode, group_id=group, reading=r.reading,
                     reading_prob=r.probability, text=r.short, detail=r.detailed, level=r.level, percent=r.percent,
                     why=r.why, sources=r.sources, engine=r.engine)
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


def answer_dict(a: Answer) -> dict:
    return {"id": a.id, "group_id": a.group_id, "question": a.question, "reading": a.reading,
            "probability": a.reading_prob, "short": a.text, "detailed": a.detail, "level": a.level,
            "percent": a.percent, "why": a.why, "sources": a.sources, "engine": a.engine, "at_s": a.at_s,
            "trigger": a.trigger, "correction": a.correction, "feedback": a.feedback, "module_id": a.module_id,
            "recording_id": a.recording_id, "created_at": a.created_at.isoformat() if a.created_at else None}
