"""Data access layer: CSV (metrics) + Markdown (long-form) + YAML (config).

Single source of truth = `data/jobs.csv` / `data/applications.csv` and the
per-job `data/jobs/<id>.md` files. Keep this module the only place that touches
those files so reads/writes stay consistent.
"""
from __future__ import annotations

import csv
import json
import shutil
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


def match_job(
    jobs: list[Job], company: str, position: str, company_job_id: str = "", location: str = ""
) -> Optional[Job]:
    """Find the tracked job an application corresponds to, against a preloaded list:
    exact company+company_job_id first, else company+position (case-insensitive, with
    location as a tiebreaker when several share the title). Returns None if untracked."""
    c = (company or "").strip().lower()
    cj = (company_job_id or "").strip().lower()
    # Only a real, non-manual key counts (a whitespace/"manual-" key must fall through
    # to the company+position match, not key-match a job with an empty id).
    if cj and not cj.startswith("manual-"):
        for j in jobs:
            if j.company.strip().lower() == c and j.company_job_id.strip().lower() == cj:
                return j
    p = (position or "").strip().lower()
    matches = [j for j in jobs if j.company.strip().lower() == c and j.position.strip().lower() == p]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1 and (location or "").strip():
        loc = location.strip().lower()
        loc_matches = [j for j in matches if j.location.strip().lower() == loc]
        if len(loc_matches) == 1:
            return loc_matches[0]
    return None  # no match, or ambiguous — don't guess by CSV row order


def find_job_for_posting(company: str, position: str, company_job_id: str = "", location: str = "") -> Optional[Job]:
    """match_job against all tracked jobs (one read)."""
    return match_job(list_jobs(), company, position, company_job_id, location)


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


def write_jobs(jobs: list[Job]) -> None:
    """Persist the whole jobs list in one write. For batch callers (e.g. a scan) that
    mutate many rows and want to avoid the per-row read+rewrite of upsert_job."""
    _write_csv(config.JOBS_CSV, JOB_FIELDS, [j.model_dump() for j in jobs])


def _max_id_num(year: int) -> int:
    """Highest NNN across BOTH jobs and applications for the given year (0 if none)."""
    ids = [j.id for j in list_jobs()] + [a.id for a in list_applications()]
    nums = [
        int(i.split("-")[-1])
        for i in ids
        if i.startswith(f"{year}-") and i.split("-")[-1].isdigit()
    ]
    return max(nums) if nums else 0


def id_minter() -> "Iterator[str]":
    """Yield successive unique ids (year-NNN), seeded once from the current jobs+applications.
    Lets a batch (scan) mint many ids without re-reading the CSV per id. Ids stay unique
    across both stores (a manually-added application can't later collide with a scanned job)."""
    from datetime import date

    year = date.today().year
    n = _max_id_num(year)
    while True:
        n += 1
        yield f"{year}-{n:03d}"


def next_id() -> str:
    """Next surrogate id like 2026-001, unique across BOTH jobs and applications
    (so a manually-added application can't later collide with a scanned job)."""
    from datetime import date

    return f"{date.today().year}-{_max_id_num(date.today().year) + 1:03d}"


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


def _mirror_to_application(job_id: str, src: Path, dest_name: str) -> None:
    """Best-effort copy of a generated material into applications/<job_id>/ so that
    folder holds the actual submission materials (the cover letter + tailored CV/PDF),
    as applications/README.md promises. Never fails the save if the copy can't happen."""
    dest_dir = config.APPLICATIONS_DIR / job_id
    tmp = dest_dir / (dest_name + ".tmp")
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, tmp)
        tmp.replace(dest_dir / dest_name)  # atomic
    except OSError as exc:
        log.warning("mirror %s -> applications/%s failed: %s", dest_name, job_id, exc)
        try:
            tmp.unlink(missing_ok=True)  # don't litter the bundle with a partial .tmp
        except OSError:
            pass


def clear_mirrored_cv_pdf(job_id: str) -> None:
    """Remove a stale applications/<id>/cv.pdf (e.g. after a failed recompile) so the
    mirrored PDF never disagrees with the mirrored .tex."""
    try:
        (config.APPLICATIONS_DIR / job_id / "cv.pdf").unlink(missing_ok=True)
    except OSError as exc:
        log.warning("clear mirrored pdf applications/%s failed: %s", job_id, exc)


