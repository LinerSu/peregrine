"""Concrete agent tools, registered for LLM tool-calling and callable directly
from API routes. Each tool persists through the data store (single source of
truth) and records progress to STATUS.md.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date
from typing import Any

from .. import config
from .. import cv_render
from .. import data_store as store
from .. import status
from ..config import APPLICATIONS_DIR
from ..cover_letter import gather_style_references
from ..evaluation import assess_legitimacy, classify_archetype
from ..logging_config import get_logger
from ..roles import classify_role
from ..skills import normalize_category
from ..schemas import Application, Job
from . import providers
from .registry import registry
from .subagents import (
    cover_letter_writer,
    cv_tailor,
    evaluator,
    job_parser,
    patterns_analyst,
    reviewer,
    upskiller,
)

log = get_logger(__name__)


def _as_float(value: Any, default: float) -> float:
    """Tolerant coercion — a null/malformed fit_score from a store-only PUT must
    not turn into a 500."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------- #
_SCAN_NEW_CAP = 500  # safety bound against a runaway broad scan; a normal board fits in one scan


@registry.register(
    "scan_jobs",
    "Scan configured ATS providers for jobs, dedupe on company+company_job_id, apply "
    "filters, and persist new postings. Pass `only` to restrict to specific companies. "
    "Returns a summary.",
    {"type": "object", "properties": {
        "only": {"type": "array", "items": {"type": "string"},
                 "description": "company names to scan; omit to scan all configured companies"},
    }, "required": []},
)
def scan_jobs(only: list[str] | None = None) -> dict[str, Any]:
    portals = store.read_portals()
    companies = portals.get("companies", []) or []
    filters = portals.get("filters", {}) or {}
    targets = store.read_targets()
    snapshot = portals.get("snapshot", True)
    max_age = _safe_int(filters.get("max_age_days"))  # 0 = no posted-date limit (bad value -> off)

    if only:  # restrict to the named companies (case-insensitive); ignore non-string entries
        wanted = {c.strip().lower() for c in only if isinstance(c, str) and c.strip()}
        if wanted:  # an all-invalid list falls back to scanning all
            companies = [c for c in companies if c.get("name", "").strip().lower() in wanted]

    status.record("scan_start", f"{len(companies)} companies", current_task="Scanning job portals")

    new = dup = filtered = 0
    capped = False
    # Preload the jobs ONCE: mutate the list in memory and persist in a single write at the
    # end. `index` is the dedup lookup over (company, company_job_id) — so we don't re-read
    # the CSV per posting (find_job_by_key) or rewrite it per new/dead job (upsert_job).
    jobs = store.list_jobs()
    index = {(j.company.strip().lower(), j.company_job_id.strip().lower()): j for j in jobs}
    mint = store.id_minter()
    # company (lowercased) -> the set of company_job_ids its board currently lists. Recorded
    # only for a successful, NON-empty fetch, so a failed/empty fetch never prunes anything.
    listed: dict[str, set[str]] = {}
    for c in companies:
        if capped:
            break
        company_name = c.get("name", "")
        postings = providers.fetch(c.get("provider", "generic"), company_name, c.get("slug", ""))
        for p in postings:
            if not p.company_job_id.strip():
                # No id in the feed -> derive a STABLE, collision-resistant key: a readable
                # slug of title+location plus a short hash of the url, so two id-less
                # postings stay distinct even past _slug's length cap.
                base = _slug(f"{p.position} {p.location}")
                seed = p.url or f"{p.position}|{p.location}"
                digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10]
                p.company_job_id = f"{base}-{digest}" if base else digest
        if postings:  # an authoritative snapshot of what this company lists right now
            listed[company_name.strip().lower()] = {p.company_job_id.strip().lower() for p in postings}
        for p in postings:
            if not _passes_filters(p, filters, targets):
                filtered += 1
                continue
            key = (p.company.strip().lower(), p.company_job_id.strip().lower())
            if key in index:  # already tracked, or added earlier in this same scan
                dup += 1
                continue
            if new >= _SCAN_NEW_CAP:  # stop persisting once the safety cap is hit
                capped = True
                break
            jid = next(mint)
            detail_path = store.write_job_md(jid, _job_md(jid, p)) if snapshot else ""
            job = Job(
                id=jid,
                company=p.company,
                company_job_id=p.company_job_id,
                position=p.position,
                status="open",
                location=p.location,
                posted_date=p.posted_date,
                url=p.url,
                detail_md=detail_path,
                role_category=classify_role(p.position),
            )
            jobs.append(job)
            index[key] = job
            new += 1

    # Dead-job pruning: an OPEN job from a company we just scanned is dead if the board no
    # longer lists it OR (with max_age_days set) its posting is older than the cutoff. Mark it
    # "closed" -- kept (not deleted) so a linked application isn't orphaned and a false positive
    # is recoverable; applied/interviewing/etc. are left untouched (you still applied).
    dead = 0
    for job in jobs:
        ck = job.company.strip().lower()
        if job.status != "open" or ck not in listed:
            continue
        gone = job.company_job_id.strip().lower() not in listed[ck]
        if gone or _too_old(job.posted_date, max_age):
            job.status = "closed"
            dead += 1

    if new or dead:  # one write for the whole batch (no per-row rewrite)
        store.write_jobs(jobs)

    pruned = _prune_orphan_snapshots({j.id for j in jobs})

    summary = {"new": new, "duplicates": dup, "filtered": filtered,
               "capped": capped, "dead": dead, "pruned_snapshots": pruned}
    status.record("scan_done", str(summary), current_task="idle")
    return summary


