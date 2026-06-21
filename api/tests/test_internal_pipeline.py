"""Internal-mode store-only persistence: save/read fit evaluations and skill-gap
analyses produced *outside* the API (by local Claude), with no LLM call. These
back the `PUT/GET /api/jobs/{id}/{evaluation,upskilling}` routes."""
from app import config
from app import data_store as store
from app.agent import tools
from app.schemas import Job


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "JOBS_CSV", tmp_path / "jobs.csv")
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(config, "APPLICATIONS_CSV", tmp_path / "applications.csv")
    monkeypatch.setattr(tools.status, "record", lambda *a, **k: None)


def _job(jid="2026-001"):
    store.upsert_job(Job(id=jid, company="Acme", company_job_id="R1", position="Eng"))
    return jid


# --- upskilling round-trip --------------------------------------------------
def test_save_and_get_upskilling_roundtrip(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    jid = _job()
    assert tools.get_upskilling(jid) is None  # nothing saved yet

    saved = tools.save_upskilling(
        jid,
        {"summary": "Strong overall.", "missing_skills": [
            {"skill": "Rust", "why": "core to the role", "how_to_close": "build a CLI"}
        ]},
    )
    assert saved["job_id"] == jid

    got = tools.get_upskilling(jid)
    assert got["summary"] == "Strong overall."
    assert got["missing_skills"][0]["skill"] == "Rust"
    assert got["job_id"] == jid


def test_save_upskilling_missing_job(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    assert "error" in tools.save_upskilling("nope-999", {"summary": "x"})


def test_get_upskilling_none_when_absent(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _job()
    assert tools.get_upskilling("2026-001") is None


# --- evaluation persistence -------------------------------------------------
def test_save_evaluation_persists_score_and_markdown(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    jid = _job("2026-002")
    store.write_job_md(jid, "# Eng — Acme\n\nbody\n")

    saved = tools.save_evaluation(
        jid,
        {"fit_score": 0.82, "recommendation": "apply",
         "strengths": ["s1"], "weaknesses": ["w1"], "materials": ["m1"]},
    )
    assert saved["job_id"] == jid
    assert store.get_job(jid).fit_score == 0.82  # CSV column updated

    md = store.read_job_md(jid)
    assert md.count("## Agent evaluation") == 1
    assert "0.82" in md and "s1" in md and "w1" in md and "m1" in md


def test_save_evaluation_missing_job(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    assert "error" in tools.save_evaluation("nope-999", {"fit_score": 0.5})


# --- the store-only path must NOT touch an LLM (Internal mode has no API key) -
def test_store_only_paths_never_call_the_llm(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)

    def boom(*a, **k):
        raise AssertionError("store-only path must not call the LLM")

    import app.agent.llm as llm
    monkeypatch.setattr(llm.LLMClient, "complete", boom)

    jid = _job("2026-003")
    tools.save_upskilling(jid, {"summary": "ok", "missing_skills": []})
    tools.save_evaluation(jid, {"fit_score": 0.5})
    assert tools.get_upskilling(jid)["summary"] == "ok"
    assert store.get_job(jid).fit_score == 0.5
