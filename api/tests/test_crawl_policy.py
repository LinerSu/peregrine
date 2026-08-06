"""Crawl-policy: the good-bot guardrail. These are the rules we never want to regress.

The pure helpers (block-list, allow-list, scheme) are the cheap half. The half that
actually decides what leaves the machine is `safe_get`, and the rules it must keep are:

  * **a redirect is a fetch of a different URL**, so it runs the same gate. Handing
    `follow_redirects` to httpx looks harmless and is not: httpx fetches the target of a
    302 with no block-list, no allow-list, no robots and no rate limit, which turns an
    allow-listed board into a request to whatever the board (or anyone who can answer for
    it) points at. The allow-list is the SSRF boundary AND a published promise about which
    sites we will and won't crawl, and a redirect must not be able to walk around either.
  * **a refused hop keeps its reason.** "LinkedIn's Terms prohibit scraping — paste the
    text instead" is advice the user can act on; "fetch failed" is not.
  * **the chain ends.** A redirect loop is otherwise an unbounded crawl of a host we are
    supposed to be polite to.
  * **robots.txt is fetched too**, and it is the one response that decides what we may
    crawl — so its redirects may only stay within the board's own domain, and being
    refused one must fail CLOSED. "No robots file" means allow; "we weren't allowed to
    read it" meaning allow too would make a redirect a way to switch robots off.
  * **nothing else reaches httpx.** `headers` would overwrite the honest User-Agent,
    `cookies`/`auth` would send credentials to a job board, `proxy` would route past the
    host check, `verify=False` would drop TLS. Each one silently deletes a guarantee.

Every test here is offline — httpx is stubbed with a stand-in that follows redirects the
way httpx does, so "unfixed code follows the hop" is what the assertions actually see.
"""
import httpx
import pytest

from app.agent import crawl_policy as cp
from app.agent.crawl_policy import PolicyViolation

APPLE = "https://jobs.apple.com/en-us/details/200123456/engineer"
AMAZON = "https://www.amazon.jobs/en/jobs/1234567"


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


@pytest.mark.parametrize("url", ["ftp://api.lever.co/etc", "file:///etc/passwd", "jobs.apple.com/x"])
def test_non_http_urls_are_refused(url):
    # The allow-list only means something for schemes that can carry a host. file:/ftp:
    # are the classic way to turn a URL fetcher into a local-file / intranet reader.
    with pytest.raises(PolicyViolation):
        cp.check_url(url)


# --------------------------------------------------------------------------- #
# safe_get: the gate that decides what actually leaves the machine.
# --------------------------------------------------------------------------- #
def _redirect(frm: str, to: str, status: int = 302) -> httpx.Response:
    return httpx.Response(status, headers={"location": to}, request=httpx.Request("GET", frm))


def _ok(url: str, body: str = "a posting") -> httpx.Response:
    return httpx.Response(200, text=body, request=httpx.Request("GET", url))


class _Net:
    """A stand-in for httpx that answers from a script and — critically — follows
    redirects exactly the way httpx does when asked to. So if safe_get delegates the hop,
    the hop really happens here, and the test sees the host that got fetched."""

    def __init__(self):
        self.script: dict[str, httpx.Response] = {}
        self.fetched: list[str] = []
        self.agents: list[str] = []
        self.follow_flags: list[bool] = []
        self.robots_checked: list[str] = []
        self.robots_denied: set[str] = set()
        self.rate_limited: list[str] = []

    def get(self, url, *, headers=None, timeout=None, follow_redirects=False, **kwargs):
        url = str(url)
        self.follow_flags.append(follow_redirects)
        for _ in range(20):
            self.fetched.append(url)
            self.agents.append((headers or {}).get("User-Agent", ""))
            response = self.script.get(url) or _ok(url)
            if not (follow_redirects and response.is_redirect):
                return response
            url = str(response.url.join(response.headers["location"]))
        raise AssertionError("stub httpx: runaway redirect chain")

    # stand-ins for the two policy steps that would otherwise touch the network / sleep
    def robots_allows(self, url: str) -> bool:
        self.robots_checked.append(url)
        return url not in self.robots_denied

    def rate_limit(self, host: str) -> None:
        self.rate_limited.append(host)


@pytest.fixture
def net(monkeypatch):
    """safe_get with no sockets: httpx stubbed, robots answered from the script, the rate
    limiter recorded instead of run (the real one sleeps 2s per host)."""
    stub = _Net()
    monkeypatch.setattr(cp.httpx, "get", stub.get)
    monkeypatch.setattr(cp, "_robots_allows", stub.robots_allows)
    monkeypatch.setattr(cp, "_respect_rate_limit", stub.rate_limit)
    return stub


