# Security

| Control | Implementation |
|---|---|
| Passwords | Argon2id (argon2-cffi defaults), min. 10 chars, no plaintext anywhere; password check is k-anonymous in the browser |
| Sessions | signed JWT in `fp_session` cookie: httpOnly, SameSite=Lax, Secure in prod; `session_version` for "log out everywhere" |
| CSRF | double-submit token (`fp_csrf` cookie + `x-csrf-token` header) on every non-GET; Stripe webhook exempt (signature-verified) |
| 2FA | TOTP (pyotp) + 10 single-use recovery codes (hashed); passkeys (WebAuthn, py_webauthn); admin area requires role=admin **and** a TOTP/passkey session |
| OAuth | Google/Apple OIDC: state token, id_token verified against provider JWKS (aud, iss) |
| Encryption at rest | AES-256-GCM per field (`EncryptedText`) for emails, identifiers, findings, requests, documents, keys; lookups via HMAC-SHA256; digital estate is E2E (PBKDF2 310k + AES-GCM in the browser) |
| Rate limiting | sliding window per IP/account on login, register, reset, 2FA, scans, tools; plan quotas per user; source quotas per day |
| Abuse | own-data consent per identifier, verification (link / code / DNS TXT), anomaly lock on too many distinct names, hard-limit guard on all free text, public abuse report form, audit log |
| Input validation | Pydantic models with lengths/patterns everywhere; upload size limits; images processed in memory only |
| Headers | CSP, X-Frame-Options DENY, nosniff, Referrer-Policy, Permissions-Policy (Next + API), HSTS (Caddy) |
| Secrets | only via `.env`; prod refuses to start without SECRET_KEY/DATA_KEY; source keys stored encrypted |
| Logs | no personal plaintext: audit meta = ids/counts; IP only as daily-salted hash; Caddy logs mask IPs and drop query strings |
| Dependencies | `pip-audit` + `npm audit` in CI (0 known vulnerabilities at build time) |
| Backups | daily `pg_dump` + uploads, AES-256 (openssl PBKDF2), 30-day rotation, `deploy/restore-test.sh` |
| Retention | daily job (`app/jobs.py`) – see PRIVACY.md |

## Hard limits (tested in `backend/tests/test_hard_limits.py` and `frontend/e2e/app.spec.ts`)
No third-party search, no face recognition, no plate lookups, no spying, no relationship inference, no bypassing of
logins/captchas/robots.txt, no plaintext passwords, no dark patterns. These are enforced server-side in
`backend/app/core/guard.py` and in the data model; there is no flag to turn them off.

## Load / security checks
`backend/tests/load_smoke.py` runs a concurrency smoke test against a running API (see file header).
Report vulnerabilities to the address in the imprint.
