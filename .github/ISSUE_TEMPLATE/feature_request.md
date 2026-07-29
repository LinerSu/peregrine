---
name: Feature request or gap
about: Something missing, incomplete, or worth building
labels: enhancement
---

<!--
Keep the headings. Both people and coding agents read these issues, and a predictable
shape is what makes them usable as work orders.

NEVER include personal data: no CV or profile contents, no real postings, no employer
names from a real search. Describe the shape of the need and use placeholders — Acme,
Initech, Globex.
-->

## What's missing

The gap, in the app's terms. If something exists but falls short, say what it produces
today versus what it should.

## Why it matters

Who is stuck, and on what. "Nice to have" is a valid answer — say it, so it can be ranked
honestly against things that are actively wrong.

## Where

The area it lands in — routes, components, the skill file, the crawl policy. Repo-relative
paths where you can.

## What would fix it

The proposed direction, and what you'd deliberately leave out of a first version.

## Notes

Constraints the implementation has to respect. The common ones here: it must work in
**both** modes (External API and Internal local-Claude); user material is private and
belongs under the existing gitignore + hook guards; scraping stays inside
`api/app/agent/crawl_policy.py`.
