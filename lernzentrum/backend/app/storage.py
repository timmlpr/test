"""Encrypted object storage on the local filesystem (Docker volume in production).

Every object is AES-GCM encrypted; keys are random ids, never user-supplied names.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from .config import get_settings
from .crypto import decrypt_bytes, encrypt_bytes, random_token


class Storage:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if not key.replace("-", "").replace("_", "").isalnum():
            raise ValueError("invalid storage key")
        return self.root / key[:2] / key

    def put(self, data: bytes) -> str:
        key = random_token(18)
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(encrypt_bytes(data))
        return key

    def get(self, key: str) -> bytes:
        return decrypt_bytes(self._path(key).read_bytes())

    def delete(self, key: str | None) -> None:
        if not key:
            return
        try:
            self._path(key).unlink()
        except FileNotFoundError:
            pass

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def usage_bytes(self) -> int:
        return sum(p.stat().st_size for p in self.root.rglob("*") if p.is_file())


_storage: Storage | None = None


def storage() -> Storage:
    global _storage
    if _storage is None:
        _storage = Storage(get_settings().data_dir / "files")
    return _storage


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
