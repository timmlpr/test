# Adapter & Erweiterungspunkte

| Schnittstelle | Datei | Implementiert | Austausch |
|---|---|---|---|
| `SttProvider` | `backend/app/providers/base.py` | `GroqStt` (Whisper large-v3-turbo) | Klasse mit `transcribe()`/`test()` schreiben, in `registry.stt_for()` wählen |
| `LlmProvider` | `backend/app/providers/base.py` | `GeminiLlm` (generate, vision_ocr, embed) | analog, in `registry.llm_for()` |
| Kein LLM | `backend/app/live/answer.py` | extraktive Antworten aus Belegen | – |
| Jobs | `backend/app/jobs.py` | DB-Queue + Threads | `enqueue()`/`@handler` auf RQ/Celery umbiegen |
| Speicher | `backend/app/storage.py` | verschlüsselte Dateien lokal | `Storage`-Klasse für S3 (put/get/delete) |
| Vektoren | `backend/app/retrieval/index.py` | numpy (lokal + Gemini) | pgvector: `_ModuleIndex` durch SQL-Abfrage ersetzen |
| Gesetze | `backend/app/statutes.py` | gesetze-im-internet.de (Einzelnorm-HTML, Gesetz-XML) | einzige externe Quelle |
| Kalender | `backend/app/calendar_sync.py` | ICS/webcal (mehrere Kalender) | – |
| Moodle | `backend/app/moodle.py` | Web-Service-Token, SSO-Token, ICS-Fallback | – |
| Eingang | `backend/app/ingest/channels.py` | Upload, Kurzbefehl-Link, IMAP, MIME-Webhook, WebDAV | siehe unten |

## Modelle & Kontingente
Standardmodelle (`app/config.py`): `whisper-large-v3-turbo`, `gemini-flash-lite-latest` (Live/Bulk),
`gemini-flash-latest` (ausführlich), `gemini-embedding-001`. Pro Nutzer überschreibbar
(`PATCH /api/settings {"models": {...}, "quotas": {...}}`). Quotenzähler in `quota_usage`.

## Nicht gebaut (bewusst) und warum
- **iCloud Drive**: keine öffentliche API für Web-Apps. Alternative: Teilen-Kurzbefehl oder WebDAV-Ordner.
- **Google Drive / OneDrive**: brauchen eine registrierte OAuth-App (Client-ID, Verifizierung) – Entscheidung der
  Betreiberin. Adapter-Muster: `webdav_sync()` in `ingest/channels.py` (Liste mit ETag → `intake()`).
- **Eigener Mailserver**: stattdessen IMAP-Abruf eines beliebigen Postfachs oder Webhook
  `POST /api/inbox/mail/{token}` (Roh-MIME, z. B. von einem Mail-Weiterleitungsdienst).
- **Offline-Spracherkennung im Browser**: auf dem iPad nicht verlässlich → offline aufnehmen, später transkribieren.
- **Teilen-/Mehrbenutzer-Funktionen**: nicht gebaut; Datenmodell ist mandantenfähig (`user_id` überall).
