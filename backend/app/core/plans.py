"""Pricing and plan gating. Pure functions; all numbers come from config/plans.json."""
from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from app.core.clock import utcnow
from app.settings import plans


def _d(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def family_price(persons: int, interval: str = "month") -> dict:
    """Family plan: base covers `included_persons`, +extra per person, capped at max_persons.
    Annual = monthly × annual_months_charged (e.g. 10 → two months free)."""
    fam = plans()["plans"]["family"]
    if persons < fam["included_persons"] or persons > fam["max_persons"]:
        raise ValueError("invalid_persons")
    monthly = _d(fam["price_month"]) + _d(fam["extra_person_month"]) * (persons - fam["included_persons"])
    total = monthly if interval == "month" else _d(monthly * fam["annual_months_charged"])
    per_person = _d(total / persons)
    return {"persons": persons, "interval": interval, "total": float(total), "per_person": float(per_person)}


def premium_price(interval: str = "month") -> float:
    p = plans()["plans"]["premium"]
    return float(_d(p["price_month"] if interval == "month" else p["price_year"]))


def price_cents(product: str, interval: str = "month", persons: int = 1) -> int:
    if product == "premium":
        return int(_d(premium_price(interval)) * 100)
    if product == "family":
        return int(_d(family_price(persons, interval)["total"]) * 100)
    if product == "one_time_report":
        return int(_d(plans()["one_time_report"]["price"]) * 100)
    raise ValueError("unknown_product")


def vat_breakdown(gross: float) -> dict:
    """Prices are gross (incl. VAT). Small-business mode (§19 UStG) shows no VAT."""
    from app.settings import brand

    if brand()["operator"].get("small_business"):
        return {"gross": gross, "net": gross, "vat": 0.0, "note": "small_business"}
    rate = Decimal(str(plans()["vat_rate"]))
    g = _d(gross)
    net = _d(g / (1 + rate))
    return {"gross": float(g), "net": float(net), "vat": float(g - net), "note": "incl_vat"}


def effective_tier(user, now: datetime | None = None) -> str:
    """Map stored plan + trial to the limit tier ('free' or 'premium')."""
    now = now or utcnow()
    if user.plan in ("premium", "family_owner", "family_member"):
        return "premium"
    if user.trial_ends_at and user.trial_ends_at > now:
        return "premium"
    return "free"


def has_feature(user, feature: str) -> bool:
    if feature in plans()["premium_features"]:
        return effective_tier(user) == "premium"
    return True


def limit(user, key: str) -> int | bool:
    return plans()["limits"][effective_tier(user)][key]
