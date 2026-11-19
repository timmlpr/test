"""Unit tests: confidence scoring, context resolution, question detection, analyzers, text utils, SRS, crypto,
quota manager."""
from datetime import datetime, timedelta

import pytest

from app.crypto import mask, open_secret, seal_secret
from app.learn.srs import review
from app.live import analyzers
from app.live.confidence import PRUEFEN, SICHER, UNSICHER, Evidence, score
from app.live.context import LiveContext, is_followup, resolve
from app.live.questions import detect
from app.models import Flashcard
from app.text import find_statutes, sentences, simhash, simhash_distance, terms


# ---------------------------------------------------------------- confidence
def test_no_evidence_is_unsicher_keine_quelle():
    c = score("Die Frist beträgt drei Jahre.", [])
    assert c.level == UNSICHER and c.percent <= 15 and "keine Quelle" in c.why


def test_direct_statute_support_is_sicher():
    ev = [Evidence("Die regelmäßige Verjährungsfrist beträgt drei Jahre.", 1.0, "bgb:195", True, True),
          Evidence("Regelmäßige Verjährung: drei Jahre nach § 195 BGB.", 0.8, "doc:1")]
    c = score("Die regelmäßige Verjährungsfrist beträgt drei Jahre.", ev,
              question="Wie lange ist die regelmäßige Verjährungsfrist?")
    assert c.level == SICHER and c.percent >= 75
    assert "Gesetzestext" in c.why


def test_unsupported_answer_is_capped():
    ev = [Evidence("Die Bilanz stellt Aktiva und Passiva gegenüber.", 0.6, "doc:1")]
    c = score("Die Verjährung beträgt zehn Jahre bei Grundstücken.", ev, question="Wie lange dauert die Verjährung?")
    assert c.level in (PRUEFEN, UNSICHER) and c.percent <= 60


def test_question_not_covered_caps_confidence():
    ev = [Evidence("Der Käufer muss den Kaufpreis zahlen.", 0.9, "doc:1"), Evidence("x y z Kaufpreis", 0.5, "doc:2")]
    c = score("Der Käufer muss den Kaufpreis zahlen.", ev, question="Wann verjähren Mängelansprüche beim Kauf?")
    assert c.percent <= 70


def test_correction_and_model_claims_cap():
    ev = [Evidence("Die regelmäßige Verjährungsfrist beträgt drei Jahre.", 1.0, "bgb:195", True, True)]
    assert score("Die regelmäßige Verjährungsfrist beträgt drei Jahre.", ev, corrected=True).level == UNSICHER
    assert score("Die regelmäßige Verjährungsfrist beträgt drei Jahre.", ev, support_claim="none").percent <= 40


# ---------------------------------------------------------------- context
def _ctx(*texts):
    ctx = LiveContext()
    t = 0.0
    for x in texts:
        ctx.add(t, t + 8, x)
        t += 10
    return ctx


def test_followup_resolves_statute_and_topic():
    ctx = _ctx("Heute geht es um den Kaufvertrag nach § 433 BGB.",
               "Der Käufer muss den Kaufpreis zahlen, der Verkäufer muss übereignen.",
               "Beim Kaufvertrag entstehen Ansprüche auf Kaufpreis und Übereignung.")
    rq = resolve("Und was gilt dann für die Verjährung?", ctx)
    assert rq.is_followup
    assert any(s.law == "BGB" and s.norm == "433" for s in rq.statutes)
    assert "Kaufvertrag" in rq.query or "kaufvertrag" in rq.query.lower()
    assert "Verjährung" in rq.query  # the question itself is kept


def test_law_less_norm_uses_default_law():
    ctx = _ctx("Wir sind im BGB, § 195 BGB regelt die Frist.")
    rq = resolve("Was sagt § 199 dazu?", ctx)
    assert any(s.law == "BGB" and s.norm == "199" for s in rq.statutes)


def test_standalone_question_is_not_followup():
    assert not is_followup("Welche Pflichten hat der Käufer aus einem Kaufvertrag nach § 433 BGB?", True)
    assert is_followup("Und warum?", True)
    assert not is_followup("Und warum?", False)


# ---------------------------------------------------------------- question detection
def test_detects_direct_and_implicit_questions():
    qs = detect("Der Kaufvertrag ist zentral. Welche Pflichten hat der Käufer? Überlegen Sie mal, wer die Gefahr trägt.")
    texts = [q.text for q in qs]
    assert any("Pflichten hat der Käufer" in t for t in texts)
    assert any("Überlegen Sie" in t for t in texts)


