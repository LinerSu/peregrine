"""Insights — aggregate pipeline metrics for the dashboard."""
from __future__ import annotations

from fastapi import APIRouter

from .. import data_store as store
from ..stats import compute_insights

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("")
def stats():
    """Funnel, fit-score distribution, status counts, and weekly activity."""
    return compute_insights(store.list_jobs(), store.list_applications())