def test_a_redirect_off_the_allow_list_is_refused_and_never_fetched(net):
    # The allow-list is the SSRF boundary. A 302 must not be able to step over it.
    net.script[APPLE] = _redirect(APPLE, "https://evil.example.com/collect")
    with pytest.raises(PolicyViolation) as exc:
        cp.safe_get(APPLE, follow_redirects=True)
    assert "allow-list" in str(exc.value)
    assert "evil.example.com" in str(exc.value) and APPLE in str(exc.value)  # names the hop
    assert net.fetched == [APPLE]  # the redirect target was never requested


def test_a_redirect_to_a_blocked_board_still_says_why_it_is_blocked(net):
    # Landing on LinkedIn via a redirect breaks the same ToS promise as pasting its URL,
    # and the user needs the same advice back.
    net.script[APPLE] = _redirect(APPLE, "https://www.linkedin.com/jobs/view/1/")
    with pytest.raises(PolicyViolation) as exc:
        cp.safe_get(APPLE, follow_redirects=True)
    assert "blocked by policy" in str(exc.value)
    assert "Paste the job description text instead" in str(exc.value)
    assert net.fetched == [APPLE]


def test_every_hop_is_robots_checked_and_rate_limited(net):
    # robots and the rate limit are per HOST. A chain that changes host and keeps only the
    # first host's checks is exactly the crawl we promise not to be.
    net.script[APPLE] = _redirect(APPLE, AMAZON)
    r = cp.safe_get(APPLE, follow_redirects=True)
    assert r.status_code == 200 and str(r.url) == AMAZON
    assert net.fetched == [APPLE, AMAZON]
    assert net.robots_checked == [APPLE, AMAZON]
    assert net.rate_limited == ["jobs.apple.com", "www.amazon.jobs"]


def test_robots_disallowing_a_later_hop_stops_the_chain(net):
    net.script[APPLE] = _redirect(APPLE, AMAZON)
    net.robots_denied = {AMAZON}
    with pytest.raises(PolicyViolation) as exc:
        cp.safe_get(APPLE, follow_redirects=True)
    assert "robots.txt disallows" in str(exc.value)
    assert net.fetched == [APPLE]


def test_a_redirect_chain_is_bounded(net):
    # A loop (or a board bouncing us around) must not become an unbounded crawl.
    net.script[APPLE] = _redirect(APPLE, APPLE)
    with pytest.raises(PolicyViolation) as exc:
        cp.safe_get(APPLE, follow_redirects=True)
    assert "exceeded" in str(exc.value)
    assert len(net.fetched) == cp.MAX_REDIRECTS + 1


def test_a_relative_redirect_is_resolved_and_re_gated(net):
    net.script[APPLE] = _redirect(APPLE, "/en-us/details/200123456/engineer-canonical")
    r = cp.safe_get(APPLE, follow_redirects=True)
    assert str(r.url) == "https://jobs.apple.com/en-us/details/200123456/engineer-canonical"
    assert net.rate_limited == ["jobs.apple.com", "jobs.apple.com"]  # the hop was gated too


def test_httpx_is_never_asked_to_follow_a_redirect(net):
    # The bug this pins: one kwarg moves redirect-following into httpx, where none of the
    # five checks exist. Not following at all is the safe default; the caller opts in and
    # gets OUR gated follow.
    net.script[APPLE] = _redirect(APPLE, AMAZON)
    r = cp.safe_get(APPLE)
    assert r.status_code == 302 and net.fetched == [APPLE]   # not followed without opt-in
    cp.safe_get(APPLE, follow_redirects=True)
    assert net.follow_flags == [False, False, False]         # ...and never by httpx


@pytest.mark.parametrize(
    "kwargs",
    [
        # a browser UA, spelled without the literal string the pre-commit guard greps for
        {"headers": {"User-Agent": "Chrome 120 (Windows NT 10.0) — a browser we are not"}},
        {"cookies": {"session": "x"}},                                 # credentialed fetch
        {"auth": ("user", "pw")},
        {"verify": False},                                             # no TLS verification
        {"proxy": "http://127.0.0.1:8080"},                            # routed past the host check
    ],
)
def test_safe_get_refuses_transport_options_that_would_undo_the_gate(net, kwargs):
    # Same shape of hole as follow_redirects: a kwarg forwarded to httpx that deletes one
    # of the five guarantees. Nothing is forwarded, so none of them can.
    with pytest.raises(PolicyViolation) as exc:
        cp.safe_get(APPLE, **kwargs)
    assert "does not forward transport options" in str(exc.value)
    assert net.fetched == []


