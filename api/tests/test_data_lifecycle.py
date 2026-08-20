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
    monkeypatch.setattr(config, "APPLICATIONS_DIR", tmp_path / "applications")
    monkeypatch.setattr(config, "PROFILE_YML", tmp_path / "profile.yml")
    (tmp_path / "jobs").mkdir()
    return store


def _stamp_profile(when: float) -> None:
    """Write a profile whose cv_parsed_at stamp is `when` (epoch seconds)."""
    config.PROFILE_YML.write_text(f"name: someone\ncv_parsed_at: {when}\n")


def _job(id: str, status: str = "open", posted: str = "") -> Job:
    return Job(id=id, company="Acme", company_job_id=f"R{id[-1]}", position="Eng",
               status=status, posted_date=posted)


# --- store.delete_job -----------------------------------------------------------------

def test_delete_job_removes_row_artifacts_and_materials_mirror(tmp_store):
    tmp_store.upsert_job(_job("2026-001"))
    tmp_store.upsert_job(_job("2026-002"))
    for name in ("2026-001.md", "2026-001.evaluation.json", "2026-001.cover_letter.md",
                 "2026-001.cv.tex", "2026-0011.md"):  # last one: PREFIX collision, must survive
        (config.JOBS_DIR / name).write_text("x")
    # the applications/<id>/ materials mirror must go too — a later job REUSING the
    # id (ids are minted sequentially) must not inherit the old job's materials
    mirror = config.APPLICATIONS_DIR / "2026-001"
    mirror.mkdir(parents=True)
    (mirror / "cover_letter.md").write_text("old")

    assert tmp_store.delete_job("2026-001") is True
    assert [j.id for j in tmp_store.list_jobs()] == ["2026-002"]
    left = sorted(p.name for p in config.JOBS_DIR.iterdir())
    assert left == ["2026-0011.md"], "only the exact <id>.* family may be removed"
    assert not mirror.exists()


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


def test_purge_refuses_zero_and_negative_windows(tmp_store):
    # A negative window flips the cutoff into the FUTURE — it must never delete.
    tmp_store.upsert_job(_job("2026-001", "closed", "2026-07-26"))
    for bad in (0, -1, -180):
        assert tmp_store.purge_closed_jobs(bad) == {
            "deleted": 0, "skipped_linked": 0, "skipped_undated": 0}
    assert len(tmp_store.list_jobs()) == 1


def test_purge_rewrites_the_jobs_csv_once_for_the_whole_batch(tmp_store, monkeypatch):
    # It used to call delete_job per doomed row, and each of those re-read and rewrote the
    # ENTIRE csv — quadratic, on the path that runs at the end of every scan, over exactly
    # the rows that pile up across months of scanning. The decision is now one pass and the
    # rewrite is one write; the artifacts still go per job, so this also pins that batching
    # the rows didn't quietly leave the sidecars and materials mirrors behind.
    today = date(2026, 7, 27)
    for n in range(1, 6):
        tmp_store.upsert_job(_job(f"2026-00{n}", "closed", "2025-01-01"))
        (config.JOBS_DIR / f"2026-00{n}.md").write_text("posting")
        (config.APPLICATIONS_DIR / f"2026-00{n}").mkdir(parents=True)

    writes: list = []
    real_write = tmp_store._write_csv

    def counting_write(path, fields, rows):
        writes.append(path)
        return real_write(path, fields, rows)

    monkeypatch.setattr(tmp_store, "_write_csv", counting_write)

    assert tmp_store.purge_closed_jobs(180, today=today)["deleted"] == 5
    assert writes.count(config.JOBS_CSV) == 1, "one purge, one rewrite — not one per row"
    assert tmp_store.list_jobs() == []
    assert list(config.JOBS_DIR.iterdir()) == [], "every purged job's artifacts go too"
    assert not (config.APPLICATIONS_DIR / "2026-003").exists(), "and its materials mirror"


