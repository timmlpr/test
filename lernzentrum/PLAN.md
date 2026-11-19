# Lernzentrum – Build Plan

Lernzentrum is an iPad-first PWA for a single student (THM, B.A. „Steuern und Rechnungswesen“). It listens in
lectures, transcribes live, detects questions with conversational context, shows grounded answers with a
3-level confidence scale, and doubles as a learning center (library, inbox, Moodle, timetable, learning aids).

Brand (name, tagline, colors) lives in one file: [`config/brand.json`](config/brand.json). Backend and frontend read it.

## 1. Architecture

```
                  ┌──────────────── Caddy (auto HTTPS, HSTS, CSP, gzip) ────────────────┐
 iPad / Browser ─►│ /api/* → backend:8000 (FastAPI, uvicorn)   /* → frontend:3000 (Next) │
                  └──────────────────────────────────────────────────────────────────────┘
 backend ─ SQLAlchemy ─ PostgreSQL (prod) | SQLite (dev, tests)
         ─ JobRunner (DB-backed queue, worker threads)  ─ ICS poll, Moodle sync, imports, embeddings, packages
         ─ Storage (AES-GCM encrypted files on disk / docker volume)
         ─ Providers: SttProvider (Groq Whisper | none), LlmProvider (Gemini | extractive fallback)
         ─ QuotaManager (per provider: RPM / RPD / audio-seconds, backoff, UI state)
         ─ Retrieval: chunker → BM25 + vectors (local hashed n-gram vectors always, Gemini embeddings optional)
         ─ Statutes: gesetze-im-internet.de fetcher + cache (the only external source)
```

