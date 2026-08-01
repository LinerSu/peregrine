"""Job-board providers (the scraper's tools).

Generic, ATS-feed based — inspired by santifer/career-ops. Each provider takes a
company slug and returns normalized raw postings. Implemented: Greenhouse, Ashby,
Lever, Recruitee, SmartRecruiters and Workable (per-tenant boards), plus Amazon
(query-based — its `slug` carries a search query, not a board id). Hosts are pinned
to the crawl_policy allow-list (no arbitrary URLs) to avoid SSRF.
"""
from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from ..logging_config import get_logger
from . import crawl_policy
from .crawl_policy import PolicyViolation

log = get_logger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class RawPosting:
    company: str
    company_job_id: str
    position: str
    location: str = ""
    url: str = ""
    posted_date: str = ""
    description: str = ""


def _strip_html(raw: str) -> str:
    """Plain text from a feed's description. Some boards (e.g. Greenhouse) return HTML that
    is itself entity-escaped (`&lt;div&gt;`, `&amp;nbsp;`), so unescape first to reveal the
    real tags, strip them, then unescape again to resolve entities the tags were hiding
    (`&amp;nbsp;` -> `&nbsp;` -> a space). Plain HTML (recruitee/ashby) is unaffected."""
    text = html.unescape(raw or "")
    text = _TAG_RE.sub("", text)
    text = html.unescape(text).replace("\xa0", " ")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _host_ok(url: str, *suffixes: str) -> bool:
    """Keep a URL from untrusted feed content only if its host is on an expected
    domain (a tenant feed could embed off-domain links)."""
    host = crawl_policy.host_of(url)
    return bool(host) and any(host == s or host.endswith("." + s) for s in suffixes)


