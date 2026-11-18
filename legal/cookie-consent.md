# Cookie- und Consent-Konzept

> **ENTWURF – vor Veröffentlichung anwaltlich prüfen lassen.** Platzhalter in eckigen Klammern sind zu ersetzen (zentral in `config/brand.json`).

- Aktuell nur technisch notwendige Cookies: `fp_session` (httpOnly, Secure, SameSite=Lax; Anmeldung) und `fp_csrf` (SameSite=Strict; CSRF-Schutz). Rechtsgrundlage § 25 Abs. 2 Nr. 2 TDDDG – keine Einwilligung nötig.
- Lokaler Speicher (localStorage): Theme, Du/Sie, Sprache, Hinweis-Status – nur auf dem Gerät, keine Übermittlung.
- Der Banner informiert transparent. Beide Buttons sind gleichwertig gestaltet (kein Dark Pattern).
- **Vor jeder Einführung von Statistik/Tracking:** Opt-in-Kategorie im Banner ergänzen, Skripte erst nach Einwilligung laden, Einwilligung im `ConsentLog` (kind=cookies) protokollieren, Widerruf über „Cookie-Einstellungen“ im Footer.