# A scan writes a `<id>.md` snapshot per new job, but a job ROW only ever leaves jobs.csv via
# a dataset reset/re-seed or a manual edit — and that path never deletes the snapshot, so
# orphaned `.md` files can pile up. Tidy them on each scan, keyed off the authoritative live
# job-id set. Scoped to the exact minted id shape (`<year>-<NNN>`, >=3 digits, per
# store.id_minter) so sidecars (`<id>.cover_letter.md`, `<id>.evaluation.json`) and any
# stray non-id `.md` are never touched.
_SNAPSHOT_RE = re.compile(r"^\d{4}-\d{3,}$")


def _prune_orphan_snapshots(job_ids: set[str]) -> int:
    # Safety floor: never let an EMPTY id-set delete everything when jobs.csv still exists —
    # a torn/corrupt read parses to zero rows, and we won't wipe every cached snapshot over
    # that. A genuinely fresh dataset has no CSV (and no snapshots), so cleanup still works.
    if not job_ids and config.JOBS_CSV.exists():
        return 0
    removed = 0
    for p in config.JOBS_DIR.glob("*.md"):
        if _SNAPSHOT_RE.match(p.stem) and p.stem not in job_ids:
            try:  # best-effort cleanup — a permission/FS error must not abort the scan
                p.unlink()
                removed += 1
            except OSError as exc:
                log.warning("could not prune orphan snapshot %s: %s", p.name, exc)
    if removed:
        log.info("pruned %d orphan job snapshot(s)", removed)
    return removed


def _safe_int(v: Any) -> int:
    """Lenient int for user-editable YAML/JSON — a non-numeric value means 0 (off), not a 500."""
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _too_old(posted_date: str, max_age_days: int) -> bool:
    """True if a posting predates the cutoff. A missing/unparseable date counts as NOT old
    (we can't age what we can't date, so we keep it rather than guess)."""
    if not max_age_days or not posted_date:
        return False
    try:
        d = date.fromisoformat(posted_date[:10])
    except ValueError:
        return False
    return (date.today() - d).days > max_age_days


