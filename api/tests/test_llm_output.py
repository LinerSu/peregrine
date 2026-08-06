"""Output caps are per call and per provider, and a completion we can't use is loud.

Rules pinned here:
  * every provider gets the CALLER's cap, in its own dialect — Anthropic `max_tokens`,
    OpenAI `max_tokens`, Ollama `options.num_predict`. A single hardcoded 1024 on the
    Anthropic branch meant every tailored CV came back cut off mid-document, and a fix
    that only taught one branch would leave the same bug for the other two;
  * every provider's "I ran out of room" is read, in its own dialect — `stop_reason`,
    `finish_reason`, `done_reason` — because that flag is the only thing separating
    "the model was interrupted" from "the model said nothing useful", and the fallbacks
    are written for the second;
  * so the paths that would otherwise substitute a placeholder (tailored CV, cover
    letter, fit evaluation, CV parse, posting parse) report the failure instead;
  * a placeholder evaluation is recognised by VALUE, before the review pass, and the
    answer is carried to the save point out of band. `reviewer` rebuilds the evaluation
    from its own model output, so a marker hung on the dict is gone by the time the
    score is written — and a job posting on that path could forge one anyway;
  * and a failed action leaves `current_task` at "idle". Nothing here used to be able
    to fail, so nothing used to have to.

Honest mock mode is untouched: with no provider configured the stubs are still
returned and still saved, and they say so on their face.
"""
from types import SimpleNamespace

import pytest

