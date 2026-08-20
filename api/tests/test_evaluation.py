"""Structured evaluation v2: legitimacy (ghost-job) signals + role archetype."""
from datetime import date

import pytest

from app.evaluation import assess_legitimacy, classify_archetype
from app.schemas import Job

TODAY = date(2026, 6, 21)
LONG = "We are hiring an engineer to build and own our payments platform end to end. " * 5


def _job(**kw):
    base = dict(id="2026-001", company="Acme", company_job_id="R1", position="Engineer")
    base.update(kw)
    return Job(**base)


def test_clean_posting_scores_full():
    j = _job(salary_min=120000, salary_max=160000, posted_date="2026-06-10")
    out = assess_legitimacy(j, LONG, today=TODAY)
    assert out["legitimacy_score"] == 1.0
    assert out["legitimacy_flags"] == []


def test_no_salary_and_sparse_are_flagged():
    out = assess_legitimacy(_job(), "Short.", today=TODAY)
    assert "No salary range disclosed" in out["legitimacy_flags"]
    assert "Sparse description" in out["legitimacy_flags"]
    assert out["legitimacy_score"] < 1.0


def test_evergreen_and_agency_language_flagged():
    j = _job(salary_min=120000, salary_max=160000)
    desc = LONG + " We are always hiring for our talent pool on behalf of our client."
    flags = assess_legitimacy(j, desc, today=TODAY)["legitimacy_flags"]
    assert any("Evergreen" in f for f in flags)
    assert any("agency" in f.lower() for f in flags)


@pytest.mark.parametrize("phrase", [
    "We post future opportunities here.",
    "Apply for a future opportunity with us.",
    "Join our talent pool for future openings.",
    "This is a general application for our hiring pipeline.",
])
def test_evergreen_phrases_are_flagged(phrase):
    j = _job(salary_min=120000, salary_max=160000)
    flags = assess_legitimacy(j, LONG + " " + phrase, today=TODAY)["legitimacy_flags"]
    assert any("Evergreen" in f for f in flags), phrase


def test_staleness_requires_today():
    j = _job(salary_min=120000, salary_max=160000, posted_date="2026-01-01")
    assert any("Stale" in f for f in assess_legitimacy(j, LONG, today=TODAY)["legitimacy_flags"])
    # Without `today` the function stays pure — no clock, no staleness flag.
    assert not any("Stale" in f for f in assess_legitimacy(j, LONG)["legitimacy_flags"])


def test_score_is_floored_at_zero():
    j = _job()  # no salary
    desc = "rockstar ninja; we are always hiring for our talent pool on behalf of our client"
    assert assess_legitimacy(j, desc, today=TODAY)["legitimacy_score"] >= 0.0


@pytest.mark.parametrize("position,expected", [
    ("Engineering Manager", "Leadership / Manager"),
    ("Head of Design", "Leadership / Manager"),
    ("Research Scientist", "Research"),
    ("ML Platform Engineer", "Platform / Infrastructure"),
    ("Machine Learning Engineer", "Builder / IC"),
    ("Process Chemist", "Builder / IC"),
    ("Quantum Strategist", "Specialist"),
])
def test_archetype_classification(position, expected):
    assert classify_archetype(position) == expected


def test_archetype_title_beats_description_noise():
    # "partner with research" in the body must not relabel an engineering role.
    assert classify_archetype(
        "Machine Learning Engineer", "You'll partner with research to ship models."
    ) == "Builder / IC"
    # A title with no archetype keyword still falls back to the description.
    assert classify_archetype("Member of Technical Staff", "deep research role") == "Research"


def test_save_evaluation_adds_v2_blocks(tmp_path, monkeypatch):
    from app import config
    from app import data_store as store
    from app.agent import tools

    monkeypatch.setattr(config, "JOBS_CSV", tmp_path / "jobs.csv")
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(config, "APPLICATIONS_CSV", tmp_path / "applications.csv")

    store.upsert_job(Job(id="2026-001", company="Acme", company_job_id="R1",
                         position="ML Platform Engineer"))
    store.write_job_md("2026-001", "# ML Platform Engineer — Acme\n\n## Posting\n"
                       "Build and own the internal ML platform tooling and pipelines.")

    ev = tools.save_evaluation("2026-001", {
        "fit_score": 0.8, "recommendation": "apply",
        "strengths": ["infra depth"], "weaknesses": [], "materials": [],
    }, today=TODAY)
    # Computed server-side, regardless of the (absent) client values.
    assert ev["archetype"] == "Platform / Infrastructure"
    assert ev["legitimacy_score"] is not None

    side = store.read_evaluation("2026-001")
    assert side and side["archetype"] == "Platform / Infrastructure"
    md = store.read_job_md("2026-001")
    assert "**archetype:**" in md and "**legitimacy:**" in md


def test_save_evaluation_staleness_uses_injected_today(tmp_path, monkeypatch):
    from app import config
    from app import data_store as store
    from app.agent import tools

    monkeypatch.setattr(config, "JOBS_CSV", tmp_path / "jobs.csv")
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(config, "APPLICATIONS_CSV", tmp_path / "applications.csv")

    store.upsert_job(Job(id="2026-002", company="Acme", company_job_id="R2",
                         position="Engineer", salary_min=120000, salary_max=160000,
                         posted_date="2026-01-01"))
    store.write_job_md("2026-002", "# Engineer — Acme\n\n## Posting\n" + LONG)
    ev = tools.save_evaluation("2026-002", {"fit_score": 0.7}, today=TODAY)
    assert any("Stale" in f for f in ev["legitimacy_flags"])
