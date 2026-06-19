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
1. Read `STATUS.md` (current task + todo + recent activity).
2. Skim `logs/agent.log` for the latest run.
3. Check `/memories/session/` notes if available.
4. Continue the top unchecked item in `STATUS.md`.
