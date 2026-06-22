"""Posting-level signals for the structured evaluation (v2).

Pure, deterministic functions over a job + its description text — no LLM, no
network, no implicit clock. They produce the "legitimacy" (ghost-job risk) and
"archetype" blocks of the evaluation, so those render identically in External
and Internal modes and are trivial to unit-test. The LLM only supplies the
subjective fit (strengths/weaknesses/materials); these are computed server-side.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from .schemas import Job

# Ghost-job / low-legitimacy language. Each (label, pattern) that matches the
# title+description adds one flag and lowers the legitimacy score.
_GHOST_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "Evergreen / talent-pool posting",
        re.compile(
            r"\b(always (?:looking|hiring|accepting)|talent (?:pool|community|network)|"
            r"pipeline|future (?:opening|opportunit)|general application|expression of interest)\b",
            re.I,
        ),
    ),
    (
        "Third-party / agency posting",
        re.compile(
            r"\b(staffing|recruit(?:ing|ment) (?:agency|firm|partner)|"
            r"on behalf of (?:our|a) client|our client (?:is|seeks))\b",
            re.I,
        ),
    ),
    (
        "Vague / boilerplate role",
        re.compile(r"\b(rockstar|ninja|wear many hats|fast[- ]paced environment|self[- ]starter)\b", re.I),
    ),
]

_STALE_DAYS = 60
_SPARSE_CHARS = 200

# Archetype rules, checked in order — first match wins. Captures the *nature* of
# the work, a different axis from role_category (the field/function).
_ARCHETYPE_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("Leadership / Manager", re.compile(
        r"\b(manager|head of|director|\bvp\b|team lead|tech lead|\blead\b|principal|"
        r"staff (?:engineer|scientist)|managing)\b", re.I)),
    ("Research", re.compile(
        r"\b(research(?:er)?|scientist|\bphd\b|publications?|novel (?:method|algorithm)|"
        r"state[- ]of[- ]the[- ]art)\b", re.I)),
    ("Platform / Infrastructure", re.compile(
        r"\b(platform|infrastructure|\binfra\b|devops|\bsre\b|reliability|"
        r"internal tool|tooling)\b", re.I)),
    ("Founding / Generalist", re.compile(
        r"\b(founding|generalist|wear many hats|early[- ]stage|0[ -]to[ -]1)\b", re.I)),
    ("Builder / IC", re.compile(
        r"\b(engineer|developer|designer|analyst|chemist|biologist|associate|clerk|intern)\b", re.I)),
]


def assess_legitimacy(job: Job, description: str, today: date | None = None) -> dict[str, Any]:
    """Ghost-job risk: a legitimacy score in [0,1] (higher = more legit) plus the
    flags behind it. `today` is optional and explicit so the function stays pure;
    pass it to enable the staleness check.
    """
    haystack = f"{job.position}\n{description}"
    flags: list[str] = []

    if job.salary_min is None and job.salary_max is None:
        flags.append("No salary range disclosed")
    if len(description.strip()) < _SPARSE_CHARS:
        flags.append("Sparse description")
    for label, pattern in _GHOST_PATTERNS:
        if pattern.search(haystack):
            flags.append(label)
    if today is not None and job.posted_date:
        try:
            age = (today - date.fromisoformat(job.posted_date)).days
            if age > _STALE_DAYS:
                flags.append(f"Stale posting ({age}d old)")
        except ValueError:
            pass

    # Preserve order, drop dupes.
    seen: set[str] = set()
    flags = [f for f in flags if not (f in seen or seen.add(f))]
    score = round(max(0.0, 1.0 - 0.2 * len(flags)), 2)
    return {"legitimacy_score": score, "legitimacy_flags": flags}


def classify_archetype(position: str, description: str = "") -> str:
    """The role's working style (Leadership / Research / Platform / Founding /
    Builder / Specialist). The title is the strongest, least-noisy signal, so it
    wins; the description is only a fallback for titles with no archetype keyword
    (otherwise stray words like "partner with research" would mislabel an
    engineering role as Research)."""
    for label, pattern in _ARCHETYPE_RULES:
        if pattern.search(position):
            return label
    for label, pattern in _ARCHETYPE_RULES:
        if pattern.search(description):
            return label
    return "Specialist"
