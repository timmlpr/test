# Lernzentrum – „Zuhören. Verstehen. Bestehen.“

iPad-first Lern-App (installierbare PWA) für das Studium **Steuern und Rechnungswesen (THM)**: hört in der Vorlesung zu,
transkribiert live, erkennt Fragen samt Gesprächskontext und zeigt belegte Antworten mit Ampel
(**SICHER / PRÜFEN / UNSICHER** + Prozent + Fundstelle). Dazu: Lernzentrum pro Modul, eigener Eingang,
Moodle- und Stundenplan-Anbindung, Karteikarten, Probeklausuren, Gesetzesfinder, Fallübungen im Gutachtenstil.

Name, Slogan und Farben stehen zentral in [`config/brand.json`](config/brand.json).

## Starten – ein Befehl

| Wo | Befehl | Adresse |
|---|---|---|
| Docker (kompletter Stack: PostgreSQL + API + Web) | `docker compose up --build` | http://localhost:3000 |
| Windows | Doppelklick auf **`start.bat`** (Docker Desktop, sonst Python/Node automatisch via winget) | http://localhost:3000 |
| macOS / Linux | `./start.sh` | http://localhost:3000 |

**Demo-Modus** ist lokal an – keine Keys nötig. Auf der Login-Seite „Demo öffnen“ oder
`demo@lernzentrum.app` / `Lernzentrum2026`. Die Demo enthält 5 THM-Module, Stundenplan (eine Vorlesung läuft
„gerade“), Folien als PDF, eine ausgewertete Vorlesung mit Antworten, Karteikarten, Glossar, Fristen,
Ankündigungen und einen Prüfeintrag im Eingang. Im Live-Modus spielt **„Demo-Vorlesung abspielen“** eine
Buchführungs-Vorlesung ein – inklusive Anschlussfrage, Klausurhinweis, Zahlen und einer Korrektur durch den Dozenten.

Für dein eigenes Konto: **Neues Konto erstellen** → Einrichtungsassistent (siehe [SETUP_GUIDE.md](SETUP_GUIDE.md)).

## Online (Hetzner, Deutschland)

```bash
# auf einem frischen Ubuntu-24.04-Server von Hetzner (Standort Nürnberg/Falkenstein), Domain zeigt auf die IP:
curl -fsSL <raw-url>/lernzentrum/deploy/hetzner-setup.sh | sudo LZ_DOMAIN=lernen.deine-domain.de REPO=<git-url> bash
```
Das Skript installiert Docker + Firewall, erzeugt zufällige Schlüssel (`deploy/.env`), startet PostgreSQL, API, Web,
**Caddy mit automatischem HTTPS** und den **täglichen verschlüsselten Backup-Job inkl. Restore-Test**.
Health-Check: `https://<domain>/api/health`. CI/CD: [`.github/workflows/lernzentrum.yml`](../.github/workflows/lernzentrum.yml)
(Tests auf SQLite und PostgreSQL, Build, Docker; Deploy per SSH sobald `DEPLOY_HOST`/`DEPLOY_SSH_KEY` gesetzt sind).
Details: [ARCHITECTURE.md](ARCHITECTURE.md#deployment).

**Aufs iPad:** Seite in Safari öffnen → Teilen → „Zum Home-Bildschirm“. Startet im Vollbild mit eigenem Icon und Splash.

## Entwicklung & Tests

```bash
cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
uvicorn app.main:app --reload            # API :8000 (SQLite, Demo-Daten)
python -m pytest                          # 58 Tests (Unit, API, Moodle-Mocks, Quoten, Prüfungsmodus …)
LZ_TEST_DATABASE_URL=postgresql+psycopg://… python -m pytest   # dieselben Tests gegen PostgreSQL
cd ../frontend && npm ci && npm run dev   # Web :3000 (leitet /api an :8000 weiter)
npm run e2e                               # Playwright: alle Bildschirme in iPad quer/hoch, Desktop, iPhone
```

## Ordner

```
config/     brand.json (Name, Slogan, Farben – einzige Quelle)
backend/    FastAPI · app/live (Fragen, Kontext, Konfidenz, Antworten, Analysen) · app/retrieval · app/ingest
            app/learn · app/providers (Groq, Gemini) · moodle.py · calendar_sync.py · statutes.py · tests/
frontend/   Next.js PWA · src/app (Seiten) · src/components · src/lib (API, Recorder, Passkey) · e2e/
deploy/     docker-compose.prod.yml · Caddyfile · backup.sh · restore-test.sh · hetzner-setup.sh · hcloud-create.sh
```

Weitere Dokumente: [PLAN.md](PLAN.md) · [SETUP_GUIDE.md](SETUP_GUIDE.md) · [ARCHITECTURE.md](ARCHITECTURE.md) ·
[SECURITY.md](SECURITY.md) · [ADAPTERS.md](ADAPTERS.md)

## Changelog
- 2026-11: Kontext-Korrektur (Regel- und Kontextschichten, Rückgängig, eigene Regeln). UI-Marker mit Popover und „Original anzeigen“. Offen: Gemini-Schiedsrichter, Batch-Neukorrektur, Eval-Set.
