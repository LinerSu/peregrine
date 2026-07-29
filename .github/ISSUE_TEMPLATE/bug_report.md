---
name: Bug report
about: Something behaves wrongly, loses data, costs money, or contradicts itself
labels: bug
---

<!--
Keep the headings. Both people and coding agents read these issues, and a predictable
shape is what makes them usable as work orders.

NEVER include personal data: no CV or profile contents, no real postings, no employer
names from a real search, no file paths containing personal information. Reproduce with
placeholders — Acme, Initech, Globex.
-->

## What happens

One or two sentences on the observable behaviour. What did the app do?

## How to reproduce

Numbered steps, or the request/command. If it's a race or a background task, say what has
to be happening at the same time — that's usually the whole bug.

## Why it matters

The cost to the user: data lost, money spent, a wrong decision made, a contradiction on
screen. If it's cosmetic, say so.

## Where

Repo-relative paths, and the route or function if you know it — `api/app/routers/jobs.py`,
`POST /api/jobs/scan`. Best guess is fine; wrong guesses are cheap to correct.

## What would fix it

Optional. A direction, not a patch. If you're unsure, say what you ruled out.

## Notes

Anything that constrains the fix — e.g. it must work in **both** modes (External API and
Internal local-Claude), or it touches data that must never be committed.
