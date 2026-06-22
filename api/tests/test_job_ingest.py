"""Job ingestion from pasted / uploaded content (both modes)."""
import pytest

from app import config
from app import data_store as store


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "JOBS_CSV", tmp_path / "jobs.csv")
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(config, "APPLICATIONS_CSV", tmp_path / "applications.csv")
    monkeypatch.setattr(config, "JOB_SOURCE", tmp_path / "job_source.md")
    from app.agent import tools

    monkeypatch.setattr(tools.status, "record", lambda *a, **k: None)
    return tmp_path


def test_save_ingested_job_creates_then_dedupes(tmp_store):
    from app.agent import tools

    r = tools.save_ingested_job({"company": "Acme", "position": "Engineer", "description": "build"})
    assert r["created"] is True and r["job"]["company"] == "Acme"
    assert len(store.list_jobs()) == 1
    # same company + derived id -> dedup (company_job_id slugged from the title)
    r2 = tools.save_ingested_job({"company": "Acme", "position": "Engineer"})
    assert r2["created"] is False
    assert len(store.list_jobs()) == 1


def test_ingest_coerces_none_optional_fields(tmp_store):
    from app.agent import tools

    # LLMs often emit null for optional fields — must not crash Pydantic validation.
    r = tools.save_ingested_job(
        {"company": "Acme", "position": "Eng", "location": None, "url": None, "description": None}
    )
    assert r["created"] is True
    assert r["job"]["location"] == ""


def test_save_ingested_job_requires_company_and_position(tmp_store):
    from app.agent import tools

    assert "error" in tools.save_ingested_job({"company": "Acme"})
    assert "error" in tools.save_ingested_job({"position": "Engineer"})
    assert store.list_jobs() == []


def test_ingest_job_doc_mock_cannot_parse(tmp_store):
    from app.agent import tools

    # The mock LLM can't produce structured fields -> a clean error, no job created.
    assert "error" in tools.ingest_job_doc("Some pasted posting text")
    assert "error" in tools.ingest_job_doc("")
    assert store.list_jobs() == []


def test_ingest_marker_bumps_on_save_and_dedup(tmp_store):
    from app.agent import tools

    assert tools.get_ingest_result()["seq"] == 0
    tools.save_ingested_job({"company": "Acme", "position": "Engineer"})
    r1 = tools.get_ingest_result()
    assert r1["seq"] == 1 and r1["created"] is True
    # A dedup (same job) STILL bumps the marker, so the Internal poll resolves
    # instead of timing out.
    tools.save_ingested_job({"company": "Acme", "position": "Engineer"})
    r2 = tools.get_ingest_result()
    assert r2["seq"] == 2 and r2["created"] is False


def test_save_job_source_roundtrip(tmp_store):
    from app.agent import tools

    assert tools.save_job_source("raw posting")["chars"] == len("raw posting")
    assert store.read_job_source() == "raw posting"


def test_scan_caps_new_jobs(tmp_store, monkeypatch):
    from app.agent import providers, tools

    monkeypatch.setattr(store, "read_portals",
                        lambda: {"companies": [{"provider": "x", "name": "Acme"}], "filters": {}, "snapshot": False})
    monkeypatch.setattr(store, "read_targets", lambda: {})
    posts = [providers.RawPosting(company="Acme", company_job_id=f"r{i}", position="Eng") for i in range(60)]
    monkeypatch.setattr(providers, "fetch", lambda *a, **k: posts)

    r = tools.scan_jobs()
    assert r["new"] == 50 and r["capped"] is True  # flood is bounded
    assert len(store.list_jobs()) == 50


def test_ingest_endpoints(tmp_store):
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    # Internal store-only save creates a job.
    r = client.post("/api/jobs/ingest-doc/save", json={"company": "Luma", "position": "ML Eng"})
    assert r.status_code == 200 and r.json()["created"] is True
    # Missing a required field (position) -> 422 from the schema.
    assert client.post("/api/jobs/ingest-doc/save", json={"company": "X"}).status_code == 422
    # Empty stash -> 422 (won't clobber).
    assert client.put("/api/jobs/ingest-source", json={"text": "  "}).status_code == 422
    # External parse can't extract a job in mock mode -> 422.
    assert client.post("/api/jobs/ingest-doc", json={"text": "posting"}).status_code == 422
    # Internal save tolerates JSON null for optional fields (the HTTP entry point,
    # not just the function) — Claude may emit null for an absent company_job_id.
    rn = client.post(
        "/api/jobs/ingest-doc/save",
        json={"company": "Beta", "position": "Dev", "company_job_id": None, "location": None},
    )
    assert rn.status_code == 200 and rn.json()["created"] is True
