"""Database models. Personal data columns use EncryptedText (AES-GCM at rest)."""
from __future__ import annotations

import secrets
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.crypto import EncryptedText
from app.db import Base


def now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def new_id() -> str:
    return secrets.token_hex(12)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(24), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(EncryptedText)
    email_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    display_name: Mapped[str | None] = mapped_column(EncryptedText)
    role: Mapped[str] = mapped_column(String(16), default="user")
    plan: Mapped[str] = mapped_column(String(20), default="free")
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime)
    address_form: Mapped[str] = mapped_column(String(3), default="du")
    locale: Mapped[str] = mapped_column(String(5), default="de")
    totp_secret: Mapped[str | None] = mapped_column(EncryptedText)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    recovery_codes: Mapped[list | None] = mapped_column(JSON)
    referral_code: Mapped[str] = mapped_column(String(12), unique=True, default=lambda: secrets.token_urlsafe(6))
    referred_by: Mapped[str | None] = mapped_column(String(24))
    stripe_customer_id: Mapped[str | None] = mapped_column(String(64))
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    lock_reason: Mapped[str | None] = mapped_column(String(255))
    is_child: Mapped[bool] = mapped_column(Boolean, default=False)
    guardian_id: Mapped[str | None] = mapped_column(String(24))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    session_version: Mapped[int] = mapped_column(Integer, default=0)
    free_months_credit: Mapped[int] = mapped_column(Integer, default=0)
    identifiers: Mapped[list[Identifier]] = relationship(back_populates="user", cascade="all, delete-orphan")


class OAuthAccount(Base, TimestampMixin):
    __tablename__ = "oauth_accounts"
    __table_args__ = (UniqueConstraint("provider", "subject"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(16))
    subject: Mapped[str] = mapped_column(String(255))


class Passkey(Base, TimestampMixin):
    __tablename__ = "passkeys"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    credential_id: Mapped[str] = mapped_column(String(512), unique=True)
    public_key: Mapped[str] = mapped_column(Text)
    sign_count: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(64), default="Passkey")


class ConsentLog(Base, TimestampMixin):
    __tablename__ = "consent_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(24), index=True)
    kind: Mapped[str] = mapped_column(String(48))  # own_data, terms, privacy, guardian, mic, ai, cookies, mailbox
    version: Mapped[str] = mapped_column(String(16), default="1")
    granted: Mapped[bool] = mapped_column(Boolean, default=True)
    subject_ref: Mapped[str | None] = mapped_column(String(64))
    ip_hash: Mapped[str | None] = mapped_column(String(64))


