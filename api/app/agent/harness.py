"""Agent harness — a small intent router, not a long autonomous loop.

Job-assistant requests are small and specific: "search jobs", "here's a URL",
"judge my CV against this job", "what am I missing", "parse my CV". So we
**classify the message into one bounded action, run it once, and return** — no
multi-step tool-calling loop where the model keeps deciding what to do next.

The deep per-job actions (`evaluate_fit`, `assess_upskilling`) are themselves
short, fixed subagent runs. Anything conversational falls to a single grounded
LLM answer. Follow-ups arrive as new messages — we don't try to do everything in
one turn.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from .. import data_store as store
from .. import status
from ..logging_config import get_logger
from . import tools  # noqa: F401  (registers tools as a side effect)
from .llm import LLMClient

log = get_logger(__name__)

_URL_RE = re.compile(r"https?://\S+")

Handler = Callable[[str, list[dict[str, str]]], "tuple[str, list[dict[str, Any]]]"]


def run(message: str, history: list[dict[str, str]]) -> dict[str, Any]:
    status.record("chat", message[:120], current_task="Handling chat request")
    intent, handler = _route(message)
    reply, actions = handler(message, history)
    status.record("chat_done", intent, current_task="idle")
    return {"reply": reply, "actions": actions}


def _route(message: str) -> tuple[str, Handler]:
    """Classify the request into exactly one bounded action. Order matters."""
    m = message.lower()
    if _URL_RE.search(message):
        return "ingest", _handle_url
    if "upskill" in m or "skill gap" in m or "gap" in m or (
        "skill" in m and any(w in m for w in ("need", "missing", "learn", "improve", "lack"))
    ):
        return "upskill", _handle_upskill
    if any(k in m for k in ("evaluate", "judge", "fit for", "fit score", "how do i match", "assess")):
        return "evaluate", _handle_evaluate
    if any(k in m for k in ("find job", "search job", "matching job", "scan", "look for job")):
        return "search", _handle_search
    if len(message) > 400 or any(k in m for k in ("here is my cv", "parse my cv", "my resume", "my résumé")):
        return "cv", _handle_cv
    return "ask", _handle_ask


# --------------------------------------------------------------------------- #
# Bounded handlers — each does one thing and returns.
# --------------------------------------------------------------------------- #
def _handle_url(message: str, _history: list[dict[str, str]]) -> tuple[str, list[dict[str, Any]]]:
    url = _URL_RE.search(message).group(0).rstrip(").,")
    ingest = tools.ingest_job_url(url)
    actions = [{"tool": "ingest_job_url", "result": ingest}]
    if "error" in ingest:
        return f"Couldn't ingest that URL: {ingest['error']}", actions
    job = ingest["job"]
    ev = tools.evaluate_fit(job["id"])  # fixed 2nd step
    actions.append({"tool": "evaluate_fit", "result": ev})
    return (
        f"Ingested **{job['position']}** at {job['company']} ({job['location']}) as `{job['id']}`"
        + (" (already tracked)" if ingest.get("deduped") else "")
        + f". Fit {ev.get('fit_score')} — {ev.get('recommendation')}. Open it to review the cards.",
        actions,
    )


def _handle_search(_message: str, _history: list[dict[str, str]]) -> tuple[str, list[dict[str, Any]]]:
    scan = tools.scan_jobs()
    listing = tools.list_jobs()
    actions = [{"tool": "scan_jobs", "result": scan}, {"tool": "list_jobs", "result": listing}]
    dead_note = f", {scan['dead']} closed (gone or aged out)" if scan.get("dead") else ""
    return (
        f"Scanned: {scan['new']} new, {scan['duplicates']} duplicates, {scan['filtered']} filtered{dead_note}. "
        f"{listing['count']} jobs tracked — see the Jobs tab.",
        actions,
    )


def _handle_evaluate(message: str, _history: list[dict[str, str]]) -> tuple[str, list[dict[str, Any]]]:
    job = _find_job(message)
    if not job:
        return ("Which job? Open it in the Jobs tab and click **Evaluate fit**, or name the company.", [])
    ev = tools.evaluate_fit(job["id"])
    return (
        f"Fit for **{job['company']} — {job['position']}**: score {ev.get('fit_score')}, "
        f"recommendation {ev.get('recommendation')} "
        f"({len(ev.get('strengths', []))} strengths, {len(ev.get('weaknesses', []))} gaps). "
        "Open the job to see the cards.",
        [{"tool": "evaluate_fit", "result": ev}],
    )


def _handle_upskill(message: str, _history: list[dict[str, str]]) -> tuple[str, list[dict[str, Any]]]:
    job = _find_job(message)
    if not job:
        return ("Which job should I compare against? Name the company, or use the Upskilling tab.", [])
    res = tools.assess_upskilling(job["id"])
    gaps = res.get("missing_skills", [])
    return (
        f"For **{job['company']} — {job['position']}**: {res.get('summary', '')} "
        f"({len(gaps)} gap{'s' if len(gaps) != 1 else ''} — see the Upskilling tab).",
        [{"tool": "assess_upskilling", "result": res}],
    )


def _handle_cv(message: str, _history: list[dict[str, str]]) -> tuple[str, list[dict[str, Any]]]:
    # A long paste looks like CV text — parse it. Otherwise point at the Profile tab.
    if len(message) > 400:
        res = tools.parse_cv(message)
        return (
            "Parsed your CV into the profile." if res.get("updated") else
            "Got it, but parsing needs a real LLM (mock mode). Set a key in `.env`, or use the Profile / CV tab.",
            [{"tool": "parse_cv", "result": res}],
        )
    return ("Paste your full CV text here, or upload it in the **Profile / CV** tab.", [])


def _handle_ask(message: str, history: list[dict[str, str]]) -> tuple[str, list[dict[str, Any]]]:
    """The only open-ended path: a single grounded LLM answer (no tool loop)."""
    jobs = tools.list_jobs()["jobs"]
    profile = store.read_profile()
    system = (
        "You are a concise personal job-search assistant. Answer the user's question "
        "directly using the context below. If they want an action, tell them the one step "
        "to take (e.g. 'open the job and click Evaluate fit'). Never fabricate skills or jobs."
    )
    context = _ask_context(jobs, profile)
    messages = [{"role": "system", "content": system}, *history, {"role": "user", "content": f"{context}\n\nUser: {message}"}]
    text = LLMClient().complete(messages).text
    if _looks_like_mock(text):
        text = _ask_mock(jobs)
    return text, []


# --------------------------------------------------------------------------- #
def _find_job(message: str) -> dict[str, Any] | None:
    m = message.lower()
    for j in tools.list_jobs()["jobs"]:
        if j["id"] in message or (j["company"] and j["company"].lower() in m):
            return j
    return None


def _ask_context(jobs: list[dict[str, Any]], profile: dict[str, Any]) -> str:
    top = ", ".join(f"{j['company']} ({j['fit_score']})" for j in jobs[:5]) or "none yet"
    skills = ", ".join(s.get("name", "") for s in (profile.get("skills") or [])[:12]) or "no profile yet"
    targets = profile.get("targets") or {}
    return f"Context — tracked jobs: {len(jobs)} [{top}]. Profile skills: {skills}. Targets: {targets}."


def _ask_mock(jobs: list[dict[str, Any]]) -> str:
    return (
        f"(Mock mode — set an LLM key in `.env` for real answers.) You have {len(jobs)} tracked job(s). "
        "I can: scan/search jobs, ingest a pasted URL, evaluate fit, or show skill gaps — just ask, "
        "or use the tabs."
    )


def _looks_like_mock(text: str) -> bool:
    return "mock** LLM mode" in text or "Using mock reply" in text
