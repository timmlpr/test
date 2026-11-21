# Einrichtung (Assistent, ca. 5 Minuten)

Der Assistent startet nach dem Anlegen deines Kontos. Jeder Schritt kann übersprungen und später unter
**Einstellungen** nachgeholt werden; der Stand wird gespeichert.

## 1 · Konto
E-Mail und Passwort (mind. 10 Zeichen, Groß-/Kleinbuchstaben, Zahl). Gespeichert wird nur ein Argon2id-Hash.
Optional: **Face ID / Passkey** einrichten – danach Anmeldung ohne Passwort.

## 2 · API-Keys (kostenlos)

| Key | Wofür | So bekommst du ihn |
|---|---|---|
| **Groq** | Spracherkennung (Whisper) – Live-Transkript und Import alter Sprachmemos | [console.groq.com/keys](https://console.groq.com/keys) → anmelden → „Create API Key“ → kopieren |
| **Google Gemini** | formulierte Antworten, Zusammenfassungen, Karteikarten, Handschrift-Erkennung | [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) → „Create API key“ → kopieren |

Key einfügen → **Speichern & testen** (echter Testaufruf, grün/rot). Der Key liegt danach verschlüsselt auf dem
Server und wird nie wieder vollständig angezeigt (nur `gsk_…1234`).

Ohne Keys funktioniert der Rest: ohne Groq kein Live-Transkript (Audio wird gespeichert und später transkribiert,
Fragen kannst du tippen); ohne Gemini werden Antworten **aus deinen Quellen zusammengestellt** (extraktiv) statt
formuliert – mit derselben Ampel und Fundstelle.

**Kostenlose Kontingente** (Stand 11/2026): Groq Whisper 20 Anfragen/Min., 2.000/Tag, 28.800 Audio-Sekunden/Tag.
Google veröffentlicht für Gemini keine festen Werte; beobachtet: Flash-Lite ≈ 15/Min. und 500/Tag, Flash ≈ 20/Tag.
Lernzentrum nutzt deshalb Flash-Lite für Live-Antworten, cacht, bündelt und zeigt den Verbrauch unter
Einstellungen → Kontingente (Grenzen dort anpassbar).

## 3 · Stundenplan
Abo-Link deines Stundenplans einfügen (`webcal://…` oder `https://….ics`), **Testen** zeigt die nächsten 3 Termine.
- iCloud-Kalender: Kalender-App → (i) neben dem Kalender → „Öffentlicher Kalender“ einschalten → Link teilen/kopieren.
- THM-Stundenplan: Abo-/Export-Link des Stundenplans kopieren.

Termine werden alle 30 Minuten abgeglichen und Modulen zugeordnet; unsichere Zuordnungen landen in der Prüfliste.

## 4 · Moodle
Adresse ist `https://moodle.thm.de` vorausgefüllt → **Prüfen**. Lernzentrum erkennt, welcher Weg funktioniert:
- **Benutzername + Passwort**: Das Passwort wird nur einmal an Moodle geschickt, um einen offiziellen
  App-Token zu erhalten, und sofort verworfen. Gespeichert wird nur der Token (verschlüsselt). Jederzeit trennbar.
- **Single Sign-on**: Link „Bei Moodle anmelden“ öffnen, dann auf der Seite „Sicherheitsschlüssel“ den Schlüssel
  „Moodle mobile web service“ kopieren und einfügen.
- **Fallback**: Moodle → Kalender → Kalender exportieren → Link kopieren (Termine/Fristen); Dateien per Eingang.

Synchronisiert werden Kursdateien (nur neue/geänderte), Termine/Abgaben und Ankündigungen – stündlich.

## 5 · Module
Aus dem Stundenplan erkannte Module per Tipp übernehmen oder eigene anlegen (Vorschläge für deine THM-Module sind
vorbereitet). Prüfungstermin, Farbe, Prüfungsmodus und Aufbewahrungsdauer später im Modul unter „Einstellungen“.

## 6 · Import (optional)
Alte Sprachmemos (m4a, mp3, wav) und Dateien hineinziehen – auch Hunderte. Lernzentrum liest Aufnahmedatum
(Metadaten, Dateiname, Änderungsdatum), ordnet per Stundenplan Modul und Vorlesung zu und transkribiert im
Rahmen des Kontingents im Hintergrund. Fortschritt: Eingang → Verarbeitung. Unsichere Zuordnungen → Prüfliste.

## Danach
- **Einstellungen → Verbindungen** zeigt grün/rot für Groq, Gemini, Kalender, Moodle, Speicher, OCR.
- **Einstellungen → Eingang**: Upload-Link für einen iOS-Kurzbefehl („An Lernzentrum senden“ im Teilen-Menü von
  GoodNotes, Dateien, Mail, Safari), E-Mail-Postfach (IMAP), Cloud-Ordner (WebDAV).
- **Einstellungen → Live-Modus**: wie dich der Dozent anspricht (damit direkte Fragen erkannt werden),
  Einwilligungs-Erinnerung, Antwortlänge.

**Kontext-Korrektur:** Gesprochene Gesetzeszitate werden automatisch korrigiert (z. B. „§433 WWW“ → „§ 433 BGB“); das Original bleibt erhalten. Abschalten: Einstellung `correction.enabled=false`.
