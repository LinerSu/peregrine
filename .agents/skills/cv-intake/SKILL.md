---
name: cv-intake
description: Parse a user's CV/resume into structured skills and experience, then store it as long-term memory in config/profile.yml. Use when the user pastes or uploads a CV, or asks to update their profile.
---

# CV Intake

## Goal
Turn raw CV text into a structured profile the rest of the system can reason over.

## Steps
1. Read the raw CV text (pasted in chat or extracted from an uploaded file).
2. Extract, as structured data:
   - `name`, `headline`, `location`.
   - `links` — profile links present (`github`, `website`, `linkedin`, `scholar`,
     `twitter`, `email`); omit ones the CV doesn't have.
   - `skills` — list of `{name, level, evidence}`.
   - `sections` — the résumé sections, each `{id, title, summary, items}`:
     - `id` ∈ `education | experience | research | service | awards | projects`
     - `title` — display heading (e.g. "Industry Experience").
     - `summary` — **one sentence** capturing the section (the collapsed view).
     - `items` — `[{heading, subhead, detail, links:[{label,url}]}]`: `heading` is the
       entry (degree / role / paper / project), `subhead` is dates/place, `detail` is the
       full text, `links` are any URLs for that entry (repo, paper, demo…).
3. Merge into `config/profile.yml` — update existing fields, never fabricate. Only
   include sections the CV actually supports.
4. Summarize what changed and ask the user to confirm anything ambiguous.

## Rules
- Never invent skills, experience, or links the CV does not support.
- Prefer specific evidence ("Built churn pipeline in PyTorch") over bare nouns.
- Keep each section `summary` to one honest sentence.
- Save the resume file under `resume/` and set `resume_path`.

## Output
A short confirmation: name/headline + the sections and skills detected.
