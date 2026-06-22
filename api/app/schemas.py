"""Pydantic models shared across the API and agent."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

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


class ProfileInput(BaseModel):
    """Body for PUT /api/profile — store-only profile merge (Internal mode: Claude
    parses the CV, then PUTs the extracted fields). Only CV-derived keys are
    accepted, so it can't clobber targets / comp / work_auth / preferences."""
    name: Optional[str] = None
    headline: Optional[str] = None
    location: Optional[str] = None
    skills: Optional[list[dict]] = None


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


class ChatResponse(BaseModel):
    reply: str
    actions: list[dict] = []  # structured side-effects the UI can render
