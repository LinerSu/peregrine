# Security policy

## Reporting a vulnerability

Use GitHub's **Report a vulnerability** button on the Security tab — that opens a private
advisory only the maintainer can see. If it isn't available to you, open an issue with the
`security` label describing the *shape* of the problem (which endpoint, what class of flaw)
and **no working exploit**; we'll move it to a private advisory to work out the details.

Please don't include real personal data in a report — no CV contents, no postings, no
profile. Reproduce with placeholders.

Expect a first response within a week. This is a personal project, not a staffed product.

## What Peregrine is, security-wise

A **local-first, single-user** application. It runs on your machine, binds to loopback,
and holds two things worth protecting: your personal data (CV, profile, tracked jobs and
applications) and, optionally, an LLM provider API key in `.env`.

**In scope** — anything that lets code you didn't run reach either of those:

- A web page you have open triggering a state-changing request against the local API
  (mutating requests from another origin are refused; `GET` is unaffected).
- Anything that gets untrusted text — a job posting is untrusted input — treated as an
  instruction rather than as data.
- Anything that causes personal data to leave the machine, reach a commit, or land in a
  log, an issue, or a PR.
- Anything that makes the app fetch a host the crawl policy forbids, ignore `robots.txt`,
  or bypass a login, paywall, CAPTCHA or bot-detection
  (`api/app/agent/crawl_policy.py` is the single gate).
- Unbounded spend: a path that fans out metered LLM calls without a cap.

**Out of scope**

- Exposing the API to a network or the internet. It binds to `127.0.0.1` by design and has
  no authentication, because it assumes one trusted user on one machine. Putting it behind
  a public address is unsupported, not a vulnerability.
- Anything requiring an attacker who already has a shell on your machine, or write access
  to your `config/`, `data/` or `.env`.
- Multi-user or multi-tenant concerns. There is no user model.
- The LLM being wrong. Fit scores and generated materials are guidance; the Apply gate
  exists precisely because the model's judgement isn't authoritative.

## Handling your own data safely

- Keep the ports on loopback. The shipped `docker-compose.yml` already does this; changing
  it to `0.0.0.0` publishes your CV to your network.
- Install the git hooks (`./scripts/install-hooks.sh`) before committing anything. They
  block personal-data paths and personal terms from reaching a commit; CI re-checks, but
  only for what reaches a pull request.
- Your API key lives in `.env`, which is gitignored. Rotate it if it ever appears in a
  terminal recording, a screenshot, or a pasted log.
