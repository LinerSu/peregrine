"""Auto-evaluate on ingest: a newly added job arrives scored — with guards.

Rules pinned here:
  * External-path ingests (/ingest, /ingest-doc, upload) schedule a BACKGROUND fit
    evaluation only when the job was CREATED, a real profile exists, and the active
    provider isn't effectively mock — a keyless anthropic/openai config silently
    falls back to the {fit 0.5, "(mock)"} stub, and placeholder scores must never be
    written silently;
  * the same predicate gates every path that scores a job the user didn't explicitly
    ask about — REST ingest, the backfill, AND the chat handler for a pasted URL. The
    chat path was written without it, so in mock mode pasting a link stamped a
    real-looking 0.5 onto the row (issue #88). `_BLOCKED_MODES` below is the rule; it
    is shared by all three tests, because a guard spelled out per call site is a guard
    the next call site forgets;
  * the Internal store-only path (/ingest-doc/save) NEVER schedules API-side LLM
    work — the local-Claude skill chains the evaluation itself (mode contract), and
    the shared /ingest URL path honours the caller's auto_evaluate:false for the
    same reason.
"""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import config
from app import data_store as store
from app.agent import llm
from app.agent import tools
from app.agent.llm import LLMUnusable
from app.main import app
from app.routers import jobs as jobs_router

# When an evaluation the user didn't ask for must NOT run: (provider, key, profile_ready).
# One table, shared by the ingest, chat and backfill guards — they are the same rule.
_BLOCKED_MODES = [
    ("mock", "sk-test", True),        # mock provider: never write placeholders silently
    ("anthropic", "", True),          # real provider, NO key -> falls back to the stub
    ("openai", "   ", True),          # blank key counts as no key
    ("anthropic", "sk-test", False),  # empty profile: scoring is noise
]


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "JOBS_CSV", tmp_path / "jobs.csv")
    monkeypatch.setattr(config, "APPLICATIONS_CSV", tmp_path / "applications.csv")
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(config, "PROFILE_YML", tmp_path / "profile.yml")
    (tmp_path / "jobs").mkdir()

    calls: list[str] = []

    def fake_evaluate(job_id: str) -> dict:
        # Records the call AND returns an evaluation-shaped dict: the background task
        # ignores the return, but the chat handler formats it into its reply.
        calls.append(job_id)
        return {"fit_score": 0.8, "recommendation": "apply"}

    monkeypatch.setattr(tools, "evaluate_fit", fake_evaluate)
    monkeypatch.setattr(tools.status, "record", lambda *a, **k: None)
    monkeypatch.setattr(store, "write_ingest_result", lambda *a, **k: None)
    monkeypatch.setattr(store, "read_ingest_result", lambda: {}, raising=False)

    # Patch the settings the mock-ness check itself reads, so a keyless real provider
    # is exercised exactly as it behaves in production (it falls back to the stub).
    def set_provider(name: str, key: str = "sk-test") -> None:
        monkeypatch.setattr(llm, "get_settings", lambda: SimpleNamespace(
            llm_provider=name, anthropic_api_key=key, openai_api_key=key))

    def set_ingest_result(created: bool) -> None:
        # Company/location are what the chat handler prints back; the REST paths only
        # read the id.
        job = {"id": "2026-001", "position": "Eng", "company": "Acme", "location": "Remote"}
        monkeypatch.setattr(
            tools, "ingest_job_doc", lambda text: {"job": job, "created": created},
        )
        monkeypatch.setattr(
            tools, "ingest_job_url", lambda url: {"job": job, "created": created},
        )

    return SimpleNamespace(calls=calls, set_provider=set_provider,
                           set_ingest_result=set_ingest_result, tmp_path=tmp_path)


def _profile(ready: bool) -> None:
    config.PROFILE_YML.write_text("name: someone\nskills: [python]\n" if ready else "name: ''\n")


def test_profile_ready_reads_the_profile(env):
    _profile(False)
    assert tools.profile_ready() is False
    _profile(True)
    assert tools.profile_ready() is True


def test_created_job_with_profile_schedules_background_eval(env):
    _profile(True)
    env.set_provider("anthropic")
    env.set_ingest_result(created=True)
    r = TestClient(app).post("/api/jobs/ingest-doc", json={"text": "posting"})
    assert r.status_code == 200 and r.json()["auto_evaluating"] is True
    # TestClient runs background tasks before returning — the eval must have fired.
    assert env.calls == ["2026-001"]


