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
