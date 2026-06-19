"""Agent harness — the orchestration loop.

Assembles a system prompt from the `.agents/skills/` modules, calls the LLM with
the registered tool specs, dispatches any tool calls, and loops until the model
returns a final answer (or a max-iteration guard trips). When running against the
`mock` provider (no API key), a lightweight keyword intent-router still drives the
core flows so the app is usable out of the box.
"""
from __future__ import annotations

import re
from typing import Any

from .. import status
from ..config import SKILLS_DIR
from ..logging_config import get_logger
from . import tools  # noqa: F401  (registers tools as a side effect)
from .llm import LLMClient
from .registry import registry

log = get_logger(__name__)

MAX_ITERS = 6


def _system_prompt() -> str:
    parts = [
        "You are the user's personal job-search assistant. You help them intake a "
        "CV, scan job portals, evaluate fit, prepare materials, and decide where to "
        "apply. You never auto-submit an application; the user always clicks Apply "
        "after reviewing strengths, weaknesses, and required materials. Never "
        "fabricate skills or experience. Use tools to take actions.",
        "\nAvailable skills:",
    ]
    for d in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        parts.append(f"\n--- {d.parent.name} ---\n{d.read_text(encoding='utf-8')}")
    return "\n".join(parts)


def run(message: str, history: list[dict[str, str]]) -> dict[str, Any]:
    status.record("chat", message[:120], current_task="Handling chat request")
    llm = LLMClient()
    messages: list[dict[str, str]] = [{"role": "system", "content": _system_prompt()}]
    messages += history
    messages.append({"role": "user", "content": message})

    actions: list[dict[str, Any]] = []
    specs = registry.specs()

    for _ in range(MAX_ITERS):
        result = llm.complete(messages, tools=specs)
        if not result.tool_calls:
            reply = result.text
            if _looks_like_mock(reply):
                reply, extra = _intent_fallback(message)
                actions += extra
            status.record("chat_done", current_task="idle")
            return {"reply": reply, "actions": actions}

        # Dispatch tool calls and feed results back to the model.
        for call in result.tool_calls:
            tool = registry.get(call.name)
            if not tool:
                continue
            try:
                output = tool.fn(**call.arguments)
            except Exception as exc:  # surface but don't crash the loop
                log.exception("tool %s failed", call.name)
                output = {"error": str(exc)}
            actions.append({"tool": call.name, "args": call.arguments, "result": output})
            messages.append({"role": "assistant", "content": f"[called {call.name}]"})
            messages.append({"role": "user", "content": f"Tool {call.name} result: {output}"})

    status.record("chat_done", "max-iters", current_task="idle")
    return {"reply": "Reached the action limit for this request.", "actions": actions}


def _looks_like_mock(text: str) -> bool:
    return "mock** LLM mode" in text or "Using mock reply" in text


def _intent_fallback(message: str) -> tuple[str, list[dict[str, Any]]]:
    """Keyword router so core flows work without a real LLM."""
    m = message.lower()
    actions: list[dict[str, Any]] = []

    # A pasted job URL -> ingest it, then evaluate fit.
    url_match = re.search(r"https?://\S+", message)
    if url_match:
        url = url_match.group(0).rstrip(").,")
        ingest = tools.ingest_job_url(url)
        actions.append({"tool": "ingest_job_url", "result": ingest})
        if "error" in ingest:
            return (
                f"Couldn't ingest that URL: {ingest['error']} "
                "Supported right now: amazon.jobs and Greenhouse boards.",
                actions,
            )
        job = ingest["job"]
        ev = tools.evaluate_fit(job["id"])
        actions.append({"tool": "evaluate_fit", "result": ev})
        return (
            f"Ingested **{job['position']}** at {job['company']} "
            f"({job['location']}) as `{job['id']}`"
            + (" (already tracked)" if ingest.get("deduped") else "")
            + f". Fit score {ev.get('fit_score')} — recommendation: "
            f"{ev.get('recommendation')}. Open it in the dashboard to review "
            "strengths, weaknesses, and materials before applying.",
            actions,
        )

    if any(k in m for k in ("find job", "search job", "matching job", "scan")):
        scan = tools.scan_jobs()
        listing = tools.list_jobs()
        actions += [
            {"tool": "scan_jobs", "result": scan},
            {"tool": "list_jobs", "result": listing},
        ]
        return (
            f"Scanned portals: {scan['new']} new, {scan['duplicates']} duplicates, "
            f"{scan['filtered']} filtered. {listing['count']} jobs now tracked — "
            "see the dashboard. (Mock mode: configure an LLM provider for richer replies.)",
            actions,
        )

    if any(k in m for k in ("cv", "resume", "profile")):
        return (
            "Paste your CV text and I'll parse it into your profile. "
            "(Mock mode: set an LLM provider in `.env` for full parsing.)",
            actions,
        )

    listing = tools.list_jobs(query=message.strip())
    actions.append({"tool": "list_jobs", "result": listing})
    return (
        f"Found {listing['count']} matching tracked jobs. Try: \"find jobs matching my CV\".",
        actions,
    )
