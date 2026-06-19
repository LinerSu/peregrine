---
name: cv-intake
description: Parse a user's CV/resume into structured skills and experience, then store it as long-term memory in config/profile.yml. Use when the user pastes or uploads a CV, or asks to update their profile.
---

# CV Intake

## Goal
Turn raw CV text into a structured profile the rest of the system can reason over.

## Steps
1. Read the raw CV text (pasted in chat or extracted from an uploaded file).
2. Extract: name, headline, location, work authorization, roles/experience,
   and a **skills list** with `name`, `level`, and `evidence` (where it was used).
3. Merge into `config/profile.yml` — update existing fields, never fabricate.
4. Summarize what changed and ask the user to confirm anything ambiguous.

## Rules
- Never invent skills or experience the CV does not support.
- Prefer specific evidence ("Built churn pipeline in PyTorch") over bare nouns.
- Save the resume file under `resume/` and set `resume_path`.

## Output
A short confirmation of the parsed profile + the list of skills detected.
