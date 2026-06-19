"""Structured logging.

Logs go to both stdout (for `docker compose logs`) and a rotating file at
`logs/agent.log`, so a future session can inspect exactly what the agent did.
The agent harness also writes higher-level progress to STATUS.md (see status.py).
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .config import LOGS_DIR, get_settings

_CONFIGURED = False


def setup_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    level = getattr(logging, get_settings().log_level.upper(), logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream = logging.StreamHandler()
    stream.setFormatter(fmt)

    file_handler = RotatingFileHandler(
        LOGS_DIR / "agent.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(stream)
    root.addHandler(file_handler)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
