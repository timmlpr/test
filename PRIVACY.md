# Privacy by design – technical summary

* **Own data only.** Scans accept identifier IDs, never free text. An identifier must be owned and verified.
* **Minimisation.** Images never touch disk. Mail exports: only sender/category/amount/unsubscribe link are kept.
  Password check sends a 5-character hash prefix. AI calls receive anonymised text only (`core/anonymizer.py`).
* **Encryption.** Sensitive fields AES-GCM; estate vault end-to-end encrypted with a key only the user knows.
* **EU hosting.** Hetzner (Germany). Processors listed in `legal/datenschutz.md`.
* **User control.** Export everything (Art. 20, JSON) and delete the account with one confirmation (Art. 17). Consent
  log for: terms, privacy, own-data per identifier, guardian, microphone, push, waitlist, family join.

## Retention (implemented in `backend/app/jobs.py::retention`, daily 03:17)
| Data | Kept |
|---|---|
| trashed findings | 30 days |
| unconfirmed waitlist | 7 days |
| one-time tokens | until expiry |
| AI response cache | 30 days |
| notifications | 180 days |
| audit log (no plaintext) | 365 days |
| uploads (if any) | 24 h |
| backups | 30 days rotation |

Full concept: `legal/loeschkonzept.md`; DPIA draft: `legal/dsfa.md`; record of processing: `legal/verarbeitungsverzeichnis.md`.
