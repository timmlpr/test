"""Live analyzers that run on every new transcript segment: keyword alerts, number keeper, correction watcher,
question suggestions. Pure functions where possible so they are unit-testable."""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..text import concepts, content_overlap, short, terms, tokens

# ---------------------------------------------------------------- keyword alerts
KEYWORD_CUES = [
    ("klausurrelevant", r"klausur\s*relevant|prüfungsrelevant|klausurwichtig"),
    ("kommt dran", r"(?:das|dies|so etwas|sowas) kommt (?:garantiert |sicher |bestimmt |auch )?(?:dran|in der klausur)|"
                   r"kommt in der (?:klausur|prüfung)"),
    ("merken", r"merken sie sich|bitte merken|unbedingt merken|das sollten sie sich merken|schreiben sie sich das auf"),
    ("wichtig", r"\b(?:ganz |sehr |besonders )?wichtig(?:e|er|es)?\b"),
    ("Prüfung", r"\bprüfung\b|\bklausur\b"),
    ("Achtung", r"\bachtung\b|aufpassen|typischer fehler|beliebter fehler|klassiker"),
]
_CUE_RE = [(name, re.compile(p, re.I)) for name, p in KEYWORD_CUES]


def keyword_alerts(text: str) -> list[str]:
    hits = []
    for name, rx in _CUE_RE:
        if rx.search(text):
            hits.append(name)
    # "wichtig"/"Prüfung" alone are weak; keep them only if no stronger cue fired or they are emphasised
    strong = {"klausurrelevant", "kommt dran", "merken", "Achtung"}
    if any(h in strong for h in hits):
        return [h for h in hits if h in strong]
    return hits


# ---------------------------------------------------------------- number keeper
NUM_WORDS = {"null": 0, "ein": 1, "eins": 1, "eine": 1, "einen": 1, "einem": 1, "zwei": 2, "drei": 3, "vier": 4,
             "fünf": 5, "sechs": 6, "sieben": 7, "acht": 8, "neun": 9, "zehn": 10, "elf": 11, "zwölf": 12,
             "fünfzehn": 15, "zwanzig": 20, "dreißig": 30, "hundert": 100, "tausend": 1000}
_NUM = r"(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?|" + "|".join(sorted(NUM_WORDS, key=len, reverse=True)) + r")"
PATTERNS = [
    ("amount", re.compile(_NUM + r"\s*(?:€|euro|eur)\b", re.I)),
    ("percent", re.compile(_NUM + r"\s*(?:%|prozent)", re.I)),
    ("deadline", re.compile(r"\b(?:bis (?:zum|spätestens)|spätestens (?:am|bis)|frist (?:endet|läuft)[^.]{0,20}?)\s*"
                            r"(\d{1,2}\.\s?(?:\d{1,2}\.|januar|februar|märz|april|mai|juni|juli|august|september|"
                            r"oktober|november|dezember)(?:\s?\d{2,4})?)", re.I)),
    ("date", re.compile(r"\b(\d{1,2}\.\s?\d{1,2}\.\s?(?:\d{4}|\d{2})?)(?!\d)")),
    ("duration", re.compile(_NUM + r"\s*(jahre?n?|monate?n?|wochen?|tage?n?|stunden?)\b", re.I)),
]


@dataclass
class NumberHit:
    kind: str
    value: str
    context: str


def numbers(text: str) -> list[NumberHit]:
    out: list[NumberHit] = []
    taken: list[tuple[int, int]] = []
    for kind, rx in PATTERNS:
        for m in rx.finditer(text):
            if any(a <= m.start() < b for a, b in taken):
                continue
            taken.append((m.start(), m.end()))
            lo = max(0, m.start() - 70)
            out.append(NumberHit(kind, m.group(0).strip(), short(text[lo:m.end() + 70], 160)))
    return out


