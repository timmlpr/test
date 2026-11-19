"""Runtime configuration. Everything comes from environment variables; no API keys live here.

Third-party keys (Groq, Gemini) are entered by the user in the setup wizard and stored encrypted in the DB.
"""
from __future__ import annotations

import base64
import json
import os
import secrets
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]  # lernzentrum/
BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LZ_", env_file=".env", extra="ignore")

    env: str = "development"  # development | production | test
    database_url: str = f"sqlite:///{BACKEND_DIR / 'data' / 'lernzentrum.db'}"
    data_dir: Path = BACKEND_DIR / "data"
    # 32-byte base64 master key for envelope encryption + file encryption. Generated for dev if missing.
    master_key: str = ""
    session_secret: str = ""
    public_url: str = "http://localhost:3000"
    demo_mode: bool = True  # seeds the demo account on startup
    allow_registration: bool = True  # single-user: disabled automatically after the first account exists
    run_jobs: bool = True  # start background worker threads
    worker_threads: int = 2
    ics_poll_minutes: int = 30
    moodle_poll_minutes: int = 60
    max_upload_mb: int = 200
    statute_base_url: str = "https://www.gesetze-im-internet.de"
    cookie_secure: bool = False

    @property
    def is_prod(self) -> bool:
        return self.env == "production"


def _ensure_key(value: str, name: str, data_dir: Path) -> str:
    """Return a key; in dev create and persist one under data/ so restarts keep data readable."""
    if value:
        return value
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / f".{name}"
    if path.exists():
        return path.read_text().strip()
    key = base64.b64encode(secrets.token_bytes(32)).decode()
    path.write_text(key)
    path.chmod(0o600)
    return key


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.is_prod and (not s.master_key or not s.session_secret):
        raise RuntimeError("LZ_MASTER_KEY and LZ_SESSION_SECRET must be set in production")
    s.master_key = _ensure_key(s.master_key, "master_key", s.data_dir)
    s.session_secret = _ensure_key(s.session_secret, "session_secret", s.data_dir)
    (s.data_dir / "files").mkdir(parents=True, exist_ok=True)
    return s


@lru_cache
def brand() -> dict:
    for candidate in (ROOT / "config" / "brand.json", Path("/app/config/brand.json")):
        if candidate.exists():
            return json.loads(candidate.read_text(encoding="utf-8"))
    return {"name": "Lernzentrum", "tagline": "", "colors": {}, "module_palette": ["#2F5D8C"]}


# Free-tier defaults (verified 2026-11; Google does not publish Gemini numbers – observed values). Overridable per user.
DEFAULT_QUOTAS: dict[str, dict[str, int]] = {
    "groq_stt": {"rpm": 20, "rpd": 2000, "audio_s_hour": 7200, "audio_s_day": 28800},
    "gemini_lite": {"rpm": 15, "rpd": 500},
    "gemini_flash": {"rpm": 5, "rpd": 20},
    "gemini_embed": {"rpm": 100, "rpd": 1000},
}

DEFAULT_MODELS = {
    "groq_stt": "whisper-large-v3-turbo",
    "gemini_lite": "gemini-flash-lite-latest",
    "gemini_flash": "gemini-flash-latest",
    "gemini_embed": "gemini-embedding-001",
}

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
