"""AES-GCM field encryption and keyed hashing for lookups.

Ciphertext format: base64(nonce[12] || ciphertext+tag). The key is FP DATA_KEY (32 bytes, base64).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import String, Text
from sqlalchemy.types import TypeDecorator


def _key(raw: str) -> bytes:
    try:
        k = base64.b64decode(raw)
        if len(k) == 32:
            return k
    except Exception:  # noqa: BLE001
        pass
    return hashlib.sha256(raw.encode()).digest()


def _data_key() -> bytes:
    from app.settings import get_settings

    return _key(get_settings().data_key)


def encrypt(plaintext: str | None, key: bytes | None = None) -> str | None:
    if plaintext is None:
        return None
    nonce = os.urandom(12)
    ct = AESGCM(key or _data_key()).encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ct).decode()


def decrypt(token: str | None, key: bytes | None = None) -> str | None:
    if token is None:
        return None
    raw = base64.b64decode(token)
    return AESGCM(key or _data_key()).decrypt(raw[:12], raw[12:], None).decode("utf-8")


def lookup_hash(value: str) -> str:
    """Deterministic keyed hash for equality lookups (normalised lower-case)."""
    from app.settings import get_settings

    k = _key(get_settings().secret_key)
    return hmac.new(k, value.strip().lower().encode(), hashlib.sha256).hexdigest()


class EncryptedText(TypeDecorator):
    """SQLAlchemy column type that transparently encrypts with AES-GCM."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return encrypt(value) if value is not None else None

    def process_result_value(self, value, dialect):
        return decrypt(value) if value is not None else None


HashColumn = String(64)
