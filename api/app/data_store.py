"""Data access layer: CSV (metrics) + Markdown (long-form) + YAML (config).

Single source of truth = `data/jobs.csv` / `data/applications.csv` and the
per-job `data/jobs/<id>.md` files. Keep this module the only place that touches
those files so reads/writes stay consistent.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Optional

import yaml

from . import config
from .logging_config import get_logger
from .schemas import Application, Job

log = get_logger(__name__)

JOB_FIELDS = list(Job.model_fields.keys())
APPLICATION_FIELDS = list(Application.model_fields.keys())


# --------------------------------------------------------------------------- #
# CSV helpers
# --------------------------------------------------------------------------- #
def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fields})
    tmp.replace(path)  # atomic


def _coerce_job(row: dict[str, str]) -> Job:
    data = dict(row)
    for k in ("salary_min", "salary_max", "fit_score"):
        v = data.get(k)
        data[k] = float(v) if v not in (None, "") else None
    return Job(**data)


# --------------------------------------------------------------------------- #
# Jobs
# --------------------------------------------------------------------------- #
def list_jobs() -> list[Job]:
    return [_coerce_job(r) for r in _read_csv(config.JOBS_CSV)]


def get_job(job_id: str) -> Optional[Job]:
    return next((j for j in list_jobs() if j.id == job_id), None)


def find_job_by_key(company: str, company_job_id: str) -> Optional[Job]:
    """Dedup key = company + company_job_id."""
    company, company_job_id = company.strip().lower(), company_job_id.strip().lower()
    for j in list_jobs():
        if j.company.strip().lower() == company and j.company_job_id.strip().lower() == company_job_id:
            return j
    return None


def upsert_job(job: Job) -> Job:
    jobs = list_jobs()
    for i, j in enumerate(jobs):
        if j.id == job.id:
            jobs[i] = job
            break
    else:
        jobs.append(job)
    _write_csv(config.JOBS_CSV, JOB_FIELDS, [j.model_dump() for j in jobs])
    log.info("upsert_job id=%s company=%s", job.id, job.company)
    return job


def next_job_id() -> str:
    """Sequential surrogate id like 2026-001 used for filenames/links."""
    from datetime import date

    year = date.today().year
    nums = [
        int(j.id.split("-")[-1])
        for j in list_jobs()
        if j.id.startswith(f"{year}-") and j.id.split("-")[-1].isdigit()
    ]
    return f"{year}-{(max(nums) + 1) if nums else 1:03d}"


# --------------------------------------------------------------------------- #
# Job detail markdown
# --------------------------------------------------------------------------- #
def read_job_md(job_id: str) -> str:
    path = config.JOBS_DIR / f"{job_id}.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def write_job_md(job_id: str, content: str) -> str:
    config.JOBS_DIR.mkdir(parents=True, exist_ok=True)
    path = config.JOBS_DIR / f"{job_id}.md"
    path.write_text(content, encoding="utf-8")
    return f"data/jobs/{job_id}.md"


# --------------------------------------------------------------------------- #
# Applications
# --------------------------------------------------------------------------- #
def list_applications() -> list[Application]:
    out: list[Application] = []
    for r in _read_csv(config.APPLICATIONS_CSV):
        data = dict(r)
        for k in ("salary_min", "salary_max", "fit_score"):
            v = data.get(k)
            data[k] = float(v) if v not in (None, "") else None
        out.append(Application(**data))
    return out


def upsert_application(app: Application) -> Application:
    apps = list_applications()
    for i, a in enumerate(apps):
        if a.id == app.id:
            apps[i] = app
            break
    else:
        apps.append(app)
    _write_csv(config.APPLICATIONS_CSV, APPLICATION_FIELDS, [a.model_dump() for a in apps])
    log.info("upsert_application id=%s", app.id)
    return app


# --------------------------------------------------------------------------- #
# YAML config / memory
# --------------------------------------------------------------------------- #
def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def read_profile() -> dict[str, Any]:
    return _read_yaml(config.PROFILE_YML)


def write_profile(data: dict[str, Any]) -> None:
    _write_yaml(config.PROFILE_YML, data)


def read_memory() -> dict[str, Any]:
    return _read_yaml(config.MEMORY_YML)


def write_memory(data: dict[str, Any]) -> None:
    _write_yaml(config.MEMORY_YML, data)


def read_portals() -> dict[str, Any]:
    return _read_yaml(config.PORTALS_YML)
