"""Job ingestion from pasted / uploaded content (both modes)."""
import pytest

from app import config
from app import data_store as store


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "JOBS_CSV", tmp_path / "jobs.csv")
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(config, "APPLICATIONS_CSV", tmp_path / "applications.csv")
    monkeypatch.setattr(config, "JOB_SOURCE", tmp_path / "job_source.md")
    from app.agent import tools

    monkeypatch.setattr(tools.status, "record", lambda *a, **k: None)
    return tmp_path


def test_save_ingested_job_creates_then_dedupes(tmp_store):
    from app.agent import tools

    r = tools.save_ingested_job({"company": "Acme", "position": "Engineer", "description": "build"})
    assert r["created"] is True and r["job"]["company"] == "Acme"
    assert len(store.list_jobs()) == 1
    # same company + derived id -> dedup (company_job_id slugged from the title)
    r2 = tools.save_ingested_job({"company": "Acme", "position": "Engineer"})
    assert r2["created"] is False
    assert len(store.list_jobs()) == 1


def test_ingest_coerces_none_optional_fields(tmp_store):
    from app.agent import tools

    # LLMs often emit null for optional fields — must not crash Pydantic validation.
    r = tools.save_ingested_job(
        {"company": "Acme", "position": "Eng", "location": None, "url": None, "description": None}
    )
    assert r["created"] is True
    assert r["job"]["location"] == ""


def test_created_job_keeps_parsed_extras_over_schema_defaults(tmp_store):
    from app.agent import tools

    # A fresh row must take the posting's own values outright. Filling only BLANKS would
    # drop any field whose schema default isn't blank — currency defaults to "USD", so a
    # parsed "CAD" would be silently overwritten by the default.
    r = tools.save_ingested_job({"company": "Acme", "position": "Eng", "currency": "CAD",
                                 "salary_min": 90000, "flexibility": "remote"})
    assert r["created"] is True
    job = store.get_job(r["job"]["id"])
    assert job.currency == "CAD" and job.salary_min == 90000 and job.flexibility == "remote"


def test_dedup_hit_fills_blanks_but_never_overwrites(tmp_store):
    from app.agent import tools

    tools.save_ingested_job({"company": "Acme", "position": "Eng", "currency": "CAD"})
    # Re-ingesting the same posting adds what was missing and leaves what was there.
    r = tools.save_ingested_job({"company": "Acme", "position": "Eng", "currency": "USD",
                                 "flexibility": "hybrid"})
    assert r["created"] is False
    job = store.get_job(r["job"]["id"])
    assert job.currency == "CAD"       # tracked value wins on a dedup hit
    assert job.flexibility == "hybrid"  # blank field filled


def test_save_ingested_job_requires_company_and_position(tmp_store):
    from app.agent import tools

    assert "error" in tools.save_ingested_job({"company": "Acme"})
    assert "error" in tools.save_ingested_job({"position": "Engineer"})
    assert store.list_jobs() == []


def test_ingest_job_doc_mock_cannot_parse(tmp_store):
    from app.agent import tools

    # The mock LLM can't produce structured fields -> a clean error, no job created.
    assert "error" in tools.ingest_job_doc("Some pasted posting text")
    assert "error" in tools.ingest_job_doc("")
    assert store.list_jobs() == []


def test_ingest_marker_bumps_on_save_and_dedup(tmp_store):
    from app.agent import tools

    assert tools.get_ingest_result()["seq"] == 0
    tools.save_ingested_job({"company": "Acme", "position": "Engineer"})
    r1 = tools.get_ingest_result()
    assert r1["seq"] == 1 and r1["created"] is True
    # A dedup (same job) STILL bumps the marker, so the Internal poll resolves
    # instead of timing out.
    tools.save_ingested_job({"company": "Acme", "position": "Engineer"})
    r2 = tools.get_ingest_result()
    assert r2["seq"] == 2 and r2["created"] is False


def test_save_job_source_roundtrip(tmp_store):
    from app.agent import tools

    assert tools.save_job_source("raw posting")["chars"] == len("raw posting")
    assert store.read_job_source() == "raw posting"


