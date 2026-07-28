---
name: peregrine-internal
description: Run Peregrine job-search analyses locally and save the result so the web UI updates. Use when working in the Peregrine repo and the user asks to "evaluate fit", "analyze skill gaps", or "draft a cover letter" or "tailor my cv" for a job id like 2026-001, or "parse my cv" to build the profile, or "ingest the job I pasted" to add a posting, or "analyze my patterns" to read application outcomes.
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

## "draft a cover letter for <id>"

1. Read `data/jobs/<id>.md` (posting + the "Agent evaluation" section) and
   `config/profile.yml`.
2. Read style/structure samples — the curated ones in `api/app/cover_letters/*.md`
   and any of the user's own in `data/cover_letter_samples/*.md`. You **may** also
   web-search for a couple of reputable cover-letter examples to refine structure
   (this is fine in Internal mode — it's your own search, on the user's
   subscription). Match tone/structure only; never copy phrasing or invent facts.
3. Follow the rubric in `.agents/skills/cover-letter/SKILL.md`: 3–4 short
   paragraphs, evidence-grounded, ~200–300 words, no fabrication.
4. Persist it (this is what makes it appear in the **Cover letter** panel). Send
   the letter as a JSON string in `content`:
   ```bash
   curl -s -X PUT http://localhost:8000/api/jobs/<id>/cover-letter \
     -H 'content-type: application/json' \
     -d "$(jq -n --arg c "<the full letter text>" '{content:$c}')"
   ```
5. Tell the user it's saved — the Cover letter panel will show it.

## "parse my cv"

1. Read the raw CV the user submitted in the web app at `config/cv_source.md`, and
   the current `config/profile.yml`. (Under a `PEREGRINE_DATASET` demo persona these
   live in `.demo/<persona>/config/` instead.) Extract only the CV-derived fields —
   don't set `resume_path` (the Internal flow has only the text, no original file).
2. Follow the rubric in `.agents/skills/cv-intake/SKILL.md`: extract name, headline,
   location, `links`, `skills`, and `sections` (education/experience/research/service/
   awards/projects — each with a one-sentence `summary` + `items`). Never invent.
3. Persist it (this updates the **Profile** tab — store-only merge):
   ```bash
   curl -s -X PUT http://localhost:8000/api/profile \
     -H 'content-type: application/json' \
     -d '{"name":"...","headline":"...","location":"...",
          "links":{"github":"https://github.com/…","scholar":"https://…"},
          "skills":[{"name":"...","level":"...","evidence":"..."}],
          "sections":[{"id":"education","title":"Education","summary":"<one sentence>",
            "items":[{"heading":"PhD, …","subhead":"2019–2024 · …","detail":"…",
                      "links":[{"label":"thesis","url":"https://…"}]}]}]}'
   ```
4. Tell the user it's saved — the Profile tab will refresh.

## "tailor my cv for <id>"

1. Read `data/jobs/<id>.md` and `config/profile.yml`.
2. Follow the rubric in `.agents/skills/cv-tailor/SKILL.md`: a **one-page** CV
   tailored to this job, as a complete, **compilable LaTeX** document, grounded only
   in the profile. Standard packages only; no `\write18`/shell-escape/external files.
3. Persist it (the API saves the `.tex` and compiles a PDF — this is what fills the
   **Tailored CV** panel). Send the LaTeX as a JSON string in `tex`:
   ```bash
   curl -s -X PUT http://localhost:8000/api/jobs/<id>/cv \
     -H 'content-type: application/json' \
     -d "$(jq -n --arg t "$(cat cv.tex)" '{tex:$t}')"
   ```
   (Write the LaTeX to `cv.tex` first, or inline it into the `--arg`.)
4. Tell the user it's saved — the Tailored CV panel shows it with a PDF download.

## "ingest the job I pasted"

1. Read the raw posting the user pasted/uploaded at `config/job_source.md`.
2. Parse it into fields — `company`, `position`, `company_job_id` (\"\" if none),
   `location`, `url`, `posted_date` (YYYY-MM-DD or \"\"), `close_date` (deadline,
   YYYY-MM-DD or \"\"), `flexibility` (remote|hybrid|onsite ONLY if stated),
   `salary_min`/`salary_max` (plain numbers) + `currency` (e.g. USD),
   `description` (clean plain text). Use ONLY what's in the posting; never invent.
3. Create the tracked job (store-only — this is what adds it to the Jobs tab):
   ```bash
   curl -s -X POST http://localhost:8000/api/jobs/ingest-doc/save \
     -H 'content-type: application/json' \
     -d '{"company":"...","position":"...","location":"...","url":"...","posted_date":"...","close_date":"...","flexibility":"...","salary_min":0,"salary_max":0,"currency":"...","description":"..."}'
   ```
4. **Auto-evaluate**: if the user's profile is set up (`config/profile.yml` has a
   name/skills/sections) and the save CREATED a new job (response `"created": true`),
   immediately continue with the "evaluate fit" flow for the new job id — the user
   expects an ingested job to arrive scored. Skip when the profile is empty, when the
   job deduped onto an existing one, or when the user asked to just add it.
5. Tell the user it's added (and evaluated, if step 4 ran) — the Jobs tab will show it.

## "evaluate all jobs missing a fit score"

1. `curl -s http://localhost:8000/api/jobs` — collect ids where `fit_score` is null
   and `status` is `open` (the backfill rule: new capabilities apply to
   already-tracked jobs too, not only future ingests).
2. For each id, run the "evaluate fit for <id>" flow above and PUT the result.
3. Tell the user how many jobs were evaluated and their scores.

## "analyze my patterns"

1. Fetch the deterministic outcome analytics:
   ```bash
   curl -s http://localhost:8000/api/stats/outcomes
   ```
2. Follow the rubric in `.agents/skills/patterns/SKILL.md`: a grounded read of what's
   working / at risk / to do. **Ground every claim in those numbers — never invent
   data**, and keep it tentative when the sample is small.
3. Persist it (this is what fills the **Pattern insights** card in the Insights tab):
   ```bash
   curl -s -X PUT http://localhost:8000/api/stats/patterns \
     -H 'content-type: application/json' \
     -d '{"summary":"<1–3 sentences>","wins":["..."],"risks":["..."],"actions":["..."]}'
   ```
4. Tell the user it's saved — the Insights tab will show it.

## Rules
- **Never fabricate** skills or experience the profile doesn't support — ground every
  strength in evidence (same rule as External mode).
- Use the **`PUT`/store-only** routes above — they only *store* what you send; the
  reasoning is yours. Do **not** call the metered routes (`POST .../evaluate`,
  `.../upskilling`, `.../cover-letter`, `.../cv`, `/api/cv`, `/api/jobs/ingest-doc`,
  `/api/jobs/ingest`, `POST /api/stats/patterns`) — those spend an API key, which
  Internal mode exists to avoid.
