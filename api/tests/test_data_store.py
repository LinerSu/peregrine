"""Data store round-trips + dedup, against a temp CSV directory."""
from datetime import date

import pytest

from app import config
from app import data_store as store
from app.schemas import Application, Job


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "JOBS_CSV", tmp_path / "jobs.csv")
    monkeypatch.setattr(config, "APPLICATIONS_CSV", tmp_path / "applications.csv")
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path / "jobs")
    return store


def test_job_roundtrip_and_dedup(tmp_store):
    yr = date.today().year
    assert tmp_store.list_jobs() == []

    tmp_store.upsert_job(Job(id=f"{yr}-001", company="Acme", company_job_id="R1", position="Eng"))
    jobs = tmp_store.list_jobs()
    assert len(jobs) == 1 and jobs[0].company == "Acme"

    # dedup key is company + company_job_id, case-insensitive
    assert tmp_store.find_job_by_key("acme", "r1").id == f"{yr}-001"
    assert tmp_store.find_job_by_key("acme", "nope") is None
    # next surrogate id increments within the year
    assert tmp_store.next_job_id() == f"{yr}-002"


def test_application_roundtrip(tmp_store):
    tmp_store.upsert_application(
        Application(id="2026-001", company="Acme", company_job_id="R1", position="Eng", notes="call went well")
    )
    apps = tmp_store.list_applications()
    assert len(apps) == 1 and apps[0].notes == "call went well"
    assert tmp_store.get_application("2026-001").company == "Acme"
    assert tmp_store.get_application("missing") is None


def test_targets_roundtrip(tmp_store, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROFILE_YML", tmp_path / "profile.yml")
    tmp_store.write_targets({"roles": ["Backend"], "work_mode": "remote"})
    assert tmp_store.read_targets() == {"roles": ["Backend"], "work_mode": "remote"}
