"""Passive domain sources: RDAP, DNS-over-HTTPS, HTTPS headers/TLS, Wayback, imprint page.
No port scans; only standard requests any browser would make. robots.txt is respected for page fetches."""
from __future__ import annotations

import socket
import ssl
from datetime import datetime
from urllib import robotparser
from urllib.parse import urljoin

from app.adapters.base import USER_AGENT, Adapter, AdapterMeta, SourceUnavailable
from app.core.clock import utcnow


class Rdap(Adapter):
    meta = AdapterMeta(name="rdap", label="RDAP (rdap.org bootstrap)", modules=["domain_check", "scam_check"],
                       terms_url="https://about.rdap.org/", data_types=["domain"], rate_per_day=3000, min_interval_s=0.5,
                       notes="IANA bootstrap redirector; keyless.")

    def lookup(self, domain: str) -> dict:
        r = self.http("GET", f"https://rdap.org/domain/{domain}", headers={"Accept": "application/rdap+json"})
        if r.status_code == 404:
            return {"found": False}
        if r.status_code != 200:
            raise SourceUnavailable(self.meta.name, f"http_{r.status_code}")
        d = r.json()
        events = {e.get("eventAction"): e.get("eventDate") for e in d.get("events", [])}
        registrar = None
        for ent in d.get("entities", []):
            if "registrar" in ent.get("roles", []):
                v = ent.get("vcardArray", [None, []])[1]
                registrar = next((x[3] for x in v if x[0] == "fn"), None) or ent.get("handle")
        return {"found": True, "registered": events.get("registration"), "updated": events.get("last changed"),
                "expires": events.get("expiration"), "registrar": registrar, "status": d.get("status", []),
                "nameservers": [n.get("ldhName") for n in d.get("nameservers", [])]}


class DnsDoh(Adapter):
    meta = AdapterMeta(name="dns_doh", label="DNS over HTTPS (Cloudflare)", modules=["domain_check", "scam_check"],
                       terms_url="https://developers.cloudflare.com/1.1.1.1/encryption/dns-over-https/",
                       data_types=["domain"], rate_per_day=20000)

    def records(self, domain: str) -> dict:
        out: dict[str, list[str]] = {}
        for t in ("A", "AAAA", "MX", "TXT", "NS", "CAA"):
            r = self.http("GET", "https://cloudflare-dns.com/dns-query", params={"name": domain, "type": t},
                          headers={"Accept": "application/dns-json"}, retries=1)
            if r.status_code == 200:
                out[t] = [a.get("data", "") for a in r.json().get("Answer", []) or []]
        return out


class WebPassive(Adapter):
    meta = AdapterMeta(name="web_passive", label="Passive HTTPS check (headers, TLS, imprint)",
                       modules=["domain_check", "scam_check"], terms_url="https://www.rfc-editor.org/rfc/rfc9110",
                       data_types=["domain"], rate_per_day=5000, min_interval_s=0.2,
                       notes="One GET of the homepage, one TLS handshake, optional imprint page if robots.txt allows.")

    SEC_HEADERS = ["strict-transport-security", "content-security-policy", "x-content-type-options",
                   "x-frame-options", "referrer-policy", "permissions-policy"]

    def tls(self, domain: str) -> dict:
        ctx = ssl.create_default_context()
        try:
            with socket.create_connection((domain, 443), timeout=8) as sock, ctx.wrap_socket(sock, server_hostname=domain) as s:
                c = s.getpeercert()
            issuer = dict(x[0] for x in c.get("issuer", []))
            not_after = datetime.strptime(c["notAfter"], "%b %d %H:%M:%S %Y %Z")
            return {"valid": True, "issuer": issuer.get("organizationName"), "expires": not_after.isoformat(),
                    "days_left": (not_after - utcnow()).days}
        except ssl.SSLError as e:
            return {"valid": False, "error": type(e).__name__}
        except OSError:
            return {"valid": False, "error": "unreachable"}

    def page(self, domain: str) -> dict:
        r = self.http("GET", f"https://{domain}/", retries=1)
        html = r.text[:400_000] if "text/html" in r.headers.get("content-type", "") else ""
        headers = {h: r.headers.get(h) for h in self.SEC_HEADERS}
        tech = []
        for h in ("server", "x-powered-by"):
            if r.headers.get(h):
                tech.append(f"{h}: {r.headers[h]}")
        low = html.lower()
        for sig, name in (("wp-content", "WordPress"), ("shopify", "Shopify"), ("__next", "Next.js"), ("wix.com", "Wix"),
                          ("jimdo", "Jimdo"), ("woocommerce", "WooCommerce"), ("magento", "Magento"), ("gtag(", "Google Analytics")):
            if sig in low:
                tech.append(name)
        imprint_url = None
        import re

        m = re.search(r'href="([^"]*(?:impressum|imprint|legal-notice)[^"]*)"', html, re.I)
        if m:
            imprint_url = urljoin(str(r.url), m.group(1))
        return {"status": r.status_code, "final_url": str(r.url), "headers": headers, "tech": tech,
                "imprint_url": imprint_url, "html": html}

    def imprint(self, url: str) -> dict:
        rp = robotparser.RobotFileParser()
        rp.set_url(urljoin(url, "/robots.txt"))
        try:
            rp.read()
            if not rp.can_fetch(USER_AGENT, url):
                return {"fetched": False, "reason": "robots_disallow"}
        except Exception:  # noqa: BLE001 – unreadable robots.txt → be conservative
            return {"fetched": False, "reason": "robots_unreadable"}
        import re

        r = self.http("GET", url, retries=1)
        text = re.sub(r"<[^>]+>", " ", r.text[:300_000])
        text = re.sub(r"\s+", " ", text)
        found = {
            "has_address": bool(re.search(r"\b\d{5}\s+[A-ZÄÖÜ][a-zäöüß]+", text)),
            "has_email": bool(re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)),
            "has_register": bool(re.search(r"(HRB|HRA|Handelsregister|Registergericht)", text)),
            "has_vat": bool(re.search(r"(USt-?IdNr|DE\s?\d{9})", text)),
        }
        return {"fetched": True, **found}


class Wayback(Adapter):
    meta = AdapterMeta(name="wayback", label="Internet Archive Wayback (CDX API)", modules=["domain_check", "scam_check"],
                       terms_url="https://archive.org/about/terms.php", data_types=["domain"], rate_per_day=2000,
                       min_interval_s=1.0)

    def first_capture(self, domain: str) -> dict:
        r = self.http("GET", "https://web.archive.org/cdx/search/cdx",
                      params={"url": domain, "limit": 1, "output": "json", "fl": "timestamp"}, timeout=15, retries=1)
        if r.status_code != 200:
            raise SourceUnavailable(self.meta.name, f"http_{r.status_code}")
        rows = r.json()
        if len(rows) < 2:
            return {"first": None, "link": f"https://web.archive.org/web/*/{domain}"}
        ts = rows[1][0]
        return {"first": f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}", "link": f"https://web.archive.org/web/*/{domain}"}
