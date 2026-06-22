"""Aggregate pipeline metrics for the Insights view.

Pure functions over the in-memory job/application lists — no I/O, no clock, so
the output is deterministic and easy to unit-test.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Any

from .schemas import Application, Job

# A job counts as "applied" once it has progressed to or past applying; likewise
# "interviewing" includes offers. These make the funnel monotonic supersets.
_APPLIED = {"applied", "interviewing", "offer", "rejected"}
_INTERVIEWING = {"interviewing", "offer"}

# An "applied" application with no interview scheduled this many days on is stale
# enough to suggest a follow-up.
_STALE_DAYS = 10

# Fit-score bands for outcome breakdown, in display order.
_FIT_BANDS = ("high (≥0.70)", "med (0.50–0.69)", "low (<0.50)", "unscored")


def _fit_band(s: float | None) -> str:
    if s is None or not math.isfinite(s):
        return "unscored"
    if s >= 0.7:
        return "high (≥0.70)"
    if s >= 0.5:
        return "med (0.50–0.69)"
    return "low (<0.50)"


def _iso_week(value: str) -> str | None:
    """'2026-06-15' -> '2026-W25'. None for blank/unparseable dates."""
    try:
        y, w, _ = date.fromisoformat(value).isocalendar()
        return f"{y}-W{w:02d}"
    except (ValueError, TypeError):
        return None


def compute_insights(jobs: list[Job], applications: list[Application]) -> dict[str, Any]:
    tracked = len(jobs)
    # Only finite scores count as "evaluated" — keeps the funnel consistent with
    # the histogram, which also excludes non-finite scores.
    evaluated = sum(1 for j in jobs if j.fit_score is not None and math.isfinite(j.fit_score))
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

    # Fit-score histogram: 5 buckets across [0, 1]. Skip non-finite scores and
    # clamp to [0, 1] so a stray nan/inf or out-of-range value can't crash this.
    buckets = [0, 0, 0, 0, 0]
    for j in jobs:
        s = j.fit_score
        if s is not None and math.isfinite(s):
            buckets[min(int(max(0.0, min(s, 1.0)) * 5), 4)] += 1
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


def compute_outcomes(applications: list[Application], today: date) -> dict[str, Any]:
    """Outcome / rejection analytics over APPLICATIONS — the record the user drives in
    the Applications view (a linked job's status is kept in sync, and orphan apps have
    no job, so applications are the complete + authoritative source here). Status is
    single-valued, so the rates are current-state ("where applications stand now"), not
    a historical funnel. Pure: the clock is injected via `today`."""

    def rate(n: int, d: int) -> float:
        return round(n / d, 3) if d else 0.0

    applied = [a for a in applications if a.status in _APPLIED]
    n_applied = len(applied)
    n_responded = sum(1 for a in applied if a.status in {"interviewing", "offer", "rejected"})
    n_interviewing = sum(1 for a in applied if a.status in _INTERVIEWING)
    n_offer = sum(1 for a in applied if a.status == "offer")
    n_rejected = sum(1 for a in applied if a.status == "rejected")

    # All rates share the stable "applied" base (n ≤ d, so each is in [0,1]).
    conversion = [
        {"label": "Heard back", "n": n_responded, "d": n_applied, "rate": rate(n_responded, n_applied)},
        {"label": "Interviewing or better", "n": n_interviewing, "d": n_applied, "rate": rate(n_interviewing, n_applied)},
        {"label": "Offer", "n": n_offer, "d": n_applied, "rate": rate(n_offer, n_applied)},
        {"label": "Rejected", "n": n_rejected, "d": n_applied, "rate": rate(n_rejected, n_applied)},
    ]

    # How each applied-to cohort stands (advanced = currently interviewing/offer),
    # grouped by fit-score band and by role category.
    def _group(key_fn) -> dict[str, dict[str, int]]:
        groups: dict[str, dict[str, int]] = {}
        for a in applied:
            g = groups.setdefault(key_fn(a), {"applied": 0, "advanced": 0, "offer": 0, "rejected": 0})
            g["applied"] += 1
            if a.status in _INTERVIEWING:
                g["advanced"] += 1
            if a.status == "offer":
                g["offer"] += 1
            if a.status == "rejected":
                g["rejected"] += 1
        return groups

    fit_groups = _group(lambda a: _fit_band(a.fit_score))
    by_fit_band = [
        {"band": b, **fit_groups[b], "advance_rate": rate(fit_groups[b]["advanced"], fit_groups[b]["applied"])}
        for b in _FIT_BANDS if b in fit_groups
    ]
    role_groups = _group(lambda a: a.role_category or "uncategorized")
    by_role = sorted(
        ({"role": r, **g, "advance_rate": rate(g["advanced"], g["applied"])} for r, g in role_groups.items()),
        key=lambda x: (-x["applied"], x["role"]),
    )

    # Calibration: does our fit score predict outcomes? Compare the average fit of
    # applications currently advancing vs those rejected.
    adv = [a.fit_score for a in applied
           if a.status in _INTERVIEWING and a.fit_score is not None and math.isfinite(a.fit_score)]
    rej = [a.fit_score for a in applied
           if a.status == "rejected" and a.fit_score is not None and math.isfinite(a.fit_score)]
    calibration = {
        "advanced_avg_fit": round(sum(adv) / len(adv), 3) if adv else None,
        "advanced_n": len(adv),
        "rejected_avg_fit": round(sum(rej) / len(rej), 3) if rej else None,
        "rejected_n": len(rej),
    }

    # Follow-ups: applications still "applied", no interview scheduled, stale.
    follow_ups = []
    for a in applications:
        if a.status == "applied" and not a.interview_date and a.applied_date:
            try:
                d0 = date.fromisoformat(a.applied_date)
            except (ValueError, TypeError):
                continue
            days = (today - d0).days
            if days >= _STALE_DAYS:
                follow_ups.append({
                    "id": a.id, "company": a.company, "position": a.position,
                    "applied_date": a.applied_date, "days": days,
                })
    follow_ups.sort(key=lambda x: (-x["days"], x["company"]))

    return {
        "conversion": conversion,
        "by_fit_band": by_fit_band,
        "by_role": by_role,
        "calibration": calibration,
        "follow_ups": follow_ups,
        "stale_days": _STALE_DAYS,
    }