def greenhouse(company: str, slug: str, timeout: float = 30.0) -> list[RawPosting]:
    """Public Greenhouse board API. Host is pinned."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    try:
        r = crawl_policy.safe_get(url, timeout=timeout)
        r.raise_for_status()
        jobs = r.json().get("jobs", [])
    except Exception as exc:
        log.warning("greenhouse(%s) failed: %s", slug, exc)
        return []
    out = []
    for j in jobs:
        out.append(
            RawPosting(
                company=company,
                company_job_id=str(j.get("id", "")),
                position=j.get("title", ""),
                location=(j.get("location") or {}).get("name", ""),
                url=j.get("absolute_url", ""),
                posted_date=(j.get("updated_at") or "")[:10],
                description=_strip_html(j.get("content", "")),
            )
        )
    return out


def ashby(company: str, slug: str, timeout: float = 30.0) -> list[RawPosting]:
    """Ashby public posting API. Host pinned via crawl_policy."""
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    try:
        r = crawl_policy.safe_get(url, timeout=timeout)
        r.raise_for_status()
        jobs = r.json().get("jobs", [])
    except Exception as exc:
        log.warning("ashby(%s) failed: %s", slug, exc)
        return []
    out = []
    for j in jobs:
        if j.get("isListed") is False:
            continue
        location = j.get("location", "") or ""
        if j.get("isRemote"):
            location = f"{location} (remote)".strip()
        out.append(
            RawPosting(
                company=company,
                company_job_id=str(j.get("id", "")),
                position=j.get("title", ""),
                location=location,
                url=j.get("jobUrl", ""),
                posted_date=(j.get("publishedAt") or "")[:10],
                description=_strip_html(j.get("descriptionPlain") or j.get("descriptionHtml", "")),
            )
        )
    return out


def _epoch_ms_to_date(ms: Any) -> str:
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError):
        return ""


def lever(company: str, slug: str, timeout: float = 30.0) -> list[RawPosting]:
    """Lever public postings API. Host pinned via crawl_policy."""
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    try:
        r = crawl_policy.safe_get(url, timeout=timeout)
        r.raise_for_status()
        postings = r.json()
    except Exception as exc:
        log.warning("lever(%s) failed: %s", slug, exc)
        return []
    out = []
    for j in postings:
        cats = j.get("categories") or {}
        body = _strip_html(j.get("descriptionPlain", ""))
        for lst in j.get("lists", []) or []:
            body += f"\n\n## {lst.get('text', '')}\n{_strip_html(lst.get('content', ''))}"
        if j.get("additionalPlain"):
            body += f"\n\n{_strip_html(j['additionalPlain'])}"
        out.append(
            RawPosting(
                company=company,
                company_job_id=str(j.get("id", "")),
                position=j.get("text", ""),
                location=cats.get("location", ""),
                url=j.get("hostedUrl", ""),
                posted_date=_epoch_ms_to_date(j.get("createdAt")),
                description=body.strip(),
            )
        )
    return out


def _parse_recruitee(data: dict, company: str) -> list[RawPosting]:
    """Parse a Recruitee /api/offers/ response. Pure (unit-tested)."""
    out = []
    for j in data.get("offers", []) or []:
        parts = [j.get("city") or "", j.get("country") or ""]
        if j.get("remote"):
            parts.append("Remote")
        location = j.get("location") or ", ".join(p for p in parts if p)
        raw_url = j.get("careers_url") or j.get("url") or ""
        out.append(
            RawPosting(
                company=company,
                company_job_id=str(j.get("id") or ""),
                position=j.get("title") or "",  # present-but-null must not become None
                location=location,
                url=raw_url if _host_ok(raw_url, "recruitee.com") else "",
                posted_date=(j.get("created_at") or "")[:10],
                description=_strip_html(j.get("description") or ""),
            )
        )
    return out


def recruitee(company: str, slug: str, timeout: float = 30.0) -> list[RawPosting]:
    """Recruitee public per-tenant offers API. Host pinned via crawl_policy."""
    url = f"https://{slug}.recruitee.com/api/offers/"
    try:
        r = crawl_policy.safe_get(url, timeout=timeout)
        r.raise_for_status()
        return _parse_recruitee(r.json(), company)  # parse inside try: a bad payload -> []
    except Exception as exc:
        log.warning("recruitee(%s) failed: %s", slug, exc)
        return []


def _parse_smartrecruiters(data: dict, company: str, slug: str) -> list[RawPosting]:
    """Parse a SmartRecruiters /postings response. Pure (unit-tested)."""
    out = []
    for j in data.get("content", []) or []:
        loc = j.get("location") if isinstance(j.get("location"), dict) else {}
        full = loc.get("fullLocation") or ", ".join(
            p for p in (loc.get("city"), loc.get("region"), loc.get("country")) if p
        )
        if loc.get("remote"):
            full = f"{full}, Remote" if full else "Remote"
        jid = str(j.get("id") or "")
        out.append(
            RawPosting(
                company=company,
                company_job_id=jid,
                position=j.get("name") or "",  # present-but-null must not become None
                location=full,
                # Synthesize the public job URL (the API `ref` points back at the API host).
                url=f"https://jobs.smartrecruiters.com/{slug}/{jid}" if jid else "",
                posted_date=(j.get("releasedDate") or "")[:10],
            )
        )
    return out


_SR_PAGE = 100


def smartrecruiters(company: str, slug: str, timeout: float = 30.0) -> list[RawPosting]:
    """SmartRecruiters public postings API (first page only — the scan's new-job cap
    bounds it; a full page is logged so a >100-posting board isn't silently truncated)."""
    url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit={_SR_PAGE}&offset=0&status=PUBLIC"
    try:
        r = crawl_policy.safe_get(url, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        if len(data.get("content") or []) >= _SR_PAGE:
            log.warning("smartrecruiters(%s): first %d postings only; more may exist", slug, _SR_PAGE)
        return _parse_smartrecruiters(data, company, slug)  # parse inside try: bad payload -> []
    except Exception as exc:
        log.warning("smartrecruiters(%s) failed: %s", slug, exc)
        return []


_WORKABLE_VIEW_RE = re.compile(r"/jobs/view/([^/.]+)")


def _parse_workable(text: str, company: str) -> list[RawPosting]:
    """Parse Workable's public markdown feed (its only no-auth surface). Rows look like:
    `| Title | Dept | Location | Type | Salary | Posted | [View](…/jobs/view/<id>.md) |`.
    Pure (unit-tested)."""
    out = []
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cols = [c.strip() for c in line.split("|")]
        if len(cols) < 8:
            continue
        title = cols[1]
        if not title or title.lower() == "title" or set(title) <= set("-: "):
            continue  # header / separator row
        m = re.search(r"\[View\]\(([^)]+)\)", line)
        url = m.group(1) if m else ""
        if url.endswith(".md"):
            url = url[:-3]
        if not _host_ok(url, "apply.workable.com"):
            continue  # skip rows with no resolvable on-domain URL
        vm = _WORKABLE_VIEW_RE.search(url)
        out.append(
            RawPosting(
                company=company,
                company_job_id=vm.group(1) if vm else "",
                position=title,
                location=cols[3],
                url=url,
                # The feed carries no body, so description stays empty (keyword filters
                # then match on the title only for workable jobs).
            )
        )
    return out


def workable(company: str, slug: str, timeout: float = 30.0) -> list[RawPosting]:
    """Workable public markdown feed (its only no-auth public surface)."""
    url = f"https://apply.workable.com/{slug}/jobs.md"
    try:
        r = crawl_policy.safe_get(url, timeout=timeout)
        r.raise_for_status()
        return _parse_workable(r.text, company)  # parse inside try: a bad feed -> []
    except Exception as exc:
        log.warning("workable(%s) failed: %s", slug, exc)
        return []


def _amazon_date(raw: Any) -> str:
    """Amazon's search feed dates jobs as 'June 23, 2026' — normalize to ISO so the
    posted-date column and the scan's max-age filter work (fall back to '')."""
    s = str(raw or "").strip()
    for fmt in ("%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def _amazon_body(j: dict) -> str:
    """Description + basic/preferred qualifications, as Markdown sections (skipping blanks).
    Shared by the board scan and the single-URL ingest."""
    parts = [
        ("Description", j.get("description", "")),
        ("Basic qualifications", j.get("basic_qualifications", "")),
        ("Preferred qualifications", j.get("preferred_qualifications", "")),
    ]
    return "\n\n".join(f"## {title}\n{_strip_html(v)}" for title, v in parts if v).strip()


_AMAZON_PAGE = 100


def amazon(company: str, slug: str, timeout: float = 30.0) -> list[RawPosting]:
    """Amazon is QUERY-based, not a per-tenant board — its `slug` carries a search query
    (e.g. "machine learning engineer"). Pages amazon.jobs' public search.json; the scan's
    new-job cap is the real bound. Host pinned via crawl_policy."""
    query = (slug or "").strip() or "engineer"
    out: list[RawPosting] = []
    for offset in range(0, 500, _AMAZON_PAGE):  # bounded loop; scan cap stops persistence first
        url = (
            f"https://www.amazon.jobs/en/search.json?base_query={quote(query)}"
            f"&result_limit={_AMAZON_PAGE}&offset={offset}&sort=recent"
        )
        try:
            r = crawl_policy.safe_get(url, timeout=timeout)
            r.raise_for_status()
            jobs = r.json().get("jobs", []) or []
        except Exception as exc:
            log.warning("amazon(%s) failed: %s", query, exc)
            break
        if not jobs:
            break
        for j in jobs:
            path = j.get("job_path", "") or ""
            out.append(
                RawPosting(
                    company=company,
                    company_job_id=str(j.get("id_icims") or j.get("id") or ""),
                    position=j.get("title") or "",  # present-but-null must not become None
                    location=j.get("normalized_location") or j.get("location") or "",
                    url=f"https://www.amazon.jobs{path}" if path else "",
                    posted_date=_amazon_date(j.get("posted_date")),
                    description=_amazon_body(j),
                )
            )
        if len(jobs) < _AMAZON_PAGE:
            break
    return out


def generic(company: str, slug: str, timeout: float = 30.0) -> list[RawPosting]:
    log.info("generic provider stub for %s — add HTML scraping here", company)
    return []


PROVIDERS = {
    "greenhouse": greenhouse,
    "ashby": ashby,
    "lever": lever,
    "recruitee": recruitee,
    "smartrecruiters": smartrecruiters,
    "workable": workable,
    "amazon": amazon,
    "generic": generic,
}


def fetch(provider: str, company: str, slug: str) -> list[RawPosting]:
    fn = PROVIDERS.get(provider.lower(), generic)
    return fn(company, slug)


# --------------------------------------------------------------------------- #
# Single-posting ingest by URL (paste a job link in the chat)
# --------------------------------------------------------------------------- #
_AMAZON_RE = re.compile(r"amazon\.jobs/(?:[a-z-]+/)?jobs/(\d+)", re.I)
_GREENHOUSE_RE = re.compile(r"greenhouse\.io/(?:embed/job_app\?for=)?([\w-]+)/jobs/(\d+)", re.I)
_APPLE_RE = re.compile(r"jobs\.apple\.com/[\w-]+/details/([\w-]+)", re.I)
_ASHBY_RE = re.compile(r"jobs\.ashbyhq\.com/([\w-]+)/([\w-]+)", re.I)
_LEVER_RE = re.compile(r"jobs\.lever\.co/([\w-]+)/([\w-]+)", re.I)
_APPLE_HYDRATION_RE = re.compile(
    r'window\.__staticRouterHydrationData\s*=\s*JSON\.parse\("(.*?)"\);', re.S
)


def _find_apple_posting(node: Any) -> dict | None:
    """Walk Apple's hydration payload for the posting object (has positionId + locations)."""
    if isinstance(node, dict):
        if "positionId" in node and "locations" in node:
            return node
        for v in node.values():
            if (hit := _find_apple_posting(v)) is not None:
                return hit
    elif isinstance(node, list):
        for v in node:
            if (hit := _find_apple_posting(v)) is not None:
                return hit
    return None


def _apple_ingest(url: str, timeout: float = 30.0) -> RawPosting | None:
    """Parse a single Apple posting from the page's embedded hydration JSON.

    Host is allow-listed to jobs.apple.com by crawl_policy; the SPA needs the
    title slug in the path, so we fetch the pasted URL through safe_get."""
    try:
        r = crawl_policy.safe_get(url, timeout=timeout, follow_redirects=True)
        r.raise_for_status()
        m = _APPLE_HYDRATION_RE.search(r.text)
        if not m:
            return None
        data = json.loads(json.loads('"' + m.group(1) + '"'))
        job = _find_apple_posting(data)
    except Exception as exc:
        log.warning("apple ingest(%s) failed: %s", url, exc)
        return None
    if not job:
        return None

    locs = job.get("locations") or []
    location = ", ".join(
        filter(None, [(locs[0].get("name") or locs[0].get("city")), locs[0].get("stateProvince")])
    ) if locs else ""
    if len(locs) > 1:
        location += f" (+{len(locs) - 1} more)"

    def sect(title: str, key: str) -> str:
        val = _strip_html(job.get(key, ""))
        return f"## {title}\n{val}\n\n" if val else ""

    body = (
        sect("Summary", "jobSummary")
        + sect("Description", "description")
        + sect("Responsibilities", "responsibilities")
        + sect("Minimum qualifications", "minimumQualifications")
        + sect("Preferred qualifications", "preferredQualifications")
    ).strip()

    return RawPosting(
        company="Apple",
        company_job_id=str(job.get("positionId") or _APPLE_RE.search(url).group(1)),
        position=job.get("postingTitle", ""),
        location=location,
        url=url,
        posted_date=str(job.get("postDateInGMT", ""))[:10],
        description=body,
    )


def _amazon_ingest(job_id: str, timeout: float = 30.0) -> RawPosting | None:
    """Fetch a single Amazon posting via the public search.json API. Host pinned."""
    url = f"https://www.amazon.jobs/en/search.json?base_query={job_id}&result_limit=10"
    try:
        r = crawl_policy.safe_get(url, timeout=timeout)
        r.raise_for_status()
        jobs = r.json().get("jobs", [])
    except Exception as exc:
        log.warning("amazon ingest(%s) failed: %s", job_id, exc)
        return None

    job = next((j for j in jobs if str(j.get("id_icims")) == str(job_id)), jobs[0] if jobs else None)
    if not job:
        return None

    # `or` (not a get-default) — the API can return a present-but-null field, which would make
    # position/location None or company_job_id the literal "None" and break downstream .strip().
    return RawPosting(
        company="Amazon",
        company_job_id=str(job.get("id_icims") or job_id),
        position=job.get("title") or "",
        location=job.get("normalized_location") or job.get("location") or "",
        url=f"https://www.amazon.jobs{job.get('job_path') or ''}",
        posted_date=_amazon_date(job.get("posted_date")),
        description=_amazon_body(job),
    )


def supports_url(url: str) -> bool:
    """Can ingest_url parse this URL at all?

    ingest_url returns None for two very different situations — a board we have no parser
    for, and a posting the board no longer lists. A liveness check must not confuse them:
    the first means "can't tell", the second means "this job is probably dead". Callers
    ask here first so they can tell which None they got."""
    return any(
        rx.search(url)
        for rx in (_AMAZON_RE, _APPLE_RE, _GREENHOUSE_RE, _ASHBY_RE, _LEVER_RE)
    )


def ingest_url(url: str) -> RawPosting | None:
    """Detect the source from a pasted URL and return a normalized posting.

    Supported: amazon.jobs, Apple (jobs.apple.com), Greenhouse, Ashby
    (jobs.ashbyhq.com) and Lever (jobs.lever.co) boards. Returns None for
    unsupported hosts (add a parser here to extend). Raises PolicyViolation for
    hosts our crawl policy refuses (e.g. LinkedIn)."""
    reason = crawl_policy.blocked_reason(crawl_policy.host_of(url))
    if reason:
        raise PolicyViolation(f"{crawl_policy.host_of(url)} is blocked by policy — {reason}")

    m = _AMAZON_RE.search(url)
    if m:
        return _amazon_ingest(m.group(1))

    if _APPLE_RE.search(url):
        return _apple_ingest(url)

    m = _GREENHOUSE_RE.search(url)
    if m:
        slug, _job_id = m.group(1), m.group(2)
        postings = greenhouse(slug.title(), slug)
        return next((p for p in postings if p.company_job_id == _job_id), None)

    m = _ASHBY_RE.search(url)
    if m:
        org, jid = m.group(1), m.group(2)
        return next((p for p in ashby(org.title(), org) if p.company_job_id == jid), None)

    m = _LEVER_RE.search(url)
    if m:
        org, jid = m.group(1), m.group(2)
        return next((p for p in lever(org.title(), org) if p.company_job_id == jid), None)

    log.info("ingest_url: unsupported host for %s", url)
    return None
