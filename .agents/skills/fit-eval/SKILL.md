---
name: fit-eval
description: Score how well a job matches the user's profile and produce strengths, weaknesses/gaps, and materials-to-prepare. Use when evaluating a specific job or ranking scan results. Runs as an isolated evaluator subagent.
---

# Fit Evaluation

## Goal
Produce an honest, evidence-based fit assessment that gates the Apply button.

## Steps
1. Load the job (`data/jobs/<id>.md`) and `config/profile.yml`.
2. Reason about fit (NOT keyword matching): responsibilities vs. experience,
   required vs. preferred qualifications, level, comp, location, restrictions.
3. Emit a `fit_score` in [0,1] and write back to `data/jobs.csv`.
4. Append to the job's `## Agent evaluation` section:
   - **Strengths** — where the user clearly matches.
   - **Weaknesses / gaps** — missing or weak requirements.
   - **Materials to prepare** — resume tweaks, portfolio, references, examples.
5. Recommend apply / hold / skip.

## Rules
- **Evidence-grounded:** every strength must cite specific evidence from the
  profile (a skill, role, or project). If you can't point to evidence, it is not
  a strength — put it in weaknesses/gaps. Never infer or fabricate experience.
- A required qualification with no supporting profile evidence is always a **gap**.
- Flag restrictions (citizenship, sponsorship) prominently.
- A second pass (reviewer subagent) critiques this output for fabrication and
  missed restrictions before it's shown.

## Output
Structured `{ fit_score, strengths[], weaknesses[], materials[], recommendation }`.
