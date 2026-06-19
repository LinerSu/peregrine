<p align="center">
  <img src="web/public/peregrine-icon.png" alt="Peregrine" width="160" height="160" />
</p>

<h1 align="center">Peregrine</h1>

A personal, local-first **AI job-search assistant** — the fastest hunter for your next role. Give it your CV; it scans
job portals, scores fit, prepares your materials, and gates the **Apply** button
behind a strengths / weaknesses / materials review. Your data stays on your
machine.

## Quick start

```bash
cp .env.example .env          # "mock" provider works with no API key
# (optional) set LLM_PROVIDER + key in .env for real responses
docker compose up --build
```

- Web UI → http://localhost:5173
- API → http://localhost:8000 (`/api/health`, `/api/status`)

Then in the chat bar try: **"find jobs matching my CV"** → review the scored
results → open a job → **Evaluate fit** → **Prepare to apply** → Apply.

## How it works

```
web/ (React chat + dashboard)
  └─► api/ (FastAPI)  ── agent harness (LLM loop + tools)
        ├─ subagents: searcher · evaluator · reviewer (isolated context)
        ├─ tools: scan_jobs · evaluate_fit · prepare_materials · parse_cv · list_jobs
        ├─ providers: greenhouse (live) · ashby/lever/generic (stubs)
        └─ skills -> .agents/skills/*/SKILL.md  (open standard, dual-use with CLIs)
data/   jobs.csv · applications.csv · jobs/<id>.md   (single source of truth)
config/ profile.yml · memory.yml · portals.yml       (memory + scraper config)
```

**Data format:** sortable metrics → CSV; long-form text (descriptions,
qualifications, snapshots, evaluations) → per-job Markdown; config/memory → YAML.
Dedup key = `company` + `company_job_id`.

For agent/architecture details and the continuity protocol (so a fresh AI
session can resume), see [AGENTS.md](AGENTS.md) and [STATUS.md](STATUS.md).

## Scope, limits & disclaimer

Peregrine is built to be a **good web citizen**, not a scraper that bulldozes
other companies' sites.

**What it does**
- Fetches jobs only from boards it officially supports **and** that permit
  automated access — currently Greenhouse, plus single postings you paste from
  amazon.jobs or jobs.apple.com.
- Scores fit against your CV, prepares materials, and tracks your applications.
- Keeps your data on your machine.

**What it won't do**
- It **won't scrape sites whose Terms forbid it or that block bots** — e.g.
  LinkedIn, Indeed, Glassdoor, Meta. For those, paste the job text instead.
- It **won't bypass** logins, paywalls, CAPTCHAs or bot-detection, and won't
  impersonate a browser to evade blocks. Every fetch honors `robots.txt`, a
  per-host rate limit, an explicit host allow-list, and an honest, self-identifying
  User-Agent (enforced in [`crawl_policy.py`](api/app/agent/crawl_policy.py)).
- It **won't submit applications for you** — you always click Apply after the
  review gate — and won't invent skills or experience you don't have.

**Disclaimer.** You are responsible for complying with each site's Terms of
Service. Fit scores and upskilling suggestions are AI-generated guidance, not
guarantees. If a board isn't supported, copy the job description in manually
rather than asking Peregrine to break through a site's protections.

---

## Vision (original notes)

applications folder track each application you applied
each application includes position, company, date, website, location, flexibility, status, salary range, interview date, contacts, and notes.

if application you provide cover letter, or special resume version, we store under applications.

resume stores either pdf or latex version of your resume. cv / resume depends on your preference. but we current just focs on industrial jobs

scraper extract job information from job posting website, try to track your interested jobs. each job includes position, company, open date, close date, website, location, flexibility, salary range, and status. E.g. is still opening or already closed (like cannot apply anymore, post removed, etc.) we keep a snapshot just in case it disappears in the future.

Each job shows what the job will do, basic qualification, and preferred qualification. any restrictions on the job, like citizenship, sponsorship, etc. The salary includes base salary, bonus, stock (if shown) and some may depends on location.

scripts may help you organize your job search, searching online to extract job information or generate some metrics for your filtering.

templates include some templates for writing cover letters, emails, and other communication with recruiters or hiring managers.

upskilling show based on your current skills, what you miss for the job you want, and try give you some advice on how to upskill yourself (may not be accurate, but just for insights).

E.g. if they require some skill your resume / any external information (website, linkedin, etc.) shows you do not have, we will flag it give you some advice on how to upskill yourself. Or try to let you know what they are looking for.

The then front-ends like a web page will show your all the information for application.

Give a search function to search for the job you want. and useful links to external resources, like resume templates, interview preparation, etc.

