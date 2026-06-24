"""Applications + profile/CV endpoints."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, File, HTTPException, UploadFile

from .. import data_store as store
from ..agent import tools
from ..extract import extract_text
from ..schemas import Application, CvSourceInput, ProfileInput
from ..skills import normalize_category

router = APIRouter(prefix="/api", tags=["applications"])

# Tracker fields the user may edit from the Applications view.
EDITABLE_APPLICATION_FIELDS = {"status", "interview_date", "applied_date", "contacts", "notes"}


@router.get("/applications")
def list_applications():
    apps = store.list_applications()
    jobs = store.list_jobs()  # load once; flag each app with whether a posting is tracked
    out = []
    for a in apps:
        # job_tracked = a tracked posting MATCHES this app (drives the "no posting"
        # badge). For apps created via Apply/auto-link it's also formally linked by id;
        # for an older orphan it may be matchable-but-not-yet-linked — both hide the badge.
        tracked = store.match_job(jobs, a.company, a.position, a.company_job_id, a.location) is not None
        out.append({**a.model_dump(), "job_tracked": tracked})
    return {"count": len(out), "applications": out}


@router.post("/applications")
def create_application(payload: dict):
    """Manually track an application (e.g. one you applied to outside Peregrine).

    If it matches a tracked job (company+position), link it (adopt the job's
    company_job_id, mark the job applied). Otherwise it's an orphan — the response's
    `job_tracked: false` lets the UI nudge the user to add the posting."""
    company, position = (payload.get("company") or "").strip(), (payload.get("position") or "").strip()
    job = (
        store.find_job_for_posting(company, position, payload.get("company_job_id", ""), payload.get("location", ""))
        if company and position
        else None
    )

    if job:
        # Unify with the Apply flow: take the FULL job fields (url/salary/posted_date/…),
        # share the job's id (so delete reverts it and re-adding dedups). Promote an
        # un-actioned job to "applied" first; the app then MIRRORS the job's status
        # (we don't let the create payload set status independently — that would desync
        # app vs job, or downgrade an actioned job). Use PATCH to change status later.
        if job.status in ("open", "closed", "removed"):
            job.status = "applied"
            store.upsert_job(job)
        existing = store.get_application(job.id)
        data = job.model_dump()  # carries the job's (post-promotion) status
        data["id"] = job.id
        if existing and existing.status:  # on re-add, keep the app's own lifecycle status
            data["status"] = existing.status
        for f in ("applied_date", "interview_date", "contacts", "notes"):
            if payload.get(f):
                data[f] = payload[f]
            elif existing and getattr(existing, f):
                data[f] = getattr(existing, f)
        if not data.get("applied_date"):
            data["applied_date"] = date.today().isoformat()
    else:
        data = {k: v for k, v in payload.items() if k in Application.model_fields}
        data["id"] = store.next_id()
        data.setdefault("status", "applied")
        data.setdefault("company_job_id", f"manual-{data['id']}")
        if not data.get("applied_date"):
            data["applied_date"] = date.today().isoformat()

    try:
        app = Application(**data)
    except Exception as exc:  # missing company/position etc.
        raise HTTPException(422, f"invalid application: {exc}")
    store.upsert_application(app)
    return {"application": app.model_dump(), "job_tracked": job is not None}


@router.post("/applications/{app_id}/link")
def link_application(app_id: str, payload: dict):
    """Link an orphan application to a (usually just-ingested) job posting: re-key the
    app to the job's id, carry the job's full fields + the orphan's tracker fields, sync
    the job to the app's lifecycle status, and drop the now-superseded orphan row.

    Deterministic (no LLM) — identical in both modes; the LLM part is the ingest that
    created the job (already mode-aware via the increment-5 flow)."""
    orphan = store.get_application(app_id)
    if not orphan:
        raise HTTPException(404, f"application {app_id} not found")
    job = store.get_job((payload.get("job_id") or "").strip())
    if not job:
        raise HTTPException(404, f"job {payload.get('job_id', '')!r} not found")
    # Promote an un-actioned job (open/closed/removed) to the orphan's lifecycle status;
    # never downgrade a job already in progress — it stays, and the app mirrors it (like
    # the Apply/auto-link flow). The common case is a fresh ingest (status "open").
    if job.status in ("open", "closed", "removed") and orphan.status:
        job.status = orphan.status
        store.upsert_job(job)
    data = job.model_dump()  # app mirrors the job's resulting status + carries its fields
    data["id"] = job.id
    for f in ("applied_date", "interview_date", "contacts", "notes"):
        if getattr(orphan, f, ""):
            data[f] = getattr(orphan, f)
    if not data.get("applied_date"):
        data["applied_date"] = date.today().isoformat()
    linked = Application(**data)
    store.upsert_application(linked)
    # Drop the now-superseded orphan row. next_id() shares one counter across jobs +
    # applications, so an orphan's id is never a real job id; store.delete_application
    # (which doesn't touch jobs at all) therefore can't affect the job we just linked.
    if app_id != job.id:
        store.delete_application(app_id)
    return {"application": linked.model_dump(), "job_tracked": True}


@router.delete("/applications/{app_id}")
def delete_application(app_id: str):
    if not store.delete_application(app_id):
        raise HTTPException(404, f"application {app_id} not found")
    # If it was tracking a scanned job, make that job actionable again.
    job = store.get_job(app_id)
    if job and job.status == "applied":
        job.status = "open"
        store.upsert_job(job)
    return {"deleted": app_id}


@router.patch("/applications/{app_id}")
def update_application(app_id: str, payload: dict):
    """Update tracker fields (status, interview_date, contacts, notes) for an application."""
    app = store.get_application(app_id)
    if not app:
        raise HTTPException(404, f"application {app_id} not found")
    changes = {k: v for k, v in payload.items() if k in EDITABLE_APPLICATION_FIELDS}
    updated = app.model_copy(update=changes)
    store.upsert_application(updated)
    # Keep a linked tracked job's status in sync (linked apps share the job's id) so the
    # Jobs funnel and the Applications outcomes agree on where each application stands.
    if "status" in changes:
        job = store.get_job(app_id)
        if job and job.status != updated.status:
            store.upsert_job(job.model_copy(update={"status": updated.status}))
    return {"application": updated.model_dump()}


@router.get("/llm-status")
def llm_status():
    """Whether External-mode LLM calls are real or mock placeholders (no key configured).
    The web UI warns when External + mock so results aren't mistaken for real analysis."""
    from ..agent.llm import active_provider_is_mock
    from ..config import get_settings

    return {"mock": active_provider_is_mock(), "provider": get_settings().llm_provider.lower()}


