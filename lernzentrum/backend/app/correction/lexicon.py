"""Law-abbreviation lexicon for transcript correction.

* Curated core set with canonical spelling and the valid section range (from the official texts on
  gesetze-im-internet.de; upper bound of the numbering, letter suffixes like § 15a are accepted).
* Exact section sets: when a whole law was loaded into the `statutes` table (statute finder), the real list of
  norms replaces the range check.
* Official list of all abbreviations from gesetze-im-internet.de/gii-toc.xml (cached) – used only to recognise a
  token as a *valid* abbreviation (never as a fuzzy correction target, to keep precision high).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import utcnow
from ..models import CacheEntry, Statute


@dataclass(frozen=True)
class Law:
    abbr: str
    title: str
    first: int
    last: int
    unit: str = "§"  # "Art." for GG / EGBGB, "Abschn." for UStAE (no range check)


CORE: dict[str, Law] = {law.abbr.lower(): law for law in [
    Law("BGB", "Bürgerliches Gesetzbuch", 1, 2385),
    Law("EGBGB", "Einführungsgesetz zum BGB", 1, 250, "Art."),
    Law("HGB", "Handelsgesetzbuch", 1, 619),
    Law("AO", "Abgabenordnung", 1, 415),
    Law("EStG", "Einkommensteuergesetz", 1, 99),
    Law("EStDV", "Einkommensteuer-Durchführungsverordnung", 1, 84),
    Law("KStG", "Körperschaftsteuergesetz", 1, 41),
    Law("UStG", "Umsatzsteuergesetz", 1, 29),
    Law("UStDV", "Umsatzsteuer-Durchführungsverordnung", 1, 75),
    Law("UStAE", "Umsatzsteuer-Anwendungserlass", 0, 0, "Abschn."),
    Law("GewStG", "Gewerbesteuergesetz", 1, 37),
    Law("AktG", "Aktiengesetz", 1, 410),
    Law("GmbHG", "GmbH-Gesetz", 1, 88),
    Law("InsO", "Insolvenzordnung", 1, 359),
    Law("ZPO", "Zivilprozessordnung", 1, 1117),
    Law("StGB", "Strafgesetzbuch", 1, 358),
    Law("GG", "Grundgesetz", 1, 146, "Art."),
    Law("BewG", "Bewertungsgesetz", 1, 266),
    Law("ErbStG", "Erbschaftsteuer- und Schenkungsteuergesetz", 1, 39),
    Law("GrEStG", "Grunderwerbsteuergesetz", 1, 23),
    Law("GrStG", "Grundsteuergesetz", 1, 38),
    Law("AStG", "Außensteuergesetz", 1, 22),
    Law("UmwStG", "Umwandlungssteuergesetz", 1, 28),
    Law("FGO", "Finanzgerichtsordnung", 1, 184),
    Law("StBerG", "Steuerberatungsgesetz", 1, 164),
    Law("SolZG", "Solidaritätszuschlaggesetz 1995", 1, 6),
    Law("InvStG", "Investmentsteuergesetz", 1, 57),
]}

# Subject areas: keywords in the module name → laws that are likely there (boost, never a hard filter)
SUBJECTS: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = [
    ("zivilrecht", ("schuld", "sachen", "zivil", "privatrecht", "bürgerlich", "vertrag", "bgb"),
     ("BGB", "EGBGB", "ZPO", "InsO")),
    ("steuerberatung", ("steuerberatung", "berufsrecht"), ("StBerG", "AO")),
    ("steuerrecht", ("steuer", "abgaben", "finanz"),
     ("EStG", "EStDV", "AO", "UStG", "UStDV", "UStAE", "KStG", "GewStG", "BewG", "ErbStG", "GrEStG", "GrStG", "AStG",
      "UmwStG", "FGO", "SolZG", "InvStG")),
    ("rechnungswesen", ("buchführung", "buchfuehrung", "bilanz", "rechnungswesen", "jahresabschluss", "rechnungslegung"),
     ("HGB", "AO", "EStG", "UStG", "AktG", "GmbHG")),
    ("bwl", ("bwl", "betriebswirt", "unternehmen"), ("HGB", "AktG", "GmbHG")),
    ("gesellschaftsrecht", ("gesellschaft", "handelsrecht", "unternehmensrecht"), ("HGB", "AktG", "GmbHG", "UmwStG")),
]


def lookup(token: str) -> Law | None:
    return CORE.get(token.lower().replace(".", "").replace(" ", ""))


def subject_laws(module_name: str) -> set[str]:
    name = (module_name or "").lower()
    laws: set[str] = set()
    for _, keys, ls in SUBJECTS:
        if any(k in name for k in keys):
            laws.update(ls)
            if "steuerberatung" in name:
                break
    return laws


def _norm_number(norm: str) -> int | None:
    m = re.match(r"(\d+)", norm)
    return int(m.group(1)) if m else None


def loaded_sections(db: Session | None, law: str) -> set[str] | None:
    """Exact list of norms if the whole law was loaded from gesetze-im-internet.de (≥ 30 norms), else None."""
    if db is None:
        return None
    n = db.scalar(select(func.count(Statute.id)).where(Statute.law == law.lower(), Statute.demo.is_(False)))
    if not n or n < 30:
        return None
    return {s for s in db.scalars(select(Statute.norm).where(Statute.law == law.lower()))}


def section_exists(law: Law, norm: str, sections: set[str] | None = None) -> bool | None:
    """True/False if we can tell, None if unknown (e.g. UStAE)."""
    if sections is not None:
        return norm.lower() in sections or str(_norm_number(norm)) in sections
    if law.last == 0:
        return None
    n = _norm_number(norm)
    return n is not None and law.first <= n <= law.last


# ---------------------------------------------------------------- official abbreviation list
TOC_KEY = "gii-toc-v1"


def official_slugs(db: Session | None) -> set[str]:
    if db is None:
        return set()
    row = db.get(CacheEntry, TOC_KEY)
    return set(row.value.split(",")) if row else set()


def refresh_official_list(db: Session) -> int:
    """Download gii-toc.xml (all federal laws) and cache the abbreviation slugs. Offline → keeps old list."""
    try:
        r = httpx.get(f"{get_settings().statute_base_url}/gii-toc.xml", timeout=30,
                      headers={"User-Agent": "Lernzentrum/1.0 (statute lexicon)"})
        r.raise_for_status()
    except httpx.HTTPError:
        return len(official_slugs(db))
    slugs = sorted(set(re.findall(r"gesetze-im-internet\.de/([^/<]+)/xml\.zip", r.text)))
    if slugs:
        db.merge(CacheEntry(key=TOC_KEY, value=",".join(slugs), created_at=utcnow()))
        db.flush()
    return len(slugs)
