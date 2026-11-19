# API keys – step by step

Everything works **without any key** (classic mode, keyless sources, demo billing). Keys only add sources.
Enter keys either in `.env` or in the app: **Admin → Schlüssel & Quoten** (stored AES-encrypted, with a "Testen" button).

## Free keys (optional upgrades)

### Brave Search API – deep scan (findability on the web)
1. https://api-dashboard.search.brave.com/register → sign up.
2. Choose the **Search** plan; Brave grants **$5 credit per month** (≈1,000 requests). A card is required (checked 2026-11).
3. *API Keys* → *Add API key* → copy. `.env`: `BRAVE_API_KEY=...`. Tracelow caps usage at 30 requests/day.

### Google Safe Browsing – scam check
1. https://console.cloud.google.com → create project → *APIs & Services* → enable **Safe Browsing API**.
2. *Credentials* → *Create credentials* → *API key* → restrict to Safe Browsing API.
3. `.env`: `SAFE_BROWSING_KEY=...`
4. ⚠ Google's terms allow free use for non-commercial purposes; a paid app must use the **Web Risk API** – check before launch.

### abuse.ch URLhaus – scam check
1. https://auth.abuse.ch/ → sign in (GitHub/Google/X/LinkedIn).
2. Profile → *Optional* → generate **Auth-Key**. `.env`: `URLHAUS_AUTH_KEY=...`

### Google Gemini – AI assistant (free tier)
1. https://aistudio.google.com → *Get API key* → create.
2. `.env`: `AI_MODE=both`, `AI_PROVIDER=gemini`, `GEMINI_API_KEY=...`
3. Free tier inputs may be used to improve Google products → Tracelow anonymises all text and shows a notice. Use a paid
   tier for the planned "privacy guarantee" plan.

### Web Push (VAPID) – push notifications (no account)
`npx web-push generate-vapid-keys` → `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`.

### seven.io – SMS codes for phone verification
1. https://app.seven.io/signup → top up credit (pay per SMS, EU provider).
2. *Developer → API keys* → create. `.env`: `SMS_PROVIDER=seven`, `SMS_API_KEY=...`, optional `SMS_SENDER=Tracelow` (max. 11 characters).
Without it, phone codes appear only in the dev outbox (demo/dev); in production phone verification is shown as unavailable.

### Gmail connection – subscription guard (read-only)
Uses the Google OAuth client from "Google sign-in" below. Additionally: *APIs & Services → Library → Gmail API → Enable*;
*OAuth consent screen → Scopes → add* `https://www.googleapis.com/auth/gmail.metadata`; authorised redirect URI
`https://<domain>/api/subs/mailbox/callback`. `gmail.metadata` is a **restricted scope**: up to 100 test users work
immediately; a public launch needs Google's app verification incl. a third-party security assessment (CASA) – plan weeks.
Tracelow reads headers only, stores the refresh token encrypted, and revokes it on disconnect or account deletion.

## Accounts needed for login / payments
* **Stripe** (test mode free): https://dashboard.stripe.com/register → *Developers → API keys* → `STRIPE_SECRET_KEY=sk_test_...`.
  Webhook: *Developers → Webhooks → Add endpoint* `https://<domain>/api/billing/webhook`, events
  `checkout.session.completed, customer.subscription.updated, customer.subscription.deleted, invoice.payment_failed`
  → `STRIPE_WEBHOOK_SECRET=whsec_...`. Enable PayPal, Apple Pay, SEPA in *Settings → Payment methods*. Customer portal:
  *Settings → Billing → Customer portal* → enable cancellation. Optional `STRIPE_TAX=true` after Stripe Tax setup.
* **Google sign-in**: https://console.cloud.google.com → *APIs & Services → Credentials → OAuth client ID (Web)* → redirect
  URI `https://<domain>/api/auth/oauth/google/callback` → `GOOGLE_CLIENT_ID/SECRET`.
* **Sign in with Apple** (Apple Developer Program, 99 USD/year): create Services ID + key → `APPLE_CLIENT_ID`,
  `APPLE_TEAM_ID`, `APPLE_KEY_ID`, `APPLE_PRIVATE_KEY` (PEM, `\n`-escaped). Return URL `https://<domain>/api/auth/oauth/apple/callback`.
* **SMTP** (any EU provider, e.g. your mail host): `SMTP_HOST/PORT/USER/PASSWORD/SMTP_FROM`.

## Paid (disabled by default)
* **HIBP e-mail API** (https://haveibeenpwned.com/API/Key) → `HIBP_API_KEY` – becomes the first source in the breach chain.
* **TinEye API** – adapter stub only; manual reverse-search links are the default.
* **Google Programmable Search** – closed to new customers; only for existing legacy keys (`GOOGLE_CSE_KEY` + `GOOGLE_CSE_CX`).
