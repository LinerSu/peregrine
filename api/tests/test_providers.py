"""Provider URL detection + pure parsing helpers (no network)."""
import pytest

from app.agent import providers as P
from app.agent.providers import PolicyViolation


def test_url_regexes_match():
    assert P._AMAZON_RE.search("https://www.amazon.jobs/en/jobs/3196773")
    assert P._APPLE_RE.search("https://jobs.apple.com/en-us/details/200668037-0836/x")
    assert P._ASHBY_RE.search("https://jobs.ashbyhq.com/openai/8fb1615c-34bf-47c4")
    assert P._LEVER_RE.search("https://jobs.lever.co/leverdemo/33538a2f-d27d")
    assert P._GREENHOUSE_RE.search("https://job-boards.greenhouse.io/acme/jobs/4521")


def test_epoch_ms_to_date():
    assert P._epoch_ms_to_date(0) == "1970-01-01"
    assert P._epoch_ms_to_date(None) == ""
    assert P._epoch_ms_to_date("nope") == ""


def test_strip_html():
    assert P._strip_html("<p>hi <b>there</b></p>") == "hi there"


def test_find_apple_posting_walks_to_node():
    data = {"loaderData": [{"noise": 1}, {"positionId": "1", "locations": [{"name": "Cupertino"}], "postingTitle": "TPM"}]}
    node = P._find_apple_posting(data)
    assert node and node["postingTitle"] == "TPM"


def test_ingest_url_blocks_linkedin():
    with pytest.raises(PolicyViolation):
        P.ingest_url("https://www.linkedin.com/jobs/view/123/")


def test_ingest_url_unsupported_is_none():
    assert P.ingest_url("https://example.com/some-job") is None


def test_parse_recruitee():
    data = {
        "offers": [
            {"id": 42, "title": "Backend Engineer", "location": "Berlin, DE",
             "careers_url": "https://channable.recruitee.com/o/backend",
             "created_at": "2026-06-01T10:00:00", "description": "<p>Build <b>things</b></p>"},
            {"id": 7, "title": "PM", "city": "Amsterdam", "country": "NL", "remote": True,
             "url": "https://evil.com/o/pm"},  # off-domain -> url dropped
        ]
    }
    out = P._parse_recruitee(data, "Channable")
    assert out[0].company == "Channable" and out[0].company_job_id == "42"
    assert out[0].position == "Backend Engineer" and out[0].location == "Berlin, DE"
    assert out[0].url == "https://channable.recruitee.com/o/backend"
    assert out[0].posted_date == "2026-06-01" and out[0].description == "Build things"
    assert out[1].location == "Amsterdam, NL, Remote" and out[1].url == ""  # assembled + dropped


def test_parse_smartrecruiters():
    data = {
        "content": [
            {"id": "abc-123", "name": "Data Scientist",
             "location": {"city": "Paris", "country": "France", "remote": True},
             "releasedDate": "2026-05-20T09:00:00Z"},
            {"id": "def-456", "name": "Designer", "location": {"fullLocation": "Remote - EU"}},
        ]
    }
    out = P._parse_smartrecruiters(data, "Adyen", "adyen")
    assert out[0].company_job_id == "abc-123" and out[0].position == "Data Scientist"
    assert out[0].location == "Paris, France, Remote"
    assert out[0].url == "https://jobs.smartrecruiters.com/adyen/abc-123"
    assert out[0].posted_date == "2026-05-20"
    assert out[1].location == "Remote - EU"


def test_parse_workable():
    md = (
        "| Title | Department | Location | Type | Salary | Posted | Link |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n"
        "| Senior Engineer | Eng | Remote | Full-time |  | 2026-06-01 "
        "| [View](https://apply.workable.com/optimile/jobs/view/ABC123.md) |\n"
        "| Off Domain | X | Y | Z |  |  | [View](https://evil.example/apply.workable.com/x) |\n"
    )
    out = P._parse_workable(md, "Optimile")
    assert len(out) == 1  # header, separator, and the off-domain row are all skipped
    assert out[0].company == "Optimile" and out[0].position == "Senior Engineer"
    assert out[0].company_job_id == "ABC123" and out[0].location == "Remote"
    assert out[0].url == "https://apply.workable.com/optimile/jobs/view/ABC123"


