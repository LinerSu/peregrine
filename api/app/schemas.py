"""Pydantic models shared across the API and agent."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, field_validator

JobStatus = Literal["open", "closed", "removed", "applied", "interviewing", "rejected", "offer"]


class Job(BaseModel):
    id: str
    company: str
    company_job_id: str
    position: str
    status: JobStatus = "open"
    location: str = ""
    flexibility: str = ""
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    currency: str = "USD"
    posted_date: str = ""
    close_date: str = ""
    url: str = ""
    fit_score: Optional[float] = None
    detail_md: str = ""
    role_category: str = ""
    # Structured tags extracted from the posting (deterministic, no LLM). Lists are stored
    # comma-joined so they fit a CSV cell; the UI splits them back into chips.
    level: str = ""          # required degree: PhD / MS / BS (highest mentioned)
    req_skills: str = ""     # required skills/languages, e.g. "Python, OCaml, Docker"
    domains: str = ""        # finer fields, e.g. "Compilers, Machine Learning"
    starred: bool = False


class Application(Job):
    applied_date: str = ""
    interview_date: str = ""
    contacts: str = ""
    notes: str = ""


class FitEvaluation(BaseModel):
    job_id: str
    fit_score: float
    strengths: list[str] = []
    weaknesses: list[str] = []
    materials: list[str] = []
    recommendation: Literal["apply", "hold", "skip"] = "hold"
    # v2 structured blocks, computed server-side (see app/evaluation.py).
    legitimacy_score: Optional[float] = None
    legitimacy_flags: list[str] = []
    archetype: str = ""


class EvaluationInput(BaseModel):
    """Body for PUT /api/jobs/{id}/evaluation — store-only persist (no LLM).

    legitimacy_*/archetype are computed server-side from the posting and ignored
    on input, so they're identical across External and Internal modes."""
    fit_score: float
    strengths: list[str] = []
    weaknesses: list[str] = []
    materials: list[str] = []
    recommendation: Literal["apply", "hold", "skip"] = "hold"


class MissingSkill(BaseModel):
    skill: str
    why: str = ""
    how_to_close: str = ""


class UpskillingInput(BaseModel):
    """Body for PUT /api/jobs/{id}/upskilling — store-only persist (no LLM)."""
    summary: str = ""
    missing_skills: list[MissingSkill] = []


class CoverLetterInput(BaseModel):
    """Body for PUT /api/jobs/{id}/cover-letter — store-only persist (no LLM).
    Used by Internal mode: Claude writes the draft in the terminal, then saves it."""
    content: str


class SkillInput(BaseModel):
    name: str
    level: str = ""
    evidence: str = ""
    category: str = ""  # Languages / Frameworks & Libraries / Tools / Domains / Soft skills


def _as_str(v: Any) -> str:
    return "" if v is None else str(v)


class ProfileLink(BaseModel):
    """A labelled link from the résumé (rendered with an icon by host)."""
    label: str = ""
    url: str = ""

    @field_validator("label", "url", mode="before")
    @classmethod
    def _coerce(cls, v):
        return _as_str(v)


class ProfileItem(BaseModel):
    """One résumé entry within a section (a degree, a job, a paper, a project…)."""
    heading: str = ""    # e.g. "PhD, Computer Science — Stanford University"
    subhead: str = ""    # e.g. "2019–2024 · Stanford, CA"
    detail: str = ""     # full prose / bullets (shown when the section is expanded)
    links: list[ProfileLink] = []

    @field_validator("heading", "subhead", "detail", mode="before")
    @classmethod
    def _coerce(cls, v):
        return _as_str(v)

    @field_validator("links", mode="before")
    @classmethod
    def _coerce_links(cls, v):
        if not isinstance(v, list):
            return []
        return [{"url": x} if isinstance(x, str) else x for x in v if isinstance(x, (str, dict))]


class ProfileSection(BaseModel):
    """A foldable résumé section: a one-line `summary` + the full `items`."""
    id: str = ""         # "education" | "experience" | "research" | "service" | "awards" | "projects"
    title: str = ""      # display title
    summary: str = ""    # one-sentence folded view
    items: list[ProfileItem] = []

    @field_validator("id", "title", "summary", mode="before")
    @classmethod
    def _coerce(cls, v):
        return _as_str(v)

    @field_validator("items", mode="before")
    @classmethod
    def _coerce_items(cls, v):
        # drop non-dict elements too, so one stray item can't 422 the whole save
        return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


