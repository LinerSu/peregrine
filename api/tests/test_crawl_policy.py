"""Crawl-policy: the good-bot guardrail. These are the rules we never want to regress."""
import pytest

from app.agent import crawl_policy as cp
from app.agent.crawl_policy import PolicyViolation


@pytest.mark.parametrize(
    "url",
    [
        "https://jobs.apple.com/en-us/details/200668037-0836/role",
        "https://api.ashbyhq.com/posting-api/job-board/openai",
        "https://api.lever.co/v0/postings/leverdemo?mode=json",
        "https://boards-api.greenhouse.io/v1/boards/acme/jobs",
        "https://www.amazon.jobs/en/search.json?base_query=1",
    ],
)
def test_allowed_hosts_pass(url):
    cp.check_url(url)  # should not raise


@pytest.mark.parametrize(
    "url",
    [
        "https://www.linkedin.com/jobs/view/123/",
        "https://www.indeed.com/viewjob?jk=x",
        "https://www.glassdoor.com/job/x",
        "https://www.metacareers.com/jobs/1/",
    ],
)
def test_blocked_hosts_raise(url):
    with pytest.raises(PolicyViolation):
        cp.check_url(url)


def test_arbitrary_host_refused():
    with pytest.raises(PolicyViolation):
        cp.check_url("https://evil.example.com/jobs/1")


def test_helpers():
    assert cp.host_of("https://jobs.apple.com/x") == "jobs.apple.com"
    assert cp.is_allowed_host("boards-api.greenhouse.io")
    assert not cp.is_allowed_host("example.com")
    assert "LinkedIn" in (cp.blocked_reason("www.linkedin.com") or "")
    assert cp.blocked_reason("jobs.apple.com") is None
