"""Jobs API — list, detail (with markdown), scan, evaluate, prepare-to-apply."""
from __future__ import annotations

import json

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .. import data_store as store
from ..agent.llm import active_provider_is_mock
from ..agent import tools
from ..extract import extract_text
from ..agent import providers
from ..schemas import (
    CONTACT_FIELDS,
    CoverLetterInput,
    CvTexInput,
    EvaluationInput,
    JobIngestInput,
    JobSourceInput,
    PortalsInput,
    PurgeInput,
    UpskillingInput,
)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

# Providers a user may configure in-app. SmartRecruiters is excluded (its robots.txt disallows
# the postings API); "generic" is the no-op fallback for an unrecognized provider.
_ALLOWED_PROVIDERS = set(providers.PROVIDERS) - {"smartrecruiters"}


def _norm_provider(v: str) -> str:
    v = (v or "").lower().strip()
    return v if v in _ALLOWED_PROVIDERS else "generic"


@router.get("")
def list_jobs(query: str = ""):
    return tools.list_jobs(query=query)


@router.get("/sources")
def sources():
    """Configured scan sources — feeds the per-company scan selector."""
    portals = store.read_portals()
    return {
        "companies": [
            {"name": c.get("name", ""), "provider": c.get("provider", "")}
            for c in (portals.get("companies") or [])
            if c.get("name")
        ]
    }


@router.get("/portals")
def get_portals():
    """The full scan config for the Settings UI (so users never hand-edit portals.yml).
    Shapes are coerced — a hand-edited/malformed portals.yml must not crash the UI."""
    p = store.read_portals()
    companies = p.get("companies")
    queries = p.get("queries")
    filters = p.get("filters")
    return {
        "companies": [c for c in companies if isinstance(c, dict)] if isinstance(companies, list) else [],
        "queries": [str(q) for q in queries if str(q).strip()] if isinstance(queries, list) else [],
        "filters": filters if isinstance(filters, dict) else {},
        "providers": sorted(_ALLOWED_PROVIDERS - {"generic"}),  # selectable in the UI
    }


@router.put("/portals")
def put_portals(payload: PortalsInput):
    """Store-only scan-config edit (no LLM -> identical in both modes). Only the provided keys
    are updated; snapshot/rate_limit_seconds and anything else in portals.yml is preserved."""
    portals = store.read_portals()
    if payload.companies is not None:
        portals["companies"] = [
            {"name": c.name.strip(), "provider": _norm_provider(c.provider), "slug": c.slug.strip()}
            for c in payload.companies
            if c.name.strip()
        ]
    if payload.queries is not None:
        portals["queries"] = payload.queries
    if payload.filters is not None:
        portals["filters"] = payload.filters.model_dump()
    store.write_portals(portals)
    return get_portals()


@router.post("/portals/detect")
def detect_portals(payload: dict):
    """Add-company-by-name: probe the supported boards for {name} and return where it lives."""
    return {"sources": tools.detect_company_sources((payload or {}).get("name", ""))}


@router.get("/portals/suggest-queries")
def suggest_queries():
    """Propose relevance queries from the user's profile (roles/headline/experience) so they
    don't hand-type search terms. Deterministic — no LLM."""
    return {"queries": tools.suggest_queries(store.read_profile())}


@router.post("/scan")
def scan(payload: dict | None = None):
    # Optional {"companies": [...]} restricts the scan to those companies; omit to scan all.
    # Only a non-empty LIST narrows the scan — anything else (string, {}, []) means "all".
    companies = (payload or {}).get("companies")
    only = companies if isinstance(companies, list) and companies else None
    return tools.scan_jobs(only=only)


@router.post("/ingest")
def ingest(payload: dict, background: BackgroundTasks):
    """Ingest a single posting from a pasted URL (e.g. amazon.jobs)."""
    result = tools.ingest_job_url(payload.get("url", ""))
    if "error" in result:
        raise HTTPException(422, result["error"])
    # URL ingest itself is deterministic, so the web calls it in BOTH modes. Auto-eval
    # is not — an Internal-mode caller sends auto_evaluate:false so the API never spends
    # API tokens on their behalf; local Claude scores it instead (mode contract).
    return _schedule_auto_eval(background, result, payload.get("auto_evaluate", True))