class ProfileInput(BaseModel):
    """Body for PUT /api/profile — store-only profile merge (Internal mode: Claude
    parses the CV, then PUTs the extracted fields). Only CV-derived keys are
    accepted, so it can't clobber targets / comp / work_auth / preferences."""
    name: Optional[str] = None
    headline: Optional[str] = None
    location: Optional[str] = None
    skills: Optional[list[SkillInput]] = None
    links: Optional[dict[str, str]] = None        # named profile links: github/website/linkedin/scholar/email…
    sections: Optional[list[ProfileSection]] = None

    @field_validator("links", mode="before")
    @classmethod
    def _clean_links(cls, v):
        if not isinstance(v, dict):
            return None
        cleaned = {str(k): str(val) for k, val in v.items() if val not in (None, "")}
        return cleaned or None

    @field_validator("sections", mode="before")
    @classmethod
    def _clean_sections(cls, v):
        # Drop non-dict elements so one stray item can't 422 the whole save — matches the
        # External parse path, which keeps the good sections and skips the bad ones.
        # (skills keep their strict shape — that's enforced by an existing test.)
        if not isinstance(v, list):
            return None
        return [s for s in v if isinstance(s, dict)] or None


class CvSourceInput(BaseModel):
    """Body for PUT /api/cv/source — store-only raw CV text (Internal mode reads it)."""
    text: str = ""


class CvTexInput(BaseModel):
    """Body for PUT /api/jobs/{id}/cv — store-only tailored-CV LaTeX (Internal mode:
    Claude writes the .tex in the terminal, then saves it; the API compiles a PDF)."""
    tex: str


class JobSourceInput(BaseModel):
    """Body for PUT /api/jobs/ingest-source — store-only raw posting text the user
    pasted/uploaded (Internal mode parses it into a tracked job)."""
    text: str = ""


class JobIngestInput(BaseModel):
    """Body for POST /api/jobs/ingest-doc/save — store-only (Internal mode: Claude
    parses the pasted/uploaded posting, then POSTs the structured fields). No LLM.

    Optional fields are null-tolerant: a model emitting JSON `null` for an absent
    field is coerced to "" rather than rejected (see _coerce_none)."""
    company: str
    position: str
    company_job_id: Optional[str] = ""
    location: Optional[str] = ""
    url: Optional[str] = ""
    posted_date: Optional[str] = ""
    description: Optional[str] = ""

    @field_validator("company_job_id", "location", "url", "posted_date", "description")
    @classmethod
    def _coerce_none(cls, v: Optional[str]) -> str:
        return v or ""


class CompanyInput(BaseModel):
    """One scan source. `provider` is validated against the live providers in the route;
    `slug` is the ATS handle (or, for query-based providers like amazon, the search query)."""
    name: str = ""
    provider: str = "generic"
    slug: str = ""

    @field_validator("name", "provider", "slug", mode="before")
    @classmethod
    def _coerce(cls, v):
        return _as_str(v)


class ScanFilters(BaseModel):
    """Hard scan filters (portals.filters)."""
    locations: list[str] = []
    remote_only: bool = False
    min_base: float = 0.0
    max_age_days: int = 0

    @field_validator("locations", mode="before")
    @classmethod
    def _locs(cls, v):
        # _as_str maps None->"" (str(None) would persist the literal "None"); drop blanks.
        return [s for s in (_as_str(x).strip() for x in v) if s] if isinstance(v, list) else []


class PortalsInput(BaseModel):
    """Body for PUT /api/jobs/portals — store-only scan-config edit (no LLM, so it's identical
    across modes). Only the provided keys are updated; the rest of portals.yml is preserved."""
    companies: Optional[list[CompanyInput]] = None
    queries: Optional[list[str]] = None
    filters: Optional[ScanFilters] = None

    @field_validator("queries", mode="before")
    @classmethod
    def _queries(cls, v):
        if not isinstance(v, list):
            return None
        # _as_str maps None->"" (str(None) would leak "None" into portals.yml); drop blanks.
        return [s for s in (_as_str(x).strip() for x in v) if s]


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


class ChatResponse(BaseModel):
    reply: str
    actions: list[dict] = []  # structured side-effects the UI can render
