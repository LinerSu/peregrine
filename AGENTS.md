# AGENTS.md — Peregrine

Canonical instructions for any AI coding agent (Claude Code, Gemini, etc.) and
for the in-app agent. A fresh session should read this file + `STATUS.md` +
`logs/agent.log` to resume with full context.

## What this project is
A personal, local-first AI job-search assistant. The user gives a CV; the agent
scans job portals, scores fit, prepares materials, and gates the Apply button
behind a strengths/weaknesses/materials review. Reference inspirations:
`santifer/career-ops` and `MadsLorentzen/ai-job-search`.

## Architecture
```
web/   React + Vite + Tailwind  (chat · jobs table · job detail + apply gate)
  └─► api/  FastAPI
        app/agent/harness.py    orchestration loop (LLM + tool dispatch)
        app/agent/subagents.py  searcher · evaluator · reviewer (isolated context)
        app/agent/tools.py      scan_jobs · evaluate_fit · prepare_materials · parse_cv · list_jobs
        app/agent/providers.py  ATS providers (greenhouse live; ashby/lever/generic stubs)
        app/agent/llm.py        provider-agnostic client (anthropic/openai/ollama/mock)
        app/data_store.py       CSV + Markdown + YAML access (single source of truth)
        app/status.py           writes STATUS.md from logs/activity.jsonl
.agents/skills/*/SKILL.md       dual-use skills (web agent + any CLI)
data/   jobs.csv · applications.csv · jobs/<id>.md     (truth)
config/ profile.yml · memory.yml · portals.yml         (memory + scraper config)
```

## Agent strategy
**Bounded workflows, not a long autonomous loop.** A job-assistant request is
small and specific, and users expect a quick result then a follow-up. So:
- **Intent router** ([harness.py](api/app/agent/harness.py) `_route`) classifies a chat message into **one**
  bounded action — `ingest` (fixed 2-step: ingest→evaluate), `search`, `evaluate`,
  `upskill`, `cv`, or a single grounded `ask` answer. No multi-iteration tool loop.
- **Deep actions are short, fixed subagent runs**, not open exploration: `evaluate_fit`
  = evaluator → reviewer (2 calls); `assess_upskilling` = 1 call. Each diagnoses and returns.
- **Evidence-grounded judgment:** the evaluator must cite profile evidence for every
  strength; an unsupported requirement is a *gap*, never a strength. The reviewer
  subagent re-checks for fabrication in a fresh context before the user sees it.
- **Right-size models** (when a real key is set): default `claude-sonnet-4-6`; route
  cheap/structured work (CV parse, upskilling, scan summaries) to a fast model (Haiku),
  reserve Sonnet/Opus for the fit judge + reviewer. Keep prompts/profile in a cached prefix.
- The `mock` provider still drives every router path deterministically, so the app
  works with no key (judgments are placeholders until a real model is configured).

## Data conventions
- **Dedup key** = `company` + `company_job_id` (companies name IDs differently).
- **Surrogate id** = `YYYY-NNN` (filenames/links).
- **Metrics** (sortable) -> CSV. **Long-form** (descriptions, qualifications,
  snapshot, evaluation) -> `data/jobs/<id>.md`. **Config/memory** -> YAML.

## Hard rules
- Never auto-submit an application. The user clicks Apply after the review gate.
- Never fabricate skills/experience. Verify claims against `config/profile.yml`.
- **Be a good bot, never a malicious crawler.** Every outbound job-board fetch goes
  through `app/agent/crawl_policy.py::safe_get`, which enforces: host **allow-list**
  (supported boards only — SSRF + scope), a **block-list** of ToS-prohibited / bot-
  protected sites (LinkedIn, Meta, Indeed, Glassdoor — refused before any request),
  **robots.txt**, per-host **rate limiting**, and an **honest self-identifying User-Agent**
  (no browser impersonation, no auth-walled/login scraping). Do not bypass it; to support
  a new board, add its host to `ALLOWED_HOSTS` and a parser — never fetch raw URLs directly.
  For blocked boards, have the user paste the job text instead of scraping.

## How to run
```bash
cp .env.example .env          # mock provider works with no API key
docker compose up --build     # web -> http://localhost:5173 , api -> :8000
```

## How to extend
- **New job board** → add a provider fn in `app/agent/providers.py` + register in `PROVIDERS`;
  add its host to `crawl_policy.ALLOWED_HOSTS` and fetch via `crawl_policy.safe_get` (never raw httpx).
- **New capability** → add a `SKILL.md` under `.agents/skills/` + a tool in `tools.py`.
- **New LLM feature → BOTH modes (required).** Every LLM-triggering capability ships
  External (a metered `POST`) **and** Internal (a store-only `PUT` + a `GET` to poll),
  and the web UI branches on the global `mode`: External calls the `POST`; Internal
  shows a copyable guided prompt for local Claude and polls the `GET`. Add the Internal
  command to `.claude/skills/peregrine/SKILL.md` **and** list its trigger phrase in that
  skill's frontmatter `description` (else local Claude won't auto-invoke it).
  `tests/test_mode_contract.py` enforces the POST/PUT/GET trio — a single-mode feature
  fails CI.
