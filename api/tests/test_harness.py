"""Intent router: the right small action for each request (pure, no side effects).

Also pins what the harness is allowed to WRITE DOWN about a request. Pasting a CV into
chat is a designed flow — anything over 400 characters routes to `_handle_cv` — and the
first 120 characters of a CV are a name, an email address and a phone number. Those went
verbatim into `logs/activity.jsonl` and then into `logs/STATUS.md`, which the README
invites the user to paste into a fresh agent session to restore context. The activity log
records the intent and a size, the way `tools.parse_cv` already does; the body stays in
the request that carried it.
"""
import pytest

from app.agent import harness


@pytest.mark.parametrize(
    "message, intent",
    [
        ("https://jobs.apple.com/en-us/details/200668037-0836/x", "ingest"),
        ("find jobs matching my CV", "search"),
        ("please scan the portals", "search"),
        ("what skills do I need for the Apple role?", "upskill"),
        ("where are my skill gaps?", "upskill"),
        ("what am I missing skill-wise", "upskill"),
        ("evaluate my fit for Stripe", "evaluate"),
        ("judge my CV against this posting", "evaluate"),
        ("how should I prioritize my applications this week?", "ask"),
        ("what skills do I already have?", "ask"),
    ],
)
def test_route_picks_one_bounded_intent(message, intent):
    assert harness._route(message)[0] == intent


def test_router_is_single_pass_not_a_loop():
    # The harness exposes bounded handlers and no MAX_ITERS loop constant.
    assert not hasattr(harness, "MAX_ITERS")
    intent, handler = harness._route("find jobs")
    assert callable(handler)


def test_the_activity_log_records_the_intent_not_the_message_body(monkeypatch):
    """A pasted CV routes here by design. The log must be able to say what happened
    without repeating a word of what the user wrote."""
    recorded: list[tuple[str, str]] = []
    monkeypatch.setattr(harness.status, "record",
                        lambda event, detail="", **kw: recorded.append((event, detail)))
    monkeypatch.setattr(harness.tools, "parse_cv", lambda text: {"updated": True})

    pasted = ("CANDIDATE NAME · candidate@example.com · +1-555-0000\n"
              "Senior Engineer at Initech. " * 40)
    assert len(pasted) > 400  # long enough to be treated as a CV paste
    harness.run(pasted, [])

    blob = " ".join(f"{e} {d}" for e, d in recorded)
    assert "candidate@example.com" not in blob
    assert "CANDIDATE NAME" not in blob
    assert "Initech" not in blob
    assert ("chat", f"cv ({len(pasted)} chars)") in recorded  # intent + size, nothing else
