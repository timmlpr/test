"""Startup: create schema in dev (prod uses Alembic), seed demo data when DEMO_MODE is on."""
from __future__ import annotations

import logging

from app.db import Base, engine
from app.settings import get_settings

log = logging.getLogger("tracelow.bootstrap")


def bootstrap() -> None:
    from app import models  # noqa: F401 – register tables

    s = get_settings()
    if not s.is_prod:
        Base.metadata.create_all(engine)
    if s.demo_mode:
        from app.seed import seed_demo

        seed_demo()
