# Datenschutz-Folgenabschätzung (DSFA) – Entwurf

> **ENTWURF – vor Veröffentlichung anwaltlich prüfen lassen.** Platzhalter in eckigen Klammern sind zu ersetzen (zentral in `config/brand.json`).

## 1. Beschreibung
{{brand}} verarbeitet eigene Identifikatoren von Nutzenden (Name, E-Mail, Telefon, Wohnort, Benutzernamen, Domains) und gleicht sie mit öffentlichen Quellen und Leck-Datenbanken ab. Die Verarbeitung ist umfangreich, betrifft potenziell sensible Kombinationen und nutzt neue Technologien (optional KI) → DSFA nach Art. 35 Abs. 1 DSGVO angezeigt (Prüfung: DSK-Muss-Liste, Nr. „Scoring“ und „umfangreiche Verarbeitung“).

## 2. Notwendigkeit und Verhältnismäßigkeit
- Zweck: Betroffene sollen eigene Exposition erkennen und reduzieren (Stärkung von Art. 15–17).
- Datenminimierung: nur eigene, bestätigte Angaben; Bilder nur im Arbeitsspeicher; Mail-Export nur Metadaten; Passwörter k-anonym.
- Speicherbegrenzung: siehe Löschkonzept.

## 3. Risiken für Rechte und Freiheiten
| Risiko | Eintritt | Schwere | Maßnahmen | Restrisiko |
|---|---|---|---|---|
| Missbrauch zur Ausforschung Dritter | mittel | hoch | Eigentumsnachweis je Identifikator, keine Freitextsuche, Anomalie-Sperre, Guard im Assistenten, Missbrauchsmeldung, Audit | niedrig |
| Fehlzuordnung namensgleicher Personen | hoch | mittel | Kennzeichnung „nicht sicher zuordenbar“, keine automatische Bewertung als eigener Fund | niedrig |
| Datenpanne beim Anbieter | niedrig | hoch | Feldverschlüsselung, TLS, 2FA Admin, Backups verschlüsselt, Logs ohne Klartext | niedrig |
| Übermittlung an KI-Anbieter | mittel | mittel | Opt-in, Anonymisierung, Tageslimits, Hinweis | niedrig |
| Kinderdaten | niedrig | hoch | nur über Elternkonto mit Einwilligung | niedrig |
| Score als Angstmacher | mittel | niedrig | transparente Regeln, ruhige Sprache, kein Countdown | niedrig |

## 4. Ergebnis
Mit den Maßnahmen ist das Restrisiko vertretbar. Überprüfung bei jeder neuen Datenquelle oder Funktion.
