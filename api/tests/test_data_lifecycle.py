"""Job deletion, retention purge, and CV-staleness flags.

Design rules pinned here:
  * deleting a job removes its row AND every `<id>.*` artifact — but NEVER while a
    linked application exists (application history must not vanish as a side effect);
  * the purge is conservative: closed-only, skips linked apps, skips unparseable dates;
  * analysis artifacts (evaluation, cover letter) report `stale: true` when they
    predate the current profile (built against a PREVIOUS CV);
  * tailored CVs are deliberately NOT staleness-flagged — their invalidation story is
    on hold pending its own design (explicit user decision 2026-07-27).
"""
import os
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import config
from app import data_store as store
from app.main import app
from app.schemas import Application, Job, ScanFilters


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "JOBS_CSV", tmp_path / "jobs.csv")
    monkeypatch.setattr(config, "APPLICATIONS_CSV", tmp_path / "applications.csv")
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(config, "PROFILE_YML", tmp_path / "profile.yml")
    (tmp_path / "jobs").mkdir()
    return store


def _job(id: str, status: str = "open", posted: str = "") -> Job:
    return Job(id=id, company="Acme", company_job_id=f"R{id[-1]}", position="Eng",
               status=status, posted_date=posted)


# --- store.delete_job -----------------------------------------------------------------

def test_delete_job_removes_row_and_artifacts(tmp_store):
    tmp_store.upsert_job(_job("2026-001"))
    tmp_store.upsert_job(_job("2026-002"))
    for name in ("2026-001.md", "2026-001.evaluation.json", "2026-001.cover_letter.md",
                 "2026-001.cv.tex", "2026-0011.md"):  # last one: PREFIX collision, must survive
        (config.JOBS_DIR / name).write_text("x")

    assert tmp_store.delete_job("2026-001") is True
    assert [j.id for j in tmp_store.list_jobs()] == ["2026-002"]
    left = sorted(p.name for p in config.JOBS_DIR.iterdir())
    assert left == ["2026-0011.md"], "only the exact <id>.* family may be removed"


def test_delete_job_unknown_returns_false(tmp_store):
    assert tmp_store.delete_job("2026-999") is False


# --- store.purge_closed_jobs ----------------------------------------------------------

def test_purge_is_conservative(tmp_store):
    today = date(2026, 7, 27)
    tmp_store.upsert_job(_job("2026-001", "closed", "2025-01-01"))   # old + closed -> purged
    tmp_store.upsert_job(_job("2026-002", "closed", "2026-07-01"))   # closed but recent -> kept
    tmp_store.upsert_job(_job("2026-003", "open", "2025-01-01"))     # old but OPEN -> kept
    tmp_store.upsert_job(_job("2026-004", "closed", "2025-01-01"))   # old closed + APP -> kept
    tmp_store.upsert_job(_job("2026-005", "closed", ""))             # closed, no date -> kept
    tmp_store.upsert_application(Application(id="2026-004", company="Acme",
                                             company_job_id="R4", position="Eng"))

    out = tmp_store.purge_closed_jobs(180, today=today)
    assert out == {"deleted": 1, "skipped_linked": 1, "skipped_undated": 1}
    assert sorted(j.id for j in tmp_store.list_jobs()) == [
        "2026-002", "2026-003", "2026-004", "2026-005"]


# --- API endpoints --------------------------------------------------------------------

def test_delete_endpoint_guards_and_deletes(tmp_store):
    c = TestClient(app)
    assert c.delete("/api/jobs/2026-404").status_code == 404

    tmp_store.upsert_job(_job("2026-001"))
    tmp_store.upsert_application(Application(id="2026-001", company="Acme",
                                             company_job_id="R1", position="Eng"))
    r = c.delete("/api/jobs/2026-001")
    assert r.status_code == 409, "a linked application must block deletion"
    assert "application" in r.json()["detail"].lower()

    tmp_store.delete_application("2026-001")
    assert c.delete("/api/jobs/2026-001").status_code == 200
    assert tmp_store.get_job("2026-001") is None


def test_purge_endpoint_validates_and_reports(tmp_store):
    c = TestClient(app)
    assert c.post("/api/jobs/purge", json={"older_than_days": 0}).status_code == 422
    tmp_store.upsert_job(_job("2026-001", "closed", "2000-01-01"))
    r = c.post("/api/jobs/purge", json={"older_than_days": 180})
    assert r.status_code == 200 and r.json()["deleted"] == 1


def test_scan_filters_accept_retention_days():
    assert ScanFilters(retention_days=180).retention_days == 180
    assert ScanFilters().retention_days == 0  # default off


# --- staleness flags ------------------------------------------------------------------

def _age(path, seconds_back: int):
    t = os.stat(path).st_mtime - seconds_back
    os.utime(path, (t, t))


def test_evaluation_and_cover_stale_when_profile_is_newer(tmp_store):
    c = TestClient(app)
    tmp_store.upsert_job(_job("2026-001"))
    c.put("/api/jobs/2026-001/evaluation", json={"fit_score": 0.8})
    c.put("/api/jobs/2026-001/cover-letter", json={"content": "Dear team"})

    # artifacts newer than the profile -> current
    config.PROFILE_YML.write_text("name: someone\n")
    _age(config.PROFILE_YML, 1000)
    assert c.get("/api/jobs/2026-001/evaluation").json()["stale"] is False
    assert c.get("/api/jobs/2026-001/cover-letter").json()["stale"] is False

    # profile re-parsed AFTER the artifacts -> both flagged as built on the old CV
    _age(config.JOBS_DIR / "2026-001.evaluation.json", 5000)
    _age(config.JOBS_DIR / "2026-001.cover_letter.md", 5000)
    assert c.get("/api/jobs/2026-001/evaluation").json()["stale"] is True
    assert c.get("/api/jobs/2026-001/cover-letter").json()["stale"] is True


def test_empty_responses_carry_no_stale_key(tmp_store):
    # "{} means no artifact yet" is load-bearing for the UI polling — the flag must
    # only ever ride on a non-empty payload.
    c = TestClient(app)
    tmp_store.upsert_job(_job("2026-001"))
    assert c.get("/api/jobs/2026-001/evaluation").json() == {}
    assert c.get("/api/jobs/2026-001/cover-letter").json() == {}


def test_tailored_cv_is_not_staleness_flagged(tmp_store):
    # ON HOLD by explicit user decision: tailored-CV invalidation needs its own design.
    # This pins that nobody extends the flag to the CV endpoint in passing.
    c = TestClient(app)
    tmp_store.upsert_job(_job("2026-001"))
    (config.JOBS_DIR / "2026-001.cv.tex").write_text("\\documentclass{article}")
    config.PROFILE_YML.write_text("name: someone\n")
    body = c.get("/api/jobs/2026-001/cv").json()
    assert "stale" not in body