def _passes_filters(
    p: providers.RawPosting, filters: dict[str, Any], targets: dict[str, Any] | None = None
) -> bool:
    """Portals filters + the user's search targets (config/profile.yml::targets)."""
    targets = targets or {}
    loc_hay = p.location.lower()
    text = f"{p.position} {p.description}".lower()

    # Posted-date age gate: skip postings older than filters.max_age_days (0 = no limit).
    if _too_old(p.posted_date, _safe_int(filters.get("max_age_days"))):
        return False

    # Location: targets override portals; remote postings always pass a location gate.
    locs = [l.lower() for l in (targets.get("locations") or filters.get("locations") or [])]
    if locs and "remote" not in loc_hay and not any(l in loc_hay for l in locs):
        return False
    if (filters.get("remote_only") or targets.get("work_mode") == "remote") and "remote" not in loc_hay:
        return False

    # Keyword include/exclude from search targets.
    if any(kw.lower() in text for kw in (targets.get("exclude_keywords") or [])):
        return False
    include = [kw.lower() for kw in (targets.get("include_keywords") or [])]
    if include and not any(kw in text for kw in include):
        return False
    return True


def _job_md(job_id: str, p: providers.RawPosting) -> str:
    return (
        f"# {p.position} — {p.company}\n\n"
        f"- **id:** {job_id}\n"
        f"- **company_job_id:** {p.company_job_id}\n"
        f"- **location:** {p.location}\n"
        f"- **url:** {p.url}\n"
        f"- **scraped:** {date.today().isoformat()}\n\n"
        f"## Posting\n{p.description or '_no description captured_'}\n\n"
        "---\n\n## Agent evaluation\n"
        "> Filled in by `evaluate_fit`. Gated before the Apply button.\n\n"
        "### Strengths\n- _pending_\n\n### Weaknesses / gaps\n- _pending_\n\n"
        "### Materials to prepare\n- _pending_\n"
    )


# --------------------------------------------------------------------------- #
@registry.register(
    "evaluate_fit",
    "Evaluate how well a job matches the user's profile. Runs evaluator + reviewer "
    "subagents, writes fit_score, and returns strengths/weaknesses/materials.",
    {
        "type": "object",
        "properties": {"job_id": {"type": "string"}},
        "required": ["job_id"],
    },
)
def evaluate_fit(job_id: str) -> dict[str, Any]:
    job = store.get_job(job_id)
    if not job:
        return {"error": f"job {job_id} not found"}

    status.record("evaluate_start", job_id, current_task=f"Evaluating fit for {job_id}")
    job_md = store.read_job_md(job_id) or f"{job.position} at {job.company}"
    evaluation = reviewer(evaluator(job_md, store.read_profile()), job_md)
    saved = save_evaluation(job_id, evaluation)

    status.record("evaluate_done", f"{job_id} score={saved.get('fit_score')}", current_task="idle")
    return saved


def save_evaluation(
    job_id: str, evaluation: dict[str, Any], today: date | None = None
) -> dict[str, Any]:
    """Persist a fit evaluation — same store path whether it came from the External
    subagents or from Internal mode (Claude reasons, then PUTs the result here). No LLM.

    `today` (used only for the legitimacy staleness check) is injectable so tests
    are deterministic; it defaults to the wall clock for live saves."""
    job = store.get_job(job_id)
    if not job:
        return {"error": f"job {job_id} not found"}
    ev = dict(evaluation)
    ev["job_id"] = job_id
    job_md = store.read_job_md(job_id) or f"{job.position} at {job.company}"
    # v2 posting signals are computed server-side (deterministic, identical in
    # External and Internal modes) — never trusted from the caller's payload.
    description = _posting_description(job_md)
    ev.update(assess_legitimacy(job, description, today=today or date.today()))
    ev["archetype"] = classify_archetype(job.position, description)
    job.fit_score = _as_float(ev.get("fit_score"), 0.5)
    store.upsert_job(job)
    store.write_evaluation(job_id, ev)  # structured sidecar the UI renders
    store.write_job_md(job_id, _merge_evaluation(job_md, ev))
    return ev


