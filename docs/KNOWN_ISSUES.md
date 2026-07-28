# Known issues

Open defects and gaps, newest first. Sources: pre-PR review rounds
(`.claude/workflows/review.js`), dogfooding, and other agents' reports.
Fixed items move out of this file — the commit that fixes one should delete its entry.

Conventions: **Cost** = spends API tokens. **Data** = can corrupt or lose stored data.
**UX** = works but confuses. **Gap** = missing coverage, not a wrong behaviour.

## Correctness / data

- **Data · A scan can clobber a fit score written by a background evaluation.**
  Both do read-modify-write on `jobs.csv` with no locking, so a scan that starts before a
  background `evaluate_fit` finishes writes back the pre-evaluation row. Widened by
  auto-evaluate-on-ingest, which made background writes routine rather than rare.
- **Data · `profile_ready()` raises on a malformed `profile.yml`**, and it runs *after* the
  job row was already created — so a hand-edited profile turns an ingest into a 500 with a
  half-finished result.
- **UX · "Missing a fit score" means two different things.** The backfill treats a job as
  scored if any evaluation exists, but the UI and Internal mode hide evaluations made
  against a previous CV (stale). A job whose only evaluation is stale therefore reads as
  unscored on screen and as scored to the backfill, so it never gets re-run.

## Cost / safety

- **Cost · `POST /api/jobs/evaluate-missing` has no cap and no in-flight dedup.** Every call
  schedules one LLM evaluation per unscored open job; calling it twice doubles the spend on
  the same jobs. Needs a per-run cap and a guard against overlapping runs.
- **Cost · That endpoint is also reachable by a cross-site form POST** (a simple request, so
  the browser sends it without a preflight). Loopback-only binding limits exposure, but a
  page open in the same browser could trigger the fan-out. Wants a same-origin check.
- **Safety · The Internal skill chains evaluation straight onto freshly ingested posting
  text** with no prompt-injection guard. Posting text is untrusted input and it now reaches
  the model automatically rather than on an explicit user action.

## Gaps

- **Gap · The backfill has no web UI caller** — nothing in the app calls
  `/api/jobs/evaluate-missing`, so in practice it's Internal-mode-only. External users have
  no way to score jobs added before the feature existed.
- **Gap · No test coverage for the auto-evaluate wiring on the upload path**
  (`/ingest-doc/upload`). The URL and paste paths are covered.
- **Gap · `PATCH /api/jobs/{id}` exposes only a small field set** — `currency`, salary and
  other parsed fields can't be corrected through the API, so fixing one means editing
  `data/jobs.csv` by hand.

## Onboarding / relevance

- **UX · A fresh install inherits the example file's search terms.** `config/portals.yml` is
  created by copying `config/portals.example.yml`, whose sample `queries:` then silently
  become the user's relevance gate *and* their target roles for skill-gap advice. The
  example should ship with `queries:` empty (empty = keep everything).
- **UX · "Suggest from my profile" proposes résumé headings, not job titles.** It returns the
  profile headline, section headings and publication titles verbatim — strings no job board
  will match. It should derive role-shaped queries and map them to board vocabulary.

## Build

- **Gap · `npx tsc --noEmit` reports one pre-existing error** in `web/src/Docs.tsx`
  (implicit `any` on a destructured `children`). The CI frontend build passes, so this is
  type-checking strictness only.
