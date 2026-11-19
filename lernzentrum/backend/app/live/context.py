"""Rolling lecture context and follow-up resolution.

The context keeps the last minutes of transcript, recently mentioned norms (with the last named law as default),
frequent topic terms, examples and the current slide. `resolve` turns a possibly elliptic question ("Und was gilt
dann für die Verjährung?") into a self-contained retrieval query – never just the last sentence.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass, field

from ..text import LAWS, STOP, StatuteRef, find_statutes, fold, tokens

WINDOW_S = 300.0
FOLLOWUP_START = re.compile(r"^(und|aber|also|dann|was ist (?:dann|damit|mit)|was gilt (?:dann|da|hier)|"
                            r"wie ist das|und wie|und was|und wenn|gilt das|ist das|was heißt das|warum (?:das|dann))\b",
                            re.I)
ANAPHORA = {"das", "dies", "diese", "dieser", "dieses", "dafür", "dazu", "davon", "damit", "dort", "hier", "da", "er",
            "sie", "es", "ihn", "ihm", "dann", "derselbe", "solche", "jener", "dabei", "darauf"}
EXAMPLE_RE = re.compile(r"\b(zum beispiel|beispiel|fall:|nehmen wir an|angenommen|stellen sie sich vor)\b", re.I)


@dataclass
class LiveContext:
    recent: list[list] = field(default_factory=list)  # [start, end, text]
    statutes: list[dict] = field(default_factory=list)  # {key,label,law,norm,at}
    default_law: str | None = None
    examples: list[str] = field(default_factory=list)
    slide: dict | None = None
    last_question: str = ""
    last_query: str = ""

    @classmethod
    def from_json(cls, data: dict | None) -> "LiveContext":
        data = data or {}
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def to_json(self) -> dict:
        return asdict(self)

    # ------------------------------------------------------------ updates
    def add(self, start: float, end: float, text: str) -> None:
        self.recent.append([start, end, text])
        self.recent = [r for r in self.recent if r[1] >= end - WINDOW_S]
        for ref in find_statutes(text):
            law = ref.law or self.default_law
            if ref.law:
                self.default_law = ref.law
            key = f"{(law or '?').lower()}:{ref.norm}"
            self.statutes = [s for s in self.statutes if s["key"] != key]
            label = StatuteRef(law, ref.norm, ref.absatz).label
            self.statutes.append({"key": key, "label": label, "law": law, "norm": ref.norm, "at": end})
        self.statutes = self.statutes[-6:]
        if EXAMPLE_RE.search(text):
            self.examples = (self.examples + [text])[-3:]

    @property
    def now(self) -> float:
        return self.recent[-1][1] if self.recent else 0.0

    def transcript(self, seconds: float = WINDOW_S) -> str:
        cutoff = self.now - seconds
        return " ".join(r[2] for r in self.recent if r[1] >= cutoff)

    def topic_terms(self, n: int = 6) -> list[str]:
        cnt = Counter(t for t in tokens(self.transcript()) if not t.isdigit() and len(t) > 3)
        return [t for t, c in cnt.most_common(n) if c >= 2] or [t for t, _ in cnt.most_common(min(n, 3))]

    def topic_words(self, n: int = 5) -> list[str]:
        """Surface forms (unstemmed) of the most frequent content words – for readable queries/prompts."""
        stems = self.topic_terms(n)
        words: dict[str, str] = {}
        for w in re.findall(r"[A-Za-zÄÖÜäöüß]{4,}", self.transcript()):
            st = tokens(w)
            if st and st[0] in stems and st[0] not in words and fold(w) not in STOP:
                words[st[0]] = w
        return [words[s] for s in stems if s in words]

    def current_statute(self) -> dict | None:
        return self.statutes[-1] if self.statutes else None

    def summary(self) -> dict:
        return {"statute": self.current_statute(), "topic": self.topic_words(), "slide": self.slide,
                "examples": self.examples[-1:], "default_law": self.default_law}


@dataclass
class ResolvedQuestion:
    question: str
    query: str
    statutes: list[StatuteRef]
    is_followup: bool
    reasons: list[str]
    topic: list[str]

    def statute_keys(self) -> list[str]:
        return [f"{(s.law or '?').lower()}:{s.norm}" for s in self.statutes]


def is_followup(question: str, has_context: bool) -> bool:
    if not has_context:
        return False
    q = question.strip()
    words = [fold(w) for w in re.findall(r"\w+", q.lower())]
    content = tokens(q)
    if FOLLOWUP_START.match(q):
        return True
    if any(w in ANAPHORA for w in words) and len(content) <= 4:
        return True
    return len(content) <= 2


def resolve(question: str, ctx: LiveContext) -> ResolvedQuestion:
    reasons: list[str] = []
    own_refs = find_statutes(question)
    refs: list[StatuteRef] = []
    for r in own_refs:
        if r.law is None and ctx.default_law:
            refs.append(StatuteRef(ctx.default_law, r.norm, r.absatz))
            reasons.append(f"Gesetz aus Kontext ergänzt: {ctx.default_law}")
        else:
            refs.append(r)
    has_ctx = bool(ctx.recent)
    follow = is_followup(question, has_ctx)
    parts = [question]
    topic = ctx.topic_words()
    if follow or not own_refs:
        cur = ctx.current_statute()
        if cur and cur["law"]:
            ref = StatuteRef(cur["law"], cur["norm"])
            if ref not in refs:
                refs.append(ref)
                parts.append(cur["label"])
                reasons.append(f"Bezug auf zuletzt genannte Norm {cur['label']}")
    if follow:
        reasons.append("Anschlussfrage erkannt – Kontext der letzten Minuten einbezogen")
        before = [r[2] for r in ctx.recent if r[2].strip() != question.strip()][-2:]
        parts.extend(before)
        if ctx.last_question:
            parts.append(ctx.last_question)
    if topic:
        parts.append(" ".join(topic))
        reasons.append("Thema: " + ", ".join(topic[:4]))
    if ctx.slide and ctx.slide.get("title"):
        parts.append(ctx.slide.get("excerpt", "")[:200])
        reasons.append(f"Aktuelle Folie: {ctx.slide.get('label', '')}")
    query = " ".join(p for p in parts if p).strip()
    return ResolvedQuestion(question=question, query=query, statutes=refs, is_followup=follow, reasons=reasons,
                            topic=topic)


def law_label(law: str | None) -> str:
    return LAWS.get((law or "").lower(), law or "")
