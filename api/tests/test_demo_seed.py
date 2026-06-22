"""Demo persona seeding: every persona produces a valid, populated dataset."""
import math

import pytest

from app import config
from app import data_store as store
from app import demo_seed

EXPECTED = {"ai-engineer", "ux-designer", "chem-phd", "bio-scientist", "law-student"}


@pytest.fixture
def tmp_dataset(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "JOBS_CSV", tmp_path / "jobs.csv")
    monkeypatch.setattr(config, "APPLICATIONS_CSV", tmp_path / "applications.csv")
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(config, "PROFILE_YML", tmp_path / "profile.yml")
    return tmp_path


def test_persona_set():
    assert set(demo_seed.PERSONAS) == EXPECTED
    assert demo_seed.list_personas() == sorted(EXPECTED)


@pytest.mark.parametrize("dataset", sorted(EXPECTED))
def test_persona_seeds_valid_dataset(tmp_dataset, dataset):
    demo_seed.seed(dataset)

    # Profile is populated.
    profile = store.read_profile()
    assert profile.get("name")
    assert profile.get("skills")

    # Jobs load and parse back through the schema.
    jobs = store.list_jobs()
    assert len(jobs) >= 3

    # At least one evaluated job, with a finite fit, saved upskilling, and an
    # evaluation block written into its markdown.
    evaluated = [j for j in jobs if j.fit_score is not None]
    assert evaluated, f"{dataset}: expected an evaluated job"
    assert all(math.isfinite(j.fit_score) for j in evaluated)
    top = evaluated[0]
    assert store.read_upskilling(top.id) is not None
    # Heading must match the app's evaluation updater so re-evaluation replaces it.
    assert "## Agent evaluation" in store.read_job_md(top.id)
    # v2: a structured evaluation sidecar with the computed legitimacy + archetype.
    ev = store.read_evaluation(top.id)
    assert ev and ev.get("archetype")
    assert ev.get("legitimacy_score") is not None

    # At least one application, each with an applied date (so Insights populates).
    apps = store.list_applications()
    assert apps, f"{dataset}: expected an application"
    assert all(a.applied_date for a in apps)


def test_reseeding_does_not_duplicate(tmp_dataset):
    demo_seed.seed("ai-engineer")
    n_jobs, n_apps = len(store.list_jobs()), len(store.list_applications())
    demo_seed.seed("ai-engineer")  # upsert by id — should not grow
    assert len(store.list_jobs()) == n_jobs
    assert len(store.list_applications()) == n_apps