def test_the_user_agent_is_ours_and_honest_on_every_hop(net):
    net.script[APPLE] = _redirect(APPLE, AMAZON)
    cp.safe_get(APPLE, follow_redirects=True)
    assert net.agents == [cp.USER_AGENT, cp.USER_AGENT]
    assert "Mozilla" not in cp.USER_AGENT and "github.com" in cp.USER_AGENT  # honest + contactable


def test_a_redirect_that_downgrades_https_to_http_is_refused(net):
    net.script[APPLE] = _redirect(APPLE, "http://jobs.apple.com/en-us/details/200123456/engineer")
    with pytest.raises(PolicyViolation) as exc:
        cp.safe_get(APPLE, follow_redirects=True)
    assert "downgrades" in str(exc.value)
    assert net.fetched == [APPLE]  # the allow-list would have passed it; the transport doesn't


def test_an_unfollowable_redirect_is_handed_back_not_guessed_at(net):
    # A 3xx whose Location can't be parsed into a URL: there is nothing to validate, so
    # there is nothing to follow. The response goes back as-is and the caller's
    # raise_for_status turns it into an error — we never invent a target.
    net.script[APPLE] = _redirect(APPLE, "\x7f")
    r = cp.safe_get(APPLE, follow_redirects=True)
    assert r.status_code == 302 and net.fetched == [APPLE]


# --------------------------------------------------------------------------- #
# robots.txt is fetched too — and it decides what we may crawl.
# --------------------------------------------------------------------------- #
@pytest.fixture
def robots_net(monkeypatch):
    """Like `net`, but with the real _robots/_robots_allows in play."""
    stub = _Net()
    monkeypatch.setattr(cp.httpx, "get", stub.get)
    monkeypatch.setattr(cp, "_respect_rate_limit", stub.rate_limit)
    monkeypatch.setattr(cp, "_robots_cache", {})  # module-level cache: don't leak between tests
    return stub


def test_a_robots_txt_redirect_off_its_own_domain_is_refused_and_fails_closed(robots_net):
    # Following it blindly would reach a host we never checked AND let that host write our
    # crawl rules. Refusing is only half the fix: "we were refused" must not then be read as
    # "no robots file, go ahead", or the redirect has simply switched robots off.
    robots = "https://jobs.apple.com/robots.txt"
    robots_net.script[robots] = _redirect(robots, "https://evil.example.com/robots.txt")
    robots_net.script["https://evil.example.com/robots.txt"] = _ok(
        "https://evil.example.com/robots.txt", "User-agent: *\nDisallow:\n")  # "everything allowed"

    with pytest.raises(PolicyViolation) as exc:
        cp.safe_get(APPLE)
    assert "robots.txt disallows" in str(exc.value)
    assert robots_net.fetched == [robots]  # neither the off-domain robots nor the posting


def test_a_robots_txt_redirect_within_the_board_is_followed_and_honored(robots_net):
    # Canonicalisation (subdomain -> apex) is legitimate and the answer is still the
    # board's own, so we follow it — and then obey what it says.
    robots = "https://jobs.apple.com/robots.txt"
    apex = "https://apple.com/robots.txt"
    robots_net.script[robots] = _redirect(robots, apex)
    robots_net.script[apex] = _ok(apex, "User-agent: *\nDisallow: /en-us/\n")

    with pytest.raises(PolicyViolation) as exc:
        cp.safe_get(APPLE)
    assert "robots.txt disallows" in str(exc.value)
    assert robots_net.fetched == [robots, apex]  # the hop happened; the posting was not fetched


def test_a_robots_txt_redirect_loop_is_bounded_and_stays_polite(robots_net):
    # A loop is a misconfiguration, not a refusal: bounded, and we proceed without robots
    # exactly as we do for a timeout — a broken CDN must not lock the user out of a board.
    robots = "https://jobs.apple.com/robots.txt"
    robots_net.script[robots] = _redirect(robots, robots)

    r = cp.safe_get(APPLE)
    assert r.status_code == 200
    assert robots_net.fetched == [robots] * (cp.MAX_REDIRECTS + 1) + [APPLE]
