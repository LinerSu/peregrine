"""Outcome / rejection analytics (stats.compute_outcomes) — over applications, clock injected."""
from datetime import date

from app.schemas import Application, Job
from app.stats import compute_outcomes, compute_skill_gaps

TODAY = date(2026, 6, 22)


def test_skill_gaps_ranks_by_unlocked_roles_with_outcome_signal():
    jobs = [
        # Golang is the canonical token extract_skills emits (bare "Go" never appears in req_skills).
        Job(id="1", company="A", company_job_id="1", position="X", req_skills="Python, Kubernetes, Golang", status="open"),
        Job(id="2", company="B", company_job_id="2", position="Y", req_skills="Kubernetes, Docker", status="open"),
        Job(id="3", company="C", company_job_id="3", position="Z", req_skills="Kubernetes", status="closed"),  # dead -> ignored
    ]
    apps = [
        Application(id="4", company="D", company_job_id="4", position="W", req_skills="Kubernetes, Golang",
                    status="rejected", applied_date="2026-06-01"),
    ]
    gaps = compute_skill_gaps(jobs, apps, user_skills={"Python", "Docker"})
    top = gaps[0]
    assert top["skill"] == "Kubernetes"  # required by 2 LIVE roles (closed one ignored)
    assert top["required_by"] == 2 and top["missed_in_stalled"] == 1
    assert all(g["skill"] not in ("Python", "Docker") for g in gaps)  # user's own skills aren't gaps
    go = next(g for g in gaps if g["skill"] == "Golang")
    assert go["required_by"] == 1 and go["missed_in_stalled"] == 1


def _app(aid, status, fit=None, role="", applied="2026-06-10", interview=""):
    return Application(id=aid, company=f"C{aid}", company_job_id=f"R{aid}", position="Eng",
                       status=status, fit_score=fit, role_category=role,
                       applied_date=applied, interview_date=interview)


def test_conversion_rates_over_applied_base():
    apps = [
        _app("1", "applied", 0.8),
        _app("2", "interviewing", 0.6),
        _app("3", "offer", 0.9),
        _app("4", "rejected", 0.4),
        _app("5", "closed", 0.5),  # withdrawn -> excluded from the applied base
    ]
    o = compute_outcomes(apps, TODAY)
    conv = {c["label"]: c for c in o["conversion"]}
    assert conv["Heard back"]["d"] == 4              # applied base = applied+interviewing+offer+rejected
    assert conv["Heard back"]["n"] == 3              # interviewing+offer+rejected (still "applied" = no response)
    assert conv["Interviewing or better"]["n"] == 2  # interviewing+offer
    assert conv["Offer"]["n"] == 1 and conv["Offer"]["rate"] == round(1 / 4, 3)
    assert conv["Rejected"]["n"] == 1
    assert all(0.0 <= c["rate"] <= 1.0 and c["n"] <= c["d"] for c in o["conversion"])  # never > 1


def test_rejected_after_interview_counts_as_rejected_not_advanced():
    # status is single-valued: an interviewed-then-rejected app is "rejected" now.
    apps = [_app("1", "rejected", 0.95), _app("2", "offer", 0.6)]
    o = compute_outcomes(apps, TODAY)
    conv = {c["label"]: c for c in o["conversion"]}
    assert conv["Interviewing or better"]["n"] == 1  # only the offer; rejected is terminal
    assert conv["Rejected"]["n"] == 1 and conv["Heard back"]["n"] == 2
    assert all(c["rate"] <= 1.0 for c in o["conversion"])


def test_by_fit_band_and_calibration():
    apps = [
        _app("1", "offer", 0.9),          # high: advanced + offer
        _app("2", "interviewing", 0.75),  # high: advanced
        _app("3", "rejected", 0.72),      # high: rejected
        _app("4", "applied", 0.55),       # med
        _app("5", "rejected", 0.4),       # low
    ]
    o = compute_outcomes(apps, TODAY)
    high = next(b for b in o["by_fit_band"] if b["band"] == "high (≥0.70)")
    assert (high["applied"], high["advanced"], high["offer"], high["rejected"]) == (3, 2, 1, 1)
    assert high["advance_rate"] == round(2 / 3, 3)
    cal = o["calibration"]
    assert cal["advanced_n"] == 2 and cal["rejected_n"] == 2
    assert cal["advanced_avg_fit"] == round((0.9 + 0.75) / 2, 3)
    assert cal["rejected_avg_fit"] == round((0.72 + 0.4) / 2, 3)


def test_by_role_sorted_and_unscored_band():
    apps = [
        _app("1", "applied", None, role="Engineering"),  # unscored (e.g. orphan, no fit)
        _app("2", "offer", 0.8, role="Engineering"),
        _app("3", "rejected", 0.3, role="Design"),
    ]
    o = compute_outcomes(apps, TODAY)
    assert o["by_role"][0]["role"] == "Engineering" and o["by_role"][0]["applied"] == 2  # most-applied first
    assert any(b["band"] == "unscored" and b["applied"] == 1 for b in o["by_fit_band"])


