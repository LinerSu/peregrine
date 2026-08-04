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
    monkeypatch.setattr(config, "APPLICATIONS_DIR", tmp_path / "applications")  # materials mirror here
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


def test_gather_dedupes_by_stem_curated_wins(tmp_store):
    d = tmp_store / "cover_letter_samples"
    d.mkdir()
    (d / "engineering.md").write_text("USER VERSION should be dropped", encoding="utf-8")
    refs = gather_style_references()
    assert refs.count("Sample: engineering") == 1
    assert "USER VERSION" not in refs  # curated sample of the same stem wins


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


# --- evidence library wiring (issue #69) ---------------------------------------------

def test_both_modes_draft_from_the_same_selected_evidence(tmp_path, monkeypatch):
    """The contract's real test: External passes evidence into the prompt, and the endpoint
    Internal reads returns the SAME passages. Different material in each mode would make
    the two modes only nominally equivalent."""
    from fastapi.testclient import TestClient

    from app import config, evidence
    from app import data_store as store
    from app.agent import subagents, tools
    from app.main import app
    from app.schemas import Job

    monkeypatch.setattr(config, "JOBS_CSV", tmp_path / "jobs.csv")
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(config, "APPLICATIONS_CSV", tmp_path / "applications.csv")
    monkeypatch.setattr(config, "PROFILE_YML", tmp_path / "profile.yml")
    (tmp_path / "jobs").mkdir()
    ev = tmp_path / "evidence"
    ev.mkdir()
    monkeypatch.setattr(config, "EVIDENCE_DIR", ev)
    (ev / "pass.md").write_text("# Loop folding\n" + "An LLVM C++ pass that folds loads. " * 6)
    config.PROFILE_YML.write_text("name: Someone\ngoal: ship analysis into other teams' CI\n")

    store.upsert_job(Job(id="2026-001", company="Acme", company_job_id="R1",
                         position="Compiler Engineer", req_skills="C++, LLVM"))
    monkeypatch.setattr(tools.status, "record", lambda *a, **k: None)

    seen: dict = {}

    def fake_writer(job, job_md, profile, evaluation, style_refs, evidence="", goal="",
                    employer=""):
        seen["evidence"], seen["goal"], seen["employer"] = evidence, goal, employer
        return "Dear team, ..."

    monkeypatch.setattr(tools, "cover_letter_writer", fake_writer)
    tools.generate_cover_letter("2026-001")

    assert "Loop folding" in seen["evidence"]          # External got the passage
    assert seen["goal"] == "ship analysis into other teams' CI"

    got = TestClient(app).get("/api/jobs/2026-001/evidence").json()
    assert [p["heading"] for p in got["passages"]] == ["Loop folding"]   # Internal: identical
    assert got["goal"] == seen["goal"]


def test_a_letter_still_works_with_no_evidence(tmp_path, monkeypatch):
    # The library is additive: someone who never creates data/evidence/ must not lose the
    # feature they already had.
    from app import config
    from app import data_store as store
    from app.agent import tools
    from app.schemas import Job

    monkeypatch.setattr(config, "JOBS_CSV", tmp_path / "jobs.csv")
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(config, "APPLICATIONS_CSV", tmp_path / "applications.csv")
    monkeypatch.setattr(config, "PROFILE_YML", tmp_path / "profile.yml")
    monkeypatch.setattr(config, "EVIDENCE_DIR", tmp_path / "nope")
    (tmp_path / "jobs").mkdir()
    store.upsert_job(Job(id="2026-001", company="Acme", company_job_id="R1", position="Eng"))
    monkeypatch.setattr(tools.status, "record", lambda *a, **k: None)

    captured: dict = {}

    def fake_writer(job, job_md, profile, evaluation, style_refs, evidence="", goal="",
                    employer=""):
        captured["evidence"] = evidence
        return "letter"

    monkeypatch.setattr(tools, "cover_letter_writer", fake_writer)
    assert "error" not in tools.generate_cover_letter("2026-001")
    assert captured["evidence"] == ""


def test_employer_context_comes_from_the_posting_not_the_web(tmp_path, monkeypatch):
    """The letter has to argue "why here", and nothing in the pipeline knew anything about
    the employer. Postings describe themselves; extracting that is free and cannot invent
    a fact about a company the way a web lookup could."""
    from app import config
    from app import data_store as store
    from app.agent import tools
    from app.schemas import Job

    monkeypatch.setattr(config, "JOBS_CSV", tmp_path / "jobs.csv")
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(config, "APPLICATIONS_CSV", tmp_path / "applications.csv")
    (tmp_path / "jobs").mkdir()
    store.upsert_job(Job(id="2026-001", company="Acme", company_job_id="R1", position="Eng"))
    store.write_job_md("2026-001", """# Eng — Acme

## Posting
We are a non-profit that maintains widget infrastructure used by thousands of projects.
You will triage incoming reports and improve the tooling. Requires C and Python.
The role is remote.
""")
    ctx = tools.employer_context("2026-001")
    assert "non-profit" in ctx                    # organisational sentence extracted
    assert "triage incoming reports" not in ctx   # role duties are not employer context
