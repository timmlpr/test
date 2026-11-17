"""Leak sources: XposedOrNot (keyless), Pwned Passwords (keyless, k-anonymity), HIBP (paid, disabled)."""
from __future__ import annotations

from urllib.parse import quote

from app.adapters.base import Adapter, AdapterMeta, SourceUnavailable

SENSITIVE = {"Passwords": "password", "Phone numbers": "phone", "Physical addresses": "address", "Dates of birth": "birthdate",
             "Credit cards": "payment", "Bank account numbers": "payment", "Partial credit card data": "payment",
             "IP addresses": "ip", "Names": "name", "Email addresses": "email", "Usernames": "username",
             "Geographic locations": "location", "Genders": "gender", "Government issued IDs": "id_document",
             "Security questions and answers": "security_qa", "Health": "health", "Passport numbers": "id_document"}


def normalise_types(raw: str) -> list[str]:
    out = []
    for part in (raw or "").split(";"):
        part = part.strip()
        if part:
            out.append(SENSITIVE.get(part, part.lower().replace(" ", "_")))
    return sorted(set(out))


class XposedOrNot(Adapter):
    meta = AdapterMeta(
        name="xposedornot", label="XposedOrNot", modules=["breach_check", "privacy_scan"],
        terms_url="https://xposedornot.com/api_doc", data_types=["email"],
        rate_per_day=2000, min_interval_s=1.05,
        notes="Free public API, 1 request/second documented. Domain endpoints need a key (not used).",
    )

    def breaches(self, email: str) -> list[dict]:
        r = self.http("GET", f"https://api.xposedornot.com/v1/breach-analytics?email={quote(email)}")
        if r.status_code == 404:
            return []
        if r.status_code != 200:
            raise SourceUnavailable(self.meta.name, f"http_{r.status_code}")
        data = r.json()
        exposed = (data.get("ExposedBreaches") or {}).get("breaches_details") or []
        out = []
        for b in exposed:
            out.append({
                "name": b.get("breach"), "domain": b.get("domain"), "year": b.get("xposed_date"),
                "data_types": normalise_types(b.get("xposed_data", "")), "description": b.get("details"),
                "password_risk": b.get("password_risk"), "verified": b.get("verified") == "Yes",
                "reference": b.get("references") or f"https://xposedornot.com/xposed#{quote(b.get('breach') or '')}",
                "records": b.get("xposed_records"),
            })
        return out

    def test(self) -> str:
        self.http("GET", "https://api.xposedornot.com/v1/breaches?domain=example.com")
        return "ok"


class PwnedPasswords(Adapter):
    meta = AdapterMeta(
        name="pwned_passwords", label="Pwned Passwords (range API)", modules=["password_check"],
        terms_url="https://haveibeenpwned.com/API/v3#PwnedPasswords", data_types=["sha1_prefix"],
        rate_per_day=100000, notes="Keyless, no rate limit on range API; only 5-char SHA-1 prefixes are sent.",
    )

    def range(self, prefix: str) -> str:
        r = self.http("GET", f"https://api.pwnedpasswords.com/range/{prefix}", headers={"Add-Padding": "true"})
        if r.status_code != 200:
            raise SourceUnavailable(self.meta.name, f"http_{r.status_code}")
        return r.text


class HibpEmail(Adapter):
    meta = AdapterMeta(
        name="hibp_email", label="Have I Been Pwned (E-Mail API)", modules=["breach_check"],
        terms_url="https://haveibeenpwned.com/API/v3", data_types=["email"], requires_key=True, paid=True,
        default_enabled=False, key_env="HIBP_API_KEY", rate_per_day=1000, min_interval_s=6.1,
        signup_url="https://haveibeenpwned.com/API/Key", notes="Paid subscription. Disabled by default.",
    )

    def breaches(self, email: str) -> list[dict]:
        k = self.require_key()
        r = self.http("GET", f"https://haveibeenpwned.com/api/v3/breachedaccount/{quote(email)}?truncateResponse=false",
                      headers={"hibp-api-key": k})
        if r.status_code == 404:
            return []
        if r.status_code != 200:
            raise SourceUnavailable(self.meta.name, f"http_{r.status_code}")
        return [{"name": b["Name"], "domain": b.get("Domain"), "year": (b.get("BreachDate") or "")[:4],
                 "data_types": normalise_types(";".join(b.get("DataClasses", []))), "description": None,
                 "verified": b.get("IsVerified"), "reference": f"https://haveibeenpwned.com/PwnedWebsites#{b['Name']}",
                 "records": b.get("PwnCount")} for b in r.json()]
