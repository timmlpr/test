# Lösch- und Aufbewahrungskonzept – Entwurf

> **ENTWURF – vor Veröffentlichung anwaltlich prüfen lassen.** Platzhalter in eckigen Klammern sind zu ersetzen (zentral in `config/brand.json`).

| Datenart | Regel | Umsetzung |
|---|---|---|
| Konto und alle Inhalte | sofort bei Konto-Löschung | `DELETE /api/profile` (purge aller Tabellen inkl. Uploads) |
| Funde im Papierkorb | 30 Tage | täglicher Job `retention` |
| Unbestätigte Wartelisten-Einträge | 7 Tage | `retention` |
| Einmal-Tokens (Links, Codes) | bei Ablauf | `retention` |
| KI-Antwort-Cache | 30 Tage | `retention` |
| Benachrichtigungen | 180 Tage | `retention` |
| Audit-Log (ohne Klartext) | 365 Tage | `retention` |
| Bild-Uploads | nicht gespeichert | Verarbeitung im Arbeitsspeicher |
| Sonstige Uploads | 24 Stunden | `Upload.expires_at` + `retention` |
| Rechnungsdaten (bei Stripe) | 10 Jahre | gesetzliche Pflicht (AO/HGB) |
| Backups | 30 Tage rotierend, verschlüsselt | `deploy/backup.sh` |

Konto-Löschung im Backup: Backups werden nicht selektiv bereinigt; gelöschte Daten verschwinden spätestens mit der Rotation nach 30 Tagen. Bei einer Wiederherstellung werden zwischenzeitliche Löschungen anhand des Audit-Logs („profile.account_deleted“ ohne Personenbezug → Löschliste mit Konto-IDs separat führen) erneut ausgeführt.