def test_purge_boundary_exactly_n_days_old_is_deleted(tmp_store):
    # posted exactly N days before today: cutoff comparison is `posted > cutoff` to
    # KEEP, so the exact boundary falls on the delete side — pinned deliberately.
    today = date(2026, 7, 27)
    tmp_store.upsert_job(_job("2026-001", "closed", "2026-01-28"))  # exactly 180 days
    assert tmp_store.purge_closed_jobs(180, today=today)["deleted"] == 1


def test_scan_applies_retention_only_when_positive(tmp_store, monkeypatch):
    from app.agent import tools

    monkeypatch.setattr(tools.status, "record", lambda *a, **k: None)
    monkeypatch.setattr(tmp_store, "read_targets", lambda: {}, raising=False)
    old = _job("2026-001", "closed", "2000-01-01")

    for retention, expect_left in ((-180, 1), (0, 1), (30, 0)):
        tmp_store.upsert_job(old)
        monkeypatch.setattr(
            tmp_store, "read_portals",
            lambda r=retention: {"companies": [], "filters": {"retention_days": r}},
            raising=False,
        )
        summary = tools.scan_jobs()
        assert len(tmp_store.list_jobs()) == expect_left, f"retention={retention}"
        assert summary["purged"] == (1 if retention == 30 else 0)


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

def test_evaluation_and_cover_stale_track_the_cv_parse_stamp(tmp_store):
    import time as _time

    c = TestClient(app)
    tmp_store.upsert_job(_job("2026-001"))
    c.put("/api/jobs/2026-001/evaluation", json={"fit_score": 0.8})
    c.put("/api/jobs/2026-001/cover-letter", json={"content": "Dear team"})
    now = _time.time()

    # no profile / no cv_parsed_at stamp yet -> nothing is stale (fail-safe)
    assert c.get("/api/jobs/2026-001/evaluation").json()["stale"] is False
    config.PROFILE_YML.write_text("name: someone\n")
    assert c.get("/api/jobs/2026-001/evaluation").json()["stale"] is False
    assert c.get("/api/jobs/2026-001/cover-letter").json()["stale"] is False

    # CV parsed BEFORE the artifacts were made -> current
    _stamp_profile(now - 5000)
    assert c.get("/api/jobs/2026-001/evaluation").json()["stale"] is False
    assert c.get("/api/jobs/2026-001/cover-letter").json()["stale"] is False

    # CV re-parsed AFTER the artifacts -> both flagged as built on the old CV,
    # and the LIST nulls the now-meaningless fit score
    _stamp_profile(now + 5000)
    assert c.get("/api/jobs/2026-001/evaluation").json()["stale"] is True
    assert c.get("/api/jobs/2026-001/cover-letter").json()["stale"] is True
    listed = c.get("/api/jobs").json()["jobs"][0]
    assert listed["fit_score"] is None


def test_preferences_save_must_not_flag_staleness(tmp_store):
    # REGRESSION PIN: profile.yml is ALSO rewritten by preferences saves
    # (write_targets). Only a CV re-parse moves the stamp — a routine keyword tweak
    # must never hide every evaluation in the app behind a false "previous CV" banner.
    import time as _time

    c = TestClient(app)
    tmp_store.upsert_job(_job("2026-001"))
    c.put("/api/jobs/2026-001/evaluation", json={"fit_score": 0.8})
    _stamp_profile(_time.time() - 5000)  # CV parsed before the artifact -> current
    assert c.get("/api/jobs/2026-001/evaluation").json()["stale"] is False

    tmp_store.write_targets({"roles": ["ML Engineer"]})  # the preferences-save path
    assert c.get("/api/jobs/2026-001/evaluation").json()["stale"] is False
    assert tmp_store.read_profile().get("cv_parsed_at") is not None, "stamp must survive"


def test_cv_intake_paths_move_the_stamp(tmp_store):
    # Internal-mode store-only save is one of exactly two flows allowed to move it.
    from app.agent import tools

    tools.save_profile({"name": "someone"})
    assert tmp_store.read_profile().get("cv_parsed_at") is not None


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
