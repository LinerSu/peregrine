"""Jobs API — list, detail (with markdown), scan, evaluate, prepare-to-apply."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .. import data_store as store
from ..agent import tools
from ..schemas import CoverLetterInput, CvTexInput, EvaluationInput, UpskillingInput

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
    """External mode: run the skill-gap analysis with the LLM and persist it."""
    result = tools.assess_upskilling(job_id)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


# --- Store-only persistence (Internal mode: Claude reasons in the terminal, then
# saves the result here via a PUT; no LLM is invoked by these routes). ----------
@router.put("/{job_id}/evaluation")
def save_evaluation(job_id: str, payload: EvaluationInput):
    """Persist a fit evaluation produced outside the API (e.g. local Claude)."""
    result = tools.save_evaluation(job_id, payload.model_dump())
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@router.get("/{job_id}/evaluation")
def read_evaluation(job_id: str):
    """Read the last saved structured fit evaluation ({} if none yet) — the UI uses
    it for the legitimacy/archetype blocks. 404s on an unknown job."""
    if not store.get_job(job_id):
        raise HTTPException(404, f"job {job_id} not found")
    return tools.get_evaluation(job_id) or {}


@router.put("/{job_id}/upskilling")
def save_upskilling(job_id: str, payload: UpskillingInput):
    """Persist a skill-gap analysis produced outside the API (e.g. local Claude)."""
    result = tools.save_upskilling(job_id, payload.model_dump())
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@router.get("/{job_id}/upskilling")
def read_upskilling(job_id: str):
    """Read the last saved skill-gap analysis ({} if none yet) — used by the UI poll.
    404s on an unknown job, consistent with GET /{job_id}."""
    if not store.get_job(job_id):
        raise HTTPException(404, f"job {job_id} not found")
    return tools.get_upskilling(job_id) or {}


@router.post("/{job_id}/cover-letter")
def generate_cover_letter(job_id: str):
    """External mode: draft a cover letter with the LLM and persist it."""
    result = tools.generate_cover_letter(job_id)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@router.put("/{job_id}/cover-letter")
def save_cover_letter(job_id: str, payload: CoverLetterInput):
    """Persist a cover-letter draft produced outside the API (e.g. local Claude)."""
    result = tools.save_cover_letter(job_id, payload.content)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@router.get("/{job_id}/cover-letter")
def read_cover_letter(job_id: str):
    """Read the last saved cover-letter draft ({} if none yet) — used by the UI poll.
    404s on an unknown job, consistent with GET /{job_id}."""
    if not store.get_job(job_id):
        raise HTTPException(404, f"job {job_id} not found")
    return tools.get_cover_letter(job_id) or {}


@router.post("/{job_id}/cv")
def generate_tailored_cv(job_id: str):
    """External mode: draft a job-tailored CV (LaTeX) with the LLM + compile a PDF."""
    result = tools.generate_tailored_cv(job_id)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@router.put("/{job_id}/cv")
def save_tailored_cv(job_id: str, payload: CvTexInput):
    """Persist a tailored-CV LaTeX produced outside the API (e.g. local Claude) and
    compile its PDF."""
    result = tools.save_tailored_cv(job_id, payload.tex)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@router.get("/{job_id}/cv")
def read_tailored_cv(job_id: str):
    """Read the last tailored CV ({} if none yet) — used by the UI poll. 404s on an
    unknown job, consistent with GET /{job_id}."""
    if not store.get_job(job_id):
        raise HTTPException(404, f"job {job_id} not found")
    return tools.get_tailored_cv(job_id) or {}


@router.get("/{job_id}/cv.pdf")
def download_tailored_cv_pdf(job_id: str):
    """Download the compiled tailored-CV PDF (404 if not compiled — e.g. no LaTeX)."""
    if not store.get_job(job_id):
        raise HTTPException(404, f"job {job_id} not found")
    path = store.cv_pdf_path(job_id)
    if not path.exists():
        raise HTTPException(404, "no compiled PDF for this job")
    return FileResponse(path, media_type="application/pdf", filename=f"cv-{job_id}.pdf")