def read_cover_letter(job_id: str) -> Optional[str]:
    """The last saved cover-letter draft for a job (None if none yet). Stored as a
    plain-markdown sidecar next to the per-job markdown."""
    path = config.JOBS_DIR / f"{job_id}.cover_letter.md"
    return path.read_text(encoding="utf-8") if path.exists() else None


def write_cover_letter(job_id: str, content: str) -> str:
    config.JOBS_DIR.mkdir(parents=True, exist_ok=True)
    path = config.JOBS_DIR / f"{job_id}.cover_letter.md"
    tmp = path.with_suffix(path.suffix + ".tmp")  # write+rename so a poller never reads a partial file
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)  # atomic
    _mirror_to_application(job_id, path, "cover_letter.md")
    return f"data/jobs/{job_id}.cover_letter.md"


def read_cv_tex(job_id: str) -> Optional[str]:
    """The last tailored-CV LaTeX source for a job (None if never generated)."""
    path = config.JOBS_DIR / f"{job_id}.cv.tex"
    return path.read_text(encoding="utf-8") if path.exists() else None


def write_cv_tex(job_id: str, tex: str) -> str:
    config.JOBS_DIR.mkdir(parents=True, exist_ok=True)
    path = config.JOBS_DIR / f"{job_id}.cv.tex"
    tmp = path.with_suffix(path.suffix + ".tmp")  # write+rename so a poller never reads a partial file
    tmp.write_text(tex, encoding="utf-8")
    tmp.replace(path)  # atomic
    _mirror_to_application(job_id, path, "cv.tex")
    return f"data/jobs/{job_id}.cv.tex"


def cv_pdf_path(job_id: str) -> Path:
    """Path to the compiled tailored-CV PDF (may not exist if LaTeX is unavailable)."""
    return config.JOBS_DIR / f"{job_id}.cv.pdf"


def mirror_cv_pdf(job_id: str) -> None:
    """Copy the compiled tailored-CV PDF into applications/<job_id>/ (no-op if absent)."""
    pdf = cv_pdf_path(job_id)
    if pdf.exists():
        _mirror_to_application(job_id, pdf, "cv.pdf")


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


def delete_job(job_id: str) -> bool:
    """Hard-remove a job row AND its per-job artifacts under data/jobs/ (snapshot,
    evaluation, cover letter, tailored CV — the `<id>.*` sidecar family). The caller
    owns the linked-application guard: application history must never vanish as a
    side effect of deleting a posting."""
    jobs = list_jobs()
    remaining = [j for j in jobs if j.id != job_id]
    if len(remaining) == len(jobs):
        return False
    _write_csv(config.JOBS_CSV, JOB_FIELDS, [j.model_dump() for j in remaining])
    # Exact-prefix match, not glob(f"{job_id}.*"): ids come from our own rows, but a
    # name with glob metacharacters must never widen the match — startswith can't.
    try:
        for p in config.JOBS_DIR.iterdir():
            if p.name.startswith(f"{job_id}."):
                try:
                    p.unlink()
                except OSError:
                    log.warning("delete_job: could not remove artifact %s", p)
    except OSError:
        pass
    # The applications/<id>/ mirror (prepared materials) goes too — otherwise a later
    # job that REUSES this id (ids are minted per-year sequentially) would silently
    # inherit the old job's materials. Safe: the caller guarantees no application row
    # exists for this id.
    shutil.rmtree(config.APPLICATIONS_DIR / job_id, ignore_errors=True)
    log.info("delete_job id=%s", job_id)
    return True


def purge_closed_jobs(older_than_days: int, today: "date | None" = None) -> dict[str, int]:
    """Bulk-delete CLOSED jobs whose posting date is older than the cutoff.

    Deliberately conservative: only status == "closed" (dead) rows qualify; jobs with
    a linked application are skipped (they are the user's history), and jobs with a
    missing/unparseable posted_date are skipped rather than guessed at. `today` is
    injectable for tests."""
    from datetime import date, timedelta

    zeros = {"deleted": 0, "skipped_linked": 0, "skipped_undated": 0}
    if older_than_days < 1:
        # A zero/negative window would flip the cutoff into the future and delete
        # EVERYTHING closed — refuse here so no caller can ever do that.
        return zeros

    cutoff = (today or date.today()) - timedelta(days=older_than_days)
    deleted = skipped_linked = skipped_undated = 0
    for j in list_jobs():
        if j.status != "closed":
            continue
        try:
            posted = date.fromisoformat(j.posted_date)
        except (TypeError, ValueError):
            skipped_undated += 1
            continue
        if posted > cutoff:
            continue
        if get_application(j.id):
            skipped_linked += 1
            continue
        delete_job(j.id)
        deleted += 1
    log.info("purge_closed_jobs days=%s deleted=%s skipped_linked=%s skipped_undated=%s",
             older_than_days, deleted, skipped_linked, skipped_undated)
    return {"deleted": deleted, "skipped_linked": skipped_linked, "skipped_undated": skipped_undated}


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
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    tmp.replace(path)  # atomic — concurrent reads (e.g. the profile poll) never see a partial file


