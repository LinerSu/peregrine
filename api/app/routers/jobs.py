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
