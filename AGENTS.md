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
- **Real LLM** → set `LLM_PROVIDER` + key in `.env`.

## Quality gate (local git hooks)
Solo/local-first, no CI — checks run at commit time via tracked hooks in `hooks/`
(enabled with `core.hooksPath`). Run **`bash scripts/install-hooks.sh`** once per clone.
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
- Backend: agent harness + evaluator/reviewer subagents + tool registry.
- Providers: **Greenhouse (live)**, **amazon.jobs URL ingest (live, job 3196773)**,
  **Apple / jobs.apple.com URL ingest (live, validated on positionId 200668037)** — parses the
  page's embedded `window.__staticRouterHydrationData`; ashby/lever/generic are stubs.
- Tools: `scan_jobs`, `ingest_job_url`, `evaluate_fit`, `prepare_materials`, `parse_cv`,
  `list_jobs`, **`mark_applied`**.
- LLM provider-agnostic (anthropic/openai/ollama/**mock** fallback so it boots with no key).
- Frontend: persistent **Chat** sidebar + tabbed working area — **Jobs** (table+detail w/ apply
  gate), **Applications** tracker, **Profile / CV**, **Upskilling**. Jobs table now shows
  status + salary; Applications tab edits status/interview-date/contacts/notes inline.
- Write path: **Mark as applied** (UI button + `POST /api/jobs/{id}/apply`) flips job status and
  writes `applications.csv`; `PATCH /api/applications/{id}` updates tracker fields.

**Front-end gaps vs. the product vision (prioritized — pick up here):**
1. ~~Top-level **tabs**~~ ✅ done. ~~**Applications tracker** + "mark as applied" write path~~ ✅ done.
2. **Jobs table** still needs **sortable** columns + flexibility/close-date (status+salary added).
3. Render **job detail + evaluation as structured cards** (Strengths / Weaknesses / Materials),
   not the current raw-Markdown `<pre>`.
4. **CV file upload** (Profile tab has paste + external-resources panel; no file upload yet).
5. **Upskilling** is a placeholder view — add the backend tool + endpoint to power it.

**Backend gaps:** implement ashby/lever providers; cover-letter generation in `materials-prep`;
optional SQLite derived index; tests.

**Provider notes / ToS:** Meta (metacareers.com) is **intentionally unsupported** — it blocks
plain fetches (HTTP 400) and its GraphQL needs a browser session + `fb_dtsg`/`doc_id` tokens;
scraping it would fight bot-protection and risk an IP ban. **Always check a site's ToS/robots and
rate-limit before fetching; don't hammer or retry aggressively. Host allow-lists stay pinned for
SSRF safety.** For blocked boards, prefer manual paste of the description over scraping.
