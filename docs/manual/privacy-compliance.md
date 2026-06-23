# Privacy & compliance

Peregrine is built to be **private to you** and a **good web citizen**. Here's the short
version of what that means in practice.

## Your data stays on your machine

Your profile, CV, jobs, and applications live in local files (`config/`, `data/`, `resume/`)
that are **gitignored** — they're never committed or uploaded. The only network traffic
Peregrine makes is:

1. the **public job-board feeds** of the companies you list, during a scan; and
2. your **chosen AI provider** (`anthropic` / `openai` / `ollama`, or none in `mock` mode) for
   the AI features.

Nothing else is sent anywhere, and nothing is phoned home. No account, no telemetry.

## It only reads public, opt-in job feeds

Scanning uses each company's **own public ATS feed** (Greenhouse, Ashby, Lever, Recruitee,
SmartRecruiters, Workable) — a company is reachable because it chose that platform and made
its board public. Peregrine:

- **does not** scrape sites whose terms forbid it or that block bots — **LinkedIn, Indeed,
  Glassdoor, Meta** are refused with a reason (paste the text instead);
- **does not** crawl the whole web or a whole platform — only the companies you list;
- **does not** bypass logins, paywalls, or CAPTCHAs, send credentials, or impersonate a
  browser;
- honors each site's `robots.txt` and rate-limits itself.

Every fetch goes through a single policy gate that enforces this, so the behavior can't be
bypassed by accident.

## You're always in control

Peregrine never submits an application for you (the **Apply** button just opens the real
posting) and never invents experience you don't have.

## Want the technical detail?

The full model — per-provider endpoints, the enforcement layers, and the rules for safely
adding a new source — is in the developer docs:
[`docs/SCANNING.md`](https://github.com/LinerSu/peregrine/blob/main/docs/SCANNING.md). You
remain responsible for complying with each site's Terms of Service in your jurisdiction.
