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
- Be a polite scraper: honor `rate_limit_seconds`, respect ToS/robots, keep host
  allow-lists in `providers.py` (SSRF safety).

## How to run
```bash
cp .env.example .env          # mock provider works with no API key
docker compose up --build     # web -> http://localhost:5173 , api -> :8000
```

## How to extend
- **New job board** → add a provider fn in `app/agent/providers.py` + register in `PROVIDERS`.
- **New capability** → add a `SKILL.md` under `.agents/skills/` + a tool in `tools.py`.
- **Real LLM** → set `LLM_PROVIDER` + key in `.env`.

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
- Providers: **Greenhouse (live)**, **amazon.jobs URL ingest (live, validated on job 3196773)**; ashby/lever/generic are stubs.
- Tools: `scan_jobs`, `ingest_job_url`, `evaluate_fit`, `prepare_materials`, `parse_cv`, `list_jobs`.
- LLM provider-agnostic (anthropic/openai/ollama/**mock** fallback so it boots with no key).
- Frontend (3-pane): Chat · Jobs table · Job detail with human-in-the-loop **apply gate**.

**Front-end gaps vs. the product vision (prioritized — pick up here):**
1. Add top-level **tabs**: Jobs · Applications · Upskilling · Profile/CV.
2. **Applications tracker** view (applied date, status, interview date, contacts, notes).
   API `/api/applications` exists; no UI yet, and no "mark as applied" write path.
3. Enrich the **jobs table** columns: status, salary range, flexibility, posted/close dates; sortable.
4. Render **job detail + evaluation as structured cards** (Strengths / Weaknesses / Materials),
   not the current raw-Markdown `<pre>`.
5. **CV upload** box (currently only chat-paste) + an **external-resources** panel
   (resume templates, interview prep links).
6. **Upskilling** UI (skill exists; add a tool + endpoint + view).

**Backend gaps:** implement ashby/lever providers; write `applications.csv` on "applied";
cover-letter generation in `materials-prep`; optional SQLite derived index; tests.