@router.get("/profile")
def get_profile():
    # Fill in any missing skill category deterministically, so the Profile page can group
    # skills (Languages / Tools / …) even for profiles parsed before categories existed.
    profile = store.read_profile()
    for s in profile.get("skills") or []:
        if isinstance(s, dict):  # fill blanks AND clamp a non-canonical stored category
            s["category"] = normalize_category(s.get("category", ""), s.get("name", ""))
    return profile


@router.put("/profile")
def put_profile(payload: ProfileInput):
    """Store-only profile merge (Internal mode: Claude parses the CV in the terminal,
    then PUTs the extracted fields here). No LLM — mirrors POST /cv's merge, and only
    the CV-derived keys are accepted (can't clobber targets/comp/etc)."""
    return tools.save_profile(payload.model_dump(exclude_none=True))


@router.get("/preferences")
def get_preferences():
    """What the user is looking for (drives scan filtering + fit scoring)."""
    return store.read_targets()


@router.put("/preferences")
def put_preferences(payload: dict):
    store.write_targets(payload)
    return store.read_targets()


@router.post("/cv")
def submit_cv(payload: dict):
    """Submit CV text for parsing into the profile."""
    return tools.parse_cv(payload.get("cv_text", ""))


@router.post("/cv/upload")
async def upload_cv(file: UploadFile = File(...)):
    """Upload a CV file (PDF / .txt / .md), extract text, parse into the profile."""
    try:
        text = extract_text(file.filename or "", await file.read())
    except Exception as exc:  # corrupt/unsupported file
        raise HTTPException(422, f"could not read file: {exc}")
    if not text.strip():
        raise HTTPException(422, "no text could be extracted from the file")
    return tools.parse_cv(text)


@router.put("/cv/source")
def put_cv_source(payload: CvSourceInput):
    """Store-only: save the raw CV text so Internal-mode Claude can read + parse it."""
    if not payload.text.strip():  # don't overwrite an existing CV with nothing
        raise HTTPException(422, "empty CV text")
    return tools.save_cv_source(payload.text)


@router.post("/cv/source/upload")
async def upload_cv_source(file: UploadFile = File(...)):
    """Store-only: extract text from an uploaded CV (PDF/.txt/.md) and save it as the
    raw source for Internal-mode parsing — no LLM call."""
    try:
        text = extract_text(file.filename or "", await file.read())
    except Exception as exc:  # corrupt/unsupported file
        raise HTTPException(422, f"could not read file: {exc}")
    if not text.strip():
        raise HTTPException(422, "no text could be extracted from the file")
    return tools.save_cv_source(text)


def _resume_text() -> tuple[str, str]:
    """Resolve the master résumé under resume/ and return (text, rel_path), or 404/422."""
    src = store.resolve_resume_file()
    if src is None:
        raise HTTPException(404, "no résumé found — add a PDF / .tex / .md / .txt under resume/")
    try:
        text = extract_text(src.name, src.read_bytes())
    except Exception as exc:  # corrupt/unreadable file
        raise HTTPException(422, f"could not read {src.name}: {exc}")
    if not text.strip():
        raise HTTPException(422, f"no text could be extracted from {src.name}")
    return text, store.resume_rel(src)


@router.post("/cv/from-resume")
def cv_from_resume():
    """External: parse the résumé in resume/ (or profile.resume_path) into the profile,
    and record it as resume_path."""
    text, rel = _resume_text()
    result = tools.parse_cv(text)
    tools.save_profile({"resume_path": rel})  # remember the master résumé
    return {**result, "resume_path": rel}


@router.post("/cv/source/from-resume")
def cv_source_from_resume():
    """Store-only: stash the résumé text from resume/ for Internal-mode Claude to parse,
    and record it as resume_path."""
    text, rel = _resume_text()
    saved = tools.save_cv_source(text)
    tools.save_profile({"resume_path": rel})
    return {**saved, "resume_path": rel}