@pytest.mark.parametrize("provider,key,ready,created", [
    *[(*mode, True) for mode in _BLOCKED_MODES],
    ("anthropic", "sk-test", True, False),  # dedup hit: keeps its existing evaluation
])
def test_guards_suppress_auto_eval(env, provider, key, ready, created):
    _profile(ready)
    env.set_provider(provider, key)
    env.set_ingest_result(created=created)
    r = TestClient(app).post("/api/jobs/ingest-doc", json={"text": "posting"})
    assert r.status_code == 200
    assert "auto_evaluating" not in r.json()
    assert env.calls == []


def test_url_ingest_respects_the_callers_auto_evaluate_flag(env):
    # /api/jobs/ingest is called in BOTH modes (fetching a URL is deterministic), so the
    # Internal client sends auto_evaluate:false — the API must not spend tokens for it.
    _profile(True)
    env.set_provider("anthropic")
    env.set_ingest_result(created=True)
    client = TestClient(app)

    r = client.post("/api/jobs/ingest", json={"url": "https://example.com/j", "auto_evaluate": False})
    assert r.status_code == 200 and "auto_evaluating" not in r.json()
    assert env.calls == []

    r = client.post("/api/jobs/ingest", json={"url": "https://example.com/j"})  # External default
    assert r.status_code == 200 and r.json()["auto_evaluating"] is True
    assert env.calls == ["2026-001"]


def test_upload_path_also_auto_evaluates(env):
    # The third External entry point. URL and paste were covered; upload wasn't, and
    # untested wiring is wiring that silently stops working.
    _profile(True)
    env.set_provider("anthropic")
    env.set_ingest_result(created=True)
    r = TestClient(app).post(
        "/api/jobs/ingest-doc/upload",
        files={"file": ("posting.txt", b"Acme is hiring an Engineer. Requires Python.", "text/plain")},
    )
    assert r.status_code == 200 and r.json()["auto_evaluating"] is True
    assert env.calls == ["2026-001"]


def test_upload_path_honours_the_guards(env):
    _profile(False)  # empty profile -> scoring is noise
    env.set_provider("anthropic")
    env.set_ingest_result(created=True)
    r = TestClient(app).post(
        "/api/jobs/ingest-doc/upload",
        files={"file": ("posting.txt", b"Acme is hiring an Engineer.", "text/plain")},
    )
    assert r.status_code == 200 and "auto_evaluating" not in r.json()
    assert env.calls == []


# --- the chat path: pasting a URL scores the job the same way, or not at all ----------

def _chat(message: str):
    return TestClient(app).post("/api/chat", json={"message": message, "history": []})


@pytest.mark.parametrize("provider,key,ready", _BLOCKED_MODES)
def test_chat_url_ingest_must_not_write_a_placeholder_score(env, provider, key, ready):
    """The REST ingest path guards this deliberately; the chat handler called
    evaluate_fit unconditionally, so a pasted link in mock or keyless mode put a
    real-looking 0.5 on the row — indistinguishable from a real score, and feeding
    ranking, the apply gate and the outcome analytics from there on."""
    _profile(ready)
    env.set_provider(provider, key)
    env.set_ingest_result(created=True)

    r = _chat("please add https://example.com/jobs/1")
    assert r.status_code == 200
    assert env.calls == []                                       # nothing scored
    assert [a["tool"] for a in r.json()["actions"]] == ["ingest_job_url"]
    assert "not scored automatically" in r.json()["reply"].lower()  # and it says so


def test_chat_url_ingest_still_scores_when_the_score_would_be_real(env):
    _profile(True)
    env.set_provider("anthropic")
    env.set_ingest_result(created=True)

    r = _chat("please add https://example.com/jobs/1")
    assert r.status_code == 200 and env.calls == ["2026-001"]
    assert [a["tool"] for a in r.json()["actions"]] == ["ingest_job_url", "evaluate_fit"]
    assert "Fit 0.8" in r.json()["reply"]


