# Scanning: how it works, and why it's compliant

Peregrine's scanner is deliberately narrow: it reads **public, opt-in ATS job feeds for
companies you explicitly list**, and refuses everything else. There is no broad web
crawling, no platform-wide search, and no attempt to defeat a site's protections. This
document describes exactly what it does so the claims in the README's disclaimer are
verifiable against the code.

## Per-company, not platform-wide

You list the companies you care about in `config/portals.yml` (copy
[`config/portals.example.yml`](../config/portals.example.yml) to create it), each with an
ATS **provider** + the company's **slug** on that ATS:

```yaml
companies:
  - name: Anthropic
    provider: greenhouse
    slug: anthropic
```

A scan iterates **only** that list and calls each company's **own public ATS feed** — the
same endpoint the ATS publishes to render that company's public job board. It never
enumerates a whole ATS, never follows arbitrary links, and never contacts a host it wasn't
configured for. (A `queries` field exists in the example config but is **not** used by the
scanner — there is no keyword crawl.)

| Provider | Public endpoint (per company slug) |
| --- | --- |
| Greenhouse | `boards-api.greenhouse.io/v1/boards/<slug>/jobs?content=true` |
| Ashby | `api.ashbyhq.com/posting-api/job-board/<slug>` |
| Lever | `api.lever.co/v0/postings/<slug>?mode=json` |
| Recruitee | `<slug>.recruitee.com/api/offers/` |
| SmartRecruiters | `api.smartrecruiters.com/v1/companies/<slug>/postings` |
| Workable | `apply.workable.com/<slug>/jobs.md` (public feed) |

These are the boards' **own published APIs** — a company is on them because it chose that
ATS and made its board public. A single posting you **paste** from `amazon.jobs` or
`jobs.apple.com` is fetched once (they have no public *listing* feed, so we don't bulk-scan
them). For anything else, paste the job text — no fetch happens.

## The one gate every fetch goes through

Every outbound board request is made by `crawl_policy.safe_get()`
([`api/app/agent/crawl_policy.py`](../api/app/agent/crawl_policy.py)) — there is no other
sanctioned fetch path, and every provider fetch + the single-URL ingest use it. It enforces,
in order, before any bytes leave the machine:

1. **Block-list** — hosts whose Terms forbid scraping or that bot-protect (LinkedIn, Indeed,
   Glassdoor, Meta) are refused with a human-readable reason. Paste the text instead.
2. **Allow-list** — only the ATS hosts above may be fetched; any other host is refused.
   This is the hard boundary (it also closes SSRF).
3. **robots.txt** — fetched and honored per host (cached); an explicit `Disallow` refuses.
4. **Rate limit** — at least 2 seconds between requests to the same host.
5. **Honest identity** — a self-identifying `User-Agent` with a contact URL. We never spoof
   a browser, never send credentials/cookies, and never touch login-, paywall-, or
   CAPTCHA-protected content.

Covered by [`api/tests/test_crawl_policy.py`](../api/tests/test_crawl_policy.py): allowed
hosts pass, blocked hosts raise, arbitrary hosts are refused.

## Privacy

Your profile, CV, jobs, and applications stay on your machine (gitignored). The only
network traffic Peregrine makes is:

- the **public ATS feeds** above, during a scan; and
- your **configured LLM provider** (`anthropic` / `openai` / `ollama`, or none in `mock`
  mode) for the AI features — the only calls in `api/app/agent/llm.py`.

Nothing else is sent anywhere, and nothing is phoned home.

## Extending the scanner safely (developer rules)

If you add or change a provider, keep these invariants — they are what make the disclaimer
true:

1. **Every outbound fetch goes through `crawl_policy.safe_get()`.** Never call
   `httpx`/`requests` directly for a job board. (The only direct calls allowed are the LLM
   provider calls in `llm.py`.) This is enforced by a **pre-commit guard**
   ([`hooks/pre-commit`](../hooks/pre-commit), installed via `scripts/install-hooks.sh`) that
   blocks staged `api/**.py` containing raw `httpx`/`requests`/`urllib.request` or a
   `Mozilla/` browser User-Agent outside `crawl_policy.py` / `llm.py` — so the rule can't be
   silently bypassed.
2. **Only add a host to `ALLOWED_HOSTS` after confirming** its feed is a public API that
   *permits automated access* (check the site's Terms and `robots.txt`). When in doubt, add
   it to `BLOCKED_HOSTS` with a reason, or support paste-only.
3. **Never add browser impersonation, cookies, auth headers, or CAPTCHA/anti-bot evasion.**
4. **Stay per-company.** Don't add platform-wide enumeration or following of arbitrary
   links from feed content (feed URLs are already host-checked before storing).
5. **Privacy:** scan results are public job postings; never fetch or store anything from a
   user's account, and keep all personal data local.
