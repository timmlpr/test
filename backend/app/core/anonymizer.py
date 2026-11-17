"""Anonymise text before it goes to any AI provider; re-insert locally afterwards.

Placeholders look like ⟦EMAIL_1⟧ so they survive model output unchanged.
"""
from __future__ import annotations

import re

PATTERNS: list[tuple[str, re.Pattern]] = [
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,7}(?:\s?[A-Z0-9]{1,3})?\b")),
    ("URL", re.compile(r"https?://[^\s<>\"']+")),
    ("PHONE", re.compile(r"(?<![\w])(?:\+|00)?\d[\d\s/().-]{6,}\d")),
    ("ADDRESS", re.compile(r"\b[A-ZÄÖÜ][a-zäöüß]+(?:straße|strasse|weg|allee|platz|gasse|ring|damm|ufer)\s+\d+[a-z]?\b", re.I)),
    ("ZIP", re.compile(r"\b\d{5}\s+[A-ZÄÖÜ][a-zäöüß]+(?:\s[A-ZÄÖÜ][a-zäöüß]+)?\b")),
    ("DATE", re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\b")),
]
NAME_RE = re.compile(r"\b([A-ZÄÖÜ][a-zäöüß]{2,})\s+([A-ZÄÖÜ][a-zäöüß]{2,})\b")
_NOT_NAMES = {"Sehr", "Geehrte", "Geehrter", "Damen", "Herren", "Ihre", "Ihr", "Mit", "Freundlichen", "Grüßen", "Liebe",
              "Lieber", "Bitte", "Ihnen", "Deutsche", "Bank", "Post", "Konto", "Paket", "Kunde", "Kundin", "Hallo",
              "Dein", "Deine", "Wir", "Sie", "Der", "Die", "Das", "Ein", "Eine", "Amazon", "Paypal", "Sparkasse", "Volksbank",
              "Apple", "Google", "Microsoft", "Netflix", "Telekom", "Vodafone", "Dhl", "Hermes", "Ups", "Dpd"}


def anonymize(text: str, known_names: list[str] | None = None) -> tuple[str, dict[str, str]]:
    mapping: dict[str, str] = {}
    counters: dict[str, int] = {}

    def sub(kind: str, value: str) -> str:
        for k, v in mapping.items():
            if v == value:
                return k
        counters[kind] = counters.get(kind, 0) + 1
        ph = f"⟦{kind}_{counters[kind]}⟧"
        mapping[ph] = value
        return ph

    out = text
    for name in sorted(known_names or [], key=len, reverse=True):
        if name.strip():
            out = re.sub(re.escape(name), lambda m: sub("NAME", m.group(0)), out, flags=re.I)
    for kind, pat in PATTERNS:
        out = pat.sub(lambda m, k=kind: sub(k, m.group(0)), out)

    def name_sub(m: re.Match) -> str:
        if m.group(1) in _NOT_NAMES or m.group(2) in _NOT_NAMES:
            return m.group(0)
        return sub("NAME", m.group(0))

    out = NAME_RE.sub(name_sub, out)
    return out, mapping


def deanonymize(text: str, mapping: dict[str, str]) -> str:
    for ph, value in mapping.items():
        text = text.replace(ph, value)
    return text
