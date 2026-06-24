"""Unit tests for tool logic: scan filtering, evaluation merge, mark-applied."""
from datetime import date

from app.agent import providers, tools


def _rp(position="Engineer", location="Remote", description=""):
    return providers.RawPosting(
        company="Acme", company_job_id="1", position=position, location=location, description=description
    )


# --- _passes_filters --------------------------------------------------------
def test_filter_location_match_and_miss():
    p = _rp(location="San Francisco, CA")
    assert tools._passes_filters(p, {"locations": ["san francisco"]}, {})
    assert not tools._passes_filters(p, {"locations": ["new york"]}, {})


def test_filter_remote_passes_location_gate():
    # A remote posting should never be filtered out by a location list.
    p = _rp(location="Remote - US")
    assert tools._passes_filters(p, {"locations": ["new york"]}, {})


def test_filter_work_mode_remote():
    assert not tools._passes_filters(_rp(location="Seattle"), {}, {"work_mode": "remote"})
    assert tools._passes_filters(_rp(location="Remote"), {}, {"work_mode": "remote"})


def test_filter_include_exclude_keywords():
    p = _rp(position="Backend Engineer", description="python and kafka")
    assert tools._passes_filters(p, {}, {"include_keywords": ["python"]})
    assert not tools._passes_filters(p, {}, {"include_keywords": ["rust"]})
    assert not tools._passes_filters(p, {}, {"exclude_keywords": ["kafka"]})


# --- relevance gate (portals.queries) ---------------------------------------
def test_query_matches_all_words_not_exact_phrase():
    # all the query's words must appear (scattered is fine) — exact phrase isn't required
    assert tools._query_matches("research engineer, machine learning (rl)", "machine learning engineer")
    assert tools._query_matches("senior machine learning engineer, platform", "machine learning engineer")
    assert not tools._query_matches("staff software engineer, payments", "machine learning engineer")
    assert not tools._query_matches("technical recruiter", "machine learning engineer")
    # tokens ending in + / # still match (custom boundary, not \b which is \w-based)
    assert tools._query_matches("strong c++ and rust", "c++")
    assert tools._query_matches("c# / .net backend", "c#")
    assert not tools._query_matches("a cobol shop", "c++")  # 'c' alone shouldn't match c++
    assert not tools._query_matches("pythonic code", "python")  # substring guard still holds


def test_matches_queries_relevance_gate():
    # relevance is judged on the title+tags surface (_relevance_text), identically at scan and
    # serve time, so a scanned-in job is never then hidden as off-target.
    ml = tools._relevance_text("Machine Learning Engineer", "Machine Learning", "Python", "ML Engineer")
    sales = tools._relevance_text("Account Executive", "", "", "Sales/GTM")
    q = ["machine learning engineer", "applied scientist"]
    assert tools._matches_queries(ml, q)
    assert not tools._matches_queries(sales, q)
    # no queries -> everything relevant (no regression for users who haven't set any)
    assert tools._matches_queries(sales, [])
    assert tools._matches_queries(sales, None)


def test_targets_locations_override_portal_filters():
    p = _rp(location="Austin, TX")
    assert tools._passes_filters(p, {"locations": ["boston"]}, {"locations": ["austin"]})


# --- _merge_evaluation ------------------------------------------------------
def test_merge_evaluation_replaces_not_duplicates():
    base = "# Job — Acme\n\nbody\n\n## Agent evaluation\n- _pending_\n"
    ev = {"fit_score": 0.8, "recommendation": "apply", "strengths": ["s1"], "weaknesses": ["w1"], "materials": ["m1"]}
    out = tools._merge_evaluation(base, ev)
    assert out.count("## Agent evaluation") == 1
    assert "0.8" in out and "s1" in out and "w1" in out and "m1" in out


# --- mark_applied -----------------------------------------------------------
def test_mark_applied_creates_and_preserves(tmp_path, monkeypatch):
    from app import config
    from app import data_store as store
    from app.schemas import Job

    monkeypatch.setattr(config, "JOBS_CSV", tmp_path / "jobs.csv")
    monkeypatch.setattr(config, "APPLICATIONS_CSV", tmp_path / "applications.csv")
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(tools.status, "record", lambda *a, **k: None)

    store.upsert_job(Job(id="2026-001", company="Acme", company_job_id="R1", position="Eng"))
    res = tools.mark_applied("2026-001")
    assert res["created"] is True
    assert res["application"]["status"] == "applied"
    assert res["application"]["applied_date"] == date.today().isoformat()
    assert store.get_job("2026-001").status == "applied"

    # User edits a tracker field; re-marking applied must not clobber it.
    a = store.get_application("2026-001")
    a.notes = "recruiter call booked"
    store.upsert_application(a)
    tools.mark_applied("2026-001")
    assert store.get_application("2026-001").notes == "recruiter call booked"


def test_mark_applied_missing_job():
    assert "error" in tools.mark_applied("nope-999")
