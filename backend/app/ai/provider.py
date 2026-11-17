"""AI layer. Providers are swappable; every call goes through `ask()` which:
  1. refuses hard-limit requests (guard) before anything leaves the server,
  2. anonymises names/emails/phones/addresses → placeholders,
  3. enforces per-user daily limits and a response cache,
  4. de-anonymises the answer locally.
Without a key the app stays fully functional in classic mode."""
from __future__ import annotations

import hashlib

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.anonymizer import anonymize, deanonymize
from app.core.clock import utcnow
from app.core.errors import ApiError
from app.settings import get_settings

SYSTEM = ("Du bist der Assistent der Datenschutz-App Fadeprint. Antworte auf Deutsch, ruhig, sachlich, in kurzen Sätzen, "
          "ohne Panikmache. Nenne immer genau einen nächsten Schritt. Hilf ausschließlich bei den eigenen Daten der Person. "
          "Lehne Recherchen über andere Menschen, Kennzeichen, Gesichtserkennung und Überwachung höflich ab. "
          "Platzhalter wie ⟦NAME_1⟧ unverändert lassen. Keine Rechtsberatung.")


class AiProvider:
    name = "none"

    def available(self) -> bool:
        return False

    def complete(self, system: str, prompt: str) -> str:  # pragma: no cover - interface
        raise NotImplementedError


class NoneProvider(AiProvider):
    pass


class GeminiProvider(AiProvider):
    name = "gemini"

    def available(self) -> bool:
        return bool(get_settings().gemini_api_key)

    def complete(self, system: str, prompt: str) -> str:
        s = get_settings()
        r = httpx.post(f"https://generativelanguage.googleapis.com/v1beta/models/{s.gemini_model}:generateContent",
                       headers={"x-goog-api-key": s.gemini_api_key},
                       json={"systemInstruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                             "generationConfig": {"maxOutputTokens": 400, "temperature": 0.3}}, timeout=30)
        if r.status_code != 200:
            raise ApiError(503, "ai_unavailable")
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]


class ClaudeProvider(AiProvider):
    name = "claude"

    def available(self) -> bool:
        return bool(get_settings().anthropic_api_key)

    def complete(self, system: str, prompt: str) -> str:
        s = get_settings()
        r = httpx.post("https://api.anthropic.com/v1/messages",
                       headers={"x-api-key": s.anthropic_api_key, "anthropic-version": "2023-06-01"},
                       json={"model": s.claude_model, "max_tokens": 400, "system": system,
                             "messages": [{"role": "user", "content": prompt}]}, timeout=30)
        if r.status_code != 200:
            raise ApiError(503, "ai_unavailable")
        return "".join(b.get("text", "") for b in r.json().get("content", []))


def provider() -> AiProvider:
    s = get_settings()
    if s.ai_mode == "classic":
        return NoneProvider()
    p = {"gemini": GeminiProvider, "claude": ClaudeProvider}.get(s.ai_provider, NoneProvider)()
    return p if p.available() else NoneProvider()


def ai_status() -> dict:
    p = provider()
    return {"mode": get_settings().ai_mode, "provider": p.name, "available": p.available(),
            "free_tier_notice": p.name == "gemini"}


def ask(db: Session, user, prompt: str, known_names: list[str], cap: int) -> str | None:
    """Return an AI answer or None when no provider is active (caller falls back to classic)."""
    from app.models import AiCache, AiUsage

    p = provider()
    if not p.available():
        return None
    anon, mapping = anonymize(prompt, known_names)
    key = hashlib.sha256(f"{p.name}|{anon}".encode()).hexdigest()
    cached = db.get(AiCache, key)
    if cached:
        return deanonymize(cached.response, mapping)
    day = utcnow().strftime("%Y-%m-%d")
    usage = db.scalar(select(AiUsage).where(AiUsage.user_id == user.id, AiUsage.day == day))
    if not usage:
        usage = AiUsage(user_id=user.id, day=day, count=0)
        db.add(usage)
    if usage.count >= cap:
        raise ApiError(429, "ai_daily_limit", limit=cap)
    usage.count += 1
    out = p.complete(SYSTEM, anon)
    db.add(AiCache(key=key, response=out))
    db.commit()
    return deanonymize(out, mapping)
