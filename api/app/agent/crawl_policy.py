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

A REDIRECT IS A FETCH OF A DIFFERENT URL, so it runs the same five checks. We
follow chains ourselves, one hop at a time, and never hand `follow_redirects` to
httpx: httpx would fetch a 302's target with none of the above, which is how an
allow-listed board turns into a request to an arbitrary host. For the same reason
`safe_get` forwards no transport options to httpx at all (see its docstring).

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
        "recruitee.com",          # public per-tenant offers API: <slug>.recruitee.com
        "api.smartrecruiters.com",  # public postings API
        "apply.workable.com",     # public markdown job feed
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

# How many redirect hops one safe_get may follow. Every hop is re-gated, but the chain
# still has to end: a redirect loop (or a board that bounces us around) must not turn one
# pasted URL into an unbounded crawl.
MAX_REDIRECTS = 5

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
    scheme = (urlparse(url).scheme or "").lower()
    if scheme not in ("http", "https"):
        # Job boards are http(s). Anything else (file:, ftp:, gopher:) is a classic
        # SSRF/local-read vector and has no legitimate caller here.
        raise PolicyViolation(
            f"refusing {scheme or 'scheme-less'} URL {url!r} — job boards are fetched over http(s) only"
        )
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


def _get_once(url: str, timeout: float) -> httpx.Response:
    """One GET, our honest identity, and NO redirect following.

    `follow_redirects=False` is the whole point: if httpx followed the hop, the target
    would be fetched without the block-list, the allow-list, robots or the rate limit.
    Callers walk the chain themselves and re-gate each hop."""
    return httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout,
                     follow_redirects=False)


def _redirect_target(response: httpx.Response) -> str:
    """Absolute URL a redirect points at; "" when there is nothing followable (relative
    Location values are resolved against the URL we asked for, as a browser would)."""
    location = response.headers.get("location", "")
    if not location:
        return ""
    try:
        return str(response.url.join(location))
    except Exception:  # unparseable Location: nothing we could validate, so don't follow
        return ""


# A robots.txt we were REFUSED is not a board with no robots.txt. "No robots" means
# allow; "we were not permitted to learn the rules" must not quietly mean the same, or a
# redirect becomes a way to switch robots enforcement OFF for a board. Cached in its place
# so the refusal is sticky and costs one fetch.
_ROBOTS_REFUSED = robotparser.RobotFileParser()
_ROBOTS_REFUSED.parse(["User-agent: *", "Disallow: /"])


def _robots_hop_ok(origin_host: str, target: str) -> bool:
    """May a robots.txt redirect be followed? Only within the board's OWN domain.

    `boards.greenhouse.io/robots.txt -> greenhouse.io/robots.txt` is canonicalisation and
    the answer is still the board's own; anything else is a host we never checked handing
    us our crawl rules. Suffix match in both directions (apex <-> subdomain) — deliberately
    NOT the allow-list, because a board's apex domain usually isn't on it."""
    if (urlparse(target).scheme or "").lower() not in ("http", "https"):
        return False
    host = host_of(target)
    return bool(host) and (_suffix_match(host, origin_host) or _suffix_match(origin_host, host))


