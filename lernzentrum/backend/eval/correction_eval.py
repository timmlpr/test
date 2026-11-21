"""Evaluation harness for the Kontext-Korrektur (labelled, generated, deterministic).

    python -m eval.correction_eval      (from backend/)

Each sample: (raw ASR text, module, expected text). Positives contain a mis-recognised citation or term; negatives must
stay unchanged. Reports precision of applied changes (auto ≥ 90 and marked 60–89 separately) and recall.
"""
from __future__ import annotations

import random

from app.correction.engine import Ctx, correct
from app.correction.lexicon import subject_laws

SSR, STR, BF, BWL = "Grundlagen im Schuld- und Sachenrecht", "Grundlagen des Steuerrechts", "Buchführung", "Grundlagen BWL"
NUMWORDS = {433: "vierhundertdreiunddreißig", 195: "hundertfünfundneunzig", 15: "fünfzehn", 238: "zweihundertachtunddreißig",
            8: "acht", 1: "eins", 2: "zwei", 4: "vier", 280: "zweihundertachtzig", 929: "neunhundertneunundzwanzig"}
# (law, valid sections, module, spoken/misheard variants)
LAWS = [
    ("BGB", [433, 195, 280, 929, 241, 437, 823, 985, 312, 104], SSR, ["WWW", "Be Ge Be", "B G B", "BKB", "PGB", "BeGeBe"]),
    ("HGB", [238, 1, 242, 246, 252, 253, 257, 266, 275, 343], BF, ["H G B", "Ha Ge Be", "HGP", "HKB"]),
    ("EStG", [15, 2, 4, 5, 6, 7, 9, 10, 18, 21], STR, ["E S T G", "Es Te Ge", "ES-TE-GE", "ESDG", "ESTG"]),
    ("UStG", [1, 3, 4, 8, 12, 14, 15, 19, 13, 2], STR, ["U S T G", "U Es Te Ge", "USDG"]),
    ("AO", [3, 37, 38, 140, 141, 147, 169, 170, 233, 347], STR, ["A O"]),
    ("KStG", [1, 8, 14, 7, 9, 10, 27], STR, ["K ST G", "Ka Es Te Ge", "KSDG"]),
    ("ZPO", [253, 704, 1, 91, 286], SSR, ["Z P O", "Zet Pe O"]),
    ("InsO", [17, 19, 80, 129, 35], SSR, ["In S O"]),
    ("GmbHG", [13, 30, 43, 5, 1], BWL, ["GmbH G"]),
]
SENT = ["das steht im {c}", "nach {c} gilt das", "gemäß {c} ist das zu prüfen", "schauen Sie in {c}", "{c} regelt das"]


def samples() -> list[tuple[str, str, str]]:
    rnd = random.Random(7)
    out: list[tuple[str, str, str]] = []
    for law, secs, mod, variants in LAWS:
        for v in variants:
            for n in rnd.sample(secs, min(3, len(secs))):
                tpl = rnd.choice(SENT)
                anchor = rnd.choice(["§", "§ ", "Paragraph ", "Paragraf "])
                num = NUMWORDS[n] if n in NUMWORDS and rnd.random() < 0.3 and anchor != "§" else str(n)
                out.append((tpl.format(c=f"{anchor}{num} {v}"), mod, tpl.format(c=f"§ {n} {law}")))
    # qualifiers
    out += [("nach Paragraph 15 Absatz 1 Satz 1 Nummer 2 E S T G", STR, "nach § 15 Abs. 1 S. 1 Nr. 2 EStG"),
            ("gemäß § 433 Absatz 2 WWW", SSR, "gemäß § 433 Abs. 2 BGB"),
            ("§ 4 Abs. 1 Satz 1 E S T G", STR, "§ 4 Abs. 1 S. 1 EStG"),
            ("Paragraph 280 Absatz eins Be Ge Be", SSR, "§ 280 Abs. 1 BGB")]
    # terms
    out += [("die Willens Erklärung ist wirksam", SSR, "die Willenserklärung ist wirksam"),
            ("ein Fall der kulpa in kontrahendo", SSR, "ein Fall der culpa in contrahendo"),
            ("die Anschaffungs Kosten sind maßgeblich", BF, "die Anschaffungskosten sind maßgeblich"),
            ("pakta sunt servanda gilt", SSR, "pacta sunt servanda gilt"),
            ("das ist eine invitatio at offerendum", SSR, "das ist eine invitatio ad offerendum")]
    # negatives: must stay unchanged
    negs = ["im WWW gibt es viele Infos", "die BGB-Gesellschaft ist eine Personengesellschaft", "§ 433 BGB regelt den Kauf",
            "§ 15 EStG und § 2 AO", "nach § 238 HGB", "per E-Mail an das Prüfungsamt", "die AGB des Händlers",
            "das ZDF berichtete", "wir sehen uns um acht", "der Paragraph ist lang", "Gewinn vor Steuern",
            "nach Erfüllung des Vertrags", "§ 433 regelt den Kaufvertrag", "die GmbH haftet", "die USA und die EU",
            "Art. 3 GG", "§ 9999 BGB", "§ 500 EStG", "§ 433 A B G", "das www ist groß"]
    out += [(n, SSR, n) for n in negs]
    return out


def evaluate() -> dict:
    tp = fp = fn = marked_ok = marked_bad = 0
    errors = []
    data = samples()
    for raw, mod, exp in data:
        got, edits = correct(raw, Ctx(module_name=mod, subject_laws=subject_laws(mod)))
        got = got.replace(" ", " ")
        changed = got != raw.replace(" ", " ")
        need = exp != raw
        marked = any(e["status"] == "check" for e in edits)
        if changed and got == exp:
            tp += 1
            marked_ok += marked
        elif changed:
            fp += 1
            marked_bad += marked
            errors.append((raw, got, exp))
        elif need:
            fn += 1
            errors.append((raw, got, exp))
    return {"samples": len(data), "tp": tp, "fp": fp, "fn": fn,
            "precision": tp / max(1, tp + fp), "recall": tp / max(1, tp + fn),
            "marked_ok": marked_ok, "marked_bad": marked_bad, "errors": errors}


if __name__ == "__main__":
    r = evaluate()
    print(f"{r['samples']} Proben · Präzision {r['precision']:.1%} · Recall {r['recall']:.1%} "
          f"(TP {r['tp']}, FP {r['fp']}, FN {r['fn']}, davon markiert: {r['marked_ok']} ok / {r['marked_bad']} falsch)")
    for e in r["errors"]:
        print("  ", e)
