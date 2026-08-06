"""Data access layer: CSV (metrics) + Markdown (long-form) + YAML (config).

Single source of truth = `data/jobs.csv` / `data/applications.csv` and the
per-job `data/jobs/<id>.md` files. Keep this module the only place that touches
those files so reads/writes stay consistent.
"""
from __future__ import annotations

import csv
import json
import threading
import re
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


# Serializes read-modify-write on the CSVs. Every mutation is read-all, change, write-all,
# so two of them interleaving loses one side's change entirely — and mutations now happen
# off the request path (background evaluations, scans), not just one at a time. Scoped to
# this process, which is the whole story for a single-worker local app; a multi-worker
# deployment would need a file lock as well.
_STORE_LOCK = threading.RLock()


# Leading characters a spreadsheet reads as "this cell is a formula". company, position and
# location arrive verbatim from a job board, and docs/manual/edit-data.md tells users to
# bulk-edit these CSVs — in a spreadsheet. `csv` quotes such a value but quoting is not
# neutralising: Excel/LibreOffice still evaluate `=WEBSERVICE(...)` or a DDE payload on open.
_FORMULA_LEAD = ("=", "+", "-", "@")


def _neutralize_formula(value: Any) -> Any:
    """Prefix a formula-leading STRING with an apostrophe, the spreadsheet marker for
    "this is text".

    Strings only: salary_min / fit_score are floats, and apostrophising a negative number
    would come back as a value `float()` can't read. The escape is idempotent — a value
    that already starts with `'` no longer starts with a formula lead, so the rewrite of
    every row on every save can't grow a second one. That stability is the contract the
    round-trip test pins; `_read_csv` deliberately does NOT unescape (undoing it would put
    the live payload back into the file a spreadsheet opens)."""
    if isinstance(value, str) and value[:1] in _FORMULA_LEAD:
        return "'" + value
    return value


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow(
                {k: ("" if r.get(k) is None else _neutralize_formula(r.get(k))) for k in fields}
            )
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


# Legal-entity suffixes that don't change WHO the employer is. Stripped repeatedly
# from the end ("Example Co., Ltd." loses both), never below one word.
_COMPANY_SUFFIXES = frozenset({
    "incorporated", "inc", "corporation", "corp", "limited", "ltd", "llc", "llp",
    "plc", "gmbh", "ag", "sa", "srl", "bv", "oy", "ab", "kk", "pte", "pty",
    "co", "company",
})


def _syntactic_norm(name: str) -> str:
    """Casefolded, punctuation collapsed to spaces, trailing legal suffixes stripped.
    Unicode-aware (a CJK company name must not collapse to nothing), and never maps a
    non-empty name to the empty key — distinct employers must never merge by accident."""
    s = re.sub(r"[^\w]+", " ", (name or "").casefold()).replace("_", " ")
    words = s.split()
    while len(words) > 1 and words[-1] in _COMPANY_SUFFIXES:
        words.pop()
    return " ".join(words) or (name or "").casefold().strip()


def board_company_key(name: str) -> str:
    """Key for BOARD-scoped bookkeeping (the scan's listed-snapshot and dead-job
    pruning): syntactic only, NO alias registry. An alias says two names are the same
    EMPLOYER — it does not say they share one job BOARD, and pruning one board's jobs
    against another board's listing silently closes live postings."""
    return _syntactic_norm(name)


# The user's INCREMENTAL company registry (config/companies.yml, gitignored): alias →
# canonical mappings for relationships no string rule can know (an acquired brand and its
# parent, a company that rebranded). Grows from what THIS install's user adds as their
# search runs into them — it is
# deliberately not a shipped global database. Cached on the file's mtime: norm_company
# runs inside scan/match loops and must not re-read yaml per call.
_alias_cache: "tuple[str, float, dict[str, str]] | None" = None  # (path, mtime, mapping)


def _company_aliases() -> dict[str, str]:
    global _alias_cache
    path = config.CONFIG_DIR / "companies.yml"
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {}
    if _alias_cache and _alias_cache[0] == str(path) and _alias_cache[1] == mtime:
        return _alias_cache[2]
    out: dict[str, str] = {}
    try:
        data = _read_yaml(path)
    except yaml.YAMLError:
        # A typo in this OPTIONAL, hand-edited file must degrade to "no aliases" —
        # norm_company sits inside dedup/matching/scan and must never 500 the app.
        log.warning("config/companies.yml is invalid YAML — ignoring the alias registry")
        data = {}
    for entry in (data.get("companies") or []) if isinstance(data, dict) else []:
        if not isinstance(entry, dict):
            continue
        canonical = _syntactic_norm(str(entry.get("name") or ""))
        if not canonical:
            continue
        aliases = entry.get("aliases")
        if isinstance(aliases, str):  # a lone string is a common YAML slip — accept it
            aliases = [aliases]
        if not isinstance(aliases, list):
            continue
        for alias in aliases:
            a = _syntactic_norm(str(alias))
            if a and a != canonical:
                out[a] = canonical
    _alias_cache = (str(path), mtime, out)  # cached even when broken/empty: no reparse loop
    return out


