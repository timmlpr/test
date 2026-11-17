"""API tests per module (network-free: adapters are replaced by fakes)."""
import hashlib
import hmac
import io
import json
import time

import pyotp
import pytest

from app.adapters import registry
from tests.conftest import Api, register


class FakeXon:
    def __init__(self):
        self.meta = registry.get("xposedornot").meta

    def enabled(self):
        return True

    def breaches(self, email):
        return [{"name": "TestLeak", "domain": "leak.example", "year": "2024", "data_types": ["email", "password"],
                 "description": "x", "verified": True, "reference": "https://leak.example", "records": 10}]


@pytest.fixture
def fake_sources(monkeypatch):
    fake = FakeXon()
    monkeypatch.setitem(registry.ADAPTERS, "xposedornot", fake)
    return fake


# ---------------------------------------------------------------- security basics
def test_csrf_required(api):
    r = api.c.post("/api/auth/login", json={"email": "a@b.de", "password": "x"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "csrf_failed"


def test_security_headers(api):
    r = api.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"


# ---------------------------------------------------------------- M2 auth
def test_register_login_logout(api):
    register(api, verify=False)
    from app.core.mailer import OUTBOX

    assert any("bestätige" in m["subject"].lower() for m in OUTBOX)
    api.post("/api/auth/logout")
    assert api.get("/api/auth/me").status_code == 401
    r = api.post("/api/auth/login", json={"email": "anna@example.org", "password": "falsch-falsch"})
    assert r.status_code == 401
    r = api.post("/api/auth/login", json={"email": "anna@example.org", "password": "sehr-sicheres-pw-1"})
    assert r.status_code == 200 and api.get("/api/auth/me").status_code == 200


def test_email_verification_link(api):
    register(api, verify=False)
    from app.core.mailer import OUTBOX

    tok = [m for m in OUTBOX if "verify-email" in m["text"]][-1]["text"].split("token=")[1].split()[0]
    assert api.post("/api/auth/verify-email", json={"token": tok}).status_code == 200
    me = api.get("/api/auth/me").json()["user"]
    assert me["email_verified"]
    ids = api.get("/api/profile/identifiers").json()
    assert any(i["kind"] == "email" and i["verified"] for i in ids)


def test_totp_and_recovery_codes(api, user):
    secret = api.post("/api/auth/totp/setup").json()["secret"]
    codes = api.post("/api/auth/totp/enable", json={"code": pyotp.TOTP(secret).now()}).json()["recovery_codes"]
    assert len(codes) == 10
    api.post("/api/auth/logout")
    r = api.post("/api/auth/login", json={"email": "anna@example.org", "password": "sehr-sicheres-pw-1"})
    assert r.json() == {"requires_2fa": True}
    assert api.get("/api/auth/me").status_code == 401  # pending session is not a session
    assert api.post("/api/auth/totp/verify", json={"code": codes[0]}).status_code == 200
    api.post("/api/auth/logout")
    api.post("/api/auth/login", json={"email": "anna@example.org", "password": "sehr-sicheres-pw-1"})
    assert api.post("/api/auth/totp/verify", json={"code": codes[0]}).status_code == 400  # single use


def test_password_reset(api, user):
    api.post("/api/auth/logout")
    api.post("/api/auth/password-reset", json={"email": "anna@example.org"})
    from app.core.mailer import OUTBOX

    tok = [m for m in OUTBOX if "reset?token=" in m["text"]][-1]["text"].split("token=")[1].split()[0]
    assert api.post("/api/auth/password-reset/confirm", json={"token": tok, "password": "ganz-neues-pw-22"}).status_code == 200
    assert api.post("/api/auth/login", json={"email": "anna@example.org", "password": "ganz-neues-pw-22"}).status_code == 200


def test_passkey_begin_returns_options(api, user):
    r = api.post("/api/auth/passkey/register/begin")
    assert r.status_code == 200 and "challenge" in r.json()


# ---------------------------------------------------------------- profile
def test_identifier_verification_flows(api, user):
    r = api.post("/api/profile/identifiers", json={"kind": "phone", "value": "+49 170 1234567", "own_data": True}).json()
    assert r["pending_reason"] == "enter_code"
    from app.core.mailer import OUTBOX

    code = [m for m in OUTBOX if m["to"] == "sms"][-1]["text"][-6:]
    assert api.post(f"/api/profile/identifiers/{r['id']}/verify", json={"code": "000000"}).status_code == 400
    assert api.post(f"/api/profile/identifiers/{r['id']}/verify", json={"code": code}).json()["verified"]
    d = api.post("/api/profile/identifiers", json={"kind": "domain", "value": "https://www.anna.example/", "own_data": True}).json()
    assert d["value"] == "anna.example" and d["dns_txt"].startswith("fadeprint-verify=")
    e = api.post("/api/profile/identifiers", json={"kind": "email", "value": "zweit@example.org", "own_data": True}).json()
    assert not e["verified"] and e["pending_reason"] == "check_inbox"


def test_export_and_delete_account(api, user):
    r = api.get("/api/profile/export")
    assert r.status_code == 200 and "identifiers" in r.json() and "password_hash" not in r.json()["user"]
    assert api.delete("/api/profile", json={"confirm": True}).status_code == 200
    assert api.get("/api/auth/me").status_code == 401
    from app.db import SessionLocal
    from app.models import Identifier, User

    with SessionLocal() as db:
        assert db.query(User).count() == 0 and db.query(Identifier).count() == 0


# ---------------------------------------------------------------- M3/M4 scan, breach, results, risk, home
def test_basic_scan_and_results_database(api, user, fake_sources):
    r = api.post("/api/scan/run", json={})
    assert r.status_code == 200, r.text
    assert r.json()["new"] == 1 and "xposedornot" in r.json()["sources"]
    items = api.get("/api/findings").json()["items"]
    assert items[0]["risk"] == "high" and items[0]["url"] and items[0]["found_at"]
    fid = items[0]["id"]
    assert api.get("/api/findings", params={"q": "testleak"}).json()["total"] == 1
    api.patch(f"/api/findings/{fid}", json={"tags": ["wichtig"], "note": "erledige ich morgen"})
    assert api.get("/api/findings", params={"tag": "wichtig"}).json()["total"] == 1
    api.patch(f"/api/findings/{fid}", json={"status": "trash"})
    assert api.get("/api/findings").json()["total"] == 0
    assert api.get("/api/findings", params={"status": "trash"}).json()["total"] == 1
    # rescan does not duplicate (fingerprint)
    api.patch(f"/api/findings/{fid}", json={"status": "open"})
    api.post("/api/scan/run", json={})
    assert api.get("/api/findings").json()["total"] == 1


def test_free_breach_check_once_per_month(api, user, fake_sources):
    assert api.post("/api/breach/check").status_code == 200
    r = api.post("/api/breach/check")
    assert r.status_code == 429 and r.json()["detail"]["code"] == "plan_limit"


def test_source_down_gives_clean_notice(api, user, monkeypatch):
    from app.adapters.base import SourceUnavailable

    class Down(FakeXon):
        def breaches(self, email):
            raise SourceUnavailable("xposedornot", "unreachable:ConnectTimeout")

    monkeypatch.setitem(registry.ADAPTERS, "xposedornot", Down())
    r = api.post("/api/breach/check")
    assert r.status_code == 200 and r.json()["errors"][0]["reason"].startswith("unreachable")


def test_home_and_risk(api, user, fake_sources):
    h = api.get("/api/home").json()
    assert h["next_step"]["key"] == "first_scan"
    api.post("/api/scan/run", json={})
    h = api.get("/api/home").json()
    assert h["risk"]["score"] > 0 and h["next_step"]["key"] == "change_password"
    assert api.get("/api/risk/history").json()


def test_deep_scan_is_premium(api, user):
    assert api.post("/api/scan/run", json={"deep": True}).status_code == 402


# ---------------------------------------------------------------- M5 deletion + reports
def test_deletion_request_flow(api, user, fake_sources):
    api.post("/api/scan/run", json={})
    fid = api.get("/api/findings").json()["items"][0]["id"]
    r = api.post("/api/requests", json={"kind": "art17", "recipient": "Leak GmbH", "recipient_email": "privacy@leak.example",
                                        "finding_id": fid, "template": "breach"}).json()
    assert "Art. 17" in r["subject"] and "Anna Schmidt" in r["body"] and r["mailto"].startswith("mailto:privacy@leak.example")
    assert "keine Rechtsberatung" in r["disclaimer"]
    r = api.patch(f"/api/requests/{r['id']}", json={"status": "sent"}).json()
    assert r["status"] == "sent" and r["due_at"]
    pdf = api.get(f"/api/requests/{r['id']}/pdf")
    assert pdf.content[:4] == b"%PDF"
    api.patch(f"/api/requests/{r['id']}", json={"status": "done"})
    assert api.get("/api/findings", params={"status": "done"}).json()["total"] == 1


def test_reports_preview_locked_for_free(api, user, fake_sources):
    api.post("/api/scan/run", json={})
    p = api.get("/api/reports/preview").json()
    assert p["summary"]["total"] == 1 and p["summary"]["high"] == 1 and not p["unlocked"]
    assert api.post("/api/reports").status_code == 402


def test_reports_full_premium_pdf_xlsx_compare(api, premium, fake_sources):
    api.post("/api/scan/run", json={})
    a = api.post("/api/reports").json()
    fid = api.get("/api/findings").json()["items"][0]["id"]
    api.patch(f"/api/findings/{fid}", json={"status": "done"})
    b = api.post("/api/reports").json()
    assert b["version"] == 2
    assert api.get(f"/api/reports/{a['id']}/pdf").content[:4] == b"%PDF"
    assert api.get(f"/api/reports/{a['id']}/xlsx").content[:2] == b"PK"
    cmp = api.get(f"/api/reports/compare/{a['id']}/{b['id']}").json()
    assert cmp["score_delta"] < 0 and len(cmp["resolved"]) == 1


# ---------------------------------------------------------------- M6 billing (Stripe webhook signature, test mode)
def _signed(payload: dict, secret: str) -> tuple[bytes, str]:
    body = json.dumps(payload).encode()
    ts = int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return body, f"t={ts},v1={sig}"


def test_plans_endpoint():
    api = Api()
    p = api.get("/api/billing/plans").json()
    assert p["premium"]["month"] == 3.99 and p["family"]["table"][0]["total"] == 5.99 and p["most_popular"] is None


def test_webhook_rejects_bad_signature(api, monkeypatch):
    from app.settings import get_settings

    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", "whsec_test")
    r = api.c.post("/api/billing/webhook", content=b"{}", headers={"stripe-signature": "t=1,v1=bad"})
    assert r.status_code == 400


def test_webhook_activates_subscription_and_one_time_report(api, user, monkeypatch, fake_sources):
    from app.settings import get_settings

    monkeypatch.setattr(get_settings(), "stripe_webhook_secret", "whsec_test")
    ev = {"id": "evt_1", "object": "event", "type": "checkout.session.completed",
          "data": {"object": {"id": "cs_1", "object": "checkout.session", "mode": "subscription", "subscription": "sub_1",
                              "metadata": {"user_id": user["id"], "product": "premium", "interval": "month", "persons": "1"}}}}
    body, sig = _signed(ev, "whsec_test")
    assert api.c.post("/api/billing/webhook", content=body, headers={"stripe-signature": sig}).json()["result"] == "ok"
    assert api.c.post("/api/billing/webhook", content=body, headers={"stripe-signature": sig}).json()["result"] == "duplicate"
    assert api.get("/api/auth/me").json()["user"]["tier"] == "premium"
    ev2 = {"id": "evt_2", "object": "event", "type": "customer.subscription.deleted", "data": {"object": {"id": "sub_1", "object": "subscription"}}}
    body, sig = _signed(ev2, "whsec_test")
    api.c.post("/api/billing/webhook", content=body, headers={"stripe-signature": sig})
    assert api.get("/api/auth/me").json()["user"]["tier"] == "free"
    ev3 = {"id": "evt_3", "object": "event", "type": "checkout.session.completed",
           "data": {"object": {"id": "cs_3", "object": "checkout.session", "mode": "payment", "payment_status": "paid", "amount_total": 900,
                               "metadata": {"user_id": user["id"], "product": "one_time_report"}}}}
    body, sig = _signed(ev3, "whsec_test")
    api.c.post("/api/billing/webhook", content=body, headers={"stripe-signature": sig})
    api.post("/api/scan/run", json={})
    assert api.get("/api/reports/preview").json()["unlocked"]
    assert api.post("/api/reports").json()["kind"] == "onetime"
    assert api.post("/api/reports").status_code == 402  # consumed


def test_client_cannot_self_upgrade(api, user):
    api.patch("/api/profile/settings", json={"plan": "premium"})
    assert api.get("/api/auth/me").json()["user"]["plan"] == "free"


def test_referral_rewards_both(api, monkeypatch):
    ref = register(api, "ref@example.org", "Rita Referer")
    code = api.get("/api/billing/referral").json()["code"]
    api.post("/api/auth/logout")
    r = api.post("/api/auth/register", json={"email": "new@example.org", "password": "sehr-sicheres-pw-1", "accept_terms": True,
                                            "referral_code": code})
    new_id = r.json()["user"]["id"]
    from app.db import SessionLocal
    from app.models import User
    from app.modules.billing import handle_event

    with SessionLocal() as db:
        handle_event(db, {"id": "evt_r", "type": "checkout.session.completed", "data": {"object": {
            "id": "cs_r", "mode": "subscription", "subscription": "sub_r",
            "metadata": {"user_id": new_id, "product": "premium", "interval": "month", "persons": "1"}}}})
        assert db.get(User, ref["id"]).free_months_credit == 1


def test_voucher(api, user):
    from app.db import SessionLocal
    from app.models import Voucher

    with SessionLocal() as db:
        db.add(Voucher(code="TEST1", free_months=2, max_uses=1))
        db.commit()
    assert api.post("/api/billing/voucher", json={"code": "test1"}).json()["added"] == 2
    assert api.post("/api/billing/voucher", json={"code": "TEST1"}).status_code == 400


def test_family_invite_join_child(api):
    owner = register(api, "o@example.org", "Olga Owner")
    from app.db import SessionLocal
    from app.models import FamilyGroup, User

    with SessionLocal() as db:
        db.get(User, owner["id"]).plan = "family_owner"
        db.add(FamilyGroup(owner_id=owner["id"], seats=3))
        db.commit()
    link = api.post("/api/family/invite", json={"label": "Mia"}).json()["invite_link"]
    assert api.post("/api/family/child", json={"label": "Kind", "login_email": "kind@example.org", "password": "kinder-pw-12345",
                                               "birth_year": 2014, "guardian_consent": False}).status_code == 400
    assert api.post("/api/family/child", json={"label": "Kind", "login_email": "kind@example.org", "password": "kinder-pw-12345",
                                               "birth_year": 2014, "guardian_consent": True}).status_code == 200
    api.post("/api/auth/logout")
    register(api, "m@example.org", "Mia Member")
    tok = link.split("token=")[1]
    assert api.post("/api/family/join", json={"token": tok, "consent": False}).status_code == 400
    assert api.post("/api/family/join", json={"token": tok, "consent": True}).status_code == 200
    assert api.get("/api/auth/me").json()["user"]["plan"] == "family_member"


# ---------------------------------------------------------------- M7 tools
def test_scam_check_rules_only_offline(api, user):
    r = api.post("/api/scam/check", json={"text": "Letzte Mahnung! Zahlen Sie sofort mit Gutscheinkarte: http://amazon-konto.xyz"}).json()
    assert r["light"] == "red" and r["summary"] and any(x["key"] == "payment" for x in r["reasons"])
    assert "safe_browsing" in r["missing_sources"]


def test_domain_check_validates(api, user):
    assert api.post("/api/domain/check", json={"domain": "not a domain"}).status_code == 400
    assert api.post("/api/domain/check", json={"domain": "https://www.example.org/x"}).json()["domain"] == "example.org"


def test_image_analyze_and_strip(api, user):
    from PIL import Image

    img = Image.new("RGB", (512, 512), "white")
    exif = Image.Exif()
    exif[0x010F] = "TestCam"
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    r = api.post("/api/image/analyze", files={"file": ("a.jpg", buf.getvalue(), "image/jpeg")}, data={"own_image": "true"}).json()
    assert r["exif"]["Make"] == "TestCam" and r["ela_image"].startswith("data:image/png") and r["stored"] is False
    s = api.post("/api/image/strip", files={"file": ("a.jpg", buf.getvalue(), "image/jpeg")})
    assert not Image.open(io.BytesIO(s.content)).getexif()


# ---------------------------------------------------------------- M8/M9
def test_checklists_feed_risk(api, user, fake_sources):
    api.post("/api/scan/run", json={})
    before = api.get("/api/risk").json()["score"]
    r = api.patch("/api/checklist", json={"item": "two_factor", "done": True}).json()
    assert r["done"] == 1 and r["risk"]["score"] < before
    s = api.patch("/api/social", json={"platform": "instagram", "item": "private_account", "done": True}).json()
    assert s["done"] == 1
    assert api.patch("/api/social", json={"platform": "myspace", "item": "x", "done": True}).status_code == 400


def test_monitor_premium_and_diff(api, premium, fake_sources):
    api.put("/api/monitor/settings", json={"enabled": True, "frequency": "daily", "min_severity": "low", "quiet_start": 22,
                                           "quiet_end": 7, "push": False, "email": True})
    r = api.post("/api/monitor/run").json()
    assert r["new"] == 1 and r["alerted"] == 1
    assert api.post("/api/monitor/run").json()["new"] == 0
    n = api.get("/api/notifications").json()
    assert n["unread"] >= 1
    t = api.get("/api/timeline").json()
    assert any(e["kind"] == "finding" for e in t["items"])


def test_monitor_requires_premium(api, user):
    r = api.put("/api/monitor/settings", json={"enabled": True, "frequency": "daily", "min_severity": "low", "quiet_start": 22,
                                               "quiet_end": 7, "push": False, "email": True})
    assert r.status_code == 402


# ---------------------------------------------------------------- M10
def test_subscription_guard_mbox(api, premium):
    mbox = (b"From a@x Mon Jan  1 00:00:00 2026\nFrom: Stream <billing@stream.example>\nSubject: Rechnung\nDate: Mon, 1 Jan 2026 10:00:00 +0100\n\n"
            b"Dein Abo monatlich 9,99 EUR\n\nFrom b@x Mon Jan  1 00:00:00 2026\nFrom: news@shop.example\nSubject: Sale\n"
            b"List-Unsubscribe: <https://shop.example/u>\n\nAngebote\n")
    r = api.post("/api/subs/upload", files={"file": ("export.mbox", mbox, "application/mbox")}).json()
    assert r["found"] == 2
    s = api.get("/api/subs").json()
    assert s["monthly_cost"] == 9.99 and s["counts"]["newsletter"] == 1
    assert api.get("/api/subs/xlsx").content[:2] == b"PK"


def test_document_scanner_txt(api, premium):
    r = api.post("/api/documents", files={"file": ("vertrag.txt", "Kündigung bis zum 31.12.2030 möglich. IBAN DE89 3704 0044 0532 0130 00".encode())}).json()
    assert r["deadlines"][0]["date"] == "2030-12-31" and "iban" in r["sensitive"]
    assert len(api.get("/api/documents").json()["reminders"]) == 1
    assert api.delete(f"/api/documents/{r['id']}").status_code == 200


def test_estate_e2e_ciphertext_only(api, premium):
    r = api.put("/api/estate", json={"ciphertext": "QUJD", "salt": "c2FsdA==", "iv": "aXY=", "trusted_email": "t@example.org",
                                     "unlock_delay_days": 3})
    assert r.status_code == 200
    from app.db import SessionLocal
    from app.models import EstateVault

    with SessionLocal() as db:
        tok = db.query(EstateVault).first().unlock_token
    w = api.post("/api/estate/unlock-request", json={"token": tok}).json()
    assert w["status"] == "waiting"
    assert api.post("/api/estate/veto").status_code == 200


# ---------------------------------------------------------------- M11
def test_graph_contains_only_own_data(api, premium, fake_sources):
    api.post("/api/scan/run", json={})
    g = api.get("/api/graph").json()
    types = {n["type"] for n in g["nodes"]}
    assert {"me", "email", "name", "breach"} <= types


# ---------------------------------------------------------------- growth + admin
def test_waitlist_double_opt_in(api):
    assert api.post("/api/waitlist", json={"email": "w@example.org", "consent": False}).status_code == 400
    api.post("/api/waitlist", json={"email": "w@example.org", "consent": True})
    from app.core.mailer import OUTBOX

    tok = [m for m in OUTBOX if "waitlist/confirm" in m["text"]][-1]["text"].split("token=")[1].split()[0]
    assert api.post("/api/waitlist/confirm", json={"token": tok}).status_code == 200


def test_admin_requires_2fa(api):
    u = register(api, "adm@example.org", "Ada Admin")
    from app.db import SessionLocal
    from app.models import User

    with SessionLocal() as db:
        db.get(User, u["id"]).role = "admin"
        db.commit()
    assert api.get("/api/admin/stats").json()["detail"]["code"] == "admin_requires_2fa"
    secret = api.post("/api/auth/totp/setup").json()["secret"]
    api.post("/api/auth/totp/enable", json={"code": pyotp.TOTP(secret).now()})
    assert api.get("/api/admin/stats").status_code == 200
    srcs = api.get("/api/admin/sources").json()
    assert any(s["name"] == "google_cse" and not s["enabled"] for s in srcs)


def test_abuse_report_public(api):
    assert api.post("/api/abuse", json={"message": "Jemand hat vermutlich nach mir gesucht."}).status_code == 200


def test_retention_job():
    from datetime import timedelta

    from app.db import SessionLocal
    from app.jobs import retention
    from app.models import WaitlistEntry, now

    with SessionLocal() as db:
        db.add(WaitlistEntry(email="old@example.org", email_hash="h", created_at=now() - timedelta(days=8)))
        db.commit()
    assert retention()["waitlist"] == 1
