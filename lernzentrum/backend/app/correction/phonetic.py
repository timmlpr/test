"""German phonetics for ASR correction: Kölner Phonetik, spoken letter names, number words."""
from __future__ import annotations

import re

# ---------------------------------------------------------------- Kölner Phonetik
_KP_SIMPLE = {**dict.fromkeys("AEIJOUY", "0"), "H": "", "B": "1", **dict.fromkeys("FVW", "3"), **dict.fromkeys("GKQ", "4"),
              "L": "5", **dict.fromkeys("MN", "6"), "R": "7", **dict.fromkeys("SZ", "8")}


def koelner(word: str) -> str:
    """Kölner Phonetik (Postel 1969) code of a word."""
    w = word.upper().replace("Ä", "A").replace("Ö", "O").replace("Ü", "U").replace("ß", "S")
    w = re.sub(r"[^A-Z]", "", w)
    codes: list[str] = []
    for i, ch in enumerate(w):
        prev = w[i - 1] if i else ""
        nxt = w[i + 1] if i + 1 < len(w) else ""
        if ch == "P":
            c = "3" if nxt == "H" else "1"
        elif ch in "DT":
            c = "8" if nxt in "CSZ" else "2"
        elif ch == "C":
            if i == 0:
                c = "4" if nxt in "AHKLOQRUX" else "8"
            else:
                c = "8" if prev in "SZ" or nxt not in "AHKOQUX" else "4"
        elif ch == "X":
            c = "8" if prev in "CKQ" else "48"
        else:
            c = _KP_SIMPLE.get(ch, "")
        codes.append(c)
    out = ""
    for c in "".join(codes):
        if not out or out[-1] != c:
            out += c
    return out[:1] + out[1:].replace("0", "") if out else ""


# ---------------------------------------------------------------- letter names ("Be Ge Be" → BGB)
LETTER_NAMES = {
    "a": "A", "ah": "A", "be": "B", "bee": "B", "ce": "C", "ze": "C", "de": "D", "dee": "D", "e": "E", "eh": "E",
    "ef": "F", "eff": "F", "ge": "G", "gee": "G", "ha": "H", "hah": "H", "i": "I", "ih": "I", "jot": "J", "ka": "K",
    "kah": "K", "el": "L", "ell": "L", "em": "M", "emm": "M", "en": "N", "enn": "N", "o": "O", "oh": "O", "pe": "P",
    "ku": "Q", "er": "R", "es": "S", "ess": "S", "te": "T", "tee": "T", "u": "U", "uh": "U", "vau": "V", "fau": "V",
    "we": "W", "weh": "W", "ix": "X", "ypsilon": "Y", "zet": "Z", "zett": "Z",
}
_NAME_RE = re.compile("(" + "|".join(sorted(LETTER_NAMES, key=len, reverse=True)) + ")", re.I)


def letters_of(token: str) -> str | None:
    """Letters a spoken/typed token stands for: 'B' → B, 'Be' → B, 'BeGeBe' → BGB, 'ST' → ST, 'GmbH' → GMBH.

    Returns None if the token cannot be read as letters."""
    t = token.strip(".-")
    if not t or not t.isalpha():
        return None
    if len(t) == 1:
        return t.upper()
    low = t.lower()
    if low in LETTER_NAMES:
        return LETTER_NAMES[low]
    # compound of letter names, e.g. "BeGeBe", "EsTeGe" – must be capitalised per letter to avoid German words
    parts = re.findall(r"[A-ZÄÖÜ][a-zäöü]*", t)
    if len(parts) >= 2 and "".join(parts) == t and all(p.lower() in LETTER_NAMES for p in parts):
        return "".join(LETTER_NAMES[p.lower()] for p in parts)
    if t.isupper() and len(t) <= 6:
        return t
    if re.fullmatch(r"(GmbH|In|St|Est|Ust|Kst|Inso|Gew|Bew|Erb|Akt|Umw)", t):
        return t.upper()
    return None


# ---------------------------------------------------------------- number words ("vierhundertdreiunddreißig" → 433)
_UNITS = {"null": 0, "ein": 1, "eins": 1, "eine": 1, "einen": 1, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5, "fuenf": 5,
          "sechs": 6, "sieben": 7, "acht": 8, "neun": 9}
_TEENS = {"zehn": 10, "elf": 11, "zwölf": 12, "zwoelf": 12, "dreizehn": 13, "vierzehn": 14, "fünfzehn": 15,
          "sechzehn": 16, "siebzehn": 17, "achtzehn": 18, "neunzehn": 19}
_TENS = {"zwanzig": 20, "dreißig": 30, "dreissig": 30, "vierzig": 40, "fünfzig": 50, "sechzig": 60, "siebzig": 70,
         "achtzig": 80, "neunzig": 90}


def _below_100(w: str) -> int | None:
    if w in _UNITS:
        return _UNITS[w]
    if w in _TEENS:
        return _TEENS[w]
    if w in _TENS:
        return _TENS[w]
    m = re.fullmatch(r"(.+?)und(.+)", w)
    if m and m.group(2) in _TENS and m.group(1) in _UNITS:
        return _UNITS[m.group(1)] + _TENS[m.group(2)]
    return None


def _below_1000(w: str) -> int | None:
    if not w:
        return 0
    if "hundert" in w:
        head, _, rest = w.partition("hundert")
        h = 1 if head in ("", "ein") else _UNITS.get(head)
        r = _below_100(rest) if rest else 0
        return None if h is None or r is None else h * 100 + r
    return _below_100(w)


def parse_number_word(word: str) -> int | None:
    """German cardinal number word (1 … 9999) → int. Ordinal endings (erste/ersten) are accepted."""
    w = word.lower().strip(".")
    if w in ("erste", "ersten", "erster"):
        return 1
    if w in ("zweite", "zweiten"):
        return 2
    if w in ("dritte", "dritten"):
        return 3
    w = re.sub(r"(ste|sten|ter|ten|te)$", "", w) if not w.endswith(("zehn", "zig", "ßig", "ssig")) else w
    if "tausend" in w:
        head, _, rest = w.partition("tausend")
        t = 1 if head in ("", "ein") else _below_1000(head)
        r = _below_1000(rest)
        return None if not t or r is None else t * 1000 + r
    v = _below_1000(w)
    return v if v else None