def test_follow_ups_stale_future_and_unparseable():
    apps = [
        _app("1", "applied", applied="2026-06-01"),                       # 21d -> stale
        _app("2", "applied", applied="2026-06-20", interview="2026-06-25"),  # has interview -> skip
        _app("3", "applied", applied="2026-06-21"),                       # 1d -> not stale
        _app("4", "interviewing", applied="2026-05-01"),                  # not "applied" -> skip
        _app("5", "applied", applied="2099-01-01"),                       # future -> negative days -> skip
        _app("6", "applied", applied="not-a-date"),                       # unparseable -> skip
    ]
    fu = compute_outcomes(apps, TODAY)["follow_ups"]
    assert [f["id"] for f in fu] == ["1"] and fu[0]["days"] == 21


def test_empty_is_safe():
    o = compute_outcomes([], TODAY)
    assert o["conversion"][0]["d"] == 0 and o["conversion"][0]["rate"] == 0.0
    assert o["by_fit_band"] == [] and o["by_role"] == [] and o["follow_ups"] == []
    assert o["calibration"]["advanced_avg_fit"] is None


def test_outcomes_endpoint_smoke(tmp_path, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "JOBS_CSV", tmp_path / "jobs.csv")
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(config, "APPLICATIONS_CSV", tmp_path / "applications.csv")
    from fastapi.testclient import TestClient

    from app.main import app

    r = TestClient(app).get("/api/stats/outcomes")
    assert r.status_code == 200
    assert {"conversion", "by_fit_band", "by_role", "calibration", "follow_ups", "stale_days"} <= r.json().keys()


def _seed_designer_targets(tmp_path, monkeypatch):
    """Isolate the store + portals for a designer (query 'designer'): a TARGET design role, an
    off-target board role, and a query-based Amazon ML role (relevant in the Jobs view, but NOT a
    skill-gap target). Empty profile -> every req skill is a gap."""
    from app import config, data_store as store

    monkeypatch.setattr(config, "JOBS_CSV", tmp_path / "jobs.csv")
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(config, "APPLICATIONS_CSV", tmp_path / "applications.csv")
    monkeypatch.setattr(config, "PROFILE_YML", tmp_path / "profile.yml")
    monkeypatch.setattr(config, "PATTERNS_FILE", tmp_path / "patterns.json")
    pf = tmp_path / "portals.yml"
    pf.write_text("companies:\n  - {name: Amazon, provider: amazon, slug: machine learning engineer}\nqueries:\n  - designer\n")
    monkeypatch.setattr(config, "PORTALS_YML", pf)
    store.upsert_job(Job(id="2026-001", company="A", company_job_id="1", position="Product Designer",
                         req_skills="Figma, Sketch", status="open"))          # TARGET (matches "designer")
    store.upsert_job(Job(id="2026-002", company="B", company_job_id="2", position="Backend Engineer",
                         req_skills="Python, SQL", status="open"))            # off-target board role
    store.upsert_job(Job(id="2026-003", company="Amazon", company_job_id="3", position="Machine Learning Engineer",
                         req_skills="Java, C++, Perl", status="open"))         # query-based, but not a design target


def test_outcomes_skill_gaps_scoped_to_relevant_jobs(tmp_path, monkeypatch):
    # /outcomes (Internal path): skill gaps reflect the user's TARGET roles, not every live posting.
    _seed_designer_targets(tmp_path, monkeypatch)

    from fastapi.testclient import TestClient

    from app.main import app

    gaps = {g["skill"] for g in TestClient(app).get("/api/stats/outcomes").json()["skill_gaps"]}
    assert {"Figma", "Sketch"} <= gaps                            # from the target design role
    assert {"Python", "SQL"}.isdisjoint(gaps)                     # off-target board role excluded
    assert {"Java", "C++", "Perl"}.isdisjoint(gaps)              # query-based Amazon ML job excluded too


def test_analyze_patterns_scopes_skill_gaps_like_the_endpoint(tmp_path, monkeypatch):
    # External path (analyze_patterns -> patterns_analyst): the narrative is grounded in the SAME
    # target-scoped skill gaps as /outcomes — they share tools.scoped_skill_gaps, so they can't drift.
    _seed_designer_targets(tmp_path, monkeypatch)
    from app.agent import tools

    captured: dict = {}
    monkeypatch.setattr(tools, "patterns_analyst", lambda outcomes: captured.update(outcomes) or {"summary": "ok"})
    monkeypatch.setattr(tools.status, "record", lambda *a, **k: None)
    tools.analyze_patterns()

    gaps = {g["skill"] for g in captured.get("skill_gaps", [])}
    assert {"Figma", "Sketch"} <= gaps
    assert {"Python", "SQL", "Java", "C++", "Perl"}.isdisjoint(gaps)