def test_new_parsers_survive_malformed_payloads():
    # null/missing/wrong-typed fields must not crash or yield position=None (which would
    # fail Job validation and abort a live scan).
    assert P._parse_recruitee({}, "X") == []                 # no "offers" key
    assert P._parse_smartrecruiters({}, "X", "x") == []      # no "content" key
    rec = P._parse_recruitee({"offers": [{"id": None, "title": None}]}, "X")
    assert rec[0].position == "" and rec[0].company_job_id == ""  # null-safe, not None
    sr = P._parse_smartrecruiters({"content": [{"name": None, "location": "Remote"}]}, "X", "x")
    assert sr[0].position == "" and sr[0].location == ""     # location-as-string doesn't crash
    sr2 = P._parse_smartrecruiters({"content": [{"id": "k", "location": None}]}, "X", "x")
    assert sr2[0].location == "" and sr2[0].url.endswith("/x/k")


def test_scan_dedups_within_and_across_scans(tmp_path, monkeypatch):
    # Clicking Scan must never add a duplicate job — within one scan (same posting twice)
    # or across re-scans (already-tracked jobs). Dedup key = company + company_job_id.
    from app import config
    from app.agent import tools

    monkeypatch.setattr(config, "JOBS_CSV", tmp_path / "jobs.csv")
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(config, "APPLICATIONS_CSV", tmp_path / "applications.csv")
    monkeypatch.setattr(config, "PORTALS_YML", tmp_path / "portals.yml")
    monkeypatch.setattr(tools.status, "record", lambda *a, **k: None)
    monkeypatch.setattr(tools.store, "read_targets", lambda: {})
    monkeypatch.setattr(tools.store, "read_portals",
                        lambda: {"companies": [{"name": "Acme", "provider": "x", "slug": "x"}], "snapshot": False})
    monkeypatch.setattr(tools.providers, "fetch", lambda *a: [
        P.RawPosting(company="Acme", company_job_id="R1", position="Engineer", location="NYC"),
        P.RawPosting(company="acme", company_job_id="r1", position="Engineer", location="NYC"),  # case-variant dup
        P.RawPosting(company="Acme", company_job_id="R2", position="PM", location="SF"),
    ])
    r1 = tools.scan_jobs()
    assert r1["new"] == 2 and r1["duplicates"] == 1     # R1 once (case-variant is a within-scan dup) + R2
    assert len(tools.store.list_jobs()) == 2
    r2 = tools.scan_jobs()                                # re-scan the same feed
    assert r2["new"] == 0 and r2["duplicates"] == 3      # everything already tracked
    assert len(tools.store.list_jobs()) == 2             # still 2 — no duplicates added


