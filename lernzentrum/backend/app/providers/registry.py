"""Resolves user-entered keys into provider instances and wraps every call with the quota manager.

Missing keys never crash a feature: callers get `MissingKey` (STT) or `None` (LLM → extractive fallback).
Tests can inject fakes through `OVERRIDES`.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import quota
from ..config import DEFAULT_MODELS
from ..crypto import mask, open_secret, seal_secret
from ..db import utcnow
from ..models import CacheEntry, Secret, User
from .base import LlmProvider, MissingKey, ProviderError, SttProvider, SttResult
from .gemini import GeminiLlm
from .groq import GroqStt

OVERRIDES: dict[str, object | None] = {"stt": None, "llm": None}

PROVIDERS = {
    "groq": {"label": "Groq (Spracherkennung)", "url": "https://console.groq.com/keys"},
    "gemini": {"label": "Google Gemini (Antworten)", "url": "https://aistudio.google.com/app/apikey"},
    "moodle": {"label": "Moodle-Token", "url": ""},
    "imap": {"label": "E-Mail-Postfach (IMAP)", "url": ""},
    "webdav": {"label": "Cloud-Ordner (WebDAV)", "url": ""},
}


def _ctx(user_id: int, provider: str) -> str:
    return f"user:{user_id}:{provider}"


def get_secret_row(db: Session, user: User, provider: str) -> Secret | None:
    return db.scalar(select(Secret).where(Secret.user_id == user.id, Secret.provider == provider))


def get_secret(db: Session, user: User, provider: str) -> str | None:
    row = get_secret_row(db, user, provider)
    return open_secret(row.sealed, _ctx(user.id, provider)) if row else None


def set_secret(db: Session, user: User, provider: str, value: str, meta: dict | None = None) -> Secret:
    value = value.strip()
    row = get_secret_row(db, user, provider)
    if row is None:
        row = Secret(user_id=user.id, provider=provider, sealed="")
        db.add(row)
    row.sealed = seal_secret(value, _ctx(user.id, provider))
    row.hint = mask(value)
    row.meta = meta or row.meta or {}
    row.status, row.status_detail, row.checked_at = "untested", "", None
    db.flush()
    return row


def delete_secret(db: Session, user: User, provider: str) -> None:
    row = get_secret_row(db, user, provider)
    if row:
        db.delete(row)
        db.flush()


def models_for(user: User) -> dict[str, str]:
    m = dict(DEFAULT_MODELS)
    m.update((user.settings or {}).get("models", {}))
    return m


def stt_for(db: Session, user: User) -> SttProvider:
    if OVERRIDES["stt"] is not None:
        return OVERRIDES["stt"]  # type: ignore[return-value]
    key = get_secret(db, user, "groq")
    if not key:
        raise MissingKey("Groq-API-Key (Spracherkennung)")
    return GroqStt(key, models_for(user)["groq_stt"])


def llm_for(db: Session, user: User) -> LlmProvider | None:
    if OVERRIDES["llm"] is not None:
        return OVERRIDES["llm"]  # type: ignore[return-value]
    key = get_secret(db, user, "gemini")
    return GeminiLlm(key, models_for(user)) if key else None


def transcribe(db: Session, user: User, audio: bytes, filename: str, mime: str, *, duration_hint: float,
               prompt: str = "") -> SttResult:
    stt = stt_for(db, user)
    quota.acquire(db, user, "groq_stt", requests=1, audio_s=max(duration_hint, 10.0))  # Groq bills min. 10 s
    db.commit()
    try:
        return stt.transcribe(audio, filename, mime, prompt=prompt)
    except ProviderError as exc:
        if exc.status == 429:
            raise quota.QuotaExceeded("groq_stt", "rpm", 60) from exc
        raise


def _cache_get(db: Session, key: str) -> str | None:
    row = db.get(CacheEntry, key)
    return row.value if row else None


def _cache_put(db: Session, key: str, value: str) -> None:
    db.merge(CacheEntry(key=key, value=value, created_at=utcnow()))


def generate(db: Session, user: User, prompt: str, *, system: str = "", json_mode: bool = False, tier: str = "lite",
             max_tokens: int = 1024, cache: bool = True) -> str | None:
    """LLM call with cache + quota. Returns None when no key is configured."""
    llm = llm_for(db, user)
    if llm is None:
        return None
    ck = hashlib.sha256(json.dumps([user.id, prompt, system, json_mode, tier]).encode()).hexdigest()
    if cache and (hit := _cache_get(db, ck)) is not None:
        return hit
    quota.acquire(db, user, "gemini_flash" if tier == "flash" else "gemini_lite")
    db.commit()
    try:
        out = llm.generate(prompt, system=system, json_mode=json_mode, tier=tier, max_tokens=max_tokens)
    except ProviderError as exc:
        if exc.status == 429:
            raise quota.QuotaExceeded("gemini_flash" if tier == "flash" else "gemini_lite", "rpm", 60) from exc
        raise
    if cache:
        _cache_put(db, ck, out)
        db.commit()
    return out


def generate_json(db: Session, user: User, prompt: str, **kw) -> dict | list | None:
    raw = generate(db, user, prompt, json_mode=True, **kw)
    if raw is None:
        return None
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def embed(db: Session, user: User, texts: list[str]) -> list[list[float]] | None:
    llm = llm_for(db, user)
    if llm is None or not texts:
        return None
    try:
        quota.acquire(db, user, "gemini_embed", requests=len(texts))
    except quota.QuotaExceeded:
        return None  # local vectors keep working
    db.commit()
    try:
        return llm.embed(texts)
    except ProviderError:
        return None


def vision_ocr(db: Session, user: User, image: bytes, mime: str) -> str | None:
    llm = llm_for(db, user)
    if llm is None:
        return None
    quota.acquire(db, user, "gemini_lite")
    db.commit()
    return llm.vision_ocr(image, mime)


def test_provider(db: Session, user: User, provider: str) -> tuple[bool, str]:
    row = get_secret_row(db, user, provider)
    if row is None:
        return False, "Kein Key hinterlegt."
    key = open_secret(row.sealed, _ctx(user.id, provider))
    try:
        if provider == "groq":
            msg = GroqStt(key, models_for(user)["groq_stt"]).test()
        elif provider == "gemini":
            msg = GeminiLlm(key, models_for(user)).test()
        else:
            return False, "Für diesen Eintrag gibt es keinen Test."
        ok = True
    except ProviderError as exc:
        ok, msg = False, str(exc)
    row.status, row.status_detail, row.checked_at = ("ok" if ok else "error"), msg, datetime.utcnow()
    db.commit()
    return ok, msg