def _schedule_auto_eval(background: BackgroundTasks, result: dict, enabled: bool = True) -> dict:
    """After an EXTERNAL-path ingest creates a job, evaluate fit automatically — in
    the background so the paste-to-added feel stays instant; the UI's normal
    refresh/poll picks the score up when it lands.

    Guards: only NEWLY created jobs (a dedup hit keeps its existing evaluation);
    only when a real profile exists (scoring an empty profile is noise); never when the
    active provider is effectively mock — a keyless anthropic/openai config falls back
    to the deterministic {fit 0.5, "(mock)"} stub, and placeholder scores must not be
    written silently. The Internal store-only path (/ingest-doc/save) is deliberately
    NOT wired here — the API can't run Internal-mode LLM work; the local-Claude skill
    chains the evaluation itself (mode contract)."""
    if (
        enabled
        and result.get("created")
        and tools.profile_ready()
        and not active_provider_is_mock()
    ):
        background.add_task(tools.evaluate_fit, result["job"]["id"])
        result["auto_evaluating"] = True
    return result


@router.post("/evaluate-missing")
def evaluate_missing(background: BackgroundTasks):
    """Backfill: evaluate every OPEN job with no fit score yet — a new capability
    applies to data already tracked, not only to future ingests. Same
    guards as auto-evaluate on ingest (real profile; never an effectively-mock provider,
    keyless anthropic/openai included — it would mass-write 0.5 placeholders), and
    evaluations run in the background — the UI's refresh picks scores up as they
    land. Internal-mode users say "evaluate all jobs missing a fit score" in the
    terminal instead — this endpoint is the External-mode path (mode contract)."""
    if not tools.profile_ready():
        return {"scheduled": 0, "reason": "profile not set up"}
    if active_provider_is_mock():
        return {"scheduled": 0,
                "reason": "mock provider — placeholder scores are never written automatically"}
    pending = [j.id for j in store.list_jobs() if j.fit_score is None and j.status == "open"]
    for jid in pending:
        background.add_task(tools.evaluate_fit, jid)
    return {"scheduled": len(pending)}


# --- Add a job from content the user provides (no scraping) — both modes. --------
@router.post("/ingest-doc")
def ingest_doc(payload: JobSourceInput, background: BackgroundTasks):
    """External: parse a pasted job posting into a tracked job with the LLM."""
    result = tools.ingest_job_doc(payload.text)
    if "error" in result:
        raise HTTPException(422, result["error"])
    return _schedule_auto_eval(background, result)


@router.post("/ingest-doc/upload")
async def ingest_doc_upload(background: BackgroundTasks, file: UploadFile = File(...)):
    """External: extract text from an uploaded posting (PDF/.txt/.md) and parse it."""
    try:
        text = extract_text(file.filename or "", await file.read())
    except Exception as exc:  # corrupt/unsupported file
        raise HTTPException(422, f"could not read file: {exc}")
    if not text.strip():
        raise HTTPException(422, "no text could be extracted from the file")
    result = tools.ingest_job_doc(text)
    if "error" in result:
        raise HTTPException(422, result["error"])
    return _schedule_auto_eval(background, result)


@router.post("/ingest-doc/save")
def ingest_doc_save(payload: JobIngestInput):
    """Internal: create a tracked job from fields Claude already parsed (store-only)."""
    result = tools.save_ingested_job(payload.model_dump())
    if "error" in result:
        raise HTTPException(422, result["error"])
    return result


@router.get("/ingest-result")
def ingest_result():
    """Last ingest marker (monotonic seq + result) — the Internal-mode UI polls this
    to detect when a paste/upload it stashed has been turned into a job by Claude."""
    return tools.get_ingest_result()


@router.put("/ingest-source")
def put_job_source(payload: JobSourceInput):
    """Internal: stash the raw posting text so local Claude can parse it."""
    if not payload.text.strip():
        raise HTTPException(422, "empty posting text")
    return tools.save_job_source(payload.text)


