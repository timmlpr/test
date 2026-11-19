from __future__ import annotations

from app.adapters.base import Adapter
from app.adapters.demo import Demo
from app.adapters.domain import DnsDoh, Rdap, Wayback, WebPassive
from app.adapters.leaks import HibpEmail, PwnedPasswords, XposedOrNot
from app.adapters.scam import SafeBrowsing, TinEye, UrlHaus
from app.adapters.search import BraveSearch, GoogleCse, Wikipedia
from app.adapters.sms import SevenSms

ADAPTERS: dict[str, Adapter] = {a.meta.name: a for a in [
    XposedOrNot(), PwnedPasswords(), HibpEmail(), Wikipedia(), BraveSearch(), GoogleCse(), Rdap(), DnsDoh(), WebPassive(),
    Wayback(), SafeBrowsing(), UrlHaus(), TinEye(), SevenSms(), Demo(),
]}

# Tests can force offline behaviour.
OFFLINE = False


def get(name: str) -> Adapter:
    return ADAPTERS[name]


def stored_key(name: str) -> str | None:
    from app.db import SessionLocal
    from app.models import SourceKey

    with SessionLocal() as db:
        row = db.get(SourceKey, name)
        return row.value if row and row.enabled else None


def is_enabled(a: Adapter) -> bool:
    if OFFLINE or not a.meta.permitted:
        return False
    if a.meta.name == "demo":
        return False
    if a.meta.requires_key and not a.key():
        return False
    if not a.meta.default_enabled:
        # paid/legacy adapters only run when an admin explicitly stored a key
        return stored_key(a.meta.name) is not None
    return True


def describe() -> list[dict]:
    from app.adapters.quota import quota

    out = []
    for a in ADAPTERS.values():
        if a.meta.name == "demo":
            continue
        used, errors = quota.usage(a.meta.name)
        m = a.meta
        out.append({"name": m.name, "label": m.label, "modules": m.modules, "terms_url": m.terms_url,
                    "data_types": m.data_types, "requires_key": m.requires_key, "paid": m.paid, "permitted": m.permitted,
                    "enabled": is_enabled(a), "has_key": bool(a.key()) if m.requires_key else None,
                    "rate_per_day": m.rate_per_day, "used_today": used, "errors_today": errors,
                    "remaining_today": max(0, m.rate_per_day - used), "signup_url": m.signup_url, "notes": m.notes,
                    "key_env": m.key_env, "verified_on": m.verified_on})
    return out
