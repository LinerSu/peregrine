"""Intent router: the right small action for each request (pure, no side effects)."""
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
