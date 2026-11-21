# Architektur

Siehe auch [PLAN.md](PLAN.md) (Entscheidungen und Abweichungen vom vorgeschlagenen Stack).

```
 iPad (PWA) ──HTTPS──► Caddy ──/api/*──► FastAPI (uvicorn) ──► PostgreSQL
                         └────/*──────► Next.js (standalone)      └─► /data (AES-GCM-verschlüsselte Dateien)
 FastAPI-Prozess: JobRunner-Threads (Transkription, Import, Moodle, ICS, Nachbereitung, Gesetze laden)
 Externe Aufrufe: Groq (Audio→Text), Gemini (Text, Bilder→Text, Embeddings), gesetze-im-internet.de, Moodle, ICS-URLs
```

## Live-Modus – Datenfluss
1. **Aufnahme** (`frontend/src/lib/recorder.ts`): MediaRecorder startet alle 8 s neu → eigenständige Audiodateien
   (Safari: mp4/aac, Chromium: webm/opus). Upload `POST /api/recordings/{id}/chunks`. Offline → IndexedDB, später
   Upload mit `late=true`; der Server markiert die Lücke und transkribiert nachträglich. Wake Lock hält den
   Bildschirm an; Sichtbarkeitswechsel lösen eine Warnung aus (Safari nimmt im Hintergrund nicht auf).
2. **Transkription** (`app/live/pipeline.py`, Job `live.chunk`): Groq Whisper `whisper-large-v3-turbo`, Sprache `de`,
   Prompt mit Modulbegriffen. Kontingent wird vorher reserviert (`app/quota.py`), 429 → Job pausiert bis Reset.
3. **Analysen pro Segment**: Kontext (`live/context.py`: letzte 5 min, zuletzt genannte Norm + Gesetz, Themenbegriffe,
   Beispiele, aktuelle Folie) · Klausur-Signalwörter · Zahlen/Fristen · Normzitate (Wortlaut) · Folien-Matching ·
   Korrektur-Wächter · Fragenerkennung (`live/questions.py`) · Fragevorschläge (alle 2 min).
4. **Antwort** (`live/answer.py`): Frage wird mit Kontext aufgelöst (Anschlussfragen, Pronomen, Norm ohne Gesetz) →
   Belege = Normen aus Frage/Kontext + hybride Suche im Modulmaterial → Gemini antwortet **nur** aus nummerierten
   Belegen (JSON mit Lesarten, Zitaten, Stützungsgrad) bzw. extraktive Antwort ohne Key → **Konfidenz** aus Belegen.
5. **Events** werden in `live_events` gespeichert und per SSE (`/stream`) mit Polling-Fallback ausgeliefert;
   nach Verbindungsabbruch wird ab der letzten Event-ID fortgesetzt.
6. **Ende**: Transkript wird als Dokument indexiert, Dozentenprofil aktualisiert, Job `learn.package` erzeugt
   Zusammenfassung, Karteikarten, offene Fragen, klausurrelevante Stellen, Fachbegriffe.

## Konfidenz (`app/live/confidence.py`)
`p = 100·(0,30·Treffergüte + 0,25·Aussagen-Abdeckung + 0,20·Fragen-Abdeckung + 0,10·unabhängige Quellen +
0,08·Normtreffer + 0,07·Modell-Selbsteinschätzung)`, danach Deckel: Frage kaum abgedeckt ≤ 70, Quellen
widersprechen sich ≤ 60, Antwort überwiegend ungedeckt ≤ 60, Modell „teilweise“ ≤ 74 / „keine Stütze“ ≤ 40,
vom Dozenten korrigiert ≤ 30. Ohne Beleg: ≤ 15 % „keine Quelle“. Stufen: SICHER ≥ 75, PRÜFEN 45–74, UNSICHER < 45.

