# Verzeichnis von Verarbeitungstätigkeiten (Entwurf, Art. 30 DSGVO)

> **ENTWURF – vor Veröffentlichung anwaltlich prüfen lassen.** Platzhalter in eckigen Klammern sind zu ersetzen (zentral in `config/brand.json`).

| Nr. | Tätigkeit | Zweck | Kategorien Betroffene | Datenkategorien | Empfänger | Drittland | Löschfrist | TOM |
|---|---|---|---|---|---|---|---|---|
| 1 | Kontoverwaltung | Vertragserfüllung | Kund:innen | Stammdaten, Login | Hetzner | nein | Konto-Löschung | Verschlüsselung, Argon2id, 2FA |
| 2 | Privatsphäre-Scan | Auffindbarkeit eigener Daten | Kund:innen | eigene Identifikatoren, Funde | Quellen-APIs (nur Suchbegriff) | je Quelle | durch Nutzer | Eigentumsnachweis, Rate-Limit |
| 3 | Leck-Check | Datenlecks prüfen | Kund:innen | E-Mail | XposedOrNot | ja (prüfen) | durch Nutzer | nur bestätigte Adressen |
| 4 | Lösch-Anfragen | Betroffenenrechte unterstützen | Kund:innen | Anfrage-Texte | – | nein | durch Nutzer | Verschlüsselung |
| 5 | Zahlungen | Abrechnung | Kund:innen | Tarif, Stripe-IDs | Stripe | ja (SCC/DPF) | 10 Jahre | Webhook-Signaturen |
| 6 | Monitoring/Benachrichtigung | Hinweise auf neue Funde | Kund:innen | Funde, Push-Endpunkt | E-Mail-Dienst, Push-Dienste der Browser | ja (Push) | 180 Tage (Hinweise) | Ruhezeiten, Schweregrad |
| 7 | Warteliste | Information zum Start | Interessent:innen | E-Mail | E-Mail-Dienst | nein | Widerruf / 7 Tage unbestätigt | DOI |
| 8 | Missbrauchsabwehr | Schutz Dritter | Nutzer:innen | Audit-Log (ohne Klartext), IP-Hash (Tagessalz) | – | nein | 365 Tage | Pseudonymisierung |
| 9 | KI-Assistent (optional) | Erklärungen | Kund:innen | anonymisierter Text | KI-Anbieter | ja | Cache 30 Tage | Anonymisierung, Limits |
| 10 | Digitaler Nachlass | Vorsorge | Kund:innen, Vertrauensperson | Chiffrat, E-Mail Vertrauensperson | – | nein | durch Nutzer | E2E-Verschlüsselung |
