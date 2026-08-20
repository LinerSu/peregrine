"""FastAPI application entry point."""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import status
from .agent.llm import LLMUnusable
from .config import ensure_dirs, get_settings
from .logging_config import get_logger, setup_logging
from .routers import applications, chat, docs, jobs, stats

setup_logging()
ensure_dirs()
log = get_logger(__name__)

app = FastAPI(title="Peregrine API", version="0.1.0")

WEB_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "PEREGRINE_WEB_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if o.strip()
]

# Methods that change something. GET/HEAD/OPTIONS are readable cross-origin only with
# CORS approval, so the browser already protects those; these are the ones that ACT.
_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def block_cross_origin_writes(request, call_next):
    """Reject state-changing requests that a page on another origin fired at us.

    CORS is not this control. A cross-origin POST with a simple content type is sent by
    the browser BEFORE any CORS check — the check only decides whether the attacker may
    READ the response. So any page you have open can silently trigger our mutating
    endpoints, several of which spend API tokens (evaluate, backfill, ingest) or delete
    data. Since the API binds to loopback, "some page in your browser" is the whole
    threat model, and it is exactly what the Origin header identifies.

    Requests with NO Origin (curl, the Internal-mode skill, server-side callers) pass:
    a browser always sets it on cross-origin writes, so absence means not-a-browser.
    """
    origin = request.headers.get("origin")
    if request.method in _MUTATING and origin and origin not in WEB_ORIGINS:
        log.warning("blocked cross-origin %s %s from %r", request.method, request.url.path, origin)
        return JSONResponse(
            status_code=403,
            content={"detail": "cross-origin write blocked — set PEREGRINE_WEB_ORIGINS "
                               "if you serve the UI from another origin"},
        )
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    # Pinned to the local web UI, not "*": the API now has destructive endpoints
    # (DELETE /jobs/{id}, POST /jobs/purge), and a wildcard would let any web page
    # you visit fire drive-by requests at them. Override via PEREGRINE_WEB_ORIGINS
    # (comma-separated) if you serve the UI elsewhere.
    allow_origins=WEB_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(LLMUnusable)
def llm_unusable(_request, exc: LLMUnusable) -> JSONResponse:
    """A provider that failed, truncated, or said nothing is reported — never papered
    over with a placeholder that reads as real analysis.

    502 rather than 500: the upstream model is what went wrong, not this request. The
    web surfaces `detail` verbatim, so the user is told what happened and what to do
    instead of being handed a document stamped "Mock CV" with a valid key configured."""
    log.warning("unusable LLM output: %s", exc)
    return JSONResponse(status_code=502, content={"detail": str(exc)})


app.include_router(chat.router)
app.include_router(jobs.router)
app.include_router(applications.router)
app.include_router(stats.router)
app.include_router(docs.router)


@app.on_event("startup")
def _startup() -> None:
    s = get_settings()
    log.info("starting Peregrine API | provider=%s model=%s", s.llm_provider, s.llm_model)
    status.record("boot", f"provider={s.llm_provider}", current_task="idle")


@app.get("/api/health")
def health() -> dict:
    from .config import DATASET, repo_relative_dirs

    s = get_settings()
    # `dataset` drives the web's demo-data badge: without it the UI is pixel-identical
    # in live and demo modes, and users forget which identity they're looking at.
    # `paths` is the authority a local CLI joins against instead of assuming `data/`:
    # under a demo dataset those are still the user's REAL files (see
    # config.repo_relative_dirs). Repo-relative, so it means the same on host and in
    # the container.
    return {"status": "ok", "provider": s.llm_provider, "model": s.llm_model,
            "dataset": DATASET or None, "paths": repo_relative_dirs()}


@app.get("/api/status")
def get_status() -> dict:
    from .config import STATUS_FILE

    text = STATUS_FILE.read_text(encoding="utf-8") if STATUS_FILE.exists() else ""
    return {"status_md": text}
