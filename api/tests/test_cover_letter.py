"""Cover-letter generation: style references, store-only save, and the mock path."""
import pytest

from app import config
from app import data_store as store
from app.cover_letter import gather_style_references
from app.schemas import Job


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    from app.agent import tools

    monkeypatch.setattr(config, "JOBS_CSV", tmp_path / "jobs.csv")
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(config, "APPLICATIONS_CSV", tmp_path / "applications.csv")
    monkeypatch.setattr(config, "PROFILE_YML", tmp_path / "profile.yml")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)  # user samples dir lives here
    monkeypatch.setattr(tools.status, "record", lambda *a, **k: None)  # no real log writes
    return tmp_path


def test_gather_includes_curated_samples(tmp_store):
    refs = gather_style_references()  # curated ship in the package; no user samples here
    assert "Sample: engineering" in refs
    assert "Sample: research" in refs
    assert "do NOT copy" in refs  # the guardrail header is present


def test_gather_includes_user_samples(tmp_store):
    d = tmp_store / "cover_letter_samples"
    d.mkdir()
    (d / "mine.md").write_text("My own letter style, kept local.", encoding="utf-8")
    assert "Sample: mine" in gather_style_references()


def test_save_and_get_cover_letter(tmp_store):
    from app.agent import tools

    store.upsert_job(Job(id="2026-001", company="Acme", company_job_id="R1", position="Engineer"))
    assert tools.get_cover_letter("2026-001") is None  # none yet

    res = tools.save_cover_letter("2026-001", "Dear Acme team, ...")
    assert res["content"] == "Dear Acme team, ..."
    assert store.read_cover_letter("2026-001") == "Dear Acme team, ..."
    assert tools.get_cover_letter("2026-001")["content"] == "Dear Acme team, ..."


def test_save_cover_letter_unknown_job_errors(tmp_store):
    from app.agent import tools

    assert "error" in tools.save_cover_letter("nope", "x")


def test_generate_cover_letter_mock_path(tmp_store):
    from app.agent import tools

    store.upsert_job(Job(id="2026-001", company="Luma AI", company_job_id="R1", position="ML Engineer"))
    store.write_job_md("2026-001", "# ML Engineer — Luma AI\n\n## Posting\nBuild the ML platform.")

    res = tools.generate_cover_letter("2026-001")
    # Mock provider -> deterministic fallback draft, still job-specific and persisted.
    assert "Luma AI" in res["content"]
    assert store.read_cover_letter("2026-001") == res["content"]
