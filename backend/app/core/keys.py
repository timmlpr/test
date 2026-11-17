"""Dev-only key bootstrap: production must supply FP keys via environment."""
from __future__ import annotations

import base64
import os
import secrets
from pathlib import Path


def ensure_dev_keys(s) -> None:
    if s.secret_key and s.data_key:
        return
    if s.is_prod:
        raise RuntimeError("SECRET_KEY and DATA_KEY must be set in production (.env)")
    store = Path(s.upload_dir).parent / ".devkeys"
    if store.exists():
        sk, dk = store.read_text().split("\n")[:2]
    else:
        sk = base64.b64encode(secrets.token_bytes(32)).decode()
        dk = base64.b64encode(secrets.token_bytes(32)).decode()
        store.parent.mkdir(parents=True, exist_ok=True)
        store.write_text(f"{sk}\n{dk}\n")
        os.chmod(store, 0o600)
    s.secret_key = s.secret_key or sk
    s.data_key = s.data_key or dk
