"""Mode contract: every LLM-touching feature must work in BOTH External and
Internal mode. Concretely, each ships:
  - POST  (External: the metered LLM call), and
  - PUT   (Internal: store-only — local Claude saves its result), and
  - GET    (poll, so the web UI reflects the Internal save).

This test enumerates the app's routes and fails if any feature is missing a leg —
the automated "inspection loop" so a new LLM feature can't land single-mode.
"""
import pytest

from app.main import app


def _routes() -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for r in app.routes:
        for method in getattr(r, "methods", None) or []:
            out.add((method, r.path))
    return out


# feature -> [external POST, internal store-only PUT, poll GET]
CONTRACT = {
    "evaluate": [
        ("POST", "/api/jobs/{job_id}/evaluate"),
        ("PUT", "/api/jobs/{job_id}/evaluation"),
        ("GET", "/api/jobs/{job_id}/evaluation"),
    ],
    "upskilling": [
        ("POST", "/api/jobs/{job_id}/upskilling"),
        ("PUT", "/api/jobs/{job_id}/upskilling"),
        ("GET", "/api/jobs/{job_id}/upskilling"),
    ],
    "cover-letter": [
        ("POST", "/api/jobs/{job_id}/cover-letter"),
        ("PUT", "/api/jobs/{job_id}/cover-letter"),
        ("GET", "/api/jobs/{job_id}/cover-letter"),
    ],
    "cv/profile": [
        ("POST", "/api/cv"),          # External: LLM parses the CV
        ("PUT", "/api/profile"),      # Internal: store-only profile merge
        ("GET", "/api/profile"),      # poll
    ],
    "tailored-cv": [
        ("POST", "/api/jobs/{job_id}/cv"),
        ("PUT", "/api/jobs/{job_id}/cv"),
        ("GET", "/api/jobs/{job_id}/cv"),
    ],
    "patterns": [
        ("POST", "/api/stats/patterns"),   # External: LLM narrative over the outcomes
        ("PUT", "/api/stats/patterns"),    # Internal: store-only (local Claude's narrative)
        ("GET", "/api/stats/patterns"),    # poll
    ],
}


@pytest.mark.parametrize("feature,legs", list(CONTRACT.items()))
def test_llm_feature_supports_both_modes(feature, legs):
    routes = _routes()
    missing = [leg for leg in legs if leg not in routes]
    assert not missing, f"{feature}: missing mode-contract route(s) {missing}"


def test_job_ingestion_supports_both_modes():
    """Ingestion creates a job (so it's not the per-job POST/PUT/GET trio), but it
    must still work in both modes: External parses with the LLM; Internal stashes
    the raw posting store-only and saves Claude's parsed fields store-only."""
    routes = _routes()
    external = [("POST", "/api/jobs/ingest-doc"), ("POST", "/api/jobs/ingest-doc/upload")]
    internal = [
        ("PUT", "/api/jobs/ingest-source"),
        ("POST", "/api/jobs/ingest-source/upload"),
        ("POST", "/api/jobs/ingest-doc/save"),
    ]
    missing = [leg for leg in external + internal if leg not in routes]
    assert not missing, f"job ingestion missing route(s): {missing}"