def read_profile() -> dict[str, Any]:
    return _read_yaml(config.PROFILE_YML)


def write_profile(data: dict[str, Any]) -> None:
    _write_yaml(config.PROFILE_YML, data)


_RESUME_EXTS = (".pdf", ".tex", ".md", ".txt")


def resolve_resume_file() -> Optional[Path]:
    """The user's master résumé to ingest: profile.resume_path if set + present, else
    the most-recently-modified real file under resume/ (PDF/.tex/.md/.txt; ignores the
    README and dotfiles). None if there's nothing to ingest.

    The résumé must live under resume/: a resume_path that is absolute or escapes the
    folder (`../…`) is rejected (no arbitrary-file read) and falls through to newest."""
    rp = str(read_profile().get("resume_path") or "").strip()
    if rp:
        try:
            p = (config.ROOT / rp).resolve()
            p.relative_to(config.RESUME_DIR.resolve())  # confine to resume/
            if p.is_file():
                return p
        except (ValueError, OSError):
            pass  # absolute / traversal / unresolvable -> ignore, use the newest instead
    if not config.RESUME_DIR.is_dir():
        return None
    cands = [
        f for f in config.RESUME_DIR.iterdir()
        # plain files only — NOT symlinks (a symlink could point outside resume/, e.g.
        # to /etc/passwd); skip dotfiles + any README.*.
        if f.is_file() and not f.is_symlink() and not f.name.startswith(".")
        and f.suffix.lower() in _RESUME_EXTS and f.stem.lower() != "readme"
    ]
    return max(cands, key=lambda f: f.stat().st_mtime) if cands else None


def resume_rel(p: Path) -> str:
    """A repo-relative string for storing as profile.resume_path (else the bare name)."""
    try:
        return str(p.relative_to(config.ROOT))
    except ValueError:
        return p.name


def read_cv_source() -> str:
    """The raw CV text the user last submitted (Internal mode reads this to parse)."""
    return config.CV_SOURCE.read_text(encoding="utf-8") if config.CV_SOURCE.exists() else ""


def write_cv_source(text: str) -> str:
    path = config.CV_SOURCE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)  # atomic — the Internal poll never reads a partial file
    return "config/cv_source.md"


def read_ingest_result() -> dict[str, Any]:
    """Marker for the last job-ingest (monotonic `seq` + result), so the UI can poll
    for completion of an Internal ingest even when the job dedups (count unchanged)."""
    path = config.JOBS_DIR / ".ingest_result.json"
    if not path.exists():
        return {"seq": 0}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {"seq": 0}


def write_ingest_result(data: dict[str, Any]) -> None:
    config.JOBS_DIR.mkdir(parents=True, exist_ok=True)
    path = config.JOBS_DIR / ".ingest_result.json"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(path)  # atomic


def read_patterns() -> dict[str, Any]:
    """The last saved pattern-insights narrative ({} if none). Same store path for
    External (POST) and Internal (PUT) — the UI polls this."""
    path = config.PATTERNS_FILE
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def write_patterns(data: dict[str, Any]) -> str:
    config.PATTERNS_FILE.parent.mkdir(parents=True, exist_ok=True)
    path = config.PATTERNS_FILE
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(path)  # atomic — the Internal poll never reads a partial file
    return "data/patterns.json"


def read_job_source() -> str:
    """The raw job posting the user last pasted/uploaded (Internal mode parses this)."""
    return config.JOB_SOURCE.read_text(encoding="utf-8") if config.JOB_SOURCE.exists() else ""


def write_job_source(text: str) -> str:
    path = config.JOB_SOURCE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)  # atomic
    return "config/job_source.md"


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


def write_portals(data: dict[str, Any]) -> None:
    """Persist the scan config (companies / queries / filters). Store-only — the Settings UI
    edits this so users never hand-edit YAML."""
    _write_yaml(config.PORTALS_YML, data)
