"""Outbound crawl policy — be a good bot, never a malicious crawler.

Every outbound job-board fetch MUST go through `safe_get()`. It enforces, in
order, before any bytes leave the box:

  1. Block-list   — sites whose ToS forbid scraping or that bot-protect (LinkedIn,
                    Meta) are refused outright, with a reason shown to the user.
  2. Allow-list   — we only fetch the boards we explicitly support. Arbitrary
                    hosts are refused (scope + SSRF safety).
  3. robots.txt   — respected per host (cached); an explicit Disallow refuses.
  4. Rate limit   — a minimum interval between requests to the same host.
  5. Honest identity — a descriptive, self-identifying User-Agent. We do NOT
                    impersonate a browser to defeat blocks, and never scrape
                    login/auth-walled content.

The allow-list is the hard security boundary; robots + rate-limit are courtesy
that keep us a well-behaved citizen and off ban lists.
"""
from __future__ import annotations

import threading
import time
from urllib import robotparser
from urllib.parse import urlparse

import httpx

from ..logging_config import get_logger

log = get_logger(__name__)

# Identify ourselves honestly — contactable, not a spoofed browser string.
USER_AGENT = (
    "PeregrineJobSearch/0.1 (personal job-search assistant; "
    "+https://github.com/LinerSu/peregrine)"
)

# Only these hosts may be fetched. Suffix-matched, so API subdomains are covered.
ALLOWED_HOSTS: frozenset[str] = frozenset(
    {
        "boards-api.greenhouse.io",
        "boards.greenhouse.io",
        "job-boards.greenhouse.io",
        "amazon.jobs",
        "jobs.apple.com",
        "api.ashbyhq.com",
        "api.lever.co",
    }
)

# Explicitly refused, with a human-readable reason surfaced to the user.
BLOCKED_HOSTS: dict[str, str] = {
    "linkedin.com": (
        "LinkedIn's User Agreement prohibits scraping and it actively blocks bots. "
        "Paste the job description text instead."
    ),
    "metacareers.com": (
        "Meta bot-protects its careers site (needs a real browser session). "
        "Paste the job description text instead."
    ),
    "indeed.com": (
        "Indeed's ToS prohibits automated access. Paste the job description text instead."
    ),
    "glassdoor.com": (
        "Glassdoor's ToS prohibits automated access. Paste the job description text instead."
    ),
}

MIN_INTERVAL_SECONDS = 2.0  # per host, between requests

_last_request: dict[str, float] = {}
_robots_cache: dict[str, robotparser.RobotFileParser | None] = {}
_lock = threading.Lock()


class PolicyViolation(RuntimeError):
    """Raised when an outbound fetch is refused by crawl policy."""


def host_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def _suffix_match(host: str, allowed: str) -> bool:
    return host == allowed or host.endswith("." + allowed)


def blocked_reason(host: str) -> str | None:
    for blocked, reason in BLOCKED_HOSTS.items():
        if _suffix_match(host, blocked):
            return reason
    return None


def is_allowed_host(host: str) -> bool:
    return any(_suffix_match(host, h) for h in ALLOWED_HOSTS)


def check_url(url: str) -> None:
    """Raise PolicyViolation if this URL must not be fetched. No network I/O."""
    host = host_of(url)
    if not host:
        raise PolicyViolation(f"no host in URL: {url!r}")
    reason = blocked_reason(host)
    if reason:
        raise PolicyViolation(f"{host} is blocked by policy — {reason}")
    if not is_allowed_host(host):
        raise PolicyViolation(
            f"{host} is not on the supported-board allow-list; "
            "refusing to crawl arbitrary sites."
        )


def _robots(host: str, scheme: str) -> robotparser.RobotFileParser | None:
    with _lock:
        if host in _robots_cache:
            return _robots_cache[host]
    rp: robotparser.RobotFileParser | None = robotparser.RobotFileParser()
    try:
        r = httpx.get(
            f"{scheme}://{host}/robots.txt",
            headers={"User-Agent": USER_AGENT},
            timeout=10.0,
            follow_redirects=True,
        )
        if r.status_code == 200 and r.text.strip():
            rp.parse(r.text.splitlines())
        else:
            rp = None  # no usable robots -> allow (still allow-listed + rate-limited)
    except Exception as exc:  # network hiccup: don't hard-fail, just proceed politely
        log.info("robots fetch failed for %s (%s); proceeding without", host, exc)
        rp = None
    with _lock:
        _robots_cache[host] = rp
    return rp


def _robots_allows(url: str) -> bool:
    parts = urlparse(url)
    rp = _robots(parts.hostname or "", parts.scheme or "https")
    return True if rp is None else rp.can_fetch(USER_AGENT, url)


def _respect_rate_limit(host: str) -> None:
    while True:
        with _lock:
            wait = MIN_INTERVAL_SECONDS - (time.monotonic() - _last_request.get(host, 0.0))
            if wait <= 0:
                _last_request[host] = time.monotonic()
                return
        time.sleep(min(wait, MIN_INTERVAL_SECONDS))


def safe_get(url: str, *, timeout: float = 30.0, **kwargs) -> httpx.Response:
    """Policy-enforced GET — the only sanctioned way to fetch a job board."""
    check_url(url)
    if not _robots_allows(url):
        raise PolicyViolation(f"robots.txt disallows fetching {url}")
    _respect_rate_limit(host_of(url))
    headers = {"User-Agent": USER_AGENT, **kwargs.pop("headers", {})}
    log.info("crawl GET %s", url)
    return httpx.get(url, headers=headers, timeout=timeout, **kwargs)
