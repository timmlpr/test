"""M-06 scam rule engine. Pure functions over text/URL features → traffic light + plain-language reasons."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>\"')]+", re.I)
SHORTENERS = {"bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "is.gd", "buff.ly", "cutt.ly", "rb.gy", "t.ly", "shorturl.at", "s.id"}
RISKY_TLDS = {"zip", "mov", "top", "xyz", "click", "country", "gq", "tk", "ml", "cf", "ga", "work", "rest", "cam", "icu", "buzz",
              "support", "live", "sbs", "cfd", "lol"}
BRANDS = {"paypal": "paypal.com", "amazon": "amazon.de", "sparkasse": "sparkasse.de", "dhl": "dhl.de", "postbank": "postbank.de",
          "volksbank": "volksbank.de", "commerzbank": "commerzbank.de", "netflix": "netflix.com", "apple": "apple.com",
          "microsoft": "microsoft.com", "telekom": "telekom.de", "vodafone": "vodafone.de", "ing": "ing.de", "dkb": "dkb.de",
          "hermes": "myhermes.de", "elster": "elster.de", "zoll": "zoll.de", "ebay": "ebay.de", "whatsapp": "whatsapp.com",
          "n26": "n26.com", "deutschebank": "deutsche-bank.de", "klarna": "klarna.com"}
SIGNALS = {
    "urgency": (r"\b(sofort|umgehend|innerhalb von (24|48) stunden|letzte (mahnung|warnung|erinnerung)|heute noch|"
                r"läuft (heute )?ab|gesperrt|eingeschränkt|deaktiviert|dringend|urgent|immediately|suspended)\b", 2),
    "credentials": (r"\b(passwort|kennwort|pin|tan|zugangsdaten|anmeldedaten|bestätigen sie ihre (daten|identität)|"
                    r"verifizieren sie|login|sicherheitscode|password|verify your account)\b", 3),
    "payment": (r"\b(gutschein(karte)?|geschenkkarte|bitcoin|krypto|western union|zollgebühr|nachgebühr|gebühr von|"
                r"überweisen sie|paysafecard|apple[- ]?karte|google play karte)\b", 3),
    "prize": (r"\b(gewonnen|gewinner|gratis|kostenlos erhalten|sie wurden ausgewählt|erbschaft|lottery|winner)\b", 2),
    "generic_greeting": (r"\b(sehr geehrter kunde|sehr geehrte kundin|lieber kunde|dear customer|hallo kunde)\b", 1),
    "family_trick": (r"\b(hallo mama|hallo papa|hi mama|hi papa|meine neue nummer|mein handy ist kaputt|neue handynummer)\b", 3),
    "package": (r"\b(paket|sendung|zustellung).{0,40}(nicht zugestellt|zurückgehalten|adresse (bestätigen|aktualisieren))\b", 2),
}


@dataclass
class ScamResult:
    score: int
    light: str
    reasons: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)


def extract_urls(text: str) -> list[str]:
    out = []
    for u in URL_RE.findall(text or ""):
        u = u.rstrip(".,;:!?")
        out.append(u if u.lower().startswith("http") else f"http://{u}")
    return list(dict.fromkeys(out))[:10]


def registrable(host: str) -> str:
    parts = host.lower().strip(".").split(".")
    if len(parts) >= 3 and parts[-2] in {"co", "com", "org", "net", "gov"} and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def url_signals(url: str) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    p = urlparse(url)
    host = (p.hostname or "").lower()
    if not host:
        return [("url_invalid", 2)]
    if p.scheme == "http":
        out.append(("no_https", 1))
    if re.fullmatch(r"[\d.]+", host) or ":" in host:
        out.append(("ip_address_url", 3))
    if "xn--" in host:
        out.append(("punycode", 3))
    if "@" in (p.netloc or ""):
        out.append(("at_in_url", 3))
    if host in SHORTENERS:
        out.append(("shortener", 2))
    tld = host.rsplit(".", 1)[-1]
    if tld in RISKY_TLDS:
        out.append(("risky_tld", 2))
    if host.count(".") >= 4:
        out.append(("many_subdomains", 1))
    if host.count("-") >= 3:
        out.append(("many_hyphens", 1))
    reg = registrable(host)
    for brand, official in BRANDS.items():
        if brand in host.replace("-", "").replace(".", "") and registrable(official) != reg and not reg.startswith(brand + "."):
            out.append(("brand_mismatch", 4))
            break
    return out


def text_signals(text: str) -> list[tuple[str, int]]:
    t = (text or "").lower()
    return [(name, w) for name, (pat, w) in SIGNALS.items() if re.search(pat, t)]


def evaluate(text: str = "", url: str | None = None, extra: list[tuple[str, int]] | None = None) -> ScamResult:
    urls = ([url] if url else []) + extract_urls(text)
    sig = text_signals(text) + [s for u in urls for s in url_signals(u)] + (extra or [])
    names = list(dict.fromkeys(n for n, _ in sig))
    score = min(100, sum(w for _, w in {n: w for n, w in sig}.items()) * 8)
    if any(n in ("blocklisted",) for n in names):
        score = 100
    light = "red" if score >= 40 else "yellow" if score >= 16 else "green"
    return ScamResult(score=score, light=light, reasons=names, urls=urls)


REASON_TEXT_DE = {
    "urgency": "Die Nachricht macht Zeitdruck. Seriöse Firmen setzen selten so kurze Fristen.",
    "credentials": "Es wird nach Passwort, PIN oder Zugangsdaten gefragt. Banken und Shops fragen das nie per Nachricht ab.",
    "payment": "Es soll mit Gutscheinkarten, Krypto oder einer ungewöhnlichen Gebühr bezahlt werden.",
    "prize": "Ein unerwarteter Gewinn wird versprochen.",
    "generic_greeting": "Die Anrede ist unpersönlich („Sehr geehrter Kunde“).",
    "family_trick": "Typische Masche: Angeblich ein Familienmitglied mit neuer Nummer.",
    "package": "Typische Paket-Masche: Zustellproblem plus Link.",
    "no_https": "Der Link ist nicht verschlüsselt (http statt https).",
    "ip_address_url": "Der Link führt auf eine nackte IP-Adresse statt auf einen Namen.",
    "punycode": "Die Adresse nutzt Sonderzeichen, die bekannte Namen nachahmen können.",
    "at_in_url": "Im Link steckt ein @-Zeichen – das kann das echte Ziel verschleiern.",
    "shortener": "Der Link ist gekürzt; das echte Ziel ist nicht sichtbar.",
    "risky_tld": "Die Endung der Adresse wird häufig für Betrug genutzt.",
    "many_subdomains": "Die Adresse ist ungewöhnlich verschachtelt.",
    "many_hyphens": "Die Adresse enthält auffällig viele Bindestriche.",
    "brand_mismatch": "Ein bekannter Markenname steckt in der Adresse, die Seite gehört aber nicht zur Marke.",
    "url_invalid": "Der Link ist ungültig.",
    "young_domain": "Die Domain ist sehr neu (jünger als 30 Tage).",
    "fairly_new_domain": "Die Domain ist noch recht neu (jünger als 6 Monate).",
    "no_imprint": "Für einen Shop fehlt ein Impressum.",
    "blocklisted": "Die Adresse steht auf einer Warnliste für Betrug oder Schadsoftware.",
    "no_dns": "Die Domain existiert nicht oder ist nicht erreichbar.",
}
SUMMARY_DE = {"green": "Keine typischen Warnzeichen gefunden. Bleib trotzdem aufmerksam.",
              "yellow": "Einige Warnzeichen. Prüfe den Absender auf einem anderen Weg, bevor du etwas tust.",
              "red": "Starke Warnzeichen. Klicke nicht, gib nichts ein und lösche die Nachricht."}