def test_scan_caps_new_jobs(tmp_store, monkeypatch):
    from app.agent import providers, tools

    monkeypatch.setattr(store, "read_portals",
                        lambda: {"companies": [{"provider": "x", "name": "Acme"}], "filters": {}, "snapshot": False})
    monkeypatch.setattr(store, "read_targets", lambda: {})
    n = tools._SCAN_NEW_CAP + 10
    posts = [providers.RawPosting(company="Acme", company_job_id=f"r{i}", position="Eng") for i in range(n)]
    monkeypatch.setattr(providers, "fetch", lambda *a, **k: posts)

    r = tools.scan_jobs()
    assert r["new"] == tools._SCAN_NEW_CAP and r["capped"] is True  # runaway flood is bounded
    assert len(store.list_jobs()) == tools._SCAN_NEW_CAP


def test_ingest_endpoints(tmp_store):
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    # Internal store-only save creates a job.
    r = client.post("/api/jobs/ingest-doc/save", json={"company": "Luma", "position": "ML Eng"})
    assert r.status_code == 200 and r.json()["created"] is True
    # Missing a required field (position) -> 422 from the schema.
    assert client.post("/api/jobs/ingest-doc/save", json={"company": "X"}).status_code == 422
    # Empty stash -> 422 (won't clobber).
    assert client.put("/api/jobs/ingest-source", json={"text": "  "}).status_code == 422
    # External parse can't extract a job in mock mode -> 422.
    assert client.post("/api/jobs/ingest-doc", json={"text": "posting"}).status_code == 422
    # Internal save tolerates JSON null for optional fields (the HTTP entry point,
    # not just the function) — Claude may emit null for an absent company_job_id.
    rn = client.post(
        "/api/jobs/ingest-doc/save",
        json={"company": "Beta", "position": "Dev", "company_job_id": None, "location": None},
    )
    assert rn.status_code == 200 and rn.json()["created"] is True


def test_scan_does_not_revert_what_changed_while_it_ran(tmp_store, monkeypatch):
    """A scan reads the jobs list, then spends real time on the network. Writing that
    stale copy back is how a background fit evaluation silently disappears."""
    from app.agent import providers, tools
    from app.schemas import Job

    store.upsert_job(Job(id="2026-001", company="Acme", company_job_id="r1", position="Eng"))
    monkeypatch.setattr(store, "read_portals", lambda: {
        "companies": [{"provider": "x", "name": "Acme"}], "filters": {}, "snapshot": False})
    monkeypatch.setattr(store, "read_targets", lambda: {})

    def fetch(*a, **k):
        # Stand-ins for what really happens mid-scan: a background evaluation lands, and
        # a job is ingested from another tab.
        j = store.get_job("2026-001")
        j.fit_score = 0.9
        store.upsert_job(j)
        store.upsert_job(Job(id="2026-009", company="Other", company_job_id="x9",
                             position="Ingested mid-scan"))
        return [providers.RawPosting(company="Acme", company_job_id="r1", position="Eng"),
                providers.RawPosting(company="Acme", company_job_id="r2", position="New")]

    monkeypatch.setattr(providers, "fetch", fetch)
    assert tools.scan_jobs()["new"] == 1

    assert store.get_job("2026-001").fit_score == 0.9        # evaluation survives
    assert store.get_job("2026-009") is not None             # concurrent ingest survives
    assert any(j.company_job_id == "r2" for j in store.list_jobs())  # the scan's row landed


