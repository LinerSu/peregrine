"""/api/health contract — the `dataset` field drives the web's demo-data badge.

Without it, live and demo modes are pixel-identical in the UI, so a forgotten
PEREGRINE_DATASET quietly impersonates the user's real workspace (the exact
confusion that motivated the badge).
"""
from fastapi.testclient import TestClient

from app import config
from app.main import app


def test_health_reports_null_dataset_in_live_mode(monkeypatch):
    monkeypatch.setattr(config, "DATASET", "", raising=False)
    body = TestClient(app).get("/api/health").json()
    assert body["status"] == "ok"
    assert body["dataset"] is None


def test_health_reports_active_dataset(monkeypatch):
    monkeypatch.setattr(config, "DATASET", "ai-engineer", raising=False)
    body = TestClient(app).get("/api/health").json()
    assert body["dataset"] == "ai-engineer"
