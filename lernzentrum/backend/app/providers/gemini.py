"""Google Gemini (Generative Language REST API) for answers, summaries, vision OCR and embeddings."""
from __future__ import annotations

import base64

import httpx

from .base import ProviderError

BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiLlm:
    name = "gemini"

    def __init__(self, api_key: str, models: dict[str, str], timeout: float = 45.0) -> None:
        self.api_key, self.models, self.timeout = api_key, models, timeout

    def _post(self, path: str, body: dict) -> dict:
        try:
            r = httpx.post(f"{BASE}/{path}", headers={"x-goog-api-key": self.api_key}, json=body, timeout=self.timeout)
        except httpx.HTTPError as exc:
            raise ProviderError(f"Gemini nicht erreichbar: {exc.__class__.__name__}") from exc
        if r.status_code in (400, 403) and "API_KEY" in r.text.upper():
            raise ProviderError("Gemini-Key ungültig", transient=False, status=r.status_code)
        if r.status_code == 429:
            raise ProviderError("Gemini-Kontingent erreicht (429)", status=429)
        if r.status_code >= 400:
            raise ProviderError(f"Gemini-Fehler {r.status_code}: {r.text[:200]}", transient=r.status_code >= 500,
                                status=r.status_code)
        return r.json()

    def _model(self, tier: str) -> str:
        return self.models["gemini_flash" if tier == "flash" else "gemini_lite"]

    def generate(self, prompt: str, *, system: str = "", json_mode: bool = False, tier: str = "lite",
                 max_tokens: int = 1024, temperature: float = 0.2) -> str:
        body: dict = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if json_mode:
            body["generationConfig"]["responseMimeType"] = "application/json"
        data = self._post(f"models/{self._model(tier)}:generateContent", body)
        try:
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError) as exc:
            raise ProviderError("Gemini lieferte keine Antwort (Filter oder leer).", transient=False) from exc

    def vision_ocr(self, image: bytes, mime: str) -> str:
        body = {"contents": [{"role": "user", "parts": [
            {"text": "Transkribiere den gesamten Text (auch Handschrift) dieses Bildes wortgetreu auf Deutsch. "
                     "Keine Erklärungen, nur der Text. Formeln und Tabellen als Klartext."},
            {"inline_data": {"mime_type": mime, "data": base64.b64encode(image).decode()}},
        ]}], "generationConfig": {"temperature": 0, "maxOutputTokens": 4096}}
        data = self._post(f"models/{self._model('lite')}:generateContent", body)
        try:
            return "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError):
            return ""

    def embed(self, texts: list[str]) -> list[list[float]]:
        model = self.models["gemini_embed"]
        body = {"requests": [{"model": f"models/{model}", "content": {"parts": [{"text": t[:8000]}]},
                              "outputDimensionality": 768} for t in texts]}
        data = self._post(f"models/{model}:batchEmbedContents", body)
        return [e["values"] for e in data.get("embeddings", [])]

    def list_models(self) -> list[str]:
        try:
            r = httpx.get(f"{BASE}/models", headers={"x-goog-api-key": self.api_key}, timeout=15,
                          params={"pageSize": 200})
        except httpx.HTTPError as exc:
            raise ProviderError(f"Gemini nicht erreichbar ({exc.__class__.__name__})") from exc
        if r.status_code in (400, 401, 403):
            raise ProviderError("Key wurde abgelehnt.", transient=False, status=r.status_code)
        if r.status_code >= 400:
            raise ProviderError(f"Gemini antwortet mit {r.status_code}.", status=r.status_code)
        return [m["name"].removeprefix("models/") for m in r.json().get("models", [])]

    def test(self) -> str:
        names = self.list_models()
        missing = [m for k, m in self.models.items() if m not in names and not m.endswith("-latest")]
        if missing:
            return f"Verbunden. Hinweis: Modell(e) {', '.join(missing)} nicht gelistet – Einstellungen prüfen."
        return f"Verbunden. {len(names)} Modelle verfügbar."
