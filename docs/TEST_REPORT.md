# Test report — Peregrine job assistant

_Run: 2026-06-20 · stack: `docker compose` (provider=mock) · all suites automated._

## Summary

| Suite | Cases | Result |
|---|---|---|
| **Unit** (`api/tests/`, pytest, isolated) | 57 | ✅ 57 passed |
| **Behavioral + regression** (`scripts/behavioral_test.py`, live API) | 37 | ✅ 37 passed, 0 failed |

**1 genuine fault found and fixed** during the run (see below).

## How to re-run

```bash
docker compose up -d                                   # stack must be running
# unit:
docker compose run --rm -v "$PWD/api/tests:/app/tests" api \
  sh -c "pip install -q pytest && cd /app && python -m pytest tests -q"
# behavioral + regression (mutates data; restore the seed after):
python3 scripts/behavioral_test.py
docker compose exec api sh -c \
  "cp /app/data/jobs.example.csv /app/data/jobs.csv && cp /app/data/applications.example.csv /app/data/applications.csv"
```

## What was tested

### Unit (pure logic, no network, no shared state)
- **crawl_policy** — allow-list passes; LinkedIn/Indeed/Glassdoor/Meta + arbitrary hosts refused; helpers.
- **providers** — URL regexes (amazon/apple/ashby/lever/greenhouse), `_strip_html`, `_epoch_ms_to_date`, Apple hydration walk, `ingest_url` blocks LinkedIn / returns None for unknown.
- **data_store** — job & application round-trips, dedup key, `next_id` (shared jobs+apps), targets round-trip.
- **roles** — 14 title→category cases (SDE, Manager, Program/Product Manager, ML Engineer, Applied Scientist, …).
- **harness router** — each message classifies to exactly one bounded intent; no `MAX_ITERS` loop.
- **tools** — `_passes_filters` (location/remote/keyword + targets override), `_merge_evaluation` (replace-not-duplicate), `mark_applied` (status flip, creation, field preservation).
- **subagents** (regression for the fault below) — evaluator/upskiller/reviewer ignore echoed non-result JSON and use the deterministic fallback.

### Behavioral (black-box over the live HTTP API)
- **Health & seed** — `/api/health`; seed = 1 Anthropic job; role backfilled to "ML Engineer".
- **Chat router** — "find jobs"→scan+list; "evaluate … Anthropic"→evaluate_fit; "skills I need"→upskilling; LinkedIn URL→polite refusal; open question→single answer, no tools.
- **Ingest / role / dedup** — Apple ingest (live) → role "Program Manager", surrogate id, re-ingest dedupes; Ashby + Lever (live).
- **Evaluate + apply gate** — fit_score returned; recommendation ∈ {apply,hold,skip}; evaluation cards present in markdown; prepare returns the apply URL.
- **Applications tracker** — mark applied (status+today's date); appears in list; PATCH updates; manual add; delete.
- **Star & role override**, **Preferences** round-trip, **CV upload** (.txt + real PDF via pypdf; invalid PDF → 422).

### Regression (encodes previously-fixed bugs / invariants)
- Crawl-policy block-list (LinkedIn/Indeed/Glassdoor/Meta) + arbitrary host refused with no fetch.
- Dedup on `company + company_job_id`.
- **ID-collision guard** — a manually-added application gets an id distinct from a later scanned job.
- **PATCH field whitelist** — a non-whitelisted field (`company`) in an application PATCH is ignored.
- Apply gate returns a real apply URL (never auto-submits).
- Role classification applied at ingest.

## Fault found & fixed

**Mock-mode evaluation/upskilling silently returned the wrong object once the profile was non-empty.**

- **Symptom:** `POST /api/jobs/{id}/evaluate` returned `{"targets": {}, "job_id": "…"}` — no `fit_score`.
- **Root cause:** the `mock` LLM echoes the prompt; the prompt embeds the profile JSON. `_json_from_text` greedily extracts the first `{…}` (the echoed profile) and the subagents accepted any non-empty dict as their result. It only worked while the profile was empty (`{}` is falsy → fallback).
- **Fix:** subagents now require their result to contain the expected key (`fit_score` for evaluator/reviewer, `missing_skills` for upskiller); `parse_cv` only accepts CV-shaped JSON (`name`/`headline`/`skills`/`location`). Otherwise the deterministic fallback is used. ([subagents.py](../api/app/agent/subagents.py), [tools.py](../api/app/agent/tools.py))
- **Guard:** [test_subagents.py](../api/tests/test_subagents.py) locks the behavior; verified against the original trigger (populated profile → `fit_score 0.5` fallback).

## Notes / known limitations
- AI-quality outputs (fit reasoning, CV parsing, upskilling) are deterministic placeholders under `mock`; they become real with an LLM key. The suites verify **plumbing and contracts**, not judgment quality.
- Live Ashby/Lever example postings can expire — those checks degrade to SKIP, not FAIL.
- `data/*.csv` are written by the container as root (bind mount); restore via the container, not `git checkout` (they're gitignored).
