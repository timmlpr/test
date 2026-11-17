import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ.update({"DATABASE_URL": f"sqlite:///{_tmp}/test.db", "DEMO_MODE": "false", "SCHEDULER_ENABLED": "false", "ENV": "test",
                   "SECRET_KEY": "dGVzdC1zZWNyZXQta2V5LTMyLWJ5dGVzLWxvbmctISE=", "DATA_KEY": "ZGF0YS1rZXktZm9yLXRlc3RzLTMyLWJ5dGVzLWxvbmc=",
                   "UPLOAD_DIR": f"{_tmp}/uploads", "STRIPE_SECRET_KEY": "", "AI_MODE": "classic"})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.adapters import registry  # noqa: E402
from app.core import ratelimit  # noqa: E402
from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

registry.OFFLINE = True
ratelimit.ENABLED = False


class Api:
    """TestClient wrapper that performs the CSRF double-submit like the browser does."""

    def __init__(self):
        self.c = TestClient(app)
        self.c.get("/api/health")

    def _h(self):
        return {"x-csrf-token": self.c.cookies.get("fp_csrf", "")}

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def post(self, url, **kw):
        return self.c.post(url, headers=self._h(), **kw)

    def patch(self, url, **kw):
        return self.c.patch(url, headers=self._h(), **kw)

    def put(self, url, **kw):
        return self.c.put(url, headers=self._h(), **kw)

    def delete(self, url, **kw):
        return self.c.request("DELETE", url, headers=self._h(), **kw)


@pytest.fixture(autouse=True)
def fresh_db():
    from app import models  # noqa: F401

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def api():
    return Api()


def register(api: Api, email="anna@example.org", name="Anna Schmidt", verify=True, premium=False) -> dict:
    r = api.post("/api/auth/register", json={"email": email, "password": "sehr-sicheres-pw-1", "display_name": name, "accept_terms": True})
    assert r.status_code == 200, r.text
    if verify:
        from app.db import SessionLocal
        from app.models import User
        from app.modules.auth import _ensure_email_identifier

        with SessionLocal() as db:
            u = db.get(User, r.json()["user"]["id"])
            u.email_verified = True
            if premium:
                u.plan = "premium"
            _ensure_email_identifier(db, u)
            db.commit()
        api.post("/api/profile/identifiers", json={"kind": "name", "value": name, "own_data": True})
    return r.json()["user"]


@pytest.fixture
def user(api):
    return register(api)


@pytest.fixture
def premium(api):
    return register(api, premium=True)
