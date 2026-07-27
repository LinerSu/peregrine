"""Application configuration and filesystem paths.

Settings come from environment variables (see `.env.example`). Paths resolve
relative to the repo root, which is the parent of the `app/` package inside the
container (`/app`) where `data/`, `config/`, and `.agents/` are mounted.
"""
from __future__ import annotations

import os
import re
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
def _valid_dataset_name(name: str) -> bool:
    """A dataset name builds a path (.demo/<name>/), so it must be a safe slug — no
    separators, `..`, or absolute paths that could traverse out of .demo/."""
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9_-]*", name))


DATASET = os.environ.get("PEREGRINE_DATASET", "").strip().lower()
if DATASET and not _valid_dataset_name(DATASET):
    raise SystemExit(
        f"PEREGRINE_DATASET='{DATASET}' is not a valid dataset name: start with a letter or "
        f"digit, then a-z / 0-9 / - / _ (no slashes or dots)."
    )
if DATASET:
    _root = ROOT / ".demo" / DATASET
    DATA_DIR = _root / "data"
    CONFIG_DIR = _root / "config"
    # Isolate generated application materials too, so demo runs never write into
    # the real applications/ dir.
    APPLICATIONS_DIR = _root / "applications"
    RESUME_DIR = _root / "resume"
else:
    DATA_DIR = ROOT / "data"
    CONFIG_DIR = ROOT / "config"
    APPLICATIONS_DIR = ROOT / "applications"
    RESUME_DIR = ROOT / "resume"  # your master résumé(s) live here (CV intake reads them)

JOBS_DIR = DATA_DIR / "jobs"
SKILLS_DIR = ROOT / ".agents" / "skills"
# Anchored beside DATA_DIR so demo datasets get their OWN logs + status page —
# otherwise demo activity overwrites the live user's runtime log/status.
LOGS_DIR = DATA_DIR.parent / "logs"

JOBS_CSV = DATA_DIR / "jobs.csv"
APPLICATIONS_CSV = DATA_DIR / "applications.csv"
PATTERNS_FILE = DATA_DIR / "patterns.json"  # saved pattern-insights narrative (singleton)
PROFILE_YML = CONFIG_DIR / "profile.yml"
CV_SOURCE = CONFIG_DIR / "cv_source.md"  # raw CV text the user submits (Internal mode reads it)
JOB_SOURCE = CONFIG_DIR / "job_source.md"  # raw job posting the user pastes/uploads (Internal mode reads it)
MEMORY_YML = CONFIG_DIR / "memory.yml"
PORTALS_YML = CONFIG_DIR / "portals.yml"
# Under logs/ (a DIRECTORY bind mount), not the repo root: a root-level STATUS.md
# was git-tracked — the runtime writer put the user's real activity (chat excerpts,
# job events) into a committable file no guard covered — and a single-file bind
# mount is fragile besides (git/editor renames detach the inode; a missing host
# file makes Docker create a root-owned directory in its place).
STATUS_FILE = LOGS_DIR / "STATUS.md"


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
    for d in (DATA_DIR, JOBS_DIR, CONFIG_DIR, APPLICATIONS_DIR, RESUME_DIR, LOGS_DIR):
        d.mkdir(parents=True, exist_ok=True)

    if DATASET:
        from . import demo_seed

        # A marker written only after a dataset is populated is the source of truth for
        # "already seeded" — so a partial or cleared dir (no marker) self-heals by
        # re-seeding on the next boot. Reset a dataset by deleting .demo/<name>/.
        marker = DATA_DIR.parent / ".seeded"
        if DATASET not in demo_seed.PERSONAS:
            # Not a committed code persona: only valid as a PRIVATE local dataset you
            # placed under .demo/<name>/ yourself (marker present) — never committed to
            # git. This is how a personal test profile stays isolated from the repo.
            if not marker.exists():
                raise SystemExit(
                    f"PEREGRINE_DATASET='{DATASET}' is not a known persona and has no local "
                    f"data under .demo/{DATASET}/. Known personas: {', '.join(demo_seed.list_personas())}"
                )
            return  # private local dataset already present -> use it as-is
        if not marker.exists():
            demo_seed.seed(DATASET)
            marker.write_text(f"{DATASET}\n", encoding="utf-8")
        return

    # Normal mode: the live CSVs are gitignored (personal data). On a fresh clone copy
    # the committed examples so the files exist with the right schema — never the
    # reverse. The example CSVs are HEADER-ONLY on purpose: a seeded sample job would
    # (a) carry a pre-baked fit score with no profile to explain it and (b) satisfy
    # jobs.length > 0, which suppresses the web's auto-opened "Get started" onboarding
    # (App.tsx) — the guided flow, not a mystery sample row, greets a new user.
    for live, example in (
        (JOBS_CSV, DATA_DIR / "jobs.example.csv"),
        (APPLICATIONS_CSV, DATA_DIR / "applications.example.csv"),
        (PORTALS_YML, CONFIG_DIR / "portals.example.yml"),  # so Scan has sources out of the box
    ):
        if not live.exists() and example.exists():
            shutil.copy(example, live)
