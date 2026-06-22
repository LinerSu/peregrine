"""Subagents — each runs with an isolated context and a single skill prompt.

This mirrors the pattern from the reference repos: separate generation from
judgment. The `searcher` discovers, the `evaluator` scores fit, and the
`reviewer` critiques the evaluation in a fresh context before it reaches the user.
"""
from __future__ import annotations

import json
from typing import Any

from ..config import SKILLS_DIR
from ..logging_config import get_logger
from .llm import LLMClient

log = get_logger(__name__)


def load_skill(name: str) -> str:
    path = SKILLS_DIR / name / "SKILL.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _json_from_text(text: str) -> dict[str, Any]:
    """Best-effort extract a JSON object from an LLM reply."""
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    return {}


def evaluator(job_md: str, profile: dict[str, Any]) -> dict[str, Any]:
    """Score fit and produce strengths / weaknesses / materials."""
    llm = LLMClient()
    messages = [
        {"role": "system", "content": load_skill("fit-eval")},
        {
            "role": "user",
            "content": (
                "Profile (YAML):\n```\n"
                + json.dumps(profile, ensure_ascii=False, indent=2)
                + "\n```\n\nJob posting:\n```\n"
                + job_md
                + "\n```\n\nGround every claim in the profile — do NOT invent skills or "
                "experience. Each strength must reference specific evidence from the profile. "
                "Any required qualification with no supporting evidence belongs in weaknesses "
                "(a gap), never in strengths.\n\n"
                "Return ONLY a JSON object with keys: fit_score (0..1), strengths (string[]), "
                "weaknesses (string[]), materials (string[]), "
                "recommendation ('apply'|'hold'|'skip')."
            ),
        },
    ]
    result = _json_from_text(llm.complete(messages).text)
    if "fit_score" not in result:
        # No valid evaluation (e.g. mock mode echoes the prompt). Deterministic
        # fallback so the UI always has something to gate on.
        result = {
            "fit_score": 0.5,
            "strengths": ["(mock) profile overlaps with core responsibilities"],
            "weaknesses": ["(mock) configure an LLM provider for a real evaluation"],
            "materials": ["Tailored resume", "Cover letter"],
            "recommendation": "hold",
        }
    return result


def upskiller(job_md: str, profile: dict[str, Any]) -> dict[str, Any]:
    """Compare a job's requirements against the profile and surface skill gaps."""
    llm = LLMClient()
    messages = [
        {"role": "system", "content": load_skill("upskill")},
        {
            "role": "user",
            "content": (
                "Profile (JSON):\n```\n"
                + json.dumps(profile, ensure_ascii=False, indent=2)
                + "\n```\n\nJob posting:\n```\n"
                + job_md
                + "\n```\n\nReturn ONLY a JSON object with keys: summary (string), "
                "missing_skills (array of {skill, why, how_to_close})."
            ),
        },
    ]
    result = _json_from_text(llm.complete(messages).text)
    if "missing_skills" not in result:
        result = {
            "summary": "(mock) Configure an LLM provider for a real upskilling analysis.",
            "missing_skills": [
                {
                    "skill": "(mock) example gap",
                    "why": "appears in the job's requirements but not yet in your profile",
                    "how_to_close": "take a focused course or ship a small project that uses it",
                }
            ],
        }
    return result


_MOCK_MARKER = "Running in **mock** LLM mode"


def cover_letter_writer(
    job: Any, job_md: str, profile: dict[str, Any], evaluation: dict[str, Any] | None, style_refs: str
) -> str:
    """Draft a tailored cover letter. Returns the letter text (markdown)."""
    llm = LLMClient()
    parts = [
        "Candidate profile (JSON):\n```\n" + json.dumps(profile, ensure_ascii=False, indent=2) + "\n```",
        "Job posting:\n```\n" + job_md + "\n```",
    ]
    if evaluation:
        parts.append(
            "Fit evaluation (JSON):\n```\n" + json.dumps(evaluation, ensure_ascii=False, indent=2) + "\n```"
        )
    if style_refs:
        parts.append(style_refs)
    parts.append("Write the cover letter now. Return ONLY the letter text.")

    messages = [
        {"role": "system", "content": load_skill("cover-letter")},
        {"role": "user", "content": "\n\n".join(parts)},
    ]
    text = llm.complete(messages).text.strip()
    if not text or _MOCK_MARKER in text:
        # Mock / no-key / provider-error fallback so the UI always gets a draft.
        return _mock_cover_letter(job, profile)
    return text


def _mock_cover_letter(job: Any, profile: dict[str, Any]) -> str:
    name = profile.get("name") or "Your Name"
    return (
        f"Dear {job.company} Hiring Team,\n\n"
        f"I am writing to apply for the {job.position} role at {job.company}. "
        "_(Mock draft — set an LLM provider in `.env`, or use Internal mode, for a "
        "tailored letter grounded in your profile and this posting.)_\n\n"
        "My background aligns with the core responsibilities in your posting, and I "
        "would welcome the chance to discuss how I can contribute.\n\n"
        f"Sincerely,\n{name}\n"
    )


def reviewer(evaluation: dict[str, Any], job_md: str) -> dict[str, Any]:
    """Critique the evaluation in a fresh context and return a revised version."""
    llm = LLMClient()
    messages = [
        {
            "role": "system",
            "content": (
                "You are a critical reviewer. Check the evaluation for fabricated "
                "strengths, missed restrictions, and weak framing. Return ONLY the "
                "corrected JSON object with the same keys."
            ),
        },
        {
            "role": "user",
            "content": "Evaluation:\n```\n"
            + json.dumps(evaluation, ensure_ascii=False, indent=2)
            + "\n```\n\nJob:\n```\n"
            + job_md
            + "\n```",
        },
    ]
    revised = _json_from_text(llm.complete(messages).text)
    return revised if "fit_score" in revised else evaluation
