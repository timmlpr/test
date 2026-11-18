"""Stripe billing. Payment state changes ONLY via verified webhooks (or, when Stripe is not configured and
DEMO_MODE is on, via a clearly labelled demo checkout that feeds the very same event handler)."""
from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime, timedelta

import stripe
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.audit import audit
from app.core.crypto import lookup_hash
from app.core.deps import client_ip, current_user
from app.core.errors import ApiError
from app.core.events import notify, timeline
from app.core.mailer import send_mail
from app.core.plans import family_price, premium_price, price_cents, vat_breakdown
from app.db import get_db
from app.models import (
    FamilyGroup,
    OneTimeToken,
    ProcessedEvent,
    Purchase,
    Referral,
    Subscription,
    User,
    Voucher,
    VoucherRedemption,
    now,
)
from app.settings import brand, get_settings, plans

router = APIRouter(prefix="/billing", tags=["billing"])


def stripe_on() -> bool:
    return bool(get_settings().stripe_secret_key)


def _stripe():
    stripe.api_key = get_settings().stripe_secret_key
    return stripe


@router.get("/plans")
def plan_table():
    p = plans()
    fam = p["plans"]["family"]
    return {
        "currency": p["currency"], "trial_days": p["trial_days"], "prices_include_vat": p["prices_include_vat"],
        "small_business": brand()["operator"]["small_business"],
        "premium": {"month": premium_price("month"), "year": premium_price("year"), "features": p["premium_features"]},
        "family": {"table": [family_price(n, "month") for n in range(fam["included_persons"], fam["max_persons"] + 1)],
                   "table_year": [family_price(n, "year") for n in range(fam["included_persons"], fam["max_persons"] + 1)],
                   "max_persons": fam["max_persons"]},
        "one_time_report": {"price": p["one_time_report"]["price"]},
        "free": {"features": p["plans"]["free"]["features"], "limits": p["limits"]["free"]},
        "most_popular": p["most_popular"],
        "vat": vat_breakdown(premium_price("month")),
        "stripe": stripe_on(), "demo_checkout": not stripe_on() and get_settings().demo_mode,
    }


class CheckoutIn(BaseModel):
    product: str = Field(pattern="^(premium|family|one_time_report)$")
    interval: str = Field(default="month", pattern="^(month|year)$")
    persons: int = Field(default=2, ge=1, le=6)


def _had_trial(db: Session, user: User) -> bool:
    return db.scalar(select(Subscription).where(Subscription.user_id == user.id)) is not None


