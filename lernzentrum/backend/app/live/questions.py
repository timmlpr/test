"""Rule-based detection of questions and implicit prompts in German lecture speech.

Whisper output is punctuated, so `?` is a strong signal; implicit prompts ("Überlegen Sie mal …", "Nennen Sie …")
and direct address of the user (configurable call names) are detected too. Organisational and rhetorical questions
are filtered.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..text import sentences, tokens

INTERROGATIVES = ("wer", "wem", "wen", "wessen", "was", "wann", "wo", "wohin", "woher", "warum", "weshalb", "wieso",
                  "wie", "welche", "welcher", "welches", "welchen", "wozu", "womit", "wofür", "worauf", "woraus",
                  "inwiefern", "weswegen")
AUDIENCE = re.compile(
    r"^(?:und\s+)?(?:wer|kann|könnte|weiß|wissen|kennt|kennen|hat|haben)\s+(?:mir\s+)?(?:jemand|einer|eine|sie|ihr)\b",
    re.I)
IMPLICIT = re.compile(
    r"\b(überlegen sie (?:mal|bitte|kurz)?|was meinen sie|was denken sie|was glauben sie|nennen sie|erklären sie|"
    r"begründen sie|prüfen sie|ordnen sie|wer möchte|wer traut sich|ihre meinung|was würden sie|"
    r"meldet sich jemand|kommen sie drauf|na,? wer)\b", re.I)
ORGANISATIONAL = re.compile(
    r"\b(hören sie mich|können sie mich|alle da|sind alle|haben sie (?:noch )?fragen|gibt es (?:noch )?fragen|"
    r"noch fragen|verstanden\?|okay\?|alles klar\?|ist das (?:so )?klar|sieht man das|können sie das lesen|"
    r"machen wir (?:eine )?pause|wo waren wir|ist das laut genug|mikro)\b", re.I)
RHETORICAL_ANSWER = re.compile(r"^(weil|ganz einfach|die antwort|nämlich|richtig,|genau,|ja,|nein,)", re.I)


@dataclass
class DetectedQuestion:
    text: str
    kind: str  # direct | implicit | addressed
    score: float
    addressed_to_user: bool = False


def _is_question(sent: str) -> tuple[bool, str]:
    s = sent.strip()
    first = s.split(" ", 1)[0].lower().strip("„\"(,") if s else ""
    if s.endswith("?"):
        return True, "direct"
    if IMPLICIT.search(s):
        return True, "implicit"
    if AUDIENCE.search(s):
        return True, "direct"
    if first in INTERROGATIVES and len(s.split()) >= 4 and not s.endswith("."):
        return True, "direct"
    return False, ""


def detect(text: str, call_names: list[str] | None = None, min_score: float = 0.5) -> list[DetectedQuestion]:
    sents = sentences(text)
    out: list[DetectedQuestion] = []
    names = [n.lower() for n in (call_names or []) if n.strip()]
    for i, s in enumerate(sents):
        is_q, kind = _is_question(s)
        addressed = any(n in s.lower() for n in names)
        if not is_q and not (addressed and len(s.split()) > 3):
            continue
        if ORGANISATIONAL.search(s):
            continue
        content = tokens(s)
        score = 0.55 + min(0.3, 0.05 * len(content))
        if kind == "implicit":
            score -= 0.05
        nxt = sents[i + 1] if i + 1 < len(sents) else ""
        if nxt and RHETORICAL_ANSWER.match(nxt):
            score -= 0.35  # lecturer answers immediately → rhetorical
        if len(content) < 2:
            score -= 0.25  # "Und?" / "Warum?" alone – needs context, manual button covers it
        if addressed:
            score, kind = max(score, 0.9), "addressed"
        if score >= min_score:
            out.append(DetectedQuestion(text=s, kind=kind or "addressed", score=round(min(score, 0.99), 2),
                                        addressed_to_user=addressed))
    return out
