"""AES-GCM encryption helpers.

* `encrypt_field/decrypt_field` – sensitive DB columns (data key derived from the master key via HKDF).
* `seal_secret/open_secret` – envelope encryption for API keys/tokens: random DEK per secret, DEK wrapped by a
  key-encryption key derived from the master key. Rotating the master key only requires re-wrapping DEKs.
* `encrypt_bytes/decrypt_bytes` – file encryption for the storage layer.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from functools import lru_cache

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from .config import get_settings

_PREFIX = b"LZ1"


@lru_cache
def _derive(purpose: str) -> bytes:
    master = base64.b64decode(get_settings().master_key)
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=b"lernzentrum", info=purpose.encode()).derive(master)


def _enc(key: bytes, data: bytes, aad: bytes = b"") -> bytes:
    nonce = os.urandom(12)
    return _PREFIX + nonce + AESGCM(key).encrypt(nonce, data, aad)


def _dec(key: bytes, blob: bytes, aad: bytes = b"") -> bytes:
    if not blob.startswith(_PREFIX):
        raise ValueError("unknown ciphertext format")
    nonce, ct = blob[3:15], blob[15:]
    return AESGCM(key).decrypt(nonce, ct, aad)


def encrypt_field(text: str) -> str:
    return base64.b64encode(_enc(_derive("field"), text.encode())).decode()


def decrypt_field(token: str) -> str:
    return _dec(_derive("field"), base64.b64decode(token)).decode()


def encrypt_bytes(data: bytes) -> bytes:
    return _enc(_derive("file"), data)


def decrypt_bytes(blob: bytes) -> bytes:
    return _dec(_derive("file"), blob)


def seal_secret(value: str, context: str) -> str:
    """Envelope-encrypt a secret. `context` (e.g. 'user:1:groq') is bound as AAD."""
    dek = AESGCM.generate_key(bit_length=256)
    wrapped = _enc(_derive("kek"), dek, context.encode())
    ct = _enc(dek, value.encode(), context.encode())
    return json.dumps({"v": 1, "dek": base64.b64encode(wrapped).decode(), "ct": base64.b64encode(ct).decode()})


def open_secret(sealed: str, context: str) -> str:
    obj = json.loads(sealed)
    dek = _dec(_derive("kek"), base64.b64decode(obj["dek"]), context.encode())
    return _dec(dek, base64.b64decode(obj["ct"]), context.encode()).decode()


def mask(value: str) -> str:
    """Masked hint shown in the UI – never the full key."""
    if len(value) <= 8:
        return "•" * len(value)
    return f"{value[:4]}…{value[-4:]}"


def lookup_hash(value: str) -> str:
    return hmac.new(_derive("lookup"), value.strip().lower().encode(), hashlib.sha256).hexdigest()


def random_token(n: int = 32) -> str:
    return base64.urlsafe_b64encode(os.urandom(n)).decode().rstrip("=")


class EncryptedText(TypeDecorator):
    """Transparent AES-GCM column type."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else encrypt_field(value)

    def process_result_value(self, value, dialect):
        return None if value is None else decrypt_field(value)