def _posting_description(job_md: str) -> str:
    """The posting's description text — the '## Posting' section only, excluding
    the title/metadata and any appended evaluation block. Used to gauge how
    detailed (vs. sparse) a posting is for the legitimacy signal."""
    body = job_md.split("## Agent evaluation")[0]
    if "## Posting" in body:
        body = body.split("## Posting", 1)[1]
    return body.strip()


def _merge_evaluation(job_md: str, ev: dict[str, Any]) -> str:
    def bullets(items: list[str]) -> str:
        return "\n".join(f"- {i}" for i in items) or "- _none_"

    legit = ev.get("legitimacy_score")
    legit_line = ""
    if legit is not None:
        flags = ev.get("legitimacy_flags", [])
        legit_line = f"- **legitimacy:** {legit} ({', '.join(flags) if flags else 'no flags'})\n"
    archetype_line = f"- **archetype:** {ev['archetype']}\n" if ev.get("archetype") else ""
    section = (
        "## Agent evaluation\n"
        f"- **fit_score:** {ev.get('fit_score')}\n"
        f"- **recommendation:** {ev.get('recommendation', 'hold')}\n"
        f"{legit_line}{archetype_line}\n"
        f"### Strengths\n{bullets(ev.get('strengths', []))}\n\n"
        f"### Weaknesses / gaps\n{bullets(ev.get('weaknesses', []))}\n\n"
        f"### Materials to prepare\n{bullets(ev.get('materials', []))}\n"
    )
    marker = "## Agent evaluation"
    return (job_md.split(marker)[0].rstrip() + "\n\n---\n\n" + section) if marker in job_md else (
        job_md + "\n\n---\n\n" + section
    )


# --------------------------------------------------------------------------- #
@registry.register(
    "prepare_materials",
    "Build the pre-apply checklist for a job (strengths, weaknesses, materials) "
    "so the user is ready before clicking Apply.",
    {
        "type": "object",
        "properties": {"job_id": {"type": "string"}},
        "required": ["job_id"],
    },
)
def prepare_materials(job_id: str) -> dict[str, Any]:
    job = store.get_job(job_id)
    if not job:
        return {"error": f"job {job_id} not found"}
    if job.fit_score is None:
        evaluate_fit(job_id)
        job = store.get_job(job_id)
    (APPLICATIONS_DIR / job_id).mkdir(parents=True, exist_ok=True)
    status.record("materials", job_id)
    return {
        "job_id": job_id,
        "apply_url": job.url,
        "detail_md": job.detail_md,
        "note": "Review strengths/weaknesses/materials in the job detail before applying.",
    }


# --------------------------------------------------------------------------- #
@registry.register(
    "assess_upskilling",
    "Compare a job's requirements against the user's profile and surface skill "
    "gaps with concrete ways to close them. Read-only; advisory.",
    {
        "type": "object",
        "properties": {"job_id": {"type": "string"}},
        "required": ["job_id"],
    },
)
def assess_upskilling(job_id: str) -> dict[str, Any]:
    job = store.get_job(job_id)
    if not job:
        return {"error": f"job {job_id} not found"}
    status.record("upskill_start", job_id, current_task=f"Upskilling analysis for {job_id}")
    job_md = store.read_job_md(job_id) or f"{job.position} at {job.company}"
    saved = save_upskilling(job_id, upskiller(job_md, store.read_profile()))
    status.record("upskill_done", job_id, current_task="idle")
    return saved


def save_upskilling(job_id: str, result: dict[str, Any]) -> dict[str, Any]:
    """Persist a skill-gap analysis — same store path for External and Internal mode.
    No LLM; Internal mode reasons in the terminal and PUTs the result here."""
    job = store.get_job(job_id)
    if not job:
        return {"error": f"job {job_id} not found"}
    out = dict(result)
    out["job_id"] = job_id
    store.write_upskilling(job_id, out)
    return out


