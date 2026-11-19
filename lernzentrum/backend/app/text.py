"""German text utilities: normalisation, tokens, light stemming, statute references, sentence split, simhash,
local hashed n-gram vectors."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

import numpy as np

STOP = set("""
aber alle allem allen aller alles als also am an ander andere anderem anderen anderer anderes anderm andern anderr
anders auch auf aus bei bin bis bist da damit dann das dass daß dein deine deinem deinen deiner dem den denn der des
dessen deshalb die dies diese diesem diesen dieser dieses doch dort du durch ein eine einem einen einer eines einig
einige einigem einigen einiger einiges einmal er es etwas euer eure für gegen gewesen hab habe haben hat hatte hatten
hier hin hinter ich ihm ihn ihnen ihr ihre ihrem ihren ihrer ihres im in indem ins ist jede jedem jeden jeder jedes
jene jenem jenen jener jenes jetzt kann kein keine keinem keinen keiner keines können könnte machen man manche
manchem manchen mancher manches mein meine meinem meinen meiner meines mich mir mit muss musste nach nicht nichts
noch nun nur ob oder ohne sehr sein seine seinem seinen seiner seines selbst sich sie sind so solche solchem solchen
solcher solches soll sollte sondern sonst über um und uns unser unsere unter viel vom von vor während war waren warst
was weg weil weiter welche welchem welchen welcher welches wenn werde werden wie wieder will wir wird wirst wo wollen
wollte würde würden zu zum zur zwar zwischen ja nein mal schon eben halt also okay gut genau sagen sagt gesagt heute
""".split())

LAWS = {
    "bgb": "BGB", "hgb": "HGB", "estg": "EStG", "ao": "AO", "ustg": "UStG", "kstg": "KStG", "gewstg": "GewStG",
    "gg": "GG", "aktg": "AktG", "gmbhg": "GmbHG", "stberg": "StBerG", "bewg": "BewG", "erbstg": "ErbStG",
    "estdv": "EStDV", "ustdv": "UStDV", "inso": "InsO", "zpo": "ZPO", "stgb": "StGB", "egbgb": "EGBGB",
    "gwg": "GwG", "fgo": "FGO", "solzg": "SolZG", "grstg": "GrStG", "umwstg": "UmwStG", "astg": "AStG",
}
# gesetze-im-internet.de path slugs where they differ from the lowercase abbreviation
LAW_SLUGS = {"stberg": "stberg", "estdv": "estdv_1955", "ustdv": "ustdv_1980", "solzg": "solzg_1995",
             "umwstg": "umwstg_2006", "grstg": "grstg_1973", "bewg": "bewg", "erbstg": "erbstg_1974",
             "kstg": "kstg_1977", "gewstg": "gewstg", "zpo": "zpo", "inso": "inso", "gwg": "gwg_2017"}

_law_alt = "|".join(sorted((v for v in LAWS.values()), key=len, reverse=True))
STATUTE_RE = re.compile(
    rf"(?:§§?|Paragraph(?:en)?|Paragraf(?:en)?|Art\.?|Artikel)\s*(\d+[a-z]?)"
    rf"(?:\s*(?:Abs\.?|Absatz)\s*(\d+))?(?:\s*(?:S\.?|Satz)\s*(\d+))?(?:\s*(?:Nr\.?|Nummer)\s*(\d+))?"
    rf"\s*(?:des\s+|der\s+)?({_law_alt}|Bürgerlichen Gesetzbuch(?:es|s)?|Handelsgesetzbuch(?:es|s)?|"
    rf"Einkommensteuergesetz(?:es|s)?|Abgabenordnung|Umsatzsteuergesetz(?:es|s)?)?",
    re.IGNORECASE,
)
_LONG = {"bürgerlichen gesetzbuch": "BGB", "handelsgesetzbuch": "HGB", "einkommensteuergesetz": "EStG",
         "abgabenordnung": "AO", "umsatzsteuergesetz": "UStG"}


@dataclass(frozen=True)
class StatuteRef:
    law: str | None  # canonical abbreviation, e.g. "BGB"; None = law not named (resolve from context)
    norm: str
    absatz: str | None = None

    @property
    def label(self) -> str:
        s = f"§ {self.norm}"
        if self.absatz:
            s += f" Abs. {self.absatz}"
        return f"{s} {self.law}" if self.law else s

    @property
    def key(self) -> str:
        return f"{(self.law or '?').lower()}:{self.norm}"


def _canon_law(raw: str | None) -> str | None:
    if not raw:
        return None
    low = raw.lower()
    for k, v in _LONG.items():
        if low.startswith(k):
            return v
    for v in LAWS.values():
        if v.lower() == low:
            return v
    return None


def find_statutes(text: str) -> list[StatuteRef]:
    out: list[StatuteRef] = []
    for m in STATUTE_RE.finditer(text):
        ref = StatuteRef(_canon_law(m.group(5)), m.group(1).lower(), m.group(2))
        if ref not in out:
            out.append(ref)
    return out


def fold(s: str) -> str:
    s = s.lower().replace("ß", "ss").replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


_SUFFIXES = ("ungen", "heiten", "keiten", "ung", "heit", "keit", "lich", "isch", "ern", "em", "en", "er", "es", "e",
             "n", "s")


def stem(tok: str) -> str:
    if len(tok) <= 4 or tok.isdigit():
        return tok
    for suf in _SUFFIXES:
        if tok.endswith(suf) and len(tok) - len(suf) >= 4:
            return tok[: -len(suf)]
    return tok


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokens(text: str, keep_stop: bool = False) -> list[str]:
    out = []
    for t in _TOKEN_RE.findall(fold(text)):
        if not keep_stop and (t in STOP or fold(t) in _FOLDED_STOP):
            continue
        if len(t) < 2 and not t.isdigit():
            continue
        out.append(stem(t))
    return out


_FOLDED_STOP = {fold(w) for w in STOP}

_SENT_RE = re.compile(r"(?<=[.!?…])\s+(?=[A-ZÄÖÜ0-9„\"(§])")
_ABBR = ["Abs.", "Nr.", "S.", "z.B.", "z. B.", "bzw.", "vgl.", "ggf.", "Art.", "i.V.m.", "i. V. m.", "d.h.", "d. h.",
         "u.a.", "Prof.", "Dr.", "ca.", "Rn.", "Var.", "Alt.", "Hs.", "lit.", "sog.", "usw.", "etc.", "evtl.", "inkl.",
         "max.", "min.", "Mio.", "Mrd.", "Tsd.", "Jh.", "Buchst."]
_ABBR_RE = re.compile("|".join(re.escape(a) for a in sorted(_ABBR, key=len, reverse=True)))


def sentences(text: str) -> list[str]:
    protected = _ABBR_RE.sub(lambda m: m.group(0).replace(".", "\x00"), text.strip())
    protected = re.sub(r"(\d)\.(?=\s?\d)", "\\1\x00", protected)  # dates like 15.01.2027
    parts = [p.strip().replace("\x00", ".") for p in _SENT_RE.split(protected) if p.strip()]
    return parts


def terms(text: str) -> list[str]:
    """Search terms: stemmed tokens plus 6-char prefixes of long words (German compounds/inflection:
    verjährt / Verjährung / Verjährungsfrist share "verjae")."""
    toks = tokens(text)
    out = list(toks)
    for t in toks:
        if t.isdigit():
            continue
        if len(t) >= 7:
            out.append(t[:6])
        for pre in _VERB_PREFIXES:
            if t.startswith(pre) and len(t) - len(pre) >= 7:
                out.append(t[len(pre):len(pre) + 6])
                break
    return out


_VERB_PREFIXES = ("ver", "be", "ent", "zer", "ge", "er")

QUESTION_FILLER = {"wann", "warum", "wieso", "eigent", "genau", "denn", "dann", "frage", "gilt", "gelten", "welch",
                   "wiev", "wiel", "sagen", "erklaer", "nenn", "gibt"}


def concepts(text: str) -> list[set[str]]:
    """Each content word with its search variants (prefixes) as one concept – for IDF-weighted matching."""
    out = []
    for t in dict.fromkeys(tokens(text)):
        if t in QUESTION_FILLER or t.isdigit() and len(t) < 3:
            continue
        out.append(set(terms(t)) | {t})
    return out


def content_overlap(a: str, b: str) -> float:
    """Share of a's content tokens that occur in b."""
    ta = set(tokens(a))
    if not ta:
        return 0.0
    return len(ta & set(tokens(b))) / len(ta)


