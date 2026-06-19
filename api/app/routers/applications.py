"""Applications + profile/CV endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import data_store as store
from ..agent import tools

router = APIRouter(prefix="/api", tags=["applications"])

# Tracker fields the user may edit from the Applications view.
EDITABLE_APPLICATION_FIELDS = {"status", "interview_date", "applied_date", "contacts", "notes"}


@router.get("/applications")
def list_applications():
    apps = store.list_applications()
    return {"count": len(apps), "applications": [a.model_dump() for a in apps]}


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


@router.post("/cv")
def submit_cv(payload: dict):
    """Submit CV text for parsing into the profile."""
    return tools.parse_cv(payload.get("cv_text", ""))