def get_upskilling(job_id: str) -> dict[str, Any] | None:
    """Read the last saved skill-gap analysis (None if never run)."""
    return store.read_upskilling(job_id)


def get_evaluation(job_id: str) -> dict[str, Any] | None:
    """Read the last saved structured fit evaluation (None if never run)."""
    return store.read_evaluation(job_id)


def generate_cover_letter(job_id: str) -> dict[str, Any]:
    """External mode: draft a tailored cover letter with the LLM and persist it.

    Grounds the draft in the job, profile, the saved fit evaluation, and local
    style samples (curated + the user's own). Web examples are an Internal-mode
    extra (Claude's own search); see the cover-letter skill."""
    job = store.get_job(job_id)
    if not job:
        return {"error": f"job {job_id} not found"}
    status.record("cover_letter_start", job_id, current_task=f"Cover letter for {job_id}")
    job_md = store.read_job_md(job_id) or f"{job.position} at {job.company}"
    content = cover_letter_writer(
        job, job_md, store.read_profile(), store.read_evaluation(job_id), gather_style_references()
    )
    saved = save_cover_letter(job_id, content)
    status.record("cover_letter_done", job_id, current_task="idle")
    return saved


def save_cover_letter(job_id: str, content: str) -> dict[str, Any]:
    """Persist a cover-letter draft — same store path for External and Internal
    (Internal: Claude writes it in the terminal, then PUTs it here). No LLM."""
    job = store.get_job(job_id)
    if not job:
        return {"error": f"job {job_id} not found"}
    store.write_cover_letter(job_id, content)
    return {"job_id": job_id, "content": content}


def get_cover_letter(job_id: str) -> dict[str, Any] | None:
    """Read the last saved cover-letter draft (None if never generated)."""
    content = store.read_cover_letter(job_id)
    return {"job_id": job_id, "content": content} if content is not None else None


def analyze_patterns() -> dict[str, Any]:
    """External: compute the outcome analytics, ask the LLM for a grounded narrative
    (what's working / at risk / to do), and persist it. Same store path as Internal."""
    from datetime import date

    from ..stats import compute_outcomes

    status.record("patterns_start", "patterns", current_task="Analyzing application patterns")
    outcomes = compute_outcomes(store.list_applications(), date.today())
    insight = patterns_analyst(outcomes)
    saved = save_patterns(insight)
    status.record("patterns_done", "patterns", current_task="idle")
    return saved


def save_patterns(insight: dict[str, Any]) -> dict[str, Any]:
    """Persist a pattern-insights narrative — same store path for External and Internal
    (Internal: local Claude analyzes the outcomes, then PUTs the result here). No LLM."""
    store.write_patterns(insight)
    return insight


def get_patterns() -> dict[str, Any]:
    """Read the last saved pattern-insights narrative ({} if none) — the UI poll target."""
    return store.read_patterns()


def save_profile(fields: dict[str, Any]) -> dict[str, Any]:
    """Store-only profile merge (Internal mode: Claude parses the CV in the terminal,
    then PUTs the extracted fields here). No LLM. Merges non-empty values into the
    existing profile, matching parse_cv's merge so both modes behave the same."""
    profile = store.read_profile()
    profile.update({k: v for k, v in fields.items() if v})  # same filter as parse_cv
    store.write_profile(profile)
    return profile


def save_cv_source(text: str) -> dict[str, Any]:
    """Store the raw CV text the user submitted so Internal-mode Claude can read and
    parse it (config/cv_source.md). No LLM."""
    store.write_cv_source(text)
    return {"chars": len(text)}


def generate_tailored_cv(job_id: str) -> dict[str, Any]:
    """External mode: draft a job-tailored CV (LaTeX) with the LLM, persist it, and
    compile a PDF if a LaTeX engine is available."""
    job = store.get_job(job_id)
    if not job:
        return {"error": f"job {job_id} not found"}
    status.record("tailor_cv_start", job_id, current_task=f"Tailoring CV for {job_id}")
    job_md = store.read_job_md(job_id) or f"{job.position} at {job.company}"
    tex = cv_tailor(store.read_profile(), job.position, job.company, job_md)
    saved = save_tailored_cv(job_id, tex)
    status.record("tailor_cv_done", job_id, current_task="idle")
    return saved


