"""FastAPI application entry point."""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import status
from .config import ensure_dirs, get_settings
from .logging_config import get_logger, setup_logging
from .routers import applications, chat, docs, jobs, stats

setup_logging()
ensure_dirs()
log = get_logger(__name__)

app = FastAPI(title="Peregrine API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    # Pinned to the local web UI, not "*": the API now has destructive endpoints
    # (DELETE /jobs/{id}, POST /jobs/purge), and a wildcard would let any web page
    # you visit fire drive-by requests at them. Override via PEREGRINE_WEB_ORIGINS
    # (comma-separated) if you serve the UI elsewhere.
    allow_origins=[
        o.strip()
        for o in os.environ.get(
            "PEREGRINE_WEB_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")
        if o.strip()
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    from .config import DATASET

    s = get_settings()
    # `dataset` drives the web's demo-data badge: without it the UI is pixel-identical
    # in live and demo modes, and users forget which identity they're looking at.
    return {"status": "ok", "provider": s.llm_provider, "model": s.llm_model,
            "dataset": DATASET or None}


@app.get("/api/status")
def get_status() -> dict:
    from .config import STATUS_FILE

    text = STATUS_FILE.read_text(encoding="utf-8") if STATUS_FILE.exists() else ""
    return {"status_md": text}
