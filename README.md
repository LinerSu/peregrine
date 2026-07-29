<p align="center">
  <img src="web/public/peregrine-icon.png" alt="Peregrine" width="160" height="160" />
</p>

<h1 align="center">Peregrine</h1>

<p align="center">
  <a href="https://github.com/LinerSu/peregrine/actions/workflows/ci.yml"><img src="https://github.com/LinerSu/peregrine/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-yellow" alt="License: MIT" /></a>
  <img src="https://img.shields.io/badge/local--first-your%20data%20stays%20home-4c1" alt="Local-first" />
  <img src="https://img.shields.io/badge/scraping-opt--in%20ATS%20feeds%20only-0aa" alt="Opt-in ATS feeds only" />
</p>
<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white" alt="Python 3.12" />
  <img src="https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black" alt="React 18" />
  <img src="https://img.shields.io/badge/Docker-compose-2496ED?logo=docker&logoColor=white" alt="Docker Compose" />
  <img src="https://img.shields.io/badge/built%20with-Claude%20Code-D97757" alt="Built with Claude Code" />
</p>

A personal, local-first **AI job-search assistant** — the fastest hunter for your next role. Give it your CV; it scans
job portals, scores fit, prepares your materials, and gates the **Apply** button
behind a strengths / weaknesses / materials review. Your data stays on your
machine.

> 📖 **Using the app?** The full **User Manual** is built into the web UI at **`/docs`**
> (or click **Docs** in the top bar) — getting started, then a guide per goal (find jobs,
> check fit, CV help, apply, track). **This README is the developer / architecture reference.**

## Scope, limits & disclaimer

Peregrine is built to be a **good web citizen**, not a scraper that bulldozes
other companies' sites.

**What it does**
- Reads jobs only from **public, opt-in ATS feeds for companies you explicitly list** —
  Greenhouse, Ashby, Lever, Recruitee, SmartRecruiters, Workable — each by the company's own
  slug. **No platform-wide search or crawl.** Plus single postings you *paste* from
  amazon.jobs / jobs.apple.com.
- Scores fit against your CV, prepares materials, and tracks your applications.
- Keeps your data on your machine.

**What it won't do**
- It **won't scrape sites whose Terms forbid it or that block bots** — LinkedIn, Indeed,
  Glassdoor, Meta are refused with a reason. Paste the job text instead.
- It **won't bypass** logins, paywalls, CAPTCHAs or bot-detection, won't send credentials,
  and won't impersonate a browser. Every board fetch goes through one gate
  ([`crawl_policy.py`](api/app/agent/crawl_policy.py)) that enforces a **block-list → host
  allow-list → robots.txt → per-host rate limit → honest, self-identifying User-Agent**.
- It **won't submit applications for you** — you always click Apply after the review gate —
  and won't invent skills or experience you don't have.

**Privacy.** Your profile, CV, jobs, and applications stay on your machine. The only network
traffic is (a) the public ATS feeds above during a scan, and (b) your configured LLM
provider (`anthropic`/`openai`/`ollama`, or none in `mock` mode). Nothing else is sent
anywhere; nothing is phoned home.

**Compliance.** As shipped, Peregrine fetches only public, opt-in ATS job feeds that permit
automated access and refuses everything else — it does not scrape sites that prohibit it,
bypass authentication or anti-bot measures, or impersonate a browser. The full model,
per-provider endpoints, and the rules for extending it safely are documented in
**[docs/SCANNING.md](docs/SCANNING.md)** (and enforced + tested in
[`crawl_policy.py`](api/app/agent/crawl_policy.py) /
[`test_crawl_policy.py`](api/tests/test_crawl_policy.py)).

**Disclaimer.** You remain responsible for complying with each site's Terms of Service in
your jurisdiction. If a board isn't supported, paste the job description in rather than
asking Peregrine to break through a site's protections. Fit scores and upskilling
suggestions are AI-generated guidance, not guarantees.

---

## Quick start

```bash
cp .env.example .env          # "mock" provider works with no API key
# (optional) set LLM_PROVIDER + key in .env for real responses
docker compose up --build
```

