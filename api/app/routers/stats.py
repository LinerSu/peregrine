"""Insights — aggregate pipeline metrics for the dashboard."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter

from .. import data_store as store
from ..stats import compute_insights, compute_outcomes

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("")
def stats():
    """Funnel, fit-score distribution, status counts, and weekly activity."""
    return compute_insights(store.list_jobs(), store.list_applications())


@router.get("/outcomes")
def outcomes():
    """Outcome / rejection analytics: conversion rates, outcome by fit-band & role,
    fit-score calibration, and stale-application follow-ups."""
    return compute_outcomes(store.list_applications(), date.today())
