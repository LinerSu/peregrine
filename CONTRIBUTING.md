# Contributing

Thanks for looking. Issues labelled [`good first issue`](../../issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22)
are self-contained and don't require understanding the whole architecture.

## Setup

```bash
cp .env.example .env      # the "mock" provider needs no API key
./scripts/install-hooks.sh   # REQUIRED — installs the pre-commit privacy guards
docker compose up -d --build
```

The API is on `127.0.0.1:8000`, the web UI on `127.0.0.1:5173`. The API bind-mounts the
repo and reloads on save; the web bundle needs `docker compose up -d --build web`.

`./scripts/install-hooks.sh` is not optional. The hooks block personal data (profile, CV,
tracked jobs, applications) from reaching a commit. CI re-checks on every pull request, but
your local history is yours to keep clean.

## Running the tests

The API image has no test dependencies and the host has no app dependencies, so tests run
in a throwaway container with the test directory mounted:

```bash
docker compose run --rm -v "$PWD/api/tests:/app/tests" api \
  sh -c "pip install -q pytest && python -m pytest tests -q"
```

Frontend:

```bash
cd web && npm install && npm run build   # tsc -b && vite build — this is the typecheck too
```

## The rules that aren't obvious

**Every LLM feature must work in BOTH modes.** External mode calls a provider from the
API; Internal mode has local Claude do the reasoning and `PUT` the result to a store-only
endpoint, which the web polls. A feature that only works in one mode is incomplete. The
Internal side lives in `.claude/skills/peregrine/SKILL.md`; the store-only routes are the
`PUT`s, and Internal must never call a metered `POST`.

**Never commit personal data, and never put it in an issue, a PR, or a code comment.** The
app runs on someone's real CV and job hunt. That includes the *shape* of it: the employers
they track and the roles they're applying to are private context, not just their name and
email. Use placeholders — `Acme`, `Acme Inc.`, `Initech`, `Globex` — in tests, comments and
examples.

**Generalize from the example.** A bug report about one field is usually a bug about a
class of fields; a request about one company is usually about a relationship between
companies. Fix the class, and let the test pin the class.

**Scraping stays inside the policy.** Every board fetch goes through
`api/app/agent/crawl_policy.py` — block-list, then host allow-list, then `robots.txt`, then
a per-host rate limit, with an honest User-Agent. Adding a source means adding it there,
with a test. Never add a path that bypasses a login, paywall, CAPTCHA, or bot detection.
See [docs/SCANNING.md](docs/SCANNING.md).

## Pull requests

- Branch from `main`; `main` is protected.
- Commit subjects are **72 characters max** (the `commit-msg` hook enforces it). Say what
  changed and why — the body is the place to explain the reasoning.
- CI must pass: backend tests, frontend build, the demo-dataset smoke test, the PII guard,
  and a `docker-compose config` check.
- Review conversations must be **resolved** before merge — reply with what you did about
  each, or why it isn't an issue.
- Add a test that **fails without your fix**. If a test passes on the unfixed code, it is
  pinning nothing; check that before you claim it covers the bug.
- Close the issue from the PR body with `Closes #N`.
