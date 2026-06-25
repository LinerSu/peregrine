#!/usr/bin/env python3
"""One-time backfill: compute Job.keywords from each tracked posting's snapshot.

The `keywords` field (a salient-word blob from the description) powers SEARCH recall beyond the
vocab-capped skill/domain tags — new scans tag it inline (tools._job_tag_kwargs), so this only
re-tags jobs scanned before the field existed. Only the `## Posting` body is used (never the
`## Agent evaluation` section — that's our analysis, not the JD). Idempotent.

Run from the `api/` directory with `app` on the path (same as scripts/demo_smoke.py), optionally
targeting a demo persona's dataset:

    PYTHONPATH=. python ../scripts/backfill_keywords.py            # the active dataset
    PYTHONPATH=. python ../scripts/backfill_keywords.py marcela    # a specific demo persona
"""
import os
import sys


def main(persona: str = "") -> int:
    if persona:
        os.environ["PEREGRINE_DATASET"] = persona.strip().lower()  # read by app.config at import
    from app import data_store as store
    from app.agent.tools import _posting_description  # the canonical '## Posting'-only extractor
    from app.job_tags import extract_keywords

    jobs = store.list_jobs()
    changed = 0
    for j in jobs:
        # Reuse the app's own posting extractor — '## Posting' section only, excluding the
        # '## Agent evaluation' block, so our analysis can never leak into the search index.
        kw = extract_keywords(_posting_description(store.read_job_md(j.id)))
        if kw and kw != j.keywords:  # never overwrite existing keywords with "" (e.g. a missing snapshot)
            j.keywords = kw
            changed += 1
    if changed:
        store.write_jobs(jobs)
    print(f"backfilled keywords on {changed}/{len(jobs)} jobs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else ""))