- **Real LLM** → set `LLM_PROVIDER` + key in `.env`.

## Quality gate (CI + local git hooks)
**CI** runs on every PR/push to `main` (`.github/workflows/ci.yml`: backend pytest +
frontend tsc/vite build + a 5-persona demo smoke) and is **required to merge**. Local
checks also run at commit time via tracked hooks in `hooks/` (enabled with
`core.hooksPath`). Run **`bash scripts/install-hooks.sh`** once per clone.
- `commit-msg` — subject must be `<type>: <summary>` (feat/fix/docs/chore/…), ≤72 chars.
- `pre-commit` — `py_compile` staged Python + **crawl-policy guard** (blocks raw `httpx`/
  `requests`/browser-UA outside `crawl_policy.py`, so the good-bot rule can't be bypassed).
- Bypass once with `git commit --no-verify`. Heavier checks (web build) belong in CI if/when added.

## Continuity protocol (for a fresh window)
1. Read this **Current status & roadmap** section (durable handoff).
2. Check repository memory (`/memories/repo/`) and `/memories/session/` if present.
3. `STATUS.md` shows the *runtime* current task/activity — it is auto-generated
   and overwritten by the app, so treat it as a live log, not the plan.
4. Skim `logs/agent.log` for the latest run.
5. Continue the top unchecked item in the roadmap below.

## Current status & roadmap
_Last updated: 2026-06-19._

**Shipped (works end-to-end, validated):**
- Repo renamed **my-job-search → Peregrine**; pushed to `github.com/LinerSu/peregrine` (main).
- `docker compose up` runs `peregrine-api` (:8000) + `peregrine-web` (:5173). Health: `/api/health`.
- Backend: agent harness + evaluator/reviewer/upskiller subagents + tool registry.
- Providers (all **live**, via `crawl_policy.safe_get`): **Greenhouse**, **amazon.jobs**,
  **Apple** (jobs.apple.com — parses embedded `__staticRouterHydrationData`), **Ashby**
  (api.ashbyhq.com), **Lever** (api.lever.co). Both scan-by-slug and paste-a-URL ingest. generic = stub.
- Tools: `scan_jobs`, `ingest_job_url`, `evaluate_fit`, `prepare_materials`, `parse_cv`,
  `list_jobs`, `mark_applied`, `assess_upskilling`.
- LLM provider-agnostic (anthropic/openai/ollama/**mock** fallback so it boots with no key).
- Frontend: persistent **Chat** sidebar + tabs — **Jobs** (sortable table + detail rendered as
  **structured cards**, apply gate), **Applications** tracker (inline status/dates/contacts/notes),
  **Targets** (search-intent preferences), **Profile / CV** (paste **+ file upload PDF/txt/md**),
  **Upskilling** (per-job skill-gap analysis).
- Write paths: `POST /api/jobs/{id}/apply` (status→applied + applications.csv), `PATCH
  /api/applications/{id}`, `PUT /api/preferences` (profile.targets), `POST /api/cv/upload`,
  `POST /api/jobs/{id}/upskilling`.
- **Search intent**: `config/profile.yml::targets` (roles/locations/work_mode/min_salary/
  include+exclude keywords) drives `scan_jobs` filtering and is visible to the fit-scoring LLM.
- **Tests**: `api/tests/` (crawl_policy, providers, data_store) — 20 passing. Run:
  `docker compose run --rm -v "$PWD/api/tests:/app/tests" api sh -c "pip install -q pytest && python -m pytest tests -q"`.

**Remaining roadmap (prioritized — pick up here):**
1. **Wire a real LLM** — set `LLM_PROVIDER` + key in `.env`; with `mock`, fit/CV/upskilling are placeholders.
2. **Cover-letter generation** in `materials-prep` (LLM-gated).
3. **min_salary** is captured in Targets but not yet enforced in `_passes_filters` (salary isn't on
   RawPosting at scan time) — wire it once providers carry comp.
4. Optional **SQLite** derived index for fast search at scale; broaden test coverage (routers/subagents).

**Provider notes / ToS:** Meta (metacareers.com) is **intentionally unsupported** — it blocks
plain fetches (HTTP 400) and its GraphQL needs a browser session + `fb_dtsg`/`doc_id` tokens;
scraping it would fight bot-protection and risk an IP ban. **Always check a site's ToS/robots and
rate-limit before fetching; don't hammer or retry aggressively. Host allow-lists stay pinned for
SSRF safety.** For blocked boards, prefer manual paste of the description over scraping.
