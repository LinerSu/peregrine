"""State-changing requests fired from another origin are refused.

CORS is not this control. A cross-origin POST with a simple content type is SENT by the
browser before any CORS check — CORS only decides whether the attacker may read the
response. Since the API binds to loopback, "a page you have open" is the entire threat
model, and several mutating endpoints spend API tokens (evaluate, backfill, ingest) or
delete data. The Origin header is what identifies that caller.
"""
from fastapi.testclient import TestClient

from app.main import app

EVIL = "https://attacker.example"
OURS = "http://localhost:5173"


def test_cross_origin_write_is_refused():
    r = TestClient(app).post("/api/applications", json={}, headers={"Origin": EVIL})
    assert r.status_code == 403
    assert "cross-origin" in r.json()["detail"]


def test_the_ui_origin_still_writes():
    # 422 = the request reached the route and failed validation, i.e. was NOT blocked.
    r = TestClient(app).post("/api/applications", json={}, headers={"Origin": OURS})
    assert r.status_code != 403


def test_a_request_with_no_origin_passes():
    # curl, the Internal-mode skill, any server-side caller: a browser always sets Origin
    # on a cross-origin write, so its absence means this isn't a browser.
    r = TestClient(app).post("/api/applications", json={})
    assert r.status_code != 403


def test_reads_are_not_blocked():
    # GETs change nothing, and CORS already stops another origin from reading the body.
    r = TestClient(app).get("/api/health", headers={"Origin": EVIL})
    assert r.status_code == 200


def test_every_mutating_method_is_covered():
    client = TestClient(app)
    for call in (
        lambda: client.put("/api/profile", json={}, headers={"Origin": EVIL}),
        lambda: client.patch("/api/jobs/2026-001", json={}, headers={"Origin": EVIL}),
        lambda: client.delete("/api/jobs/2026-001", headers={"Origin": EVIL}),
    ):
        assert call().status_code == 403
