"""Aggregate pipeline metrics for the Insights view.

Pure functions over the in-memory job/application lists — no I/O, no clock, so
the output is deterministic and easy to unit-test.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from .schemas import Application, Job

# A job counts as "applied" once it has progressed to or past applying; likewise
# "interviewing" includes offers. These make the funnel monotonic supersets.
_APPLIED = {"applied", "interviewing", "offer", "rejected"}
_INTERVIEWING = {"interviewing", "offer"}


def _iso_week(value: str) -> str | None:
    """'2026-06-15' -> '2026-W25'. None for blank/unparseable dates."""
    try:
        y, w, _ = date.fromisoformat(value).isocalendar()
        return f"{y}-W{w:02d}"
    except (ValueError, TypeError):
        return None


def compute_insights(jobs: list[Job], applications: list[Application]) -> dict[str, Any]:
    tracked = len(jobs)
    evaluated = sum(1 for j in jobs if j.fit_score is not None)
    applied = sum(1 for j in jobs if j.status in _APPLIED)
    interviewing = sum(1 for j in jobs if j.status in _INTERVIEWING)
    offer = sum(1 for j in jobs if j.status == "offer")

    def rate(n: int, d: int) -> float:
        return round(n / d, 3) if d else 0.0

    funnel = [
        {"stage": "Tracked", "count": tracked, "rate": 1.0 if tracked else 0.0},
        {"stage": "Evaluated", "count": evaluated, "rate": rate(evaluated, tracked)},
        {"stage": "Applied", "count": applied, "rate": rate(applied, tracked)},
        {"stage": "Interviewing", "count": interviewing, "rate": rate(interviewing, tracked)},
        {"stage": "Offer", "count": offer, "rate": rate(offer, tracked)},
    ]

    # Fit-score histogram: 5 buckets across [0, 1].
    buckets = [0, 0, 0, 0, 0]
    for j in jobs:
        if j.fit_score is not None:
            buckets[min(int(max(j.fit_score, 0.0) * 5), 4)] += 1
    score_distribution = [
        {"range": f"{i * 0.2:.1f}–{(i + 1) * 0.2:.1f}", "count": c}
        for i, c in enumerate(buckets)
    ]

    by_status: dict[str, int] = {}
    for j in jobs:
        by_status[j.status] = by_status.get(j.status, 0) + 1

    # Weekly activity: jobs added (by posted_date) + applications (by applied_date).
    weeks: dict[str, dict[str, int]] = {}
    for j in jobs:
        w = _iso_week(j.posted_date)
        if w:
            weeks.setdefault(w, {"added": 0, "applied": 0})["added"] += 1
    for a in applications:
        w = _iso_week(a.applied_date)
        if w:
            weeks.setdefault(w, {"added": 0, "applied": 0})["applied"] += 1
    activity = [
        {"week": w, "added": v["added"], "applied": v["applied"]}
        for w, v in sorted(weeks.items())
    ]

    return {
        "funnel": funnel,
        "score_distribution": score_distribution,
        "by_status": by_status,
        "activity": activity,
        "totals": {"jobs": tracked, "applications": len(applications), "evaluated": evaluated},
    }
