"""The external-agent prompts (web/src/prompts.ts) must not drift from the schemas.

The prompts tell OTHER agents which fields to emit for a job posting / a submitted
application. If a field is renamed or added in api/app/schemas.py and the prompt
isn't updated, users get markdown the app can't map — this pins the two together.
"""
from pathlib import Path

import pytest

PROMPTS_TS = Path(__file__).resolve().parents[2] / "web" / "src" / "prompts.ts"

pytestmark = pytest.mark.skipif(
    not PROMPTS_TS.exists(),
    reason="needs the repo-root web/ tree (absent when ./api is mounted as /app)",
)

# The subset of schema fields an external agent can meaningfully provide (derived
# fields like fit_score/role_category and internal ones like detail_md are ours).
JOB_PROMPT_FIELDS = ["company", "position", "company_job_id", "location",
                     "flexibility", "salary", "posted_date", "close_date", "url"]
APPLICATION_PROMPT_FIELDS = ["company", "position", "company_job_id", "applied_date",
                             "status", "interview_date", "location", "salary", "url",
                             "contacts"]


def _block(name: str) -> str:
    src = PROMPTS_TS.read_text(encoding="utf-8")
    start = src.index(name)
    return src[start : src.index("`;", start)]


def test_prompt_fields_exist_on_the_real_schemas():
    from app.schemas import Application, Job

    job_fields = set(Job.model_fields) | {"salary"}  # salary_min/max/currency condensed
    app_fields = set(Application.model_fields) | {"salary"}
    for f in JOB_PROMPT_FIELDS:
        assert f in job_fields, f"job prompt field {f!r} is not a Job schema field"
    for f in APPLICATION_PROMPT_FIELDS:
        assert f in app_fields, f"application prompt field {f!r} is not an Application field"


def test_prompts_mention_every_expected_field():
    job = _block("JOB_AGENT_PROMPT")
    for f in JOB_PROMPT_FIELDS:
        assert f"**{f}:**" in job, f"job prompt lost the {f!r} field"
    application = _block("APPLICATION_AGENT_PROMPT")
    for f in APPLICATION_PROMPT_FIELDS:
        assert f"**{f}:**" in application, f"application prompt lost the {f!r} field"


def test_prompts_carry_the_never_invent_rule():
    for name in ("JOB_AGENT_PROMPT", "APPLICATION_AGENT_PROMPT"):
        assert "never invent" in _block(name).lower(), f"{name} lost the never-invent rule"
