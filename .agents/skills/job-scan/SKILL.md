---
name: job-scan
description: Search job portals (ATS feeds + queries) for roles matching the user's profile, dedupe, snapshot postings, and write them to data/jobs.csv + data/jobs/<id>.md. Use when the user asks to find or search for jobs.
---

# Job Scan

## Goal
Discover relevant openings and persist them as the single source of truth.

## Steps
1. Load `config/portals.yml` (queries, companies, filters) and `config/profile.yml`.
2. For each configured company, call the matching provider tool
   (`provider_greenhouse`, `provider_ashby`, `provider_lever`, or `provider_generic`).
3. For each free-text query, run `web_search` across supported boards.
4. **Dedupe** on `company` + `company_job_id`.
5. Apply hard filters (location, remote_only, max_age_days). Not salary: boards don't
   give comp at scan time, so `targets.min_salary` is flagged at serve time instead.
6. For survivors: write a row to `data/jobs.csv` and, if `snapshot: true`,
   a `data/jobs/<id>.md` with the full posting.
7. Keep scanning until the queries/companies are exhausted, then report counts.

## Rules
- Be a polite scraper: honor `rate_limit_seconds`, respect robots/ToS.
- Never auto-apply. Discovery only.
- Preserve a snapshot so closed/removed postings survive.

## Output
A summary: how many new, how many duplicates, how many filtered out.
