"""Insights — aggregate pipeline metrics for the dashboard."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException

from .. import data_store as store
from ..agent import tools
from ..stats import compute_insights, compute_outcomes

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("")
def stats():
    """Funnel, fit-score distribution, status counts, and weekly activity."""
    return compute_insights(store.list_jobs(), store.list_applications())


@router.get("/outcomes")
def outcomes():
    """Outcome / rejection analytics: conversion rates, outcome by fit-band & role,
    fit-score calibration, stale-application follow-ups, and the aggregate skill gaps
    (what to learn next) across your live roles + stalled applications."""
    apps = store.list_applications()
    result = compute_outcomes(apps, date.today())
    # Skill gaps are scoped to your TARGET roles (the search queries), not every live posting — so
    # off-target roles don't dominate "what to learn" (a designer told to learn Python). Shared with
    # the External narrative path via tools.scoped_skill_gaps.
    result["skill_gaps"] = tools.scoped_skill_gaps(apps)
    return result


@router.post("/patterns")
def analyze_patterns():
    """External: LLM narrative over the outcome analytics (what's working / at risk / to do)."""
    return tools.analyze_patterns()


@router.put("/patterns")
def save_patterns(payload: dict):
    """Internal store-only: local Claude analyzes the outcomes and PUTs its narrative here."""
    summary = payload.get("summary")
    if not (isinstance(summary, str) and summary.strip()):
        raise HTTPException(422, "patterns insight needs a non-empty string 'summary'")
    return tools.save_patterns(payload)


@router.get("/patterns")
def get_patterns():
    """Read the last saved pattern-insights narrative ({} if none) — the UI poll target."""
    return tools.get_patterns()
