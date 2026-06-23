# What is Peregrine

Peregrine is a **local-first AI job-search assistant**. You give it your CV and the companies
you care about; it finds matching jobs, scores how well you fit, helps you prepare your
application materials, and tracks everything — all on your own machine.

## The idea

A job search is a pipeline: *find roles → judge fit → prepare materials → apply → track*.
Peregrine runs that pipeline for you, but keeps **you** in control at every step. It never
applies on your behalf — the **Apply** button is gated behind a review so you always see your
strengths, gaps, and materials before anything goes out.

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
