#!/bin/sh
# Hugging Face sets SPACE_HOST (e.g. user-tracelow.hf.space); fall back to localhost for local tests.
set -e
mkdir -p /tmp/tracelow/uploads
HOST="${SPACE_HOST:-localhost:7860}"
case "$HOST" in localhost*) export PUBLIC_URL="http://$HOST" COOKIE_SECURE=false ;; *) export PUBLIC_URL="https://$HOST" ;; esac
export WEBAUTHN_RP_ID="${HOST%%:*}"
cd backend && uvicorn app.main:app --host 127.0.0.1 --port 8000 &
cd /home/user/app/web
for i in $(seq 1 60); do python3 -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health')" 2>/dev/null && break; sleep 1; done
exec node server.js