def _num_value(tok: str) -> float | None:
    tok = tok.lower()
    if tok in NUM_WORDS:
        return float(NUM_WORDS[tok])
    try:
        return float(tok.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def quantities(text: str) -> dict[str, set[float]]:
    """unit -> numeric values, for contradiction detection ("drei Jahre" vs. "zehn Jahre")."""
    out: dict[str, set[float]] = {}
    for kind, rx in PATTERNS:
        if kind not in ("amount", "percent", "duration"):
            continue
        for m in rx.finditer(text):
            v = _num_value(m.group(1))
            if v is None:
                continue
            unit = kind if kind != "duration" else re.sub(r"(e?n|e)$", "", m.group(2).lower())[:4]
            out.setdefault(unit, set()).add(v)
    return out


# ---------------------------------------------------------------- correction watcher
CORRECTION_CUES = re.compile(
    r"\b(nein|nicht ganz|stimmt (?:so )?nicht|das ist falsch|falsch|achtung|vorsicht|eigentlich|korrekt(?:er)? ist|"
    r"richtig ist|genauer gesagt|sondern|im gegenteil|anders als|ausnahme|nicht (?:immer|automatisch)|"
    r"das gilt nur|nur wenn|außer)\b", re.I)


@dataclass
class CorrectionSignal:
    reason: str
    strength: float
    statement: str


AFFIRM = re.compile(r"^\s*(richtig|genau|korrekt|ja\b|stimmt|sehr gut|exakt)", re.I)


def detect_correction(answer_text: str, question: str, new_text: str) -> CorrectionSignal | None:
    """Heuristic: lecturer's later statement contradicts or qualifies a shown answer.

    Requires that the statement is about the *question's* topic (shares at least one of its concepts) – a later
    remark about something else never flags an answer. Affirmations ("Richtig, …") are not corrections unless a
    number contradicts the answer."""
    new_terms = set(terms(new_text))
    q_concepts = concepts(question)
    if not q_concepts or not any(c & new_terms for c in q_concepts):
        return None
    shared = sum(1 for c in q_concepts if c & new_terms) / len(q_concepts)
    q_ans, q_new = quantities(answer_text), quantities(new_text)
    for unit, vals in q_new.items():
        if unit in q_ans and not (vals & q_ans[unit]):
            return CorrectionSignal(f"Zahl weicht ab ({', '.join(f'{v:g}' for v in sorted(q_ans[unit]))} → "
                                    f"{', '.join(f'{v:g}' for v in sorted(vals))})", 0.85, new_text)
    if AFFIRM.match(new_text):
        return None
    if CORRECTION_CUES.search(new_text) and (shared >= 0.5 or content_overlap(new_text, answer_text) >= 0.3):
        return CorrectionSignal("Dozent relativiert/korrigiert das Thema", 0.6, new_text)
    return None


# ---------------------------------------------------------------- question suggestions
def suggest_questions(topic_words: list[str], statute_label: str | None, slide_terms: list[str],
                      discussed: str) -> list[str]:
    """Template suggestions without LLM: gaps (slide terms not yet discussed) + norm-related follow-ups."""
    out = []
    disc = set(tokens(discussed))
    gaps = [t for t in slide_terms if tokens(t) and tokens(t)[0] not in disc][:2]
    for g in gaps:
        out.append(f"Wie hängt „{g}“ mit dem aktuellen Thema zusammen?")
    if statute_label:
        out.append(f"Gibt es Ausnahmen oder Sonderregeln zu {statute_label}?")
        out.append(f"Wie würde man {statute_label} in einer Klausur im Gutachtenstil prüfen?")
    if topic_words:
        out.append(f"Könnten Sie ein Beispiel aus der Praxis zu „{topic_words[0]}“ geben?")
        out.append(f"Ist „{topic_words[0]}“ klausurrelevant – und in welcher Form?")
    seen, uniq = set(), []
    for q in out:
        if q not in seen:
            seen.add(q)
            uniq.append(q)
    return uniq[:4]