@router.post("/checkout")
def checkout(body: CheckoutIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.is_child:
        raise ApiError(403, "child_cannot_purchase")
    if body.product == "family":
        family_price(body.persons, body.interval)  # validates persons range
    cents = price_cents(body.product, body.interval, body.persons)
    trial_days = 0 if body.product == "one_time_report" or _had_trial(db, user) else plans()["trial_days"]
    trial_days += 30 * user.free_months_credit if body.product != "one_time_report" else 0
    meta = {"user_id": user.id, "product": body.product, "interval": body.interval, "persons": str(body.persons),
            "free_months_used": str(user.free_months_credit if body.product != "one_time_report" else 0)}
    base = get_settings().public_url
    name = {"premium": f"{brand()['name']} Premium", "family": f"{brand()['name']} Familie ({body.persons} Personen)",
            "one_time_report": f"{brand()['name']} Einmal-Report"}[body.product]
    if not stripe_on():
        if not get_settings().demo_mode:
            raise ApiError(503, "billing_not_configured")
        tok = secrets.token_urlsafe(24)
        import json

        db.add(OneTimeToken(token_hash=lookup_hash(tok), user_id=user.id, purpose="demo_checkout",
                            data=json.dumps({**meta, "amount": cents, "trial_days": trial_days}), expires_at=now() + timedelta(minutes=30)))
        db.commit()
        return {"url": f"/app/billing/demo-checkout?token={tok}", "demo": True,
                "summary": {"name": name, "amount": cents / 100, "trial_days": trial_days}}
    s = _stripe()
    if not user.stripe_customer_id:
        cust = s.Customer.create(email=user.email, metadata={"user_id": user.id})
        user.stripe_customer_id = cust.id
        db.commit()
    price_data = {"currency": "eur", "unit_amount": cents, "product_data": {"name": name},
                  "tax_behavior": "inclusive"}
    params = {"customer": user.stripe_customer_id, "client_reference_id": user.id, "metadata": meta,
              "success_url": f"{base}/app/billing?status=success", "cancel_url": f"{base}/app/billing?status=cancel",
              "allow_promotion_codes": True, "locale": "de", "billing_address_collection": "auto"}
    if get_settings().stripe_tax:
        params["automatic_tax"] = {"enabled": True}
        params["customer_update"] = {"address": "auto"}
    if body.product == "one_time_report":
        params.update(mode="payment", line_items=[{"price_data": price_data, "quantity": 1}], invoice_creation={"enabled": True})
    else:
        price_data["recurring"] = {"interval": body.interval}
        params.update(mode="subscription", line_items=[{"price_data": price_data, "quantity": 1}],
                      subscription_data={"metadata": meta, **({"trial_period_days": trial_days} if trial_days else {})})
    sess = s.checkout.Session.create(**params)
    return {"url": sess.url, "demo": False}


# ------------------------------------------------------------------ event handling (shared)
def _activate(db: Session, user: User, product: str, interval: str, persons: int, status: str, sub_id: str | None,
              period_end: datetime | None, trial_days: int = 0) -> None:
    sub = db.scalar(select(Subscription).where(Subscription.stripe_subscription_id == sub_id)) if sub_id else None
    if not sub:
        sub = Subscription(user_id=user.id, plan=product, interval=interval, seats=persons, stripe_subscription_id=sub_id)
        db.add(sub)
    sub.status, sub.current_period_end = status, period_end
    user.plan = "family_owner" if product == "family" else "premium"
    if trial_days:
        user.trial_ends_at = now() + timedelta(days=trial_days)
    user.free_months_credit = 0
    if product == "family":
        grp = db.scalar(select(FamilyGroup).where(FamilyGroup.owner_id == user.id))
        if not grp:
            db.add(FamilyGroup(owner_id=user.id, seats=persons))
        else:
            grp.seats = persons
    _reward_referral(db, user)
    timeline(db, user.id, "change", f"Abo aktiv: {product}")


def _reward_referral(db: Session, user: User) -> None:
    ref = db.scalar(select(Referral).where(Referral.referee_id == user.id, Referral.rewarded.is_(False)))
    if not ref:
        return
    n = plans()["referral_free_months"]
    referrer = db.get(User, ref.referrer_id)
    if referrer:
        referrer.free_months_credit += n
        _extend_active(db, referrer, n)
        notify(db, referrer.id, "Empfehlung erfolgreich", f"Du erhältst {n} Gratis-Monat.", "low", "/app/billing")
    user.free_months_credit += n
    _extend_active(db, user, n)
    ref.rewarded = True


def _extend_active(db: Session, user: User, months: int) -> None:
    """If the user already pays, apply free months directly by pushing the next billing date."""
    sub = db.scalar(select(Subscription).where(Subscription.user_id == user.id, Subscription.status.in_(["active", "trialing"])))
    if not sub:
        return
    new_end = (sub.current_period_end or now()) + timedelta(days=30 * months)
    if sub.stripe_subscription_id and stripe_on():
        _stripe().Subscription.modify(sub.stripe_subscription_id, trial_end=int(new_end.timestamp()), proration_behavior="none")
    sub.current_period_end = new_end
    user.free_months_credit = max(0, user.free_months_credit - months)


def _deactivate(db: Session, sub: Subscription) -> None:
    sub.status = "canceled"
    user = db.get(User, sub.user_id)
    if user and not db.scalar(select(Subscription).where(Subscription.user_id == user.id, Subscription.status.in_(["active", "trialing"]),
                                                         Subscription.id != sub.id)):
        user.plan = "free"
        user.trial_ends_at = None
        grp = db.scalar(select(FamilyGroup).where(FamilyGroup.owner_id == user.id))
        if grp:
            from app.models import FamilyMember

            for m in db.scalars(select(FamilyMember).where(FamilyMember.group_id == grp.id, FamilyMember.status == "active")):
                mu = db.get(User, m.user_id) if m.user_id else None
                if mu and mu.plan == "family_member":
                    mu.plan = "free"
        timeline(db, user.id, "change", "Abo beendet")


def handle_event(db: Session, event: dict) -> str:
    """Process one Stripe event (dict form). Idempotent by event id."""
    eid = event["id"]
    if db.get(ProcessedEvent, eid):
        return "duplicate"
    obj = event["data"]["object"]
    typ = event["type"]
    if typ == "checkout.session.completed":
        meta = obj.get("metadata") or {}
        user = db.get(User, meta.get("user_id") or obj.get("client_reference_id"))
        if not user:
            return "unknown_user"
        if obj.get("mode") == "payment":
            if obj.get("payment_status") not in ("paid", "no_payment_required"):
                return "unpaid"
            db.add(Purchase(user_id=user.id, product="one_time_report", amount_cents=obj.get("amount_total") or 0,
                            stripe_session_id=obj["id"]))
            notify(db, user.id, "Einmal-Report freigeschaltet", "Du kannst deinen vollständigen Report jetzt erstellen.", "low", "/app/reports")
        else:
            period_end = datetime.fromtimestamp(obj["current_period_end"], UTC).replace(tzinfo=None) if obj.get("current_period_end") else None
            _activate(db, user, meta.get("product", "premium"), meta.get("interval", "month"), int(meta.get("persons", 1)),
                      obj.get("status_override", "active"), obj.get("subscription"), period_end, int(meta.get("trial_days", 0) or 0))
        audit(db, "billing.checkout_completed", user.id, mode=obj.get("mode"))
    elif typ in ("customer.subscription.updated", "customer.subscription.created"):
        sub = db.scalar(select(Subscription).where(Subscription.stripe_subscription_id == obj["id"]))
        if sub:
            sub.status = obj["status"]
            sub.cancel_at_period_end = bool(obj.get("cancel_at_period_end"))
            if obj.get("current_period_end"):
                sub.current_period_end = datetime.fromtimestamp(obj["current_period_end"], UTC).replace(tzinfo=None)
            if obj["status"] in ("canceled", "unpaid", "incomplete_expired"):
                _deactivate(db, sub)
    elif typ == "customer.subscription.deleted":
        sub = db.scalar(select(Subscription).where(Subscription.stripe_subscription_id == obj["id"]))
        if sub:
            _deactivate(db, sub)
    elif typ == "invoice.payment_failed":
        sub = db.scalar(select(Subscription).where(Subscription.stripe_subscription_id == obj.get("subscription")))
        if sub:
            sub.status = "past_due"
            notify(db, sub.user_id, "Zahlung fehlgeschlagen", "Bitte prüfe deine Zahlungsmethode im Kundenportal.", "medium", "/app/billing")
    db.add(ProcessedEvent(event_id=eid))
    db.commit()
    return "ok"


@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    s = get_settings()
    if not s.stripe_webhook_secret:
        raise ApiError(503, "billing_not_configured")
    payload = await request.body()
    try:
        stripe.Webhook.construct_event(payload, request.headers.get("stripe-signature", ""), s.stripe_webhook_secret)
    except (ValueError, stripe.SignatureVerificationError) as e:
        raise ApiError(400, "invalid_signature") from e
    return {"result": handle_event(db, json.loads(payload))}  # signature verified above


class DemoIn(BaseModel):
    token: str


@router.post("/demo/complete")
def demo_complete(body: DemoIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Demo-only stand-in for Stripe Checkout + webhook. Disabled as soon as a Stripe key exists."""
    import json

    if stripe_on() or not get_settings().demo_mode:
        raise ApiError(404, "not_found")
    row = db.get(OneTimeToken, lookup_hash(body.token))
    if not row or row.purpose != "demo_checkout" or row.user_id != user.id or row.expires_at < now():
        raise ApiError(400, "invalid_or_expired_token")
    meta = json.loads(row.data)
    db.delete(row)
    sid = f"demo_{secrets.token_hex(8)}"
    end = now() + timedelta(days=30 if meta["interval"] == "month" else 365)
    obj = {"id": sid, "mode": "payment" if meta["product"] == "one_time_report" else "subscription", "payment_status": "paid",
           "amount_total": meta["amount"], "metadata": {**meta, "trial_days": meta["trial_days"]}, "client_reference_id": user.id,
           "subscription": None if meta["product"] == "one_time_report" else f"demo_sub_{secrets.token_hex(6)}",
           "current_period_end": int((now() + timedelta(days=meta["trial_days"]) if meta["trial_days"] else end).timestamp()),
           "status_override": "trialing" if meta["trial_days"] else "active"}
    return {"result": handle_event(db, {"id": f"evt_{sid}", "type": "checkout.session.completed", "data": {"object": obj}})}


@router.get("/status")
def status(user: User = Depends(current_user), db: Session = Depends(get_db)):
    subs = db.scalars(select(Subscription).where(Subscription.user_id == user.id).order_by(Subscription.created_at.desc())).all()
    purchases = db.scalars(select(Purchase).where(Purchase.user_id == user.id)).all()
    return {"plan": user.plan, "trial_ends_at": user.trial_ends_at, "free_months_credit": user.free_months_credit,
            "subscriptions": [{"id": s.id, "plan": s.plan, "interval": s.interval, "seats": s.seats, "status": s.status,
                               "current_period_end": s.current_period_end, "cancel_at_period_end": s.cancel_at_period_end} for s in subs],
            "purchases": [{"product": p.product, "amount": p.amount_cents / 100, "consumed": p.consumed, "at": p.created_at} for p in purchases],
            "stripe": stripe_on()}


@router.post("/portal")
def portal(user: User = Depends(current_user)):
    if not stripe_on() or not user.stripe_customer_id:
        raise ApiError(503, "billing_not_configured")
    sess = _stripe().billing_portal.Session.create(customer=user.stripe_customer_id, return_url=f"{get_settings().public_url}/app/billing")
    return {"url": sess.url}


@router.post("/cancel")
def cancel(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Cancellation button (§ 312k BGB): one click, no retention flow. Ends at period end, confirmation by mail."""
    subs = db.scalars(select(Subscription).where(Subscription.user_id == user.id, Subscription.status.in_(["active", "trialing", "past_due"]))).all()
    if not subs:
        raise ApiError(404, "no_active_subscription")
    for sub in subs:
        if sub.stripe_subscription_id and stripe_on() and not sub.stripe_subscription_id.startswith("demo_"):
            _stripe().Subscription.modify(sub.stripe_subscription_id, cancel_at_period_end=True)
        sub.cancel_at_period_end = True
        if sub.status == "trialing" or not sub.current_period_end or sub.current_period_end < now():
            _deactivate(db, sub)
    end = max((s.current_period_end or now()) for s in subs)
    send_mail(user.email, f"{brand()['name']}: Kündigungsbestätigung",
              f"Deine Kündigung ist am {now():%d.%m.%Y um %H:%M} Uhr eingegangen.\nDein Zugang endet zum {end:%d.%m.%Y}.\n"
              "Es entstehen keine weiteren Kosten.")
    audit(db, "billing.cancel", user.id)
    db.commit()
    return {"ok": True, "ends_at": end}


class PublicCancelIn(BaseModel):
    email: EmailStr
    name: str = Field(max_length=120)
    contract: str = Field(default="", max_length=120)
    extraordinary: bool = False
    reason: str | None = Field(default=None, max_length=1000)


@router.post("/cancel-request")
def cancel_request(body: PublicCancelIn, request: Request, db: Session = Depends(get_db)):
    """Public cancellation form (works without login). Confirms receipt in text form immediately."""
    ratelimit.hit(f"cancelreq:{client_ip(request)}", 5, 3600)
    user = db.scalar(select(User).where(User.email_hash == lookup_hash(body.email)))
    ends = None
    if user:
        for sub in db.scalars(select(Subscription).where(Subscription.user_id == user.id, Subscription.status.in_(["active", "trialing"]))):
            if sub.stripe_subscription_id and stripe_on() and not sub.stripe_subscription_id.startswith("demo_"):
                _stripe().Subscription.modify(sub.stripe_subscription_id, cancel_at_period_end=True)
            sub.cancel_at_period_end = True
            ends = sub.current_period_end
        audit(db, "billing.cancel_public", user.id)
    send_mail(body.email, f"{brand()['name']}: Eingang deiner Kündigung",
              f"Wir haben deine Kündigung am {now():%d.%m.%Y um %H:%M} Uhr erhalten.\n"
              + (f"Dein Vertrag endet zum {ends:%d.%m.%Y}.\n" if ends else "Wir prüfen den Vertrag und melden uns.\n"))
    db.commit()
    return {"ok": True, "received_at": now()}


class VoucherIn(BaseModel):
    code: str = Field(max_length=32)


@router.post("/voucher")
def redeem_voucher(body: VoucherIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ratelimit.hit(f"voucher:{user.id}", 10, 3600)
    v = db.get(Voucher, body.code.strip().upper())
    if not v or not v.active or v.used >= v.max_uses:
        raise ApiError(400, "invalid_voucher")
    if db.scalar(select(VoucherRedemption).where(VoucherRedemption.code == v.code, VoucherRedemption.user_id == user.id)):
        raise ApiError(409, "voucher_used")
    v.used += 1
    db.add(VoucherRedemption(code=v.code, user_id=user.id))
    user.free_months_credit += v.free_months
    _extend_active(db, user, v.free_months)
    db.commit()
    return {"free_months_credit": user.free_months_credit, "added": v.free_months}


@router.get("/referral")
def referral(user: User = Depends(current_user), db: Session = Depends(get_db)):
    refs = db.scalars(select(Referral).where(Referral.referrer_id == user.id)).all()
    return {"code": user.referral_code, "link": f"{get_settings().public_url}/register?ref={user.referral_code}",
            "invited": len(refs), "rewarded": sum(r.rewarded for r in refs), "free_months": plans()["referral_free_months"]}
