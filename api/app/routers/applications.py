"""Applications + profile/CV endpoints."""
from __future__ import annotations

import io
from datetime import date

from fastapi import APIRouter, File, HTTPException, UploadFile

from .. import data_store as store
from ..agent import tools
from ..schemas import Application

router = APIRouter(prefix="/api", tags=["applications"])

# Tracker fields the user may edit from the Applications view.
EDITABLE_APPLICATION_FIELDS = {"status", "interview_date", "applied_date", "contacts", "notes"}


@router.get("/applications")
def list_applications():
    apps = store.list_applications()
    return {"count": len(apps), "applications": [a.model_dump() for a in apps]}


@router.post("/applications")
def create_application(payload: dict):
    """Manually track an application (e.g. one you applied to outside Peregrine)."""
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
    return {"application": app.model_dump()}


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
    return {"application": updated.model_dump()}


@router.get("/profile")
def get_profile():
    return store.read_profile()


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


def _extract_text(filename: str, raw: bytes) -> str:
    if (filename or "").lower().endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(raw))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    return raw.decode("utf-8", errors="ignore")


@router.post("/cv/upload")
async def upload_cv(file: UploadFile = File(...)):
    """Upload a CV file (PDF / .txt / .md), extract text, parse into the profile."""
    try:
        text = _extract_text(file.filename or "", await file.read())
    except Exception as exc:  # corrupt/unsupported file
        raise HTTPException(422, f"could not read file: {exc}")
    if not text.strip():
        raise HTTPException(422, "no text could be extracted from the file")
    return tools.parse_cv(text)