class Identifier(Base, TimestampMixin):
    __tablename__ = "identifiers"
    id: Mapped[str] = mapped_column(String(24), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # name|email|phone|city|username|domain
    value: Mapped[str] = mapped_column(EncryptedText)
    value_hash: Mapped[str] = mapped_column(String(64), index=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    own_data_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)
    code_hash: Mapped[str | None] = mapped_column(String(64))
    code_expires: Mapped[datetime | None] = mapped_column(DateTime)
    code_attempts: Mapped[int] = mapped_column(Integer, default=0)
    user: Mapped[User] = relationship(back_populates="identifiers")


class Scan(Base, TimestampMixin):
    __tablename__ = "scans"
    id: Mapped[str] = mapped_column(String(24), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # basic|deep|breach|monitor
    status: Mapped[str] = mapped_column(String(16), default="done")
    summary: Mapped[dict | None] = mapped_column(JSON)
    new_count: Mapped[int] = mapped_column(Integer, default=0)


class Finding(Base, TimestampMixin):
    __tablename__ = "findings"
    id: Mapped[str] = mapped_column(String(24), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    scan_id: Mapped[str | None] = mapped_column(String(24))
    identifier_id: Mapped[str | None] = mapped_column(String(24))
    module: Mapped[str] = mapped_column(String(24), index=True)
    source: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(EncryptedText)
    url: Mapped[str | None] = mapped_column(EncryptedText)
    data_types: Mapped[list] = mapped_column(JSON, default=list)
    risk: Mapped[str] = mapped_column(String(8), default="low")  # low|medium|high
    details: Mapped[str | None] = mapped_column(EncryptedText)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    found_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime)  # e.g. breach date
    status: Mapped[str] = mapped_column(String(8), default="open")  # open|done|trash
    tags: Mapped[list] = mapped_column(JSON, default=list)
    note: Mapped[str | None] = mapped_column(EncryptedText)
    attributable: Mapped[bool] = mapped_column(Boolean, default=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    trashed_at: Mapped[datetime | None] = mapped_column(DateTime)


class RiskSnapshot(Base, TimestampMixin):
    __tablename__ = "risk_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    score: Mapped[int] = mapped_column(Integer)
    factors: Mapped[dict] = mapped_column(JSON)


class DeletionRequest(Base, TimestampMixin):
    __tablename__ = "deletion_requests"
    id: Mapped[str] = mapped_column(String(24), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    finding_id: Mapped[str | None] = mapped_column(String(24))
    kind: Mapped[str] = mapped_column(String(8))  # art15|art16|art17
    recipient: Mapped[str] = mapped_column(EncryptedText)
    recipient_email: Mapped[str | None] = mapped_column(EncryptedText)
    subject: Mapped[str] = mapped_column(EncryptedText)
    body: Mapped[str] = mapped_column(EncryptedText)
    status: Mapped[str] = mapped_column(String(10), default="open")  # open|sent|done|rejected
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    due_at: Mapped[datetime | None] = mapped_column(DateTime)
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime)


class QuotaUsage(Base):
    __tablename__ = "quota_usage"
    __table_args__ = (UniqueConstraint("source", "day"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(32))
    day: Mapped[str] = mapped_column(String(10))
    count: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)


class UserUsage(Base):
    """Per-user feature counters (plan limits). period = YYYY-MM-DD or YYYY-MM."""

    __tablename__ = "user_usage"
    __table_args__ = (UniqueConstraint("user_id", "feature", "period"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(24), index=True)
    feature: Mapped[str] = mapped_column(String(32))
    period: Mapped[str] = mapped_column(String(10))
    count: Mapped[int] = mapped_column(Integer, default=0)


class SourceKey(Base):
    __tablename__ = "source_keys"
    source: Mapped[str] = mapped_column(String(32), primary_key=True)
    value: Mapped[str] = mapped_column(EncryptedText)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_test: Mapped[str | None] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class AuditLog(Base, TimestampMixin):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(24), index=True)
    action: Mapped[str] = mapped_column(String(64))
    meta: Mapped[dict | None] = mapped_column(JSON)  # never personal plaintext
    ip_hash: Mapped[str | None] = mapped_column(String(64))


class Subscription(Base, TimestampMixin):
    __tablename__ = "subscriptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plan: Mapped[str] = mapped_column(String(16))  # premium|family
    interval: Mapped[str] = mapped_column(String(8))  # month|year
    seats: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16))  # trialing|active|canceled|past_due
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)


class Purchase(Base, TimestampMixin):
    __tablename__ = "purchases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    product: Mapped[str] = mapped_column(String(32))  # one_time_report
    amount_cents: Mapped[int] = mapped_column(Integer)
    stripe_session_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)


