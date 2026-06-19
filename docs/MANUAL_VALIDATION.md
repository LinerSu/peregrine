# Manual validation — web behaviors

A click-through checklist to validate Peregrine's UI by hand. ~10 minutes.
Tick each **Expected** box as you go.

> **Heads-up on the mock AI:** by default `LLM_PROVIDER=mock`, so anything
> AI-driven (fit scoring, CV parsing, upskilling) returns **deterministic
> placeholders** — e.g. fit `0.50`, a "(mock) …" gap. That's expected. The
> *behaviors* below all work; the *quality* of those AI outputs turns real once
> you set an LLM key in `.env`.

---

## 0. Start the app

```bash
cd my-job-search
cp .env.example .env          # only needed the first time
docker compose up --build     # leave it running
```

- [ ] Web loads at **http://localhost:5173**
- [ ] API healthy at **http://localhost:8000/api/health** → `{"status":"ok","provider":"mock",...}`

---

## 1. Layout & tabs

- [ ] Header shows the **Peregrine** logo + title
- [ ] Left side: a persistent **Assistant** chat panel
- [ ] Right side: tab bar — **Jobs · Applications · Targets · Profile / CV · Upskilling**
- [ ] Jobs tab is selected; the table shows **1 seed job** (Anthropic — Machine Learning Engineer)

---

## 2. Chat assistant

1. In the chat box type **`find jobs matching my CV`**, press Enter.
   - [ ] Assistant replies with a scan summary (e.g. "0 new … 1 jobs now tracked")
2. Paste a **job URL** into the chat and send (these are live; if one 404s the posting expired — try another):
   - Apple: `https://jobs.apple.com/en-us/details/200668037-0836/technical-program-manager-sensing?team=OPMFG`
   - Ashby: `https://jobs.ashbyhq.com/openai/8fb1615c-34bf-47c4-a1d1-b7b2f836bbd3`
   - Lever: `https://jobs.lever.co/leverdemo/33538a2f-d27d-4a96-8f05-fa4b0e4d940e`
   - [ ] Assistant replies "Ingested **<role>** at **<company>** as `2026-00x`…"
   - [ ] The new job appears in the **Jobs** table (right pane)
3. **Safety check** — paste a blocked URL: `https://www.linkedin.com/jobs/view/4012345678/`
   - [ ] Assistant politely **refuses**: "…linkedin.com is blocked by policy — … Paste the job description text instead."
   - [ ] No job is added

---

## 3. Jobs table — sort & filter

- [ ] Columns: **Fit · Company · Position · Status · Flex · Salary · Location**
- [ ] Click the **Company** header → rows sort A→Z; click again → Z→A (arrow ▲/▼ shows)
- [ ] Click **Fit** → sorts by score; **Salary** → sorts by pay
- [ ] Type in **Filter jobs…** (e.g. `apple`) → only matching rows remain; clear it → all return
- [ ] Click a row → it highlights and the **detail** opens on the right

---

## 4. Job detail — evaluate, cards, apply gate

Select the **Anthropic** seed job (or any job).

1. Click **Evaluate fit**
   - [ ] After a moment, the body shows **cards**: Posting/Description, then **Strengths** (green), **Weaknesses / gaps** (amber), **Materials to prepare** (indigo)
   - [ ] Header shows a fit score (mock → `0.50`)
2. Apply gate:
   - [ ] Before preparing, the footer says "Review … then click **Prepare to apply**"
   - [ ] Click **Prepare to apply** → an **Apply on company site ↗** button + an **I applied ✓** button appear
   - [ ] The Apply link points at the real company URL (it never submits for you)
3. Click **I applied ✓**
   - [ ] Footer changes to "✓ Applied — tracked in the Applications tab"
   - [ ] The **Applications** tab count badge increments

---

## 5. Applications tracker

Open the **Applications** tab.

1. **See it:** the job you marked applied is a row with company, role, **status**, applied date, etc.
   - [ ] `applied_date` is today
2. **Update status:** change the **Status** dropdown → `interviewing`
   - [ ] The colored pill updates and persists (switch tabs and back — still `interviewing`)
3. **Edit details:** set an **Interview** date; type in **Contacts** and **Notes**, click away
   - [ ] Values stick after a tab switch / page reload
4. **Manual add** (a job you applied to elsewhere): click **+ Add**
   - Fill **Company** = `Stripe`, **Position** = `Staff Engineer`, status `applied`, optional location/URL → **Save**
   - [ ] A new Stripe row appears
5. **Filter:** type `stripe` in **Filter applications…**
   - [ ] Only the Stripe row shows; clear → all return
6. **Sort:** click the **Company** / **Status** / **Applied** headers
   - [ ] Rows reorder (▲/▼ indicator)
7. **Remove:** click the **✕** on the Stripe row → confirm
   - [ ] Row disappears; count badge decrements

---

## 6. Targets (search intent)

Open the **Targets** tab.

1. Fill some fields: Roles = `Backend Engineer`, Locations = `Remote`, Work mode = `Remote`,
   Min salary = `180000`, Must-have = `python`, Exclude = `crypto` → **Save preferences**
   - [ ] "Saved ✓" appears
2. Switch to another tab and back, **or reload the page**
   - [ ] Your values are still there (persisted to `config/profile.yml`)

---

## 7. Profile / CV

Open the **Profile / CV** tab.

1. **Upload:** click **Choose file (PDF, .txt, .md)** and pick any PDF or text résumé
   - [ ] No error; with a real LLM the parsed profile/skills populate above (mock → may stay empty, but the upload succeeds)
2. **Paste:** paste some résumé text → **Parse CV → profile**
   - [ ] No error (same mock caveat)
3. - [ ] **External resources** links (Overleaf, Tech Interview Handbook) open in a new tab

---

## 8. Upskilling

Open the **Upskilling** tab.

1. Pick a job from the dropdown → **Analyze gaps**
   - [ ] A summary line + one or more **gap cards** (skill · why · how to close) appear
     (mock → a single "(mock) example gap"; real LLM → tailored gaps)

---

## 9. Reset (optional)

To return to a clean slate (removes ingested jobs + tracked applications you created):

```bash
git checkout -- data/jobs.csv data/applications.csv
find data/jobs -name '*.md' ! -name '2026-001.md' -delete
# clear local Targets/profile if you set them:
#   rm config/profile.yml   (it's gitignored / local-only)
docker compose restart api
```

---

## Notes

- **Your data is local:** jobs/applications in `data/*.csv` + `data/jobs/<id>.md`; profile + targets in `config/profile.yml`.
- **Live postings expire:** the Apple/Ashby/Lever example URLs may 404 over time — grab a fresh URL from those boards if so.
- **Scan button:** returns 0 until you list companies in `config/profile.yml`'s sibling `config/portals.yml` (e.g. `companies: [{name: Anthropic, provider: greenhouse, slug: anthropic}]`). The chat URL-paste flow above needs no setup.
- **Make the AI real:** set `LLM_PROVIDER` + the matching key in `.env`, then `docker compose up --build`. Fit scores, CV parsing, and upskilling become genuine.
