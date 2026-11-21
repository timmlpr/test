"""Kontext-Korrektur: spec cases, safety, latency, undo/rule learning, pipeline integration."""
import time

from app.correction.engine import Ctx, apply_edits, correct
from app.correction.lexicon import subject_laws

SSR, STR, BF = "Grundlagen im Schuld- und Sachenrecht", "Grundlagen des Steuerrechts", "Buchführung"


def fix(text, module=""):
    out, edits = correct(text, Ctx(module_name=module, subject_laws=subject_laws(module)))
    return out.replace(" ", " "), edits


def test_www_to_bgb_auto():
    out, edits = fix("das steht im §433 WWW", SSR)
    assert out == "das steht im § 433 BGB"
    assert next(e for e in edits if e["from"] == "WWW")["status"] == "applied"


def test_spelled_estg_with_qualifiers():
    assert fix("nach Paragraph 15 Absatz 1 Satz 1 Nummer 2 E S T G", STR)[0] == "nach § 15 Abs. 1 S. 1 Nr. 2 EStG"


def test_hgb_and_ustg_and_letter_names():
    assert fix("gemäß § 238 H G B", BF)[0] == "gemäß § 238 HGB"
    assert fix("Paragraf 8 U S T G")[0] == "§ 8 UStG"
    assert fix("Paragraf 80 U S T G")[0] == "§ 80 U S T G"  # § 80 does not exist in UStG → not applied
    assert fix("Paragraph vierhundertdreiunddreißig Be Ge Be", SSR)[0] == "§ 433 BGB"


def test_invalid_section_unclear():
    out, edits = fix("§ 9999 BGB")
    assert out == "§ 9999 BGB" and any(e["status"] == "unclear" for e in edits)


def test_ambiguous_stays_unapplied():
    out, edits = fix("§ 433 A B G", SSR)
    e = next(e for e in edits if e["kind"] == "law")
    assert out == "§ 433 A B G" and e["status"] == "unclear" and e["candidates"][0]["to"] == "BGB"


def test_internet_www_untouched():
    assert fix("im WWW gibt es viele Infos") == ("im WWW gibt es viele Infos", [])
    assert fix("§ 433 BGB regelt den Kaufvertrag")[0] == "§ 433 BGB regelt den Kaufvertrag"


def test_terms_and_merges():
    assert fix("die Willens Erklärung und kulpa in kontrahendo")[0] == \
        "die Willenserklärung und culpa in contrahendo"


def test_latency_rule_layers():
    t = time.perf_counter()
    for _ in range(200):
        fix("nach Paragraph 15 Absatz 1 E S T G und § 433 WWW sowie die Willens Erklärung", SSR)
    assert (time.perf_counter() - t) / 200 < 0.3


def test_original_kept_and_undo():
    _, edits = fix("das steht im §433 WWW", SSR)
    for e in edits:
        e["status"] = "undone"
    assert apply_edits("das steht im §433 WWW", edits) == "das steht im §433 WWW"


def test_pipeline_undo_and_always_rule(api, module):
    rec = api.post("/api/recordings/start", json={"module_id": module["id"], "consent": True}).json()
    api.post(f"/api/recordings/{rec['id']}/simulate", json={"text": "Das steht im §433 WWW."})
    seg = api.get(f"/api/recordings/{rec['id']}").json()["transcript"][0]
    assert "BGB" in seg["text"] and seg["original"] == "Das steht im §433 WWW."
    eid = next(e["id"] for e in seg["edits"] if e["from"] == "WWW")
    r = api.post(f"/api/segments/{seg['id']}/edits/{eid}", json={"action": "undo"}).json()
    assert "WWW" in r["text"] and r["original"] == "Das steht im §433 WWW."
    # learned rule: "QQQ" → BGB, only in this module
    api.post(f"/api/recordings/{rec['id']}/simulate", json={"text": "Siehe § 195 QQQ."})
    seg2 = api.get(f"/api/recordings/{rec['id']}").json()["transcript"][1]
    e2 = next(e for e in seg2["edits"] if e["kind"] == "law")
    api.post(f"/api/segments/{seg2['id']}/edits/{e2['id']}", json={"action": "always", "to": "BGB"})
    api.post(f"/api/recordings/{rec['id']}/simulate", json={"text": "Und § 199 QQQ."})
    assert "§ 199 BGB" in api.get(f"/api/recordings/{rec['id']}").json()["transcript"][2]["text"]
    other = api.post("/api/modules", json={"name": "Anderes Modul"}).json()
    rec2 = api.post("/api/recordings/start", json={"module_id": other["id"], "consent": True}).json()
    api.post(f"/api/recordings/{rec2['id']}/simulate", json={"text": "Und § 199 QQQ."})
    assert "QQQ" in api.get(f"/api/recordings/{rec2['id']}").json()["transcript"][0]["text"]