def norm_company(name: str) -> str:
    """Canonical company key: "Acme", "Acme Inc." and "ACME, INC" are the same
    employer — variants must never break dedup, application↔job matching, or scan
    pruning. Two layers: syntactic normalization (case/punctuation/legal suffixes),
    then the user's personal alias registry for real-world relationships (see
    _company_aliases). This is only ever an EQUALITY KEY — display strings are
    never rewritten (the first-seen spelling stays on the row)."""
    s = _syntactic_norm(name)
    return _company_aliases().get(s, s)


def find_job_by_key(company: str, company_job_id: str) -> Optional[Job]:
    """Dedup key = company + company_job_id (company via norm_company, so "Acme"
    and "Acme Inc." can't create duplicate rows for the same req)."""
    company, company_job_id = norm_company(company), company_job_id.strip().lower()
    for j in list_jobs():
        if norm_company(j.company) == company and j.company_job_id.strip().lower() == company_job_id:
            return j
    return None


def match_job(
    jobs: list[Job], company: str, position: str, company_job_id: str = "",
    location: str = "", url: str = ""
) -> Optional[Job]:
    """Find the tracked job an application corresponds to, against a preloaded list.

    In precedence order: the posting URL (two rows pointing at the same link ARE the
    same posting, whatever the company/title spellings say), then company+requisition
    id, then company+position (case-insensitive, with location as a tiebreaker when
    several share the title). Returns None if untracked."""
    u = (url or "").strip()
    if u:
        # Only when it's UNAMBIGUOUS. The same posting really can be tracked twice under
        # one link (a board listing it in two cities, an ingest that beat the URL dedup),
        # and picking the first row would be guessing by CSV order — the same thing the
        # company+position branch below refuses to do. Fall through instead: the
        # requisition key may still separate them.
        hits = [j for j in jobs if j.url.strip() == u]
        if len(hits) == 1:
            return hits[0]
    c = norm_company(company)  # "Acme" must match a job tracked as "Acme Inc."
    cj = (company_job_id or "").strip().lower()
    # Only a real, non-manual key counts (a whitespace/"manual-" key must fall through
    # to the company+position match, not key-match a job with an empty id).
    if cj and not cj.startswith("manual-"):
        for j in jobs:
            if norm_company(j.company) == c and j.company_job_id.strip().lower() == cj:
                return j
    p = (position or "").strip().lower()
    matches = [j for j in jobs if norm_company(j.company) == c and j.position.strip().lower() == p]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1 and (location or "").strip():
        loc = location.strip().lower()
        loc_matches = [j for j in matches if j.location.strip().lower() == loc]
        if len(loc_matches) == 1:
            return loc_matches[0]
    return None  # no match, or ambiguous — don't guess by CSV row order


def link_application_to_job(orphan: Application, job: Job) -> Application:
    """Re-key an application onto the job it belongs to: the job is promoted to the
    application's lifecycle status, the application takes the job's id and posting fields
    (url/salary/posted_date/fit…) while keeping its own tracker fields, and the superseded
    row is dropped. Never downgrades a job already in progress — the application mirrors
    the job then. Deterministic (no LLM), so both modes behave identically."""
    from datetime import date

    if job.status in ("open", "closed", "removed") and orphan.status:
        job.status = orphan.status
        upsert_job(job)
    data = job.model_dump()
    data["id"] = job.id
    for f in ("applied_date", "interview_date", "contacts", "notes", "people"):
        if getattr(orphan, f, ""):
            data[f] = getattr(orphan, f)
    if not data.get("applied_date"):
        data["applied_date"] = date.today().isoformat()
    linked = Application(**data)
    upsert_application(linked)
    if orphan.id != job.id:
        delete_application(orphan.id)
    return linked


def adopt_orphan_application(job: Job) -> Optional[Application]:
    """Link an application recorded BEFORE its posting was tracked to the job that just
    arrived.

    Applying first and adding the posting afterwards is the normal order of events, but it
    leaves an ORPHAN: an application row with its own id and a "manual-" key, connected to
    nothing. The Jobs list then keeps offering "prepare to apply" for a job already applied
    to, and the two rows drift apart. So a newly created posting adopts a single
    unambiguous orphan.

    Deliberately conservative: several orphans matching one posting means don't guess.
    """
    candidates = [
        a for a in list_applications()
        if a.id != job.id
        and match_job([job], a.company, a.position, a.company_job_id, a.location, a.url) is not None
    ]
    if len(candidates) != 1:
        return None
    linked = link_application_to_job(candidates[0], job)
    log.info("adopted orphan application %s onto job %s", candidates[0].id, job.id)
    return linked


def find_job_for_posting(
    company: str, position: str, company_job_id: str = "", location: str = "", url: str = ""
) -> Optional[Job]:
    """match_job against all tracked jobs (one read)."""
    return match_job(list_jobs(), company, position, company_job_id, location, url)


