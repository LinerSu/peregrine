---
name: materials-prep
description: Given a job the user wants to apply to, prepare the application materials checklist and draft tailored artifacts (cover letter, resume tweaks). Use right before the user clicks Apply.
---

# Materials Prep

## Goal
Make sure the user walks into an application prepared — this is the last
human-in-the-loop gate before the Apply link is exposed.

## Steps
1. Read the job's `fit-eval` output (strengths / weaknesses / materials).
2. Produce a concrete checklist: tailored resume version, cover letter,
   references, work samples, talking points for gaps.
3. Draft a cover letter from `templates/` mirroring the posting's language and
   the user's real experience. Save under `applications/<id>/`.
4. Note any restrictions (sponsorship, citizenship) the user must address.

## Rules
- Never auto-submit. Only prepare; the user clicks Apply.
- Every claim must trace to `config/profile.yml`. No fabrication.

## Output
A checklist + draft artifact paths, then surface the Apply link.
