"""Demo seed (DEMO_MODE only). Creates clearly marked sample accounts and data so every screen is clickable.

  demo@demo.example.com   / FadeprintDemo1!   – premium (demo subscription), full sample data
  free@demo.example.com   / FadeprintDemo1!   – free plan, to see plan gating
  admin@demo.example.com  / FadeprintAdmin1!  – admin, TOTP secret DEMO_ADMIN_TOTP (dev only!)
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.core.crypto import lookup_hash
from app.core.security import hash_password
from app.db import SessionLocal
from app.models import (
    ChecklistState,
    DeletionRequest,
    Document,
    FamilyTreePerson,
    Finding,
    Identifier,
    InviteCode,
    MailSubscription,
    MonitorSettings,
    Reminder,
    RiskSnapshot,
    Scan,
    Subscription,
    TimelineEvent,
    User,
    Voucher,
    now,
)

DEMO_PASSWORD = "FadeprintDemo1!"
ADMIN_PASSWORD = "FadeprintAdmin1!"
DEMO_ADMIN_TOTP = "FADEPRINTDEMOADMINTOTPKEYABCDEF2"


def _user(db, email: str, pw: str, name: str, **kw) -> User:
    u = User(email=email, email_hash=lookup_hash(email), password_hash=hash_password(pw), email_verified=True, display_name=name,
             is_demo=True, **kw)
    db.add(u)
    db.flush()
    return u


def _ident(db, u: User, kind: str, value: str) -> Identifier:
    i = Identifier(user_id=u.id, kind=kind, value=value, value_hash=lookup_hash(value), verified_at=now(), own_data_confirmed_at=now())
    db.add(i)
    db.flush()
    return i


def seed_demo() -> None:
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email_hash == lookup_hash("demo@demo.example.com"))):
            return
        demo = _user(db, "demo@demo.example.com", DEMO_PASSWORD, "Alex Beispiel", plan="premium")
        free = _user(db, "free@demo.example.com", DEMO_PASSWORD, "Kim Muster")
        _user(db, "admin@demo.example.com", ADMIN_PASSWORD, "Admin", role="admin", totp_secret=DEMO_ADMIN_TOTP, totp_enabled=True)
        db.add(Subscription(user_id=demo.id, plan="premium", interval="month", status="active", stripe_subscription_id="demo_seed_sub",
                            current_period_end=now() + timedelta(days=21)))
        for u, name in ((demo, "Alex Beispiel"), (free, "Kim Muster")):
            _ident(db, u, "email", u.email)
            _ident(db, u, "name", name)
            _ident(db, u, "city", "Musterstadt")
        _ident(db, demo, "username", "alex_beispiel")
        db.add(InviteCode(code="WELLE1", wave=1, max_uses=50))
        db.add(Voucher(code="TESTMONAT", free_months=1, max_uses=100))
        db.commit()

        from app.modules.findings_service import snapshot
        from app.modules.scan import run_privacy_scan

        for u in (demo, free):
            idents = db.scalars(select(Identifier).where(Identifier.user_id == u.id)).all()
            scan = Scan(user_id=u.id, kind="basic")
            db.add(scan)
            db.flush()
            scan.summary = run_privacy_scan(db, u, idents, scan, deep=False)
            snapshot(db, u)
        db.commit()

        # Backdate demo data to make history, timeline and deadlines meaningful.
        findings = db.scalars(select(Finding).where(Finding.user_id == demo.id)).all()
        for n, f in enumerate(findings):
            f.found_at = f.created_at = now() - timedelta(days=60 - n * 6)
        for ev in db.scalars(select(TimelineEvent).where(TimelineEvent.user_id == demo.id)).all():
            ev.at = now() - timedelta(days=58)
        for d, score in ((90, 71), (75, 68), (60, 66), (45, 61), (30, 57), (15, 52)):
            db.add(RiskSnapshot(user_id=demo.id, score=score, factors={}, created_at=now() - timedelta(days=d)))
        for item in ("two_factor", "password_manager", "screen_lock", "updates"):
            db.add(ChecklistState(user_id=demo.id, scope="security", item=item, done=True))
        for item in ("private_account", "location_off"):
            db.add(ChecklistState(user_id=demo.id, scope="social:instagram", item=item, done=True))
        high = [f for f in findings if f.risk == "high"]
        if high:
            db.add(DeletionRequest(user_id=demo.id, finding_id=high[0].id, kind="art17", recipient="Verein Beispiel e. V.",
                                   recipient_email="datenschutz@verein.example", subject="Antrag auf Löschung (Demo)",
                                   body="Demo-Anfrage – Text wird beim Erstellen generiert.", status="sent",
                                   sent_at=now() - timedelta(days=35), due_at=now() - timedelta(days=5)))
            db.add(DeletionRequest(user_id=demo.id, finding_id=high[-1].id, kind="art17", recipient="Blog Beispiel",
                                   recipient_email=None, subject="Antrag auf Löschung (Demo)", body="Demo-Anfrage.", status="sent",
                                   sent_at=now() - timedelta(days=10), due_at=now() + timedelta(days=20)))
        db.add(MonitorSettings(user_id=demo.id, enabled=True, frequency="weekly", min_severity="medium", last_run=now() - timedelta(days=2)))
        for sender, dom, cat, amt, inter, unsub in (
            ("Streamingdienst", "stream.example", "subscription", 12.99, "month", "https://stream.example/abmelden"),
            ("Musik-Abo", "musik.example", "subscription", 10.99, "month", None),
            ("Cloud-Speicher", "cloud.example", "subscription", 29.99, "year", "https://cloud.example/unsubscribe"),
            ("Mode-Newsletter", "mode.example", "newsletter", None, None, "https://mode.example/unsub"),
            ("Reiseportal", "reise.example", "account", None, None, None),
        ):
            db.add(MailSubscription(user_id=demo.id, sender=sender, sender_domain=dom, category=cat, amount=amt, interval=inter,
                                    unsubscribe=unsub, last_seen=now() - timedelta(days=4), message_count=6))
        doc = Document(user_id=demo.id, title="Handyvertrag (Demo).pdf",
                       text="Mindestlaufzeit 24 Monate. Kündigung bis zum 31.03.2027 möglich, sonst verlängert sich der Vertrag.",
                       deadlines=[{"date": "2027-03-31", "context": "Kündigung bis zum 31.03.2027 möglich"}], sensitive=[])
        db.add(doc)
        db.flush()
        db.add(Reminder(user_id=demo.id, title="Frist: Handyvertrag (Demo).pdf", due_at=now().replace(year=2027, month=3, day=24), ref=doc.id))
        db.add(FamilyTreePerson(user_id=demo.id, label="Sam (Partner:in)", relation="partner", consent_confirmed=True))
        db.commit()
