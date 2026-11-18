# Launch checklist

## Business & legal
- [ ] Choose legal form (Einzelunternehmen / UG / GmbH) and register the business (Gewerbeanmeldung, Finanzamt: Fragebogen zur steuerlichen Erfassung).
- [ ] Decide small-business rule (§ 19 UStG) vs. standard VAT → `config/brand.json → operator.small_business`.
- [ ] Fill operator data in `config/brand.json` (imprint is generated from it).
- [ ] **Trademark search for "Fadeprint"**: DPMA (https://register.dpma.de), EUIPO (https://euipo.europa.eu/eSearch), WIPO Global Brand DB; check app stores and domains. Consider filing (classes 9, 42, 45).
- [ ] Register domain(s) (.de / .com / .app).
- [ ] **Lawyer review** of all drafts in `/legal`: imprint, privacy policy, terms (AGB), withdrawal policy + early-expiry consent for the one-time report (§ 356 Abs. 5 BGB – add checkbox to checkout), usage terms, "no legal advice", cookie concept.
- [ ] Data-protection-officer assessment (§ 38 BDSG: ≥20 persons regularly processing personal data, or DPIA-mandatory core activity → likely **appoint** an external DPO; check with lawyer).
- [ ] Finalise DPIA (`legal/dsfa.md`) and record of processing (`legal/verarbeitungsverzeichnis.md`).
- [ ] Sign DPAs (AVV): Hetzner, Stripe, mail provider, AI provider (if enabled).
- [ ] Verify commercial-use terms of every enabled source (esp. Safe Browsing → Web Risk; XposedOrNot attribution).
- [ ] Insurance: professional/cyber liability (Vermögensschaden-/Cyber-Haftpflicht).
- [ ] Rechtsdienstleistungsgesetz check: templates are general information, user sends requests – confirm with lawyer.

## Technical
- [ ] `.env` from `.env.example` with `ENV=production`, `DEMO_MODE=false`, `COOKIE_SECURE=true`, fresh `SECRET_KEY`/`DATA_KEY`/`POSTGRES_PASSWORD`/`BACKUP_PASSPHRASE`.
- [ ] Hetzner server via `deploy/hetzner-setup.sh`; `docker compose --profile prod up -d --build`; DNS A/AAAA → server.
- [ ] Stripe live keys + webhook + customer portal (cancellation enabled) + payment methods; run one real 1 € test purchase and refund.
- [ ] SMTP with SPF/DKIM/DMARC for the sending domain.
- [ ] Create admin: register, set `role='admin'` in DB, enable TOTP.
- [ ] Run `deploy/restore-test.sh` once and document the result.
- [ ] Monitoring/uptime check on `/api/health`.
- [ ] Waitlist waves: Admin → Warteliste → "Welle freigeben".

## Later: store apps
- [ ] Wrap PWA with Capacitor (iOS/Android); Apple requires Sign in with Apple if Google login is offered; in-app purchase rules for digital subscriptions (or reader/link-out entitlement in the EU under the DMA) – check current store rules.
- [ ] Store privacy labels (App Privacy / Data safety) from `legal/verarbeitungsverzeichnis.md`.
