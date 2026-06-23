# Find jobs

**Goal:** pull current openings into Peregrine so you can score and track them.

## 1. Tell it which companies to watch

Peregrine reads each company's **own public job board**, so you list the companies you care
about. The quickest way is the **Targets** tab (or edit `config/portals.yml` directly — see
*Edit your data directly*). Each entry is a company name + which job-board platform it uses
(Greenhouse, Ashby, Lever, Recruitee, SmartRecruiters, or Workable) + the company's slug on
that platform.

A fresh install ships with a couple of example companies so you can try Scan immediately.

## 2. Scan

Open the **Jobs** tab and click **Scan sources** (top-left of the jobs list). Peregrine
fetches the current openings from each configured company and adds the ones you don't already
have. You'll see a summary like:

> Found 12 new (40 dupes · 3 filtered).

- **new** — postings added this scan.
- **dupes** — already in your list (skipped, never duplicated).
- **filtered** — skipped by your filters (e.g. too old — see *Target your scan*).

A scan never adds a duplicate, so you can click it as often as you like.

## 3. Browse

New jobs land in the **Jobs** table. Use the tabs (**All / Open / Evaluated / …**), the
search box, the role filter, and the column headers to sort. Star the ones you like. Click a
row to open it and see the full posting.

## Don't see a Scan source you want?

- Some sites (LinkedIn, Indeed, Glassdoor, Meta) can't be scanned — their terms forbid it.
  For those, **paste** the job text or a URL instead (see *Add jobs & applications* under your
  first tasks, or the **Add a job** button on the Jobs tab).
- To scan only one or two of your companies, use the **company checkboxes** next to Scan —
  see *Target your scan*.

## Next

- **Check your fit** — score a job against your profile.