def save_tailored_cv(job_id: str, tex: str) -> dict[str, Any]:
    """Persist tailored-CV LaTeX and (best-effort) compile a PDF — same store path
    for External and Internal (Internal: Claude writes the .tex, then PUTs it). No LLM."""
    job = store.get_job(job_id)
    if not job:
        return {"error": f"job {job_id} not found"}
    store.write_cv_tex(job_id, tex)
    pdf_available = cv_render.compile_pdf(tex, store.cv_pdf_path(job_id))
    # Keep applications/<id>/cv.pdf in sync with the new .tex: mirror on success, or
    # clear a now-stale prior PDF on a failed (re)compile.
    if pdf_available:
        store.mirror_cv_pdf(job_id)
    else:
        store.clear_mirrored_cv_pdf(job_id)
    return {"job_id": job_id, "tex": tex, "pdf_available": pdf_available}


def get_tailored_cv(job_id: str) -> dict[str, Any] | None:
    """Read the last tailored CV (None if never generated)."""
    tex = store.read_cv_tex(job_id)
    if tex is None:
        return None
    return {"job_id": job_id, "tex": tex, "pdf_available": store.cv_pdf_path(job_id).exists()}


def _slug(text: str) -> str:
    """Derive a stable company_job_id from a title when the posting has none."""
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:40] or "posting"


