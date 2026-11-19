# Datenschutzerklärung

> **ENTWURF – vor Veröffentlichung anwaltlich prüfen lassen.** Platzhalter in eckigen Klammern sind zu ersetzen (zentral in `config/brand.json`).

Stand: [DATUM]

## 1. Verantwortlicher
{{company}}, {{street}}, {{city}}, E-Mail: {{email}}.
Datenschutzbeauftragte:r: [NAME/KONTAKT oder „nicht benannt, da nicht erforderlich“ – siehe LAUNCH_CHECKLIST].

## 2. Grundsätze
{{brand}} verarbeitet nur die Daten, die für die Funktionen nötig sind (Datenminimierung, Art. 5 Abs. 1 lit. c DSGVO). Sensible Angaben werden verschlüsselt gespeichert (AES-256-GCM). Server stehen in Deutschland. Gesucht wird ausschließlich nach den eigenen, bestätigten Angaben der Nutzerinnen und Nutzer.

## 3. Welche Daten wir verarbeiten
| Zweck | Daten | Rechtsgrundlage | Speicherdauer |
|---|---|---|---|
| Konto | E-Mail, Passwort-Hash (Argon2id), Anzeigename, Einstellungen | Art. 6 Abs. 1 lit. b | bis Konto-Löschung |
| Eigenes Profil & Scans | Namen, E-Mails, Telefonnummern, Wohnort, Benutzernamen, Domains (verschlüsselt), Funde | Art. 6 Abs. 1 lit. b | bis Löschung durch dich |
| Nachweis eigener Daten | Zeitstempel der Bestätigung, gekürzter IP-Hash | Art. 6 Abs. 1 lit. c, f (Missbrauchsschutz) | 3 Jahre |
| Lösch-Anfragen & Fristen | Empfänger, Text, Status | Art. 6 Abs. 1 lit. b | bis Löschung durch dich |
| Bezahlung | Tarif, Stripe-Kunden-ID, Rechnungsdaten bei Stripe | Art. 6 Abs. 1 lit. b, c | 10 Jahre (§ 147 AO, § 257 HGB) |
| Sicherheit | Audit-Log ohne Klartext-Personendaten, Rate-Limits | Art. 6 Abs. 1 lit. f | 365 Tage |
| Warteliste | E-Mail (Double-Opt-in) | Art. 6 Abs. 1 lit. a | bis Widerruf; unbestätigt 7 Tage |
| Bild-Check | Bild nur im Arbeitsspeicher | Art. 6 Abs. 1 lit. b | keine Speicherung |
| Abo-Wächter | Absender, Kategorie, Betrag, Abmelde-Link (keine Inhalte); bei Gmail-Verbindung zusätzlich verschlüsseltes Zugriffstoken | Art. 6 Abs. 1 lit. b, a | bis Löschung/Trennung durch dich |
| Dokumenten-Scanner | erkannter Text, Fristen (verschlüsselt) | Art. 6 Abs. 1 lit. b | bis Löschung durch dich |
| Digitaler Nachlass | nur verschlüsselter Inhalt (Schlüssel bei dir), E-Mail der Vertrauensperson | Art. 6 Abs. 1 lit. b | bis Löschung durch dich |
| KI-Assistent (optional) | anonymisierter Text | Art. 6 Abs. 1 lit. a/b | Antwort-Cache 30 Tage |

## 4. Abfragen bei externen Quellen
Für Scans fragen wir öffentliche Schnittstellen ab (z. B. XposedOrNot für Datenlecks, Wikipedia, RDAP, DNS). Dabei übermitteln wir nur die jeweils nötige Angabe (z. B. deine E-Mail-Adresse an den Leck-Dienst). Beim Passwort-Check verlassen nur die ersten 5 Zeichen eines SHA-1-Hashwerts deinen Browser (k-Anonymität).

## 5. KI-Anbieter
Nur wenn aktiviert: Texte werden vor dem Versand anonymisiert (Namen, Adressen, Telefonnummern, E-Mails werden durch Platzhalter ersetzt). Kostenlose Tarife mancher Anbieter (z. B. Google Gemini) können Eingaben zur Produktverbesserung nutzen. Bilder mit Gesichtern werden nie an KI-Dienste gesendet.

## 6. Auftragsverarbeiter und Empfänger
| Dienstleister | Zweck | Ort | Garantie |
|---|---|---|---|
| Hetzner Online GmbH | Hosting | Deutschland | AVV nach Art. 28 |
| Stripe Payments Europe Ltd. | Zahlungen | Irland/EU (+ USA) | AVV, EU-US Data Privacy Framework / SCC |
| [E-Mail-Versanddienst] | Transaktions-Mails | [EU] | AVV |
| Google (Gemini API), optional | KI-Antworten (anonymisiert) | USA/EU | AVV/SCC – prüfen |
| Anthropic (Claude API), optional | KI-Antworten (anonymisiert) | USA | AVV/SCC – prüfen |
| seven communications GmbH & Co. KG (seven.io), optional | SMS-Code zur Bestätigung der eigenen Telefonnummer | Deutschland | AVV |
| Google (Gmail API), nur bei Verbindung durch dich | Lesen von E-Mail-Kopfzeilen für den Abo-Wächter (kein Inhalt) | USA/EU | AVV/SCC, Widerruf jederzeit – prüfen |
| Google Safe Browsing / abuse.ch, optional | Link-Prüfung (nur URL) | USA/Schweiz | Angemessenheitsbeschluss (CH) / SCC – prüfen |

## 7. Cookies
Wir setzen nur technisch notwendige Cookies: Sitzungs-Cookie (Anmeldung, httpOnly) und Sicherheits-Cookie (CSRF-Schutz). Es gibt kein Tracking und keine Werbe-Cookies (§ 25 Abs. 2 TDDDG). Sollten wir später Statistik einsetzen, fragen wir vorher um Einwilligung.

## 8. Deine Rechte
Auskunft (Art. 15), Berichtigung (Art. 16), Löschung (Art. 17 – in der App mit einem Klick), Einschränkung (Art. 18), Datenübertragbarkeit (Art. 20 – Export in der App), Widerspruch (Art. 21), Widerruf von Einwilligungen (Art. 7 Abs. 3), Beschwerde bei einer Aufsichtsbehörde (Art. 77).

## 9. Minderjährige
Kinder unter 16 Jahren können nur über ein Familienkonto mit Zustimmung eines Elternteils angelegt werden (Art. 8 DSGVO).

## 10. Sicherheit
TLS-Verschlüsselung, Verschlüsselung sensibler Felder, Argon2id-Passwort-Hashes, optionale Zwei-Faktor-Anmeldung und Passkeys, verschlüsselte Backups, Protokolle ohne Klartext-Personendaten.

---

## Anhang A – Entwurf Verzeichnis von Verarbeitungstätigkeiten (Art. 30)
Siehe `legal/verarbeitungsverzeichnis.md`.
