# Source adapters

Every external source is a plugin in `backend/app/adapters/` subclassing `Adapter` with an `AdapterMeta` that declares
**source, terms of use, allowed data types, daily quota, min interval, key requirement, paid flag, permitted flag**.
All HTTP goes through `Adapter.http()` → quota manager (per source per day, persisted in `quota_usage`) → per-second
throttle → retries with exponential backoff → clean `SourceUnavailable` (shown in the UI as a calm notice, never a crash).
`first_available()` implements fallback chains (e.g. HIBP → XposedOrNot). Adapters with `permitted=False` can never be
enabled. Paid/legacy adapters (`default_enabled=False`) run only after an admin stores a key.

Terms were checked on **2026-11-17**. Re-check before launch (links below).

| Adapter | Modules | Key | Status | Limits we enforce | Notes |
|---|---|---|---|---|---|
| `xposedornot` | breach, scan | none | on | 1 req/s, 2,000/day | Public API, free. Domain endpoints (not used) need a key. [docs](https://xposedornot.com/api_doc) |
| `pwned_passwords` | password | none | on | – | k-anonymity range API, only 5-char SHA-1 prefix sent, `Add-Padding`. [docs](https://haveibeenpwned.com/API/v3#PwnedPasswords) |
| `wikipedia` | scan | none | on | 5/s, 5,000/day | exact-phrase search; hits flagged "not reliably attributable". [ToU](https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use) |
| `rdap` | domain, scam | none | on | 2/s | rdap.org IANA bootstrap |
| `dns_doh` | domain, scam, domain ownership | none | on | – | Cloudflare DNS-over-HTTPS |
| `web_passive` | domain, scam | none | on | – | one homepage GET, one TLS handshake, imprint page only if robots.txt allows. No port scans. |
| `wayback` | domain | none | on | 1/s | CDX API, first capture |
| `brave_search` | deep scan | free credit | off until key | 30/day | Since Feb 2026: $5 monthly credit (~1,000 req), card required |
| `google_cse` | deep scan | legacy | off | 100/day | Closed to new customers, shutdown 2027-01-01 |
| `safe_browsing` | scam | free key | off until key | 10,000/day | Free for non-commercial use; commercial → Web Risk API (check!) |
| `urlhaus` | scam | free Auth-Key | off until key | 5,000/day | Key required since 2025-06-30; keyless feed returns 410 |
| `hibp_email` | breach | paid | off | 6 s interval | Paid subscription |
| `tineye` | image | paid | off | – | Paid; free alternative = manual reverse-search links |
| `sms_seven` | phone verification | paid | off until key | 500/day | seven.io, Germany; only for ownership codes |
| Gmail API (in `modules/vault.py`) | subscription guard | Google OAuth | off until configured | 500 messages per sync | scope `gmail.metadata` – headers only |
| `demo` | all | none | DEMO_MODE only | – | deterministic sample data, labelled "Demo" |

Deliberately **not** built: PhishTank (registrations closed), any scraping of sites that forbid it, any people-search
scraping, face search, plate lookups. The architecture (generic adapters + quota) is reusable for a future separate
product "Atlas" – nothing for it is built here.

## Adding an adapter
1. Create a class with `meta = AdapterMeta(...)` (fill `terms_url`, `notes`, `verified_on`).
2. Use `self.http()` only. Never log query values.
3. Register it in `registry.py`. 4. Add a fake in tests. 5. Document it here and in API_KEYS.md if it needs a key.
