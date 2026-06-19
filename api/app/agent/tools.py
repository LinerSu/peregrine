"""Concrete agent tools, registered for LLM tool-calling and callable directly
from API routes. Each tool persists through the data store (single source of
truth) and records progress to STATUS.md.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from .. import data_store as store
from .. import status
from ..config import APPLICATIONS_DIR
from ..logging_config import get_logger
from ..schemas import Application, Job
from . import providers
from .registry import registry
from .subagents import evaluator, reviewer, upskiller

log = get_logger(__name__)


# --------------------------------------------------------------------------- #
@registry.register(
    "scan_jobs",
    "Scan configured ATS providers for jobs, dedupe on company+company_job_id, "
    "apply filters, and persist new postings. Returns a summary.",
    {"type": "object", "properties": {}, "required": []},
)
def scan_jobs() -> dict[str, Any]:
    portals = store.read_portals()
    companies = portals.get("companies", []) or []
    filters = portals.get("filters", {}) or {}
    targets = store.read_targets()
    snapshot = portals.get("snapshot", True)

    status.record("scan_start", f"{len(companies)} companies", current_task="Scanning job portals")

    new = dup = filtered = 0
    for c in companies:
        postings = providers.fetch(c.get("provider", "generic"), c.get("name", ""), c.get("slug", ""))
        for p in postings:
            if not _passes_filters(p, filters, targets):
                filtered += 1
                continue
            if store.find_job_by_key(p.company, p.company_job_id):
                dup += 1
                continue
            jid = store.next_job_id()
            detail_md = _job_md(jid, p)
            detail_path = store.write_job_md(jid, detail_md) if snapshot else ""
            store.upsert_job(
                Job(
                    id=jid,
                    company=p.company,
                    company_job_id=p.company_job_id,
                    position=p.position,
                    status="open",
                    location=p.location,
                    posted_date=p.posted_date,
                    url=p.url,
                    detail_md=detail_path,
                )
            )
            new += 1

    summary = {"new": new, "duplicates": dup, "filtered": filtered}
    status.record("scan_done", str(summary), current_task="idle")
    return summary


def _passes_filters(
    p: providers.RawPosting, filters: dict[str, Any], targets: dict[str, Any] | None = None
) -> bool:
    """Portals filters + the user's search targets (config/profile.yml::targets)."""
    targets = targets or {}
    loc_hay = p.location.lower()
    text = f"{p.position} {p.description}".lower()

    # Location: targets override portals; remote postings always pass a location gate.
    locs = [l.lower() for l in (targets.get("locations") or filters.get("locations") or [])]
    if locs and "remote" not in loc_hay and not any(l in loc_hay for l in locs):
        return False
    if (filters.get("remote_only") or targets.get("work_mode") == "remote") and "remote" not in loc_hay:
        return False

    # Keyword include/exclude from search targets.
    if any(kw.lower() in text for kw in (targets.get("exclude_keywords") or [])):
        return False
    include = [kw.lower() for kw in (targets.get("include_keywords") or [])]
    if include and not any(kw in text for kw in include):
        return False
    return True


def _job_md(job_id: str, p: providers.RawPosting) -> str:
    return (
        f"# {p.position} — {p.company}\n\n"
        f"- **id:** {job_id}\n"
        f"- **company_job_id:** {p.company_job_id}\n"
        f"- **location:** {p.location}\n"
        f"- **url:** {p.url}\n"
        f"- **scraped:** {date.today().isoformat()}\n\n"
        f"## Posting\n{p.description or '_no description captured_'}\n\n"
        "---\n\n## Agent evaluation\n"
        "> Filled in by `evaluate_fit`. Gated before the Apply button.\n\n"
        "### Strengths\n- _pending_\n\n### Weaknesses / gaps\n- _pending_\n\n"
        "### Materials to prepare\n- _pending_\n"
    )