def test_scan_does_not_close_a_job_you_actioned_while_it_ran(tmp_store, monkeypatch):
    # The board going quiet is weaker evidence than you clicking "I applied" — and the
    # scan's copy still says "open", so only a merge that re-reads can tell.
    from app.agent import providers, tools
    from app.schemas import Job

    store.upsert_job(Job(id="2026-001", company="Acme", company_job_id="r1", position="Eng"))
    monkeypatch.setattr(store, "read_portals", lambda: {
        "companies": [{"provider": "x", "name": "Acme"}], "filters": {}, "snapshot": False})
    monkeypatch.setattr(store, "read_targets", lambda: {})

    def fetch(*a, **k):
        j = store.get_job("2026-001")
        j.status = "applied"
        store.upsert_job(j)
        return [providers.RawPosting(company="Acme", company_job_id="r2", position="Other")]

    monkeypatch.setattr(providers, "fetch", fetch)
    tools.scan_jobs()
    assert store.get_job("2026-001").status == "applied"     # not reverted to closed


def test_a_scan_that_changes_nothing_still_prunes_from_fresh_state(tmp_store, monkeypatch):
    # The no-op path had the same staleness bug: with nothing new and nothing dead there
    # is no merge to re-read through, so a job ingested mid-scan looked like an orphan and
    # lost its snapshot.
    from app.agent import providers, tools
    from app.schemas import Job

    store.upsert_job(Job(id="2026-001", company="Acme", company_job_id="r1", position="Eng"))
    monkeypatch.setattr(store, "read_portals", lambda: {
        "companies": [{"provider": "x", "name": "Acme"}], "filters": {}, "snapshot": True})
    monkeypatch.setattr(store, "read_targets", lambda: {})

    ingested = {}

    def fetch(*a, **k):
        ingested["id"] = tools.save_ingested_job(
            {"company": "Other", "position": "Ingested mid-scan", "description": "text"}
        )["job"]["id"]
        return [providers.RawPosting(company="Acme", company_job_id="r1", position="Eng")]

    monkeypatch.setattr(providers, "fetch", fetch)
    r = tools.scan_jobs()
    assert r["new"] == 0 and r["dead"] == 0          # the no-op path
    assert (config.JOBS_DIR / f"{ingested['id']}.md").exists()  # snapshot survived


def test_ingest_during_a_scan_cannot_be_handed_a_minted_id(tmp_store, monkeypatch):
    """The scan mints ids up front and writes them minutes later. An ingest reading the
    CSV in between must not be handed an id the scan already took — both rows would claim
    it, and one snapshot would overwrite the other."""
    from app.agent import providers, tools
    from app.schemas import Job

    store.upsert_job(Job(id="2026-001", company="Acme", company_job_id="r0", position="Old"))
    monkeypatch.setattr(store, "read_portals", lambda: {
        "companies": [{"provider": "x", "name": "Acme"}], "filters": {}, "snapshot": True})
    monkeypatch.setattr(store, "read_targets", lambda: {})
    monkeypatch.setattr(providers, "fetch", lambda *a, **k: [
        providers.RawPosting(company="Acme", company_job_id=f"r{i}", position=f"Eng {i}")
        for i in (1, 2, 3)])

    # Land the ingest in the gap: right after the scan minted its FIRST id, long before
    # the batch is written. This is the window the CSV can't see.
    ingested = {}
    fired = []                       # set BEFORE the nested call: it writes a snapshot too
    real_write_md = store.write_job_md

    def write_md(jid, md):
        if not fired:
            fired.append(True)
            ingested["id"] = tools.save_ingested_job(
                {"company": "Other", "position": "Ingested mid-scan", "description": "text"}
            )["job"]["id"]
        return real_write_md(jid, md)

    monkeypatch.setattr(store, "write_job_md", write_md)
    tools.scan_jobs()

    ids = [j.id for j in store.list_jobs()]
    assert len(ids) == len(set(ids)), f"duplicate ids handed out: {ids}"
    assert ingested["id"] in ids                                            # ingest survived
    assert len([j for j in store.list_jobs() if j.company == "Acme"]) == 4  # 1 old + 3 scanned


def test_reserved_ids_are_never_handed_out_twice(tmp_store):
    # Interleaving the two allocators must not repeat: the batch minter reserves as it
    # yields, so next_id() can't hand the same number to something else.
    minter = store.id_minter()
    handed = [next(minter), store.next_id(), next(minter), store.next_id(), next(minter)]
    assert len(handed) == len(set(handed)), handed