def _robots(host: str, scheme: str) -> robotparser.RobotFileParser | None:
    with _lock:
        if host in _robots_cache:
            return _robots_cache[host]
    rp: robotparser.RobotFileParser | None = robotparser.RobotFileParser()
    try:
        url = f"{scheme}://{host}/robots.txt"
        for _ in range(MAX_REDIRECTS + 1):
            r = _get_once(url, 10.0)
            if not r.is_redirect:
                break
            target = _redirect_target(r)
            if not target:
                break
            # Even a robots.txt redirect is an outbound fetch, and this one decides what we
            # may crawl: following it off-domain would reach a host we never checked AND
            # let that host write our policy. (No robots check on robots itself, and no
            # rate limit — this is the courtesy call, not the crawl.)
            if not _robots_hop_ok(host, target):
                raise PolicyViolation(
                    f"robots.txt for {host} redirected off its own domain (-> {target})"
                )
            url = target
        else:
            # A loop is a misconfiguration, not a refusal — same class as a timeout, so it
            # falls through to the network-hiccup clause and we proceed politely.
            raise RuntimeError(f"robots.txt for {host} redirected more than {MAX_REDIRECTS} times")
        if r.status_code == 200 and r.text.strip():
            rp.parse(r.text.splitlines())
        else:
            rp = None  # no usable robots -> allow (still allow-listed + rate-limited)
    except PolicyViolation as exc:  # refused, so we never learned the rules -> don't crawl
        log.warning("robots.txt for %s could not be resolved (%s); treating as disallow", host, exc)
        rp = _ROBOTS_REFUSED
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


def _gate(url: str, *, redirected_from: str | None = None) -> None:
    """The whole policy for ONE fetch: block-list -> allow-list -> robots -> rate limit.

    Every hop of a redirect chain runs it, so a hop is exactly as constrained as the URL
    the user pasted. A refused hop keeps the original reason verbatim — a blocked board
    still explains why it is blocked and what to do instead, an off-allow-list host still
    says so — and names the hop that caused it, because "LinkedIn is blocked" is baffling
    when you pasted an Apple link."""
    try:
        check_url(url)
        if redirected_from and urlparse(redirected_from).scheme == "https" and \
                urlparse(url).scheme != "https":
            # The host is allow-listed either way, but the transport isn't: a hop that
            # drops to plaintext hands the rest of the exchange to anyone on the path.
            raise PolicyViolation("it downgrades the connection from https to http")
        if not _robots_allows(url):
            raise PolicyViolation(f"robots.txt disallows fetching {url}")
    except PolicyViolation as exc:
        if redirected_from is None:
            raise
        raise PolicyViolation(
            f"refusing to follow the redirect {redirected_from} -> {url}: {exc}"
        ) from exc
    _respect_rate_limit(host_of(url))


def safe_get(
    url: str, *, timeout: float = 30.0, follow_redirects: bool = False, **kwargs
) -> httpx.Response:
    """Policy-enforced GET — the only sanctioned way to fetch a job board.

    `follow_redirects=True` follows the chain HERE, one hop at a time, re-running the
    full gate on each. It is never delegated to httpx, which would fetch a 302's target
    with no block-list, no allow-list, no robots and no rate limit — a paste of an
    allow-listed board could then reach an arbitrary host (SSRF), a ToS-blocked board, or
    a robots-disallowed path, and nothing in the logs would say so.

    Nothing else is forwarded to httpx either: `headers` would let a caller overwrite the
    honest User-Agent, `cookies`/`auth` would send credentials to a job board, `proxy`/
    `transport`/`mounts` would route the bytes past the host we just checked, and
    `verify=False` would drop TLS verification. Each undoes a guarantee this module
    exists to make, so they are not accepted — widen the policy here, in the open."""
    if kwargs:  # refuse loudly rather than forward something that silently drops a check
        raise PolicyViolation(
            f"safe_get does not forward transport options to httpx ({', '.join(sorted(kwargs))}) — "
            "headers/cookies/auth/proxy/verify/redirect handling each disable one of the "
            "crawl-policy checks. Extend crawl_policy.py instead of passing them through."
        )
    current, previous = url, None
    for _ in range(MAX_REDIRECTS + 1):
        _gate(current, redirected_from=previous)
        log.info("crawl GET %s", current)
        response = _get_once(current, timeout)
        if not (follow_redirects and response.is_redirect):
            return response
        target = _redirect_target(response)
        if not target:
            return response  # a 3xx we cannot follow — hand it back as-is
        previous, current = current, target
    raise PolicyViolation(
        f"redirect chain starting at {url} exceeded {MAX_REDIRECTS} hops — refusing to keep following"
    )
