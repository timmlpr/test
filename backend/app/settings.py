"""Runtime settings. Every secret comes from the environment (.env); nothing is hard-coded."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = Path(__import__("os").environ.get("FP_CONFIG_DIR", ROOT / "config"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(ROOT / ".env", ".env"), extra="ignore")

    env: str = "development"  # development | production | test
    demo_mode: bool = True
    database_url: str = f"sqlite:///{ROOT / 'backend' / 'tracelow.db'}"
    public_url: str = "http://localhost:3000"

    # Crypto: 32-byte keys, base64 or hex. Dev defaults are generated & persisted on first start.
    secret_key: str = ""
    data_key: str = ""

    session_days: int = 14
    cookie_secure: bool = False

    # Mail (swappable SMTP). Without host, mails go to the dev outbox (log + /api/dev/outbox).
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "Tracelow <no-reply@tracelow.example>"

    # OAuth / OIDC
    google_client_id: str = ""
    google_client_secret: str = ""
    apple_client_id: str = ""
    apple_team_id: str = ""
    apple_key_id: str = ""
    apple_private_key: str = ""

    # WebAuthn
    webauthn_rp_id: str = "localhost"
    webauthn_rp_name: str = "Tracelow"

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_tax: bool = False

    # Web push (VAPID)
    vapid_public_key: str = ""
    vapid_private_key: str = ""

    # AI
    ai_mode: str = "classic"  # classic | ai | both
    ai_provider: str = "none"  # none | gemini | claude
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash-lite"
    anthropic_api_key: str = ""
    claude_model: str = "claude-haiku-5-5"

    # SMS provider adapter for phone verification (optional)
    sms_provider: str = "none"  # none | seven
    sms_api_key: str = ""
    sms_sender: str = "Tracelow"

    # OCR (document scanner). Empty = tesseract from PATH.
    tesseract_cmd: str = ""

    upload_dir: str = str(ROOT / "backend" / "uploads")
    upload_ttl_hours: int = 24
    scheduler_enabled: bool = True
    ratelimit_enabled: bool = True  # only ever false for automated e2e runs

    @property
    def is_prod(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    from app.core.keys import ensure_dev_keys

    s = Settings()
    ensure_dev_keys(s)
    return s


@lru_cache
def brand() -> dict:
    return json.loads((CONFIG_DIR / "brand.json").read_text(encoding="utf-8"))


@lru_cache
def plans() -> dict:
    return json.loads((CONFIG_DIR / "plans.json").read_text(encoding="utf-8"))
