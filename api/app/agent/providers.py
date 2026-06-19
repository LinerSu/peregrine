"""Job-board providers (the scraper's tools).

Generic, ATS-feed based — inspired by santifer/career-ops. Each provider takes a
company slug and returns normalized raw postings. Greenhouse is implemented
against its public board API; Ashby/Lever are stubbed with the same interface so
they can be filled in later. Hosts are pinned (no arbitrary URLs) to avoid SSRF.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

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


def _strip_html(html: str) -> str:
    text = _TAG_RE.sub("", html or "")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


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
    log.info("ashby provider stub for %s (slug=%s) — implement feed parsing", company, slug)
    return []


def lever(company: str, slug: str, timeout: float = 30.0) -> list[RawPosting]:
    log.info("lever provider stub for %s (slug=%s) — implement feed parsing", company, slug)
    return []


def generic(company: str, slug: str, timeout: float = 30.0) -> list[RawPosting]:
    log.info("generic provider stub for %s — add HTML scraping here", company)
    return []


PROVIDERS = {
    "greenhouse": greenhouse,
    "ashby": ashby,
    "lever": lever,
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

    desc = _strip_html(job.get("description", ""))
    basic = _strip_html(job.get("basic_qualifications", ""))
    pref = _strip_html(job.get("preferred_qualifications", ""))
    body = (
        f"## Description\n{desc}\n\n"
        f"## Basic qualifications\n{basic}\n\n"
        f"## Preferred qualifications\n{pref}\n"
    )
    return RawPosting(
        company="Amazon",
        company_job_id=str(job.get("id_icims", job_id)),
        position=job.get("title", ""),
        location=job.get("normalized_location", job.get("location", "")),
        url=f"https://www.amazon.jobs{job.get('job_path', '')}",
        posted_date=str(job.get("posted_date", "")),
        description=body,
    )


def ingest_url(url: str) -> RawPosting | None:
    """Detect the source from a pasted URL and return a normalized posting.

    Supported: amazon.jobs, Apple (jobs.apple.com) and Greenhouse-hosted boards.
    Returns None for unsupported hosts (add a parser here to extend). Raises
    PolicyViolation for hosts our crawl policy refuses (e.g. LinkedIn)."""
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

    log.info("ingest_url: unsupported host for %s", url)
    return None
