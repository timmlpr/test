"""Findability sources for the user's OWN verified identifiers only (callers pass verified values)."""
from __future__ import annotations

import re
from html import unescape

from app.adapters.base import Adapter, AdapterMeta, SourceUnavailable

TAG_RE = re.compile(r"<[^>]+>")


def _hit(source: str, title: str, url: str, snippet: str, data_type: str) -> dict:
    return {"source": source, "title": unescape(TAG_RE.sub("", title))[:200], "url": url,
            "snippet": unescape(TAG_RE.sub("", snippet))[:400], "data_type": data_type}


class Wikipedia(Adapter):
    meta = AdapterMeta(
        name="wikipedia", label="Wikipedia (MediaWiki API)", modules=["privacy_scan"],
        terms_url="https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use", data_types=["name"],
        rate_per_day=5000, min_interval_s=0.2, notes="Public API, identify via User-Agent; exact-phrase search only.",
    )

    def search(self, phrase: str, lang: str = "de") -> list[dict]:
        r = self.http("GET", f"https://{lang}.wikipedia.org/w/api.php",
                      params={"action": "query", "list": "search", "srsearch": f'"{phrase}"', "format": "json", "srlimit": 5})
        if r.status_code != 200:
            raise SourceUnavailable(self.meta.name, f"http_{r.status_code}")
        hits = r.json().get("query", {}).get("search", [])
        return [_hit("wikipedia", h["title"], f"https://{lang}.wikipedia.org/wiki/{h['title'].replace(' ', '_')}",
                     h.get("snippet", ""), "name") for h in hits]


class BraveSearch(Adapter):
    meta = AdapterMeta(
        name="brave_search", label="Brave Search API", modules=["privacy_scan"],
        terms_url="https://api-dashboard.search.brave.com/terms-of-service", data_types=["name", "email", "username", "phone"],
        requires_key=True, key_env="BRAVE_API_KEY", rate_per_day=30, min_interval_s=1.1,
        signup_url="https://api-dashboard.search.brave.com/register",
        notes="Since Feb 2026: $5 free monthly credit (~1,000 requests), card required. Daily cap 30 keeps us inside it.",
    )

    def search(self, phrase: str) -> list[dict]:
        k = self.require_key()
        r = self.http("GET", "https://api.search.brave.com/res/v1/web/search",
                      params={"q": f'"{phrase}"', "count": 10, "country": "DE", "search_lang": "de"},
                      headers={"X-Subscription-Token": k, "Accept": "application/json"})
        if r.status_code != 200:
            raise SourceUnavailable(self.meta.name, f"http_{r.status_code}")
        return [_hit("brave_search", w.get("title", ""), w.get("url", ""), w.get("description", ""), "web")
                for w in r.json().get("web", {}).get("results", [])]

    def test(self) -> str:
        self.search("Fadeprint")
        return "ok"


class GoogleCse(Adapter):
    meta = AdapterMeta(
        name="google_cse", label="Google Programmable Search (JSON API)", modules=["privacy_scan"],
        terms_url="https://developers.google.com/custom-search/v1/overview", data_types=["name", "email", "username"],
        requires_key=True, key_env="GOOGLE_CSE_KEY", default_enabled=False, rate_per_day=100,
        signup_url="https://developers.google.com/custom-search/v1/overview",
        notes="Closed to new customers (2026), shutdown 2027-01-01. Only for legacy keys. Needs GOOGLE_CSE_CX too.",
    )

    def search(self, phrase: str) -> list[dict]:
        import os

        k = self.require_key()
        cx = os.environ.get("GOOGLE_CSE_CX", "")
        r = self.http("GET", "https://www.googleapis.com/customsearch/v1", params={"key": k, "cx": cx, "q": f'"{phrase}"'})
        if r.status_code != 200:
            raise SourceUnavailable(self.meta.name, f"http_{r.status_code}")
        return [_hit("google_cse", i.get("title", ""), i.get("link", ""), i.get("snippet", ""), "web")
                for i in r.json().get("items", [])]