- Web UI → http://localhost:5173
- API → http://localhost:8000 (`/api/health`, `/api/status`)

> Want the in-app Claude terminal too? Run `./start.sh` instead of `docker compose up`
> — it starts the stack **and** the local Claude terminal. See
> [Assistant: External vs Internal (Claude)](#assistant-external-vs-internal-claude).

**First launch is empty by design** — the guided **Get started** flow opens
automatically (CV → search → companies → first scan). Prefer doing it by hand?
Drop your résumé (PDF/`.tex`/`.md`/`.txt`) into `resume/` → **Profile → Import
from resume/**, and list companies to watch in the **Targets** tab.

Then in the chat bar try: **"find jobs matching my CV"** → review the scored
results → open a job → **Evaluate fit** → **Prepare to apply** → Apply.

### Updating after a `git pull`

The **API** mounts its source and runs with `--reload`, so backend code changes (new
routes/schema) take effect on the next request — no rebuild needed. The **web** UI is a
static build, so frontend changes need a rebuild:

```bash
docker compose up -d --build web     # or `--build` to rebuild both
```

(If the API ever seems to serve old behavior, `docker compose up -d --build api`.)

> **Upgrading an install from before the non-root container change:** the api now
> runs as *your* user, but files the old root-mode container wrote are still
> root-owned and will crash it on boot. One-time fix (or just use `./start.sh`,
> which detects this and prints the same command):
> `sudo chown -R $(id -u):$(id -g) data config logs .demo applications resume`
> If your uid isn't 1000 and you run `docker compose up` directly, set
> `PEREGRINE_UID`/`PEREGRINE_GID` in `.env` (see `.env.example`).

## Assistant: External vs Internal (Claude)

The assistant panel has a toggle between two modes:

- **External** — the API-backed chat. Uses your `LLM_PROVIDER` + key
  (`anthropic` / `openai` / `ollama` / `mock`) and is billed per token by that
  provider. This is the default and the path for anyone with API budget.
- **Internal (Claude)** — a **local terminal** embedded in the page, running an
  interactive `claude` session on **your own Anthropic subscription** — no API
  key, no per-token cost. Use this if you'd rather drive Claude on your existing
  plan than pay the metered API.

Internal mode needs [`ttyd`](https://github.com/tsl0922/ttyd) and
[Claude Code](https://claude.com/claude-code) installed on your machine.

> **Heads-up on `ttyd`:** on Debian/Ubuntu, `sudo apt install ttyd` also installs
> and **enables a `ttyd.service`** that runs a *root login shell* on port 7681 —
> which collides with this feature (you'd get a username/password prompt instead
> of Claude). Disable it once: `sudo systemctl disable --now ttyd.service`.

**Recommended — set it up once.** Install the terminal as a background **user**
service (no sudo) so it's always running and you never start it by hand:

```bash
./scripts/install-terminal-service.sh
```

After that, day-to-day you just `docker compose up` and click **Internal
(Claude)** — the terminal auto-starts on login and is always listening; nothing
else to run. Manage it with `systemctl --user {status,stop,start} peregrine-terminal`,
or remove it with `./scripts/install-terminal-service.sh --uninstall`.

**Or start it per session** (no service): `./start.sh` brings up the stack **and**
the terminal together, or run just the terminal with `./scripts/terminal.sh`
(serves `claude` at http://127.0.0.1:7681). Ctrl-C stops it.

Claude runs on the **host**, not inside Docker — that's how it has your own login
and sees this repo, and it's why the terminal can't be a `docker compose` service.

> ⚠️ **Local-only.** The terminal is full shell access to your machine. The
> script binds it to `127.0.0.1`, so it's reachable only from your own machine.
> **Never** bind it to `0.0.0.0` or expose that port to a network. Driving Claude
> here yourself is interactive use of your subscription; don't wire the app to
> query it automatically — that's what the External (API) mode is for.

## How it works

```
web/ (React chat + dashboard)
  └─► api/ (FastAPI)  ── agent harness (LLM loop + tools)
        ├─ subagents: searcher · evaluator · reviewer (isolated context)
        ├─ tools: scan_jobs · evaluate_fit · prepare_materials · assess_upskilling · parse_cv · list_jobs · mark_applied · ingest_job_url
        ├─ scan providers: greenhouse · ashby · lever · recruitee · smartrecruiters · workable  (generic = stub)
        ├─ crawl_policy: allow-list · ToS block-list · robots · rate-limit · honest UA
        └─ skills -> .agents/skills/*/SKILL.md  (open standard, dual-use with CLIs)
data/   jobs.csv · applications.csv · jobs/<id>.md   (single source of truth)
config/ profile.yml · memory.yml · portals.yml       (memory + scraper config)
```

> **Amazon/Apple** aren't supported for **scanning** — they have no public board
> *listing* feed (unlike greenhouse/ashby/lever), so we don't bulk-scan them (same
> stance as career-ops). A single pasted URL still ingests (amazon.jobs `search.json`,
> the Apple posting page), and paste/upload works for any site.

**Data format:** sortable metrics → CSV; long-form text (descriptions,
qualifications, snapshots, evaluations) → per-job Markdown; config/memory → YAML.
Dedup key = `company` + `company_job_id`.

**Where your data lives + what you can drop in:** every folder (and the
"edit a file / drop a résumé" workflows, plus how Internal mode hands off through the
filesystem) is mapped in **[docs/FILESYSTEM.md](docs/FILESYSTEM.md)**.

For agent/architecture details and the continuity protocol (so a fresh AI
session can resume), see [AGENTS.md](AGENTS.md). Runtime status is written to `logs/STATUS.md` at
run time (gitignored — it's generated, and it's scoped to whichever dataset is active).

## Demo / test datasets

Your real profile and jobs are gitignored, so a fresh clone starts empty. To see
the app fully populated — for a demo, a screenshot, or while testing a new
feature — switch on a **demo persona**. Each is a fictional but realistic person
(invented names, companies, and schools) with a profile, jobs, saved fit
evaluations, upskilling notes, and applications, so every tab fills in.

```bash
./scripts/dataset.sh ai-engineer   # switch to a persona (sets .env + restarts the API)
./scripts/dataset.sh off           # back to your live config/ + data/
./scripts/dataset.sh               # show the active dataset + what's available
```

The web reflects the switch on **refresh** — no rebuild (only the API's data changes).
Equivalent by hand: set/clear `PEREGRINE_DATASET` in `.env`, then `docker compose up -d`.

Personas: `ai-engineer` · `ux-designer` · `chem-phd` · `bio-scientist` · `law-student`.
(`./scripts/dataset.sh <name>` also accepts a private local dataset under `.demo/<name>/`.)

The dataset is generated from [`api/app/demo_seed.py`](api/app/demo_seed.py) into an
isolated, gitignored `.demo/<persona>/` directory (mounted to the host) — your `data/`
and `config/` are never touched. Reset a persona by deleting its dir:
`rm -rf .demo/<persona>` then `docker compose up -d` re-seeds it. (Because the data now
persists, editing a persona in `demo_seed.py` also needs that delete to take effect.)

**Private test profile (kept out of the repo):** `PEREGRINE_DATASET` also accepts a
name that *isn't* a built-in persona — as long as you've placed your own data under
`.demo/<name>/` (with a `.seeded` marker file). That's how a personal test résumé you
don't want committed stays isolated: `.demo/` is gitignored, so it never leaves your
machine, and the live `config/`/`data/` stay reserved for your real profile.

(If you run the API **directly on the host** instead of via Docker, `APP_ROOT` defaults
to `api/`, so these datasets live under `api/.demo/<name>/`.)

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) boots every persona and
smoke-tests the API against it.

## Contributing

`./start.sh` self-installs the repo's git hooks on first launch (or run
`scripts/install-hooks.sh` once per clone): a **PII guard** that blocks real
CVs/profiles/jobs/emails from ever being committed, plus crawl-policy and
commit-message checks. To make the guard also catch **your** name/phone/handles:

```bash
cp config/pii_terms.example.txt config/pii_terms.txt   # then add your real strings
```

The terms file is gitignored *and* hook-blocked — it never leaves your machine.
CI re-runs the generic (path + email) checks on every push as a backstop.
