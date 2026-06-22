"""Application configuration and filesystem paths.

Settings come from environment variables (see `.env.example`). Paths resolve
relative to the repo root, which is the parent of the `app/` package inside the
container (`/app`) where `data/`, `config/`, and `.agents/` are mounted.
"""
from __future__ import annotations

import os
import shutil
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# /app inside the container (data/ config/ .agents/ are mounted there). Override
# with APP_ROOT for local dev where the package lives at <repo>/api/app.
ROOT = Path(os.environ.get("APP_ROOT", Path(__file__).resolve().parents[1])).resolve()

# Demo/test persona switch. PEREGRINE_DATASET=<persona> runs the app against an
# isolated, gitignored runtime dataset under .demo/<persona>/ (seeded on boot
# from app/demo_seed.py), leaving the real (gitignored) data/ + config/ untouched.
# Unset = normal mode. See README "Demo / test datasets".
DATASET = os.environ.get("PEREGRINE_DATASET", "").strip().lower()
if DATASET:
    _root = ROOT / ".demo" / DATASET
    DATA_DIR = _root / "data"
    CONFIG_DIR = _root / "config"
else:
    DATA_DIR = ROOT / "data"
    CONFIG_DIR = ROOT / "config"

JOBS_DIR = DATA_DIR / "jobs"
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
    llm_model: str = "claude-sonnet-4-6"
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
    """Create runtime directories and seed data on first boot.

    In demo mode (PEREGRINE_DATASET set) the dataset is generated from the chosen
    persona; otherwise the live CSVs are seeded from the committed examples.
    """
    for d in (DATA_DIR, JOBS_DIR, CONFIG_DIR, APPLICATIONS_DIR, LOGS_DIR):
        d.mkdir(parents=True, exist_ok=True)

    if DATASET:
        from . import demo_seed

        if DATASET not in demo_seed.PERSONAS:
            raise SystemExit(
                f"PEREGRINE_DATASET='{DATASET}' is not a known persona. "
                f"Choose one of: {', '.join(demo_seed.list_personas())}"
            )
        # Consider the dataset seeded only when its key artifacts both exist;
        # otherwise (re)seed, so a partial/cleared dir self-heals on boot.
        if not (JOBS_CSV.exists() and PROFILE_YML.exists()):
            demo_seed.seed(DATASET)
        return

    # Normal mode: the live CSVs are gitignored (personal data). On a fresh clone
    # copy the committed examples so the app isn't empty — never the reverse.
    for live, example in (
        (JOBS_CSV, DATA_DIR / "jobs.example.csv"),
        (APPLICATIONS_CSV, DATA_DIR / "applications.example.csv"),
    ):
        if not live.exists() and example.exists():
            shutil.copy(example, live)
