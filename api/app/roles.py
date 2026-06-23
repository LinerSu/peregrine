"""Deterministic role-family classifier for job titles (no LLM needed).

Maps a position title to a coarse role category the user can filter by — SDE,
Manager, Applied Scientist, etc. First match wins, so specific rules come before
generic ones (e.g. "Program Manager" before bare "Manager").
"""
from __future__ import annotations

_RULES: list[tuple[str, tuple[str, ...]]] = [
    # Technical / research roles.
    ("Applied Scientist", ("applied scientist", "research scientist", "researcher", "research engineer")),
    ("ML Engineer", ("machine learning", "ml engineer", " mle", "ai engineer", "deep learning")),
    ("Data Scientist", ("data scientist",)),
    ("Data Engineer", ("data engineer",)),
    ("Product Manager", ("product manager", "product management", "group product")),
    ("Program Manager", ("program manager", "tpm", "project manager")),
    # Business / GTM / operations families — before the generic "Manager" rule so a
    # "Sales Manager" lands under Sales, not Manager. Keywords avoid substrings that would
    # catch engineering titles (e.g. "operations", not bare "ops" which is inside "devops").
    ("Sales / GTM", ("account executive", "account manager", "account director", "sales",
                     "business development", "go-to-market", " gtm", "partnership",
                     "solutions engineer", "sales engineer", "solutions architect", "customer success")),
    ("Marketing", ("marketing", "brand ", "growth marketing", "demand generation",
                   "content strategist", "communications", "social media", "public relations")),
    ("Operations", ("operations", "chief of staff", "business operations", "biz ops")),
    ("Finance", ("finance", "financial", "accounting", "accountant", "controller", "fp&a", "treasury")),
    ("Legal & Compliance", ("legal", "counsel", "compliance", "regulatory", "privacy",
                            "policy", "trust & safety", "trust and safety")),
    ("People / Recruiting", ("recruiter", "recruiting", "talent acquisition", "people operations",
                             "people partner", "human resources")),
    ("Support", ("customer support", "customer experience", "technical support", "support engineer")),
    ("Security", ("security", "infosec", "appsec")),
    # Generic leadership (after the specific families above).
    ("Manager", ("manager", "director", "head of", "people lead", "engineering lead", "vp ")),
    ("SDE", ("software engineer", "sde", "swe", "developer", "backend", "frontend",
             "full stack", "full-stack", "software development", "programmer",
             "infrastructure engineer", "platform engineer")),
    ("Designer", ("designer", "ux", "ui/ux", "product design")),
    ("Analyst", ("analyst", "analytics")),
]

CATEGORIES = [label for label, _ in _RULES] + ["Other"]


def classify_role(title: str) -> str:
    # Pad with spaces so boundary keywords (" gtm", "vp ", " mle") match at the start/end of
    # the title too — e.g. "GTM Manager" -> Sales / GTM, not Manager.
    t = f" {(title or '').lower()} "
    for label, keywords in _RULES:
        if any(k in t for k in keywords):
            return label
    return "Other"
