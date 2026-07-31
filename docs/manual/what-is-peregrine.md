# What is Peregrine

Peregrine is a **local-first AI job-search assistant**. You give it your CV and the companies
you care about; it finds matching jobs, scores how well you fit, helps you prepare your
application materials, and tracks everything — all on your own machine.

## The idea

A job search is a pipeline: *find roles → judge fit → prepare materials → apply → track*.
Peregrine runs that pipeline for you, but keeps **you** in control at every step. It never
applies on your behalf — the **Apply** button is gated behind a review so you always see your
strengths, gaps, and materials before anything goes out.

## A tour of the Jobs view

![Annotated tour of the Peregrine Jobs view](/img/hero-annotated.png)

| # | What it is |
|---|---|
| 1 | **The six tabs** — the whole app. Jobs is where you live; the number on Applications is your live count. |
| 2 | **Demo data badge** — you're on a fictional persona. `./scripts/dataset.sh off` returns to your own data. |
| 3 | **External / Internal (Claude)** — where the AI runs. External spends an API key; Internal drives the Claude already on your machine. |
| 4 | **Scan all · Add a job** — two ways in: pull from the boards you configured, or paste / upload / link a single posting. |
| 5 | **Status chips** — your funnel as a filter. The counts update live. |
| 6 | **A job row** — fit score, company, position and skill fit at a glance. Click to open it on the right. |
| 7 | **Evaluate fit** — scores this posting against your CV and writes everything below. |
| 8 | **The evaluation** — not just a number: recommendation, legitimacy and archetype, then evidence-backed strengths, honest gaps, and what to prepare. |
| 9 | **Prepare to apply** — the apply gate. The Apply link stays locked until you've read the review; Peregrine never applies for you. |
| 10 | **The local Claude terminal** — in Internal mode the analysis runs in your own Claude session, on your machine. |

## How it works (high level)

1. **You set up** a profile (from your CV) and a short list of target companies.
2. **Scan** pulls current openings from those companies' public job boards and stores them.
3. **Evaluate fit** scores a job against your profile and explains the *why* — strengths,
   gaps, and what to prepare.
4. **Prepare** drafts a tailored CV and cover letter; a review gate summarizes everything.
5. **Track** records what you applied to, with status, dates, and notes.

The AI does the reading, scoring, and drafting. You make the decisions.

## What makes it different

- **Local-first & private.** Your profile, jobs, and applications live on your machine. The
  only network traffic is the public job feeds during a scan and (optionally) your chosen AI
  provider. Nothing is phoned home. See *Privacy & compliance*.
- **A good web citizen.** It reads only public, opt-in job-board feeds for companies you
  list — no scraping sites that forbid it, no platform-wide crawling.
- **You hold the wheel.** No auto-apply, no invented experience. It surfaces and drafts; you
  review and decide.

## Two ways to run the AI

- **External** — uses an AI provider key you set (metered per token). The default.
- **Internal (Claude)** — drives Claude in a local terminal on your own subscription (no API
  key, no per-token cost).

Both do the same things; pick whichever fits your budget. See *External vs Internal mode*.

## Where to go next

- **Find jobs** — your first scan.
- **Check your fit** — score a job and read the explanation.
- **Get CV help** — build your profile and improve your CV.
