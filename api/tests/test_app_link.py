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


def test_link_orphan_application_to_job(tmp_store):
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    orphan = client.post("/api/applications", json={
        "company": "Acme", "position": "Engineer", "notes": "referred by X", "interview_date": "2026-07-01",
    }).json()["application"]
    assert orphan["company_job_id"].startswith("manual-")
    oid = orphan["id"]
    store.upsert_job(Job(id="2026-050", company="Acme", company_job_id="R9",
                         position="Engineer", status="open", url="http://x"))
    r = client.post(f"/api/applications/{oid}/link", json={"job_id": "2026-050"})
    assert r.status_code == 200
    linked = r.json()["application"]
    assert linked["id"] == "2026-050"            # re-keyed to the job
    assert linked["company_job_id"] == "R9"      # adopts the job's key
    assert linked["url"] == "http://x"           # carries the job's fields
    assert linked["notes"] == "referred by X"    # preserves the orphan's tracker fields
    assert linked["interview_date"] == "2026-07-01"
    assert store.get_job("2026-050").status == "applied"  # job synced to the app's status
    ids = [a.id for a in store.list_applications()]
    assert oid not in ids and "2026-050" in ids and len(ids) == 1  # orphan row replaced


def test_link_syncs_job_to_orphan_status(tmp_store):
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    orphan = client.post("/api/applications", json={
        "company": "Beta", "position": "Designer", "status": "interviewing",
    }).json()["application"]
    store.upsert_job(Job(id="2026-051", company="Beta", company_job_id="R1", position="Designer", status="open"))
    client.post(f"/api/applications/{orphan['id']}/link", json={"job_id": "2026-051"})
    assert store.get_job("2026-051").status == "interviewing"  # synced to the user's progress


def test_orphan_ingest_marker_link_chain(tmp_store, monkeypatch):
    """End-to-end orphan -> add-posting -> link: an ingest writes the job + a marker
    carrying its id (what the Internal poll and the External response both surface),
    then the deterministic link re-keys the orphan onto it. Same chain in both modes."""
    from fastapi.testclient import TestClient

    from app.agent import tools
    from app.main import app

    monkeypatch.setattr(tools.status, "record", lambda *a, **k: None)
    client = TestClient(app)
    orphan = client.post("/api/applications", json={"company": "Acme", "position": "Engineer"}).json()["application"]
    saved = tools.save_ingested_job({"company": "Acme", "position": "Engineer", "description": "build things"})
    assert saved["created"] is True
    marker = tools.get_ingest_result()  # the poll/response payload
    assert marker["job_id"] and marker["seq"] > 0
    linked = client.post(f"/api/applications/{orphan['id']}/link", json={"job_id": marker["job_id"]}).json()
    assert linked["application"]["id"] == marker["job_id"]
    assert linked["job_tracked"] is True


def test_link_endpoint_does_not_downgrade_actioned_job(tmp_store):
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    orphan = client.post("/api/applications", json={"company": "Acme", "position": "Eng"}).json()["application"]
    assert orphan["status"] == "applied"  # orphan default
    store.upsert_job(Job(id="2026-060", company="Acme", company_job_id="R1", position="Eng", status="offer"))
    linked = client.post(f"/api/applications/{orphan['id']}/link", json={"job_id": "2026-060"}).json()["application"]
    assert store.get_job("2026-060").status == "offer"  # NOT downgraded to the orphan's "applied"
    assert linked["status"] == "offer"                  # app mirrors the (more-advanced) job


def test_link_idempotent_when_already_job_keyed(tmp_store):
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    store.upsert_job(Job(id="2026-061", company="Acme", company_job_id="R1", position="Eng", status="open"))
    created = client.post("/api/applications", json={"company": "Acme", "position": "Eng"}).json()["application"]
    assert created["id"] == "2026-061"  # auto-linked on create -> shares the job id
    r = client.post("/api/applications/2026-061/link", json={"job_id": "2026-061"})
    assert r.status_code == 200
    assert len(store.list_applications()) == 1            # not deleted by the self-link
    assert store.get_application("2026-061") is not None


def test_link_404s_on_bad_ids(tmp_store):
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    store.upsert_job(Job(id="2026-052", company="Gamma", company_job_id="R1", position="PM"))
    assert client.post("/api/applications/nope/link", json={"job_id": "2026-052"}).status_code == 404
    orphan = client.post("/api/applications", json={"company": "Solo", "position": "Founder"}).json()["application"]
    assert client.post(f"/api/applications/{orphan['id']}/link", json={"job_id": "ghost"}).status_code == 404


def test_patch_application_syncs_linked_job_status(tmp_store):
    from fastapi.testclient import TestClient

    from app.main import app

    store.upsert_job(Job(id="2026-001", company="Acme", company_job_id="R1", position="Engineer", status="open"))
    client = TestClient(app)
    client.post("/api/applications", json={"company": "Acme", "position": "Engineer"})  # linked, shared id
    client.patch("/api/applications/2026-001", json={"status": "interviewing"})
    assert store.get_job("2026-001").status == "interviewing"  # job kept in sync


def test_patch_job_syncs_linked_application_status(tmp_store):
    from fastapi.testclient import TestClient

    from app.main import app

    store.upsert_job(Job(id="2026-001", company="Acme", company_job_id="R1", position="Engineer", status="open"))
    client = TestClient(app)
    client.post("/api/applications", json={"company": "Acme", "position": "Engineer"})  # linked, shared id
    client.patch("/api/jobs/2026-001", json={"status": "offer"})
    assert store.get_application("2026-001").status == "offer"  # application kept in sync
    # a pre-application status is NOT pushed onto the application
    client.patch("/api/jobs/2026-001", json={"status": "open"})
    assert store.get_application("2026-001").status == "offer"  # unchanged


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
