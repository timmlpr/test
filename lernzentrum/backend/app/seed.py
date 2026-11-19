"""Demo mode: a fully clickable account with THM-style modules, timetable, slides, a processed lecture, answers,
flashcards, glossary, deadlines, announcements and an inbox review item. Content is original sample material."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .calendar_sync import TZ
from .db import utcnow
from .learn.core import build_glossary, build_package
from .live.pipeline import finalize_recording, ingest_segments
from .models import Announcement, ConsentLog, Deadline, Document, Event, InboxItem, Lecture, Module, Recording, User
from .pdfgen import slides_pdf
from .retrieval.index import index_document
from .security import hash_password
from .statutes import seed_demo_norms
from .storage import sha256, storage
from .text import simhash

DEMO_EMAIL = "demo@lernzentrum.app"
DEMO_PASSWORD = "Lernzentrum2026"

MODULES = [
    ("Grundlagen im Schuld- und Sachenrecht", "SSR", "#2F5D8C", "Prof. Dr. Weber", 0, (8, 15)),
    ("Buchführung", "BF", "#3E8E7E", "Prof. Dr. Schäfer", 1, (10, 0)),
    ("Grundlagen des Steuerrechts", "GStR", "#8E5B3E", "Prof. Dr. Krüger", 2, (8, 15)),
    ("Grundlagen BWL", "BWL", "#6B4E9B", "Prof. Dr. Neumann", 3, (11, 45)),
    ("Einstieg in die Steuerberatung", "ESB", "#B5523B", "Prof. Dr. Lorenz", 4, (14, 0)),
]

SLIDES = {
    "SSR": ("Kaufrecht und Verjährung", [
        "Kaufvertrag – Grundlagen. Der Kaufvertrag ist in § 433 BGB geregelt. Er ist ein gegenseitiger Vertrag: Die "
        "Pflichten von Verkäufer und Käufer stehen im Gegenseitigkeitsverhältnis.",
        "Pflichten des Verkäufers. Nach § 433 Abs. 1 BGB muss der Verkäufer die Sache übergeben, das Eigentum "
        "verschaffen und die Sache frei von Sach- und Rechtsmängeln verschaffen.",
        "Pflichten des Käufers. Nach § 433 Abs. 2 BGB muss der Käufer den vereinbarten Kaufpreis zahlen und die "
        "gekaufte Sache abnehmen.",
        "Trennungs- und Abstraktionsprinzip. Der Kaufvertrag ist das Verpflichtungsgeschäft. Die Übereignung nach "
        "§ 929 BGB ist das Verfügungsgeschäft. Die Übereignung ist in ihrer Wirksamkeit unabhängig vom Kaufvertrag.",
        "Regelmäßige Verjährung. Die regelmäßige Verjährungsfrist beträgt drei Jahre (§ 195 BGB). Sie beginnt mit dem "
        "Schluss des Jahres, in dem der Anspruch entstanden ist und der Gläubiger von den Umständen Kenntnis erlangt "
        "hat (§ 199 Abs. 1 BGB).",
        "Verjährung von Mängelansprüchen. Mängelansprüche beim Kauf beweglicher Sachen verjähren grundsätzlich in zwei "
        "Jahren (§ 438 Abs. 1 Nr. 3 BGB). Die Frist beginnt mit der Ablieferung der Sache (§ 438 Abs. 2 BGB).",
        "Gutachtenstil. Aufbau: Obersatz, Definition, Subsumtion, Ergebnis. Beispiel für einen Obersatz: V könnte "
        "gegen K einen Anspruch auf Zahlung des Kaufpreises aus § 433 Abs. 2 BGB haben.",
        "Gefahrübergang. Mit der Übergabe der verkauften Sache geht die Gefahr des zufälligen Untergangs auf den "
        "Käufer über (§ 446 BGB).",
    ]),
    "BF": ("Buchführungspflicht und Grundlagen", [
        "Buchführungspflicht nach Handelsrecht. Jeder Kaufmann ist verpflichtet, Bücher zu führen (§ 238 Abs. 1 HGB). "
        "Kaufmann ist, wer ein Handelsgewerbe betreibt (§ 1 Abs. 1 HGB).",
        "Befreiung für kleine Einzelkaufleute. Einzelkaufleute mit nicht mehr als 800.000 Euro Umsatzerlösen und "
        "80.000 Euro Jahresüberschuss sind von der Buchführungspflicht befreit (§ 241a HGB).",
        "Steuerliche Buchführungspflicht. Derivative Pflicht: Wer nach anderen Gesetzen Bücher führen muss, muss dies "
        "auch für die Besteuerung (§ 140 AO). Originäre Pflicht nach § 141 AO bei mehr als 800.000 Euro Umsatz oder "
        "mehr als 80.000 Euro Gewinn.",
        "Bilanz. Die Bilanz stellt Vermögen (Aktiva) und Kapital (Passiva) gegenüber. Bilanzgleichung: Aktiva gleich "
        "Passiva, Vermögen gleich Eigenkapital plus Fremdkapital.",
        "Buchungssatz. Ein Buchungssatz nennt zuerst das Soll-Konto, dann das Haben-Konto. Beispiel: Wareneinkauf auf "
        "Ziel über 1.000 Euro: Wareneingang an Verbindlichkeiten aus Lieferungen und Leistungen.",
        "Umsatzsteuer in der Buchführung. Der allgemeine Steuersatz beträgt 19 Prozent, der ermäßigte Steuersatz 7 "
        "Prozent (§ 12 UStG). Vorsteuer ist ein Forderungskonto gegenüber dem Finanzamt.",
        "Aufbewahrungsfristen. Bücher und Jahresabschlüsse sind zehn Jahre aufzubewahren, Buchungsbelege acht Jahre, "
        "empfangene und abgesandte Handelsbriefe sechs Jahre (§ 257 HGB, § 147 AO).",
    ]),
    "GStR": ("Einführung Steuerrecht", [
        "Steuerbegriff. Steuern sind Geldleistungen, die nicht eine Gegenleistung für eine besondere Leistung "
        "darstellen und von einem öffentlich-rechtlichen Gemeinwesen zur Erzielung von Einnahmen allen auferlegt "
        "werden (§ 3 Abs. 1 AO).",
        "Einkunftsarten. Das Einkommensteuergesetz kennt sieben Einkunftsarten (§ 2 Abs. 1 EStG): Land- und "
        "Forstwirtschaft, Gewerbebetrieb, selbständige Arbeit, nichtselbständige Arbeit, Kapitalvermögen, Vermietung "
        "und Verpachtung sowie sonstige Einkünfte.",
        "Gewinneinkünfte und Überschusseinkünfte. Bei den ersten drei Einkunftsarten ist der Gewinn maßgeblich, bei "
        "den übrigen der Überschuss der Einnahmen über die Werbungskosten (§ 2 Abs. 2 EStG).",
        "Einkünfte aus Gewerbebetrieb. Gewerbebetrieb ist eine selbständige nachhaltige Betätigung mit "
        "Gewinnerzielungsabsicht und Beteiligung am allgemeinen wirtschaftlichen Verkehr (§ 15 Abs. 2 EStG).",
        "Steuerarten. Man unterscheidet Besitzsteuern, etwa die Einkommensteuer, und Verkehrsteuern, etwa die "
        "Umsatzsteuer. Nach der Ertragshoheit unterscheidet man Bundes-, Landes-, Gemeinde- und Gemeinschaftsteuern.",
    ]),
    "BWL": ("Grundbegriffe der BWL", [
        "Ökonomisches Prinzip. Maximalprinzip: Mit gegebenen Mitteln einen möglichst großen Erfolg erzielen. "
        "Minimalprinzip: Einen gegebenen Erfolg mit möglichst geringem Mitteleinsatz erreichen.",
        "Produktionsfaktoren nach Gutenberg. Elementarfaktoren sind ausführende Arbeit, Betriebsmittel und "
        "Werkstoffe. Hinzu kommt der dispositive Faktor, also Leitung, Planung und Organisation.",
        "Rechtsformen. Einzelunternehmen, Personengesellschaften wie OHG und KG sowie Kapitalgesellschaften wie GmbH "
        "und AG. Die Rechtsform beeinflusst Haftung, Besteuerung und Finanzierung.",
    ]),
    "ESB": ("Beruf Steuerberater", [
        "Befugnis zur Hilfeleistung in Steuersachen. Zur unbeschränkten geschäftsmäßigen Hilfeleistung in "
        "Steuersachen sind insbesondere Steuerberater, Rechtsanwälte und Wirtschaftsprüfer befugt (§ 3 StBerG).",
        "Allgemeine Berufspflichten. Steuerberater haben ihren Beruf unabhängig, eigenverantwortlich, gewissenhaft, "
        "verschwiegen und unter Verzicht auf berufswidrige Werbung auszuüben (§ 57 Abs. 1 StBerG).",
    ]),
}

OLD_SCRIPT_BF = ("Skript Buchführung (Stand 2023). Aufbewahrungsfristen: Bücher, Jahresabschlüsse und Buchungsbelege "
                 "sind zehn Jahre aufzubewahren. Handelsbriefe sind sechs Jahre aufzubewahren. Die Frist beginnt mit "
                 "dem Schluss des Kalenderjahres.")

PAST_LECTURE_SSR = [
    "Guten Morgen zusammen, heute machen wir weiter mit dem Kaufvertrag nach § 433 BGB.",
    "Der Verkäufer muss die Sache übergeben und das Eigentum verschaffen, und zwar frei von Sach- und Rechtsmängeln.",
    "Welche Pflichten hat eigentlich der Käufer?",
    "Genau, der Käufer muss den Kaufpreis zahlen und die Sache abnehmen, das steht in Absatz 2.",
    "Unter dem Abstraktionsprinzip versteht man die Unabhängigkeit des Verfügungsgeschäfts vom "
    "Verpflichtungsgeschäft.",
    "Das ist klausurrelevant, merken Sie sich das bitte.",
    "Und wann verjährt dann der Anspruch auf den Kaufpreis?",
    "Die regelmäßige Verjährungsfrist beträgt drei Jahre nach § 195 BGB, Beginn zum Jahresende nach § 199.",
    "Achtung, bei Mängelansprüchen gilt etwas anderes, da sind es grundsätzlich zwei Jahre ab Ablieferung.",
    "Die Hausarbeit ist bis zum 15.01.2027 abzugeben, bitte als PDF in Moodle.",
]

# Played step by step in live demo mode ("Demo-Vorlesung abspielen")
LIVE_DEMO_BF = [
    "Wir starten heute mit der Buchführungspflicht nach § 238 HGB.",
    "Jeder Kaufmann ist verpflichtet, Bücher zu führen, und Kaufmann ist, wer ein Handelsgewerbe betreibt.",
    "Wer muss denn nach Handelsrecht überhaupt Bücher führen?",
    "Richtig, der Kaufmann – kleine Einzelkaufleute sind aber nach § 241a HGB befreit.",
    "Und ab welchem Umsatz gilt das dann im Steuerrecht?",
    "Im Steuerrecht schauen wir in § 141 AO, da liegt die Grenze bei 800.000 Euro Umsatz oder 80.000 Euro Gewinn.",
    "Das kommt garantiert in der Klausur dran.",
    "Wie lange müssen Buchungsbelege aufbewahrt werden?",
    "Achtung, Buchungsbelege müssen seit 2025 nur noch acht Jahre aufbewahrt werden, nicht mehr zehn Jahre.",
    "Zum Buchungssatz: Wareneinkauf auf Ziel über 1.000 Euro bucht man Wareneingang an Verbindlichkeiten.",
]


def _week_start(now: datetime) -> datetime:
    return (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)


def seed_demo(db: Session) -> User:
    existing = db.scalar(select(User).where(User.email == DEMO_EMAIL))
    if existing:
        return existing
    user = User(email=DEMO_EMAIL, password_hash=hash_password(DEMO_PASSWORD), display_name="Demo", is_demo=True,
                setup_step=7, settings={"consent_reminder": True, "keep_audio": True, "answer_mode": "short",
                                        "call_names": ["Frau Demo", "Herr Demo"]})
    db.add(user)
    db.flush()
    seed_demo_norms(db)
    now = datetime.now(TZ).replace(tzinfo=None)
    week0 = _week_start(now)
    mods: dict[str, Module] = {}
    for name, short_, color, lecturer, weekday, (h, m) in MODULES:
        mod = Module(user_id=user.id, name=name, short=short_, color=color, lecturer=lecturer, aliases=[],
                     exam_date=(week0 + timedelta(days=70 + weekday)).replace(hour=9),
                     lecturer_profile={"notes": "Betont Gutachtenstil und Normzitate." if short_ == "SSR" else ""})
        db.add(mod)
        db.flush()
        mods[short_] = mod
        # timetable: weekly lecture −6…+8 weeks
        for w in range(-6, 9):
            start = week0 + timedelta(weeks=w, days=weekday, hours=h, minutes=m)
            ev = Event(user_id=user.id, uid=f"demo-{short_}-{w}", start=start, end=start + timedelta(minutes=90),
                       title=f"{name} (VL)", location=f"A{10 + weekday}.0{w % 3 + 1}", source="ics",
                       module_id=mod.id, match_score=1.0, match_confirmed=True)
            db.add(ev)
            db.flush()
            db.add(Lecture(user_id=user.id, module_id=mod.id, event_id=ev.id, start=ev.start, end=ev.end,
                           title=ev.title, source="calendar"))
    # a lecture running right now (BF) so one-tap start works in the demo
    start = now.replace(second=0, microsecond=0) - timedelta(minutes=20)
    ev = Event(user_id=user.id, uid="demo-now", start=start, end=start + timedelta(minutes=90),
               title="Buchführung (VL)", location="A12.01", source="ics", module_id=mods["BF"].id, match_score=1.0,
               match_confirmed=True)
    db.add(ev)
    db.flush()
    db.add(Lecture(user_id=user.id, module_id=mods["BF"].id, event_id=ev.id, start=ev.start, end=ev.end,
                   title=ev.title, source="calendar"))
    db.add(Event(user_id=user.id, uid="demo-unmatched", start=now.replace(hour=16, minute=0) + timedelta(days=1),
                 end=now.replace(hour=17, minute=30) + timedelta(days=1), title="Tutorium Mathe für Ökonomen",
                 location="B2.12", source="ics", match_score=0.31))
    # slides as real PDFs (encrypted storage) + index
    for short_, (title, pages) in SLIDES.items():
        mod = mods[short_]
        pdf = slides_pdf(f"{mod.name} – {title}", pages)
        doc = Document(user_id=user.id, module_id=mod.id, kind="slides",
                       title=f"{short_}_{(week0 - timedelta(weeks=2)).date()}_Folien_{title.replace(' ', '-')}.pdf",
                       original_name=f"{title}.pdf", mime="application/pdf", size=len(pdf),
                       storage_key=storage().put(pdf), sha256=sha256(pdf), pages=len(pages), text="\n\n".join(pages),
                       source="demo", status="ready", confidence=1.0, doc_date=week0 - timedelta(weeks=2),
                       simhash=simhash("\n".join(pages)), meta={"extract": "pdf-text"})
        db.add(doc)
        db.flush()
        index_document(db, doc, pages=pages)
    old = Document(user_id=user.id, module_id=mods["BF"].id, kind="script", title="BF_2023-10-01_Skript_Altfassung.pdf",
                   original_name="Skript_BF_2023.pdf", mime="application/pdf", text=OLD_SCRIPT_BF, pages=1,
                   source="demo", status="ready", confidence=1.0, doc_date=datetime(2023, 10, 1),
                   meta={"note": "veraltete Fassung"})
    db.add(old)
    db.flush()
    index_document(db, old, pages=[OLD_SCRIPT_BF])
    # past lecture with transcript, processed by the real pipeline
    lec = db.scalar(select(Lecture).where(Lecture.module_id == mods["SSR"].id, Lecture.start < now - timedelta(days=1))
                    .order_by(Lecture.start.desc()))
    consent = ConsentLog(user_id=user.id, module_id=mods["SSR"].id,
                         statement="Demo: Einwilligung aller Anwesenden bestätigt")
    db.add(consent)
    db.flush()
    rec = Recording(user_id=user.id, module_id=mods["SSR"].id, lecture_id=lec.id if lec else None,
                    consent_id=consent.id, title=f"SSR {lec.start:%d.%m.%Y}" if lec else "SSR Vorlesung",
                    started_at=lec.start if lec else now - timedelta(days=7), status="live", source="demo")
    db.add(rec)
    db.flush()
    t = 0.0
    segs = []
    for s in PAST_LECTURE_SSR:
        segs.append((t, t + 9.0, s))
        t += 9.0 + 25
    ingest_segments(db, user, rec, segs)
    rec.ended_at = rec.started_at + timedelta(seconds=t)
    finalize_recording(db, rec)
    build_package(db, user, rec)
    build_glossary(db, user, mods["SSR"].id)
    build_glossary(db, user, mods["GStR"].id)
    # deadlines, announcements
    db.add_all([
        Deadline(user_id=user.id, module_id=mods["BF"].id, title="Übungsblatt 4 abgeben", due=now + timedelta(days=3, hours=2),
                 source="moodle", status="accepted"),
        Deadline(user_id=user.id, module_id=mods["GStR"].id, title="Anmeldung Prüfungen (Prüfungsamt)",
                 due=now + timedelta(days=9), source="manual", status="accepted"),
        Announcement(user_id=user.id, module_id=mods["BF"].id, title="Raumänderung nächste Woche",
                     body="Die Vorlesung am Dienstag findet ausnahmsweise in A20.1.36 statt.",
                     author="Prof. Dr. Schäfer", posted_at=utcnow() - timedelta(hours=5)),
        Announcement(user_id=user.id, module_id=mods["SSR"].id, title="Folien Kapitel 3 online",
                     body="Die Folien zu Kauf- und Verjährungsrecht stehen in Moodle bereit.", author="Prof. Dr. Weber",
                     posted_at=utcnow() - timedelta(days=2)),
    ])
    # inbox review item (low-confidence scan)
    scan_text = "Notizen Tutorium. Übungsaufgabe: Berechne den Gewinn. Lösungsskizze siehe Rückseite."
    review = Document(user_id=user.id, kind="notes", title="Allgemein_Notizen_Scan_0042.pdf",
                      original_name="Scan_0042.pdf", mime="application/pdf", text=scan_text, pages=1, source="upload",
                      status="ready", confidence=0.34, needs_review=True,
                      review_reason="Modul unsicher (34 %, Inhalt)", doc_date=now - timedelta(days=1))
    db.add(review)
    db.flush()
    index_document(db, review, pages=[scan_text])
    db.add(InboxItem(user_id=user.id, document_id=review.id, channel="upload", status="review",
                     suggestion={"module_id": mods["BF"].id, "module_confidence": 0.34, "kind": "notes",
                                 "module_reason": "Inhalt", "title": review.title}))
    db.flush()
    return user