def test_chat_still_reports_the_ingest_when_the_score_fails(env, monkeypatch):
    """The ingest is already persisted by the time scoring runs. Failing the whole turn
    would tell the user nothing was added when a job was — and leave them re-pasting a
    link that is already tracked."""
    _profile(True)
    env.set_provider("anthropic")
    env.set_ingest_result(created=True)

    def boom(job_id):
        raise LLMUnusable("the provider returned no usable evaluation")

    monkeypatch.setattr(tools, "evaluate_fit", boom)
    r = _chat("please add https://example.com/jobs/1")
    assert r.status_code == 200
    body = r.json()
    assert "Ingested" in body["reply"] and "couldn't score it" in body["reply"]
    assert [a["tool"] for a in body["actions"]] == ["ingest_job_url"]  # the ingest is kept


def test_chat_reports_an_ingest_failure_instead_of_scoring_nothing(env, monkeypatch):
    monkeypatch.setattr(tools, "ingest_job_url", lambda url: {"error": "unsupported board"})
    r = _chat("https://example.com/jobs/1")
    assert r.status_code == 200 and "unsupported board" in r.json()["reply"]
    assert env.calls == []


def test_prepare_materials_does_not_score_on_the_way_to_applying(env, monkeypatch):
    """prepare_materials evaluates an unscored job as a convenience — the user asked to
    apply, not for a score — so it carries the same guard. Without it, clicking through
    to apply in mock mode is another way to stamp a placeholder onto the row."""
    from app.schemas import Job

    _profile(True)
    env.set_provider("mock")
    store.upsert_job(Job(id="2026-001", company="Acme", company_job_id="R1", position="Eng"))

    r = TestClient(app).post("/api/jobs/2026-001/prepare")
    assert r.status_code == 200
    assert env.calls == []

    env.set_provider("anthropic")  # real provider + real profile -> the score is worth writing
    assert TestClient(app).post("/api/jobs/2026-001/prepare").status_code == 200
    assert env.calls == ["2026-001"]


def test_prepare_still_unlocks_apply_when_the_evaluation_fails(env, monkeypatch):
    """The pre-apply gate's real work is deterministic — make the application dir, hand
    back the apply URL and the review material. The UI unlocks Apply on `apply_url`, so
    a convenience score that can't be produced must not lock the user out of applying."""
    from app.schemas import Job

    _profile(True)
    env.set_provider("anthropic")
    store.upsert_job(Job(id="2026-001", company="Acme", company_job_id="R1", position="Eng",
                         url="https://example.com/jobs/1"))

    def boom(job_id):
        raise LLMUnusable("the provider returned nothing usable")

    monkeypatch.setattr(tools, "evaluate_fit", boom)
    r = TestClient(app).post("/api/jobs/2026-001/prepare")
    assert r.status_code == 200
    assert r.json()["apply_url"] == "https://example.com/jobs/1"


def test_internal_store_only_save_never_schedules_api_eval(env):
    # The mode contract: /ingest-doc/save is Claude's store-only path — the API must
    # not run LLM work for it (the skill chains the evaluation locally instead).
    _profile(True)
    env.set_provider("anthropic")
    r = TestClient(app).post("/api/jobs/ingest-doc/save",
                             json={"company": "Acme", "position": "Eng"})
    assert r.status_code == 200
    assert "auto_evaluating" not in r.json()
    assert env.calls == []


# --- backfill: apply the capability to already-tracked jobs ---------------------------

def _job(id: str, status: str = "open", fit: "float | None" = None):
    from app.schemas import Job

    from app import data_store as store_mod
    store_mod.upsert_job(Job(id=id, company="Acme", company_job_id=f"R{id[-1]}",
                             position="Eng", status=status, fit_score=fit))


def test_backfill_schedules_only_open_jobs_missing_scores(env):
    _profile(True)
    env.set_provider("anthropic")
    _job("2026-001")                       # open, missing -> scheduled
    _job("2026-002", fit=0.7)              # already scored -> skipped
    _job("2026-003", status="closed")      # dead -> skipped
    _job("2026-004")                       # open, missing -> scheduled
    r = TestClient(app).post("/api/jobs/evaluate-missing")
    assert r.status_code == 200
    assert r.json() == {"scheduled": 2, "remaining": 0, "capped": False}
    assert sorted(env.calls) == ["2026-001", "2026-004"]