def upsert_job(job: Job) -> Job:
    with _STORE_LOCK:  # read-modify-write: a concurrent one would lose this change
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
    """Persist the whole jobs list in one write. For batch callers that mutate many rows
    and want to avoid the per-row read+rewrite of upsert_job.

    Callers holding a list they read a while ago should use merge_scan_results instead —
    this one overwrites, including anything that changed since they read."""
    with _STORE_LOCK:
        _write_csv(config.JOBS_CSV, JOB_FIELDS, [j.model_dump() for j in jobs])


def merge_scan_results(minted: list[Job], closed_ids: set[str]) -> set[str]:
    """Apply a scan's outcome onto the CURRENT rows instead of overwriting them.

    A scan reads the jobs list, then spends seconds to minutes on the network. Writing its
    stale copy back reverts everything that changed meanwhile — a background fit
    evaluation (now routine, since ingest auto-evaluates), a star, a status set by hand, a
    job ingested in another tab. Whole rows could vanish that way, not just fields.

    So only what the scan actually DECIDED is applied: the postings it minted, and the
    ones it found dead. Everything else is whatever the store says now. Returns the
    resulting id set, so snapshot pruning also works from post-merge reality rather than
    from the scan's stale view.
    """
    with _STORE_LOCK:
        current = list_jobs()
        by_id = {j.id: j for j in current}
        for jid in closed_ids:
            j = by_id.get(jid)
            # Only an OPEN row goes closed: if you applied to it while the scan ran, that
            # decision is newer than the board's silence and outranks it.
            if j is not None and j.status == "open":
                j.status = "closed"
        for j in minted:
            if j.id in by_id:
                # Shouldn't happen: ids are reserved when handed out (_allocate_id), so a
                # concurrent ingest can't take one this scan minted. Keep the guard for a
                # hand-edited CSV — but say so, rather than dropping a posting silently.
                log.warning("scan merge: minted id %s already present, dropping the scan's row", j.id)
                continue
            current.append(j)
            by_id[j.id] = j
        _write_csv(config.JOBS_CSV, JOB_FIELDS, [j.model_dump() for j in current])
        return {j.id for j in current}


def _max_id_num(year: int) -> int:
    """Highest NNN across BOTH jobs and applications for the given year (0 if none)."""
    ids = [j.id for j in list_jobs()] + [a.id for a in list_applications()]
    nums = [
        int(i.split("-")[-1])
        for i in ids
        if i.startswith(f"{year}-") and i.split("-")[-1].isdigit()
    ]
    return max(nums) if nums else 0


# Highest id number handed out THIS PROCESS, keyed by (store path, year). The CSV alone
# can't answer "what's free": a scan mints ids in memory and writes them minutes later, so
# an ingest reading the CSV meanwhile would hand out the same id — two rows, one id, and
# whichever wrote second clobbered the other's snapshot. Reserving here makes an id taken
# the moment it is handed out, written or not. Keyed by path so a test's temp store never
# inherits another's counter; never lowered by deletions, so a deleted id is not reused
# (its artifacts may still exist). A second API process on one data directory would need a
# file lock — not a configuration we ship.
_allocated: dict[tuple[str, int], int] = {}


def _allocate_id(year: int) -> str:
    with _STORE_LOCK:
        key = (str(config.JOBS_CSV), year)
        n = _allocated.get(key)
        if n is None:  # first id for this store: seed from what's on disk
            n = _max_id_num(year)
        n += 1
        _allocated[key] = n
        return f"{year}-{n:03d}"


def id_minter() -> "Iterator[str]":
    """Yield successive unique ids (year-NNN). Lets a batch (scan) mint many ids up front;
    each one is RESERVED as it is yielded, so a concurrent ingest can't be handed the same
    id while the scan is still on the network. Unique across jobs + applications."""
    from datetime import date

    while True:
        yield _allocate_id(date.today().year)


def next_id() -> str:
    """Next surrogate id like 2026-001, unique across BOTH jobs and applications (so a
    manually-added application can't later collide with a scanned job) and reserved on the
    spot, so it can't collide with ids a running scan has minted but not yet written."""
    from datetime import date

    return _allocate_id(date.today().year)


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
    with _STORE_LOCK:
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
    with _STORE_LOCK:
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
    with _STORE_LOCK:
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
    """Read a config mapping, degrading to {} rather than raising.

    Every file this reads is documented as hand-editable, so malformed YAML is a user
    typo, not an exceptional condition — and it used to surface as a 500 from whichever
    request happened to touch it next, sometimes AFTER that request had already written
    a row. A non-mapping (a list, a bare string) is the same class of mistake: callers
    all do .get(), which would raise on a list. Both become "empty", loudly logged."""
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        log.warning("%s is not valid YAML (%s) — treating it as empty", path.name, exc.__class__.__name__)
        return {}
    if data is None:
        return {}
    if not isinstance(data, dict):
        log.warning("%s should be a mapping, got %s — treating it as empty", path.name, type(data).__name__)
        return {}
    return data


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
