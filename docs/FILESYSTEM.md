# Filesystem guide — what lives where, and what you can drop in

Peregrine is **local-first**: all your data *persists* as plain files on your machine —
nothing is uploaded to a Peregrine server (there isn't one). You can drive a lot of the
app straight from the filesystem (edit a YAML, drop a résumé), and in **Internal mode**
the local Claude reads and writes these same files. Your personal files are gitignored
(the committed `*.example.*` files are just first-run seeds).

> **Privacy note:** in **External** mode, AI actions send the relevant text (a CV, a
> posting) to your configured `LLM_PROVIDER` over the network — that's the metered API
> call. **Internal** mode keeps even that on your local Claude.

## You edit / drop these (you → app)

| Path | What it's for |
|------|---------------|
| `config/profile.yml` | Your career profile **and** what you're looking for (targets, comp, locations, keywords). The agent reads it for every fit score and updates it from your CV. |
| `config/portals.yml` | **Scan** sources — one entry per company: `provider` (`greenhouse \| ashby \| lever \| recruitee \| smartrecruiters \| workable`) + the company's `slug` on that board. Plus search `queries` and `filters`. |
| `resume/` | Drop your master résumé (**PDF / .tex / .md / .txt**). Then **Profile → "Import from `resume/` folder"** parses it into your profile. Uses `resume_path` if set, else the newest file. |
| `data/cover_letter_samples/*.md` | Your own past cover letters — used as **style references** when drafting new ones (tone/structure only, never copied). |
| `config/cv_source.md`, `config/job_source.md` | Raw CV / job text you paste or upload in the UI. In **Internal mode** the local Claude reads these to parse (you normally don't touch them by hand). |

## The app writes these (app → you)

| Path | What it is |
|------|-----------|
| `data/jobs.csv` + `data/jobs/<id>.md` | Tracked jobs + the full posting + the agent's evaluation, per job. |
| `data/jobs/<id>.{evaluation.json,cover_letter.md,cv.tex,cv.pdf,upskilling.json}` | Per-job generated artifacts (fit eval, cover letter, tailored CV LaTeX + PDF, skill-gap analysis). The `cv.pdf` exists only when a LaTeX engine is installed — a missing PDF is expected, not a bug. |
| `data/applications.csv` | Your application tracker (status, dates, contacts, notes). |
| `applications/<id>/` | The **per-submission bundle** for a job: `cover_letter.md`, `cv.tex`, and `cv.pdf` (when LaTeX is available) are copied here as you generate them, so each application's materials sit in one folder. |
| `data/patterns.json` | The saved "pattern insights" narrative shown on the Insights tab. |

## Internal mode — the filesystem *is* the hand-off

There are two assistant modes (global toggle, top-right):

- **External** — AI actions call a metered LLM API (`LLM_PROVIDER` + key in `.env`).
- **Internal** — AI actions run on your **local Claude** in the embedded terminal
  (free, on your own subscription). Here the loop is filesystem-based: the web app
  writes the input file, shows you a copyable command, the local Claude does the work
  and saves the result via a store-only API route, and the web polls for it.

Internal-mode commands (run them in the Claude terminal when prompted):

| Command | Reads | Writes |
|---------|-------|--------|
| `parse my cv` | `config/cv_source.md` (or `resume/`) | profile (`PUT /api/profile`) |
| `evaluate fit for <id>` | `data/jobs/<id>.md`, `config/profile.yml` | the job's evaluation |
| `analyze skill gaps for <id>` | same | the job's upskilling sidecar |
| `draft a cover letter for <id>` | the job, profile, `api/app/cover_letters/`, `data/cover_letter_samples/` | the cover letter |
| `tailor my cv for <id>` | the job + profile | the tailored CV (`.tex` → PDF) |
| `ingest the job I pasted` | `config/job_source.md` | a new tracked job |
| `analyze my patterns` | `GET /api/stats/outcomes` | the pattern-insights narrative |

If `LLM_PROVIDER` is unset (no key), External mode returns **mock placeholders** and
the app shows an amber banner — switch to Internal, or set a key.

## Reference assets (shipped with the repo)

| Path | What it is |
|------|-----------|
| `templates/` | Outreach/application templates (`cover-letter.md`, `recruiter-email.md`) the `materials-prep` skill drafts from. |
| `api/app/cover_letters/*.md` | Curated example cover letters (by role) used as built-in style references. |
| `.agents/skills/*/SKILL.md` | The rubrics each Internal-mode task follows. |
| `*.example.*` (in `config/`, `data/`) | First-run seeds copied to the live files on startup. |

## What's gitignored (stays on your machine)

`data/*.csv`, `data/jobs/*`, `data/patterns.json`, `config/profile.yml`,
`config/portals.yml`, `config/cv_source.md`, `config/job_source.md`,
`data/cover_letter_samples/`, `resume/*`, and `applications/*` — your real data.
Only the `README.md` / `.example.*` placeholders in those folders are committed.

## Folder tree

```
config/         profile.yml · portals.yml · cv_source.md · job_source.md · memory.yml  (+ *.example.yml)
data/           jobs.csv · applications.csv · patterns.json
  jobs/         <id>.md and per-job sidecars (evaluation, cover_letter, cv.tex/pdf, upskilling)
  cover_letter_samples/   your past letters (style refs)
resume/         your master résumé (drop a PDF/.tex/.md/.txt here)
applications/   <id>/ — per-submission bundle (cover_letter.md, cv.tex, cv.pdf)
templates/      outreach/application templates (materials-prep skill)
api/            FastAPI backend (app/, tests/)
web/            React + Vite frontend
docs/           guides (this file, manual-validation, test report)
.agents/skills/ Internal-mode task rubrics
.claude/skills/ the peregrine Internal command router
```
