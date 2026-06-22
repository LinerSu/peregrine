"""Data access layer: CSV (metrics) + Markdown (long-form) + YAML (config).

Single source of truth = `data/jobs.csv` / `data/applications.csv` and the
per-job `data/jobs/<id>.md` files. Keep this module the only place that touches
those files so reads/writes stay consistent.
"""
from __future__ import annotations

import csv
import json
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


def next_id() -> str:
    """Next surrogate id like 2026-001, unique across BOTH jobs and applications
    (so a manually-added application can't later collide with a scanned job)."""
    from datetime import date

    year = date.today().year
    ids = [j.id for j in list_jobs()] + [a.id for a in list_applications()]
    nums = [
        int(i.split("-")[-1])
        for i in ids
        if i.startswith(f"{year}-") and i.split("-")[-1].isdigit()
    ]
    return f"{year}-{(max(nums) + 1) if nums else 1:03d}"


def next_job_id() -> str:
    """Back-compat alias; ids are shared across jobs + applications."""
    return next_id()


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


def read_upskilling(job_id: str) -> Optional[dict[str, Any]]:
    """Last saved skill-gap analysis for a job (None if never run). Stored as a
    JSON sidecar next to the per-job markdown."""
    path = config.JOBS_DIR / f"{job_id}.upskilling.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def write_upskilling(job_id: str, result: dict[str, Any]) -> str:
    config.JOBS_DIR.mkdir(parents=True, exist_ok=True)
    path = config.JOBS_DIR / f"{job_id}.upskilling.json"
    tmp = path.with_suffix(path.suffix + ".tmp")  # write+rename so a poller never reads a partial file
    tmp.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)  # atomic
    return f"data/jobs/{job_id}.upskilling.json"


def read_evaluation(job_id: str) -> Optional[dict[str, Any]]:
    """Last saved structured fit evaluation (v2) for a job, or None. JSON sidecar
    next to the per-job markdown; lets the UI render the blocks without parsing MD."""
    path = config.JOBS_DIR / f"{job_id}.evaluation.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def write_evaluation(job_id: str, result: dict[str, Any]) -> str:
    config.JOBS_DIR.mkdir(parents=True, exist_ok=True)
    path = config.JOBS_DIR / f"{job_id}.evaluation.json"
    tmp = path.with_suffix(path.suffix + ".tmp")  # write+rename so a poller never reads a partial file
    tmp.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)  # atomic
    return f"data/jobs/{job_id}.evaluation.json"


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


def get_application(app_id: str) -> Optional[Application]:
    return next((a for a in list_applications() if a.id == app_id), None)


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


def delete_application(app_id: str) -> bool:
    apps = list_applications()
    remaining = [a for a in apps if a.id != app_id]
    if len(remaining) == len(apps):
        return False
    _write_csv(config.APPLICATIONS_CSV, APPLICATION_FIELDS, [a.model_dump() for a in remaining])
    log.info("delete_application id=%s", app_id)
    return True


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


def read_targets() -> dict[str, Any]:
    """What the user is looking for (search intent), stored under profile.targets."""
    return read_profile().get("targets", {}) or {}


def write_targets(targets: dict[str, Any]) -> None:
    profile = read_profile()
    profile["targets"] = targets
    write_profile(profile)


def read_memory() -> dict[str, Any]:
    return _read_yaml(config.MEMORY_YML)


def write_memory(data: dict[str, Any]) -> None:
    _write_yaml(config.MEMORY_YML, data)


def read_portals() -> dict[str, Any]:
    return _read_yaml(config.PORTALS_YML)
