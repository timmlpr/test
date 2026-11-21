"""Transcript correction engine (layers 2 + 3 + 5): citation grammar, law candidates, existence check,
context scoring, confidence policy. Pure functions, no DB, no network."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from rapidfuzz.distance import Levenshtein

from .lexicon import CORE, Law, lookup, section_exists
from .phonetic import koelner, letters_of, parse_number_word

NBSP = " "
_DATA = json.loads((Path(__file__).parent / "confusions.json").read_text(encoding="utf-8"))
CONF_LAWS: dict[str, list] = _DATA["laws"]
CONF_TERMS: dict[str, list] = _DATA["terms"]
VOCAB = {v.lower(): v for v in _DATA["vocabulary"]}

ANCHOR = re.compile(r"(§§|§|\b[Pp]aragra(?:ph|f)(?:en)?\b)\s*")
NUM = re.compile(r"(\d{1,4})([a-z])?(?![\w])")
WORD = re.compile(r"([A-Za-zÄÖÜäöüß]+)")
QUALS = [("Abs.", r"Absatz|Abs\.?"), ("S.", r"Satz|S\."), ("Nr.", r"Nummer|Ziffer|Nr\.?"),
         ("lit.", r"Buchstabe|lit\.?"), ("Alt.", r"Alternative|Alt\.?"), ("Hs.", r"Halbsatz|Hs\.?")]


@dataclass
class Ctx:
    module_name: str = ""
    subject_laws: set[str] = field(default_factory=set)
    recent_laws: set[str] = field(default_factory=set)
    material_keys: set[str] = field(default_factory=set)  # e.g. "bgb:433" found in module materials
    user_rules: dict[str, str] = field(default_factory=dict)  # upper-case slot/phrase → replacement
    auto: int = 90
    mark: int = 60


def _status(conf: int, ctx: Ctx) -> str:
    return "applied" if conf >= ctx.auto else "check" if conf >= ctx.mark else "unclear"


def _num_at(text: str, pos: int):
    m = NUM.match(text, pos)
    if m:
        return m.group(1) + (m.group(2) or ""), m.end()
    m = WORD.match(text, pos)
    if m and (n := parse_number_word(m.group(1))):
        return str(n), m.end()
    return None, pos


def _slot_tokens(text: str, pos: int) -> list[tuple[int, int, str]]:
    toks, i = [], pos
    m = re.compile(r"\s+(des|der)\b").match(text, i)
    if m:
        i = m.end()
    tok_re = re.compile(r"([ \t\-]*)([A-Za-zÄÖÜäöüß]+)")
    while len(toks) < 4:
        m = tok_re.match(text, i)
        if not m or (toks and not m.group(1) and text[i - 1:i] != "."):
            break
        if not toks and not m.group(1) and i > 0 and text[i - 1].isdigit() is False and text[i - 1] != ".":
            break
        toks.append((m.start(2), m.end(2), m.group(2)))
        i = m.end()
        if re.match(r"\.[A-Za-z]", text[i:i + 2]):
            i += 1
    return toks


def _candidates(words: list[str], spelled: bool, ctx: Ctx) -> list[tuple[Law, float, str]]:
    raw = re.sub(r"[\s.\-]", "", " ".join(words)).upper()
    out: list[tuple[Law, float, str]] = []
    if raw in ctx.user_rules and (law := lookup(ctx.user_rules[raw])):
        out.append((law, 0.97, "eigene Regel"))
    letters = [letters_of(w) for w in words]
    if all(letters) and spelled:
        joined = "".join(letters)
        if law := lookup(joined):
            out.append((law, 0.93, f"buchstabiert „{' '.join(words)}“"))
        for abbr, w in CONF_LAWS.get(joined, []):
            out.append((lookup(abbr), 0.8 * w, f"typischer Hörfehler „{' '.join(words)}“"))
    for abbr, w in CONF_LAWS.get(raw, []):
        out.append((lookup(abbr), 0.8 * w, f"typischer Hörfehler „{' '.join(words)}“"))
    if not out and all(letters) and (spelled or words[0].isupper()) and 2 <= len("".join(letters)) <= 6:
        joined = "".join(letters)
        for law in CORE.values():
            d = Levenshtein.distance(joined, law.abbr.upper())
            limit = 2 if (len(words) > 1 or len(joined) > 3) else 1
            if koelner(joined) == koelner(law.abbr) and abs(len(joined) - len(law.abbr)) <= 1:
                out.append((law, 0.6, "ähnlicher Klang"))
            elif d <= limit:
                out.append((law, 0.55 if d == 1 else 0.4, f"ähnliche Schreibweise (Abstand {d})"))
    return out


def correct(text: str, ctx: Ctx | None = None, sections=None) -> tuple[str, list[dict]]:
    """Return (corrected_text, edits). Edits reference spans in the ORIGINAL text; original is never modified."""
    ctx = ctx or Ctx()
    edits: list[dict] = []
    taken: list[tuple[int, int]] = []
    for am in ANCHOR.finditer(text):
        norm, pos = _num_at(text, am.end())
        if not norm:
            continue
        head = ("§§" if am.group(1) in ("§§", "Paragraphen", "Paragrafen") else "§") + NBSP + norm
        while True:
            matched = False
            for label, rx in QUALS:
                m = re.compile(rf"\s*(?:{rx})\s*").match(text, pos)
                if not m:
                    continue
                if label == "lit.":
                    v = re.compile(r"([a-z])\b").match(text, m.end())
                    val = v.group(1) if v else None
                else:
                    val, end = _num_at(text, m.end())
                    v = type("M", (), {"end": lambda s, e=end: e})() if val else None
                if val:
                    head += f" {label} {val}"
                    pos = v.end()
                    matched = True
                    break
            if not matched:
                break
        orig_head = text[am.start():pos]
        if orig_head.replace(NBSP, " ") != head.replace(NBSP, " "):
            edits.append({"start": am.start(), "end": pos, "from": orig_head, "to": head, "kind": "norm",
                          "layer": "rule", "confidence": 99, "reason": "Zitierweise vereinheitlicht"})
        taken.append((am.start(), pos))
        toks = _slot_tokens(text, pos)
        for k in range(len(toks), 0, -1):
            sub = toks[:k]
            words = [t[2] for t in sub]
            s0, s1 = sub[0][0], sub[-1][1]
            if k == 1 and (law := lookup(words[0])):
                n = int(re.match(r"\d+", norm).group())
                if section_exists(law, norm, sections(law.abbr) if sections else None) is False:
                    edits.append({"start": am.start(), "end": s1, "from": text[am.start():s1], "to": None,
                                  "kind": "law", "layer": "rule", "confidence": 0, "candidates": [],
                                  "reason": f"§ {n} existiert im {law.abbr} nicht"})
                elif words[0] != law.abbr:
                    edits.append({"start": s0, "end": s1, "from": words[0], "to": law.abbr, "kind": "law",
                                  "layer": "rule", "confidence": 97, "reason": "Schreibweise des Gesetzes"})
                taken.append((s0, s1))
                break
            spelled = k > 1 or (letters_of(words[0]) or "") not in ("", words[0].upper())
            if k == 1 and words[0].islower():
                break
            cands = _candidates(words, spelled, ctx)
            if not cands:
                continue
            scored = []
            for law, base, why in cands:
                ex = section_exists(law, norm, sections(law.abbr) if sections else None)
                if ex is False:
                    continue
                s = base * 100 + (8 if ex else 0)
                reasons = [why]
                if ex:
                    reasons.append(f"§ {norm} steht im {law.abbr}")
                if law.abbr in ctx.subject_laws:
                    s += 6
                    reasons.append(f"Modul {ctx.module_name}")
                if law.abbr in ctx.recent_laws:
                    s += 5
                    reasons.append("zuvor in der Vorlesung genannt")
                if f"{law.abbr.lower()}:{norm.lower()}" in ctx.material_keys:
                    s += 8
                    reasons.append("in deinen Unterlagen zitiert")
                if base < 0.7:
                    s = min(s, 83)
                if ex is None:
                    s = min(s, 85)
                scored.append((min(99, round(s)), law.abbr, ", ".join(reasons)))
            best: dict[str, tuple] = {}
            for sc in scored:
                if sc[1] not in best or sc[0] > best[sc[1]][0]:
                    best[sc[1]] = sc
            ranked = sorted(best.values(), reverse=True)
            if ranked and len(ranked) > 1 and ranked[0][0] - ranked[1][0] < 12:
                ranked[0] = (ranked[0][0] - (12 - (ranked[0][0] - ranked[1][0])),) + ranked[0][1:]
            top = ranked[0] if ranked else None
            edits.append({"start": s0, "end": s1, "from": text[s0:s1], "to": top[1] if top else None, "kind": "law",
                          "layer": "context", "confidence": top[0] if top else 0,
                          "reason": top[2] if top else "kein Gesetz mit diesem Paragraphen gefunden",
                          "candidates": [{"to": r[1], "confidence": r[0], "reason": r[2]} for r in ranked[:3]]})
            taken.append((s0, s1))
            break
    # domain terms: explicit confusions, user rules, split compounds
    low = text.lower()
    rules = {**{k: [v, True] for k, v in ctx.user_rules.items() if " " in k or len(k) > 6}}
    for phrase, (term, safe) in list(CONF_TERMS.items()) + [(k.lower(), v) for k, v in rules.items()]:
        for m in re.finditer(rf"(?<!\w){re.escape(phrase)}(?!\w)", low):
            if any(a < m.end() and m.start() < b for a, b in taken):
                continue
            conf = 93 if safe else 55
            edits.append({"start": m.start(), "end": m.end(), "from": text[m.start():m.end()], "to": term,
                          "kind": "term", "layer": "rule", "confidence": conf, "reason": "Fachbegriff"})
            taken.append((m.start(), m.end()))
    for m in re.finditer(r"\b([A-ZÄÖÜ][a-zäöüß]+)[ \-]([A-ZÄÖÜ][a-zäöüß]+)\b", text):
        merged = m.group(1) + m.group(2).lower()
        if merged.lower() in VOCAB and not any(a < m.end() and m.start() < b for a, b in taken):
            edits.append({"start": m.start(), "end": m.end(), "from": m.group(0), "to": VOCAB[merged.lower()],
                          "kind": "term", "layer": "rule", "confidence": 91, "reason": "getrenntes Wort zusammengeführt"})
            taken.append((m.start(), m.end()))
    for i, e in enumerate(sorted(edits, key=lambda e: e["start"])):
        e["id"] = f"e{i}"
        e["status"] = _status(e["confidence"], ctx) if e["to"] else "unclear"
    edits.sort(key=lambda e: e["start"])
    return apply_edits(text, edits), edits


def apply_edits(original: str, edits: list[dict]) -> str:
    out, last = [], 0
    for e in sorted(edits, key=lambda e: e["start"]):
        if e["status"] in ("applied", "check", "accepted") and e.get("to") and e["start"] >= last:
            out.append(original[last:e["start"]])
            out.append(e["to"])
            last = e["end"]
    out.append(original[last:])
    return "".join(out)