class Voucher(Base, TimestampMixin):
    __tablename__ = "vouchers"
    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    free_months: Mapped[int] = mapped_column(Integer, default=1)
    max_uses: Mapped[int] = mapped_column(Integer, default=100)
    used: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class VoucherRedemption(Base, TimestampMixin):
    __tablename__ = "voucher_redemptions"
    __table_args__ = (UniqueConstraint("code", "user_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32))
    user_id: Mapped[str] = mapped_column(String(24))


class Referral(Base, TimestampMixin):
    __tablename__ = "referrals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    referrer_id: Mapped[str] = mapped_column(String(24), index=True)
    referee_id: Mapped[str] = mapped_column(String(24), unique=True)
    rewarded: Mapped[bool] = mapped_column(Boolean, default=False)


class ProcessedEvent(Base, TimestampMixin):
    """Idempotency for Stripe webhooks."""

    __tablename__ = "processed_events"
    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)


class FamilyGroup(Base, TimestampMixin):
    __tablename__ = "family_groups"
    id: Mapped[str] = mapped_column(String(24), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    seats: Mapped[int] = mapped_column(Integer, default=2)


class FamilyMember(Base, TimestampMixin):
    __tablename__ = "family_members"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[str] = mapped_column(ForeignKey("family_groups.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str | None] = mapped_column(String(24))
    invite_token: Mapped[str | None] = mapped_column(String(64), unique=True)
    label: Mapped[str | None] = mapped_column(EncryptedText)
    status: Mapped[str] = mapped_column(String(12), default="invited")  # invited|active|removed
    is_child: Mapped[bool] = mapped_column(Boolean, default=False)


class WaitlistEntry(Base, TimestampMixin):
    __tablename__ = "waitlist"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(EncryptedText)
    email_hash: Mapped[str] = mapped_column(String(64), unique=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, default=lambda: secrets.token_urlsafe(24))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)
    wave: Mapped[int | None] = mapped_column(Integer)
    invite_code: Mapped[str | None] = mapped_column(String(32))
    approved: Mapped[bool] = mapped_column(Boolean, default=False)


class InviteCode(Base, TimestampMixin):
    __tablename__ = "invite_codes"
    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    wave: Mapped[int] = mapped_column(Integer, default=1)
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    used: Mapped[int] = mapped_column(Integer, default=0)


class Feedback(Base, TimestampMixin):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(24))
    page: Mapped[str | None] = mapped_column(String(128))
    rating: Mapped[int | None] = mapped_column(Integer)
    message: Mapped[str] = mapped_column(EncryptedText)


class AbuseReport(Base, TimestampMixin):
    __tablename__ = "abuse_reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reporter_user_id: Mapped[str | None] = mapped_column(String(24))
    contact: Mapped[str | None] = mapped_column(EncryptedText)
    message: Mapped[str] = mapped_column(EncryptedText)
    status: Mapped[str] = mapped_column(String(12), default="new")


class ChecklistState(Base):
    __tablename__ = "checklist_state"
    __table_args__ = (UniqueConstraint("user_id", "scope", "item"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    scope: Mapped[str] = mapped_column(String(24))  # security | social:<platform>
    item: Mapped[str] = mapped_column(String(48))
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class MonitorSettings(Base):
    __tablename__ = "monitor_settings"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    frequency: Mapped[str] = mapped_column(String(8), default="weekly")  # daily|weekly
    min_severity: Mapped[str] = mapped_column(String(8), default="medium")
    quiet_start: Mapped[int] = mapped_column(Integer, default=22)
    quiet_end: Mapped[int] = mapped_column(Integer, default=7)
    push: Mapped[bool] = mapped_column(Boolean, default=True)
    email: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run: Mapped[datetime | None] = mapped_column(DateTime)


class PushSubscription(Base, TimestampMixin):
    __tablename__ = "push_subscriptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    endpoint: Mapped[str] = mapped_column(EncryptedText)
    keys: Mapped[str] = mapped_column(EncryptedText)


class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(8), default="low")
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    link: Mapped[str | None] = mapped_column(String(160))


class TimelineEvent(Base, TimestampMixin):
    __tablename__ = "timeline"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(24))  # finding|warning|request|change|scan|checklist
    title: Mapped[str] = mapped_column(String(200))
    ref: Mapped[str | None] = mapped_column(String(48))
    risk: Mapped[str | None] = mapped_column(String(8))
    at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)


class Upload(Base, TimestampMixin):
    __tablename__ = "uploads"
    id: Mapped[str] = mapped_column(String(24), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    path: Mapped[str] = mapped_column(String(512))
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class MailSubscription(Base, TimestampMixin):
    __tablename__ = "mail_subscriptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    sender: Mapped[str] = mapped_column(EncryptedText)
    sender_domain: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(16))  # newsletter|subscription|account
    amount: Mapped[float | None] = mapped_column(Float)
    interval: Mapped[str | None] = mapped_column(String(8))
    unsubscribe: Mapped[str | None] = mapped_column(EncryptedText)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime)
    message_count: Mapped[int] = mapped_column(Integer, default=1)