# --------------------------------------------------------------------------- #
@registry.register(
    "evaluate_fit",
    "Evaluate how well a job matches the user's profile. Runs evaluator + reviewer "
    "subagents, writes fit_score, and returns strengths/weaknesses/materials.",
    {
        "type": "object",
        "properties": {"job_id": {"type": "string"}},
        "required": ["job_id"],
    },
)
def evaluate_fit(job_id: str) -> dict[str, Any]:
    job = store.get_job(job_id)
    if not job:
        return {"error": f"job {job_id} not found"}

    status.record("evaluate_start", job_id, current_task=f"Evaluating fit for {job_id}")
    job_md = store.read_job_md(job_id) or f"{job.position} at {job.company}"
    profile = store.read_profile()

    evaluation = evaluator(job_md, profile)
    evaluation = reviewer(evaluation, job_md)
    evaluation["job_id"] = job_id

    job.fit_score = float(evaluation.get("fit_score", 0.5))
    store.upsert_job(job)
    store.write_job_md(job_id, _merge_evaluation(job_md, evaluation))

    status.record("evaluate_done", f"{job_id} score={job.fit_score}", current_task="idle")
    return evaluation


def _merge_evaluation(job_md: str, ev: dict[str, Any]) -> str:
    def bullets(items: list[str]) -> str:
        return "\n".join(f"- {i}" for i in items) or "- _none_"

    section = (
        "## Agent evaluation\n"
        f"- **fit_score:** {ev.get('fit_score')}\n"
        f"- **recommendation:** {ev.get('recommendation', 'hold')}\n\n"
        f"### Strengths\n{bullets(ev.get('strengths', []))}\n\n"
        f"### Weaknesses / gaps\n{bullets(ev.get('weaknesses', []))}\n\n"
        f"### Materials to prepare\n{bullets(ev.get('materials', []))}\n"
    )
    marker = "## Agent evaluation"
    return (job_md.split(marker)[0].rstrip() + "\n\n---\n\n" + section) if marker in job_md else (
        job_md + "\n\n---\n\n" + section
    )


# --------------------------------------------------------------------------- #
@registry.register(
    "prepare_materials",
    "Build the pre-apply checklist for a job (strengths, weaknesses, materials) "
    "so the user is ready before clicking Apply.",
    {
        "type": "object",
        "properties": {"job_id": {"type": "string"}},
        "required": ["job_id"],
    },
)
def prepare_materials(job_id: str) -> dict[str, Any]:
    job = store.get_job(job_id)
    if not job:
        return {"error": f"job {job_id} not found"}
    if job.fit_score is None:
        evaluate_fit(job_id)
        job = store.get_job(job_id)
    (APPLICATIONS_DIR / job_id).mkdir(parents=True, exist_ok=True)
    status.record("materials", job_id)
    return {
        "job_id": job_id,
        "apply_url": job.url,
        "detail_md": job.detail_md,
        "note": "Review strengths/weaknesses/materials in the job detail before applying.",
    }


# --------------------------------------------------------------------------- #
@registry.register(
    "assess_upskilling",
    "Compare a job's requirements against the user's profile and surface skill "
    "gaps with concrete ways to close them. Read-only; advisory.",
    {
        "type": "object",
        "properties": {"job_id": {"type": "string"}},
        "required": ["job_id"],
    },
)
def assess_upskilling(job_id: str) -> dict[str, Any]:
    job = store.get_job(job_id)
    if not job:
        return {"error": f"job {job_id} not found"}
    status.record("upskill_start", job_id, current_task=f"Upskilling analysis for {job_id}")
    job_md = store.read_job_md(job_id) or f"{job.position} at {job.company}"
    result = upskiller(job_md, store.read_profile())
    result["job_id"] = job_id
    status.record("upskill_done", job_id, current_task="idle")
    return result


