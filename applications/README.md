# Applications

One folder per application/job, keyed by the job `id` (e.g. `2026-001/`). When you
generate materials for that job, copies are written here automatically:

- `cover_letter.md` — the tailored cover letter
- `cv.tex` / `cv.pdf` — the job-tailored CV (LaTeX source + compiled PDF, when a LaTeX
  engine is available)

The canonical copies also live beside the posting in `data/jobs/<id>.*`; this folder
is the per-submission bundle. The sortable application metrics live in
`data/applications.csv`. (Folder contents are gitignored — your materials stay local.)
