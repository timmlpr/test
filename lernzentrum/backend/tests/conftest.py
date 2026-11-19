"""Test setup: isolated temp data dir + SQLite, no worker threads, no demo seed (unless requested)."""
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="lz-test-")
os.environ.update({"LZ_ENV": "test", "LZ_DATA_DIR": _tmp, "LZ_DATABASE_URL": f"sqlite:///{_tmp}/test.db",
                   "LZ_RUN_JOBS": "false", "LZ_DEMO_MODE": "false"})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.providers import registry  # noqa: E402
from app.retrieval.index import bump  # noqa: E402
from app.security import limiter  # noqa: E402

PASSWORD = "Sicher-Passwort-2026"


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    bump()
    limiter._hits.clear()
    registry.OVERRIDES.update({"stt": None, "llm": None})
    yield
    registry.OVERRIDES.update({"stt": None, "llm": None})


class Api:
    """TestClient wrapper that sends the CSRF header automatically."""

    def __init__(self, client: TestClient) -> None:
        self.c = client

    def _h(self, kw):
        h = kw.pop("headers", {}) or {}
        tok = self.c.cookies.get("lz_csrf")
        if tok:
            h["x-csrf-token"] = tok
        return h

    def get(self, url, **kw):
        return self.c.get(url, headers=self._h(kw), **kw)

    def post(self, url, **kw):
        return self.c.post(url, headers=self._h(kw), **kw)

    def put(self, url, **kw):
        return self.c.put(url, headers=self._h(kw), **kw)

    def patch(self, url, **kw):
        return self.c.patch(url, headers=self._h(kw), **kw)

    def delete(self, url, **kw):
        return self.c.delete(url, headers=self._h(kw), **kw)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def api(client):
    a = Api(client)
    r = a.post("/api/auth/register", json={"email": "studi@example.com", "password": PASSWORD, "display_name": "Tim"})
    assert r.status_code == 200, r.text
    return a


@pytest.fixture
def module(api):
    r = api.post("/api/modules", json={"name": "Grundlagen im Schuld- und Sachenrecht", "short": "SSR",
                                       "lecturer": "Prof. Dr. Weber"})
    assert r.status_code == 200
    return r.json()
