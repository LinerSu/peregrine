---
name: upskill
description: Analyze the gap between the user's profile and a job (or all tracked jobs) and produce a prioritized learning plan. Use when the user asks what they're missing or how to become competitive.
---

# Upskill

## Goal
Show what's missing for target roles and how to close the gap.

## Steps
1. Load `config/profile.yml` and the target job(s) from `data/`.
2. Diff required/preferred skills against the user's skills.
3. Rank gaps by frequency across targets and impact on fit.
4. For each top gap, suggest a concrete learning resource and rough time.

## Rules
- Be honest about effort; insights, not guarantees.
- Tie advice to specific postings so it's actionable.

## Output
A prioritized gap list + a short learning plan.
