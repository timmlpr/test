"""Moodle: token exchange (password never stored), error handling, pasted tokens, sync with mocks."""
import base64

import httpx
import pytest
import respx

from app import moodle
from app.db import SessionLocal
from app.jobs import drain
from app.models import Secret

SITE = "https://moodle.example.edu"


@respx.mock
def test_detect_password_vs_sso():
    respx.post(f"{SITE}/lib/ajax/service-nologin.php").mock(
        return_value=httpx.Response(200, json=[{"error": False, "data": {"typeoflogin": 1, "sitename": "THM"}}]))
    assert moodle.detect(SITE)["method"] == "password"
    respx.post(f"{SITE}/lib/ajax/service-nologin.php").mock(
        return_value=httpx.Response(200, json=[{"error": False, "data": {"typeoflogin": 2, "sitename": "THM"}}]))
    d = moodle.detect(SITE + "/login/index.php")
    assert d["method"] == "sso" and "launch.php" in d["launch_url"]
    respx.post(f"{SITE}/lib/ajax/service-nologin.php").mock(return_value=httpx.Response(404, text="nope"))
    assert moodle.detect(SITE)["method"] == "ics"


@respx.mock
def test_exchange_errors():
    respx.post(f"{SITE}/login/token.php").mock(
        return_value=httpx.Response(200, json={"error": "x", "errorcode": "invalidlogin"}))
    with pytest.raises(moodle.MoodleError, match="falsch"):
        moodle.exchange_password(SITE, "u", "p")


def test_parse_pasted_token():
    tok = "0123456789abcdef0123456789abcdef"
    assert moodle.parse_pasted_token(tok) == tok
    url = "moodlemobile://token=" + base64.b64encode(f"sig:::{tok}:::priv".encode()).decode()
    assert moodle.parse_pasted_token(url) == tok
    with pytest.raises(moodle.MoodleError):
        moodle.parse_pasted_token("hallo")


def _mock_ws(token="t" * 32):
    def handler(request):
        form = dict(x.split("=", 1) for x in request.content.decode().split("&"))
        fn = form["wsfunction"]
        assert form["wstoken"] == token
        data = {
            "core_webservice_get_site_info": {"userid": 7, "sitename": "THM Moodle", "fullname": "Studi"},
            "core_enrol_get_users_courses": [{"id": 42, "fullname": "Grundlagen im Schuld- und Sachenrecht WS26",
                                              "shortname": "SSR"}],
            "core_course_get_contents": [{"name": "Woche 1", "modules": [{"id": 5, "name": "Folien", "contents": [
                {"type": "file", "filename": "Folien_Kaufrecht.txt", "filepath": "/", "filesize": 30,
                 "timemodified": 1767000000, "mimetype": "text/plain",
                 "fileurl": f"{SITE}/webservice/pluginfile.php/1/mod_resource/content/1/Folien_Kaufrecht.txt"}]}]}],
            "core_calendar_get_action_events_by_timesort": {"events": [
                {"id": 9, "name": "Abgabe Hausarbeit", "timesort": 1800000000, "course": {"id": 42}}]},
            "mod_forum_get_forums_by_courses": [{"id": 3, "type": "news", "course": 42}],
            "mod_forum_get_forum_discussions": {"discussions": [
                {"discussion": 11, "subject": "Raumänderung", "message": "<p>Heute A10</p>", "created": 1767000000,
                 "userfullname": "Prof. Dr. Weber"}]},
        }[fn]
        return httpx.Response(200, json=data)

    return handler


@respx.mock
def test_link_with_password_stores_only_token_and_syncs(api, module, monkeypatch):
    monkeypatch.setattr(moodle, "PAUSE_S", 0)
    respx.post(f"{SITE}/login/token.php").mock(return_value=httpx.Response(200, json={"token": "t" * 32}))
    respx.post(f"{SITE}/webservice/rest/server.php").mock(side_effect=_mock_ws())
    respx.get(url__startswith=f"{SITE}/webservice/pluginfile.php").mock(
        return_value=httpx.Response(200, content="Der Käufer zahlt den Kaufpreis nach § 433 Abs. 2 BGB.".encode()))
    r = api.post("/api/moodle/link/password", json={"site": SITE, "username": "studi", "password": "GeheimesPW!9"})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        row = db.query(Secret).filter(Secret.provider == "moodle").one()
        assert "GeheimesPW" not in row.sealed and "GeheimesPW" not in str(row.meta)
    drain()
    drain()
    st = api.get("/api/moodle/status").json()
    assert st["linked"] and st["last_stats"]["files"] == 1 and st["last_stats"]["deadlines"] == 1
    docs = api.get("/api/documents", params={"module_id": module["id"]}).json()
    assert docs and docs[0]["source"] == "moodle"
    assert api.get("/api/announcements").json()[0]["title"] == "Raumänderung"
    # incremental: second sync downloads nothing new
    api.post("/api/moodle/sync")
    drain()
    assert api.get("/api/moodle/status").json()["last_stats"]["files"] == 0
    # revoke
    api.delete("/api/moodle/link")
    assert api.get("/api/moodle/status").json()["linked"] is False


@respx.mock
def test_invalid_token_marks_error(api, monkeypatch):
    monkeypatch.setattr(moodle, "PAUSE_S", 0)
    respx.post(f"{SITE}/webservice/rest/server.php").mock(return_value=httpx.Response(
        200, json={"exception": "x", "errorcode": "invalidtoken", "message": "Invalid token"}))
    r = api.post("/api/moodle/link/token", json={"site": SITE, "token": "0123456789abcdef0123456789abcdef"})
    assert r.status_code == 422 and "Token" in r.json()["detail"]
