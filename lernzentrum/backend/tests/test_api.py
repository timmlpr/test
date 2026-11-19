"""API tests: auth/CSRF, wizard, keys (masked, test buttons), missing-key degradation, live flow, exam guard,
inbox/library, search, statutes, learning aids, export/delete."""
import io
import json

import httpx
import respx

from app.jobs import drain
from app.providers import registry
from app.providers.base import SttResult, SttSegment
from tests.conftest import PASSWORD, Api


class FakeStt:
    name = "fake"

    def __init__(self, text="Welche Pflichten hat der Käufer nach § 433 BGB? Das ist klausurrelevant."):
        self.text = text

    def transcribe(self, audio, filename, mime, *, prompt="", language="de"):
        return SttResult(self.text, [SttSegment(0.0, 6.0, self.text)], 6.0)

    def test(self):
        return "ok"


class FakeLlm:
    name = "fake"

    def __init__(self):
        self.calls = []

    def generate(self, prompt, *, system="", json_mode=False, tier="lite", max_tokens=1024, temperature=0.2):
        self.calls.append(prompt)
        if "readings" in prompt:
            return json.dumps({"readings": [{"reading": "Pflichten des Käufers", "probability": 0.7,
                                             "short": "Der Käufer muss den Kaufpreis zahlen und die Sache abnehmen [S1].",
                                             "detailed": "Nach § 433 Abs. 2 BGB muss der Käufer den vereinbarten "
                                                         "Kaufpreis zahlen und die gekaufte Sache abnehmen [S1].",
                                             "citations": ["S1"], "support": "direct", "self_confidence": 0.9},
                                            {"reading": "Pflichten des Verkäufers", "probability": 0.3,
                                             "short": "Übergabe und Übereignung [S1].",
                                             "detailed": "Der Verkäufer muss die Sache übergeben und das Eigentum "
                                                         "verschaffen [S1].", "citations": ["S1"],
                                             "support": "partial", "self_confidence": 0.6}]})
        if "contradicts" in prompt:
            return json.dumps({"contradicts": True, "corrected_answer": "Buchungsbelege: acht Jahre."})
        return json.dumps({"summary": ["Kaufvertrag"], "flashcards": [{"front": "F?", "back": "A"}],
                           "open_questions": [], "terms": []})

    def vision_ocr(self, image, mime):
        return "Handschrift erkannt"

    def embed(self, texts):
        return [[0.1] * 768 for _ in texts]

    def test(self):
        return "ok"


# ---------------------------------------------------------------- auth
def test_register_only_once_and_csrf(client, api):
    other = Api(client)
    client.cookies.clear()
    r = other.post("/api/auth/register", json={"email": "zwei@example.com", "password": PASSWORD})
    assert r.status_code == 403  # single-user app
    r = client.post("/api/auth/login", json={"email": "studi@example.com", "password": PASSWORD})
    assert r.status_code == 200
    # mutating call without CSRF header is rejected
    assert client.post("/api/modules", json={"name": "X"}).status_code == 403
    assert other.post("/api/modules", json={"name": "Grundlagen BWL"}).status_code == 200


def test_login_wrong_password(client, api):
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"email": "studi@example.com", "password": "falsch"}).status_code == 401
    assert client.get("/api/home").status_code == 401


def test_weak_password_rejected(client):
    r = client.post("/api/auth/register", json={"email": "a@example.com", "password": "kurz"})
    assert r.status_code == 422


