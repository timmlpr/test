"""Unit tests: risk score, scam rule engine, anonymiser, pricing logic, quiet hours, document parsing."""
from datetime import datetime, timedelta

import pytest

from app.core.anonymizer import anonymize, deanonymize
from app.core.plans import family_price, premium_price, price_cents, vat_breakdown
from app.modules.monitor import in_quiet_hours
from app.modules.risk_rules import CAPS, F, actions_by_impact, compute, light
from app.modules.scam_rules import evaluate, registrable, url_signals
from app.modules.vault import classify_message, detect_sensitive, extract_deadlines

NOW = datetime(2026, 11, 1)


# ---------------------------------------------------------------- risk score
def test_empty_profile_scores_zero_and_green():
    r = compute([], now=NOW)
    assert r.score == 0 and r.light == "green"


def test_light_thresholds():
    assert light(33) == "green" and light(34) == "yellow" and light(66) == "yellow" and light(67) == "red"


def test_password_leak_weighs_more_than_email_leak():
    a = compute([F("1", "breach_check", "low", ("email",), NOW - timedelta(days=2000))], now=NOW)
    b = compute([F("1", "breach_check", "high", ("email", "password"), NOW - timedelta(days=2000))], now=NOW)
    assert b.score > a.score
    assert b.factors["leaks"] == 10 and b.factors["sensitivity"] == 7


def test_caps_are_respected():
    many = [F(str(i), "privacy_scan", "high", ("address", "phone", "payment", "id_document", "health"), NOW) for i in range(50)]
    r = compute(many, now=NOW)
    for k, cap in CAPS.items():
        if k != "protection":
            assert r.factors[k] <= cap
    assert r.score == sum(r.factors.values()) == 75 and r.light == "red"


def test_not_attributable_findings_do_not_count():
    r = compute([F("1", "privacy_scan", "high", ("address",), NOW, attributable=False)], now=NOW)
    assert r.score == 0


def test_checklist_reduces_score_but_not_below_zero():
    fs = [F("1", "privacy_scan", "medium", ("phone",), NOW)]
    full = compute(fs, 8, 8, NOW)
    none = compute(fs, 0, 8, NOW)
    assert full.score < none.score and full.factors["protection"] == -15 and full.score >= 0


def test_recency_counts_only_last_24_months():
    old = compute([F("1", "breach_check", "low", ("email",), NOW - timedelta(days=900))], now=NOW)
    new = compute([F("1", "breach_check", "low", ("email",), NOW - timedelta(days=30))], now=NOW)
    assert new.factors["recency"] == 2 and old.factors["recency"] == 0


def test_actions_sorted_by_impact():
    fs = [F("a", "privacy_scan", "low", ("username",), NOW - timedelta(days=1000)),
          F("b", "breach_check", "high", ("password", "email"), NOW)]
    acts = actions_by_impact(fs, 0, 8, NOW)
    assert acts[0]["finding_id"] == "b"
    assert acts[0]["impact"] >= acts[1]["impact"]


# ---------------------------------------------------------------- scam rules
def test_registrable_domain():
    assert registrable("login.paypal.com") == "paypal.com"
    assert registrable("shop.example.co.uk") == "example.co.uk"


def test_brand_mismatch_detected():
    names = [n for n, _ in url_signals("https://paypal.com.secure-login.xyz/verify")]
    assert "brand_mismatch" in names and "risky_tld" in names


def test_official_brand_domain_not_flagged():
    assert url_signals("https://www.paypal.com/de/signin") == []


def test_phishing_sms_is_red():
    r = evaluate("Ihr Paket wurde nicht zugestellt. Adresse bestätigen innerhalb von 24 Stunden: http://dhl-paket-info.top/x")
    assert r.light == "red"
    assert {"package", "urgency", "no_https", "risky_tld", "brand_mismatch"} <= set(r.reasons)


def test_family_trick_flagged():
    r = evaluate("Hallo Mama, mein Handy ist kaputt, das ist meine neue Nummer. Kannst du kurz was überweisen?")
    assert "family_trick" in r.reasons and r.light in ("yellow", "red")


def test_normal_message_green():
    assert evaluate("Hi, treffen wir uns morgen um 10 im Café?").light == "green"


def test_blocklist_hit_forces_red():
    r = evaluate("", "https://example.org", [("blocklisted", 10)])
    assert r.light == "red"


# ---------------------------------------------------------------- anonymiser
def test_anonymiser_replaces_and_restores():
    text = "Ich bin Anna Schmidt, wohne Lindenstraße 5, 10115 Berlin, mail anna@example.org, Tel +49 170 1234567."
    anon, mapping = anonymize(text, ["Anna Schmidt"])
    for secret in ("Anna Schmidt", "Lindenstraße 5", "anna@example.org", "+49 170 1234567", "10115 Berlin"):
        assert secret not in anon
    assert deanonymize(anon, mapping) == text


def test_anonymiser_catches_unknown_names_and_iban():
    anon, m = anonymize("Bitte überweise an Max Mustermann, IBAN DE89 3704 0044 0532 0130 00.")
    assert "Max Mustermann" not in anon and "DE89" not in anon
    assert any(v == "Max Mustermann" for v in m.values())


# ---------------------------------------------------------------- pricing
def test_premium_prices():
    assert premium_price("month") == 3.99 and premium_price("year") == 39.99
    assert price_cents("premium", "year") == 3999


@pytest.mark.parametrize("persons,total", [(2, 5.99), (3, 6.99), (6, 9.99)])
def test_family_monthly(persons, total):
    p = family_price(persons)
    assert p["total"] == total
    assert p["per_person"] == round(total / persons, 2)


def test_family_annual_two_months_free():
    assert family_price(2, "year")["total"] == round(5.99 * 10, 2)


def test_family_bounds():
    with pytest.raises(ValueError):
        family_price(7)
    with pytest.raises(ValueError):
        family_price(1)


def test_one_time_report_price_and_vat_small_business():
    assert price_cents("one_time_report") == 900
    assert vat_breakdown(3.99)["vat"] == 0.0  # small_business=true in config


# ---------------------------------------------------------------- misc
def test_quiet_hours_overnight():
    assert in_quiet_hours(23, 22, 7) and in_quiet_hours(3, 22, 7) and not in_quiet_hours(12, 22, 7)
    assert in_quiet_hours(13, 12, 14) and not in_quiet_hours(15, 12, 14)


def test_deadline_extraction():
    d = extract_deadlines("Der Vertrag endet am 31.03.2027. Kündigung bis zum 01.01.2027 möglich. Geburtstag 05.05.1990.")
    dates = [x["date"] for x in d]
    assert "2027-03-31" in dates and "2027-01-01" in dates and "1990-05-05" not in dates


def test_sensitive_detection():
    assert "iban" in detect_sensitive("IBAN DE89 3704 0044 0532 0130 00")


def test_mail_classifier():
    sub = classify_message({"from": "Stream <billing@stream.example>", "subject": "Deine Rechnung"}, "Abo monatlich 12,99 €")
    assert sub["category"] == "subscription" and sub["amount"] == 12.99
    nl = classify_message({"from": "news@shop.example", "subject": "Angebote", "list-unsubscribe": "<https://shop.example/u>"}, "")
    assert nl["category"] == "newsletter" and nl["unsubscribe"] == "https://shop.example/u"
    assert classify_message({"from": "freund@example.org", "subject": "Hi"}, "Wie gehts?") is None
