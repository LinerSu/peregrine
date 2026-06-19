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


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


class ChatResponse(BaseModel):
    reply: str
    actions: list[dict] = []  # structured side-effects the UI can render
