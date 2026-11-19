#!/usr/bin/env bash
# One-shot setup on a fresh Hetzner Cloud server (Ubuntu 24.04, location nbg1/fsn1 = Germany).
#   curl -fsSL <raw-url>/lernzentrum/deploy/hetzner-setup.sh | sudo LZ_DOMAIN=lernen.example.de REPO=<git-url> bash
# Point the domain's A/AAAA record at the server first – Caddy then fetches the TLS certificate automatically.
set -euo pipefail
: "${LZ_DOMAIN:?LZ_DOMAIN fehlt (z. B. lernen.example.de)}"
REPO=${REPO:-}
BRANCH=${BRANCH:-main}
APP_DIR=/opt/lernzentrum

apt-get update -y
apt-get install -y ca-certificates curl git ufw unattended-upgrades fail2ban
if ! command -v docker >/dev/null; then curl -fsSL https://get.docker.com | sh; fi
ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw allow 443/udp && ufw --force enable
dpkg-reconfigure -f noninteractive unattended-upgrades

if [ -n "$REPO" ] && [ ! -d "$APP_DIR/.git" ]; then git clone --branch "$BRANCH" "$REPO" "$APP_DIR"; fi
cd "$APP_DIR/lernzentrum" 2>/dev/null || cd "$APP_DIR"
ENV=deploy/.env
if [ ! -f "$ENV" ]; then
  umask 077
  cat > "$ENV" <<CONF
LZ_DOMAIN=$LZ_DOMAIN
ACME_EMAIL=${ACME_EMAIL:-}
POSTGRES_PASSWORD=$(openssl rand -hex 24)
LZ_MASTER_KEY=$(openssl rand -base64 32)
LZ_SESSION_SECRET=$(openssl rand -base64 32)
BACKUP_PASSPHRASE=$(openssl rand -base64 32)
BACKUP_KEEP_DAYS=14
LZ_DEMO_MODE=false
CONF
  echo ">>> $ENV erzeugt. LZ_MASTER_KEY und BACKUP_PASSPHRASE zusätzlich offline sichern (ohne sie sind Backups nicht lesbar)."
fi
mkdir -p deploy/backups
docker compose -f deploy/docker-compose.prod.yml --env-file "$ENV" up -d --build
echo ">>> Lernzentrum läuft: https://$LZ_DOMAIN  (Health: https://$LZ_DOMAIN/api/health)"
