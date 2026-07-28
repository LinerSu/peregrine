# Target your scan

**Goal:** control *what* a scan pulls in, so your jobs list stays focused.

## Scan only certain companies

On the **Jobs** tab, the **Scan** control has a checkbox per configured company. Tick the ones
you want and click **Scan** — only those are fetched (and only their jobs are tidied up).
Tick nothing to scan everything (the default). The button shows what you're about to do
("Scan all" / "Scan 2 selected").

## Filter what gets stored

Filters live in `config/portals.yml` (see *Edit your data directly*) under `filters:`:

- **`max_age_days`** — only keep postings from the last N days. `0` = no limit; e.g. `60`
  ≈ the last two months. Older postings aren't scanned in, and tracked **open** jobs that age
  past the cutoff are moved to **Closed** automatically (your applied jobs are never touched).
- **`retention_days`** — `0` = keep closed jobs forever. Set e.g. `180` and, at the end of
  each scan, **closed** jobs posted more than ~6 months ago are **deleted** — the row and its
  generated materials (evaluation, cover letter, tailored CV). Jobs linked to an application
  are never removed. For a one-shot cleanup without waiting for a scan, use
  **Search → Housekeeping → Purge now**.
- **`locations`** — only roles matching these locations (empty = any).
- **`remote_only`** — only remote roles.

You can also set search keywords/locations in the **Targets** tab.

## Stale & closed jobs

Companies often leave old postings up for months. Two things keep your list current:

- **Disappeared postings** — if a job is gone from the board on a later scan, it's marked
  **closed** (kept, not deleted, so a linked application isn't lost).
- **Aged-out postings** — with `max_age_days` set, old open jobs are closed too.

Closed (and manually removed) jobs leave the **All** view and live under the **Closed** tab,
where you can review them — or set a status back to **open** to recover one.

## Why the count sometimes jumps

A first scan of a big board can add a lot at once (up to a safety cap per scan — click Scan
again for more). After that, re-scans add only what's genuinely new. None of it is
duplicated.

## Next

- **External vs Internal mode** — how the AI runs.
- **Edit your data directly** — the config files behind all of this.
