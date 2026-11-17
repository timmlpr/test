"""Hard-limit enforcement (H1–H6). Used by every free-text entry point: assistant, voice, scam text,
identifier creation. Detection is deliberately conservative: when in doubt, refuse politely.

These checks are server-side and cannot be switched off by flags, admins or tests.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# German licence plates: 1–3 letter district, optional separator, 1–2 letters, 1–4 digits, optional E/H.
PLATE_RE = re.compile(r"\b[A-ZÄÖÜ]{1,3}[\s\-:]{0,2}[A-Z]{1,2}[\s\-]?\d{1,4}[EH]?\b")
PLATE_WORDS = ("kennzeichen", "nummernschild", "fahrzeughalter", "halterabfrage", "halter ermitteln",
               "license plate", "licence plate", "number plate", "vehicle owner", "kfz-halter", "wem gehört das auto",
               "wem gehoert das auto", "autonummer")
FACE_WORDS = ("gesichtserkennung", "gesicht erkennen", "face recognition", "facial recognition", "wer ist auf dem foto",
              "wer ist auf dem bild", "person auf dem foto identifizieren", "person auf dem bild identifizieren",
              "identify this person", "who is this person", "who is in this photo", "pimeyes", "facecheck",
              "biometri", "gesicht abgleichen", "gesicht suchen", "find this face")
SPY_WORDS = ("spyware", "stalkerware", "handy orten", "handy überwachen", "handy ueberwachen", "standort meiner",
             "standort meines", "standort von meiner", "standort von meinem", "mitlesen", "chats lesen", "whatsapp lesen",
             "e-mails von", "emails von", "mails meines", "mails meiner", "account hacken", "konto hacken",
             "passwort von", "passwort meiner", "passwort meines", "überwachen", "ueberwachen", "ausspionieren",
             "spionieren", "track my", "spy on", "read his messages", "read her messages", "hack into", "keylogger")
BYPASS_WORDS = ("captcha umgehen", "captcha lösen", "paywall umgehen", "robots.txt ignorieren", "login umgehen",
                "bypass captcha", "bypass paywall", "ignore robots", "scrape linkedin", "agb umgehen")
PROFILE_WORDS = ("dossier", "alles über", "alles ueber", "alles zu der person", "recherchiere über", "recherchiere ueber",
                 "recherchier", "finde heraus wer", "wo wohnt", "adresse von", "telefonnummer von", "handynummer von",
                 "arbeitgeber von", "profil über", "profil von", "infos über", "infos ueber", "informationen über",
                 "informationen ueber", "find everything about", "background check", "hintergrundcheck",
                 "who is", "wer ist", "suche nach person", "person suchen", "personensuche", "beziehung zwischen",
                 "mit wem ist", "verwandt mit", "kennen sich", "freundeskreis von", "relationship between")
THIRD_PARTY_HINTS = ("nachbar", "kollege", "kollegin", "chef", "chefin", "ex-freund", "ex-freundin", "meine ex", "mein ex",
                     "freundin", "freund ", "partner", "partnerin", "frau ", "mann ", "lehrer", "vermieter", "mieter",
                     "jemand", "jemanden", "einer person", "einen menschen", "dieser person", "diese person", "andere person",
                     "fremde", "fremden", "someone", "another person", "my neighbour", "my neighbor", "my boss", "my ex")
SELF_HINTS = ("mich", "meine daten", "mein name", "meinen namen", "über mich", "ueber mich", "my own", "about me", "myself")
NAME_PAIR_RE = re.compile(r"\b([A-ZÄÖÜ][a-zäöüß]+)\s+([A-ZÄÖÜ][a-zäöüß]+(?:-[A-ZÄÖÜ][a-zäöüß]+)?)\b")


@dataclass(frozen=True)
class Refusal:
    category: str  # third_party | plate | face | spying | bypass
    message_de: str
    message_en: str

    def as_dict(self) -> dict:
        return {"refused": True, "category": self.category, "message_de": self.message_de, "message_en": self.message_en}


_MSG = {
    "third_party": ("Das kann ich nicht machen. Fadeprint hilft nur bei deinen eigenen Daten – Recherchen über andere "
                    "Menschen sind ausgeschlossen. Wenn du selbst betroffen bist, prüfe gern deine eigenen Angaben.",
                    "I can't do that. Fadeprint only helps with your own data – researching other people is not possible."),
    "plate": ("Kennzeichen- oder Halterabfragen sind bei Fadeprint ausgeschlossen. Für Unfälle oder Anzeigen ist die "
              "Polizei bzw. das Zentrale Fahrzeugregister zuständig.",
              "Licence plate or vehicle-owner lookups are not available in Fadeprint."),
    "face": ("Gesichtserkennung und das Identifizieren von Personen auf Fotos bietet Fadeprint bewusst nicht an. "
             "Du kannst aber prüfen, wo deine eigenen Bilder auftauchen.",
             "Face recognition or identifying people in photos is deliberately not offered."),
    "spying": ("Das Überwachen fremder Geräte, Konten oder Standorte ist ausgeschlossen. Wenn du dich selbst bedroht fühlst, "
               "helfen z. B. der Weiße Ring (116 006) oder die Polizei.",
               "Monitoring other people's devices, accounts or locations is not possible."),
    "bypass": ("Fadeprint nutzt nur offizielle Schnittstellen und erlaubte Quellen. Logins, Captchas oder Paywalls "
               "werden nicht umgangen.",
               "Fadeprint only uses official APIs and permitted sources; it does not bypass logins, captchas or paywalls."),
}


def _refuse(cat: str) -> Refusal:
    de, en = _MSG[cat]
    return Refusal(cat, de, en)


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKC", text).lower()


def _foreign_names(text: str, own_names: list[str]) -> list[str]:
    own = {_norm(n) for n in own_names}
    own_tokens = {t for n in own for t in n.split()}
    out = []
    for m in NAME_PAIR_RE.finditer(text):
        pair = _norm(f"{m.group(1)} {m.group(2)}")
        first, last = pair.split(" ", 1)
        if pair in own or (first in own_tokens and last in own_tokens):
            continue
        # skip sentence-initial common words ("Was Ist", "Wie Kann") – require neither token be a stop word
        if first in _STOP or last in _STOP:
            continue
        out.append(pair)
    return out


_STOP = {"was", "wie", "wer", "wo", "ist", "mein", "meine", "die", "der", "das", "ich", "bitte", "kannst", "kann", "welche",
         "welcher", "zeige", "zeig", "hallo", "danke", "google", "instagram", "facebook", "tiktok", "linkedin", "what",
         "how", "my", "the", "please", "deutsche", "bank", "post", "telekom", "amazon", "netflix", "dsgvo", "art"}


def check_text(text: str, own_names: list[str] | None = None) -> Refusal | None:
    """Return a Refusal if the text asks for something outside the hard limits."""
    t = _norm(text)
    own_names = own_names or []
    if any(w in t for w in FACE_WORDS):
        return _refuse("face")
    if any(w in t for w in PLATE_WORDS) or (PLATE_RE.search(text) and any(k in t for k in ("auto", "wagen", "fahrzeug", "car", "wem", "halter", "owner"))):
        return _refuse("plate")
    if any(w in t for w in BYPASS_WORDS):
        return _refuse("bypass")
    if any(w in t for w in SPY_WORDS):
        return _refuse("spying")
    profile_intent = any(w in t for w in PROFILE_WORDS)
    third_party = any(w in t for w in THIRD_PARTY_HINTS)
    foreign = _foreign_names(text, own_names)
    self_ref = any(w in t for w in SELF_HINTS)
    if profile_intent and (third_party or foreign) and not (self_ref and not foreign and not third_party):
        return _refuse("third_party")
    if profile_intent and not self_ref and not own_names:
        return _refuse("third_party")
    if foreign and (profile_intent or third_party):
        return _refuse("third_party")
    return None


def is_plate_like(value: str) -> bool:
    return bool(PLATE_RE.fullmatch(value.strip().upper()))