from app import config
from app import data_store as store
from app.agent import llm, subagents, tools
from app.agent.llm import LLMUnusable
from app.schemas import Job


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "JOBS_CSV", tmp_path / "jobs.csv")
    monkeypatch.setattr(config, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(config, "APPLICATIONS_CSV", tmp_path / "applications.csv")
    monkeypatch.setattr(config, "APPLICATIONS_DIR", tmp_path / "applications")
    monkeypatch.setattr(config, "PROFILE_YML", tmp_path / "profile.yml")
    (tmp_path / "jobs").mkdir()
    monkeypatch.setattr(tools.status, "record", lambda *a, **k: None)
    return tmp_path


def _pin_provider(monkeypatch, provider: str = "anthropic", key: str = "sk-test") -> None:
    """Pin the settings the client and the mock-ness check read, so the runner's own
    environment (a real .env, an exported LLM_PROVIDER) can never leak into a test."""
    monkeypatch.setattr(llm, "get_settings", lambda: SimpleNamespace(
        llm_provider=provider, llm_model="a-model",
        anthropic_api_key=key, openai_api_key=key, ollama_base_url="http://ollama.invalid"))


# Each provider's wire format: what a finished answer looks like, and a cut-off one.
# One row per branch of the client — a rule taught to one branch is a rule for none.
# Truncation DETECTION is required of all three. Sending a cap is not: see
# `test_the_openai_request_sends_no_cap_of_its_own`.
_PROVIDERS = [
    ("anthropic",
     {"content": [{"type": "text", "text": "hi"}], "stop_reason": "end_turn"},
     {"content": [{"type": "text", "text": "half a doc"}], "stop_reason": "max_tokens"}),
    ("openai",
     {"choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}]},
     {"choices": [{"message": {"content": "half a doc"}, "finish_reason": "length"}]}),
    ("ollama",
     {"message": {"content": "hi"}, "done_reason": "stop"},
     {"message": {"content": "half a doc"}, "done_reason": "length"}),
]


def _cap_sent(provider: str, payload: dict) -> int:
    """Where each provider that takes a cap carries it."""
    return payload["options"]["num_predict"] if provider == "ollama" else payload["max_tokens"]


class _Response:
    """Just enough of an httpx response for the client — no network, ever."""

    def __init__(self, body: dict):
        self._body = body

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._body


def _capture_posts(monkeypatch, body: dict) -> list[dict]:
    sent: list[dict] = []

    def fake_post(url, headers=None, json=None, timeout=None):
        sent.append({**json, "_timeout": timeout})
        return _Response(body)

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    return sent


def _reply(text: str = "", truncated: bool = False, error: str = "", mocked: bool = False):
    return SimpleNamespace(text=text, truncated=truncated, error=error, mocked=mocked)


def _fake_client(monkeypatch, *replies):
    """Install a fake LLMClient returning `replies` in order (the last one repeats).

    The queue lives out here because each subagent constructs its own client — which is
    also what lets a test drive `evaluator` and `reviewer` with different answers, the
    combination that decides whether a placeholder reaches the row."""
    queue = list(replies) or [_reply()]

    class _Client:
        def __init__(self, max_tokens: int = llm.MAX_TOKENS_DEFAULT, **kwargs):
            self.max_tokens = max_tokens

        def complete(self, messages, tools=None):
            return queue.pop(0) if len(queue) > 1 else queue[0]

    monkeypatch.setattr(subagents, "LLMClient", _Client)


# --- the cap, in every provider's dialect ----------------------------------------------

@pytest.mark.parametrize("provider", ["anthropic", "ollama"])
def test_the_output_cap_is_the_callers_not_one_hardcoded_number(monkeypatch, provider):
    ok_body = next(ok for name, ok, _ in _PROVIDERS if name == provider)
    _pin_provider(monkeypatch, provider)
    sent = _capture_posts(monkeypatch, ok_body)

    llm.LLMClient().complete([{"role": "user", "content": "hi"}])
    llm.LLMClient(max_tokens=llm.MAX_TOKENS_LONG_FORM).complete([{"role": "user", "content": "hi"}])

    assert [_cap_sent(provider, p) for p in sent] == [
        llm.MAX_TOKENS_DEFAULT, llm.MAX_TOKENS_LONG_FORM]
    # A long-form generation legitimately runs for minutes: raising the cap without the
    # timeout would just trade truncation for a timeout.
    assert {p["_timeout"] for p in sent} == {llm._TIMEOUT_S}


def test_the_openai_request_sends_no_cap_of_its_own(monkeypatch):
    """OpenAI is the exception, on purpose. It doesn't require a cap — omitting it means
    "as much as the model allows", which is never too little — and `max_tokens` is
    rejected outright by reasoning-model configs that work today. Detection is what
    fixes the bug there; sending a field to fix a problem this branch doesn't have
    would break a working setup."""
    _pin_provider(monkeypatch, "openai")
    ok_body = next(ok for name, ok, _ in _PROVIDERS if name == "openai")
    sent = _capture_posts(monkeypatch, ok_body)

    llm.LLMClient(max_tokens=llm.MAX_TOKENS_LONG_FORM).complete([{"role": "user", "content": "x"}])

    assert "max_tokens" not in sent[0] and "max_completion_tokens" not in sent[0]
    assert sent[0]["_timeout"] == llm._TIMEOUT_S


def test_a_one_page_cv_would_never_have_fit_the_old_cap():
    assert llm.MAX_TOKENS_LONG_FORM > llm.MAX_TOKENS_DEFAULT > 1024


def test_whole_documents_ask_for_the_long_form_cap(monkeypatch):
    """The subagents that emit a complete document — not a reply — must say so, or the
    cap is right on average and wrong exactly where it matters."""
    caps: list[int] = []

    class _RecordingClient:
        def __init__(self, max_tokens: int = llm.MAX_TOKENS_DEFAULT, **kwargs):
            caps.append(max_tokens)

        def complete(self, messages, tools=None):
            # mocked: this test is about which cap each caller asks for, so every call
            # must reach `complete` — a real provider answering with no LaTeX is a
            # refusal now (see test_a_cv_the_model_never_wrote_is_never_substituted).
            return _reply(text='{"fit_score": 0.9, "company": "Acme"}', mocked=True)

    monkeypatch.setattr(subagents, "LLMClient", _RecordingClient)
    subagents.evaluator("job md", {})                                  # a JSON verdict
    subagents.cv_tailor({}, "Eng", "Acme", "job md")                   # a LaTeX document
    subagents.cover_letter_writer(SimpleNamespace(company="Acme", position="Eng"),
                                  "job md", {}, None, "")              # a letter
    subagents.job_parser("posting text")                               # re-emits the posting
    assert caps == [llm.MAX_TOKENS_DEFAULT, *[llm.MAX_TOKENS_LONG_FORM] * 3]


# --- the flags, in every provider's dialect --------------------------------------------

@pytest.mark.parametrize("provider,ok_body,cut_body", _PROVIDERS)
def test_a_completion_that_stopped_at_the_cap_says_so(monkeypatch, provider, ok_body, cut_body):
    _pin_provider(monkeypatch, provider)

    _capture_posts(monkeypatch, cut_body)
    cut = llm.LLMClient().complete([{"role": "user", "content": "hi"}])
    assert cut.truncated is True and cut.text == "half a doc"  # a fragment, not an answer

    _capture_posts(monkeypatch, ok_body)
    assert llm.LLMClient().complete([{"role": "user", "content": "hi"}]).truncated is False


@pytest.mark.parametrize("provider,_ok,_cut", _PROVIDERS)
def test_a_failed_call_carries_its_error_not_only_a_mock_reply(monkeypatch, provider, _ok, _cut):
    _pin_provider(monkeypatch, provider)

    def boom(*a, **k):
        raise RuntimeError("429 rate limited")

    monkeypatch.setattr(llm.httpx, "post", boom)
    res = llm.LLMClient().complete([{"role": "user", "content": "hi"}])
    assert "429 rate limited" in res.error          # the caller can refuse to fabricate
    assert "mock" in res.text.lower()               # the chat loop still gets a reply


@pytest.mark.parametrize("provider,_ok,cut_body", _PROVIDERS)
def test_the_whole_chain_holds_from_the_providers_stop_reason(
        monkeypatch, provider, _ok, cut_body):
    """End to end with only the HTTP call faked: a real client, the real subagent. This
    is the reported bug exactly — a valid key, a configured provider, and a CV that
    doesn't fit the cap — and on EVERY provider it must now fail loudly instead of
    returning the template that says to configure the provider already configured."""
    _pin_provider(monkeypatch, provider)
    _capture_posts(monkeypatch, cut_body)
    with pytest.raises(LLMUnusable) as exc:
        subagents.cv_tailor({"name": "Someone"}, "Engineer", "Acme", "job md")
    assert "output cap" in str(exc.value)


# --- refusing to pass a placeholder off as analysis ------------------------------------

def test_a_failed_provider_never_becomes_a_mock_cover_letter(monkeypatch):
    _fake_client(monkeypatch, _reply(text="(LLM provider error: 429)", error="429 rate limited"))
    with pytest.raises(LLMUnusable) as exc:
        subagents.cover_letter_writer(
            SimpleNamespace(company="Acme", position="Engineer"), "job md", {}, None, "")
    assert "429 rate limited" in str(exc.value)


def test_a_failed_provider_never_becomes_a_fit_score(monkeypatch):
    _fake_client(monkeypatch, _reply(text="(LLM provider error: 429)", error="429 rate limited"))
    with pytest.raises(LLMUnusable):
        subagents.evaluator("job md", {"name": "Someone"})


def test_an_empty_completion_is_reported_too(monkeypatch):
    _fake_client(monkeypatch, _reply(text="   "))
    with pytest.raises(LLMUnusable):
        subagents.evaluator("job md", {"name": "Someone"})


@pytest.mark.parametrize("run", [
    lambda: subagents.upskiller("job md", {"name": "Someone"}),
    lambda: subagents.patterns_analyst({"applications": 3}),
])
def test_every_advisory_subagent_refuses_a_failed_completion(monkeypatch, run):
    """The gaps list and the patterns narrative have "(mock) example gap" / "(mock)
    configure an LLM provider" fallbacks of their own. Advice invented by a fallback is
    still advice the user will act on, so the same rule binds here — and each subagent
    needs its own test, or the guard can be deleted from one of them unnoticed."""
    _fake_client(monkeypatch, _reply(text="(LLM provider error: 429)", error="429 rate limited"))
    with pytest.raises(LLMUnusable):
        run()


def test_a_cv_the_model_never_wrote_is_never_substituted(tmp_store, monkeypatch):
    """Issue #88's actual complaint, and the case no flag catches: the call succeeded,
    the model just answered with prose instead of a LaTeX document. `_extract_latex`
    returns "" and the old code handed back `cv_render.fallback_tex` — a PDF stamped
    "Mock CV — set an LLM provider in .env" to a user who has set one."""
    from fastapi.testclient import TestClient

    from app.main import app

    store.upsert_job(Job(id="2026-001", company="Acme", company_job_id="R1", position="Eng"))
    store.write_job_md("2026-001", "# Eng — Acme\n\n## Posting\nBuild stuff.")
    _fake_client(monkeypatch, _reply(text="Sure! Here is a summary of your CV: ..."))

    r = TestClient(app).post("/api/jobs/2026-001/cv")
    assert r.status_code == 502
    assert "Mock CV" not in r.text
    assert store.read_cv_tex("2026-001") is None  # nothing persisted, nothing to download


def test_a_letter_the_model_did_write_is_never_swapped_for_the_stub(tmp_store, monkeypatch):
    """The letter path had no "did it parse?" step, so it decided by sniffing the reply
    for the mock's own banner text. A model that quotes that phrase — from this repo's
    docs, or because the posting asked it to — had its real letter thrown away and the
    "(Mock draft…)" template saved over it. Whether the mock wrote something is the
    client's answer to give, not a substring's."""
    from fastapi.testclient import TestClient

    from app.main import app

    store.upsert_job(Job(id="2026-001", company="Acme", company_job_id="R1", position="Eng"))
    letter = ("Dear Acme Hiring Team,\n\nYour posting warns that Running in **mock** LLM "
              "mode produces placeholder text; I have shipped the real thing.\n\nSincerely,")
    _fake_client(monkeypatch, _reply(text=letter))

    r = TestClient(app).post("/api/jobs/2026-001/cover-letter")
    assert r.status_code == 200
    assert r.json()["content"] == letter        # the model's letter, kept
    assert "Mock draft" not in r.text


@pytest.mark.parametrize("generate,expected", [
    (lambda: tools.generate_tailored_cv("2026-001"), "Mock CV"),
    (lambda: tools.generate_cover_letter("2026-001"), "Mock draft"),
])
def test_honest_mock_mode_still_gets_its_labelled_stub(tmp_store, monkeypatch, generate, expected):
    """The other half of the rule: with no provider configured the stub is the truth,
    it says so on its face, and the demo keeps working."""
    store.upsert_job(Job(id="2026-001", company="Acme", company_job_id="R1", position="Eng"))
    _fake_client(monkeypatch, _reply(text="Running in mock LLM mode. You said: ...", mocked=True))
    out = generate()
    assert expected in (out.get("tex") or out.get("content") or "")


def test_a_truncated_cv_parse_is_reported_not_read_as_mock_mode(tmp_store, monkeypatch):
    """`parse_cv`'s empty-handed answer is "parsing needs a real LLM (mock mode)" —
    wrong, and actively misleading, when the key is set and the model ran out of room."""
    _fake_client(monkeypatch, _reply(text='{"name": "Some', truncated=True))
    with pytest.raises(LLMUnusable):
        tools.parse_cv("Someone. Engineer at Acme. Skills: Python.")
    assert not store.read_profile().get("name")  # nothing half-parsed written to the profile


def test_a_truncated_posting_parse_is_reported_not_a_parse_failure(tmp_store, monkeypatch):
    """Same for the paste-a-posting path: "couldn't parse a job from that text" tells
    the user to paste more, which is the opposite of what a cap overrun needs."""
    _fake_client(monkeypatch, _reply(text='{"company": "Ac', truncated=True))
    with pytest.raises(LLMUnusable):
        tools.ingest_job_doc("Acme is hiring an Engineer. Requires Python.")


def test_unparseable_output_still_falls_back_to_the_placeholder(monkeypatch):
    """Only the unambiguous failures raise. Output that merely doesn't parse is what an
    echoed prompt looks like in mock mode, so the deterministic stub stays."""
    _fake_client(monkeypatch, _reply(text='echo Profile {"targets": {}} end'))
    ev = subagents.evaluator("job md", {})
    assert ev == subagents.STUB_EVALUATION and subagents.is_stub_evaluation(ev)


# --- the one place every score is written ----------------------------------------------

def test_a_reviewed_placeholder_is_still_a_placeholder(tmp_store, monkeypatch):
    """The whole point — and the way a marker-in-the-dict fails. `evaluate_fit` runs
    evaluator -> reviewer -> save, and the reviewer returns a dict rebuilt from ITS own
    model output, so anything hung on the evaluator's result is gone by the save. Drive
    the real path: output the evaluator can't use, then a reviewer reply that parses."""
    _pin_provider(monkeypatch, "anthropic", "sk-test")
    store.upsert_job(Job(id="2026-001", company="Acme", company_job_id="R1", position="Eng"))
    store.write_job_md("2026-001", "# Eng — Acme\n\n## Posting\nBuild stuff.")
    _fake_client(
        monkeypatch,
        _reply(text="I'm afraid I can't help with that."),            # evaluator -> stub
        _reply(text='{"fit_score": 0.5, "recommendation": "hold"}'),  # reviewer -> parses
    )

    with pytest.raises(LLMUnusable):
        tools.evaluate_fit("2026-001")
    assert store.get_job("2026-001").fit_score is None       # no fabricated score on the row
    assert not store.read_evaluation("2026-001")             # and no sidecar either


def test_the_same_path_in_honest_mock_mode_still_saves_the_placeholder(tmp_store, monkeypatch):
    """Mock mode is a supported way to run the app: there the placeholder IS the truth,
    the UI says so, and the demo must keep working."""
    _pin_provider(monkeypatch, "mock")
    store.upsert_job(Job(id="2026-001", company="Acme", company_job_id="R1", position="Eng"))
    store.write_job_md("2026-001", "# Eng — Acme\n\n## Posting\nBuild stuff.")
    _fake_client(
        monkeypatch,
        _reply(text="I'm afraid I can't help with that."),
        _reply(text='{"fit_score": 0.5, "recommendation": "hold"}'),
    )

    saved = tools.evaluate_fit("2026-001")
    assert saved["fit_score"] == 0.5 and store.get_job("2026-001").fit_score == 0.5


def test_a_real_evaluation_is_saved_untouched(tmp_store, monkeypatch):
    _pin_provider(monkeypatch, "anthropic", "sk-test")
    store.upsert_job(Job(id="2026-002", company="Acme", company_job_id="R2", position="Eng"))
    store.write_job_md("2026-002", "# Eng — Acme\n\n## Posting\nBuild stuff.")
    _fake_client(monkeypatch, _reply(text='{"fit_score": 0.9, "recommendation": "apply"}'))

    assert tools.evaluate_fit("2026-002")["fit_score"] == 0.9
    assert store.get_job("2026-002").fit_score == 0.9


def test_an_internal_mode_put_is_never_treated_as_a_placeholder(tmp_store, monkeypatch):
    """Internal mode PUTs Claude's own reasoning through the same save path. It cannot
    set `stub`, and must not be second-guessed by pattern-matching its content — 0.5 is
    a legitimate score for a middling job."""
    from fastapi.testclient import TestClient

    from app.main import app

    _pin_provider(monkeypatch, "anthropic", "sk-test")
    store.upsert_job(Job(id="2026-003", company="Acme", company_job_id="R3", position="Eng"))
    r = TestClient(app).put("/api/jobs/2026-003/evaluation",
                            json={"fit_score": 0.5, "recommendation": "hold"})
    assert r.status_code == 200 and store.get_job("2026-003").fit_score == 0.5


# --- a failure must not leave the app looking stuck ------------------------------------

def test_a_failed_action_returns_the_app_to_idle(tmp_store, monkeypatch):
    """`current_task` only moved back to "idle" on the success record, which was safe
    while nothing could fail. STATUS.md and the UI would otherwise read "Evaluating fit
    for 2026-001" until the process restarts."""
    events: list[tuple[str, "str | None"]] = []
    monkeypatch.setattr(tools.status, "record",
                        lambda ev, detail="", **kw: events.append((ev, kw.get("current_task"))))
    _pin_provider(monkeypatch, "anthropic", "sk-test")
    store.upsert_job(Job(id="2026-001", company="Acme", company_job_id="R1", position="Eng"))
    _fake_client(monkeypatch, _reply(text="", error="429 rate limited"))

    with pytest.raises(LLMUnusable):
        tools.evaluate_fit("2026-001")
    assert ("evaluate_failed", "idle") in events
    assert events[-1][1] == "idle"


def test_a_failed_chat_turn_returns_the_app_to_idle(tmp_store, monkeypatch):
    """Same rule one level up: the chat handler sets "Handling chat request" and only
    clears it on the way out. A raising handler would pin it there for good."""
    from app.agent import harness

    events: list[tuple[str, "str | None"]] = []
    monkeypatch.setattr(harness.status, "record",
                        lambda ev, detail="", **kw: events.append((ev, kw.get("current_task"))))
    monkeypatch.setattr(harness, "_handle_ask",
                        lambda *a: (_ for _ in ()).throw(LLMUnusable("the provider failed")))

    with pytest.raises(LLMUnusable):
        harness.run("how should I prioritize this week?", [])
    assert ("chat_failed", "idle") in events
    assert events[-1][1] == "idle"


# --- what the user actually sees -------------------------------------------------------

def test_the_cv_route_reports_the_truncation_instead_of_returning_a_mock_cv(
        tmp_store, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    store.upsert_job(Job(id="2026-001", company="Acme", company_job_id="R1", position="Eng"))
    store.write_job_md("2026-001", "# Eng — Acme\n\n## Posting\nBuild stuff.")
    _fake_client(monkeypatch,
                 _reply(text="\\documentclass{article}\\begin{document}Half", truncated=True))

    r = TestClient(app).post("/api/jobs/2026-001/cv")
    assert r.status_code == 502
    assert "output cap" in r.json()["detail"]
    assert store.read_cv_tex("2026-001") is None  # no "Mock CV" left behind either
