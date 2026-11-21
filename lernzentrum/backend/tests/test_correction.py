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
    assert "199 BGB" in api.get(f"/api/recordings/{rec['id']}").json()["transcript"][2]["text"]
    other = api.post("/api/modules", json={"name": "Anderes Modul"}).json()
    rec2 = api.post("/api/recordings/start", json={"module_id": other["id"], "consent": True}).json()
    api.post(f"/api/recordings/{rec2['id']}/simulate", json={"text": "Und § 199 QQQ."})
    assert "QQQ" in api.get(f"/api/recordings/{rec2['id']}").json()["transcript"][0]["text"]


def test_evaluation_set_precision():
    from eval.correction_eval import evaluate

    r = evaluate()
    assert r["samples"] >= 100 and r["precision"] >= 0.98, r["errors"]


# ---------------------------------------------------------------- layer 4, batch, settings, search
def test_llm_validation_rejects_paraphrase_and_foreign_edits():
    from app.correction.service import validate_llm

    edits = [{"from": "A B G", "to": "BGB", "status": "unclear", "candidates": [{"to": "BGB"}]}]
    ok = {"corrected_text": "§ 433 BGB prüfen", "edits": [{"from": "A B G", "to": "BGB"}], "confidence": 0.9}
    assert validate_llm("§ 433 A B G prüfen", edits, ok, 0.3) == {"A B G": ("BGB", 0.9)}
    para = {"corrected_text": "Der Kaufvertrag nach dem Bürgerlichen Gesetzbuch muss man prüfen", "edits":
            [{"from": "A B G", "to": "BGB"}], "confidence": 0.9}
    assert validate_llm("§ 433 A B G prüfen", edits, para, 0.3) == {}
    foreign = {"corrected_text": "§ 433 BGB prüfen", "edits": [{"from": "prüfen", "to": "lesen"}], "confidence": 1}
    assert validate_llm("§ 433 A B G prüfen", edits, foreign, 0.3) == {}


class _Judge:
    name = "fake"

    def generate(self, prompt, **kw):
        import json as _j

        if "Unsichere Stellen" in prompt:
            return _j.dumps({"corrected_text": "Siehe § 433 BGB.", "edits": [{"from": "A B G", "to": "BGB"}],
                             "confidence": 0.95})
        return _j.dumps({"readings": []})

    def embed(self, texts):
        return None


def test_llm_adjudicator_job_and_recorrect_idempotent(api, module):
    from app.jobs import drain
    from app.providers import registry

    registry.OVERRIDES["llm"] = _Judge()
    rec = api.post("/api/recordings/start", json={"module_id": module["id"], "consent": True}).json()
    api.post(f"/api/recordings/{rec['id']}/simulate", json={"text": "Siehe § 433 A B G."})
    drain()
    seg = api.get(f"/api/recordings/{rec['id']}").json()["transcript"][0]
    e = next(x for x in seg["edits"] if x["kind"] == "law")
    assert e["layer"] == "llm" and e["to"] == "BGB" and "BGB" in seg["text"]
    assert any(ev["kind"] == "transcript_update" for ev in api.get(f"/api/recordings/{rec['id']}/events").json())
    # user undoes, then batch re-correction keeps the decision and is idempotent
    api.post(f"/api/segments/{seg['id']}/edits/{e['id']}", json={"action": "undo"})
    registry.OVERRIDES["llm"] = None
    for _ in range(2):
        job = api.post(f"/api/correction/modules/{module['id']}/recorrect").json()
        drain()
        j = next(x for x in api.get("/api/jobs").json() if x["id"] == job["job_id"])
        assert j["status"] == "done" and j["progress"] == 1.0
    seg2 = api.get(f"/api/recordings/{rec['id']}").json()["transcript"][0]
    assert seg2["original"] == "Siehe § 433 A B G." and "BGB" not in seg2["text"]


def test_settings_vocab_rules_export_and_search_original(api, module):
    s = api.put("/api/correction/settings", json={"mode": "conservative"}).json()
    assert (s["auto"], s["mark"]) == (95, 75)
    assert api.put("/api/correction/settings", json={"auto": 50, "mark": 80}).status_code == 422
    api.post("/api/correction/vocabulary", json={"term": "Kaufpreisanspruch", "module_id": module["id"]})
    rec = api.post("/api/recordings/start", json={"module_id": module["id"], "consent": True}).json()
    api.post(f"/api/recordings/{rec['id']}/simulate", json={"text": "Der Kaufpreis Anspruch und § 433 WWW."})
    seg = api.get(f"/api/recordings/{rec['id']}").json()["transcript"][0]
    assert "Kaufpreisanspruch" in seg["text"]
    exp = api.get("/api/correction/export").json()
    assert exp["vocabulary"][0]["term"] == "Kaufpreisanspruch"
    assert api.post("/api/correction/import", json=exp).json()["vocabulary"] == 1
    api.post(f"/api/recordings/{rec['id']}/finish")
    from app.jobs import drain

    drain()
    hits = api.get("/api/search", params={"q": "WWW"}).json()["hits"]  # original wording still searchable
    assert hits and hits[0]["start_s"] is not None
    api.put("/api/correction/settings", json={"enabled": False})
    api.post(f"/api/recordings/{rec['id']}/simulate", json={"text": "§ 433 WWW."})
    assert api.get(f"/api/recordings/{rec['id']}").json()["transcript"][-1]["text"] == "§ 433 WWW."
