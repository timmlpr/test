# Deployment (Hetzner Cloud, Germany)

1. Create a server (Ubuntu 24.04, CX22, location **Falkenstein** or **Nuremberg**), add your SSH key.
2. `ssh root@SERVER 'REPO_URL=https://github.com/<owner>/<repo>.git sh -s' < deploy/hetzner-setup.sh`
3. On the server: `cd /opt/tracelow && cp .env.example .env` and set at least:
   ```
   ENV=production
   DEMO_MODE=false
   DOMAIN=tracelow.de
   PUBLIC_URL=https://tracelow.de
   WEBAUTHN_RP_ID=tracelow.de
   COOKIE_SECURE=true
   ACME_EMAIL=you@yourdomain
   SECRET_KEY=<base64 32 bytes>   DATA_KEY=<base64 32 bytes>
   POSTGRES_PASSWORD=<random>     BACKUP_PASSPHRASE=<random, store offline!>
   SMTP_*  STRIPE_*
   ```
4. Point DNS (A/AAAA) to the server, then `docker compose --profile prod up -d --build`.
   Caddy obtains certificates automatically. Health: `https://DOMAIN/api/health`.
5. Backups land in `/opt/tracelow/backups` (encrypted, daily, 30 days). Copy them off-site (e.g. Hetzner Storage Box via
   `rsync`). Test restore: `BACKUP_PASSPHRASE=... sh deploy/restore-test.sh`.
6. CI/CD: add GitHub secrets `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`; pushes to `main` deploy automatically after tests.

Upgrades: `git pull && docker compose --profile prod up -d --build` (migrations run on backend start via Alembic).

## Building behind a TLS-intercepting proxy
If your network re-signs HTTPS (corporate proxy), pass its CA as a BuildKit secret:
`docker build --secret id=ca,src=/path/to/ca.crt ...` (both Dockerfiles pick it up for pip/npm; nothing is stored in the image).
