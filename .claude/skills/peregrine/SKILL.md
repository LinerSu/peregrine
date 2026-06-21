---
name: peregrine-internal
description: Run Peregrine job-search analyses locally and save the result so the web UI updates. Use when working in the Peregrine repo and the user asks to "evaluate fit" or "analyze skill gaps" for a job id like 2026-001.
---

# Peregrine — Internal-mode worker

You're inside the Peregrine job-search app. The user runs you in a local terminal
("Internal mode") so analyses run on their own subscription, not the metered API.
When they ask for an analysis, **you do the reasoning, then persist the result via
the local API** so the web page reflects it exactly like External (API) mode.

- API: `http://localhost:8000`
- Posting text: `data/jobs/<id>.md`   ·   User profile: `config/profile.yml`
- `<id>` is a job id like `2026-001`. List them with `curl -s http://localhost:8000/api/jobs`.

## "analyze skill gaps for <id>"

1. Read `data/jobs/<id>.md` and `config/profile.yml`.
2. Follow the rubric in `.agents/skills/upskill/SKILL.md`: diff required/preferred
   skills vs. the profile, rank gaps, suggest a concrete way + rough time to close each.
3. Persist it (this is what makes it appear in the **Upskilling** tab):
   ```bash
   curl -s -X PUT http://localhost:8000/api/jobs/<id>/upskilling \
     -H 'content-type: application/json' \
     -d '{"summary":"<one short paragraph>",
          "missing_skills":[{"skill":"<name>","why":"<why it matters here>","how_to_close":"<step + rough time>"}]}'
   ```
4. Tell the user it's saved — the Upskilling tab will show it.

## "evaluate fit for <id>"

1. Read `data/jobs/<id>.md` and `config/profile.yml`.
2. Follow the rubric in `.agents/skills/fit-eval/SKILL.md`: evidence-grounded
   strengths/weaknesses, materials to prepare, a `fit_score` in [0,1], and a
   recommendation of `apply` | `hold` | `skip`.
3. Persist it (updates the job's fit score + the "Agent evaluation" section):
   ```bash
   curl -s -X PUT http://localhost:8000/api/jobs/<id>/evaluation \
     -H 'content-type: application/json' \
     -d '{"fit_score":0.0,"recommendation":"hold","strengths":[],"weaknesses":[],"materials":[]}'
   ```
4. Tell the user it's saved — refresh the job in the Jobs tab.

## Rules
- **Never fabricate** skills or experience the profile doesn't support — ground every
  strength in evidence (same rule as External mode).
- Use the **`PUT`** routes above — they only *store* what you send; the reasoning is
  yours. Do **not** call the metered `POST .../evaluate` or `POST .../upskilling`
  endpoints — those spend an API key, which Internal mode exists to avoid.