# ---------------------------------------------------------------- wizard & keys
@respx.mock
def test_keys_masked_and_test_buttons(api):
    respx.get("https://api.groq.com/openai/v1/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "whisper-large-v3-turbo"}]}))
    respx.get("https://generativelanguage.googleapis.com/v1beta/models").mock(
        return_value=httpx.Response(403, json={"error": {"message": "API_KEY_INVALID"}}))
    r = api.put("/api/secrets/groq", json={"value": "gsk_abcdefghijklmnop1234"})
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert r.json()["hint"] == "gsk_…1234"
    r = api.put("/api/secrets/gemini", json={"value": "AIzaSyBADBADBADBAD9999"})
    assert r.json()["status"] == "error"
    listing = api.get("/api/secrets").json()
    assert all("abcdefghijklmnop" not in json.dumps(x) for x in listing)
    conns = {c["key"]: c["status"] for c in api.get("/api/health/connections").json()}
    assert conns["groq"] == "ok" and conns["gemini"] == "error" and conns["moodle"] == "missing"
    st = api.post("/api/setup/step", json={"step": 2}).json()
    assert st["setup_step"] == 3


def test_wizard_skip_is_resumable(api):
    api.post("/api/setup/step", json={"step": 2, "skipped": True})
    s = api.get("/api/setup").json()
    assert s["step"] == 3 and 2 in s["skipped"] and s["done"]["2"] is False


# ---------------------------------------------------------------- live mode
def _start(api, module_id, consent=True):
    return api.post("/api/recordings/start", json={"module_id": module_id, "consent": consent})


def test_consent_required_and_logged(api, module):
    assert _start(api, module["id"], consent=False).status_code == 428
    r = _start(api, module["id"])
    assert r.status_code == 200 and r.json()["live_answers"] is True


def test_missing_groq_key_degrades_but_keeps_audio(api, module):
    rec = _start(api, module["id"]).json()
    r = api.post(f"/api/recordings/{rec['id']}/chunks", data={"seq": "0", "offset_s": "0", "duration_s": "8"},
                 files={"file": ("c0.webm", b"\x1aE\xdf\xa3fakeaudio", "audio/webm")})
    assert r.status_code == 200
    drain()
    events = api.get(f"/api/recordings/{rec['id']}/events").json()
    status = [e for e in events if e["kind"] == "status"]
    assert status and "fehlt: Groq" in status[-1]["payload"]["message"]
    detail = api.get(f"/api/recordings/{rec['id']}").json()
    assert detail["chunks"][0]["has_audio"] is True  # audio kept for later transcription


def _seed_material(api, module_id):
    from app.seed import SLIDES

    text = "\n\n".join(SLIDES["SSR"][1])
    r = api.post("/api/documents/upload", data={"module_id": str(module_id)},
                 files=[("files", ("SSR_Folien_Kaufrecht.txt", text.encode(), "text/plain"))])
    assert r.status_code == 200
    drain()


def test_live_flow_with_stt_answers_sources_and_followup(api, module):
    from app.db import SessionLocal
    from app.statutes import seed_demo_norms

    with SessionLocal() as db:  # offline: statute texts from the demo cache
        seed_demo_norms(db)
        db.commit()
    _seed_material(api, module["id"])
    registry.OVERRIDES["stt"] = FakeStt("Heute behandeln wir den Kaufvertrag nach § 433 BGB. "
                                        "Welche Pflichten hat der Käufer? Das ist klausurrelevant.")
    rec = _start(api, module["id"]).json()
    api.post(f"/api/recordings/{rec['id']}/chunks", data={"seq": "0", "offset_s": "0", "duration_s": "8"},
             files={"file": ("c0.webm", b"audio", "audio/webm")})
    drain()
    ev = api.get(f"/api/recordings/{rec['id']}/events").json()
    kinds = {e["kind"] for e in ev}
    assert {"transcript", "keyword", "statute", "answer"} <= kinds
    ans = next(e for e in ev if e["kind"] == "answer")["payload"]["answers"][0]
    assert ans["level"] in ("SICHER", "PRÜFEN", "UNSICHER") and 0 <= ans["percent"] <= 99
    assert ans["sources"] and all(s.get("label") for s in ans["sources"])
    assert any("433" in (s.get("excerpt", "") + s.get("label", "")) for s in ans["sources"])
    statute_ev = next(e for e in ev if e["kind"] == "statute")["payload"]
    assert statute_ev["found"] and "Kaufvertrag" in statute_ev["excerpt"]
    # follow-up via manual ask → resolved with lecture context
    r = api.post(f"/api/recordings/{rec['id']}/ask", json={"question": "Und wann verjährt dann der Anspruch?"})
    a = r.json()["answers"][0]
    assert a["sources"] and "verj" in (a["short"] + a["detailed"]).lower()
    # duplicate chunk upload is idempotent
    r = api.post(f"/api/recordings/{rec['id']}/chunks", data={"seq": "0"},
                 files={"file": ("c0.webm", b"audio", "audio/webm")})
    assert r.json().get("duplicate")
    # finish → transcript document + package
    api.post(f"/api/recordings/{rec['id']}/finish")
    drain()
    drain()
    items = api.get(f"/api/learn/items?recording_id={rec['id']}").json()
    assert any(i["kind"] == "summary" for i in items)
    assert any(i["kind"] == "exam_passage" for i in items)
    hist = api.get("/api/answers").json()
    assert len(hist) >= 2


def test_no_source_gives_unsicher(api, module):
    r = api.post("/api/ask", json={"question": "Wie hoch ist der Grundfreibetrag in Australien?",
                                   "module_id": module["id"]})
    a = r.json()["answers"][0]
    assert a["level"] == "UNSICHER" and a["percent"] <= 15 and "keine Quelle" in a["why"]


def test_llm_candidates_and_correction(api, module):
    _seed_material(api, module["id"])
    registry.OVERRIDES["llm"] = FakeLlm()
    rec = _start(api, module["id"]).json()
    api.post(f"/api/recordings/{rec['id']}/simulate", json={"text": "Es geht um § 433 BGB. Welche Pflichten hat der Käufer?"})
    ev = api.get(f"/api/recordings/{rec['id']}/events").json()
    answers = next(e for e in ev if e["kind"] == "answer")["payload"]["answers"]
    assert len(answers) == 2 and answers[0]["probability"] >= answers[1]["probability"]
    assert answers[0]["engine"] == "gemini" and answers[0]["level"] in ("SICHER", "PRÜFEN")
    # lecturer contradicts with a different number on the same topic → correction flagged
    api.post(f"/api/recordings/{rec['id']}/simulate",
             json={"text": "Achtung, der Käufer muss den Kaufpreis nicht immer sofort zahlen, nur wenn fällig."})
    ev = api.get(f"/api/recordings/{rec['id']}/events").json()
    corr = [e for e in ev if e["kind"] == "correction"]
    assert corr and corr[0]["payload"]["correction"]["corrected"]
    prof = api.get(f"/api/modules/{module['id']}/profile").json()
    assert prof["corrections"]


def test_exam_guard_blocks_live_answers(api, module):
    api.patch(f"/api/modules/{module['id']}", json={"exam_mode": True})
    rec = _start(api, module["id"]).json()
    assert rec["live_answers"] is False and rec["exam_mode"] is True
    api.post(f"/api/recordings/{rec['id']}/simulate", json={"text": "Welche Pflichten hat der Käufer?"})
    ev = api.get(f"/api/recordings/{rec['id']}/events").json()
    assert not [e for e in ev if e["kind"] == "answer"]
    assert [e for e in ev if e["kind"] == "exam_guard"]
    r = api.post(f"/api/recordings/{rec['id']}/ask", json={"question": "Welche Pflichten hat der Käufer?"})
    assert r.json()["answers"] == []
    assert api.patch(f"/api/recordings/{rec['id']}", json={"live_answers": True}).status_code == 409


def test_offline_gap_chunk_marked_late(api, module):
    registry.OVERRIDES["stt"] = FakeStt("Nachgereichter Abschnitt über Verjährung.")
    rec = _start(api, module["id"]).json()
    api.post(f"/api/recordings/{rec['id']}/chunks", data={"seq": "3", "offset_s": "24", "late": "true"},
             files={"file": ("c3.webm", b"audio", "audio/webm")})
    drain()
    detail = api.get(f"/api/recordings/{rec['id']}").json()
    assert detail["transcript"][0]["start_s"] >= 24 and "late" in detail["transcript"][0]["flags"]
    assert any(e["kind"] == "gap" for e in api.get(f"/api/recordings/{rec['id']}/events").json())


# ---------------------------------------------------------------- inbox & library
def _docx_bytes(text):
    import docx

    d = docx.Document()
    for line in text.split("\n"):
        d.add_paragraph(line)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def test_upload_classify_dedupe_review(api, module):
    bwl = api.post("/api/modules", json={"name": "Grundlagen BWL", "short": "BWL"}).json()
    body = _docx_bytes("Übungsblatt 3\nAufgabe 1: Erläutern Sie das ökonomische Prinzip.\n"
                       "Abgabe bis zum 15.01.2027.")
    r = api.post("/api/documents/upload", files=[
        ("files", ("BWL_Uebung_3.docx", body, "application/octet-stream")),
        ("files", ("Kopie_BWL_Uebung_3.docx", body, "application/octet-stream")),
        ("files", ("Scan_0042.txt", "Irgendwelche Notizen ohne Bezug zu etwas.".encode(), "text/plain")),
    ])
    assert r.status_code == 200
    drain()
    inbox = {i["document"]["original_name"]: i for i in api.get("/api/inbox").json()}
    first = inbox["BWL_Uebung_3.docx"]
    assert first["status"] == "sorted" and first["document"]["module_id"] == bwl["id"]
    assert first["document"]["kind"] == "exercise"
    assert first["document"]["title"].startswith("BWL_") and "Uebung" in first["document"]["title"]
    assert inbox["Kopie_BWL_Uebung_3.docx"]["status"] == "duplicate"
    scan = inbox["Scan_0042.txt"]
    assert scan["status"] == "review"
    # deadline proposal extracted from the document
    dls = api.get("/api/deadlines").json()
    assert any(d["due"].startswith("2027-01-15") for d in dls)
    # review → confirm
    r = api.post(f"/api/inbox/{scan['id']}/confirm", json={"module_id": module["id"]})
    assert r.json()["document"]["module_id"] == module["id"] and not r.json()["document"]["needs_review"]
    # search finds content with jump location
    hits = api.get("/api/search", params={"q": "ökonomisches Prinzip"}).json()["hits"]
    assert hits and hits[0]["document_id"] == first["document"]["id"]


def test_upload_token_drop_and_mail_webhook(client, api):
    tok = api.post("/api/inbox/upload-token").json()["token"]
    r = client.post(f"/api/inbox/drop/{tok}", files={"file": ("Notiz.txt", b"Kurze Notiz zur Bilanz.", "text/plain")})
    assert r.status_code == 200
    mime = (b"From: a@example.com\r\nTo: b@example.com\r\nSubject: Folien\r\nMIME-Version: 1.0\r\n"
            b"Content-Type: multipart/mixed; boundary=XX\r\n\r\n--XX\r\nContent-Type: text/plain\r\n\r\nHallo\r\n"
            b"--XX\r\nContent-Type: text/plain\r\nContent-Disposition: attachment; filename=\"BWL_Folien.txt\"\r\n\r\n"
            b"Folie 1 Produktionsfaktoren\r\n--XX--\r\n")
    r = client.post(f"/api/inbox/mail/{tok}", content=mime)
    assert r.json()["attachments"] == 1
    assert client.post("/api/inbox/drop/falsch-falsch-falsch-xx", files={"file": ("a.txt", b"x")}).status_code == 404


def test_bulk_audio_import_without_key_waits_and_assigns(api, module):
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".m4a") as f:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                        "-metadata", "creation_time=2026-11-02T07:20:00Z", f.name], check=True)
        audio = open(f.name, "rb").read()
    # timetable lecture at that time (08:15 Berlin = 07:15 UTC)
    from datetime import datetime

    from app.db import SessionLocal
    from app.models import Lecture

    with SessionLocal() as db:
        db.add(Lecture(user_id=1, module_id=module["id"], start=datetime(2026, 11, 2, 8, 15),
                       end=datetime(2026, 11, 2, 9, 45)))
        db.commit()
    r = api.post("/api/documents/upload", data={"channel": "import"},
                 files=[("files", ("20261102 082000.m4a", audio, "audio/mp4"))])
    assert r.status_code == 200
    drain()
    doc = api.get("/api/documents").json()[0]
    assert doc["module_id"] == module["id"] and doc["status"] == "waiting"
    registry.OVERRIDES["stt"] = FakeStt("Willkommen zur Vorlesung über den Kaufvertrag.")
    api.post(f"/api/jobs/{api.get('/api/jobs').json()[0]['id']}/retry")
    drain()
    doc = api.get(f"/api/documents/{doc['id']}").json()
    assert doc["status"] == "ready" and doc["recording_id"]
    rec = api.get(f"/api/recordings/{doc['recording_id']}").json()
    assert rec["transcript"] and rec["source"] == "import"


