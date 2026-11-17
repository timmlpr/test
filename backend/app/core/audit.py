from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AuditLog


def audit(db: Session, action: str, user_id: str | None = None, ip_hash: str | None = None, **meta) -> None:
    """Write an audit entry. `meta` must never contain personal plaintext (ids/counts only)."""
    db.add(AuditLog(user_id=user_id, action=action, meta=meta or None, ip_hash=ip_hash))
