"""SMS provider, mailbox connection (Gmail metadata), OCR path – all network calls faked."""
import pytest

from tests.conftest import register


class FakeResp:
    def __init__(self, status=200, data=None):
        self.status_code, self._d = status, data or {}

    def json(self):
        return self._d


def test_phone_code_sent_via_sms_provider(api, monkeypatch):
    register(api)
    from app.settings import get_settings

    monkeypatch.setattr(get_settings(), "sms_provider", "seven")
    monkeypatch.setattr(get_settings(), "sms_api_key", "test-key")
    sent = {}

    from app.adapters.sms import SevenSms

    def fake_http(self, method, url, **kw):
        sent.update(url=url, data=kw["data"], headers=kw["headers"])
        return FakeResp(200, {"success": "100"})

    monkeypatch.setattr(SevenSms, "http", fake_http)
    r = api.post("/api/profile/identifiers", json={"kind": "phone", "value": "+49 170 1234567", "own_data": True}).json()
    assert r["pending_reason"] == "enter_code" and "dev_hint" not in r
    assert sent["url"] == "https://gateway.seven.io/api/sms" and sent["headers"]["X-Api-Key"] == "test-key"
    code = sent["data"]["text"].split("Code: ")[1][:6]
    assert sent["data"]["to"] == "+491701234567"
    assert api.post(f"/api/profile/identifiers/{r['id']}/verify", json={"code": code}).json()["verified"]


def test_sms_provider_failure_is_clean_error(api, monkeypatch):
    register(api)
    from app.adapters.sms import SevenSms
    from app.settings import get_settings

    monkeypatch.setattr(get_settings(), "sms_provider", "seven")
    monkeypatch.setattr(get_settings(), "sms_api_key", "k")
    monkeypatch.setattr(SevenSms, "http", lambda self, *a, **k: FakeResp(200, {"success": "900"}))
    r = api.post("/api/profile/identifiers", json={"kind": "phone", "value": "+49 170 7654321", "own_data": True})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "sms_unavailable"


@pytest.fixture
def google(monkeypatch):
    from app.settings import get_settings

    monkeypatch.setattr(get_settings(), "google_client_id", "cid")
    monkeypatch.setattr(get_settings(), "google_client_secret", "secret")


def _connect(api, monkeypatch):
    import jwt

    r = api.c.get("/api/subs/mailbox/start", follow_redirects=False)
    assert r.status_code in (302, 307)
    loc = r.headers["location"]
    assert "gmail.metadata" in loc and "access_type=offline" in loc
    state = loc.split("state=")[1].split("&")[0]
    id_token = jwt.encode({"email": "anna@gmail.example"}, "x", algorithm="HS256")
    import httpx

    monkeypatch.setattr(httpx, "post", lambda url, **kw: FakeResp(200, {"refresh_token": "rt", "access_token": "at", "id_token": id_token,
                                                                       "scope": "openid email https://www.googleapis.com/auth/gmail.metadata"}))
    from app.modules import vault

    monkeypatch.setattr(vault, "_fetch_headers", lambda tok, limit=500: iter([
        ({"from": "Stream <billing@stream.example>", "subject": "Deine Rechnung: Abo monatlich 9,99 €", "date": "Mon, 1 Jan 2026 10:00:00 +0100"}, ""),
        ({"from": "news@shop.example", "subject": "Sale", "list-unsubscribe": "<https://shop.example/u>"}, ""),
        ({"from": "freund@example.org", "subject": "Hi"}, ""),
    ]))
    return api.c.get(f"/api/subs/mailbox/callback?code=abc&state={state}", follow_redirects=False)


def test_mailbox_unavailable_without_google_config(api, premium):
    s = api.get("/api/subs").json()
    assert s["mailbox"]["available"] is False
    assert api.c.get("/api/subs/mailbox/start", follow_redirects=False).status_code == 503


def test_mailbox_connect_sync_and_disconnect(api, premium, google, monkeypatch):
    r = _connect(api, monkeypatch)
    assert r.status_code == 303 and "mailbox=connected" in r.headers["location"]
    s = api.get("/api/subs").json()
    assert s["mailbox"]["connected"] and s["mailbox"]["address"] == "anna@gmail.example"
    assert s["counts"]["subscription"] == 1 and s["counts"]["newsletter"] == 1 and s["monthly_cost"] == 9.99
    from app.db import SessionLocal
    from app.models import ConsentLog, MailboxConnection

    with SessionLocal() as db:
        raw = db.execute(__import__("sqlalchemy").text("select refresh_token from mailbox_connections")).scalar()
        assert raw != "rt"  # encrypted at rest
    revoked = []
    import httpx

    monkeypatch.setattr(httpx, "post", lambda url, **kw: revoked.append(url) or FakeResp(200))
    assert api.delete("/api/subs/mailbox").json()["ok"]
    assert revoked and "revoke" in revoked[0]
    with SessionLocal() as db:
        assert db.query(MailboxConnection).count() == 0
        assert {c.granted for c in db.query(ConsentLog).filter(ConsentLog.kind == "mailbox")} == {True, False}


def test_mailbox_callback_rejects_foreign_state(api, premium, google):
    r = api.c.get("/api/subs/mailbox/callback?code=abc&state=forged", follow_redirects=False)
    assert r.status_code == 400


def test_mailbox_requires_premium(api, user, google):
    assert api.c.get("/api/subs/mailbox/start", follow_redirects=False).status_code == 402


def test_account_deletion_revokes_mailbox(api, premium, google, monkeypatch):
    _connect(api, monkeypatch)
    import httpx

    revoked = []
    monkeypatch.setattr(httpx, "post", lambda url, **kw: revoked.append(url) or FakeResp(200))
    assert api.delete("/api/profile", json={"confirm": True}).status_code == 200
    assert revoked


def test_ocr_image_when_tesseract_available(api, premium):
    import shutil

    if not shutil.which("tesseract"):
        pytest.skip("tesseract binary not installed here (installed in Docker image and by start scripts)")
    import io

    from PIL import Image, ImageDraw

    img = Image.new("RGB", (900, 120), "white")
    ImageDraw.Draw(img).text((10, 40), "Kuendigung bis zum 31.12.2030 moeglich", fill="black")
    buf = io.BytesIO()
    img.resize((1800, 240)).save(buf, "PNG")
    r = api.post("/api/documents", files={"file": ("brief.png", buf.getvalue(), "image/png")})
    assert r.status_code == 200 and r.json()["chars"] > 10