* **frontend/** Next.js (App Router, TypeScript), Tailwind CSS, in-repo shadcn-style components, Recharts,
  PWA (manifest, hand-written service worker, offline shell, IndexedDB audio queue, Wake Lock), i18n dictionary (`de`).
* **backend/** FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, argon2-cffi, cryptography (AES-GCM), httpx,
  icalendar + recurring-ical-events, pypdf/pypdfium2, python-docx, python-pptx, pytesseract (+ Gemini vision for
  handwriting), ffmpeg for audio, numpy, rapidfuzz, webauthn (passkeys).
* Same-origin: the browser only talks to one origin. Dev: Next.js rewrites `/api/*` to `:8000`.
  Session = signed httpOnly cookie (`SameSite=Lax`, `Secure` in prod); CSRF = double-submit header `X-CSRF-Token`.

## 2. Deviations from the proposed stack (with reasons)

| Proposal | Decision | Reason |
|---|---|---|
| Celery/RQ + Redis | DB-backed job queue + worker threads inside the API process | Single user, one Hetzner server. Jobs survive restarts (rows in `jobs`), no extra container. `JobRunner` is an interface; RQ can replace it later. |
| pgvector | Vectors stored as float32 blobs, cosine in numpy, per-module scope | Works identically on SQLite and Postgres; a single user has ≤ ~50k chunks, numpy search is < 30 ms. Swap point: `retrieval/vector_store.py`. |
| MinIO / S3 | Encrypted local storage (`storage.py`, AES-GCM per file) on a Docker volume | One less service; files are encrypted at rest anyway. `Storage` interface keeps S3 open. |
| shadcn CLI | shadcn-style components written in-repo | CLI is interactive/network dependent; same ownership model. |
| Gemini embeddings as the only vectors | Local hashed char-n-gram vectors always + Gemini embeddings when key/quota allow | Free tier allows ~1000 embedding requests/day; demo and offline must still search semantically-ish. |
| Web Share Target on iPad | Implemented (Android/desktop Chromium) + iOS Shortcut upload link + e-mail intake + WebDAV folder sync | iOS Safari does **not** support `share_target`. iCloud has no public API; Google Drive/OneDrive need a registered OAuth app (owner decision) → WebDAV (Nextcloud etc.) is implemented, the others are documented as adapters. |
| Dedicated e-mail address | IMAP poller (any mailbox the user creates, e.g. `lernzentrum.xyz@gmx.de`) + raw-MIME webhook `/api/inbox/mail/{token}` | Running an MX server is out of scope for one user; both paths need no build-time key. |

## 3. Data model (`backend/app/models.py`)

All tables carry `user_id` (tenant-ready). Secrets/sensitive text columns use `EncryptedText` (AES-GCM).

* `User` (email, Argon2id hash, settings JSON, setup_step), `Passkey`, `Session` via signed cookie, `AuditLog`.
* `Secret` (provider, envelope-encrypted value, masked hint, status, checked_at).
* `Calendar` (url enc, name, last_sync, etag), `Event` (uid, start, end, title, location, description, module_id, match_score, lecture_id).
* `Module` (name, short, color, lecturer, exam_date, exam_mode, aliases, retention_days, lecturer_profile JSON).
* `Lecture` (module, start, end, title, event_id, source: calendar|manual|import).
* `Document` (module, lecture, kind: slides|script|exercise|notes|transcript|audio|photo|other, title, filename,
  storage_key, sha256, simhash, version_of, pages, status, text, doc_date, source: upload|share|mail|webdav|moodle|demo,
  confidence, needs_review), `Chunk` (document, module, page, start_s, end_s, text, local_vec, gemini_vec).
* `Recording` (module, lecture, started_at, consent_id, status, duration_s, exam_mode), `AudioChunk` (seq, storage_key,
  started_at, duration, transcribed, gap flag), `TranscriptSegment` (start_s, end_s, text, speaker, flags).
* `ConsentLog` (ts, module, recording, statement).
* `Answer` (recording, question, resolved_query, mode, candidates JSON, text, level, percent, why, sources JSON,
  correction JSON, status), `Participation`, `KeyMoment` (keyword alerts), `NumberFact`.
* `Statute` (law, norm, title, text, url, fetched_at, demo flag).
* Learning: `Flashcard` (SM-2 fields), `Quiz`/`QuizItem`, `MockExam`/`MockAttempt`, `GlossaryTerm`, `Summary`,
  `OpenQuestion`, `Task` (study plan), `StudySession` (stats), `Deadline`, `Announcement`, `InboxItem`, `MoodleLink`.
* `Job` (kind, payload, status, progress, error, attempts, run_after), `QuotaUsage` (provider, bucket, window, count).

## 4. API routes (prefix `/api`)

`auth/*` (register, login, logout, me, passkey register/login), `setup/*` (state, step), `secrets/*` (list masked, set,
test, delete), `health` (+ `health/connections`), `calendars/*` (CRUD, test, sync), `events/today`, `modules/*`
(CRUD, dashboard, lecturer-profile, exam-mode), `lectures/*`, `documents/*` (upload, list, get, file, reprocess,
confirm), `inbox/*` (items, confirm, share target, mail webhook, drop token, imap/webdav config), `search`,
`recordings/*` (start with consent, chunk upload, finish, events SSE, answer-now, hide state), `answers/*` (history,
feedback), `statutes/{law}/{norm}`, `statutes/find`, `imports/audio` (bulk), `review/*`, `moodle/*` (detect, token,
qr/launch token, ics fallback, sync, revoke), `learn/*` (package, flashcards due/review, quizzes, mock exams, radar,
gaps, contradictions, glossary, case practice, notes enhancer, study plan, stats), `quota`, `jobs`, `export`, `delete-all`.

## 5. Retrieval design

1. **Chunking** – per page (slides) or ~900-char windows with 150 overlap (scripts), transcript chunks of ~60 s.
   Each chunk keeps its *source location*: document + page, or recording + start/end seconds.
2. **Index** – BM25 (German-normalised tokens: lowercase, umlaut folding, light suffix stemming, stop words) and
   vectors (local 512-dim hashed char-3/4-grams; Gemini `gemini-embedding-001` if available).
3. **Query** – hybrid score = 0.55·BM25(normalised) + 0.45·cosine; statute references in the query boost chunks that
   cite the same norm (+0.15). Scope: current module (+ statutes). Top-k = 6.
4. **Statutes** – norms mentioned in question/context are fetched from `gesetze-im-internet.de/<law>/__<n>.html`
   and cached; they enter the evidence set as first-class sources.
5. **Grounding** – Gemini receives only the evidence passages with ids and must answer with `[S1]`-style citations
   in JSON. Without Gemini, an *extractive* answer is composed from the best evidence sentences.

## 6. Confidence scoring (`backend/app/live/confidence.py`)

Never model self-report alone. Inputs: retrieval top score `r` (0–1), citation coverage `c` (share of answer sentences
whose content tokens overlap ≥ 35 % with a cited passage), source agreement `a` (≥ 2 independent sources supporting,
or a statute that literally matches), statute match `s`, model self-rating `m` (weight ≤ 0.1), correction penalty.

`p = 100 · (0.35 r + 0.35 c + 0.12 a + 0.08 s + 0.10 m)`; no evidence ⇒ `p ≤ 15`, level UNSICHER, „keine Quelle“.
Levels: **SICHER ≥ 75**, **PRÜFEN 45–74**, **UNSICHER < 45**. The „why“ text is generated from the factors.

## 7. Live pipeline

Browser `MediaRecorder` restarts every 8 s → standalone segments (webm/opus or mp4/aac on iPad) → `POST
/recordings/{id}/chunks` (or IndexedDB queue when offline → gap marked, uploaded later). Backend: Groq Whisper
(`whisper-large-v3-turbo`, `language=de`, prompt seeded with module glossary) → transcript segments → analyzers:
question detector, context tracker (topic terms, current norm, examples, last 5 min, current slide), keyword alerts,
number keeper, slide matcher, statute quotes, correction watcher. Events go to the client via SSE.

## 8. iPad / PWA constraints

* Standalone display, `apple-touch-icon`, splash images, `viewport-fit=cover`, safe areas.
* No background recording in Safari: Wake Lock + visibility warnings; the recorder is foreground-only.
* `share_target` unsupported on iOS → iOS Shortcut upload URL, mail intake, in-app multi-file upload.
* Service worker: app shell + static assets cache; API never cached; audio queue in IndexedDB.
* Touch targets ≥ 44 px, landscape split view (answers top, transcript bottom), large-type & hide.

## 9. Free tiers (verified 2026-11, configurable in Settings → Kontingente)

* Groq `whisper-large-v3-turbo`: 20 RPM, 2,000 RPD, 7,200 audio s/h, 28,800 audio s/day (console.groq.com/docs/rate-limits).
* Gemini: Google no longer publishes free-tier numbers; observed values: Flash 5 RPM / 20 RPD, Flash-Lite 15 RPM /
  500 RPD, Embeddings 100 RPM / 1,000 RPD. ⇒ Live answers use Flash-Lite, bulk/learning jobs also Flash-Lite,
  Flash only on explicit „ausführlich“ requests; heavy caching; extractive fallback when exhausted.

## 10. Milestones

M1 skeleton/design/PWA/auth/wizard/demo · M2 modules + ICS · M3 inbox & library · M4 audio pipeline & bulk import ·
M5 retrieval & statutes · M6 live core · M7 live extras · M8 Moodle · M9 package/flashcards/quiz/mock/radar/gaps ·
M10 glossary/statute finder/case practice/notes/profile/history · M11 dashboard/plan/stats/health · M12 hardening & deploy.
Each milestone: code + tests + commit.

## 11. Addendum – Kontext-Korrektur (transcript correction)

Package `backend/app/correction/`: `phonetic.py` (Kölner Phonetik, German letter names, number words),
`lexicon.py` (curated law abbreviations + section ranges, subject areas, official list from gesetze-im-internet.de
`gii-toc.xml`, exact section sets from loaded laws), `confusions.json` (data-driven ASR confusion table),
`engine.py` (layers 2 + 3 + 5: citation grammar, candidates, existence check, context scoring, policy – pure,
no DB, < 300 ms), `service.py` (DB integration: context, learned rules, segment storage, user actions,
LLM adjudicator job = layer 4, batch re-correction job, Whisper vocabulary prompt = layer 1).
Data: `transcript_segments.original_text` (immutable) + `edits` JSON + `correction_conf/status`; `text` = corrected
(so retrieval, questions, answers, statute quotes, slide matching consume corrected text); `chunks.alt_text`
indexes the original as well; `correction_rules` table (user rules, vocabulary, learned confusion weights,
module-scoped or global). Policy: ≥ auto (90) applied, ≥ mark (60) applied + marked, below → unclear, not applied.
Deviation: Groq's Whisper endpoint has no hotword parameter → layer 1 uses the `prompt` parameter only.