def _ingest_from_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Turn parsed posting fields into a tracked job (dedup by company + id). Shared
    by the External (LLM-parsed) and Internal (Claude-parsed) ingest paths. Bumps the
    ingest marker so the Internal-mode UI poll resolves — even when the job dedups."""
    company = (fields.get("company") or "").strip()
    position = (fields.get("position") or "").strip()
    if not (company and position):
        return {"error": "need at least a company and a position"}
    # Coerce optional fields to strings — the LLM/Claude often emits null for these,
    # which would fail RawPosting/Job validation.
    location = fields.get("location") or ""
    url = fields.get("url") or ""
    posted_date = fields.get("posted_date") or ""
    description = fields.get("description") or ""
    # Mix location into the derived id so two same-titled reqs don't collide.
    company_job_id = (fields.get("company_job_id") or "").strip() or _slug(f"{position} {location}")
    existing = store.find_job_by_key(company, company_job_id)
    if existing:
        job, created = existing, False
    else:
        job = _persist_posting(providers.RawPosting(
            company=company, company_job_id=company_job_id, position=position,
            location=location, url=url, posted_date=posted_date, description=description,
        ))
        created = True
    seq = store.read_ingest_result().get("seq", 0) + 1
    store.write_ingest_result({"seq": seq, "job_id": job.id, "created": created, "position": position})
    return {"job": job.model_dump(), "created": created}


def get_ingest_result() -> dict[str, Any]:
    """The last job-ingest marker (seq + result) — the Internal UI polls this."""
    return store.read_ingest_result()


def ingest_job_doc(text: str) -> dict[str, Any]:
    """External mode: parse a pasted/extracted posting with the LLM into a tracked job."""
    if not text.strip():
        return {"error": "no posting text provided"}
    status.record("ingest_doc_start", f"{len(text)} chars", current_task="Ingesting pasted job")
    parsed = job_parser(text)
    if not parsed:
        status.record("ingest_doc_failed", "no fields parsed", current_task="idle")
        return {"error": "couldn't parse a job from that text — paste more of the posting, or use Internal mode"}
    result = _ingest_from_fields(parsed)
    status.record(
        "ingest_doc_failed" if "error" in result else "ingest_doc_done",
        result.get("error") or parsed.get("company", "?"),
        current_task="idle",
    )
    return result


def save_ingested_job(fields: dict[str, Any]) -> dict[str, Any]:
    """Store-only: create a tracked job from already-parsed fields (Internal mode:
    Claude parses the posting in the terminal, then POSTs the fields here). No LLM."""
    return _ingest_from_fields(fields)


def save_job_source(text: str) -> dict[str, Any]:
    """Stash the raw posting text so Internal-mode Claude can read + parse it. No LLM."""
    store.write_job_source(text)
    return {"chars": len(text)}


# --------------------------------------------------------------------------- #
@registry.register(
    "mark_applied",
    "Record that the user applied to a job: set the job status to 'applied' and "
    "create/refresh the row in applications.csv. The user always clicks Apply "
    "themselves first — this only tracks it.",
    {
        "type": "object",
        "properties": {
            "job_id": {"type": "string"},
            "applied_date": {"type": "string", "description": "ISO date; defaults to today"},
        },
        "required": ["job_id"],
    },
)
def mark_applied(job_id: str, applied_date: str = "") -> dict[str, Any]:
    job = store.get_job(job_id)
    if not job:
        return {"error": f"job {job_id} not found"}

    job.status = "applied"
    store.upsert_job(job)

    when = applied_date or date.today().isoformat()
    existing = store.get_application(job_id)
    app = Application(**job.model_dump(), applied_date=when)
    if existing:  # preserve tracker fields the user has edited
        app.applied_date = existing.applied_date or when
        app.interview_date = existing.interview_date
        app.contacts = existing.contacts
        app.notes = existing.notes
    store.upsert_application(app)

    status.record("mark_applied", f"{job_id} {job.company}", current_task="idle")
    return {"application": app.model_dump(), "created": not existing}


# --------------------------------------------------------------------------- #
_CV_PROMPT = (
    "Return ONLY a JSON profile object with keys:\n"
    "- name, headline, location (strings)\n"
    "- links: object of profile links present in the CV — any of "
    "github/website/linkedin/scholar/twitter/email (omit ones not present)\n"
    "- skills: array of {name, level, evidence, category} where category is one of "
    "Languages | Frameworks & Libraries | Tools | Domains | Soft skills (best guess)\n"
    "- sections: array of résumé sections, each {id, title, summary, items}, where id is "
    "one of education|experience|research|service|awards|projects, title is the display "
    "heading, summary is ONE sentence capturing the section (shown when collapsed), and "
    "items is an array of {heading, subhead, detail, links:[{label,url}]} — heading is the "
    "entry title (degree/role/paper/project), subhead is dates/place, detail is the full "
    "text, and links are any URLs for that entry.\n"
    "Ground everything in the CV; never invent. Omit any section the CV doesn't support."
)


def _normalize_cv_fields(parsed: dict[str, Any]) -> dict[str, Any]:
    """Coerce the LLM's parsed CV into canonical profile fields (lenient — bad entries
    are dropped, not fatal). Produces the same shape for both External and Internal."""
    from ..schemas import ProfileSection

    out: dict[str, Any] = {}
    for k in ("name", "headline", "location"):
        if parsed.get(k):
            out[k] = str(parsed[k])
    skills = parsed.get("skills")
    if isinstance(skills, list):
        clean = [s for s in skills if isinstance(s, dict) and s.get("name")]
        clean += [{"name": s} for s in skills if isinstance(s, str) and s.strip()]
        for s in clean:  # clamp the LLM's category to the canonical set (fallback: classify)
            s["category"] = normalize_category(s.get("category", ""), s.get("name", ""))
        if clean:
            out["skills"] = clean
    links = parsed.get("links")
    if isinstance(links, dict):
        cleaned = {str(k): str(v) for k, v in links.items() if v}
        if cleaned:
            out["links"] = cleaned
    sections = parsed.get("sections")
    if isinstance(sections, list):
        norm = []
        for s in sections:
            if isinstance(s, dict):
                try:
                    norm.append(ProfileSection(**s).model_dump())
                except Exception:
                    pass  # skip an unparseable section, keep the rest
        if norm:
            out["sections"] = norm
    return out


@registry.register(
    "parse_cv",
    "Parse pasted CV text into the user's profile (config/profile.yml) as memory.",
    {
        "type": "object",
        "properties": {"cv_text": {"type": "string"}},
        "required": ["cv_text"],
    },
)
def parse_cv(cv_text: str) -> dict[str, Any]:
    from .subagents import LLMClient, _json_from_text, load_skill

    status.record("cv_intake", f"{len(cv_text)} chars", current_task="Parsing CV")
    llm = LLMClient()
    res = llm.complete(
        [
            {"role": "system", "content": load_skill("cv-intake")},
            {"role": "user", "content": "CV:\n```\n" + cv_text[:12000] + "\n```\n\n" + _CV_PROMPT},
        ]
    )
    fields = _normalize_cv_fields(_json_from_text(res.text))
    # Only accept output that actually looks like a parsed CV (mock mode echoes the
    # prompt, which can contain unrelated JSON — don't write that to the profile).
    valid = any(k in fields for k in ("name", "headline", "skills", "location", "links", "sections"))
    profile = store.read_profile()
    if valid:
        profile.update(fields)
        store.write_profile(profile)
    n = len(fields.get("sections", [])) if valid else 0
    status.record("cv_intake_done", f"sections={n}", current_task="idle")
    return {"updated": valid, "profile": profile}


# --------------------------------------------------------------------------- #
@registry.register(
    "list_jobs",
    "List tracked jobs, optionally filtered by a free-text query over company/position.",
    {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": [],
    },
)
def list_jobs(query: str = "") -> dict[str, Any]:
    jobs = store.list_jobs()
    for j in jobs:  # backfill role for jobs saved before classification existed
        if not j.role_category:
            j.role_category = classify_role(j.position)
    if query:
        q = query.lower()
        jobs = [j for j in jobs if q in j.company.lower() or q in j.position.lower()]
    jobs.sort(key=lambda j: (j.fit_score or 0), reverse=True)
    return {"count": len(jobs), "jobs": [j.model_dump() for j in jobs]}


# --------------------------------------------------------------------------- #
def _persist_posting(p: providers.RawPosting) -> Job:
    """Write a RawPosting to the store (CSV row + snapshot md), returning the Job."""
    jid = store.next_job_id()
    detail_path = store.write_job_md(jid, _job_md(jid, p))
    return store.upsert_job(
        Job(
            id=jid,
            company=p.company,
            company_job_id=p.company_job_id,
            position=p.position,
            status="open",
            location=p.location,
            posted_date=p.posted_date,
            url=p.url,
            detail_md=detail_path,
            role_category=classify_role(p.position),
        )
    )


@registry.register(
    "ingest_job_url",
    "Ingest a single job posting from a pasted URL (e.g. amazon.jobs or a "
    "Greenhouse board), persist it, and return the job. Deduped on company+company_job_id.",
    {
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
    },
)
def ingest_job_url(url: str) -> dict[str, Any]:
    status.record("ingest_start", url[:120], current_task="Ingesting job URL")
    try:
        posting = providers.ingest_url(url)
    except providers.PolicyViolation as exc:
        status.record("ingest_blocked", str(exc)[:160], current_task="idle")
        return {"error": str(exc)}
    if not posting:
        status.record("ingest_failed", url[:120], current_task="idle")
        return {"error": f"unsupported or unreachable URL: {url}"}

    existing = store.find_job_by_key(posting.company, posting.company_job_id)
    job = existing or _persist_posting(posting)
    status.record(
        "ingest_done", f"{job.id} {job.company} {job.company_job_id}", current_task="idle"
    )
    return {"job": job.model_dump(), "deduped": bool(existing), "created": existing is None}