# --------------------------------------------------------------------------- #
@registry.register(
    "mark_applied",
    "Record that the user applied to a job: set the job status to 'applied' and "
    "create/refresh the row in applications.csv. The user always clicks Apply "
    "themselves first — this only tracks it.",
    {
        "type": "object",
        "properties": {
            "job_id": {"type": "string"},
            "applied_date": {"type": "string", "description": "ISO date; defaults to today"},
        },
        "required": ["job_id"],
    },
)
def mark_applied(job_id: str, applied_date: str = "") -> dict[str, Any]:
    job = store.get_job(job_id)
    if not job:
        return {"error": f"job {job_id} not found"}

    job.status = "applied"
    store.upsert_job(job)

    when = applied_date or date.today().isoformat()
    existing = store.get_application(job_id)
    app = Application(**job.model_dump(), applied_date=when)
    if existing:  # preserve tracker fields the user has edited
        app.applied_date = existing.applied_date or when
        app.interview_date = existing.interview_date
        app.contacts = existing.contacts
        app.notes = existing.notes
    store.upsert_application(app)

    status.record("mark_applied", f"{job_id} {job.company}", current_task="idle")
    return {"application": app.model_dump(), "created": not existing}


# --------------------------------------------------------------------------- #
@registry.register(
    "parse_cv",
    "Parse pasted CV text into the user's profile (config/profile.yml) as memory.",
    {
        "type": "object",
        "properties": {"cv_text": {"type": "string"}},
        "required": ["cv_text"],
    },
)
def parse_cv(cv_text: str) -> dict[str, Any]:
    from .subagents import LLMClient, _json_from_text, load_skill

    status.record("cv_intake", f"{len(cv_text)} chars", current_task="Parsing CV")
    llm = LLMClient()
    res = llm.complete(
        [
            {"role": "system", "content": load_skill("cv-intake")},
            {
                "role": "user",
                "content": "CV:\n```\n" + cv_text[:12000] + "\n```\n\nReturn ONLY a JSON "
                "profile object with keys: name, headline, location, skills "
                "(array of {name, level, evidence}).",
            },
        ]
    )
    parsed = _json_from_text(res.text)
    profile = store.read_profile()
    if parsed:
        profile.update({k: v for k, v in parsed.items() if v})
        store.write_profile(profile)
    status.record("cv_intake_done", f"skills={len(parsed.get('skills', []))}", current_task="idle")
    return {"updated": bool(parsed), "profile": profile}


# --------------------------------------------------------------------------- #
@registry.register(
    "list_jobs",
    "List tracked jobs, optionally filtered by a free-text query over company/position.",
    {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": [],
    },
)
def list_jobs(query: str = "") -> dict[str, Any]:
    jobs = store.list_jobs()
    if query:
        q = query.lower()
        jobs = [j for j in jobs if q in j.company.lower() or q in j.position.lower()]
    jobs.sort(key=lambda j: (j.fit_score or 0), reverse=True)
    return {"count": len(jobs), "jobs": [j.model_dump() for j in jobs]}


# --------------------------------------------------------------------------- #
def _persist_posting(p: providers.RawPosting) -> Job:
    """Write a RawPosting to the store (CSV row + snapshot md), returning the Job."""
    jid = store.next_job_id()
    detail_path = store.write_job_md(jid, _job_md(jid, p))
    return store.upsert_job(
        Job(
            id=jid,
            company=p.company,
            company_job_id=p.company_job_id,
            position=p.position,
            status="open",
            location=p.location,
            posted_date=p.posted_date,
            url=p.url,
            detail_md=detail_path,
        )
    )


@registry.register(
    "ingest_job_url",
    "Ingest a single job posting from a pasted URL (e.g. amazon.jobs or a "
    "Greenhouse board), persist it, and return the job. Deduped on company+company_job_id.",
    {
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
    },
)
def ingest_job_url(url: str) -> dict[str, Any]:
    status.record("ingest_start", url[:120], current_task="Ingesting job URL")
    try:
        posting = providers.ingest_url(url)
    except providers.PolicyViolation as exc:
        status.record("ingest_blocked", str(exc)[:160], current_task="idle")
        return {"error": str(exc)}
    if not posting:
        status.record("ingest_failed", url[:120], current_task="idle")
        return {"error": f"unsupported or unreachable URL: {url}"}

    existing = store.find_job_by_key(posting.company, posting.company_job_id)
    job = existing or _persist_posting(posting)
    status.record(
        "ingest_done", f"{job.id} {job.company} {job.company_job_id}", current_task="idle"
    )
    return {"job": job.model_dump(), "deduped": bool(existing)}
