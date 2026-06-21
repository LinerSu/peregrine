"""Insights metrics: funnel, score distribution, weekly activity."""
from app.schemas import Application, Job
from app.stats import compute_insights


def _job(jid, status="open", fit=None, posted="2026-06-15"):
    return Job(id=jid, company="Acme", company_job_id=jid, position="Eng",
               status=status, fit_score=fit, posted_date=posted)


def test_funnel_is_monotonic_superset():
    jobs = [
        _job("1", "open"),
        _job("2", "open", fit=0.8),
        _job("3", "applied", fit=0.6),
        _job("4", "interviewing", fit=0.7),
        _job("5", "offer", fit=0.9),
        _job("6", "rejected", fit=0.3),
    ]
    counts = {f["stage"]: f["count"] for f in compute_insights(jobs, [])["funnel"]}
    assert counts["Tracked"] == 6
    assert counts["Evaluated"] == 5          # fit set on jobs 2..6
    assert counts["Applied"] == 4            # applied + interviewing + offer + rejected
    assert counts["Interviewing"] == 2       # interviewing + offer
    assert counts["Offer"] == 1
    assert counts["Tracked"] >= counts["Applied"] >= counts["Interviewing"] >= counts["Offer"]


def test_score_distribution_buckets():
    jobs = [_job("1", fit=0.05), _job("2", fit=0.25), _job("3", fit=0.95), _job("4")]  # job 4 unscored
    sd = compute_insights(jobs, [])["score_distribution"]
    assert len(sd) == 5
    assert sd[0]["count"] == 1   # 0.0–0.2
    assert sd[1]["count"] == 1   # 0.2–0.4
    assert sd[4]["count"] == 1   # 0.8–1.0
    assert sum(b["count"] for b in sd) == 3  # the unscored job is excluded


def test_weekly_activity_groups_by_iso_week():
    jobs = [_job("1", posted="2026-06-15"), _job("2", posted="2026-06-15")]  # same week
    apps = [Application(id="3", company="Acme", company_job_id="3", position="Eng",
                        applied_date="2026-06-15")]
    act = compute_insights(jobs, apps)["activity"]
    assert len(act) == 1
    assert act[0]["added"] == 2
    assert act[0]["applied"] == 1


def test_by_status_and_totals():
    jobs = [_job("1", "open"), _job("2", "open"), _job("3", "applied", fit=0.5)]
    out = compute_insights(jobs, [])
    assert out["by_status"] == {"open": 2, "applied": 1}
    assert out["totals"] == {"jobs": 3, "applications": 0, "evaluated": 1}


def test_nonfinite_fit_score_does_not_crash():
    # A stray nan must not break /api/stats; it's excluded from the histogram.
    jobs = [_job("1", fit=float("nan")), _job("2", fit=0.5)]
    sd = compute_insights(jobs, [])["score_distribution"]
    assert sum(b["count"] for b in sd) == 1


def test_empty_data():
    out = compute_insights([], [])
    assert out["totals"]["jobs"] == 0
    assert all(f["count"] == 0 for f in out["funnel"])
    assert out["activity"] == []
    assert out["by_status"] == {}
    assert sum(b["count"] for b in out["score_distribution"]) == 0