def simhash(text: str) -> str:
    v = [0] * 64
    toks = tokens(text)
    for i in range(len(toks) - 2):
        h = int(hashlib.md5(" ".join(toks[i:i + 3]).encode()).hexdigest()[:16], 16)
        for b in range(64):
            v[b] += 1 if h >> b & 1 else -1
    out = 0
    for b in range(64):
        if v[b] > 0:
            out |= 1 << b
    return f"{out:016x}"


def simhash_distance(a: str, b: str) -> int:
    if not a or not b:
        return 64
    return bin(int(a, 16) ^ int(b, 16)).count("1")


DIM = 512


def local_vector(text: str) -> np.ndarray:
    """Deterministic hashed bag of stemmed words + char 4-grams (no network, no quota)."""
    vec = np.zeros(DIM, dtype=np.float32)
    toks = tokens(text)
    for t in toks:
        h = int(hashlib.blake2b(t.encode(), digest_size=4).hexdigest(), 16)
        vec[h % DIM] += 1.0 if h & 1 else -1.0
        padded = f"#{t}#"
        for i in range(len(padded) - 3):
            g = int(hashlib.blake2b(padded[i:i + 4].encode(), digest_size=4).hexdigest(), 16)
            vec[g % DIM] += 0.35 if g & 1 else -0.35
    n = np.linalg.norm(vec)
    return vec / n if n else vec


def to_blob(vec: np.ndarray) -> bytes:
    return np.asarray(vec, dtype=np.float32).tobytes()


def from_blob(blob: bytes | None) -> np.ndarray | None:
    return None if blob is None else np.frombuffer(blob, dtype=np.float32)


def surface_words(text: str, stems: list[str]) -> list[str]:
    """Map stemmed tokens back to readable words as they appear in `text`."""
    found: dict[str, str] = {}
    for w in re.findall(r"[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß-]+", text):
        st = tokens(w)
        if st and st[0] in stems and st[0] not in found:
            found[st[0]] = w
    return [found.get(s, s) for s in stems]


def short(text: str, n: int = 160) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1].rsplit(" ", 1)[0] + "…"
