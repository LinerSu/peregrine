"""Re-checking a tracked posting against its source board.

Two restraints carry the design and are pinned here:
  * it NEVER changes status — a board 404s for reasons that aren't "the job is gone"
    (redesign, rate limit, region redirect), and a wrongly-closed job silently drops out
    of the user's list, so closing stays a user decision;
  * it only fills BLANKS — anything already on the row was parsed once or typed by hand,
    and a refresh must not overwrite a correction.
"""
import pytest
from fastapi.testclient import TestClient

from app import config
from app import data_store as store
from app.agent import crawl_policy, providers, tools
from app.main import app
from app.schemas import Job

GREENHOUSE = "https://job-boards.greenhouse.io/acme/jobs/12345"


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "JOBS_CSV", tmp_path / "jobs.csv")
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(config, "APPLICATIONS_CSV", tmp_path / "applications.csv")
    monkeypatch.setattr(tools.status, "record", lambda *a, **k: None)
    (tmp_path / "jobs").mkdir()
    return tmp_path


def _job(**kw):
    base = dict(id="2026-001", company="Acme", company_job_id="12345", position="Engineer",
                status="open", url=GREENHOUSE)
    store.upsert_job(Job(**{**base, **kw}))


def test_fills_only_the_blanks(tmp_store, monkeypatch):
    _job(posted_date="", location="Toronto, ON")  # location already known, date missing
    monkeypatch.setattr(providers, "ingest_url", lambda url: providers.RawPosting(
        company="Acme", company_job_id="12345", position="Engineer",
        posted_date="2026-07-01", location="SOMEWHERE ELSE"))

    r = TestClient(app).post("/api/jobs/2026-001/refresh").json()
    assert r == {"checked": True, "alive": True, "filled": {"posted_date": "2026-07-01"}}
    job = store.get_job("2026-001")
    assert job.posted_date == "2026-07-01"
    assert job.location == "Toronto, ON"   # the user's value survives the refresh


def test_a_posting_the_board_no_longer_lists_is_reported_not_closed(tmp_store, monkeypatch):
    _job()
    monkeypatch.setattr(providers, "ingest_url", lambda url: None)

    r = TestClient(app).post("/api/jobs/2026-001/refresh").json()
    assert r["checked"] is True and r["alive"] is False
    assert store.get_job("2026-001").status == "open"  # the app does NOT decide this


def test_unsupported_board_is_not_evidence_of_anything(tmp_store, monkeypatch):
    # ingest_url returns None both for "no parser" and "not listed". Conflating them would
    # report every job on an unsupported board as dead.
    _job(url="https://careers.example.com/jobs/7")
    monkeypatch.setattr(crawl_policy, "check_url", lambda url: None)

    r = TestClient(app).post("/api/jobs/2026-001/refresh").json()
    assert r["checked"] is False and "no parser" in r["reason"]
    assert "alive" not in r


def test_blocked_host_reports_the_policy_reason(tmp_store, monkeypatch):
    _job(url="https://www.linkedin.com/jobs/view/12345")
    r = TestClient(app).post("/api/jobs/2026-001/refresh").json()
    assert r["checked"] is False and "linkedin" in r["reason"].lower()


def test_no_url_and_unknown_job(tmp_store):
    _job(url="")
    client = TestClient(app)
    r = client.post("/api/jobs/2026-001/refresh").json()
    assert r["checked"] is False and "no posting URL" in r["reason"]
    assert client.post("/api/jobs/nope/refresh").status_code == 404


def test_board_outage_is_not_a_dead_posting(tmp_store, monkeypatch):
    def boom(url):
        raise ConnectionError("board unreachable")

    _job()
    monkeypatch.setattr(providers, "ingest_url", boom)
    r = TestClient(app).post("/api/jobs/2026-001/refresh").json()
    assert r["checked"] is False and "couldn't reach" in r["reason"]
    assert store.get_job("2026-001").status == "open"


def test_supports_url_recognises_the_boards_we_parse():
    assert providers.supports_url(GREENHOUSE)
    assert providers.supports_url("https://jobs.apple.com/en-us/details/200123456/engineer")
    assert providers.supports_url("https://www.amazon.jobs/en/jobs/1234567/engineer")
    assert not providers.supports_url("https://careers.example.com/jobs/7")