## Retrieval (`app/retrieval/index.py`)
Chunks mit Fundstelle (Seite/Folie oder Sekunden). Index pro Nutzer/Modul im Speicher (entschlüsselt beim ersten
Zugriff, invalidiert bei Änderungen). Score = 0,55·BM25 (deutsche Normalisierung, Stammformen, Präfixe für
Komposita) + 0,45·Kosinus (lokale Hash-Vektoren; Gemini-Embeddings wenn verfügbar), gedämpft nach Begriffsabdeckung,
+0,15 für passende Normzitate.

## Datenmodell
`app/models.py` – alle Nutzerdaten mit `user_id` (mandantenfähig). Migrationen: `backend/migrations` (Alembic);
CI prüft `alembic check` (Schema = Modelle).

## Hintergrundjobs (`app/jobs.py`)
DB-Tabelle `jobs`, 2 Worker-Threads, periodische Aufgaben (ICS 30 min, Moodle 60 min, Eingang 15 min,
Aufbewahrung 6 h). Quoten-Fehler → Status „pausiert“ bis zum Reset; andere Fehler → exponentielles Backoff (4 Versuche).

## Deployment
`deploy/docker-compose.prod.yml`: `db` (PostgreSQL 16), `backend`, `frontend`, `caddy` (Let's Encrypt, HSTS, CSP,
SSE ungepuffert), `backup` (täglich `pg_dump` + Dateiablage → AES-256-verschlüsselt, 14 Tage, anschließend
automatischer **Restore-Test** in eine Wegwerf-Datenbank). Server: Hetzner Cloud, Standort Nürnberg/Falkenstein
(`deploy/hetzner-setup.sh`, optional `deploy/hcloud-create.sh` mit API-Token). Empfohlen zusätzlich: Hetzner-Volume
mit LUKS für `/var/lib/docker/volumes` und Storage Box als Off-site-Ziel für `deploy/backups`.

## iPad-/PWA-Grenzen (bewusst behandelt)
- Kein Aufnehmen im Hintergrund/bei gesperrtem Bildschirm → Wake Lock + Warnung, App im Vordergrund lassen.
- Kein Web-Share-Target in Safari → iOS-Kurzbefehl mit persönlichem Upload-Link, E-Mail-Eingang, Mehrfach-Upload.
- Keine zuverlässige Offline-Spracherkennung im Browser → offline aufnehmen, später transkribieren.
- Wake Lock in installierten iPad-Web-Apps erst ab neueren iPadOS-Versionen → Hinweis „Automatische Sperre: Nie“.

## Transcript correction (Kontext-Korrektur)
`backend/app/correction/`: every transcript segment runs through `engine.correct()` before analysis.
Layer 1: module vocabulary prompt for Whisper (`pipeline._whisper_prompt`, ≤ 600 chars; Groq has no hotwords).
Layer 2: citation grammar (§/Paragraph + number/number words + Abs./S./Nr./lit./Alt./Hs. + law slot), law lexicon with
section ranges (`lexicon.py`, exact norms if a law is loaded), spelled letters ("Be Ge Be", "E S T G"), confusion table
(`confusions.json`), Kölner Phonetik/edit distance. Layer 3: scoring by section existence, module subject, laws
mentioned in the lecture, citations in the module materials, user rules. Layer 5: ≥ 90 applied, ≥ 60 applied + marked,
below → "unclear", not applied. `transcript_segments.original_text` is never modified; `edits` hold span, from, to,
reason, confidence, status. API: `POST /api/segments/{id}/edits/{edit}` (accept/undo/redo/choose/always → module rule).
Layer 4 (`correction/service.py`): only segments with "check"/"unclear" edits go to Gemini (job `correction.llm`,
cached, quota-aware, skipped with a notice without key); the answer may only pick one of the listed candidates and
may change at most the candidate spans + `max_edit_ratio` of the text – otherwise it is discarded.
Learning loop: accept/undo adjust per-module confusion weights; "immer so korrigieren" creates a module (or global)
rule; own vocabulary feeds the merge rule and the Whisper prompt. `chunks.alt_text` keeps the original wording
searchable. Batch: `POST /api/correction/modules/{id}/recorrect` (job with progress, keeps user decisions, idempotent).
Live answers get the original wording in the prompt when a correction in the question is below the auto threshold.
