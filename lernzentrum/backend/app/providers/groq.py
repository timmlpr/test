"""Groq Whisper speech-to-text (OpenAI-compatible endpoint)."""
from __future__ import annotations

import httpx

from .base import ProviderError, SttResult, SttSegment

BASE = "https://api.groq.com/openai/v1"


class GroqStt:
    name = "groq"

    def __init__(self, api_key: str, model: str = "whisper-large-v3-turbo", timeout: float = 60.0) -> None:
        self.api_key, self.model, self.timeout = api_key, model, timeout

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    def transcribe(self, audio: bytes, filename: str, mime: str, *, prompt: str = "", language: str = "de") -> SttResult:
        data = {"model": self.model, "response_format": "verbose_json", "language": language, "temperature": "0"}
        if prompt:
            data["prompt"] = prompt[:800]  # Whisper prompt is limited to ~224 tokens
        try:
            r = httpx.post(f"{BASE}/audio/transcriptions", headers=self._headers(), data=data,
                           files={"file": (filename, audio, mime or "application/octet-stream")}, timeout=self.timeout)
        except httpx.HTTPError as exc:
            raise ProviderError(f"Groq nicht erreichbar: {exc.__class__.__name__}") from exc
        if r.status_code == 401:
            raise ProviderError("Groq-Key ungültig", transient=False, status=401)
        if r.status_code == 429:
            raise ProviderError("Groq-Kontingent erreicht (429)", transient=True, status=429)
        if r.status_code >= 400:
            raise ProviderError(f"Groq-Fehler {r.status_code}: {r.text[:200]}", transient=r.status_code >= 500,
                                status=r.status_code)
        body = r.json()
        segs = [SttSegment(float(s.get("start", 0)), float(s.get("end", 0)), str(s.get("text", "")).strip())
                for s in body.get("segments") or []]
        return SttResult(text=str(body.get("text", "")).strip(), segments=segs,
                         duration=float(body.get("duration") or (segs[-1].end if segs else 0)))

    def test(self) -> str:
        try:
            r = httpx.get(f"{BASE}/models", headers=self._headers(), timeout=15)
        except httpx.HTTPError as exc:
            raise ProviderError(f"Groq nicht erreichbar ({exc.__class__.__name__})") from exc
        if r.status_code == 401:
            raise ProviderError("Key wurde abgelehnt (401).", transient=False, status=401)
        if r.status_code >= 400:
            raise ProviderError(f"Groq antwortet mit {r.status_code}.", status=r.status_code)
        ids = [m.get("id", "") for m in r.json().get("data", [])]
        if not any("whisper" in i for i in ids):
            raise ProviderError("Key gültig, aber kein Whisper-Modell freigeschaltet.", transient=False)
        return f"Verbunden. Whisper verfügbar ({self.model})."
