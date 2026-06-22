---
name: cv-tailor
description: Produce a one-page CV tailored to a specific job, as compilable LaTeX, grounded only in the candidate's profile.
---

# Tailored-CV writer

Given the candidate's profile and a job posting, write a **one-page CV tailored to
that job**, as a complete, compilable LaTeX document.

## Tailoring
- **Ground everything in the profile** — never invent employers, dates, numbers, or
  skills. If the profile lacks something the job wants, simply don't claim it.
- **Lead with relevance:** order skills/experience so the most job-relevant items
  come first; drop or compress weakly-relevant content to keep it to one page.
- **Mirror the posting's language** where it's truthful (ATS keywords), but don't
  keyword-stuff.

## LaTeX rules (must compile in a base TeX install)
- Use only standard packages: `article`, `geometry`, `enumitem`, `hyperref`
  (`[hidelinks]`), optionally `titlesec`, `xcolor`. No `moderncv`, no `fontspec`.
- **No `\write18`, no `-shell-escape`, no `\input`/`\include` of external files** —
  the document must be self-contained.
- Escape LaTeX specials in user text (`& % $ # _ { } ~ ^`).
- Target **one page**. `\pagestyle{empty}`. A4, ~2cm margins.
- Return **only** the LaTeX document (`\documentclass … \end{document}`), nothing else.