@pytest.mark.parametrize("provider,key,ready", _BLOCKED_MODES)
def test_backfill_guards(env, provider, key, ready):
    _profile(ready)
    env.set_provider(provider, key)
    _job("2026-001")
    r = TestClient(app).post("/api/jobs/evaluate-missing")
    assert r.status_code == 200 and r.json()["scheduled"] == 0
    assert "reason" in r.json()
    assert env.calls == []


def test_backfill_is_capped_and_reports_what_is_left(env):
    """Each evaluation is a metered request, so one click must not fan out unbounded."""
    _profile(True)
    env.set_provider("anthropic")
    n = jobs_router._BACKFILL_CAP + 5
    for i in range(n):
        _job(f"2026-{i:03d}")

    r = TestClient(app).post("/api/jobs/evaluate-missing").json()
    assert r == {"scheduled": jobs_router._BACKFILL_CAP, "remaining": 5, "capped": True}
    assert len(env.calls) == jobs_router._BACKFILL_CAP


def test_backfill_skips_jobs_already_being_evaluated(env, monkeypatch):
    # A second click (or a click racing the auto-eval on ingest) must not pay twice for
    # the same job. The claim is released in a finally, so a crash can't strand a job.
    _profile(True)
    env.set_provider("anthropic")
    _job("2026-001")
    _job("2026-002")
    monkeypatch.setattr(jobs_router, "_evaluating", {"2026-001"})

    r = TestClient(app).post("/api/jobs/evaluate-missing").json()
    assert r["scheduled"] == 1 and r["remaining"] == 1
    assert env.calls == ["2026-002"]
    assert "2026-002" not in jobs_router._evaluating  # claim released after the run


def test_a_failing_evaluation_releases_its_claim(env, monkeypatch):
    _profile(True)
    env.set_provider("anthropic")
    _job("2026-001")

    def boom(job_id):
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(tools, "evaluate_fit", boom)
    try:
        TestClient(app).post("/api/jobs/evaluate-missing")
    except RuntimeError:
        pass  # TestClient surfaces the background task's error; the claim must still clear
    assert "2026-001" not in jobs_router._evaluating


def test_one_failing_evaluation_does_not_strand_the_rest_of_the_batch(env, monkeypatch):
    """A backfill queues N background tasks, and Starlette runs them in sequence in one
    coroutine — so an exception escaping the first cancels every task behind it. Those
    jobs were claimed at SCHEDULE time, so their release never runs either: they stay
    claimed for the life of the process and can never be evaluated again without a
    restart. Now that an evaluation can fail (it used to write a placeholder instead),
    one hiccup must cost one job, not the batch."""
    _profile(True)
    env.set_provider("anthropic")
    for i in (1, 2, 3):
        _job(f"2026-00{i}")

    seen: list[str] = []

    def flaky(job_id: str) -> dict:
        seen.append(job_id)
        if job_id == "2026-001":
            raise LLMUnusable("the provider returned no usable evaluation")
        return {"fit_score": 0.8}

    monkeypatch.setattr(tools, "evaluate_fit", flaky)
    r = TestClient(app).post("/api/jobs/evaluate-missing").json()

    assert r["scheduled"] == 3
    assert seen == ["2026-001", "2026-002", "2026-003"]  # the failure didn't stop the queue
    assert jobs_router._evaluating == set()              # and nothing stayed claimed



def test_backfill_treats_a_stale_evaluation_as_missing(env, monkeypatch):
    """GET /api/jobs nulls a fit score whose evaluation predates the last CV parse, so on
    screen — and to the Internal skill, which reads that list — the job reads as unscored.
    The backfill read raw rows, making it the one place that disagreed: the job the user
    can see needs scoring was the one job it skipped."""
    _profile(True)
    env.set_provider("anthropic")
    _job("2026-001", fit=0.8)   # scored, but against a previous CV
    _job("2026-002", fit=0.9)   # scored and current

    monkeypatch.setattr(tools, "cv_parsed_stamp", lambda: 1000.0)
    monkeypatch.setattr(tools, "artifact_stale",
                        lambda jid, suffix, cv_ts=None: jid == "2026-001")

    r = TestClient(app).post("/api/jobs/evaluate-missing").json()
    assert r["scheduled"] == 1
    assert env.calls == ["2026-001"]
