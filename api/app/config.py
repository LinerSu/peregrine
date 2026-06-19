"""Application configuration and filesystem paths.

Settings come from environment variables (see `.env.example`). Paths resolve
relative to the repo root, which is the parent of the `app/` package inside the
container (`/app`) where `data/`, `config/`, and `.agents/` are mounted.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# /app inside the container (data/ config/ .agents/ are mounted there). Override
# with APP_ROOT for local dev where the package lives at <repo>/api/app.
ROOT = Path(os.environ.get("APP_ROOT", Path(__file__).resolve().parents[1])).resolve()

DATA_DIR = ROOT / "data"
JOBS_DIR = DATA_DIR / "jobs"
CONFIG_DIR = ROOT / "config"
SKILLS_DIR = ROOT / ".agents" / "skills"
APPLICATIONS_DIR = ROOT / "applications"
LOGS_DIR = ROOT / "logs"

JOBS_CSV = DATA_DIR / "jobs.csv"
APPLICATIONS_CSV = DATA_DIR / "applications.csv"
PROFILE_YML = CONFIG_DIR / "profile.yml"
MEMORY_YML = CONFIG_DIR / "memory.yml"
PORTALS_YML = CONFIG_DIR / "portals.yml"
STATUS_FILE = ROOT / "STATUS.md"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_provider: str = "mock"
    llm_model: str = "claude-sonnet-4-5"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def ensure_dirs() -> None:
    """Create runtime directories if missing (first boot)."""
    for d in (DATA_DIR, JOBS_DIR, CONFIG_DIR, APPLICATIONS_DIR, LOGS_DIR):
        d.mkdir(parents=True, exist_ok=True)