def test_scan_marks_disappeared_jobs_closed(tmp_path, monkeypatch):
    # A posting that drops off the board on a later scan is "dead" -> marked closed (kept,
    # not deleted). Applied jobs and a failed/empty fetch must never be pruned.
    from app import config
    from app.agent import tools

    monkeypatch.setattr(config, "JOBS_CSV", tmp_path / "jobs.csv")
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(config, "APPLICATIONS_CSV", tmp_path / "applications.csv")
    monkeypatch.setattr(config, "PORTALS_YML", tmp_path / "portals.yml")
    monkeypatch.setattr(tools.status, "record", lambda *a, **k: None)
    monkeypatch.setattr(tools.store, "read_targets", lambda: {})
    monkeypatch.setattr(tools.store, "read_portals",
                        lambda: {"companies": [{"name": "Acme", "provider": "x", "slug": "x"}], "snapshot": False})

    board = [
        P.RawPosting(company="Acme", company_job_id="R1", position="Engineer", location="NYC"),
        P.RawPosting(company="Acme", company_job_id="R2", position="PM", location="SF"),
        P.RawPosting(company="Acme", company_job_id="R3", position="Designer", location="LA"),
    ]
    monkeypatch.setattr(tools.providers, "fetch", lambda *a: list(board))
    tools.scan_jobs()
    by_key = lambda k: next(j for j in tools.store.list_jobs() if j.company_job_id == k)
    # Mark R2 as applied so we can prove applied jobs survive pruning.
    r2job = by_key("R2"); r2job.status = "applied"; tools.store.upsert_job(r2job)

    board[:] = [board[2]]  # R1 and R2 both disappear; only R3 still listed
    res = tools.scan_jobs()
    assert res["dead"] == 1                       # only R1 pruned (R2 is applied, R3 still listed)
    assert by_key("R1").status == "closed"        # disappeared OPEN job -> closed
    assert by_key("R2").status == "applied"       # disappeared APPLIED job -> left untouched (you still applied)
    assert by_key("R3").status == "open"          # still listed -> stays open

    # A failed/empty fetch (returns []) must NOT prune the surviving open job.
    monkeypatch.setattr(tools.providers, "fetch", lambda *a: [])
    res2 = tools.scan_jobs()
    assert res2["dead"] == 0
    assert by_key("R3").status == "open"


def _scan_setup(tmp_path, monkeypatch, portals):
    from app import config
    from app.agent import tools

    monkeypatch.setattr(config, "JOBS_CSV", tmp_path / "jobs.csv")
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(config, "APPLICATIONS_CSV", tmp_path / "applications.csv")
    monkeypatch.setattr(config, "PORTALS_YML", tmp_path / "portals.yml")
    monkeypatch.setattr(tools.status, "record", lambda *a, **k: None)
    monkeypatch.setattr(tools.store, "read_targets", lambda: {})
    monkeypatch.setattr(tools.store, "read_portals", lambda: portals)
    return tools


def test_scan_age_filter_skips_old_postings(tmp_path, monkeypatch):
    # filters.max_age_days skips postings older than the cutoff; a missing date is kept.
    from datetime import date, timedelta

    tools = _scan_setup(tmp_path, monkeypatch, {
        "companies": [{"name": "Acme", "provider": "x", "slug": "x"}],
        "filters": {"max_age_days": 60}, "snapshot": False,
    })
    recent = (date.today() - timedelta(days=10)).isoformat()
    old = (date.today() - timedelta(days=120)).isoformat()
    monkeypatch.setattr(tools.providers, "fetch", lambda *a: [
        P.RawPosting(company="Acme", company_job_id="R1", position="Eng", posted_date=recent),
        P.RawPosting(company="Acme", company_job_id="R2", position="PM", posted_date=old),     # too old
        P.RawPosting(company="Acme", company_job_id="R3", position="Dev", posted_date=""),      # undatable -> kept
    ])
    r = tools.scan_jobs()
    assert r["new"] == 2 and r["filtered"] == 1
    assert {j.company_job_id for j in tools.store.list_jobs()} == {"R1", "R3"}


def test_scan_prunes_aged_open_jobs(tmp_path, monkeypatch):
    # An OPEN job that has aged past the cutoff is closed even though the board still lists it.
    from datetime import date, timedelta

    from app.schemas import Job

    tools = _scan_setup(tmp_path, monkeypatch, {
        "companies": [{"name": "Acme", "provider": "x", "slug": "x"}],
        "filters": {"max_age_days": 60}, "snapshot": False,
    })
    old = (date.today() - timedelta(days=200)).isoformat()
    tools.store.upsert_job(Job(id="2026-900", company="Acme", company_job_id="OLD",
                               position="Eng", status="open", posted_date=old))
    tools.store.upsert_job(Job(id="2026-901", company="Acme", company_job_id="OLDAPP",
                               position="PM", status="applied", posted_date=old))  # applied -> survives
    monkeypatch.setattr(tools.providers, "fetch", lambda *a: [
        P.RawPosting(company="Acme", company_job_id="OLD", position="Eng", posted_date=old),
        P.RawPosting(company="Acme", company_job_id="OLDAPP", position="PM", posted_date=old),
    ])
    r = tools.scan_jobs()
    by = lambda k: next(j for j in tools.store.list_jobs() if j.company_job_id == k)
    assert r["dead"] == 1
    assert by("OLD").status == "closed"      # aged open job pruned
    assert by("OLDAPP").status == "applied"  # applied job untouched


