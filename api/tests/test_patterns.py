"""Pattern-insights narrative (both modes): mock fallback, store-only PUT, poll GET."""
import pytest

from app import config
from app import data_store as store


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "JOBS_CSV", tmp_path / "jobs.csv")
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(config, "APPLICATIONS_CSV", tmp_path / "applications.csv")
    monkeypatch.setattr(config, "PATTERNS_FILE", tmp_path / "patterns.json")
    from app.agent import tools

    monkeypatch.setattr(tools.status, "record", lambda *a, **k: None)
    return tmp_path


def test_write_read_patterns_roundtrip(tmp_store):
    assert store.read_patterns() == {}
    store.write_patterns({"summary": "ok", "wins": ["w"], "risks": [], "actions": ["a"]})
    assert store.read_patterns()["summary"] == "ok"


def test_patterns_analyst_mock_fallback_and_normalizes():
    # The mock LLM can't produce JSON -> deterministic fallback, normalized to the four
    # keys with list values (a real LLM may omit wins/risks/actions).
    from app.agent.subagents import patterns_analyst

    out = patterns_analyst({"conversion": [], "follow_ups": []})
    assert set(out.keys()) == {"summary", "wins", "risks", "actions"}
    assert isinstance(out["summary"], str)
    assert all(isinstance(out[k], list) for k in ("wins", "risks", "actions"))


def test_as_str_list_is_type_safe():
    from app.agent.subagents import _as_str_list

    assert _as_str_list(["a", "b"]) == ["a", "b"]
    assert _as_str_list("one") == ["one"]   # whole string, never split into chars
    assert _as_str_list([1, 2]) == ["1", "2"]  # stringified
    assert _as_str_list(None) == [] and _as_str_list(True) == [] and _as_str_list(5) == []  # no TypeError


def test_post_patterns_external_persists(tmp_store):
    from fastapi.testclient import TestClient

    from app.main import app

    r = TestClient(app).post("/api/stats/patterns")
    assert r.status_code == 200
    body = r.json()
    assert "summary" in body
    assert store.read_patterns()["summary"] == body["summary"]  # persisted (same store path)


def test_put_patterns_internal_store_only(tmp_store):
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    payload = {"summary": "high-fit roles convert better", "wins": ["x"], "risks": [], "actions": ["y"]}
    assert client.put("/api/stats/patterns", json=payload).status_code == 200
    assert client.get("/api/stats/patterns").json()["summary"] == "high-fit roles convert better"
    assert client.put("/api/stats/patterns", json={"summary": "  "}).status_code == 422  # empty rejected
    for bad in (123, 1.5, True, {"x": 1}, ["a"]):  # truthy non-string summary -> 422, not 500
        assert client.put("/api/stats/patterns", json={"summary": bad}).status_code == 422


def test_get_patterns_empty_when_none(tmp_store):
    from fastapi.testclient import TestClient

    from app.main import app

    assert TestClient(app).get("/api/stats/patterns").json() == {}
