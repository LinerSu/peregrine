"""FastAPI application entry point."""
from __future__ import annotations

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
    allow_origins=["*"],  # local-first dev; tighten for any real deployment
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
    s = get_settings()
    return {"status": "ok", "provider": s.llm_provider, "model": s.llm_model}


@app.get("/api/status")
def get_status() -> dict:
    from .config import STATUS_FILE

    text = STATUS_FILE.read_text(encoding="utf-8") if STATUS_FILE.exists() else ""
    return {"status_md": text}
