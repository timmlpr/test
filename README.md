# Tracelow – „Mach deinen digitalen Fußabdruck kleiner.“

German-language, GDPR-first web app (PWA) that shows people where **their own** data can be found online, how exposed they
are, and guides them step by step to reduce it. Brand, tagline, prices and plan limits live only in
[`config/brand.json`](config/brand.json) and [`config/plans.json`](config/plans.json).

## Start in one command

| Where | Command | URL |
|---|---|---|
| Windows | double-click **`start.bat`** (Docker Desktop if present, else installs Python/Node via winget) | http://localhost:3000 |
| macOS / Linux | `./start.sh` | http://localhost:3000 |
| Docker (full stack: Postgres + API + web) | `docker compose up --build` | http://localhost:3000 |

Demo mode is on by default (no keys needed). Demo accounts:

| Account | Password | What you see |
|---|---|---|
| `demo@demo.example.com` | `TracelowDemo1!` | Premium, full sample data |
| `free@demo.example.com` | `TracelowDemo1!` | Free plan, plan gating, demo checkout |
| `admin@demo.example.com` | `TracelowAdmin1!` | Admin (TOTP secret `TRACELOWDEMOADMINTOTPKEYABCDEFG2` – dev only) |

Mails are not sent without SMTP; they appear in the dev outbox at `/api/dev/outbox` (development only).

## Repository

```
config/      single source of truth: brand, prices, plan limits
backend/     FastAPI (Python 3.13), SQLAlchemy, Alembic, APScheduler – app/modules/* = one module per feature
frontend/    Next.js 16 (App Router, TypeScript, Tailwind, shadcn-style UI, Recharts, PWA)
legal/       legal DRAFTS (imprint, privacy, terms, withdrawal, usage terms, DPIA, record of processing, retention)
marketing/   brand assets (SVG logo/wordmark, social preview), 20 short-video scripts
deploy/      Caddyfile (auto HTTPS), encrypted backups + restore test, Hetzner setup
docs/        DEPLOYMENT.md
```

## Development

```bash
cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
DEMO_MODE=true uvicorn app.main:app --reload --port 8000        # API docs: http://localhost:8000/api/docs
cd frontend && npm install && npm run dev                        # http://localhost:3000 (proxies /api → :8000)
```

Tests:

```bash
cd backend && pytest -q                                          # 86 tests: unit, API per module, Stripe webhooks, hard limits
cd frontend && npm run typecheck && npm run build
# e2e (needs both servers running; backend with RATELIMIT_ENABLED=false and a fresh demo DB):
cd frontend && npx playwright test --trace off                  # 21 tests, desktop + mobile
```

## Modules

M-01 privacy scan · M-02 breach check · M-03 risk score (pure rules, `backend/app/modules/risk_rules.py`) · M-04 GDPR requests
+ deadline tracker · M-05 monitor · M-06 scam check · M-07 domain check · M-08 image integrity · M-09 security checklist ·
M-10 password check (k-anonymity) · M-11 social privacy · M-12 subscription guard · M-13 document scanner · M-14 digital
estate (E2E-encrypted) · M-15 timeline · M-16 relation graph (own data only) · M-17 assistant · M-18 voice · M-19 reports
(PDF/XLSX) · M-20 results database. Details: [PLAN.md](PLAN.md).

## Further docs
[ADAPTERS.md](ADAPTERS.md) · [SECURITY.md](SECURITY.md) · [PRIVACY.md](PRIVACY.md) · [API_KEYS.md](API_KEYS.md) ·
[SETUP_CHECKLIST.md](SETUP_CHECKLIST.md) · [LAUNCH_CHECKLIST.md](LAUNCH_CHECKLIST.md) · [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
