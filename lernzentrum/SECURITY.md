# Sicherheit & Datenschutz

## Geheimnisse
- **Keine Keys im Code oder Build.** Groq/Gemini-Keys, Moodle-Token, IMAP-/WebDAV-App-Passwörter gibt der Nutzer in
  der App ein. Speicherung per **Envelope-Encryption**: zufälliger Datenschlüssel (AES-256-GCM) je Geheimnis,
  dieser mit einem aus `LZ_MASTER_KEY` abgeleiteten Schlüssel (HKDF) umhüllt; Kontext `user:<id>:<provider>`
  als AAD gebunden (`app/crypto.py`). Die API gibt nur maskierte Hinweise (`gsk_…1234`) zurück.
- **Moodle-Passwort** wird ausschließlich für `login/token.php` verwendet, nie gespeichert oder geloggt.
- `LZ_MASTER_KEY`, `LZ_SESSION_SECRET` nur als Umgebungsvariablen (Produktion: Start bricht ohne sie ab).

## Daten im Ruhezustand
- Dateien (Folien, Audio, Fotos) AES-256-GCM-verschlüsselt im Dateispeicher (`app/storage.py`).
- Sensible Spalten (Dokumenttext, Chunks, Transkripte, Fragen/Antworten, Kalender-URLs) als `EncryptedText`.
- Backups zusätzlich AES-256 (PBKDF2, 200k Iterationen) mit eigener Passphrase; täglicher Restore-Test.
- Empfehlung Hetzner: Volume mit LUKS-Verschlüsselung für die Docker-Volumes.

## Transport & Web
- TLS über Caddy (Let's Encrypt), HSTS, CSP, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`
  (Mikrofon nur same-origin), kein `Server`-Header.
- Sitzung: signiertes, httpOnly-Cookie (`SameSite=Lax`, `Secure` in Produktion), 30 Tage.
- CSRF: Double-Submit-Token (`lz_csrf`-Cookie + `X-CSRF-Token`-Header) für alle ändernden Anfragen.
- Rate-Limits: Login 10/5 min, Registrierung 5/h, Passkey 20/5 min, Moodle-Login 6/10 min, Upload-Link 60/h.
- Passwörter: Argon2id (time 3, 64 MiB). Passkeys (WebAuthn) optional.
- Einzelnutzer: Registrierung schließt sich nach dem ersten Konto.
- Audit-Log: Anmeldungen, Schlüsseländerungen, Moodle-Verbindung, Aufnahmen, Export (ohne Geheimnisse).

## Datenschutz (DSGVO)
- Datenminimierung: an Groq gehen nur Audioabschnitte, an Gemini nur die nötigen Textausschnitte (Belege, Frage,
  kurzer Kontext). Keine Analyse-/Tracking-Dienste, keine externen Schriftarten oder CDNs.
- Aufbewahrung: Audio pro Modul automatisch löschbar (Tage einstellbar), „Audio speichern“ global abschaltbar.
- **Export** aller Daten (ZIP) und **Alles löschen** (Passwort + Bestätigung) in den Einstellungen.
- Einwilligung: vor jeder Aufnahme Bestätigung, dass Lehrperson und Anwesende zustimmen; protokolliert
  (Zeitpunkt, Modul, Text). Hinweis auf § 201 StGB (Vertraulichkeit des Wortes).
- **Prüfungsschutz**: Prüfungsmodus pro Modul schaltet Live-Antworten serverseitig ab (auch manuelle Fragen);
  App weist darauf hin, dass sie in Prüfungen nicht benutzt werden darf.
- Hinweis Gemini Free Tier: Google kann Eingaben im kostenlosen Kontingent zur Produktverbesserung nutzen.
  Für sensible Inhalte bezahlten Tarif verwenden oder ohne Gemini (extraktiv) arbeiten.

## Meldung von Schwachstellen
Private App – Hinweise bitte direkt an die Betreiberin/den Betreiber.
