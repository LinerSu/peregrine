"""Applications + profile/CV endpoints."""
from __future__ import annotations

from fastapi import APIRouter

from .. import data_store as store
from ..agent import tools

router = APIRouter(prefix="/api", tags=["applications"])


@router.get("/applications")
def list_applications():
    apps = store.list_applications()
    return {"count": len(apps), "applications": [a.model_dump() for a in apps]}


@router.get("/profile")
def get_profile():
    return store.read_profile()


@router.post("/cv")
def submit_cv(payload: dict):
    """Submit CV text for parsing into the profile."""
    return tools.parse_cv(payload.get("cv_text", ""))