def test_scan_only_restricts_to_named_companies(tmp_path, monkeypatch):
    # scan_jobs(only=[...]) fetches and persists only the named companies.
    tools = _scan_setup(tmp_path, monkeypatch, {"companies": [
        {"name": "Acme", "provider": "x", "slug": "a"},
        {"name": "Globex", "provider": "x", "slug": "g"},
    ], "snapshot": False})
    fetched: list[str] = []

    def fake_fetch(_provider, name, _slug):
        fetched.append(name)
        return [P.RawPosting(company=name, company_job_id="R1", position="Eng")]

    monkeypatch.setattr(tools.providers, "fetch", fake_fetch)
    tools.scan_jobs(only=["Globex"])
    assert fetched == ["Globex"]                                   # Acme never fetched
    assert {j.company for j in tools.store.list_jobs()} == {"Globex"}


def test_scan_tolerates_bad_filter_and_company_values(tmp_path, monkeypatch):
    # Garbage max_age_days and non-string `only` entries must degrade gracefully, never 500.
    tools = _scan_setup(tmp_path, monkeypatch, {
        "companies": [{"name": "Acme", "provider": "x", "slug": "x"}],
        "filters": {"max_age_days": "sixty"}, "snapshot": False,  # non-numeric -> treated as off
    })
    monkeypatch.setattr(tools.providers, "fetch", lambda *a: [
        P.RawPosting(company="Acme", company_job_id="R1", position="Eng"),
    ])
    r = tools.scan_jobs(only=[123, None])   # non-string entries -> fall back to scanning all
    assert r["new"] == 1                     # bad age filter is off; bad `only` doesn't exclude Acme


def test_scan_backfills_empty_company_job_id(tmp_path, monkeypatch):
    # Two id-less postings from the same company must NOT dedup into one.
    from app import config
    from app.agent import tools

    monkeypatch.setattr(config, "JOBS_CSV", tmp_path / "jobs.csv")
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(config, "APPLICATIONS_CSV", tmp_path / "applications.csv")
    monkeypatch.setattr(config, "PORTALS_YML", tmp_path / "portals.yml")
    monkeypatch.setattr(tools.status, "record", lambda *a, **k: None)
    monkeypatch.setattr(tools.store, "read_targets", lambda: {})  # no search filters (hermetic)
    monkeypatch.setattr(tools.store, "read_portals", lambda: {"companies": [{"name": "Acme", "provider": "x", "slug": "x"}], "snapshot": False})
    # Same title+location and a >40-char shared URL prefix — only the tail differs, past
    # _slug's truncation; the url hash must still keep them distinct.
    pre = "https://acme.recruitee.com/o/very-long-shared-path-prefix/job-"
    monkeypatch.setattr(tools.providers, "fetch", lambda *a: [
        P.RawPosting(company="Acme", company_job_id="", position="Engineer", location="NYC", url=f"{pre}1"),
        P.RawPosting(company="Acme", company_job_id="", position="Engineer", location="NYC", url=f"{pre}2"),
    ])
    r = tools.scan_jobs()
    assert r["new"] == 2  # both persisted, no false dedup
    assert len({j.company_job_id for j in tools.store.list_jobs()}) == 2  # distinct keys


def test_new_provider_hosts_allowlisted():
    from app.agent import crawl_policy

    assert crawl_policy.is_allowed_host("channable.recruitee.com")  # per-tenant subdomain
    assert crawl_policy.is_allowed_host("api.smartrecruiters.com")
    assert crawl_policy.is_allowed_host("apply.workable.com")
    assert not crawl_policy.is_allowed_host("evil-recruitee.com")  # not a real subdomain
    assert {"recruitee", "smartrecruiters", "workable"} <= set(P.PROVIDERS)
