"""Applications <-> jobs: matching, auto-link on create, orphan detection."""
import pytest

from app import config
from app import data_store as store
from app.schemas import Application, Job


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "JOBS_CSV", tmp_path / "jobs.csv")
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(config, "APPLICATIONS_CSV", tmp_path / "applications.csv")
    return tmp_path


def test_match_job_key_then_title_with_location_tiebreak():
    jobs = [
        Job(id="1", company="Acme", company_job_id="R1", position="Engineer", location="NYC"),
        Job(id="2", company="Acme", company_job_id="R2", position="Engineer", location="SF"),
    ]
    assert store.match_job(jobs, "Acme", "X", "R2").id == "2"  # exact key wins
    assert store.match_job(jobs, "acme", "engineer", "", "SF").id == "2"  # title + location tiebreak
    assert store.match_job(jobs, "Beta", "Engineer") is None  # no match
    # ambiguous: 2 same company+position, location doesn't disambiguate -> None (no guess)
    assert store.match_job(jobs, "Acme", "Engineer") is None              # no location
    assert store.match_job(jobs, "Acme", "Engineer", "", "Austin") is None  # location matches neither
    # a "manual-" key must NOT falsely match a real job by key
    assert store.match_job(jobs, "Acme", "Designer", "manual-9") is None


def test_link_reuses_job_id_and_dedupes(tmp_store):
    from fastapi.testclient import TestClient

    from app.main import app

    store.upsert_job(Job(id="2026-001", company="Acme", company_job_id="R1", position="Engineer", status="open"))
    client = TestClient(app)
    a1 = client.post("/api/applications", json={"company": "Acme", "position": "Engineer"}).json()
    assert a1["application"]["id"] == "2026-001"  # reuses the job's id
    # re-adding the same job does NOT create a second application row
    client.post("/api/applications", json={"company": "Acme", "position": "Engineer"})
    assert len(store.list_applications()) == 1


def test_delete_linked_application_reverts_job(tmp_store):
    from fastapi.testclient import TestClient

    from app.main import app

    store.upsert_job(Job(id="2026-001", company="Acme", company_job_id="R1", position="Engineer", status="open"))
    client = TestClient(app)
    client.post("/api/applications", json={"company": "Acme", "position": "Engineer"})
    assert store.get_job("2026-001").status == "applied"
    client.delete("/api/applications/2026-001")
    assert store.get_job("2026-001").status == "open"  # reverted


def test_link_does_not_downgrade_actioned_job(tmp_store):
    from fastapi.testclient import TestClient

    from app.main import app

    store.upsert_job(Job(id="2026-001", company="Acme", company_job_id="R1", position="Engineer", status="interviewing"))
    client = TestClient(app)
    client.post("/api/applications", json={"company": "Acme", "position": "Engineer"})
    assert store.get_job("2026-001").status == "interviewing"  # not downgraded to applied


def test_linked_app_mirrors_job_status_ignoring_payload(tmp_store):
    from fastapi.testclient import TestClient

    from app.main import app

    store.upsert_job(Job(id="2026-001", company="Acme", company_job_id="R1", position="Engineer", status="interviewing"))
    # payload status is ignored on link -> the app mirrors the job, no desync/downgrade
    r = TestClient(app).post("/api/applications", json={"company": "Acme", "position": "Engineer", "status": "applied"})
    assert r.json()["application"]["status"] == "interviewing"
    assert store.get_job("2026-001").status == "interviewing"


def test_create_application_links_to_tracked_job(tmp_store):
    from fastapi.testclient import TestClient

    from app.main import app

    store.upsert_job(Job(id="2026-001", company="Acme", company_job_id="R1", position="Engineer", status="open"))
    r = TestClient(app).post("/api/applications", json={"company": "Acme", "position": "Engineer"})
    assert r.status_code == 200
    body = r.json()
    assert body["job_tracked"] is True
    assert body["application"]["company_job_id"] == "R1"  # linked to the job's key
    assert store.get_job("2026-001").status == "applied"  # job marked applied


def test_create_application_orphan_when_no_job(tmp_store):
    from fastapi.testclient import TestClient

    from app.main import app

    r = TestClient(app).post("/api/applications", json={"company": "Nowhere", "position": "Wizard"})
    assert r.status_code == 200
    assert r.json()["job_tracked"] is False
    assert r.json()["application"]["company_job_id"].startswith("manual-")


def test_list_applications_flags_job_tracked(tmp_store):
    from fastapi.testclient import TestClient

    from app.main import app

    store.upsert_job(Job(id="2026-001", company="Acme", company_job_id="R1", position="Engineer"))
    store.upsert_application(Application(id="2026-002", company="Acme", company_job_id="R1",
                                        position="Engineer", applied_date="2026-06-01"))
    store.upsert_application(Application(id="2026-003", company="Solo", company_job_id="manual-x",
                                        position="Founder", applied_date="2026-06-01"))
    apps = {a["id"]: a for a in TestClient(app).get("/api/applications").json()["applications"]}
    assert apps["2026-002"]["job_tracked"] is True
    assert apps["2026-003"]["job_tracked"] is False
