# Edit your data directly

Everything Peregrine knows is plain files on your machine, so you can edit them by hand and
the app picks the changes up. The web UI is the easy path; this is the power-user path.

## The files that matter

- **`config/portals.yml`** — your **scan sources** and **filters**. Add companies (name +
  provider + slug) and set `filters:` (`max_age_days`, `locations`, `remote_only`). This is
  what **Scan** reads. (Copy `config/portals.example.yml` to start.)
- **`config/profile.yml`** — your **profile** (name, headline, skills, links, experience
  sections) and **search targets**. The Profile / CV tab edits this; you can also edit it
  directly.
- **`resume/`** — drop your master résumé here (`.pdf` / `.tex` / `.md` / `.txt`). The
  **Profile / CV** tab's **Import from resume/** reads the newest file to build your profile.
- **`data/jobs.csv`**, **`data/applications.csv`** — the source of truth for jobs and
  applications (the tables you see). Per-job detail is saved under `data/jobs/<id>.md`.
  Two rules if you edit these in a spreadsheet:
  - **`id` must look like `2026-001`** (year, dash, at least three digits). It is not a
    label — it names `data/jobs/<id>.md` and the `applications/<id>/` folder, so an
    invented id is refused rather than acted on.
  - A value that would start with `=`, `+`, `-` or `@` is stored with a leading `'`.
    That apostrophe is deliberate: it stops your spreadsheet from *running* a job title
    a board sent us. Leave it alone; the app strips nothing and adds nothing further.

## How changes take effect

- **Config/data edits** (`portals.yml`, `profile.yml`, CSVs) are read live — just refresh the
  page (or re-scan, for portals).
- Prefer the UI for jobs/applications so IDs and links stay consistent; reach for the files
  when you want to bulk-edit or template your setup.

## A note on the data folder

`data/`, `config/`, and `resume/` are **gitignored** — they're yours and never committed. On
a fresh clone the app copies the example files so it isn't empty.

## Next

- **Demo & test datasets** — swap in a fully-populated example without touching your data.
- **Privacy & compliance** — what stays local.
