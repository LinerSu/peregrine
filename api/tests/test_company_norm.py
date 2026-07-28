"""Company-name canonicalization + the personal alias registry.

Invariants pinned here (several from adversarial review, one from a duplicate seen in
live use):
  * norm_company is an EQUALITY KEY for dedup/matching only — display spellings are
    never rewritten, and the key is Unicode-aware (a non-Latin name must not collapse to
    "" and merge distinct employers);
  * the alias registry (config/companies.yml) is user-taught, tolerant of hand-edit
    mistakes (invalid YAML degrades to "no aliases", never a 500), and picked up on
    edit without a restart;
  * dead-job pruning stays PER JOB BOARD (alias-free): an alias says "same employer",
    not "same board" — one board's listing must never close another board's live
    jobs, and two boards of one employer merge (union), never clobber;
  * the same posting ingested twice under different keys dedups by URL (a board req id vs a
    derived slug for the same posting);
  * a wrong company spelling is fixed IN PLACE (PATCH company), syncing any linked
    application — never delete-and-re-add.
"""
import pytest
from fastapi.testclient import TestClient

from app import config
from app import data_store as store
from app.main import app
from app.schemas import Application, Job


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    """Every test in this module runs against a temp store AND a temp registry dir —
    a real config/companies.yml on the dev machine must never leak into assertions."""
    monkeypatch.setattr(config, "JOBS_CSV", tmp_path / "jobs.csv")
    monkeypatch.setattr(config, "APPLICATIONS_CSV", tmp_path / "applications.csv")
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "PROFILE_YML", tmp_path / "profile.yml")
    monkeypatch.setattr(store, "_alias_cache", None)
    (tmp_path / "jobs").mkdir()
    return tmp_path


_BUMP = {"n": 0}


def _write_registry(text: str) -> None:
    import os

    path = config.CONFIG_DIR / "companies.yml"
    path.write_text(text)
    # Rapid rewrites within one test land in the same second — force a STRICTLY
    # increasing mtime so the registry cache can't serve a stale mapping.
    _BUMP["n"] += 10
    st = os.stat(path)
    os.utime(path, (st.st_mtime + _BUMP["n"],) * 2)


# --- syntactic layer ------------------------------------------------------------------

@pytest.mark.parametrize("a,b", [
    ("Acme", "Acme Inc."),
    ("Acme", "ACME, INC"),
    ("Acme Inc.", "acme inc"),
    ("Example Co., Ltd.", "Example"),          # suffixes strip repeatedly
    ("Midco Corporation", "Midco Corp."),
    ("Acme  LLC", "acme"),
])
def test_variants_share_a_key(a, b):
    assert store.norm_company(a) == store.norm_company(b)


@pytest.mark.parametrize("a,b", [
    ("Acme", "Acmetric"),          # no prefix-matching accidents
    ("Initech", "Globex"),         # semantic aliases are the REGISTRY's job, not syntax
    ("Stripe", "Stripe Press"),    # different trailing word ≠ legal suffix
    ("北方电子", "南方软件"),        # non-Latin names must stay distinct, never collapse to ""
])
def test_different_companies_stay_distinct(a, b):
    assert store.norm_company(a) != store.norm_company(b)
    assert store.norm_company(a) and store.norm_company(b)


def test_single_word_suffix_name_survives():
    assert store.norm_company("Co") == "co"


def test_symbol_only_name_keeps_a_nonempty_key():
    assert store.norm_company("***") != ""


def test_dedup_across_name_variants():
    store.upsert_job(Job(id="2026-001", company="Acme Inc.", company_job_id="R1",
                         position="ML Engineer"))
    assert store.find_job_by_key("ACME", "r1").id == "2026-001"
    assert store.find_job_by_key("Applied Materials", "r1") is None


def test_application_matches_job_across_variants():
    store.upsert_job(Job(id="2026-001", company="Acme Inc.", company_job_id="R1",
                         position="ML Engineer"))
    assert store.find_job_for_posting("acme, inc", "anything", "R1").id == "2026-001"
    assert store.find_job_for_posting("Acme", "ML Engineer").id == "2026-001"


def test_display_spelling_is_never_rewritten():
    store.upsert_job(Job(id="2026-001", company="Acme Inc.", company_job_id="R1",
                         position="Eng"))
    store.find_job_by_key("acme", "r1")
    assert store.get_job("2026-001").company == "Acme Inc."


# --- the alias registry ---------------------------------------------------------------

