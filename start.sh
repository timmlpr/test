#!/usr/bin/env sh
# Start Fadeprint locally. Uses Docker if available, otherwise Python + Node directly.
set -e
cd "$(dirname "$0")"
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  docker compose up --build -d && echo "Fadeprint läuft: http://localhost:3000  (Demo: demo@demo.example.com / FadeprintDemo1!)"
  exit 0
fi
python3 -m venv backend/.venv && backend/.venv/bin/pip install -q -r backend/requirements.txt
(cd backend && DEMO_MODE=true .venv/bin/uvicorn app.main:app --port 8000 &) 
(cd frontend && npm install --no-audit --no-fund && npm run build && npx next start -p 3000 &)
echo "Fadeprint startet: http://localhost:3000  (Demo: demo@demo.example.com / FadeprintDemo1!)"
wait
