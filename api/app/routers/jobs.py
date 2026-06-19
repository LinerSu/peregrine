"""Jobs API — list, detail (with markdown), scan, evaluate, prepare-to-apply."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import data_store as store
from ..agent import tools

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("")
def list_jobs(query: str = ""):
    return tools.list_jobs(query=query)


@router.post("/scan")
def scan():
    return tools.scan_jobs()


@router.post("/ingest")
def ingest(payload: dict):
    """Ingest a single posting from a pasted URL (e.g. amazon.jobs)."""
    result = tools.ingest_job_url(payload.get("url", ""))
    if "error" in result:
        raise HTTPException(422, result["error"])
    return result


@router.get("/{job_id}")
def get_job(job_id: str):
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(404, f"job {job_id} not found")
    return {"job": job.model_dump(), "markdown": store.read_job_md(job_id)}


EDITABLE_JOB_FIELDS = {"starred", "role_category", "status"}


@router.patch("/{job_id}")
def update_job(job_id: str, payload: dict):
    """Update user-controllable job fields: starred, role_category, status."""
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(404, f"job {job_id} not found")
    changes = {k: v for k, v in payload.items() if k in EDITABLE_JOB_FIELDS}
    updated = job.model_copy(update=changes)
    store.upsert_job(updated)
    return {"job": updated.model_dump()}


@router.post("/{job_id}/evaluate")
def evaluate(job_id: str):
    result = tools.evaluate_fit(job_id)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@router.post("/{job_id}/prepare")
def prepare(job_id: str):
    """Pre-apply gate: returns the apply URL only alongside the review material."""
    result = tools.prepare_materials(job_id)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@router.post("/{job_id}/apply")
def apply(job_id: str, payload: dict | None = None):
    """Record that the user applied: flips status to 'applied' and tracks it."""
    result = tools.mark_applied(job_id, (payload or {}).get("applied_date", ""))
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@router.post("/{job_id}/upskilling")
def upskilling(job_id: str):
    """Skill-gap analysis: what the job wants vs. the user's profile."""
    result = tools.assess_upskilling(job_id)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result
