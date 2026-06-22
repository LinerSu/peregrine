---
name: peregrine-internal
description: Run Peregrine job-search analyses locally and save the result so the web UI updates. Use when working in the Peregrine repo and the user asks to "evaluate fit", "analyze skill gaps", or "draft a cover letter" or "tailor my cv" for a job id like 2026-001, or "parse my cv" to build the profile.
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
   location, and skills (array of `{name, level, evidence}`). Never invent skills.
3. Persist it (this updates the **Profile** tab — store-only merge):
   ```bash
   curl -s -X PUT http://localhost:8000/api/profile \
     -H 'content-type: application/json' \
     -d '{"name":"...","headline":"...","location":"...","skills":[{"name":"...","level":"...","evidence":"..."}]}'
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

## Rules
- **Never fabricate** skills or experience the profile doesn't support — ground every
  strength in evidence (same rule as External mode).
- Use the **`PUT`** routes above — they only *store* what you send; the reasoning is
  yours. Do **not** call the metered `POST` routes (`.../evaluate`, `.../upskilling`,
  `.../cover-letter`, `.../cv`, `/api/cv`) — those spend an API key, which Internal mode exists to avoid.