def test_filters_organisational_and_rhetorical():
    assert detect("Können Sie mich hinten hören?") == []
    assert detect("Haben Sie noch Fragen?") == []
    rhet = detect("Warum ist das so wichtig für die Bilanz? Weil der Gläubigerschutz im Vordergrund steht.")
    assert all(q.score < 0.6 for q in rhet)


def test_addressed_to_user_by_call_name():
    qs = detect("Herr Lepper, was ist der Unterschied zwischen Gewinn und Überschuss?", ["Herr Lepper"])
    assert qs and qs[0].addressed_to_user and qs[0].score >= 0.9


# ---------------------------------------------------------------- analyzers
def test_keyword_alerts():
    assert "klausurrelevant" in analyzers.keyword_alerts("Das ist klausurrelevant!")
    assert "kommt dran" in analyzers.keyword_alerts("So etwas kommt garantiert dran.")
    assert "merken" in analyzers.keyword_alerts("Merken Sie sich bitte diese Definition.")
    assert analyzers.keyword_alerts("Heute ist schönes Wetter.") == []


def test_number_keeper():
    found = {(n.kind, n.value) for n in analyzers.numbers(
        "Die Grenze liegt bei 800.000 Euro Umsatz, der Satz ist 19 Prozent und die Abgabe bis zum 15. Januar.")}
    kinds = {k for k, _ in found}
    assert {"amount", "percent", "deadline"} <= kinds


def test_correction_detects_number_conflict():
    sig = analyzers.detect_correction("Buchungsbelege sind zehn Jahre aufzubewahren.", "Wie lange Buchungsbelege aufbewahren?",
                                      "Achtung, Buchungsbelege müssen nur noch acht Jahre aufbewahrt werden.")
    assert sig is not None and sig.strength >= 0.8


def test_no_correction_on_unrelated_speech():
    assert analyzers.detect_correction("Die Frist beträgt drei Jahre.", "Wie lange ist die Frist?",
                                       "Nein, wir machen jetzt zehn Minuten Pause.") is None


def test_suggestions():
    s = analyzers.suggest_questions(["Kaufvertrag"], "§ 433 BGB", ["Gefahrübergang"], "kaufvertrag käufer")
    assert any("§ 433 BGB" in q for q in s) and len(s) <= 4


# ---------------------------------------------------------------- text
def test_statute_regex_variants():
    refs = find_statutes("Nach § 433 Abs. 2 BGB und § 15 EStG sowie Art. 3 GG; vgl. auch § 199.")
    labels = [r.label for r in refs]
    assert "§ 433 Abs. 2 BGB" in labels and "§ 15 EStG" in labels
    assert any(r.norm == "199" and r.law is None for r in refs)


def test_sentences_keep_abbreviations_and_dates():
    s = sentences("Nach § 433 Abs. 2 BGB zahlt der Käufer. Abgabe am 15.01.2027 bis 12 Uhr. Fertig ist das.")
    assert s[0].endswith("zahlt der Käufer.") and len(s) == 3


def test_terms_match_inflections():
    assert set(terms("verjährt")) & set(terms("Verjährungsfrist"))
    assert set(terms("Pflichten")) & set(terms("verpflichtet"))


def test_simhash_near_duplicates():
    a = "Der Kaufvertrag verpflichtet den Verkäufer zur Übergabe und Übereignung der Sache. " * 5
    b = a.replace("Sache", "Sache,", 1)
    c = "Die Bilanz stellt Vermögen und Kapital gegenüber, Aktiva gleich Passiva. " * 5
    assert simhash_distance(simhash(a), simhash(b)) <= 3
    assert simhash_distance(simhash(a), simhash(c)) > 12


# ---------------------------------------------------------------- SRS, crypto
def test_sm2_progression_and_lapse():
    card = Flashcard(front="a", back="b", ease=2.5, interval_days=0, repetitions=0, lapses=0)
    now = datetime(2026, 11, 1)
    review(card, 4, now)
    assert card.interval_days == 1
    review(card, 5, now)
    assert card.interval_days == 6
    review(card, 4, now)
    assert card.interval_days >= 14
    review(card, 1, now)
    assert card.repetitions == 0 and card.lapses == 1 and card.due < now + timedelta(hours=1)


def test_envelope_encryption_binds_context():
    sealed = seal_secret("gsk_supersecretkey1234", "user:1:groq")
    assert "supersecret" not in sealed
    assert open_secret(sealed, "user:1:groq") == "gsk_supersecretkey1234"
    with pytest.raises(Exception):
        open_secret(sealed, "user:2:groq")
    assert mask("gsk_supersecretkey1234") == "gsk_…1234"
