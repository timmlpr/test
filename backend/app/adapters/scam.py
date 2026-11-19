"""Threat-intel sources for the scam check. Both need FREE keys and stay disabled until configured."""
from __future__ import annotations

from app.adapters.base import Adapter, AdapterMeta, SourceUnavailable


class SafeBrowsing(Adapter):
    meta = AdapterMeta(name="safe_browsing", label="Google Safe Browsing v4 (Lookup API)", modules=["scam_check"],
                       terms_url="https://developers.google.com/safe-browsing/v4/usage-limits", data_types=["url"],
                       requires_key=True, key_env="SAFE_BROWSING_KEY", rate_per_day=10000,
                       signup_url="https://console.cloud.google.com/apis/library/safebrowsing.googleapis.com",
                       notes="Free for non-commercial use per Google terms; commercial use → Web Risk API. Check before launch.")

    def check(self, url: str) -> dict:
        k = self.require_key()
        body = {"client": {"clientId": "tracelow", "clientVersion": "1.0"},
                "threatInfo": {"threatTypes": ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE", "POTENTIALLY_HARMFUL_APPLICATION"],
                               "platformTypes": ["ANY_PLATFORM"], "threatEntryTypes": ["URL"], "threatEntries": [{"url": url}]}}
        r = self.http("POST", f"https://safebrowsing.googleapis.com/v4/threatMatches:find?key={k}", json=body)
        if r.status_code != 200:
            raise SourceUnavailable(self.meta.name, f"http_{r.status_code}")
        matches = r.json().get("matches", [])
        return {"listed": bool(matches), "threats": sorted({m["threatType"] for m in matches})}


class UrlHaus(Adapter):
    meta = AdapterMeta(name="urlhaus", label="abuse.ch URLhaus", modules=["scam_check"],
                       terms_url="https://urlhaus.abuse.ch/api/", data_types=["url"], requires_key=True,
                       key_env="URLHAUS_AUTH_KEY", rate_per_day=5000, signup_url="https://auth.abuse.ch/",
                       notes="Free Auth-Key required since 2025-06-30; keyless text feeds return HTTP 410 (checked 2026-11).")

    def check(self, url: str) -> dict:
        k = self.require_key()
        r = self.http("POST", "https://urlhaus-api.abuse.ch/v1/url/", data={"url": url}, headers={"Auth-Key": k})
        if r.status_code != 200:
            raise SourceUnavailable(self.meta.name, f"http_{r.status_code}")
        d = r.json()
        return {"listed": d.get("query_status") == "ok", "threat": d.get("threat"), "status": d.get("url_status")}


class TinEye(Adapter):
    meta = AdapterMeta(name="tineye", label="TinEye API", modules=["image_integrity"], terms_url="https://services.tineye.com/TinEyeAPI",
                       data_types=["own_image"], requires_key=True, paid=True, default_enabled=False, key_env="TINEYE_API_KEY",
                       signup_url="https://services.tineye.com/TinEyeAPI", notes="Paid. Free alternative: manual reverse-search links.")
