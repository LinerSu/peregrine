"""The external-agent prompts (web/src/prompts.ts) must match the INGEST contract.

The prompts tell OTHER agents which fields to emit for a job posting / a submitted
application. Two failure modes are pinned:
  * the prompt asks for a field the ingest pipeline silently discards (the user pays
    an agent round-trip for data the app throws away) — pinned by the ROUND-TRIP test
    through the real store-only ingest, and by subset checks against JobIngestInput;
  * a schema/ingest field an agent could supply is missing from the prompt — pinned
    by two-way set equality against an explicit internal-fields exclusion list.
"""
from pathlib import Path

import pytest

from app import config
from app import data_store as store
from app.schemas import Application, Job, JobIngestInput

PROMPTS_TS = Path(__file__).resolve().parents[2] / "web" / "src" / "prompts.ts"

pytestmark = pytest.mark.skipif(
    not PROMPTS_TS.exists(),
    reason="needs the repo-root web/ tree (absent when ./api is mounted as /app)",
)

JOB_PROMPT_FIELDS = ["company", "position", "company_job_id", "location", "flexibility",
                     "salary_min", "salary_max", "currency", "posted_date", "close_date", "url"]
APPLICATION_PROMPT_FIELDS = ["company", "position", "company_job_id", "applied_date",
                             "status", "interview_date", "location", "salary", "posted_date",
                             "url", "people"]

# Job fields an external agent can NOT meaningfully supply: ours (derived/internal).
JOB_INTERNAL_FIELDS = {"id", "status", "fit_score", "detail_md", "role_category", "level",
                       "req_skills", "domains", "keywords", "starred", "people"}


def _block(name: str) -> str:
    src = PROMPTS_TS.read_text(encoding="utf-8")
    start = src.index(name)
    return src[start : src.index("`;", start)]


def test_job_prompt_matches_the_ingest_contract_both_ways():
    # Everything the prompt collects must be ACCEPTED by the store-only ingest body
    # (the surface both modes converge on) — except description, which rides as the
    # Posting section.
    ingest_fields = set(JobIngestInput.model_fields)
    for f in JOB_PROMPT_FIELDS:
        assert f in ingest_fields, f"job prompt collects {f!r} but ingest would drop it"
    # And the reverse: every agent-suppliable Job column is asked for.
    expected = set(Job.model_fields) - JOB_INTERNAL_FIELDS
    assert expected == set(JOB_PROMPT_FIELDS), (
        "job prompt fields drifted from the agent-suppliable Job columns — update "
        "the prompt (web/src/prompts.ts) or JOB_INTERNAL_FIELDS deliberately"
    )


def test_application_prompt_fields_exist_on_the_schema():
    app_fields = set(Application.model_fields) | {"salary"}  # min/max/currency condensed
    for f in APPLICATION_PROMPT_FIELDS:
        assert f in app_fields, f"application prompt field {f!r} is not an Application field"


def test_prompts_mention_every_expected_field():
    job = _block("JOB_AGENT_PROMPT")
    for f in JOB_PROMPT_FIELDS:
        assert f"**{f}:**" in job, f"job prompt lost the {f!r} field"
    application = _block("APPLICATION_AGENT_PROMPT")
    for f in APPLICATION_PROMPT_FIELDS:
        assert f"**{f}:**" in application, f"application prompt lost the {f!r} field"


def test_application_prompt_status_vocabulary_is_complete():
    application = _block("APPLICATION_AGENT_PROMPT")
    for s in ("applied", "interviewing", "offer", "rejected", "closed"):
        assert s in application, f"application prompt status vocabulary lost {s!r}"


def test_prompts_carry_the_never_invent_rule():
    for name in ("JOB_AGENT_PROMPT", "APPLICATION_AGENT_PROMPT"):
        assert "never invent" in _block(name).lower(), f"{name} lost the never-invent rule"


def test_prompts_require_a_markdown_file_output():
    # The deliverable is an uploadable FILE (the .md uploader is the cleanest ingest
    # path), with a bare code block as the no-file-capability fallback.
    for name in ("JOB_AGENT_PROMPT", "APPLICATION_AGENT_PROMPT"):
        block = _block(name).lower()
        assert "markdown file" in block, f"{name} lost the file-output rule"
        assert ".md" in block, f"{name} lost the filename convention"


def test_prompt_shaped_fields_round_trip_through_ingest(tmp_path, monkeypatch):
    # The REAL guarantee: a fields payload in the prompt's shape, pushed through the
    # actual store-only ingest, lands on the Job row with nothing discarded.
    from app.agent import tools

    monkeypatch.setattr(config, "JOBS_CSV", tmp_path / "jobs.csv")
    monkeypatch.setattr(config, "APPLICATIONS_CSV", tmp_path / "applications.csv")
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(config, "PROFILE_YML", tmp_path / "profile.yml")
    (tmp_path / "jobs").mkdir()
    monkeypatch.setattr(tools.status, "record", lambda *a, **k: None)
    monkeypatch.setattr(store, "write_ingest_result", lambda *a, **k: None)
    monkeypatch.setattr(store, "read_ingest_result", lambda: {}, raising=False)

    payload = JobIngestInput(
        company="Acme", position="ML Engineer", company_job_id="R-1",
        location="Toronto, ON", url="https://example.com/jobs/r-1",
        posted_date="2026-07-01", close_date="2026-09-01", flexibility="hybrid",
        salary_min="300000", salary_max=420000, currency="USD",
        description="Build models. Requires Python.",
    ).model_dump()
    out = tools.save_ingested_job(payload)
    assert "error" not in out

    job = store.get_job(out["job"]["id"])
    assert job.flexibility == "hybrid"
    assert job.close_date == "2026-09-01"
    assert job.salary_min == 300000.0 and job.salary_max == 420000.0
    assert job.currency == "USD"
    assert job.posted_date == "2026-07-01" and job.url == "https://example.com/jobs/r-1"