def test_alias_registry_maps_and_composes():
    _write_registry("companies:\n  - name: Initech\n    aliases: [Vandelay Analytics]\n")
    assert store.norm_company("Vandelay Analytics") == "initech"
    assert store.norm_company("Vandelay Analytics, Inc.") == "initech"  # syntax + alias compose
    store.upsert_job(Job(id="2026-001", company="Vandelay Analytics", company_job_id="R1",
                         position="Eng"))
    assert store.find_job_by_key("Initech", "R1").id == "2026-001"


def test_no_registry_file_means_pure_syntactic():
    assert store.norm_company("Vandelay Analytics") == "vandelay analytics"


def test_registry_edits_are_picked_up_incrementally():
    _write_registry("companies: []\n")
    assert store.norm_company("Vandelay Analytics") == "vandelay analytics"
    _write_registry("companies:\n  - name: Initech\n    aliases: [Vandelay Analytics]\n")
    assert store.norm_company("Vandelay Analytics") == "initech"


def test_invalid_yaml_degrades_to_no_aliases():
    # The manual tells users to hand-edit this file: one stray bracket must NOT 500
    # every dedup/match/scan path — it degrades to the syntactic layer.
    _write_registry("companies:\n  - name: [unclosed\n")
    assert store.norm_company("Acme Inc.") == "acme"
    assert store.norm_company("Vandelay Analytics") == "vandelay analytics"


def test_lone_string_alias_is_accepted_not_iterated_charwise():
    _write_registry("companies:\n  - name: Initech\n    aliases: Vandelay Analytics\n")
    assert store.norm_company("Vandelay Analytics") == "initech"
    assert store.norm_company("v") == "v"  # no per-character alias entries leaked


def test_malformed_registry_entries_are_ignored():
    _write_registry("companies:\n  - just a string\n  - name: ''\n    aliases: [X]\n")
    assert store.norm_company("Vandelay Analytics") == "vandelay analytics"


# --- scan: dedup uses aliases, pruning stays per-board --------------------------------

def _scan_env(monkeypatch, portals, fetch):
    from app.agent import tools

    monkeypatch.setattr(tools.status, "record", lambda *a, **k: None)
    monkeypatch.setattr(store, "read_targets", lambda: {}, raising=False)
    monkeypatch.setattr(store, "read_portals", lambda: portals, raising=False)
    monkeypatch.setattr(tools.providers, "fetch", fetch)
    return tools


def test_scan_dedups_across_name_variants(monkeypatch):
    from app.agent.providers import RawPosting

    store.upsert_job(Job(id="2026-001", company="Acme Inc.", company_job_id="R1",
                         position="Eng", status="open"))
    tools = _scan_env(
        monkeypatch,
        {"companies": [{"name": "Acme", "provider": "generic", "slug": "x"}],
         "filters": {}, "snapshot": False},
        lambda provider, name, slug: [RawPosting(company="Acme", company_job_id="R1",
                                                 position="Eng")],
    )
    summary = tools.scan_jobs()
    assert summary["new"] == 0 and summary["duplicates"] == 1
    assert len(store.list_jobs()) == 1


def test_alias_must_not_prune_another_boards_live_job(monkeypatch):
    # THE review high: registry Initech<-Vandelay, an open Vandelay-board job, and an
    # Initech-only scan. Same employer, different board — the job must stay open.
    from app.agent.providers import RawPosting

    _write_registry("companies:\n  - name: Initech\n    aliases: [Vandelay Analytics]\n")
    store.upsert_job(Job(id="2026-001", company="Vandelay Analytics", company_job_id="VD-1",
                         position="Eng", status="open"))
    tools = _scan_env(
        monkeypatch,
        {"companies": [{"name": "Initech", "provider": "generic", "slug": "x"}],
         "filters": {}, "snapshot": False},
        lambda provider, name, slug: [RawPosting(company="Initech", company_job_id="IN-9",
                                                 position="Other")],
    )
    summary = tools.scan_jobs()
    assert summary["dead"] == 0
    assert store.get_job("2026-001").status == "open"


