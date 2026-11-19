#!/usr/bin/env bash
# Start Lernzentrum locally. Uses Docker if available, otherwise Python + Node directly (SQLite, demo mode).
set -euo pipefail
cd "$(dirname "$0")"
if command -v docker >/dev/null && docker info >/dev/null 2>&1; then
  exec docker compose up --build
fi
command -v python3 >/dev/null || { echo "Python 3.12+ fehlt"; exit 1; }
command -v npm >/dev/null || { echo "Node.js 22 fehlt"; exit 1; }
( cd backend && [ -d .venv ] || python3 -m venv .venv; . .venv/bin/activate && pip install -q -r requirements.txt )
( cd frontend && [ -d node_modules ] || npm ci --no-audit --no-fund )
( cd frontend && [ -d .next ] || npm run build )
( cd backend && . .venv/bin/activate && exec uvicorn app.main:app --host 127.0.0.1 --port 8000 ) &
API=$!
trap 'kill $API 2>/dev/null' EXIT
cd frontend && npx next start -p 3000 &
sleep 4 && (command -v xdg-open >/dev/null && xdg-open http://localhost:3000 || open http://localhost:3000 || true) >/dev/null 2>&1
wait