class Document(Base, TimestampMixin):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(24), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(EncryptedText)
    text: Mapped[str] = mapped_column(EncryptedText)
    deadlines: Mapped[list] = mapped_column(JSON, default=list)
    sensitive: Mapped[list] = mapped_column(JSON, default=list)


class Reminder(Base, TimestampMixin):
    __tablename__ = "reminders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(EncryptedText)
    due_at: Mapped[datetime] = mapped_column(DateTime)
    ref: Mapped[str | None] = mapped_column(String(48))
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    notified: Mapped[bool] = mapped_column(Boolean, default=False)


class EstateVault(Base):
    """Digital estate. `ciphertext` is encrypted in the browser with a key only the user holds."""

    __tablename__ = "estate_vaults"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    ciphertext: Mapped[str | None] = mapped_column(Text)
    salt: Mapped[str | None] = mapped_column(String(64))
    iv: Mapped[str | None] = mapped_column(String(64))
    trusted_email: Mapped[str | None] = mapped_column(EncryptedText)
    unlock_delay_days: Mapped[int] = mapped_column(Integer, default=30)
    unlock_requested_at: Mapped[datetime | None] = mapped_column(DateTime)
    unlock_token: Mapped[str | None] = mapped_column(String(64))
    released_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class FamilyTreePerson(Base, TimestampMixin):
    """Self-maintained, private family tree entry. Never auto-suggested."""

    __tablename__ = "family_tree"
    id: Mapped[str] = mapped_column(String(24), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(EncryptedText)
    relation: Mapped[str] = mapped_column(String(24))
    member_user_id: Mapped[str | None] = mapped_column(String(24))  # only with that member's consent
    consent_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)


class Report(Base, TimestampMixin):
    __tablename__ = "reports"
    id: Mapped[str] = mapped_column(String(24), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(12))  # full|onetime
    data: Mapped[str] = mapped_column(EncryptedText)  # JSON


class AiUsage(Base):
    __tablename__ = "ai_usage"
    __table_args__ = (UniqueConstraint("user_id", "day"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(24))
    day: Mapped[str] = mapped_column(String(10))
    count: Mapped[int] = mapped_column(Integer, default=0)


class AiCache(Base, TimestampMixin):
    __tablename__ = "ai_cache"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    response: Mapped[str] = mapped_column(EncryptedText)


class OneTimeToken(Base, TimestampMixin):
    """Email verification / password reset / webauthn challenges."""

    __tablename__ = "one_time_tokens"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(24))
    purpose: Mapped[str] = mapped_column(String(24))
    data: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class MailboxConnection(Base):
    """Read-only mailbox link for the subscription guard (Gmail scope gmail.metadata: headers only, no bodies).
    Only the encrypted refresh token is stored; disconnect revokes it at Google and deletes the row."""

    __tablename__ = "mailbox_connections"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    provider: Mapped[str] = mapped_column(String(16), default="gmail")
    address: Mapped[str | None] = mapped_column(EncryptedText)
    refresh_token: Mapped[str] = mapped_column(EncryptedText)
    connected_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    last_sync: Mapped[datetime | None] = mapped_column(DateTime)
