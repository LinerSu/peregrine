"""Auto-evaluate on ingest: a newly added job arrives scored — with guards.

Rules pinned here:
  * External-path ingests (/ingest, /ingest-doc, upload) schedule a BACKGROUND fit
    evaluation only when the job was CREATED, a real profile exists, and the active
    provider isn't effectively mock — a keyless anthropic/openai config silently
    falls back to the {fit 0.5, "(mock)"} stub, and placeholder scores must never be
    written silently;
  * the Internal store-only path (/ingest-doc/save) NEVER schedules API-side LLM
    work — the local-Claude skill chains the evaluation itself (mode contract), and
    the shared /ingest URL path honours the caller's auto_evaluate:false for the
    same reason.
"""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import config
from app import data_store as store
from app.agent import llm
from app.agent import tools
from app.main import app


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "JOBS_CSV", tmp_path / "jobs.csv")
    monkeypatch.setattr(config, "APPLICATIONS_CSV", tmp_path / "applications.csv")
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(config, "PROFILE_YML", tmp_path / "profile.yml")
    (tmp_path / "jobs").mkdir()

    calls: list[str] = []
    monkeypatch.setattr(tools, "evaluate_fit", lambda job_id: calls.append(job_id))
    monkeypatch.setattr(tools.status, "record", lambda *a, **k: None)
    monkeypatch.setattr(store, "write_ingest_result", lambda *a, **k: None)
    monkeypatch.setattr(store, "read_ingest_result", lambda: {}, raising=False)

    # Patch the settings the mock-ness check itself reads, so a keyless real provider
    # is exercised exactly as it behaves in production (it falls back to the stub).
    def set_provider(name: str, key: str = "sk-test") -> None:
        monkeypatch.setattr(llm, "get_settings", lambda: SimpleNamespace(
            llm_provider=name, anthropic_api_key=key, openai_api_key=key))

    def set_ingest_result(created: bool) -> None:
        monkeypatch.setattr(
            tools, "ingest_job_doc",
            lambda text: {"job": {"id": "2026-001", "position": "Eng"}, "created": created},
        )
        monkeypatch.setattr(
            tools, "ingest_job_url",
            lambda url: {"job": {"id": "2026-001", "position": "Eng"}, "created": created},
        )

    return SimpleNamespace(calls=calls, set_provider=set_provider,
                           set_ingest_result=set_ingest_result, tmp_path=tmp_path)


def _profile(ready: bool) -> None:
    config.PROFILE_YML.write_text("name: someone\nskills: [python]\n" if ready else "name: ''\n")


def test_profile_ready_reads_the_profile(env):
    _profile(False)
    assert tools.profile_ready() is False
    _profile(True)
    assert tools.profile_ready() is True


def test_created_job_with_profile_schedules_background_eval(env):
    _profile(True)
    env.set_provider("anthropic")
    env.set_ingest_result(created=True)
    r = TestClient(app).post("/api/jobs/ingest-doc", json={"text": "posting"})
    assert r.status_code == 200 and r.json()["auto_evaluating"] is True
    # TestClient runs background tasks before returning — the eval must have fired.
    assert env.calls == ["2026-001"]


@pytest.mark.parametrize("provider,key,ready,created", [
    ("mock", "sk-test", True, True),   # mock provider: never write placeholders silently
    ("anthropic", "", True, True),     # real provider, NO key -> falls back to the stub
    ("openai", "   ", True, True),     # blank key counts as no key
    ("anthropic", "sk-test", False, True),  # empty profile: scoring is noise
    ("anthropic", "sk-test", True, False),  # dedup hit: keeps its existing evaluation
])
def test_guards_suppress_auto_eval(env, provider, key, ready, created):
    _profile(ready)
    env.set_provider(provider, key)
    env.set_ingest_result(created=created)
    r = TestClient(app).post("/api/jobs/ingest-doc", json={"text": "posting"})
    assert r.status_code == 200
    assert "auto_evaluating" not in r.json()
    assert env.calls == []


def test_url_ingest_respects_the_callers_auto_evaluate_flag(env):
    # /api/jobs/ingest is called in BOTH modes (fetching a URL is deterministic), so the
    # Internal client sends auto_evaluate:false — the API must not spend tokens for it.
    _profile(True)
    env.set_provider("anthropic")
    env.set_ingest_result(created=True)
    client = TestClient(app)

    r = client.post("/api/jobs/ingest", json={"url": "https://example.com/j", "auto_evaluate": False})
    assert r.status_code == 200 and "auto_evaluating" not in r.json()
    assert env.calls == []

    r = client.post("/api/jobs/ingest", json={"url": "https://example.com/j"})  # External default
    assert r.status_code == 200 and r.json()["auto_evaluating"] is True
    assert env.calls == ["2026-001"]


def test_internal_store_only_save_never_schedules_api_eval(env):
    # The mode contract: /ingest-doc/save is Claude's store-only path — the API must
    # not run LLM work for it (the skill chains the evaluation locally instead).
    _profile(True)
    env.set_provider("anthropic")
    r = TestClient(app).post("/api/jobs/ingest-doc/save",
                             json={"company": "Acme", "position": "Eng"})
    assert r.status_code == 200
    assert "auto_evaluating" not in r.json()
    assert env.calls == []


# --- backfill: apply the capability to already-tracked jobs ---------------------------

def _job(id: str, status: str = "open", fit: "float | None" = None):
    from app.schemas import Job

    from app import data_store as store_mod
    store_mod.upsert_job(Job(id=id, company="Acme", company_job_id=f"R{id[-1]}",
                             position="Eng", status=status, fit_score=fit))


def test_backfill_schedules_only_open_jobs_missing_scores(env):
    _profile(True)
    env.set_provider("anthropic")
    _job("2026-001")                       # open, missing -> scheduled
    _job("2026-002", fit=0.7)              # already scored -> skipped
    _job("2026-003", status="closed")      # dead -> skipped
    _job("2026-004")                       # open, missing -> scheduled
    r = TestClient(app).post("/api/jobs/evaluate-missing")
    assert r.status_code == 200 and r.json() == {"scheduled": 2}
    assert sorted(env.calls) == ["2026-001", "2026-004"]


@pytest.mark.parametrize("provider,key,ready", [
    ("mock", "sk-test", True),
    ("anthropic", "", True),   # keyless real provider would mass-write 0.5 placeholders
    ("anthropic", "sk-test", False),
])
def test_backfill_guards(env, provider, key, ready):
    _profile(ready)
    env.set_provider(provider, key)
    _job("2026-001")
    r = TestClient(app).post("/api/jobs/evaluate-missing")
    assert r.status_code == 200 and r.json()["scheduled"] == 0
    assert "reason" in r.json()
    assert env.calls == []
