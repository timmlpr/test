"""Provider interfaces. Implementations: providers/groq.py (STT), providers/gemini.py (LLM, embeddings).

Adding another provider = implement the Protocol and register it in providers/registry.py (see ADAPTERS.md).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class ProviderError(Exception):
    """Provider unreachable or returned an error. `transient` = worth retrying later."""

    def __init__(self, msg: str, transient: bool = True, status: int | None = None) -> None:
        super().__init__(msg)
        self.transient, self.status = transient, status


class MissingKey(Exception):
    def __init__(self, what: str) -> None:
        super().__init__(f"fehlt: {what}")
        self.what = what


@dataclass
class SttSegment:
    start: float
    end: float
    text: str
    speaker: str = ""


@dataclass
class SttResult:
    text: str
    segments: list[SttSegment] = field(default_factory=list)
    duration: float = 0.0
    language: str = "de"


class SttProvider(Protocol):
    name: str

    def transcribe(self, audio: bytes, filename: str, mime: str, *, prompt: str = "", language: str = "de") -> SttResult: ...

    def test(self) -> str: ...


class LlmProvider(Protocol):
    name: str

    def generate(self, prompt: str, *, system: str = "", json_mode: bool = False, tier: str = "lite",
                 max_tokens: int = 1024, temperature: float = 0.2) -> str: ...

    def vision_ocr(self, image: bytes, mime: str) -> str: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...

    def test(self) -> str: ...