@router.post("/ingest-source/upload")
async def upload_job_source(file: UploadFile = File(...)):
    """Internal: extract text from an uploaded posting (PDF/.txt/.md) and stash it
    for local Claude to parse — no LLM call."""
    try:
        text = extract_text(file.filename or "", await file.read())
    except Exception as exc:  # corrupt/unsupported file
        raise HTTPException(422, f"could not read file: {exc}")
    if not text.strip():
        raise HTTPException(422, "no text could be extracted from the file")
    return tools.save_job_source(text)


@router.get("/{job_id}")
def get_job(job_id: str):
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(404, f"job {job_id} not found")
    d = job.model_dump()
    d["skill_fit"] = tools._skill_fit(job.req_skills, tools._user_skills())  # for the detail panel
    return {"job": d, "markdown": store.read_job_md(job_id)}


# People you found yourself (never scraped) are editable from the Jobs view too.
# `company` is editable so a name variant is fixed IN PLACE ("Acme Inc" -> "Acme"):
# correcting a spelling must never mean delete-and-re-add, which would drop the row's
# history and any linked application.
EDITABLE_JOB_FIELDS = {"starred", "role_category", "status", "company"} | CONTACT_FIELDS
# Statuses that also make sense on an application (so a job→app status sync can't set
# a pre-application status like "open"/"removed" on a tracked application).
_APP_STATUSES = {"applied", "interviewing", "offer", "rejected", "closed"}


@router.patch("/{job_id}")
def update_job(job_id: str, payload: dict):
    """Update user-controllable job fields: starred, role_category, status, and people
    (recruiter / hiring manager)."""
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(404, f"job {job_id} not found")
    changes = {k: v for k, v in payload.items() if k in EDITABLE_JOB_FIELDS}
    if "people" in changes and not isinstance(changes["people"], str):
        changes["people"] = json.dumps(changes["people"])  # always a JSON string (the UI parses it)
    updated = job.model_copy(update=changes)
    store.upsert_job(updated)
    # Keep a linked application (shared id) in sync: status, and the people fields — so contacts
    # are consistent across Jobs + Applications no matter where you enter them.
    appn = store.get_application(job_id)
    if appn:
        sync = {k: changes[k] for k in CONTACT_FIELDS if k in changes}
        if "company" in changes:  # a spelling fix must not desync the application row
            sync["company"] = updated.company
        if "status" in changes and updated.status in _APP_STATUSES and appn.status != updated.status:
            sync["status"] = updated.status
        if sync:
            store.upsert_application(appn.model_copy(update=sync))
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
    ev = tools.get_evaluation(job_id)
    if not ev:
        return {}
    # `stale` = evaluated against a PREVIOUS CV (profile changed since); the UI hides
    # the scores and points at re-running Evaluate fit. Added only on a non-empty
    # response so "{} means no evaluation yet" stays true for the polling UI.
    ev["stale"] = tools.artifact_stale(job_id, ".evaluation.json")
    return ev


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
    404s on an unknown job, consistent with GET /{job_id}. `stale` means it was
    drafted against a PREVIOUS CV (the profile changed since) — the UI de-emphasizes
    it and points at Redraft."""
    if not store.get_job(job_id):
        raise HTTPException(404, f"job {job_id} not found")
    cover = tools.get_cover_letter(job_id)
    if not cover:
        return {}
    cover["stale"] = tools.artifact_stale(job_id, ".cover_letter.md")
    return cover


@router.delete("/{job_id}")
def delete_job(job_id: str):
    """Hard-delete a mistakenly-added job (row + all its data/jobs/ artifacts).

    Refuses while a linked application exists (shared id): application history must
    never vanish as a side effect of deleting a posting — delete the application
    first if that's really the intent."""
    if not store.get_job(job_id):
        raise HTTPException(404, f"job {job_id} not found")
    if store.get_application(job_id):
        raise HTTPException(
            409, "a linked application exists — delete it on the Applications tab first"
        )
    store.delete_job(job_id)
    return {"deleted": job_id}


@router.post("/purge")
def purge_closed_jobs(payload: PurgeInput):
    """One-shot retention purge: delete CLOSED jobs whose posting is older than the
    cutoff (rows + artifacts). Jobs with a linked application or without a parseable
    posted_date are skipped — conservative by design. For an automatic version, set
    filters.retention_days in portals.yml (applied at the end of every scan)."""
    return store.purge_closed_jobs(payload.older_than_days)


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
