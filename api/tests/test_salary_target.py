"""The minimum-salary target: a preference that finally does something.

`targets.min_salary` was collected by the Search tab, written to profile.yml, and then read
by nothing at all — the worst shape a setting can take, because the user has no way to tell
a floor that is being applied from one that is being ignored. It stayed dead for a real
reason: `providers.RawPosting` carries no compensation, so a gate in `_passes_filters` would
have filtered exactly nothing while looking like it worked.

Design rules pinned here:
  * the floor is judged at SERVE time, off `Job.salary_min` (populated for pasted and
    ingested postings), and shipped as `below_min_salary` on every listed job — the same
    derived-flag shape as `relevant` and `skill_fit`;
  * a posting that states no salary is NEVER flagged: we can't price what the posting never
    priced, the same restraint `_too_old` shows for undated postings. Marking those would
    punish the most common case (boards rarely publish comp) and teach the user to ignore
    the flag;
  * it is a flag, never a filter. `list_jobs` returns the same rows either way, so the UI
    can de-emphasise; a job under your floor may still be worth a look, and silently
    dropping rows is how a preference becomes a trap;
  * the floor is read from the user's profile, so a hand-edited garbage value must read as
    "no floor" rather than 500 the Jobs page;
  * these assertions drive `GET /api/jobs`, not the helper — a flag computed correctly in
    `tools` but never serialized onto the response is exactly the bug this replaces.

`ScanFilters.min_base` — a second, differently-named salary field read by nothing — is gone,
and that is pinned too, so it can't drift back as a scan filter nobody applies.
"""
import pytest
from fastapi.testclient import TestClient

from app import config
from app import data_store as store
from app.main import app
from app.schemas import Job, ScanFilters


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "JOBS_CSV", tmp_path / "jobs.csv")
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(config, "APPLICATIONS_CSV", tmp_path / "applications.csv")
    monkeypatch.setattr(config, "PROFILE_YML", tmp_path / "profile.yml")
    # The runner's real portals.yml must not leak in: its queries decide `relevant`, and a
    # job filtered out of the fixture by someone else's search terms would fake a pass here.
    monkeypatch.setattr(config, "PORTALS_YML", tmp_path / "portals.yml")
    (tmp_path / "jobs").mkdir()
    from app.agent import tools

    monkeypatch.setattr(tools.status, "record", lambda *a, **k: None)
    return store


def _job(id: str, salary_min: float | None = None) -> Job:
    return Job(id=id, company="Acme", company_job_id=f"R{id[-1]}", position="Engineer",
               salary_min=salary_min)


def _listed(client: TestClient) -> dict[str, dict]:
    return {j["id"]: j for j in client.get("/api/jobs").json()["jobs"]}


def test_jobs_endpoint_flags_a_stated_salary_under_the_target(tmp_store):
    tmp_store.write_targets({"min_salary": 140000})
    tmp_store.upsert_job(_job("2026-001", salary_min=90000))   # under the floor
    tmp_store.upsert_job(_job("2026-002", salary_min=180000))  # over it

    jobs = _listed(TestClient(app))
    assert jobs["2026-001"]["below_min_salary"] is True
    assert jobs["2026-002"]["below_min_salary"] is False


def test_a_posting_that_states_no_salary_is_never_flagged(tmp_store):
    # Most boards publish no compensation at all. "Unknown" must not read as "too low", or
    # the flag means nothing and the user learns to ignore it.
    tmp_store.write_targets({"min_salary": 140000})
    tmp_store.upsert_job(_job("2026-001", salary_min=None))

    assert _listed(TestClient(app))["2026-001"]["below_min_salary"] is False


def test_a_salary_exactly_at_the_target_is_not_under_it(tmp_store):
    # The floor is a minimum you'd accept, not one you must beat — pinned deliberately.
    tmp_store.write_targets({"min_salary": 140000})
    tmp_store.upsert_job(_job("2026-001", salary_min=140000))

    assert _listed(TestClient(app))["2026-001"]["below_min_salary"] is False


def test_no_salary_target_flags_nothing(tmp_store):
    # A user who never set a floor has nothing to be under.
    tmp_store.upsert_job(_job("2026-001", salary_min=1))
    assert _listed(TestClient(app))["2026-001"]["below_min_salary"] is False

    tmp_store.write_targets({"min_salary": 0})
    assert _listed(TestClient(app))["2026-001"]["below_min_salary"] is False


def test_the_salary_flag_must_not_drop_a_row_from_the_list(tmp_store):
    # The whole point of the derived-flag shape: the UI de-emphasises, the API still serves
    # it. A hidden job is a job the user can't reconsider, negotiate, or even find.
    tmp_store.write_targets({"min_salary": 140000})
    for i, pay in enumerate([1000, 90000, None, 400000], start=1):
        tmp_store.upsert_job(_job(f"2026-00{i}", salary_min=pay))

    body = TestClient(app).get("/api/jobs").json()
    assert body["count"] == 4
    assert sorted(j["id"] for j in body["jobs"]) == [
        "2026-001", "2026-002", "2026-003", "2026-004"]


def test_a_malformed_min_salary_target_reads_as_no_floor(tmp_store):
    # profile.yml is hand-editable, and PUT /api/preferences accepts a partial dict — a bad
    # value must never 500 the Jobs page, which is the one page you can't work around.
    tmp_store.write_targets({"min_salary": "a lot"})
    tmp_store.upsert_job(_job("2026-001", salary_min=1))

    r = TestClient(app).get("/api/jobs")
    assert r.status_code == 200
    assert r.json()["jobs"][0]["below_min_salary"] is False


def test_scan_filters_carry_no_dead_salary_field():
    # min_base was a portals-level salary floor read by nothing whatsoever — a second name
    # for a preference that already had one. Deleted; it must not come back as a scan filter,
    # because RawPosting still carries no compensation for it to filter on.
    assert "min_base" not in ScanFilters.model_fields
