# Fadeprint – Build Plan

> Working name "Fadeprint". Brand, tagline, prices, plan limits live in **`config/brand.json`** and
> **`config/plans.json`** only. Backend and frontend both read these files, so a rename or price
> change needs no refactor.

## 1. Architecture

```
            ┌──────────── Caddy (HTTPS, security headers, gzip) ────────────┐
 Browser ──►│  /api/*  → backend:8000 (FastAPI)    /*  → frontend:3000 (Next) │
            └────────────────────────────────────────────────────────────────┘
 backend ── PostgreSQL (prod) / SQLite (dev) ── APScheduler (monitor, reminders, retention)
         └─ Source adapters (plugins) ── Quota manager ── external free APIs
         └─ AI layer (AiProvider: none | gemini | claude) behind anonymiser
```

* **frontend/** Next.js 15 (App Router, TypeScript), Tailwind CSS, shadcn/ui-style components
  (written in-repo with `class-variance-authority` + `tailwind-merge`, the same pattern the shadcn CLI
  generates – avoids an interactive CLI during automated builds), Recharts, PWA (manifest + hand-written
  service worker), i18n dictionaries `de` (default) / `en`, Du/Sie switch.
* **backend/** FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, APScheduler, argon2-cffi, pyotp,
  `webauthn`, PyJWT (OIDC id_token check for Apple/Google), stripe, reportlab (PDF), openpyxl (XLSX),
  Pillow (EXIF/ELA), pypdf (+ optional tesseract OCR), pywebpush, cryptography (AES-GCM).
* Same-origin deployment: the browser only ever talks to one origin. In dev, Next.js rewrites
  `/api/*` to the backend. Session = signed httpOnly cookie; CSRF = double-submit token header.

## 2. Deviations from the prompt (with reasons)

| Topic | Decision | Reason |
|---|---|---|
| Background jobs | APScheduler in-process (single worker) instead of Celery/RQ + Redis | Fewer moving parts for a one-server Hetzner deploy; jobs are light (re-scans, reminders, retention). Adapter boundary lets us swap to RQ later. |
| shadcn/ui | Components written in-repo following the shadcn pattern | The CLI is interactive/network-dependent; output is identical in style and ownership. |
| Google Programmable Search | Adapter shipped **disabled** | Verified 2026-11: Custom Search JSON API is closed to new customers and shuts down 2027-01-01. |
| Brave Search | Optional key adapter | Verified 2026-11: free plan replaced by $5 monthly credit (≈1,000 requests), card required. |
| URLhaus | Optional free key adapter | Verified 2026-11: API requires a free `Auth-Key` since 2025-06-30; keyless text feed returns HTTP 410. |
| PhishTank | Not shipped | Verified 2026-11: new registrations closed, no way to obtain an app key. |
| XposedOrNot | Keyless default for email leaks | Public endpoints free, documented limit 1 request/second → quota manager enforces it. |
| Gemini | Optional AI provider | Free tier inputs "used to improve products" → anonymiser is mandatory, in-app notice shown. |
| Celery beat "daily scans" | Scheduled by APScheduler cron jobs | see above |

## 3. Data model (SQLAlchemy, `backend/app/models.py`)

Sensitive columns are AES-GCM encrypted (`EncryptedText` type, key `FP_DATA_KEY`). Lookups use an
HMAC hash column (`*_hash`) so plaintext never needs to be indexed.

* `User` – email(enc)+email_hash, password_hash (Argon2id), email_verified, role (user|admin), plan
  (free|premium|family_owner|family_member), trial_ends_at, address_form (du|sie), locale, totp
  secret(enc), recovery code hashes, referral_code, locked/lock_reason, is_child, guardian_id.
* `OAuthAccount`, `Passkey` (WebAuthn credential), `ConsentLog` (kind, version, granted, ts, ip hash).
* `Identifier` – kind (name|email|phone|city|username|domain), value(enc)+hash, verified_at,
  own-data confirmation timestamp. **Only verified identifiers can be scanned.**
* `Scan`, `Finding` (module, source, url, data_type, risk, found_at, status open|done|trash, tags, note,
  attributable), `RiskSnapshot` (score, factors JSON).
* `DeletionRequest` (art15|art16|art17, recipient, body, status open|sent|done|rejected, due_at).
* `QuotaUsage` (source, day, count), `SourceKey` (enc key per adapter), `AuditLog`.
* Billing: `Subscription`, `Purchase`, `Voucher`, `Referral`, `FamilyGroup`, `FamilyMember`.
* Growth: `WaitlistEntry`, `InviteCode`, `Feedback`, `AbuseReport`.
* Modules: `ChecklistItemState`, `SocialItemState`, `MonitorSettings`, `PushSubscription`,
  `Notification`, `TimelineEvent`, `Upload`, `MailSubscription`, `Document`, `Reminder`,
  `EstateVault`, `FamilyTreePerson`, `Report`, `AiUsage`, `AiCache`.

## 4. API routes (prefix `/api`)

| Area | Routes |
|---|---|
| health/config | `GET /health`, `GET /config/public` |
| auth | `POST /auth/register, /auth/login, /auth/logout, /auth/verify-email, /auth/totp/*, /auth/recovery`, `GET /auth/me`, `GET/POST /auth/oauth/{google,apple}/*`, `POST /auth/passkey/{register,login}/{begin,finish}` |
| profile | `GET/POST/DELETE /profile/identifiers`, `POST /profile/identifiers/{id}/verify`, `PATCH /profile/settings`, `GET /profile/export` (Art. 20), `DELETE /profile` |
| M-01 scan | `POST /scan/run`, `GET /scan/history` |
| M-20 results | `GET /findings?q&module&source&risk&status&from&to`, `PATCH /findings/{id}`, `POST /findings/{id}/restore` |
| M-02 breach | `POST /breach/check`, `GET /breach` |
| M-10 password | `GET /password/range/{prefix}` (k-anonymity proxy; plaintext never leaves the browser) |
| M-03 risk | `GET /risk`, `GET /risk/history`, `GET /home` |
| M-04 deletion | `GET/POST /requests`, `PATCH /requests/{id}`, `GET /requests/{id}/pdf`, `GET /requests/templates` |
| M-19 reports | `GET /reports/preview`, `POST /reports`, `GET /reports`, `GET /reports/{id}/{pdf,xlsx}`, `GET /reports/compare` |
| billing | `GET /billing/plans`, `POST /billing/checkout`, `POST /billing/portal`, `POST /billing/cancel`, `POST /billing/webhook`, `POST /billing/voucher`, `GET /billing/referral` |
| family | `GET/POST /family`, `POST /family/invite`, `POST /family/join/{token}`, `POST /family/child` |
| M-06/07/08 | `POST /scam/check`, `POST /domain/check`, `POST /image/analyze`, `POST /image/strip`, `POST /image/reverse-links` |
| M-09/M-11 | `GET/PATCH /checklist`, `GET/PATCH /social` |
| M-05/M-15 | `GET/PUT /monitor/settings`, `POST /monitor/run`, `POST /push/subscribe`, `GET /notifications`, `GET /timeline` |
| M-12/13/14 | `POST /subs/upload`, `GET /subs`, `GET /subs/xlsx`, `POST /documents`, `GET /documents`, `DELETE /documents/{id}`, `GET/PUT /estate`, `POST /estate/unlock-request` |
| M-16/17 | `GET /graph`, `GET/POST/DELETE /graph/family`, `POST /assistant/chat` |
| growth | `POST /waitlist`, `GET /waitlist/confirm`, `POST /feedback`, `POST /abuse` |
| admin (2FA) | `GET /admin/stats, /admin/quota, /admin/audit, /admin/waitlist`, `PUT/POST /admin/keys/{source}[/test]`, `POST /admin/waitlist/approve`, `POST /admin/invite-codes` |

## 5. Source adapters (see ADAPTERS.md)

| Adapter | Module | Key | Default |
|---|---|---|---|
| xposedornot | M-02, M-01 | none | enabled |
| pwned_passwords | M-10 | none | enabled |
| wikipedia (de/en) | M-01 (own name only) | none | enabled |
| rdap | M-07 | none | enabled |
| dns_doh (Cloudflare/Google DoH) | M-07, M-06 | none | enabled |
| tls / headers (passive HTTPS GET) | M-07 | none | enabled |
| wayback | M-07 | none | enabled |
| crtsh | M-07 | none | enabled |
| brave_search | M-01 deep scan | free credit key | disabled until key |
| google_cse | M-01 | legacy key | disabled (closed to new customers) |
| safe_browsing | M-06 | free key | disabled until key |
| urlhaus | M-06 | free key | disabled until key |
| hibp_email | M-02 | paid | disabled |
| tineye | M-08 | paid | disabled |
| demo | all | none | used only in DEMO_MODE |

Each adapter declares: `name, modules, terms_url, allowed_data_types, rate_limit_per_day,
rate_limit_per_second, requires_key, permitted`. Adapters with `permitted=False` cannot be enabled.

## 6. Hard limits (enforced in `backend/app/core/guard.py`, tested in `tests/test_hard_limits.py`)

* No endpoint accepts a free-text person query. Scans take identifier **IDs** that must be verified and
  owned by the caller.
* Name identifiers: anomaly lock when a user adds more than N distinct names (config).
* Plate pattern, face-recognition, spying and third-party-profiling intents are detected and refused
  in every free-text input (assistant, voice, scam text).
* Passwords: only SHA-1 prefixes (5 chars) are ever received; no plaintext column exists.
* No dark patterns: cancel endpoint = one call, no retention flow; no countdowns.

## 7. Milestones

M1 skeleton/design/PWA/landing/waitlist · M2 accounts · M3 adapters/quota/scan/results ·
M4 breach/password/risk/home · M5 deletion/reports · M6 Stripe · M7 scam/domain/image ·
M8 checklists · M9 monitor/push/timeline · M10 subscriptions/documents/estate ·
M11 graph/assistant/voice · M12 legal/blog/scripts/launch · M13 hardening/deploy/docs.

## 8. Testing

* `backend/tests` (pytest): risk score, rule engine, anonymiser, pricing, guard, API flows per module,
  Stripe webhook (signed test events), hard-limit tests.
* `frontend/e2e` (Playwright): landing, login with demo user, every app page renders, hard-limit UI.
