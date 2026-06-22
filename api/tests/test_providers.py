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