@respx.mock
def test_statute_fetch_and_parse(api):
    html = ('<div class="jnheader"><h1><span class="jnenbez">§ 195</span>&nbsp;<span class="jnentitel">Regelmäßige '
            'Verjährungsfrist</span></h1></div><div class="jnhtml"><div><div class="jurAbsatz">Die regelmäßige '
            'Verjährungsfrist beträgt drei Jahre.</div></div></div>')
    respx.get("https://www.gesetze-im-internet.de/bgb/__195.html").mock(return_value=httpx.Response(200, text=html))
    r = api.get("/api/learn/statutes/bgb/195")
    assert r.status_code == 200
    j = r.json()
    assert j["text"] == "Die regelmäßige Verjährungsfrist beträgt drei Jahre." and "Verjährungsfrist" in j["title"]
    f = api.post("/api/learn/statutes/find", json={"question": "Wie lange ist die regelmäßige Verjährungsfrist?"}).json()
    assert f["results"] and f["results"][0]["norm"] == "195"


# ---------------------------------------------------------------- learning
def test_learning_aids(api, module):
    _seed_material(api, module["id"])
    for i in range(4):
        api.post("/api/learn/flashcards", json={"module_id": module["id"], "front": f"Frage {i}",
                                                "back": f"Antwort Nummer {i}"})
    cards = api.get("/api/learn/flashcards", params={"module_id": module["id"], "due_only": True}).json()
    assert len(cards) == 4
    r = api.post(f"/api/learn/flashcards/{cards[0]['id']}/review", json={"grade": 5}).json()
    assert r["interval_days"] == 1
    quiz = api.get(f"/api/learn/quiz/{module['id']}").json()["items"]
    assert quiz and {q["type"] for q in quiz} <= {"mc", "cloze"}
    mock = api.post("/api/learn/mock", json={"module_id": module["id"], "minutes": 20}).json()
    assert mock["items"] and all("answer" not in i for i in mock["items"])
    res = api.post(f"/api/learn/mock/{mock['id']}/submit", json={"answers": {"0": 0}}).json()
    assert res["grade"] and res["score"] is not None and len(res["feedback"]) == len(res["items"])
    case = api.post("/api/learn/case", json={
        "case": "V verkauft K ein Fahrrad. K zahlt nicht.",
        "solution": "V könnte gegen K einen Anspruch auf Zahlung aus § 433 Abs. 2 BGB haben. Voraussetzung ist ein "
                    "wirksamer Kaufvertrag. Hier haben V und K sich geeinigt. Somit besteht der Anspruch."}).json()
    assert case["score"] == 1.0
    assert api.get("/api/learn/plan").json()
    assert "modules" in api.get("/api/learn/stats").json()
    dash = api.get(f"/api/modules/{module['id']}/dashboard").json()
    assert dash["cards"]["total"] == 4 and "next_tasks" in dash
    assert api.post(f"/api/learn/glossary/{module['id']}/build").status_code == 200


# ---------------------------------------------------------------- privacy
def test_export_and_delete_all(client, api, module):
    r = api.get("/api/export")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert api.post("/api/delete-all", json={"password": "falsch", "confirm": "LÖSCHEN"}).status_code == 403
    assert api.post("/api/delete-all", json={"password": PASSWORD, "confirm": "LÖSCHEN"}).status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"
