"""Job-board providers (the scraper's tools).

Generic, ATS-feed based — inspired by santifer/career-ops. Each provider takes a
company slug and returns normalized raw postings. Greenhouse is implemented
against its public board API; Ashby/Lever are stubbed with the same interface so
they can be filled in later. Hosts are pinned (no arbitrary URLs) to avoid SSRF.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx

from ..logging_config import get_logger

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
        r = httpx.get(url, timeout=timeout)
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


def _amazon_ingest(job_id: str, timeout: float = 30.0) -> RawPosting | None:
    """Fetch a single Amazon posting via the public search.json API. Host pinned."""
    url = f"https://www.amazon.jobs/en/search.json?base_query={job_id}&result_limit=10"
    try:
        r = httpx.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout)
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

    Supported: amazon.jobs and Greenhouse-hosted boards. Returns None for
    unsupported hosts (add a parser here to extend)."""
    m = _AMAZON_RE.search(url)
    if m:
        return _amazon_ingest(m.group(1))

    m = _GREENHOUSE_RE.search(url)
    if m:
        slug, _job_id = m.group(1), m.group(2)
        postings = greenhouse(slug.title(), slug)
        return next((p for p in postings if p.company_job_id == _job_id), None)

    log.info("ingest_url: unsupported host for %s", url)
    return None
