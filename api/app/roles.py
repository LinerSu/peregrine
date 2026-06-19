"""Deterministic role-family classifier for job titles (no LLM needed).

Maps a position title to a coarse role category the user can filter by — SDE,
Manager, Applied Scientist, etc. First match wins, so specific rules come before
generic ones (e.g. "Program Manager" before bare "Manager").
"""
from __future__ import annotations

_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("Applied Scientist", ("applied scientist", "research scientist", "researcher", "research engineer")),
    ("ML Engineer", ("machine learning", "ml engineer", " mle", "ai engineer", "deep learning")),
    ("Data Scientist", ("data scientist",)),
    ("Data Engineer", ("data engineer",)),
    ("Product Manager", ("product manager", "product management", "group product")),
    ("Program Manager", ("program manager", "tpm", "project manager")),
    ("Manager", ("manager", "director", "head of", "people lead", "engineering lead", "vp ")),
    ("SDE", ("software engineer", "sde", "swe", "developer", "backend", "frontend",
             "full stack", "full-stack", "software development", "programmer",
             "infrastructure engineer", "platform engineer")),
    ("Designer", ("designer", "ux", "ui/ux", "product design")),
    ("Analyst", ("analyst", "analytics")),
]

CATEGORIES = [label for label, _ in _RULES] + ["Other"]


def classify_role(title: str) -> str:
    t = (title or "").lower()
    for label, keywords in _RULES:
        if any(k in t for k in keywords):
            return label
    return "Other"
