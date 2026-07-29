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

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(stream)

    # File logging is a convenience, never a reason to fail to boot. The log directory is
    # a bind mount, so it can be read-only, owned by another uid, or blocked by SELinux —
    # none of which should turn "I can't write agent.log" into "the API won't start".
    try:
        file_handler = RotatingFileHandler(
            LOGS_DIR / "agent.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8"
        )
    except OSError as exc:
        root.warning("file logging disabled (%s: %s) — logging to stdout only",
                     type(exc).__name__, exc)
    else:
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
