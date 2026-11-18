# Setup checklist – accounts & keys that remain

Nothing here is required for the local demo. Items marked **launch** are needed for a public launch.

| Service | Purpose | Signup | Env variable(s) | Free? | Needed for |
|---|---|---|---|---|---|
| Hetzner Cloud | EU server (Germany) | https://accounts.hetzner.com/signUp | – (`DEPLOY_HOST/USER/SSH_KEY` as GitHub secrets for CI deploy) | no (~5 €/month CX22) | **launch** |
| Domain + DNS | public URL, HTTPS | any registrar (e.g. INWX, Hetzner) | `DOMAIN`, `PUBLIC_URL`, `WEBAUTHN_RP_ID` | no (~10 €/year) | **launch** |
| SMTP provider | verification, reminders, cancellation receipts | e.g. Brevo/Mailjet (EU) or own mailbox | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | free tiers exist | **launch** |
| Stripe | payments, invoices, portal | https://dashboard.stripe.com/register | `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_TAX` | test mode free; fees per transaction | **launch** (paid plans) |
| Secrets | encryption + sessions | generate locally | `SECRET_KEY`, `DATA_KEY`, `POSTGRES_PASSWORD`, `BACKUP_PASSPHRASE` | yes | **launch** |
| Google OAuth | "Sign in with Google" | Google Cloud Console | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | yes | optional |
| Apple Developer | "Sign in with Apple" | https://developer.apple.com/programs/ | `APPLE_CLIENT_ID`, `APPLE_TEAM_ID`, `APPLE_KEY_ID`, `APPLE_PRIVATE_KEY` | no (99 USD/year) | optional |
| VAPID keys | web push | `npx web-push generate-vapid-keys` | `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` | yes | optional |
| Brave Search API | deep scan | https://api-dashboard.search.brave.com | `BRAVE_API_KEY` | $5 credit/month | optional |
| Google Safe Browsing / Web Risk | scam check | Google Cloud Console | `SAFE_BROWSING_KEY` | free non-commercial | optional |
| abuse.ch | URLhaus scam check | https://auth.abuse.ch | `URLHAUS_AUTH_KEY` | yes | optional |
| Gemini / Claude | AI assistant | aistudio.google.com / console.anthropic.com | `GEMINI_API_KEY` / `ANTHROPIC_API_KEY`, `AI_MODE`, `AI_PROVIDER` | Gemini free tier | optional |
| SMS provider | phone verification | e.g. seven.io, sms77 (EU) | `SMS_PROVIDER` (+ adapter to implement) | no | optional |
| HIBP / TinEye | paid sources | haveibeenpwned.com / tineye.com | `HIBP_API_KEY`, `TINEYE_API_KEY` | no | optional |

Owner decisions still open: legal entity & imprint data (`config/brand.json → operator`), small-business VAT switch
(`operator.small_business`), final brand name (trademark search), whether to show a "most popular" plan (`plans.json →
most_popular`, keep `null` until real data supports it).
