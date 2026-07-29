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


def test_contacts_sync_between_job_and_application(tmp_store):
    """User-entered people (a JSON list of contacts) stay consistent across a linked
    job + application, whichever side you edit from."""
    from fastapi.testclient import TestClient

    from app.main import app

    store.upsert_job(Job(id="2026-010", company="Acme", company_job_id="R9", position="Eng", status="open"))
    client = TestClient(app)
    client.post("/api/applications", json={"company": "Acme", "position": "Eng"})  # linked app (shares id)

    # set people on the JOB -> syncs to the application (often just a recruiter name + email)
    p1 = '[{"name": "Jane R", "role": "recruiter", "link": "jane@example.com"}]'
    client.patch("/api/jobs/2026-010", json={"people": p1})
    assert store.get_application("2026-010").people == p1

    # edit people on the APPLICATION -> syncs to the job
    p2 = '[{"name": "Bob M", "role": "hiring manager", "link": ""}]'
    client.patch("/api/applications/2026-010", json={"people": p2})
    assert store.get_job("2026-010").people == p2

def test_ingesting_a_posting_adopts_a_hand_recorded_application(tmp_store):
    """Applying first and tracking the posting after is the normal order — the job must
    not land "open" with a prepare-to-apply button for a job already applied to."""
    from fastapi.testclient import TestClient

    from app.agent import tools
    from app.main import app

    client = TestClient(app)
    created = client.post("/api/applications", json={
        "company": "Acme", "position": "Engineer", "applied_date": "2026-07-01",
        "url": "https://example.com/jobs/r-1", "notes": "referred by a friend",
    }).json()
    assert created["job_tracked"] is False  # orphan: no posting tracked yet

    saved = tools.save_ingested_job({"company": "Acme", "position": "Engineer",
                                     "url": "https://example.com/jobs/r-1",
                                     "description": "build things"})
    job_id = saved["job"]["id"]

    apps = client.get("/api/applications").json()["applications"]
    assert [a["id"] for a in apps] == [job_id]          # re-keyed onto the job, orphan gone
    assert apps[0]["applied_date"] == "2026-07-01"      # tracker fields survive
    assert apps[0]["notes"] == "referred by a friend"
    assert store.get_job(job_id).status == "applied"    # job no longer offers "apply"


def test_adoption_matches_on_url_even_when_the_title_differs(tmp_store):
    # The same posting can be recorded under a shortened title; the link is the identity.
    from fastapi.testclient import TestClient

    from app.agent import tools
    from app.main import app

    client = TestClient(app)
    client.post("/api/applications", json={
        "company": "Acme", "position": "Engineer 3", "url": "https://example.com/jobs/r-9",
    })
    saved = tools.save_ingested_job({"company": "Acme", "position": "Engineer 3 (C++/Rust)",
                                     "url": "https://example.com/jobs/r-9", "description": "x"})
    apps = client.get("/api/applications").json()["applications"]
    assert [a["id"] for a in apps] == [saved["job"]["id"]]


def test_adoption_refuses_to_guess_between_two_candidates(tmp_store):
    from fastapi.testclient import TestClient

    from app.agent import tools
    from app.main import app

    client = TestClient(app)
    for i in (1, 2):
        client.post("/api/applications", json={"company": "Acme", "position": "Engineer",
                                               "applied_date": f"2026-07-0{i}"})
    saved = tools.save_ingested_job({"company": "Acme", "position": "Engineer", "description": "x"})
    apps = client.get("/api/applications").json()["applications"]
    assert len(apps) == 2                                    # both left alone
    assert store.get_job(saved["job"]["id"]).status == "open"  # nothing guessed


def test_scan_adopts_a_hand_recorded_application(tmp_store, monkeypatch):
    """The other real order: applied on the company's own site, and a later scan is what
    brings the posting in. Same guarantee as ingest — the row must not read "open"."""
    from fastapi.testclient import TestClient

    from app.agent import providers, tools
    from app.main import app

    client = TestClient(app)
    client.post("/api/applications", json={"company": "Acme", "position": "Engineer",
                                           "applied_date": "2026-07-02"})
    monkeypatch.setattr(store, "read_portals", lambda: {
        "companies": [{"provider": "x", "name": "Acme"}], "filters": {}, "snapshot": False})
    monkeypatch.setattr(store, "read_targets", lambda: {})
    monkeypatch.setattr(providers, "fetch", lambda *a, **k: [
        providers.RawPosting(company="Acme", company_job_id="r1", position="Engineer")])

    assert tools.scan_jobs()["new"] == 1
    job = store.list_jobs()[0]
    assert job.status == "applied"
    apps = client.get("/api/applications").json()["applications"]
    assert [a["id"] for a in apps] == [job.id] and apps[0]["applied_date"] == "2026-07-02"


def test_create_by_job_id_beats_an_ambiguous_title(tmp_store):
    """The picker's whole point: two postings can share a company AND a title, which is
    exactly when matching gives up. Choosing the row says which one, unambiguously."""
    from fastapi.testclient import TestClient

    from app.main import app

    for jid, loc in (("2026-001", "Beaverton, OR"), ("2026-002", "Seattle, WA")):
        store.upsert_job(Job(id=jid, company="Acme", company_job_id=f"R{jid[-1]}",
                             position="Engineer", location=loc, status="open"))
    # Matching alone can't choose (same company + title, no location given).
    assert store.find_job_for_posting("Acme", "Engineer") is None

    r = TestClient(app).post("/api/applications", json={"job_id": "2026-002",
                                                        "applied_date": "2026-07-05"})
    assert r.status_code == 200 and r.json()["job_tracked"] is True
    assert r.json()["application"]["id"] == "2026-002"
    assert r.json()["application"]["location"] == "Seattle, WA"   # posting fields carried
    assert store.get_job("2026-002").status == "applied"
    assert store.get_job("2026-001").status == "open"             # the other one untouched


def test_create_by_job_id_honours_the_chosen_status(tmp_store):
    # Logging something already in flight must not silently become "applied".
    from fastapi.testclient import TestClient

    from app.main import app

    store.upsert_job(Job(id="2026-001", company="Acme", company_job_id="R1", position="Engineer"))
    r = TestClient(app).post("/api/applications", json={"job_id": "2026-001", "status": "interviewing"})
    assert r.json()["application"]["status"] == "interviewing"
    assert store.get_job("2026-001").status == "interviewing"     # job and app move together


def test_create_by_unknown_job_id_is_404(tmp_store):
    from fastapi.testclient import TestClient

    from app.main import app

    assert TestClient(app).post("/api/applications", json={"job_id": "nope"}).status_code == 404
    assert store.list_applications() == []


def test_url_match_refuses_to_guess_between_duplicate_rows():
    # The same posting tracked twice under one link (listed in two cities) must not be
    # resolved by row order — fall through to the requisition key, which does separate them.
    jobs = [
        Job(id="1", company="Acme", company_job_id="R1", position="Engineer",
            location="NYC", url="https://example.com/jobs/r-1"),
        Job(id="2", company="Acme", company_job_id="R2", position="Engineer",
            location="SF", url="https://example.com/jobs/r-1"),
    ]
    assert store.match_job(jobs, "Acme", "Engineer", "", "", "https://example.com/jobs/r-1") is None
    assert store.match_job(jobs, "Acme", "Engineer", "R2", "", "https://example.com/jobs/r-1").id == "2"