def test_two_boards_of_one_employer_union_not_clobber(monkeypatch):
    # "Acme" and "Acme Inc" configured as two boards: their listings must UNION —
    # the second fetch clobbering the first wrongly pruned the first board's jobs.
    from app.agent.providers import RawPosting

    store.upsert_job(Job(id="2026-001", company="Acme", company_job_id="R1",
                         position="Eng", status="open"))
    store.upsert_job(Job(id="2026-002", company="Acme Inc", company_job_id="R2",
                         position="Eng2", status="open"))
    boards = {"acme-a": [RawPosting(company="Acme", company_job_id="R1", position="Eng")],
              "acme-b": [RawPosting(company="Acme Inc", company_job_id="R2", position="Eng2")]}
    tools = _scan_env(
        monkeypatch,
        {"companies": [{"name": "Acme", "provider": "generic", "slug": "acme-a"},
                        {"name": "Acme Inc", "provider": "generic", "slug": "acme-b"}],
         "filters": {}, "snapshot": False},
        lambda provider, name, slug: boards[slug],
    )
    summary = tools.scan_jobs()
    assert summary["dead"] == 0
    assert store.get_job("2026-001").status == "open"
    assert store.get_job("2026-002").status == "open"


def test_scan_prune_still_works_across_spelling_variants(monkeypatch):
    # Same board, spelling variant: a job tracked as "Acme Inc." IS prunable by a
    # scan configured as "Acme" (syntactic board key) when its req disappears.
    from app.agent.providers import RawPosting

    store.upsert_job(Job(id="2026-001", company="Acme Inc.", company_job_id="R1",
                         position="Eng", status="open"))
    tools = _scan_env(
        monkeypatch,
        {"companies": [{"name": "Acme", "provider": "generic", "slug": "x"}],
         "filters": {}, "snapshot": False},
        lambda provider, name, slug: [RawPosting(company="Acme", company_job_id="R2",
                                                 position="Other")],
    )
    assert tools.scan_jobs()["dead"] == 1
    assert store.get_job("2026-001").status == "closed"


def test_scan_only_filter_matches_name_variants(monkeypatch):
    from app.agent.providers import RawPosting

    fetched = []

    def fetch(provider, name, slug):
        fetched.append(name)
        return [RawPosting(company=name, company_job_id="R1", position="Eng")]

    tools = _scan_env(
        monkeypatch,
        {"companies": [{"name": "Globex", "provider": "generic", "slug": "g"},
                        {"name": "Initech", "provider": "generic", "slug": "i"}],
         "filters": {}, "snapshot": False},
        fetch,
    )
    tools.scan_jobs(only=["Globex, Inc."])
    assert fetched == ["Globex"]


def test_relevance_bypass_uses_normalized_company(monkeypatch):
    # Query-based providers (Amazon) bypass the relevance queries — the bypass must
    # match name variants, or "Amazon, Inc." rows lose the bypass the scan gave them.
    from app.agent import tools

    monkeypatch.setattr(
        store, "read_portals",
        lambda: {"companies": [{"name": "Amazon", "provider": "amazon", "slug": "q"}],
                 "queries": ["definitely-not-matching"]},
        raising=False,
    )
    pred = tools._relevance_predicate()
    assert pred(Job(id="2026-001", company="Amazon, Inc.", company_job_id="R1", position="Eng"))
    assert not pred(Job(id="2026-002", company="Globex", company_job_id="R2", position="Eng"))


# --- URL-fallback dedup (from the user's real duplicate pair) -------------------------

def test_same_url_dedups_despite_different_keys(monkeypatch):
    from app.agent import tools

    monkeypatch.setattr(tools.status, "record", lambda *a, **k: None)
    monkeypatch.setattr(store, "write_ingest_result", lambda *a, **k: None)
    monkeypatch.setattr(store, "read_ingest_result", lambda: {}, raising=False)

    url = "https://jobs.example.com/details/200665894"
    first = tools.save_ingested_job({"company": "Acme", "position": "Security Engineer",
                                     "company_job_id": "200665894", "url": url})
    assert first["created"] is True
    # Same posting pasted again: different company spelling AND no req id in the text
    # (a slug gets derived) — the URL is the same document, so it must dedup.
    second = tools.save_ingested_job({"company": "Acme Inc", "position": "Security Engineer",
                                      "company_job_id": "", "url": url})
    assert second["created"] is False
    assert second["job"]["id"] == first["job"]["id"]
    assert len(store.list_jobs()) == 1


# --- fix-in-place company edit --------------------------------------------------------

def test_company_is_editable_in_place_and_syncs_the_application():
    store.upsert_job(Job(id="2026-001", company="Acme Inc", company_job_id="R1",
                         position="Eng", status="applied"))
    store.upsert_application(Application(id="2026-001", company="Acme Inc",
                                         company_job_id="R1", position="Eng",
                                         status="applied"))
    r = TestClient(app).patch("/api/jobs/2026-001", json={"company": "Acme"})
    assert r.status_code == 200 and r.json()["job"]["company"] == "Acme"
    assert store.get_job("2026-001").company == "Acme"
    assert store.get_application("2026-001").company == "Acme"
