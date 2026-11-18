#!/bin/sh
# One-time server setup for a fresh Hetzner Cloud server (Ubuntu 24.04, location Falkenstein/Nuremberg = Germany).
# Run as root:  curl -fsSL <raw-url-of-this-file> | sh   or copy & run.  Then: cd /opt/fadeprint && cp .env.example .env && edit .env
set -eu
apt-get update && apt-get -y upgrade
apt-get install -y ca-certificates curl git ufw unattended-upgrades
curl -fsSL https://get.docker.com | sh
ufw default deny incoming && ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw allow 443/udp && ufw --force enable
dpkg-reconfigure -f noninteractive unattended-upgrades
mkdir -p /opt/fadeprint
[ -d /opt/fadeprint/.git ] || git clone "${REPO_URL:-https://github.com/timmlpr/test.git}" /opt/fadeprint
echo "Next: cd /opt/fadeprint && cp .env.example .env, set ENV=production DEMO_MODE=false DOMAIN=... secrets, then:"
echo "      docker compose --profile prod up -d --build"
